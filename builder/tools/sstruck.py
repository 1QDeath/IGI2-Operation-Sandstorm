"""sstruck - Sandstorm's troop trucks on the ramp (owner 11-06, item 65): wheels that turn (RotateAttachment on ATTA rows of the truck, slowed to a stop by
RotateAttachment_SetTargetSpeed), a driver in the cab (the originals' EditBoneObj child with fly_chopper), a real stop, men who jump down behind the tailgate and fight,
a hit that is a short cutscene before Jones dies. Behind env SS_TRUCKS2=1. Truck nose = local -x, ground z = 0. World units unless named."""
import math
import numpy as np
import mefmesh
import modelkit as MK
import biprefabs as BP
import cutscene as CS
import sshall as SH

M = 4096.0
AXLES = {'ss_twf_1': (2, 3, -9.0, -1.0), 'ss_twr_1': (4, 5, -1.0, 1.42), 'ss_twq_1': (4, 5, 1.42, 9.0)}   # groups, x range (m)
DRIVER = (-0.4, 1.32, -0.2, 0.0)                           # (owner 87: the originals' L22 / L23 truck drivers with priboy_driving_truck, the clip itself carries the man to the seat, placed by eye on g8tk15; last = yaw on the truck. L22's 600_01_1 lies along y, this truck along x)
RIDERS = ((4.82, -1.36, 0.01, math.pi), (0.49, 1.36, 0.01, 0.0), (3.22, -1.33, 0.02, math.pi))   # (L22 'Inside truck': guard_in_back_of_truck, x y z yaw; L22's 600_07_1 lies along y, turned 90 degrees for this truck, which lies along x)
CLIMB_S = 1.6                                               # guard_get_out_of_truck
DRIVER_CLIMB_S = 0.9                                        # (judge 11-13: the cab driver's jump is out of sight after ~0.4 s; at 1.6 s nobody stood by the truck for ~1.2 s before the door soldier (g9jf1 h38-h40))
STOPS = (118.0, 134.0)                                     # where the two trucks stop (tunnel arc, m): the second behind the first
TROOPS = ((3.9, -0.9), (3.9, 0.9), (5.0, 0.0))             # men behind the tailgate (local m)
DOOR = (-1.9, -1.75)                                       # (owner 118 + S15 11-15: the driver steps down on the LANE side, not into the 1 m slot at the tunnel wall; local m)


def _axle(orig, key):
    g0, g1, x0, x1 = AXLES[key]
    G = SH._orig_parts(orig, (g0, g1))
    out, pts = {}, []
    for gi, (P, T_, N, U) in G.items():
        c = P[T_].mean(1)[:, 0] / M
        tr = T_[(c >= x0) & (c < x1)]
        out[gi] = (P, tr, N, U)
        pts.append(P[np.unique(tr)])
    A = np.vstack(pts)
    hub = np.array([(A[:, 0].min() + A[:, 0].max()) / 2, 0.0, (A[:, 2].min() + A[:, 2].max()) / 2])
    return out, hub


def wheel_model(orig, key):
    """one axle with its wheels, origin on the hub"""
    G, hub = _axle(orig, key)
    parts = [(gi, [(P - hub, T_, N, U)]) for gi, (P, T_, N, U) in G.items()]
    return MK.model(parts, [BP.box_m(-0.02, -0.02, -0.02, 0.02, 0.02, 0.02)])


def truck_model(orig):
    """the map's truck 600_00_1, wheels off, an attachment row per axle, headlamps on"""
    G = SH._orig_parts(orig, (0, 1, 6, 7))                 # (1 = the canvas back: a troop truck needs one)
    gl = np.zeros(2, mefmesh.WOLG_DT)
    for k, y in enumerate((-0.85, 0.85)):
        gl[k] = ((-3.45 * M, y * M, 1.05 * M), 1500.0, 1.0, 0.92, 0.7, 0xABABABAB)
    at = np.zeros(len(AXLES), mefmesh.ATTA_DT)
    for k, key in enumerate(AXLES):
        at[k]['name'] = key.encode()
        at[k]['pos'] = _axle(orig, key)[1]
        at[k]['rot'] = np.eye(3)
        at[k]['i0'], at[k]['i1'] = 0, -1
    # (owner G09b 11-13: the dark box of item 118 read as a driverless truck - gone: the cab is open again, the driver sits in it behind
    #  the glass of glass_model(). The hull is a low hood box ahead of the cab + the cab and bed, closer to the body than one 2.4 m box)
    return MK.model([(gi, [G[gi]]) for gi in sorted(G)], [BP.box_m(-3.3, -1.2, 0.0, CAB_X, 1.2, HOOD_Z), BP.box_m(CAB_X, -1.2, 0.0, 3.3, 1.2, 2.4)], glows=gl, atta=at)


CAB_X, HOOD_Z = -1.92, 1.55                                 # where the hull's hood box ends / how high it is (local m)
WIN_Z = (1.55, 2.32)                                         # window band of the cab, front and sides
GLASS_TEX = 'ss_tglass'


def tex_glass(n=32):
    """light grey-green tint, mostly see-through (cablecar's glass, a little lighter)"""
    return np.dstack([np.full((n, n), 0.66), np.full((n, n), 0.74), np.full((n, n), 0.76), np.full((n, n), 0.28)])


def glass_model():
    """owner G09b: the cab's windscreen + both side windows, lightly tinted (an EditRigidObj child of the truck, placed on the truck's own pose).
    (11-13: as a breakable ExplodeObject with hit faces outside the hull it broke on 1 of ~14 rig bursts and that once a fireball killed Jones
    beside the cab (g9gw5) - not shipped; the glass is plain glass, the seated driver cannot be shot)"""
    z0, z1 = WIN_Z
    see = [BP.box_m(-1.89, -0.84, z0, -1.87, 0.84, z1, uv=0.5),           # windscreen
           BP.box_m(-1.80, 0.86, z0, -1.00, 0.88, z1, uv=0.5), BP.box_m(-1.80, -0.88, z0, -1.00, -0.86, z1, uv=0.5)]   # side windows
    return MK.model([(0, see)], see, alpha_slots=(0,))     # (its collision = the panes, inside the hull boxes: it stops nothing)


def wheels(T, nid, guide, last):
    """the RotateAttachment children of a truck: turning from the start, run down in 1.5 s as the guide nears its last node (beta = the axle)"""
    out = []
    for key in AXLES:
        out.append(T(nid(), 'RotateAttachment', '', 0.0, 0.5, 0.0, key, 0, children=[
            T(nid(), 'SequenceCommand', '', 'SplinePathGuideQTask_%d.vPosition >= %d' % (guide, last - 1), 'RotateAttachment_SetTargetSpeed(1, 60, 0.0)', '1', 'SequenceCommand_SetCommand(-1)')]))
    return out


def engine(T, nid, guide, last):
    """ss_truck_engine while it drives, ss_truck_idle once it stands (the L15 helicopter's SoundGenerator pattern). Level defs from audio():
    (judge A1 11-14: the old names truck_engine / truck_idle are defined in no bank the game loads - the trucks were silent)"""
    a, b, c = nid(), nid(), nid()
    return T(nid(), 'SoundGenerator', '', children=[
        T(a, 'SequenceCommand', '', 'SplinePathGuideQTask_%d.vPosition > 0' % guide, 'SoundGenerator_PlaySound("ss_truck_engine")', '1', 'SequenceCommand_SetCommand(%d)' % b),
        T(b, 'SequenceCommand', '', 'SplinePathGuideQTask_%d.vPosition >= %d' % (guide, last), 'SoundGenerator_StopSound();', '1', 'SequenceCommand_SetCommand(%d)' % c),
        T(c, 'SequenceCommand', '', '1', 'SoundGenerator_PlaySound("ss_truck_idle")', '1', 'SequenceCommand_SetCommand(-1)')])


def horn(T, guide, at=1.0):
    """one horn blast as the truck starts down the ramp (judge A7 11-14), beside Anya's warning; id -1 tasks, nothing names them.
    The builder hangs it on the truck's GLASS child: a second SoundGenerator on the truck itself beside engine() was never heard (rc7s18 ear check)"""
    return T(-1, 'SoundGenerator', '', children=[
        T(-1, 'SequenceCommand', '', 'SplinePathGuideQTask_%d.vPosition > %.2f' % (guide, at), 'SoundGenerator_PlaySound("ss_truck_horn")', '1', 'SequenceCommand_SetCommand(-1)')])


# (judge A1/A7 11-14) level sound defs: name -> (source bank under MISSIONS or None = a COMMON sample, sample, vol, min m, max m, loop)
SOUNDS = {'ss_truck_engine': ('location2/LEVEL2', 'cs22_truckintloop', 0.32, 5.0, 120.0, True),   # L22's moving-truck loop (rc7s18 ear: -14..-17 dBFS beside the truck at vol 1, ~10 dB over the mix)
          'ss_truck_idle': (None, 'truck_idle', 1.0, 3.5, 100.0, True),                          # L17's truck idle (truck_idle_2 there), the sample is in COMMON
          'ss_truck_hit': ('location2/LEVEL2', 'cs22_truckland', 1.0, 6.0, 120.0, False),        # the impact, under the hit shot's black
          'ss_truck_horn': ('location2/level1', 'horn_02', 1.0, 10.0, 250.0, False),             # L21's horns
          'ss_hall_siren': (None, 'ALARM_2', 0.6, 5.0, 60.0, True)}                             # (ssgarr's hall sirens; rc7s18 ear: COMMON alarm_50 = vol 1, 50-1000 m, -15 dBFS at the surface gate)


def audio(g, extra, defs, sb):
    """builder sound step (after m.write): copy the samples into the level bank and define SOUNDS. Task edits go in late(), before m.write"""
    import os
    from qast import tasks, lit
    from mission_lib import v
    app = g['G_APP']
    have = {n.rsplit('/', 1)[-1].rsplit('.', 1)[0].lower() for n, _ in extra}   # (extra holds bare names, 'ss_ic1.wav')
    for name, (lv, smp, vol, lo, hi, loop) in SOUNDS.items():
        if lv is not None and smp.lower() not in have:
            got = [(n.rsplit('/', 1)[-1], b) for n, b in sb.read_bank(os.path.join(app, 'MISSIONS', *lv.split('/'), 'sounds', 'sounds.res'))[1] if n.rsplit('/', 1)[-1].rsplit('.', 1)[0].lower() == smp.lower()]
            assert len(got) == 1, (name, smp, len(got))
            extra.append(got[0]); have.add(smp.lower())
        defs.append('DefineSound("%s", "%s", 0, 0, 0, %g, %g, %g, -1, -1, -1, -1, %s)' % (name, smp, vol, lo, hi, 'TRUE' if loop else 'FALSE'))
    print('sstruck audio: %d defs (%s)' % (len(SOUNDS), ', '.join(SOUNDS)))


def late(g):
    """builder, just BEFORE m.write (rc7s18 ear check: audio() ran after objects.qvm was written, so its task edits never shipped):
    the impact on the hit blasts (bumper + backup run-over), and the hall sirens stop while any cutscene runs (ending, truck hits, ...)"""
    from qast import tasks, lit
    from mission_lib import v
    m, n = g['m'], 0
    for t, _, _ in tasks(m.stmts):
        if lit(t.args[1]) == 'ExplodeObject' and (str(lit(t.args[2])) == 'SS truck bumper' or str(lit(t.args[2])).startswith('SS run over ')):
            t.args[-1] = v('ss_truck_hit'); n += 1
    cs = ' || '.join('CutScene_%d.isRun' % lit(t.args[0]) for t, _, _ in tasks(m.stmts) if lit(t.args[1]) == 'CutScene' and lit(t.args[0]) >= 0)
    k = 0
    if cs:
        seq = {lit(t.args[0]): t for t, _, _ in tasks(m.stmts) if lit(t.args[1]) == 'SequenceCommand'}
        for t in list(seq.values()):
            if str(lit(t.args[4])) == 'SoundGenerator_PlaySound("ss_hall_siren")':
                on = '(%s) && !(%s)' % (lit(t.args[3]), cs)
                t.args[3] = v(on); t.args[5] = v(on)
                off = seq[int(str(lit(t.args[6])).split('(')[1].rstrip(')'))]
                o2 = '(%s) || (%s)' % (lit(off.args[3]), cs)
                off.args[3] = v(o2); off.args[5] = v(o2); k += 1
    print('sstruck late: impact on %d hit blasts, %d hall sirens stop in cutscenes' % (n, k))


def seated(T, nid, p, g, spot, model, clip, weapon, name):
    """a man on a truck at p (units), yaw g: the originals' EditBoneObj child of the truck"""
    q = rot(p, spot[:3], g)
    return T(nid(), 'EditBoneObj', 'SS truck ' + name, q[0], q[1], q[2], 0.0, 0.0, g + spot[3], True, True, model, True, weapon, '', clip, 1.0, 0.0)


def crew(m, T, nid, truck, p, g, skins, rule_ride, rule_climb=None, actor_driver=True):
    """the driver stays at the wheel; the men sit in the back (under the canvas) while rule_ride holds, then the AI squad takes over at the tailgate.
    (owner 102, 11-08: the climb-out actors looped their 1.6 s clip twice - the window ran on level ticks - and an EditBoneObj cannot be hit, so men
    jumping down could not be killed. No scripted climb any more: the men are real soldiers from the moment anyone can see them.)"""
    nid = lambda: -1                                       # (id -1: nothing names them, the id ranges are full)
    if actor_driver:                                       # (owner 118: the builder seats a real soldier instead, killable in the cab)
        m.add_child(truck, seated(T, nid, p, g, DRIVER, skins[0], 'priboy_driving_truck', '', 'driver'))
    ride = [seated(T, nid, p, g, s_, skins[k_ % len(skins)], 'guard_in_back_of_truck', '107_01_1', 'rider %d' % k_) for k_, s_ in enumerate(RIDERS)]
    m.add_child(truck, T(nid(), 'ConditionalContainer', 'SS truck riders', rule_ride, '', '', children=ride))


def driver(m, T, truck, p, g, skin, seated_rule, climb_rule):
    """owner G09b 11-13: a driver you can see. The same seat holds, by turns (EditBoneObj children of the truck, so they ride with it):
    seated at the wheel while seated_rule holds; climbing out (guard_get_out_of_truck, once) while climb_rule holds, then the builder's real
    soldier stands at the door. The seated man cannot be shot (an EditBoneObj takes no hits). A seated man cannot be a real soldier: on a moving truck he stands beside the cab (g9dv2, g9dv3)."""
    from mission_lib import v
    nid = lambda: -1
    sit = seated(T, nid, p, g, DRIVER, skin, 'priboy_driving_truck', '', 'driver')
    out = seated(T, nid, p, g, DRIVER, skin, 'guard_get_out_of_truck', '107_01_1', 'driver climbs out'); out.args[9] = v(False)   # (S10 ss-ending 11-15: the clip's weapon attachment is in the right hand; '' = he climbed out holding air for 1.6 s, then the armed soldier appeared. Same AK the real soldier at the door carries)
    m.add_child(truck, T(nid(), 'ConditionalContainer', 'SS truck driver seated', seated_rule, '', '', children=[sit]))
    m.add_child(truck, T(nid(), 'ConditionalContainer', 'SS truck driver climbs out', climb_rule, '', '', children=[out]))


def match_driver_models(m, lit, tasks, squad_ids, truck_keys):
    """judge Q08 11-13: the seated / climbing actor and the real soldier at the door are the same man - dress the actors in the soldier's FINAL
    model (sssoldiers re-dresses the soldiers after the crews are built). truck_keys = {truck id: 'U truck troops N driver'}. Run late."""
    from mission_lib import v
    n = 0
    for truck, key in truck_keys.items():
        if key not in squad_ids:
            continue
        sid, hids = squad_ids[key]
        hid = next((h for h in hids if h in m.byid), None)
        if hid is None:
            continue
        model = lit(m.byid[hid].args[7])
        for t, _, _ in tasks([m.byid[truck]]):
            if lit(t.args[1]) == 'EditBoneObj' and str(lit(t.args[2])).startswith('SS truck driver'):
                t.args[11] = v(model); n += 1
    r = 0                                                  # (judge Q29 11-14: the riders wore the CSFM pool (alplas_1 = the PLA skin, Chinese sleeve flag) and changed look at the
    for truck, key in truck_keys.items():                  #  tailgate: dress rider k as tailgate man k % 2, in his FINAL model, as the drivers above)
        tkey = key[:-len(' driver')] if key.endswith(' driver') else key
        if tkey not in squad_ids:
            continue
        mods = [lit(m.byid[h].args[7]) for h in squad_ids[tkey][1] if h in m.byid]
        if not mods:
            continue
        k = 0
        for t, _, _ in tasks([m.byid[truck]]):
            if lit(t.args[1]) == 'EditBoneObj' and str(lit(t.args[2])).startswith('SS truck rider'):
                t.args[11] = v(mods[k % len(mods)]); k += 1; r += 1
    print('sstruck: %d driver actors dressed as their door soldier, %d riders as their tailgate men' % (n, r))


def glass(T, gid, p, beta, g):
    """the pane set of glass_model() on the truck's start pose, a child of the truck (it rides with it, as the wheels and riders do)"""
    return T(gid, 'EditRigidObj', 'SS truck glass', p[0], p[1], p[2], 0.0, float(beta), float(g), 'ss_trkg_1', 5, False, False)


def rot(p, b, g):
    """a local point (m) on a truck at p (units), yaw g -> world units"""
    c, s = math.cos(g), math.sin(g)
    return (p[0] + (b[0] * c - b[1] * s) * M, p[1] + (b[0] * s + b[1] * c) * M, p[2] + b[2] * M)


BLAST = (5.0, 5.0, 50.0)   # radius, falloff, damage of a truck hit (was 30 / 40 / 50; 2.5 / 3.5 / 50 and 2 / 3 / 20 left Jones alive under the truck, g9h3 g9h5)
OPEN_S = 1.0               # the hit shot opens on a clean picture of the truck reaching Jones this long (judge P1, rc7p2 film: 0.45 s was lost in the chapter fade); the timings below follow it
BLACK_S = 0.7              # the impact cut's black, 0.45-1.15 s of the hit shot: the bumper blast (0.5 s) and the backup (BACKUP_S) burn out inside it (rc7k h06 glare); 1.2 s read as a dropped feed (REVIEW_rc7m #3)
BACKUP_S = OPEN_S + 0.10   # build_sandstorm.py fires the backup 'SS run over' blast this far into the hit shot (was: when the shot ended, in plain view)
HOLD_S = 6.0               # the hit shot holds this long after the fade in: the truck is stopped now, so it watches Jones fall and his body (2.5 s on a moving truck ended on empty floor, REVIEW_rc7m #2);
                           #  6 s covers the engine death camera's settling, which dipped under the tunnel floor into the sand void for ~1 s (rc7n take 3, g9w6b-h)
HALT_S = OPEN_S - 0.25     # each truck stops this far into its hit shot, or when Jones dies: no truck rolls on over the body, under or onto its bonnet, or pushes it
                           #  through the tunnel floor into the sand void (REVIEW_rc7m #1, F07 back; g9j*/g9q1z: every body on the floor in front of the stopped truck)
LEAD_S = OPEN_S - 0.15     # the hit windows open this much earlier: the nose leads the spline point by ~3.4 m, at 46 km/h it scooped Jones onto the bonnet first (g9j3y)


def halt_guides(m, T, nid, cs_of):
    """cs_of = {truck id: its hit CutScene id}: each truck's guide chains a stop after its start (the originals' SequenceCommand chain, L-4/5/6:
    the start command's done '1' -> SequenceCommand_SetCommand(stop); a second SequenceCommand that is never chained never runs)"""
    from qast import tasks, lit
    from mission_lib import v
    n = 0
    for t, _, _ in list(tasks(m.stmts)):
        if lit(t.args[1]) == 'SplinePathGuideQTask' and lit(t.args[4]) in cs_of:
            sc = [c for c in t.args if hasattr(c, 'args') and lit(c.args[1]) == 'SequenceCommand']
            assert len(sc) == 1, 'truck guide %s: %d SequenceCommands' % (lit(t.args[0]), len(sc))
            sid = nid()
            sc[0].args[5] = v('1'); sc[0].args[6] = v('SequenceCommand_SetCommand(%d)' % sid)
            m.add_child(lit(t.args[0]), T(sid, 'SequenceCommand', '', 'HumanPlayer_0.isDead || CutScene_%d.nTick > %.2f * GAME_FREQUENCY' % (cs_of[lit(t.args[4])], HALT_S),
                                          'SplinePathGuide_SetRunning(FALSE)', '1', 'SequenceCommand_SetCommand(-1)'))
            n += 1
    assert n == len(cs_of), 'halt_guides: %d of %d truck guides' % (n, len(cs_of))


def hit_cutscene(m, nid, T, parent, K, truck, start, gamma, trigger, skin):
    """the truck hits Jones: the camera rides beside it, a blast on its bumper kills him in shot. 2.4 s -> dict of ids + 'complete'"""
    cc = nid()
    a_, at_ = rot(start, (-8.0, -2.8, 1.3), gamma), rot(start, (-4.2, 0.0, 0.9), gamma)
    b_, bt_ = rot(start, (-10.0, -1.6, 3.4), gamma), rot(start, (-5.0, 0.0, 0.4), gamma)   # (judge Q18/Q19 11-13: the hold camera high and wide, ahead of the truck: the dismounting men pass under it and Jones's body settles small in a wide frame, g9wa2/g9wb2; was (-6, -2.8, 0.9))
    W_, K_ = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    keys = [dict(CS.key(a_, at_, OPEN_S, False, filt=CS.BAND, noise=0.0, color=W_, shake=0.012), link_id=truck),   # (REVIEW_rc7k fault 4: a fade from the first frame read as ~1 s of near-black; a clean picture, hard cut to black before the 0.5 s blast, g9o1x-o4x) (rc7j: the bumper blast drew a hard-edged bright quad in shot, its fireball
            dict(CS.key(a_, at_, BLACK_S, False, filt=CS.BAND, noise=0.0, color=K_, shake=0.012), link_id=truck),   #  clipped by the tunnel; 0 fireballs = no damage (g9f1/f4), behind the cab it
            dict(CS.key(b_, bt_, 0.4, True, filt=CS.BAND, noise=0.0, color=K_, shake=0.02), link_id=truck, target_id=0),   #  misses at full speed (g9k1x). Impact cut instead: 0.4 s in,
            dict(CS.key(b_, bt_, HOLD_S, False, filt=CS.BAND, noise=0.0, color=W_, shake=0.02), link_id=truck, target_id=0),   #  black over the blast 0.4-1.2 s, fade in. g9b1x-b4x)
            dict(CS.key(b_, bt_, 0.0, False, filt=CS.BAND, noise=0.0, color=W_, shake=0.02), link_id=truck, target_id=0)]   # (judge F07: after 2.4 s the death camera rose through the tunnel roof onto the desert; the shot holds on Jones's body instead)
    # (judge Q20 11-13: noise 0 = no 'CAMERA n' caption; it is not a real camera, and the engine's counter read CAMERA 1 on both trucks)
    D = CS.add_outro(m, nid, parent, keys, [], trigger)
    m.set(D['outro'], 3, str(m.arg(D['outro'], 3)).replace(' && !HumanPlayer_0.isDead', ''))   # (judge F06: the blast kills him at 0.5 s and the isDead clause cut the shot to the death camera; he dies in shot now)
    p = rot(start, (-3.0, 0.0, 1.0), gamma)                # (judge F07: at -4.4, 1 m ahead of the nose, it blew a man standing at the nose back under the truck, which parked on him and pushed the body through the floor, z -1300 m in g9j1. Behind the nose it throws him ahead.) (gk2: Jones himself stands there in the cutscene, an actor doubled him; the hit is a blast on the bumper, his own death animation, in shot)
    m.add_child(truck, T(cc, 'ExplodeObject', 'SS truck bumper', p[0], p[1], p[2], 0.0, 0.0, 0.0, 'none', 'none', 100.0, BLAST[0], BLAST[1], BLAST[2], 0.0, 1, 1, 'CutScene_%d.nTick > %.2f * GAME_FREQUENCY' % (D['cs'], OPEN_S + 0.05), ''))
    return D
