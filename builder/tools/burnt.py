"""burnt - a burnt-out copy of a model (owner round 3, 10-10: "it looks like it's just glowing ... make it like it's
blown up"). There is no wrecked helicopter in the game, so the Hind gets one: the SAME mesh under a new virtual model
name whose texture slots point at charred copies of its textures.

Textures (.tex, LOOP v11): 32-byte header (u16 width at 22, height at 24, bytes per pixel at 30; mode dword at 8:
2 = 16-bit A1R5G5B5, no mip maps), then the pixels. Only that mode is charred here (the Hind's 731_26_1 / 731_27_1).
The manifest gets: 2 TEXF names, 2 GTT entries, 1 VNAM + INST (same MODS index as the source model's LOD 1).
Only LOD 1 exists, so the engine (which bumps the last character for LODs) stops there.

    burnt.add_burnt_model(overlay_dir, 'forestraid', '740_01_1', 'b740_01_1')
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp

COMMON_BIT = mtp.COMMON_BIT


def tex_read(b):
    assert b[:4] == b'LOOP' and struct.unpack_from('<I', b, 8)[0] == 2, 'only 16-bit (mode 2) textures'
    w, h = struct.unpack_from('<HH', b, 22)
    assert len(b) == 32 + w * h * 2, (len(b), w, h)
    px = np.frombuffer(b[32:], '<u2').reshape(h, w)
    rgb = np.dstack([((px >> 10) & 31), ((px >> 5) & 31), (px & 31)]).astype(np.float32) / 31.0
    return b[:32], rgb, (px & 0x8000)


def tex_write(hdr, rgb, abit):
    q = np.clip(np.rint(rgb * 31.0), 0, 31).astype(np.uint16)
    px = abit | (q[:, :, 0] << 10) | (q[:, :, 1] << 5) | q[:, :, 2]
    return hdr + px.astype('<u2').tobytes()


def _noise(h, w, seed, scales=(8, 24, 64, 160), weights=(0.45, 0.3, 0.17, 0.08)):
    """smooth value noise in 0..1 (bilinear-upsampled random grids)"""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    for s, wt in zip(scales, weights):
        gh, gw = max(2, h // max(1, h // s)), max(2, w // max(1, w // s))
        g = rng.random((s + 1, s + 1)).astype(np.float32)
        ys = np.linspace(0, s, h, endpoint=False); xs = np.linspace(0, s, w, endpoint=False)
        y0 = ys.astype(int); x0 = xs.astype(int); fy = (ys - y0)[:, None]; fx = (xs - x0)[None, :]
        a = g[y0][:, x0]; b_ = g[y0][:, x0 + 1]; c = g[y0 + 1][:, x0]; d = g[y0 + 1][:, x0 + 1]
        out += wt * ((a * (1 - fx) + b_ * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy)
    return out / sum(weights)


def char(rgb, seed=7):
    """burnt paint: mostly soot black-grey, scorch patches burnt to the bare (dark) metal, a little brown rust, the
    original detail kept faintly so panel lines and markings still read"""
    h, w, _ = rgb.shape
    lum = (0.3 * rgb[:, :, 0] + 0.59 * rgb[:, :, 1] + 0.11 * rgb[:, :, 2])[:, :, None]
    n1 = _noise(h, w, seed)[:, :, None]
    n2 = _noise(h, w, seed + 1, scales=(16, 48, 128), weights=(0.5, 0.3, 0.2))[:, :, None]
    soot = np.array([0.075, 0.07, 0.065], np.float32)
    metal = np.array([0.22, 0.21, 0.2], np.float32)
    rust = np.array([0.30, 0.15, 0.07], np.float32)
    base = soot + lum * 0.11                                       # charred paint, a hint of the old shading
    k_metal = np.clip((n1 - 0.58) * 4.0, 0, 1)                    # paint burnt off: dull dark metal
    base = base * (1 - k_metal) + (metal * (0.55 + 0.35 * lum)) * k_metal
    k_rust = np.clip((n2 - 0.56) * 4.0, 0, 1) * (1 - k_metal) * 0.85
    base = base * (1 - k_rust) + rust * (0.5 + 0.5 * lum) * k_rust
    k_black = np.clip((0.38 - n2) * 5.0, 0, 1)                    # deep soot where the fire was hottest
    base = base * (1 - 0.7 * k_black)
    return np.clip(base * 0.92 + rgb * 0.04, 0, 1)                # (4 % of the original: markings still faintly visible)


def add_burnt_model(overlay_dir, base, src_vn, new_vn, seed=7):
    """overlay_dir = a prefabs/mapforge overlay (has <base>.mtp, textures/<base>.res). -> [new texture names]"""
    mp = os.path.join(overlay_dir, base + '.mtp')
    tp = os.path.join(overlay_dir, 'textures', base + '.res')
    m = mtp.read(mp)
    assert new_vn not in m['VNAM'], new_vn
    i = m['VNAM'].index(src_vn)
    mods_i, gtts = m['INST'][i]
    raw = open(tp, 'rb').read()
    form, ch, hdr = ilff.read(raw)
    have = {n: b for n, t, b in ilff.entries(ch) if n}
    new_g, made = [], []
    for gi in gtts:
        if gi >= COMMON_BIT:
            new_g.append(gi); continue
        ti, pal = m['GTT'][gi]
        if ti >= COMMON_BIT:
            new_g.append(gi); continue
        tname = m['TEXF'][ti]
        key = 'LOCAL:textures/%s.tex' % tname
        if key not in have:
            new_g.append(gi); continue                           # (texture in another bank: leave that slot)
        bname = tname + '_burnt'
        if bname not in m['TEXF']:
            h_, rgb, a = tex_read(have[key])
            data = tex_write(h_, char(rgb, seed + len(made)), a)
            ch.append((b'NAME', ('LOCAL:textures/%s.tex' % bname).encode('latin1') + b'\0', 4))
            ch.append((b'BODY', data, 4))
            m['TEXF'].append(bname)
            made.append(bname)
        m['GTT'].append([m['TEXF'].index(bname), pal])
        new_g.append(len(m['GTT']) - 1)
    assert made, 'no texture of %s could be charred' % src_vn
    m['VNAM'].append(new_vn)
    m['INST'].append([mods_i, new_g])
    open(mp, 'wb').write(mtp.write(m))
    open(tp, 'wb').write(ilff.write(form, ch, hdr[1] or 4))
    m2 = mtp.read(mp)                                            # round trip
    assert m2['VNAM'][-1] == new_vn and m2['INST'][-1] == [mods_i, new_g]
    form2, ch2, hdr2 = ilff.read(open(tp, 'rb').read())
    got = {n for n, t, b in ilff.entries(ch2) if n}
    assert all('LOCAL:textures/%s.tex' % b in got for b in made)
    return made


def preview(tex_bytes, out_png, burnt=True):
    from PIL import Image
    h_, rgb, a = tex_read(tex_bytes)
    im = char(rgb) if burnt else rgb
    Image.fromarray((np.clip(im, 0, 1) * 255).astype(np.uint8)).save(out_png)
