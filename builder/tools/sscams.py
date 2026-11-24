"""sscams - owner item 116 (11-08): cutscene feed cameras and their camera models. Last pass of build_sandstorm.py, no flag (SS_CAMS=0 turns it off).

Measured (work/qa/hands/camaudit.py, work/qa/cams): the map's camera holder 313_07_1 has its wall plate at its origin and an arm to y 0.668; the head 313_06_1
sits on the arm's post, y +-0.352 round it, so the lens front is 1.02 m out from the plate. Six feed shots put the cutscene eye 0.30-0.68 m in front of
their own camera's plate: inside the head. Its faces cut the near plane, and as the shot pans or shakes the head blinks in and out of the picture
(intro and ending office feeds, decrypt lift room and control room, the general's server desk).

hide_in_feeds(): such a camera goes into a ConditionalContainer that is off while the cutscene holding those keys runs: the feed is filmed from where the
camera hangs, and the camera itself is not there to be seen from inside. Every shot keeps its framing (moving the eyes out wrecked the general's close shots
and his zoom on the monitor: reviewer, renders 11-08). In play the camera hangs where it always did and can be shot.
headroom(): cameras with less than HEADROOM under a ceiling (over plate, post or lens) go down to it; mast / rod cameras stay on their mounts.
rc7t (owner 11-13): every camera is on the original game's models (stock_models); one_per_room keeps one camera per room. SS_STOCKCAMS=0 skips both
(it is not a rollback to rc7s3: use that build)."""
import math, os
import numpy as np

ON = os.environ.get('SS_CAMS', '1') == '1'


def _is_mount(md):
    """a camera's mast / rod / arm (ssworld.cameras; indoorize renames the rods and arms wissw_*: review rc7s #1, the console and hall rods were left)"""
    return str(md).lower() in ('ss_pole_1', 'ssw_rod_1', 'ssw_arm_1', 'wissw_rod_1', 'wissw_arm_1')
HEAD = 1.06                                                # an eye nearer the plate than this is inside the head (lens front 1.02 m)
M = 4096.0


def _head_keys(m, lit):
    """{camera id: (name, [EditCamera ids whose eye is in its head zone])}: 0..HEAD m in front of the plate, within 0.5 m of its axis, -0.8..0.8 m up"""
    cams = []
    for i in m.find('SCamera'):
        p = np.array([float(lit(m.byid[i].args[k])) for k in (3, 4, 5)]) / M
        g = float(lit(m.byid[i].args[6]))
        cams.append((i, str(lit(m.byid[i].args[2])), p, np.array([-math.sin(g), math.cos(g), 0.0])))
    out = {}
    for e in m.find('EditCamera'):
        a = m.byid[e].args
        try:
            q = np.array([float(lit(a[k])) for k in (3, 4, 5)]) / M
        except Exception:
            continue
        for i, nm, p, f in cams:
            d = q - p
            lf = float(d @ f)
            lat = float(np.hypot(*(d[:2] - f[:2] * lf)))
            if 0.0 <= lf < HEAD and lat < 0.5 and -0.8 < d[2] < 0.8:
                out.setdefault(i, (nm, []))[1].append(e)
    return out


def _holder(m, lit, tid):
    """the ConditionalContainer a task lives in (its cutscene's container)"""
    t = m.parent.get(tid)
    while t is not None:
        if str(lit(t.args[1])) == 'ConditionalContainer':
            return int(lit(t.args[0]))
        t = m.parent.get(int(lit(t.args[0])))
    return None


def _windows(m, lit, keys):
    """[(CutScene id, container id, t0, t1)] when those keys are on screen: a key holds for its Duration, a smooth key moves on into the next one"""
    out = []
    for e in keys:
        cs = m.parent.get(e)
        if cs is None or str(lit(cs.args[1])) != 'CutScene':
            continue
        cams = [c for c in cs.args if hasattr(c, 'args') and getattr(c, 'name', '') == 'Task_New' and str(lit(c.args[1])) == 'EditCamera']
        t = 0.0
        for k, c in enumerate(cams):
            dur = float(lit(c.args[10]))
            if int(lit(c.args[0])) == e:
                end = t + dur + (float(lit(cams[k + 1].args[10])) if str(lit(c.args[15])).upper() == 'TRUE' and k + 1 < len(cams) else 0.0)
                out.append((int(lit(cs.args[0])), _holder(m, lit, e), max(0.0, t - 0.2), end + 0.2))
                break
            t += dur
    return out


RULE_MAX = 1023                                            # the engine cuts a ConditionalContainer rule at 1023 chars (tools/qa.py exprs)


def _merge(win):
    """one window per stretch of a cutscene: overlapping or touching windows (same CutScene and container) joined, sorted by cutscene and time"""
    out = []
    for cs, cc, a, b in sorted(win):
        if out and out[-1][0] == cs and out[-1][1] == cc and a <= out[-1][3] + 0.05:
            out[-1] = (cs, cc, out[-1][2], max(out[-1][3], b))
        else:
            out.append((cs, cc, a, b))
    return out


def _rule(win):
    """the 'feed on screen' expression, the container's isRun said once per cutscene"""
    by = {}
    for cs, cc, a, b in win:
        by.setdefault((cs, cc), []).append((a, b))
    parts = []
    for (cs, cc), ab in by.items():
        t = ' || '.join('(CutScene_%d.nTick >= %.2f * GAME_FREQUENCY && CutScene_%d.nTick < %.2f * GAME_FREQUENCY)' % (cs, a, cs, b) for a, b in ab)
        parts.append('(ConditionalContainer_%d.isRun && %s)' % (cc, t if len(ab) == 1 else '(%s)' % t))
    return ' || '.join(parts)


NEAR_USE = 3.6                                             # m from where Jones stands at a use point (point + 0.85 m along its +y)
USE_DZ = 3.0                                               # m up or down from the use point


def _mast_xy(m, lit):
    return [np.array([float(lit(m.byid[r].args[3])), float(lit(m.byid[r].args[4]))]) for r in m.find('EditRigidObj')
            if _is_mount(lit(m.byid[r].args[9]))]


def _near_uses(m, lit):
    """{camera id: [GenericTBA ids]}: wall / ceiling cameras within NEAR_USE of Jones's stand at a use point. The E use view circles him at
    about 2 m and ceiling height (rig cams_e7m, rc7m server room): such a camera slides in and out at the top of the picture as the view turns
    (owner 116, 11-10: 'looking left and right makes the camera model appear and disappear'). Mast cameras stay: a bare mast would show."""
    masts = _mast_xy(m, lit)
    uses = []
    for u in m.find('GenericTBA'):
        a = m.byid[u].args
        try:
            p = np.array([float(lit(a[k])) for k in (3, 4, 5)]) / M; g = float(lit(a[8]))
        except Exception:
            continue
        uses.append((u, p + np.array([-math.sin(g), math.cos(g), 0.0]) * 0.85))
    out = {}
    for i in m.find('SCamera'):
        c = np.array([float(lit(m.byid[i].args[k])) for k in (3, 4, 5)])
        if str(lit(m.byid[i].args[20])) != '0':                    # (review 116 11-10: an alarm camera never goes blind while E is held)
            continue
        if any(np.hypot(c[0] - q[0], c[1] - q[1]) < 0.3 * M for q in masts):
            continue
        c = c / M
        for u, s in uses:
            if np.hypot(*(c[:2] - s[:2])) < NEAR_USE and abs(c[2] - s[2]) < USE_DZ:
                out.setdefault(i, []).append(u)
    return out


def hide_in_feeds(G):
    """each camera with its eye in a feed shot (off during those seconds) or hanging over a use point (off while it is in use) goes into one
    ConditionalContainer that is off at those times; in play it hangs where it always did and can be shot"""
    from qast import lit
    m, T, nid = G['m'], G['T'], G['nid']
    feeds = {}
    for i, (nm, keys) in sorted(_head_keys(m, lit).items()):
        win = [w for w in _windows(m, lit, keys) if w[1] is not None]
        if not win:
            print('sscams: camera %d %r: %d keys in its head, no cutscene window found: left' % (i, nm, len(keys))); continue
        feeds[i] = _merge(win)
    uses = _near_uses(m, lit)
    out = []
    for i in sorted(set(feeds) | set(uses)):
        nm = str(lit(m.byid[i].args[2]))
        par = m.parent.get(i)
        if par is None:
            continue
        win, us = feeds.get(i, []), uses.get(i, [])
        on = ' || '.join(([_rule(win)] if win else []) + ['GenericTBA_%d.isInUse' % u for u in us])
        if len(on) + 3 >= RULE_MAX:                                # (rc7h qa exprs: 13 overlapping windows made a 1741-char rule; the engine cuts rules at 1023)
            raise SystemExit('sscams: camera %d %r: rule of %d chars over the engine cap %d' % (i, nm, len(on) + 3, RULE_MAX))
        box = nid()                                                # (before the remove: after it nid() handed back the camera's own id, container and camera shared it, rc7m 417/878)
        assert box != i
        task = m.byid[i]
        m.remove(i)
        m.add_child(int(lit(par.args[0])), T(box, 'ConditionalContainer', 'SS camera %d out of its own feed' % i if win else 'SS camera %d out of the use view' % i,
                                             '!(%s)' % on, '', '', children=[task]))
        out.append((i, nm, [(cs, round(a, 1), round(b, 1)) for cs, cc, a, b in win], us))
    for i, nm, w, us in out:
        print('sscams: camera %d %r gone while its own feed is on screen %s / while use points %s are in use' % (i, nm, w, us))
    print('sscams: %d cameras out of their own feeds, %d out of use views' % (sum(1 for o in out if o[2]), sum(1 for o in out if o[3])))
    return out


def ray(T, o, d, maxd, normal=False):
    """nearest hit of ray o + s d (unit d) into triangles T (n,3,3), same units; None when nothing within maxd. normal=True: (t, |normal z|) of the hit face"""
    lo = np.minimum(o, o + d * maxd) - 1.0; hi = np.maximum(o, o + d * maxd) + 1.0
    T = T[(T.max(1) >= lo).all(1) & (T.min(1) <= hi).all(1)]
    if not len(T):
        return None
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    p = np.cross(d, e2); det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
    tv = o - T[:, 0]
    u = (tv * p).sum(1) * inv; q = np.cross(tv, e1); v = (q * d).sum(1) * inv; t = (e2 * q).sum(1) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0) & (t < maxd)
    if not hit.any():
        return None
    k = int(np.argmin(np.where(hit, t, np.inf)))
    if not normal:
        return float(t[k])
    n = np.cross(e1[k], e2[k])
    return float(t[k]), float(abs(n[2]) / max(np.linalg.norm(n), 1e-12))


def wall_plate(tris, eye_u, back_u, max_m=2.5):
    """a wall camera's plate ON the wall behind its eye (cam_obj put it 0.35 m back, in the air when the wall was farther: the control room one hung 0.15 m off it).
    -> the plate position (units), or back_u when no wall is found"""
    o = np.array(eye_u, float); b = np.array(back_u, float)
    d = b - o; d[2] = 0.0
    n = np.linalg.norm(d)
    if n < 1e-6:
        return back_u
    d /= n
    h = ray(np.asarray(tris, float), o, d, max_m * M)
    if h is None or not 0.3 * M <= h <= 0.95 * M:                 # (review 116 #5: a far wall left the eye floating where no camera could be; such a shot keeps cam_obj's 0.35 m)
        print('sscams: wall %s behind the eye at %s: plate left at 0.35 m' % ('none' if h is None else '%.2f m' % (h / M), [round(c / M, 2) for c in eye_u]))
        return back_u
    w = o + d * (h - 0.005 * M)
    return (float(w[0]), float(w[1]), float(b[2]))


HEADROOM = 0.36                                            # m from a camera's origin to the ceiling over it: the holder rises 0.206 m, the 0.2 rad tilt lifts its back corner more


def headroom(G, room_m=None, probe=(0.0, 0.67, 1.0), soft=None):
    """cameras hung 0.12-0.17 m under a ceiling poked through it in play (server room, rig cams_rc look4): each one with less than HEADROOM over it goes down to it.
    soft = (room m, probe m) for cameras on the stock soft holder 335_01_1 (review rc7t #2: the metal 313 arm and head reach 0.67 / 1.0 m, keep their probe)"""
    import atmos
    from qast import lit
    m, K = G['m'], G['K']
    T = K._tris()[0]
    mounts = [np.array([float(lit(m.byid[r].args[3])), float(lit(m.byid[r].args[4]))]) for r in m.find('EditRigidObj')
              if _is_mount(lit(m.byid[r].args[9]))]
    out = []
    for i in m.find('SCamera'):
        p = [float(lit(m.byid[i].args[k])) for k in (3, 4, 5)]
        if any(np.hypot(p[0] - q[0], p[1] - q[1]) < 0.3 * M for q in mounts):   # (review 116 #3: a mast / rod camera stays on its mount)
            continue
        g = float(lit(m.byid[i].args[6]))
        f = (-math.sin(g), math.cos(g))
        rm, pr = (soft if soft and str(lit(m.byid[i].args[7])) == '335_01_1' else (room_m, probe))
        room = []
        for s_ in pr:                                          # (review 116 #4: over the plate, the arm's post and the lens)
            up, dn = atmos._vertical_hits(T, (p[0] + f[0] * s_ * M, p[1] + f[1] * s_ * M, p[2]))
            if up and (not dn or p[2] - dn[0] > 1.0 * M):
                room.append(up[0] - p[2])
        hr = HEADROOM if rm is None else rm
        if room and min(room) < hr * M:
            m.set(i, 5, float(p[2] + min(room) - hr * M))
            out.append((i, str(lit(m.byid[i].args[2])), round(min(room) / M, 2), hr))
    for i, nm, h, hr in out:
        print('sscams: camera %d %r had %.2f m under the ceiling: lowered to %.2f' % (i, nm, h, hr))
    return out


# ------------------------------------------------------------------------------------------------ owner 11-12 (rc7s): one good camera per room
# "the cutscene cameras shouldn't be there at all ... one camera in each room ... it's not looking well". Every cutscene feed is an EditCamera key of its
# own (no SCamera links to it), so a feed camera the room does not need goes, task and mount, and its shots play from an invisible eye. One camera stays
# per room / area (rig groups by line of sight, rc7q), the original alarm cameras all stay. (rc7s drew them with a new model; rc7t: stock_models below.)
STOCKCAMS = os.environ.get('SS_STOCKCAMS', '1') == '1'
REMOVE = ('SS feed camera server corner', 'SS feed camera office', 'SS feed camera office side', 'SS feed camera office west',   # (server room: five -> the desk one)
          'SS feed camera console', 'SS feed camera hall',                  # (control room keeps its own; the hall one sat inside a column, 5 cm of geometry all round)
          'SS feed camera chip', 'SS feed camera chip mast', 'SS feed camera cage', 'SS feed camera gate',   # (missile bay: the silo wall one stays; 'gate' = blast door + main gate)
          'SS feed camera gate 2')                                          # (main gate: the alarm camera 3933 on its mast stands for it)
MOVE = {                                                                     # name: (x, y m where rc7q has it, new x, y, z m) - into a ceiling corner, measured rc7q
    'SS feed camera server desk': (48.04, 239.29, 48.454, 240.395, 8.08),   # (1.18 m north along the west wall, 0.4 m from the north wall, 0.2 m under the ceiling)
    'SS feed camera control room': (256.00, 197.01, 265.60, 197.01, -30.60),   # (9.6 m east along the south wall to the corner)
    'SS feed camera lift room': (158.60, 232.90, 158.60, 232.90, -10.92),   # (already 0.39 m from the corner: up under the ceiling)
}


def one_per_room(G):
    from qast import lit
    m = G['m']
    mounts = [r for r in m.find('EditRigidObj') if _is_mount(lit(m.byid[r].args[9]))]
    gone, moved = [], []
    for i in list(m.find('SCamera')):
        nm = str(lit(m.byid[i].args[2]))
        p = [float(lit(m.byid[i].args[k])) for k in (3, 4, 5)]
        if nm in REMOVE:
            for r in list(mounts):
                q = [float(lit(m.byid[r].args[k])) for k in (3, 4)]
                if math.hypot(q[0] - p[0], q[1] - p[1]) < 0.35 * M:
                    m.remove(r); mounts.remove(r)
            m.remove(i)
            gone.append(nm[15:])
        elif nm in MOVE:
            x0, y0, x, y, z = MOVE[nm]
            if math.hypot(p[0] / M - x0, p[1] / M - y0) > 0.1:
                print('sscams: one_per_room: %r is no longer at %.2f, %.2f: left' % (nm, x0, y0)); continue
            m.set(i, 3, x * M); m.set(i, 4, y * M); m.set(i, 5, z * M)
            moved.append(nm[15:])
    print('sscams: one camera per room: %d feed cameras gone %s, %d into ceiling corners %s, %d cameras left' % (len(gone), gone, len(moved), moved, len(m.find('SCamera'))))
    return gone, moved


MAST_MOVE = {                                                # name: (pole x, y m where it stands, new pole x, y m) - camera and mast together
    'SS feed camera generators': (107.33, 101.94, 105.47, 98.53),   # (G03 fix 2, 11-13: the pole stood in a slope rising 1.5 m a metre, ground 7.4-8.3 at a
                                                                     #  camera 7.1 m up = buried. 2.5 m downhill + 3 m aside: ground 3.65, 3.5 m of mast shows;
                                                                     #  63 deg off its own feed's axis (eye 1 m in front of the old spot), so not in that shot)
    'SS feed camera east block': (160.38, 173.71, 159.38, 177.21),  # (S7 / propaudit look_5 SUNK 701, 11-17: G03 missed it. Camera 2354 (z 6.24) and its
}                                                                    #  mast stood INSIDE a cliff (terrain 10.3 at the camera, falling ~2.5 m a metre to
                                                                     #  +x +y): 0 of 68 mast and 0 of 56 camera vertices over the ground. 1 m west + 3.5 m
                                                                     #  north: ground 2.30, 3.9 m of mast shows, terrain >= 2 m under the camera within
                                                                     #  0.6 m; 68 deg off its feed's axis (forward +0.56 x +0.83 y, eye 1 m in front of the
                                                                     #  old spot); nearest AI node 5.8 m, no object within 3 m. No alarm link (Doors container))


def mast_move(G):
    from qast import lit
    m = G['m']
    out = []
    for i in list(m.find('SCamera')):
        nm = str(lit(m.byid[i].args[2]))
        if nm not in MAST_MOVE:
            continue
        x0, y0, x, y = MAST_MOVE[nm]
        p = [float(lit(m.byid[i].args[k])) for k in (3, 4)]
        poles = [r for r in m.find('EditRigidObj') if _is_mount(lit(m.byid[r].args[9]))
                 and math.hypot(float(lit(m.byid[r].args[3])) / M - x0, float(lit(m.byid[r].args[4])) / M - y0) < 0.1]
        if len(poles) != 1 or math.hypot(p[0] / M - x0, p[1] / M - y0) > 0.35:
            print('sscams: mast_move: %r or its mast is no longer at %.2f, %.2f: left' % (nm, x0, y0)); continue
        d = ((x - x0) * M, (y - y0) * M)
        for t in (i, poles[0]):
            m.set(t, 3, float(lit(m.byid[t].args[3])) + d[0]); m.set(t, 4, float(lit(m.byid[t].args[4])) + d[1])
        out.append(nm[15:])
    print('sscams: masts moved %s' % out)
    return out


# owner 11-13 (G03, "the cameras you added are broken, add real ones"): the rc7s model is gone; every camera is the ORIGINAL game's. Plastic ones the
# stock soft camera of the single-player levels (holder 335_01_1, head 335_02_1, shot -> 335_03_1, damage factor 0.5; cams.SOFT), metal ones the
# stock metal camera (313_07_1 / 313_06_1, factor 50; cams.METAL). All five are already in the level's model set: no LOD slot (lodvir 577 either way).
# Underground a metal one keeps ssgun's darkened copy of the same mesh (ss_cam7_1 / ss_cam6_1): the lightmapped 313 draws white in a dark room (owner 83).
SOFT_PLATE = 0.215                                         # m: 335_01_1's wall plate sits 0.20-0.23 m behind its origin (313_07_1: at it) - forward so it meets the wall


MAST_DROP = 0.03                                           # m: on a pole cap the 335 holder's foot is 0.157 m under its origin, the cap 0.185 m (review rc7t: 2.8 cm gap)


def stock_models(G):
    from qast import lit
    m = G['m']
    gun = getattr(G.get('SB'), 'GUNROOM', True)              # (review rc7t #3: ssgun registers ss_cam7_1 / ss_cam6_1 only with the gun room)
    masts = _mast_xy(m, lit)
    soft, metal, dark = [], [], []
    for i in m.find('SCamera'):
        a = m.byid[i].args
        p = [float(lit(a[k])) for k in (3, 4, 5)]; g = float(lit(a[6]))
        if float(lit(a[21])) < 1.0:
            if str(lit(a[7])) != '335_01_1':                     # (review rc7t #4: the plate shift once only)
                m.set(i, 3, p[0] - math.sin(g) * SOFT_PLATE * M); m.set(i, 4, p[1] + math.cos(g) * SOFT_PLATE * M)
                if any(np.hypot(p[0] - q[0], p[1] - q[1]) < 0.3 * M for q in masts):
                    m.set(i, 5, p[2] - MAST_DROP * M)
            for k, md in ((7, '335_01_1'), (11, '335_02_1'), (12, '335_03_1')):
                m.set(i, k, md)
            soft.append(i)
        elif p[2] < -8.0 * M and gun:
            for k, md in ((7, 'ss_cam7_1'), (11, 'ss_cam6_1'), (12, 'ss_cam6_1')):
                m.set(i, k, md)
            dark.append(i)
        else:
            for k, md in ((7, '313_07_1'), (11, '313_06_1'), (12, '313_06_1')):
                m.set(i, k, md)
            metal.append(i)
    print('sscams: stock cameras: %d soft (335, plate %.3f m forward), %d metal (313), %d metal underground (ssgun dark copy)' % (len(soft), SOFT_PLATE, len(metal), len(dark)))
    return soft, metal, dark


CAM_LOD = {'ss_cam7_1': '313_07_1', 'ss_cam6_1': '313_06_1', '335_01_1': '335_01_1', '335_02_1': '335_02_1', '313_07_1': '313_07_1', '313_06_1': '313_06_1'}   # the dark camera meshes (tools/ssgun.dark_cameras) -> the map camera whose LOD row they take


def lod(G):
    """owner 116 (11-10): every SCamera is on the dark meshes ss_cam7_1 / ss_cam6_1 (ssworld.cameras), and the overlay lod.qvm the builder writes
    (lodfix.build, LOD_QVM) had no row for them (ssgun's wreck._lod_entry row is overwritten by it; qa WARN 'no lod.qvm entry'). A model
    without a row is drawn to ~10 x its radius: ~4.5 m for a camera. Rig cmo / cmu (rc7m): bare masts, an empty rod in the hall, and the
    server room cameras popping in and out as the E use view circles. Each gets the row of the map camera it was copied from."""
    import igiqvm, lodfix
    from igiqvm import Call, Int, Flt, Str
    data = G.get('LOD_QVM')
    if not data:
        print('sscams: lod: no LOD_QVM in the builder: left'); return []
    ver, st = igiqvm.decompile(data)
    have = {}
    for c in st:
        if isinstance(c, Call) and c.name == 'Task_New' and str(c.args[1]) == 'ModelLODSettings':
            have.setdefault(str(c.args[3]).lower(), [float(lodfix.lit(x)) for x in c.args[4:9]])
    gl = lodfix.read(os.path.join(lodfix.GAME, 'lod.qvm'))[2]
    out = []
    for dst, src in CAM_LOD.items():
        if dst in have:
            continue
        v = have.get(src) or gl.get(src)
        if v is None:
            raise SystemExit('sscams: lod: no LOD row for %s to copy to %s' % (src, dst))
        st = list(st) + [Call('Task_New', [Int(-1), Str('ModelLODSettings'), Str(dst), Str(dst)] + [Flt(x) for x in v])]
        out.append((dst, v))
    if out:
        data = igiqvm.compile_stmts(st, ver)
        v2, st2 = igiqvm.decompile(data)
        got = {str(c.args[3]).lower() for c in st2 if isinstance(c, Call) and c.name == 'Task_New' and str(c.args[1]) == 'ModelLODSettings'}
        assert all(d in got for d, v in out), out
        G['LOD_QVM'] = data
    print('sscams: lod rows for the camera meshes: %s' % (out or 'already there'))
    return out


SPREAD = 1.3                                               # m between two cameras on one wall: holder arm 0.67 m, head 0.70 m wide -> heads 0.6 m apart


def spread(G):
    """judge E05 (11-12): the server desk and office west cameras hung 0.77 m apart on the server room's west wall, one arm through the other.
    Of two cameras on the same wall (facing within 20 degrees, within 1 m in height) nearer than SPREAD, the later one slides along the wall away
    from the other, only when the wall goes on behind the new spot. After hide_in_feeds: which feed hides which camera stays as measured."""
    from qast import lit
    m, K = G['m'], G['K']
    T = K._tris()[0]
    mounts = _mast_xy(m, lit)
    cams = []
    for i in sorted(m.find('SCamera')):
        p = np.array([float(lit(m.byid[i].args[k])) for k in (3, 4, 5)]); g = float(lit(m.byid[i].args[6]))
        if any(np.hypot(p[0] - q[0], p[1] - q[1]) < 0.3 * M for q in mounts):   # (review rc7s #2: a mast / rod camera stays on its mount)
            continue
        cams.append([i, str(lit(m.byid[i].args[2])), p, g])
    out = []
    for a in range(len(cams)):
        for b in range(a + 1, len(cams)):
            i, nm, p, g = cams[b]
            q = cams[a][2]
            dg = abs((g - cams[a][3] + math.pi) % (2 * math.pi) - math.pi)
            d = np.hypot(*(p[:2] - q[:2])) / M
            if d >= SPREAD or dg > 0.35 or abs(p[2] - q[2]) > 1.0 * M:
                continue
            t = np.array([math.cos(g), math.sin(g)])            # along the wall (perpendicular to the view)
            s = 1.0 if (p[:2] - q[:2]) @ t >= 0 else -1.0
            along = abs(float((p[:2] - q[:2]) @ t)) / M
            mv = SPREAD - along if along > 0.05 else SPREAD
            n = p.copy(); n[:2] += t * s * mv * M
            f = np.array([-math.sin(g), math.cos(g), 0.0])
            back = SOFT_PLATE if str(lit(m.byid[i].args[7])) == '335_01_1' else 0.0   # (review rc7t #1: the soft holder's wall is 0.215 m behind its origin)
            h = ray(T, n + f * 0.3 * M, -f, (0.6 + back) * M)
            if h is None or not (0.15 + back) * M <= h <= (0.45 + back) * M:
                print('sscams: spread: camera %d %r %.2f m from %d: no wall %.2f m along, left' % (i, nm, d, cams[a][0], mv)); continue
            m.set(i, 3, float(n[0])); m.set(i, 4, float(n[1]))
            cams[b][2] = n
            out.append((i, nm, cams[a][0], round(d, 2), round(mv, 2)))
    for i, nm, o, d, mv in out:
        print('sscams: spread: camera %d %r was %.2f m from camera %d on its wall: %.2f m along it' % (i, nm, d, o, mv))
    return out


def apply(G):
    if ON:
        lod(G)
        if STOCKCAMS:
            one_per_room(G)                                      # (first: its table holds the rc7q spots)
            mast_move(G)                                         # (before the plate shift: its table holds the pole spots)
            stock_models(G)
            headroom(G, soft=(0.45, (-0.2, 0.0, 0.3, 0.6, 0.8)))  # (the stock soft head stands 0.33 m over its pivot, 0.42 m over the camera's origin; probe plate to past the lens)
        else:
            headroom(G)
        hide_in_feeds(G)
        spread(G)
