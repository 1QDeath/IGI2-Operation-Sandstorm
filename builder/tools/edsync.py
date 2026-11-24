"""edsync - carry edits made in the official IGI 2 editor (igi2ed) back into a Python-built mission.

Builders regenerate objects.qsc from scratch, so anything moved / added / deleted in igi2ed is lost on the next build.
edsync diffs the editor-saved objects.qsc against the builder's own build/<name>/objects.qsc and writes an EDITS file
(JSON) that Kit.write() re-applies on every later build (spkit hook: work/edits/<folder>.json, see work/igi2ed/HOWTO.md).

    python -P tools/edsync.py diff build/<name>/objects.qsc <editor saved objects.qsc> work/edits/<folder>.json [--merge] [--skip T1,T2] [--keep-noise]
    python -P tools/edsync.py show work/edits/<folder>.json
    python -P tools/edsync.py apply build/<name>/objects.qsc work/edits/<folder>.json <out objects.qsc>   (dry run / test)

Edit kinds (one entry each, applied in this order):
    remove  {anchor}                      - delete that task + its subtree
    set     {anchor, args: {idx: value}}  - change Task_New arguments by index (3,4,5 = position x,y,z for world
                                            objects; the next ones are the orientation; any other parameter too)
    add     {parent: anchor, qsc: text}   - a new subtree (as igi2ed saved it) under that parent
anchor = {id, type, note, args}: `args` are the builder's own values of that task when the edit was taken. A task is
found by id + type + note + equal args, else by type + note + equal args (builder renumbered), else by id + type + note
with a WARNING (the builder changed that object too; removes are then SKIPPED, never applied to a lookalike).
Tolerances: positions (args 3-5) 0.5 unit (1/8192 m), other numbers 1e-4, + 1e-6*|a|. TRUE/FALSE stay symbols.
--merge appends a ROUND ({"rounds": [...]}): rounds apply in order. Always diff against the CURRENT build.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igiqvm
from igiqvm import Call, Int, Flt, Str, Ident, Neg

TOL_ABS, TOL_REL = 8.0, 1e-6          # positions (args 3-5): 8 units = 2 mm; everything else (angles, scales): TOL_SMALL
TOL_SMALL = 1e-4
# igi2ed rewrites some values on save (seen 10-31, edscr): Euler angles re-derived from the matrix (gamma -pi/2 -> 4.712,
# (0.3, 0, -pi) -> (3.44, 0, 0)), AnimTasks saved at their ANIMATED pose (timer running), Forest counts, lens flare
# colours, RenderGroup 5 -> 12, extra trailing default params. diff() ignores these unless keep_noise.
ROT = {'EditRigidObj': 6, 'Building': 6, 'ExplodeObject': 6, 'GenericTBA': 6, 'Switch': 6, 'GenericPickup': 6,
       'Ladder': 6, 'Door': 9}                 # first index of (alpha, beta, gamma); engine matrix = Rz Ry Rx
NOISE = {('Forest', 17), ('Lensflare', 6), ('Lensflare', 7), ('Lensflare', 8), ('EditRigidObj', 10)}
ANIMATED = {'AnimTask': range(3, 9)}           # runtime pose, not an edit
RESERVED = set(range(900, 1000)) | set(range(0, 20))


# ------------------------------------------------------------------ values
def lit(x):
    if isinstance(x, Neg):
        v = lit(x.e)
        return -v if isinstance(v, (int, float)) else v
    if isinstance(x, Ident):
        return '@' + str(x)                  # TRUE / FALSE stay symbols (written back as idents)
    if isinstance(x, Flt):
        return float(x)
    if isinstance(x, Int):
        return int(x)
    return str(x)


def to_node(v):
    """JSON value -> igiqvm literal node"""
    if isinstance(v, bool):
        return Ident('TRUE' if v else 'FALSE')
    if isinstance(v, int):
        return Neg(Int(-v)) if v < 0 else Int(v)
    if isinstance(v, float):
        return Neg(Flt(-v)) if v < 0 else Flt(v)
    if isinstance(v, str) and v.startswith('@'):
        return Ident(v[1:])
    return Str(v)


BOOL = {'@TRUE': 1, '@FALSE': 0}


def same(a, b, idx=None):
    """idx = Task_New argument index: 3..5 (positions) get the half-unit tolerance, all other numbers TOL_SMALL"""
    if a in BOOL or b in BOOL:                   # TRUE/FALSE (also written as 1/0): exact
        return BOOL.get(a, a) == BOOL.get(b, b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        tol = TOL_ABS if idx in (3, 4, 5) else TOL_SMALL
        return abs(a - b) <= tol + TOL_REL * max(abs(a), abs(b))
    return a == b


def same_args(pa, pb):
    return len(pa) == len(pb) and all(same(x, y, i + 3) for i, (x, y) in enumerate(zip(pa, pb)))


def params(t):
    return [lit(x) for x in t.args[3:] if not isinstance(x, Call)]


def kids(t):
    return [x for x in t.args if isinstance(x, Call) and x.name == 'Task_New']


def tid(t):
    return lit(t.args[0])


def anchor(t):
    return {'id': tid(t), 'type': lit(t.args[1]), 'note': lit(t.args[2]), 'args': params(t)}


def roots(stmts):
    return [s for s in stmts if isinstance(s, Call) and s.name == 'Task_New']


def walk(ts, parent=None):
    for t in ts:
        yield t, parent
        yield from walk(kids(t), t)


def load(p):
    return igiqvm.parse_qsc(open(p, encoding='latin1').read())


# ------------------------------------------------------------------ diff
def _match(bk, ek):
    """pair builder children with editor children: id first, then equal type+note+args, then type+note in order"""
    pairs, eleft = [], list(ek)
    bleft = []
    byid = {}
    for e in eleft:
        if isinstance(tid(e), int) and tid(e) >= 0:
            byid.setdefault(tid(e), []).append(e)
    for b in bk:
        i = tid(b)
        cs = [e for e in byid.get(i, []) if lit(e.args[1]) == lit(b.args[1])] if isinstance(i, int) and i >= 0 else []
        if cs:                                         # (a pasted copy may keep the id: prefer the unchanged one)
            e = next((e for e in cs if same_args(params(b), params(e))), cs[0])
            pairs.append((b, e)); eleft.remove(e); byid[i].remove(e)
        else:
            bleft.append(b)
    for rule in ('args', 'order'):
        rest = []
        for b in bleft:
            hit = None
            for e in eleft:
                if lit(e.args[1]) != lit(b.args[1]) or lit(e.args[2]) != lit(b.args[2]):
                    continue
                if isinstance(tid(e), int) and tid(e) >= 0 and tid(e) != tid(b) and tid(b) not in (-1,):
                    continue                                   # a different explicit id = a different task
                if rule == 'order' or same_args(params(b), params(e)):
                    hit = e; break
            if hit is not None:
                pairs.append((b, hit)); eleft.remove(hit)
            else:
                rest.append(b)
        bleft = rest
    return pairs, bleft, eleft


def _rotm(a, b, g):
    import math
    ca, sa, cb, sb, cg, sg = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(g), math.sin(g)
    rx = [[1, 0, 0], [0, ca, -sa], [0, sa, ca]]; ry = [[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]]; rz = [[cg, -sg, 0], [sg, cg, 0], [0, 0, 1]]
    mul = lambda A, B: [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(mul(rz, ry), rx)


def _noise(typ, ch, pb, pe, stats):
    """drop editor rewrites from ch {str idx: new value}"""
    import math
    r = ROT.get(typ)
    if r is not None and any(str(k) in ch for k in (r, r + 1, r + 2)):
        try:
            ab, ae = [pb[k - 3] for k in (r, r + 1, r + 2)], [pe[k - 3] for k in (r, r + 1, r + 2)]
            if all(isinstance(x, (int, float)) for x in ab + ae):
                mb, me = _rotm(*ab), _rotm(*ae)
                if all(abs(mb[i][j] - me[i][j]) < 1e-4 for i in range(3) for j in range(3)):
                    for k in (r, r + 1, r + 2):
                        ch.pop(str(k), None)
                    stats['rotation'] = stats.get('rotation', 0) + 1
        except IndexError:
            pass
    for k in list(ch):
        i = int(k)
        vb = pb[i - 3] if i - 3 < len(pb) else None
        ve = ch[k]
        why = None
        if vb is None:
            why = 'added param'
        elif (typ, i) in NOISE:
            why = 'rewrite %s.%d' % (typ, i)
        elif typ in ANIMATED and i in ANIMATED[typ]:
            why = 'animated pose'
        elif i >= 6 and isinstance(vb, (int, float)) and isinstance(ve, (int, float)) and abs(vb) < 13 and abs(ve) < 13                 and abs(ve - vb) > 6 and abs(math.remainder(ve - vb, 2 * math.pi)) < 1e-4:
            why = 'angle +-2pi'
        if why:
            ch.pop(k); stats[why] = stats.get(why, 0) + 1


def diff(bstmts, estmts, skip=(), keep_noise=False):
    """skip: task types whose removal / addition is ignored (e.g. HumanPlayer if the editor drops it).
    keep_noise: keep the editor's own rewrites (see NOISE / ROT / ANIMATED) as edits"""
    edits = {'remove': [], 'set': [], 'add': []}
    stats = {}

    def rec(bk, ek, bparent):
        pairs, gone, new = _match(bk, ek)
        for b in gone:
            if lit(b.args[1]) in skip:
                print('edsync: skipped removal of %s %s %r' % (tid(b), lit(b.args[1]), lit(b.args[2])))
                continue
            edits['remove'].append({'anchor': anchor(b), 'subtree': sum(1 for _ in walk([b]))})
        for e in new:
            if lit(e.args[1]) in skip:
                continue
            if bparent is None:
                print('edsync: WARNING new top-level task %s %s ignored' % (tid(e), lit(e.args[1])))
                continue
            edits['add'].append({'parent': anchor(bparent), 'id': tid(e), 'type': lit(e.args[1]), 'note': lit(e.args[2]),
                                 'qsc': igiqvm.to_text(e)})
        for b, e in pairs:
            pb, pe = params(b), params(e)
            ch = {}
            for i in range(max(len(pb), len(pe))):
                vb = pb[i] if i < len(pb) else None
                ve = pe[i] if i < len(pe) else None
                if vb is None or ve is None or not same(vb, ve, i + 3):
                    ch[str(i + 3)] = ve
            if ch and not keep_noise:
                _noise(lit(b.args[1]), ch, pb, pe, stats)
            if ch:
                edits['set'].append({'anchor': anchor(b), 'args': ch})
            rec(kids(b), kids(e), b)

    rec(roots(bstmts), roots(estmts), None)
    if stats:
        print('edsync: ignored editor rewrites: %s (keep with --keep-noise)' % ', '.join('%s %d' % kv for kv in sorted(stats.items())))
    return edits


# ------------------------------------------------------------------ apply
def _find(stmts, a, where='', strict=False):
    """task + parent for anchor a; (None, None) if not found.
    1. the anchor id with equal type, note AND args; 2. type + note + equal args anywhere (unique);
    3. the anchor id with equal type + note but other args (the builder changed it) - never when strict (removes)."""
    allt = list(walk(roots(stmts)))
    has_id = isinstance(a['id'], int) and a['id'] >= 0
    byid = [(t, p) for t, p in allt if has_id and tid(t) == a['id'] and lit(t.args[1]) == a['type'] and lit(t.args[2]) == a['note']]
    for t, p in byid:
        if same_args(params(t), a['args']):
            return t, p
    cand = [(t, p) for t, p in allt if lit(t.args[1]) == a['type'] and lit(t.args[2]) == a['note'] and same_args(params(t), a['args'])]
    if len(cand) == 1:
        if has_id:
            print('edsync: %s task %s %r found as id %s (builder renumbered it)' % (where, a['id'], a['note'], tid(cand[0][0])))
        return cand[0]
    if len(cand) > 1:
        print('edsync: WARNING %s anchor %s %s %r is ambiguous (%d tasks with these values) - skipped' % (where, a['id'], a['type'], a['note'], len(cand)))
        return None, None
    if byid and not strict:
        print('edsync: WARNING %s task %s %r: values differ from the edit (builder changed it?) - applying to id %s anyway'
              % (where, a['id'], a['note'], a['id']))
        return byid[0]
    return None, None


def _set_arg(t, idx, v):
    """set the idx-th Task_New argument (counting the non-Call ones, idx >= 3)"""
    pos = [k for k, x in enumerate(t.args) if k < 3 or not isinstance(x, Call)]
    if idx < len(pos):
        t.args[pos[idx]] = to_node(v)
    else:
        print('edsync: WARNING arg %d of task %s does not exist in the build - ignored' % (idx, tid(t)))


def _free_ids(stmts):
    """free task ids: above the highest used one below 3000 first (never a just-removed id), then the gaps from 20"""
    used = {tid(t) for t, _ in walk(roots(stmts))}
    top = max([i for i in used if isinstance(i, int) and 20 <= i < 3000] + [19])     # (MP leftovers sit at 3000-4095)
    for i in list(range(top + 1, 4087)) + list(range(20, top)):
        if i not in used and i not in RESERVED:
            yield i
    raise RuntimeError('edsync: no free task id < 4087')


def apply(stmts, edits, where='edsync'):
    """apply an EDITS dict (or a path to one) to a statement list in place; returns the number of edits applied.
    A file is either one round {remove, set, add} or {"rounds": [round, ...]} (--merge appends a round; rounds apply in
    order, so a later round can target a task an earlier round added)."""
    if isinstance(edits, str):
        edits = json.load(open(edits))
    if 'rounds' in edits:
        return sum(apply(stmts, r, '%s round %d' % (where, k + 1)) for k, r in enumerate(edits['rounds']))
    n = 0
    parents = [_find(stmts, a['parent'], 'add')[0] for a in edits.get('add', [])]   # before removes/sets change values
    for r in edits.get('remove', []):
        t, p = _find(stmts, r['anchor'], 'remove', strict=True)
        if t is None:
            print('edsync: WARNING remove: task %s %r not found - skipped' % (r['anchor']['id'], r['anchor']['note']))
            continue
        (p.args if p is not None else stmts).remove(t); n += 1
    for s in edits.get('set', []):
        t, p = _find(stmts, s['anchor'], 'set')
        if t is None:
            print('edsync: WARNING set: task %s %r not found - skipped' % (s['anchor']['id'], s['anchor']['note']))
            continue
        for i, v in s['args'].items():
            if v is None:
                print('edsync: WARNING set: arg %s of task %s removed in the editor - ignored' % (i, tid(t)))
                continue
            _set_arg(t, int(i), v)
        n += 1
    free = None
    for a, p in zip(edits.get('add', []), parents):
        if p is None:
            print('edsync: WARNING add: parent %s %r not found - %s skipped' % (a['parent']['id'], a['parent']['note'], a['type']))
            continue
        new = igiqvm.parse_qsc(a['qsc'] + ';')[0]
        used = {tid(t) for t, _ in walk(roots(stmts))}
        for t, _ in walk([new]):
            i = tid(t)
            if isinstance(i, int) and i >= 0 and (i in used or i in RESERVED):
                free = free or _free_ids(stmts)
                j = next(free)
                while j in used:
                    j = next(free)
                print('edsync: add: id %s taken -> %s (scripts that name %s are NOT rewritten)' % (i, j, i))
                t.args[0] = Int(j)
                used.add(j)
            elif isinstance(i, int) and i >= 0:
                used.add(i)
        p.args.append(new); n += 1
    print('%s: applied %d editor edit(s)' % (where, n))
    return n


def summary(edits):
    out = []
    for r in edits.get('remove', []):
        a = r['anchor']; out.append('remove %5s %-14s %r (+%d tasks)' % (a['id'], a['type'], a['note'], r.get('subtree', 1) - 1))
    for s in edits.get('set', []):
        a = s['anchor']
        d = []
        for i, v in sorted(s['args'].items(), key=lambda kv: int(kv[0])):
            old = a['args'][int(i) - 3] if int(i) - 3 < len(a['args']) else None
            if isinstance(old, (int, float)) and isinstance(v, (int, float)) and int(i) in (3, 4, 5):
                d.append('%s:%+.2fm' % ('xyz'[int(i) - 3], (v - old) / 4096))
            else:
                d.append('%s:%r->%r' % (i, old, v))
        out.append('set    %5s %-14s %r %s' % (a['id'], a['type'], a['note'], ' '.join(d)))
    for a in edits.get('add', []):
        out.append('add    %5s %-14s %r under %s %r' % (a['id'], a['type'], a['note'], a['parent']['id'], a['parent']['note']))
    return out


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ('diff', 'show', 'apply'):
        sys.exit(__doc__)
    if a[0] == 'diff':
        skip = a[a.index('--skip') + 1].split(',') if '--skip' in a else ()
        e = diff(load(a[1]), load(a[2]), skip, '--keep-noise' in a)
        out = e
        if '--merge' in a and os.path.exists(a[3]):         # a new round after the old ones (diff against the CURRENT build)
            old = json.load(open(a[3]))
            out = {'rounds': (old['rounds'] if 'rounds' in old else [old]) + [e]}
        os.makedirs(os.path.dirname(os.path.abspath(a[3])), exist_ok=True)
        json.dump(out, open(a[3], 'w'), indent=1)
        print('\n'.join(summary(e)) or '(no differences)')
        print('edsync: %d remove, %d set, %d add -> %s' % (len(e['remove']), len(e['set']), len(e['add']), a[3]))
    elif a[0] == 'show':
        print('\n'.join(summary(json.load(open(a[1])))) or '(empty)')
    else:
        st = load(a[1])
        apply(st, a[2])
        open(a[3], 'w', encoding='latin1', newline='\n').write(igiqvm.stmts_to_qsc(st))


if __name__ == '__main__':
    main()
