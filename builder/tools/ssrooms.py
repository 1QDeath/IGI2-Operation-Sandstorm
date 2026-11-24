"""ssrooms - Sandstorm's rooms (owner 11-06 item 74), used by tools/ssworld.py behind SS_WORLD=1. The originals give props and how they use them: L24's store stands guns upright in the
231_14_1 wall rack, about 0.2 m apart, sorted by kind, ammo cases and shelves round it. Layouts here are new. The barracks wings' ground floors stood empty: the south one becomes the
armoury, the north one the unit clinic. World metres; 'floor' values measured from the collision mesh (work/sandstorm/world/floors.py)."""
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import altex
import ssposters as SP

PI = math.pi


def Y(dx, dy):
    """the yaw that turns model +y toward (dx, dy)"""
    return math.atan2(-dx, dy)


E, W_, N, S = Y(1, 0), Y(-1, 0), Y(0, 1), Y(0, -1)
F_ARM, F_MED, F_KRAL, F_STS, F_STN, F_BASE = 0.31, -7.01, -7.21, 0.25, -7.22, -34.0
F_SEW = -20.59                                             # (the sewer CHANNEL floor, under 0.3 m of water since owner 95 (ssworld.WATER_FLOOR) - not a walkway)
F_SEWWALK = -19.84                                         # (the sewer side walks; ss-look S6 11-15: the medipack and its carton moved here, out of the water)
RACK_Z = 0.98                                              # (the rack's top edge over the floor; the guns' centres 0.55 m under that. L24 hangs it at 1.37 m, which leaves its
                                                           #  legless bottom shelf 0.40 m over the floor: player2 N2 11-15 saw it floating. Model z -0.972..0: now it stands on the floor)


# ------------------------------------------------------------------------------------------------ textures
def _rgba(im):
    a = np.asarray(im.convert('RGB'), np.float32) / 255.0
    return np.dstack([a, np.ones(a.shape[:2], np.float32)])


def _grime(im, seed, k=0.22):
    """soft stains and a dirty lower edge: nothing in this base is new"""
    w, h = im.size
    rng = np.random.default_rng(seed)
    a = np.asarray(im.convert('RGB'), np.float32) / 255.0
    n = np.zeros((h, w), np.float32)
    for o in (6, 14, 40):
        g = Image.fromarray((rng.random((o, o)) * 255).astype('u1')).resize((w, h), Image.BICUBIC)
        n += np.asarray(g, np.float32) / 255.0 / (o ** 0.5)
    n = n / n.max()
    v = np.linspace(0, 1, h)[:, None] ** 3
    d = np.clip((n - 0.45) * 1.6, 0, 1) * k + v * k * 0.6
    a = a * (1 - d[..., None])
    a = a + (rng.random((h, w, 1)) - 0.5) * 0.025
    return _rgba(Image.fromarray((np.clip(a, 0, 1) * 255).astype('u1')))


def _text(d, cx, y, s, path, w, pt, fill):
    return SP._center(d, cx, y, SP._ar(s), path, w, pt, fill)


def tx_white():
    return _grime(Image.new('RGB', (128, 128), (214, 214, 206)), 11, 0.1)


def tx_mattress():
    im = Image.new('RGB', (128, 128), (196, 194, 180))
    d = ImageDraw.Draw(im)
    for x in range(0, 128, 16):
        d.rectangle([x, 0, x + 5, 128], fill=(160, 170, 182))
    return _grime(im, 12, 0.28)


def tx_crescent():
    """the clinic's door plate: the Red Crescent, 'unit clinic' """
    W_, H_ = 512, 256
    im = Image.new('RGB', (W_, H_), (226, 222, 208))
    d = ImageDraw.Draw(im)
    d.rectangle([8, 8, W_ - 9, H_ - 9], outline=(170, 26, 30), width=6)
    cx, cy, r = 112, 128, 80
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(176, 28, 30))
    d.ellipse([cx - r + 34, cy - r + 8, cx + r + 18, cy + r - 8], fill=(226, 222, 208))
    _text(d, 345, 44, 'مستوصف الوحدة', SP.F_CALLIG, 300, 78, (150, 24, 26))
    _text(d, 345, 150, 'الهلال الأحمر', SP.F_CALLIG, 280, 56, (40, 38, 36))
    return _grime(im, 13, 0.12)


def tx_armsign():
    W_, H_ = 512, 256
    im = Image.new('RGB', (W_, H_), (58, 66, 44))
    d = ImageDraw.Draw(im)
    d.rectangle([8, 8, W_ - 9, H_ - 9], outline=(214, 196, 120), width=5)
    _text(d, W_ / 2, 34, 'مخزن الأسلحة', SP.F_CALLIG, 450, 112, (226, 208, 130))
    _text(d, W_ / 2, 166, 'ممنوع الدخول إلا بإذن آمر الوحدة', SP.F_CALLIG, 450, 52, (226, 208, 130))
    return _grime(im, 14, 0.3)


def tx_medcab():
    """a white medicine cupboard: two glass doors, rows of bottles and boxes behind"""
    W_, H_ = 256, 512
    im = Image.new('RGB', (W_, H_), (208, 208, 200))
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(15)
    for k, (x0, x1) in enumerate(((12, 122), (134, 244))):
        d.rectangle([x0, 12, x1, 372], fill=(60, 66, 66), outline=(160, 160, 152), width=3)
        for sy in (120, 244, 368):
            d.rectangle([x0 + 3, sy, x1 - 3, sy + 4], fill=(178, 178, 170))
            x = x0 + 6
            while x < x1 - 16:
                w = int(rng.integers(10, 22)); h = int(rng.integers(36, 92))
                col = [(120, 70, 40), (210, 210, 200), (60, 90, 120), (190, 180, 150), (40, 80, 60)][int(rng.integers(0, 5))]
                d.rectangle([x, sy - h, x + w, sy], fill=col)
                x += w + int(rng.integers(2, 8))
        d.line([x0 + 8, 40, x0 + 40, 12], fill=(150, 165, 165), width=4)
    d.rectangle([12, 392, 122, 498], outline=(176, 176, 168), width=3)
    d.rectangle([134, 392, 244, 498], outline=(176, 176, 168), width=3)
    return _grime(im, 15, 0.1)


def tx_carton():
    W_, H_ = 256, 256
    im = Image.new('RGB', (W_, H_), (168, 136, 96))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 112, W_, 144], fill=(190, 166, 120))
    cx, cy, r = 128, 74, 42
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(170, 30, 30))
    d.ellipse([cx - r + 18, cy - r + 5, cx + r + 10, cy + r - 5], fill=(168, 136, 96))
    _text(d, 128, 160, 'مواد طبية', SP.F_CALLIG, 200, 70, (60, 40, 30))
    return _grime(im, 16, 0.3)


def tx_fakdoor():
    im = Image.new('RGB', (256, 256), (222, 222, 212))
    d = ImageDraw.Draw(im)
    d.rectangle([6, 6, 249, 249], outline=(170, 170, 160), width=4)
    cx, cy, r = 128, 104, 66
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(176, 28, 30))
    d.ellipse([cx - r + 28, cy - r + 7, cx + r + 14, cy + r - 7], fill=(222, 222, 212))
    _text(d, 128, 186, 'إسعاف أولي', SP.F_CALLIG, 210, 52, (150, 24, 26))
    return _grime(im, 21, 0.12)


def tx_tray():
    im = Image.new('RGB', (128, 128), (168, 172, 174))
    return _grime(im, 17, 0.2)


def tx_glassvial():
    im = Image.new('RGB', (64, 64), (196, 208, 208))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 64, 18], fill=(200, 200, 196))
    return _rgba(im)


ROSTER = ['الجندي علي حسين', 'الجندي كريم جاسم', 'نائب العريف سعد محمد', 'الجندي حيدر عباس', 'العريف ماجد ناصر', 'الجندي فاضل كاظم', 'الجندي عمار ياسين', 'الجندي رائد سلمان']


def _sheet(w, h, seed, title, rows, tilt=0):
    """a typed sheet: title, ruled lines of names and times"""
    s = Image.new('RGB', (w, h), (222, 216, 196))
    d = ImageDraw.Draw(s)
    _text(d, w / 2, 8, title, SP.F_CALLIG, w - 16, int(h * 0.11), (30, 30, 34))
    d.line([10, int(h * 0.17), w - 10, int(h * 0.17)], fill=(40, 40, 44), width=2)
    y = int(h * 0.2)
    rng = np.random.default_rng(seed)
    f = SP.ImageFont.truetype(SP.F_SIGN, max(10, int(h * 0.05)))
    for k in range(rows):
        t = SP._ar(ROSTER[(k + seed) % len(ROSTER)])
        d.text((w - 12, y), t, font=f, fill=(46, 46, 52), anchor='ra')
        d.text((12, y), '%02d:00' % ((k * 2 + 6) % 24), font=f, fill=(46, 46, 52))
        y += int(h * 0.07)
    return s.rotate(tilt, expand=True, fillcolor=(0, 0, 0)) if tilt else s


def tx_notice(seed=0):
    """a cork board: duty roster, standing orders, a pinned map sketch, curled corners"""
    W_, H_ = 512, 340
    rng = np.random.default_rng(100 + seed)
    a = 0.62 + (rng.random((H_, W_, 1)) - 0.5) * 0.12
    im = Image.fromarray((np.clip(a * np.array([0.72, 0.53, 0.33]), 0, 1) * 255).astype('u1'))
    im = im.filter(ImageFilter.GaussianBlur(0.7))
    titles = [('جدول الحراسة', 8), ('أوامر مستديمة', 6), ('تعليمات الأمان', 7), ('جدول الخفارات', 8)]
    pos = [(18, 16, 170, 214, -2), (200, 26, 150, 200, 2), (362, 14, 134, 180, -1), (214, 240, 130, 90, 3)]
    for k, (x, y, w, h, t) in enumerate(pos[:3]):
        ti, n = titles[(k + seed) % len(titles)]
        sh = _sheet(w, h, seed + k, ti, n, t)
        mask = sh.convert('L').point(lambda v: 255 if v > 6 else 0)
        shadow = Image.new('RGB', sh.size, (40, 28, 18))
        im.paste(shadow, (x + 3, y + 4), mask)
        im.paste(sh, (x, y), mask)
        d = ImageDraw.Draw(im)
        d.ellipse([x + w // 2 - 5, y + 2, x + w // 2 + 5, y + 12], fill=(170, 30, 30))
    d = ImageDraw.Draw(im)
    x, y, w, h = 28, 244, 170, 84
    d.rectangle([x, y, x + w, y + h], fill=(208, 200, 170), outline=(120, 110, 90))
    for k in range(6):                                     # (a hand-drawn plan of the base)
        d.line([x + 8 + k * 26, y + 8, x + 16 + k * 22, y + h - 10], fill=(70, 70, 120), width=1)
    d.rectangle([x + 60, y + 24, x + 120, y + 56], outline=(150, 40, 40), width=2)
    d.rectangle([0, 0, W_ - 1, H_ - 1], outline=(58, 40, 24), width=9)
    return _grime(im, 18 + seed, 0.2)


def tx_health():
    """clinic wall: 'cleanliness is part of faith', a hand-washing panel"""
    W_, H_ = 256, 360
    im = Image.new('RGB', (W_, H_), (226, 226, 214))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W_, 60], fill=(40, 96, 72))
    _text(d, W_ / 2, 8, 'النظافة من الإيمان', SP.F_CALLIG, 236, 44, (236, 236, 226))
    d.ellipse([58, 90, 198, 230], fill=(92, 140, 176))
    for k in range(5):
        d.ellipse([90 + k * 16, 120 + (k % 2) * 30, 106 + k * 16, 150 + (k % 2) * 30], fill=(226, 226, 214))
    _text(d, W_ / 2, 250, 'اغسل يديك قبل الطعام', SP.F_CALLIG, 226, 34, (30, 40, 40))
    _text(d, W_ / 2, 296, 'وزارة الصحة', SP.F_CALLIG, 200, 30, (90, 40, 40))
    return _grime(im, 19, 0.24)


def tx_map():
    """the staff map: desert, wadi, roads, grid, pins and a red marked line"""
    W_, H_ = 512, 256
    rng = np.random.default_rng(31)
    im = Image.new('RGB', (W_, H_), (206, 190, 150))
    d = ImageDraw.Draw(im)
    for k in range(9):
        x, y, r_ = int(rng.integers(0, W_)), int(rng.integers(0, H_)), int(rng.integers(30, 80))
        d.ellipse([x - r_, y - r_ // 2, x + r_, y + r_ // 2], outline=(176, 156, 112), width=1)
    d.line([(0, 196), (90, 170), (170, 182), (262, 130), (350, 120), (512, 64)], fill=(84, 124, 150), width=5)
    d.line([(30, 0), (112, 96), (214, 110), (306, 216), (360, 256)], fill=(120, 90, 60), width=2)
    d.line([(214, 110), (420, 90), (470, 0)], fill=(120, 90, 60), width=2)
    for x in range(0, W_, 64):
        d.line([x, 0, x, H_], fill=(150, 136, 104), width=1)
    for y in range(0, H_, 64):
        d.line([0, y, W_, y], fill=(150, 136, 104), width=1)
    d.line([(120, 60), (214, 104), (300, 86)], fill=(176, 30, 30), width=4)
    for x, y, c in ((214, 110, (170, 30, 30)), (122, 62, (30, 60, 150)), (302, 86, (170, 30, 30)), (380, 150, (30, 60, 150))):
        d.rectangle([x - 6, y - 6, x + 6, y + 6], fill=c, outline=(20, 20, 20))
    d.rectangle([0, 0, 200, 34], fill=(222, 214, 186))
    _text(d, 100, 2, 'خريطة العمليات', SP.F_CALLIG, 190, 34, (30, 30, 34))
    return _grime(im, 31, 0.14)


def tx_radio():
    W_, H_ = 128, 64
    im = Image.new('RGB', (W_, H_), (70, 80, 62))
    d = ImageDraw.Draw(im)
    d.rectangle([6, 6, 62, 30], fill=(24, 30, 26), outline=(120, 120, 100))
    for x in range(10, 60, 6):
        d.line([x, 10, x, 18 + (x % 4)], fill=(190, 170, 90))
    for x, y in ((80, 18), (106, 18), (80, 46), (106, 46)):
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(26, 26, 26), outline=(150, 150, 130))
    d.rectangle([8, 40, 60, 56], fill=(48, 56, 42), outline=(26, 30, 24))
    d.ellipse([8, 34, 14, 40], fill=(190, 40, 30))
    return _grime(im, 32, 0.1)


def tx_file():
    W_, H_ = 64, 128
    im = Image.new('RGB', (W_, H_), (112, 118, 110))
    d = ImageDraw.Draw(im)
    for k in range(4):
        y = 3 + k * 31
        d.rectangle([3, y, W_ - 4, y + 27], outline=(70, 74, 68), width=2)
        d.rectangle([24, y + 10, 40, y + 14], fill=(170, 170, 160))
        d.rectangle([22, y + 4, 42, y + 8], fill=(214, 208, 180))
    return _grime(im, 33, 0.24)


def tx_wood():
    W_ = 128
    im = Image.new('RGB', (W_, W_), (112, 82, 52))
    d = ImageDraw.Draw(im)
    for y in range(0, W_, 26):
        d.line([0, y, W_, y], fill=(68, 48, 30), width=2)
    return _grime(im, 34, 0.3)


def tx_tools():
    """a tool board: hooks, the painted outline of each tool, some of them home"""
    W_, H_ = 256, 128
    im = Image.new('RGB', (W_, H_), (84, 100, 88))
    d = ImageDraw.Draw(im)
    for k, x in enumerate(range(20, 240, 30)):
        h = 60 + (k * 37) % 40
        d.rectangle([x - 5, 16, x + 5, 16 + h], fill=(214, 208, 180))
        if k % 3 != 1:
            d.rectangle([x - 3, 16, x + 3, 12 + h], fill=(56, 58, 60))
            d.ellipse([x - 8, 8 + h, x + 8, 22 + h], fill=(56, 58, 60))
    return _grime(im, 35, 0.28)


def tx_sack():
    W_ = 128
    im = Image.new('RGB', (W_, W_), (182, 166, 128))
    d = ImageDraw.Draw(im)
    for k in range(0, W_, 4):
        d.line([k, 0, k, W_], fill=(170, 154, 116))
    _text(d, 64, 40, 'طحين', SP.F_CALLIG, 110, 56, (120, 40, 30))
    return _grime(im, 36, 0.2)


def tx_blanket():
    im = Image.new('RGB', (64, 64), (78, 84, 58))
    d = ImageDraw.Draw(im)
    for y in range(0, 64, 12):
        d.line([0, y, 64, y], fill=(52, 56, 40), width=2)
    return _grime(im, 37, 0.2)


def tx_rug():
    """a dealer's carpet: border, field, a lozenge, knots"""
    W_ = 256
    im = Image.new('RGB', (W_, W_), (118, 26, 30))
    d = ImageDraw.Draw(im)
    d.rectangle([6, 6, W_ - 7, W_ - 7], outline=(204, 176, 112), width=8)
    d.rectangle([24, 24, W_ - 25, W_ - 25], outline=(26, 34, 70), width=10)
    for k in range(5):
        r_ = 90 - k * 18
        d.polygon([(128, 128 - r_), (128 + r_, 128), (128, 128 + r_), (128 - r_, 128)], fill=[(26, 34, 70), (204, 176, 112), (118, 26, 30), (214, 204, 170), (26, 34, 70)][k])
    for x in range(44, 220, 28):
        for y in (44, 212):
            d.rectangle([x - 4, y - 4, x + 4, y + 4], fill=(204, 176, 112))
            d.rectangle([y - 4, x - 4, y + 4, x + 4], fill=(204, 176, 112))
    return _grime(im, 38, 0.18)


def tx_prayer():
    """a prayer mat: green field, the arch of the niche, a border"""
    W_, H_ = 128, 256
    im = Image.new('RGB', (W_, H_), (34, 84, 62))
    d = ImageDraw.Draw(im)
    d.rectangle([5, 5, W_ - 6, H_ - 6], outline=(196, 168, 104), width=5)
    d.rectangle([14, 14, W_ - 15, H_ - 15], outline=(120, 30, 34), width=3)
    d.polygon([(30, 96), (64, 34), (98, 96)], fill=(120, 30, 34))
    d.rectangle([30, 96, 98, 214], fill=(44, 104, 80), outline=(196, 168, 104))
    return _grime(im, 44, 0.16)


def tx_mirror():
    im = Image.new('RGB', (128, 64), (64, 70, 72))           # (judge V13: the flat grey read as a plate: a darker room reflected, two bright streaks, a steel rim)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 34, 128, 64], fill=(92, 88, 80))
    d.polygon([(18, 64), (52, 0), (70, 0), (36, 64)], fill=(170, 182, 186))
    d.polygon([(78, 64), (100, 0), (106, 0), (84, 64)], fill=(140, 150, 154))
    d.rectangle([0, 0, 127, 63], outline=(150, 152, 150), width=3)
    return _grime(im, 45, 0.16)


def tx_trolley():
    """the original trolley texture, taken down: pale as painted it reads white in any light here"""
    import igitex
    im = np.array(igitex.decode(_level('location3/LEVEL4').find_resource('LOCAL:textures/205_22_1.tex', 'textures')[1]), np.float32)
    im[..., :3] *= 0.42
    return im


def tx_locker():
    """judge R08: the map's 261_07_1 drew as a thin black slab here. Two steel doors, vents, number plates, handles"""
    W_, H_ = 128, 256
    im = Image.new('RGB', (W_, H_), (92, 104, 96))
    d = ImageDraw.Draw(im)
    for k, x0 in enumerate((4, 66)):
        d.rectangle([x0, 4, x0 + 58, H_ - 6], outline=(56, 62, 58), width=2)
        for y in range(16, 46, 6):
            d.rectangle([x0 + 14, y, x0 + 44, y + 2], fill=(40, 44, 42))
        d.rectangle([x0 + 20, 58, x0 + 38, 70], fill=(214, 206, 176))
        d.rectangle([x0 + (48 if k == 0 else 6), 120, x0 + (52 if k == 0 else 10), 150], fill=(170, 170, 160))
    return _grime(im, 46, 0.3)


def tx_rack():
    """a server rack's front: 19-inch units, drive bays, green and amber lamps, a vent, the cable comb"""
    W_, H_ = 128, 256
    rng = np.random.default_rng(47)
    im = Image.new('RGB', (W_, H_), (64, 66, 70))              # (judge E01: 30-58 grey read as plain black slabs; brighter units, LEDs that read, patch panels)
    d = ImageDraw.Draw(im)
    d.rectangle([2, 2, W_ - 3, H_ - 3], outline=(132, 134, 138), width=4)
    y = 10
    while y < H_ - 24:
        h = int(rng.choice([8, 8, 16, 24]))
        v = int(rng.integers(92, 128))
        d.rectangle([8, y, W_ - 9, y + h - 2], fill=(v, v + 2, v + 6), outline=(150, 152, 156))
        if h == 8 and rng.random() < 0.35:                      # a patch panel: ports and short coloured leads
            for k in range(12):
                d.rectangle([12 + k * 8, y + 2, 16 + k * 8, y + 5], fill=(30, 30, 32))
                d.line([14 + k * 8, y + 5, 14 + k * 8, y + 7], fill=[(40, 90, 200), (220, 200, 40), (230, 230, 230), (200, 50, 40)][k % 4])
        else:
            for k in range(int(rng.integers(3, 8))):
                x = 14 + k * 10
                d.rectangle([x, y + 2, x + 6, y + h - 4], fill=(150, 152, 156), outline=(60, 62, 66))
        for k in range(int(rng.integers(2, 5))):
            c = [(60, 255, 90), (255, 190, 40), (70, 160, 255), (60, 255, 90)][k % 4]
            d.rectangle([W_ - 24 + k * 5, y + 2, W_ - 21 + k * 5, y + 5], fill=c)
        y += h + 2
    for x in range(14, W_ - 14, 6):
        d.line([x, H_ - 20, x, H_ - 10], fill=(18, 18, 20), width=2)
    return _grime(im, 47, 0.12)


def tx_rackside():
    """judge E01: a rack's steel side panel (was jr_dark, a black slab): grey, vent slots in two columns, a maker's plate; 1 m a tile"""
    W_, H_ = 128, 128
    im = Image.new('RGB', (W_, H_), (98, 101, 106))
    d = ImageDraw.Draw(im)
    for x0 in (18, 74):
        for y in range(10, H_ - 8, 9):
            d.rectangle([x0, y, x0 + 36, y + 4], fill=(40, 42, 46))
            d.line([x0, y + 5, x0 + 36, y + 5], fill=(140, 143, 148))
    d.rectangle([0, 0, W_ - 1, H_ - 1], outline=(70, 72, 76), width=2)
    return _grime(im, 48, 0.14)


def tx_printer():
    """a laser printer's top and front: pale plastic, the output slot, a green display, buttons, a sheet in the tray"""
    W_, H_ = 128, 128
    im = Image.new('RGB', (W_, H_), (186, 184, 176))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 14, 118, 30], fill=(40, 40, 42))
    d.rectangle([16, 18, 112, 26], fill=(236, 236, 230))
    d.rectangle([14, 48, 52, 64], fill=(60, 120, 70)); d.rectangle([17, 51, 49, 61], fill=(120, 200, 120))
    for k in range(4):
        d.ellipse([62 + k * 13, 52, 70 + k * 13, 60], fill=(70, 72, 76))
    d.rectangle([10, 84, 118, 120], fill=(150, 148, 142)); d.line([10, 100, 118, 100], fill=(110, 108, 104), width=2)
    return _grime(im, 49, 0.18)


def tx_cable():
    """a cable run seen along it: columns are the cables (black, grey, blue, yellow)"""
    W_, H_ = 64, 64
    im = Image.new('RGB', (W_, H_), (22, 22, 24))
    d = ImageDraw.Draw(im)
    for k, c in enumerate([(22, 22, 24), (70, 72, 74), (30, 60, 140), (22, 22, 24), (170, 150, 40), (40, 40, 44), (120, 30, 30), (22, 22, 24)]):
        d.rectangle([k * 8, 0, k * 8 + 7, H_], fill=c)
        d.line([k * 8 + 2, 0, k * 8 + 2, H_], fill=tuple(min(255, v + 40) for v in c))
    return _grime(im, 50, 0.1)


def tx_galv():
    """galvanised tray steel"""
    W_, H_ = 64, 64
    im = Image.new('RGB', (W_, H_), (150, 154, 156))
    d = ImageDraw.Draw(im)
    for y in range(0, H_, 8):
        d.line([0, y, W_, y], fill=(120, 124, 126))
    return _grime(im, 51, 0.2)


def tx_lantern():
    """a paraffin lantern's glass: a warm flame glow, wire guards"""
    W_, H_ = 64, 64
    v, u = np.mgrid[-1:1:H_ * 1j, -1:1:W_ * 1j]
    g = np.clip(1.0 - 0.55 * (u ** 2 + (v * 1.2) ** 2), 0, 1)
    a = np.array([1.0, 0.82, 0.45]) * (0.45 + 0.55 * g)[..., None]
    a[(np.abs(u) < 0.06) | (np.abs(u - 0.6) < 0.05) | (np.abs(u + 0.6) < 0.05)] = (0.16, 0.14, 0.12)
    return _grime(Image.fromarray((np.clip(a, 0, 1) * 255).astype('u1')), 52, 0.08)


def tx_pipe():
    """an old water main: rust over grey paint, wet streaks"""
    W_, H_ = 64, 64
    rng = np.random.default_rng(53)
    a = np.zeros((H_, W_, 3), np.float32) + np.array([0.30, 0.30, 0.28])
    n = np.asarray(Image.fromarray((rng.random((8, 8)) * 255).astype('u1')).resize((W_, H_), Image.BICUBIC), np.float32) / 255.0
    a = a * (1 - n[..., None] * 0.7) + np.array([0.36, 0.20, 0.10]) * n[..., None] * 0.7
    return _grime(Image.fromarray((np.clip(a, 0, 1) * 255).astype('u1')), 54, 0.25)


def tx_rubble():
    """broken brick and concrete"""
    W_, H_ = 64, 64
    rng = np.random.default_rng(55)
    im = Image.new('RGB', (W_, H_), (96, 88, 78))
    d = ImageDraw.Draw(im)
    for _ in range(40):
        x, y, r = rng.integers(0, W_), rng.integers(0, H_), rng.integers(3, 9)
        c = [(120, 70, 50), (140, 134, 124), (80, 74, 66), (104, 60, 44)][int(rng.integers(0, 4))]
        d.ellipse([x - r, y - r, x + r, y + r], fill=c)
    return _grime(im, 56, 0.3)


def tx_cloth(rgb, seed, kind):
    """a garment on a line: shirt, towel or trousers, faded"""
    def fn():
        W_, H_ = 64, 128
        im = Image.new('RGB', (W_, H_), (0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W_, H_], fill=rgb)
        if kind == 'shirt':
            d.line([W_ // 2, 0, W_ // 2, H_], fill=tuple(int(v * 0.8) for v in rgb), width=2)
            for y in range(10, H_, 16):
                d.ellipse([W_ // 2 + 3, y, W_ // 2 + 6, y + 3], fill=(60, 60, 50))
        elif kind == 'towel':
            for y in (8, 14, H_ - 16, H_ - 10):
                d.line([0, y, W_, y], fill=(150, 60, 50), width=3)
        else:
            d.line([W_ // 2, 20, W_ // 2, H_], fill=tuple(int(v * 0.6) for v in rgb), width=3)
        d.rectangle([0, 0, W_, 4], fill=tuple(int(v * 0.7) for v in rgb))
        return _grime(im, seed, 0.25)
    return fn


def tx_sign2(ar, en, bg, fg, seed):
    """a door plate: the Arabic name, the English under it"""
    def fn():
        W_, H_ = 256, 128
        im = Image.new('RGB', (W_, H_), bg)
        d = ImageDraw.Draw(im)
        d.rectangle([5, 5, W_ - 6, H_ - 6], outline=fg, width=4)
        _text(d, W_ / 2, 14, ar, SP.F_CALLIG, 226, 60, fg)
        from PIL import ImageFont
        f = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', 24)
        d.text(((W_ - d.textlength(en, font=f)) / 2, 88), en, font=f, fill=fg)
        return _grime(im, seed, 0.2)
    return fn


def tx_tyre():
    im = Image.new('RGB', (64, 64), (34, 34, 34))
    d = ImageDraw.Draw(im)
    for x in range(0, 64, 8):
        d.line([x, 0, x, 64], fill=(18, 18, 18), width=2)
    return _rgba(im)


def tx_mon():
    """six small screens: grey yard pictures, a time stamp, one dead"""
    W_, H_ = 256, 128
    rng = np.random.default_rng(39)
    im = Image.new('RGB', (W_, H_), (44, 46, 44))
    d = ImageDraw.Draw(im)
    for k in range(6):
        x, y = 6 + (k % 3) * 84, 6 + (k // 3) * 60
        if k == 4:
            d.rectangle([x, y, x + 78, y + 54], fill=(10, 12, 12))
            continue
        v = int(rng.integers(150, 200))                     # (judge V09: the old grey read as dead tiles: sky, a wall, a road, a man, a time stamp)
        d.rectangle([x, y, x + 78, y + 54], fill=(v - 40, v, v - 30))
        d.rectangle([x, y + 30, x + 78, y + 54], fill=(v - 90, v - 70, v - 90))
        d.polygon([(x + 30, y + 54), (x + 44, y + 54), (x + 40, y + 30), (x + 36, y + 30)], fill=(v - 50, v - 40, v - 55))
        d.rectangle([x + 4 + k * 9, y + 10, x + 26 + k * 9, y + 32], fill=(v - 110, v - 95, v - 110))
        d.rectangle([x + 50, y + 26, x + 53, y + 38], fill=(30, 34, 30))
        d.rectangle([x + 2, y + 2, x + 34, y + 7], fill=(236, 240, 236))
    return _rgba(im)


REAL2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'sandstorm', 'art', 'real2')   # (job B 11-13: Commons photos, CREDITS.md there)


def tx_portrait(src, box, size, seed, k=0.3):
    """job B: a framed portrait from a real photo: a crop (box in the source's pixels, None = all), resized to a power-of-2 texture, aged like the paintings round it"""
    def fn():
        im = Image.open(src).convert('RGB')
        if box:
            im = im.crop(box)
        im = im.resize(size, Image.LANCZOS)
        a = np.asarray(SP.aged(im, seed, k).convert('RGB'), np.float32) / 255.0
        return np.dstack([a, np.ones(a.shape[:2], np.float32)])
    return fn


def tx_painted(src, box, size, seed):
    """job B: a painting on the plaster (the border brigade's emblem): sun-bleached, flaking, the wall's grain through it"""
    def fn():
        im = Image.open(src).convert('RGB')
        if box:
            im = im.crop(box)
        im = SP.sun_bleach(SP.aged(im.resize(size, Image.LANCZOS), seed, 0.45), seed, 0.4)
        return _grime(im, seed, 0.25)
    return fn


def tx_frame(rgb, seed):
    """job B: a frame's moulding (64 px): gold leaf, black lacquer or dark wood"""
    def fn():
        n = 64
        rng = np.random.default_rng(seed)
        v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
        g = 0.82 + 0.18 * np.sin(v * 9.0 + rng.random() * 3)[..., None] + 0.08 * (rng.random((n, n, 1)) - 0.5)
        a = np.clip(np.array(rgb, np.float32) / 255.0 * g, 0, 1)
        return np.dstack([a, np.ones((n, n), np.float32)])
    return fn


def tx_sign(ar, bg, fg, seed):
    def fn():
        W_, H_ = 256, 128
        im = Image.new('RGB', (W_, H_), bg)
        d = ImageDraw.Draw(im)
        d.rectangle([5, 5, W_ - 6, H_ - 6], outline=fg, width=4)
        _text(d, W_ / 2, 24, ar, SP.F_CALLIG, 226, 74, fg)
        return _grime(im, seed, 0.26)
    return fn


# ------------------------------------------------------------------------------------------------ models (+y = out of the wall / the front, origin on the floor or the wall)
def _bed():
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    fr = [bx(-0.47, -1.0, 0.42, 0.47, 1.0, 0.47)]
    for x in (-0.44, 0.44):
        for y in (-0.97, 0.97):
            fr.append(bx(x - 0.025, y - 0.025, 0.0, x + 0.025, y + 0.025, 0.46))
    fr += [bx(-0.47, 0.97, 0.78, 0.47, 1.0, 0.86), bx(-0.47, 0.97, 0.46, 0.47, 1.0, 0.52), bx(-0.47, -1.0, 0.56, 0.47, -0.97, 0.62)]      # (head and foot rails, open below)
    for x in (-0.44, 0.44):
        fr.append(bx(x - 0.025, 0.95, 0.46, x + 0.025, 1.0, 0.86))
    mat = [bx(-0.44, -0.96, 0.47, 0.44, 0.96, 0.60)]
    pil = [bx(-0.3, 0.55, 0.60, 0.3, 0.92, 0.68)]
    return MK.model([(0, fr), (1, mat), (2, pil)], [bx(-0.47, -1.0, 0.0, 0.47, 1.0, 0.68)])


def _drip():
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    st = [bx(-0.012, -0.012, 0.0, 0.012, 0.012, 1.85), bx(-0.24, -0.012, 0.02, 0.24, 0.012, 0.05), bx(-0.012, -0.24, 0.02, 0.012, 0.24, 0.05), bx(-0.14, -0.008, 1.83, 0.14, 0.008, 1.85)]
    bag = [bx(0.07, -0.05, 1.56, 0.15, 0.05, 1.82)]
    tube = [bx(0.106, -0.002, 0.82, 0.112, 0.002, 1.56)]
    return MK.model([(0, st + tube), (1, bag)], [bx(-0.03, -0.03, 0.0, 0.03, 0.03, 1.85)])


def _traymdl():
    """a steel tray for the table: a syringe with its needle, three ampoules, a folded gauze"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    tray = [bx(-0.21, -0.14, 0.0, 0.21, 0.14, 0.008), bx(-0.21, -0.14, 0.0, -0.20, 0.14, 0.03), bx(0.20, -0.14, 0.0, 0.21, 0.14, 0.03), bx(-0.21, -0.14, 0.0, 0.21, -0.13, 0.03), bx(-0.21, 0.13, 0.0, 0.21, 0.14, 0.03)]
    barrel = [bx(-0.09, 0.03, 0.02, 0.05, 0.052, 0.042)]
    plunger = [bx(0.05, 0.036, 0.026, 0.11, 0.046, 0.036), bx(0.11, 0.024, 0.02, 0.116, 0.058, 0.048)]
    needle = [bx(-0.16, 0.039, 0.029, -0.09, 0.043, 0.033)]
    vials = [BP.cyl_z(0.012, 0.008, 0.06, seg=6, cx=x, cy=-0.07) for x in (-0.1, -0.06, -0.02)]
    gauze = [bx(0.04, -0.11, 0.008, 0.17, -0.02, 0.03)]
    return MK.model([(0, tray + plunger), (1, barrel + needle + vials + gauze)], [bx(-0.21, -0.14, 0.0, 0.21, 0.14, 0.03)])


def _table():
    """a steel examination table: white enamel top with a raised lip, tube legs, a shelf under it"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    top = [bx(-1.0, -0.42, 0.82, 1.0, 0.42, 0.85), bx(-1.0, -0.42, 0.85, 1.0, -0.405, 0.87), bx(-1.0, 0.405, 0.85, 1.0, 0.42, 0.87), bx(-1.0, -0.42, 0.85, -0.985, 0.42, 0.87), bx(0.985, -0.42, 0.85, 1.0, 0.42, 0.87), bx(-0.9, -0.36, 0.28, 0.9, 0.36, 0.30)]
    legs = [bx(x - 0.02, y - 0.02, 0.0, x + 0.02, y + 0.02, 0.82) for x in (-0.94, 0.94) for y in (-0.37, 0.37)]
    return MK.model([(0, top), (1, legs)], [bx(-1.0, -0.42, 0.82, 1.0, 0.42, 0.87), bx(-0.9, -0.36, 0.28, 0.9, 0.36, 0.30)] + legs)


def _cab():
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    front = MK.panel((0.0, 0.42, 0.95), (-1, 0, 0), (0, 0, 1), 1.0, 1.9)
    body = [bx(-0.5, 0.0, 0.0, 0.5, 0.41, 1.9)]
    return MK.model([(1, [front]), (0, body)], body)


def _fak():
    """an open first-aid cupboard on the wall: back, sides, a shelf; its door stands open flat against the wall beside it, the crescent on it; the medipack sits on the lower shelf"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    w, h, d = 0.25, 0.56, 0.2
    pts = [bx(-w, 0.0, 0.0, w, 0.01, h), bx(-w, 0.0, 0.0, -w + 0.012, d, h), bx(w - 0.012, 0.0, 0.0, w, d, h), bx(-w, 0.0, 0.0, w, d, 0.012), bx(-w, 0.0, h - 0.012, w, d, h), bx(-w, 0.0, 0.31, w, d, 0.322)]
    door = bx(w, 0.0, 0.0, w + 2 * w, 0.02, h)
    face = MK.panel((w + w, 0.032, h / 2), (-1, 0, 0), (0, 0, 1), 2 * w, h)
    return MK.model([(0, pts + [door]), (1, [face])], [bx(-w, 0.0, 0.0, w, 0.03, h)])


def _plate(w, h, thick=0.015):
    import modelkit as MK, biprefabs as BP
    front = MK.panel((0.0, thick + 0.012, h / 2), (-1, 0, 0), (0, 0, 1), w, h)      # (owner 115: 12 mm proud of the backing)
    back = BP.box_m(-w / 2, 0.0, 0.0, w / 2, thick, h)
    return MK.model([(0, [front]), (1, [back])], [back])




def _pframe(w, h, b=0.05):
    """job B: a framed picture, origin bottom centre on the wall, +y out: the picture 3.4 cm out, the moulding round it, a backing board. Seen only"""
    import modelkit as MK, biprefabs as BP
    pic = MK.panel((0.0, 0.034, h / 2), (-1, 0, 0), (0, 0, 1), w, h)
    bar = [BP.box_m(-w / 2 - b, 0.0, -b, w / 2 + b, 0.045, 0.0), BP.box_m(-w / 2 - b, 0.0, h, w / 2 + b, 0.045, h + b), BP.box_m(-w / 2 - b, 0.0, 0.0, -w / 2, 0.045, h), BP.box_m(w / 2, 0.0, 0.0, w / 2 + b, 0.045, h)]
    back = BP.box_m(-w / 2, 0.0, 0.0, w / 2, 0.02, h)
    return MK.model([(0, [pic]), (1, bar + [back])], [_nocoll()])


ARCH_N = [(76.81, 2.60), (76.85, 2.68), (77.00, 2.91), (77.15, 3.11), (77.30, 3.18), (77.45, 3.24), (77.60, 3.31), (77.75, 3.37), (77.90, 3.44), (78.05, 3.42), (78.20, 3.35),
          (78.35, 3.28), (78.50, 3.21), (78.65, 3.14), (78.80, 3.01), (78.95, 2.78), (79.06, 2.60)]       # (judge Q23: the north armoury arch's soffit over its floor, x world)


def _transom():
    """judge Q23: the plank transom over the north armoury leaves: origin (77.935, 113.6, floor), vertical planks from 2.21 m up to the arch's soffit, 7 cm thick,
    just north of the leaves' plane, a dark batten across. Seen only"""
    import modelkit as MK, biprefabs as BP
    xs, hs = np.array([a for a, b in ARCH_N]), np.array([b for a, b in ARCH_N])
    soff = lambda x: float(np.interp(x, xs, hs)) - 0.01
    x0, x1, z0, y0, y1, c = 76.81, 79.06, 2.21, 0.045, 0.115, 77.935   # (redo 11-13: the leaf tops are at 2.207 over this floor (origin 0.295 + 2.222): 3 mm over them, no dark strip)
    planks = []
    edges = np.linspace(x0, x1, 15)
    for a, b in zip(edges[:-1], edges[1:]):
        planks.append(MK.hull_m(np.array([(a - c, y, z0) for y in (y0, y1)] + [(b - c, y, z0) for y in (y0, y1)] + [(a - c, y, soff(a)) for y in (y0, y1)] + [(b - c, y, soff(b)) for y in (y0, y1)]
                                         + [((a + b) / 2 - c, y, soff((a + b) / 2)) for y in (y0, y1)]), uv=1.0))
    batten = [BP.box_m(x0 - c + 0.05, y1, z0 + 0.12, x1 - c - 0.05, y1 + 0.025, z0 + 0.22)]
    return MK.model([(0, planks), (1, batten)], [_nocoll()])


def _carton():
    import modelkit as MK, biprefabs as BP
    b = BP.box_m(-0.25, -0.2, 0.0, 0.25, 0.2, 0.34, uv=2.0)
    return MK.model([(0, [b])], [b])


def _chair():
    """a steel mess chair, cheap (the originals cost 214 tris each); the sitter faces -y, like 261_06_1"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    fr = [bx(x - 0.015, y - 0.015, 0.0, x + 0.015, y + 0.015, 0.45) for x in (-0.2, 0.2) for y in (-0.2, 0.2)]
    fr += [bx(-0.2, 0.185, 0.45, -0.17, 0.215, 0.9), bx(0.17, 0.185, 0.45, 0.2, 0.215, 0.9)]
    wd = [bx(-0.22, -0.22, 0.44, 0.22, 0.22, 0.47), bx(-0.2, 0.18, 0.66, 0.2, 0.22, 0.88)]
    return MK.model([(0, fr), (1, wd)], [bx(-0.22, -0.22, 0.0, 0.22, 0.22, 0.88)])


def _maptable():
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    fr = [bx(-1.3, -0.75, 0.86, 1.3, 0.75, 0.9)] + [bx(x - 0.04, y - 0.04, 0.0, x + 0.04, y + 0.04, 0.86) for x in (-1.22, 1.22) for y in (-0.67, 0.67)]
    top = MK.panel((0.0, 0.0, 0.902), (1, 0, 0), (0, 1, 0), 2.56, 1.46)
    return MK.model([(0, [top]), (1, fr)], [bx(-1.3, -0.75, 0.0, 1.3, 0.75, 0.9)])


def _radio():
    """a field set on a desk: front = +y"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    b = bx(-0.26, -0.16, 0.0, 0.26, 0.16, 0.26)
    ant = bx(0.2, 0.0, 0.26, 0.21, 0.01, 0.8)
    face = MK.panel((0.0, 0.162, 0.13), (-1, 0, 0), (0, 0, 1), 0.5, 0.25)
    return MK.model([(0, [face]), (1, [b, ant])], [b])


def _filing():
    """front = +y"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    b = bx(-0.23, -0.3, 0.0, 0.23, 0.3, 1.3)
    face = MK.panel((0.0, 0.302, 0.65), (-1, 0, 0), (0, 0, 1), 0.46, 1.3)
    return MK.model([(0, [face]), (1, [b])], [b])


def _bench():
    """a workbench 2.4 m long on x: planks on a steel frame, a low shelf; +y = the side a man stands"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    wd = [bx(-1.2, -0.35, 0.84, 1.2, 0.35, 0.9, uv=1.0), bx(-1.1, -0.28, 0.2, 1.1, 0.28, 0.24, uv=1.0)]
    fr = [bx(x - 0.03, y - 0.03, 0.0, x + 0.03, y + 0.03, 0.84) for x in (-1.12, 0.0, 1.12) for y in (-0.3, 0.3)]
    return MK.model([(0, wd), (1, fr)], [bx(-1.2, -0.35, 0.0, 1.2, 0.35, 0.9)])


def _seat():
    """a long plank seat on three legs, for the changing room"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    return MK.model([(0, [bx(-0.9, -0.17, 0.42, 0.9, 0.17, 0.46)]), (1, [bx(x - 0.03, -0.14, 0.0, x + 0.03, 0.14, 0.42) for x in (-0.8, 0.0, 0.8)])], [bx(-0.9, -0.17, 0.0, 0.9, 0.17, 0.46)])


def _sacks():
    """a pallet of flour sacks, 1.2 x 1.0 m, two layers"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    p = [bx(-0.6, -0.5, 0.0, 0.6, 0.5, 0.12)]
    s = []
    for k, z in enumerate((0.12, 0.38)):
        for x in (-0.4, 0.0, 0.4):
            dx = 0.02 if k else 0.0
            s.append(bx(x - 0.19 + dx, -0.47, z, x + 0.19 + dx, 0.47, z + 0.25, uv=1.4))
    return MK.model([(0, s), (1, p)], [bx(-0.6, -0.5, 0.0, 0.6, 0.5, 0.64)])


def _blankets():
    import modelkit as MK, biprefabs as BP
    b = BP.box_m(-0.3, -0.2, 0.0, 0.3, 0.2, 0.3, uv=2.0)
    return MK.model([(0, [b])], [b])


def _rug():
    import modelkit as MK, biprefabs as BP
    return MK.model([(0, [MK.panel((0.0, 0.0, 0.012), (1, 0, 0), (0, 1, 0), 3.2, 2.2)])], [BP.box_m(-1.6, -1.1, 0.0, 1.6, 1.1, 0.008)])


def _mat():
    import modelkit as MK, biprefabs as BP
    return MK.model([(0, [MK.panel((0.0, 0.0, 0.01), (1, 0, 0), (0, 1, 0), 0.62, 1.15)])], [BP.box_m(-0.01, -0.01, 0.0, 0.01, 0.01, 0.002)])   # (a mat stops nobody)


def _shower():
    """a shower stall on a wall (+y into the room): two side panels, the pipe and rose, a duckboard"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    pan = [bx(-0.52, 0.0, 0.1, -0.5, 1.0, 1.9), bx(0.5, 0.0, 0.1, 0.52, 1.0, 1.9)]
    pipe = [bx(-0.02, 0.0, 0.8, 0.02, 0.04, 2.1), bx(-0.02, 0.0, 2.08, 0.02, 0.3, 2.12), bx(-0.08, 0.24, 2.04, 0.08, 0.36, 2.08), bx(-0.04, 0.02, 1.1, 0.04, 0.08, 1.16)]
    return MK.model([(0, pan), (1, pipe), (2, [bx(-0.48, 0.04, 0.0, 0.48, 0.98, 0.04, uv=1.0)])], pan + [bx(-0.48, 0.04, 0.0, 0.48, 0.98, 0.04)])


def _trough():
    """a steel wash trough 2.2 m long on x, four taps along the back (-y)"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    s = [bx(-1.1, -0.24, 0.72, 1.1, 0.24, 0.76), bx(-1.1, -0.24, 0.76, 1.1, -0.21, 0.86), bx(-1.1, 0.21, 0.76, 1.1, 0.24, 0.86), bx(-1.1, -0.24, 0.76, -1.07, 0.24, 0.86), bx(1.07, -0.24, 0.76, 1.1, 0.24, 0.86)]
    s += [bx(x - 0.03, y - 0.03, 0.0, x + 0.03, y + 0.03, 0.72) for x in (-1.0, 1.0) for y in (-0.18, 0.18)]
    t = [bx(x - 0.015, -0.24, 0.86, x + 0.015, -0.1, 1.0) for x in (-0.75, -0.25, 0.25, 0.75)]
    return MK.model([(0, s + t)], [bx(-1.1, -0.24, 0.0, 1.1, 0.24, 0.86)])


def _arm():
    """a steel tube 1.3 m along +y: holds a camera off the nearest wall, its far end buried in it"""
    import modelkit as MK, biprefabs as BP
    b = BP.box_m(-0.025, 0.0, -0.025, 0.025, 1.3, 0.025)
    return MK.model([(0, [b])], [BP.box_m(-0.02, 0.0, -0.02, 0.02, 0.02, 0.02)])


def _rod():
    """the same tube along +z, for a ceiling or a beam"""
    import modelkit as MK, biprefabs as BP
    b = [BP.box_m(-0.045, -0.045, 0.0, 0.045, 0.045, 1.3), BP.box_m(-0.09, -0.09, -0.02, 0.09, 0.09, 0.06)]     # (judge R07: a 5 cm tube read as a wire: a post and the clamp on the camera)
    return MK.model([(0, b)], [BP.box_m(-0.02, -0.02, 0.0, 0.02, 0.02, 0.02)])


def _locker():
    """a two-door steel locker, the footprint of 261_07_1: 1.0 x 0.8, +y to the wall"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    b = bx(-0.5, -0.4, 0.0, 0.5, 0.4, 1.9)                 # (the same box as 261_07_1's: the graph does not change)
    face = MK.panel((0.0, -0.402, 0.95), (1, 0, 0), (0, 0, 1), 0.98, 1.88)
    return MK.model([(0, [face]), (1, [b])], [b])


def _rack():
    """a server rack 0.6 x 1.0 x 2.0 m, fronts on both long ends (+-y)"""
    import modelkit as MK, biprefabs as BP
    b = BP.box_m(-0.3, -0.5, 0.0, 0.3, 0.5, 2.0)
    f1 = MK.panel((0.0, -0.502, 1.0), (1, 0, 0), (0, 0, 1), 0.58, 1.98)
    f2 = MK.panel((0.0, 0.502, 1.0), (-1, 0, 0), (0, 0, 1), 0.58, 1.98)
    return MK.model([(0, [f1, f2]), (1, [b])], [b])


def _partition(length, height=1.75, base=0.15):
    """a wash-room stall wall along y, on two steel feet"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    p = bx(-0.02, -length / 2, base, 0.02, length / 2, base + height, uv=1.0)
    feet = [bx(-0.03, y - 0.03, 0.0, 0.03, y + 0.03, base) for y in (-length / 2 + 0.1, length / 2 - 0.1)]
    return MK.model([(0, [p]), (1, feet)], [p])


def _tyres():
    """four lorry tyres in a stack"""
    import modelkit as MK, biprefabs as BP
    t = [BP.cyl_z(0.46, k * 0.25, k * 0.25 + 0.24, seg=10) for k in range(4)]
    return MK.model([(0, t)], [BP.box_m(-0.42, -0.42, 0.0, 0.42, 0.42, 1.0)])


def _screens():
    """a six-screen bank on a desk: front = +y"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    b = bx(-0.6, -0.16, 0.0, 0.6, 0.16, 0.6)
    face = MK.panel((0.0, 0.162, 0.3), (-1, 0, 0), (0, 0, 1), 1.16, 0.56)
    return MK.model([(0, [face]), (1, [b])], [b])


def _nocoll():
    import biprefabs as BP
    return BP.box_m(-0.03, -0.06, 0.0, 0.03, -0.02, 0.04)      # (a model needs a collision part: this one sits in the wall behind)


def _ctray(length):
    """judge E01: a ceiling cable tray along x, origin = the tray's floor centre: galvanised U, three cable bundles, two hanger rods up 0.27 m"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    L = length / 2
    tray = [bx(-L, -0.16, 0.0, L, 0.16, 0.012, uv=1.0), bx(-L, -0.16, 0.0, L, -0.148, 0.07, uv=1.0), bx(-L, 0.148, 0.0, L, 0.16, 0.07, uv=1.0)]
    rods = [bx(x - 0.01, -0.01, 0.0, x + 0.01, 0.01, 0.27, uv=1.0) for x in (-L + 0.3, L - 0.3)] + [bx(x - 0.02, -0.18, -0.02, x + 0.02, 0.18, 0.0, uv=1.0) for x in (-L + 0.3, L - 0.3)]
    cab = [BP.cyl_axis(0.035, -L, L, 'x', 8, at=(y, 0.045), uv=1.0) for y in (-0.08, 0.0, 0.08)]
    c = BP.box_m(-0.02, -0.02, 0.26, 0.02, 0.02, 0.27)
    return MK.model([(0, tray + rods), (1, cab)], [c])


def _printer():
    """a printer on a steel stand, front = +y"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    stand = bx(-0.3, -0.25, 0.0, 0.3, 0.25, 0.72)
    body = bx(-0.23, -0.2, 0.72, 0.23, 0.2, 0.94, uv=2.0)
    top = MK.panel((0.0, 0.0, 0.942), (1, 0, 0), (0, 1, 0), 0.46, 0.4)
    paper = bx(-0.105, -0.14, 0.72, 0.105, 0.16, 0.73, uv=4.0)
    return MK.model([(0, [top]), (1, [stand, body]), (2, [paper])], [stand, body])


def _lantern():
    """a paraffin lantern on a wall bracket, origin on the wall, +y out; its glow"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    arm = [bx(-0.015, 0.0, 0.18, 0.015, 0.22, 0.21), bx(-0.03, 0.0, 0.08, 0.03, 0.02, 0.3)]
    base = bx(-0.08, 0.14, -0.2, 0.08, 0.3, -0.17)
    glass = bx(-0.065, 0.155, -0.17, 0.065, 0.285, 0.0, uv=6.0)
    cap = [bx(-0.07, 0.15, 0.0, 0.07, 0.29, 0.03), bx(-0.01, 0.21, 0.03, 0.01, 0.23, 0.18)]
    import mefmesh
    gl = np.zeros(1, mefmesh.WOLG_DT)
    gl[0] = ((0.0, 0.22 * 4096.0, -0.09 * 4096.0), 380.0, 1.0, 0.78, 0.45, 0xABABABAB)
    return MK.model([(0, [glass]), (1, arm + [base] + cap)], [_nocoll()], glows=gl)


def _pipes():
    """two old mains along a wall (x, 6 m), origin on the wall at the lower pipe's height, +y out; three brackets"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    p = [BP.cyl_axis(0.09, -3.0, 3.0, 'x', 10, at=(0.16, 0.0), uv=1.0), BP.cyl_axis(0.06, -3.0, 3.0, 'x', 8, at=(0.14, 0.3), uv=1.0)]
    br = [bx(x - 0.03, 0.0, -0.12, x + 0.03, 0.28, -0.08) for x in (-2.6, 0.0, 2.6)] + [bx(x - 0.03, 0.0, 0.2, x + 0.03, 0.24, 0.24) for x in (-2.6, 0.0, 2.6)]
    return MK.model([(0, p), (1, br)], [_nocoll()])


def _planks():
    """three loose boards afloat"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    b = [bx(-0.9, -0.1, 0.0, 0.9, 0.1, 0.03), bx(-0.6, 0.15, 0.01, 0.8, 0.33, 0.04), bx(-1.0, -0.4, 0.0, 0.4, -0.22, 0.03)]
    return MK.model([(0, b)], [BP.box_m(-0.02, -0.02, -0.3, 0.02, 0.02, -0.26)])


def _rubble():
    """a heap of broken brick and concrete, 1.0 x 0.8 m"""
    import modelkit as MK, biprefabs as BP
    rng = np.random.default_rng(57)
    parts = []
    for k in range(9):
        c = rng.uniform((-0.4, -0.3, 0.0), (0.4, 0.3, 0.12))
        s = rng.uniform(0.08, 0.2, 3)
        pts = np.array([c + s * np.array([sx, sy, sz]) * rng.uniform(0.6, 1.0) for sx in (-1, 1) for sy in (-1, 1) for sz in (0, 1.4)])
        pts[:, 2] = np.maximum(pts[:, 2], 0.0)
        parts.append(MK.hull_m(pts * 1.0, uv=2.0))
    return MK.model([(0, parts)], [BP.box_m(-0.45, -0.35, 0.0, 0.45, 0.35, 0.25)])


def _laundry():
    """a washing line along a wall (x, 4.6 m), origin on the wall at line height, +y out: brackets, the line, shirts, a towel, trousers (both faces)"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    line = [bx(-2.3, 0.28, -0.006, 2.3, 0.292, 0.006, uv=1.0)] + [bx(x - 0.02, 0.0, -0.03, x + 0.02, 0.3, 0.03) for x in (-2.3, 2.3)]
    groups = {0: [], 1: [], 2: []}
    for k, (x, kind, w, h) in enumerate(((-1.7, 0, 0.55, 0.7), (-0.9, 1, 0.5, 0.8), (-0.1, 0, 0.55, 0.7), (0.75, 2, 0.4, 0.95), (1.6, 1, 0.5, 0.8))):
        for nx in (-1, 1):
            groups[kind].append(MK.panel((x, 0.286 + 0.004 * nx, -h / 2), (-nx, 0, 0), (0, 0, 1), w, h))
    return MK.model([(0, line), (1, groups[0]), (2, groups[1]), (3, groups[2])], [_nocoll()])



TEX = {'ssw_fakd': tx_fakdoor, 'ssw_white': tx_white, 'ssw_matt': tx_mattress, 'ssw_cres': tx_crescent, 'ssw_arms': tx_armsign, 'ssw_cab': tx_medcab, 'ssw_cart': tx_carton, 'ssw_tray': tx_tray, 'ssw_vial': tx_glassvial,
       'ssw_rckf': tx_rack, 'ssw_lkrf': tx_locker, 'ssw_pray': tx_prayer, 'ssw_mirr': tx_mirror, 'ssw_trol': tx_trolley, 'ssw_map': tx_map, 'ssw_rdo': tx_radio, 'ssw_filc': tx_file, 'ssw_wood': tx_wood, 'ssw_tool': tx_tools, 'ssw_sack': tx_sack, 'ssw_blkt': tx_blanket, 'ssw_rug': tx_rug, 'ssw_tyre': tx_tyre, 'ssw_mon': tx_mon,
       'ssw_sops': tx_sign('غرفة العمليات', (40, 50, 38), (222, 208, 140), 41), 'ssw_sqm': tx_sign('مخزن التجهيزات', (40, 50, 38), (222, 208, 140), 42), 'ssw_sfuel': tx_sign('ممنوع التدخين', (196, 170, 40), (30, 26, 20), 43),
       'ssw_rcks': tx_rackside, 'ssw_prnt': tx_printer, 'ssw_cbl': tx_cable, 'ssw_galv': tx_galv, 'ssw_lant': tx_lantern, 'ssw_pipe': tx_pipe, 'ssw_rubb': tx_rubble,
       'ssw_cl1': tx_cloth((150, 140, 100), 58, 'shirt'), 'ssw_cl2': tx_cloth((214, 210, 196), 59, 'towel'), 'ssw_cl3': tx_cloth((86, 92, 62), 60, 'trousers'),
       'ssw_ssrv': tx_sign2('غرفة الخوادم', 'SERVER ROOM', (40, 50, 38), (222, 208, 140), 61),
       # job B 11-13: door signs (Arabic, a small English line), portraits, frames, the brigade's emblem
       'ssw_dws': tx_sign2('الورشة', 'WORKSHOP', (40, 50, 38), (222, 208, 140), 71), 'ssw_dfu': tx_sign2('مخزن الوقود', 'FUEL STORE', (196, 170, 40), (30, 26, 20), 72),
       'ssw_drd': tx_sign2('غرفة اللاسلكي', 'RADIO ROOM', (40, 50, 38), (222, 208, 140), 73), 'ssw_dfd': tx_sign2('مخزن الأغذية', 'FOOD STORE', (40, 50, 38), (222, 208, 140), 74),
       'ssw_dkt': tx_sign2('المطبخ', 'KITCHEN', (226, 222, 210), (40, 40, 36), 75), 'ssw_dga': tx_sign2('المرآب', 'MOTOR POOL', (40, 50, 38), (222, 208, 140), 76),
       'ssw_dgp': tx_sign2('نقطة الحراسة', 'GUARD POST', (120, 28, 22), (230, 222, 200), 77), 'ssw_dcr': tx_sign2('غرفة المراقبة', 'CONTROL ROOM', (40, 50, 38), (222, 208, 140), 78),
       'ssw_dch': tx_sign2('غرفة الملابس', 'CHANGING ROOM', (226, 222, 210), (40, 40, 36), 79), 'ssw_dcm': tx_sign2('آمر الموقع', 'COMMANDER', (120, 28, 22), (230, 222, 200), 80),
       'ssw_drs': tx_sign2('استراحة الجنود', "MEN'S REST", (40, 50, 38), (222, 208, 140), 81),
       'ssw_pt1': tx_portrait(os.path.join(SP.ART2, 'real_bust_b.png'), (110, 0, 634, 705), (256, 512), 91),
       'ssw_pt2': tx_portrait(os.path.join(SP.ART2, 'real_bust_a.png'), (260, 60, 1010, 1060), (256, 512), 92),
       'ssw_pt3': tx_portrait(os.path.join(SP.ART2, 'real_mural_a.png'), (120, 0, 1180, 1380), (256, 512), 93),
       'ssw_pt4': tx_portrait(os.path.join(REAL2, 'tile_uniform.jpg'), (553, 122, 713, 440), (256, 512), 94, 0.25),
       'ssw_pt5': tx_portrait(os.path.join(REAL2, 'family_painting.jpeg'), (785, 180, 913, 350), (256, 512), 95, 0.3),
       'ssw_pt6': tx_portrait(os.path.join(REAL2, 'family_painting.jpeg'), (215, 158, 1519, 946), (512, 256), 96, 0.3),
       'ssw_emb': tx_painted(os.path.join(REAL2, 'border_brigade.jpg'), (67, 100, 1333, 1883), (256, 512), 97),
       'ssw_fgd': tx_frame((168, 124, 46), 98), 'ssw_fbk': tx_frame((30, 28, 26), 99), 'ssw_fwd': tx_frame((84, 52, 30), 100),
       'ssw_nb2': lambda: SP._pot(tx_notice(2)), 'ssw_nb3': lambda: SP._pot(tx_notice(3)), 'ssw_nb0': lambda: SP._pot(tx_notice(0)), 'ssw_nb1': lambda: SP._pot(tx_notice(1)), 'ssw_hlth': lambda: SP._pot(tx_health())}
MODELS = {'ssw_tbl_1': (_table, ['ssw_white', 'jr_steel']), 'ssw_bed_1': (_bed, ['jr_steel', 'ssw_matt', 'ssw_white']), 'ssw_drip_1': (_drip, ['jr_steel', 'ssw_white']), 'ssw_tray_1': (_traymdl, ['ssw_tray', 'ssw_vial']),
          'ssw_cab_1': (_cab, ['ssw_white', 'ssw_cab']), 'ssw_fak_1': (_fak, ['ssw_white', 'ssw_fakd']), 'ssw_cart_1': (_carton, ['ssw_cart']),
          'ssw_scr_1': (lambda: _plate(0.8, 0.4), ['ssw_cres', 'jr_dark']), 'ssw_sga_1': (lambda: _plate(1.1, 0.55), ['ssw_arms', 'jr_dark']), 'ssw_hlt_1': (lambda: _plate(0.5, 0.7, 0.004), ['ssw_hlth', 'jr_dark']),
          'ssw_chr_1': (_chair, ['jr_steel', 'ssw_wood']), 'ssw_mapt_1': (_maptable, ['ssw_map', 'jr_dark']), 'ssw_wmap_1': (lambda: _plate(2.6, 1.3, 0.03), ['ssw_map', 'jr_dark']), 'ssw_rad_1': (_radio, ['ssw_rdo', 'jr_dark']),
          'ssw_file_1': (_filing, ['ssw_filc', 'jr_steel']), 'ssw_wb_1': (_bench, ['ssw_wood', 'jr_steel']), 'ssw_seat_1': (_seat, ['ssw_wood', 'jr_steel']), 'ssw_tool_1': (lambda: _plate(1.8, 0.9, 0.02), ['ssw_tool', 'jr_dark']),
          'ssw_sack_1': (_sacks, ['ssw_sack', 'ssw_wood']), 'ssw_blk_1': (_blankets, ['ssw_blkt']), 'ssw_rug_1': (_rug, ['ssw_rug']), 'ssw_tyr_1': (_tyres, ['ssw_tyre']), 'ssw_scrn_1': (_screens, ['ssw_mon', 'jr_dark']),
          'ssw_rck_1': (_rack, ['ssw_rckf', 'ssw_rcks']), 'ssw_ctr_1': (lambda: _ctray(5.8), ['ssw_galv', 'ssw_cbl']), 'ssw_ctx_1': (lambda: _ctray(3.4), ['ssw_galv', 'ssw_cbl']),
          'ssw_prn_1': (_printer, ['ssw_prnt', 'jr_steel', 'ssw_white']), 'ssw_ssv_1': (lambda: _plate(0.6, 0.3), ['ssw_ssrv', 'jr_dark']), 'ssw_lan_1': (_lantern, ['ssw_lant', 'jr_dark']),
          'ssw_pip_1': (_pipes, ['ssw_pipe', 'jr_dark']), 'ssw_plk_1': (_planks, ['ssw_wood']), 'ssw_rub_1': (_rubble, ['ssw_rubb']), 'ssw_lnd_1': (_laundry, ['jr_steel', 'ssw_cl1', 'ssw_cl2', 'ssw_cl3']), 'ssw_lkr_1': (_locker, ['ssw_lkrf', 'jr_steel']), 'ssw_prt_1': (lambda: _partition(1.55), ['ssw_white', 'jr_steel']), 'ssw_prs_1': (lambda: _partition(0.85), ['ssw_white', 'jr_steel']),
          'ssw_prd_1': (lambda: _partition(0.6, 1.1, 0.35), ['ssw_white', 'jr_steel']), 'ssw_arm_1': (_arm, ['jr_steel']), 'ssw_rod_1': (_rod, ['jr_steel']), 'ssw_mat_1': (_mat, ['ssw_pray']), 'ssw_nb2_1': (lambda: _plate(1.3, 0.86, 0.03), ['ssw_nb2', 'jr_dark']), 'ssw_nb3_1': (lambda: _plate(1.3, 0.86, 0.03), ['ssw_nb3', 'jr_dark']), 'ssw_wms_1': (lambda: _plate(1.6, 0.8, 0.03), ['ssw_map', 'jr_dark']), 'ssw_shw_1': (_shower, ['ssw_white', 'jr_steel', 'ssw_wood']), 'ssw_trg_1': (_trough, ['jr_steel']), 'ssw_mir_1': (lambda: _plate(1.2, 0.6, 0.012), ['ssw_mirr', 'jr_dark']),
          'ssw_sgo_1': (lambda: _plate(0.9, 0.45), ['ssw_sops', 'jr_dark']), 'ssw_sgq_1': (lambda: _plate(0.9, 0.45), ['ssw_sqm', 'jr_dark']), 'ssw_sgf_1': (lambda: _plate(0.7, 0.35), ['ssw_sfuel', 'jr_dark']),
          'ssw_nb0_1': (lambda: _plate(1.3, 0.86, 0.03), ['ssw_nb0', 'jr_dark']), 'ssw_nb1_1': (lambda: _plate(1.3, 0.86, 0.03), ['ssw_nb1', 'jr_dark'])}
# job B 11-13: the dressing's merge sources (never placed alone, so no LOD rows): door signs, portraits in three frames and sizes, the painted emblem
for _k in ('dws', 'dfu', 'drd', 'dfd', 'dkt', 'dga', 'dgp', 'dcr', 'dch', 'dcm', 'drs'):
    MODELS['ssw_%s_1' % _k] = ((lambda: _plate(0.7, 0.35, 0.012)), ['ssw_' + _k, 'jr_dark'])
for _k, _t, _f, _w, _h in (('pa', 'ssw_pt1', 'ssw_fgd', 0.45, 0.6), ('pb', 'ssw_pt2', 'ssw_fwd', 0.42, 0.56), ('pc', 'ssw_pt3', 'ssw_fgd', 0.62, 0.8), ('pd', 'ssw_pt4', 'ssw_fgd', 0.5, 1.0),
                           ('pe', 'ssw_pt5', 'ssw_fbk', 0.45, 0.6), ('pf', 'ssw_pt6', 'ssw_fbk', 1.1, 0.66), ('pg', 'ssw_pt3', 'ssw_fwd', 0.42, 0.56), ('ph', 'ssw_pt1', 'ssw_fbk', 0.4, 0.53),
                           ('pi', 'ssw_pt5', 'ssw_fgd', 0.62, 0.8), ('pj', 'ssw_pt2', 'ssw_fgd', 0.62, 0.8)):
    MODELS['ssw_%s_1' % _k] = ((lambda w_=_w, h_=_h: _pframe(w_, h_)), [_t, _f])
MODELS['ssw_emb_1'] = ((lambda: _plate(1.0, 1.4, 0.004)), ['ssw_emb', 'jr_dark'])
MODELS['ssw_trn_1'] = (_transom, ['ssw_wood', 'jr_dark'])             # (judge Q23: the north armoury arch's transom)
ORIG = {'location2/LEVEL2': ['230_19_1', '231_03_1', '231_14_1', '239_01_1', '306_01_1', '231_17_1', '231_19_1', '261_17_1'],
        'location3/LEVEL4': ['205_36_1', '261_32_1', '261_06_1', '205_25_1', '260_03_1'], 'location3/LEVEL5': ['205_24_1', '231_16_1', 'ssw_lkr_1', '237_01_1', '231_02_1', '260_02_1', '261_18_1', '260_04_1'],
        'location1/level2': ['205_17_1'], 'location2/LEVEL6': ['231_15_1'], 'location1/level3': ['260_11_1', '230_03_1', '205_26_1'], 'location2/LEVEL5': ['333_01_1'], 'location3/level2': ['360_24_1']}


# ------------------------------------------------------------------------------------------------ merging: a room = one model
_SRC, _LV, ROOM_AT, _TEXSRC = {}, {}, {}, {}


def _level(rel):
    import prefab, os
    if rel not in _LV:
        _LV[rel] = prefab.Level(os.path.join(prefab.GAME, 'MISSIONS', *rel.split('/')))
    return _LV[rel]


def _source(md):
    """(RigidModel, texture names, level) of a piece: one of ours, or an original from the first level of ORIG that ships it"""
    import mefmesh
    if md in _SRC:
        return _SRC[md]
    if md in MODELS:
        fn, slots = MODELS[md]
        _SRC[md] = (mefmesh.RigidModel.from_mef(fn()), list(slots), None)
        return _SRC[md]
    for rel, names in ORIG.items():
        if md in names:
            lv = _level(rel)
            L = lv.find_vnam(md)
            nm, tx = L.entry(md)
            rm = mefmesh.RigidModel.from_mef(mefmesh.Mef.read(lv.find_resource('LOCAL:models/%s.mef' % nm, 'models')[1]))
            for t in tx:
                _TEXSRC.setdefault(t, lv)
            _SRC[md] = (rm, ['ssw_trol' if t == '205_22_1' else t for t in tx], lv)
            return _SRC[md]
    raise KeyError(md)


def src_texture(t):
    """texture loader for the Library: an original's own texture (used only when the level does not hold that name yet)"""
    lv = _TEXSRC[t]

    def fn():
        import igitex
        return igitex.decode(lv.find_resource('LOCAL:textures/%s.tex' % t, 'textures')[1])
    return fn


def merged(items):
    """[(model, x, y, z, yaw)] -> (mef, texture slots, origin): every piece's LOD 1 and collision in one mesh around the room's floor centre, one group per texture"""
    import mefmesh, navgen
    import biprefabs as BP
    solid = [p for p in items if not p[0].endswith('~')] or items       # (job B: dressing pieces '~' have no collision and leave the origin where it was)
    xs = [p[1] for p in solid]; ys = [p[2] for p in solid]
    o = (round(float(np.mean(xs)), 2), round(float(np.mean(ys)), 2), round(float(min(p[3] for p in solid)), 2))
    groups, glo = {}, []
    cm = [([], [], [], {}, [0]) for _ in (0, 1)]           # (each mesh on its own: mesh 1 is the originals' coarse hull, about 0.2 m larger; per-face kinds stay)
    for md, x, y, z, yaw in items:
        seen_only = md.endswith('~')
        md = md.rstrip('~')
        rm, tx, _ = _source(md)
        Rm = navgen.rot(0.0, 0.0, float(yaw))
        off = (np.array((x, y, z)) - o) * 4096.0
        for g in rm.groups:
            k = (tx[g.tex], g.flags)
            e = groups.setdefault(k, ([], [], [], [0]))
            e[0].append(g.pos @ Rm.T + off); e[1].append(g.uv); e[2].append(g.tris + e[3][0]); e[3][0] += len(g.pos)
        if rm.glows is not None and len(rm.glows):
            q = rm.glows.copy()
            q['pos'] = np.asarray(q['pos'], float) @ Rm.T + off
            glo.append(q)
        for k, (cP, cT, cM, kinds, nv) in enumerate(cm):
            if not rm.coll or seen_only:
                continue
            c = rm.coll[min(k, len(rm.coll) - 1)]
            idx = np.array([kinds.setdefault(tuple(q_.tolist()), len(kinds)) for q_ in c.mats], np.int64)
            cP.append(np.asarray(c.pos, float) @ Rm.T + off); cT.append(np.asarray(c.faces) + nv[0]); cM.append(idx[np.asarray(c.mat)]); nv[0] += len(c.pos)
    slots = sorted({k[0] for k in groups})
    out = []
    for (t, fl), (P, U, T_, n) in sorted(groups.items()):
        P_ = np.concatenate(P)
        out.append(mefmesh.Group(P_, np.concatenate(U), np.concatenate(T_), slots.index(t), flags=fl, nrm=np.tile((0.0, 0.0, 1.0), (len(P_), 1))))
    coll = [mefmesh.CollMesh(np.concatenate(cP), np.concatenate(cT), np.concatenate(cM), np.array(list(kinds), mefmesh.TAMC_DT)) for cP, cT, cM, kinds, nv in cm]
    r = mefmesh.RigidModel(out, coll, hsem=BP._hsem(), typ=0, glows=np.concatenate(glo) if glo else None)
    return r.to_mef(recompute_spheres=True, recompute_centres=True, rebuild_trees=True), slots, o


# ------------------------------------------------------------------------------------------------ rooms: (model, x, y, z, yaw)
def armoury():
    f = F_ARM
    P = [('231_14_1', 80.63, y, f + RACK_Z, E) for y in (106.3, 107.45, 108.6, 109.75)]
    P += [('261_32_1', 80.42, 111.45, f, E)]   # (S7 11-15, s5audit: the 2nd shelf at y 113.28 ran 0.59 m into the Large house's north wall; no room for it south of it: dropped)
    P += [('239_01_1', 75.42, 108.5, f, 0.0), ('239_01_1', 75.42, 109.85, f, 0.0), ('239_01_1', 75.42, 108.5, f + 0.5, 0.0), ('306_01_1', 75.56, 112.9, f, PI / 2)]
    P += [('231_03_1', 78.1, 107.6, f, 0.0), ('261_06_1', 78.1, 106.6, f, N), ('231_03_1', 79.4, 104.86, f, 0.0), ('261_06_1', 79.4, 105.9, f, S)]      # (S5 11-15: 261_06_1's sitter faces +y: each chair now faces its table)
    P += [('231_16_1', 79.9, 104.62, f + 0.85, PI), ('261_17_1', 79.1, 104.8, f + 0.85, 0.5), ('205_25_1', 78.8, 105.0, f + 0.85, PI / 2), ('205_24_1', 75.5, 111.3, f, 0.0)]
    return P


def clinic():
    f = F_MED
    P = [('ssw_bed_1', x, 248.35, f, 0.0) for x in (135.2, 137.8, 140.4)]
    P += [('ssw_drip_1', 136.5, 248.9, f, 0.0), ('ssw_drip_1', 139.1, 248.9, f, 0.0), ('205_24_1', 141.95, 248.9, f, 0.0)]
    P += [('ssw_tbl_1', 136.5, 244.75, f, 0.0), ('ssw_tray_1', 137.05, 244.8, f + 0.85, 0.3), ('ssw_cart_1', 135.85, 244.75, f + 0.30, 0.0), ('ssw_cart_1', 136.9, 244.75, f + 0.30, 0.1)]
    P += [('205_36_1', 138.65, 245.7, f, 2.2), ('ssw_cab_1', 134.0, 243.3, f, 0.0), ('ssw_cab_1', 143.05, 245.0, f, PI / 2)]   # (S5 11-15: y 246.4 stood in front of the east window, open y 245.7..246.5, 1.2..2.6 m up)
    P += [('230_19_1', 142.68, 247.95, f, W_), ('ssw_cart_1', 142.68, 247.6, f + 0.68, W_), ('ssw_cart_1', 142.68, 248.4, f + 0.68, W_), ('ssw_cart_1', 142.68, 247.95, f + 1.55, W_), ('261_06_1', 134.4, 245.4, f, E)]
    # (S7 11-15, propaudit look_1: the east wall's face is x 143.086 (render and collision, rays y 244-249.4) but the cabinet's back stood at 143.25 (0.16 m in
    #  the wall, INTO_WALL) and the shelf's east feet at 143.27 (0.19 m in, over the wall's footing: PART_FLOAT 0.16). Cabinet back 143.25 -> 143.05, shelf
    #  142.9 -> 142.68 (its 0.369 half-depth ends at 143.05) with its cartons: both 3.5 cm off the face)
    return P


# the buildings: x, y, z, yaw from the map. Their insides were read from the render meshes AND the child collision (work/sandstorm/world/rmesh.py, fl3.py): the plans of the shell alone miss the stairs.
# 405_03_1 (barracks): floors 0.2, 3.77, 7.18 (the top floor already has its kitchen and sofas); ground x -6.83..6.92, y -4.7..6.97, the stairs behind a wall along the south, their foot in the corner
# x 2.7..6.9; door north x -4.4..-3.4. First floor x -6.8..4.9, four bunks along the north wall, stairs up behind a wall at x 4.9; the whole south strip (y < -5.2) is the stairwell: a landing at 3.50 and the stair falling east from x -0.65, nothing stands there. (Wall faces: tools run work/sandstorm/world/rays.py.)
# 432_10_1 (shed): floor 0.1, x -1.75..1.95, y -3.36..3.35, door east y 1.2..3.0. 401_96_1 (garage): floor 0.3, bays either side of the wall x = -0.21, end walls y = +-7.83.
# 401_85_1: floors 0.2, 3.77; ground x -5.17..5.16, y -3.2..5.18, the stairs along the south behind a wall, foot at x 2.8..5.0; door north x -4.7..-3.4; first floor y down to -5.17.
BLD = {'pn': (93.677, 242.124, 7.808, 1.18), 'ps': (118.39, 82.413, 13.106, 0.0), 'kr': (176.623, 198.0, -7.409, PI), 's1': (52.041, 104.424, 0.319, 1.5708), 's2': (94.944, 91.519, 1.128, 1.5708), 's3': (110.328, 234.844, 2.539, 5.8832),
       's4': (143.687, 58.132, 0.115, 6.2632), 's5': (181.7, 34.429, 2.191, 0.976), 's6': (214.757, 168.249, -7.405, 2.016), 'g1': (201.702, 75.895, 0.505, 5.858), 'g2': (98.096, 308.97, 13.972, 0.0),
       'h1': (156.068, 72.078, 0.079, 4.6964), 'sc': (68.126, 272.636, 8.396, 5.8072), 'ad': (54.3713, 235.7943, 8.3799, 5.927182)}
F0, F1, FS, FG = 0.2, 3.77, 0.1, 0.3


def W(b, x, y, z=0.0, yaw=0.0):
    """a building's local frame -> world: (x, y, z, yaw)"""
    x0, y0, z0, g = BLD[b]
    c, s = math.cos(g), math.sin(g)
    return (x0 + c * x - s * y, y0 + s * x + c * y, z0 + z, g + yaw)


def local(b, items):
    return [(md,) + W(b, x, y, z, yaw) for md, x, y, z, yaw in items]


def boxes(md, spots, z, yaw=0.0):
    return [(md, x, y, z, yaw) for x, y in spots]


def shed(b, items):
    """the sheds' west wall stands at -1.75, not -1.9: written against -1.9, pulled in here; what hangs on it sits on its face"""
    out = []
    for md, x, y, z, yaw in items:
        if md in ('ssw_tool_1', 'ssw_wmap_1', 'ssw_sgf_1') and x < -1.7:
            x = -1.73
        elif x < -1.0:
            x += 0.15
        out.append((md, x, y, z, yaw))
    return local(b, out)


def office():
    """Kral's office: his table stands where the story needs it. Round it a carpet, a sofa, his files. The safe and the board had stood behind the stair wall, out of sight"""
    f = F0
    P = [('ssw_lkr_1', 170.12, y, F_KRAL, PI / 2) for y in (196.6, 197.65, 198.7)]
    P += [('237_01_1', 170.5, 204.0, F_KRAL, 0.0), ('205_24_1', 183.1, 194.95, F_KRAL, 0.0)]
    P += local('kr', [('230_03_1', -6.25, -2.7, f, PI),     # (S5 11-15: 230_03_1 opens to -x: turned so the front faces the room, back 3 cm off the west wall)
                       ('ssw_nb2_1', -0.8, -4.69, f + 1.2, 0.0), ('ssw_rug_1', 2.1, 4.0, f, 0.0), ('231_02_1', -6.15, 0.3, f, E),
                      ('230_19_1', -6.45, 4.3, f, E), ('205_25_1', -6.45, 3.8, f + 0.68, 0.0), ('205_25_1', -6.45, 4.1, f + 0.68, 0.0), ('205_25_1', -6.45, 4.4, f + 0.68, 0.0), ('205_25_1', -6.45, 4.3, f + 1.55, 0.0),
                      ('205_25_1', -6.45, 4.6, f + 1.55, 0.0), ('231_17_1', -6.45, 4.8, f + 0.68, 0.0), ('ssw_file_1', 6.5, 2.75, f, W_), ('ssw_file_1', 6.5, 3.25, f, W_), ('ssw_file_1', 6.5, 3.75, f, W_), ('261_18_1', 6.5, 3.25, f + 1.3, 0.0)])
    return P


def stores():
    """sorted by kind: arms to the west, stores and cartons by the north wall, flour to the east, fuel out of the way in the south-east"""
    f, g = F_STS, F_STN
    P = [('306_01_1', 147.7, 105.8, f, 0.0), ('306_01_1', 150.0, 105.8, f, 0.0), ('306_01_1', 147.7, 105.8, f + 1.5, 0.0), ('205_17_1', 161.4, 102.6, f, 0.0), ('205_17_1', 158.7, 102.6, f, 0.0),
         ('260_03_1', 145.6, 101.0, f, 0.0), ('260_03_1', 145.6, 100.0, f, 0.0), ('230_19_1', 157.6, 106.15, f, N), ('230_19_1', 161.3, 106.15, f, N), ('230_19_1', 162.9, 106.15, f, N),
         ('231_17_1', 157.3, 106.15, f + 0.68, 0.2), ('231_17_1', 157.9, 106.1, f + 0.68, 1.1), ('231_19_1', 161.2, 106.15, f + 0.68, 0.0), ('231_17_1', 161.0, 106.15, f + 1.55, 0.7),
         ('231_17_1', 162.7, 106.15, f + 1.55, 0.3), ('239_01_1', 162.9, 106.15, f + 0.68, PI / 2)]
    P += boxes('239_01_1', ((145.0, 95.4), (146.0, 95.4), (147.0, 95.4)), f) + boxes('239_01_1', ((145.0, 95.4), (146.0, 95.4)), f + 0.5) + boxes('306_01_1', ((145.6, 92.4),), f, PI / 2)
    P += boxes('ssw_sack_1', ((164.75, 106.47), (167.2, 106.47), (168.6, 106.47), (164.75, 105.44), (167.2, 105.44)), f) + boxes('ssw_sack_1', ((164.75, 106.47), (167.2, 106.47)), f + 0.64, 0.1)
    # (S7 11-15, propaudit look_1 PART_FLOAT 0.18: the north wall is not square, its face runs y 107.204 at x 164.1 to 107.004 at x 169.25 (rays); the back
    #  row (pallets 1.0 deep, y +-0.5) at 106.75 put the pallets at 167.2 and 168.6 0.17 / 0.25 m into it. Back row 106.75 -> 106.47: the east end of the
    #  168.6 pallet and the turned top pallet's corner (+0.557 at yaw 0.1) stay 3.5 cm off the face; front row 105.5 -> 105.44 so the rows do not meet)
    P += boxes('333_01_1', ((160.6, 88.35), (161.5, 88.35), (162.4, 88.35), (161.0, 89.25), (161.9, 89.25)), f)
    P += [('230_19_1', 154.0, 106.75, f, N), ('230_19_1', 155.6, 106.75, f, N), ('ssw_blk_1', 153.7, 106.75, f + 0.68, 0.0), ('ssw_blk_1', 154.4, 106.75, f + 0.68, 0.0), ('ssw_blk_1', 155.3, 106.75, f + 0.68, 0.0), ('ssw_blk_1', 155.9, 106.75, f + 1.55, 0.0)]
    P += [('306_01_1', 150.4, 229.2, g, 0.0), ('306_01_1', 153.1, 229.2, g, 0.0), ('205_17_1', 161.6, 226.0, g, 0.0), ('205_17_1', 158.9, 226.0, g, 0.0), ('260_03_1', 164.6, 226.4, g, 0.0),
          ('260_03_1', 164.6, 225.4, g, 0.0), ('239_01_1', 150.4, 229.2, g + 1.5, PI / 2)]
    # (S7 11-16, rig probe rc7s25 stand 'stn' (156.0, 222.0): the two barrels never seen from 10.6-11.2 m. Rays on look_1 (mesh 0): the store's west
    #  wall is a 0.20 m partition, faces x 149.04 / 149.24, straight from y 223.0 (door jamb; doorway y 218-222.5) to the north wall y 229.82. The barrels
    #  at x 147.6 / 148.5 (boxes x 147.2-148.9, r 0.40) stood west of it, in the next room (sector 434_18_1), 0.14 m behind its back face. Moved into the
    #  room along the west wall south of the 150.4 pallet: x 149.67 = box 149.27, 3.3 cm off the face; y 228.20 / 227.38 = 8.6 cm off the pallet's front
    #  228.667, 6 cm apart, 4 m clear of the doorway, 1.7 m off the graph walk x 151.8; free lines to centre and top from 6 room stands incl. 'stn')
    P += boxes('ssw_sack_1', ((158.6, 229.05), (160.75, 229.05), (162.15, 229.05)), g) + boxes('333_01_1', ((149.67, 228.2), (149.67, 227.38)), g)
    return P


def ops():
    """pers n, ground: the operations room. The men and the alarm button keep the west half"""
    f = F0
    return local('pn', [('ssw_mapt_1', 2.8, 1.4, f, 0.0), ('ssw_wms_1', 6.9, 1.0, f + 1.15, W_), ('ssw_chr_1', 2.0, 0.25, f, S), ('ssw_chr_1', 3.5, 0.25, f, S), ('205_25_1', 3.6, 1.7, f + 0.9, PI / 2), ('261_17_1', 1.8, 1.0, f + 0.9, 0.0),
                        ('231_03_1', 0.6, 6.5, f, 0.0), ('231_03_1', 2.2, 6.5, f, 0.0), ('ssw_rad_1', 0.3, 6.55, f + 0.85, S), ('ssw_rad_1', 1.0, 6.55, f + 0.85, S), ('ssw_rad_1', 2.5, 6.55, f + 0.85, S), ('205_25_1', 1.8, 6.4, f + 0.85, 0.0),
                        ('261_18_1', 1.55, 6.65, f + 0.85, 0.0), ('ssw_chr_1', 0.6, 5.75, f, S), ('ssw_chr_1', 2.2, 5.75, f, S), ('ssw_file_1', 3.75, 6.65, f, S), ('ssw_file_1', 4.25, 6.65, f, S), ('ssw_file_1', 4.75, 6.65, f, S), ('205_24_1', 5.5, 6.6, f, 0.0),
                        ('ssw_nb1_1', -6.81, 3.2, f + 1.15, E), ('ssw_sgo_1', -2.0, 6.95, f + 1.9, S)])


def quartermaster():
    """pers s, ground: the quartermaster: two rows of shelves sorted by kind behind an issue counter, the west half open for the queue"""
    f = F0
    P = []
    for k, y in enumerate((-3.1, -1.6, -0.1, 1.4)):
        P += [('230_19_1', 1.7, y, f, E), ('230_19_1', 4.3, y, f, E)]
        P += [('231_17_1', 1.7, y - 0.4, f + 0.68, 0.2 * k), ('231_17_1', 1.7, y + 0.35, f + 0.68, 0.5), ('231_17_1', 1.7, y - 0.3, f + 1.55, 0.1), ('231_17_1', 1.7, y + 0.3, f + 1.55, 0.4)]
        P += [('ssw_blk_1', 4.3, y - 0.36, f + 0.68, PI / 2), ('ssw_blk_1', 4.3, y + 0.36, f + 0.68, PI / 2), ('231_19_1', 4.3, y - 0.3, f + 1.55, 0.0), ('231_19_1', 4.3, y + 0.05, f + 1.55, 0.0), ('231_19_1', 4.3, y + 0.4, f + 1.55, 0.0)]
    P += [('231_03_1', 1.4, 3.3, f, 0.0), ('231_03_1', 3.0, 3.3, f, 0.0), ('205_25_1', 2.9, 3.3, f + 0.85, PI / 2), ('231_16_1', 3.5, 3.5, f + 0.85, PI), ('261_17_1', 3.2, 3.05, f + 0.85, 0.4), ('ssw_chr_1', 2.4, 2.55, f, S)]
    P += [('ssw_sgq_1', 1.8, 6.95, f + 1.7, S), ('ssw_nb3_1', 4.4, 6.95, f + 1.15, S), ('306_01_1', 6.2, 5.6, f, PI / 2), ('306_01_1', 6.2, 3.3, f, PI / 2)]
    return local('ps', P)


def dorm(b, table=True):
    """a barracks first floor: the bunks stand, the men's lockers go along the west wall, a table to sit at"""
    f = F1
    P = boxes('ssw_lkr_1', ((-6.38, -1.6), (-6.38, -0.55), (-6.38, 0.5), (-6.38, 1.55)), f, W_)
    if table:
        P += [('231_03_1', -1.2, 0.6, f, 0.0), ('ssw_chr_1', -1.6, -0.2, f, S), ('ssw_chr_1', -0.7, -0.2, f, S), ('ssw_chr_1', -1.2, 1.4, f, 0.0), ('205_26_1', -1.4, 0.6, f + 0.85, 0.3), ('261_17_1', -0.8, 0.45, f + 0.85, 0.0), ('261_17_1', -1.75, 0.8, f + 0.85, 1.0), ('205_24_1', 4.3, 3.4, f, 0.0)]
    return local(b, P)


def toolshed():
    f = FS
    return shed('s1', [('ssw_wb_1', -1.5, 0.3, f, E), ('ssw_tool_1', -1.84, 0.3, f + 1.05, E), ('230_19_1', -0.35, -2.95, f, N), ('231_17_1', -0.7, -2.95, f + 0.68, 0.3), ('231_19_1', 0.0, -2.95, f + 0.68, 0.0), ('260_04_1', -0.4, -2.95, f + 1.55, 0.0),
                        ('333_01_1', 1.35, -2.9, f, 0.0), ('360_24_1', 1.6, -1.1, f, W_), ('360_24_1', 1.6, -0.4, f, W_)])


def fuelstore():
    f = FS
    return shed('s2', boxes('333_01_1', ((-1.4, -2.8), (-1.4, -1.95), (-1.4, -1.1), (-1.4, -0.25), (-0.4, -2.8), (-0.4, -1.95)), f) + boxes('360_24_1', ((-1.55, 0.75), (-1.55, 1.5), (-1.55, 2.25)), f, E)
                 + [('ssw_sgf_1', -1.84, 0.4, f + 1.7, E), ('260_04_1', 1.4, -2.9, f, 0.0), ('260_04_1', 1.4, -2.9, f + 0.4, 0.2)])


def radiohut():
    f = FS
    return shed('s3', [('231_03_1', -1.42, -0.85, f, E), ('231_03_1', -1.42, 0.7, f, E), ('ssw_rad_1', -1.5, -1.1, f + 0.85, E), ('ssw_rad_1', -1.5, -0.4, f + 0.85, E), ('ssw_rad_1', -1.5, 0.9, f + 0.85, E), ('205_25_1', -1.3, 0.3, f + 0.85, 0.0), ('261_17_1', -1.2, -0.6, f + 0.85, 0.0),
                        ('ssw_chr_1', -0.55, -0.85, f, E), ('ssw_chr_1', -0.55, 0.7, f, E), ('ssw_wms_1', -1.84, -0.6, f + 1.2, E), ('230_19_1', -0.8, 2.9, f, S), ('231_17_1', -1.1, 2.9, f + 0.68, 0.0), ('231_17_1', -0.5, 2.9, f + 0.68, 0.0), ('ssw_rad_1', -0.8, 2.9, f + 1.55, S),
                        ('ssw_file_1', 0.3, -3.05, f, N), ('ssw_file_1', 0.8, -3.05, f, N), ('205_24_1', 1.45, -2.9, f, 0.0)])


def resthut():
    f = FS
    return shed('s4', [('260_02_1', -1.25, -1.8, f, E), ('260_02_1', -1.25, 0.95, f, E), ('231_03_1', 1.4, -1.75, f, W_), ('ssw_chr_1', 0.6, -2.1, f, W_), ('ssw_chr_1', 0.6, -1.3, f, W_), ('205_26_1', 1.35, -1.9, f + 0.85, 0.2),
                        ('261_17_1', 1.5, -1.3, f + 0.85, 0.0), ('261_18_1', 1.55, -2.3, f + 0.85, 0.0), ('ssw_lkr_1', 1.3, -2.9, f, S), ('ssw_nb2_1', -0.3, -3.36, f + 1.15, 0.0)])


def foodstore():
    f = FS
    return shed('s5', boxes('ssw_sack_1', ((-1.15, -2.7), (-1.15, -1.3), (-1.15, 0.1)), f, PI / 2) + boxes('ssw_sack_1', ((-1.15, -2.7),), f + 0.64, PI / 2 + 0.1)
                 + [('230_19_1', 1.45, -1.5, f, W_), ('231_17_1', 1.45, -1.8, f + 0.68, 0.2), ('231_17_1', 1.45, -1.2, f + 0.68, 1.0), ('231_19_1', 1.45, -1.5, f + 1.55, 0.0), ('231_19_1', 1.45, -1.0, f + 1.55, 0.0), ('231_17_1', 1.45, -2.0, f + 1.55, 0.0), ('260_04_1', 1.4, -2.85, f, 0.0)])


def kitchenhut():
    f = FS
    return shed('s6', [('ssw_tbl_1', -1.4, -0.2, f, PI / 2), ('ssw_tray_1', -1.4, -0.6, f + 0.85, PI / 2), ('261_18_1', -1.5, 0.3, f + 0.85, 0.0), ('261_17_1', -1.25, 0.1, f + 0.85, 0.0), ('261_17_1', -1.5, 0.05, f + 0.85, 1.0),
                        ('ssw_sack_1', -1.15, -2.7, f, PI / 2), ('333_01_1', 1.4, -2.9, f, 0.0), ('333_01_1', 0.5, -2.9, f, 0.0), ('230_19_1', 1.45, -1.1, f, W_), ('231_17_1', 1.45, -1.4, f + 0.68, 0.2), ('231_19_1', 1.45, -0.8, f + 0.68, 0.0), ('231_19_1', 1.45, -1.2, f + 1.55, 0.0),
                        ('205_24_1', -1.5, 2.9, f, 0.0)])


def garage(b, s):
    """the free bay: a workbench on the middle wall, tyres, drums and the spares against the end walls. s = the side of the free bay"""
    f = FG
    y_, w_ = (E if s > 0 else W_), -0.21 + s * 0.02            # (the middle wall's face)
    P = [('ssw_wb_1', w_ + s * 0.36, 4.1, f, y_), ('ssw_tool_1', w_, 4.1, f + 1.05, y_), ('231_19_1', w_ + s * 0.4, 3.3, f + 0.9, 0.0), ('260_04_1', w_ + s * 0.36, 4.7, f + 0.9, 0.0),
         ('ssw_tyr_1', s * 1.0, 7.3, f, 0.0), ('ssw_tyr_1', s * 2.0, 7.3, f, 0.5), ('ssw_tyr_1', s * 1.0, 6.3, f, 1.0),
         ('333_01_1', s * 5.4, 7.35, f, 0.0), ('333_01_1', s * 6.3, 7.35, f, 0.0), ('333_01_1', s * 7.2, 7.35, f, 0.0), ('360_24_1', s * 6.6, 6.7, f, S),
         ('230_19_1', s * 3.7, 7.4, f, N), ('231_17_1', s * 3.3, 7.4, f + 0.68, 0.2), ('260_04_1', s * 4.0, 7.4, f + 0.68, PI / 2), ('231_19_1', s * 3.7, 7.4, f + 1.55, 0.0),
         ('306_01_1', s * 1.4, -7.1, f, 0.0), ('260_03_1', s * 3.0, -7.3, f, 0.0), ('260_03_1', s * 3.8, -7.3, f, 0.0)]
    # (S7 11-15, propaudit look_1 FLOAT 0.46: the green box 260_04_1 is 0.65 x 0.85 and stood with its 0.85 across the shelf, whose board is 0.74 deep drawn and
    #  0.60 in collision (230_19_1 board top 0.626, y -0.30..0.30): all four corners hung past it. Turned PI / 2 its 0.85 runs along the shelf (x 3.575..4.425 of
    #  the shelf's 2.945..4.455) and its 0.65 sits inside the drawn board; the small box 231_17_1 (0.236 m half-span at yaw 0.2) 3.4 -> 3.3 so the two do not meet)
    return local(b, P)


def changing():
    """small house, ground: the men change here on their way up to the wash room"""
    f = F0
    return local('h1', boxes('ssw_lkr_1', ((4.74, 0.2), (4.74, 1.25), (4.74, 2.3), (4.74, 3.35)), f, E) + [('ssw_seat_1', 2.9, 1.7, f, PI / 2), ('ssw_seat_1', 0.6, 1.7, f, PI / 2), ('ssw_nb3_1', 1.0, 5.16, f + 1.15, S), ('231_17_1', 2.9, 1.2, f + 0.46, 0.3), ('205_24_1', -0.6, 4.8, f, 0.0)])


def guardroom():
    """security, ground: the guards off shift: table, lockers, their rifles in the rack"""
    f = F0
    return local('sc', [('231_03_1', 0.6, 2.2, f, 0.0), ('ssw_chr_1', 0.2, 1.4, f, S), ('ssw_chr_1', 1.1, 1.4, f, S), ('ssw_chr_1', 0.6, 3.0, f, 0.0), ('205_26_1', 0.4, 2.2, f + 0.85, 0.5), ('261_17_1', 1.0, 2.0, f + 0.85, 0.0), ('261_18_1', 0.15, 2.4, f + 0.85, 0.0),
                        ('231_14_1', 4.8, 1.8, f + RACK_Z, E), ('ssw_lkr_1', -4.75, -2.2, f, W_), ('ssw_lkr_1', -4.75, -1.15, f, W_), ('ssw_lkr_1', -4.75, -0.1, f, W_), ('ssw_nb0_1', -1.0, -3.18, f + 1.15, 0.0), ('205_24_1', 4.75, 4.75, f, 0.0)])


def monitors():
    """security, first floor: the camera room: the screens beside the control computer, the log files by the door"""
    f = F1
    return local('sc', [('231_03_1', -4.6, -1.0, f, E), ('231_03_1', -4.6, -2.6, f, E), ('ssw_scrn_1', -4.75, -1.0, f + 0.85, E), ('ssw_scrn_1', -4.75, -2.6, f + 0.85, E), ('205_25_1', -4.4, -3.2, f + 0.85, 0.0), ('261_17_1', -4.3, -1.9, f + 0.85, 0.0), ('ssw_chr_1', -3.7, -1.8, f, E),
                        ('ssw_file_1', 0.2, 4.8, f, S), ('ssw_file_1', 0.7, 4.8, f, S), ('ssw_nb2_1', 1.0, -5.15, f + 1.15, 0.0), ('205_24_1', 4.75, -3.25, f, 0.0)])
    # (S7 11-15, propaudit look_1 FLOAT 0.11 / 3.57: this first floor ends at local y -3.6, the strip south of it is the open stairwell (ground floor 8.60 and
    #  the stair 9.2-9.8 under it, two 0.1 m ledges at x 3.0 and 5.0). The plant (+-0.25 m) at y -4.7 stood over the hole: y -4.7 -> -3.25, on the floor in
    #  the same corner, 0.1 m short of the floor's edge and 0.14 m off the east wall)


def decor():
    """job B 11-13: room -> the wall dressing added to it (seen only)"""
    fs, f0, f1, fg = FS, F0, F1, FG
    D = {'sh1': local('s1', [('ssw_dws_1~', 0.9, 3.35, fs + 1.85, S), ('ssw_pg_1~', -0.55, 3.35, fs + 1.3, S)]),
         'sh2': local('s2', [('ssw_dfu_1~', 0.3, 3.35, fs + 1.8, S), ('ssw_nb0_1~', 0.4, -3.36, fs + 1.25, N)]),
         'sh3': local('s3', [('ssw_drd_1~', 0.9, 3.35, fs + 1.9, S), ('ssw_pa_1~', -1.0, -3.36, fs + 1.4, N)]),
         'sh4': local('s4', [('ssw_drs_1~', 0.9, 3.35, fs + 1.9, S), ('ssw_pe_1~', -0.45, 3.35, fs + 1.3, S), ('ssw_mat_1~', -0.75, 2.55, fs, PI / 2)]),
         'sh5': local('s5', [('ssw_dfd_1~', 0.3, 3.35, fs + 1.8, S), ('ssw_nb3_1~', 0.2, -3.36, fs + 1.25, N)]),
         'sh6': local('s6', [('ssw_dkt_1~', 0.2, 3.35, fs + 1.85, S), ('ssw_pb_1~', -0.3, -3.36, fs + 1.4, N)]),
         'grd': local('sc', [('ssw_emb_1~', 1.2, 5.18, f0 + 0.85, S), ('ssw_dgp_1~', -1.0, 5.18, f0 + 2.0, S), ('ssw_pe_1~', 5.16, -1.0, f0 + 1.4, W_)]),
         'mon': local('sc', [('ssw_dcr_1~', -1.5, 5.18, f1 + 2.0, S), ('ssw_ph_1~', -3.2, 5.18, f1 + 1.4, S)]),
         'chg': local('h1', [('ssw_dch_1~', -0.75, 5.16, f0 + 2.0, S), ('ssw_pb_1~', -5.17, 1.5, f0 + 1.4, E)]),
         'ops': local('pn', [('ssw_pc_1~', 6.92, 4.0, f0 + 1.3, W_)]),
         'qm': local('ps', [('ssw_pi_1~', -6.83, 1.5, f0 + 1.3, E), ('ssw_nb2_1~', -6.83, -1.5, f0 + 1.15, E)]),
         'dpn': local('pn', [('ssw_pa_1~', -6.8, 1.05, f1 + 2.0, E)]),
         'dps': local('ps', [('ssw_pe_1~', -6.8, 1.05, f1 + 2.0, E)]),
         'dkr': local('kr', [('ssw_pb_1~', -6.8, 1.05, f1 + 2.0, E)]),
         'off': local('kr', [('ssw_pd_1~', 2.1, 6.97, f0 + 1.1, S), ('ssw_dcm_1~', 0.4, 6.97, f0 + 2.0, S), ('ssw_pf_1~', 4.6, 6.97, f0 + 1.45, S)]),
         'ga1': garage_decor('g1', 1), 'ga2': garage_decor('g2', -1),
         'anl': [('ssw_pj_1~', 141.78, 295.0, 17.5 + 1.3, W_), ('ssw_pe_1~', 136.43, 295.2, 20.7 + 1.4, E)],
         'arm': [('ssw_trn_1~', 77.935, 113.6, F_ARM, 0.0)]}      # (judge Q23: the transom over ss-loot's north leaves)
    return D


def garage_decor(b, s):
    """job B: the free bay's middle wall (chain-link: what is wired to it, no paintings): the motor pool's sign, the vehicle log board"""
    f = FG
    y_, w_ = (E if s > 0 else W_), -0.21 + s * 0.02
    return local(b, [('ssw_dga_1~', w_, 1.4, f + 2.0, y_), ('ssw_nb2_1~', w_, -1.0, f + 1.15, y_)])


def _dressed(nm, fn):
    return lambda: fn() + DECOR_FN().get(nm, [])


_DEC = {}


def DECOR_FN():
    if not _DEC:
        _DEC.update(decor())
    return _DEC


ROOMS = [('arm', armoury), ('cli', clinic), ('off', office), ('sts', lambda: [p for p in stores() if p[2] < 150.0]), ('stn', lambda: [p for p in stores() if p[2] >= 150.0]),
         ('ops', ops), ('qm', quartermaster), ('dpn', lambda: dorm('pn')), ('dps', lambda: dorm('ps', False)), ('dkr', lambda: dorm('kr')),
         ('sh1', toolshed), ('sh2', fuelstore), ('sh3', radiohut), ('sh4', resthut), ('sh5', foodstore), ('sh6', kitchenhut), ('ga1', lambda: garage('g1', 1)), ('ga2', lambda: garage('g2', -1)),
         ('chg', changing), ('grd', guardroom), ('mon', monitors)]
ROOMS = [(nm_, _dressed(nm_, fn_)) for nm_, fn_ in ROOMS]          # (job B: each room's wall dressing, seen only)
# baked level of a room's furniture where the default (78) would stand out: the dim rooms of the barracks and small houses
def kral_corner():
    """judge R13: Kral's working corner by the stair wall. A LATE piece (inside ukr) so the graph and the men stay as they were"""
    f = F0
    return local('kr', [('231_03_1', -2.6, -4.25, f, 0.0), ('ssw_rad_1', -3.0, -4.3, f + 0.85, 0.0), ('205_25_1', -2.2, -4.2, f + 0.85, PI / 2), ('231_16_1', -3.25, -4.35, f + 0.85, 0.0), ('ssw_chr_1', -2.6, -3.45, f, N),      # (S5 11-15: chair faces its table)
                       
                        ('ssw_wms_1', 1.6, -4.68, f + 1.2, 0.0), ('231_17_1', 4.3, -4.35, f, 0.2), ('231_17_1', 4.8, -4.3, f, 1.0), ('231_17_1', 4.3, -4.35, f + 0.4, 0.3)])
    # (S7 11-15, propaudit look_1 PART_FLOAT 0.39: the top box (0.4 m cube) sat across the gap of the two under it at x 4.5, yaw 0.5, one corner over the floor
    #  0.39 m down. Now on the first box (4.3, -4.35), turned 0.1 off it (0.02 m overhang per side); the second box 4.75 -> 4.8 so the two lower boxes,
    #  0.217 + 0.281 m half-spans toward each other at 0.45 m apart, no longer cut into each other)


def dorm2(b, by=-1.5):
    """the rest of a barracks first floor. The south strip is the stairwell, so: kit shelves on the west wall either side of the lockers, foot lockers under the bunks, prayer mats (no collision) by the stair wall, the orders on it"""
    f = F1
    P = boxes('260_04_1', ((-4.86, 5.5), (-2.6, 5.5), (-0.25, 5.5), (2.12, 5.5)), f, PI / 2)
    P += [('230_19_1', -6.42, -3.0, f, E), ('230_19_1', -6.42, 2.9, f, E), ('ssw_blk_1', -6.42, -3.4, f + 0.68, PI / 2), ('ssw_blk_1', -6.42, -2.7, f + 0.68, PI / 2), ('231_17_1', -6.42, -3.0, f + 1.55, 0.2), ('231_17_1', -6.42, 2.6, f + 0.68, 0.4), ('231_17_1', -6.42, 3.2, f + 0.68, 0.0), ('ssw_blk_1', -6.42, 2.9, f + 1.55, PI / 2)]
    P += boxes('ssw_mat_1', ((2.2, 2.3), (3.05, 2.3), (3.9, 2.3)), f, 0.0)
    P += [('ssw_nb1_1' if b != 'ps' else 'ssw_nb3_1', 4.88, by, f + 1.15, W_)]
    if b == 'pn':                                           # (judge E15: every stone room had the same kit: the radio corner on the south wall)
        # (S5 + S7 11-15: the corner stood over the stairwell strip, y < -5.2, table 1.7 m and chair 2.1 m over the stair: now at the stairwell's edge (the
        #  floor reaches y -5.3 here; there is NO wall at -5.2, see the map below), the same spacing as before (table edge 0.04 m short of -5.2, chair 0.78 m
        #  off the table), chair facing it)
        P += [('ssw_tbl_1', 2.0, -4.74, f, 0.0), ('ssw_rad_1', 1.45, -4.88, f + 0.87, 0.0), ('231_16_1', 2.75, -4.91, f + 0.87, 0.0), ('ssw_chr_1', 1.5, -3.96, f, N),
              ('ssw_wms_1', 4.90, -4.4, f + 1.3, W_), ('ssw_file_1', 3.75, -4.91, f, 0.0)]
        # (S5 11-15, propaudit look_1 NO_WALL 1.56: there is no wall at y -5.2, the strip is the open stairwell and the south wall's face is 1.56 m further,
        #  y -6.747. The map goes on the nearest real wall: the room's east wall, face x 4.914 from y -3.2 to -6.4 at its height (rays, render = collision),
        #  back 1.4 cm off it, facing the room (W_), centred y -4.4 (-5.2..-3.6: clear of the board at y -2.4 +- 0.65 and 0.9 m east of the file cabinet))
    elif b == 'ps':                                         # (judge E15: a washing line along the south wall)
        P += [('ssw_lnd_1', 0.5, -6.74, f + 2.15, 0.0)]
    return local(b, P)


def servers():
    """judge R05: 'hack their server' showed shelves of cartons. Eight server racks (not 261_05_1: that one draws as lying gas bottles) on the shelves' spots, the shelves and their cartons go (ssworld.REMOVE_LATE)"""
    f = 5.29
    g = 1.21                                               # (the shelves' yaw: two racks side by side on each shelf's 1.5 m, fronts toward the room either way)
    c, s = math.cos(g), math.sin(g)
    out = []
    for x, y in ((54.46, 237.79), (53.32, 234.69), (52.98, 238.34), (51.84, 235.24)):
        for dx in ((-0.33,) if (x, y) == (52.98, 238.34) else (-0.33, 0.33)):     # (one rack fewer by the door 3664)
            out.append(('ssw_rck_1', x + c * dx, y + s * dx, f, g))
    fl = -3.09                                              # (judge E01 11-12: the cheapest room in the mission: cable trays under the ceiling to the racks and the desk, a printer at the aisle's end, a door plate in the corridor)
    out += local('ad', [('ssw_ctr_1', -2.6, 0.0, fl + 2.6, 0.0), ('ssw_ctx_1', -1.35, 0.15, fl + 2.5, PI / 2), ('ssw_prn_1', 0.05, 0.25, fl, PI / 2),
                        ('ssw_ssv_1', -1.45, 2.75, fl + 1.5, 0.0)])
    return out


def washroom():
    """small house, first floor: the wash room's showers, trough, mirrors, towels; the stairwell's corner stays clear"""
    f = F1
    P = boxes('ssw_shw_1', ((5.14, -2.4), (5.14, -1.35), (5.14, -0.3), (5.14, 0.75)), f, W_)
    P += [('ssw_trg_1', -4.9, -0.5, f, E), ('ssw_mir_1', -5.15, -0.5, f + 1.3, E), ('ssw_mir_1', -5.15, 2.4, f + 1.3, E), ('230_19_1', -2.6, 4.75, f, S), ('ssw_blk_1', -2.9, 4.75, f + 0.68, 0.0), ('ssw_blk_1', -2.3, 4.75, f + 0.68, 0.1), ('ssw_blk_1', -2.6, 4.75, f + 1.55, 0.0),
          ('ssw_seat_1', 2.8, -0.8, f, PI / 2), ('205_24_1', 4.75, 2.6, f, 0.0), ('231_17_1', 2.8, -1.2, f + 0.46, 0.3),
          ('ssw_prs_1', -4.72, 3.6, f, PI / 2), ('ssw_prt_1', -3.75, 2.3, f, 0.0),   # (S5 11-15, s5audit: the stall wall at (-3.75, 4.38) stood 0.22 m in front of the base map's toilet 3064, a 0.8 m closet: dropped)
          ('ssw_prd_1', -1.55, 4.88, f, 0.0), ('ssw_prd_1', -0.25, 4.88, f, 0.0), ('ssw_prd_1', 1.05, 4.88, f, 0.0)]
    return local('h1', P)


def corridor(f):
    """admin north: the long corridor between the (fake) office doors: a bench and the board between the doors, files, a plant, the fire bucket"""
    w, e = 136.43, 141.78
    return [('ssw_seat_1', w + 0.2, 288.85, f, PI / 2), ('ssw_nb0_1', w + 0.02, 288.85, f + 1.15, E), ('ssw_file_1', e - 0.32, 287.6, f, W_), ('ssw_file_1', e - 0.32, 288.1, f, W_), ('ssw_file_1', e - 0.32, 288.6, f, W_),
            ('205_24_1', e - 0.3, 290.4, f, 0.0), ('ssw_seat_1', w + 0.2, 296.9, f, PI / 2), ('ssw_nb1_1', w + 0.02, 296.9, f + 1.15, E), ('205_24_1', w + 0.3, 283.0, f, 0.0)]


def corridor_top(f):
    """judge R13: the top corridor read as a copy of the one below: here a long carpet runner, a row of waiting chairs, the plant"""
    w, e = 136.43, 141.78
    return [('ssw_rug_1', 139.1, 287.0, f, PI / 2), ('ssw_rug_1', 139.1, 296.0, f, PI / 2), ('ssw_chr_1', w + 0.35, 289.0, f, W_), ('ssw_chr_1', w + 0.35, 289.7, f, W_), ('ssw_chr_1', w + 0.35, 290.4, f, W_),
            ('ssw_file_1', e - 0.36, 295.5, f, W_), ('ssw_file_1', e - 0.36, 296.0, f, W_), ('ssw_nb3_1', e - 0.02, 289.0, f + 1.15, W_), ('205_24_1', w + 0.3, 291.3, f, 0.0)]
    # (S5 11-15, propaudit look_1 FRONT_TO_WALL 0.13: ssw_chr_1's sitter faces -y (backrest at +y 0.2); at yaw E its -y pointed west, the sitter's knees 0.13 m from
    #  the west wall. Yaw E -> W_: backrest to the wall (0.13 m off it), the sitters face the corridor)


def sewer2():
    """judge E13 11-12: five stands showed the same empty brick tube and 'sewer bunks' had no bunks. A worker's corner on the bunks' east walk (cot, blanket, ammo chest,
    green boxes, a lantern), mains along the walls, boards afloat, rubble, lanterns at the turn, the lobby and the junction. Walk floor -19.84, walls 2.85-3.0 m off the axis"""
    z = -19.84
    return [('ssw_bed_1', 86.45, 116.2, z, 0.0), ('ssw_blk_1', 86.45, 115.55, z + 0.60, 0.1),      # (S7 11-15: the blanket on the mattress top 0.60, was 0.21 m inside it)
            ('ssw_cart_1', 80.0, 134.30, F_SEWWALK, 0.0),                                   # (S6 11-15: the medipack's carton on the north walk, 0.1 m off the wall; was in the channel water)
            ('239_01_1', 86.7, 113.8, z, 0.0), ('260_04_1', 86.55, 118.25, z, 0.0), ('260_04_1', 86.55, 118.25, z + 0.4, 0.2),
            ('ssw_lan_1', 87.03, 117.3, -18.2, W_), ('ssw_rub_1', 81.95, 121.2, z, 0.6),
            ('ssw_pip_1', 81.37, 106.7, -18.0, E), ('ssw_pip_1', 81.37, 112.7, -18.0, E), ('ssw_pip_1', 81.37, 122.7, -18.0, E),
            ('ssw_plk_1', 83.9, 124.5, -20.28, 0.4), ('ssw_plk_1', 83.6, 108.0, -20.28, 2.0),
            ('ssw_lan_1', 81.37, 126.0, -18.2, E),
            ('ssw_lan_1', 70.5, 54.19, -18.2, N), ('ssw_rub_1', 73.6, 54.8, z, 1.4), ('ssw_pip_1', 66.0, 60.05, -18.0, S), ('ssw_pip_1', 72.0, 60.05, -18.0, S), ('ssw_pip_1', 78.0, 60.05, -18.0, S),
            ('ssw_plk_1', 75.0, 57.3, -20.28, 1.1),
            ('ssw_lan_1', 72.6, 195.5, -18.2, E), ('ssw_rub_1', 73.3, 199.0, z, 2.2),
            ('ssw_pip_1', 89.01, 14.0, -18.0, W_), ('ssw_pip_1', 89.01, 20.0, -18.0, W_)]


# these stand after the graphs, off the graph's edges (walls, under bunks, or no collision), and nothing found from a graph node moves for them (rooms() furniture re-rolls pick())
LATE = [('upn', lambda: dorm2('pn', -2.4)), ('ups', lambda: dorm2('ps', 1.9)), ('ukr', lambda: dorm2('kr') + kral_corner()), ('uh1', washroom), ('anl', lambda: corridor(17.5) + corridor_top(20.7)), ('srv', servers), ('sw2', sewer2)]
LATE = [(nm_, _dressed(nm_, fn_)) for nm_, fn_ in LATE]

# furniture stands before navgen, so a new room changes the graph and pick() rolls other nodes: what the story or a proven route needs is pinned here, in game units, as in the build before these rooms
PIN_CASE = (714795.9, 794776.9)                            # (Kral's table and laptop: the carpet and the office are laid round it)
PIN_GUN = {'Dragunov admin top floor': (228384.0, 952435.7, 51971.8)}      # (on the table in the sniper's room)
PIN_BUTTON = {'S generator A yard': ((426924.2, 398182.9, 12993.9), 1.1780972), 'S large house': ((310854.1, 487629.7, 7290.7), 1.5707964), 'N admin ground floor': ((221211.2, 974099.9, 40058.5), 1.5707964),
              'N hangar': ((638980.9, 939499.4, -24190.4), -2.9452431), 'N personnel building west': ((379339.0, 963492.3, 38142.6), -0.3926991), 'N personnel building east': None,
              'S garage and east gate': None, 'N east pad and fuel depot': None, 'S storage house': None}        # (None: no button there, as before)
ROOM_LEVEL = {'sw2': 50.0, 'srv': 70.0, 'upn': 66.0, 'ups': 66.0, 'ukr': 66.0, 'uh1': 66.0, 'ops': 66.0, 'qm': 66.0, 'dpn': 66.0, 'dps': 66.0, 'dkr': 66.0, 'chg': 66.0, 'grd': 66.0, 'mon': 66.0, 'sh1': 62.0, 'sh2': 62.0, 'sh3': 62.0, 'sh4': 62.0, 'sh5': 62.0, 'sh6': 62.0}


def rack_guns(rx, ry, rz, yaw, wid, xs=(-0.3, 0.0, 0.3)):
    """guns standing in one rack: L24 3307, local y -0.05, 0.56 m under the rack's top edge"""
    c, s = math.cos(yaw), math.sin(yaw)
    g = (yaw - PI) % (2 * PI)
    return [(wid, rx + c * x + s * 0.05, ry + s * x - c * 0.05, rz - 0.56, 1.570796, 0.0, g) for x in xs]


def pickups():
    """(name, weapon id, x, y, z, alpha, beta, gamma): every gun in a rack or on a bench, every medipack on a table or in a cupboard"""
    f = F_ARM
    P = []
    for y, wid, xs in ((106.3, 'AK47', (-0.3, 0.0, 0.3)), (107.45, 'AK47', (-0.15, 0.15)), (108.6, 'UZI', (-0.3, 0.0, 0.3)), (109.75, 'SPAS12', (-0.15, 0.15))):
        for q in rack_guns(80.63, y, f + RACK_Z, E, 'WEAPON_ID_' + wid, xs):
            P.append(('armoury ' + wid.lower(),) + q)
    P.append(('armoury bench rifle', 'WEAPON_ID_AK47', 78.0, 107.65, f + 0.85 + 0.03, 3.141605, 1.449968, 0.2))
    P.append(('armoury bench grenades', 'WEAPON_ID_GRENADE', 78.55, 107.5, f + 0.85 + 0.03, 0.0, 0.0, 0.0))
    P.append(('medipack sewer', 'WEAPON_ID_MEDIPACK', 80.0, 134.30, F_SEWWALK + 0.34 + 0.03, 0.0, 0.0, 1.2))     # (S6: on its carton on the north walk)
    P.append(('clinic medipack 1', 'WEAPON_ID_MEDIPACK', 136.2, 245.0, F_MED + 0.85 + 0.03, 0.0, 0.0, 1.2))
    P.append(('clinic medipack 2', 'WEAPON_ID_MEDIPACK', 135.8, 245.02, F_MED + 0.85 + 0.03, 0.0, 0.0, 1.9))
    qx, qy, qz, _ = W('ps', 1.5, 3.3, F0 + 0.85 + 0.03)
    P.append(('quartermaster rifle', 'WEAPON_ID_AK47', qx, qy, qz, 3.141605, 1.449968, 0.2))
    qx, qy, qz, _ = W('s4', 1.3, -1.45, FS + 0.85 + 0.03)
    P.append(('rest hut uzi', 'WEAPON_ID_UZI', qx, qy, qz, 3.141605, 1.449968, 1.2))
    rx, ry, rz, ryaw = W('sc', 4.8, 1.8, F0 + RACK_Z, E)
    for q in rack_guns(rx, ry, rz, ryaw, 'WEAPON_ID_AK47', (-0.15, 0.15)):
        P.append(('guard room ak47',) + q)
    fb = F_BASE
    for x, wid in ((224.0, 'G36'), (226.0, 'AK47'), (228.0, 'SPAS12'), (230.0, 'DRAGUNOV')):
        for q in rack_guns(x, 199.2, fb + RACK_Z, PI, 'WEAPON_ID_' + wid, (-0.2, 0.2)):
            P.append(('garrison armoury ' + wid.lower(),) + q)
    return P


# a thing hung on the nearest wall of a floor spot, after navgen: (model, x, y, floor z, height of its bottom edge)
HANG = [('ssw_hlt_1', 137.5, 244.0, F_MED, 1.35, (137.5, 243.0)), ('ssw_sga_1', 75.8, 115.3, F_ARM + 0.18, 1.85, (75.8, 114.5))]
# known walls: (model, x, y, z of the bottom edge, gamma); x, y = the plate's back on the wall's DRAWN face (+5 mm)
HANG_AT = [('ssw_nb1_1', 230.96, 205.8, F_BASE + 1.25, PI / 2),
           # (S5 11-15, propaudit look_1: from these three floor spots ssworld.square_wall() squared to what the rays met, but the rays met door jambs: the
           #  crescent's spot (131.2, 245.6) looks through the clinic's doorway (y 245.0..247.27), its side rays hit the south stub's west face AND its end, and it
           #  hung 41 degrees across the jamb's corner, 0.12 m in it (BURIED); the north board was centred where the rays met (y 247.75) and its 1.3 m ran 0.17 m
           #  past the north stub's end into the doorway (NO_WALL); the armoury board's west end hung over the south doorway x 77.55..78.33 (NO_WALL).
           #  Faces measured by rays on build look_1, render = collision mesh 0:)
           ('ssw_scr_1', 132.135, 244.25, F_MED + 2.0, W_),       # lobby side of the south stub, face x 132.140, y 242.9..245.0; the sign's 0.8 at 243.85..244.65
           ('ssw_nb0_1', 132.74, 248.35, F_MED + 1.2, E),         # clinic side of the north stub, face x 132.735, y 247.27..249.42; the board's 1.3 centred on it
           ('ssw_nb1_1', 79.75, 103.245, F_ARM + 1.15, N)]        # armoury south wall, face y 103.240, x 78.33..81.2; the board 79.1..80.4, 1.2 m behind the table
# first-aid cupboards with a medipack on the lower shelf: (x, y, floor z) of a floor spot beside the wall
FAK = [('admin', 56.4, 236.5, 8.38)]
_w0 = W('h1', -1.0, -3.2, F0)
FAK_AT = [('base mess', 230.96, 240.5, F_BASE), ('changing room', _w0[0], _w0[1], _w0[2]),          # (the sewer's wall leans in: a cupboard there was buried, its medipack sits on a carton instead)
          ('south lobby', 76.82, 118.592, F_ARM + 0.18)]       # (S5 11-15, propaudit look_1 NO_WALL: the lobby's south face, y 118.597, ends at x 75.95; from the spot x 76.6 the
#  cupboard's open door (model x 0.25..0.75, to world -x at yaw PI) reached 75.85, 0.1 m past that end into the doorway. x 76.6 -> 76.82: door end 76.07, body to 77.07,
#  0.34 m short of the poster por_p2 (77.41..78.13); back 5 mm off the face. Its medipack: 'SS medipack south lobby', on the lower shelf as before)
FAK_YAW = {'base mess': PI / 2, 'changing room': _w0[3], 'south lobby': PI}
