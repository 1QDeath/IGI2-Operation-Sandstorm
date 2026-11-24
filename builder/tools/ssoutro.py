"""ssoutro - Sandstorm's second ending (owner 11-05 items 46-51), behind env SS_OUTRO2=1 until proven. Shot list: work/sandstorm/outro/SHOTLIST.md.
Jones hides in a crate in the freight van, three Hinds land, men run in and search, General Dhari says hunt him, they board and the train pulls out.

Called from build_sandstorm.py with its globals():
  world(G)     before navgen: the loading platform
  prepare(G)   before X.finish: Hind models, the two new cars, the door leaves, the crate lids; puts the freight van second from the rear
  keys(G)      in section 8b: -> (camera keys, captions) in place of the old OUTRO
  stage(G)     after CSO exists: helicopters, men, doors, train, sound cues

Facts this rests on (rig + originals):
- `run_forward` is not a clip: the men of the first ending stood still. Clips below are checked against work/originals/data/anim_durations.json at build time.
- The map's 740_01_1 has its blades in the hull. 720_01_1 has rotors as RotateAttachment, a real cabin behind a sliding left door, wheels 4.16 m under its origin.
- A man = the invisible carrier 'lot' on spline legs (L11's rig) + one EditBoneObj per phase. A list that ends holds its last pose, so idling phases loop.
- A spline for an object inside a ConditionalContainer must sit outside it.
- Cutscene clocks: CutScene_n.nTick > T * GAME_FREQUENCY.
"""
import copy, json, math, os, random
import numpy as np
import atmos, biprefabs as BP, mefmesh, modelkit as MK, srgunship as SGS, srtrain as ST, rail
import ssbase as SB
import ssbay
import ssvsound as VS
import cutscene as CS
from mission_lib import T, v
from qast import lit, tasks
from igiqvm import Call

M = 4096.0
HERE = os.path.dirname(os.path.abspath(__file__))
# (X3_TRANSITIONS.md 11-16: the engine plays clips at 4800 ticks/s; anim_durations.json divided by 4096, so every length was ~17 % too long: a list ended early and
#  its man stood frozen in the last pose until the next phase (Jones kneeling 0.8 s after his landing, review S8_a_049-050). Every clip is a whole number of 160-tick
#  frames (1/30 s): real seconds = round(json * 4096 / 160) / 30. SS_CLIP4096=1 = the old lengths, for A/B only)
CLIPS = {k: (d['sec'] if os.environ.get('SS_CLIP4096') == '1' else round(d['sec'] * 25.6) / 30.0)
         for k, d in json.load(open(os.path.join(HERE, '..', 'work', 'originals', 'data', 'anim_durations.json'))).items()}
BLEND = float(os.environ.get('SS_BLEND', '0.3'))   # (A8 + X3_TRANSITIONS.md: Transition time of every ending actor; 0 = no blender = a one-frame snap at every clip change)
# ---- cars and props
COACHD, FRT, CDOOR, FDOOR, LID, PLAT = 'ss_o_coach_1', 'ss_o_frt_1', 'ss_o_cdr_1', 'ss_o_fdr_1', 'ss_o_lid_1', 'ss_o_plat_1'
K_LOCO, K_CMD, K_COACH, K_FLAT, K_FRT, K_VAN = range(6)
def _slots(body):
    """texture list of a car: the srtrain slots with this car's paint on the body and rust slots, 8 m tiles everywhere"""
    return [body, 'so_glass', 'so_steel', 'so_cream', 'so_wood', 'so_roof', body]


C_SLOTS = _slots('so_coach')
F_SLOTS = _slots('so_box') + ['so_crate', 'so_carton', 'so_tarp', 'so_board']
S_CRATE, S_CARTON, S_TARP, S_BOARD = len(ST.SLOTS), len(ST.SLOTS) + 1, len(ST.SLOTS) + 2, len(ST.SLOTS) + 3
DOOR_Y, DOOR_HW = 8.0, 0.68        # coach side doors: centre along the car, half width
FDOOR_HW = 1.12                    # freight side door half width
CRATE = (-1.40, 1.50, -0.20, 3.10, 1.25)   # hero crate in the freight van: x0, y0, x1, y1, height (car frame, from the floor)
NCRATE = (0.58, 1.50, 1.40, 3.00, 0.75)    # the crate the soldier opens (owner 106: 16 cm further over; owner 119 rc7m: his shins and hands went through its 1.25 m slats while he leaned in:
#                                             tba_filing_search puts the legs 0.77 m ahead of the root and the hands at 0.8-1.06 m: a low crate he leans OVER, 8 cm more aisle)
# ---- the loading platform (world m)
PX0, PX1, PY0, PY1 = 430.0, 478.0, 206.92, 212.6
RAMP_X0 = 414.0
STAIR_X0, STAIR_X1, STAIR_RUN = 443.6, 447.4, 2.6
# ---- landing zones: (x, y, gamma): the cabin door is on the left, so each lands left side to where its men go
LZ_A = (446.0, 238.0, math.pi / 2)      # north of the line, nose west
LZ_B = (416.0, 172.0, -math.pi / 2)     # south of the line, nose east
LZ_C = (364.0, 164.0, 0.0)              # short of the sand door, nose north
HIND = '720_01_1'
FEED = 'ss_o_feed_1'
GEN2 = os.environ.get('SS_GEN2', '1') == '1'           # (owner 100: ss-general's footage-review scene, tools/ssgeneral.py; off = the scene below)
SCREEN = 'ss_o_scrn_1'
FAN_LENS = (431.0, 211.6)                                  # m, the fan shot's lens
FOOT_CAM = (247.4, 232.6, SB.F + 3.0)                      # m, the lens of the chip replay
F_GATE = 60.0                                              # m under the hall: the sealed copy of the hall for the gate replay
F_SET = 30.0                                               # m under the hall: the sealed set of the chip replay
F_SKIP = 2.4                                               # s into tba_sabotage at the cut: the lid is coming up
F_CUT, F_RUN = 3.0, 3.4                                    # s (owner 93, 94): the silent lock box replay, the gate replay
AXLES = ['ss_o_ax%d_1' % k_ for k_ in range(4)]             # (one model per ATTA row: the row is found by its name)
AXLE_R = 0.42
TURN_L = 0.0                        # cars at least this long have turning wheels (ssprune leaves room: VNAM rows + 28 against the cap of 600, ATTA rows do not count)
WHEELS = 4.16                      # m from the hull's origin down to its wheels
CABIN_Z, CABIN = -2.72, [(0.3, 3.3), (0.3, 2.2), (0.3, 1.2), (-0.5, 3.3), (-0.5, 2.2), (-0.5, 1.2), (0.3, 0.3), (-0.5, 0.3), (0.75, 2.7), (0.75, 1.7)]   # cabin floor + spots (hull frame)
DOOR_LOCAL = (-1.234, 2.281, -1.22)
RUN = 'stand_run_forward'
SIT_DZ = -0.55                     # guard_in_back_of_truck sits this far above its root (rig o2e)
TRUCK_SEAT = (-3.2, 0.42, 0.2)     # driver's root from a parked ss_trk_1's origin (nose = -x): x, y, z m


def _clip(name):
    assert name in CLIPS, 'no such clip: %s' % name
    return CLIPS[name]


# ------------------------------------------------------------------------------------------------ models
TILE_M = 2.5                       # the car bodies map one texture over 2.5 x 2.5 m: the game's own panel and plank textures at their real size (owner 107)
UV = 1.0 / TILE_M


def _tex_glass(n=64):
    """window glass: dusty, blue-grey, a soft sky reflection across it. Seen through, not a hole in the wall"""
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    s = np.clip(1.0 - np.abs(u + v * 0.6 - 0.75) * 3.0, 0, 1) * 0.28
    return np.clip(np.dstack([0.34 + s, 0.42 + s, 0.46 + s, 0.42 + s * 0.6]), 0, 1)


def _car_paint(rgb, band, seed, ribs=0.0, dark_low=(0.20, 0.19, 0.16)):
    """an 8 x 8 m tile: row = z / 8 * n (car frame, z up, rail line 0). Steel panels with seams and rivets, a belt line, dust caked low, rust and rain runs"""
    n = 512
    rng = np.random.default_rng(seed)
    g = 0.88 + 0.16 * BP._noise(n, rng, 5)
    img = np.dstack([rgb[k] * g for k in range(3)])
    px = lambda m_: int(m_ / TILE_M * n)
    if band is not None:                                   # the coloured band under the windows
        img[px(ST.FLOOR_Z):px(ST.FLOOR_Z + 0.82), :] = np.array(band) * g[px(ST.FLOOR_Z):px(ST.FLOOR_Z + 0.82), :, None]
    img[px(ST.FLOOR_Z + 0.82):px(ST.FLOOR_Z + 0.87), :] *= 0.55
    for k in range(4):                                     # panel seams every 2 m, a rivet row each side of them
        x = px(1.0 + 2.0 * k)
        img[:, x - 1:x + 1] *= 0.5
        for dx in (-5, 5):
            img[(np.arange(n) % 14) < 3, x + dx - 1:x + dx + 1] *= 0.72
    if ribs:                                               # pressed ribs of a freight van
        for k in range(int(TILE_M / ribs)):
            x = px(k * ribs)
            img[:, x:x + 5] *= 1.16; img[:, x + 5:x + 8] *= 0.66
    for row in (px(ST.FLOOR_Z - 0.02), px(ST.CEIL - 0.1)):
        img[row - 2:row + 2, :] *= 0.5
    for k in range(70):                                    # rain and rust runs from the roof line and the seams
        x, y0 = int(rng.integers(0, n)), px(ST.CEIL - rng.uniform(0.0, 1.8))
        L = int(rng.integers(14, 90)); w = int(rng.integers(1, 4))
        tint = np.array((0.34, 0.20, 0.12)) if k % 3 else np.array((0.16, 0.14, 0.12))
        img[max(y0 - L, 0):y0, x:x + w] = img[max(y0 - L, 0):y0, x:x + w] * 0.72 + tint * 0.28
    z = np.linspace(0.0, TILE_M, n)[:, None]               # sand caked up from the frame
    d = (np.clip((ST.FLOOR_Z + 0.9 - z) / 1.1, 0, 1) * (0.62 + 0.38 * BP._noise(n, rng, 3)))[:, :, None] * 0.55
    img = img * (1 - d) + np.array((0.60, 0.49, 0.34)) * d
    return np.clip(np.dstack([img, np.ones((n, n))]), 0, 1)


def _tex_roof(n=256, seed=35):
    rng = np.random.default_rng(seed)
    g = 0.78 + 0.26 * BP._noise(n, rng, 5)
    img = np.dstack([0.30 * g, 0.29 * g, 0.26 * g])
    return np.clip(np.dstack([img, np.ones((n, n))]), 0, 1)


def _tex_door(n=256, seed=36):
    """one door leaf: dark green paint, an inset panel, a kick plate, a bright worn edge round the handle"""
    rng = np.random.default_rng(seed)
    g = 0.86 + 0.16 * BP._noise(n, rng, 4)
    img = np.dstack([0.15 * g, 0.21 * g, 0.16 * g])
    img[:10, :] = img[-10:, :] = 0.10
    img[:, :10] = img[:, -10:] = 0.10
    img[24:90, 24:-24] *= 1.25
    img[16:22, 16:-16] = (0.42, 0.42, 0.40)
    return np.clip(np.dstack([img, np.ones((n, n))]), 0, 1)


def _tex_crate(n=256, seed=31):
    return BP.tex_planks(n, seed=seed, base=(0.50, 0.38, 0.24))


def _tex_carton(n=128, seed=32):
    rng = np.random.default_rng(seed)
    g = 0.9 + 0.1 * BP._noise(n, rng, 3)
    img = np.dstack([0.56 * g, 0.42 * g, 0.26 * g])
    img[n // 2 - 3:n // 2 + 3, :] = (0.72, 0.64, 0.46)      # packing tape
    return np.clip(np.dstack([img, np.ones((n, n))]), 0, 1)


def _tex_tarp(n=128, seed=33):
    rng = np.random.default_rng(seed)
    g = 0.8 + 0.2 * BP._noise(n, rng, 4)
    return np.clip(np.dstack([0.30 * g, 0.31 * g, 0.20 * g, np.ones((n, n))]), 0, 1)


_under0, _box_m = ST.under, BP.box_m
BW = lambda *a_: _box_m(*a_, uv=1.0)


def under2(c, h):
    """srtrain's underframe + what the eye expects of a bogie: side frames, leaf springs, axle boxes, a brake pipe"""
    c.add(ST.S_STEEL, ST.B(-ST.HW + 0.1, -h, ST.FLOOR_Z - 0.35, ST.HW - 0.1, h, ST.FLOOR_Z - 0.12), solid=False)
    rows = []
    for by in (-h + 0.36 * h, h - 0.36 * h):
        c.add(ST.S_STEEL, ST.B(-0.55, by - 1.4, 0.35, 0.55, by + 1.4, 0.75), solid=False)       # (narrow: the turning wheels are the axles' own models, out at x 0.66-0.8)
        rows += [by - 0.9, by + 0.9]
    if c.L >= TURN_L:
        at = np.zeros(4, mefmesh.ATTA_DT)
        for k_, y_ in enumerate(rows):
            at[k_]['name'] = AXLES[k_].encode()
            at[k_]['pos'] = (0.0, y_ * M, AXLE_R * M)
            at[k_]['rot'] = np.eye(3)
            at[k_]['i0'], at[k_]['i1'] = 0, -1
        c.atta = at
    else:
        for y_ in rows:
            for a_, b_ in ((-0.8, -0.66), (0.66, 0.8)):
                c.add(ST.S_STEEL, BP.cyl_axis(AXLE_R, a_, b_, 'x', 12, at=(y_, AXLE_R)), solid=False)
    for ey in (-h, h):
        s = 1 if ey > 0 else -1
        c.add(ST.S_STEEL, ST.B(-ST.DOOR_HW - 0.1, min(ey, ey + s * ST.PLATE), ST.FLOOR_Z - 0.08, ST.DOOR_HW + 0.1, max(ey, ey + s * ST.PLATE), ST.FLOOR_Z))
        for bx in (-1.05, 1.05):
            c.add(ST.S_STEEL, BP.cyl_axis(0.17, min(ey, ey + s * 0.35), max(ey, ey + s * 0.35), 'y', 8, at=(bx, ST.FLOOR_Z - 0.3)), solid=False)
    for by in (-h + 0.36 * h, h - 0.36 * h):
        for sx in (-1, 1):
            xa, xb = (sx * 0.84, sx * 0.94) if sx > 0 else (sx * 0.94, sx * 0.84)
            c.add(ST.S_STEEL, ST.B(xa, by - 1.5, 0.52, xb, by + 1.5, 0.74), solid=False)
            for ay in (by - 0.9, by + 0.9):
                c.add(ST.S_STEEL, ST.B(xa - 0.03, ay - 0.16, 0.26, xb + 0.03, ay + 0.16, 0.6), solid=False)
            for k in range(4):
                c.add(ST.S_STEEL, ST.B(xa, by - 0.5 + k * 0.06, 0.74 + k * 0.03, xb, by + 0.5 - k * 0.06, 0.77 + k * 0.03), solid=False)
    c.add(ST.S_STEEL, ST.B(-0.05, -h, ST.FLOOR_Z - 0.5, 0.05, h, ST.FLOOR_Z - 0.42), solid=False)


def trim(c, y0, y1, top=ST.FLOOR_Z + 2.24):
    """a door frame proud of both long walls, a tread under it, grab rails each side"""
    for sx in (-1, 1):
        a, b = (ST.HW, ST.HW + 0.035) if sx > 0 else (-ST.HW - 0.035, -ST.HW)
        c.add(ST.S_STEEL, ST.B(a, y0 - 0.07, ST.FLOOR_Z - 0.04, b, y0, top + 0.07), solid=False)
        c.add(ST.S_STEEL, ST.B(a, y1, ST.FLOOR_Z - 0.04, b, y1 + 0.07, top + 0.07), solid=False)
        c.add(ST.S_STEEL, ST.B(a, y0 - 0.07, top, b, y1 + 0.07, top + 0.07), solid=False)
        o0, o1 = (ST.HW, ST.HW + 0.3) if sx > 0 else (-ST.HW - 0.3, -ST.HW)
        c.add(ST.S_STEEL, ST.B(o0, y0, ST.FLOOR_Z - 0.46, o1, y1, ST.FLOOR_Z - 0.40), solid=False)
        for y in (y0 - 0.14, y1 + 0.11):
            c.add(ST.S_STEEL, ST.B(a + 0.05 * sx, y, ST.FLOOR_Z + 0.3, b + 0.05 * sx, y + 0.03, ST.FLOOR_Z + 1.5), solid=False)


def windows(c, sx, a, b, n, sill=0.85, head=2.0):
    """piers + glass + a bright aluminium frame round each pane"""
    xa, xb = (ST.HW - ST.WALL, ST.HW) if sx > 0 else (-ST.HW, -ST.HW + ST.WALL)
    span = (b - a) / n
    fa, fb = (ST.HW, ST.HW + 0.02) if sx > 0 else (-ST.HW - 0.02, -ST.HW)
    for k in range(n):
        wa, wb = a + k * span + 0.22, a + (k + 1) * span - 0.22
        c.add(ST.S_OCHRE, ST.B(xa, a + k * span, ST.FLOOR_Z + sill, xb, wa, ST.FLOOR_Z + head))
        c.add(ST.S_OCHRE, ST.B(xa, wb, ST.FLOOR_Z + sill, xb, a + (k + 1) * span, ST.FLOOR_Z + head))
        c.add(ST.S_GLASS, ST.B(xa + 0.02, wa, ST.FLOOR_Z + sill, xb - 0.02, wb, ST.FLOOR_Z + head))
        for y0_, z0_, y1_, z1_ in ((wa, sill, wb, sill + 0.05), (wa, head - 0.05, wb, head), (wa, sill, wa + 0.05, head), (wb - 0.05, sill, wb, head),
                                   ((wa + wb) / 2 - 0.02, sill, (wa + wb) / 2 + 0.02, head)):
            c.add(ST.S_CREAM, ST.B(fa, y0_, ST.FLOOR_Z + z0_, fb, y1_, ST.FLOOR_Z + z1_), solid=False)


def boards(c, y):
    """the data plate on both long sides, reading the right way round"""
    for sx in (-1, 1):
        n_r = (0.0, sx * 1.0, 0.0)
        p = MK.panel((sx * (ST.HW + 0.012), y, ST.FLOOR_Z + 0.5), n_r, (0.0, 0.0, 1.0), 1.3, 0.32)
        c.add(S_BOARD, p, solid=False)


def loco_detail(c, h, cab1):
    """the long hood stops being a box: engine doors and louvres along it, a walkway rail, a nose with lamps and warning bars (the last shot looks straight at it)"""
    Z = ST.FLOOR_Z
    S, O, K = ST.S_STEEL, ST.S_OCHRE, ST.S_CREAM
    for sx in (-1, 1):
        a, b = (1.15, 1.19) if sx > 0 else (-1.19, -1.15)
        for k in range(6):
            y0 = cab1 + 0.5 + k * 1.75
            c.add(S, ST.B(a, y0, Z + 0.25, b, y0 + 1.5, Z + 0.3), solid=False)
            c.add(S, ST.B(a, y0, Z + 1.9, b, y0 + 1.5, Z + 1.95), solid=False)
            c.add(S, ST.B(a, y0, Z + 0.25, b, y0 + 0.05, Z + 1.95), solid=False)
            c.add(S, ST.B(a, y0 + 1.45, Z + 0.25, b, y0 + 1.5, Z + 1.95), solid=False)
            for q in range(5):
                c.add(S, ST.B(a - 0.01 * sx, y0 + 0.3, Z + 1.3 + q * 0.09, b + 0.01 * sx, y0 + 1.2, Z + 1.34 + q * 0.09), solid=False)
        ra, rb = (1.42, 1.46) if sx > 0 else (-1.46, -1.42)
        c.add(S, ST.B(ra, cab1, Z + 1.0, rb, h - 0.7, Z + 1.04), solid=False)
        for y in np.arange(cab1 + 0.3, h - 0.6, 2.2):
            c.add(S, ST.B(ra, y, Z, rb, y + 0.04, Z + 1.0), solid=False)
    for k in range(5):                                     # the nose: warning bars
        x = -1.35 + k * 0.56
        c.add(K, ST.B(x, h, Z - 0.05, x + 0.28, h + 0.02, Z + 1.5), solid=False)
    c.add(S, ST.B(-0.5, h, Z + 1.15, 0.5, h + 0.06, Z + 1.5), solid=False)
    for x in (-0.3, 0.3):                                  # headlamps
        c.add(K, BP.cyl_axis(0.13, h + 0.06, h + 0.14, 'y', 10, at=(x, Z + 1.33)), solid=False)
    c.add(S, ST.B(-1.15, h - 0.6, Z + 2.2, 1.15, h - 0.5, Z + 2.26), solid=False)


CAB_L = 5.0                                                # m, the loco's cab at its front end (owner 107)


def build_loco_front():
    """owner 107: a driver's cab at the very FRONT of the loco: a split windscreen with corner posts, the control desk under it (gauges,
    throttle and brake levers, a brake wheel, switches), the door at its back, the long hood behind it. Only for this ending (srtrain keeps its own)"""
    c = ST.Car(ST.LENGTH[ST.LOCO]); h = c.h
    B, Z, W, HW = ST.B, ST.FLOOR_Z, ST.WALL, ST.HW
    O, G_, S, K, R = ST.S_OCHRE, ST.S_GLASS, ST.S_STEEL, ST.S_CREAM, ST.S_RUST
    cab0 = h - CAB_L
    ST.under(c, h); ST.floor(c, cab0, h)
    ST.end_wall(c, cab0, +1)                                 # the cab's back wall, door through to the hood walkway
    ST.side_walls(c, cab0, h, windows=2, openings=[(cab0 + 0.6, cab0 + 1.5)])
    ST.roof(c, cab0, h)
    # the front: low wall, two windscreens with a centre post, a header band; the nose plate slopes out below
    c.add(O, B(-HW, h - W, Z, HW, h, Z + 1.15))
    for x0, x1 in ((-HW + 0.12, -0.06), (0.06, HW - 0.12)):
        c.add(G_, B(x0, h - W + 0.02, Z + 1.15, x1, h - 0.02, Z + 2.0))
    for x0, x1 in ((-HW, -HW + 0.12), (-0.06, 0.06), (HW - 0.12, HW)):
        c.add(O, B(x0, h - W, Z + 1.15, x1, h, Z + 2.0))
    c.add(O, B(-HW, h - W, Z + 2.0, HW, h, ST.CEIL))
    c.add(O, B(-HW, h, Z - 0.12, HW, h + 0.55, Z + 0.95))             # nose below the windscreen
    c.add(S, B(-HW, h + 0.5, Z - 0.3, HW, h + 0.6, Z + 0.1), solid=False)   # buffer beam
    for k in range(6):                                                # warning bars on the nose
        x = -1.38 + k * 0.5
        c.add(K, B(x, h + 0.55, Z - 0.05, x + 0.25, h + 0.57, Z + 0.9), solid=False)
    for x in (-0.95, 0.95):                                           # headlamps and their hoods
        c.add(K, BP.cyl_axis(0.14, h + 0.55, h + 0.63, 'y', 12, at=(x, Z + 0.6)), solid=False)
        c.add(S, B(x - 0.2, h + 0.55, Z + 0.78, x + 0.2, h + 0.75, Z + 0.82), solid=False)
    c.add(K, BP.cyl_axis(0.12, h + 0.0, h + 0.08, 'y', 12, at=(0.0, Z + 2.25)), solid=False)   # top lamp over the windscreen
    for x in (-0.75, 0.75):                                           # wipers
        c.add(S, B(x - 0.01, h + 0.005, Z + 1.2, x + 0.01, h + 0.02, Z + 1.75), solid=False)
    c.add(S, B(-0.5, h + 0.005, Z + 2.05, 0.5, h + 0.03, Z + 2.25), solid=False)   # number board frame
    # the control desk under the windscreen: a sloped top in two steps, gauges, levers, a brake wheel, a switch panel
    d0 = h - 0.95
    c.add(S, B(-HW + W, d0, Z, HW - W, h - W, Z + 0.85))
    c.add(S, B(-HW + W, d0, Z + 0.85, HW - W, d0 + 0.35, Z + 0.93), solid=False)
    c.add(S, B(-HW + W, d0 + 0.35, Z + 0.93, HW - W, h - W, Z + 1.06), solid=False)
    c.add(R, B(-HW + W, d0 + 0.35, Z + 1.06, HW - W, h - W, Z + 1.08), solid=False)   # its dark top
    for x in (-1.05, -0.8, -0.55, 0.55, 0.8, 1.05):                   # round gauges, faces towards the driver
        c.add(K, BP.cyl_axis(0.075, d0 + 0.33, d0 + 0.355, 'y', 14, at=(x, Z + 0.99)), solid=False)
        c.add(R, B(x - 0.004, d0 + 0.325, Z + 0.99, x + 0.004, d0 + 0.33, Z + 1.05), solid=False)   # the needle
    for x in (-0.25, -0.1, 0.1, 0.25):                                # switch row
        c.add(K, B(x - 0.03, d0 + 0.12, Z + 0.93, x + 0.03, d0 + 0.18, Z + 0.96), solid=False)
    for x, hgt in ((0.35, 0.28), (0.48, 0.22)):                       # throttle and brake levers with knobs (driver's side)
        c.add(S, B(x - 0.015, d0 + 0.08, Z + 0.9, x + 0.015, d0 + 0.12, Z + 0.9 + hgt), solid=False)
        c.add(R, BP.cyl_axis(0.03, x - 0.04, x + 0.04, 'x', 8, at=(d0 + 0.1, Z + 0.92 + hgt)), solid=False)
    c.add(S, BP.cyl_axis(0.16, d0 - 0.02, d0 + 0.01, 'y', 16, at=(-0.45, Z + 0.95)), solid=False)   # brake wheel
    c.add(S, B(-0.46, d0 - 0.01, Z + 0.78, -0.44, d0 + 0.02, Z + 1.12), solid=False)
    c.add(S, B(-0.62, d0 - 0.01, Z + 0.94, -0.28, d0 + 0.02, Z + 0.96), solid=False)
    c.add(K, B(-HW + W, h - 0.45, Z + 1.95, -0.2, h - W, Z + 2.0), solid=False)   # sun visor
    c.add(R, B(HW - 0.5, cab0 + 0.2, Z, HW - W, cab0 + 0.65, Z + 1.3), solid=False)   # a locker at the back
    # the long hood behind the cab: doors and louvres, walkway rails, exhaust, the rear end plate
    c.add(O, B(-1.15, -h + 0.6, Z - 0.12, 1.15, cab0, Z + 2.2))
    c.add(ST.S_OLIVE, B(-1.16, -h + 1.0, Z + 1.1, 1.16, cab0 - 0.4, Z + 1.25), solid=False)
    c.add(S, B(-0.25, cab0 - 2.6, Z + 2.2, 0.25, cab0 - 2.0, Z + 2.6), solid=False)
    c.add(O, B(-HW, -h, Z - 0.12, HW, -h + 0.6, Z + 1.6))
    for sx in (-1, 1):
        a, b = (1.15, 1.19) if sx > 0 else (-1.19, -1.15)
        for k in range(6):
            y0 = -h + 0.9 + k * 1.75
            if y0 + 1.5 > cab0 - 0.2:
                break
            c.add(S, B(a, y0, Z + 0.25, b, y0 + 1.5, Z + 0.3), solid=False)
            c.add(S, B(a, y0, Z + 1.9, b, y0 + 1.5, Z + 1.95), solid=False)
            c.add(S, B(a, y0, Z + 0.25, b, y0 + 0.05, Z + 1.95), solid=False)
            c.add(S, B(a, y0 + 1.45, Z + 0.25, b, y0 + 1.5, Z + 1.95), solid=False)
            for q in range(5):
                c.add(S, B(a - 0.01 * sx, y0 + 0.3, Z + 1.3 + q * 0.09, b + 0.01 * sx, y0 + 1.2, Z + 1.34 + q * 0.09), solid=False)
        ra, rb = (1.42, 1.46) if sx > 0 else (-1.46, -1.42)
        c.add(S, B(ra, -h + 0.6, Z + 1.0, rb, cab0, Z + 1.04), solid=False)
        for y in np.arange(-h + 0.9, cab0, 2.2):
            c.add(S, B(ra, y, Z, rb, y + 0.04, Z + 1.0), solid=False)
    return c.model()


def _liner(c, y0, y1, z0, z1):
    """cream inside face on the long walls"""
    for sx in (-1, 1):
        x = sx * (ST.HW - ST.WALL)
        c.add(ST.S_CREAM, ST.B(min(x, x - sx * 0.012), y0, ST.FLOOR_Z + z0, max(x, x - sx * 0.012), y1, ST.FLOOR_Z + z1), solid=False)


def build_coachd():
    """the crew coach with sliding side doors at both ends and facing bench bays along the windows; the aisle x -0.55..0.55 stays free"""
    c = ST.Car(ST.LENGTH[COACHD]); h = c.h
    ST.under(c, h); ST.floor(c, -h, h)
    ST.end_wall(c, -h, +1); ST.end_wall(c, h, -1)
    gaps = [(-DOOR_Y - DOOR_HW, -DOOR_Y + DOOR_HW), (DOOR_Y - DOOR_HW, DOOR_Y + DOOR_HW)]
    a, b = gaps[0][1], gaps[1][0]
    for sx in (-1, 1):
        xa, xb = (ST.HW - ST.WALL, ST.HW) if sx > 0 else (-ST.HW, -ST.HW + ST.WALL)
        for ya, yb in ((-h, gaps[0][0]), (gaps[1][1], h)):
            c.add(ST.S_OCHRE, ST.B(xa, ya, ST.FLOOR_Z, xb, yb, ST.CEIL))
        for oa, ob in gaps:
            c.add(ST.S_OCHRE, ST.B(xa, oa, ST.FLOOR_Z + 2.2, xb, ob, ST.CEIL))
        c.add(ST.S_OCHRE, ST.B(xa, a, ST.FLOOR_Z, xb, b, ST.FLOOR_Z + 0.85))
        c.add(ST.S_OCHRE, ST.B(xa, a, ST.FLOOR_Z + 2.0, xb, b, ST.CEIL))
        windows(c, sx, a, b, 6)
        c.add(ST.S_OLIVE, ST.B(sx * ST.HW - 0.005, -h, ST.FLOOR_Z + 0.7, sx * ST.HW + 0.005, h, ST.FLOOR_Z + 0.8), solid=False)
        xs0, xs1 = (0.6, ST.HW - ST.WALL) if sx > 0 else (-ST.HW + ST.WALL, -0.6)
        for by in BAYS:
            for ey in (by - 1.05, by + 1.05):
                c.add(ST.S_WOOD, ST.B(xs0, ey - 0.22, ST.FLOOR_Z, xs1, ey + 0.22, ST.FLOOR_Z + 0.45))
                s = 1 if ey > by else -1
                c.add(ST.S_WOOD, ST.B(xs0, min(ey + s * 0.22, ey + s * 0.3), ST.FLOOR_Z, xs1, max(ey + s * 0.22, ey + s * 0.3), ST.FLOOR_Z + 1.05))
    for oa, ob in gaps:
        trim(c, oa, ob)
    _liner(c, -h, gaps[0][0], 0.0, 2.45); _liner(c, gaps[1][1], h, 0.0, 2.45)
    for ye, s_ in ((-h + ST.WALL, 1), (h - ST.WALL, -1)):    # (judge 107: the end walls were flat dark green inside: the cream face round the door)
        y0_, y1_ = sorted((ye, ye + s_ * 0.012))
        for x0_, x1_ in ((-ST.HW + ST.WALL, -ST.DOOR_HW), (ST.DOOR_HW, ST.HW - ST.WALL)):
            c.add(ST.S_CREAM, ST.B(x0_, y0_, ST.FLOOR_Z, x1_, y1_, ST.CEIL), solid=False)
        c.add(ST.S_CREAM, ST.B(-ST.DOOR_HW, y0_, ST.FLOOR_Z + ST.DOOR_H, ST.DOOR_HW, y1_, ST.CEIL), solid=False)
    _liner(c, a, b, 0.0, 0.85); _liner(c, a, b, 2.0, 2.45)
    ST.roof(c, -h, h)
    return c.model()


BAYS = (-5.2, -1.3, 2.6)            # bench bays along the coach (y of the middle)
MORE = {K_CMD: [], K_FLAT: []}   # (men who go on past the coach. Owner 11-15 S21 / PLAN decision 3: no riflemen in the command car right behind the cab - seen through
                                 #  its windows in 'pull' they read as the train's drivers holding guns. All ten troopers ride in the coach)
SEATS = [(sx * 1.0, by + s * 1.05, 0 if s < 0 else math.pi) for by in BAYS for sx in (1, -1) for s in (-1, 1)]    # (x, y, facing: 0 = +y along the car)


class FCar(ST.Car):
    def __init__(self, L):
        super().__init__(L)
        self.g = {k: [] for k in range(len(F_SLOTS))}


def _crate_body(c, x0, y0, x1, y1, H, slat=0.075, gap=0.09, post=0.07, slit=None, slit_x=None, backed=False):
    """a slatted crate open at the top: four corner posts, slats with gaps, a floor. Boxes, so it reads from inside and outside"""
    Z = ST.FLOOR_Z
    c.add(S_CRATE, BW(x0, y0, Z, x1, y1, Z + 0.05))
    for px, py in ((x0, y0), (x1 - post, y0), (x0, y1 - post), (x1 - post, y1 - post)):
        c.add(S_CRATE, BW(px, py, Z, px + post, py + post, Z + H))
    z = Z + 0.08
    t = 0.022
    while z + slat <= Z + H + 1e-6:
        for a_, b_ in (((z, Z + slit[0]), (Z + slit[1], z + slat)) if slit and z < Z + slit[1] and z + slat > Z + slit[0] else ((z, z + slat),)):
            if b_ > a_:
                c.add(S_CRATE, BW(x0, y0, a_, x1, y0 + t, b_))
        if slit and slit_x and z < Z + slit[1] and z + slat > Z + slit[0]:   # (judge H10/F12: the slit only where he looks through it, the rest of the plank closed)
            a_, b_ = max(z, Z + slit[0]), min(z + slat, Z + slit[1])
            for u0, u1 in ((x0, slit_x[0]), (slit_x[1], x1)):
                if u1 > u0:
                    c.add(S_CRATE, BW(u0, y0, a_, u1, y0 + t, b_))
        c.add(S_CRATE, BW(x0, y1 - t, z, x1, y1, z + slat))
        c.add(S_CRATE, BW(x0, y0, z, x0 + t, y1, z + slat))
        c.add(S_CRATE, BW(x1 - t, y0, z, x1, y1, z + slat))
        z += slat + gap
    if backed:                                             # (rc7k K2: the 12 mm seams between the planks showed the van behind his head: a board behind each wall, the slit window left open)
        b_ = 0.006
        z0_, z1_ = Z + 0.08, Z + H
        c.add(S_CRATE, BW(x0, y1, z0_, x1, y1 + b_, z1_))
        c.add(S_CRATE, BW(x0 - b_, y0, z0_, x0, y1, z1_))
        c.add(S_CRATE, BW(x1, y0, z0_, x1 + b_, y1, z1_))
        if slit and slit_x:
            c.add(S_CRATE, BW(x0, y0 - b_, z0_, x1, y0, Z + slit[0]))
            c.add(S_CRATE, BW(x0, y0 - b_, Z + slit[1], x1, y0, z1_))
            c.add(S_CRATE, BW(x0, y0 - b_, Z + slit[0], slit_x[0], y0, Z + slit[1]))
            c.add(S_CRATE, BW(slit_x[1], y0 - b_, Z + slit[0], x1, y0, Z + slit[1]))
        else:
            c.add(S_CRATE, BW(x0, y0 - b_, z0_, x1, y0, z1_))


def _stack(c, x0, y0, x1, y1, rows, slot=S_CARTON, n=2, z0=None):
    """cartons in rows, a few cm apart so they read as packages; solid"""
    z = ST.FLOOR_Z if z0 is None else z0
    dz = 0.36
    for r in range(rows):
        w, d = (x1 - x0) / n, (y1 - y0) / n
        for i in range(n):
            for j in range(n):
                o = 0.018 if (r + i + j) % 2 else 0.04
                c.add(slot, BW(x0 + i * w + o, y0 + j * d + o, z, x0 + (i + 1) * w - o, y0 + (j + 1) * d - o, z + dz - 0.012))
        z += dz
    return z


def build_frt():
    """the freight van: side doors in the middle, stacks of crates and packages both ways, the hero crate by the north wall of the front half"""
    c = FCar(ST.LENGTH[FRT]); h = c.h
    ST.under(c, h); ST.floor(c, -h, h)
    ST.end_wall(c, -h, +1, slot=ST.S_RUST); ST.end_wall(c, h, -1, slot=ST.S_RUST)
    ST.side_walls(c, -h, h, windows=0, slot=ST.S_RUST, openings=[(-FDOOR_HW, FDOOR_HW)])
    ST.roof(c, -h, h, slot=ST.S_RUST)
    trim(c, -FDOOR_HW, FDOOR_HW, top=ST.FLOOR_Z + 2.3)
    for sx in (-1, 1):                                     # the rail the leaf hangs from, and its bottom guide
        a, b = (ST.HW, ST.HW + 0.09) if sx > 0 else (-ST.HW - 0.09, -ST.HW)
        c.add(ST.S_STEEL, ST.B(a, -FDOOR_HW - 0.2, ST.FLOOR_Z + 2.32, b, 3.6, ST.FLOOR_Z + 2.42), solid=False)
        c.add(ST.S_STEEL, ST.B(a, -FDOOR_HW - 0.2, ST.FLOOR_Z - 0.06, b, 3.6, ST.FLOOR_Z + 0.02), solid=False)
    for y in np.arange(-h + 0.25, h, 0.5):                 # pressed ribs along both walls, the leaf's run left clear
        if abs(y) < FDOOR_HW + 0.1:
            continue
        for sx in (-1, 1):
            a, b = (ST.HW, ST.HW + 0.04) if sx > 0 else (-ST.HW - 0.04, -ST.HW)
            c.add(ST.S_RUST, ST.B(a, y - 0.05, ST.FLOOR_Z + 0.05, b, y + 0.05, ST.CEIL - 0.1), solid=False)
    boards(c, -3.8)
    # (owner 67: he climbed in and stuck among the boxes) collision only: no way into the crates or down the narrow gaps, the floor between the doors stays free
    Z = ST.FLOOR_Z
    for x0_, y0_, x1_, y1_, H_ in (CRATE, NCRATE):
        c.coll.append(ST.B(x0_, y0_, Z + H_ - 0.02, x1_, y1_, Z + 2.6))
    c.coll.append(ST.B(-1.42, 1.42, Z, 1.42, 1.5, Z + 2.6))
    c.coll.append(ST.B(-1.42, -1.5, Z, 1.42, -1.42, Z + 2.6))
    for sx in (-1, 1):                                     # the step up at the door
        c.add(ST.S_STEEL, ST.B(min(sx * 1.5, sx * 1.72), -1.0, ST.FLOOR_Z - 0.62, max(sx * 1.5, sx * 1.72), 1.0, ST.FLOOR_Z - 0.55))
    _crate_body(c, *CRATE, slat=0.1565, gap=0.012, slit=(0.60, 0.74), slit_x=(-0.62, -0.12), backed=True)   # (owner 88: nearly closed, one gap he looks through, on the side towards the door;
    #                                                       judge H10: only 50 cm of it, where the 'slat1' lens looks out at x -0.37: behind his head in the close-ups it showed the van)
    _crate_body(c, *NCRATE)
    x0, y0, x1, y1, H = NCRATE
    for k in range(3):                                     # packages in the crate the soldier opens
        c.add(S_CARTON, BW(x0 + 0.08, y0 + 0.08 + k * 0.45, ST.FLOOR_Z + 0.05, x1 - 0.08, y0 + 0.47 + k * 0.45, ST.FLOOR_Z + 0.55))
    # the lid of the hero crate waits on this stack, as high as the crate
    _stack(c, CRATE[0], CRATE[3] + 0.05, CRATE[2], CRATE[3] + 1.7, 3, slot=S_CRATE, n=1, z0=ST.FLOOR_Z + 0.17)
    c.add(S_CRATE, BW(CRATE[0], CRATE[3] + 0.05, ST.FLOOR_Z, CRATE[2], CRATE[3] + 1.7, ST.FLOOR_Z + 0.17))
    _stack(c, NCRATE[0], NCRATE[3] + 0.05, NCRATE[2], NCRATE[3] + 1.7, 2, slot=S_CRATE, n=1, z0=ST.FLOOR_Z + 0.03)   # (its lid slides onto this: as high as the crate)
    c.add(S_CRATE, BW(NCRATE[0], NCRATE[3] + 0.05, ST.FLOOR_Z, NCRATE[2], NCRATE[3] + 1.7, ST.FLOOR_Z + 0.03))
    for x0, x1, y0, y1, rows, slot in ((-1.40, -0.60, -6.8, -5.2, 4, S_CARTON), (-1.40, -0.60, -5.1, -3.4, 5, S_CARTON), (-1.40, -0.60, -3.3, -1.5, 3, S_CARTON),
                                       (0.60, 1.40, -6.8, -5.2, 5, S_CARTON), (0.60, 1.40, -5.1, -3.4, 3, S_CARTON), (0.60, 1.40, -3.3, -1.5, 4, S_CARTON),
                                       (-1.40, -0.60, 4.9, 6.8, 5, S_CARTON), (0.60, 1.40, 4.9, 6.8, 4, S_CARTON)):
        top = _stack(c, x0, y0, x1, y1, rows, slot)
        if rows == 3:
            c.add(S_TARP, ST.B(x0 - 0.02, y0 - 0.02, top, x1 + 0.02, y1 + 0.02, top + 0.05), solid=False)
    return c.model()


def build_cdoor():
    """a coach door leaf: origin at its centre, along y, 8 cm thick, a small window"""
    c = ST.Car(2.0)
    hw, H = DOOR_HW + 0.03, 2.22
    z = lambda a: a - H / 2
    B = lambda *a_: BP.box_m(*a_, uv=0.42)
    c.add(ST.S_OCHRE, B(-0.03, -hw, z(0), 0.03, hw, z(1.1)))
    c.add(ST.S_OCHRE, B(-0.03, -hw, z(1.75), 0.03, hw, z(H)))
    for a, b in ((-hw, -0.32), (0.32, hw)):
        c.add(ST.S_OCHRE, B(-0.03, a, z(1.1), 0.03, b, z(1.75)))
    c.add(ST.S_GLASS, B(-0.012, -0.32, z(1.1), 0.012, 0.32, z(1.75)))
    for sx in (-1, 1):                                     # handle on both faces
        c.add(ST.S_OCHRE, BP.cyl_axis(0.016, z(0.85), z(1.2), 'z', 6, at=(sx * 0.07, -hw + 0.12)) if False else B(min(sx * 0.03, sx * 0.075), -hw + 0.1, z(0.85), max(sx * 0.03, sx * 0.075), -hw + 0.14, z(1.2)), solid=False)
    return MK.model([(ST.S_OCHRE, c.g[ST.S_OCHRE]), (ST.S_GLASS, c.g[ST.S_GLASS])], c.coll, alpha_slots=(ST.S_GLASS,))


def build_fdoor():
    """a freight door leaf: planks + steel bands, origin at its centre"""
    c = ST.Car(2.0)
    hw, H = FDOOR_HW + 0.05, 2.3
    z = lambda a: a - H / 2
    c.add(ST.S_RUST, ST.B(-0.03, -hw, z(0), 0.03, hw, z(H)))
    for a in (0.3, 1.15, 2.0):
        c.add(ST.S_STEEL, ST.B(-0.045, -hw, z(a - 0.04), 0.045, hw, z(a + 0.04)), solid=False)
    for k in range(9):                                     # ribs like the van, a long handle
        y = -hw + 0.08 + k * 0.28
        c.add(ST.S_RUST, ST.B(-0.05, y, z(0.05), 0.05, y + 0.07, z(H - 0.05)), solid=False)
    c.add(ST.S_STEEL, ST.B(-0.07, -hw + 0.06, z(0.8), 0.07, -hw + 0.1, z(1.5)), solid=False)
    return MK.model([(ST.S_RUST, c.g[ST.S_RUST]), (ST.S_STEEL, c.g[ST.S_STEEL])], c.coll)


def build_lid():
    """a crate lid: six boards with gaps you can see light through, origin at its centre, along y"""
    c = FCar(2.0)
    x0, y0, x1, y1 = CRATE[:4]
    w, d = (x1 - x0) / 2 + 0.02, (y1 - y0) / 2 + 0.02
    n = 6; sp = 2 * w / n
    for k in range(n):
        c.add(S_CRATE, BW(-w + k * sp + 0.012, -d, 0.0, -w + (k + 1) * sp - 0.012, d, 0.035))
    for y in (-d + 0.08, d - 0.08):
        c.add(S_CRATE, BW(-w, y - 0.05, 0.035, w, y + 0.05, 0.06))
    return MK.model([(S_CRATE, c.g[S_CRATE])], c.coll)


_SSLV = []


def _orig(name, rgb=None, n=512, keep=0.35):
    """owner 107 (the cars looked like Lego): a texture of the game's own Sandstorm bank, tinted to `rgb` with its detail kept"""
    import prefab, igitex
    from PIL import Image
    if not _SSLV:
        _SSLV.append(prefab.Level(os.path.join(prefab.GAME, 'MISSIONS', 'multiplayer', 'sandstorm')))
    a_ = np.asarray(igitex.decode(_SSLV[0].find_resource('LOCAL:textures/%s.tex' % name, 'textures')[1]), float)
    if a_.max() > 1.5:
        a_ = a_ / 255.0
    if a_.shape[0] != n:
        a_ = np.asarray(Image.fromarray((np.clip(a_, 0, 1) * 255).astype('uint8')).resize((n, n), Image.LANCZOS), float) / 255.0
    rgb_ = a_[..., :3]
    if rgb is not None:
        m_ = rgb_.reshape(-1, 3).mean(0) + 1e-3
        rgb_ = rgb_ * (np.array(rgb) / m_) * (1 - keep) + rgb_ * keep
    return np.dstack([np.clip(rgb_, 0, 1), np.ones(rgb_.shape[:2])])


def _tex_feed():
    """the video wall: real frames of Jones from the base's own cameras (work/sandstorm/outro/feed.png)"""
    from PIL import Image
    a_ = np.asarray(Image.open(os.path.join(HERE, '..', 'work', 'sandstorm', 'outro', 'feed.png')).convert('RGB'), float) / 255.0
    return np.dstack([a_, np.ones(a_.shape[:2])])


def build_axle():
    """an axle with its two wheels, origin on the hub, turning about x: dark wheels, pale spokes and one pale crank mark so the turning reads"""
    w_ = [BP.cyl_axis(0.05, -0.8, 0.8, 'x', 8, at=(0.0, 0.0))]
    for a_, b_ in ((-0.8, -0.66), (0.66, 0.8)):
        w_.append(BP.cyl_axis(AXLE_R, a_, b_, 'x', 16, at=(0.0, 0.0)))
    sp = []

    def turned(x0, x1, y0, y1, z0, z1, a_):
        P, T_, N, U = BW(x0, y0, z0, x1, y1, z1)
        c_, s_ = math.cos(a_), math.sin(a_)
        R = np.array([[1.0, 0.0, 0.0], [0.0, c_, -s_], [0.0, s_, c_]])
        return (P @ R.T, T_, N @ R.T, U)
    for sx in (-1.0, 1.0):
        xa, xb = sorted((sx * 0.8, sx * 0.815))
        for k_ in range(3):
            sp.append(turned(xa, xb, -0.04, 0.04, -AXLE_R + 0.03, AXLE_R - 0.03, k_ * math.pi / 3))
        sp.append(turned(xa, xb, -0.1, 0.1, 0.12, AXLE_R - 0.03, 0.0))
    return MK.model([(0, w_), (1, sp)], [BP.box_m(-0.02, -0.02, -0.02, 0.02, 0.02, 0.02)])


def build_wall():
    """3.4 x 1.3 m of monitors on a steel frame, screens facing +y, origin at the wall behind its middle"""
    w, h = 3.4, 1.3
    y0 = -0.35                                             # (the origin stands 0.5 m in front of the screens)
    s_ = MK.panel((0.0, y0 + 0.1, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), w, h)
    st_ = []
    for a_ in (-w / 2, -w / 2 + 2.0, w / 2):
        st_.append(BW(a_ - 0.04, y0, -h / 2 - 0.05, a_ + 0.04, y0 + 0.12, h / 2 + 0.05))
    for z_ in (-h / 2, 0.0, h / 2):
        st_.append(BW(-w / 2, y0, z_ - 0.04, w / 2, y0 + 0.12, z_ + 0.04))
    return MK.model([(0, [s_]), (1, st_)], st_)


def build_set():
    """the sealed copy of the guidance bay the replay is shot in: floor, the missile's skin to the east, a railed wall to the north. Origin at (248.0, 236.0) on its floor"""
    st_ = [BW(-5.0, -6.0, -0.2, 2.0, 7.0, 0.0), BW(-5.0, -6.0, 5.5, 2.0, 7.0, 5.7), BW(-5.2, -6.0, 0.0, -5.0, 7.0, 5.5), BW(-5.0, -6.2, 0.0, 2.0, -6.0, 5.5),
           BW(-5.0, 5.2, 0.0, 2.0, 5.4, 5.5)]
    sk_ = [BW(0.78, -6.0, 0.0, 1.0, 7.0, 5.5)]
    for z_ in (1.0, 1.9):
        sk_.append(BW(-5.0, 5.05, z_, 0.78, 5.2, z_ + 0.07))
    for k_ in range(5):
        sk_.append(BW(-4.6 + 1.2 * k_, 5.05, 0.0, -4.52 + 1.2 * k_, 5.2, 2.0))
    return MK.model([(0, st_), (1, sk_)], [BW(-5.0, -6.0, -0.2, 2.0, 7.0, 0.0)])


def add_models(lib):
    if not GEN2:                                           # (owner 100: ss-general's scene places no video wall: its LOD row back)
        lib.texture('so_feed', _tex_feed)
        lib.add(FEED, build_wall, ['so_feed', 'so_steel'], lod_like='740_01_1')
    if ssbay.BAY:
        lib.add(SCREEN, build_set, ['jr_dark', 'jr_steel'], lod_like='740_01_1')
    for k_ in AXLES:
        lib.add(k_, build_axle, ['so_steel', 'so_whl'], lod_like='740_01_1')
    lib.texture('so_whl', lambda: BP.tex_flat((0.66, 0.63, 0.56)))
    lib.texture('so_glass', _tex_glass, alpha=True)
    # (owner 107: the game's own textures, no more noise colours: painted and riveted steel, ribbed roofs, weathered boards)
    lib.texture('so_coach', lambda: _orig('406_48_1', (0.55, 0.52, 0.40)))
    lib.texture('so_loco', lambda: _orig('406_49_1', (0.24, 0.29, 0.20)))
    lib.texture('so_van', lambda: _orig('406_48_1', (0.22, 0.27, 0.19)))
    lib.texture('so_box', lambda: _orig('431_11_1', (0.36, 0.19, 0.13)))
    lib.texture('so_steel', lambda: _orig('400_83_1', (0.17, 0.17, 0.18)))
    lib.texture('so_wood', lambda: _orig('433_03_1', (0.34, 0.27, 0.19)))
    lib.texture('so_cream', lambda: _orig('409_10_1', (0.62, 0.60, 0.52)))
    lib.texture('so_roof', lambda: _orig('433_10_1', (0.20, 0.20, 0.19))); lib.texture('so_door', lambda: _orig('406_48_1', (0.55, 0.52, 0.40)))   # (judge 107 leftover: the flat green leaf with its pane floating in it: the coach's own panels)
    lib.texture('so_board', lambda: BP.tex_text(['I.R.R.  40417', 'TARE 24 T   LOAD 40 T'], size=(512, 128), bg=(0.10, 0.10, 0.10), fg=(0.82, 0.80, 0.70)))
    lib.texture('so_crate', lambda: _orig('433_01_1', (0.45, 0.34, 0.21)));   # (judge: flat-shaded boxes: the game's weathered boards)
    lib.texture('so_carton', lambda: _orig('231_33_1'));   # (judge 107 leftover: the tinted plain card read as flat orange: the game's own labelled carton, untinted)
    lib.texture('so_tarp', _tex_tarp)
    lib.add(CDOOR, build_cdoor, ['so_door', 'so_glass'], lod_like='740_01_1')
    lib.add(FDOOR, build_fdoor, _slots('so_box'), lod_like='740_01_1')
    lib.add(LID, build_lid, F_SLOTS, lod_like='740_01_1')


def use_consist():
    """loco, command coach, door coach, MG flatcar, freight van, guard van: Jones's freight van second from the rear. STR's own list, in place, so
    the builder's calls stay as they are; car indices 0 and 5 keep their meaning"""
    for old, new in ((ST.COACH, COACHD), (ST.BOX, FRT)):
        ST.LENGTH[new] = ST.LENGTH.pop(old)
    ST.CONSIST[:] = [ST.LOCO, ST.CMD, COACHD, ST.FLAT, FRT, ST.VAN]
    ST.NAMES[:] = list(ST.CONSIST)
    ST.BUILD[COACHD], ST.BUILD[FRT] = build_coachd, build_frt
    ST.CAR_SLOTS.update({COACHD: C_SLOTS, FRT: F_SLOTS, ST.CMD: C_SLOTS, ST.LOCO: _slots('so_loco'), ST.VAN: _slots('so_van'), ST.FLAT: _slots('so_van')})
    ST.B = lambda *a_, **k_: _box_m(*a_, uv=UV)
    ST.under = under2
    ST.LOCO_EXTRA = loco_detail
    ST.BUILD[ST.LOCO] = build_loco_front                     # (owner 107: the cab at the very front)
    ST.LOCO_SEATS = False                                  # (owner 88: the crew's legs went into them)


def _plat_mesh(G):
    z = G['RAIL_Z'] + rail.DISP_Z + ST.FLOOR_Z
    gz0 = 6.2
    me = SB.Mesh(((PX0 + PX1) / 2, (PY0 + PY1) / 2, z), ['so_conc', 'so_edge'])
    me.box('so_conc', PX0, PY0, gz0, PX1, PY1, z, uv=0.25)
    me.box('so_edge', PX0, PY0, z - 0.02, PX1, PY0 + 0.32, z + 0.008, uv=1.0, solid=False)
    me.box(None, RAMP_X0, PY0 - 0.2, z - 0.1, PX1, PY0, z)    # (rig p1: Jones dropped into the slot between coach and platform: nothing to see, nothing to fall into)
    me.hull('so_conc', [(RAMP_X0, y_, z_) for y_ in (PY0, PY1) for z_ in (gz0, 7.72)] + [(PX0, y_, z_) for y_ in (PY0, PY1) for z_ in (gz0, z)], uv=0.25)
    n = 9
    for k in range(n):                                     # the stairs up from the desert, north side
        zt = z - (k + 1) * (z - 6.9) / n
        me.box('so_conc', STAIR_X0, PY1 + k * STAIR_RUN / n, gz0, STAIR_X1, PY1 + (k + 1) * STAIR_RUN / n, zt, uv=0.25)
    return me


GROUND_DZ = 0.12                   # the sand sheet above the terrain under the railhead (men stand on it)


def _dune_mesh(G):
    """(owner 11-07 'camera at the end of the map') past x 404 the fine terrain map ends and the coarse one is a pale flat plane. A sand sheet over it, with real
    dunes beyond the railhead and along both sides of the line, so no shot looks onto the plane. No collision: within 0.12 m of the ground where anybody walks"""
    bh = G['_bh']
    xs = np.arange(392.0, 680.1, 7.0); ys = np.arange(96.0, 330.1, 7.0)
    X, Y = np.meshgrid(xs, ys, indexing='ij')
    base = np.vectorize(bh)(X, Y)

    def smooth(a_, b_, v_):
        s_ = np.clip((v_ - a_) / (b_ - a_), 0.0, 1.0)
        return s_ * s_ * (3 - 2 * s_)
    far = np.maximum(smooth(250.0, 300.0, Y), smooth(165.0, 120.0, Y))    # north and south of the working area
    far = np.maximum(far, smooth(195.0, 165.0, Y) * smooth(520.0, 570.0, X))
    far = far * smooth(392.0, 430.0, X) * (1.0 - smooth(190.0, 196.0, Y) * smooth(222.0, 216.0, Y))
    n = 2.6 * (np.sin(X * 0.031 + Y * 0.014) + 1.0) + 1.5 * (np.sin(X * 0.013 - Y * 0.041 + 1.2) + 1.0) + 0.7 * np.sin(X * 0.07 + Y * 0.05)
    Z = base + GROUND_DZ + far * n
    Z = Z + 1.6 * np.exp(-((X - 492.0) / 14.0) ** 2 - ((Y - 188.0) / 6.0) ** 2)   # (a low dune in the lower left of 'pull')
    Z = Z - 1.2 * (1.0 - smooth(392.0, 406.0, X))           # the west edge goes under the fine terrain
    rim = np.minimum.reduce([smooth(96.0, 110.0, Y), smooth(330.0, 316.0, Y), smooth(680.0, 666.0, X)])
    Z = Z * rim + (base - 1.0) * (1 - rim)
    Zx, Zy = np.gradient(Z, 7.0, 7.0)
    N_ = np.dstack([-Zx, -Zy, np.ones_like(Z)]); N_ /= np.linalg.norm(N_, axis=2, keepdims=True)
    o = np.array([(xs[0] + xs[-1]) / 2, (ys[0] + ys[-1]) / 2, float(Z.mean())])
    me = SB.Mesh(o, ['ss_sand'])
    nx, ny = X.shape
    P = np.dstack([X - o[0], Y - o[1], Z - o[2]]).reshape(-1, 3) * M
    U = np.dstack([X / 26.0, Y / 26.0]).reshape(-1, 2)
    Tr = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a_, b_, c_, d_ = i * ny + j, (i + 1) * ny + j, (i + 1) * ny + j + 1, i * ny + j + 1
            Tr += [(a_, c_, b_), (a_, d_, c_)]                # (clockwise seen from above)
    me.g['ss_sand'].append((P, np.array(Tr), N_.reshape(-1, 3), U))
    me.box(None, o[0], o[1], o[2] - 30.0, o[0] + 0.2, o[1] + 0.2, o[2] - 29.8)
    return me


TRUCKS = ((431.0, 221.0, 0.25), (472.0, 222.0, -0.2))      # parked by the platform: x, y, yaw


def world(G):
    """before navgen: the loading platform north of the line, stairs to the LZ, a ramp at its west end"""
    lib, m, nid = G['_VLIB'], G['m'], G['nid']
    lib.texture('so_conc', lambda: BP.tex_concrete(256, seed=34, base=(0.60, 0.53, 0.42)))
    lib.texture('so_edge', lambda: BP.tex_flat((0.72, 0.62, 0.22)))
    du = _dune_mesh(G)
    lib.add('ss_o_dune_1', lambda: du.model(), du.slots, lod_like='406_68_1')
    m.add_child(G['HALL'], T(nid(), 'EditRigidObj', 'SS sand at the railhead', *[float(c_) * M for c_ in du.o], 0.0, 0.0, 0.0, 'ss_o_dune_1', 5, False, False))
    me = _plat_mesh(G)
    lib.add(PLAT, lambda: me.model(), me.slots, lod_like='406_68_1')
    m.add_child(G['HALL'], T(nid(), 'EditRigidObj', 'SS loading platform', *[float(c_) * M for c_ in me.o], 0.0, 0.0, 0.0, PLAT, 5, False, False))
    z = float(me.o[2])
    # (judge Q15: the three crates on the platform sat tilted and half sunk in it from the satellite pass: gone)
    for k_, (x, y, yw) in enumerate(TRUCKS):
        m.add_child(G['HALL'], T(nid(), 'EditRigidObj', 'SS truck at the railhead %d' % (k_ + 1), x * M, y * M, G['_bh'](x, y) * M, 0.0, 0.0, yw, 'ss_trk_1', 5, False, False))
    print('ssoutro: platform top z %.2f, x %.0f..%.0f' % (z, PX0, PX1))


def prepare(G):
    """before the builder's train: the consist, Hind models, leaves and lids"""
    G['X'].models('location1/LEVEL7', [HIND, '720_02_1', '720_03_1', '720_04_1'])
    add_models(G['_VLIB'])
    atm = G['_atmos']
    for t_ in ('RotateAttachment', 'SoundGenerator', 'SequenceCommand', 'Smoke', 'EditBoneObj'):
        atm.ensure_decl(G['m'], t_)
    if GEN2:
        __import__('ssgeneral').models(G)


# ------------------------------------------------------------------------------------------------ the timeline
SHOTS = [('run', 3.4), ('in', 2.2), ('crate', 3.6), ('drop', 3.0), ('ridge', 6.0), ('over', 3.6), ('touch', 4.0), ('door', 4.2), ('fan', 4.4), ('tunnel', 4.0),
         ('slat1', 3.6), ('search', 4.6), ('jones', 2.4), ('slat2', 5.0), ('under', 4.0), ('GEN', 0.0), ('board', 5.0), ('aisle', 4.6), ('window', 3.6),
         ('vand', 3.4), ('HQ', 0.0), ('last', 3.8), ('cab', 3.0), ('pull', 9.0)]
DIM = (0.72, 0.68, 0.62)
SLAT_F = dict(filt=CS.BAND, color=DIM, noise=0.0)


class Stage:
    def __init__(self, G):
        self.G = G
        self.m, self.K = G['m'], G['K']
        self.line, self.ts = G['TR_LINE'], G['TR_S']
        self.rail_z = G['RAIL_Z']
        self.fz = self.rail_z + rail.DISP_Z + ST.FLOOR_Z       # floor top of the cars, world z
        self.bh, self.bedy = G['_bh'], G['_bedy']
        self.T = {}
        self.dur = dict(SHOTS)
        self.appear = {}
        self.men = []
        self.ids = set()
        self.drv_dz = -1.05

    def nid(self):
        for lo, hi in ((1000, 1600), (2754, 4095), (20, 899)):
            try:
                i_ = self.m.new_id(lo, hi)
                self.ids.add(i_)                             # (every id the ending makes: guncheck below fails the build on any of its actors)
                return i_
            except RuntimeError:
                pass
        raise RuntimeError('ssoutro: no free task id')

    # ---- places
    def car(self, k, x, y, z=0.0):
        """car k's frame (x right of travel = south, y along = east, z above the floor) -> world metres"""
        p = ST.local_to_world(self.line, self.ts, k, (x, y, ST.FLOOR_Z + z))
        return (p[0] / M, p[1] / M, p[2] / M)

    def gz(self, x, y):
        """the surface a man stands on: sand, ballast, platform, ramp, stairs"""
        z = self.fz
        if PX0 <= x <= PX1 and PY0 <= y <= PY1:
            return z
        if STAIR_X0 <= x <= STAIR_X1 and PY1 < y < PY1 + STAIR_RUN:
            return z - (y - PY1) / STAIR_RUN * (z - 6.9)
        if RAMP_X0 <= x < PX0 and PY0 <= y <= PY1:
            return 7.72 + (x - RAMP_X0) / (PX0 - RAMP_X0) * (z - 7.72)
        d = abs(y - self.bedy); top = self.rail_z - 0.12; b = self.bh(x, y)
        if d < SB.BED_HW:
            return max(b, top)
        if d < SB.BED_HW + SB.BED_FOOT:
            return max(b, top - (d - SB.BED_HW) / SB.BED_FOOT * SB.BED_D)
        return b + (GROUND_DZ if x > 400.0 else 0.0)

    def on(self, x, y, h=0.0):
        return (float(x), float(y), self.gz(x, y) + h)

    # ---- camera
    def key(self, p, l, dur, smooth=True, fov=0.8, shake=0.0, link=None, target=None, **kw):
        k = CS.key(tuple(c_ * M for c_ in p), tuple(c_ * M for c_ in l), dur, smooth, fov=fov, shake=shake, **kw)
        if link is not None:
            k['link_id'] = link
        if target is not None:
            k['target_id'] = target
        k['indoor'] = True                                   # (the builder's one metre rule is for aerial shots: these sit at knee height, some in the tunnel)
        return k

    def move(self, name, p0, l0, p1, l1, fov=0.8, fov1=None, shake=0.0, link=None, target=None, **kw):
        """one shot: a glide from (p0, l0) to (p1, l1) over the shot's length"""
        d = self.dur[name]
        return [self.key(p0, l0, d, True, fov, shake, link, target, **kw), self.key(p1, l1, 0.0, False, fov if fov1 is None else fov1, shake, link, target, **kw)]


# ------------------------------------------------------------------------------------------------ cameras and lines
def keys(G):
    S = Stage(G)
    G['SO'] = S
    C_, F = S.car, K_FRT
    vo, orig, shots = G['vo'], G['orig'], G['shots']
    CAM2 = (49.0 * M, 239.95 * M, G['_cn'][2] + 1.9 * M)      # (x 49.2: the opening's test, the room's props all draw from here)
    U_ = G['V'].U
    CHIP_CAM, GATE_CAM = U_((FOOT_CAM[0], FOOT_CAM[1], FOOT_CAM[2] - F_SET)), U_((250.0, 209.0, SB.F - F_GATE + 4.2))   # (the hall's own camera looks straight at the gate; the chip's on a mast at the pit's rim, the old one saw only his back)
    CHIP_A, CHIP_B = U_((248.3, 238.0, SB.F - F_SET + 1.0)), U_((248.3, 238.0, SB.F - F_SET + 1.2))
    chip_shots = [(None, '', ('office', CHIP_CAM, CHIP_A), F_CUT),
                  (('ss_dhari3', 'David'), "GENERAL DHARI: That is the guidance chip. He took it with his own hands.", ('office', CHIP_CAM, CHIP_B))] if ssbay.BAY else [
                  (('ss_dhari3', 'David'), "GENERAL DHARI: That is the guidance chip. He took it with his own hands.", ('office', U_((246.9, 236.9, SB.F + 2.9)), U_((248.3, 238.0, SB.F + 1.3))))]
    GEN_SPEC = [(('ss_dhari1', 'David'), "GENERAL DHARI: Show me the server room. Again... stop. There.", ('office', G['GEN_CAM'], (G['_cn'][0], G['_cn'][1], G['_cn'][2] + 1.5 * M))),
                (None, '', ('office', U_((257.7, 206.8, SB.F + 1.8)), U_((256.0, 206.5, SB.F + 1.5))), 2.1)] + chip_shots + [
                (None, '', ('office', GATE_CAM, U_((266.0, 222.0, SB.F - F_GATE + 2.0))), F_RUN),
                (('ss_o_clean', 'David'), "GENERAL DHARI: The train is clean? Then put your men on it. Every car, every station.", ('office', CAM2, (G['_cn'][0], G['_cn'][1], G['_cn'][2] + 1.6 * M))),
                (('ss_dhari2', 'David'), "GENERAL DHARI: One man did all this. He has the chip. Find out who sent him... we are going to hunt him.", ('office', CAM2, (G['_cn'][0], G['_cn'][1], G['_cn'][2] + 1.6 * M)))]
    gk, gcap = __import__('ssgeneral').keys(G, S, GEN_SPEC) if GEN2 else shots(GEN_SPEC, 'SS_OG')
    if ssbay.BAY:                                            # (a long lens from the mast: the operator has zoomed in on the box)
        for k_ in gk:
            if tuple(k_['pos']) == tuple(CHIP_CAM):
                k_['fov'] = 0.3
    for k_ in gk:
        if tuple(k_['pos']) == tuple(GATE_CAM):
            k_['fov'] = 0.5
    hq_spec = [(('ss_o_hq', 'AnyaHQ'), "ANYA: Kral's laptop has the routes, Jones. Dhari moved the shipment out the same way you are leaving. And now you have company.",
                ('hq', (4.62, -1.95, -1.30), (4.40, -0.85, -1.42), (4.55, -1.85, -1.31)))]
    hk, hcap = shots(hq_spec, 'SS_OH')
    hk = [dict(k_, filt=CS.NONE, color=(0.0, 0.0, 0.0), noise=0.0) for k_ in hk]   # (judge J08: her own room seen plainly and close, as the intro now has it; the old wide lens had the monitor's grey back fill the left)
    S.dur['GEN'] = sum(k_['dur'] for k_ in gk)
    S.gen_caps = [c_[0] for c_ in gcap]
    S.dur['HQ'] = sum(k_['dur'] for k_ in hk)
    t = 0.0
    for n_, d_ in SHOTS:
        S.T[n_] = t
        t += S.dur[n_]
    S.total = t
    TT = S.T
    z0 = S.fz
    # A: the box
    J0, J1 = 389.0, 406.5
    jy = 202.75
    bz = S.rail_z - 0.12
    OK = S.move('run', (J0 - 4.0, 199.6, bz + 1.0), (J0 + 14.0, jy - 0.8, bz + 1.2), (J1 - 9.0, 199.6, bz + 1.0), (418.0, 201.6, bz + 1.3), fov=0.8, shake=0.006)   # (owner 11-12 boarding beat: from behind Jones, the van door and the train sentry beyond it in the lens: he turns his back as Jones jumps in)
    OK += S.move('in', C_(F, -1.2, -0.9, 0.45), C_(F, 1.6, 0.0, 0.9), C_(F, -1.2, -0.9, 0.45), C_(F, 1.6, 0.0, 0.9), fov=1.0)
    OK += S.move('crate', C_(F, -1.3, -1.3, 1.55), C_(F, 0.1, 1.6, 0.8), C_(F, -1.2, -1.0, 1.5), C_(F, -0.2, 1.9, 0.8), fov=0.8)
    OK += S.move('drop', C_(F, 0.3, 0.95, 1.38), C_(F, -0.8, 2.4, 1.05), C_(F, 0.3, 1.05, 1.38), C_(F, -0.8, 2.4, 1.1), fov=0.75)   # (owner 105: from the aisle at the crate's top edge, not down into it)
    # B: the chase
    S.ridge_keys = S.move('ridge', (436.0, 232.8, S.bh(436.0, 232.8) + 1.7), (372.0, 318.0, 44.0), (436.0, 232.8, S.bh(436.0, 232.8) + 1.7), (430.0, 282.0, 32.0), fov=0.6)   # (judge J14: 25 m to the lens's left, away from the lead Hind's path: it flew 0.1 rad from the sun disc, and from right below a blade end-on read as a pole)
    OK += S.ridge_keys
    OK += S.move('over', (470.0, 226.0, 8.3), (470.0, 246.0, 20.0), (470.0, 226.0, 8.3), (450.0, 240.0, 12.0), fov=1.0)
    OK += S.move('touch', (421.0, 226.0, S.bh(421.0, 226.0) + 1.5), (446.0, 238.0, 12.0), (421.0, 226.0, S.bh(421.0, 226.0) + 1.5), (446.0, 238.0, 10.0), fov=0.7)
    ax, ay, ag = LZ_A
    dx, dy = _rot((DOOR_LOCAL[0], DOOR_LOCAL[1]), ag)
    OK += S.move('door', S.on(ax + dx - 8.0, ay + dy - 11.0, 2.6), S.on(ax + dx + 1.0, ay + dy - 1.0, 1.4), S.on(ax + dx - 8.5, ay + dy - 12.0, 2.5), S.on(ax + dx + 0.5, ay + dy - 3.0, 1.3), fov=0.85, shake=0.003)   # (owner 104: from ahead of them, the whole Hind behind; it was low under the hull, the wheel and pods filled it)
    OK += S.move('fan', (FAN_LENS[0], FAN_LENS[1], z0 + 1.65), (452.0, 232.0, 9.0), (431.0, 211.6, z0 + 1.65), (449.0, 219.0, 9.5), fov=0.55)
    SDX, SDY, SDG = G['SD_X'], G['SD_Y'], G['SD_G']
    OK += S.move('tunnel', (SDX - 15.0, SDY - 1.8, SDG + 1.2), (SDX + 2.0, SDY, SDG + 1.6), (SDX - 13.0, SDY - 1.8, SDG + 1.2), (SDX + 2.0, SDY, SDG + 1.4), fov=0.9)
    # C: the search
    _sc = {'b': (C_(F, 0.15, 3.0, 2.2), C_(F, 0.2, 1.9, 0.3)), 'c': (C_(F, 1.2, 2.0, 1.3), C_(F, -0.3, 1.95, 0.6))}.get(os.environ.get('SS_SRCHCAM', ''))
    if _sc:                                                  # (debug: one fixed lens on the searcher for slat1 .. slat2)
        for n_ in ('slat1', 'search', 'jones', 'slat2'):
            OK += S.move(n_, _sc[0], _sc[1], _sc[0], _sc[1], fov=0.9)
    else:
        OK += S.move('slat1', C_(F, -0.75, 1.95, 0.6), C_(F, 1.4, -0.6, 1.0), C_(F, -0.75, 1.95, 0.6), C_(F, 1.3, -0.5, 1.0), fov=0.55)
        OK += S.move('search', C_(F, -1.2, -1.75, 1.6), C_(F, 0.5, 2.2, 0.75), C_(F, -1.15, -1.35, 1.55), C_(F, 0.5, 2.2, 0.75), fov=0.7)
        OK += S.move('jones', C_(F, -0.82, 3.02, 0.72), C_(F, -0.72, 2.3, 0.55), C_(F, -0.82, 2.95, 0.72), C_(F, -0.72, 2.3, 0.55), fov=0.9, **SLAT_F)
        OK += S.move('slat2', C_(F, 0.07, 3.5, 1.55), C_(F, -0.1, 1.9, 1.05), C_(F, 0.07, 3.35, 1.5), C_(F, -0.25, 1.9, 0.95), fov=0.8)
    OK += S.move('under', (431.0, 195.4, S.bh(431.0, 195.4) + 1.6), (440.0, 203.0, bz + 1.0), (434.0, 195.4, S.bh(434.0, 195.4) + 1.6), (443.0, 203.0, bz + 1.0), fov=0.65)
    OK += gk
    # E: the train
    OK += S.move('board', (436.2, 212.0, z0 + 1.7), (453.0, 207.0, z0 + 1.2), (437.6, 212.0, z0 + 1.7), (453.0, 207.0, z0 + 1.2), fov=0.6)
    OK += S.move('aisle', C_(K_COACH, 0.0, -10.2, 1.45), C_(K_COACH, 0.0, 6.0, 1.3), C_(K_COACH, 0.0, -9.6, 1.45), C_(K_COACH, 0.0, 6.0, 1.3), fov=0.9)
    OK += S.move('window', (444.5, 210.9, z0 + 1.7), (450.0, 205.5, z0 + 1.3), (446.5, 210.9, z0 + 1.7), (451.0, 205.5, z0 + 1.2), fov=0.7)
    OK += S.move('vand', C_(F, -1.25, -0.95, 1.5), C_(F, 1.5, 0.1, 1.15), C_(F, -1.2, -0.8, 1.45), C_(F, 1.5, 0.3, 1.1), fov=0.85)
    OK += hk
    OK += S.move('last', C_(F, -0.30, 2.95, 0.85), C_(F, -0.75, 2.2, 0.6), C_(F, -0.32, 2.85, 0.82), C_(F, -0.75, 2.2, 0.6), fov=0.9, shake=0.0025, **SLAT_F)   # (judge H11: it was the 'jones' lens again: now from the crate's east corner, his face, the shut west corner behind)   # (the 'jones' shot's lens, the one that frames him: from the side the hiding clip's body, off its root, fell out of the picture, c3b)
    cy = ST.LENGTH[ST.LOCO] / 2 - CAB_L + 0.2                # (owner 107: the cab is at the front now; the lens at its back, the crew and the windscreen ahead)
    OK += S.move('cab', C_(K_LOCO, -0.2, cy + 0.9, 1.6), C_(K_LOCO, 0.7, cy + 4.6, 0.85), C_(K_LOCO, -0.1, cy + 1.2, 1.55), C_(K_LOCO, 0.7, cy + 4.6, 0.85), fov=0.8)
    py = 193.5
    OK += S.move('pull', (518.0, py, S.bh(518.0, py) + 1.1), (470.0, 205.0, z0 + 1.8), (518.0, py, S.bh(518.0, py) + 1.1), (505.0, 205.0, z0 + 2.0), fov=0.75)
    p_, l_ = OK[-1]['pos'], OK[-1]['tgt']
    OK += [dict(CS.key(p_, l_, 1.1, True, fov=0.8, filt=CS.BAND, color=(1, 1, 1), noise=0.0), indoor=True), dict(CS.key(p_, l_, 0.0, False, fov=0.8, filt=CS.BAND, color=(0, 0, 0), noise=0.0), indoor=True)]
    # the lines
    caps = []
    import ssvoices as _VC

    def line(at, vdef, text, who='Anya', raw=False):
        name, secs = vo(vdef, text, who, raw)
        caps.append((round(at, 2), vdef.upper(), _VC.caption(vdef, text), name, secs + 0.3))   # (owner 11-15 S19: the caption says what the friend's Arabic take says)
    line(TT['run'] + 0.25, 'ss_o1c', 'ANYA: The missile is dead and Dhari has no way to launch it now, Jones.')
    line(TT['ridge'] + 0.4, 'ss_o6c', "ANYA: Helicopters, Jones, right behind you. Stay in that crate. Don't move.")
    line(TT['fan'] + 0.2, 'ss_o7air', "ANYA: The whole airbase is awake now. They are running, and they are looking for you.")
    # (owner 11-15 S19: these two are the friends' Arabic takes once ssvoices.SCENE_DEFS has them (voices role); the caption then comes from ssvoices.CAPTION.
    #  The English text stays only as the old cache key / fallback, so a tree without those takes still builds without making a new voice)
    for v_ in ('ss_o_nada', 'ss_o_call'):                  # (decision 25 / S19 review point 1: no silent English fallback: the build FAILS without the friends' take)
        assert _VC.actor(v_) or os.environ.get('SS_ENGLISH_OK') == '1', (
            "ssoutro: no friends' take for %s (ssvoices ON=%s, clip %s): the line would ship in English; SS_ENGLISH_OK=1 only for test builds"
            % (v_, _VC.ON, _VC.clip(v_)))
    line(TT['jones'] + 0.2, 'ss_o_nada', "SOLDIER: Nothing here. Crates.", 'Soldier', True)
    line(TT['slat2'] + 1.7, 'ss_o_call', "SERGEANT: Leave that! Come here, search this place!", 'Soldier', True)
    for c_ in gcap:
        caps.append((round(TT['GEN'] + c_[0], 2),) + tuple(c_[1:]))
    for c_ in hcap:
        caps.append((round(TT['HQ'] + c_[0], 2),) + tuple(c_[1:]))
    name, secs = orig('cv32_intro_04_jones')
    caps.append((round(TT['last'] + 0.8, 2), 'SS_O_JONES', 'JONES: So, business as usual then.', name, secs + 0.3))
    G['HQ_CAPS'].extend(c_[1] for c_ in hcap)
    S.keys = OK
    print('ssoutro: %d keys, %.1f s, shots %s' % (len(OK), S.total, ' '.join('%s@%.1f' % (n_, TT[n_]) for n_, d_ in SHOTS)))
    return OK, caps


def _rot(p, g):
    """a hull-frame offset (x right of the nose, y along it) -> world offset at yaw g"""
    return (p[0] * math.cos(g) - p[1] * math.sin(g), p[0] * math.sin(g) + p[1] * math.cos(g))


# ------------------------------------------------------------------------------------------------ the stage
def stage(G):
    S = G['SO']
    S.cs, S.box = G['CSO']['cs'], G['CSO']['outro']
    S.at = lambda t_: 'ConditionalContainer_%d.isRun && CutScene_%d.nTick > %.2f * GAME_FREQUENCY' % (S.box, S.cs, t_)
    S.tick = lambda t_: 'CutScene_%d.nTick > %.2f * GAME_FREQUENCY' % (S.cs, t_)
    S.LOGIC = G['LOGIC']
    S.flat = [skin for skin in G['LESM']] + [skin for skin in G['CSFM']]
    import sssoldiers as SSS                                 # (judge J11: technicians in shirt and jeans came out of the assault Hinds: troopers wear uniform)
    role_ = dict(SSS.ROLE_OF); role_.update({r_[0]: r_[5] for r_ in SSS.ROSTER})
    kit_ = {r_[0]: r_[4] for r_ in SSS.ROSTER}
    S.flat = [s_ for s_ in S.flat if role_.get(s_, 'man') in ('man', 'elite') and not any(w_ in kit_.get(s_, '') for w_ in ('jeans', 'tech'))] or S.flat
    if os.environ.get('SS_SOLDIERS', '1') == '1':            # (orchestrator 11-13, owner 'all look the same': the troopers wear the new men's looks, dealt so that
        mesh_ = {r_[0]: r_[2] for r_ in SSS.ROSTER}         #  two neighbours never share headgear - bare, cap, helmet, balaclava; skins only, no ids, no LOD rows)
        deal_ = [n_ for n_ in ('ssm01_1', 'ssm03_1', 'ssm10_1', 'ssm02_1', 'ssm12_1', 'ssm04_1', 'ssm06_1', 'ssm11_1', 'ssm05_1') if n_ in kit_ and role_[n_] in ('man', 'elite') and not any(w_ in kit_[n_] for w_ in ('jeans', 'tech'))]
        if len(deal_) >= 6:
            S.flat = deal_
    m = S.m                                                  # Jones's goal: the open freight door, not the guard van's platform
    q = S.car(K_FRT, ST.HW + 1.3, 0.0, -1.3)
    for k_ in range(3):
        m.set(G['HOPON'], 3 + k_, float(q[k_]) * M)
    m.set(G['HOPON'], 9, 7.0 * M); m.set(G['HOPON'], 10, 6.0 * M)
    # (owner 69: he jumped on elsewhere, or came overland, and nothing fired) any part of the train, on it, in it or under it, ends the mission. Sand door route: after Anya's line.
    allz = S.nid()
    a0, a1 = 386.0, 500.0
    m.add_child(G['LOGIC'], T(allz, 'AreaActivate', 'SS at the train, anywhere', (a0 + a1) / 2 * M, 207.0 * M, 11.0 * M, 0.0, 0.0, 0.0, (a1 - a0) * M, 13.0 * M, 13.0 * M, 'CRITERIA_HUMAN0'))
    m.set(G['DONE'], 9, '(StatusMessage_%d.isFinishedDisplay || !GenericTBA_%d.isFinished) && (AreaActivate_%d.nActive || AreaActivate_%d.nActive) && GenericTBA_%d.isFinished && !HumanPlayer_0.isDead'
          % (G['RUN'], G['SAND_PAD'], G['HOPON'], allz, G['GATE_PAD']))
    if 'trainpop' in G['DBG'] or 'trainpop2' in G['DBG']:
        _trainpop(S, G, allz)
    if 'trainonly' in G['DBG']:                              # (test: the train there, the ending held back: walk out of a car by real input)
        m.set(G['TRAINC'], 3, '1'); m.set(G['DONE'], 9, '0')
    if 'gateend' in G['DBG']:                                # (test: a real theft, then the ending as soon as the gate pad is pressed: live men block the walker in the tunnel)
        m.set(G['CSO']['outro'], 3, 'GenericTBA_%d.isFinished && !HumanPlayer_0.isDead && EditVariable_%d.nValue == 0' % (G['GATE_PAD'], G['CSO']['skip']))
    sd_ = G['SAND_DOOR']                                     # (judge J02: GATE 2 stood shut in the tunnel shot and the men came through it: it rolls up as the ending starts)
    m.set(sd_, 19, '(%s) || (Door_%d.isClosed && %s)' % (lit(m.byid[sd_].args[19]), sd_, S.at(0.0)))
    if 'revout' in G['DBG']:
        for d_ in (G['VGATE'], G['CAGE_GATE']) + (() if 'gate2test' in G['DBG'] else (G['SAND_DOOR'],)):   # (as a player leaves them: the replays film the open gate; gate2test: GATE 2 by the ending's own rule)
            m.set(d_, 19, 'Door_%d.isClosed' % d_)
    _helis(S, G)
    _doors(S, G)
    _men(S, G)
    _jones(S, G)
    _sentry(S, G)
    (__import__('ssgeneral').stage if GEN2 else _general)(S, G)
    _train(S, G)
    _crew(S, G)
    check_paths(S)
    check_cuts(S)
    check_lens(S, S.keys)
    check_sentry(S)
    check_calm(S)
    import guncheck                                          # (owner 11-15 S10/S21: no actor of the ending holds air or loses his gun; the whole level: tools/guncheck.py on the build)
    hits = [h for h in guncheck.check(S.m.stmts) if h[1] in S.ids]
    for h in hits[:12]:
        print('ssoutro: guncheck %s %s %s clip %s (%s s)' % (h[0], h[1], h[2], h[5], h[6]))
    assert not hits, ('guncheck: ending actors with a vanishing gun / empty rifle grip / unknown clip', len(hits))
    print('ssoutro: guncheck OK - every ending actor keeps his gun in hand (or has no rifle pose without one)')
    print('ssoutro: stage done, %.1f s, %d two-node legs given a third node' % (S.total, getattr(S, 'legs2', 0)))


def _node(S, p, g, spd, t, tg, a=0.0, b=0.0):
    return T(S.nid(), 'SplinePathNodeQTask', '', *[float(c_) for c_ in p], float(a), float(b), float(g), True, float(spd), round(float(t), 6), *[float(c_) for c_ in tg], True)


def path(S, rigid, pts, gammas, when, speeds=None, secs=None, name='path', pitch=None, roll=None, times=None):
    """a spline for `rigid` (pts in world metres) that starts at `when`: times = seconds from its start per node, or secs = its whole length, or speeds = km/h per node.
    Goes under LOGIC (a spline must sit outside the container of what it moves)"""
    P = [np.array(p_, float) * M for p_ in pts]
    d = [np.linalg.norm(P[k_] - P[k_ - 1]) / M for k_ in range(1, len(P))]
    if times is not None:
        ts_ = list(times)
        seg = [dd / max(ts_[k_ + 1] - ts_[k_], 1e-3) * 3.6 for k_, dd in enumerate(d)]
        spd = seg + [seg[-1]]
    else:
        spd = [sum(d) / secs * 3.6] * len(P) if speeds is None else list(speeds)
        ts_ = [0.0]
        for k_, dd in enumerate(d):
            ts_.append(ts_[-1] + dd / (0.5 * (spd[k_] + spd[k_ + 1]) / 3.6))
    pa, gu = S.nid(), S.nid()
    nodes = []
    for k_, p_ in enumerate(P):
        tg = P[min(k_ + 1, len(P) - 1)] - P[max(k_ - 1, 0)]
        nodes.append(_node(S, p_, gammas[k_], spd[k_], ts_[k_], tg, pitch[k_] if pitch else 0.0, roll[k_] if roll else 0.0))
    S.m.add_child(S.LOGIC, T(pa, 'SplinePathDynCubeObj', '', False, children=nodes))
    S.m.add_child(S.LOGIC, T(gu, 'SplinePathGuideQTask', '', pa, rigid, False, False, 0.0, children=[
        T(S.nid(), 'SequenceCommand', '', when, 'SplinePathGuide_SetRunning (TRUE);', '', '')]))
    return ts_[-1]


def rotor_sound(S, sound=VS.HIND, land_t=None):      # (owner 11-14 'helicopter has no sounds' + judge G31: each Hind its own short-range loop on COMMON's helicopter_1
    ev = [(0.0, sound)] + ([(land_t, VS.HIND_IDLE)] if land_t else [])   #  (the level's own name, as L16), down to the settled loop once its wheels are on the sand; tools/ssvsound.py)
    for w0, w1 in quiet_windows(S):                      # (vsg1 take: 3D sound is heard from the scene, not the camera, so the rotors carried into
        ev += [(w0, None), (w1, 'resume')]               #  Dhari's CCTV room: they stop for the general's scene and Anya's HQ, then go on as they were)
    ev.sort(key=lambda e_: e_[0])
    ids = [S.nid() for _ in ev]
    kids = []
    for k_, (t_, what) in enumerate(ev):
        if what == 'resume':
            what = VS.HIND_IDLE if land_t and t_ >= land_t else sound
        cmd = 'SoundGenerator_StopSound();' if what is None else 'SoundGenerator_PlaySound("%s")' % what
        kids.append(T(ids[k_], 'SequenceCommand', '', '1' if t_ <= 0.0 else S.tick(t_), cmd, '1', 'SequenceCommand_SetCommand(%d)' % (ids[k_ + 1] if k_ + 1 < len(ids) else -1)))
    return T(S.nid(), 'SoundGenerator', '', children=kids)


def quiet_windows(S):
    """the ending's shots far from the train (General Dhari's CCTV room, Anya's HQ): no rotor, diesel or storm wind there"""
    return [(S.T['GEN'], S.T['board']), (S.T['HQ'], S.T['last'])]


def outside_quiet(S):
    return ' && '.join('!(%s && !(%s))' % (S.tick(w0), S.tick(w1)) for w0, w1 in quiet_windows(S))


def _flight(S, lz, side, far):
    """waypoints (x, y, height over the ground, km/h) -> the Hind's world path ending on its wheels at lz"""
    x, y, g = lz
    nx, ny = -math.sin(g), math.cos(g)                      # the nose
    gz = S.bh(x, y) + WHEELS
    out = [(a_, b_, c_ + S.bh(a_, b_) + WHEELS, d_) for a_, b_, c_, d_ in far]
    out += [(x - nx * 30.0, y - ny * 30.0, gz + 11.0, 55.0), (x - nx * 10.0, y - ny * 10.0, gz + 4.0, 22.0), (x, y, gz + 1.2, 7.0), (x, y, gz, 3.0)]
    return out


def _clearance(S, way, name):
    """no part of the flight under the terrain + 6 m of clear air, or through a model"""
    K = S.K
    lo = 1e9
    for a_, b_ in zip(way[:-4], way[1:-3]):
        for f in np.linspace(0, 1, 40):
            p = np.array(a_[:3]) * (1 - f) + np.array(b_[:3]) * f
            lo = min(lo, p[2] - WHEELS - S.bh(p[0], p[1]))
        A_, B_ = tuple(c_ * M for c_ in a_[:3]), tuple(c_ * M for c_ in b_[:3])
        assert not K.blocked(np.array(A_), np.array(B_), pad=3.0 * M), ('helicopter path hits a model', name, a_, b_)
    print('ssoutro: %s lowest wheels over the ground %.1f m' % (name, lo))
    assert lo > 6.0, (name, lo)


def hind(S, G, name, lz, far, land_t):
    """a Hind with turning rotors, its own rotor sound, pilots, rotor wash, a sliding left door; on its wheels at land_t -> (hull id, door id)"""
    way = _flight(S, lz, 1, far)
    _clearance(S, way, name)
    x, y, g = lz
    hid = S.nid()
    pts = [w_[:3] for w_ in way]
    gam = []
    for k_, p_ in enumerate(pts):                            # the nose follows the flight, the last legs settle on the LZ's yaw
        if k_ < len(pts) - 3:
            n_ = pts[min(k_ + 1, len(pts) - 1)]
            gam.append(math.atan2(-(n_[0] - p_[0]), n_[1] - p_[1]))
        else:
            gam.append(g)
    gam = list(np.unwrap(gam))
    off = round((gam[-1] - g) / (2 * math.pi)) * 2 * math.pi
    pitch = [0.0] * (len(pts) - 4) + [0.06, 0.14, 0.04, 0.0]    # flares nose up over the last legs
    lift = lambda p_, l_: (p_[0] + _rot(l_, gam[0])[0] * 1.0, p_[1] + _rot(l_, gam[0])[1] * 1.0)
    p0 = pts[0]
    loc = lambda l_: (p0[0] + _rot(l_[:2], gam[0])[0], p0[1] + _rot(l_[:2], gam[0])[1], p0[2] + l_[2])
    kids = [T(S.nid(), 'RotateAttachment', '', 0.0, 0.0, 0.7, '720_02_1', 0), T(S.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '720_03_1', 0), rotor_sound(S, land_t=land_t)]
    for sk_, lp, in (('alarm1_1', (0.276, 5.504, -1.521)), ('alarm2_1', (0.302, 7.549, -2.301))):
        kids.append(T(S.nid(), 'EditBoneObj', 'SS %s pilot' % name, *[float(c_) * M for c_ in loc(lp)], 0.0, 0.0, float(gam[0] + 0.06), False, True, sk_, True, '', '', 'fly_chopper', 1.0, 0.0))
    d_ = copy.deepcopy(G['_src_gate']); did = S.nid()
    d_.args[0] = v(did); d_.args[2] = v('SS %s door' % name)
    for k_, c_ in enumerate(loc(DOOR_LOCAL)):
        d_.args[3 + k_] = v(float(c_) * M)
    d_.args[6] = v(0.0); d_.args[7] = v(-3.0); d_.args[8] = v(0.0)
    d_.args[9] = v(0.0); d_.args[10] = v(0.0); d_.args[11] = v(float(gam[0]))
    d_.args[12] = v('720_04_1'); d_.args[14] = v(0.6); d_.args[15] = v(False); d_.args[18] = v('1'); d_.args[19] = v(''); d_.args[20] = v('0')
    d_.args[24] = v(''); d_.args[25] = v('door_metal_1'); d_.args[26] = v(''); d_.args[27] = v('door_metal_1')
    for c_ in [a_ for a_ in d_.args if isinstance(a_, Call)]:
        d_.args.remove(c_)
    kids.append(d_)
    start = land_t - sum(np.linalg.norm(np.array(pts[k_ + 1]) - np.array(pts[k_])) / (0.5 * (way[k_][3] + way[k_ + 1][3]) / 3.6) for k_ in range(len(pts) - 1))
    assert start > 0.0, (name, start)
    cc = S.nid()
    S.m.add_child(S.LOGIC, T(cc, 'ConditionalContainer', 'SS %s' % name, S.at(start - 0.2), '', '', children=[
        T(hid, 'EditRigidObj', 'SS %s' % name, *[float(c_) * M for c_ in pts[0]], 0.0, 0.0, float(gam[0]), HIND, 5, False, False, children=kids)]))
    path(S, hid, pts, [float(g_) for g_ in gam], S.at(start), speeds=[w_[3] for w_ in way], name=name + ' flight', pitch=pitch)
    # dust thrown out from under it for the last seconds and while it stands
    if True:
        gz = S.bh(x, y)
        for k_ in range(6):
            a_ = k_ * math.pi / 3
            S.m.add_child(cc, SGS.smoke(S.nid, 'SS %s dust %d' % (name, k_), (x * M + 4.0 * M * math.cos(a_), y * M + 4.0 * M * math.sin(a_), (gz + 0.5) * M), math.pi / 2, a_ - math.pi / 2,
                                        50, 2.0, 0.5, 60.0, 100.0, (1.0, 0.88, 0.68), 1.0, 0.9, 3, 1.6, 0.8, 0.16, 0.0,
                                        '14 * (CutScene_%d.nTick > %.2f * GAME_FREQUENCY) * !(CutScene_%d.nTick > %.2f * GAME_FREQUENCY)' % (S.cs, land_t - 3.0, S.cs, land_t + 4.0), cutoff=500.0, mode=0))
    return hid, did, start


def _helis(S, G):
    TT = S.T
    S.land = dict(A=TT['touch'] + 2.3, B=TT['door'] + 0.6, C=TT['tunnel'] - 11.5)
    # A: over the north shoulder of the hill, past the camera in 'over', turns and settles nose west
    S.hA, S.dA, s_a = hind(S, G, 'Hind A', LZ_A, [(300.0, 332.0, 34.0, 170.0), (372.0, 318.0, 32.0, 170.0), (440.0, 288.0, 30.0, 150.0), (486.0, 258.0, 22.0, 110.0), (492.0, 240.0, 14.0, 80.0)], S.land['A'])
    # B: south of the hill, in along the plain, nose east
    S.hB, S.dB, s_b = hind(S, G, 'Hind B', LZ_B, [(250.0, 62.0, 32.0, 170.0), (318.0, 110.0, 32.0, 170.0), (360.0, 150.0, 22.0, 130.0)], S.land['B'])
    # C: behind B, breaks north for the sand door
    S.hC, S.dC, s_c = hind(S, G, 'Hind C', LZ_C, [(222.0, 44.0, 34.0, 170.0), (300.0, 70.0, 32.0, 150.0), (352.0, 108.0, 22.0, 120.0)], S.land['C'])
    S.door_t = dict(A=S.land['A'] + 1.2, B=S.land['B'] + 1.0, C=S.land['C'] + 0.8)
    for did, t_ in ((S.dA, S.door_t['A']), (S.dB, S.door_t['B']), (S.dC, S.door_t['C'])):
        S.m.set(did, 19, 'Door_%d.isClosed && CutScene_%d.nTick > %.2f * GAME_FREQUENCY' % (did, S.cs, t_))
    for k_ in S.ridge_keys:                                  # (the long lens stays on the lead Hind)
        k_['target_id'] = S.hA
    print('ssoutro: Hind flights start %.1f / %.1f / %.1f, land %.1f / %.1f / %.1f' % (s_a, s_b, s_c, S.land['A'], S.land['B'], S.land['C']))


# ------------------------------------------------------------------------------------------------ men
# (owner 11-15 S20 'soldiers crouch, look right and left ... repeated too much. Use other animations, or none: just standing normally' + review ENDING_review_1:
#  a man kneeling (stand_study_ground_rifle), raised fists (stand_wave) and rifles aimed at empty desert (stand_rifle / stand_inspect_weapon_rifle). The calm pool is now
#  the originals' guard filler only, plain 'stand' twice as often; stand_look_about (the look right and left) is out. check_calm fails on any of the dropped clips)
CALM = ['stand', 'stand', 'stand_clean_weapon', 'stand_wipe_nose', 'stand_streatch_neck', 'stand_bugged_by_fly', 'stand_sneze']
EASY = ['stand_wipe_nose', 'stand_streatch_neck', 'stand_bugged_by_fly', 'stand_sneze']   # (eb4: the fillers share one pelvis yaw, 55.5 deg off 'stand' / talk / salute:
#  a list mixing the two turns the man in ONE frame at the switch (the Transition does not carry the root), ENDING_review_2 105.20; and no stand_clean_weapon, its AK held out)
NOPE = ('stand_look_about', 'stand_rifle', 'stand_inspect_weapon_rifle', 'stand_study_ground_rifle')   # (S20: no man of the ending plays these; stand_wave only for the van man who calls his mate out)
TENSE = ['tense_look_forward', 'tense_look_left', 'tense_look_right', 'tense_look_forward_left', 'tense_look_backward_left', 'tense_look_backward_right', 'tense_reload_ak47', 'tense_ak47']


# (fix1123b E1, owner 11-24 'the enemies in the ending ghost / lag (sliding, popping)': X3_TRANSITIONS 2.4, a NEW EditBoneObj never blends from the old one, so
#  every phase of a man (one actor per phase) snapped to frame 0 of its first clip. ONE: each man is ONE actor for as long as he is seen: his phases become one
#  non-looping animation list on one EditBoneObj (the Transition blends every clip change), every stand / hold is FITTED to whole clips (his later steps move
#  with the fit, the next absolute hold takes the slack back), every leg lasts exactly its clips (whole cycles at the clip's foot speed). SS_ONE_ACTOR=0 = as f1123b_6
ONE = os.environ.get('SS_ONE_ACTOR', '1') == '1'
ONE_KEEP = ('his aide',)                                  # (fix1123b f1123b_8: the aide walks out in the wide shot and goes at the cut: per-phase timing, f1123b_7 lost him mid-room)
ONE_CAP = 990                                              # (string args > 1023 chars are cut silently: a longer list starts a second actor there)


def fit(main, pool, secs, first=None):
    """clips whose lengths add up to secs as near as whole clips allow: `main` (a deck or a loop) up to ~ secs - one pool clip, then the best pool tail
    (frames, nearest sum, fewer clips first). -> (clips, their seconds)"""
    out = [first] if first else []
    t_ = sum(_clip(c_) for c_ in out)
    big = max(_clip(c_) for c_ in pool)
    k_ = 0
    while main and t_ + _clip(main[k_ % len(main)]) <= secs - big and len(out) < 40:
        out.append(main[k_ % len(main)]); t_ += _clip(main[k_ % len(main)]); k_ += 1
    rem = int(round((secs - t_) * 30.0))
    fr = sorted({(int(round(_clip(c_) * 30.0)), c_) for c_ in pool})
    best = {0: []}
    frontier = [0]
    lim = rem + max(f_ for f_, c_ in fr)
    while frontier:
        nxt = []
        for v_ in frontier:
            for f_, c_ in fr:
                w_ = v_ + f_
                if w_ <= lim and w_ not in best and len(best[v_]) < 12:
                    best[w_] = best[v_] + [c_]; nxt.append(w_)
        frontier = nxt
    pick = min(best, key=lambda v_: (abs(v_ - rem), len(best[v_])))
    if not out and pick == 0 and secs >= 0.2:            # (a short hold still shows him: one clip, the nearest)
        pick = min((v_ for v_ in best if v_ > 0), key=lambda v_: (abs(v_ - rem), len(best[v_])))
    out += best[pick]
    return out, sum(_clip(c_) for c_ in out)


def deck(seed, pool, secs, first=None):
    """clips for `secs`, shuffled by man, every clip of the pool before any comes round again (at most 30: the string is capped)"""
    r = random.Random(seed)
    out = [first] if first else []
    t_ = sum(_clip(c_) for c_ in out)
    while t_ < secs + 3.0 and len(out) < 30:
        d_ = list(pool)
        r.shuffle(d_)
        for c_ in d_:
            if not out or c_ != out[-1]:
                out.append(c_); t_ += _clip(c_)
    return out[:30]


class Man:
    """one man: a carrier on spline legs + phases of animation. t runs in outro seconds"""
    def __init__(self, S, name, skin, gun, pos, gamma, t0):
        self.S, self.name, self.skin, self.gun = S, name, skin, gun
        self.p, self.g, self.t = tuple(float(c_) for c_ in pos), float(gamma), float(t0)
        self.p0, self.g0, self.t0 = self.p, self.g, self.t
        self.rig = S.nid()
        self.ph, self.cur, self.cur_t = [], [], self.t         # finished phases; the open clip list
        self.n = 0
        self.leg = None                                        # the spline being laid: [start time, points, gammas, node times]
        self.tf = 1.0                                          # (owner 11-12: his standing loops' time factor; the Hind men get their own so nobody moves in step)
        self.cond = ''                                         # (owner 11-12: one more condition on all his phases, e.g. '!HumanSoldier_N.isDead')
        self.gun_expr = ''                                     # (WeaponModel Expression: 'HumanPlayer_GetPrimaryWeaponModel' = the player's own gun, gun = the fallback; originals L14/L16/L23/L25)
        self.track = []                                        # (outro second, point) of everything he walks, for check_paths
        self.gt = [(self.t, self.g)]                           # (outro second, facing) at every node he walks through, for check_sentry (owner 11-15 S8)
        self.one = ONE and 'Jones' not in name and name not in ONE_KEEP   # (fix1123b E1: the enemies; Jones and the men timed to a camera cut keep their phases)
        S.men.append(self)

    def _lay(self):
        """he stops here: the moving legs so far become one spline"""
        if self.leg:
            t0, pts, gam, ts_ = self.leg
            self.n += 1
            if len(pts) == 2 and ts_[1] > 0.6:                 # (owner 93, rig f3: a long spline of two nodes never starts, the man runs on the spot; three nodes do. Short hops of two run: a third node there lost Jones his crate, review g1)
                pts.insert(1, tuple((a_ + b_) / 2.0 for a_, b_ in zip(pts[0], pts[1])))
                gam.insert(1, gam[1])
                ts_.insert(1, (ts_[0] + ts_[1]) / 2.0)
                self.S.legs2 = getattr(self.S, 'legs2', 0) + 1
            path(self.S, self.rig, pts, list(np.unwrap(gam)), self.S.tick(t0), times=ts_, name='%s leg %d' % (self.name, self.n))
            self.leg = None

    def _flush(self):
        self._lay()
        if self.cur:
            self.ph.append((self.cur_t, self.t, list(self.cur), False))
            self.cur = []
        self.cur_t = self.t

    def clip(self, *names):
        self._lay()
        for n_ in names:
            self.cur.append(n_); self.t += _clip(n_)
        return self

    def hold(self, until, *loop, shuffle=True):
        """loop these clips until outro second `until`. Owner 88 'the same video over and over': a stand of over 2 s plays a shuffled deck of its kind, not a loop
        (shuffle=False: exactly these clips, e.g. a small calm set in the Hind cabin)"""
        self._flush()
        if self.one:                                       # (fix1123b E1: no loop; whole clips fitted to the time, this man's clock moves with the fit)
            if until <= self.t + 1e-6:
                return self
            if loop:
                tense = loop[0] in TENSE
                main = list(loop)
                if shuffle and until - self.t >= 2.0 and loop[0] in CALM + TENSE:
                    main = deck('%s %.1f' % (self.name, self.t), TENSE if tense else CALM, until - self.t, loop[0])
                pool = sorted(set(loop) | (set(TENSE) if tense else {'stand'}))
                clips, secs = fit(main, pool, until - self.t)
                if secs > 0:
                    self.ph.append((self.t, self.t + secs, clips, False))
                    self.plan = getattr(self, 'plan', {}); self.plan[(round(self.t, 4), round(self.t + secs, 4))] = until   # (where he was meant to stop: a stretch that ends here ends there)
                    self.t = self.cur_t = self.t + secs
                    return self
            self.ph.append((self.t, until, [], True))      # (no clips: not there for that time)
            self.t = self.cur_t = until
            return self
        assert until >= self.t - 1e-6, (self.name, until, self.t)
        if shuffle and until - self.t >= 2.0 and loop and loop[0] in CALM + TENSE:
            loop = deck('%s %.1f' % (self.name, self.t), TENSE if loop[0] in TENSE else CALM, until - self.t, loop[0])
        self.ph.append((self.t, until, list(loop), True))
        self.t = self.cur_t = until
        return self

    def cut_at(self, at, early=0.15):
        """the open phase ends EXACTLY at outro second `at`, a hard cut: the rest of its list is never seen (one actor per character per SHOT).
        A list that ends before `at` holds its last pose up to the cut (at most `early` s). (eb2a1 9.20-9.32: Jones' jump list ran 0.12 s past
        the cut to the crate, so the new lens saw him standing in the crate for 8 frames)"""
        self._lay()
        assert self.one or self.t >= at - early, (self.name, 'list ends %.2f s before the cut' % (at - self.t))
        if self.cur:
            self.ph.append((self.cur_t, at, list(self.cur), False))
            self.cur = []
        self.t = self.cur_t = max(self.t, at)
        return self

    def fill(self, until, *clips):
        """stand on these clips, cycled, in the SAME actor (no new phase = no pop, X3_TRANSITIONS.md) until outro second `until`; the last clip may run
        past it (< one clip): what follows starts when the list gets there"""
        self._lay()
        k_ = 0
        while self.t < until - 0.05:
            c_ = clips[k_ % len(clips)]
            self.cur.append(c_); self.t += _clip(c_); k_ += 1
        return self

    def go(self, pts, secs, *clips, face=None):
        """a leg over pts (world m) in secs, playing clips in that time"""
        pts = [tuple(float(c_) for c_ in q) for q in pts]
        if self.one and clips:                             # (fix1123b E1: the leg lasts exactly its clips, so the list and the carrier stay in step)
            secs = sum(_clip(c_) for c_ in clips)
        if self.leg is None:
            self.leg = [self.t, [self.p], [self.g], [0.0]]
            self.track.append((self.t, self.p))
        L = [math.dist(a_, b_) for a_, b_ in zip([self.p] + pts[:-1], pts)]
        tot = max(sum(L), 1e-6)
        at, tt = self.leg[3][-1], 0.0
        prev = self.p
        for k_, q in enumerate(pts):
            dx, dy = q[0] - prev[0], q[1] - prev[1]
            g_ = math.atan2(-dx, dy) if math.hypot(dx, dy) > 0.02 else self.leg[2][-1]
            tt += L[k_] / tot * secs
            self.leg[1].append(q); self.leg[2].append(g_); self.leg[3].append(at + tt)
            self.track.append((self.t + tt, q))
            self.gt.append((self.t + tt, g_))
            prev = q
        if face is not None:
            self.leg[2][-1] = face
            self.gt[-1] = (self.gt[-1][0], face)
        self.cur.extend(_clip(c_) and c_ for c_ in clips)
        self.t += secs
        self.p, self.g = pts[-1], float(self.leg[2][-1])
        return self

    def run(self, pts, speed=4.8, clip=RUN, face=None):
        d = sum(math.dist(a_, b_) for a_, b_ in zip([self.p] + pts[:-1], pts))
        L = _clip(clip)
        if self.one:                                       # (fix1123b E1: whole cycles at the clip's own foot speed; a tiny step is a shuffle turn)
            fs1 = FOOT1123.get(clip) or speed
            if d < 0.45 * fs1 * L:
                return self.go(pts, 0.0, 'stand_turn_mp_shuffle', face=face)
            n = max(1, int(round(d / (fs1 * L))))
            return self.go(pts, n * L, *([clip] * n), face=face)
        n = max(1, int(round(d / (speed * L))))
        fs_ = FOOT1123.get(clip)
        if FIX1123_RUN and fs_ and 0.8 * fs_ <= speed <= 1.25 * fs_ and d / (speed * L) < 0.88:   # (only legs meant at the clip's own pace: Jones' slow walk up to the crate etc. keep theirs)
            # (fix1123-story S8, owner film 3:38 'they walk, then they start SLIDING'): whole cycles only made a short leg slow (0.64 m in one 1 s walk
            #  cycle = 0.6 m/s on feet that move 1.15) or a leg of 1.4 cycles 40 % fast. The leg now takes d / speed (the feet's own speed) and plays
            #  enough cycles to cover it; the phase ends with the leg (the last cycle is cut there, as every leg end already cuts its list)
            #  (review e004237: only legs shorter than one cycle; a multi-cycle leg keeps whole cycles, else chained legs drift out of step with their clips)
            return self.go(pts, max(d / fs_, 0.3), clip, face=face)
        return self.go(pts, n * L, *([clip] * n), face=face)

    def walk(self, pts, speed=1.65, clip='stand_walk_forward', face=None):
        return self.run(pts, speed, clip, face)

    def stroll(self, pts, face=None):
        """owner 11-15 S20: the relaxed walk, rifle down (the engine's own patrol walk for a rifle; stand_walk_forward holds it up at the ready)"""
        return self.run(pts, 1.2 if FIX_RUN else 1.35, 'civilian_walk_rifle', face)   # (fix1122 C2: its feet move 1.15 m/s)

    def mill(self, end, moves=3, stand=('stand',)):
        """a man with nothing left to do does not stand on one spot: a few steps round where he is, then stands again, until `end`
        (owner 11-15 S20: relaxed walk, and each man his own stand clip so two neighbours never match)"""
        r = random.Random('mill ' + self.name)
        x0, y0 = self.p[:2]
        for k_ in range(moves):
            a_ = self.t + r.uniform(3.0, 6.5)
            if a_ + 4.0 > end:
                break
            self.hold(a_, *stand)
            self.stroll([self.S.on(x0 + r.uniform(-2.2, 2.2), y0 + r.uniform(-2.0, 2.0))])
        return self.hold(end, *stand)

    def finish(self, end):
        """to the task tree: carrier in a container from t0; each phase a container on the carrier"""
        S = self.S
        self._flush()
        kids, self.vis = [], []                                # (vis: what the engine shows of him, for check_cuts)
        ph = [q for q in self.ph if q[1] - q[0] > 0.0]
        if self.one:
            return self._finish_one(end, ph)
        for k_, (a_, b_, clips, loop) in enumerate(ph):
            if not clips:                                      # (a hold with no clips: not there for that time)
                continue
            b2 = end if k_ == len(ph) - 1 else b_
            s_ = ', '.join(clips)
            assert len(s_) < 1000, (self.name, len(s_))
            for c_ in clips:
                _clip(c_)
            self.vis.append((a_, b2, clips[0]))
            kids.append(T(S.nid(), 'ConditionalContainer', 'SS %s %d' % (self.name, k_), '%s && !(%s)%s' % (S.tick(a_), S.tick(b2), ' && ' + self.cond if self.cond else ''), '', '', children=[
                T(S.nid(), 'EditBoneObj', 'SS %s' % self.name, *[c_ * M for c_ in self.p0], 0.0, 0.0, self.g0, bool(loop), True, self.skin, True, self.gun, self.gun_expr, s_, self.tf if loop else 1.0, BLEND)]))
        key = round(self.t0, 2)
        if key not in S.appear:
            S.appear[key] = S.nid()
            S.m.add_child(S.LOGIC, T(S.appear[key], 'ConditionalContainer', 'SS men at %.1f' % key, S.tick(self.t0 - 0.05), '', ''))
        S.m.add_child(S.appear[key], T(self.rig, 'EditRigidObj', 'SS %s carrier' % self.name, *[c_ * M for c_ in self.p0], 0.0, 0.0, self.g0, 'lot', 5, False, False, children=kids))


    def _finish_one(self, end, ph):
        """fix1123b E1: consecutive phases with clips = ONE actor (one EditBoneObj, one non-looping list) from his first seen second to his last"""
        S = self.S
        chunks, cur = [], None
        plan = getattr(self, 'plan', {})
        for a_, b_, clips, loop in ph:
            if not clips:
                cur = None
                continue
            if cur is not None and abs(cur[1] - a_) < 1e-3 and len(', '.join(cur[2] + clips)) < ONE_CAP:
                cur[1] = b_; cur[2] += clips; cur[3] = plan.get((round(a_, 4), round(b_, 4)), b_)
            else:
                cur = [a_, b_, list(clips), plan.get((round(a_, 4), round(b_, 4)), b_)]; chunks.append(cur)
        for i_, c_ in enumerate(chunks):                   # (a stretch ends where his hold was meant to end (a cut, a hand-over to the riders), not where its fitted clips end:
            if abs(c_[3] - c_[1]) > 1e-3:                  #  the actor is taken off then; a list that ends early gets one more clip of the same kind)
                if c_[0] + sum(_clip(x_) for x_ in c_[2]) < c_[3]:
                    c_[2].append(c_[2][-1])
                c_[1] = min(c_[3], chunks[i_ + 1][0]) if i_ + 1 < len(chunks) else c_[3]
        if chunks and ph and ph[-1][2] and chunks[-1][1] >= ph[-1][1] - 1e-3:   # (his last list runs to the end of the scene: cycle its last phase's clips)
            last = ph[-1][2]
            k_ = 0
            while chunks[-1][0] + sum(_clip(c_) for c_ in chunks[-1][2]) < end and len(', '.join(chunks[-1][2] + [last[k_ % len(last)]])) < ONE_CAP:
                chunks[-1][2].append(last[k_ % len(last)]); k_ += 1
            chunks[-1][1] = max(end, chunks[-1][1])
        kids = []
        for k_, (a_, b_, clips, _pl) in enumerate(chunks):
            s_ = ', '.join(clips)
            self.vis.append((a_, b_, clips[0]))
            kids.append(T(S.nid(), 'ConditionalContainer', 'SS %s %d' % (self.name, k_), '%s && !(%s)%s' % (S.tick(a_), S.tick(b_), ' && ' + self.cond if self.cond else ''), '', '', children=[
                T(S.nid(), 'EditBoneObj', 'SS %s' % self.name, *[c_ * M for c_ in self.p0], 0.0, 0.0, self.g0, False, True, self.skin, True, self.gun, self.gun_expr, s_, 1.0, BLEND)]))
        for _ in range(2 * (sum(1 for q in ph if q[2]) - len(kids))):   # (the ids the per-phase actors took: burned, so later task ids do not shift)
            S.nid()
        S.one_actors = getattr(S, 'one_actors', 0) + len(kids)
        S.one_phases = getattr(S, 'one_phases', 0) + sum(1 for q in ph if q[2])
        key = round(self.t0, 2)
        if key not in S.appear:
            S.appear[key] = S.nid()
            S.m.add_child(S.LOGIC, T(S.appear[key], 'ConditionalContainer', 'SS men at %.1f' % key, S.tick(self.t0 - 0.05), '', ''))
        S.m.add_child(S.appear[key], T(self.rig, 'EditRigidObj', 'SS %s carrier' % self.name, *[c_ * M for c_ in self.p0], 0.0, 0.0, self.g0, 'lot', 5, False, False, children=kids))


LOOK = ['tense_look_forward', 'tense_look_left', 'tense_look_forward_left', 'tense_look_right', 'tense_look_forward']


def _trainpop(S, G, allz, secs=24):
    """test only (item 67): Jones is put on each car in turn, the ending held back, a message says whether the end zone has him; the sequence walks and jumps at the crates"""
    import atmos
    m, C_ = S.m, S.car
    atmos.ensure_decl(m, 'SequenceCommand'); atmos.ensure_decl(m, 'LevelTimer')
    m.set(G['TRAINC'], 3, '1')
    m.set(G['DONE'], 9, '0')
    stands = [('van', C_(K_VAN, 0.0, 1.0, 0.0)), ('balcony', C_(K_VAN, 0.0, -5.2, 0.0)), ('freight aisle', C_(K_FRT, 0.6, 0.0, 0.0)), ('freight crate top', C_(K_FRT, -0.8, 2.3, 1.35)),
              ('freight stack', C_(K_FRT, 1.0, -4.2, 1.9)), ('flat', C_(K_FLAT, 0.0, 0.0, 0.0)), ('coach', C_(K_COACH, 0.0, 0.0, 0.0)), ('command', C_(K_CMD, 0.0, 0.0, 0.0)),
              ('cab', C_(K_LOCO, 0.0, ST.LENGTH[ST.LOCO] / 2 - 2.5, 0.0)), ('coach roof', C_(K_COACH, 0.0, 0.0, 2.9))]
    stands = stands[6:] if 'trainpop2' in G['DBG'] else stands
    tm = S.nid()
    m.add_child(S.LOGIC, T(tm, 'LevelTimer', 'DEBUG train stands', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, '1', '', False))
    ids = [S.nid() for _ in stands]
    kids = []
    for k_, (n_, q) in enumerate(stands):
        kids.append(T(ids[k_], 'SequenceCommand', 'DEBUG stand ' + n_, 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (tm, 8 + secs * k_), 'Human_PopPosition(0, %.3f, %.3f, %.3f)' % (q[0], q[1], q[2] + 0.35), 'TRUE',
                      'SequenceCommand_SetCommand(%d)' % (ids[k_ + 1] if k_ + 1 < len(ids) else -1)))
        G['msg']('SS_DBGZ%d' % k_, 'DEBUG zone %d' % k_, 'AreaActivate_%d.nActive && LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (allz, tm, 10 + secs * k_), 'TEST: end zone has Jones at %s' % n_, 6.0)
    m.add_child(S.LOGIC, T(S.nid(), 'Container', 'DEBUG train stands', False, children=kids))
    print('ssoutro: trainpop stands ' + ' '.join('%d:%s(%.1f,%.1f,%.1f)' % (k_, n_, q[0], q[1], q[2]) for k_, (n_, q) in enumerate(stands)))


def check_lens(S, OK, clear=1.3):
    """men against the camera, shot by shot"""
    t_, bad = 0.0, {}
    for k_, a_ in enumerate(OK[:-1]):
        d_ = a_['dur']
        if d_ > 0:
            b_ = OK[k_ + 1] if a_['smooth'] else a_
            for q in np.arange(0.0, d_, 0.2):
                f = q / d_
                c = [(a_['pos'][i] * (1 - f) + b_['pos'][i] * f) / M for i in range(3)]
                for mn in S.men:
                    if len(mn.track) >= 1 and mn.track[0][0] <= t_ + q <= mn.track[-1][0]:
                        ts_ = [p_[0] for p_ in mn.track]
                        pt = [np.interp(t_ + q, ts_, [p_[1][i] for p_ in mn.track]) for i in range(3)]
                        if math.dist(pt[:2], c[:2]) < clear and abs(pt[2] + 1.0 - c[2]) < 1.3:
                            bad.setdefault(mn.name, round(float(t_ + q), 1))
        t_ += d_
    print('ssoutro: men within %.1f m of the lens: %d %s' % (clear, len(bad), sorted(bad.items(), key=lambda q: q[1])[:12]))
    return bad


def check_cuts(S, short=0.3, win=0.3, far=120.0):
    """eb4 (ENDING_review_2, 'no third case'): nobody appears or vanishes 0.02-0.3 s after a hard cut (eb2a1: Jones gone 0.12 s after 9.20, the
    walkers swapped for the riders 0.2 s into 'pull'), and nobody comes on a cut with a clip no earlier ending actor played (46.60: jones_hiding loaded
    late, the crate empty for 0.1 s). Shots under `short` s (the CCTV bursts) are not cuts here; a man farther than `far` m from the new shot's lens is
    not in it (the general's aide 200 m away in his room)."""
    t_, ks = 0.0, []
    for k in S.keys:
        ks.append((t_, bool(k['smooth']), k)); t_ += float(k['dur'])
    at = [i_ for i_ in range(1, len(ks)) if not ks[i_ - 1][1]]
    cuts = [(ks[i_][0], np.array(ks[i_][2]['pos'], float) / M) for n_, i_ in enumerate(at)
            if (ks[at[n_ + 1]][0] if n_ + 1 < len(at) else S.total) - ks[i_][0] >= short]
    used, bad = {}, []
    for mn in S.men:
        for a_, b_, cl, lp in mn.ph:
            for c0 in cl:
                used[c0] = min(used.get(c0, a_), a_)
    for c0, t0 in getattr(S, 'preloaded', {}).items():      # (fix1123-story S4: a clip played earlier by a hidden preload actor is loaded)
        used[c0] = min(used.get(c0, t0), t0)
    for mn in S.men:
        iv = []
        for a_, b_, c0 in sorted(getattr(mn, 'vis', [])):
            if iv and abs(a_ - iv[-1][1]) < 0.02:
                iv[-1][1] = b_
            else:
                iv.append([a_, b_, c0])
        for s_, e_, c0 in iv:
            for c_, eye in cuts:
                near = lambda t2: math.dist(_pos_at(mn, t2), eye) < far
                if c_ + 0.02 < e_ <= c_ + win and near(e_):
                    bad.append((mn.name, 'gone %.2f s after the cut at %.2f' % (e_ - c_, c_)))
                if c_ + 0.02 < s_ <= c_ + win and near(s_):
                    bad.append((mn.name, 'comes %.2f s after the cut at %.2f' % (s_ - c_, c_)))
                if abs(s_ - c_) <= 0.02 and used.get(c0, 0.0) >= s_ - 0.02 and near(s_):
                    bad.append((mn.name, 'comes on the cut at %.2f with %s, its first use' % (c_, c0)))
    print('ssoutro: check_cuts: %d hard cuts, pops %d %s' % (len(cuts), len(bad), bad[:8]))
    assert not bad, ('a man pops in or out just after a hard cut', bad[:10])


def check_paths(S, clear=0.62):
    """walkers sampled every 0.1 s from each man's first step to his last: pairs closer than `clear` while level with each other"""
    tr = []
    for mn in S.men:
        if len(mn.track) < 2:
            continue
        ts_ = np.array([q[0] for q in mn.track]); ps = np.array([q[1] for q in mn.track])
        tr.append((mn.name, ts_, ps))
    bad = {}
    for i, (na, ta, pa) in enumerate(tr):
        for nb, tb, pb in tr[i + 1:]:
            lo, hi = max(ta[0], tb[0]), min(ta[-1], tb[-1])
            if hi <= lo:
                continue
            for t_ in np.arange(lo, hi, 0.1):
                a_ = [np.interp(t_, ta, pa[:, k_]) for k_ in range(3)]
                b_ = [np.interp(t_, tb, pb[:, k_]) for k_ in range(3)]
                if abs(a_[2] - b_[2]) < 1.0 and math.hypot(a_[0] - b_[0], a_[1] - b_[1]) < clear:
                    bad.setdefault((na, nb), round(float(t_), 1))
    print('ssoutro: walkers closer than %.2f m: %d pairs %s' % (clear, len(bad), sorted(bad.items(), key=lambda q: q[1])[:14]))
    # (judge J01: a man standing at his spot and a man arriving there were never compared: tracks end at the last step. Here each man stands on after it)
    st_ = {}
    for i, (na, ta, pa) in enumerate(tr):
        for nb, tb, pb in tr[i + 1:]:
            lo, hi = max(ta[0], tb[0]), S.total
            for t_ in np.arange(lo, hi, 0.2):
                a_ = [np.interp(t_, ta, pa[:, k_]) for k_ in range(3)]
                b_ = [np.interp(t_, tb, pb[:, k_]) for k_ in range(3)]
                if abs(a_[2] - b_[2]) < 1.0 and math.hypot(a_[0] - b_[0], a_[1] - b_[1]) < clear and (na, nb) not in bad:
                    st_.setdefault((na, nb), (round(float(t_), 1), [round(c_, 1) for c_ in a_[:2]]))
    print('ssoutro: standing men closer than %.2f m: %d pairs %s' % (clear, len(st_), sorted(st_.items(), key=lambda q: q[1][0])[:30]))
    if 'menat' in S.G['DBG']:                                # (test: every man within 14 m of the fan lens while it rolls)
        for t_ in (TT_ := S.T)['fan'] + np.arange(0.0, 4.4, 1.0):
            row = []
            for mn in S.men:
                if t_ < mn.t0:
                    continue
                ts_ = [mn.t0] + [q[0] for q in mn.track]; ps = [mn.p0] + [q[1] for q in mn.track]
                q_ = [float(np.interp(t_, ts_, [p_[k_] for p_ in ps])) for k_ in range(3)]
                if math.hypot(q_[0] - 431.0, q_[1] - 211.6) < 14.0:
                    row.append((mn.name, round(q_[0], 1), round(q_[1], 1), round(q_[2], 1)))
            print('ssoutro: men at %.1f: %s' % (t_, row))
    return bad


def _pos_at(mn, t_):
    ts_ = [mn.t0] + [q[0] for q in mn.track]; ps = [mn.p0] + [q[1] for q in mn.track]
    return [float(np.interp(t_, ts_, [p_[k_] for p_ in ps])) for k_ in range(3)]


def _gamma_at(mn, t_):
    ts_ = [q[0] for q in mn.gt]; gs = list(np.unwrap([q[1] for q in mn.gt]))
    return float(np.interp(t_, ts_, gs))


def check_sentry(S, min_deg=100.0):
    """owner 11-15 S8: while Jones is outside the van ('run' + 'in'), the train sentry never faces him: the angle between his facing and the line to Jones
    stays over min_deg at every tick"""
    sn, jn = getattr(S, 'sentry', None), next((m_ for m_ in S.men if m_.name == 'outro Jones'), None)
    if sn is None or jn is None:
        print('ssoutro: check_sentry skipped (no live sentry in this build)')
        return
    worst = 180.0
    for t_ in np.arange(0.0, S.T['crate'] + 1e-6, 0.05):
        p_, q_ = _pos_at(sn, t_), _pos_at(jn, t_)
        g_ = _gamma_at(sn, t_)
        f_ = (-math.sin(g_), math.cos(g_))
        d_ = (q_[0] - p_[0], q_[1] - p_[1]); n_ = math.hypot(*d_)
        a_ = math.degrees(math.acos(max(-1.0, min(1.0, (f_[0] * d_[0] + f_[1] * d_[1]) / max(n_, 1e-6)))))
        worst = min(worst, a_)
        assert a_ > min_deg, ('S8: the train sentry faces Jones', round(float(t_), 2), round(a_, 1), round(n_, 1))
    print('ssoutro: check_sentry OK - the sentry never faces Jones before he is in the van (smallest angle %.0f deg, limit %.0f)' % (worst, min_deg))


MOVE_CLIP = ('run', 'walk', 'jump', 'stroll')


def _clip_at(mn, t_):
    for a_, b_, clips, loop in mn.ph:
        if a_ <= t_ < b_ and clips:
            f_ = mn.tf if loop else 1.0
            L = [_clip(c_) / f_ for c_ in clips]
            x_ = t_ - a_
            if loop:
                x_ %= max(sum(L), 1e-6)
            for c_, l_ in zip(clips, L):
                if x_ < l_:
                    return c_
                x_ -= l_
            return clips[-1]
    return None


def check_calm(S, near=3.0, step=0.25):
    """owner 11-15 S9 + S20 counters: phases of the Hind men with a tense / kneel / crouch clip (must be 0), all men's tense phases, and neighbours
    (within `near` m) standing on the SAME clip at the same time (moving clips excepted), as man-seconds"""
    bad = lambda c_: c_.startswith(('tense', 'kneel', 'crouch'))   # (stand_jump_land stays allowed: the two van men hop up into the van with it)
    hind = [m_ for m_ in S.men if m_.name[:1] in 'ABC' and m_.name[1:].isdigit()]
    hph = [(m_.name, c_) for m_ in hind for a_, b_, cl, lp in m_.ph for c_ in cl if bad(c_)]
    allt = sum(1 for m_ in S.men if m_.name != 'outro Jones' for a_, b_, cl, lp in m_.ph if any(bad(c_) for c_ in cl))
    same, pairs = 0.0, {}
    men = [m_ for m_ in S.men if m_.name != 'outro Jones']
    for t_ in np.arange(0.0, S.total, step):
        cur = []
        for m_ in men:
            c_ = _clip_at(m_, t_)
            if c_ and not any(w_ in c_ for w_ in MOVE_CLIP):
                cur.append((m_, c_, _pos_at(m_, t_)))
        for i_ in range(len(cur)):
            for j_ in range(i_ + 1, len(cur)):
                if cur[i_][1] == cur[j_][1] and math.dist(cur[i_][2][:2], cur[j_][2][:2]) < near:
                    same += step
                    k_ = (cur[i_][0].name, cur[j_][0].name, cur[i_][1])
                    pairs[k_] = pairs.get(k_, 0.0) + step
    print('ssoutro: check_calm: Hind men tense/kneel/crouch clips %d %s; phases with tense/kneel (all men but Jones) %d; neighbours on one clip %.1f man-s %s'
          % (len(hph), sorted(set(hph))[:6], allt, same, sorted(((round(v_, 2),) + k_ for k_, v_ in pairs.items()), reverse=True)[:6]))
    assert not hph, ('S9/S20: Hind men still crouch or go tense', sorted(set(hph))[:10])
    assert allt == 0, ('S20: tense / kneel phases left', allt)
    nope = sorted({(m_.name, c_) for m_ in S.men if m_.name != 'outro Jones' for a_, b_, cl, lp in m_.ph for c_ in cl
                   if c_ in NOPE or (c_ == 'stand_wave' and m_ is not getattr(S, 's2', None))})
    print('ssoutro: check_calm: look-about / aim / kneel / wave clips on the men %d %s' % (len(nope), nope[:6]))
    assert not nope, ('S20: men still look about, aim, kneel or wave', nope[:10])


def _cabin(S, lz, k):
    """a man's spot in the cabin -> (world pos, the door sill, the sand under the door + 1.8 m out), men in a stream through it"""
    x, y, g = lz
    a, b = CABIN[k]
    gz = S.bh(x, y) + WHEELS
    w = lambda l_, z_: (x + _rot(l_, g)[0], y + _rot(l_, g)[1], z_)
    sp = w((a, b), gz + CABIN_Z)
    sill = w((-1.4, 2.3 + (0.35 if k % 2 else -0.35)), gz + CABIN_Z)
    out = w((-3.1, 2.3 + (0.7 if k % 2 else -0.7)), 0.0)
    return sp, sill, (out[0], out[1], S.gz(out[0], out[1]))


WAITS = ['stand', 'stand_wipe_nose', 'stand_streatch_neck', 'stand_clean_weapon']   # (owner 11-15 S20: they stand easy in the cabin, nobody sweeps the tense looks)
# (owner 11-15 S9 'they crouch for no reason, then stand up' + S10: crouch_jump_land has no 'weapon' entry (the gun vanished), stand_jump_land dips the hip to 0.62 m.
#  Every man now drops with running_jump_land (hip 0.89-0.94 m, gun in hand) and runs on upright; variety = his run clip, pace and spacing)
EXITS = [(RUN, 0.42, 'running_jump_land', 0.46), ('stand_run_fwd_full_ak47', 0.45, 'running_jump_land', 0.46)]
RUNS = [(RUN, 4.8), ('stand_run_fwd_full_ak47', 5.1), ('stand_run_fwd_full_m16', 4.6)]
# (fix1122-story C2, owner pics 26 28 39-41: 'they SLIDE instead of walking'). Measured 11-22 on alarm1_1 with tools/cutanim.py (foot speed in
#  the stance phase, engine seconds = file x 4096/4800): stand_run_forward 2.7 m/s, stand_run_fwd_full_ak47 / _m16 2.9, stand_walk_forward 1.65-1.8,
#  civilian_walk_rifle 1.15. The men ran the run clips at 4.6-5.1 m/s and boarded at 3.6: the ground went by 1.3-1.8 x faster than their feet.
#  Now every run of the Hind men is at its clip's own speed (+5 %), the relaxed walk at 1.2 m/s. SS_FIX1122_RUN=0 = the old speeds
FIX_RUN = os.environ.get('SS_FIX1122_RUN', '1') == '1'
FIX1123_RUN = os.environ.get('SS_FIX1123_RUN', '1') == '1'   # (fix1123-story S8: every leg at its clip's foot speed, see Man.run)
FIX1123 = os.environ.get('SS_FIX1123_STORY', '1') == '1'     # (fix1123-story S3 S4)
FOOT1123 = {'stand_run_forward': 2.85, 'stand_run_fwd_full_ak47': 3.0, 'stand_run_fwd_full_m16': 3.0, 'civilian_walk_rifle': 1.15, 'stand_walk_forward': 1.7}   # (m/s, fix1122 C2's tools/cutanim.py measurements)
FOOT = {RUN: 2.85, 'stand_run_fwd_full_ak47': 3.0, 'stand_run_fwd_full_m16': 3.0}
if FIX_RUN:
    RUNS = [(c_, FOOT[c_]) for c_, s_ in RUNS]


def _out(S, name, lz, k, t_appear, t_exit, skin):
    """a man waiting in the cabin of a landed Hind who jumps out at t_exit.
    Owner 11-12 'their animations keep repeating the same animation': each man waits on his own deck at his own speed, leaves by one of three
    jumps (owner 11-15 S9: always the upright running_jump_land, no kneel or tense run), then runs on with his own clip and pace (mn.run_clip)"""
    r = random.Random('out ' + name)
    sp, sill, gr = _cabin(S, lz, k)
    g = math.atan2(-(sill[0] - sp[0]), sill[1] - sp[1])
    mn = Man(S, name, skin, '107_01_1', sp, g, t_appear)
    mn.tf = r.uniform(0.86, 1.14)
    w_ = list(WAITS); r.shuffle(w_)
    mn.hold(t_exit, *w_[:3], shuffle=False)
    c1, s1, c2, s2 = EXITS[(k + r.randrange(len(EXITS))) % len(EXITS)]
    mn.go([sill], s1, c1)
    mn.go([gr], s2, c2)
    mn.run_clip = RUNS[r.randrange(len(RUNS))]
    mn.first = mn.run_clip                                   # (owner 11-15 S9: no kneel run from under the rotor: upright from the door on)
    return mn


def _men(S, G):
    TT = S.T
    end = S.total + 2.0
    sk = lambda k_: S.flat[k_ % len(S.flat)]
    # --- A: out of the north Hind, across the sand, up the stairs, along the platform; they wait there and board
    Ta, Ea = S.land['A'] + 0.4, S.door_t['A'] + 0.7
    S.board_gap = 1.35                                       # s between men at one door
    S.boarders = []
    wait = [(452.0, 209.2), (450.5, 208.7), (454.6, 209.0), (447.2, 209.6), (457.0, 208.6), (445.6, 208.9), (459.6, 209.4), (442.0, 209.5), (462.2, 209.0), (439.6, 208.7)]
    # (owner 11-15 S20 'calm and varied': on the platform two pairs talk face to face, 1.6-1.8 m apart (the originals' pairs: 0.9-1.9 m, within ~15 deg),
    #  every other man stands easy doing his own small thing, no two neighbours on one clip, nobody aims)
    pair = {0: 1, 1: 0, 3: 5, 5: 3}
    own = {2: ['stand'], 4: ['stand_clean_weapon'], 6: ['stand_streatch_neck', 'stand'], 7: ['stand_wipe_nose', 'stand'], 8: ['stand_bugged_by_fly', 'stand'], 9: ['stand']}
    gap = lambda tag_, n_: [0.0] + list(np.cumsum([random.Random('%s gap %d' % (tag_, i_)).uniform(0.42, 0.82) + (0.35 if FIX_RUN and tag_ == 'A' else 0.0) for i_ in range(n_ - 1)]))   # (owner 11-12: not one even stream)
    # (fix1122 C2, owner pics 26 28 'they walk through each other' at the stairs: A's ten men 0.35 s further apart, so one flight of the stair never holds two)
    ga = gap('A', 10)
    east = [k_ for k_ in range(10) if wait[k_][0] >= STAIR_X0 + 0.7 + (k_ % 3) * 1.2]
    for k_ in range(10):
        mn = _out(S, 'A%d' % k_, LZ_A, k_, Ta, Ea + ga[k_], sk(k_))
        wx, wy = wait[k_]
        sx = STAIR_X0 + 0.7 + (k_ % 3) * 1.2
        lane = 211.8 if wx < sx else (210.3 if east.index(k_) % 2 == 0 else 211.35)   # (the men for the far end run behind the near ones; eb4, ENDING_review_2 33.00-33.35:
                                                             #  two men east on one lane were one body in the fan lens, which looks along it: every other one takes a lane 1 m north)
        if k_ in pair:
            ox, oy = wait[pair[k_]]
            fc = math.atan2(-(ox - wx), oy - wy)             # (he faces his partner)
            mn.wait_idle = ['stand_talk1'] if k_ in (0, 3) else ['stand_talk2']
        else:
            fc = math.pi
            mn.wait_idle = own[k_]
        mn.run([S.on(sx + 1.0 + (k_ % 3) * 1.1, 224.5)], speed=mn.first[1], clip=mn.first[0])
        mn.run([S.on(sx, PY1 + STAIR_RUN + 0.6)], speed=mn.run_clip[1], clip=mn.run_clip[0])
        # (batch 1b, review S9_a_050-056 'runners airborne beside the stairs', DIAG_batch1b.md 2: one straight leg from the sand to near the top floated up to 0.65 m over
        #  the treads, and the diagonal to the lane left the flight over the drop. Now: the foot of the flight, the top tread (both on the pitch line), straight onto the
        #  platform, then the lane: 0-0.26 m over a tread, never off the stair's sides)
        mn.run([S.on(sx, PY1 + STAIR_RUN - 0.05), S.on(sx, PY1 + 0.1)], speed=3.0)   # (eb4, ENDING_review_2 32.0-32.3: at 4.8 m/s the flight took one run cycle, 9 treads in
        mn.run([S.on(sx, PY1 - 0.35), S.on(wx + (1.0 if wx < sx else -1.0), lane), S.on(wx, wy)], speed=FOOT[RUN] if FIX_RUN else 4.8, face=fc)   #  two strides = a leap; at 3 two cycles, two treads a stride)
        S.boarders.append(mn)
    # --- B: out of the south Hind to the line; men look under the cars; two get on the freight van
    Tb, Eb = S.land['B'] + 0.4, S.door_t['B'] + 0.6
    S.vanmen = []
    # (owner 11-15 S20 + S10: the three men in the 'under' shot no longer go tense -> kneel -> stand in step (tense_to_kneel has no 'weapon' entry: the AK vanished
    #  for 1 s). Now each has his own job: B2 bends to look under the car, B3 and B4 talk face to face 1.5 m apart, B5 waves the next man on, B6 checks his rifle, B7 looks about)
    spot = [(433.6, 200.2, 0.0), (437.3, 199.55, None), (438.8, 199.75, None), (446.0, 199.7, -0.1), (403.0, 199.5, -0.1), (394.0, 199.8, -0.1)]
    gb = gap('B', 8)
    for k_ in range(8):
        mn = _out(S, 'B%d' % k_, LZ_B, k_, Tb, Eb + gb[k_], sk(k_ + 3))
        if k_ < 2:
            S.vanmen.append(mn)
            continue
        px, py, fc = spot[k_ - 2]
        if fc is None:                                       # (the talk pair face each other)
            ox, oy = spot[(4 if k_ == 3 else 3) - 2][:2]
            fc = math.atan2(-(ox - px), oy - py)
        mn.run([S.on(px - 3.0, 190.0)], speed=mn.first[1], clip=mn.first[0])
        mn.run([S.on(px, py)], speed=mn.run_clip[1], clip=mn.run_clip[0], face=fc)
        if k_ == 2:
            mn.hold(TT['under'] + 6.2, 'stand', shuffle=False)   # (S20: he stands by the car; no bend to the ground)
            mn.stroll([S.on(px + 3.5, py - 0.5), S.on(px + 6.5, py - 0.9)], face=-math.pi / 2).mill(end, moves=1, stand=('stand',))
        elif k_ in (3, 4):
            mn.hold(TT['under'] + 4.0 + 2.5 * (k_ - 3), 'stand_talk1' if k_ == 3 else 'stand_talk2')
            if k_ == 3:
                mn.stroll([S.on(px - 3.0, py - 0.3), S.on(px - 6.0, py - 0.2)], face=math.pi / 2).mill(end, moves=1, stand=('stand_clean_weapon',))
            else:
                mn.mill(end, moves=1, stand=('stand',))
        else:                                                # (owner 11-12: different end states: one waves the next man on, one checks his rifle, one looks about)
            mn.clip(*[('stand',), ('stand_streatch_neck',), ('stand_wipe_nose',)][k_ - 5]).mill(end, moves=2, stand=[('stand',), ('stand',), ('stand_clean_weapon',)][k_ - 5])
        mn.finish(end)
    # --- C: out of the third Hind, west to the sand door, in
    Tc, Ec = S.land['C'] + 0.4, S.door_t['C'] + 0.5
    sdx, sdy, sdg = G['SD_X'], G['SD_Y'], G['SD_G']
    gc_ = gap('C', 6)
    for k_ in range(6):                                      # (owner 11-12: 6, not 8: the level has no task ids to spare and the train sentry needs some)
        mn = _out(S, 'C%d' % k_, LZ_C, k_, Tc, Ec + gc_[k_], sk(k_ + 6))
        o = (k_ - 2.5) * 1.1
        mn.run([S.on(345.0, 168.0 + o * 3.0), S.on(326.0, sdy - 4.0 + o), (sdx + 3.0, sdy + o, sdg + 0.15), (sdx - 30.0, sdy + o * 1.4, sdg)], speed=5.2)   # (rc7s8 ids: the tunnel leg is straight, its middle node bought nothing)
        mn.hold(end, 'stand')
        mn.finish(end)
    # --- the two in the freight van
    C_, F = S.car, K_FRT
    s1, s2 = S.vanmen
    j0 = TT['slat1'] + 0.4
    # (owner 11-15 S10 + S20: tba_filing_search has no 'weapon' entry - his AK vanished for 3.9 s and again for 1.7 s - and the tense look deck read as
    #  'crouch, look left and right' again. He searches with the rifle in his hands; since batch 1b without the bend / look-round loop (below))
    s1.run([S.on(405.0, 190.0), S.on(409.8, 201.9)], face=0.0)
    s1.hold(j0 - 0.5, 'stand', shuffle=False)
    s1.go([C_(F, 1.0, -0.1, 0.0)], 0.5, 'stand_jump', face=math.pi / 2).clip('stand_jump_land')   # (judge J15: running_jump carries the rifle over his head)
    s1.hold(TT['search'], 'stand', shuffle=False)                   # (his new actor starts on the cut)
    s1.walk([C_(F, 0.25, 0.9, 0.0), C_(F, 0.13, 1.95, 0.0)], face=math.pi)   # (owner 106: in the middle of the wider aisle, at the opened crate)
    # (S20 batch 1b: the bend - look round - bend loop at the crate was the owner's 'crouch, look right and left' again. He now stands at the opened crate,
    #  0.45 m from its slats, looking into it ('Nothing here' at jones + 0.2), until the sergeant's shout; then he turns and walks out along the aisle with the
    #  relaxed walk (rifle down, as in 'stand'). The old 0.5 s spin to the north on stand_walk_forward -> stand_rifle snapped 90 deg at slat2 + 2.4, review S10_a_085-086)
    s1.fill(TT['slat2'] + 2.1, 'stand', 'stand', 'stand_streatch_neck')   # (one actor from the cut into 'search' to the cut into GEN: no new actor in the van shots,
    assert abs(s1.t - (TT['slat2'] + 2.1)) < 0.3, ('s1 leaves the crate on the call', round(s1.t - TT['slat2'], 3))   #  X3_TRANSITIONS.md; 2.9 + 2.9 + 1.97 s from 43.4)
    s1.stroll([C_(F, 0.2, 0.9, 0.0), C_(F, 1.0, 0.1, 0.0)], face=-math.pi / 2)
    s1.fill(TT['GEN'] + 0.2, 'stand')
    s1.hold(TT['vand'] + 1.1, 'stand', shuffle=False)
    S.s1 = s1
    s2.run([S.on(412.0, 190.0), S.on(408.9, 201.9)], face=0.0)
    s2.hold(TT['slat2'] + 1.3, 'stand', shuffle=False)                # (he stands at the door while his mate searches; then waves him out)
    s2.clip('stand_wave')
    s2.hold(TT['vand'] - 2.0, 'stand')
    S.s2 = s2


def _car_door(S, G, car_k, name, model, x, y, z, slide, open_t, close_t=None):
    """a sliding leaf, child of the car, moved by the outro's clock. slide = metres along the car"""
    d_ = copy.deepcopy(G['_src_gate']); did = S.nid()
    d_.args[0] = v(did); d_.args[2] = v('SS %s' % name)
    p = S.car(car_k, x, y, z)
    for k_, c_ in enumerate(p):
        d_.args[3 + k_] = v(float(c_) * M)
    d_.args[6] = v(0.0); d_.args[7] = v(float(slide)); d_.args[8] = v(0.0)
    d_.args[9] = v(0.0); d_.args[10] = v(0.0); d_.args[11] = v(float(G['_trg']))
    d_.args[12] = v(model); d_.args[14] = v(1.0); d_.args[15] = v(False); d_.args[18] = v('' if close_t is not None else '1')   # (a locked leaf never takes its close rule)
    d_.args[19] = v('0' if open_t is None else 'Door_%d.isClosed && %s' % (did, S.tick(open_t)) if close_t is None else 'Door_%d.isClosed && %s && !(%s)' % (did, S.tick(open_t), S.tick(close_t)))   # (shut again it must not reopen)
    d_.args[20] = v(S.tick(close_t) if close_t is not None else '0')
    d_.args[24] = v(''); d_.args[25] = v('door_metal_1'); d_.args[26] = v(''); d_.args[27] = v('door_metal_2')
    for c_ in [a_ for a_ in d_.args if isinstance(a_, Call)]:
        d_.args.remove(c_)
    S.m.add_child(G['TR_IDS'][car_k], d_)
    return did


def _doors(S, G):
    TT = S.T
    X = ST.HW + 0.05
    S.door_open = TT['board'] + 1.0
    S.door_shut = TT['window'] + 2.6
    for ys in (-DOOR_Y, DOOR_Y):
        _car_door(S, G, K_COACH, 'coach door north %+d' % ys, CDOOR, -X, ys, 1.11, 1.42, S.door_open, S.door_shut)
        _car_door(S, G, K_COACH, 'coach door south %+d' % ys, CDOOR, X, ys, 1.11, 1.42, None)
    _car_door(S, G, K_FRT, 'freight door north', FDOOR, -X, 0.0, 1.15, 2.3, None)
    S.van_shut = TT['vand'] + 0.9
    _car_door(S, G, K_FRT, 'freight door south', FDOOR, X, 2.28, 1.15, -2.28, S.van_shut)
    cx, cy = (CRATE[0] + CRATE[2]) / 2, (CRATE[1] + CRATE[3]) / 2
    _car_door(S, G, K_FRT, 'crate lid', LID, cx, cy + 1.66, CRATE[4], -1.66, TT['drop'] + 1.2)
    nx, ny = min((NCRATE[0] + NCRATE[2]) / 2, NCRATE[2] - (CRATE[2] - CRATE[0]) / 2 - 0.02), (NCRATE[1] + NCRATE[3]) / 2   # (the lid is the hero crate's: kept inside the van wall)
    _car_door(S, G, K_FRT, 'next crate lid', LID, nx, ny, NCRATE[4], 1.6, TT['search'] + 1.0)


def _sentry(S, G):
    """owner 11-12: one guard walks a beat along the train in play (builder squad 'S train sentry'). At the boarding he walks towards
    Jones's line, stops 8 m short of the van door, turns his back and looks up at the helicopters' sound while Jones runs behind him
    and jumps in. If the player killed him, none of this plays (every phase needs his guard alive)"""
    sq = G.get('SQUAD_IDS', {}).get('S train sentry')
    if not sq or {'noai', 'noenemies'} & set(G.get('DBG', ())):   # (walk builds: noai removes the squads after stage(), so HumanSoldier refs would dangle; the beat plays as if he were dead)
        return None
    TT = S.T
    y_ = 201.4
    # (owner 11-15 S8 'a soldier is looking at Jones; Jones gets into the train; only then he turns around. He saw you already': the old beat walked him WEST
    #  towards Jones for 2.5 s and turned him only at 2.8 s. Now his back is to the van from the first frame: he is walking his beat east, away from it,
    #  then stops and looks about, east, where the rotors will come from. check_sentry asserts it for every tick of 'run' + 'in')
    mn = Man(S, 'train sentry', G['CSF'][0] if 'CSF' in G else S.flat[0], '107_01_1', S.on(419.5, y_), -math.pi / 2, 0.0)
    mn.cond = '!HumanSoldier_%d.isDead' % sq[1][0]
    mn.stroll([S.on(425.0, y_ - 0.2)], face=-math.pi / 2)    # (on along his beat, away from the van: the relaxed walk, rifle down)
    mn.hold(TT['crate'], 'stand', shuffle=False)             # (stops and stands easy - his back to the line; S20: no look right and left)
    mn.stroll([S.on(431.0, y_ - 0.5)], face=-math.pi / 2)
    mn.hold(TT['ridge'] + 2.0, 'stand', shuffle=False)
    mn.hold(TT['ridge'] + 2.01)                              # (gone once the Hinds are in: the searchers own the train)
    mn.finish(TT['ridge'] + 2.01)
    S.sentry = mn
    return mn


def _jones(S, G):
    TT = S.T
    C_, F = S.car, K_FRT
    bz = S.rail_z - 0.12
    jy = 202.75
    mn = Man(S, 'outro Jones', 'jones2_1', '110_01_1', (389.0, jy, bz), -math.pi / 2, 0.0)
    mn.gun_expr = 'HumanPlayer_GetPrimaryWeaponModel'       # (owner 11-15 R2/S10: the gun he was holding, as the originals' cutscene Jones; the M16 if he has none)
    n = int(round(TT['in'] / _clip(RUN)))
    mn.go([(406.5, jy, bz)], n * _clip(RUN), *([RUN] * n), face=-math.pi / 2)
    mn.go([(409.6, jy, bz)], 0.82, RUN)
    mn.go([C_(F, 1.0, 0.0, 0.0)], _clip('running_jump'), 'running_jump', face=0.5).clip('running_jump_land')
    # (owner 105: the side view of the lid shot keeps him hidden. The walk and hop stay rc6's: a slower walk without the turn left him outside the crate, h1c to c7)
    # (batch 1b, review S8_a_049-050 'kneeling side-on -> standing face-on in one frame' at 5.0 s: the landing list ended early (clip lengths) and a NEW actor started
    #  the look back. Now one list from the first stride to the hop, blended (BLEND): land, one look back (owner 119), the slow walk up to the crate, one tense beat,
    #  the jump. Real lengths: land ends 5.2, look 6.0, walk 8.1, tense 8.8, jump 9.17; the hop is 0.03 s on the cut at 9.2)
    mn.clip('tense_look_backward')
    mn.walk([C_(F, 0.45, 0.8, 0.0), C_(F, 0.12, 1.25, 0.0)], speed=0.8, face=math.pi * 0.25)   # (owner 119: a slow walk up to it; the turn at the end stays: without it he ended outside the crate, c7)
    mn.clip('tense', 'stand_jump')
    assert abs(mn.t - (TT['drop'] - 0.03)) < 0.25, ('Jones reaches the hop off the cut', round(mn.t, 3), TT['drop'])
    mn.go([C_(F, -0.82, 2.3, 0.05)], 0.03, 'stand')          # (the hard cut hides the hop; he ends up facing east, the lens looks at him from there)
    mn.cut_at(TT['drop'])                                    # (eb2a1: the list ran to 9.32, the crate lens saw him for 8 frames after the 9.20 cut; now he is gone on the cut)
    mn.hold(TT['ridge'])                                   # (not there for the lid shot: the tip of his rifle stood over the rim, hf4 a12)
    if FIX1123:                                              # (fix1123-story S4, owner V2 V3: in the 'search' shot Jones and his rifle showed through the crate's slat gap and over its rim:
        #  those were the 0.3 s he was in before the cut. He now enters ON the cut; the late load of jones_hiding is taken by a preload copy of him 3 m under the
        #  van's floor from the 'crate' shot on (nobody sees it), so the clip is in memory when he appears)
        mn.hold(TT['jones'])
        _pz = C_(F, -0.82, 2.3, 0.05)
        S.preloaded = dict(getattr(S, 'preloaded', {}), jones_hiding=TT['crate'])
        _pc = S.nid()
        S.m.add_child(S.LOGIC, T(_pc, 'ConditionalContainer', 'SS jones_hiding preload (under the van)', '%s && !(%s)' % (S.at(TT['crate']), S.at(TT['jones'] + 0.5)), '', '',
                                 children=[T(S.nid(), 'EditBoneObj', 'SS outro Jones preload', _pz[0] * M, _pz[1] * M, (_pz[2] - 3.0) * M, 0.0, 0.0, 0.0, True, True, 'jones2_1', True,
                                             '110_01_1', '', 'jones_hiding', 1.0, BLEND)]))   # (his rifle as in the clip: guncheck AIR)
    else:
        mn.hold(TT['jones'] - 0.3)                         # (eb4, ENDING_review_2 fault 2: on the cut into 'jones' the crate was empty for 0.1 s, then he popped in at 46.77 -
    mn.hold(TT['slat2'], 'jones_hiding')                   #  the first use of jones_hiding loads late. He is in the crate 0.3 s before the cut, under the 'search' lens's rim)
    mn.hold(TT['last'])
    mn.hold(TT['cab'], 'jones_hiding')                     # (only the lens in the crate sees him here; seen from its old corner the hiding clip was a bent, cut-off body (c1b), kneeling a headless chest (c2c))
    mn.hold(TT['pull'])
    mn.finish(TT['pull'])


def _general(S, G):
    K, GEN_P, _cq, F = S.K, G['GEN_P'], G['_cq'], SB.F
    V, TT = G['V'], S.T
    base = TT['GEN']
    box = S.box
    K.actor(box, GEN_P, (_cq[0], _cq[1], _cq[2]), 'alseao_1', anim='cutscene_talk1, cutscene_talk2', name='General Dhari at the server')
    K.actor(box, (GEN_P[0] + 2.1 * M, GEN_P[1] - 0.15 * M, GEN_P[2]), GEN_P, S.flat[0], anim='stand', weapon='107_01_1', name='his aide')   # (not behind him: his rifle read as the general's)
    S.m.add_child(S.LOGIC, T(S.nid(), 'EditRigidObj', 'SS base video wall', GEN_P[0] + 2.2 * M, GEN_P[1] - 1.65 * M, GEN_P[2] + 1.7 * M, 0.0, 0.0, 0.927, FEED, 5, False, False))   # (on the room's far wall behind Dhari, facing the second camera; relative to him: the room ends near x 52.6, wall_near and the rays do not see it)
    t_c = S.gen_caps
    t_chip = base + t_c[1] - 0.3                             # (owner 93, 94: each replay has its one Jones, there only for his own shot, so no shot can see two)
    t_cut = t_chip - F_CUT if ssbay.BAY else t_chip
    t_end = base + t_c[2] - 0.3 - F_RUN
    t_con = t_cut - 2.1

    def footage(name, a, b, kids=()):
        c_ = S.nid()
        S.m.add_child(S.LOGIC, T(c_, 'ConditionalContainer', 'SS ' + name, '%s && !(%s)' % (S.at(a), S.at(b)), '', '', children=list(kids)))
        return c_

    def rigid(x, y, z, g, model):
        return T(S.nid(), 'EditRigidObj', '', x * M, y * M, z * M, 0.0, 0.0, g, model, 5, False, False)
    K.actor(footage('console footage', t_con - 0.05, t_cut), V.U((256.0, 206.5, F)), V.U((256.0, 207.3, F)), 'jones2_1', anim='hack_computer, hack_computer', name='Jones on the console footage')
    if ssbay.BAY:
        # (rc4e3, ssr6w, 118 men alive: scientists and riflemen walk round him on the real gantry during the cutscene, and a container going false would take them and their bodies for good.
        #  So the theft is replayed on a sealed copy of the bay F_SET under the hall, no AI can reach it. The real box, hatch and module stay as the player left them, untouched)
        z_ = F - F_SET
        p1, p2 = ssbay.S1, ssbay.S2
        hz = z_ + ssbay.HATCH[2]
        h0, h1 = ssbay.HINGE
        footage('chip set', t_cut - F_SKIP, t_end, [rigid(248.0, 236.0, z_, 0.0, SCREEN),
                                                    rigid(p1[0] + ssbay.STAND, p1[1], z_ + ssbay.CUT_Z, math.pi / 2, 'ss_gbx_1'),
                                                    rigid(p2[0] + ssbay.STAND, p2[1], z_ + ssbay.CHIP_Z, math.pi / 2, 'ss_ghr_1')])
        # step 1: knife, lid, wire: the clip draws lid and wire itself, the hatch is shut
        c1 = footage('lock box footage', t_cut - F_SKIP, t_chip, [rigid(h0, h1, hz, 0.0, 'ss_ghd_1')])
        K.actor(c1, V.U((p1[0], p1[1], z_)), V.U((p1[0] + 1.0, p1[1], z_)), 'jones2_1', anim='tba_sabotage, stand_nogun', name='Jones on the lock box footage')   # (owner 11-15 S10: 'stand' with no gun = an empty rifle grip; guncheck AIR)
        # step 2: the hatch stands open, he pulls the red module over the line. Same hold in his hand as in play
        c2 = footage('module footage', t_chip - 0.05, t_end, [rigid(h0, h1, hz, math.radians(ssbay.DOOR_END), 'ss_ghd_1'), rigid(ssbay.O[0], ssbay.O[1], z_, 0.0, 'ss_gbo_1')])
        K.actor(c2, V.U((p2[0], p2[1], z_)), V.U((p2[0] + 1.0, p2[1], z_)), 'jones2_1', anim='tba_filing_search, stand_nogun', name='Jones on the module footage')
        hand = ssbay.HAND
        footage('module in its socket', t_chip - 0.05, t_chip + hand[0][0], [rigid(ssbay.MOD[0], ssbay.MOD[1], z_ + ssbay.MOD[2], 0.0, 'ss_gmd_1')])
        for a_, b_, x_, y_, q_ in hand[:2]:                  # (not the last rows: here no end of a use clears it, it hung in the air after his hands had left, frame f8 8)
            footage('module lifted', t_chip + a_, t_chip + b_, [rigid(p2[0] + y_, p2[1] - x_, z_ + q_, 0.0, 'ss_gmd_1')])
        G['cam_obj'](V.U(FOOT_CAM), V.U((248.3, 238.0, F + 1.1)), name='chip mast', pole=True)   # (the real camera that filmed it)
    else:
        K.actor(footage('chip footage', t_chip - 0.05, t_end), V.U((248.0, 238.0, F)), V.U((248.8, 238.0, F)), 'jones2_1', anim='tba_sabotage, tba_sabotage', name='Jones on the chip footage')
    t_r = t_end                                              # (owner 93: he crosses the hall and goes out through the open gate, as the player did, and is gone before the cut)
    # (rc4 ghost, ssr7w: ten live men stood in the hall round him. As the bay: a copy of the hall F_GATE under it, only for this shot, the level's own models, no new rows. The real hall, its men and bodies untouched)
    zg = F - F_GATE
    hall = [rigid(SB.ORIGIN[0], SB.ORIGIN[1], SB.ORIGIN[2] - F_GATE, 0.0, 'ss_hall_1')]
    tun = [t_ for t_ in S.m.find('EditRigidObj') if str(lit(S.m.byid[t_].args[9])) == 'ss_tun1_1']   # (the truck tunnel beyond the gate: without it the opening showed a flat pale void)
    assert len(tun) == 1, tun
    q_ = [float(lit(S.m.byid[tun[0]].args[k_])) / M for k_ in (3, 4, 5)]
    hall.append(rigid(q_[0], q_[1], q_[2] - F_GATE, float(lit(S.m.byid[tun[0]].args[8])), 'ss_tun1_1'))
    hall += [rigid(x_, y_, zg, g_, '360_05_1') for x_, y_, g_ in ((262.5, 212.5, 0.0), (262.5, 232.0, 0.0), (259.0, 222.0, math.pi / 2))]
    footage('gate set', 0.0, S.total + 5.0, hall)            # (there for the whole ending, out of every other shot: rig ssr10wa2 froze 1.7 s on the cut where it was taken away)
    mn = Man(S, 'Jones running (footage)', 'jones2_1', '110_01_1', (255.0, 224.3, zg), -math.pi / 2, t_r - 0.05)
    mn.run([(278.0, 224.3, zg)], speed=5.5, face=-math.pi / 2).finish(t_r + F_RUN)


TRD = (0.0, 5.0, 16.0, 38.0, 80.0, 150.0, 240.0)
TRV = [5.0, 12.0, 20.0, 28.0, 36.0, 44.0, 50.0]


def _train(S, G):
    TT = S.T
    end = S.total + 2.0
    C_ = S.car
    S.dep = TT['pull'] + 0.6
    when = S.tick(S.dep)
    gam = float(G['_trg'])
    for k_, car in enumerate(G['TR_IDS']):
        p0 = C_(k_, 0.0, 0.0, -ST.FLOOR_Z)
        path(S, car, [(p0[0] + d_, p0[1], p0[2]) for d_ in TRD], [gam] * len(TRD), when, speeds=TRV, name='train car %d' % (k_ + 1))
        for key in AXLES if ST.LENGTH[ST.CONSIST[k_]] >= TURN_L else ():   # (still until it leaves, then up to about 36 km/h over the shot: alpha = the axle)
            S.m.add_child(car, T(-1, 'RotateAttachment', '', 0.0, 0.0, 0.0, key, 0, children=[
                T(-1, 'SequenceCommand', '', when, 'RotateAttachment_SetTargetSpeed(0, 540, 0.4)', '1', 'SequenceCommand_SetCommand(-1)')]))
    S.m.add_child(G['TR_IDS'][K_LOCO], T(S.nid(), 'ConditionalContainer', 'SS diesel', '%s && %s' % (S.tick(0.05), outside_quiet(S)), '', '', children=[   # (judge A4: idling at the platform from the first tick, not 2 s before she goes)
        T(S.nid(), 'SoundGenerator', '', children=[T(S.nid(), 'SequenceCommand', '', '1', 'SoundGenerator_PlaySound("%s")' % VS.TRAIN, '1', 'SequenceCommand_SetCommand(-1)')]),
        T(S.nid(), 'SoundGenerator', '', children=[T(S.nid(), 'SequenceCommand', '', S.tick(S.dep - 1.6), 'SoundGenerator_PlaySound("%s")' % VS.HORN, '1', 'SequenceCommand_SetCommand(-1)')]),   # (the horn, then
        T(S.nid(), 'SoundGenerator', '', children=[T(S.nid(), 'SequenceCommand', '', S.tick(S.dep - 0.3), 'SoundGenerator_PlaySound("%s")' % VS.TRAIN_DEP, '1', 'SequenceCommand_SetCommand(-1)')])]))   #  the diesel revs as she pulls out)
    S.m.add_child(G['TR_IDS'][K_FRT], T(S.nid(), 'SoundGenerator', '', children=[   # (judge A4: wheels on the rails under the crate car once she rolls)
        T(S.nid(), 'SequenceCommand', '', S.tick(S.dep + 0.4), 'SoundGenerator_PlaySound("%s")' % VS.WHEELS, '1', 'SequenceCommand_SetCommand(-1)')]))
    S.m.add_child(S.LOGIC, T(S.nid(), 'AmbientArea', 'SS ending storm wind (judge A2: the play ambience is off in cutscenes; 1000 wide: ssmusic re-zones wider wind areas to play-only)', *[float(c_) * M for c_ in S.car(K_FRT, 0.0, 0.0)],
                             0.0, 0.0, 0.0, 1000.0, 1000.0, 1000.0, 6.0, 0.0, 0.0, VS.WIND, True, True, '%s && !(%s) && %s' % (S.at(0.0), S.at(S.total), outside_quiet(S)), 0.8, False, 0.0))
    for (w0, w1), (tone, what) in zip(quiet_windows(S), (('24_inside_gen', "Dhari's CCTV room"), ('computer_ss', "Anya's HQ"))):   # (judge 11-14: no 1 s holes at the cuts:
        S.m.add_child(S.LOGIC, T(S.nid(), 'AmbientArea', 'SS ending room tone, %s' % what, *[float(c_) * M for c_ in S.car(K_FRT, 0.0, 0.0)],   #  the level's own room tones under the far shots)
                                 0.0, 0.0, 0.0, 1000.0, 1000.0, 1000.0, 6.0, 0.0, 0.0, tone, True, True, '%s && !(%s)' % (S.at(w0), S.at(w1)), 0.8, False, 0.0))

    swap = TT['pull']                                        # (walkers end, the men in the seats are the car's own children from here: ON the cut into 'pull' (eb4; at pull + 0.2
                                                             #  ten men vanished and came back as riders inside the shot, ENDING_review_2), 0.6 s before she moves)
    seated = {K_COACH: [], K_FRT: [], K_CMD: [], K_FLAT: []}

    # --- A boards: each door takes one man at a time, the first in goes furthest down the coach; while they wait each does his own small thing
    Bx = TT['board'] + 1.3
    ride = lambda n_: ', '.join(deck(n_ + ' rides', CALM, 40.0))
    # (owner 11-15 S20: no tense look deck and no lone man 'talking' to nobody; the platform pairs talk in _men (mn.wait_idle); in the coach each stands easy at a window)
    idle = (['stand'], ['stand_streatch_neck', 'stand'], ['stand_clean_weapon'], ['stand_wipe_nose', 'stand'], ['stand_bugged_by_fly', 'stand'], ['stand'])   # (S20: nobody aims out of the windows)
    fwd = sorted([q for q in SEATS if q[1] > -2.5], key=lambda q: q[1])       # door +8: furthest first
    aft = sorted([q for q in SEATS if q[1] <= -2.5], key=lambda q: -q[1])     # door -8
    seq = {DOOR_Y: fwd, -DOOR_Y: aft}
    for ys_ in (DOOR_Y, -DOOR_Y):                            # (owner 88: not all in one place: the first through each door go on into the next car)
        w_ = C_(K_COACH, 0.0, ys_, 0.0)
        k2 = min((K_CMD, K_FLAT), key=lambda k_: math.dist(C_(k_, 0.0, 0.0, 0.0)[:2], w_[:2]))
        seq[ys_][:0] = sorted([q_ + (k2,) for q_ in MORE[k2]], key=lambda q_: -math.dist(C_(k2, 0.0, q_[1], 0.0)[:2], w_[:2]))   # (furthest first: nobody passes anybody)
    arrive = {DOOR_Y: Bx + 0.9, -DOOR_Y: Bx + 0.9}
    C_d = lambda ys: C_(K_COACH, -2.3, ys, 0.0)
    order = sorted(S.boarders, key=lambda mn: min(math.dist(mn.p[:2], C_d(ys)[:2]) for ys in (DOOR_Y, -DOOR_Y)))

    def _plan(bsp_, bgap_):                                  # (fix1122 C2: the boarding below, dry: does every man reach his door before it shuts?)
        arr_, sq_ = dict(arrive), {k_: list(v_) for k_, v_ in seq.items()}
        for mn_ in order:
            ys_ = min((DOOR_Y, -DOOR_Y), key=lambda y_: math.dist(mn_.p[:2], C_d(y_)[:2]) + 40.0 * (not sq_[y_]))
            sq_[ys_].pop(0)
            ld_ = math.dist(mn_.p[:2], C_d(ys_)[:2]) / bsp_
            g_ = max(arr_[ys_] - ld_, mn_.t + 0.2)
            arr_[ys_] = g_ + ld_ + bgap_
            if g_ + ld_ >= TT['window'] + 2.3 - 0.2:
                return False
        return True
    BSP, BGAP = 3.6, S.board_gap                             # (fix1122 C2: board at the run clip's own speed, 1.8 s apart in the aisle (pics 40 41: three men in one
    if FIX_RUN:                                              #  lump), faster / closer only when the coach door would shut on a man)
        BSP, BGAP = next(((a_, b_) for a_, b_ in ((FOOT[RUN], 1.8), (FOOT[RUN], S.board_gap), (3.2, S.board_gap)) if _plan(a_, b_)), (3.6, S.board_gap))
    print('ssoutro: boarding at %.2f m/s, %.2f s apart' % (BSP, BGAP))
    for n_, mn in enumerate(order):
        ys = min((DOOR_Y, -DOOR_Y), key=lambda y_: math.dist(mn.p[:2], C_d(y_)[:2]) + 40.0 * (not seq[y_]))
        q_ = seq[ys].pop(0)
        xs, ysd, fc = q_[:3]
        car_ = q_[3] if len(q_) > 3 else K_COACH
        dp = C_d(ys)
        bsp, bgap = BSP, BGAP
        lead = math.dist(mn.p[:2], dp[:2]) / bsp
        go = max(arrive[ys] - lead, mn.t + 0.2)
        arrive[ys] = go + lead + bgap
        assert go + lead < TT['window'] + 2.3, (mn.name, go + lead)   # (the coach door shuts at window + 2.6: nobody runs through the leaf)
        mn.hold(go, *getattr(mn, 'wait_idle', idle[n_ % len(idle)]))
        s_ = 1 if ys > 0 else -1
        tail = [C_(K_COACH, 0.0, ysd, 0.0)] if car_ == K_COACH else [C_(K_COACH, 0.0, s_ * (ST.LENGTH[COACHD] / 2 - 0.2), 0.0), C_(car_, 0.0, ysd, 0.0)]
        L0 = max(math.dist(mn.p[:2], dp[:2]), 0.6)          # (batch 1b, review S20_a_010-014 / DIAG_batch1b.md 1: the leg turned him from his wait facing to the door over 2.35 s,
        fst = S.on(mn.p[0] + (dp[0] - mn.p[0]) * 0.5 / L0, mn.p[1] + (dp[1] - mn.p[1]) * 0.5 / L0)   #  a crab run with the lens on his back and the rifle hidden: a node 0.5 m on turns him at once)
        mn.run([fst, dp, C_(K_COACH, -0.9, ys, 0.0), C_(K_COACH, 0.0, ys - 0.6 * s_, 0.0)] + tail, speed=bsp)
        sg = 1.0 if xs > 0 else -1.0                         # (the truck-seat clips throw the body metres off their root and out through the wall: a troop train, they stand by the windows)
        here = idle[(n_ + 1) % len(idle)]
        mn.stroll([C_(car_, sg * 0.4, ysd - 0.5 * sg, 0.0)], face=0.0 if xs < 0 else math.pi)   # (eb4, ENDING_review_2 115.3: stand_walk_forward walked the aisle rifle at the shoulder)
        mn.hold(swap, *here)
        mn.finish(swap)
        seated[car_].append((mn, mn.p, 0.0 if xs < 0 else math.pi, ride(mn.name)))
    # --- the NCO on the platform
    nc = Man(S, 'NCO', S.flat[1], '107_01_1', S.on(453.5, 211.7), math.pi, S.land['A'] + 0.4)
    nc.hold(end, *deck('NCO', EASY, end - nc.t), shuffle=False)   # (S20: no raised-fist signals on a loop; eb4: the far-left man of the board shot turned to the lens in one frame at 105.20 ('stand' ->
                                                                   #  clean_weapon) and held his AK out at the desert: same-pelvis fillers only, rifle down)
    nc.finish(end)
    # --- s1 sits on the crate, s2 rides by the door
    s1, s2 = S.s1, S.s2
    F = K_FRT
    s1.stroll([C_(F, 0.6, 0.75, 0.0)], face=0.0)              # (clear of the crate: nothing of him through its slats; eb4: rifle down inside the cars)
    s1.hold(swap, 'stand', 'stand_clean_weapon')
    s1.finish(swap)
    seated[K_FRT].append((s1, s1.p, s1.g, ride('s1')))
    s2.go([C_(F, 1.15, -0.7, 0.0)], 0.5, 'stand_jump', face=math.pi / 2).clip('stand_jump_land')   # (judge J15: running_jump carries the rifle over his head)
    s2.hold(swap, 'stand', 'stand_wipe_nose')
    s2.finish(swap)
    seated[K_FRT].append((s2, s2.p, s2.g, ride('s2')))
    for k_, men in seated.items():
        cc = S.nid()
        S.m.add_child(G['TR_IDS'][k_], T(cc, 'ConditionalContainer', 'SS men on the train', S.tick(swap), '', ''))
        for mn, p_, g_, an in men:
            S.m.add_child(cc, T(S.nid(), 'EditBoneObj', 'SS %s rides' % mn.name, *[c_ * M for c_ in p_], 0.0, 0.0, float(g_), True, True, mn.skin, True, mn.gun, '', an, 1.0, BLEND))


def _crew(S, G):
    """the men who work here: loco driver and mate in the cab, a gunner on the flatcar, a driver in each truck, men unloading. Children of what they ride, always there"""
    C_, m = S.car, S.m
    sk = S.flat
    cab = lambda x_, y_: C_(K_LOCO, x_, y_, 0.0)
    ids = G['TR_IDS']
    y = ST.LENGTH[ST.LOCO] / 2 - 1.35                        # (the truck-seat clips throw the body metres off their root: the crew stand at the desk; owner 107 cab at the front)
    # (owner 11-15 S21 'the men who drive the train are holding guns. It doesn't make any sense ... they're hidden stuff': the driver wore the army officer's
    #  cap and coat and both stood on RIFLE idle clips (stand_look_about, stand_wipe_nose ... carry 'weapon' in the right hand) with no WeaponModel: two men
    #  holding invisible rifles at the desk (guncheck AIR). Now: railwaymen in work clothes (the roster's tech / jeans kits), WeaponModel 'none', and only clips
    #  that are not a weapon pose: the originals' unarmed clips (scientist_*, stand_nogun) - reading the gauges, leaning on the desk, standing with empty hands)
    import sssoldiers as SSS
    kit_ = {r_[0]: r_[4] for r_ in SSS.ROSTER}
    work = [s_ for s_ in ('ssm14_1', 'ssm08_1', 'ssm07_1', 'ssm09_1') if s_ in kit_] if os.environ.get('SS_SOLDIERS', '1') == '1' else []
    drv_skin, mate_skin = (work + [sk[2], sk[3]])[:2]
    crew = []
    for x_, a_, s_, g_ in ((0.6, ', '.join(deck('driver', ['scientist_standing_studying', 'stand_nogun', 'scientist_confused_studying'], 120.0, 'scientist_standing_studying')), drv_skin, float(G['_trg'])),
                           (-0.45, ', '.join(deck('mate', ['stand_nogun', 'scientist_standing_studying', 'stand_nogun', 'scientist_confused_studying'], 120.0, 'stand_nogun')), mate_skin, float(G['_trg']) + 0.5)):
        p_ = cab(x_, y)
        crew.append((K_LOCO, T(S.nid(), 'EditBoneObj', 'SS loco crew', p_[0] * M, p_[1] * M, p_[2] * M, 0.0, 0.0, g_, True, True, s_, True, 'none', '', a_, 1.0, BLEND)))
    # (owner 11-15 S21 / PLAN decision 3: no rifleman standing on the flatcar either - a man with a gun on the train, next to the crew, is what he objected to)
    for k_ in (K_LOCO,):                                     # (owner 11-12: the train is empty in play: its crew is there only once the ending runs)
        m.add_child(ids[k_], T(S.nid(), 'ConditionalContainer', 'SS train crew in the ending', S.tick(0.05), '', '', children=[b_ for c_, b_ in crew if c_ == k_]))
    # (owner 11-12: the seated truck drivers hung in the air beside the trucks in play, and nobody sits in a parked truck by a train: none)
    # two men by the first truck, talking to each other (item 109: one reached for crates in the air past the bare end of the chassis): only while the outro runs
    x, y_, yw = TRUCKS[0]
    pr = [((5.2, -1.6), 'stand_talk2, stand_talk1'), ((6.4, 0.2), 'stand_talk1, stand_talk2')]
    pw = [(x + _rot(d_, yw)[0], y_ + _rot(d_, yw)[1]) for d_, _ in pr]
    v_ = np.array(pw[0]) - np.array(FAN_LENS[:2]); v_ = v_ / np.linalg.norm(v_)   # (judge J01: from the fan lens one stood right behind the other, one head over the other: now side by side as it sees them)
    pw[1] = (pw[0][0] - 2.2 * v_[1], pw[0][1] + 2.2 * v_[0])
    for k_, (_, a_) in enumerate(pr):
        o_ = pw[1 - k_]
        mn = Man(S, 'unloader %d' % k_, sk[(k_ + 2) % len(sk)], '107_01_1', S.on(*pw[k_]), math.atan2(-(o_[0] - pw[k_][0]), o_[1] - pw[k_][1]), 0.0)
        # (judge J12: he stood like a statue while a Hind set down 10 m away. They talk until it comes in, then watch it: they stay put, out of the fan lens line)
        lk = min(('A', LZ_A), ('B', LZ_B), ('C', LZ_C), key=lambda q_: math.dist(q_[1][:2], pw[k_]))
        aw = np.array(pw[k_]) - np.array(lk[1][:2]); aw = aw / max(np.linalg.norm(aw), 1e-3)
        mn.hold(S.land[lk[0]] - 2.5 + 1.3 * k_, *[c_.strip() for c_ in a_.split(',')])   # (judge Q06: staggered, 1.3 s apart)
        if k_ == 0:                                          # (judge Q06: two identical statues aiming side by side for 10 s: one walks a few steps towards the platform and watches,
            mn.tf = 0.92                                     #  the other stands easy and looks about, at his own pace. Owner 11-15 S20: nobody aims - no tense / alert clips)
            if FIX1123:                                      # (fix1123-story S3, owner film 2:19 'two soldiers inside each other': the 2.2 m sidestep (aw turned right) ended
                ow_ = np.array(pw[0]) - np.array(pw[1]); ow_ = ow_ / max(np.linalg.norm(ow_), 1e-3)   #  exactly on unloader 1's spot, pw[1] is pw[0] + 2.2 m
                mn.stroll([S.on(pw[0][0] + 1.8 * ow_[0], pw[0][1] + 1.8 * ow_[1])], face=math.atan2(-aw[0], aw[1]) + math.pi)   #  the same way; now 1.8 m AWAY from him)
            else:
                mn.stroll([S.on(pw[0][0] + 2.2 * aw[1], pw[0][1] - 2.2 * aw[0])], face=math.atan2(-aw[0], aw[1]) + math.pi)
            mn.hold(S.total + 2.0, 'stand', 'stand_streatch_neck', 'stand', 'stand_wipe_nose', shuffle=False)
        else:
            mn.tf = 1.08
            mn.hold(S.total + 2.0, 'stand_clean_weapon', 'stand', 'stand_bugged_by_fly', 'stand', shuffle=False)
        mn.finish(S.total + 2.0)
