"""Operation Sandstorm - a single-player mission on the multiplayer map 'Sandstorm'.

A map the campaign never uses: a Libyan desert airbase in two compounds joined by a sewer. Jones lands in a
sandstorm at dusk, kills the power in the southern compound, goes underground through the sewer, steals the
Hind flight plans, destroys both gunships and the fuel depot in the northern airbase and escapes through the
north tunnel.

Multiplayer maps ship no AI graphs: tools/navgen.py generates them from the terrain heightmap and the
building collision meshes (verified against the multiplayer spawn points).

  python build_sandstorm.py              -> build/sandstorm/
  SS_DEBUG=die|win|alarm|noai|objectives|start=x,y,z[,gamma]|face=<task id>|rpg (';'-separated)
                                          -> build/sandstorm_TEST/ (test-only, never ship)
"""
import os, sys, math, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
import numpy as np
import igiqvm
from igiqvm import Call, Int, Str, Ident
from mission_lib import Mission, T, v
from qast import lit, tasks
import navgen
import cutscene as CS
import terrain as terrain_mod
import voice
import soundbank as sb

MISSION_ID = 19
FOLDER = 'sandstorm_sp'
DEBUG = os.environ.get('SS_DEBUG', '')
DBG = set(p.split('=')[0] for p in DEBUG.split(';') if p)
L1 = os.path.join(HERE, 'work', 'decomp', 'location1_level1_objects.qsc')
G_ = r'C:/Users/1qdeath/Games/IGI2/app/'

m = Mission('multiplayer', 'sandstorm', 'sandstorm', seed=1919)
L = m.byid
def nid():                                         # free id ranges in this map (900-999 skipped by new_id)
    try:
        return m.new_id(1602, 2753)
    except RuntimeError:
        try:
            return m.new_id(402, 899)
        except RuntimeError:                       # (the full army and the rooms fill both ranges: any other free id, then the ids of removed tasks)
            try:
                return m.new_id(20, 4096)
            except RuntimeError:
                return m.reuse_id()

# =========================================================== 0. strip the multiplayer game logic
for i in (3887, 2785):                                    # Network_Mission (+objectives, spawn areas), play-area warnings
    m.remove(i)
for i in m.find('C4BombArea') + m.find('AIStationaryGunHolder'):
    m.remove(i)
for i in [i for i in m.find('SequenceCommand') if 'NetObjective_' in str(lit(L[i].args[4]))]:
    m.remove(i)
for i in m.find('DefineComputerObjective') + [i for i in m.find('ComputerHilight') if 'NetMission_' in str(lit(L[i].args[6]))]:
    m.remove(i)
for i in (1102, 3208, 1100):                              # MP objective variables, "security offline" MP message
    m.remove(i)
TERMINALS = {i: [lit(a) for a in L[i].args[3:9]] for i in m.find('Terminal')}   # positions reused for SP computers
for i in m.find('Terminal'):
    m.remove(i)
# SHOBI 10-29 ambience (kept 10-31): the MP jet fly-bys (the storm grounded everything) and the rotor loops of the parked Hinds go
for i in (3763, 3761, 3757):
    m.remove(i)
# owner 10-31 'too many cars': the MP map parks 13 trucks (3 in each storage house / garage row). Keep one per spot
# like the originals' bases (L24 airfield: a truck or two per yard): 13 -> 8. Removed before navgen (graph sees the gap).
for i in (3090, 3088, 3200, 3198, 4070):
    m.remove(i)
# r9 walk gate 11-02: the EMP bunker's courtyard (the MP map's north entrance pocket) was closed on every side - cliffs, the Large
# house, and this diagonal compound wall (2 stacked 300_06_1 pieces). Removed: the courtyard opens onto the Hind pad (before navgen)
for i in (3777, 3778):
    assert str(lit(L[i].args[9])) == '300_06_1', i
    m.remove(i)
added = m.import_decls(L1)

# doors: the MP map opens/locks them per multiplayer objective -> single-player rules
COVERAI = os.environ.get('SS_COVERAI', '0') == '1'       # (N8 ss-life 11-15: squads that have Jones fight from where they are (HoldArea) instead of being re-sent into his cell; A/B take first)
LIFTG = os.environ.get('SS_LIFTG', '0') == '1'           # (off-node men, ss-life 11-17: graph 7's box began at x 164, the top lift landing (x 159-161) where the two lift
                                                          #  sentries 1211 / 1213 stand fell outside it: 9.2 / 7.6 m to the nearest node (islands, ssb3), alerted they walk straight at the cab corner. Box x0 158 = 11 landing
                                                          #  nodes (navcache 11-14), guards 0.9 / 1.4 m off a node, none in the cab. Default OFF until orch-2's word (no build yet))
TRKARR = os.environ.get('SS_TRKARR', '0') == '1'         # (N6 ss-life 11-17: the tailgate men and the riders swap on a TIMER (planned arrival + 1 s) at spots behind the PLANNED stop;
                                                          #  a hit halts the truck short of it (halt_guides), so in the hit shot two men popped up beside Jones's body with no truck there
                                                          #  (REVIEW_intro_mid_rc7s24 #11, 90.30 s). Flag: they swap only once the truck is at its last node, as the driver already does.
                                                          #  Condition strings only: no task id, no rng draw. Default OFF until orch-2's word (no build yet))
DEADHOLD = os.environ.get('SS_DEADHOLD', '0') == '1'     # (N15 ss-life 11-17: after Jones dies the hunt kept sending squads to the two nodes of the zone that holds his body every
                                                          #  14 s: men walked to and fro across it under the death camera (ss_full2 9:20). Flag: every hunting squad holds its area
                                                          #  once he is dead (alarmai dead_hold). No task id, no rng draw; HumanPlayer_0.isDead read in a squad script is new: A/B take first)
RQ7 = os.environ.get('SS_RQ7', '1') == '1'               # (RQ7 / N9 ss-life 11-16: the engine KILLS a man ordered to a node he cannot path to (humanai.c 10963-10972, 0.4 + 1.0 = the logged 1.4).
LOBBY_G = 13                                              #  ssloot.cut_graph split graph 1 into islands (lobby 21 + armoury 13 nodes) after the hunt was built on it. Now: the armoury leaves are
                                                          #  closed at navgen (no door nodes, no links), the large-house lobby gets its own AIGraph LOBBY_G (the armoury's nodes left out),
                                                          #  every graph is one island, and tools/islands.py on the output = 0 orders to another island (build gate))
DOOR_RULES = {
    3891: ('1', '0'), 3890: ('1', '0'),                   # west gate of the airbase: welded shut
    3148: ('1', None), 3147: ('1', None),                 # north escape tunnel: opened by the mission (below)
    3928: ('', ''), 3659: ('', ''),                       # sewer doors at the landing zone: open normally (player shortcut)
    3927: (None, ''),                                     # sewer door in the south compound: power lock (below)
    3658: ('', ''),                                       # sewer exit inside the airbase
    3070: ('', ''), 3069: ('', ''),                       # tunnel building in the south compound
    3079: ('', None), 3080: ('', None), 3668: ('', None), 3669: ('', None),   # (A9 ss-life 11-16: the MP map's own lock '1' + pick, never set by us. Closed for the AI they cut
}                                                         #  'S storage house' off graph 1 (life_6: 0 nodes for its squad); with door nodes the men opened them anyway: plain doors now
for d in (3079, 3080, 3668, 3669):
    m.set(d, 15, False)                                   # (not lock-pickable: there is no lock)
for d, (lock, opn) in DOOR_RULES.items():
    if lock is not None:
        m.set(d, 18, lock)
    if opn is not None:
        m.set(d, 19, opn)
m.set(3664, 15, True); m.set(3664, 17, 12); m.set(3664, 18, '!Door_3664.isPicked')   # (owner 11-04: shut; a long hold of E cracks it, the men inside hear nothing)
m.set(3664, 13, -90.0)                                    # (v4 walk gate: the server-basement door swings INTO the room - opened toward
                                                          #  the corridor its leaf closed the corridor off)
for d in (3891, 3890, 3148, 3147):
    m.set(d, 15, False)                                   # not lock-pickable
CLOSED_FOR_AI = (400, 401, 3891, 3890, 3148, 3147, 3928, 3659, 3927)
for _id, _bad, _good in ((400, 'door_blast_clos', 'door_blast_cl'), (401, 'door_blast_clos', 'door_blast_cl'), (3893, 'explo_02_l', 'explo_03_l')):   # (judge P16 sound A9/A10: names with no def = silent)
    _hits = [i_ for i_, a_ in enumerate(m.byid[_id].args) if str(lit(a_)) == _bad] if _id in m.byid else []
    for i_ in _hits:
        m.set(_id, i_, _good)
    print('P16 sound: task %d %s -> %s (%d slot)' % (_id, _bad, _good, len(_hits)))   # locked / switch-driven / player-only: no AI route
# (3928/3659 open for the player but stay out of the AI graphs: linking the sewer into graph 1 would push it past 2000 nodes)

# =========================================================== 1. single-player infrastructure
START = (358558.34, -90150.51, 400.0)
START_GAMMA = 0.0                                         # facing north, up the canyon towards the south compound
# owner 11-01: no sniper at the start (a silenced PSG1 made it trivial) - silenced SOCOM sidearm + M16A2, knife, binoculars,
# grenades / flashbangs, medipacks. Better guns are in the base (the snipers' Dragunovs, the Minimi gunners).
LOADOUT = ['Human_AddWeapon("WEAPON_ID_SOCOM")', 'Human_AddWeapon("WEAPON_ID_M16A2")', 'Human_AddWeapon("WEAPON_ID_KNIFE")',
           'Human_AddWeapon("WEAPON_ID_BINOCULARS")', 'Human_AddWeapon("WEAPON_ID_THERMICAL")',   # (11-01: goggles back - T = Thermal)
           'Human_AddWeapon("WEAPON_ID_GRENADE")', 'Human_AddWeapon("WEAPON_ID_FLASHBANG")',
           'Human_AddWeapon("WEAPON_ID_MEDIPACK")',
           'Human_AddAmmoForWeapon("WEAPON_ID_SOCOM",60)', 'Human_AddAmmoForWeapon("WEAPON_ID_M16A2",150)',
           'Human_AddAmmoForWeapon("WEAPON_ID_GRENADE",4)', 'Human_AddAmmoForWeapon("WEAPON_ID_FLASHBANG",2)',
           'Human_AddAmmoForWeapon("WEAPON_ID_MEDIPACK",3)']
PLAYER = T(0, 'HumanPlayer', '', START[0], START[1], START[2], START_GAMMA, 'jones2_1', 0, ',\n'.join(LOADOUT) + ';',
           'arms2_1', 0.8, 0.2, 0.95, False, children=[T(nid(), 'HumanPlayerInput', '', '', '')])
PC = nid()
m.add_child(4087, T(PC, 'Container', 'ThePlayer', False, children=[PLAYER]))
LOGIC = nid()
m.add_child(4087, T(LOGIC, 'Container', 'SS mission logic', False))
DEAD = nid()
m.add_child(LOGIC, T(DEAD, 'StatusMessage', 'Mission Failed Player dead', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                     'HumanPlayer_0.isDead', 'MISSION_FAILED', '', 'statusmessage', True, False, 2.0, ''))

# =========================================================== 2. atmosphere: sandstorm at dusk
gk = L[4090]
for base in (4, 12, 20, 28, 36):                          # terrain + 4 object categories: ambient(3) fog(3) density
    for k, val in enumerate((0.42, 0.33, 0.24, 0.70, 0.52, 0.32, 2.6)):
        gk.args[base + k] = v(val)
for k, val in zip(range(6, 26), [0.70, 0.52, 0.32, False, 8.0, 0.40, 0.30, 0.21, 0.62, 0.47, 0.31,
                                 0.66, 0.50, 0.33, 0.70, 0.53, 0.34, 0.68, 0.51, 0.33]):
    m.set(4094, k, val)                                    # sky fog colour + dusty sky dome
m.set(2978, 8, 0.65); m.set(2978, 9, 0.62); m.set(2978, 10, 0.47)     # dust-coloured clouds
m.set(2978, 5, 0.0003); m.set(2978, 6, 0.0009)             # drifting fast
for k, val in zip(range(5, 11), (0.78, 0.58, 0.38, 0.18, 0.13, 0.09)):
    m.set(4088, k, val)                                    # low orange sun, warm shadows
for k, val in zip(range(3, 8), (0.9, 0.35, 0.8, 0.9, 0.4)):
    m.set(3162, k, val)                                    # strong gusting wind

# =========================================================== 2b. v4 (owner-approved plan v4, 11-03): the SECRET MISSILE BASE UNDER THE
# AIRFIELD (replaces the 11-02 hill bunker). tools/ssv4.py: the L34 'Lab Cave' SHELL buried under the airfield (shell only, its doors
# locked, own red/amber light below), the way down = the shed behind the storage hangar (432_10_1's own mesh, a stair hatch cut into
# its floor) -> tight stairs -> a low corridor -> the machine room under the hill -> the ORIGINAL L12 personnel lift -> the cave.
import prefabs as _prefabs, types as _types, ssv4 as V
import modelkit as _MK, jrmodels as _JM
X = _prefabs.Transplant(_types.SimpleNamespace(m=m, nid=nid))
_TB = terrain_mod.Terrain(m.src, m.stmts)
_bh = lambda x_m, y_m: float(_TB.height(x_m * 4096.0, y_m * 4096.0)) / 4096.0
_CELL = _TB.maps[0][3] / 4096.0                            # (the finest heightmap's cell, m: a hole cuts whole cells)
_ROOTS = [lit(s_.args[0]) for s_ in m.stmts if isinstance(s_, Call) and s_.name == 'Task_New']
BK_ST = next(i for i in _ROOTS if lit(L[i].args[1]) == 'Static')
# the cave: hall A (rel x 23..56, floor -2) <-> hall B (rel x 57..100, floor 0, two 1 m bays) through the fence doors 4070/4071; the
# south cave (rel y -35..-5, floor -1..-3) along both halls; every other L34 door locked (beyond them: the void or L34's rooms)
# the MP map's sewer Water (3716, z -20.2 m) is a global plane for the engine: everything under it swims (rig v4r1: Jones spawned in
# the base floated up to -21.5 m). The sewer channel's 0.26 m puddle goes; the base 30 m lower needs dry air.
m.remove(3716)
# (owner 11-04, the L34 shell was 'the China map': gone. tools/ssbase.py: a NEW hall + truck tunnel, new meshes from the map's own textures)
import ssbase as SB
LIFT_BOTTOM = SB.F
LIFT = V.place_lift(X, m, 4029, LIFT_BOTTOM, '1')          # (owner r3: no generator - the L12 button rule, nothing on top)
# (owner 11-03 r3 'the gate will not open' + the deaths at the cab; rig lift_r3: the exit gate shows no use prompt at the bottom, and an entry gate
#  opened with E shuts by itself ~27 s later and kills Jones) -> both gates run on script only, no E: open while the cab stands at their floor,
#  shut on the call button (which works only with Jones well inside)
if SB.GUNROOM:                                             # (owner 63, tools/ssgun.py: floors 0 top, 1 gun room, 2 bottom; the exit gate serves both lower stops)
    import ssgun as GN
    GN.three_stops(globals())
_still = 'Lift_%d.nCurrentFloor %%s && !Lift_%d.isMoving && EditVariable_%d.nValue == 0' % (LIFT['lift'], LIFT['lift'], LIFT['var'])
for _gid, _fl in ((LIFT['gate_in'], '== 0'), (LIFT['gate_out'], '> 0' if SB.GUNROOM else '== 1')):
    m.set(_gid, 18, '1')
    m.set(_gid, 19, 'Door_%d.isClosed && %s' % (_gid, _still % _fl))
import copy as _copy
# the shed: the map's own (Building 3137) out, its copy with the stair hatch in (vertex-lit EditRigidObj, same mesh + textures)
_shed_yaw = float(lit(L[V.SHED_ID].args[8]))
assert abs(float(lit(L[V.SHED_ID].args[3])) / 4096 - V.SHED[0]) < 0.05 and abs(float(lit(L[V.SHED_ID].args[4])) / 4096 - V.SHED[1]) < 0.05
m.remove(V.SHED_ID)
_c_, _s_ = math.cos(-_shed_yaw), math.sin(-_shed_yaw)
_hl = [(_c_ * (x_ - V.SHED[0]) - _s_ * (y_ - V.SHED[1]), _s_ * (x_ - V.SHED[0]) + _c_ * (y_ - V.SHED[1]))
       for x_ in (V.HATCH[0], V.HATCH[2]) for y_ in (V.HATCH[1], V.HATCH[3])]
SHED_HATCH = (min(p_[0] for p_ in _hl), min(p_[1] for p_ in _hl), max(p_[0] for p_ in _hl), max(p_[1] for p_ in _hl))
SHED_DOOR = (1.0, 2.16)                                    # (the opening in its north wall - toward the north Hind pad; shed y m; owner 11-04: the leaf is 1.15 m, a wider opening showed a lit slit beside it)
_shed_mesh, SHED_SLOTS = V.shed_model(SHED_HATCH, SHED_DOOR), V.SHED_SLOTS
WAY_G, MROOM = V.way_geometry()
SHAFT_G = V.shaft_geometry(LIFT_BOTTOM, GN.FZ if SB.GUNROOM else None)
_VLIB = _MK.Library()
_VLIB.texture('jr_steel', _JM.TEXTURES['jr_steel'])
_VLIB.add('ss_shed_1', lambda: _shed_mesh, SHED_SLOTS, lod_like='406_68_1')
_VLIB.add('ss_way_1', lambda: V.mesh_from_boxes(WAY_G, V.SHED, extra_coll=[V.way_ramp(V.SHED)]), ['ss_shc', 'jr_steel'], lod_like='406_68_1')
_VLIB.texture('jr_dark', _JM.TEXTURES['jr_dark'])
_VLIB.add('ss_shaft_1', lambda: V.mesh_from_boxes(SHAFT_G, (V.LIFT_C[0], V.LIFT_C[1], V.TOP_Z), slots=('c', 's', 'd')), ['ss_shc', 'jr_steel', 'jr_dark'], lod_like='406_68_1')
# (orchestrator 11-05, sp26: a step past the sewer ladder is a free 18 m fall in the south hut: a steel rail round the shaft, the ladder side open)
_SHR_O = (73.1, 131.6, 0.28)
def _shaft_rail():
    x0_, x1_, y0_, y1_, g0_, g1_, z0_, t_ = 71.1, 75.1, 129.5, 133.7, 131.05, 132.15, 0.28, 0.06
    sides_ = [(x0_, y0_, x1_, y0_), (x0_, y1_, x1_, y1_), (x1_, y0_, x1_, y1_), (x0_, y0_, x0_, g0_), (x0_, g1_, x0_, y1_)]
    coll_ = []
    bx_ = V._bx()
    me_ = SB.Mesh(_SHR_O, ['ss_rail', 'ss_stl'])          # (judge R12: 6 cm boxes, every normal up, read as flat orange planks: round painted pipes, real normals, a steel kick plate)
    for a_, b_, c_, d_ in sides_:
        ax_, a0_, a1_ = ('x', a_, c_) if abs(b_ - d_) < 1e-6 else ('y', b_, d_)
        for h_ in (0.55, 1.08):
            me_.cyl('ss_rail', 0.024, a0_, a1_, ax_, (b_, z0_ + h_) if ax_ == 'x' else (a_, z0_ + h_), uv=1.0, seg=8)
        me_.box('ss_stl', min(a_, c_) - 0.004, min(b_, d_) - 0.004, z0_, max(a_, c_) + 0.004, max(b_, d_) + 0.004, z0_ + 0.1, uv=1.0, solid=False)
        coll_.append(bx_(a_ - t_ / 2 - _SHR_O[0], b_ - t_ / 2 - _SHR_O[1], 0.0, c_ + t_ / 2 - _SHR_O[0], d_ + t_ / 2 - _SHR_O[1], 1.15, uv=0.35))
    for px_, py_ in ((x0_, y0_), (x0_, y1_), (x1_, y0_), (x1_, y1_), (x0_, g0_), (x0_, g1_), (x1_, 131.6), (73.1, y0_), (73.1, y1_)):
        me_.g["ss_rail"].append(SB.BP.cyl_z(0.026, 0.0, 1.11, 8, px_ - _SHR_O[0], py_ - _SHR_O[1], 1.0))
    me_.coll = coll_
    return me_.model()
_VLIB.add('ss_shrail_1', _shaft_rail, ['ss_rail', 'ss_stl'], lod_like='406_68_1')
m.add_child(BK_ST, T(nid(), 'EditRigidObj', 'SS rail round the sewer shaft', *[float(c_) * 4096.0 for c_ in _SHR_O], 0.0, 0.0, 0.0, 'ss_shrail_1', 5, False, False))
for _nm, _mdl, _p, _yw in (('SS storeroom shed (432_10_1, stair hatch)', 'ss_shed_1', V.SHED, _shed_yaw),
                           ('SS stairs, corridor and machine room', 'ss_way_1', V.SHED, 0.0),
                           ('SS lift shaft', 'ss_shaft_1', (V.LIFT_C[0], V.LIFT_C[1], V.TOP_Z), 0.0)):
    m.add_child(BK_ST, T(nid(), 'EditRigidObj', _nm, *V.U(_p), 0.0, 0.0, _yw, _mdl, 5, False, False))
# owner 11-03 r3: the machine-room doorway was an open hole - now the ORIGINAL prison cell door (location2/LEVEL2 Door 3761, 500_23_1:
# riveted steel, a window panel), shut and locked: pick the lock (hold E). Hinge at the doorway's west jamb, in the wall's middle
_cd_src = X._source('location2/level2')['byid'][3761][0]
_cd_p = [float(lit(_cd_src.args[3 + k_])) for k_ in range(3)]
CELL_DOOR, _cd_ids = X.place_group('location2/level2', 3761, V.U((V.CELL_DOOR_P[0], V.CELL_DOOR_P[1], V.TOP_Z)), 0.0 - float(lit(_cd_src.args[11])),
                                   4029, pivot=_cd_p, name='SS machine room cell door (locked, pick it)', on_ground=False, strip_rules=False)
m.set(CELL_DOOR, 15, True); m.set(CELL_DOOR, 18, '!Door_%d.isPicked' % CELL_DOOR)
print('v4 cell door %d (500_23_1) in the machine-room doorway' % CELL_DOOR)
# the shed's door: the map's own sewer door 501_04_1 (a copy of 3928), locked - pick the lock (hold E)
import copy as _copy
SHED_DOOR_ID = nid()
_sd = _copy.deepcopy(L[3928]); _sd.args[0] = v(SHED_DOOR_ID); _sd.args[2] = v('SS storeroom shed door (locked, pick it)')
_dl = (2.0 - 0.05, SHED_DOOR[0] + 0.03)                   # hinge on the wall line, the leaf toward +y (shed frame)
_c2, _s2 = math.cos(_shed_yaw), math.sin(_shed_yaw)
_sd.args[3] = v((V.SHED[0] + _c2 * _dl[0] - _s2 * _dl[1]) * 4096.0); _sd.args[4] = v((V.SHED[1] + _s2 * _dl[0] + _c2 * _dl[1]) * 4096.0)
_sd.args[5] = v((V.SHED[2] + 0.08) * 4096.0); _sd.args[11] = v(_shed_yaw + math.pi / 2)
_sd.args[13] = v(-90.0); _sd.args[15] = v(True); _sd.args[18] = v('!Door_%d.isPicked' % SHED_DOOR_ID); _sd.args[19] = v(''); _sd.args[20] = v('')
m.add_child(4029, _sd)
# the base's own layout in the cave (tools/sshall.py; placed BEFORE navgen so the graph walks round them): four launch trucks in
# hall A (the map's own truck 600_00_1, tarp off, a missile on an erector - one raised for checks), the BIG missile upright in hall
# B's first bay (its panels open) with a service gantry beside it
import sshall as SH
_truck = V.orig_mesh('multiplayer/sandstorm', '600_00_1')
for _tn, _fn in _JM.TEXTURES.items():
    if _tn in ('jr_olive', 'jr_misw', 'jr_white'):
        _VLIB.texture(_tn, _fn)
import prefab as _pfb, igitex as _itx
_sslv = _pfb.Level(os.path.join(_pfb.GAME, 'MISSIONS', 'multiplayer', 'sandstorm'))
for _tn in SH.TEL_SLOTS[:8]:                               # (600_00_1's own textures; the glass ones are alpha)
    _VLIB.texture(_tn, (lambda n_: (lambda: _itx.decode(_sslv.find_resource('LOCAL:textures/%s.tex' % n_, 'textures')[1])))(_tn),
                  alpha=_tn.endswith('argb8888'))
_VLIB.add('ss_tel_1', lambda: SH.tel_model(_truck, False), SH.TEL_SLOTS, lod_like='406_68_1')
_VLIB.add('ss_telr_1', lambda: SH.tel_model(_truck, True), SH.TEL_SLOTS, lod_like='406_68_1')
_VLIB.add('ss_bigm_1', SH.bigm_model, SH.BIGM_SLOTS, lod_like='406_68_1')
_VLIB.add('ss_gant_1', SH.gant_model, SH.GANT_SLOTS, lod_like='406_68_1')
HALL = nid()
m.add_child(BK_ST, T(HALL, 'Container', 'SS missile base layout', False))
# --- owner 11-04: the NEW base (tools/ssbase.py): hall, truck tunnel, portal, roll-up gates (all new meshes, the map's own textures)
_sbget = lambda n_: _itx.decode(_sslv.find_resource('LOCAL:textures/%s.tex' % n_, 'textures')[1])
import ssworld as SSW                                      # (owner 70, 71, 74: light, posters, rooms; tools/ssworld.py behind SS_WORLD=1 until proven)
GARRISON2 = SB.GARRISON2                                   # (owner 11-05, 55-56: tools/ssgarr.py, behind env SS_GARRISON2=1 until proven)
if GARRISON2:
    import ssgarr as GR
    SB.TEXTURES.update(GR.TEXTURES)
for _tn, _fn in SB.TEXTURES.items():
    _VLIB.texture(_tn, (lambda f_: (lambda: f_(_sbget)))(_fn))
TUN = SB.Tunnel(lambda x_, y_: _bh(x_, y_) + 0.1)
_VLIB.add('ss_hall_1', SB.hall_model, SB.HALL_SLOTS, lod_like='406_68_1')
if SB.GUNROOM:
    GN.models(globals())
if GARRISON2:
    _gb = GR.bulwark()
    _VLIB.add('ss_bulw_1', lambda: _gb.model(even=[s_ for s_ in GR.SLOTS if s_ != GR.S_MESH], alpha=(GR.S_MESH,)), GR.SLOTS, lod_like='406_68_1')
    _VLIB.add('ss_shut_1', GR.shutter_model, ['ss_corr', 'ss_hz'], lod_like='406_68_1')
    X.models('location3/level3', ['208_01_1'])
    X.models('location2/LEVEL2', ['260_02_1', '239_01_1', '306_01_1', '231_14_1', '230_19_1', '231_03_1', '231_04_1', '260_11_1', '230_06_1', '231_17_1', '231_15_1'])
    X.models('location2/LEVEL3', ['260_01_1', '231_10_1'])
    X.models('location1/level4', ['333_03_1'])
    X.models('location2/LEVEL5', ['360_05_1', '360_04_1'])
_VLIB.add('ss_trk_1', lambda: SH.truck_model(_truck), SH.TEL_SLOTS, lod_like='406_68_1')
TRUCKS2 = os.environ.get('SS_TRUCKS2', '1') == '1'           # (owner 65: wheels, drivers, stops, men, a hit: tools/sstruck.py)
if TRUCKS2:
    import sstruck as TK
    _VLIB.add('ss_trk2_1', lambda: TK.truck_model(_truck), SH.TEL_SLOTS, lod_like='406_68_1')
    _VLIB.texture(TK.GLASS_TEX, TK.tex_glass, alpha=True)   # (owner G09b: clear cab glass, the seated driver seen through it)
    _VLIB.add('ss_trkg_1', TK.glass_model, [TK.GLASS_TEX], lod_like='406_68_1')
    for _n in TK.AXLES:
        _VLIB.add(_n, (lambda n_: (lambda: TK.wheel_model(_truck, n_)))(_n), SH.TEL_SLOTS, lod_like='406_68_1')
_rl12 = V.orig_mesh('location1/level2', '417_01_1')
for _tn, _src in (('ss_tr0', '336_04_1'), ('ss_tr1', '336_03_1')):   # (dark weathered sleepers and rails, sand in the gravel between them)
    _VLIB.texture(_tn, (lambda n_: (lambda: SB.tex_track(_itx.decode(_rl12[0].find_resource('LOCAL:textures/%s.tex' % n_, 'textures')[1]), (0.46, 0.40, 0.33))))(_src))
_VLIB.add('ss_rail_1', lambda: SH.rail_model(_rl12), ['ss_tr0', 'ss_tr1'], lod_like='406_68_1')
_wd = SB.way_decor(V)
_VLIB.add('ss_wayd_1', lambda: _wd.model(even=_wd.slots), _wd.slots, lod_like='406_68_1')
m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS way down lining (see-only)', *V.U(_wd.o), 0.0, 0.0, 0.0, 'ss_wayd_1', 5, False, False))
for _n, _x, _y, _yw in (('crate 1', 164.4, 237.2, 0.0), ('crate 2', 169.6, 239.6, 0.0), ('crate 3', 167.6, 239.7, 0.3)):
    m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS storeroom ' + _n, _x * 4096.0, _y * 4096.0, (V.SHED[2] + V.SHED_FLOOR) * 4096.0, 0.0, 0.0, _yw, '330_01_1', 5, False, False))
X.models('location3/LEVEL4', ['205_35_1', '205_36_1', '261_32_1'])   # (owner 40, 44: the game's own lab and server furniture)
X.models('location2/LEVEL2', ['200_01_1', '231_15_1'])
X.models('location2/level1', ['333_03_1'])
X.models('location1/level1', ['335_01_1', '335_02_1', '335_03_1'])   # (the soft cameras with their own textures: from the common bank they drew peach)
X.models('location3/level3', ['261_04_1'])
X.models('location1/LEVEL6', ['261_05_1'])
X.models('location3/level1', ['660_01_1'])
_VLIB.add('ss_bgate_1', SB.gate_model, SB.GATE_SLOTS['ss_bgate_1'], lod_like='406_68_1')
_VLIB.add('ss_sgate_1', lambda: SB.gate_model(True), SB.GATE_SLOTS['ss_sgate_1'], lod_like='406_68_1')
_PORT = SB.portal_model(TUN, _bh)
_VLIB.add('ss_port_1', lambda: _PORT.model(even=['ss_sand']), SB.PORT_SLOTS, lod_like='406_68_1')   # (owner 11-04: every face of the berm the hill's own sand, no dark wedges)
m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS the base hall', *V.U(SB.ORIGIN), 0.0, 0.0, 0.0, 'ss_hall_1', 5, False, False))
if SB.GUNROOM:
    GN.place(globals())
if GARRISON2:
    m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS the Bulwark', *V.U(_gb.o), 0.0, 0.0, 0.0, 'ss_bulw_1', 5, True, False))   # (judge A03: 'Protect from shadows' on: the sun's man-shaped shadows climbed the mess walls indoors)
    for _k, (_x, _y, _z, _yw, _md) in enumerate(GR.BAGS):
        m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS sandbags %d' % _k, _x * 4096.0, _y * 4096.0, (SB.F + _z) * 4096.0, 0.0, 0.0, _yw, _md, 5, False, False))
m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS portal of the sand door', *V.U(_PORT.o), 0.0, 0.0, 0.0, 'ss_port_1', 5, False, False))
TUN_IDS = []
for _k, (_a, _b) in enumerate(TUN.part_ranges()):
    _tm = TUN.seg_mesh(_a, _b, SB.TUN_SLOTS)
    _nm = 'ss_tun%d_1' % (_k + 1)
    _VLIB.add(_nm, (lambda t_: (lambda: t_.model(even=SB.TUN_EVEN)))(_tm), SB.TUN_SLOTS, lod_like='406_68_1')
    _tid = nid(); TUN_IDS.append(_tid)
    m.add_child(HALL, T(_tid, 'EditRigidObj', 'SS truck tunnel %d' % (_k + 1), *V.U(_tm.o), 0.0, 0.0, 0.0, _nm, 5, False, False))
_pm = SB.post_mesh(TUN)
_VLIB.add('ss_post_1', lambda: _pm.model(even=_pm.slots), _pm.slots, lod_like='406_68_1')
m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS tunnel checkpoint', *V.U(_pm.o), 0.0, 0.0, 0.0, 'ss_post_1', 5, False, False))
_mg = TUN.check(_bh)
print('v5 tunnel: %.0f m, door (%.1f, %.1f) z %.1f, slope %.1f %%, cover min %.1f m before the exposed stretch' % (
    TUN.s[-1], TUN.door[0], TUN.door[1], TUN.door_z, 100 * (TUN.door_z - SB.F) / (TUN.s[-1] - SB.SLOPE_FLAT_A - SB.SLOPE_FLAT_B), _mg[:TUN.exposed].min()))
assert _mg[:TUN.exposed].min() > 0.5, 'the tunnel leaves the hill'
X.models('location1/level1', ['337_11_1'])
for _k, (_s, _l) in enumerate(((42.0, -3.5), (47.0, -3.4), (96.0, 3.5), (150.0, -3.6), (236.0, 3.5), (242.0, 3.6), (280.0, -3.5))):   # (critic rv10: 20 identical segments)
    _q = TUN.at(_s); _px = _q[0] + _q[4][0] * _l; _py = _q[1] + _q[4][1] * _l
    m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS tunnel crates %d' % _k, _px * 4096.0, _py * 4096.0, (_q[2] - 0.08) * 4096.0, 0.0, 0.0, 0.3 * _k, '330_01_1', 5, False, False))   # (RQ4 ss-look S7: only the 1.22 m crate; the 2.44 m one floated 0.7 m on the ramp)
for _nm, _md, _x, _y, _z, _yw in SB.props():
    m.add_child(HALL, T(nid(), 'EditRigidObj', _nm, _x * 4096.0, _y * 4096.0, _z * 4096.0, 0.0, 0.0, _yw, _md, 5, False, False))
_bz = SB.PIT_Z
m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS the big missile (panels open)', *V.U((SB.PIT_C[0], SB.PIT_C[1], _bz)), 0.0, 0.0, 0.3,
                    'ss_bigm_1', 5, False, False))
m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS missile service gantry', *V.U((SB.PIT_C[0] - 2.6, SB.PIT_C[1], _bz)), 0.0, 0.0,
                    math.pi, 'ss_gant_1', 5, False, False))
TELS = []
for _k, (_tx, _ty) in enumerate(SB.TEL_SPOTS):
    _tid = nid(); TELS.append(_tid)
    m.add_child(HALL, T(_tid, 'EditRigidObj', 'SS launch truck %d' % (_k + 1), *V.U((_tx, _ty, SB.F)), 0.0, 0.0, 0.0,
                        'ss_telr_1' if _k == 1 else 'ss_tel_1', 5, False, False))
# --- owner 11-04 'the train is not on the railway': a ballast bed under the whole line, the rails on top of it, buffer stops at its end (before navgen)
TR_Y = 203.0
_tg = [_bh(x_, y_) for x_ in np.arange(376.0, 530.0, 4.0) for y_ in (TR_Y - 2.0, TR_Y + 2.5)]
RAIL_Z = round(float(max(_tg)) + 0.2, 2)                  # (west of x ~372 and far east the sand has drifted over the line: the rails run into the dunes)
_bedy = TR_Y + 0.43                                        # (the double track's middle)
for _k, _bm in enumerate(SB.bed_meshes(358.0, 568.0, _bedy, RAIL_Z - 0.12)):
    _nm = 'ss_bed%d_1' % _k
    _VLIB.add(_nm, (lambda t_: (lambda: t_.model()))(_bm), _bm.slots, lod_like='406_68_1')
    m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS railway bed %d' % _k, *V.U(_bm.o), 0.0, 0.0, 0.0, _nm, 5, False, False))
_dr1 = SB.drift(362.0, 381.0, _bedy, RAIL_Z)
_VLIB.add('ss_drift_1', lambda: _dr1.model(), _dr1.slots, lod_like='406_68_1')
m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS sand over the line', *V.U(_dr1.o), 0.0, 0.0, 0.0, 'ss_drift_1', 5, False, False))
if os.environ.get('SS_RAIL_EAST', '0') == '1':             # (N3 11-17 ss-ending, default OFF = installed: east of x ~533 the ballast is under the dune before the
    _dr2 = SB.drift_east(530.5, 533.0, 550.0, _bedy, RAIL_Z + 0.18, _bh)   #  sleepers and rail heads (top RAIL_Z + 0.18): ~10 m of bare rails taper into the sand; a sand mound over them)
    _VLIB.add('ss_drift2_1', lambda: _dr2.model(), _dr2.slots, lod_like='406_68_1')
    m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS sand over the line east', *V.U(_dr2.o), 0.0, 0.0, 0.0, 'ss_drift2_1', 5, False, False))
# (critic rv12: the run to the train is empty dunes) a pump hut and scattered crates give it cover and a reason
for _nm, _md, _x, _y, _yw in (('SS pump hut', '432_10_1', 352.0, 182.0, 0.5), ('SS trackside crates 1', '330_01_1', 338.0, 188.0, 0.4), ('SS trackside crates 2', '330_02_1', 339.6, 186.8, 1.0),
                              ('SS trackside crates 3', '330_01_1', 366.0, 193.0, 0.2), ('SS trackside crates 4', '330_01_1', 372.0, 196.0, 0.9)):
    m.add_child(HALL, T(nid(), 'EditRigidObj', _nm, _x * 4096.0, _y * 4096.0, (_bh(_x, _y) - (0.23 if _md == '432_10_1' else 0.03)) * 4096.0, 0.0, 0.0, _yw, _md, 5, False, False))   # (RQ5 ss-look S7: the hut sat 0.17 m high on one side)
print('v5 railway: ground up to %.2f m, rail z %.2f m' % (max(_tg), RAIL_Z))
INTRO2 = os.environ.get('SS_INTRO2', '1') == '1'                  # (owner 72, 73: the new opening, tools/ssintro.py, behind this flag until proven)
if INTRO2:
    import ssintro as _SI
OUTRO2 = os.environ.get('SS_OUTRO2', '1') == '1'                  # (owner 46-51: the second ending, tools/ssoutro.py, behind this flag until proven)
if OUTRO2:
    import ssoutro as _SO
    _SO.world(globals())
CTRL_DOOR = nid()                                          # the control room's door: the map's own 501_04_1 (a copy of 3928), a plain door (E)
_cd = _copy.deepcopy(L[3928]); _cd.args[0] = v(CTRL_DOOR); _cd.args[2] = v('SS control room door')
_cd.args[3] = v((SB.CTRL[0] - 0.125) * 4096.0); _cd.args[4] = v((SB.CTRL_DOOR_Y[0] + 0.02) * 4096.0); _cd.args[5] = v(SB.F * 4096.0)
_cd.args[11] = v(math.pi / 2); _cd.args[15] = v(False); _cd.args[18] = v(''); _cd.args[19] = v(''); _cd.args[20] = v('')   # (arg 18 = the LOCK rule: '' = a plain door, E opens it)
m.add_child(4029, _cd)
_MPAN = SH.missile_panels(SB.PIT_C, 1.25, SB.F + 1.0)
_VLIB.add('ss_mpan_1', lambda: _MPAN.model(even=['jr_dark', 'ss_hz', 'ss_stl', 'ss_cpaint']), ['jr_dark', 'ss_hz', 'ss_stl', 'ss_cpaint'], lod_like='406_68_1')
m.add_child(HALL, T(nid(), 'EditRigidObj', 'SS missile open bays', *V.U(_MPAN.o), 0.0, 0.0, 0.0, 'ss_mpan_1', 5, False, False))
_VLIB.add('ss_cgate_1', SB.cage_gate_model, ['ss_hz', 'ss_stl'], lod_like='406_68_1')
if GARRISON2:
    for _nm, _ax, _c, _t, _z in GR.DOORS:
        _rd = _copy.deepcopy(L[3928]); _ri = nid(); _rd.args[0] = v(_ri); _rd.args[2] = v('SS garrison door ' + _nm)
        _px, _py, _yw = (_c, _t + 0.02, math.pi / 2) if _ax == 'x' else (_t + 0.02, _c, 0.0)
        _rd.args[3] = v(_px * 4096.0); _rd.args[4] = v(_py * 4096.0); _rd.args[5] = v((SB.F + _z) * 4096.0)
        _rd.args[11] = v(_yw); _rd.args[15] = v(False); _rd.args[16] = v(True); _rd.args[18] = v(''); _rd.args[19] = v(''); _rd.args[20] = v('')   # (gwb, gwc: a leaf that swings at the man stops on him: arg 16, it opens away)
        if _nm == 'armoury':                               # (a pick pays: the silenced gun and ammo inside)
            _rd.args[15] = v(True); _rd.args[17] = v(6.0); _rd.args[18] = v('1')
            CLOSED_FOR_AI = CLOSED_FOR_AI + (_ri,)
        m.add_child(4029, _rd)
for _k, (_rx0, _rx1) in enumerate(() if GARRISON2 else SB.ROOMS):
    _rd = _copy.deepcopy(L[3928]); _ri = nid(); _rd.args[0] = v(_ri); _rd.args[2] = v('SS quarters room door %d' % (_k + 1))
    _rd.args[3] = v(((_rx0 + _rx1) / 2 - 0.58) * 4096.0); _rd.args[4] = v((SB.QUARTERS[1] + 0.1) * 4096.0); _rd.args[5] = v(SB.F * 4096.0)
    _rd.args[11] = v(0.0); _rd.args[15] = v(False); _rd.args[18] = v(''); _rd.args[19] = v(''); _rd.args[20] = v('')
    m.add_child(4029, _rd)
print('v5 hall: big missile at %s (floor %.1f), launch trucks %s' % (SB.PIT_C, _bz, TELS))
_hx, _hy, _hw, _hh, _hcut = V.hole_rect(_CELL, _TB.maps[0][1] / 4096.0, _TB.maps[0][2] / 4096.0, V.HATCH, (163.4, 236.1, V.SHED_EAST, 240.9))
SHED_HOLE = nid()
m.add_child(m.find('Terrain')[0], T(SHED_HOLE, 'DiscardTask', 'SS stair hatch under the shed', _hx * 4096.0, _hy * 4096.0, -7.3 * 4096.0, _hw, _hh))
if SSW.WORLD:
    SSW.add_models(X, _VLIB)
    SSW.rooms(m, nid, T, m.find('Static')[0])
    SSW.fix_racks(m)
V_NAVRES = V.write_nav_res(_VLIB.build(), os.path.join(HERE, 'work', 'sandstorm', 'navstage', 'ss_v4.res'))
print('v4 way down: shed hatch %s (shed frame), terrain cut %s m, machine room %s, lift %.1f -> %.1f m' % (
    [round(c_, 2) for c_ in SHED_HATCH], [round(c_, 2) for c_ in _hcut], MROOM, V.TOP_Z, LIFT_BOTTOM))
_, BK_MERGED = X.finish(os.path.join(HERE, 'work', 'sandstorm', 'navstage'))
# (compat for the older debug variants that still name the 11-02 bunker frame: they now land in hall B)
BW = lambda lx, ly, lz=0.0: V.U((238.0 + lx, 225.0 + ly, SB.F + lz))
BK_FOOT, BK_RING, BK_TEND, BK_FAR = 0.0, 0.0, 0.0, 30.0
def bk_blocked(x_u, y_u):
    return bool(SB.GUNROOM and GN.S14B_ON and GN.screen_blocked(x_u, y_u))   # (S14 decision 91: graph 6 drops nodes on / links through the lobby barricade)
# (S15 owner 11-15 'enemies walk through cars': the two troop trucks park ON the long-ramp floor the graph was made from, and a walking
#  soldier follows the link, not the collision. Their stop poses only need TUN / SB.POST_S / TK.STOPS, so they are made here, before the graphs)
_trs = np.arange(SB.POST_S - 16.0, TK.STOPS[0] - 1.0 if TRUCKS2 else 27.0, -5.0)
_trq = [TUN.at(float(s_)) for s_ in _trs]
_trl = [1.1 if abs(TUN.at(float(s_) + 4.0)[3] @ TUN.at(float(s_) - 4.0)[3]) < 0.985 else 2.3 for s_ in _trs]   # (critic rv10: its corners went through the wall in the bends)
_trp = [((q_[0] + q_[4][0] * l_) * 4096.0, (q_[1] + q_[4][1] * l_) * 4096.0, q_[2] * 4096.0) for q_, l_ in zip(_trq, _trl)]
_trg2 = np.unwrap([math.atan2(-q_[3][1], -q_[3][0]) + math.pi for q_ in _trq])     # (its nose is -x; it drives against the path's direction)
TRK_STOPS = [(_trp[-1][0] / 4096.0, _trp[-1][1] / 4096.0, float(_trg2[-1])), (_trp[-4][0] / 4096.0, _trp[-4][1] / 4096.0, float(_trg2[-4]))] if TRUCKS2 else []
print('S15 truck stops: %s' % ['(%.2f, %.2f, %.3f)' % s_ for s_ in TRK_STOPS])


def trk_blocked(x_u, y_u, pad=0.7):
    """a point (units) inside a parked troop truck's hull (sstruck.truck_model: x -3.3..3.3, y -1.2..1.2 local m) + pad m"""
    for cx, cy, g in TRK_STOPS:
        dx, dy = x_u / 4096.0 - cx, y_u / 4096.0 - cy
        a, b = dx * math.cos(g) + dy * math.sin(g), -dx * math.sin(g) + dy * math.cos(g)
        if abs(a) <= 3.3 + pad and abs(b) <= 1.2 + pad:
            return True
    return False
def bed_blocked(x_u, y_u):                                 # (graph 8 stays off the railway embankment: no node on it, no link through it)
    return 354.0 * 4096 < x_u < 572.0 * 4096 and abs(y_u - _bedy * 4096) < (SB.BED_HW + SB.BED_FOOT + 1.2) * 4096

# =========================================================== 3. AI graphs (generated: the multiplayer map has none)
NAV_BOUNDS = (60000.0, -200000.0, 1950000.0, 1640000.0)   # (v4: east to x 476 m - the cave's halls, the plain by the train)
# (owner 92: the cage gate is only placed further down, so the graph ran through it as open floor and men walked through the shut leaf: a walking soldier follows the link, not the collision. A Door here gives it door nodes, like every other door)
PICK_DOORS = (3664, CELL_DOOR, SHED_DOOR_ID)               # (A9 / S17 orch-2 11-15: the 'pick it' doors (rc7s25 ids 3664, 1623, 1624) had AI door nodes: a soldier there opens them unpicked)
LOOT_DOORS = (4025, 4026)                                 # (A9 ss-int chkdoors 11-15: the armoury leaves, locked by ssloot.apply AFTER navgen. look_2 11-16: closing them at navgen left the
                                                          #  large-house lobby pocket without nodes ('talk pair S large house' failed) -> RQ7: closed again, the lobby has its own graph LOBBY_G)
NAV_OPEN = () if RQ7 else LOOT_DOORS                      # (SS_RQ7=0: the 411a201 state, leaves open for navgen, ssloot.cut_graph makes the islands)
LOCKED_AT_NAV = tuple(sorted(i_ for i_ in m.find('Door') if str(lit(m.byid[i_].args[18])).strip() not in ('', '0')))   # (A9: every door locked now, e.g. the MP map's pickable 3079 / 3080 / 3668 / 3669 '1')
_cgn = nid(); _cgd = _copy.deepcopy(L[3928]); _cgd.args[0] = v(_cgn); _cgd.args[12] = v('ss_cgate_1')
for _k, _c in enumerate((SB.PIT[0] * 4096.0, SB.PIT_C[1] * 4096.0, SB.F * 4096.0)):
    _cgd.args[3 + _k] = v(_c)
_cgd.args[6] = v(0.0); _cgd.args[7] = v(SB.DOOR_SLIDE); _cgd.args[8] = v(0.0); _cgd.args[9] = v(math.pi / 2); _cgd.args[10] = v(0.0); _cgd.args[11] = v(0.0)
m.add_child(4029, _cgd)
nv = navgen.generate(m, NAV_BOUNDS, [G_ + 'MISSIONS/multiplayer/sandstorm/models/sandstorm.res',
                                     G_ + 'MISSIONS/multiplayer/common/models/multiplayer.res', G_ + 'COMMON/models/common.res', BK_MERGED, V_NAVRES],
                     cache_dir=os.path.join(HERE, 'work', 'navcache'), fine_tile=9, coarse_tile=22,
                     closed_doors=tuple(sorted(set(CLOSED_FOR_AI + (_cgn,) + PICK_DOORS + LOCKED_AT_NAV + LOOT_DOORS) - set(NAV_OPEN))), max_dev_m=0.20, long_link_m=25.0)
# (S17 owner 11-15 'the missile-site gate is ALREADY OPEN before I go to the computer'): with door nodes a soldier who reaches one toggles the
#  nearest door and the lock flag is not read on that path (humanai.c 10405); its close rule is '0', so it stayed up. Watched on rc7s25 (rig takes
#  work/films/proof_11-15/S17 watch_a / watch_c): calm, the leaf stays shut for minutes; in the alert a hall rifleman stands in the open gateway.
#  Now the cage gate is a CLOSED door for the graph: no door pair, no link through it; the nodes inside the cage fall away as an island
m.remove(_cgn)
# (owner 10-11 'the enemies float above the ground / sink into it': a walking soldier's feet follow the straight line
#  between two graph nodes - igi2.exe 0x50c820 - so links must follow the ground: navgen max_dev_m, bridge nodes)
NF = nv.F
NODE_P = np.array([[NF['x'][q['s']], NF['y'][q['s']], NF['z'][q['s']]] for q in nv.nodes])
ADJ = {}
for a_, b_ in nv.edges:
    ADJ.setdefault(a_, set()).add(b_); ADJ.setdefault(b_, set()).add(a_)


def region_graph(probe, box):
    """the connected set of nodes inside box (x0, y0, x1, y1) that contains the node nearest to probe"""
    inside = (NODE_P[:, 0] >= box[0]) & (NODE_P[:, 0] <= box[2]) & (NODE_P[:, 1] >= box[1]) & (NODE_P[:, 1] <= box[3])
    d = np.hypot(NODE_P[:, 0] - probe[0], NODE_P[:, 1] - probe[1]) + 3 * np.abs(NODE_P[:, 2] - probe[2])
    d[~inside] = 1e18
    seed = int(np.argmin(d))
    comp, todo = {seed}, [seed]
    while todo:
        u = todo.pop()
        for w in ADJ.get(u, ()):
            if inside[w] and w not in comp:
                comp.add(w); todo.append(w)
    return sorted(comp)


GRAPHS = {}                                               # id -> list of node dicts (pos, crit, terrain)
GEDGES = {}                                               # id -> [(node a, node b)]
import re as _re
SQ_AREAS = {}                                             # graph -> [(x, y, r)] of every squad() call below + start/objectives
for _g, _x, _y, _r in _re.findall(r"^squad\('[^']*', (\d), \(([-\d.]+), ([-\d.]+)\), ([-\d.]+)",
                                  open(os.path.abspath(__file__)).read(), _re.M):
    if int(_g) in (1, 2, 4, 8):
        SQ_AREAS.setdefault(int(_g), []).append((float(_x), float(_y), float(_r)))
SQ_AREAS[1] += [(START[0], START[1], 30000.0), (518600.0, 344000.0, 60000.0)]   # landing zone, both generators
SQ_AREAS[2] += [(560000.0, 900000.0, 60000.0), (850000.0, 784000.0, 60000.0),     # airbase centre, east pad + fuel depot,
                 (595000.0, 1045000.0, 30000.0)]                                    # the bunker courtyard + the Hind pad gap
if RQ7:                                                   # (the large-house squad is on LOBBY_G now; graph 1 keeps its trim area as before)
    SQ_AREAS[1].append((318900.0, 481300.0, 26000.0))
SQ_AREAS.setdefault(4, []).append((640000.0, 1545000.0, 80000.0))
SQ_AREAS.setdefault(8, []).extend([(412.0 * 4096, 225.0 * 4096, 45000.0), (440.0 * 4096, 232.0 * 4096, 30000.0)])   # (v4: the sand door -> the train)                                # the extraction area
GZ = {6: (SB.F - 1.0, SB.F + (9.0 if SB.GUNROOM else 8.5 if GARRISON2 else 2.0)), 7: (V.TOP_Z - 1.0, V.TOP_Z + 1.0), 8: (-1.0, 40.0)}   # (owner 11-03 r3: graph 7 = the machine
#  room + corridor floor only - it reached up the stairs and the machine-room guards walked up into the shed when they heard shots)
graph_box = nid()
m.add_child(4095, T(graph_box, 'Container', 'Static AI', False))
gcont = nid()
m.add_child(graph_box, T(gcont, 'Container', 'Graphs', False))
NAV_COMPS = {}                                            # (RQ7: graph id -> the navgen node indices it exported)
for gid, name, probe, box in [
        (1, 'South compound and desert', START, (150000.0, -175000.0, 910000.0, 600000.0)),
        (2, 'Airbase valley', (560000.0, 1000000.0, -28000.0), (60000.0, 640000.0, 1000000.0, 1345000.0)),
        (3, 'Sewer channel', (352200.0, 11170.0, -84353.0), (60000.0, -200000.0, 1000000.0, 1640000.0)),
        (4, 'North tunnel exit', (698126.0, 1558158.0, 61330.0), (400000.0, 1345000.0, 1000000.0, 1640000.0)),
        (5, 'Hill house roof', (484900.0, 337500.0, 96290.0), (440000.0, 300000.0, 530000.0, 375000.0)),
        (6, 'Missile base (underground)', V.U((205.0, 225.0, SB.F)), (170.0 * 4096, 195.0 * 4096, 269.0 * 4096, 257.0 * 4096)),
        (7, 'Machine room and stairs', V.U((182.0, 231.0, V.TOP_Z)), ((158.0 if LIFTG else 164.0) * 4096, 216.0 * 4096, 193.0 * 4096, 242.0 * 4096)),
        (8, 'East plain by the train', (440.0 * 4096, 232.0 * 4096, _bh(440.0, 232.0) * 4096), (300.0 * 4096, 140.0 * 4096, 476.0 * 4096, 262.0 * 4096)),
        (9, 'Truck tunnel checkpoint', V.U(TUN.at(SB.POST_S - 12.0)[:3]), (240.0 * 4096, 120.0 * 4096, 270.0 * 4096, 195.0 * 4096))] + ([(11, 'Long ramp', V.U(TUN.at(100.0)[:3]), (262.0 * 4096, 40.0 * 4096, 345.0 * 4096, 240.0 * 4096))] if TRUCKS2 else []) + ([(GN.ROOM_G, 'Gun room', V.U((172.3, 226.6, GN.FZ)), (168.0 * 4096, 218.0 * 4096, 176.0 * 4096, 235.0 * 4096))] if SB.GUNROOM else []) + ([(LOBBY_G, 'Large house lobby', (318546.0, 482550.0, 18964.0), (278528.0, 421888.0, 360448.0, 532480.0))] if RQ7 else []):
    comp = region_graph(probe, box)
    if gid == LOBBY_G and RQ7:                             # (RQ7: the lobby + upstairs, behind the shut armoury leaves; the armoury's own nodes are left out (judge Q24: no man in it),
        assert LOBBY_G not in m.byid, 'RQ7: task id %d is taken, LOBBY_G needs a free id' % LOBBY_G   #  then the largest connected part: one island)
        _arm = lambda k_: 74.55 < NODE_P[k_][0] / 4096.0 < 82.0 and 103.5 < NODE_P[k_][1] / 4096.0 < 113.55
        _n0 = len(comp)
        _cs = {k_ for k_ in comp if not _arm(k_)}
        _best, _seen = set(), set()
        for k0_ in sorted(_cs):
            if k0_ in _seen:
                continue
            _part, _todo = {k0_}, [k0_]
            while _todo:
                u_ = _todo.pop()
                for w_ in ADJ.get(u_, ()):
                    if w_ in _cs and w_ not in _part:
                        _part.add(w_); _todo.append(w_)
            _seen |= _part
            if len(_part) > len(_best):
                _best = _part
        comp = sorted(_best)
        assert not set(comp) & NAV_COMPS.get(1, set()), 'RQ7: the lobby pocket is also on graph 1 (a link past the armoury leaves): %d shared nodes' % len(set(comp) & NAV_COMPS[1])
        print('graph %d: lobby pocket %d -> %d nodes (armoury nodes and islands left out)' % (gid, _n0, len(comp)))
    if gid in GZ:                                         # (v4: the underground graphs keep their own level only)
        _n0 = len(comp)
        comp = [k_ for k_ in comp if GZ[gid][0] <= NODE_P[k_][2] / 4096.0 <= GZ[gid][1]]
        print('graph %d: %d -> %d nodes in z %s m' % (gid, _n0, len(comp), GZ[gid]))
    if gid in (9, 11):                                     # (the ramp only: the nodes on the tunnel's floor)
        _tq = np.array([TUN.at(s_)[:3] for s_ in (np.arange(60.0, 180.0, 1.0) if gid == 11 else np.arange(SB.POST_S - 26.0, SB.POST_S + 26.0, 1.0))]) * 4096.0
        comp = [k_ for k_ in comp if (np.hypot(_tq[:, 0] - NODE_P[k_][0], _tq[:, 1] - NODE_P[k_][1]).min() < 4.6 * 4096 and np.abs(_tq[:, 2] - NODE_P[k_][2]).min() < 1.5 * 4096)]
        print('graph %d: %d nodes on the ramp' % (gid, len(comp)))
    _ed0 = nv.edges
    if gid in (6, 8, 11):                                  # (the bunker: drop nodes on / links through the set-piece props; the plain: the rail bed; S15 the ramp: the parked trucks)
        _blk = {6: bk_blocked, 8: bed_blocked, 11: trk_blocked}[gid]
        _n0 = len(comp)
        comp = [k_ for k_ in comp if not _blk(NODE_P[k_][0], NODE_P[k_][1])]
        _cs = set(comp)
        def _cut(a_, b_):
            return any(_blk(NODE_P[a_][0] + (NODE_P[b_][0] - NODE_P[a_][0]) * t_, NODE_P[a_][1] + (NODE_P[b_][1] - NODE_P[a_][1]) * t_)
                       for t_ in np.linspace(0.0, 1.0, 24 if gid == 11 else 12))
        nv.edges = [e_ for e_ in _ed0 if not (e_[0] in _cs and e_[1] in _cs and _cut(*e_))]
        _adj = {}
        for a_, b_ in nv.edges:
            if a_ in _cs and b_ in _cs:
                _adj.setdefault(a_, set()).add(b_); _adj.setdefault(b_, set()).add(a_)
        _best, _seen = [], set()
        _keep8 = min(comp, key=lambda k_: math.hypot(NODE_P[k_][0] - 412.0 * 4096, NODE_P[k_][1] - 225.0 * 4096))
        for k0_ in comp:                                   # (keep the largest connected part: no islands behind the container)
            if k0_ in _seen:
                continue
            _part, _todo = {k0_}, [k0_]
            while _todo:
                u_ = _todo.pop()
                for w_ in _adj.get(u_, ()):
                    if w_ not in _part:
                        _part.add(w_); _todo.append(w_)
            _seen |= _part
            if len(_part) > len(_best) or (gid == 8 and _keep8 in _part):   # (the plain: the part with the landing party, north of the line)
                _best = sorted(_part)
                if gid == 8 and _keep8 in _part:
                    break
        comp = _best
        print('graph %d: %d -> %d nodes off the set piece, %d links through it dropped' % (gid, _n0, len(comp), len(_ed0) - len(nv.edges)))
    if gid in SQ_AREAS:                                    # ground-following graphs are denser: keep the squads' ground
        import spkit as _spkit, types as _types
        _n0 = len(comp)
        comp = _spkit.Kit.trim(_types.SimpleNamespace(NODE_P=NODE_P, ADJ=ADJ), comp,
                               [(x_, y_, r_ * 1.2 + 15000.0) for x_, y_, r_ in SQ_AREAS[gid]], 30.0)
        print('graph %d: trimmed to the squads\' ground: %d -> %d nodes' % (gid, _n0, len(comp)))
    data, gnodes, ne, mx = nv.export(comp)
    nv.edges = _ed0
    m.graphs[gid] = (data, None)
    GRAPHS[gid] = gnodes
    NAV_COMPS[gid] = set(comp)
    GEDGES[gid] = list(nv.last_edges)                      # (tools/alarmai.py: the hunters' reach on each graph)
    m.add_child(gcont, T(gid, 'AIGraph', name, 0.0, 0.0, 0.0, True, False, len(gnodes), mx, ne,
                         0.7, 2.0, 3.0, 0.3, 1.5, 15.0, False, 0.05, False))
    print('graph %d %-28s nodes %4d edges %5d doors %d | %s' % (gid, name, len(gnodes), ne, sum(1 for n in gnodes if n['crit']), nv.merge_log))
    import spkit as _spkit, types as _types
    _dev = _spkit.Kit.link_report(_types.SimpleNamespace(TERR=nv.terrain), gid, gnodes, nv.last_edges)
    if _dev:
        print('graph %d terrain links vs ground: p50 %.1f p90 %.1f max %.1f cm' % ((gid,) + _dev))
        assert _dev[2] <= 26.0, 'graph %d: a link leaves the ground by %.0f cm' % (gid, _dev[2])
assert all(len(g) < 2000 for g in GRAPHS.values()), 'graph too large (A* arrays hold 2000 slots, ids 1..N)'
if 11 in GRAPHS:                                          # (S15 build gate: no ramp node in a parked truck, no ramp link through one, with a 0.45 m body radius)
    _g11 = {q_['id']: q_['pos'] for q_ in GRAPHS[11]}
    _bad = [i_ for i_, p_ in _g11.items() if trk_blocked(p_[0], p_[1], pad=0.45)]
    _bad += [(a_, b_) for a_, b_ in GEDGES[11] if any(trk_blocked(_g11[a_][0] + (_g11[b_][0] - _g11[a_][0]) * t_, _g11[a_][1] + (_g11[b_][1] - _g11[a_][1]) * t_, pad=0.45)
                                                    for t_ in np.linspace(0.0, 1.0, 48))]
    assert not _bad, 'S15: graph 11 runs through a parked troop truck: %s' % _bad[:8]
    print('S15 check: graph 11 clear of both parked trucks (%d nodes, %d links)' % (len(_g11), len(GEDGES[11])))
_cgd6 = [q_['id'] for q_ in GRAPHS.get(6, []) if q_['crit'] and math.hypot(q_['pos'][0] / 4096.0 - SB.PIT[0], q_['pos'][1] / 4096.0 - SB.PIT_C[1]) < 3.0]
assert not _cgd6, 'S17: graph 6 has door nodes at the missile cage gate (a soldier there opens it): %s' % _cgd6
assert not [q_ for q_ in GRAPHS.get(6, []) if SB.PIT[0] < q_['pos'][0] / 4096.0 < SB.PIT[2] and SB.PIT[1] < q_['pos'][1] / 4096.0 < SB.PIT[3]], 'S17: graph 6 nodes inside the cage'
print('S17 check: no AI door nodes and no graph 6 nodes at / in the missile cage')
print('A9: closed for the AI graphs: %s' % sorted(set(CLOSED_FOR_AI + (_cgn,) + PICK_DOORS + LOCKED_AT_NAV + LOOT_DOORS) - set(NAV_OPEN)))
if os.environ.get('SS_NODES'):                            # dev aid: dump the graph nodes for placement work
    import pickle
    pickle.dump(GRAPHS, open(os.path.join(HERE, 'work', 'ss_graphs.pkl'), 'wb'))
    pickle.dump(GEDGES, open(os.path.join(HERE, 'work', 'ss_gedges.pkl'), 'wb'))   # (11-02 r8: routes by A* on the graph)
    sys.exit(0)


# =========================================================== 4. objectives
def gtba(tid, name, pos, rot, model, done_model, anim, secs, sprite, sound, parent):
    m.add_child(parent, T(tid, 'GenericTBA', name, *[float(c) for c in pos], *[float(r) for r in rot], model, done_model,
                          100.0, 0.0, 0.0, 0.0, 0.0, 0, 0, '', '', 0.0, 0.0, 0.0, False,
                          '!GenericTBA_%d.isFinished' % tid, anim, float(secs), sprite, sound))


# O1: the two power generators (code pads of the MP map)
for i in (150, 152):
    m.set(i, 18, ''); m.set(i, 24, '!GenericTBA_%d.isFinished' % i); m.set(i, 26, 4.0)   # 4 s = length of the hands animation (originals); longer = hands stop, E must be held
POWER_OFF = 'GenericTBA_150.isFinished && GenericTBA_152.isFinished'
m.set(3927, 18, '!(%s)' % POWER_OFF)                      # south-compound sewer door unlocks when the power is off

# Door 3927 (south sewer hut <-> south compound): locked from the compound side until the power is off, but it always
# opens from INSIDE the hut (owner 10-10: came in through the landing-zone sewer and could not get out to area 1).
# The hut side is the side with a roof over the floor (tested 10-10: the +normal side is the sunlit compound).
D27 = [d_ for d_ in nv.doors() if d_['id'] == 3927][0]
def _headroom(sgn):
    s_ = nv.surface_at(*(D27['center'] + D27['normal'] * sgn * 6000)[:2], D27['zlo'] + 200, maxdz=2500, radius=2)
    return NF['ceil'][s_] - NF['z'][s_]
HUT_SIGN = [sg for sg in (1, -1) if _headroom(sg) < 8 * 4096]
assert len(HUT_SIGN) == 1, ('door 3927: cannot tell the hut side', _headroom(1), _headroom(-1))
HUT_SIGN = HUT_SIGN[0]
print('door 3927: hut side %+d (headroom %.1f m / %.1f m)' % (HUT_SIGN, _headroom(HUT_SIGN) / 4096, _headroom(-HUT_SIGN) / 4096))
_hut = D27['center'] + D27['normal'] * 6500 * HUT_SIGN
print('door 3927: hut point %.0f,%.0f' % (_hut[0], _hut[1]))
SEWER_HUT = nid()
_hutc = D27['center'] + D27['normal'] * 7000 * HUT_SIGN   # (owner 9, 11-07: the box was 1.2 m wide, extents are FULL widths, so inside the hut the door stayed locked with no prompt at most spots. Now the hut from 5 cm behind the leaf back 3.3 m, 3.9 m wide)
m.add_child(LOGIC, T(SEWER_HUT, 'AreaActivate', 'SS inside the south sewer hut', float(_hutc[0]), float(_hutc[1]), float(D27['zlo']) + 4000.0,
                     0.0, 0.0, 0.0, 16000.0, 13600.0, 12000.0, 'CRITERIA_HUMAN0'))
m.set(3927, 18, '(!GenericTBA_150.isFinished || !GenericTBA_152.isFinished) && !AreaActivate_%d.nActive' % SEWER_HUT)

# O2: through the sewer into the airbase (player climbs out at the north sewer entrance)
SEWER_EXIT = nid()
m.add_child(LOGIC, T(SEWER_EXIT, 'AreaActivate', 'SS reached the airbase', 381673.5, 843439.2, 2000.0, 0.0, 0.0, 0.0,
                     60000.0, 60000.0, 26000.0, 'CRITERIA_HUMAN0'))

# O3: flight plans on the basement server of the western admin building (where MP terminal 701 stood)
COMPUTER = nid()
p701 = TERMINALS[701]
gtba(COMPUTER, 'SS flight plan server', p701[:3], p701[3:6], '200_01_1', '200_01_1', 'hack_computer', 4.0,   # (judge F05: the screen stays lit after the hack)
     'STATUSSCREEN:action_comput.spr', 'tba_hackcomp', LOGIC)

# optional: camera control computer (MP terminal 1601) shuts the airbase cameras down for good
SECURITY_PC = nid()
p1601 = TERMINALS[1601]
gtba(SECURITY_PC, 'SS camera control computer', p1601[:3], p1601[3:6], '200_01_1', '200_03_1', 'hack_computer', 4.0,
     'STATUSSCREEN:action_comput.spr', 'tba_hackcomp', LOGIC)

# O5 (owner 10-12): plant C4 on BOTH Hind gunships. The countdown only starts once the second charge is planted
# (MissionTimer = the originals' on-screen clock, location2/level1 3541; a LevelTimer started by the same condition
# blows both up - the originals' recipe). Guns, grenades and rockets no longer hurt them (HP 1e6).
import spkit as _spkit2, atmos as _atmos, cams as _cams
K = _spkit2.Kit.__new__(_spkit2.Kit)                       # the kit's spot finders / plant / marker on this builder's mission
K.m, K.PFX, K.nid, K.NODE_P, K.nv, K.LOGIC = m, 'SS', nid, NODE_P, nv, LOGIC
K.TERR = terrain_mod.Terrain(m.src, m.stmts)
FUSE_S = 30                                                # seconds on the clock after the 2nd charge
HINDS, CHARGES, CHARGE_AT, CHARGE_FLOOR = [], {}, {}, {}
O3_ID = nid()                                              # (v4: the objective-3 message id, reserved - the C4 charges wait for it)

HIND_PAD_Z = {}
for hid, label in ((3901, 'SS Hind north pad'), (3904, 'SS Hind east pad')):
    t = L[hid]
    a = [lit(x) for x in t.args[3:9]]
    rotors = [c for c in t.args if isinstance(c, Call)]
    for r_ in rotors:
        r_.args[5] = v(0.0)                                # parked: rotors still
    par = m.parent[hid]
    idx = par.args.index(t)
    # the blast is an invisible ExplodeObject; the Hind you see is the MP EditRigidObj with its rotor attachments, shown
    # only until the blast (10-12 test: rotors attached to the ExplodeObject stayed hanging in the air over the wreck)
    par.args[idx] = T(hid, 'ExplodeObject', label, *[float(c) for c in a], 'none', 'none', 1e6, 5.0, 3.0, 1.5, 0.3,
                      6, 8, '', 'explo_04_xl')
    HINDS.append(hid)
    HIND_PAD_Z[hid] = float(a[2])
    m.add_child(LOGIC, T(nid(), 'ConditionalContainer', label + ' (intact until the blast)', '!ExplodeObject_%d.isExploded' % hid,
                         '', '', children=[T(nid(), 'EditRigidObj', label + ' (intact)', *[float(c) for c in a], '740_01_1', 5,
                                             False, False, children=rotors)]))
m.reindex()
import mef as _mef
_HLIB = _mef.ModelLib([G_ + 'MISSIONS/multiplayer/sandstorm/models/sandstorm.res'])
_HV, _HF, _ = _mef.collision(_HLIB.index['740_01_1'])[0]   # mesh 0 = the detailed hull (the rotors are separate meshes)


def hull_spot(hid, toward, heights_m=(1.2, 1.35, 1.05), stand_m=1.0):
    """(owner 10-12) a C4 spot ON the Hind's fuselage side: cast at heights_m above the PAD (terrain; the Hind's origin
    lies 1.36 m below it) from beside the fuselage onto its own collision hull (the pads' outdoor graph nodes are too
    coarse for the kit's surface_spot). Fuselage = local y, width = local x. The standing spot needs 2 m of headroom
    (stub wings, rocket pods). -> (spot 6 cm off the hull, gamma facing the standing player, (standing x, y, z))"""
    P_ = np.array([m.arg(hid, 3), m.arg(hid, 4), m.arg(hid, 5)], float)
    R_ = navgen.rot(m.arg(hid, 6), m.arg(hid, 7), m.arg(hid, 8))
    W_ = _HV @ R_.T + P_
    tri = W_[_HF[:, :3].astype(int)]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]

    def cast(a_, b_):
        d_ = b_ - a_; L_ = np.linalg.norm(d_); d_ = d_ / L_
        pv = np.cross(d_, e2); det = np.einsum('ij,ij->i', e1, pv)
        ok = np.abs(det) > 1e-9; inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        tv = a_ - tri[:, 0]; u = np.einsum('ij,ij->i', tv, pv) * inv
        qv = np.cross(tv, e1); vv = (qv @ d_) * inv; tt = np.einsum('ij,ij->i', e2, qv) * inv
        hit = ok & (u >= 0) & (vv >= 0) & (u + vv <= 1) & (tt > 0) & (tt < L_)
        return (float(tt[hit].min()), d_) if hit.any() else (None, d_)

    best = None
    for height_m in heights_m:
        for side in (1.0, -1.0):
            for ly in np.arange(-12000.0, 6001.0, 1000.0):
                o_ = P_ + R_ @ np.array([side * 24000.0, ly, 0.0])
                gz = float(K.TERR.height(o_[0], o_[1]))
                a_ = np.array([o_[0], o_[1], gz + height_m * 4096.0])
                c_ = P_ + R_ @ np.array([0.0, ly, 0.0]); b_ = np.array([c_[0], c_[1], gz + height_m * 4096.0])
                t0, d_ = cast(a_, b_)
                if t0 is None:
                    continue
                surf = a_ + d_ * t0
                stand = surf - d_ * stand_m * 4096.0
                stand[2] = float(K.TERR.height(stand[0], stand[1]))
                up_, _ = cast(np.array([stand[0], stand[1], stand[2] + 0.1 * 4096.0]), np.array([stand[0], stand[1], stand[2] + 2.1 * 4096.0]))
                if up_ is not None:
                    continue                               # something of the Hind over the head
                spot_ = surf - d_ * 0.06 * 4096.0
                score = np.hypot(stand[0] - toward[0], stand[1] - toward[1]) + abs(ly + 3000.0) * 0.5
                if best is None or score < best[0]:
                    u_ = (stand[:2] - surf[:2]) / np.linalg.norm(stand[:2] - surf[:2])
                    best = (score, tuple(float(c) for c in spot_), math.atan2(-u_[0], u_[1]), tuple(float(c) for c in stand))
        if best:
            break
    assert best, ('no hull hit on Hind', hid)
    return best[1:]


HANGAR = (639500.0, 900800.0)
for k_, hid in enumerate(HINDS):
    spot, gam, fl = hull_spot(hid, HANGAR)
    print('Hind %d charge spot %s (floor %s)' % (hid, [round(c / 4096, 2) for c in spot], [round(c / 4096, 2) for c in fl]))
    cc = nid()                                             # the charge is gone with the helicopter
    m.add_child(LOGIC, T(cc, 'ConditionalContainer', 'SS Hind %d charge (gone with the Hind)' % hid,
                         '0 && !ExplodeObject_%d.isExploded && StatusMessage_%d.isSendt' % (hid, O3_ID), '', ''))   # (phase 2 11-03: no
    #  C4 on the helicopters any more - owner rule 8 'no blow up helicopters'; the decrypt cutscene sends Jones below instead)
    CHARGES[hid] = K.plant('C4 on Hind %d' % (k_ + 1), spot, gam, parent=cc)
    CHARGE_AT[hid] = spot
    CHARGE_FLOOR[hid] = (fl, math.atan2(-(spot[0] - fl[0]), spot[1] - fl[1]))
    assert 0.8 * 4096 < math.hypot(spot[0] - fl[0], spot[1] - fl[1]) < 1.3 * 4096
    # (owner 10-31: no glowing red guide dots - the originals don't hand-hold; the map computer marker stays)
# ---- owner 11-02: the EMP set piece in the bunker hall (replaces the Hind C4 objective). The ORIGINAL cargo container 331_01_1
# (ss_ctr_1 = its own mesh and textures with the door end opened: the two door leaves swung back against the sides, the inside
# faces added - tools in this builder, section 7) at the far end of the hall, the colonel's EMP missile on its cradle inside, the
# launch console at the open doors. Reaching the console trips the tamper system: a 90 s launch countdown; hack the console 4 s
# to pull the guidance chip, else the missile fires = mission fail. The chip pull rings the base alarm.
K.root = [lit(s_.args[0]) for s_ in m.stmts if isinstance(s_, Call) and s_.name == 'Task_New']
DYN_ROOT = K._dynamic_root()
# ---- v4: the launch control room = the NE annex room by hall B's west wall (rel x 100..107, y 6..18; door 2109/2110 from the hall):
# the launch console, the guidance chip on its panel. Reaching the console trips the tamper system: 90 s launch countdown; hack the
# console 4 s to pull the chip, else the big missile fires = mission fail. The chip pull wakes the base below (U_ALARM) + the alarm.
CONT_L = 0.0
_cr = (256.0, 207.2)                                       # (owner 11-04: the console against the window band, the missile beyond it)
CONT_P = V.U((_cr[0], _cr[1], SB.F))
CONT_G = math.pi                                           # set-piece frame: local +y = world -y (into the room)
_CCOS, _CSIN = math.cos(CONT_G), math.sin(CONT_G)
CW = lambda lx, ly, lz=0.0: (CONT_P[0] + (lx * _CCOS - ly * _CSIN) * 4096, CONT_P[1] + (lx * _CSIN + ly * _CCOS) * 4096, CONT_P[2] + lz * 4096)
FCC_P = CW(0.0, 0.0)
CAGE_PC = nid()                                            # (owner 11-04: the control station opens the cage round the missile; the chip is taken from the missile itself)
_cp = CW(0.0, 0.05, 0.91)
m.add_child(LOGIC, T(CAGE_PC, 'GenericTBA', 'SS launch console (opens the cage)', *_cp, 0.0, 0.0, CONT_G, '200_01_1', '200_01_1',
                     100.0, 0.0, 0.0, 0.0, 0.0, 0, 0, '', '', 0.0, 0.0, 0.0, False, '!GenericTBA_%d.isFinished' % CAGE_PC, 'hack_computer', 4.0,
                     'STATUSSCREEN:action_comput.spr', 'tba_hackcomp'))
CHIP = nid()
m.add_child(LOGIC, T(CHIP, 'GenericTBA', 'SS guidance chip (on the missile)', *V.U((SB.PIT_C[0] - 1.28, SB.PIT_C[1], SB.F + 1.3)), 0.0, 0.0, math.pi / 2, 'ss_chipa_1', 'ss_chipb_1',
                     100.0, 0.0, 0.0, 0.0, 0.0, 0, 0, '', '', 0.0, 0.0, 0.0, False, '1', 'turn_wheel', 5.0,
                     'STATUSSCREEN:a_turnwheel.spr', 'tba_turnwheel'))
# (owner 62: Jones works on something real: the originals' wheel 515_04_1 on the guidance bay, turn_wheel under his hands while he
#  turns it, the bay stands open after)
X.models('location3/LEVEL6', ['515_04_1'])
import ssbay                                               # (owner 85, 86: the bay and the use points, tools/ssbay.py behind SS_BAY)
ssbay.models(globals())
import ssboom; ssboom.models(globals())                    # (owner 96: explosive barrels / tanks / drums, tools/ssboom.py behind SS_BOOM)
_wh = V.U((SB.PIT_C[0] - 1.28 - 0.03, SB.PIT_C[1], SB.F + 1.3))
_wt = nid()                                                # (the clip has no wheel in it: the placed one stays under his hands and turns, three spokes, 40 degree steps)
m.add_child(LOGIC, T(_wt, 'LevelTimer', 'SS guidance bay wheel turns', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'GenericTBA_%d.isInUse' % CHIP,
                     'LevelTimer_%d.nTick > 0.75 * GAME_FREQUENCY || !GenericTBA_%d.isInUse' % (_wt, CHIP), False))
for _k, _w in enumerate(('LevelTimer_%d.nTick <= 0.25 * GAME_FREQUENCY' % _wt, 'LevelTimer_%d.nTick > 0.25 * GAME_FREQUENCY && LevelTimer_%d.nTick <= 0.5 * GAME_FREQUENCY' % (_wt, _wt),
                         'LevelTimer_%d.nTick > 0.5 * GAME_FREQUENCY' % _wt)):
    m.add_child(LOGIC, T(nid(), 'ConditionalContainer', 'SS guidance bay wheel %d' % _k, '!GenericTBA_%d.isFinished && %s' % (CHIP, _w), '', '',
                         children=[T(nid(), 'EditRigidObj', '', _wh[0], _wh[1], _wh[2] + 354.0, 0.0, _k * math.radians(40.0), math.pi / 2, '515_04_1', 5, False, False)]))
CHIPPED = 'GenericTBA_%d.isFinished' % CHIP
NEAR_PANEL = nid()
_np = V.U((256.0, 202.5, SB.F + 1.0))                     # (the room inside its door)
m.add_child(LOGIC, T(NEAR_PANEL, 'AreaActivate', 'SS at the launch console', *_np, 0.0, 0.0, 0.0, 20.0 * 4096, 11.0 * 4096, 3.0 * 4096,
                     'CRITERIA_HUMAN0'))
_atmos.ensure_decl(m, 'LevelTimer')
LAUNCH = nid()                                             # runs from the moment the cage opens; fires unless the chip is out
m.add_child(LOGIC, T(LAUNCH, 'LevelTimer', 'SS EMP launch countdown', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'GenericTBA_%d.isFinished || LevelTimer_%d.nTick > 0' % (CAGE_PC, LAUNCH),
                     '', False))
OPENED = 'LevelTimer_%d.nTick > 0' % LAUNCH
m.set(CHIP, 24, '!GenericTBA_%d.isFinished && GenericTBA_%d.isFinished' % (CHIP, CAGE_PC))
LAUNCH_S = 120
FIRED = 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY && !%s' % (LAUNCH, LAUNCH_S, CHIPPED)
# ---- v4: the machine room's diesel generator (L11 3435 'Generator' 337_11_1 + its start sound 11_gen_start): start it (4 s) -> the
# lights come on, the lift's call button works
X.models('location1/level1', ['337_11_1'])
print('v4 set piece: console + chip %d in the control room rel %s, trip area %d, launch timer %d' % (CHIP, _cr, NEAR_PANEL, LAUNCH))
# =========================================================== 8c. v4 FINALE (plan v4): the vehicle gate -> the truck tunnel -> the sand door ->
# Anya's satellite: two REINFORCEMENT helicopters landing beyond the train -> the run -> the guard van's rear platform -> outro: the
# train pulls away east (tools/srtrain.py cars on a rail.py spline; it departs only on the 'aboard' latch - Sirocco spike 11-03: a
# player put onto a moving train lands on the ground).
import srtrain as STR, rail
rail.ensure_decls(m)
# --- the vehicle blast gate (owner 11-04: 'does not look like a door'): the NEW roll-up leaf ss_bgate_1 in a slot of the hall's east wall,
# hazard jambs, the L36 door task's sounds; it rolls up 6.75 m behind the lintel, the truck tunnel starts behind it
X.models('location1/level1', ['360_16_1', '360_17_1'])
_src_gate = X._source('location3/LEVEL6')['byid'][3529][0]


def roll_gate(name, model, p_m, speed):
    d_ = _copy.deepcopy(_src_gate); i_ = nid(); d_.args[0] = v(i_); d_.args[2] = v(name)
    for k_ in range(3):
        d_.args[3 + k_] = v(p_m[k_] * 4096.0)
    # (rig dt2 11-04: a Door slides in its local x-y plane only, the z offset is ignored: the leaf is built lying down and turned up by alpha, local y = world up)
    d_.args[6] = v(0.0); d_.args[7] = v(SB.DOOR_SLIDE); d_.args[8] = v(0.0)
    d_.args[9] = v(math.pi / 2); d_.args[10] = v(0.0); d_.args[11] = v(0.0)
    d_.args[12] = v(model); d_.args[14] = v(speed)
    d_.args[24] = v('door_blast_cl'); d_.args[25] = v('door_blast_cl'); d_.args[26] = v('door_blast_move'); d_.args[27] = v('door_blast_open')   # (the map's own blast door, owner 11-04: 'fence sound')
    d_.args[15] = v(False); d_.args[18] = v('1'); d_.args[19] = v(''); d_.args[20] = v('0' if 'gateclose' not in DBG else '')   # (rig wb15: an open gate shut itself behind Jones; arg 20 = close rule)
    for c_ in [a_ for a_ in d_.args if isinstance(a_, Call)]:
        d_.args.remove(c_)
    m.add_child(4029, d_)
    return i_


GATE_FLOOR = SB.F
VGATE = roll_gate('SS vehicle blast gate', 'ss_bgate_1', (SB.GATE_X, (SB.GATE_Y0 + SB.GATE_Y1) / 2, SB.F), 0.5)
if SB.GUNROOM:
    GN.gates(globals())
GATE_PAD = nid()
_gpad, _gpg = V.U((SB.X1 - 0.13, SB.GATE_Y0 - 1.3, SB.F + 1.35)), math.pi / 2   # (owner 42: the code panel on the wall beside the gate)
CAGE_GATE = roll_gate('SS missile cage gate', 'ss_cgate_1', (SB.PIT[0], SB.PIT_C[1], SB.F), 1.0)
if GARRISON2:
    SHUTTER = roll_gate('SS ready room shutter', 'ss_shut_1', ((GR.SHUT[0] + GR.SHUT[1]) / 2, GR.SY1 + 0.25, SB.F), 1.2)
    m.set(SHUTTER, 11, math.pi / 2); m.set(SHUTTER, 7, GR.SHUT[2] + 0.1)
    SHUT_T = nid()                                         # (the reaction force: the shutter rolls up 12 s into the alert)
m.set(CAGE_GATE, 7, 3.45); m.set(CAGE_GATE, 19, 'Door_%d.isClosed && LevelTimer_%d.nTick > 1 * GAME_FREQUENCY' % (CAGE_GATE, LAUNCH))
# (S17: it rolls up 1 s after the console, inside the short shot of it (the 'SS_CG' cutscene below); the rule is on the launch clock, so a skipped shot opens it too)
m.add_child(LOGIC, T(GATE_PAD, 'GenericTBA', 'SS vehicle gate code pad', *_gpad, 0.0, 0.0, _gpg, '360_16_1', '360_17_1', 100.0, 0.0, 0.0, 0.0,
                     0.0, 0, 0, '', '', 0.0, 0.0, 0.0, False, '!GenericTBA_%d.isFinished && %s' % (GATE_PAD, CHIPPED),
                     'tba_hack_code_pad', 4.0, 'STATUSSCREEN:a_codepad.spr', 'tba_codepad'))
m.set(VGATE, 19, 'Door_%d.isClosed && GenericTBA_%d.isFinished' % (VGATE, GATE_PAD))
GATE_OPEN = 'GenericTBA_%d.isFinished' % GATE_PAD
print('v5 finale: vehicle gate %d, code pad %d' % (VGATE, GATE_PAD))
# --- the train (tools/srtrain.py: 6 NEW cars on the ORIGINAL L12 track 417_01_1) waiting on the east plain, heading EAST; the guard
# van (rear) on the detailed ground (x < 404 m). It leaves only after the hop-on (outro).
TR_LINE = rail.Line([(372.0, TR_Y), (420.0, TR_Y), (470.0, TR_Y), (520.0, TR_Y), (570.0, TR_Y), (620.0, TR_Y)], RAIL_Z)
if OUTRO2:
    _SO.use_consist(); _SO.prepare(globals())
STR.add_textures(_VLIB); STR.add_models(_VLIB)
for _tn, _c, _sd in (('sr_ochre', (0.62, 0.45, 0.25), 41), ('sr_olive', (0.32, 0.31, 0.20), 42), ('sr_rust', (0.45, 0.21, 0.14), 43)):
    _VLIB.texture(_tn, (lambda c_, s_: (lambda: SB.tex_car(c_, s_)))(_c, _sd))
RAILC = nid()
m.add_child(BK_ST, T(RAILC, 'Container', 'SS the railway', False))
TR_SPLINE, _sp_t = rail.spline_task(nid, TR_LINE, 'SS the railway (L12 track, darkened)', models=['ss_rail_1'] * len(TR_LINE.waypoints()))
m.add_child(RAILC, _sp_t)
m.add_child(TR_SPLINE, T(nid(), 'LightmapInfo', '', 150, 0.0, 0.0, 0.0, ''))
X.models('location1/level2', [rail.TRACK])
TR_S = 8.0 + sum(STR.LENGTH.values()) + 2 * STR.PLATE * len(STR.CONSIST)    # the loco's front (m along the line)
# (rv1/rv2 11-04, 'the train is not on the railway': a native Train that has not moved stands at yaw 0, ACROSS an east-west line, whatever settles it.
#  So the cars are EditRigidObj at the line's yaw, each on a cine.spline path for the departure - the report's 'robust' recipe, work/inv/train/report.md)
TR_IDS = []
_trg = TR_LINE.gamma(TR_S)
TRAINC = nid()                                             # (owner 11-04: no train on the map from the start; it pulls in while Jones is underground)
m.add_child(LOGIC, T(TRAINC, 'ConditionalContainer', 'SS the train (after the gate)', 'GenericTBA_%d.isFinished' % GATE_PAD, '', ''))
for _k, _nm in enumerate(STR.CONSIST):
    _i = nid(); TR_IDS.append(_i)
    m.add_child(TRAINC, T(_i, 'EditRigidObj', 'SS supply train car %d (%s)' % (_k + 1, _nm), *STR.local_to_world(TR_LINE, TR_S, _k, (0.0, 0.0, 0.0)),
                         0.0, 0.0, _trg, _nm, 5, False, False))
TRAIN = TR_IDS[0]
HOP_P = STR.local_to_world(TR_LINE, TR_S, 5, (0.0, -STR.LENGTH[STR.VAN] / 2 - 2.0, 0.0))   # 2 m behind the van's rear balcony
print('v4 train: rail z %.2f m (ground %.1f..%.1f), front s %.1f m, hop-on spot (%.1f, %.1f) m' % (
    RAIL_Z, min(_tg), max(_tg), TR_S, HOP_P[0] / 4096, HOP_P[1] / 4096))
# --- the sand door (owner 11-04: no teleport): the end of the truck tunnel, a roll-up gate in a concrete headwall in the hillside, its code pad
# inside; the player walks it all. The terrain is cut from the door plane back to where the hill covers the roof, narrower than the shell.
SD_X, SD_Y, SD_G = float(TUN.door[0]), float(TUN.door[1]), TUN.door_z
SAND_DOOR = roll_gate('SS the sand door', 'ss_sgate_1', (SD_X + 0.6, SD_Y, SD_G), 1.4)
m.set(SAND_DOOR, 7, -6.86)
SAND_PAD = nid()
_spad = V.U((SD_X - 3.0, SD_Y - SB.TW + 0.13, SD_G + 1.25))
m.add_child(LOGIC, T(SAND_PAD, 'GenericTBA', 'SS sand door code pad', *_spad, 0.0, 0.0, 0.0, '360_16_1', '360_17_1', 100.0, 0.0, 0.0, 0.0,
                     0.0, 0, 0, '', '', 0.0, 0.0, 0.0, False, '!GenericTBA_%d.isFinished && %s' % (SAND_PAD, GATE_OPEN),
                     'tba_hack_code_pad', 4.0, 'STATUSSCREEN:a_codepad.spr', 'tba_codepad'))
m.set(SAND_DOOR, 19, 'Door_%d.isClosed && GenericTBA_%d.isFinished' % (SAND_DOOR, SAND_PAD))
_sh = SB.hole(TUN, _bh, 0, 0, 0)
_shx, _shy, _shw, _shh, _shc = V.hole_rect(_CELL, _TB.maps[0][1] / 4096.0, _TB.maps[0][2] / 4096.0, (_sh[0], SD_Y - 4.55, _sh[2], SD_Y + 4.55),
                                           (_sh[0] - 1.3, SD_Y - 5.95, _sh[2] + 1.3, SD_Y + 5.95))
m.add_child(m.find('Terrain')[0], T(nid(), 'DiscardTask', 'SS sand door cut', _shx * 4096.0, _shy * 4096.0, (SD_G + 3.0) * 4096, _shw, _shh))
print('v5 sand door: door %d at (%.1f, %.1f) m floor %.1f, pad %d, terrain cut %s' % (SAND_DOOR, SD_X, SD_Y, SD_G, SAND_PAD, [round(c_, 1) for c_ in _shc]))
HOPON = nid()
m.add_child(LOGIC, T(HOPON, 'AreaActivate', 'SS at the guard van platform', *HOP_P, 0.0, 0.0, 0.0, 4.0 * 4096, 5.0 * 4096, 3.0 * 4096,
                     'CRITERIA_HUMAN0'))
BOTH_PLANTED = ' && '.join('GenericTBA_%d.isFinished' % CHARGES[h] for h in HINDS)
ONE_PLANTED = '(%s)' % ' || '.join('GenericTBA_%d.isFinished' % CHARGES[h] for h in HINDS)
_atmos.ensure_decl(m, 'LevelTimer'); _atmos.ensure_decl(m, 'MissionTimer')
ARMED = nid()                                              # (latched 0 -> 1 once both are planted: the charges' TBAs live in
m.add_child(LOGIC, T(ARMED, 'EditVariable', 'SS both charges armed', 0.0, 0.0, 0.0, 0,   # containers that vanish with
                     'EditVariable_%d.nValue == 0 && %s' % (ARMED, BOTH_PLANTED), ''))   # (v4 11-03: armed again)
IS_ARMED = 'EditVariable_%d.nValue == 1' % ARMED
FUSE = nid()
m.add_child(LOGIC, T(FUSE, 'LevelTimer', 'SS Hind charges fuse', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, IS_ARMED, '', False))
CLOCK = nid()
m.add_child(LOGIC, T(nid(), 'ConditionalContainer', 'SS charges clock (shown while it runs)',   # (owner 10-19: a finished clock
                     '!(LevelTimer_%d.nTick > %d * GAME_FREQUENCY)' % (FUSE, FUSE_S), '', '',      #  stayed on screen at 00:00)
                     children=[T(CLOCK, 'MissionTimer', '', '0', '', FUSE_S)]))   # (v4: never shown - one HUD clock only;
#  the fuse counts down as messages instead, like the launch countdown)
HBOOM = 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (FUSE, FUSE_S)
for hid in HINDS:
    m.set(hid, 18, HBOOM)
m.set(2949, 3, 'ExplodeObject_3901.isExploded')            # MP chopper smoke columns
m.set(2946, 3, 'ExplodeObject_3904.isExploded')
m.set(3139, 18, 'ExplodeObject_3901.isExploded')           # MP "end effect" blasts = secondary explosions
m.set(3140, 18, 'ExplodeObject_3904.isExploded')
for b in (3139, 3140):                                     # MP values: radius 20 m + falloff 35 m, damage 10 = killed the player
    m.set(b, 12, 2.0); m.set(b, 13, 1.0); m.set(b, 14, 0.0)  # fireballs only, no damage
# owner 10-12: 'not just fire on it, that looks childish - make it feel real': the burning bonfire on an intact Hind
# goes; the Hind is replaced by a wreck (WRECK_MODEL) with a thin black smoke column rising out of it
WRECK_MODEL = os.environ.get('SS_WRECK', 'w740_01_1')       # (10-12: tools/wreck.py - a real wreck mesh; b740_01_1 = the old burnt copy)
for cc_ in (2949, 2946):
    for c_ in [c_ for c_ in L[cc_].args if isinstance(c_, Call)]:
        if float(lit(c_.args[9])) < 3.5:                   # Smoke arg 9: 3 = the flames (2947), 4 = the smoke column (2948)
            print('Hind wreck: flames %d removed (smoke column kept)' % lit(c_.args[0]))
            m.remove(lit(c_.args[0]))
m.reindex()
import wreck as _wreck_mod
for hid in HINDS:
    if WRECK_MODEL == 'b740_01_1':
        K.heli_wreck(hid, 'Hind %d' % hid, model=WRECK_MODEL, sink_m=0.6)
    else:                                                  # (the crash pose is in the mesh: exactly the intact one's place)
        _wreck_mod.heli_wreck(K, hid, 'Hind %d' % hid, model=WRECK_MODEL)
m.reindex()
# 10-17 owner: 'fires that never stop' - the Hind smoke columns and the 5 MP fuel barrels ('Explode object 1-5',
# 406_50_1, shootable, damaging flames) burned for the rest of the mission: they burn out now (Kit.burn_out, generate
# factor -> 0 on a burn clock; flames ~50 s, smoke ~110 s; the Hind smoke stays on for the outro over the base)
import re
K.DEBUG = DEBUG
HIND_BURN = []
for hid_, cc_ in ((3901, 2949), (3904, 2946)):
    HIND_BURN += [K.burn_out([lit(c_.args[0]) for c_ in m.byid[cc_].args if isinstance(c_, Call) and lit(c_.args[1]) == "Smoke"],
               'ExplodeObject_%d.isExploded' % hid_, 'Hind %d' % hid_)]
for cc_ in (3191, 3187, 3183, 3896, 3145):
    _cond = str(lit(m.byid[cc_].args[3]))
    assert re.fullmatch(r'ExplodeObject_\d+\.isExploded', _cond), (cc_, _cond)
    K.burn_out([lit(c_.args[0]) for c_ in m.byid[cc_].args if isinstance(c_, Call) and lit(c_.args[1]) == "Smoke"],
               _cond, 'fuel barrel %d' % cc_)
K.burn_test_variant()                                      # SS_DEBUG 'burntest=<s>': all of them start at LevelFlow s

# O6: escape through the north tunnel once the airbase targets are down
EXTRACT = nid()
m.add_child(LOGIC, T(EXTRACT, 'AreaActivate', 'SS extraction', 640000.0, 1545000.0, 61000.0, 0.0, 0.0, 0.0,
                     150000.0, 90000.0, 60000.0, 'CRITERIA_HUMAN0'))
EXTRACT_WIDE = nid()                                       # everything north of the tunnel's north door (3147, y 1476093)
m.add_child(LOGIC, T(EXTRACT_WIDE, 'AreaActivate', 'SS extraction (whole north valley)', 600000.0, 1700000.0, 60000.0,
                     0.0, 0.0, 0.0, 450000.0, 215000.0, 150000.0, 'CRITERIA_HUMAN0'))

# =========================================================== 5. security: power kills the south cameras, the
# camera-control computer kills the airbase cameras; any camera that sees Jones raises the base alarm
SOUTH_CAMS = [c for c in m.find('SCamera') if m.arg(c, 4) < 600000.0 and m.arg(c, 5) > -60000.0]
SEWER_CAMS = [c for c in m.find('SCamera') if m.arg(c, 5) <= -60000.0]
NORTH_CAMS = [c for c in m.find('SCamera') if m.arg(c, 4) >= 600000.0]
for c in SOUTH_CAMS + SEWER_CAMS:
    m.set(c, 20, '!(%s) && EditVariable_1500.nValue == 0' % POWER_OFF)
for c in NORTH_CAMS:                                       # (owner crash 10-11: no camera may re-detect Jones during an alarm -
    m.set(c, 20, '!GenericTBA_%d.isFinished && EditVariable_1500.nValue == 0' % SECURITY_PC)   # it calls every soldier at once)
CAM_KINDS = _cams.soften(m, SOUTH_CAMS + SEWER_CAMS + NORTH_CAMS)   # owner 10-12: most cameras can be shot out
for _c, _k in CAM_KINDS.items():                           # (the soft set is beige: the grey head on all, a bullet still swaps it for the broken one, rig cb1)
    if _k == 'soft':
        m.set(_c, 7, '313_07_1'); m.set(_c, 11, '313_06_1'); m.set(_c, 12, '335_03_1')
print('cameras: %d soft, %d metal' % (sum(k == 'soft' for k in CAM_KINDS.values()), sum(k == 'metal' for k in CAM_KINDS.values())))
m.set(1501, 7, '0'); m.set(1501, 8, '0')                   # MP "security offline" timer unused
m.set(1500, 8, 'EditVariable_1500.nValue == 1 && LevelTimer_1400.nTick > 60 * GAME_FREQUENCY')   # alarm lasts 60 s
m.set(1400, 10, 'EditVariable_1500.nValue == 0')
ALARM = nid()
m.add_child(LOGIC, T(ALARM, 'AlarmControl', 'SS base alarm', 450000.0, 600000.0, 150000.0, 0.0, 0.0, 0.0, '', '', 1.0, 0.5, 0.5, 1.0,
                     0.0, 5, 4, '', 'explo_02_m', '1', 4.0, 'tba_hackcomp', 'EditVariable_1500.nValue == 1', 'EditVariable_1500.nValue == 1'))

# =========================================================== 6. enemies (~50)
C2N, C2T = 'HUMANAI_TYPE_C2_NORMAL_SOLDIER', 'HUMANAI_TYPE_C2_TOUGH_SOLDIER'
C3N, C3T = 'HUMANAI_TYPE_C3_NORMAL_SOLDIER', 'HUMANAI_TYPE_C3_TOUGH_SOLDIER'
# owner 11-02: Libya -> IRAQ. The asset library's 'ar' faction (tools/alskins.py): alarm1_1 3-colour desert + tan beret,
# alarm2_1 olive jacket + red-white shemagh, alarmo_1 olive officer + red beret (LOD rows below)
LES = ['alarm1_1', 'alarm2_1', 'alsea2_1', 'alarm1_1', 'alalpc_1']
CSF = ['alarm1_1', 'alplas_1', 'alsea2_1', 'alarm2_1']
SQ_PARENT = nid()
m.add_child(4087, T(SQ_PARENT, 'Container', 'SS enemies', False))
TAKEN = [START]


def free_run(p, gam, cap=25.0):
    """(S2 owner 11-15 'guards stand facing walls like robots') metres of floor a man at p (units, feet) has straight ahead along gamma:
    0.25 m steps over the nav grid, each step at most 0.45 m up or down, head room >= 1.7 m; stops at a wall, a table, bags or an edge"""
    x, y, zc = p
    dx, dy = -math.sin(gam), math.cos(gam)
    d = 0.0
    while d < cap:
        j = nv.surface_at(x + dx * (d + 0.25) * 4096.0, y + dy * (d + 0.25) * 4096.0, zc, maxdz=0.45 * 4096.0, alive_only=False, radius=0)
        if j < 0 or NF['ceil'][j] - NF['z'][j] < 1.7 * 4096.0:
            break
        zc = NF['z'][j]
        d += 0.25
    return d


def look_node(g, p, mate=None):
    """(S2) the reason a standing man faces where he faces -> (graph g node id or None, gamma): his mate > a door within 8 m he can see >
    the graph node 6-25 m away on the longest free floor run (never a bearing with under 4 m of floor). Draws nothing from m.rng"""
    bear = lambda q: math.atan2(-(q[0] - p[0]), q[1] - p[1])
    if mate is not None:
        return mate['id'], bear(mate['pos'])
    near = [(math.hypot(q['pos'][0] - p[0], q['pos'][1] - p[1]) / 4096.0, q) for q in GRAPHS[g] if abs(q['pos'][2] - p[2]) < 1.5 * 4096.0]
    doors = sorted((d_, q['id'], q) for d_, q in near if q['crit'] and 2.0 <= d_ <= 8.0)
    for d_, _i, q in doors:
        if free_run(p, bear(q['pos']), cap=d_) >= d_ - 1.0:
            return q['id'], bear(q['pos'])
    runs = [free_run(p, k_ * math.pi / 8.0) for k_ in range(16)]        # 16 bearings, then the node that lies on the best of them
    best = None
    for d_, q in near:
        if 6.0 <= d_ <= 25.0:
            b_ = bear(q['pos'])
            fr = runs[int(round(b_ / (math.pi / 8.0))) % 16]
            if fr >= min(d_, 4.0) and (best is None or (fr, -abs(d_ - 12.0)) > best[0]):
                best = ((fr, -abs(d_ - 12.0)), q)
    if best is not None:
        fr = free_run(p, bear(best[1]['pos']))
        if fr >= 4.0:
            return best[1]['id'], bear(best[1]['pos'])
    k_ = max(range(16), key=lambda i_: runs[i_])                      # (no node on a free line: the freest bearing, no look node)
    return None, k_ * math.pi / 8.0


def pick(g, n, center, radius, zlo=-1e9, zhi=1e9, where='any', spacing=7000.0):
    """n graph-g nodes (never door nodes) near center; widens the search a little if the area is sparse"""
    for r_mul, s_mul in ((1.0, 1.0), (1.4, 1.0), (1.4, 0.7), (2.0, 0.7)):
        cand = [q for q in GRAPHS[g] if not q['crit'] and zlo <= q['pos'][2] <= zhi
                and math.hypot(q['pos'][0] - center[0], q['pos'][1] - center[1]) <= radius * r_mul
                and (where == 'any' or (where == 'in') == (q['terrain'] == 0))]
        cand.sort(key=lambda q: q['pos'])
        m.rng.shuffle(cand)
        got = []
        for q in cand:
            p = q['pos']
            if all(math.dist(p, o) >= spacing * s_mul for o in got + TAKEN):
                got.append(p)
                if len(got) == n:
                    TAKEN.extend(got)
                    return got
    raise AssertionError('squad at %s: wanted %d nodes, found %d of %d candidates' % (center, n, len(got), len(cand)))


ENEMY_COUNT = [0]
SQUAD_IDS = {}


def squad(key, g, center, radius, loadouts, ai_type, skins, zlo=-1e9, zhi=1e9, where='any', sqtype='AIType_Offensive',
          alarm=True, ai='generic', spacing=7000.0, patrol=0.5, talk=False, calm_var='EditVariable_1500.nValue', sleep=(False, False)):
    """owner 10-31: original-style guards (aiscript.NORMAL = the engine defaults 92 % of the originals use, not HARD);
    about half walk a short PatrolPath (Kit.patrol_route), the rest stand their post and look around; snipers hold."""
    if talk:                                                # (owner 11-01: interiors alive - two men talking face to face)
        return talk_pair(key, g, center, radius, loadouts, ai_type, skins, zlo, zhi, alarm, where if where in ('in', 'out') else 'in', calm_var, sleep)
    pts = pick(g, len(loadouts), center, radius, zlo, zhi, where, spacing)
    mem, pair = [], None
    for k, (p, w) in enumerate(zip(pts, loadouts)):
        d = dict(pos=p, model=skins[k % len(skins)], weapons=w, ai_type=ai_type, graph=g)
        if 'DRAGUNOV' in w or ai == 'hold':
            d['ai'] = 'hold'
            d['gamma'] = round(look_node(g, p)[1], 6)      # (S2: snipers had a random heading, one looked at a wall 3 m away)
        else:
            # (owner 11-01: patrols in pairs) the 2nd man of a squad walks his mate's PatrolPath with him
            path = pair if pair else (K.patrol_route(g, p) if m.rng.random() < patrol else None)
            pair = path if k == 0 else None
            if not path:
                if g in APPROACH:                          # (the old compass bearing's draw is still taken: every later random pick stays where it was)
                    m.rng.uniform(-0.5, 0.5)
                ln, gm = look_node(g, p)                   # (S2 owner 11-15: he faces a door, a lane, a long view: never a wall)
                d['gamma'] = round(gm, 6)
                LOOKS.append((key, k, p, ln, gm))
            d['ai'] = _aiscript.patrol(path, _aiscript.NORMAL) if path else life_sentry(w, PATROLS[0] + ENEMY_COUNT[0] + k, calm_var, look=ln)
            PATROLS[0] += bool(path)
        mem.append(d)
    sid, hids = m.squad(SQ_PARENT, key, sqtype, mem, alarm_switch=-1, alarm_control=ALARM if alarm else -1)
    SQUAD_IDS[key] = (sid, hids)
    ENEMY_COUNT[0] += len(hids)
    return hids


def talk_pair(key, g, center, radius, loadouts, ai_type, skins, zlo, zhi, alarm, where='in', calm_var='EditVariable_1500.nValue', sleep=(False, False)):
    """two off-duty men indoors on two LINKED graph nodes 1.2-3.6 m apart (a graph link = a clear walk = no wall between),
    facing each other; the originals' life recipe (L21 Priboi / L24 575): SetStandActionAnimation('stand_talk1' / 'stand_talk2')
    + AIAction_PlayAnimation(1, 0) on every calm IDLE (11-01: without PlayAnimation they stood frozen); in the alarm their
    squad's hunt takes over (alarmai.Hunt zones). where = 'in' (off-duty indoors) | 'out' (a gate post pair)"""
    byid = {q['id']: q for q in GRAPHS[g]}
    nb = {}
    for a_, b_ in GEDGES[g]:
        nb.setdefault(a_, []).append(b_); nb.setdefault(b_, []).append(a_)
    T0 = 0 if where == 'in' else 1
    cand = sorted((q for q in GRAPHS[g] if not q['crit'] and q['terrain'] == T0 and zlo <= q['pos'][2] <= zhi
                   and math.hypot(q['pos'][0] - center[0], q['pos'][1] - center[1]) <= radius
                   and all(math.dist(q['pos'], o) >= 4000.0 for o in TAKEN)), key=lambda q: q['pos'])
    m.rng.shuffle(cand)
    for q in cand:
        for j in nb.get(q['id'], ()):
            r_ = byid[j]
            d_ = math.hypot(r_['pos'][0] - q['pos'][0], r_['pos'][1] - q['pos'][1])
            if where == 'out' and not r_['crit'] and d_ >= 2.4 * 4096:   # (outdoor nodes are sparse: the mate stands 2.4 m
                f_ = 2.4 * 4096 / d_                                        #  along a walkable link, on the ground; both hold)
                px_, py_ = q['pos'][0] + (r_['pos'][0] - q['pos'][0]) * f_, q['pos'][1] + (r_['pos'][1] - q['pos'][1]) * f_
                pz_ = float(K.TERR.height(px_, py_))
                if abs(pz_ - q['pos'][2]) < 0.4 * 4096 and all(math.dist((px_, py_, pz_), o) >= 4000.0 for o in TAKEN):
                    r_ = dict(id=j, pos=(px_, py_, pz_), look=q['id'])
                    break
                continue
            if where == 'in' and not r_['crit'] and r_['terrain'] == T0 and 1.2 * 4096 <= d_ <= 3.6 * 4096 and abs(r_['pos'][2] - q['pos'][2]) < 0.4 * 4096                     and all(math.dist(r_['pos'], o) >= 4000.0 for o in TAKEN):     # (review 11-01: the mate is spaced too)
                break
        else:
            continue
        break
    else:
        raise AssertionError('talk pair %s: no two %s spots 1.2-3.6 m apart' % (key, where))
    ev = alarmai.C('AIFunction_GetCurrentEventType')
    mem = []
    for k, (me, mate, w) in enumerate(((q, r_, loadouts[0]), (r_, q, loadouts[1]))):
        clip = 'jones_sits_against_wall' if sleep[k] else 'stand_talk1' if k == 0 else 'stand_talk2'
        if where == 'out':                                  # outdoor pair: no post node for the mate - both face each other's
            look_ = r_['id'] if k == 0 else q['id']         #  side (the first man the link the mate stands on) and hold
            calm = [Call('AIFunction_SetStandActionAnimation', [Str(clip)])] +                 ([alarmai.C('AIAction_WalkToNode', q['id'], 1)] if k == 0 else []) +                 [alarmai.C('AIAction_LookAtNode', look_, 1), alarmai.C('AIAction_PlayAnimation', 1, 0)]   # (review: back to his post)
        else:
            calm = [Call('AIFunction_SetStandActionAnimation', [Str(clip)]), alarmai.C('AIAction_WalkToNode', me['id'], 1),
                    alarmai.C('AIAction_LookAtNode', mate['id'], 1), alarmai.C('AIAction_PlayAnimation', 1, 0)]
        busy = [alarmai.C('AIAction_Idle', 'AIACTIONFLAG_NONE')]   # (review 11-01: in the alarm the squad's hunt leads, like the patrollers)
        sc = alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), [alarmai.C('AIFunction_DefaultHandler')],
                                            [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                        [alarmai.If(alarmai.EQ(calm_var, 1), busy, calm),
                                                         alarmai.C('AIFunction_PassEventOnToSquad')],
                                                        [alarmai.C('AIFunction_DefaultHandler')])])])
        gam = math.atan2(-(mate['pos'][0] - me['pos'][0]), mate['pos'][1] - me['pos'][1])
        mem.append(dict(pos=me['pos'], model=skins[k % len(skins)], weapons=w, ai_type=ai_type, graph=g, ai=sc, gamma=round(gam, 6)))
        TAKEN.append(me['pos'])
    sid, hids = m.squad(SQ_PARENT, key, 'AIType_Offensive', mem, alarm_switch=-1, alarm_control=ALARM if alarm else -1)
    SQUAD_IDS[key] = (sid, hids)
    ENEMY_COUNT[0] += len(hids)
    TALKERS.append(key)
    print('talk pair %s at %s / %s' % (key, [round(c) for c in q['pos']], [round(c) for c in r_['pos']]))
    return hids


import alarmai
import aiscript as _aiscript
TALKERS = []
LIFE_RIFLE = ('stand_clean_weapon', 'stand_inspect_weapon_rifle', 'stand_streatch_neck', 'stand_look_about', 'stand_bugged_by_fly')
LIFE_PISTOL = ('stand_clean_weapon_pistol', 'stand_streatch_neck_pistol', 'stand_scratch_ass_pistol', 'stand_wipe_nose_pistol')


LOOKS = []                                                 # (S2: (squad, k, pos, look node, gamma) of every standing man squad() faced, for the build log and ssface)


def life_sentry(weapons, k, calm_var='EditVariable_1500.nValue', look=None):
    """a standing guard. S3/S4 owner 11-15 ('always 100 % alerted, aiming, sweeping left / right'; 'they teleport from one animation into
    another'): the old calm loop was a fidget clip chained to an aimed 180 degree LookAround on every idle (45 men; the originals: 4.8 %).
    Now the commonest original recipe (L11 501: 53 % of the originals' men stand in the engine idle): turn to his look node, then
    AIAction_Idle(1) - the engine's own relaxed stand, gun low, its own fidgets, blended by the engine (rig take T0 11-15:
    work/films/proof_11-15/S4). LookAround only in the alarm branch. weapons / k kept for the callers."""
    ev = alarmai.C('AIFunction_GetCurrentEventType')
    look_ = alarmai.C('AIAction_LookAround', 'AILOOKAROUND_PATTERN_180_CLOCKWISE', 1)
    calm = ([alarmai.C('AIAction_LookAtNode', look, 1)] if look else []) + [alarmai.C('AIAction_Idle', 1)]
    look = look_
    return alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), [alarmai.C('AIFunction_DefaultHandler')],
                                          [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                      [alarmai.If(alarmai.EQ(calm_var, 1), [look], calm),
                                                       alarmai.C('AIFunction_PassEventOnToSquad')],
                                                      [alarmai.C('AIFunction_DefaultHandler')])])])


def arrive_ai(cnt_var, fight, look, after=None, acc=None):
    """R-ARRIVE (S16 owner 11-15 'why would they come with cars, get out, and not know what is happening?'): the originals' L15 'Far Side Car'
    men (location1/LEVEL5/ai/3728): they see 120 m from the first tick and their FIRST idle is a run to a fight node, no wait. For the first
    8 s after his container opened (cnt_var < 240): run to `fight`, turn to `look`, stand in combat idle (weapon up); then `after`
    (default: the squad's hunt). ENEMYDETECTION calls backup at 45 m. Eyes widened only for these men (they came because of an intruder)"""
    ev = alarmai.C('AIFunction_GetCurrentEventType')
    eyes = [alarmai.C('AIFunction_DefaultHandler'),
            alarmai.C('AIFunction_SetIdleViewCone1Alpha', 60), alarmai.C('AIFunction_SetIdleViewCone1Length', 120),
            alarmai.C('AIFunction_SetIdleViewCone2Alpha', 100), alarmai.C('AIFunction_SetIdleViewCone2Length', 40),
            alarmai.C('AIFunction_SetInvestigateViewCone1Alpha', 45), alarmai.C('AIFunction_SetInvestigateViewCone1Length', 150),
            alarmai.C('AIFunction_SetCombatViewCone1Alpha', 60), alarmai.C('AIFunction_SetCombatViewCone1Length', 150)] + \
           ([alarmai.C('AIFunction_SetMinRangeAccuracy', acc)] if acc else [])
    go = [alarmai.C('AIAction_RunToNode', fight, 1), alarmai.C('AIAction_LookAtNode', look, 1), alarmai.C('AIAction_CombatIdle', 'AIACTIONFLAG_NONE')]
    later = after if after is not None else [alarmai.C('AIAction_Idle', 'AIACTIONFLAG_NONE'), alarmai.C('AIFunction_PassEventOnToSquad')]
    return alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), eyes,
                                          [alarmai.If(alarmai.EQ(ev, 'AIEVENT_ENEMYDETECTION'), [alarmai.C('AIAction_CallForBackup', 45), alarmai.C('AIFunction_DefaultHandler')],
                                                      [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                                  [alarmai.If(alarmai.Bin('<', alarmai.E(cnt_var), alarmai.E(240)), go, later)],
                                                                  [alarmai.C('AIFunction_DefaultHandler')])])])])


def arrive_counter(cc, name):
    """the 'SS arrive ticks' clock of a run-time container: counts game ticks from its opening up to 240 (8 s); R-ARRIVE reads it"""
    v_ = nid()
    m.add_child(LOGIC, T(v_, 'EditVariable', 'SS arrive ticks %s' % name, 0.0, 0.0, 0.0, 0, 'ConditionalContainer_%d.isRun && EditVariable_%d.nValue < 240' % (cc, v_), ''))
    return 'EditVariable_%d.nValue' % v_
PATROLS = [0]
APPROACH ={1: START[:2], 2: (381673.0, 843439.0), 4: (538624.0, 1476198.0)}   # spawn / sewer exit / tunnel north door
K.GRAPHS, K.GEDGES, K.START = GRAPHS, GEDGES, START
K.root = [lit(s_.args[0]) for s_ in m.stmts if isinstance(s_, Call) and s_.name == 'Task_New']
AK, AKG, MG, SG, SMG, SN, RPG = ['AK47'], ['AK47', 'GRENADE'], ['MINIMI'], ['SPAS12'], ['UZI'], ['DRAGUNOV'], ['RPG7']
MAC, T64, HK, JH = ['MAC10'], ['TYPE64SMG'], ['HK104'], ['JACKHAMMER']   # (owner 28)
# Owner 10-10: 103 was far too many -> ~50. Owner 10-31 (after the SHOBI rework's 56 HARD guards in one base): a MIDDLE
# density like the originals (19 SP levels: 28-68 soldiers, median 44; L24 airfield 40, L25 52) -> 46, normal soldiers,
# four snipers on the far side of each area (gatehouse loft, hill house roof, admin top floor, north admin over the
# tunnel road), mixed guns (AK / AK+grenades / Minimi / SPAS / Uzi) and mixed les/csf skins, inside and outside.
LESM = ['alarm1_1', 'alarm2_1', 'alsea2_1', 'alalpc_1']
CSFM = ['alarm1_1', 'alplas_1', 'alarm2_1', 'alsea2_1', 'alplas_1']
# --- south compound (graph 1): regular desert troops
import weather as _weather_h
_weather_h.hearing(0.4)                                    # (owner 11-04: one shot must not bring the whole army)
squad('S landing zone pickets', 1, (345000.0, 30000.0), 45000.0, [AK], C2N, LES, zhi=90000.0, where='out')
squad('S south gate', 1, (332000.0, 236000.0), 45000.0, [AKG, AK], C2N, LESM, zlo=-4000.0, zhi=8000.0, where='out', talk=True)
squad('S gatehouse loft', 1, (332300.0, 252900.0), 16000.0, [SN], C2N, LES, zlo=18000.0, zhi=27000.0, alarm=False, sqtype='AIType_Defensive')
squad('S generator A yard', 1, (402650.0, 410186.0), 32000.0, [T64, MG], C2N, LESM, zlo=-4000.0, zhi=16000.0)
squad('S tunnel corridor', 1, (493400.0, 401400.0), 30000.0, [JH, MAC], C2N, LES, zlo=-2000.0, zhi=3000.0, where='in')
squad('S hill house ground', 1, (484900.0, 337500.0), 26000.0, [SG], C2N, LES, zlo=54000.0, zhi=56500.0)
squad('S hill house upstairs', 1, (484900.0, 337500.0), 30000.0, [AK], C2N, LESM, zlo=67000.0, zhi=84000.0, where='in')
squad('S hill house roof', 5, (484900.0, 337500.0), 35000.0, [SN], C2N, LES, zlo=95000.0, zhi=98000.0, alarm=False, sqtype='AIType_Defensive')
squad('S storage house', 1, (645000.0, 399200.0), 32000.0, [AKG, AK], C2N, LES, zlo=-2000.0, zhi=3000.0, where='in')
squad('S generator B house', 1, (639300.0, 295200.0), 24000.0, [AK, SG], C2N, LESM, zlo=27000.0, zhi=33000.0, where='in')
squad('S garage and east gate', 1, (820000.0, 240000.0), 80000.0, [AKG], C2N, LES, zlo=-6000.0, zhi=12000.0)
squad('S large house', LOBBY_G if RQ7 else 1, (318900.0, 481300.0), 26000.0, [AK, SG], C2N, LESM, zlo=0.0, zhi=30000.0, where='in', talk=True)
squad('S sewer entrance guards', 1, (299000.0, 530000.0), 30000.0, [AKG, AK], C2N, LES, zlo=-6000.0, zhi=8000.0, where='out', talk=True)
# --- the sewer (graph 3): close quarters
squad('W sewer south', 3, (350000.0, 330000.0), 120000.0, [MAC], C2N, LES, spacing=15000.0)
squad('W sewer north', 3, (380000.0, 740000.0), 90000.0, [SG], C2N, LES, spacing=15000.0)
# --- the airbase (graph 2): better armed, still normal soldiers
import weather as _weather_h
_weather_h.hearing(0.12)                                   # (owner 11-04: they must not hear Jones come up the sewer stairs, nor at the server room door)
squad('N sewer exit yard', 2, (395000.0, 825000.0), 40000.0, [AKG, AK], C3N, CSFM, zlo=-8000.0, zhi=12000.0, where='out', talk=True)
squad('N server room', 2, (205000.0, 975000.0), 26000.0, [JH, HK], C3N, CSF, zlo=20000.0, zhi=24000.0, where='in')
_weather_h.hearing(0.4)                                    # (owner 11-04: one shot must not bring the whole army)
squad('N admin ground floor', 2, (222700.0, 965800.0), 36000.0, [AKG, MG], C3N, CSFM, zlo=33500.0, zhi=36500.0, where='in')
squad('N admin top floor', 2, (222700.0, 965800.0), 36000.0, [SN], C3N, CSF, zlo=46500.0, zhi=50500.0, where='in', alarm=False, sqtype='AIType_Defensive')
squad('N personnel building west', 2, (383700.0, 991700.0), 30000.0, [AK, SG], C3N, LES, zlo=30000.0, zhi=60000.0, talk=True)
squad('N large house', 2, (527600.0, 1007900.0), 30000.0, [SMG], C3N, LES, zlo=-30000.0, zhi=0.0)
squad('N north pad guards', 2, (659500.0, 1017700.0), 40000.0, [AKG, MG], C3T, CSFM, zlo=-34000.0, zhi=-20000.0, where='out')
squad('N hangar', 2, (639500.0, 900800.0), 40000.0, [HK, JH], C3N, CSF, zlo=-31000.0, zhi=-27000.0, where='in')
squad('N east pad and fuel depot', 2, (850000.0, 790000.0), 60000.0, [AKG, MG], C3T, CSFM, zlo=-34000.0, zhi=-20000.0, where='out')
squad('N personnel building east', 2, (723400.0, 811000.0), 30000.0, [T64, SG], C3N, LESM, zlo=-31000.0, zhi=14000.0, where='in', talk=True)
squad('N camera control', 2, (279000.0, 1116700.0), 30000.0, [AK], C3N, LES)
# --- v4: the underground garrison (graphs 6 + 7). Owner plan v4: a SEPARATE, RELAXED garrison - they never heard the alarm upstairs
# (alarm=False: no AlarmControl, so alarmai.Hunt never sends them; their calm loop breaks only on U_ALARM = the chip pulled), walking,
# talking in pairs, guns lowered (life clips), one squad marching in a line; they fight the moment they see Jones (engine default).
U_ALARM = nid()
m.add_child(LOGIC, T(U_ALARM, 'EditVariable', 'SS base below on alert (chip pulled)', 0.0, 0.0, 0.0, 0,
                     'EditVariable_%d.nValue == 0 && GenericTBA_%d.isFinished' % (U_ALARM, GATE_PAD), ''))   # (owner 11-04: nobody hears the sneaking; the gate is the alarm)
_UA = 'EditVariable_%d.nValue' % U_ALARM
# (S12 owner 11-15 'the two soldiers you kill going down the tunnel are 100 % alert'): the checkpoint read U_ALARM, which the gate pad sets, and
# ssperf creates them only then: their calm branch never ran. Their own variable: 0 until one of THEM sees, hears or feels Jones (alert_on_events)
TUN_ALERT = nid()
m.add_child(LOGIC, T(TUN_ALERT, 'EditVariable', 'SS checkpoint on alert', 0.0, 0.0, 0.0, 0, '', ''))
_TA = 'EditVariable_%d.nValue' % TUN_ALERT
_ru = lambda x_, y_: (x_ * 4096.0, y_ * 4096.0)


def alert_on_events(hids, var):
    """(S12) every man of hids sets var = 1 on the first event that means Jones is here (seen, shot at, hit, a mate dying, a blast);
    his calm branch reads var, so from then on he fights and never goes back to his clip. First statement of his script (L21 style)"""
    ev = alarmai.C('AIFunction_GetCurrentEventType')
    evs = ('ENEMYDETECTION', 'ENEMYDETECTION_NO_LOF', 'TAKINGDAMAGE', 'GUNSHOT', 'GUNSHOTMISS', 'BULLETIMPACT', 'FRIENDLY_DYING', 'DEATH_CRY', 'EXPLOSION')
    for h in hids:
        aid = str(lit(next(c.args[0] for c in m.byid[h].args if hasattr(c, 'args') and str(lit(c.args[1])) == 'HumanAI')))
        ver, body = alarmai.decompile_ai(bytes(m.ai_files[aid]))
        body.insert(0, alarmai.If(alarmai.OR(*[alarmai.EQ(ev, 'AIEVENT_' + e) for e in evs]), [alarmai.Bin('=', alarmai.E(var), alarmai.E(1))]))
        m.ai_files[aid] = alarmai.compile_ai(body, ver)


def loop_walkers():
    """S3 (owner 11-15 'they walk around, they move in each direction'; X3_GUARD_LIFE 7.4 recipe C, CRITIC contradiction 1): every
    Kit.patrol_route path (start -> A -> B -> start with a 3-10 s halt AND a look at a random node at every stop = robot-like) becomes a
    node-to-node loop as the originals write it (L16 800: WALKTO per link, median 4.2 m hops): the same start / A / B, walked through the
    graph nodes between them, ONE stop at the far point (look down the freest lane = look_node, 5-9 s), QUIT. The same number of commands
    with the SAME task ids and no m.rng draw: no other id or random pick moves. Runs after the last AI pass, before m.write."""
    import heapq
    pc = getattr(K, 'PATHS_C', None)
    if pc is None or pc not in m.byid:
        print('S3 loops: no patrol paths'); return 0
    n_ok, hops = 0, []
    for pt in [a for a in m.byid[pc].args if isinstance(a, Call) and a.name == 'Task_New' and str(lit(a.args[1])) == 'PatrolPath']:
        g = int(lit(pt.args[3]))
        ci = [i for i, a in enumerate(pt.args) if isinstance(a, Call) and a.name == 'Task_New']
        cmds = [pt.args[i] for i in ci]
        ids = [int(lit(c.args[0])) for c in cmds]
        stops = [int(lit(c.args[4])) for c in cmds if int(lit(c.args[3])) == 2]
        s0 = int(lit(cmds[0].args[5]))
        if len(stops) != 3 or stops[2] != s0 or len(ids) < 7 or g not in GRAPHS:
            print('S3 loops: path %d left (%d walks, %d commands)' % (int(lit(pt.args[0])), len(stops), len(ids))); continue
        byid = {q['id']: q for q in GRAPHS[g]}
        adj = {}
        for a_, b_ in GEDGES[g]:
            adj.setdefault(a_, []).append(b_); adj.setdefault(b_, []).append(a_)

        def path(u, v):                                    # shortest walk u -> v on the graph, never through a door node (as patrol_route)
            dist, prev, q = {u: 0.0}, {}, [(0.0, u)]
            while q:
                d, x = heapq.heappop(q)
                if x == v:
                    break
                if d > dist.get(x, 1e18):
                    continue
                for y in adj.get(x, ()):
                    if byid[y]['crit'] and y != v:
                        continue
                    nd = d + math.dist(byid[x]['pos'], byid[y]['pos'])
                    if nd < dist.get(y, 1e18):
                        dist[y], prev[y] = nd, x; heapq.heappush(q, (nd, y))
            if v not in dist:
                return None
            out_ = [v]
            while out_[-1] != u:
                out_.append(prev[out_[-1]])
            return out_[::-1][1:]
        a, b = stops[0], stops[1]
        legs = [path(s0, a), path(a, b), path(b, s0)]
        if not all(legs):
            print('S3 loops: path %d left (no graph walk)' % int(lit(pt.args[0]))); continue
        n_walk = len(ids) - 3
        L = []
        for st_, lg in zip((s0, a, b), legs):
            cum, prv, c_ = [], byid[st_]['pos'], 0.0
            for n_ in lg:
                c_ += math.dist(prv, byid[n_]['pos']); prv = byid[n_]['pos']; cum.append(c_)
            L.append((lg, cum))
        tot = sum(cum[-1] for lg, cum in L) or 1.0
        k_ = [max(1, int(round(n_walk * cum[-1] / tot))) for lg, cum in L]
        while sum(k_) > n_walk:
            k_[k_.index(max(k_))] -= 1
        while sum(k_) < n_walk:
            k_[k_.index(min(k_))] += 1
        walk = []
        for (lg, cum), kk in zip(L, k_):
            sel = []
            for j in range(1, kk + 1):                     # even spacing along the leg; the leg's end always
                tgt = cum[-1] * j / kk
                n_ = lg[min(range(len(lg)), key=lambda i_: abs(cum[i_] - tgt))]
                if n_ not in sel:
                    sel.append(n_)
            walk += sel
        far = max((a, b), key=lambda n_: math.dist(byid[n_]['pos'], byid[s0]['pos']))
        look, _gm = look_node(g, byid[far]['pos'])
        ticks = 150 + (far * 37) % 120                     # (5-9 s; originals' DELAY median 250 ticks, O7 / L21 180)
        n_delay = len(ids) - 1 - len(walk) - (1 if look is not None else 0)
        new, here = [], s0

        def c(cmd, par, text):
            new.append((cmd, par, here, text))
        for n_ in walk:
            c(2, n_, 'Walks to node id %d' % n_)
            here = n_
            if n_ == far:
                if look is not None:
                    c(5, look, 'Looks at node id %d' % look)
                for j in range(n_delay):
                    t_ = ticks // n_delay
                    c(1, t_, 'Delays the script execution for %d ticks' % t_)
        c(7, -1, 'Quit script, stops script. Takes no parameters')
        assert len(new) == len(ids), (len(new), len(ids))
        for i_, id_, (cmd, par, hr, text) in zip(ci, ids, new):
            pt.args[i_] = T(id_, 'PatrolPathCommand', text, cmd, int(par), int(hr), '', '')
        prv = byid[s0]['pos']
        for n_ in walk:
            hops.append(math.dist(prv, byid[n_]['pos']) / 4096.0); prv = byid[n_]['pos']
        n_ok += 1
    m.reindex()
    hops.sort()
    print('S3 loops: %d patrol paths are node-to-node loops with one stop (hop median %.1f m, max %.1f m)' % (n_ok, hops[len(hops) // 2] if hops else 0, hops[-1] if hops else 0))
    return n_ok


def march(key, g, center, radius, loadouts, ai_type, skins):
    """(plan v4) a squad marching in a line: every man walks the SAME patrol path, spawned a few metres apart along it"""
    pts = pick(g, len(loadouts), center, radius, spacing=4500.0)
    path = K.patrol_route(g, pts[0])
    mem = [dict(pos=p, model=skins[k % len(skins)], weapons=w, ai_type=ai_type, graph=g, ai=_aiscript.patrol(path, _aiscript.NORMAL))
           for k, (p, w) in enumerate(zip(pts, loadouts))]
    sid, hids = m.squad(SQ_PARENT, key, 'AIType_Offensive', mem, alarm_switch=-1, alarm_control=-1)
    SQUAD_IDS[key] = (sid, hids)
    ENEMY_COUNT[0] += len(hids); PATROLS[0] += len(hids)
    return hids


# --- loop 1: the base goes to alert when the chip comes out: red beacons on the walls and all the way up the tunnel
_aglow = [_atmos.glow(m, nid, None, V.U(p_), color=(2.0, 0.25, 0.15), size=0.55, name='SS alert beacon', cutoff_m=120.0) for p_ in
          [(SB.X1 - 0.4, y_, SB.F + 8.0) for y_ in (SB.GATE_Y0 - 1.0, SB.GATE_Y1 + 1.0)] + [(x_, SB.Y0 + 0.4, SB.F + 8.0) for x_ in (200.0, 238.0)] +
          [(x_, SB.Y1 - 0.4, SB.F + 8.0) for x_ in (238.0, 262.0)] + [(SB.X0 + 0.4, 214.0 if SB.GUNROOM else 220.0, SB.F + 8.0)]]
for _s in np.arange(30.0, TUN.s[-1] - 8.0, 36.0):
    _ta = TUN.at(float(_s))
    _aglow.append(_atmos.glow(m, nid, None, V.U((_ta[0] + _ta[4][0] * (SB.TW - 0.3), _ta[1] + _ta[4][1] * (SB.TW - 0.3), _ta[2] + 5.1)), color=(2.0, 0.25, 0.15), size=0.45, name='SS alert beacon', cutoff_m=120.0))
_acc, _atm = _atmos.blink(m, nid, LOGIC, 1.2, 0.6, _aglow, name='SS base alert beacons')
m.set(_acc, 3, 'LevelTimer_%d.nTick < 0.6 * GAME_FREQUENCY && EditVariable_%d.nValue == 1' % (_atm, U_ALARM))
import weather as _weather_h
_weather_h.hearing(0.35)                                   # (owner 11-03 r3: the garrison below reacts only to what happens down there)
squad('U machine room', 7, (170 * 4096.0, 232.4 * 4096.0), 16000.0, [AK, SG, AK], C3N, CSF, where='in', alarm=False, calm_var=_UA,
      patrol=0.0 if LIFTG else 0.5)   # (owner: guards at the lift. SS_LIFTG: the wider graph 7 would give them a patrol route = extra rng draws + task ids
                                      #  ahead of m.squad, every later id and pick shifted (reviewer 11-17); 0.0 keeps the draw and loses it, as the old graph did)
squad('U lift landing', 6, _ru(190.0, 244.5), 9000.0, [HK, AK], C3N, CSFM, alarm=False, talk=True, calm_var=_UA)   # (cb1: at 7 m from the doorway their rifle grenade killed Jones in his first 4 s, in the reveal: moved off, no AKG below until the alert)
squad('U silo post', 6, _ru(238.0, 232.0), 9000.0, [AK], C3N, CSF, alarm=False, patrol=1.0, calm_var=_UA)   # (owner 32: some walk around)
if GARRISON2:
    GR.garrison(globals())
else: squad('U room 1', 6, _ru(183.5, 252.6), 9000.0, [AK, AK], C3N, CSF, alarm=False, talk=True, calm_var=_UA, sleep=(True, True))   # (owner 11-04: the rest in rooms, seen through walls by the goggles)
if SB.GUNROOM:
    GN.crew(globals())
if not GARRISON2: squad('U room 2', 6, _ru(199.5, 252.6), 9000.0, [T64, JH], C3N, CSF, alarm=False, talk=True, calm_var=_UA)
if not GARRISON2: squad('U room 3', 6, _ru(216.0, 252.6), 9000.0, [AK, AK], C3N, CSFM, alarm=False, talk=True, calm_var=_UA, sleep=(True, False))
def work_squad(key, g, spots, weapons, ai_type, skin, clip, calm_var):
    """men at work on the spot, facing the work: a work clip on every calm IDLE (the talk pair recipe), the AI takes them over when they notice Jones"""
    ev = alarmai.C('AIFunction_GetCurrentEventType')
    mem = []
    for (x_, y_, g_), w_ in zip(spots, weapons):
        calm = [Call('AIFunction_SetStandActionAnimation', [Str(clip)]), alarmai.C('AIAction_PlayAnimation', 1, 0)]
        busy = [alarmai.C('AIAction_Idle', 'AIACTIONFLAG_NONE')]
        sc = alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), [alarmai.C('AIFunction_DefaultHandler')],
                                            [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                        [alarmai.If(alarmai.EQ(calm_var, 1), busy, calm), alarmai.C('AIFunction_PassEventOnToSquad')],
                                                        [alarmai.C('AIFunction_DefaultHandler')])])])
        mem.append(dict(pos=(x_ * 4096.0, y_ * 4096.0, SB.F * 4096.0), model=skin, weapons=w_, ai_type=ai_type, graph=g, ai=sc, gamma=g_))
    sid, hids = m.squad(SQ_PARENT, key, 'AIType_Offensive', mem, alarm_switch=-1, alarm_control=-1)
    SQUAD_IDS[key] = (sid, hids)
    ENEMY_COUNT[0] += len(hids)
    return hids


# (owner 109: kneeling they worked the air beside the lock box, hands 0.3 and 1.2 m off it, work/qa/hands. Standing, studying the missile, hands on the hips: nothing to touch.
#  Turned 50 degrees off east, so the box stands, Jones's walk in along y 238 and the decrypt actor at (247.4, 239.0) stay 120+ degrees off their gaze, behind them as before)
work_squad('U scientists', 6, ((247.45, 236.75, -2.443), (247.70, 239.30, -0.698)), [['MAKAROV'], ['MAKAROV']], C3N, 'bubsci_1', 'scientist_standing_studying', _UA)
_tp9 = TUN.at(SB.POST_S - 12.0)
S12_HAND = os.environ.get('SS_S12_HAND', 'KNIFE,SPAS12').split(',')   # (S12: the standing man's hands: knife first = no gun in his hands while calm, test T2)
_tph = squad('U tunnel post', 9, _ru(_tp9[0], _tp9[1]), 16000.0, [AK, S12_HAND], C3N, CSFM, alarm=False, talk=True, calm_var=_TA)


def s12_tea_break(hids, s_, var):
    """S12 (owner 11-15: 'one sitting, one holding something that is not a gun ... talking to each other. Make it feel alive'; SS_AI_LIFE
    scene L1): the checkpoint pair is moved off its two graph nodes (talk_pair keeps its rng draw and ids): 1372 sits on the floor with his
    back to the tunnel's east wall (jones_sits_against_wall, the barracks sleepers' clip, 0.35 m off the wall; small 40 deg / 8 m calm cone:
    he notices Jones late), his mate stands 1.5 m in front of him facing him, stand_talk2 with a knife in his hand. Both calm on `var`.
    11-17 probes s12pC-F (M/work/films/proof_11-15/S12): jones_sits_against_wall draws the body ~1 m BEHIND its origin (the origin is
    near his feet): at 0.35 m he sat inside the wall (never seen), at 0.9 m only his knees showed; 1.3 m back at the wall, 1.6 m a gap.
    So the origin goes S12_SIT m off the wall (1.4) and the talker S12_GAP m (1.2) in front of it (1.9 m off the road's middle)."""
    sit_off = float(os.environ.get('SS_S12_SIT', '1.4'))
    gap = float(os.environ.get('SS_S12_GAP', '1.2'))
    x_, y_, z_, d_, n_ = TUN.at(s_)
    ne = n_ if n_[0] > 0 else -n_                              # (the east wall: the tunnel runs north-south here)
    sit = (x_ + ne[0] * (SB.TW - sit_off), y_ + ne[1] * (SB.TW - sit_off), z_)
    tlk = (sit[0] - ne[0] * gap, sit[1] - ne[1] * gap, z_)
    ev = alarmai.C('AIFunction_GetCurrentEventType')
    for h, p, clip, gam, cone in ((hids[0], sit, 'jones_sits_against_wall', _s12_face(-ne[0], -ne[1]), (40, 8)),
                                  (hids[1], tlk, 'stand_talk2', _s12_face(ne[0], ne[1]), None)):
        for k_, c_ in zip((3, 4, 5, 6), (p[0] * 4096.0, p[1] * 4096.0, p[2] * 4096.0, round(gam, 6))):
            m.set(h, k_, float(c_))
        create = [alarmai.C('AIFunction_DefaultHandler')] + ([alarmai.C('AIFunction_SetIdleViewCone1Alpha', cone[0]), alarmai.C('AIFunction_SetIdleViewCone1Length', cone[1])] if cone else [])
        calm = [Call('AIFunction_SetStandActionAnimation', [Str(clip)]), alarmai.C('AIAction_PlayAnimation', 1, 0)]
        aid = str(lit(next(c.args[0] for c in m.byid[h].args if hasattr(c, 'args') and str(lit(c.args[1])) == 'HumanAI')))
        m.ai_files[aid] = alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), create,
                                                         [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                                     [alarmai.If(alarmai.EQ(var, 1), [alarmai.C('AIAction_Idle', 'AIACTIONFLAG_NONE')], calm),
                                                                      alarmai.C('AIFunction_PassEventOnToSquad')],
                                                                     [alarmai.C('AIFunction_DefaultHandler')])])])
    print('S12 tea break: %d sits at (%.1f, %.1f, %.1f) against the east wall, %d talks over him at (%.1f, %.1f) with %s' % (hids[0], sit[0], sit[1], z_, hids[1], tlk[0], tlk[1], S12_HAND))


def _s12_face(dx, dy):
    return math.atan2(-dx, dy)


s12_tea_break(_tph, SB.POST_S - 12.0, _TA)
alert_on_events(_tph, _TA)   # (S12: calm on their own latch)
_tp8 = TUN.at(SB.POST_S + 5.5)
_tp8c = (_tp8[0] + _tp8[4][0] * 2.2, _tp8[1] + _tp8[4][1] * 2.2)   # (judge 11-08 / orchestrator 11-09: behind barrier 2, out of the chicane gap)
alert_on_events(squad('U tunnel rockets', 9, _ru(_tp8c[0], _tp8c[1]), 8192.0, [RPG, RPG, RPG], C3T, CSFM, alarm=False, patrol=0.0, calm_var=_TA), _TA)   # (owner 11-04: one rocket and you are dead)   # (owner 11-04 'as you imagined': a post on the way out)
_ts8 = min((q_['pos'] for q_ in GRAPHS[8] if not q_['crit']), key=lambda p_: math.hypot(p_[0] - 452.0 * 4096, p_[1] - 201.0 * 4096))   # (the train itself holds no nodes: post him at the nearest one)
print('train sentry post: %.1f %.1f' % (_ts8[0] / 4096, _ts8[1] / 4096))
squad('S train sentry', 8, (_ts8[0], _ts8[1]), 9000.0, [AK], C3N, CSF, alarm=False, patrol=1.0, calm_var=_UA)   # (owner 11-12: the train is empty; one guard walks a beat along it. tools/ssoutro.py _sentry plays him at the boarding while he lives)
squad('U control room', 6, _ru(256.0, 201.5), 6000.0, [HK, MG], C3T, CSFM, where='in', alarm=False, talk=True, calm_var=_UA)
_weather_h.hearing(None)
# --- v4: the reinforcements' landing party by their helicopters beyond the train (graph 8; they hold and fight on sight)
squad('N north admin and garage', 2, (480000.0, 1230000.0), 110000.0, [SN], C3N, CSF, zlo=50000.0, zhi=100000.0, alarm=False, sqtype='AIType_Defensive')
squad('N tunnel mouth', 2, (543000.0, 1320000.0), 50000.0, [AKG, AK], C3T, CSFM)
# --- beyond the tunnel (graph 4): last ambush before the extraction
# (owner rule 4, gradual difficulty: the canyon + south compound = normal desert troops, the airbase = better armed C3,
#  the Hind pads and the tunnel = TOUGH C3 - the end is the hardest)
print('enemies: %d (patrolling %d, talking pairs %s)' % (ENEMY_COUNT[0], PATROLS[0], TALKERS))

# =========================================================== 6b. the alarm AI (owner 10-16: 'when a camera or the alarm triggers they
# stay where they are... it must feel real'): tools/alarmai.py (see work/alarmai/README.md) - wall alarm buttons (the
# map's own door-button model) that a guard who finds a body or sees Jones runs to; on the alarm the squads run to the
# zone Jones is in and search it from two sides; a man who sees him calls for backup; bodies -> distress call + search
import alarmai
# owner 10-31 'kill one and a hundred come': the alarm brings the squads NEAR Jones, not the whole map. The originals'
# AlarmControl wakes the squads in its area; here only squads within 55 m (graph walk) of his zone hunt him (was 260 m),
# a death cry / a body calls the men within 40 m (was 110 m), a man who sees him calls backup within 60 m (was 110 m)
# --- owner 11-03 r3, items 3/8/9: (a) nobody in or next to the shed and its stairs (men REMOVED, never re-laid: the 0xfabc3 trap);
# (b) the top lift station = 2 men talking beside the elevator, nothing else; (c) the garrison below is ISOLATED: no alarm / hunt
# links (alarm=False) and a short hearing range set in every man's CREATE, so a rifle at the lift is not heard in the halls
_rm = 0
for _k, (_sid, _hids) in list(SQUAD_IDS.items()):
    for _h in list(_hids):
        _hx, _hy, _hz = [float(m.arg(_h, c_)) / 4096.0 for c_ in (3, 4, 5)]
        if 160.0 <= _hx <= 174.0 and 233.0 <= _hy <= 245.0 and -11.0 <= _hz <= 0.0:
            print('r3: guard %d (%s) removed at the shed (%.1f, %.1f, %.1f)' % (_h, _k, _hx, _hy, _hz))
            _aidr = next(lit(c_.args[0]) for c_ in m.byid[_h].args if hasattr(c_, 'args') and lit(c_.args[1]) == 'HumanAI')
            m.ai_files.pop(str(_aidr), None); m.remove(_h); _hids.remove(_h); ENEMY_COUNT[0] -= 1; _rm += 1
_lh = SQUAD_IDS['U machine room'][1]
_aidr = next(lit(c_.args[0]) for c_ in m.byid[_lh[2]].args if hasattr(c_, 'args') and lit(c_.args[1]) == 'HumanAI')
m.ai_files.pop(str(_aidr), None); m.remove(_lh[2]); _lh.pop(2); ENEMY_COUNT[0] -= 1
LIFT_GUARDS = ((159.4, 225.4, 0.0, 'stand_talk1'), (159.4, 227.9, math.pi, 'stand_talk2'))
_ev = alarmai.C('AIFunction_GetCurrentEventType')
for _h, (_gx, _gy, _gg, _clip) in zip(_lh, LIFT_GUARDS):
    m.set(_h, 3, _gx * 4096.0); m.set(_h, 4, _gy * 4096.0); m.set(_h, 5, V.TOP_Z * 4096.0); m.set(_h, 6, _gg)
    _aidr = next(lit(c_.args[0]) for c_ in m.byid[_h].args if hasattr(c_, 'args') and lit(c_.args[1]) == 'HumanAI')
    m.ai_files[str(_aidr)] = alarmai.compile_ai([alarmai.If(alarmai.EQ(_ev, 'AIEVENT_CREATE'), [alarmai.C('AIFunction_DefaultHandler')],
        [alarmai.If(alarmai.EQ(_ev, 'AIEVENT_IDLE'),
                    [alarmai.If(alarmai.EQ(_UA, 1), [alarmai.C('AIAction_Idle', 'AIACTIONFLAG_NONE')],
                                [Call('AIFunction_SetStandActionAnimation', [Str(_clip)]), alarmai.C('AIAction_PlayAnimation', 1, 0)]),
                     alarmai.C('AIFunction_PassEventOnToSquad')],
                    [alarmai.C('AIFunction_DefaultHandler')])])])
if LIFTG:                                                 # (off-node men: the lift sentries stand on graph 7 now, and no node or link of it is in the lift cab / shaft)
    _g7 = {n_['id']: n_['pos'] for n_ in GRAPHS[7]}
    _hx, _hy = (V.CAB[2] - V.CAB[0]) / 2 + 0.3, (V.CAB[3] - V.CAB[1]) / 2 + 0.3    # (LIFT_C = the cab's CENTRE (ssv4 place_lift), LIFT_YAW pi keeps the axes; 0.3 m margin)
    _cx0, _cx1, _cy0, _cy1 = V.LIFT_C[0] - _hx, V.LIFT_C[0] + _hx, V.LIFT_C[1] - _hy, V.LIFT_C[1] + _hy
    _incab = lambda x_, y_: _cx0 < x_ < _cx1 and _cy0 < y_ < _cy1
    for _h, (_gx, _gy, _gg, _clip) in zip(_lh, LIFT_GUARDS):
        _d = min(math.hypot(q_[0] / 4096.0 - _gx, q_[1] / 4096.0 - _gy) for q_ in _g7.values() if abs(q_[2] / 4096.0 - V.TOP_Z) < 0.5)
        assert _d < 2.0, 'off-node men: lift sentry %d is %.1f m from graph 7' % (_h, _d)
        print('off-node men: lift sentry %d is %.1f m from graph 7' % (_h, _d))
    _bad = [k_ for k_, q_ in _g7.items() if _incab(q_[0] / 4096.0, q_[1] / 4096.0)]
    _bad += [(a_, b_) for a_, b_ in GEDGES[7] if any(_incab((_g7[a_][0] + (_g7[b_][0] - _g7[a_][0]) * t_) / 4096.0, (_g7[a_][1] + (_g7[b_][1] - _g7[a_][1]) * t_) / 4096.0)
                                                for t_ in np.linspace(0.0, 1.0, 24))]
    assert not _bad, 'off-node men: graph 7 nodes / links in the lift cab: %s' % _bad[:8]
    print('off-node men: graph 7 %d nodes, none in the lift cab (x %.1f-%.1f, y %.1f-%.1f)' % (len(_g7), _cx0, _cx1, _cy0, _cy1))
import diffscale as _ds
from igiqvm import Flt as _Flt
_n = 0
for _k, (_sid, _hids) in SQUAD_IDS.items():
    if not _k.startswith('U ') and _k not in ('N sewer exit yard', 'N server room'):
        continue
    _f = 0.35 if _k == 'U machine room' else GR.hearing(_k) if GARRISON2 and _k.startswith('U ') else 0.08           # (rifle ~100 m x 0.2: the halls hear the halls; a crouching Jones is not heard)
    for _h in _hids:
        _aidr = next(lit(c_.args[0]) for c_ in m.byid[_h].args if hasattr(c_, 'args') and lit(c_.args[1]) == 'HumanAI')
        _ver, _body = alarmai.decompile_ai(bytes(m.ai_files[str(_aidr)]))
        _cr = _ds._find_create(_body)
        assert _cr is not None, _h
        _cr.then.insert(0, Call('AIFunction_SetHearingRangeFactor', [_Flt(_f)]))
        if GARRISON2 and _k.startswith('U '):
            _cr.then.insert(0, Call('AIFunction_SetIdleViewCone1Alpha', [Int(40)]))
            _cr.then.insert(0, Call('AIFunction_SetIdleViewCone1Length', [Int(GR.sight(_k))]))
        if SB.GUNROOM and _k.startswith('U '):             # (owner 63, gf4-gf7: at the gun Jones lasted 16-25 s once the alarm was up, too short to be the fun: long shots miss more, the near fight stays as it is)
            _cr.then.insert(0, Call('AIFunction_SetMaxRangeAccuracy', [Int(GN.MAX_RANGE_ACC)]))
            GN.gun_ai(alarmai, _body, GUNROOM_ZONE, _f)
        m.ai_files[str(_aidr)] = alarmai.compile_ai(_body, _ver)
        _n += 1
print('r3: %d men removed at the shed, lift station %s, %d men below on short hearing' % (_rm, _lh, _n))
if INTRO2:
    _SI.picket(globals())
HUNT = alarmai.Hunt(m, nid, GRAPHS, GEDGES, 1500, ALARM, LOGIC, pfx='SS', reach_m=55.0, distress_m=22.0, backup_m=22.0,
                    run_m=90.0)
for key_ in ('S generator A yard', 'S storage house', 'S garage and east gate', 'S large house', 'N admin ground floor',
             'N hangar', 'N personnel building east', 'N east pad and fuel depot', 'N personnel building west'):
    if SSW.WORLD and key_ in SSW.pins().PIN_BUTTON:        # (a wall found from a man's spot moves with the graph, and can be furniture)
        if SSW.pins().PIN_BUTTON[key_]:
            HUNT.add_switch(*SSW.pins().PIN_BUTTON[key_], on='262_01_1', pressed='262_02_1', name='alarm button (%s)' % key_[2:])
        continue
    for h_ in SQUAD_IDS[key_][1]:
        hp_ = tuple(float(m.arg(h_, k_)) for k_ in (3, 4, 5))
        w_ = K.wall_near(hp_, height_m=1.3, max_m=2.5)
        if w_:
            HUNT.add_switch(w_[0], w_[1], on='262_01_1', pressed='262_02_1', name='alarm button (%s)' % key_[2:])
            break
    else:
        print('alarm button: no wall by %s' % key_)
HUNT.build(loud_alarm=GARRISON2, fight_gate=COVERAI, dead_hold=DEADHOLD)
HUNT2 = GR.alert(globals()) if GARRISON2 else None
if GARRISON2:
    GR.eyes(globals())
if GARRISON2:
    m.add_child(LOGIC, T(SHUT_T, 'LevelTimer', 'SS reaction force clock', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'EditVariable_%d.nValue == 1' % U_ALARM, '', False))
    m.set(SHUTTER, 19, 'Door_%d.isClosed && EditVariable_%d.nValue == 1 && LevelTimer_%d.nTick > 12 * GAME_FREQUENCY' % (SHUTTER, U_ALARM, SHUT_T))
for r_ in HUNT.report:
    print('  hunt: ' + r_)
# owner 10-31 'kill one and a hundred come' - proof: how many guards the alarm sends to Jones at each place of the route
_cw = HUNT.cell * 4096.0
for _lab, _pt in [('start', START), ('generator yard A', (402650.0, 410186.0)), ('generator house B', (639300.0, 295200.0)),
                  ('south sewer hut', (286046.0, 544171.0)), ('sewer exit yard', (381673.0, 843439.0)), ('server', (205000.0, 975000.0)),
                  ('briefcase', (723400.0, 811000.0)), ('east Hind', (819000.0, 749000.0)), ('north Hind', (659500.0, 1017700.0)),
                  ('tunnel mouth', (543000.0, 1320000.0))]:
    _key = (math.floor(_pt[0] / _cw), math.floor(_pt[1] / _cw))
    _zs = {z_['id'] for z_ in HUNT.ZONES if z_['key'] == _key}
    _sq = [q_ for q_ in HUNT.SQUADS if _zs & {zid_ for zid_, a_, b_ in q_['zones']} and (q_['graph'] == 3) == ('sewer' in _lab and 'hut' not in _lab and 'yard' not in _lab)]
    print('alarm response at %-18s %2d guards in %d squads (%s)' % (_lab, sum(len(q_['mem']) for q_ in _sq), len(_sq),
                                                               ', '.join(q_['name'][2:] for q_ in _sq)))
_a7 = str(lit(m.byid[1500].args[7]))                      # (the MP rule: cameras; + a guard pressing an alarm button)
m.set(1500, 7, _a7.rstrip()[:-1] + ' || ' + HUNT.switch_expr() + ')')   # (+ the chip pull: a one-shot window, added after O5 below)

# =========================================================== 7. pickups (RPG shares the rifle slot -> pickups)
PICK = nid()
m.add_child(4087, T(PICK, 'Container', 'SS pickups', False))
for name, g, center, zr, wid in [('medipack storage house', 1, (645000.0, 399200.0), (-2000.0, 3000.0), 'WEAPON_ID_MEDIPACK'),
                                 ('medipack sewer', 3, (345000.0, 600000.0), (-90000.0, -80000.0), 'WEAPON_ID_MEDIPACK'),
                                 ('medipack admin', 2, (222700.0, 965800.0), (33500.0, 36500.0), 'WEAPON_ID_MEDIPACK'),
                                 # (owner rule 3, risk for reward: better guns in the guarded rooms - a silenced MP5SD by the
                                 #  server's guards in the basement, a Dragunov in the admin sniper's room on the top floor)
                                 ('Dragunov admin top floor', 2, (222700.0, 965800.0), (46500.0, 50500.0), 'WEAPON_ID_DRAGUNOV')]:
    if SSW.WORLD and name in SSW.FLOOR_PICKS:
        continue
    p = pick(g, 1, center, 45000.0, zr[0], zr[1], spacing=5000.0)[0]
    if wid != 'WEAPON_ID_MEDIPACK' and not name.startswith('MP5SD'):   # a table top 0.6-1.05 m over this floor within 4 m (the laptop's rule; owner 11-04: the server room's went into the wall)
        _TT0 = K._tris()[0]
        _tp = []
        for _dx in np.arange(-4.0, 4.01, 0.5):
            for _dy in np.arange(-4.0, 4.01, 0.5):
                _x0, _y0 = p[0] + _dx * 4096.0, p[1] + _dy * 4096.0
                _ab0, _be0 = _atmos._vertical_hits(_TT0, (_x0, _y0, p[2] + 1.6 * 4096.0))
                _t0 = [z for z in _be0 if p[2] + 0.6 * 4096 <= z <= p[2] + 1.05 * 4096]
                if _t0 and not any(_t0[0] < z < _t0[0] + 0.45 * 4096 for z in _ab0 + _be0) and any(abs(z - p[2]) < 0.15 * 4096 for z in _be0):
                    _tp.append((math.hypot(_dx, _dy), (_x0, _y0, _t0[0])))
        if _tp:
            p = min(_tp)[1]
            print('pickup %s on a table top' % name)
        if SSW.WORLD and name in SSW.pins().PIN_GUN:
            p = SSW.pins().PIN_GUN[name]
    _rot = (1.570796, 0.0, 0.0)                            # (medipacks: the originals' pickup pose)
    if wid not in ('WEAPON_ID_MEDIPACK',):                 # (a gun lies flat, like L35 3135 'PSG SD' (3.14, 1.45, g) - never upright)
        _rot = (3.141605, 1.449968, float(m.rng.uniform(0, 6.28)))
    m.add_child(PICK, T(nid(), 'GunPickup', 'SS ' + name, float(p[0]), float(p[1]), float(p[2]) + 120.0, *_rot, wid, ''))
if GARRISON2:
    GR.loot(globals())
if SSW.WORLD:
    SSW.pick_ups(m, nid, T, PICK)
if SB.GUNROOM:
    GN.loot(globals())
# O4 (owner 10-12, replaces the fuel depot): steal the courier's documents - his briefcase (Mission 25's 806_01_1,
# transplanted) on the floor of the east personnel building, the block between the east pad and the hangar
import prefabs as _prefabs
X.kit = K                                                  # (the transplant was opened before the AI graphs: the bunker)
X.models('location2/LEVEL5', ['806_01_1', '220_04_1'])
X.models('location1/level1', ['306_02_1', '306_03_1'])    # (the padlock shut / broken - Mission 1, Joyride's gate lock)
CASE_P = pick(2, 1, (723400.0, 811000.0), 30000.0, -31000.0, -24000.0, where='in', spacing=3000.0)[0]   # (ground floor)
if SSW.WORLD:
    CASE_P = SSW.pins().PIN_CASE + (CASE_P[2],)
# on a table top, not on the floor (10-12 test: on the floor it lay hidden under the dining table): a flat surface
# 0.6-1.05 m above that floor within 4 m, 45 cm clear above it, the same height 20 cm around (not an edge)
_TT = K._tris()[0]
_fz = CASE_P[2]
_tops = []
for _dx in np.arange(-4.0, 4.01, 0.25):
    for _dy in np.arange(-4.0, 4.01, 0.25):
        _x, _y = CASE_P[0] + _dx * 4096.0, CASE_P[1] + _dy * 4096.0
        _ab, _be = _atmos._vertical_hits(_TT, (_x, _y, _fz + 1.6 * 4096.0))
        _t = [z for z in _be if _fz + 0.6 * 4096 <= z <= _fz + 1.05 * 4096]
        if not _t or any(_t[0] < z < _t[0] + 0.45 * 4096 for z in _ab + _be):
            continue
        if not any(abs(z - _fz) < 0.15 * 4096 for z in _be):
            continue                                       # a raised floor, not furniture standing on this floor
        _ok = True
        for _ex, _ey in ((0.2, 0), (-0.2, 0), (0, 0.2), (0, -0.2)):
            _a2, _b2 = _atmos._vertical_hits(_TT, (_x + _ex * 4096, _y + _ey * 4096, _fz + 1.6 * 4096.0))
            if not any(abs(z - _t[0]) < 0.03 * 4096 for z in _b2):
                _ok = False
        if _ok:
            _tops.append((math.hypot(_dx, _dy), (_x, _y, _t[0])))
if _tops:
    CASE_P = min(_tops)[1]
    print('briefcase on a table top %.2f m above the floor' % ((CASE_P[2] - _fz) / 4096))
else:                                                      # (11-02: no table in reach - bring the map's own table, 260_11_1)
    import prefab as _pfb, mefmesh as _mmh
    _lvs = _pfb.Level(os.path.join(_pfb.GAME, 'MISSIONS', 'multiplayer', 'sandstorm'))
    _Lt = _lvs.find_vnam('260_11_1'); _mt, _ = _Lt.entry('260_11_1')
    _rt = _mmh.RigidModel.from_mef(_mmh.Mef.read(_lvs.find_resource('LOCAL:models/%s.mef' % _mt, 'models')[1]))
    _top = float(max(np.asarray(g_.pos, float)[:, 2].max() for g_ in _rt.groups))
    m.add_child(K.static_root(), T(nid(), 'EditRigidObj', "SS Kral's table", float(CASE_P[0]), float(CASE_P[1]), float(_fz), 0.0, 0.0,
                                   float(m.rng.random() * 6.28), '260_11_1', 5, False, False))
    CASE_P = (CASE_P[0], CASE_P[1], _fz + _top)
    _tops = [(0.0, CASE_P)]
    print('briefcase: no table in reach - the laptop is on its own table, %.2f m above the floor' % (_top / 4096))
_atmos.ensure_decl(m, 'GenericPickup')
CASE = nid()
m.add_child(PICK, T(CASE, 'GenericPickup', "SS Kral's laptop", float(CASE_P[0]), float(CASE_P[1]),
                    float(CASE_P[2]) + (100.0 if _tops else 300.0),
                    0.0, 0.0, float(m.rng.random() * 6.28), '220_04_1'))
print("Kral's laptop at %s" % [round(c / 4096, 1) for c in CASE_P])
# owner 11-02 'that building looks empty': the broker's room furnished with the base map's own furniture on its free floor
# (indoor graph nodes of that room, away from the laptop table and the talk pair; facing the nearest wall)
_fz0 = _fz
_used = [CASE_P[:2]]
_furn = []
for _mdl, _clear in (('330_01_1', 1.3), ('330_01_1', 1.3), ('230_12_1', 0.7), ('230_12_1', 0.7), ('261_06_1', 0.8), ('261_06_1', 0.8),
                     ('260_02_1', 1.6), ('330_02_1', 1.8)):
    _cand = [q_ for q_ in GRAPHS[2] if q_['terrain'] == 0 and not q_['crit'] and abs(q_['pos'][2] - _fz0) < 0.4 * 4096
             and 1.2 * 4096 < math.dist(q_['pos'][:2], CASE_P[:2]) < 9.0 * 4096
             and all(math.dist(q_['pos'][:2], u_) > (_clear + 1.0) * 4096 for u_ in _used)
             and all(math.dist(q_['pos'][:2], t_[:2]) > 1.6 * 4096 for t_ in TAKEN)]
    if not _cand:
        continue
    _q = min(_cand, key=lambda q_: math.dist(q_['pos'][:2], CASE_P[:2]))
    _w = K.wall_near(_q['pos'], height_m=0.8, max_m=2.5)
    _g = _w[1] if _w else m.rng.uniform(0, 6.28)
    _fp = _q['pos']
    if _w:                                                 # back the piece against that wall
        _fp = (_w[0][0] - math.sin(_g) * -(_clear / 2 + 0.05) * 4096 * -1, _w[0][1] + math.cos(_g) * (_clear / 2 + 0.05) * 4096, _q['pos'][2])
    if any(math.dist(_fp[:2], u_) < _clear * 4096 for u_ in _used):   # (backing on to the wall can land on the last piece: two chairs stood in one)
        continue
    _fid = nid()
    m.add_child(K.static_root(), T(_fid, 'EditRigidObj', 'SS broker room %s' % _mdl, float(_fp[0]), float(_fp[1]), float(_q['pos'][2]),
                                   0.0, 0.0, float(_g + (math.pi if _mdl == '230_12_1' else 0.0)), _mdl, 5, False, False))   # (RQ6 ss-look S5: 230_12_1's front is -y, the chairs faced the wall at 0.12 m)
    _used.append(_fp[:2]); _furn.append(_mdl)
print('broker room furnished: %s' % _furn)
import tempfile as _tf
XSTAGE = _tf.mkdtemp(prefix='ss_prefab_')
# owner 11-01 'when Anya talks, show HER with her mouth moving': the IGI operations room under the map (tools/hq.py - the
# originals' video-link set, L21 / L31: ctrl_01_1 + Anya 'anya_talking'), lit at time-of-day 1000; staged in the intro below
import hq as _hq
HQR = _hq.HQ(K, X, base_m=(140.0, 270.0, -420.0))     # (metres: under the airbase, far below the terrain)
X.models('location3/LEVEL4', ['bubsci_1'])                 # (owner 36: the lab staff of the originals; COMMON's 'scientist' is a cutscene model, shots go through it)
if not (INTRO2 and os.environ.get('SS_SOLDIERS', '1') == '1'):   # (orchestrator 11-14: with the new intro and the new men Kral is sssoldiers' ssm19_1, not the Senator's pat_1)
    X.models('location2/level1', ['pat_1'])                # (the arms broker Kral in the intro call: a civilian in a suit)
import albuild, alskins
import altex as _altex_mod
DRS = albuild.Dresser(K, X)
# (the MP trucks are the base map's own models - not in the overlay manifest, so no livery; they are plain desert trucks)
_orig_ls = m.location_skins
m.location_skins = lambda: _orig_ls() | {'alarm1_1', 'alarm2_1', 'alarmo_1', 'alsea2_1', 'alseao_1', 'alplas_1', 'alalpc_1', 'bubsci_1'} | (set() if INTRO2 and os.environ.get('SS_SOLDIERS', '1') == '1' else {'pat_1'})   # (11-14: Kral no longer wears pat_1)
PROVIDED, _merged = X.finish(XSTAGE)                       # (models merged now: validate() checks them)
_OVL = os.path.join(XSTAGE, 'overlay')
alskins.SHEMAGH = (0.10, 0.10, 0.11)                       # (owner 26: nobody in red)
AL_SKINS = alskins.add_skins(_OVL, 'sandstorm', names=['alarm1_1', 'alarm2_1', 'alarmo_1', 'alsea2_1', 'alseao_1', 'alplas_1', 'alalpc_1'])
SOLDIERS = os.environ.get('SS_SOLDIERS', '1') == '1'            # (owner 52-54: the new Iraqi men and the posters, tools/sssoldiers.py + ssposters.py, behind this flag until proven)
if SOLDIERS:
    import sssoldiers as _SSM, ssposters as _SSP
    _SSM_NAMES = _SSM.add_skins(_OVL, 'sandstorm')
    _ols2 = m.location_skins
    m.location_skins = lambda: _ols2() | set(_SSM_NAMES)
# signs + flags (altex: correctly spelled Arabic; the Iraqi flag; the fictional base name), on walls of the buildings Jones passes
_ST = K.static_root()
SIGNS_AT = []
for _sid, _pt, _h in (('ar_stop', (334500.0, 254000.0, 1300.0), 1.9),   # (11-02 close-ups: both 'Al-Saqr Air Base' plates hung over a
                                                                     #  wall edge - dropped, owner: 'fewer signs rather than broken ones')
                      ('ar_cmd', (205000.0, 975000.0, 22000.0), 1.8), ('ar_restricted', (639500.0, 900800.0, -29000.0), 2.0),
                      ('ar_ammo', (645000.0, 399200.0, 1500.0), 1.8),
                      *(() if SSW.WORLD else (('ar_barracks', (723400.0, 811000.0, -900.0), 1.9),)),   # (ss world: it hung in Kral's office)
                      ('ar_garage', (820000.0, 240000.0, 1500.0), 2.0), ('ar_comms', (279000.0, 1116700.0, 60000.0), 1.9)):
    _w = K.wall_near(_pt, height_m=_h, max_m=6.0)
    if _w:                                                 # (11-02 owner 'mismatched squares': the stone relief poked through a
        _wp = (_w[0][0] - math.sin(_w[1]) * 0.08 * 4096, _w[0][1] + math.cos(_w[1]) * 0.08 * 4096, _w[0][2])   # flush plate)
        DRS.sign(_sid, _wp, _w[1], _ST, name='SS sign %s' % _sid)
        SIGNS_AT.append((_sid, [round(c / 4096.0, 1) for c in _w[0]]))
DRS.finish(_OVL, 'sandstorm', sign_set=())
# the set-piece models (modelkit, vertex-lit like the originals' small props): the container, its door leaf, the missile and its
# cradle, the launch console (Joyride's jrmodels parts), and the Iraqi flag on a pole
import modelkit as _MK, biprefabs as _BP
_box, _cyl, _panel = _BP.box_m, _BP.cyl_z, _MK.panel


def _orig_mesh(rel, vn):
    """an original model's mesh (mefmesh.RigidModel), its level and texture names"""
    import prefab as _pf, mefmesh as _mm
    lv = _pf.Level(os.path.join(_pf.GAME, 'MISSIONS', *rel.split('/')))
    L_ = lv.find_vnam(vn)
    mefn, texs = L_.entry(vn)
    return lv, _mm.RigidModel.from_mef(_mm.Mef.read(lv.find_resource('LOCAL:models/%s.mef' % mefn, 'models')[1])), texs


def _orig_tex(rel, name):
    import prefab as _pf, igitex as _it
    lv = _pf.Level(os.path.join(_pf.GAME, 'MISSIONS', *rel.split('/')))
    return _it.decode(lv.find_resource('LOCAL:textures/%s.tex' % name, 'textures')[1])


def _rotz_part(part, hinge_m, ang):
    P, T_, N, U = part
    c_, s_ = math.cos(ang), math.sin(ang)
    R = np.array([[c_, -s_, 0.0], [s_, c_, 0.0], [0.0, 0.0, 1.0]])
    h = np.array([hinge_m[0], hinge_m[1], 0.0]) * 4096.0
    return (P - h) @ R.T + h, T_, N @ R.T, U


def _ss_ctr():
    """owner 11-02: the ORIGINAL cargo container 331_01_1 (location1/level1) - its own mesh, UVs and textures - with the door end
    opened: the end face (texture 331_01_1, x +5.18 m) becomes two leaves swung 255 deg back along the sides on hinges at the
    corners, every other face gets an inside copy (reversed), a strip light under the roof. Collision: floor, sides, roof,
    closed end and the two leaves - the door end open, nothing inside."""
    lv, r, texs = _orig_mesh('location1/level1', '331_01_1')
    G = {texs[g.tex]: g for g in r.groups}

    def part(g, flip=False):
        P = np.asarray(g.pos, float).copy(); U = np.asarray(g.uv, float).copy()
        T_ = np.asarray(g.tris).copy()
        N = np.zeros_like(P)                               # (the original carries no normals: from its faces, clockwise = front)
        for t_ in T_:
            n_ = -np.cross(P[t_[1]] - P[t_[0]], P[t_[2]] - P[t_[0]])
            N[t_] += n_ / (np.linalg.norm(n_) + 1e-9)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        if flip:
            T_ = T_[:, ::-1].copy(); N = -N
        return P, T_, N, U

    side, end, base = G['331_03_1'], G['331_02_1'], G['331_04_1']
    door = G['331_01_1']
    X0 = float(np.asarray(door.pos, float)[:, 0].mean()) / 4096.0          # the door end (+5.18 m)
    W = float(np.abs(np.asarray(side.pos, float)[:, 1]).max()) / 4096.0     # half width (1.2 m)
    Hh = float(np.asarray(side.pos, float)[:, 2].max()) / 4096.0            # height (2.66 m)
    dP = np.asarray(door.pos, float) / 4096.0; dU = np.asarray(door.uv, float)
    au = np.linalg.lstsq(np.c_[dP[:, 1], np.ones(len(dP))], dU[:, 0], rcond=None)[0]   # u = a y + b
    av = np.linalg.lstsq(np.c_[dP[:, 2], np.ones(len(dP))], dU[:, 1], rcond=None)[0]   # v = c z + d
    z0, z1 = float(dP[:, 2].min()), float(dP[:, 2].max())
    leaves = []
    for sgn in (1.0, -1.0):                                # the leaf hinged at y = +W, then the one at -W
        ya, yb = (0.0, W) if sgn > 0 else (-W, 0.0)
        u_a, u_b = au[0] * ya + au[1], au[0] * yb + au[1]
        v_top, v_bot = av[0] * z1 + av[1], av[0] * z0 + av[1]
        c = (X0, (ya + yb) / 2, (z0 + z1) / 2)
        front = _panel(c, (0, 1, 0), (0, 0, 1), yb - ya, z1 - z0, uv=(u_a, v_top, u_b, v_bot))
        back = _panel(c, (0, -1, 0), (0, 0, 1), yb - ya, z1 - z0, uv=(u_b, v_top, u_a, v_bot))
        hinge = (X0 + 0.03, sgn * (W + 0.03))
        ang = math.radians(255.0) * sgn
        leaves += [_rotz_part(front, hinge, ang), _rotz_part(back, hinge, ang)]
    lamps = [_box(x_ - 0.45, -0.07, Hh - 0.07, x_ + 0.45, 0.07, Hh - 0.02) for x_ in (-2.6, 1.6)]
    groups = [(0, [part(side), part(side, True)]), (1, leaves), (2, [part(end), part(end, True)]), (3, [part(base)]), (4, lamps)]
    t = 0.05
    coll = [_box(-X0, -W, 0.0, X0, W, 0.12), _box(-X0, W - t, 0.0, X0, W, Hh), _box(-X0, -W, 0.0, X0, -W + t, Hh),
            _box(-X0, -W, Hh - t, X0, W, Hh), _box(-X0, -W, 0.0, -X0 + t, W, Hh)]
    for sgn in (1.0, -1.0):
        hinge = np.array([X0 + 0.03, sgn * (W + 0.03)])
        a_ = math.radians(255.0) * sgn
        far = hinge + np.array([[math.cos(a_), -math.sin(a_)], [math.sin(a_), math.cos(a_)]]) @ np.array([0.0, -sgn * W])
        nrm = np.array([-(far - hinge)[1], (far - hinge)[0]]); nrm /= np.linalg.norm(nrm)
        pts = [np.r_[q_ + nrm * o_, z_] for q_ in (hinge, far) for o_ in (-0.02, 0.02) for z_ in (z0, z1)]
        coll.append(_MK.hull_m(pts))
    return _MK.model(groups, coll)


def _ss_bulkhead():
    """the concrete wall closing the rock gallery's open end, with a steel-framed doorway onto the rock tunnel: model x across,
    y = thickness (the hall side at +y), z up"""
    hw, x_d, z_d, t = 7.5, 1.9, 3.85, 0.4
    conc = [_box(-hw, 0.0, -0.6, -x_d, t, 7.8, uv=0.25), _box(x_d, 0.0, -0.6, hw, t, 7.8, uv=0.25),
            _box(-x_d, 0.0, z_d, x_d, t, 7.8, uv=0.25)]
    frame = [_box(-x_d - 0.14, t, -0.05, -x_d, t + 0.06, z_d + 0.14), _box(x_d, t, -0.05, x_d + 0.14, t + 0.06, z_d + 0.14),
             _box(-x_d - 0.14, t, z_d, x_d + 0.14, t + 0.06, z_d + 0.14),
             _box(-x_d - 0.14, -0.06, -0.05, -x_d, 0.0, z_d + 0.14), _box(x_d, -0.06, -0.05, x_d + 0.14, 0.0, z_d + 0.14),
             _box(-x_d - 0.14, -0.06, z_d, x_d + 0.14, 0.0, z_d + 0.14)]
    lamp = [_box(-0.5, t + 0.02, z_d + 0.35, 0.5, t + 0.16, z_d + 0.5)]
    return _MK.model([(0, conc), (1, frame), (2, lamp)], conc)


def _ss_lamp():
    """a hanging work lamp: steel housing, a white diffuser underneath, its cable running 1.6 m up into the rock"""
    housing = [_box(-0.35, -0.11, 0.06, 0.35, 0.11, 0.16)]
    diff = [_box(-0.31, -0.08, 0.02, 0.31, 0.08, 0.06)]
    cable = [_box(-0.012, -0.012, 0.16, 0.012, 0.012, 1.8)]
    return _MK.model([(0, housing + cable), (1, diff)], housing)


def _ss_pole():
    """an 8 m steel mast for a CCTV camera (its foot sinks into the ground: the top carries the camera holder)"""
    mast = [_cyl(0.07, 0.0, 8.0, 10)]
    cap = [_box(-0.12, -0.12, 7.92, 0.12, 0.12, 8.0)]
    return _MK.model([(0, mast + cap)], [_cyl(0.08, 0.0, 8.0, 8)])


def _ss_cable(length_m):
    """a bundle of three power cables lying on the floor along +y (console -> missile)"""
    parts = [_box(x_ - 0.025, 0.0, 0.0, x_ + 0.025, length_m, 0.05) for x_ in (-0.08, 0.0, 0.07)]
    return _MK.model([(0, parts)], parts[:1])


def _ss_cradle():
    parts = [_box(-0.55, -3.0, 0.0, 0.55, 3.0, 0.12)]
    for y in (-2.0, 0.0, 2.0):
        parts += [_box(-0.45, y - 0.12, 0.12, -0.18, y + 0.12, 0.45), _box(0.18, y - 0.12, 0.12, 0.45, y + 0.12, 0.45)]
    return _MK.model([(0, parts)], [_box(-0.55, -3.0, 0.0, 0.55, 3.0, 0.45)])


def _ss_chip(full):                                        # the guidance bay on the missile's skin, +y out: shut with its hub (the wheel 515_04_1 sits on it) / open and empty, the door swung aside
    rim = [_box(-0.42, -0.14, -0.46, -0.36, 0.03, 0.46), _box(0.36, -0.14, -0.46, 0.42, 0.03, 0.46), _box(-0.36, -0.14, -0.46, 0.36, 0.03, -0.40), _box(-0.36, -0.14, 0.40, 0.36, 0.03, 0.46)]
    if full:
        door = [_box(-0.36, -0.14, -0.40, 0.36, 0.02, 0.40)]
        hub = [_box(-0.09, 0.02, -0.09, 0.09, 0.045, 0.09)]
        return _MK.model([(0, door), (1, rim), (2, hub)], door + rim)
    door = [_box(0.42, 0.03, -0.40, 0.46, 0.75, 0.40)]
    back = [_box(-0.36, 0.0, -0.40, 0.36, 0.012, 0.40)]      # (ch1: further back it lay behind the missile's own skin, the bay read as shut)
    return _MK.model([(0, back), (1, rim + door)], rim + door)


def _ss_flag():
    pole = [_cyl(0.05, 0.0, 6.2, 10)]
    front = _panel((0.95, 0.03, 5.45), (-1, 0, 0), (0, 0, 1), 1.8, 1.2)
    back = _panel((0.95, -0.03, 5.45), (1, 0, 0), (0, 0, 1), 1.8, 1.2)
    return _MK.model([(0, pole), (1, [front, back])], [_cyl(0.06, 0.0, 6.2, 8)])


def _ss_flag_s(h, fw, fh, r, base=False):
    """a smaller flag (owner playtest 11-03 item 11): a roof / gate-top pole (h 3.2 m) or a desk flag on a little stand (h 0.42 m)"""
    d = max(0.004, r * 0.6)
    pole = [_cyl(r, 0.0, h, 8)] + ([_box(-0.05, -0.05, 0.0, 0.05, 0.05, 0.015)] if base else [])
    c = (fw / 2 + r, 0.0, h - fh / 2 - min(0.15, h * 0.05))
    front = _panel((c[0], d, c[2]), (-1, 0, 0), (0, 0, 1), fw, fh)
    back = _panel((c[0], -d, c[2]), (1, 0, 0), (0, 0, 1), fw, fh)
    return _MK.model([(0, pole), (1, [front, back])], pole)


_SLIB = _MK.Library()
for _tn, _fn in _JM.TEXTURES.items():
    if _tn in ('jr_olive', 'jr_dark', 'jr_steel', 'jr_misw', 'jr_white', 'jr_console', 'jr_rubber'):
        _SLIB.texture(_tn, _fn)
_SLIB.texture('ss_cpaint', lambda: _JM.tex_paint((0.46, 0.17, 0.11), seed=61, chips=0.06))     # (the chip's red handle)
for _tn, _src in (('ss_ct_side', '331_03_1'), ('ss_ct_door', '331_01_1'), ('ss_ct_end', '331_02_1'), ('ss_ct_base', '331_04_1')):
    _SLIB.texture(_tn, (lambda src_: (lambda: _orig_tex('location1/level1', src_)))(_src))   # (331_01_1's own textures)
_SLIB.texture('ss_bk_conc', lambda: _orig_tex('multiplayer/sandstorm', '400_83_1'))         # (the entrance block's concrete)
_SLIB.texture('ss_flagt', lambda: _altex_mod.sign('iq_flag'))
_SLIB.add('ss_ctr_1', _ss_ctr, ['ss_ct_side', 'ss_ct_door', 'ss_ct_end', 'ss_ct_base', 'jr_white'], lod_like='406_68_1')
_SLIB.add('ss_bkh_1', _ss_bulkhead, ['ss_bk_conc', 'jr_steel', 'jr_white'], lod_like='406_68_1')
_SLIB.add('ss_cab_1', lambda: _ss_cable(6.0), ['jr_rubber'], lod_like='406_68_1')
_SLIB.add('ss_lamp_1', _ss_lamp, ['jr_dark', 'jr_white'], lod_like='406_68_1')
_SLIB.add('ss_pole_1', _ss_pole, ['jr_steel'], lod_like='406_68_1')
_SLIB.add('ss_crd_1', _ss_cradle, ['jr_olive'], lod_like='406_68_1')
_SLIB.add('ss_mis_1', lambda: _JM.build_missile(False), ['jr_misw', 'jr_white'], lod_like='406_68_1')
_SLIB.add('ss_fcc_1', _JM.build_fcc, ['jr_olive', 'jr_console', 'jr_dark'], lod_like='406_68_1')
_SLIB.add('ss_flag_1', _ss_flag, ['jr_steel', 'ss_flagt'], lod_like='406_68_1')
_SLIB.add('ss_flagr_1', lambda: _ss_flag_s(3.2, 1.2, 0.8, 0.035), ['jr_steel', 'ss_flagt'], lod_like='406_68_1')
_SLIB.add('ss_flagd_1', lambda: _ss_flag_s(0.42, 0.22, 0.15, 0.005, base=True), ['jr_steel', 'ss_flagt'], lod_like='406_68_1')
if not ssbay.BAY:                                          # (rc7s ss-loot: with the bay on the chip TBA is re-modelled; slots -> ss_key_1 / ss_note_1)
    _SLIB.add('ss_chipa_1', lambda: _ss_chip(True), ['jr_dark', 'jr_steel', 'ss_cpaint'], lod_like='406_68_1')
if not ssbay.BAY:
    _SLIB.add('ss_chipb_1', lambda: _ss_chip(False), ['jr_dark', 'jr_steel'], lod_like='406_68_1')
if SOLDIERS:
    _SSP.register(_SLIB)
ssbay.lib(_SLIB, _orig_tex, _OVL)
import ssloot
ssloot.lib(_SLIB)
_SLIB.install(_OVL, 'sandstorm')
SS_MODELS = list(_SLIB.names)
_VLIB.install(_OVL, 'sandstorm')                           # (v4: after _SLIB - it reuses jr_steel and the map's own textures)
if SB.GUNROOM:
    GN.tone_cab(_OVL)
    GN.dark_camera(_OVL)
SS_MODELS += list(_VLIB.names)
# (owner playtest 11-03 item 11: no flag on the ground in front of the gate - flags on the gate, the rooftops and desks: section 8b)
print('set-piece models: %s' % SS_MODELS)
print('iraq: %d skins %s, %d signs %s' % (len(AL_SKINS), AL_SKINS, len(SIGNS_AT), SIGNS_AT))

# =========================================================== 8. messages, objective list, map markers
M = {}
# --- voice-over: Windows text-to-speech (Zira = Anya) through a radio filter, cached by text; packed into the level
# sound bank after m.write (ILSF samples + DefineSound entries); a StatusMessage plays it through its Sound parameter
VO = {}                                                    # def name -> (wav path, seconds)
VO_CACHE = os.path.join(HERE, 'work', 'voice_cache')


def spoken(text):
    import re as _re_sp                                    # (review 11-01: strip ANY speaker tag - the guards said 'Guard')
    t = text.split(':', 1)[1].strip() if _re_sp.match(r'^[A-Z][A-Z .]{1,20}:', text) else text
    for a, b in (('1 of 2', 'one of two'), ('2 of 2', 'two of two'), ('RPG', 'R P G'), ('EMP', 'E M P'), ("Xing's", "Shing's"),
                 ('Jones.', 'Jones.'), ('Hind', 'Hind')):
        t = t.replace(a, b)
    return t


def vo(name, text, who='Zira', raw=False):
    """register a voice line; returns (def name, seconds). Def names <= 15 chars (String16 slots), samples unique."""
    import hashlib, shutil as _sh, wave as _wave
    assert len(name) <= 15 and name.startswith('ss_'), name
    import ssvoices as _VCA                                # (owner 11-12: with SS_VOICES=1 a friend's take of this line wins, voices/friends_11-10/clips/<def>.wav)
    _rec = _VCA.actor(name) or voice.actor_wav(name, 'sandstorm')   # (owner 72: a recorded line in work/voice_actors/sandstorm/<def>.wav wins over every generated voice)
    if _rec:
        w = _wave.open(_rec, 'rb'); secs = w.getnframes() / float(w.getframerate()); w.close()
        VO[name] = (_rec, secs)
        return name, secs
    h = hashlib.sha1(('v1|%s|%s%s' % (who, spoken(text), '|raw' if raw else '')).encode()).hexdigest()[:10]
    path = os.path.join(VO_CACHE, '%s_%s.wav' % (name, h))
    if not os.path.exists(path):
        os.makedirs(VO_CACHE, exist_ok=True)
        tmp = voice.make({name: (who, spoken(text))}, os.path.join(VO_CACHE, 'tmp'), raw=raw)[name]
        _sh.move(tmp, path)
    if INTRO2 and who == 'Anya' and not raw:               # (owner 11-07: her face on screen = clear, only heard = a weak radio link)
        path = _SI.radio_link(path, name)
    w = _wave.open(path, 'rb'); secs = w.getnframes() / float(w.getframerate()); w.close()
    VO[name] = (path, secs)
    return name, secs


# owner 11-01 'the voices sound fake - use the ORIGINAL game's': the original speech clips (each level's sounds/ENGLISH
# bank, mp3) are copied into this level's bank with their original DefineSound lines; captions keep their original text
ORIG_VO = {}                                               # def name -> (mp3 bytes, DefineSound qsc, seconds)
ORIG_SYN = {}                                              # def name -> [the original <voice>.syn] (lip-sync envelope)


def syn_from_wav(path):
    """a <voice>.syn for our own lines: what the originals ship next to each voice clip - float32 mouth openness 0..1 at ~30 per
    second (L11 CV10/CV11 .syn: 29.8-30.7 values a second, max 1.0); here the RMS of each 1/30 s window, normalised"""
    import wave as _wv, struct as _st
    if os.path.exists(path[:-4] + '.synsrc.wav'):           # (a line with a sound effect in its file: the mouth follows the words only)
        path = path[:-4] + '.synsrc.wav'
    w_ = _wv.open(path, 'rb'); n_ = w_.getnframes(); sr_ = w_.getframerate(); ch_ = w_.getnchannels()
    pcm = np.frombuffer(w_.readframes(n_), dtype='<i2').astype(float); w_.close()
    if ch_ > 1:
        pcm = pcm.reshape(-1, ch_).mean(axis=1)
    hop = max(1, sr_ // 30)
    env = np.array([np.sqrt(np.mean(pcm[i:i + hop] ** 2)) if len(pcm[i:i + hop]) else 0.0 for i in range(0, len(pcm), hop)])
    env = np.clip(env / (env.max() or 1.0), 0.0, 1.0)
    env[env < 0.08] = 0.0
    return _st.pack('<%df' % len(env), *env)


def _mp3_secs(b):
    """length of an MPEG audio stream (frame walk; layer III, MPEG-1/2)"""
    br1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    br2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    i = 10 + ((b[6] & 0x7f) << 21 | (b[7] & 0x7f) << 14 | (b[8] & 0x7f) << 7 | (b[9] & 0x7f)) if b[:3] == b'ID3' else 0
    t = 0.0
    while i + 4 <= len(b):
        if b[i] != 0xFF or (b[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        ver = (b[i + 1] >> 3) & 3
        bri = b[i + 2] >> 4
        sri = (b[i + 2] >> 2) & 3
        pad = (b[i + 2] >> 1) & 1
        if bri in (0, 15) or sri == 3 or ver == 1:
            i += 1
            continue
        sr = [44100, 48000, 32000][sri] // (1 if ver == 3 else (2 if ver == 2 else 4))
        kbps = (br1 if ver == 3 else br2)[bri]
        n = (144000 * kbps // sr + pad) if ver == 3 else (72000 * kbps // sr + pad)
        t += (1152 if ver == 3 else 576) / float(sr)
        i += max(n, 1)
    return t


def orig(name):
    """register an original speech clip -> (def name, seconds)"""
    import glob as _gl
    name = name.lower()
    if name not in ORIG_VO:
        for bank in sorted(_gl.glob(G_ + 'MISSIONS/location*/*/sounds/ENGLISH/sounds.res')):
            _items = sb.read_bank(bank)[1]
            hit = [b_ for n_, b_ in _items if n_.rsplit('/', 1)[1].lower() == name + '.mp3']
            if not hit:
                continue
            ORIG_SYN[name] = [b_ for n_, b_ in _items if n_.rsplit('/', 1)[1].lower() == name + '.syn'][:1]
            qvm = os.path.join(os.path.dirname(os.path.dirname(bank)), 'sounds.qvm')
            _v, _st = igiqvm.decompile(open(qvm, 'rb').read())
            dq = [d_ for g_ in _st for d_ in (g_.args if isinstance(g_, Call) else []) if isinstance(d_, Call)
                  and d_.name == 'DefineSound' and str(lit(d_.args[0])).lower() == name]
            line = igiqvm.stmts_to_qsc([dq[0]]).strip().rstrip(';') if dq else \
                'DefineSound("%s", "%s", 0, 0, 0, 1, 19.999989, 1e+03, -1, -1, -1, -1, FALSE)' % (name, name)
            ORIG_VO[name] = (hit[0], line, _mp3_secs(hit[0]))
            break
        assert name in ORIG_VO, 'original clip %s not found' % name
    return name, ORIG_VO[name][2]


def msg(key, label, send, text, dur=5.0, voice_def=None, tid=None, parent=None):
    i = tid or nid()
    snd = 'statusmessage'
    if voice_def:
        snd, secs = vo(voice_def, text, 'Anya')               # (11-01: Anya's original-matched radio voice)
        dur = max(dur, secs + 0.5)
    m.add_child(parent or LOGIC, T(i, 'StatusMessage', label, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, send, key, '', snd, True, False, dur, ''))
    if text:
        m.add_text('messages', key, text)
    M[key] = i
    return i


# (10-31 qa DT08: no original plays a briefing on a timer after control; the intro carries it, the first voice in play is an event)
ONE_GEN = '(GenericTBA_150.isFinished || GenericTBA_152.isFinished)'
msg('SS_GEN1', 'SS generator 1 of 2', ONE_GEN + ' && !(%s)' % POWER_OFF,
    'ANYA: One generator is off. Find the other one, Jones.', 8.0, 'ss_gen1')
O1 = msg('SS_DONE1', 'SS objective 1 done', POWER_OFF,
         'ANYA: That was the last one. Lights out down there, and the hut door is free.', 9.0, 'ss_done1')
m.set(3927, 18, '!StatusMessage_%d.isSendt && !AreaActivate_%d.nActive' % (O1, SEWER_HUT))   # (dd4: with both generators done the hut door stayed locked)
O2 = msg('SS_DONE2', 'SS objective 2 done', 'AreaActivate_%d.nActive' % SEWER_EXIT,
         'ANYA: You are through, Jones. Find that basement.', 9.0, 'ss_done2')
O3 = msg('SS_DONE3', 'SS objective 3 done', 'GenericTBA_%d.isFinished' % COMPUTER,
         "ANYA: I'm in. Their network is encrypted - give me a few seconds to break it. Keep your head down, Jones.",
         7.0, 'ss_done3p3', tid=O3_ID)
# phase 2 (owner playtest 11-03 item 6): ~15 s after the hack Anya breaks the encryption -> the decrypt cutscene through the base's
# own cameras (section 8b) -> the new plan: Kral's laptop, then down under the airfield to the missile. No front-gate trap any more.
DECRYPT = 'StatusMessage_%d.nTicksSinceFinishedDisplay > 8 * GAME_FREQUENCY' % O3
if 'decnow' in DBG:                                        # (test: the decrypt cutscene at 5 s, to look at its shots)
    DECRYPT = 'LevelFlow_10.nTick > 5 * GAME_FREQUENCY'
O4 = msg('SS_DONE4', 'SS objective 4 done', 'GenericPickup_%d.isPickedUp' % CASE,
         "ANYA: You have the laptop. Now get to that storeroom shed and go down.", 9.0,
         'ss_done4p4')
msg('SS_LAUNCH0', 'SS launch sequence started', 'LevelTimer_%d.nTick > 5 * GAME_FREQUENCY' % LAUNCH,   # (S17: after the 4.5 s shot of the gate rolling up)
    "ANYA: The cage is open, but that console armed the launch. Two minutes, Jones. Pull the chip from the missile, now!", 6.0, 'ss_launch0')
for _k, _left in enumerate([80, 70, 60, 50, 40, 30, 20, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]):
    _key = 'SS_LCH_%02d' % _left
    m.add_child(LOGIC, T(nid(), 'StatusMessage', 'SS launch countdown %d' % _left, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                         'LevelTimer_%d.nTick > %d * GAME_FREQUENCY && !%s' % (LAUNCH, LAUNCH_S - _left, CHIPPED), _key, '',
                         'statusmessage' if _left <= 10 else '', True, False, 0.9 if _left <= 10 else 2.5, ''))
    m.add_text('messages', _key, 'MISSILE LAUNCH IN %d SECOND%s' % (_left, '' if _left == 1 else 'S'))
O5 = msg('SS_DONE5', 'SS objective 5 done', CHIPPED,
         "ANYA: Chip's out. That missile is going nowhere now. Time to leave, Jones.", 8.0, 'ss_done5e')
GATEUP = nid()                                             # (owner 11-04: the chip goes quietly; the gate rolling up is what rings the alarm)
_a7 = str(lit(m.byid[1500].args[7]))
m.set(1500, 7, _a7.rstrip()[:-1] + ' || (StatusMessage_%d.isSendt && !StatusMessage_%d.isFinishedDisplay))' % (GATEUP, GATEUP))
FIREDMSG = msg('SS_FIRED', 'SS the missile fired', FIRED, "ANYA: The missile's away... It's over, Jones.", 5.0, 'ss_fired')
_atmos.ensure_decl(m, 'MissionTimer')
MCLOCK_S = 150 if 'shortclock' in DBG else 3600                                             # 60 minutes of play (judge J04, 11-08: kept, the full army makes 15 min unfair); paused while a cutscene runs
OUTOFTIME = nid()                                          # (the timer itself is created after the intro exists - section 8b)
# 10-12 owner stuck after all 5 objectives: the raw TARGETS_DONE conjunction (5 isExploded/isFinished at the SAME tick)
# never came true in a real run (only ever tested with the 'objectives' variant, which used these latches) -> doors stayed
# locked and the extraction never counted. The objective messages latch (isSendt stays set): drive doors + escape on them.
TARGETS_LATCHED = 'StatusMessage_%d.isSendt && StatusMessage_%d.isSendt && StatusMessage_%d.isSendt' % (O3, O4, O5)
m.set(3148, 18, '1'); m.set(3148, 19, '0')                # (phase 2: no lockdown - the flooded tunnel stays shut)
m.set(3147, 18, '1'); m.set(3147, 19, '0')                # (the north door never opens again)
FLOOD = nid()
m.add_child(LOGIC, T(FLOOD, 'AreaActivate', 'SS inside the flooded tunnel', 541000.0, 1372000.0, 60000.0, 0.0, 0.0, 0.0,
                     2.6 * 4096, 7.0 * 4096, 3.0 * 4096, 'CRITERIA_HUMAN0'))
DROWN = msg('SS_DROWN', 'SS drowned in the tunnel', 'AreaActivate_%d.nActive' % FLOOD,
            'ANYA: Jones, that tunnel is flooded to the roof. You will never get through.', 3.0, 'ss_drown')   # (judge P20-2: voiced)
OPEN = msg('SS_ESCAPE', 'SS escape open', 'StatusMessage_%d.nTicksSinceFinishedDisplay > GAME_FREQUENCY / 2' % O5,
           "ANYA: The code panel is on the wall right beside that gate. Open it, then get up the ramp.", 6.0, 'ss_escape')   # (audit 11-07: the old line sent him back to the control room; judge P20-1 11-14: voiced)
HALL_AT = nid()                                            # (loop 3: the reveal: Anya sees it through Jones' feed, and it tells him where to go with no markers on the map)
m.add_child(LOGIC, T(HALL_AT, 'AreaActivate', 'SS Jones in the hall', 177.0 * 4096, 226.5 * 4096, (SB.F + 1.5) * 4096, 0.0, 0.0, 0.0, 6.0 * 4096, 8.0 * 4096, 4.0 * 4096, 'CRITERIA_HUMAN0'))
msg('SS_HALL', 'SS the hall', 'AreaActivate_%d.nActive' % HALL_AT,
    "ANYA: My God, Jones. Four launchers... and that one is on its pad. The control room is at the far end, past the silo.", 7.0, 'ss_hall')
msg('SS_CAMS', 'SS cameras offline', 'GenericTBA_%d.isFinished' % SECURITY_PC, 'ANYA: Camera control hacked. The airbase cameras are offline.', 8.0, 'ss_cams')
msg('SS_ALARM', 'SS alarm', 'EditVariable_1500.nValue == 1', 'Alarm! Guards are coming your way.', 4.0)
DONE = msg('MISSION_COMPLETE', 'SS mission complete', '%s && StatusMessage_%d.isFinishedDisplay && (AreaActivate_%d.nActive || AreaActivate_%d.nActive) && !HumanPlayer_0.isDead'
           % (TARGETS_LATCHED, OPEN, EXTRACT, EXTRACT_WIDE),       # (qa SK08: after Anya's escape line, never on top of it)
           None, 3.0)                                      # built-in text

lf = L[10]                                                 # LevelFlow, moved to the end below
lf.args[10] = v('StatusMessage_%d.isFinishedDisplay && !HumanPlayer_0.isDead' % DONE)
lf.args[11] = v('StatusMessage_%d.nTicksSinceFinishedDisplay > 5 * GAME_FREQUENCY || StatusMessage_%d.nTicksSinceFinishedDisplay > 3 * GAME_FREQUENCY'
                ' || StatusMessage_%d.nTicksSinceFinishedDisplay > 2 * GAME_FREQUENCY' % (DEAD, FIREDMSG, DROWN))

OBJ_TEXT = [('SS_OBJ1', 152, 'StatusMessage_%d.isSendt' % O1, 'Shut down both power generators in the southern compound.'),
            ('SS_OBJ2', SEWER_EXIT, 'StatusMessage_%d.isSendt' % O2, 'Go through the sewer hut by the generators, under the hills, into the northern airbase.'),
            ('SS_OBJ3', COMPUTER, 'StatusMessage_%d.isSendt' % O3, 'Hack the server in the west admin basement and find out what this base hides.'),
            ('SS_OBJ4', CASE, 'StatusMessage_%d.isSendt' % O4, "Take the arms broker Kral's laptop from the east personnel building."),
            ('SS_OBJ5', CHIP, 'StatusMessage_%d.isSendt' % O5, 'Act on what the server reveals. Anya will tell you where to go.'),
            ('SS_OBJ6', HOPON, 'StatusMessage_%d.isSendt' % DONE, 'Get out of Al-Saqr alive.')]
args = [Int(nid()), Str('DefineComputerObjective'), Str('Objectives'), Str('1')]
for slot in range(8):
    if slot < len(OBJ_TEXT):
        key, link, cond, text = OBJ_TEXT[slot]
        args += [Str(key), v(link), Str(cond), Str('')]
        m.add_text('objectives', key, text)
    else:
        args += [Str(''), v(-1), Str(''), Str('')]
mapc = nid()
m.add_child(4087, T(mapc, 'Container', 'SS map computer', False, children=[Call('Task_New', args)]))
# (orchestrator 11-03 r3 item 10: every objective has a marker, but it APPEARS only once that objective is revealed; the later ones
#  mark the AREA or entrance, not the item: 3 the admin building, 4 the personnel building, 5 the shed + the missile hall, 6 the vehicle gate)
_mk = lambda tid_: tuple(float(m.arg(tid_, k_)) for k_ in (3, 4, 5))
_after_hack = DECRYPT
for tid, n, _mp, _mc_ in [(150, 1, _mk(150), '1'), (152, 1, _mk(152), '1'), (SEWER_EXIT, 2, _mk(SEWER_EXIT), '1'),
                          (COMPUTER, 3, (54.4 * 4096, 235.8 * 4096, 8.4 * 4096), '1'),
                          (CASE, 4, (176.6 * 4096, 198.0 * 4096, -3.0 * 4096), _after_hack),
                          (CHIP, 5, V.U(V.SHED), _after_hack), (CHIP, 5, V.U((SB.PIT_C[0], SB.PIT_C[1], SB.F)), _after_hack),
                          (HOPON, 6, _mk(VGATE), 'StatusMessage_%d.isSendt' % O5)]:
    m.add_child(mapc, T(nid(), 'ComputerHilight', '', float(_mp[0]), float(_mp[1]), float(_mp[2]), _mc_, str(tid), 'COMPUTER:h_%d.spr' % n,
                        'MARKER_NONE', 'MARKER_COLOR_NONE', '', '', -1))

# loading-screen tips (owner 10-12: 'a loading screen like the original game, with tips'): LANGUAGE menusystem.res
# level<id>tips/heading + tip1..3, shown by igi2.exe 0x5380a0 under the loading picture (install.py RESFILES)
m.add_text('menusystem', 'level19tips/heading', 'Al-Saqr Air Base')
m.add_text('menusystem', 'level19tips/tip1', 'Both generators feed the lock on the sewer hut door: cut the power, then go under the hills')
m.add_text('menusystem', 'level19tips/tip2', 'The server tells you what this base really hides')
m.add_text('menusystem', 'level19tips/tip3', 'The plastic security cameras can be shot out; the metal ones cannot - cut the power or hack the camera control')
m.add_text('missions', 'Mission %d Name' % MISSION_ID, 'Operation Sandstorm')
m.add_text('missions', 'Mission %d Desc' % MISSION_ID,
           "Something is going on at Al-Saqr Air Base in the western Iraqi desert: night flights, General Dhari running "
           "the base, and tonight a European arms broker, Kral, has flown in. IGI does not know what they are doing. Cut the "
           "power in the southern compound, go under the hills through the sewer, hack their server, take the broker's "
           "laptop - and find out what this base hides. You have one hour.")

# =========================================================== 8b. cutscenes: intro flythrough of every target with Anya's
# voice-over, outro over the burning base that sets up the next mission (Atlas Mountains). Pattern of the originals
# (work/research/cutscenes.md): player + enemies sit in ConditionalContainers that are off while a cutscene runs.
TERR = terrain_mod.Terrain(m.src, m.stmts)
P = lambda i: tuple(float(m.arg(i, k)) for k in (3, 4, 5))
up = lambda p_, metres: (p_[0], p_[1], p_[2] + metres * CS.M)


def shots(spec, prefix, fade_in=False, fade_out=False):
    """spec: [(voice def, text, target, dist m, bearing0, bearing1, elev deg)] or an explicit [(pos, look), (pos, look)]
    pair in place of the target; every shot lasts as long as its line + 0.6 s (owner 10-30: no dead air). -> (keys, captions)"""
    keys, caps, t = [], [], 0.0
    for k, (vdef, text, target, *geo) in enumerate(spec):
        who, raw = ('Anya', False)                         # (11-01: Anya's original-matched radio voice, voice.py blend)
        if vdef is None:                                   # a silent establishing shot (11-02: 'show the camera object')
            name, secs = None, float(geo[0]) - 0.6
        elif isinstance(vdef, tuple) and vdef[0] == 'orig':  # an ORIGINAL speech clip (owner 11-01)
            name, secs = orig(vdef[1])
        else:
            if isinstance(vdef, tuple):                    # (def, voice): an on-screen speaker in person (no radio filter)
                vdef, who = vdef
                raw = True
            name, secs = vo(vdef, text, who, raw)
        dur = secs + 0.6
        therm = False
        if isinstance(target, tuple) and target and target[0] == 'thermal':  # 11-02: a THERMAL satellite pass (engine thermal view)
            if len(target) > 4:                            # (rc7k K1: the pass looked 15 m beside the train, straight down: the cars read as a strip. Now the lens looks AT the train)
                ks = [_rkey(target[1], target[3], dur, True, fov=0.8, shake=0.0008, **recon.FEED), _rkey(target[2], target[4], 0.0, False, fov=0.8, shake=0.0008, **recon.FEED),
                      _rkey(target[2], target[4], 0.0, False, fov=0.8, shake=0.0008, **recon.FEED)]
            else:
                ks = recon.drone_keys(_rkey, lambda x_, y_: float(TERR.height(x_, y_)), target[1], target[2], dur, alt_m=target[3],
                                      look_ahead_m=25.0, burst=0.0)
            for k_ in ks:                                  # (11-02 rig: the OverlayHolder infrared flag did not engage in a cutscene -
                k_.update(filt=atmos.LINE, color=(0.02, 0.10, 0.03), noise=0.05)   # (critic rv3: flat green read as a placeholder -> the HQ video-link lines over the real view)
            therm = False
        elif isinstance(target, tuple) and target and target[0] == 'office':  # a hacked CCTV camera inside the colonel's office
            if len(target) > 5:                            # (judge H05: two real cameras on one line, a static cut between them)
                _d1 = (dur - 0.25) * target[7]
                _k1 = atmos.cctv_keys(target[1], target[2], _d1, tint='surveillance', fov=0.95, pan_to=target[3], zoom_to=target[4], burst_out=False)
                _k2 = atmos.cctv_keys(target[5], target[6], dur - 0.375 - _d1, tint='surveillance', fov=0.95)
                ks = [dict(k_, indoor=True) for k_ in _k1 + _k2]
            else:
                ks = [dict(k_, indoor=True) for k_ in atmos.cctv_keys(target[1], target[2], dur - 0.25, tint='surveillance', fov=0.95,
                                                                      pan_to=target[3] if len(target) > 3 else None, zoom_to=target[4] if len(target) > 4 else None)]   # (judge F04: operator zoom)
        elif isinstance(target, tuple) and target and target[0] == 'drone':   # 11-01 variety: recon drone feed (tools/recon.py)
            ks = recon.drone_keys(_rkey, lambda x_, y_: float(TERR.height(x_, y_)), target[1], target[2], dur, alt_m=target[3])
        elif isinstance(target, tuple) and target and target[0] == 'photo':  # recon photo stills, a shutter click each
            ks, at_ = recon.photo_keys(_rkey, target[1], dur)
        elif isinstance(target, tuple) and target and target[0] == 'hq':     # the IGI HQ video link: Anya at her desk
            ks = [HQR.key(target[1], target[2], dur, True, fov=0.6, filt=atmos.LINE, color=(0.0, 0.12, 0.0), noise=0.04),
                  HQR.key(target[3], target[2], 0.0, False, fov=0.56, filt=atmos.LINE, color=(0.0, 0.12, 0.0), noise=0.04)]
            HQ_CAPS.append('%s_%d' % (prefix, k + 1))
        elif isinstance(target, tuple) and target and target[0] == 'cctv':   # a hacked security camera feed (L13 / L21 pattern)
            ks = atmos.cctv_keys(target[1], target[2], dur - 0.25, tint='surveillance', fov=0.8,   # (L11 'Surveilance footage' tint)
                                 pan_to=target[3] if len(target) > 3 else None, zoom_to=target[4] if len(target) > 4 else None)   # (rc7m 1:08: a pan that follows a man)
        elif isinstance(target, tuple) and target and target[0] == 'still':  # a held ground shot (the guards talking)
            ks = [CS.key(target[1], target[2], dur, True, fov=0.6), CS.key(target[3], target[2], 0.0, False, fov=0.6)]
        elif isinstance(target, list):                    # explicit (pos, look-at) pair: smooth move
            (p0, l0), (p1, l1) = target
            ks = [CS.key(p0, l0, dur, True), CS.key(p1, l1, 0.0, False)]
        else:
            dist, b0, b1, elev = geo
            ks = CS.orbit_shot(TERR, target, dist, b0, b1, elev, dur)
        if k == 0 and fade_in:
            p0, l0 = ks[0]['pos'], ks[0]['tgt']
            keys += [dict(CS.key(p0, l0, 1.0, True, fov=ks[0]['fov'], filt=CS.BAND, color=(0, 0, 0), noise=0.0), **({'tod': ks[0]['tod']} if 'tod' in ks[0] else {})),
                     dict(CS.key(p0, l0, 0.0, False, fov=ks[0]['fov'], filt=CS.BAND,   # (owner 11-03 item 8: 'white then green' -
                                 color=ks[0]['color'] if ks[0].get('filt') == CS.BAND else (1, 1, 1), noise=0.0),   #  fade up into the shot's own tint)
                          **({'tod': ks[0]['tod']} if 'tod' in ks[0] else {}))]
            t += 1.0
        keys += ks
        if therm:
            THERMAL_WIN.append((prefix, t, t + dur))
        if name is not None:
            caps.append((round(t + 0.3, 2), '%s_%d' % (prefix, k + 1), text, name, secs + 0.3))
        t += dur
    if fade_out:
        p_, l_ = keys[-1]['pos'], keys[-1]['tgt']
        keys += [CS.key(p_, l_, 0.9, True, filt=CS.BAND, color=(1, 1, 1), noise=0.0),
                 CS.key(p_, l_, 0.0, False, filt=CS.BAND, color=(0, 0, 0), noise=0.0)]
    return keys, caps


import recon, atmos
THERMAL_TINT = (0.14, 0.55, 0.24)                             # (green-only = monochrome green, like the T goggles; L12 1111 'Security Cam')
HQ_CAPS = []
THERMAL_WIN = []
_rkey = lambda *a_, tod=-1.0, **kw_: CS.key(*a_, **kw_)    # (recon passes tod; the in-game light is the default anyway)
SOUTH = (518600.0, 344000.0, 21000.0)                     # between the two generators
EASTPAD = (850000.0, 784000.0, -30000.0)                  # east Hind + fuel depot
NORTH_OUT = (590000.0, 1440000.0, 60000.0)                # north tunnel -> extraction valley
EYE = up(START, 1.7)
FWD = (START[0], START[1] + 80 * CS.M, START[2] + 4 * CS.M)
# 11-01 (owner + SHOBI cutscene notes): varied, short, no dead air, nothing above ~150 m - a recon-drone feed over the airbase,
# the south gate guards talking in person (L11 'Jones glide by guards' recipe, lip-synced), low orbits, recon photo stills
GUARD_A = (326000.0, 256500.0)                             # inside the south gate (doors 300/301 at y 59.5 m)
GUARD_B = (334500.0, 259000.0)
_gz = lambda xy: float(TERR.height(xy[0], xy[1]))
GMID = ((GUARD_A[0] + GUARD_B[0]) / 2, (GUARD_A[1] + GUARD_B[1]) / 2)
GCAM0 = (GMID[0] + 3.6 * CS.M, GMID[1] + 4.2 * CS.M, _gz(GMID) + 1.75 * CS.M)
GCAM1 = (GMID[0] + 2.9 * CS.M, GMID[1] + 3.6 * CS.M, _gz(GMID) + 1.7 * CS.M)
GLOOK = (GMID[0], GMID[1], _gz(GMID) + 1.5 * CS.M)
GCCTV0 = (GMID[0] + 4.5 * CS.M, GMID[1] + 6.0 * CS.M, _gz(GMID) + 3.4 * CS.M)      # a wall camera by the gate
GCCTV1 = (GMID[0] - 4.0 * CS.M, GMID[1] + 5.5 * CS.M, _gz(GMID) + 3.1 * CS.M)      # its twin on the other side
ADMIN = P(COMPUTER)
EASTB = (723400.0, 811000.0, -943.0)                        # the east personnel block (Kral's laptop)
# the colonel's office = the server room in the west admin basement (floor 5.29 m; graph nodes 760 / 689 there)
_OM = lambda x, y, z: (x * CS.M, y * CS.M, z * CS.M)
COL_P, KRAL_P = _OM(50.02, 239.31, 5.29), _OM(50.5, 236.81, 5.29)
OCAM0, OLOOK0 = _OM(51.2, 236.5, 7.6), _OM(50.15, 238.9, 6.85)     # CCTV in the corner, the colonel faces it
OCAM1, OLOOK1 = _OM(48.9, 238.2, 7.7), _OM(50.5, 236.9, 6.85)      # the side wall: Kral (the colonel out of the frame)
# Jones listening in the canyon before going in (L26 'jones_hiding')
JON_P = (START[0] - 2.0 * CS.M, START[1] + 3.0 * CS.M, float(TERR.height(START[0] - 2.0 * CS.M, START[1] + 3.0 * CS.M)))
_jc = lambda dx, dy, h: (JON_P[0] + dx * CS.M, JON_P[1] + dy * CS.M,
                        max(JON_P[2], float(TERR.height(JON_P[0] + dx * CS.M, JON_P[1] + dy * CS.M))) + h * CS.M)
JCAM0, JCAM1 = _jc(3.4, -3.6, 1.15), _jc(2.8, -3.0, 1.1)
JLOOK = (JON_P[0], JON_P[1], JON_P[2] + 0.8 * CS.M)
# the burning east Hind on a pad camera (outro)
HCAM = (P(3904)[0] - 14.0 * CS.M, P(3904)[1] + 10.0 * CS.M, float(TERR.height(P(3904)[0] - 14.0 * CS.M, P(3904)[1] + 10.0 * CS.M)) + 6.0 * CS.M)
HLOOK = up(P(3904), 1.5)
# owner 11-02 'shots from places where no camera could be': every feed comes from a REAL camera object (the map's own security
# camera 313_07_1 holder + 313_06_1 head) mounted where its picture is taken from; the gate camera is shown first at eye level
import sscams as _SCAMS                                    # (owner 116: camera plates on walls, cutscene eyes out of camera heads, tools/sscams.py)


def cam_obj(pos, look, parent=None, name='SS CCTV camera', pole=True):
    g_ = math.atan2(-(look[0] - pos[0]), look[1] - pos[1])
    _bk = 1.5 if pole else 0.35                            # (in5: a mast camera's own head filled the bottom of its picture)
    back = (pos[0] + math.sin(g_) * _bk * CS.M, pos[1] - math.cos(g_) * _bk * CS.M, pos[2] + 0.12 * CS.M)
    pt = parent or K.static_root()
    if not pole:                                           # (a wall camera: its holder on the nearest wall at its height)
        if _SCAMS.ON:                                      # (owner 116: the plate ON the wall behind the eye - 0.35 m back left the control room one 0.15 m in the air)
            back = _SCAMS.wall_plate(K._tris()[0], (pos[0], pos[1], back[2]), back)
        _ab, _be = _atmos._vertical_hits(K._tris()[0], back)   # (an office camera hangs from the ceiling: 313_07_1's top is +0.206 m)
        _ceil = min([z_ for z_ in _ab if z_ > back[2]] or [None]) if _ab else None
        if _ceil is not None and _ceil - back[2] < 2.5 * CS.M:
            back = (back[0], back[1], _ceil - (_SCAMS.HEADROOM if _SCAMS.ON else 0.215) * CS.M)   # (owner 116: 0.215 left the tilted holder in the ceiling)
        print('cctv %s: %s' % (name, 'under the ceiling' if _ceil is not None else 'NO CEILING'))
    if pole:                                               # (owner 11-02 r6: the gate cameras hung in the air - every outdoor /
        m.add_child(pt, T(nid(), 'EditRigidObj', name + ' mast', back[0], back[1], back[2] - 8.0 * CS.M - 0.185 * CS.M, 0.0, 0.0, 0.0,
                          'ss_pole_1', 5, False, False))  #  hall camera stands on its own mast; the office ones hang on walls)
    feed_cam(back, g_, name)
FEEDS = {}


def feed_cam(pos_u, gamma, name):
    """a real SCamera (a copy of the map's own, breakable, it never trips the alarm: the feeds only) at pos_u facing gamma"""
    i_ = nid()
    c_ = _copy.deepcopy(L[3212]); c_.args[0] = v(i_); c_.args[2] = v('SS feed camera ' + name)
    for k_, a_ in zip((3, 4, 5, 6), (*pos_u, gamma)):
        c_.args[k_] = v(float(a_))
    c_.args[13] = v(0); c_.args[14] = v(0); c_.args[15] = v(0); c_.args[20] = v('0')
    m.add_child(4029, c_)
    _cams.set_kind(m, i_, 'soft')
    _under = SB.GUNROOM and float(pos_u[2]) < -8.0 * 4096.0   # (owner 83: the map's camera bakes bright outdoors, underground it drew white in a dark room)
    for k_, a_ in ((7, 'ss_cam7_1' if _under else '313_07_1'), (11, 'ss_cam6_1' if _under else '313_06_1'), (12, '335_03_1')):   # (the grey head; a bullet swaps it for the broken one)
        m.set(i_, k_, a_)
    FEEDS[name] = i_
    return i_


def map_feed(target, name, maxm=130.0):
    """the nearest of the map's cameras with a clear line to target (the map's own, breakable): ('cctv', pos 1 m out of it, target); none: a new one on the nearest wall"""
    best = None
    for c_ in m.find('SCamera'):
        q_ = np.array([float(m.arg(c_, k_)) for k_ in (3, 4, 5)])
        t_ = np.array(target[:3], float)
        d_ = float(np.linalg.norm(q_ - t_))
        if d_ < 12.0 * CS.M or d_ > maxm * CS.M or K.blocked(q_ + (t_ - q_) / d_ * 1.0 * CS.M, t_, pad=0.1 * CS.M):
            continue
        if best is None or d_ < best[0]:
            best = (d_, tuple(q_ + (t_ - q_) / d_ * 1.0 * CS.M), c_)
    if best is None:
        w_ = None
        for r_ in (10.0, 20.0, 35.0):
            w_ = K.wall_near((target[0], target[1], target[2]), height_m=4.5, max_m=r_)
            if w_:
                break
        assert w_, ('no wall for a feed camera', name)
        c_ = feed_cam(w_[0], w_[1], name)
        print('feed %s: new camera %d on a wall %s' % (name, c_, [round(x_ / 4096.0, 1) for x_ in w_[0]]))
        q_ = (w_[0][0] - math.sin(w_[1]) * 4096.0, w_[0][1] + math.cos(w_[1]) * 4096.0)
        return ('cctv', (q_[0], q_[1], max(w_[0][2], float(TERR.height(q_[0], q_[1])) + 2.0 * CS.M)), target)
    print('feed %s: map camera %d, %.0f m' % (name, best[2], best[0] / 4096.0))
    return ('cctv', best[1], target)


def mast_feed(xy, look, name):
    """a feed from a camera on its own mast at xy (outdoors, where no wall looks at the target)"""
    p_ = (xy[0], xy[1], float(TERR.height(xy[0], xy[1])) + 7.4 * CS.M)
    cam_obj(p_, look, name=name, pole=True)
    return ('cctv', p_, look)


CONT_CAM = V.U((236.0, 253.0, SB.F + 12.0))                  # (v4: hall B camera high on the north wall, on the big missile)
CONT_LOOK = V.U((SB.PIT_C[0], SB.PIT_C[1], SB.F + 7.0))
GEST0 = (GMID[0] + 1.8 * CS.M, GMID[1] + 9.5 * CS.M, _gz(GMID) + 1.65 * CS.M)      # eye level, looking at the gate camera
# the north tunnel's south door on the camera that watches it (mast), its guards in the frame
_tp = P(3148)
TCAM = (_tp[0] + 7.0 * CS.M, _tp[1] - 13.0 * CS.M, float(TERR.height(_tp[0] + 7.0 * CS.M, _tp[1] - 13.0 * CS.M)) + 4.6 * CS.M)
TLOOK = (_tp[0], _tp[1], _tp[2] + 1.4 * CS.M)
# over the shoulder of Jones crouching in the canyon ('Let's do it'), looking up the canyon toward the base
JS_CAM0 = _jc(0.75, -2.3, 1.5)
JS_CAM1 = _jc(0.65, -2.0, 1.45)
JS_LOOK = (JON_P[0] - 0.3 * CS.M, JON_P[1] + 25 * CS.M, JON_P[2] + 0.9 * CS.M)
_pcam = lambda p_, dx, dy, dz: (p_[0] + dx * CS.M, p_[1] + dy * CS.M,      # a photo camera position, kept 12 m over the ground
                                max(p_[2] + dz * CS.M, float(TERR.height(p_[0] + dx * CS.M, p_[1] + dy * CS.M)) + 12 * CS.M))
INTRO = [
    ('ss_i1c', 'ANYA: Al-Saqr Air Base, western Iraq. The wire is just over that ridge, Jones.', (JON_P[0], JON_P[1], JON_P[2] + 1.0 * CS.M), 6.5, 215, 150, 16),
    (('ss_i2v4', 'AnyaHQ'), "ANYA: Something is going on at Al-Saqr. Night flights, General Dhari running the base, an arms broker flying in. We don't know what they're doing.",
     ('hq', (4.05, -2.25, -1.30), (4.28, -0.85, -1.58), (4.10, -2.05, -1.33))),
    (('ss_col3', 'Soldier'), 'GENERAL DHARI: Everything below must be ready by dawn. Nothing leaves this base before that.', ('office', OCAM0, OLOOK0)),
    (('ss_kral2', 'Mark'), 'KRAL: Then our business is done, General. The contract and the routes stay on my laptop until I am paid.',
     ('office', OCAM1, OLOOK1)),
    (('orig', 'cv31_intro_04_jones'), "JONES: Sure. What's the plan?", ('still', GEST0, GLOOK, GEST0)),   # (no camera prop any more: on the guards)
    (('orig', 'cv10_camp_02_guard'), "GUARD: This is boring, nothing's happening here. I don't know why security is so tight.",
     ('cctv', GCCTV0, GLOOK)),
    (('orig', 'cv10_camp_03_guard'), "GUARD: Yeah I agree. It's not like anybody could get in here anyway.", ('cctv', GCCTV1, GLOOK)),
    ('ss_cs2', 'ANYA: First, the south compound. Shut down both power generators. That kills the cameras and unlocks the sewer.',
     map_feed((402651.0, 410186.0, _gz((402651.0, 410186.0)) + 1.6 * CS.M), 'generators')),
    ('ss_cs3', 'ANYA: The sewer runs under the hills, straight into the northern airbase.',
     map_feed(up(P(3927), 1.5), 'sewer hut')),
    ('ss_cs4v4', "ANYA: Their server is in the basement of the west admin building. Hack it, and we find out what this place really is.",
     mast_feed((ADMIN[0] + 25.0 * CS.M, ADMIN[1] - 30.0 * CS.M), up(ADMIN, 6), 'admin')),
    ('ss_cs5d', "ANYA: Kral keeps the sale records on his laptop, in the barracks east of the hangar. Take it.",
     map_feed(up(EASTB, 2), 'east block')),
    ('ss_cs5v4', "ANYA: And two helicopters on the airfield. If this goes wrong, the whole garrison flies after you.",
     mast_feed((P(3904)[0] - 14.0 * CS.M, P(3904)[1] + 10.0 * CS.M), up(P(3904), 1.5), 'helicopters')),
    ('ss_cs6v4', "ANYA: Get in quietly. Once we know what we're dealing with, we get you out.",
     ('cctv', TCAM, TLOOK)),
    (('orig', 'cv21_midro_02_arab'), 'OFFICER (radio): The Sun sets early tonight.', ('still', JCAM0, JLOOK, JCAM1)),
    (('orig', 'cv21_midro_03_arab'), 'OFFICER (radio): Easy money. I go home now.', ('still', JCAM1, JLOOK, JCAM1)),
    (('ss_hq7', 'AnyaHQ'), 'ANYA: You land at dusk, and the sandstorm is your only cover. Good luck, Jones.',
     ('hq', (4.15, -2.10, -1.35), (4.28, -0.85, -1.58), (4.05, -2.25, -1.30))),
    (('orig', 'cv24_intro_05_jones'), "JONES: Let's do it.", ('still', JS_CAM0, JS_LOOK, JS_CAM1)),
    (None, '', [((JON_P[0] + 30.0 * CS.M, JON_P[1] + 90.0 * CS.M, JON_P[2] + 120.0 * CS.M), (JON_P[0], JON_P[1], JON_P[2] + 1.0 * CS.M)),
                ((JON_P[0] + 0.5 * CS.M, JON_P[1] - 1.5 * CS.M, JON_P[2] + 2.0 * CS.M), (JON_P[0], JON_P[1] + 6.0 * CS.M, JON_P[2] + 1.0 * CS.M))], 7.5),
]
if 'hqcam' in DBG:                                         # 11-01 test: three HQ camera angles on Anya, 1 line each
    INTRO = [(('ss_hq1', 'AnyaHQ'), INTRO[0][1], ('hq', (3.3, -1.9, -1.35), (4.28, -0.85, -1.55), (3.3, -1.9, -1.35))),
             (('ss_hq7', 'AnyaHQ'), INTRO[-2][1], ('hq', (3.0, -0.6, -1.30), (4.28, -0.85, -1.55), (3.0, -0.6, -1.30))),
             (('ss_hq1', 'AnyaHQ'), INTRO[0][1], ('hq', (4.0, -2.2, -1.30), (4.28, -0.85, -1.55), (4.0, -2.2, -1.30))),
             (('orig', 'cv10_camp_02_guard'), INTRO[2][1], ('cctv', GCCTV0, GLOOK)),
             (('orig', 'cv10_camp_03_guard'), INTRO[3][1], ('cctv', GCCTV1, GLOOK))]
OUTRO = [
    ('ss_o1c', 'ANYA: The missile is dead and Dhari has no way to launch it now, Jones.', ('office', CONT_CAM, CONT_LOOK)),
    ('ss_o2', 'ANYA: His office is empty on the cameras. Dhari was gone before you got in.', ('office', OCAM0, OLOOK0)),
    (('ss_hq_o4', 'AnyaHQ'), "ANYA: The server data points to the rail line. He moved the shipment out the same way you are leaving.",
     ('hq', (4.05, -2.25, -1.30), (4.28, -0.85, -1.58), (4.12, -2.0, -1.34))),
    (('orig', 'cv30_camp_04_jones'), 'JONES: Great. Just how I like it.',       # (owner 11-04: his face, close, on the guard van's balcony)
     [(STR.local_to_world(TR_LINE, TR_S, 5, (0.35, -STR.LENGTH[STR.VAN] / 2 - 0.75, STR.FLOOR_Z + 1.62)), STR.local_to_world(TR_LINE, TR_S, 5, (0.0, -STR.LENGTH[STR.VAN] / 2 + 0.6, STR.FLOOR_Z + 1.6))),
      (STR.local_to_world(TR_LINE, TR_S, 5, (0.28, -STR.LENGTH[STR.VAN] / 2 - 0.55, STR.FLOOR_Z + 1.62)), STR.local_to_world(TR_LINE, TR_S, 5, (0.0, -STR.LENGTH[STR.VAN] / 2 + 0.6, STR.FLOOR_Z + 1.6)))]),
    ('ss_o5train', "ANYA: We see you, Jones. That train is heading east, and whatever Dhari loaded is on board. Stay with it - and stay out of sight.",
     [(STR.local_to_world(TR_LINE, TR_S, 5, (9.0, -9.0, 2.2)), STR.local_to_world(TR_LINE, TR_S, 5, (0.0, -5.0, 2.0))),
      (STR.local_to_world(TR_LINE, TR_S, 5, (9.0, 27.0, 2.2)), STR.local_to_world(TR_LINE, TR_S, 5, (0.0, 34.0, 2.0)))]),   # (the train pulls away east)
]
# the mid-mission cut-in (owner 11-02 'green CCTV shots of talking guards in the mission'): the power dies, a base camera
# catches two guards in the south yard (squads + Jones are off while it runs, the break key skips it - Kit mids pattern)
MGA = (402651.0 + 3.0 * CS.M, 410186.0 + 2.5 * CS.M)
MGB = (402651.0 + 5.2 * CS.M, 410186.0 + 3.6 * CS.M)
MMID = ((MGA[0] + MGB[0]) / 2, (MGA[1] + MGB[1]) / 2)
_mc = (MMID[0] - 6.0 * CS.M, MMID[1] - 5.0 * CS.M)
MCAM = (_mc[0], _mc[1], max(_gz(_mc) + 3.5 * CS.M, _gz(MMID) + 4.0 * CS.M))
MLOOK = (MMID[0], MMID[1], _gz(MMID) + 1.4 * CS.M)
MIDCS = [(('ss_mid1', 'Soldier'), 'GUARD: The power is out! Check the generators, now!', ('cctv', MCAM, MLOOK))]
for _n, _p, _g in (('console', (257.7, 207.93, SB.F + 2.4), math.pi), ('chip', (246.02, 236.9, SB.F + 3.0), -math.pi / 2), ('hall', (250.0, 208.25, SB.F + 4.4), 0.0),
                   ('missile', (236.0, 255.93, SB.F + 12.0), math.pi), ('gate', (267.93, 229.0, SB.F + 7.0), math.pi / 2), ('lift room', (158.6, 232.9, -11.2), -math.pi / 2)):
    feed_cam(V.U(_p), _g, _n)
feed_cam(V.U((50.5, 234.85, _SI.ceiling(globals(), 'N') if INTRO2 else 7.2)), 0.0, 'office')         # (walked: the server room is x 48.5-52.6, y 234.9-240.5)
feed_cam(V.U((_SI.CAM_S[0] if INTRO2 else 50.2, 240.5, _SI.ceiling(globals(), 'S') if INTRO2 else 7.2)), math.pi, 'office side')
cam_obj(GCCTV0, GLOOK, name='gate', pole=True)
cam_obj(GCCTV1, GLOOK, name='gate 2', pole=True)
IK, ICAP = _SI.keys(globals()) if INTRO2 else shots(INTRO, 'SS_CS', fade_in=True)
_cq = [float(m.arg(COMPUTER, k_)) for k_ in (3, 4, 5, 8)]
_cn = min(GRAPHS[2], key=lambda n_: math.dist(n_['pos'][:3], _cq[:3]))['pos']
GEN_P = (_cn[0], _cn[1], _cn[2])
GEN_CAM = (_cq[0] + 2.4 * 4096, _cq[1] - 1.4 * 4096, _cn[2] + 1.75 * 4096)
GEN_CAM2 = (_cn[0] - 1.6 * 4096, _cn[1] + 1.2 * 4096, _cn[2] + 1.6 * 4096)
_lz = (SD_X + 24.0, SD_Y + 12.0, _bh(SD_X + 24.0, SD_Y + 12.0))
LZ_CAM, LZ_LOOK = V.U((SD_X + 62.0, SD_Y - 6.0, _lz[2] + 9.0)), V.U((_lz[0], _lz[1], _lz[2] + 4.0))
_ftg = V.U((165.5, 243.0, -5.8))
OUTRO += [('ss_o6heli', "ANYA: Helicopters, Jones, right behind you. They're landing on both sides of the line and pouring into that tunnel. You got out just in time.", ('still', LZ_CAM, LZ_LOOK, V.U((SD_X + 58.0, SD_Y - 2.0, _lz[2] + 8.0)))),
          ('ss_o7air', "ANYA: The whole airbase is awake now. They are running, and they are looking for you.", ('still', V.U((SD_X + 30.0, SD_Y - 18.0, _lz[2] + 16.0)), V.U((SD_X - 2.0, SD_Y, _lz[2] + 3.0)), V.U((SD_X + 24.0, SD_Y - 14.0, _lz[2] + 13.0)))),
          (('ss_dhari1', 'David'), "GENERAL DHARI: Show me the server room. Again... stop. There.", ('office', GEN_CAM, (_cn[0], _cn[1], _cn[2] + 1.5 * 4096))),
          (None, '', ('office', V.U((257.7, 206.8, SB.F + 1.8)), V.U((256.0, 206.5, SB.F + 1.5))), 2.1),
          (('ss_dhari3', 'David'), "GENERAL DHARI: That is the guidance chip. He took it with his own hands.", ('office', V.U((246.9, 236.9, SB.F + 2.9)), V.U((248.3, 238.0, SB.F + 1.3)))),
          (None, '', ('office', V.U((250.0, 209.0, SB.F + 4.2)), V.U((258.0, 221.0, SB.F + 1.1))), 2.1),
          (('ss_dhari2', 'David'), "GENERAL DHARI: One man did all this. He has the chip. Find out who sent him... we are going to hunt him.", ('office', GEN_CAM2, (_cn[0], _cn[1], _cn[2] + 1.6 * 4096)))]
TRAIN_SHOT = 4                                             # (the fifth line of OUTRO: the train pulls away; everything after it happens behind him)
if OUTRO2:
    OK_, OCAP = _SO.keys(globals())
else:
    OK_, OCAP = shots(OUTRO, 'SS_OUT', fade_out=True)
    OK_[-3]['pos'] = up(OK_[-4]['pos'], 35)                    # last outro shot: crane up over the extraction, then fade out
    OK_[-2]['pos'] = OK_[-1]['pos'] = OK_[-3]['pos']
for k_ in [k_ for k_ in IK + OK_ if k_.get('tod', -1.0) < 0 and not k_.get('indoor')]:   # (HQ / office keys: indoors)
    assert k_['pos'][2] > TERR.height(k_['pos'][0], k_['pos'][1]) + 1.0 * CS.M, ('camera under the terrain', k_['pos'])
    assert k_['pos'][2] < TERR.height(k_['pos'][0], k_['pos'][1]) + 155.0 * CS.M, ('camera too high: overhead flicker (recon.py)', k_['pos'])
print('cutscenes: highest camera %.0f m over the ground' % max((k_['pos'][2] - TERR.height(k_['pos'][0], k_['pos'][1])) / CS.M
                                                                for k_ in IK + OK_ if k_.get('tod', -1.0) < 0 and not k_.get('indoor')))
CSI = CS.add_intro(m, nid, 4087, IK, ICAP)
CSO = CS.add_outro(m, nid, 4087, OK_, OCAP, 'StatusMessage_%d.isFinishedDisplay' % DONE)
# the two gate guards of the intro: EditBoneObj actors (squads are off in cutscenes), the L11 talking pair clips, their own
# lines lip-synced (tools/lipsync.py: the StatusMessage 'Morph QTask IDs' = the speaking actor)
import lipsync
K.PFX = 'SS'
GA = 0 if INTRO2 else K.actor(CSI['intro'], (GUARD_A[0], GUARD_A[1], _gz(GUARD_A)), GUARD_B, 'alarm1_1', anim='right_guard_talking',   # (item 9: no stand_talk head scratch)
             weapon='107_01_1', name='intro gate guard A')
GB = 0 if INTRO2 else K.actor(CSI['intro'], (GUARD_B[0], GUARD_B[1], _gz(GUARD_B)), GUARD_A, 'alarm2_1', anim='left_guard_talking',
             weapon='107_01_1', name='intro gate guard B')
_GCAP = {c_[3]: c_ for c_ in ICAP + OCAP}                 # (review: by the voice def, not the shot order)


def _cap_msg(key_):
    mid_ = [t_ for t_ in m.find('StatusMessage') if str(lit(m.byid[t_].args[2])) == 'caption ' + key_]
    assert len(mid_) == 1, key_
    return mid_[0]


for cap_, aid_ in (() if INTRO2 else ((_GCAP['cv10_camp_02_guard'], GA), (_GCAP['cv10_camp_03_guard'], GB))):
    lipsync.link(m, _cap_msg(cap_[1]), [aid_])
print('cutscenes: intro gate guards %d / %d lip-synced (original L11 lines, on two CCTV feeds)' % (GA, GB))
# --- v4 finale, the cutscene: the vehicle gate rolls up (hall A camera) -> inside the sand door at the end of the truck tunnel, the
# blast door opening on the desert -> outside, the sand door open, Jones in it -> Anya's satellite pass over the train: two
# reinforcement helicopters down beyond it. Then Jones stands outside the sand door (Human_PopPosition, L26 'snap human player').
_gl = (SB.X1, 222.0, SB.F + 3.0)
_gc, _gc2 = (246.0, 214.0, SB.F + 5.5), (254.0, 219.0, SB.F + 3.0)
_in0, _in1 = (SD_X - 13.0, SD_Y - 1.5, SD_G + 2.4), (SD_X - 7.0, SD_Y - 0.8, SD_G + 2.0)   # inside the tunnel, toward the sand door
_sdd = (SD_X + 1.0, SD_Y, SD_G + 2.6)
_trc = STR.local_to_world(TR_LINE, TR_S, 2, (0.0, 0.0, 0.0))
_tra = STR.local_to_world(TR_LINE, TR_S, 0, (-16.0, 4.0, 22.0)); _trb = STR.local_to_world(TR_LINE, TR_S, len(STR.CONSIST) - 1, (-16.0, -4.0, 22.0))   # (rc7k K1: 22 m up, 16 m out on the van door's side,
_tla = STR.local_to_world(TR_LINE, TR_S, 0, (0.0, 4.0, 1.5)); _tlb = STR.local_to_world(TR_LINE, TR_S, len(STR.CONSIST) - 1, (0.0, 0.0, 1.5))             #  looking at the cars: loco to the freight van, the open door at the end)   # (judge F10: along the train, not over empty rails)
GATECS = [('ss_gate1', "ANYA: The gate is moving, Jones.", [(V.U(_gc), V.U(_gl)), (V.U(_gc2), V.U(_gl))])]
_lv = ('ss_leave2', "ANYA: Jones, I have you on the satellite. That train is getting up steam, the only way out of here.") if OUTRO2 else (
    'ss_leave', "ANYA: Jones, I have you on the satellite. That train is getting up steam, the only way out of here. Run for the guard van at the back, now!")
SANDCS = [('ss_gate2', "ANYA: The far door is opening. Daylight - well, sandstorm.", [(V.U(_in0), V.U(_sdd)), (V.U(_in1), V.U(_sdd))]),
          (_lv[0], _lv[1], ('thermal', _tra, _trb, _tla, _tlb))]
GK, GCAP = shots(GATECS, 'SS_GT')
CSG = CS.add_outro(m, nid, 4087, GK, GCAP, '0')              # (owner 11-04: no cutscene at the gate; the line below instead)
msg('SS_GATEUP', 'SS the gate rolls up', GATE_OPEN, "ANYA: It's rolling up. That ramp climbs straight to the desert, Jones. Move!", 5.0, 'ss_gateup', tid=GATEUP)
m.set(CSG['outro'], 2, 'Mid-game Cutscene (vehicle gate)')
# (S17 owner 11-15 'there is a point to go in the computer place and then open it ... shows animation of the gates being open'): the console
#  finishes -> a 4.5 s shot from beside the cage's mast camera: the leaf rolls up (open rule: launch clock > 1 s), the scientists inside; Esc skips
_cg0, _cg1, _cgl = V.U((SB.PIT[0] - 6.2, SB.PIT_C[1] + 3.4, SB.F + 2.3)), V.U((SB.PIT[0] - 4.6, SB.PIT_C[1] + 2.4, SB.F + 1.9)), V.U((SB.PIT[0] + 0.6, SB.PIT_C[1], SB.F + 1.5))
CGK, CGCAP = shots([(None, '', [(_cg0, _cgl), (_cg1, _cgl)], 4.5)], 'SS_CG')
CSCG = CS.add_outro(m, nid, 4087, CGK, CGCAP, 'GenericTBA_%d.isFinished' % CAGE_PC)
m.set(CSCG['outro'], 2, 'Mid-game Cutscene (missile cage gate)')
SK, SCAP = shots(SANDCS, 'SS_SD')
CSS = CS.add_outro(m, nid, 4087, SK, SCAP, 'GenericTBA_%d.isFinished' % SAND_PAD)
m.set(CSS['outro'], 2, 'Mid-game Cutscene (sand door)')
K.actor(CSS['outro'], V.U((SD_X - 3.0, SD_Y - SB.TW + 1.1, SD_G)), V.U(_sdd), 'jones2_1', anim='stand', weapon='110_01_1', name='finale Jones at the sand door')
_atmos.ensure_decl(m, 'SequenceCommand')
# (loop 1: when the sand door rolls up the storm comes in: sand blown down the tunnel for a quarter of a minute, the wind heard inside)
import srgunship as _SGS
_atmos.ensure_decl(m, 'Smoke')
_gust = [_SGS.smoke(nid, 'SS sand blowing in', V.U((SD_X + 2.0, SD_Y + o_, SD_G + 1.0 + abs(o_) * 0.3)), math.pi / 2, math.pi / 2, 160, 1.2, 0.25, 5.0, 9.0, (0.72, 0.58, 0.40), 3.0, 3.0,
                 3, 1.6, 0.5, 0.45, 0.0, '', cutoff=120.0, mode=0) for o_ in (-3.0, 0.0, 3.0)]
m.add_child(LOGIC, T(nid(), 'ConditionalContainer', 'SS sand comes in at the sand door', 'Door_%d.nDoorOpenTicks > 0 && Door_%d.nDoorOpenTicks < 25 * GAME_FREQUENCY' % (SAND_DOOR, SAND_DOOR), '', '', children=_gust))
# --- loop 2: the ramp is alive: past the first bend a troop truck comes down from the checkpoint, headlamps on, and runs to the gate - get out of the lane
#  (_trs, _trq, _trl, _trp, _trg2: the truck path, made before the graphs - S15 trk_blocked)
_trb2 = [-math.atan2(q_[2] - TUN.at(float(s_) - 1.0)[2], 1.0) for s_, q_ in zip(_trs, _trq)]
_brake = lambda d_: 6.0 + 3.6 * math.sqrt(2.0 * 3.0 * d_)   # (owner 87: it crawled the last 15 m with the wheels turning. Now a truck's brake: 3 m/s2 from speed, km/h)
_trv = [min(14.0 + 8.0 * k_, 46.0, _brake(5.0 * (len(_trs) - 1 - k_)) if TRUCKS2 else 16.0 * (len(_trs) - 1 - k_) + 10.0) for k_ in range(len(_trs))]
TROOP = nid()
m.add_child(LOGIC, T(TROOP, 'EditRigidObj', 'SS troop truck on the ramp', *_trp[0], 0.0, float(_trb2[0]), float(_trg2[0]), 'ss_trk2_1' if TRUCKS2 else 'ss_trk_1', 5, False, False))
TGLASS = {}
if TRUCKS2:
    TGLASS[TROOP] = nid(); m.add_child(TROOP, TK.glass(T, TGLASS[TROOP], _trp[0], _trb2[0], _trg2[0]))
TRK_AT = nid()
_q70 = TUN.at(next((float(p_[6:]) for p_ in DEBUG.split(';') if p_.startswith('g2trk=')), 70.0))
m.add_child(LOGIC, T(TRK_AT, 'AreaActivate', 'SS Jones on the long ramp', *V.U((_q70[0], _q70[1], _q70[2] + 2.0)), 0.0, 0.0, 0.0, 12.0 * 4096, 5.0 * 4096, 7.0 * 4096, 'CRITERIA_HUMAN0'))
if 'review' in DBG:
    m.set(TRK_AT, 3, -4096000.0)                           # (the stands teleport through it: no trucks in the review)
import cine as _cine
for _t in ('SplinePathDynCubeObj', 'SplinePathNodeQTask', 'SplinePathGuideQTask', 'SequenceCommand'):
    _atmos.ensure_decl(m, _t)
_sp, _ = _cine.Cine.spline(_types.SimpleNamespace(K=K), TROOP, _trp, _trv, [float(g_) for g_ in _trg2], name='SS troop truck path')
_kn = 0
for t_, d_, p_ in tasks(_sp):
    if lit(t_.args[1]) == 'SequenceCommand':
        t_.args[3] = v('AreaActivate_%d.nActive' % TRK_AT)
    elif lit(t_.args[1]) == 'SplinePathNodeQTask':
        t_.args[7] = v(float(_trb2[_kn])); _kn += 1
for _t in _sp:
    m.add_child(LOGIC, _t)
_atmos.ensure_decl(m, 'LevelTimer')
TRK_T = nid()
m.add_child(LOGIC, T(TRK_T, 'LevelTimer', 'SS second truck delay', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'AreaActivate_%d.nActive || LevelTimer_%d.nTick > 0' % (TRK_AT, TRK_T), '', False))
TROOP2 = nid()
_t2c = nid()
m.add_child(LOGIC, T(_t2c, 'ConditionalContainer', 'SS second troop truck', 'LevelTimer_%d.nTick > 7 * GAME_FREQUENCY' % TRK_T, '', '',
                     children=[T(TROOP2, 'EditRigidObj', 'SS troop truck 2', *_trp[0], 0.0, float(_trb2[0]), float(_trg2[0]), 'ss_trk2_1' if TRUCKS2 else 'ss_trk_1', 5, False, False)]))
if TRUCKS2:
    TGLASS[TROOP2] = nid(); m.add_child(TROOP2, TK.glass(T, TGLASS[TROOP2], _trp[0], _trb2[0], _trg2[0]))
_sp2, _ = _cine.Cine.spline(_types.SimpleNamespace(K=K), TROOP2, _trp[:-3], [min(v_, _brake(5.0 * (len(_trv) - 4 - k_))) for k_, v_ in enumerate(_trv[:-3])] if TRUCKS2 else _trv[:-3], [float(g_) for g_ in _trg2[:-3]], name='SS troop truck 2 path')
_kn = 0
for t_, d_, p_ in tasks(_sp2):
    if lit(t_.args[1]) == 'SequenceCommand':
        t_.args[3] = v('LevelTimer_%d.nTick > 7 * GAME_FREQUENCY' % TRK_T)
    elif lit(t_.args[1]) == 'SplinePathNodeQTask':
        t_.args[7] = v(float(_trb2[_kn])); _kn += 1
for _t in _sp2:
    m.add_child(LOGIC, _t)
_atmos.ensure_decl(m, 'ExplodeObject')
if TRUCKS2:
    for _t in ('RotateAttachment', 'EditBoneObj', 'SequenceCommand', 'SoundGenerator'):
        _atmos.ensure_decl(m, _t)
    for _tr, _sq, _nl in ((TROOP, _sp, len(_trp)), (TROOP2, _sp2, len(_trp) - 3)):
        _gd = next(lit(t_.args[0]) for t_, d_, p_ in tasks(_sq) if lit(t_.args[1]) == 'SplinePathGuideQTask')
        for _c in TK.wheels(T, nid, _gd, _nl - 1) + [TK.engine(T, nid, _gd, _nl - 1)]:
            m.add_child(_tr, _c)
        if _tr == TROOP:                                   # (judge A7 11-14: truck 1's horn as it starts down, beside Anya's warning; on the glass child: a 2nd SoundGenerator on the truck was never heard, rc7s18 ear)
            m.add_child(TGLASS[_tr], TK.horn(T, _gd))
    _hv = {0: [], 1: []}
_tt, _tk = 0.0, []
_tc = [0.0]                                                # (the clock at each node of truck 1)
_v2n = [min(v_, _brake(5.0 * (len(_trv) - 4 - k_))) if TRUCKS2 else v_ for k_, v_ in enumerate(_trv[:-3])]   # (truck 2's own speeds and clock, as its spline)
_tc2 = [0.0]
for _k in range(1, len(_v2n)):
    _tc2.append(_tc2[-1] + math.dist(_trp[_k - 1], _trp[_k]) / 4096.0 / (0.5 * (_v2n[_k - 1] + _v2n[_k]) / 3.6))
for _k, _p in enumerate(_trp):
    if _k:
        _d = math.dist(_trp[_k - 1], _p) / 4096.0
        _tt += _d / (0.5 * (_trv[_k - 1] + _trv[_k]) / 3.6)
        _tc.append(_tt)
    _hw = min(1.0, 3.2 / max(_trv[_k] / 3.6, 1.0))
    _ld = lambda x_: x_ if not TRUCKS2 or x_ < 0 else max(0.0, x_ - TK.LEAD_S)   # (REVIEW_rc7m #1: the hit windows open TK.LEAD_S earlier, before the nose reaches him)
    _w1 = '(LevelTimer_%d.nTick > 0 && LevelTimer_%d.nTick > %.2f * GAME_FREQUENCY && LevelTimer_%d.nTick < %.2f * GAME_FREQUENCY)' % (TRK_T, TRK_T, _ld(_tt - _hw), TRK_T, _ld(_tt + _hw))   # (11-07: nTick > 0: before the timer starts tick 0 lies inside the first windows, the parked truck killed a man walking past)
    if _k < len(_trp) - 3:                                 # (judge F08: truck 2 brakes to its own stop 3 nodes early, so it ran on truck 1's clock + 7 s and 'hit' Jones before it got there)
        _tt2 = _tc2[_k]; _hw2 = min(1.0, 3.2 / max(_v2n[_k] / 3.6, 1.0))
        _w2 = '(LevelTimer_%d.nTick > %.2f * GAME_FREQUENCY && LevelTimer_%d.nTick < %.2f * GAME_FREQUENCY)' % (TRK_T, _ld(7.0 + _tt2 - _hw2), TRK_T, _ld(7.0 + _tt2 + _hw2))
    _za, _zb = nid(), nid()
    _tkd = np.subtract(_trp[min(_k + 1, len(_trp) - 1)], _trp[max(_k - 1, 0)])   # (judge F08: 5 x 5 m boxes 'hit' a man standing beside the 2.5 m truck; 2.6 m across a straight lane)
    _ax = int(abs(_tkd[1]) > abs(_tkd[0])); _tn = abs(_tkd[1 - _ax]) / max(abs(_tkd[_ax]), 1e-6)
    _bw = ((6.0, 2.6) if _ax == 0 else (2.6, 6.0)) if TRUCKS2 and _tn < 0.05 else (5.0, 5.0)   # (straight lanes only: the boxes are axis-aligned, on bends a narrow box leaves gaps (review 11-08))
    m.add_child(LOGIC, T(_za, 'AreaActivate', 'SS truck lane %d' % _k, _p[0], _p[1], _p[2] + 1.6 * 4096.0, 0.0, 0.0, 0.0, _bw[0] * 4096, _bw[1] * 4096, 4.0 * 4096, 'CRITERIA_HUMAN0'))
    if TRUCKS2:                                            # (owner 65: a hit is a short cutscene, then he dies where he stood)
        for _w_, _h_ in ((_w1, 0), (_w2, 1)):
            if _h_ == 1 and _k >= len(_trp) - 3:
                continue
            _hz = nid(); _hv[_h_].append(_hz)
            m.add_child(LOGIC, T(_hz, 'EditVariable', 'SS truck hit %d' % _k, 0.0, 0.0, 0.0, 0, 'EditVariable_%d.nValue == 0 && AreaActivate_%d.nActive && %s' % (_hz, _za, _w_), ''))
        _hk = '(HITCS)'
        m.add_child(LOGIC, T(_zb, 'ExplodeObject', 'SS run over %d' % _k, _p[0], _p[1], _p[2] + 1.0 * 4096.0, 0.0, 0.0, 0.0, 'none', 'none', 100.0, *TK.BLAST, 0.0, 1, 1,
                             'AreaActivate_%d.nActive && !HumanPlayer_0.isDead && %s' % (_za, _hk), ''))   # (judge F07: after the hit shot this backup blast hit the dead body under the parked truck and pushed it through the floor, z -1600 m, g9k2)
    else:
        m.add_child(LOGIC, T(_zb, 'ExplodeObject', 'SS run over %d' % _k, _p[0], _p[1], _p[2] + 1.0 * 4096.0, 0.0, 0.0, 0.0, 'none', 'none', 100.0, 30.0, 40.0, 50.0, 0.0, 1, 1,
                             'AreaActivate_%d.nActive && (%s)' % (_za, _w1 if _k >= len(_trp) - 3 else _w1 + ' || ' + _w2), ''))
_tk.append(_tt)
print('v5 trucks: %d lethal zones, %.1f s down the ramp' % (len(_trp), _tt))
if TRUCKS2:
    _hd = []
    for _h_, _tr in enumerate((TROOP, TROOP2)):
        _hx = nid()
        m.add_child(LOGIC, T(_hx, 'EditVariable', 'SS truck hit Jones %d' % _h_, 0.0, 0.0, 0.0, 0, 'EditVariable_%d.nValue == 0 && !HumanPlayer_0.isDead && (%s)' % (_hx, ' || '.join('EditVariable_%d.nValue == 1' % z_ for z_ in _hv[_h_])), ''))
        _hd.append(TK.hit_cutscene(m, nid, T, 4087, K, _tr, _trp[0], float(_trg2[0]), 'EditVariable_%d.nValue == 1' % _hx, 'jones2_1'))
    TK.halt_guides(m, T, nid, {TROOP: _hd[0]['cs'], TROOP2: _hd[1]['cs']})   # (REVIEW_rc7m #1: each truck stops at its hit, no body under, on or pushed through the floor by a truck)
    _hx = ' || '.join('CutScene_%d.nTick > %.2f * GAME_FREQUENCY' % (d_['cs'], TK.BACKUP_S) for d_ in _hd)   # (rc7k h06: when the bumper blast missed, the backup fired after the shot, a full-screen glare in play; now inside the shot's black, g9g1x-g4x)
    for t_, d_, p_ in tasks(m.stmts):
        if lit(t_.args[1]) == 'ExplodeObject' and isinstance(t_.args[-2], Str) and '(HITCS)' in str(t_.args[-2]):
            t_.args[-2] = v(str(t_.args[-2]).replace('(HITCS)', '(%s)' % _hx))
    if 'noai' not in DBG and 'noenemies' not in DBG:      # (the men: behind the tailgate, hidden from Jones by the truck, 2 s after it stops)
        _sv = lambda: sum(math.dist(_trp[k_ - 1], _trp[k_]) / 4096.0 / (0.5 * (_v2[k_ - 1] + _v2[k_]) / 3.6) for k_ in range(1, len(_v2)))
        _v2 = [min(v_, _brake(5.0 * (len(_trv) - 4 - k_))) for k_, v_ in enumerate(_trv[:-3])]
        for _h_, (_tr, _end, _gm, _at, _key) in enumerate(((TROOP, _trp[-1], float(_trg2[-1]), _tt, 'U truck troops 1'), (TROOP2, _trp[-4], float(_trg2[-4]), 7.0 + _sv(), 'U truck troops 2'))):
            _cc = nid()
            _gd = next(lit(t_.args[0]) for t_, d_, p_ in tasks(m.stmts) if lit(t_.args[1]) == 'SplinePathGuideQTask' and lit(t_.args[4]) == _tr)
            _arr = 'SplinePathGuideQTask_%d.vPosition >= %.2f' % (_gd, (len(_trp) - 1 if _tr == TROOP else len(_trp) - 4) - 0.05)   # (review 11-13: he climbs out only once his truck has stopped at its last node)
            _tk1 = 'LevelTimer_%d.nTick > %.1f * GAME_FREQUENCY' % (TRK_T, _at + 1.0)
            if TRKARR:                                     # (N6: no men at the planned stop while a hit has halted the truck short of it; the riders stay on the halted truck)
                _tk1 = '%s && %s' % (_arr, _tk1)
            TK.crew(m, T, nid, _tr, _trp[0], float(_trg2[0]), CSFM, '!(%s)' % _tk1, actor_driver=False)   # (owner 102: riders gone and real soldiers at the tailgate on the same tick)
            # owner 118: a real driver. L25 carries real soldiers on a moving helicopter (an AIType_OnVehicle squad under it), but a soldier there would not play
            # the seated driving clip - he stood beside the cab (g9dv2, g9dv3). So the cab has dark glass (tools/sstruck.py) and nobody sits at the wheel to be shot;
            # when the truck stops the driver steps down by the far-side door, a real soldier from his first visible frame, and fights with the others
            _ecc = nid()                                   # (owner G09b: he sits at the wheel behind clear glass until the stop, climbs out for TK.CLIMB_S, then stands at the door as a real soldier)
            _tkc = '%s && LevelTimer_%d.nTick > %.2f * GAME_FREQUENCY' % (_arr, TRK_T, _at + 0.2)
            _tkd = '%s && LevelTimer_%d.nTick > %.2f * GAME_FREQUENCY' % (_arr, TRK_T, _at + 0.2 + TK.DRIVER_CLIMB_S)
            TK.driver(m, T, _tr, _trp[0], float(_trg2[0]), CSFM[0], '!(%s)' % _tkc, '(%s) && !(%s)' % (_tkc, _tkd))
            m.add_child(LOGIC, T(_ecc, 'ConditionalContainer', 'SS %s driver steps down' % _key, _tkd, '', ''))
            # (S16 owner 11-15: they came for Jones. Fight nodes beside the cab (lane side), in front of the nose, by the west wall - picked by position
            #  on the truck-free graph 11 (S15); the look node is down the ramp, where he comes from. R-ARRIVE scripts, the L15 originals' way)
            _fn, _used = [], set()
            for _lx, _ly in ((-1.0, -2.2), (-5.5, -1.5), (-4.5, -3.8)):
                _wp = TK.rot(_end, (_lx, _ly, 0.0), _gm)
                _q = min((q_ for q_ in GRAPHS[11] if q_['id'] not in _used), key=lambda q_: math.hypot(q_['pos'][0] - _wp[0], q_['pos'][1] - _wp[1]))
                _used.add(_q['id']); _fn.append(_q['id'])
            _dn = min(GRAPHS[11], key=lambda q_: math.hypot(q_['pos'][0] / 4096.0 - TUN.at(95.0)[0], q_['pos'][1] / 4096.0 - TUN.at(95.0)[1]))['id']
            print('S16 %s: fight nodes %s, look node %d' % (_key, _fn, _dn))
            _ed = dict(pos=TK.rot(_end, TK.DOOR + (0.0,), _gm), model=CSFM[0], weapons=AK, ai_type=C3T, graph=11, gamma=round(_gm + math.pi / 2, 6))
            K.patrol_route(11, _ed['pos'], route_m=(14.0, 34.0))   # (no longer used: the draw keeps every later random pick where it was)
            _ed['ai'] = arrive_ai(arrive_counter(_ecc, _key + ' driver'), _fn[0], _dn)
            SQUAD_IDS[_key + ' driver'] = m.squad(_ecc, _key + ' driver', 'AIType_Offensive', [_ed], alarm_switch=-1, alarm_control=-1)
            ENEMY_COUNT[0] += 1
            m.add_child(LOGIC, T(_cc, 'ConditionalContainer', 'SS ' + _key, _tk1, '', ''))
            _tcnt = arrive_counter(_cc, _key)
            _mem = [dict(pos=TK.rot(_end, (a_, b_, 0.0), _gm), model=CSFM[k_ % len(CSFM)], weapons=w_, ai_type=C3T, graph=11, gamma=round(_gm + math.pi / 2, 6)) for k_, ((a_, b_), w_) in enumerate(zip(TK.TROOPS[:2], (AKG, MG)))]   # (S16: they face down the ramp, where Jones is; they faced up it)   # (owner 118: two at the tailgate, the driver is the third; the Human list stays under 128)
            for _k2, _d in enumerate(_mem):                # (owner 87: they come on down the ramp, they don't stand behind the truck until someone finds them; lost from the tree before rc1, back 11-08)
                K.patrol_route(11, _d['pos'], route_m=(14.0, 34.0))   # (judge A04, 11-08: the men stay hidden behind the tailgate; the old patrol's draw kept for the rng)
                _d['ai'] = arrive_ai(_tcnt, _fn[1 + _k2], _dn)
            SQUAD_IDS[_key] = m.squad(_cc, _key, 'AIType_Offensive', _mem, alarm_switch=-1, alarm_control=-1)
            ENEMY_COUNT[0] += len(_mem)
        _ht = alarmai.Hunt(m, nid, GRAPHS, GEDGES, U_ALARM, HUNT2.alarm_control, LOGIC, pfx='ST', cell_m=30.0, reach_m=240.0, distress_m=30.0, backup_m=45.0, run_m=60.0)
        _ht.build(exclude=[s_ for s_ in m.find('AISquad') if s_ not in [SQUAD_IDS[k_][0] for k_ in ('U truck troops 1', 'U truck troops 2', 'U truck troops 1 driver', 'U truck troops 2 driver')]], only_alarmed=False, open_vars=[U_ALARM], cry_alarm=False, loud_alarm=False,
                  react_fight=[SQUAD_IDS[k_][0] for k_ in ('U truck troops 1', 'U truck troops 2', 'U truck troops 1 driver', 'U truck troops 2 driver')], fight_gate=COVERAI, dead_hold=DEADHOLD)   # (N8)
# --- owner 30: a silenced shot is not heard, but a man who sees his mate go down calls it in: 1.5 s to drop the second man too
_wit = []
for _k, _key in enumerate(('U lift landing', 'U room 2', 'U room 3', 'U control room', 'U scientists', 'U tunnel post') if 'noenemies' not in DBG and 'noai' not in DBG else ()):
    _a, _b = SQUAD_IDS[_key][1][:2]
    _wt = nid()
    m.add_child(LOGIC, T(_wt, 'LevelTimer', 'SS witness clock %d' % _k, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'HumanSoldier_%d.isDead || HumanSoldier_%d.isDead || LevelTimer_%d.nTick > 0' % (_a, _b, _wt), '', False))
    _wit.append('(LevelTimer_%d.nTick > 1.5 * GAME_FREQUENCY && !(HumanSoldier_%d.isDead && HumanSoldier_%d.isDead))' % (_wt, _a, _b))
    if 'witfake' in DBG and _key == 'U scientists':     # (test: his mate 'dies' at 8 s, the rest of the chain is real: clock, 1.5 s, hall alarm, 'man down')
        m.set(_wt, 9, 'LevelFlow_10.nTick > 8 * GAME_FREQUENCY || LevelTimer_%d.nTick > 0' % _wt)
_wsaw = ' || '.join(_wit) or '0'
m.set(U_ALARM, 7, 'EditVariable_%d.nValue == 0 && (GenericTBA_%d.isFinished || %s)' % (U_ALARM, GATE_PAD, _wsaw if not GARRISON2 else _wsaw + ' || ' + HUNT2.switch_expr()))
if 'g2alert' in DBG:                                       # (test: the hall alert on a clock)
    m.set(U_ALARM, 7, 'EditVariable_%d.nValue == 0 && LevelFlow_10.nTick > 25 * GAME_FREQUENCY' % U_ALARM)
msg('SS_MANDOWN', 'SS a man saw it', 'EditVariable_%d.nValue == 1 && !GenericTBA_%d.isFinished' % (U_ALARM, GATE_PAD), 'GUARD: Intruder below! Sound the alarm!', 4.0)
# --- owner 31: walk close to two men talking and you read what they say
TALK_LINES = [('U lift landing', 'GUARD: Twelve hours down here and the air still tastes of diesel.'), ('U room 2', 'GUARD: The Russians get a bed. We get a crate.'),
              ('U room 3', 'GUARD: Let him sleep. He pulled the night shift on the pad.'), ('U control room', 'GUARD: The countdown drills again? Who are they planning to frighten?'),
              ('U tunnel post', 'GUARD: Another truck. Nobody tells us what they carry.'), ('N sewer exit yard', 'GUARD: Two trucks left in the night. Nobody says where.'),
              ('N personnel building west', 'GUARD: My cousin says the money stops next month.'), ('N personnel building east', 'GUARD: Did you see that broker? Shoes like a film star.'),
              ('S south gate', 'GUARD: Sand in the rifle again. Clean it or the sergeant eats you.'), ('S large house', 'GUARD: The storm will last till morning. No flights.'),
              ('S sewer entrance guards', 'GUARD: Something is living in that sewer. Listen to it.')]
_ttour = []
TALK = os.environ.get('SS_TALK', '1') == '1' and 'noenemies' not in DBG and 'noai' not in DBG   # (owner 59-60: Iraqi talk and barks, tools/sstalk.py + work/sandstorm/voices, behind this flag until proven)
if TALK:
    import sstalk as _TK
    _TK.stage(globals())
VOICES = TALK and os.environ.get('SS_VOICES', '1') == '1'      # (owner 11-12: his friends' recorded voices, tools/ssvoices.py + work/sandstorm/voices/friends_11-10, behind this flag until proven)
if VOICES:
    import ssvoices as _VC
    _VC.stage(globals())
for _k, (_key, _line) in enumerate(TALK_LINES if 'noenemies' not in DBG and 'noai' not in DBG and not TALK else ()):
    _a, _b = SQUAD_IDS[_key][1][:2]
    _pa, _pb = [[float(m.arg(h_, k_)) for k_ in (3, 4, 5)] for h_ in (_a, _b)]
    _z, _i = nid(), nid()
    m.add_child(LOGIC, T(_z, 'AreaActivate', 'SS within earshot %d' % _k, (_pa[0] + _pb[0]) / 2, (_pa[1] + _pb[1]) / 2, _pa[2] + 1.5 * 4096.0, 0.0, 0.0, 0.0, 15.0 * 4096, 15.0 * 4096, 5.0 * 4096, 'CRITERIA_HUMAN0'))
    _calm = _UA + ' == 0' if _key.startswith('U ') else 'EditVariable_1500.nValue == 0'
    _key2 = 'SS_TALK%d' % _k
    m.add_child(LOGIC, T(_i, 'StatusMessage', 'SS overheard %d' % _k, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'AreaActivate_%d.nActive && !HumanSoldier_%d.isDead && !HumanSoldier_%d.isDead && %s' % (_z, _a, _b, _calm), _key2, '', 'statusmessage', True, False, 5.0, ''))
    m.add_text('messages', _key2, _line)
    _ttour.append(((_pa[0] + _pb[0]) / 2, (_pa[1] + _pb[1]) / 2, _pa[2]))
if 'hearwatch' in DBG:                                     # (test: did anyone notice? the alarm and the sighting count on screen)
    msg('SS_DBGA', 'DEBUG alarm', 'EditVariable_1500.nValue == 1', 'DEBUG: ALARM UP', 30.0)
    msg('SS_DBGU', 'DEBUG hall alarm', 'EditVariable_%d.nValue == 1' % U_ALARM, 'DEBUG: HALL ALARM UP', 30.0)
    msg('SS_DBGS', 'DEBUG spotted', 'HumanPlayer_0.nSpotted > 0', 'DEBUG: SPOTTED', 30.0)
if 'talktour' in DBG:                                      # (test: Jones beside each talking pair in turn, 14 s each)
    m.set(1500, 7, '0')                                    # (a camera must not end the calm in this test)
    _ttour = _ttour[7:]
    _tc = [nid() for _ in _ttour]
    _atmos.ensure_decl(m, 'SequenceCommand')
    m.add_child(LOGIC, T(nid(), 'Container', 'DEBUG talk tour', False, children=[
        T(_tc[k_], 'SequenceCommand', 'DEBUG talk %d' % k_, 'LevelFlow_10.nTick > %d * GAME_FREQUENCY' % (10 + 14 * k_),
          'Human_PopPosition(0, %.3f, %.3f, %.3f)' % (p_[0] / 4096, p_[1] / 4096, p_[2] / 4096 + 0.4), 'TRUE',
          'SequenceCommand_SetCommand(%d)' % (_tc[k_ + 1] if k_ + 1 < len(_tc) else -1)) for k_, p_ in enumerate(_ttour)]))
if 'camtest' in DBG:                                       # (does a bullet break a feed camera?)
    msg('SS_CAMT', 'DEBUG camera', 'SCamera_%d.isDestroyed' % FEEDS['console'], 'DEBUG: CAMERA BROKEN', 30.0)
_tw = None
if globals().get('_hd'):                                   # (engine 11-15, TEAM_RULES A8: the warning box stayed up over the truck hit shot; a ConditionalContainer
    _tw = nid()                                            #  going false takes its StatusMessage off at once (sstalk.py:20, originals L11/L13/L32/L35))
    m.add_child(LOGIC, T(_tw, 'ConditionalContainer', 'SS truck warning (off in the hit shots)', ' && '.join('!ConditionalContainer_%d.isRun' % d_['outro'] for d_ in _hd), '', ''))
TRUCK_MSG = msg('SS_TRUCK', 'SS truck on the ramp', 'AreaActivate_%d.nActive' % TRK_AT, "ANYA: Vehicle on the ramp, coming down fast. Get against the wall!", 4.0, 'ss_truck', parent=_tw)
print('v5 troop truck %d: %d path nodes, %.0f..%.0f m along the tunnel' % (TROOP, len(_trp), _trs[0], _trs[-1]))
# the reinforcements' helicopters: the map's own Hind, landed beyond the train once the satellite sees them
_hind = str(lit(L[3901].args[9]))
HELI_CC = 0
RUN = msg('SS_RUN', 'SS run for the train', CSS['complete'],
          "ANYA: The freight van, Jones, second from the back. The door is open. Go!" if OUTRO2 else "ANYA: Get on the guard van's rear platform, Jones. Go!", 5.0, 'ss_run2' if OUTRO2 else 'ss_run')
print('v5 finale: gate cutscene %d (%.1f s), sand door %d, sand cutscene %d, helicopters %d, hop-on area %d' % (
    CSG['cs'], sum(k_['dur'] for k_ in GK), SAND_DOOR, CSS['cs'], HELI_CC, HOPON))
m.set(DONE, 9, 'StatusMessage_%d.isFinishedDisplay && AreaActivate_%d.nActive && !HumanPlayer_0.isDead' % (RUN, HOPON))   # (qa SK08: after Anya's line)
if OUTRO2:
    _SO.stage(globals())
else:
    # --- v4 outro on the train: Jones (an actor) on the guard van's rear balcony while the outro runs - a child of the van, so he rides
    # along - and the train pulls away east on the last shot (it never moves before: the 'aboard' latch is the hop-on itself)
    _vcc = nid()
    m.add_child(TR_IDS[5], T(_vcc, 'ConditionalContainer', 'SS Jones aboard (outro)', 'ConditionalContainer_%d.isRun' % CSO['outro'], '', ''))
    _bal = STR.local_to_world(TR_LINE, TR_S, 5, (0.0, -STR.LENGTH[STR.VAN] / 2 + 0.6, STR.FLOOR_Z))
    _JVAN = K.actor(_vcc, _bal, STR.local_to_world(TR_LINE, TR_S, 5, (0.0, -30.0, STR.FLOOR_Z + 1.0)), 'jones2_1', anim='stand_talk1, stand_talk2, stand',
                    name='outro Jones on the guard van')
    lipsync.link(m, _cap_msg(_GCAP['cv30_camp_04_jones'][1]), [_JVAN])
    _tlast = OCAP[TRAIN_SHOT][0]
    # 17: two Hinds drop in left and right of the line, soldiers run for the tunnel, a third Hind behind them; 18: the general at the server, Jones on the footage
    _thl = OCAP[TRAIN_SHOT + 1][0]
    _hc = nid()
    _hwhen = 'ConditionalContainer_%d.isRun && CutScene_%d.nTick > %%.2f * GAME_FREQUENCY' % (CSO['outro'], CSO['cs'])
    m.add_child(LOGIC, T(_hc, 'ConditionalContainer', 'SS helicopters land after the train', _hwhen % (_thl - 7.0), '', ''))
    for _k, (_hx_, _hy_, _hyaw, _dt) in enumerate(((_lz[0] - 8.0, _lz[1] + 21.0, 1.6, 0.0), (_lz[0] + 6.0, _lz[1] - 10.0, 1.6, 1.0), (_lz[0] - 26.0, _lz[1] + 2.0, 1.6, 5.0))):
        _hi = nid()
        _hz = _bh(_hx_, _hy_) - 0.85
        _hp = [((_hx_ + 150.0) * 4096, (_hy_ + 40.0) * 4096, (_hz + 70.0) * 4096), ((_hx_ + 40.0) * 4096, (_hy_ + 8.0) * 4096, (_hz + 24.0) * 4096), (_hx_ * 4096, _hy_ * 4096, (_hz + 6.0) * 4096), (_hx_ * 4096, _hy_ * 4096, _hz * 4096)]
        m.add_child(_hc, T(_hi, 'EditRigidObj', 'SS helicopter %d' % (_k + 1), *_hp[0], 0.0, 0.0, _hyaw, _hind, 5, False, False))
        _sp3, _ = _cine.Cine.spline(_types.SimpleNamespace(K=K), _hi, _hp, [150.0, 90.0, 22.0, 6.0], [_hyaw] * 4, name='SS helicopter %d path' % (_k + 1))
        for t_, d_, p_ in tasks(_sp3):
            if lit(t_.args[1]) == 'SequenceCommand':
                t_.args[3] = v(_hwhen % (_thl - 6.5 + _dt))
        for _t in _sp3:
            m.add_child(LOGIC, _t)
    _ths = OCAP[TRAIN_SHOT + 2][0]
    _sc = nid()
    m.add_child(LOGIC, T(_sc, 'ConditionalContainer', 'SS soldiers out of the helicopters', _hwhen % (_ths - 1.6), '', ''))
    for _k, _o in enumerate((-6.0, -3.5, -1.0, 1.5, 4.0, 6.5, -4.5, 3.0, -2.2, 0.4, 2.6, 5.2, -5.2, -0.2)):
        _car = nid()
        _a = (_lz[0] - 6.0 + 1.3 * _k, _lz[1] + 1.0 + _o, _bh(_lz[0] - 6.0 + 1.3 * _k, _lz[1] + 1.0 + _o))
        _b = (SD_X + 1.0, SD_Y + _o * 0.5, SD_G)
        _g = math.atan2(-(_b[0] - _a[0]), _b[1] - _a[1])
        _pa = tuple(c_ * 4096.0 for c_ in _a); _pb = tuple(c_ * 4096.0 for c_ in _b)
        _act = T(nid(), 'EditBoneObj', 'SS running soldier %d' % _k, *_pa, 0.0, 0.0, _g, True, True, 'alarm1_1', True, '107_01_1', '', 'run_forward, run_forward', 1.0, 0.0)
        m.add_child(_sc, T(_car, 'EditRigidObj', 'SS soldier carrier %d' % _k, *_pa, 0.0, 0.0, _g, 'lot', 5, False, False, children=[_act]))
        _sp4, _ = _cine.Cine.spline(_types.SimpleNamespace(K=K), _car, [_pa, _pb], [17.0, 17.0], [_g, _g], name='SS soldier path %d' % _k)
        for t_, d_, p_ in tasks(_sp4):
            if lit(t_.args[1]) == 'SequenceCommand':
                t_.args[3] = v(_hwhen % (_ths - 1.4 + 0.25 * _k))
        for _t in _sp4:
            m.add_child(LOGIC, _t)
    K.actor(CSO['outro'], GEN_P, (_cq[0], _cq[1], _cq[2]), 'alseao_1', anim='cutscene_talk1, cutscene_talk2', name='General Dhari at the server')
    K.actor(CSO['outro'], (GEN_P[0] + 1.2 * 4096, GEN_P[1] - 0.9 * 4096, GEN_P[2]), GEN_P, 'alarm1_1', anim='stand_look_about', weapon='107_01_1', name='his aide')
    _fc1, _fc2 = nid(), nid()                                  # (review: while the outro opened on the missile a Jones stood on the gantry: each only for his own footage shot)
    m.add_child(LOGIC, T(_fc1, 'ConditionalContainer', 'SS console footage', _hwhen % (OCAP[-2][0] - 2.4), '', ''))
    m.add_child(LOGIC, T(_fc2, 'ConditionalContainer', 'SS chip footage', _hwhen % (OCAP[-2][0] - 0.3), '', ''))
    K.actor(_fc1, V.U((256.0, 206.5, SB.F)), V.U((256.0, 207.3, SB.F)), 'jones2_1', anim='hack_computer, hack_computer', name='Jones on the console footage')
    K.actor(_fc2, V.U((248.0, 238.0, SB.F)), V.U((248.8, 238.0, SB.F)), 'jones2_1', anim='tba_sabotage, tba_sabotage', name='Jones on the chip footage')
    _rp = (V.U((249.0, 221.0, SB.F)), V.U((267.0, 221.0, SB.F)))
    _rg = -math.pi / 2
    _rc = nid()
    _act = T(nid(), 'EditBoneObj', 'SS Jones running (footage)', *_rp[0], 0.0, 0.0, _rg, True, True, 'jones2_1', True, '110_01_1', '', 'run_forward, run_forward', 1.0, 0.0)
    _rt = OCAP[-1][0] - 2.1
    _rca = nid()
    m.add_child(LOGIC, T(_rc, 'ConditionalContainer', 'SS Jones running clip', _hwhen % (_rt - 0.5), '', '', children=[T(_rca, 'EditRigidObj', 'SS footage carrier', *_rp[0], 0.0, 0.0, _rg, 'lot', 5, False, False, children=[_act])]))
    _sp5, _ = _cine.Cine.spline(_types.SimpleNamespace(K=K), _rca, list(_rp), [20.0, 20.0], [_rg, _rg], name='SS footage run')
    for t_, d_, p_ in tasks(_sp5):
        if lit(t_.args[1]) == 'SequenceCommand':
            t_.args[3] = v(_hwhen % _rt)
    for _t in _sp5:
        m.add_child(LOGIC, _t)
    for _t in ('SplinePathDynCubeObj', 'SplinePathNodeQTask', 'SplinePathGuideQTask', 'SequenceCommand'):
        _atmos.ensure_decl(m, _t)
    import cine as _cine
    CINE = _types.SimpleNamespace(K=K)                         # (only its path helper: Cine() would add models after X.finish)
    _when = _hwhen % _tlast
    _trd = (0.0, 5.0, 16.0, 38.0, 80.0, 150.0, 240.0, 340.0)
    for _k, _car in enumerate(TR_IDS):                         # (one path per car, the same speeds: they leave as one train)
        _p0 = STR.local_to_world(TR_LINE, TR_S, _k, (0.0, 0.0, 0.0))
        _pts = [(_p0[0] + d_ * 4096.0, _p0[1], _p0[2]) for d_ in _trd]
        _sp, _ = _cine.Cine.spline(CINE, _car, _pts, [5.0, 12.0, 20.0, 28.0, 36.0, 44.0, 50.0, 54.0], [_trg] * len(_pts), name='SS train departs (car %d)' % (_k + 1))
        for t_, d_, p_ in tasks(_sp):
            if lit(t_.args[1]) == 'SequenceCommand':
                t_.args[3] = v(_when)
        for _t in _sp:
            m.add_child(LOGIC, _t)
    print('v5 outro: Jones aboard actor under the van %d, the train departs at outro second %.1f' % (TR_IDS[5], _tlast))
# the colonel (officer, red beret) and the broker Kral in the colonel's office, seen on a hacked camera, lip-synced
COL = 0 if INTRO2 else K.actor(CSI['intro'], COL_P, KRAL_P, 'alseao_1', anim='white_stand_look_forward_talk, white_stand_look_right_talk', name='intro General Dhari')   # (canon 11-14)   # (owner r3: cutscene_talk*
#  read as a gun pose with empty hands - the originals' UNARMED talk clips: white_stand_look_*_talk, stand_nogun)
KRAL = 0 if INTRO2 else K.actor(CSI['intro'], KRAL_P, COL_P, 'pat_1', anim='white_stand_look_right_talk, stand_nogun', name='intro arms broker Kral')
if not INTRO2:
    lipsync.link(m, _cap_msg(_GCAP['ss_col3'][1]), [COL])
    lipsync.link(m, _cap_msg(_GCAP['ss_kral2'][1]), [KRAL])
JON = 0 if INTRO2 else K.actor(CSI['intro'], (JON_P[0], JON_P[1], JON_P[2] + 0.45 * CS.M), (JON_P[0], JON_P[1] + 10 * CS.M), 'jones2_1', anim='jones_hiding',   # (owner 11-04: hand and legs sunk in the sand, the rifle in the hand at his ear)
              name='intro Jones listening', speed=0.6)
# (owner playtest 11-03 item 10: the cutscene camera props - holder + head + mast - floated in the sky: gone; the feeds come from
#  the map's own security cameras and the base network, no prop per shot)
# the mission clock (MCLOCK_S), from the end of the intro; out of time = mission failed
MCLOCK = nid()
m.add_child(LOGIC, T(MCLOCK, 'MissionTimer', 'SS mission clock', 'LevelTimer_%d.nTick > 0' % CSI['after'], 'StatusMessage_%d.isSendt' % DONE,
                     MCLOCK_S))                            # (review 11-02: stops at mission complete - no clock over the outro)
m.add_child(LOGIC, T(OUTOFTIME, 'StatusMessage', 'SS out of time', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                     'LevelTimer_%d.nTick > %d * GAME_FREQUENCY && !StatusMessage_%d.isSendt' % (CSI['after'], MCLOCK_S, DONE),
                     'SS_OUTOFTIME', '', 'statusmessage', True, False, 4.0, ''))
m.add_text('messages', 'SS_OUTOFTIME', 'Out of time. The window is closed - mission failed.')
lf.args[11] = v(str(lit(lf.args[11])) + ' || StatusMessage_%d.nTicksSinceFinishedDisplay > 2 * GAME_FREQUENCY' % OUTOFTIME)
# the thermal satellite pass: the engine's own thermal rendering (OverlayHolder 'Infrared' flag = the thermal goggles' view,
# igi2.exe 0x546490 - L32 2945 uses it on a scope shot) only while that shot runs; no scope overlay shown
atmos.ensure_decl(m, 'OverlayHolder')
for _pf, _a, _b in THERMAL_WIN:
    _box, _cs = (CSI['intro'], CSI['cs']) if _pf == 'SS_CS' else (CSO['outro'], CSO['cs'])
    _cond = 'CutScene_%d.nTick > %d && CutScene_%d.nTick < %d' % (_cs, int(_a * 60), _cs, int(_b * 60))
    m.add_child(_box, T(nid(), 'OverlayHolder', 'SS thermal satellite view', _cond, _cond, Ident('OVERLAY_ZOOM'), False))
if INTRO2:
    _SI.stage(globals())
print('cutscenes: thermal windows %s, colonel %d / Kral %d lip-synced, Jones listening %d' % (THERMAL_WIN, COL, KRAL, JON))
# the HQ video link (owner 11-01): the operations room, Anya talking at her desk (L21 'Anya Closeup MAPCOMP' / L31 HQ), staff at
# work behind her; her lines lip-synced to her; the cameras carry time-of-day 1000 (the HQ light), the rest the level light
HQR.light()
_room = m.byid[HQR.room]
m.parent[HQR.room].args.remove(_room)
m.remove(HQR.holder)
m.add_child(4087, T(nid(), 'ConditionalContainer', 'SS HQ room (intro / outro)',
                    'ConditionalContainer_%d.isRun || ConditionalContainer_%d.isRun' % (CSI['intro'], CSO['outro']), '', '',
                    children=[_room]))
for _box, _caps in ((CSI['intro'], ICAP), (CSO['outro'], OCAP)):
    _anya, _anya_t = HQR.actor((4.28, -0.85, -2.72), math.pi / 2, 'anya_1', 'anya_talking', name='HQ Anya talking')
    _kids = [_anya_t] + [HQR.actor(p_, g_, mdl_, an_, name='HQ staff %s' % mdl_)[1] for p_, g_, mdl_, an_ in [(c_[0], c_[1], c_[2], {'cutscene_talk1': 'white_stand_look_forward_talk', 'cutscene_talk2': 'white_stand_look_right_talk'}.get(c_[3], c_[3])) for c_ in HQR.CAST[:4]]]
    for t_ in _kids:
        m.add_child(_box, t_)
    for c_ in _caps:
        if c_[1] in HQ_CAPS:
            lipsync.link(m, _cap_msg(c_[1]), [_anya])
m.reindex()
for _cs, _keys in ((CSI['cs'], IK), (CSO['cs'], OK_)):    # (EditCamera arg 'time of day': 1000 in the HQ shots)
    _t = m.byid[_cs]
    _t.args = [a_ for a_ in _t.args if not (isinstance(a_, Call) and a_.name == 'Task_New')] + atmos.cameras(nid, _keys)   # (keeps shake + tod)
m.reindex()
print('cutscenes: HQ video link - Anya lip-synced in %s' % HQ_CAPS)
K.burn_keep('ConditionalContainer_%d.isRun' % CSO['outro'], timers=HIND_BURN)   # (10-17: the Hinds still smoke in the outro over the base)
# (owner playtest 11-03 r3: the power-cut cut-in - two guards shouting about the generators - is gone: he had already killed
#  them; Anya's one line SS_DONE1 is enough)
# --- phase 2 (owner playtest 11-03 item 6): the decrypt cutscene, ~15 s after the hack - Anya breaks the encryption and walks Jones
# through the base's own cameras: the machine room by the lift, the shed behind the hangar, hall B and the big missile -> the new plan.
# Squads stay live (the feeds show the real garrison below); Jones is off while it runs (NOT_CS)
MR_CAM, MR_LOOK = (158.9 * 4096, 232.9 * 4096, -11.2 * 4096), (160.8 * 4096, 226.7 * 4096, -14.6 * 4096)
SH_CAM, SH_LOOK = (165.5 * 4096, 246.0 * 4096, -5.0 * 4096), (V.SHED[0] * 4096, V.SHED[1] * 4096, (V.SHED[2] + 1.4) * 4096)
# (orchestrator 11-10, rc7m 1:08: the storeroom feed held 6 s on an empty hut. A guard walks along the door wall to his post at the door, the operator pans with him)
SH_WALK = [(171.4, 241.7), (168.8, 241.6), (166.4, 241.6)]   # (world m, 1.1 m in front of the door wall at y 240.5, east to west, the door at x ~166)
SH_LA, SH_LB = (168.6 * 4096, 238.5 * 4096, (V.SHED[2] + 1.3) * 4096), (166.5 * 4096, 238.5 * 4096, (V.SHED[2] + 1.2) * 4096)
HB_CAM2 = V.U((262.0, 226.0, SB.F + 7.0))
# (judge J13, 11-08: 'fuelled and on its pad' played over a lift tower and a dark hall, and the last line held 10 s on an empty dark hall.
#  Now: the hall camera east of the pit (HB_CAM2) frames the whole missile, nose to pad, in a wider lens (camaim.py renders),
#  the last line, 'open the cage from the control room', is the control room's own ceiling camera on its desks and window)
DEC_MAST, DEC_UP = HB_CAM2, V.U((SB.PIT_C[0], SB.PIT_C[1], SB.F + 9.0))
DEC_CTRL, DEC_CTRL_LOOK = V.U((256.0, 197.5, SB.F + 2.8)), V.U((256.0, 208.0, SB.F + 2.0))
DEC_CTRL_SCI, DEC_CTRL_ZOOM = V.U((256.0, 206.6, SB.F + 1.2)), 0.40   # (judge F04: the ~11 s feed zooms from the room onto the typing scientist)
DEC_CAGE, DEC_CAGE_LOOK = V.U((SB.PIT[0] - 5.5, SB.PIT_C[1] + 3.0, SB.F + 3.5)), V.U((SB.PIT_C[0] - 1.3, SB.PIT_C[1], SB.F + 1.2))   # (judge H05: a new mast camera west of the cage gate, on the gate and the chip (camaim render 11-08))
cam_obj(DEC_CAGE, DEC_CAGE_LOOK, name='cage', pole=True)   # (a real, shootable camera: one camera = one CAMERA number, R16)
cam_obj(DEC_CTRL, DEC_CTRL_LOOK, name='control room', pole=False)
DECCS = [('ss_dec1', "ANYA: Jones, I decrypted the data. Their camera network goes a lot deeper than this airbase.", ('office', MR_CAM, MR_LOOK)),
         ('ss_dec2', "ANYA: That storeroom shed behind the hangar. There are stairs under its floor, down to a lift.", ('cctv', SH_CAM, SH_LA, SH_LB, 0.68)),
         ('ss_dec3', "ANYA: And at the bottom of that lift... a missile base. That one is fuelled and on its pad.", ('office', DEC_MAST, DEC_UP)),
         ('ss_dec4', "ANYA: The plan has changed, Jones. Take Kral's laptop, it proves who bought that thing. Then get down there, open the missile cage "
                     "from the control room and pull the guidance chip.", ('office', DEC_CTRL, DEC_CTRL_LOOK, DEC_CTRL_SCI, DEC_CTRL_ZOOM, DEC_CAGE, DEC_CAGE_LOOK, 0.5))]
DK, DCAP = shots(DECCS, 'SS_DEC')
CSD = CS.add_outro(m, nid, 4087, DK, DCAP, DECRYPT)
m.set(CSD['outro'], 2, 'Mid-game Cutscene (decrypted data)')
_td = m.byid[CSD['cs']]
_td.args = [a_ for a_ in _td.args if not (isinstance(a_, Call) and a_.name == 'Task_New')] + atmos.cameras(nid, DK)
m.reindex()
_FT = K._tris()[0]


def _top_at(x_m, y_m, below_m, above_m=None):
    """the highest collision surface at (x, y) m under below_m (and over above_m) - a roof or a desk top"""
    _, be = atmos._vertical_hits(_FT, (x_m * 4096.0, y_m * 4096.0, below_m * 4096.0))
    be = [z_ / 4096.0 for z_ in be if above_m is None or z_ / 4096.0 > above_m]
    return be[0] if be else None


FLAGS = []
for _fn, _fm, _fx, _fy, _zb, _za, _fyaw in (
        ('on the south gatehouse', 'ss_flagr_1', 81.1, 61.8, 40.0, None, 0.4),
        ('on the west admin roof', 'ss_flagr_1', 54.4, 235.8, 60.0, None, 1.2),
        # (editor look ss_p2look2: the hangar ray hit its inner truss under the glass roof, the personnel roof one sat in a wall - dropped)
        ('on the colonel desk', 'ss_flagd_1', 47.88, 237.35, 6.6, 5.4, 0.3),   # (owner 116: at 48.0, 238.0 the flag stood inside the server's monitor, seen in the E use view; 1.1 m along the desk)
        ('on the gatehouse table', 'ss_flagd_1', 80.6, 63.1, 6.3, 5.1, 2.6),
        ):
    _ffz = _top_at(_fx, _fy, _zb, _za)
    if _ffz is None:
        print('flag %s: NO SURFACE - skipped' % _fn)
        continue
    _f = nid(); FLAGS.append(_f)
    m.add_child(_ST, T(_f, 'EditRigidObj', 'SS Iraqi flag %s' % _fn, _fx * 4096.0, _fy * 4096.0, (_ffz + 0.01) * 4096.0, 0.0, 0.0, _fyaw,
                       _fm, 5, False, False))
    print('flag %s: %s at (%.1f, %.1f, %.2f) m' % (_fn, _fm, _fx, _fy, _ffz))
# (owner 11-03 r3 item 7: the live garrison in this cutscene 'went crazy' - it is held back while it runs, unless Jones is already below;
#  the feeds show a calm STAGED scene: the 2 lift guards at their post, scientists at the missile, guards on set posts)
BELOW = nid()
m.add_child(LOGIC, T(BELOW + 0, 'AreaActivate', 'SS Jones below the airfield', 215.0 * 4096, 226.0 * 4096, -26.0 * 4096, 0.0, 0.0, 0.0,
                     130.0 * 4096, 70.0 * 4096, 34.0 * 4096, 'CRITERIA_HUMAN0'))
WAS_BELOW = nid()
m.add_child(LOGIC, T(WAS_BELOW, 'EditVariable', 'SS Jones has been below', 0.0, 0.0, 0.0, 0,
                     'EditVariable_%d.nValue == 0 && AreaActivate_%d.nActive' % (WAS_BELOW, BELOW), ''))
_hold = '!ConditionalContainer_%d.isRun || EditVariable_%d.nValue == 1' % (CSD['outro'], WAS_BELOW)
for _sk in [k_ for k_ in SQUAD_IDS if k_.startswith('U ')]:
    _sid = SQUAD_IDS[_sk][0]
    _par = m.parent[_sid]
    _ix = _par.args.index(m.byid[_sid])
    _par.args[_ix] = T(nid(), 'ConditionalContainer', 'SS %s (held back in the decrypt cutscene)' % _sk, _hold, '', '', children=[m.byid[_sid]])
    m.reindex()
_rw = lambda x_, y_: V.U((x_, y_, SB.F))
# (N4 ss-ending 11-15: the staged lift guards and missile scientists are copies of the live U men 1211/1213 and 1367/1369 on the same spots:
#  they show only while those men are held back = Jones has not been below; else the feeds show the live men, alive or dead)
_cp = nid()
m.add_child(CSD['outro'], T(_cp, 'ConditionalContainer', 'SS decrypt staged copies of the U men (Jones never below)',
                            'EditVariable_%d.nValue == 0' % WAS_BELOW, '', '', children=[]))
for (_gx, _gy, _gg, _clip), _nm in zip(LIFT_GUARDS, ('A', 'B')):
    K.actor(_cp, (_gx * 4096.0, _gy * 4096.0, V.TOP_Z * 4096.0), (_gx * 4096.0, (_gy + (1 if _gg == 0.0 else -1)) * 4096.0, V.TOP_Z * 4096.0),
            'alarm1_1', anim=_clip, weapon='107_01_1', name='decrypt lift guard ' + _nm)
_mis = V.U((SB.PIT_C[0], SB.PIT_C[1], SB.F + 2.0))
for _rx, _ry, _an in ((246.9, 237.3, 'scientist_standing_studying'), (247.4, 239.0, 'scientist_confused_studying, scientist_standing_studying'),
                      (242.6, 236.4, 'scientist_standing_studying')):
    K.actor(_cp, _rw(_rx, _ry), _mis, 'bubsci_1', anim=_an, name='decrypt scientist')
K.actor(CSD['outro'], _rw(256.0, 206.38), _rw(256.0, 212.0), 'bubsci_1', anim='hack_computer, hack_computer', name='decrypt control room scientist')   # (J13 + item 109: typing on the launch console, fingertips mid-keyboard)
for _rx, _ry in ((238.0, 228.0), (260.0, 228.0)):
    K.actor(CSD['outro'], _rw(_rx, _ry), _rw(_rx, _ry + 8.0), 'alarm1_1', anim='stand_look_about', weapon='107_01_1',
            name='decrypt post guard')
_s2 = DCAP[1][0] - 0.3                                     # (the storeroom shot: from its line's caption, line + 0.6 s)
_wa, _wb = _s2 + 0.4, _s2 + 0.4 + 4 * 0.82                 # (4 strides of stand_walk_forward over the 5 m, then he stands his post)
_wz = []
for _x, _y in SH_WALK:
    _g = float(TERR.height(_x * 4096.0, _y * 4096.0)) / 4096.0
    _wz.append(_g if abs(_g - V.SHED[2]) < 0.6 else V.SHED[2])
_wp = [(_x * 4096.0, _y * 4096.0, _z * 4096.0) for (_x, _y), _z in zip(SH_WALK, _wz)]
_wrig, _wpa, _wgu = nid(), nid(), nid()
_wt = lambda a_: 'CutScene_%d.nTick > %.2f * GAME_FREQUENCY' % (CSD['cs'], a_)
_wbone = lambda clips_, loop_: T(nid(), 'EditBoneObj', 'SS decrypt shed guard', *_wp[0], 0.0, 0.0, math.pi / 2, loop_, True, 'alarm1_1', True, '107_01_1', '', clips_, 1.0, 0.0)
m.add_child(CSD['outro'], T(_wrig, 'EditRigidObj', 'SS decrypt shed guard carrier', *_wp[0], 0.0, 0.0, math.pi / 2, 'lot', 5, False, False, children=[
    T(nid(), 'ConditionalContainer', 'SS decrypt shed guard waits', '!(%s)' % _wt(_wa), '', '', children=[_wbone('stand', True)]),
    T(nid(), 'ConditionalContainer', 'SS decrypt shed guard walks', '%s && !(%s)' % (_wt(_wa), _wt(_wb)), '', '', children=[_wbone('stand_walk_forward', True)]),
    T(nid(), 'ConditionalContainer', 'SS decrypt shed guard posts', _wt(_wb), '', '', children=[_wbone('stand_look_about', True)])]))
_wd = [math.dist(_wp[k_], _wp[k_ - 1]) / 4096.0 for k_ in (1, 2)]
_wts = [0.0, (_wb - _wa) * _wd[0] / sum(_wd), _wb - _wa]
_wkh = sum(_wd) / (_wb - _wa) * 3.6
m.add_child(LOGIC, T(_wpa, 'SplinePathDynCubeObj', '', False, children=[
    T(nid(), 'SplinePathNodeQTask', '', *_wp[k_], 0.0, 0.0, math.pi / 2, True, _wkh, round(_wts[k_], 6),
      *[float(a_ - b_) for a_, b_ in zip(_wp[min(k_ + 1, 2)], _wp[max(k_ - 1, 0)])], True) for k_ in range(3)]))
m.add_child(LOGIC, T(_wgu, 'SplinePathGuideQTask', '', _wpa, _wrig, False, False, 0.0, children=[
    T(nid(), 'SequenceCommand', '', _wt(_wa), 'SplinePathGuide_SetRunning (TRUE);', '', '')]))
print('cutscenes: decrypt shed guard walks %.1f-%.1f s at %.1f km/h, ground z %s' % (_wa, _wb, _wkh, [round(z_, 2) for z_ in _wz]))
m.reindex()
print('cutscenes: decrypt cutscene %d (%.1f s) after the hack' % (CSD['cs'], sum(k_['dur'] for k_ in DK)))
NOT_CS = '!ConditionalContainer_%d.isRun && !ConditionalContainer_%d.isRun && !ConditionalContainer_%d.isRun && !ConditionalContainer_%d.isRun && !ConditionalContainer_%d.isRun && !ConditionalContainer_%d.isRun' % (
    CSI['intro'], CSO['outro'], CSG['outro'], CSD['outro'], CSS['outro'], CSCG['outro'])   # (engine 11-15: + the S17 cage-gate shot, Jones was live through it)
CS.gate(m, PC, NOT_CS + ' && LevelFlow_10.nTick > 0', 'ThePlayer - off during cutscenes')   # (engine 11-15 / player N14: ThePlayer sits before the intro in the tree, so on tick 0 the
                                                                                          #  intro's isRun still read FALSE: HUD icons on black for a tick. LevelFlow (last in the tree, the
                                                                                          #  originals use LevelFlow_10.nTick 8x) reads 0 then. NOT_CS itself stays as it is for the clocks)
# (judge J04, 11-08: the clock drew over the decrypt and sand door cutscenes. Its pause rule (arg 2) hides and holds it in any cutscene;
#  the out-of-time fail counts the same play time on its own LevelTimer, so the clock on screen and the fail agree)
CLKT = nid()
m.add_child(LOGIC, T(CLKT, 'LevelTimer', 'SS mission clock play time', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'LevelTimer_%d.nTick > 0 && %s' % (CSI['after'], NOT_CS), '', False))
m.set(MCLOCK, 4, 'StatusMessage_%d.isSendt || !(%s)' % (DONE, NOT_CS))
m.set(OUTOFTIME, 9, 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY && !StatusMessage_%d.isSendt' % (CLKT, MCLOCK_S, DONE))
# (owner 11-02 'the cutscenes must show the real live soldiers': the squads keep running during cutscenes - the feeds film the
#  live patrols and posts; only Jones is off while a cutscene runs)
# (owner playtest 11-03 item 9: 'two glitched soldiers behind the man talking to the commander' + 'four glitched things at the front
#  gate' = the LIVE server-room and south-gate guards standing inside the intro's actors) -> those two squads join after the intro
LIVE_PICKETS = os.environ.get('SS_LIVE_PICKETS', '1') == '1'   # (G43 11-14 plive_patch: men with the level, server room 10 s after the intro)
import ssmovewait as _MW
MOVEWAIT = None                                            # (allocated just before m.write: no task id shifts)
for _sk in (('N server room',) if LIVE_PICKETS else ('N server room', 'S south gate') + (('S landing zone pickets', 'S ridge mate') if INTRO2 else ())):
    _sid = SQUAD_IDS[_sk][0]
    _par = m.parent[_sid]
    _ix = _par.args.index(m.byid[_sid])
    _cnd = '!ConditionalContainer_%d.isRun' % CSI['intro'] + (' && LevelTimer_%d.nTick > 10 * GAME_FREQUENCY' % CSI['after'] if LIVE_PICKETS else '')
    _par.args[_ix] = T(nid(), 'ConditionalContainer', 'SS %s (after the intro)' % _sk, _cnd, '', '',
                       children=[m.byid[_sid]])
    m.reindex()
if LIVE_PICKETS:                                           # (G43 11-14: burn the ids the other after-intro containers had, so no later task id shifts)
    m.set(SQUAD_IDS['S landing zone pickets'][1][0], 6, 1.5708)   # (G43 heading, ss-intro k24: idle AK pointed at his mate in the fall zoom -> faces west)
    _G43_BURN = [nid() for _ in range(3 if INTRO2 else 1)]
lf.args[10] = v(CSO['complete'])
print('cutscenes: intro %.1f s (%d keys), outro %.1f s' % (sum(k_['dur'] for k_ in IK), len(IK), sum(k_['dur'] for k_ in OK_)))

# ambience (SHOBI 10-29 addition kept 10-31): the ORIGINAL game's banks at their own volumes (owner SOUND RULE 10-18) -
# MP storm howl at ground level + COMMON wind bed, L24 airfield one-shots / interiors / music, Arabic shouts, radio
# chatter, generator hums that stop with each generator (tools/ssamb.py build_classic)
import ssamb
AMB_BANKS = ssamb.build_classic(globals())
# --- loop 2: the base has its own sound; the storm stays outside (the ground-level wind beds reach 130 m down and are not stopped by a mesh hall)
TUN_AREA = nid()
m.add_child(LOGIC, T(TUN_AREA, 'AreaActivate', 'SS Jones in the truck tunnel', 279.0 * 4096, 150.0 * 4096, -8.0 * 4096, 0.0, 0.0, 0.0, 63.0 * 4096, 146.0 * 4096, 56.0 * 4096, 'CRITERIA_HUMAN0'))
UNDER = '(AreaActivate_%d.nActive || AreaActivate_%d.nActive)' % (BELOW, TUN_AREA)
# (critic rv3: 'a sandstorm with clear air'. The engine's RainEffect as sand read as snow and showed underground (rv4) -> low drifts of sand from Smoke emitters where Jones crosses open ground)
_dr = []
# (S7 F4 'dark puffs over the sand', ss-look 11-17, SS_SAND_TINT=1, default OFF until a take: in the originals' alpha-mode Smoke (sprite 3) colour 2.0 = white
#  smoke / dust, 1.3 = concrete dust, 0.6-1.0 = BLACK smoke, desert dust (2.0, 1.75, 1.44) / (2.0, 1.9, 1.6) at intensity 0.03-0.08 (L2, L5). Ours was darker
#  than their black smoke -> dark brown blobs. The switch takes L2's tan dust colour and a lighter intensity)
_SAND_RGB, _SAND_INT = ((2.0, 1.75, 1.44), 0.12) if os.environ.get('SS_SAND_TINT') == '1' else ((0.74, 0.60, 0.42), 0.28)
for _x, _y in ((87.0, -22.0), (120.0, 12.0), (82.0, 58.0), (150.0, 208.0), (205.0, 248.0), (326.0, 181.0), (352.0, 190.0), (396.0, 196.0), (440.0, 214.0)):
    _dr.append(_SGS.smoke(nid, 'SS blowing sand', V.U((_x, _y, _bh(_x, _y) + 0.8)), math.pi / 2, -math.pi / 2, 90, 7.0, 0.35, 4.0, 8.0, _SAND_RGB, 4.0, 3.0,
                          3, 3.2, 0.7, _SAND_INT, 0.0, '', cutoff=130.0, mode=0))
m.add_child(LOGIC, T(nid(), 'Container', 'SS sand drifts', False, children=_dr))
for _i in m.find('AmbientArea'):
    if str(m.arg(_i, 15)) in ('sandstorm_wind', 'wind_1', 'car_distant_01,car_distant_02', 'dogs_03,dogs_05,dogs_08'):
        _c = str(m.arg(_i, 18))
        m.set(_i, 18, ('(%s) && !%s' % (_c, UNDER)) if _c else '!%s' % UNDER)
_BA = nid()
m.add_child(LOGIC, T(_BA, 'Container', 'SS base sound', False))
_atmos.ambient_sound(m, nid, _BA, 'SS base machinery', V.U((222.0, 226.0, SB.F + 6.0)), (112.0, 72.0, 44.0), 'industrial_02', True, True, '', 8.0)
_atmos.ambient_sound(m, nid, _BA, 'SS base generators', V.U((196.5, 199.2, SB.F + 1.0)), (26.0, 14.0, 10.0), 'sandstorm_gen', True, True, '', 8.0)
for _t in ('SoundGenerator', 'SequenceCommand', 'EditRigidObj'):
    _atmos.ensure_decl(m, _t)
for _g in (152, 150):                                     # (judge P16 A11: the generator's own stop sound when Jones cuts it, the hum bed fades with it)
    _gx, _gy, _gz = (float(m.arg(_g, _k)) for _k in (3, 4, 5))
    _c = 'GenericTBA_%d.isFinished' % _g
    m.add_child(LOGIC, T(-1, 'EditRigidObj', 'SS generator stop %d' % _g, _gx, _gy, _gz + 1.0 * 4096, 0.0, 0.0, 0.0, 'none', 5, False, False, children=[
        T(-1, 'SoundGenerator', '', children=[T(-1, 'SequenceCommand', '', _c, 'SoundGenerator_PlaySound("generator_stop")', 'TRUE', 'SequenceCommand_SetCommand(-1)')])]))
_atmos.ambient_sound(m, nid, _BA, 'SS control room radio', V.U((256.0, 202.5, SB.F + 1.5)), (20.0, 11.0, 6.0), 'tech_radio_01', True, True, '', 7.0)
_atmos.ambient_sound(m, nid, _BA, 'SS tunnel draught', V.U((277.0, 153.0, -8.0)), (56.0, 140.0, 58.0), 'wind_1', True, True, '', 10.0)
_atmos.ambient_sound(m, nid, _BA, 'SS the storm at the open sand door', V.U((SD_X - 6.0, SD_Y, SD_G + 3.0)), (36.0, 14.0, 12.0), 'sandstorm_wind', True, True, 'Door_%d.nDoorOpenTicks > 0' % SAND_DOOR, 6.0)
import ssmusic; ssmusic.areas(globals(), below_cond=UNDER)   # (own score; underground = the hall + the tunnel)

# =========================================================== 9. LevelFlow must be created AFTER the HumanPlayer: its
# init (igi2.exe+0x40a070) links the existing player into player slot 0. Created first (as in the MP file, inside
# Dynamic) the slot stays empty and the game crashes (igi2.exe+0x352e2) as soon as the mission fails.
m.remove(10)
m.stmts.append(lf)
m.stmts.append(T(nid(), 'MissionScoreSettings', '', 3600.0, 2700.0, 1800.0, 6.0, 3.0, 0.0, 5.0, 2.0, 0.0, 40.0, 65.0, 90.0,
                 40.0, 50.0, 60.0))
m.stmts.append(T(nid(), 'LevelInfo', '', False, False, 'LOCAL:modelsused.qsc'))
m.reindex()

# =========================================================== 10. test-only variants
if 'failtest' in DBG:                                      # M10 proof: the mission FAILS when one guard dies (killone kills him)
    _h = SQUAD_IDS['S generator A yard'][1][0]
    lf.args[11] = v('HumanSoldier_%d.isDead || (%s)' % (_h, str(lit(lf.args[11]))))
    print('debug: the mission fails when guard %d dies' % _h)
if 'flash' in DBG:                                         # M10 proof: flashbangs only; a flashed yard guard is stunned 12 s
    PLAYER.args[9] = v('Human_AddWeapon("WEAPON_ID_FLASHBANG"),\nHuman_AddAmmoForWeapon("WEAPON_ID_FLASHBANG",6);')
    for _h in SQUAD_IDS['S generator A yard'][1]:
        for _k in m.children(_h):
            if lit(_k.args[1]) == 'HumanAI':
                _ev = alarmai.C('AIFunction_GetCurrentEventType')
                _, _b = alarmai.decompile_ai(bytes(m.ai_files[str(lit(_k.args[0]))]))
                m.ai_files[str(lit(_k.args[0]))] = alarmai.compile_ai([alarmai.If(alarmai.EQ(_ev, 'AIEVENT_FLASHBANG'),
                    [alarmai.C('AIAction_Stunned', 12, 'AIACTIONFLAG_NONE')], _b)])
    print('debug: flashbangs only, yard guards stunned 12 s')
if 'killsci' in DBG:                                       # (test: one of the two scientists dies at 8 s, his mate is the witness: the hall alarm must ring 1.5 s later)
    _hp = [float(m.arg(SQUAD_IDS['U scientists'][1][0], k_)) for k_ in (3, 4, 5)]
    msg('SS_DBGK', 'DEBUG scientist', 'HumanSoldier_%d.isDead' % SQUAD_IDS['U scientists'][1][0], 'DEBUG: SCIENTIST DEAD', 30.0)
    m.add_child(PC, T(nid(), 'ExplodeObject', 'DEBUG kill one scientist', _hp[0], _hp[1] - 0.9 * 4096.0, _hp[2] + 2000.0, 0.0, 0.0, 0.0,
                      'none', 'none', 100.0, 2.0, 2.6, 100.0, 0.0, 0, 0, 'LevelFlow_10.nTick > 8 * GAME_FREQUENCY', ''))
if 'killone' in DBG:                                       # alarm-AI test: one generator-yard guard dies at 8 s (a tiny blast on
    _h = SQUAD_IDS['S generator A yard'][1][0]             #  him) - his mates must find him and run to the alarm button
    _hp = [float(m.arg(_h, k_)) for k_ in (3, 4, 5)]
    m.add_child(PC, T(nid(), 'ExplodeObject', 'DEBUG kill one guard', _hp[0], _hp[1], _hp[2] + 2000.0, 0.0, 0.0, 0.0,
                      'none', 'none', 100.0, 2.5, 3.5, 100.0, 0.0, 0, 0, 'LevelFlow_10.nTick > 8 * GAME_FREQUENCY', ''))
    print('debug: guard %d dies at 8 s at %s' % (_h, [round(c) for c in _hp]))
if 'die' in DBG:
    m.add_child(PC, T(nid(), 'ExplodeObject', 'DEBUG death blast', START[0], START[1], START[2] + 500, 0.0, 0.0, 0.0,
                      'none', 'none', 100.0, 30.0, 40.0, 50.0, 0.0, 3, 3, 'LevelFlow_10.nTick > 5 * GAME_FREQUENCY', ''))
if 'win' in DBG:
    lf.args[10] = v('LevelFlow_10.nTick > 8 * GAME_FREQUENCY')
if 'alarm' in DBG:
    m.set(1500, 7, 'EditVariable_1500.nValue == 0 && LevelFlow_10.nTick > 5 * GAME_FREQUENCY')
if 'objectives' in DBG:                                    # every objective completes on a timer
    m.set(O1, 9, 'LevelFlow_10.nTick > 6 * GAME_FREQUENCY')
    m.set(O2, 9, 'LevelFlow_10.nTick > 12 * GAME_FREQUENCY')
    m.set(O3, 9, 'LevelFlow_10.nTick > 18 * GAME_FREQUENCY')
    m.set(O4, 9, 'LevelFlow_10.nTick > 20 * GAME_FREQUENCY')
    m.set(O5, 9, 'LevelFlow_10.nTick > 24 * GAME_FREQUENCY')
    m.set(OPEN, 9, 'StatusMessage_%d.isSendt && StatusMessage_%d.isSendt && StatusMessage_%d.isSendt' % (O3, O4, O5))
    m.set(DONE, 9, 'StatusMessage_%d.isSendt && LevelFlow_10.nTick > 40 * GAME_FREQUENCY && !HumanPlayer_0.isDead' % OPEN)
if 'targets' in DBG:                                       # objectives 1-3 on timers, Hinds + fuel REALLY explode on timers,
    m.set(O1, 9, 'LevelFlow_10.nTick > 6 * GAME_FREQUENCY')   # the escape/doors/extraction chain stays the RELEASE one
    m.set(O2, 9, 'LevelFlow_10.nTick > 12 * GAME_FREQUENCY')  # (10-12: 'objectives' rewrote that chain and hid the bug)
    m.set(O3, 9, 'LevelFlow_10.nTick > 18 * GAME_FREQUENCY')
    m.set(O4, 9, 'LevelFlow_10.nTick > 20 * GAME_FREQUENCY')
    m.set(O5, 9, 'LevelFlow_10.nTick > 24 * GAME_FREQUENCY')
if 'pre4' in DBG:                                          # 11-02 r7 walk gate: objectives 1-4 done on timers, the bunker (O5),
    m.set(O1, 9, 'LevelFlow_10.nTick > 3 * GAME_FREQUENCY')   # the escape and the extraction stay the RELEASE chain
    m.set(O2, 9, 'LevelFlow_10.nTick > 5 * GAME_FREQUENCY')
    m.set(O3, 9, 'LevelFlow_10.nTick > 7 * GAME_FREQUENCY')
    m.set(O4, 9, 'LevelFlow_10.nTick > 9 * GAME_FREQUENCY')
if 'tour' in DBG:                                          # 11-02 r7: after the start spot, Jones is put in front of two more wall signs
    _tseq = nid()                                          # (L26 'snap human player': Human_PopPosition in metres)
    _tc = [nid(), nid(), nid()]
    _tour = [((333130.0, 253999.0, 3348.0), 'stop sign'), ((642772.0, 388000.0, 3138.0), 'ammo sign'),
             (BW(-0.2, BK_FAR - 3.2 - CONT_L - 9.0, 0.3), 'bunker hall')]
    _atmos.ensure_decl(m, 'SequenceCommand')
    m.add_child(LOGIC, T(_tseq, 'Container', 'DEBUG sign tour', False, children=[
        T(_tc[k_], 'SequenceCommand', 'DEBUG tour %s' % nm_, 'LevelFlow_10.nTick > %d * GAME_FREQUENCY' % (25 + 15 * k_),
          'Human_PopPosition(0, %.3f, %.3f, %.3f)' % (p_[0] / 4096, p_[1] / 4096, p_[2] / 4096 + 0.4), 'TRUE',
          'SequenceCommand_SetCommand(%d)' % (_tc[k_ + 1] if k_ + 1 < len(_tc) else -1)) for k_, (p_, nm_) in enumerate(_tour)]))
if 'signhop' in DBG:                                       # 11-02 r8 walk: start at the barracks sign; after its close-ups Jones is put
    _atmos.ensure_decl(m, 'SequenceCommand'); _atmos.ensure_decl(m, 'LevelTimer')   # in front of the stop sign, then the ammo sign
    _SB = (724382.0, 815937.0, -943.0 + 0.35 * 4096)       # (latched timers: 14 / 11 / 11 s after he reaches each stand), then
    _SS = (333130.0, 253999.0, float(K.TERR.height(333130.0, 253999.0)) + 0.5 * 4096)   # back here, and walks the release
    _SA = (642772.0, 388000.0, float(K.TERR.height(642772.0, 388000.0)) + 0.5 * 4096)   # chain on foot from there
    m.set(0, 3, _SB[0]); m.set(0, 4, _SB[1]); m.set(0, 5, _SB[2]); m.set(0, 6, 6.087)
    _hop = [(_SB, _SS, 14), (_SS, _SA, 11), (_SA, _SB, 11)]
    _scs = [nid() for _ in _hop]
    _kids = []
    for k_, (at_, to_, wait_) in enumerate(_hop):
        a_, l_ = nid(), nid()
        m.add_child(LOGIC, T(a_, 'AreaActivate', 'DEBUG sign stand %d' % k_, *at_, 0.0, 0.0, 0.0, 1.6 * 4096, 1.6 * 4096, 2.5 * 4096,
                             'CRITERIA_HUMAN0'))
        m.add_child(LOGIC, T(l_, 'LevelTimer', 'DEBUG sign stand %d timer' % k_, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                             'AreaActivate_%d.nActive || LevelTimer_%d.nTick > 0' % (a_, l_), '', False))
        _kids.append(T(_scs[k_], 'SequenceCommand', 'DEBUG sign hop %d' % k_, 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (l_, wait_),
                       'Human_PopPosition(0, %.3f, %.3f, %.3f)' % tuple(c_ / 4096 for c_ in to_), 'TRUE',
                       'SequenceCommand_SetCommand(%d)' % (_scs[k_ + 1] if k_ + 1 < len(_scs) else -1)))
    m.add_child(LOGIC, T(nid(), 'Container', 'DEBUG sign hops', False, children=_kids))
if 'signs2' in DBG:                                        # 11-02 r9 sign close-ups (art check, not gameplay): walking 4.5 m BACK from the
    _atmos.ensure_decl(m, 'SequenceCommand'); _atmos.ensure_decl(m, 'LevelTimer')   # spawn (an area entered on foot - never one
    _ta = BW(-0.6, -12.0, 0.5)                             # spawned in) starts a timer; Jones is then put in front of each sign
    _stands = [(333130.0, 253999.0, 6000.0), (642772.0, 388000.0, 6000.0), (724382.0, 815937.0, 4000.0)]   # (the r6 close-up stands)
    _a, _l = nid(), nid()
    m.add_child(LOGIC, T(_a, 'AreaActivate', 'DEBUG sign tour trigger', *_ta, 0.0, 0.0, 0.0, 1.5 * 4096, 1.5 * 4096, 2.5 * 4096, 'CRITERIA_HUMAN0'))
    m.add_child(LOGIC, T(_l, 'LevelTimer', 'DEBUG sign tour timer', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                         'AreaActivate_%d.nActive || LevelTimer_%d.nTick > 0' % (_a, _l), '', False))
    _scs = [nid() for _ in _stands]
    m.add_child(LOGIC, T(nid(), 'Container', 'DEBUG sign tour', False, children=[
        T(_scs[k_], 'SequenceCommand', 'DEBUG sign stand %d' % k_, 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (_l, 3 + 10 * k_),
          'Human_PopPosition(0, %.3f, %.3f, %.3f)' % tuple(c_ / 4096 for c_ in p_), 'TRUE',
          'SequenceCommand_SetCommand(%d)' % (_scs[k_ + 1] if k_ + 1 < len(_scs) else -1)) for k_, p_ in enumerate(_stands)]))
if 'signs3' in DBG:                                        # 11-02 r10 sign close-ups: start at the airbase sewer exit facing east; a few
    _atmos.ensure_decl(m, 'SequenceCommand'); _atmos.ensure_decl(m, 'LevelTimer')   # steps BACK (west) onto open ground start the
    _S0 = (373825.0, 875706.0)                             # timer (an area entered on foot); then Jones is put at each sign stand
    _cand = [q_['pos'] for q_ in GRAPHS[2] if q_['terrain'] == 1 and 3.5 * 4096 < math.dist(q_['pos'][:2], _S0) < 7.0 * 4096
             and q_['pos'][0] < _S0[0] - 2.5 * 4096]
    _ta = min(_cand, key=lambda q_: abs(q_[1] - _S0[1]))
    m.set(0, 3, _S0[0]); m.set(0, 4, _S0[1]); m.set(0, 6, -math.pi / 2)
    m.set(0, 5, float(K.TERR.height(*_S0)) + 0.3 * 4096)
    m.set(0, 6, math.atan2(-(_S0[0] - _ta[0]), _S0[1] - _ta[1]) + math.pi)   # (facing away from the trigger: 's' walks into it)
    _stands = [(333130.0, 253999.0, 6000.0), (642772.0, 388000.0, 6000.0), (724382.0, 815937.0, 4000.0)]
    _a, _l = nid(), nid()
    m.add_child(LOGIC, T(_a, 'AreaActivate', 'DEBUG sign tour trigger', _ta[0], _ta[1], _ta[2] + 2000.0, 0.0, 0.0, 0.0, 1.5 * 4096, 1.5 * 4096,
                         2.5 * 4096, 'CRITERIA_HUMAN0'))
    m.add_child(LOGIC, T(_l, 'LevelTimer', 'DEBUG sign tour timer', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                         'AreaActivate_%d.nActive || LevelTimer_%d.nTick > 0' % (_a, _l), '', False))
    _scs = [nid() for _ in _stands]
    m.add_child(LOGIC, T(nid(), 'Container', 'DEBUG sign tour', False, children=[
        T(_scs[k_], 'SequenceCommand', 'DEBUG sign stand %d' % k_, 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (_l, 3 + 10 * k_),
          'Human_PopPosition(0, %.3f, %.3f, %.3f)' % tuple(c_ / 4096 for c_ in p_), 'TRUE',
          'SequenceCommand_SetCommand(%d)' % (_scs[k_ + 1] if k_ + 1 < len(_scs) else -1)) for k_, p_ in enumerate(_stands)]))
    print('debug signs3: start yaw %.3f, trigger at %s m' % (m.arg(0, 6), [round(c_ / 4096, 1) for c_ in _ta]))
if 'atext' in DBG:                                         # 10-18 playthrough: Jones on the extraction area (with 'targets': the real escape/extraction chain)
    m.set(0, 3, float(m.arg(EXTRACT, 3))); m.set(0, 4, float(m.arg(EXTRACT, 4))); m.set(0, 5, float(m.arg(EXTRACT, 5)) + 300.0)
def _put_jones(p_m, look_m):                                # (v4 tests: Jones at p_m (world m, feet), facing look_m)
    m.set(0, 3, p_m[0] * 4096.0); m.set(0, 4, p_m[1] * 4096.0); m.set(0, 5, p_m[2] * 4096.0 + 200.0)
    m.set(0, 6, round(math.atan2(-(look_m[0] - p_m[0]), look_m[1] - p_m[1]), 6))
    print('debug: Jones at (%.1f, %.1f, %.1f) m facing (%.1f, %.1f)' % (p_m[0], p_m[1], p_m[2], look_m[0], look_m[1]))
if 'isoak' in DBG:                                         # r3 test: Jones carries a loud rifle only (isolation: fired at the lift station)
    PLAYER.args[9] = v('Human_AddWeapon("WEAPON_ID_AK47"), Human_AddAmmoForWeapon("WEAPON_ID_AK47",300);')
if 'unarmedlift' in DBG:                                   # r3 test: the 2 lift guards stand there, cannot shoot (real-input lift walk past them)
    for _h in SQUAD_IDS['U machine room'][1]:
        m.set(_h, 9, '')
if 'noliftguards' in DBG:                                  # r3 test: the isolation run (no men at the lift station, the halls stay)
    m.remove(SQUAD_IDS['U machine room'][0]); m.reindex()
if 'nogarrison' in DBG:                                    # r3 test: no men below (noenemies keeps them), lift + way-down behaviour runs
    for _k, (_sid, _hids) in SQUAD_IDS.items():
        if _k.startswith('U ') and not (_k == 'U machine room' and 'unarmedlift' in DBG):
            m.remove(_sid)
    m.reindex()
if 'review' in DBG or 'gapcam' in DBG:                     # 11-04 chapter review: every chapter of the route in story order (world m, feet)
    def _nearn(g_, p_):                                    # (the nearest AI graph node: a real floor)
        q_ = min(GRAPHS[g_], key=lambda n_: math.dist(n_['pos'][:3], p_[:3]))['pos']
        return (q_[0] / 4096.0, q_[1] / 4096.0, q_[2] / 4096.0)
    _tp = lambda s_: (float(np.interp(s_, TUN.s, TUN.P[:, 0])), float(np.interp(s_, TUN.s, TUN.P[:, 1])), float(np.interp(s_, TUN.s, TUN.z)))
    REV = [('start', (START[0] / 4096, START[1] / 4096, START[2] / 4096)), ('sewer', _nearn(3, (352200.0, 11170.0, -84353.0))),
           ('server', _nearn(2, tuple(float(m.arg(COMPUTER, k_)) for k_ in (3, 4, 5)))), ('laptop', _nearn(2, CASE_P)),
           ('shed_out', (float(lit(m.byid[SHED_DOOR_ID].args[3])) / 4096 - 0.6, float(lit(m.byid[SHED_DOOR_ID].args[4])) / 4096 + 1.3, V.SHED[2])),
           ('shed_in', (167.8, 239.6, V.SHED[2] + 0.1)), ('stairs', (172.0, 237.8, -10.9)), ('passage', (177.7, 235.0, V.TOP_Z)),
           ('corridor', (172.0, 232.4, V.TOP_Z)), ('lift_room', (160.5, 227.0, V.TOP_Z)), ('cab', (165.1, 226.7, V.TOP_Z + 0.25))]
    REV += [(n_, (x_, y_, z_)) for n_, x_, y_, z_ in SB.REVIEW]
    REV += [('gate_out', _tp(4.0)), ('tun_bend', _tp(18.0)), ('tun_ramp', _tp(70.0)), ('tun_low', _tp(130.0)), ('tun_hairpin', _tp(165.0)),
            ('tun_over', _tp(262.0)), ('sand_in', _tp(TUN.s[-1] - 6.0)), ('sand_out', (SD_X + 6.0, SD_Y, _bh(SD_X + 6.0, SD_Y))),
            ('run', (350.0, 192.0, _bh(350.0, 192.0))), ('train_van', (384.0, 199.5, _bh(384.0, 199.5))), ('train_mid', (420.0, 199.0, _bh(420.0, 199.0))),
            ('train_loco', (470.0, 199.0, _bh(470.0, 199.0))), ('train_end', (HOP_P[0] / 4096.0 - 1.0, HOP_P[1] / 4096.0 - 2.5, _bh(HOP_P[0] / 4096.0 - 1.0, HOP_P[1] / 4096.0 - 2.5)))]
    _rf = next((int(p_.split('=')[1]) for p_ in DEBUG.split(';') if p_.startswith('revfrom=')), 0)   # (the review's second job: stands from here on)
    REV_OPEN = max(0, 20 - _rf)
    REV = REV[_rf:]
    if SSW.WORLD or 'wstands' in DBG:                      # (ss world: every changed room first; 'wstands' = the same stands with the flag off, for before shots)
        REV = SSW.stands() + REV[:17]
    if GARRISON2 and 'g2only' in DBG:
        REV = list(GR.REVIEW)
if 'gapcam' in DBG:
    for _n, _p in REV:
        _i = nid()
        m.add_child(K.static_root(), T(_i, 'EditRigidObj', 'REVCAM ' + _n, *V.U((_p[0], _p[1], _p[2] + 1.6)), 0.0, 0.0, 0.0, 'none', 5, False, False))
        print('revcam %d %s' % (_i, _n))
if 'gateopen' in DBG:                                      # (the big gate up from the start, for a look at the open gate)
    m.set(VGATE, 19, 'Door_%d.isClosed && LevelFlow_10.nTick > 2 * GAME_FREQUENCY' % VGATE)
if 'cagetest' in DBG:                                      # (the cage gate on a timer, for a look at whether it stays up)
    m.set(CAGE_GATE, 19, 'Door_%d.isClosed && LevelFlow_10.nTick > 5 * GAME_FREQUENCY' % CAGE_GATE)
if 'review' in DBG or 'revcs' in DBG or 'revout' in DBG:
    m.set(TRAINC, 3, '1')
if 'review' in DBG:                                        # (no walk: Jones is put on each stand in turn, REV_S seconds each; the gates stay open)
    _atmos.ensure_decl(m, 'SequenceCommand')
    REV_S = 13
    _rl = nid()
    m.add_child(LOGIC, T(_rl, 'LevelTimer', 'DEBUG review clock', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, '1', '', False))
    _rs = [nid() for _ in REV]
    m.add_child(LOGIC, T(nid(), 'Container', 'DEBUG review stands', False, children=[
        T(_rs[k_], 'SequenceCommand', 'DEBUG stand ' + n_, 'LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (_rl, 2 + REV_S * k_),
          'Human_PopPosition(0, %.3f, %.3f, %.3f)' % (p_[0], p_[1], p_[2] + 0.35), 'TRUE',
          'SequenceCommand_SetCommand(%d)' % (_rs[k_ + 1] if k_ + 1 < len(_rs) else -1)) for k_, (n_, p_) in enumerate(REV)]))
    m.set(VGATE, 19, 'Door_%d.isClosed && LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (VGATE, _rl, 2 + REV_S * REV_OPEN))
    m.set(SAND_DOOR, 19, 'Door_%d.isClosed && LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (SAND_DOOR, _rl, 2 + REV_S * max(0, REV_OPEN + 5)))
    print('review stands: ' + ' '.join('%d:%s' % (k_, n_) for k_, (n_, p_) in enumerate(REV)))
if 'revout' in DBG:                                        # loop test: the outro alone, from 15 s, Jones parked at the train
    m.set(CSO['outro'], 3, 'LevelFlow_10.nTick > 15 * GAME_FREQUENCY && !HumanPlayer_0.isDead && EditVariable_%d.nValue == 0' % CSO['skip'])
if 'revcs' in DBG:                                         # 11-04 chapter review: every mid cutscene + the outro in turn (the 'intro' scenario shoots them)
    _ft = 'LevelFlow_10.nTick > %d * GAME_FREQUENCY'
    m.set(VGATE, 19, 'Door_%d.isClosed && %s' % (VGATE, _ft % 40))
    m.set(SAND_DOOR, 19, 'Door_%d.isClosed && %s' % (SAND_DOOR, _ft % 75))
    for _cc, _t in ((CSD, 8), (CSG, 42), (CSS, 76), (CSO, 110)):
        m.set(_cc['outro'], 3, '%s && !HumanPlayer_0.isDead && EditVariable_%d.nValue == 0' % (_ft % _t, _cc['skip']))
if 'atserver' in DBG:                                      # phase 2 test: in front of the server (hack -> decrypt cutscene)
    _tp_ = np.array([float(m.arg(COMPUTER, k_)) for k_ in (3, 4, 5)])
    _g_ = float(m.arg(COMPUTER, 8))
    _sp_ = K._exact_spot(_tp_, _g_, 1.2)
    if _sp_ is None:                                       # (the server stands on a desk/rack: 1.1 m in front, on the floor below)
        _q_ = (_tp_[0] - math.sin(_g_) * 1.1 * 4096, _tp_[1] + math.cos(_g_) * 1.1 * 4096)
        _, _be_ = atmos._vertical_hits(K._tris()[0], (_q_[0], _q_[1], _tp_[2] - 0.2 * 4096))
        _sp_ = (_q_[0], _q_[1], _be_[0])
    _put_jones((_sp_[0] / 4096.0, _sp_[1] / 4096.0, _sp_[2] / 4096.0), (_tp_[0] / 4096.0, _tp_[1] / 4096.0))
if 'atlift' in DBG or 'liftmsg' in DBG:                    # (v4 test aid: on-screen proof the cab reached the bottom)
    msg('SS_DBG_LIFT', 'DEBUG lift at the bottom', 'Lift_%d.nCurrentFloor == %d' % (LIFT['lift'], 2 if SB.GUNROOM else 1), 'DEBUG: LIFT AT THE BOTTOM', 30.0)
if 'atlift' in DBG:                                        # v4 test: in the cab at the top, facing the call button
    _bt_ = [float(lit(m.byid[LIFT['button']].args[3 + k])) / 4096.0 for k in range(3)]
    _d_ = math.hypot(_bt_[0] - V.LIFT_C[0], _bt_[1] - V.LIFT_C[1])
    _put_jones((_bt_[0] + (V.LIFT_C[0] - _bt_[0]) / _d_ * 0.9, _bt_[1] + (V.LIFT_C[1] - _bt_[1]) / _d_ * 0.9, V.TOP_Z), _bt_)
if SB.GUNROOM:
    GN.late(globals())
if 'killmsg' in DBG and SB.GUNROOM:
    GN.killmsg(globals())
if 'atgun' in DBG and SB.GUNROOM:                          # (owner 63 test: in the gun room behind the gun, facing the window)
    _put_jones((GN.GUN[0] - 1.6, GN.GUN[1], GN.FZ), (GN.GUN[0] + 5.0, GN.GUN[1]))
if 'atdoor' in DBG and SB.GUNROOM:                         # (owner 91 test: facing the stair door from inside the gun room, to watch how the men come in)
    _put_jones((173.3, 227.0, GN.FZ), (173.9, 234.0))
if 'athall' in DBG:                                        # (owner 89 test: on foot in the middle of the hall, facing north; with g2alert, for a long fight without the gun)
    _put_jones((225.0, 226.7, SB.F), (225.0, 240.0))
if 'atvest' in DBG:                                        # v4 test: the vestibule at the bottom, facing the annex door (rel -x)
    _put_jones((170.3, 226.7, LIFT_BOTTOM), (175.0, 226.7))
if 'atshed' in DBG:                                        # v4 test: 2.5 m in front of the shed's door, facing it
    _dw = (float(lit(m.byid[SHED_DOOR_ID].args[3])) / 4096.0, float(lit(m.byid[SHED_DOOR_ID].args[4])) / 4096.0)
    _dc = (_dw[0] - 0.6, _dw[1])                           # (the leaf's middle: the hinge + 0.6 m toward -x... world)
    _put_jones((_dc[0], _dc[1] + 1.1, V.SHED[2]), _dc)
if 'atsewer' in DBG:                                       # v4 walk leg 2: the airbase sewer exit (top of ladder 4053), facing north
    _put_jones((373825 / 4096.0, 875706 / 4096.0, _bh(373825 / 4096.0, 875706 / 4096.0)), (373825 / 4096.0, 885706 / 4096.0))
if 'atgate' in DBG:                                        # v4 test: the chip done, Jones 1 m in front of the vehicle gate's code pad
    m.set(GATE_PAD, 24, '!GenericTBA_%d.isFinished' % GATE_PAD)
    _gp_ = [c_ / 4096.0 for c_ in _gpad]
    _put_jones((SB.X1 - 1.05, _gp_[1], GATE_FLOOR), _gp_)
if 'attrk' in DBG:                                         # loop test: on the long ramp short of the trigger, facing up it (the troop truck comes down)
    _q_ = TUN.at(52.0); _q2 = TUN.at(90.0)
    _lt_ = 2.3 if 'trkhit' in DBG else -2.5                # ('trkhit': in the truck's lane)
    _put_jones((_q_[0] + _q_[4][0] * _lt_, _q_[1] + _q_[4][1] * _lt_, _q_[2]), (_q2[0], _q2[1]))
    m.set(VGATE, 19, '0')
if 'athop' in DBG:                                         # v4 test: after the gate cutscene, 6 m short of the guard van's platform
    m.set(RUN, 9, 'LevelFlow_10.nTick > 2 * GAME_FREQUENCY')
    _hp_ = (HOP_P[0] / 4096.0, HOP_P[1] / 4096.0)
    _put_jones((_hp_[0] - 6.0, _hp_[1], _bh(_hp_[0] - 6.0, _hp_[1])), (_hp_[0], _hp_[1]))
ssboom.apply(globals())                                    # (owner 96: the clusters + 'boomtest=' words, before the debug loop)
for part in DEBUG.split(';'):
    if part == 'case':                                     # stand 1.5-3.5 m from the briefcase, looking at it (dbgrun still DBG_W)
        cand = [q['pos'] for q in GRAPHS[2] if 1.5 * 4096 < math.dist(q['pos'][:2], CASE_P[:2]) < 3.5 * 4096
                and abs(q['pos'][2] - _fz) < 0.5 * 4096 and q['terrain'] == 0]
        sx, sy, sz = min(cand, key=lambda q: abs(math.dist(q[:2], CASE_P[:2]) - 2.5 * 4096))
        m.set(0, 3, sx); m.set(0, 4, sy); m.set(0, 5, sz + 300); m.set(0, 6, math.atan2(-(CASE_P[0] - sx), CASE_P[1] - sy))
        print('debug: player %.1f m from the briefcase, yaw %.4f' % (math.dist((sx, sy), CASE_P[:2]) / 4096, math.atan2(-(CASE_P[0] - sx), CASE_P[1] - sy)))
    if part == 'twin':                                     # both charges at Hind 3901's spot (dbgrun 'use' DBG_REPEAT=1 plants
        sp_, (fl_, g_) = CHARGE_AT[3901], CHARGE_FLOOR[3901]  # both for real -> the armed latch, fuse, clock, both blasts)
        # (10-12 tests: dbgrun could NOT plant a 2nd charge from one spot - next to the first one (40/15/2 cm) or 60 deg
        #  to the left in the air - it never engaged; a 'use' needs the view ray to hit a surface at the TBA. Kept for a
        #  manual test only; the real chain was checked in parts: one real plant + 'targets' (latch on a timer).)
        r_ = np.array([sp_[0] - fl_[0], sp_[1] - fl_[1]]); a_ = math.radians(60.0)
        r_ = np.array([r_[0] * math.cos(a_) - r_[1] * math.sin(a_), r_[0] * math.sin(a_) + r_[1] * math.cos(a_)])
        q_ = (fl_[0] + r_[0], fl_[1] + r_[1], sp_[2])
        for k_, c_ in enumerate(q_):
            m.set(CHARGES[3904], 3 + k_, float(c_))
        print('debug: charge 2 moved next to charge 1 (Hind 3901)')
    if part.startswith('at=') and int(part[3:]) in CHARGE_FLOOR:   # stand at a Hind charge spot (else Kit's at=)
        hid_ = int(part[3:])
        (sx, sy, sz), g_ = CHARGE_FLOOR[hid_]
        m.set(0, 3, sx); m.set(0, 4, sy); m.set(0, 5, sz + 300); m.set(0, 6, g_)
        print('debug: player at the charge spot of Hind %d' % hid_)
    if part.startswith('start='):
        c = [float(x) for x in part[6:].split(',')]
        m.set(0, 3, c[0]); m.set(0, 4, c[1]); m.set(0, 5, c[2])
        if len(c) > 3:
            m.set(0, 6, c[3])
    if part.startswith('face='):                           # stand ~25 m from a task, looking at it
        tid = int(part[5:])
        tx, ty, tz = m.arg(tid, 3), m.arg(tid, 4), m.arg(tid, 5)
        best = None
        for g, nodes in GRAPHS.items():
            for q in nodes:
                n_ = q['pos']; d = math.hypot(n_[0] - tx, n_[1] - ty)
                if 50000 < d < 110000 and abs(n_[2] - tz) < 6000 and not q['crit'] and q['terrain'] == 1:   # outdoors
                    if best is None or abs(d - 75000) < abs(best[1] - 75000):
                        best = (n_, d)
        (sx, sy, sz), _ = best
        m.set(0, 3, sx); m.set(0, 4, sy); m.set(0, 5, sz + 500); m.set(0, 6, math.atan2(-(tx - sx), (ty - sy)))
        print('debug: player at %.0f,%.0f,%.0f facing task %d (%.0f units)' % (sx, sy, sz, tid, best[1]))
    if part.startswith('near='):                           # stand a few metres from a task (doors), looking at it
        tid = int(part[5:])
        tx, ty, tz = m.arg(tid, 3), m.arg(tid, 4), m.arg(tid, 5)
        best = None
        for g, nodes in GRAPHS.items():
            for q in nodes:
                n_ = q['pos']; d = math.hypot(n_[0] - tx, n_[1] - ty)
                if 5000 < d < 20000 and abs(n_[2] - tz) < 4000 and not q['crit'] and (best is None or d < best[1]):
                    best = (n_, d)
        (sx, sy, sz), _ = best
        m.set(0, 3, sx); m.set(0, 4, sy); m.set(0, 5, sz + 500); m.set(0, 6, math.atan2(-(tx - sx), (ty - sy)))
        print('debug: player at %.0f,%.0f,%.0f facing task %d (%.0f units)' % (sx, sy, sz, tid, best[1]))
    if part.startswith('door='):                           # stand 1.5 m in front of a door leaf, looking at it
        tid = int(part[5:].split(',')[0])
        dr = [d_ for d_ in nv.doors() if d_['id'] == tid][0]
        c, nrm = dr['center'], dr['normal']
        sides = {'in': (HUT_SIGN,) if tid == 3927 else (1,), 'out': (-HUT_SIGN,) if tid == 3927 else (-1,)}   # ',in' = inside the hut
        cand = [c + nrm * sgn * 6000 for sgn in sides.get(part.rsplit(',', 1)[-1], (1, -1))]
        hz = lambda p_: min((abs(q['pos'][2] - dr['zlo']), q) for nodes in GRAPHS.values() for q in nodes
                            if math.hypot(q['pos'][0] - p_[0], q['pos'][1] - p_[1]) < 9000)[0] if any(
                            math.hypot(q['pos'][0] - p_[0], q['pos'][1] - p_[1]) < 9000 for nodes in GRAPHS.values() for q in nodes) else 1e9
        p_ = min(cand, key=hz)                                 # the side that has walkable ground at door height
        m.set(0, 3, float(p_[0])); m.set(0, 4, float(p_[1])); m.set(0, 5, float(dr['zlo']) + 500)
        m.set(0, 6, math.atan2(-(c[0] - p_[0]), (c[1] - p_[1])))
        msg('SS_DBG_DOOR', 'DEBUG door open', 'Door_%d.nDoorOpenTicks > 0' % tid, 'DEBUG: DOOR %d IS OPEN' % tid, 30.0)
        print('debug: player at %.0f,%.0f in front of door %d' % (p_[0], p_[1], tid))
    if part.startswith('face=') and lit(L[int(part[5:])].args[1]) == 'ExplodeObject':
        msg('SS_DBG_BOOM', 'DEBUG target destroyed', 'ExplodeObject_%s.isExploded' % part[5:], 'DEBUG: TARGET DESTROYED', 30.0)
    if part == 'atbunker':                                 # 11-02 test: Jones 6 m in front of the bunker's blast door, facing it
        _sp = BW(-0.6, -7.5, 0.2)
        m.set(0, 3, _sp[0]); m.set(0, 4, _sp[1]); m.set(0, 5, _sp[2]); m.set(0, 6, 0.0)
    if part.startswith('bpos='):                           # 11-02 test: stand at bunker-local x,y,z (m; +y = into the hill) facing dg
        _c = [float(x_) for x_ in part[5:].split(',')]     #  (0 = into the hill, 90 = west)
        _sp = BW(_c[0], _c[1], _c[2])
        m.set(0, 3, _sp[0]); m.set(0, 4, _sp[1]); m.set(0, 5, _sp[2]); m.set(0, 6, math.radians(_c[3]))
    if part == 'twotimers':                                # 11-02 HUD test: two MissionTimers at once (do they stack or overlap?)
        m.add_child(LOGIC, T(nid(), 'MissionTimer', 'DEBUG mission clock', '1', '', 900))
        m.add_child(LOGIC, T(nid(), 'MissionTimer', 'DEBUG launch clock', 'LevelFlow_10.nTick > 20 * GAME_FREQUENCY', '', 90))
    if part == 'ghost':                                    # 11-01 life test: the AI cannot see Jones (HumanPlayer visibility min/max 0)
        m.set(0, 12, 0.0); m.set(0, 13, 0.0)
    if part == 'sniper':                                   # 11-01 combat test: watch + provoke through a scope
        m.set(0, 9, 'Human_AddWeapon("WEAPON_ID_DRAGUNOV"), Human_AddAmmoForWeapon("WEAPON_ID_DRAGUNOV",60);')
    if part == 'guns':                                     # 11-01 gun-bug test: every rifle the player can carry or pick up
        m.set(0, 9, ', '.join('Human_AddWeapon("WEAPON_ID_%s"), Human_AddAmmoForWeapon("WEAPON_ID_%s",120)' % (w_, w_)
                              for w_ in ('AK47', 'MP5SD', 'DRAGUNOV', 'SPAS12', 'MINIMI')) + ';')
    if part == 'rpg':
        m.set(0, 9, 'Human_AddWeapon("WEAPON_ID_RPG7"),\nHuman_AddAmmo("AMMO_ID_RPG7CLIP", 8);')
if 'nointro' in DBG:                                       # (then never DBG_INTRO=1: its Esc opens the pause menu)
    m.set(CSI['skip'], 7, 'EditVariable_%d.nValue == 0' % CSI['skip'])
if 'noenemies' in DBG:                                     # walk tests that must not be shot at: every squad off
    m.set(SQ_PARENT, 3, '0')
if 'nolaunch' in DBG:                                      # noclip inspection copy (work/noclip): flying past the console must not end the mission
    m.set(LAUNCH, 9, '0')
if 'noai' in DBG:
    m.remove(SQ_PARENT)
    print('debug: all squads removed')
if DEBUG:
    print('*** TEST BUILD (%s) - do not ship ***' % DEBUG)

for t_, d_, p_ in tasks(m.stmts):                          # level time includes the intro: count from its end instead
    for k_, a_ in enumerate(t_.args):
        if isinstance(a_, Str) and 'LevelFlow_10.nTick' in a_:
            t_.args[k_] = v(str(a_).replace('LevelFlow_10.nTick', 'LevelTimer_%d.nTick' % CSI['after']))

# =========================================================== 11. validate + write
problems = m.validate()
import re as _re
for t, d, p in tasks(m.stmts):
    ty = lit(t.args[1])
    if ty in ('Terminal', 'C4BombArea', 'SpawnPoint', 'SpawnArea', 'Network_Mission', 'Network_Objective', 'AIStationaryGunHolder'):
        problems.append('multiplayer-only task left: %s %s' % (lit(t.args[0]), ty))
    for a in t.args:
        if isinstance(a, Str) and _re.search(r'\bNet[A-Z]\w*_|HUMAN_TEAM_|\bmp/', a):
            problems.append('multiplayer reference left in task %s: %s' % (lit(t.args[0]), a[:60]))
if problems:
    print('VALIDATION FAILED:'); [print('  -', p) for p in problems[:40]]
    sys.exit(1)
out = os.environ.get('SS_OUT') or os.path.join(HERE, 'build', 'sandstorm' + ('_TEST' if DEBUG else ''))   # (SS_OUT: a side build dir)
import lodfix                                             # (owner 10-11: far buildings and trees popped in the cutscenes)
if SOLDIERS:
    _SSP.place(K, m, _ST)
    _SSM.assign(m, K)
if SSW.WORLD:
    SSW.hang(m, K, nid, T, _ST, PICK)
    SSW.indoorize(m, _OVL, K)
    SSW.light_trees(m, nid)
LOD_QVM, _lodn = lodfix.build(m, os.path.join(G_ + 'MISSIONS', 'multiplayer', 'sandstorm'),
                              extra={**alskins.lod_rows(AL_SKINS), **alskins.lod_rows(['bubsci_1']), **DRS.lod_rows(), **(_SSM.lod_rows() if SOLDIERS else {}), **SSW.lod_rows(),
                                     **{n_: [300.0, 600.0, 900.0, 1200.0, 1500.0] for n_ in SS_MODELS}})   # (no row = invisible beyond 10 m)
print('lodfix: %d model cut-offs raised / added, %d forests drawn farther' % (len(_lodn), lodfix.raise_forests(m)))
for _f in (2914, 2915):                                    # (qa sky 10-31: the intro's high key culled these at 400 m)
    if float(m.arg(_f, 20)) < 900.0:
        m.set(_f, 20, 900.0)
if TALK:
    _TK.ai(globals())                                      # (last: every AI edit is in)
ssbay.apply(globals())
ssloot.apply(globals())
if VOICES:
    _VC.ai(globals())                                      # (after sstalk, and after ssbay: it writes the scientists' scripts whole. Each man's own voice prefix runs first)
import ssfew
m.set(4089, 7, float(os.environ.get('SS_SUNSHADOW', '0.06')))   # (judge A03: the sun's shadow strength 0.25 -> 0.06; the man-shaped shadows on indoor walls nearly gone, g9ss4; SS_SUNSHADOW=<v> for tests)
print('release flags: GARRISON2=%s alarm_ai=%s OUTRO2=%s SOLDIERS=%s CHARS=%s GUNROOM=%s TRUCKS2=%s INTRO2=%s TALK=%s WORLD=%s FEWMEN=%s' % (GARRISON2, GARRISON2, OUTRO2, SOLDIERS, _SSM.CHARS, SB.GUNROOM, TRUCKS2, INTRO2, TALK, SSW.WORLD, ssfew.FEWMEN))
if ssfew.FEWMEN:                                           # (owner 77: 5 men on the missile side; SS_FEWMEN=0 = the full garrison. Test builds too: review 11-07 finding 8)
    ssfew.apply(globals())
if TRUCKS2 and 'noai' not in DBG and 'noenemies' not in DBG:   # (judge Q08 11-13: the cab actors wear the door soldier's final model, after every skin pass)
    TK.match_driver_models(m, lit, tasks, SQUAD_IDS, {TROOP: 'U truck troops 1 driver', TROOP2: 'U truck troops 2 driver'})
import ssbrain                                             # (owner G09 11-13: combat / investigate sight as the originals, backup calls, event priorities; last AI pass, after ssfew)
ssbrain.apply(globals())
_SCAMS.apply(globals())                                    # (owner 116: last, every cutscene key and camera is in)
if TRUCKS2:
    TK.late(globals())                                     # (rc7s18 ear: task edits of the sound pass must come before m.write - hit-blast impact, sirens stop in cutscenes)
# (A9 orch-2 11-15, the S17 class: a soldier who reaches a door node toggles the nearest door and the lock is not read (humanai.c 10405).
#  So NO door with a lock ('1' or an expression) may have door nodes in any graph: it must be in navgen's closed_doors. Runs last, when
#  every lock is set (ssloot locks 4025 / 4026 after navgen); ss-int's work/sandstorm/chkdoors.py is the candidate gate (nearest-door rule))
_LOCKED = sorted(i_ for i_ in m.find('Door') if str(lit(m.byid[i_].args[18])).strip() not in ('', '0') and i_ not in NAV_OPEN)   # (SS_RQ7=0: the leaves are open for navgen, ssloot's cut, chkdoors judges them)
_lk_bad = []
for _dr in nv.doors():
    if _dr['id'] not in _LOCKED:
        continue
    _r = _dr['width'] * 0.5 + 2600.0 + 2048.0                # (navgen puts the pair at width / 2 + 2600 units from the centre; + 0.5 m)
    for _g, _ns in GRAPHS.items():
        _hit = [q_['id'] for q_ in _ns if q_['crit'] and math.hypot(q_['pos'][0] - _dr['center'][0], q_['pos'][1] - _dr['center'][1]) < _r
                and abs(q_['pos'][2] - _dr['zlo']) < 2.5 * 4096.0]
        if _hit:
            _lk_bad.append((_dr['id'], str(lit(m.byid[_dr['id']].args[2]))[:40], _g, _hit[:4]))
assert not _lk_bad, 'A9: locked doors with AI door nodes (a soldier opens them unlocked): %s' % _lk_bad
print('A9 check: %d locked doors, none has AI door nodes: %s' % (len(_LOCKED), _LOCKED))
if SB.GUNROOM and os.environ.get('SS_RQ8', '1') != '0' and 'noai' not in DBG and 'noenemies' not in DBG:
    # (RQ8 / N-e5 ss-look 11-16: the gun-room flashes = enemy hand grenades 2-6 m from Jones on the M2. GN.gun_ai's 'no grenades on the gun'
    #  rule went first (~l.1522), then HUNT.build's soldier wrapper put the ENEMYDETECTION branch in front of it; the truck troops never had
    #  it. Last AI pass: the rule is the first statement again in every man below ground; build gate: every grenade carrier below has it first)
    _rq8, _rq8g = {}, []
    for _k, (_sid, _hids) in SQUAD_IDS.items():
        if not _k.startswith('U '):
            continue
        for _h in _hids:
            if _h not in m.byid:
                continue
            _aidr = next((lit(c_.args[0]) for c_ in m.byid[_h].args if hasattr(c_, 'args') and lit(c_.args[1]) == 'HumanAI'), None)
            _dat = m.ai_files.get(str(_aidr))
            if not isinstance(_dat, (bytes, bytearray)):
                continue
            _ver, _body = alarmai.decompile_ai(bytes(_dat))
            _how = GN.gun_ai_first(alarmai, _body, GUNROOM_ZONE)
            _rq8[_how] = _rq8.get(_how, 0) + 1
            if _how != 'kept':
                m.ai_files[str(_aidr)] = alarmai.compile_ai(_body, _ver)
            _ok = alarmai.to_text(alarmai.decompile_ai(bytes(m.ai_files[str(_aidr)]))[1][:1])
            if 'WEAPON_ID_GRENADE' in str(lit(m.byid[_h].args[9])) and not ('AreaActivate_%d.nActive' % GUNROOM_ZONE in _ok.splitlines()[0] and 'SetGrenadeThrowProb' in _ok):
                _rq8g.append((_k, _h))
    assert not _rq8g, 'RQ8: grenade carriers below ground without the gun-room rule first: %s' % _rq8g
    print('RQ8: gun-room grenade rule first in every man below ground: %s' % _rq8)
loop_walkers()                                            # (S3 ss-life 11-15: robot stop-and-look patrols -> node-to-node loops, same ids, no rng)
MOVEWAIT = _MW.add_latch(m, T, nid, LOGIC, CSI['after']) if LIVE_PICKETS else None   # (orchestrator 11-14: posts stand through the intro, move 2 s after it; last nid())
if SB.GUNROOM and GN.S14B_ON:                            # (S14b decision 91: the lobby barricade's sandbags; after the last nid(), before the intro actors are removed: no id shifts, no id reused)
    _s14b = GN.screen_props(globals())
    print('S14b: lobby barricade %d bags (ids %d-%d), collision box %s in the gun room mesh' % (len(_s14b), _s14b[0], _s14b[-1], GN.SCREEN_BOX))
if SB.GUNROOM and GN.S14W_ON:                            # (S14 window, orch-2 11-17: the steel window shutter + its latch; after the last nid() like S14b: no id shifts)
    GN.window_shutter(globals())
for _da in (__import__('ssintro').DROP_ACTORS if INTRO2 else []):   # (G43 11-14: after the last nid(), so no task id shifts)
    m.remove(_da)
print('G43: intro actors removed before write: %s' % (__import__('ssintro').DROP_ACTORS if INTRO2 else []))
m.write(out, MISSION_ID, FOLDER, 'sandstorm.spr', debug=bool(DEBUG), own_common='common')
_mj = os.path.join(out, 'meta.json')                        # (tools/cscheck.py SK06: the squads stay live in these cutscenes on purpose)
_meta = json.load(open(_mj))
_meta['qa'] = {'live_squads_in_cutscenes': {
    'intro': "owner 11-02 round 6: 'the cutscenes must show the real live soldiers' (the CCTV feeds film the live posts; Jones is off)",
    'outro': "owner 11-02 round 6: live soldiers in the cutscenes (the mission is over, Jones is off)",
    'mid': "v4 vehicle-gate cutscene: the satellite shot shows the live reinforcements by their helicopters (Jones is off; the power-cut cut-in still gates its squads)"}}
json.dump(_meta, open(_mj, 'w'), indent=1)
# owner 11-01 'original enemies crouch, peek, dodge and move to cover; ours stand and shoot': the engine's combat AI reads the
# graphs' cover items from graphs/graphcover<id>.dat (the originals ship them; our generated graphs had none) - tools/graphcover.py
import graphcover
_CT = K._tris()[0]
for _gid, _nodes in sorted(GRAPHS.items()):
    _data, _n = graphcover.build(_CT, [(q_['id'], q_['pos']) for q_ in _nodes])
    open(os.path.join(out, 'graphs', 'graphcover%d.dat' % _gid), 'wb').write(_data)
    print('graphcover %d: %d of %d nodes are cover' % (_gid, _n, len(_nodes)))
import shutil as _sh_ov
_sh_ov.copytree(os.path.join(XSTAGE, 'overlay'), os.path.join(out, 'overlay'), dirs_exist_ok=True)
_sh_ov.rmtree(XSTAGE, ignore_errors=True)
if SSW.WORLD:
    SSW.relight(m, out, K)
ssboom.relight(globals(), out)                             # (rc7d review: an ExplodeObject reads '<id>a_<node>_<lod>.olm', the barrels drew full bright)
os.makedirs(os.path.join(out, 'overlay'), exist_ok=True)
open(os.path.join(out, 'overlay', 'lod.qvm'), 'wb').write(LOD_QVM)
if WRECK_MODEL == 'b740_01_1':
    import burnt as _burnt
    _burnt.add_burnt_model(os.path.join(out, 'overlay'), 'sandstorm', '740_01_1', 'b740_01_1')
else:
    import wreck as _wreck
    _wreck.add_wreck_model(os.path.join(out, 'overlay'), 'sandstorm', src='740_01_1', dst=WRECK_MODEL)

# =========================================================== 12. sound banks. The PATH entry of a bank must name the folder it
# is loaded from or the game registers none of its samples (that silenced the alarm siren and all level ambience).
G_APP = r'C:\Users\1qdeath\Games\IGI2\app'
MPS = os.path.join(G_APP, 'MISSIONS', 'multiplayer', 'sandstorm', 'sounds')
LEVEL_SND = 'LOCAL:missions/multiplayer/%s/sounds' % FOLDER
extra, defs, seen = [], [], set()
for name, (path, secs) in sorted(VO.items()):              # Anya's voice-over
    extra.append((name + '.wav', sb.riff_to_ilsf(open(path, 'rb').read(), flags=0x1001)))
    extra.append((name + '.syn', syn_from_wav(path)))   # (11-01: the lip-sync envelope the Morph QTask IDs read)
    defs.append('DefineSound("%s", "%s", 0, 0, 0, 1, 2.0, 1e+02, -1, -1, -1, -1, FALSE)' % (name, name))
    seen.add(name.lower())
for name, (mp3, line, secs) in sorted(ORIG_VO.items()):    # (11-01) the ORIGINAL speech clips, their own DefineSound lines
    extra.append((name.upper() + '.mp3', mp3)); defs.append(line); seen.add(name)
    extra += [(name.upper() + '.syn', b_) for b_ in ORIG_SYN.get(name, [])]
print('original speech clips: %s' % ', '.join('%s %.1f s' % (n_, v_[2]) for n_, v_ in sorted(ORIG_VO.items())))
for n_, b_ in sb.read_bank(os.path.join(G_APP, 'MISSIONS', 'location2', 'level1', 'sounds', 'sounds.res'))[1]:
    bn = n_.rsplit('/', 1)[1]
    if False and bn.lower().startswith('arab_0'):          # (11-02: no Arabic shouts - every soldier speaks English)
        extra.append((bn, b_)); seen.add(bn[:-4].lower())
        defs.append('DefineSound("%s", "%s", 0, 0, 0, 0.6, 1e+01, 1e+02, -1, -1, -1, -1, FALSE)' % (bn[:-4], bn[:-4]))
own = {n.rsplit('/', 1)[1].rsplit('.', 1)[0].lower() for n, _ in sb.read_bank(os.path.join(MPS, 'sounds.res'))[1]}
for bank, prefixes, vol, *src_qvm in AMB_BANKS:            # original samples with the source level's own DefineSound lines
    orig_d = {}
    if src_qvm:
        _v, st_ = igiqvm.decompile(open(src_qvm[0], 'rb').read())
        for grp in st_:
            for d_ in (grp.args if isinstance(grp, Call) else []):
                if isinstance(d_, Call) and d_.name == 'DefineSound':
                    orig_d[str(lit(d_.args[1])).lower()] = d_
    for n_, b_ in sb.read_bank(bank)[1]:
        bn = n_.rsplit('/', 1)[1]
        stem = bn.rsplit('.', 1)[0]
        if any(stem.lower().startswith(p_) for p_ in prefixes) and stem.lower() not in seen and stem.lower() not in own:
            extra.append((bn, b_)); seen.add(stem.lower())
            defs.append(igiqvm.stmts_to_qsc([orig_d[stem.lower()]]).strip().rstrip(';') if stem.lower() in orig_d else
                        'DefineSound("%s", "%s", 0, 0, 0, %s, 1e+01, 1e+02, -1, -1, -1, -1, FALSE)' % (stem, stem, vol))
os.makedirs(os.path.join(out, 'sounds'))
if TALK:
    _TK.sounds(extra, defs, sb)
if VOICES:
    _VC.sounds(extra, defs, sb)
import ssvsound as _VS                                     # (owner 11-14: Hinds + train on the level's own sound names, tools/ssvsound.py)
_VS.sounds(extra, defs, sb)
if TRUCKS2:
    TK.audio(globals(), extra, defs, sb)                   # (judge A1/A5/A7 11-14: truck engine / idle / impact / horn + hall siren samples and level defs)
open(os.path.join(out, 'sounds', 'sounds.res'), 'wb').write(sb.rebase_bank(os.path.join(MPS, 'sounds.res'), LEVEL_SND, add=extra))
sver, sst = igiqvm.decompile(open(os.path.join(MPS, 'sounds.qvm'), 'rb').read())
sqsc = igiqvm.stmts_to_qsc(sst) + '\nDefineGroup(\n    "SS VOICE AND AMBIENCE",\n    ' + ',\n    '.join(defs) + '\n);\n'
open(os.path.join(out, 'sounds', 'sounds.qvm'), 'wb').write(igiqvm.compile_stmts(igiqvm.parse_qsc(sqsc), sver))
assert not sb.check_bank(os.path.join(out, 'sounds', 'sounds.res'), LEVEL_SND)[2]
import origsounds as _orig
ssmusic.install(out)
# own common folder (owner 11-02 'soldiers speak a foreign language - all soldier speech in English, like the originals'):
# the guards' voice events (AISquad_aazVoiceTable, decomp aisquad.c / OpenIGI Igi2AiSquadVoices: GV_xx_01/02 per event) are
# defined onto the ORIGINAL English radio recordings of the multiplayer common bank (three voices mpr1/2/3_*)
MPC = os.path.join(G_APP, 'MISSIONS', 'multiplayer', 'common', 'sounds')
COMMON_SND = 'LOCAL:missions/multiplayer/%s/common/sounds' % FOLDER
os.makedirs(os.path.join(out, 'common', 'sounds'))
open(os.path.join(out, 'common', 'sounds', 'sounds.res'), 'wb').write(sb.rebase_bank(os.path.join(MPC, 'sounds.res'), COMMON_SND))
_EN = {   # event -> (GV ids, [radio lines])   texts: LANGUAGE/english messages.res radio/TEXT_c_m
    'HurryUp': ((1, 2), ['2_1', '1_5']),                 # Go go go! / This way!
    'Acknowledge': ((5, 6, 7), ['3_1']),                 # Affirmative
    'HoldArea': ((11,), ['2_8']),                        # Defend this area
    'SearchArea': ((13,), ['2_3', '1_3']),               # Stick together! / Move ahead, I'll cover you
    'RaiseAlarm': ((15, 16, 17), ['1_2']),               # Need assistance
    'ManStationaryGun': ((19,), ['3_4']),                # I'm in position
    'EnemySpotted': ((26, 27), ['1_1']),                 # I see 'em!
    'EnemyFound': ((30, 31), ['1_1', '1_4']),            # I see 'em! / Cover me!
    'EnemyDetected': ((34, 35, 36), ['1_1', '1_4']),
    'GunShotHeard': ((40, 41), ['1_8']),                 # Be quiet
    'WhatsThat': ((47, 48), ['1_8']),
    'Engaging': ((62, 63, 64, 66), ['5_1', '1_4']),      # Eat this! / Cover me!
    'Grenade': ((75, 76), ['3_5']),                      # Grenade!
    'LostTarget': ((80, 81, 82), ['2_9']),               # Regroup!
    'TakeCover': ((84,), ['1_4']),
    'Stop': ((49,), ['1_8']),
    'BackToIdle': ((87, 88, 89, 90), ['1_6']),           # Area secure
    'FalseAlarm': ((91, 92, 93, 94), ['1_6']),
    'ManDown': ((60,), ['1_2']),
}
_have = {n.rsplit('/', 1)[1].rsplit('.', 1)[0].lower() for n, _ in sb.read_bank(os.path.join(MPC, 'sounds.res'))[1]}
_gv = []
for _ev, (_ids, _lines) in sorted(_EN.items()):
    for _k, _gid in enumerate(_ids):
        for _suf, _voice in (('01', 1 + _k % 3), ('02', 1 + (_k + 1) % 3)):
            _ln = _lines[(_k + int(_suf)) % len(_lines)]
            _smp = 'mpr%d_%s' % (_voice, _ln) if 'mpr%d_%s' % (_voice, _ln) in _have else 'mpr1_%s' % _ln
            assert _smp in _have, (_ev, _smp)
            _gv.append('DefineSound("GV_%02d_%s", "%s", 0, 0, 0, 1, 8.5, 1.2e+02, -1, -1, -1, -1, FALSE)' % (_gid, _suf, _smp))
_gv.append('DefineSound("GV_75_01", "mpr1_3_5", 0, 0, 0, 1, 8.5, 1.2e+02, -1, -1, -1, -1, FALSE)' if not any('"GV_75_01"' in g_ for g_ in _gv) else '')
_gv = [g_ for g_ in _gv if g_]
if VOICES:
    _gv = _VC.gv(_gv, _EN)                                 # (the English squad barks go where the young soldier's recording covers the situation; the rest stay)
if TALK and os.environ.get('SS_TALK_GV', '1') == '0':
    _gv = ['DefineSound("GV_75_01", "mpr1_3_5", 0, 0, 0, 0.01, 1, 2, -1, -1, -1, -1, FALSE)']   # (owner 60: all shouts recorded in Iraqi: the English radio barks go; the group may not be empty)
_cv, _cst = igiqvm.decompile(open(os.path.join(MPC, 'sounds.qvm'), 'rb').read())
_cq = igiqvm.stmts_to_qsc(_cst) + '\nDefineGroup(\n    "AI GUARDS ENGLISH",\n    ' + ',\n    '.join(_gv) + '\n);\n'
open(os.path.join(out, 'common', 'sounds', 'sounds.qvm'), 'wb').write(igiqvm.compile_stmts(igiqvm.parse_qsc(_cq), _cv))
print('guard voices: %d English GV defs on the original radio recordings' % len(_gv))
assert not sb.check_bank(os.path.join(out, 'common', 'sounds', 'sounds.res'), COMMON_SND)[2]
print('sound banks: level %d KB (%d voice lines), common %d KB' % (os.path.getsize(os.path.join(out, 'sounds', 'sounds.res')) // 1024,
      len(VO), os.path.getsize(os.path.join(out, 'common', 'sounds', 'sounds.res')) // 1024))
import ssprune; ssprune.apply(out)                         # (11-07: last, the engine's 600 slot LOD table)
import ssperf; ssperf.apply(out)                           # (11-13 ss-perf: frame rate - head maps 1024, loose-prop and bush cut-offs, base + sewer shells drawn only near them; SS_PERF=0 off)
import ssportal; ssportal.apply(out)                       # (S1 11-17 ss-look: arg 12 TRUE on the props sectorcheck finds mis-registered; SS_PORTAL=0 off)
print('Operation Sandstorm built: mission %d | enemies %d | graphs %s | computer %d security %d hinds %s briefcase %s extract %d'
      % (MISSION_ID, ENEMY_COUNT[0], {g: len(n) for g, n in GRAPHS.items()}, COMPUTER, SECURITY_PC, HINDS, CASE, EXTRACT))
print('objects.qvm %d bytes, %d AI files -> %s' % (os.path.getsize(os.path.join(out, 'objects.qvm')), len(m.ai_files), out))
if MOVEWAIT: _MW.apply(out, ('S landing zone pickets', 'S south gate'), MOVEWAIT)
import ssspawnwait; ssspawnwait.apply(out)               # (G43 11-14: run-time men act only 3 s after their container opened)
import sscreate; sscreate.check(out)                       # (G43 11-14: no run-time soldier with a move order in the first 10 s)
if 'noenemies' not in DBG and 'noai' not in DBG:
    import ssface; ssface.check(out, free_run)             # (S2 ss-life 11-15: no standing man faces a wall / obstacle without a partner or a reason)
if 'noenemies' not in DBG and 'noai' not in DBG:           # (RQ7 / N9 ss-life 11-16: no order (script node, patrol walk, alarm switch) to a node on another island of the man's graph
    import islands                                         #  or to a missing node: the engine kills him (humanai.c 10963-10972). rc7s25: 10 FAIL (squads 1113, 1145))
    _isl = islands.main(['islands', out])
    assert _isl == 0 or not RQ7, 'RQ7: orders to another graph island (tools/islands.py %s): the engine kills these men' % out
