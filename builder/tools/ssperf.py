"""ssperf - 11-13 Sandstorm frame-rate pass (owner: 'make the game well optimised ... super good PC and a potato'). Runs LAST on a finished
build dir (after ssprune), so it can also post-process any build for an A/B test without a rebuild:

    import ssperf; ssperf.apply(out)                     # builder, after ssprune.apply(out)
    python -P tools/ssperf.py <build dir> [parts]        # parts: comma list of lods,heads (default: SS_PERF or all)

Parts (env SS_PERF, default heads,cut,veg,under,sleep (squads below only; SSPERF_SLEEP_NORTH=1 adds the north) ; SS_PERF=0 = off; 'lods' exists, off: no gain measured on the rigs):
  lods   The new soldiers (tools/sssoldiers.py, 18 VNAMs ssmXX_1 on 13 meshes) were single-LOD: their full LOD-1 skinned mesh (8-10x the
         triangles of the originals' LOD 5) was drawn and skinned for every man at every distance. Each man gets the originals' far
         meshes (rsg/resg/les/csf/infgu _2.._5) with HIS build, head shape and height applied by sssoldiers' own functions, as rows
         ssmXX_2.._5 (the engine finds LODs by VNAM name), switched at 10/20/32/70 m (originals 7/14/21/50) - cut-off stays 1400 m.
         Close up (and in every cutscene close-up: the switch is distance x tan(fov/2)) nothing changes.
         Room for the rows in the 600-slot LOD table (CAP, ssprune): VNAM families nothing in the build names are dropped first.
  heads  Head maps 2048x1024 32-bit + mips (11.2 MB each, 157 MB of the level's 353 MB textures, 4x the HD patch's own heads per
         man) -> 1024x512 (2.8 MB): a head is under 300 px tall in the closest cutscene shot. Box filter of the stored mips = the
         same picture the GPU already showed at any distance past ~2 m.
"""
import os, re, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ilff, mtp, igiqvm
from igiqvm import Call, Flt
from qast import lit

CAP, COMMON = 600, 28
LOD_D = [10.0, 20.0, 32.0, 70.0]                 # m to LOD 2..5 (originals' men: 7 14 21 50)
LOD_CUT = 1400.0
MARGIN = 12                                      # free LOD slots kept after this pass


def _paths(out):
    o = os.path.join(out, 'overlay')
    return os.path.join(o, 'sandstorm.mtp'), os.path.join(o, 'models', 'sandstorm.res'), os.path.join(o, 'textures', 'sandstorm.res'), os.path.join(o, 'lod.qvm')


def _free_ids(out, used, skip=()):
    """Free task ids in the builder's own nid() order (1602-2752, 402-898, then 20-4095). Never 1-19 (AI graph ids,
    10 = LevelFlow), never 900-999 (menu screens: a task there crashes on Esc), never >= 4096, never an id with an
    ai/<id>.qvm or Squad_<id>.qvm file, never an id in skip (e.g. stale lightmap ids). (11-13 fix: was range(1, 4096))"""
    ai = os.path.join(out, 'ai')
    taken = set(used) | set(skip) | set(range(0, 20)) | set(range(900, 1000))
    for lo, hi in ((1602, 2753), (402, 899), (20, 4096)):
        for i in range(lo, hi):
            if i in taken or os.path.exists(os.path.join(ai, '%d.qvm' % i)) or os.path.exists(os.path.join(ai, 'Squad_%d.qvm' % i)):
                continue
            taken.add(i)
            yield i


BASE_LEVEL = r'C:\Users\1qdeath\Games\IGI2\app\MISSIONS\multiplayer\sandstorm'   # (install.py copies this whole folder under the build: sandstorm.dat lists models)


def _used_words(out, extra=b''):
    text = extra.lower()
    for f in glob.glob(os.path.join(out, '**', '*'), recursive=True) + glob.glob(os.path.join(BASE_LEVEL, '**', '*'), recursive=True):
        if os.path.isfile(f) and not f.lower().endswith(('.res', '.mtp', '.wav', '.ogg', '.mp3', '.olm', '.tga')) and os.path.getsize(f) < 50e6:
            text += b'\n' + open(f, 'rb').read().lower()
    return set(re.findall(rb'[a-z0-9_]+', text))


def prune(m, out, need, log=print, extra=b''):
    """drop whole VNAM families (x_1..x_5) that no file of the build nor of the base level it installs over names (reviewer 11-13: the
    base folder's sandstorm.dat lists models), until `need` rows are free; returns rows dropped"""
    free = CAP - COMMON - len(m['VNAM'])
    if free >= need:
        return 0
    used = _used_words(out, extra)
    fam = {}
    for i, n in enumerate(m['VNAM']):
        fam.setdefault(re.sub(r'_\d$', '', n.lower()), []).append(i)
    drop = set()
    for k, ids in sorted(fam.items(), key=lambda kv: -len(kv[1])):
        if k.startswith('ssm') or k.encode() in used or any(m['VNAM'][i].lower().encode() in used for i in ids):
            continue
        drop.update(ids)
        if free + len(drop) >= need:
            break
    old = list(m['VNAM'])
    m['VNAM'] = [n for i, n in enumerate(m['VNAM']) if i not in drop]
    m['INST'] = [n for i, n in enumerate(m['INST']) if i not in drop]
    log('ssperf: prune %d VNAM rows nothing names: %s%s' % (len(drop), ' '.join(sorted({re.sub(r'_\d$', '', n) for i, n in enumerate(old) if i in drop})),
                                                      '' if free + len(drop) >= need else ' - SHORT by %d rows' % (need - free - len(drop))))
    return len(drop)


def _men():
    """[(vnam, mesh id, (mesh, shape, build), height)] exactly as sssoldiers._textures assigns them"""
    if os.environ.get('SSPERF_SRC'):                    # (A/B on an old build: the tools tree that built it, e.g. work/relbuild25/tools)
        sys.path.insert(0, os.environ['SSPERF_SRC'])
    import sssoldiers as S
    out, mesh_id = [], {}
    for vn, face, mesh, shape, bd, kind, wt, build in S.ROSTER:
        k = (mesh, shape, build)
        if k not in mesh_id:
            mesh_id[k] = 'ssm%02d' % len(mesh_id)
        out.append((vn, mesh_id[k], k))
    return S, out


def _lod_mesh(S, k, lod):
    import mefmesh
    mesh, shape, build = k
    base = mesh[:-2]
    src = '%s_%d' % (base, min(lod, 4) if base == 'infgu' else lod)     # (infgu_5 has an extra texture slot first: its LOD 4 stands in)
    data = S._model_bytes(src)
    if build and S.CHARS:
        data = S.build_mesh(data, build)
    if shape:
        data = S.morph(mefmesh.Mef.read(data), shape)
    if S.CHARS and S.HEIGHT.get(k):
        data = S.scale_mesh(data, S.HEIGHT[k])
    return src, data


def lods(out, log=print):
    pm, pmod, ptex, plod = _paths(out)
    m = mtp.read(pm)
    S, men = _men()
    men = [x for x in men if x[0] in m['VNAM'] and x[0] + '_2' not in m['VNAM'] and x[0].endswith('_1')]
    if not men:
        log('ssperf: lods: nothing to do'); return 0
    meshes = sorted({x[1]: x[2] for x in men}.items())
    rows = 4 * len(men)
    prune(m, out, rows + MARGIN, log)
    form, ch, hdr = ilff.read(open(pmod, 'rb').read())
    have = {d.rstrip(b'\0').decode('latin1') for t, d, a in ch if t == b'NAME'}
    # check: sssoldiers' own LOD-1 recipe must give the bytes the build holds, else the far meshes would not be this man
    bodies = {n_: b_ for n_, t_, b_ in ilff.entries(ch) if n_}
    bad = []
    for mid, k in meshes:
        import mefmesh
        mesh, shape, build = k
        d1 = S._model_bytes(mesh)
        if build and S.CHARS: d1 = S.build_mesh(d1, build)
        if shape: d1 = S.morph(mefmesh.Mef.read(d1), shape)
        if S.CHARS and S.HEIGHT.get(k): d1 = S.scale_mesh(d1, S.HEIGHT[k])
        if bodies.get('LOCAL:models/%s.mef' % mid) != d1:
            bad.append(mid)
    if bad:
        log('ssperf: lods: LOD-1 recipe differs from the build for %s - left single-LOD' % bad); return 0
    for mid, k in meshes:
        for lod in (2, 3, 4, 5):
            mn = '%s_l%d' % (mid, lod)
            src, data = _lod_mesh(S, k, lod)
            key = 'LOCAL:models/%s.mef' % mn
            if key not in have:
                ch.append((b'NAME', key.encode('latin1') + b'\0', 4)); ch.append((b'BODY', data, 4)); have.add(key)
            if mn not in m['MODS']:
                m['MODS'].append(mn)
    for vn, mid, k in men:
        i = m['VNAM'].index(vn)
        mods_i, g_ = m['INST'][i]
        for lod in (2, 3, 4, 5):
            m['VNAM'].append(vn[:-2] + '_%d' % lod); m['INST'].append([m['MODS'].index('%s_l%d' % (mid, lod)), list(g_)])
    n = len(m['VNAM'])
    assert n + COMMON <= CAP, ('ssperf: LOD table over the cap', n + COMMON)
    # lod.qvm: the men switch at LOD_D
    ver, st = igiqvm.decompile(open(plod, 'rb').read())
    want = {vn.lower() for vn, _, _ in men}
    hit = 0
    for c in st:
        if isinstance(c, Call) and c.name == 'Task_New' and str(c.args[1]) == 'ModelLODSettings' and str(c.args[3]).lower() in want:
            for j, v in enumerate(LOD_D + [LOD_CUT]):
                c.args[4 + j] = Flt(v)
            hit += 1
    for path, blob in ((pmod, ilff.write(form, ch, hdr[1] or 4)), (pm, mtp.write(m)), (plod, igiqvm.compile_stmts(st, ver))):
        open(path + '.perf.tmp', 'wb').write(blob); os.replace(path + '.perf.tmp', path)
    log('ssperf: lods: %d men x 4 far LODs on %d meshes (%d new meshes), lod rows %d, LOD table %d of %d' % (len(men), len(meshes), 4 * len(meshes), hit, n + COMMON, CAP))
    return len(men)


def heads(out, log=print):
    import struct
    import numpy as np
    pm, pmod, ptex, plod = _paths(out)
    form, ch, hdr = ilff.read(open(ptex, 'rb').read())
    n0, saved, k = len(open(ptex, 'rb').read()), 0, 0
    for j in range(0, len(ch) - 1):
        t, d, a = ch[j]
        if t != b'NAME' or not d.startswith(b'LOCAL:textures/ss_h_'):
            continue
        b = ch[j + 1][1]
        mode = struct.unpack_from('<I', b, 8)[0]; w, h = struct.unpack_from('<HH', b, 22); bpp = struct.unpack_from('<H', b, 30)[0]
        if mode != 67 or bpp != 4 or w <= 1024 or any(d.startswith(b'LOCAL:textures/ss_h_%s_' % f.encode()) for f in HEADS_KEEP):
            continue
        nb = bytearray(b[:32]); struct.pack_into('<HHHH', nb, 22, w // 2, h // 2, w // 2, h // 2)
        new = bytes(nb) + b[32 + w * h * 4:]          # drop the top mip: the chain below it is the same file's own
        ch[j + 1] = (ch[j + 1][0], new, ch[j + 1][2]); saved += len(b) - len(new); k += 1
    if k:
        blob = ilff.write(form, ch, hdr[1] or 4)
        open(ptex + '.perf.tmp', 'wb').write(blob); os.replace(ptex + '.perf.tmp', ptex)
    log('ssperf: heads: %d head maps halved, %.1f MB saved' % (k, saved / 1e6))
    return k


HEADS_KEEP = ('tariq', 'adnan')                  # (the colonel and the general: cutscene close-ups keep the full 2048 face)


PROP_R = 2.5                                    # m: a model under this radius placed as a loose prop
PROP_MIN = 120.0                                 # m: no prop cut-off below this (a 1 m crate there is ~4 px at 1080p, 90 deg)
PROP_K = 25.0                                    # cut-off >= 25 x radius


def _radii(out):
    """{vnam lower: render radius m} for every VNAM of the level (level banks, then the shipped MP common and COMMON banks)"""
    import mefmesh
    pm, pmod, ptex, plod = _paths(out)
    m = mtp.read(pm)
    GAME = r'C:\Users\1qdeath\Games\IGI2\app'
    common = mtp.read(os.path.join(GAME, 'COMMON', 'common.mtp'))
    res = mtp.resolve(m, common)
    banks = {}
    for p in (os.path.join(GAME, 'COMMON', 'models', 'common.res'), os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'models', 'multiplayer.res'), pmod):
        if os.path.exists(p):
            _, ch, _ = ilff.read(p)
            banks.update({n.split('/')[-1][:-4].lower(): b for n, t, b in ilff.entries(ch) if n and n.lower().endswith('.mef')})
    out_ = {}
    for vn, (mef, tx) in res.items():
        b = banks.get(str(mef).lower())
        if b:
            try:
                out_[vn.lower()] = float(mefmesh.Mef.read(b).hsem['sph_render'][3]) / 4096.0
            except Exception:
                pass
    return out_


def cut(out, log=print):
    """loose props (EditRigidObj only, render radius < PROP_R, never a Door / Lift / Building / Ladder / pickup model) go back to sane
    cut-offs: lodfix raised every model we place to 1500 m (owner 10-11: far BUILDINGS popped in cutscenes), so every crate, lamp and
    chair of the base was drawn from anywhere on the map - the engine has no occlusion. New cut-off = max(the game's own lod.qvm value,
    25 x radius, 120 m), never above what it was. Buildings, rooms, walls, fences, doors, trees, vehicles, men keep theirs."""
    pm, pmod, ptex, plod = _paths(out)
    from qast import load, tasks
    st = load(os.path.join(out, 'objects.qvm'))
    kinds = {}
    for t, d, p in tasks(st):
        ty = lit(t.args[1])
        for a in t.args[3:]:
            if isinstance(a, Call):
                continue
            s = lit(a)
            if isinstance(s, str) and len(s) < 40:
                kinds.setdefault(s.lower(), set()).add(ty)
    ver, lst = igiqvm.decompile(open(plod, 'rb').read())
    import lodfix
    _, _, G = lodfix.read(os.path.join(r'C:\Users\1qdeath\Games\IGI2\app', 'lod.qvm'))
    R = _radii(out)
    n, before, after = 0, 0.0, 0.0
    for c in lst:
        if not (isinstance(c, Call) and c.name == 'Task_New' and str(c.args[1]) == 'ModelLODSettings'):
            continue
        mdl = str(c.args[3]).lower()
        k = kinds.get(mdl, set())
        if k != {'EditRigidObj'} or mdl.startswith('ssm') or mdl not in R or R[mdl] >= PROP_R:
            continue
        cur = float(lit(c.args[8]))
        new = min(cur, max(G.get(mdl, [0] * 5)[4], PROP_K * R[mdl], PROP_MIN))
        if new < cur - 1:
            for j in range(4, 8):                    # LOD switches stay where they were, but never past the new cut-off
                c.args[j] = Flt(min(float(lit(c.args[j])), new))
            c.args[8] = Flt(new); n += 1; before += cur; after += new
    open(plod + '.perf.tmp', 'wb').write(igiqvm.compile_stmts(lst, ver)); os.replace(plod + '.perf.tmp', plod)
    log('ssperf: cut: %d loose prop models, mean cut-off %.0f -> %.0f m' % (n, before / max(n, 1), after / max(n, 1)))
    return n


BUSH_CUT = 300.0                                 # m: the MP map's own bushes stop at 150; lodfix had raised every Forest to 900


def veg(out, log=print):
    """the two BUSH forests (900_17_1, 900_18_1: ~690 knee-high bushes) drawn to 300 m instead of 900 (the shipped map: 150). The palm
    forest keeps 900 m (owner 10-11: far trees in the cutscenes). objects.qvm is rewritten in place (decompile/compile is byte-exact)."""
    p = os.path.join(out, 'objects.qvm')
    ver, st = igiqvm.decompile(open(p, 'rb').read())
    from qast import tasks
    n = 0
    for t, d, par in tasks(st):
        if lit(t.args[1]) == 'Forest' and str(lit(t.args[6])).lower() in ('900_17_1', '900_18_1') and float(lit(t.args[20])) > BUSH_CUT:
            t.args[20] = Flt(BUSH_CUT); n += 1
    if n:
        open(p + '.perf.tmp', 'wb').write(igiqvm.compile_stmts(st, ver)); os.replace(p + '.perf.tmp', p)
        q = os.path.join(out, 'objects.qsc')
        if os.path.exists(q):
            open(q, 'w', encoding='latin1').write(igiqvm.stmts_to_qsc(st))
    log('ssperf: veg: %d bush forests drawn to %.0f m' % (n, BUSH_CUT))
    return n


# --------------------------------------------------------------------------------------------- under: the base drawn only near it
# The engine has no occlusion: from the surface every underground room was drawn through the ground (rig spins: hiding them = +37 % avg,
# 1 % low x2.3). A lod.qvm cut-off hides the DRAWING only, collision stays (proven: full walk through the base with them at 1 m, ub1_n2).
# So each big underground shell keeps its Static task (men stand on it, bullets hit it) on a twin VNAM 'c<model>' cut off at 1 m, and a
# drawn copy (same model, place, light) sits in a ConditionalContainer that is on while Jones is in or above that part, or in any cutscene.
GROUPS = [
    ('base', ['ss_hall_1', 'ss_bulw_1', 'ss_gunr_1', 'ss_bigm_1', 'ss_gant_1', 'ss_shaft_1', 'ss_wayd_1'],
     [(220.0, 230.0, -15.0, 200.0, 140.0, 150.0)]),                                  # (the whole airfield above the base and every way down)
]
# (11-13 tour perf_w2: the sewer group is OUT - a drawn copy made at run time does not take its .olm lightmap even with the file
#  copied for its id: the sewer water showed bright green, the sewer rooms +9 brightness. Its shells did not cost frames either.
#  Only shells with light baked into the texture (no LightmapInfo .olm) may be copied. The base shells: identical in the tour.)


def under(out, log=print):
    import copy
    pq, pm, plod = os.path.join(out, 'objects.qvm'), _paths(out)[0], _paths(out)[3]
    lmp = os.path.join(out, 'overlay', 'lightmaps', 'lightmaps.res')
    ver, st = igiqvm.decompile(open(pq, 'rb').read())
    from qast import tasks
    used, logic, cuts, cc_t, aa_t = set(), None, [], None, None
    for t, d, p in tasks(st):
        used.add(int(lit(t.args[0]))) if isinstance(lit(t.args[0]), int) else None
        ty = lit(t.args[1])
        if ty == 'Container' and lit(t.args[2]) == 'SS mission logic':
            logic = t
        elif ty == 'CutScene':
            cuts.append(int(lit(t.args[0])))
        elif ty == 'ConditionalContainer' and cc_t is None:
            cc_t = t
        elif ty == 'AreaActivate' and aa_t is None:
            aa_t = t
    if logic is None or cc_t is None or aa_t is None:
        log('ssperf: under: builder layout not found - left'); return 0
    m = mtp.read(pm)
    if any(v.startswith('css_') or v.startswith('cwissw_') for v in m['VNAM']):
        log('ssperf: under: already applied - left'); return 0
    n_vnam0 = len(m['VNAM'])
    lver, lst = igiqvm.decompile(open(plod, 'rb').read())
    rows = {str(c.args[3]).lower(): c for c in lst if isinstance(c, Call) and c.name == 'Task_New' and str(c.args[1]) == 'ModelLODSettings'}
    lf, lch, lh = ilff.read(open(lmp, 'rb').read())
    lm = {}
    for n_, t_, b_ in ilff.entries(lch):
        if n_:
            lm.setdefault(n_.split('/')[-1].split('_')[0], []).append((n_, b_))
    stale = {int(k) for k in lm if k.isdigit()}          # (old .olm files of ids no task has now: never reuse those ids)
    free = _free_ids(out, used, stale)
    targets = {}
    for t, d, p in tasks(st):
        if lit(t.args[1]) == 'EditRigidObj' and str(lit(t.args[9])).lower() in {x for g in GROUPS for x in g[1]} and p is not None:
            targets.setdefault(str(lit(t.args[9])).lower(), []).append((t, p))
    n_inst, rows_new, lm_new = 0, 0, 0
    for gname, models, zones in GROUPS:
        twins = []
        for mdl in models:
            for t, p in targets.get(mdl, []):
                if 'gate set' in str(lit(p.args[2])) or 'chip set' in str(lit(p.args[2])):
                    continue
                if lit(t.args[2]) == '':                        # (unnamed copies live in cutscene sets)
                    continue
                if lm.get(str(lit(t.args[0]))):                 # (lightmapped: a run-time copy would lose its .olm - tour perf_w2)
                    log('ssperf: under: %s %s has a lightmap - left as it is' % (lit(t.args[0]), mdl)); continue
                cname = 'c' + mdl
                if cname not in m['VNAM']:
                    i = m['VNAM'].index(mdl) if mdl in m['VNAM'] else None
                    if i is None:
                        log('ssperf: under: %s has no level VNAM - skipped' % mdl); continue
                    m['VNAM'].append(cname); m['INST'].append(copy.deepcopy(m['INST'][i])); rows_new += 1
                    if mdl in rows:
                        r = copy.deepcopy(rows[mdl]); r.args[2] = igiqvm.Str(cname); r.args[3] = igiqvm.Str(cname)
                        for j in range(4, 9): r.args[j] = Flt(1.0)
                        lst.append(r)
                tw = copy.deepcopy(t); nid_ = next(free)
                tw.args[0] = igiqvm.Int(nid_); tw.args[2] = igiqvm.Str((str(lit(t.args[2])) + ' (drawn)')[:60])
                for a in tw.args:
                    if isinstance(a, Call) and a.name == 'Task_New':
                        a.args[0] = igiqvm.Int(next(free))       # (a LightmapInfo child: its own id)
                old = str(lit(t.args[0]))
                for n_, b_ in lm.get(old, []):                   # (the lightmaps go by the task id: the copy gets its own)
                    nn = n_.replace('/%s_' % old, '/%d_' % nid_)
                    lch.append((b'NAME', nn.encode('latin1') + b'\0', 4)); lch.append((b'BODY', b_, 4)); lm_new += 1
                t.args[9] = igiqvm.Str(cname)                     # (the Static shell: collision only, never drawn)
                twins.append(tw); n_inst += 1
        if not twins:
            continue
        conds = []
        for k, (x, y, z, fx, fy, fz) in enumerate(zones):
            a = copy.deepcopy(aa_t); aid = next(free)
            a.args[0] = igiqvm.Int(aid); a.args[2] = igiqvm.Str('SS perf %s zone %d' % (gname, k))
            for j, v in zip((3, 4, 5, 9, 10, 11), (x, y, z, fx, fy, fz)):
                v = v * 4096.0
                a.args[j] = igiqvm.Neg(Flt(-v)) if v < 0 else Flt(v)
            a.args[12] = igiqvm.Str('CRITERIA_HUMAN0')          # (Jones only, whatever the template had)
            logic.args.append(a); conds.append('AreaActivate_%d.nActive' % aid)
        conds += ['CutScene_%d.isRun' % c for c in cuts]
        cc = copy.deepcopy(cc_t)
        cc.args[:] = [igiqvm.Int(next(free)), igiqvm.Str('ConditionalContainer'), igiqvm.Str('SS perf: the %s drawn near it' % gname),
                      igiqvm.Str(' || '.join(conds)), igiqvm.Str(''), igiqvm.Str('')] + twins
        logic.args.append(cc)
    prune(m, out, CAP - COMMON - n_vnam0, log, extra=igiqvm.stmts_to_qsc(st).encode('latin1'))   # (LOD rule: a new row replaces one; files are written last)
    assert len(m['VNAM']) + COMMON <= CAP, ('ssperf: under: LOD table over the cap', len(m['VNAM']) + COMMON)
    for path, blob in ((pq, igiqvm.compile_stmts(st, ver)), (pm, mtp.write(m)), (plod, igiqvm.compile_stmts(lst, lver)), (lmp, ilff.write(lf, lch, lh[1] or 4))):
        open(path + '.perf.tmp', 'wb').write(blob); os.replace(path + '.perf.tmp', path)
    q = os.path.join(out, 'objects.qsc')
    if os.path.exists(q):
        open(q, 'w', encoding='latin1').write(igiqvm.stmts_to_qsc(st))
    log('ssperf: under: %d shells drawn only near them (%d VNAM rows, %d lightmaps copied), LOD table %d of %d' % (n_inst, rows_new, lm_new, len(m['VNAM']) + COMMON, CAP))
    return n_inst


# --------------------------------------------------------------------------------------------- sleep: the men below wait until needed
# The underground garrison ('SS U ...' squads, 72 men + 6 truck troops) sits in ConditionalContainers already (held back in the decrypt
# cutscene). Their condition gets '&& (wake || any cutscene)': wake = an EditVariable latch that goes to 1 once Jones enters the airfield /
# base zone or the tunnel zone, either base alarm sounds, or the base-alert variable rises. Once awake they stay awake (a latch), so no man
# is ever re-created after Jones met him. Cutscenes keep them live (the intro films the live posts).
SLEEP_ZONES = {'base': (220.0, 230.0, -15.0, 220.0, 160.0, 150.0),          # (x 110-330, y 150-310, all depths: the airfield and every way down)
               'tunnel': (265.0, 115.0, -5.0, 150.0, 140.0, 120.0),        # (x 190-340, y 45-185: the truck tunnel and its mouth)
               'north': (115.0, 245.0, 0.0, 300.0, 250.0, 160.0)}          # (x -35-265, y 120-370: 60 m + spread south of every sleeping north squad - ss-garrison's event radii)
NEVER = ('truck troops', 'gun room crew')     # (ss-garrison 11-13: climb-out timing / the scripted M2HB fight - never asleep)
SLEEP_NORTH = os.environ.get('SSPERF_SLEEP_NORTH') == '1'                   # (11-13 wake proof: OFF. A north squad woken by the top side alarm is created
                                                                           #  after the alarm's one-shot orders went out: it stayed at its post 60 s
                                                                           #  (work/perf/wake/wa_s vs wa). Only the squads below sleep now.)
NORTH_MIN_Y = 180.0                                                        # (a north squad sleeps only if all its men stand north of this: 150+ m from the start)


def sleep(out, log=print):
    import copy
    pq = os.path.join(out, 'objects.qvm')
    ver, st = igiqvm.decompile(open(pq, 'rb').read())
    from qast import tasks
    used, logic, cuts, aa_t, ev_t, alarms, alert = set(), None, [], None, None, [], None
    for t, d, p in tasks(st):
        if isinstance(lit(t.args[0]), int):
            used.add(int(lit(t.args[0])))
        ty, nm = lit(t.args[1]), str(lit(t.args[2]))
        if ty == 'Container' and nm == 'SS mission logic':
            logic = t
        elif ty == 'CutScene':
            cuts.append(int(lit(t.args[0])))
        elif ty == 'AreaActivate' and aa_t is None:
            aa_t = t
        elif ty == 'EditVariable' and ev_t is None:
            ev_t = t
        elif ty == 'AlarmControl':
            alarms.append(int(lit(t.args[0])))
        if ty == 'EditVariable' and nm.startswith('SS base below on alert'):
            alert = int(lit(t.args[0]))
        if ty == 'ConditionalContainer' and nm.startswith('SS perf: the men below sleep'):
            log('ssperf: sleep: already applied - left'); return 0
    if logic is None or aa_t is None or ev_t is None:
        log('ssperf: sleep: builder layout not found - left'); return 0
    free = _free_ids(out, used)
    conts = []
    for t, d, p in tasks(st):
        nm = str(lit(t.args[2]))
        if lit(t.args[1]) == 'ConditionalContainer' and nm.startswith('SS U ') and 'held back' in nm and not any(k in nm for k in NEVER):
            men = []
            def rec(e):
                if isinstance(e, Call):
                    if e.name == 'Task_New' and lit(e.args[1]) == 'HumanSoldier':
                        men.append([float(lit(v)) / 4096 for v in e.args[3:6]])
                    for a in e.args: rec(a)
            rec(t)
            if men:
                conts.append((t, sum(m[1] for m in men) / len(men)))
    # the far north surface squads (not in any container yet): each gets its own container, woken by the north zone
    north = []
    def wrap(e, parent, inc):
        if isinstance(e, Call):
            if e.name == 'Task_New':
                ty, nm = lit(e.args[1]), str(lit(e.args[2]))
                if ty == 'AISquad' and not inc and parent is not None and nm.startswith('N '):
                    men = [[float(lit(v)) / 4096 for v in a.args[3:6]] for a in e.args if isinstance(a, Call) and a.name == 'Task_New' and lit(a.args[1]) == 'HumanSoldier']
                    if SLEEP_NORTH and men and min(m[1] for m in men) > NORTH_MIN_Y:
                        north.append((parent, e))
                inc2 = inc or ty == 'ConditionalContainer'
                for a in list(e.args):
                    wrap(a, e, inc2)
            else:
                for a in e.args:
                    wrap(a, parent, inc)
    for s_ in st:
        wrap(s_, None, False)
    zid, wid = {}, {}
    # wake: hall + tunnel on the latched base-below alert only (the garrison below is isolated from the top side alarm, owner 11-03 r3);
    # north on the top side alarm 'Alarm on' (it resets after 60 s: the latch keeps them up)
    top = next((int(lit(t.args[0])) for t, d, p in tasks(st) if lit(t.args[1]) == 'EditVariable' and str(lit(t.args[2])) == 'Alarm on'), None)
    wake = {'base': ['EditVariable_%d.nValue > 0' % alert] if alert else [], 'tunnel': ['EditVariable_%d.nValue > 0' % alert] if alert else [],
            'north': ['EditVariable_%d.nValue == 1' % top] if top else []}
    for k, (x, y, z, fx, fy, fz) in SLEEP_ZONES.items():
        if k == 'north' and not north:
            continue
        a = copy.deepcopy(aa_t); zid[k] = next(free)
        a.args[0] = igiqvm.Int(zid[k]); a.args[2] = igiqvm.Str('SS perf sleep zone %s' % k)
        for j, v in zip((3, 4, 5, 9, 10, 11), (x, y, z, fx, fy, fz)):
            v *= 4096.0; a.args[j] = igiqvm.Neg(Flt(-v)) if v < 0 else Flt(v)
        a.args[12] = igiqvm.Str('CRITERIA_HUMAN0')
        logic.args.append(a)
        e = copy.deepcopy(ev_t); wid[k] = next(free)
        e.args[:] = [igiqvm.Int(wid[k]), igiqvm.Str('EditVariable'), igiqvm.Str('SS perf: the %s men awake' % k), Flt(0.0), Flt(0.0), Flt(0.0),
                     igiqvm.Int(0), igiqvm.Str('EditVariable_%d.nValue == 0 && (%s)' % (wid[k], ' || '.join(['AreaActivate_%d.nActive' % zid[k]] + wake[k]))), igiqvm.Str('')]
        logic.args.append(e)
    live = ' || '.join('CutScene_%d.isRun' % c for c in cuts)
    # (ss-garrison check 4: the intro wakes them all on frame 1; when it ends they leave in steps of 1-4 s, not in one tick)
    tmr = next((int(lit(t.args[0])) for t, d, p in tasks(st) if lit(t.args[1]) == 'LevelTimer' and str(lit(t.args[2])) == 'time since intro ended'), None)
    for i, (t, y) in enumerate(conts):
        k = 'tunnel' if y < 150 else 'base'
        old = str(lit(t.args[3]))
        lv = live + ((' || (LevelTimer_%d.isRun && LevelTimer_%d.nTick < %d * GAME_FREQUENCY)' % (tmr, tmr, 1 + i % 4)) if tmr else '')
        if os.environ.get('SSPERF_WAKE_ONLY', '1') == '1':   # (G43 11-14: wake latch only - no cutscene / intro-end terms, see pwake_patch.py)
            lv = ''
        t.args[3] = igiqvm.Str('(%s) && (EditVariable_%d.nValue == 1%s)' % (old, wid[k], (' || ' + lv) if lv else ''))
        assert len(str(t.args[3])) < 1023
    for parent, sq in north:
        ix = next(i for i, a in enumerate(parent.args) if a is sq)
        parent.args[ix] = Call('Task_New', [igiqvm.Int(next(free)), igiqvm.Str('ConditionalContainer'), igiqvm.Str('SS perf: %s asleep until needed' % str(lit(sq.args[2]))[:40]),
                                            igiqvm.Str('EditVariable_%d.nValue == 1%s' % (wid['north'], (' || ' + live) if live else '')), igiqvm.Str(''), igiqvm.Str(''), sq])
    marker = copy.deepcopy(ev_t)                       # (an empty container as the 'already applied' mark)
    marker = Call('Task_New', [igiqvm.Int(next(free)), igiqvm.Str('ConditionalContainer'), igiqvm.Str('SS perf: the men below sleep until needed'),
                               igiqvm.Str('FALSE'), igiqvm.Str(''), igiqvm.Str('')])
    logic.args.append(marker)
    open(pq + '.perf.tmp', 'wb').write(igiqvm.compile_stmts(st, ver)); os.replace(pq + '.perf.tmp', pq)
    q = os.path.join(out, 'objects.qsc')
    if os.path.exists(q):
        open(q, 'w', encoding='latin1').write(igiqvm.stmts_to_qsc(st))
    log('ssperf: sleep: %d squads below (base %d, tunnel %d) + %d north squads asleep until Jones nears or an alarm' % (len(conts), sum(1 for c in conts if c[1] >= 150), sum(1 for c in conts if c[1] < 150), len(north)))
    return len(conts)


def apply(out, parts=None, log=print):
    parts = parts if parts is not None else os.environ.get('SS_PERF', 'heads,cut,veg,under,sleep')
    if parts in ('', '0'):
        log('ssperf: off'); return
    parts = parts.split(',')
    if 'heads' in parts:
        heads(out, log)
    if 'lods' in parts:
        lods(out, log)
    if 'cut' in parts:
        cut(out, log)
    if 'veg' in parts:
        veg(out, log)
    if 'under' in parts:
        under(out, log)
    if 'sleep' in parts:
        sleep(out, log)


if __name__ == '__main__':
    apply(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
