"""alarmai - realistic alarm / search / body / reinforcement AI for IGI 2 custom missions (shared by every builder).

How the ORIGINAL game does it (work/alarmai/README.md has the details, work/alarmai/squaddefault.c the engine's own
squad brain = COMMON/ai/squaddefault.qvm decompiled):
  * every soldier script ends in AIFunction_DefaultHandler (COMMON/ai/default.qvm) which passes events to his squad;
  * the squad script (ai/Squad_<id>.qvm) ends in AISquad_DefaultHandler (COMMON/ai/squaddefault.qvm): ALARMON -> Danger
    (= take cover and aim IN PLACE - what the owner saw: 'they stand and aim'), body / death cry -> 'man down' + a 35 m
    distress call + AISquad_TriggerAlarm, detection -> Inquire -> Leapfrog (bounding advance) ...
  * AISquad_TriggerAlarm only works when the AISquad task has an ALARM SWITCH (a Switch task, arg 5) and an AlarmControl
    (arg 6): the nearest man then RUNS to the switch and presses it; the level's alarm variable listens to
    Switch_N.isLastPressed. Our squads had switch -1 = bodies / sightings never raised the alarm.
  * the levels' own squad scripts send squads on alarm to nodes / sweep paths chosen by the AreaActivate the player is in
    (location1/LEVEL6/ai/Squad_704: if AreaActivate_1190.nActive -> AISquad_MoveToNode(90) ...).

What this module builds (Hunt):
  * zones: AreaActivate boxes on Jones over the playable ground; per (graph, zone) two sweep PatrolPaths of 'run to node'
    + 'look at' commands through the zone, in opposite orders (two squads come at him from two sides);
  * squad script per squad: alarm on (ALARMON / IDLE / Danger time-out while the alarm variable is 1) -> run the sweep of
    the zone Jones is in (only zones within reach_m of the squad's home on its own graph component: no unreachable
    targets, bounded paths for the 8192-entry path pool); a body / death cry -> 'man down', a 120 m distress call
    (squads around come and search there), alarm switch; a backup request (a soldier who sees Jones calls for backup) /
    a shot-out camera -> search there; everything else -> the engine's own squaddefault;
  * soldier scripts: patrol / sentry as before but during the alarm IDLE goes to the squad (so it can re-target), and a
    man who sees Jones calls for backup (AIAction_CallForBackup -> AIEVENT_BACKUP_REQUEST around Jones's position);
  * alarm switches: Switch panels (360_18_1) placed on each squad graph's ground; AISquad arg 5 = nearest reachable one.

Usage (builder; full notes in work/alarmai/README.md):
    import alarmai
    H = alarmai.Hunt(m, nid, K.GRAPHS, K.GEDGES, ALARM_VAR, ALARM_CONTROL_ID, LOGIC, pfx='SR')
    H.add_switch(pos, gamma, on='201_01_1', pressed='201_02_1')    # alarm buttons (model must be in the map's bank)
    H.build(open_vars=[GARRISON_VAR])                             # AFTER every squad exists (rewrites m.ai_files)
    m.set(ALARM_VAR, 7, '<old on-rule> || ' + H.switch_expr())     # a pressed button raises the alarm
"""
import os, sys, struct, math, heapq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igiqvm
from igiqvm import Call, Int, Ident

# ------------------------------------------------------------------ structured AI script AST + compiler
BIN = {'&&': 0x22, '||': 0x23, '==': 0x24, '!=': 0x25, '<': 0x26, '<=': 0x27, '>': 0x28, '>=': 0x29, '=': 0x2a,
       '+': 0x19, '-': 0x1a, '*': 0x1b, '/': 0x1c}
BIN_R = {v_: k for k, v_ in BIN.items()}


class Bin:
    def __init__(s, op, a, b): s.op, s.a, s.b = op, a, b


class Not:
    def __init__(s, e): s.e = e


class If:
    def __init__(s, cond, then, els=None): s.cond, s.then, s.els = cond, list(then), (list(els) if els is not None else None)


def E(x):
    """python value -> expression node: int -> Int, 'Name' -> Ident, ('Fn', args..) -> Call"""
    if isinstance(x, (Bin, Not, Call, Int, Ident)):
        return x
    if isinstance(x, bool):
        return Ident('TRUE' if x else 'FALSE')
    if isinstance(x, int):
        return Int(x)
    if isinstance(x, str):
        return Ident(x)
    if isinstance(x, tuple):
        return Call(x[0], [E(a) for a in x[1:]])
    raise TypeError(x)


def C(name, *args):
    return Call(name, [E(a) for a in args])


def AND(*xs):
    e = E(xs[0])
    for x in xs[1:]:
        e = Bin('&&', e, E(x))
    return e


def OR(*xs):
    e = E(xs[0])
    for x in xs[1:]:
        e = Bin('||', e, E(x))
    return e


def EQ(a, b):
    return Bin('==', E(a), E(b))


def _emit_expr(en, e):
    if isinstance(e, Bin):
        _emit_expr(en, e.a); _emit_expr(en, e.b); en.c.append(BIN[e.op])
    elif isinstance(e, Not):
        _emit_expr(en, e.e); en.c.append(0x2e)
    else:
        en.emit(e)


def _emit_block(en, stmts):
    c = en.c
    for s in stmts:
        if isinstance(s, If):
            _emit_expr(en, s.cond)
            c.append(0x04); bf = len(c); c += b'\0\0\0\0'
            _emit_block(en, s.then)
            c.append(0x03); bra = len(c); c += b'\0\0\0\0'
            struct.pack_into('<i', c, bf, len(c) - (bf + 4))
            if s.els is not None:
                _emit_block(en, s.els)
            struct.pack_into('<i', c, bra, len(c) - (bra + 4))
        else:
            _emit_expr(en, s); c.append(0x18)


def compile_ai(stmts, ver=(8, 7)):
    en = igiqvm.Encoder()
    _emit_block(en, stmts)
    en.c.append(0x00)

    def table(items):
        offs, blob = [], bytearray()
        for it in items:
            offs.append(len(blob)); blob += it.encode('latin1') + b'\0'
        return struct.pack('<%dI' % len(offs), *offs), bytes(blob)
    symT, symD = table(en.syms)
    strT, strD = table(en.strs)
    base = 0x40
    o_symT = base; o_symD = o_symT + len(symT); o_strT = o_symD + len(symD); o_strD = o_strT + len(strT)
    o_code = o_strD + len(strD)
    hdr = struct.pack('<4s12I', b'LOOP', ver[0], ver[1], o_symT, o_symD, len(symT), len(symD),
                      o_strT, o_strD, len(strT), len(strD), o_code, len(en.c))
    hdr += b'\0' * (base - len(hdr))
    return hdr + symT + symD + strT + strD + bytes(en.c)


def decompile_ai(data):
    """AI qvm (control flow) -> (ver, [stmts]); compile_ai(decompile_ai(x)[1]) == x for every original (selftest)"""
    ver, syms, strs, code = igiqvm.read_qvm(data)

    def expr(p, end):
        st = []
        while p < end:
            op = code[p]
            if op == 0x07:
                k = struct.unpack_from('<I', code, p + 1)[0]
                offs = struct.unpack_from('<%dI' % k, code, p + 5)
                q = p + 5 + 4 * k
                args = []
                for o in offs:
                    s_, r = expr(o, len(code))
                    assert code[r] == 0x00 and len(s_) == 1
                    args.append(s_[0])
                fn = st.pop()
                st.append(Call(str(fn), args))
                assert code[q] == 0x03
                p = q + 5 + struct.unpack_from('<i', code, q + 1)[0]
            elif op in (0x12, 0x13, 0x14):
                n, f = {0x12: (5, '<I'), 0x13: (2, '<B'), 0x14: (3, '<H')}[op]
                st.append(Ident(syms[struct.unpack_from(f, code, p + 1)[0]])); p += n
            elif op in (0x0e, 0x0f, 0x10):
                n, f = {0x0e: (5, '<I'), 0x0f: (2, '<B'), 0x10: (3, '<H')}[op]
                st.append(igiqvm.Str(strs[struct.unpack_from(f, code, p + 1)[0]])); p += n
            elif op == 0x08: st.append(Int(struct.unpack_from('<i', code, p + 1)[0])); p += 5
            elif op == 0x09: st.append(Int(struct.unpack_from('<b', code, p + 1)[0])); p += 2
            elif op == 0x0a: st.append(Int(struct.unpack_from('<h', code, p + 1)[0])); p += 3
            elif op == 0x0b: st.append(igiqvm.Flt(struct.unpack_from('<f', code, p + 1)[0])); p += 5
            elif op == 0x15: st.append(Int(0)); p += 1
            elif op == 0x16: st.append(Int(1)); p += 1
            elif op in BIN_R:
                b = st.pop(); a = st.pop(); st.append(Bin(BIN_R[op], a, b)); p += 1
            elif op == 0x2e:
                st.append(Not(st.pop())); p += 1
            elif op == 0x2c:
                st.append(igiqvm.Neg(st.pop())); p += 1
            else:
                return st, p
        return st, p

    def block(p, end):
        out = []
        while p < end:
            st, q = expr(p, end)
            if q >= end:
                raise ValueError('dangling expression at %04x' % p)
            op = code[q]
            if op == 0x18:
                assert len(st) == 1, (hex(q), len(st))
                out.append(st[0]); p = q + 1
            elif op == 0x04:
                assert len(st) == 1
                tgt = q + 5 + struct.unpack_from('<i', code, q + 1)[0]
                assert code[tgt - 5] == 0x03, 'if without its BRA at %04x' % q
                j = tgt + struct.unpack_from('<i', code, tgt - 4)[0]
                then = block(q + 5, tgt - 5)
                if j > tgt:
                    out.append(If(st[0], then, block(tgt, j))); p = j
                else:
                    assert j == tgt
                    out.append(If(st[0], then)); p = tgt
            elif op == 0x00 and q == len(code) - 1 and not st:
                p = q + 1
            else:
                raise ValueError('op %02x at %04x' % (op, q))
        return out
    return ver, block(0, len(code))


def to_text(stmts, ind=''):
    def ex(e):
        if isinstance(e, Bin): return '(%s %s %s)' % (ex(e.a), e.op, ex(e.b))
        if isinstance(e, Not): return '!' + ex(e.e)
        if isinstance(e, Call): return '%s(%s)' % (e.name, ', '.join(ex(a) for a in e.args))
        if isinstance(e, igiqvm.Str): return repr(str(e))
        return str(e)
    out = []
    for s in stmts:
        if isinstance(s, If):
            out.append('%sif %s {' % (ind, ex(s.cond)))
            out.append(to_text(s.then, ind + '  '))
            if s.els is not None:
                out.append('%s} else {' % ind); out.append(to_text(s.els, ind + '  '))
            out.append(ind + '}')
        else:
            out.append(ind + ex(s) + ';')
    return '\n'.join(x for x in out if x)


# ------------------------------------------------------------------ the alarm / hunt system
def EV(n):
    return 'AIEVENT_' + n


def ST(n):
    return 'AISquadState_' + n


# (squaddefault keeps them in AISquad_nSquadState / AISquad_nEvent, but an assignment to those from a LEVEL script does
#  nothing - traced in game 10-16: the conditions saw stale values; the levels' own scripts call the getters every time)
SQ_S, SQ_E = ('AISquad_GetState',), ('AISquad_GetEvent',)


def _in(var, *names):
    return OR(*[EQ(var, n) for n in names])


class Hunt:
    """see the module doc. All distances in metres; world units = 4096 per metre."""
    M = 4096.0

    def __init__(s, m, nid, graphs, edges, alarm_var, alarm_control, parent, pfx='AI', cell_m=40.0, reach_m=260.0,
                 backup_m=110.0, distress_m=110.0, phase_s=14.0, run_m=160.0):
        s.m, s.nid, s.G, s.E = m, nid, graphs, edges
        s.alarm_var, s.alarm_control, s.parent, s.pfx = alarm_var, alarm_control, parent, pfx
        s.cell, s.reach, s.backup, s.distress, s.phase_s, s.run = cell_m, reach_m, backup_m, distress_m, phase_s, run_m
        s.switches = []                                     # (id, pos)
        s.switch_graph = {}                                 # id -> the AI graph its guard stands on (None = found in build)
        s.report = []

    # ---- alarm buttons the guards run to (originals: Switch 360_18_1 / 334_01_1 / 350_05_1; any button model of the map)
    def add_switch(s, pos, gamma, on='201_01_1', pressed='201_02_1', name='alarm button', sound='button_1', graph=None):
        """graph = the AI graph id the guard who presses it stands on (10-29: optional; None = the ONLY graph with a node
        within 3 m / 2.5 m, worked out in build(); near several graphs = ambiguous: no squad). Only that graph's squads
        get the button."""
        from mission_lib import T
        i = s.nid()
        s.m.add_child(s.parent, T(i, 'Switch', '%s %s' % (s.pfx, name), *[float(c) for c in pos], 0.0, 0.0, float(gamma), '1',
                                  False, sound, on, pressed, on, pressed, pressed, False, 'STATUSSCREEN:action_pressbutton.spr'))
        s.switches.append((i, tuple(float(c) for c in pos)))
        if not hasattr(s, 'switch_graph'):                 # (a Hunt made without __init__)
            s.switch_graph = {}
        s.switch_graph[i] = graph
        return i

    def _switch_graphs(s):
        """10-29 (SHOBI rework, tw-cedar's root cause of the start crash igi2.exe+0xfabc3 READ 0x244): a squad was given an
        alarm button that stands on ANOTHER AI graph (Cedar's lab button: graphs 4 and 7 both have a node 1.75 m from it,
        through the hut wall). Each button belongs to ONE graph: the one given to add_switch(graph=); else the ONLY graph
        with a node within the old 3 m / 2.5 m test. A button near nodes of several graphs is AMBIGUOUS: no squad gets it
        (Jones can still press it) - pass graph= to add_switch. -> {switch id: graph id or None}"""
        M = s.M
        out, s.SWITCH_AMBIGUOUS = {}, {}
        for sw, p in s.switches:
            g0 = getattr(s, 'switch_graph', {}).get(sw)
            if g0 is not None:
                out[sw] = g0
                continue
            near = []
            for g, nodes in s.G.items():
                if not nodes:
                    continue
                n = min(nodes, key=lambda n_: math.dist(n_['pos'], p))
                if math.hypot(n['pos'][0] - p[0], n['pos'][1] - p[1]) <= 3.0 * M and abs(n['pos'][2] - p[2]) <= 2.5 * M:
                    near.append(g)
            out[sw] = near[0] if len(near) == 1 else None
            if len(near) > 1:
                s.SWITCH_AMBIGUOUS[sw] = sorted(near)
        return out

    def switch_expr(s):
        """OR this into the alarm variable's on-expression: a guard (or Jones) pressing a button raises the alarm"""
        return ' || '.join('Switch_%d.isLastPressed' % i for i, _ in s.switches) or '0'

    # ---- graph helpers
    def _dist(s, g, src, locked=None):
        nodes = {n['id']: n for n in s.G[g]}
        adj = {}
        for a, b in s.E[g]:
            if a in nodes and b in nodes and s._ok(nodes[a], locked) and s._ok(nodes[b], locked):
                adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
        d = {src: 0.0}
        q = [(0.0, src)]
        lim = s.reach * s.M * 1.25
        while q:
            du, u = heapq.heappop(q)
            if du > d.get(u, 1e30) or du > lim:
                continue
            for w in adj.get(u, ()):
                nd = du + math.dist(nodes[u]['pos'], nodes[w]['pos'])
                if nd < d.get(w, 1e30):
                    d[w] = nd; heapq.heappush(q, (nd, w))
        return d

    def _ok(s, n, locked=None):
        """a node the hunters may cross: any floor node, and door nodes of doors that are open (during the alarm; or,
        locked=s.locked_pre, before it)"""
        if not n['crit']:
            return True
        return all(math.hypot(n['pos'][0] - p[0], n['pos'][1] - p[1]) > 3.0 * s.M or abs(n['pos'][2] - p[2]) > 3.0 * s.M
                   for p in (s.locked if locked is None else locked))

    def _locked_doors(s, open_vars):
        """doors that may be shut during the alarm: a lock rule (arg 18) unless their unlock rule (arg 19) names one of
        open_vars (variables that go to 1 with the alarm, e.g. Sirocco's 'garrison called out')"""
        from qast import lit
        out = []
        for d in s.m.find('Door'):
            a = s.m.byid[d].args
            lock, unlock = str(lit(a[18])).strip(), str(lit(a[19]))
            if lock in ('', '0', 'FALSE'):
                continue
            if any('EditVariable_%d.' % v_ in unlock for v_ in open_vars):
                continue
            out.append(tuple(float(lit(a[3 + k])) for k in range(3)))
        return out

    def _squads(s, exclude):
        from qast import lit
        out = []
        for sid in sorted(s.m.find('AISquad')):
            t = s.m.byid[sid]
            if sid in exclude or lit(t.args[4]) != 'AIType_Offensive':
                continue
            mem = []
            for k in s.m.children(sid):
                if lit(k.args[1]) != 'HumanSoldier':
                    continue
                ai = [a for a in k.args if isinstance(a, Call) and a.name == 'Task_New' and lit(a.args[1]) == 'HumanAI']
                if ai:
                    mem.append(dict(hid=lit(k.args[0]), aid=lit(ai[0].args[0]), graph=lit(ai[0].args[5]),
                                    pos=tuple(float(lit(k.args[3 + j])) for j in range(3))))
            if not mem:
                continue
            if all('DRAGUNOV' in str(lit(s.m.byid[mm['hid']].args[9])) for mm in mem):
                continue                                    # (snipers keep their perches)
            g = mem[0]['graph']
            if g not in s.G or len(s.G[g]) < 8:            # (tower platforms / vehicle graphs: nowhere to hunt)
                continue
            out.append(dict(sid=sid, name=lit(t.args[2]), graph=g, mem=mem, alarmed=lit(t.args[6]) != -1))
        return out

    # ---- build everything
    def build(s, exclude=(), only_alarmed=True, open_vars=(), gf='GAME_FREQUENCY', cry_alarm=True, hold=(), loud_alarm=False, react_fight=(), fight_gate=False, engage='HoldArea',
              death_cover=None, dead_hold=False):
        """squads = every Offensive AISquad with an AlarmControl (only_alarmed) on a real graph, minus `exclude`.
        open_vars: EditVariable ids whose doors open with the alarm (their door nodes count as passable)
        cry_alarm=False (Cedar 10-31, owner 'kill one and 100 come'): a DEATH_CRY only sends the squad to search, no man-down
        distress call and no alarm run; a body seen (FRIENDLYDETECTION / FRIENDLY_DYING) still raises it. Default = old behaviour
        hold: squad ids that keep their alarm button + body / backup reactions but do NOT join the hunt (on the alarm they
        take cover at their post, the engine default - Cedar 10-31: only the response squads come)
        loud_alarm (Sandstorm 11-06, owner 64): a squad that hears a shot or a blast, is hit, or sees a body or a friend dying raises the alarm in ANY state until the alarm is on;
        the old branches only took a body in Idle / Move / Patrol, so a squad already searching or in Danger never reported, and nothing loud ever did
        death_cover (N8 first cut, ss-life 11-17; None = follow fight_gate): a squad in Idle / Move / Patrol that sees or hears a friend die goes to DANGER (the engine's
        own cover: every man takes the nearest free cover within 10 m from the danger, kneels or sweeps; Danger's timeout then moves them: hunt, or the default's
        MoveSearchInDirection) instead of SearchArea (a walk in the open). That is the originals' answer, COMMON squaddefault Offensive SD:26-30
        dead_hold (N15 ss-life 11-17, default off): once Jones is dead every hunting squad holds its area (HoldArea, the state fight_gate / engage uses) on its next
        event and gets no further order. Without it the hunt zone that holds his body stays active, so squads keep being sent to its two nodes every phase_s and
        walk to and fro across the body under the death camera (ss_full2 9:20, ss_full3 10:44). No task id; the reader HumanPlayer_0.isDead is new in a squad
        script (no original ai script reads HumanPlayer; objects.qvm conditions do): prove it in an A/B take before it ships"""
        death_cover = fight_gate if death_cover is None else death_cover
        grief = ST('Danger') if death_cover else ST('SearchArea')
        from mission_lib import T
        from qast import lit
        M = s.M
        s.locked = s._locked_doors(set(open_vars) | {s.alarm_var})
        s.locked_pre = s._locked_doors(())                 # (a guard runs to the button BEFORE the alarm opens anything -
        if os.environ.get('ALARMAI_TRACE'):                 #  reviewer 10-16: Sirocco's garrison button was sealed off)
            print('*' * 70)
            print('*** ALARMAI_TRACE: breakpoint marker calls in the squad scripts - TEST ONLY, never ship ***')
            print('*' * 70)
        sqs = [q for q in s._squads(set(exclude)) if q['alarmed'] or not only_alarmed]
        golden = math.pi * (3 - math.sqrt(5))
        for k, q in enumerate(sqs):
            g = q['graph']
            c = [sum(mm['pos'][j] for mm in q['mem']) / len(q['mem']) for j in range(3)]
            ok = [n for n in s.G[g] if not n['crit']]
            home = min(ok, key=lambda n: math.dist(n['pos'], c))
            q['home'] = home['id']
            q['dist'] = s._dist(g, home['id'])
            q['angle'] = k * golden
        cw = s.cell * M
        cells = {}
        for q in sqs:
            byid = {n['id']: n for n in s.G[q['graph']]}
            for nid_, d in q['dist'].items():
                if d <= s.reach * M:
                    p = byid[nid_]['pos']
                    cells.setdefault((math.floor(p[0] / cw), math.floor(p[1] / cw)), []).append(p[2])
        zones = []
        for key, zs in sorted(cells.items()):
            zs = sorted(zs)
            band = [zs[0]]
            for z in zs[1:] + [None]:
                if z is not None and z - band[-1] < 6.0 * M:
                    band.append(z); continue
                if len(band) >= 2:
                    zones.append(dict(key=key, lo=band[0], hi=band[-1],
                                      c=((key[0] + 0.5) * cw, (key[1] + 0.5) * cw, (band[0] + band[-1]) / 2 + 1.0 * M)))
                if z is not None:
                    band = [z]
        for z in zones:
            z['id'] = s.nid()
            s.m.add_child(s.parent, T(z['id'], 'AreaActivate', '%s hunt zone %d,%d' % (s.pfx, z['key'][0], z['key'][1]),
                                      *[float(c) for c in z['c']], 0.0, 0.0, 0.0, cw, cw,      # (FULL extents: the
                                      float((z['hi'] - z['lo']) + 8.0 * M), 'CRITERIA_HUMAN0'))  #  originals' zones abut so)
        s.ZONES = zones
        # the search clock: a squad that reached Jones's zone without seeing him goes on to its other node every phase_s
        s.CLOCK, s.PHASE = s.nid(), s.nid()
        s.m.add_child(s.parent, T(s.CLOCK, 'LevelTimer', '%s hunt search clock' % s.pfx, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, '1',
                                  'LevelTimer_%d.nTick > %d * %s' % (s.CLOCK, int(2 * s.phase_s), gf), False))
        s.m.add_child(s.parent, T(s.PHASE, 'EditVariable', '%s hunt search phase' % s.pfx, 0.0, 0.0, 0.0, 0,
                                  'LevelTimer_%d.nTick < %d * %s' % (s.CLOCK, int(s.phase_s), gf),
                                  'LevelTimer_%d.nTick > %d * %s' % (s.CLOCK, int(s.phase_s), gf)))
        ALARM = EQ('EditVariable_%d.nValue' % s.alarm_var, 1)
        PH = EQ('EditVariable_%d.nValue' % s.PHASE, 1)
        n_sw = 0
        sw_graph = s._switch_graphs()                       # (10-29: a button is only for squads on ITS graph)
        for sw, p in s.switches:                            # (review: an explicit graph= the button is not near = dropped)
            g0 = getattr(s, 'switch_graph', {}).get(sw)
            if g0 is None:
                continue
            nodes = s.G.get(g0) or []
            n = min(nodes, key=lambda n_: math.dist(n_['pos'], p)) if nodes else None
            if n is None or math.hypot(n['pos'][0] - p[0], n['pos'][1] - p[1]) > 3.0 * M or abs(n['pos'][2] - p[2]) > 2.5 * M:
                print('alarmai: WARNING alarm switch %d was given graph=%s but %s - no squad gets it' % (
                    sw, g0, 'that graph does not exist' if n is None else 'its nearest node there is %.1f m away (3 m / 2.5 m test)'
                    % (math.dist(n['pos'], p) / M)))
        for sw, gg in sorted(sw_graph.items()):
            if gg is None and sw in s.SWITCH_AMBIGUOUS:
                print('alarmai: WARNING alarm switch %d is within 3 m of nodes of graphs %s - AMBIGUOUS, given to no squad '
                      '(pass graph=<id> to add_switch; a cross-graph button crashes igi2.exe+0xfabc3)' % (sw, s.SWITCH_AMBIGUOUS[sw]))
            elif gg is None:
                print('alarmai: WARNING alarm switch %d is not within 3 m of any AI graph node - no squad can press it' % sw)
        s.SWITCH_GRAPH = sw_graph
        for q in sqs:
            g = q['graph']
            byid = {n['id']: n for n in s.G[g]}
            reach = sorted(i for i, d in q['dist'].items() if d <= s.reach * M)
            chain = []
            for z in zones:
                cand = [byid[i] for i in reach if not byid[i]['crit'] and (math.floor(byid[i]['pos'][0] / cw), math.floor(byid[i]['pos'][1] / cw)) == z['key']
                        and z['lo'] <= byid[i]['pos'][2] <= z['hi']]
                if not cand:
                    continue
                u = (math.cos(q['angle']), math.sin(q['angle']))     # each squad comes at the zone from its own side
                a = max(cand, key=lambda n: (n['pos'][0] - z['c'][0]) * u[0] + (n['pos'][1] - z['c'][1]) * u[1])
                b = max(cand, key=lambda n: math.dist(n['pos'], a['pos']))
                if math.dist(a['pos'], b['pos']) < 10 * M:
                    b = a
                chain.append((z['id'], a['id'], b['id']))
            if q['sid'] in hold:                            # (a post squad: no zone moves, ALARMON -> default Danger)
                chain = []
            q['zones'] = chain
            hunt = [C('AISquad_DefaultHandler')]
            for zid, a, b in reversed(chain):
                hunt = [If(E('AreaActivate_%d.nActive' % zid),
                           [If(PH, [C('AISquad_MoveToNode', a)], [C('AISquad_MoveToNode', b)])], hunt)]
            cry_branch = [If(AND(*([ALARM, _in(SQ_S, ST('Idle'), ST('Danger')),
                                    _in(SQ_E, EV('ALARMON'), EV('IDLE'), EV('DANGERSTATETIMEOUT'), EV('CAMERAALARMUPDATE'))]
                                   + ([Not(C('AISquad_HasTarget'))] if fight_gate else []))),   # (N8 ss-life 11-15: a squad that has Jones fights, it is not re-sent)
                          hunt, [C('AISquad_DefaultHandler')])]
            if not cry_alarm:                               # (a death cry: the squad searches, nobody runs to the button)
                cry_branch = [If(AND(EQ(SQ_E, EV('DEATH_CRY')), _in(SQ_S, ST('Idle'), ST('Move'), ST('Patrol'))),
                                 [C('AISquad_SwitchState', grief, 'AIVoice_TakeCover' if death_cover else 'AIVoice_SearchArea')], cry_branch)]
            script = [If(_in(SQ_E, EV('BACKUP_REQUEST'), EV('DESTROYED_CAMERA')),
                         [If(AND(_in(SQ_S, ST('Idle'), ST('Move'), ST('Patrol'), ST('Danger')), Not(C('AISquad_ReceiverHasTarget'))),
                             [C('AISquad_PlaySoundAtReceiversPos', 'AIVoice_HurryUp'),
                              C('AISquad_SwitchState', ST('SearchArea'), 'AIVoice_SearchArea')])],
                         [If(AND(_in(SQ_E, *[EV(e_) for e_ in ('FRIENDLYDETECTION', 'FRIENDLY_DYING', 'DEATH_CRY')[:3 if cry_alarm else 2]]),
                                 _in(SQ_S, ST('Idle'), ST('Move'), ST('Patrol'))),
                             [C('AISquad_PlaySoundAtReceiversPos', 'AIVoice_ManDown'),
                              C('AISquad_TriggerEvent', EV('DISTRESSCALL'), int(s.distress)),
                              C('AISquad_SwitchState', grief), C('AISquad_TriggerAlarm')],
                             cry_branch)])]
            if q['sid'] in react_fight:                     # (S16 ss-life 11-15 'he kills one and the others do not react': men who came for Jones do not 'search the area'
                script = [If(AND(_in(SQ_E, *[EV(e_) for e_ in ('FRIENDLY_DYING', 'DEATH_CRY', 'FRIENDLYDETECTION', 'TAKINGDAMAGE', 'GUNSHOT', 'GUNSHOTMISS')]),   #  after a death:
                                 Not(C('AISquad_ReceiverHasTarget'))),                                                                                    #  they turn to it and
                             [C('AISquad_PlaySoundAtReceiversPos', 'AIVoice_ManDown'), C('AISquad_ReceiverLookAtEvent'),                                   #  push that way, the
                              C('AISquad_SwitchState', ST('MoveSearchInDirection'))], script)]                                                             #  engine default's answer)
            if fight_gate:                                  # (N8 ss-life 11-15, PLANDIR/N8_COVER_AI.md R1: men walked up to Jones firing and knelt in the open to reload:
                script = [If(AND(ALARM, EQ(SQ_S, ST('Move')), C('AISquad_HasTarget'),        #  the hunt re-ordered MoveToNode over the fight. A moving squad under fire
                                 _in(SQ_E, EV('ENEMYDETECTION'), EV('TAKINGDAMAGE'), EV('GUNSHOTMISS'), EV('SEENSOMETHING'))),   #  holds its area (the originals' L15 701 / L32 704 call)
                             [C('AISquad_PlaySoundAtReceiversPos', 'AIVoice_Engaging'), C('AISquad_SwitchState', ST(engage)), C('AISquad_TriggerAlarm')], script)]
            if loud_alarm:
                # (fg4, gf2: the path pool fell to 19 of 8192 on the first rifle shots: a DISTRESSCALL per shot heard sent every squad around searching at once. Only a body calls the others; a noise just sends one man to the button)
                script = [If(AND(Not(ALARM), _in(SQ_E, EV('FRIENDLYDETECTION'), EV('FRIENDLY_DYING'))),
                             [C('AISquad_PlaySoundAtReceiversPos', 'AIVoice_RaiseAlarm'), C('AISquad_TriggerEvent', EV('DISTRESSCALL'), int(s.distress)), C('AISquad_TriggerAlarm')]),
                          If(AND(Not(ALARM), _in(SQ_E, *[EV(e_) for e_ in ('EXPLOSION', 'GUNSHOT', 'GUNSHOTMISS', 'FRIENDLY_GUNSHOT', 'TAKINGDAMAGE', 'GRENADELAND')])),
                             ([C('AISquad_TriggerEvent', EV('DISTRESSCALL'), int(s.distress))] if os.environ.get('SS_SHOTCALL') else []) + [C('AISquad_TriggerAlarm')])] + script
            if dead_hold:                                   # (N15: Jones is dead: hold where you are, no hunt order, no search walk over his body)
                script = [If(E('HumanPlayer_0.isDead'), [If(Not(EQ(SQ_S, ST('HoldArea'))), [C('AISquad_SwitchState', ST('HoldArea'))])], script)]
            if os.environ.get('ALARMAI_TRACE'):           # debug: breakpoints on 0x4a5310 (every event) / 0x4a5290 (hunt branch)
                script[0:0] = [C('AISquad_GetEventSpecificInt32'), If(ALARM, [C('AISquad_GetCurrentPatrolID')])]
                if chain:
                    script.insert(2, If(OR(*[E('AreaActivate_%d.nActive' % z_[0]) for z_ in chain] + [Int(0)]),
                                        [C('AISquad_GetDistanceToEvent')]))
            s.m.ai_files['Squad_%d' % q['sid']] = compile_ai(script)
            for mm in q['mem']:                             # soldiers: backup call on sight; in the alarm IDLE goes to the squad
                key = str(mm['aid'])
                old = s.m.ai_files.get(key)
                if not isinstance(old, (bytes, bytearray)):
                    continue
                s.m.ai_files[key] = s.soldier(bytes(old))
            best = None                                     # alarm switch: the nearest reachable on this squad's graph
            pre = s._dist(g, q['home'], s.locked_pre) if s.switches else {}   # (with the doors as they are before the alarm)
            for sw, p in s.switches:
                if sw_graph.get(sw) != g:                  # (10-29: another graph's button = the start crash 0xfabc3)
                    n = min(s.G[g], key=lambda n_: math.dist(n_['pos'], p))
                    if math.hypot(n['pos'][0] - p[0], n['pos'][1] - p[1]) <= 3.0 * M and abs(n['pos'][2] - p[2]) <= 2.5 * M:
                        print('alarmai: switch %d (graph %s) is within 3 m of graph %d (squad %s) - NOT given to it '
                              '(cross-graph button = crash igi2.exe+0xfabc3)' % (sw, sw_graph.get(sw), g, q['name']))
                    continue
                n = min(s.G[g], key=lambda n_: math.dist(n_['pos'], p))
                if math.hypot(n['pos'][0] - p[0], n['pos'][1] - p[1]) > 3.0 * M or abs(n['pos'][2] - p[2]) > 2.5 * M:
                    continue
                d = pre.get(n['id'])
                if d is not None and d <= s.reach * M and (best is None or d < best[1]):
                    best = (sw, d)
            if best:
                s.m.set(q['sid'], 5, best[0])
                n_sw += 1
            s.m.set(q['sid'], 6, s.alarm_control)
            run = max(float(lit(s.m.byid[q['sid']].args[7 + 1])), s.run, (best[1] / M + 15.0) if best else 0.0)
            s.m.set(q['sid'], 8, int(math.ceil(run)))
            s.report.append('%s (squad %d, graph %d): %d zones, alarm switch %s' % (
                q['name'], q['sid'], g, len(chain), best[0] if best else '-'))
        s.SQUADS = sqs
        bad = [(q['name'], q['graph'], lit(s.m.byid[q['sid']].args[5])) for q in sqs
               if lit(s.m.byid[q['sid']].args[5]) in sw_graph and sw_graph[lit(s.m.byid[q['sid']].args[5])] != q['graph']]
        assert not bad, ('alarmai: squads with an alarm switch of ANOTHER graph (crash igi2.exe+0xfabc3 at the start)', bad)
        print('alarmai: %d hunting squads, %d zones (%.0f m cells), %d with an alarm switch, search clock %d' % (
            len(sqs), len(zones), s.cell, n_sw, s.PHASE))
        return sqs

    def soldier(s, data, backup=True):
        """wrap a soldier script: ENEMYDETECTION -> call for backup (AIEVENT_BACKUP_REQUEST around Jones) + default;
        during the alarm a PATROL script's IDLE goes to the squad instead of walking the patrol again"""
        _, body = decompile_ai(data)
        ev = C('AIFunction_GetCurrentEventType')
        ALARM = EQ('EditVariable_%d.nValue' % s.alarm_var, 1)
        inner = body
        if 'AIAction_Patrol' in to_text(body):
            inner = [If(AND(EQ(ev, EV('IDLE')), ALARM), [C('AIAction_Idle', 'AIACTIONFLAG_NONE'), C('AIFunction_PassEventOnToSquad')],
                        body)]
        if not backup:
            return compile_ai(inner)
        return compile_ai([If(EQ(ev, EV('ENEMYDETECTION')), [C('AIAction_CallForBackup', int(s.backup)), C('AIFunction_DefaultHandler')],
                              inner)])


def selftest():
    import glob
    G = r'C:/Users/1qdeath/Games/IGI2/app/'
    files = sorted(glob.glob(G + 'MISSIONS/location*/*/ai/*.qvm')) + sorted(glob.glob(G + 'COMMON/ai/*default.qvm'))
    bad = []
    for f in files:
        d = open(f, 'rb').read()
        try:
            ver, st = decompile_ai(d)
            if compile_ai(st, ver) != d:
                bad.append(f)
        except Exception as e:
            bad.append('%s (%s)' % (f, e))
    print('alarmai selftest: %d / %d original AI scripts round-trip byte for byte' % (len(files) - len(bad), len(files)))
    for b in bad[:10]:
        print('  FAIL', b)
    return not bad


if __name__ == '__main__':
    sys.exit(0 if selftest() else 1)
