"""jrmodels - the NEW models of Operation Joyride (ART, WP-D, 2026-10-30), built with tools/modelkit (vertex-lit type 0, the
proven Black Ice path), every one with its own lod row (lod_rows()). Frames: z up, metres in the helpers, origin on the
ground / floor unless noted, the FRONT (use side, text side) faces +y. Names all end _1 (a VNAM ending _2 is the
engine's LOD 2 of the _1 name).

  battery   jr_sam_1   SAM launcher: 2-axle trailer, outrigger jacks, turntable, a launch rail pitched RAIL_PITCH to +y
            jr_mis_1   the missile on the rail (cold); jr_misf_1 the same in flight (motor glow) - origin = its centre, nose +y
            jr_fcc_1   fire-control console with the LAUNCH KEYSWITCH (front +y, screens glow), desk 0.95 m
            jr_key_1   the launch key on a red tag (walk-over pickup model, 0.24 m)
  pad one   jr_grid_1  30 x 30 m hover-grid deck, top z 0 (0.2 m thick): grating, yellow VTOL circle, a big '1', tie-downs
            jr_stand_1 yellow boarding stair (static, NEVER a Door): flight rising +y to a platform at STAND_TOP; the jet
                       side (+y end) open; collision = smooth wedge + platform + rails (Last Light recipe, 32 deg)
            jr_tug_1   tow tractor; jr_gpu_1 ground power cart with 2 work-light glows (and the SHOBI noclip panel sealed
                       inside its body); jr_chock_1 wheel chocks; jr_hose_1 a fuel hose coil
  base      jr_relay_1 field radio set (front +y, origin = its bottom on a table)   jr_brk_1 breaker cabinet + red wheel
            jr_cul_1   culvert: headwall + 10 m box (1.4 x 1.4 m clear) + a BENT grate at the inlet (y 0 = the inlet face)
            jr_pal_1   pallet steps (4 steps to 1.8 m, rising +y)   jr_cage_1 safety cage for a 24.1 m ladder (wall at -y)
            jr_zip_1   zip-line start platform (top ZIP_TOP) + A-frame anchor, the wire start at ZIP_GRAB (local)
            jr_tent_1  army tent 4.6 x 4.6 m   jr_pa_1 PA horns on a 5.5 m pole   jr_paw_1 PA horns on a wall bracket
            jr_rwl_1 / jr_rwd_1  runway edge lamp lit / dark   jr_thr_1 / jr_thd_1  threshold light bar lit / dark (green)
  signs     jr_gate_1 'СОКОЛ-9' gate board   jr_stop_1 STOP + 'ПРЕДЪЯВИ ПРОПУСК'   jr_nosm_1 'НЕ КУРИТЬ / NO SMOKING'
            jr_blast_1 'ОПАСНО! РЕАКТИВНАЯ СТРУЯ / DANGER JET BLAST'   jr_desc_1 'АВАРИЙНЫЙ СПУСК'   jr_shut_1 'ЗАКРЫТО'
            jr_chk_1 the JSF checklist board (Russian + English)   jr_kfal_1 the Kestrel falcon panel
            jr_su27_1 Shrike's framed photo: his Su-27 on a rainy runway, 'My Sukhoi. Taken by IGI.'
  wall plates (jr_nosm_1, jr_desc_1, jr_shut_1, jr_chk_1, jr_kfal_1, jr_su27_1, jr_paw_1): origin = the wall surface,
  the plate stands 2 cm proud of it facing +y (place with gamma = the wall's outward normal).

    import modelkit, jrmodels; LIB = modelkit.Library(); jrmodels.add_models(LIB)    # or the builder hook add(B, LIB)
    python -P tools/jrmodels.py preview [out_dir]                                     # contact sheets in work/joyride/art
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import mefmesh
import biprefabs as BP
import modelkit as MK
import jrjet as JJ

M = 4096.0
FONT_B = r'C:\Windows\Fonts\arialbd.ttf'
FONT_R = r'C:\Windows\Fonts\arial.ttf'
FONT_C = r'C:\Windows\Fonts\cour.ttf'
box, cyl, cylx, hull, panel = BP.box_m, BP.cyl_z, BP.cyl_axis, MK.hull_m, MK.panel

# ---------------------------------------------------------------------------------------------- published dimensions
RAIL_PITCH = math.radians(32.0)      # launch rail elevation (rad), the rail points along +y
RAIL_PIVOT = (0.0, -0.6, 2.35)       # rail pivot over the turntable (launcher frame, m)
RAIL_LEN = 7.2                       # rail length from the pivot toward +y (m)
MIS_LEN, MIS_R = 6.2, 0.26           # missile body length / radius (m)
MIS_ON_RAIL = 2.9                    # missile centre along the rail from the pivot (m)
MIS_LIFT = 0.30                      # ... and over the rail axis (the booster r 0.35 rides on the beams' tops at -0.07)
GRID_HALF = 15.0                     # jr_grid_1 half size (m); top at z 0, 0.2 m thick
STAND_TOP = JJ.ORIGIN_Z + JJ.STAIR_TOP   # boarding stair platform top (m): the jet frame's z 0 = deck + 2.75
STAND_W, STAND_DEPTH = 1.40, JJ.STAND_DEPTH   # platform width (x) / depth (y, toward the jet; jrjet places it)
STAND_SLOPE = math.radians(32.0)
ZIP_TOP = 1.0                        # zip platform top (m)
ZIP_GRAB = (0.0, 1.45, ZIP_TOP + 1.85)   # the wire's start point (local m): <= 2 m over the floor (owner zip rule 12)
CUL_W, CUL_H, CUL_LEN = 1.4, 1.4, 10.0   # culvert clear width / height / length (m)
CAGE_H = 24.1                        # 400_13_1 top deck height (m)
PAL_STEP, PAL_N = 0.38, 7            # pallet step rise (m) x steps: 2.66 m = a 2.6 m container top (stack a 2nd set on it
                                     # for the 5.3 m two-high stack); 0.38 m < navgen's 0.41 m climb
FCC_DESK = 0.95                      # console desk height (m)
KEYSWITCH = (0.0, 0.33, 1.06)        # the keyswitch on jr_fcc_1 (local m): the 'console' use target


def sam_rail(pos, yaw):
    """world geometry of a placed jr_sam_1 (pos = its origin, world units; yaw = its gamma): -> dict(base, tip, mis,
    yaw, pitch) world units / radians: the rail pivot, the rail tip, the missile centre on the rail (place jr_mis_1 there
    with gamma = yaw and alpha = +RAIL_PITCH: alpha > 0 tips +y UP - navgen.rot = rz @ ry @ rx, L32's SAM path node 3748
    climbs with alpha +0.305, INT 17:30)"""
    c, s = math.cos(yaw), math.sin(yaw)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
    d = np.array([0.0, math.cos(RAIL_PITCH), math.sin(RAIL_PITCH)])
    piv = np.asarray(RAIL_PIVOT, float)
    p = np.asarray(pos, float)
    w = lambda q: tuple(float(x) for x in (p + R @ (np.asarray(q, float) * M)))
    up = np.array([0.0, -math.sin(RAIL_PITCH), math.cos(RAIL_PITCH)])           # (the rail's up normal)
    return dict(base=w(piv), tip=w(piv + d * RAIL_LEN), mis=w(piv + d * MIS_ON_RAIL + up * MIS_LIFT), yaw=float(yaw),
                pitch=float(RAIL_PITCH))


# ================================================================================================ geometry helpers
def beam(a, b, w=0.1, h=None):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a; L = np.linalg.norm(d); d = d / L
    up = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.95 else np.array([1.0, 0.0, 0.0])
    s = np.cross(d, up); s /= np.linalg.norm(s); u = np.cross(s, d)
    h = w if h is None else h
    return hull([p + s * sx * w / 2 + u * sy * h / 2 for p in (a, b) for sx in (-1, 1) for sy in (-1, 1)], uv=0.5)


def tube(a, b, r, seg=10):
    """a round tube between two points (metres) -> part (convex)"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a; d = d / np.linalg.norm(d)
    up = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.95 else np.array([1.0, 0.0, 0.0])
    s = np.cross(d, up); s /= np.linalg.norm(s); u = np.cross(s, d)
    ring = [s * math.cos(t) * r + u * math.sin(t) * r for t in np.linspace(0, 2 * math.pi, seg, endpoint=False)]
    return hull([a + q for q in ring] + [b + q for q in ring], uv=0.6)


def wheel_x(r, w, cx, cy, cz, seg=14):
    """a wheel turning about x -> (tyre part, hub part)"""
    return cylx(r, cx - w / 2, cx + w / 2, 'x', seg, at=(cy, cz)), cylx(r * 0.55, cx - w / 2 - 0.01, cx + w / 2 + 0.01, 'x', 8, at=(cy, cz))


def rot_part(part, R, t=(0, 0, 0)):
    P, T_, N, U = part
    return (P @ R.T + np.asarray(t, float) * M, T_, N @ R.T, U)


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def glow(*items):
    """[(pos m, size, (r, g, b))] -> WOLG records (size in model units: 2400 = a sodium street lamp)"""
    g = np.zeros(len(items), mefmesh.WOLG_DT)
    for k, (p, size, col) in enumerate(items):
        g[k] = (tuple(float(c) * M for c in p), float(size), col[0], col[1], col[2], 0xABABABAB)
    return g


def plate(w, h, d=0.03, stand=0.02):
    """a wall plate: the back on the wall (y 0), the front face (+y) at stand + d, the text panel on it -> (plate, face)"""
    pl = box(-w / 2, stand, -h / 2, w / 2, stand + d, h / 2)
    face = panel((0.0, stand + d + 0.003, 0.0), (-1, 0, 0), (0, 0, 1), w * 0.97, h * 0.97)
    return pl, face


# ================================================================================================ textures (float RGBA)
def _rng(s):
    return np.random.default_rng(s)


def tex_paint(rgb, n=128, seed=1, grime=0.12, chips=0.0):
    rng = _rng(seed)
    g = (1 - grime) + grime * BP._noise(n, rng, 4)
    img = np.dstack([np.full((n, n), c) * g for c in rgb] + [np.ones((n, n))])
    if chips:
        ch_ = BP._noise(n, rng, 5) > 1 - chips
        img[ch_, :3] = img[ch_, :3] * 0.5 + 0.2
    img[:, :1, :3] *= 0.8; img[:1, :, :3] *= 0.8
    return np.clip(img, 0, 1)


def _pil(w, h, bg):
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (w, h), tuple(int(c * 255) for c in bg))
    return im, ImageDraw.Draw(im)


def _font(path, pt):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(path, pt)
    except Exception:
        return ImageFont.load_default()


def _centre_text(dr, W, y, txt, f, fill):
    bb = dr.textbbox((0, 0), txt, font=f)
    dr.text(((W - (bb[2] - bb[0])) / 2 - bb[0], y), txt, fill=fill, font=f)
    return bb[3] - bb[1]


def _arr(im, seed=0, grime=0.10):
    a = np.asarray(im, float) / 255.0
    if grime:
        n = max(a.shape[:2])
        g = (1 - grime) + grime * BP._noise(n, _rng(seed), 3)[:a.shape[0], :a.shape[1]]
        a = a * g[..., None]
    return np.dstack([np.clip(a, 0, 1), np.ones(a.shape[:2])])


def tex_sign(lines, size=(512, 256), bg=(0.92, 0.91, 0.86), border=(0.70, 0.08, 0.06), bw=14, seed=7, icon=None):
    """lines = [(text, pt, rgb, bold)]; icon 'hazard' (yellow/black diagonal frame) | 'nosmoke' | 'arrow' | 'star'"""
    W, H = size
    im, dr = _pil(W, H, bg)
    if icon == 'hazard':
        for k in range(-H, W + H, 36):
            dr.polygon([(k, 0), (k + 18, 0), (k + 18 - H, H), (k - H, H)], fill=(20, 18, 16))
        dr.rectangle([bw * 2, bw * 2, W - bw * 2, H - bw * 2], fill=tuple(int(c * 255) for c in bg))
    elif border:
        dr.rectangle([bw // 2, bw // 2, W - bw // 2 - 1, H - bw // 2 - 1], outline=tuple(int(c * 255) for c in border), width=bw)
    x_text = 0
    if icon == 'nosmoke':
        r = int(H * 0.36); cx, cy = int(H * 0.5), H // 2
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(200, 20, 16), width=max(8, r // 5))
        dr.rectangle([cx - r * 0.6, cy - r * 0.12, cx + r * 0.45, cy + r * 0.12], fill=(240, 240, 235), outline=(30, 30, 30), width=2)
        dr.rectangle([cx + r * 0.30, cy - r * 0.12, cx + r * 0.45, cy + r * 0.12], fill=(210, 120, 40))
        for k in range(3):
            dr.arc([cx + r * 0.35 + k * 6, cy - r * 0.75, cx + r * 0.55 + k * 6, cy - r * 0.2], 200, 340, fill=(90, 90, 90), width=3)
        dr.line([(cx - r * 0.7, cy - r * 0.7), (cx + r * 0.7, cy + r * 0.7)], fill=(200, 20, 16), width=max(8, r // 5))
        x_text = int(H * 0.9)
    if icon == 'arrow':
        cx, cy = int(W * 0.84), H // 2
        dr.polygon([(cx - 50, cy - 26), (cx + 10, cy - 26), (cx + 10, cy - 52), (cx + 62, cy), (cx + 10, cy + 52), (cx + 10, cy + 26), (cx - 50, cy + 26)],
                   fill=(245, 245, 240))
    if icon == 'star':
        cx, cy, r = int(H * 0.5), H // 2, int(H * 0.32)
        pts = [(cx + (r if k % 2 == 0 else r * 0.42) * math.cos(-math.pi / 2 + k * math.pi / 5),
                cy + (r if k % 2 == 0 else r * 0.42) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)]
        dr.polygon(pts, fill=(200, 24, 20), outline=(250, 220, 120))
        x_text = int(H * 0.85)
    margin = (bw * 2 if (border or icon == 'hazard') else 0) + 12
    x0_ = x_text or margin
    x1_ = int(W * 0.70) if icon == 'arrow' else W - margin
    fitted = []
    for t, pt, c, b in lines:                                  # shrink each line until it fits between x0_ and x1_
        while pt > 10:
            f = _font(FONT_B if b else FONT_R, pt)
            bb = dr.textbbox((0, 0), t, font=f)
            if bb[2] - bb[0] <= x1_ - x0_:
                break
            pt -= 2
        fitted.append((t, f, c, bb))
    gap = 10
    tot = sum(bb[3] - bb[1] for t, f, c, bb in fitted) + gap * (len(fitted) - 1)
    while tot > H - 2 * margin and gap > 2:
        gap -= 2; tot = sum(bb[3] - bb[1] for t, f, c, bb in fitted) + gap * (len(fitted) - 1)
    y = (H - tot) / 2
    for t, f, c, bb in fitted:
        dr.text((x0_ + (x1_ - x0_ - (bb[2] - bb[0])) / 2 - bb[0], y - bb[1]), t, fill=tuple(int(q * 255) for q in c), font=f)
        y += bb[3] - bb[1] + gap
    return _arr(im, seed)


def tex_grid(n=1024, seed=31):
    """jr_grid_1 top: steel hover-grid (0.5 m grating) on 30 m, a yellow 20 m circle, a white '1', yellow tie-downs, red/
    white edge band, 'VTOL'"""
    from PIL import Image, ImageDraw
    rng = _rng(seed)
    px = n / 30.0
    base = 0.33 + 0.06 * BP._noise(n, rng, 5)
    img = np.dstack([base * 0.98, base, base * 1.02])
    yy, xx = np.mgrid[0:n, 0:n]
    step = int(round(0.5 * px))
    img[((xx % step) < 2) | ((yy % step) < 2)] *= 0.62
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype('u1'))
    dr = ImageDraw.Draw(im)
    c = n / 2
    for r_m, w_m in ((10.0, 0.45), (9.2, 0.15)):
        r = r_m * px
        dr.ellipse([c - r, c - r, c + r, c + r], outline=(214, 176, 26), width=max(2, int(w_m * px)))
    f = _font(FONT_B, int(9.0 * px))
    bb = dr.textbbox((0, 0), '1', font=f)
    dr.text((c - (bb[2] - bb[0]) / 2 - bb[0], c - (bb[3] - bb[1]) / 2 - bb[1]), '1', fill=(232, 232, 226), font=f)
    f2 = _font(FONT_B, int(1.6 * px))
    for txt, yy_ in (('VTOL', c + 11.5 * px), ('ПЛОЩАДКА 1', c - 13.2 * px)):
        bb = dr.textbbox((0, 0), txt, font=f2)
        dr.text((c - (bb[2] - bb[0]) / 2 - bb[0], yy_ - (bb[3] - bb[1]) / 2 - bb[1]), txt, fill=(214, 176, 26), font=f2)
    for a in range(8):                                         # tie-down rings
        x = c + 6.5 * px * math.cos(a * math.pi / 4); y = c + 6.5 * px * math.sin(a * math.pi / 4)
        dr.ellipse([x - 0.25 * px, y - 0.25 * px, x + 0.25 * px, y + 0.25 * px], outline=(214, 176, 26), width=3)
    e = int(0.6 * px)                                          # red / white edge band
    for k in range(0, n, int(2 * px)):
        col = (190, 30, 26) if (k // int(2 * px)) % 2 == 0 else (225, 225, 220)
        for rect in ((k, 0, k + int(2 * px), e), (k, n - e, k + int(2 * px), n), (0, k, e, k + int(2 * px)), (n - e, k, n, k + int(2 * px))):
            dr.rectangle(rect, fill=col)
    a = np.asarray(im, float) / 255.0
    a *= (0.88 + 0.12 * BP._noise(n, rng, 3))[..., None]           # soot + tyre marks
    burn = np.clip(1 - np.hypot(xx - c, yy - c) / (6 * px), 0, 1) ** 1.5 * 0.35
    a *= (1 - burn)[..., None]
    return np.dstack([np.clip(a, 0, 1), np.ones((n, n))])


def tex_console(seed=41):
    """jr_fcc_1 sloped panel: two round radar scopes (green phosphor), a target table, rows of lamps, the KEYSWITCH plate
    (red ring, 'ПУСК'), Cyrillic labels"""
    W, H = 512, 256
    im, dr = _pil(W, H, (0.30, 0.34, 0.31))
    for cx in (90, 422):
        dr.ellipse([cx - 70, 30, cx + 70, 170], fill=(10, 22, 12), outline=(20, 20, 20), width=8)
        for r in (20, 40, 60):
            dr.ellipse([cx - r, 100 - r, cx + r, 100 + r], outline=(40, 150, 70), width=1)
        dr.line([(cx, 100), (cx + 52, 62)], fill=(120, 255, 150), width=3)
        dr.ellipse([cx + 20, 70, cx + 26, 76], fill=(200, 255, 200))
    dr.rectangle([196, 30, 316, 120], fill=(14, 16, 14), outline=(10, 10, 10), width=4)
    fC = _font(FONT_C, 13)
    for k, t in enumerate(('ЦЕЛЬ 1  --', 'ЦЕЛЬ 2  --', 'КАНАЛ  4', 'ГОТОВ  ДА')):
        dr.text((204, 38 + k * 19), t, fill=(60, 230, 110), font=fC)
    for k in range(10):                                         # lamp rows
        col = [(220, 40, 30), (240, 200, 40), (60, 220, 90)][k % 3]
        dr.ellipse([30 + k * 47, 196, 46 + k * 47, 212], fill=col, outline=(20, 20, 20), width=2)
    dr.ellipse([226, 136, 286, 196], fill=(150, 20, 18), outline=(30, 30, 30), width=4)  # keyswitch ring
    dr.ellipse([246, 156, 266, 176], fill=(40, 40, 40))
    dr.rectangle([253, 150, 259, 182], fill=(200, 200, 190))
    f = _font(FONT_B, 18)
    dr.text((230, 112), 'ПУСК', fill=(235, 230, 210), font=f)
    dr.text((24, 226), 'ПИТАНИЕ', fill=(220, 215, 200), font=_font(FONT_B, 14))
    dr.text((380, 226), 'БАТАРЕЯ 4', fill=(220, 215, 200), font=_font(FONT_B, 14))
    return _arr(im, seed, 0.06)


def tex_radio(seed=42):
    W, H = 256, 128
    im, dr = _pil(W, H, (0.27, 0.31, 0.25))
    dr.rectangle([12, 12, 120, 58], fill=(12, 14, 12), outline=(20, 20, 20), width=3)
    dr.text((18, 22), '145.250', fill=(255, 160, 40), font=_font(FONT_C, 22))
    for k, x in enumerate((150, 196, 236)):
        dr.ellipse([x - 16, 20, x + 16, 52], fill=(30, 30, 30), outline=(80, 80, 80), width=3)
        dr.line([(x, 36), (x + 10 * math.cos(k + 0.5), 36 - 10 * math.sin(k + 0.5))], fill=(220, 220, 220), width=3)
    for k in range(8):
        dr.rectangle([14 + k * 28, 76, 34 + k * 28, 96], fill=(35, 35, 35), outline=(90, 90, 90))
    dr.text((14, 104), 'Р-159  СВЯЗЬ', fill=(220, 220, 205), font=_font(FONT_B, 14))
    return _arr(im, seed, 0.08)


def tex_checklist(seed=43):
    W, H = 256, 512
    im, dr = _pil(W, H, (0.90, 0.89, 0.84))
    dr.rectangle([0, 0, W, 40], fill=(40, 52, 40))
    dr.text((10, 8), 'JSF-97  ЧЕК-ЛИСТ', fill=(240, 236, 220), font=_font(FONT_B, 20))
    rows = ['1  ФОНАРЬ - ЗАКРЫТ  / CANOPY', '2  ПИТАНИЕ - ВКЛ  / BATT ON', '3  ДВС - ЗАПУСК  / ENG START', '4  ВЕНТИЛЯТОР  / LIFT FAN',
            '5  СОПЛО 90  / NOZZLE 90', '6  ВЗЛЕТ ВЕРТ.  / VTOL', '7  ШАССИ - УБР.  / GEAR UP', '8  ПЕРЕХОД  / TRANSITION',
            '9  КУРС 180  / HDG 180']
    f = _font(FONT_R, 14)
    for k, t in enumerate(rows):
        y = 56 + k * 46
        dr.text((10, y), t, fill=(30, 30, 30), font=f)
        dr.line([(10, y + 30), (W - 10, y + 30)], fill=(150, 150, 140), width=1)
        if k < 4:
            dr.text((W - 28, y - 4), 'v', fill=(170, 30, 25), font=_font(FONT_B, 22))
    dr.text((10, H - 40), 'ВЫШКА УЧИТ - САМОЛЕТ ЛЕТИТ', fill=(140, 30, 25), font=_font(FONT_B, 13))
    return _arr(im, seed, 0.08)


def tex_falcon(seed=44):
    W = H = 512
    im, dr = _pil(W, H, (0.14, 0.14, 0.15))
    dr.ellipse([46, 46, 466, 466], fill=(176, 150, 100), outline=(220, 200, 150), width=10)
    cx, cy, k = 256, 240, 170
    body = [(cx, cy - 0.55 * k), (cx + 0.18 * k, cy - 0.1 * k), (cx + 0.95 * k, cy - 0.45 * k), (cx + 0.35 * k, cy + 0.15 * k),
            (cx + 0.12 * k, cy + 0.75 * k), (cx, cy + 0.55 * k), (cx - 0.12 * k, cy + 0.75 * k), (cx - 0.35 * k, cy + 0.15 * k),
            (cx - 0.95 * k, cy - 0.45 * k), (cx - 0.18 * k, cy - 0.1 * k)]
    dr.polygon(body, fill=(24, 22, 20))
    dr.ellipse([cx - 0.13 * k, cy - 0.70 * k, cx + 0.13 * k, cy - 0.44 * k], fill=(24, 22, 20))
    f = _font(FONT_B, 54)
    _centre_text(dr, W, 392, 'KESTREL', f, (24, 22, 20))
    return _arr(im, seed, 0.06)


def tex_su27(seed=45):
    """Shrike's photo, painted (not a copy of anything): an Su-27 silhouette on a wet dusk runway, runway lights, the
    caption strip 'My Sukhoi. Taken by IGI.' on a brass plate under the print"""
    from PIL import Image, ImageDraw, ImageFilter
    W, H = 512, 512
    im = Image.new('RGB', (W, H), (40, 36, 30))
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, W, H], fill=(68, 50, 32))                               # the wooden frame
    px0, py0, px1, py1 = 34, 34, W - 34, 370
    for y in range(py0, py1):                                                  # sky: grey rain clouds into a low orange dusk
        f = (y - py0) / (py1 - py0)
        col = (int(70 + 80 * f ** 2), int(74 + 40 * f ** 2), int(84 + 4 * f))
        dr.line([(px0, y), (px1, y)], fill=col)
    hz = py0 + int(0.62 * (py1 - py0))
    for y in range(hz, py1):                                                   # wet runway (reflective)
        f = (y - hz) / (py1 - hz)
        dr.line([(px0, y), (px1, y)], fill=(int(46 + 30 * (1 - f)), int(46 + 22 * (1 - f)), int(50 + 10 * (1 - f))))
    for k in range(-6, 7):                                                     # runway edge lights in perspective
        x = W / 2 + k * 30
        dr.ellipse([x - 3, hz + 6, x + 3, hz + 10], fill=(255, 210, 120))
    for k in range(1, 6):
        for sx in (-1, 1):
            x = W / 2 + sx * (40 + k * k * 9); y = hz + 8 + k * 12
            dr.ellipse([x - 4, y - 3, x + 4, y + 3], fill=(255, 215, 130))
    cx, cy, s = W / 2, hz - 34, 1.0                                            # Su-27 side silhouette: long nose, two fins
    pts = [(-190, 8), (-150, 0), (-60, -6), (40, -8), (120, -10), (175, -4), (205, 2), (175, 8), (90, 14), (-120, 16), (-185, 14)]
    dr.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=(58, 66, 74))
    dr.polygon([(cx + x, cy + y) for x, y in ((100, -10), (150, -62), (178, -62), (165, -8))], fill=(52, 60, 68))      # fins
    dr.polygon([(cx + x, cy + y) for x, y in ((112, -10), (160, -50), (176, -50), (170, -9))], fill=(44, 52, 60))
    dr.polygon([(cx + x, cy + y) for x, y in ((-120, -6), (-95, -20), (-60, -21), (-50, -6))], fill=(30, 36, 44))      # canopy
    dr.polygon([(cx + x, cy + y) for x, y in ((-20, 10), (90, 10), (130, 30), (10, 28))], fill=(48, 56, 64))           # wing
    dr.ellipse([cx + 62, cy + 2, cx + 74, cy + 12], fill=(200, 30, 25))                                             # red star
    for x in (-30, 60, 120):                                                   # gear legs + wheels
        dr.line([(cx + x, cy + 14), (cx + x, cy + 38)], fill=(30, 30, 32), width=3)
        dr.ellipse([cx + x - 7, cy + 34, cx + x + 7, cy + 46], fill=(16, 16, 16))
    refl = im.crop((px0, int(cy - 70), px1, hz)).transpose(Image.FLIP_TOP_BOTTOM).filter(ImageFilter.GaussianBlur(3))
    m_ = Image.new('L', refl.size, 70)
    im.paste(refl, (px0, hz + 2), m_)
    for k in range(260):                                                       # rain streaks
        rng = _rng(seed + k)
        x, y = int(rng.integers(px0, px1)), int(rng.integers(py0, py1 - 20))
        dr.line([(x, y), (x - 3, y + 14)], fill=(150, 152, 158), width=1)
    dr.rectangle([px0, py0, px1, py1], outline=(18, 16, 14), width=4)
    dr.rectangle([60, 392, W - 60, 470], fill=(170, 140, 70), outline=(110, 86, 40), width=4)                        # brass plate
    f = _font(FONT_B, 25)
    _centre_text(dr, W, 404, 'My Sukhoi.', f, (40, 30, 16))
    _centre_text(dr, W, 436, 'Taken by IGI.', f, (40, 30, 16))
    return _arr(im, seed, 0.05)


def tex_noclip(seed=46):
    W, H = 512, 128
    im, dr = _pil(W, H, (0.10, 0.10, 0.11))
    dr.rectangle([4, 4, W - 5, H - 5], outline=(214, 176, 26), width=4)
    f = _font(FONT_B, 30)
    _centre_text(dr, W, 22, 'SHOBI - yes, we checked', f, (240, 236, 220))
    _centre_text(dr, W, 68, 'in here too.', f, (240, 236, 220))
    return _arr(im, seed, 0.0)


def tex_missile(seed=47):
    """missile body (uv u = around, v = along): light grey, a dark nose band, red + black stencil rings, a number"""
    W, H = 128, 256
    im, dr = _pil(W, H, (0.78, 0.79, 0.76))
    dr.rectangle([0, 0, W, 28], fill=(60, 64, 60))                            # radome band
    dr.rectangle([0, 92, W, 100], fill=(170, 30, 24))
    dr.rectangle([0, 104, W, 108], fill=(30, 30, 30))
    dr.rectangle([0, 190, W, 256], fill=(150, 152, 148))                      # booster section
    dr.text((30, 140), '4-04', fill=(30, 30, 30), font=_font(FONT_B, 24))
    return _arr(im, seed, 0.10)


def tex_hazard(n=128):
    im, dr = _pil(n, n, (0.86, 0.70, 0.10))
    for k in range(-n, 2 * n, 32):
        dr.polygon([(k, 0), (k + 16, 0), (k + 16 - n, n), (k - n, n)], fill=(22, 20, 18))
    return _arr(im, 48, 0.08)


def tex_wood(n=128, seed=49):
    rng = _rng(seed)
    g = 0.75 + 0.25 * BP._noise(n, rng, 4)
    img = np.dstack([0.58 * g, 0.46 * g, 0.30 * g])
    xx = np.mgrid[0:n, 0:n][1]
    img[(xx % 32) < 2] *= 0.55
    return np.dstack([np.clip(img, 0, 1), np.ones((n, n))])


def tex_flat(rgb, n=32):
    return np.dstack([np.full((n, n), c) for c in rgb] + [np.ones((n, n))])


TEXTURES = {
    'jr_olive': lambda: tex_paint((0.27, 0.31, 0.21), seed=11, chips=0.04),
    'jr_yellow': lambda: tex_paint((0.86, 0.68, 0.10), seed=12, chips=0.05),
    'jr_steel': lambda: BP.tex_steel(128, seed=13, base=(0.38, 0.39, 0.41)),
    'jr_dark': lambda: tex_paint((0.10, 0.10, 0.11), n=64, seed=14),
    'jr_conc': lambda: BP.tex_concrete(256, seed=15, base=(0.55, 0.55, 0.53)),
    'jr_canvas': lambda: tex_paint((0.30, 0.31, 0.20), n=256, seed=16, grime=0.22),
    'jr_rubber': lambda: tex_paint((0.06, 0.06, 0.06), n=32, seed=17, grime=0.2),
    'jr_red': lambda: tex_paint((0.66, 0.10, 0.08), n=64, seed=18),
    'jr_white': lambda: tex_paint((0.85, 0.85, 0.82), n=64, seed=19),
    'jr_green': lambda: tex_flat((0.30, 0.95, 0.45)),
    'jr_lamp': lambda: tex_flat((1.0, 0.92, 0.72)),
    'jr_lampoff': lambda: tex_flat((0.30, 0.29, 0.27)),
    'jr_wood': tex_wood,
    'jr_hazard': tex_hazard,
    'jr_grid': tex_grid,
    'jr_console': tex_console,
    'jr_radio': tex_radio,
    'jr_chk': tex_checklist,
    'jr_falcon': tex_falcon,
    'jr_su27': tex_su27,
    'jr_noclip': tex_noclip,
    'jr_misw': tex_missile,
    'jr_sgate': lambda: tex_sign([('СОКОЛ-9', 120, (0.85, 0.10, 0.08), True), ('ВОЙСКОВАЯ ЧАСТЬ 41927', 32, (0.12, 0.12, 0.12), True),
                                ('ПРОХОД ЗАПРЕЩЕН', 28, (0.12, 0.12, 0.12), False)], size=(512, 256), icon='star', seed=51),
    'jr_sstop': lambda: tex_stop(),
    'jr_spass': lambda: tex_sign([('ПРЕДЪЯВИ', 40, (0.10, 0.10, 0.10), True), ('ПРОПУСК', 40, (0.10, 0.10, 0.10), True)], size=(256, 128),
                               border=(0.10, 0.10, 0.10), bw=8, seed=53),
    'jr_snosm': lambda: tex_sign([('НЕ КУРИТЬ', 50, (0.75, 0.08, 0.06), True), ('NO SMOKING', 36, (0.12, 0.12, 0.12), True)], size=(512, 256),
                               icon='nosmoke', seed=54),
    'jr_sblast': lambda: tex_sign([('ОПАСНО!', 64, (0.12, 0.10, 0.08), True), ('РЕАКТИВНАЯ СТРУЯ', 40, (0.12, 0.10, 0.08), True),
                                 ('DANGER  JET BLAST', 30, (0.12, 0.10, 0.08), True)], size=(512, 256), bg=(0.90, 0.74, 0.10),
                                icon='hazard', seed=55),
    'jr_sdesc': lambda: tex_sign([('АВАРИЙНЫЙ', 48, (0.97, 0.97, 0.95), True), ('СПУСК', 60, (0.97, 0.97, 0.95), True)], size=(512, 256),
                               bg=(0.08, 0.46, 0.20), border=(0.97, 0.97, 0.95), bw=10, icon='arrow', seed=56),
    'jr_sshut': lambda: tex_sign([('ЗАКРЫТО', 72, (0.97, 0.96, 0.94), True), ('ВХОД ЗАПРЕЩЕН', 30, (0.97, 0.96, 0.94), False)], size=(512, 256),
                               bg=(0.70, 0.08, 0.06), border=(0.97, 0.96, 0.94), bw=10, seed=57),
}


# ================================================================================================ the models
def build_sam():
    """towed launcher (origin ground centre, the rail points +y, up RAIL_PITCH)"""
    olive, dark, rub, steel = [], [], [], []
    olive.append(box(-1.15, -2.9, 0.85, 1.15, 2.6, 1.20))                     # trailer bed
    olive.append(box(-0.12, 2.6, 0.75, 0.12, 4.3, 0.95))                      # tow bar
    for y in (-1.9, -0.7):                                                      # 2 axles
        for sx in (-1, 1):
            t_, h_ = wheel_x(0.52, 0.32, sx * 1.12, y, 0.52)
            rub.append(t_); steel.append(h_)
        dark.append(box(-1.0, y - 0.07, 0.45, 1.0, y + 0.07, 0.60))
    for sx in (-1, 1):                                                          # outrigger jacks on the ground
        for y in (-2.6, 2.2):
            olive.append(beam((sx * 1.1, y, 1.0), (sx * 2.3, y, 0.25), 0.14))
            steel.append(box(sx * 2.3 - 0.25, y - 0.25, 0.0, sx * 2.3 + 0.25, y + 0.25, 0.06))
            steel.append(cyl(0.07, 0.06, 0.40, 8, sx * 2.3, y))
    olive.append(cyl(1.05, 1.20, 1.55, 18, 0.0, -0.6))                         # turntable
    olive.append(box(-0.55, -1.25, 1.55, 0.55, 0.05, 2.25))                    # trunnion block
    R = rx(RAIL_PITCH)
    piv = np.asarray(RAIL_PIVOT, float)
    for sx in (-1, 1):                                                          # the rail: two beams + cross ties, pitched
        a = piv + R @ np.array([sx * 0.22, -0.8, -0.18]); b = piv + R @ np.array([sx * 0.22, RAIL_LEN, -0.18])
        steel.append(beam(a, b, 0.12, 0.22))
    for f in np.linspace(-0.6, RAIL_LEN - 0.2, 6):
        steel.append(beam(piv + R @ np.array([-0.30, f, -0.30]), piv + R @ np.array([0.30, f, -0.30]), 0.08))
    olive.append(beam(piv + R @ np.array([0.0, 1.2, -0.45]), np.array([0.0, 1.8, 1.25]), 0.16))       # elevation ram
    steel.append(box(0.75, -2.5, 1.20, 1.10, -1.6, 1.85))                      # control box
    coll = [box(-1.2, -2.95, 0.45, 1.2, 2.65, 1.25), box(-0.6, -1.3, 1.2, 0.6, 0.1, 2.3)] + steel[-1:]
    for sx in (-1, 1):
        coll.append(beam(piv + R @ np.array([sx * 0.22, -0.8, -0.18]), piv + R @ np.array([sx * 0.22, RAIL_LEN, -0.18]), 0.14, 0.24))
    return MK.model([(0, olive), (1, dark), (2, rub), (3, steel)], coll)


def _missile_parts():
    L, r = MIS_LEN, MIS_R
    body = [cylx(r, -L / 2 + 1.2, L / 2 - 0.9, 'y', 14)]                          # (cyl_axis 'y': along y)
    nose = hull([(r * math.cos(a), L / 2 - 0.9, r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 14, endpoint=False)] + [(0, L / 2, 0)], uv=0.5)
    boost = [cylx(r * 1.35, -L / 2, -L / 2 + 1.25, 'y', 14)]
    fins = []
    for k in range(4):                                                          # cruciform fins (+ booster fins)
        a = k * math.pi / 2 + math.pi / 4
        d = np.array([math.cos(a), 0, math.sin(a)])
        for (y0, y1, span) in ((L / 2 - 2.0, L / 2 - 1.2, 0.30), (-L / 2 + 0.1, -L / 2 + 0.9, 0.62)):
            base = r * (1.35 if y0 < 0 else 1.0)
            pts = [d * base + np.array([0, y0, 0]), d * base + np.array([0, y1, 0]), d * (base + span) + np.array([0, y0 + 0.2, 0]),
                   d * (base + span) + np.array([0, y0, 0])]
            n = np.cross(d, [0, 1, 0]) * 0.02
            fins.append(hull([p + n for p in pts] + [p - n for p in pts], uv=0.5))
    return body + [nose], boost, fins


def _fix_axis_y(parts):
    """cyl_axis('y') builds along -y..? -> make sure the parts run along +y as given (no-op helper for clarity)"""
    return parts


def build_missile(hot=False):
    body, boost, fins = _missile_parts()
    gl = glow(((0, -MIS_LEN / 2 - 0.3, 0), 2600.0, (1.0, 0.72, 0.35)), ((0, -MIS_LEN / 2 - 1.6, 0), 1700.0, (1.0, 0.55, 0.22))) if hot else None
    return MK.model([(0, body), (1, boost + fins)], body + boost, glows=gl)


def build_fcc():
    """fire-control console: desk 2.2 x 0.9 m (top FCC_DESK), a sloped panel + a cabinet behind, front +y"""
    steel, dark = [], []
    steel.append(box(-1.1, -0.45, 0.0, 1.1, 0.45, FCC_DESK - 0.05))
    steel.append(box(-1.15, -0.5, FCC_DESK - 0.05, 1.15, 0.5, FCC_DESK))
    slope = hull([(-1.05, 0.10, FCC_DESK), (1.05, 0.10, FCC_DESK), (-1.05, -0.40, FCC_DESK), (1.05, -0.40, FCC_DESK),
                  (-1.05, -0.40, FCC_DESK + 0.62), (1.05, -0.40, FCC_DESK + 0.62), (-1.05, -0.20, FCC_DESK + 0.62), (1.05, -0.20, FCC_DESK + 0.62)])
    steel.append(slope)
    steel.append(box(-1.1, -0.5, FCC_DESK + 0.6, 1.1, -0.15, FCC_DESK + 0.95))     # top cabinet
    p0, p1 = np.array([0.0, 0.10, FCC_DESK]), np.array([0.0, -0.20, FCC_DESK + 0.62])   # the slope's front edge -> top edge
    up = (p1 - p0) / np.linalg.norm(p1 - p0)
    nrm = np.cross((-1.0, 0.0, 0.0), up)                                                 # (= +y and up: toward the operator)
    face = panel(tuple((p0 + p1) / 2 + nrm * 0.004), (-1, 0, 0), up, 2.0, float(np.linalg.norm(p1 - p0)) * 0.96)
    dark.append(box(-0.04, 0.30, FCC_DESK, 0.04, 0.38, FCC_DESK + 0.09))            # the key socket proud of the desk
    gl = glow(((-0.75, -0.05, FCC_DESK + 0.45), 320.0, (0.35, 1.0, 0.5)), ((0.75, -0.05, FCC_DESK + 0.45), 320.0, (0.35, 1.0, 0.5)),
              ((0.0, 0.34, FCC_DESK + 0.12), 160.0, (1.0, 0.3, 0.2)))
    return MK.model([(0, steel), (1, [face]), (2, dark)], steel[:3] + steel[3:4], glows=gl)


def build_key():
    """the launch key (lying flat, origin = the table top under it): a steel key + a red lanyard tag"""
    steel = [box(-0.012, -0.05, 0.0, 0.012, 0.06, 0.006), cyl(0.022, 0.0, 0.008, 10, 0.0, -0.07)]
    red = [box(-0.03, -0.20, 0.0, 0.03, -0.09, 0.005)]
    return MK.model([(0, steel), (1, red)], [box(-0.03, -0.2, 0.0, 0.03, 0.06, 0.01)])


def build_grid():
    """30 x 30 m deck, top z 0, 0.2 m thick, chamfered edge (no step > 0.2 m)"""
    H = GRID_HALF
    top = BP.slab(-H, -H, H, H, 0.0, uv=(1.0, 1.0), up=True)
    P, T_, N, U = top
    U = np.array([((p[0] / M + H) / (2 * H), 1 - (p[1] / M + H) / (2 * H)) for p in P])
    T_ = T_[:len(T_) // 2]                                                       # one-sided (the top)
    deck = (P, T_, N, U)
    edge = hull([(sx * H, sy * H, z) for sx in (-1, 1) for sy in (-1, 1) for z in (-0.20, -0.01)] +
                [(sx * (H + 0.25), sy * (H + 0.25), -0.20) for sx in (-1, 1) for sy in (-1, 1)], uv=0.3)
    coll = [box(-H, -H, -0.2, H, H, 0.0)]
    return MK.model([(0, [deck]), (1, [edge])], coll)


def stair_parts(top=STAND_TOP, w=STAND_W, depth=STAND_DEPTH, slope=STAND_SLOPE):
    """the boarding stair: platform y 0..depth (top `top`), flight from y 0 down to y -run (z 0); x -w/2..w/2"""
    run = top / math.tan(slope)
    yel, dark, steel, coll = [], [], [], []
    yel.append(box(-w / 2, 0.0, top - 0.12, w / 2, depth, top))                  # platform (grating top in 'jr_steel'?)
    n = max(2, int(round(top / 0.22)))
    for k in range(n):
        za = top * (k + 1) / n
        ya = -run + run * k / n
        steel.append(box(-w / 2 + 0.05, ya, za - 0.05, w / 2 - 0.05, ya + run / n + 0.02, za))
    for sx in (-1, 1):
        yel.append(beam((sx * w / 2, -run, 0.05), (sx * w / 2, 0.0, top - 0.06), 0.08, 0.28))     # stringers
        yel.append(box(sx * w / 2 - 0.05, -0.05, 0.0, sx * w / 2 + 0.05, 0.05, top))           # posts under the platform
        yel.append(box(sx * w / 2 - 0.05, depth - 0.1, 0.0, sx * w / 2 + 0.05, depth, top))
        yel.append(beam((sx * w / 2, -run, 1.0), (sx * w / 2, 0.0, top + 1.0), 0.05))         # handrails
        yel.append(beam((sx * w / 2, 0.0, top + 1.0), (sx * w / 2, depth - 0.03, top + 1.0), 0.05))
        yel.append(beam((sx * w / 2, 0.0, top + 0.5), (sx * w / 2, depth - 0.03, top + 0.5), 0.04))
        yel.append(box(sx * w / 2 - 0.03, -run - 0.03, 0.0, sx * w / 2 + 0.03, -run + 0.03, 1.0))
        yel.append(box(sx * w / 2 - 0.03, -0.03, top, sx * w / 2 + 0.03, 0.03, top + 1.0))
        yel.append(box(sx * w / 2 - 0.03, depth - 0.06, top, sx * w / 2 + 0.03, depth, top + 1.0))
        t_, h_ = wheel_x(0.18, 0.12, sx * (w / 2 + 0.12), -run + 0.35, 0.18)
        dark.append(t_)
        t_, h_ = wheel_x(0.18, 0.12, sx * (w / 2 + 0.12), depth - 0.25, 0.18)
        dark.append(t_)
    yel.append(box(-w / 2, -run, 0.0, w / 2, -run + 0.15, 0.06))                # base frame
    yel.append(box(-w / 2 - 0.12, depth - 0.35, 0.0, w / 2 + 0.12, depth - 0.15, 0.36))
    # the yellow/black hazard edge strip on the platform front (toward the jet)
    haz = [box(-w / 2, depth - 0.04, top - 0.12, w / 2, depth, top + 0.005)]
    wedge = hull([(-w / 2, -run, 0.0), (w / 2, -run, 0.0), (-w / 2, 0.0, top), (w / 2, 0.0, top),
                  (-w / 2, -run, -0.3), (w / 2, -run, -0.3), (-w / 2, 0.0, top - 0.3), (w / 2, 0.0, top - 0.3)], uv=0.5)
    coll += [wedge, box(-w / 2, 0.0, top - 0.3, w / 2, depth, top)]
    for sx in (-1, 1):                                                          # rails as collision (no fall off the side)
        coll.append(hull([(sx * w / 2 - 0.04, -run, 0.0), (sx * w / 2 + 0.04, -run, 0.0), (sx * w / 2 - 0.04, 0.0, top), (sx * w / 2 + 0.04, 0.0, top),
                          (sx * w / 2 - 0.04, -run, 1.05), (sx * w / 2 + 0.04, -run, 1.05), (sx * w / 2 - 0.04, 0.0, top + 1.05), (sx * w / 2 + 0.04, 0.0, top + 1.05)]))
        coll.append(box(sx * w / 2 - 0.04, 0.0, top, sx * w / 2 + 0.04, depth, top + 1.05))
    return yel, dark, steel, haz, coll, run


def build_stand():
    yel, dark, steel, haz, coll, run = stair_parts()
    return MK.model([(0, yel), (1, dark), (2, steel), (3, haz)], coll)


def build_tug():
    yel, dark, rub = [], [], []
    yel.append(hull([(-0.9, -1.6, 0.35), (0.9, -1.6, 0.35), (-0.9, 1.7, 0.35), (0.9, 1.7, 0.35),
                     (-0.9, -1.6, 0.95), (0.9, -1.6, 0.95), (-0.85, 1.2, 1.05), (0.85, 1.2, 1.05), (-0.8, 1.75, 0.6), (0.8, 1.75, 0.6)], uv=0.5))
    dark.append(box(-0.45, -0.9, 0.95, 0.45, -0.3, 1.45))                       # seat back
    dark.append(box(-0.45, -0.9, 0.95, 0.45, -0.1, 1.05))
    dark.append(cyl(0.18, 1.05, 1.30, 12, 0.0, 0.25))                          # steering wheel hub
    dark.append(beam((0.0, 0.25, 1.15), (0.0, 0.5, 0.95), 0.05))
    for y in (-1.05, 1.15):
        for sx in (-1, 1):
            t_, h_ = wheel_x(0.38, 0.34, sx * 0.95, y, 0.38)
            rub.append(t_); dark.append(h_)
    dark.append(box(-0.08, -2.4, 0.42, 0.08, -1.6, 0.52))                       # tow hitch
    yel.append(box(-0.95, 1.55, 0.25, 0.95, 1.75, 0.45))                        # bumper
    gl = glow(((0.55, 1.78, 0.75), 300.0, (1.0, 0.95, 0.8)), ((-0.55, 1.78, 0.75), 300.0, (1.0, 0.95, 0.8)))
    return MK.model([(0, yel), (1, dark), (2, rub)], [box(-1.0, -1.7, 0.0, 1.0, 1.8, 1.1), box(-0.5, -0.95, 1.0, 0.5, -0.25, 1.5)], glows=gl)


def build_gpu():
    """ground power cart: a closed generator body (sealed: the noclip panel inside), drawbar, cable reel, 2 lamp masts"""
    yel, dark, rub, steel = [], [], [], []
    body = box(-0.75, -1.3, 0.45, 0.75, 1.3, 1.65)
    yel.append(body)
    dark.append(box(-0.76, -0.9, 0.7, -0.74, 0.9, 1.4))                         # louvres
    dark.append(box(0.74, -0.9, 0.7, 0.76, 0.9, 1.4))
    steel.append(box(-0.5, 1.30, 0.8, 0.5, 1.36, 1.4))                          # control panel front
    for y in (-0.85, 0.85):
        for sx in (-1, 1):
            t_, h_ = wheel_x(0.30, 0.2, sx * 0.85, y, 0.30)
            rub.append(t_); dark.append(h_)
    steel.append(box(-0.05, 1.3, 0.38, 0.05, 2.4, 0.46))                        # drawbar
    dark.append(cylx(0.32, -0.25, 0.25, 'x', 14, at=(-1.55, 1.15)))             # cable reel at the back
    lamps = []
    for sx in (-1, 1):
        steel.append(cyl(0.04, 1.65, 3.2, 8, sx * 0.55, -1.15))
        steel.append(box(sx * 0.55 - 0.18, -1.25, 3.15, sx * 0.55 + 0.18, -1.05, 3.4))
        lamps.append(((sx * 0.55, -1.0, 3.27), 1800.0, (1.0, 0.95, 0.85)))
    # the SHOBI noclip panel: INSIDE the sealed body, facing +x, readable only from inside (the walls are one-sided)
    nc = panel((0.30, 0.0, 1.05), (0, 1, 0), (0, 0, 1), 1.6, 0.4)
    return MK.model([(0, yel), (1, dark), (2, rub), (3, steel), (4, [nc])], [body, box(-0.9, -1.0, 0.0, 0.9, 1.0, 0.5)], glows=glow(*lamps))


def build_chock():
    """a pair of yellow wheel chocks joined by a rope (for one wheel, 0.8 m apart along y)"""
    yel = []
    for sg in (-1, 1):                          # (clear of a 0.46 m tyre: its face is 0.35 m out at the chock's 0.16 m top)
        yel.append(hull([(x, sg * yy, z) for x in (-0.15, 0.15) for yy, z in ((0.38, 0.0), (0.62, 0.0), (0.62, 0.16), (0.52, 0.16))], uv=0.5))
    dark = [beam((0.16, -0.5, 0.08), (0.16, 0.5, 0.08), 0.02)]
    return MK.model([(0, yel), (1, dark)], yel)


def build_hose():
    """a coiled fuel hose lying on the deck (3 turns, 1.2 m across) + a nozzle"""
    parts = []
    for k in range(3):
        R = 0.45 + 0.08 * k
        pts = [(R * math.cos(t), R * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 17)]
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            parts.append(tube((x0, y0, 0.05 + 0.02 * k), (x1, y1, 0.05 + 0.02 * k), 0.05, 6))
    steel = [tube((0.62, 0.0, 0.08), (1.0, 0.25, 0.10), 0.05, 6), box(0.95, 0.2, 0.0, 1.15, 0.38, 0.16)]
    return MK.model([(0, parts), (1, steel)], [box(-0.7, -0.7, 0.0, 0.7, 0.7, 0.14)])


def build_relay():
    """field radio set on a table (origin = its bottom centre), front +y, handset, antenna lead"""
    olive = [box(-0.32, -0.18, 0.0, 0.32, 0.18, 0.38)]
    face = panel((0.0, 0.183, 0.19), (-1, 0, 0), (0, 0, 1), 0.60, 0.33)
    dark = [box(0.36, -0.06, 0.0, 0.48, 0.06, 0.05), box(0.40, -0.03, 0.05, 0.44, 0.03, 0.22), tube((-0.25, -0.1, 0.38), (-0.25, -0.1, 1.35), 0.008, 5)]
    return MK.model([(0, olive), (1, [face]), (2, dark)], olive, glows=glow(((-0.18, 0.19, 0.30), 120.0, (1.0, 0.6, 0.2))))


def build_brk():
    """breaker cabinet 1.2 x 0.5 x 1.9 m with the big red handwheel on its front (+y) and a warning plate"""
    steel = [box(-0.6, -0.25, 0.0, 0.6, 0.25, 1.9), box(-0.65, -0.3, 1.9, 0.65, 0.3, 1.96)]
    red = []
    for k in range(8):
        a0, a1 = k * math.pi / 4, (k + 1) * math.pi / 4
        p0 = (0.32 * math.cos(a0), 0.36, 1.15 + 0.32 * math.sin(a0)); p1 = (0.32 * math.cos(a1), 0.36, 1.15 + 0.32 * math.sin(a1))
        red.append(beam(p0, p1, 0.05))
    for k in range(3):
        a = k * math.pi * 2 / 3
        red.append(beam((0, 0.36, 1.15), (0.3 * math.cos(a), 0.36, 1.15 + 0.3 * math.sin(a)), 0.035))
    red.append(cylx(0.07, 0.25, 0.40, 'y', 10, at=(0.0, 1.15)))
    haz = [panel((0.0, 0.253, 1.65), (-1, 0, 0), (0, 0, 1), 0.8, 0.22)]
    return MK.model([(0, steel), (1, red), (2, haz)], steel)


def build_culvert():
    """the culvert under the north wall: inlet headwall at y 0 (faces -y = outside), a 1.4 x 1.4 m clear box running
    +y for CUL_LEN, an outlet headwall; the inlet grate's lower-right corner BENT OPEN (the tell)"""
    w, h, L, t = CUL_W, CUL_H, CUL_LEN, 0.20
    conc = [box(-w / 2 - t, 0.0, -t, w / 2 + t, L, 0.0),                       # floor slab (top z 0)
            box(-w / 2 - t, 0.0, h, w / 2 + t, L, h + t),                        # roof
            box(-w / 2 - t, 0.0, 0.0, -w / 2, L, h), box(w / 2, 0.0, 0.0, w / 2 + t, L, h)]
    for y0, y1 in ((-0.3, 0.0), (L, L + 0.3)):                                  # headwalls
        conc += [box(-w / 2 - 1.6, y0, -0.3, -w / 2, y1, h + 1.0), box(w / 2, y0, -0.3, w / 2 + 1.6, y1, h + 1.0),
                 box(-w / 2, y0, h, w / 2, y1, h + 1.0)]
    steel = []
    for k in range(7):                                                          # the grate at the inlet (y -0.15)
        x = -w / 2 + 0.1 + k * (w - 0.2) / 6
        if k >= 3:                                                              # bars 3-6 wrenched out from the bottom and bent
            steel.append(beam((x, -0.15, h), (x, -0.15, h - 0.12), 0.03))         #  up and outward: the opening (x -0.1..0.7,
            steel.append(beam((x, -0.15, h - 0.12), (x + 0.10, -0.80, h - 0.10 + 0.04 * k), 0.03))   #  0..1.25 m) shows no bar
        else:
            steel.append(beam((x, -0.15, 0.0), (x, -0.15, h), 0.03))
    steel.append(beam((-w / 2, -0.15, h - 0.08), (w / 2, -0.15, h - 0.08), 0.05))
    steel.append(beam((-w / 2, -0.15, 0.55), (-0.12, -0.15, 0.55), 0.05))       # the cross bar, torn off at the gap
    steel.append(beam((-0.12, -0.15, 0.55), (0.05, -0.55, 0.30), 0.05))
    coll = list(conc) + [box(-w / 2, -0.18, 0.0, -0.10, -0.12, h)]               # (the grate closes only the left 0.6 m)
    return MK.model([(0, conc), (1, steel)], coll)


def build_pallets():
    """pallet steps: PAL_N steps of PAL_STEP rise, each 0.6 m deep, 1.2 m wide, rising +y (origin = front edge, ground);
    every step a stack of 0.15 m pallets (dark slat gaps on the faces), the last one 1.0 m deep (a landing)"""
    wood, dark, coll = [], [], []
    for k in range(PAL_N):
        y0 = k * 0.6
        y1 = y0 + (0.6 if k < PAL_N - 1 else 1.0)
        z1 = (k + 1) * PAL_STEP
        wood.append(box(-0.6, y0, 0.0, 0.6, y1, z1, uv=1.0))
        coll.append(box(-0.6, y0, 0.0, 0.6, y1, z1))
        for zz in np.arange(0.15, z1 - 0.05, 0.15):                             # the gaps between the pallets (front face)
            dark.append(box(-0.58, y0 - 0.005, zz - 0.02, 0.58, y0 + 0.01, zz))
    return MK.model([(0, wood), (1, dark)], coll)


def build_cage(h=CAGE_H):
    """safety cage for a ladder on a wall at y 0 (the climber faces -y on the +y side): hoops every 0.9 m from 2.4 m,
    5 uprights; NO collision in the climbing lane (only a foot plate)"""
    steel = []
    R, cy = 0.38, 0.42
    zs = np.arange(2.4, h + 1.05, 0.9)
    for z in zs:
        pts = [(R * math.cos(t), cy + R * math.sin(t)) for t in np.linspace(-0.2, math.pi + 0.2, 9)]
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            steel.append(beam((x0, y0, z), (x1, y1, z), 0.035, 0.05))
        steel.append(beam((-R - 0.06, 0.02, z), (-R * math.cos(0.2), cy - R * math.sin(0.2), z), 0.03))   # hoop to wall arms
        steel.append(beam((R + 0.06, 0.02, z), (R * math.cos(0.2), cy - R * math.sin(0.2), z), 0.03))
    for t in np.linspace(0.15, math.pi - 0.15, 5):
        x, y = R * math.cos(t), cy + R * math.sin(t)
        steel.append(beam((x, y, 2.4), (x, y, zs[-1]), 0.03))
    steel.append(beam((-R, cy, h + 1.05), (R, cy, h + 1.05), 0.04))
    return MK.model([(0, steel)], [box(-0.3, 0.0, 0.0, 0.3, 0.1, 0.04)])


def build_zip():
    """zip start platform: 3 x 3 m deck at ZIP_TOP, 3 steps up from -y, rails on 3 sides (open toward +y), an A-frame anchor
    over the +y edge with the wire start at ZIP_GRAB and the 'АВАРИЙНЫЙ СПУСК' sign on it"""
    steel, yel, sign = [], [], []
    top = ZIP_TOP
    steel.append(box(-1.5, -1.5, top - 0.12, 1.5, 1.5, top))
    for sx in (-1, 1):
        for sy in (-1, 1):
            steel.append(box(sx * 1.4 - 0.06, sy * 1.4 - 0.06, 0.0, sx * 1.4 + 0.06, sy * 1.4 + 0.06, top - 0.1))
    for k in range(3):                                                          # steps up from -y
        z = top * (k + 1) / 4
        steel.append(box(-0.6, -1.5 - 0.35 * (3 - k), z - 0.06, 0.6, -1.5 - 0.35 * (2 - k), z))
    for p0, p1 in (((-1.5, -1.5), (-1.5, 1.5)), ((1.5, -1.5), (1.5, 1.5)), ((-1.5, -1.5), (-0.65, -1.5)), ((0.65, -1.5), (1.5, -1.5))):
        yel.append(beam((p0[0], p0[1], top + 1.05), (p1[0], p1[1], top + 1.05), 0.05))
        yel.append(beam((p0[0], p0[1], top + 0.55), (p1[0], p1[1], top + 0.55), 0.04))
        for q in (p0, p1):                                                      # (posts: rails never float)
            yel.append(box(q[0] - 0.03, q[1] - 0.03, top, q[0] + 0.03, q[1] + 0.03, top + 1.08))
    gx, gy, gz = ZIP_GRAB
    for sx in (-1, 1):                                                          # the A-frame
        steel.append(beam((sx * 1.2, 1.35, top), (0.0, gy, gz + 0.45), 0.12))
    steel.append(beam((-0.25, gy, gz + 0.3), (0.25, gy, gz + 0.3), 0.10))
    steel.append(cylx(0.09, -0.06, 0.06, 'x', 10, at=(gy, gz + 0.12)))          # pulley
    pl = panel((0.0, 1.30, top + 1.55), (-1, 0, 0), (0, 0, 1), 1.0, 0.5)          # sign faces +y (toward the wire's run)
    pl2 = panel((0.0, 1.26, top + 1.55), (1, 0, 0), (0, 0, 1), 1.0, 0.5)          # ... and -y (as you climb up)
    steel.append(box(-0.52, 1.265, top + 1.29, 0.52, 1.295, top + 1.81))
    coll = [box(-1.5, -1.5, 0.0, 1.5, 1.5, top)] + [box(-0.6, -1.5 - 0.35 * (3 - k), 0.0, 0.6, -1.5 - 0.35 * (2 - k), top * (k + 1) / 4) for k in range(3)]
    for p0, p1 in (((-1.5, -1.5), (-1.5, 1.5)), ((1.5, -1.5), (1.5, 1.5))):
        coll.append(box(min(p0[0], p1[0]) - 0.04, min(p0[1], p1[1]), top, max(p0[0], p1[0]) + 0.04, max(p0[1], p1[1]), top + 1.05))
    return MK.model([(0, steel), (1, yel), (2, [pl, pl2])], coll)


def build_tent():
    """army tent 4.6 x 4.6 m, eaves 1.7 m, ridge 3.1 m, a rolled-up door flap on +y (closed inside: decor)"""
    can, dark = [], []
    a, e, r = 2.3, 1.7, 3.1
    can.append(hull([(sx * a, sy * a, 0.0) for sx in (-1, 1) for sy in (-1, 1)] + [(sx * a, sy * a, e) for sx in (-1, 1) for sy in (-1, 1)]
                    + [(0.0, sy * a, r) for sy in (-1, 1)], uv=0.3))
    dark.append(box(-0.55, a - 0.01, 0.0, 0.55, a + 0.03, 1.6))                    # the door opening (dark)
    can.append(cylx(0.12, -0.6, 0.6, 'x', 8, at=(a + 0.1, 1.72)))                  # rolled flap
    for sx in (-1, 1):                                                              # guy ropes + pegs
        for sy in (-1, 1):
            dark.append(beam((sx * a, sy * a, e - 0.1), (sx * (a + 1.1), sy * (a + 1.1), 0.0), 0.02))
    dark.append(tube((0.0, 0.0, r), (0.0, 0.0, r + 0.6), 0.04, 6))                  # stove pipe
    return MK.model([(0, can), (1, dark)], can[:1])


def build_pa(wall=False):
    """two PA horns (front +y, back -y) on a 5.5 m pole (wall=False) or on a wall bracket (wall=True: origin = the wall)"""
    steel, horn = [], []
    if wall:
        steel.append(box(-0.1, 0.0, -0.15, 0.1, 0.06, 0.15))
        steel.append(box(-0.04, 0.0, -0.04, 0.04, 0.45, 0.04))
        base = np.array([0.0, 0.45, 0.0])
        dirs = [(-0.5, 1.0, -0.25), (0.5, 1.0, -0.25)]
    else:
        steel.append(cyl(0.08, 0.0, 5.5, 8))
        steel.append(box(-0.35, -0.35, -0.1, 0.35, 0.35, 0.25))
        base = np.array([0.0, 0.0, 5.3])
        dirs = [(0.0, 1.0, -0.2), (0.0, -1.0, -0.2)]
    for d in dirs:
        d = np.asarray(d, float); d /= np.linalg.norm(d)
        up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0, 0])
        s = np.cross(d, up); s /= np.linalg.norm(s); u = np.cross(s, d)
        mouth = [base + d * 0.62 + (s * math.cos(t) + u * math.sin(t)) * 0.24 for t in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
        neck = [base + d * 0.12 + (s * math.cos(t) + u * math.sin(t)) * 0.07 for t in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
        horn.append(hull(mouth + neck, uv=0.5))
    return MK.model([(0, steel), (1, horn)], steel)


def build_lamp(lit=True):
    """runway edge lamp: a frangible stalk 0.35 m with a yellow-white lens (glow when lit)"""
    steel = [cyl(0.03, 0.0, 0.30, 8), cyl(0.09, 0.0, 0.04, 8)]
    lens = [cyl(0.065, 0.30, 0.40, 10)]
    gl = glow(((0, 0, 0.36), 900.0, (1.0, 0.88, 0.62))) if lit else None
    return MK.model([(0, steel), (1, lens)], [box(-0.08, -0.08, 0.0, 0.08, 0.08, 0.4)], glows=gl)


def build_thr(lit=True):
    """threshold light bar: 6 m long (x), 8 green lamps on a low steel rail"""
    steel = [box(-3.0, -0.08, 0.0, 3.0, 0.08, 0.12)]
    lens, items = [], []
    for k in range(8):
        x = -2.8 + k * 0.8
        lens.append(cyl(0.07, 0.12, 0.22, 10, x, 0.0))
        items.append(((x, 0.0, 0.2), 900.0, (0.35, 1.0, 0.45)))
    return MK.model([(0, steel), (1, lens)], steel, glows=glow(*items) if lit else None)


def build_post_sign(w, h, top, two_posts=True, sub=None):
    """a sign board on post(s): face (+y) w x h with its top at `top`; sub = (w, h) of an extra plate under it"""
    steel = []
    xs = (-w / 2 + 0.15, w / 2 - 0.15) if two_posts else (0.0,)
    for x in xs:
        steel.append(box(x - 0.05, -0.05, 0.0, x + 0.05, 0.05, top))
    board = box(-w / 2, 0.05, top - h, w / 2, 0.09, top)
    face = panel((0.0, 0.093, top - h / 2), (-1, 0, 0), (0, 0, 1), w * 0.98, h * 0.98)
    groups = [(0, steel + [board]), (1, [face])]
    coll = [board] + steel
    if sub:
        sw, sh_ = sub
        sb = box(-sw / 2, 0.05, top - h - 0.06 - sh_, sw / 2, 0.09, top - h - 0.06)
        groups[0][1].append(sb)
        groups.append((2, [panel((0.0, 0.093, top - h - 0.06 - sh_ / 2), (-1, 0, 0), (0, 0, 1), sw * 0.98, sh_ * 0.98)]))
    return MK.model(groups, coll)


def build_stop(w=0.9, top=2.6, sub=(0.9, 0.45)):
    """an OCTAGONAL STOP board on one post + a plate under it (faces +y)"""
    import searchlight as SL
    r = w / 2 / math.cos(math.pi / 8)
    cz = top - w / 2
    ang = [math.pi / 8 + k * math.pi / 4 for k in range(8)]
    ring = [(r * math.cos(a), r * math.sin(a)) for a in ang]
    board = hull([(x, y_, cz + z) for x, z in ring for y_ in (0.05, 0.09)], uv=0.5)
    P = np.array([(0.0, 0.093, cz)] + [(-x, 0.093, cz + z) for x, z in ring]) * M        # (-x: the viewer's right = -x)
    U = np.array([(0.5, 0.5)] + [(0.5 + x / w, 0.5 - z / w) for x, z in ring])
    T_ = np.array([(0, 1 + k, 1 + (k + 1) % 8) for k in range(8)])
    N = np.tile([0.0, 1.0, 0.0], (len(P), 1))
    T_ = SL._orient(P, T_, N, np.tile([0.0, 1.0, 0.0], (len(T_), 1)))
    post = box(-0.05, -0.05, 0.0, 0.05, 0.05, top - 0.1)
    sw, sh_ = sub
    sb = box(-sw / 2, 0.05, top - w - 0.06 - sh_, sw / 2, 0.09, top - w - 0.06)
    sf = panel((0.0, 0.093, top - w - 0.06 - sh_ / 2), (-1, 0, 0), (0, 0, 1), sw * 0.98, sh_ * 0.98)
    return MK.model([(0, [post, board, sb]), (1, [(P, T_, N, U)]), (2, [sf])], [post, board, sb])


def tex_stop():
    """a red octagon (white rim) filling the texture, 'STOP' fitted"""
    W = H = 256
    im, dr = _pil(W, H, (0.75, 0.08, 0.06))
    r = W / 2 / math.cos(math.pi / 8)
    oct_ = [(W / 2 + r * math.cos(math.pi / 8 + k * math.pi / 4) * 0.94, H / 2 + r * math.sin(math.pi / 8 + k * math.pi / 4) * 0.94) for k in range(8)]
    dr.polygon(oct_, outline=(246, 244, 240), width=10)
    pt = 120
    while pt > 20:
        f = _font(FONT_B, pt); bb = dr.textbbox((0, 0), 'STOP', font=f)
        if bb[2] - bb[0] <= W * 0.78:
            break
        pt -= 4
    dr.text(((W - (bb[2] - bb[0])) / 2 - bb[0], (H - (bb[3] - bb[1])) / 2 - bb[1]), 'STOP', fill=(246, 244, 240), font=f)
    return _arr(im, 52, 0.06)


def build_plate(w, h):
    pl, face = plate(w, h)
    return MK.model([(0, [pl]), (1, [face])], [pl])


def build_photo():
    """framed print 0.9 x 0.9 m on the wall (the brass caption is part of the print)"""
    pl, face = plate(0.9, 0.9, d=0.04)
    return MK.model([(0, [pl]), (1, [face])], [pl])


# ================================================================================================ the registry
MODELS = [   # name, builder, slots, cut-off (m)
    ('jr_sam_1', build_sam, ['jr_olive', 'jr_dark', 'jr_rubber', 'jr_steel'], 1800),
    ('jr_mis_1', lambda: build_missile(False), ['jr_misw', 'jr_white'], 1800),
    ('jr_misf_1', lambda: build_missile(True), ['jr_misw', 'jr_white'], 2500),
    ('jr_fcc_1', build_fcc, ['jr_olive', 'jr_console', 'jr_dark'], 300),
    ('jr_key_1', build_key, ['jr_steel', 'jr_red'], 150),
    ('jr_grid_1', build_grid, ['jr_grid', 'jr_conc'], 1800),
    ('jr_stand_1', build_stand, ['jr_yellow', 'jr_rubber', 'jr_steel', 'jr_hazard'], 1500),
    ('jr_tug_1', build_tug, ['jr_yellow', 'jr_dark', 'jr_rubber'], 1500),
    ('jr_gpu_1', build_gpu, ['jr_yellow', 'jr_dark', 'jr_rubber', 'jr_steel', 'jr_noclip'], 1500),
    ('jr_chock_1', build_chock, ['jr_yellow', 'jr_dark'], 300),
    ('jr_hose_1', build_hose, ['jr_rubber', 'jr_steel'], 300),
    ('jr_relay_1', build_relay, ['jr_olive', 'jr_radio', 'jr_dark'], 300),
    ('jr_brk_1', build_brk, ['jr_steel', 'jr_red', 'jr_hazard'], 300),
    ('jr_cul_1', build_culvert, ['jr_conc', 'jr_steel'], 1500),
    ('jr_pal_1', build_pallets, ['jr_wood', 'jr_dark'], 1500),
    ('jr_cage_1', build_cage, ['jr_steel'], 1500),
    ('jr_zip_1', build_zip, ['jr_steel', 'jr_yellow', 'jr_sdesc'], 1500),
    ('jr_tent_1', build_tent, ['jr_canvas', 'jr_dark'], 1500),
    ('jr_pa_1', lambda: build_pa(False), ['jr_steel', 'jr_olive'], 1500),
    ('jr_paw_1', lambda: build_pa(True), ['jr_steel', 'jr_olive'], 900),
    ('jr_rwl_1', lambda: build_lamp(True), ['jr_steel', 'jr_lamp'], 1800),
    ('jr_rwd_1', lambda: build_lamp(False), ['jr_steel', 'jr_lampoff'], 1800),
    ('jr_thr_1', lambda: build_thr(True), ['jr_steel', 'jr_green'], 1800),
    ('jr_thd_1', lambda: build_thr(False), ['jr_steel', 'jr_lampoff'], 1800),
    ('jr_gate_1', lambda: build_post_sign(3.0, 1.5, 3.4), ['jr_white', 'jr_sgate'], 1500),
    ('jr_stop_1', build_stop, ['jr_steel', 'jr_sstop', 'jr_spass'], 1500),
    ('jr_nosm_1', lambda: build_plate(1.0, 0.5), ['jr_white', 'jr_snosm'], 900),
    ('jr_blast_1', lambda: build_post_sign(2.2, 1.1, 1.6), ['jr_steel', 'jr_sblast'], 1500),
    ('jr_desc_1', lambda: build_plate(1.0, 0.5), ['jr_white', 'jr_sdesc'], 900),
    ('jr_shut_1', lambda: build_plate(1.0, 0.5), ['jr_white', 'jr_sshut'], 900),
    ('jr_chk_1', lambda: build_plate(0.42, 0.84), ['jr_dark', 'jr_chk'], 150),
    ('jr_kfal_1', lambda: build_plate(1.2, 1.2), ['jr_dark', 'jr_falcon'], 900),
    ('jr_su27_1', build_photo, ['jr_wood', 'jr_su27'], 150),
]
NAMES = [n for n, b, s, c in MODELS]


def add_models(lib):
    for tname, fn in TEXTURES.items():
        lib.texture(tname, fn)
    for name, fn, slots, cut in MODELS:
        lib.add(name, fn, slots, lod_like='406_68_1')
    return list(NAMES)


def _lodrow(cut):
    return [cut * 0.96, cut * 0.97, cut * 0.98, cut * 0.99, cut]


def lod_rows():
    """{model: [5 cut-offs]} for lodfix extra (single-LOD models: the first four only matter for the switch, not a pop)"""
    return {n: _lodrow(float(c)) for n, b, s, c in MODELS}


# ================================================================================================ builder hook (CONTRACT.md S4)
def add(B, LIB):
    names = add_models(LIB)
    B.ART_DIMS = dict(RAIL_PITCH=RAIL_PITCH, RAIL_PIVOT=RAIL_PIVOT, RAIL_LEN=RAIL_LEN, MIS_ON_RAIL=MIS_ON_RAIL, GRID_HALF=GRID_HALF,
                      STAND_TOP=STAND_TOP, ZIP_TOP=ZIP_TOP, ZIP_GRAB=ZIP_GRAB, CUL=(CUL_W, CUL_H, CUL_LEN), CAGE_H=CAGE_H,
                      PAL=(PAL_STEP, PAL_N), FCC_DESK=FCC_DESK, KEYSWITCH=KEYSWITCH)
    B.sam_rail = sam_rail
    return names


def preview(out_dir, names=None):
    os.makedirs(out_dir, exist_ok=True)
    lib = MK.Library(); add_models(lib)
    want = names or NAMES
    out = []
    for k in range(0, len(want), 9):
        p = os.path.join(out_dir, 'models_%d.png' % (k // 9 + 1))
        lib.preview(p, names=want[k:k + 9])
        out.append(p)
    return out


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'preview':
        print(preview(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'joyride', 'art'),
                      sys.argv[3].split(',') if len(sys.argv) > 3 else None))
    else:
        lib = MK.Library(); add_models(lib)
        print({n: int(m_.hsem['n_rfaces']) for n, m_ in lib.build().items()})
