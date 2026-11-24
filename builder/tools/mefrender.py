"""mefrender - offline software renderer for IGI 2 models (previews; no game, no GPU).

Textured, Gouraud-lit (per-vertex normals), z-buffered, perspective-correct, sun shadow map, 2x supersampled,
back faces culled like the engine (front face = CLOCKWISE seen from outside in the z-up model frame: the stored
vertex normals point along -cross(b-a, c-a) for all 6479 Hind triangles), optional alpha-blended glass.

    import mefrender as R
    sc = R.Scene()
    sc.add_mef(mef, [tex_rgba_slot0, tex_rgba_slot1, ...], rot=np.eye(3), pos=(0, 0, 0))
    sc.add_ground(z=0, half=60000, color=(0.78, 0.68, 0.5))
    img = sc.render(eye=(x, y, z), target=(x, y, z), size=(1280, 800), fov=40)   # PIL image
"""
import math
import numpy as np


def _norm(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-12)


class Scene:
    def __init__(self):
        self.P = []      # (T,3,3) world positions
        self.N = []      # (T,3,3) normals
        self.UV = []     # (T,3,2)
        self.M = []      # (T,) material id
        self.D = []      # (T,) double sided
        self.G = []      # (T,) ground (receives shadows, casts none, not in the shadow-map extent)
        self.mats = []   # dict(tex=RGBA or None, color=rgb, alpha=float, tint=rgb, emissive=float)
        self.labels = []

    def material(self, tex=None, color=(0.7, 0.7, 0.7), alpha=1.0, tint=(1, 1, 1), emissive=0.0, flat=False, tex_alpha=False):
        """tex_alpha: per-pixel alpha from the texture (alpha-blended pass, like DNER flag 0x04 groups)"""
        self.mats.append(dict(tex=None if tex is None else np.asarray(tex, np.float32), color=np.array(color, float),
                              alpha=0.99 if tex_alpha and alpha >= 0.99 else alpha, tint=np.array(tint, float),
                              emissive=emissive, flat=flat, tex_alpha=tex_alpha))
        return len(self.mats) - 1

    def add_tris(self, P, N, UV, mat, double=False, ground=False):
        P = np.asarray(P, float).reshape(-1, 3, 3)
        if not len(P):
            return
        if N is None:
            g = -np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
            g /= np.linalg.norm(g, axis=1, keepdims=True).clip(1e-12)
            N = np.repeat(g[:, None], 3, 1)
        if UV is None:
            UV = np.zeros((len(P), 3, 2))
        self.P.append(P); self.N.append(np.asarray(N, float).reshape(-1, 3, 3)); self.UV.append(np.asarray(UV, float).reshape(-1, 3, 2))
        self.M.append(np.full(len(P), mat, int)); self.D.append(np.full(len(P), bool(double)))
        self.G.append(np.full(len(P), bool(ground)))

    def add_mef(self, m, textures, rot=np.eye(3), pos=(0, 0, 0), group_mats=None, colors=None, double=False,
                skip_groups=(), glass_slots=()):
        """render groups of a Mef (type 0: stored normals; type 3: geometric normals). textures[slot] = RGBA array.
        group_mats: optional {group index: material id} override (part colouring)."""
        rot = np.asarray(rot, float); pos = np.asarray(pos, float)
        X = m.get('XTRV'); I = m.get('ECAF')['v'].astype(int).reshape(-1); D = m.get('DNER')
        P = X['pos'].astype(float) @ rot.T + pos
        has_n = 'nrm' in X.dtype.names
        Nv = X['nrm'].astype(float) @ rot.T if has_n else None
        cache = {}
        for gi, g in enumerate(D):
            if gi in skip_groups:
                continue
            tri = I[int(g['i0']):int(g['i0']) + 3 * int(g['ntris'])].reshape(-1, 3)
            if not len(tri):
                continue
            slot = int(g['tex'])
            if group_mats and gi in group_mats:
                mid = group_mats[gi]
            else:
                key = slot
                if key not in cache:
                    tex = textures[slot] if textures and slot < len(textures) and slot != 0xFFFF else None
                    glass = slot in glass_slots
                    cache[key] = self.material(tex, color=(0.05, 0.05, 0.05) if tex is None else (1, 1, 1),
                                               alpha=0.45 if glass else 1.0)
                mid = cache[key]
            self.add_tris(P[tri], Nv[tri] if has_n else None, X['uv'][tri].astype(float), mid, double)

    def add_ground(self, z=0.0, half=80000.0, centre=(0, 0), color=(0.76, 0.66, 0.48), tex=None, tile=8000.0):
        cx, cy = centre
        n = 8
        xs = np.linspace(cx - half, cx + half, n + 1); ys = np.linspace(cy - half, cy + half, n + 1)
        mid = self.material(tex, color=color)
        T = []; UV = []
        for i in range(n):
            for j in range(n):
                a = (xs[i], ys[j], z); b = (xs[i + 1], ys[j], z); c = (xs[i + 1], ys[j + 1], z); d = (xs[i], ys[j + 1], z)
                for tri in ((a, c, b), (a, d, c)):                 # clockwise seen from above = front
                    T.append(tri); UV.append([(p[0] / tile, p[1] / tile) for p in tri])
        T = np.array(T); UV = np.array(UV)
        N = np.zeros_like(T); N[..., 2] = 1
        self.add_tris(T, N, UV, mid, ground=True)

    # ------------------------------------------------------------------ raster core
    @staticmethod
    def _raster(sx, sy, key, W, H, cull_sign=None, valid=None, buf=None):
        """sx, sy, key: (T,3). key is interpolated linearly in screen space, larger = nearer. -> zbuf, tid, l1, l2"""
        if buf is None:
            zb = np.full(W * H, -np.inf); tid = np.full(W * H, -1, np.int64)
            l1b = np.zeros(W * H, np.float32); l2b = np.zeros(W * H, np.float32)
        else:
            zb, tid, l1b, l2b = buf
        x0 = np.floor(sx.min(1)).astype(int); x1 = np.ceil(sx.max(1)).astype(int)
        y0 = np.floor(sy.min(1)).astype(int); y1 = np.ceil(sy.max(1)).astype(int)
        area = (sx[:, 1] - sx[:, 0]) * (sy[:, 2] - sy[:, 0]) - (sx[:, 2] - sx[:, 0]) * (sy[:, 1] - sy[:, 0])
        for t in range(len(sx)):
            if valid is not None and not valid[t]:
                continue
            A = area[t]
            if abs(A) < 1e-9:
                continue
            if cull_sign is not None and cull_sign[t] != 0 and np.sign(A) != cull_sign[t]:
                continue
            xa, xb = max(x0[t], 0), min(x1[t], W - 1)
            ya, yb = max(y0[t], 0), min(y1[t], H - 1)
            if xa > xb or ya > yb:
                continue
            px = np.arange(xa, xb + 1) + 0.5; py = np.arange(ya, yb + 1) + 0.5
            gx, gy = np.meshgrid(px, py)
            X0, X1, X2 = sx[t]; Y0, Y1, Y2 = sy[t]
            w1 = ((gx - X0) * (Y2 - Y0) - (X2 - X0) * (gy - Y0)) / A
            w2 = ((X1 - X0) * (gy - Y0) - (gx - X0) * (Y1 - Y0)) / A
            w0 = 1 - w1 - w2
            ins = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not ins.any():
                continue
            k = key[t, 0] * w0 + key[t, 1] * w1 + key[t, 2] * w2
            ix = (gy.astype(int) * W + gx.astype(int))[ins]
            kk = k[ins]
            closer = kk > zb[ix]
            if not closer.any():
                continue
            ix = ix[closer]
            zb[ix] = kk[closer]; tid[ix] = t
            l1b[ix] = w1[ins][closer]; l2b[ix] = w2[ins][closer]
        return zb, tid, l1b, l2b

    # ------------------------------------------------------------------ render
    def render(self, eye, target, size=(1280, 800), fov=40.0, up=(0, 0, 1), sun=(-0.45, 0.35, 0.82), ambient=0.42,
               diffuse=0.75, ss=2, sky=(0.62, 0.72, 0.85), shadow_res=2048, label=None):
        from PIL import Image, ImageDraw
        W, H = size[0] * ss, size[1] * ss
        P = np.concatenate(self.P); N = np.concatenate(self.N); UV = np.concatenate(self.UV)
        M = np.concatenate(self.M); D = np.concatenate(self.D)
        alpha = np.array([m['alpha'] for m in self.mats])[M]
        opaque = alpha >= 0.999
        L = _norm(sun)
        eye = np.asarray(eye, float); target = np.asarray(target, float)
        f = _norm(target - eye); r = _norm(np.cross(f, up)); u = np.cross(r, f)
        C = (P - eye) @ np.stack([r, u, f], 1)               # camera space: x right, y up, z forward
        near = 200.0
        valid = (C[..., 2] > near).all(1)
        fl = 0.5 * H / math.tan(math.radians(fov) / 2)
        z = np.maximum(C[..., 2], near)
        sx = W / 2 + fl * C[..., 0] / z
        sy = H / 2 - fl * C[..., 1] / z
        invw = 1.0 / z
        # engine culling: front face = clockwise seen from outside, i.e. -cross(b-a, c-a) points to the viewer
        g = -np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        facing = (np.einsum('ij,ij->i', g, eye - P[:, 0]) > 0) | D
        GR = np.concatenate(self.G)
        # ---- shadow map (orthographic from the sun)
        lz = -L
        lr = _norm(np.cross(lz, (0, 0, 1) if abs(lz[2]) < 0.99 else (0, 1, 0))); lu = np.cross(lr, lz)
        Ls = P @ np.stack([lr, lu, lz], 1)
        omin = Ls[..., :2].reshape(-1, 2).min(0); omax = Ls[..., :2].reshape(-1, 2).max(0)
        caster = opaque & ~GR                                  # the shadow map covers the casters only
        omin = Ls[caster][..., :2].reshape(-1, 2).min(0); omax = Ls[caster][..., :2].reshape(-1, 2).max(0)
        ext = (omax - omin).max() * 1.02
        SR = shadow_res
        ssx = (Ls[..., 0] - omin[0]) / ext * SR; ssy = (Ls[..., 1] - omin[1]) / ext * SR
        skey = -Ls[..., 2]
        szb, _, _, _ = self._raster(ssx, ssy, skey, SR, SR, valid=caster)
        # ---- main pass
        zb, tid, l1, l2 = self._raster(sx, sy, invw, W, H, valid=valid & opaque & facing)
        img = np.zeros((H * W, 3))
        skyc = np.array(sky); img[:] = skyc
        yy = (np.arange(H * W) // W) / H
        img[:] = skyc[None] * (1.05 - 0.25 * yy[:, None])
        hit = tid >= 0
        self._shade(img, hit, tid, l1, l2, invw, P, N, UV, M, L, ambient, diffuse, (lr, lu, lz, omin, ext, SR, szb))
        # ---- transparent pass (back to front, no z write)
        tr = np.nonzero(~opaque & valid)[0]
        if len(tr):
            order = tr[np.argsort(C[tr, :, 2].mean(1))[::-1]]
            for t in order:
                buf = (zb.copy(), np.full(W * H, -1, np.int64), np.zeros(W * H, np.float32), np.zeros(W * H, np.float32))
                if not facing[t]:
                    continue
                zz, tt, a1, a2 = self._raster(sx[t:t + 1], sy[t:t + 1], invw[t:t + 1], W, H, buf=buf)
                h2 = tt >= 0
                if not h2.any():
                    continue
                col = np.zeros((H * W, 3))
                acov = np.ones(H * W)
                self._shade(col, h2, np.where(h2, t, -1), a1, a2, invw, P, N, UV, M, L, ambient, diffuse,
                            (lr, lu, lz, omin, ext, SR, szb), alpha_out=acov)
                a = (alpha[t] if not self.mats[M[t]].get('tex_alpha') else 1.0) * acov[h2]
                img[h2] = img[h2] * (1 - a[:, None]) + col[h2] * a[:, None]
        out = np.clip(img.reshape(H, W, 3), 0, 1)
        im = Image.fromarray((out * 255).astype(np.uint8))
        if ss > 1:
            im = im.resize(size, Image.LANCZOS)
        if label:
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, 8 + 7 * len(label), 18), fill=(0, 0, 0))
            d.text((4, 3), label, fill=(255, 255, 255))
        return im

    def _shade(self, img, hit, tid, l1, l2, invw, P, N, UV, M, L, ambient, diffuse, shadow, alpha_out=None):
        t = tid[hit]
        b1 = l1[hit].astype(float); b2 = l2[hit].astype(float); b0 = 1 - b1 - b2
        iw = invw[t]                                                   # perspective-correct barycentrics
        w0 = b0 * iw[:, 0]; w1 = b1 * iw[:, 1]; w2 = b2 * iw[:, 2]
        s = w0 + w1 + w2
        w0 /= s; w1 /= s; w2 /= s
        wpos = P[t, 0] * w0[:, None] + P[t, 1] * w1[:, None] + P[t, 2] * w2[:, None]
        nrm = N[t, 0] * w0[:, None] + N[t, 1] * w1[:, None] + N[t, 2] * w2[:, None]
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True).clip(1e-9)
        uv = UV[t, 0] * w0[:, None] + UV[t, 1] * w1[:, None] + UV[t, 2] * w2[:, None]
        mid = M[t]
        col = np.zeros((len(t), 3))
        for k, m in enumerate(self.mats):
            sel = mid == k
            if not sel.any():
                continue
            if m['tex'] is not None:
                T = m['tex']; th, tw = T.shape[:2]
                u = np.mod(uv[sel, 0], 1.0); v = np.mod(uv[sel, 1], 1.0)
                x = np.minimum((u * tw).astype(int), tw - 1); y = np.minimum((v * th).astype(int), th - 1)
                col[sel] = T[y, x, :3] * m['tint'][None]
                if alpha_out is not None and m.get('tex_alpha'):
                    idx = np.nonzero(hit)[0][sel]
                    alpha_out[idx] = T[y, x, 3]
            else:
                col[sel] = m['color'][None]
        ndl = np.clip(nrm @ L, 0, 1)
        sh = np.ones(len(t))
        if shadow is not None:
            lr, lu, lz, omin, ext, SR, szb = shadow
            ls = wpos @ np.stack([lr, lu, lz], 1)
            qx = np.clip(((ls[:, 0] - omin[0]) / ext * SR).astype(int), 0, SR - 1)
            qy = np.clip(((ls[:, 1] - omin[1]) / ext * SR).astype(int), 0, SR - 1)
            occ = szb[qy * SR + qx]
            sh = np.where(-ls[:, 2] < occ - 60.0, 0.0, 1.0)            # bias 60 units (1.5 cm)
        em = np.array([self.mats[k]['emissive'] for k in range(len(self.mats))])[mid]
        flat = np.array([self.mats[k]['flat'] for k in range(len(self.mats))])[mid]
        lit = ambient + diffuse * ndl * sh
        lit = np.where(flat, 1.0, lit)
        img[hit] = col * (lit + em)[:, None]
