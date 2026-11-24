"""recipe.py - make the add-on GitHub-clean (package worker 11-23): no game content in the package.

  res_recipe(path, index)  a .res the add-on needs (rebuilt level textures/models/sounds, language files, mission pictures) becomes a
                           RECIPE: every chunk whose bytes exist in the player's own game is a reference (game file + chunk name + md5);
                           only our own chunks are shipped (a .bin blob). Setup.exe rebuilds the .res from the player's files.
  gog_index()              md5 of every chunk body of every .res in the GOG game -> (file, chunk name)
  resolve(recipe, blob, root_of)   rebuild in Python (build-time proof, and the expected md5 on a patched game)
  exe_patch(gog_exe, new_exe)      our byte patches (runs + the added tail) so Setup.exe patches the PLAYER's igi2.exe
"""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools'))
import ilff
PRE = r'C:\Users\1qdeath\Games\IGI2\app-backup-before-patch'
SMALL = 64                      # chunks below this size (names, path lists, tiny headers) are shipped as ours


def md5b(b):
    return hashlib.md5(b).hexdigest()


def pairs(path):
    """[(name or None, tag, data, align)] - a NAME chunk followed by its body counts as one named body"""
    form, ch, hdr = ilff.read(path)
    out, name = [], None
    for t, d, a in ch:
        out.append((name if t != b'NAME' else None, t, d, a))
        name = d.rstrip(b'\0').decode('latin1') if t == b'NAME' else None
    return form, hdr, out


_IDX = None


def gog_index():
    global _IDX
    if _IDX is None:
        _IDX = {}
        for root, dirs, files in sorted(os.walk(PRE)):
            dirs.sort()
            for f in sorted(files):
                p = os.path.join(root, f)
                with open(p, 'rb') as fh:                 # EVERY ILFF container of the game (.res, .mef, .tex, ... any extension)
                    if fh.read(4) != b'ILFF':
                        continue
                rel = os.path.relpath(p, PRE).replace(os.sep, '\\')
                try:
                    form, hdr, prs = pairs(p)
                except Exception:
                    continue
                for name, t, d, a in prs:
                    if name and len(d) >= SMALL:
                        lst = _IDX.setdefault(md5b(d), [])
                        if len(lst) < 6 and (rel, name) not in lst:
                            lst.append((rel, name))          # (v1.1: other places with the same bytes = alternative sources)
    return _IDX


_WHOLE = None


def gog_files():
    """md5 of every file of the GOG game -> its path (a mission file that IS a game file is copied from the player's game)"""
    global _WHOLE
    if _WHOLE is None:
        _WHOLE = {}
        for root, dirs, files in sorted(os.walk(PRE)):
            dirs.sort()
            for f in sorted(files):
                p = os.path.join(root, f)
                _WHOLE.setdefault(md5b(open(p, 'rb').read()), os.path.relpath(p, PRE).replace(os.sep, '\\'))
    return _WHOLE


def res_recipe(path, blob_path):
    raw = open(path, 'rb').read()
    form, hdr, prs = pairs(path)
    chs = [(t, d, a) for n, t, d, a in prs]
    pad = ilff.write(form, chs, align=hdr[1], pad_last=True) == raw
    assert pad or ilff.write(form, chs, align=hdr[1], pad_last=False) == raw, path
    idx = gog_index()
    rec = {'form': form.decode('latin1'), 'align': hdr[1], 'pad_last': pad, 'chunks': []}
    blob = bytearray()
    ref_bytes = 0
    for name, t, d, a in prs:
        h = md5b(d)
        if len(d) >= SMALL and h in idx:
            (rel, src), alts = idx[h][0], idx[h][1:]
            c = {'t': t.decode('latin1'), 'a': a, 'g': rel, 'n': src, 'm': h}
            if alts:
                c['alt'] = [list(x) for x in alts]
            rec['chunks'].append(c)
            ref_bytes += len(d)
        else:
            rec['chunks'].append({'t': t.decode('latin1'), 'a': a, 'o': len(blob), 'l': len(d)})
            blob += d
    open(blob_path, 'wb').write(bytes(blob))
    return rec, ref_bytes, len(blob)


_CACHE = {}


def _chunks_by_name(path):
    if path not in _CACHE:
        if len(_CACHE) > 6:
            _CACHE.clear()
        form, hdr, prs = pairs(path)
        _CACHE[path] = {n.lower(): d for n, t, d, a in prs if n}
    return _CACHE[path]


def resolve(rec, blob, root_of):
    """rebuild the .res; root_of(rel) -> the player's file path. Returns (bytes, n chunks that differ from the GOG md5)"""
    chs, other = [], 0
    for c in rec['chunks']:
        if 'g' in c:
            # same order as Setup.exe: the same bytes at any known place first, then the same asset name (the player's version)
            cands = [(c['g'], c['n'])] + [tuple(x) for x in c.get('alt', [])]
            d = None
            for rel, nm in cands:
                p = root_of(rel)
                v = _chunks_by_name(p).get(nm.lower()) if os.path.exists(p) else None
                if v is not None and md5b(v) == c['m']:
                    d = v; break
            if d is None:
                for rel, nm in cands:
                    p = root_of(rel)
                    v = _chunks_by_name(p).get(nm.lower()) if os.path.exists(p) else None
                    if v is not None:
                        d = v; other += 1; break
            assert d is not None, (c['g'], c['n'])
        else:
            d = blob[c['o']:c['o'] + c['l']]
        chs.append((c['t'].encode('latin1'), d, c['a']))
    return ilff.write(rec['form'].encode('latin1'), chs, align=rec['align'], pad_last=rec['pad_last']), other


def exe_patch(gog_exe, new_exe):
    a = open(gog_exe, 'rb').read(); b = open(new_exe, 'rb').read()
    assert len(b) >= len(a)
    runs, i, L = [], 0, len(a)
    while i < L:
        if a[i] != b[i]:
            j = i
            while j < L and (a[j] != b[j] or any(a[k] != b[k] for k in range(j, min(j + 4, L)))):
                j += 1
            runs.append([i, b[i:j].hex()]); i = j
        else:
            i += 1
    return {'runs': runs, 'tail': b[L:].hex(), 'size': len(b), 'result_sha1': hashlib.sha1(b).hexdigest()}


# ---------------------------------------------------------------- v1.1: exe patch by CONTENT (any exe of the same build)
def pe_checksum(b, cs_off):
    """the standard PE checksum (16-bit one's complement sum with the checksum field taken as 0, plus the file length)"""
    s = 0
    n = len(b) // 2 * 2
    for i in range(0, n, 2):
        if cs_off <= i < cs_off + 4:
            continue
        s += b[i] | (b[i + 1] << 8)
        s = (s & 0xffff) + (s >> 16)
    if len(b) & 1:
        s += b[-1]; s = (s & 0xffff) + (s >> 16)
    s = (s & 0xffff) + (s >> 16)
    return (s + len(b)) & 0xffffffff


def exe_patch2(gog_exe, new_exe, known_exes):
    """runs WITH the GOG original bytes + the header fields that are recomputed for the player's exe"""
    import struct
    a = open(gog_exe, 'rb').read(); b = open(new_exe, 'rb').read()
    p = exe_patch(gog_exe, new_exe)
    for r in p['runs']:
        r.append(a[r[0]:r[0] + len(r[1]) // 2].hex())
    pe = struct.unpack_from('<I', a, 0x3c)[0]; opt = struct.unpack_from('<H', a, pe + 20)[0]
    ns_gog = struct.unpack_from('<H', a, pe + 6)[0]; ns_new = struct.unpack_from('<H', b, pe + 6)[0]
    sec0 = pe + 24 + opt
    p.update(pe=pe, opt=opt, gog_len=len(a), ns_gog=ns_gog, ns_new=ns_new,
             f_ns=pe + 6, f_char=pe + 0x16, f_soi=pe + 0x50, f_cs=pe + 0x58, f_salign=pe + 0x38,
             slots=[sec0 + 40 * ns_gog, sec0 + 40 * ns_new],
             known_cs=sorted({struct.unpack_from('<I', open(k, 'rb').read(), pe + 0x58)[0] for k in known_exes}),
             result_cs=struct.unpack_from('<I', b, pe + 0x58)[0], laa=0x20)
    return p


def apply_exe_patch2(src, p):
    """-> (patched bytes, None) or (None, reason): the Python twin of Setup.exe's PatchExe (proof + tests)"""
    import struct
    if len(src) != p['gog_len']:
        return None, 'size %d differs from the GOG build (%d)' % (len(src), p['gog_len'])
    pe = struct.unpack_from('<I', src, 0x3c)[0]
    if pe != p['pe'] or struct.unpack_from('<H', src, pe + 20)[0] != p['opt'] or struct.unpack_from('<H', src, pe + 6)[0] != p['ns_gog']:
        return None, 'PE header layout differs from the GOG build'
    rec = set()
    for o, n in ((p['f_ns'], 2), (p['f_char'], 2), (p['f_soi'], 4), (p['f_cs'], 4)):
        rec |= set(range(o, o + n))
    s0, s1 = p['slots']
    b = bytearray(src)
    for off, new, old in p['runs']:
        nb, ob = bytes.fromhex(new), bytes.fromhex(old)
        for k in range(len(nb)):
            o = off + k
            if o in rec:
                continue
            if s0 <= o < s1:                          # the two new section headers: the slot holds the GOG bytes or nothing
                if src[o] != ob[k] and src[o] != 0:
                    return None, 'section table slot at 0x%x is not free' % o
            elif src[o] != ob[k]:
                return None, 'byte 0x%x is 0x%02x, the patch expects 0x%02x' % (o, src[o], ob[k])
        b[off:off + len(nb)] = nb
    b += bytes.fromhex(p['tail'])
    struct.pack_into('<H', b, p['f_ns'], p['ns_new'])
    struct.pack_into('<H', b, p['f_char'], struct.unpack_from('<H', src, p['f_char'])[0] | p['laa'])
    salign = struct.unpack_from('<I', b, p['f_salign'])[0]
    top = 0
    sec0 = pe + 24 + p['opt']
    for k in range(p['ns_new']):
        vs, va = struct.unpack_from('<II', b, sec0 + 40 * k + 8)
        top = max(top, va + vs)
    struct.pack_into('<I', b, p['f_soi'], (top + salign - 1) // salign * salign)
    cs = struct.unpack_from('<I', src, p['f_cs'])[0]
    struct.pack_into('<I', b, p['f_cs'], p['result_cs'] if cs in p['known_cs'] else pe_checksum(b, p['f_cs']))
    return bytes(b), None
