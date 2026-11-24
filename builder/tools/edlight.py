"""edlight - carry lightmaps baked by the official editor (igi2ed 'Calculate lightmaps') into a build.

igi2ed writes one loose file per lightmapped mesh part into the level folder: lightmaps/<task id>_<part>_<lod>.olm
(same naming as the entries of lightmaps/lightmaps.res, 'LOCAL:lightmaps/0048_0002_1.olm'). The game reads the .res.

    python -P tools/edlight.py merge <overlay lightmaps.res> <dir with .olm files> [ids]   # replace/add those entries
    python -P tools/edlight.py stash <dir with .olm files> work/edits/<folder>_lightmaps [ids]  # keep them for rebuilds
    python -P tools/edlight.py info <lightmaps.res|.olm dir> [ids]
    python -P tools/edlight.py take <editor-saved lightmaps.res> <outdir> <ids>      # entries -> loose .olm files

igi2ed Ctrl+S ALSO rewrites the level's lightmaps/lightmaps.res (seen 10-31: 528 of 1289 entries kept, every 112-byte
header rewritten, pixels unchanged unless baked). Never ship that file whole: `take` the baked tasks' entries only.

Kit.write() merges work/edits/<folder>_lightmaps/*.olm into build/<name>/overlay/lightmaps/lightmaps.res on every build
(after the builder's lightcal.calibrate, so the editor bake wins for those tasks). The .olm header (112 bytes) is
checked by the engine against the mesh: only valid for the SAME model with the SAME task id.
"""
import os, re, struct, sys, glob, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OLM = re.compile(r'(\d{4,})([a-z]?)_(\d{4})_(\d)\.olm$', re.I)


def olms(d, ids=None):
    out = {}
    for p in sorted(glob.glob(os.path.join(d, '**', '*.olm'), recursive=True)):
        m = OLM.search(os.path.basename(p))
        if m and (not ids or int(m.group(1)) in ids):
            out[os.path.basename(p).lower()] = p
    return out


def info_olm(b):
    w, h = struct.unpack_from('<HH', b, 108)
    import numpy as np
    px = np.frombuffer(b, 'u1', w * h * 4, 112).reshape(-1, 4)[:, :3] if len(b) >= 112 + w * h * 4 else None
    return w, h, (float(px.mean()) if px is not None else None)


def merge(res_path, olm_dir, ids=None, log=print):
    import prefab
    R = prefab.Res(res_path)
    files = olms(olm_dir, ids)
    rep, add = 0, 0
    lower = {n.lower(): n for n in R.names()}
    for base, p in files.items():
        name = lower.get('local:lightmaps/' + base)
        body = open(p, 'rb').read()
        if name:
            i = R.index[name]
            t, _, a = R.chunks[i]
            R.chunks[i] = (t, body, a); rep += 1
        else:
            R.add('LOCAL:lightmaps/' + os.path.basename(p), body); add += 1
    open(res_path, 'wb').write(R.data())
    log('edlight: %s: %d lightmaps replaced, %d added (from %s)' % (res_path, rep, add, olm_dir))
    return rep, add


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    ids = set(int(x) for x in a[3].split(',')) if len(a) > 3 else None
    if a[0] == 'merge':
        merge(a[1], a[2], set(int(x) for x in a[3].split(',')) if len(a) > 3 else None)
    elif a[0] == 'stash':
        os.makedirs(a[2], exist_ok=True)
        fs = olms(a[1], ids)
        for base, p in fs.items():
            shutil.copy2(p, os.path.join(a[2], os.path.basename(p)))
        print('edlight: %d .olm -> %s' % (len(fs), a[2]))
    elif a[0] == 'take':
        import prefab
        R = prefab.Res(a[1]); want = set(int(x) for x in a[3].split(','))
        os.makedirs(a[2], exist_ok=True); k = 0
        for n in R.names():
            m = OLM.search(n)
            if m and int(m.group(1)) in want:
                open(os.path.join(a[2], n.split('/')[-1]), 'wb').write(R.get(n)); k += 1
        print('edlight: %d .olm -> %s' % (k, a[2]))
    elif a[0] == 'info':
        ids = set(int(x) for x in a[2].split(',')) if len(a) > 2 else None
        if os.path.isdir(a[1]):
            for base, p in olms(a[1], ids).items():
                print(base, *info_olm(open(p, 'rb').read()))
        else:
            import prefab
            R = prefab.Res(a[1])
            for n in R.names():
                m = OLM.search(n)
                if m and (not ids or int(m.group(1)) in ids):
                    print(n, *info_olm(R.get(n)))


if __name__ == '__main__':
    main()
