"""ssgun - Sandstorm item 63 (owner 11-06): the base lift gets three stops (top, gun room, bottom; each press moves it one stop) and the GUN ROOM: a new concrete box on the
hall's west wall, 8.4 m over the gallery floor, with a big open window over the site, sandbags and the M2HB the player mans (original missions 14/15: StationaryGun 112_02_1
on stand 106_03_1 inside sandbag ring 400_45_1, body 0.7 m behind the gun). A steel stair runs from the room's north door to the hall floor: it is how the garrison comes for
Jones when he opens fire, and a third way down for him. The layout is new; only the gun, the stand and the bags are original small assets. Behind env SS_GUNROOM=1.

Lift facts (igi2-decomp lift.c, Lift_RunHandler): 'Floor up' moves to the NEXT Floor sibling, 'Floor down' to the previous one, so floor order = 0 top, 1 gun room, 2 bottom
and 'Floor up' is the way DOWN the shaft here. The two cab gates ride on the cab: the exit gate serves both lower stops (both open east). World metres."""
import copy, math, os
import numpy as np
import ssbase as SB
import ssv4 as V
import ssgarr as GR
from ssbase import Mesh, F
from ssgarr import wallrun, floor, stair, rail, landing, ceil_lamp, wall_lamp, DOOR_H

M = 4096.0
R0, RT = 8.4, 11.6                                         # room floor, ceiling (rel F)
FZ = F + R0
SLAB = 0.7                                                 # (the sandbag ring reaches 0.64 m under its origin)
_hx0, _hy0, _hx1, _hy1 = V.shaft_rect()
RX0, RX1, RY0, RY1 = _hx1 + 0.31, 175.4, 218.7, 234.7      # room inside (0.31: the shaft's wall is 0.30, its face must not fight the room's)
WT = 0.4                                                   # outer walls
OP0, OP1 = _hy0 - 0.3, _hy1 + 0.3                          # the lift's opening in the shaft's east wall
CY = V.LIFT_C[1]
WIN = (219.7, 233.7, R0 + 0.85, R0 + 2.9)                  # the big window: y0, y1, sill, head (rel F)
NOTCH = (CY - 2.2, CY + 2.2, R0 + 0.45)                    # (gf2: from 1.5 m behind a 1 m sill the gun could not reach the floor, the rounds chewed the sill) the sill drops at the gun
GUN = (174.7, CY, FZ + 1.31)                               # (L14: the gun 1.31 m over the ground, the stand under it; here at the ring's front bags, the muzzle over them, so it reaches the gallery floor)
RING_X = 173.94                                            # the sandbag ring's middle: its front bags fill the notch
GUN_YAW = 3 * math.pi / 2                                  # (barrel = (-sin g, cos g), proven on L14's gunner standing at (sin g, -cos g)): east
GUN_LIMITS = (15, -40, 62, -1)                             # up, down, sideways, ammo (-1 = unlimited: owner, no time to reload)
MGSIGHT_UP = 5                                             # (sight v2) up limit with the scope on: the window band then never reaches the crossbar
CAB_TONE = 0.5                                             # (the cab's texture over the shaft's light)
GUN_HEAR = 0.02                                            # (the soldiers' hearing factor while Jones is on the gun)
ROOM_G = 12                                                # (owner 91) the room's own AI graph
STAIR_ACC = 45                                             # (owner 91) their close aim
WAVES = (35, 90, 150)                                      # (owner 91) stair teams, s
GUN_ACC = (14, 2, 1)                                       # (owner 89: soldiers' min, med, max range accuracy % while Jones is on the gun. C3 default 65-70, 20, 15-17; a shot gets x2 after 4 s in sight, igi2 HumanAIContent)
WB_Z, WB_Y = FZ + 1.45, RY1 - 0.06                         # (owner 99) the wooden bar on the wall left of the stair door: height, its middle off the wall
WB_X0, WB_SLIDE, WB_LEN = 172.70, 0.28, 0.9               # its middle at rest; Jones' push moves it 0.28 m right, its right end then crosses the door's edge into the staple
# (fix1122-use U5, owner pic 11 round 2: 'the door is closed but the wood bar is still on the wall, not on the door'. The 0.28 m push only put the bar's
#  end over the door's edge. Now a 1.5 m bar that rests on the wall left of the doorway and slides 1.5 m ACROSS the closed leaf, into two staples on the
#  jambs either side (DOOR_X - 0.07, DOOR_X + 1.27): barred = the bar lies across the whole door)
WB_X0, WB_SLIDE, WB_LEN = 172.40, 1.50, 1.5
WB_USE = (172.85, RY1 + 0.57, WB_Z)                       # use point: the engine stands Jones 0.85 m in front of it, press_alarm's right hand reaches 0.22 m ahead, so the point sits 0.63 m behind the bar
MAX_RANGE_ACC = 7                                          # (the engine's default 20 %: the far end of the soldiers' accuracy line, past their 30 m med range)
DOOR_X = 173.3                                             # the stair door in the north wall, x0..x0 + 1.2
LANDY1 = RY1 + WT + 2.0
ST_X0, ST_X1 = 172.12, 173.62                              # the stair against the hall's west wall
ST_Y1 = LANDY1 + 12.0
SLOTS = ['ss_gw', 'ss_gi', 'ss_gi2', 'ss_gf', 'ss_gc', 'ss_bc', 'ss_lamp', 'ss_hz', 'ss_stl', 'ss_duct', 'ss_cc']
HALL_CUT = (RY0 - WT, RY1 + WT, FZ - SLAB, F + RT + 0.35)  # where the room goes through the hall's west wall (y0, y1, z0, z1)


def room():
    me = Mesh(((RX0 + RX1) / 2, (RY0 + RY1) / 2, FZ), SLOTS)
    z0, z1 = R0 - SLAB, RT + 0.35
    RF = (R0, RT, 'ss_gi2', 3.0)                           # (judge R06: its own wall, panels and bolts, not the garrison's plain distemper)
    x2, y0, y1 = RX1 + WT, RY0 - WT, RY1 + WT
    # --- the front wall with the window, side walls (the stair door in the north one), back wall round the lift's opening
    wallrun(me, 'x', RX1, -1, y0, y1, z0, z1, [(WIN[0], NOTCH[0], WIN[2], WIN[3]), (NOTCH[0], NOTCH[1], NOTCH[2], WIN[3]), (NOTCH[1], WIN[1], WIN[2], WIN[3])], rooms=[RF], tout='ss_gw', thick=WT, tbase=216.0, oz=(z0, z1))
    wallrun(me, 'y', RY0, 1, RX0, x2, z0, z1, rooms=[RF], tout='ss_gw', thick=WT, tbase=168.0, oz=(z0, z1))
    wallrun(me, 'y', RY1, -1, RX0, x2, z0, z1, [(DOOR_X, DOOR_X + 1.2, R0, R0 + DOOR_H)], rooms=[RF], tout='ss_gw', thick=WT, tbase=168.0, oz=(z0, z1))
    wallrun(me, 'x', RX0, 1, y0, y1, R0, RT, [(OP0, OP1, R0, R0 + 2.7)], rooms=[RF], thick=0.3, tbase=216.0)
    # --- floor: the threshold reaches 5 cm over the cab's floor edge (rig lift2: Jones dips in a 5 cm gap, the cab passes clear of the plate), slab, soffit, ceiling, roof
    floor(me, 'ss_gf', RX0, RY0, RX1, RY1, FZ)
    floor(me, 'ss_gf', _hx1 - 0.05, _hy0, _hx1, _hy1, FZ + 0.008)        # (8 mm: the shaft wall's top lies at FZ)
    floor(me, 'ss_gf', _hx1, OP0, RX0, OP1, FZ + 0.008)
    me.box(None, RX0, y0, FZ - SLAB, x2, y1, FZ)
    me.box(None, _hx1 - 0.05, _hy0, FZ - 0.2, RX0, _hy1, FZ)
    floor(me, 'ss_gw', 172.0, y0, x2, y1, FZ - SLAB, up=False)
    floor(me, 'ss_gc', RX0, RY0, RX1, RY1, F + RT, up=False)
    me.box(None, RX0, y0, F + RT, x2, y1, F + z1)
    floor(me, 'ss_gw', 172.0, y0, x2, y1, F + z1)
    # --- (owner 99) the staple on the door's edge that takes the wooden bar once it is slid (the two it rests in are the use point's model)
    for _sx in (DOOR_X - 0.07, DOOR_X + 1.27):              # (fix1122-use U5: a staple on each jamb, the slid bar lies across the leaf between them)
        staple(me, _sx, RY1, WB_Z, -1)
    # --- hazard line at the lift, a steel ledge on the sill, two thin mullions (the bullets pass them)
    me.box('ss_hz', RX0 + 0.02, _hy0, FZ, RX0 + 0.16, _hy1, FZ + 0.012, uv=0.5, solid=False)
    for a, b, z_ in ((WIN[0], NOTCH[0], WIN[2]), (NOTCH[0], NOTCH[1], NOTCH[2]), (NOTCH[1], WIN[1], WIN[2])):
        me.box('ss_stl', RX1 - 0.06, a, F + z_ - 0.03, x2 + 0.06, b, F + z_, uv=0.5, solid=False)
    # --- on the hall side: two columns over the lobby door, the steel under the box
    for y in (RY0 + 0.1, RY1 - 0.1):
        me.box('ss_cc', x2 - 0.75, y - 0.4, F, x2 + 0.05, y + 0.4, FZ - SLAB, uv=0.25)
        me.box('ss_hz', x2 - 0.79, y - 0.44, F, x2 + 0.09, y + 0.44, F + 1.3, uv=0.75, solid=False)
    for y in (RY0 + 0.1, CY - 4.0, CY + 4.0, RY1 - 0.1):
        me.box('ss_stl', 172.0, y - 0.14, FZ - SLAB - 0.32, x2 + 0.02, y + 0.14, FZ - SLAB, uv=0.5, solid=False)
    me.box('ss_stl', x2 - 0.2, y0, FZ - SLAB - 0.32, x2 + 0.02, y1, FZ - SLAB, uv=0.25, solid=False)
    # --- lamps: low and warm so the hall stays the bright thing in the window; pipes under the ceiling
    for y in (RY0 + 3.0, CY, RY1 - 3.0):
        ceil_lamp(me, 170.6, y, F + RT, 'y', L=1.0, size=420.0)
        cage(me, 170.6, y, F + RT, 1.0)
    ceil_lamp(me, 174.2, CY, F + RT, 'y', L=0.6, size=260.0)
    cage(me, 174.2, CY, F + RT, 0.6)
    # --- (judge R06) the walls carry the room's services: a fuse panel and its conduits, a cable tray under the ceiling
    zc = F + RT
    me.box('ss_stl', 169.1, RY0, FZ + 1.3, 169.7, RY0 + 0.12, FZ + 1.9, uv=0.5, solid=False)
    me.box('ss_hz', 169.15, RY0 + 0.12, FZ + 1.78, 169.65, RY0 + 0.125, FZ + 1.85, uv=0.5, solid=False)
    for x_, z_ in ((169.37, FZ + 1.9), (172.6, FZ + 0.3), (RX1 - 0.4, FZ + 0.3)):
        me.box('ss_duct', x_, RY0, z_, x_ + 0.06, RY0 + 0.06, zc - 0.3, uv=0.5, solid=False)
    me.box('ss_stl', 172.5, RY0, FZ + 1.1, 172.76, RY0 + 0.1, FZ + 1.4, uv=0.5, solid=False)
    me.box('ss_duct', 169.0, RY1 - 0.06, FZ + 0.3, 169.06, RY1, zc - 0.3, uv=0.5, solid=False)
    me.box('ss_stl', 168.9, RY1 - 0.1, FZ + 1.2, 169.16, RY1, FZ + 1.5, uv=0.5, solid=False)
    for y_, s_ in ((RY0, 1), (RY1, -1)):
        a_, b_ = sorted((y_, y_ + s_ * 0.25))
        me.box('ss_stl', 168.1, a_, zc - 0.33, RX1 - 0.1, b_, zc - 0.3, uv=0.5, solid=False)
        c_, d_ = sorted((y_ + s_ * 0.24, y_ + s_ * 0.25))
        me.box('ss_stl', 168.1, c_, zc - 0.33, RX1 - 0.1, d_, zc - 0.25, uv=0.5, solid=False)
    me.cyl('ss_duct', 0.07, RY0, RY1, 'y', (RX0 + 0.3, F + RT - 0.25), uv=0.5, seg=8)
    me.cyl('ss_duct', 0.05, RY0, RY1, 'y', (RX0 + 0.3, F + RT - 0.45), uv=0.5, seg=8)
    # --- the landing outside the door, the stair down the west wall
    landing(me, 172.05, y1, x2, LANDY1, FZ)
    rail(me, x2 - 0.05, y1, x2, LANDY1, FZ)
    rail(me, ST_X1, LANDY1 - 0.05, x2, LANDY1, FZ)
    stair(me, LANDY1, ST_Y1, ST_X0, ST_X1, FZ, F, axis='y', rails=(False, True))
    me.box('ss_stl', ST_X0, ST_Y1 - 0.5, F, ST_X1, ST_Y1 + 0.3, F + 0.03, uv=0.5, solid=False)
    wall_lamp(me, 172.1, LANDY1 - 0.9, FZ + 2.6, 1.0, 0.0, 700.0)
    # --- (S14 decision 91, ported by hand fix1120-logic L12 from main 26fb84e) the lobby barricade's collision: one box inside the sandbags (screen_props), so rounds and eyes stop at it
    if S14B_ON:
        me.box(None, *SCREEN_BOX)
    # --- dark rock behind the walls that stand in the hill (a pressed camera clips through them; rv8)
    bk = 1.0
    bx0, by0, by1, bz0, bz1 = RX0 - 0.3 - bk, y0 - bk, y1 + bk, FZ - SLAB - bk, F + z1 + bk
    for y_, s in ((by0, 1), (by1, -1)):
        me.quad('ss_bc', (bx0, y_, bz0), (172.0, y_, bz0), (172.0, y_, bz1), (bx0, y_, bz1), (0, s, 0))
    for a, b in ((by0, OP0), (OP1, by1)):
        me.quad('ss_bc', (bx0, a, bz0), (bx0, b, bz0), (bx0, b, bz1), (bx0, a, bz1), (1, 0, 0))
    me.quad('ss_bc', (bx0, by0, bz0), (172.0, by0, bz0), (172.0, by1, bz0), (bx0, by1, bz0), (0, 0, 1))
    me.quad('ss_bc', (bx0, by0, bz1), (172.0, by0, bz1), (172.0, by1, bz1), (bx0, by1, bz1), (0, 0, -1))
    return me


# (name, model, x, y, z over the room floor, yaw): the ring at the gun, bags along the window, the crew's corner
PROPS = [('stand', '106_03_1', GUN[0], GUN[1], 0.0, 0.66), ('ring', '400_45_1', RING_X, GUN[1], 0.0, GUN_YAW)]
for k_, y_ in enumerate((CY - 5.9, CY - 3.8, CY + 3.8, CY + 5.9)):
    PROPS.append(('bags %d' % k_, GR.SB_STRAIGHT, RX1 - 0.34, y_, 0.0, math.pi / 2))
PROPS += [('crew table', '231_03_1', 170.2, 232.4, 0.0, 0.0), ('crew chair 1', '261_06_1', 169.4, 231.3, 0.0, 2.8 - math.pi), ('crew chair 2', '261_06_1', 171.1, 231.3, 0.0, 3.5 - math.pi),
          ('ammo case 1', '306_01_1', 169.4, 220.0, 0.0, 0.0), ('ammo case 2', '306_01_1', 171.8, 220.0, 0.0, 0.1), ('crate', '330_01_1', 174.1, 219.9, 0.0, 0.3), ('crate 2', '330_01_1', RX0 + 0.66, RY1 - 0.66, 0.0, 0.0)]   # (fix1122-use U8, owner pic 10 round 2: the 2.4 m crate 330_02_1 at (168.9, 233.6) swallowed the crew table's west end and medipack 1; now the 1.2 m crate in the north-west corner, 0.5 m clear of the table)
LOOT = (('medipack 1', 'WEAPON_ID_MEDIPACK', 169.9, 232.4, 0.82), ('medipack 2', 'WEAPON_ID_MEDIPACK', 170.6, 232.5, 0.82))
MGSIGHT_ON = os.environ.get('SS_MGSIGHT', '1') == '1'      # (owner 11-12, rc7r) the gunner's box sight on the gun's own holder; the exe (v11) draws the window, owns zoom and heat
MGSIGHT_COMPACT = MGSIGHT_ON and os.environ.get('SS_MGSIGHT_COMPACT', '1') == '1'   # (sight v3) the compact scope on the receiver: needs the exe that hides the gun in the sight (v14)
SIGHT_ON = not MGSIGHT_ON and os.environ.get('SS_SIGHT', '1') == '1'           # (owner 97) the thermal sight: proven 11-08 (th6, th7), SS_SIGHT=0 leaves it out
SIGHT = (170.3, 232.15, 0.84)                              # (owner 97) the thermal sight on the medic table, beside the medipacks
CAM_R, PIN_R = 0.55, 0.70                                  # (owner 117) half sizes of the eye box and the body box round the pivot
MOUNT = (173.7, 226.7)                                     # (owner 97) where the engine counts a MOUNTED Jones for AreaActivate (probe th5: the box at 173.7 lit only on the gun; his drawn body sits at 174.65, his feet on foot at 173.1-173.4)
S14B_ON = os.environ.get('SS_S14B', '1') == '1'           # (S14 owner 11-15 'men hiding underneath shoot at him through the wall'; PLAN decision 91, 11-17; fix1120 L12 port of main 26fb84e) the lobby barricade, below
SCREEN_X = 173.78                                          # (S14) the sandbag wall in front of the lift doorway (hall side, under the gun room): its middle, world x. 1.4 m walk passage to the hall's west wall face (x 172.0)
SCREEN_N, SCREEN_STEP, SCREEN_Y0 = 5, 1.8, 223.1           # five 2 m straights per row, 0.2 m overlap: y 222.1 - 231.3 (the doorway y 225.4 - 228.0)
SCREEN_ROWS, SCREEN_ROW_H = 2, 1.16                        # two rows (360_05_1 is 1.18 m high): top 2.34 m, the door head is 2.5
SCREEN_BOX = (173.48, 222.25, F, 174.05, 231.15, F + 2.30)  # (S14) the bullet-stop box inside the bags (gun room mesh): x0, y0, z0, x1, y1, z1
CREW = ((170.0, 230.6, -1.466, 'stand_talk1'), (171.9, 230.8, 1.676, 'stand_talk2'))   # (S11-A owner 11-15 'two soldiers both looking at the wall': the old 0.3 / 3.5 rad stood them 101 / 105 degrees off each other, one nose to the furniture; now face to face across 1.9 m)


def three_stops(g):
    """the third Floor goes between the two of place_lift; a direction variable flips at both ends, each press = one stop (the rules: gates())"""
    m, LIFT, nid, lit, Call, v = g['m'], g['LIFT'], g['nid'], g['lit'], g['Call'], g['v']
    lid = LIFT['lift']
    t = m.byid[lid]
    fl = [a for a in t.args if isinstance(a, Call) and lit(a.args[1]) == 'Floor']
    assert len(fl) == 2
    mid = copy.deepcopy(fl[0])
    mid.args[0] = v(nid())
    mid.args[5] = v((FZ + V.CAB_DZ) * M)
    t.args.insert(t.args.index(fl[0]) + 1, mid)
    m.reindex()
    LIFT['dir'] = _var(g, 'SS lift direction (0 down the shaft, 1 up)', 'EditVariable_%d.nValue == 0 && Lift_%d.nCurrentFloor == 2', 'EditVariable_%d.nValue == 1 && Lift_%d.nCurrentFloor == 0')
    print('ssgun: three stops, floors %s, direction variable %d, gun room floor %.2f m' % ([lit(f.args[0]) for f in (fl[0], mid, fl[1])], LIFT['dir'], FZ))


def _var(g, name, add, sub):
    """an EditVariable beside the lift's go variable; add / sub rules name it and the lift by two %d"""
    m, LIFT, nid, v = g['m'], g['LIFT'], g['nid'], g['v']
    i = nid()
    t = m.byid[LIFT['lift']]
    dv = copy.deepcopy(m.byid[LIFT['var']])
    assert 'isPressed' in g['lit'](dv.args[7]) and 'isMoving' in g['lit'](dv.args[8])
    dv.args[0] = v(i); dv.args[2] = v(name)
    dv.args[7] = v(add % (i, LIFT['lift'])); dv.args[8] = v(sub % (i, LIFT['lift']))
    t.args.insert(t.args.index(m.byid[LIFT['var']]) + 1, dv)
    m.reindex()
    return i


def gates(g):
    """(the stair lets Jones reach a stop the cab is not at: an open shaft, 8 m down) a mesh landing gate at the two lower stops, open only with the cab there, and a call
    button by each. Called after roll_gate exists; replaces the lift's and the cab gates' rules"""
    m, LIFT, nid, T = g['m'], g['LIFT'], g['nid'], g['T']
    roll = g['roll_gate']
    lid, var, d = LIFT['lift'], LIFT['var'], LIFT['dir']
    lx, ly = _hx1 + 0.15, (OP0 + OP1) / 2
    G1 = roll('SS lift landing gate, gun room', 'ss_lgate_1', (lx, ly, FZ), 1.2)
    G2 = roll('SS lift landing gate, bottom', 'ss_lgate_1', (lx, ly, F), 1.2)
    S = []
    for nm, x, y, z in (('gun room', RX0 + 0.06, OP0 - 0.7, FZ + 1.3), ('bottom', 167.86, 222.6, F + 1.3)):
        i = nid()
        m.add_child(4029, T(i, 'Switch', 'SS lift call button, ' + nm, x * M, y * M, z * M, 0.0, 0.0, float(GR.face(1, 0)), '1', False, 'button_1', '262_01_1', '262_02_1', '262_01_1', '262_02_1', '262_02_1', False,
                            'STATUSSCREEN:action_pressbutton.spr'))
        S.append(i)
    f = 'Lift_%d.nCurrentFloor' % lid
    C1 = _var(g, 'SS lift called to the gun room', 'EditVariable_%%d.nValue == 0 && Switch_%d.isPressed && Lift_%%d.nCurrentFloor != 1' % S[0], 'EditVariable_%%d.nValue == 1 && Lift_%%d.nCurrentFloor == 1 && !Lift_%d.isMoving' % lid)
    C2 = _var(g, 'SS lift called to the bottom', 'EditVariable_%%d.nValue == 0 && Switch_%d.isPressed && Lift_%%d.nCurrentFloor != 2' % S[1], 'EditVariable_%%d.nValue == 1 && Lift_%%d.nCurrentFloor == 2 && !Lift_%d.isMoving' % lid)
    go, c1, c2, dn0 = 'EditVariable_%d.nValue == 1' % var, 'EditVariable_%d.nValue == 1' % C1, 'EditVariable_%d.nValue == 1' % C2, 'EditVariable_%d.nValue == 0' % d
    doors = ' && '.join('Door_%d.isClosed' % i for i in (LIFT['gate_in'], LIFT['gate_out'], G1, G2))
    up = '((%s && %s && %s < 2) || (%s && %s < 2) || (%s && %s == 0)) && %s' % (go, dn0, f, c2, f, c1, f, doors)
    down = '((%s && EditVariable_%d.nValue == 1 && %s > 0 && EditVariable_%d.nValue == 0) || (%s && %s == 2)) && %s' % (go, d, f, C2, c1, f, doors)   # (review: a press and a bottom call in one gate-close window fired both rules)
    t = m.byid[lid]
    n = 0
    for k, a in enumerate(t.args):
        s_ = g['lit'](a) if not isinstance(a, g['Call']) else None
        if isinstance(s_, str) and 'nCurrentFloor == 1' in s_:
            m.set(lid, k, down); n += 1
        elif isinstance(s_, str) and 'nCurrentFloor == 0' in s_:
            m.set(lid, k, up); n += 1
    assert n == 2, n
    still = '!Lift_%d.isMoving && EditVariable_%d.nValue == 0 && EditVariable_%d.nValue == 0 && EditVariable_%d.nValue == 0' % (lid, var, C1, C2)
    shut = '%s || %s || %s' % (go, c1, c2)
    for i, fl_ in ((LIFT['gate_in'], '== 0'), (LIFT['gate_out'], '> 0'), (G1, '== 1'), (G2, '== 2')):
        m.set(i, 18, '1'); m.set(i, 19, 'Door_%d.isClosed && %s %s && %s' % (i, f, fl_, still)); m.set(i, 20, shut)
    for i in (G1, G2):
        m.set(i, 7, 2.85); m.set(i, 21, True)
    bar = roll('SS gun room door bar', 'ss_wbar_1', (WB_X0, WB_Y, WB_Z), 0.8)   # (fix1122-use U5: 1.5 m of slide, 0.8 s)   # (owner 99: the wooden bar slides with Jones' push, from the start of the use)
    did, lock, pad = g['GUNROOM_DOOR'], g['GUNROOM_LOCK'], g['GUNROOM_PAD']
    m.set(bar, 6, WB_SLIDE); m.set(bar, 7, 0.0)            # (args 6, 7 = the slide in the leaf's x, y: a lying leaf's y is world up, wb1 slid it up)
    m.set(bar, 19, 'GenericTBA_%d.isInUse || GenericTBA_%d.isFinished || EditVariable_%d.nValue == 1' % (pad, pad, lock))
    m.set(bar, 20, '!GenericTBA_%d.isInUse && !GenericTBA_%d.isFinished && EditVariable_%d.nValue == 0' % (pad, pad, lock))   # (review: no tick where the use is over but the lock not yet counted; as ssbay)   # (a use let go early: the bar goes back)
    for k_ in (24, 25, 26, 27):                            # (no blast-door noise: the use's own sound is the slide)
        m.set(bar, k_, '')
    m.set(bar, 21, False)                                  # (fix1122-use U5: StopOnCollision off: a leaf an AI left open must not stop the bar half way)
    m.set(S[0], 9, '!Lift_%d.isMoving && %s != 1 && EditVariable_%d.nValue == 0' % (lid, f, C1))
    m.set(S[1], 9, '!Lift_%d.isMoving && %s != 2 && EditVariable_%d.nValue == 0' % (lid, f, C2))
    LIFT.update(gate_mid=G1, gate_bot=G2, call=S, c1=C1, c2=C2)
    print('ssgun: landing gates %d %d, call buttons %s, rule lengths up %d down %d' % (G1, G2, S, len(up), len(down)))


def cage(me, x, y, z, L):
    """(judge R06) a steel housing round a ceiling lamp and three guard bars under its face (the lamp itself is ssgarr.ceil_lamp, along y, 18 cm wide)"""
    dy = L / 2 + 0.04
    me.box('ss_stl', x - 0.14, y - dy, z - 0.13, x - 0.11, y + dy, z, uv=0.5, solid=False)
    me.box('ss_stl', x + 0.11, y - dy, z - 0.13, x + 0.14, y + dy, z, uv=0.5, solid=False)
    for s_ in (-1, 1):
        a_, b_ = sorted((y + s_ * dy, y + s_ * (dy - 0.02)))
        me.box('ss_stl', x - 0.13, a_, z - 0.09, x + 0.13, b_, z, uv=0.5, solid=False)
    for k_ in range(3):
        yy = y - L / 2 + (k_ + 0.5) * L / 3
        me.box('ss_stl', x - 0.13, yy - 0.018, z - 0.125, x + 0.13, yy + 0.018, z - 0.09, uv=0.5, solid=False)   # (tour 55a0fe04: 1.6 cm bars did not show from the floor)


def tex_gi2(get):
    """(judge R06) the gun room's wall, 3 x 3.2 m: concrete panels with seams and bolt heads, rust run from each bolt, the olive dado and a steel kick strip"""
    from ssbase import _tile, _noise, _rgba
    n = 256
    a = _tile(get('409_17_1'), 2, 2, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    L = a.mean(2) / max(float(a.mean()), 1e-3)
    b = (0.46 + 0.20 * L) * (0.78 + 0.22 * _noise(n, n, 71))
    img = np.dstack([b * 0.92, b * 0.86, b * 0.72])
    for uu in (0.0, 0.5, 1.0):                             # seams between panels
        d_ = np.abs(u - uu)
        img[d_ < 0.006] *= 0.45
        img[(d_ >= 0.006) & (d_ < 0.012)] *= 1.12
    img[np.abs(v - 0.30) < 0.005] *= 0.5
    img[(v - 0.30 >= 0.005) & (v - 0.30 < 0.010)] *= 1.1
    for bu in (0.035, 0.465, 0.535, 0.965):                # bolt heads, rust running down from each
        for bv in (0.04, 0.26, 0.34, 0.56):
            r = np.hypot((u - bu) * n, (v - bv) * n)
            img[r < 3.2] = (0.22, 0.20, 0.17)
            img[(r < 1.6) & (u < bu) & (v < bv)] = (0.55, 0.52, 0.46)
            run = (np.abs(u - bu) < 0.012) & (v > bv) & (v < bv + 0.16)
            k_ = np.clip(1 - (v - bv) / 0.16, 0, 1) * (1 - np.abs(u - bu) / 0.012)
            img[run] = img[run] * (1 - 0.35 * k_[run, None]) + np.array([0.30, 0.17, 0.08]) * 0.35 * k_[run, None]
    img *= (0.85 + 0.3 * _noise(n, n, 72, (2, 4, 8)))[..., None]
    d = v > 0.60
    img[d] = np.dstack([b * 0.42, b * 0.50, b * 0.34])[d]
    img[(v > 0.595) & (v <= 0.605)] = (0.20, 0.18, 0.12)
    img[v > 0.94] = np.dstack([b * 0.55, b * 0.56, b * 0.58])[v > 0.94]
    img[(v > 0.935) & (v <= 0.942)] = (0.12, 0.12, 0.12)
    return _rgba(img)


def staple(me, x, yw, z, s):
    """a steel U the wooden bar rides in: on the wall face at yw, open toward s (-1 = the room lies at smaller y)"""
    f = yw + s * 0.11
    for a, b in ((0.06, 0.08), (-0.08, -0.06)):
        me.box('ss_stl', x - 0.03, min(yw, f), z + a, x + 0.03, max(yw, f), z + b, uv=0.5, solid=False)
    me.box('ss_stl', x - 0.03, min(f, f - s * 0.012), z - 0.08, x + 0.03, max(f, f - s * 0.012), z + 0.08, uv=0.5, solid=False)


def wbar_model():
    """(owner 99) the wooden bar: WB_LEN long, 10 cm high, 6 cm thick, a grip in the middle. Built upright, turned to lie like the roll gates (local y = world up once alpha turns it)"""
    me = Mesh((0, 0, 0), ['ss_gwood'])
    h = WB_LEN / 2
    me.box('ss_gwood', -h, -0.03, -0.05, h, 0.03, 0.05, uv=0.4, solid=False)
    me.box('ss_gwood', -0.05, -0.08, -0.025, 0.05, 0.08, 0.025, uv=0.4, solid=False)
    me.box(None, -h, -0.03, -0.05, h, 0.03, 0.05)
    R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    for k_ in me.g:
        me.g[k_] = [(P_ @ R.T, T_, N_ @ R.T, U_) for P_, T_, N_, U_ in me.g[k_]]
    me.coll = [(P_ @ R.T, T_, N_ @ R.T, U_) for P_, T_, N_, U_ in me.coll]
    return me.model(even=['ss_gwood'])


def wbuse_model():
    """(owner 99) the use point's model: the two staples the bar rests in, drawn 0.63 m in front of the point (gamma pi: local = point - world in x and y). They give the use point a body, so E engages from a wide angle"""
    me = Mesh((0, 0, 0), ['ss_stl'])
    for xw in (WB_X0 - 0.30, WB_X0 + 0.25):
        staple(me, WB_USE[0] - xw, WB_USE[1] - RY1, 0.0, 1)
    me.box(None, WB_USE[0] - WB_X0 - 0.35, WB_USE[1] - RY1, -0.08, WB_USE[0] - WB_X0 + 0.35, WB_USE[1] - RY1 + 0.11, 0.08)
    return me.model(even=['ss_stl'])


def lgate_model():
    """a landing gate: steel frame round a mesh, the opening's full width and 2.72 m high; origin = bottom centre. Turned up by alpha like the roll gates"""
    hw, h = (OP1 - OP0) / 2 - 0.02, 2.72
    me = Mesh((0, 0, 0), ['ss_stl', GR.S_MESH])
    uv = [(0, h / 2), (hw, h / 2), (hw, 0), (0, 0)]
    for s_ in (1, -1):
        me.quad(GR.S_MESH, (0, -hw, 0), (0, hw, 0), (0, hw, h), (0, -hw, h), (s_, 0, 0), uv)
    for a in ((-hw, -hw + 0.1, 0, h), (hw - 0.1, hw, 0, h), (-hw, hw, 0, 0.1), (-hw, hw, h - 0.1, h), (-hw, hw, 1.3, 1.38), (-0.04, 0.04, 0, h)):
        me.box('ss_stl', -0.04, a[0], a[2], 0.04, a[1], a[3], uv=0.5, solid=False)
    me.box(None, -0.05, -hw, 0, 0.05, hw, h)
    R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    for k_ in me.g:
        me.g[k_] = [(P_ @ R.T, T_, N_ @ R.T, U_) for P_, T_, N_, U_ in me.g[k_]]
    me.coll = [(P_ @ R.T, T_, N_ @ R.T, U_) for P_, T_, N_, U_ in me.coll]
    return me.model(alpha=(GR.S_MESH,), even=['ss_stl'])


def models(g):
    X, VLIB = g['X'], g['_VLIB']
    # (gf4, gf5: a rifle grenade through the window ended the fight in 18 s, Jones blown off the gun at full run; cb1 knew this blast) rifles instead on the posts that see the window
    for key in ('U deck west', 'U road post', 'U ready') + (() if os.environ.get('SS_RQ8', '1') == '0' else ('U deck east', 'U spur')):   # (RQ8 11-16: N-e5 flash2's grenade came from the far gallery = deck east; the spur man looks down on the hall too)
        ty, hold_, spots = GR.POSTS[key]
        GR.POSTS[key] = ('N', hold_, [sp[:5] + (GR.AK if sp[5] == GR.AKG else sp[5],) for sp in spots])   # (gf6: with the alarm on, 10 s to death at the gun: normal soldiers, not tough ones, on the posts in sight)
    X.models('location1/level4', ['400_45_1', '106_03_1'])
    X.models('location2/LEVEL5', ['112_02_1'])
    me = room()
    g['_GNMESH'] = me
    VLIB.add('ss_gunr_1', lambda: me.model(even=SLOTS), SLOTS, lod_like='406_68_1')
    VLIB.add('ss_lgate_1', lgate_model, ['ss_stl', GR.S_MESH], lod_like='406_68_1')
    import ssrooms
    VLIB.texture('ss_gwood', ssrooms.tx_wood)
    VLIB.texture('ss_gi2', lambda: tex_gi2(g['_sbget']))
    VLIB.add('ss_wbar_1', wbar_model, ['ss_gwood'], lod_like='406_68_1')
    VLIB.add('ss_wbu_1', wbuse_model, ['ss_stl'], lod_like='406_68_1')
    if SIGHT_ON:                                           # (review: no model row or LOD slot for a sight that is off)
        VLIB.add('ss_tsight_1', sight_model, ['ss_stl', 'ss_hz'], lod_like='406_68_1')


def tone_cab(ovl):
    """(owner 75: the L12 cab's lightmap does not come with it, its rails drew as flat glowing orange in the dark shaft) its texture toned down to the shaft's light, in place in the overlay's bank"""
    import ilff, altex
    p = os.path.join(ovl, 'textures', 'sandstorm.res')
    form, ch, hdr = ilff.read(open(p, 'rb').read())
    for name in (b'LOCAL:textures/elevator.tex', b'LOCAL:textures/203_02_1.tex'):      # (the cab, its two gates; only those two models use them)
        k = next(i for i, (t, d, a) in enumerate(ch) if t == b'NAME' and d.rstrip(b'\x00') == name)
        b = ch[k + 1][1]
        rgb, al, _ = altex.read(b)
        ch[k + 1] = (b'BODY', altex.write_like(b, rgb * CAB_TONE, al), ch[k + 1][2])
    tmp = p + '.gn.tmp'
    open(tmp, 'wb').write(ilff.write(form, ch, hdr[1] or 4))
    os.replace(tmp, p)
    print('ssgun: cab texture toned x %.2f' % CAB_TONE)


def dark_camera(ovl, level='sandstorm', tone=0.32):
    """(owner 83: the feed camera in the lift room drew white in the dark) the two camera meshes copied whole under new names, on a darkened copy of their texture. Their magic vertices stay, SCamera needs them"""
    import ilff, altex, mtp, wreck
    import prefab
    lv = prefab.Level(os.path.join(prefab.GAME, 'MISSIONS', 'multiplayer', 'sandstorm'))
    pm, pt, pmd = os.path.join(ovl, level + '.mtp'), os.path.join(ovl, 'textures', level + '.res'), os.path.join(ovl, 'models', level + '.res')
    m = mtp.read(pm)
    form, ch, hdr = ilff.read(open(pt, 'rb').read())
    b = lv.find_resource('LOCAL:textures/313_13_1.tex', 'textures')[1]
    rgb, al, _ = altex.read(b)
    ch.append((b'NAME', b'LOCAL:textures/ss_camd.tex' + bytes(1), 4))
    ch.append((b'BODY', altex.write_like(b, rgb * tone, al), 4))
    m['TEXF'].append('ss_camd')
    m['GTT'].append([len(m['TEXF']) - 1, -1])
    gt = len(m['GTT']) - 1
    mform, mch, mhdr = ilff.read(open(pmd, 'rb').read())
    for src, nm in (('313_07_1', 'ss_cam7_1'), ('313_06_1', 'ss_cam6_1')):
        mefn = lv.find_vnam(src).entry(src)[0]
        mch.append((b'NAME', ('LOCAL:models/%s.mef' % nm).encode('latin1') + bytes(1), 4))
        mch.append((b'BODY', lv.find_resource('LOCAL:models/%s.mef' % mefn, 'models')[1], 4))
        m['MODS'].append(nm)
        m['VNAM'].append(nm)
        m['INST'].append([len(m['MODS']) - 1, [gt]])
    for path, blob in ((pt, ilff.write(form, ch, hdr[1] or 4)), (pmd, ilff.write(mform, mch, mhdr[1] or 4)), (pm, mtp.write(m))):
        tmp = path + '.gn.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    for nm in ('ss_cam7_1', 'ss_cam6_1'):
        wreck._lod_entry(ovl, '406_68_1', nm, level)
    print('ssgun: dark cameras ss_cam7_1, ss_cam6_1')
    if MGSIGHT_ON:
        mg_sight(ovl, level)


def _flat(P, T, uvs=0.08):
    """triangles (P m, T) -> per-triangle vertices with flat normals and planar uv (dominant axis), model units"""
    import numpy as np
    P = np.asarray(P, float)
    V, N, U, TT = [], [], [], []
    for a, b, c in T:
        n = np.cross(P[b] - P[a], P[c] - P[a]); ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n = n / ln
        ax = int(np.argmax(abs(n)))
        o = [k for k in range(3) if k != ax]
        k = len(V)
        for q in (a, b, c):
            V.append(P[q]); N.append(n); U.append((P[q][o[0]] / uvs, P[q][o[1]] / uvs))
        TT.append((k, k + 1, k + 2))
    return np.array(V) * 4096.0, np.array(N), np.array(U), np.array(TT)


def _hull(pts, uvs=0.08):
    """a convex solid from points: outward triangles, flat shaded"""
    import numpy as np
    from scipy.spatial import ConvexHull
    pts = np.asarray(pts, float)
    h = ConvexHull(pts)
    c = pts.mean(0)
    T = []
    for (a, b, cc), eq in zip(h.simplices, h.equations):
        n = np.cross(pts[b] - pts[a], pts[cc] - pts[a])
        T.append((a, b, cc) if n @ eq[:3] > 0 else (a, cc, b))
    return _flat(pts, T, uvs)


def _chamfer(lo, hi, e):
    """a box with bevelled edges (bevel e, m)"""
    import itertools
    pts = []
    for sx, sy, sz in itertools.product((0, 1), repeat=3):
        cx, cy, cz = (hi[0] if sx else lo[0]), (hi[1] if sy else lo[1]), (hi[2] if sz else lo[2])
        dx, dy, dz = (-e if sx else e), (-e if sy else e), (-e if sz else e)
        pts += [(cx + dx, cy, cz), (cx, cy + dy, cz), (cx, cy, cz + dz)]
    return _hull(pts)


def _tube_y(cx, cz, ro, ri, y0, y1, n=14, cap0=True, cap1=True, uvs=0.08):
    """a tube along y (outer radius ro, inner ri; ri 0 = solid), smooth sides, uv u around, v along"""
    import numpy as np
    V, N, U, T = [], [], [], []
    ang = [2 * np.pi * k / n for k in range(n + 1)]
    def ring(r, y, nrm_out):
        out = []
        for k, a in enumerate(ang):
            d = np.array([np.cos(a), 0, np.sin(a)])
            V.append((cx + r * d[0], y, cz + r * d[2])); N.append(d if nrm_out else -d); U.append((k / n, y / uvs)); out.append(len(V) - 1)
        return out
    for r, sgn in ((ro, 1), (ri, -1)):
        if r <= 0:
            continue
        a_, b_ = ring(r, y0, sgn > 0), ring(r, y1, sgn > 0)
        for k in range(n):
            q = (a_[k], a_[k + 1], b_[k + 1], b_[k])
            T += [(q[0], q[2], q[1]), (q[0], q[3], q[2])] if sgn > 0 else [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    for y, on, nrm in ((y0, cap0, (0, -1, 0)), (y1, cap1, (0, 1, 0))):
        if not on:
            continue
        o, i_ = [], []
        for k, a in enumerate(ang):
            d = (np.cos(a), np.sin(a))
            V.append((cx + ro * d[0], y, cz + ro * d[1])); N.append(nrm); U.append((0.5 + 0.5 * d[0], 0.5 + 0.5 * d[1])); o.append(len(V) - 1)
            r2 = max(ri, 1e-4)
            V.append((cx + r2 * d[0], y, cz + r2 * d[1])); N.append(nrm); U.append((0.5 + 0.5 * d[0] * r2 / ro, 0.5 + 0.5 * d[1] * r2 / ro)); i_.append(len(V) - 1)
        for k in range(n):
            q = (o[k], o[k + 1], i_[k + 1], i_[k])
            T += [(q[0], q[1], q[2]), (q[0], q[2], q[3]), (q[0], q[2], q[1]), (q[0], q[3], q[2])]   # (both sides: one winding was culled offline)
    return np.array(V) * 4096.0, np.array(N, float), np.array(U), np.array(T)


def _knob_z(cx, cy, r, z0, z1, n=10):
    """a short knob along z: knurled side, flat top"""
    import numpy as np
    pts = [(cx + r * np.cos(2 * np.pi * k / n), cy + r * np.sin(2 * np.pi * k / n), z) for k in range(n) for z in (z0, z1)]
    return _hull(pts, uvs=0.03)


# (owner 11-12, orchestrator review) the gunner's box sight, metres in the holder's frame: +y the barrel's way, z up from the pivot, -x = left of the bore.
# The holder turns with the gun but never tilts; on the gun the eye sits about 0.45 m behind and 0.2 m over the pivot (probe th10), so the sight rides low on the left
# and the gunner looks at its BACK: the round eyecup end-on, the housing behind it, one knob, a status light. Material slots: 0 sand paint, 1 rubber, 2 glass, 3 light
MG_C = (-0.19, 0.02)                                       # the optic's axis (x, z) as drawn on the left; MG_MIRROR puts it on the right
MG_MIRROR = -0.07                                          # (x -> -x + MG_MIRROR... ): the M2HB's ammo box fills the left up to 0.13 m over the pivot (112_01_1 groups 5, 6), the eye is at 0.2: on the left the sight hid in the box. Right of the receiver it sits low and clear
def mg_parts():
    X = lambda x: -x + MG_MIRROR
    def cb(lo, hi, e):
        return _chamfer((X(hi[0]), lo[1], lo[2]), (X(lo[0]), hi[1], hi[2]), e)
    cx, cz = X(MG_C[0]), MG_C[1]
    return [(0, cb((-0.228, -0.10, -0.022), (-0.152, 0.06, 0.064), 0.010)),          # housing
            (0, cb((-0.205, -0.075, -0.048), (-0.142, 0.035, -0.020), 0.006)),       # mount block down to the holder
            (0, cb((-0.158, -0.06, -0.040), (-0.118, 0.02, -0.024), 0.004)),         # clamp onto the holder's side
            (1, _tube_y(cx, cz, 0.030, 0.019, -0.132, -0.100, cap1=False)),          # rubber eyecup ring, end-on to the eye
            (2, _tube_y(cx, cz, 0.019, 0.0, -0.110, -0.106, cap0=True, cap1=False)), # eyepiece glass, set back in the cup
            (0, _tube_y(cx, cz, 0.034, 0.029, 0.060, 0.102, cap1=True)),             # front hood
            (2, _tube_y(cx, cz, 0.029, 0.0, 0.068, 0.071, cap0=False, cap1=True)),   # front lens, deep in the hood
            (0, _knob_z(X(-0.205), -0.035, 0.011, 0.064, 0.080)),                    # the knob on top
            (3, cb((-0.166, -0.1015, 0.047), (-0.158, -0.0995, 0.055), 0.001)),      # status light on the back face
            (0, cb((-0.234, -0.07, 0.000), (-0.228, 0.03, 0.040), 0.002))]           # battery lid on the outer side


def _knob_x(cy, cz, r, x0, x1, n=10):
    """a short knob along x (the windage turret on the right side)"""
    import numpy as np
    pts = [(x, cy + r * np.cos(2 * np.pi * k / n), cz + r * np.sin(2 * np.pi * k / n)) for k in range(n) for x in (x0, x1)]
    return _hull(pts, uvs=0.03)


def _disk_y(cx, cz, r, y, front=True, n=16):
    """a flat disk facing +y (front) or -y, uv = the whole texture (the M2HB's muzzle texture 0 = a dark ring: the lens glass)"""
    import numpy as np
    V, N, U, T = [(cx, y, cz)], [(0, 1 if front else -1, 0)], [(0.5, 0.5)], []
    for k in range(n + 1):
        a = 2 * np.pi * k / n
        V.append((cx + r * np.cos(a), y, cz + r * np.sin(a))); N.append(N[0]); U.append((0.5 + 0.5 * np.cos(a), 0.5 + 0.5 * np.sin(a)))
    for k in range(n):
        T += [(0, k + 1, k + 2), (0, k + 2, k + 1)]
    return np.array(V) * 4096.0, np.array(N, float), np.array(U), np.array(T)


# (owner 11-13, sight v2) the optic ON TOP of the gun, centred over the receiver. The M2HB weapon model can't be replaced per mission (COMMON's 112_01_1
# wins over a bank copy, outside run sv2s), so the scope rides our holder ss_m2hold_1, which turns with the gun but never tilts. Holder frame = the gun at
# pitch 0: pivot at the origin, +y barrel, z up. Two rules, checked by work/sandstorm/scopecheck.py over the gun's whole pitch range (+15 .. -40 deg):
# the swinging M2HB never touches it (in front of the pivot the gun stays under z 0.18; the grips rise to 0.41 behind it), and from the gunner's eye
# (0, -0.45, 0.2, turning with the barrel) nothing enters the X2.5 window (0.4 rad: about 10 deg each side, 5.4 up/down) - the exe can't hide the gun.
# Hence: the scope forward over the receiver front, axis z 0.42, on a crossbar between two posts that stand on the stock shield plate's top corners.
# Material slots: 0 sand paint, 1 rubber, 2 glass, 3 light (own textures, as v1)
SC_Z, SC_Y = 0.490, 0.0                                    # the optic's axis height; its body runs y SC_Y-0.06 .. SC_Y+0.18 (a heavy-weapon thermal sight)
SC_POST = 0.330                                            # posts this far out: the X2.5 window shows +-0.255 m at the post plane (rig sv3m)
def scope_parts():
    cz, y0, px = SC_Z, SC_Y, SC_POST
    return [(0, _chamfer((-0.050, y0 - 0.06, cz - 0.050), (0.050, y0 + 0.18, cz + 0.045), 0.012)),          # the box body
            (0, _tube_y(0.0, cz, 0.050, 0.044, y0 + 0.18, y0 + 0.25, cap0=True, cap1=False)),             # objective hood
            (2, _tube_y(0.0, cz, 0.044, 0.0, y0 + 0.195, y0 + 0.198, cap0=False, cap1=True)),             # front lens deep in the hood
            (0, _tube_y(0.0, cz, 0.030, 0.0, y0 - 0.10, y0 - 0.06, cap0=False, cap1=False)),              # eyepiece
            (1, _tube_y(0.0, cz, 0.036, 0.024, y0 - 0.135, y0 - 0.10, cap1=False)),                       # rubber eyecup, end-on to the gunner
            (2, _tube_y(0.0, cz, 0.024, 0.0, y0 - 0.115, y0 - 0.112, cap0=True, cap1=False)),             # eyepiece glass in the cup
            (0, _knob_z(0.030, y0 + 0.13, 0.014, cz + 0.045, cz + 0.064)),                                # focus knob on top
            (0, _knob_x(y0 + 0.06, cz, 0.016, 0.050, 0.072)),                                             # windage/zoom knob, right
            (0, _chamfer((-0.068, y0 - 0.02, cz - 0.030), (-0.050, y0 + 0.14, cz + 0.030), 0.004)),       # battery box, left
            (3, _chamfer((0.022, y0 - 0.0615, cz + 0.022), (0.032, y0 - 0.0595, cz + 0.032), 0.001)),     # status light on the back face
            (0, _chamfer((-0.010, y0 - 0.01, cz + 0.045), (0.010, y0 + 0.01, cz + 0.078), 0.003)),        # carry handle: rear leg
            (0, _chamfer((-0.010, y0 + 0.11, cz + 0.045), (0.010, y0 + 0.13, cz + 0.078), 0.003)),        # front leg
            (0, _chamfer((-0.012, y0 - 0.015, cz + 0.068), (0.012, y0 + 0.135, cz + 0.082), 0.004)),      # grip bar
            (0, _chamfer((-0.020, 0.125, 0.420), (0.020, 0.175, cz - 0.048), 0.004)),                     # saddle under the body
            (0, _chamfer((-px - 0.012, 0.13, 0.410), (px + 0.012, 0.17, 0.424), 0.004)),                  # crossbar, over the window (rig sv3m: +15 deg shows up to 0.40)
            (0, _chamfer((-px - 0.012, 0.13, -0.080), (-px + 0.012, 0.17, 0.414), 0.003)),                # post, left
            (0, _chamfer((px - 0.012, 0.13, -0.080), (px + 0.012, 0.17, 0.414), 0.003)),                  # post, right
            (0, _chamfer((-px, 0.13, -0.080), (-0.150, 0.17, -0.058), 0.003)),                            # outrigger arm from the shield plate, left
            (0, _chamfer((0.150, 0.13, -0.080), (px, 0.17, -0.058), 0.003))]                              # outrigger arm, right


# (sight v3, orchestrator 11-13) the compact scope straight over the receiver front, no frame: only with the exe that hides the gun's models while the sight
# is up (v14), since it sits on the gunner's eye line. Still on the holder (it can't tilt with the barrel), so it keeps clear of the swinging gun over the
# full +15 .. -40 deg (work/sandstorm/scopecheck.py): in front of the pivot the barrel stays under z 0.21, the receiver's top swings under 0.19 there.
SCC_Z = 0.255                                              # axis height; eyecup at y 0.03, objective hood to y 0.31
def scope_parts_compact():
    cz = SCC_Z
    return [(0, _chamfer((-0.038, 0.10, cz - 0.035), (0.038, 0.26, cz + 0.035), 0.010)),                 # the box body
            (0, _tube_y(0.0, cz, 0.038, 0.033, 0.26, 0.31, cap0=True, cap1=False)),                     # objective hood
            (2, _tube_y(0.0, cz, 0.033, 0.0, 0.272, 0.275, cap0=False, cap1=True)),                     # front lens deep in the hood
            (0, _tube_y(0.0, cz, 0.025, 0.0, 0.06, 0.10, cap0=False, cap1=False)),                      # eyepiece
            (1, _tube_y(0.0, cz, 0.031, 0.021, 0.03, 0.06, cap1=False)),                                # rubber eyecup
            (2, _tube_y(0.0, cz, 0.021, 0.0, 0.045, 0.048, cap0=True, cap1=False)),                     # eyepiece glass in the cup
            (0, _knob_z(0.022, 0.20, 0.012, cz + 0.035, cz + 0.052)),                                   # focus knob on top
            (0, _knob_x(0.15, cz, 0.013, 0.038, 0.056)),                                                # zoom knob, right
            (0, _chamfer((-0.054, 0.12, cz - 0.024), (-0.038, 0.24, cz + 0.024), 0.004)),               # battery box, left
            (3, _chamfer((0.016, 0.0985, cz + 0.016), (0.026, 0.1005, cz + 0.026), 0.001)),             # status light on the back face
            (0, _chamfer((-0.084, 0.150, 0.206), (0.084, 0.190, 0.222), 0.004)),                        # arch top under the body
            (0, _chamfer((-0.084, 0.150, 0.108), (-0.064, 0.190, 0.214), 0.003)),                       # arch leg, left (on the shield plate)
            (0, _chamfer((0.064, 0.150, 0.108), (0.084, 0.190, 0.214), 0.003)),                         # arch leg, right
            (0, _chamfer((-0.092, 0.140, 0.104), (-0.056, 0.200, 0.118), 0.002)),                       # leg feet clamped to the plate
            (0, _chamfer((0.056, 0.140, 0.104), (0.092, 0.200, 0.118), 0.002))]

def _tex_sand():
    """scratched sand paint over dark metal: panel seams, four bolts, chips, grime in the corners (0.08 m a tile)"""
    import numpy as np
    from ssbase import _noise
    n = 128
    rng = np.random.default_rng(97)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    b = 0.56 + 0.10 * _noise(n, n, 91)
    img = np.dstack([b * 0.92, b * 0.80, b * 0.58])
    for _ in range(40):                                    # scratches to bare metal
        x0, y0 = rng.random(2) * n; a = rng.random() * np.pi; L = 4 + rng.random() * 14
        for t in np.linspace(0, L, int(L * 2)):
            xi, yi = int(x0 + t * np.cos(a)) % n, int(y0 + t * np.sin(a)) % n
            img[yi, xi] = (0.40, 0.39, 0.36)
    chip = _noise(n, n, 92, (16, 32, 64)) > 0.83
    img[chip] = (0.22, 0.21, 0.19)
    for e in (0.0, 0.5):                                   # panel seams
        img[np.abs(v - e) < 0.006] *= 0.45
        img[np.abs(u - e) < 0.006] *= 0.45
    for bu in (0.08, 0.42, 0.58, 0.92):                    # bolts
        for bv in (0.08, 0.42, 0.58, 0.92):
            r = np.hypot((u - bu) * n, (v - bv) * n)
            img[r < 2.4] = (0.30, 0.28, 0.24)
            img[(r < 1.2) & (u < bu)] = (0.62, 0.58, 0.50)
    grime = np.clip(1 - np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v)) * 9, 0, 1)
    img *= (1 - 0.35 * grime)[..., None]
    return np.dstack([np.clip(img, 0, 1), np.ones((n, n))])


def _tex_rubber():
    """dark rubber with ribs"""
    import numpy as np
    from ssbase import _noise
    n = 64
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    b = 0.08 + 0.03 * _noise(n, n, 93) + 0.04 * (np.sin(v * np.pi * 10) > 0.6)
    return np.dstack([b, b, b * 0.95, np.ones((n, n))])


def _tex_lens():
    """coated glass: deep blue-black, a soft sky streak, one hot spot"""
    import numpy as np
    n = 64
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    s_ = np.exp(-((u + v - 0.8) / 0.12) ** 2) * 0.35
    g = np.exp(-(((u - 0.32) / 0.07) ** 2 + ((v - 0.30) / 0.07) ** 2)) * 0.8
    return np.dstack([0.03 + s_ * 0.6 + g, 0.05 + s_ * 0.8 + g, 0.09 + s_ + g, np.ones((n, n))])


def _tex_light():
    import numpy as np
    n = 16
    return np.dstack([np.full((n, n), 0.25), np.full((n, n), 1.0), np.full((n, n), 0.35), np.ones((n, n))])


def mg_window():
    """(owner 11-12) the sight window the exe draws full screen: a wide window with rounded corners and a soft dark housing edge, 256 x 256 BGRA (LOOP sprite format 3)"""
    import numpy as np
    n = 256
    v, u = np.mgrid[0:n, 0:n] / (n - 1.0)
    x0, x1, y0, y1, r = 0.07, 0.93, 0.13, 0.87, 0.16          # the window in texture space (stretched over the screen)
    dx = np.maximum(np.maximum(x0 + r - u, u - (x1 - r)), 0) / r
    dy = np.maximum(np.maximum(y0 + r - v, v - (y1 - r)), 0) / r
    d = np.hypot(dx, dy)                                      # 0 in the straight part, 1 at the rounded edge
    inside = (u > x0) & (u < x1) & (v > y0) & (v < y1) & (d < 1.0)
    a = np.where(inside, np.clip((d - 0.72) / 0.28, 0, 1) ** 1.6, 1.0)
    rim = np.where(inside, np.clip(1 - abs(d - 0.97) / 0.05, 0, 1), 0) * 0.25   # a faint lit rim on the housing
    col = np.dstack([0.035 + rim, 0.033 + rim, 0.028 + rim])
    px = np.dstack([col[..., 2], col[..., 1], col[..., 0], a])       # BGRA
    return (np.clip(px, 0, 1) * 255).astype(np.uint8)


def mg_sight(ovl, level='sandstorm'):
    """(owner 11-13, sight v2) ss_m2hold_1 = the stock holder 112_02_1 with the scope on top (posts on its shield plate), on its own textures; the name is
    the exe's gate. The sight window as g11sight.spr, an entry in the mission's models bank, which stays loaded and is read before COMMON (first name wins)"""
    import numpy as np
    import ilff, altex, mtp, wreck, prefab, mefmesh
    pm, pt, pmd = os.path.join(ovl, level + '.mtp'), os.path.join(ovl, 'textures', level + '.res'), os.path.join(ovl, 'models', level + '.res')
    m = mtp.read(pm)
    form, ch, hdr = ilff.read(open(pt, 'rb').read())
    gts = []
    for nm, fn in (('ss_msand', _tex_sand), ('ss_mrub', _tex_rubber), ('ss_mlens', _tex_lens), ('ss_mled', _tex_light)):
        ch.append((b'NAME', ('LOCAL:textures/%s.tex' % nm).encode('latin1') + bytes(1), 4))
        ch.append((b'BODY', wreck.tex_mode2(fn()), 4))
        m['TEXF'].append(nm)
        m['GTT'].append([len(m['TEXF']) - 1, -1])
        gts.append(len(m['GTT']) - 1)
    lv = prefab.Level(os.path.join(prefab.GAME, 'MISSIONS', 'location2', 'LEVEL5'))
    base = []                                              # (the stock holder's six textures, from LEVEL5 when the build pruned the unused 112_02_1)
    for tn in lv.find_vnam('112_02_1').entry('112_02_1')[1]:
        if tn in m['TEXF'] and any(gt_[0] == m['TEXF'].index(tn) for gt_ in m['GTT']):
            base.append(next(i_ for i_, gt_ in enumerate(m['GTT']) if gt_[0] == m['TEXF'].index(tn)))
            continue
        ch.append((b'NAME', ('LOCAL:textures/%s.tex' % tn).encode('latin1') + bytes(1), 4))
        ch.append((b'BODY', lv.find_resource('LOCAL:textures/%s.tex' % tn, 'textures')[1], 4))
        m['TEXF'].append(tn); m['GTT'].append([len(m['TEXF']) - 1, -1]); base.append(len(m['GTT']) - 1)
    r = mefmesh.RigidModel.from_mef(mefmesh.Mef.read(lv.find_resource('LOCAL:models/%s.mef' % lv.find_vnam('112_02_1').entry('112_02_1')[0], 'models')[1]))
    fl = r.groups[3].flags                                 # (0x1900: the holder's big lit plates)
    for sl, (P, N, U, T) in (scope_parts_compact() if MGSIGHT_COMPACT else scope_parts()):   # (v3 compact on the receiver / v2 on the frame)
        r.groups.append(mefmesh.Group(P.astype(np.float32), U.astype(np.float32), T.astype(np.int64), len(base) + sl, flags=fl, nrm=N.astype(np.float32)))
    mform, mch, mhdr = ilff.read(open(pmd, 'rb').read())
    mch.append((b'NAME', b'LOCAL:models/ss_m2hold_1.mef' + bytes(1), 4))
    mch.append((b'BODY', r.to_mef().write(), 4))
    m['MODS'].append('ss_m2hold_1'); m['VNAM'].append('ss_m2hold_1')
    m['INST'].append([len(m['MODS']) - 1, list(base) + gts])
    G = os.path.join(prefab.GAME, 'COMMON')
    G = os.path.join(prefab.GAME, 'COMMON')
    sform, sch, shdr = ilff.read(open(os.path.join(G, 'sprites', 'sprites.res'), 'rb').read())
    bino = next(b for n_, t_, b in ilff.entries(sch) if n_ == 'LOCAL:common/sprites/binoculars.spr')
    spr = bino[:84] + mg_window().tobytes() + bino[84 + 256 * 256 * 4:]
    mch.append((b'NAME', b'LOCAL:common/sprites/g11sight.spr' + bytes(1), 4))
    mch.append((b'BODY', spr, 4))
    # (owner 11-13, G01/G02) no white-hot ramp any more: heat shows the stock yellow-orange (infra_scale2.tex from COMMON), in the sight and the T goggles
    for path, blob in ((pt, ilff.write(form, ch, hdr[1] or 4)), (pmd, ilff.write(mform, mch, mhdr[1] or 4)), (pm, mtp.write(m))):
        tmp = path + '.gn.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    wreck._lod_entry(ovl, '406_68_1', 'ss_m2hold_1', level)
    print('ssgun: sight v2: holder ss_m2hold_1 with the scope on top (%d groups), sight window g11sight.spr, stock heat colours' % len(r.groups))


def place(g):
    """the static room and its props under the hall, the gun and the stair door under the Dynamic root"""
    m, T, nid, HALL, L, v = g['m'], g['T'], g['nid'], g['HALL'], g['L'], g['v']
    import cwheli
    m.import_decls(cwheli._decomp(), ['StationaryGun'])
    m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS the gun room', *V.U(g['_GNMESH'].o), 0.0, 0.0, 0.0, 'ss_gunr_1', 5, False, False))
    for nm, md, x, y, z, yw in PROPS:
        m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS gun room ' + nm, x * M, y * M, (FZ + z) * M, 0.0, 0.0, yw, md, 5, False, False))
    gid = nid()
    up, dn, side, ammo = GUN_LIMITS
    up = MGSIGHT_UP if MGSIGHT_ON and not MGSIGHT_COMPACT else up
    m.add_child(4029, T(gid, 'StationaryGun', 'SS gun room M2HB', GUN[0] * M, GUN[1] * M, GUN[2] * M, 0.0, 0.0, GUN_YAW, 'ss_m2hold_1' if MGSIGHT_ON else '112_02_1', 'WEAPON_ID_M2HB', up, dn, side, ammo))
    d = copy.deepcopy(L[3928]); did = nid()
    d.args[0] = v(did); d.args[2] = v('SS gun room stair door')
    d.args[3] = v((DOOR_X + 0.02) * M); d.args[4] = v((RY1 + WT / 2) * M); d.args[5] = v(FZ * M)
    d.args[11] = v(0.0); d.args[15] = v(False); d.args[16] = v(True); d.args[18] = v(''); d.args[19] = v(''); d.args[20] = v('')
    m.add_child(4029, d)
    # (owner 91, 99) the wooden bar left of the door: E, Jones' right hand shoves it 0.28 m right (press_alarm, 1.5 s), the door shuts, the bar stays across its edge for good. He leaves by the lift
    pad, lock = nid(), nid()
    m.add_child(4029, T(pad, 'GenericTBA', 'SS gun room door bar (use)', WB_USE[0] * M, WB_USE[1] * M, WB_USE[2] * M, 0.0, 0.0, math.pi, 'ss_wbu_1', 'ss_wbu_1', 100.0, 0.0, 0.0, 0.0,
                        0.0, 0, 0, '', '', 0.0, 0.0, 0.0, False, '!GenericTBA_%d.isFinished' % pad, 'press_alarm', 1.5, 'STATUSSCREEN:action_pressbutton.spr', 'tba_searchcab'))
    m.add_child(4029, T(lock, 'EditVariable', 'SS gun room door locked', 0.0, 0.0, 0.0, 0, ('EditVariable_%d.nValue == 0 && LevelFlow_10.nTick > 2 * GAME_FREQUENCY' % lock if 'lockstart' in os.environ.get('SS_DEBUG', '') else 'EditVariable_%d.nValue == 0 && GenericTBA_%d.isFinished' % (lock, pad)), ''))
    m.set(did, 18, 'EditVariable_%d.nValue == 1' % lock)   # (stairs() adds the first team: door.c starts every door shut, E opens it until then)
    m.set(did, 20, 'EditVariable_%d.nValue == 1' % lock)
    zone = nid()                                           # (owner 89) the sandbag nest round the gun: rounds go wide at a man behind the bags, on the gun or crouched at it. AreaActivate sizes = full extents
    m.add_child(4029, T(zone, 'AreaActivate', 'SS Jones in the gun nest', 174.0 * M, GUN[1] * M, (FZ + 0.5) * M, 0.0, 0.0, 0.0, 2.6 * M, 2.6 * M, 2.4 * M, 'CRITERIA_HUMAN0'))
    # (owner 117) Jones ON the gun, at any yaw, and never on foot: no script reads the gun's user, so two boxes. CRITERIA_CAMERA counts the eye: on the gun it sits 0.45 m behind the pivot (probe th10)
    # and turns with the gun; his body counts 1.05 m behind it (th5, and where E puts him down), outside a 0.70 m square at every yaw. On foot eye and body share a spot, so both are never true
    cam, pin = nid(), nid()
    m.add_child(4029, T(cam, 'AreaActivate', 'SS M2HB eye on the gun', GUN[0] * M, GUN[1] * M, (FZ + 1.6) * M, 0.0, 0.0, 0.0, 2 * CAM_R * M, 2 * CAM_R * M, 1.6 * M, 'CRITERIA_CAMERA'))
    m.add_child(4029, T(pin, 'AreaActivate', 'SS M2HB body at the pivot', GUN[0] * M, GUN[1] * M, (FZ + 0.8) * M, 0.0, 0.0, 0.0, 2 * PIN_R * M, 2 * PIN_R * M, 3.0 * M, 'CRITERIA_HUMAN0'))
    g['GUNROOM_MOUNTED'] = 'AreaActivate_%d.nActive == 1 && AreaActivate_%d.nActive == 0' % (cam, pin)
    g['CLOSED_FOR_AI'] = g['CLOSED_FOR_AI'] + (did,)       # (owner 91: a walking soldier follows the graph link, not the door: gx, gz2 men came through with the lock on. No link here, the room is its own island)
    g['GUNROOM_GUN'], g['GUNROOM_DOOR'], g['GUNROOM_LOCK'], g['GUNROOM_PAD'], g['GUNROOM_ZONE'] = gid, did, lock, pad, zone
    print('ssgun: M2HB %d at %s, stair door %d, lock pad %d, on-the-gun zone %d' % (gid, tuple(round(c, 2) for c in GUN), did, pad, zone))


def stairs(g):
    """(owner 91) the door has no link in the army's graph, so the army never comes through it (gh24: 310 s untouched; gx: with a link they walked through a shut door). The room is graph ROOM_G, its own, and what the lock stops is this:
    while the door is not locked men come up the stairs in twos, the door opens for them, behind Jones (the engine's Human list is 128, this leaves it at 127: more men = fatal QTaskList is full at load).
    Each team is latched in an EditVariable: a ConditionalContainer whose rule goes false removes its men, bodies too. A team only comes while Jones is in the nest; WAVES = seconds after he first stepped in"""
    m, T, nid, LOGIC, alarmai = g['m'], g['T'], g['nid'], g['LOGIC'], g['alarmai']
    tm = nid()
    zone, lock, did = g['GUNROOM_ZONE'], g['GUNROOM_LOCK'], g['GUNROOM_DOOR']
    m.add_child(LOGIC, T(tm, 'LevelTimer', 'SS stair team clock', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'AreaActivate_%d.nActive == 1 || LevelTimer_%d.nTick > 0' % (zone, tm), '', False))
    g['GUNROOM_WAVE_T'] = tm
    if 'noenemies' in g['DBG'] or 'noai' in g['DBG']:
        return
    paths, st, first = {}, m.rng.getstate(), None          # (the same walks for every team; the picks after this stay what they were)
    def walk(x, y):
        if (x, y) not in paths:
            n0 = min(g['GRAPHS'][ROOM_G], key=lambda q: math.dist(q['pos'][:3], (x * M, y * M, FZ * M)))['pos']   # (patrol_route wants a start ON a node, within 50 units)
            paths[x, y] = next(filter(None, (g['K'].patrol_route(ROOM_G, n0, route_m=r) for r in ((5.0, 14.0), (3.0, 16.0), (2.0, 20.0)))), None)
        assert paths[x, y], (x, y)
        ver, body = alarmai.decompile_ai(bytes(g['_aiscript'].patrol(paths[x, y], g['_aiscript'].NORMAL)))
        __import__('diffscale')._find_create(body).then.insert(0, alarmai.C('AIFunction_SetMinRangeAccuracy', STAIR_ACC))   # (hk: at the default 70 two men took Jones from 100 to 0 in 2 s, no time to turn)
        return alarmai.compile_ai(body, ver)
    _rn = lambda x_, y_, skip=(): min((q for q in g['GRAPHS'][ROOM_G] if q['id'] not in skip), key=lambda q: math.hypot(q['pos'][0] - x_ * M, q['pos'][1] - y_ * M))['id']
    FIGHT = [_rn(172.5, 229.0)]; FIGHT.append(_rn(172.5, 229.0, skip=FIGHT))   # (the two nodes nearest the room's middle, the mount in view)
    LOOK_N = _rn(*MOUNT)
    for k, at in enumerate(WAVES):
        cc, v = nid(), nid()
        first = first or v
        m.add_child(LOGIC, T(v, 'EditVariable', 'SS stair team %d is coming' % (k + 1), 0.0, 0.0, 0.0, 0,
                             'EditVariable_%d.nValue == 0 && LevelTimer_%d.nTick > %d * GAME_FREQUENCY && EditVariable_%d.nValue == 0 && AreaActivate_%d.nActive == 1' % (v, tm, at, lock, zone), ''))
        m.add_child(LOGIC, T(cc, 'ConditionalContainer', 'SS stair team %d' % (k + 1), 'EditVariable_%d.nValue == 1' % v, '', ''))
        cnt = g['arrive_counter'](cc, 'stair team %d' % (k + 1))
        mem = []
        for j, (x, y, w) in enumerate(((173.9, 234.2, g['AK']), (173.5, 233.7, g['MG']))):
            walk(x, y)                                     # (a man left idle stood at the door: hc, Jones 75 % at 5 min. A short walk through the room finds him: his 'after' phase)
            # (S16-class, ss-life 11-15: they used to stand 3 s sweeping at the door, then stroll the loop. R-ARRIVE: in through the door to a node by the
            #  room's middle, turned to the gun mount, weapon up; after 8 s the walk through the room as before. STAIR_ACC kept)
            mem.append(dict(pos=(x * M, y * M, FZ * M), model=g['CSFM'][(k + j) % len(g['CSFM'])], weapons=w, ai_type=g['C3T'], graph=ROOM_G, gamma=math.pi,
                            ai=g['arrive_ai'](cnt, FIGHT[j], LOOK_N, after=[alarmai.C('AIAction_Patrol', paths[x, y], 1, 0)], acc=STAIR_ACC)))
        key = 'Stair team %d' % (k + 1)                     # (not 'U ...': they keep their aim and hearing, the nest does not cover its back. Defensive: alarmai.Hunt takes Offensive squads only, its buttons are on another graph = 0xfabc3)
        g['SQUAD_IDS'][key] = m.squad(cc, key, 'AIType_Defensive', mem, alarm_switch=-1, alarm_control=-1)
        g['ENEMY_COUNT'][0] += len(mem)
    m.rng.setstate(st)
    m.set(did, 18, 'EditVariable_%d.nValue == 1 || EditVariable_%d.nValue == 1' % (lock, first))   # (a plain door for Jones until the first team or the lock. door.c: the open rule only runs on a locked door, the close rule only on an open one)
    m.set(did, 19, 'EditVariable_%d.nValue == 1 && EditVariable_%d.nValue == 0' % (first, lock))


def _crew_look(g, k):
    """(fix1120 L8) the ROOM_G node that best lies on the line from crew man k through his mate (within 30 deg of it, 1-8 m out): he looks at the mate"""
    nodes = g.get('GRAPHS', {}).get(ROOM_G) or []
    x, y = CREW[k][0], CREW[k][1]
    mx, my = CREW[1 - k][0], CREW[1 - k][1]
    want = math.atan2(my - y, mx - x)
    best = None
    for q in nodes:
        dx, dy = q['pos'][0] / M - x, q['pos'][1] / M - y
        d = math.hypot(dx, dy)
        if not 1.0 <= d <= 8.0:
            continue
        off = abs((math.atan2(dy, dx) - want + math.pi) % (2 * math.pi) - math.pi)
        if off <= math.radians(30.0) and (best is None or off < best[0]):
            best = (off, q['id'])
    print('fix1120 L8: gun room crew %d looks at node %s (off %.0f deg)' % (k, best and best[1], math.degrees(best[0]) if best else -1))
    return best[1] if best else None


def crew(g):
    """two men in the room who talk until the alert; the owner's garrison rules (rifles low, ua = the hall's calm variable)"""
    stairs(g)
    m, alarmai, Call, Str = g['m'], g['alarmai'], g['Call'], g['Str']
    if 'nocrew' in g['DBG']:                               # (test: Jones starts in the room)
        return
    C = alarmai.C
    ua = g['_UA']
    mem = []
    for k, (x, y, gam, clip) in enumerate(CREW):
        ev = C('AIFunction_GetCurrentEventType')
        calm = [Call('AIFunction_SetStandActionAnimation', [Str(clip)]), C('AIAction_PlayAnimation', 1, 0)]
        look_ = _crew_look(g, k)                            # (fix1120 L8 owner pic 25/26: the spawn gamma alone did not hold, both men faced the lift. As talk_pair: LookAtNode the mate, then the talk clip)
        if look_ is not None:
            calm = [C('AIAction_LookAtNode', look_, 1)] + calm
        sc = alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), [C('AIFunction_DefaultHandler')],
                                            [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                        [alarmai.If(alarmai.EQ(ua, 1), [C('AIAction_Idle', 'AIACTIONFLAG_NONE')], calm), C('AIFunction_PassEventOnToSquad')],
                                                        [C('AIFunction_DefaultHandler')])])])
        mem.append(dict(pos=(x * M, y * M, FZ * M), model=g['CSFM'][k % len(g['CSFM'])], weapons=g['AK'], ai_type=g['C3N'], graph=ROOM_G, ai=sc, gamma=gam))
    sid, hids = m.squad(g['SQ_PARENT'], 'U gun room crew', 'AIType_Defensive', mem, alarm_switch=-1, alarm_control=-1)
    g['SQUAD_IDS']['U gun room crew'] = (sid, hids)
    g['ENEMY_COUNT'][0] += len(hids)


def gun_ai(alarmai, body, zone, hear):
    """(owner 89: 100 men killed Jones on the gun in 5-20 s) a soldier's first statement on every event: while Jones is on the gun his rounds go wide and he throws no grenades,
    off the gun he is the man he was. (tools/diffscale.py skips an If on an AreaActivate when it reads a script's own accuracy)
    Hearing 0.02 on the gun, the crash igi2.exe+0x16bbf4 (gh1-gh3): every round the M2HB fires queues an event in every man who hears it, 32 events x 2 task references x 116 men, and the
    engine's 8064 references are 5742 used before a shot is fired: the pool ran empty after 55 s of fire. The fight does not need the noise, they can see the muzzle"""
    from igiqvm import Call, Flt
    C, If, E, EQ = alarmai.C, alarmai.If, alarmai.E, alarmai.EQ
    hr = lambda f: Call('AIFunction_SetHearingRangeFactor', [Flt(f)])
    acc = lambda mn, med, mx, gr: [C('AIFunction_SetMinRangeAccuracy', mn), C('AIFunction_SetMedRangeAccuracy', med), C('AIFunction_SetMaxRangeAccuracy', mx), C('AIFunction_SetGrenadeThrowProb', gr), hr(GUN_HEAR if mx == GUN_ACC[2] else hear)]
    d = C('Config_GetActiveDifficultyLevel')
    off = [If(EQ(d, 0), acc(36, 20, 3, 50), [If(EQ(d, 2), acc(90, 20, 10, 50), acc(65, 20, MAX_RANGE_ACC, 50))])]
    body.insert(0, If(E('AreaActivate_%d.nActive' % zone), acc(*GUN_ACC, 0), off))


def gun_ai_first(alarmai, body, zone):
    """(RQ8 / N-e5 ss-look 11-16: enemy hand grenades burst 2-6 m from Jones on the M2 = the cream flashes over the sight) gun_ai's rule went first,
    then alarmai's soldier wrapper (HUNT.build) put 'if ENEMYDETECTION { CallForBackup; DefaultHandler } else {..}' in front of it, so the
    detection event never reached it and the engine threw with the value of an older event; the truck troops (built later) never had it.
    Called in the LAST AI pass: the rule is made the first statement again (a copy of the man's own nested rule, or for a man without one
    the grenade part alone). Returns 'kept' | 'copied' | 'added'"""
    import copy
    key = 'AreaActivate_%d.nActive' % zone

    def is_rule(st):
        if not isinstance(st, alarmai.If):
            return False
        t = alarmai.to_text([st])
        return key in t.splitlines()[0] and 'SetGrenadeThrowProb' in t

    if body and is_rule(body[0]):
        return 'kept'
    todo = list(body)
    while todo:
        st = todo.pop(0)
        if is_rule(st):
            body.insert(0, copy.deepcopy(st))
            return 'copied'
        if isinstance(st, alarmai.If):
            todo += st.then + (st.els or [])
    body.insert(0, alarmai.If(alarmai.E(key), [alarmai.C('AIFunction_SetGrenadeThrowProb', 0)], [alarmai.C('AIFunction_SetGrenadeThrowProb', 50)]))
    return 'added'


def screen_props(g):
    """(S14 decision 91, 11-17; fix1120 L12 hand port of main 26fb84e) the lobby barricade: two rows of the stock 2 m sandbag straight (360_05_1,
    already in the bank: no LOD slot) in front of the lift doorway on the hall side, a 1.4 m passage between it and the wall. The bags are the look,
    SCREEN_BOX in the room mesh (room()) is the collision that stops rounds and eyes. Called AFTER the builder's last nid(). Returns the new task ids"""
    m, T, nid, HALL = g['m'], g['T'], g['nid'], g['HALL']
    out = []
    for r in range(SCREEN_ROWS):
        for k in range(SCREEN_N):
            i = nid()
            m.add_child(HALL, T(i, 'EditRigidObj', 'SS lobby barricade bags %d-%d' % (r, k), SCREEN_X * M, (SCREEN_Y0 + SCREEN_STEP * k) * M,
                                (F + SCREEN_ROW_H * r) * M, 0.0, 0.0, math.pi / 2 + (0.0 if r == 0 else math.pi), GR.SB_STRAIGHT, 5, False, False))
            out.append(i)
    return out


def screen_blocked(x_u, y_u, pad=0.45):
    """(S14) graph 6: a point (units) on the barricade's footprint + pad m (navgen drops nodes there and links through it)"""
    x0, y0, _, x1, y1, _ = SCREEN_BOX
    x, y = x_u / M, y_u / M
    return x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad


def late(g):
    """messages, once msg() exists"""
    if 'killmsg' in os.environ.get('SS_DEBUG', ''):          # (test: is the nest zone on?)
        g['msg']('SS_GN_ZONE', 'zone test', 'AreaActivate_%d.nActive == 1' % g['GUNROOM_ZONE'], 'ZONE ON', 8.0)
    g['msg']('SS_GN_OPEN', 'Stair door hint', 'AreaActivate_%d.nActive == 1 && EditVariable_%d.nValue == 0' % (g['GUNROOM_ZONE'], g['GUNROOM_LOCK']), 'That stair door is not barred. Slide the wooden bar beside it across.', 6.0)
    g['msg']('SS_GN_STAIRS', 'Stair team warning', 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY && EditVariable_%d.nValue == 0' % (g['GUNROOM_WAVE_T'], WAVES[0] - 10, g['GUNROOM_LOCK']), 'SOLDIER: The stairs! Get up the stairs, take him from behind!', 5.0)
    if 'GUNROOM_MOUNTED' in g:                             # (owner 98: the exe zooms the mounted gun on the scoped rifles' keys)
        g['msg']('SS_GN_ZOOM', 'Gun zoom hint', g['GUNROOM_MOUNTED'], 'Zoom the gun: H in, N out (or the mouse wheel).', 5.0)
    if 'SIGHT_DBG' in g:                                   # (test: is the thermal rule true?)
        g['msg']('SS_GN_SDBG', 'sight debug', g['SIGHT_DBG'], 'THERMAL RULE TRUE', 20.0)
        g['msg']('SS_GN_SDBG2', 'sight debug 2', g['GUNROOM_MOUNTED'], 'MOUNT BOX ON', 20.0)
        g['msg']('SS_GN_SDBG3', 'sight debug 3', 'GenericPickup_%d.isPickedUp' % g['GUNROOM_SIGHT'], 'SIGHT TAKEN', 20.0)
    if 'GUNROOM_SIGHT' in g:
        g['msg']('SS_GN_SIGHT', 'Thermal sight taken', 'GenericPickup_%d.isPickedUp' % g['GUNROOM_SIGHT'], 'Thermal sight. Fit it to the M2HB: on the gun you see their heat.', 5.0)
    g['msg']('SS_GN_LOCK', 'Stair door barred', 'EditVariable_%d.nValue == 1' % g['GUNROOM_LOCK'], 'Stair door sealed. Nobody comes up behind you.', 5.0)


def killmsg(g):
    """test only (variant killmsg): a line on screen when a man of the hall dies, the proof of kills through the window"""
    k = 0
    for key, (sid, hids) in g['SQUAD_IDS'].items():
        if key.startswith('U ') and key not in ('U machine room', 'U tunnel post', 'U tunnel rockets', 'U scientists'):
            for h in hids:
                g['msg']('SS_DBG_K%d' % k, 'DEBUG dead %d' % k, 'HumanSoldier_%d.isDead' % h, 'DEBUG DEAD %s %d' % (key[2:], h), 6.0)
                k += 1
    print('ssgun: %d kill lines' % k)


def sight_model():
    """(owner 97) a gun sight lying on the table: a 26 cm tube on a mount, the lens end dark"""
    me = Mesh((0, 0, 0), ['ss_stl', 'ss_hz'])
    me.box('ss_stl', -0.13, -0.025, 0.03, 0.13, 0.025, 0.08, uv=0.3)
    me.box('ss_hz', 0.13, -0.03, 0.025, 0.145, 0.03, 0.085, uv=0.3)
    me.box('ss_stl', -0.06, -0.02, 0.0, 0.06, 0.02, 0.03, uv=0.3)
    return me.model(even=['ss_stl', 'ss_hz'])


def sight(g):
    """(owner 97) take the sight from the table; from then on, while Jones is on the gun, the engine draws heat: an OverlayHolder whose infrared expression
    sets the thermal goggles' flag (igi2.exe 0x546490; L32 task 2945). OVERLAY_ZOOM draws no frame. On the gun is a tight box at the mount spot. The T goggles cannot do it: mounting puts Jones in Lock, which reads no binocular key"""
    import atmos
    m, T, nid, LOGIC = g['m'], g['T'], g['nid'], g['LOGIC']
    atmos.ensure_decl(m, 'GenericPickup')                 # (as Kit.item does; this build's Kit has no PICK)
    pid = nid()
    sp = (GUN[0] - 1.25, GUN[1], 0.05) if 'sightnear' in g['DBG'] else SIGHT   # (test: the sight under Jones' feet at the atgun start, picked up as he spawns)
    m.add_child(g['PICK'], T(pid, 'GenericPickup', 'SS thermal sight for the M2HB', sp[0] * M, sp[1] * M, (FZ + sp[2]) * M, 0.0, 0.0, 0.4, 'ss_tsight_1'))
    on = g['GUNROOM_MOUNTED']                             # (a rule, not a box: owner 117)
    atmos.ensure_decl(m, 'OverlayHolder')
    cond = 'GenericPickup_%d.isPickedUp && %s' % (pid, on)
    if 'sightall' in g['DBG']:                             # (test: heat from the pick-up on, wherever he is: does the holder draw heat at all?)
        cond = 'GenericPickup_%d.isPickedUp' % pid
    if 'sightprobe' in g['DBG']:                           # (test: six boxes along the gun's axis, each shows a sandbag pile at its own height in the hall: which is on only while mounted?)
        import atmos as _a
        _a.ensure_decl(m, 'ConditionalContainer')
        for k_, x_ in enumerate((173.95, 174.1, 174.25, 174.4, 174.55, 174.7)):   # (owner 117: CRITERIA_CAMERA boxes along the gun's axis at eye height: where is the camera on the gun and on foot?)
            zp = nid()
            m.add_child(4029, T(zp, 'AreaActivate', 'SS sight probe %d' % k_, x_ * M, GUN[1] * M, (FZ + 1.6) * M, 0.0, 0.0, 0.0, 0.15 * M, 0.6 * M, 1.6 * M, 'CRITERIA_CAMERA'))
            m.add_child(LOGIC, T(nid(), 'ConditionalContainer', 'SS sight probe show %d' % k_, 'AreaActivate_%d.nActive == 1' % zp, '', '',
                                 children=[T(nid(), 'EditRigidObj', 'SS sight probe bags %d' % k_, 179.0 * M, (GUN[1] + 2.6 - 1.04 * k_) * M, (FZ + 1.6 + 0.0 * k_) * M, 0.0, 0.0, 1.5708, '360_05_1', 5, False, False)]))
    if 'sightdbg' in g['DBG']:                             # (test: sandbags appear left of the barrel while the mounted box is on, right of it while the nest box is on)
        import atmos as _a
        _a.ensure_decl(m, 'ConditionalContainer')
        for k_, (zr_, dy) in enumerate(((on, 1.4), ('AreaActivate_%d.nActive == 1' % g['GUNROOM_ZONE'], -1.4))):
            m.add_child(LOGIC, T(nid(), 'ConditionalContainer', 'SS sight debug %d' % k_, zr_, '', '',
                                 children=[T(nid(), 'EditRigidObj', 'SS sight debug bags %d' % k_, 178.5 * M, (GUN[1] + dy) * M, (FZ + 0.6) * M, 0.0, 0.0, 1.5708, '360_05_1', 5, False, False)]))
    ov = 'OVERLAY_SNIPER' if 'ovsniper' in g['DBG'] else 'OVERLAY_ZOOM'   # (test: a type that draws a frame, to see the holder is on)
    m.add_child(LOGIC, T(nid(), 'OverlayHolder', 'SS M2HB thermal sight', cond, cond, g['Ident'](ov), 'ovsniper' in g['DBG']))
    if 'sightdbg' in g['DBG']:
        g['SIGHT_DBG'] = cond
    g['GUNROOM_SIGHT'] = pid
    print('ssgun: thermal sight %d on the table, mounted rule %s' % (pid, on))


def loot(g):
    m, T, nid, PICK = g['m'], g['T'], g['nid'], g['PICK']
    if SIGHT_ON:
        sight(g)
    for nm, wid, x, y, z in LOOT:
        m.add_child(PICK, T(nid(), 'GunPickup', 'SS gun room ' + nm, x * M, y * M, (FZ + z) * M + 120.0, 1.570796, 0.0, 0.0, wid, ''))
