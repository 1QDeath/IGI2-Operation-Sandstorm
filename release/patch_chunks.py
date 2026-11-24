"""patch_chunks.py - find (and, for the package, swap out) chunks of a .res (texture / model / sound) that exist ONLY in the Patch
patch's version of a game .res, i.e. Patch's own content that the mission builder pulled from the owner's GOG+Patch game.
A chunk whose bytes exist anywhere in the GOG game (app-backup-before-patch) is not Patch's.

  python -P work/release/patch_chunks.py [package dir]      report only (read-only)
  release.py calls depatch(<res>) on the package copies: every Patch-only chunk is replaced by the GOG game's chunk of the same
  name from the same source file (e.g. Anya's face from the GOG location3.res instead of the Patch one)."""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools'))
import ilff
LIVE = r'C:\Users\1qdeath\Games\IGI2\app'
PRE = r'C:\Users\1qdeath\Games\IGI2\app-backup-before-patch'


def bodies(p):
    """{md5 of chunk body: name} for every body chunk >= 64 bytes"""
    try:
        form, ch, hdr = ilff.read(p)
    except Exception:
        return {}
    out, name = {}, None
    for t, d, a in ch:
        if t == b'NAME':
            name = d.rstrip(b'\0').decode('latin1')
        elif len(d) >= 64:
            out[hashlib.md5(d).hexdigest()] = name or t.decode('latin1')
            name = None
    return out


_MAP = None


def patch_only():
    """{md5: (rel, name)} of chunks in Patch-changed/added .res files that are in no GOG .res"""
    global _MAP
    if _MAP is not None:
        return _MAP
    neo = json.load(open(os.path.join(HERE, 'PATCH_FILES.json')))
    cand = {}
    for rel in neo['changed'] + neo['added']:
        if rel.lower().endswith('.res'):
            for h, n in bodies(os.path.join(LIVE, rel)).items():
                cand[h] = (rel, n)
    gog = set()
    for root, dirs, files in os.walk(PRE):
        for f in files:
            if f.lower().endswith('.res'):
                gog |= set(bodies(os.path.join(root, f)))
    _MAP = {h: v for h, v in cand.items() if h not in gog}
    return _MAP


def gog_chunk(rel, name):
    """the GOG game's body for chunk <name> of <rel> (same file, else the GOG file of the same level folder), or None"""
    cands = [os.path.join(PRE, rel)]
    if rel.lower().endswith('level2/level2.res'):                     # Patch ADDED location2/LEVEL2/level2.res; GOG keeps it in textures/
        cands.append(os.path.join(PRE, os.path.dirname(rel), 'textures', os.path.basename(rel)))
    for p in cands:
        if not os.path.exists(p):
            continue
        form, ch, hdr = ilff.read(p)
        nm = None
        for t, d, a in ch:
            if t == b'NAME':
                nm = d.rstrip(b'\0').decode('latin1')
            elif nm is not None:
                if nm.lower() == name.lower():
                    return d
                nm = None
    return None


def depatch(path):
    """replace every Patch-only chunk of the .res at <path> by the GOG one -> list of (chunk, source, 'swapped'|'NO GOG VERSION')"""
    m = patch_only()
    raw = open(path, 'rb').read()
    form, ch, hdr = ilff.read(path)
    pad = ilff.write(form, ch, align=hdr[1], pad_last=True) == raw          # write it back the way the file was written
    assert pad or ilff.write(form, ch, align=hdr[1], pad_last=False) == raw, 'ilff round trip fails: ' + path
    ch = list(ch)
    out, name = [], None
    for i, (t, d, a) in enumerate(ch):
        if t == b'NAME':
            name = d.rstrip(b'\0').decode('latin1')
            continue
        h = hashlib.md5(d).hexdigest() if len(d) >= 64 else None
        if h in m:
            rel, src = m[h]
            g = gog_chunk(rel, src)
            if g is None:
                out.append((name, '%s:%s' % (rel, src), 'NO GOG VERSION'))
            else:
                ch[i] = (t, g, a)
                out.append((name, '%s:%s' % (rel, src), 'swapped'))
        name = None
    if any(x[2] == 'swapped' for x in out):
        open(path, 'wb').write(ilff.write(form, ch, align=hdr[1], pad_last=pad))
    return out


def report(pkg):
    m = patch_only()
    print('Patch-only chunks (in no GOG .res at all): %d' % len(m))
    total = 0
    for root, dirs, files in os.walk(pkg):
        for f in files:
            if f.lower().endswith('.res'):
                p = os.path.join(root, f)
                b = bodies(p)
                h = [(n, '%s:%s' % m[k]) for k, n in b.items() if k in m]
                total += len(h)
                print('%-62s chunks %5d  patch-only %d' % (os.path.relpath(p, pkg), len(b), len(h)))
                for x in h:
                    print('    PATCH %s  <- %s' % x)
    print('total Patch chunks:', total)
    return total


if __name__ == '__main__':
    sys.exit(1 if report(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'dist', 'Sandstorm_v1.0')) else 0)
