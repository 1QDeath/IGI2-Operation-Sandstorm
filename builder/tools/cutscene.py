"""Cutscene helpers for IGI 2 missions built with tools/mission_lib.py (from the 10-10 research, work/research/cutscenes.md).

Everything here mirrors the wiring of the original single-player levels (see cutscenes.md for the evidence):
  intro  = ConditionalContainer('!CutScene_<cs>.isFinished && !EditVariable_<skip>.nValue',
                                'MenuManager_SetEnabled (FALSE) && Game_DisableMusic()',
                                'MenuManager_SetEnabled (TRUE) && Game_EnableMusic()')
             -> CutScene(Run='!CutScene_<cs>.isFinished') -> EditCamera keyframes (children, in time order)
             -> StatusMessage captions (Cutscene message = TRUE, Send = 'CutScene_<cs>.nTick > t*GAME_FREQUENCY')
  skip   = EditVariable(Add='EditVariable_<skip>.nValue == 0 && LevelFlow_GetBreakCutSceneKey()')
  player = HumanPlayer inside ConditionalContainer('!ConditionalContainer_<intro>.isRun && !ConditionalContainer_<outro>.isRun')
  outro  = same as intro, started by the mission-complete message; LevelFlow Complete = 'EditVariable_<outro skip>.nValue == 1'
"""
import math
from igiqvm import Call, Int, Str
from mission_lib import T
from qast import lit

M = 4096.0                                   # world units per metre (spline speed/time check: median ratio 0.993 over 597 segments)
NONE = 'CAMERAFILTER_TYPE_NONE'
BAND = 'CAMERAFILTER_TYPE_BAND'              # colour-multiply filter: (0,0,0) = black, (1,1,1) = normal picture -> fades
MENU_OFF = 'MenuManager_SetEnabled (FALSE) && Game_DisableMusic()'   # verbatim in all 19 original intros + 11 outros
MENU_ON = 'MenuManager_SetEnabled (TRUE) && Game_EnableMusic()'
BREAK_KEY = 'LevelFlow_GetBreakCutSceneKey()'


def look(cam, tgt):
    """(Alpha, Gamma) for an EditCamera at `cam` looking at point `tgt`.
    Alpha = pitch: -pi/2 level, -pi straight down, 0 straight up.  Gamma = yaw, same as HumanPlayer: 0 = +y (north), pi/2 = -x (west)."""
    dx, dy, dz = tgt[0] - cam[0], tgt[1] - cam[1], tgt[2] - cam[2]
    return math.atan2(dz, math.hypot(dx, dy)) - math.pi / 2, math.atan2(-dx, dy)


def key(pos, tgt, dur, smooth, fov=1.0, filt=NONE, color=(0.0, 0.0, 0.0), noise=0.5, shake=0.0):
    """One camera keyframe. smooth=True: move/pan/zoom/fade from this key to the NEXT key over `dur` seconds.
    smooth=False: hold this key for `dur` seconds, then hard-cut to the next key. A dur=0 key is an end pose."""
    return dict(pos=pos, tgt=tgt, dur=dur, smooth=smooth, fov=fov, filt=filt, color=color, noise=noise, shake=shake)


def cameras(nid, keys):
    out, prev = [], None
    for k in keys:
        a, g = look(k['pos'], k['tgt'])
        if prev is not None:                 # interpolating INTO this key: keep yaw continuous (never spin the long way round)
            g += 2 * math.pi * round((prev - g) / (2 * math.pi))
        prev = g if k['smooth'] else None    # after a hard cut the next key starts fresh in (-pi, pi]
        x, y, z = (float(c) for c in k['pos'])
        r, gr, b = (float(c) for c in k['color'])
        out.append(T(nid(), 'EditCamera', '', x, y, z, round(a, 6), 0.0, round(g, 6), float(k['fov']), float(k['dur']),
                     int(k.get('link_id', -1)), True, int(k.get('target_id', -1)), True,   # target: follow a task (originals:
                     bool(k['smooth']), -1, k['filt'], float(k['noise']), r, gr, b, float(k['shake'])))  # trucks, soldiers)
    return out


def cutscene(nid, keys, name=''):
    """CutScene task with the EditCamera children. All 149 originals use exactly these 17 values (only Position and Run differ)."""
    cs = nid()
    x, y, z = (float(c) for c in keys[0]['pos'])         # Position is only the editor gizmo; any value works
    return cs, T(cs, 'CutScene', name, x, y, z, 0.0, 0.0, 0.0,
                 '!CutScene_%d.isFinished' % cs, '', '', 0.0, 1.0, 0.7, 0.0, 0.0, 0.0, '', '',
                 children=cameras(nid, keys))


def caption(nid, cs, at, text_key, secs=5.0, cutscene_msg=True, sound=''):
    """Subtitle line `text_key` (a key in LANGUAGE/<lang>/messages.res) shown `at` seconds into CutScene `cs`."""
    return T(nid(), 'StatusMessage', 'caption ' + text_key, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
             'CutScene_%d.nTick > %s * GAME_FREQUENCY' % (cs, at), text_key, '', sound, True, cutscene_msg, float(secs), '')


def gate(m, cid, cond, label=None):
    """Turn an existing Container into a ConditionalContainer with `cond` (children kept) - same trick as Mission.disable()."""
    t = m.task(cid)
    kids = [a for a in t.args if isinstance(a, Call)]
    t.args = [Int(cid), Str('ConditionalContainer'), Str(label or str(lit(t.args[2]))), Str(cond), Str(''), Str('')] + kids


def _caps(nid, cs, captions):
    """captions = [(seconds, text_key, english_text[, sound_def[, secs]])]"""
    out = []
    for c in captions:
        at, k, _txt = c[:3]
        snd = c[3] if len(c) > 3 else ''
        secs = c[4] if len(c) > 4 else 5.0
        out.append(caption(nid, cs, at, k, secs=secs, sound=snd))
    return out


def add_intro(m, nid, parent, keys, captions):
    """captions = [(seconds, text_key, english_text[, sound_def[, secs]])].
    Returns ids: intro container, cutscene, skip variable, 'after' LevelTimer."""
    skip, intro = nid(), nid()
    cs, cs_task = cutscene(nid, keys)
    kids = [cs_task] + _caps(nid, cs, captions)
    m.add_child(parent, T(intro, 'ConditionalContainer', 'Intro Cutscene',
                          '!CutScene_%d.isFinished && !EditVariable_%d.nValue' % (cs, skip), MENU_OFF, MENU_ON, children=kids))
    m.add_child(parent, T(skip, 'EditVariable', 'CutScene Break Key (intro)', 0.0, 0.0, 0.0, 0,
                          'EditVariable_%d.nValue == 0 && %s' % (skip, BREAK_KEY), ''))
    after = nid()                              # counts game time from the end (or skip) of the intro
    m.add_child(parent, T(after, 'LevelTimer', 'time since intro ended', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                          'CutScene_%d.isFinished || EditVariable_%d.nValue == 1' % (cs, skip), '', False))
    for c in captions:
        m.add_text('messages', c[1], c[2])
    return dict(intro=intro, cs=cs, skip=skip, after=after)


def add_outro(m, nid, parent, keys, captions, trigger):
    """trigger = expression that starts the outro (e.g. the mission-complete StatusMessage has finished displaying).
    Returns ids + 'complete' = the expression to put in LevelFlow arg 10."""
    skip, outro = nid(), nid()
    cs, cs_task = cutscene(nid, keys)
    kids = [cs_task] + _caps(nid, cs, captions)
    m.add_child(parent, T(outro, 'ConditionalContainer', 'Outro Cutscene',
                          '%s && !HumanPlayer_0.isDead && EditVariable_%d.nValue == 0' % (trigger, skip), MENU_OFF, MENU_ON,
                          children=kids))
    # flips to 1 when the outro finishes OR the break key is pressed WHILE the outro runs (never during gameplay)
    m.add_child(parent, T(skip, 'EditVariable', 'CutScene Break Key (outro)', 0.0, 0.0, 0.0, 0,
                          'EditVariable_%d.nValue == 0 &&\n(\n (%s && ConditionalContainer_%d.isRun)\n ||\n CutScene_%d.isFinished\n)'
                          % (skip, BREAK_KEY, outro, cs), ''))
    for c in captions:
        m.add_text('messages', c[1], c[2])
    return dict(outro=outro, cs=cs, skip=skip, complete='EditVariable_%d.nValue == 1' % skip)


def add_chain(m, nid, parent, shots, captions, kind, trigger=None):
    """several shots one after another (Mission 11 intro pattern: one ConditionalContainer per shot,
    'CutScene_<previous>.isFinished && !CutScene_<this>.isFinished', so each shot's props exist only while it runs).
    shots = [dict(cs=<CutScene id>, tasks=[the shot's tasks incl. that CutScene], dur=seconds, name='')];
    captions = [(seconds from the start of the whole chain, text_key, english_text[, sound_def[, secs]])].
    kind 'intro' -> like add_intro(); 'outro' -> like add_outro(trigger)."""
    starts, t = [], 0.0
    for s in shots:
        starts.append(t); t += s['dur']
    kids = []
    for k, s in enumerate(shots):
        cond = ('!CutScene_%d.isFinished' % s['cs'] if k == 0 else
                'CutScene_%d.isFinished && !CutScene_%d.isFinished' % (shots[k - 1]['cs'], s['cs']))
        kids.append(T(nid(), 'ConditionalContainer', 'shot %d %s' % (k + 1, s.get('name', '')), cond, '', '', children=s['tasks']))
    for c in captions:
        at, key_, _txt = c[:3]
        snd = c[3] if len(c) > 3 else ''
        secs = c[4] if len(c) > 4 else 5.0
        k = max(i for i in range(len(shots)) if starts[i] <= at + 1e-6)
        kids.append(caption(nid, shots[k]['cs'], round(at - starts[k], 2), key_, secs=secs, sound=snd))
        m.add_text('messages', key_, _txt)
    last = shots[-1]['cs']
    skip, box = nid(), nid()
    if kind == 'intro':
        m.add_child(parent, T(box, 'ConditionalContainer', 'Intro Cutscene',
                              '!CutScene_%d.isFinished && !EditVariable_%d.nValue' % (last, skip), MENU_OFF, MENU_ON, children=kids))
        m.add_child(parent, T(skip, 'EditVariable', 'CutScene Break Key (intro)', 0.0, 0.0, 0.0, 0,
                              'EditVariable_%d.nValue == 0 && %s' % (skip, BREAK_KEY), ''))
        after = nid()
        m.add_child(parent, T(after, 'LevelTimer', 'time since intro ended', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                              'CutScene_%d.isFinished || EditVariable_%d.nValue == 1' % (last, skip), '', False))
        return dict(intro=box, cs=last, skip=skip, after=after, starts=starts, total=t)
    m.add_child(parent, T(box, 'ConditionalContainer', 'Outro Cutscene',
                          '%s && !HumanPlayer_0.isDead && EditVariable_%d.nValue == 0' % (trigger, skip), MENU_OFF, MENU_ON,
                          children=kids))
    m.add_child(parent, T(skip, 'EditVariable', 'CutScene Break Key (outro)', 0.0, 0.0, 0.0, 0,
                          'EditVariable_%d.nValue == 0 &&\n(\n (%s && ConditionalContainer_%d.isRun)\n ||\n CutScene_%d.isFinished\n)'
                          % (skip, BREAK_KEY, box, last), ''))
    return dict(outro=box, cs=last, skip=skip, complete='EditVariable_%d.nValue == 1' % skip, starts=starts, total=t)


def orbit_shot(terrain, target, dist_m, bearing0, bearing1, elev_deg, secs, clear_m=4.0, fov=1.0, max_elev=70.0, fov_end=None):
    """two keys orbiting `target` (x, y, z) at dist_m metres, bearing0 -> bearing1 (degrees, 0 = camera north of the target),
    elev_deg above the target; the elevation is raised until both camera-to-target lines clear the terrain by clear_m."""
    def cam(b, e):
        r = dist_m * M * math.cos(math.radians(e))
        return (target[0] + r * math.sin(math.radians(b)), target[1] + r * math.cos(math.radians(b)),
                target[2] + dist_m * M * math.sin(math.radians(e)))

    def clear(c):
        for k in range(1, 18):                          # skip the last stretch next to the target itself
            f = k / 20.0
            x, y, z = (c[i] + (target[i] - c[i]) * f for i in range(3))
            if z < terrain.height(x, y) + clear_m * M:
                return False
        return True
    e = elev_deg
    while e < max_elev and not (clear(cam(bearing0, e)) and clear(cam(bearing1, e))):
        e += 3.0
    return [key(cam(bearing0, e), target, secs, True, fov=fov), key(cam(bearing1, e), target, 0.0, False,
                                                                  fov=fov if fov_end is None else fov_end)]
