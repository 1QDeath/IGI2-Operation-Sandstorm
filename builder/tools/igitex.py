"""igitex - IGI 2 texture (.tex, 'LOOP' v11) decode / encode for the modes the vehicle textures use.

Header (32 bytes): 'LOOP', u32 version 11, u32 mode, 2 x u32 0, u16 @20 = 5 (?), u16 width @22, u16 height @24,
u16 width @26, u16 height @28, u16 bytes-per-pixel @30. Pixels follow, top row first.
  mode 2  = 16-bit A1R5G5B5, one level (no mip maps)                   (731_26_1 Hind skin, ref1 env map)
  mode 67 = 32-bit A8R8G8B8 (BGRA byte order) + full mip chain        (412_06_1_argb8888 glass)
  mode 3  = 16-bit A4R4G4B4, one level; mode 66 (0x42) / 65 = 16-bit with mips (decoded by bpp + mode bit 6 = mips)
Decoding of modes 2 and 67 is checked against shipped files (mode 2 re-encodes byte-identically). Mode-67 mip
chains: halve both sides per level and stop at the level whose SHORT side is 1 (2048x1024 ends at 2x1, square ends
at 1x1) in 316 of the 322 shipped mode-67 files; 6 non-square ones go on to 1x1 with identical headers, so the
engine accepts both. Derived from file sizes, not from engine code; encode_like follows its template's size.
"""
import struct
import numpy as np


def header(b):
    assert b[:4] == b'LOOP', b[:4]
    mode = struct.unpack_from('<I', b, 8)[0]
    w, h = struct.unpack_from('<HH', b, 22)
    bpp = struct.unpack_from('<H', b, 30)[0]
    return mode, w, h, bpp


def decode(b):
    """-> float32 RGBA (h, w, 4) in 0..1 of the top mip level"""
    mode, w, h, bpp = header(b)
    base = mode & 0x3F
    n = w * h
    if bpp == 2:
        px = np.frombuffer(b, '<u2', n, 32)
        if base == 3:                                              # A4R4G4B4
            a = ((px >> 12) & 15) / 15.0; r = ((px >> 8) & 15) / 15.0; g = ((px >> 4) & 15) / 15.0; bl = (px & 15) / 15.0
        elif base == 1:                                            # R5G6B5
            r = ((px >> 11) & 31) / 31.0; g = ((px >> 5) & 63) / 63.0; bl = (px & 31) / 31.0; a = np.ones(n)
        else:                                                      # A1R5G5B5
            a = ((px >> 15) & 1).astype(float); r = ((px >> 10) & 31) / 31.0; g = ((px >> 5) & 31) / 31.0; bl = (px & 31) / 31.0
        out = np.stack([r, g, bl, a], 1)
    elif bpp == 4:
        px = np.frombuffer(b, 'u1', n * 4, 32).reshape(-1, 4).astype(float) / 255.0
        out = px[:, [2, 1, 0, 3]]                                  # BGRA -> RGBA
    else:
        raise ValueError('bpp %d' % bpp)
    return out.reshape(h, w, 4).astype(np.float32)


def encode_like(b, rgba):
    """re-encode an RGBA image (same size) with the header / format of texture b (mode 2 or 67; mips regenerated)"""
    mode, w, h, bpp = header(b)
    rgba = np.clip(np.asarray(rgba, np.float32), 0, 1)
    assert rgba.shape[:2] == (h, w), (rgba.shape, w, h)
    if bpp == 2 and (mode & 0x3F) == 2:
        q = np.rint(rgba[..., :3] * 31).astype(np.uint16)
        a = (rgba[..., 3] >= 0.5).astype(np.uint16) << 15
        px = a | (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
        body = px.astype('<u2').tobytes()
        if mode & 0x40:
            raise ValueError('16-bit mip chains not supported')
        out = b[:32] + body
    elif bpp == 4:
        levels = [rgba]
        if mode & 0x40:
            # shipped chains: 316 / 322 stop at the level whose SHORT side is 1, 6 non-square ones go on to 1x1
            # (same headers) - follow whichever the template's size says
            def chain_px(full):
                n, w_, h_ = 0, W_, H_
                while True:
                    n += w_ * h_
                    if (min(w_, h_) == 1 and not full) or (w_ == 1 and h_ == 1):
                        return n
                    w_, h_ = max(1, w_ // 2), max(1, h_ // 2)
            H_, W_ = rgba.shape[:2]
            full = (len(b) - 32) == 4 * chain_px(True) and (len(b) - 32) != 4 * chain_px(False)
            cur = rgba
            while (max(cur.shape[:2]) > 1) if full else (min(cur.shape[:2]) > 1):
                hh, ww = max(1, cur.shape[0] // 2), max(1, cur.shape[1] // 2)
                c = cur[:hh * 2, :ww * 2] if cur.shape[0] > 1 and cur.shape[1] > 1 else cur
                if cur.shape[0] > 1 and cur.shape[1] > 1:
                    cur = 0.25 * (c[0::2, 0::2] + c[1::2, 0::2] + c[0::2, 1::2] + c[1::2, 1::2])
                elif cur.shape[0] > 1:
                    cur = 0.5 * (cur[0::2] + cur[1::2])
                else:
                    cur = 0.5 * (cur[:, 0::2] + cur[:, 1::2])
                levels.append(cur)
        body = b''.join((np.rint(L[..., [2, 1, 0, 3]] * 255).astype(np.uint8)).tobytes() for L in levels)
        out = b[:32] + body
    else:
        raise ValueError('mode %d not supported' % mode)
    if len(out) != len(b):
        raise ValueError('size mismatch %d vs %d' % (len(out), len(b)))
    return out
