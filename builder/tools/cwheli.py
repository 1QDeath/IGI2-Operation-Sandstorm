"""cwheli - Operation Crosswind's IGI gunship with Jones on the door gun (S2, 10-25).

The original 'helicopter assault' is Mission 25 (location2/LEVEL5, igi2-originals howto 4):
  * StationaryGun 4021 (holder 112_02_1, M2HB, up 10 / down -70 / sideways 75, ammo 2000) is a CHILD of the flying
    helicopter 151, at its right door, facing out (gun gamma = heli gamma - pi/2);
  * a SequenceCommand under HumanPlayer: 'HumanPlayer_Activate(4021), HumanPlayer_LockActivate(TRUE)' at start,
    'HumanPlayer_LockActivate(FALSE)' once the 'heli landed' zone flag is set;
  * the player starts 0.58 m inboard of the gun, 0.22 m aft, 1.0 m below its pivot (measured from L25: heli 151,
    gun 4021, HumanPlayer 0, in the heli frame).
Here the aircraft is the friendly Huey 710_01_1 (the Sirocco gunship), whose right cabin door cine.py measured
(DOOR_IN: the door soldier's feet at (1.15, 0.60, -1.10) m in the heli frame). Flights = Mission 16's two guides on
one aircraft (cine.Cine.spline), the pilot = cine.Cine.pilot ('fly_chopper', visible in the cockpit).

    G = cwheli.Gunship(K, C, origin, yaw)              # C = cine.Cine; origin = the heli task position (units)
    tasks_a, secs_a = G.path('path A', pts, speeds, yaws, start_expr, hover=True)
    G.mount(unlock_expr, disarm_expr)                  # the HumanPlayer commands (L25 3771/3770 + L26 disarm)
    K.player(G.player_start(), G.player_gamma(), ...)  # BEFORE mount(): Jones stands behind the gun
"""
import math
import numpy as np
from mission_lib import T, v
from qast import tasks, lit

M = 4096.0
FLOOR_Z = -1.10                                   # cabin floor in the heli frame (cine DOOR_IN z)
GUN_LOCAL = (1.25, 0.60, FLOOR_Z + 1.0)           # the M2HB pivot in the right-hand door (x right, y forward, z up)
PLAYER_LOCAL = (GUN_LOCAL[0] - 0.58, GUN_LOCAL[1] - 0.22, FLOOR_Z)   # (L25 offsets, gun frame -> heli frame)
GUN_LIMITS = (10, -70, 75, 2000)                  # up, down, sideways, ammo (L25 4021)
# the M2HB barrel lies along the gun's local +y like a soldier's face (in game 10-25: gamma = heli gamma pointed it at the
# cockpit, testB3 t00; + pi aft, testB2 t00; - pi/2 = L25 4021's own value out of the right door, testB a_fly03)
GUN_YAW = -math.pi / 2
L25_SRC = 'location2_LEVEL5'


def R(yaw):
    c_, s_ = math.cos(yaw), math.sin(yaw)
    return np.array([[c_, -s_, 0.0], [s_, c_, 0.0], [0.0, 0.0, 1.0]])


def loc(origin, yaw, local_m):
    return tuple(float(c) for c in (np.asarray(origin, float) + R(yaw) @ (np.asarray(local_m, float) * M)))


def heading_yaw(a, b):
    """the yaw whose nose (local +y) points from a to b"""
    return float(math.atan2(-(b[0] - a[0]), b[1] - a[1]))


class Gunship:
    def __init__(self, K, C, origin, yaw, name='gunship', pilot='igiagent2_1', gun=True):
        self.K, self.C, self.m = K, C, K.m
        self.origin, self.yaw = tuple(float(c) for c in origin), float(yaw)
        self.m.import_decls(_decomp(), ['StationaryGun'])
        self.id = K.nid()
        kids = [T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_04_1', 0),
                T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_05_1', 0),
                C.pilot(self.origin, self.yaw, pilot, name='%s pilot' % name)]
        self.gun = None
        if gun:
            self.gun = K.nid()
            up_, down_, side_, ammo_ = GUN_LIMITS
            kids.append(T(self.gun, 'StationaryGun', '%s %s door gun' % (K.PFX, name), *loc(self.origin, self.yaw, GUN_LOCAL),
                          0.0, 0.0, float(self.yaw + GUN_YAW), '112_02_1', 'WEAPON_ID_M2HB', up_, down_, side_, ammo_))
        self.kids = kids
        self.task = T(self.id, 'EditRigidObj', '%s %s' % (K.PFX, name), *self.origin, 0.0, 0.0, self.yaw, '710_01_1', 8, False, False,
                      children=kids)
        self.guides = []
        self.player_local = PLAYER_LOCAL

    def player_start(self):
        return loc(self.origin, self.yaw, self.player_local)

    def player_gamma(self):
        return float(self.yaw - math.pi / 2)              # facing out of the right door, along the gun

    def path(self, name, pts, speeds_kmh, yaws, start_expr, hover=True):
        """a guide flying this helicopter through pts (world units, pts[0] = where it is when the guide starts);
        start_expr starts it; hover=True stops the guide at the last node (Mission 16: SetRunning(FALSE) at the last
        node -> the aircraft hovers there, rotors turning). -> (tasks, seconds, guide id, last node index)"""
        sp, secs = self.C.spline(self.id, [tuple(float(c) for c in p) for p in pts], list(speeds_kmh), list(yaws), free=True,
                                 name='%s %s' % (self.K.PFX, name))
        guide = None
        for t_, d_, p_ in tasks(sp):
            ty_ = lit(t_.args[1])
            if ty_ == 'SplinePathGuideQTask':
                guide = int(lit(t_.args[0]))
                gt = t_
            elif ty_ == 'SequenceCommand':
                t_.args[3] = v(start_expr)
        last = len(pts) - 1
        if hover:
            gt.args.append(T(self.K.nid(), 'SequenceCommand', '', 'SplinePathGuideQTask_%d.vPosition > %.2f' % (guide, last - 0.02),
                             'SplinePathGuide_SetRunning (FALSE);', '', ''))
        self.guides.append(guide)
        return sp, secs, guide, last

    def mount(self, unlock_expr, disarm_expr=None, remount=None, dismount=None):
        """Jones on the gun from his first tick (L25 3771), unlocked by unlock_expr (L25 3770); disarm_expr then takes his
        weapons away (L26 mid-game: HumanPlayer_DisableAllWeapons) - Jones is home and cannot shoot his colleagues.
        remount = (expr, (x, y, z) units of the helicopter's hover point, its yaw): after a mid cutscene that switched the
        player off (Kit's mids) he is put back behind the gun - L26 'snap human player' Human_PopPosition (metres) + Activate.
        dismount = (off_expr or None, expr, (x, y, z) units): instead of disarm_expr - at off_expr HumanPlayer_Activate on the
        gun again (cmp4/cmp5 10-25: it does NOT let go - only the player's own E does; None = leave it to E), at expr his
        weapons go AND he is put down there (beside the door: off the gun the hull and the gun mount box him in the cabin,
        cmp2 10-25); expr should hold while a cutscene runs"""
        K, m = self.K, self.m
        a, r, b, c, o = K.nid(), K.nid(), K.nid(), K.nid(), K.nid()
        first_next = r if remount else b
        cmds = [T(a, 'SequenceCommand', '%s mount the door gun' % K.PFX, '1',
                  'HumanPlayer_Activate(%d), HumanPlayer_LockActivate(TRUE)' % self.gun, '1', 'SequenceCommand_SetCommand(%d)' % first_next)]
        if remount:
            expr, hover, hyaw = remount
            px, py, pz = (c_ / M for c_ in loc(hover, hyaw, self.player_local))
            cmds.append(T(r, 'SequenceCommand', '%s back on the door gun' % K.PFX, expr,
                          'Human_PopPosition(0, %.4f, %.4f, %.4f), HumanPlayer_Activate(%d), HumanPlayer_LockActivate(TRUE)'
                          % (px, py, pz + 0.05, self.gun), '1', 'SequenceCommand_SetCommand(%d)' % b))
        # (with dismount: the weapons go at the unlock too - note 10-25, walkgate: a player who jumps out past every box must
        #  still be unarmed at headquarters)
        cmds.append(T(b, 'SequenceCommand', '%s unlock the door gun' % K.PFX, unlock_expr,
                      'HumanPlayer_LockActivate(FALSE)' + (', HumanPlayer_DisableAllWeapons()' if dismount else ''), '1',
                      'SequenceCommand_SetCommand(%d)' % (o if (dismount and dismount[0]) else c if (disarm_expr or dismount) else -1)))
        if dismount:
            oexpr, dexpr, dpos = dismount
            if oexpr:
                cmds.append(T(o, 'SequenceCommand', '%s lets go of the door gun' % K.PFX, oexpr, 'HumanPlayer_Activate(%d)' % self.gun, '1',
                              'SequenceCommand_SetCommand(%d)' % c))
            cmds.append(T(c, 'SequenceCommand', '%s off the gunship' % K.PFX, dexpr,
                          'HumanPlayer_DisableAllWeapons(), Human_PopPosition(0, %.4f, %.4f, %.4f)' % tuple(c_ / M for c_ in dpos),
                          '1', 'SequenceCommand_SetCommand(-1)'))
        elif disarm_expr:
            cmds.append(T(c, 'SequenceCommand', '%s weapons stay in the helicopter' % K.PFX, disarm_expr,
                          'HumanPlayer_DisableAllWeapons()', '1', 'SequenceCommand_SetCommand(-1)'))
        for t_ in cmds:
            m.add_child(0, t_)
        return [t_ for t_ in (a, r if remount else None, b, o if (dismount and dismount[0]) else None, c if (disarm_expr or dismount) else None)
                if t_]


class L25Gunship(Gunship):
    """Mission 25's own player helicopter, cloned 1:1 (note 10-25, owner: the Huey's view from the gun was 'glitchy and
    ghosty' - its cabin is a hollow shell made for outside shots; the original ride is the Kamov 741_01_1, built for it):
    container 4075 'PLAYERS Helicopter' = EditRigidObj 151 (741_01_1, RenderGroup 8) + rotors 4042 (741_03_1) / 3995 (741_02_1)
    + StationaryGun 4021 + pilot 3421 'fly_chopper' + SoundGenerators 3488 'helicopter' / 3318 'wind', every child at L25's own
    offset. Its path 150 / guide 4074 are dropped (our flights are our own guides); the player stands where L25 starts him.
    Needs: X.models('location2/LEVEL5', L25_MODELS) before X.finish, and origsounds.bank('location2/LEVEL5', L25_SOUNDS) in
    K.write's extra_samples."""
    SRC = 'location2/LEVEL5'
    HELI, GUN, PILOT, PATH, GUIDE, CONT, WIND = 151, 4021, 3421, 150, 4074, 4075, 3318
    L25_PLAYER = (-1900694.6, 10674254.0, 155792.64, 2.094395)  # HumanPlayer 0 of L25: position, gamma
    SKIDS_M = -0.87                                          # 741_01_1 bbox z 0.87..6.65: origin 0.87 m below the wheels

    def __init__(self, K, C, origin, yaw, name='gunship', pilot='igiagent2_1'):
        self.K, self.C, self.m = K, C, K.m
        self.origin, self.yaw = tuple(float(c) for c in origin), float(yaw)
        self.m.import_decls(_decomp(), ['StationaryGun', 'SoundGenerator'])
        S = __import__('cine').Source(self.SRC)
        h = S.byid[self.HELI]
        p0 = np.array([float(lit(h.args[3 + k])) for k in range(3)])
        y0 = float(lit(h.args[8]))
        dy = self.yaw - y0
        tasks_, idmap = C.clone(self.SRC, [self.CONT], np.asarray(self.origin, float) - p0, yaw=dy, pivot=p0)
        cont = tasks_[0]
        for c_ in [a_ for a_ in cont.args if isinstance(a_, type(cont)) and lit(a_.args[0]) in (idmap[self.PATH], idmap[self.GUIDE])]:
            cont.args.remove(c_)                              # (the L25 route: ours are our own guides)
        self.id, self.gun, self.pilot = idmap[self.HELI], idmap[self.GUN], idmap[self.PILOT]
        self.wind = idmap[self.WIND]
        self.old_guide = idmap[self.GUIDE]
        for t_, d_, p_ in tasks([cont]):
            i_ = lit(t_.args[0])
            if i_ == self.gun:                                # (clone turns rigid objects / bones / cameras, not guns)
                t_.args[8] = v(float(lit(t_.args[8])) + dy)
            elif i_ == self.pilot and pilot:
                t_.args[11] = v(pilot)                        # (an IGI pilot, not Priboi)
            elif i_ == self.id:
                t_.args[2] = v('%s %s (L25 741)' % (K.PFX, name))
        self.task = cont
        self.guides = []
        R0 = R(-y0)
        pl = np.array(self.L25_PLAYER[:3])
        self.player_local = tuple(float(c_) for c_ in (R0 @ ((pl - p0) / M)))
        self.player_g = float(self.L25_PLAYER[3] - y0)        # (his facing relative to the nose)
        g_ = S.byid[self.GUN]
        self.gun_local = tuple(float(c_) for c_ in (R0 @ ((np.array([float(lit(g_.args[3 + k])) for k in range(3)]) - p0) / M)))

    def player_gamma(self):
        return float(self.yaw + self.player_g)

    def path(self, name, pts, speeds_kmh, yaws, start_expr, hover=True):
        out = Gunship.path(self, name, pts, speeds_kmh, yaws, start_expr, hover)
        if len(self.guides) == 1:                             # (the wind sound follows the first flight, as on L25's guide)
            for t_, d_, p_ in tasks([self.task]):
                for k_, a_ in enumerate(t_.args):
                    if isinstance(lit(a_), str) and 'SplinePathGuideQTask_%d' % self.old_guide in str(lit(a_)):
                        t_.args[k_] = v(str(lit(a_)).replace('SplinePathGuideQTask_%d' % self.old_guide, 'SplinePathGuideQTask_%d' % out[2]))
        return out


L25_MODELS = ['741_01_1', '741_02_1', '741_03_1', '740_04_1', '740_05_1', 'ka27shadow']
L25_SOUNDS = ('helicopter', 'wind')


def _decomp():
    import os
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'decomp', L25_SRC + '_objects.qsc')
