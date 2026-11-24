"""ssmovewait.py (G43 11-14, orchestrator): men created WITH THE LEVEL whose IDLE branch gives a move order (Patrol / WalkToNode) stand on their spot
until the latch EditVariable <var> goes to 1 (2 s after the intro ends, set by the builder), so the intro films them at their posts and the move
never lands in the frames around 'player live'. Until then their IDLE stands in the engine idle (ss-life 11-15; was a look-around). Runs after m.write on out/ai/<HumanAI id>.qvm.

    add_latch(m, T, nid, LOGIC, after_timer_id) -> var id          (builder, before m.write)
    apply(out, squad_names, var_id, log=print) -> patched AI ids    (builder, after m.write)"""
import os
import igiqvm, alarmai
from alarmai import If, C, EQ, compile_ai, decompile_ai
from qast import lit

MOVES = ('AIAction_Patrol', 'AIAction_WalkToNode', 'AIAction_RunToNode')


def add_latch(m, T, nid, parent, after_timer):
    v = nid()
    m.add_child(parent, T(v, 'EditVariable', 'SS G43 posts may move (2 s after the intro)', 0.0, 0.0, 0.0, 0,
                          'EditVariable_%d.nValue == 0 && LevelTimer_%d.nTick > 2 * GAME_FREQUENCY' % (v, after_timer), ''))
    return v


def _has_move(stmts):
    for s in stmts:
        if isinstance(s, If):
            if _has_move(s.then) or (s.els and _has_move(s.els)):
                return True
        elif getattr(s, 'name', '') in MOVES:
            return True
    return False


def _is_idle(cond):
    t = alarmai.to_text([If(cond, [])])
    return 'AIFunction_GetCurrentEventType() == AIEVENT_IDLE' in t.splitlines()[0]


def _wrap(stmts, var):
    """the innermost IDLE If whose branch holds a move: its then-block runs only when the latch is 1, else the engine idle"""
    n = 0
    for s in stmts:
        if isinstance(s, If):
            if _is_idle(s.cond) and _has_move(s.then):
                import ssspawnwait
                s.then = [If(EQ('EditVariable_%d.nValue' % var, 1), s.then,
                             ssspawnwait.strip_moves(s.then))]   # (S3/S4 ss-life 11-15: was an aimed LookAround, then a 10-19 s Idle; now his own branch minus moves: talkers talk, walkers Wait(1, 1))
                n += 1
            else:
                n += _wrap(s.then, var)
                if s.els:
                    n += _wrap(s.els, var)
    return n


def apply(out, squads, var, log=print):
    v, st = igiqvm.decompile(open(os.path.join(out, 'objects.qvm'), 'rb').read())
    ai_ids = []

    def walk(x, insq=False, insol=False):
        if isinstance(x, list):
            for y in x:
                walk(y, insq, insol)
        elif hasattr(x, 'args'):
            if getattr(x, 'name', '') == 'Task_New':
                ty, nm = str(lit(x.args[1])), str(lit(x.args[2]))
                sq = insq or (ty == 'AISquad' and nm in squads)
                if ty == 'HumanAI' and insq and insol:
                    ai_ids.append(int(lit(x.args[0])))
                for a in x.args:
                    walk(a, sq, insol or (sq and ty == 'HumanSoldier'))
                return
            for a in x.args:
                walk(a, insq, insol)
    walk(st)
    done = []
    for a in ai_ids:
        f = os.path.join(out, 'ai', '%d.qvm' % a)
        if not os.path.exists(f):
            continue
        ver, body = decompile_ai(open(f, 'rb').read())
        k = _wrap(body, var)
        if k:
            open(f, 'wb').write(compile_ai(body, ver))
            done.append(a)
    log('ssmovewait: %d AI scripts of %s wait for EditVariable_%d before their IDLE move: %s' % (len(done), list(squads), var, done))
    assert done or not ai_ids, 'ssmovewait: nothing patched'   # (a noenemies variant has no men to patch)
    return done
