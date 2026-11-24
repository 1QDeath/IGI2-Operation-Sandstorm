"""sectorcheck - offline replay of the IGI 2 engine's portal-sector registration for every placed prop (owner bug S1:
props that vanish / reappear when the player turns or side-steps).

    python -P tools/sectorcheck.py <build dir | original level dir> [--json out.json] [--txt out.txt] [--no-pieces]
    e.g. python -P tools/sectorcheck.py build/rc7s25 --txt work/qa/sectorcheck/rc7s25.txt
         python -P tools/sectorcheck.py C:/Users/1qdeath/Games/IGI2/app/MISSIONS/location1/level1

Engine rules replayed (decompilation ShahriyarB_igi2-decomp/src, read 11-15):
  * Sector objects = every type derived from SectorInteriorObject (e/3/sectorobject.c SectorObject_Open + the
    QTask_NewQTaskType parents): EditRigidObj (ConveyorBelt), ExplodeObject (GenericTBA, PlaceExplosiveTBA, Bomb,
    Generator, Mine, Radio, Terminal, AlarmControl, SCameraControl), GenericPickup, AmmoPickup, SCamera, SCameraLens,
    Switch, StationaryGun, AIStationaryGunHolder, AlarmLight, Cabinet. NOT sector objects: GunPickup and Door
    (RigidDynCubeObj), HumanSoldier (Human: queries its sector every frame, Human_GetSector).
  * A Building's sectors are its model's ATTA attachments whose model has portals (HSEM n_portals > 0): ModelObj_
    CreateAttachObject (e/3/modelobj.c) makes them type Sector when the owner derives from SectorObject, and
    SectorObject_CreateAttachObjects moves them into the building's sector container (+400). World pose of a sector:
    pos = Rb @ atta.pos + building pos, R = Rb @ atta.rot.T (the relative orientation is the transposed ATTA matrix).
  * Registration (SectorObject_RegisterInteriorDynCubeObjSpecificSectorObject): point P = pos + R @ HSEM.sph_render
    centre of the object's LOD-0 model. Buildings asked = those with |building pos - object pos| < building radius
    (World_TriggerQTaskEventXyzSpecificTree; radius = max(scale) * HSEM.radius of the building model; note: the
    reach test uses the object's POSITION, the rays use P). Per building (SectorObject_GetSectorHandler): two
    vertical rays from P.z + 0.1 m (isTolerance) down to P.z - 2 r and up to P.z + 2 r, traced against each sector's
    collision mesh 0 (RigidDynCubeObj_TraceLinesHandler, iMesh 0, isTracePortals 1: normal faces two-sided, portal
    faces one-sided: kept only when ((v2-v0) x (v1-v0)) . dir < 0); the closest hit per ray is kept across the
    building's sectors in order, and after each sector, if both closest hits are that sector it becomes the answer
    when min(d_down, d_up) beats the current one (the context is shared across buildings, so the nearest wins).
    Stored once (iSector / ptSector); re-tried only while it has none (a building registering later re-asks).
  * EditRigidObj arg 12 "Excluded from clipping against portals" TRUE skips registration (plain frustum test).
  * Drawing (e/3/pc/pc_rigiddyncubeobj.c): in a sector -> drawn only while that sector is visible this frame and its
    sphere passes one of that sector's portal screen rectangles; in no sector while the camera is in a building
    (camera sector = the same query at the camera position, isTolerance 0, f/1/vptask.c) -> only through that
    building's outside-portal rectangles, nothing when none is on screen. So a prop whose geometry is inside a
    sector but registered in none (or in another sector) pops in and out as the camera turns.

Where the geometry really is: the same up/down test (no 0.1 m offset) at the base point (pos + 0.3 m) and at a
spread of the object's render vertices (pulled 5 cm toward the render-sphere centre so surface-touching vertices
do not land on a floor/ceiling face; a sample still outside is retried 0.2 m toward the centre, up, then down, so
vertices sunk into a floor or embedded in a wall count for the room they show in). Classes:
  OK            registered sector == the sector (or outside) holding most samples, < SPAN_MIN of them elsewhere
  NONE_INSIDE   registered in no sector, geometry inside a sector  (vanishes while the camera is inside)
  WRONG_SECTOR  registered in sector X, geometry mostly in Y (Y may be 'outside')
  SPANS         geometry split over 2+ sectors / inside+outside (>= SPAN_MIN each side), registered in one of them
                or none (merged rooms likely; for 'SS room <x>' objects the pieces of tools/ssrooms.py are listed)
  FLAGGED       EditRigidObj with arg 12 TRUE: not registered, plain frustum test (fine)
  IGNORED       ConveyorBelt / Mine: the renderer skips the sector test for these two types
"""
import argparse, collections, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import igiqvm, mefmesh, mtp
import mef as meflib
from qast import load, tasks, lit
from navgen import rot

M = 4096.0
GAME = r'C:\Users\1qdeath\Games\IGI2\app'
TOL = 0.1 * M                       # isTolerance start offset (409.6 units)
SPAN_MIN = 0.15                     # a second group holding >= this share of the samples = SPANS
MINOR_SHOW = 0.05                   # OK objects with >= this share elsewhere are listed separately (big merged rooms)
PULL = 0.05 * M                     # sample vertices are pulled this far toward the render-sphere centre
NUDGE = 0.2 * M                     # an outside sample within this of a sector (toward the centre / up / down) counts as in it
VOXEL = 0.25 * M                    # sample vertices: one per voxel ...
MAX_SAMPLES = 300                   # ... at most this many per object (+ the base point)
CELL = 2.0 * M                      # XY grid of a sector's triangles

# sector-object types -> index of the model argument (Task_New args incl. id/type/name); None = first arg >= 6 that
# names a known model. Angles: args 6..8 when numeric, else a single yaw at arg 6.
SECTOR_TYPES = {
    'EditRigidObj': 9, 'ConveyorBelt': 9,
    'ExplodeObject': 9, 'GenericTBA': 9, 'PlaceExplosiveTBA': 9, 'Bomb': 9, 'Generator': 9, 'Mine': 9, 'Radio': 9,
    'Terminal': 9, 'AlarmControl': 9, 'SCameraControl': 9,
    'GenericPickup': 9, 'AmmoPickup': None, 'StationaryGun': 9, 'AIStationaryGunHolder': None,
    'Switch': 11, 'SCamera': 7, 'SCameraLens': None, 'AlarmLight': None, 'Cabinet': None,
}
RENDER_SKIPS_SECTOR = ('ConveyorBelt', 'Mine')     # pc_rigiddyncubeobj.c: these two never take the sector branch
NOT_SECTOR = ('GunPickup', 'Door', 'HumanSoldier')


# ================================================================================================ level + models
def _alias_vnams(lib, mtps, common_mtp):
    common = mtp.read(common_mtp) if os.path.exists(common_mtp) else None
    for p in mtps:
        try:
            for vn, (mf, texs) in mtp.resolve(mtp.read(p), common).items():
                if vn.lower() not in lib.index and mf and mf.lower() in lib.index:
                    lib.index[vn.lower()] = lib.index[mf.lower()]
        except Exception:
            pass


def open_level(d):
    """-> (label, stmts, ModelLib). d = a build dir (meta.json) or an original level dir (objects.qvm + models/)"""
    d = os.path.abspath(d)
    cm = os.path.join(GAME, 'COMMON', 'common.mtp')
    gres = [os.path.join(GAME, 'COMMON', 'models', 'common.res'), os.path.join(GAME, 'COMMON', 'models', 'new.res')]
    if os.path.exists(os.path.join(d, 'meta.json')):
        meta = json.load(open(os.path.join(d, 'meta.json')))
        base, loc = meta['base'], meta['location']
        lvl = os.path.join(GAME, 'MISSIONS', loc, base)
        res = sorted(glob.glob(os.path.join(d, 'overlay', 'models', '*.res')))
        res += [os.path.join(lvl, 'models', base + '.res')] + sorted(glob.glob(os.path.join(GAME, 'MISSIONS', loc, 'common', 'models', '*.res'))) + gres
        mtps = sorted(glob.glob(os.path.join(d, 'overlay', '*.mtp'))) + [os.path.join(lvl, base + '.mtp')]
        mtps += sorted(glob.glob(os.path.join(GAME, 'MISSIONS', loc, 'common', '*.mtp')))
    else:
        res = sorted(glob.glob(os.path.join(d, 'models', '*.res'))) + sorted(glob.glob(os.path.join(os.path.dirname(d), 'common', 'models', '*.res'))) + gres
        mtps = sorted(glob.glob(os.path.join(d, '*.mtp'))) + sorted(glob.glob(os.path.join(os.path.dirname(d), 'common', '*.mtp')))
    stmts = load(os.path.join(d, 'objects.qvm'))
    lib = meflib.ModelLib(res)
    _alias_vnams(lib, mtps, cm)
    return os.path.basename(d.rstrip('/\\')), stmts, lib


class Models:
    def __init__(self, lib):
        self.lib, self.cache = lib, {}

    def get(self, name):
        """model facts or None: hsem, centre (sph_render xyz), sph_r, radius, n_portals, atta [(name, pos, rot)],
        V (render vertices, model frame; collision vertices when there is no render mesh), coll0 (V, F, portal mask)"""
        if not isinstance(name, str):
            return None
        k = name.lower()
        if k in self.cache:
            return self.cache[k]
        b = self.lib.index.get(k)
        out = None
        if b is not None:
            try:
                m = mefmesh.Mef.read(b)
            except Exception:
                m = None
            if m is not None and m.hsem is not None:
                h = m.hsem
                at = m.get('ATTA')
                atta = [] if at is None else [(e['name'].split(b'\0')[0].decode('latin1').lower(), e['pos'].astype(float),
                                               e['rot'].astype(float)) for e in at]
                V = None
                try:
                    V = mefmesh.RigidModel.from_mef(m).all_render_pos().astype(float)
                except Exception:
                    V = None
                coll0 = None
                hs = m.get('HSMC')
                if hs is not None and int(hs[0]['mesh'][0]['nfaces']) > 0:
                    cv, cf, ct = m.get('XTVC'), m.get('ECFC'), m.get('TAMC')
                    if cv is not None and cf is not None and ct is not None:
                        ip = (ct['id'] & 0xFFFF).astype(int)
                        mat = np.clip(cf['mat'].astype(int), 0, max(len(ct) - 1, 0))
                        coll0 = (cv['pos'].astype(float), cf['v'].astype(int), ip[mat] != 0xFFFF)
                if (V is None or not len(V)) and coll0 is not None:
                    V = coll0[0]
                s = h['sph_render'].astype(float)
                out = dict(hsem=h, centre=s[:3], sph_r=float(s[3]), radius=float(h['radius']), n_portals=int(h['n_portals']),
                           atta=atta, V=V, coll0=coll0)
        self.cache[k] = out
        return out


# ================================================================================================ sectors
class Sector:
    """one Sector object of a Building: its collision mesh 0 in world space, ready for vertical ray casts"""
    def __init__(self, bid, model, k, R, pos, coll0):
        self.bid, self.model, self.k = bid, model, k
        self.key = '%d:%s' % (bid, model)
        V, F, portal = coll0
        W = V @ R.T + pos
        T = W[F]                                                    # (n, 3, 3) world triangles, engine vertex order
        n = np.cross(T[:, 2] - T[:, 0], T[:, 1] - T[:, 0])          # N = (v2 - v0) x (v1 - v0)  (trace handler)
        nz = n[:, 2]
        keep = np.abs(nz) > 1e-6                                    # vDot == 0 -> never hit (vertical faces)
        self.T, self.nz, self.portal = T[keep], nz[keep], portal[keep]
        self.ok_down = ~self.portal | (self.nz > 0)                 # portal faces: one-sided (vDot = N.d must be < 0)
        self.ok_up = ~self.portal | (self.nz < 0)
        self.lo = self.T.min(axis=1); self.hi = self.T.max(axis=1)
        self.grid = collections.defaultdict(list)
        for i in range(len(self.T)):
            for gx in range(int(self.lo[i, 0] // CELL), int(self.hi[i, 0] // CELL) + 1):
                for gy in range(int(self.lo[i, 1] // CELL), int(self.hi[i, 1] // CELL) + 1):
                    self.grid[(gx, gy)].append(i)
        self.grid = {c: np.array(v) for c, v in self.grid.items()}
        self.bbox = (self.lo.min(axis=0), self.hi.max(axis=0)) if len(self.T) else (pos, pos)

    def trace(self, xy, zs, zlo, zhi):
        """closest hit distance of the down ray (zs -> zlo) and the up ray (zs -> zhi) per point; inf = no hit"""
        N = len(xy)
        dd = np.full(N, np.inf); du = np.full(N, np.inf)
        if not len(self.T) or not N:
            return dd, du
        cells = np.floor(xy / CELL).astype(np.int64)
        keys, inv = np.unique(cells, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        for ci, key in enumerate(keys):
            tri = self.grid.get((int(key[0]), int(key[1])))
            if tri is None:
                continue
            pi = np.nonzero(inv == ci)[0]
            T = self.T[tri]
            a, b, c = T[:, 0], T[:, 1], T[:, 2]
            v0 = (c - a)[:, :2]; v1 = (b - a)[:, :2]
            p = xy[pi][:, None, :] - a[None, :, :2]                 # (P, K, 2)
            d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
            den = d00 * d11 - d01 * d01
            good = np.abs(den) > 1e-9
            den = np.where(good, den, 1.0)
            d20 = (p * v0[None]).sum(2); d21 = (p * v1[None]).sum(2)
            u = (d11[None] * d20 - d01[None] * d21) / den[None]
            v = (d00[None] * d21 - d01[None] * d20) / den[None]
            eps = 1e-7
            inside = good[None] & (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps)
            z = a[None, :, 2] + u * (c - a)[None, :, 2] + v * (b - a)[None, :, 2]
            zs_ = zs[pi][:, None]
            down = inside & self.ok_down[tri][None] & (z <= zs_) & (z >= zlo[pi][:, None])
            up = inside & self.ok_up[tri][None] & (z >= zs_) & (z <= zhi[pi][:, None])
            ddv = np.where(down, zs_ - z, np.inf).min(axis=1)
            duv = np.where(up, z - zs_, np.inf).min(axis=1)
            dd[pi] = np.minimum(dd[pi], ddv); du[pi] = np.minimum(du[pi], duv)
        return dd, du


class Building:
    def __init__(self, bid, name, model, pos, ang, mo):
        self.bid, self.name, self.model, self.pos, self.ang = bid, name, model, pos, ang
        self.R = rot(*ang)
        info = mo.get(model)
        self.r = info['radius'] if info else 0.0                   # reach radius = ray half-length / 2 (scale 1)
        self.sectors, self.missing = [], []
        if info is None:
            return
        for k, (an, apos, arot) in enumerate(info['atta']):
            si = mo.get(an)
            if si is None:
                self.missing.append(an); continue
            if si['n_portals'] <= 0:
                continue                                            # a plain attachment (lamp, stairs ...), not a Sector
            if si['coll0'] is None:
                self.missing.append(an + '(no collision mesh 0)'); continue
            R = self.R @ arot.T
            pos_s = self.R @ apos + self.pos
            self.sectors.append(Sector(bid, an, k, R, pos_s, si['coll0']))


def find_sector(buildings, P, reach_from, tolerance):
    """engine GetSector for many points at once. -> (key array (object, '' = none), vd array, claim count array)"""
    N = len(P)
    best_vd = np.full(N, np.inf); best = np.full(N, -1); claims = np.zeros(N, int)
    flat = []
    for b in buildings:
        if not b.sectors:
            continue
        m = np.linalg.norm(reach_from - b.pos[None], axis=1) < b.r
        if not m.any():
            continue
        idx = np.nonzero(m)[0]
        Q = P[idx]
        zs = Q[:, 2] + (TOL if tolerance else 0.0)
        zlo = Q[:, 2] - 2.0 * b.r; zhi = Q[:, 2] + 2.0 * b.r
        cd = np.full(len(idx), np.inf); cdk = np.full(len(idx), -1)
        cu = np.full(len(idx), np.inf); cuk = np.full(len(idx), -1)
        claimed = np.zeros(len(idx), bool)
        for s in b.sectors:
            si = len(flat); flat.append(s)
            dd, du = s.trace(Q[:, :2], zs, zlo, zhi)
            u = dd < cd; cd[u] = dd[u]; cdk[u] = si
            u = du < cu; cu[u] = du[u]; cuk[u] = si
            ok = (cdk == si) & (cuk == si)
            vd = np.minimum(cd, cu)
            better = ok & (vd < best_vd[idx])
            best_vd[idx[better]] = vd[better]; best[idx[better]] = si
            claimed |= ok
        claims[idx] += claimed
    keys = np.array([flat[i].key if i >= 0 else '' for i in best], dtype=object)
    return keys, best_vd, claims


# ================================================================================================ objects
def _arg(a, i):
    return a[i] if len(a) > i else None


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def object_pose(ty, a, mo):
    """-> (model, angles) per type; model None when the object has none / it is unknown"""
    mi = SECTOR_TYPES.get(ty)
    model = None
    if mi is not None and isinstance(_arg(a, mi), str) and mo.get(_arg(a, mi)) is not None:
        model = _arg(a, mi)
    else:
        for i in range(6, len(a)):
            if isinstance(a[i], str) and a[i].lower() not in ('', 'none', 'true', 'false') and mo.get(a[i]) is not None:
                model = a[i]; break
    if all(_num(_arg(a, i)) for i in (6, 7, 8)):
        ang = (float(a[6]), float(a[7]), float(a[8]))
    else:
        ang = (0.0, 0.0, float(a[6]) if _num(_arg(a, 6)) else 0.0)
    return model, ang


def iter_objects(stmts, types):
    for t, d, par in tasks(stmts):
        ty = lit(t.args[1])
        if ty not in types:
            continue
        a = [lit(x) if not isinstance(x, igiqvm.Call) else None for x in t.args]
        ptype = lit(par.args[1]) if par is not None and getattr(par, 'name', '') == 'Task_New' and len(par.args) > 1 else None
        pid = lit(par.args[0]) if ptype else None
        yield a, ptype, pid


def sample_sectors(sb, S, c):
    """sector key per sample ('' = outside). An outside sample is nudged NUDGE toward the object's centre c, then up,
    then down: vertices sunk a few cm into a floor or embedded in a wall belong to the room they show in"""
    sk, _, _ = find_sector(sb, S, S, False)
    out = np.nonzero(sk == '')[0]
    for kind in ('centre', 'up', 'down'):
        if not len(out):
            break
        Q = S[out].copy()
        if kind == 'centre':
            d = c[None] - Q
            L = np.linalg.norm(d, axis=1)
            Q += d * (np.minimum(NUDGE, L) / np.maximum(L, 1e-9))[:, None]
        else:
            Q[:, 2] += NUDGE if kind == 'up' else -NUDGE
        qk, _, _ = find_sector(sb, Q, Q, False)
        hit = qk != ''
        sk[out[hit]] = qk[hit]
        out = out[~hit]
    return sk


def samples_of(info, R, pos):
    """base point + a spread of render vertices (pulled inward), world"""
    pts = [pos + np.array([0.0, 0.0, 0.3 * M])]
    V = info['V']
    if V is not None and len(V):
        W = V @ R.T + pos
        c = R @ info['centre'] + pos
        d = c[None] - W
        L = np.linalg.norm(d, axis=1)
        step = np.minimum(PULL, 0.1 * L)
        W = W + d * (step / np.maximum(L, 1e-9))[:, None]
        _, first = np.unique(np.floor(W / VOXEL).astype(np.int64), axis=0, return_index=True)
        W = W[np.sort(first)]
        if len(W) > MAX_SAMPLES:
            W = W[np.random.default_rng(0).choice(len(W), MAX_SAMPLES, replace=False)]
        pts += list(W)
    return np.array(pts)


def classify(reg, groups, flagged, ty):
    """reg = registered key ('' none); groups = Counter key -> samples ('' outside) -> (class, majority key, share)"""
    if flagged:
        return 'FLAGGED'
    if ty in RENDER_SKIPS_SECTOR:
        return 'IGNORED'
    n = sum(groups.values())
    major, cnt = groups.most_common(1)[0]
    rest = n - cnt
    if major == reg:
        return 'OK' if rest < SPAN_MIN * n else 'SPANS'
    if rest >= SPAN_MIN * n:
        return 'SPANS'
    return 'NONE_INSIDE' if reg == '' else 'WRONG_SECTOR'


# ================================================================================================ merged rooms
_ROOMS = None


def room_pieces(name):
    """'SS room <x>' -> [(model, x, y, z, yaw)] world metres from tools/ssrooms.py ROOMS + LATE (the CURRENT tree), or None"""
    global _ROOMS
    if _ROOMS is None:
        _ROOMS = {}
        try:
            import ssrooms as RM
            for nm, fn in RM.ROOMS + RM.LATE:
                _ROOMS[nm] = fn
        except Exception as e:
            print('sectorcheck: ssrooms unavailable (%s) - no per-piece list' % e, file=sys.stderr)
    nm = name[len('SS room '):]
    fn = _ROOMS.get(nm)
    if fn is None:
        return None
    try:
        return list(fn())
    except Exception:
        return None


# ================================================================================================ main
def check(level_dir, pieces=True, verbose=False):
    label, stmts, lib = open_level(level_dir)
    mo = Models(lib)
    buildings = []
    for a, ptype, pid in iter_objects(stmts, ('Building',)):
        if not isinstance(_arg(a, 9), str):
            continue
        b = Building(a[0], a[2], a[9], np.array(a[3:6], float), tuple(float(x) for x in a[6:9]), mo)
        buildings.append(b)
    sb = [b for b in buildings if b.sectors]
    rows, nosector = [], collections.Counter()
    for a, ptype, pid in iter_objects(stmts, set(SECTOR_TYPES) | set(NOT_SECTOR)):
        ty = a[1]
        if ty in NOT_SECTOR:
            nosector[ty] += 1
            continue
        model, ang = object_pose(ty, a, mo)
        if model is None:
            continue                                                # nothing drawn (model none / unknown)
        info = mo.get(model)
        pos = np.array(a[3:6], float)
        R = rot(*ang)
        P = R @ info['centre'] + pos
        near = [b for b in sb if np.linalg.norm(P - b.pos) < b.r + info['sph_r'] or np.linalg.norm(pos - b.pos) < b.r]
        if not near:
            continue
        flagged = ty == 'EditRigidObj' and str(_arg(a, 12)).upper() in ('TRUE', '1')
        k, vd, cl = find_sector(sb, P[None], pos[None], True)
        reg = k[0]
        S = samples_of(info, R, pos)
        sk = sample_sectors(sb, S, P)
        groups = collections.Counter(sk.tolist())
        cls = classify(reg, groups, flagged, ty)
        n = len(S)
        row = dict(id=a[0], type=ty, name=a[2], model=model, pos_m=[round(float(x) / M, 2) for x in pos],
                   ang=[round(x, 4) for x in ang], cls=cls, registered=reg or None, reg_point_m=[round(float(x) / M, 2) for x in P],
                   claims=int(cl[0]), real={(kk or 'outside'): round(v / n, 3) for kk, v in groups.most_common()},
                   base=(sk[0] or 'outside'), n_samples=n, flag12=flagged, parent=('%s %s' % (ptype, pid)) if ptype else None,
                   near=[b.bid for b in near])
        major = groups.most_common(1)[0][1]
        row['minority'] = round(1.0 - major / n, 3)
        show = cls not in ('OK', 'FLAGGED') or row['minority'] >= MINOR_SHOW
        if pieces and show and isinstance(a[2], str) and a[2].startswith('SS room '):
            pcs = room_pieces(a[2])
            if pcs:
                Q = np.array([(x * M, y * M, (z + 0.3) * M) for md, x, y, z, yaw in pcs])
                qk, _, _ = find_sector(sb, Q, Q, False)
                solid = [p for p in pcs if not p[0].endswith('~')] or pcs
                o = (np.mean([p[1] for p in solid]), np.mean([p[2] for p in solid]), min(p[3] for p in solid))
                row['pieces_origin_m'] = [round(float(x), 2) for x in o]
                row['pieces_match_build'] = bool(np.allclose(np.array(o), pos / M, atol=0.02))
                row['pieces'] = [dict(model=md, at_m=[round(x, 2), round(y, 2), round(z, 2)], sector=(qk[i] or 'outside'))
                                 for i, (md, x, y, z, yaw) in enumerate(pcs)]
        rows.append(row)
    bl = [dict(id=b.bid, name=b.name, model=b.model, pos_m=[round(float(x) / M, 2) for x in b.pos], yaw=round(b.ang[2], 4),
               radius_m=round(b.r / M, 2), sectors=[s.model for s in b.sectors], missing=b.missing) for b in buildings]
    return dict(level=label, dir=os.path.abspath(level_dir), buildings=bl, rows=rows, not_sector_types=dict(nosector))


def report(res, out=sys.stdout):
    rows = res['rows']
    cnt = collections.Counter(r['cls'] for r in rows)
    p = lambda *s: print(*s, file=out)
    p('sectorcheck %s  (%s)' % (res['level'], res['dir']))
    p('rule: registered sector = engine GetSector at pos + R @ sph_render centre (rays from +0.1 m, -/+ 2 x building radius, vs each')
    p('      sector\'s collision mesh 0, portal faces one-sided; buildings within their radius of the object POSITION). real = the same')
    p('      test at the base point (+0.3 m) and up to %d render vertices (0.2 m nudge). keys = <building id>:<sector model>.' % MAX_SAMPLES)
    p('buildings with sectors:')
    for b in res['buildings']:
        if b['sectors']:
            p('  %5d %-10s %-40s at %s yaw %.3f  r %.1f m  sectors %s%s' % (b['id'], b['model'], repr(b['name'])[:40], b['pos_m'], b['yaw'], b['radius_m'],
                                                                          ' '.join(b['sectors']), ('  MISSING ' + ' '.join(b['missing'])) if b['missing'] else ''))
    nb = [b for b in res['buildings'] if not b['sectors']]
    p('buildings without sectors: %d (%s)' % (len(nb), ', '.join(sorted({b['model'] for b in nb}))))
    p('sector objects near a sectored building: %d   classes: %s' % (len(rows), ', '.join('%s %d' % (k, cnt[k]) for k in
      ('OK', 'NONE_INSIDE', 'WRONG_SECTOR', 'SPANS', 'FLAGGED', 'IGNORED') if cnt[k])))
    p('not sector objects (plain frustum test, not checked): %s' % res['not_sector_types'])
    order = {'NONE_INSIDE': 0, 'WRONG_SECTOR': 1, 'SPANS': 2}
    bad = sorted([r for r in rows if r['cls'] in order], key=lambda r: (order[r['cls']], r['id']))
    p('')
    p('non-OK objects (%d):' % len(bad))
    for r in bad:
        _row(r, p)
    minor = sorted([r for r in rows if r['cls'] == 'OK' and r.get('minority', 0) >= MINOR_SHOW], key=lambda r: -r['minority'])
    if minor:
        p('')
        p('OK, but %d%%-%d%% of the geometry elsewhere (that part shows only while the registered sector is visible) (%d):' % (
            round(MINOR_SHOW * 100), round(SPAN_MIN * 100) - 1, len(minor)))
        for r in minor:
            _row(r, p)
    fl = [r for r in rows if r['cls'] == 'FLAGGED']
    if fl:
        p('')
        p('FLAGGED (arg 12 TRUE, plain frustum test): ' + ', '.join('%d %s' % (r['id'], r['model']) for r in fl))


def _row(r, p):
    real = ', '.join('%s %d%%' % (k, round(v * 100)) for k, v in r['real'].items())
    p('  %-12s %5d %-14s %-13s %-34s at %s  registered %s  real: %s%s%s' % (
        r['cls'], r['id'], r['type'], r['model'], repr(r['name'])[:34], r['pos_m'], r['registered'] or 'none', real,
        ('  (claims %d)' % r['claims']) if r['claims'] > 1 else '', ('  parent %s' % r['parent']) if r['parent'] else ''))
    if r.get('pieces'):                                     # (merged rooms: where each piece's base point is, '~' = seen-only dressing)
        g = collections.defaultdict(list)
        for q in r['pieces']:
            g[q['sector']].append('%s@%.1f,%.1f,%.1f' % (q['model'], *q['at_m']))
        p('               pieces (tools/ssrooms.py, current tree%s):' % ('' if r['pieces_match_build'] else ', ORIGIN DIFFERS FROM BUILD %s' % r['pieces_origin_m']))
        for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
            p('                 %-22s %3d: %s' % (k, len(v), ' '.join(v)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('dir')
    ap.add_argument('--json')
    ap.add_argument('--txt')
    ap.add_argument('--no-pieces', action='store_true')
    o = ap.parse_args()
    res = check(o.dir, pieces=not o.no_pieces)
    report(res)
    if o.txt:
        os.makedirs(os.path.dirname(os.path.abspath(o.txt)), exist_ok=True)
        with open(o.txt, 'w', encoding='utf-8') as f:
            report(res, f)
    if o.json:
        os.makedirs(os.path.dirname(os.path.abspath(o.json)), exist_ok=True)
        json.dump(res, open(o.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
