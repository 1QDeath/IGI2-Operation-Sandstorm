"""icecrack - cracked lake ice for IGI 2 custom missions (Operation Frostbite, owner brief 10-13: 'ice that visibly cracks at
the lake edges'). The game has no ice-crack texture or sound, so both are generated here:

  write_textures(dir) -> dir/fb_icecrack.jpg   1024x1024, tiles seamlessly: wind-blown snow over lake ice, swept-clear
                         blue-grey ice along a network of pressure cracks (torus Voronoi edges with gaps) and a few long
                         main fractures with branches, snow piled on their rims. Used as a TerrainMaterial texture
                         (mapforge.add_material) painted in a ragged band along the shore.
  write_sounds(dir)   -> dir/fb_icecrk<n>.wav  22.05 kHz mono 16-bit: a sharp crack + the descending 'pew' chirp of
                         thermally cracking lake ice + a low boom; for AmbientAreas along the shore (Kit.VO).
"""
import math, os, wave
import numpy as np


# ------------------------------------------------------------------------------------------------ texture
def _tile_noise(n, cells, rng, octaves=4):
    """seamless value noise in 0..1 on an n x n torus"""
    out = np.zeros((n, n)); amp = 1.0; tot = 0.0
    for o in range(octaves):
        c = cells * (2 ** o)
        g = rng.random((c, c))
        y = np.arange(n) * c / n
        y0 = np.floor(y).astype(int); fy = y - y0; fy = fy * fy * (3 - 2 * fy)
        y1 = (y0 + 1) % c
        a = g[y0][:, y0] * (1 - fy)[None, :] + g[y0][:, y1] * fy[None, :]
        b = g[y1][:, y0] * (1 - fy)[None, :] + g[y1][:, y1] * fy[None, :]
        out += amp * (a * (1 - fy)[:, None] + b * fy[:, None]); tot += amp; amp *= 0.5
    return out / tot


def _draw_line(mask, p0, p1, width):
    """anti-aliased thick line on a torus mask (max blend)"""
    n = mask.shape[0]
    L = max(1, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * 2))
    for t in np.linspace(0, 1, L):
        x = p0[0] + (p1[0] - p0[0]) * t; y = p0[1] + (p1[1] - p0[1]) * t
        r = int(math.ceil(width + 1))
        xs = np.arange(int(x) - r, int(x) + r + 1); ys = np.arange(int(y) - r, int(y) + r + 1)
        dx = xs[None, :] - x; dy = ys[:, None] - y
        v = np.clip(width - np.hypot(dx, dy) + 0.5, 0, 1)
        sub = mask[np.ix_(ys % n, xs % n)]
        mask[np.ix_(ys % n, xs % n)] = np.maximum(sub, v)


def crack_texture(n=1024, seed=10):
    rng = np.random.default_rng(seed)
    # pressure-crack network: Voronoi cell edges on the torus (F2 - F1 small)
    pts = rng.random((46, 2)) * n
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    d1 = np.full((n, n), 1e9); d2 = np.full((n, n), 1e9)
    warp = (_tile_noise(n, 6, rng) - 0.5) * 9.0
    wx_, wy_ = xx + warp, yy + np.roll(warp, n // 3, axis=0)
    for px, py in pts:
        for ox in (-n, 0, n):
            for oy in (-n, 0, n):
                d = np.hypot(wx_ - (px + ox), wy_ - (py + oy))
                d2 = np.where(d < d1, d1, np.minimum(d2, d))
                d1 = np.minimum(d1, d)
    edge = d2 - d1
    gaps = _tile_noise(n, 10, rng)                               # cracks are not everywhere: they fade in and out
    net = np.clip(2.4 - edge / 1.3, 0, 1) * np.clip((gaps - 0.36) * 4.0, 0, 1)
    from scipy import ndimage as _nd                            # (folds of the warp made wide dark wedges: a crack is
    yk, xk = np.mgrid[-3:4, -3:4]                               #  never wider than a few pixels - drop the blobs)
    blob = _nd.binary_opening(np.pad(net > 0.4, 8, mode='wrap'), structure=(xk ** 2 + yk ** 2) <= 9)[8:-8, 8:-8]
    blob = _nd.binary_dilation(np.pad(blob, 8, mode='wrap'), iterations=3)[8:-8, 8:-8]
    net[blob] = 0.0
    # long main fractures with branches (random walks, wrapping)
    main = np.zeros((n, n))
    for k in range(5):
        p = rng.random(2) * n
        ang = rng.random() * 2 * math.pi
        wdt = rng.uniform(2.6, 3.6)
        for step in range(70):
            ang += rng.normal(0, 0.07) + (rng.choice((-1, 1)) * rng.uniform(0.4, 0.8) if rng.random() < 0.08 else 0.0)
            q = p + np.array([math.cos(ang), math.sin(ang)]) * rng.uniform(8, 22)
            wdt = float(np.clip(wdt + rng.normal(0, 0.25), 1.6, 4.2))
            _draw_line(main, p, q, wdt)
            if rng.random() < 0.09:                             # a branch
                b = p.copy(); ba = ang + rng.choice((-1, 1)) * rng.uniform(0.6, 1.2)
                for s2 in range(rng.integers(8, 25)):
                    ba += rng.normal(0, 0.15)
                    c = b + np.array([math.cos(ba), math.sin(ba)]) * rng.uniform(6, 14)
                    _draw_line(main, b, c, max(1.0, wdt * rng.uniform(0.45, 0.7)))
                    b = c
            p = q
    crack = np.clip(np.maximum(net * 0.85, main), 0, 1)
    # swept-clear ice along the cracks (wider soft halo) + big blown patches
    from scipy import ndimage
    halo = ndimage.gaussian_filter(crack, 9, mode='wrap')
    halo = np.clip(halo * 3.2, 0, 1)
    patches = np.clip((_tile_noise(n, 3, rng) - 0.55) * 3.5, 0, 1)
    clear = np.clip(np.maximum(halo, patches * 0.8), 0, 1)
    rim = np.clip(ndimage.gaussian_filter(crack, 1.6, mode='wrap') * 2.0 - crack, 0, 1)   # snow piled on the edges
    grain = _tile_noise(n, 64, rng, octaves=2)
    streak = _tile_noise(n, 12, rng, octaves=3)
    snow = np.stack([219.0, 226.0, 240.0])[None, None, :] + ((grain - 0.5) * 22 + (streak - 0.5) * 18)[:, :, None]
    ice_tone = 0.55 + 0.45 * _tile_noise(n, 20, rng, octaves=3)
    ice = np.stack([128.0, 158.0, 190.0])[None, None, :] * (0.85 + 0.25 * ice_tone)[:, :, None] + ((grain - 0.5) * 10)[:, :, None]
    img = snow * (1 - clear[:, :, None] * 0.75) + ice * (clear[:, :, None] * 0.75)
    img = img * (1 - crack[:, :, None] * 0.62) + np.array([52.0, 70.0, 92.0])[None, None, :] * crack[:, :, None] * 0.62
    img = img + rim[:, :, None] * 26.0
    return np.clip(img, 0, 255).astype(np.uint8)


def snow_texture(n=1024, seed=20):
    """wind-packed snow without landmarks (10-13: the shipped k_snow02 has big rock clusters that repeat every tile -
    from the HALO / tour cameras the whole ground was a dotted grid): soft drifts, wind ripples, a few grains"""
    rng = np.random.default_rng(seed)
    drift = _tile_noise(n, 3, rng, octaves=4)
    mid = _tile_noise(n, 9, rng, octaves=3)
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    warp = (_tile_noise(n, 4, rng, octaves=2) - 0.5) * 0.9
    ripple = 0.5 + 0.5 * np.sin(2 * math.pi * (xx * 9 + yy * 3) / n + warp * 6.0)      # (integer wave numbers: seamless)
    ripple = ripple * np.clip((_tile_noise(n, 5, rng) - 0.35) * 2.2, 0, 1)
    grain = _tile_noise(n, 128, rng, octaves=2)
    shade = (drift - 0.5) * 26 + (mid - 0.5) * 12 - ripple * 9 + (grain - 0.5) * 14
    base = np.array([214.0, 222.0, 236.0])
    blue = np.array([-10.0, -4.0, 6.0])                        # shadowed hollows go a little blue
    img = base[None, None, :] + shade[:, :, None] + blue[None, None, :] * np.clip(-(drift - 0.5) * 2.5, 0, 1)[:, :, None]
    specks = rng.random((n, n)) < 0.00025                      # a few dark grains (twigs, grit) - no clusters
    from scipy import ndimage
    specks = ndimage.binary_dilation(specks, iterations=1)
    img[specks] = img[specks] * 0.55
    return np.clip(img, 0, 255).astype(np.uint8)


def write_textures(out_dir):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for name, fn in (('fb_icecrack.jpg', crack_texture), ('fb_snow.jpg', snow_texture)):
        p = os.path.join(out_dir, name)
        if not os.path.exists(p):
            Image.fromarray(fn()).save(p, quality=92)
        out.append(p)
    return out


# ------------------------------------------------------------------------------------------------ sounds
def crack_sound(seed, rate=22050):
    rng = np.random.default_rng(seed)
    dur = rng.uniform(1.4, 2.4)
    n = int(dur * rate)
    t = np.arange(n) / rate
    x = np.zeros(n)
    # 1. the snap: a few broadband micro-cracks in the first 60 ms
    t0 = 0.02
    for k in range(rng.integers(2, 5)):
        tk = t0 + rng.uniform(0, 0.06)
        i0 = int(tk * rate)
        L = int(rng.uniform(0.006, 0.03) * rate)
        env = np.exp(-np.arange(L) / (L / 4.0))
        x[i0:i0 + L] += rng.normal(0, 1, L)[:len(x[i0:i0 + L])] * env[:len(x[i0:i0 + L])] * rng.uniform(0.5, 1.0)
    # 2. the 'pew': a dispersive descending chirp (thermal cracking of lake ice), 2-3 overtones
    f0, f1 = rng.uniform(2600, 4200), rng.uniform(160, 320)
    T = rng.uniform(0.25, 0.6)
    tc = np.clip(t - t0, 0, None)
    f = f1 + (f0 - f1) * np.exp(-tc / (T / 3.0))
    ph = 2 * math.pi * np.cumsum(f) / rate
    env = np.where(t >= t0, np.exp(-tc / (T * 0.9)), 0) * (1 - np.exp(-tc / 0.004))
    chirp = (np.sin(ph) + 0.35 * np.sin(2.03 * ph) + 0.15 * np.sin(3.1 * ph)) * env
    x += chirp * rng.uniform(0.5, 0.8)
    # 3. a low boom rolling under the ice
    b = rng.normal(0, 1, n)
    for _ in range(3):                                           # cheap low-pass: repeated moving averages
        b = np.convolve(b, np.ones(60) / 60, mode='same')
    benv = np.where(t >= t0, np.exp(-tc / rng.uniform(0.5, 0.9)) * (1 - np.exp(-tc / 0.03)), 0)
    x += b / (np.abs(b).max() + 1e-9) * benv * 0.7
    x /= np.abs(x).max() + 1e-9
    fade = np.ones(n); fl = int(0.05 * rate); fade[-fl:] = np.linspace(1, 0, fl)
    return (x * fade * 0.8 * 32767).astype('<i2'), dur


def write_sounds(out_dir, count=3, rate=22050):
    """-> [(path, seconds)]"""
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for k in range(count):
        p = os.path.join(out_dir, 'fb_icecrk%d.wav' % (k + 1))
        x, dur = crack_sound(1300 + k, rate)
        w = wave.open(p, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(x.tobytes()); w.close()
        out.append((p, len(x) / float(rate)))
    return out


if __name__ == '__main__':
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else '.'
    print(write_textures(d), write_sounds(d))
