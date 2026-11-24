"""ssface.py - S2 build gate (ss-life 11-15, owner: 'guards stand facing walls like robots; in the original game guards face each other, talk, do
something'). Last pass of build_sandstorm.py, on the written build (out/objects.qvm + out/ai).

For every HumanSoldier whose own AI script does not walk (no AIAction_Patrol, no AIAction_RunToNode = R-ARRIVE):
  free  = metres of floor straight ahead of his spawn facing (the builder's free_run: 0.25 m steps on the nav grid, step <= 0.45 m,
          head room >= 1.7 m; a wall, a table, sandbags or an edge stop it)
  OK when free >= MIN_FREE (3 m), or a man of the SAME squad stands within 4 m inside +-20 degrees of his facing (a partner),
          or his squad / slot is in ALLOW with a reason (a parapet he looks over, bags in front of his MG, a desk he works at, a seat).
  FAIL otherwise. check() raises unless SS_FACE_WARN=1 (only while iterating; never for a candidate).
Writes <out>/ssface.txt: one line per standing man (id, squad, position, facing, free m, verdict) - the S2 table for the proof index."""
import math, os, re
import igiqvm, alarmai
from qast import lit

MIN_FREE = 3.0
PARTNER_M, PARTNER_DEG = 4.0, 20.0
# squad name -> reason, or {slot index in the squad: reason}; slots count the squad's men in file order
ALLOW = {
    'U deck west': 'parapet: looks over the deck wall at the road and the lobby',
    'U deck east': 'parapet: looks over the deck wall at the gate road',
    'U spur': {0: 'catwalk rail: looks down on the cage'},
    'U road post': {0: 'MG behind the sandbags, watching the road'},
    'U gate post': {0: 'MG behind the sandbags, watching the road', 1: 'checks his rifle at the bags'},
    'U comms': {0: 'types at the comms terminal'},
    'U motor pool': {0: 'kneels at the launch truck, working on it'},
    'U scientists': 'study the missile (work clip)',
    'U barracks': {0: 'asleep against the wall by his bunk', 1: 'asleep against the wall by his bunk', 2: 'sits against the wall, awake'},
    'U ready': {3: 'kit check at his locker', 5: 'cleans his rifle at the lockers'},
}


def _walk(st):
    out = []

    def w(x, par):
        if isinstance(x, list):
            for y in x:
                w(y, par)
        elif isinstance(x, igiqvm.Call):
            if x.name == 'Task_New':
                out.append((x, par))
                for a in x.args:
                    w(a, x)
                return
            for a in x.args:
                w(a, par)
    w(st, None)
    return out


def _alarm_only_look(txt):
    """(S3) True when every AIAction_LookAround line sits inside an 'if (<var>.nValue == 1) {' block (the alarm branch); the census only"""
    lines, ok = txt.splitlines(), True
    for i, l in enumerate(lines):
        if 'AIAction_LookAround(' not in l:
            continue
        ind = len(l) - len(l.lstrip())
        j = i - 1
        while j >= 0 and not (lines[j].rstrip().endswith('{') and len(lines[j]) - len(lines[j].lstrip()) < ind):
            j -= 1
        if j < 0 or not re.search(r'nValue == 1\) \{$', lines[j].rstrip()):
            ok = False
    return ok


def check(out, free_run, log=print, strict=None):
    ver, st = igiqvm.decompile(open(os.path.join(out, 'objects.qvm'), 'rb').read())
    T = _walk(st)
    par = {id(t): p for t, p in T}
    ty = lambda t: str(lit(t.args[1]))
    men = []                                                   # (id, squad name, slot, pos units, gamma, ai text)
    slots = {}
    for t, p in T:
        if ty(t) != 'HumanSoldier':
            continue
        q, sq = par.get(id(t)), None
        while q is not None and sq is None:
            if ty(q) == 'AISquad':
                sq = q
            q = par.get(id(q))
        name = str(lit(sq.args[2])) if sq is not None else '?'
        slot = slots.get(name, 0); slots[name] = slot + 1
        x, y, z, g = (float(lit(t.args[k])) for k in (3, 4, 5, 6))
        ai = next((c for c in t.args if isinstance(c, igiqvm.Call) and c.name == 'Task_New' and str(lit(c.args[1])) == 'HumanAI'), None)
        f = os.path.join(out, 'ai', '%s.qvm' % lit(ai.args[0])) if ai is not None else None
        txt = alarmai.to_text(alarmai.decompile_ai(open(f, 'rb').read())[1]) if f and os.path.exists(f) else ''
        men.append((int(lit(t.args[0])), name, slot, (x, y, z), g, txt))
    rows, bad = [], []
    for hid, name, slot, p, g, txt in men:
        if 'AIAction_Patrol(' in txt or 'AIAction_RunToNode(' in txt:
            continue
        free = free_run(p, g, cap=25.0)
        why = None
        if free >= MIN_FREE:
            why = 'lane %.1f m' % free
        else:
            for hid2, name2, _s2, p2, _g2, _t2 in men:
                if hid2 == hid or name2 != name:
                    continue
                d = math.hypot(p2[0] - p[0], p2[1] - p[1]) / 4096.0
                b = math.atan2(-(p2[0] - p[0]), p2[1] - p[1])
                off = abs((math.degrees(b - g) + 180.0) % 360.0 - 180.0)
                if d <= PARTNER_M and off <= PARTNER_DEG:
                    why = 'partner %d at %.1f m, %.0f deg' % (hid2, d, off)
                    break
        if why is None:
            a = ALLOW.get(name)
            a = a.get(slot) if isinstance(a, dict) else a
            if a:
                why = 'allowed: ' + a
        rows.append('%5d  %-28s %2d  (%6.1f %6.1f %6.1f)  %5.0f deg  free %5.2f m  %s' % (hid, name[:28], slot, p[0] / 4096, p[1] / 4096, p[2] / 4096,
                                                                                         math.degrees(g) % 360, free, why or 'FAIL: faces an obstacle, no partner, no reason'))
        if why is None:
            bad.append((hid, name, slot, round(free, 2)))
    walkers = [hid for hid, name, _s, _p, _g, txt in men if 'AIAction_Patrol(' in txt and 'AIAction_RunToNode(' not in txt]
    talkers = [hid for hid, name, _s, _p, _g, txt in men if "SetStandActionAnimation('stand_talk" in txt]
    looks = [hid for hid, name, _s, _p, _g, txt in men if 'AIAction_LookAround(' in txt and not _alarm_only_look(txt)]
    rows.append('S3: %d men, %d walk a patrol loop (%.0f %%), %d talk, %d with a LookAround outside an alarm branch: %s'
                % (len(men), len(walkers), 100.0 * len(walkers) / max(1, len(men)), len(talkers), len(looks), looks))
    log(rows[-1])
    open(os.path.join(out, 'ssface.txt'), 'w').write('\n'.join(rows) + '\n')
    log('ssface: %d standing men checked, %d fail (free floor < %.0f m ahead, no partner, no reason): %s' % (len(rows), len(bad), MIN_FREE, bad))
    if strict is None:
        strict = os.environ.get('SS_FACE_WARN') != '1'
    if bad and strict:
        raise AssertionError('S2 ssface: men facing an obstacle: %s (table: %s)' % (bad, os.path.join(out, 'ssface.txt')))
    return bad
