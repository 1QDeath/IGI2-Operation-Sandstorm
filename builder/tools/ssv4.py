"""ssv4 - Sandstorm v4 (2026-11-03, owner-approved plan work/plans/sandstorm_plan_v4.html): the secret missile base UNDER the
airfield. Mission-specific (only build_sandstorm.py imports it).

  * the hall = the L34 'Lab Cave' SHELL (460_01_1, location3/LEVEL4 Building 4090) - shell only: none of its 803 props, its own
    doors copied LOCKED (open doorways would show the void), buried under the airfield (origin O, turned YAW);
  * the way down = the shed behind the storage hangar (a copy of the map's own shed 432_10_1 with a stair hatch cut into its
    floor), tight stairs, a low corridor, a machine room under the hill, the ORIGINAL L12 personnel lift (Lift 4024: cab
    202_02_1, gates 202_03_1, call button, cablelift sounds) in a concrete shaft down into the cave;
  * new meshes (modelkit, vertex-lit) only where no original exists: the stairwell / corridor / machine room / lift shaft
    concrete (the map's own concrete texture), and the shed copy (432_10_1's own mesh + textures, floor re-cut).

Frames: world metres; the cave's own frame 'rel' = L34 coordinates minus the Lab Cave origin (floors: hall A -2, hall B 0, the
south cave -2.5..-3, catwalks +5; hall ceilings ~+23).
"""
import math, os, re
import numpy as np
from mission_lib import T, v
from qast import lit, tasks
from igiqvm import Str

M = 4096.0
CAVE_REL, CAVE_ID, CAVE_DOORS = 'location3/LEVEL4', 4090, 3929
CAVE_SRC = (-881684.5, -2021451.2, 1726162.8)             # the Lab Cave's origin in L34 (units)
O = (278.5, 255.0, -53.0)                                  # its origin here (m): the whole shell >= 2 m under the ground
YAW = math.pi                                              # (hall B's north-west corner under the machine room)
SHED_ID = 3137                                             # the map's shed behind the storage hangar (432_10_1)
SHED = (167.1, 238.5, -7.3)                                # its position (m); the way-down model's origin
SHED_EAST = 170.9                                          # its east wall (world x, m)
SHED_FLOOR = 0.08                                          # the shed floor's top over SHED z (shed_model's floor slab)
CELL_DOOR_P = (176.67, 233.45)                             # its hinge (world m): the west jamb, in the door wall's middle
CELL_DOOR_W = 1.12                                         # the machine-room doorway, narrowed to the prison cell door 500_23_1
HATCH = (166.5, 236.9, 170.10, 238.7)                      # the stair hatch in its floor (world m): the terrain cut must stay in the shed
TOP_Z = -15.3                                              # machine room / corridor floor (m)
LIFT_C = (165.1, 226.7)                                    # the lift cab's centre (m) = rel (113.4, 28.3): OUTSIDE the shell (the cab must
                                                           # cross no cave geometry), facing the NE annex's ground-floor east door (rel x 108.5)
VEST_END, VEST_DOOR_Y = 170.8, 226.1                       # the vestibule's end wall (world x) + its door opening (world y, 1.12 m wide)
LANDING_DOOR_HW = 0.8                                       # half width of the landing door gap in the cage (m)
LIFT_YAW = math.pi                                         # cab +x (entry gate) -> world -x; the exit (cab -x) -> world +x = rel -x (the landing)
LANDING = (107.4, 24.6, 110.7, 33.4)                       # the closed vestibule shaft -> door, under the annex's +4.6 balcony (rel)
CAB_SIDE = (224.2, 229.2)                                  # the cab's side walls (world y): collision faces of 202_02_1
CAB_HOLE = (-2.84, -2.83, 1.72, 2.67)                      # 202_02_1's floor/walls (collision): its entry-side floor ends at x 1.69
CAB_DZ = 0.22                                              # its walkable floor lies 0.17-0.26 m under its origin -> origin this much up
CAB = (-2.84, -2.83, 2.29, 2.67)                           # 202_02_1 extents in its own frame (x0, y0, x1, y1), m


def rel2w(rx, ry, rz=0.0):
    c, s = math.cos(YAW), math.sin(YAW)
    return (O[0] + c * rx - s * ry, O[1] + s * rx + c * ry, O[2] + rz)


def w2rel(x, y, z=0.0):
    c, s = math.cos(YAW), math.sin(YAW)
    dx, dy = x - O[0], y - O[1]
    return (c * dx + s * dy, -s * dx + c * dy, z - O[2])


def U(p):
    return tuple(float(c * M) for c in p)


# ------------------------------------------------------------------------------------------------ the cave shell + doors
def place_cave(X, m, static_parent, door_parent, open_doors=()):
    """copy the Lab Cave building (props dropped) and its door container; every door locked except open_doors (source ids)"""
    cid, ids = X.place_group(CAVE_REL, CAVE_ID, U(O), YAW, static_parent, pivot=list(CAVE_SRC),
                             name='SS underground base (L34 Lab Cave shell, props removed)', on_ground=False)
    m.reindex()
    kids = [lit(a.args[0]) for a in m.byid[cid].args if hasattr(a, 'name') and a.name == 'Task_New']
    dropped = 0
    for i in kids:                                         # props, cabinets, smoke: everything but the light map info
        if lit(m.byid[i].args[1]) != 'LightmapInfo':
            gone = [lit(t_.args[0]) for t_, d_, p_ in tasks([m.byid[i]])]
            dropped += len(gone); m.remove(i)
            m.used.difference_update(gone)                  # (their ids go back to the free pool: 1602-2753 is tight)
    m.reindex()
    job = X.jobs[CAVE_REL]                                 # the dropped props must not drag their models / light maps along
    job[1].clear(); job[1].add('460_01_1')
    for k_ in list(job[2]):
        job[2][k_] = [n_ for n_ in job[2][k_] if n_ in m.byid]
        if not job[2][k_]:
            del job[2][k_]
    S = X._source(CAVE_REL)
    src_doors = [lit(t.args[0]) for t, d, p in tasks([S['byid'][CAVE_DOORS][0]])]
    did, dids = X.place_group(CAVE_REL, CAVE_DOORS, U(O), YAW, door_parent, pivot=list(CAVE_SRC), name='SS base doors', on_ground=False)
    src2new = dict(zip(src_doors, dids))
    for n_ in dids:
        if lit(m.byid[n_].args[1]) == 'Door':
            job[1].add(str(lit(m.byid[n_].args[12])))
    locked = []
    for s_, n_ in src2new.items():
        if lit(m.byid[n_].args[1]) != 'Door':
            continue
        if s_ in open_doors:
            m.set(n_, 18, ''); m.set(n_, 19, '')
        else:
            locked.append(n_)
    # the locked ones become plain closed-door props (EditRigidObj, same model + pose) under Static: nothing to press E on, no AI
    # route through them (qa 11-03: 37 'looks like a normal door but is locked' warnings), and the openings stay closed
    statics = []
    for n_ in locked:
        t_ = m.byid[n_]
        a = [lit(x) for x in t_.args[:13]]
        statics.append(T(n_, 'EditRigidObj', 'SS base door (shut) ' + str(a[2]), float(a[3]), float(a[4]), float(a[5]),
                         float(a[9]), float(a[10]), float(a[11]), str(a[12]), 5, False, False))
        m.parent[n_].args.remove(t_)
    m.reindex()
    for t_ in statics:
        m.add_child(static_parent, t_)
    m.reindex()
    print('ssv4 cave: building %d at (%.1f, %.1f, %.1f) m yaw %.0f deg, %d source props dropped, %d doors (%d shut as props)' % (
        cid, O[0], O[1], O[2], math.degrees(YAW), dropped, len(src2new) - 1, len(locked)))
    return cid, src2new, locked


def cave_floor(X, rx, ry, zlo=-4.0, zhi=1.5, any_wind=False):
    """the cave floor height (rel m) under (rx, ry): its collision is wound the other way (floors face 'down' in numpy terms)"""
    S = X._source(CAVE_REL)
    if 'cave_tris' not in S:
        S['cave_tris'] = np.concatenate([vs[np.asarray(f)] for vs, f in S['lib'].collision_tree('460_01_1', 'union')]) / M
    Tr = S['cave_tris']
    a, b, c = Tr[:, 0], Tr[:, 1], Tr[:, 2]
    cr = lambda p, q: (q[:, 0] - p[:, 0]) * (ry - p[:, 1]) - (q[:, 1] - p[:, 1]) * (rx - p[:, 0])
    d1, d2, d3 = cr(a, b), cr(b, c), cr(c, a)
    ins = ((d1 >= 0) & (d2 >= 0) & (d3 >= 0)) | ((d1 <= 0) & (d2 <= 0) & (d3 <= 0))
    n = np.cross(b - a, c - a)
    zs = []
    for i in np.where(ins & ((np.abs(n[:, 2]) > 1e-6) if any_wind else (n[:, 2] < -1e-6)))[0]:
        wv = np.linalg.solve(np.array([[a[i, 0], b[i, 0], c[i, 0]], [a[i, 1], b[i, 1], c[i, 1]], [1.0, 1.0, 1.0]]), [rx, ry, 1.0])
        z = float(wv @ Tr[i, :, 2])
        if zlo <= z <= zhi:
            zs.append(z)
    return max(zs) if zs else None


# ------------------------------------------------------------------------------------------------ the L12 lift
def place_lift(X, m, parent, bottom_z, power_expr):
    """the ORIGINAL L12 personnel lift (location1/level2 Lift 4024 + its floors, gates, call button, button lights, go variable),
    moved rigidly: cab centre LIFT_C, top floor TOP_Z, bottom floor bottom_z, cab yaw LIFT_YAW. The call button also needs
    power_expr (the generator). Returns dict(lift, var, button, gate_in, gate_out)."""
    rel = 'location1/level2'
    S = X._source(rel)
    src = S['byid'][4024][0]
    src_ids = [lit(t.args[0]) for t, d, p in tasks([src])]
    src_pos = np.array([float(lit(src.args[13 + k])) for k in range(3)])
    yaw_add = LIFT_YAW - float(lit(src.args[18]))
    # the source Lift's position is its cab origin; the cab's centre in its own frame:
    cx, cy = (CAB[0] + CAB[2]) / 2, (CAB[1] + CAB[3]) / 2
    c0, s0 = math.cos(LIFT_YAW), math.sin(LIFT_YAW)
    pos = (LIFT_C[0] - (c0 * cx - s0 * cy), LIFT_C[1] - (s0 * cx + c0 * cy), TOP_Z + CAB_DZ)
    lid, ids = X.place_group(rel, 4024, U(pos), yaw_add, parent, pivot=list(src_pos), name='SS lift to the base (L12 personnel elevator)',
                             on_ground=False, strip_rules=False)
    o2n = dict(zip(src_ids, ids))
    R = np.array([[math.cos(yaw_add), -math.sin(yaw_add)], [math.sin(yaw_add), math.cos(yaw_add)]])
    P_new = np.array(U(pos))

    def mv(p):
        q = R @ (np.array(p[:2]) - src_pos[:2]) + P_new[:2]
        return float(q[0]), float(q[1]), float(p[2] - src_pos[2] + P_new[2])
    floors = []
    for t, d, p in tasks([m.byid[lid]]):
        ty = lit(t.args[1])
        if ty == 'Lift':
            x_, y_, z_ = mv([float(lit(t.args[13 + k])) for k in range(3)])
            for k, val in enumerate((x_, y_, z_)):
                t.args[13 + k] = v(val)
            t.args[18] = v(float(lit(t.args[18])) + yaw_add)
        elif ty == 'Floor':
            floors.append(t)
        for k, a in enumerate(t.args):                      # rename every task reference to the copies' ids
            s = lit(a) if isinstance(a, Str) else None
            if isinstance(s, str) and re.search(r'_\d+', s):
                s2 = re.sub(r'\b([A-Za-z]+)_(\d+)\b', lambda mo: '%s_%d' % (mo.group(1), o2n.get(int(mo.group(2)), int(mo.group(2)))), s)
                if s2 != s:
                    t.args[k] = v(s2)
    assert len(floors) == 2, floors
    for f_, z_ in zip(floors, (TOP_Z + CAB_DZ, bottom_z + CAB_DZ)):   # (CAB_DZ: the cab floor flush with both landings)           # floor 0 = the top (start), floor 1 = the bottom (L12 order)
        f_.args[3] = v(float(P_new[0])); f_.args[4] = v(float(P_new[1])); f_.args[5] = v(float(z_ * M))
        f_.args[8] = v(float(lit(f_.args[8])) + yaw_add)
    m.byid[lid].args[4] = v(o2n[4023])                      # (the start floor: the top)
    var, btn, g_in, g_out = o2n[3484], o2n[150], o2n[4032], o2n[3570]
    m.set(btn, 9, '!Lift_%d.isMoving && EditVariable_%d.nValue == 0' % (lid, var) + ('' if power_expr == '1' else ' && ' + power_expr))
    m.reindex()
    print('ssv4 lift: Lift %d cab centre (%.1f, %.1f) m, %.1f -> %.1f m (%.1f m), button %d, gates in %d / out %d, go variable %d' % (
        lid, LIFT_C[0], LIFT_C[1], TOP_Z, bottom_z, TOP_Z - bottom_z, btn, g_in, g_out, var))
    return dict(lift=lid, var=var, button=btn, gate_in=g_in, gate_out=g_out, ids=ids)


# ------------------------------------------------------------------------------------------------ new concrete meshes
def _bx():
    import biprefabs as BP
    return BP.box_m


def shaft_rect(margin=0.05):
    """the lift shaft's inner rectangle (world m): the cab's FLOOR footprint (CAB_HOLE) turned by LIFT_YAW + margin
    (owner 11-03 r3: cut to the render extents the hole ran 0.6 m past the cab floor on the entry side - Jones fell in)"""
    c, s = math.cos(LIFT_YAW), math.sin(LIFT_YAW)
    pts = [(c * x - s * y, s * x + c * y) for x in (CAB_HOLE[0], CAB_HOLE[2]) for y in (CAB_HOLE[1], CAB_HOLE[3])]
    cx, cy = (CAB[0] + CAB[2]) / 2, (CAB[1] + CAB[3]) / 2
    ox, oy = c * cx - s * cy, s * cx + c * cy
    xs = [p[0] - ox + LIFT_C[0] for p in pts]; ys = [p[1] - oy + LIFT_C[1] for p in pts]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def way_geometry():
    """the stairwell, corridor and machine room as solid concrete slabs, world metres: list of (x0, y0, z0, x1, y1, z1, kind)
    kind: 'c' concrete, 's' steel (railings, door frames). The hatch in the shed floor is HATCH."""
    G = []
    sx0, sy0, sy1 = 167.0, 236.9, 238.7                    # stairs: 32 steps 0.30 x 0.25 going east, 1.8 m wide
    n_st, run, rise = 32, 0.30, 0.25
    sx1 = sx0 + n_st * run                                 # 176.6
    top = SHED[2]
    for k in range(n_st):                                  # (owner 11-03 r3: 'drops two steps at a time' - the steps are seen
        zt = top - rise * (k + 1)                          #  only ('cv'); one smooth ramp is their collision, way_ramp())
        G.append((sx0 + k * run, sy0, zt - 0.7, sx0 + (k + 1) * run, sy1, zt, 'cv'))
    G.append((HATCH[0], sy0, top - 0.7, sx0, sy1, top + SHED_FLOOR, 'c'))   # the top landing, flush with the shed floor's top
    t = 0.3
    x = HATCH[0]
    while x < sx1 - 1e-6:                                  # side walls + a sloped ceiling in 0.6 m steps
        x2 = min(x + 0.6, sx1)
        f_lo = top - rise * max(0.0, (x2 - sx0) / run) - 0.7
        f_hi = top - rise * max(0.0, (x - sx0) / run)
        under_shed = x2 <= SHED_EAST + 1e-6                # (under the shed its floor closes the stairwell; beyond it a
        ceil = top if under_shed else min(f_hi + 2.6, top - 0.45)   #  concrete ceiling stays 0.45 m under the ground)
        # (owner playtest 11-03: 'head hits the ceiling, sees through the map' - the stepped ceiling slabs were 0.3 m thick while each
        #  step drops 0.5 m: slits to the void between them. Now 2.6 m headroom and 1.2 m slabs that overlap; walls reach their tops)
        ctop = top if under_shed else min(ceil + 1.2, top - 0.05)
        for ya, yb in ((sy0 - t, sy0), (sy1, sy1 + 2 * t)):   # (north wall 0.6 m: the terrain hole's last cell row)
            G.append((x, ya, f_lo, x2, yb, ctop, 'c'))
        if not under_shed:
            G.append((x, sy0 - t, ceil, x2, sy1 + 2 * t, ctop, 'c'))
        x = x2
    G.append((HATCH[0] - t, sy0 - t, top - 2.5, HATCH[0], sy1 + 2 * t, top, 'c'))   # the hatch's west wall
    # (owner 11-03 r3: 'too big, double doors' -> built like L12: a SMALL room against the shaft, the cab in the shaft opening, no cage, no landing door)
    # stairs bottom -> short passage south -> cell door -> low corridor west -> the lift room; the cab's entry gate is the only gate
    z0, h = TOP_Z, 2.4
    cx0, cx1 = sx1, sx1 + 1.8                              # the passage (x), the corridor (y c0..c1), the lift room (x r0..hx0, y hy0..c1)
    c0, c1, wy = 231.5, 233.3, 233.6
    hx0, hy0, hx1, hy1 = shaft_rect()
    r0 = 158.5
    zc = z0 + 4.6
    MR = (r0, hy0, hx0, c1)
    G.append((cx0 - 0.3, sy0 - t, z0 + h, cx0 + 0.6, sy1 + 2 * t, min(top - rise * ((cx0 - 0.3 - sx0) / run) + 2.6 + 1.2, top - 0.05), 'c'))   # (the stair ceiling's header)
    G += [(cx0, wy, z0 - t, cx1 + t, sy1 + t, z0, 'c'), (cx0, wy, z0 + h, cx1 + t, sy1 + t, z0 + h + t, 'c'),      # passage floor, ceiling
          (cx0, sy1, z0, cx1 + t, sy1 + t, z0 + h, 'c'), (cx1, wy, z0, cx1 + t, sy1, z0 + h, 'c'), (cx0 - t, wy, z0, cx0, sy0 - t, z0 + h, 'c')]
    d1 = cx0 + CELL_DOOR_W                                  # the door wall: the prison cell door 500_23_1 (1.11 x 2.13 m)
    G += [(d1, c1, z0, cx1 + t, wy, z0 + h, 'c'), (cx0, c1, z0 + 2.16, d1, wy, z0 + h, 'c')]
    G += [(hx0, c0 - t, z0 - t, cx1 + t, wy, z0, 'c'), (hx0, c0 - t, z0 + h, cx1 + t, wy, z0 + h + t, 'c'),         # corridor floor, ceiling
          (hx0 + t, c0 - t, z0, cx1 + t, c0, z0 + h, 'c'), (hx0 + t, c1, z0, cx0, wy, z0 + h, 'c'), (cx1, c0, z0, cx1 + t, c1, z0 + h, 'c')]
    G += [(r0 - t, hy0 - t, z0 - t, hx0, c1 + t, z0, 'c'),                                                           # room floor (flush to the cab)
          (r0 - t, hy0 - t, zc, hx1 + t, c1 + t, zc + t, 'c'),                                                       # one ceiling over room + shaft
          (r0 - t, hy0 - t, z0, r0, c1 + t, zc, 'c'), (r0 - t, hy0 - t, z0, hx1 + t, hy0, zc, 'c'),                   # west + south walls
          (r0 - t, c1, z0, hx0 + t, c1 + t, zc, 'c'),                                                                # north wall
          (hx1, hy0 - t, z0, hx1 + t, hy1 + t, zc, 'c'), (hx0, hy1, z0, hx1 + t, hy1 + t, zc, 'c'),                   # the shaft's east + north sides
          (hx0, hy1, z0, hx0 + t, c0, zc, 'c'), (hx0, c0, z0 + h, hx0 + t, c1, zc, 'c')]                               # the room's east wall, its header
    return G, MR


def shaft_geometry(bottom_z, mid_z=None):
    """the lift shaft from 0.8 m under the bottom floor up to the machine room floor; the exit opening (2.7 m high) on the cab's -x
    side at the bottom (with LIFT_YAW pi: world +x, into hall B)"""
    hx0, hy0, hx1, hy1 = shaft_rect()
    t = 0.3
    zb, zt = bottom_z - 0.8, TOP_Z                         # (owner 75: to TOP_Z - 0.3 they left a 30 cm slit all round under the top floor: the sky through the cab's mesh)
    ex, ey = -round(math.cos(LIFT_YAW)), -round(math.sin(LIFT_YAW))
    walls = {(-1, 0): (hx0 - t, hy0 - t, hx0, hy1 + t), (1, 0): (hx1, hy0 - t, hx1 + t, hy1 + t),
             (0, -1): (hx0, hy0 - t, hx1, hy0), (0, 1): (hx0, hy1, hx1, hy1 + t)}
    G = [(hx0 - t, hy0 - t, zb - t, hx1 + t, hy1 + t, zb, 'c')]
    if ex == 1:                                            # (rig lift2: Jones dipped 0.16 m in the 5 cm gap between the cab sill and the exit threshold)
        G.append((hx1 - 0.05, hy0, bottom_z - 0.2, hx1 + 0.01, hy1, bottom_z, 'c'))
    for k_, a in walls.items():
        if k_ == (ex, ey):
            G += [(a[0], a[1], zb, a[2], a[3], bottom_z, 'c')]
            if mid_z is None:
                G += [(a[0], a[1], bottom_z + 2.7, a[2], a[3], zt, 'c')]
            else:                                          # (owner 63: a second opening at the gun room stop, same size, the same exit gate serves it)
                G += [(a[0], a[1], bottom_z + 2.7, a[2], a[3], mid_z, 'c'), (a[0], a[1], mid_z + 2.7, a[2], a[3], zt, 'c')]
        else:
            G.append((a[0], a[1], zb, a[2], a[3], zt, 'c'))
    # the vestibule: the ground under the annex's balcony (rel x 108..110) lies outside the cave (the void) - a floor + side walls
    lz = bottom_z
    cs = [rel2w(x, y) for x in (LANDING[0], LANDING[2]) for y in (LANDING[1], LANDING[3])]
    vx0, vx1 = min(c[0] for c in cs), max(c[0] for c in cs); vy0, vy1 = min(c[1] for c in cs), max(c[1] for c in cs)
    G += [(vx0, vy0 - t, lz - 0.4, vx1, vy0, lz + 4.4, 'c'), (vx0, vy1, lz - 0.4, vx1, vy1 + t, lz + 4.4, 'c'),
          (vx0, vy0, lz - 0.3, vx1, vy1, lz, 'c'), (vx0, vy0 - t, lz + 4.1, vx1, vy1 + t, lz + 4.4, 'c')]   # (+ a roof: outside the
                                                                                                         #  shell the engine draws sky)
    # (rig lift_r3: from outside the shell the cave is not drawn - sky behind the open end of the vestibule) -> an end wall with a plain
    # doorway (no door: owner 'one gate only'), a dark one-sided panel (dark_doorway) hides the void in it; Jones walks through the panel
    import ssbase as SB                                    # (owner 11-04: the new hall stands behind this wall, the doorway is the hall's own)
    ex0, ex1, dy0, dy1, dh = VEST_END, VEST_END + 0.3, SB.LOBBY_DOOR[0], SB.LOBBY_DOOR[1], SB.LOBBY_DOOR[2]
    G += [(ex0, vy0, lz, ex1, dy0, lz + 4.1, 'c'), (ex0, dy1, lz, ex1, vy1, lz + 4.1, 'c'), (ex0, dy0, lz + dh, ex1, dy1, lz + 4.1, 'c')]
    G += [(vx0 - t, vy0, lz, vx0, hy0 - t, lz + 4.1, 'c'), (vx0 - t, hy1 + t, lz, vx0, vy1, lz + 4.1, 'c')]   # (rv15: the vestibule is wider than the shaft: two tall holes onto the sky at its lift end)
    # (owner 75, 83, rig lf5, lf14: the 0.3 m slits beside the cab: Jones slid past its front post and fell 19 m into the pit, and they stood as a black gap in full view) concrete jambs, at every stop
    for x0, x1, z, h in [(hx0 - 0.05, hx0 + 0.25, TOP_Z, 4.6), (hx1 - 0.25, hx1 + 0.05, bottom_z, 2.7)] + ([(hx1 - 0.25, hx1 + 0.05, mid_z, 2.7)] if mid_z is not None else []):
        for y0, y1 in ((hy0 - 0.05, CAB_SIDE[0]), (CAB_SIDE[1], hy1 + 0.05)):
            G.append((x0, y0, z, x1, y1, z + h, 'c'))
    return G


def shaft_clear(X, zlo=0.4, zhi=30.0):
    """cave collision triangles inside the shaft's column (rel z zlo..zhi over the cave floor): the cab must pass nothing"""
    S = X._source(CAVE_REL)
    cave_floor(X, 0.0, 0.0)
    Tr = S['cave_tris']
    hx0, hy0, hx1, hy1 = shaft_rect(0.35)
    cs = [w2rel(x, y) for x in (hx0, hx1) for y in (hy0, hy1)]
    rx0, rx1 = min(c[0] for c in cs), max(c[0] for c in cs); ry0, ry1 = min(c[1] for c in cs), max(c[1] for c in cs)
    c = Tr.mean(1)
    hit = (Tr[:, :, 0].max(1) > rx0) & (Tr[:, :, 0].min(1) < rx1) & (Tr[:, :, 1].max(1) > ry0) & (Tr[:, :, 1].min(1) < ry1) &           (Tr[:, :, 2].max(1) > zlo) & (Tr[:, :, 2].min(1) < zhi)
    return sorted(set(round(float(z), 1) for z in c[hit, 2]))


def mesh_from_boxes(G, origin, slots=('c', 's'), extra_coll=()):
    """modelkit model from slab boxes (world m) around origin: one render group per kind, collision = every slab
    (kind 'cv' = seen as 'c' but no collision; extra_coll = collision-only pieces, e.g. way_ramp())"""
    import modelkit as MK
    box = _bx()
    groups = {k: [] for k in slots}
    coll = list(extra_coll)
    for x0, y0, z0, x1, y1, z1, kind in G:
        b = box(x0 - origin[0], y0 - origin[1], z0 - origin[2], x1 - origin[0], y1 - origin[1], z1 - origin[2], uv=0.35)
        groups[kind.rstrip('v')].append(b)
        if not kind.endswith('v'):
            coll.append(b)
    up = lambda ps: [(P_, T_, np.tile((0.0, 0.0, 1.0), (len(P_), 1)), U_) for P_, T_, N_, U_ in ps]   # (even light: the level's sun must not pick out one wall underground)
    return MK.model([(i, up(groups[k])) for i, k in enumerate(slots) if groups[k]], coll)


def way_ramp(origin):
    """the stairs' collision: one ramp along the step noses, from the top landing (shed floor top) to the corridor floor"""
    import modelkit as MK
    sx0, sy0, sy1, sx1 = 167.0, 236.9, 238.7, 167.0 + 32 * 0.30
    z_a, z_b = SHED[2] + SHED_FLOOR, TOP_Z
    o = origin
    pts = []
    for x, z in ((sx0, z_a), (sx1, z_b)):
        for y in (sy0, sy1):
            pts += [(x - o[0], y - o[1], z - o[2]), (x - o[0], y - o[1], z - 0.5 - o[2])]
    return MK.hull_m(pts, uv=0.35)


def shed_model(hatch, door):
    """the map's shed 432_10_1 rebuilt ENTERABLE (the original is a hollow outer skin with a painted door: no inside faces, no
    floor) from its own textures and measures: walls 0.1 m (tin 431_15_1, both faces), gables + roof slopes (431_11_1), a floor
    (400_23_1) with the stair hatch cut out, a door opening in the +x long wall (where the original paints its door). Shed frame (m): long axis y (walls x +-2.0,
    y +-3.5, eaves 2.65 m, ridge 3.45 m, roof overhang to x +-2.3 / y +-3.8). hatch = (x0, y0, x1, y1); door = (y0, y1) of the
    opening in the x = +2 wall (2.15 m high; the -2 side stands against a stone wall). Slots: 431_15_1, 431_11_1, 400_23_1."""
    import modelkit as MK
    box = _bx()
    t, H, R, D = 0.10, 2.65, 3.45, 2.15
    hx0, hy0, hx1, hy1 = hatch
    dy0, dy1 = door
    walls = [box(-2.0, -3.5, 0.0, -2.0 + t, 3.5, H, uv=0.5), box(2.0 - t, -3.5, 0.0, 2.0, dy0, H, uv=0.5),
             box(2.0 - t, dy1, 0.0, 2.0, 3.5, H, uv=0.5), box(2.0 - t, dy0, D, 2.0, dy1, H, uv=0.5),
             box(-2.0, -3.5, 0.0, 2.0, -3.5 + t, H, uv=0.5), box(-2.0, 3.5 - t, 0.0, 2.0, 3.5, H, uv=0.5)]
    for ys in (-3.5, 3.5 - t):                              # the gables
        walls.append(MK.hull_m([(-2.0, ys, H), (2.0, ys, H), (0.0, ys, R), (-2.0, ys + t, H), (2.0, ys + t, H), (0.0, ys + t, R)], uv=0.5))
    roof = []
    for sg in (-1.0, 1.0):
        roof.append(MK.hull_m([(sg * 2.3, -3.8, H - 0.12), (0.0, -3.8, R), (sg * 2.3, 3.8, H - 0.12), (0.0, 3.8, R),
                               (sg * 2.3, -3.8, H - 0.04), (0.0, -3.8, R + 0.08), (sg * 2.3, 3.8, H - 0.04), (0.0, 3.8, R + 0.08)], uv=0.4))
    X0, Y0, X1, Y1 = -2.0 + t, -3.5 + t, 2.0 - t, 3.5 - t
    ceil = box(X0, Y0, H - 0.06, X1, Y1, H, uv=0.4)         # (rig p1: the hull slopes are one-sided - sky seen from inside; a ceiling)
    ceilp = [MK.panel((0.0, 0.0, H - 0.061), (1, 0, 0), (0, sg_, 0), X1 - X0, Y1 - Y0, uv=(0.0, 0.0, (X1 - X0) * 0.5, (Y1 - Y0) * 0.5)) for sg_ in (-1, 1)]
    # (judge R02: seen from below the roof tin's corrugations ran to one point like a smear: the ceiling is boards, the floor's planks)
    fl = [box(X0, Y0, -0.05, X1, hy0, 0.08, uv=0.5), box(X0, hy1, -0.05, X1, Y1, 0.08, uv=0.5),
          box(X0, hy0, -0.05, hx0, hy1, 0.08, uv=0.5), box(hx1, hy0, -0.05, X1, hy1, 0.08, uv=0.5)]
    # (judge E03, 11-12: 400_23_1 is this map's sand, not planks: the ceiling showed desert overhead. The boards are the walls' 431_15_1)
    return MK.model([(0, walls + ceilp), (1, roof), (2, fl)], walls + roof + fl + [ceil])


SHED_SLOTS = ['431_15_1', '431_11_1', '400_23_1']


def write_nav_res(meshes, path):
    """a tiny .res with these meshes (name -> mefmesh) for navgen (it reads model collision from .res banks)"""
    import ilff
    from mission_lib import GAME
    form, ch, hdr = ilff.read(os.path.join(GAME, 'COMMON', 'models', 'common.res'))
    out = []
    for nm, mesh in meshes.items():
        out.append((b'NAME', ('LOCAL:models/%s.mef' % nm).encode('latin1') + b'\0', 4))
        out.append((b'BODY', mesh.write(), 4))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(ilff.write(form, out, hdr[1] or 4))
    return path


def orig_mesh(rel, vn):
    """an original model's mesh (mefmesh.RigidModel), its level and texture names (= build_sandstorm._orig_mesh)"""
    import prefab as _pf, mefmesh as _mm
    lv = _pf.Level(os.path.join(_pf.GAME, 'MISSIONS', *rel.split('/')))
    L_ = lv.find_vnam(vn)
    mefn, texs = L_.entry(vn)
    return lv, _mm.RigidModel.from_mef(_mm.Mef.read(lv.find_resource('LOCAL:models/%s.mef' % mefn, 'models')[1])), texs


def hole_rect(cell_m, x0_grid, y0_grid, rect, inside):
    """the terrain cells a DiscardTask must cut so that every cell touching rect (x0, y0, x1, y1 m) goes; asserts the cut stays
    inside `inside` (the shed's footprint). Returns (centre x, centre y, width, height) m for the DiscardTask."""
    i0 = math.floor((rect[0] - x0_grid) / cell_m); i1 = math.ceil((rect[2] - x0_grid) / cell_m)
    j0 = math.floor((rect[1] - y0_grid) / cell_m); j1 = math.ceil((rect[3] - y0_grid) / cell_m)
    cx0, cx1 = x0_grid + i0 * cell_m, x0_grid + i1 * cell_m
    cy0, cy1 = y0_grid + j0 * cell_m, y0_grid + j1 * cell_m
    assert inside[0] <= cx0 and cx1 <= inside[2] and inside[1] <= cy0 and cy1 <= inside[3], ('hole leaves the shed', (cx0, cy0, cx1, cy1))
    e = 0.05                                               # (a cell goes only when FULLY inside the rectangle)
    return (cx0 + cx1) / 2, (cy0 + cy1) / 2, cx1 - cx0 + e, cy1 - cy0 + e, (cx0, cy0, cx1, cy1)
