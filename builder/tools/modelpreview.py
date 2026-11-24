"""modelpreview - offline pictures of IGI 2 models with their real textures (planning aid, no game needed).

    python -P tools/modelpreview.py <out.png> <location/level>:<model>[,<model>...] [...]
    e.g. python -P tools/modelpreview.py work/blackice/prefabs.png location1/level1:434_26_1,400_06_1 location1/LEVEL5:305_03_1

Each model is drawn from a 3/4 view (mesh + ATTA attachments one level deep) with tools/mefrender; the pictures are
tiled into one contact sheet with labels. Model frames: z up.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import igitex, mefmesh, mefrender, mef as meflib
import prefab

GAME = prefab.GAME


def _tex(lv, name):
    L, body = lv.find_resource('LOCAL:textures/%s.tex' % name, 'textures')
    if body is None:
        return None
    try:
        return igitex.decode(body)
    except Exception:
        return None


def add_model(sc, lv, vn, pos=(0, 0, 0), R=None, depth=0):
    L = lv.find_vnam(vn)
    if L is None:
        return None
    mefn, texs = L.entry(vn)
    body = lv.find_resource('LOCAL:models/%s.mef' % mefn, 'models')[1]
    m = mefmesh.Mef.read(body)
    R = np.eye(3) if R is None else R
    pos = np.asarray(pos, float)
    try:
        r = mefmesh.RigidModel.from_mef(m)
    except Exception:
        return m
    mats = {}
    for g in r.groups:
        if g.tex not in mats:
            tex = _tex(lv, texs[g.tex]) if g.tex < len(texs) else None
            alpha = 1.0
            mats[g.tex] = sc.material(tex, color=(0.6, 0.6, 0.6), alpha=alpha, tex_alpha=bool(g.flags & 0x04))
        P = g.pos @ R.T + pos
        if g.nrm is not None:
            N = g.nrm
        else:                                              # lightmapped models carry no normals: area-weighted vertex normals
            tri = g.pos[g.tris]
            fn = -np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])   # (front face = clockwise seen from outside)
            N = np.zeros_like(g.pos)
            for k in range(3):
                np.add.at(N, g.tris[:, k], fn)
            N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        N = N @ R.T
        sc.add_tris(P[g.tris], N[g.tris], g.uv[g.tris], mats[g.tex], double=bool(g.flags & 0x04))
    if depth < 1:
        for a, apos, arot in meflib.attachments(body):
            if lv.find_vnam(a):
                add_model(sc, lv, a, pos + R @ np.asarray(apos, float), R @ np.asarray(arot, float).reshape(3, 3), depth + 1)
    return m


def preview(lv, vn, size=(640, 400), bearing_deg=35.0, elev_deg=22.0):
    sc = mefrender.Scene()
    m = add_model(sc, lv, vn)
    if m is None:
        return None
    P = np.concatenate([t.reshape(-1, 3) for t in sc.P]) if sc.P else np.zeros((1, 3))
    lo, hi = P.min(0), P.max(0)
    c = (lo + hi) / 2
    rad = float(np.linalg.norm(hi - lo) / 2) + 1.0
    sc.add_ground(z=float(lo[2]), half=rad * 3, color=(0.80, 0.82, 0.86))
    b, e = math.radians(bearing_deg), math.radians(elev_deg)
    d = rad / math.tan(math.radians(20)) * 1.05
    eye = c + np.array([math.sin(b) * math.cos(e), -math.cos(b) * math.cos(e), math.sin(e)]) * d
    return sc.render(eye, c, size=size, fov=40, ss=1)


def sheet(out_path, specs, size=(640, 400)):
    from PIL import Image, ImageDraw
    tiles = []
    for rel, names in specs:
        lv = prefab.Level(os.path.join(GAME, 'MISSIONS', *rel.split('/')))
        for vn in names:
            try:
                im = preview(lv, vn, size=size)
            except Exception as ex:
                im = None
                print('%s %s: %s' % (rel, vn, ex))
            if im is None:
                im = Image.new('RGB', size, (40, 0, 0))
            tiles.append(('%s  %s' % (vn, rel), im))
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    W, H = size
    sh = Image.new('RGB', (cols * W, rows * (H + 18)), 'black')
    dr = ImageDraw.Draw(sh)
    for i, (label, im) in enumerate(tiles):
        x, y = (i % cols) * W, (i // cols) * (H + 18)
        sh.paste(im.convert('RGB'), (x, y + 18)); dr.text((x + 4, y + 3), label, fill='yellow')
    sh.save(out_path)
    return out_path


if __name__ == '__main__':
    out = sys.argv[1]
    specs = []
    for a in sys.argv[2:]:
        rel, names = a.split(':')
        specs.append((rel, names.split(',')))
    print(sheet(out, specs))
