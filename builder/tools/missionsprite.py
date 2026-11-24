"""missionsprite - the mission-select pictures (MENUSYSTEM/missionsprites.res).

Each original picture is 'LOCAL:menusystem/missionsprites/missionNN.spr': a LOOP v9 sprite = 84-byte header
(width, height at dwords 10/11, pixel offset 84 at dword 12, row bytes | height<<16 at dword 14), the picture as
16-bit A1R5G5B5 (alpha bit set), then a constant 40-byte LOOP v6 trailer. The archive ends with a PATH chunk that
lists every sprite (';'-separated) - a sprite missing from that list is not registered.

    python missionsprite.py make <in.png> <out.spr>        (168 x 124, like the originals)
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff

W, H = 168, 124
PREFIX = 'LOCAL:menusystem/missionsprites/'


def _template(res_bytes):
    form, ch, hdr = ilff.read(res_bytes)
    for n, t, b in ilff.entries(ch):
        if n and n.endswith('mission12.spr'):
            return b
    raise KeyError('mission12.spr')


def make(png_path, template):
    """png -> .spr bytes (cropped to the 168:124 shape, resized, a little sharpened)"""
    from PIL import Image, ImageFilter, ImageEnhance
    im = Image.open(png_path).convert('RGB')
    w, h = im.size
    want = W / H
    if w / h > want:                                   # crop the sides
        nw = int(h * want); x0 = (w - nw) // 2; im = im.crop((x0, 0, x0 + nw, h))
    else:
        nh = int(w / want); y0 = (h - nh) // 2; im = im.crop((0, y0, w, y0 + nh))
    im = im.resize((W, H), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.2, percent=60))
    im = ImageEnhance.Contrast(im).enhance(1.08)
    a = np.asarray(im).astype(np.uint16)
    px = 0x8000 | ((a[:, :, 0] >> 3) << 10) | ((a[:, :, 1] >> 3) << 5) | (a[:, :, 2] >> 3)
    hdr = bytearray(template[:84])
    assert struct.unpack_from('<I', hdr, 40)[0] == W and struct.unpack_from('<I', hdr, 44)[0] == H
    return bytes(hdr) + px.astype('<u2').tobytes() + template[84 + W * H * 2:]


def merge(orig_res_path, out_path, sprites):
    """orig archive + {sprite name ('mission20.spr'): spr bytes} -> out_path (replaces same-named entries)"""
    raw = open(orig_res_path, 'rb').read()
    form, ch, hdr = ilff.read(raw)
    path_i = [i for i, (t, b, a) in enumerate(ch) if t == b'PATH']
    assert len(path_i) == 1 and path_i[0] == len(ch) - 1, 'expected one PATH chunk at the end'
    names = ch[-1][1].rstrip(b'\0').decode('latin1').split(';')
    body = list(ch[:-2])                                   # (NAME 'LOCAL:menusystem/missionsprites' + PATH)
    tail = ch[-2:]
    existing = {}
    for i in range(0, len(body) - 1):
        if body[i][0] == b'NAME':
            existing[body[i][1].rstrip(b'\0').decode('latin1')] = i + 1
    for sname, data in sorted(sprites.items()):
        full = PREFIX + sname
        if full in existing:
            t, b, a = body[existing[full]]
            body[existing[full]] = (t, data, a)
        else:
            body.append((b'NAME', full.encode('latin1') + b'\0', 4))
            body.append((b'BODY', data, 4))
            names.append(full)
    tail = [tail[0], (b'PATH', ';'.join(names).encode('latin1') + b'\0', tail[1][2])]
    out = ilff.write(form, body + tail, hdr[1] or 4)
    form2, ch2, hdr2 = ilff.read(out)                      # round trip check
    got = {n for n, t, b in ilff.entries(ch2) if n}
    assert all(PREFIX + s in got for s in sprites), 'sprites missing after merge'
    open(out_path, 'wb').write(out)
    return len(names)


if __name__ == '__main__':
    if sys.argv[1] == 'make':
        tpl = _template(open(r'C:\Users\1qdeath\Games\IGI2\app\MENUSYSTEM\missionsprites.res', 'rb').read())
        open(sys.argv[3], 'wb').write(make(sys.argv[2], tpl))
