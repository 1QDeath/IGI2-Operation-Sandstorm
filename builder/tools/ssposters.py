"""ssposters - the Iraq of Al-Saqr Air Base on its walls (owner 11-05 item 54): leader portraits, painted murals, slogans in Arabic and
English. Everything is original art: the portraits are stylised gouache-poster paintings made on this PC (igi2-face-tools, prompts kept
beside them) and reduced to a few flat poster tones here, never a press photograph.

Arabic checked word by word; translations beside each line. Real slogans of the time, as they stood on such walls.

    import ssposters as SP
    SP.preview(out_dir)                       # every sheet, offline
    SP.register(lib)                          # modelkit.Library: textures + flat wall panels (one model per poster)
    SP.place(K, m, parent)                    # after navgen: on the wall nearest each spot in SPOTS
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage
import altex

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, 'work', 'sandstorm', 'soldiers', 'art')
FONTS = r'C:\Windows\Fonts'
F_CALLIG = os.path.join(FONTS, 'majallab.ttf')                    # Sakkal Majalla Bold: a sign painter's naskh
F_SIGN = os.path.join(FONTS, 'tahomabd.ttf')
F_LAT = os.path.join(FONTS, 'arialbd.ttf')
RED, GREEN, BLACK, WHITE, GOLD = (182, 24, 30), (0, 106, 58), (18, 17, 16), (240, 236, 224), (214, 172, 66)

SLOGANS = {
    'bilruh': ('بالروح بالدم نفديك يا صدام', 'WITH OUR SOULS, WITH OUR BLOOD, WE REDEEM YOU'),      # with soul, with blood, we redeem you, O Saddam
    'umma': ('أمة عربية واحدة ذات رسالة خالدة', 'ONE ARAB NATION WITH AN ETERNAL MESSAGE'),            # the Ba'ath motto
    'qaid': ('عاش القائد صدام حسين', 'LONG LIVE THE LEADER'),                                          # long live the leader Saddam Hussein
    'jaysh': ('الجيش العراقي درع الأمة', 'THE IRAQI ARMY IS THE SHIELD OF THE NATION'),               # the Iraqi army, shield of the nation
    'nasr': ('النصر أو الشهادة', 'VICTORY OR MARTYRDOM'),                                              # victory or martyrdom
    'iraq': ('عاش العراق العظيم', 'LONG LIVE GREAT IRAQ'),                                             # long live great Iraq
}


def _ar(text):
    return altex._shape_ar(text)


def _fit(dr, text, path, w, pt):
    while pt > 10:
        f = ImageFont.truetype(path, pt)
        bb = dr.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= w:
            return f, bb
        pt -= 2
    return f, bb


def _center(dr, cx, y, text, path, w, pt, fill):
    f, bb = _fit(dr, text, path, w, pt)
    dr.text((cx - (bb[2] - bb[0]) / 2 - bb[0], y - bb[1]), text, font=f, fill=fill)
    return bb[3] - bb[1]


def weather(im, seed, grime=0.5):
    """sun-fade, flaking paint, dust from the top edge; RGB image -> RGBA float (the sign weathering of altex at wall scale)"""
    a = np.asarray(im.convert('RGB'), np.float32) / 255.0
    H, W = a.shape[:2]
    n = altex.noise(H, W, seed, scales=(6, 18, 48, 120), weights=(0.3, 0.3, 0.25, 0.15))
    fade = (0.10 + 0.18 * n) * grime * 2
    a = a * (1 - fade[..., None]) + (0.62 + 0.28 * altex.lum(a)[..., None]) * np.array((1.02, 0.98, 0.90)) * fade[..., None]
    a *= (0.84 + 0.22 * altex.noise(H, W, seed + 3, scales=(16, 48, 96), weights=(0.4, 0.4, 0.2)))[..., None]
    s, c = altex._streaks(H, W, seed + 5, 'dust', 0.22 * grime * 2)
    a = a * (1 - s[..., None]) + c * altex.lum(a)[..., None] * s[..., None]
    rng = np.random.default_rng(seed + 9)
    fl = altex.noise(H, W, seed + 7, scales=(3, 8, 20), weights=(0.5, 0.3, 0.2))
    chip = ndimage.binary_opening(fl > np.percentile(fl, 99.0 - 1.6 * grime), iterations=1)
    a[chip] = a[chip] * 0.35 + np.array((0.62, 0.58, 0.50)) * 0.65
    return np.dstack([np.clip(a, 0, 1), np.ones((H, W), np.float32)])


def banner(key, style='red', size=(1024, 192)):
    """a long painted cloth / wall line: Arabic big, English under it"""
    W, H = size
    S = 2
    bg, fg, sub = {'red': (RED, WHITE, WHITE), 'white': (WHITE, RED, BLACK), 'black': (BLACK, WHITE, GOLD), 'green': (GREEN, WHITE, WHITE)}[style]
    im = Image.new('RGB', (W * S, H * S), bg)
    dr = ImageDraw.Draw(im)
    b = 7 * S
    dr.rectangle([b, b, W * S - b, H * S - b], outline=sub, width=3 * S)
    ar, en = SLOGANS[key]
    h1 = _center(dr, W * S / 2, 14 * S, _ar(ar), F_CALLIG, (W - 50) * S, int(H * S * 0.66), fg)
    _center(dr, W * S / 2, (H - 44) * S, en, F_LAT, (W - 90) * S, int(H * S * 0.15), sub)
    return weather(im.resize((W, H), Image.LANCZOS), sum(map(ord, key)), 0.45)


def _flag_band(dr, x0, y0, x1, y1, stars=False):
    h = (y1 - y0) / 3
    dr.rectangle([x0, y0, x1, y0 + h], fill=RED)
    dr.rectangle([x0, y0 + h, x1, y0 + 2 * h], fill=WHITE)
    dr.rectangle([x0, y0 + 2 * h, x1, y1], fill=BLACK)


def poster_tones(path, levels=7, sat=1.05):
    """a painted portrait -> flat print tones: bilateral-like smoothing, then a few grey levels per channel"""
    im = Image.open(path).convert('RGB')
    a = np.asarray(im, np.float32) / 255.0
    a = ndimage.median_filter(a, size=(5, 5, 1))
    q = np.floor(a * levels) / (levels - 1)
    return Image.fromarray((np.clip(q * sat, 0, 1) * 255).astype('u1'))


def portrait_poster(art, key, size=(512, 640), frame='flag'):
    """the framed portrait of the offices and corridors: painting on top, the flag behind it, a slogan under it"""
    W, H = size
    S = 2
    im = Image.new('RGB', (W * S, H * S), WHITE)
    dr = ImageDraw.Draw(im)
    _flag_band(dr, 0, 0, W * S, H * S * 0.2)
    pic = poster_tones(os.path.join(ART, art))
    pw = int(W * S * 0.86); ph = int(H * S * 0.68)
    pic = pic.resize((pw, pw), Image.LANCZOS).crop((0, 0, pw, min(pw, ph)))
    x, y = (W * S - pw) // 2, int(H * S * 0.07)
    im.paste(pic, (x, y))
    dr.rectangle([x - 5 * S, y - 5 * S, x + pw + 5 * S, y + pic.size[1] + 5 * S], outline=GOLD, width=5 * S)
    ar, en = SLOGANS[key]
    yt = y + pic.size[1] + 12 * S
    h = _center(dr, W * S / 2, yt, _ar(ar), F_CALLIG, (W - 26) * S, int(H * S * 0.10), RED)
    _center(dr, W * S / 2, yt + h + 8 * S, en, F_LAT, (W - 60) * S, int(H * S * 0.027), BLACK)
    return weather(im.resize((W, H), Image.LANCZOS), sum(map(ord, art)), 0.3)


def mural(art, key, size=(1024, 512)):
    """the painted outside wall: the leader against a sun over the flag, a slogan beside him, brush edges into the render"""
    W, H = size
    S = 2
    im = Image.new('RGB', (W * S, H * S), (206, 182, 136))
    dr = ImageDraw.Draw(im)
    _flag_band(dr, 0, 0, W * S, H * S)
    cx, cy = int(W * S * 0.27), int(H * S * 0.55)
    for k in range(36):
        a0 = k * math.pi / 18
        r = W * S
        dr.polygon([(cx, cy), (cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a0 + 0.07), cy + r * math.sin(a0 + 0.07))], fill=GOLD)
    pic = poster_tones(os.path.join(ART, art), levels=6).resize((H * S, H * S), Image.LANCZOS)
    m = Image.new('L', pic.size, 0)
    ImageDraw.Draw(m).ellipse([18 * S, 10 * S, H * S - 18 * S, H * S + 200 * S], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(6 * S))
    im.paste(pic, (int(W * S * 0.27 - H * S / 2), 0), m)
    ar, en = SLOGANS[key]
    bx0 = int(W * S * 0.53)
    dr.rectangle([bx0, H * S * 0.22, W * S - 12 * S, H * S * 0.78], fill=WHITE, outline=BLACK, width=4 * S)
    tw = W * S - 12 * S - bx0 - 26 * S
    tcx = (bx0 + W * S - 12 * S) / 2
    w_ = ar.split()
    mid = (len(w_) + 1) // 2
    h = _center(dr, tcx, H * S * 0.25, _ar(' '.join(w_[:mid])), F_CALLIG, tw, int(H * S * 0.20), RED)
    _center(dr, tcx, H * S * 0.45, _ar(' '.join(w_[mid:])), F_CALLIG, tw, int(H * S * 0.20), RED)
    _center(dr, tcx, H * S * 0.68, en, F_LAT, tw, int(H * S * 0.05), BLACK)
    return weather(im.resize((W, H), Image.LANCZOS), sum(map(ord, art)) + 1, 0.7)


# ---- owner 11-06 item 71 (SS_WORLD=1): no English on Iraqi walls, painted art instead of cut-out cartoons, cloth that hangs, paper that has aged, frames in offices
WORLD = os.environ.get('SS_WORLD', '1') == '1'
ART2 = os.path.join(ROOT, 'work', 'sandstorm', 'world', 'art')
PICK = {'beret': 'por_beret_1.png', 'suit': 'por_suit_0.png', 'salute': 'mur_salute_0.png', 'horse': 'mur_horse_3.png', 'beret2': 'por_beret_2.png'}     # (the chosen paintings)


def _noise2(h, w, seed, octaves=(5, 11, 26, 60)):
    rng = np.random.default_rng(seed)
    n = np.zeros((h, w), np.float32)
    for o in octaves:
        g = Image.fromarray((rng.random((o, o)) * 255).astype('u1')).resize((w, h), Image.BICUBIC)
        n += np.asarray(g, np.float32) / 255.0 / o ** 0.45
    return n / n.max()


def sun_bleach(im, seed, k=0.5):
    """years of sun: colours fade toward the plaster, dust settles from the top, the paint flakes along cracks"""
    w, h = im.size
    a = np.asarray(im.convert('RGB'), np.float32) / 255.0
    grey = a.mean(2, keepdims=True)
    a = a * (1 - 0.35 * k) + (grey * 0.55 + 0.42) * 0.35 * k
    n = _noise2(h, w, seed, octaves=(40, 90, 170))
    fl = np.clip((n - (0.80 - 0.06 * k)) * 16, 0, 1)[..., None]
    wall = np.array((0.74, 0.66, 0.52), np.float32)
    a = a * (1 - fl) + wall * fl
    rng = np.random.default_rng(seed + 1)
    runs = ndimage.gaussian_filter1d((rng.random((h, w)) > 0.9985).astype(np.float32), 40, axis=0)
    a = a * (1 - np.clip(runs * 9, 0, 0.16)[..., None])
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype('u1'))


def banner2(key, style='red', size=(1024, 192)):
    """a cloth slogan: Arabic only, hand-lettered, the cloth's folds run through the paint"""
    W, H = size
    S = 2
    bg = {'red': (150, 22, 26), 'white': (222, 216, 200), 'black': (22, 21, 20), 'green': (0, 88, 50)}[style]
    fg = (158, 22, 26) if style == 'white' else (236, 232, 218)
    im = Image.new('RGB', (W * S, H * S), bg)
    dr = ImageDraw.Draw(im)
    _center(dr, W * S / 2, 16 * S, _ar(SLOGANS[key][0]), F_CALLIG, (W - 70) * S, int(H * S * 0.82), fg)
    im = im.resize((W, H), Image.LANCZOS)
    a = np.asarray(im, np.float32) / 255.0
    x = np.arange(W)[None, :]
    fold = np.sin(x / 37.0 + 1.0) * 0.5 + np.sin(x / 13.0) * 0.28 + np.sin(x / 91.0 + 2.0) * 0.6
    y = np.arange(H)[:, None] / H
    sag = 1 + 0.10 * fold * (0.45 + 0.55 * np.sin(y * math.pi))
    a = a * sag[..., None]
    edge = np.minimum(y, 1 - y)
    a = a * np.clip(edge * 22 + 0.55, 0, 1)[..., None]
    n = _noise2(H, W, sum(map(ord, key)), octaves=(8, 24, 80))
    a = a * (0.84 + 0.26 * n)[..., None]                    # (sun and dust in the weave: no flaking, it is cloth)
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype('u1'))


def _paper_age(im, seed):
    """paper on a wall: yellowed, creased from folding, corners lifting"""
    w, h = im.size
    a = np.asarray(im.convert('RGB'), np.float32) / 255.0
    a = a * np.array((1.0, 0.95, 0.84), np.float32)
    for f, ax in ((0.5, 0), (0.5, 1)):
        c = int((w if ax == 0 else h) * f)
        d = np.abs((np.arange(w)[None, :] if ax == 0 else np.arange(h)[:, None]) - c)
        a = a * (1 - 0.22 * np.exp(-(d / 2.2) ** 2))[..., None]
    n = _noise2(h, w, seed)
    a = a * (0.86 + 0.26 * n)[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype('u1'))


def poster2(art, key, size=(512, 640)):
    """a printed poster: the painted portrait, the flag's colours along the top, the slogan below"""
    W, H = size
    S = 2
    im = Image.new('RGB', (W * S, H * S), (232, 228, 214))
    dr = ImageDraw.Draw(im)
    _flag_band(dr, 0, 0, W * S, H * S * 0.05)
    pic = Image.open(os.path.join(ART2, art)).convert('RGB')
    ph = int(H * S * 0.76); pw = int(ph * pic.width / pic.height)
    if pw > W * S:
        pw = W * S; ph = int(pw * pic.height / pic.width)
    pic = pic.resize((pw, ph), Image.LANCZOS)
    im.paste(pic, ((W * S - pw) // 2, int(H * S * 0.05)))
    _center(dr, W * S / 2, H * S * 0.825, _ar(SLOGANS[key][0]), F_CALLIG, (W - 30) * S, int(H * S * 0.13), RED)
    return _paper_age(im.resize((W, H), Image.LANCZOS), sum(map(ord, art)))


def _flag_field(W, H, S):
    """the flag painted on plaster: three bars, three green stars, the takbir in the white"""
    im = Image.new('RGB', (W * S, H * S), (226, 218, 198))
    dr = ImageDraw.Draw(im)
    h = H * S / 3
    dr.rectangle([0, 0, W * S, h], fill=(156, 24, 28))
    dr.rectangle([0, 2 * h, W * S, H * S], fill=(24, 22, 20))
    for k in (-1, 0, 1):
        cx, cy, r = W * S * 0.70 + k * W * S * 0.2, h * 1.5, h * 0.2
        pts = [(cx + (r if q % 2 == 0 else r * 0.42) * math.sin(q * math.pi / 5), cy - (r if q % 2 == 0 else r * 0.42) * math.cos(q * math.pi / 5)) for q in range(10)]
        dr.polygon(pts, fill=(0, 104, 60))
    _center(dr, W * S * 0.80, h * 1.14, _ar('الله'), F_CALLIG, W * S * 0.1, int(h * 0.62), (0, 104, 60))    # (the 1991 flag: the takbir between the stars, read from the right)
    _center(dr, W * S * 0.60, h * 1.14, _ar('أكبر'), F_CALLIG, W * S * 0.1, int(h * 0.62), (0, 104, 60))
    return im


def _bust(art, h_px):
    """the oil portrait with its background painted out: head and shoulders with a feathered edge"""
    pic = Image.open(os.path.join(ART2, art)).convert('RGB')
    r = h_px / pic.height
    pic = pic.resize((int(pic.width * r), h_px), Image.LANCZOS)
    m = Image.new('L', pic.size, 0)
    w, h = pic.size
    dr = ImageDraw.Draw(m)
    dr.ellipse([w * 0.20, h * 0.08, w * 0.82, h * 0.70], fill=255)
    dr.polygon([(w * 0.0, h), (w * 0.08, h * 0.72), (w * 0.3, h * 0.58), (w * 0.72, h * 0.58), (w * 0.98, h * 0.70), (w, h)], fill=255)
    return pic, m.filter(ImageFilter.GaussianBlur(h_px * 0.012))


def mural2(art, key, size=(1024, 512), scene=None):
    """painted straight on the wall by a sign painter: the flag or a scene behind, the leader's portrait, a slogan band; sun-bleached, flaked only in small patches"""
    W, H = size
    S = 2
    im = _flag_field(W, H, S)
    if scene:
        pic = Image.open(os.path.join(ART2, scene)).convert('RGB')
        r = H * 0.8 * S / pic.height
        pic = pic.resize((int(pic.width * r), int(H * 0.8 * S)), Image.LANCZOS)
        im.paste(pic, (W * S - pic.width, 0))
    b, m = _bust(art, int(H * 0.8 * S))
    im.paste(b, (int(W * S * 0.02), 0), m)
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, H * S * 0.8, W * S, H * S], fill=(150, 22, 26))
    _center(dr, W * S / 2, H * S * 0.815, _ar(SLOGANS[key][0]), F_CALLIG, (W - 60) * S, int(H * S * 0.17), (240, 234, 216))
    return sun_bleach(im.resize((W, H), Image.LANCZOS), sum(map(ord, art)) + sum(map(ord, key)), 0.5)


REAL = {'mural_a': 'real_mural_a.png', 'mural_b': 'real_mural_b.png', 'bust_a': 'real_bust_a.png', 'bust_b': 'real_bust_b.png'}   # (work/sandstorm/world/realart.py)


def aged(im, seed, k=0.35):
    """a photo made to sit in the room: a little less colour, the light warm and lower, dust settled from the top, a soft dark rim"""
    a = np.asarray(im.convert('RGB'), np.float32) / 255.0
    g = a.mean(2, keepdims=True)
    a = a * 0.82 + g * 0.18
    a = 0.06 + a * 0.84
    a = a * np.array([1.0, 0.96, 0.88], np.float32)
    h, w = a.shape[:2]
    rng = np.random.default_rng(seed)
    n = np.asarray(Image.fromarray((rng.random((12, 12)) * 255).astype('u1')).resize((w, h), Image.BICUBIC), np.float32)[..., None] / 255.0
    yy, xx = np.mgrid[0:h, 0:w]
    rim = np.clip(np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) - 0.6, 0, 1)[..., None]
    a = a * (1 - k * 0.35 * n) * (1 - 0.35 * rim)
    a = a + (1 - yy[..., None] / h) * k * 0.05 * np.array([0.8, 0.7, 0.55], np.float32)
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype('u1'))


def real_mural(art, size, seed):
    """a real tile mural, straightened (realart.py), sun-bleached and dusty like the paintings round it"""
    pic = Image.open(os.path.join(ART2, art)).convert('RGB').resize(size, Image.LANCZOS)
    return sun_bleach(aged(pic, seed, 0.4), seed, 0.35)


def framed(art, size=(512, 640)):
    """an oil portrait for a frame: nothing on it but the painting"""
    pic = Image.open(os.path.join(ART2, art)).convert('RGB')
    r = max(size[0] / pic.width, size[1] / pic.height)
    pic = pic.resize((int(pic.width * r) + 1, int(pic.height * r) + 1), Image.LANCZOS)
    x, y = (pic.width - size[0]) // 2, (pic.height - size[1]) // 3
    return pic.crop((x, y, x + size[0], y + size[1]))


def _pot(img):
    """resize to the next power-of-2 sides (the wall panel keeps the real proportions)"""
    H, W = img.shape[:2]
    nh, nw = 1 << int(round(math.log2(H))), 1 << int(round(math.log2(W)))
    if (nh, nw) == (H, W):
        return img
    im = Image.fromarray((np.clip(img[..., :3], 0, 1) * 255).astype('u1')).resize((nw, nh), Image.LANCZOS)
    return np.dstack([np.asarray(im, np.float32) / 255.0, np.ones((nh, nw), np.float32)])


def _plate(w, h, thick=0.02):
    import modelkit as MK, biprefabs as BP
    front = MK.panel((0.0, thick + 0.012, h / 2), (-1, 0, 0), (0, 0, 1), w, h)      # (owner 115: 12 mm proud of the backing, 2 mm flickered from the side)
    back = BP.box_m(-w / 2, 0.0, 0.0, w / 2, thick, h)
    return MK.model([(0, [front]), (1, [back])], [back])


def _cloth(w, h):
    """a banner tied at its corners: six panels at slightly different depths so it hangs like cloth, two ropes"""
    import modelkit as MK, biprefabs as BP
    parts = []
    n = 6
    off = [0.03, 0.09, 0.05, 0.11, 0.06, 0.03, 0.05]
    for k in range(n):
        x0, x1 = w / 2 - w * k / n, w / 2 - w * (k + 1) / n
        y0, y1 = off[k], off[k + 1]
        c = ((x0 + x1) / 2, (y0 + y1) / 2, h / 2)
        r = np.array((x1 - x0, y1 - y0, 0.0))
        parts.append(MK.panel(c, r, (0, 0, 1), float(np.linalg.norm(r)), h, uv=(k / n, 0.0, (k + 1) / n, 1.0)))
    rope = [BP.box_m(w / 2, 0.0, h - 0.04, w / 2 + 0.25, 0.03, h - 0.02), BP.box_m(-w / 2 - 0.25, 0.0, h - 0.04, -w / 2, 0.03, h - 0.02)]
    return MK.model([(0, parts), (1, rope)], [BP.box_m(-w / 2, 0.0, 0.0, w / 2, 0.05, h)])


def _frame(w, h):
    """a gilt frame round a painting: origin bottom centre on the wall, +y out"""
    import modelkit as MK, biprefabs as BP
    b = 0.06
    pic = MK.panel((0.0, 0.034, h / 2), (-1, 0, 0), (0, 0, 1), w, h)               # (owner 115: 14 mm over the backing, still inside the 5 cm frame)
    bar = [BP.box_m(-w / 2 - b, 0.0, -b, w / 2 + b, 0.05, 0.0), BP.box_m(-w / 2 - b, 0.0, h, w / 2 + b, 0.05, h + b), BP.box_m(-w / 2 - b, 0.0, 0.0, -w / 2, 0.05, h), BP.box_m(w / 2, 0.0, 0.0, w / 2 + b, 0.05, h)]
    back = BP.box_m(-w / 2, 0.0, 0.0, w / 2, 0.02, h)
    return MK.model([(0, [pic]), (1, bar + [back])], [BP.box_m(-w / 2 - b, 0.0, -b, w / 2 + b, 0.05, h + b)])


def _gilt():
    a = np.zeros((64, 64, 4), np.float32)
    n = _noise2(64, 64, 5)
    a[..., 0], a[..., 1], a[..., 2], a[..., 3] = 0.46 + 0.3 * n, 0.33 + 0.22 * n, 0.12 + 0.1 * n, 1.0
    return a


def register(lib):
    """one texture + one thin plate model per sheet: origin = bottom centre on the wall, +y out of the wall"""
    s = sheets()
    if WORLD:
        lib.texture('ssp_gilt', _gilt)
    for nm, (img, w, h) in s.items():
        tx = 'ssp_' + nm
        lib.texture(tx, (lambda i_: (lambda: _pot(i_)))(img))
        if WORLD and nm.startswith('ban_'):
            lib.add('sp_%s_1' % nm, (lambda w_, h_: (lambda: _cloth(w_, h_)))(w, h), [tx, 'jr_dark'], lod_like='406_68_1')
        elif WORLD and nm.startswith('fr_'):
            lib.add('sp_%s_1' % nm, (lambda w_, h_: (lambda: _frame(w_, h_)))(w, h), [tx, 'ssp_gilt'], lod_like='406_68_1')
        else:
            lib.add('sp_%s_1' % nm, (lambda w_, h_: (lambda: _plate(w_, h_)))(w, h), [tx, 'jr_dark'], lod_like='406_68_1')
    for k in ('m1', 'm2'):                                        # the roadside board: the same painting on two steel posts, in its own proportions
        if 'mur_' + k in s:
            lib.add('sp_b%s_1' % k, (lambda w_, h_: (lambda: _board(w_, h_)))(s['mur_' + k][1], s['mur_' + k][2]), ['ssp_mur_' + k, 'jr_dark'], lod_like='406_68_1')
    return s


def _board(w=5.0, h=2.5):
    import modelkit as MK, biprefabs as BP
    z0 = 1.5 if h < 3.5 else 0.6
    front = MK.panel((0.0, 0.052, z0 + h / 2), (-1, 0, 0), (0, 0, 1), w, h)
    rear = MK.panel((0.0, -0.062, z0 + h / 2), (1, 0, 0), (0, 0, 1), w, h)          # (judge V02: the back was a bare dark slab)
    back = BP.box_m(-w / 2, -0.05, z0, w / 2, 0.04, z0 + h)      # (owner 115: the board's face 12 mm off it)
    legs = [BP.box_m(x - 0.06, -0.18, 0.0, x + 0.06, -0.07, z0 + h - 0.1) for x in (-(w / 2 - 0.4), w / 2 - 0.4)]   # (judge V02: the posts stood in front of the picture)
    return MK.model([(0, [front, rear]), (1, [back] + legs)], legs + [back])


F_ = -34.0                                                        # (ssbase.F, the hall floor)
# (N5 11-17, ss-ending; default OFF = the installed place): the hall mural mur_m2 (4.46 m tall, F_+5.0..9.46) hangs behind the south wall's
#  long pipe (ssbase.py hall: cyl r 0.16 at y Y0+0.4, z F+7.6, x X0..X1) which crosses its middle. SS_MURAL_LOW=1 hangs it 2.15 m lower
#  (F_+2.85..7.31): 0.13 m under the pipe's lowest face, 0.78 m over the top of 'SS base generator 0' (wd337_11_1, F..F+2.07) under it.
#  Offline on build/ssb2 (platevis ray check, 810 eye lines): pipe gone from every line; propaudit plates: wall flat behind it both ways.
MURAL_M2_Z = F_ + (2.85 if os.environ.get('SS_MURAL_LOW', '0') == '1' else 5.0)
# (sheet, how, ...): 'wall' = the nearest wall of a standing spot (x, y, z of the floor, m), height of the plate's centre, optional point to prefer;
# 'at' = a known wall: point on it (x, y, z of the plate's bottom centre) and the plate's facing (gamma)
SPOTS = [
    # the gatehouse and the compound, where the man at the wire sees them
    ('mur_m1', 'wall', (156.0, 220.0, -7.0), 2.6, None),
    ('ban_umma', 'wall', (176.6, 198.0, -0.2), 2.6, None),
    # offices
    ('por_p2', 'wall', (50.0, 238.0, 5.4), 1.8, None),
    ('por_p3', 'wall', (54.4, 235.8, 8.5), 1.8, None),
    ('por_p1', 'wall', (93.7, 242.1, 10.0), 1.8, None),
    ('ban_iraq', 'wall', (68.1, 272.6, 14.6), 2.2, None),
    # under the hill
    ('mur_m2', 'at', (186.0, 196.03, MURAL_M2_Z), 0.0),
    ('ban_bilruh', 'at', (268.0 - 0.03, 240.0, F_ + 9.0), math.pi / 2),
    ('por_p1', 'at', (266.0 - 0.03, 205.0, F_ + 1.9), math.pi / 2),
    ('ban_nasr', 'at', (266.0 - 0.03, 200.5, F_ + 2.35), math.pi / 2),
]
# free-standing roadside boards (the walk found the old stone walls' collision far behind what is drawn: a plate there is buried):
# (sheet, x, y, point it faces)
BOARDS = [('mur_m1', 88.0, 50.0, (70.0, 45.0)), ('mur_m2', 90.0, 74.0, (80.0, 62.0)), ('mur_m1', 104.0, 214.0, (96.0, 201.0))]
GARRISON_SPOTS = [('por_p2', 'at', (222.4 + 0.03, 242.12, F_ + 1.2), -math.pi / 2), ('ban_iraq', 'at', (226.7, 207.6 - 0.03, F_ + 2.3), math.pi)]   # (judge V05; player2 N1 11-15: at x 224.95 it hung free 2.5 m in front of the armoury's
#  west wall (inner face 222.4) whose 3.4 m between the door and the corner cannot take the 4.1 m banner: now on the armoury's north wall (ssgarr ARM_Y), facing the room)
#  (S5 11-15, propaudit look_1 NO_WALL: por_p2 at y 244.0 hung in the mess west wall's doorway (open y 242.95..244.25, wall only behind its north end), and the
#  wall north of the door (244.35..247.0) has the shelf 'SS garrison prop 19' (y 245.15..246.66, 1.9 m tall) in front of it. y 244.0 -> 242.12: the middle of the
#  solid piece between the two doorways, face x 222.400 from y 241.3 to 242.95 (rays), nothing standing within 1.5 m of it)


SPOTS2 = [
    ('mur_m1', 'at', (162.13, 229.82 - 0.03, -7.22 + 0.6), math.pi),   # (judge E11 11-12: at 212.8 it stood free by the stair, a stringer through it: the north wall between the columns at x 160 and 164, ray-checked flat 160.9-163.4)
    ('ban_umma', 'wall', (176.6, 198.0, -0.2), 2.6, None),
    ('fr_s', 'wall', (178.0, 192.0, -7.2), 1.65, None),       # Kral's office
    ('fr_b', 'wall', (50.0, 238.0, 5.4), 1.8, None),          # the admin block
    ('por_p1', 'wall', (93.7, 242.1, 10.0), 1.8, None),
    ('por_p2', 'wall', (78.5, 118.0, 0.49), 1.75, None),      # the south barracks' lobby
    ('por_p1', 'wall', (129.5, 246.0, -6.83), 1.75, None),    # the north barracks' lobby
    ('ban_iraq', 'wall', (68.1, 272.6, 14.6), 2.2, None),
    ('mur_m2', 'at', (186.0, 196.03, MURAL_M2_Z), 0.0),
    ('ban_bilruh', 'at', (268.0 - 0.03, 240.0, F_ + 3.2), math.pi / 2),       # (judge V11: 9 m up it read as a thin red strip)
    ('fr_b', 'at', (266.0 - 0.03, 207.3, F_ + 1.4), math.pi / 2),             # (judge V06: at 205 it stood behind the cable-reel rack)
    ('ban_nasr', 'at', (266.0 - 0.03, 200.5, F_ + 2.35), math.pi / 2),
]


def _flat(K, w, w_m, h_m):
    """the whole plate lies on one wall: at every corner the wall is there, within 12 cm, and nothing stands in front of it"""
    c, g = np.array(w[0], float), w[1]
    n = np.array([-math.sin(g), math.cos(g), 0.0]); t_ = np.array([math.cos(g), math.sin(g), 0.0])
    for du in (-w_m / 2 - 0.08, 0.0, w_m / 2 + 0.08):
        for dz in (-h_m / 2 - 0.05, h_m / 2 + 0.05):
            a = c + (t_ * du + np.array([0, 0, dz]) + n * 0.5) * 4096.0
            if K.blocked(a, a - n * 0.40 * 4096.0, pad=0.01 * 4096) or not K.blocked(a, a - n * 0.68 * 4096.0, pad=0.01 * 4096):
                return False
    return True


def place(K, m, parent, log=print):
    from mission_lib import T
    import ssbase as SB
    done = []
    sh = sheets()
    for sp in (SPOTS2 if WORLD else SPOTS) + (GARRISON_SPOTS if SB.GARRISON2 else []):
        nm, how = sp[0], sp[1]
        if nm not in sh:
            continue
        h_m = sh[nm][2]
        if how == 'at':
            p, g = np.array(sp[2]) * 4096.0, sp[3]
        else:
            f = np.array(sp[2]) * 4096.0
            d = np.hypot(K.NODE_P[:, 0] - f[0], K.NODE_P[:, 1] - f[1]) + 3 * np.abs(K.NODE_P[:, 2] - f[2])
            w = None
            for q in K.NODE_P[np.argsort(d)[:60]]:                # (a graph node is a real floor point of that room)
                w = K.wall_near((q[0], q[1], q[2] - 0.3 * 4096), height_m=sp[3], max_m=4.0)
                if w and _flat(K, w, sh[nm][1], h_m):
                    f = q
                    break
                w = None
            if not w:
                log('poster %s at %s: no wall' % (nm, sp[2])); continue
            g = w[1]
            p = np.array([w[0][0] - math.sin(g) * 0.04 * 4096, w[0][1] + math.cos(g) * 0.04 * 4096, f[2] - 0.3 * 4096 + (sp[3] - h_m / 2) * 4096])
        i = K.nid()
        m.add_child(parent, T(i, 'EditRigidObj', 'SS poster %s' % nm, float(p[0]), float(p[1]), float(p[2]), 0.0, 0.0, float(g),
                              'sp_%s_1' % nm, 5, False, False))
        done.append((i, nm, [round(float(c) / 4096, 1) for c in p], round(float(g), 2)))
    for nm, x, y, tgt in BOARDS:
        if nm not in sh:
            continue
        best = None
        for dx, dy in ((0, 0), (2, 0), (-2, 0), (0, 2), (0, -2), (4, 0), (-4, 0), (0, 4), (0, -4), (3, 3), (-3, 3), (3, -3), (-3, -3)):
            px, py = (x + dx) * 4096.0, (y + dy) * 4096.0
            z = K.TERR.height(px, py)
            g = math.atan2(-(tgt[0] * 4096.0 - px), tgt[1] * 4096.0 - py)
            r = np.array([math.cos(g), math.sin(g), 0.0]) * 2.4 * 4096.0
            c = np.array([px, py, z + 2.2 * 4096.0])
            if np.isnan(z) or K.blocked(c - r, c + r, pad=0.2 * 4096) or K.blocked(c, np.array([tgt[0] * 4096.0, tgt[1] * 4096.0, c[2]]), pad=0.05 * 4096):
                continue
            if float(np.min(np.hypot(K.NODE_P[:, 0] - px, K.NODE_P[:, 1] - py))) < 1.0 * 4096:
                continue
            best = (px, py, z, g)
            break
        if not best:
            log('board %s at %s: no free spot' % (nm, (x, y))); continue
        i = K.nid()
        m.add_child(parent, T(i, 'EditRigidObj', 'SS board %s' % nm, float(best[0]), float(best[1]), float(best[2] - 0.15 * 4096), 0.0, 0.0, float(best[3]),
                              'sp_b%s_1' % nm[-2:], 5, False, False))
        done.append((i, 'board ' + nm, [round(float(c_) / 4096, 1) for c_ in best[:3]], round(float(best[3]), 2)))
    log('ssposters: %d placed %s' % (len(done), done))
    return done


# id -> (painter, width m, height m)
_SHEETS = {}


def sheets():
    out = _SHEETS
    if out:
        return out
    if WORLD:
        miss_ = [f_ for f_ in PICK.values() if not os.path.exists(os.path.join(ART2, f_))]
        assert not miss_, 'ssposters: art missing (work/sandstorm/world/art, gen_art.py): %s' % miss_
        for key, st in (('bilruh', 'red'), ('umma', 'white'), ('qaid', 'black'), ('jaysh', 'green'), ('nasr', 'red'), ('iraq', 'white')):
            out['ban_' + key] = (banner2(key, st), 3.6, 0.68)
        if all(os.path.exists(os.path.join(ART2, f_)) for f_ in REAL.values()):      # (owner 114: real photos of a real tile mural, work/sandstorm/art/real/CREDITS.md)
            for nm, fn, key in (('p1', REAL['bust_a'], 'qaid'), ('p2', REAL['bust_b'], 'iraq')):
                out['por_' + nm] = (poster2(fn, key), 0.72, 0.90)
            out['fr_b'] = (aged(framed(REAL['bust_a']), 61, 0.25), 0.62, 0.78)
            out['fr_s'] = (aged(framed(REAL['bust_b']), 62, 0.25), 0.62, 0.78)
            out['mur_m1'] = (real_mural(REAL['mural_a'], (768, 1024), 63), 2.4, 3.28)     # (the panel's own proportions; a real tile panel is 2-3 m)
            out['mur_m2'] = (real_mural(REAL['mural_b'], (640, 1024), 64), 2.6, 4.46)
        else:
            for nm, fn, key in (('p1', PICK['beret2'], 'qaid'), ('p2', PICK['suit'], 'iraq')):
                out['por_' + nm] = (poster2(fn, key), 0.72, 0.90)
            out['fr_b'] = (framed(PICK['beret']), 0.62, 0.78)
            out['fr_s'] = (framed(PICK['suit']), 0.62, 0.78)
            out['mur_m1'] = (mural2(PICK['beret'], 'umma'), 6.0, 3.0)
            out['mur_m2'] = (mural2(PICK['beret'], 'bilruh', scene=PICK['horse']), 9.0, 4.5)
        for k, v in out.items():
            im_ = v[0]
            if isinstance(im_, Image.Image):
                a_ = np.asarray(im_.convert('RGB'), np.float32) / 255.0
                out[k] = (np.dstack([a_, np.ones(a_.shape[:2], np.float32)]), v[1], v[2])
        return out
    for key, st in (('bilruh', 'red'), ('umma', 'white'), ('qaid', 'black'), ('jaysh', 'green'), ('nasr', 'red'), ('iraq', 'white')):
        out['ban_' + key] = (banner(key, st), 3.6, 0.68)
    for fn, key, nm in (('leader1.png', 'qaid', 'p1'), ('leader2.png', 'bilruh', 'p2'), ('leader3.png', 'iraq', 'p3')):
        if os.path.exists(os.path.join(ART, fn)):
            out['por_' + nm] = (portrait_poster(fn, key), 0.72, 0.90)
    for fn, key, nm, w_ in (('leader1.png', 'umma', 'm1', 6.0), ('leader3.png', 'bilruh', 'm2', 9.0)):
        if os.path.exists(os.path.join(ART, fn)):
            out['mur_' + nm] = (mural(fn, key), w_, w_ / 2)
    return out


def preview(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    s = sheets()
    W = 1400
    sh = Image.new('RGB', (W, 60 + 300 * ((len(s) + 2) // 3)), (40, 40, 40)); d = ImageDraw.Draw(sh)
    for k, (nm, (img, w, h)) in enumerate(s.items()):
        im = Image.fromarray((img[..., :3] * 255).astype('u1')); im.thumbnail((450, 270))
        x, y = (k % 3) * 465 + 5, (k // 3) * 300 + 22
        sh.paste(im, (x, y)); d.text((x, y - 14), '%s  %.1f x %.1f m' % (nm, w, h), fill='yellow')
    p = os.path.join(out_dir, 'posters.png'); sh.save(p)
    return p


if __name__ == '__main__':
    print(preview(sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'work', 'sandstorm', 'soldiers', 'prev')))
