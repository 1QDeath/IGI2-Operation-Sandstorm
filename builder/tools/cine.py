"""cine - the owner's round-3 cutscenes (10-10) for spkit missions:

  * HALO drop intro, lifted from the very first mission of the game (Mission 11, location1/level1 'Intro Cutscene'):
    the C-130 flies over, Jones jumps from the cargo bay, free fall, ripcord - then the mission's own briefing tour -
    then Jones glides down under his canopy and kneels by the parachute at his start position.
  * helicopter extraction outro (Mission 16 'Quest and Jones in chopper' pattern): the friendly helicopter 710_01_1
    comes in low over the extraction point, Jones waves it down, the inside shot as it lifts off, then the mission's
    own outro tour as the view from the helicopter.

Original shots are copied task by task (ids renumbered, every ObjectPos moved by one offset, internal references -
spline guide -> path / rigid object, camera link / target, CutScene_N in expressions - remapped); their models are
merged into the mission bank with prefabs.Transplant.models() before Transplant.finish().

    C = cine.Cine(K, X)          # before X.finish(): registers the models
    ...                          # after K.navigate() (cutscene props must not become nav obstacles)
    pre, post = C.halo(skin)     # shot lists for Kit.cutscenes(intro_pre=pre, intro_post=post)
    heli = C.heli(lz, skin)      # for Kit.cutscenes(outro_pre=heli)
"""
import copy, math, os, re
import numpy as np
from igiqvm import Call, Str, Int
from mission_lib import T, v, GAME
from qast import load, tasks, lit
import cutscene as CS
import atmos

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G_ = GAME.replace('\\', '/') + '/MISSIONS/'
M = CS.M
L11, L16 = 'location1/level1', 'location1/LEVEL6'
L11_MODELS = ['700_03_1', '700_04_1', 'c-130bay', 'c-130door', 'lot', 'chutehandle', 'halochuteground', 'w_chute']
L16_MODELS = ['710_01_1', '710_04_1', '710_05_1']
L11_LAND = np.array([845179.4, 1994732.4, 13096.264])         # 'Jones after landing' EditBoneObj 3096 (kneels by the chute)
L11_LAND_GAMMA = 3.383252
FLYBY_M = float(os.environ.get('CINE_FLYBY_M', '420'))               # fly-by height over the landing spot (m)
HANG_DZ = float(os.environ.get('CINE_HANG_DZ', '0.9'))
APPROACH_SECS = 3200 / 4096.0                       # parachute_approach: one 0.78 s clip (COMMON/new.res)
APPROACH_ROOT = (np.array([0.0, -6.06, 4.52]), np.array([0.0, -0.39, 1.50]))   # its pelvis at start / end, actor frame (m)                # Jones' feet below the w_chute origin (m)
# the HALO shots kept from Mission 11 (container -> its CutScene): fly-by, inside the bay (jump), free fall, ripcord
HALO_SHOTS = [(3062, 3049), (3077, 1111), (3109, 3102), (3403, 3401)]
SOUNDS = [(G_ + 'location1/level1/sounds/sounds.res', ('cs11_herc', 'cs11_wind', 'cs11_jonesby', 'cs11_chute', 'cs11_distant', 'cs11_gate'), 0.7,
           G_ + 'location1/level1/sounds/sounds.qvm'),
          (G_ + 'location1/LEVEL6/sounds/sounds.res', ('cs16_heli',), 1.0, G_ + 'location1/LEVEL6/sounds/sounds.qvm')]
REF = re.compile(r'\b([A-Z][A-Za-z0-9]+)_(\d+)\b')


def _decls(st):
    d = {}
    for s in st:
        if isinstance(s, Call) and s.name == 'Task_DeclareParameters':
            a = [lit(x) for x in s.args]
            d[a[0]] = list(zip(a[1::2], a[2::2]))
    return d


class Source:
    _cache = {}

    def __new__(cls, rel):
        if rel not in cls._cache:
            o = super().__new__(cls)
            o.st = load(os.path.join(ROOT, 'work', 'decomp', '%s_objects.qsc' % rel.replace('/', '_')))
            o.byid = {lit(t.args[0]): t for t, d, p in tasks(o.st)}
            o.decl = _decls(o.st)
            cls._cache[rel] = o
        return cls._cache[rel]

    def has_pos(self, typ):
        d = self.decl.get(typ)
        return bool(d) and d[0][1] == 'ObjectPos'


class Cine:
    def __init__(self, K, X):
        self.K, self.m = K, K.m
        X.models(L11, L11_MODELS)
        X.models(L16, L16_MODELS)
        for typ in ('CutScene', 'EditCamera', 'Smoke', 'EditBoneObj', 'EditRigidObj', 'RotateAttachment', 'SplinePathDynCubeObj',
                    'SplinePathNodeQTask', 'SplinePathGuideQTask', 'SequenceCommand', 'ConditionalContainer', 'AmbientArea',
                    'StatusMessage'):
            atmos.ensure_decl(self.m, typ)

    # ------------------------------------------------------------------ copying original tasks
    def clone(self, rel, root_ids, offset, skin=None, yaw=0.0, pivot=None, drop=('LightmapInfo',)):
        """deep copies of the subtrees root_ids of level rel: new ids, every position p -> R(yaw) (p - pivot) + pivot
        + offset, yaws + yaw, references remapped, camera 'time of day' -> default, Jones -> `skin`.
        -> (list of copies, {old id: new id})"""
        S = Source(rel)
        old = []

        def collect(t):
            if lit(t.args[1]) in drop:
                return
            old.append(lit(t.args[0]))
            for a in t.args:
                if isinstance(a, Call) and a.name == 'Task_New':
                    collect(a)
        for r in root_ids:
            collect(S.byid[r])
        idmap = {i: self.K.nid() for i in old}
        off = np.asarray(offset, float)
        piv = np.zeros(3) if pivot is None else np.asarray(pivot, float)
        c_, s_ = math.cos(yaw), math.sin(yaw)
        R = np.array([[c_, -s_, 0], [s_, c_, 0], [0, 0, 1.0]])

        def fix(t):
            typ = lit(t.args[1])
            t.args[0] = Int(idmap[lit(t.args[0])])
            t.args = [a for a in t.args if not (isinstance(a, Call) and a.name == 'Task_New' and lit(a.args[1]) in drop)]
            if S.has_pos(typ):
                p = np.array([float(lit(t.args[3 + k])) for k in range(3)])
                q = R @ (p - piv) + piv + off
                for k in range(3):
                    t.args[3 + k] = v(float(q[k]))
                if yaw and typ in ('EditRigidObj', 'EditBoneObj', 'SplinePathNodeQTask'):
                    t.args[8] = v(float(lit(t.args[8])) + yaw)
                if yaw and typ == 'EditCamera':
                    t.args[8] = v(float(lit(t.args[8])) + yaw)
                if yaw and typ == 'Smoke':                         # (args 6 Alpha, 7 Gamma: the emission direction)
                    t.args[7] = v(float(lit(t.args[7])) + yaw)
                if yaw and typ == 'SplinePathNodeQTask':           # tangent = a direction: rotate only
                    tg = np.array([float(lit(t.args[12 + k])) for k in range(3)])
                    tg = R @ tg
                    for k in range(3):
                        t.args[12 + k] = v(float(tg[k]))
            if typ == 'SplinePathGuideQTask':
                for k in (3, 4):
                    t.args[k] = Int(idmap.get(int(lit(t.args[k])), int(lit(t.args[k]))))
            if typ == 'EditCamera':
                for k in (11, 13):
                    x = int(lit(t.args[k]))
                    t.args[k] = Int(idmap.get(x, x) if x >= 0 else -1)
                t.args[16] = v(-1.0)                               # Mission 11's light keyframes do not exist here
            if typ == 'EditBoneObj' and skin and str(lit(t.args[11])).startswith('jones'):     # (arg 11 = Model)
                t.args[11] = v(skin)
            if typ == 'EditBoneObj':                           # (arg 13 = WeaponModel: Mission 16's 101_01_1 / 110_01_1 are
                t.args[13] = v('')                             #  not in our banks -> the whole actor was invisible, test 10-10)
            if typ == 'StatusMessage':
                t.args[-1] = v('')                                 # (morph ids: lip sync of the original actors)
            for k, a in enumerate(t.args):
                if isinstance(a, Str) and REF.search(a):
                    t.args[k] = v(REF.sub(lambda mm: '%s_%d' % (mm.group(1), idmap[int(mm.group(2))])
                                          if int(mm.group(2)) in idmap else mm.group(0), str(a)))
            for a in t.args:
                if isinstance(a, Call) and a.name == 'Task_New':
                    fix(a)
        out = []
        for r in root_ids:
            t2 = copy.deepcopy(S.byid[r])
            fix(t2)
            out.append(t2)
        return out, idmap

    # ------------------------------------------------------------------ helpers
    def _ground(self, x, y):
        h = float(self.K.TERR.height(x, y))
        return None if np.isnan(h) else h

    def _clear_above(self, tasks_, margin_m):
        """how far (units) these tasks' positions must go up to stay margin_m above the terrain"""
        need = 0.0
        for t in tasks_:
            for tt, d, p in tasks([t]):
                typ = lit(tt.args[1])
                if typ in ('EditCamera', 'EditRigidObj', 'EditBoneObj', 'SplinePathNodeQTask'):
                    x, y, z = (float(lit(tt.args[3 + k])) for k in range(3))
                    g = self._ground(x, y)
                    if g is not None:
                        need = max(need, g + margin_m * M - z)
        return need

    @staticmethod
    def _shift(tasks_, dz):
        for t in tasks_:
            for tt, d, p in tasks([t]):
                if lit(tt.args[1]) in ('EditCamera', 'EditRigidObj', 'EditBoneObj', 'SplinePathNodeQTask', 'Smoke', 'CutScene',
                                       'StatusMessage', 'AmbientArea'):
                    tt.args[5] = v(float(lit(tt.args[5])) + dz)

    def spline(self, rigid_id, pts, speeds_kmh, gammas, free=True, name='SplinePath', run_from_start=False):
        """a SplinePathDynCubeObj + guide that moves rigid_id through pts (world units) at speeds_kmh -> [tasks]"""
        path, guide = self.K.nid(), self.K.nid()
        nodes, t_ = [], 0.0
        for k, p in enumerate(pts):
            if k:
                d = math.dist(pts[k - 1], p) / M
                t_ += d / (0.5 * (speeds_kmh[k - 1] + speeds_kmh[k]) / 3.6)
            nxt = pts[min(k + 1, len(pts) - 1)]
            prv = pts[max(k - 1, 0)]
            tg = np.array(nxt, float) - np.array(prv, float)
            nodes.append(T(self.K.nid(), 'SplinePathNodeQTask', '', *[float(c) for c in p], 0.0, 0.0, float(gammas[k]), bool(free),
                           float(speeds_kmh[k]), float(round(t_, 6)), *[float(c) for c in tg], True))
        return [T(self.K.nid(), 'Container', name, False, children=[
            T(path, 'SplinePathDynCubeObj', '', False, children=nodes),
            T(guide, 'SplinePathGuideQTask', '', path, rigid_id, False, bool(run_from_start), 0.0, children=[
                T(self.K.nid(), 'SequenceCommand', '', '1', 'SplinePathGuide_SetRunning (TRUE);', '', '')])])], t_

    def cs(self, keys, name=''):
        return CS.cutscene(self.K.nid, keys, name)

    def say(self, cs_id, at, vdef, text, who='David'):
        """a voiced caption at `at` s into CutScene cs_id -> (StatusMessage task, text key)"""
        name, secs = self.K.vo(vdef, text, who)
        key = vdef.upper()
        self.m.add_text('messages', key, text)
        return CS.caption(self.K.nid, cs_id, at, key, secs=secs + 0.3, sound=name)

    def sfx(self, cs_id, at, sound, secs=3.0):
        return T(self.K.nid(), 'StatusMessage', 'sfx ' + sound, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                 'CutScene_%d.nTick > %s * GAME_FREQUENCY' % (cs_id, at), '', '', sound, True, True, float(secs), '')

    # ------------------------------------------------------------------ the HALO drop
    def halo(self, skin, land=None, gamma=None, lines=None):
        """-> (pre shots, post shots); a shot = dict(cs=<CutScene id>, tasks=[tasks for its container], dur=seconds).
        land/gamma = where Jones touches down (default: the player's start). lines = (pilot line 1, pilot line 2)."""
        K = self.K
        land = np.array(land if land is not None else K.START, float)
        land[2] = self._land_z(land)
        gamma = K.GAMMA if gamma is None else gamma
        off = land - L11_LAND
        yaw = self._halo_yaw(off)
        pre = []
        for cont, cs_id in HALO_SHOTS:
            src = Source(L11).byid[cont]
            kids = [lit(a.args[0]) for a in src.args if isinstance(a, Call) and a.name == 'Task_New']
            got, idmap = self.clone(L11, kids, off, skin=skin, yaw=yaw, pivot=L11_LAND)
            if cont in (3062, 3077):                           # the fly-by (14.5 km up) + inside the Hercules (4.6 km): on these
                zs = [float(lit(t.args[5])) for t, d, p in tasks(got)   # small maps shows the whole map and the void
                      if lit(t.args[1]) in ('EditCamera', 'EditRigidObj', 'SplinePathNodeQTask')]   # past its edge (owner
                self._shift(got, land[2] + FLYBY_M * M - max(zs))                            # 10-11): down over the drop zone
            if cont in (3109, 3403):                           # free fall (~1 km) + ripcord (~670 m) showed the map's edge too
                self._shift(got, -{3109: float(os.environ.get('CINE_FALL_DZ', '600')), 3403: float(os.environ.get('CINE_RIP_DZ', '300'))}[cont] * M)   # (owner 10-11) - as low as the terrain lets them
                #  (10-31 additive: CINE_FALL_DZ / CINE_RIP_DZ env - Joyride: cameras 350-600 m up flicker (0.1 m near plane); defaults unchanged)
            up_ = self._clear_above(got, 25.0 if cont not in (3062, 3077) else 60.0)
            if up_ > 0:
                self._shift(got, up_)
            dur = sum(float(lit(c.args[10])) for c in [x for x in got if lit(x.args[0]) == idmap[cs_id]][0].args
                      if isinstance(c, Call) and lit(c.args[1]) == 'EditCamera')
            pre.append(dict(cs=idmap[cs_id], tasks=got, dur=dur, name=str(lit(src.args[2])), raised_m=up_ / M))
        l1, l2 = lines or ('PILOT: Two minutes to the drop zone. Wind is calm. Good luck, Jones.', 'PILOT: Green light! Go, go, go!')
        pre[0]['tasks'].append(self.say(pre[0]['cs'], 0.6, K.vp + 'halo1', l1))
        pre[1]['tasks'].append(self.say(pre[1]['cs'], 2.5, K.vp + 'halo2', l2))
        return pre, self._touchdown(land, gamma, skin)

    def _halo_yaw(self, off):
        """turn the whole drop about the landing spot so that what the low shots look down on (free fall 1 km up,
        ripcord) lies over this map's terrain, not over the void past its edge"""
        S = Source(L11)
        pts = []
        for cont, cs_id in [HALO_SHOTS[0]] + HALO_SHOTS[2:]:      # (+ the fly-by: it is low now, keep it over the map)
            for t, d, p in tasks([S.byid[cont]]):
                if lit(t.args[1]) in ('EditCamera', 'EditRigidObj', 'SplinePathNodeQTask', 'EditBoneObj'):
                    pts.append(np.array([float(lit(t.args[3 + k])) for k in range(3)]))
        best = None
        for deg in range(0, 360, 15):
            a = math.radians(deg)
            R = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1.0]])
            bad = 0
            for p in pts:
                q = R @ (p - L11_LAND) + L11_LAND + off
                if self._ground(q[0], q[1]) is None:
                    bad += 1
            if best is None or bad < best[0]:
                best = (bad, a)
            if bad == 0:
                break
        self.HALO_YAW = best
        return best[1]

    def _land_z(self, p):
        """the floor under the start position (navgen nodes / terrain)"""
        K = self.K
        Pn = K.NODE_P
        d = np.hypot(Pn[:, 0] - p[0], Pn[:, 1] - p[1])
        ok = (d < 2.5 * M) & (Pn[:, 2] < p[2] + 1.0 * M) & (Pn[:, 2] > p[2] - 3.0 * M)
        g = self._ground(p[0], p[1])
        if ok.any():
            z = float(Pn[np.argmin(np.where(ok, d, np.inf)), 2])
            return max(z, g) if g is not None and abs(z - g) < 1.0 * M else z
        return g if g is not None else float(p[2]) - 300.0

    def _touchdown(self, land, gamma, skin):
        K = self.K
        shots = []
        # 1. the glide: Jones under the canopy (w_chute) comes down a straight line onto the start position
        end = land + np.array([0, 0, 1.6 * M])                     # (w_chute: his boots 0.9 m below its origin)
        best = None
        for b in list(range(0, 360, 20)):
            # come in from behind the landing direction first (he lands facing his start yaw)
            pref = abs(((b - (-math.degrees(gamma) + 180)) + 180) % 360 - 180)   # (bearing (sin b, cos b); facing gamma = bearing -gamma)
            for dist_m, h_m in ((55, 30), (45, 24), (35, 18)):
                st = end + np.array([math.sin(math.radians(b)) * dist_m * M, math.cos(math.radians(b)) * dist_m * M, h_m * M])
                if K.blocked(st, end, pad=0.5 * M):
                    continue
                score = pref + (55 - dist_m)
                if best is None or score < best[0]:
                    best = (score, st)
                break
        assert best, 'no clear glide path down to the start'
        st = best[1]
        travel = math.atan2(-(end[0] - st[0]), end[1] - st[1])
        glider = K.nid()
        # owner 10-11 (2nd report): 'it duplicates the parachute and keeps lagging back'. w_chute (straps + pack ->
        # canopy) AND the parachute_approach animation (its own pack -> canopy) each brought a canopy, and the 0.78 s
        # clip looped: its pelvis travels 6 m forward / 3 m down per cycle, so Jones snapped back 6 m 1.3x a second.
        # Mission 11's own rig for a man on a spline: the invisible carrier 'lot' + the actor as its child. The clip
        # plays ONCE, stretched over the glide, and the carrier is offset so that his pelvis goes st -> end.
        cg, sg = math.cos(travel), math.sin(travel)
        R_ = lambda r: np.array([r[0] * cg - r[1] * sg, r[0] * sg + r[1] * cg, r[2]]) * M
        c0, c1 = st - R_(APPROACH_ROOT[0]), end - R_(APPROACH_ROOT[1])
        sp, secs = self.spline(glider, [tuple(c0), tuple((c0 + c1) / 2 + np.array([0, 0, -2 * M])), tuple(c1)],
                               [30.0, 26.0, 18.0], [travel] * 3, name='HALO glide path')
        hang = T(K.nid(), 'EditBoneObj', 'Jones under the canopy', *[float(c) for c in c0], 0.0, 0.0, float(travel),
                 False, True, skin, True, '', '', 'parachute_approach', float(APPROACH_SECS / max(secs, 1.0)), 0.0)
        rig = T(glider, 'EditRigidObj', 'HALO carrier', *[float(c) for c in c0], 0.0, 0.0, float(travel), 'lot', 5, False, False,
                children=[hang])
        dur = max(4.0, secs - 0.4)
        mid = (st + end) / 2
        cam, _ = K.frame(tuple(land + np.array([0, 0, 6 * M])), dist_m=(10, 18), height_m=(1.0, 3.0),
                         prefer=(math.degrees(travel) + 90) % 360)
        keys = [dict(CS.key(cam, tuple(st), dur, True, fov=0.75), target_id=glider),
                dict(CS.key(cam, tuple(end), 0.0, False, fov=0.95), target_id=glider)]
        cs_id, cs_t = self.cs(keys, 'HALO glide')
        shots.append(dict(cs=cs_id, tasks=[rig] + sp + [cs_t, self.sfx(cs_id, 0.2, 'cs11_chute_open', 4.0)], dur=dur, name='HALO glide'))   # (no loop def from a message: it might never stop)
        # 2. on the ground: kneeling by the parachute (Mission 11 'Jones after landing', laid out around him)
        rel = lambda v_, g0: np.array([v_[0] * math.cos(g0) - v_[1] * math.sin(g0), v_[0] * math.sin(g0) + v_[1] * math.cos(g0), v_[2]])
        rot = gamma - L11_LAND_GAMMA
        jones = K.nid()
        man = T(jones, 'EditBoneObj', 'Jones landed', *[float(c) for c in land], 0.0, 0.0, float(gamma), False, True, skin, True, '', '',
                'kneeling_by_parachute', 1.0, 0.0)
        chute_p = land + rel((15050.1, 12183.4, 0.0), rot)
        for flip in (1, -1):
            cp = land + rel((15050.1 * flip, 12183.4 * flip, 0.0), rot)
            g = self._ground(cp[0], cp[1])
            if g is not None and abs(g - land[2]) < 1.0 * M and not K.blocked(land + np.array([0, 0, 0.5 * M]),
                                                                                 cp + np.array([0, 0, 0.5 * M])):
                chute_p = np.array([cp[0], cp[1], g]); break
        else:
            chute_p = None
        kids = [man]
        if chute_p is not None:
            kids.append(T(K.nid(), 'EditRigidObj', 'HALO chute on the ground', *[float(c) for c in chute_p], 0.0, 0.0,
                          float(5.497787 + rot), 'halochuteground', 5, False, False))
        cam = land + rel((-10277.5, 15122.8, 7393.2), rot)
        look = land + np.array([0, 0, 0.8 * M])
        if K.blocked(cam, look):
            cam, _ = K.frame(tuple(look), dist_m=(3, 6), height_m=(0.8, 2.2))
        keys = [CS.key(tuple(cam), tuple(look), 4.5, True, fov=0.6), CS.key(tuple(cam), tuple(look), 0.0, False, fov=0.52)]
        cs_id, cs_t = self.cs(keys, 'HALO landed')
        shots.append(dict(cs=cs_id, tasks=kids + [cs_t], dur=4.5, name='HALO landed'))
        return shots

    # ------------------------------------------------------------------ the helicopter extraction
    def lz(self, near, radius_m=60.0, clear_m=11.0):
        """an open spot for the helicopter near `near`: flat ground (terrain or a wide floor), nothing within
        clear_m metres up to 25 m height -> (x, y, z)"""
        K = self.K
        best = None
        for r in np.linspace(0, radius_m, 13):
            for b in range(0, 360, 20 if r else 360):
                c = np.array([near[0] + math.sin(math.radians(b)) * r * M, near[1] + math.cos(math.radians(b)) * r * M])
                g = self._ground(c[0], c[1])
                if g is None:
                    continue
                hs = [self._ground(c[0] + dx * clear_m * M, c[1] + dy * clear_m * M) for dx, dy in
                      ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, -0.7), (0.7, -0.7), (-0.7, 0.7))]
                if any(h is None or abs(h - g) > 2.5 * M for h in hs):
                    continue
                base = np.array([c[0], c[1], g])
                if any(K.blocked(base + np.array([0, 0, hh * M]), base + np.array([dx * clear_m * M, dy * clear_m * M, hh * M]), pad=0.2 * M)
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, -0.7), (0.7, -0.7), (-0.7, 0.7))
                       for hh in (1.5, 4.0, 8.0)):
                    continue
                if K.blocked(base + np.array([0, 0, 1.0 * M]), base + np.array([0, 0, 30 * M]), pad=0.2 * M):
                    continue
                best = base
                break
            if best is not None:
                break
        assert best is not None, ('no landing zone near', [c / M for c in near])
        return tuple(float(c) for c in best)

    def heli(self, lz, skin, pilot='igiagent_1', lines=None):
        """outro shots: the friendly helicopter comes in, Jones waves, then the lift-off seen from inside the cabin.
        -> shots (the mission's own outro tour follows them as the view from the helicopter)"""
        K = self.K
        lz = np.array(lz, float)
        hover = lz + np.array([0, 0, 1.8 * M])                     # (710_01_1: the skids are 1.77 m below its origin)
        # approach bearing with free airspace
        app = None
        for b in range(0, 360, 15):
            far = lz + np.array([math.sin(math.radians(b)) * 260 * M, math.cos(math.radians(b)) * 260 * M, 70 * M])
            mid = lz + np.array([math.sin(math.radians(b)) * 70 * M, math.cos(math.radians(b)) * 70 * M, 22 * M])
            if not K.blocked(far, mid, pad=2 * M) and not K.blocked(mid, hover + np.array([0, 0, 4 * M]), pad=2 * M):
                app = (b, far, mid); break
        assert app, 'no approach for the helicopter'
        b, far, mid = app
        yaw = math.atan2(-(lz[0] - far[0]), lz[1] - far[1])      # it flies (and lands) facing away from where it came
        shots = []
        # --- 1. it comes in; Jones waves it down
        heli1 = K.nid()
        rotors = [T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_04_1', 0),
                  T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_05_1', 0)]
        h1 = T(heli1, 'EditRigidObj', 'extraction helicopter (arriving)', *[float(c) for c in far], 0.0, 0.0, float(yaw), '710_01_1', 8,
               False, False, children=rotors + [self.pilot(far, yaw, name='pilot (arriving)')])   # (owner A2 10-13: a visible pilot)
        pts = [far, mid, hover + np.array([0, 0, 6 * M]), hover]
        sp, secs = self.spline(heli1, [tuple(p) for p in pts], [140.0, 70.0, 18.0, 4.0], [yaw] * 4, name='helicopter approach')
        dur1 = secs + 1.5
        jpos = lz + np.array([math.cos(yaw) * 14 * M, math.sin(yaw) * 14 * M, 0])        # 14 m to the side of the LZ, facing it
        jz = self._ground(jpos[0], jpos[1])
        jpos[2] = jz if jz is not None else lz[2]
        face = math.atan2(-(lz[0] - jpos[0]), lz[1] - jpos[1])
        jones = T(K.nid(), 'EditBoneObj', 'Jones waits for the helicopter', *[float(c) for c in jpos], 0.0, 0.0, float(face), True, True,
                  skin, True, '', '', 'stand_wave, stand_wave, stand_look_about', 1.0, 0.3)
        cam = jpos + np.array([math.sin(face) * 3.5 * M, -math.cos(face) * 3.5 * M, 1.4 * M]) \
            + np.array([math.cos(face) * 1.6 * M, math.sin(face) * 1.6 * M, 0])                 # over his shoulder
        if K.blocked(cam, jpos + np.array([0, 0, 1.2 * M])):
            cam, _ = K.frame(tuple(jpos + np.array([0, 0, 1.4 * M])), dist_m=(3, 6), height_m=(0.5, 2.0))
        keys = [dict(CS.key(tuple(cam), tuple(far), dur1 - 0.5, True, fov=0.9), target_id=heli1),
                dict(CS.key(tuple(cam), tuple(hover), 0.5, False, fov=1.0), target_id=heli1),
                dict(CS.key(tuple(cam), tuple(hover), 0.0, False, fov=1.0), target_id=heli1)]
        cs1, cs1_t = self.cs(keys, 'helicopter arrives')
        t1 = [h1] + sp + [jones, cs1_t, self.sfx(cs1, 0.3, 'cs16_heliby_outro', 6.0), self.sfx(cs1, 4.0, 'cs16_heliext', 6.0)]
        l1 = (lines or ('PILOT: Eagle one on final. Hold on to your hat, Jones!',))[0]
        t1.append(self.say(cs1, 0.8, K.vp + 'heli1', l1))
        shots.append(dict(cs=cs1, tasks=t1, dur=dur1, name='helicopter arrives'))
        # --- 2. inside: Mission 16 'Quest and Jones in chopper' (pilot + Jones + the linked cabin camera), lifting off
        S = Source(L16)
        H16 = S.byid[3623]
        P16 = np.array([float(lit(H16.args[3 + k])) for k in range(3)])
        G16 = float(lit(H16.args[8]))
        got, idmap = self.clone(L16, [3623], hover - P16, skin=skin, yaw=yaw - G16, pivot=P16)
        heli2 = idmap[3623]
        for t_, d_, p_ in tasks(got):                         # Mission 16's passenger rq_1 is General Volkov's skin here
            if lit(t_.args[1]) == 'EditBoneObj' and str(lit(t_.args[11])) == 'rq_1':
                t_.args[11] = v(pilot)
            if lit(t_.args[1]) == 'EditBoneObj' and 'jones_takes_walk_from_chopper' in str(lit(t_.args[15])):
                # (Mission 16 walks him OUT; ours lifts off.) Seated like Mission 16's in-chopper Jones 3849: its seat in
                # the helicopter's frame (3784), looping at normal speed (reviewer 10-10: the walk-out actor's spot is
                # ~1 m off, in the aisle, and plays once at 0.4x)
                loc = np.array([3127.4, -2252.3, -3942.5])
                cy_, sy_ = math.cos(yaw), math.sin(yaw)
                p_ = hover + np.array([loc[0] * cy_ - loc[1] * sy_, loc[0] * sy_ + loc[1] * cy_, loc[2]])
                for k_ in range(3):
                    t_.args[3 + k_] = v(float(p_[k_]))
                t_.args[8] = v(float(yaw + 0.060413))
                t_.args[9] = v(True)
                t_.args[15] = v('jones_in_chopper_no_props ')
                t_.args[16] = v(1.0)
        h2 = got[0]
        h2.args.append(self.pilot(hover, yaw, name='pilot (cabin)'))   # (owner A2 10-13: Mission 16's cockpit was empty)
        fwd = np.array([-math.sin(yaw), math.cos(yaw), 0])
        pts2 = [hover, hover + np.array([0, 0, 12 * M]), hover + fwd * 60 * M + np.array([0, 0, 30 * M]),
                hover + fwd * 260 * M + np.array([0, 0, 70 * M])]
        sp2, secs2 = self.spline(heli2, [tuple(p) for p in pts2], [3.0, 25.0, 80.0, 160.0], [yaw] * 4, name='helicopter lift-off')
        cam16 = S.byid[3614]
        c16 = np.array([float(lit(cam16.args[3 + k])) for k in range(3)])
        R = np.array([[math.cos(yaw - G16), -math.sin(yaw - G16), 0], [math.sin(yaw - G16), math.cos(yaw - G16), 0], [0, 0, 1]])
        cpos = R @ (c16 - P16) + hover
        dur2 = min(9.0, secs2)
        # test 10-10: Mission 16's linked camera sits in the cockpit looking FORWARD - the seated pilot and Jones are behind
        # it (that shot is a view out of the cabin). So first a camera outside the open right door looking in at them
        # (helicopter frame: +x right, +y forward; spot ray-tested clear to Jones' head/chest and the pilot on the
        # 710_01_1 collision mesh), riding along (linked), then Mission 16's view out of the cabin as it climbs.
        Ry = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
        door = hover + Ry @ np.array([22000.0, 8000.0, -1500.0])
        aim = hover + Ry @ (0.65 * np.array([3127.0, -2252.0, -942.0]) + 0.35 * np.array([621.0, 1882.0, -650.0]))
        da, dg = CS.look(door, aim)
        t_door = min(5.0, max(2.0, dur2 - 3.0))
        cams = [T(K.nid(), 'EditCamera', '', *[float(c) for c in door], float(da), 0.0, float(dg), 0.85, t_door, heli2, True, -1, True,
                  False, -1, CS.NONE, 0.0, 0.0, 0.0, 0.0, 0.0),
                T(K.nid(), 'EditCamera', '', *[float(c) for c in cpos], float(lit(cam16.args[6])), 0.0,
                  float(lit(cam16.args[8])) + (yaw - G16), 0.95, dur2 - t_door, heli2, True, -1, True, False, -1, CS.NONE,
                  0.0, 0.0, 0.0, 0.0, 0.0)]
        cs2 = K.nid()
        cs2_t = T(cs2, 'CutScene', 'helicopter cabin', *[float(c) for c in door], 0.0, 0.0, 0.0, '!CutScene_%d.isFinished' % cs2, '', '',
                  0.0, 1.0, 0.7, 0.0, 0.0, 0.0, '', '', children=cams)
        shots.append(dict(cs=cs2, tasks=got + sp2 + [cs2_t, self.sfx(cs2, 0.0, 'cs16_heliint', dur2)], dur=dur2, name='helicopter cabin'))
        self.HELI = dict(lz=tuple(lz), yaw=yaw, approach_bearing=b)
        return shots

    # ------------------------------------------------------------------ the owner's A1/A2 standard (10-13): a helicopter that
    # WAITS on the pad, rotors turning, a red smoke flare beside it, an IGI soldier in the open door, the PILOT visible in
    # the cockpit; the mission ends when Jones steps into the door; the outro = he is pulled in, the cabin, the lift-off.
    # 710_01_1 frame (collision mesh, metres): cabin floor z -1.1 (x +-1.66, y -9.5..5.1), cockpit seats z 0.0 at
    # y 4.6..5.5 (x +-1.37), skids 1.77 below the origin, side door on +x around y 0..1.5 (Mission 16 looks in there).
    SKIDS_M = 1.77
    FLOOR_M = -1.10
    PILOT_SEAT = (-0.57, 4.13, -0.88)                # (10-19 owner: the pilot did not sit in his seat -> the offset Mission 16's own
                                                     #  'Helicopter' 1102 uses for its fly_chopper pilot rq_1, measured in its frame)
    DOOR_IN = (1.15, 0.60, -1.10)                    # where the soldier stands in the right-hand door
    DOOR_OUT = (3.0, 0.60)                           # where Jones steps in (x right, y forward; z = the ground)
    J_SEAT = (3127.4 / 4096.0, -2252.3 / 4096.0, -3942.5 / 4096.0)   # Mission 16's seated Jones (jones_in_chopper_no_props)
    S_SEAT = (3127.4 / 4096.0, 1.75, -3942.5 / 4096.0)   # (10-19 owner: the soldier sat in mid-air -> the other bench, mirrored
                                                     #  across the door from Jones's, same seated anim)

    @staticmethod
    def _R(yaw):
        c_, s_ = math.cos(yaw), math.sin(yaw)
        return np.array([[c_, -s_, 0.0], [s_, c_, 0.0], [0.0, 0.0, 1.0]])

    def _loc(self, origin, yaw, local_m):
        return tuple(float(c) for c in (np.asarray(origin, float) + self._R(yaw) @ (np.asarray(local_m, float) * M)))

    def pilot(self, origin, yaw, skin='igiagent2_1', name='pilot', seat=None):
        """a seated pilot in the cockpit of a 710_01_1 standing at `origin` (its task position) facing `yaw`
        (anim 'fly_chopper': the originals' chopper pilots - L36 csf1_1, L16 rq_1, L26 jones2_1)"""
        p = self._loc(origin, yaw, seat or self.PILOT_SEAT)
        return T(self.K.nid(), 'EditBoneObj', '%s %s' % (self.K.PFX, name), *p, 0.0, 0.0, float(yaw), True, True, skin, True, '', '',
                 'fly_chopper', 1.0, 0.0)

    def flare(self, pos, name='smoke flare', cutoff_m=900.0):
        """a burning red smoke flare on the ground at pos (world units): a red flame glow + red smoke drifting up,
        seen from far away (view cutoff) - [tasks]"""
        import atmos
        from mission_lib import load as _load
        src = {lit(t.args[0]): t for t, d, p in tasks(_load(os.path.join(ROOT, 'work', 'decomp', 'multiplayer_sandstorm_objects.qsc')))
               if lit(t.args[0]) in (2947, 2948)}
        out = []
        sm = atmos._clone(src[2948], self.K.nid(), '%s %s smoke' % (self.K.PFX, name))
        for k, c in enumerate(pos):
            sm.args[3 + k] = v(float(c) + (0.25 * M if k == 2 else 0.0))
        sm.args[8] = v(60)                                   # particles
        sm.args[9] = v(1.6)                                  # radius
        sm.args[11] = v(1.2); sm.args[12] = v(2.2)           # velocity: a lazy plume
        sm.args[13] = v(0.95); sm.args[14] = v(0.12); sm.args[15] = v(0.10)   # red
        sm.args[16] = v(5.0); sm.args[17] = v(3.5)           # life / fade
        sm.args[20] = v(2.2); sm.args[21] = v(0.5)           # particle size
        sm.args[26] = v(0.0); sm.args[27] = v('6')           # generate factor
        sm.args[29] = v(float(cutoff_m)); sm.args[30] = v(False)
        out.append(sm)
        fl = atmos._clone(src[2947], self.K.nid(), '%s %s flame' % (self.K.PFX, name))
        for k, c in enumerate(pos):
            fl.args[3 + k] = v(float(c) + (0.12 * M if k == 2 else 0.0))
        fl.args[8] = v(14); fl.args[9] = v(0.25)
        fl.args[13] = v(1.0); fl.args[14] = v(0.25); fl.args[15] = v(0.12)
        fl.args[20] = v(0.55); fl.args[29] = v(float(cutoff_m)); fl.args[30] = v(False)
        out.append(fl)
        out.append(atmos.glow(self.m, self.K.nid, None, (pos[0], pos[1], pos[2] + 0.35 * M), color=(2.0, 0.3, 0.15), size=0.7,
                              name='%s %s glow' % (self.K.PFX, name), cutoff_m=cutoff_m))
        return out

    def waiting_heli(self, pad, yaw, soldier='igiagent1_1', pilot='igiagent2_1', flare_side=-1.0):
        """the landed helicopter waiting on `pad` (ground z, units), nose along `yaw`; rotors turning; the IGI soldier
        in the right door waving Jones in (soldier=None: nobody in the door - Sirocco 10-24c, pilot only); the pilot in the
        cockpit; the flare 7 m off the left side.
        -> dict(tasks=[...], heli=<rigid id>, origin, door=(x, y, z) outside the door, flare=(x, y, z))"""
        K = self.K
        origin = (float(pad[0]), float(pad[1]), float(pad[2]) + self.SKIDS_M * M)
        heli = K.nid()
        rotors = [T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_04_1', 0),
                  T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_05_1', 0)]
        h = T(heli, 'EditRigidObj', '%s extraction helicopter (waiting)' % K.PFX, *origin, 0.0, 0.0, float(yaw), '710_01_1', 8,
              False, False, children=rotors)
        sp = self._loc(origin, yaw, self.DOOR_IN)
        sold = T(K.nid(), 'EditBoneObj', '%s IGI soldier in the door' % K.PFX, *sp, 0.0, 0.0, float(yaw - math.pi / 2), True, True,
                 soldier, True, '', '', 'stand_wave, stand_wave, stand_look_about, stand_wave', 1.0, 0.0) if soldier else None   # faces out of the door (+x)
        door = self._loc(origin, yaw, (self.DOOR_OUT[0], self.DOOR_OUT[1], 0.0))
        door = (door[0], door[1], float(pad[2]))
        fp = self._loc(origin, yaw, (flare_side * 7.0, -1.0, 0.0))
        fp = (fp[0], fp[1], float(pad[2]))
        tasks_ = [h, self.pilot(origin, yaw, pilot)] + ([sold] if soldier else []) + self.flare(fp, 'extraction flare')
        self.WAIT = dict(heli=heli, origin=origin, yaw=yaw, door=door, flare=fp)
        K.WAIT_INFO = self.WAIT                                   # (10-18: Kit's 'chaindoor' test variant stands Jones here)
        return dict(tasks=tasks_, heli=heli, origin=origin, door=door, flare=fp, yaw=yaw)

    def fly_in(self, pad, yaw, when, name='helicopter flies in'):
        """A1: the helicopter flies in and lands once `when` is true (gameplay, not a cutscene): an approach copy on a
        spline from 300 m out down onto the pad; when it has landed the waiting set (waiting_heli, gate it with the
        returned 'landed' expression) takes over in exactly its place.
        -> dict(tasks=[...], landed=<expression>, secs=<flight seconds>, timer=<LevelTimer id>)"""
        K = self.K
        origin = np.array([float(pad[0]), float(pad[1]), float(pad[2]) + self.SKIDS_M * M])
        fwd = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
        best = None
        for db in (0, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180):
            a_ = yaw + math.pi + math.radians(db)                  # come in from behind (it lands nose-on to its yaw)
            back = np.array([-math.sin(a_), math.cos(a_), 0.0])
            far = origin + back * 300 * M + np.array([0, 0, 75 * M])
            mid = origin + back * 70 * M + np.array([0, 0, 22 * M])
            if not K.blocked(far, mid, pad=2 * M) and not K.blocked(mid, origin + np.array([0, 0, 6 * M]), pad=2 * M):
                best = (far, mid); break
        assert best, 'no clear approach for the helicopter'
        far, mid = best
        hid = K.nid()
        rotors = [T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_04_1', 0),
                  T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_05_1', 0)]
        h = T(hid, 'EditRigidObj', '%s %s' % (K.PFX, name), *[float(c) for c in far], 0.0, 0.0, float(yaw), '710_01_1', 8, False, False,
              children=rotors + [self.pilot(far, yaw, name='pilot (flying in)')])
        pts = [far, mid, origin + np.array([0, 0, 6 * M]), origin]
        sp, secs = self.spline(hid, [tuple(p) for p in pts], [150.0, 70.0, 14.0, 3.0], [yaw] * 4, name=name + ' path')
        timer = K.nid()
        for t_, d_, p_ in tasks(sp):                           # the flight starts with `when`
            if lit(t_.args[1]) == 'SequenceCommand':
                t_.args[3] = v(when)
        landed = 'LevelTimer_%d.nTick > %.2f * GAME_FREQUENCY' % (timer, secs + 0.5)
        cc = K.nid()
        out = [T(timer, 'LevelTimer', '%s %s clock' % (K.PFX, name), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, when, '', False),
               T(cc, 'ConditionalContainer', '%s %s (flying)' % (K.PFX, name), '(%s) && !(%s)' % (when, landed), '', '', children=[h]),
               ] + sp
        out.append(T(K.nid(), 'StatusMessage', '%s rotor noise' % K.PFX, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                     'LevelTimer_%d.nTick > 1' % timer, '', '', 'cs16_heliby_outro', True, False, float(min(secs, 8.0)), ''))
        return dict(tasks=out, landed=landed, secs=secs, timer=timer)

    # 10-24 S1: Mission 16's own cockpit shot 'Quest in cocpit' (container 3735, camera 3736 linked to helicopter 3723): the
    # camera sits INSIDE the cockpit 0.71 m left of the pilot (beside the left window), 1.22 m above his root, level, looking
    # 100 deg to the right of the nose - his profile. The right-hand window only shows the empty co-pilot seat (10-24c).
    COCKPIT_CAM = (-0.71, 0.0, 1.22)                 # (from the pilot's seat offset, helicopter frame, metres)
    COCKPIT_YAW = math.radians(-100.2)               # (camera yaw - helicopter yaw; Gamma convention: 0 = nose, +pi/2 = left)

    def cockpit_camera(self, origin, yaw, heli_id, dur, seat=None, fov=1.0, shake=0.004):
        """an EditCamera riding on helicopter heli_id (a 710_01_1 at origin/yaw) that films its pilot in profile (L16 3736)"""
        s = np.array(seat or self.PILOT_SEAT) + np.array(self.COCKPIT_CAM)
        cam = self._loc(origin, yaw, s)
        return T(self.K.nid(), 'EditCamera', '', *cam, -math.pi / 2, 0.0, float(yaw + self.COCKPIT_YAW), float(fov), float(dur),
                 heli_id, True, -1, True, False, -1, CS.NONE, 0.0, 0.0, 0.0, 0.0, float(shake))

    def board_outro(self, pad, yaw, skin, soldier='igiagent1_1', pilot='igiagent2_1', passengers=(), lines=None, cabin_lines=(),
                    cabin_min=0.0, cockpit=0.0, heli_extras=None):
        """outro shots for the waiting helicopter: (1) Jones walks the last metres to the door, the soldier reaches out
        and pulls him in; (2) inside: the soldier and Jones seated, the pilot in the cockpit, the helicopter lifts off
        (linked camera); (3) from the ice: it climbs away. passengers = [(skin, seat local m, anim)] extra people in the
        cabin (e.g. Elena). lines = (soldier line, pilot line).
        soldier=None (Sirocco 10-24c, owner: 'pilot only'): nobody in the door - (1) Jones walks up to the open door by
        himself, the camera aimed between the door and the cockpit so the pilot stays in the shot, lines[0] (or None) is
        his door line; (2) the cabin: the same door view, Jones seated alone (10-24c in game: a cockpit-window camera
        only showed the empty co-pilot seat hiding the pilot - dropped).
        cockpit=s > 0 (10-24 S1): the cabin shot cuts after s seconds to Mission 16's cockpit camera (cockpit_camera: the
        pilot in profile, riding along) and the pilot's line plays there. heli_extras(origin, yaw) -> [child tasks] adds
        children to every helicopter copy (e.g. a mounted gun; positions for the copy standing at origin/yaw)."""
        K = self.K
        origin = np.array([float(pad[0]), float(pad[1]), float(pad[2]) + self.SKIDS_M * M])
        R = self._R(yaw)
        _x = (lambda: list(heli_extras(origin, yaw))) if heli_extras else (lambda: [])
        rotors = lambda: [T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_04_1', 0),
                          T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_05_1', 0)] + _x()
        l_sold, l_pilot = lines or ('SOLDIER: Jones! Get in, get in!', 'PILOT: He is aboard. Lifting off.')
        shots = []
        # --- 1. the door: Jones comes in from 6 m out (generic_walk: 6.4 m in 8 s, played once), the soldier in the door
        heli1 = K.nid()
        h1 = T(heli1, 'EditRigidObj', '%s helicopter (boarding)' % K.PFX, *origin, 0.0, 0.0, float(yaw), '710_01_1', 8, False, False,
               children=rotors())
        door_in = self._loc(origin, yaw, self.DOOR_IN)
        start = self._loc(origin, yaw, (self.DOOR_OUT[0] + 5.2, self.DOOR_OUT[1], 0.0))
        start = (start[0], start[1], float(pad[2]))
        walk_g = float(yaw - math.pi / 2 + math.pi)          # walking toward -x of the helicopter frame = into the door
        jones = T(K.nid(), 'EditBoneObj', '%s Jones boards' % K.PFX, *start, 0.0, 0.0, walk_g, False, True, skin, True, '', '',
                  'generic_walk', 1.25, 0.0)
        sold = T(K.nid(), 'EditBoneObj', '%s soldier pulls him in' % K.PFX, *door_in, 0.0, 0.0, float(yaw - math.pi / 2), True, True,
                 soldier, True, '', '', 'stand_wave, cutscene_talk1', 1.0, 0.0) if soldier else None
        pil = self.pilot(origin, yaw, pilot, name='pilot (boarding)')
        c1 = self._loc(origin, yaw, (self.DOOR_OUT[0] + 2.4, self.DOOR_OUT[1] + 3.6, 0.0))
        c1 = (c1[0], c1[1], float(pad[2]) + 1.55 * M)
        look1 = (door_in[0], door_in[1], door_in[2] + 1.3 * M)
        if not soldier:                                       # (no soldier: aim between the door and the pilot's seat)
            pl_ = self._loc(origin, yaw, self.PILOT_SEAT)
            look1 = ((door_in[0] + pl_[0]) / 2, (door_in[1] + pl_[1]) / 2, door_in[2] + 1.2 * M)
        c1b = self._loc(origin, yaw, (self.DOOR_OUT[0] + 1.3, self.DOOR_OUT[1] + 2.2, 0.0))
        c1b = (c1b[0], c1b[1], float(pad[2]) + 1.45 * M)
        keys = [CS.key(c1, look1, 5.6, True, fov=0.9, shake=0.004), CS.key(c1b, look1, 0.0, False, fov=0.8, shake=0.004)]
        cs1, cs1_t = self.cs(keys, 'boarding')
        t1 = [h1, pil] + ([sold] if soldier else []) + [jones, cs1_t, self.sfx(cs1, 0.0, 'cs16_heliext', 6.0)]
        if l_sold:
            t1.append(self.say(cs1, 0.5, K.vp + 'board1', l_sold))
        shots.append(dict(cs=cs1, tasks=t1, dur=5.6, name='boarding'))
        # --- 2. inside: seated, the pilot ahead, lift-off (the camera rides along: linked to the helicopter)
        heli2 = K.nid()
        h2 = T(heli2, 'EditRigidObj', '%s helicopter (lift-off)' % K.PFX, *origin, 0.0, 0.0, float(yaw), '710_01_1', 8, False, False,
               children=rotors())                     # (the people inside are its CHILDREN below: they lift off with it)
        js = self._loc(origin, yaw, self.J_SEAT)
        j2 = T(K.nid(), 'EditBoneObj', '%s Jones seated' % K.PFX, *js, 0.0, 0.0, float(yaw + 0.060413), True, True, skin, True, '', '',
               'jones_in_chopper_no_props ', 1.0, 0.0)
        ss = self._loc(origin, yaw, self.S_SEAT)
        s2 = T(K.nid(), 'EditBoneObj', '%s soldier seated' % K.PFX, *ss, 0.0, 0.0, float(yaw + 0.060413), True, True, soldier, True, '', '',
               'jones_in_chopper_no_props ', 1.0, 0.0) if soldier else None
        extra = []
        for k, (pskin, seat, anim) in enumerate(passengers):
            ps = self._loc(origin, yaw, seat)
            extra.append(T(K.nid(), 'EditBoneObj', '%s passenger %d' % (K.PFX, k + 1), *ps, 0.0, 0.0, float(yaw), True, True, pskin, True,
                           '', '', anim, 1.0, 0.0))
        p2 = self.pilot(origin, yaw, pilot, name='pilot (lift-off)')
        fwd = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
        pts2 = [origin, origin + np.array([0, 0, 10 * M]), origin + fwd * 50 * M + np.array([0, 0, 28 * M]),
                origin + fwd * 240 * M + np.array([0, 0, 70 * M]), origin + fwd * 900 * M + np.array([0, 0, 110 * M])]
        sp2, secs2 = self.spline(heli2, [tuple(p) for p in pts2], [2.0, 22.0, 75.0, 150.0, 160.0], [yaw] * 5, name='lift-off')
        dur2 = max(min(9.0, secs2), min(cabin_min, secs2))
        cam_rear = self._loc(origin, yaw, (-0.3, -3.4, 0.35))     # at the back of the cabin, looking forward past the seats
        aim = self._loc(origin, yaw, (0.3, 3.2, -0.25))
        da, dg = CS.look(cam_rear, aim)
        cam_door = self._loc(origin, yaw, (3.6, 0.6, -0.35))      # outside the open door, looking in (Mission 16 recipe)
        aim2 = self._loc(origin, yaw, ((self.J_SEAT[0] + self.S_SEAT[0]) / 2, (self.J_SEAT[1] + self.S_SEAT[1]) / 2, -0.2))
        ea, eg = CS.look(cam_door, aim2)
        t_door = 3.0
        t_cut = min(float(cockpit), dur2 - 2.5) if cockpit else dur2   # (cockpit: the door view, then the pilot in profile)
        cams = [T(K.nid(), 'EditCamera', '', *cam_door, float(ea), 0.0, float(eg), 0.85, t_cut, heli2, True, -1, True, False, -1,
                  CS.NONE, 0.0, 0.0, 0.0, 0.0, 0.0)]          # (owner 10-19: the rear-cabin camera showed the hollow inside of the
                                                             #  model - the door view rides along for the whole lift-off instead)
        if cockpit:
            cams.append(self.cockpit_camera(origin, yaw, heli2, dur2 - t_cut))
        cs2 = K.nid()
        cs2_t = T(cs2, 'CutScene', '%s helicopter cabin' % K.PFX, *cam_rear, 0.0, 0.0, 0.0, '!CutScene_%d.isFinished' % cs2, '', '',
                  0.0, 1.0, 0.7, 0.0, 0.0, 0.0, '', '', children=cams)
        h2.args += [j2] + ([s2] if soldier else []) + [p2] + extra
        t2 = [h2] + sp2 + [cs2_t, self.sfx(cs2, 0.0, 'cs16_heliint', dur2),
                           self.say(cs2, (t_cut + 0.3) if cockpit else 1.0, K.vp + 'board2', l_pilot)]
        for at_, vdef_, text_, who_ in cabin_lines:            # (more lines in the cabin: e.g. Elena's)
            t2.append(self.say(cs2, at_, vdef_, text_, who_))
        shots.append(dict(cs=cs2, tasks=t2, dur=dur2, name='cabin lift-off'))
        # --- 3. from the ice: it climbs away (a 2nd copy on the same path, the camera on the ground panning with it)
        heli3 = K.nid()
        h3 = T(heli3, 'EditRigidObj', '%s helicopter (away)' % K.PFX, *origin, 0.0, 0.0, float(yaw), '710_01_1', 8, False, False,
               children=rotors() + [self.pilot(origin, yaw, pilot, name='pilot (away)')])
        sp3, secs3 = self.spline(heli3, [tuple(p) for p in pts2[:4]], [2.0, 22.0, 75.0, 150.0], [yaw] * 4, name='lift-off (away)')
        side = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        c3 = origin - fwd * 18 * M + side * 14 * M
        c3 = (float(c3[0]), float(c3[1]), float(pad[2]) + 1.6 * M)
        dur3 = min(7.0, secs3)
        keys3 = [dict(CS.key(c3, tuple(origin), dur3 - 2.5, True, fov=0.95), target_id=heli3),
                 dict(CS.key(c3, tuple(pts2[2]), 2.5, True, fov=0.7, filt=CS.BAND, color=(1, 1, 1), noise=0.0), target_id=heli3),
                 dict(CS.key(c3, tuple(pts2[2]), 0.0, False, fov=0.7, filt=CS.BAND, color=(0, 0, 0), noise=0.0), target_id=heli3)]
        cs3, cs3_t = self.cs(keys3, 'helicopter away')
        shots.append(dict(cs=cs3, tasks=[h3] + sp3 + [cs3_t, self.sfx(cs3, 0.0, 'cs16_heliby_outro', dur3)], dur=dur3, name='helicopter away'))
        self.HELI = dict(lz=tuple(float(c) for c in pad), yaw=yaw)
        return shots
