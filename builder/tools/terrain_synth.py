"""IGI 2 terrain synthesis: read / edit / write a level's terrain data.

Formats (verified, see terrain.md):
  heightmaps/heightmaps.res  ILFF 'IRES', NAME+BODY pairs, bare names 'heightmapNNN.thm|tmm|tlm', NO PATH chunk
    .thm  52-byte header + W*H float32 heights (row = y, col = x), world z = h + TerrainMap Position.z
    .tmm  44-byte header + W*H uint8  material index (= TerrainMaterial 'index' arg)
    .tlm  44-byte header + W*H uint32 B,G,R,A terrain light map (A = 255), becomes an ARGB8888 texture
    header: u32 0x3C23D70A (float 0.01 magic), 7 x u32 SYSTEMTIME (Y,M,D,h,m,s,ms), u32 type (2 thm, 0 tmm, 3 tlm),
            thm only: u32 0, f32 1.0 ; then u32 W, u32 H.
    The engine (igi2.exe 0x5910b0/0x5914c0/0x591570) checks ONLY magic, type and W/H == TerrainMap 'Map width/height'.
  forest_<taskid>.dat  u32 len + '\\nVer. 3.0\\n' + N x 40-byte records:
            pos[3] f32 (RELATIVE to the Forest task Position), rot[3] f32 (radians, x, y, z), scale[3] f32, u32 0x00RRGGBB
  TerrainMap task args: index, MapW, MapH, Px, Py, Pz, WorldW_m, WorldH_m, SoftenEdge, DEMfile
    samples are CENTRED on Position:  x = Px + (i - (MapW-1)/2) * WorldW*4096/MapW   (same for y with MapH/WorldH)
    z = h + Terrain task Position.z (the engine overwrites every TerrainMap z with its parent Terrain's z)

Units: 1 m = 4096 world units.  Python 3 + numpy (+ PIL only for previews).
"""
import os, struct, time, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = HERE                                   # lives in tools/ (copied from work/research/terrain 10-10)
import sys
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import ilff                     # noqa: E402

M = 4096.0
MAGIC = 0x3C23D70A
TYPE = {'thm': 2, 'tmm': 0, 'tlm': 3}
BPP = {'thm': 4, 'tmm': 1, 'tlm': 4}
DTYPE = {'thm': '<f4', 'tmm': np.uint8, 'tlm': np.uint8}


# ------------------------------------------------------------------------------------------------ grid entries
class Grid:
    """one heightmapNNN.thm / .tmm / .tlm body"""

    def __init__(self, kind, data, stamp=None, reserved=(0, 1.0), extra=b''):
        self.kind = kind
        self.data = data                    # thm: (H,W) float32 ; tmm: (H,W) uint8 ; tlm: (H,W,4) uint8 BGRA
        self.stamp = tuple(stamp) if stamp else now_stamp()
        self.reserved = reserved            # thm only: (u32 0, f32 1.0) - never seen different, not checked by the engine
        self.extra = extra                  # trailing bytes (location3/LEVEL4 .thm carry a float mip chain; ignored by engine)

    @property
    def shape(self):
        return self.data.shape[:2]

    @classmethod
    def parse(cls, name, body):
        kind = name[-3:].lower()
        magic, = struct.unpack_from('<I', body, 0)
        if magic != MAGIC:
            raise ValueError('%s: bad magic %08x' % (name, magic))
        stamp = struct.unpack_from('<7I', body, 4)
        typ, = struct.unpack_from('<I', body, 32)
        if typ != TYPE[kind]:
            raise ValueError('%s: type %d != %d' % (name, typ, TYPE[kind]))
        if kind == 'thm':
            r0, r1, w, h = struct.unpack_from('<IfII', body, 36)
            off, reserved = 52, (r0, r1)
        else:
            w, h = struct.unpack_from('<II', body, 36)
            off, reserved = 44, (0, 1.0)
        n = w * h * BPP[kind]
        raw = np.frombuffer(body[off:off + n], DTYPE[kind]).copy()
        data = raw.reshape(h, w, 4) if kind == 'tlm' else raw.reshape(h, w)
        g = cls(kind, data, stamp, reserved, bytes(body[off + n:]))
        g._r1_bits = body[40:44] if kind == 'thm' else None      # keep exact float bits
        return g

    def tobytes(self):
        h, w = self.shape
        hdr = struct.pack('<I7II', MAGIC, *self.stamp, TYPE[self.kind])
        if self.kind == 'thm':
            r1 = getattr(self, '_r1_bits', None) or struct.pack('<f', self.reserved[1])
            hdr += struct.pack('<I', self.reserved[0]) + r1 + struct.pack('<II', w, h)
            body = np.ascontiguousarray(self.data, '<f4').tobytes()
        else:
            hdr += struct.pack('<II', w, h)
            body = np.ascontiguousarray(self.data, np.uint8).tobytes()
        return hdr + body + self.extra


def now_stamp():
    t = time.localtime()
    return (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, 0)


# ------------------------------------------------------------------------------------------------ heightmaps.res
class HeightmapRes:
    """ordered container of heightmapNNN.* entries; write() is byte-identical for unmodified files"""

    def __init__(self, entries=None, align=4):
        self.entries = entries or []        # list of [name, Grid, chunk_aligns(name_al, body_al)]
        self.align = align

    @classmethod
    def read(cls, path_or_bytes):
        form, ch, hdr = ilff.read(path_or_bytes)
        assert form == b'IRES', form
        ents, i = [], 0
        while i < len(ch):
            t, b, al = ch[i]
            assert t == b'NAME' and ch[i + 1][0] == b'BODY', (t, ch[i + 1][0])
            name = b.rstrip(b'\0').decode('latin1')
            ents.append([name, Grid.parse(name, ch[i + 1][1]), (al, ch[i + 1][2]), b])
            i += 2
        return cls(ents, hdr[1])

    def get(self, idx, kind):
        for e in self.entries:
            if e[0].lower() == 'heightmap%03d.%s' % (idx, kind):
                return e[1]
        return None

    def put(self, idx, kind, grid):
        name = 'heightmap%03d.%s' % (idx, kind)
        for e in self.entries:
            if e[0].lower() == name:
                e[1] = grid
                return
        self.entries.append([name, grid, (4, 4), None])

    def indices(self):
        return sorted({int(e[0][9:12]) for e in self.entries})

    def tobytes(self):
        chunks = []
        for name, g, (al_n, al_b), raw_name in self.entries:
            nb = raw_name if raw_name is not None else name.encode('latin1') + b'\0'
            chunks.append((b'NAME', nb, al_n))
            chunks.append((b'BODY', g.tobytes(), al_b))
        return ilff.write(b'IRES', chunks, self.align)

    def write(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(self.tobytes())


# ------------------------------------------------------------------------------------------------ terrain model
class MapSpec:
    """one TerrainMap task"""

    def __init__(self, index, nw, nh, px, py, pz, ww, wh, soften=0.1, dem='', task_id=None, name=''):
        self.index, self.nw, self.nh = int(index), int(nw), int(nh)
        self.px, self.py, self.pz = float(px), float(py), float(pz)
        self.ww, self.wh = float(ww), float(wh)
        self.soften, self.dem, self.task_id, self.name = soften, dem, task_id, name

    @property
    def sx(self):
        return self.ww * M / self.nw

    @property
    def sy(self):
        return self.wh * M / self.nh

    # world position of sample 0. Samples are centred on Position: fitted on 103 shipped forests (68k trees) and AI
    # graph nodes - the half-cell-shifted alternative (Px - W/2*sx) is 10-100x worse (terrain.md 3.2)
    @property
    def x0(self):
        return self.px - (self.nw - 1) * self.sx / 2.0

    @property
    def y0(self):
        return self.py - (self.nh - 1) * self.sy / 2.0

    def sample_xy(self):
        """world X, Y of every sample: arrays (nh, nw)"""
        xs = self.x0 + np.arange(self.nw) * self.sx
        ys = self.y0 + np.arange(self.nh) * self.sy
        return np.meshgrid(xs, ys)

    def args(self):
        """Task_New argument values after (id, "TerrainMap", name)"""
        return [self.index, self.nw, self.nh, self.px, self.py, self.pz, self.ww, self.wh, self.soften, self.dem]

    def __repr__(self):
        return 'MapSpec(idx=%d %dx%d centre=(%.0f,%.0f,%.0f) size=%gx%g m step=%.2fx%.2f m)' % (
            self.index, self.nw, self.nh, self.px, self.py, self.pz, self.ww, self.wh, self.sx / M, self.sy / M)


def specs_from_objects(stmts):
    """TerrainMap specs + Terrain task args + TerrainMaterial list from a decompiled objects.qvm"""
    import igiqvm
    from qast import tasks, lit
    specs, terrain, mats = [], None, []
    for t, d, p in tasks(stmts):
        a = [lit(x) for x in t.args if not isinstance(x, igiqvm.Call)]
        if a[1] == 'TerrainMap':
            specs.append(MapSpec(*a[3:13], task_id=a[0], name=a[2]))
        elif a[1] == 'Terrain':
            terrain = a
        elif a[1] == 'TerrainMaterial':
            mats.append(dict(task_id=a[0], name=a[2], index=a[3], game_material=a[4], texture=a[5], detail=a[6],
                             tex_scale=a[7], detail_scale=a[8], mapping=a[9]))
    return specs, terrain, mats


class Terrain:
    """heights / materials / light of all TerrainMaps of a level, in world coordinates.
    terrain_z: the Terrain task's Position z - the engine copies it into every TerrainMap (0x591d37), so it is
    applied to all specs here (pass None to keep each spec's own pz)."""

    def __init__(self, specs, res, terrain_z=None):
        self.specs = sorted(specs, key=lambda s: s.sx * s.sy)          # finest first
        self.res = res
        if terrain_z is not None:
            for s in self.specs:
                s.pz = float(terrain_z)
        for s in self.specs:
            g = res.get(s.index, 'thm')
            if g is None or g.shape != (s.nh, s.nw):
                raise ValueError('heightmap%03d.thm missing or size %s != TerrainMap %dx%d' % (
                    s.index, None if g is None else g.shape, s.nw, s.nh))

    @classmethod
    def load(cls, level_dir, stmts=None):
        import glob
        from qast import load
        hp = glob.glob(os.path.join(level_dir, '[Hh][Ee][Ii][Gg][Hh][Tt][Mm][Aa][Pp][Ss]', 'heightmaps.res'))[0]
        if stmts is None:
            stmts = load(os.path.join(level_dir, 'objects.qvm'))
        specs, terr, _ = specs_from_objects(stmts)
        return cls(specs, HeightmapRes.read(hp), terr[5] if terr else None)

    def bounds(self):
        """(x0, y0, x1, y1) world extent of the coarsest map"""
        s = self.specs[-1]
        return s.x0, s.y0, s.x0 + (s.nw - 1) * s.sx, s.y0 + (s.nh - 1) * s.sy

    def H(self, s):
        return self.res.get(s.index, 'thm').data

    # -- sampling -------------------------------------------------------------------------------------------
    def height(self, x, y):
        """world z of the ground (bilinear; finest map covering the point wins); nan outside all maps"""
        x = np.asarray(x, float); y = np.asarray(y, float)
        out = np.full(np.broadcast(x, y).shape, np.nan)
        for s in reversed(self.specs):                       # coarse first, finer maps overwrite
            ok, z = _bilinear(self.H(s).astype(float), s, x, y, s.pz)
            out = np.where(ok, z, out)
        return out if out.shape else float(out)

    def sample(self, s, kind, x, y):
        """nearest-sample value of a .tmm / .tlm grid of map s at world (x, y)"""
        g = self.res.get(s.index, kind).data
        i = np.clip(np.round((np.asarray(x) - s.x0) / s.sx).astype(int), 0, s.nw - 1)
        j = np.clip(np.round((np.asarray(y) - s.y0) / s.sy).astype(int), 0, s.nh - 1)
        return g[j, i]

    def finest_at(self, x, y):
        for s in self.specs:
            i = (x - s.x0) / s.sx; j = (y - s.y0) / s.sy
            if 0 <= i < s.nw - 1 and 0 <= j < s.nh - 1:
                return s
        return None

    # -- editing --------------------------------------------------------------------------------------------
    def apply(self, fn, maps=None):
        """fn(X, Y, Z) -> new Z (all world units, arrays). Applied to EVERY map so coarse and fine stay consistent."""
        for s in (maps or self.specs):
            X, Y = s.sample_xy()
            Z = self.H(s).astype(float) + s.pz
            Zn = fn(X, Y, Z)
            self.res.get(s.index, 'thm').data = (np.asarray(Zn, float) - s.pz).astype('<f4')

    def paint_material(self, mask_fn, index, maps=None):
        """mask_fn(X, Y, Z) -> bool array; sets .tmm cells to TerrainMaterial index"""
        for s in (maps or self.specs):
            X, Y = s.sample_xy()
            Z = self.H(s).astype(float) + s.pz
            g = self.res.get(s.index, 'tmm')
            g.data = np.where(mask_fn(X, Y, Z), np.uint8(index), g.data).astype(np.uint8)


def _bilinear(H, s, x, y, z0):
    h, w = H.shape
    i = (x - s.x0) / s.sx; j = (y - s.y0) / s.sy
    ok = (i >= 0) & (j >= 0) & (i <= w - 1) & (j <= h - 1)
    ic = np.clip(i, 0, w - 1.000001); jc = np.clip(j, 0, h - 1.000001)
    ii = ic.astype(int); jj = jc.astype(int); fi = ic - ii; fj = jc - jj
    z = (H[jj, ii] * (1 - fi) * (1 - fj) + H[jj, ii + 1] * fi * (1 - fj) +
         H[jj + 1, ii] * (1 - fi) * fj + H[jj + 1, ii + 1] * fi * fj) + z0
    return ok, z


# ------------------------------------------------------------------------------------------------ shape primitives
# every primitive returns fn(X, Y, Z) -> Z for Terrain.apply ; distances in world units (use m * M)

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0 + 1e-12), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def flatten_pad(cx, cy, radius, z, falloff, shape='circle', half=None, angle=0.0):
    """flat pad at world height z; blends back to the original terrain over `falloff` (world units).
    shape='rect': half=(hx, hy) half-sizes, rotated by angle (radians)"""
    def fn(X, Y, Z):
        dx, dy = X - cx, Y - cy
        if shape == 'rect':
            ca, sa = math.cos(angle), math.sin(angle)
            u, v = np.abs(dx * ca + dy * sa) - half[0], np.abs(-dx * sa + dy * ca) - half[1]
            d = np.hypot(np.maximum(u, 0), np.maximum(v, 0))
        else:
            d = np.maximum(np.hypot(dx, dy) - radius, 0)
        w = 1 - smoothstep(0, falloff, d)
        return Z * (1 - w) + z * w
    return fn


def bump(cx, cy, radius, dz):
    """raise (dz > 0) or lower (dz < 0) with a smooth cosine bell of the given radius"""
    def fn(X, Y, Z):
        r = np.hypot(X - cx, Y - cy) / radius
        return Z + dz * np.where(r < 1, 0.5 * (1 + np.cos(np.pi * np.minimum(r, 1))), 0)
    return fn


def mountain(cx, cy, radius, height, roughness=0.35, seed=1):
    """adds a peak `height` (world units) on top of the existing ground, fBm-roughened, zero at `radius`"""
    nz = fbm(seed, radius / 3.0, octaves=5)

    def fn(X, Y, Z):
        r = np.hypot(X - cx, Y - cy) / radius
        prof = np.clip(1 - r, 0, 1) ** 1.6
        return Z + height * prof * (1 + roughness * nz(X, Y))
    return fn


def plateau(cx, cy, radius, z, cliff):
    """raise the ground to at least z inside radius, cliff of width `cliff` (steep smoothstep) outside"""
    def fn(X, Y, Z):
        d = np.hypot(X - cx, Y - cy) - radius
        w = 1 - smoothstep(0, cliff, d)
        return np.maximum(Z, Z * (1 - w) + z * w)
    return fn


def valley(points, width, depth, falloff, floor=None):
    """carve a valley/canyon along a polyline [(x, y), ...]: floor `depth` below the original (or absolute `floor`
    z if given), flat floor of `width`, banks of `falloff`. Never raises the ground."""
    P = np.asarray(points, float)

    def fn(X, Y, Z):
        dmin = np.full(X.shape, np.inf)
        for k in range(len(P) - 1):
            a, b = P[k], P[k + 1]; ab = b - a; L2 = ab @ ab + 1e-12
            t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / L2, 0, 1)
            dmin = np.minimum(dmin, np.hypot(X - (a[0] + t * ab[0]), Y - (a[1] + t * ab[1])))
        w = 1 - smoothstep(width / 2.0, width / 2.0 + falloff, dmin)
        target = (Z - depth) if floor is None else np.full(Z.shape, float(floor))
        return np.minimum(Z, Z * (1 - w) + target * w)
    return fn


def fbm(seed, scale, octaves=4, persistence=0.5):
    """value-noise fBm in [-1, 1]; scale = feature size in world units"""
    rng = np.random.default_rng(seed)
    tabs = []
    for _ in range(octaves):
        t = rng.uniform(-1, 1, (257, 257))
        t[256, :] = t[0, :]; t[:, 256] = t[:, 0]           # periodic lattice: no seam where the index wraps
        tabs.append(t)

    def noise(X, Y):
        out = np.zeros(np.shape(X)); amp = 1.0; tot = 0.0; f = 1.0 / scale
        for o in range(octaves):
            u = X * f + 37.0 * o; v = Y * f + 91.0 * o
            iu = np.floor(u).astype(np.int64); iv = np.floor(v).astype(np.int64)
            fu = u - iu; fv = v - iv
            fu = fu * fu * (3 - 2 * fu); fv = fv * fv * (3 - 2 * fv)
            T = tabs[o]; a = iu % 256; b = iv % 256
            n = (T[b, a] * (1 - fu) * (1 - fv) + T[b, a + 1] * fu * (1 - fv) +
                 T[b + 1, a] * (1 - fu) * fv + T[b + 1, a + 1] * fu * fv)
            out += amp * n; tot += amp; amp *= persistence; f *= 2.0
        return out / tot
    return noise


def chain(*fns):
    def fn(X, Y, Z):
        for f in fns:
            Z = f(X, Y, Z)
        return Z
    return fn


# ------------------------------------------------------------------------------------------------ light maps
def sun_vector(pitch, yaw):
    """unit vector TO the sun from the first two DirlightKeyframe args (radians, as stored in objects.qvm):
        L = (cos p * cos y, -cos p * sin y, sin p)
    Checked against a blind sun fit of the shipped .tlm files: 18 of 21 terrain levels agree within ~5 deg of
    azimuth (terrain.md 4.3)."""
    return np.array([math.cos(pitch) * math.cos(yaw), -math.cos(pitch) * math.sin(yaw), math.sin(pitch)])


def sun_from_azel(az_deg, el_deg):
    """vector TO the sun: azimuth from +X towards +Y (degrees), elevation above the horizon"""
    a, e = math.radians(az_deg), math.radians(el_deg)
    return np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])


def normals(H, sx, sy):
    gy, gx = np.gradient(H.astype(float), sy, sx)
    n = np.dstack([-gx, -gy, np.ones_like(gx)])
    return n / np.linalg.norm(n, axis=2, keepdims=True)


def cast_shadows(H, sx, sy, L, max_dist=None, step=1.0):
    """1 where the sample sees the sun, 0 in terrain shadow (height-field ray march, numpy)"""
    h, w = H.shape
    if L[2] >= 0.999:
        return np.ones_like(H, float)
    horiz = math.hypot(L[0], L[1])
    dx, dy = L[0] / horiz, L[1] / horiz                  # unit horizontal step (in world units * cell)
    tan = L[2] / horiz
    cell = min(sx, sy) * step
    max_dist = max_dist or max(w * sx, h * sy)
    lit = np.ones_like(H, bool)
    J, I = np.mgrid[0:h, 0:w].astype(float)
    Hf = H.astype(float)
    nsteps = int(max_dist / cell)
    for k in range(1, nsteps + 1):
        d = k * cell
        x = I + dx * d / sx; y = J + dy * d / sy
        inside = (x >= 0) & (y >= 0) & (x <= w - 1) & (y <= h - 1)
        if not inside.any():
            break
        xc = np.clip(x, 0, w - 1.0001); yc = np.clip(y, 0, h - 1.0001)
        ii = xc.astype(int); jj = yc.astype(int); fi = xc - ii; fj = yc - jj
        z = (Hf[jj, ii] * (1 - fi) * (1 - fj) + Hf[jj, ii + 1] * fi * (1 - fj) + Hf[jj + 1, ii] * (1 - fi) * fj +
             Hf[jj + 1, ii + 1] * fi * fj)
        lit &= ~(inside & (z > Hf + d * tan + 0.05 * M))
    return lit.astype(float)


def shade(H, sx, sy, sun, shadows=True, shadow_strength=0.8):
    """max(0, N.L), optionally darkened where the terrain itself blocks the sun"""
    nd = np.clip(normals(H, sx, sy) @ np.asarray(sun, float), 0, 1)
    if shadows:
        nd = nd * (1 - shadow_strength * (1 - cast_shadows(H, sx, sy, sun)))
    return nd


def compute_tlm(H, sx, sy, sun, base_bgr=(45, 45, 50), sun_bgr=(85, 95, 105), shadows=True, shadow_strength=0.8):
    """synthetic terrain light map (H, W, 4) uint8 BGRA = base + sun_gain * shade, per channel (0..255 units).
    Defaults = a neutral daylight look inside the range of the originals (per-channel fits on daylight levels:
    base ~25-90, gain ~45-150; night levels gain ~15-35). Use fit_channels() on a shipped level to copy its look."""
    s = shade(H, sx, sy, sun, shadows, shadow_strength)
    out = np.empty(H.shape + (4,), np.uint8)
    for c in range(3):
        out[:, :, c] = np.clip(np.round(base_bgr[c] + sun_bgr[c] * s), 0, 255)
    out[:, :, 3] = 255
    return out


def fit_channels(H, sx, sy, tlm, sun, shadows=False):
    """per-channel least squares tlm[c] = base[c] + gain[c] * shade -> (base_bgr, sun_bgr, corr_lum)"""
    s = shade(H, sx, sy, sun, shadows)[2:-2, 2:-2].ravel()
    base, gain = [], []
    for c in range(3):
        v = tlm[2:-2, 2:-2, c].astype(float).ravel()
        b, a = np.polyfit(s, v, 1)
        base.append(a); gain.append(b)
    lum = tlm[2:-2, 2:-2, :3].astype(float).mean(2).ravel()
    return tuple(base), tuple(gain), float(np.corrcoef(s, lum)[0, 1])


def neutral_tlm(h, w, bgr=(128, 128, 128)):
    """flat light map (no baked shading). NB: a MISSING .tlm makes the engine use 0xFFFFFFFF (full white)."""
    out = np.empty((h, w, 4), np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2], out[:, :, 3] = bgr[0], bgr[1], bgr[2], 255
    return out


def fit_lambert(H, sx, sy, tlm, mask=None):
    """least-squares: lum = a + b * max(0, N.L); grid search over sun direction. -> (corr, pitch, yaw, a, b)"""
    n = normals(H, sx, sy)
    lum = tlm[:, :, :3].astype(float).mean(2)
    m = np.ones(lum.shape, bool) if mask is None else np.array(mask, bool)      # copy: never touch the caller's mask
    m[:2] = m[-2:] = False; m[:, :2] = m[:, -2:] = False
    nn = n[m]; ll = lum[m]
    if len(ll) > 60000:
        sel = np.random.default_rng(0).choice(len(ll), 60000, replace=False); nn = nn[sel]; ll = ll[sel]
    best = None
    for pitch in np.radians(np.arange(5, 90, 2.5)):
        for yaw in np.radians(np.arange(-180, 180, 2.5)):
            s = np.clip(nn @ sun_vector(pitch, yaw), 0, 1)
            if s.std() < 1e-6:
                continue
            c = np.corrcoef(s, ll)[0, 1]
            if best is None or c > best[0]:
                b, a = np.polyfit(s, ll, 1)
                best = (c, pitch, yaw, a, b)
    return best


def transfer_baked(old_tlm, old_shade, new_shade, lo=0.2, hi=3.0):
    """keep baked object shadows / lamp pools of the original light map when the terrain shading changes:
    new = old * new_shade / old_shade (per channel, ratio clipped)"""
    r = np.clip((new_shade.astype(float) + 1) / (old_shade.astype(float) + 1), lo, hi)
    out = old_tlm.copy()
    out[:, :, :3] = np.clip(old_tlm[:, :, :3].astype(float) * r[:, :, :3], 0, 255).astype(np.uint8)
    return out


# ------------------------------------------------------------------------------------------------ material maps
def auto_materials(H, sx, sy, rules, default=0):
    """rules: list of (index, fn(z_world_rel, slope_deg) -> bool), later rules win. Returns (H,W) uint8"""
    n = normals(H, sx, sy)
    slope = np.degrees(np.arccos(np.clip(n[:, :, 2], -1, 1)))
    out = np.full(H.shape, default, np.uint8)
    for idx, f in rules:
        out[f(H, slope)] = idx
    return out


# ------------------------------------------------------------------------------------------------ forests
FOREST_REC = np.dtype([('pos', '<f4', 3), ('rot', '<f4', 3), ('scale', '<f4', 3), ('color', '<u4')])
FOREST_VER = b'\nVer. 3.0\n'


def read_forest(path_or_bytes):
    d = open(path_or_bytes, 'rb').read() if isinstance(path_or_bytes, str) else path_or_bytes
    L, = struct.unpack_from('<I', d, 0)
    ver = d[4:4 + L]
    if ver != FOREST_VER:
        raise ValueError('forest version %r (engine knows Ver. 3.0 = 40-byte records and an older 36-byte one)' % ver)
    n = (len(d) - 4 - L) // 40
    rec = np.frombuffer(d[4 + L:4 + L + n * 40], FOREST_REC).copy()
    return rec, d[4 + L + n * 40:]


def write_forest(rec, tail=b''):
    rec = np.ascontiguousarray(rec, FOREST_REC)
    return struct.pack('<I', len(FOREST_VER)) + FOREST_VER + rec.tobytes() + tail


def snap_forest(rec, task_pos, terrain, dz=0.0):
    """put every tree exactly on the ground of `terrain` (use for NEW terrain / new trees).
    Positions are relative to the Forest task Position."""
    out = rec.copy()
    wx = out['pos'][:, 0].astype(float) + task_pos[0]
    wy = out['pos'][:, 1].astype(float) + task_pos[1]
    z = terrain.height(wx, wy)
    keep = ~np.isnan(z)
    out['pos'][keep, 2] = (z[keep] + dz - task_pos[2]).astype('<f4')
    return out


def reseat_forest(rec, task_pos, old_terrain, new_terrain, eps=0.001 * M):
    """after RESHAPING a level: move each tree by the change of the ground under it (new - old), so trees on
    unedited ground keep their exact original Z (and trees that sat on rocks/props keep their offset).
    Returns (records, number of trees moved)."""
    out = rec.copy()
    wx = out['pos'][:, 0].astype(float) + task_pos[0]
    wy = out['pos'][:, 1].astype(float) + task_pos[1]
    d = new_terrain.height(wx, wy) - old_terrain.height(wx, wy)
    mv = ~np.isnan(d) & (np.abs(d) > eps)
    out['pos'][mv, 2] = (out['pos'][mv, 2].astype(float) + d[mv]).astype('<f4')
    return out, int(mv.sum())


def scatter_forest(n, area_fn, task_pos, terrain, seed=0, rot_range=1.0, scale_range=(0.1, 0.1, 0.1),
                   isotropic=True, color_fn=None, bounds=None, color_gain=1.15):
    """n trees at random positions where area_fn(x, y, z) is True (world units). rot_range in turns (1 = 0..2pi,
    like the Forest 'Random rotation range' arg); scale 1 +- range. bounds = (x0, y0, x1, y1), default the whole
    terrain. color_fn(x, y) -> 0x00RRGGBB; default = .tlm under the tree * color_gain (GUESS: shipped tree
    colours are 1.0-2.3x the .tlm, median ~1.1 on most levels). May return fewer than n trees (never raises)."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = bounds or terrain.bounds()
    pts = []
    tries = 0
    while len(pts) < n and tries < 200:
        tries += 1
        X = rng.uniform(x0, x1, n * 4); Y = rng.uniform(y0, y1, n * 4)
        Z = terrain.height(X, Y)
        ok = ~np.isnan(Z)
        ok[ok] = np.asarray(area_fn(X[ok], Y[ok], Z[ok]), bool)
        pts += list(zip(X[ok], Y[ok], Z[ok]))
    pts = np.array(pts[:n], float).reshape(-1, 3)
    rec = np.zeros(len(pts), FOREST_REC)
    if not len(pts):
        return rec
    rec['pos'] = (pts - np.asarray(task_pos, float)).astype('<f4')
    rec['rot'][:, 2] = rng.uniform(0, 2 * np.pi * rot_range, len(pts))
    s = 1 + rng.uniform(-1, 1, (len(pts), 3)) * np.asarray(scale_range)
    if isotropic:
        s[:, 1] = s[:, 2] = s[:, 0]
    rec['scale'] = s.astype('<f4')
    if color_fn is None:
        def color_fn(x, y):
            out = np.zeros(len(x), np.uint32)
            for k, (xx, yy) in enumerate(zip(x, y)):
                sp = terrain.finest_at(xx, yy)
                if sp is not None and terrain.res.get(sp.index, 'tlm') is not None:
                    b, g, r, a = (min(255, int(c * color_gain)) for c in terrain.sample(sp, 'tlm', xx, yy))
                    out[k] = (r << 16) | (g << 8) | b
                else:
                    out[k] = 0x808080
            return out
    rec['color'] = color_fn(pts[:, 0], pts[:, 1])
    return rec


def forest_task_args(px, py, pz, model, n_trees, area=500.0, rot=1.0, xs=0.1, ys=0.1, zs=0.1, iso=True,
                     cutoff=200.0, wind_lods=2):
    """Task_New argument values after (id, "Forest", name); 'Number of trees' MUST equal the record count
    (engine 0x5c85d0 loads min(arg, records) and skips the file when the arg is 0)"""
    return [px, py, pz, model, area, False, False, False, 1e-06, rot, xs, ys, zs, iso, int(n_trees), 2.0, False,
            cutoff, False, wind_lods]


# ------------------------------------------------------------------------------------------------ new terrain
def new_terrain(maps, height_fn, materials_fn=None, light=None, stamp=None):
    """build a HeightmapRes from scratch.
    maps: list of MapSpec, all with the same pz (= the Terrain task Position z); W/H powers of two 2..1024 (every
    shipped map is 64..512 square; the .tlm becomes a texture). height_fn(X, Y) -> world z.
    materials_fn(H, sx, sy) -> uint8 grid of TerrainMaterial indices.
    light: keyword dict for compute_tlm, e.g. dict(sun=sun_vector(p, y), base_bgr=(..), sun_bgr=(..), shadows=True),
    or None for a neutral grey map."""
    res = HeightmapRes()
    st = stamp or now_stamp()
    if len({s.pz for s in maps}) > 1:
        raise ValueError('all TerrainMaps share the Terrain task z - got %s' % sorted({s.pz for s in maps}))
    for s in maps:
        for v in (s.nw, s.nh):
            if v < 2 or v > 1024 or v & (v - 1):
                raise ValueError('map size %d not a power of two in 2..1024' % v)
        X, Y = s.sample_xy()
        Hrel = (np.asarray(height_fn(X, Y), float) - s.pz).astype('<f4')
        res.put(s.index, 'thm', Grid('thm', Hrel, st))
        mat = materials_fn(Hrel, s.sx, s.sy) if materials_fn else np.zeros(Hrel.shape, np.uint8)
        res.put(s.index, 'tmm', Grid('tmm', mat.astype(np.uint8), st))
        tl = compute_tlm(Hrel, s.sx, s.sy, **light) if light else neutral_tlm(s.nh, s.nw)
        res.put(s.index, 'tlm', Grid('tlm', tl, st))
    return res


def terrain_task_qsc(task_id, terrain_args, maps, materials, first_id):
    """QSC text for a Terrain task with its TerrainMap / TerrainMaterial children (ids from first_id).
    terrain_args: 16 values (Position x,y,z, World width, World height, Detail, Adaption, Brush size, Brush power,
    Shadow samples, Shadow spread, Min/Max brush size, Min/Max brush power, Number of brushes)."""
    import igiqvm

    def v(x):
        if isinstance(x, (bool, np.bool_)):
            return 'TRUE' if x else 'FALSE'
        if isinstance(x, str):
            return igiqvm.qstr(x)
        if isinstance(x, (float, np.floating)):
            if not math.isfinite(x):
                raise ValueError('non-finite task argument %r' % x)
            return '%d' % int(x) if x == int(x) and abs(x) < 1e15 else igiqvm.fmt_float(float(x))
        return str(int(x))
    for s in maps:
        if s.pz != terrain_args[2]:
            raise ValueError('TerrainMap %d z %r != Terrain z %r (engine overwrites it)' % (s.index, s.pz, terrain_args[2]))
    kids = []
    nid = first_id
    for s in maps:
        kids.append('Task_New(%d, "TerrainMap", %s, %s)' % (nid, igiqvm.qstr(s.name), ', '.join(v(a) for a in s.args())))
        nid += 1
    for m in materials:
        kids.append('Task_New(%d, "TerrainMaterial", %s, %s)' % (nid, igiqvm.qstr(m['name']), ', '.join(v(a) for a in (
            m['index'], m['game_material'], m['texture'], m['detail'], m['tex_scale'], m['detail_scale'], m['mapping']))))
        nid += 1
    return 'Task_New(%d, "Terrain", "", %s,\n    %s)' % (task_id, ', '.join(v(a) for a in terrain_args), ',\n    '.join(kids))


def check_level(res, specs, material_indices=None, terrain_z=None, textures=None, texture_dir=None):
    """the engine's own load checks (magic/type/size/index slots) + things that silently go wrong.
    material_indices: TerrainMaterial 'index' values (flags .tmm cells without a material);
    terrain_z: the Terrain task Position z (every TerrainMap z should equal it);
    textures + texture_dir: TerrainMaterial texture strings and the mission's textures folder (existence check of
    MISSION:textures/<basename>, the engine's rewrite)."""
    problems = []
    idx = {s.index for s in specs}
    if len(specs) > 10:
        problems.append('%d TerrainMaps > 10 (engine: "Too many heightmaps")' % len(specs))
    if material_indices is not None:
        mi = list(material_indices)
        if len(mi) > 10 or len(set(mi)) != len(mi) or any(not 0 <= m <= 9 for m in mi):
            problems.append('TerrainMaterial indices must be unique 0..9, max 10 (no range check in the engine: '
                            'index >= 10 writes past its 10-slot table): %s' % mi)
    if terrain_z is not None:
        for s in specs:
            if s.pz != terrain_z:
                problems.append('TerrainMap %d z %r != Terrain z %r (engine uses the Terrain z)' % (s.index, s.pz, terrain_z))
    if textures is not None and texture_dir is not None:
        have = {f.lower() for f in os.listdir(texture_dir)} if os.path.isdir(texture_dir) else set()
        for t in textures:
            base = t.replace('\\', '/').split('/')[-1]
            if t != 'File not found' and base.lower() not in have:
                problems.append('texture %s -> MISSION:textures/%s not in %s' % (t, base, texture_dir))
    for s in specs:
        if not 0 <= s.index <= 9:
            problems.append('TerrainMap index %d out of range 0..9 (no range check in the engine: >= 10 overruns the '
                            '10-slot table, >= 1000 is a fatal load error)' % s.index)
        for v in (s.nw, s.nh):
            if v < 2 or v > 1024 or v & (v - 1):
                problems.append('TerrainMap %d size %d is not a power of two in 2..1024 (engine clamps/rounds it up)' % (s.index, v))
        if material_indices is not None and res.get(s.index, 'tmm') is not None:
            bad = sorted(set(np.unique(res.get(s.index, 'tmm').data).tolist()) - set(material_indices))
            if bad:
                problems.append('heightmap%03d.tmm uses material indices %s with no TerrainMaterial' % (s.index, bad))
        for k in ('thm', 'tmm', 'tlm'):
            g = res.get(s.index, k)
            if g is None:
                problems.append('heightmap%03d.%s missing (engine: thm -> unfilled buffer, tmm -> material 0, '
                                'tlm -> 0xFFFFFFFF white)' % (s.index, k))
            elif g.shape != (s.nh, s.nw):
                problems.append('heightmap%03d.%s is %s, TerrainMap wants %dx%d -> engine treats it as missing' % (s.index, k, g.shape, s.nw, s.nh))
            elif k == 'thm' and not np.isfinite(g.data).all():
                problems.append('heightmap%03d.thm has NaN/inf' % s.index)
    if len(idx) != len(specs):
        problems.append('duplicate TerrainMap index (engine: "Duplicate heightmap IDs")')
    return problems


# ------------------------------------------------------------------------------------------------ previews
def preview(res, idx, path):
    from PIL import Image
    H = res.get(idx, 'thm').data.astype(float)
    gy, gx = np.gradient(H)
    sh = np.clip(0.5 + (gx - gy) / (np.abs(gx).mean() * 8 + 1e-9), 0, 1)
    g = (H - H.min()) / (np.ptp(H) + 1e-9)
    a = np.dstack([g * 255 * 0.6 + sh * 255 * 0.4] * 3).astype(np.uint8)
    t = res.get(idx, 'tlm')
    b = t.data[:, :, [2, 1, 0]] if t is not None else a
    Image.fromarray(np.hstack([a, b])).save(path)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('res'); a = ap.parse_args()
    r = HeightmapRes.read(a.res)
    for name, g, al, _ in r.entries:
        extra = ' +%d trailing bytes' % len(g.extra) if g.extra else ''
        rng = ' z=[%.0f, %.0f]' % (g.data.min(), g.data.max()) if g.kind == 'thm' else ''
        print('%-18s %s %dx%d stamp=%04d-%02d-%02d%s%s' % (name, g.kind, g.shape[1], g.shape[0], *g.stamp[:3], rng, extra))
