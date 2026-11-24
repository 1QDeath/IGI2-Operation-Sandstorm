"""srtrain - al-Rashid's supply train (Sirocco v2 + the end of Sandstorm), 2026-11-03. OWNER: the Sirocco session.
Other missions IMPORT it, never edit it (Sandstorm uses the same cars for its outro).

Six NEW vertex-lit cars (no original passenger coach / mainline loco exists: L12 has only a mine loco + ore wagons), built
with tools/modelkit (the proven gondola path: cablecar.py). They run as native Trains on a rail.py spline (the L12
engine pattern: the lead Train + child Trains = coupled cars), on the ORIGINAL L12 track 417_01_1.

Car frame (same as the L12 cars, measured 11-03): x across (+-1.5 m), y along (+y = the travel direction), z up from the rail
line (0). Floor top FLOOR_Z. Every car has a door gap at BOTH ends (one corridor through the train) and a 0.45 m gangway
plate beyond each end wall, so coupled cars meet plate to plate.

    import srtrain as ST
    lib = modelkit.Library(); ST.add_models(lib); lib.install(OVERLAY, MAP); m.models |= {n.lower() + '.mef' for n in lib.names}
    lead, ids, t = ST.place(nid, spline_id, s_front_m)        # rail.train with the 6 cars, loco first (front)
    ST.local_to_world(line, s_front_m, car, (x, y, z))        # a point inside a car at build time (riders, pickups)

Consist (front -> rear, as rail.train wants the lead first): loco, command coach, freight van, crew coach, MG flatcar, guard van.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import biprefabs as BP
import modelkit as MK
import rail

M = 4096.0
LOCO, CMD, BOX, COACH, FLAT, VAN = 'sr_tr_loco_1', 'sr_tr_cmd_1', 'sr_tr_box_1', 'sr_tr_coach_1', 'sr_tr_flat_1', 'sr_tr_van_1'
CONSIST = [LOCO, CMD, BOX, COACH, FLAT, VAN]               # front -> rear
LENGTH = {LOCO: 18.0, CMD: 22.0, BOX: 14.0, COACH: 22.0, FLAT: 13.0, VAN: 12.0}   # body length (m), plates excluded
PLATE = 0.45                                               # gangway plate beyond each end wall (m)
FLOOR_Z = 1.15                                             # floor top above the rail line (m)
HW = 1.5                                                   # half width of the body (m)
WALL = 0.08
CEIL = FLOOR_Z + 2.45                                      # ceiling (m)
DOOR_HW, DOOR_H = 0.62, 2.1                                # end door gap: half width, height above the floor
SLOTS = ['sr_ochre', 'sr_glass', 'sr_steel', 'sr_cream', 'sr_wood', 'sr_olive', 'sr_rust']
S_OCHRE, S_GLASS, S_STEEL, S_CREAM, S_WOOD, S_OLIVE, S_RUST = range(7)
NAMES = list(CONSIST)


# ------------------------------------------------------------------------------------------------ textures
def _weathered(rgb, n=256, seed=1, dust=0.35):
    rng = np.random.default_rng(seed)
    g = 0.86 + 0.14 * BP._noise(n, rng, 4)
    img = np.dstack([rgb[k] * g for k in range(3)])
    d = np.clip(np.linspace(-0.4, 1.0, n), 0, 1)[:, None] * (0.6 + 0.4 * BP._noise(n, rng, 3))   # dust caked low (v = down)
    w = (dust * d)[:, :, None]
    img = img * (1 - w) + np.array([0.70, 0.58, 0.42]) * w
    return np.clip(np.dstack([img, np.ones((n, n))]), 0, 1)


def add_textures(lib):
    lib.texture('sr_ochre', lambda: _weathered((0.66, 0.48, 0.27), seed=11))
    lib.texture('sr_glass', lambda: np.dstack([np.full((32, 32), 0.55), np.full((32, 32), 0.66), np.full((32, 32), 0.70),
                                               np.full((32, 32), 0.32)]), alpha=True)
    lib.texture('sr_steel', lambda: BP.tex_steel(128, seed=12, base=(0.24, 0.24, 0.25)))
    lib.texture('sr_cream', lambda: _weathered((0.74, 0.70, 0.60), n=128, seed=13, dust=0.15))
    lib.texture('sr_wood', lambda: _weathered((0.42, 0.30, 0.19), n=128, seed=14, dust=0.1))
    lib.texture('sr_olive', lambda: _weathered((0.34, 0.33, 0.21), n=128, seed=15, dust=0.3))
    lib.texture('sr_rust', lambda: _weathered((0.47, 0.22, 0.15), seed=16, dust=0.3))


# ------------------------------------------------------------------------------------------------ geometry
B = BP.box_m


class Car:
    """parts per texture slot + the collision parts"""
    def __init__(self, L):
        self.L, self.h = L, L / 2.0
        self.g = {k: [] for k in range(len(SLOTS))}
        self.coll = []

    def add(self, slot, part, solid=True):
        self.g[slot].append(part)
        if solid:
            self.coll.append(part)

    def model(self):
        groups = [(k, v) for k, v in self.g.items() if v]
        return MK.model(groups, self.coll, atta=getattr(self, 'atta', None), alpha_slots=(S_GLASS,) if self.g[S_GLASS] else ())


def under(c, h):
    """underframe, 2 bogies (4 axles), buffers, the gangway plates"""
    c.add(S_STEEL, B(-HW + 0.1, -h, FLOOR_Z - 0.35, HW - 0.1, h, FLOOR_Z - 0.12), solid=False)
    for by in (-h + 0.18 * 2 * h, h - 0.18 * 2 * h):
        c.add(S_STEEL, B(-1.2, by - 1.4, 0.35, 1.2, by + 1.4, 0.75), solid=False)
        for ay in (by - 0.9, by + 0.9):
            c.add(S_STEEL, BP.cyl_axis(0.42, -0.78, 0.78, 'x', 10, at=(ay, 0.42)), solid=False)
    for ey in (-h, h):
        s = 1 if ey > 0 else -1
        c.add(S_STEEL, B(-DOOR_HW - 0.1, min(ey, ey + s * PLATE), FLOOR_Z - 0.08, DOOR_HW + 0.1, max(ey, ey + s * PLATE), FLOOR_Z))
        for bx in (-1.05, 1.05):
            c.add(S_STEEL, BP.cyl_axis(0.17, min(ey, ey + s * 0.35), max(ey, ey + s * 0.35), 'y', 8, at=(bx, FLOOR_Z - 0.3)), solid=False)


def floor(c, y0, y1, slot=S_WOOD):
    c.add(slot, B(-HW, y0, FLOOR_Z - 0.12, HW, y1, FLOOR_Z))


def end_wall(c, y, inward, slot=S_OCHRE, inner=S_CREAM, top=CEIL):
    """an end wall at y with the door gap (inward = +1 if the car body lies at +y of the wall)"""
    y0, y1 = (y, y + WALL) if inward > 0 else (y - WALL, y)
    for x0, x1 in ((-HW, -DOOR_HW), (DOOR_HW, HW)):
        c.add(slot, B(x0, y0, FLOOR_Z, x1, y1, top))
    c.add(slot, B(-DOOR_HW, y0, FLOOR_Z + DOOR_H, DOOR_HW, y1, top))


def side_walls(c, y0, y1, windows=0, slot=S_OCHRE, inner=S_CREAM, top=CEIL, sill=0.95, head=1.95, openings=()):
    """both long walls from y0 to y1; `windows` glazed openings per side; openings = [(ya, yb)] full-height door gaps"""
    for sx in (-1, 1):
        xa, xb = (HW - WALL, HW) if sx > 0 else (-HW, -HW + WALL)
        cuts = sorted(openings)
        segs, a = [], y0
        for oa, ob in cuts:
            segs.append((a, oa)); a = ob
        segs.append((a, y1))
        for ya, yb in segs:
            if yb - ya < 0.05:
                continue
            if windows:
                c.add(slot, B(xa, ya, FLOOR_Z, xb, yb, FLOOR_Z + sill))
                c.add(slot, B(xa, ya, FLOOR_Z + head, xb, yb, top))
            else:
                c.add(slot, B(xa, ya, FLOOR_Z, xb, yb, top))
        for oa, ob in cuts:                                   # lintels over door openings
            c.add(slot, B(xa, oa, FLOOR_Z + 2.25, xb, ob, top))
        if windows:
            n = windows
            span = (y1 - y0) / n
            for k in range(n):
                wa, wb = y0 + k * span + 0.35, y0 + (k + 1) * span - 0.35
                c.add(slot, B(xa, y0 + k * span, FLOOR_Z + sill, xb, wa, FLOOR_Z + head))        # pier
                c.add(S_GLASS, B(xa + 0.02, wa, FLOOR_Z + sill, xb - 0.02, wb, FLOOR_Z + head))
            c.add(slot, B(xa, y1 - 0.35, FLOOR_Z + sill, xb, y1, FLOOR_Z + head))


def roof(c, y0, y1, slot=S_OLIVE, z=CEIL):
    c.add(slot, B(-HW - 0.06, y0, z, HW + 0.06, y1, z + 0.12))
    c.add(slot, B(-HW + 0.35, y0, z + 0.12, HW - 0.35, y1, z + 0.28))
    for y in np.arange(y0 + 1.0, y1 - 0.5, 2.0):            # (11-04 owner: 'simple boxes up close': roof ribs, ventilators, a rain strip)
        c.add(S_STEEL, B(-HW + 0.05, y - 0.03, CEIL + 0.28, HW - 0.05, y + 0.03, CEIL + 0.33), solid=False)
    for y in np.arange(y0 + 2.5, y1 - 1.5, 5.0):
        c.add(S_STEEL, B(-0.28, y - 0.28, CEIL + 0.28, 0.28, y + 0.28, CEIL + 0.5), solid=False)
        c.add(S_STEEL, B(-0.36, y - 0.36, CEIL + 0.5, 0.36, y + 0.36, CEIL + 0.54), solid=False)
    for sx in (-1, 1):
        c.add(S_STEEL, B(min(sx * (HW + 0.02), sx * (HW + 0.08)), y0, CEIL - 0.1, max(sx * (HW + 0.02), sx * (HW + 0.08)), y1, CEIL - 0.04), solid=False)


def coach_shell(c, windows=8):
    h = c.h
    under(c, h); floor(c, -h, h)
    end_wall(c, -h, +1); end_wall(c, h, -1)
    side_walls(c, -h, h, windows=windows)
    c.add(S_OLIVE, B(-HW - 0.01, -h, FLOOR_Z + 0.75, -HW + 0.0, h, FLOOR_Z + 0.85), solid=False)    # livery stripes
    c.add(S_OLIVE, B(HW, -h, FLOOR_Z + 0.75, HW + 0.01, h, FLOOR_Z + 0.85), solid=False)
    roof(c, -h, h)


def table(c, x0, x1, y0, y1):
    c.add(S_WOOD, B(x0, y0, FLOOR_Z + 0.72, x1, y1, FLOOR_Z + 0.78))
    c.add(S_STEEL, B((x0 + x1) / 2 - 0.05, (y0 + y1) / 2 - 0.05, FLOOR_Z, (x0 + x1) / 2 + 0.05, (y0 + y1) / 2 + 0.05, FLOOR_Z + 0.72))


def bench(c, x0, x1, y0, y1):
    c.add(S_WOOD, B(x0, y0, FLOOR_Z, x1, y1, FLOOR_Z + 0.45))


def build_coach():
    """crew coach: mess tables + benches (rear half), bunks (front half), a stove; the corridor x -0.55..0.55 stays free"""
    c = Car(LENGTH[COACH]); coach_shell(c)
    for sx in (-1, 1):
        xa, xb = (0.6, HW - WALL) if sx > 0 else (-HW + WALL, -0.6)
        for ty in (-8.2, -4.4):
            table(c, xa, xb, ty - 0.45, ty + 0.45)
            bench(c, xa, xb, ty - 1.05, ty - 0.65); bench(c, xa, xb, ty + 0.65, ty + 1.05)
        for by in (1.2, 4.6):                                  # bunks, two levels
            for bz in (0.45, 1.55):
                c.add(S_OLIVE, B(xa, by, FLOOR_Z + bz, xb, by + 2.0, FLOOR_Z + bz + 0.18))
            c.add(S_STEEL, B(xa if sx < 0 else xb - 0.06, by, FLOOR_Z, (xa + 0.06) if sx < 0 else xb, by + 0.06, FLOOR_Z + 1.9))
    c.add(S_STEEL, B(0.75, 9.3, FLOOR_Z, 1.35, 10.0, FLOOR_Z + 0.85))                    # stove
    c.add(S_STEEL, BP.cyl_z(0.08, FLOOR_Z + 0.85, CEIL + 0.5, 8, 1.05, 9.65), solid=False)
    return c.model()


def build_cmd():
    """command coach: radio desk, map table, a partition with a door, Fadhil's desk (the arming case sits at its edge)"""
    c = Car(LENGTH[CMD]); coach_shell(c)
    table(c, 0.75, HW - WALL, -9.2, -6.6)                                                # radio desk
    c.add(S_STEEL, B(1.05, -9.0, FLOOR_Z + 0.78, HW - WALL, -7.0, FLOOR_Z + 1.25))         # radio sets
    table(c, -HW + WALL, -0.65, -2.2, 1.2)                                               # map table
    for x0, x1 in ((-HW, -0.6), (0.6, HW)):                                              # partition with a door gap
        c.add(S_CREAM, B(x0, 4.0, FLOOR_Z, x1, 4.08, CEIL))
    c.add(S_CREAM, B(-0.6, 4.0, FLOOR_Z + 2.1, 0.6, 4.08, CEIL))
    table(c, 0.62, HW - WALL, 6.2, 8.8)                                                  # Fadhil's desk
    c.add(S_OLIVE, B(-HW + WALL, 7.0, FLOOR_Z, -0.9, 9.6, FLOOR_Z + 0.5))                # cot
    c.add(S_STEEL, BP.cyl_z(0.04, CEIL + 0.28, CEIL + 2.4, 6, 0.0, 8.5), solid=False)     # radio mast
    return c.model()


def build_box():
    """freight van: no windows, open side doors (2 m), ammo crates stacked off the corridor"""
    c = Car(LENGTH[BOX]); h = c.h
    under(c, h); floor(c, -h, h)
    end_wall(c, -h, +1, slot=S_RUST, top=CEIL); end_wall(c, h, -1, slot=S_RUST, top=CEIL)
    side_walls(c, -h, h, windows=0, slot=S_RUST, openings=[(-1.0, 1.0)])
    roof(c, -h, h, slot=S_RUST)
    for x0, x1, y0, y1, z in ((-HW + WALL, -0.55, -6.2, -2.4, 1.4), (0.55, HW - WALL, 2.4, 6.2, 1.8), (0.55, HW - WALL, -6.2, -4.4, 0.9),
                              (-HW + WALL, -0.55, 4.0, 6.2, 1.2)):
        c.add(S_OLIVE, B(x0, y0, FLOOR_Z, x1, y1, FLOOR_Z + z))
    return c.model()


def build_flat():
    """MG flatcar: a deck, sandbag walls along the sides, a twin MG on a pedestal right of the corridor"""
    c = Car(LENGTH[FLAT]); h = c.h
    under(c, h); floor(c, -h, h, slot=S_STEEL)
    for sx in (-1, 1):
        c.add(S_OLIVE, B(sx * HW - (0.35 if sx > 0 else 0), -h + 1.0, FLOOR_Z, sx * HW + (0.35 if sx < 0 else 0), h - 1.0, FLOOR_Z + 0.85))
    for x0, x1, y0, y1 in ((0.55, 1.15, -1.6, -1.1), (0.55, 1.15, 1.1, 1.6)):
        c.add(S_OLIVE, B(x0, y0, FLOOR_Z, x1, y1, FLOOR_Z + 0.85))
    c.add(S_STEEL, BP.cyl_z(0.16, FLOOR_Z, FLOOR_Z + 1.1, 10, 0.85, 0.0))                  # pedestal
    c.add(S_STEEL, B(0.6, -0.35, FLOOR_Z + 1.1, 1.1, 0.35, FLOOR_Z + 1.35), solid=False)
    for bz in (1.2, 1.3):
        c.add(S_STEEL, BP.cyl_axis(0.035, 0.85, 2.3, 'x', 6, at=(0.0, FLOOR_Z + bz)), solid=False)
    for ey, s in ((-h, 1), (h, -1)):                                                     # low end rails (gap in the middle)
        for x0, x1 in ((-HW, -DOOR_HW), (DOOR_HW, HW)):
            c.add(S_STEEL, B(x0, min(ey, ey + s * 0.06), FLOOR_Z, x1, max(ey, ey + s * 0.06), FLOOR_Z + 1.0))
    return c.model()


def build_van():
    """guard van: the open rear balcony (Jones lands here: side steps + rails), the body with a stove, a bench and a bunk"""
    c = Car(LENGTH[VAN]); h = c.h
    under(c, h); floor(c, -h, h)
    by = -h + 1.6                                                                         # body starts behind the balcony
    end_wall(c, by, +1, slot=S_OCHRE); end_wall(c, h, -1, slot=S_OCHRE)
    side_walls(c, by, h, windows=2)
    roof(c, by - 0.6, h)
    for sx in (-1, 1):                                                                    # balcony rails: side rails with a step gap
        xa, xb = (HW - 0.06, HW) if sx > 0 else (-HW, -HW + 0.06)
        c.add(S_STEEL, B(xa, -h + 0.9, FLOOR_Z, xb, by, FLOOR_Z + 1.0))
        c.add(S_STEEL, B(sx * HW - 0.3 * sx - 0.15, -h + 0.05, FLOOR_Z - 0.75, sx * HW - 0.3 * sx + 0.15, -h + 0.85, FLOOR_Z - 0.6))   # step
    for x0, x1 in ((-HW, -DOOR_HW), (DOOR_HW, HW)):                                       # rear rail (gap = the end door line)
        c.add(S_STEEL, B(x0, -h, FLOOR_Z, x1, -h + 0.06, FLOOR_Z + 1.0))
    c.add(S_STEEL, B(0.8, h - 1.4, FLOOR_Z, HW - WALL, h - 0.7, FLOOR_Z + 0.85))           # stove
    c.add(S_STEEL, BP.cyl_z(0.07, FLOOR_Z + 0.85, CEIL + 0.6, 8, 1.1, h - 1.05), solid=False)
    bench(c, -HW + WALL, -0.7, by + 0.6, h - 2.4)
    c.add(S_OLIVE, B(0.75, by + 0.6, FLOOR_Z + 0.5, HW - WALL, by + 2.6, FLOOR_Z + 0.68))   # bunk
    return c.model()


def build_loco():
    """diesel loco, cab at the REAR (Jones comes in from the command coach): cab body with windows, the control desk at the
    cab's front wall (the route control is used standing in front of it), a long hood forward"""
    c = Car(LENGTH[LOCO]); h = c.h
    under(c, h); floor(c, -h, -h + 5.0)
    cab0, cab1 = -h, -h + 5.0
    end_wall(c, cab0, +1)
    side_walls(c, cab0, cab1, windows=2, openings=[(cab0 + 0.6, cab0 + 1.5)])
    for x0, x1 in ((-HW, -DOOR_HW), (DOOR_HW, HW)):                                       # cab front wall with the windscreen
        c.add(S_OCHRE, B(x0, cab1 - WALL, FLOOR_Z, x1, cab1, CEIL))
    c.add(S_OCHRE, B(-DOOR_HW, cab1 - WALL, FLOOR_Z, DOOR_HW, cab1, FLOOR_Z + 1.1))
    c.add(S_GLASS, B(-DOOR_HW, cab1 - WALL + 0.02, FLOOR_Z + 1.1, DOOR_HW, cab1 - 0.02, FLOOR_Z + 1.95))
    c.add(S_OCHRE, B(-DOOR_HW, cab1 - WALL, FLOOR_Z + 1.95, DOOR_HW, cab1, CEIL))
    roof(c, cab0, cab1)
    c.add(S_STEEL, B(-0.9, cab1 - 0.75, FLOOR_Z, 0.9, cab1 - WALL, FLOOR_Z + 1.0))          # control desk
    c.add(S_STEEL, B(-0.9, cab1 - 0.75, FLOOR_Z + 1.0, 0.9, cab1 - 0.45, FLOOR_Z + 1.12), solid=False)
    for sx in (-1, 1) if LOCO_SEATS else ():
        c.add(S_OLIVE, B(sx * 0.75 - 0.25, cab1 - 1.6, FLOOR_Z, sx * 0.75 + 0.25, cab1 - 1.1, FLOOR_Z + 0.5))   # seats
    c.add(S_OCHRE, B(-1.15, cab1, FLOOR_Z - 0.12, 1.15, h - 0.6, FLOOR_Z + 2.2))             # long hood
    c.add(S_OLIVE, B(-1.16, cab1 + 0.4, FLOOR_Z + 1.1, 1.16, h - 1.0, FLOOR_Z + 1.25), solid=False)   # stripe
    c.add(S_STEEL, B(-0.25, cab1 + 2.0, FLOOR_Z + 2.2, 0.25, cab1 + 2.6, FLOOR_Z + 2.6), solid=False)  # exhaust
    c.add(S_OCHRE, B(-HW, h - 0.6, FLOOR_Z - 0.12, HW, h, FLOOR_Z + 1.6))                    # nose
    c.add(S_STEEL, B(-HW, h - 0.05, FLOOR_Z - 0.3, HW, h + 0.05, FLOOR_Z + 0.1), solid=False)  # chevron plate
    if LOCO_EXTRA:
        LOCO_EXTRA(c, h, cab1)
    return c.model()


BUILD = {LOCO: build_loco, CMD: build_cmd, BOX: build_box, COACH: build_coach, FLAT: build_flat, VAN: build_van}


LOCO_SEATS = True                                           # (False: a mission whose crew stands, tools/ssoutro.py)
LOCO_EXTRA = None                                           # (detail a mission adds to the loco: tools/ssoutro.py)
CAR_SLOTS = {}                                              # (a car with its own texture list: tools/ssoutro.py)


def add_models(lib):
    add_textures(lib)
    for nm in CONSIST:
        lib.add(nm, BUILD[nm], CAR_SLOTS.get(nm, SLOTS), lod_like='740_01_1')
    return NAMES


# ------------------------------------------------------------------------------------------------ placing the train
def pitch(nm):
    """collision length along y (body + both plates): the engine spaces coupled cars by it (L12 loco: coll 10.01 m = its
    calibrated pitch 10.0). NOT measured for these cars yet - the 11-03 spike checks it."""
    return LENGTH[nm] + 2 * PLATE


def offsets(consist=CONSIST):
    """distance of every car's centre behind the lead car's centre (m)"""
    out, d = [0.0], 0.0
    for k in range(1, len(consist)):
        d += 0.5 * (pitch(consist[k - 1]) + pitch(consist[k]))
        out.append(d)
    return out


def place(nid, spline_id, s_front_m, disp_x=rail.PLAYER_X, consist=CONSIST, name='SR supply train', car_kids=None, accel=0.05):
    """rail.train with the consist (lead = the loco at s_front_m) -> (lead id, [car ids front -> rear], task)"""
    return rail.train(nid, spline_id, s_front_m, [(nm, False) for nm in consist], disp_x, name=name, car_kids=car_kids, accel=accel)


def local_to_world(line, s_front_m, car_index, p_local_m, disp_x=rail.PLAYER_X, consist=CONSIST):
    """a point given in car `car_index`'s frame (x across, y along, z up from the rail line) -> world units at build time"""
    s_c = s_front_m - offsets(consist)[car_index]
    x, y, z = p_local_m
    return line.on_track(s_c, disp_x, fwd_m=y, side_m=x, up_m=z + rail.DISP_Z)


def yaw_on(line, s_m):
    """IGI yaw (gamma) facing the travel direction at s_m"""
    return line.gamma(s_m)


def place_separate(nid, spline_id, s_lead_m, disp_x=rail.PLAYER_X, consist=CONSIST, name='SR supply train', accel=0.05):
    """(Sandstorm v4 11-03, additive) every car as its OWN lead Train at its own arc position (centre = s_lead - offsets[k]):
    the rig showed coupled child Trains of these cars all piled up at the lead (the engine's spacing does not come from
    pitch() for them). Drive them with one AnimTask each, all on the same keys, so they move as one -> ([ids], [tasks])"""
    ids, tasks_ = [], []
    for k, (nm, off) in enumerate(zip(consist, offsets(consist))):
        i, _, t = rail.train(nid, spline_id, s_lead_m - off, [(nm, False)], disp_x, name='%s car %d (%s)' % (name, k + 1, nm), accel=accel)
        ids.append(i); tasks_.append(t)
    return ids, tasks_
