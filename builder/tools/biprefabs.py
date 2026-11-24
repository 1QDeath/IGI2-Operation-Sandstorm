"""biprefabs - the NEW models of Operation Black Ice (owner 10-13: 'new prefabs, built with tools/mefmesh like the
searchlight and the wreck'). Every model is a vertex-lit rigid .mef (type 0) built from boxes / cylinders / slabs with
generated textures, registered in the mission overlay's manifest + banks (searchlight.add_models recipe).

    import biprefabs
    biprefabs.add_models(overlay_dir, 'jungle')     # after K.write(): every bi_*_1 model + its textures + lod lines
    biprefabs.NAMES                                 # the model names (for Mission.models / validate)

Model frames: z up, 1 m = 4096 units, origin on the ground (floor) unless noted. Front face = clockwise seen from
outside (searchlight._box / _orient take care of that).
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, mefmesh, wreck, searchlight as SL

M = 4096.0
NAMES = ['bi_barracks_1', 'bi_culvert_1', 'bi_headframe_1', 'bi_shaft_1', 'bi_cell_1', 'bi_bars_1', 'bi_generator_1',
         'bi_lamp_1', 'bi_lampoff_1', 'bi_sign_1', 'bi_poster_1', 'bi_poster_2', 'bi_poster_3', 'bi_keys_1', 'bi_icetrack_1',
         'bi_icehole_1', 'bi_flare_1', 'bi_bunk_1', 'bi_wallgap_1', 'bi_ramp_1', 'bi_slhoff_1', 'bi_icelid_1', 'bi_slpost_1', 'bi_tower_1']
FONT_B = r'C:\Windows\Fonts\arialbd.ttf'
FONT_R = r'C:\Windows\Fonts\arial.ttf'


# ================================================================================================ geometry helpers
def box(c, h, uv_scale=1.0):
    P, T, N, U = SL._box(c, h)
    return P, T, N, U * uv_scale


def box_m(x0, y0, z0, x1, y1, z1, uv=1.0):
    """axis-aligned box from corner to corner (metres) -> units"""
    c = ((x0 + x1) / 2 * M, (y0 + y1) / 2 * M, (z0 + z1) / 2 * M)
    h = ((x1 - x0) / 2 * M, (y1 - y0) / 2 * M, (z1 - z0) / 2 * M)
    P, T, N, U = SL._box(c, h)
    # uv in metres so wood/log textures tile at their real size
    U2 = []
    for k in range(len(P)):
        n = N[k]; p = P[k] / M
        if abs(n[2]) > 0.5:
            U2.append((p[0] * uv, p[1] * uv))
        elif abs(n[0]) > 0.5:
            U2.append((p[1] * uv, p[2] * uv))
        else:
            U2.append((p[0] * uv, p[2] * uv))
    return P, T, N, np.array(U2, float)


def cyl_z(r, z0, z1, seg=12, cx=0.0, cy=0.0, uv=1.0):
    """vertical cylinder (side wall + top/bottom discs), metres -> units"""
    P, N, U, T = [], [], [], []
    for k in range(seg + 1):
        a = 2 * math.pi * k / seg
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        for z in (z0, z1):
            P.append((x * M, y * M, z * M)); N.append((math.cos(a), math.sin(a), 0)); U.append((k / seg * 2 * math.pi * r * uv, z * uv))
    for k in range(seg):
        i = 2 * k
        T += [(i, i + 1, i + 3), (i, i + 3, i + 2)]
    P, N, U, T = np.array(P, float), np.array(N, float), np.array(U, float), np.array(T)
    out = np.c_[P[T].mean(1)[:, 0] - cx * M, P[T].mean(1)[:, 1] - cy * M, np.zeros(len(T))]
    T = SL._orient(P, T, N, out)
    parts = [(P, T, N, U)]
    for z, sg in ((z1, 1.0), (z0, -1.0)):
        Pd = [(cx * M, cy * M, z * M)] + [(cx * M + r * M * math.cos(2 * math.pi * k / seg), cy * M + r * M * math.sin(2 * math.pi * k / seg), z * M) for k in range(seg)]
        Ud = [(0.5, 0.5)] + [(0.5 + 0.5 * math.cos(2 * math.pi * k / seg), 0.5 + 0.5 * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
        Td = np.array([(0, 1 + k, 1 + (k + 1) % seg) for k in range(seg)])
        Pd = np.array(Pd, float); Nd = np.tile([0, 0, sg], (len(Pd), 1))
        Td = SL._orient(Pd, Td, Nd, np.tile([0, 0, sg], (len(Td), 1)))
        parts.append((Pd, Td, Nd, np.array(Ud, float)))
    return SL._merge(parts)


def cyl_axis(r, a0, a1, axis, seg=12, at=(0.0, 0.0), uv=1.0):
    """cylinder along axis 'x' or 'y' from a0 to a1 (metres), centred at `at` in the other two axes"""
    P, T, N, U = cyl_z(r, a0, a1, seg, 0.0, 0.0, uv)
    if axis == 'x':
        R = np.array([[0, 0, 1.0], [0, 1.0, 0], [-1.0, 0, 0]])     # z -> x
    else:
        R = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])     # z -> y
    P = P @ R.T; N = N @ R.T
    off = np.array([0.0, at[0] * M, at[1] * M]) if axis == 'x' else np.array([at[0] * M, 0.0, at[1] * M])
    return P + off, T, N, U


def slab(x0, y0, x1, y1, z, uv=(1.0, 1.0), up=True, thick=0.0):
    """a horizontal quad (two-sided when thick == 0)"""
    if thick > 0:
        return box_m(x0, y0, z - thick, x1, y1, z, uv=uv[0])
    P = np.array([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], float) * M
    U = np.array([(0, 0), (uv[0], 0), (uv[0], uv[1]), (0, uv[1])], float)
    T = np.array([(0, 1, 2), (0, 2, 3)])
    N = np.tile([0, 0, 1.0 if up else -1.0], (4, 1))
    T = SL._orient(P, T, N, np.tile(N[0], (2, 1)))
    T2 = T[:, [0, 2, 1]]
    return P, np.concatenate([T, T2]), N, U


def merge(parts):
    return SL._merge(parts)


# ================================================================================================ textures (float RGBA)
def _noise(n, rng, octaves=4):
    out = np.zeros((n, n))
    for o in range(octaves):
        k = 2 ** o
        g = rng.random((k * 4 + 1, k * 4 + 1))
        y = np.linspace(0, k * 4, n); x = np.linspace(0, k * 4, n)
        yi, xi = np.floor(y).astype(int), np.floor(x).astype(int)
        yf, xf = (y - yi)[:, None], (x - xi)[None, :]
        yi = np.clip(yi, 0, k * 4 - 1); xi = np.clip(xi, 0, k * 4 - 1)
        a = g[yi][:, xi]; b = g[yi][:, xi + 1]; c = g[yi + 1][:, xi]; d = g[yi + 1][:, xi + 1]
        out += ((a * (1 - xf) + b * xf) * (1 - yf) + (c * (1 - xf) + d * xf) * yf) / (2 ** o)
    return (out - out.min()) / (out.max() - out.min() + 1e-9)


def tex_logs(n=512, seed=1):
    """horizontal pine logs, dark brown, snow dust on the top edge of every log (1 texture repeat = 1 m)"""
    rng = np.random.default_rng(seed)
    yy = np.linspace(0, 1, n)[:, None]
    logs = 4                                                     # 4 logs per metre
    ph = (yy * logs) % 1.0
    shade = 0.55 + 0.45 * np.sin(ph * math.pi) ** 0.6           # round log
    grain = 0.85 + 0.15 * _noise(n, rng, 3)
    base = np.array([0.42, 0.30, 0.18])
    img = np.dstack([base[k] * shade * grain for k in range(3)])
    gap = ph < 0.06
    img[gap.repeat(n, 1)] *= 0.35                                # the dark seam between logs
    snow = (ph > 0.60) & (ph < 0.78) & (_noise(n, rng, 2) > 0.45)
    img[snow.repeat(n, 1) if snow.shape[1] == 1 else snow] = [0.86, 0.88, 0.92]
    return np.dstack([img, np.ones((n, n))])


def tex_planks(n=512, seed=2, base=(0.46, 0.36, 0.24), snow=0.0):
    rng = np.random.default_rng(seed)
    xx = np.linspace(0, 1, n)[None, :]
    ph = (xx * 6) % 1.0
    img = np.dstack([np.full((n, n), c) for c in base]) * (0.8 + 0.2 * _noise(n, rng, 4))[:, :, None]
    img[np.broadcast_to(ph < 0.04, (n, n))] *= 0.4
    if snow:
        sn = _noise(n, rng, 2) > (1 - snow)
        img[sn] = [0.88, 0.90, 0.94]
    return np.dstack([img, np.ones((n, n))])


def tex_concrete(n=512, seed=3, base=(0.52, 0.52, 0.50)):
    rng = np.random.default_rng(seed)
    g = 0.75 + 0.25 * _noise(n, rng, 5)
    img = np.dstack([base[k] * g for k in range(3)])
    stain = _noise(n, rng, 2) < 0.25
    img[stain] *= 0.75
    return np.dstack([img, np.ones((n, n))])


def tex_steel(n=256, seed=4, base=(0.30, 0.30, 0.32)):
    rng = np.random.default_rng(seed)
    g = 0.8 + 0.2 * _noise(n, rng, 4)
    img = np.dstack([base[k] * g for k in range(3)])
    # (owner 10-14 'new buildings look glitched': hard-edged rust blobs read as camouflage. Soft rust that runs down
    #  in streaks, at most 40 % over the paint.)
    r = _noise(n, rng, 3)
    r = np.clip((r - 0.55) / 0.35, 0.0, 1.0)
    r = np.cumsum(r, axis=0) / np.arange(1, n + 1)[:, None] * 0.5 + r * 0.5     # streaks down the texture (v)
    w = (0.40 * np.clip(r, 0.0, 1.0))[:, :, None]
    img = img * (1 - w) + (np.array([0.42, 0.27, 0.17]) * g[:, :, None]) * w
    return np.dstack([img, np.ones((n, n))])


def tex_rock(n=512, seed=5):
    rng = np.random.default_rng(seed)
    g = 0.35 + 0.45 * _noise(n, rng, 6)
    img = np.dstack([g * 0.62, g * 0.58, g * 0.55])
    return np.dstack([img, np.ones((n, n))])


def tex_snowroof(n=512, seed=6):
    rng = np.random.default_rng(seed)
    g = 0.86 + 0.12 * _noise(n, rng, 3)
    img = np.dstack([g * 0.96, g * 0.97, g])
    yy = np.linspace(0, 1, n)[:, None]
    ridge = ((yy * 10) % 1.0) < 0.05
    img[np.broadcast_to(ridge, (n, n))] *= 0.8
    return np.dstack([img, np.ones((n, n))])


def tex_blanket(n=128, seed=7):
    rng = np.random.default_rng(seed)
    g = 0.8 + 0.2 * _noise(n, rng, 3)
    return np.dstack([g * 0.35, g * 0.37, g * 0.30, np.ones((n, n))])


def tex_green(n=128, seed=8):
    rng = np.random.default_rng(seed)
    g = 0.85 + 0.15 * _noise(n, rng, 3)
    return np.dstack([g * 0.30, g * 0.36, g * 0.22, np.ones((n, n))])


def tex_water(n=256, seed=9):
    rng = np.random.default_rng(seed)
    g = 0.5 + 0.5 * _noise(n, rng, 4)
    img = np.dstack([0.02 + 0.05 * g, 0.04 + 0.07 * g, 0.08 + 0.10 * g])
    return np.dstack([img, np.full((n, n), 0.92)])


def tex_ice(n=512, seed=10):
    import icecrack
    try:
        rgb = np.asarray(icecrack.crack_texture(n, seed), float)
        if rgb.max() > 1.5:
            rgb = rgb / 255.0
        rgb = rgb[:, :, :3]
    except Exception:
        rng = np.random.default_rng(seed)
        g = 0.8 + 0.2 * _noise(n, rng, 3)
        rgb = np.dstack([g * 0.86, g * 0.90, g * 0.96])
    return np.dstack([rgb, np.ones((n, n))])


def tex_ruts(n=512, seed=11):
    """snow with two dark tyre ruts along u (the ice-track segment: u runs along the spline)"""
    rng = np.random.default_rng(seed)
    g = 0.84 + 0.14 * _noise(n, rng, 3)
    img = np.dstack([g * 0.90, g * 0.92, g * 0.97])
    yy = np.linspace(0, 1, n)[:, None]
    for c in (0.40, 0.60):                                       # the ruts at 40 % and 60 % across
        rut = np.abs(yy - c) < 0.035
        img[np.broadcast_to(rut, (n, n))] *= 0.62
    return np.dstack([img, np.ones((n, n))])


def tex_text(lines, size=(512, 256), bg=(0.80, 0.78, 0.70), fg=(0.10, 0.08, 0.08), font=FONT_B, pt=56, border=(0.6, 0.1, 0.1), seed=12):
    """a board with Cyrillic / Latin text (PIL + Arial, which has Cyrillic)"""
    from PIL import Image, ImageDraw, ImageFont
    W, H = size
    im = Image.new('RGB', (W, H), tuple(int(c * 255) for c in bg))
    dr = ImageDraw.Draw(im)
    if border:
        dr.rectangle([6, 6, W - 7, H - 7], outline=tuple(int(c * 255) for c in border), width=10)
    try:
        f = ImageFont.truetype(font, pt)
    except Exception:
        f = ImageFont.load_default()
    y = 30
    for ln in lines:
        bb = dr.textbbox((0, 0), ln, font=f)
        dr.text(((W - (bb[2] - bb[0])) / 2, y), ln, fill=tuple(int(c * 255) for c in fg), font=f)
        y += (bb[3] - bb[1]) + 18
    a = np.asarray(im, float) / 255.0
    rng = np.random.default_rng(seed)
    a *= (0.88 + 0.12 * _noise(max(W, H), rng, 3))[:H, :W, None]
    return np.dstack([a, np.ones((H, W))])


def tex_poster(kind, seed=13):
    """three 'Soviet' camp posters: red/cream block graphics with slogans (generated, not copied)"""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 256, 384
    rng = np.random.default_rng(seed + kind)
    im = Image.new('RGB', (W, H), (205, 190, 150))
    dr = ImageDraw.Draw(im)
    red = (170, 30, 25); black = (30, 25, 25)
    if kind == 1:
        dr.rectangle([0, 0, W, 120], fill=red)
        dr.polygon([(30, 300), (120, 150), (210, 300)], fill=black)
        dr.ellipse([95, 125, 145, 175], fill=black)
        title, sub = 'ТРУД', 'ПУТЬ К СВОБОДЕ'
    elif kind == 2:
        dr.rectangle([0, H - 110, W, H], fill=red)
        for k in range(5):
            dr.rectangle([25 + k * 42, 110, 50 + k * 42, 250], fill=black)
        dr.rectangle([20, 95, 236, 110], fill=black)
        title, sub = 'НЕ БОЛТАЙ!', 'ВРАГ СЛУШАЕТ'
    else:
        dr.rectangle([0, 0, W, H], fill=(60, 60, 70))
        dr.ellipse([48, 60, 208, 220], fill=(225, 225, 230))
        dr.polygon([(128, 60), (160, 140), (96, 140)], fill=red)
        title, sub = 'ДИСЦИПЛИНА', 'ПОРЯДОК. РАБОТА.'
    try:
        f1 = ImageFont.truetype(FONT_B, 40); f2 = ImageFont.truetype(FONT_B, 22)
    except Exception:
        f1 = f2 = ImageFont.load_default()
    for txt, f, y in ((title, f1, 20 if kind != 1 else 30), (sub, f2, H - 70 if kind != 2 else 60)):
        bb = dr.textbbox((0, 0), txt, font=f)
        dr.text(((W - (bb[2] - bb[0])) / 2, y), txt, fill=(240, 230, 210) if kind != 2 or y < 100 else (240, 230, 210), font=f)
    H = 512                                                # (10-13 in-game: 'mipmap texture not power of 2' fatal - drawn 2:3, stored 256x512)
    im = im.resize((W, H), Image.LANCZOS)
    a = np.asarray(im, float) / 255.0
    a *= (0.85 + 0.15 * _noise(H, rng, 3))[:H, :W, None]
    return np.dstack([a, np.ones((H, W))])


def tex_flat(rgb, n=32):
    return np.dstack([np.full((n, n), c) for c in rgb] + [np.ones((n, n))])


# ================================================================================================ the models
def _hsem():
    return SL._hsem_template()


def _model(groups_parts, coll_parts, hsem, glows=None, atta=None):
    """groups_parts = [(slot, [parts...])], coll_parts = [parts...] -> mef"""
    groups = []
    for slot, parts in groups_parts:
        P, T, N, U = merge(parts)
        groups.append(mefmesh.Group(P, U, T, slot, flags=0x1900, nrm=N))
    cP, cT, _, _ = merge(coll_parts)
    r = mefmesh.RigidModel(groups, SL._coll(cP, cT), hsem=hsem, glows=glows, atta=atta, typ=0)
    return r.to_mef(recompute_spheres=True, recompute_centres=True, rebuild_trees=True)


def build_barracks(hsem):
    """log barracks 18 x 7 m: walls 2.6 m, gable roof to 4.2 m, doorway on the +y long side (centre), plank floor,
    6 bunks inside (3 double bunks), a stove. Origin = floor centre, floor top at z 0.05."""
    L, Wd, H, t = 18.0, 7.0, 2.6, 0.22
    walls = []
    # long walls (y = +-Wd/2), the +y one with a 1.1 m doorway at x 0
    walls.append(box_m(-L / 2, -Wd / 2 - t, 0.0, L / 2, -Wd / 2, H))
    walls.append(box_m(-L / 2, Wd / 2, 0.0, -0.55, Wd / 2 + t, H))
    walls.append(box_m(0.55, Wd / 2, 0.0, L / 2, Wd / 2 + t, H))
    walls.append(box_m(-0.55, Wd / 2, 2.1, 0.55, Wd / 2 + t, H))         # lintel
    walls.append(box_m(-L / 2 - t, -Wd / 2 - t, 0.0, -L / 2, Wd / 2 + t, H))
    walls.append(box_m(L / 2, -Wd / 2 - t, 0.0, L / 2 + t, Wd / 2 + t, H))
    # gables (as stacked boxes narrowing up)
    for k in range(6):
        f = k / 6.0
        hw = (Wd / 2 + t) * (1 - f)
        for x0, x1 in ((-L / 2 - t, -L / 2), (L / 2, L / 2 + t)):
            walls.append(box_m(x0, -hw, H + f * 1.6, x1, hw, H + (f + 1 / 6.0) * 1.6))
    # roof: two slabs (thick boxes, slightly tilted via two steps of boxes would be ugly: use rotated quads)
    roof = []
    for sg in (1.0, -1.0):
        y_e, y_r = sg * (Wd / 2 + t + 0.5), 0.0
        z_e, z_r = H - 0.1, H + 1.7
        P = np.array([(-L / 2 - 0.6, y_e, z_e), (L / 2 + 0.6, y_e, z_e), (L / 2 + 0.6, y_r, z_r), (-L / 2 - 0.6, y_r, z_r)], float) * M
        n = np.array([0.0, sg * (z_r - z_e), abs(y_e - y_r)]); n /= np.linalg.norm(n)
        U = np.array([(0, 0), (L / 2.5, 0), (L / 2.5, 1.6), (0, 1.6)], float)
        T = SL._orient(P, np.array([(0, 1, 2), (0, 2, 3)]), np.tile(n, (4, 1)), np.tile(n, (2, 1)))
        roof.append((P, np.concatenate([T, T[:, [0, 2, 1]]]), np.tile(n, (4, 1)), U))
    floor = [box_m(-L / 2, -Wd / 2, -0.3, L / 2, Wd / 2, 0.05, uv=0.5)]
    bunks, stove = [], []
    for k, x in enumerate((-6.5, -2.5, 1.5, 5.5)):
        if k == 2:
            continue
        for z in (0.45, 1.35):
            bunks.append(box_m(x, -Wd / 2 + 0.1, z, x + 2.0, -Wd / 2 + 1.0, z + 0.18, uv=1.0))
        bunks.append(box_m(x, -Wd / 2 + 0.1, 0.0, x + 0.08, -Wd / 2 + 0.18, 1.6)); bunks.append(box_m(x + 1.92, -Wd / 2 + 0.1, 0.0, x + 2.0, -Wd / 2 + 0.18, 1.6))
        bunks.append(box_m(x, -Wd / 2 + 0.92, 0.0, x + 0.08, -Wd / 2 + 1.0, 1.6)); bunks.append(box_m(x + 1.92, -Wd / 2 + 0.92, 0.0, x + 2.0, -Wd / 2 + 1.0, 1.6))
    stove.append(box_m(1.0, 1.8, 0.05, 1.8, 2.6, 0.9, uv=1.0))
    stove.append(cyl_z(0.12, 0.9, 2.6, 8, 1.4, 2.2))
    groups = [(0, walls), (1, roof), (2, floor), (3, bunks), (4, stove)]
    coll = walls + floor + bunks + [stove[0]] + roof
    return _model(groups, coll, hsem)


def build_bunk(hsem):
    """a free-standing double bunk (prop for the guard barracks / office)"""
    parts = [box_m(0, 0, 0.45, 2.0, 0.9, 0.63), box_m(0, 0, 1.35, 2.0, 0.9, 1.53)]
    for x, y in ((0, 0), (1.92, 0), (0, 0.82), (1.92, 0.82)):
        parts.append(box_m(x, y, 0.0, x + 0.08, y + 0.08, 1.6))
    return _model([(0, parts)], parts, hsem)


def build_culvert(hsem):
    """concrete box drain 7 m long along y, inner 1.5 wide x 1.45 high, floor (ice) at z 0, open both ends"""
    Ln, wi, hi, t = 7.0, 1.5, 1.45, 0.25
    parts = [box_m(-wi / 2 - t, -Ln / 2, -0.3, -wi / 2, Ln / 2, hi + t),          # side walls
             box_m(wi / 2, -Ln / 2, -0.3, wi / 2 + t, Ln / 2, hi + t),
             box_m(-wi / 2 - t, -Ln / 2, hi, wi / 2 + t, Ln / 2, hi + t),          # roof slab
             box_m(-wi / 2, -Ln / 2, -0.3, wi / 2, Ln / 2, 0.0, uv=0.5)]           # floor (ice)
    # a torn grating leaning at the outer end
    bars = [box_m(-0.55 + 0.25 * k, -Ln / 2 - 0.35, 0.0, -0.5 + 0.25 * k, -Ln / 2 - 0.3, 1.3) for k in range(5)]
    return _model([(0, parts[:3]), (1, [parts[3]]), (2, bars)], parts + bars, hsem)


def build_wallgap(hsem):
    """a 5 m concrete wall piece standing on the culvert roof (1.7 m up), same style as the prison wall 305_01_1"""
    parts = [box_m(-2.5, -0.2, 1.7, 2.5, 0.2, 3.6)]
    wire = [cyl_axis(0.03, -2.5, 2.5, 'x', 6, at=(0.0, 3.75 + 0.08 * k)) for k in range(3)]
    return _model([(0, parts), (1, wire)], parts, hsem)


def build_headframe(hsem):
    """mine headframe: 4 steel legs to a 9 m crown with a sheave wheel, the shaft collar (5.8 m square opening with a
    0.6 m kerb) and a winch house box beside it. Origin = the collar's centre at ground level."""
    legs, crown, collar, house = [], [], [], []
    s0, s1 = 3.4, 1.2
    for sx in (-1, 1):
        for sy in (-1, 1):
            # a leg = 8 stacked boxes leaning inward
            for k in range(8):
                f0, f1 = k / 8.0, (k + 1) / 8.0
                x0 = sx * (s0 + (s1 - s0) * f0); x1 = sx * (s0 + (s1 - s0) * f1)
                y0 = sy * (s0 + (s1 - s0) * f0); y1 = sy * (s0 + (s1 - s0) * f1)
                legs.append(box_m(min(x0, x1) - 0.12, min(y0, y1) - 0.12, 9.0 * f0, max(x0, x1) + 0.12, max(y0, y1) + 0.12, 9.0 * f1))
            for k in (3, 6):
                z = 9.0 * k / 8.0; f = k / 8.0; xx = s0 + (s1 - s0) * f
                legs.append(box_m(-xx, sy * xx - 0.08, z, xx, sy * xx + 0.08, z + 0.16))
                legs.append(box_m(sx * xx - 0.08, -xx, z, sx * xx + 0.08, xx, z + 0.16))
    crown.append(box_m(-1.5, -1.5, 9.0, 1.5, 1.5, 9.3))
    crown.append(cyl_axis(1.1, -0.18, 0.18, 'y', 20, at=(0.0, 10.4)))        # the sheave wheel
    crown.append(box_m(-0.15, -0.5, 9.3, 0.15, 0.5, 10.4))
    crown.append(cyl_z(0.06, 0.0, 10.4, 6, 0.0, 0.0))                        # the cable
    for sg in (-1, 1):
        collar.append(box_m(-3.5, sg * 2.9, -0.2, 3.5, sg * 3.5, 0.6))
        collar.append(box_m(sg * 2.9, -2.9, -0.2, sg * 3.5, 2.9, 0.6))
    house.append(box_m(4.2, -2.5, 0.0, 8.0, 2.5, 3.0))
    house.append(box_m(4.0, -2.7, 3.0, 8.2, 2.7, 3.3))
    groups = [(0, legs + crown), (1, collar), (2, house)]
    return _model(groups, legs + collar + house + [crown[0]], hsem)


SHAFT_D = 23.4                                             # collar (ground) to the gallery floor


def build_shaft(hsem):
    """the shaft: timbered square tube, inner 5.8 x 5.8 m, from z 0.6 (collar top) down to z -SHAFT_D; at the bottom a
    3.2 m wide x 3 m high opening on BOTH y sides (+y: the adit to the river, -y: the cell). A 1.1 m railing round the
    collar on three sides, the open (-x) side gets the gate (a Door task). Origin = the collar centre at ground level."""
    wi, d, t = 5.8, SHAFT_D, 0.3
    parts = [box_m(-wi / 2 - t, -wi / 2 - t, -d, -wi / 2, wi / 2 + t, 0.6),
             box_m(wi / 2, -wi / 2 - t, -d, wi / 2 + t, wi / 2 + t, 0.6)]
    for sg in (1, -1):
        y0, y1 = (wi / 2, wi / 2 + t) if sg > 0 else (-wi / 2 - t, -wi / 2)
        parts += [box_m(-wi / 2, y0, -d + 3.0, wi / 2, y1, 0.6), box_m(-wi / 2, y0, -d, -1.6, y1, -d + 3.0),
                  box_m(1.6, y0, -d, wi / 2, y1, -d + 3.0)]
    floor = box_m(-wi / 2 - t, -wi / 2 - t, -d - 0.4, wi / 2 + t, wi / 2 + t, -d, uv=0.5)
    rail = [box_m(wi / 2 + t, -wi / 2 - t, 0.6, wi / 2 + t + 0.1, wi / 2 + t, 1.2),
            box_m(-wi / 2 - t, wi / 2 + t, 0.6, wi / 2 + t + 0.1, wi / 2 + t + 0.1, 1.2),
            box_m(-wi / 2 - t, -wi / 2 - t - 0.1, 0.6, wi / 2 + t + 0.1, -wi / 2 - t, 1.2)]
    beams = []
    for k in range(1, int(d // 3.0) + 1):
        z = -d + k * 3.0
        for sg in (-1, 1):
            beams.append(box_m(-wi / 2, sg * (wi / 2 - 0.15), z, wi / 2, sg * wi / 2, z + 0.25))
            beams.append(box_m(sg * (wi / 2 - 0.15), -wi / 2, z, sg * wi / 2, wi / 2, z + 0.25))
    return _model([(0, parts + beams + rail), (1, [floor])], parts + [floor] + rail, hsem)


def build_ramp(hsem):
    """a plank ramp up to a truck bed: 1.0 m wide, from the ground (y 0) up to 1.32 m at y 3.4, origin at its foot"""
    L, H = 3.4, 1.32
    ang = math.atan2(H, L)
    P, T, N, U = box_m(-0.5, 0.0, -0.06, 0.5, math.hypot(L, H), 0.0, uv=1.0)
    R = np.array([[1, 0, 0], [0, math.cos(ang), -math.sin(ang)], [0, math.sin(ang), math.cos(ang)]])
    P = P @ R.T; N = N @ R.T
    legs = [box_m(-0.45, L - 0.1, 0.0, -0.35, L, H), box_m(0.35, L - 0.1, 0.0, 0.45, L, H)]
    return _model([(0, [(P, T, N, U)] + legs)], [(P, T, N, U)] + legs, hsem)


def build_slhoff(hsem):
    """the searchlight head with the power off: the drum + a dark lens, no glow, no beam (fb_slh_1's shape)"""
    drum = SL._cylinder(0.21 * M, -0.28 * M, 0.24 * M, seg=18)
    back = SL._disc(0.21 * M, -0.28 * M)
    back = (back[0], back[1][:, [0, 2, 1]], -back[2], back[3])
    ears = SL._box((0, -0.02 * M, 0), (0.25 * M, 0.06 * M, 0.06 * M))
    lens = SL._disc(0.19 * M, 0.25 * M)
    return _model([(0, [drum, back, ears]), (1, [lens])], [drum, ears], hsem)


def build_cell(hsem):
    """'the hole': a rock-cut cell 4 x 3.2 m, 2.6 high, open doorway 1.3 wide on the -y side (the bars gate hangs there),
    a plank bed, a bucket, a lamp. Origin = doorway centre on the floor, the room extends +y."""
    wi, dp, h, t = 4.0, 3.2, 2.6, 0.5
    parts = [box_m(-wi / 2 - t, 0.0, -0.3, -wi / 2, dp + t, h + t),
             box_m(wi / 2, 0.0, -0.3, wi / 2 + t, dp + t, h + t),
             box_m(-wi / 2 - t, dp, -0.3, wi / 2 + t, dp + t, h + t),
             box_m(-wi / 2 - t, -t, -0.3, -0.65, 0.0, h + t),
             box_m(0.65, -t, -0.3, wi / 2 + t, 0.0, h + t),
             box_m(-0.65, -t, 2.2, 0.65, 0.0, h + t),
             box_m(-wi / 2 - t, -t, h, wi / 2 + t, dp + t, h + t),
             box_m(-wi / 2, -t, -0.3, wi / 2, dp + t, 0.0, uv=0.5)]
    bed = [box_m(wi / 2 - 0.9, 0.3, 0.35, wi / 2 - 0.05, 2.3, 0.48), box_m(wi / 2 - 0.9, 0.3, 0.0, wi / 2 - 0.8, 0.4, 0.35),
           box_m(wi / 2 - 0.15, 2.2, 0.0, wi / 2 - 0.05, 2.3, 0.35)]
    bucket = [cyl_z(0.16, 0.0, 0.3, 8, -wi / 2 + 0.4, dp - 0.4)]
    lamp = [box_m(-0.2, dp - 0.25, h - 0.35, 0.2, dp, h - 0.1)]
    glow = np.zeros(1, mefmesh.WOLG_DT)
    glow[0] = ((0.0, (dp - 0.3) * M, (h - 0.4) * M), 1200.0, 1.0, 0.9, 0.7, 0xABABABAB)
    return _model([(0, parts[:7]), (1, [parts[7]]), (2, bed + bucket), (3, lamp)], parts + bed + bucket, hsem, glows=glow)


def build_bars(hsem):
    """the cell gate for a Door task: 1.3 x 2.2 m of vertical bars, hinge at the origin (x 0), the leaf along +y"""
    parts = [box_m(0.0, 0.0, 0.0, 0.05, 1.3, 0.06), box_m(0.0, 0.0, 2.14, 0.05, 1.3, 2.2), box_m(0.0, 0.0, 1.05, 0.05, 1.3, 1.11)]
    for k in range(7):
        parts.append(box_m(0.005, 0.08 + k * 0.19, 0.0, 0.045, 0.12 + k * 0.19, 2.2))
    parts.append(box_m(0.0, 0.0, 0.0, 0.06, 0.06, 2.2)); parts.append(box_m(0.0, 1.24, 0.0, 0.06, 1.3, 2.2))
    return _model([(0, parts)], parts, hsem)


def build_generator(hsem):
    """diesel genset on a skid + exhaust + a cable spool + the switch panel on a post (origin = skid centre)"""
    skid = [box_m(-1.3, -0.65, 0.0, 1.3, 0.65, 0.12)]
    body = [box_m(-1.1, -0.5, 0.12, 0.3, 0.5, 1.15), cyl_axis(0.45, 0.3, 1.1, 'x', 14, at=(0.0, 0.62)),
            cyl_z(0.06, 1.15, 1.9, 6, -0.6, 0.2), box_m(-1.15, -0.55, 1.15, 0.35, 0.55, 1.22)]
    spool = [cyl_axis(0.45, -0.25, 0.25, 'y', 12, at=(1.9, 0.45)), cyl_axis(0.2, -0.3, 0.3, 'y', 8, at=(1.9, 0.45))]
    panel = [box_m(-1.9, -0.05, 0.0, -1.8, 0.05, 1.5), box_m(-2.1, -0.12, 1.0, -1.6, 0.0, 1.7)]
    return _model([(0, skid + body[0:1] + body[3:4]), (1, body[1:3] + panel), (2, spool)], skid + body + spool + panel, hsem)


def build_lamp(hsem, on=True):
    """concrete lamp post 5.5 m with a sodium lamp head (WOLG glow when on)"""
    post = [cyl_z(0.12, 0.0, 5.3, 8, 0.0, 0.0), box_m(-0.35, -0.35, -0.1, 0.35, 0.35, 0.3)]
    arm = [box_m(-0.06, 0.0, 5.2, 0.06, 1.2, 5.32), box_m(-0.22, 0.9, 5.05, 0.22, 1.5, 5.25)]
    lens = [slab(-0.18, 0.95, 0.18, 1.45, 5.05, uv=(1, 1), up=False)]
    glow = None
    if on:
        glow = np.zeros(1, mefmesh.WOLG_DT)
        glow[0] = ((0.0, 1.2 * M, 5.0 * M), 2400.0, 1.0, 0.78, 0.45, 0xABABABAB)      # sodium orange
    return _model([(0, post), (1, arm), (2 if on else 3, lens)], post + arm, hsem, glows=glow)


def build_sign(hsem):
    """gate board 2.6 x 0.9 m on two posts, top at 3.2 m"""
    posts = [box_m(-1.2, -0.08, 0.0, -1.04, 0.08, 3.2), box_m(1.04, -0.08, 0.0, 1.2, 0.08, 3.2)]
    board = [box_m(-1.3, -0.04, 2.25, 1.3, 0.04, 3.15)]
    P, T, N, U = board[0]
    # the +y face of the board carries the text: uv 0..1 across its face
    U = U.copy()
    for k in range(len(P)):
        if N[k][1] > 0.5 or N[k][1] < -0.5:
            U[k] = ((P[k][0] / M + 1.3) / 2.6, 1 - (P[k][2] / M - 2.25) / 0.9)
    return _model([(0, posts), (1, [(P, T, N, U)])], posts + board, hsem)


def build_poster(hsem):
    """a 0.6 x 0.85 m poster board (hangs on a wall: origin at its bottom centre, faces -y)"""
    P, T, N, U = box_m(-0.3, -0.02, 0.0, 0.3, 0.0, 0.85)
    U = U.copy()
    for k in range(len(P)):
        U[k] = ((P[k][0] / M + 0.3) / 0.6, 1 - P[k][2] / M / 0.85)
    return _model([(0, [(P, T, N, U)])], [(P, T, N, U)], hsem)


def build_keys(hsem):
    """a ring of three cell keys (pickup): 0.16 m across"""
    parts = []
    for k in range(10):
        a0, a1 = 2 * math.pi * k / 10, 2 * math.pi * (k + 1) / 10
        x0, y0, x1, y1 = 0.05 * math.cos(a0), 0.05 * math.sin(a0), 0.05 * math.cos(a1), 0.05 * math.sin(a1)
        parts.append(box_m(min(x0, x1) - 0.005, min(y0, y1) - 0.005, 0.0, max(x0, x1) + 0.005, max(y0, y1) + 0.005, 0.008))
    for k, a in enumerate((0.3, 0.9, 1.5)):
        c, s = math.cos(a), math.sin(a)
        parts.append(box_m(0.04 * c - 0.008, 0.04 * s - 0.03, 0.0, 0.04 * c + 0.1, 0.04 * s + 0.03, 0.006))
    return _model([(0, parts)], parts, hsem)


def build_icetrack(hsem):
    """the SplineObj segment: a snow slab with tyre ruts, x -21.2 .. 17.18 m (the same span as the Mission 12 track piece
    417_01_1, so the waypoints every 38.38 m join), 9 m wide, 4 cm thick"""
    x0, x1 = -21.2, 17.18
    P, T, N, U = box_m(x0, -4.5, -0.04, x1, 4.5, 0.0)
    U = U.copy()
    for k in range(len(P)):
        U[k] = ((P[k][0] / M - x0) / 38.38 * 4.0, (P[k][1] / M + 4.5) / 9.0)
    return _model([(0, [(P, T, N, U)])], [(P, T, N, U)], hsem)


def build_icehole(hsem):
    """broken ice: a 14 x 14 m sheet of dark water (z -0.08) with 14 tilted floes around the hole (origin = hole centre on
    the ice). No collision on the water (the sinking truck passes through), the floes collide."""
    water = [slab(-7, -7, 7, 7, -0.08, uv=(2, 2), up=True)]
    floes, rng = [], np.random.default_rng(3)
    for k in range(14):
        a = 2 * math.pi * k / 14 + rng.uniform(-0.1, 0.1)
        r = rng.uniform(4.5, 6.5)
        cx, cy = r * math.cos(a), r * math.sin(a)
        w, l = rng.uniform(1.2, 2.6), rng.uniform(1.8, 3.4)
        P, T, N, U = box_m(cx - w / 2, cy - l / 2, -0.25, cx + w / 2, cy + l / 2, 0.05, uv=0.3)
        tilt = rng.uniform(-0.35, 0.35)
        Rt = np.array([[1, 0, 0], [0, math.cos(tilt), -math.sin(tilt)], [0, math.sin(tilt), math.cos(tilt)]])
        c = np.array([cx * M, cy * M, 0.0])
        P = (P - c) @ Rt.T + c; N = N @ Rt.T
        floes.append((P, T, N, U))
    return _model([(0, water), (1, floes)], floes, hsem)


def build_icelid(hsem):
    """the ice over the break hole until it breaks: a 16 x 16 m slab, top at z 0.02 (a hair over the river ice)"""
    P, T, N, U = box_m(-8, -8, -0.3, 8, 8, 0.02, uv=0.12)
    return _model([(0, [(P, T, N, U)])], [(P, T, N, U)], hsem)


def build_slpost(hsem):
    """the searchlight post without its lamp head (fb_slb_1 shape minus the ATTA slot): the power-off variant"""
    post = SL._box((0, 0, SL.PIVOT_M * M / 2), (0.07 * M, 0.07 * M, SL.PIVOT_M * M / 2))
    plate = SL._box((0, 0, 0.02 * M), (0.28 * M, 0.28 * M, 0.02 * M))
    yoke = SL._box((0, 0, (SL.PIVOT_M - 0.12) * M), (0.26 * M, 0.05 * M, 0.04 * M))
    return _model([(0, [post, plate, yoke])], [post, plate], hsem)


TOWER_PLAT = 7.8                                          # the watchtower platform (m), the ladder 332_17_1 is 8.37 m


def build_tower(hsem):
    """a gulag watchtower: 4 timber legs (splayed), cross braces, a 4 x 4 m plank platform at TOWER_PLAT with a 1 m
    railing (open on the +y side for the ladder), 4 corner posts and a pyramid roof. Origin = ground centre."""
    H = TOWER_PLAT
    legs, brace = [], []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for k in range(6):
                f0, f1 = k / 6.0, (k + 1) / 6.0
                x0, x1 = sx * (2.3 - 0.5 * f0), sx * (2.3 - 0.5 * f1)
                y0, y1 = sy * (2.3 - 0.5 * f0), sy * (2.3 - 0.5 * f1)
                legs.append(box_m(min(x0, x1) - 0.11, min(y0, y1) - 0.11, H * f0, max(x0, x1) + 0.11, max(y0, y1) + 0.11, H * f1))
    for z in (2.2, 4.8):
        f = z / H; w = 2.3 - 0.5 * f
        for sg in (-1, 1):
            brace.append(box_m(-w, sg * w - 0.06, z, w, sg * w + 0.06, z + 0.14))
            brace.append(box_m(sg * w - 0.06, -w, z, sg * w + 0.06, w, z + 0.14))
    plat = [box_m(-2.0, -2.0, H - 0.18, 2.0, 2.0, H, uv=1.0)]
    rail = [box_m(-2.0, -2.0, H, 2.0, -1.92, H + 1.0), box_m(-2.0, -2.0, H, -1.92, 2.0, H + 1.0), box_m(1.92, -2.0, H, 2.0, 2.0, H + 1.0),
            box_m(-2.0, 1.92, H, -0.45, 2.0, H + 1.0), box_m(0.45, 1.92, H, 2.0, 2.0, H + 1.0)]
    posts = [box_m(sx * 1.9 - 0.07, sy * 1.9 - 0.07, H, sx * 1.9 + 0.07, sy * 1.9 + 0.07, H + 2.3) for sx in (-1, 1) for sy in (-1, 1)]
    roof = []
    apex = np.array([0.0, 0.0, (H + 3.3) * M])
    for k in range(4):
        a0, a1 = k * math.pi / 2 + math.pi / 4, (k + 1) * math.pi / 2 + math.pi / 4
        c0 = np.array([2.6 * math.sqrt(2) * math.cos(a0) / math.sqrt(2) * math.sqrt(2) * 0.71 * M, 2.6 * math.sin(a0) * M, (H + 2.2) * M])
        c0 = np.array([2.6 * math.copysign(1, math.cos(a0)) * M, 2.6 * math.copysign(1, math.sin(a0)) * M, (H + 2.2) * M])
        c1 = np.array([2.6 * math.copysign(1, math.cos(a1)) * M, 2.6 * math.copysign(1, math.sin(a1)) * M, (H + 2.2) * M])
        P = np.array([c0, c1, apex]); n = -np.cross(c1 - c0, apex - c0); n = n / np.linalg.norm(n)
        if n[2] < 0:
            n = -n
        T = SL._orient(P, np.array([(0, 1, 2)]), np.tile(n, (3, 1)), n[None, :])
        roof.append((P, np.concatenate([T, T[:, [0, 2, 1]]]), np.tile(n, (3, 1)), np.array([(0, 0), (2, 0), (1, 1.5)], float)))
    return _model([(0, legs + brace + posts), (1, plat + rail), (2, roof)], legs + plat + rail + posts, hsem)


def build_flare(hsem):
    """a burning smoke-flare canister (the smoke + glow are tasks)"""
    parts = [cyl_z(0.035, 0.0, 0.22, 8, 0.0, 0.0), box_m(-0.06, -0.02, 0.0, 0.06, 0.02, 0.02)]
    return _model([(0, parts)], parts, hsem)


# ================================================================================================ registration
TEXTURES = {
    'bi_logs': lambda: tex_logs(), 'bi_snowroof': lambda: tex_snowroof(), 'bi_planks': lambda: tex_planks(),
    'bi_blanket': lambda: tex_blanket(), 'bi_steel': lambda: tex_steel(), 'bi_concrete': lambda: tex_concrete(),
    'bi_rock': lambda: tex_rock(), 'bi_ice': lambda: tex_ice(), 'bi_water': lambda: tex_water(), 'bi_ruts': lambda: tex_ruts(),
    'bi_green': lambda: tex_green(), 'bi_rust': lambda: tex_steel(seed=9, base=(0.36, 0.22, 0.14)),
    'bi_lampon': lambda: tex_flat((1.0, 0.85, 0.55)), 'bi_lampoff': lambda: tex_flat((0.25, 0.25, 0.27)),
    'bi_sign': lambda: tex_text(['ИТЛ-7  «АМУРЛАГ»', 'ЗАПРЕТНАЯ ЗОНА', 'СТОЙ! СТРЕЛЯЮТ БЕЗ', 'ПРЕДУПРЕЖДЕНИЯ'], pt=44),
    'bi_post1': lambda: tex_poster(1), 'bi_post2': lambda: tex_poster(2), 'bi_post3': lambda: tex_poster(3),
    'bi_brass': lambda: tex_flat((0.75, 0.62, 0.3)), 'bi_red': lambda: tex_flat((0.7, 0.12, 0.1)),
    'bi_timber': lambda: tex_planks(seed=21, base=(0.36, 0.28, 0.18)),
}
ALPHA_TEX = {'bi_water'}
SLOTS = {
    'bi_barracks_1': ['bi_logs', 'bi_snowroof', 'bi_planks', 'bi_blanket', 'bi_steel'],
    'bi_bunk_1': ['bi_blanket'],
    'bi_culvert_1': ['bi_concrete', 'bi_ice', 'bi_rust'],
    'bi_wallgap_1': ['bi_concrete', 'bi_steel'],
    'bi_headframe_1': ['bi_steel', 'bi_concrete', 'bi_planks'],
    'bi_shaft_1': ['bi_timber', 'bi_rock'],
    'bi_cell_1': ['bi_rock', 'bi_rock', 'bi_planks', 'bi_lampon'],
    'bi_bars_1': ['bi_steel'],
    'bi_generator_1': ['bi_green', 'bi_steel', 'bi_timber'],
    'bi_lamp_1': ['bi_concrete', 'bi_steel', 'bi_lampon', 'bi_lampoff'],
    'bi_lampoff_1': ['bi_concrete', 'bi_steel', 'bi_lampon', 'bi_lampoff'],
    'bi_sign_1': ['bi_timber', 'bi_sign'],
    'bi_poster_1': ['bi_post1'], 'bi_poster_2': ['bi_post2'], 'bi_poster_3': ['bi_post3'],
    'bi_keys_1': ['bi_brass'],
    'bi_icetrack_1': ['bi_ruts'],
    'bi_icehole_1': ['bi_water', 'bi_ice'],
    'bi_flare_1': ['bi_red'],
    'bi_ramp_1': ['bi_timber'],
    'bi_slhoff_1': ['bi_steel', 'bi_lampoff'],
    'bi_icelid_1': ['bi_ice'],
    'bi_slpost_1': ['bi_steel'],
    'bi_tower_1': ['bi_timber', 'bi_planks', 'bi_snowroof'],
}
BUILDERS = {
    'bi_barracks_1': build_barracks, 'bi_bunk_1': build_bunk, 'bi_culvert_1': build_culvert, 'bi_wallgap_1': build_wallgap,
    'bi_headframe_1': build_headframe, 'bi_shaft_1': build_shaft, 'bi_cell_1': build_cell, 'bi_bars_1': build_bars,
    'bi_generator_1': build_generator, 'bi_lamp_1': lambda h: build_lamp(h, True), 'bi_lampoff_1': lambda h: build_lamp(h, False),
    'bi_sign_1': build_sign, 'bi_poster_1': build_poster, 'bi_poster_2': build_poster, 'bi_poster_3': build_poster,
    'bi_keys_1': build_keys, 'bi_icetrack_1': build_icetrack, 'bi_icehole_1': build_icehole, 'bi_flare_1': build_flare,
    'bi_ramp_1': build_ramp, 'bi_slhoff_1': build_slhoff, 'bi_icelid_1': build_icelid, 'bi_slpost_1': build_slpost, 'bi_tower_1': build_tower,
}
LOD_LIKE = {'bi_tower_1': '434_26_1', 'bi_barracks_1': '434_26_1', 'bi_headframe_1': '400_06_1', 'bi_shaft_1': '434_26_1', 'bi_icetrack_1': '417_01_1',
            'bi_icehole_1': '434_26_1', 'bi_lamp_1': '740_01_1', 'bi_lampoff_1': '740_01_1', 'bi_culvert_1': '740_01_1',
            'bi_cell_1': '434_26_1', 'bi_wallgap_1': '740_01_1', 'bi_sign_1': '740_01_1', 'bi_generator_1': '740_01_1'}


def build_all(names=None):
    hsem = _hsem()
    out = {}
    for nm in (names or NAMES):
        mf = BUILDERS[nm](hsem)
        probs = list(mefmesh.semantic_check(mf))
        if probs:
            raise ValueError('%s failed its checks: %s' % (nm, probs[:5]))
        out[nm] = mf
    return out


def add_models(overlay_dir, level_name, names=None, log=print):
    """register the models (+ textures, lod lines) in the overlay's manifest and banks"""
    game_root = os.path.normcase(os.path.realpath(wreck.GAME))
    try:
        inside = os.path.commonpath([game_root, os.path.normcase(os.path.realpath(overlay_dir))]) == game_root
    except ValueError:
        inside = False
    if inside:
        raise ValueError('refusing to write into the game folder: %s' % overlay_dir)
    paths = wreck._ensure_overlay(overlay_dir, level_name)
    m = mtp.read(paths['mtp'])
    names = list(names or NAMES)
    clash = [n for n in names if n in m['VNAM']]
    if clash:
        raise ValueError('models already in %s: %s' % (paths['mtp'], clash))
    meshes = build_all(names)
    need_tex = sorted({t for n in names for t in SLOTS[n]})
    form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
    have = {d.rstrip(b'\0').decode('latin1') for t, d, a in ch if t == b'NAME'}
    gtt = {}
    for tname in need_tex:
        if tname in m['TEXF']:
            gtt[tname] = next(i for i, (t_, pl) in enumerate(m['GTT']) if t_ == m['TEXF'].index(tname))
            continue
        img = TEXTURES[tname]()
        h_, w_ = img.shape[:2]
        if h_ & (h_ - 1) or w_ & (w_ - 1):                 # the engine dies on non power-of-2 mipmapped textures
            raise ValueError('texture %s is %dx%d - not a power of 2' % (tname, w_, h_))
        tb = wreck.tex_mode67(img) if tname in ALPHA_TEX else wreck.tex_mode2(img)
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
        m['INST'].append([len(m['MODS']) - 1, [gtt[t] for t in SLOTS[nm]]])
    out_tex = ilff.write(form, ch, hdr[1] or 4)
    out_mod = ilff.write(mform, mch, mhdr[1] or 4)
    out_mtp = mtp.write(m)
    for path, blob in ((paths['textures'], out_tex), (paths['models'], out_mod), (paths['mtp'], out_mtp)):
        tmp = path + '.bi.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    for nm in names:
        wreck._lod_entry(overlay_dir, LOD_LIKE.get(nm, '740_01_1'), nm, level_name)
    b2 = wreck.Bank(paths['mtp'], paths['models'], paths['textures'])
    probs = []
    for nm in names:
        if b2.models.get(nm) is None:
            probs.append('%s not in the model bank' % nm)
        if b2.res.get(nm) is None:
            probs.append('%s does not resolve' % nm)
    if set(x.lower() for x in b2.m['MODS']) - set(b2.models):
        probs.append('MODS entries without a mesh')
    if set(b2.m['TEXF']) - set(b2.tex):
        probs.append('TEXF entries without a texture')
    log('biprefabs: %d models (%s), %d textures, problems %s' % (len(names), ', '.join('%s %d tris' % (n, int(meshes[n].hsem['n_rfaces'])) for n in names),
                                                                 len(need_tex), probs or 'none'))
    assert not probs, probs
    return dict(models=names, textures=need_tex)


def preview(out_png, names=None):
    """offline pictures of the models (tools/mefrender) -> contact sheet"""
    import mefrender, igitex
    from PIL import Image, ImageDraw
    meshes = build_all(names)
    tiles = []
    for nm, mf in meshes.items():
        r = mefmesh.RigidModel.from_mef(mf)
        sc = mefrender.Scene()
        mats = {}
        for g in r.groups:
            tname = SLOTS[nm][g.tex] if g.tex < len(SLOTS[nm]) else None
            if g.tex not in mats:
                img = TEXTURES[tname]() if tname else None
                mats[g.tex] = sc.material(img, color=(0.6, 0.6, 0.6), alpha=(0.9 if tname in ALPHA_TEX else 1.0))
            sc.add_tris(g.pos[g.tris], g.nrm[g.tris], g.uv[g.tris], mats[g.tex], double=True)
        P = np.concatenate([t.reshape(-1, 3) for t in sc.P])
        lo, hi = P.min(0), P.max(0); c = (lo + hi) / 2; rad = float(np.linalg.norm(hi - lo) / 2) + 1.0
        sc.add_ground(z=float(lo[2]), half=rad * 3, color=(0.80, 0.82, 0.86))
        b, e = math.radians(35), math.radians(22)
        d = rad / math.tan(math.radians(20)) * 1.05
        eye = c + np.array([math.sin(b) * math.cos(e), -math.cos(b) * math.cos(e), math.sin(e)]) * d
        tiles.append((nm, sc.render(eye, c, size=(480, 320), fov=40, ss=1)))
    cols = 4; W, H = 480, 320
    rows = (len(tiles) + cols - 1) // cols
    sh = Image.new('RGB', (cols * W, rows * (H + 18)), 'black')
    dr = ImageDraw.Draw(sh)
    for i, (label, im) in enumerate(tiles):
        x, y = (i % cols) * W, (i // cols) * (H + 18)
        sh.paste(im.convert('RGB'), (x, y + 18)); dr.text((x + 4, y + 3), label, fill='yellow')
    sh.save(out_png)
    return out_png


if __name__ == '__main__':
    print(preview(sys.argv[1] if len(sys.argv) > 1 else 'biprefabs.png', sys.argv[2].split(',') if len(sys.argv) > 2 else None))
