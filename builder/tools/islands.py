"""islands.py - RQ7 / N9 build gate (ss-life 11-16): orders that send a man to a graph node he cannot path to, read offline from a BUILT mission.
    python -P tools/islands.py <build dir> [--quiet]
Works for any built level (Sandstorm, Sirocco): objects.qvm + graphs/graph<N>.dat + ai/*.qvm.

Why (ss-look N9_cause.md): HumanAI_MoveCharacterToNode KILLS the man when AIGraphAStarSearch_CreatePath fails (humanai.c 10963-10972:
damage = vMaxDamage 0.4 + 1.0 = the logged 1.4). A path fails when the target node is on another connected part (island) of the man's
graph, or does not exist. Both men of a squad get the order on one tick = they die together.

Checked (FAIL, exit 1):
  - every node id a soldier or squad script names in a call with 'Node' in its name (MoveToNode, ...; LookAtNode excluded: no path)
  - every 'walk / run to node' command of every PatrolPath a script names (AIAction_Patrol / AISquad_* with the path id)
  - the squad's alarm switch (AISquad arg 5): the node nearest to it on the squad's graph (a man RUNS there on TriggerAlarm)
  ... must exist in the man's graph (HumanAI arg 5) and lie on the same island as the node he stands on (nearest node to his position).
Census (WARN, not an exit code): islands per graph and the men on each; men with nodes of ANOTHER island of their graph within the
engine's cover search window (HumanAI_HandleCoverSearch, humanai.c:11568: 20 m by straight distance, |dz| < 2 m, no reachability test)
- an engine-chosen cover or search node there kills the man the same way. Last line: islands: <orders> orders, <f> FAIL, <w> cover-risk men"""
import collections, glob, math, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import igiqvm
import graph as G
import alarmai
from qast import walk, lit

M = 4096.0
K_ID, K_POS = 0x735ce, 0x1d4295
NODE_CALL = re.compile(r'\b(\w*Node\w*)\(\s*(-?\d+)')
PATROL_CALL = re.compile(r'\b(\w*Patrol\w*)\(\s*(\d+)')
MOVE_CMDS = (2, 3, 4)                                      # PatrolPathCommand: 2 walk to node, 3 / 4 run variants (1 delay, 5 look at node, 7 quit)


def load(bd):
    st = igiqvm.decompile(open(os.path.join(bd, 'objects.qvm'), 'rb').read())[1]
    T, kids = {}, collections.defaultdict(list)
    for s in st:
        for e, d, par in walk(s):
            if e.name != 'Task_New':
                continue
            a = [x if isinstance(x, igiqvm.Call) else lit(x) for x in e.args]
            try:
                tid = int(a[0])
            except (TypeError, ValueError):
                continue
            T[tid] = a
            if par is not None and par.name == 'Task_New':
                try:
                    kids[int(lit(par.args[0]))].append(tid)
                except (TypeError, ValueError):
                    pass
    return T, kids


def graphs(bd, T):
    goff = {tid: tuple(float(c) for c in a[3:6]) for tid, a in T.items() if str(a[1]) == 'AIGraph'}
    out = {}
    for f in sorted(glob.glob(os.path.join(bd, 'graphs', 'graph*.dat'))):
        mm = re.match(r'graph(\d+)\.dat$', os.path.basename(f))
        if not mm:
            continue
        gid = int(mm.group(1))
        off = goff.get(gid, (0.0, 0.0, 0.0))
        pos, cur = {}, None
        for k, t, v in G.parse(f):
            if k == K_ID:
                cur = v
            elif k == K_POS and cur is not None:
                pos[cur] = tuple(v[i] + off[i] for i in range(3))
        ids, edges = G.topology(f)
        parent = {n: n for n in ids}

        def fnd(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        for a, b in edges:
            parent[fnd(a)] = fnd(b)
        comp = {n: fnd(n) for n in ids}
        sizes = collections.Counter(comp.values())
        out[gid] = dict(pos=pos, comp=comp, sizes=sizes)
    return out


def nearest(g, p):
    return min(g['pos'], key=lambda i: math.hypot(g['pos'][i][0] - p[0], g['pos'][i][1] - p[1]) + 3.0 * abs(g['pos'][i][2] - p[2]))


def script_text(bd, name):
    p = os.path.join(bd, 'ai', name + '.qvm')
    if not os.path.exists(p):
        return ''
    try:
        return alarmai.to_text(alarmai.decompile_ai(open(p, 'rb').read())[1])
    except Exception as ex:                                # (a script the decompiler does not read: reported, not judged)
        return '#UNREADABLE %s' % ex


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    quiet = '--quiet' in argv
    if len(args) != 1 or not os.path.isdir(args[0]):
        print(__doc__)
        return 2
    bd = args[0]
    T, kids = load(bd)
    GR = graphs(bd, T)
    paths = {}
    for tid, a in T.items():
        if str(a[1]) == 'PatrolPath':
            cmds = []
            for c in kids.get(tid, []):
                ca = T[c]
                if str(ca[1]) == 'PatrolPathCommand':
                    try:
                        cmds.append((int(ca[3]), int(ca[4])))
                    except (TypeError, ValueError):
                        pass
            try:
                paths[tid] = (int(a[3]), cmds)
            except (TypeError, ValueError):
                pass
    men = []                                               # (soldier id, ai id, graph, pos, squad id)
    squad_of = {}
    for tid, a in T.items():
        if str(a[1]) == 'AISquad':
            for h in kids.get(tid, []):
                squad_of[h] = tid
    for tid, a in T.items():
        if str(a[1]) != 'HumanSoldier':
            continue
        ai = [c for c in kids.get(tid, []) if str(T[c][1]) == 'HumanAI']
        if not ai:
            continue
        try:
            g = int(T[ai[0]][5])
        except (TypeError, ValueError):
            continue
        men.append((tid, ai[0], g, tuple(float(c) for c in a[3:6]), squad_of.get(tid)))
    fails, warns, n_orders, unread = [], [], 0, []
    own = {}                                               # soldier -> (graph, island root, node)
    for h, aid, g, p, sq in men:
        if g not in GR:
            fails.append('man %d (ai %d): graph %d has no graph file' % (h, aid, g))
            continue
        n = nearest(GR[g], p)
        d = math.hypot(GR[g]['pos'][n][0] - p[0], GR[g]['pos'][n][1] - p[1]) / M
        own[h] = (g, GR[g]['comp'][n], n, d)

    def judge(who, g, root, target, kind):
        if target not in GR[g]['comp']:
            fails.append('%s: %s node %d is not in graph %d (missing node = no path = death)' % (who, kind, target, g))
        elif GR[g]['comp'][target] != root:
            fails.append('%s: %s node %d of graph %d is on another island (%d nodes) than the man (%d nodes)'
                         % (who, kind, target, g, GR[g]['sizes'][GR[g]['comp'][target]], GR[g]['sizes'][root]))

    def orders(text, who, g, root):
        cnt = 0
        if text.startswith('#UNREADABLE'):
            unread.append(who)
            return 0
        for fn, num in NODE_CALL.findall(text):
            if 'LookAt' in fn or 'Look' in fn:
                continue
            judge(who, g, root, int(num), fn)
            cnt += 1
        for fn, num in PATROL_CALL.findall(text):
            pid = int(num)
            if pid not in paths:
                continue
            pg, cmds = paths[pid]
            if pg != g:
                fails.append('%s: %s(%d) is a path on graph %d, the man is on graph %d' % (who, fn, pid, pg, g))
                continue
            for c, par in cmds:
                if c in MOVE_CMDS:
                    judge(who, g, root, par, 'PatrolPath %d cmd %d' % (pid, c))
                    cnt += 1
        return cnt
    by_squad = collections.defaultdict(list)
    for h, aid, g, p, sq in men:
        if h not in own:
            continue
        g_, root, n, d = own[h]
        n_orders += orders(script_text(bd, str(aid)), 'man %d (ai %d, graph %d)' % (h, aid, g), g, root)
        if sq is not None:
            by_squad[sq].append(h)
        # cover search window: other-island nodes within 20 m, |dz| < 2 m
        q = GR[g]['pos'][n]
        risk = [i for i, pp in GR[g]['pos'].items() if GR[g]['comp'][i] != root and math.hypot(pp[0] - p[0], pp[1] - p[1]) < 20.0 * M and abs(pp[2] - p[2]) < 2.0 * M]
        if risk:
            warns.append('man %d (graph %d, island of %d nodes): %d nodes of another island within the 20 m cover window, e.g. %s'
                         % (h, g, GR[g]['sizes'][root], len(risk), risk[:5]))
    for sq, hs in sorted(by_squad.items()):
        text = script_text(bd, 'Squad_%d' % sq)
        sw = T[sq][5] if len(T[sq]) > 5 else -1
        for h in hs:
            g, root, n, d = own[h]
            n_orders += orders(text, 'squad %d %r man %d' % (sq, str(T[sq][2])[:28], h), g, root)
            try:
                swid = int(sw)
            except (TypeError, ValueError):
                swid = -1
            if swid > 0 and swid in T:
                sp = tuple(float(c) for c in T[swid][3:6])
                judge('squad %d %r man %d' % (sq, str(T[sq][2])[:28], h), g, root, nearest(GR[g], sp), 'alarm switch %d' % swid)
                n_orders += 1
    if not quiet:
        for gid, g in sorted(GR.items()):
            isl = sorted(g['sizes'].items(), key=lambda kv: -kv[1])
            on = collections.Counter(own[h][1] for h, aid, gg, p, sq in men if h in own and gg == gid)
            print('graph %2d: %4d nodes, %d island(s): %s' % (gid, len(g['pos']), len(isl),
                                                         ', '.join('%d nodes / %d men' % (sz, on.get(r, 0)) for r, sz in isl[:8])))
        far = sorted(((own[h][3], h) for h in own if own[h][3] > 3.0), reverse=True)
        if far:
            print('men > 3 m from any node of their graph: %s' % ', '.join('%d (%.1f m)' % (h, d) for d, h in far[:12]))
        for w in warns:
            print('WARN ' + w)
    for f in fails:
        print('FAIL ' + f)
    if unread:
        print('NOTE scripts the decompiler could not read (not judged): %s' % unread[:10])
    print('islands: %d orders, %d FAIL, %d cover-risk men, %d graphs with more than one island %s'
          % (n_orders, len(fails), len(warns), sum(1 for g in GR.values() if len(g['sizes']) > 1),
             sorted(gid for gid, g in GR.items() if len(g['sizes']) > 1)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
