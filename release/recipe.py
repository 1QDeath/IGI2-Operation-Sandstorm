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
                        _IDX.setdefault(md5b(d), (rel, name))
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
            rel, src = idx[h]
            rec['chunks'].append({'t': t.decode('latin1'), 'a': a, 'g': rel, 'n': src, 'm': h})
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
            d = _chunks_by_name(root_of(c['g'])).get(c['n'].lower())
            assert d is not None, (c['g'], c['n'])
            if md5b(d) != c['m']:
                other += 1
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
