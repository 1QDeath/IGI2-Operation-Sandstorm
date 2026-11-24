"""IGI 2 sound-bank helpers (written by the sound research 10-10, see work/research/sounds.md).

Formats (reverse-engineered 2026-10-10, see sounds.md):
  * sounds.res = ILFF/IRES archive: NAME+BODY chunk pairs, then one NAME+PATH pair.
      NAME  = 'LOCAL:<dir>/<file>.wav' (or .mp3), NUL-terminated
      PATH  NAME = 'LOCAL:<dir>'   (MUST equal the folder the .res is loaded from, case-insensitive)
      PATH  data = ';'.join(all BODY names) + NUL
  * BODY of a .wav entry = ILSF sample: 20-byte header + signed 16-bit little-endian PCM
      'ILSF' u16 fmt=1  u16 bits=16  u16 channels  u16 flags(0x0000 or 0x1001)  u32 rate  u32 frames
  * BODY of a .mp3 entry = the raw .mp3 file bytes (MPEG audio, as in the ENGLISH voice banks)

Usage examples:
  python soundbank.py ilsf2wav <bank.res> <outdir> [name-substring]   # extract samples as RIFF wav to listen
  python soundbank.py wav2ilsf <in.wav> <out.ilsf>                    # convert a RIFF PCM16 wav
  python soundbank.py list <bank.res>
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ilff  # noqa: E402

ILSF_HDR = struct.Struct('<4sHHHHII')  # magic fmt bits channels flags rate frames  (20 bytes)


# ----------------------------------------------------------------------------- sample formats
def parse_riff(data):
    """-> (channels, rate, bits, pcm_bytes) for a RIFF/WAVE PCM file"""
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise ValueError('not a RIFF/WAVE file')
    p, fmt, pcm = 12, None, None
    while p + 8 <= len(data):
        cid, sz = data[p:p + 4], struct.unpack_from('<I', data, p + 4)[0]
        if cid == b'fmt ':
            fmt = struct.unpack_from('<HHIIHH', data, p + 8)
        elif cid == b'data':
            pcm = data[p + 8:p + 8 + sz]
        p += 8 + sz + (sz & 1)
    if fmt is None or pcm is None:
        raise ValueError('missing fmt/data chunk')
    tag, ch, rate, _br, _ba, bits = fmt
    if tag not in (1, 0xFFFE) or bits != 16:
        raise ValueError('need uncompressed 16-bit PCM (got tag %d, %d bits)' % (tag, bits))
    return ch, rate, bits, pcm


def to_mono16(pcm, channels):
    if channels == 1:
        return pcm
    import array
    a = array.array('h'); a.frombytes(pcm[:len(pcm) // (2 * channels) * 2 * channels])
    out = array.array('h', (sum(a[i:i + channels]) // channels for i in range(0, len(a), channels)))
    return out.tobytes()


def make_ilsf(pcm16, rate, channels=1, flags=0x0000):
    if rate not in (11025, 22050, 44100, 48000):
        raise ValueError('use 11025/22050/44100/48000 Hz (the rates the shipped banks use)')
    frames = len(pcm16) // (2 * channels)
    return ILSF_HDR.pack(b'ILSF', 1, 16, channels, flags, rate, frames) + pcm16[:frames * 2 * channels]


def riff_to_ilsf(wav_bytes, force_mono=True, flags=0x0000):
    ch, rate, bits, pcm = parse_riff(wav_bytes)
    if force_mono and ch != 1:
        pcm, ch = to_mono16(pcm, ch), 1
    return make_ilsf(pcm, rate, ch, flags)


def parse_ilsf(body):
    magic, fmt, bits, ch, flags, rate, frames = ILSF_HDR.unpack_from(body, 0)
    if magic != b'ILSF':
        raise ValueError('not ILSF')
    return dict(fmt=fmt, bits=bits, channels=ch, flags=flags, rate=rate, frames=frames,
                pcm=body[20:20 + frames * ch * 2], seconds=frames / float(rate))


def ilsf_to_riff(body):
    s = parse_ilsf(body)
    pcm, ch, rate = s['pcm'], s['channels'], s['rate']
    return (b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVE' +
            b'fmt ' + struct.pack('<IHHIIHH', 16, 1, ch, rate, rate * ch * 2, ch * 2, 16) +
            b'data' + struct.pack('<I', len(pcm)) + pcm)


# ----------------------------------------------------------------------------- banks
def read_bank(path_or_bytes):
    """-> (dirname_from_PATH, [(full_name, body_bytes), ...])"""
    form, ch, hdr = ilff.read(path_or_bytes)
    assert form == b'IRES', form
    pathname, items = None, []
    for n, t, b in ilff.entries(ch):
        if t == 'PATH':
            pathname = n
        elif t == 'BODY':
            items.append((n, b))
    return pathname, items


def write_bank(res_dir, items, strict=True):
    """res_dir: e.g. 'LOCAL:missions/multiplayer/sandstorm_sp/sounds'
    items: [(file_name_or_full_name, body)] ; plain names get res_dir prefixed.
    Returns the bytes of a sounds.res whose PATH matches res_dir."""
    res_dir = res_dir.rstrip('/')
    chunks, names, seen = [], [], set()
    for n, body in items:
        full = n if ':' in n else res_dir + '/' + n
        base = full.rsplit('/', 1)[-1]
        stem, ext = base.rsplit('.', 1)
        key = stem.lower() + ('.syn' if ext.lower() == 'syn' else '')   # (a voice and its .syn share the stem)
        if not strict:                                     # rebasing an original bank: keep it exactly as shipped
            pass
        elif key in seen:
            raise ValueError('duplicate sample basename %r' % key)
        seen.add(key)
        if strict and len(stem) > 31:
            raise ValueError('sample basename %r longer than 31 chars (engine copies it into a 32-byte stack buffer)' % stem)
        if strict and ext.lower() == 'wav' and body[:4] != b'ILSF':
            raise ValueError('%s: .wav bodies must be ILSF (use riff_to_ilsf)' % base)
        if strict and ext.lower() not in ('wav', 'mp3', 'syn'):    # (11-01 additive: <voice>.syn = the lip-sync envelope)
            raise ValueError('%s: only .wav (ILSF) and .mp3 are registered as samples' % base)
        chunks.append((b'NAME', full.encode('latin1') + b'\0', 4))
        chunks.append((b'BODY', bytes(body), 4))
        names.append(full)
    chunks.append((b'NAME', res_dir.encode('latin1') + b'\0', 4))
    chunks.append((b'PATH', ';'.join(names).encode('latin1') + b'\0', 4))
    return ilff.write(b'IRES', chunks, align=4)


def rebase_bank(path_or_bytes, new_dir, add=(), drop=(), strict=True):
    """copy a bank, renaming every entry + the PATH to new_dir; optionally drop/add samples"""
    _old, items = read_bank(path_or_bytes)
    drop = {d.lower() for d in drop}
    out = [(n.rsplit('/', 1)[-1], b) for n, b in items if n.rsplit('/', 1)[-1].rsplit('.', 1)[0].lower() not in drop]
    out += list(add)
    return write_bank(new_dir, out, strict=strict)


def check_bank(path_or_bytes, expect_dir=None):
    pathname, items = read_bank(path_or_bytes)
    form, ch, hdr = ilff.read(path_or_bytes)
    listed = None
    for n, t, b in ilff.entries(ch):
        if t == 'PATH':
            listed = b.rstrip(b'\0').decode('latin1').split(';')
    problems = []
    if expect_dir and (pathname or '').lower() != expect_dir.lower():
        problems.append('PATH name %r != load dir %r  -> NO sample of this bank gets registered' % (pathname, expect_dir))
    if listed != [n for n, _ in items]:
        problems.append('PATH list does not match BODY names')
    for n, b in items:
        if n.lower().endswith('.wav') and b[:4] != b'ILSF':
            problems.append('%s is not ILSF' % n)
    return pathname, len(items), problems


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'list':
        p, items = read_bank(sys.argv[2])
        print('PATH', p)
        for n, b in items:
            if b[:4] == b'ILSF':
                s = parse_ilsf(b)
                print('%-60s ILSF ch=%d %5d Hz flags=0x%04x %.2fs' % (n, s['channels'], s['rate'], s['flags'], s['seconds']))
            else:
                print('%-60s %s %d bytes' % (n, b[:4], len(b)))
    elif cmd == 'ilsf2wav':
        p, items = read_bank(sys.argv[2]); od = sys.argv[3]; flt = sys.argv[4].lower() if len(sys.argv) > 4 else ''
        os.makedirs(od, exist_ok=True)
        for n, b in items:
            base = n.rsplit('/', 1)[-1]
            if flt in base.lower() and b[:4] == b'ILSF':
                open(os.path.join(od, base.rsplit('.', 1)[0] + '.wav'), 'wb').write(ilsf_to_riff(b))
                print('wrote', base)
    elif cmd == 'wav2ilsf':
        open(sys.argv[3], 'wb').write(riff_to_ilsf(open(sys.argv[2], 'rb').read()))
    else:
        print(__doc__)
