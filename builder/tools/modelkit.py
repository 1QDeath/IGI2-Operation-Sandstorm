"""modelkit - register NEW vertex-lit models (built with tools/mefmesh) in a mission overlay: the biprefabs.add_models
recipe made generic, so every new-model module (boat.py, cablecar.py, harbor props ...) shares one proven path.

    import modelkit
    lib = modelkit.Library()                       # one per mission build
    lib.add('hb_boat_1', build_fn, ['hb_hull', 'hb_deck'], lod_like='740_01_1', cutoff_m=900)
    lib.texture('hb_hull', lambda: rgba_array)    # (H, W, 4) float 0..1, power-of-2 sides
    lib.install(overlay_dir, 'forestraid')         # after K.write()/X.finish(): models + textures + LOD lines
    lib.names                                      # model names (for lodfix extra / validate)

Model frames: z up, 1 m = 4096 units. Front faces clockwise seen from outside (biprefabs helpers handle it).
Everything here is the biprefabs code path that is verified in game (Black Ice, 10-14); only the tables are parameters.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, mefmesh, wreck
import biprefabs as BP
import searchlight as SL

M = 4096.0


def hull_m(points_m, uv=1.0):
    """convex solid through the given points (metres), flat-shaded, front faces outward -> part (P, T, N, U) in units.
    For shapes the box/cylinder helpers cannot make: a boat bow, a wedge, a tapered cabin."""
    from scipy.spatial import ConvexHull
    Q = np.asarray(points_m, float)
    h = ConvexHull(Q)
    c = Q.mean(0)
    P, T, N, U = [], [], [], []
    for simp, eq in zip(h.simplices, h.equations):
        n = eq[:3]
        a, b, d = Q[simp]
        if np.linalg.norm(np.cross(b - a, d - a)) < 1e-9:
            continue
        k = len(P)
        ax = int(np.argmax(np.abs(n)))
        ua, va = [i for i in range(3) if i != ax]
        for p in (a, b, d):
            P.append(p * M); N.append(n); U.append((p[ua] * uv, p[va] * uv))
        T.append((k, k + 1, k + 2))
    P, T, N, U = np.array(P), np.array(T), np.array(N), np.array(U, float)
    T = SL._orient(P, T, N, N[T[:, 0]])
    return P, T, N, U


GLASS = 0x7f1906          # group flags of an alpha-blended group (searchlight beam: 0x04 blend + the shipped lamp-glass bits);
                          # 10-16 in game: a mode-67 alpha texture in a plain 0x1900 group renders OPAQUE (pale green 'glass')


def panel(center_m, right, up, w_m, h_m, uv=(0.0, 0.0, 1.0, 1.0)):
    """a one-sided quad showing ONE copy of a texture (signs, labels, name boards): centre (m), `right` / `up` unit vectors
    as the viewer sees them (the face looks along right x up, toward the viewer), size w x h m; uv = (u0, v0, u1, v1) of
    the image (v 0 = the image's top row) -> part"""
    c = np.asarray(center_m, float); r = np.asarray(right, float); u = np.asarray(up, float)
    r /= np.linalg.norm(r); u /= np.linalg.norm(u)
    n = np.cross(r, u)
    P = np.array([c - r * w_m / 2 - u * h_m / 2, c + r * w_m / 2 - u * h_m / 2, c + r * w_m / 2 + u * h_m / 2, c - r * w_m / 2 + u * h_m / 2]) * M
    u0, v0, u1, v1 = uv
    U = np.array([(u0, v1), (u1, v1), (u1, v0), (u0, v0)], float)
    T_ = np.array([(0, 1, 2), (0, 2, 3)])
    N = np.tile(n, (4, 1))
    T_ = SL._orient(P, T_, N, np.tile(n, (2, 1)))
    return P, T_, N, U


def model(groups_parts, coll_parts, glows=None, atta=None, alpha_slots=()):
    """groups_parts = [(texture slot, [parts])], coll_parts = [parts] (parts from biprefabs.box_m / cyl_z / ...) -> mef.
    alpha_slots = texture slots whose groups are alpha-blended (GLASS flags)"""
    if not alpha_slots:
        return BP._model(groups_parts, coll_parts, BP._hsem(), glows=glows, atta=atta)
    groups = []
    for slot, parts in groups_parts:
        P, T_, N, U = BP.merge(parts)
        groups.append(mefmesh.Group(P, U, T_, slot, flags=GLASS if slot in alpha_slots else 0x1900, nrm=N))
    cP, cT, _, _ = BP.merge(coll_parts)
    r = mefmesh.RigidModel(groups, SL._coll(cP, cT), hsem=BP._hsem(), glows=glows, atta=atta, typ=0)
    return r.to_mef(recompute_spheres=True, recompute_centres=True, rebuild_trees=True)


# per-model collision material override (S14, 11-15): VNAM -> TAMC surface written over every material-6 row of collision mesh 0
# (the face list bullets and AI sight test). 6 = NormalMetal, penetration 4: an AK/Minimi round (power 12) passes one wall of it.
# 12 = Runway, penetration 20: what the originals use for thick concrete; stops every weapon, the M2HB (18) included.
# A mission fills it before Library.build (Sandstorm: tools/ssbase.py BULLET_STOP). Empty = no change for any other mission.
SURFACE = {}


def set_surface(mf, surface, only=(6,)):
    """mef with every collision-mesh-0 material row whose surface is in `only` set to `surface` (render, spheres, trees unchanged)"""
    r = mefmesh.RigidModel.from_mef(mf)
    if not r.coll:
        return mf, 0
    mats = r.coll[0].mats.copy()
    hit = np.isin(mats['surface'], np.array(only, mats['surface'].dtype))
    if not hit.any():
        return mf, 0
    mats['surface'][hit] = surface
    r.coll[0].mats = mats
    return r.to_mef(recompute_spheres=False, recompute_centres=False, rebuild_trees=False), int(hit.sum())


class Library:
    def __init__(self):
        self.builders, self.slots, self.lod, self.textures, self.alpha = {}, {}, {}, {}, set()
        self.names = []

    def texture(self, name, fn, alpha=False):
        self.textures[name] = fn
        if alpha:
            self.alpha.add(name)

    def add(self, name, build_fn, slots, lod_like='740_01_1'):
        assert name.endswith('_1') and len(name) <= 15, name
        self.builders[name], self.slots[name], self.lod[name] = build_fn, list(slots), lod_like
        self.names.append(name)

    def build(self, names=None):
        out = {}
        for nm in (names or self.names):
            mf = self.builders[nm]()
            if nm in SURFACE:
                mf, _n = set_surface(mf, SURFACE[nm])
            probs = list(mefmesh.semantic_check(mf))
            if probs:
                raise ValueError('%s failed its checks: %s' % (nm, probs[:5]))
            out[nm] = mf
        return out

    def install(self, overlay_dir, level_name, log=print):
        """register every model (+ textures, lod lines) in the overlay's manifest and banks (biprefabs.add_models)"""
        game_root = os.path.normcase(os.path.realpath(wreck.GAME))
        try:
            inside = os.path.commonpath([game_root, os.path.normcase(os.path.realpath(overlay_dir))]) == game_root
        except ValueError:
            inside = False
        if inside:
            raise ValueError('refusing to write into the game folder: %s' % overlay_dir)
        paths = wreck._ensure_overlay(overlay_dir, level_name)
        m = mtp.read(paths['mtp'])
        names = list(self.names)
        clash = [n for n in names if n in m['VNAM']]
        if clash:
            raise ValueError('models already in %s: %s' % (paths['mtp'], clash))
        meshes = self.build(names)
        need_tex = sorted({t for n in names for t in self.slots[n]})
        form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
        have = {d.rstrip(b'\0').decode('latin1') for t, d, a in ch if t == b'NAME'}
        gtt = {}
        for tname in need_tex:
            if tname in m['TEXF']:
                gtt[tname] = next(i for i, (t_, pl) in enumerate(m['GTT']) if t_ == m['TEXF'].index(tname))
                continue
            img = self.textures[tname]()
            h_, w_ = img.shape[:2]
            if h_ & (h_ - 1) or w_ & (w_ - 1):
                raise ValueError('texture %s is %dx%d - not a power of 2' % (tname, w_, h_))
            tb = wreck.tex_mode67(img) if tname in self.alpha else wreck.tex_mode2(img)
            if ('LOCAL:textures/%s.tex' % tname) not in have:
                ch.append((b'NAME', ('LOCAL:textures/%s.tex' % tname).encode('latin1') + b'\0', 4))
                ch.append((b'BODY', tb, 4))
            m['TEXF'].append(tname)
            m['GTT'].append([len(m['TEXF']) - 1, -1])
            gtt[tname] = len(m['GTT']) - 1
        mform, mch, mhdr = ilff.read(open(paths['models'], 'rb').read())
        for nm in names:
            mch.append((b'NAME', ('LOCAL:models/%s.mef' % nm).encode('latin1') + b'\0', 4))
            mch.append((b'BODY', meshes[nm].write(), 4))
            m['MODS'].append(nm)
            m['VNAM'].append(nm)
            m['INST'].append([len(m['MODS']) - 1, [gtt[t] for t in self.slots[nm]]])
        blobs = ((paths['textures'], ilff.write(form, ch, hdr[1] or 4)), (paths['models'], ilff.write(mform, mch, mhdr[1] or 4)),
                 (paths['mtp'], mtp.write(m)))
        for path, blob in blobs:
            tmp = path + '.mk.tmp'
            open(tmp, 'wb').write(blob)
            os.replace(tmp, path)
        for nm in names:
            wreck._lod_entry(overlay_dir, self.lod[nm], nm, level_name)
        b2 = wreck.Bank(paths['mtp'], paths['models'], paths['textures'])
        probs = ['%s not in the model bank' % nm for nm in names if b2.models.get(nm) is None]
        probs += ['%s does not resolve' % nm for nm in names if b2.res.get(nm) is None]
        if set(x.lower() for x in b2.m['MODS']) - set(b2.models):
            probs.append('MODS entries without a mesh')
        if set(b2.m['TEXF']) - set(b2.tex):
            probs.append('TEXF entries without a texture')
        log('modelkit: %d models (%s), %d textures, problems %s' % (
            len(names), ', '.join('%s %d tris' % (n, int(meshes[n].hsem['n_rfaces'])) for n in names), len(need_tex), probs or 'none'))
        assert not probs, probs
        return dict(models=names, textures=need_tex)

    def preview(self, out_png, names=None, eye=(35, 22)):
        """offline contact sheet of the models (tools/mefrender)"""
        import math, mefrender
        from PIL import Image, ImageDraw
        meshes = self.build(names)
        tiles = []
        for nm, mf in meshes.items():
            r = mefmesh.RigidModel.from_mef(mf)
            sc = mefrender.Scene()
            mats = {}
            for g in r.groups:
                tname = self.slots[nm][g.tex] if g.tex < len(self.slots[nm]) else None
                if g.tex not in mats:
                    img = self.textures[tname]() if tname else None
                    mats[g.tex] = sc.material(img, color=(0.6, 0.6, 0.6), alpha=(0.6 if tname in self.alpha else 1.0))
                sc.add_tris(g.pos[g.tris], g.nrm[g.tris], g.uv[g.tris], mats[g.tex], double=True)
            P = np.concatenate([t.reshape(-1, 3) for t in sc.P])
            lo, hi = P.min(0), P.max(0); c = (lo + hi) / 2; rad = float(np.linalg.norm(hi - lo) / 2) + 1.0
            sc.add_ground(z=float(lo[2]), half=rad * 3, color=(0.80, 0.82, 0.86))
            b, e = math.radians(eye[0]), math.radians(eye[1])
            d = rad / math.tan(math.radians(20)) * 1.05
            ey = c + np.array([math.sin(b) * math.cos(e), -math.cos(b) * math.cos(e), math.sin(e)]) * d
            tiles.append((nm, sc.render(ey, c, size=(480, 320), fov=40, ss=1)))
        cols, W, H = 3, 480, 320
        rows = (len(tiles) + cols - 1) // cols
        sh = Image.new('RGB', (cols * W, rows * (H + 18)), 'black')
        dr = ImageDraw.Draw(sh)
        for i, (label, im) in enumerate(tiles):
            x, y = (i % cols) * W, (i // cols) * (H + 18)
            sh.paste(im.convert('RGB'), (x, y + 18)); dr.text((x + 4, y + 3), label, fill='yellow')
        sh.save(out_png)
        return out_png
