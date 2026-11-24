"""ssworld - Sandstorm's lived-in world (owner 11-06 items 70, 71, 74), behind env SS_WORLD=1 until proven.

LIGHT (item 70). Root cause found 11-06: a lightmapped model (mesh type 3) gets its light from '<task>_<node>_<lod>.olm' in lightmaps.res, and only inside the subtree of a
LightmapInfo task. 206 of our 390 lightmapped objects had neither: the engine draws those full bright (432_12_1 in the sewers, sandbags and crates in the base). relight()
gives each one a LightmapInfo parent and a new .olm: the header needs only a stamp newer than the mesh and the mesh's own lightmap size (PMTL), so any instance can have one.
Pixels are baked per texel from the zone's light level, the surface normal and the height over the floor.
Units: world metres unless named otherwise, 1 m = 4096."""
import math, os, struct, sys
import numpy as np

WORLD = os.environ.get('SS_WORLD', '1') == '1'
WATER = os.environ.get('SS_WATER', '1') == '1'             # (owner 95: water in the sewer channel)
if os.environ.get('SS_MEMLOG'):                            # (dev aid: the build's memory by stage, for the node's 24 GB limit)
    import threading, time as _t

    def _ml():
        while True:
            print('MEM', int(open('/proc/self/statm').read().split()[1]) * 4096 // 2 ** 20, 'MB', flush=True)
            _t.sleep(4.0)
    threading.Thread(target=_ml, daemon=True).start()
OLM_MAGIC = struct.pack('<ff', 0.12, 0.16)
STAMP = (2026, 11, 6, 12, 0, 0, 0)


def _pow2(n):
    p = 1
    while p < n:
        p *= 2
    return p


def make_olm(px):
    """px (h, w, 3) uint8 RGB -> an .olm body, field for field as the shipped ones (D3D A8R8G8B8 texture block)"""
    h, w = px.shape[:2]
    tw, th = _pow2(w), _pow2(h)
    b = bytearray(112)
    b[0:8] = OLM_MAGIC
    struct.pack_into('<7I', b, 8, *STAMP)
    struct.pack_into('<3I', b, 36, 0, 1, 1)
    struct.pack_into('<I', b, 64, tw | th << 16)
    struct.pack_into('<I', b, 68, w * 4 | 3 << 16)
    struct.pack_into('<ff', b, 76, w / float(tw), h / float(th))
    struct.pack_into('<I', b, 88, 0x20000001)
    struct.pack_into('<II', b, 92, 0x1c000000, 0x1c000000)
    struct.pack_into('<I', b, 100, 0x15)
    struct.pack_into('<HH', b, 108, w, h)
    a = np.zeros((h, w, 4), 'u1')
    a[..., 0], a[..., 1], a[..., 2], a[..., 3] = px[..., 2], px[..., 1], px[..., 0], 255    # (BGRA on disk)
    return bytes(b) + a.tobytes()


def texel_maps(rm):
    """RigidModel of type 3 -> (w, h, N, P, mask): each lightmap texel's surface normal and model-space point (rasterised through the lightmap uvs)"""
    w, h = int(rm.pmtl[0]['w']), int(rm.pmtl[0]['h'])
    N = np.zeros((h, w, 3)); P = np.zeros((h, w, 3)); M = np.zeros((h, w), bool)
    for g in rm.groups:
        if g.lmuv is None:
            continue
        uv = g.lmuv * (w, h)
        for t in g.tris:
            a, b, c = uv[t[0]], uv[t[1]], uv[t[2]]
            pa, pb, pc = g.pos[t[0]], g.pos[t[1]], g.pos[t[2]]
            n = -np.cross(pb - pa, pc - pa)                # (faces wind clockwise from the front)
            ln = np.linalg.norm(n)
            if ln < 1e-6:
                continue
            n = n / ln
            x0, y0 = int(max(math.floor(min(a[0], b[0], c[0]) - 1), 0)), int(max(math.floor(min(a[1], b[1], c[1]) - 1), 0))
            x1, y1 = int(min(math.ceil(max(a[0], b[0], c[0]) + 1), w - 1)), int(min(math.ceil(max(a[1], b[1], c[1]) + 1), h - 1))
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    px, py = x + 0.5, y + 0.5
                    l0 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
                    l1 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
                    l2 = 1 - l0 - l1
                    if min(l0, l1, l2) >= -0.02:
                        N[y, x] = n; P[y, x] = l0 * pa + l1 * pb + l2 * pc; M[y, x] = True
    for _ in range(max(w, h)):                             # (the texels between islands take a neighbour's value: bilinear bleed at the seams)
        if M.all():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sh = np.roll(M, (dy, dx), (0, 1)); nsh = np.roll(N, (dy, dx), (0, 1)); psh = np.roll(P, (dy, dx), (0, 1))
            new = sh & ~M
            N[new] = nsh[new]; P[new] = psh[new]; M |= new
    return w, h, N, P, M


# ---------------------------------------------------------------------------------------------- light levels (0..255 of the lightmap; 128 = the texture as painted)
# (name, x0, y0, x1, y1, z0, z1, level, tint r g b): first match wins. Each level is set against the walls' own bake in that place.
ZONES = [
    ('armoury', 74.5, 103.5, 82.0, 115.0, -1.0, 5.0, 98.0, (1.0, 0.97, 0.9)),
    ('large s', 62.0, 100.0, 94.0, 126.0, -1.0, 12.0, 92.0, (1.0, 0.97, 0.9)),
    ('large n', 112.0, 232.0, 146.0, 262.0, -8.0, 5.0, 92.0, (1.0, 0.97, 0.9)),
    ('store s', 144.0, 84.0, 172.0, 112.0, -1.0, 10.0, 112.0, (0.96, 1.0, 1.04)),
    ('store n', 144.0, 208.0, 170.0, 232.0, -8.0, 3.0, 112.0, (0.96, 1.0, 1.04)),
    ('kral', 169.0, 190.0, 185.0, 206.0, -8.0, -2.0, 64.0, (1.0, 0.96, 0.88)),
    ('sewer', 40.0, -40.0, 115.0, 215.0, -24.0, -14.0, 50.0, (0.93, 1.0, 1.02)),
    ('way down', 160.0, 222.0, 180.0, 242.0, -24.0, -7.5, 62.0, (1.0, 0.96, 0.9)),
    ('base', 160.0, 120.0, 330.0, 270.0, -48.0, -14.0, 66.0, (1.0, 0.95, 0.88)),
]
SUN = np.array((0.0, math.cos(0.744), math.sin(0.744)))
# pale things in a dark place: the same light reads brighter on them, so they take less (the sewer's concrete arches against its dark brick)
MODEL_LEVEL = {'432_12_1': (30.0, (1.0, 0.86, 0.72))}


def zone_at(p):
    for z in ZONES:
        if z[1] <= p[0] <= z[3] and z[2] <= p[1] <= z[4] and z[5] <= p[2] <= z[6]:
            return z
    return None


def bake(wmap, R, o, level, tint, outdoor):
    """the pixels of one instance: R, o = its rotation and position (m)"""
    w, h, N, P, M = wmap
    nw = N @ R.T
    pw = P / 4096.0 @ R.T + o
    zlo = pw[..., 2][M].min() if M.any() else o[2]
    up = np.clip(nw[..., 2], -1, 1)
    if outdoor:
        lit = np.clip(nw @ SUN, 0, 1)
        v = level * (0.62 + 0.62 * lit)
    else:
        v = level * (0.84 + 0.22 * np.maximum(up, 0) - 0.14 * np.maximum(-up, 0))
        v = v * (0.78 + 0.22 * np.clip((pw[..., 2] - zlo) / 1.4, 0, 1))   # (the floor's contact shade)
    px = np.stack([v * tint[0], v * tint[1], v * tint[2]], -1)
    return np.clip(np.round(px), 0, 255).astype('u1')


RIGID = ('EditRigidObj', 'ExplodeObject', 'Door', 'Building', 'GenericTBA')
HELD = ('EditBoneObj', 'HumanSoldier', 'HumanAI', 'HumanPlayer')


def _model(t):
    from qast import lit
    for a in t.args[6:20]:
        try:
            s_ = lit(a)
        except Exception:
            continue
        if isinstance(s_, str) and s_.endswith('_1'):
            return s_
    return None


def _pid(m, i):
    """parent task id, None at the top (m.parent holds the parent's Call)"""
    from qast import lit
    p = m.parent.get(i)
    if p is None:
        return None
    try:
        q = lit(p.args[0])
    except Exception:
        return None
    return q if isinstance(q, int) and q in m.byid else None


def _covered(m, i):
    """is task i inside a LightmapInfo subtree?"""
    p = _pid(m, i)
    while p is not None:
        if any(m.typ(c) == 'LightmapInfo' for c in _kids(m, p)):
            return True
        p = _pid(m, p)
    return False


def _kids(m, i):
    from qast import lit
    return [lit(a.args[0]) for a in m.byid[i].args if type(a).__name__ == 'Call' and a.name == 'Task_New' and lit(a.args[0]) in m.byid]


def light_trees(m, nid, log=print):
    """give every rigid object outside a LightmapInfo subtree a LightmapInfo beside it. Run after the last object is placed, before m.write"""
    from mission_lib import T
    from qast import lit
    add, solo, apart = set(), [], {}

    def has_air(p):
        return any((m.typ(c) in RIGID and (_model(m.byid[c]) or ' ')[:1] in '67') or has_air(c) for c in _kids(m, p))

    for i in list(m.byid):
        if m.typ(i) not in RIGID or not _model(m.byid[i]) or _covered(m, i) or _model(m.byid[i])[:1] in '67':   # (vehicles and aircraft get no bake: under a LightmapInfo they draw full bright)
            continue
        p = _pid(m, i)
        if p is None or m.typ(p) in ('Static', 'Dynamic'):
            solo.append(i)
        elif has_air(p):                                   # (a LightmapInfo covers the whole subtree: on the mission logic it lit the ending's Hinds full bright)
            apart.setdefault(p, []).append(i)
        else:
            add.add(p)
    for p, ids in apart.items():                           # (these objects move into a box of their own beside the vehicles; one id, not one per object)
        calls = [m.byid[i] for i in ids]
        for c in calls:
            m.byid[p].args.remove(c)
        m.reindex()
        m.add_child(p, T(nid(), 'Container', 'SS lit objects', False, children=calls + [T(nid(), 'LightmapInfo', '', 150, 0.0, 0.0, 0.0, '')]))
    for p in sorted(add):
        m.add_child(p, T(nid(), 'LightmapInfo', '', 150, 0.0, 0.0, 0.0, ''))
    for i in solo:
        m.add_child(i, T(nid(), 'LightmapInfo', '', 150, 0.0, 0.0, 0.0, ''))
    log('ssworld: LightmapInfo added to %d containers, %d lone objects, %d objects boxed apart from vehicles' % (len(add), len(solo), sum(map(len, apart.values()))))


def indoor(K, p):
    """a roof over this spot (m)?"""
    a = np.array(p, float) * 4096.0 + (0, 0, 1.6 * 4096)
    return K.blocked(a, a + (0, 0, 40.0 * 4096), pad=0.02 * 4096)


def rescale(R, ids, target, log=print, cap=None, floor=None):
    """pull whole instances to one lightmap mean (their inner gradients stay)"""
    import prefab
    by = {}
    for n in R.names():
        mm = prefab.LM_RE.match(n)
        if mm and int(mm.group(1)) in ids:
            by.setdefault(int(mm.group(1)), []).append((n, int(mm.group(4))))
    for i, L in sorted(by.items()):
        v = []
        for n, lod in L:
            if lod == 1:
                b = R.get(n); w, h = struct.unpack_from('<HH', b, 108)
                v.append(np.frombuffer(b, 'u1', w * h * 4, 112).reshape(-1, 4)[:, :3].astype(float))
        q = np.concatenate(v).mean(1)
        k = target / max(float(np.median(q[q > 8.0])) if (q > 8.0).any() else 1.0, 1.0)   # (the lit texels only: half of these maps is unused black)
        for n, lod in L:
            j = R.index[n]; b = bytearray(R.chunks[j][1]); w, h = struct.unpack_from('<HH', b, 108)
            a = np.frombuffer(bytes(b[112:112 + w * h * 4]), 'u1').reshape(-1, 4).astype(float)
            a[:, :3] = a[:, :3] * k
            if cap is not None:                            # (a soft ceiling: the lit strips and pale concrete come down, the shadows stay)
                a[:, :3] = np.where(a[:, :3] > cap, cap + (a[:, :3] - cap) * 0.3, a[:, :3])
            if floor is not None:                          # (owner 82: stretches of the sewer were pure black beside a lamp)
                a[:, :3] = np.where(a[:, :3] < floor, floor + (a[:, :3] - floor) * 0.35, a[:, :3])
            a[:, :3] = np.clip(a[:, :3], 0, 255)
            b[112:112 + w * h * 4] = np.round(a).astype('u1').tobytes()
            R.chunks[j] = (R.chunks[j][0], bytes(b), R.chunks[j][2])
    log('ssworld: %d instances pulled to mean %.0f' % (len(by), target))


# rooms emptied of the map's crates: the wall's low-res bake still holds their dark patches (1 texel = about 1 m, so a patch reads as a smudge). (building, x0, y0, x1, y1, z0, z1)
HEAL = [(4066, 74.7, 104.2, 81.3, 114.7, 0.0, 5.6), (3135, 132.9, 243.0, 143.6, 249.8, -7.4, -1.7), (4058, 146.0, 103.5, 152.0, 108.2, -0.5, 1.2),
        (3573, 147.5, 213.0, 157.0, 228.0, -8.0, -6.5), (3573, 157.0, 213.0, 169.0, 224.5, -8.0, -6.5)]   # (judge E10 11-12: truck 3090, removed 10-31, left its shadow on the north store's floor)


def heal(R, lv, m, log=print):
    """dark texels of a room's walls and floor take the room's median, in every mesh of the building (rooms live in child meshes): only LOD 1, which is what shows up close"""
    import prefab, mefmesh, navgen
    from qast import lit
    n = 0
    for bid, x0, y0, x1, y1, z0, z1 in HEAL:
        t = m.byid[bid]
        md = _model(t)
        nodes = prefab.lightmap_nodes(lv, md)
        o = np.array([float(lit(t.args[k])) / 4096.0 for k in (3, 4, 5)])
        Rm = navgen.rot(*[float(lit(t.args[k])) for k in (6, 7, 8)])
        root = mefmesh.Mef.read(lv.find_resource('LOCAL:models/%s.mef' % lv.find_vnam(md).entry(md)[0], 'models')[1])
        off = {x['name'].split(bytes(1))[0].decode('latin1'): np.array(x['pos'], float) / 4096.0 for x in root.get('ATTA')}
        room = []
        olms = {}                                          # (node numbers do not follow the attachment order: a mesh finds its bake by the lightmap's size)
        pre = 'LOCAL:lightmaps/%04d_' % bid
        for nm_ in R.names():
            if nm_.startswith(pre) and nm_.endswith('_1.olm'):
                olms.setdefault(struct.unpack_from('<HH', R.get(nm_), 108), []).append(nm_)
        for vn in sorted(set(nodes)):
            L = lv.find_vnam(vn)
            if L is None:
                continue
            me = mefmesh.Mef.read(lv.find_resource('LOCAL:models/%s.mef' % L.entry(vn)[0], 'models')[1])
            if me.type != 3 or me.get('PMTL') is None or len(me.get('PMTL')) != 1:
                continue
            w, h, N, P, M = texel_maps(mefmesh.RigidModel.from_mef(me))
            if w * h < 100 or len(olms.get((w, h), ())) != 1:
                continue
            name = olms[(w, h)][0]
            pw = (P / 4096.0 + off.get(vn, 0.0)) @ Rm.T + o
            sel = M & (pw[..., 0] > x0) & (pw[..., 0] < x1) & (pw[..., 1] > y0) & (pw[..., 1] < y1) & (pw[..., 2] > z0) & (pw[..., 2] < z1)
            if not sel.any():
                continue
            j = R.index[name]
            b = bytearray(R.chunks[j][1])
            if struct.unpack_from('<HH', b, 108) != (w, h):
                continue
            a_ = np.frombuffer(bytes(b[112:112 + w * h * 4]), 'u1').reshape(h, w, 4).copy()
            room.append((j, b, a_, sel, w, h))
        if not room:
            continue
        med = np.median(np.concatenate([a_[..., :3][sel] for j, b, a_, sel, w, h in room]), axis=0)
        for j, b, a_, sel, w, h in room:
            low = sel & (a_[..., :3].mean(2) < 0.82 * float(med.mean()))
            a_[..., :3][low] = np.round(med).astype('u1')
            b[112:112 + w * h * 4] = a_.tobytes()
            R.chunks[j] = (R.chunks[j][0], bytes(b), R.chunks[j][2])
            n += int(low.sum())
    log('ssworld: %d dark wall texels healed' % n)


def relight(m, out, K, log=print):
    """after the overlay is in <out>/overlay: an .olm for every lightmapped object that has none, one light level for the sewer's pieces"""
    import prefab, mefmesh, navgen
    from qast import lit
    path = os.path.join(out, 'overlay', 'lightmaps', 'lightmaps.res')
    R = prefab.Res(path)
    have = {int(prefab.LM_RE.match(n).group(1)) for n in R.names() if prefab.LM_RE.match(n)}
    have -= set(getattr(m, 'reused', ()))                  # (a reused id still has the removed crate's .olm: a new object takes its own)
    lv = prefab.Level(os.path.join(prefab.GAME, 'MISSIONS', 'multiplayer', 'sandstorm'), files_dir=os.path.join(out, 'overlay'))
    maps, types, n_new, n_skip, rows = {}, {}, 0, [], []
    for i in sorted(m.byid):
        t = m.byid[i]
        if m.typ(i) not in RIGID or i in have:
            continue
        md = _model(t)
        if not md or md[:1] in '67' or not _covered_after(m, i):      # (vehicles and aircraft move: a bake would stay behind)
            continue
        got = False
        for lod in range(1, 6):
            vn = prefab.lod_name(md, lod)
            if vn not in maps:
                maps[vn] = None
                L = lv.find_vnam(vn)
                if L is not None:
                    b = lv.find_resource('LOCAL:models/%s.mef' % L.entry(vn)[0], 'models')[1]
                    me = mefmesh.Mef.read(b) if b else None
                    if me is not None and me.type == 3 and me.get('PMTL') is not None and len(me.get('PMTL')) == 1:
                        maps[vn] = texel_maps(mefmesh.RigidModel.from_mef(me))
                    elif me is not None and me.type == 3:
                        n_skip.append(vn)
            wm = maps[vn]
            if wm is None:
                continue
            o = np.array([float(lit(t.args[k])) / 4096.0 for k in (3, 4, 5)])
            A = [float(lit(t.args[k])) for k in (6, 7, 8)]
            Rm = navgen.rot(*A)
            z = zone_at(o)
            if z is not None:
                lvl, tint, outd = z[7], z[8], False
            elif indoor(K, o):
                lvl, tint, outd = 78.0, (1.0, 0.96, 0.9), False
            else:
                lvl, tint, outd = 92.0, (1.0, 0.96, 0.88), True
            if md in MODEL_LEVEL:
                lvl, tint = MODEL_LEVEL[md]
            if md.startswith('wissw_r'):
                import ssrooms as RM
                lvl = RM.ROOM_LEVEL.get(md[7:-2], lvl)
            if m.typ(i) == 'GenericTBA':                   # (a terminal's screen is its own light)
                lvl *= 1.35
            k_ = 'LOCAL:lightmaps/%04d_0000_%d.olm' % (i, lod)
            if k_ in R.index:                              # (a reused id)
                R.chunks[R.index[k_]] = (R.chunks[R.index[k_]][0], make_olm(bake(wm, Rm, o, lvl, tint, outd)), R.chunks[R.index[k_]][2])
            else:
                R.add(k_, make_olm(bake(wm, Rm, o, lvl, tint, outd)))
            got = True
            if lod == 1:
                rows.append((i, md, z[0] if z else ('out' if outd else 'in'), lvl))
        n_new += got
    sew = {i for i in m.byid if m.typ(i) == 'Building' and str(lit(m.byid[i].args[2])).lower().startswith('sewer') and 'lower' not in str(lit(m.byid[i].args[2])).lower() and float(lit(m.byid[i].args[5])) < -15 * 4096}
    sew |= {i for i in m.byid if m.typ(i) == 'Building' and _model(m.byid[i]) in ('432_27_1', '432_28_1', '432_29_1', '432_30_1')}
    rescale(R, sew, 46.0, cap=62.0, floor=30.0)                        # (one median over all the pieces, the lit strips under a soft ceiling)
    n_p = 0
    for i in sew:                                          # (the junction's and the entrance's arch nodes: pale concrete, it reads twice as bright as the brick under the same light)
        if _model(m.byid[i]) in ('432_28_1', '432_30_1'):
            for n_ in R.names():
                mm = prefab.LM_RE.match(n_)
                if mm and int(mm.group(1)) == i and int(mm.group(3)) >= 3:
                    j = R.index[n_]; b = bytearray(R.chunks[j][1]); w, h = struct.unpack_from('<HH', b, 108)
                    q = np.frombuffer(bytes(b[112:112 + w * h * 4]), 'u1').reshape(-1, 4).astype(float)
                    q[:, :3] *= 0.6
                    b[112:112 + w * h * 4] = np.round(q).astype('u1').tobytes()
                    R.chunks[j] = (R.chunks[j][0], bytes(b), R.chunks[j][2]); n_p += 1
    log('ssworld: %d arch lightmaps dimmed' % n_p)
    heal(R, lv, m)
    open(path, 'wb').write(R.data())
    with open(os.path.join(out, 'overlay', 'ssworld_light.txt'), 'w') as f:
        for r_ in rows:
            f.write(('%d %s %s %.0f' % r_) + chr(10))
    log('ssworld: %d objects lit by new .olm, %d models with several lightmaps skipped %s' % (n_new, len(set(n_skip)), sorted(set(n_skip))[:12]))
    retex_logo(out, log)


def logo_rgb(rgb):
    """409_21_1 (256 x 256 brushed steel, the firm's name in rows 30-85) -> the same steel with an Iraqi air force crest: a roundel with wings, the name in naskh"""
    from PIL import Image, ImageDraw
    import ssposters as SP
    a = np.array(rgb, np.float32).copy()
    H, W = a.shape[:2]
    band = a[150:150 + 70].copy()                          # (a stretch of plain steel over the old name, its seams blended)
    a[24:94] = band
    for k in range(6):
        f = (k + 1) / 7.0
        a[24 + k] = a[24 + k] * f + rgb[24 + k] * (1 - f)
        a[93 - k] = a[93 - k] * f + rgb[93 - k] * (1 - f)
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype('u1'))
    d = ImageDraw.Draw(im)
    cx, cy, r = 44, 59, 30
    d.polygon([(cx - 6, cy - 4), (cx - 40, cy - 16), (cx - 34, cy - 6), (cx - 40, cy + 2), (cx - 30, cy + 6), (cx - 6, cy + 6)], fill=(40, 46, 70))     # wings
    d.polygon([(cx + 6, cy - 4), (cx + 40, cy - 16), (cx + 34, cy - 6), (cx + 40, cy + 2), (cx + 30, cy + 6), (cx + 6, cy + 6)], fill=(40, 46, 70))
    d.ellipse([cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10], fill=(30, 110, 60), outline=(40, 46, 70), width=2)
    t = [(cx, cy - 11), (cx - 10, cy + 8), (cx + 10, cy + 8)]
    d.polygon(t, fill=(200, 30, 30))
    d.polygon([(cx, cy - 5), (cx - 5, cy + 5), (cx + 5, cy + 5)], fill=(240, 240, 236))
    SP._center(d, 165, 46, SP._ar('القوة الجوية العراقية'), SP.F_CALLIG, 168, 46, (40, 46, 70))
    return np.asarray(im, np.float32) / 255.0


def retex_logo(out, log=print):
    """judge E12 11-12: the lobby's logo wall, in place in the overlay's own bank (only the admin building uses 409_21_1)"""
    import ilff, altex
    p = os.path.join(out, 'overlay', 'textures', 'sandstorm.res')
    if not os.path.exists(p):
        return
    form, ch, hdr = ilff.read(open(p, 'rb').read())
    k = next((i for i, (t, d, a) in enumerate(ch) if t == b'NAME' and d.rstrip(bytes(1)) == b'LOCAL:textures/409_21_1.tex'), None)
    if k is None:
        log('ssworld: 409_21_1 not in the overlay bank, logo left'); return
    b = ch[k + 1][1]
    rgb, al, _ = altex.read(b)
    ch[k + 1] = (b'BODY', altex.write_like(b, logo_rgb(rgb), al), ch[k + 1][2])
    tmp = p + '.logo.tmp'
    open(tmp, 'wb').write(ilff.write(form, ch, hdr[1] or 4))
    os.replace(tmp, p)
    log('ssworld: admin lobby logo 409_21_1 re-skinned (Iraqi air force crest)')


def _covered_after(m, i):
    return _covered(m, i) or any(m.typ(c) == 'LightmapInfo' for c in _kids(m, i))


# ---------------------------------------------------------------------------------------------- vertex-lit originals -> lightmapped clones
LM_W, LM_H = 24, 16                                        # six charts, one per face direction, 8 x 8 texels each
_CLONES = {}


def lightmapped_clone(rm):
    """a type-0 RigidModel as type 3: same mesh, a box-unwrapped lightmap. Faces split per direction; charts may overlap, the bake reads only direction and height"""
    import mefmesh
    allp = np.concatenate([g.pos for g in rm.groups])
    lo, hi = allp.min(0), allp.max(0)
    sz = np.maximum(hi - lo, 1e-3)
    out = []
    for g in rm.groups:
        P, U, L, T_ = [], [], [], []
        for t in g.tris:
            a, b, c = g.pos[t]
            n = -np.cross(b - a, c - a)
            k = int(np.argmax(np.abs(n)))
            chart = k * 2 + (1 if n[k] < 0 else 0)
            i_, j_ = [q for q in range(3) if q != k]
            base = len(P)
            for vi in t:
                p = g.pos[vi]
                uu = (p[i_] - lo[i_]) / sz[i_]; vv = (p[j_] - lo[j_]) / sz[j_]
                cx, cy = chart % 3, chart // 3
                L.append(((cx + 0.12 + 0.76 * uu) / 3.0, (cy + 0.12 + 0.76 * vv) / 2.0))
                P.append(p); U.append(g.uv[vi])
            T_.append((base, base + 1, base + 2))
        out.append(mefmesh.Group(P, U, T_, g.tex, flags=g.flags, lmuv=L, lightmap=0, name=g.name))
    r2 = mefmesh.RigidModel(out, rm.coll, hsem=rm.hsem, atta=rm.atta, magic=rm.magic, portals=rm.portals, glows=rm.glows, typ=3,
                            pmtl=np.array([(LM_W, LM_H, 0)], mefmesh.PMTL_DT), d3dr_tail=np.zeros(6, '<u4'), extra=rm.extra)
    return r2


DIM_RIGID = {'205_36_1': 0.3, '205_35_1': 0.3, '337_11_1': 0.42}


def lit_here(K, o):
    """should the thing at o (m) sit in baked light? any zone, or a roof over it"""
    return zone_at(o) is not None or indoor(K, o)


def indoorize(m, ovl, K, skip_models=(), log=print):
    """indoor vertex-lit furniture takes full sun whatever is overhead: swap it for a lightmapped clone (see relight). Before lodfix and m.write"""
    import prefab, mefmesh, mtp, ilff
    from qast import lit
    mp, mr, mt = os.path.join(ovl, 'sandstorm.mtp'), os.path.join(ovl, 'models', 'sandstorm.res'), os.path.join(ovl, 'textures', 'sandstorm.res')
    mm = mtp.read(mp)
    form, ch, hdr = ilff.read(open(mr, 'rb').read())
    have = {d.rstrip(bytes(1)).decode('latin1').lower(): k + 1 for k, (t, d, a) in enumerate(ch) if t == b'NAME'}
    tform, tch, thdr = ilff.read(open(mt, 'rb').read())
    thave = {d.rstrip(bytes(1)).decode('latin1').lower() for t, d, a in tch if t == b'NAME'}
    lv = prefab.Level(os.path.join(prefab.GAME, 'MISSIONS', 'multiplayer', 'sandstorm'), files_dir=ovl)
    made, n_sw, off, n_tex = {}, 0, [], [0]

    def gtt_of(tname, L):
        """the manifest's texture row for a name; a texture of the common bank is copied in"""
        if tname not in mm['TEXF']:
            key = 'LOCAL:textures/%s.tex' % tname
            if key.lower() not in thave:
                body = L.textures.get(key) if L is not None else None
                if body is None:
                    body = lv.find_resource(key, 'textures')[1]
                if body is None:
                    raise KeyError(tname)
                tch.append((b'NAME', key.encode('latin1') + bytes(1), 4)); tch.append((b'BODY', body, 4))
                thave.add(key.lower()); n_tex[0] += 1
            mm['TEXF'].append(tname); mm['GTT'].append([len(mm['TEXF']) - 1, -1])
            return len(mm['GTT']) - 1
        ti = mm['TEXF'].index(tname)
        return next(k for k, (t_, pl) in enumerate(mm['GTT']) if t_ == ti)

    def clone(md):
        if md in made:
            return made[md]
        made[md] = None
        new1 = 'wi' + md
        if len(new1) > 15:
            new1 = 'wi%03d_1' % len(made)
        names = []
        for lod in range(1, 6):
            vn = md[:-1] + str(lod)
            if vn in mm['VNAM']:
                mi, gtts = mm['INST'][mm['VNAM'].index(vn)]
                nm = mm['MODS'][mi]
                key = ('LOCAL:models/%s.mef' % nm).lower()
                b = ch[have[key]][1] if key in have else lv.find_resource('LOCAL:models/%s.mef' % nm, 'models')[1]
                L_, tx = None, None
            else:
                L_ = lv.find_vnam(vn)
                if L_ is None:
                    break
                try:
                    nm, tx = L_.entry(vn)
                except NotImplementedError:
                    off.append(vn)
                    break
                b = lv.find_resource('LOCAL:models/%s.mef' % nm, 'models')[1]
                gtts = None
            if b is None:
                break
            me = mefmesh.Mef.read(b)
            if me.type != 0:
                break
            rm = mefmesh.RigidModel.from_mef(me)
            if sum(len(g.tris) for g in rm.groups) < 6:            # (a single quad as a lightmapped mesh crashes D3D8.dll+0x7c45e on the first frame: stays vertex-lit)
                off.append(vn)
                break
            data = lightmapped_clone(rm).to_mef().write()
            if gtts is None:
                gtts = [gtt_of(t_, L_) for t_ in tx]
            nv = new1[:-1] + str(lod)
            ch.append((b'NAME', ('LOCAL:models/%s.mef' % nv).encode('latin1') + bytes(1), 4))
            ch.append((b'BODY', data, 4))
            mm['MODS'].append(nv); mm['VNAM'].append(nv); mm['INST'].append([len(mm['MODS']) - 1, list(gtts)])
            names.append(nv)
        if names:
            made[md] = new1
            m.models |= {n.lower() + '.mef' for n in names}
            _CLONES.update({n: md for n in names})
        return made[md]

    for i in sorted(m.byid):
        if m.typ(i) != 'EditRigidObj':
            continue
        t = m.byid[i]
        md = lit(t.args[9])
        if not isinstance(md, str) or (md[:1] not in '23' and not md.startswith(('ssw_', 'sp_'))) or md in skip_models or not md.endswith('_1'):
            continue
        o = [float(lit(t.args[k])) / 4096.0 for k in (3, 4, 5)]
        if not lit_here(K, o):
            continue
        new = clone(md)
        if new:
            m.set(i, 9, new); n_sw += 1
    # a GenericTBA takes no lightmap (it is not enumerated): terminals draw full bright. Same mesh, its texture darkened: the case sits in the room, the screen stays readable
    import igitex, wreck
    tb = {}
    def dim(md, k=None):
        if md in tb:
            return tb[md]
        names = []
        for lod in range(1, 6):
            vn = md[:-1] + str(lod)
            L_ = lv.find_vnam(vn)
            if L_ is None:
                break
            nm, tx = L_.entry(vn)
            ng = []
            for t_ in tx:
                nt = 'wd' + t_
                if nt not in mm['TEXF']:
                    body = lv.find_resource('LOCAL:textures/%s.tex' % t_, 'textures')[1]
                    im = np.array(igitex.decode(body), np.float32)
                    lum_ = im[..., :3].mean(2, keepdims=True)  # (under a LightmapInfo a TBA draws on a blank, doubled lightmap: in rig frames the case reads about 3.7 x its texture: 0.13 puts it at the room's level; the dark screen stays lit)
                    im[..., :3] *= (0.13 + 0.47 * (lum_ < 0.5)) if k is None else k
                    key = 'LOCAL:textures/%s.tex' % nt
                    tch.append((b'NAME', key.encode('latin1') + bytes(1), 4)); tch.append((b'BODY', wreck.tex_mode2(im), 4))
                    n_tex[0] += 1
                    mm['TEXF'].append(nt); mm['GTT'].append([len(mm['TEXF']) - 1, -1])
                ng.append(next(k for k, (t2, pl) in enumerate(mm['GTT']) if t2 == mm['TEXF'].index(nt)))
            nv = 'wd' + vn
            mm['VNAM'].append(nv)
            if nm in mm['MODS']:
                mm['INST'].append([mm['MODS'].index(nm), ng])
            else:
                b = lv.find_resource('LOCAL:models/%s.mef' % nm, 'models')[1]
                ch.append((b'NAME', ('LOCAL:models/%s.mef' % nv).encode('latin1') + bytes(1), 4)); ch.append((b'BODY', b, 4))
                mm['MODS'].append(nv); mm['INST'].append([len(mm['MODS']) - 1, ng])
            names.append(nv)
        tb[md] = 'wd' + md
        m.models |= {n.lower() + '.mef' for n in names}
        _CLONES.update({n: md for n in names})
        return tb[md]

    for i in sorted(m.byid):
        if m.typ(i) != 'GenericTBA':
            continue
        for k, a_ in enumerate(m.byid[i].args):            # (the model before and after the hack: the two must match)
            if k >= 6 and type(a_).__name__ == 'Str' and lit(a_) in ('200_01_1', '200_03_1'):
                m.set(i, k, dim(lit(a_)))
    for i in sorted(m.byid):                               # (these read bright against a dark room whatever their bake: lab trolleys, the yellow generator cabinets. Under a roof only)
        if m.typ(i) == 'EditRigidObj' and lit(m.byid[i].args[9]) in DIM_RIGID and lit_here(K, [float(lit(m.byid[i].args[k_])) / 4096.0 for k_ in (3, 4, 5)]):
            m.set(i, 9, dim(lit(m.byid[i].args[9]), DIM_RIGID[lit(m.byid[i].args[9])]))
    open(mr, 'wb').write(ilff.write(form, ch, hdr[1] or 4))
    if n_tex[0]:
        open(mt, 'wb').write(ilff.write(tform, tch, thdr[1] or 4))
    open(mp, 'wb').write(mtp.write(mm))
    log('ssworld: %d objects on %d lightmapped clones (%s), %d textures copied; left vertex-lit: %s' % (n_sw, sum(1 for v in made.values() if v), ' '.join(sorted(v for v in made.values() if v))[:300], n_tex[0], off[:12]))


def lod_rows():
    return {n: [300.0, 600.0, 900.0, 1200.0, 1500.0] for n in _CLONES}


# ---------------------------------------------------------------------------------------------- rooms (tools/ssrooms.py)
FLOOR_PICKS = ('medipack storage house', 'medipack sewer', 'medipack admin')     # (the old pickups that lay on floors: they move to cupboards and tables)
REMOVE = (3045, 3010, 3009, 2972, 3058)                                # (crates of the MP map left in the middle of what are now rooms)
REMOVE_LATE = (3665, 3134, 2952, 2854, 3081, 3082, 3083, 3084) + tuple(range(2835, 2843)) + tuple(range(2844, 2854))   # (judge E11 11-12: 3081-3084, the MP map's crates up on the north store's girders)     # (judge R05: the server room's shelves of cartons; 2843 stays on the desk)
REMOVE_NAMED = ('SS broker room 260_02_1', 'SS broker room 330_01_1', 'SS broker room 330_02_1')        # (the crates in Kral's office: it is an office now)


def add_models(X, lib):
    """before lib.build / X.finish: each room is ONE model (its furniture merged), so a room costs one object, one lightmap and one draw per texture"""
    import ssrooms as RM
    for n, fn in RM.TEX.items():
        lib.texture(n, fn)
    hung = {h_[0] for h_ in RM.HANG + RM.HANG_AT} | {'ssw_fak_1', 'ssw_arm_1', 'ssw_rod_1'}
    if WATER:
        lib.texture('ssw_swat', tx_sewer_water, alpha=True)
        _wm = sewer_water_model(X.m)
        lib.add('ssw_water_1', lambda: _wm, ['ssw_swat'], lod_like='406_68_1')      # (the rest only feed merged(): the engine stops at MTP_nLODVirModel >= 600, 'fatal error' at 80 % of the load)
    for n, (fn, slots) in RM.MODELS.items():
        if n in hung:
            lib.add(n, fn, slots, lod_like='406_68_1')
    for nm, fn_ in RM.ROOMS + RM.LATE:
        items = fn_()
        mdl, slots, o = RM.merged(items)
        RM.ROOM_AT[nm] = o
        for t_ in slots:
            if t_ not in lib.textures:
                lib.texture(t_, RM.src_texture(t_))
        lib.add('ssw_r%s_1' % nm, (lambda m_: (lambda: m_))(mdl), slots, lod_like='406_68_1')


def rooms(m, nid, T, parent):
    """furniture, before navgen: the graph walks round it"""
    import ssrooms as RM
    for i in REMOVE:
        if i in m.byid:
            m.remove(i)
    c = nid()
    m.add_child(parent, T(c, 'Container', 'SS rooms', False))
    n = 0
    for nm, fn_ in RM.ROOMS:
        x, y, z = RM.ROOM_AT[nm]
        m.add_child(c, T(nid(), 'EditRigidObj', 'SS room ' + nm, x * 4096.0, y * 4096.0, z * 4096.0, 0.0, 0.0, 0.0, 'ssw_r%s_1' % nm, 5, False, False))
        n += len(fn_())
    print('ssworld: %d rooms, %d pieces merged, %d rigid objects' % (len(RM.ROOMS), n, len(RM.ROOMS)))


def trim(what=''):
    """give freed memory back to the system: the node's builds run in 24 GB and stand near it"""
    import gc, ctypes
    gc.collect()
    try:
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except OSError:
        pass                                               # (Windows)
    if os.environ.get('SS_MEMLOG'):
        print('TRIM', what, int(open('/proc/self/statm').read().split()[1]) * 4096 // 2 ** 20, 'MB', flush=True)


def pins():
    import ssrooms as RM
    return RM


# the cameras with nothing behind them, read from the render meshes (work/sandstorm/world/mounts.py, axes.py); the others sit on a wall, their bracket spans 0.67 m
CAM_MOUNT = {'SS feed camera generators': 'mast', 'SS feed camera east block': 'mast', 'SS feed camera chip': 'mast', 'SS feed camera hall': 'rod down', 3736: 'arm south',
             'SS feed camera console': 'rod up'}       # (judge R07: the console camera hung in front of the window. The silo one sits 7 cm off the north wall: its mast stood through the catwalk and hung in the air, item 116)


# ---------------------------------------------------------------------------------------------- owner 95: sewer water
WATER_FLOOR = (-20.62, -20.54)                             # (the channel floor of the sewer pieces 432_27..30 and their children: 197 up-facing collision triangles)
WATER_DEPTH = 0.3                                          # (shin deep; the side walks stand 0.75 m over it)
WATER_MAT = 2                                              # (MATERIAL/material.qvm: 2 = 'Water', footsteps watermix_w_01..06)
_WATER = {}


def tx_sewer_water():
    """dark murky water: brown-green depth, slow ripple bands, lighter scum drifting, a faint sheen. Alpha 0.62 (it draws near opaque under the lightmap: murky)"""
    from PIL import Image
    n = 256
    rng = np.random.default_rng(95)

    def noise(o):
        return np.asarray(Image.fromarray((rng.random((o, o)) * 255).astype('u1')).resize((n, n), Image.BICUBIC), np.float32) / 255.0
    f = noise(6) * 0.5 + noise(16) * 0.3 + noise(48) * 0.2
    y, x = np.mgrid[0:n, 0:n] / n
    rip = 0.5 + 0.5 * np.sin((x * 9.0 + f * 2.2) * 2 * np.pi) * np.sin((y * 3.0 + f * 1.3) * 2 * np.pi)
    scum = np.clip((noise(20) - 0.62) * 3.0, 0, 1) * np.clip((noise(64) - 0.3) * 2.0, 0, 1)
    v = 0.55 + 0.25 * f + 0.2 * rip
    a = np.zeros((n, n, 4), np.float32)
    a[..., 0] = 0.20 * v + 0.16 * scum
    a[..., 1] = 0.23 * v + 0.15 * scum
    a[..., 2] = 0.15 * v + 0.09 * scum
    a[..., 3] = 0.62
    return np.clip(a, 0, 1)


def sewer_water_model(m):
    """the water: the channel floor's own triangles lifted WATER_DEPTH (render, alpha, no collision of its own) and the same triangles 1 cm over the floor as
    collision of material Water, so a step splashes. That floor layer changes no height a man walks at and is placed after the graphs"""
    import glob, mef as meflib, mefmesh, navgen, prefab
    import modelkit as MK, biprefabs as BP
    from qast import lit
    G = os.path.join(prefab.GAME, 'MISSIONS', 'multiplayer')
    L = meflib.ModelLib(glob.glob(os.path.join(G, 'sandstorm', 'models', '*.res')) + glob.glob(os.path.join(G, 'common', 'models', '*.res')) + [os.path.join(prefab.GAME, 'COMMON', 'models', 'common.res')])

    def tree(n, Rm, t, out):
        for c in (L.collision(n) or []):
            P = np.array(c[0], float); F = np.array(c[1], int)
            if len(P):
                out.append((P[F] / 4096.0) @ Rm.T + t)
        for k, tt, RR in L.attached(n):
            tree(k, Rm @ np.asarray(RR), t + Rm @ (np.asarray(tt) / 4096.0), out)
    tris = []
    for i in sorted(m.byid):
        if m.typ(i) != 'Building':
            continue
        t = m.byid[i]
        md = _model(t)
        p = np.array([float(lit(t.args[k])) / 4096.0 for k in (3, 4, 5)])
        if not md or not (-24.0 < p[2] < -17.0) or not md.startswith('432_'):
            continue
        tree(md.lower(), navgen.rot(*[float(lit(t.args[k])) for k in (6, 7, 8)]), p, tris)
    T = np.concatenate(tris)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    z = T[:, :, 2].mean(1)
    U = T[(n[:, 2] < -0.95 * np.linalg.norm(n, axis=1)) & (z > WATER_FLOOR[0]) & (z < WATER_FLOOR[1])]
    o = U.reshape(-1, 3).mean(0)
    o = np.array([round(o[0], 2), round(o[1], 2), round(float(U[:, :, 2].min()), 2)])
    W = U - o
    top = W.copy(); top[:, :, 2] += WATER_DEPTH
    P = top.reshape(-1, 3) * 4096.0
    uv = (U.reshape(-1, 3)[:, :2] / 1.8)
    tr = np.arange(len(P)).reshape(-1, 3)
    g = mefmesh.Group(P, uv, tr, 0, flags=MK.GLASS, nrm=np.tile((0.0, 0.0, 1.0), (len(P), 1)))
    flo = W.copy(); flo[:, :, 2] += 0.01
    C = flo.reshape(-1, 3) * 4096.0
    m0 = np.zeros(1, mefmesh.TAMC_DT); m0[0] = (0, 0xFFFF, 0, WATER_MAT)
    m1 = np.zeros(1, mefmesh.TAMC_DT); m1[0] = (1065353216, 0xFFFFFFFF, 0, 21)
    coll = [mefmesh.CollMesh(C, tr, np.zeros(len(tr), np.int64), m0), mefmesh.CollMesh(C, tr, np.zeros(len(tr), np.int64), m1)]
    rm = mefmesh.RigidModel([g], coll, hsem=BP._hsem(), typ=0)
    _WATER['at'] = tuple(float(v) for v in o)
    _WATER['tris'] = len(tr)
    return rm.to_mef(recompute_spheres=True, recompute_centres=True, rebuild_trees=True)


def water(m, nid, T, parent, log=print):
    if 'at' not in _WATER:
        return
    x, y, z = _WATER['at']
    m.add_child(parent, T(nid(), 'EditRigidObj', 'SS sewer water', x * 4096.0, y * 4096.0, z * 4096.0, 0.0, 0.0, 0.0, 'ssw_water_1', 5, False, False))
    log('ssworld: sewer water, %d triangles at %.2f m (floor %.2f), floor layer of material %d' % (_WATER['tris'], z + WATER_DEPTH, z, WATER_MAT))


def cameras(m, nid, T, parent, log=print):
    """owner 82: every SCamera on the dark mesh (they draw far over their texture), and the floating ones on something real. A camera itself does not move: the cutscene feeds hang on it"""
    from qast import lit
    import ssbase
    n, done = 0, []
    for i in m.find('SCamera'):
        t = m.byid[i]
        if ssbase.GUNROOM:
            for k, a_, b_ in ((7, '313_07_1', 'ss_cam7_1'), (11, '313_06_1', 'ss_cam6_1'), (12, '313_06_1', 'ss_cam6_1')):
                if lit(t.args[k]) == a_:
                    m.set(i, k, b_)
            n += 1
        how = CAM_MOUNT.get(str(lit(t.args[2])), CAM_MOUNT.get(i))
        if not how:
            continue
        x, y, z = [float(lit(t.args[k])) for k in (3, 4, 5)]
        md, dz, g = {'mast': ('ss_pole_1', -8.185, 0.0), 'rod down': ('ssw_rod_1', -1.3, 0.0), 'rod up': ('ssw_rod_1', 0.0, 0.0), 'arm south': ('ssw_arm_1', 0.0, math.pi)}[how]
        m.add_child(parent, T(nid(), 'EditRigidObj', 'SS camera mount %d' % i, x, y, z + dz * 4096.0, 0.0, 0.0, g, md, 5, False, False))
        done.append(how)
    log('ssworld: %d cameras on the dark mesh; %d mounts %s' % (n, len(done), done))


def fix_racks(m):
    """the garrison armoury's wall racks stood on the floor with their backs to the room: they hang 1.37 m up, back to the south wall (L24 3759)"""
    import ssrooms as RM
    from qast import lit
    n = 0
    for i in m.find('EditRigidObj', 'SS garrison prop'):
        if lit(m.byid[i].args[9]) == '231_14_1':
            m.set(i, 4, 199.2 * 4096.0); m.set(i, 5, (RM.F_BASE + RM.RACK_Z) * 4096.0); m.set(i, 8, math.pi)
            n += 1
    print('ssworld: %d garrison racks hung' % n)


def pick_ups(m, nid, T, pick):
    trim('after the graphs')
    import ssrooms as RM
    for nm, wid, x, y, z, a, b, g in RM.pickups():
        m.add_child(pick, T(nid(), 'GunPickup', 'SS ' + nm, x * 4096.0, y * 4096.0, z * 4096.0 + 40.0, float(a), float(b), float(g), wid, ''))


def square_wall(K, floor_pt, height_m, w, half=0.25, max_m=5.0):
    """S5 11-15 (SS_PROPS 3.3): K.wall_near returns the direction of the winning ray (a multiple of 11.25 degrees), not the wall's
    normal, so plates hung up to 25 degrees skewed. Two more rays parallel to the winning one, `half` m left and right of it, give
    the wall's line; gamma = its normal toward the standing spot. None when a side ray misses or the two depths differ by more than
    0.15 m (a corner, a door frame, furniture): the caller must then name the spot (HANG_AT / FAK_AT)."""
    M = 4096.0
    f = np.array(floor_pt[:3], float)
    a = f + np.array([0.0, 0.0, height_m * M])
    hit = np.array(w[0], float)
    d = hit[:2] - a[:2]
    if np.linalg.norm(d) < 1.0:
        return None
    d /= np.linalg.norm(d)
    side = np.array([-d[1], d[0]])
    pts = []
    for sg in (-1.0, 1.0):
        a2 = a.copy(); a2[:2] += side * sg * half * M
        b2 = a2.copy(); b2[:2] += d * max_m * M
        if not K.blocked(a2, b2, pad=0.01 * M):
            return None
        lo, hi = 0.0, 1.0
        for _ in range(18):
            mid = (lo + hi) / 2
            if K.blocked(a2, a2 + (b2 - a2) * mid, pad=0.01 * M):
                hi = mid
            else:
                lo = mid
        pts.append(a2[:2] + d * lo * max_m * M)
    if abs(float(np.dot(pts[1] - pts[0], d))) > 0.15 * M:
        return None
    t = pts[1] - pts[0]
    n = np.array([-t[1], t[0]]) / max(1.0, np.linalg.norm(t))
    if np.dot(n, d) > 0:                                   # (the normal out of the wall, toward the standing spot)
        n = -n
    c = (pts[0] + pts[1]) / 2 + n * 0.06 * M                 # (6 cm off the wall, as wall_near)
    return (float(c[0]), float(c[1]), float(hit[2])), math.atan2(-n[0], n[1])


def hang(m, K, nid, T, parent, pick):
    """things on walls, after navgen: the wall is found from the floor spot, not guessed"""
    trim('before hang')
    import ssrooms as RM
    for nm in REMOVE_NAMED:                                # (the broker's room is furnished after rooms() ran)
        for i in m.find(name=nm):
            m.remove(i)
    for i in REMOVE_LATE:                                  # (after the graphs: only space is freed)
        if i in m.byid:
            m.remove(i)
    c = nid()
    m.add_child(parent, T(c, 'Container', 'SS late rooms', False))
    for nm, fn_ in RM.LATE:
        x, y, z = RM.ROOM_AT[nm]
        m.add_child(c, T(nid(), 'EditRigidObj', 'SS room ' + nm, x * 4096.0, y * 4096.0, z * 4096.0, 0.0, 0.0, 0.0, 'ssw_r%s_1' % nm, 5, False, False))
    cameras(m, nid, T, parent)
    for i in m.find(name='SS sign ar_ammo'):                 # (judge V03: the wall finder took the parked truck's tarp for the store's wall: on the south wall's face)
        for k, v_ in ((3, 155.5), (4, 87.643), (5, 2.2)):     # (S5 11-15, propaudit look_1 NO_WALL: at x 157.5 the 1.2 m sign hung on a 0.55 m pilaster (x 157.25..157.8,
            m.set(i, k, v_ * 4096.0)                           #  face y 88.01), both ends 0.46-0.50 m off the wall. Now centred between the pilasters at 153.75 and 157.25
        m.set(i, 8, -0.0388)                                   #  on the plain face, which is not square: y 87.704 at x 153.8 to 87.572 at 157.2 (rays) = 87.638 at 155.5,
        #                                                         gamma -0.0388 (its own slope), back 5 mm off it)
    if WATER:
        water(m, nid, T, parent)
    done, miss = [], []
    for md, x, y, fz, h, toward in RM.HANG:
        w = K.wall_near((x * 4096.0, y * 4096.0, fz * 4096.0), height_m=h + 0.2, max_m=5.0, toward=(toward[0] * 4096.0, toward[1] * 4096.0), spread_deg=30)
        w = w and square_wall(K, (x * 4096.0, y * 4096.0, fz * 4096.0), h + 0.2, w)
        if not w:
            miss.append(md); continue
        g = w[1]
        px, py = w[0][0] - math.sin(g) * 0.05 * 4096, w[0][1] + math.cos(g) * 0.05 * 4096
        m.add_child(parent, T(nid(), 'EditRigidObj', 'SS wall ' + md, float(px), float(py), (fz + h) * 4096.0, 0.0, 0.0, float(g), md, 5, False, False))
        done.append(md)
    for md, x, y, z, g in RM.HANG_AT:                      # (underground wall_near fails: the terrain above counts as blocked. Known walls)
        m.add_child(parent, T(nid(), 'EditRigidObj', 'SS wall ' + md, x * 4096.0, y * 4096.0, z * 4096.0, 0.0, 0.0, float(g), md, 5, False, False))
        done.append(md)
    for nm, x, y, fz in RM.FAK + RM.FAK_AT:
        if (nm, x, y, fz) in RM.FAK_AT:
            g = RM.FAK_YAW[nm]
            px, py = x * 4096.0, y * 4096.0
        else:
            w = K.wall_near((x * 4096.0, y * 4096.0, fz * 4096.0), height_m=1.3, max_m=4.0)
            w = w and square_wall(K, (x * 4096.0, y * 4096.0, fz * 4096.0), 1.3, w, max_m=4.0)
            if not w:
                miss.append(nm); continue
            g = w[1]
            px, py = w[0][0] - math.sin(g) * 0.05 * 4096, w[0][1] + math.cos(g) * 0.05 * 4096
        m.add_child(parent, T(nid(), 'EditRigidObj', 'SS first aid ' + nm, float(px), float(py), (fz + 1.0) * 4096.0, 0.0, 0.0, float(g), 'ssw_fak_1', 5, False, False))
        qx, qy = px + (-math.sin(g)) * 0.13 * 4096, py + math.cos(g) * 0.13 * 4096
        m.add_child(pick, T(nid(), 'GunPickup', 'SS medipack ' + nm, float(qx), float(qy), (fz + 1.0 + 0.012) * 4096.0 + 60.0, 0.0, 0.0, float(g) + 1.2, 'WEAPON_ID_MEDIPACK', ''))
        done.append(nm)
    print('ssworld: hung %s; no wall for %s' % (done, miss))


def stands():
    """review stands of every changed room (name, (x, y, feet z)): DBG variant 'wrooms'"""
    return [('armoury door', (77.9, 113.2, 0.31)), ('armoury mid', (77.0, 109.8, 0.31)), ('armoury bench', (76.2, 106.4, 0.31)), ('lobby s', (77.5, 117.0, 0.49)),
            ('clinic west', (134.0, 246.6, -7.01)), ('clinic east', (141.0, 245.4, -7.01)), ('lobby n', (130.5, 246.5, -6.83)),
            ('kral', (176.0, 199.0, -7.21)), ('kral table', (178.5, 195.0, -7.21)), ('store s', (155.0, 100.0, 0.25)), ('store s east', (161.0, 99.5, 0.25)), ('store n', (156.0, 222.0, -7.22)),
            ('sewer junction', (84.0, 127.0, -21.5)), ('sewer bunks', (84.2, 118.0, -21.5)), ('sewer turn', (72.0, 57.0, -21.5)), ('sewer lobby', (75.6, 195.0, -21.5)),
            ('base armoury', (226.5, 205.5, -34.0)), ('mess', (229.0, 243.0, -34.0)), ('control', (256.0, 203.0, -34.0)), ('hall', (240.0, 225.0, -34.0)), ('way', (172.0, 232.4, -14.8))]
