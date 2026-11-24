"""rail - the native IGI 2 railway of Mission 12 'Deep in the Mines' (location1/level2), as a library for spkit missions.

How the original works (work/inv/train/report.md, decompiled work/decomp/location1_level2_objects.qsc):
  * ONE SplineObj ('The ride', L12 4084) is both the track geometry and the rail the trains run on: every
    SplineObjWaypoint names the 'Segment Model' that is deformed along the spline from it to the next waypoint
    (417_01_1 = straight double track 38.4 m, 418_01_1 tunnel end, 410_11_1 rock tunnel).
  * a Train task (Position = distance along the spline in units, Model, Acceleration, MaxSpeed, Flip Direction,
    Displacement X = which of the two tracks, Displacement Z = rail height) - its child Train tasks with Position 0 are
    the coupled wagons; any other child (EditRigidObj, Switch, AIGraph + AISquad) rides along.
  * an AnimTask (TargetID = the train) is the throttle: AnimData = 2 * nkeys, then per key (0, thrust, 32, ticks);
    thrust -1 = leave the throttle as it is. Run expression starts it (L12: the 'Go go go !' Switch -> EditVariable).
  * soldiers ON a train: AISquad AIType_OnVehicle, child of the train, with its own AIGraph (Relative TRUE, last arg
    TRUE) of 2 nodes in the vehicle's own frame (x across, y along, z up; 0.88 m = the loco floor), criteria
    NODECRITERIA_VEHICLE.
Everything here copies those values; what had to be measured in game is marked CALIBRATED.
"""
import math, os
import numpy as np
from igiqvm import Call, Int, Flt, Str, Ident
from mission_lib import T, v, GAME
from qast import load, lit, tasks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L12 = os.path.join(ROOT, 'work', 'decomp', 'location1_level2_objects.qsc')
L12_DIR = os.path.join(GAME, 'MISSIONS', 'location1', 'level2')
M = 4096.0
TRACK = '417_01_1'                   # straight double track, 38.38 m long (collision x -21.2 .. 17.18)
PORTAL = '418_01_1'                  # tunnel end piece (with a lamp)
TUNNEL = '410_11_1'                  # rock tunnel piece
SEG_M = 38.38
LOCO, WAGON = '603_08_1', '603_09_1'
MODELS = [TRACK, PORTAL, TUNNEL, LOCO, WAGON, '201_02_1', '201_01_1']
PLAYER_X = -2.166667                 # 'Displacement X' of Mission 12's train (track A)
OTHER_X = 1.25                       # the other track: Mission 12's enemy train used -1.25 with Flip TRUE
DISP_Z = 0.166667                    # 'Displacement Z' (both trains)
LAT_SIGN = 1.0                       # CALIBRATED: +1 = positive Displacement X is to the RIGHT of the travel direction
CAR_PITCH_M = {LOCO: 10.0, WAGON: 10.84}   # CALIBRATED: spacing of coupled cars along the spline (collision lengths)
# Mission 12's 'Go go go !' button relative to its loco (3989 at 22.9 m along 'The ride'): 3.28 m ahead, 0.53 m
# right, 2.19 m above the rail line, facing backwards (the driver stands behind it)
GO_OFFSET_M = (3.28, 0.53, 2.19)
LOCO_FLOOR_M = 0.88                  # L12 graph3/graph4 nodes stand 0.88 m up in the loco's frame
# CALIBRATED in game 10-11 (work/inv/sirocco/ride1, ride2: checkpoint messages vs screenshot times):
V_PER_THRUST = 51.5                  # steady speed (m/s) per unit of throttle: 0.35 -> 18 m/s, 0.4 -> 20.6 m/s, 0.55 -> ~29
ANIM_HZ = 29.3                       # AnimTask nTick per second (= GAME_FREQUENCY ~30: 2400 ticks took 82 s)
DECL_TYPES = ('Train', 'SplineObj', 'SplineObjWaypoint', 'AnimTask', 'Switch', 'Lift', 'Floor', 'AIGraph', 'AISquad',
              'HumanSoldier', 'HumanAI', 'EditVariable', 'EditRigidObj', 'AreaActivate', 'StatusMessage', 'LevelTimer',
              'ConditionalContainer')


def ensure_decls(m, types=DECL_TYPES):
    have = {lit(s.args[0]) for s in m.stmts if isinstance(s, Call) and s.name == 'Task_DeclareParameters'}
    missing = [t for t in types if t not in have]
    if missing:
        got = m.import_decls(L12, missing)
        assert sorted(got) == sorted(missing), (missing, got)
    return missing


def _num(x):
    """AnimData literal: integral values as ints (L12 writes 0 / -1 / 32 as ints), the rest as floats"""
    return int(x) if float(x) == int(x) else float(x)


# ------------------------------------------------------------------------------------------------ geometry
class Line:
    """a level railway centre line: control points (metres) -> a smooth curve (centripetal Catmull-Rom), the
    SplineObj waypoints every SEG_M metres along it, and a frame for anything that rides on it."""

    def __init__(self, ctrl_m, z_m, seg_m=SEG_M, step_m=0.25):
        C = np.asarray(ctrl_m, float)
        pts = [C[0]]
        P = np.vstack([C[0] - (C[1] - C[0]), C, C[-1] + (C[-1] - C[-2])])
        for i in range(1, len(P) - 2):
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            n = max(4, int(np.linalg.norm(p2 - p1) / step_m))
            t0 = 0.0
            t1 = t0 + np.linalg.norm(p1 - p0) ** 0.5
            t2 = t1 + np.linalg.norm(p2 - p1) ** 0.5
            t3 = t2 + np.linalg.norm(p3 - p2) ** 0.5
            for t in np.linspace(t1, t2, n + 1)[1:]:
                a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
                a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
                a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
                b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
                b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
                pts.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
        D = np.array(pts)                                    # dense curve, metres
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(D, axis=0), axis=1))])
        self.D, self.Ds, self.z = D, s, float(z_m)
        self.length = float(s[-1])
        n = int(self.length // seg_m)
        self.S = np.arange(n + 1) * seg_m                    # waypoint arc positions (m)
        self.seg_m = seg_m

    def xy(self, s_m):
        s_m = np.clip(s_m, 0.0, self.length)
        return np.array([np.interp(s_m, self.Ds, self.D[:, 0]), np.interp(s_m, self.Ds, self.D[:, 1])])

    def heading(self, s_m, ds=1.0):
        """direction of travel (radians, atan2(dy, dx): 0 = east) at arc position s_m"""
        a, b = self.xy(max(0.0, s_m - ds)), self.xy(min(self.length, s_m + ds))
        return math.atan2(b[1] - a[1], b[0] - a[0])

    def gamma(self, s_m):
        """the same direction as an IGI yaw (HumanPlayer / EditRigidObj convention: 0 = +y north, pi/2 = -x west)"""
        a = self.heading(s_m)
        return math.atan2(-math.cos(a), math.sin(a))

    def point(self, s_m, lateral_m=0.0, up_m=0.0):
        """world point (units): on the centre line at s_m, lateral_m to the RIGHT of travel, up_m above the rail line"""
        p = self.xy(s_m)
        a = self.heading(s_m)
        r = np.array([math.sin(a), -math.cos(a)])
        q = p + r * lateral_m
        return (float(q[0] * M), float(q[1] * M), float((self.z + up_m) * M))

    def on_track(self, s_m, disp_x, fwd_m=0.0, side_m=0.0, up_m=0.0, flip=False):
        """a point on a train standing at s_m on the track 'Displacement X' = disp_x: fwd_m along its travel,
        side_m to its right, up_m above the rail line"""
        lat = LAT_SIGN * (-disp_x if flip else disp_x)
        return self.point(s_m + (-fwd_m if flip else fwd_m), lat + (-side_m if flip else side_m), up_m)

    def nearest_s(self, x, y):
        """arc position of the centre-line point nearest to world (x, y) units"""
        d = np.hypot(self.D[:, 0] - x / M, self.D[:, 1] - y / M)
        return float(self.Ds[int(np.argmin(d))])

    def dist(self, x, y):
        d = np.hypot(self.D[:, 0] - x / M, self.D[:, 1] - y / M)
        return float(d.min())

    def waypoints(self):
        """[(x, y, z) units, waypoint gamma (atan2 convention, 0..2pi like L12)]"""
        out = []
        for k, s in enumerate(self.S):
            p = self.xy(s)
            prv, nxt = self.xy(max(0.0, s - self.seg_m)), self.xy(min(self.length, s + self.seg_m))
            g = math.atan2(nxt[1] - prv[1], nxt[0] - prv[0]) % (2 * math.pi)
            out.append(((float(p[0] * M), float(p[1] * M), float(self.z * M)), g))
        return out


# ------------------------------------------------------------------------------------------------ tasks
def spline_task(nid, line, name, models=None):
    """the SplineObj (L12 4084 values) with one waypoint per line.S; models = list of segment models (one per
    waypoint) or None = straight track everywhere -> (spline id, task)"""
    wps = line.waypoints()
    if models is None:
        models = [TRACK] * len(wps)
    assert len(models) == len(wps), (len(models), len(wps))
    kids = []
    for (p, g), mdl in zip(wps, models):
        kids.append(T(nid(), 'SplineObjWaypoint', '', 0, 0, round(g, 6), *p, 'ai-arrow', mdl, 20, False, False, False))
    sid = nid()
    return sid, T(sid, 'SplineObj', name, False, False, False, True, 20, 0, 0, 0, 0, 3.141593, children=kids)


def train(nid, spline_id, s_m, cars, disp_x, flip=False, sound='', name='train', accel=0.05, vmax=200.0,
          lead_kids=(), car_kids=None):
    """a train: cars = [(model, flip)] lead first (L12 player train: loco FALSE + two wagons TRUE).
    lead_kids = extra children of the lead vehicle (Switch, AIGraph + AISquad ...), car_kids = {car index: [tasks]}
    -> (lead id, [ids of every car, lead first], task)"""
    car_kids = car_kids or {}
    lead = nid()
    ids = [lead]
    wag = []
    for k, (mdl, fl) in enumerate(cars[1:], 1):
        i = nid(); ids.append(i)
        wag.append(T(i, 'Train', 'Wagon', 0, 0, spline_id, mdl, accel, vmax, bool(fl), float(disp_x), DISP_Z, sound,
                     children=list(car_kids.get(k, ()))))
    t = T(lead, 'Train', name, float(s_m * M), 0, spline_id, cars[0][0], accel, vmax, bool(flip), float(disp_x), DISP_Z,
          sound, children=wag + list(lead_kids) + list(car_kids.get(0, ())))
    return lead, ids, t


def car_offsets(cars):
    """distance (m) of every car's centre behind the lead car's position (CALIBRATED pitch)"""
    out, d = [0.0], 0.0
    for k in range(1, len(cars)):
        d += 0.5 * (CAR_PITCH_M[cars[k - 1][0]] + CAR_PITCH_M[cars[k][0]])
        out.append(d)
    return out


def throttle(nid, train_id, pos, gamma, run, keys, initial=False, name='throttle'):
    """AnimTask driving train_id: keys = [(thrust, ticks)], thrust -1 = keep the current throttle"""
    data = [2 * len(keys)]
    for th, tk in keys:
        data += [0, _num(th), 32, float(tk)]
    i = nid()
    return i, T(i, 'AnimTask', name, *[float(c) for c in pos], 0, 0, float(gamma), int(train_id), run, bool(initial), *data)


def keys_total(keys):
    return sum(float(tk) for th, tk in keys)


def simulate(keys, s0_m, t_end_s, dt=0.05, start_s=0.0):
    """predicted arc position over time for a throttle script that starts at start_s seconds (the speed follows the
    throttle within ~1-2 s in game: modelled as instant) -> function t -> s (metres)"""
    ev, t = [], start_s
    for th, tk in keys:
        if th != -1:
            ev.append((t, float(th)))
        t += float(tk) / ANIM_HZ
    ts_ = np.arange(0.0, t_end_s + dt, dt)
    s, thr, out = s0_m, 0.0, []
    for t_ in ts_:
        for te, th in ev:
            if abs(te - t_) < dt / 2 or (te <= t_ < te + dt):
                thr = th
        s += thr * V_PER_THRUST * dt
        out.append(s)
    out = np.array(out)
    return lambda t_: float(np.interp(t_, ts_, out))


def switch(nid, pos, gamma, active, name, sound='button_1', on='201_02_1', off='201_01_1',
           sprite='STATUSSCREEN:action_pressbutton.spr'):
    """a push button (L12 163 'Go go go !' values)"""
    i = nid()
    return i, T(i, 'Switch', name, *[float(c) for c in pos], 0.0, 0.0, float(gamma), active, False, sound, on, on, off, off,
                off, False, sprite)


def vehicle_graph(m, gid, nodes_local_m, name='+'):
    """an AIGraph that rides on a vehicle (child of a Train): nodes in the vehicle frame (metres; x across, y along,
    z up) linked in a chain. L12 graph3/graph4 values (material 6, light 0.42, criteria NODECRITERIA_VEHICLE)."""
    import graph as G
    assert gid not in m.byid, 'graph id %d is a task id' % gid
    nodes = [dict(id=k + 1, pos=tuple(float(c) * M for c in p), material=6, light=0.42, terrain=0, crit='NODECRITERIA_VEHICLE',
                  f7e9c=0.0, f143023=0.5) for k, p in enumerate(nodes_local_m)]
    edges = [(k + 2, k + 1) for k in range(len(nodes) - 1)]
    data, ne, mx = G.write(nodes, edges, max_nodes=100)
    m.graphs[gid] = (data, None)
    return T(gid, 'AIGraph', name, 0, 0, 0, True, False, len(nodes), 100, ne, 1, 2, 3, 0.3, 1, 30, False, 0.05, True)


def l12_ai(kind):
    """AI scripts of Mission 12's train riders: 'soldier' (518.qvm: default handler + view 270 deg / 50 m) or 'squad'"""
    f = {'soldier': '518.qvm', 'squad': 'Squad_307.qvm'}[kind]
    return open(os.path.join(L12_DIR, 'ai', f), 'rb').read()


def vehicle_squad(m, name, gid, members, weapons_fn=None):
    """AIType_OnVehicle squad (a child of the train vehicle that carries graph gid). members = [dict(pos=(x,y,z)
    units, gamma, skin, weapons=[...], ai_type)] -> (squad id, [soldier ids], task)"""
    sid = m.new_id(1100, 2600)
    kids, hids = [], []
    for mem in members:
        hid, aid = m.new_id(1100, 2600), m.new_id(1100, 2600)
        wp = ',\n'.join('Human_AddWeapon("WEAPON_ID_%s")' % w for w in mem['weapons']) + ';'
        kids.append(T(hid, 'HumanSoldier', mem.get('name', ''), *[float(c) for c in mem['pos']], float(mem.get('gamma', 0.0)),
                      mem['skin'], 1, wp, 1, -1,
                      children=[T(aid, 'HumanAI', '', mem['ai_type'], 'HUMANAI_ANIMTYPE_SOLDIER_RIFLE', gid)]))
        m.ai_files[str(aid)] = mem.get('ai') or l12_ai('soldier')
        hids.append(hid)
    t = T(sid, 'AISquad', name, 2, Ident('AIType_OnVehicle'), -1, -1, -1, 30, 5, 60, children=kids)
    m.ai_files['Squad_%d' % sid] = l12_ai('squad')
    return sid, hids, t
