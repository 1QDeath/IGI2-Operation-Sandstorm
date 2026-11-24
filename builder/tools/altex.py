"""altex - asset library (2026-10-31): realistic RE-TONED textures for original IGI 2 buildings / doors / aircraft, and
weathered signage in Chinese, Arabic, Vietnamese, English + German (shared by every mission; nothing existing changed).

Realism rule (owner 10-31: 'realistic, at the quality of the original assets, never flat or cartoonish'): every building
texture is DERIVED from the original game texture - its own high-frequency detail (bricks, boards, panel seams, the baked
dirt) is kept as the luminance layer and re-coloured into the theme's palette, then theme weathering is added (dust,
rain/water streaks, mould, rust bleed, sun fade). No flat colour, no procedural-only surfaces.

    import altex
    rgb, a, hdr = altex.read(tex_bytes)                 # mode 2 (A1R5G5B5) / 67 (ARGB8888) textures
    role = altex.classify(rgb)                          # 'wall' 'roof' 'metal' 'wood' 'red' 'green' 'glass' 'dark' 'detail'
    out = altex.retone(rgb, role, 'cn', seed=3)         # themes: cn ar sea nato alpine
    body = altex.write_like(tex_bytes, out, a)
    img = altex.sign('cn_restricted')                   # RGBA float, see SIGNS (text checked word by word below)
    python -P tools/altex.py preview [out_dir]          # every sign + a swatch sheet of every theme
"""
import math, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import igitex
import burnt

FONTS = r'C:\Windows\Fonts'
F_CJK, F_CJK_B = os.path.join(FONTS, 'msyh.ttc'), os.path.join(FONTS, 'msyhbd.ttc')
F_LAT, F_LAT_B = os.path.join(FONTS, 'arial.ttf'), os.path.join(FONTS, 'arialbd.ttf')
F_AR, F_AR_B = os.path.join(FONTS, 'tahoma.ttf'), os.path.join(FONTS, 'tahomabd.ttf')     # (Tahoma: full Arabic presentation forms)
F_DIN = os.path.join(FONTS, 'segoeuib.ttf')                                                 # (Vietnamese diacritics)


# ===================================================================================================== texture I/O
def read(b):
    """tex bytes -> (rgb float32 h x w x 3, alpha (h x w) float or the A1 bit array, header bytes)"""
    mode, w, h, bpp = igitex.header(b)
    if bpp == 2 and (mode & 0x3F) == 2 and not mode & 0x40:
        hdr, rgb, abit = burnt.tex_read(b)
        return rgb, abit, hdr
    rgba = igitex.decode(b)
    return rgba[..., :3].copy(), rgba[..., 3].copy(), b[:32]


def write_like(b, rgb, a):
    """re-encode rgb (+ the alpha read() gave) with the format of the template texture b"""
    mode, w, h, bpp = igitex.header(b)
    if bpp == 2 and (mode & 0x3F) == 2 and not mode & 0x40:
        return burnt.tex_write(b[:32], np.clip(rgb, 0, 1), a)
    return igitex.encode_like(b, np.dstack([np.clip(rgb, 0, 1), a]))


def supported(b):
    mode, w, h, bpp = igitex.header(b)
    return (bpp == 2 and (mode & 0x3F) == 2 and not mode & 0x40) or bpp == 4


# ===================================================================================================== helpers
def noise(h, w, seed, scales=(8, 24, 64, 160), weights=(0.45, 0.3, 0.17, 0.08)):
    return burnt._noise(h, w, seed, scales, weights)


def lum(rgb):
    return 0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2]


def _hsv(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn + 1e-6
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6.0
    s = (mx - mn) / np.maximum(mx, 1e-3)
    return h, s, mx


def classify(rgb, name=''):
    """a texture's material role from its colour statistics (overridable per texture in albuild recipes)"""
    if name.endswith('_argb8888') or 'glass' in name.lower():
        return 'glass'
    h_, w_ = rgb.shape[:2]
    if h_ * w_ <= 32 * 32:
        return 'detail'
    H, S, V = _hsv(rgb)
    L = float(lum(rgb).mean())
    s = float(np.median(S))
    hue = float(np.median(H[S > 0.12])) if (S > 0.12).mean() > 0.3 else -1.0
    if s > 0.35 and (hue < 0.04 or hue > 0.93):
        return 'red'
    if s > 0.22 and 0.17 < hue < 0.45:
        return 'green'
    if s > 0.25 and 0.04 <= hue <= 0.12 and L < 0.42:
        return 'wood'
    if L < 0.22:
        return 'dark'
    if L < 0.36:
        return 'roof'
    if s < 0.12 and L < 0.5:
        return 'metal'
    return 'wall'


# ===================================================================================================== themes
# role -> (base rgb, contrast, keep): out = base * shade^contrast, keep = how much of the original colour survives
# fx: dust (light sandy veil, stronger low on the texture), streak (vertical rain / rust / mould runs), mottle (patchy
#     repaint / sun fade), speck (snow / lime specks), tint (final global multiply)
THEMES = {
    'cn': dict(            # PLA compound, south-west China: grey-cream render, green-grey roofs, olive steel, red-lacquer wood
        label='Chinese military compound',
        wall=((0.74, 0.72, 0.66), 1.0, 0.08), roof=((0.27, 0.33, 0.29), 1.0, 0.05), metal=((0.30, 0.35, 0.27), 1.0, 0.05),
        wood=((0.46, 0.13, 0.09), 1.05, 0.05), red=((0.55, 0.10, 0.08), 1.0, 0.25), green=((0.28, 0.36, 0.25), 1.0, 0.2),
        dark=((0.17, 0.18, 0.17), 1.0, 0.3), detail=None, glass=None,
        fx=dict(streak=('water', 0.22), mottle=0.10, dust=0.05)),
    'ar': dict(            # Middle-East / desert: sand stucco, sun-bleached concrete roofs, faded turquoise steel, grey wood
        label='Middle-East desert base',
        wall=((0.80, 0.69, 0.52), 1.0, 0.10), roof=((0.66, 0.61, 0.53), 0.9, 0.10), metal=((0.50, 0.53, 0.52), 1.0, 0.06),
        wood=((0.27, 0.45, 0.44), 1.0, 0.08), red=((0.62, 0.30, 0.20), 1.0, 0.2), green=((0.40, 0.42, 0.30), 1.0, 0.2),
        dark=((0.26, 0.24, 0.21), 1.0, 0.3), detail=None, glass=None,
        fx=dict(dust=0.22, mottle=0.12, streak=('dust', 0.12), tint=(1.03, 1.0, 0.95))),
    'sea': dict(           # South-East Asia (Vietnam / Indonesia): mouldy ochre plaster, rusted tin, dark teak, faded olive
        label='South-East Asian jungle post',
        wall=((0.66, 0.60, 0.46), 1.05, 0.10), roof=((0.40, 0.27, 0.18), 1.1, 0.05), metal=((0.34, 0.36, 0.27), 1.0, 0.05),
        wood=((0.30, 0.19, 0.11), 1.05, 0.05), red=((0.55, 0.16, 0.10), 1.0, 0.25), green=((0.25, 0.33, 0.20), 1.0, 0.25),
        dark=((0.15, 0.15, 0.12), 1.0, 0.3), detail=None, glass=None,
        fx=dict(streak=('mould', 0.42), mottle=0.18, tint=(0.97, 1.0, 0.94))),
    'nato': dict(          # Western European / NATO garrison: clean light-grey concrete, anthracite roofs, RAL 6014 steel
        label='Western European NATO garrison',
        wall=((0.68, 0.68, 0.66), 1.0, 0.05), roof=((0.23, 0.24, 0.26), 1.0, 0.05), metal=((0.34, 0.34, 0.27), 1.0, 0.05),
        wood=((0.20, 0.26, 0.20), 1.0, 0.05), red=((0.60, 0.12, 0.10), 1.0, 0.25), green=((0.30, 0.34, 0.26), 1.0, 0.2),
        dark=((0.16, 0.16, 0.17), 1.0, 0.3), detail=None, glass=None,
        fx=dict(streak=('water', 0.16), mottle=0.05)),
    'alpine': dict(        # mountain airbase: cold weathered concrete, slate roofs with frost specks, blue-grey hangar steel
        label='Mountain airbase',
        wall=((0.60, 0.62, 0.64), 1.05, 0.05), roof=((0.30, 0.32, 0.35), 1.0, 0.05), metal=((0.36, 0.40, 0.44), 1.0, 0.05),
        wood=((0.28, 0.22, 0.17), 1.0, 0.05), red=((0.62, 0.14, 0.10), 1.0, 0.3), green=((0.30, 0.33, 0.29), 1.0, 0.2),
        dark=((0.15, 0.16, 0.18), 1.0, 0.3), detail=None, glass=None,
        fx=dict(streak=('water', 0.30), speck=0.05, mottle=0.08, tint=(0.97, 0.99, 1.03))),
    # ---- aircraft / vehicle liveries (whole airframe repaint; markings, glass and dark details kept per pixel)
    'liv_desert': dict(label='desert livery (sand / tan)',
        wall=((0.70, 0.60, 0.44), 1.0, 0.05), roof=((0.60, 0.51, 0.37), 1.0, 0.05), metal=((0.66, 0.57, 0.42), 1.0, 0.05),
        wood=((0.50, 0.40, 0.28), 1.0, 0.1), red=None, green=((0.62, 0.53, 0.39), 1.0, 0.05), dark=((0.30, 0.26, 0.20), 1.0, 0.4),
        detail=None, glass=None, fx=dict(dust=0.10, mottle=0.06)),
    'liv_grey': dict(label='NATO light-grey livery',
        wall=((0.55, 0.57, 0.59), 1.0, 0.05), roof=((0.50, 0.52, 0.55), 1.0, 0.05), metal=((0.53, 0.55, 0.57), 1.0, 0.05),
        wood=((0.45, 0.46, 0.48), 1.0, 0.1), red=None, green=((0.52, 0.54, 0.56), 1.0, 0.05), dark=((0.20, 0.21, 0.22), 1.0, 0.4),
        detail=None, glass=None, fx=dict(streak=('water', 0.10), mottle=0.04)),
    'liv_green': dict(label='dark green livery (PLA / SE Asia)',
        wall=((0.24, 0.29, 0.20), 1.0, 0.05), roof=((0.22, 0.27, 0.19), 1.0, 0.05), metal=((0.25, 0.30, 0.21), 1.0, 0.05),
        wood=((0.24, 0.24, 0.17), 1.0, 0.1), red=None, green=((0.24, 0.30, 0.20), 1.0, 0.05), dark=((0.12, 0.13, 0.11), 1.0, 0.4),
        detail=None, glass=None, fx=dict(streak=('water', 0.12), mottle=0.08)),
    'liv_black': dict(label='IGI black / charcoal livery',
        wall=((0.13, 0.135, 0.145), 1.0, 0.05), roof=((0.12, 0.125, 0.135), 1.0, 0.05), metal=((0.14, 0.145, 0.155), 1.0, 0.05),
        wood=((0.14, 0.14, 0.14), 1.0, 0.1), red=None, green=((0.14, 0.15, 0.15), 1.0, 0.05), dark=((0.07, 0.07, 0.075), 1.0, 0.5),
        detail=None, glass=None, fx=dict(mottle=0.05)),
}


def _shade(rgb):
    """the original texture's light (its own detail), normalised to a mean of ~1"""
    L = lum(rgb)
    m = float(np.percentile(L, 60)) + 1e-3
    return np.clip(L / m, 0, 2.2)


def _streaks(h, w, seed, kind, amount):
    """vertical runs (rows = v, top = row 0 of the texture: walls are mapped upright in the originals)"""
    rng = np.random.default_rng(seed)
    cols = noise(1, w, seed, scales=(16, 48, 96), weights=(0.5, 0.3, 0.2))[0]
    cols = np.clip((cols - 0.45) * 3.0, 0, 1) ** 1.5
    fall = np.linspace(0, 1, h)[:, None]
    start = rng.random(w)[None, :] * 0.5
    run = np.clip((fall - start) * 2.5, 0, 1) * np.clip(1.2 - fall, 0, 1) * 1.5
    s = cols[None, :] * run * (0.6 + 0.4 * noise(h, w, seed + 5, scales=(4, 12, 32), weights=(0.4, 0.4, 0.2)))
    col = {'water': (0.55, 0.55, 0.55), 'rust': (0.42, 0.20, 0.08), 'mould': (0.20, 0.22, 0.14), 'dust': (0.95, 0.88, 0.72)}[kind]
    return np.clip(s * amount, 0, 1), np.array(col, np.float32)


def retone(rgb, role, theme, seed=1, override=None, lum_mix=0.6):
    """original texture -> theme texture, PER PIXEL: neutral pixels (grey / beige) take the texture's role colour,
    coloured pixels take the theme colour of their own hue (red trims, green paint, brown wood), blue glass panes and
    near-black stay; brightness = geometric mix of the original light and the theme colour's (lum_mix) so a dark
    texture stays darker than a light one and every brick / board / seam of the original remains. 'glass' / 'detail'
    (signs, ornaments, decals) and None recipes keep the colours (light weathering only)."""
    T = THEMES[theme]
    h, w = rgb.shape[:2]
    force = role.endswith('!')                     # 'wall!' = every pixel takes the role colour (red brick -> grey render)
    role = role.rstrip('!')
    rec = override if override is not None else T.get(role)
    out = rgb.astype(np.float32).copy()
    if rec:
        from scipy import ndimage
        H_, S_, V_ = _hsv(rgb)
        Ssm = ndimage.gaussian_filter(S_, 1.2)
        L = lum(rgb)
        sh = _shade(rgb)

        def paint(recipe):
            base, contrast, keep = recipe
            base = np.array(base, np.float32)
            bl = float(lum(base[None, None, :])[0, 0])
            tl = np.maximum(L, 1e-3) ** (1 - lum_mix) * np.maximum(bl * sh ** contrast, 1e-3) ** lum_mix
            col = base[None, None, :] / max(bl, 1e-3) * tl[..., None]
            return col * (1 - keep) + rgb * keep
        neutral = paint(rec)
        wt = {}
        hue_rec = {'red': T.get('red'), 'green': T.get('green'), 'wood': T.get('wood')}
        col_sat = np.clip((Ssm - 0.16) * 6.0, 0, 1)
        wt['red'] = col_sat * (((H_ < 0.035) | (H_ > 0.94)).astype(np.float32))
        wt['green'] = col_sat * (((H_ > 0.16) & (H_ < 0.45)).astype(np.float32))
        wt['wood'] = col_sat * (((H_ >= 0.035) & (H_ <= 0.13) & (L < 0.45)).astype(np.float32))
        keep_px = col_sat * (((H_ > 0.5) & (H_ < 0.72)).astype(np.float32)) + np.clip((0.06 - L) * 20, 0, 1)
        out = neutral
        for k_, r_ in hue_rec.items():
            if r_ is None or role == k_ or force:
                continue
            a_ = np.clip(wt[k_], 0, 1)[..., None]
            out = out * (1 - a_) + paint(r_) * a_
        kp = np.clip(keep_px, 0, 1)[..., None]
        out = out * (1 - kp) + rgb * kp
    if role in ('glass',):
        return np.clip(out, 0, 1)
    fx = T['fx']
    if fx.get('mottle'):
        n = noise(h, w, seed + 11, scales=(3, 7, 15), weights=(0.5, 0.3, 0.2))
        out *= (1 - fx['mottle'] / 2 + fx['mottle'] * n)[..., None]
    if fx.get('streak') and role in ('wall', 'roof', 'metal', 'wood', 'green', 'red'):
        kind, amt = fx['streak']
        s, c = _streaks(h, w, seed + 23, kind, amt)
        if kind in ('water', 'mould'):
            out = out * (1 - s[..., None] * (1 - c))       # darkening runs
        else:
            out = out * (1 - s[..., None]) + c * lum(out)[..., None] * 1.1 * s[..., None]
        if role == 'metal' and theme in ('sea', 'ar'):
            s2, c2 = _streaks(h, w, seed + 29, 'rust', 0.35)
            out = out * (1 - s2[..., None]) + c2 * (0.6 + 0.4 * _shade(rgb)[..., None]) * s2[..., None]
    if fx.get('dust') and role not in ('detail',):
        n = noise(h, w, seed + 31, scales=(6, 18, 48), weights=(0.4, 0.4, 0.2))
        low = np.linspace(0.6, 1.4, h)[:, None]
        k = np.clip(fx['dust'] * n * low, 0, 0.6)[..., None]
        out = out * (1 - k) + np.array((0.86, 0.78, 0.62), np.float32) * (0.75 + 0.25 * _shade(rgb)[..., None]) * k
    if fx.get('speck') and role in ('roof', 'wall', 'metal'):
        rng = np.random.default_rng(seed + 41)
        sp = (rng.random((h, w)) < fx['speck'] * (0.5 + noise(h, w, seed + 43, scales=(4, 12), weights=(0.6, 0.4)))).astype(np.float32)
        out = out * (1 - sp[..., None] * 0.7) + 0.9 * sp[..., None] * 0.7
    if fx.get('tint'):
        out *= np.array(fx['tint'], np.float32)
    return np.clip(out, 0, 1)


# ===================================================================================================== signage
def _shape_ar(text):
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text))


def _font(path, pt):
    from PIL import ImageFont
    return ImageFont.truetype(path, pt)


def _font_for(text, bold):
    if any('\u0600' <= ch <= '\u06ff' for ch in text):
        return F_AR_B if bold else F_AR
    if any('\u3400' <= ch <= '\u9fff' for ch in text):
        return F_CJK_B if bold else F_CJK
    if any(ord(ch) > 0x17f for ch in text):
        return F_DIN
    return F_LAT_B if bold else F_LAT


def _draw_line(dr, W, x0, x1, y, text, pt, fill, bold):
    shown = _shape_ar(text) if any('\u0600' <= ch <= '\u06ff' for ch in text) else text
    fp = _font_for(text, bold)
    while pt > 9:
        f = _font(fp, pt)
        bb = dr.textbbox((0, 0), shown, font=f)
        if bb[2] - bb[0] <= x1 - x0:
            break
        pt -= 2
    return shown, f, bb


# style: (background, text colour, border colour or None, icon)
STYLES = {
    'red_white': ((0.72, 0.09, 0.07), (0.96, 0.95, 0.92), (0.96, 0.95, 0.92), None),
    'white_red': ((0.93, 0.92, 0.88), (0.70, 0.08, 0.06), (0.70, 0.08, 0.06), None),
    'white_black': ((0.93, 0.92, 0.88), (0.10, 0.10, 0.10), (0.10, 0.10, 0.10), None),
    'yellow_hazard': ((0.90, 0.74, 0.10), (0.10, 0.09, 0.08), None, 'hazard'),
    'green_white': ((0.10, 0.36, 0.20), (0.96, 0.96, 0.94), (0.96, 0.96, 0.94), None),
    'blue_white': ((0.10, 0.22, 0.48), (0.96, 0.96, 0.94), (0.96, 0.96, 0.94), None),
    'olive_stencil': ((0.30, 0.33, 0.24), (0.88, 0.86, 0.78), None, None),
    'nosmoke': ((0.93, 0.92, 0.88), (0.70, 0.08, 0.06), (0.70, 0.08, 0.06), 'nosmoke'),
    'star_red': ((0.72, 0.09, 0.07), (0.98, 0.84, 0.30), (0.98, 0.84, 0.30), 'star'),
    'iq_flag': ((0.97, 0.97, 0.96), (0.00, 0.48, 0.24), None, 'iqflag'),    # (11-02 additive: Iraqi flag, red / white / black)
}

# id -> (lines [(text, rel size, bold)], style, (w px, h px), plate size (w m, h m)).  Translations (checked):
SIGNS = {
    # ---- Chinese (simplified)
    'cn_restricted': ([('军事管理区', 1.0, True), ('闲人免进', 0.8, True), ('MILITARY ZONE - NO ENTRY', 0.32, False)], 'red_white',
                      (512, 256), (1.6, 0.8)),           # military administrative zone / unauthorised persons keep out
    'cn_nofire': ([('严禁烟火', 1.0, True), ('NO SMOKING  NO NAKED FLAME', 0.34, False)], 'nosmoke', (512, 256), (1.0, 0.5)),
    'cn_ammo': ([('弹药库', 1.0, True), ('危险  严禁靠近', 0.6, True)], 'yellow_hazard', (512, 256), (1.2, 0.6)),   # ammunition depot / danger, keep away
    'cn_comms': ([('通信值班室', 1.0, True), ('COMMS DUTY ROOM', 0.4, False)], 'white_black', (512, 128), (0.9, 0.225)),
    'cn_barracks': ([('三连 营房', 1.0, True)], 'white_black', (512, 128), (0.9, 0.225)),            # 3rd company barracks
    'cn_cmd': ([('指挥所', 1.0, True), ('61248部队', 0.55, True)], 'star_red', (512, 256), (1.4, 0.7)),  # command post / unit 61248
    'cn_garage': ([('车库', 1.0, True), ('注意倒车', 0.55, False)], 'white_black', (512, 256), (1.0, 0.5)),   # garage / watch reversing vehicles
    'cn_stop': ([('停', 1.0, True), ('出示证件', 0.5, True)], 'red_white', (256, 256), (0.8, 0.8)),       # stop / show your ID
    'cn_slogan': ([('提高警惕  保卫祖国', 1.0, True)], 'red_white', (1024, 128), (4.0, 0.5)),          # raise vigilance, defend the motherland
    # ---- Arabic
    'ar_restricted': ([('منطقة عسكرية', 1.0, True), ('ممنوع الدخول', 0.8, True), ('MILITARY AREA - NO ENTRY', 0.32, False)],
                      'red_white', (512, 256), (1.6, 0.8)),
    'ar_nosmoke': ([('ممنوع التدخين', 1.0, True), ('NO SMOKING', 0.4, False)], 'nosmoke', (512, 256), (1.0, 0.5)),
    'ar_ammo': ([('مستودع الذخيرة', 1.0, True), ('خطر', 0.8, True)], 'yellow_hazard', (512, 256), (1.2, 0.6)),   # ammunition store / danger
    'ar_comms': ([('غرفة الاتصالات', 1.0, True)], 'white_black', (512, 128), (0.9, 0.225)),       # communications room
    'ar_barracks': ([('مهجع الجنود', 1.0, True)], 'white_black', (512, 128), (0.9, 0.225)),       # soldiers' dormitory
    'ar_cmd': ([('مكتب القائد', 1.0, True)], 'green_white', (512, 128), (0.9, 0.225)),           # commander's office
    'ar_stop': ([('قف', 1.0, True), ('نقطة تفتيش', 0.55, True)], 'red_white', (256, 256), (0.8, 0.8)),   # stop / checkpoint
    'ar_garage': ([('ورشة الآليات', 1.0, True)], 'white_black', (512, 128), (0.9, 0.225)),        # vehicle workshop
    # ---- Iraq (11-02 additive, Sandstorm): the national flag (takbir in green on the white band) and a fictional base name
    'iq_flag': ([('الله أكبر', 0.5, True)], 'iq_flag', (512, 256), (1.5, 1.0)),
    'iq_base': ([('قاعدة الصقر الجوية', 1.0, True), ('AL-SAQR AIR BASE', 0.42, True)], 'green_white', (512, 256), (1.8, 0.9)),
    # ---- Vietnamese (South-East Asia)
    'vn_restricted': ([('KHU VỰC QUÂN SỰ', 1.0, True), ('CẤM VÀO', 0.9, True)], 'red_white', (512, 256), (1.6, 0.8)),
    'vn_nosmoke': ([('CẤM HÚT THUỐC', 1.0, True)], 'nosmoke', (512, 256), (1.0, 0.5)),
    'vn_ammo': ([('KHO ĐẠN', 1.0, True), ('NGUY HIỂM', 0.7, True)], 'yellow_hazard', (512, 256), (1.2, 0.6)),
    'vn_comms': ([('PHÒNG THÔNG TIN', 1.0, True)], 'white_black', (512, 128), (0.9, 0.225)),
    'vn_barracks': ([('NHÀ Ở  ĐẠI ĐỘI 2', 1.0, True)], 'white_black', (512, 128), (0.9, 0.225)),    # quarters, 2nd company
    'vn_stop': ([('DỪNG LẠI', 1.0, True), ('TRẠM KIỂM SOÁT', 0.55, True)], 'red_white', (256, 256), (0.8, 0.8)),
    'id_restricted': ([('DAERAH MILITER', 1.0, True), ('DILARANG MASUK', 0.85, True)], 'red_white', (512, 256), (1.6, 0.8)),  # Indonesian
    # ---- English + German (NATO garrison)
    'eu_restricted': ([('RESTRICTED AREA', 1.0, True), ('AUTHORISED PERSONNEL ONLY', 0.5, True),
                       ('MILITÄRISCHER SICHERHEITSBEREICH', 0.42, True), ('UNBEFUGTES BETRETEN VERBOTEN', 0.42, False)],
                      'white_red', (512, 256), (1.6, 0.8)),
    'eu_nosmoke': ([('RAUCHEN VERBOTEN', 0.8, True), ('NO SMOKING', 0.8, True)], 'nosmoke', (512, 256), (1.0, 0.5)),
    'eu_armoury': ([('WAFFENKAMMER', 1.0, True), ('ARMOURY', 0.8, True)], 'blue_white', (512, 128), (0.9, 0.225)),
    'eu_comms': ([('FERNMELDERAUM', 1.0, True), ('SIGNALS', 0.7, True)], 'blue_white', (512, 128), (0.9, 0.225)),
    'eu_stop': ([('HALT', 1.0, True), ('AUSWEISKONTROLLE', 0.42, True)], 'red_white', (256, 256), (0.8, 0.8)),
    'eu_unit': ([('PANZERGRENADIERBATAILLON 371', 0.6, True), ('KASERNE', 1.0, True)], 'green_white', (512, 256), (2.0, 1.0)),
    # ---- airfield / mountain airbase (aviation English, ICAO style)
    'av_jetblast': ([('DANGER', 1.0, True), ('JET BLAST', 0.8, True)], 'yellow_hazard', (512, 256), (2.2, 1.1)),
    'av_hangar': ([('HANGAR 2', 1.0, True)], 'olive_stencil', (512, 128), (4.0, 1.0)),
    'av_fod': ([('FOD CHECK', 1.0, True), ('BEFORE TAXI', 0.6, True)], 'yellow_hazard', (512, 256), (1.0, 0.5)),
    'av_avalanche': ([('AVALANCHE AREA', 1.0, True), ('DO NOT LEAVE THE ROAD', 0.5, True)], 'yellow_hazard', (512, 256), (1.6, 0.8)),
    'av_ops': ([('FLIGHT OPS', 1.0, True)], 'blue_white', (512, 128), (0.9, 0.225)),
}


def sign(sid, seed=None):
    """-> float RGBA (h, w, 4): the sign's face, weathered (faded paint, grime, a rust run from each screw, chipped edges)"""
    from PIL import Image, ImageDraw
    lines, style, (W, H), _plate = SIGNS[sid]
    bg, fg, border, icon = STYLES[style]
    seed = seed if seed is not None else (sum(map(ord, sid)) % 997)
    S = 2                                                   # supersample
    im = Image.new('RGB', (W * S, H * S), tuple(int(c * 255) for c in bg))
    dr = ImageDraw.Draw(im)
    bw = max(6, H * S // 20)
    if icon == 'hazard':
        for k in range(-H * S, W * S + H * S, 40 * S):
            dr.polygon([(k, 0), (k + 20 * S, 0), (k + 20 * S - H * S, H * S), (k - H * S, H * S)], fill=(22, 20, 18))
        dr.rectangle([bw * 2, bw * 2, W * S - bw * 2, H * S - bw * 2], fill=tuple(int(c * 255) for c in bg))
    elif border:
        dr.rectangle([bw // 2, bw // 2, W * S - bw // 2 - 1, H * S - bw // 2 - 1], outline=tuple(int(c * 255) for c in border), width=bw)
    x_text = 0
    if icon == 'nosmoke':
        r = int(H * S * 0.34); cx, cy = int(H * S * 0.5), H * S // 2
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(190, 22, 18), width=max(8, r // 5))
        dr.rectangle([cx - r * 0.6, cy - r * 0.12, cx + r * 0.45, cy + r * 0.12], fill=(240, 240, 235), outline=(30, 30, 30), width=2)
        dr.rectangle([cx + r * 0.30, cy - r * 0.12, cx + r * 0.45, cy + r * 0.12], fill=(210, 120, 40))
        dr.line([(cx - r * 0.7, cy - r * 0.7), (cx + r * 0.7, cy + r * 0.7)], fill=(190, 22, 18), width=max(8, r // 5))
        x_text = int(H * S * 0.92)
    if icon == 'iqflag':                                    # three equal bands, the text centred on the white one
        dr.rectangle([0, 0, W * S, H * S // 3], fill=(206, 17, 38))
        dr.rectangle([0, 2 * H * S // 3, W * S, H * S], fill=(12, 12, 12))
    if icon == 'star':
        cx, cy, r = int(H * S * 0.5), H * S // 2, int(H * S * 0.32)
        pts = [(cx + (r if k % 2 == 0 else r * 0.40) * math.cos(-math.pi / 2 + k * math.pi / 5),
                cy + (r if k % 2 == 0 else r * 0.40) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)]
        dr.polygon(pts, fill=(250, 214, 80))
        x_text = int(H * S * 0.88)
    margin = (bw * 2 if (border or icon == 'hazard') else 0) + 10 * S
    x0, x1 = (x_text or margin), W * S - margin
    base_pt = int(H * S * (0.42 if len(lines) == 1 else 0.36 if len(lines) == 2 else 0.24 if len(lines) == 3 else 0.18))
    fitted = [(_draw_line(dr, W * S, x0, x1, 0, t, int(base_pt * rel), fg, b)) for t, rel, b in lines]
    gap = 8 * S
    tot = sum(bb[3] - bb[1] for s_, f, bb in fitted) + gap * (len(fitted) - 1)
    y = (H * S - tot) / 2
    for shown, f, bb in fitted:
        dr.text((x0 + (x1 - x0 - (bb[2] - bb[0])) / 2 - bb[0], y - bb[1]), shown, fill=tuple(int(c * 255) for c in fg), font=f)
        y += bb[3] - bb[1] + gap
    screws = [(bw * 1.2, bw * 1.2), (W * S - bw * 1.2, bw * 1.2), (bw * 1.2, H * S - bw * 1.2), (W * S - bw * 1.2, H * S - bw * 1.2)]
    for sx, sy in screws:
        rr = max(3, bw // 3)
        dr.ellipse([sx - rr, sy - rr, sx + rr, sy + rr], fill=(70, 66, 60), outline=(30, 28, 26))
    im = im.resize((W, H), Image.LANCZOS)
    a = np.asarray(im, np.float32) / 255.0
    # weathering: sun fade (towards a chalky version of itself), grime noise, rust runs under the screws, chipped edges
    n = noise(H, W, seed, scales=(4, 12, 32, 64), weights=(0.3, 0.3, 0.25, 0.15))
    fade = 0.10 + 0.12 * n
    a = a * (1 - fade[..., None]) + (0.55 + 0.35 * lum(a)[..., None]) * fade[..., None]
    a *= (0.86 + 0.18 * noise(H, W, seed + 3, scales=(16, 48, 96), weights=(0.4, 0.4, 0.2)))[..., None]
    yy, xx = np.mgrid[0:H, 0:W]
    for sx, sy in screws:
        sx, sy = sx / S, sy / S
        run = np.exp(-((xx - sx) / max(1.5, W / 220.0)) ** 2) * np.clip((yy - sy) / (H * 0.45), 0, 1) * np.clip(1 - (yy - sy) / (H * 0.6), 0, 1)
        run *= (yy > sy)
        a = a * (1 - 0.5 * run[..., None]) + np.array((0.40, 0.20, 0.08)) * 0.5 * run[..., None]
    edge = np.minimum.reduce([xx, yy, W - 1 - xx, H - 1 - yy]).astype(np.float32)
    rng = np.random.default_rng(seed + 9)
    chip = (edge < 4 + 6 * noise(H, W, seed + 7, scales=(8, 24), weights=(0.6, 0.4))) & (rng.random((H, W)) < 0.35)
    a[chip] = a[chip] * 0.35 + np.array((0.45, 0.43, 0.40)) * 0.65
    return np.dstack([np.clip(a, 0, 1), np.ones((H, W), np.float32)])


def sign_ids(prefix=None):
    return [k for k in SIGNS if prefix is None or k.startswith(prefix)]


# ===================================================================================================== previews
def preview(out_dir):
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    ims = []
    for sid in SIGNS:
        img = sign(sid)
        im = Image.fromarray((img[..., :3] * 255).astype('u1'))
        im.thumbnail((380, 190))
        ims.append((sid, im))
    cols = 4
    rows = (len(ims) + cols - 1) // cols
    sh = Image.new('RGB', (cols * 390, rows * 215), (40, 40, 40))
    d = ImageDraw.Draw(sh)
    for k, (sid, im) in enumerate(ims):
        x, y = (k % cols) * 390 + 5, (k // cols) * 215 + 18
        sh.paste(im, (x, y)); d.text((x, y - 15), sid, fill='yellow')
    p = os.path.join(out_dir, 'signs.png')
    sh.save(p)
    return p


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'preview':
        print(preview(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'assetlib', 'prev')))
