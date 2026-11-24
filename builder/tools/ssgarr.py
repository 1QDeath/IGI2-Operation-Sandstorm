"""ssgarr - Sandstorm garrison 2 (owner 11-05 items 55, 56, 11-04b item 32): THE BULWARK. The soldiers no longer live in rooms along a wall: they live INSIDE a
fortified wall that cuts the hall in two. Two wings (mess + barracks / armoury + ready room + comms) either side of a road portal, a fire deck on top, bastions,
steel stairs, a catwalk over the silo. Behind env SS_GARRISON2=1. New vertex-lit meshes from the map's own textures, original props inside. World metres."""
import math
import numpy as np
import ssbase as SB
from ssbase import Mesh, wall, F, Y0, Y1, _tile, _noise, _rgba, _concrete

X0, X1 = 222.0, 231.4                                      # the wall's west and east faces
PY0, PY1 = 218.5, 231.5                                    # the road portal
PH = 5.6                                                   # its clear height
GC, U0, UC, DK = 3.4, 3.6, 6.7, 7.0                        # ground ceiling, upper floor, upper ceiling, deck (rel F)
T_ = 0.4                                                   # outer wall
PAR = 1.05                                                 # parapet
XI0, XI1 = X0 + T_, X1 - T_
NY0, NY1 = 232.0, 255.6                                    # north wing inside
SY0, SY1 = 196.4, 218.0                                    # south wing inside
KITCHEN_Y = 247.0
PASS_Y = 198.6                                             # the service passage's north wall
ARM_Y = 207.6                                              # armoury / ready room
SPUR_Y = 253.6                                             # the catwalk over the silo, x X1..SPUR_X
SPUR_X = 258.0
SHUT = (224.2, 229.2, 3.2)                                 # the ready room's roll-up shutter in the portal's south wall (x0, x1, height)
SLOTS = ['ss_gw', 'ss_gi', 'ss_gf', 'ss_gc', 'ss_gd', 'ss_lamp', 'ss_hz', 'ss_stl', 'ss_duct', 'ss_cc', 'ss_corr', '433_13_1_argb8888', 'ss_gk', 'ss_lkr']
S_MESH = '433_13_1_argb8888'
DOOR_W, DOOR_H = 1.2, 2.14
RESERVED = (218.0, 196.0, 234.6, 256.0)                    # nothing else stands here
# doors (name, wall axis, wall centre, t0 of the opening, z rel F): the map's 501_04_1, plain doors unless named locked
DOORS = [('mess west', 'x', X0 + T_ / 2, 237.0, 0.0), ('mess east', 'x', X1 - T_ / 2, 235.0, 0.0), ('barracks', 'x', X0 + T_ / 2, 250.8, U0),
         ('passage west', 'x', X0 + T_ / 2, 196.9, 0.0), ('passage east', 'x', X1 - T_ / 2, 196.9, 0.0), ('armoury', 'x', X0 + T_ / 2, 203.0, 0.0),
         ('comms', 'x', X1 - T_ / 2, 199.4, U0), ('nco', 'y', 206.85, 226.0, U0)]


# ------------------------------------------------------------------------------------------------ textures
def tex_gw(get):
    """the wall's outer face, 4 x 7 m: board-marked concrete, rust and soot run down from the deck, a dark dado"""
    n = 512
    a = _tile(get('409_17_1'), 2, 3, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    p = np.exp(-(((u - 0.5) / 0.34) ** 2 + ((v - 0.62) / 0.34) ** 2))
    img = _concrete(a, p, 0.40, 0.42) * (0.82 + 0.34 * _noise(n, n, 41))[..., None]
    for k in range(0, n, n // 10):                          # shutter boards
        img[k:k + 2, :] *= 0.72
    st = np.clip(_noise(n, n, 42, (24, 48)) * 1.6 - 0.62, 0, 1) * np.clip(1.05 - v * 1.5, 0, 1)
    img *= (1 - 0.55 * st)[..., None]
    d = v > 0.84
    img[d] = (np.array([0.15, 0.17, 0.13]) * (0.8 + 0.4 * _noise(n, n, 43))[..., None])[d]
    img[(v > 0.83) & (v <= 0.84)] = (0.50, 0.37, 0.10)
    g = np.clip((v - 0.95) / 0.05, 0, 1)
    return _rgba(img * (1 - 0.55 * g)[..., None])


def tex_gi(get):
    """a room's wall, 3 x 3.2 m: cream distemper over an olive dado, a lamp's pool, damp at the floor"""
    n = 256
    a = _tile(get('409_17_1'), 2, 2, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    L = a.mean(2) / max(float(a.mean()), 1e-3)
    p = np.exp(-(((u - 0.5) / 0.48) ** 2 + ((v - 0.12) / 0.55) ** 2))
    b = (0.50 + 0.17 * L) * (0.40 + 0.40 * p)
    img = np.dstack([b * 0.98, b * 0.90, b * 0.72])
    d = v > 0.60
    img[d] = np.dstack([b * 0.44, b * 0.52, b * 0.36])[d]
    img[(v > 0.595) & (v <= 0.605)] = (0.20, 0.18, 0.12)
    img *= (0.88 + 0.22 * _noise(n, n, 44))[..., None]
    img[v > 0.97] *= 0.45
    return _rgba(img)


def tex_gf(get):
    """a room's floor, 4 x 4 m: worn terrazzo squares, a lamp's pool"""
    n = 256
    a = _tile(get('409_10_1'), 2, 2, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    p = np.exp(-(np.hypot(u - 0.5, v - 0.5) / 0.42) ** 2)
    img = _concrete(a, p, 0.30, 0.40, cool=np.array([0.60, 0.58, 0.52])) * (0.82 + 0.3 * _noise(n, n, 45))[..., None]
    for k in range(0, n, n // 8):
        img[k:k + 2, :] *= 0.6
        img[:, k:k + 2] *= 0.6
    return _rgba(img)


def tex_gc(get):
    n = 128
    a = _tile(get('436_11_1'), 2, 2, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    return _rgba(_concrete(a, np.exp(-(np.hypot(u - 0.5, v - 0.5) / 0.3) ** 2), 0.16, 0.34))


def tex_gd(get):
    """the fire deck, 4 x 4 m: rough screed, a drain line, worn by boots"""
    n = 256
    a = _tile(get('409_10_1'), 2, 2, n, n)
    img = _concrete(a, np.zeros((n, n)), 0.30, 0.0) * (0.78 + 0.42 * _noise(n, n, 46))[..., None]
    img[:, :3] *= 0.5
    return _rgba(img)


def tex_gk(get):
    """kitchen and wash tiles, 2 x 2 m"""
    n = 128
    img = np.tile(np.array([0.46, 0.47, 0.42]), (n, n, 1)) * (0.8 + 0.3 * _noise(n, n, 47))[..., None]
    for k in range(0, n, n // 6):
        img[k, :] *= 0.72
        img[:, k] *= 0.72
    return _rgba(img)


def tex_lkr(get):
    """judge R08: steel lockers drawn into the Bulwark itself (the map's 208_01_1 showed as bare black posts): ss-world's locker face"""
    import ssrooms as RM
    return np.asarray(RM.tx_locker(), float)


TEXTURES = {'ss_lkr': tex_lkr, 'ss_gw': tex_gw, 'ss_gi': tex_gi, 'ss_gf': tex_gf, 'ss_gc': tex_gc, 'ss_gd': tex_gd, 'ss_gk': tex_gk}


# ------------------------------------------------------------------------------------------------ building helpers
def _bands(z0, z1, cuts):
    out, z = [], z0
    for a, b in sorted(cuts):
        if a > z:
            out.append((z, a))
        z = max(z, b)
    if z < z1:
        out.append((z, z1))
    return out


def wallrun(me, axis, plane, side, t0, t1, z0, z1, ops=(), rooms=(), tout=None, thick=T_, tbase=0.0, frames=True, istep=3.0, ostep=4.0, oz=(0.0, DK)):
    """a wall with holes. plane = its room face, seen from `side` (+1 / -1 along axis); the outer face lies thick behind it. ops = (a, b, zlo, zhi) holes.
    rooms = (zlo, zhi, slot, step) the bands of the room face that are drawn (each bay's texture stands on its own floor). All z rel F. tout = the outer face's slot"""
    o = plane - side * thick
    p, q = min(plane, o), max(plane, o)
    cuts = sorted({t0, t1} | {c for a, b, _, _ in ops for c in (a, b) if t0 < c < t1})
    for a, b in zip(cuts[:-1], cuts[1:]):
        m_ = (a + b) / 2
        for za, zb in _bands(z0, z1, [(zl, zh) for c0, c1, zl, zh in ops if c0 <= m_ <= c1]):
            if axis == 'x':
                me.box(None, p, a, F + za, q, b, F + zb)
            else:
                me.box(None, a, p, F + za, b, q, F + zb)
            if tout:
                wall(me, axis, o, -side, a, b, F + za, F + zb, tout, ztop=F + oz[1], H=oz[1] - oz[0], tbase=tbase, step=ostep)
            for r0, r1, slot, st in rooms:
                za2, zb2 = max(za, r0), min(zb, r1)
                if zb2 > za2 + 1e-6:
                    wall(me, axis, plane, side, a, b, F + za2, F + zb2, slot, ztop=F + r1, H=r1 - r0, tbase=tbase, step=st)
    if frames:
        for a, b, zl, zh in ops:
            frame(me, axis, p, q, a, b, F + zl, F + zh, bottom=zl > z0)


def frame(me, axis, p, q, a, b, z0, z1, bottom=False, w=0.07):
    """steel reveal of an opening, standing 3 cm proud of both faces"""
    def B(t0, t1, z_0, z_1):
        if axis == 'x':
            me.box('ss_stl', p - 0.03, t0, z_0, q + 0.03, t1, z_1, uv=0.5, solid=False)
        else:
            me.box('ss_stl', t0, p - 0.03, z_0, t1, q + 0.03, z_1, uv=0.5, solid=False)
    B(a - w, a, z0, z1 + w); B(b, b + w, z0, z1 + w); B(a - w, b + w, z1, z1 + w)
    if bottom:
        B(a - w, b + w, z0 - w, z0)


def bars(me, axis, c, a, b, z0, z1):
    for t in np.arange(a + 0.12, b - 0.05, 0.16):
        if axis == 'x':
            me.box('ss_duct', c - 0.015, t - 0.015, F + z0, c + 0.015, t + 0.015, F + z1, solid=False)
        else:
            me.box('ss_duct', t - 0.015, c - 0.015, F + z0, t + 0.015, c + 0.015, F + z1, solid=False)


def floor(me, slot, x0, y0, x1, y1, z, up=True, s=4.0):
    uv = [(x0 / s, y0 / s), (x1 / s, y0 / s), (x1 / s, y1 / s), (x0 / s, y1 / s)]
    me.quad(slot, (x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), (0, 0, 1 if up else -1), uv)


def stair(me, a, b, w0, w1, z0, z1, axis='y', rails=(True, True)):
    """a steel flight from (a, z0) to (b, z1), across w0..w1. World z. Collision = a smooth ramp (the AI and the walker need no step-up), the steps are seen only"""
    n = max(2, int(round(abs(z1 - z0) / 0.19)))
    run = (b - a) / n
    d = (z1 - z0) / n
    P = (lambda t, w, z: (w, t, z)) if axis == 'y' else (lambda t, w, z: (t, w, z))
    me.hull(None, [P(t_, w_, z_ + o_) for t_, z_ in ((a, z0), (b, z1)) for w_ in (w0, w1) for o_ in (-0.14, 0.0)])
    for k in range(n):
        t0, t1 = a + k * run, a + (k + 1) * run
        z_ = z0 + (k + 1) * d
        lo, hi = min(t0, t1), max(t0, t1)
        if axis == 'y':
            me.box('ss_stl', w0, lo, z_ - 0.05, w1, hi, z_, uv=0.5, solid=False)
        else:
            me.box('ss_stl', lo, w0, z_ - 0.05, hi, w1, z_, uv=0.5, solid=False)
    for w, r in ((w0, rails[0]), (w1 - 0.06, rails[1])):
        me.hull('ss_duct', [P(t_, w_, z_ + o_) for t_, z_ in ((a, z0), (b, z1)) for w_ in (w, w + 0.06) for o_ in (-0.26, 0.0)], uv=0.5, solid=False)
        if r:
            me.hull('ss_hz', [P(t_, w_, z_ + o_) for t_, z_ in ((a, z0), (b, z1)) for w_ in (w, w + 0.05) for o_ in (0.94, 1.0)], uv=0.5, solid=False)
            me.hull(None, [P(t_, w_, z_ + o_) for t_, z_ in ((a, z0), (b, z1)) for w_ in (w, w + 0.05) for o_ in (0.0, 1.0)])
            for f in np.linspace(0.0, 1.0, 5):
                t_, z_ = a + (b - a) * f, z0 + (z1 - z0) * f
                q = P(t_, w, 0.0)
                me.box('ss_duct', q[0] - 0.02, q[1] - 0.02, z_, q[0] + 0.02, q[1] + 0.02, z_ + 0.96, solid=False)


def rail(me, x0, y0, x1, y1, z):
    """a rail along one side of a landing: x0..x1 or y0..y1 thin"""
    me.box('ss_hz', x0, y0, z + 0.94, x1, y1, z + 1.0, uv=0.5, solid=False)
    me.box(None, x0, y0, z, x1, y1, z + 1.0)
    L = max(x1 - x0, y1 - y0)
    for f in np.linspace(0.0, 1.0, max(2, int(L / 1.2) + 1)):
        x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        me.box('ss_duct', x - 0.02, y - 0.02, z, x + 0.02, y + 0.02, z + 0.96, solid=False)


def landing(me, x0, y0, x1, y1, z, posts=()):
    me.box('ss_stl', x0, y0, z - 0.12, x1, y1, z, uv=0.5, solid=False)
    me.box(None, x0, y0, z - 0.6, x1, y1, z)               # (gwb: a closed door shoved Jones through a thin plate)
    for x, y in posts:
        me.box('ss_stl', x - 0.08, y - 0.08, F, x + 0.08, y + 0.08, z - 0.12, uv=0.5)


def ceil_lamp(me, x, y, z, ax='x', L=0.6, size=520.0):
    w = 0.09 if L > 1.0 else L / 2                         # (judge R03, 11-08: a 1.2 x 0.18 m strip seen from close below read as a bar poking out of the ceiling; the rooms get 0.6 m square panels, the portal keeps its long ones)
    dx, dy = (L / 2, w) if ax == 'x' else (w, L / 2)
    me.box('ss_stl', x - dx - 0.04, y - dy - 0.04, z - 0.025, x + dx + 0.04, y + dy + 0.04, z, uv=0.5, solid=False)   # (judge R03: a flush panel in a steel rim, no 7 cm bright slab hanging off the ceiling)
    me.quad('ss_lamp', (x - dx, y - dy, z - 0.03), (x + dx, y - dy, z - 0.03), (x + dx, y + dy, z - 0.03), (x - dx, y + dy, z - 0.03), (0, 0, -1))
    me.lamp((x, y, z - 0.14), size, (1.0, 0.86, 0.62))


def locker(me, x0, y, z, face, w=0.95, d=0.5, h=1.9):
    """a steel locker against the wall at x0 (its back), door to +x (face 1) or -x (face -1)"""
    x1 = x0 + face * d
    me.box('ss_stl', min(x0, x1), y - w / 2, z, max(x0, x1), y + w / 2, z + h, uv=0.5)
    xf = x1 + face * 0.005
    a, b = (y + w / 2, y - w / 2) if face > 0 else (y - w / 2, y + w / 2)
    me.quad('ss_lkr', (xf, a, z + 0.02), (xf, b, z + 0.02), (xf, b, z + h - 0.02), (xf, a, z + h - 0.02), (face, 0, 0), [(0, 1), (1, 1), (1, 0), (0, 0)])


def kitchen(me):
    """judge R10: the Bulwark kitchen's own fittings along the west wall: a range with burners, oven door and pots, a steel sink and drainer with a tap"""
    x0 = XI0
    # range: 0.9 wide, 0.65 deep, 0.86 high, burners and pots on top, oven door and knobs in front
    y = 251.0
    me.box('ss_stl', x0, y - 0.45, F, x0 + 0.65, y + 0.45, F + 0.86, uv=0.5)
    me.box('ss_duct', x0 + 0.66, y - 0.36, F + 0.18, x0 + 0.67, y + 0.36, F + 0.62, solid=False)          # oven door
    me.box('ss_hz', x0 + 0.66, y - 0.30, F + 0.66, x0 + 0.685, y + 0.30, F + 0.68, solid=False)           # its handle
    for k in range(4):
        me.box('ss_duct', x0 + 0.66, y - 0.33 + k * 0.22, F + 0.74, x0 + 0.69, y - 0.29 + k * 0.22, F + 0.78, solid=False)   # knobs
    for bx, by in ((0.18, -0.22), (0.18, 0.22), (0.46, -0.22), (0.46, 0.22)):
        me.box('ss_duct', x0 + bx - 0.1, y + by - 0.1, F + 0.86, x0 + bx + 0.1, y + by + 0.1, F + 0.88, solid=False)   # burners
    me.box('ss_corr', x0 + 0.08, y - 0.37, F + 0.88, x0 + 0.30, y - 0.07, F + 1.10, uv=0.5, solid=False)   # a big pot
    me.box('ss_duct', x0 + 0.06, y - 0.39, F + 1.10, x0 + 0.32, y - 0.05, F + 1.12, solid=False)          # its lid
    me.box('ss_corr', x0 + 0.36, y + 0.10, F + 0.88, x0 + 0.56, y + 0.34, F + 0.98, uv=0.5, solid=False)   # a pan
    me.box('ss_stl', x0, y - 0.5, F + 1.9, x0 + 0.5, y + 0.5, F + 2.25, uv=0.5, solid=False)              # hood
    # sink: a steel counter with a basin, a drainer and a tap
    y = 253.4
    me.box('ss_stl', x0, y - 0.7, F, x0 + 0.6, y + 0.7, F + 0.9, uv=0.5)
    me.box('ss_duct', x0 + 0.08, y - 0.55, F + 0.9, x0 + 0.52, y - 0.05, F + 0.905, solid=False)          # the basin
    for k in range(6):
        me.box('ss_duct', x0 + 0.1, y + 0.08 + k * 0.09, F + 0.9, x0 + 0.5, y + 0.11 + k * 0.09, F + 0.906, solid=False)   # drainer ribs
    me.box('ss_duct', x0 + 0.02, y - 0.32, F + 0.9, x0 + 0.06, y - 0.28, F + 1.2, solid=False)            # tap riser
    me.box('ss_duct', x0 + 0.02, y - 0.32, F + 1.17, x0 + 0.24, y - 0.28, F + 1.2, solid=False)           # spout
    me.box('ss_corr', x0 + 0.12, y + 0.2, F + 0.906, x0 + 0.36, y + 0.44, F + 0.95, uv=0.5, solid=False)   # a stack of plates


def wall_lamp(me, x, y, z, dx, dy, size=1100.0):
    """a bracket flood on an outer face (dx, dy = the way it looks)"""
    me.box('ss_lamp', x - 0.3 - abs(dy) * 0.3 + abs(dx) * 0.28, y - 0.3 - abs(dx) * 0.3 + abs(dy) * 0.28, z - 0.08, x + 0.3 + abs(dy) * 0.3 - abs(dx) * 0.28, y + 0.3 + abs(dx) * 0.3 - abs(dy) * 0.28, z + 0.08, solid=False)
    me.lamp((x + dx * 0.4, y + dy * 0.4, z - 0.2), size, (1.0, 0.82, 0.55))


# ------------------------------------------------------------------------------------------------ the Bulwark
def slit(c, w=1.3, lo=1.45, hi=2.1):
    return (c - w / 2, c + w / 2, lo, hi)


def uslit(c):
    return (c - 0.6, c + 0.6, U0 + 1.5, U0 + 2.05)


def door(t, z=0.0):
    return (t, t + DOOR_W, z, z + DOOR_H)


def bulwark():
    me = Mesh(((X0 + X1) / 2, 226.0, F), SLOTS)
    D = F + DK
    GR, UR = (0.0, GC, 'ss_gi', 3.0), (U0, UC, 'ss_gi', 3.0)
    KR = (0.0, GC, 'ss_gk', 2.0)
    # --- long walls, both storeys in one run. West (gallery) face, east (silo) face
    w_n = [slit(234.2), door(237.0), slit(240.6), slit(243.6), slit(251.0, 0.8), uslit(234.0), uslit(237.5), uslit(241.0), uslit(244.5), uslit(248.0), door(250.8, U0), uslit(254.2)]
    e_n = [door(235.0), slit(239.4), slit(243.0), slit(251.0, 0.8), uslit(234.0), uslit(237.5), uslit(241.0), uslit(244.5), uslit(248.0), uslit(251.5)]
    wallrun(me, 'x', XI0, 1, 231.5, Y1, 0.0, DK, w_n, rooms=[GR, UR], tout='ss_gw', tbase=232.0)
    wallrun(me, 'x', XI1, -1, 231.5, Y1, 0.0, DK, e_n, rooms=[GR, UR], tout='ss_gw', tbase=232.0)
    w_s = [door(196.9), door(203.0), slit(200.6), slit(206.4, 0.8), slit(210.0), slit(213.5), slit(216.8, 0.8), uslit(198.4), uslit(201.5), uslit(204.6), uslit(209.5), uslit(212.6), uslit(215.7)]
    e_s = [door(196.9), door(199.4, U0), uslit(203.0), uslit(209.5), uslit(212.6), uslit(215.7), slit(201.5, 0.8), slit(210.5), slit(214.5)]
    wallrun(me, 'x', XI0, 1, Y0, 218.5, 0.0, DK, w_s, rooms=[GR, UR], tout='ss_gw', tbase=196.0)
    wallrun(me, 'x', XI1, -1, Y0, 218.5, 0.0, DK, e_s, rooms=[GR, UR], tout='ss_gw', tbase=196.0)
    for k in (234.2, 240.6, 243.6, 251.0):
        bars(me, 'x', XI0 - 0.2, k - 0.65 if k != 251.0 else k - 0.4, k + 0.65 if k != 251.0 else k + 0.4, 1.45, 2.1)
    for k in (239.4, 243.0):
        bars(me, 'x', XI1 + 0.2, k - 0.65, k + 0.65, 1.45, 2.1)
    # --- the wings' end walls on the portal (concrete both sides, no room face at the portal side), the wings' ends on the hall walls
    wallrun(me, 'y', NY0, 1, X0, X1, 0.0, DK, rooms=[(0.0, GC, 'ss_gi', 3.0), UR], tout='ss_gw', thick=0.5, tbase=222.0)
    wallrun(me, 'y', SY1, -1, X0, X1, 0.0, DK, [(SHUT[0], SHUT[1], 0.0, SHUT[2])], rooms=[(0.0, GC, 'ss_gi', 3.0), UR], tout='ss_gw', thick=0.5, tbase=222.0)
    wallrun(me, 'y', NY1, -1, XI0, XI1, 0.0, DK, rooms=[KR, UR], thick=0.4, tbase=222.0)
    wallrun(me, 'y', SY0, 1, XI0, XI1, 0.0, DK, rooms=[(0.0, GC, 'ss_cc', 3.0), UR], thick=0.4, tbase=222.0)
    # --- slabs: ground floors, between the storeys, deck
    floor(me, 'ss_gf', XI0, NY0, XI1, KITCHEN_Y, F + 0.012)
    floor(me, 'ss_gk', XI0, KITCHEN_Y + 0.3, XI1, NY1, F + 0.012, s=2.0)
    floor(me, 'ss_gf', XI0, ARM_Y + 0.4, XI1, SY1, F + 0.012)
    floor(me, 'ss_corr', XI0, PASS_Y + 0.3, XI1, ARM_Y, F + 0.012)
    floor(me, 'ss_gf', XI0, NY0, XI1, NY1, F + U0)
    floor(me, 'ss_gf', XI0, SY0, XI1, SY1, F + U0)
    for y0, y1 in ((NY0, NY1), (SY0, SY1)):
        me.box(None, XI0, y0, F + GC, XI1, y1, F + U0)
        me.box(None, XI0, y0, F + UC, XI1, y1, D - 0.02)
        floor(me, 'ss_gc', XI0, y0, XI1, y1, F + UC, up=False)
    floor(me, 'ss_gc', XI0, NY0, XI1, KITCHEN_Y, F + GC, up=False)
    floor(me, 'ss_gk', XI0, KITCHEN_Y + 0.3, XI1, NY1, F + GC, up=False, s=2.0)
    floor(me, 'ss_gc', XI0, PASS_Y + 0.3, XI1, SY1, F + GC, up=False)
    # --- partitions
    wallrun(me, 'y', KITCHEN_Y, -1, XI0, XI1, 0.0, GC, [(225.8, 227.0, 0.0, DOOR_H)], rooms=[(0.0, GC, 'ss_gi', 3.0)], thick=0.3, tbase=222.0)
    for a, b in ((XI0, 225.8), (227.0, XI1)):
        wall(me, 'y', KITCHEN_Y + 0.3, 1, a, b, F, F + GC, 'ss_gk', ztop=F + GC, H=GC, step=2.0, tbase=222.0)
    wall(me, 'y', KITCHEN_Y + 0.3, 1, 225.8, 227.0, F + DOOR_H, F + GC, 'ss_gk', ztop=F + GC, H=GC, step=2.0, tbase=222.0)
    # the service passage: low, pipes, its own ceiling
    PZ = 2.6
    wallrun(me, 'y', PASS_Y + 0.3, 1, XI0, XI1, 0.0, GC, rooms=[(0.0, GC, 'ss_gi', 3.0)], thick=0.3, tbase=222.0)
    wall(me, 'y', PASS_Y, -1, XI0, XI1, F, F + PZ, 'ss_cc', tbase=222.0, step=3.0)
    me.box(None, XI0, SY0, F + PZ, XI1, PASS_Y, F + GC)
    floor(me, 'ss_corr', XI0, SY0, XI1, PASS_Y, F + PZ, up=False)
    floor(me, 'ss_corr', XI0, SY0, XI1, PASS_Y, F + 0.012)
    for z_, r_ in ((PZ - 0.2, 0.09), (PZ - 0.42, 0.06)):
        me.cyl('ss_duct', r_, XI0, XI1, 'x', (PASS_Y - 0.2, F + z_), uv=0.5, seg=8)
    ceil_lamp(me, (XI0 + XI1) / 2, SY0 + 0.5, F + PZ, L=0.5, size=320.0)
    # armoury / ready room
    wallrun(me, 'y', ARM_Y, -1, XI0, XI1, 0.0, GC, rooms=[(0.0, GC, 'ss_cc', 3.0)], thick=0.4, tbase=222.0, frames=False)
    wall(me, 'y', ARM_Y + 0.4, 1, XI0, XI1, F, F + GC, 'ss_gi', ztop=F + GC, H=GC, step=3.0, tbase=222.0)
    # upper floor, south: comms / NCOs
    wallrun(me, 'y', 206.7, -1, XI0, XI1, U0, UC, [(226.0, 227.2, U0, U0 + DOOR_H)], rooms=[UR], thick=0.3, tbase=222.0)
    for a, b in ((XI0, 226.0), (227.2, XI1)):
        wall(me, 'y', 207.0, 1, a, b, F + U0, F + UC, 'ss_gi', ztop=F + UC, H=UC - U0, step=3.0, tbase=222.0)
    wall(me, 'y', 207.0, 1, 226.0, 227.2, F + U0 + DOOR_H, F + UC, 'ss_gi', ztop=F + UC, H=UC - U0, step=3.0, tbase=222.0)
    # --- judge R08, R10: lockers (ready room both walls, barracks between the bunks, NCO room) and the kitchen fittings, drawn into this mesh
    for y in np.arange(209.0, 217.5, 1.25):
        locker(me, XI0, y, F, 1); locker(me, XI1, y, F, -1)
    for y in np.arange(233.4, 249.5, 3.5):
        locker(me, XI0, y + 1.75, F + U0, 1); locker(me, XI1, y + 1.75, F + U0, -1)
    for y in (209.5, 213.2, 216.4):
        locker(me, XI1, y, F + U0, -1)
    kitchen(me)
    # --- ceiling lamps
    for y in (235.0, 240.5, 245.0):
        ceil_lamp(me, 226.7, y, F + GC, 'y')
    ceil_lamp(me, 226.7, 251.5, F + GC, size=420.0)
    for y in (236.0, 243.0, 250.0):
        ceil_lamp(me, 226.7, y, F + UC, 'y')
    ceil_lamp(me, 226.7, 203.3, F + GC, size=380.0)
    ceil_lamp(me, 226.7, 213.0, F + GC, 'y')
    ceil_lamp(me, 226.7, 201.6, F + UC, size=420.0)
    ceil_lamp(me, 226.7, 212.5, F + UC, 'y')
    # --- the portal: soffit, beams, hazard jambs, two lamps
    me.box(None, X0, PY0, F + PH, X1, PY1, D - 0.02)
    floor(me, 'ss_gc', X0, PY0, X1, PY1, F + PH, up=False)
    wall(me, 'x', X0, -1, PY0, PY1, F + PH, D, 'ss_gw', ztop=D, H=DK, tbase=196.0, step=4.0)
    wall(me, 'x', X1, 1, PY0, PY1, F + PH, D, 'ss_gw', ztop=D, H=DK, tbase=196.0, step=4.0)
    for x in (X0 + 0.15, X1 - 0.15):
        me.box('ss_hz', x - 0.15, PY0 - 0.02, F + PH - 0.22, x + 0.15, PY1 + 0.02, F + PH, uv=0.5, solid=False)
    for y, s in ((PY0, 1), (PY1, -1)):
        me.box('ss_hz', X0 - 0.12, min(y, y + s * 0.5), F, X0 + 0.3, max(y, y + s * 0.5), F + 1.4, uv=0.5)
        me.box('ss_hz', X1 - 0.3, min(y, y + s * 0.5), F, X1 + 0.12, max(y, y + s * 0.5), F + 1.4, uv=0.5)
    ceil_lamp(me, 224.5, 225.0, F + PH - 0.05, 'y', L=2.4, size=900.0)
    ceil_lamp(me, 229.0, 225.0, F + PH - 0.05, 'y', L=2.4, size=900.0)
    # --- bastions either side of the portal, solid, slits drawn dark; the deck runs out over them
    for y0, y1 in ((214.0, 218.5), (231.5, 236.0)):
        x0 = 218.0
        me.box(None, x0, y0, F, X0, y1, D - 0.02)
        wall(me, 'x', x0, -1, y0, y1, F, D, 'ss_gw', tbase=196.0, step=4.0)
        wall(me, 'y', y0, -1, x0, X0, F, D, 'ss_gw', tbase=218.0, step=4.0)
        wall(me, 'y', y1, 1, x0, X0, F, D, 'ss_gw', tbase=218.0, step=4.0)
        me.quad('ss_stl', (x0 - 0.02, (y0 + y1) / 2 - 0.6, F + 4.8), (x0 - 0.02, (y0 + y1) / 2 + 0.6, F + 4.8), (x0 - 0.02, (y0 + y1) / 2 + 0.6, F + 5.3), (x0 - 0.02, (y0 + y1) / 2 - 0.6, F + 5.3), (-1, 0, 0))
    # --- the deck: floor, parapets, gaps for the stairs and the catwalk
    me.box(None, X0, Y0, D - 0.02, X1, Y1, D)
    floor(me, 'ss_gd', X0, Y0, X1, Y1, D)
    for y0, y1 in ((214.0, 218.5), (231.5, 236.0)):
        me.box(None, 218.0, y0, D - 0.02, X0, y1, D)
        floor(me, 'ss_gd', 218.0, y0, X0, y1, D)

    def par(x0, y0, x1, y1):
        me.box('ss_cc', x0, y0, D, x1, y1, D + PAR, uv=0.4)
        me.box('ss_hz', x0 - 0.01, y0 - 0.01, D + PAR, x1 + 0.01, y1 + 0.01, D + PAR + 0.03, uv=0.5, solid=False)
    par(X0 - 0.3, Y0, X0, 214.0)
    par(217.7, 213.7, X0, 214.0); par(217.7, 213.7, 218.0, 218.8); par(217.7, 218.5, X0, 218.8)
    par(X0 - 0.3, 218.5, X0, 231.5)
    par(217.7, 231.2, X0, 231.5); par(217.7, 231.2, 218.0, 236.3); par(217.7, 236.0, X0, 236.3)
    par(X0 - 0.3, 236.0, X0, 243.7); par(X0 - 0.3, 245.5, X0, Y1)
    par(X1, Y0, X1 + 0.3, 205.8); par(X1, 207.3, X1 + 0.3, SPUR_Y)
    # --- NW stair (gallery side): up to the barracks door, then on to the deck
    SX0, SX1, SX2 = 218.9, 220.4, 220.5
    ya, yb, yl = 245.5, 250.3, 252.4
    stair(me, ya, yb, SX2, X0, F, F + U0, rails=(False, False))
    stair(me, yb, ya, SX0, SX1, F + U0, D, rails=(True, False))
    landing(me, SX0, yb, X0, yl, F + U0, posts=[(SX0 + 0.1, yl - 0.1), (SX0 + 0.1, yb)])
    landing(me, SX0, 243.7, X0, ya, D, posts=[(SX0 + 0.1, 243.8), (SX0 + 0.1, ya)])
    rail(me, SX0, yl - 0.05, X0, yl, F + U0); rail(me, SX0, yb, SX0 + 0.05, yl, F + U0)
    rail(me, SX0, 243.7, X0, 243.75, D); rail(me, SX0, 243.7, SX0 + 0.05, ya, D)
    me.box('ss_duct', SX1, ya + 0.3, F + U0 - 0.3, SX2, yb, F + U0, solid=False)
    # --- SE stair (silo side)
    ex0, ex1, ex2, ex3 = 231.4, 232.9, 233.0, 234.5
    ya, yb, yl = 205.8, 201.0, 198.9
    stair(me, ya, yb, ex0, ex1, F, F + U0, rails=(False, False))
    stair(me, yb, ya, ex2, ex3, F + U0, D, rails=(False, True))
    landing(me, ex0, yl, ex3, yb, F + U0, posts=[(ex3 - 0.1, yl + 0.1), (ex3 - 0.1, yb)])
    landing(me, ex0, ya, ex3, 207.3, D, posts=[(ex3 - 0.1, ya), (ex3 - 0.1, 207.2)])
    rail(me, ex0, yl, ex3, yl + 0.05, F + U0); rail(me, ex3 - 0.05, yl, ex3, yb, F + U0)
    rail(me, ex0, 207.25, ex3, 207.3, D); rail(me, ex3 - 0.05, ya, ex3, 207.3, D)
    # --- the catwalk over the silo + its stair down by the gate
    me.box('ss_stl', X1, SPUR_Y, D - 0.12, SPUR_X, Y1, D, uv=0.5)
    for x in np.arange(X1 + 3.0, SPUR_X + 0.1, 6.0):
        me.box('ss_stl', x - 0.06, SPUR_Y - 0.0, D - 0.7, x + 0.06, SPUR_Y + 0.12, D - 0.12, uv=0.5, solid=False)
        me.hull('ss_stl', [(x - 0.06, SPUR_Y, D - 0.12), (x + 0.06, SPUR_Y, D - 0.12), (x - 0.06, Y1, D - 0.12), (x + 0.06, Y1, D - 0.12), (x - 0.06, Y1, D - 1.4), (x + 0.06, Y1, D - 1.4)], uv=0.5, solid=False)
    rail(me, X1, SPUR_Y, SPUR_X, SPUR_Y + 0.05, D)
    stair(me, SPUR_X, 267.0, 254.4, Y1 - 0.02, D, F, axis='x', rails=(True, False))
    me.box(None, SPUR_X - 0.05, SPUR_Y, D, SPUR_X, 254.4, D + 1.0)
    # --- floods on the faces
    for x, y, dx, dy in ((X0, 226.0 - 8.0, -1, 0), (X0, 226.0 + 18.0, -1, 0), (X0, 208.0, -1, 0), (X0, 200.0, -1, 0), (X1, 226.0 + 15.0, 1, 0), (X1, 212.0, 1, 0), (X1, 233.0, 1, 0)):
        wall_lamp(me, x + dx * 0.15, y, F + 6.1, dx, dy)
    return me


def fix_props(P):
    """the hall's old props out of the wall's way, the fuel truck in the motor pool"""
    x0, y0, x1, y1 = RESERVED
    out = []
    for r in P:
        nm, md, x, y, z, yaw = r
        if nm.startswith('SS room prop'):
            continue
        if nm == 'SS fuel truck':
            out.append((nm, md, 214.0, 204.5, z, yaw)); continue
        if x0 - 1.0 <= x <= x1 + 1.0 and y0 <= y <= y1:
            continue
        out.append(r)
    return out


def props():
    """(name, model, x, y, z rel F, yaw) the originals in the rooms"""
    P = []

    def add(md, x, y, z=0.0, yaw=0.0, nm='SS garrison prop'):
        P.append(('%s %d' % (nm, len(P)), md, x, y, F + z, yaw))
    # mess: long tables with benches down the room, a stove, shelves, a fridge, a TV
    for k, y in enumerate((234.4, 238.2, 242.0)):
        add('231_03_1', 225.2, y, yaw=math.pi / 2); add('231_03_1', 228.6, y, yaw=math.pi / 2)
        add('231_04_1', 224.3, y, yaw=math.pi / 2); add('231_04_1', 226.1, y, yaw=math.pi / 2)
        add('231_04_1', 227.7, y, yaw=math.pi / 2); add('231_04_1', 229.5, y, yaw=math.pi / 2)
    add('230_06_1', 230.5, 246.2, yaw=math.pi); add('230_19_1', 223.0, 245.9, yaw=math.pi / 2); add('231_10_1', 228.8, 246.38, yaw=0.0)   # (RQ1 ss-look S5: floor set, screen to the mess, back 3 cm off the partition; the table is gone)
    # kitchen (judge R10: the two 260_01_1 drew as bare black posts here; the range and sink are in the mesh)
    add('230_19_1', 230.4, 250.0, yaw=-math.pi / 2); add('230_19_1', 230.4, 253.0, yaw=-math.pi / 2)
    add('260_11_1', 226.8, 251.2); add('333_03_1', 228.8, 248.2); add('231_17_1', 229.0, 254.8)
    add('306_01_1', 229.9, 252.9, yaw=math.pi / 2); add('333_03_1', 229.6, 250.9)          # (judge R10: supply cases and a second drum; 333_01_1 crates exist only inside ss-world's merged rooms)
    # barracks: two rows of bunks with lockers between, a table at the end
    for k, y in enumerate(np.arange(233.4, 249.5, 3.5)):
        add('260_02_1', 223.5, y, z=U0, yaw=math.pi / 2); add('260_02_1', 229.9, y, z=U0, yaw=-math.pi / 2)
    add('260_11_1', 228.4, 253.4, z=U0); add('261_06_1', 227.2, 253.4, z=U0, yaw=-math.pi / 2); add('261_06_1', 229.6, 253.4, z=U0, yaw=math.pi / 2)
    # armoury: gun racks, weapon boxes, ammo cases
    for x in (224.0, 226.0, 228.0, 230.0):
        add('231_14_1', x, 200.6 - 0.9 + 0.0, z=0.0, yaw=0.0)
        add('239_01_1', x, 207.0)
    add('231_03_1', 226.7, 203.3, yaw=math.pi / 2)
    for x, y in ((223.9, 205.7), (223.9, 204.6), (229.6, 203.0), (229.6, 204.1)):      # (2.0 x 1.05 m cases)
        add('306_01_1', x, y)
    # ready room: lockers both sides, benches, kit
    add('231_04_1', 226.7, 210.0); add('231_04_1', 226.7, 213.0)
    # comms: desks, shelves, lamp; NCOs: bunks
    add('200_01_1', 224.3, 197.36, z=U0 + 0.908, yaw=0.0)     # (item 109: the terminal on the comms desk, keyboard at the front edge, under hack_computer's hands)
    add('231_15_1', 224.3, 196.98, z=U0, yaw=-math.pi / 2); add('231_15_1', 229.2, 196.98, z=U0, yaw=-math.pi / 2); add('261_06_1', 229.2, 198.0, z=U0, yaw=math.pi)
    add('230_19_1', 223.0, 205.4, z=U0, yaw=math.pi / 2); add('231_17_1', 230.4, 205.6, z=U0)
    for y in (209.5, 213.2, 216.4):
        add('260_02_1', 223.5, y, z=U0, yaw=math.pi / 2)
    return P


REVIEW = [(n_, (x_, y_, F + z_)) for n_, x_, y_, z_ in (('road', 200.0, 225.0, 0.0), ('front', 215.0, 225.0, 0.0), ('portal', 226.7, 225.0, 0.0), ('inner', 237.0, 225.0, 0.0), ('mess', 226.7, 240.0, 0.0),
          ('kitchen', 226.7, 249.0, 0.0), ('barracks', 226.7, 240.0, U0), ('stair foot', 221.2, 243.0, 0.0), ('landing', 221.0, 251.4, U0), ('deck', 226.7, 225.0, DK), ('deck n', 226.7, 250.0, DK),
          ('bastion', 220.0, 233.7, DK), ('spur', 245.0, 254.8, DK), ('spur end', 256.0, 254.8, DK), ('passage', 226.7, 197.5, 0.0), ('ready', 226.7, 213.0, 0.0), ('armoury', 226.7, 203.0, 0.0),
          ('comms', 226.7, 202.0, U0), ('nco', 226.7, 212.0, U0), ('silo nw', 236.0, 250.0, 0.0), ('se top', 232.5, 206.5, DK))]


# sandbag positions in the open and on the deck: (x, y, z rel F, yaw, model)
SB_STRAIGHT, SB_CORNER = '360_05_1', '360_04_1'
BAGS = []
for _x, _y, _yw in ((205.0, 222.0, 0.0), (205.0, 228.0, 0.0), (213.0, 219.5, 0.0), (213.0, 231.0, 0.0), (197.0, 218.5, 0.0), (197.0, 233.0, 0.0), (240.0, 212.5, math.pi / 2), (240.0, 241.0, math.pi / 2),
                    (262.5, 212.5, 0.0), (262.5, 232.0, 0.0), (259.0, 222.0, math.pi / 2)):
    BAGS.append((_x, _y, 0.0, _yw, SB_STRAIGHT))
for _x, _y, _yw in ((218.5, 221.0, math.pi / 2), (218.5, 229.0, math.pi / 2)):
    BAGS.append((_x, _y, 0.0, _yw, SB_STRAIGHT))
for _x, _y, _yw in ((219.0, 216.2, math.pi / 2), (219.0, 233.8, math.pi / 2), (222.8, 225.0, math.pi / 2), (222.8, 209.0, math.pi / 2), (222.8, 241.0, math.pi / 2), (230.6, 241.0, math.pi / 2), (230.6, 225.0, math.pi / 2), (230.6, 212.0, math.pi / 2)):
    BAGS.append((_x, _y, DK, _yw, SB_STRAIGHT))


def shutter_model():
    """the ready room's roll-up shutter: corrugated, hazard foot; built lying down like the blast gate (it slides up)"""
    hw, h = (SHUT[1] - SHUT[0]) / 2 + 0.02, SHUT[2] + 0.02
    me = Mesh((0, 0, 0), ['ss_corr', 'ss_hz'])
    me.quad('ss_corr', (0.06, -hw, 0), (0.06, hw, 0), (0.06, hw, h), (0.06, -hw, h), (1, 0, 0), [(0, 2), (3, 2), (3, 0), (0, 0)])
    me.quad('ss_corr', (-0.06, hw, 0), (-0.06, -hw, 0), (-0.06, -hw, h), (-0.06, hw, h), (-1, 0, 0), [(0, 2), (3, 2), (3, 0), (0, 0)])
    me.box('ss_hz', -0.08, -hw, 0.0, 0.08, hw, 0.22, uv=0.5, solid=False)
    me.box(None, -0.06, -hw, 0.0, 0.06, hw, h)
    R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    for k_ in me.g:
        me.g[k_] = [(P_ @ R.T, T__, N_ @ R.T, U_) for P_, T__, N_, U_ in me.g[k_]]
    me.coll = [(P_ @ R.T, T__, N_ @ R.T, U_) for P_, T__, N_, U_ in me.coll]
    return me.model()


# ------------------------------------------------------------------------------------------------ the men
def face(dx, dy):
    return round(math.atan2(-dx, dy), 6)


AK, AKG, MG, SG, MAC, T64, HK, JH = ['AK47'], ['AK47', 'GRENADE'], ['MINIMI'], ['SPAS12'], ['MAC10'], ['TYPE64SMG'], ['HK104'], ['JACKHAMMER']
WEST, EAST, NORTH, SOUTH = face(-1, 0), face(1, 0), face(0, 1), face(0, -1)
# (mess check 11-05: guard_in_back_of_truck carries a root offset: the sitters stood through the wall, only shadows and hands in the room; no seated clip in play)
TALK1, TALK2, SIT, SLEEP, WORK, LOOK = 'stand_talk1', 'stand_talk2', 'stand_talk1', 'jones_sits_against_wall', 'scientist_kneeling_consolework', None
# key: (type, hold at post in the alert, [(x, y, z rel F, facing, clip, weapons)])
POSTS = {
    'U road post': ('T', True, [(204.2, 224.6, 0.0, WEST, LOOK, MG), (204.2, 226.0, 0.0, face(3.3, -0.8), TALK2, AKG), (207.5, 225.2, 0.0, face(-3.3, 0.8), TALK1, AK)]),   # (ss-life 11-15 L9: one watches the road at the bags, two talk behind him; 1230 used to talk to 1228's back)
    'U motor pool': ('N', False, [(185.91, 212.45, 0.0, NORTH, WORK, AK), (191.0, 210.6, 0.0, SOUTH, TALK1, T64), (191.0, 208.8, 0.0, NORTH, TALK2, SG)]),
    'U deck west': ('T', True, [(219.3, 232.8, DK, WEST, LOOK, AKG), (220.0, 216.8, DK, WEST, LOOK, MG), (222.9, 228.0, DK, WEST, LOOK, AKG), (222.9, 248.0, DK, WEST, LOOK, HK)]),
    'U deck east': ('T', True, [(230.3, 222.0, DK, EAST, LOOK, AKG), (230.3, 238.0, DK, EAST, LOOK, MG)]),
    'U spur': ('T', True, [(240.0, 254.8, DK, SOUTH, LOOK, AKG), (250.0, 254.8, DK, EAST, TALK1, HK), (251.8, 254.8, DK, WEST, TALK2, MG)]),   # (ss-life 11-15 L8: one looks down on the cage, two talk on the catwalk)
    'U gate post': ('T', True, [(260.4, 222.6, 0.0, WEST, LOOK, MG), (263.5, 212.0, 0.0, WEST, 'stand_inspect_weapon_rifle', AKG), (263.5, 232.8, 0.0, None, LOOK, AKG)]),   # (ss-life 11-15 L10: the MG man watches the road, one checks his rifle; life_2 ssface: 1265 faced WEST into an obstacle 2 m off -> facing None = the builder's look_node)
    'U cage': ('N', True, [(242.8, 235.8, 0.0, round(math.radians(133.0), 6), LOOK, AK), (242.8, 238.6, 0.0, SOUTH, TALK2, HK)]),   # (S11-C owner 11-15 'two soldiers both looking at the wall': they stood 9.5 m apart, both west at the Bulwark wall 11 m off, backs to the gate they guard; L6: one watches the portal mouth by the gate, his mate talks at his shoulder)
    # the two pairs the witness clocks and the talk lines read keep the old keys
    'U room 3': ('N', False, [(224.3, 245.0, 0.0, EAST, TALK1, AK), (225.9, 245.0, 0.0, WEST, TALK2, T64)]),
    'U mess': ('N', False, [(224.2, 234.4, 0.0, EAST, TALK1, AK), (224.2, 238.2, 0.0, face(1.0, 1.4), TALK1, HK), (226.1, 234.4, 0.0, WEST, TALK2, MAC), (225.2, 239.6, 0.0, face(-1.0, -1.4), TALK2, AK)]),   # (ss-life 11-15 L3: two conversations across the tables; the other two used to talk to nobody 5 m away)
    'U room 2': ('N', False, [(226.2, 246.0, U0, EAST, TALK1, AK), (227.8, 246.0, U0, WEST, TALK2, SG)]),
    'U barracks': ('N', False, [(224.9, 233.4, U0, EAST, SLEEP, AK), (228.5, 236.9, U0, WEST, SLEEP, AK), (224.9, 240.0, U0, EAST, SLEEP, T64), (226.4, 240.0, U0, WEST, TALK2, HK)]),   # (ss-life 11-15 L7: the one who cannot sleep talks low to the man against the wall)
    'U nco': ('N', False, [(225.6, 214.0, U0, EAST, TALK1, AK), (227.4, 214.0, U0, WEST, TALK2, AKG)]),
    'U ready': ('T', False, [(226.2, 213.0, 0.0, SOUTH, TALK1, AKG), (226.7, 216.8, 0.0, EAST, TALK1, MG), (228.2, 216.8, 0.0, WEST, TALK2, AKG),
                             (224.2, 211.5, 0.0, WEST, 'stand_inspect_weapon_rifle', SG), (226.2, 210.0, 0.0, NORTH, TALK2, AK), (229.2, 213.5, 0.0, EAST, 'stand_clean_weapon', AK)]),   # (ss-life 11-15 L4: a platoon waiting, not a parade of six facing north on the sweep loop)
    'U comms': ('N', False, [(224.3, 198.1, U0, SOUTH, 'hack_computer', ['MAKAROV']), (229.2, 203.8, U0, SOUTH, LOOK, HK)]),
    'U passage': ('N', False, [(227.0, 197.5, 0.0, WEST, LOOK, AK)]),
}
PATROLS = [('U south walk', (205.0, 202.0), 0.0, 9000.0, 'AK|HK'), ('U yard walk', (205.0, 246.0), 0.0, 9000.0, 'AK|SG'), ('U silo walk', (260.0, 245.0), 0.0, 9000.0, 'AK|AK'), ('U deck walk', (226.7, 205.0), DK, 8000.0, 'AK|AK')]
ROOM_KEYS = ('U room 3', 'U mess', 'U room 2', 'U barracks', 'U nco', 'U ready', 'U comms', 'U passage')
BUTTONS = ((X0 - 0.06, 241.0, 1.3, face(-1, 0)), (X0 - 0.06, 209.0, 1.3, face(-1, 0)), (X1 + 0.06, 214.0, 1.3, face(1, 0)), (X1 + 0.06, 247.0, 1.3, face(1, 0)), (172.06, 212.0, 1.3, face(1, 0)))
HEAR_ROOM, HEAR_OPEN = 0.2, 0.3                            # (owner 64: rifle ~100 m -> 30 m in the open, 20 m through a wall; a silenced hit's 10 m noise stops at 3 m / 2 m)


def garrison(g):
    """section 6: every man at a place with a reason, facing his work; rifles lowered until the alert. g = the builder's globals"""
    m, alarmai, squad = g['m'], g['alarmai'], g['squad']
    Call, Str = g['Call'], g['Str']
    C = alarmai.C
    ua, skins, SP = g['_UA'], g['CSFM'], g['SQ_PARENT']
    types = {'T': g['C3T'], 'N': g['C3N']}
    far = 0
    for key, (ty, hold_, spots) in POSTS.items():
        mem = []
        for k, (x, y, z, gam, clip, w) in enumerate(spots):
            p = (x * 4096.0, y * 4096.0, (F + z) * 4096.0)
            d = min(math.dist(n['pos'], p) for n in g['GRAPHS'][6]) / 4096.0
            if d > 1.6:
                far += 1
                print('garrison: %s man %d is %.1f m from a node' % (key, k, d))
            look = None
            if gam is None:                                    # (S2 ss-life 11-15: facing None = the builder's look_node: a door he can see, else the longest free lane, never a wall)
                look, gam = g['look_node'](6, p)
                print('garrison: %s man %d faces %.0f deg (look node %s)' % (key, k, math.degrees(gam) % 360, look))
            if clip is None:
                sc = g['life_sentry'](w, k + len(key), ua, look=look)
            else:
                ev = C('AIFunction_GetCurrentEventType')
                calm = [Call('AIFunction_SetStandActionAnimation', [Str(clip)]), C('AIAction_PlayAnimation', 1, 0)]
                sc = alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), [C('AIFunction_DefaultHandler')],
                                                    [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                                [alarmai.If(alarmai.EQ(ua, 1), [C('AIAction_Idle', 'AIACTIONFLAG_NONE')], calm), C('AIFunction_PassEventOnToSquad')],
                                                                [C('AIFunction_DefaultHandler')])])])
            mem.append(dict(pos=p, model=skins[(k + len(key)) % len(skins)], weapons=w, ai_type=types[ty], graph=6, ai=sc, gamma=gam))
        sid, hids = m.squad(SP, key, 'AIType_Offensive', mem, alarm_switch=-1, alarm_control=-1)
        g['SQUAD_IDS'][key] = (sid, hids)
        g['ENEMY_COUNT'][0] += len(hids)
    for key, (x, y), z, r, ws in PATROLS:
        w = [dict(AK=AK, HK=HK, SG=SG)[s_] for s_ in ws.split('|')]
        squad(key, 6, (x * 4096.0, y * 4096.0), r, w, types['N'], skins, zlo=(F + z - 0.6) * 4096.0, zhi=(F + z + 0.6) * 4096.0, alarm=False, patrol=1.0, calm_var=ua, spacing=5000.0)
    print('garrison: %d posted men, %d far from a node' % (sum(len(v[2]) for v in POSTS.values()), far))


LOOT = (('MP5SD', 'WEAPON_ID_MP5SD', 226.5, 203.1, 0.82), ('medipack 1', 'WEAPON_ID_MEDIPACK', 227.1, 203.8, 0.82), ('medipack 2', 'WEAPON_ID_MEDIPACK', 228.8, 246.5, 0.82))


def loot(g):
    """a risky spot pays: the armoury's silenced gun, medipacks"""
    m, T, nid, PICK = g['m'], g['T'], g['nid'], g['PICK']
    for nm, wid, x, y, z in LOOT:
        r = (1.570796, 0.0, 0.0) if 'MEDIPACK' in wid else (3.141605, 1.449968, 0.6)
        m.add_child(PICK, T(nid(), 'GunPickup', 'SS garrison ' + nm, x * 4096.0, y * 4096.0, (F + z) * 4096.0 + 120.0, *r, wid, ''))


def sight(key):
    """calm sight in metres (owner item 10): 3 m inside the lobby door Jones died in 7 s (gd1, gd2) with the engine's default cones: a calm man sees what is near him, once the fight is on the combat cones take over"""
    return 14 if key in ROOM_KEYS else 28 if key in ('U deck west', 'U deck east', 'U spur', 'U gate post') else 20


EARLY = ('DEAD', 'DELETE', 'PATROLCOMMANDPROCESSED', 'DANGERSTATETIMEOUT', 'ALARMOFF', 'ALARMON', 'FLASHBANG', 'GRENADETHROWN', 'GRENADELAND', 'GRENADESHOUT', 'ENEMYDETECTION', 'ENEMYDETECTION_NO_LOF', 'TAKINGDAMAGE',
         'GUNSHOT', 'FRIENDLY_DYING', 'FRIENDLYDETECTION', 'EXPLOSION')


def eyes(g):
    """owner 64: COMMON default.qvm ranks a body, a friend dying and a blast BELOW IDLE, so a man in an idle clip never got them (gb1). The first SetEventPriority of an event wins: name these first, in the default's own order"""
    m, alarmai = g['m'], g['alarmai']
    from igiqvm import Call, Ident
    import diffscale as ds
    n = 0
    for key, (sid, hids) in g['SQUAD_IDS'].items():
        for h in hids:
            aid = next(c.args[0] for c in m.byid[h].args if hasattr(c, 'args') and str(c.args[1]).strip('"') == 'HumanAI')
            k = str(g['lit'](aid))
            old = m.ai_files.get(k)
            if not isinstance(old, (bytes, bytearray)):
                continue
            ver, body = alarmai.decompile_ai(bytes(old))
            cr = ds._find_create(body)
            if cr is None:
                continue
            cr.then[0:0] = [Call('AIFunction_SetEventPriority', [Ident('AIEVENT_' + e)]) for e in EARLY]
            m.ai_files[k] = alarmai.compile_ai(body, ver)
            n += 1
    print('garrison: %d men see bodies and blasts while idle' % n)


def hearing(key):
    return HEAR_ROOM if key in ROOM_KEYS else HEAR_OPEN


def alert(g):
    """section 6b: the hall's own alarm: buttons, hunt, reaction force. The Hunt runs on graph 6 only, in cells of 24 m"""
    import alarmai
    m, nid, T, LOGIC = g['m'], g['nid'], g['T'], g['LOGIC']
    U = g['U_ALARM']
    rule = 'EditVariable_%d.nValue == 1' % U
    A2 = nid()
    m.add_child(LOGIC, T(A2, 'AlarmControl', 'SS hall alarm', 220.0 * 4096.0, 226.0 * 4096.0, F * 4096.0, 0.0, 0.0, 0.0, '', '', 1.0, 0.5, 0.5, 1.0,
                         0.0, 5, 4, '', 'explo_02_m', '1', 4.0, 'tba_hackcomp', rule, rule))
    H = alarmai.Hunt(m, nid, g['GRAPHS'], g['GEDGES'], U, A2, LOGIC, pfx='SU', cell_m=24.0, reach_m=150.0, distress_m=28.0, backup_m=45.0, phase_s=10.0, run_m=70.0)
    for x, y, z, gam in BUTTONS:
        H.add_switch((x * 4096.0, y * 4096.0, (F + z) * 4096.0), gam, on='262_01_1', pressed='262_02_1', name='hall alarm button', graph=6)
    for x, y, z, gam in (BUTTONS[0], BUTTONS[3]):          # (judge A5 11-14: the base alert raised no siren - the originals' siren speaker, L12 3079 / spkit.siren: SoundGenerator + an
        sx = x - 1.0 if x < 0.5 * (X0 + X1) else x + 1.0  #  on / off SequenceCommand pair. rc7s18 ear: alarm_50 (vol 1, 50-1000 m) drowned the surface and the ending -> 2 speakers on
        a, b = nid(), nid()                                #  the level def ss_hall_siren (sstruck.SOUNDS: vol 0.6, 5-60 m); sstruck.late() adds 'stop while a cutscene runs')
        m.add_child(LOGIC, T(-1, 'EditRigidObj', 'SS hall alarm siren', sx * 4096.0, y * 4096.0, (F + 2.5) * 4096.0, 0.0, 0.0, 0.0, 'none', 5, False, False, children=[
            T(-1, 'SoundGenerator', '', children=[
                T(a, 'SequenceCommand', '', rule, 'SoundGenerator_PlaySound("ss_hall_siren")', rule, 'SequenceCommand_SetCommand(%d)' % b),
                T(b, 'SequenceCommand', '', '!(%s)' % rule, 'SoundGenerator_StopSound()', '!(%s)' % rule, 'SequenceCommand_SetCommand(%d)' % a)])]))
    SQ = g['SQUAD_IDS']
    keep = {sid for k, (sid, h) in SQ.items() if k.startswith('U ') and h and k not in ('U machine room', 'U tunnel post', 'U tunnel rockets', 'U scientists')}
    excl = [sid for sid in m.find('AISquad') if sid not in keep]
    hold = [SQ[k][0] for k, v in POSTS.items() if v[1]]
    H.build(exclude=excl, only_alarmed=False, open_vars=[U], cry_alarm=False, hold=hold, loud_alarm=True, fight_gate=g.get('COVERAI', False), dead_hold=g.get('DEADHOLD', False))   # (N8 ss-life 11-15; N15 11-17)
    D = g['DBG'] if 'DBG' in g else ''
    if 'g2surf' in D:                                      # (test: a blast by a surface squad at 25 s, far from Jones: their own alarm)
        h = SQ['S generator A yard'][1][0]
        m.add_child(LOGIC, T(nid(), 'ExplodeObject', 'DEBUG surface blast', float(m.arg(h, 3)) + 7.0 * 4096.0, float(m.arg(h, 4)), float(m.arg(h, 5)) + 2400.0, 0.0, 0.0, 0.0, 'none', 'none', 1e6, 2.0, 1.0, 100.0, 0.0, 1, 1, 'LevelFlow_10.nTick > 25 * GAME_FREQUENCY', ''))
    if 'g2blast' in D:                                     # (test: a grenade's blast at the road post at 25 s, no Jones near)
        p = (205.0, 225.0, F + 0.6)
        m.add_child(LOGIC, T(nid(), 'ExplodeObject', 'DEBUG blast', p[0] * 4096.0, p[1] * 4096.0, p[2] * 4096.0, 0.0, 0.0, 0.0, 'none', 'none', 1e6, 3.0, 2.0, 100.0, 0.0, 1, 1, 'LevelFlow_10.nTick > 25 * GAME_FREQUENCY', ''))
    for r_ in H.report:
        print('  hall hunt: ' + r_)
    return H
