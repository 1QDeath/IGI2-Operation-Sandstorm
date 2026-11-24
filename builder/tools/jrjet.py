"""jrjet - Operation Joyride's stolen JSF (ART, WP-D, 2026-10-30): the parked jet on Pad One, its gear, the bomb, the
boarding stair spot, and the outro clone builder (proof P1, fallbacks of plan section 15 / 18).

The stock jet 760_01_1 (L32 location3/level2, the only copy in the game, ONE instance, no lightmaps anywhere, catalog.json)
is a LIGHTMAPPED (type 3) mesh with NO landing gear, an opaque canopy, an afterburner flame cone + 3 shock-diamond glows
behind the nozzle (texture slots 1002_01..04_1, y -13.3..-7.6 m) and LODs 2-4 that change shape (LOD 4 has no wings;
L32 itself pins LOD 1 to 1000 m). Two ways to put it on the pad, both built here so ONE rig run (variant 'jetlab')
decides P1:

  A  'stock'  760_01_1 + 760_03_1 merged (X.models, every texture copied into the mission bank by prefab.merge), the
              modelled gear legs jr_ngear_1 (nose) / jr_mgear_1 (main, twice) and the bomb as CHILD EditRigidObjs (children
              ride along with a moving EditRigidObj, cine.board_outro), LOD row [900, 900, 900, 900, 1500] (LOD 1 to 900 m).
              No lightmap donor exists (no shipped 760_01_1 instance has an .olm): it gets the engine's default lightmap.
  B  'vl'     fallback (a) of the plan done up front: jr_jsf_1 = the same airframe re-exported VERTEX-LIT (type 0, the
              proven modelkit path: lit by the level's ambient + sun like every prop, moving copies are not black),
              with the gear legs, wheels, bay doors and the bomb BAKED INTO ONE MESH (no children, nothing can float),
              the flame cone + glows dropped (a parked jet with its afterburner lit looks broken), single LOD (no pop),
              every texture slot a LOCAL copy under a new name (COMMON_BIT slots crashed igi2.exe+0x16fda0 at a cut,
              srkit 10-24; prefab-merged names are not touched). Variants: jr_jsf_1 parked (gear, no glow),
              jr_jsfl_1 lift (gear + nozzle glow), jr_jsfu_1 gear up + nozzle glow (outro O3/O4).

Builder hooks (work/joyride/CONTRACT.md): models(B) S2, prep(B) S4, dress(B) S7, debug(B) S15, lod_rows() S16.
Env JR_JET=vl|stock picks the parked jet (default vl until P1 says otherwise; 'jetlab' always builds both).

    python -P tools/jrjet.py preview [out_dir]      # offline sheets: views, gear seating, lift strip, distance strip

Model frame of every jet here = 760_01_1's: z up, nose +y, starboard +x, origin ORIGIN_Z above the deck (gear feet at
z = -ORIGIN_Z exactly). Units: metres in the helpers, world units (4096 / m) in the meshes.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import mefmesh, igitex
import biprefabs as BP
import modelkit as MK
import searchlight as SL

M = 4096.0
GAME = r'C:\Users\1qdeath\Games\IGI2\app'
L32 = 'location3/level2'
STOCK = ['760_01_1', '760_03_1']
ORIGIN_Z = 2.75                  # jet origin over the deck (m): belly -1.25 m + 1.5 m clearance (plan Z13)
VL_NAMES = ['jr_jsf_1', 'jr_jsfl_1', 'jr_jsfu_1']
GEAR_NAMES = ['jr_ngear_1', 'jr_mgear_1']             # (NOT jr_gear_1/_2: a name ending _2 is the engine's LOD 2 of _1)
NAMES = VL_NAMES + GEAR_NAMES
TEX = {'jr_jsf_a': '760_01_1', 'jr_jsf_n': '760_02_1', 'jr_jsf_b': '760_06_1'}   # local copies (new names) of the L32 slots
BODY_SLOTS = ('760_01_1', '760_02_1')     # airframe + nozzle; the rest of 760_01_1's slots are the afterburner effect
BODY_CREASE = 60.0                        # airframe normal crease (deg): smooth fuselage, wing / fin edges stay sharp
NOSE_GEAR = (0.0, 6.35)                   # (x, y) m of the nose leg (under the cockpit front, behind the radome)
MAIN_GEAR = (1.72, -2.35)                 # (|x|, y) m of the two main legs (wing roots, outboard of the bomb)
BOMB_Y = -1.6                             # bomb centre y (m), between the main legs
MAIN_R, MAIN_W = 0.46, 0.30               # main wheel radius / width (m)
NOSE_R, NOSE_W = 0.31, 0.16               # nose wheels (twin)
VARIANTS = {'jetlab': 'P1: stock 760_01_1 (+gear children) and vertex-lit jr_jsf_1 parked side by side on a lab deck '
                      '+ a 40 s test intro (lift 15 m up / 60 m forward, then a dolly-out to 900 m for LOD pops)'}

_CACHE = {}


# ================================================================================================ the stock meshes
def _level():
    if 'lv' not in _CACHE:
        import prefab
        _CACHE['lv'] = prefab.Level(os.path.join(GAME, 'MISSIONS', *L32.split('/')))
    return _CACHE['lv']


def stock(vn):
    """(RigidModel, [texture names]) of a stock L32 model"""
    key = 'm:' + vn
    if key not in _CACHE:
        lv = _level()
        mefn, texs = lv.find_vnam(vn).entry(vn)
        m = mefmesh.Mef.read(lv.find_resource('LOCAL:models/%s.mef' % mefn, 'models')[1])
        _CACHE[key] = (mefmesh.RigidModel.from_mef(m), list(texs), m)
    return _CACHE[key][:2]


def stock_tex(name):
    """float RGBA of an L32 texture (mode 2 decodes exactly: re-encoding gives the same 16-bit pixels)"""
    key = 't:' + name
    if key not in _CACHE:
        _CACHE[key] = igitex.decode(_level().find_resource('LOCAL:textures/%s.tex' % name, 'textures')[1])
    return _CACHE[key].copy()


def _outward_normals(P, T, crease_deg):
    """per-corner normals of triangles that are CLOCKWISE seen from outside (the engine's front face): mefmesh.smooth_normals
    uses +cross (counter-clockwise front), so its result points inward here -> negated"""
    return -mefmesh.smooth_normals(P, T, crease_deg)


def _soup(r, texs, slots, crease_deg=38.0):
    """render groups of a stock model whose texture is in `slots` -> {texture name: [(P, T, N, U) parts]} (units, the
    model's own frame), corners unwelded (flat where the crease splits them)"""
    out = {}
    for g in r.groups:
        name = texs[g.tex] if g.tex < len(texs) else None
        if name not in slots or not len(g.tris):
            continue
        P = g.pos.astype(float); T_ = g.tris.astype(int)
        Nc = _outward_normals(P, T_, crease_deg)                 # (len(T), 3, 3)
        Pc = P[T_].reshape(-1, 3); Uc = g.uv.astype(float)[T_].reshape(-1, 2)
        Tc = np.arange(len(Pc)).reshape(-1, 3)
        out.setdefault(name, []).append((Pc, Tc, Nc.reshape(-1, 3), Uc))
    return out


def body_tris():
    """the airframe triangles (metres), for ray casts: (A, B, C) arrays"""
    if 'tri' not in _CACHE:
        r, texs = stock('760_01_1')
        A, B_, C = [], [], []
        for g in r.groups:
            if texs[g.tex] in BODY_SLOTS:
                Q = g.pos.astype(float)[g.tris] / M
                A.append(Q[:, 0]); B_.append(Q[:, 1]); C.append(Q[:, 2])
        _CACHE['tri'] = (np.concatenate(A), np.concatenate(B_), np.concatenate(C))
    return _CACHE['tri']


def ray(o, d):
    """first hit distance (m) of the ray o + t d against the airframe (Moller-Trumbore, both sides) or None"""
    A, B_, C = body_tris()
    o = np.asarray(o, float); d = np.asarray(d, float); d = d / np.linalg.norm(d)
    e1, e2 = B_ - A, C - A
    p = np.cross(d, e2)
    det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - A
    u = (s * p).sum(1) * inv
    q = np.cross(s, e1)
    v = (q * d).sum(1) * inv
    t = (e2 * q).sum(1) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)
    return float(t[hit].min()) if hit.any() else None


def belly_z(x, y):
    """lowest airframe surface z (m) over (x, y): a ray up from 5 m below"""
    t = ray((x, y, -5.0), (0, 0, 1))
    return None if t is None else -5.0 + t


def side_x(y, z, side=-1):
    """the hull's outer x (m) at (y, z) on the port (-1) or starboard (+1) side: a ray in from 10 m out"""
    t = ray((side * 10.0, y, z), (-side, 0, 0))
    return None if t is None else side * (10.0 - t)


def top_z(x, y):
    t = ray((x, y, 8.0), (0, 0, -1))
    return None if t is None else 8.0 - t


# ================================================================================================ the gear (modelled)
def _ring_strut(r, za, zb, x, y, seg=10):
    return BP.cyl_z(r, za, zb, seg, x, y)


def _wheel(r, w, cx, cy, cz, seg=16):
    """a wheel turning about x: tyre (slot 'tyre') + hub discs (slot 'metal') -> (tyre parts, hub parts)"""
    tyre = BP.cyl_axis(r, cx - w / 2, cx + w / 2, 'x', seg, at=(cy, cz))
    hub = BP.cyl_axis(r * 0.55, cx - w / 2 - 0.012, cx + w / 2 + 0.012, 'x', 10, at=(cy, cz))
    return [tyre], [hub]


def _door(p0, p1, p2, p3, thick=0.03):
    """a thin flat panel through 4 corners (metres) -> convex part"""
    pts = [np.asarray(p, float) for p in (p0, p1, p2, p3)]
    n = np.cross(pts[1] - pts[0], pts[3] - pts[0]); n = n / np.linalg.norm(n) * thick / 2
    return MK.hull_m([p + n for p in pts] + [p - n for p in pts], uv=0.8)


def gear_parts(kind, x, y, top, foot=-ORIGIN_Z, side=1):
    """one gear leg in the jet frame (metres): kind 'nose' | 'main'; top = the hull z it hangs from; foot = deck z.
    side = +1 starboard / -1 port (main: the door opens outboard). -> dict(metal=[parts], tyre=[parts], white=[parts],
    coll=[parts])"""
    out = dict(metal=[], tyre=[], white=[], coll=[])
    if kind == 'nose':
        r, w = NOSE_R, NOSE_W
        axle = foot + r
        out['white'].append(_ring_strut(0.085, axle + 0.18, top + 0.05, x, y))               # the leg (into the bay)
        out['metal'].append(_ring_strut(0.065, axle + 0.02, axle + 0.30, x, y))              # chromed oleo piston
        out['metal'].append(BP.box_m(x - 0.17, y - 0.05, axle - 0.05, x + 0.17, y + 0.05, axle + 0.05))   # axle beam
        out['white'].append(BP.box_m(x - 0.03, y - 0.26, axle + 0.30, x + 0.03, y - 0.06, axle + 0.62))   # drag brace
        for sx in (-1, 1):
            t_, h_ = _wheel(r, w, x + sx * (0.12 + w / 2), y, axle)
            out['tyre'] += t_; out['metal'] += h_
        out['white'].append(BP.box_m(x - 0.30, y - 0.03, top - 0.02, x + 0.30, y + 0.03, top + 0.01))       # bay edge
        # two bay doors hanging open either side of the leg
        for sx in (-1, 1):
            out['white'].append(_door((x + sx * 0.18, y - 0.75, top + 0.02), (x + sx * 0.18, y + 0.75, top + 0.02),
                                      (x + sx * 0.32, y + 0.75, top - 0.55), (x + sx * 0.32, y - 0.75, top - 0.55)))
        out['coll'] += [BP.box_m(x - 0.36, y - 0.33, foot, x + 0.36, y + 0.33, axle + 0.35),
                        BP.box_m(x - 0.09, y - 0.09, axle + 0.35, x + 0.09, y + 0.09, top + 0.05)]
    else:
        r, w = MAIN_R, MAIN_W
        axle = foot + r
        wx = x + side * 0.06                                                                  # the wheel just outboard
        out['white'].append(_ring_strut(0.11, axle + 0.24, top + 0.05, x, y))
        out['metal'].append(_ring_strut(0.08, axle + 0.03, axle + 0.36, x, y))
        out['metal'].append(BP.box_m(min(x, wx) - 0.10, y - 0.06, axle - 0.06, max(x, wx) + 0.10, y + 0.06, axle + 0.06))
        out['white'].append(BP.box_m(x - 0.035, y + 0.08, axle + 0.36, x + 0.035, y + 0.36, top - 0.15))   # side brace
        out['white'].append(BP.box_m(x - 0.03, y - 0.14, axle + 0.16, x + 0.03, y - 0.06, axle + 0.46))    # torque link
        t_, h_ = _wheel(r, w, wx, y, axle)
        out['tyre'] += t_; out['metal'] += h_
        # the big outboard door, hanging open (hinged on the bay's outer edge), and the bay edge
        hx = x + side * 0.55
        out['white'].append(_door((hx, y - 0.95, top + 0.02), (hx, y + 0.95, top + 0.02),
                                  (hx + side * 0.10, y + 0.95, top - 0.78), (hx + side * 0.10, y - 0.95, top - 0.78)))
        out['white'].append(BP.box_m(x - 0.55, y - 0.04, top - 0.02, x + 0.55, y + 0.04, top + 0.01))
        out['coll'] += [BP.box_m(wx - w / 2 - 0.02, y - r, foot, wx + w / 2 + 0.02, y + r, axle + 0.30),
                        BP.box_m(x - 0.12, y - 0.12, axle + 0.30, x + 0.12, y + 0.12, top + 0.05)]
    return out


def gear_layout():
    """[(kind, x, y, top z, side)] of the three legs on THIS airframe (ray-cast hull heights)"""
    legs = []
    zt = belly_z(*NOSE_GEAR)
    assert zt is not None and -1.3 < zt < 0.5, ('nose gear: no hull over', NOSE_GEAR, zt)
    legs.append(('nose', NOSE_GEAR[0], NOSE_GEAR[1], zt, 1))
    for sx in (-1, 1):
        x, y = sx * MAIN_GEAR[0], MAIN_GEAR[1]
        zt = belly_z(x, y)
        assert zt is not None and -1.3 < zt < 0.5, ('main gear: no hull over', (x, y), zt)
        legs.append(('main', x, y, zt, sx))
    return legs


# ================================================================================================ the bomb under the belly
def bomb_parts():
    """760_03_1 (2.84 m, fins 1.12 m) re-exported vertex-lit, hung 6 cm under the belly at (0, BOMB_Y), its nose forward,
    on a short pylon -> (bomb {slot: parts}, pylon parts, coll parts) in the jet frame (units)"""
    r, texs = stock('760_03_1')
    soup = _soup(r, texs, ('760_06_1',), crease_deg=40.0)
    P = np.concatenate([p for p, t, n, u in soup['760_06_1']]) / M
    zb = belly_z(0.0, BOMB_Y)
    assert zb is not None
    top = zb - 0.06
    dz = top - P[:, 2].max()
    flip = _bomb_nose_is_minus_y()
    parts = []
    for Pp, Tp, Np, Up in soup['760_06_1']:
        Q = Pp / M
        Nq = Np.copy()
        if flip:                                    # nose forward (+y): rotate 180 deg about z
            Q = Q * np.array([-1, -1, 1.0]); Nq = Nq * np.array([-1, -1, 1.0])
        Q = Q + np.array([0.0, BOMB_Y, dz])
        parts.append((Q * M, Tp, Nq, Up))
    pyl = BP.box_m(-0.07, BOMB_Y - 0.55, top - 0.05, 0.07, BOMB_Y + 0.55, zb + 0.08)
    lo = np.concatenate([p for p, t, n, u in parts]).min(0) / M
    hi = np.concatenate([p for p, t, n, u in parts]).max(0) / M
    coll = [BP.box_m(-0.30, lo[1], lo[2] + 0.25, 0.30, hi[1], top), pyl]
    return parts, [pyl], coll


def _bomb_nose_is_minus_y():
    """the fin end is the wide end: if the wide end is at +y the nose points -y"""
    r, texs = stock('760_03_1')
    P = np.concatenate([g.pos for g in r.groups]).astype(float) / M
    wide = np.hypot(P[:, 0], P[:, 2])
    hi_end = wide[P[:, 1] > 0.9].max()
    lo_end = wide[P[:, 1] < -0.9].max()
    return hi_end > lo_end


# ================================================================================================ textures
# Rework 2026-10-31 (owner playtest: "cartoonish, low quality"): the airframe is repainted as a real stealth jet at dusk -
# dark radar-absorbent grey derived FROM the L32 skin (same UV layout: its shading/details stay where the UVs expect
# them), panel lines + access panels + darker leading edges + light streaks placed in 3D (a UV bake of the airframe),
# smoky gold canopy, grey gear and doors, black tyres; ordered dither so the A1R5G5B5 encoder does not band.
PAINT = np.array([0.33, 0.345, 0.37])     # radar-absorbent grey, a touch blue (~RGB 84 88 94)
SKIN_N = 512                              # jr_jsf_a size (the L32 skin is 128: 4x)


def _bake_uv(n=SKIN_N):
    """rasterise the airframe triangles (texture 760_01_1) into its UV space -> (pos (n,n,3) m, face normal (n,n,3),
    covered mask (n,n), canopy mask (n,n)); covered texels dilated 6 px for bilinear bleed"""
    r, t = stock('760_01_1')
    pos = np.zeros((n, n, 3)); nrm = np.zeros((n, n, 3)); msk = np.zeros((n, n), bool); can = np.zeros((n, n), bool)
    work = []
    for g in r.groups:
        if t[g.tex] != '760_01_1':
            continue
        P = g.pos.astype(float) / M; U = g.uv.astype(float) * n
        for tri in g.tris.astype(int):
            cu, cv = U[tri].mean(0) / n
            glass = 0.10 < cu < 0.19 and 0.33 < cv < 0.44 and P[tri][:, 2].mean() > 0.8   # the canopy (13 tris; its
            work.append((glass, P[tri], U[tri]))                     # texels are shared with the intake lips: drawn last)
    work.sort(key=lambda w_: w_[0])
    for glass, p, uv in work:
        fn = -np.cross(p[1] - p[0], p[2] - p[0]); ln = np.linalg.norm(fn)
        if ln < 1e-12:
            continue
        fn /= ln
        x0, y0 = np.floor(uv.min(0)).astype(int) - 1; x1, y1 = np.ceil(uv.max(0)).astype(int) + 1
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        a, b, c = uv
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        X = np.floor(xs[m]).astype(int) % n; Y = np.floor(ys[m]).astype(int) % n
        pos[Y, X] = l0[m, None] * p[0] + l1[m, None] * p[1] + l2[m, None] * p[2]
        nrm[Y, X] = fn; msk[Y, X] = True; can[Y, X] = glass
    for _ in range(6):
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(msk, (dy, dx), (0, 1)) & ~msk
            pos[src] = np.roll(pos, (dy, dx), (0, 1))[src]; nrm[src] = np.roll(nrm, (dy, dx), (0, 1))[src]
            msk = msk | src
    return pos, nrm, msk, can


def _leading_edges(fold_deg=110.0):
    """3D segments (a, b) in metres of the airframe's sharp forward-facing edges (wing / tail / intake leading edges),
    mirrored across x too (mirrored UV islands bake one side only)"""
    r, t = stock('760_01_1')
    out = []
    for g in r.groups:
        if t[g.tex] != '760_01_1':
            continue
        P = g.pos.astype(float) / M; T_ = g.tris.astype(int)
        _, wid = np.unique(np.round(P * 1000).astype(np.int64), axis=0, return_inverse=True); wid = wid.reshape(-1)
        fn = -np.cross(P[T_[:, 1]] - P[T_[:, 0]], P[T_[:, 2]] - P[T_[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        edges = {}
        for f, tri in enumerate(T_):
            for k in range(3):
                i, j = tri[k], tri[(k + 1) % 3]
                edges.setdefault(tuple(sorted((int(wid[i]), int(wid[j])))), []).append((f, i, j))
        cosf = np.cos(np.radians(fold_deg))
        for fs in edges.values():
            if len(fs) != 2:
                continue
            (f1, i, j), (f2, _, _) = fs
            avg = fn[f1] + fn[f2]
            if fn[f1] @ fn[f2] > cosf or np.linalg.norm(avg) < 1e-6 or (avg / np.linalg.norm(avg))[1] < 0.35:
                continue
            out.append((P[i], P[j])); out.append((P[i] * [-1, 1, 1], P[j] * [-1, 1, 1]))
    return out


def _seg_dist(Q, segs):
    best = np.full(len(Q), 1e9)
    for a, b in segs:
        ab = b - a
        s = np.clip(((Q - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        best = np.minimum(best, np.linalg.norm(Q - (a + s[:, None] * ab), axis=1))
    return best


def _line(v, period, w, offset=0.0):
    """antialiased line strength where v crosses offset + k * period (w = half width, same units)"""
    d = np.abs((v - offset + period / 2) % period - period / 2)
    return np.clip(1.0 - d / w, 0.0, 1.0)


def _box_outline(a, b, a0, a1, b0, b1, w):
    """strength of the outline of the rectangle [a0,a1] x [b0,b1] in a plane coordinate pair (a, b)"""
    ina = (a > a0 - w) & (a < a1 + w); inb = (b > b0 - w) & (b < b1 + w)
    da = np.minimum(np.abs(a - a0), np.abs(a - a1)); db = np.minimum(np.abs(b - b0), np.abs(b - b1))
    return np.maximum(np.clip(1 - da / w, 0, 1) * inb, np.clip(1 - db / w, 0, 1) * ina)


def _streaks(across, along, rng, pitch=0.05):
    """weathering streaks: random 1D values across (interpolated), faded by a slow wave along"""
    k = rng.random(4096)
    t = (across / pitch) % 4000
    i = np.floor(t).astype(int); f = t - i
    s = np.clip((k[i] * (1 - f) + k[i + 1] * f - 0.55) / 0.45, 0, 1)
    k2 = rng.random(4096); t2 = (across / (pitch * 7)) % 4000; i2 = np.floor(t2).astype(int); f2 = t2 - i2
    return s * (0.5 + 0.5 * np.sin(along * 1.3 + (k2[i2] * (1 - f2) + k2[i2 + 1] * f2) * 6.28))


def _dither5(img):
    """4x4 ordered dither for the A1R5G5B5 encoder (wreck.tex_mode2 rounds to 1/31 steps: dark greys would band)"""
    b = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], float) / 16.0 - 0.47
    h, w = img.shape[:2]
    out = img.copy()
    out[..., :3] = np.clip(img[..., :3] + np.tile(b, (h // 4 + 1, w // 4 + 1))[:h, :w, None] / 31.0, 0, 1)
    return out


def tex_skin():
    """jr_jsf_a: the airframe skin, 512 px on 760_01_1's UV layout - dark RAM grey from the L32 skin's own tones (no
    JSF-97 stencil: the fins share one mirrored UV island, so any text reads backwards on one side), cached"""
    if 'skin' in _CACHE:
        return _CACHE['skin'].copy()
    from PIL import Image, ImageFilter
    n = SKIN_N
    a = (np.clip(stock_tex('760_01_1')[..., :3], 0, 1) * 255).astype('u1')
    big = np.asarray(Image.fromarray(a, 'RGB').resize((n, n), Image.BICUBIC), float) / 255.0
    L = big @ np.array([0.30, 0.59, 0.11])
    Lb = np.asarray(Image.fromarray((L * 255).astype('u1')).filter(ImageFilter.GaussianBlur(10)), float) / 255.0
    pos, nrm, msk, cmask = _bake_uv(n)
    rng = np.random.default_rng(7601)
    can = np.asarray(Image.fromarray((cmask * 255).astype('u1')).filter(ImageFilter.MaxFilter(3)), float) / 255.0
    tone = 1.0 + 0.8 * np.clip(L - Lb, -0.25, 0.25) + 0.18 * (Lb - 0.45)   # the original's detail, a narrow range
    noise = BP._noise(n, rng, 5)
    tone *= 0.93 + 0.12 * noise
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    ax = np.abs(x)
    top = np.abs(nrm[..., 2]) > 0.55; side = ~top
    w = 0.024                                                          # line half width (m; ~1 texel)
    fus = ax < 1.35
    lines = _line(y, 2.05, w, 0.31) * fus * 0.8                        # fuselage frames
    lines = np.maximum(lines, _line(ax, 1.6, w, 0.4) * (~fus) * top * 0.7)    # wing spar seams
    lines = np.maximum(lines, (np.abs(ax - 0.62) < w) * 1.0 * top)     # spine seams
    lines = np.maximum(lines, (np.abs(ax - 1.35) < w) * 1.0 * top * (y > -6.5))
    prng = np.random.default_rng(9)
    for _ in range(16):                                                # access panels, top / bottom (symmetric in x)
        cy_ = prng.uniform(-8.5, 8.5); cx_ = prng.uniform(0.25, 3.2)
        hw = prng.uniform(0.15, 0.4); hh = prng.uniform(0.2, 0.55)
        lines = np.maximum(lines, _box_outline(ax, y, cx_ - hw, cx_ + hw, cy_ - hh, cy_ + hh, w * 0.9) * top * 0.85)
    for _ in range(10):                                                # access panels, sides
        cy_ = prng.uniform(-8.0, 8.0); cz_ = prng.uniform(-0.9, 1.6)
        hw = prng.uniform(0.15, 0.5); hh = prng.uniform(0.1, 0.3)
        lines = np.maximum(lines, _box_outline(y, z, cy_ - hw, cy_ + hw, cz_ - hh, cz_ + hh, w * 0.9) * side * 0.85)
    tone *= 1.0 - 0.26 * lines
    le = _seg_dist(pos.reshape(-1, 3), _leading_edges()).reshape(n, n)
    tone *= 1.0 - 0.30 * np.clip(1.0 - le / 0.16, 0, 1)                # darker RAM on the leading edges
    tone *= 1.0 - 0.07 * np.where(top, _streaks(x, y, rng), _streaks(y, z, rng, 0.04))   # streaks
    tone *= 1.0 - 0.12 * np.clip((-y - 6.0) / 3.5, 0, 1)               # exhaust soot toward the tail
    tone *= np.where(nrm[..., 2] < -0.5, 0.92, 1.0)                    # belly grime
    col = PAINT[None, None] * tone[..., None]
    # smoky gold glass: dark, a warm sheen strongest on the upward-facing front panes
    sheen = (0.35 + 0.65 * np.clip(nrm[..., 2], 0, 1)) * (1.0 - 0.6 * np.clip((y - 4.6) / 3.0, 0, 1))
    gl = np.array([0.055, 0.05, 0.04])[None, None] + np.array([0.32, 0.23, 0.08])[None, None] * sheen[..., None] ** 1.5
    gl *= (0.95 + 0.1 * noise)[..., None]
    col = col * (1 - can[..., None]) + gl * can[..., None]
    out = np.ones((n, n, 4)); out[..., :3] = np.clip(col, 0, 1)
    _CACHE['skin'] = _dither5(out)
    return _CACHE['skin'].copy()


def tex_copy(name):
    img = stock_tex(name)
    out = np.ones(img.shape[:2] + (4,))
    out[..., :img.shape[2]] = img[..., :4]
    out[..., 3] = 1.0
    return out


def tex_nozzle():
    """jr_jsf_n: the nozzle - dark burnt metal from 760_02_1's tones (128 px)"""
    from PIL import Image
    a = (np.clip(stock_tex('760_02_1')[..., :3], 0, 1) * 255).astype('u1')
    big = np.asarray(Image.fromarray(a, 'RGB').resize((128, 128), Image.BICUBIC), float) / 255.0
    L = big @ np.array([0.30, 0.59, 0.11])
    col = np.array([0.26, 0.25, 0.27])[None, None] * (0.55 + 0.9 * (L - L.mean()))[..., None]
    out = np.ones((128, 128, 4)); out[..., :3] = np.clip(col, 0, 1)
    return _dither5(out)


def tex_gear_metal(n=64, seed=451):
    """jr_gearm: oleo pistons, axles, hubs - worn steel grey"""
    rng = np.random.default_rng(seed)
    g = 0.50 + 0.07 * BP._noise(n, rng, 3)
    img = np.dstack([g * 0.98, g, g * 1.03, np.ones((n, n))])
    img[:, :2, :3] *= 0.7; img[:2, :, :3] *= 0.7
    return np.clip(img, 0, 1)


def tex_tyre(n=64, seed=452):
    rng = np.random.default_rng(seed)
    g = 0.07 + 0.03 * BP._noise(n, rng, 3)
    img = np.dstack([g, g, g * 1.05, np.ones((n, n))])
    for k in range(0, n, 8):                            # tread grooves
        img[:, k:k + 2, :3] *= 0.55
    return np.clip(img, 0, 1)


def tex_white(n=64, seed=453):
    """jr_gearw (the name is historic): gear legs, bay doors, bay edges, the pylon - the airframe grey a shade lighter,
    dark edge seams"""
    rng = np.random.default_rng(seed)
    g = 0.92 + 0.10 * BP._noise(n, rng, 3)
    img = np.ones((n, n, 4)); img[..., :3] = (PAINT * 1.12)[None, None] * g[..., None]
    img[:, :2, :3] *= 0.6; img[:2, :, :3] *= 0.6
    return np.clip(img, 0, 1)


SLOTS = ['jr_jsf_a', 'jr_jsf_n', 'jr_jsf_b', 'jr_gearm', 'jr_tyre', 'jr_gearw']


def add_textures(lib):
    lib.texture('jr_jsf_a', tex_skin)
    lib.texture('jr_jsf_n', tex_nozzle)
    lib.texture('jr_jsf_b', lambda: tex_copy('760_06_1'))
    lib.texture('jr_gearm', tex_gear_metal)
    lib.texture('jr_tyre', tex_tyre)
    lib.texture('jr_gearw', tex_white)


# ================================================================================================ the vertex-lit jet
NOZZLE = (0.0, -8.15, 0.06)            # glow at the nozzle exit (m): 760_02_1 spans y -8.71..-7.53, z -0.73..0.84


def _glow_nozzle():
    gl = np.zeros(2, mefmesh.WOLG_DT)
    gl[0] = ((NOZZLE[0] * M, (NOZZLE[1] - 0.45) * M, NOZZLE[2] * M), 2200.0, 1.0, 0.62, 0.30, 0xABABABAB)   # (size: model units,
    gl[1] = ((NOZZLE[0] * M, (NOZZLE[1] - 1.6) * M, NOZZLE[2] * M), 1500.0, 1.0, 0.50, 0.22, 0xABABABAB)    #  2400 = a street lamp)
    return gl


def jsf_groups(gear=True, bomb=True):
    """the airframe + options -> (groups_parts [(slot index, parts)], coll parts)"""
    r, texs = stock('760_01_1')
    soup = _soup(r, texs, BODY_SLOTS, crease_deg=BODY_CREASE)
    body = soup['760_01_1']; nozz = soup['760_02_1']
    groups = {0: list(body), 1: list(nozz)}
    coll = []
    for Pp, Tp, Np, Up in body + nozz:                      # (collision = the airframe itself, no flame cone)
        coll.append((Pp, Tp, Np, Up))
    if bomb:
        bp, pyl, bc = bomb_parts()
        groups.setdefault(2, []).extend(bp)
        groups.setdefault(5, []).extend(pyl)
        coll += bc
    if gear:
        for kind, x, y, top, side in gear_layout():
            g = gear_parts(kind, x, y, top, side=side)
            groups.setdefault(3, []).extend(g['metal'])
            groups.setdefault(4, []).extend(g['tyre'])
            groups.setdefault(5, []).extend(g['white'])
            coll += g['coll']
    gp = [(k, groups[k]) for k in sorted(groups)]
    return gp, coll


def build_jsf(gear=True, glow=False, bomb=True):
    gp, coll = jsf_groups(gear, bomb)
    return MK.model(gp, coll, glows=_glow_nozzle() if glow else None)


def build_gear_leg(kind):
    """the stock-jet children: one leg in its OWN frame (origin = the foot on the deck, z up, +y = the jet's nose)"""
    legs = gear_layout()
    leg = legs[0] if kind == 'nose' else legs[2]
    _, x, y, top, side = leg
    g = gear_parts(kind, 0.0, 0.0, top + ORIGIN_Z, foot=0.0, side=1)
    gp = [(0, g['metal']), (1, g['tyre']), (2, g['white'])]
    return MK.model(gp, g['coll'])


def add_models(lib):
    """register the jet models + their local texture copies in a modelkit.Library"""
    add_textures(lib)
    lib.add('jr_jsf_1', lambda: build_jsf(gear=True, glow=False), SLOTS, lod_like='406_68_1')
    lib.add('jr_jsfl_1', lambda: build_jsf(gear=True, glow=True), SLOTS, lod_like='406_68_1')
    lib.add('jr_jsfu_1', lambda: build_jsf(gear=False, glow=True), SLOTS, lod_like='406_68_1')
    lib.add('jr_ngear_1', lambda: build_gear_leg('nose'), ['jr_gearm', 'jr_tyre', 'jr_gearw'], lod_like='406_68_1')
    lib.add('jr_mgear_1', lambda: build_gear_leg('main'), ['jr_gearm', 'jr_tyre', 'jr_gearw'], lod_like='406_68_1')
    return list(NAMES)


def _lodrow(cut):
    return [cut * 0.96, cut * 0.97, cut * 0.98, cut * 0.99, cut]


def lod_rows():
    """{model: [5 cut-offs]}: the vertex-lit jets are single-LOD (no pop) and drawn to 1800 m (satellite keys); the stock
    jet's LOD 1 is pinned to 900 m (its LOD 4 has no wings), cut-off 1500 m (plan 10.3)"""
    rows = {n: _lodrow(1800.0) for n in VL_NAMES}
    rows.update({n: _lodrow(1500.0) for n in GEAR_NAMES})
    rows['760_01_1'] = [900.0, 900.0, 900.0, 900.0, 1500.0]
    rows['760_03_1'] = [900.0, 900.0, 900.0, 900.0, 1500.0]
    return rows


# ================================================================================================ checks (offline)
def seat_report(mef=None):
    """gear feet vs the deck plane z = -ORIGIN_Z: every collision vertex >= the deck, the wheels' lowest points within
    3 cm of it (plan Z13 assert) -> dict"""
    mf = mef or build_jsf(gear=True)
    V = mf.all('XTVC')[0]['pos'].astype(float) / M
    zmin = float(V[:, 2].min())
    X = mf.get('XTRV')['pos'].astype(float) / M
    feet = []
    for kind, x, y, top, side in gear_layout():
        sel = (np.abs(X[:, 0] - x) < 0.8) & (np.abs(X[:, 1] - y) < 0.8) & (X[:, 2] < -ORIGIN_Z + 0.4)
        feet.append(float(X[sel, 2].min()) if sel.any() else None)
    ok = all(f is not None and abs(f + ORIGIN_Z) <= 0.03 for f in feet) and zmin >= -ORIGIN_Z - 0.03
    return dict(ok=ok, coll_zmin=zmin, feet=feet, deck=-ORIGIN_Z)


STAIR_Y = (5.65, 7.05)                    # the platform's extent along the fuselage (m): the forward cockpit, where the
                                          # chine is narrow (y < 5.4 the intake chine sticks out to x -2.16 at z 0)
STAIR_TOP = 0.0                           # platform top = the jet origin height (deck + ORIGIN_Z): the sill at his chest
STAND_DEPTH = 1.80                        # jr_stand_1 platform depth (m, toward the jet): the TBA 0.65 m off the hull + room
                                          # to stand 0.8-1.1 m in front of it (review 10-30: 1.2 m left no floor in front)


def _hull_min_x(ys, zs):
    xs = [side_x(y, z, side=-1) for y in ys for z in zs]
    xs = [x for x in xs if x is not None]
    assert xs, 'stair spot: no port hull at the cockpit'
    return min(xs)                                           # (port side = negative x: the widest point)


def stair_spot():
    """where the boarding stair docks (jet frame, metres; ray casts against the airframe):
    edge_x = the platform's inner edge, 0.15 m off the widest port hull between 0.35 m under its top and 1.2 m over it,
             over the platform's whole length (no gap Jones fits through, no chine over the floor);
    tba    = the cockpit GenericTBA ('use point'): 0.65 m off the widest hull at every height his body takes (0..1.8 m over
             the platform) within 0.5 m of the stair centre (PD trap: a use point near a hull walked Jones into it), 1.0 m
             over the platform (chest height); its +y faces out to him;
    stand  = where he stands to use it: 0.95 m in front of the tba, on the platform (STAND_DEPTH covers it)"""
    yc = 0.5 * (STAIR_Y[0] + STAIR_Y[1])
    hx = _hull_min_x(np.linspace(STAIR_Y[0], STAIR_Y[1], 9), np.arange(STAIR_TOP - 0.35, STAIR_TOP + 1.21, 0.15))
    hx_c = _hull_min_x(np.linspace(yc - 0.5, yc + 0.5, 5), np.arange(STAIR_TOP, STAIR_TOP + 1.81, 0.15))
    tba = (hx_c - 0.65, yc, STAIR_TOP + 1.0)
    stand = (tba[0] - 0.95, yc, STAIR_TOP)
    edge = hx - 0.15
    assert edge - STAND_DEPTH < stand[0] - 0.35, ('stair: the platform does not reach the stand point', edge, stand)
    return dict(y=yc, y0=STAIR_Y[0], y1=STAIR_Y[1], hull_x=hx, hull_x_tba=hx_c, edge_x=edge, top_z=STAIR_TOP, tba=tba, stand=stand,
                use=stand)


# ================================================================================================ builder hooks (CONTRACT.md)
JET_KIND = os.environ.get('JR_JET', 'vl')         # 'vl' = jr_jsf_1 (fallback a, default) | 'stock' = 760_01_1 + gear children


def _wants_stock(B):
    return JET_KIND == 'stock' or 'jetlab' in B.DBG


def models(B):
    """S2: merge the stock jet + bomb (prefab.merge copies every texture slot into the mission's own bank) - only when the
    stock path is in use (JR_JET=stock) or the P1 lab compares both"""
    if _wants_stock(B):
        B.X.models(L32, STOCK)
        B.note('jrjet: stock 760_01_1 + 760_03_1 merged from %s' % L32)


def prep(B):
    """S4: the vertex-lit jets + the stock-path gear legs into B.LIB (with their LOCAL texture copies)"""
    if any(n in set(B.LIB.names) for n in NAMES):
        return []
    return add_models(B.LIB)


def _R(yaw):
    c, s_ = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1.0]])


def to_world(origin, yaw, local_m):
    """jet frame (metres, origin = the jet's task position) -> world units"""
    return tuple(float(c) for c in (np.asarray(origin, float) + _R(yaw) @ (np.asarray(local_m, float) * M)))


def jet_tasks(B, origin, yaw, kind='vl', name='JR stolen JSF', model=None):
    """the jet as task(s) at origin (world units: the jet frame origin = deck + ORIGIN_Z) facing yaw:
    kind 'vl' -> one EditRigidObj (model jr_jsf_1 or `model`); 'stock' -> 760_01_1 with CHILD EditRigidObjs
    (jr_ngear_1, 2 x jr_mgear_1, the bomb 760_03_1) that ride along when it moves. -> (task, rigid id)"""
    T, nid = B.T, B.nid
    rid = nid()
    if kind == 'vl':
        return T(rid, 'EditRigidObj', name, *[float(c) for c in origin], 0.0, 0.0, float(yaw), model or 'jr_jsf_1', 5, False, False), rid
    kids = []
    for leg, x, y, top, side in gear_layout():
        foot = to_world(origin, yaw, (x, y, -ORIGIN_Z))
        g = yaw if (leg == 'nose' or side > 0) else yaw + math.pi        # (the port leg turned round: its door outboard)
        kids.append(T(nid(), 'EditRigidObj', '%s gear %s %s' % (name, leg, 'L' if side < 0 else 'R'), *foot, 0.0, 0.0, float(g),
                      'jr_ngear_1' if leg == 'nose' else 'jr_mgear_1', 5, False, False))
    zb = belly_z(0.0, BOMB_Y)
    bomb = to_world(origin, yaw, (0.0, BOMB_Y, zb - 0.06 - 0.56))
    kids.append(T(nid(), 'EditRigidObj', '%s bomb' % name, *bomb, 0.0, 0.0, float(yaw), '760_03_1', 5, False, False))
    return T(rid, 'EditRigidObj', name, *[float(c) for c in origin], 0.0, 0.0, float(yaw), model or '760_01_1', 5, False, False,
             children=kids), rid


def _deck_top(B, cx, cy, half=15.0, yaw=0.0, half_y=None):
    """the deck top over (cx, cy): the highest terrain point under its footprint + 0.20 m (MAP lowers the pad 0.20 m ->
    flush) -> (z top units, terrain range m)"""
    zs = []
    hy = half if half_y is None else half_y
    for u in np.linspace(-half, half, 7):
        for w in np.linspace(-hy, hy, 7):
            q = np.array([cx, cy]) + _R(yaw)[:2, :2] @ (np.array([u, w]) * M)
            h = B.TER.height(q[0], q[1]) if B.TER is not None else np.nan
            if not np.isnan(h):
                zs.append(float(h))
    if not zs:
        return None, None
    return max(zs) + 0.20 * M, (max(zs) - min(zs)) / M


def flat_spot(B, near, r_m=160.0, half=17.0, step_m=8.0, half_y=None, yaw=0.0):
    """the flattest (2 half x 2 half_y, turned yaw) patch near `near` (world units) -> (score, x, y, range m) - the lab
    before MAP's pad exists"""
    best = None
    for dx in np.arange(-r_m, r_m + 1, step_m):
        for dy in np.arange(-r_m, r_m + 1, step_m):
            cx, cy = near[0] + dx * M, near[1] + dy * M
            z, rg = _deck_top(B, cx, cy, half, yaw, half_y)
            if z is None:
                continue
            score = rg + 0.002 * math.hypot(dx, dy)
            if best is None or score < best[0]:
                best = (score, cx, cy, rg)
    return best


def place_parked(B, centre, yaw, kind='vl', name='JR stolen JSF (parked)', stand=True, deck=True, parent_cc=True):
    """a deck + the parked jet + the boarding stair + chocks at centre (x, y world units) -> dict (the B.JET format)"""
    T, nid, m = B.T, B.nid, B.m
    zt, rg = _deck_top(B, centre[0], centre[1], 15.0, yaw)
    assert zt is not None, 'jrjet: no terrain under the pad'
    if rg > 0.25:
        msg = 'jrjet: the ground under %s varies %.2f m (MAP: flatten the pad; the deck bridges it)' % (name, rg)
        if getattr(B, 'BUILD', '') == 'joyride':     # (release: a floating deck lip is a 'looks broken' bug)
            raise AssertionError(msg)
        B.note(msg)
    out = dict(kind=kind, yaw=float(yaw), deck_top=float(zt), deck=None, stair=None, chocks=[], terrain_range_m=rg)
    if deck:
        did = nid()
        m.add_child(B.STATIC, T(did, 'EditRigidObj', name + ' deck (jr_grid_1)', float(centre[0]), float(centre[1]), float(zt), 0.0, 0.0,
                                float(yaw), 'jr_grid_1', 5, False, False))
        out['deck'] = did
        B.SEAT_SKIP.add(did)                         # (flush in a 0.2 m recess: seatcheck would call it floating)
    origin = (float(centre[0]), float(centre[1]), float(zt + ORIGIN_Z * M))
    jt, jid = jet_tasks(B, origin, yaw, kind, name)
    if parent_cc:
        cc = nid()
        m.add_child(B.DYN, T(cc, 'ConditionalContainer', name + ' (CIN: hidden while the outro runs)', '1', '', '', children=[jt]))
        out['cc'] = cc
    else:
        m.add_child(B.STATIC, jt)
        out['cc'] = None
    out.update(id=jid, origin=origin)
    for t_, d_, p_ in B.tasks([jt]):
        B.SEAT_SKIP.add(int(B.lit(t_.args[0])))      # (the jet + its children stand on the deck: own assert below)
    sp = stair_spot()
    if stand:
        sid = nid()
        st_o = to_world(origin, yaw, (sp['edge_x'] - STAND_DEPTH, sp['y'], -ORIGIN_Z))   # (jr_stand_1 platform depth)
        m.add_child(B.STATIC, T(sid, 'EditRigidObj', name + ' boarding stair (static, never a Door)', *st_o, 0.0, 0.0,
                                float(yaw - math.pi / 2), 'jr_stand_1', 5, False, False))
        out['stair'] = sid
        B.SEAT_SKIP.add(sid)
    for leg, x, y, top, side in gear_layout():
        wxs = [x - 0.20, x + 0.20] if leg == 'nose' else [x + side * 0.06]       # (the twin nose wheels: a pair each)
        for wx in wxs:
            cid = nid()
            m.add_child(B.STATIC, T(cid, 'EditRigidObj', name + ' chocks %s %s' % (leg, 'L' if (side < 0 or wx < x) else 'R'),
                                    *to_world(origin, yaw, (wx, y, -ORIGIN_Z)), 0.0, 0.0, float(yaw), 'jr_chock_1', 5, False, False))
            out['chocks'].append(cid)
            B.SEAT_SKIP.add(cid)
    pt, pu = to_world(origin, yaw, sp['tba']), to_world(origin, yaw, sp['stand'])
    g_tba = float(math.atan2(-(pu[0] - pt[0]), pu[1] - pt[1]))                       # (the TBA's +y looks at the user)
    run = ORIGIN_Z / math.tan(math.radians(32.0))                                   # (jr_stand_1 flight run on the deck)
    foot = to_world(origin, yaw, (sp['edge_x'] - STAND_DEPTH - run - 1.0, sp['y'], -ORIGIN_Z))   # (1 m beyond its foot)
    out.update(cockpit=pt, stand_top=to_world(origin, yaw, (sp['edge_x'] - STAND_DEPTH / 2, sp['y'], STAIR_TOP)),
               use=dict(pos=pt, gamma=g_tba, prop=None, stand=pu), stand_foot=foot,
               feet=[to_world(origin, yaw, (x if k == 'nose' else x + s_ * 0.06, y, -ORIGIN_Z)) for k, x, y, t_, s_ in gear_layout()])
    rep = seat_report()                              # own seat assert (plan Z13): every wheel on the deck plane within 3 cm
    assert rep['ok'], ('jrjet: gear feet off the deck plane', rep)
    out['seat'] = dict(feet_m=rep['feet'], deck_plane_m=-ORIGIN_Z, ok=rep['ok'])
    return out


def dress(B):
    """S7: Pad One - the deck, the parked jet (JR_JET kind), the boarding stair, chocks; B.JET for jrsys / jrbase / CIN.
    The pad: SPOTS['pad'] (MAP), else the plan spot (+100, +72) (jetlab: the flattest patch near it)"""
    assert JET_KIND in ('vl', 'stock'), 'JR_JET must be vl or stock, not %r' % JET_KIND
    need = ['jr_grid_1', 'jr_stand_1', 'jr_chock_1'] + (['jr_jsf_1'] if JET_KIND == 'vl' else ['jr_ngear_1', 'jr_mgear_1'])
    miss = [n for n in need if n not in set(B.LIB.names)]
    assert not miss, 'jrjet.dress: models %s are not registered (jrmodels / jrjet.prep skipped?)' % miss
    pd = B.PADS.get('pad_one') if isinstance(B.PADS, dict) else None
    yaw = -math.pi / 2 + (float(pd.get('angle', 0.0)) if isinstance(pd, dict) else 0.0)     # (nose east; the pad's turn)
    if 'pad' in B.SPOTS:
        c = tuple(B.SPOTS['pad'][:2])
    else:
        c = B.lp(100.0, 72.0)[:2]
        fs = None
        if 'jetlab' in B.DBG:                       # (the pair: 2 decks side by side = 68 x 30 m, the long side across the jets)
            fs = flat_spot(B, (B.C[0] * M, B.C[1] * M), r_m=120.0, half=34.0, half_y=15.0, yaw=yaw)   # (inside the nav box)
            if fs:
                off = _R(yaw)[:2, :2] @ np.array([-17.0, 0.0]) * M
                c = (fs[1] + off[0], fs[2] + off[1])
        B.note('jrjet: no SPOTS[pad] from MAP - the jet stands at %s m (plan spot%s)' % (
            tuple(round(v_ / M, 1) for v_ in c), ', jetlab: flattest patch, range %.2f m' % fs[3] if fs else ''))
    B.JET = place_parked(B, c, yaw, JET_KIND)
    if 'jetlab' in B.DBG:                           # P1: the other kind on its own deck 34 m to the jet's right
        side = _R(yaw)[:2, :2] @ np.array([34.0, 0.0]) * M
        other = 'stock' if JET_KIND == 'vl' else 'vl'
        o2 = place_parked(B, (c[0] + side[0], c[1] + side[1]), yaw, other, name='JR jetlab %s jet (parked)' % other)
        B.JETLAB = {JET_KIND: B.JET, other: o2}
    if B.JET.get('stand_foot') and 'stand' in B.SPOTS:           # (the trio holds 'near the stand': the REAL stair foot)
        old = B.SPOTS['stand']
        B.SPOTS['stand'] = B.JET['stand_foot']
        B.note('jrjet: SPOTS[stand] (%.0f, %.0f) -> the boarding stair foot (%.0f, %.0f) m' % (
            old[0] / M, old[1] / M, B.JET['stand_foot'][0] / M, B.JET['stand_foot'][1] / M))
    B.IDS.update(jet=B.JET['id'], jet_cc=B.JET.get('cc'), jet_stair=B.JET.get('stair'))
    print('jrjet: parked %s jet %d at (%.0f, %.0f) m, deck top %.2f m (ground range %.2f m), stair %s, feet %s' % (
        B.JET['kind'], B.JET['id'], c[0] / M, c[1] / M, B.JET['deck_top'] / M, B.JET['terrain_range_m'], B.JET['stair'],
        B.JET['seat']['feet_m']))
    return B.JET


def clone(B, pts, yaws, speeds_kmh, kind='lift', name='JR jet clone', pitches=None, start='1'):
    """a jet copy on its OWN SplinePathGuide (the cine fly_in mechanism, 'Use Free Orientation' TRUE: the nodes' own
    pitch / yaw keep it level - proven on the 710 lift-off). pts = world units, pts[0] = the start pose; yaws / pitches per
    node (rad; pitch > 0 = nose up). kind: 'parked' jr_jsf_1 | 'lift' jr_jsfl_1 (gear + nozzle glow) | 'up' jr_jsfu_1
    (gear up + glow) | 'stock' 760_01_1 + gear/bomb children. start = the guide's run expression ('1' = as soon as its
    container runs). -> dict(tasks, rigid, guide, secs)"""
    T, nid = B.T, B.nid
    model = {'parked': 'jr_jsf_1', 'lift': 'jr_jsfl_1', 'up': 'jr_jsfu_1', 'stock': None}[kind]
    jt, rid = jet_tasks(B, pts[0], yaws[0], 'stock' if kind == 'stock' else 'vl', name, model=model)
    pitches = pitches or [0.0] * len(pts)
    path, guide = nid(), nid()
    nodes, t_ = [], 0.0
    for k, p in enumerate(pts):
        if k:
            d = math.dist(pts[k - 1], p) / M
            t_ += d / max(0.1, 0.5 * (speeds_kmh[k - 1] + speeds_kmh[k]) / 3.6)
        nxt, prv = pts[min(k + 1, len(pts) - 1)], pts[max(k - 1, 0)]
        tg = np.array(nxt, float) - np.array(prv, float)
        nodes.append(T(nid(), 'SplinePathNodeQTask', '', *[float(c) for c in p], float(pitches[k]), 0.0, float(yaws[k]), True,
                       float(speeds_kmh[k]), float(round(t_, 6)), *[float(c) for c in tg], True))
    box = T(nid(), 'Container', name + ' path', False, children=[
        T(path, 'SplinePathDynCubeObj', '', False, children=nodes),
        T(guide, 'SplinePathGuideQTask', '', path, rid, False, False, 0.0, children=[
            T(nid(), 'SequenceCommand', '', start, 'SplinePathGuide_SetRunning (TRUE);', '', '')])])
    for t2, d2, p2 in B.tasks([jt]):                   # (the carrier is skipped by the builder; its children too)
        B.SEAT_SKIP.add(int(B.lit(t2.args[0])))
    return dict(tasks=[jt, box], rigid=rid, guide=guide, secs=t_)


def lift_path(origin, yaw, up_m=15.0, fwd_m=60.0):
    """the P1 / O2 lift: straight up up_m, a beat, then forward fwd_m climbing 3 m -> (pts, yaws, speeds km/h)"""
    o = np.asarray(origin, float)
    f = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    pts = [o, o + [0, 0, 0.5 * M], o + [0, 0, up_m * 0.6 * M], o + [0, 0, up_m * M], o + f * 6 * M + [0, 0, (up_m + 0.5) * M],
           o + f * fwd_m * 0.5 * M + [0, 0, (up_m + 1.5) * M], o + f * fwd_m * M + [0, 0, (up_m + 3.0) * M]]
    speeds = [1.0, 6.0, 13.0, 4.0, 14.0, 42.0, 60.0]
    return [tuple(float(c) for c in p) for p in pts], [float(yaw)] * len(pts), speeds


def debug(B):
    """S15 'jetlab' (P1): the intro replaced by a 5-shot test of both parked jets: a 3/4 view, the gear on each deck, the
    15 m lift + 60 m forward (one clone of each kind side by side, own guides), a dolly-out to ~600 m (LOD pops)"""
    if 'jetlab' not in B.DBG:
        return None
    CS = B.CS
    A, Bk = B.JETLAB['vl'], B.JETLAB['stock']
    yaw = A['yaw']
    f = np.array([-math.sin(yaw), math.cos(yaw), 0.0]); s_ = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    oa, ob = np.array(A['origin']), np.array(Bk['origin'])
    mid = (oa + ob) / 2

    def up(p, h):
        return (float(p[0]), float(p[1]), float(B.TER.height(p[0], p[1])) + h * M)
    shots = []
    c1, c1b = mid + f * 30 * M - s_ * 14 * M, mid + f * 26 * M - s_ * 6 * M
    shots.append(dict(label='jetlab 1 parked pair', vhf=1.0, keys=[CS.key(up(c1, 5.0), tuple(mid), 6.0, True, fov=0.95, noise=0.0),
                                                                  CS.key(up(c1b, 4.0), tuple(mid), 0.0, False, fov=0.95, noise=0.0)]))
    for J, lab in ((A, 'vl'), (Bk, 'stock')):
        ft = np.array(J['feet'][1])                  # (the port main leg)
        cam = ft - s_ * 7.5 * M + f * 2.0 * M
        cam = (float(cam[0]), float(cam[1]), float(J['deck_top']) + 1.25 * M)
        tg = (float(ft[0]), float(ft[1]), float(J['deck_top']) + 0.7 * M)
        shots.append(dict(label='jetlab gear %s' % lab, vhf=1.0, keys=[CS.key(cam, tg, 4.0, False, fov=0.9, noise=0.0),
                                                                     CS.key(cam, tg, 0.0, False, fov=0.9, noise=0.0)]))
    extra, secs = [], 0.0
    for J, kind in ((A, 'lift'), (Bk, 'stock')):
        o = np.array(J['origin']) + f * 45 * M
        o[2] = float(B.TER.height(o[0], o[1])) + ORIGIN_Z * M
        pts, yaws, spd = lift_path(o, yaw)
        cl = clone(B, pts, yaws, spd, kind=kind, name='JR jetlab clone %s' % kind)
        extra += cl['tasks']; secs = max(secs, cl['secs'])
    lm = mid + f * 75 * M
    c4 = lm - s_ * 70 * M
    shots.append(dict(label='jetlab 4 lift 15 m + 60 m', vhf=1.0, extra=extra,
                      keys=[CS.key(up(c4, 7.0), up(lm, 9.0), round(secs + 1.5, 2), True, fov=1.0, noise=0.0),
                            CS.key(up(c4, 7.0), up(lm + f * 30 * M, 14.0), 0.0, False, fov=1.0, noise=0.0)]))
    st = np.array(B.START[:2]) if getattr(B, 'START', None) else np.array([mid[0] - 600 * M, mid[1]])
    d = np.array([st[0] - mid[0], st[1] - mid[1], 0.0]); d /= max(1e-6, np.linalg.norm(d))
    p0, p1 = mid + d * 25 * M, mid + d * 600 * M
    shots.append(dict(label='jetlab 5 dolly out', vhf=1.0, keys=[CS.key(up(p0, 6.0), tuple(mid), 20.0, True, fov=0.8, noise=0.0),
                                                                 CS.key(up(p1, 120.0), tuple(mid), 0.0, False, fov=0.8, noise=0.0)]))
    B.fill_intro(shots)
    B.IDS.update(jetlab=dict(vl=A['id'], stock=Bk['id'], shots=[s['label'] for s in shots], lift_secs=round(secs, 2)))
    print('debug jetlab: vl jet %d + stock jet %d, intro %d shots, lift %.1f s' % (A['id'], Bk['id'], len(shots), secs))
    return shots


def _render_mef(sc, mf, slots, textures, R=np.eye(3), pos=(0, 0, 0)):
    r = mefmesh.RigidModel.from_mef(mf)
    mats = {}
    for g in r.groups:
        if g.tex not in mats:
            img = textures[slots[g.tex]]() if g.tex < len(slots) else None
            mats[g.tex] = sc.material(img, color=(0.6, 0.6, 0.6))
        P = g.pos.astype(float) @ R.T + np.asarray(pos, float)
        N = g.nrm.astype(float) @ R.T
        sc.add_tris(P[g.tris], N[g.tris], g.uv[g.tris], mats[g.tex], double=False)
    gl = mf.get('WOLG') if any(c.tag == 'WOLG' for c in mf.chunks) else None
    return r


def preview(out_dir):
    """offline proof sheets for P1 (an offline preview is NOT in-game proof)"""
    import mefrender
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    lib = MK.Library(); add_models(lib)
    meshes = lib.build()
    tex = lib.textures
    sh = seat_report(meshes['jr_jsf_1'])
    files = []

    def sheet(path, tiles, cols=3, W=640, H=400):
        rows = (len(tiles) + cols - 1) // cols
        im = Image.new('RGB', (cols * W, rows * (H + 18)), 'black'); dr = ImageDraw.Draw(im)
        for i, (lab, t) in enumerate(tiles):
            x, y = (i % cols) * W, (i // cols) * (H + 18)
            im.paste(t.convert('RGB').resize((W, H)), (x, y + 18)); dr.text((x + 4, y + 3), lab, fill='yellow')
        im.save(path); files.append(path)

    def scene(names, deck=True):
        sc = mefrender.Scene()
        for nm, pos in names:
            _render_mef(sc, meshes[nm], lib.slots[nm], tex, pos=np.asarray(pos, float) * M)
        if deck:
            sc.add_ground(z=-ORIGIN_Z * M, half=60 * M, color=(0.42, 0.43, 0.42))
        return sc
    tiles = []
    for nm in VL_NAMES:
        for lab, eye in (('3/4 front', (26, 24, 9)), ('3/4 rear low', (-22, -26, 1.5))):
            sc = scene([(nm, (0, 0, 0))])
            c = np.array([0, -1.0, -0.6]) * M
            tiles.append(('%s %s' % (nm, lab), sc.render(c + np.array(eye) * M, c, size=(640, 400), fov=36, ss=1)))
    sheet(os.path.join(out_dir, 'p1_jsf_vl.png'), tiles)
    # gear close-ups + the deck contact
    tiles = []
    for kind, x, y, top, side in gear_layout():
        sc = scene([('jr_jsf_1', (0, 0, 0))])
        tgt = np.array([x, y, -ORIGIN_Z + 0.6]) * M
        eye = tgt + np.array([5.5 * (1 if x >= 0 else -1) if kind == 'main' else 4.5, 3.0, 0.6]) * M
        tiles.append(('%s gear x %.2f y %.2f (hull z %.2f) feet %s' % (kind, x, y, top, ['%.3f' % f for f in sh['feet']]),
                      sc.render(eye, tgt, size=(640, 400), fov=40, ss=1)))
    sc = scene([('jr_jsf_1', (0, 0, 0))])
    tiles.append(('side at deck level: feet on z = -%.2f (ok=%s)' % (ORIGIN_Z, sh['ok']),
                  sc.render(np.array([30, -1.0, -ORIGIN_Z + 0.3]) * M, np.array([0, -1.0, -ORIGIN_Z + 0.8]) * M, size=(640, 400), fov=30, ss=1)))
    sheet(os.path.join(out_dir, 'p1_jsf_gear.png'), tiles, cols=2)
    # the lift strip: 0, 5, 10, 15 m up, then forward
    tiles = []
    for k, (dz, dy, nm) in enumerate(((0, 0, 'jr_jsf_1'), (5, 0, 'jr_jsfl_1'), (10, 0, 'jr_jsfl_1'), (15, 0, 'jr_jsfl_1'),
                                      (15, 30, 'jr_jsfu_1'), (16, 60, 'jr_jsfu_1'))):
        sc = scene([(nm, (0, dy, dz))])
        eye = np.array([38, 10, 2.0]) * M
        tiles.append(('lift +%d m up, +%d m fwd (%s)' % (dz, dy, nm), sc.render(eye, np.array([0, dy, dz]) * M, size=(640, 400), fov=60, ss=1)))
    sheet(os.path.join(out_dir, 'p1_jsf_lift.png'), tiles)
    # distance strip (single LOD: nothing can pop; framing as an outro camera at fov 0.9 rad)
    tiles = []
    for d in (15, 60, 200, 450, 900):
        sc = scene([('jr_jsf_1', (0, 0, 0))], deck=True)
        eye = np.array([d * 0.7, d * 0.7, max(3.0, d * 0.12)]) * M
        tiles.append(('%d m' % d, sc.render(eye, np.array([0, 0, 0]) * M, size=(640, 400), fov=math.degrees(0.9) if d < 200 else 12, ss=1)))
    sheet(os.path.join(out_dir, 'p1_jsf_dist.png'), tiles)
    return dict(files=files, seat=sh, tris={n: int(m_.hsem['n_rfaces']) for n, m_ in meshes.items()})


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'preview':
        print(preview(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'joyride', 'art')))
    else:
        print(__doc__)
