"""ssprune - 11-07: the engine's LOD model table holds 600 models (igi2.exe, counter 0x7a06c30, fatal 'MTP_nLODVirModel >= 600' at about 75 % of the load).
Every VNAM row of the level takes a slot, plus 28 from COMMON (read live: 552 rows = 580 used). Merged rooms and their props leave ssw_* rows nothing places: only
their wissw_* lit copies or the room mesh are used. This pass runs last and drops those rows, the meshes and textures stay. dbgrun logs the live count as [lodvir]."""
import glob, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtp

CAP = 600
COMMON = 28


def apply(out):
    p = os.path.join(out, 'overlay', 'sandstorm.mtp')
    m = mtp.read(p)
    text = open(os.path.join(out, 'objects.qsc'), 'rb').read().lower()
    for f in glob.glob(os.path.join(out, 'ai', '*')) + [os.path.join(out, 'objects.qvm')]:
        if os.path.isfile(f):
            text += b'\n' + open(f, 'rb').read().lower()
    used = set(re.findall(rb'[a-z0-9_]+', text))
    fam = {}
    for i, n in enumerate(m['VNAM']):
        fam.setdefault(re.sub(r'_\d$', '', n.lower()), []).append(i)
    drop = set()
    for k, ids in fam.items():
        if k.startswith('ssw_') and not any(m['VNAM'][i].lower().encode() in used for i in ids) and k.encode() not in used:
            drop.update(ids)
    n0 = len(m['VNAM'])
    m['VNAM'] = [n for i, n in enumerate(m['VNAM']) if i not in drop]
    m['INST'] = [n for i, n in enumerate(m['INST']) if i not in drop]
    if drop:
        open(p, 'wb').write(mtp.write(m))
    n1 = len(m['VNAM'])
    print('ssprune: %d unused ssw rows dropped, %d left, LOD table %d of %d' % (len(drop), n1, n1 + COMMON, CAP))
    assert n1 + COMMON <= CAP, ('ssprune: LOD table over the engine cap, the level would die at load', n1 + COMMON)
    return len(drop)
