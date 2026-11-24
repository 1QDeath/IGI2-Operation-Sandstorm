"""spkit - single-player missions on multiplayer maps (the Operation Sandstorm recipe as a library).

Everything here was proven in-game on Sandstorm (10-10): MP logic stripped, generated AI graphs (navgen), squads,
voiced status messages (Windows TTS through a radio filter), objective list + map markers, intro / outro
cutscenes with the player and the enemies gated off while they run, LevelFlow moved behind the HumanPlayer,
timers counted from the end of the intro, level + own-common sound banks with the right PATH entries.

    K = Kit('timberland', mission_id=20, folder='atlas_sp', prefix='AT', seed=2020, debug_env='AT_DEBUG')
    K.strip_mp(); K.player(start, gamma, loadout); K.graphs(...); K.squad(...); K.msg(...); ...; K.finish(...)
"""
import hashlib, math, os, re, shutil, sys, wave
import numpy as np
import igiqvm
from igiqvm import Call, Int, Str
from mission_lib import Mission, T, v, GAME
from qast import lit, tasks
import navgen
import cutscene as CS
import terrain as terrain_mod
import voice
import soundbank as sb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L1 = os.path.join(ROOT, 'work', 'decomp', 'location1_level1_objects.qsc')
VO_CACHE = os.path.join(ROOT, 'work', 'voice_cache')
MP_ONLY_TYPES = ('Terminal', 'C4BombArea', 'SpawnPoint', 'SpawnArea', 'Network_Mission', 'Network_Objective',
                 'AIStationaryGunHolder')
MP_REF = re.compile(r'\bNet[A-Z]\w*_|HUMAN_TEAM_|\bmp/|NetMission|NetObjective|\bNetwork_')
GAME_FREQ = 'GAME_FREQUENCY'

# soldier types / weapons shorthands
C1N, C1T = 'HUMANAI_TYPE_C1_NORMAL_SOLDIER', 'HUMANAI_TYPE_C1_TOUGH_SOLDIER'
C2N, C2T = 'HUMANAI_TYPE_C2_NORMAL_SOLDIER', 'HUMANAI_TYPE_C2_TOUGH_SOLDIER'
C3N, C3T = 'HUMANAI_TYPE_C3_NORMAL_SOLDIER', 'HUMANAI_TYPE_C3_TOUGH_SOLDIER'
AK, AKG, MG, SG, SMG, SN, RPG = ['AK47'], ['AK47', 'GRENADE'], ['MINIMI'], ['SPAS12'], ['UZI'], ['DRAGUNOV'], ['RPG7']


def spoken(text, extra=()):
    """what the TTS voice says for a caption: drop the speaker tag, spell out abbreviations"""
    t = text.split(':', 1)[1].strip() if re.match(r'^[A-Z][A-Z .]{1,20}:', text) else text
    for a, b in (('1 of 2', 'one of two'), ('2 of 2', 'two of two'), ('1 of 3', 'one of three'), ('2 of 3', 'two of three'),
                 ('3 of 3', 'three of three'), ('1 of 4', 'one of four'), ('2 of 4', 'two of four'), ('3 of 4', 'three of four'),
                 ('4 of 4', 'four of four'), ('RPG', 'R P G'), ('EMP', 'E M P'), ('CCTV', 'C C T V'), ('SAM', 'Sam'),
                 ("Xing's", "Shing's"), ('IRGC', 'I R G C'), ('USS', 'U S S'), ('GRU', 'G R U')) + tuple(extra):
        t = t.replace(a, b)
    return t


class Kit:
    def __init__(self, mp_map, mission_id, folder, prefix, seed, debug_env, title):
        self.m = Mission('multiplayer', mp_map, mp_map, seed=seed)
        # 10-16 (proto M7): a folder name > 13 chars crashes the level load (D3D8.dll+0xeefd / 'Mem_Alloc() failed to
        # allocate 16777248 bytes') - 'harborproto_sp' crashed even a bare map, 'harbor_sp' / 'eagleproto_sp' load
        assert len(folder) <= 13, 'mission folder %r is %d chars: the engine needs <= 13' % (folder, len(folder))
        self.mp_map, self.ID, self.FOLDER, self.PFX, self.title = mp_map, mission_id, folder, prefix.upper(), title
        self.vp = prefix.lower() + '_'                       # voice def prefix (def names <= 15 chars)
        self.DEBUG = os.environ.get(debug_env, '')
        self.DBG = set(p.split('=')[0] for p in self.DEBUG.split(';') if p)
        self.VO, self.M, self.GRAPHS, self.SQUADS, self.GEDGES = {}, {}, {}, {}, {}
        self.PATROLS = 0
        self.ENEMIES = 0
        self.TAKEN = []
        self.TERMINALS = {}
        self.removed = []
        self.root = [lit(s.args[0]) for s in self.m.stmts if isinstance(s, Call) and s.name == 'Task_New']
        self.TERR = terrain_mod.Terrain(self.m.src, self.m.stmts)

    @property
    def L(self):
        return self.m.byid                                  # (re-made by every reindex: never cache it)

    def nid(self):
        return self.m.new_id(20, 4095)                       # 1..19 stay free for AI graph ids

    # ------------------------------------------------------------------ 0. strip the multiplayer game logic
    def strip_mp(self, keep=(), extra_remove=()):
        m = self.m
        for i in m.find('Terminal'):
            self.TERMINALS[i] = [lit(a) for a in self.L[i].args[3:9]]
        doomed = set(extra_remove)
        for i, t in list(m.byid.items()):
            if i in keep:
                continue
            ty = lit(t.args[1])
            if ty in MP_ONLY_TYPES or ty == 'DefineComputerObjective':
                doomed.add(i)
        for i in sorted(doomed):
            if i in m.byid:
                self.removed.append((i, lit(m.byid[i].args[1]), lit(m.byid[i].args[2])))
                m.remove(i)
        # anything else that still talks to the multiplayer game: doors get neutral lock/open rules, the rest goes
        for _round in range(3):
            for i, t in list(m.byid.items()):
                if i in keep or i not in m.byid:
                    continue
                strs = [(k, a) for k, a in enumerate(t.args) if isinstance(a, Str) and MP_REF.search(str(a))]
                if not strs:
                    continue
                ty = lit(t.args[1])
                if ty in ('Door', 'LevelFlow'):
                    for k, a in strs:
                        m.set(i, k, '')
                elif ty in ('Container', 'ConditionalContainer') and any(isinstance(a, Call) for a in t.args):
                    for k, a in strs:                       # keep the children, drop the MP condition
                        m.set(i, k, '1' if k == 3 else '')
                else:
                    self.removed.append((i, ty, lit(t.args[2])))
                    m.remove(i)
        # anything that still reads a task we removed: that term becomes 0 (FALSE) - the task itself stays
        # (removing it cascaded on Timberland: terminal -> 'alarm off' variable -> 'alarm on' -> cameras -> sirens)
        REF = re.compile(r'\b([A-Z][A-Za-z0-9]+(?:_[A-Z][A-Za-z0-9]+)*)_(\d+)\.[A-Za-z]\w*')   # (types like Network_Objective)
        self.dangling = []
        for i, t in list(m.byid.items()):
            for k, a in enumerate(t.args):
                if isinstance(a, Str) and REF.search(str(a)):
                    new_ = REF.sub(lambda mm: mm.group(0) if int(mm.group(2)) in m.byid else '0', str(a))
                    if new_ != str(a):
                        # a door rule that read a removed task becomes a NORMAL door (''): substituting 0 turned Forest Raid's
                        # 'LevelTimer_1103.nTick < 15 s' (locked for 15 s per MP round) into 'locked forever' (reviewer 10-10)
                        m.set(i, k, '' if lit(t.args[1]) == 'Door' else new_)
                        self.dangling.append((i, k))
        m.import_decls(L1)
        return self.removed

    # ------------------------------------------------------------------ 1. player, logic, failure
    def player(self, start, gamma, loadout, skin='jones2_1', arms='arms2_1', parent=None, carry=False):
        # carry (sf-flow 11-15, R2): HumanPlayer arg 14 'Carry over weapons from previous mission'. With TRUE the exe loads
        #  savegames/missions/co<profile><difficulty><mission>.qsc (written when the previous campaign mission is completed) AFTER the
        #  level's Weapon script and replaces that kit; no file = `loadout` is the kit. Originals: 9 of 19 levels TRUE (X3_CARRY_OVER.md).
        self.START, self.GAMMA = tuple(float(c) for c in start), float(gamma)
        self.PARENT = parent or self._dynamic_root()
        if loadout and not any('WEAPON_ID_THERMICAL' in x for x in loadout) and os.environ.get('SPKIT_THERMAL', '1') != '0':   # (empty kit = on purpose: Burned)
            loadout = list(loadout) + ['Human_AddWeapon("WEAPON_ID_THERMICAL")']   # (11-02 default: without the goggles T fires a round)
        p = T(0, 'HumanPlayer', '', self.START[0], self.START[1], self.START[2], self.GAMMA, skin, 0,
              ',\n'.join(loadout) + ';', arms, 0.8, 0.2, 0.95, bool(carry), children=[T(self.nid(), 'HumanPlayerInput', '', '', '')])
        self.PC = self.nid()
        self.m.add_child(self.PARENT, T(self.PC, 'Container', 'ThePlayer', False, children=[p]))
        self.LOGIC = self.nid()
        self.m.add_child(self.PARENT, T(self.LOGIC, 'Container', '%s mission logic' % self.PFX, False))
        self.DEAD = self.nid()
        self.m.add_child(self.LOGIC, T(self.DEAD, 'StatusMessage', 'Mission Failed Player dead', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                       'HumanPlayer_0.isDead', 'MISSION_FAILED', '', 'statusmessage', True, False, 2.0, ''))
        self.SQ_PARENT = self.nid()
        self.m.add_child(self.PARENT, T(self.SQ_PARENT, 'Container', '%s enemies' % self.PFX, False))
        self.PICK = self.nid()
        self.m.add_child(self.PARENT, T(self.PICK, 'Container', '%s pickups' % self.PFX, False))
        self.TAKEN.append(self.START)

    def _dynamic_root(self):
        for i in self.root:
            if lit(self.L[i].args[1]) == 'Dynamic':
                return i
        raise AssertionError('no Dynamic root container: %s' % [(i, lit(self.L[i].args[2])) for i in self.root])

    def static_root(self):
        for i in self.root:
            if lit(self.L[i].args[1]) == 'Static':
                return i
        raise AssertionError('no Static root container')

    # ------------------------------------------------------------------ 2. AI graphs
    def navigate(self, bounds, closed_doors=(), fine_tile=9, coarse_tile=22, extra_res=(), terrain=None, **nav_args):
        G_ = GAME.replace('\\', '/') + '/'
        res = [G_ + 'MISSIONS/multiplayer/%s/models/%s.res' % (self.mp_map, self.mp_map),
               G_ + 'MISSIONS/multiplayer/common/models/multiplayer.res', G_ + 'COMMON/models/common.res'] + list(extra_res)
        self.MODEL_RES = res
        self.nv = navgen.generate(self.m, bounds, res, cache_dir=os.path.join(ROOT, 'work', 'navcache'),
                                  fine_tile=fine_tile, coarse_tile=coarse_tile, closed_doors=tuple(sorted(closed_doors)),
                                  terrain=terrain, **nav_args)
        if terrain is not None:
            self.TERR = terrain
        nv = self.nv
        self.NF = nv.F
        self.NODE_P = np.array([[self.NF['x'][q['s']], self.NF['y'][q['s']], self.NF['z'][q['s']]] for q in nv.nodes])
        self.ADJ = {}
        for a_, b_ in nv.edges:
            self.ADJ.setdefault(a_, set()).add(b_); self.ADJ.setdefault(b_, set()).add(a_)
        return nv

    def region(self, probe, box):
        """the connected node set inside box that contains the node nearest to probe (probe None = the largest one)"""
        P = self.NODE_P
        inside = (P[:, 0] >= box[0]) & (P[:, 0] <= box[2]) & (P[:, 1] >= box[1]) & (P[:, 1] <= box[3])
        if probe is None:
            best, seen = [], set()
            for s0 in np.nonzero(inside)[0]:
                s0 = int(s0)
                if s0 in seen:
                    continue
                comp, todo = {s0}, [s0]
                while todo:
                    u = todo.pop()
                    for w in self.ADJ.get(u, ()):
                        if inside[w] and w not in comp:
                            comp.add(w); todo.append(w)
                seen |= comp
                if len(comp) > len(best):
                    best = sorted(comp)
            return best
        d = np.hypot(P[:, 0] - probe[0], P[:, 1] - probe[1]) + 3 * np.abs(P[:, 2] - probe[2])
        d[~inside] = 1e18
        seed = int(np.argmin(d))
        comp, todo = {seed}, [seed]
        while todo:
            u = todo.pop()
            for w in self.ADJ.get(u, ()):
                if inside[w] and w not in comp:
                    comp.add(w); todo.append(w)
        return sorted(comp)

    def trim(self, comp, anchors, walk_m):
        """keep the nodes of comp within walk_m metres of WALKING from any anchor disc (x, y, r in units), plus the
        shortest paths that join the kept pieces (a graph must stay ONE component). Ground-following graphs on rugged
        terrain have too many nodes for the A* arrays (2000) - the AI only needs the ground around its squads."""
        import scipy.sparse as sp_, scipy.sparse.csgraph as csg_
        P = self.NODE_P
        cidx = {u: k for k, u in enumerate(comp)}
        rr, cc, ww = [], [], []
        for u in comp:
            for w in self.ADJ.get(u, ()):
                if w in cidx:
                    rr.append(cidx[u]); cc.append(cidx[w]); ww.append(float(np.linalg.norm(P[u] - P[w])) + 1.0)
        A = sp_.coo_matrix((ww, (rr, cc)), shape=(len(comp), len(comp))).tocsr()
        cp = P[comp]
        seeds = set()
        for ax_, ay_, ar_ in anchors:
            dd_ = np.hypot(cp[:, 0] - ax_, cp[:, 1] - ay_)
            inn = np.nonzero(dd_ <= ar_)[0].tolist()
            seeds |= set(inn) if inn else {int(np.argmin(dd_))}
        seeds = sorted(seeds)
        dist = csg_.dijkstra(A, directed=False, indices=seeds, min_only=True)
        keep = set(np.nonzero(dist <= walk_m * CS.M)[0].tolist())
        # join every kept piece to the first one along shortest paths through the full region
        while True:
            ks = sorted(keep)
            kidx = {u: k for k, u in enumerate(ks)}
            sub = A[ks][:, ks]
            n_, lab = csg_.connected_components(sub, directed=False)
            if n_ <= 1:
                break
            main_lab = lab[kidx[seeds[0]]]
            main = set(ks[k] for k in np.nonzero(lab == main_lab)[0])
            d_, pred, _src = csg_.dijkstra(A, directed=False, indices=sorted(main), min_only=True, return_predecessors=True)
            other = [u for u in ks if lab[kidx[u]] != main_lab]
            u = min(other, key=lambda q: d_[q])
            assert np.isfinite(d_[u]), 'trim: a kept piece is not connected to the rest'
            while u >= 0 and u not in main:
                keep.add(u); u = pred[u]
        return sorted(comp[k] for k in keep)

    def link_report(self, gid, gnodes, edges):
        """owner 10-11 regression guard: how far the straight node-to-node lines (where a walking soldier's feet are)
        leave the real ground, terrain links only. -> (p50, p90, max) in cm"""
        if getattr(self, 'TERR', None) is None:
            return None
        GP = {n_['id']: np.array(n_['pos']) for n_ in gnodes}
        GT = {n_['id']: n_['terrain'] for n_ in gnodes}
        devs = []
        for a_, b_ in edges:
            if not (GT[a_] and GT[b_]):
                continue
            pa, pb = GP[a_], GP[b_]
            k_ = max(2, int(np.linalg.norm(pb[:2] - pa[:2]) / 256) + 1)
            t_ = np.linspace(0, 1, k_)
            X = pa[0] + t_ * (pb[0] - pa[0]); Y = pa[1] + t_ * (pb[1] - pa[1]); Z = pa[2] + t_ * (pb[2] - pa[2])
            devs.append(float(np.abs(Z - self.TERR.height(X, Y)).max()) / CS.M * 100)
        if not devs:
            return None
        return float(np.percentile(devs, 50)), float(np.percentile(devs, 90)), max(devs)

    def graphs(self, regions):
        """regions: [(graph id, name, probe (x, y, z), box (x0, y0, x1, y1)[, dict(anchors=[(x, y, r) units], walk_m=)])]"""
        m = self.m
        gbox = self.nid()
        m.add_child(self.static_root(), T(gbox, 'Container', 'Static AI', False))
        gcont = self.nid()
        m.add_child(gbox, T(gcont, 'Container', 'Graphs', False))
        comps = {}
        for r_ in regions:
            gid, name, probe, box = r_[:4]
            comps[gid] = self.region(probe, box)
            if len(r_) > 4 and r_[4]:
                n0 = len(comps[gid])
                comps[gid] = self.trim(comps[gid], r_[4]['anchors'], r_[4].get('walk_m', 25.0))
                print('graph %d: trimmed to the squads\' ground: %d -> %d nodes' % (gid, n0, len(comps[gid])))
        big = [(gid, len(c)) for gid, c in comps.items() if len(c) >= 1990]
        assert not big, 'regions too big for the A* arrays (< 2000 nodes): %s' % big
        for r_ in regions:
            gid, name, probe, box = r_[:4]
            assert gid not in self.m.byid, 'graph id %d is already a task id (10 = LevelFlow)' % gid
            comp = comps[gid]
            data, gnodes, ne, mx = self.nv.export(comp)
            m.graphs[gid] = (data, None)
            self.GRAPHS[gid] = gnodes
            self.GEDGES[gid] = list(self.nv.last_edges)
            m.add_child(gcont, T(gid, 'AIGraph', name, 0.0, 0.0, 0.0, True, False, len(gnodes), mx, ne,
                                 0.7, 2.0, 3.0, 0.3, 1.5, 15.0, False, 0.05, False))
            print('graph %d %-30s nodes %4d edges %5d doors %d | %s' % (gid, name, len(gnodes), ne,
                                                                      sum(1 for n in gnodes if n['crit']), self.nv.merge_log))
            dev = self.link_report(gid, gnodes, self.nv.last_edges)
            if dev:
                print('graph %d terrain links vs ground: p50 %.1f p90 %.1f max %.1f cm' % ((gid,) + dev))
                if self.nv.max_dev is not None:          # ground-following graphs must really follow the ground
                    assert dev[2] <= self.nv.max_dev / CS.M * 100 + 6.0, 'graph %d: a link leaves the ground by %.0f cm' % (gid, dev[2])
            assert 20 <= len(gnodes) < 2000, 'graph %d: %d nodes (A* arrays hold 2000; tiny graphs mean a bad probe)' % (gid, len(gnodes))

    # ------------------------------------------------------------------ 3. enemies + pickups
    def pick(self, g, n, center, radius, zlo=-1e9, zhi=1e9, where='any', spacing=7000.0):
        for r_mul, s_mul in ((1.0, 1.0), (1.4, 1.0), (1.4, 0.7), (2.0, 0.7)):
            cand = [q for q in self.GRAPHS[g] if not q['crit'] and zlo <= q['pos'][2] <= zhi
                    and math.hypot(q['pos'][0] - center[0], q['pos'][1] - center[1]) <= radius * r_mul
                    and (where == 'any' or (where == 'in') == (q['terrain'] == 0))]
            cand.sort(key=lambda q: q['pos'])
            for attempt in range(12):                       # greedy spacing can fail on one shuffle and work on another
                self.m.rng.shuffle(cand)
                got = []
                for q in cand:
                    p = q['pos']
                    if all(math.dist(p, o) >= spacing * s_mul for o in got + self.TAKEN):
                        got.append(p)
                        if len(got) == n:
                            self.TAKEN.extend(got)
                            return got
        raise AssertionError('squad at %s: wanted %d nodes, found %d of %d candidates' % (center, n, len(got), len(cand)))

    def squad(self, key, g, center, radius, loadouts, ai_type, skins, zlo=-1e9, zhi=1e9, where='any',
              sqtype='AIType_Offensive', alarm=True, ai='generic', spacing=7000.0, parent=None, patrol=None, route_m=(9.0, 30.0),
              profile=False, pairs=False, approach=None):
        """soldiers on graph g near center. Owner round 3 (10-10): nobody just stands there - `patrol` (default 0.65) of
        them walk a PatrolPath (walk, wait, look, walk on, back, again; each in his own one-man squad like the originals'
        patrol guards) and the rest stand their post but keep scanning (AIAction_LookAround); all get the view cones and
        accuracy of the sharpest original guards (aiscript.HARD). Snipers (DRAGUNOV) keep the 'hold' script."""
        import aiscript
        pts = self.pick(g, len(loadouts), center, radius, zlo, zhi, where, spacing)
        if patrol is None:
            patrol = 0.65
        if profile is False:                                # (False = the mission's default: Kit.PROFILE, else the sharpest)
            profile = getattr(self, 'PROFILE', aiscript.HARD)
        alarm_c = self.ALARM if (alarm and getattr(self, 'ALARM', None)) else -1
        stay, walkers = [], []
        mate = None                                        # (11-01 additive, Sandstorm owner fix: pairs=True - the next man walks
        for k, (p, w) in enumerate(zip(pts, loadouts)):    #  the same PatrolPath as his mate; approach=(x, y) - sentries face it)
            mem = dict(pos=p, model=skins[k % len(skins)], weapons=w, ai_type=ai_type, graph=g)
            if 'DRAGUNOV' in w or ai == 'hold':
                mem['ai'] = 'hold'
                stay.append(mem); continue
            if pairs and mate:
                path, mate = mate, None
            else:
                path = self.patrol_route(g, p, route_m) if self.m.rng.random() < patrol else None
                mate = path if pairs else None
            if path:
                mem['ai'] = aiscript.patrol(path, profile)
                walkers.append(mem)
            else:
                mem['ai'] = aiscript.sentry(profile)
                if approach is not None:
                    mem['gamma'] = round(math.atan2(-(approach[0] - p[0]), approach[1] - p[1]) + self.m.rng.uniform(-0.5, 0.5), 6)
                stay.append(mem)
        # one squad per call, walkers and sentries together (the originals mix them: 'PWW', 'PPWg', 'PPPPP'); one-man
        # squads per walker doubled the squad count past every original level (reviewer 10-10: 65 vs 35 max)
        sid, hids = self.m.squad(parent or self.SQ_PARENT, key, sqtype, stay + walkers, alarm_switch=-1, alarm_control=alarm_c)
        self.SQUADS[key] = (sid, hids)
        self.ENEMIES += len(hids)
        self.PATROLS += len(walkers)
        # (the first id stays the first loadout's soldier: bosses are looked up as squad(...)[0])
        first = [m_ for m_ in stay + walkers if m_['pos'] == pts[0]]
        if first and first[0]['id'] in hids:
            hids.remove(first[0]['id']); hids.insert(0, first[0]['id'])
        return hids

    def talk_pair(self, key, g, center, radius, loadouts, ai_type, skins, zlo=-1e9, zhi=1e9, alarm=True, alarm_var=None, parent=None):
        """(11-01 additive, port of build_sandstorm.talk_pair) two off-duty men indoors on two LINKED graph nodes 1.2-3.6 m apart,
        facing each other, 'stand_talk1/2' as their stand action; in the alarm (EditVariable alarm_var == 1) their squad's hunt leads"""
        import alarmai
        from igiqvm import Call, Str
        alarm_var = alarm_var or getattr(self, 'ALARM_VAR', 1500)
        byid = {q['id']: q for q in self.GRAPHS[g]}
        nb = {}
        for a_, b_ in self.GEDGES[g]:
            nb.setdefault(a_, []).append(b_); nb.setdefault(b_, []).append(a_)
        free = lambda p_: all(math.dist(p_, o) >= 4000.0 for o in self.TAKEN)
        cand = sorted((q for q in self.GRAPHS[g] if not q['crit'] and q['terrain'] == 0 and zlo <= q['pos'][2] <= zhi
                       and math.hypot(q['pos'][0] - center[0], q['pos'][1] - center[1]) <= radius and free(q['pos'])),
                      key=lambda q: q['pos'])
        self.m.rng.shuffle(cand)
        pair = None
        for q in cand:
            for j in nb.get(q['id'], ()):
                r_ = byid[j]
                d_ = math.hypot(r_['pos'][0] - q['pos'][0], r_['pos'][1] - q['pos'][1])
                if (not r_['crit'] and r_['terrain'] == 0 and 1.2 * 4096 <= d_ <= 3.6 * 4096 and abs(r_['pos'][2] - q['pos'][2]) < 0.4 * 4096
                        and free(r_['pos'])):
                    pair = (q, r_); break
            if pair:
                break
        assert pair, 'talk pair %s: no two linked indoor nodes 1.2-3.6 m apart' % key
        q, r_ = pair
        ev = alarmai.C('AIFunction_GetCurrentEventType')
        mem = []
        for k, (me, mt, w) in enumerate(((q, r_, loadouts[0]), (r_, q, loadouts[1]))):
            clip = 'stand_talk1' if k == 0 else 'stand_talk2'
            calm = [Call('AIFunction_SetStandActionAnimation', [Str(clip)]), alarmai.C('AIAction_WalkToNode', me['id'], 1),
                    alarmai.C('AIAction_LookAtNode', mt['id'], 1), alarmai.C('AIAction_PlayAnimation', 1, 0)]
            # (11-02: AIAction_PlayAnimation(1,0) instead of Idle - with Idle the stand-action clip only freezes the pose; L21/L24 recipe)
            busy = [alarmai.C('AIAction_Idle', 'AIACTIONFLAG_NONE')]
            sc = alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), [alarmai.C('AIFunction_DefaultHandler')],
                                                [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                            [alarmai.If(alarmai.EQ('EditVariable_%d.nValue' % alarm_var, 1), busy, calm),
                                                             alarmai.C('AIFunction_PassEventOnToSquad')],
                                                            [alarmai.C('AIFunction_DefaultHandler')])])])
            gam = math.atan2(-(mt['pos'][0] - me['pos'][0]), mt['pos'][1] - me['pos'][1])
            mem.append(dict(pos=me['pos'], model=skins[k % len(skins)], weapons=w, ai_type=ai_type, graph=g, ai=sc, gamma=round(gam, 6)))
            self.TAKEN.append(me['pos'])
        alarm_c = self.ALARM if (alarm and getattr(self, 'ALARM', None)) else -1
        sid, hids = self.m.squad(parent or self.SQ_PARENT, key, 'AIType_Offensive', mem, alarm_switch=-1, alarm_control=alarm_c)
        self.SQUADS[key] = (sid, hids)
        self.ENEMIES += len(hids)
        print('talk pair %s at %s / %s' % (key, [round(c / 4096, 1) for c in q['pos']], [round(c / 4096, 1) for c in r_['pos']]))
        return hids

    def patrol_route(self, g, start, route_m=(9.0, 30.0)):
        """a PatrolPath for a soldier standing on graph g at `start`: start -> A -> B -> start with a pause and a look at
        every stop. Waypoints are 9-30 m away along the graph links (never through a door node: doors may be locked;
        short routes keep the game's 1280-node path pool far from full). -> PatrolPath id or None"""
        import atmos
        nodes = self.GRAPHS[g]
        byid = {n['id']: n for n in nodes}
        s0 = min(nodes, key=lambda n: math.dist(n['pos'], start))
        if math.dist(s0['pos'], start) > 50.0:
            return None
        adj = {}
        for a, b in self.GEDGES[g]:
            adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
        import heapq
        dist = {s0['id']: 0.0}
        q = [(0.0, s0['id'])]
        while q:
            d, u = heapq.heappop(q)
            if d > dist.get(u, 1e18) or d > route_m[1] * 1.6 * CS.M:
                continue
            for w in adj.get(u, ()):
                if byid[w]['crit']:
                    continue
                nd = d + math.dist(byid[u]['pos'], byid[w]['pos'])
                if nd < dist.get(w, 1e18):
                    dist[w] = nd; heapq.heappush(q, (nd, w))
        lo, hi = route_m[0] * CS.M, route_m[1] * CS.M
        st_ = getattr(self, 'START', None)                  # never walk up to where Jones lands (reviewer: 11 m)
        far_start = lambda q: st_ is None or math.hypot(q[0] - st_[0], q[1] - st_[1]) > 40 * CS.M
        cand = sorted(i for i, d in dist.items() if lo <= d <= hi and abs(byid[i]['pos'][2] - s0['pos'][2]) < 2.5 * CS.M
                      and far_start(byid[i]['pos']))
        if len(cand) < 2:
            return None
        rng = self.m.rng
        a = rng.choice(cand)
        far = [i for i in cand if math.dist(byid[i]['pos'], byid[a]['pos']) >= 0.7 * lo]
        if not far:
            return None
        b = rng.choice(far)
        everyone = sorted(dist)

        def look_from(i):                                   # something to look at: a node 8-25 m away, any direction
            opts = [j for j in everyone if 8 * CS.M <= math.dist(byid[j]['pos'], byid[i]['pos']) <= 25 * CS.M]
            return rng.choice(opts) if opts else s0['id']
        for typ in ('PatrolPath', 'PatrolPathCommand'):
            atmos.ensure_decl(self.m, typ)
        if not hasattr(self, 'PATHS_C'):
            self.PATHS_C = self.nid()
            self.m.add_child(self.static_root(), T(self.PATHS_C, 'Container', 'Patrol Paths', False))
        cmds, here = [], s0['id']

        def c(cmd, par, text):
            cmds.append(T(self.nid(), 'PatrolPathCommand', text, cmd, par, here, '', ''))
        for stop in (a, b, s0['id']):
            c(2, stop, 'Walks to node id %d' % stop)
            here = stop
            ticks = int(rng.uniform(90, 320))
            c(1, ticks, 'Delays the script execution for %d ticks' % ticks)
            lk = look_from(stop)
            c(5, lk, 'Looks at node id %d' % lk)
            if rng.random() < 0.5:
                ticks = int(rng.uniform(60, 200))
                c(1, ticks, 'Delays the script execution for %d ticks' % ticks)
        c(7, -1, 'Quit script, stops script. Takes no parameters')
        pid = self.nid()
        self.m.add_child(self.PATHS_C, T(pid, 'PatrolPath', '%s route g%d n%d' % (self.PFX, g, s0['id']), g, children=cmds))
        return pid

    def pickup(self, name, g, center, zr, weapon, radius=45000.0):
        p = self.pick(g, 1, center, radius, zr[0], zr[1], spacing=5000.0)[0]
        self.m.add_child(self.PICK, T(self.nid(), 'GunPickup', '%s %s' % (self.PFX, name), float(p[0]), float(p[1]),
                                      float(p[2]) + 300.0, 1.570796, 0.0, 0.0, weapon, ''))
        return p

    # ------------------------------------------------------------------ 4. alarm
    def alarm(self, pos, var_id=None, seconds=60):
        """AlarmControl (siren + 'alarm' state for the squads). var_id = an existing alarm EditVariable of the map, or
        a new one is made: the alarm switches on when any camera / squad raises it and goes off again after `seconds`."""
        m = self.m
        if var_id is None:
            var_id = self.nid()
            m.add_child(self.LOGIC, T(var_id, 'EditVariable', '%s alarm on' % self.PFX, 0.0, 0.0, 0.0, 0, '', ''))
        self.ALARM_VAR = var_id
        self.ALARM = self.nid()
        m.add_child(self.LOGIC, T(self.ALARM, 'AlarmControl', '%s base alarm' % self.PFX, float(pos[0]), float(pos[1]), float(pos[2]),
                                  0.0, 0.0, 0.0, '', '', 1.0, 0.5, 0.5, 1.0, 0.0, 5, 4, '', 'explo_02_m', '1', 4.0, 'tba_hackcomp',
                                  'EditVariable_%d.nValue == 1' % var_id, 'EditVariable_%d.nValue == 1' % var_id))
        return self.ALARM

    def siren(self, pos, var_id, parent=None, sound='alarm_60'):
        """alarm speaker (Timberland 3328 pattern): plays `sound` while EditVariable var_id == 1. alarm_60 is a COMMON
        def that plays the level sample ALARM_2 (every MP bank has alarm_2.wav)"""
        a, b = self.nid(), self.nid()
        sg = self.nid()
        seq_on = T(a, 'SequenceCommand', '', 'EditVariable_%d.nValue == 1' % var_id, 'SoundGenerator_PlaySound("%s")' % sound,
                   'EditVariable_%d.nValue == 1' % var_id, 'SequenceCommand_SetCommand(%d)' % b)
        seq_off = T(b, 'SequenceCommand', '', 'EditVariable_%d.nValue == 0' % var_id, 'SoundGenerator_StopSound()',
                    'EditVariable_%d.nValue == 0' % var_id, 'SequenceCommand_SetCommand(%d)' % a)
        self.m.add_child(parent or self.LOGIC, T(self.nid(), 'EditRigidObj', '%s alarm siren' % self.PFX, *[float(c) for c in pos],
                                                 0.0, 0.0, 0.0, 'none', 5, False, False,
                                                 children=[T(sg, 'SoundGenerator', '', children=[seq_on, seq_off])]))

    def add_camera(self, like, pos, gamma, parent=None):
        """a security camera: a copy of SCamera `like` at pos (holder position) facing gamma"""
        import copy as _copy
        t = _copy.deepcopy(self.L[like])
        cid = self.nid()
        t.args[0] = v(cid)
        for k in range(3):
            t.args[3 + k] = v(float(pos[k]))
        t.args[6] = v(float(gamma))
        self.m.add_child(parent or self.m.parent[like] and lit(self.m.parent[like].args[0]), t)
        return cid

    def actor(self, parent, pos, face_to, model, anim='stand_talk1, stand_talk2', weapon='', name='actor', speed=1.0):
        """a cutscene extra (the originals' EditBoneObj pattern, e.g. L31 1060 csf1_1 'stand_talk2' + weapon 107_01_1):
        a character model looping an animation list, no AI. parent = a mid cutscene container (K.MIDS[i]['outro']) ->
        it exists only while that cutscene runs. Needed because every squad is OFF during cutscenes, so a CCTV shot of
        the general showed an empty floor (in-game 10-10). The talk/stand animations are global (COMMON/models/new.res)."""
        import atmos
        atmos.ensure_decl(self.m, 'EditBoneObj')
        g = math.atan2(-(face_to[0] - pos[0]), face_to[1] - pos[1])
        aid = self.nid()
        self.m.add_child(parent, T(aid, 'EditBoneObj', '%s %s' % (self.PFX, name), *[float(c) for c in pos], 0.0, 0.0, g,
                                   True, True, model, True, weapon, '', anim, float(speed), 0.0))
        return aid

    def cast(self, parent, pos, camera, model, name, guard_skins=(), guard_weapon='107_01_1'):
        """the man on a CCTV feed: `model` talking at pos, facing the camera, plus a guard standing 1.6 m to each side
        and 1 m behind him (only where there is floor: a nav node within 0.8 m, level within 0.6 m)"""
        p = np.array(pos[:3], float)
        dist = np.hypot(self.NODE_P[:, 0] - p[0], self.NODE_P[:, 1] - p[1]) + 3 * np.abs(self.NODE_P[:, 2] - p[2])
        p[2] = float(self.NODE_P[int(np.argmin(dist)), 2])  # stand on the walk surface (graph nodes sit above it)
        ids = [self.actor(parent, p, camera, model, 'cutscene_talk1, cutscene_talk2', name='%s (CCTV)' % name)]   # unarmed
                                                       # talkers: stand_talk* holds a rifle (all 22 originals carry one)
        d = np.array(camera[:2], float) - p[:2]
        d /= np.linalg.norm(d)
        side = np.array([-d[1], d[0]])
        for k, skin in enumerate(guard_skins[:2]):
            import atmos
            gz = None
            for sc in (1.6, 1.2, 2.0):                     # a floor next to him (vertical ray), no wall in between
                c = p[:2] + side * (sc if k == 0 else -sc) * CS.M - d * 1.0 * CS.M
                above, below = atmos._vertical_hits(self._tris()[0], (c[0], c[1], p[2] + 1.0 * CS.M))
                fl = [z for z in below if abs(z - p[2]) < 0.6 * CS.M]
                h = float(self.TERR.height(c[0], c[1]))
                if not fl and not below and not np.isnan(h) and abs(h - p[2]) < 0.6 * CS.M:
                    fl = [h]                               # the floor is the terrain (the Chinese Temple hall)
                if not fl or [z for z in below if z > fl[0]] or any(z < fl[0] + 2.0 * CS.M for z in above):
                    continue
                if self.blocked(p + np.array([0, 0, 1.0 * CS.M]), np.array([c[0], c[1], fl[0] + 1.0 * CS.M]), pad=0.02 * CS.M):
                    continue
                gz = fl[0]; break
            if gz is None:
                print('cast: no floor for %s guard %d | below %s above %s (m rel. to his floor)' % (
                    name, k + 1, [round((z - p[2]) / CS.M, 2) for z in below[:4]], [round((z - p[2]) / CS.M, 2) for z in above[:3]]))
                continue
            ids.append(self.actor(parent, (c[0], c[1], gz), camera, skin, 'stand', guard_weapon, name='%s guard %d (CCTV)' % (name, k + 1)))
        return ids

    # 10-17 (owner: 'fires that never stop'): every DESTRUCTION fire burns out. A Smoke emitter's arg 26 is its generate
    # factor and arg 27 an optional generate-factor EXPRESSION (Mission 34 'Smoke from Wu Xing's gun', Frostbite's HALO
    # 'GEN'): emission stops when it turns 0 and the particles in the air fade out by themselves (no pop). The burn clock
    # is a LevelTimer started by the trigger; the ConditionalContainer around the emitters goes false a little later and
    # removes the dead emitters. keep = an expression that keeps it burning (an outro that flies over the wreck).
    BURN_FIRE_S, BURN_SMOKE_S = 50.0, 110.0                  # flames die first, the smoke column thins out after them

    def burn_timer(self, trigger, name='fire'):
        """a LevelTimer that starts when `trigger` turns true (the burn clock) -> id"""
        import atmos
        atmos.ensure_decl(self.m, 'LevelTimer')
        timer = self.nid()
        self.m.add_child(self.LOGIC, T(timer, 'LevelTimer', '%s %s burn timer' % (self.PFX, name), 0.0, 0.0, 0.0, 0.0, 0.0,
                                       0.0, trigger, '', False))
        if not hasattr(self, 'BURNS'):
            self.BURNS = []
        self.BURNS.append(dict(trigger=trigger, timer=timer, ccs=[], fire=[], smoke=[]))
        return timer

    @staticmethod
    def burn_alive(timer, secs, keep=None):
        """'still burning' expression of a burn clock"""
        e = 'LevelTimer_%d.nTick < %d * %s' % (timer, int(round(secs)), GAME_FREQ)
        return '(%s || %s)' % (e, keep) if keep else '(%s)' % e

    def burn_out_smoke(self, t, timer, secs, keep=None):
        """make one Smoke task (a Call) stop emitting `secs` after its burn clock started (generate factor -> 0)"""
        assert lit(t.args[1]) == 'Smoke', t
        old = lit(t.args[27])
        assert not old, ('Smoke %s already has a generate-factor expression %r' % (lit(t.args[0]), old))
        gen = float(lit(t.args[26]))
        t.args[26] = v(0.0)
        t.args[27] = v('%g * %s' % (gen, self.burn_alive(timer, secs, keep)))
        return t

    def burn_out(self, smoke_ids, trigger, name='fire', fire_s=None, smoke_s=None, keep=None, fire_ids=None):
        """make Smoke tasks that already exist (MP leftovers, transplants) burn out: fire emitters (damage flag arg 30 TRUE,
        or listed in fire_ids) stop after fire_s, the others (smoke columns, dust) after smoke_s -> burn timer id"""
        fire_s = self.BURN_FIRE_S if fire_s is None else fire_s
        smoke_s = self.BURN_SMOKE_S if smoke_s is None else smoke_s
        timer = self.burn_timer(trigger, name)
        for sid in smoke_ids:
            t = self.L[sid]
            is_fire = (sid in fire_ids) if fire_ids is not None else str(lit(t.args[30])).upper() == 'TRUE'
            self.burn_out_smoke(t, timer, fire_s if is_fire else smoke_s, keep)
            self.BURNS[-1]['fire' if is_fire else 'smoke'].append(sid)
            print('burn out: %s Smoke %d (%s) stops %d s after %s' % (name, sid, 'fire' if is_fire else 'smoke',
                                                                       fire_s if is_fire else smoke_s, trigger[:60]))
        return timer

    def burn_keep(self, keep, which=('smoke',), timers=None):
        """keep registered fires going while `keep` is true (e.g. 'ConditionalContainer_<outro>.isRun': an outro that
        flies over the wreck - call it once the outro exists). which = 'fire' and/or 'smoke' emitters (smoke only by
        default: a wreck still smokes minutes later; flames that re-light would break continuity)"""
        n = 0
        for b in getattr(self, 'BURNS', []):
            if timers is not None and b['timer'] not in timers:
                continue
            pat = re.compile(r'\((LevelTimer_%d\.nTick < \d+ \* %s)\)' % (b['timer'], GAME_FREQ))
            for kind in which:
                for sid in b[kind]:
                    t = self.L[sid]
                    t.args[27] = v(pat.sub(lambda mo: '(%s || %s)' % (mo.group(1), keep), str(lit(t.args[27]))))
                    n += 1
                    par = self.m.parent.get(sid)               # its container (wreck_fx) must stay too
                    if par is not None and lit(par.args[0]) in b['ccs']:
                        par.args[3] = v(pat.sub(lambda mo: '(%s || %s)' % (mo.group(1), keep), str(lit(par.args[3]))))
        print('burn keep: %d emitters also burn while %s' % (n, keep))
        return n

    def burn_test_variant(self):
        """debug variant 'burntest=<s>': every fire registered by burn_timer / wreck_fx / burn_out starts at LevelFlow s
        (the ExplodeObject behind an 'ExplodeObject_N.isExploded' trigger really blows); the burn-out logic stays the
        release one. Kit.debug_variants calls it; builders without debug_variants call it themselves."""
        part = [p for p in getattr(self, 'DEBUG', '').split(';') if p.startswith('burntest=')]
        if not part:
            return
        dbg = 'LevelFlow_10.nTick > %d * %s' % (int(part[0][9:]), GAME_FREQ)
        m = self.m
        for b in getattr(self, 'BURNS', []):
            trig = b['trigger']
            new = '(%s || %s)' % (trig, dbg)
            m.set(b['timer'], 9, new)
            for cc in b['ccs']:
                m.set(cc, 3, str(lit(m.byid[cc].args[3])).replace(trig, new, 1))
            mo = re.fullmatch(r'ExplodeObject_(\d+)\.isExploded', trig.strip())
            if mo and int(mo.group(1)) in m.byid:
                eo = int(mo.group(1))
                old = str(lit(m.byid[eo].args[18]))
                m.set(eo, 18, '(%s) || %s' % (old, dbg) if old else dbg)
            print('debug burntest: %s starts at %s' % (trig[:50], dbg))

    def wreck_fx(self, pos, exploded, name='wreck', fire_m=3.0, smoke_m=3.5, blasts=(1.6, 3.4), smoke=True, flame=1.0,
                 fire_s=None, smoke_s=None, keep=None):
        """a burning wreck once `exploded` is true (Sandstorm MP chopper recipe, proven 10-10): the black smoke column
        and the flames of Smoke 2948/2947, plus secondary blasts (ExplodeObject 'none') `blasts` seconds later.
        There is no wrecked helicopter model in the game, so a destroyed 740_01_1 stays whole - this makes it burn.
        pos = the object's origin (world units).
        10-17: it BURNS OUT - the flames stop fire_s after the blast (default BURN_FIRE_S), the smoke column smoke_s
        (BURN_SMOKE_S); keep = expression that keeps both going (e.g. an outro over the wreck). -> the fire container id"""
        import atmos
        from mission_lib import load
        m = self.m
        fire_s = self.BURN_FIRE_S if fire_s is None else fire_s
        smoke_s = self.BURN_SMOKE_S if smoke_s is None else smoke_s
        for typ in ('Smoke', 'ConditionalContainer', 'LevelTimer'):        # ExplodeObject: every MP map declares it
            atmos.ensure_decl(m, typ)
        src = {lit(t.args[0]): t for t, d, p in tasks(load(os.path.join(ROOT, 'work', 'decomp', 'multiplayer_sandstorm_objects.qsc')))
               if lit(t.args[0]) in (2947, 2948)}
        x, y, z = (float(c) for c in pos)
        timer = self.burn_timer(exploded, name)
        kids = {}
        for sid, dz, label in ((2948, smoke_m, 'smoke'), (2947, fire_m, 'fire'))[(0 if smoke else 1):]:   # no column indoors
            t = atmos._clone(src[sid], self.nid(), '%s %s %s' % (self.PFX, name, label))
            for k, c in enumerate((x, y, z + dz * 4096.0)):
                t.args[3 + k] = v(c)
            if label == 'fire' and flame != 1.0:             # owner 10-10: a truck-sized fire, not a glowing bonfire
                t.args[8] = Int(max(20, int(lit(t.args[8]) * flame)))
                t.args[9] = v(float(lit(t.args[9])) * flame)
                t.args[20] = v(float(lit(t.args[20])) * flame)
                t.args[24] = v(float(lit(t.args[24])) * min(1.0, flame + 0.1))
            self.burn_out_smoke(t, timer, fire_s if label == 'fire' else smoke_s, keep)
            self.BURNS[-1][label].append(lit(t.args[0]))
            kids[label] = t
        for k, secs in enumerate(blasts):
            m.add_child(self.LOGIC, T(self.nid(), 'ExplodeObject', '%s %s secondary blast %d' % (self.PFX, name, k + 1),
                                      x + (k * 2 - 1) * 1.5 * 4096.0, y, z + fire_m * 4096.0, 0.0, 0.0, 0.0, 'none', 'none',
                                      1e6, 4.0, 3.0, 1.0, 0.0, 3, 3,           # HP 1e6: only the timer sets it off
                                      'LevelTimer_%d.nTick > %.2f * %s' % (timer, secs, GAME_FREQ),
                                      'explo_04_xl' if k == 0 else 'explo_03_l'))
        out = None
        for label, secs in (('fire', fire_s), ('smoke', smoke_s)):          # the dead emitters go 20 s after they stop
            if label not in kids:                                           # (the particles in the air have faded by then)
                continue
            cc = self.nid()
            m.add_child(self.LOGIC, T(cc, 'ConditionalContainer', '%s %s burning (%s)' % (self.PFX, name, label),
                                      '(%s) && %s' % (exploded, self.burn_alive(timer, secs + 20.0, keep)), '', '',
                                      children=[kids[label]]))
            self.BURNS[-1]['ccs'].append(cc)
            out = out or cc
        return out

    def heli_wreck(self, hid, name='helicopter', model='b740_01_1', sink_m=0.8):
        """owner round 3 (10-10): a blown-up helicopter must look blown up. The intact ExplodeObject vanishes in the blast
        (destroyed model 'none', like Mission 32's 'Plane Shot down') and a burnt-out copy (tools/burnt.py: same mesh,
        charred textures) lies there instead - sunk onto its belly, rolled over, rotors stopped."""
        a = [float(lit(x)) for x in self.L[hid].args[3:9]]
        self.m.set(hid, 10, 'none')
        cc = self.nid()
        wreck = T(self.nid(), 'EditRigidObj', '%s %s wreck (burnt)' % (self.PFX, name), a[0], a[1], a[2] - sink_m * 4096.0,
                  0.09, 0.27, a[5] + 0.22, model, 5, False, False)
        self.m.add_child(self.LOGIC, T(cc, 'ConditionalContainer', '%s %s wreck' % (self.PFX, name),
                                       'ExplodeObject_%d.isExploded' % hid, '', '', children=[wreck]))
        self.m.models.add(model.lower() + '.mef')
        return cc

    # ------------------------------------------------------------------ 5. objectives: TBAs, messages, list, markers
    def tba(self, name, pos, rot, model='200_01_1', done_model='200_03_1', anim='hack_computer', secs=4.0,
            sprite='STATUSSCREEN:action_comput.spr', sound='tba_hackcomp', parent=None, need=None, tid=None):
        """use-object ('press E'): 4 s = the length of the hands animation of the originals (longer = the hands stop and
        the player has to keep holding E - owner bug report 10-10). need = extra condition before it can be used
        (e.g. 'GenericPickup_N.isPickedUp': the C4 kit). tid = an id reserved earlier (sf-flow 11-15: a TBA that takes an
        original's lightmaps through prefabs.Transplant needs its id before X.finish)"""
        assert secs <= 5.0, 'TBA longer than its animation'
        tid = tid or self.nid()
        active = '!GenericTBA_%d.isFinished' % tid + (' && (%s)' % need if need else '')
        self.m.add_child(parent or self.LOGIC, T(tid, 'GenericTBA', '%s %s' % (self.PFX, name), *[float(c) for c in pos],
                                                 *[float(r) for r in rot], model, done_model, 100.0, 0.0, 0.0, 0.0, 0.0, 0, 0,
                                                 '', '', 0.0, 0.0, 0.0, False, active, anim,
                                                 float(secs), sprite, sound))
        return tid

    # ------------------------------------------------------------------ 5b. objective kinds beyond 'type on a computer'
    # (owner feedback 10-10: plant things, take things, see where they are, a harder kit, a bit of loot in the houses)
    @staticmethod
    def loadout(primary='TYPE64SMG', primary_ammo=270, sidearm='SOCOM', sidearm_ammo=60, extras=()):
        """the owner's kit, round 3 (10-10): ONE silenced automatic (IGI 2 has no silenced assault rifle - the Type 64
        is its only silenced full-auto primary), ONE silenced pistol (SOCOM) and the knife. Nothing else: no grenades,
        no syringes, no binoculars. Ammo for the Type 64 also lies in the loot (enemies carry AKs)."""
        out = ['Human_AddWeapon("WEAPON_ID_%s")' % primary, 'Human_AddWeapon("WEAPON_ID_%s")' % sidearm,
               'Human_AddWeapon("WEAPON_ID_KNIFE")']
        out += ['Human_AddWeapon("WEAPON_ID_%s")' % e for e in extras]
        out += ['Human_AddAmmoForWeapon("WEAPON_ID_%s",%d)' % (primary, primary_ammo),
                'Human_AddAmmoForWeapon("WEAPON_ID_%s",%d)' % (sidearm, sidearm_ammo)]
        return out

    def item(self, name, pos, gamma, model, show_when=None):
        """an objective item Jones TAKES (GenericPickup; originals: 'Briefcase' 806_01_1, 'Papers' 230_05_1, 'C4' 113_02_1,
        'Fuses' 113_05_1): it disappears from the world -> GenericPickup_N.isPickedUp. show_when = it only appears once
        that is true (e.g. the safe is open)."""
        import atmos
        atmos.ensure_decl(self.m, 'GenericPickup')
        pid = self.nid()
        t = T(pid, 'GenericPickup', '%s %s' % (self.PFX, name), *[float(c) for c in pos], 0.0, 0.0, float(gamma), model)
        if show_when:
            atmos.ensure_decl(self.m, 'ConditionalContainer')
            self.m.add_child(self.PICK, T(self.nid(), 'ConditionalContainer', '%s %s (hidden until)' % (self.PFX, name),
                                          show_when, '', '', children=[t]))
        else:
            self.m.add_child(self.PICK, t)
        return pid

    def plant(self, name, pos, gamma, need=None, done_model='113_04_1', kind='c4', parent=None):
        """a charge / device Jones PLANTS (originals: L4 'C4 #1' - model none -> the C4 113_04_1 stays where he put it).
        kind 'c4' = tba_place_c4 + C4 icon, 'gps' = tba_place_gps + GPS icon (L36 'Attach Transmitter')"""
        anim, sprite = {'c4': ('tba_place_c4', 'STATUSSCREEN:a_c4.spr'), 'gps': ('tba_place_gps', 'STATUSSCREEN:a_gps.spr')}[kind]
        tid = self.tba(name, pos, (0.0, 0.0, float(gamma)), model='none', done_model=done_model, anim=anim, secs=4.0,
                       sprite=sprite, sound='tba_placec4', need=need, parent=parent)
        # the 'Destroyed model' only shows once the TBA 'explodes' (decl arg 18 = Explosion expression): L4 'C4 #1' sets
        # it to its own isFinished (reviewer 10-10). Explodable stays FALSE (L1-6 1001) - no early trigger by a grenade.
        self.m.set(tid, 18, 'GenericTBA_%d.isFinished' % tid)
        return tid

    def marker(self, pos, until, color=(2.0, 0.25, 0.15), size=0.3, name='marker'):
        """a small blinking light at an objective spot (it was invisible - owner 10-10) that goes out once `until` is true"""
        import atmos
        atmos.ensure_decl(self.m, 'ConditionalContainer')
        cc = self.nid()
        self.m.add_child(self.LOGIC, T(cc, 'ConditionalContainer', '%s %s' % (self.PFX, name), '!(%s)' % until, '', ''))
        atmos.blink(self.m, self.nid, cc, 1.2, 0.6, [atmos.glow(self.m, self.nid, None, pos, color=color, size=size, name=name)],
                    name='%s %s blink' % (self.PFX, name))
        return cc

    def loot(self, items):
        """a little loot inside the houses: items = [(name, 'WEAPON_ID_X', graph, center, radius)] -> GunPickups on INDOOR
        floor nodes near center (any node if that graph has no indoor nodes there)"""
        got = []
        for name, weapon, g, center, radius in items:
            try:
                p = self.pick(g, 1, center, radius, where='in', spacing=4000.0)[0]
            except AssertionError:
                p = self.pick(g, 1, center, radius, spacing=4000.0)[0]
            self.m.add_child(self.PICK, T(self.nid(), 'GunPickup', '%s loot %s' % (self.PFX, name), float(p[0]), float(p[1]),
                                          float(p[2]) + 300.0, 1.570796, 0.0, float(self.m.rng.random() * 6.28), weapon, ''))
            got.append(p)
        return got

    def surface_spot(self, target, height_m=1.0, rmin_m=1.0, rmax_m=6.0, ground_z=None, prefer=None, obj_radius_m=None):
        """a plant spot ON the side of an object (truck, crate, hut wall): from the nearest walkable floor around it, cast
        toward its centre at height_m and stop 6 cm before the first surface -> ((x, y, z), gamma facing the player, floor).
        prefer = a point the player comes from (picks the floor node nearest to it among the candidates)"""
        tgt = np.array(target[:3], float)
        Pn = self.NODE_P
        gz = tgt[2] if ground_z is None else ground_z
        d = np.hypot(Pn[:, 0] - tgt[0], Pn[:, 1] - tgt[1])
        ok = (np.abs(Pn[:, 2] - gz) < 1.0 * CS.M) & (d >= rmin_m * CS.M) & (d <= rmax_m * CS.M)
        assert ok.any(), ('no floor around', [c / CS.M for c in tgt])
        key = d if prefer is None else np.hypot(Pn[:, 0] - prefer[0], Pn[:, 1] - prefer[1])
        for k in np.argsort(np.where(ok, key, np.inf))[:40]:
            if not ok[k]:
                break
            fl = Pn[k]
            a = np.array([fl[0], fl[1], fl[2] + height_m * CS.M])
            b = np.array([tgt[0], tgt[1], fl[2] + height_m * CS.M])
            if not self.blocked(a, b, pad=0.02 * CS.M):
                continue                                    # nothing to plant on along this line
            lo, hi = 0.0, 1.0                               # binary search: the first surface on a -> b
            for _ in range(18):
                mid = (lo + hi) / 2
                if self.blocked(a, a + (b - a) * mid, pad=0.01 * CS.M):
                    hi = mid
                else:
                    lo = mid
            L = np.linalg.norm(b - a)
            if lo * L < 0.3 * CS.M:
                continue                                    # started inside geometry (reviewer 10-10)
            hit = a + (b - a) * max(0.0, lo - 0.06 * CS.M / L)
            if obj_radius_m is not None and np.linalg.norm(hit[:2] - tgt[:2]) > obj_radius_m * CS.M:
                continue                                    # hit something else (a wall, a railing) before the target
            if np.linalg.norm(hit[:2] - fl[:2]) > 2.2 * CS.M:
                continue                                    # the surface must be within reach of that floor spot
            u = (fl[:2] - hit[:2]) / max(1.0, np.linalg.norm(fl[:2] - hit[:2]))
            return (float(hit[0]), float(hit[1]), float(hit[2])), math.atan2(-u[0], u[1]), tuple(float(c) for c in fl)
        raise AssertionError(('no reachable surface on', [c / CS.M for c in tgt]))

    def wall_near(self, floor_pt, height_m=1.0, max_m=2.0, toward=None, spread_deg=75):
        """the nearest collision surface around a standing spot (16 horizontal rays at height_m; toward = a point to prefer,
        only rays within spread_deg of it) -> ((x, y, z) 6 cm off the surface, gamma facing the standing spot) or None"""
        f = np.array(floor_pt[:3], float)
        a = f + np.array([0, 0, height_m * CS.M])
        base = None if toward is None else math.atan2(toward[1] - f[1], toward[0] - f[0])
        best = None
        for k in range(32):
            ang = k * math.pi / 16
            if base is not None and abs((ang - base + math.pi) % (2 * math.pi) - math.pi) > math.radians(spread_deg):
                continue
            b = a + np.array([math.cos(ang), math.sin(ang), 0.0]) * max_m * CS.M
            if not self.blocked(a, b, pad=0.01 * CS.M):
                continue
            lo, hi = 0.0, 1.0
            for _ in range(16):
                mid = (lo + hi) / 2
                if self.blocked(a, a + (b - a) * mid, pad=0.01 * CS.M):
                    hi = mid
                else:
                    lo = mid
            dist = lo * max_m * CS.M
            if dist < 0.3 * CS.M:
                continue
            if best is None or dist < best[0]:
                best = (dist, ang)
        if best is None:
            return None
        dist, ang = best
        hit = a + np.array([math.cos(ang), math.sin(ang), 0.0]) * (dist - 0.06 * CS.M)
        u = (f[:2] - hit[:2]) / max(1.0, np.linalg.norm(f[:2] - hit[:2]))
        return (float(hit[0]), float(hit[1]), float(hit[2])), math.atan2(-u[0], u[1])

    def desk_spot(self, p_top, floor_dz=(0.5, 1.4), edge_m=0.25):
        """a panel ON a table top, at the edge a player can reach, facing him: from p_top (a point on the table top) find
        the nearest floor (nav node 0.5-1.4 m lower, in clear sight), walk the table top toward it to its edge, step back
        edge_m. -> ((x, y, z), gamma). (10-10: the lab computer faced the wall - 'I need to get over the table')"""
        import atmos
        Tr = self._tris()[0]
        p = np.array(p_top[:3], float)
        Pn = self.NODE_P
        dz = p[2] - Pn[:, 2]
        d = np.hypot(Pn[:, 0] - p[0], Pn[:, 1] - p[1])
        ok = (dz >= floor_dz[0] * CS.M) & (dz <= floor_dz[1] * CS.M) & (d < 4 * CS.M)
        best = None
        for k in np.argsort(np.where(ok, d, np.inf))[:60]:
            if not ok[k]:
                break
            eye = Pn[k] + np.array([0, 0, 1.6 * CS.M])
            if not self.blocked(eye, p + np.array([0, 0, 0.3 * CS.M]), pad=0.02 * CS.M):
                best = Pn[k]
                break
        assert best is not None, ('no floor in sight of the table spot', [c / CS.M for c in p])
        u = (best[:2] - p[:2]) / np.linalg.norm(best[:2] - p[:2])
        q = p[:2].copy()
        for step in range(80):                              # 5 cm steps along the table top toward the floor spot
            n_ = q + u * 0.05 * CS.M
            _, below = atmos._vertical_hits(Tr, (n_[0], n_[1], p[2] + 0.3 * CS.M))
            if not below or abs(below[0] - p[2]) > 0.15 * CS.M:
                break                                       # off the table top
            q = n_
        q = q - u * (edge_m - 0.05) * CS.M                  # back from the edge (onto the table, never over it)
        gamma = math.atan2(-u[0], u[1])                     # front = (-sin g, cos g) = toward the player
        return (float(q[0]), float(q[1]), float(p[2])), gamma

    def area(self, name, pos, size, criteria='CRITERIA_HUMAN0', parent=None):
        """AreaActivate box (size = half extents in world units, like the originals)"""
        aid = self.nid()
        self.m.add_child(parent or self.LOGIC, T(aid, 'AreaActivate', '%s %s' % (self.PFX, name), float(pos[0]), float(pos[1]),
                                                 float(pos[2]), 0.0, 0.0, 0.0, float(size[0]), float(size[1]), float(size[2]), criteria))
        return aid

    def vo(self, name, text, who='Zira', speed=0, raw=False):
        """register a voice line -> (def name, seconds). Cached by text in work/voice_cache. raw=True: no radio filter
        (a voice heard in person, not over the radio - Iron Tsar 10-16; default unchanged)"""
        assert len(name) <= 15 and name.startswith(self.vp), name
        said = spoken(text)
        # 10-29 (SHOBI rework, tw-shared): a RECORDED line wins - work/voice_actors/<build>/<def>.wav (or the mission's
        # short name / flat, voice.actor_wav); converted to 16-bit mono 22050 Hz, radio speakers through voice.radio2,
        # in-person speakers (raw / RAW_VOICES) dry. Cached by the file's content, so a new take is picked up. A take
        # recorded for another text (voicescript's _script.json next to it) is NOT used: the caption must match.
        folder, mid = getattr(self, 'FOLDER', '') or '', getattr(self, 'ID', None)
        rec = voice.actor_wav(name, folder.replace('_sp', '') or None, mid) if hasattr(voice, 'actor_wav') else None
        if rec and hasattr(voice, 'take_text'):
            tt = voice.take_text(rec)
            if tt is not None and spoken(tt).strip() != said.strip():
                print('spkit.vo: WARNING the take %s was recorded for "%s" - the line now says "%s": TTS used' % (
                    os.path.relpath(rec, ROOT), tt[:60], text[:60]))
                rec = None
        if rec:
            chain = 'raw' if (raw or who in voice.RAW_VOICES) else 'r2'
            tag = voice.r2_tag() if hasattr(voice, 'r2_tag') else 'r2v%d' % getattr(voice, 'R2_VERSION', 0)
            h = hashlib.sha1(('rec|%s|%s|' % (chain, tag)).encode() + open(rec, 'rb').read()).hexdigest()[:10]
            path = os.path.join(VO_CACHE, '%s_rec_%s.wav' % (name, h))
            if not os.path.exists(path):
                os.makedirs(VO_CACHE, exist_ok=True)
                voice.recorded(rec, path, chain)
            src = 'recorded'
        else:
            eng = voice.engine_for(who)                          # (10-13: Kokoro neural voices; the cache key carries the engine)
            if hasattr(voice, 'radio_chain'):                    # (10-29: r2 = the new radio chain, missions 1-4 by default)
                chain = voice.radio_chain(who, raw, mission_id=mid)
            else:
                chain = 'raw' if raw or who in voice.RAW_VOICES else 'r1'
            h = hashlib.sha1((('v1|' if eng == 'sapi' else 'v2|%s|' % eng) + '%s|%s' % (who, said) + ('|%d' % speed if speed else '') + ('|raw' if raw else '')
                              + ('|' + voice.r2_tag() if chain == 'r2' else '')).encode()).hexdigest()[:10]   # (old r1 / raw keys unchanged)
            path = os.path.join(VO_CACHE, '%s_%s.wav' % (name, h))
            if not os.path.exists(path):
                os.makedirs(VO_CACHE, exist_ok=True)
                if hasattr(voice, 'safe_replace'):           # (10-29: a per-process tmp dir - parallel variant builds of one
                    tdir = os.path.join(VO_CACHE, 'tmp_%d' % os.getpid())   # mission make the same defs at the same time)
                    tmp = voice.make({name: (who, said)}, tdir, speed=speed, raw=raw, chain=chain)[name]
                    voice.safe_replace(tmp, path)
                    try:
                        os.rmdir(tdir)
                    except OSError:
                        pass
                else:
                    tmp = voice.make({name: (who, said)}, os.path.join(VO_CACHE, 'tmp'), speed=speed, raw=raw)[name]
                    shutil.move(tmp, path)
            src = 'tts-%s' % eng
        w = wave.open(path, 'rb'); secs = w.getnframes() / float(w.getframerate()); w.close()
        self.VO[name] = (path, secs)
        self._vo_note(name, dict(def_=name, who=who, text=text, said=said, speed=speed, raw=bool(raw), chain=chain, source=src,
                                 secs=round(secs, 2), wav=os.path.relpath(path, ROOT), recorded=os.path.relpath(rec, ROOT) if rec else ''))
        return name, secs

    def _vo_note(self, name, rec):
        """10-29: every voice line of this build -> work/shobi/voice/lines/<build>.json at exit (tools/voicescript.py reads
        it for the Neonix script: mission, def, speaker, text, radio or in person, length). A process that never reached
        the end of K.write leaves <build>.partial.json instead (review 10-29: a crashed build must not feed the sheet)."""
        if not hasattr(self, 'VO_META'):
            self.VO_META = {}
            import atexit
            atexit.register(self._vo_dump)
        self.VO_META[name] = rec

    def _vo_dump(self):
        try:
            import json
            d = os.path.join(ROOT, 'work', 'shobi', 'voice', 'lines')
            os.makedirs(d, exist_ok=True)
            folder = getattr(self, 'FOLDER', '') or 'unknown_sp'
            b = os.environ.get('SPKIT_BUILD') or (folder.replace('_sp', '') + ('_TEST' if getattr(self, 'DEBUG', '') else ''))
            done = bool(getattr(self, 'out', None))           # (K.write sets self.out when the build is complete)
            p = os.path.join(d, b + ('.json' if done else '.partial.json'))
            tmp = p + '.%d.tmp' % os.getpid()
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(dict(build=b, mission_id=getattr(self, 'ID', None), folder=folder, prefix=getattr(self, 'PFX', ''),
                               title=getattr(self, 'title', ''), debug=getattr(self, 'DEBUG', ''), complete=done,
                               written=__import__('time').strftime('%Y-%m-%d %H:%M:%S'), lines=list(self.VO_META.values())),
                          fh, indent=1)
            (voice.safe_replace if hasattr(voice, 'safe_replace') else os.replace)(tmp, p)
        except Exception as e_:                              # (never fail a build over the line sheet)
            print('spkit: voice line manifest not written: %s' % e_)

    def msg(self, key, label, send, text, dur=5.0, voice_def=None, who='Zira', sound=None):
        i = self.nid()
        snd = sound or 'statusmessage'
        if voice_def:
            snd, secs = self.vo(voice_def, text, who)
            dur = max(dur, secs + 0.5)
        self.m.add_child(self.LOGIC, T(i, 'StatusMessage', label, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, send, key, '', snd, True, False,
                                       float(dur), ''))
        if text:
            self.m.add_text('messages', key, text)
        self.M[key] = i
        return i

    def objectives(self, items, markers):
        """items: [(key, linked task id, done condition, text)] (<= 8); markers: [(task id or (x, y, z), objective no.)]"""
        assert len(items) <= 8, 'the objective list has 8 slots'
        m = self.m
        args = [Int(self.nid()), Str('DefineComputerObjective'), Str('Objectives'), Str('1')]
        for slot in range(8):
            if slot < len(items):
                key, link, cond, text = items[slot]
                args += [Str(key), v(link), Str(cond), Str('')]
                m.add_text('objectives', key, text)
            else:
                args += [Str(''), v(-1), Str(''), Str('')]
        mapc = self.nid()
        m.add_child(self.PARENT, T(mapc, 'Container', '%s map computer' % self.PFX, False, children=[Call('Task_New', args)]))
        for tid, n in markers:
            x, y, z = (m.arg(tid, 3), m.arg(tid, 4), m.arg(tid, 5)) if isinstance(tid, int) else tid
            link = str(tid) if isinstance(tid, int) else '-1'
            # owner bug 10-11: markers 7 (kill the commander) and 8 (extraction) never showed - linked to a soldier / an
            # area, and also not when linked to a StatusMessage (tested in game). Markers linked to a model-less GenericTBA
            # do show (the tracker, 6), even while it cannot be used yet (the truck C4, 5). So those get an invisible anchor:
            # a GenericTBA that can never be used, at the target's spot.
            typ = str(lit(self.L[tid].args[1])) if isinstance(tid, int) and tid in self.L else ''
            if not isinstance(tid, int) or typ in ('HumanSoldier', 'HumanAI', 'AreaActivate'):
                link = str(self.tba('map marker %d anchor' % n, (float(x), float(y), float(z)), (0.0, 0.0, 0.0), model='none',
                                    done_model='none', need='FALSE'))
            m.add_child(mapc, T(self.nid(), 'ComputerHilight', '', float(x), float(y), float(z), '1', link, 'COMPUTER:h_%d.spr' % n,
                                'MARKER_NONE', 'MARKER_COLOR_NONE', '', '', -1))

    def texts(self, name, desc):
        self.m.add_text('missions', 'Mission %d Name' % self.ID, name)
        self.m.add_text('missions', 'Mission %d Desc' % self.ID, desc)

    # ------------------------------------------------------------------ 6. cutscenes
    def P(self, i):
        return tuple(float(self.m.arg(i, k)) for k in (3, 4, 5))

    @staticmethod
    def up(p_, metres):
        return (p_[0], p_[1], p_[2] + metres * CS.M)

    def shots(self, spec, prefix, fade_in=False, fade_out=False):
        """spec entries:
             (voice def, text, target, dist m, bearing0, bearing1, elev deg[, fov])      orbit around a point
             (voice def, text, [(pos, look), (pos, look)])                                 explicit camera move
             (voice def, text, [(pos, look, fov), (pos, look, fov)], 'cctv')               hacked security-camera look
           voice def None = caption without voice (dur 4 s). Each shot lasts its line + 1.2 s. -> (keys, captions)"""
        keys, caps, t = [], [], 0.0
        for k, (vdef, text, target, *geo) in enumerate(spec):
            who = 'Zira'
            if isinstance(vdef, tuple):
                vdef, who = vdef
            if vdef:
                name, secs = self.vo(vdef, text, who)
            else:
                name, secs = '', 3.0
            dur = secs + 1.2
            if isinstance(target, list):
                look_ = geo[0] if geo else None
                (p0, l0, *f0), (p1, l1, *f1) = target
                f0 = f0[0] if f0 else 1.0
                f1 = f1[0] if f1 else f0
                if look_ == 'cctv':
                    ks = cctv(p0, l0, p1, l1, dur, f0, f1)
                else:
                    ks = [CS.key(p0, l0, dur, True, fov=f0), CS.key(p1, l1, 0.0, False, fov=f1)]
            else:
                dist, b0, b1, elev = geo[:4]
                fov = geo[4] if len(geo) > 4 else 1.0
                fov_end = geo[5] if len(geo) > 5 else None            # (zoom in / out during the orbit)
                ks = CS.orbit_shot(self.TERR, target, dist, b0, b1, elev, dur, fov=fov, fov_end=fov_end)
            if k == 0 and fade_in:
                p0, l0 = ks[0]['pos'], ks[0]['tgt']
                keys += [CS.key(p0, l0, 1.5, True, filt=CS.BAND, color=(0, 0, 0), noise=0.0, fov=ks[0]['fov']),
                         CS.key(p0, l0, 0.0, False, filt=CS.BAND, color=(1, 1, 1), noise=0.0, fov=ks[0]['fov'])]
                t += 1.5
            keys += ks
            caps.append((round(t + 0.3, 2), '%s_%d' % (prefix, k + 1), text, name, secs + 0.3))
            t += sum(k_['dur'] for k_ in ks)
        if fade_out:
            p_, l_ = keys[-1]['pos'], keys[-1]['tgt']
            keys += [CS.key(p_, l_, 2.5, True, filt=CS.BAND, color=(1, 1, 1), noise=0.0),
                     CS.key(p_, l_, 0.0, False, filt=CS.BAND, color=(0, 0, 0), noise=0.0)]
        return keys, caps

    # ------------------------------------------------------------------ camera placement with line of sight
    def _tris(self):
        if not hasattr(self, '_TRI'):
            T_ = self.nv.triangles()
            self._TRI = (T_, T_.min(axis=1), T_.max(axis=1))
        return self._TRI

    def _exact_spot(self, tp, gamma, dist_m):
        """test placement (at=): a floor point dist_m in front of panel tp (within +-45 deg), the panel 0.3-1.8 m above
        that floor, standing room above it (not a desk top) and the panel in clear sight -> (x, y, floor z) or None"""
        import atmos
        T_ = self._tris()[0]
        for dist_ in (dist_m, 1.0, 1.3, 0.9):
            for off in (0, 15, -15, 30, -30, 45, -45):
                g = gamma + math.radians(off)
                c = tp[:2] + np.array([-math.sin(g), math.cos(g)]) * dist_ * CS.M
                above, below = atmos._vertical_hits(T_, (c[0], c[1], tp[2]))
                fl = [z for z in below if 0.3 * CS.M <= tp[2] - z <= 1.8 * CS.M]
                h = float(self.TERR.height(c[0], c[1]))
                if not fl and not np.isnan(h) and 0.3 * CS.M <= tp[2] - h <= 1.8 * CS.M and not below:
                    fl = [h]                               # open ground
                if not fl:
                    continue
                fz = fl[0]
                if [z for z in below if z > fz] or any(z < fz + 1.9 * CS.M for z in above):
                    continue                               # something between the floor and head height
                if any(fz - z > 0.6 * CS.M for z in fl[1:]):
                    continue                               # fz is furniture (a desk top), a real floor lies below it
                u_ = (c - tp[:2]) / np.linalg.norm(c - tp[:2])     # (reviewer 10-10: blocked() ignores hits within
                s0 = np.array([tp[0] + u_[0] * 0.15 * CS.M, tp[1] + u_[1] * 0.15 * CS.M, fz + 1.0 * CS.M])   # 0.3 m of
                if self.blocked(s0, np.array([c[0], c[1], fz + 1.0 * CS.M]), pad=0.02 * CS.M):   # its ends, so a spot
                    continue                               # inside / behind a wall passed the sight test) - wall between
                if any(self.blocked(np.array([c[0], c[1], fz + hh]), np.array([c[0] + dx * 0.35 * CS.M, c[1] + dy * 0.35 * CS.M,
                                                                              fz + hh]), pad=0.01 * CS.M)
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) for hh in (0.9 * CS.M, 1.5 * CS.M)):
                    continue                               # no room for a body there
                eye = np.array([c[0], c[1], fz + 1.6 * CS.M]); v_ = tp - eye
                if self.blocked(eye, tp - v_ / np.linalg.norm(v_) * 0.35 * CS.M):
                    continue
                return np.array([c[0], c[1], fz])
        return None

    def _grid_near(self, smin, smax):
        """indices of the triangles whose box may touch smin..smax in x, y: a superset, blocked() still tests every one of them"""
        if not hasattr(self, '_GRID'):
            _, lo, hi = self._tris()
            s = 16.0 * CS.M
            x0, y0 = np.floor(lo[:, 0] / s).astype(int), np.floor(lo[:, 1] / s).astype(int)
            x1, y1 = np.floor(hi[:, 0] / s).astype(int), np.floor(hi[:, 1] / s).astype(int)
            g = {}
            for i in range(len(lo)):
                for cx in range(x0[i], x1[i] + 1):
                    for cy in range(y0[i], y1[i] + 1):
                        g.setdefault((cx, cy), []).append(i)
            self._GRID = (s, {k: np.array(v) for k, v in g.items()})
        s, g = self._GRID
        cells = [g[(cx, cy)] for cx in range(int(math.floor(smin[0] / s)), int(math.floor(smax[0] / s)) + 1)
                 for cy in range(int(math.floor(smin[1] / s)), int(math.floor(smax[1] / s)) + 1) if (cx, cy) in g]
        return np.unique(np.concatenate(cells)) if cells else np.zeros(0, int)

    def blocked(self, a, b, pad=0.3 * CS.M):
        """True if the segment a -> b hits a collision triangle of any structure (or dips under the terrain)"""
        a = np.asarray(a, float); b = np.asarray(b, float)
        for f in np.linspace(0.05, 0.95, 19):
            p = a + (b - a) * f
            h = self.TERR.height(p[0], p[1])
            if not np.isnan(h) and p[2] < h + 0.3 * CS.M:
                return True
        T_, lo, hi = self._tris()
        smin, smax = np.minimum(a, b) - pad, np.maximum(a, b) + pad
        if os.environ.get('SS_FAST'):                     # (11-07: 46 % of a build was the two all() below, over every triangle. Same answer from a 2-D grid)
            near = self._grid_near(smin, smax)
            sel = np.all(hi[near] >= smin, axis=1) & np.all(lo[near] <= smax, axis=1)
            if not sel.any():
                return False
            t = T_[near[sel]]
        else:
            sel = np.all(hi >= smin, axis=1) & np.all(lo <= smax, axis=1)
            if not sel.any():
                return False
            t = T_[sel]
        d = b - a
        L = np.linalg.norm(d); d = d / L
        e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
        pv = np.cross(d, e2)
        det = np.einsum('ij,ij->i', e1, pv)
        ok = np.abs(det) > 1e-9
        inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        tv = a - t[:, 0]
        u = np.einsum('ij,ij->i', tv, pv) * inv
        qv = np.cross(tv, e1)
        vv = (qv @ d) * inv
        tt = np.einsum('ij,ij->i', e2, qv) * inv
        hit = ok & (u >= 0) & (vv >= 0) & (u + vv <= 1) & (tt > pad) & (tt < L - pad)
        return bool(hit.any())

    def frame(self, target, dist_m=(7, 14), height_m=(3.5, 7.0), bearings=None, prefer=None, clear_m=1.0, stop_m=0.5):
        """a camera position that SEES target (clear line of sight through the real collision meshes), with free
        space around the lens; prefer = bearing (deg) to favour. -> (pos, target)"""
        tgt = np.asarray(target, float)
        best = None
        for b in (bearings if bearings is not None else range(0, 360, 15)):
            for dm in np.linspace(dist_m[0], dist_m[1], 4):
                for hm in np.linspace(height_m[0], height_m[1], 3):
                    c = tgt + np.array([math.sin(math.radians(b)) * dm * CS.M, math.cos(math.radians(b)) * dm * CS.M, hm * CS.M])
                    dv = tgt - c
                    if self.blocked(c, tgt - dv / np.linalg.norm(dv) * stop_m * CS.M):   # (stop short of the target's own mesh)
                        continue
                    if any(self.blocked(c, c + np.array(o) * clear_m * CS.M) for o in
                           ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))):
                        continue                              # lens inside a wall / roof
                    score = abs(dm - sum(dist_m) / 2) + (0 if prefer is None else abs(((b - prefer + 180) % 360) - 180) / 30.0)
                    if best is None or score < best[0]:
                        best = (score, tuple(float(x) for x in c))
        assert best, ('no clear camera position for', [x / CS.M for x in tgt])
        return best[1], tuple(float(x) for x in tgt)

    @staticmethod
    def zoom_in(spec, factor=0.6, first=0.85):
        """orbit shots slowly zoom in on their target while the camera circles (the establishing shot only a little)"""
        out = []
        for k, e in enumerate(spec):
            vdef, text, target, *geo = e
            if isinstance(target, list) or len(geo) < 4:
                out.append(e); continue
            fov = geo[4] if len(geo) > 4 else 1.0
            out.append((vdef, text, target, *geo[:4], fov, round(fov * (first if k == 0 else factor), 3)))
        return out

    def panel_spot(self, target, ground_z, rmin_m, rmax_m, height_m=0.9):
        """a place for an invisible use-panel against a structure: the nearest walkable floor point at ground level
        (ground_z +- 1 m) rmin..rmax metres from the target's centre, raised height_m, facing away from the target
        (panels are used from their front). -> (pos, gamma)"""
        Pn = self.NODE_P
        d = np.hypot(Pn[:, 0] - target[0], Pn[:, 1] - target[1])
        ok = (np.abs(Pn[:, 2] - ground_z) < 1.0 * CS.M) & (d >= rmin_m * CS.M) & (d <= rmax_m * CS.M)
        assert ok.any(), ('no panel spot near', [c / CS.M for c in target])
        k = int(np.argmin(np.where(ok, d, np.inf)))
        p_ = Pn[k]
        return ((float(p_[0]), float(p_[1]), float(p_[2]) + height_m * CS.M),
                math.atan2(-(p_[0] - target[0]), p_[1] - target[1]))

    def check_cameras(self, keys, allow_inside=()):
        for k_ in keys:
            p = k_['pos']
            if any(math.dist(p, a) < 1 for a in allow_inside):
                continue
            h = self.TERR.height(p[0], p[1])
            assert np.isnan(h) or p[2] > h + 1.0 * CS.M, ('camera under the terrain', p, h)

    def cutscenes(self, intro_keys, intro_caps, outro_keys, outro_caps, done_msg, allow_inside=(), mids=(),
                  intro_pre=(), intro_post=(), outro_pre=()):
        """mids: [(keys, captions, trigger expression)] mid-mission cutscenes (L26 'Mid-game Cutscene' pattern: the
        player and the enemies are off while it runs, the break key skips it, it plays once).
        intro_pre / intro_post / outro_pre: extra shots from tools/cine.py (HALO drop before + touchdown after the
        briefing tour, the helicopter pick-up before the outro tour) - [dict(cs, tasks, dur, name)]"""
        self.check_cameras(intro_keys + outro_keys + [k for ks, c, t in mids for k in ks], allow_inside)
        m = self.m
        if intro_pre or intro_post:
            cs, cs_t = CS.cutscene(self.nid, intro_keys, 'briefing')
            brief = dict(cs=cs, tasks=[cs_t], dur=sum(k_['dur'] for k_ in intro_keys), name='briefing tour')
            off = sum(s_['dur'] for s_ in intro_pre)
            caps = [(round(c[0] + off, 2),) + tuple(c[1:]) for c in intro_caps]
            self.CSI = CS.add_chain(m, self.nid, self.PARENT, list(intro_pre) + [brief] + list(intro_post), caps, 'intro')
        else:
            self.CSI = CS.add_intro(m, self.nid, self.PARENT, intro_keys, intro_caps)
        trig = 'StatusMessage_%d.isFinishedDisplay' % done_msg
        if outro_pre:
            cs, cs_t = CS.cutscene(self.nid, outro_keys, 'outro tour')
            tour = dict(cs=cs, tasks=[cs_t], dur=sum(k_['dur'] for k_ in outro_keys), name='outro tour')
            off = sum(s_['dur'] for s_ in outro_pre)
            caps = [(round(c[0] + off, 2),) + tuple(c[1:]) for c in outro_caps]
            self.CSO = CS.add_chain(m, self.nid, self.PARENT, list(outro_pre) + [tour], caps, 'outro', trigger=trig)
        else:
            self.CSO = CS.add_outro(m, self.nid, self.PARENT, outro_keys, outro_caps, trig)
        self.MIDS = [CS.add_outro(m, self.nid, self.PARENT, ks, caps, trig) for ks, caps, trig in mids]
        for md in self.MIDS:                                 # (outro wiring minus the LevelFlow link)
            m.set(md['outro'], 2, 'Mid-game Cutscene')
        self.NOT_CS = ' && '.join(['!ConditionalContainer_%d.isRun' % c for c in
                                   [self.CSI['intro'], self.CSO['outro']] + [md['outro'] for md in self.MIDS]])
        CS.gate(m, self.PC, self.NOT_CS, 'ThePlayer - off during cutscenes')
        CS.gate(m, self.SQ_PARENT, self.NOT_CS, '%s enemies - off during cutscenes' % self.PFX)
        print('cutscenes: intro %.1f s (%d keys%s), outro %.1f s%s' % (
            self.CSI.get('total', sum(k_['dur'] for k_ in intro_keys)), len(intro_keys),
            ', + HALO drop %.1f s + touchdown %.1f s' % (sum(s_['dur'] for s_ in intro_pre), sum(s_['dur'] for s_ in intro_post))
            if intro_pre else '', self.CSO.get('total', sum(k_['dur'] for k_ in outro_keys)),
            ' (helicopter %.1f s first)' % sum(s_['dur'] for s_ in outro_pre) if outro_pre else ''))

    def ambience(self, areas):
        """areas: [(name, pos, size m (x, y, z), falloff, delay, random, 'def1,def2', inside, outside[, condition])] - the
        optional condition switches that sound off when it is false (owner 10-12: the radio static kept playing after the
        radio was cut)"""
        amb = self.nid()
        self.m.add_child(self.LOGIC, T(amb, 'Container', '%s ambience' % self.PFX, False))
        for name, pos, size, falloff, delay, rnd, defs_, inside, outside, *cond in areas:
            on = ' && '.join(c for c in [getattr(self, 'NOT_CS', '')] + [('(%s)' % c) for c in cond if c] if c)
            self.m.add_child(amb, T(self.nid(), 'AmbientArea', name, *[float(c) for c in pos], 0.0, 0.0, 0.0,
                                    *[float(c) for c in size], float(falloff), float(delay), float(rnd), defs_, inside, outside,
                                    on, 0.5, False, 0.0))

    # ------------------------------------------------------------------ 7. finish: flow, debug variants, validate, write, sounds
    def flow(self, done_msg):
        """LevelFlow (task 10) complete/failed + move it behind the HumanPlayer (crash igi2.exe+0x352e2 otherwise)"""
        m = self.m
        lf = self.L[10]
        if hasattr(self, 'CSO'):
            lf.args[10] = v(self.CSO['complete'])
        else:
            lf.args[10] = v('StatusMessage_%d.isFinishedDisplay && !HumanPlayer_0.isDead' % done_msg if done_msg else '0')
        lf.args[11] = v('StatusMessage_%d.nTicksSinceFinishedDisplay > 5 * GAME_FREQUENCY' % self.DEAD)
        m.remove(10)
        m.stmts.append(lf)
        m.stmts.append(T(self.nid(), 'MissionScoreSettings', '', 3600.0, 2700.0, 1800.0, 6.0, 3.0, 0.0, 5.0, 2.0, 0.0, 40.0, 65.0,
                         90.0, 40.0, 50.0, 60.0))
        m.stmts.append(T(self.nid(), 'LevelInfo', '', False, False, 'LOCAL:modelsused.qsc'))
        m.reindex()

    def debug_variants(self, objective_timers=(), finish=None):
        """die / win / alarm / noai / objectives / start= / rpg ; objective_timers = [(task id, arg idx, seconds)] that the
        'objectives' variant sets to 'LevelFlow_10.nTick > s' (rebased to the post-intro timer later)"""
        m = self.m
        D = self.DBG
        S = self.START
        self.burn_test_variant()                            # 10-17: 'burntest=<s>' (fires start on a timer)
        if 'chaindoor' in D and getattr(self, 'WAIT_INFO', None):   # 10-18 playthrough: Jones ON the waiting helicopter's door point (its area is only 1.8 m wide), facing it
            _w = self.WAIT_INFO; _d = np.array(_w['door'][:2], float) - np.array(_w['origin'][:2], float); _d /= np.linalg.norm(_d)
            _p = np.array(_w['door'][:2], float) + _d * 0.25 * 4096.0
            m.set(0, 3, float(_p[0])); m.set(0, 4, float(_p[1])); m.set(0, 5, float(_w['door'][2]) + 0.35 * 4096.0)
            m.set(0, 6, math.atan2(-(_w['door'][0] - _p[0]), _w['door'][1] - _p[1]))
        if 'die' in D:
            m.add_child(self.PC, T(self.nid(), 'ExplodeObject', 'DEBUG death blast', S[0], S[1], S[2] + 500, 0.0, 0.0, 0.0,
                                   'none', 'none', 100.0, 30.0, 40.0, 50.0, 0.0, 3, 3, 'LevelFlow_10.nTick > 5 * GAME_FREQUENCY', ''))
        if 'alarm' in D and hasattr(self, 'ALARM_VAR'):
            m.add_child(self.LOGIC, T(self.nid(), 'EditVariable', 'DEBUG alarm', 0.0, 0.0, 0.0, 0,
                                      'LevelFlow_10.nTick > 5 * GAME_FREQUENCY', ''))
            m.set(self.ALARM_VAR, 7, 'EditVariable_%d.nValue == 0 && LevelFlow_10.nTick > 5 * GAME_FREQUENCY' % self.ALARM_VAR)
        if 'objectives' in D:
            for tid, idx, secs in objective_timers:
                m.set(tid, idx, 'LevelFlow_10.nTick > %d * GAME_FREQUENCY' % secs)
            if finish:
                finish()
        for part in self.DEBUG.split(';'):
            if part.startswith('start='):
                c = [float(x) for x in part[6:].split(',')]
                m.set(0, 3, c[0]); m.set(0, 4, c[1]); m.set(0, 5, c[2])
                if len(c) > 3:
                    m.set(0, 6, c[3])
            if part.startswith('at='):                       # stand next to a task (an objective panel) facing it
                tid = int(part[3:])
                tp = np.array([float(m.arg(tid, k)) for k in (3, 4, 5)])
                Pn = self.NODE_P
                d = np.hypot(Pn[:, 0] - tp[0], Pn[:, 1] - tp[1])
                below = tp[2] - Pn[:, 2]                      # a panel sits 0.3-1.8 m above the floor you stand on
                d[(below < 0.3 * CS.M) | (below > 1.8 * CS.M) | (d < 0.5 * CS.M)] = np.inf   # (not on the desk top)
                sp = None
                near_ = float(os.environ.get('AT_DIST', '1.2'))   # about 1.2 m away (AT_DIST), the panel in sight
                pref = np.abs(d - near_ * CS.M)
                pref[d > (near_ + 1.0) * CS.M] = np.inf
                g_ = float(m.arg(tid, 8))                      # ... and in FRONT of it (panels are used from their front)
                fx_, fy_ = -math.sin(g_), math.cos(g_)
                front = ((Pn[:, 0] - tp[0]) * fx_ + (Pn[:, 1] - tp[1]) * fy_) / np.maximum(d, 1.0)
                if np.isfinite(np.where(front >= 0.5, pref, np.inf)).any():
                    pref[front < 0.5] = np.inf               # (MP terminals: whatever side the map lets you stand on)
                sp = self._exact_spot(tp, g_, near_)          # nav nodes are ~1-2 m apart: the exact spot first
                if sp is not None:
                    d[0] = np.hypot(*(sp[:2] - tp[:2])); kk = 0
                slack_ = 0.35 if str(m.arg(tid, 9)) != 'none' else 0.03   # (no model: nothing of its own to hit - with
                for kk in ([] if sp is not None else np.argsort(pref)[:300]):   # 0.35 m slack a node INSIDE the hollow
                    if not np.isfinite(pref[kk]):                              # container behind the tracker passed, 10-10)
                        break
                    eye = Pn[kk] + np.array([0, 0, 1.6 * CS.M])
                    v_ = tp - eye
                    if not self.blocked(eye, tp - v_ / np.linalg.norm(v_) * slack_ * CS.M, pad=(0.3 if slack_ > 0.1 else 0.01) * CS.M):
                        sp = Pn[kk]; break
                if sp is None:                                # outdoors the nav nodes are metres apart: stand on the
                    for dist_ in (float(os.environ.get('AT_DIST', '1.2')), 1.2, 1.0, 1.5):   # terrain in front of the panel
                        c_ = tp[:2] + np.array([fx_, fy_]) * dist_ * CS.M
                        gz = float(self.TERR.height(c_[0], c_[1]))
                        if np.isnan(gz) or not 0.3 * CS.M <= tp[2] - gz <= 1.8 * CS.M:
                            continue
                        eye = np.array([c_[0], c_[1], gz + 1.6 * CS.M]); v_ = tp - eye
                        if not self.blocked(eye, tp - v_ / np.linalg.norm(v_) * 0.35 * CS.M):
                            sp = np.array([c_[0], c_[1], gz]); d[0] = dist_ * CS.M; kk = 0
                            break
                if sp is None:                                # test-only last resort: nearest floor spot, no sight check
                    ok_ = np.isfinite(pref)
                    if ok_.any():
                        kk = int(np.argmin(np.where(ok_, pref, np.inf))); sp = Pn[kk]
                        print('debug: at=%d: no spot in clear sight, using the nearest floor spot' % tid)
                assert sp is not None, ('no standing spot that sees task', tid)
                kk = int(kk)
                m.set(0, 3, float(sp[0])); m.set(0, 4, float(sp[1])); m.set(0, 5, float(sp[2]) + 300.0)
                m.set(0, 6, math.atan2(-(tp[0] - sp[0]), tp[1] - sp[1]))
                print('debug: player %.1f m from task %d' % (d[kk] / CS.M, tid))
            if part.startswith('aim='):                      # stand on open ground <dist> m from a target, facing it
                tid, dist_ = part[4:].split(',')
                tid, dist_ = int(tid), float(dist_)
                tp = np.array([float(m.arg(tid, k)) for k in (3, 4, 5)])
                best_ = None
                for b_ in range(0, 360, 15):
                    c_ = tp[:2] + np.array([math.sin(math.radians(b_)), math.cos(math.radians(b_))]) * dist_ * CS.M
                    gz = float(self.TERR.height(c_[0], c_[1]))
                    if np.isnan(gz):
                        continue
                    eye = np.array([c_[0], c_[1], gz + 1.6 * CS.M])
                    if not self.blocked(eye, tp + np.array([0, 0, 1.5 * CS.M])):
                        best_ = (c_, gz); break
                assert best_, ('no clear firing position for', tid)
                (cx_, cy_), gz = best_
                m.set(0, 3, float(cx_)); m.set(0, 4, float(cy_)); m.set(0, 5, gz + 300.0)
                m.set(0, 6, math.atan2(-(tp[0] - cx_), tp[1] - cy_))
                print('debug: player %.0f m from task %d, facing it' % (dist_, tid))
            if part.startswith('door='):                     # stand 1.5 m in front of a door leaf, facing it
                tid = int(part[5:])
                tp = np.array([float(m.arg(tid, k)) for k in (3, 4, 5)])
                g_ = float(m.arg(tid, 11))
                import mef                                    # the door origin is its HINGE: face the leaf centre
                fz_ = float(tp[2])                            # the door's own floor (before the leaf-centre shift)
                ms_ = mef.ModelLib(self.MODEL_RES).collision(str(m.arg(tid, 12)))
                if ms_ and sum(len(q[0]) for q in ms_):
                    V_ = np.vstack([q[0] for q in ms_ if len(q[0])])
                    tp = tp + navgen.rot(*[float(m.arg(tid, k)) for k in (9, 10, 11)]) @ ((V_.min(0) + V_.max(0)) / 2)
                Pn = self.NODE_P
                best_ = None
                for sgn in (1, -1):
                    for ang in (g_, g_ + math.pi / 2):
                        c_ = tp[:2] + sgn * np.array([-math.sin(ang), math.cos(ang)]) * 1.5 * CS.M
                        d_ = np.hypot(Pn[:, 0] - c_[0], Pn[:, 1] - c_[1]) + 3 * np.abs(Pn[:, 2] - fz_)
                        k_ = int(np.argmin(d_))
                        if best_ is None or d_[k_] < best_[0]:
                            best_ = (d_[k_], Pn[k_])
                sp = best_[1]
                m.set(0, 3, float(sp[0])); m.set(0, 4, float(sp[1])); m.set(0, 5, float(sp[2]) + 300.0)
                m.set(0, 6, math.atan2(-(tp[0] - sp[0]), tp[1] - sp[1]))
                self.msg('DBG_DOOR', 'DEBUG door open', 'Door_%d.nDoorOpenTicks > 0' % tid, 'DEBUG: DOOR %d IS OPEN' % tid, 30.0)
                print('debug: player %.1f m from door %d' % (math.hypot(sp[0] - tp[0], sp[1] - tp[1]) / CS.M, tid))
            if part == 'rpg':
                m.set(0, 9, 'Human_AddWeapon("WEAPON_ID_RPG7"),\nHuman_AddAmmo("AMMO_ID_RPG7CLIP", 8);')
            if part.startswith('walkto='):                   # stand ~2 m from a pickup item, facing it (walk in + E)
                tid = int(part[7:])
                tp = np.array([float(m.arg(tid, k)) for k in (3, 4, 5)])
                Pn = self.NODE_P
                d = np.hypot(Pn[:, 0] - tp[0], Pn[:, 1] - tp[1])
                ok = (d > 1.6 * CS.M) & (d < 3.0 * CS.M) & (np.abs(Pn[:, 2] - tp[2]) < 0.8 * CS.M)
                sp = None
                for kk in np.argsort(np.where(ok, d, np.inf))[:80]:
                    if ok[kk] and not self.blocked(Pn[kk] + np.array([0, 0, 1.0 * CS.M]), tp + np.array([0, 0, 0.5 * CS.M])):
                        sp = Pn[kk]; break
                for b_ in (range(0, 360, 30) if sp is None else ()):   # outdoors the nav nodes are sparse: terrain
                    c_ = tp[:2] + np.array([math.sin(math.radians(b_)), math.cos(math.radians(b_))]) * 2.2 * CS.M
                    gz = float(self.TERR.height(c_[0], c_[1]))
                    if not np.isnan(gz) and abs(gz - tp[2]) < 0.8 * CS.M and not self.blocked(
                            np.array([c_[0], c_[1], gz + 1.0 * CS.M]), tp + np.array([0, 0, 0.5 * CS.M])):
                        sp = np.array([c_[0], c_[1], gz]); break
                assert sp is not None, ('no spot to walk to item', tid)
                m.set(0, 3, float(sp[0])); m.set(0, 4, float(sp[1])); m.set(0, 5, float(sp[2]) + 300.0)
                m.set(0, 6, math.atan2(-(tp[0] - sp[0]), tp[1] - sp[1]))
                self.msg('DBG_PICK', 'DEBUG picked', 'GenericPickup_%d.isPickedUp' % tid, 'DEBUG: PICKED UP %d' % tid, 30.0)
                print('debug: player %.1f m from item %d' % (math.hypot(*(sp[:2] - tp[:2])) / CS.M, tid))
        if 'noenemies' in D:                                  # tests that must not be shot at: every squad off
            m.set(self.SQ_PARENT, 3, '0') if lit(self.L[self.SQ_PARENT].args[1]) == 'ConditionalContainer' else None
        for part in self.DEBUG.split(';'):
            if part.startswith('watch='):                    # a DEBUG message once that item is taken
                wid = int(part[6:])
                self.msg('DBG_WATCH', 'DEBUG watched pickup', 'GenericPickup_%d.isPickedUp' % wid, 'DEBUG: PICKED UP %d' % wid, 30.0)
            if part.startswith('bring='):                    # those pickup items at Jones's feet (test: take -> plant)
                ps = [float(m.arg(0, k)) for k in (3, 4, 5)]
                for j_, pid in enumerate(int(x) for x in part[6:].split(',')):
                    m.set(pid, 3, ps[0] + 0.15 * CS.M * (j_ + 1)); m.set(pid, 4, ps[1]); m.set(pid, 5, ps[2] - 200.0)
                print('debug: items %s at the player' % part[6:])
        if 'killtest' in D and getattr(self, 'MIDS', None):      # do enemies killed before a mid cutscene stay dead after it?
            sid, hids = next(iter(self.SQUADS.values()))
            vic = hids[0]
            vp = [float(m.arg(vic, k)) for k in (3, 4, 5)]
            m.add_child(self.LOGIC, T(self.nid(), 'ExplodeObject', 'DEBUG kill victim', vp[0], vp[1], vp[2] + 1000, 0.0, 0.0, 0.0,
                                      'none', 'none', 1e6, 5.0, 3.0, 100.0, 0.0, 2, 2, 'LevelFlow_10.nTick > 3 * GAME_FREQUENCY', ''))
            latch = self.nid()
            m.add_child(self.LOGIC, T(latch, 'EditVariable', 'DEBUG victim died', 0.0, 0.0, 0.0, 0,
                                      'EditVariable_%d.nValue == 0 && HumanSoldier_%d.isDead' % (latch, vic), ''))
            cs = self.MIDS[0]['cs']
            self.msg('DBG_KILL1', 'DEBUG victim dead', 'EditVariable_%d.nValue == 1' % latch, 'DEBUG: VICTIM %d KILLED' % vic, 6.0)
            self.msg('DBG_KILL2', 'DEBUG still dead', 'CutScene_%d.isFinished && EditVariable_%d.nValue == 1 && HumanSoldier_%d.isDead'
                     % (cs, latch, vic), 'KILLTEST STILL DEAD %d' % vic, 30.0)
            self.msg('DBG_KILL3', 'DEBUG alive again', 'CutScene_%d.isFinished && EditVariable_%d.nValue == 1 && !HumanSoldier_%d.isDead'
                     % (cs, latch, vic), 'KILLTEST ALIVE AGAIN %d' % vic, 30.0)
            print('debug: killtest victim %d at %s' % (vic, [round(c / CS.M) for c in vp]))
        if 'noai' in D:                                  # every squad goes, except one whose soldier an objective needs
            need = set()
            for t_, d_, p_ in tasks(m.stmts):
                for a_ in t_.args:
                    if isinstance(a_, Str):
                        need |= {int(x) for x in re.findall(r'HumanSoldier_(\d+)\.', str(a_))}
            gone = 0
            for sid_, (squad_id, hids_) in list(self.SQUADS.items()):
                if not need & set(hids_) and squad_id in m.byid:
                    m.remove(squad_id); gone += 1
            print('debug: %d squads removed (kept the ones an objective needs)' % gone)
        if self.DEBUG:
            print('*** TEST BUILD (%s) - do not ship ***' % self.DEBUG)

    def rebase_timers(self):
        """LevelFlow_10.nTick counts the intro too: game-time conditions use the timer that starts when it ends"""
        if not hasattr(self, 'CSI'):
            return
        for t_, d_, p_ in tasks(self.m.stmts):
            for k_, a_ in enumerate(t_.args):
                if isinstance(a_, Str) and 'LevelFlow_10.nTick' in a_:
                    t_.args[k_] = v(str(a_).replace('LevelFlow_10.nTick', 'LevelTimer_%d.nTick' % self.CSI['after']))

    def validate(self):
        m = self.m
        problems = m.validate()
        REFX = re.compile(r'\b[A-Z][A-Za-z0-9]+(?:_[A-Z][A-Za-z0-9]+)*_\d+\.')
        for t, d, p in tasks(m.stmts):
            if lit(t.args[1]) == 'Door':
                for k in (18, 19, 20):
                    e = str(lit(t.args[k])).strip()
                    if e not in ('', '0', '1') and not REFX.search(e) and 'HumanPlayer' not in e and 'this.' not in e:   # (10-24: Mission 1's gate '!this.isOpen')
                        problems.append('door %s arg %d is a constant rule %r (a removed reference?)' % (lit(t.args[0]), k, e[:50]))
        for t, d, p in tasks(m.stmts):
            ty = lit(t.args[1])
            if ty in MP_ONLY_TYPES and not (ty == 'AIStationaryGunHolder' and str(lit(t.args[2])).endswith('[SP]')):   # (11-08 additive: an SP gunship
                problems.append('multiplayer-only task left: %s %s' % (lit(t.args[0]), ty))                                 #  cloned from L17 opts in by name)
            for a in t.args:
                if isinstance(a, Str) and MP_REF.search(a):
                    problems.append('multiplayer reference left in task %s: %s' % (lit(t.args[0]), a[:60]))
        if problems:
            print('VALIDATION FAILED:'); [print('  -', p) for p in problems[:60]]
            sys.exit(1)

    def write(self, sprite, common_location, voice_src_banks=(), extra_samples=()):
        """objects/mission qvm + ai + graphs + text, then the sound banks:
        level bank = the MP map's own sounds + our voice-over + `extra_samples` [(bank path, basename prefix, volume)];
        common bank = MISSIONS/<common_location>/common sounds (guard voices in that language)."""
        self.rebase_timers()
        _ed = os.path.join(ROOT, 'work', 'edits', '%s.json' % self.FOLDER)     # (10-31 additive: igi2ed edits survive rebuilds,
        if os.path.exists(_ed) and os.environ.get('EDSYNC', '1') != '0':      #  tools/edsync.py + work/igi2ed/HOWTO.md; EDSYNC=0 = off)
            import edsync                                                     # (after rebase_timers: edits are diffed against built output)
            edsync.apply(self.m.stmts, _ed, 'edsync work/edits/%s.json' % self.FOLDER)
            self.m.reindex()
        self.validate()
        out = os.path.join(ROOT, 'build', os.environ.get('SPKIT_BUILD') or (self.FOLDER.replace('_sp', '') + ('_TEST' if self.DEBUG else '')))   # (SPKIT_BUILD: parallel test variants)
        self.m.write(out, self.ID, self.FOLDER, sprite, debug=bool(self.DEBUG), own_common='common')
        if self.GRAPHS and os.environ.get('SPKIT_GRAPHCOVER', '1') != '0':      # (11-02 default: cover data for every graph, else
            import graphcover                                                   #  guards never take cover - tools/graphcover.py)
            for _gid, _nodes in sorted(self.GRAPHS.items()):
                _gc = os.path.join(out, 'graphs', 'graphcover%d.dat' % _gid)
                if os.path.exists(os.path.join(out, 'graphs', 'graph%d.dat' % _gid)) and not os.path.exists(_gc):
                    _data, _n = graphcover.build(self._tris()[0], [(q_['id'], q_['pos']) for q_ in _nodes])
                    open(_gc, 'wb').write(_data)
                    print('graphcover %d: %d of %d nodes are cover' % (_gid, _n, len(_nodes)))
        _lm =os.path.join(ROOT, 'work', 'edits', '%s_lightmaps' % self.FOLDER)   # (10-31 additive: igi2ed-baked .olm lightmaps,
        _lr = os.path.join(out, 'overlay', 'lightmaps', 'lightmaps.res')           #  tools/edlight.py; same task ids + models only)
        if os.path.isdir(_lm) and os.path.exists(_lr) and os.environ.get('EDSYNC', '1') != '0':
            import edlight
            edlight.merge(_lr, _lm)
        G_APP = GAME
        MPS = os.path.join(G_APP, 'MISSIONS', 'multiplayer', self.mp_map, 'sounds')
        LEVEL_SND = 'LOCAL:missions/multiplayer/%s/sounds' % self.FOLDER
        extra, defs, seen = [], [], set()
        for name, (path, secs) in sorted(self.VO.items()):
            extra.append((name + '.wav', sb.riff_to_ilsf(open(path, 'rb').read(), flags=0x1001)))
            defs.append('DefineSound("%s", "%s", 0, 0, 0, 1, 2.0, 1e+02, -1, -1, -1, -1, FALSE)' % (name, name))
            seen.add(name.lower())
        own = {n.rsplit('/', 1)[1].rsplit('.', 1)[0].lower() for n, _ in sb.read_bank(os.path.join(MPS, 'sounds.res'))[1]}
        for bank, prefixes, vol, *src_qvm in extra_samples:
            orig = {}                                        # (bank, prefixes, vol, sounds.qvm): keep the original
            if src_qvm:                                      # DefineSound lines (loop flag, range) of those samples
                _v, st_ = igiqvm.decompile(open(src_qvm[0], 'rb').read())
                for grp in st_:
                    for d_ in (grp.args if isinstance(grp, Call) else []):
                        if isinstance(d_, Call) and d_.name == 'DefineSound':
                            orig[str(lit(d_.args[1])).lower()] = d_
            for n_, b_ in sb.read_bank(bank)[1]:
                bn = n_.rsplit('/', 1)[1]
                stem = bn.rsplit('.', 1)[0]
                if any(stem.lower().startswith(p_) for p_ in prefixes) and stem.lower() not in seen and stem.lower() not in own:
                    extra.append((bn, b_)); seen.add(stem.lower())
                    if stem.lower() in orig:
                        defs.append(igiqvm.stmts_to_qsc([orig[stem.lower()]]).strip().rstrip(';'))
                    else:
                        defs.append('DefineSound("%s", "%s", 0, 0, 0, %s, 1e+01, 1e+02, -1, -1, -1, -1, FALSE)' % (stem, stem, vol))
        os.makedirs(os.path.join(out, 'sounds'))
        open(os.path.join(out, 'sounds', 'sounds.res'), 'wb').write(sb.rebase_bank(os.path.join(MPS, 'sounds.res'), LEVEL_SND, add=extra))
        sver, sst = igiqvm.decompile(open(os.path.join(MPS, 'sounds.qvm'), 'rb').read())
        sqsc = igiqvm.stmts_to_qsc(sst)
        defs += list(getattr(self, 'EXTRA_DEFS', ()))            # (a builder's own DefineSound lines, e.g. vehicles on COMMON samples)
        if defs:
            sqsc += '\nDefineGroup(\n    "%s VOICE AND AMBIENCE",\n    ' % self.PFX + ',\n    '.join(defs) + '\n);\n'
        open(os.path.join(out, 'sounds', 'sounds.qvm'), 'wb').write(igiqvm.compile_stmts(igiqvm.parse_qsc(sqsc), sver))
        assert not sb.check_bank(os.path.join(out, 'sounds', 'sounds.res'), LEVEL_SND)[2]
        LC = os.path.join(G_APP, 'MISSIONS', common_location, 'common', 'sounds')
        COMMON_SND = 'LOCAL:missions/multiplayer/%s/common/sounds' % self.FOLDER
        os.makedirs(os.path.join(out, 'common', 'sounds'))
        open(os.path.join(out, 'common', 'sounds', 'sounds.res'), 'wb').write(
            sb.rebase_bank(os.path.join(LC, 'sounds.res'), COMMON_SND, strict=False))
        shutil.copy2(os.path.join(LC, 'sounds.qvm'), os.path.join(out, 'common', 'sounds', 'sounds.qvm'))
        assert not sb.check_bank(os.path.join(out, 'common', 'sounds', 'sounds.res'), COMMON_SND)[2]
        self.out = out
        print('sound banks: level %d KB (%d voice lines, %d extra samples), common %d KB from %s' % (
            os.path.getsize(os.path.join(out, 'sounds', 'sounds.res')) // 1024, len(self.VO), len(extra) - len(self.VO),
            os.path.getsize(os.path.join(out, 'common', 'sounds', 'sounds.res')) // 1024, common_location))
        print('%s built: mission %d | enemies %d | graphs %s -> %s' % (self.title, self.ID, self.ENEMIES,
                                                                    {g: len(n) for g, n in self.GRAPHS.items()}, out))
        return out


def cctv(p0, l0, p1, l1, dur, fov0=0.9, fov1=0.7):
    """'we hacked their security camera': monochrome green-grey picture with heavy noise and a slow servo pan/zoom,
    framed by quick black flickers (the feed connecting). CAMERAFILTER_TYPE_BAND multiplies the picture by (r, g, b)."""
    tint = (0.55, 0.8, 0.55)
    return [CS.key(p0, l0, 0.25, False, filt=CS.BAND, color=(0.0, 0.0, 0.0), noise=1.0, fov=fov0),
            CS.key(p0, l0, 0.15, False, filt=CS.BAND, color=tint, noise=1.0, fov=fov0),
            CS.key(p0, l0, 0.10, False, filt=CS.BAND, color=(0.1, 0.12, 0.1), noise=1.0, fov=fov0),
            CS.key(p0, l0, max(0.5, dur - 0.5), True, filt=CS.BAND, color=tint, noise=0.85, fov=fov0, shake=0.02),
            CS.key(p1, l1, 0.0, False, filt=CS.BAND, color=tint, noise=0.85, fov=fov1, shake=0.02)]
