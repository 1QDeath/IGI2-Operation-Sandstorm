"""sshall - Sandstorm v4 (11-03): the missile base's own layout inside the L34 cave shell (tools/ssv4.py). Mission-specific.

New meshes (modelkit, vertex-lit) only where no original exists, each built from originals where possible:
  ss_tel_1 / ss_telr_1  launch truck = the map's own truck 600_00_1 (its mesh + textures, the canvas tarp left off) carrying a
                        missile on an erector (lowered / raised 48 deg for checks)
  ss_bigm_1             the big missile, upright, two side panels open (dark bays) - 18 m (hall B's ceiling is ~23 m)
  ss_gant_1             a steel service gantry beside it with three platforms

Frames: model x = the truck's length (cab at -x, as 600_00_1), z up; the big missile's axis = z.
"""
import math
import numpy as np

M = 4096.0
TEL_SLOTS = ['600_06_1', '600_07_1', '600_03_1', '600_04_1', '600_05_1', '600_02_1', '600_09_1_argb8888', '600_01_1_argb8888',
             'jr_olive', 'jr_misw', 'jr_white']   # (= 600_00_1's groups in order; group 1, the tarp, is left off)
BIGM_SLOTS = ['jr_white', 'jr_dark', 'jr_olive', 'jr_misw']   # (critic rv3: the banded texture read as stacked drums)
GANT_SLOTS = ['jr_olive', 'jr_steel']
BED_Z = 1.42                                               # 600_00_1's bed top (m)
BIGM_H = 24.5                                               # (critic rv10: too small from the hall)


def _orig_parts(orig, keep):
    """600_00_1's render groups -> {group index: part} (normals from the faces, clockwise = front, like _ss_ctr)"""
    lv, r, texs = orig
    out = {}
    for gi, g in enumerate(r.groups):
        if gi not in keep:
            continue
        P = np.asarray(g.pos, float).copy(); Uv = np.asarray(g.uv, float).copy(); Tr = np.asarray(g.tris).copy()
        N = np.zeros_like(P)
        for t in Tr:
            n = -np.cross(P[t[1]] - P[t[0]], P[t[2]] - P[t[0]])
            N[t] += n / (np.linalg.norm(n) + 1e-9)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        out[gi] = (P, Tr, N, Uv)
    return out


def _xform(part, R, t_m):
    P, Tr, N, Uv = part
    return (P @ R.T + np.asarray(t_m) * M, Tr, N @ R.T, Uv)


def _ry(a):                                                # pitch about y (x toward z)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])


def tel_model(orig, raised):
    """the launch truck: 600_00_1 without its tarp (group 1) + an erector frame and a missile (jrmodels parts) lying along x over
    the bed and the cab; raised = the erector pitched up 48 deg about its rear pivot.
    fix1120 (owner 11-20 marks 27, 31-38): the tarp group was also the truck's BED, so the erector and the raised missile stood on bare wheels
    ('resting on the air'), and the rails and the missile ran through the cab roof (2.70 m, measured on 600_00_1). Now: a steel flatbed on the
    chassis, the cradle up on a rear pedestal and a front frame behind the cab so rails and missile clear the roof, saddles under the missile"""
    import modelkit as MK, biprefabs as BP, jrmodels as JM
    box = BP.box_m
    G = _orig_parts(orig, (0, 2, 3, 4, 5, 6, 7))
    body, boost, fins = JM._missile_parts()                # along y, centred
    Rz = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.0]])    # y -> -x: the nose toward the cab (-x)
    PIV_Z = 2.95                                           # (fix1120: was BED_Z + 0.35 = 1.77, 0.9 m under the cab roof; rail bottom now 2.85, roof 2.70)
    pivot = (3.1, 0.0, PIV_Z)
    ang = math.radians(48.0) if raised else 0.0
    Rp = _ry(-ang)                                         # nose (-x) goes up

    def er(part, offs):                                    # erector-frame part: about the pivot
        P, Tr, N, Uv = part
        P2 = (P / M + np.asarray(offs) - pivot) @ Rp.T + pivot
        return (P2 * M, Tr, N @ Rp.T, Uv)
    rail = [box(-3.6 - 3.1, -0.42, -0.10, 0.0, -0.30, 0.05), box(-3.6 - 3.1, 0.30, -0.10, 0.0, 0.42, 0.05),   # (fix1120: rails end over the cab front, not 0.9 m past it)
            box(-0.25, -0.5, -0.30, 0.0, 0.5, 0.05)]
    rail += [box(xr - 0.12, -0.42, -0.10, xr + 0.12, 0.42, 0.16) for xr in (-5.1, -2.5)]   # (fix1120: two saddles: the body (r 0.26) hung 9 cm over nothing between the rails)
    rail = [er(p_, pivot) for p_ in rail]
    mis = [er(_xform(p_, Rz, (0, 0, 0)), (pivot[0] - 3.4, 0.0, pivot[2] + 0.40)) for p_ in body]
    mis2 = [er(_xform(p_, Rz, (0, 0, 0)), (pivot[0] - 3.4, 0.0, pivot[2] + 0.40)) for p_ in boost + fins]
    groups = [(gi, [G[gi]]) for gi in sorted(G)]
    deck = [box(-0.62, -1.18, 1.10, 3.3, 1.18, BED_Z),     # (fix1120 W6: the flatbed the tarp group used to carry, on the wheels (tops 1.06))
            box(-0.62, -1.18, BED_Z, -0.52, 1.18, BED_Z + 0.25)]   # headboard behind the cab
    struts = [box(2.6, -0.5, BED_Z, 3.4, 0.5, PIV_Z)]       # the rear pedestal up to the pivot
    if not raised:                                         # (fix1120: the lowered cradle rests on a frame behind the cab)
        struts += [box(-0.50, yy - 0.06, BED_Z, -0.36, yy + 0.06, PIV_Z - 0.10) for yy in (-0.36, 0.36)]
        struts.append(box(-0.50, -0.42, PIV_Z - 0.30, -0.36, 0.42, PIV_Z - 0.10))
    if raised:                                             # the lift ram from the bed to the rail
        a_ = (0.9, 0.0, BED_Z + 0.2)
        b_ = np.array(pivot) + Rp @ (np.array((-2.6, 0.0, 0.0)))
        struts.append(MK.hull_m([np.r_[a_[0] + dx, dy, a_[2]] for dx in (-0.1, 0.1) for dy in (-0.1, 0.1)] +
                                [np.r_[b_[0] + dx, dy, b_[2]] for dx in (-0.1, 0.1) for dy in (-0.1, 0.1)]))
    groups += [(8, rail + struts + deck), (9, mis), (10, mis2)]
    coll = [box(-3.3, -1.2, 0.0, 3.3, 1.2, BED_Z)] + struts + rail
    return MK.model(groups, coll)


def truck_model(orig):
    """the map's own truck 600_00_1 (no tarp) with its headlamps on: the troop truck on the ramp. Nose = -x"""
    import modelkit as MK, biprefabs as BP, mefmesh
    G = _orig_parts(orig, (0, 2, 3, 4, 5, 6, 7))
    gl = np.zeros(2, mefmesh.WOLG_DT)
    for k, y in enumerate((-0.85, 0.85)):
        gl[k] = ((-3.45 * M, y * M, 1.05 * M), 1500.0, 1.0, 0.92, 0.7, 0xABABABAB)
    return MK.model([(gi, [G[gi]]) for gi in sorted(G)], [BP.box_m(-3.3, -1.2, 0.0, 3.3, 1.2, 2.4)], glows=gl)


def rail_model(orig):
    """L12's track piece 417_01_1 with its own geometry, on darkened copies of its textures (rv: the bleached wood read pink under the desert sun)"""
    import modelkit as MK, biprefabs as BP
    G = _orig_parts(orig, (0, 1))
    return MK.model([(gi, [G[gi]]) for gi in sorted(G)], [BP.box_m(-21.19, -2.54, -0.21, 17.18, 3.41, 0.05)])


def bigm_model():
    """the big missile: body r 0.9 m, 15.5 m + a 2.5 m nose, four fins, two open service bays (dark, a panel swung out)"""
    import modelkit as MK, biprefabs as BP
    box, cyl = BP.box_m, BP.cyl_z
    r, L = 1.25, 21.0
    body = [cyl(r, 0.6, L, 20)]
    nose = [MK.hull_m([(r * math.cos(a), r * math.sin(a), L) for a in np.linspace(0, 2 * math.pi, 20, endpoint=False)] + [(0, 0, BIGM_H)])]
    skirt = [cyl(r * 1.15, 0.0, 0.6, 20)]
    fins = []
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        d, e = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
        pts = []
        for (rr, z) in ((r, 0.4), (r, 3.4), (r + 1.3, 0.2), (r + 1.3, 1.4)):
            for o in (-0.04, 0.04):
                q = d * rr + e * o
                pts.append((q[0], q[1], z))
        fins.append(MK.hull_m(pts))
    bays, doors = [], []
    for side, z0 in ((1.0, 5.0), (-1.0, 9.5)):             # bays on +x / -x: dark recess faces just proud of the skin
        x = side * (r + 0.01)
        bays.append(box(min(x, x + side * 0.02), -0.55, z0, max(x, x + side * 0.02), 0.55, z0 + 2.4))
        doors.append(MK.hull_m([(side * (r + 0.02), 0.55, z0), (side * (r + 0.02), 0.55, z0 + 2.4),
                                (side * (r + 0.95), 1.15, z0), (side * (r + 0.95), 1.15, z0 + 2.4),
                                (side * (r + 0.06), 0.55, z0), (side * (r + 0.06), 0.55, z0 + 2.4),
                                (side * (r + 0.99), 1.12, z0), (side * (r + 0.99), 1.12, z0 + 2.4)]))
    return MK.model([(0, body + nose + doors), (1, bays + fins), (2, skirt)], body + skirt)


def missile_panels(c, r, z, ang=(0.55, -0.55)):
    """owner 41: two service bays open on the missile's skin at the gantry: a dark recess, bundles of wires hanging out, the hatch folded down. World m; c = axis (x, y), r = skin radius"""
    import ssbase as SB
    me = SB.Mesh((c[0], c[1], z), ['jr_dark', 'ss_hz', 'ss_stl', 'ss_cpaint'])
    me.box(None, c[0] + r + 0.5, c[1] - 0.1, z - 0.1, c[0] + r + 0.6, c[1], z)
    for a in ang:
        ux, uy = -np.cos(a), np.sin(a)                       # (out of the skin, toward the gantry on the west)
        tx, ty = -uy, ux
        q = lambda o, t, dz: (c[0] + ux * (r + o) + tx * t, c[1] + uy * (r + o) + ty * t, z + dz)
        n = (ux, uy, 0.0)
        me.quad('jr_dark', q(0.03, -0.36, -0.42), q(0.03, 0.36, -0.42), q(0.03, 0.36, 0.42), q(0.03, -0.36, 0.42), n)
        me.quad('ss_stl', q(0.05, -0.42, -0.48), q(0.05, 0.42, -0.48), q(0.05, 0.42, -0.42), q(0.05, -0.42, -0.42), n)
        me.quad('ss_stl', q(0.05, -0.42, 0.42), q(0.05, 0.42, 0.42), q(0.05, 0.42, 0.48), q(0.05, -0.42, 0.48), n)
        me.quad('ss_stl', q(0.05, -0.36, -0.46), q(0.62, -0.36, -0.46), q(0.62, 0.36, -0.46), q(0.05, 0.36, -0.46), (0.0, 0.0, 1.0))   # (the hatch, folded down)
        for k, t in enumerate(np.arange(-0.27, 0.28, 0.09)):
            slot = ('ss_hz', 'ss_cpaint', 'ss_stl')[k % 3]
            o = 0.1 + 0.06 * (k % 4)
            for p0, p1 in (((0.04, 0.3), (o, 0.05)), ((o, 0.05), (o * 1.6, -0.42))):
                a_, b_ = q(p0[0], t, p0[1]), q(p1[0], t + 0.02 * (k % 3), p1[1])
                me.hull(slot, [(a_[0] + dx, a_[1] + dy, a_[2]) for dx, dy in ((-0.012, -0.012), (0.012, 0.012), (0.012, -0.012))] +
                        [(b_[0] + dx, b_[1] + dy, b_[2]) for dx, dy in ((-0.012, -0.012), (0.012, 0.012), (0.012, -0.012))], uv=0.5, solid=False)
    return me


def gant_model(levels=(5.0, 10.0, 15.0), h=17.0):
    """a steel service gantry: four posts 2.4 x 3.6 m, cross bracing, platforms (with toe rails) at `levels`; it stands at
    +x of the missile, the platforms reach to 0.15 m from its skin (model frame: the missile axis at x = -(r + 1.35))"""
    import biprefabs as BP
    import modelkit as MK
    box = BP.box_m
    st = []
    for x in (-1.2, 1.2):
        for y in (-1.8, 1.8):
            st.append(box(x - 0.1, y - 0.1, 0.0, x + 0.1, y + 0.1, h))
    for z in np.arange(2.5, h, 2.5):
        st += [box(-1.2, -1.85, z - 0.06, 1.2, -1.75, z + 0.06), box(-1.2, 1.75, z - 0.06, 1.2, 1.85, z + 0.06)]
    plat = []
    for z in levels:
        plat.append(box(-1.3 - 0.95, -1.9, z - 0.12, 1.3, 1.9, z))
        plat += [box(-1.3 - 0.95, -1.9, z, 1.3, -1.84, z + 1.05), box(-1.3 - 0.95, 1.84, z, 1.3, 1.9, z + 1.05)]
        if z == levels[0]:                                  # (wb20: this rail closed the bridge from the cage gate; Jones had to jump it and fell in the pit)
            plat += [box(1.24, -1.9, z, 1.3, -1.2, z + 1.05), box(1.24, 1.2, z, 1.3, 1.9, z + 1.05)]
        else:
            plat.append(box(1.24, -1.9, z, 1.3, 1.9, z + 1.05))
    return MK.model([(0, st), (1, plat)], st + plat)
