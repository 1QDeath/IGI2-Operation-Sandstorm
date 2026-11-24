"""alskins - asset library (2026-10-31): soldier skins + faces for FIVE factions, so a mission is not always Russians.
Painted over the shipped resg_1 layout like jrskins (body ch_resg_01 1024^2, head ch_resg_00 512x1024), the shipped
luminance kept as the cloth shading (folds, pockets, straps) - realistic camouflage patterns, not flat fills. Every slot is
LOCAL (COMMON_BIT slots crashed igi2.exe+0x16fda0) and every skin gets a lod.qvm row via lod_rows() (owner 10-18: a skin
without one vanishes beyond ~10 m).

  faction  skins                                   look
  cn       alpla1_1 alpla2_1 alplas_1 alplao_1     PLA Type-07 woodland DIGITAL camo + helmet / soft cap; special ops in
                                                   black-grey urban digital; officer in olive service jacket, peaked cap
  ar       alarm1_1 alarm2_1 alarmo_1              desert army: tan 'chocolate-chip'-free 3-colour desert camo + tan beret;
                                                   red-white SHEMAGH over the head (militia); officer olive, red beret
  sea      alsea1_1 alsea2_1 alseao_1              South-East Asian army: TIGER-STRIPE camo + boonie hat; olive fatigues
                                                   + black bandana; officer in olive with a green beret
  nato     alnat1_1 alnat2_1 alnatm_1              West-European garrison: FLECKTARN 5-colour spots + helmet cover;
                                                   military police in olive with a white MP band and a white cap cover
  alpine   alalp1_1 alalp2_1 alalpc_1              mountain troops: winter over-whites with grey-green breakup + white
                                                   helmet; airbase crew: dark blue flight jacket, grey trousers, beanie

    import alskins
    names = alskins.add_skins(OVERLAY, MAP, factions=['cn'])     # after X.finish / the forge (overlay must exist)
    m.location_skins = lambda: old() | set(names)                # (builders do this for their guard skins)
    lodfix.apply(..., extra={**alskins.lod_rows(names)})
    python -P tools/alskins.py preview [out_dir]                 # sheets + 3D bind-pose renders at 10 / 60 / 150 m
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, wreck
import skinforge as SF
import jrskins as JR

GAME = wreck.GAME
_soft, _noise, _rect, recolor, _lum = SF._soft_ellipse, SF._noise, SF._rect, SF.recolor, SF._lum
JACKET, LEGS, SLEEVES, HANDS = JR.JACKET, JR.LEGS, JR.SLEEVES, JR.HANDS
BOOTS, HAT, BADGE = JR.BOOTS, JR.HAT, JR.BADGE

FACTIONS = {
    'cn': ['alpla1_1', 'alpla2_1', 'alplas_1', 'alplao_1'],
    'ar': ['alarm1_1', 'alarm2_1', 'alarmo_1'],
    'sea': ['alsea1_1', 'alsea2_1', 'alseao_1'],
    'nato': ['alnat1_1', 'alnat2_1', 'alnatm_1'],
    'alpine': ['alalp1_1', 'alalp2_1', 'alalpc_1'],
}
NAMES = [n for v in FACTIONS.values() for n in v]
ROLE = {'alpla1_1': 'guard', 'alpla2_1': 'guard', 'alplas_1': 'elite', 'alplao_1': 'officer',
        'alarm1_1': 'guard', 'alarm2_1': 'militia', 'alarmo_1': 'officer',
        'alsea1_1': 'guard', 'alsea2_1': 'guard', 'alseao_1': 'officer',
        'alnat1_1': 'guard', 'alnat2_1': 'guard', 'alnatm_1': 'police',
        'alalp1_1': 'guard', 'alalp2_1': 'guard', 'alalpc_1': 'crew'}


SHEMAGH = (0.62, 0.10, 0.10)                                  # (the militia scarf's dark check; a mission may recolour it before add_skins)


def _shade(reg):
    L = _lum(reg)
    return np.clip(L / max(1e-6, float(np.percentile(L, 90))), 0, 1.3)


# ===================================================================================================== camouflage patterns
def _apply(img, box, col, keep=0.15):
    """paint a (h, w, 3) colour field into box, multiplied by the shipped shading"""
    reg = img[_rect(img, *box)]
    sh = 0.18 + 0.85 * _shade(reg)
    reg[..., :3] = np.clip(col * sh[..., None] * (1 - keep) + reg[..., :3] * keep, 0, 1)


def digital(h, w, rng, cols, cell=6, scales=(4, 10)):
    """PLA Type-07 style pixelated camo: blobs from noise, quantised to square cells"""
    gh, gw = max(2, -(-h // cell)), max(2, -(-w // cell))
    out = np.empty((gh, gw, 3)); out[:] = cols[0]
    for k, c in enumerate(cols[1:]):
        n = _noise(gh, gw, rng, scale=scales[k % len(scales)], octaves=2)
        thr = np.percentile(n, 100 - [38, 26, 14][k % 3])
        out[n > thr] = c
    return np.repeat(np.repeat(out, cell, 0), cell, 1)[:h, :w]


def flecktarn(h, w, rng, cols=((0.42, 0.42, 0.28), (0.30, 0.33, 0.20), (0.36, 0.26, 0.16), (0.20, 0.25, 0.14), (0.07, 0.07, 0.06))):
    """German 5-colour spot camo: many small round spots in clusters"""
    out = np.empty((h, w, 3)); out[:] = cols[0]
    yy, xx = np.mgrid[0:h, 0:w]
    for k, c in enumerate(cols[1:]):
        n_sp = int(h * w / (90.0 if k < 3 else 160.0))
        cy = rng.integers(0, h, n_sp); cx = rng.integers(0, w, n_sp)
        cl = _noise(h, w, rng, scale=6, octaves=2) > (0.48 if k < 3 else 0.55)
        r = 2.2 + rng.random(n_sp) * (3.0 if k < 3 else 2.0)
        mask = np.zeros((h, w), bool)
        for y0, x0, rr in zip(cy, cx, r):
            if not cl[y0, x0]:
                continue
            y1, y2, x1, x2 = max(0, int(y0 - rr)), min(h, int(y0 + rr) + 1), max(0, int(x0 - rr)), min(w, int(x0 + rr) + 1)
            mask[y1:y2, x1:x2] |= (yy[y1:y2, x1:x2] - y0) ** 2 + (xx[y1:y2, x1:x2] - x0) ** 2 <= rr * rr
        out[mask] = c
    return out


def tiger(h, w, rng, cols=((0.40, 0.42, 0.26), (0.22, 0.28, 0.14), (0.30, 0.22, 0.13), (0.06, 0.06, 0.05))):
    """tiger stripe: horizontal brush strokes, black stripes on top"""
    out = np.empty((h, w, 3)); out[:] = cols[0]
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    for k, c in enumerate(cols[1:]):
        n = _noise(h, w, rng, scale=8, octaves=2)
        band = np.sin(yy / h * 2 * math.pi * (9 + 4 * k) + 6 * n + 3 * k + xx / w * 2.0)
        thin = _noise(h, w, rng, scale=3, octaves=2)
        out[(band > (0.62 if k < 2 else 0.45)) & (thin > (0.35 if k < 2 else 0.22))] = c
    return out


def desert3(h, w, rng, cols=((0.74, 0.64, 0.47), (0.58, 0.50, 0.34), (0.45, 0.36, 0.24))):
    """3-colour desert: soft large blobs (sand / light brown / brown)"""
    out = np.empty((h, w, 3)); out[:] = cols[0]
    for k, c in enumerate(cols[1:]):
        n = _noise(h, w, rng, scale=5 + 2 * k, octaves=3)
        out[n > np.percentile(n, 62 + 12 * k)] = c
    return out


def winter(h, w, rng):
    out = np.empty((h, w, 3)); out[:] = (0.86, 0.87, 0.88)
    n = _noise(h, w, rng, scale=6, octaves=3)
    out[n > np.percentile(n, 84)] = (0.55, 0.58, 0.56)
    n2 = _noise(h, w, rng, scale=12, octaves=2)
    out[n2 > np.percentile(n2, 93)] = (0.36, 0.40, 0.34)
    return out


def _camo(img, fn, rng, boxes=(JACKET, SLEEVES, LEGS), **kw):
    for box in boxes:
        reg = img[_rect(img, *box)]
        h, w = reg.shape[:2]
        _apply(img, box, fn(h, w, rng, **kw) if kw else fn(h, w, rng))


def _rig(img, col, pouches=True):
    H, W = img.shape[:2]
    y0, y1, x0, x1 = int(0.07 * H), int(0.38 * H), int(0.05 * W), int(0.54 * W)
    v = img[y0:y1, x0:x1]
    v[..., :3] = np.clip(np.array(col) * (0.30 + 0.80 * _shade(v))[..., None], 0, 1)
    if pouches:
        for x in (0.09, 0.18, 0.39, 0.48):
            img[int(0.22 * H):int(0.34 * H), int(x * W):int((x + 0.06) * W), :3] *= 0.66
    img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = np.array(col) * 0.55


def _hat(img, col, rng, knit=False):
    hreg = img[_rect(img, *HAT)]
    sh = (0.40 + 0.75 * _shade(hreg))[..., None]
    k = 1.0
    if knit:
        h_, w_ = hreg.shape[:2]
        k = (0.88 + 0.24 * _noise(h_, w_, rng, scale=1, octaves=2))[..., None]
    hreg[..., :3] = np.clip(np.asarray(col)[None, None, :] * sh * k, 0, 1)


def _hat_pattern(img, fn, rng):
    hreg = img[_rect(img, *HAT)]
    h_, w_ = hreg.shape[:2]
    hreg[..., :3] = np.clip(fn(h_, w_, rng) * (0.40 + 0.75 * _shade(hreg))[..., None], 0, 1)


def _flag(img, box, kind):
    """small sleeve flag / patch: 'cn' (red, gold star), 'de' (black-red-gold), 'mp' (white band, black MP)"""
    from PIL import Image, ImageDraw, ImageFont
    H, W = img.shape[:2]
    x0, y0, x1, y1 = int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)
    w, h = x1 - x0, y1 - y0
    im = Image.new('RGB', (w * 4, h * 4), (0, 0, 0)); dr = ImageDraw.Draw(im)
    if kind == 'cn':
        dr.rectangle([0, 0, w * 4, h * 4], fill=(170, 24, 20))
        cx, cy, r = w * 4 * 0.25, h * 4 * 0.35, min(w, h) * 4 * 0.22
        dr.polygon([(cx + (r if k % 2 == 0 else r * 0.4) * math.cos(-math.pi / 2 + k * math.pi / 5),
                     cy + (r if k % 2 == 0 else r * 0.4) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)], fill=(250, 210, 60))
    elif kind == 'de':
        for k, c in enumerate([(20, 20, 20), (190, 20, 20), (240, 190, 20)]):
            dr.rectangle([0, k * h * 4 / 3, w * 4, (k + 1) * h * 4 / 3], fill=c)
    elif kind == 'mp':
        dr.rectangle([0, 0, w * 4, h * 4], fill=(235, 235, 230))
        f = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', int(h * 4 * 0.7))
        bb = dr.textbbox((0, 0), 'MP', font=f)
        dr.text(((w * 4 - bb[2]) / 2, (h * 4 - bb[3]) / 2 - bb[1] / 2), 'MP', fill=(15, 15, 15), font=f)
    elif kind == 'tan':
        dr.rectangle([0, 0, w * 4, h * 4], fill=(150, 125, 85))
        dr.ellipse([w * 0.8, h * 0.8, w * 3.2, h * 3.2], outline=(60, 45, 25), width=3)
    a = np.asarray(im.resize((w, h), Image.LANCZOS), float) / 255.0
    img[y0:y1, x0:x1, :3] = a


# ===================================================================================================== bodies
def body(vn, seed):
    rng = np.random.default_rng(seed)
    img = SF.shipped('ch_resg_01').copy()
    H, W = img.shape[:2]
    skin_tone = None
    if vn in ('alpla1_1', 'alpla2_1'):
        cols = [(0.33, 0.37, 0.24), (0.20, 0.27, 0.15), (0.36, 0.29, 0.18), (0.10, 0.11, 0.09)]
        _camo(img, digital, rng, cols=cols, cell=5)
        _rig(img, (0.24, 0.28, 0.17))
        _hat_pattern(img, lambda h, w, r: digital(h, w, r, cols, cell=5), rng) if vn == 'alpla1_1' else _hat(img, (0.24, 0.29, 0.17), rng)
        _flag(img, BADGE, 'cn')
    elif vn == 'alplas_1':
        cols = [(0.30, 0.31, 0.32), (0.16, 0.17, 0.18), (0.42, 0.42, 0.42), (0.06, 0.06, 0.07)]
        _camo(img, digital, rng, cols=cols, cell=4)
        _rig(img, (0.08, 0.08, 0.09))
        _hat(img, (0.07, 0.07, 0.08), rng)
        _flag(img, BADGE, 'cn')
    elif vn == 'alplao_1':
        for box in (JACKET, SLEEVES):
            JR._smooth_recolor(img, _rect(img, *box), (0.27, 0.32, 0.20), keep=0.72, rng=rng, wool=0.18)
        recolor(img, _rect(img, *LEGS), (0.25, 0.29, 0.19), keep_shading=0.88, rng=rng, wool=0.12)
        for k in range(4):
            y = int((0.07 + 0.08 * k) * H); x = int(0.295 * W)
            img[y - 5:y + 5, x - 5:x + 5, :3] = (0.82, 0.70, 0.30)
        for x0 in (0.02, 0.46):                                        # shoulder boards: gold bar on olive
            img[int(0.03 * H):int(0.07 * H), int(x0 * W):int((x0 + 0.11) * W), :3] = (0.28, 0.34, 0.20)
            img[int(0.045 * H):int(0.052 * H), int(x0 * W):int((x0 + 0.11) * W), :3] = (0.84, 0.70, 0.28)
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.10, 0.08, 0.06)
        img[int(0.12 * H):int(0.15 * H), int(0.38 * W):int(0.47 * W), :3] = (0.70, 0.12, 0.10)
        _hat(img, (0.26, 0.31, 0.19), rng)
        y0, y1 = int(0.18 * H), int(0.23 * H)                          # red band on the peaked cap
        img[y0:y1, int(0.59 * W):W, :3] = np.clip(np.array([0.62, 0.08, 0.06]) * (0.5 + 0.6 * _shade(img[y0:y1, int(0.59 * W):W]))[..., None], 0, 1)
        img[int(0.25 * H):int(0.33 * H), int(0.59 * W):W, :3] = (0.03, 0.03, 0.03)
        _flag(img, BADGE, 'cn')
    elif vn in ('alarm1_1', 'alarmo_1'):
        if vn == 'alarm1_1':
            _camo(img, desert3, rng)
            _rig(img, (0.52, 0.44, 0.30))
            _hat(img, (0.55, 0.46, 0.30), rng)                         # tan beret
        else:
            for box in (JACKET, SLEEVES):
                JR._smooth_recolor(img, _rect(img, *box), (0.33, 0.33, 0.22), keep=0.72, rng=rng, wool=0.15)
            recolor(img, _rect(img, *LEGS), (0.31, 0.30, 0.21), keep_shading=0.88, rng=rng, wool=0.12)
            img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.24, 0.15, 0.08)
            for x0 in (0.02, 0.46):
                img[int(0.03 * H):int(0.07 * H), int(x0 * W):int((x0 + 0.11) * W), :3] = (0.30, 0.30, 0.20)
                for k in range(2):
                    xx_ = int((x0 + 0.03 + 0.04 * k) * W)
                    img[int(0.045 * H):int(0.055 * H), xx_:xx_ + 10, :3] = (0.86, 0.72, 0.30)
            _hat(img, (0.56, 0.10, 0.09), rng)                         # red beret
        _flag(img, BADGE, 'tan')
    elif vn == 'alarm2_1':                                             # militia: olive jacket, faded blue-grey trousers, shemagh
        recolor(img, _rect(img, *JACKET), (0.30, 0.31, 0.21), keep_shading=0.88, rng=rng, wool=0.15)
        recolor(img, _rect(img, *SLEEVES), (0.30, 0.31, 0.21), keep_shading=0.88, rng=rng, wool=0.15)
        recolor(img, _rect(img, *LEGS), (0.30, 0.34, 0.40), keep_shading=0.86, rng=rng, wool=0.20)
        _rig(img, (0.36, 0.30, 0.20))
        hreg = img[_rect(img, *HAT)]                                   # the shemagh on the head geometry: red-white check
        h_, w_ = hreg.shape[:2]
        yy, xx = np.mgrid[0:h_, 0:w_]
        chk = (((yy // 6) + (xx // 6)) % 2 == 0)
        col = np.where(chk[..., None], np.array([0.86, 0.84, 0.80]), np.array(SHEMAGH))
        hreg[..., :3] = np.clip(col * (0.45 + 0.70 * _shade(hreg))[..., None], 0, 1)
    elif vn in ('alsea1_1', 'alsea2_1'):
        if vn == 'alsea1_1':
            _camo(img, tiger, rng)
            _rig(img, (0.26, 0.28, 0.17))
            _hat_pattern(img, tiger, rng)                              # boonie hat in tiger stripe
        else:
            for box in (JACKET, SLEEVES, LEGS):
                recolor(img, _rect(img, *box), (0.27, 0.31, 0.19), keep_shading=0.88, rng=rng, wool=0.12)
            _rig(img, (0.20, 0.21, 0.14))
            _hat(img, (0.06, 0.06, 0.06), rng, knit=True)              # black bandana
        recolor(img, _rect(img, *BOOTS), (0.10, 0.09, 0.07), keep_shading=0.6)   # jungle boots
    elif vn == 'alseao_1':
        for box in (JACKET, SLEEVES):
            JR._smooth_recolor(img, _rect(img, *box), (0.28, 0.32, 0.20), keep=0.72, rng=rng, wool=0.12)
        recolor(img, _rect(img, *LEGS), (0.26, 0.30, 0.19), keep_shading=0.88, rng=rng, wool=0.10)
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.12, 0.10, 0.07)
        _hat(img, (0.12, 0.26, 0.14), rng)                             # green beret
    elif vn in ('alnat1_1', 'alnat2_1'):
        _camo(img, flecktarn, rng)
        _rig(img, (0.29, 0.31, 0.21) if vn == 'alnat1_1' else (0.20, 0.22, 0.15))
        _hat_pattern(img, flecktarn, rng)                              # helmet cover in flecktarn
        _flag(img, BADGE, 'de')
    elif vn == 'alnatm_1':
        for box in (JACKET, SLEEVES, LEGS):
            recolor(img, _rect(img, *box), (0.30, 0.31, 0.22), keep_shading=0.88, rng=rng, wool=0.12)
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.86, 0.86, 0.84)   # white belt
        _flag(img, (0.56, 0.47, 0.80, 0.53), 'mp')                     # white MP armband on the sleeve
        _hat(img, (0.88, 0.88, 0.86), rng)                             # white cap cover
        _flag(img, BADGE, 'de')
    elif vn in ('alalp1_1', 'alalp2_1'):
        _camo(img, winter, rng)
        _rig(img, (0.80, 0.81, 0.80) if vn == 'alalp1_1' else (0.36, 0.38, 0.33))
        _hat(img, (0.88, 0.89, 0.90), rng)                             # white helmet cover
        recolor(img, _rect(img, *HANDS), (0.82, 0.83, 0.84), keep_shading=0.8)   # white gloves
    elif vn == 'alalpc_1':
        for box in (JACKET, SLEEVES):
            JR._smooth_recolor(img, _rect(img, *box), (0.10, 0.13, 0.22), keep=0.75, rng=rng, wool=0.08)
        recolor(img, _rect(img, *LEGS), (0.33, 0.34, 0.36), keep_shading=0.88, rng=rng, wool=0.10)
        img[0:int(0.05 * H), int(0.08 * W):int(0.51 * W), :3] = (0.18, 0.20, 0.25)   # knit collar
        cx = int(0.295 * W)
        img[0:int(0.42 * H), cx - int(0.006 * W):cx + int(0.006 * W), :3] = (0.62, 0.60, 0.55)
        img[int(0.12 * H):int(0.16 * H), int(0.12 * W):int(0.24 * W), :3] = (0.75, 0.40, 0.10)   # orange name tab
        _hat(img, (0.12, 0.13, 0.15), rng, knit=True)                  # dark beanie
    if vn not in ('alalp1_1', 'alalp2_1'):
        recolor(img, _rect(img, *HANDS), skin_tone or (0.72, 0.55, 0.44), keep_shading=0.8)
    if vn not in ('alsea1_1', 'alsea2_1'):
        recolor(img, _rect(img, *BOOTS), (0.06, 0.05, 0.045) if 'ar' not in vn[2:5] else (0.42, 0.34, 0.22), keep_shading=0.6)
    return img


# face = (skin tone, beard 0..1, age 0..1, brow, (jaw, eyes, nose, cheeks))
FACES = {
    'alpla1_1': ((0.86, 0.72, 0.58), 0.0, 0.15, 0.55, (0.98, 0.94, 0.96, 1.04)),
    'alpla2_1': ((0.80, 0.66, 0.52), 0.05, 0.35, 0.65, (1.04, 0.92, 0.98, 1.08)),
    'alplas_1': ((0.82, 0.68, 0.54), 0.0, 0.30, 0.70, (1.06, 0.92, 0.96, 1.02)),
    'alplao_1': ((0.84, 0.70, 0.57), 0.0, 0.75, 0.70, (1.04, 0.93, 0.98, 1.06)),
    'alarm1_1': ((0.66, 0.50, 0.38), 0.55, 0.30, 0.85, (1.04, 1.00, 1.08, 1.00)),
    'alarm2_1': ((0.60, 0.44, 0.33), 0.95, 0.45, 0.90, (1.08, 1.02, 1.10, 1.04)),
    'alarmo_1': ((0.64, 0.48, 0.36), 0.35, 0.80, 0.90, (1.06, 0.98, 1.08, 1.06)),
    'alsea1_1': ((0.72, 0.56, 0.40), 0.0, 0.20, 0.55, (0.96, 0.96, 0.98, 1.06)),
    'alsea2_1': ((0.64, 0.48, 0.34), 0.10, 0.35, 0.60, (1.00, 0.98, 1.00, 1.08)),
    'alseao_1': ((0.70, 0.54, 0.40), 0.0, 0.70, 0.65, (1.02, 0.96, 1.00, 1.04)),
    'alnat1_1': ((0.88, 0.72, 0.64), 0.25, 0.25, 0.55, (1.04, 1.00, 1.04, 0.98)),
    'alnat2_1': ((0.84, 0.66, 0.56), 0.60, 0.40, 0.70, (1.08, 1.02, 1.02, 1.02)),
    'alnatm_1': ((0.90, 0.75, 0.66), 0.0, 0.35, 0.50, (1.00, 1.02, 1.06, 0.96)),
    'alalp1_1': ((0.88, 0.70, 0.62), 0.35, 0.30, 0.60, (1.06, 1.00, 1.02, 1.00)),
    'alalp2_1': ((0.82, 0.64, 0.54), 0.10, 0.20, 0.55, (0.96, 1.02, 1.00, 0.96)),
    'alalpc_1': ((0.86, 0.68, 0.58), 0.0, 0.55, 0.60, (1.02, 0.98, 1.04, 1.00)),
}


def _monolid(img, k=0.5):
    """softer, narrower eye shadows + flatter brow ridge for East / South-East Asian faces"""
    H, W = img.shape[:2]
    for xc in (0.455, 0.545):
        e_ = _soft(H, W, 0.345 * H, xc * W, 0.010 * H, 0.032 * W, 0.6)
        img[..., :3] = img[..., :3] * (1 - 0.35 * k * e_[..., None])


def head(vn, seed):
    rng = np.random.default_rng(seed)
    img = SF.shipped('ch_resg_00').copy()
    grey = 0.06
    JR._face(img, FACES[vn], rng, grey=grey)
    if vn[:4] in ('alpl', 'alse'):
        _monolid(img)
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    hair = np.clip((0.23 - yy) / 0.015, 0, 1)                         # short black hair (the shipped strip), all but
    img[..., :3] = img[..., :3] * (1 - hair[..., None]) + 0.05 * hair[..., None]   #  the covered heads below
    if vn in ('alpla1_1', 'alplas_1', 'alnat1_1', 'alnat2_1', 'alalp1_1', 'alalp2_1'):   # helmet rim + chin strap
        col = {'alpla1_1': (0.26, 0.31, 0.19), 'alplas_1': (0.07, 0.07, 0.08), 'alnat1_1': (0.30, 0.32, 0.22),
               'alnat2_1': (0.30, 0.32, 0.22), 'alalp1_1': (0.86, 0.87, 0.88), 'alalp2_1': (0.86, 0.87, 0.88)}[vn]
        a = np.clip((0.245 + np.where((xx < 0.22) | (xx > 0.78), 0.10, 0.0) - yy) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.array(col) * (0.8 + 0.3 * _noise(H, W, rng, 1, 2))[..., None] * a[..., None]
        for xc in (0.16, 0.84):
            st = (np.abs(xx - xc) < 0.012) & (yy > 0.30) & (yy < 0.72)
            img[st, :3] = (0.08, 0.07, 0.05)
    elif vn == 'alarm2_1':                                             # shemagh wrapped round the head, face open
        chk = ((((yy * H) // 10) + ((xx * W) // 10)) % 2 == 0)
        col = np.where(chk[..., None], np.array([0.86, 0.84, 0.80]), np.array(SHEMAGH))
        a = np.clip((0.26 - yy) / 0.012, 0, 1) + np.clip(((xx < 0.24) | (xx > 0.76)) * (yy < 0.75) * 1.0, 0, 1)
        a = np.clip(a, 0, 1)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + col * a[..., None] * 0.9
    elif vn in ('alarm1_1', 'alarmo_1', 'alseao_1'):                  # beret: band low over one side
        col = {'alarm1_1': (0.55, 0.46, 0.30), 'alarmo_1': (0.56, 0.10, 0.09), 'alseao_1': (0.12, 0.26, 0.14)}[vn]
        a = np.clip((0.225 + 0.02 * (xx - 0.5) - yy) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.array(col) * a[..., None]
    elif vn in ('alsea1_1',):                                          # boonie hat brim shadow
        a = np.clip((0.25 - yy) / 0.012, 0, 1)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.array([0.30, 0.32, 0.20]) * a[..., None]
    elif vn in ('alsea2_1', 'alalpc_1'):
        JR._cap_band(img, (0.06, 0.06, 0.06) if vn == 'alsea2_1' else (0.12, 0.13, 0.15), rng)
    elif vn in ('alplao_1', 'alnatm_1'):                              # peaked cap
        col, band = ((0.26, 0.31, 0.19), (0.62, 0.08, 0.06)) if vn == 'alplao_1' else ((0.88, 0.88, 0.86), (0.10, 0.10, 0.10))
        a = np.clip((0.235 - yy) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.array(col) * a[..., None]
        b = np.clip((0.235 - yy) / 0.01, 0, 1) * np.clip((yy - 0.19) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - b[..., None]) + np.array(band) * b[..., None]
    elif vn == 'alpla2_1':                                             # soft cap
        JR._cap_band(img, (0.24, 0.29, 0.17), rng, edge=0.23, side_drop=0.03)
    return img


def _textures(names):
    out = {}
    for k, vn in enumerate(names):
        i = NAMES.index(vn)
        out[vn] = [('al_%sb' % vn[2:-2], body(vn, 7100 + i)), ('al_%sh' % vn[2:-2], head(vn, 7200 + i))]
    return out


def add_skins(overlay_dir, level_name, factions=None, names=None, log=print):
    """register the skins (VNAM over the resg_1 mesh + 2 LOCAL textures each) in the overlay manifest + banks"""
    names = list(names or [n for f in (factions or FACTIONS) for n in FACTIONS[f]])
    paths = wreck._ensure_overlay(overlay_dir, level_name)
    m = mtp.read(paths['mtp'])
    clash = [n for n in names if n in m['VNAM']]
    if clash:
        raise ValueError('skins already in %s: %s' % (paths['mtp'], clash))
    mp_mtp = os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'multiplayer.mtp')
    resg_mesh, _ = SF._mesh_entry(mp_mtp, 'resg1_1')
    mform, mch, mhdr = ilff.read(open(paths['models'], 'rb').read())
    have_m = {d.rstrip(b'\0').decode('latin1') for t, d, a in mch if t == b'NAME'}
    key = 'LOCAL:models/%s.mef' % resg_mesh
    if key not in have_m:
        ch_, names_ = SF._bank(os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'models', 'multiplayer.res'))
        mch.append((b'NAME', key.encode('latin1') + b'\0', 4)); mch.append((b'BODY', ch_[names_[key]][1], 4))
    if resg_mesh not in m['MODS']:
        m['MODS'].append(resg_mesh)
    form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
    have_t = {d.rstrip(b'\0').decode('latin1') for t, d, a in ch if t == b'NAME'}
    gtt = {}
    for vn, slots in _textures(names).items():
        for tname, img in slots:
            k_ = 'LOCAL:textures/%s.tex' % tname
            if k_ not in have_t:
                ch.append((b'NAME', k_.encode('latin1') + b'\0', 4)); ch.append((b'BODY', wreck.tex_mode2(img), 4)); have_t.add(k_)
            if tname not in m['TEXF']:
                m['TEXF'].append(tname)
            ti = m['TEXF'].index(tname)
            for i, (t_, pl) in enumerate(m['GTT']):
                if t_ == ti and pl == -1:
                    gtt[tname] = i; break
            else:
                m['GTT'].append([ti, -1]); gtt[tname] = len(m['GTT']) - 1
        g_ = [gtt[t] for t, _ in slots]
        assert all(x < mtp.COMMON_BIT for x in g_), (vn, g_)
        m['VNAM'].append(vn); m['INST'].append([m['MODS'].index(resg_mesh), g_])
    for path, blob in ((paths['textures'], ilff.write(form, ch, hdr[1] or 4)), (paths['models'], ilff.write(mform, mch, mhdr[1] or 4)),
                       (paths['mtp'], mtp.write(m))):
        tmp = path + '.al.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    b2 = wreck.Bank(paths['mtp'], paths['models'], paths['textures'])
    probs = [n for n in names if b2.res.get(n) is None]
    if set(b2.m['TEXF']) - set(b2.tex):
        probs.append('TEXF entries without a texture')
    log('alskins: %s registered (mesh %s), problems %s' % (names, resg_mesh, probs or 'none'))
    assert not probs, probs
    return names


def lod_rows(names=None):
    """lod.qvm rows (1400 m like jrskins): a skin without one is drawn only to ~10 x its radius"""
    return {n: [1344.0, 1358.0, 1372.0, 1386.0, 1400.0] for n in (names or NAMES)}


def preview(out_dir):
    """texture sheets + bind-pose renders (front, back, 10/60/150 m) via jrskins' renderer"""
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    tex = _textures(NAMES)
    tiles = []
    for vn in NAMES:
        b, h = tex[vn][0][1], tex[vn][1][1]
        bi = Image.fromarray((np.clip(b[..., :3], 0, 1) * 255).astype('u1')).resize((256, 256))
        hi = Image.fromarray((np.clip(h[..., :3], 0, 1) * 255).astype('u1')).resize((128, 256))
        t = Image.new('RGB', (384, 256)); t.paste(bi, (0, 0)); t.paste(hi, (256, 0))
        tiles.append((vn, t))
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sh = Image.new('RGB', (cols * 390, rows * 275), (30, 30, 30)); d = ImageDraw.Draw(sh)
    for k, (vn, t) in enumerate(tiles):
        x, y = (k % cols) * 390 + 3, (k // cols) * 275 + 16
        sh.paste(t, (x, y)); d.text((x, y - 14), '%s (%s)' % (vn, ROLE[vn]), fill='yellow')
    p = os.path.join(out_dir, 'skins_sheet.png'); sh.save(p)
    out = [p]
    try:
        out.append(_render(out_dir, tex))
    except Exception as e:
        print('3D render skipped:', e)
    return out


def _render(out_dir, tex):
    """bind-pose renders (jrskins._resg_soup + mefrender) of every skin, front + back - offline, NOT in-game proof"""
    import mefrender
    from PIL import Image, ImageDraw
    P, N, U, groups = JR._resg_soup()
    tiles = []
    for vn in NAMES:
        for lab, brg in (('front', 180.0), ('back', 0.0)):
            sc = mefrender.Scene()
            for slot, T_ in groups:
                mat = sc.material(tex[vn][slot][1], color=(0.6, 0.6, 0.6))
                Pp = P[T_]
                fn = -np.cross(Pp[:, 1] - Pp[:, 0], Pp[:, 2] - Pp[:, 0])
                fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
                sc.add_tris(Pp, np.repeat(fn[:, None], 3, 1), U[T_], mat, double=True)
            c = np.array([0, 0, 0.95]) * 4096
            b = math.radians(brg)
            eye = c + np.array([math.sin(b) * 3.2, -math.cos(b) * 3.2, 0.25]) * 4096
            tiles.append(('%s %s' % (vn, lab), sc.render(eye, c, size=(200, 300), fov=40, ss=1)))
    cols, W, H = 8, 200, 300
    rows = (len(tiles) + cols - 1) // cols
    sh = Image.new('RGB', (cols * W, rows * (H + 16)), (90, 95, 100)); dr = ImageDraw.Draw(sh)
    for i, (lab, im) in enumerate(tiles):
        x, y = (i % cols) * W, (i // cols) * (H + 16)
        sh.paste(im.convert('RGB'), (x, y + 16)); dr.text((x + 3, y + 2), lab, fill='yellow')
    p = os.path.join(out_dir, 'skins_3d.png'); sh.save(p)
    return p


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'preview':
        print(preview(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'assetlib', 'prev')))
