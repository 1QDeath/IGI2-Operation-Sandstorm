"""sssoldiers - NEW Sandstorm soldiers (owner 11-05 items 52, 53): real Iraqi looks, every man his own face.

How the engine draws a soldier: a skin is one VNAM row = one character mesh + its texture slots (body, head, glass). Hats are
GEOMETRY of the mesh (resg_1 has a cap), so a texture can never remove them: bare heads need a bare-headed mesh. Every original
human shares the same 31 bones, so any of them runs any soldier animation. Textures are shared between VNAMs, so the cost of
another man is one VNAM row + what he alone adds. Far LOD: a skin with only its _1 name stays on that mesh at every distance
(lod rows 1344+), no pop to the originals' _2.._5 meshes.

Head textures are cylindrical panoramas (u = angle round the head, centre = the nose, seam at the back of the head). The faces are
invented people: SDXL portraits on this PC (igi2-face-tools/gen_faces.py, prompts + seeds kept beside them), warped landmark by
landmark onto the rsg_1 panorama (facewarp.py there), finished as head maps in work/sandstorm/soldiers/heads/<man>.png.
Other meshes get them through bake(): texel by texel from the 3D surface of the rsg_1 head.

    import sssoldiers as SS
    names = SS.add_skins(overlay_dir, 'sandstorm')         # after the forge; registers meshes, textures, VNAMs
    SS.assign(m, K)                                        # last pass: every soldier and cutscene actor gets his man
    lodfix.apply(..., extra={**SS.lod_rows()})
    python -P tools/sssoldiers.py preview [out_dir]
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, igitex, mefmesh, wreck
import skinforge as SF
import jrskins as JR

GAME = wreck.GAME
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADS = os.environ.get('SS_HEADS') or os.path.join(ROOT, 'work', 'sandstorm', 'soldiers', 'heads')   # (SS_HEADS: a test tree's own head maps, the shared dir untouched)
LOC = {'rsg_1': 'location1', 'les_1': 'location2', 'infgu_1': 'location2', 'libgu_1': 'location2', 'zib_1': None, 'priboi_1': 'location2',
       'csf_1': 'location3'}


_FOUND = {}                                                        # (a bank is read whole: one pass over them per name took 15 GB on the node)


def _find(kind, names):
    """the original resources `names` of kind 'models' / 'textures': one pass over the banks, only what is wanted stays in memory"""
    import glob
    ext = {'models': 'mef', 'textures': 'tex'}[kind]
    todo = {'LOCAL:%s/%s.%s' % (kind, n, ext): n for n in names if (kind, n) not in _FOUND}
    if not todo:
        return
    banks = glob.glob(os.path.join(GAME, 'MISSIONS', 'location*', '**', kind, '*.res'), recursive=True) + \
        [os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', kind, 'multiplayer.res')]
    for p in banks:
        ch, nm = SF._bank(p)
        for k in [k for k in todo if k in nm]:
            _FOUND[kind, todo.pop(k)] = bytes(ch[nm[k]][1])
        del ch, nm
        if not todo:
            return
    raise KeyError(sorted(todo))


def _model_bytes(mesh):
    """the original .mef of a character mesh, wherever the game ships it"""
    _find('models', ['rsg_1', 'les_1', 'infgu_1', 'resg_1', 'csf_1', mesh])
    return _FOUND['models', mesh]


def _bone_names(m):
    return [bytes(x['name']).split(b'\0')[0].decode('latin1') for x in m.get('MANB')]


def head_group(m):
    """(group index, v0, n verts) of the render group that carries the most head-bone vertices"""
    X, names = m.get('XTRV'), _bone_names(m)
    hb = [i for i, n in enumerate(names) if n in ('head', 'rotate_head', 'head end')]
    best = None
    for k, g in enumerate(m.get('DNER')):
        v0, n = int(g['v0']), int(g['nverts'])
        c = int(np.isin(X['bone'][v0:v0 + n], hb).sum())
        if best is None or c > best[0]:
            best = (c, k, v0, n)
    return best[1:]


def _raster(P, U, T, W, H):
    """rasterise triangles T in uv space: -> (iy, ix, 3D point at each covered texel)"""
    ys, xs, pts = [], [], []
    UV = U * np.array([W, H]) - 0.5
    for t in T:
        a, b, c = UV[t[0]], UV[t[1]], UV[t[2]]
        x0, x1 = int(max(0, math.floor(min(a[0], b[0], c[0])))), int(min(W - 1, math.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = int(max(0, math.floor(min(a[1], b[1], c[1])))), int(min(H - 1, math.ceil(max(a[1], b[1], c[1]))))
        if x1 < x0 or y1 < y0:
            continue
        gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        l0 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / d
        l1 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / d
        l2 = 1 - l0 - l1
        ok = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not ok.any():
            continue
        ys.append(gy[ok]); xs.append(gx[ok])
        pts.append(l0[ok, None] * P[t[0]] + l1[ok, None] * P[t[1]] + l2[ok, None] * P[t[2]])
    return np.concatenate(ys), np.concatenate(xs), np.concatenate(pts)


def _group_tris(m, k):
    g = m.get('DNER')[k]
    I = m.get('ECAF')['v'].astype(int)
    i0, nt = int(g['i0']), int(g['ntris'])
    return I.reshape(-1)[i0:i0 + 3 * nt].reshape(-1, 3)


def bake(head_rsg, base_tex, target_mesh, max_cm=2.5, src_mesh='rsg_1'):
    """head_rsg (RGB float, rsg_1 layout) -> a head texture for target_mesh: every texel takes the colour of the nearest point of the
    rsg_1 head; texels further than max_cm from it (helmet rims, beret bands, collars) keep the mesh's own base_tex"""
    from scipy.spatial import cKDTree
    a = mefmesh.Mef.read(_model_bytes(src_mesh)); b = mefmesh.Mef.read(_model_bytes(target_mesh))
    Pa, _, Ua = JR.bind_pose(a); Pb, _, Ub = JR.bind_pose(b)
    ka = head_group(a)[0]; kb = head_group(b)[0]
    H, W = head_rsg.shape[:2]
    ya, xa, pa = _raster(Pa, Ua, _group_tris(a, ka), W, H)
    Hb, Wb = base_tex.shape[:2]
    yb, xb, pb = _raster(Pb, Ub, _group_tris(b, kb), Wb, Hb)
    tree = cKDTree(pa)
    d, j = tree.query(pb)
    out = base_tex[..., :3].copy()
    near = np.clip((max_cm * 40.96 - d) / (0.8 * 40.96), 0, 1)[..., None]
    out[yb, xb] = head_rsg[ya[j], xa[j], :3] * near + out[yb, xb] * (1 - near)
    return out


# head shapes: small changes of the rsg_1 head so that silhouettes differ too (cm at the skull / jaw); y = forward, z = up
SHAPES = {
    'plain': {},
    'shaved': dict(crown=-0.8),
    'heavy': dict(crown=-0.6, wide=0.5, jaw=0.7),
    'thin': dict(crown=-0.4, wide=-0.3, jaw=-0.5, long=0.5),
    'bigbeard': dict(crown=-0.8, beard=1.6),
}


def morph(m, shape):
    """bytes of a copy of mesh m with its head vertices moved by SHAPES[shape] (counts, UVs, bones, mouth morph untouched)"""
    s = SHAPES[shape]
    X = m.get('XTRV')
    names = _bone_names(m)
    hb = [i for i, n in enumerate(names) if n in ('head', 'rotate_head', 'head end')]
    P, _, U = JR.bind_pose(m)
    nv = len(P)
    sel = np.isin(X['bone'][:nv], hb)
    c = P[sel].mean(0)
    top, chin = P[sel, 2].max(), P[sel, 2].min()
    h = (P[:, 2] - chin) / max(1.0, top - chin)                  # 0 = neck, 1 = crown
    q = P - c
    d = np.zeros_like(P)
    cm = 40.96
    if s.get('crown'):
        d[:, 2] += s['crown'] * cm * np.clip((h - 0.55) / 0.45, 0, 1) ** 2
    if s.get('wide'):
        d[:, 0] += np.sign(q[:, 0]) * s['wide'] * cm * np.clip(np.abs(q[:, 0]) / (7.0 * cm), 0, 1) * np.clip(h / 0.5, 0, 1)
    if s.get('jaw'):
        k = np.clip((0.55 - h) / 0.3, 0, 1) * np.clip(h / 0.15, 0, 1)
        d[:, 0] += np.sign(q[:, 0]) * s['jaw'] * cm * k * np.clip(np.abs(q[:, 0]) / (5.0 * cm), 0, 1)
    if s.get('long'):
        d[:, 2] -= s['long'] * cm * np.clip((0.45 - h) / 0.3, 0, 1) * np.clip(h / 0.15, 0, 1)
    if s.get('beard'):
        k = np.clip((0.48 - h) / 0.2, 0, 1) * np.clip((h - 0.10) / 0.1, 0, 1) * (q[:, 1] > -2.0 * cm)
        fwd = np.clip(q[:, 1] / (8.0 * cm), 0.2, 1)
        d[:, 1] += s['beard'] * cm * k * fwd
        d[:, 2] -= 0.8 * s['beard'] * cm * k * fwd
    X = X.copy()
    mv = sel                                                     # first records = head vertices on one head bone
    X['pos'][:nv][mv] = X['pos'][:nv][mv] + d[mv].astype(np.float32)
    for c_ in m.chunks:
        if c_.tag == 'XTRV':
            c_.rec = X
    return m.write()


# body builds: every vertex moves along its own smoothed normal, by region (metres); the bones, UVs and animations stay, so any clip fits
def scale_mesh(data, s):
    """the whole man s times taller: skeleton offsets and every vertex; the feet stay on the ground only if the clips carry no absolute height"""
    m = mefmesh.Mef.read(data)
    for c_ in m.chunks:
        if c_.tag == 'XTRV':
            X = c_.rec.copy(); X['pos'] = X['pos'] * s; c_.rec = X
        elif c_.tag == 'REIH':
            r = dict(c_.rec); r['offset'] = r['offset'] * s; c_.rec = r
        elif c_.tag == 'ATTA':
            a = c_.rec.copy(); a['pos'] = a['pos'] * s; c_.rec = a
    return m.write()


def build_mesh(data, build):
    """bytes of mesh `data` reshaped to a build: 'fat', 'muscle', 'skinny' (welded, so no seam opens)"""
    m = mefmesh.Mef.read(data)
    P, _, _ = JR.bind_pose(m)
    X = m.get('XTRV').copy()
    names = _bone_names(m)
    nv = len(P)
    bone = np.array([names[i] for i in X['bone'][:nv]])
    I = m.get('ECAF')['v'].astype(int)
    key = np.round(P / 6.0).astype(np.int64)
    _, wid = np.unique(key, axis=0, return_inverse=True)
    wid = wid.reshape(-1)
    nw = int(wid.max()) + 1
    fn = -np.cross(P[I[:, 1]] - P[I[:, 0]], P[I[:, 2]] - P[I[:, 0]])
    Nw = np.zeros((nw, 3))
    for c in range(3):
        np.add.at(Nw, wid[I[:, c]], fn)
    Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-9)
    Pw = np.zeros((nw, 3)); np.add.at(Pw, wid, P); Pw /= np.maximum(np.bincount(wid, minlength=nw), 1)[:, None]
    z, y = Pw[:, 2] / 4096.0, Nw[:, 1]

    def on(*bs):
        v = np.zeros(nw); np.maximum.at(v, wid, np.isin(bone, bs).astype(float)); return v
    tor = on('center', 'lower body', 'upper body', 'shoulders') * (z < 1.54) * (z > 0.8)
    arm_u, arm_l = on('upper left arm', 'upper right arm'), on('lower left arm', 'lower right arm')
    leg_u, leg_l = on('upper left leg', 'upper right leg'), on('lower left leg', 'lower right leg')
    g = lambda c, s: np.exp(-((z - c) / s) ** 2)
    front = np.clip(y, 0, 1)
    if build == 'fat':
        a = tor * (0.030 + 0.085 * g(1.03, 0.17) * (0.30 + 0.70 * front) + 0.020 * g(1.34, 0.10)) + 0.022 * arm_u + 0.012 * arm_l + 0.032 * leg_u + 0.012 * leg_l
    elif build == 'muscle':
        a = tor * (0.016 + 0.052 * g(1.38, 0.11) * (0.45 + 0.55 * front) - 0.016 * g(1.03, 0.10)) + 0.038 * arm_u + 0.024 * arm_l + 0.028 * leg_u + 0.016 * leg_l
    elif build == 'skinny':
        a = tor * (-0.024 - 0.012 * g(1.03, 0.14) * front) - 0.011 * arm_u - 0.006 * arm_l - 0.015 * leg_u - 0.007 * leg_l
    else:
        raise KeyError(build)
    e = np.unique(np.sort(wid[np.concatenate([I[:, [0, 1]], I[:, [1, 2]], I[:, [2, 0]]])], axis=1), axis=0)
    for _ in range(6):                                            # no steps at the wrists, the neck, the belt
        s_, c_ = np.zeros(nw), np.zeros(nw)
        np.add.at(s_, e[:, 0], a[e[:, 1]]); np.add.at(s_, e[:, 1], a[e[:, 0]])
        np.add.at(c_, e[:, 0], 1.0); np.add.at(c_, e[:, 1], 1.0)
        a = 0.5 * a + 0.5 * s_ / np.maximum(c_, 1.0)
    fixed = on('left hand', 'right hand', 'head', 'rotate_head', 'head end', 'left foot', 'right foot', 'left toe', 'right toe')
    a = a * (1 - fixed)
    dw = Nw * a[:, None] * 4096.0
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    nc, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nw, nw)), directed=False)
    big = np.bincount(lab).argmax()
    for c in range(nc):                                           # pouch, knife sheath: separate parts, they ride on the body and keep their shape
        if c != big:
            A, B = np.where(lab == c)[0], np.where(lab == big)[0]
            near = B[np.argmin(np.linalg.norm(Pw[B][None] - Pw[A][:, None], axis=2), axis=1)]
            dw[A] = dw[near].mean(0)
    d = dw[wid]
    rec = np.arange(len(X))
    v = np.where(rec < nv, rec, X['vi'].astype(int))              # every influence of a vertex moves with it (no bone rotates in bind pose)
    X['pos'] = (X['pos'].astype(float) + d[v]).astype(np.float32)
    for c_ in m.chunks:
        if c_.tag == 'XTRV':
            c_.rec = X
    return m.write()


# ===================================================================================================== bodies
# regions of each original's body sheet (fractions x0, y0, x1, y1; read off the shipped sheets)
RSG = dict(jacket=(0.0, 0.0, 0.545, 0.56), sleeves=(0.0, 0.56, 0.34, 1.0), legs=(0.545, 0.0, 1.0, 0.71), pocket=(0.34, 0.56, 0.545, 0.69),
           hands=(0.34, 0.69, 0.53, 0.80), sole=(0.53, 0.69, 0.71, 0.80), shoes=(0.34, 0.80, 0.72, 1.0), badge=(0.78, 0.70, 0.92, 0.82))
LES = dict(vest=(0.0, 0.0, 0.50, 0.52), legs=(0.0, 0.52, 0.50, 1.0), sleeves=(0.73, 0.0, 0.93, 0.27), arms=(0.50, 0.0, 0.73, 0.27), hands=(0.50, 0.27, 0.65, 0.42),
           glove=(0.65, 0.27, 0.86, 0.45), legs2=(0.50, 0.52, 0.75, 0.80))
INF = dict(shirt=(0.0, 0.0, 0.62, 0.45), legs=(0.0, 0.45, 0.53, 1.0), sleeves=(0.75, 0.0, 1.0, 0.18), beret=(0.78, 0.18, 1.0, 0.36),
           hands=(0.62, 0.18, 0.78, 0.32), pocket=(0.53, 0.45, 0.62, 0.56), collar=(0.75, 0.62, 1.0, 0.82), skin=(0.52, 0.69, 0.745, 1.0))
# rsg_1's knife sheath = a loose tube (111 verts) on the outer right thigh, z 0.68-1.03 m: its sides and tip use this corner of the sheet, its top cap a
# few texels inside 'legs'. THIGH = the trouser cloth right behind it (outer right thigh, between the side seam at u 0.79 and the edge), about the
# tube's own 20 x 35 cm, so resampled into the corner the weave keeps the trousers' scale
RSG_SHEATH, RSG_THIGH = (0.72, 0.815, 1.0, 1.0), (0.80, 0.06, 0.96, 0.31)


def shipped(name):
    _find('textures', ['ch_rsg_01', 'les_2', 'ch_infgu_2', 'ch_rsg_00', 'les_1', 'ch_infgu_1', 'ch_resg_01', 'ch_resg_00', 'csf_2', 'csf_1', name])
    return igitex.decode(_FOUND['textures', name])


def _frog(h, w, rng, cols):
    """Iraqi issue camouflage: broad overlapping leaf blobs, three colours on a light base (no copy of a named pattern)"""
    out = np.empty((h, w, 3)); out[:] = cols[0]
    for k, c in enumerate(cols[1:]):
        n = SF._noise(h, w, rng, scale=9 + 5 * k, octaves=3)
        out[n > np.percentile(n, 58 + 13 * k)] = c
    return out


def _paint(img, box, col, keep=0.86, rng=None, wool=0.10):
    SF.recolor(img, SF._rect(img, *box), col, keep_shading=keep, rng=rng, wool=wool)


def _camo(img, box, cols, rng):
    sl = SF._rect(img, *box)
    reg = img[sl]
    h, w = reg.shape[:2]
    L = SF._lum(reg)
    sh = 0.16 + 0.88 * np.clip(L / max(1e-6, float(np.percentile(L, 90))), 0, 1.3)
    reg[..., :3] = np.clip(_frog(h, w, rng, cols) * sh[..., None], 0, 1)


def _triangle(img, box, col=(0.60, 0.06, 0.05)):
    """the Republican Guard shoulder flash: a small red triangle"""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = box[0] * W, box[1] * H, box[2] * W, box[3] * H
    yy, xx = np.mgrid[int(y0):int(y1), int(x0):int(x1)]
    t = (yy - y0) / max(1.0, y1 - y0)
    inside = np.abs(xx - (x0 + x1) / 2) < (1 - t) * (x1 - x0) / 2
    img[int(y0):int(y1), int(x0):int(x1), :3][inside] = col


OLIVE, DKOLIVE, KHAKI, SAND = (0.31, 0.32, 0.20), (0.20, 0.22, 0.14), (0.47, 0.42, 0.28), (0.60, 0.53, 0.38)
FROG = [(0.47, 0.44, 0.30), (0.27, 0.30, 0.18), (0.36, 0.26, 0.16), (0.11, 0.11, 0.09)]
LIZARD = [(0.55, 0.50, 0.36), (0.35, 0.33, 0.20), (0.26, 0.20, 0.13), (0.14, 0.12, 0.09)]


def _mask_paint(img, mask, col, keep=0.86):
    L = SF._lum(img[..., :3])
    if not mask.any():
        return
    ref = max(1e-3, float(np.percentile(L[mask], 60)))
    img[..., :3][mask] = np.clip(np.array(col)[None, :] * (1 - keep + keep * (L[mask] / ref))[:, None], 0, 1)


def _mask_camo(img, mask, cols, rng):
    H, W = img.shape[:2]
    L = SF._lum(img[..., :3])
    ref = max(1e-3, float(np.percentile(L[mask], 90))) if mask.any() else 1.0
    c = _frog(H, W, rng, cols)
    sh = 0.16 + 0.88 * np.clip(L / ref, 0, 1.3)
    img[..., :3][mask] = np.clip(c[mask] * sh[mask][:, None], 0, 1)


def _cover(img, box, src):
    """region box := the cloth of region src resampled to its size: the trousers' own colour, weave and shading (S21: no knife sheath)"""
    from PIL import Image
    d, s = SF._rect(img, *box), SF._rect(img, *src)
    h, w = img[d].shape[:2]
    img[d][..., :3] = np.clip(np.dstack([np.asarray(Image.fromarray(np.ascontiguousarray(img[s][..., c], np.float32)).resize((w, h), Image.BICUBIC))
                                         for c in range(3)]), 0, 1)   # (colour only, as _paint: alpha stays the sheet's)


def _masks(img):
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    blue = (b > r + 0.04) & (b > g)
    green = (g > r + 0.015) & (g > b + 0.015) & (g > 0.06)
    skin = (r > g + 0.06) & (g > b + 0.02) & (r > 0.30)
    return blue, green, skin


def body(kind, seed, skin=(0.62, 0.45, 0.33), sheath=True):
    """float RGBA body sheets. rsg_* on rsg_1 (bare head), les_* on les_1 (helmet + vest), inf_* on infgu_1 (shirt + beret).
    sheath=False (rsg_* only): the knife sheath wears the trouser cloth beside it (NO_SHEATH)"""
    rng = np.random.default_rng(seed)
    if kind.startswith('rsg'):
        img = shipped('ch_rsg_01').copy()
        R = RSG
        boots = (0.075, 0.065, 0.055)
        if kind == 'rsg_olive':                                    # conscript: plain olive fatigues
            _paint(img, R['jacket'], OLIVE, rng=rng); _paint(img, R['sleeves'], OLIVE, rng=rng); _paint(img, R['legs'], (0.29, 0.30, 0.19), rng=rng)
        elif kind == 'rsg_frog':                                   # issue camouflage shirt, olive trousers
            _camo(img, R['jacket'], FROG, rng); _camo(img, R['sleeves'], FROG, rng); _paint(img, R['legs'], DKOLIVE, rng=rng)
        elif kind == 'rsg_lizard':                                 # the Guard's lizard camouflage, shirt and trousers
            for b in ('jacket', 'sleeves', 'legs'):
                _camo(img, R[b], LIZARD, rng)
        elif kind == 'rsg_jeans':                                  # shirt and jeans: faded grey-white shirt, the shipped jeans
            _paint(img, R['jacket'], (0.62, 0.61, 0.56), rng=rng, keep=0.92); _paint(img, R['sleeves'], (0.60, 0.59, 0.54), rng=rng, keep=0.92)
            boots = (0.20, 0.12, 0.07)
        elif kind == 'rsg_jeans2':                                 # brown work shirt, dark jeans
            _paint(img, R['jacket'], (0.34, 0.27, 0.22), rng=rng); _paint(img, R['sleeves'], (0.32, 0.25, 0.21), rng=rng)
            _paint(img, R['legs'], (0.13, 0.15, 0.22), rng=rng, keep=0.92, wool=0.2)
            boots = (0.16, 0.10, 0.06)
        elif kind == 'rsg_leather':                                # the secret police man: black leather jacket
            _paint(img, R['jacket'], (0.075, 0.07, 0.07), keep=0.95, rng=rng, wool=0.0); _paint(img, R['sleeves'], (0.075, 0.07, 0.07), keep=0.95, rng=rng, wool=0.0)
            _paint(img, R['legs'], (0.19, 0.18, 0.17), rng=rng)
        elif kind == 'rsg_suit':                                   # Kral, the foreign broker: cream linen suit, light trousers, polished brown shoes
            _paint(img, R['jacket'], (0.74, 0.70, 0.60), keep=0.9, rng=rng, wool=0.0); _paint(img, R['sleeves'], (0.73, 0.69, 0.59), keep=0.9, rng=rng, wool=0.0)
            _paint(img, R['legs'], (0.66, 0.62, 0.53), keep=0.9, rng=rng, wool=0.0)
            boots = (0.24, 0.12, 0.05)
        elif kind == 'rsg_tech':                                   # base technician: blue-grey overall
            for b in ('jacket', 'sleeves', 'legs'):
                _paint(img, R[b], (0.27, 0.32, 0.37), rng=rng)
        _paint(img, R['pocket'], (0.72, 0.68, 0.58) if kind == 'rsg_suit' else (0.22, 0.22, 0.15), rng=rng)
        _paint(img, R['hands'], skin, keep=0.8)
        _paint(img, R['shoes'], boots, keep=0.75)
        if sheath:
            _paint(img, RSG_SHEATH, (0.66, 0.62, 0.53) if kind == 'rsg_suit' else (0.075, 0.065, 0.055), keep=0.55)    # (the knife sheath: dull leather, no shining steel; Kral's suit has none)
        else:
            _cover(img, RSG_SHEATH, RSG_THIGH)                     # (S21: no knife on the train crew - the tube reads as a fold of the trousers)
        _paint(img, R['badge'], (0.73, 0.69, 0.59) if kind == 'rsg_suit' else (0.16, 0.16, 0.12), keep=0.2)   # (no unit patch on Kral's sleeve)
        if 'lizard' in kind:
            _triangle(img, (0.12, 0.58, 0.20, 0.64))
        return img
    if kind.startswith('resg'):                                    # cap, tactical vest, sleeves, trousers (the shipped jeans)
        img = shipped('ch_resg_01').copy()
        blue, green, sk = _masks(img)
        if kind == 'resg_olive':
            _mask_paint(img, blue, DKOLIVE, keep=0.9); _mask_paint(img, green, OLIVE)
        elif kind == 'resg_lizard':
            _mask_camo(img, blue, LIZARD, rng); _mask_paint(img, green, (0.36, 0.33, 0.21))
        elif kind == 'resg_tan':                                   # Hadi: sand trousers, dark brown shirt and vest, worn by nobody else
            _mask_paint(img, blue, (0.60, 0.50, 0.34), keep=0.9); _mask_paint(img, green, (0.27, 0.22, 0.17))
        _mask_paint(img, sk, skin, keep=0.8)
        _paint(img, (0.745, 0.06, 0.835, 0.175), (0.07, 0.07, 0.07), keep=0.3)      # (the cap badge: no foreign eagle)
        _paint(img, (0.80, 0.50, 1.0, 0.70), (0.075, 0.065, 0.055), keep=0.55)    # (knife sheath: dull leather)
        return img
    if kind.startswith('csf'):                                     # balaclava man: desert camouflage instead of the shipped woodland
        img = shipped('csf_2').copy()
        H, W = img.shape[:2]
        blue, green, sk = _masks(img)
        yy = np.arange(H)[:, None] / H; xx = np.arange(W)[None, :] / W
        camo = green & (yy > 0.5) & (xx < 0.75)
        _mask_camo(img, camo, FROG, rng); _mask_paint(img, green & ~camo, (0.36, 0.33, 0.22))
        _mask_paint(img, sk, skin, keep=0.8)
        return img
    if kind.startswith('les'):
        img = shipped('les_2').copy()
        R = LES
        vest = {'les_olive': (0.13, 0.15, 0.10), 'les_black': (0.06, 0.06, 0.065)}[kind]
        _paint(img, R['vest'], vest, keep=0.92, rng=rng)
        cols = LIZARD if kind == 'les_olive' else FROG
        for b in ('legs', 'legs2'):
            _camo(img, R[b], cols, rng)
        _paint(img, R['sleeves'], (0.36, 0.33, 0.21), rng=rng)
        _paint(img, R['arms'], skin, keep=0.8, wool=0.0); _paint(img, R['hands'], skin, keep=0.8, wool=0.0)
        return img
    if kind.startswith('inf'):
        img = shipped('ch_infgu_2').copy()
        R = INF
        shirt, beret = {'inf_officer': ((0.25, 0.27, 0.17), (0.035, 0.035, 0.04)), 'inf_khaki': ((0.36, 0.30, 0.20), (0.12, 0.09, 0.06)),   # (brown shirt, brown beret: next to the general he must not read as him)
                        'inf_general': ((0.60, 0.57, 0.48), (0.22, 0.27, 0.11))}[kind]   # (judge J10: the general in pale stone and a green beret, never the colonel's look)
        for b in ('shirt', 'sleeves', 'legs', 'collar', 'pocket'):
            _paint(img, R[b], shirt, rng=rng)
        _paint(img, R['beret'], beret, keep=0.9, rng=rng)
        _paint(img, R['skin'], skin, keep=0.8, wool=0.0); _paint(img, R['hands'], skin, keep=0.8, wool=0.0)
        return img
    raise KeyError(kind)


# ===================================================================================================== the men
# (vnam, face, mesh, head shape, body sheet, kind): kind = squad role; weight = how often he appears. Hair lives in the head map.
ROSTER = [
    # regulars, bare headed: thin conscripts, strong men, a heavy sergeant
    ('ssm01_1', 'hamid', 'rsg_1', 'shaved', 'rsg_olive', 'man', 3, 'muscle'), ('ssm02_1', 'salim', 'rsg_1', 'thin', 'rsg_frog', 'man', 3, 'skinny'),
    ('ssm04_1', 'faris', 'rsg_1', 'shaved', 'rsg_lizard', 'man', 3, 'muscle'), ('ssm05_1', 'karim', 'rsg_1', 'heavy', 'rsg_frog', 'man', 2, 'fat'),
    # shirt and jeans
    ('ssm07_1', 'yusuf', 'rsg_1', 'shaved', 'rsg_jeans', 'man', 2, 'skinny'), ('ssm08_1', 'nasir', 'rsg_1', 'bigbeard', 'rsg_jeans2', 'man', 2, 'muscle'),
    ('ssm09_1', 'qasim', 'rsg_1', 'bigbeard', 'rsg_jeans', 'man', 2, 'fat'),
    # cap and tactical vest (owner 11-13: headgear must differ inside a group)
    ('ssm03_1', 'saddiq', 'resg_1', None, 'resg_olive', 'man', 2, None), ('ssm06_1', 'jabir', 'resg_1', None, 'resg_lizard', 'man', 2, 'skinny'),
    # helmets and vests, the balaclava: the strong, well equipped men
    ('ssm10_1', 'omar', 'les_1', None, 'les_olive', 'elite', 2, 'skinny'), ('ssm11_1', 'mahmud', 'les_1', None, 'les_black', 'elite', 2, 'muscle'),
    ('ssm12_1', 'salim', 'csf_1', None, 'csf_desert', 'elite', 2, 'muscle'),
    # technicians (cutscenes), the leather jacket
    ('ssm13_1', 'majid', 'resg_1', None, 'resg_tan', 'named', 1, None),   # (judge p16 11-14: Sergeant Hadi, our man in the intro, his own look: no live guard wears it)
    ('ssm14_1', 'hassan', 'rsg_1', 'shaved', 'rsg_tech', 'tech', 1, 'skinny'),
    ('ssm15_1', 'ali', 'rsg_1', 'thin', 'rsg_leather', 'officer', 1, None),
    # beret and officer's shirt
    ('ssm16_1', 'tariq', 'infgu_1', None, 'inf_officer', 'officer', 1, None), ('ssm17_1', 'khalil', 'infgu_1', None, 'inf_khaki', 'officer', 1, 'fat'),
    ('ssm18_1', 'adnan', 'infgu_1', None, 'inf_general', 'officer', 1, 'fat'),
    # (orchestrator 11-14, owner: "josef breboy most not be in iraq" - Kral the arms broker wore the Senator's pat_1: his own invented face, a cream suit, cutscenes only)
    ('ssm19_1', 'kral', 'rsg_1', 'thin', 'rsg_suit', 'civ', 1, None),
    # (S21 11-15: the ending's loco mate - Nasir as ssm08_1, same mesh, but that sheet is worn by live AK guards in both missions: his own, no sheath)
    ('ssm20_1', 'nasir', 'rsg_1', 'bigbeard', 'rsg_jeans2', 'crew', 1, 'muscle'),
]
NAMES = [r[0] for r in ROSTER]
# (S21 11-15, owner: 'the men who drive the train are holding guns ... they're hidden stuff': the loco crew are railwaymen, so no knife sheath. A body
#  sheet is shared by everyone who wears that man, so a sheet loses its sheath only in a level where none of its wearers is armed: ssm14_1 is
#  Sandstorm's loco driver (+ cutscene technicians, never a HumanSoldier there) but an AK regular in Sirocco (build_sirocco5 REGULARS)
# (PLAN decision 76, 11-17: crew continuity = the INSTALLED crew, ssm14_1 + ssm08_1 with the painted sheath, in Sandstorm and Sirocco alike. The sheath-free
#  crew (bd5c486, + the Sirocco copy 4947911) goes into no install: off by default, SS_CREW_PLAIN=1 brings it back. Off = the rc7s25 / ssb2 skins, no ssm20_1 row)
CREW_PLAIN = os.environ.get('SS_CREW_PLAIN', '0') == '1'
NO_SHEATH = {'sandstorm': ('ssm14_1', 'ssm20_1')} if CREW_PLAIN else {}   # level -> men whose body sheet there is the sheath-free 'ss_c_' copy
LEVEL_ONLY = {'ssm20_1': ('sandstorm',) if CREW_PLAIN else ()}            # rows registered in those levels only (no VNAM / LOD-table row elsewhere)
CREW = {'ssm08_1': 'ssm20_1'} if CREW_PLAIN else {}                       # assign(): the 'SS loco crew' actors' skin -> the sheath-free man (ssoutro._crew names ssm08_1)
REGISTERED = None                                                 # the names add_skins put in this build's bank
COLONEL, GENERAL = 'ssm16_1', 'ssm18_1'
CHARS = os.environ.get('SS_CHARS', '1') == '1'                   # (owner 58: fat, muscular, skinny bodies)
HEIGHT = {('rsg_1', 'thin', 'skinny'): 1.05, ('rsg_1', 'heavy', 'fat'): 0.95} if CHARS else {}   # (proven: feet stay on the ground, stills ch3, walking ch4)
HEAD_SIZE = int(os.environ.get('SS_HEADSIZE', '2048'))
HEADSRC = {'les_1': 'les_1', 'infgu_1': 'ch_infgu_1', 'rsg_1': 'ch_rsg_00', 'resg_1': 'ch_resg_00', 'csf_1': 'csf_1'}
LEADERS = ['ssm03_1', 'ssm05_1', 'ssm17_1', 'ssm15_1', 'ssm11_1']   # (owner 11-13: sergeants and officers look their own; the man in the middle of a group)
HEADGEAR = {'rsg_1': 'bare', 'resg_1': 'cap', 'les_1': 'helmet', 'csf_1': 'mask', 'infgu_1': 'beret'}


def tex_mode67(rgb):
    """RGB float -> .tex bytes: 32-bit + full mip chain (no 16-bit banding on skin, no shimmer at range), header as the shipped ones"""
    import struct
    a = np.ones(rgb.shape[:2] + (1,), np.float32)
    cur = np.dstack([np.clip(rgb.astype(np.float32), 0, 1), a])
    H, W = cur.shape[:2]
    hdr = bytearray(b'LOOP' + struct.pack('<I', 11) + struct.pack('<I', 67) + b'\0' * 20)
    struct.pack_into('<H', hdr, 20, 5)
    struct.pack_into('<HHHHH', hdr, 22, W, H, W, H, 4)
    out = [bytes(hdr)]
    while True:
        out.append(np.rint(cur[..., [2, 1, 0, 3]] * 255).astype(np.uint8).tobytes())
        if min(cur.shape[:2]) == 1:
            break
        cur = 0.25 * (cur[0::2, 0::2] + cur[1::2, 0::2] + cur[0::2, 1::2] + cur[1::2, 1::2])
    return b''.join(out)


def _head_rgb(face):
    from PIL import Image
    im = Image.open(os.path.join(HEADS, '%s.png' % face)).convert('RGB')
    return np.asarray(im.resize((HEAD_SIZE, HEAD_SIZE // 2), Image.LANCZOS), np.float32) / 255.0


def textures():
    """the finished banks, cached on disk by content (orchestrator 11-05: the bake took most of a 13 minute build under the build lock)"""
    import hashlib, pickle, glob
    h = hashlib.sha1(open(os.path.abspath(__file__), 'rb').read() + str(HEAD_SIZE).encode() + b'v2' + str(CHARS).encode() + str(HEIGHT).encode())
    for f in sorted(glob.glob(os.path.join(HEADS, '*.png'))):
        h.update(('%s %d %d' % (os.path.basename(f), os.path.getsize(f), os.stat(f).st_mtime_ns)).encode())
    p = os.path.join(ROOT, 'work', 'sandstorm', 'soldiers', 'cache', 'skins_%s.pkl' % h.hexdigest()[:16])
    if os.path.exists(p):
        return pickle.load(open(p, 'rb'))
    out = _textures()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    pickle.dump(out, open(p + '.tmp', 'wb'), protocol=4)
    os.replace(p + '.tmp', p)
    return out


def _skin(face):
    return tuple(float(x) for x in open(os.path.join(HEADS, '%s.skin.txt' % face)).read().split())


def _body_tex(bd, seed, face, sheath=True):
    from PIL import Image
    img = body(bd, seed, _skin(face), sheath=sheath)
    if img.shape[0] > 1024:
        img = np.dstack([np.asarray(Image.fromarray((np.clip(img[..., c], 0, 1) * 255).astype('u1')).resize((1024, 1024), Image.LANCZOS), np.float32) / 255.0 for c in range(4)])
    return wreck.tex_mode2(img)


def _textures():
    """-> {texture name: bytes}, {vnam: (mesh name in the bank, [texture names by slot])}, {mesh name: mef bytes}"""
    texs, skins, meshes, mesh_id, seeds = {}, {}, {}, {}, {}
    for vn, face, mesh, shape, bd, kind, wt, build in ROSTER:
        bn = 'ss_b_%s_%s' % (bd[:8], face)                        # (a body sheet per man: his hands and arms have his skin)
        if bn not in texs:
            seeds[bn] = 8100 + len(texs)
            texs[bn] = _body_tex(bd, seeds[bn], face)
        hn = 'ss_h_%s_%s' % (face, mesh[:3])
        if hn not in texs:
            rgb = _head_rgb(face)
            if mesh == 'csf_1':
                rgb = shipped('csf_1')[..., :3].copy()
                _mask_paint(rgb, _masks(rgb)[2], _skin(face), keep=0.8)
            elif mesh != 'rsg_1':
                rgb = bake(rgb, shipped(HEADSRC[mesh]), mesh, max_cm=6.0)
            texs[hn] = tex_mode67(rgb)
        k = (mesh, shape, build)
        if k not in mesh_id:
            mesh_id[k] = 'ssm%02d' % len(mesh_id)
            data = _model_bytes(mesh)
            if build and CHARS:
                data = build_mesh(data, build)
            if shape:
                data = morph(mefmesh.Mef.read(data), shape)
            if CHARS and HEIGHT.get(k):
                data = scale_mesh(data, HEIGHT[k])
            meshes[mesh_id[k]] = data
        skins[vn] = (mesh_id[k], [bn, hn] + list(_slot_names(mesh)[2:]))
    for vn in sorted({v for vs in NO_SHEATH.values() for v in vs} & set(skins)):   # (after the loop: no other man's seed moves; same seed = same sheet bar the sheath)
        r = next(r for r in ROSTER if r[0] == vn)
        bn = skins[vn][1][0]
        if 'ss_c_' + bn[5:] not in texs:
            texs['ss_c_' + bn[5:]] = _body_tex(r[4], seeds[bn], r[1], sheath=False)
    return texs, skins, meshes


SLOTS = {}


def _slot_names(mesh):
    import glob
    if mesh in SLOTS:
        return SLOTS[mesh]
    common = mtp.read(os.path.join(GAME, 'COMMON', 'common.mtp'))
    for p in glob.glob(os.path.join(GAME, 'MISSIONS', 'location*', '**', '*.mtp'), recursive=True):
        try:
            m = mtp.read(p)
        except Exception:
            continue
        for vn, (mef, tx) in mtp.resolve(m, common).items():
            if mef == mesh:
                SLOTS[mesh] = tx
                return tx
    raise KeyError(mesh)


def add_skins(overlay_dir, level_name, log=print):
    """the same bank work as alskins.add_skins, for many meshes; every slot LOCAL"""
    global REGISTERED
    paths = wreck._ensure_overlay(overlay_dir, level_name)
    m = mtp.read(paths['mtp'])
    texs, skins, meshes = textures()
    plain = set(NO_SHEATH.get(level_name, ()))
    skins = {vn: (mn, ['ss_c_' + tx[0][5:]] + tx[1:] if vn in plain else tx) for vn, (mn, tx) in skins.items() if level_name in LEVEL_ONLY.get(vn, (level_name,))}
    want = {t for mn, tx in skins.values() for t in tx}
    texs = {nm: data for nm, data in texs.items() if nm in want}  # (only the sheets this level's men wear: Sandstorm's ssm14_1 sheet with the sheath stays out)
    mform, mch, mhdr = ilff.read(open(paths['models'], 'rb').read())
    have_m = {d.rstrip(b'\0').decode('latin1') for t, d, a in mch if t == b'NAME'}
    for mn, data in meshes.items():
        key = 'LOCAL:models/%s.mef' % mn
        if key not in have_m:
            mch.append((b'NAME', key.encode('latin1') + b'\0', 4)); mch.append((b'BODY', data, 4))
        if mn not in m['MODS']:
            m['MODS'].append(mn)
    form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
    have_t = {d.rstrip(b'\0').decode('latin1') for t, d, a in ch if t == b'NAME'}
    for nm, data in texs.items():
        ch.append((b'NAME', ('LOCAL:textures/%s.tex' % nm).encode('latin1') + b'\0', 4)); ch.append((b'BODY', data, 4)); have_t.add('LOCAL:textures/%s.tex' % nm)
    gtt = {}

    def slot(t):
        k = 'LOCAL:textures/%s.tex' % t
        if k not in have_t:                                       # (the glasses of infgu_1: the original texture, copied LOCAL)
            ch.append((b'NAME', k.encode('latin1') + b'\0', 4)); ch.append((b'BODY', _shipped_bytes(t), 4)); have_t.add(k)
        if t not in m['TEXF']:
            m['TEXF'].append(t)
        ti = m['TEXF'].index(t)
        for i, (t_, pl) in enumerate(m['GTT']):
            if t_ == ti and pl == -1:
                return i
        m['GTT'].append([ti, -1])
        return len(m['GTT']) - 1
    for vn, (mn, tx) in skins.items():
        g_ = [slot(t) for t in tx]
        assert all(x < mtp.COMMON_BIT for x in g_), (vn, g_)
        m['VNAM'].append(vn); m['INST'].append([m['MODS'].index(mn), g_])
    for path, blob in ((paths['textures'], ilff.write(form, ch, hdr[1] or 4)), (paths['models'], ilff.write(mform, mch, mhdr[1] or 4)),
                       (paths['mtp'], mtp.write(m))):
        tmp = path + '.ss.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    lab_face(paths['textures'], log)
    b2 = wreck.Bank(paths['mtp'], paths['models'], paths['textures'])
    names = [n for n in NAMES if n in skins]
    probs = [n for n in names if b2.res.get(n) is None]
    log('sssoldiers: %d men, %d textures (%.1f MB), %d meshes, problems %s; no sheath: %s' % (len(skins), len(texs), sum(map(len, texs.values())) / 1e6, len(meshes),
                                                                                            probs or 'none', sorted(plain & set(skins)) or 'none'))
    assert not probs, probs
    REGISTERED = names
    return list(names)


LAB_FACE = 'hassan'                                                # (judge p16 11-14: the scientists' eyes are an invented Iraqi man's, not the shipped lab head's)


def lab_face(tex_res, log=print):
    """bubsci_2 = the bubsci_1 scientists' head: a frontal face, eyes at (0.28, 0.29) and (0.71, 0.29), a white surgical mask from y 0.42 down.
    The eye band of LAB_FACE's head panorama (eyes at (0.44, 0.42) and (0.56, 0.42)) is scaled onto it, feathered, the mask and hood kept."""
    from PIL import Image
    form, ch, hdr = ilff.read(open(tex_res, 'rb').read())
    key = b'LOCAL:textures/bubsci_2.tex'
    k = next((i for i, (t_, d, a) in enumerate(ch) if t_ == b'NAME' and d.rstrip(b'\0').lower() == key.lower()), None)
    if k is None or ch[k + 1][0] != b'BODY':
        log('sssoldiers: bubsci_2 not in this overlay, lab face left'); return
    im = lab_paste(np.array(igitex.decode(ch[k + 1][1]), np.float32))
    ch[k + 1] = (b'BODY', wreck.tex_mode2(np.clip(im, 0, 1)), ch[k + 1][2])
    tmp = tex_res + '.lab.tmp'
    open(tmp, 'wb').write(ilff.write(form, ch, hdr[1] or 4))
    os.replace(tmp, tex_res)
    log('sssoldiers: scientists\' eyes = %s (bubsci_2 re-textured)' % LAB_FACE)


def lab_paste(im):
    from PIL import Image
    H, W = im.shape[:2]
    src = np.asarray(Image.open(os.path.join(HEADS, LAB_FACE + '.png')).convert('RGB'), np.float32) / 255.0
    sh, sw = src.shape[:2]
    e0, e1 = np.array((0.28 * W, 0.29 * H)), np.array((0.71 * W, 0.29 * H))          # eye centres, target
    s0, s1 = np.array((0.4395 * sw, 0.418 * sh)), np.array((0.5615 * sw, 0.416 * sh))  # eye centres, panorama
    sc = np.linalg.norm(s1 - s0) / np.linalg.norm(e1 - e0)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    mid_e, mid_s = (e0 + e1) / 2, (s0 + s1) / 2
    u = np.clip(mid_s[0] + (xx - mid_e[0]) * sc, 0, sw - 1).astype(int)
    v = np.clip(mid_s[1] + (yy - mid_e[1]) * sc, 0, sh - 1).astype(int)
    face = src[v, u]
    rgb = im[..., :3]
    lum = rgb.mean(2); sat = rgb.max(2) - rgb.min(2)
    maskcloth = (lum > 0.62) & (sat < 0.10) & (yy > (0.40 + 0.10 * (1 - np.abs(xx / W - 0.5) * 2)) * H)   # (the mask's top edge: y 0.40 at the sides, 0.50 under the nose)                       # the surgical mask stays white
    r = np.sqrt(((xx - mid_e[0]) / (0.47 * W)) ** 2 + ((yy - mid_e[1]) / (0.30 * H)) ** 2)
    a = np.clip((1.0 - r) / 0.25, 0, 1) * (~maskcloth) * (yy < 0.56 * H)
    from scipy.ndimage import gaussian_filter
    a = gaussian_filter(a.astype(np.float32), 6)
    edge = (r > 0.85) & (r < 1.0) & ~maskcloth                    # match the shipped skin round the edge to the pasted face
    if edge.any():
        face = face * (rgb[edge].mean(0) / np.maximum(1e-3, face[edge].mean(0)))[None, None, :] * 0.5 + face * 0.5
    im[..., :3] = rgb * (1 - a[..., None]) + np.clip(face, 0, 1) * a[..., None]
    return im


def _shipped_bytes(name):
    _find('textures', [name])
    return _FOUND['textures', name]


def lod_rows():
    return {n: [1344.0, 1358.0, 1372.0, 1386.0, 1400.0] for n in (NAMES if REGISTERED is None else REGISTERED)}


# old skin (what the builder and the cutscene code name) -> role of the man who replaces it
ROLE_OF = {'alarm1_1': 'man', 'alarm2_1': 'man', 'alsea2_1': 'man', 'alalpc_1': 'tech', 'alplas_1': 'elite', 'alarmo_1': 'officer', 'alseao_1': 'officer'}
NAMED = {'Colonel': COLONEL, 'General': GENERAL}


def assign(m, K=None, log=print):
    """last pass over the mission: every HumanSoldier and cutscene EditBoneObj that still wears an old skin gets a man of the right role.
    Nearest neighbours rarely match (greedy by id order, penalty falling with distance); a cutscene actor takes the man of the live
    soldier standing nearest him when that is within 12 m (owner item 22: same people in cutscene and play)."""
    from mission_lib import lit
    men = {r[0]: r for r in ROSTER}
    sol = [i for i in sorted(m.find('HumanSoldier')) if lit(m.byid[i].args[7]) in ROLE_OF]
    placed = []
    used = dict.fromkeys(NAMES, 0)
    live = [vn for vn, r in men.items() if vn not in NAMED.values() and r[5] not in ('tech', 'civ', 'named', 'crew')]     # (the colonel and general are one man each; technicians stay in cutscenes)
    pos = {i: np.array([lit(m.byid[i].args[k]) for k in (3, 4, 5)], float) / 4096.0 for i in sol}
    lab = {i: i for i in sol}

    def root(x):
        while lab[x] != x:
            lab[x] = lab[lab[x]]; x = lab[x]
        return x
    for x in sol:
        for y in sol:
            if x < y and np.linalg.norm(pos[x] - pos[y]) < 12.0:
                lab[root(x)] = root(y)
    groups = {}
    for x in sol:
        groups.setdefault(root(x), []).append(x)
    pl = [i for i in m.find('HumanPlayer')]
    start = np.array([lit(m.byid[pl[0]].args[k]) for k in (3, 4, 5)], float) / 4096.0 if pl else np.zeros(3)
    order = sorted(groups.values(), key=lambda g: float(np.linalg.norm(np.mean([pos[x] for x in g], 0) - start)))

    def score(vn, p, grp):
        r = men[vn]
        s = used[vn] / float(r[6])
        for q, ow, og in placed:
            d = float(np.linalg.norm(p - q))
            if d < 45.0:
                o = men[ow]
                w = 12.0 / (d + 4.0)
                s += w * (30.0 * (ow == vn) + 8.0 * (o[1] == r[1]) + 2.0 * (o[4] == r[4]))
                if og == grp:
                    s += 3.0 * (HEADGEAR[o[2]] == HEADGEAR[r[2]]) + 1.5 * ((o[7] or 'std') == (r[7] or 'std'))
        return s
    for gi, g in enumerate(order):
        c = np.mean([pos[x] for x in g], 0)
        g = sorted(g, key=lambda x: float(np.linalg.norm(pos[x] - c)))
        for k, i in enumerate(g):
            role = ROLE_OF[lit(m.byid[i].args[7])]
            if len(g) >= 3 and k == 0:
                cand = LEADERS
            elif role == 'elite':
                cand = [vn for vn in live if HEADGEAR[men[vn][2]] in ('helmet', 'mask', 'cap')]
            else:
                cand = [vn for vn in live if vn not in LEADERS or len(g) < 3]
            best = min(cand, key=lambda vn: score(vn, pos[i], gi))
            m.set(i, 7, best)
            used[best] += 1
            placed.append((pos[i], best, gi))
    placed = [(q, v) for q, v, _ in placed]
    act = 0
    for i in sorted(m.find('EditBoneObj')):
        a = m.byid[i].args
        if lit(a[11]) not in ROLE_OF:
            continue
        nm = str(lit(a[2]))
        named = [v for k, v in NAMED.items() if k in nm]
        p = np.array([lit(a[3]), lit(a[4]), lit(a[5])], float) / 4096.0
        role = ROLE_OF[lit(a[11])]
        if named:
            m.set(i, 11, named[0])
        else:
            near = sorted(((float(np.linalg.norm(p - q)), v) for q, v in placed if men[v][5] == role or role == 'man'))
            ok = near[0][1] if near and near[0][0] < 12.0 else min((v for v, r in men.items() if r[5] == role), key=lambda v: used[v])
            m.set(i, 11, ok)
        act += 1
    crew = 0
    for i in sorted(m.find('EditBoneObj')):                       # (S21: the loco crew wear the sheath-free men; ssoutro._crew names the live guard ssm08_1)
        a = m.byid[i].args
        if 'loco crew' in str(lit(a[2])) and CREW.get(lit(a[11])) in (NAMES if REGISTERED is None else REGISTERED):
            m.set(i, 11, CREW[lit(a[11])])
            crew += 1
    plain = set(NO_SHEATH.get('sandstorm', ()))                   # (assign() is Sandstorm's pass: nobody armed may wear a sheath-free man)
    armed = [i for i in m.find('HumanSoldier') if lit(m.byid[i].args[7]) in plain] + \
            [i for i in m.find('EditBoneObj') if len(m.byid[i].args) > 13 and lit(m.byid[i].args[11]) in plain and str(lit(m.byid[i].args[13])).lower() not in ('', 'none')]
    if armed:
        log('sssoldiers.assign: WARN S21 - armed men wear a sheath-free body (no knife sheath on an armed man): tasks %s' % armed[:12])
    if os.environ.get('SS_LINEUP'):                               # (test build: every man stands in an arc 3.5 m round this floor point, facing it)
        import atmos
        from mission_lib import T
        atmos.ensure_decl(m, 'EditBoneObj')
        c = [float(x) * 4096.0 for x in os.environ['SS_LINEUP'].split(',')]
        men_ = [x for x in os.environ.get('SS_LINEUP_MEN', '').split(',') if x] or NAMES
        row = [(vn, tn) for vn in men_ for tn in (0.0, 1.5708, 3.14159)]       # every man three times: front, side, back
        for k, (vn, tn) in enumerate(row):
            a_ = (k / float(len(row))) * 2 * math.pi
            r_ = float(os.environ.get('SS_LINEUP_R', '3.5')) * 4096
            p = (c[0] + r_ * math.cos(a_), c[1] + r_ * math.sin(a_), c[2])
            g = math.atan2(-(c[0] - p[0]), c[1] - p[1]) + tn
            i = K.nid()
            m.add_child(K.static_root(), T(i, 'EditBoneObj', 'SS lineup %s' % vn, p[0], p[1], p[2], 0.0, 0.0, g, True, True, vn, True, '107_01_1', '', 'stand_look_about', 1.0, 0.0))
    log('sssoldiers.assign: %d soldiers, %d cutscene actors, %d loco crew re-dressed; men used %s' % (len(sol), act, crew, sorted(used.items())))
    return used
