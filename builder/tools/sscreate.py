"""sscreate.py <build dir>: G43 rule check (orchestrator 11-14). No soldier may be created at RUN TIME in the first 10 s of the mission with a
move order (WalkToNode / RunToNode / Patrol in his AI script): a man created by a ConditionalContainer and moved in the same frames reads an
unfilled graph node in the stencil-shadow pass on a real GPU (igi2.exe+0xfabc3 / 0xf8ac3, work/perf/g19/FABC3_STACK.md).

Every ConditionalContainer that holds a HumanSoldier is classed by its condition:
  LATE   a conjoined term that cannot be true before 10 s: a wake/fight latch 'EditVariable_N.nValue == 1' whose own rule needs Jones or an
         alarm (listed), an 'AreaActivate_N.nActive', a 'LevelTimer_N.nTick > s' with s >= 10 on the after-intro timer, a SplinePath position
  LOAD   true from tick 0 and never depends on a cutscene ('!ConditionalContainer_<decrypt>.isRun ...'): created with the level (reported only)
  EARLY  anything else (a cutscene / the intro container / a timer under 10 s): FAIL if any man in it has a move order
Prints one line per container; exits 1 (or raises with check()) on an EARLY container with a move order. Also importable: check(out)."""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, HERE)                                   # (copied into a release tree's tools/: igiqvm sits beside it)
import igiqvm, alarmai
from qast import lit

MOVES = ('AIAction_WalkToNode', 'AIAction_RunToNode', 'AIAction_Patrol')


def _tasks(st):
    out = {}

    def walk(x, par):
        if isinstance(x, list):
            for y in x:
                walk(y, par)
        elif hasattr(x, 'args'):
            if getattr(x, 'name', '') == 'Task_New':
                try:
                    tid = int(lit(x.args[0]))
                except Exception:
                    tid = None
                if tid is not None:
                    out[tid] = (x, par)
                for a in x.args:
                    walk(a, tid if tid is not None else par)
                return
            for a in x.args:
                walk(a, par)
    walk(st, None)
    return out


def check(out, log=print, strict=True):
    v, st = igiqvm.decompile(open(os.path.join(out, 'objects.qvm'), 'rb').read())
    T = _tasks(st)
    ty = {k: str(lit(t.args[1])) for k, (t, p) in T.items()}
    rule = {k: str(lit(t.args[7])) if ty[k] == 'EditVariable' and len(t.args) > 7 else '' for k, (t, p) in T.items()}
    timers = {k: str(lit(t.args[9])) for k, (t, p) in T.items() if ty[k] == 'LevelTimer' and len(t.args) > 9}
    after = [k for k, (t, p) in T.items() if ty[k] == 'LevelTimer' and str(lit(t.args[2])) == 'time since intro ended']

    def children(k):
        return [c for c, (t, p) in T.items() if p == k]

    def men_of(k):
        res, todo = [], [k]
        while todo:
            c = todo.pop()
            for d in children(c):
                if ty[d] == 'HumanSoldier':
                    res.append(d)
                todo.append(d)
        return res

    def ai_of(h):
        for d in children(h):
            if ty[d] == 'HumanAI':
                return d
        return None

    def moves(h):
        a = ai_of(h)
        f = os.path.join(out, 'ai', '%d.qvm' % a) if a else None
        if not f or not os.path.exists(f):
            return []
        t = alarmai.to_text(alarmai.decompile_ai(open(f, 'rb').read())[1])
        return sorted(set(m for m in MOVES if m + '(' in t))

    def late(cond):
        for term in [c.strip(' ()') for c in re.split(r'&&', cond)]:
            if re.fullmatch(r'\(?EditVariable_\d+\.nValue == 1\)?', term):
                n = int(re.search(r'\d+', term).group())
                r = rule.get(n, '')
                if 'AreaActivate_' in r or 'Alarm' in r or 'EditVariable_' in r:      # (a latch set by Jones' zone / an alarm / another latch)
                    return 'latch EditVariable_%d' % n
            if term.startswith('AreaActivate_') and term.endswith('.nActive'):
                return term
            m_ = re.fullmatch(r'LevelTimer_(\d+)\.nTick > ([\d.]+) \* GAME_FREQUENCY', term)
            if m_ and float(m_.group(2)) >= 10.0 and int(m_.group(1)) in after:
                return 'after-intro timer >= %s s' % m_.group(2)
            if m_ and 'AreaActivate_' in timers.get(int(m_.group(1)), ''):          # (a timer that starts on Jones' zone, e.g. the truck delay)
                return 'zone timer LevelTimer_%s' % m_.group(1)
            if term.startswith('SplinePathGuideQTask_'):
                return term
        return None

    bad, n = [], 0
    for k, (t, p) in sorted(T.items()):
        if ty[k] != 'ConditionalContainer':
            continue
        men = men_of(k)
        if not men:
            continue
        n += 1
        cond = str(lit(t.args[3]))
        # a container nested in another container is gated by its parents too
        anc = _ancestors(T, k)
        conds = [cond] + [str(lit(T[a][0].args[3])) for a in anc if ty.get(a) == 'ConditionalContainer']
        why = next((w for w in (late(c) for c in conds) if w), None)
        if why:
            cls = 'LATE (%s)' % why
        elif not re.search(r'CutScene_\d+\.isRun|ConditionalContainer_\d+\.isRun\b(?! \|\|)|LevelTimer_', ' '.join(conds)) or \
                all(re.match(r'^\(?!ConditionalContainer_\d+\.isRun \|\| EditVariable_\d+\.nValue == 1\)?$', c.strip()) for c in conds):
            cls = 'LOAD'
        else:
            cls = 'EARLY'
        mv = {h: moves(h) for h in men}
        movers = [h for h in men if mv[h]]
        log('sscreate: %5d %-55s %-34s men %d%s' % (k, str(lit(t.args[2]))[:55], cls[:34], len(men),
                                                    (' move: %s' % ', '.join('%d %s' % (h, '/'.join(x[9:] for x in mv[h])) for h in movers)) if movers else ''))
        if cls == 'EARLY' and movers:
            bad.append((k, str(lit(t.args[2])), movers))
        if cls != 'LOAD':                                   # (orchestrator 11-14: no move order right at the man's own creation; ss-life 11-15: 0.5 s, IDLE only)
            import ssspawnwait as _sw
            _tk = _sw.TICKS
            cnt = [n_ for n_, r_ in rule.items() if ty.get(n_) == 'EditVariable' and r_.startswith('ConditionalContainer_%d.isRun && EditVariable_%d.nValue < %d' % (k, n_, _tk))]
            arrive = str(lit(t.args[2])).lower().startswith(tuple(a_.lower() for a_ in _sw.ARRIVE))
            for h in men:
                a_ = ai_of(h)
                f_ = os.path.join(out, 'ai', '%d.qvm' % a_) if a_ else None
                txt = alarmai.to_text(alarmai.decompile_ai(open(f_, 'rb').read())[1]) if f_ and os.path.exists(f_) else ''
                first = txt.splitlines()[0] if txt else ''
                inner = [c_ for c_ in _ancestors(T, h) if ty.get(c_) == 'ConditionalContainer'][:1]
                if inner and inner[0] != k:
                    continue                                # (checked with his innermost container)
                if arrive:                                  # (S16 R-ARRIVE: no wrapper; his first idle may run to his fight node, the L15 originals' way)
                    if 'AIAction_RunToNode(' not in txt:
                        bad.append((k, str(lit(t.args[2])), 'man %d: R-ARRIVE container but no RunToNode' % h))
                elif not cnt or not any(('EditVariable_%d.nValue < %d' % (c_, _tk)) in first for c_ in cnt):
                    bad.append((k, str(lit(t.args[2])), 'man %d: no spawn guard' % h))
                if any(m_ + '(' in _create_blocks(txt) for m_ in MOVES):
                    bad.append((k, str(lit(t.args[2])), 'man %d: move order in his CREATE branch' % h))
    log('sscreate: %d containers with soldiers, %d rule problems' % (n, len(bad))); [log('sscreate: PROBLEM %s' % (b_,)) for b_ in bad]
    if bad and strict:
        raise AssertionError('G43 rule broken: %s' % bad)
    return bad


def _create_blocks(txt):
    """(ss-life 11-15) every AIEVENT_CREATE branch of the script: the spawn guard's hold branch carries a stripped copy of the body"""
    lines, res = txt.splitlines(), []
    for i, l in enumerate(lines):
        if 'AIEVENT_CREATE) {' in l and '!=' not in l:
            res.append(_create_block(chr(10).join(lines[i:])))
    return chr(10).join(res)


def _create_block(txt):
    """the body of the script's AIEVENT_CREATE branch (lines after the 'if (... == AIEVENT_CREATE) {' line until its closing brace)"""
    lines = txt.splitlines()
    for i, l in enumerate(lines):
        if 'AIEVENT_CREATE) {' in l and '!=' not in l:
            ind = len(l) - len(l.lstrip())
            body = []
            for x in lines[i + 1:]:
                if x.strip().startswith('}') and len(x) - len(x.lstrip()) == ind:
                    break
                body.append(x)
            return chr(10).join(body)
    return ''


def _ancestors(T, k):
    res, p = [], T[k][1]
    while p is not None and p in T:
        res.append(p)
        p = T[p][1]
    return res


if __name__ == '__main__':
    b = check(sys.argv[1], strict=False)
    sys.exit(1 if b else 0)
