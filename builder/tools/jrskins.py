"""jrskins - NEW character skins + faces for Operation Joyride (ART, WP-D, 2026-10-30; owner rule 3: new skins and faces
every mission). Painted over the shipped resg_1 layout (body ch_resg_01 1024^2, head ch_resg_00 512x1024; skinforge.py
notes), the shipped luminance kept as shading, nothing copied from another game. Every slot is a LOCAL texture (COMMON_BIT
slots crashed igi2.exe+0x16fda0, srkit 10-24) and every skin gets a lod.qvm row (lod_rows: 1400 m), else it vanishes
beyond ~10 m (owner 10-18 'skins invisible').

  jrk1_1 jrk2_1 jrk3_1   Kestrel contractors on Sokol-9: olive RAIN SMOCKS (wet streaks), knit watch caps (black / olive
                         / grey), the falcon patch on the shoulder, three faces (stubble, full beard + older, young)
  jrq1_1                 QRF: 'flora' stripe camo (green / brown / sand), olive helmet cover, tan chest rig, a 4th face
  jrc1_1                 the valley checkpoint: black kit, black rig, gloves, a black balaclava (eyes + mouth open)
  jrcrew_1               ground crew: ORANGE coveralls, reflective bands, ear defenders (red cups) over a dark cap
  jrtech_1               technician: BLUE coverall, grey cap, rolled sleeves, a 6th face
  jrcmd_1                the battery commander: olive-grey officer jacket, shoulder boards, PEAKED cap (red band, black
                         visor), polished boots, an older stern face
  jrshrike_1             Major Lev Rudnev 'Shrike': olive flight suit, brown leather flight jacket, a red SHRIKE patch,
                         grey hair, grey moustache, an older hard face

    import jrskins; jrskins.add(B)                       # builder hook S4 (sets B.SKINS, B.GUARD_SKINS)
    jrskins.add_skins(overlay_dir, 'forestraid')         # plain use
    python -P tools/jrskins.py preview [out_dir]         # sheets + 3D bind-pose renders (front / back / 10-60-150 m)
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, wreck
import skinforge as SF
import itskins as IS

GAME = wreck.GAME
BASE = ['jrk1_1', 'jrk2_1', 'jrk3_1']
QRF, CHECK, CREW, TECH, CMD, SHRIKE = 'jrq1_1', 'jrc1_1', 'jrcrew_1', 'jrtech_1', 'jrcmd_1', 'jrshrike_1'
NAMES = BASE + [QRF, CHECK, CREW, TECH, CMD, SHRIKE]
GUARD_SKINS = {'base': list(BASE), 'qrf': [QRF], 'black': [CHECK], 'crew': [CREW], 'tech': [TECH], 'cmd': CMD, 'pilot': SHRIKE}
VARIANTS = {'lineup': 'all 9 skins as standing actors 10 / 60 / 150 m in front of the start (play) + a 3-shot intro at the '
                      'same distances (cutscene): the 3-distance skin + LOD check'}
_soft, _noise, _rect, recolor, _lum = SF._soft_ellipse, SF._noise, SF._rect, SF.recolor, SF._lum
JACKET, LEGS, SLEEVES, HANDS = (0.0, 0.0, 0.59, 0.44), (0.0, 0.44, 0.56, 1.0), (0.56, 0.44, 0.80, 0.83), (0.82, 0.33, 1.0, 0.44)
SOLES, BOOTS, HAT, PATCH = (0.59, 0.33, 0.82, 0.44), (0.75, 0.83, 1.0, 1.0), (0.59, 0.0, 1.0, 0.33), (0.56, 0.83, 0.75, 1.0)
BADGE = (0.56, 0.83, 0.64, 0.93)                   # the small shoulder emblem inside PATCH (the shipped eagle badge)
HAT_BADGE = (0.70, 0.04, 0.80, 0.15)               # the badge on the shipped cap


def _wet(img, sl, rng, amount=0.20):
    """rain-wet: darker cloth with light streaks running down (the Sokol-9 drizzle)"""
    reg = img[sl]
    h, w = reg.shape[:2]
    n = _noise(h, w, rng, scale=2, octaves=3)
    streak = (np.sin(np.mgrid[0:h, 0:w][1] * 0.33 + 6 * n) > 0.86).astype(float)
    reg[..., :3] = np.clip(reg[..., :3] * 0.90 + amount * 0.22 * streak[..., None], 0, 1)


def _shade(reg):
    L = _lum(reg)
    return np.clip(L / max(1e-6, float(np.percentile(L, 90))), 0, 1.3)


def _smooth_recolor(img, sl, rgb, keep=0.75, sigma=7.0, rng=None, wool=0.0):
    """recolor with a BLURRED shading: folds stay, the shipped vest's pouches and straps fade (officer jacket, leather)"""
    from scipy import ndimage
    reg = img[sl]
    L = ndimage.gaussian_filter(_lum(reg), sigma)
    sh = (1 - keep) + keep * np.clip(L / max(1e-6, float(np.percentile(L, 90))), 0, 1.25)
    col = np.asarray(rgb, float)[None, None, :] * sh[..., None]
    if wool and rng is not None:
        n = _noise(reg.shape[0], reg.shape[1], rng, scale=2, octaves=2)
        col = col * (1 - wool + wool * (0.8 + 0.4 * n))[..., None]
    reg[..., :3] = np.clip(col, 0, 1)


def _stripes(img, sl, cols, rng, scale=10):
    """'flora'-like vertical brush stripes (Russian army pattern): cols[0] base + stripes of the others, shading kept"""
    reg = img[sl]
    h, w = reg.shape[:2]
    sh = 0.15 + 0.85 * _shade(reg)
    n = _noise(h, w, rng, scale=scale, octaves=2)
    xx = np.mgrid[0:h, 0:w][1].astype(float)
    band = np.sin(xx / w * 2 * math.pi * 7 + 5 * n)
    col = np.empty((h, w, 3)); col[:] = cols[0]
    col[band > 0.55] = cols[1]
    if len(cols) > 2:
        col[(band < -0.70)] = cols[2]
    reg[..., :3] = np.clip(col * sh[..., None], 0, 1)


def _patch(img, box, kind):
    """a sewn patch painted into the (fractional) box: 'falcon' (Kestrel: a black falcon stooping on a tan disc),
    'shrike' (red shield, a black shrike bird), 'flag' (a plain grey-blue tab)"""
    from PIL import Image, ImageDraw
    H, W = img.shape[:2]
    x0, y0, x1, y1 = int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)
    w, h = x1 - x0, y1 - y0
    S = 4
    im = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    if kind == 'falcon':
        dr.ellipse([2 * S, 2 * S, (w - 2) * S, (h - 2) * S], fill=(176, 150, 100, 255), outline=(40, 34, 24, 255), width=2 * S)
        cx, cy = w * S / 2, h * S / 2
        k = min(w, h) * S / 2.4
        body = [(cx, cy - 0.55 * k), (cx + 0.18 * k, cy - 0.1 * k), (cx + 0.95 * k, cy - 0.45 * k), (cx + 0.35 * k, cy + 0.15 * k),
                (cx + 0.12 * k, cy + 0.75 * k), (cx, cy + 0.55 * k), (cx - 0.12 * k, cy + 0.75 * k), (cx - 0.35 * k, cy + 0.15 * k),
                (cx - 0.95 * k, cy - 0.45 * k), (cx - 0.18 * k, cy - 0.1 * k)]
        dr.polygon(body, fill=(22, 20, 18, 255))
        dr.ellipse([cx - 0.12 * k, cy - 0.68 * k, cx + 0.12 * k, cy - 0.44 * k], fill=(22, 20, 18, 255))
    elif kind == 'shrike':
        dr.polygon([(2 * S, 2 * S), ((w - 2) * S, 2 * S), ((w - 2) * S, h * S * 0.62), (w * S / 2, (h - 2) * S), (2 * S, h * S * 0.62)],
                   fill=(170, 26, 22, 255), outline=(240, 220, 180, 255))
        cx, cy = w * S / 2, h * S * 0.42
        k = min(w, h) * S / 3.0
        dr.polygon([(cx - 0.9 * k, cy - 0.1 * k), (cx + 0.55 * k, cy - 0.35 * k), (cx + 0.95 * k, cy - 0.15 * k), (cx + 0.5 * k, cy + 0.05 * k),
                    (cx + 0.1 * k, cy + 0.6 * k), (cx - 0.25 * k, cy + 0.15 * k)], fill=(15, 12, 12, 255))
        dr.line([(cx + 0.55 * k, cy - 0.35 * k), (cx + 0.95 * k, cy - 0.45 * k)], fill=(15, 12, 12, 255), width=2 * S)
    else:
        dr.rectangle([2 * S, 2 * S, (w - 2) * S, (h - 2) * S], fill=(70, 84, 104, 255), outline=(30, 30, 30, 255), width=S)
    a = np.asarray(im.resize((w, h), Image.LANCZOS), float) / 255.0
    reg = img[y0:y1, x0:x1]
    al = a[..., 3:4]
    reg[..., :3] = reg[..., :3] * (1 - al) + a[..., :3] * al


def _floor_lum(img, sl, frac):
    """lift the shipped texture's darkest parts in sl to frac x its 90th-percentile luminance (the vest's black ammo
    pouches) so a recolour paints them in the outfit's colour instead of leaving black pouches on a coverall"""
    reg = img[sl]
    L = _lum(reg)
    t = frac * float(np.percentile(L, 90))
    k = np.where(L < t, t / np.maximum(L, 1e-4), 1.0)
    reg[..., :3] = np.clip(reg[..., :3] * k[..., None], 0, 1)


def body(kind, seed):
    rng = np.random.default_rng(seed)
    img = SF.shipped('ch_resg_01').copy()
    H, W = img.shape[:2]
    if kind in ('crew', 'tech', 'cmd', 'shrike'):   # (review 10-30: no black ammo pouches on coveralls, the officer, the pilot)
        _floor_lum(img, _rect(img, *JACKET), 0.55)
    hat_col = None
    if kind in ('k1', 'k2', 'k3'):
        smock = {'k1': (0.24, 0.27, 0.17), 'k2': (0.19, 0.21, 0.13), 'k3': (0.30, 0.31, 0.21)}[kind]
        trous = {'k1': (0.20, 0.20, 0.19), 'k2': (0.27, 0.27, 0.19), 'k3': (0.12, 0.12, 0.12)}[kind]
        recolor(img, _rect(img, *JACKET), smock, keep_shading=0.88, rng=rng, wool=0.10)
        recolor(img, _rect(img, *SLEEVES), smock, keep_shading=0.88, rng=rng, wool=0.10)
        recolor(img, _rect(img, *LEGS), trous, keep_shading=0.85, rng=rng, wool=0.10)
        # the smock's zipped storm flap down the front + two big lower pockets, a dark yoke over the shoulders (rain cape)
        cx = int(0.295 * W)
        img[0:int(0.40 * H), cx - int(0.010 * W):cx + int(0.010 * W), :3] *= 0.55
        for x in (0.06, 0.37):
            img[int(0.26 * H):int(0.38 * H), int(x * W):int((x + 0.15) * W), :3] *= 0.80
            img[int(0.26 * H):int(0.272 * H), int(x * W):int((x + 0.15) * W), :3] *= 0.60     # pocket flaps
        img[0:int(0.07 * H), 0:int(0.59 * W), :3] *= 0.78
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.07, 0.07, 0.06)                     # webbing belt
        _wet(img, _rect(img, *JACKET), rng); _wet(img, _rect(img, *SLEEVES), rng); _wet(img, _rect(img, *LEGS), rng, 0.12)
        hat_col = {'k1': (0.07, 0.07, 0.07), 'k2': (0.22, 0.24, 0.15), 'k3': (0.30, 0.30, 0.31)}[kind]
        recolor(img, _rect(img, *HANDS), (0.10, 0.09, 0.08) if kind != 'k3' else (0.72, 0.55, 0.44), keep_shading=0.8)
        recolor(img, _rect(img, *BOOTS), (0.07, 0.06, 0.05), keep_shading=0.65)
        _patch(img, BADGE, 'falcon')
    elif kind == 'qrf':
        for box in (JACKET, SLEEVES, LEGS):
            _stripes(img, _rect(img, *box), [(0.33, 0.36, 0.24), (0.20, 0.16, 0.10), (0.52, 0.48, 0.34)], rng)
        y0, y1, x0, x1 = int(0.06 * H), int(0.38 * H), int(0.05 * W), int(0.54 * W)                    # tan plate carrier
        v = img[y0:y1, x0:x1]
        v[..., :3] = np.clip(np.array([0.46, 0.40, 0.28]) * (0.30 + 0.80 * _shade(v))[..., None], 0, 1)
        for x in (0.09, 0.18, 0.39, 0.48):
            img[int(0.22 * H):int(0.34 * H), int(x * W):int((x + 0.06) * W), :3] *= 0.62
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.18, 0.15, 0.10)
        hat_col = (0.28, 0.31, 0.20)                                                                   # helmet cover
        recolor(img, _rect(img, *HANDS), (0.20, 0.18, 0.13), keep_shading=0.8)
        recolor(img, _rect(img, *BOOTS), (0.10, 0.08, 0.06), keep_shading=0.65)
        _patch(img, BADGE, 'falcon')
        _wet(img, _rect(img, *JACKET), rng, 0.12)
    elif kind == 'check':
        for box in (JACKET, SLEEVES, LEGS):                                                           # (charcoal, not 0: the
            recolor(img, _rect(img, *box), (0.095, 0.095, 0.10), keep_shading=0.9, rng=rng, wool=0.10)   #  shape reads at dusk)
        img[int(0.08 * H):int(0.38 * H), int(0.06 * W):int(0.53 * W), :3] *= 0.62                       # black rig
        for x in (0.10, 0.19, 0.40, 0.49):
            img[int(0.20 * H):int(0.31 * H), int(x * W):int((x + 0.06) * W), :3] *= 0.55
        hat_col = (0.05, 0.05, 0.05)
        recolor(img, _rect(img, *HANDS), (0.04, 0.04, 0.04), keep_shading=0.8)
        recolor(img, _rect(img, *BOOTS), (0.05, 0.05, 0.05), keep_shading=0.6)
        _patch(img, BADGE, 'flag')
    elif kind in ('crew', 'tech'):
        col = (0.92, 0.42, 0.08) if kind == 'crew' else (0.14, 0.24, 0.50)
        for box in (JACKET, SLEEVES, LEGS):
            recolor(img, _rect(img, *box), col, keep_shading=0.86, rng=rng, wool=0.06)
        if kind == 'crew':                                                                             # reflective bands
            for yb in (0.30, 0.66, 0.88):
                img[int(yb * H):int((yb + 0.018) * H), 0:int(0.59 * W), :3] = (0.82, 0.84, 0.80)
            img[int(0.70 * H):int(0.718 * H), int(0.56 * W):int(0.80 * W), :3] = (0.82, 0.84, 0.80)
            hat_col = (0.10, 0.10, 0.11)
        else:
            cx = int(0.295 * W)                                                                        # zip + chest pocket + name tab
            img[0:int(0.42 * H), cx - int(0.006 * W):cx + int(0.006 * W), :3] = (0.55, 0.55, 0.57)
            img[int(0.10 * H):int(0.16 * H), int(0.12 * W):int(0.22 * W), :3] *= 0.75
            img[int(0.09 * H):int(0.105 * H), int(0.36 * W):int(0.48 * W), :3] = (0.85, 0.85, 0.82)
            # rolled-up sleeves: the lower part of the sleeve region bare forearm
            sl = _rect(img, 0.56, 0.70, 0.80, 0.83)
            recolor(img, sl, (0.74, 0.56, 0.45), keep_shading=0.75)
            img[int(0.695 * H):int(0.715 * H), int(0.56 * W):int(0.80 * W), :3] = np.array(col) * 0.7     # the roll
            hat_col = (0.36, 0.37, 0.39)
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = np.array(col) * 0.55
        recolor(img, _rect(img, *HANDS), (0.72, 0.55, 0.44) if kind == 'tech' else (0.30, 0.22, 0.12), keep_shading=0.8)
        recolor(img, _rect(img, *BOOTS), (0.12, 0.10, 0.08), keep_shading=0.65)
        _patch(img, BADGE, 'flag')
    elif kind == 'cmd':
        for box in (JACKET, SLEEVES):
            _smooth_recolor(img, _rect(img, *box), (0.30, 0.32, 0.25), keep=0.72, rng=rng, wool=0.20)
        recolor(img, _rect(img, *LEGS), (0.24, 0.25, 0.20), keep_shading=0.88, rng=rng, wool=0.15)
        for k in range(5):                                                                            # brass buttons, one row
            y = int((0.06 + 0.07 * k) * H)
            x = int(0.295 * W)
            img[y - 5:y + 5, x - 5:x + 5, :3] = (0.80, 0.68, 0.30)
        for x0 in (0.02, 0.46):                                                                       # shoulder boards (major: one star)
            img[int(0.03 * H):int(0.07 * H), int(x0 * W):int((x0 + 0.11) * W), :3] = (0.30, 0.36, 0.22)
            img[int(0.045 * H):int(0.055 * H), int((x0 + 0.05) * W):int((x0 + 0.06) * W), :3] = (0.86, 0.72, 0.30)
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.22, 0.14, 0.08)                     # brown leather belt
        img[int(0.405 * H):int(0.435 * H), int(0.275 * W):int(0.315 * W), :3] = (0.78, 0.66, 0.30)
        img[int(0.12 * H):int(0.16 * H), int(0.38 * W):int(0.47 * W), :3] = (0.62, 0.12, 0.12)          # ribbon bar
        img[int(0.13 * H):int(0.15 * H), int(0.38 * W):int(0.47 * W), :3] = (0.82, 0.70, 0.22)
        hat_col = (0.26, 0.29, 0.21)
        recolor(img, _rect(img, *HANDS), (0.74, 0.56, 0.46), keep_shading=0.8)
        recolor(img, _rect(img, *BOOTS), (0.04, 0.035, 0.03), keep_shading=0.5)
        _patch(img, BADGE, 'flag')
    elif kind == 'shrike':
        recolor(img, _rect(img, *LEGS), (0.30, 0.32, 0.22), keep_shading=0.86, rng=rng, wool=0.06)    # flight suit
        _smooth_recolor(img, _rect(img, *JACKET), (0.29, 0.17, 0.09), keep=0.78, rng=rng, wool=0.05)  # leather jacket
        _smooth_recolor(img, _rect(img, *SLEEVES), (0.29, 0.17, 0.09), keep=0.78, rng=rng, wool=0.05)
        reg = img[_rect(img, *JACKET)]                                                                # worn leather: lighter scuffs
        n = _noise(reg.shape[0], reg.shape[1], rng, scale=3, octaves=3)
        reg[..., :3] = np.clip(reg[..., :3] * (0.85 + 0.30 * n[..., None]), 0, 1)
        img[0:int(0.05 * H), int(0.08 * W):int(0.51 * W), :3] = (0.58, 0.50, 0.40)                     # sheepskin collar
        cx = int(0.295 * W)
        img[0:int(0.42 * H), cx - int(0.006 * W):cx + int(0.006 * W), :3] = (0.62, 0.60, 0.55)          # zip
        # leg pockets of the flight suit (thigh), a knee board strap
        for x in (0.05, 0.33):
            img[int(0.55 * H):int(0.68 * H), int(x * W):int((x + 0.14) * W), :3] *= 0.80
        img[int(0.74 * H):int(0.755 * H), 0:int(0.28 * W), :3] = (0.10, 0.10, 0.10)
        _patch(img, (0.10, 0.09, 0.20, 0.19), 'shrike')                                              # on the chest
        _patch(img, BADGE, 'shrike')                                                                  # and the shoulder
        hat_col = 'hair'
        recolor(img, _rect(img, *HANDS), (0.18, 0.11, 0.07), keep_shading=0.8)                        # leather gloves
        recolor(img, _rect(img, *BOOTS), (0.06, 0.05, 0.04), keep_shading=0.55)
    pouch = {'cmd': (0.22, 0.14, 0.07), 'shrike': (0.22, 0.14, 0.07), 'crew': (0.60, 0.28, 0.05), 'tech': (0.10, 0.17, 0.36)}.get(kind)
    if pouch:                                     # the modelled waist pouches: holster / tool pouches, not black ammo pouches
        sl_ = _rect(img, 0.82, 0.69, 1.0, 0.83)   #  in the outfit's colour (UV probe 10-30: the pouch faces map to x 0.85..1, y 0.70..0.83)
        _floor_lum(img, sl_, 0.45)
        recolor(img, sl_, pouch, keep_shading=0.8)
    # the cap geometry (top right of the sheet): knit / helmet / peaked cap / grey hair
    hs = _rect(img, *HAT)
    hreg = img[hs]
    sh = (0.40 + 0.75 * _shade(hreg))[..., None]
    if hat_col == 'hair':
        h_, w_ = hreg.shape[:2]
        hair = (0.50 + 0.22 * _noise(h_, w_, rng, scale=1, octaves=3))[..., None] * np.array([0.92, 0.92, 0.94])
        hreg[..., :3] = np.clip(hair * (0.75 + 0.35 * _shade(hreg))[..., None], 0, 1)
    elif hat_col is not None:
        knit = 1.0
        if kind in ('k1', 'k2', 'k3', 'crew', 'tech'):
            h_, w_ = hreg.shape[:2]
            knit = (0.88 + 0.24 * _noise(h_, w_, rng, scale=1, octaves=2))[..., None]
        hreg[..., :3] = np.clip(np.asarray(hat_col)[None, None, :] * sh * knit, 0, 1)
        if kind == 'cmd':                                                                             # red band + cockade
            y0, y1 = int(0.18 * H), int(0.23 * H)
            img[y0:y1, int(0.59 * W):W, :3] = np.clip(np.array([0.58, 0.08, 0.08]) * (0.5 + 0.6 * _shade(img[y0:y1, int(0.59 * W):W]))[..., None], 0, 1)
            yb, xb = int(0.09 * H), int(0.75 * W)
            star = _soft(H, W, yb, xb, 16, 16, 0.3)
            img[..., :3] = img[..., :3] * (1 - star[..., None]) + np.array([0.86, 0.72, 0.28]) * star[..., None]
            img[int(0.25 * H):int(0.33 * H), int(0.59 * W):W, :3] = (0.03, 0.03, 0.03)                  # the black visor part
    return img


# face = (skin tone, beard 0..1, age 0..1, brow, geometry (jaw, eyes, nose, cheeks))
FACES = {'k1': ((0.82, 0.66, 0.56), 0.55, 0.25, 0.60, (1.06, 0.98, 1.02, 1.00)),     # stubble, square jaw
         'k2': ((0.74, 0.57, 0.46), 0.95, 0.55, 0.80, (1.10, 1.02, 1.06, 1.08)),     # full dark beard, broad, older
         'k3': ((0.88, 0.72, 0.62), 0.10, 0.05, 0.40, (0.94, 1.04, 0.98, 0.92)),     # young, clean shaven, narrow
         'qrf': ((0.80, 0.62, 0.50), 0.35, 0.35, 0.70, (1.02, 0.96, 1.08, 0.98)),    # long nose, light stubble
         'crew': ((0.66, 0.48, 0.37), 0.20, 0.30, 0.55, (1.00, 1.04, 0.96, 1.04)),   # darker, round
         'tech': ((0.86, 0.70, 0.60), 0.00, 0.45, 0.45, (0.96, 0.98, 1.04, 0.94)),   # glasses-free bookish, thin
         'cmd': ((0.84, 0.66, 0.56), 0.00, 0.80, 0.95, (1.08, 0.96, 1.06, 1.06)),    # stern, older
         'shrike': ((0.82, 0.64, 0.54), 0.00, 0.95, 0.85, (1.06, 0.97, 1.08, 1.02))}  # old pilot (grey moustache)


def _face(img, face, rng, grey=0.06):
    H, W = img.shape[:2]
    tone, beard, age, brow, geo = face
    SF._warp_face(img, *geo)
    sk = _rect(img, 0.0, 0.18, 1.0, 0.78)
    reg = img[sk]
    L = _lum(reg)[..., None]
    reg[..., :3] = np.clip(np.asarray(tone)[None, None, :] * (0.35 + 0.95 * L / max(1e-6, float(np.percentile(L, 92)))), 0, 1)
    img[sk] = reg
    if beard > 0:
        m_ = _soft(H, W, 0.62 * H, 0.5 * W, 0.13 * H, 0.17 * W, 0.5) - _soft(H, W, 0.585 * H, 0.5 * W, 0.022 * H, 0.05 * W, 0.6)
        a = np.clip(m_, 0, 1) * (0.55 + 0.45 * _noise(H, W, rng, scale=1, octaves=2)) * beard
        img[..., :3] = img[..., :3] * (1 - 0.78 * a[..., None]) + grey * a[..., None]
    for xc in (0.455, 0.545):
        e_ = _soft(H, W, 0.333 * H, xc * W, 0.006 * H * (1 + brow), 0.03 * W, 0.7)
        img[..., :3] = img[..., :3] * (1 - 0.7 * brow * e_[..., None])
    if age > 0:
        for xc in (0.44, 0.56):                                        # nasolabial folds
            f_ = _soft(H, W, 0.56 * H, xc * W, 0.05 * H, 0.004 * W, 0.8)
            img[..., :3] *= 1 - 0.4 * age * f_[..., None]
        for yc in (0.255, 0.275, 0.295):                               # forehead lines
            f_ = _soft(H, W, yc * H, 0.5 * W, 0.002 * H, 0.08 * W, 0.8)
            img[..., :3] *= 1 - 0.3 * age * f_[..., None]
    return img


def _cap_band(img, col, rng, edge=0.235, side_drop=0.08):
    """a knit cap over the hair strip (and down the sides of the head)"""
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    e = edge + np.where((xx < 0.21) | (xx > 0.79), side_drop, 0.0)
    a = np.clip((e - yy) / 0.012, 0, 1)
    knit = (np.asarray(col) * (0.85 + 0.30 * _noise(H, W, rng, scale=1, octaves=2))[..., None])
    rib = (np.sin(xx * W * 0.9) > 0.6)[..., None] * 0.025
    img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.clip(knit + rib, 0, 1) * a[..., None]


def head(kind, seed):
    rng = np.random.default_rng(seed)
    if kind == 'check':                                                 # balaclava: eyes AND mouth open (not the IT envoy's)
        img = SF.shipped('ch_resg_00').copy()
        _face(img, ((0.80, 0.62, 0.52), 0.4, 0.3, 0.6, (1.0, 1.0, 1.0, 1.0)), rng)
        H, W = img.shape[:2]
        yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
        knit = (0.055 + 0.045 * _noise(H, W, rng, scale=1, octaves=2))[..., None] * np.array([1.0, 1.0, 1.05])
        rib = (np.sin(xx * W * 0.9) > 0.6)[..., None] * 0.02
        eyes = _soft(H, W, 0.335 * H, 0.5 * W, 0.042 * H, 0.15 * W, 0.25)
        mouth = _soft(H, W, 0.585 * H, 0.5 * W, 0.030 * H, 0.06 * W, 0.35)
        a = np.clip(1.0 - np.maximum(eyes, mouth), 0, 1)[..., None]
        img[..., :3] = img[..., :3] * (1 - a) + np.clip(knit + rib, 0, 1) * a
        return img
    img = SF.shipped('ch_resg_00').copy()
    grey = 0.55 if kind in ('shrike',) else 0.06
    _face(img, FACES[kind], rng, grey=grey)
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    if kind in ('k1', 'k2', 'k3'):
        _cap_band(img, {'k1': (0.07, 0.07, 0.07), 'k2': (0.22, 0.24, 0.15), 'k3': (0.30, 0.30, 0.31)}[kind], rng)
        if kind == 'k2':                                                # older: grey at the temples under the cap
            t_ = (np.clip((yy - 0.24) / 0.02, 0, 1) * np.clip((0.30 - yy) / 0.02, 0, 1) * ((xx < 0.2) | (xx > 0.8)))
            img[..., :3] = img[..., :3] * (1 - 0.5 * t_[..., None]) + 0.45 * t_[..., None]
    elif kind == 'qrf':                                                 # olive helmet rim low over the brow + chin strap
        a = np.clip((0.245 + np.where((xx < 0.22) | (xx > 0.78), 0.10, 0.0) - yy) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.array([0.28, 0.31, 0.20]) * (0.8 + 0.3 * _noise(H, W, rng, 1, 2))[..., None] * a[..., None]
        for xc in (0.16, 0.84):
            st = (np.abs(xx - xc) < 0.012) & (yy > 0.30) & (yy < 0.72)
            img[st, :3] = (0.08, 0.07, 0.05)
    elif kind == 'crew':                                                # dark cap + RED ear defender cups over the ears
        _cap_band(img, (0.10, 0.10, 0.11), rng, edge=0.23, side_drop=0.05)
        for xc in (0.21, 0.785):                                        # (the ears on the sheet: x 0.21 / 0.79, y ~0.31)
            cup = _soft(H, W, 0.315 * H, xc * W, 0.055 * H, 0.065 * W, 0.15)
            img[..., :3] = img[..., :3] * (1 - cup[..., None]) + np.array([0.78, 0.10, 0.08]) * cup[..., None]
            rim = _soft(H, W, 0.315 * H, xc * W, 0.064 * H, 0.075 * W, 0.12) - cup
            img[..., :3] = img[..., :3] * (1 - np.clip(rim, 0, 1)[..., None]) + 0.08 * np.clip(rim, 0, 1)[..., None]
        band = (np.abs(yy - 0.20) < 0.012)                              # the headband over the top
        img[band, :3] = (0.15, 0.15, 0.15)
    elif kind == 'tech':
        _cap_band(img, (0.36, 0.37, 0.39), rng, edge=0.225, side_drop=0.03)
        a = np.clip((0.245 - yy) / 0.01, 0, 1) * (np.abs(xx - 0.5) < 0.16)    # the cap's peak over the brow
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.array([0.30, 0.31, 0.33]) * a[..., None]
    elif kind == 'cmd':                                                 # peaked cap: the band low on the brow, hair short grey at the sides
        a = np.clip((0.235 - yy) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.array([0.26, 0.29, 0.21]) * a[..., None]
        band = np.clip((0.235 - yy) / 0.01, 0, 1) * np.clip((yy - 0.19) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - band[..., None]) + np.array([0.58, 0.08, 0.08]) * band[..., None]
        side = np.clip((yy - 0.235) / 0.01, 0, 1) * np.clip((0.29 - yy) / 0.01, 0, 1) * ((xx < 0.2) | (xx > 0.8))
        img[..., :3] = img[..., :3] * (1 - 0.6 * side[..., None]) + 0.5 * side[..., None]
    elif kind == 'shrike':                                              # grey short hair, heavy grey moustache
        a = np.clip((0.22 - yy) / 0.015, 0, 1)
        hair = (0.52 + 0.22 * _noise(H, W, rng, scale=1, octaves=3))[..., None] * np.array([0.93, 0.93, 0.95])
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + hair * a[..., None]
        # (owner 10-31 'the captain must look different': an air-force officer's PEAKED cap - dark blue-grey crown, a sky-blue band,
        #  the grey hair showing at the sides; nobody else on the base wears one)
        a = np.clip((0.235 - yy) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.array([0.16, 0.19, 0.26]) * a[..., None]
        band = np.clip((0.235 - yy) / 0.01, 0, 1) * np.clip((yy - 0.19) / 0.01, 0, 1)
        img[..., :3] = img[..., :3] * (1 - band[..., None]) + np.array([0.30, 0.55, 0.86]) * band[..., None]
        badge = _soft(H, W, 0.205 * H, 0.5 * W, 0.012 * H, 0.03 * W, 0.5)
        img[..., :3] = img[..., :3] * (1 - badge[..., None]) + np.array([0.85, 0.70, 0.25]) * badge[..., None]
        mm_ = _soft(H, W, 0.548 * H, 0.5 * W, 0.014 * H, 0.075 * W, 0.6)
        img[..., :3] = img[..., :3] * (1 - 0.9 * mm_[..., None]) + 0.60 * mm_[..., None] * np.array([0.92, 0.90, 0.88])
        scar = (np.abs(xx - 0.60) < 0.004) & (yy > 0.36) & (yy < 0.43)  # a small scar under the left eye
        img[scar, :3] *= 0.75
    elif kind == 'k1':
        pass
    return img


KIND = {'jrk1_1': 'k1', 'jrk2_1': 'k2', 'jrk3_1': 'k3', QRF: 'qrf', CHECK: 'check', CREW: 'crew', TECH: 'tech', CMD: 'cmd',
        SHRIKE: 'shrike'}


def _textures():
    out = {}
    for k, vn in enumerate(NAMES):
        kd = KIND[vn]
        out[vn] = [('jr_%sbody' % kd, body(kd, 4500 + k)), ('jr_%shead' % kd, head(kd, 4600 + k))]
    return out


def add_skins(overlay_dir, level_name, log=print):
    """register every skin (VNAM over the resg_1 mesh + 2 local textures) in the overlay's manifest + banks"""
    paths = wreck._ensure_overlay(overlay_dir, level_name)
    m = mtp.read(paths['mtp'])
    clash = [n for n in NAMES if n in m['VNAM']]
    if clash:
        raise ValueError('skins already in %s: %s' % (paths['mtp'], clash))
    mp_mtp = os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'multiplayer.mtp')
    resg_mesh, _ = SF._mesh_entry(mp_mtp, 'resg1_1')
    mform, mch, mhdr = ilff.read(open(paths['models'], 'rb').read())
    have_m = {d.rstrip(b'\0').decode('latin1') for t, d, a in mch if t == b'NAME'}
    key = 'LOCAL:models/%s.mef' % resg_mesh
    if key not in have_m:                                   # (every MODS entry in the overlay's own bank)
        ch_, names_ = SF._bank(os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'models', 'multiplayer.res'))
        mch.append((b'NAME', key.encode('latin1') + b'\0', 4)); mch.append((b'BODY', ch_[names_[key]][1], 4))
    if resg_mesh not in m['MODS']:
        m['MODS'].append(resg_mesh)
    form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
    have_t = {d.rstrip(b'\0').decode('latin1') for t, d, a in ch if t == b'NAME'}
    gtt = {}
    for vn, slots in _textures().items():
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
        assert all(x < mtp.COMMON_BIT for x in g_), (vn, g_)          # every slot LOCAL (the 0x16fda0 cutscene crash)
        m['VNAM'].append(vn); m['INST'].append([m['MODS'].index(resg_mesh), g_])
    for path, blob in ((paths['textures'], ilff.write(form, ch, hdr[1] or 4)), (paths['models'], ilff.write(mform, mch, mhdr[1] or 4)),
                       (paths['mtp'], mtp.write(m))):
        tmp = path + '.jr.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    b2 = wreck.Bank(paths['mtp'], paths['models'], paths['textures'])
    probs = [n for n in NAMES if b2.res.get(n) is None]
    if set(b2.m['TEXF']) - set(b2.tex):
        probs.append('TEXF entries without a texture: %s' % sorted(set(b2.m['TEXF']) - set(b2.tex))[:5])
    log('jrskins: %s registered (mesh %s), problems %s' % (NAMES, resg_mesh, probs or 'none'))
    assert not probs, probs
    return list(NAMES)


# ================================================================================================ builder hooks (CONTRACT.md)
def add(B):
    """S4: skins into B.OVERLAY, names into B.SKINS (the builder adds them to m.location_skins), B.GUARD_SKINS for hx_ai"""
    names = add_skins(B.OVERLAY, B.MAP)
    B.SKINS |= set(names)
    B.GUARD_SKINS = {k: (list(v) if isinstance(v, list) else v) for k, v in GUARD_SKINS.items()}
    return names


def _lodrow(cut):
    return [cut * 0.96, cut * 0.97, cut * 0.98, cut * 0.99, cut]


def lod_rows():
    """S16: every skin drawn to 1400 m (GH _lodrow) - without a row a skin vanishes at ~10 x its radius"""
    return {n: _lodrow(1400.0) for n in NAMES}


LINEUP = ((10.0, 0.0), (60.0, -18.0), (150.0, 18.0))   # (distance m, bearing deg from the start view): near / mid / far
                                                         # (10-30 rig: -32 deg fell outside the play view)


def debug(B):
    """S15: 'lineup' - the 3-distance skin check: 3 rows of all 9 skins as standing actors in front of the start
    (in play: one still screenshot shows all three), and the intro replaced by 3 shots from the start eye looking at
    each row (cutscene). Never in a release build."""
    if 'lineup' not in B.DBG:
        return None
    assert 'jetlab' not in B.DBG, "'lineup' and 'jetlab' both replace the intro: run them as separate builds"
    K, m, nid, T, M = B.K, B.m, B.nid, B.T, B.M
    for f_ in list(m.find('Forest')):                 # (test only: the base map's trees and bushes hid the far rows, rig 10-30)
        m.remove(f_)
    # the eye: the highest ground within 220 m of the start (rows downhill all round), the player moved there
    best = None
    for dx in np.arange(-220, 221, 10.0):
        for dy in np.arange(-220, 221, 10.0):
            x_, y_ = B.START[0] + dx * M, B.START[1] + dy * M
            h_ = B.TER.height(x_, y_)
            if not np.isnan(h_) and (best is None or h_ > best[2]):
                best = (x_, y_, float(h_))
    sx, sy = best[0], best[1]
    eye = np.array([sx, sy, best[2] + 1.65 * M])

    def clear(c):                                     # the sight line from the eye to the row's chest clears the ground by
        tgt = np.array([c[0], c[1], float(B.TER.height(c[0], c[1])) + 1.0 * M])   # >= 0.5 m all the way (10-30 rig: rows
        for f in np.linspace(0.05, 0.95, 40):                                         # behind a crest were invisible)
            q = eye + (tgt - eye) * f
            if q[2] < float(B.TER.height(q[0], q[1])) + 0.25 * M:
                return False
        return True

    def row_at(g, dist):
        c = np.array([sx, sy]) + np.array([-math.sin(g), math.cos(g)]) * dist * M
        side = np.array([math.cos(g), math.sin(g)])
        return c, side, all(clear(c + side * e * 3.0 * M) for e in (-1, 0, 1))
    score = []                                        # the heading with the most rows in clear view (ties: the start's)
    for k_ in range(72):
        g_ = 2 * math.pi * k_ / 72
        score.append((sum(row_at(g_ + math.radians(b_), d_)[2] for d_, b_ in LINEUP), -abs(math.sin((g_ - B.START_YAW) / 2)), g_))
    n_ok, _, g0 = max(score)
    if n_ok < 3:
        B.note('jrskins lineup: only %d of 3 rows in clear view from the summit (bearings searched per row)' % n_ok)
    m.set(0, 3, float(sx)); m.set(0, 4, float(sy)); m.set(0, 5, best[2] + 40.0); m.set(0, 6, float(g0))   # (the player there)
    rows, cents = [], []
    used = []
    for dist, brg in LINEUP:
        cand = sorted(range(-44, 45, 2), key=lambda b_: abs(b_ - brg))
        pick = next((b_ for b_ in cand if all(abs(b_ - u) >= 12 for u in used) and row_at(g0 + math.radians(b_), dist)[2]), brg)
        used.append(pick)
        g = g0 + math.radians(pick)
        c, side, ok = row_at(g, dist)
        cents.append((dist, pick, c))
        for k, vn in enumerate(NAMES):
            p = c + side * (k - (len(NAMES) - 1) / 2.0) * 1.25 * M
            z = float(B.TER.height(p[0], p[1])) if B.TER is not None else B.START[2]
            face = B.gyaw((p[0], p[1]), (sx, sy))
            rows.append(T(nid(), 'EditBoneObj', 'JR lineup %s %dm' % (vn, dist), float(p[0]), float(p[1]), z, 0.0, 0.0, float(face),
                          True, True, vn, True, '', '', 'stand_look_about, stand', 1.0, 0.0))
    m.add_child(B.DYN, T(nid(), 'Container', 'JR debug lineup (skins at 10 / 60 / 150 m)', False, children=rows))
    eye_t = tuple(float(c) for c in eye)
    keys = []
    for dist, db, c in cents:
        z = float(B.TER.height(c[0], c[1])) if B.TER is not None else B.START[2]
        tgt = (float(c[0]), float(c[1]), z + 1.0 * M)
        keys.append(B.CS.key(eye_t, tgt, 6.0, False, fov=0.9, noise=0.0))      # (6 s: the rig screenshots every 2-3 s)
    keys.append(B.CS.key(eye_t, keys[-1]['tgt'], 0.0, False, fov=0.9, noise=0.0))
    B.fill_intro([dict(label='JR lineup intro (10 / 60 / 150 m)', vhf=1.0, keys=keys)])
    B.IDS.update(lineup=[dict(dist=d_, bearing=b_) for d_, b_, c_ in cents])
    print('debug lineup: %d actors in 3 rows %s (distance m, bearing deg), intro 3 x 6 s' % (len(rows), [(d_, b_) for d_, b_, c_ in cents]))
    return rows


# ================================================================================================ previews (offline)
def bind_pose(m):
    """bind pose of a skinned (type 1) mesh: REIH = per-bone child counts in BREADTH-first MANB order + per-bone offsets
    (parent frame, no rotation); each XTRV record = one (vertex 'vi', bone, weight) influence with its position in the
    bone's frame -> per-record positions of the weighted vertex (units), normals, uvs"""
    reih = m.get('REIH')
    nb = len(m.get('MANB'))
    counts = [int(c) for c in reih['nchild']]
    offs = reih['offset'].astype(float)
    parent, nxt = [-1] * nb, 1
    for b in range(nb):
        for _ in range(counts[b]):
            if nxt < nb:
                parent[nxt] = b; nxt += 1
    world = np.zeros((nb, 3))
    for b in range(nb):
        world[b] = offs[b] + (world[parent[b]] if parent[b] >= 0 else 0)
    X = m.get('XTRV')
    nv = int(m.get('D3DR')[4])                     # D3DR = (4, faces, groups, extra influences, vertices, records)
    rec_pos = X['pos'].astype(float) + world[X['bone'].astype(int)]
    w = X['weight'].astype(float)
    acc = rec_pos[:nv] * w[:nv, None]              # record k < nv = vertex k's first influence ('vi' there is group-local)
    wsum = w[:nv].copy()
    vi = X['vi'][nv:].astype(int)                  # records >= nv = extra influences of vertex 'vi' (absolute)
    np.add.at(acc, vi, rec_pos[nv:] * w[nv:, None])
    np.add.at(wsum, vi, w[nv:])
    vpos = acc / np.maximum(wsum, 1e-9)[:, None]
    return vpos, X['nrm'][:nv].astype(float), X['uv'][:nv].astype(float)


def _resg_soup():
    import mefmesh
    ch, names = SF._bank(os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'models', 'multiplayer.res'))
    m = mefmesh.Mef.read(ch[names['LOCAL:models/resg_1.mef']][1])
    P, N, U = bind_pose(m)
    I = m.get('ECAF')['v'].astype(int)
    out = []
    for g in m.get('DNER'):
        i0, nt = int(g['i0']), int(g['ntris'])
        T_ = I.reshape(-1)[i0:i0 + 3 * nt].reshape(-1, 3)
        out.append((int(g['tex']), T_))
    return P, N, U, out


def preview(out_dir):
    """sheets + 3D bind-pose renders (front, back, then 10 / 60 / 150 m at fov 0.9) - offline, NOT in-game proof"""
    import mefrender
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    tx = _textures()
    P, N, U, groups = _resg_soup()
    tiles = []
    for vn in NAMES:
        for lab, brg in (('front', 180.0), ('back', 0.0)):              # (the mesh faces +y)
            sc = mefrender.Scene()
            for slot, T_ in groups:
                img = tx[vn][slot][1]
                mat = sc.material(img, color=(0.6, 0.6, 0.6))
                Nn = N[T_]
                Pp = P[T_]
                fn = -np.cross(Pp[:, 1] - Pp[:, 0], Pp[:, 2] - Pp[:, 0])
                fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
                sc.add_tris(Pp, np.repeat(fn[:, None], 3, 1), U[T_], mat, double=True)
            c = np.array([0, 0, 0.95]) * 4096
            b = math.radians(brg)
            eye = c + np.array([math.sin(b) * 3.2, -math.cos(b) * 3.2, 0.25]) * 4096
            tiles.append(('%s %s' % (vn, lab), sc.render(eye, c, size=(240, 360), fov=40, ss=1)))
    cols, W, H = 6, 240, 360
    rows = (len(tiles) + cols - 1) // cols
    sh = Image.new('RGB', (cols * W, rows * (H + 16)), 'black'); dr = ImageDraw.Draw(sh)
    for i, (lab, im) in enumerate(tiles):
        x, y = (i % cols) * W, (i // cols) * (H + 16)
        sh.paste(im.convert('RGB'), (x, y + 16)); dr.text((x + 3, y + 2), lab, fill='yellow')
    p1 = os.path.join(out_dir, 'skins_3d.png'); sh.save(p1)
    # the painted sheets (quarter size)
    sheet = Image.new('RGB', (len(NAMES) * 200, 300), 'black'); dr = ImageDraw.Draw(sheet)
    for i, vn in enumerate(NAMES):
        b_ = Image.fromarray((np.clip(tx[vn][0][1][..., :3], 0, 1) * 255).astype('u1')).resize((200, 200))
        h_ = Image.fromarray((np.clip(tx[vn][1][1][..., :3], 0, 1) * 255).astype('u1')).resize((50, 100))
        sheet.paste(b_, (i * 200, 0)); sheet.paste(h_, (i * 200 + 75, 200)); dr.text((i * 200 + 3, 285), vn, fill='yellow')
    p2 = os.path.join(out_dir, 'skins_sheets.png'); sheet.save(p2)
    # faces close-up (head sheets)
    fs = Image.new('RGB', (len(NAMES) * 160, 330), 'black'); dr = ImageDraw.Draw(fs)
    for i, vn in enumerate(NAMES):
        h_ = Image.fromarray((np.clip(tx[vn][1][1][..., :3], 0, 1) * 255).astype('u1')).resize((160, 320))
        fs.paste(h_, (i * 160, 0)); dr.text((i * 160 + 3, 318), vn, fill='yellow')
    p3 = os.path.join(out_dir, 'skins_faces.png'); fs.save(p3)
    return [p1, p2, p3]


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'preview':
        print(preview(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'joyride', 'art')))
    else:
        print(__doc__)
