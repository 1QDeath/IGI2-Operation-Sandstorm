"""searchlight - rotating searchlights for the watch towers of IGI 2 custom missions (Operation Frostbite, owner brief 10-13:
'rotating searchlights on watchtowers'). IGI 2 has no dynamic light; a searchlight here is two new vertex-lit models:

  fb_slb_1   a steel post with a foot plate, carrying an ATTA slot 'fb_slh_1' at its pivot (the 740 rotor recipe:
             the engine draws an ATTA sub-model by itself, a RotateAttachment task spins it about its local z)
  fb_slh_1   the lamp drum (+ yoke) whose lens carries a WOLG glow (the engine's lamp halo, as on 332_01_1 / 710_01_1)
             and the BEAM: an open cone, tilted down, alpha-blended (DNER flag 0x04, mode-67 ARGB texture whose alpha
             fades along the beam), both windings, normals up (vertex light: the beam reads bright)

    import searchlight
    searchlight.add_models(overlay_dir, 'forestraid')              # after the mission is written: manifest + banks + lod
    ... EditRigidObj(pos, yaw, 'fb_slb_1') with child RotateAttachment(0, 0, speed, 'fb_slh_1', 0)

Model frame: z up, +y = where the lamp looks. Units: 4096 per metre.
"""
import copy, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, mefmesh, wreck

M = 4096.0
BASE, HEAD = 'fb_slb_1', 'fb_slh_1'             # (names end in _1: single-LOD, like w740_01_1)
PIVOT_M = 1.05                                     # lamp pivot above the base origin (the platform floor)


# ------------------------------------------------------------------------------------------------ geometry helpers
def _box(c, h):
    """axis-aligned box: centre c, half sizes h -> (positions (24,3), triangles (12,3), normals (24,3), uv (24,2))"""
    c = np.asarray(c, float); h = np.asarray(h, float)
    P, T, N, U = [], [], [], []
    for ax in range(3):
        for sg in (-1, 1):
            n = np.zeros(3); n[ax] = sg
            u_ax, v_ax = [a for a in range(3) if a != ax]
            quad = []
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = c.copy(); p[ax] += sg * h[ax]; p[u_ax] += su * h[u_ax]; p[v_ax] += sv * h[v_ax]
                quad.append(p)
            b = len(P)
            P += quad; N += [n] * 4; U += [(0, 0), (1, 0), (1, 1), (0, 1)]
            tri = [(b, b + 1, b + 2), (b, b + 2, b + 3)]
            # front face CLOCKWISE seen from outside (FORMAT.md): flip so -cross(b-a, c-a) points along n
            out = []
            for t in tri:
                a_, b_, c_ = (np.asarray(P[i]) for i in t)
                if -np.cross(b_ - a_, c_ - a_) @ n < 0:
                    t = (t[0], t[2], t[1])
                out.append(t)
            T += out
    return np.array(P), np.array(T), np.array(N), np.array(U, float)


def _orient(P, T, N, outward):
    """make every triangle clockwise from outside (-cross along `outward` per triangle)"""
    T = T.copy()
    for k, (a, b, c) in enumerate(T):
        if -np.cross(P[b] - P[a], P[c] - P[a]) @ outward[k] < 0:
            T[k] = (a, c, b)
    return T


def _cylinder(r, y0, y1, seg=16, cap_front=False):
    """drum along +y: side wall (+ optional front cap) -> P, T, N, U"""
    P, N, U, T = [], [], [], []
    for k in range(seg + 1):
        a = 2 * math.pi * k / seg
        x, z = r * math.cos(a), r * math.sin(a)
        for y in (y0, y1):
            P.append((x, y, z)); N.append((math.cos(a), 0, math.sin(a))); U.append((k / seg, 0.0 if y == y0 else 1.0))
    for k in range(seg):
        i = 2 * k
        T += [(i, i + 1, i + 3), (i, i + 3, i + 2)]
    P, N, U, T = np.array(P, float), np.array(N, float), np.array(U, float), np.array(T)
    cen = np.c_[P[T].mean(1)[:, 0], np.zeros(len(T)), P[T].mean(1)[:, 2]]
    T = _orient(P, T, N, cen)
    return P, T, N, U


def _disc(r, y, seg=16):
    P = [(0, y, 0)] + [(r * math.cos(2 * math.pi * k / seg), y, r * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
    U = [(0.5, 0.5)] + [(0.5 + 0.5 * math.cos(2 * math.pi * k / seg), 0.5 + 0.5 * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
    T = np.array([(0, 1 + k, 1 + (k + 1) % seg) for k in range(seg)])
    P = np.array(P, float); N = np.tile([0, 1.0, 0], (len(P), 1))
    T = _orient(P, T, N, np.tile([0, 1.0, 0], (len(T), 1)))
    return P, T, N, np.array(U, float)


def _beam(length_m, r0_m, r1_m, y0_m, tilt_deg, seg=24, rings=10):
    """open cone along +y, pitched down by tilt_deg, two-sided; uv: u around, v along (0 at the lamp)"""
    P, U = [], []
    for j in range(rings + 1):
        f = j / rings
        y = (y0_m + (length_m - y0_m) * f) * M
        r = (r0_m + (r1_m - r0_m) * f) * M
        for k in range(seg + 1):
            a = 2 * math.pi * k / seg
            P.append((r * math.cos(a), y, r * math.sin(a))); U.append((k / seg, f))
    P = np.array(P, float)
    t = math.radians(tilt_deg)
    R = np.array([[1, 0, 0], [0, math.cos(t), math.sin(t)], [0, -math.sin(t), math.cos(t)]])   # +y tips down (-z)
    P = P @ R.T
    T = []
    w = seg + 1
    for j in range(rings):
        for k in range(seg):
            i = j * w + k
            T += [(i, i + w, i + w + 1), (i, i + w + 1, i + 1)]
    T = np.array(T)
    T2 = T[:, [0, 2, 1]]                                         # the inside: the same triangles, other winding
    N = np.tile([0, 0, 1.0], (len(P), 1))                        # (lit from above: the beam reads bright, both faces)
    return P, np.concatenate([T, T2]), N, np.array(U, float)


def _merge(parts):
    P, T, N, U = [], [], [], []
    off = 0
    for p, t, n, u in parts:
        P.append(p); T.append(t + off); N.append(n); U.append(u); off += len(p)
    return np.concatenate(P), np.concatenate(T), np.concatenate(N), np.concatenate(U)


# ------------------------------------------------------------------------------------------------ textures (float RGBA)
def tex_metal(n=64):
    rng = np.random.default_rng(3)
    g = 0.26 + 0.05 * rng.random((n, n))
    img = np.dstack([g * 0.95, g, g * 1.08, np.ones((n, n))])
    img[:, :2, :3] *= 0.6; img[:2, :, :3] *= 0.6                  # seams
    return np.clip(img, 0, 1)


def tex_lens(n=64):
    yy, xx = np.mgrid[0:n, 0:n] / (n - 1) * 2 - 1
    r = np.hypot(xx, yy)
    v = np.clip(1.15 - 0.35 * r, 0, 1)
    img = np.dstack([v, v * 0.97, v * 0.86, np.ones((n, n))])
    return np.clip(img, 0, 1)


def tex_beam(w=32, h=128, alpha0=0.55):
    rng = np.random.default_rng(5)
    v = np.linspace(0, 1, h)[:, None]
    fall = (1 - v) ** 1.25 * np.clip(v / 0.03, 0, 1)             # fade out along the beam, soft at the lens
    streak = 0.85 + 0.15 * np.interp(np.arange(w), np.linspace(0, w - 1, 9), rng.random(9))[None, :]
    a = np.clip(alpha0 * fall * streak, 0, 1)
    img = np.dstack([np.full((h, w), 1.0), np.full((h, w), 0.97), np.full((h, w), 0.84), a])
    return img


# ------------------------------------------------------------------------------------------------ models
def _coll(P, T, surface=6):
    mats0 = np.zeros(1, mefmesh.TAMC_DT); mats0[0] = (0, 0xFFFF, 0, surface)
    mats1 = np.zeros(1, mefmesh.TAMC_DT); mats1[0] = (1065353216, 0xFFFFFFFF, 0, 21)
    return [mefmesh.CollMesh(P, T, np.zeros(len(T), np.int64), mats0), mefmesh.CollMesh(P, T, np.zeros(len(T), np.int64), mats1)]


_HSEM = []


def _hsem_template():
    if os.environ.get('SS_FAST') and _HSEM:           # (11-07: 133 calls, each re-read the game's .res files until it found the mesh: 33 s of a build)
        return copy.deepcopy(_HSEM[0])
    for n, p, b in mefmesh.iter_game_mefs():
        if n.lower().endswith('/710_01_1.mef'):
            m = mefmesh.Mef.read(b)
            if m.type == 0:
                _HSEM[:] = [copy.deepcopy(m.hsem)]
                return m.hsem
    raise FileNotFoundError('no type-0 710_01_1 for the HSEM template')


def build_base(hsem):
    post = _box((0, 0, PIVOT_M * M / 2), (0.07 * M, 0.07 * M, PIVOT_M * M / 2))
    plate = _box((0, 0, 0.02 * M), (0.28 * M, 0.28 * M, 0.02 * M))
    yoke = _box((0, 0, (PIVOT_M - 0.12) * M), (0.26 * M, 0.05 * M, 0.04 * M))
    P, T, N, U = _merge([post, plate, yoke])
    g = mefmesh.Group(P, U, T, 0, flags=0x1900, nrm=N)
    atta = np.zeros(1, mefmesh.ATTA_DT)
    atta[0] = (HEAD.encode(), (0.0, 0.0, PIVOT_M * M), np.eye(3), 0, -1)
    cP, cT, _, _ = _merge([post, plate])
    r = mefmesh.RigidModel([g], _coll(cP, cT), hsem=hsem, atta=atta, typ=0)
    return r.to_mef(recompute_spheres=True, recompute_centres=True, rebuild_trees=True)


def build_head(hsem, beam_m=26.0, tilt_deg=13.0):
    drum = _cylinder(0.21 * M, -0.28 * M, 0.24 * M, seg=18)
    back = _disc(0.21 * M, -0.28 * M)
    back = (back[0], back[1][:, [0, 2, 1]], -back[2], back[3])   # (faces backwards)
    ears = _box((0, -0.02 * M, 0), (0.25 * M, 0.06 * M, 0.06 * M))
    P1, T1, N1, U1 = _merge([drum, back, ears])
    lens = _disc(0.19 * M, 0.25 * M)
    bP, bT, bN, bU = _beam(beam_m, 0.19, 2.6, 0.26, tilt_deg)
    groups = [mefmesh.Group(P1, U1, T1, 0, flags=0x1900, nrm=N1),
              mefmesh.Group(lens[0], lens[3], lens[1], 1, flags=0x7f1902, nrm=lens[2]),
              mefmesh.Group(bP, bU, bT, 2, flags=0x7f1906, nrm=bN)]   # (0x04: alpha blended - mode-67 beam texture; 0x02 + byte 2: as the shipped lamp glass groups)
    glow = np.zeros(1, mefmesh.WOLG_DT)
    glow[0] = ((0.0, 0.30 * M, 0.0), 2600.0, 1.0, 0.96, 0.82, 0xABABABAB)   # the lamp halo (size, r, g, b)
    cP, cT, _, _ = _merge([drum, ears])                          # (no collision on the beam)
    r = mefmesh.RigidModel(groups, _coll(cP, cT), hsem=hsem, glows=glow, typ=0)
    return r.to_mef(recompute_spheres=True, recompute_centres=True, rebuild_trees=True)


def add_models(overlay_dir, level_name, beam_m=26.0, tilt_deg=13.0, log=print):
    """register fb_slbase + fb_slhead (+ textures) in a mission overlay's manifest and banks (wreck.add_wreck_model
    recipe: textures -> TEXF/GTT, meshes -> MODS + VNAM/INST, a lod line). -> dict"""
    game_root = os.path.normcase(os.path.realpath(wreck.GAME))   # (reviewer 10-13: the wreck module's guard - never the game folder)
    try:
        inside = os.path.commonpath([game_root, os.path.normcase(os.path.realpath(overlay_dir))]) == game_root
    except ValueError:
        inside = False
    if inside:
        raise ValueError('refusing to write into the game folder: %s' % overlay_dir)
    paths = wreck._ensure_overlay(overlay_dir, level_name)
    m = mtp.read(paths['mtp'])
    if BASE in m['VNAM'] or HEAD in m['VNAM']:
        raise ValueError('searchlight models already in %s' % paths['mtp'])
    hsem = _hsem_template()
    meshes = {BASE: build_base(hsem), HEAD: build_head(hsem, beam_m, tilt_deg)}
    for nm, mf in meshes.items():
        probs = list(mefmesh.semantic_check(mf))
        if probs:
            raise ValueError('%s failed its checks: %s' % (nm, probs[:5]))
    texs = {'fb_slmetal': wreck.tex_mode2(tex_metal()), 'fb_sllens': wreck.tex_mode2(tex_lens()),
            'fb_slbeam': wreck.tex_mode67(tex_beam())}
    form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
    gtt = {}
    for tname, tb in texs.items():
        ch.append((b'NAME', ('LOCAL:textures/%s.tex' % tname).encode('latin1') + b'\0', 4))
        ch.append((b'BODY', tb, 4))
        m['TEXF'].append(tname)
        m['GTT'].append([len(m['TEXF']) - 1, -1])
        gtt[tname] = len(m['GTT']) - 1
    mform, mch, mhdr = ilff.read(open(paths['models'], 'rb').read())
    slots = {BASE: ['fb_slmetal'], HEAD: ['fb_slmetal', 'fb_sllens', 'fb_slbeam']}
    for nm, mf in meshes.items():
        mch.append((b'NAME', ('LOCAL:models/%s.mef' % nm).encode('latin1') + b'\0', 4))
        mch.append((b'BODY', mf.write(), 4))
        m['MODS'].append(nm)
        m['VNAM'].append(nm)
        m['INST'].append([len(m['MODS']) - 1, [gtt[t] for t in slots[nm]]])
    out_tex = ilff.write(form, ch, hdr[1] or 4)
    out_mod = ilff.write(mform, mch, mhdr[1] or 4)
    out_mtp = mtp.write(m)
    for path, blob in ((paths['textures'], out_tex), (paths['models'], out_mod), (paths['mtp'], out_mtp)):
        tmp = path + '.sl.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    lods = [wreck._lod_entry(overlay_dir, '740_01_1', nm, level_name) for nm in meshes]   # (seen from far: a Kamov's cut-offs)
    b2 = wreck.Bank(paths['mtp'], paths['models'], paths['textures'])
    probs = []
    for nm in meshes:
        if b2.models.get(nm) is None:
            probs.append('%s not in the model bank' % nm)
        if b2.res.get(nm) is None:
            probs.append('%s does not resolve' % nm)
    if set(x.lower() for x in b2.m['MODS']) - set(b2.models):
        probs.append('MODS entries without a mesh')
    if set(b2.m['TEXF']) - set(b2.tex):
        probs.append('TEXF entries without a texture')
    log('searchlight: %s (%d tris) + %s (%d tris, beam %.0f m tilted %.0f deg), textures %s, lod %s, problems %s' % (
        BASE, int(meshes[BASE].hsem['n_rfaces']), HEAD, int(meshes[HEAD].hsem['n_rfaces']), beam_m, tilt_deg, sorted(texs), lods[0],
        probs or 'none'))
    assert not probs, probs
    return dict(models=[BASE, HEAD], textures=sorted(texs))
