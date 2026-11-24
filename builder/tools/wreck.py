"""wreck - a REAL destroyed-helicopter model for IGI 2 custom missions (owner 10-12: the burnt Hind "is just fire on it,
looks childish, make it feel real").

740_01_1 (the MP maps call it "Hind") is a coaxial Kamov (Ka-27/29 style): fuselage 740_01_1 + ATTA sub-models
740_02_1 lower rotor, 740_03_1 upper rotor (both MIRRORED, det -1), 740_04_1 left door, 740_05_1 right sliding door
(+ window glass), 740_06_1 canopy glass. The engine draws ATTA sub-models by itself, so a wreck must not keep them
(b740_01_1 showed clean rotors floating over the charred body). This module bakes everything into ONE new vertex-lit
mesh (type 0, no ATTA, no lightmap), and wrecks it:

  * gear collapsed, fuselage settled on its belly, rolled 8 deg to the right, crushed where it meets the ground,
  * tail boom torn off behind the cabin (cut + jagged edge + soot-black inside), lying twisted beside the stump,
  * rotors broken: blades snapped / drooping to the ground, upper head bent over, three blade pieces, a wheel and
    the left door thrown onto the ground around the wreck, canopy and door glass gone,
  * burnt-through holes in the cabin roof / engine deck (dark inside),
  * new charred textures baked with 3D knowledge (soot rising up the sides, paint burnt off the hot engine deck,
    bare scraped metal on the belly, heat tint, rust edges), plus a soot texture for the insides,
  * both collision meshes rebuilt the same way (no invisible walls where the rotors / tail used to be), new sphere
    trees, all header counts / spheres recomputed (tools/mefmesh.py).

The wreck model uses the SAME frame as the intact helicopter: place w740_01_1 with exactly the intact object's
position and orientation (wreck.heli_wreck(K, hid) does that for spkit missions). The ground is assumed flat at the
intact helicopter's wheels.

    import wreck
    wreck.add_wreck_model(overlay_dir, 'sandstorm', src='740_01_1', dst='w740_01_1')   # manifest + banks + lod
    wreck.heli_wreck(K, hid, 'Hind 3901', model='w740_01_1')                         # spkit: swap on explosion

Format: work/wreck/FORMAT.md. Verified / in-game checks: the hand-over report of 2026-10-12 (work/wreck).
"""
import math, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, mefmesh, igitex

GAME = r'C:\Users\1qdeath\Games\IGI2\app'
M = 4096.0                         # world units per metre
COMMON_BIT = mtp.COMMON_BIT
BACKSLASH = chr(92)
PLACEMENT_ALPHA = 0.10472          # every shipped 740_01_1 placement: alpha (pitch) 6 deg, the gear on the ground


# =============================================================================================== small math
def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def axis_angle(axis, a):
    k = np.asarray(axis, float); k = k / np.linalg.norm(k)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def _hash3(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def noise3(p, scale, seed=0, octaves=4, gain=0.5, stretch=(1, 1, 1)):
    """fBm value noise in 0..1 at 3D points p (N,3) [world units]; scale = feature size (units); stretch per axis"""
    rr = np.random.default_rng(1000 + seed)
    q_, _ = np.linalg.qr(rr.normal(size=(3, 3)))                  # random rotation of the lattice
    p = np.asarray(p, float) / (np.asarray(stretch, float) * scale)
    p = p @ q_
    out = np.zeros(len(p)); amp = 1.0; tot = 0.0
    for o in range(octaves):
        q = p * (2 ** o) + o * 17.13
        i0 = np.floor(q).astype(np.int64); f = q - i0
        f = f * f * (3 - 2 * f)
        acc = 0.0
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                    acc = acc + w * _hash3(i0[:, 0] + dx, i0[:, 1] + dy, i0[:, 2] + dz, seed + o)
        out += amp * acc; tot += amp; amp *= gain
    return out / tot


# =============================================================================================== triangle soup
CORNER = ('P', 'N', 'UV', 'E')                       # per corner: position, normal, uv, cut-edge flag
TRI = ('slot', 'flags', 'part', 'mat')               # per triangle: texture slot NAME index, DNER flags, part id, coll material


class Soup:
    """triangles with per-corner attributes. Render soups use slot/flags, collision soups use mat."""
    def __init__(self, **kw):
        n = len(kw['P'])
        self.d = {}
        for k in CORNER + TRI:
            if k in kw and kw[k] is not None:
                self.d[k] = np.asarray(kw[k])
            elif k == 'E':
                self.d[k] = np.zeros((n, 3))
            elif k == 'N':
                self.d[k] = np.zeros((n, 3, 3))
            elif k == 'UV':
                self.d[k] = np.zeros((n, 3, 2))
            else:
                self.d[k] = np.zeros(n, np.int64)
        self.d['P'] = self.d['P'].astype(float)

    def __len__(self):
        return len(self.d['P'])

    def __getattr__(self, k):
        if k == 'd':
            raise AttributeError(k)
        try:
            return self.d[k]
        except KeyError:
            raise AttributeError(k)

    def sel(self, mask):
        return Soup(**{k: v[mask] for k, v in self.d.items()})

    @staticmethod
    def cat(soups):
        soups = [s for s in soups if s is not None and len(s)]
        return Soup(**{k: np.concatenate([s.d[k] for s in soups]) for k in soups[0].d})

    def flip(self):
        """reverse winding (and normals): the inside of a skin"""
        d = {k: v.copy() for k, v in self.d.items()}
        for k in CORNER:
            d[k] = d[k][:, [0, 2, 1]]
        d['N'] = -d['N']
        return Soup(**d)

    def apply(self, mask, fn, nfn=None):
        """p -> fn(p) for the corners of masked triangles (points (k,3)); normals through nfn(p_old, n) or kept"""
        if not mask.any():
            return
        P = self.d['P'][mask].reshape(-1, 3)
        N = self.d['N'][mask].reshape(-1, 3)
        newP = fn(P)
        if nfn is not None:
            N = nfn(P, N)
        self.d['P'][mask] = newP.reshape(-1, 3, 3)
        self.d['N'][mask] = N.reshape(-1, 3, 3)

    def rigid(self, mask, R, t=np.zeros(3), pivot=np.zeros(3), keep_winding=False):
        """p -> R (p - pivot) + pivot + t, normals rotated. A mirror (det R < 0) also reverses the corner order so
        front faces stay in front (used for the mirrored rotor ATTA matrices); keep_winding skips that."""
        R = np.asarray(R, float); t = np.asarray(t, float); pivot = np.asarray(pivot, float)
        self.apply(mask, lambda p: (p - pivot) @ R.T + pivot + t, lambda p, n: n @ R.T)
        if np.linalg.det(R) < 0 and not keep_winding:
            for k in CORNER:
                self.d[k][mask] = self.d[k][mask][:, [0, 2, 1]]

    def fix_normals(self, mask=None):
        """flip every (masked) corner normal that points against its triangle's winding (front = clockwise seen
        from outside = -cross(b-a, c-a)). The rotor sub-models 740_02/03 have outward winding (ray-parity test:
        819/876 and 796/864 faces) but about 40 % of their stored normals point inward (cos ~ -1); the fuselage and
        doors agree 100 %."""
        if mask is None:
            mask = np.ones(len(self), bool)
        P = self.d['P']; g = -np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        bad = mask[:, None] & (np.einsum('ij,ikj->ik', g, self.d['N']) < 0)
        self.d['N'][bad] = -self.d['N'][bad]
        return int(bad.sum())

    def split(self, n, d, mask=None, eps=1e-6):
        """cut the (masked) triangles by the plane n.p = d. Returns side (+1 / -1 per triangle of the new soup);
        new corners on the plane get E = 1. Winding is kept."""
        n = np.asarray(n, float)
        if mask is None:
            mask = np.ones(len(self), bool)
        s = self.d['P'] @ n - d
        pos = (s >= -eps).all(1); neg = (s <= eps).all(1)
        cross = mask & ~pos & ~neg
        side = np.where(s.mean(1) >= 0, 1, -1)
        keep = ~cross
        new = {k: [v[keep]] for k, v in self.d.items()}
        sides = [side[keep]]
        for t in np.nonzero(cross)[0]:
            sg = s[t] >= 0
            lone = [i for i in range(3) if sg[i] != sg[(i + 1) % 3] and sg[i] != sg[(i + 2) % 3]][0]
            i, j, k = lone, (lone + 1) % 3, (lone + 2) % 3
            tij = s[t, i] / (s[t, i] - s[t, j]); tik = s[t, i] / (s[t, i] - s[t, k])

            def lerp(arr, a, b, w):
                return arr[t, a] + (arr[t, b] - arr[t, a]) * w
            corners = {}
            for key in CORNER:
                A = self.d[key][t, i]; B = self.d[key][t, j]; C = self.d[key][t, k]
                X = lerp(self.d[key], i, j, tij); Y = lerp(self.d[key], i, k, tik)
                if key == 'E':
                    X = 1.0; Y = 1.0
                if key == 'N':
                    X = X / max(np.linalg.norm(X), 1e-9); Y = Y / max(np.linalg.norm(Y), 1e-9)
                corners[key] = [np.array([A, X, Y]), np.array([X, B, C]), np.array([X, C, Y])]
            ls = 1 if sg[i] else -1
            for q, sd in zip(range(3), (ls, -ls, -ls)):
                tri = corners['P'][q]
                if np.linalg.norm(np.cross(tri[1] - tri[0], tri[2] - tri[0])) < 1e-3:
                    continue
                for key in CORNER:
                    new[key].append(corners[key][q][None])
                for key in self.d:
                    if key not in CORNER:
                        new[key].append(self.d[key][t:t + 1])
                sides.append(np.array([sd]))
        self.d = {k: np.concatenate(v) for k, v in new.items()}
        return np.concatenate(sides)

    def subdivide_along(self, mask, origin, axis, step):
        """split the masked triangles by planes perpendicular to axis every `step` units (smooth bending later)"""
        axis = np.asarray(axis, float) / np.linalg.norm(axis)
        u = (self.d['P'][mask] - origin) @ axis
        if not len(u):
            return mask
        lo, hi = u.min(), u.max()
        tag = np.zeros(len(self), np.int64); tag[mask] = 1
        self.d['_tag'] = tag
        for c in np.arange(lo + step, hi, step):
            m2 = self.d['_tag'] == 1
            self.split(axis, float(origin @ axis + c), mask=m2)
        out = self.d.pop('_tag') == 1
        return out


def weld_groups(S, slot_values, flags_default=0x1900):
    """render soup -> [mefmesh.Group] (one per (slot, flags)); identical corners are welded into one vertex"""
    groups = []
    keys = sorted(set(zip(S.slot.tolist(), S.flags.tolist())), key=lambda k: (k[0] == 0xFFFF, k))
    for slot, flags in keys:
        m = (S.slot == slot) & (S.flags == flags)
        P = S.P[m].reshape(-1, 3); N = S.N[m].reshape(-1, 3); UV = S.UV[m].reshape(-1, 2)
        key = np.concatenate([np.round(P * 4), np.round(N * 2000), np.round(UV * 65536)], 1).astype(np.int64)
        _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        inv = inv.reshape(-1)
        tris = inv.reshape(-1, 3)
        ok = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
        tex = slot_values[slot] if slot != 0xFFFF else 0xFFFF
        Nn = N[first] / np.linalg.norm(N[first], axis=1, keepdims=True).clip(1e-9)
        groups.append(mefmesh.Group(P[first], UV[first], tris[ok], tex, flags=int(flags), nrm=Nn))
    return groups


def weld_coll(S, mats):
    """collision soup -> mefmesh.CollMesh (positions welded at 1/4 unit)"""
    P = S.P.reshape(-1, 3)
    key = np.round(P * 4).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    F = inv.reshape(-1, 3)
    ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    used = np.unique(S.mat[ok])
    remap = {int(u): i for i, u in enumerate(used)}
    tab = np.array([mats[int(u)] for u in used], mefmesh.TAMC_DT)
    return mefmesh.CollMesh(P[first], F[ok], np.array([remap[int(x)] for x in S.mat[ok]], np.int64), tab)


def components(P, T, weld=2.0):
    """connected components of a triangle list over positions P (welded at `weld` units) -> label per triangle"""
    key = np.round(np.asarray(P, float) / weld).astype(np.int64)
    _, wid = np.unique(key, axis=0, return_inverse=True)
    wid = wid.reshape(-1)
    par = np.arange(wid.max() + 1 if len(wid) else 1)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]; a = par[a]
        return a
    for a, b, c in wid[np.asarray(T)]:
        ra = find(a)
        par[find(b)] = ra; par[find(c)] = ra
    roots = np.array([find(w) for w in wid[np.asarray(T)[:, 0]]])
    _, lab = np.unique(roots, return_inverse=True)
    return lab.reshape(-1)


# =============================================================================================== sources (read-only game)
def level_dir(level_name, game=GAME):
    """MISSIONS/<location>/<level> folder of a level name ('sandstorm' -> multiplayer/sandstorm); a name used by
    several locations ('level4') must be given as 'location2/level4'"""
    root = os.path.join(game, 'MISSIONS')
    if '/' in level_name or BACKSLASH in level_name:
        loc, lv = level_name.replace(BACKSLASH, '/').split('/')[-2:]
        hits = [os.path.join(root, l, v) for l in os.listdir(root) if l.lower() == loc.lower()
                for v in os.listdir(os.path.join(root, l)) if v.lower() == lv.lower()]
    else:
        hits = []
        for loc in sorted(os.listdir(root)):
            d = os.path.join(root, loc)
            if not os.path.isdir(d):
                continue
            for lv in os.listdir(d):
                if lv.lower() == level_name.lower() and os.path.exists(os.path.join(d, lv, lv + '.mtp')):
                    hits.append(os.path.join(d, lv))
    if len(hits) != 1:
        raise FileNotFoundError('level %r: %s' % (level_name, hits or 'not found'))
    return hits[0]


class Bank:
    """a level's manifest + model/texture banks (overlay first, else the shipped level)"""
    def __init__(self, mtp_path, models_res, textures_res, common_mtp=os.path.join(GAME, 'COMMON', 'common.mtp')):
        self.mtp_path, self.models_res, self.textures_res = mtp_path, models_res, textures_res
        self.m = mtp.read(mtp_path)
        self.common = mtp.read(common_mtp)
        self.res = mtp.resolve(self.m, self.common)
        _, ch, _ = ilff.read(models_res)
        self.models = {n.split('/')[-1][:-4].lower(): b for n, t, b in ilff.entries(ch) if n and n.lower().endswith('.mef')}
        _, ch, _ = ilff.read(textures_res)
        self.tex = {n.split('/')[-1][:-4]: b for n, t, b in ilff.entries(ch) if n and n.lower().endswith('.tex')}

    def mef(self, vn):
        mef_name = self.res[vn][0]
        return mefmesh.Mef.read(self.models[mef_name.lower()])

    def texnames(self, vn):
        return self.res[vn][1]


def vertex_lit_copy(name, want_bbox=None, game=GAME):
    """a type-0 (vertex-lit) copy of model `name` anywhere in the game (same geometry, with normals)"""
    for n, p, b in mefmesh.iter_game_mefs(game):
        if n.lower().endswith('/' + name.lower() + '.mef'):
            m = mefmesh.Mef.read(b)
            if m.type != 0:
                continue
            if want_bbox is not None:
                P = m.get('XTRV')['pos']
                if not (np.allclose(P.min(0), want_bbox[0], atol=1) and np.allclose(P.max(0), want_bbox[1], atol=1)):
                    continue
            return m, p
    return None, None


# =============================================================================================== intact assembly
PART_NAMES = []
_CURRENT = [None]


def pid(name):
    if name not in PART_NAMES:
        PART_NAMES.append(name)
    return PART_NAMES.index(name)


def _render_soup(m, texnames, R, t, part_of_tri, slot_ids):
    """Mef render groups -> Soup (model frame of the assembly). part_of_tri(group index, tris, P) -> part ids"""
    out = []
    r = mefmesh.RigidModel.from_mef(m)
    for gi, g in enumerate(r.groups):
        if not len(g.tris):
            continue
        name = texnames[g.tex] if g.tex != 0xFFFF and g.tex < len(texnames) else None
        P = g.pos.astype(float)[g.tris]
        if g.nrm is not None:
            N = g.nrm.astype(float)[g.tris]
        else:
            N = np.repeat(-np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])[:, None], 3, 1)
            N /= np.linalg.norm(N, axis=2, keepdims=True).clip(1e-9)
        s = Soup(P=P, N=N, UV=g.uv.astype(float)[g.tris], slot=np.full(len(P), slot_ids(name)),
                 flags=np.full(len(P), g.flags), part=part_of_tri(gi, g.tris, g.pos.astype(float)))
        s.rigid(np.ones(len(s), bool), R, t)                  # (a mirror reverses the corner order)
        s.fix_normals()
        out.append(s)
    return out


def _coll_soups(m, R, t, mat_table):
    """both collision meshes -> [Soup, Soup] (mat = index into the shared TAMC table)"""
    out = []
    for V, F, T in zip(m.all('XTVC'), m.all('ECFC'), m.all('TAMC')):
        if not len(F):
            out.append(None); continue
        P = V['pos'].astype(float)[F['v'].astype(int)]
        mi = []
        for rec in T:
            key = tuple(int(x) for x in (rec['w0'], rec['id'], rec['w2'], rec['surface']))
            if key not in mat_table:
                mat_table.append(key)
            mi.append(mat_table.index(key))
        s = Soup(P=P, mat=np.array(mi, np.int64)[F['mat'].astype(int)])
        s.rigid(np.ones(len(s), bool), R, t)                  # (mirror: corner order reversed, faces stay outward)
        out.append(s)
    return out


GLASS_SURFACE = 14          # TAMC surface of the canopy / door window glass


def _same_slots(a, b, name):
    """the vertex-lit twin must use the same texture slots per group as the level's own (lightmapped) copy, because
    the slots are resolved through the LEVEL's INST list"""
    import collections
    ga, gb = collections.Counter(), collections.Counter()      # triangles per texture slot (the lightmapped copy
    for gg, m_ in ((ga, a), (gb, b)):                          # may split a slot into several lightmap groups)
        for g in m_.get('DNER'):
            if g['tex'] != 0xFFFF:
                gg[int(g['tex'])] += int(g['ntris'])
    if ga != gb:
        raise ValueError('%s: vertex-lit twin groups %s differ from the level copy %s' % (name, gb, ga))


class Assembly:
    """the intact helicopter (fuselage + ATTA sub-models) as soups in the fuselage's model frame, with part labels"""
    def __init__(self, bank, src='740_01_1', transpose=True):
        self.bank = bank
        self.slots = []                 # texture names used (slot name index)
        self.mats = []                  # collision TAMC records (tuples)
        PART_NAMES.clear()                 # (part ids are global: one Assembly at a time, make_wreck checks)
        _CURRENT[0] = self
        body = bank.mef(src)
        if body.type != 0:              # lightmapped copy (Mission 24 / transplants): take the vertex-lit twin's normals
            P = body.get('XTRV')['pos']
            twin, where = vertex_lit_copy(bank.res[src][0], (P.min(0), P.max(0)))
            if twin is None:
                raise ValueError('no vertex-lit copy of %s in the game' % src)
            _same_slots(body, twin, src)
            body = twin
        self.src = src
        self.body_mef = body
        self.render = []; self.coll = [[], []]
        lab = {}
        texn = bank.texnames(src)
        rbody = mefmesh.RigidModel.from_mef(body)
        for gi, g in enumerate(rbody.groups):
            lab[gi] = components(g.pos.astype(float), g.tris)
        self.body_labels = lab
        self.render += _render_soup(body, texn, np.eye(3), np.zeros(3),
                                    lambda gi, T, P: self._body_parts(gi, T, P, lab[gi]), self.slot)
        for k, s in enumerate(_coll_soups(body, np.eye(3), np.zeros(3), self.mats)):
            if s is not None:
                s.d['part'] = np.full(len(s), -1)
                self.coll[k].append(s)
        self.atta = []
        for a in body.get('ATTA'):
            nm = a['name'].split(b'\0')[0].decode('latin1').lower()
            R = a['rot'].astype(float).T if transpose else a['rot'].astype(float)
            t = a['pos'].astype(float)
            self.atta.append((nm, R, t))
            if nm not in bank.res:
                continue
            sub = bank.mef(nm)
            if sub.type != 0:
                P = sub.get('XTRV')['pos']
                tw, _ = vertex_lit_copy(bank.res[nm][0], (P.min(0), P.max(0)))
                if tw is not None:
                    _same_slots(sub, tw, nm)
                    sub = tw
            texs = bank.texnames(nm)
            rs = mefmesh.RigidModel.from_mef(sub)
            sublab = {gi: components(g.pos.astype(float), g.tris) for gi, g in enumerate(rs.groups)}
            # (attachment textures get their own slot '<tex>@atta': the rotors / doors share texels with the
            #  fuselage, and the charring is baked per 3D surface, so they need a separate charred copy)
            self.render += _render_soup(sub, texs, R, t, lambda gi, T, P, nm=nm, sl=sublab: self._sub_parts(nm, gi, T, P, sl[gi]),
                                        lambda n, tag=('@rotor' if nm in ('740_02_1', '740_03_1') else '@atta'):
                                        self.slot(None if n is None else (n if n.startswith('412_06') else n + tag)))
            for k, s in enumerate(_coll_soups(sub, R, t, self.mats)):
                if s is not None:
                    s.d['part'] = np.full(len(s), pid(nm + ':coll'))
                    self.coll[k].append(s)
        self.R = Soup.cat(self.render)
        self.C = [Soup.cat(c) if c else None for c in self.coll]
        self._label_collision()

    def slot(self, name):
        if name is None:
            return 0xFFFF
        if name not in self.slots:
            self.slots.append(name)
        return self.slots.index(name)

    # ------------------------------------------------------------------ part rules (model frame, metres)
    def _body_parts(self, gi, T, P, lab):
        out = np.zeros(len(T), np.int64)
        if gi == 1:
            return np.full(len(T), pid('interior'))
        if gi == 2:
            return np.full(len(T), pid('body'))
        ncomp = lab.max() + 1
        sizes = np.bincount(lab, minlength=ncomp)
        hull = int(np.argmax(sizes))
        for c in range(ncomp):
            Q = P[np.unique(T[lab == c])] / M
            lo, hi = Q.min(0), Q.max(0); ce = (lo + hi) / 2
            if c == hull:
                name = 'hull'
            elif hi[1] < -5.5 and (lo[0] > 2.0 or hi[0] < -2.0):
                name = 'finR' if ce[0] > 0 else 'finL'
            elif hi[1] < -6.0 and hi[2] - lo[2] < 0.5 and hi[0] - lo[0] > 1.5:
                name = 'stab'
            elif hi[1] < -4.0 and abs(ce[0]) < 0.5:
                name = 'tailbits'
            elif -0.6 < ce[1] < 1.7 and hi[2] < 4.8 and (lo[0] < -2.2 or hi[0] > 2.2):
                name = 'gearR' if ce[0] > 0 else 'gearL'
            elif -0.6 < ce[1] < 1.7 and hi[2] < 3.2 and abs(ce[0]) > 1.4:
                name = 'gearR' if ce[0] > 0 else 'gearL'
            elif 3.8 < ce[1] < 5.6 and hi[2] < 2.75 and abs(ce[0]) < 1.6:
                name = 'gearN'
            else:
                name = 'body'
            out[lab == c] = pid(name)
        # the main wheels are their own pieces (one is thrown off)
        for c in range(ncomp):
            Q = P[np.unique(T[lab == c])] / M
            lo, hi = Q.min(0), Q.max(0)
            if hi[2] < 2.3 and abs((lo[0] + hi[0]) / 2) > 2.3 and (hi[2] - lo[2]) > 0.6:
                out[lab == c] = pid('wheelR' if lo[0] > 0 else 'wheelL')
        return out

    def _sub_parts(self, nm, gi, T, P, lab):
        if nm in ('740_02_1', '740_03_1'):
            tag = 'r1' if nm == '740_02_1' else 'r2'
            out = np.full(len(T), pid(tag + 'hub'))
            blades = []
            for c in range(lab.max() + 1):
                Q = P[np.unique(T[lab == c])]
                if np.linalg.norm(Q.max(0) - Q.min(0)) > 4.0 * M:
                    blades.append(c)
            blades.sort(key=lambda c: math.atan2(*P[np.unique(T[lab == c])].mean(0)[[1, 0]]))
            for k, c in enumerate(blades):
                out[lab == c] = pid('%sblade%d' % (tag, k))
            return out
        if nm == '740_04_1':
            return np.full(len(T), pid('doorL'))
        if nm == '740_05_1':
            return np.full(len(T), pid('doorR' if gi == 0 else 'glass'))
        if nm == '740_06_1':
            return np.full(len(T), pid('glass'))
        return np.full(len(T), pid('body'))

    def _label_collision(self):
        """collision triangles inherit the part of the nearest rendered surface (samples on the render triangles,
        voting with the face's corners + centroid), per face: a coarse hull box that spans two parts (the left gear
        box is welded to the fuselage box) splits with them instead of leaving an invisible box behind.
        Glass faces -> 'glass'."""
        from scipy.spatial import cKDTree
        S = self.R
        samples = [S.P.reshape(-1, 3), S.P.mean(1)]
        labels = [np.repeat(S.part, 3), S.part]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            samples.append((S.P[:, a] + S.P[:, b]) / 2); labels.append(S.part)
        tree = cKDTree(np.concatenate(samples)); lab_s = np.concatenate(labels)
        glass_mats = {i for i, k in enumerate(self.mats) if k[3] == GLASS_SURFACE}
        for k, C in enumerate(self.C):
            if C is None:
                continue
            q = np.concatenate([C.P.reshape(-1, 3), C.P.mean(1)])
            _, j = tree.query(q)
            votes = np.concatenate([lab_s[j[:3 * len(C)]].reshape(-1, 3), lab_s[j[3 * len(C):]][:, None]], 1)
            part = votes[:, 3].copy()                              # centroid vote unless 2+ corners agree
            for i in range(len(C)):
                vals, cnt = np.unique(votes[i, :3], return_counts=True)
                if cnt.max() >= 2:
                    part[i] = vals[np.argmax(cnt)]
            part[np.isin(C.mat, list(glass_mats))] = pid('glass')
            C.d['part'] = part

    def parts(self, soup, *names):
        ids = [PART_NAMES.index(n) for n in names if n in PART_NAMES]
        return np.isin(soup.part, ids)


# =============================================================================================== the wreck recipe
DEFAULT_RECIPE = dict(
    seed=11,
    tail_cut_y=-4.15,                 # m (model frame): the boom tears just behind the cabin
    tail_yaw=24.0, tail_roll=-36.0, tail_gap=(0.55, 0.9),    # deg, deg, (lateral, backward) m of the torn piece
    body_roll=8.0, body_pitch=-4.5, body_sink=0.10,          # deg (right side down), deg (nose down), m into the sand
    gear=dict(gearL=28.0, gearR=-35.0, gearN=-78.0),         # deg: main legs buckle outward (crushed), nose leg folds back
    door_r=(12.0, 8.0),                                      # deg: right sliding door hangs askew off its rail (rear end
                                                             # dropped, swung out)
    # rotors (blade index = azimuth order in the rotor's own, unmirrored frame): ('droop', deg) | ('break', span m, droop deg)
    r1=[('break', 2.4, 9.0), ('break', 3.0, 12.0), ('droop', 55.0)],
    r2=[('break', 1.9, 6.0), ('break', 1.3, 4.0), ('break', 4.6, 18.0)],
    r2_tilt=9.0,                                             # deg: the upper head bent over on its mast
    # debris lying around (ground frame, metres from the wreck centre, yaw deg)
    debris={'r1blade1_out': (7.6, 3.4, 64.0), 'r2blade0_out': (-8.8, -6.2, -28.0), 'r2blade2_out': (4.6, -10.4, 12.0),
            'r1blade0_out': (-6.4, 9.6, 105.0), 'r2blade1_out': (9.8, -3.2, -40.0),
            'gearL+wheelL': (-4.9, 2.4, 30.0), 'doorL': (-3.7, 5.2, -12.0)},   # (a+b = parts thrown as one piece)
    holes=[((0.15, -1.35, 6.35), 0.95), ((-1.1, -2.3, 5.0), 0.85), ((1.25, -1.2, 4.9), 0.7), ((1.15, 3.6, 5.1), 0.45)],
    # (burnt-through holes: centre in the intact model frame m, radius m)
    ground_offset=0.07,               # m: terrain above the wheel plane (Sandstorm heightmap at both Hinds: +0.06/+0.07)
    clamp_lift=0.10,                  # m above that ground for crushed faces (no z-fight with the terrain)
    scorch=(8.5, 6.5, 0.06),          # burnt ground under the wreck: half length, half width, lift (m); None = off
)
TAIL_PARTS = ('tailhull', 'finL', 'finR', 'stab', 'tailbits')


def _jag(p, n, amp, scale, seed):
    """displacement of cut-edge vertices along the cut normal (torn metal), a function of position only so the two
    sides of a cut and the collision copy move together"""
    v = noise3(p, scale, seed, octaves=3) - 0.5
    return p + np.outer(v * 2 * amp, n)


def _bend_fns(c, s_dir, u, w, kappa, s0):
    """constant-curvature droop of a blade: points beyond span s0 (from hub centre c along s_dir) bend down (-u)"""
    def bend(p):
        q = p - c
        aa = q @ s_dir; bb = q @ u; ee = q @ w
        L = np.maximum(aa - s0, 0.0); ph = kappa * L
        if kappa > 0:
            sk = np.sin(ph) / kappa; ck = (1 - np.cos(ph)) / kappa
        else:
            sk = L; ck = np.zeros_like(L)
        return (c + np.outer(np.minimum(aa, s0) + sk + bb * np.sin(ph), s_dir)
                + np.outer(-ck + bb * np.cos(ph), u) + np.outer(ee, w))

    def bend_n(p, n):
        ph = kappa * np.maximum((p - c) @ s_dir - s0, 0.0)
        ns, nu, nw = n @ s_dir, n @ u, n @ w
        return (np.outer(ns * np.cos(ph) + nu * np.sin(ph), s_dir) + np.outer(-ns * np.sin(ph) + nu * np.cos(ph), u)
                + np.outer(nw, w))
    return bend, bend_n


def make_wreck(A, alpha=PLACEMENT_ALPHA, recipe=None, log=print):
    """-> (render soup, [coll soup 0, coll soup 1], ground height in the ground frame) - intact model frame"""
    rc = dict(DEFAULT_RECIPE); rc.update(recipe or {})
    assert _CURRENT[0] is A, 'make_wreck needs the most recent Assembly (part ids are module-global)'
    rng = np.random.default_rng(rc['seed'])
    Gm = rx(alpha)                                              # model -> ground frame (gravity aligned, z up)
    st = dict(R=A.R.sel(np.ones(len(A.R), bool)),
              C=[c.sel(np.ones(len(c), bool)) if c is not None else None for c in A.C])

    def S_all():
        return [st['R']] + [c for c in st['C'] if c is not None]
    for s in S_all():
        s.rigid(np.ones(len(s), bool), Gm)
    st['R'] = st['R'].sel(~A.parts(st['R'], 'glass'))           # canopy + door window glass: gone
    st['C'] = [c.sel(~A.parts(c, 'glass')) if c is not None else None for c in st['C']]
    up = np.array([0, 0, 1.0])
    ax_y = Gm @ np.array([0, 1.0, 0]); ax_x = np.array([1.0, 0, 0])
    soot = A.slot('soot')

    def pts(*names):
        m = A.parts(st['R'], *names)
        return st['R'].P[m].reshape(-1, 3)
    h = min(pts('wheelL')[:, 2].min(), pts('wheelR')[:, 2].min(), pts('gearN')[:, 2].min())
    h += rc['ground_offset'] * M                                  # the real terrain sits a little above the wheels
    log('wreck: ground at %.3f m in the ground frame (alpha %.4f)' % (h / M, alpha))

    # ---------------------------------------------------------------- 1. tail torn off
    n_cut = ax_y.copy(); d_cut = float(n_cut @ (Gm @ np.array([0, rc['tail_cut_y'] * M, 0])))
    tail_id = pid('tailhull')
    for s in S_all():
        side = s.split(n_cut, d_cut, mask=A.parts(s, 'hull'))
        s.d['part'][A.parts(s, 'hull') & (side < 0)] = tail_id
    for s in S_all():                                             # jagged tear line (same function for all soups)
        on = np.abs(s.P @ n_cut - d_cut) < 2.0
        if on.any():
            P = s.d['P'].copy(); P[on] = _jag(P[on], n_cut, 0.32 * M, 0.22 * M, rc['seed'] + 1)
            s.d['P'] = P
    ring = st['R'].P[A.parts(st['R'], 'hull', 'tailhull')].reshape(-1, 3)
    ring_c = ring[np.abs(ring @ n_cut - d_cut) < 0.4 * M].mean(0)

    def crumple(p, reach=0.9 * M, amp=0.2 * M):
        q = p - ring_c
        ax_d = q @ n_cut
        rad = q - np.outer(ax_d, n_cut)
        rl = np.linalg.norm(rad, axis=1, keepdims=True).clip(1.0)
        fall = np.clip(1 - np.abs(ax_d) / reach, 0, 1)
        k = (noise3(p, 0.3 * M, rc['seed'] + 2, octaves=2) - 0.5) * 2 * amp * fall
        return p + rad / rl * k[:, None]
    for s in S_all():
        m_ = A.parts(s, 'hull', 'tailhull')
        s.apply(m_, crumple)
    R = st['R']
    near = A.parts(R, 'hull', 'tailhull') & (np.abs(R.P @ n_cut - d_cut).min(1) < 1.4 * M)
    inner = R.sel(near).flip()
    inner.d['slot'][:] = soot
    st['R'] = Soup.cat([R, inner])

    # ---------------------------------------------------------------- 2. burnt-through holes (render only)
    for k, (c_m, r_m) in enumerate(rc['holes']):
        R = st['R']
        c = Gm @ (np.array(c_m) * M); r = r_m * M
        skin = A.parts(R, 'hull', 'body') & (R.slot != soot)
        dist0 = np.linalg.norm(R.P.mean(1) - c, axis=1)
        region = skin & (dist0 < r * 1.4)
        for ax in (ax_x, ax_y, up):
            region = R.subdivide_along(region, c, ax, 0.4 * M)
        skin = A.parts(R, 'hull', 'body') & (R.slot != soot)
        cen = R.P.mean(1)
        dist = np.linalg.norm(cen - c, axis=1)
        wob = 0.65 + 0.7 * noise3(cen, 0.35 * M, rc['seed'] + 10 + k, octaves=2)
        hole = skin & (dist < r * wob)
        inner = R.sel(skin & ~hole & (dist < max(r * 2.0, 1.3 * M))).flip()   # the inside of the skin round the hole
        hole |= A.parts(R, 'hull', 'body') & (R.slot == soot) & (dist < r * wob)   # (and open older soot patches)
        inner.d['slot'][:] = soot
        st['R'] = Soup.cat([R.sel(~hole), inner])
        C0 = st['C'][0]                                           # no invisible lid over the hole (fine collision)
        if C0 is not None:
            reg0 = A.parts(C0, 'hull', 'body') & (np.linalg.norm(C0.P.mean(1) - c, axis=1) < r * 1.4)
            for ax in (ax_x, ax_y, up):
                reg0 = C0.subdivide_along(reg0, c, ax, 0.4 * M)
            cc0 = C0.P.mean(1)                                    # same hole test as the render faces
            wob0 = 0.65 + 0.7 * noise3(cc0, 0.35 * M, rc['seed'] + 10 + k, octaves=2)
            lid = A.parts(C0, 'hull', 'body') & (np.linalg.norm(cc0 - c, axis=1) < r * wob0)
            st['C'][0] = C0.sel(~lid)
        log('wreck: hole %d: %d triangles burnt away, %d inner faces' % (k, int(hole.sum()), len(inner)))

    # ---------------------------------------------------------------- 3. gear collapsed, right door jammed open
    for name, deg in rc['gear'].items():
        P = pts(name)
        if not len(P):
            continue
        top = P[P[:, 2] > P[:, 2].max() - 0.15 * M].mean(0)
        axis = ax_y if name != 'gearN' else ax_x
        for s in S_all():
            s.rigid(A.parts(s, name), axis_angle(axis, math.radians(deg)), pivot=top)
    P = pts('doorR')
    if len(P):
        topv = P[P[:, 2] > P[:, 2].max() - 0.1 * M]
        hinge = topv[np.argmax(topv @ ax_y)]                     # top front corner (still on the rail)
        Rdoor = axis_angle(ax_y, math.radians(-rc['door_r'][1])) @ axis_angle(ax_x, math.radians(rc['door_r'][0]))
        for s in S_all():
            s.rigid(A.parts(s, 'doorR'), Rdoor, pivot=hinge)

    # ---------------------------------------------------------------- 4. rotors broken
    for tag, atta_name in (('r1', '740_02_1'), ('r2', '740_03_1')):
        hits = [t for nm, Rm, t in A.atta if nm == atta_name]
        if not hits:
            continue
        c = Gm @ hits[0]
        u = Gm @ np.array([0, 0, 1.0])
        for b, op in enumerate(rc[tag]):
            name = '%sblade%d' % (tag, b)
            if name not in PART_NAMES:
                continue
            Pb = pts(name)
            v = Pb - c; v -= np.outer(v @ u, u)
            s_dir = v.mean(0); s_dir /= np.linalg.norm(s_dir)
            w = np.cross(s_dir, u)
            a = (Pb - c) @ s_dir
            a0 = a.min()
            if op[0] == 'break':
                span_cut = a0 + op[1] * M
                out_id = pid(name + '_out')
                for s in S_all():
                    side = s.split(s_dir, float(s_dir @ c + span_cut), mask=A.parts(s, name))
                    s.d['part'][A.parts(s, name) & (side > 0)] = out_id
                    on = A.parts(s, name, name + '_out')[:, None] & (np.abs((s.P - c) @ s_dir - span_cut) < 2.0)
                    if on.any():
                        P2 = s.d['P'].copy(); P2[on] = _jag(P2[on], s_dir, 0.13 * M, 0.2 * M, rc['seed'] + 20 + b)
                        s.d['P'] = P2
                droop, length = op[2], op[1] * M
            else:
                droop, length = op[1], a.max() - a0
            if droop > 0 and length > 2.5 * M:                    # smooth bend: slice the (remaining) blade
                for s in S_all():                                  # (collision too, or it would cut the chord)
                    s.subdivide_along(A.parts(s, name), c, s_dir, 1.3 * M)
            bend, bend_n = _bend_fns(c, s_dir, u, w, math.radians(droop) / max(length, 1.0), a0 + 0.15 * M)
            for s in S_all():
                s.apply(A.parts(s, name), bend, bend_n)
        if tag == 'r2' and rc.get('r2_tilt'):
            mast = c - u * 1.2 * M
            Rt = axis_angle(ax_x, math.radians(rc['r2_tilt'])) @ axis_angle(ax_y, math.radians(-6.0))
            names = [n for n in PART_NAMES if n.startswith('r2') and not n.endswith('_out')]
            for s in S_all():
                s.rigid(A.parts(s, *names), Rt, pivot=mast)

    # ---------------------------------------------------------------- 5. the body settles on its belly
    loose = set(TAIL_PARTS) | {n for k in rc['debris'] for n in k.split('+')} | {n for n in PART_NAMES if n.endswith('_out')}
    attached = [n for n in PART_NAMES if n not in loose]
    Pb = pts('hull')
    pivot = np.array([Pb[:, 0].mean(), Pb[:, 1].mean(), Pb[:, 2].min()])
    Rb = axis_angle(ax_y, math.radians(rc['body_roll'])) @ axis_angle(ax_x, math.radians(rc['body_pitch']))
    Pr = (Pb - pivot) @ Rb.T + pivot
    dz = (h - rc['body_sink'] * M) - Pr[:, 2].min()
    log('wreck: body drops %.2f m' % (-dz / M))
    tb = np.array([0, 0, dz])
    for s in S_all():
        s.rigid(A.parts(s, *attached), Rb, tb, pivot)

    # ---------------------------------------------------------------- 6. the torn tail lies beside the stump
    Pt = pts('tailhull')
    ring_t = Pt[np.abs(Pt @ n_cut - d_cut) < 0.3 * M]
    Ph = pts('hull')
    back_proj = ((Ph - tb - pivot) @ Rb) + pivot                 # stump vertices back in the pre-pose frame
    ring_s = Ph[np.abs(back_proj @ n_cut - d_cut) < 0.3 * M]
    ct = ring_t.mean(0); cs = ring_s.mean(0)
    Rt = (axis_angle(up, math.radians(rc['tail_yaw'])) @ axis_angle(ax_y, math.radians(rc['tail_roll']))
          @ axis_angle(ax_x, -alpha + math.radians(1.5)))
    back = -(Rb @ ax_y); back[2] = 0; back /= np.linalg.norm(back)
    side_v = np.cross(up, back)
    tgt = cs + back * rc['tail_gap'][1] * M + side_v * rc['tail_gap'][0] * M
    for s in S_all():
        s.rigid(A.parts(s, *TAIL_PARTS), Rt, tgt - ct, ct)
    Pt2 = pts(*TAIL_PARTS)
    lowest = np.sort(Pt2[:, 2])[max(0, int(len(Pt2) * 0.01))]
    for s in S_all():
        s.rigid(A.parts(s, *TAIL_PARTS), np.eye(3), np.array([0, 0, h - 0.04 * M - lowest]))

    # ---------------------------------------------------------------- 7. debris on the ground
    Ph = pts('hull')
    centre = np.array([Ph[:, 0].mean(), Ph[:, 1].mean(), h])
    placed = dict(rc['debris'])
    for k, n in enumerate(n for n in PART_NAMES if n.endswith('_out') and n not in placed):
        a_ = math.radians(40 + 97 * k)                           # (a broken piece nobody placed: around the wreck)
        placed[n] = (9.0 * math.cos(a_), 9.0 * math.sin(a_), 60.0 * k)
    for name, (dx, dy, yaw) in placed.items():
        names = [n for n in name.split('+') if n in PART_NAMES]
        if not names:
            continue
        P = pts(*names)
        if not len(P):
            continue
        cen0 = (P.min(0) + P.max(0)) / 2
        Q = P - P.mean(0)
        ev, evec = np.linalg.eigh(Q.T @ Q)
        thin = evec[:, 0] * (1 if evec[2, 0] >= 0 else -1)     # thinnest principal axis -> vertical (lies flat)
        cr = np.cross(thin, up); sn = np.linalg.norm(cr)
        Rflat = axis_angle(cr, math.atan2(sn, thin @ up)) if sn > 1e-6 else np.eye(3)
        tilt_ax = rng.normal(size=3); tilt_ax[2] = 0
        Rd = axis_angle(up, math.radians(yaw)) @ axis_angle(tilt_ax, math.radians(rng.uniform(2, 7))) @ Rflat
        P2 = (P - cen0) @ Rd.T
        tgt = centre + np.array([dx * M, dy * M, 0.04 * M - P2[:, 2].min()])
        for s in S_all():
            s.rigid(A.parts(s, *names), Rd, tgt - cen0, cen0)

    # ---------------------------------------------------------------- 7b. scorched ground (alpha-blended decal)
    if rc.get('scorch'):
        hl, hw, lift_s = rc['scorch']
        Ph = pts('hull')
        cx, cy = Ph[:, 0].mean(), Ph[:, 1].mean() - 1.0 * M
        nseg, nring = 28, 5
        rr = np.linspace(0, 1, nring + 1)
        th = np.linspace(0, 2 * math.pi, nseg + 1)[:-1]
        V = [(cx, cy)]
        for r_ in rr[1:]:
            for t_ in th:
                wob = 1.0 + 0.18 * (noise3(np.array([[math.cos(t_) * 3 * M, math.sin(t_) * 3 * M, r_ * M]]), 1.0 * M, rc['seed'] + 50)[0] - 0.5) * 2
                V.append((cx + math.cos(t_) * hw * M * r_ * wob, cy + math.sin(t_) * hl * M * r_ * wob))
        V = np.array(V)
        idx = lambda ring, k: 1 + (ring - 1) * nseg + (k % nseg)
        T = []
        for k in range(nseg):
            T.append((0, idx(1, k + 1), idx(1, k)))                  # clockwise seen from above = front face
        for ring in range(1, nring):
            for k in range(nseg):
                a_, b_, c_, d_ = idx(ring, k), idx(ring, k + 1), idx(ring + 1, k + 1), idx(ring + 1, k)
                T += [(a_, b_, c_), (a_, c_, d_)]
        T = np.array(T)
        P3 = np.column_stack([V, np.full(len(V), h + lift_s * M)])[T]
        UV = np.stack([(P3[..., 0] - cx) / (2 * hw * M * 1.2) + 0.5, (P3[..., 1] - cy) / (2 * hl * M * 1.2) + 0.5], -1)
        N = np.zeros_like(P3); N[..., 2] = 1
        dec = Soup(P=P3, N=N, UV=UV, slot=np.full(len(T), A.slot('scorch')), flags=np.full(len(T), 0x1904),
                   part=np.full(len(T), pid('scorch')))
        st['R'] = Soup.cat([st['R'], dec])

    # ---------------------------------------------------------------- 8. crushed where it meets the ground
    lift = rc['clamp_lift'] * M
    for s in S_all():
        P = s.d['P']
        low = (P[..., 2] < h + lift) & ~A.parts(s, 'scorch')[:, None]
        if low.any():
            jitter = noise3(P[low], 0.3 * M, rc['seed'] + 40, octaves=2) * 0.03 * M
            P[..., 2][low] = h + lift + jitter
    # ---------------------------------------------------------------- 9. collision sanity: no invisible walls
    # the coarse hull (mesh 1) of the rotors is a set of hub-to-tip boxes that cannot follow broken blades: drop it
    # (mesh 0 keeps exact rotor collision); then drop any face that ended > 1 m from the rendered surface (the intact
    # coarse hull is within 0.88 m everywhere)
    from scipy.spatial import cKDTree
    if st['C'][1] is not None:
        rot = [n for n in PART_NAMES if n.startswith(('r1', 'r2'))]
        st['C'][1] = st['C'][1].sel(~A.parts(st['C'][1], *rot))
    skin = st['R'].sel(~A.parts(st['R'], 'scorch'))
    tree = cKDTree(surface_samples(skin))
    for k, c in enumerate(st['C']):
        if c is None or not len(c):
            continue
        d, _ = tree.query(c.P.reshape(-1, 3))
        far = d.reshape(-1, 3).max(1) > 1.0 * M
        if far.any():
            log('wreck: collision mesh %d: %d faces dropped (> 1 m from the wreck surface)' % (k, int(far.sum())))
            st['C'][k] = c.sel(~far)
    for s in S_all():                                             # back to the model frame
        s.rigid(np.ones(len(s), bool), Gm.T)
    R, C = st['R'], st['C']
    log('wreck: %d render triangles, collision %s' % (len(R), [len(c) if c is not None else 0 for c in C]))
    return R, C, h


# =============================================================================================== charred textures
def bake_surface_maps(S, slot, W, H):
    """texel -> 3D position / normal of the surface that uses it (triangles of `slot` rasterised in UV space; tiled
    triangles are wrapped into [0,1) when they stay inside one tile). -> pos (H,W,3), nrm (H,W,3), covered (H,W)"""
    pos = np.zeros((H * W, 3)); nrm = np.zeros((H * W, 3)); cov = np.zeros(H * W, bool)
    m = S.slot == slot
    P, N, UV = S.P[m], S.N[m], S.UV[m]
    fl = np.floor(UV.min(1))
    one_tile = (np.floor(UV.max(1) - 1e-6) == fl).all(1)
    for t in np.nonzero(one_tile)[0]:
        uv = UV[t] - fl[t]
        x = uv[:, 0] * W - 0.5; y = uv[:, 1] * H - 0.5
        x0, x1 = int(max(0, math.floor(x.min()))), int(min(W - 1, math.ceil(x.max())))
        y0, y1 = int(max(0, math.floor(y.min()))), int(min(H - 1, math.ceil(y.max())))
        if x0 > x1 or y0 > y1:
            continue
        A_ = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0])
        if abs(A_) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        w1 = ((gx - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (gy - y[0])) / A_
        w2 = ((x[1] - x[0]) * (gy - y[0]) - (gx - x[0]) * (y[1] - y[0])) / A_
        w0 = 1 - w1 - w2
        ins = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        if not ins.any():
            continue
        ix = (gy * W + gx)[ins]
        pos[ix] = np.outer(w0[ins], P[t, 0]) + np.outer(w1[ins], P[t, 1]) + np.outer(w2[ins], P[t, 2])
        nn = np.outer(w0[ins], N[t, 0]) + np.outer(w1[ins], N[t, 1]) + np.outer(w2[ins], N[t, 2])
        nrm[ix] = nn / np.linalg.norm(nn, axis=1, keepdims=True).clip(1e-9)
        cov[ix] = True
    pos = pos.reshape(H, W, 3); nrm = nrm.reshape(H, W, 3); cov = cov.reshape(H, W)
    for _ in range(6):                                           # bleed the maps a few texels past the islands
        if cov.all():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src_c = np.roll(cov, (dy, dx), (0, 1))
            fill = ~cov & src_c
            pos[fill] = np.roll(pos, (dy, dx), (0, 1))[fill]; nrm[fill] = np.roll(nrm, (dy, dx), (0, 1))[fill]
            cov = cov | fill
    return pos, nrm, cov


def _resize(img, W, H):
    from PIL import Image
    out = []
    for k in range(img.shape[2]):
        ch = Image.fromarray(np.asarray(img[..., k], np.float32), mode='F').resize((W, H), Image.BILINEAR)
        out.append(np.asarray(ch))
    return np.stack(out, 2)


def _smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def char_texture(rgba, pos=None, nrm=None, cov=None, seed=7, holes=(), interior=False):
    """realistic burnt paint for one texture (float RGBA in, float RGBA out). With 3D maps (model frame of the
    INTACT helicopter, world units) the damage follows the real surfaces, the way a burnt-out airframe looks:
      lower sides  - the paint survives, scorched dark and blistered, soot streaks climbing up from below,
      middle       - heavy black soot with flakes of paint left,
      engine deck / around the burnt-through holes - paint gone: dull bare aluminium, white-grey oxide / ash,
                     black soot rims, rust-brown on the steel parts,
      belly        - scraped bright where it slid on the ground, sand dirt,
      upward faces - grey ash; plus burnt pin holes and blisters where it was hottest."""
    H, W = rgba.shape[:2]
    rgb = rgba[..., :3].astype(np.float64).reshape(-1, 3)
    lum = 0.3 * rgb[:, 0] + 0.59 * rgb[:, 1] + 0.11 * rgb[:, 2]
    if pos is None or interior:
        yy, xx = np.mgrid[0:H, 0:W]
        pos = np.stack([xx * 6.0, yy * 6.0, np.zeros_like(xx, float)], 2)
        nrm = np.zeros((H, W, 3)); nrm[..., 2] = 1.0
        cov = np.ones((H, W), bool)
    P = pos.reshape(-1, 3); Nn = nrm.reshape(-1, 3)
    z = P[:, 2] / M
    nz = Nn[:, 2]
    n_big = noise3(P, 0.9 * M, seed, octaves=4)
    n_streak = noise3(P, 0.35 * M, seed + 1, octaves=3, stretch=(0.3, 0.3, 4.0))     # vertical soot streaks
    n_blot = noise3(P, 0.4 * M, seed + 2, octaves=4)
    n_fine = noise3(P, 0.07 * M, seed + 3, octaves=2)
    n_scr = noise3(P, 0.05 * M, seed + 4, octaves=2, stretch=(1.0, 14.0, 0.6))          # scratches along the body
    n_flake = noise3(P, 0.12 * M, seed + 5, octaves=3)
    heat = 0.15 + 0.85 * _smooth(z, 2.9, 6.2)
    for c_m, r_m in holes:
        d = np.linalg.norm(P / M - np.asarray(c_m), axis=1)
        heat = heat + 0.8 * np.exp(-(d / (r_m * 2.6)) ** 2)
    if interior:
        heat = 0.55 + 0.4 * n_big
    heat = np.clip(heat + 0.45 * (n_big - 0.5) + 0.2 * (n_blot - 0.5), 0, 1.3)
    one = np.ones((len(P), 1))
    # zone A: scorched, blistered paint (darkened, desaturated, a little browned)
    grey = lum[:, None] * one
    scorched = (0.5 * rgb + 0.5 * grey) * (0.30 + 0.22 * n_fine[:, None]) * np.array([1.0, 0.92, 0.82])
    streak = _smooth(n_streak, 0.38, 0.7) * (0.6 + 0.4 * _smooth(z, 2.2, 4.0))
    scorched = scorched * (1 - 0.8 * streak[:, None]) + 0.03 * streak[:, None]
    # zone B: soot with paint flakes
    soot = np.array([0.040, 0.036, 0.033]) * (0.8 + 0.6 * n_fine[:, None])
    flakes = _smooth(n_flake, 0.62, 0.7)[:, None]
    sooty = soot * (1 - flakes) + scorched * 0.6 * flakes
    # zone C: bare metal, white oxide / ash, rust on steel, soot rims
    metal = np.array([0.40, 0.40, 0.39]) * (0.75 + 0.45 * n_fine[:, None])
    oxide = _smooth(n_blot, 0.55, 0.75)[:, None]
    metal = metal * (1 - oxide) + np.array([0.60, 0.59, 0.56]) * (0.85 + 0.25 * n_fine[:, None]) * oxide
    rusty = _smooth(n_big, 0.62, 0.8)[:, None] * 0.7
    metal = metal * (1 - rusty) + np.array([0.30, 0.16, 0.07]) * (0.7 + 0.6 * n_fine[:, None]) * rusty
    kA = 1 - _smooth(heat, 0.32, 0.5)
    kC = _smooth(heat, 0.78, 0.98)
    kB = np.clip(1 - kA - kC, 0, 1)
    out = scorched * kA[:, None] + sooty * kB[:, None] + metal * kC[:, None]
    rim = np.clip(1 - np.abs(heat - 0.8) * 6.0, 0, 1) * 0.85                     # black soot rim around the bare metal
    out = out * (1 - rim[:, None]) + soot * rim[:, None]
    blis = _smooth(n_fine, 0.74, 0.86) * _smooth(heat, 0.45, 0.9)                 # blisters / pin holes
    out = out * (1 - 0.92 * blis[:, None]) + 0.012 * blis[:, None]
    if not interior:
        low = _smooth(-nz, 0.2, 0.7) * (1 - _smooth(z, 2.8, 3.8))                # belly: dirt + bright scratches
        scr = _smooth(n_scr, 0.55, 0.72) * low
        dirt = np.array([0.40, 0.34, 0.25]) * (0.7 + 0.5 * n_fine[:, None])
        out = out * (1 - 0.6 * low[:, None]) + dirt * 0.6 * low[:, None]
        out = out * (1 - scr[:, None]) + np.array([0.58, 0.58, 0.56]) * (0.8 + 0.3 * n_fine[:, None]) * scr[:, None]
    ash = _smooth(nz, 0.4, 0.8) * _smooth(n_big, 0.4, 0.6) * 0.55                  # ash on upward faces
    out = out * (1 - ash[:, None]) + np.array([0.42, 0.41, 0.39]) * (0.85 + 0.3 * n_fine[:, None]) * ash[:, None]
    out = np.clip(out, 0, 1).reshape(H, W, 3)
    unc = ~cov
    if unc.any():                                                 # texels no surface uses: plain soot
        out[unc] = np.array([0.05, 0.045, 0.04])
    a = rgba[..., 3:4]
    return np.concatenate([out, a], 2).astype(np.float32)


def soot_texture(size=128, seed=5):
    """the inside of the burnt skin: matt black-brown soot"""
    yy, xx = np.mgrid[0:size, 0:size]
    P = np.stack([xx * 40.0, yy * 40.0, np.zeros_like(xx, float)], 2).reshape(-1, 3)
    n = noise3(P, 600.0, seed, octaves=4).reshape(size, size)
    base = 0.045 + 0.07 * n
    rgb = np.stack([base * 1.15, base * 1.0, base * 0.9], 2)
    return np.concatenate([rgb, np.ones((size, size, 1))], 2).astype(np.float32)


def scorch_texture(size=256, seed=21):
    """burnt sand under the wreck: soot-black centre, grey-brown ash, ragged transparent edge (alpha)"""
    yy, xx = np.mgrid[0:size, 0:size]
    u = (xx + 0.5) / size * 2 - 1; v = (yy + 0.5) / size * 2 - 1
    r = np.sqrt(u * u + v * v) * 1.2
    P = np.stack([u * 8 * M, v * 8 * M, np.zeros_like(u)], 2).reshape(-1, 3)
    n1 = noise3(P, 1.2 * M, seed, octaves=4).reshape(size, size)
    n2 = noise3(P, 0.25 * M, seed + 1, octaves=3).reshape(size, size)
    edge = r + 0.35 * (n1 - 0.5)
    alpha = np.clip((1.0 - edge) / 0.35, 0, 1) ** 1.3 * (0.65 + 0.3 * n2)
    soot = np.array([0.05, 0.045, 0.04]); ash = np.array([0.24, 0.22, 0.19])
    k = np.clip((r - 0.25) / 0.6 + 0.4 * (n2 - 0.5), 0, 1)[..., None]
    rgb = soot * (1 - k) + ash * k
    rgb = rgb * (0.8 + 0.4 * n2[..., None])
    return np.concatenate([rgb, alpha[..., None]], 2).astype(np.float32)


def tex_mode67(rgba):
    """float RGBA -> .tex bytes, 32-bit A8R8G8B8 with a full mip chain (mode 67, as the shipped alpha textures)"""
    H, W = rgba.shape[:2]
    hdr = bytearray(b'LOOP' + struct.pack('<I', 11) + struct.pack('<I', 67) + b'\0' * 8 + b'\0' * 12)
    struct.pack_into('<HHHHHH', hdr, 20, 5, W, H, W, H, 4)
    n = 0; w_, h_ = W, H
    while True:                                                   # (chain ends where the SHORT side is 1)
        n += w_ * h_
        if min(w_, h_) == 1:
            break
        w_, h_ = max(1, w_ // 2), max(1, h_ // 2)
    dummy = bytes(hdr) + b'\0' * (4 * n)
    return igitex.encode_like(dummy, rgba)


def tex_mode2(rgba, template=None):
    """float RGBA -> .tex bytes, 16-bit A1R5G5B5 (mode 2, no mips) with a 32-byte LOOP v11 header"""
    H, W = rgba.shape[:2]
    if template is None:
        hdr = bytearray(b'LOOP' + struct.pack('<I', 11) + struct.pack('<I', 2) + b'\0' * 8 + b'\0' * 12)
        struct.pack_into('<H', hdr, 20, 5)
    else:
        hdr = bytearray(template[:32])
        assert struct.unpack_from('<I', hdr, 8)[0] == 2
    struct.pack_into('<HHHHH', hdr, 22, W, H, W, H, 2)
    q = np.clip(np.rint(np.clip(rgba[..., :3], 0, 1) * 31), 0, 31).astype(np.uint16)
    a = (rgba[..., 3] >= 0.5).astype(np.uint16) << 15
    px = a | (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
    return bytes(hdr) + px.astype('<u2').tobytes()


# =============================================================================================== build the model
def build_mef(A, R, C, slot_order):
    """wreck soups -> mefmesh.Mef (type 0, no attachments). slot_order = [soup slot ids] in INST order."""
    slot_values = {sid: k for k, sid in enumerate(slot_order)}
    S = R.sel(np.isin(R.slot, list(slot_order) + [0xFFFF]))
    groups = weld_groups(S, slot_values)
    coll = [weld_coll(c, A.mats) if c is not None and len(c) else mefmesh.CollMesh(np.zeros((0, 3)), np.zeros((0, 3)), [], np.zeros(0, mefmesh.TAMC_DT))
            for c in C]
    tmpl = A.body_mef
    r = mefmesh.RigidModel(groups, coll, hsem=tmpl.hsem, atta=np.zeros(0, mefmesh.ATTA_DT), magic=np.zeros(0, mefmesh.XTVM_DT),
                           portals=dict(TROP=np.zeros(0, mefmesh.TROP_DT), XVTP=np.zeros(0, mefmesh.XVTP_DT),
                                        CFTP=np.zeros(0, mefmesh.CFTP_DT)), glows=None, typ=0)
    m = r.to_mef(recompute_spheres=True, recompute_centres=True, rebuild_trees=True)
    return m


def verify_mef(m):
    """structural checks on a built wreck -> list of problems"""
    probs = list(mefmesh.semantic_check(m))
    m2 = mefmesh.Mef.read(m.write())
    if m2.write() != m.write():
        probs.append('re-read differs')
    for V, F, S in zip(m.all('XTVC'), m.all('ECFC'), m.all('HPSC')):
        probs += mefmesh.check_tree(S, V['pos'], F['v'], tol=0.0)
    X = m.get('XTRV')
    if not np.isfinite(X['pos']).all() or not np.isfinite(X['nrm']).all():
        probs.append('non-finite vertices')
    if len(X) > 65535:
        probs.append('too many vertices')
    h = m.hsem
    P = X['pos'].astype(float)
    if np.linalg.norm(P - h['sph_render'][:3], axis=1).max() > h['sph_render'][3] + 1:
        probs.append('render sphere')
    allc = np.concatenate([V['pos'] for V in m.all('XTVC')]).astype(float)
    if np.linalg.norm(allc - h['sph_coll'][:3], axis=1).max() > h['sph_coll'][3] + 1:
        probs.append('collision sphere')
    if np.linalg.norm(np.concatenate([allc, P]), axis=1).max() > h['radius'] + 1:
        probs.append('radius')
    return probs


# =============================================================================================== previews
VIEWS = [('front_left', (-60000, 52000, 30000)), ('rear_right', (62000, -42000, 32000)), ('rear_left', (-48000, -66000, 22000))]


def render_views(R, textures, h, prefix, alpha=PLACEMENT_ALPHA, size=(1100, 700), ss=2, views=VIEWS, target=(0, -3000, 9500),
                 fov=46, colors=None, ground_color=(0.74, 0.64, 0.47), alpha_slots=()):
    """software-render a soup (model frame) on the flat ground of the intact helicopter -> [png paths].
    textures = {soup slot id: RGBA}; colors = {soup slot id: rgb} for untextured slots."""
    import mefrender
    Gm = rx(alpha)
    sc = mefrender.Scene()
    mids = {}
    for sid in np.unique(R.slot):
        sid = int(sid)
        tex = textures.get(sid) if textures else None
        mids[sid] = sc.material(tex, color=(colors or {}).get(sid, (0.05, 0.05, 0.05)), tex_alpha=sid in alpha_slots)
        m = R.slot == sid
        sc.add_tris(R.P[m] @ Gm.T, R.N[m] @ Gm.T, R.UV[m], mids[sid])
    sc.add_ground(z=h, half=110000, color=ground_color)
    out = []
    tgt = Gm @ np.asarray(target, float)
    for name, eye in views:
        im = sc.render(np.asarray(eye, float), tgt, size=size, fov=fov, ss=ss)
        p = '%s_%s.png' % (prefix, name)
        im.save(p); out.append(p)
    return out


# =============================================================================================== textures for a wreck
INTERIOR_TEXTURES = ('731_27_1',)          # tiled cabin-interior texture: generic char (no 3D map)


def make_textures(A, R, bank, recipe=None, body_size=(2048, 1024), atta_size=(1024, 512), log=print):
    """-> {soup slot id: float RGBA} for every slot the wreck soup R uses (glass slots are gone with the glass)"""
    rc = dict(DEFAULT_RECIPE); rc.update(recipe or {})
    out = {}
    used = sorted(int(s) for s in np.unique(R.slot) if s != 0xFFFF)
    for sid in used:
        name = A.slots[sid]
        if name == 'scorch':
            out[sid] = scorch_texture()
            log('wreck: texture slot %d scorch -> 256x256 (alpha)' % sid)
            continue
        if name == 'soot':
            out[sid] = soot_texture()
            log('wreck: texture slot %d soot -> 128x128' % sid)
            continue
        base = name.split('@')[0]
        if base not in bank.tex:
            raise KeyError('texture %s is not in the level bank' % base)
        src = igitex.decode(bank.tex[base])
        if base in INTERIOR_TEXTURES:
            out[sid] = char_texture(src, interior=True, seed=8 + sid)
        else:
            Wt, Ht = atta_size if '@' in name else body_size
            src = _resize(src, Wt, Ht) if src.shape[:2] != (Ht, Wt) else src
            pos, nrm, cov = bake_surface_maps(A.R, sid, Wt, Ht)
            out[sid] = char_texture(src, pos, nrm, cov, seed=7 + sid, holes=rc['holes'])
        log('wreck: texture slot %d %s -> %dx%d charred' % (sid, name, out[sid].shape[1], out[sid].shape[0]))
    return out


# =============================================================================================== level integration
def _ensure_overlay(overlay_dir, level_name, game=GAME):
    """the overlay's <level>.mtp + models/<level>.res + textures/<level>.res; copied from the shipped level when the
    overlay does not have them yet (Sandstorm's overlay already has merged ones from the briefcase transplant)"""
    import shutil
    base = level_name.replace(BACKSLASH, '/').split('/')[-1]
    paths = dict(mtp=os.path.join(overlay_dir, base + '.mtp'),
                 models=os.path.join(overlay_dir, 'models', base + '.res'),
                 textures=os.path.join(overlay_dir, 'textures', base + '.res'))
    src = None
    for k, p in paths.items():
        if not os.path.exists(p):
            src = src or level_dir(level_name, game)
            sb = os.path.basename(src)
            rel = {'mtp': sb + '.mtp', 'models': os.path.join('models', sb + '.res'),
                   'textures': os.path.join('textures', sb + '.res')}[k]
            os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copyfile(os.path.join(src, rel), p)           # copy (never a hard link to the game files)
    return paths


def _lod_entry(overlay_dir, src, dst, level_name, game=GAME):
    """give dst the LOD cut-off of src in the overlay's lod.qvm (models without an entry vanish at ~10 x radius)"""
    import igiqvm, lodfix
    from igiqvm import Call, Int, Str, Flt
    lp = os.path.join(overlay_dir, 'lod.qvm')
    if not os.path.exists(lp):                                   # start from the level's own (or the global) table
        import shutil
        try:
            lv = os.path.join(level_dir(level_name, game), 'lod.qvm')
        except FileNotFoundError:
            lv = None
        shutil.copyfile(lv if lv and os.path.exists(lv) else os.path.join(game, 'lod.qvm'), lp)
    ver, st, ent = lodfix.read(lp)
    _, _, gent = lodfix.read(os.path.join(game, 'lod.qvm'))
    vals = ent.get(src.lower()) or gent.get(src.lower()) or [60.0, 120.0, 240.0, 480.0, 1500.0]
    vals = list(vals); vals[4] = max(vals[4], 1000.0)
    if dst.lower() in ent:
        return ent[dst.lower()]
    row = Call('Task_New', [Int(-1), Str('ModelLODSettings'), Str(dst), Str(dst)] + [Flt(x) for x in vals])
    data = igiqvm.compile_stmts(list(st) + [row], ver)
    tmp = lp + '.tmp'
    open(tmp, 'wb').write(data)
    _, _, ent2 = lodfix.read(tmp)
    assert ent2.get(dst.lower()) == vals, ent2.get(dst.lower())
    os.replace(tmp, lp)
    return vals


def add_wreck_model(overlay_dir, level_name, src='740_01_1', dst='w740_01_1', recipe=None, alpha=PLACEMENT_ALPHA,
                    preview_dir=None, log=print):
    """build the wreck of `src` and register it as virtual model `dst` in a mission overlay (mirrors
    burnt.add_burnt_model): overlay_dir/<level>.mtp gets MODS + VNAM/INST + TEXF/GTT entries, models/<level>.res the
    new <dst>.mef, textures/<level>.res the charred textures (<dst>_0.. names), lod.qvm (if present) a cut-off line.
    The wreck has the frame of the intact model: place it with the intact object's exact position + orientation.
    -> report dict (counts, texture names, problems = [] when every check passed)"""
    game_root = os.path.normcase(os.path.realpath(GAME))
    ov_real = os.path.normcase(os.path.realpath(overlay_dir))
    try:
        inside = os.path.commonpath([game_root, ov_real]) == game_root
    except ValueError:                                            # (different drives)
        inside = False
    if inside:
        raise ValueError('refusing to write into the game folder: %s' % overlay_dir)
    paths = _ensure_overlay(overlay_dir, level_name)
    bank = Bank(paths['mtp'], paths['models'], paths['textures'])
    m = bank.m
    if dst in m['VNAM']:
        raise ValueError('%s already in %s (rebuild the overlay first)' % (dst, paths['mtp']))
    if src not in m['VNAM']:
        raise ValueError('%s is not a model of %s' % (src, level_name))
    A = Assembly(bank, src)
    R, C, h = make_wreck(A, alpha=alpha, recipe=recipe, log=log)
    texs = make_textures(A, R, bank, recipe=recipe, log=log)
    slot_order = sorted(texs)
    mef = build_mef(A, R, C, slot_order)
    probs = verify_mef(mef)
    if probs:
        raise ValueError('wreck mesh failed its checks (nothing written): %s' % probs)
    data = mef.write()
    # ---- textures -> bank + TEXF/GTT
    form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
    have = {n for n, t, b in ilff.entries(ch) if n}
    gtts, names = [], []
    for k, sid in enumerate(slot_order):
        tname = '%s_%d' % (dst, k)
        base = A.slots[sid].split('@')[0]
        tmpl = bank.tex.get(base)
        if A.slots[sid] == 'scorch':
            tb = tex_mode67(texs[sid])
        else:
            tb = tex_mode2(texs[sid], tmpl if tmpl is not None and igitex.header(tmpl)[0] == 2 else None)
        key = 'LOCAL:textures/%s.tex' % tname
        assert key not in have and tname not in m['TEXF'], tname
        ch.append((b'NAME', key.encode('latin1') + b'\0', 4))
        ch.append((b'BODY', tb, 4))
        m['TEXF'].append(tname)
        m['GTT'].append([len(m['TEXF']) - 1, -1])
        gtts.append(len(m['GTT']) - 1)
        names.append(tname)
    # ---- mesh -> bank + MODS, VNAM + INST
    mform, mch, mhdr = ilff.read(open(paths['models'], 'rb').read())
    mkey = 'LOCAL:models/%s.mef' % dst
    assert mkey not in {n for n, t, b in ilff.entries(mch) if n} and dst not in m['MODS']
    mch.append((b'NAME', mkey.encode('latin1') + b'\0', 4))
    mch.append((b'BODY', data, 4))
    m['MODS'].append(dst)
    m['VNAM'].append(dst)
    m['INST'].append([len(m['MODS']) - 1, gtts])
    out_tex = ilff.write(form, ch, hdr[1] or 4)
    out_mod = ilff.write(mform, mch, mhdr[1] or 4)
    out_mtp = mtp.write(m)
    m_chk = mtp.read(out_mtp)                                   # in-memory checks before anything is written
    _, ch_t, _ = ilff.read(out_tex); _, ch_m, _ = ilff.read(out_mod)
    t_names = {n.split('/')[-1][:-4] for n, t, b in ilff.entries(ch_t) if n}
    m_names = {n.split('/')[-1][:-4].lower() for n, t, b in ilff.entries(ch_m) if n}
    pre = [n for n in m_chk['MODS'] if n.lower() not in m_names] + [n for n in m_chk['TEXF'] if n not in t_names]
    if pre:
        raise ValueError('manifest would reference resources missing from its banks (nothing written): %s' % pre[:5])

    def put(path, blob):                                          # atomic replace
        tmp = path + '.wreck.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    put(paths['textures'], out_tex)                               # banks first, the manifest last: a crash in between
    put(paths['models'], out_mod)                                 # leaves unused bank entries, never a manifest entry
    put(paths['mtp'], out_mtp)                                    # without its resource
    lod = _lod_entry(overlay_dir, src, dst, level_name)
    # ---- read everything back
    b2 = Bank(paths['mtp'], paths['models'], paths['textures'])
    if b2.res.get(dst) != (dst, names):
        probs.append('manifest resolve: %s' % (b2.res.get(dst),))
    if b2.models.get(dst.lower()) != data:
        probs.append('mesh not in the model bank')
    for n in names:
        if n not in b2.tex:
            probs.append('texture %s missing' % n)
    mm = b2.m
    missing = set(x.lower() for x in mm['MODS']) - set(b2.models)       # (fatal 'Failed to load resource' modal)
    if missing:
        probs.append('MODS entries missing from the model bank: %s' % sorted(missing)[:5])
    if set(mm['TEXF']) - set(b2.tex):
        probs.append('TEXF entries missing from the texture bank: %s' % sorted(set(mm['TEXF']) - set(b2.tex))[:5])
    if mtp.write(mtp.read(paths['mtp'])) != open(paths['mtp'], 'rb').read():
        probs.append('mtp round trip')
    h_ = mef.hsem
    rep = dict(model=dst, mef_bytes=len(data), render_tris=int(h_['n_rfaces']), render_verts=int(h_['n_rverts']),
               groups=len(mef.get('DNER')), coll_faces=[len(F) for F in mef.all('ECFC')], textures=names,
               lod=lod, ground_h_m=h / M, problems=probs)
    log('wreck: %s -> %s: %d tris / %d verts, %d groups, collision %s, textures %s, lod %s, problems %s' % (
        src, dst, rep['render_tris'], rep['render_verts'], rep['groups'], rep['coll_faces'], names, lod, probs or 'none'))
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        rep['previews'] = render_views(R, texs, h, os.path.join(preview_dir, 'wreck'), alpha=alpha,
                                       alpha_slots={A.slot('scorch')} if 'scorch' in A.slots else ())
    assert not probs, probs
    return rep


def heli_wreck(K, hid, name='helicopter', model='w740_01_1', alpha=PLACEMENT_ALPHA, tol=0.005):
    """spkit missions: the intact helicopter (ExplodeObject hid) vanishes in its blast (destroyed model 'none') and the
    wreck appears in EXACTLY its place and orientation (the wreck mesh carries the crash pose itself; do not use
    Kit.heli_wreck's sink / tilt offsets with it). -> ConditionalContainer id"""
    from mission_lib import T
    from qast import lit
    a = [float(lit(x)) for x in K.L[hid].args[3:9]]
    tw = 2 * math.pi
    d_alpha = abs((a[3] - alpha + math.pi) % tw - math.pi)
    d_beta = abs((a[4] + math.pi) % tw - math.pi)
    if d_alpha > tol or d_beta > tol:                             # (0.005 rad = 5 cm of tilt 10 m out)
        raise ValueError('helicopter %d is placed with alpha %.4f / beta %.4f; the wreck was baked for alpha %.5f, '
                         'beta 0 (rebuild it with add_wreck_model(..., alpha=%.5f) and pass alpha= here)'
                         % (hid, a[3], a[4], alpha, a[3]))
    K.m.set(hid, 10, 'none')
    cc = K.nid()
    w = T(K.nid(), 'EditRigidObj', '%s %s wreck' % (K.PFX, name), a[0], a[1], a[2], a[3], a[4], a[5], model, 5, False, False)
    K.m.add_child(K.LOGIC, T(cc, 'ConditionalContainer', '%s %s wreck' % (K.PFX, name),
                             'ExplodeObject_%d.isExploded' % hid, '', '', children=[w]))
    K.m.models.add(model.lower() + '.mef')
    return cc


# =============================================================================================== collision checks
def surface_samples(S, per_edge=3):
    """points on the triangles of a soup (corners, edge points, centroids)"""
    P = S.P
    out = [P.reshape(-1, 3), P.mean(1)]
    for a, b in ((0, 1), (1, 2), (2, 0)):
        for t in np.linspace(0, 1, per_edge + 2)[1:-1]:
            out.append(P[:, a] + (P[:, b] - P[:, a]) * t)
    return np.concatenate(out)


def collision_fit(R, C):
    """how far each collision face lies from the rendered surface (metres): per mesh p50 / p95 / p99 / max and
    the share of faces > 0.5 m away (= invisible walls). Compare with the intact model's numbers."""
    from scipy.spatial import cKDTree
    tree = cKDTree(surface_samples(R))
    out = []
    for c in C:
        if c is None or not len(c):
            out.append(None); continue
        d, _ = tree.query(np.concatenate([c.P.mean(1), c.P.reshape(-1, 3)]))
        d = d / M
        nf = len(c)
        dc = d[:nf]
        out.append(dict(p50=float(np.percentile(d, 50)), p95=float(np.percentile(d, 95)), p99=float(np.percentile(d, 99)),
                        max=float(d.max()), far_faces=float((dc > 0.5).mean())))
    return out


# =============================================================================================== preview CLI
PART_COLOURS = {'hull': (0.75, 0.75, 0.75), 'body': (0.55, 0.62, 0.72), 'interior': (0.35, 0.6, 0.35),
                'gearN': (0.95, 0.75, 0.1), 'gearL': (0.95, 0.5, 0.1), 'gearR': (0.95, 0.5, 0.1),
                'wheelL': (0.2, 0.2, 0.2), 'wheelR': (0.2, 0.2, 0.2), 'finL': (0.8, 0.2, 0.6), 'finR': (0.8, 0.2, 0.6),
                'stab': (0.9, 0.35, 0.75), 'tailbits': (0.6, 0.1, 0.4), 'r1hub': (0.15, 0.45, 0.85),
                'r2hub': (0.1, 0.75, 0.8), 'doorL': (0.9, 0.2, 0.2), 'doorR': (0.6, 0.1, 0.1), 'glass': (0.5, 0.85, 1.0)}


def render_parts(A, prefix, alpha=PLACEMENT_ALPHA, size=(1100, 700), ss=1, views=VIEWS):
    """the intact helicopter coloured by part (+ a legend) -> [png]"""
    import mefrender
    from PIL import ImageDraw
    Gm = rx(alpha)
    S = A.R
    sc = mefrender.Scene()
    used = []
    for p in np.unique(S.part):
        name = PART_NAMES[p]
        col = PART_COLOURS.get(name, PART_COLOURS.get(name.rstrip('0123456789').replace('blade', 'hub'), (0.5, 0.5, 0.5)))
        if 'blade' in name:
            col = (0.1, 0.3, 0.95) if name.startswith('r1') else (0.0, 0.85, 0.55)
        mid = sc.material(None, color=col, alpha=0.5 if name == 'glass' else 1.0)
        m = S.part == p
        sc.add_tris(S.P[m] @ Gm.T, S.N[m] @ Gm.T, None, mid)
        used.append((name, col))
    hg = (S.P[A.parts(S, 'wheelL', 'wheelR', 'gearN')].reshape(-1, 3) @ Gm.T)[:, 2].min()
    sc.add_ground(z=hg, half=110000)
    out = []
    legend = {}
    for name, col in used:
        key = 'lower rotor blades' if name.startswith('r1blade') else 'upper rotor blades' if name.startswith('r2blade') else name
        legend.setdefault(key, col)
    for vname, eye in views:
        im = sc.render(np.asarray(eye, float), Gm @ np.array([0, -3000, 13000.0]), size=size, fov=48, ss=ss)
        d = ImageDraw.Draw(im)
        for k, (name, col) in enumerate(legend.items()):
            y = 8 + 15 * k
            d.rectangle((8, y, 20, y + 11), fill=tuple(int(255 * c) for c in col), outline=(0, 0, 0))
            d.text((26, y), name, fill=(0, 0, 0))
        p = '%s_%s.png' % (prefix, vname)
        im.save(p); out.append(p)
    return out


def render_intact(A, bank, prefix, alpha=PLACEMENT_ALPHA, size=(1100, 700), ss=2, views=VIEWS):
    """the intact helicopter with its real textures (glass translucent) -> [png]"""
    import mefrender
    Gm = rx(alpha)
    S = A.R
    sc = mefrender.Scene()
    for sid in np.unique(S.slot):
        sid = int(sid)
        name = A.slots[sid] if sid != 0xFFFF else None
        base = name.split('@')[0] if name else None
        tex = igitex.decode(bank.tex[base]) if base in bank.tex else None
        glass = bool(base and base.startswith('412_06'))
        mid = sc.material(tex, color=(0.05, 0.05, 0.05), alpha=0.45 if glass else 1.0)
        m = S.slot == sid
        sc.add_tris(S.P[m] @ Gm.T, S.N[m] @ Gm.T, S.UV[m], mid)
    hg = (S.P[A.parts(S, 'wheelL', 'wheelR', 'gearN')].reshape(-1, 3) @ Gm.T)[:, 2].min()
    sc.add_ground(z=hg, half=110000)
    out = []
    for vname, eye in views:
        im = sc.render(np.asarray(eye, float), Gm @ np.array([0, -3000, 11000.0]), size=size, fov=46, ss=ss)
        p = '%s_%s.png' % (prefix, vname)
        im.save(p); out.append(p)
    return out


def _main(argv):
    """python -P wreck.py --preview <level> <out dir>   : intact + part map + wreck previews, OBJ exports
       (reads the shipped level read-only; writes only into <out dir>)"""
    level, out = argv[1], argv[2]
    os.makedirs(out, exist_ok=True)
    d = level_dir(level)
    b_ = os.path.basename(d)
    bank = Bank(os.path.join(d, b_ + '.mtp'), os.path.join(d, 'models', b_ + '.res'), os.path.join(d, 'textures', b_ + '.res'))
    A = Assembly(bank)
    print(render_intact(A, bank, os.path.join(out, 'hind')))
    print(render_parts(A, os.path.join(out, 'hind_parts')))
    R, C, h = make_wreck(A)
    texs = make_textures(A, R, bank)
    m = build_mef(A, R, C, sorted(texs))
    print('verify:', verify_mef(m) or 'ok', 'fit:', collision_fit(R, C))
    open(os.path.join(out, 'w740_01_1.mef'), 'wb').write(m.write())
    mefmesh.export_obj(m, os.path.join(out, 'w740_01_1.obj'))
    mefmesh.export_obj(A.body_mef, os.path.join(out, '740_01_1.obj'))
    from PIL import Image
    for sid, t in texs.items():
        Image.fromarray((np.clip(t[..., :3], 0, 1) * 255).astype(np.uint8)).save(
            os.path.join(out, 'tex_w%d_%s.png' % (sid, A.slots[sid].replace('@', '_'))))
    print(render_views(R, texs, h, os.path.join(out, 'wreck'), alpha_slots={A.slot('scorch')} if 'scorch' in A.slots else ()))


if __name__ == '__main__':
    if len(sys.argv) > 3 and sys.argv[1] == '--preview':
        _main(sys.argv[1:])
    else:
        print(__doc__)
