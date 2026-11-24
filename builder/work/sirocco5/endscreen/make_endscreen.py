"""make_endscreen - our own end picture for the campaign (owner 11-15 R14: no Patch screen, not "THE END", leave a hook).

The engine shows screens/intro/<language>/congratulations.jpg after the last mission's stats if it exists (introscreen.c l.145-158),
else the plain screens/intro/congratulations.jpg (= the Patch patch's picture on the owner's PC). We never touch or ship the Patch
file: ss-int's installer copies THIS picture as NEW files SCREENS\\intro\\english\\congratulations.jpg and SCREENS\\intro\\USA\\congratulations.jpg
(and deletes them on rollback). Same size and format as the stock file: 640 x 480 RGB baseline JPEG.

    python work/sirocco5/endscreen/make_endscreen.py        -> work/sirocco5/endscreen/congratulations.jpg (+ preview_2x.png)
"""
import math, os, random
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 640, 480
FONTS = r'C:\Windows\Fonts'


def font(names, size):
    for n in names:
        p = os.path.join(FONTS, n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def ar(text):
    return get_display(arabic_reshaper.reshape(text))


def main():
    random.seed(30)
    S = 2                                                  # (drawn at 2x, then downsampled: clean edges)
    w, h = W * S, H * S
    img = Image.new('RGB', (w, h), (0, 0, 0))
    px = img.load()
    hor = int(h * 0.74)                                    # the ridge line of the oil field
    # sky: near-black blue at the top, warm smoke over the fire at the horizon
    for y in range(h):
        t = y / h
        for x in range(0, w):
            if y < hor:
                g = max(0.0, (t - 0.25) / 0.49) ** 2.2
                d = 1.0 - min(1.0, abs(x - w * 0.62) / (w * 0.55))
                k = g * (0.35 + 0.65 * d)
                px[x, y] = (int(6 + 150 * k), int(8 + 52 * k), int(16 + 8 * k))
    # smoke columns: soft dark plumes rising from the fire
    smoke = Image.new('L', (w, h), 0)
    sd = ImageDraw.Draw(smoke)
    for c_ in range(26):
        x0 = w * (0.40 + 0.40 * random.random())
        r0 = w * (0.02 + 0.03 * random.random())
        for k_ in range(18):
            yy = hor - k_ * h * 0.035
            xx = x0 + math.sin(k_ * 0.45 + c_) * w * 0.02 + k_ * w * 0.006
            rr = r0 * (1 + k_ * 0.22)
            sd.ellipse([xx - rr, yy - rr, xx + rr, yy + rr], fill=int(60 - k_ * 2.5))
    smoke = smoke.filter(ImageFilter.GaussianBlur(18 * S))
    img = Image.composite(Image.new('RGB', (w, h), (4, 4, 6)), img, smoke)
    # the fire on the ridge: bright core, glow
    glow = Image.new('RGB', (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for k_ in range(40):
        x0 = w * (0.48 + 0.28 * random.random())
        fh = h * (0.03 + 0.07 * random.random())
        fw = w * (0.012 + 0.02 * random.random())
        gd.polygon([(x0 - fw, hor + 4 * S), (x0 + fw, hor + 4 * S), (x0 + random.uniform(-fw, fw) * 0.6, hor - fh)],
                   fill=(255, 150 + random.randint(0, 70), 40))
    glow = glow.filter(ImageFilter.GaussianBlur(3 * S))
    big = glow.filter(ImageFilter.GaussianBlur(30 * S))
    img = Image.blend(img, Image.eval(Image.merge('RGB', [Image.eval(c, lambda v: min(255, v * 2)) for c in big.split()]), lambda v: v), 0.0)
    from PIL import ImageChops
    img = ImageChops.add(img, big)
    img = ImageChops.add(img, glow)
    # the ridge and a pipeline's stilts in silhouette in front of the fire
    d = ImageDraw.Draw(img)
    pts = [(0, hor + 30 * S)]
    for x in range(0, w + 40 * S, 40 * S):
        pts.append((x, hor + int(10 * S * math.sin(x / (90.0 * S)) + 6 * S * math.sin(x / (23.0 * S)))))
    pts += [(w, h), (0, h)]
    d.polygon(pts, fill=(3, 3, 4))
    py = hor - 22 * S
    d.rectangle([0, py, w, py + 5 * S], fill=(3, 3, 4))
    for x in range(14 * S, w, 64 * S):
        d.rectangle([x, py, x + 3 * S, hor + 12 * S], fill=(3, 3, 4))
    # a helicopter far over the fire, leaving (the story's last image: Dhari is dead, the buyer is not)
    hx, hy = int(w * 0.80), int(h * 0.30)
    d.ellipse([hx - 9 * S, hy - 3 * S, hx + 9 * S, hy + 3 * S], fill=(2, 2, 3))
    d.line([hx + 8 * S, hy, hx + 22 * S, hy - 2 * S], fill=(2, 2, 3), width=2 * S)
    d.line([hx - 16 * S, hy - 5 * S, hx + 16 * S, hy - 5 * S], fill=(2, 2, 3), width=1 * S)
    # vignette
    vig = Image.new('L', (w, h), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([-w * 0.25, -h * 0.35, w * 1.25, h * 1.25], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(60 * S))
    img = Image.composite(img, Image.new('RGB', (w, h), (0, 0, 0)), vig)
    # the words
    d = ImageDraw.Draw(img)
    f_big = font(['impact.ttf', 'arialbd.ttf'], 56 * S)     # (orch-2 decision 104: 62 -> 56, the block moves up)
    f_ar = font(['tahomabd.ttf', 'arialbd.ttf', 'arial.ttf'], 36 * S)   # (44 -> 36)
    f_small = font(['arialbd.ttf', 'arial.ttf'], 14 * S)

    def centre(text, f, top, fill, spacing=0, shadow=True):
        """draw text centred with its GLYPH top at `top` (2x px) -> its glyph bottom incl. the shadow (2x px)"""
        bb = d.textbbox((0, 0), text, font=f)
        y = top - bb[1]
        tw = bb[2] - bb[0] + spacing * (len(text) - 1)
        x = (w - tw) / 2 - bb[0]
        if spacing:
            for ch in text:
                if shadow:
                    d.text((x + 2 * S, y + 2 * S), ch, font=f, fill=(0, 0, 0))
                d.text((x, y), ch, font=f, fill=fill)
                x += d.textbbox((0, 0), ch, font=f)[2] + spacing
        else:
            if shadow:
                d.text((x + 2 * S, y + 2 * S), text, font=f, fill=(0, 0, 0))
            d.text((x, y), text, font=f, fill=fill)
        return y + bb[3] + (2 * S if shadow else 0)

    # orch-2 decision 104 (sheet r14_end.jpg): the engine's MISSION STATS table is drawn over this picture and covered half of the Arabic
    # word - the title block ends above y 165 (of 480), nothing but sky and glow from 165 to 300; the hook line stays where it was
    TITLE_END = 165
    b1 = centre('OPERATION SIROCCO', f_small, 18 * S, (170, 150, 110), spacing=5 * S)
    b2 = centre('TO BE CONTINUED', f_big, b1 + 12 * S, (236, 232, 222), spacing=2 * S)
    b3 = centre(ar('يتبع'), f_ar, b2 + 14 * S, (222, 170, 70))
    assert b3 <= (TITLE_END - 5) * S, 'title block ends at y %.0f, must end above %d' % (b3 / S, TITLE_END)
    print('title block: OPERATION SIROCCO to y %.0f, TO BE CONTINUED to y %.0f, Arabic to y %.0f (limit %d)' % (b1 / S, b2 / S, b3 / S, TITLE_END))
    hook = 'JONES... DON\'T COME HOME. NOT YET.'
    centre(hook, f_small, int(h * 0.90) + d.textbbox((0, 0), hook, font=f_small)[1], (150, 140, 120), spacing=2 * S)   # (unchanged: same draw origin)
    img2 = img.resize((W, H), Image.LANCZOS)
    out = os.path.join(HERE, 'congratulations.jpg')
    img2.save(out, 'JPEG', quality=92, optimize=False, progressive=False, subsampling=2)
    img.save(os.path.join(HERE, 'preview_2x.png'))
    chk = Image.open(out)
    assert chk.size == (W, H) and chk.mode == 'RGB', (chk.size, chk.mode)
    print('wrote', out, chk.size, chk.mode, os.path.getsize(out), 'bytes')


if __name__ == '__main__':
    main()
