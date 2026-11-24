"""ssspawnwait.py (G43 rule, orchestrator 11-14): a soldier created at RUN TIME by a ConditionalContainer gets no move order in his first 3 s.

For every ConditionalContainer that holds HumanSoldiers and is not true from load (LOAD = '!ConditionalContainer_<decrypt>.isRun || ...' only):
  - one counter EditVariable 'SS G43 open ticks <K>': Add rule 'ConditionalContainer_K.isRun && EditVariable_V.nValue < 90' (GAME_FREQUENCY = 30,
    igi2.exe Symbol_Register: TICKS 15 = 0.5 s after the container opened (was 90 = 3 s until 11-15); the containers open once and stay open)
  - each man's AI script (ai/<HumanAI id>.qvm) and each AISquad script inside it (ai/Squad_<id>.qvm) gets a guard in front of everything:
      soldier: if (EditVariable_V.nValue < 15 && IDLE) { strip_moves(<the script>) } else { <the script as built> }   (ARRIVE squads: not wrapped)
      squad:   if (EditVariable_V.nValue < 15 && event != CREATE) { } else { <the script as built> }
    (the CREATE event always passes: its branch sets event priorities, accuracy and stand clips; sscreate checks it holds no move)
    so no Patrol / WalkToNode / RunToNode / squad move can be issued in the frames around his creation (crash class 0xfabc3 / 0xf8ac3:
    work/perf/g19/FABC3_STACK.md). A nested container uses the innermost one's counter.
Post-build: runs on out/objects.qvm + out/ai after ssperf (free ids in the builder's order, ssperf._free_ids). apply(out) -> {container: counter}."""
import os, re
import igiqvm, alarmai
from alarmai import If, C, EQ, Bin, compile_ai, decompile_ai
from igiqvm import Call, Flt, Int, Str
from qast import lit

LOAD_RE = re.compile(r'^\(?!ConditionalContainer_\d+\.isRun \|\| EditVariable_\d+\.nValue == 1\)?$')
TICKS = 15                                        # (S3/S4 ss-life 11-15: was 90 = 3 s of aimed LookAround with every event dropped, seen on the truck men
                                                  #  and the stair teams; the G43 cause was stale saves (memory igi2-g43-real-gpu-crash). Now only the IDLE
                                                  #  move is held back for 0.5 s, the man stands in the engine idle, every other event reaches his script)
ARRIVE = ('SS U truck troops', 'SS stair team')   # (S16: containers whose men carry R-ARRIVE (their own 'SS arrive ticks' counter, made by the builder):
                                                  #  the men are not wrapped, their first idle is the run to the fight node; the squad script still waits)


def _walk(st):
    """[(task call, parent call)] in file order"""
    out = []

    def w(x, par):
        if isinstance(x, list):
            for y in x:
                w(y, par)
        elif isinstance(x, Call):
            if x.name == 'Task_New':
                out.append((x, par))
                for a in x.args:
                    w(a, x)
                return
            for a in x.args:
                w(a, par)
    w(st, None)
    return out


ARRIVED = {}                                      # container id -> its counter, for the R-ARRIVE scripts (filled by apply)
MOVES = ('AIAction_WalkToNode', 'AIAction_RunToNode', 'AIAction_Patrol')


def strip_moves(stmts):
    """(S3/S4 ss-life 11-15, X3_GUARD_LIFE 7.4) the man's own script without its moves and without LookAround, for the frames in which no
    move may land. One AIAction_Idle lasts 10-19 s (init 0x5bcb20: (rand % 10 + 10) * 30 ticks), so the old hold [Idle(1)] parked walkers for
    up to 19 s and made talkers change pose when it ended. Now: a clip man keeps SetStandActionAnimation + PlayAnimation (he talks from his
    first frame), a walker gets AIAction_Wait(1, 1) (the originals' run-time call, L31 ai/543-545: asks again every second), a standing man
    keeps his Idle. A branch that lost its only action gets Wait(1, 1) if it lost a move, else the engine idle. Returns a new list."""
    import copy
    out, lost_move, lost = [], False, False
    for s in stmts:
        if isinstance(s, If):
            s = copy.copy(s)
            s.then = strip_moves(s.then)
            if s.els:
                s.els = strip_moves(s.els)
            out.append(s)
        elif getattr(s, 'name', '') in MOVES:
            lost_move = lost = True
        elif getattr(s, 'name', '') == 'AIAction_LookAround':
            lost = True
        else:
            out.append(copy.deepcopy(s))
    if lost and not any(_acts(s) for s in out):
        out.insert(0, C('AIAction_Wait', 1, 1) if lost_move else C('AIAction_Idle', 1))
    return out


def _acts(s):
    if isinstance(s, If):
        return any(_acts(x) for x in s.then) or bool(s.els and any(_acts(x) for x in s.els))
    return str(getattr(s, 'name', '')).startswith('AIAction_')


def apply(out, log=print):
    import ssperf
    pq = os.path.join(out, 'objects.qvm')
    ver, st = igiqvm.decompile(open(pq, 'rb').read())
    T = _walk(st)
    par = {id(t): p for t, p in T}
    ty = lambda t: str(lit(t.args[1]))
    used = {int(lit(t.args[0])) for t, p in T if isinstance(lit(t.args[0]), int)}
    logic = next(t for t, p in T if ty(t) == 'Container' and str(lit(t.args[2])) == 'SS mission logic')
    if any(ty(t) == 'EditVariable' and str(lit(t.args[2])).startswith('SS G43 open ticks') for t, p in T):
        log('ssspawnwait: already applied - left'); return {}
    free = ssperf._free_ids(out, used)

    def container_of(t):
        p = par.get(id(t))
        while p is not None:
            if ty(p) == 'ConditionalContainer':
                return p
            p = par.get(id(p))
        return None

    groups = {}                                   # container id -> [soldier AI ids, squad ids]
    for t, p in T:
        k = ty(t)
        if k not in ('HumanAI', 'AISquad'):
            continue
        c = container_of(t)
        if c is None:
            continue
        chain, q = [], c                          # (LOAD only if this container and every container above it are true from load)
        while q is not None:
            if ty(q) == 'ConditionalContainer':
                chain.append(q)
            q = par.get(id(q))
        if all(LOAD_RE.match(str(lit(x.args[3])).strip()) for x in chain):
            continue
        g = groups.setdefault(int(lit(c.args[0])), (c, [], []))
        (g[1] if k == 'HumanAI' else g[2]).append(int(lit(t.args[0])))
    counters = {}
    for cid, (c, ais, sqs) in sorted(groups.items()):
        if not ais:
            continue
        v = next(free)
        arrive = str(lit(c.args[2])).lower().startswith(tuple(a_.lower() for a_ in ARRIVE))
        logic.args.append(Call('Task_New', [Int(v), Str('EditVariable'), Str('SS G43 open ticks %d' % cid), Flt(0.0), Flt(0.0), Flt(0.0), Int(0),
                                           Str('ConditionalContainer_%d.isRun && EditVariable_%d.nValue < %d' % (cid, v, TICKS)), Str('')]))
        counters[cid] = v
        if arrive:
            ARRIVED[cid] = v
        _w = Bin('<', alarmai.E('EditVariable_%d.nValue' % v), alarmai.E(TICKS))
        wait = Bin('&&', _w, Bin('!=', alarmai.E(('AIFunction_GetCurrentEventType',)), alarmai.E('AIEVENT_CREATE')))   # (CREATE passes: eyes, accuracy, stand clips)
        swait = Bin('&&', _w, Bin('!=', alarmai.E(('AISquad_GetEvent',)), alarmai.E('AIEVENT_CREATE')))
        for a in ais:
            f = os.path.join(out, 'ai', '%d.qvm' % a)
            if os.path.exists(f):
                vr, body = decompile_ai(open(f, 'rb').read())
                if arrive:                        # (R-ARRIVE: his own first idle is the run to his fight node, as the originals' L15 'Far Side Car' men)
                    continue
                hold = Bin('&&', _w, EQ(('AIFunction_GetCurrentEventType',), 'AIEVENT_IDLE'))
                open(f, 'wb').write(compile_ai([If(hold, strip_moves(body), body)], vr))   # (S3/S4: his own script minus moves, not a 10-19 s Idle)
        for s in sqs:
            f = os.path.join(out, 'ai', 'Squad_%d.qvm' % s)
            if os.path.exists(f):
                vr, body = decompile_ai(open(f, 'rb').read())
                open(f, 'wb').write(compile_ai([If(swait, [], body)], vr))
    open(pq + '.sw.tmp', 'wb').write(igiqvm.compile_stmts(st, ver)); os.replace(pq + '.sw.tmp', pq)
    q = os.path.join(out, 'objects.qsc')
    if os.path.exists(q):
        open(q, 'w', encoding='latin1').write(igiqvm.stmts_to_qsc(st))
    log("ssspawnwait: %d run-time containers: each man's first move + his squad wait %d ticks (0.5 s) after his container opened; R-ARRIVE containers %s: %s" % (len(counters), TICKS, sorted(ARRIVED), counters))
    return counters
