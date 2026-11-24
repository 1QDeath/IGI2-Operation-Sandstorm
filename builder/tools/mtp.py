"""IGI 2 .mtp (resource manifest) reader/writer.

File = big-endian IFF  'FORM' <u32 BE size> 'MTP '  then chunks <tag> <u32 BE size> <data> (padded to even).
Chunk payloads are little-endian (decoded from igi2.exe 0x504a50 / 0x504780 / 0x5047e0 / 0x504840 / 0x504920 /
0x5049d0 and the INST loop at 0x504c00-0x504dd9):
  BANM  u32 n + n NUL strings      animations           -> LOCAL:anims/<s>.iff   (fatal if missing)
  SNDS  u32 n                      (always 0 in shipped files)
  SVOL  u32 n + n NUL strings      shadow-volume models -> LOCAL:models/<s>.mef (0x5042f0)
  MODS  u32 n + n NUL strings      mesh files           -> LOCAL:models/<s>.mef (0x503ba0, FATAL if missing)
  VNAM  u32 n + n u32 offsets + n NUL strings  'virtual model' names = the names tasks reference.
        offsets = running sum of (1 + k) * 4 over the INST entries (not read by the loader, regenerated)
  INST  per VNAM: u32 mods_index, u32 k, k x u32 gtt_index   (the model's texture slots, in mef order)
  TEXF  u32 n + n NUL strings      textures             -> LOCAL:textures/<s>.tex
  PALF  u32 n + n NUL strings      palettes             -> <prefix>palettes/<s>.pal  (always 0)
  GTT   u32 n + n x (u32 texf_index, i32 palf_index|-1)
An index >= 0x2000 (MODS index in INST, GTT index in INST, TEXF index in GTT) means (index - 0x2000) in the
FIRST MTP of the engine's chain = COMMON/common.mtp (0x504c47, 0x504d2d, 0x504d7d).
Every chunk is NUL-padded to a multiple of 4 bytes and the size field includes the padding: the engine's chunk walker
(0x503a90, 0x503b13) steps by (size + 3) & ~3, so an unaligned chunk desynchronises it (fatal null read at load).
"""
import struct, sys

ORDER = ['BANM', 'SNDS', 'SVOL', 'MODS', 'VNAM', 'INST', 'TEXF', 'PALF', 'GTT ']
COMMON_BIT = 0x2000


def _strings(b, p, n):
    out = []
    for _ in range(n):
        e = b.index(b'\0', p)
        out.append(b[p:e].decode('latin1')); p = e + 1
    return out, p


def read(path_or_bytes):
    d = open(path_or_bytes, 'rb').read() if isinstance(path_or_bytes, str) else path_or_bytes
    assert d[:4] == b'FORM' and d[8:12] == b'MTP ', d[:12]
    size = struct.unpack('>I', d[4:8])[0]
    p = 12; raw = {}; order = []
    while p < 8 + size:
        tag = d[p:p + 4].decode('latin1'); sz = struct.unpack('>I', d[p + 4:p + 8])[0]
        raw[tag] = d[p + 8:p + 8 + sz]; order.append(tag)
        p += 8 + ((sz + 3) & ~3)          # the engine's chunk walker (0x503b13) steps by the size rounded up to 4
    m = {'_order': order, '_raw': raw, '_pad': {}}
    ends = {}
    for tag in ('BANM', 'SVOL', 'MODS', 'TEXF', 'PALF'):
        b = raw[tag]; n = struct.unpack_from('<I', b, 0)[0]
        m[tag], ends[tag] = _strings(b, 4, n)
    m['SNDS'] = raw['SNDS']; ends['SNDS'] = len(raw['SNDS'])
    b = raw['VNAM']; n = struct.unpack_from('<I', b, 0)[0]
    m['VNAM_offs'] = list(struct.unpack_from('<%dI' % n, b, 4))
    m['VNAM'], ends['VNAM'] = _strings(b, 4 + 4 * n, n)
    b = raw['INST']; p = 0; inst = []
    for _ in range(n):
        mi, k = struct.unpack_from('<2I', b, p); p += 8
        inst.append([mi, list(struct.unpack_from('<%dI' % k, b, p))]); p += 4 * k
    m['INST'] = inst; ends['INST'] = p
    b = raw['GTT ']; n = struct.unpack_from('<I', b, 0)[0]
    m['GTT'] = [list(struct.unpack_from('<Ii', b, 4 + 8 * i)) for i in range(n)]
    ends['GTT '] = 4 + 8 * n
    for t in order:
        m['_pad'][t] = raw[t][ends[t]:]
    return m


def _pack_strings(lst):
    return struct.pack('<I', len(lst)) + b''.join(s.encode('latin1') + b'\0' for s in lst)


def _pad4(b):
    return b + b'\0' * ((-len(b)) % 4)


def build_chunks(m, keep_pad=False):
    raw = {}
    for tag in ('BANM', 'SVOL', 'MODS', 'TEXF', 'PALF'):
        raw[tag] = _pack_strings(m[tag])
    raw['SNDS'] = m['SNDS']
    names = b''.join(s.encode('latin1') + b'\0' for s in m['VNAM'])
    offs, cum = [], 0
    for mi, g in m['INST']:
        offs.append(cum); cum += (1 + len(g)) * 4
    raw['VNAM'] = struct.pack('<I', len(m['VNAM'])) + struct.pack('<%dI' % len(offs), *offs) + names
    raw['INST'] = b''.join(struct.pack('<2I', mi, len(g)) + struct.pack('<%dI' % len(g), *g) for mi, g in m['INST'])
    raw['GTT '] = struct.pack('<I', len(m['GTT'])) + b''.join(struct.pack('<Ii', t, pl) for t, pl in m['GTT'])
    for t in raw:
        raw[t] = raw[t] + m['_pad'].get(t, b'') if keep_pad else _pad4(raw[t])   # pad4 reproduces all 34 shipped files
    return raw


def write(m, keep_pad=False):
    raw = build_chunks(m, keep_pad)
    body = b''
    for tag in m['_order']:
        data = raw[tag]
        assert len(data) % 4 == 0, 'chunk %s is %d bytes - the engine needs 4-byte aligned chunks' % (tag, len(data))
        body += tag.encode('latin1') + struct.pack('>I', len(data)) + data
    return b'FORM' + struct.pack('>I', len(body) + 4) + b'MTP ' + body


def _get(lst_owner, common, idx, key):
    src = common if idx >= COMMON_BIT else lst_owner
    if src is None:
        return None, None
    return src, src[key][idx & (COMMON_BIT - 1)]


def resolve(m, common=None):
    """-> {vnam: (mef_name, [texture names])}; indices >= 0x2000 resolved through `common` (read() of common.mtp)"""
    out = {}
    for name, (mi, g) in zip(m['VNAM'], m['INST']):
        _, mef = _get(m, common, mi, 'MODS')
        texs = []
        for gi in g:
            gsrc, ent = _get(m, common, gi, 'GTT')
            if ent is None:
                texs.append(None); continue
            _, tex = _get(gsrc, common, ent[0], 'TEXF')
            texs.append(tex)
        out[name] = (mef, texs)
    return out


if __name__ == '__main__':
    m = read(sys.argv[1])
    for k in ORDER:
        v = m.get(k.strip(), m.get(k))
        print(k, len(v))
    print('round-trip byte-identical:', write(m) == open(sys.argv[1], 'rb').read())
