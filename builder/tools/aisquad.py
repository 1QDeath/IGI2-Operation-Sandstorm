"""aisquad - structured IGI 2 AI scripts (soldier ai/<HumanAI id>.qvm and squad ai/Squad_<id>.qvm) with nested if / else,
&& / || and comparisons, encoded exactly like the originals (selftest: Mission 15 Squad_721 + Squad_3744 byte for byte).

tools/aiscript.py only writes flat 'event -> calls' chains; the originals' SQUAD scripts are nested (work/aidis.py):

    location1/LEVEL5/ai/Squad_721.qvm   if (GetState() == Idle) { if (GetEvent() == ALARMON) MoveToNode(430); }
                                        else DefaultHandler();
    (squad hunting itself lives in tools/alarmai.py - shared, with reach limits and alarm buttons)
    location1/LEVEL6/ai/Squad_704.qvm   ... on ALARMON: if (AreaActivate_1190.nActive == TRUE) MoveToNode(90); if (..1191..)
                                        MoveToNode(236); ...  = the squad runs to where the player IS (Mission 16)
    location1/LEVEL5/ai/Squad_3744.qvm  if Idle and the event is a gunshot / death cry / wounded cry / damage / miss /
                                        explosion: SwitchState(HoldArea)

Language (Python tuples):
    stmt  = ('call', name, *args)                     args: int, 'IDENT' (str), or a nested ('call', ...) expression
          | ('if', cond, [stmts], [stmts] or None)
    cond  = ('eq', x, y) | ('and', a, b) | ('or', a, b) | x       x/y: int, 'IDENT', ('call', name, *args) (an expression)
    script(stmts) -> qvm bytes
Helpers: ev(name) / squad_ev(name) / state(name) / any_of(...) build the usual conditions.
Encoding (v8.7, from the originals): a statement = expression + POP; if = cond, BF else, then, BRA end, else; an if with no
else still ends with 'BRA +0'; == 0x24, && 0x22, || 0x23; 0/1 = PUSH0 / PUSH1; symbols numbered in order of first use.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igiqvm
from igiqvm import Call, Int, Ident

EQ, AND, OR, BF, BRA, POP = 0x24, 0x22, 0x23, 0x04, 0x03, 0x18


def _expr(x):
    if isinstance(x, tuple) and x and x[0] == 'call':
        return Call(x[1], [_expr(a) for a in x[2:]])
    if isinstance(x, bool):
        return Ident('TRUE' if x else 'FALSE')
    if isinstance(x, int):
        return Int(x)
    if isinstance(x, str):
        return Ident(x)
    raise TypeError(x)


class _Asm:
    def __init__(self):
        self.en = igiqvm.Encoder()
        self.c = self.en.c

    def value(self, x):
        self.en.emit(_expr(x))

    def cond(self, k):
        if isinstance(k, tuple) and k and k[0] in ('eq', 'and', 'or'):
            self.cond(k[1]) if k[0] != 'eq' else self.value(k[1])
            self.cond(k[2]) if k[0] != 'eq' else self.value(k[2])
            self.c.append({'eq': EQ, 'and': AND, 'or': OR}[k[0]])
        else:
            self.value(k)

    def stmts(self, ss):
        for s in ss:
            self.stmt(s)

    def stmt(self, s):
        c = self.c
        if s[0] == 'call':
            self.value(s); c.append(POP)
        elif s[0] == 'if':
            _, k, then, els = (list(s) + [None])[:4]
            self.cond(k)
            c.append(BF); bf = len(c); c += b'\0\0\0\0'
            self.stmts(then)
            c.append(BRA); bra = len(c); c += b'\0\0\0\0'
            struct.pack_into('<i', c, bf, len(c) - (bf + 4))
            if els:
                self.stmts(els)
            struct.pack_into('<i', c, bra, len(c) - (bra + 4))
        else:
            raise ValueError(s)

    def finish(self, ver=(8, 7)):
        self.c.append(0x00)
        en = self.en

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
                          o_strT, o_strD, len(strT), len(strD), o_code, len(self.c))
        hdr += b'\0' * (base - len(hdr))
        return hdr + symT + symD + strT + strD + bytes(self.c)


def script(stmts):
    a = _Asm()
    a.stmts(stmts)
    return a.finish()


# ------------------------------------------------------------------------------------------------ condition helpers
def ev(name):
    """soldier script: the current event is `name`"""
    return ('eq', ('call', 'AIFunction_GetCurrentEventType'), name)


def squad_ev(name):
    return ('eq', ('call', 'AISquad_GetEvent'), name)


def state(name):
    return ('eq', ('call', 'AISquad_GetState'), name)


def any_of(conds):
    k = conds[0]
    for c in conds[1:]:
        k = ('or', k, c)
    return k


def var_is(var, value):
    """mission variable test as the originals write it: EditVariable_103.nValue == 1 / AreaActivate_1190.nActive == TRUE"""
    return ('eq', var, value)


# ------------------------------------------------------------------------------------------------ scripts used by builders
ALERT_EVENTS = ('AIEVENT_GUNSHOT', 'AIEVENT_FRIENDLY_GUNSHOT', 'AIEVENT_DEATH_CRY', 'AIEVENT_WOUNDED_CRY', 'AIEVENT_TAKINGDAMAGE',
                'AIEVENT_GUNSHOTMISS', 'AIEVENT_EXPLOSION')


def guard(profile, idle=(), dark_var=None, dark_cone=(30, 35)):
    """a soldier: profile = aiscript.HARD-style dict (view cones, accuracy) set on CREATE; idle = calls for AIEVENT_IDLE
    (patrol / look around); dark_var = 'EditVariable_N.nValue' that is 1 in the blackout: while it is, his IDLE view cone
    shrinks to dark_cone (deg, m) - the camp lamps are out - and grows back to the profile's when the power returns."""
    setup = [('call', 'AIFunction_DefaultHandler')]
    if profile:
        p = profile
        setup += [('call', 'AIFunction_SetIdleViewCone1Alpha', p['idle'][0]), ('call', 'AIFunction_SetIdleViewCone1Length', p['idle'][1]),
                  ('call', 'AIFunction_SetInvestigateViewCone1Alpha', p['investigate'][0]),
                  ('call', 'AIFunction_SetInvestigateViewCone1Length', p['investigate'][1]),
                  ('call', 'AIFunction_SetCombatViewCone1Alpha', p['combat'][0]), ('call', 'AIFunction_SetCombatViewCone1Length', p['combat'][1]),
                  ('call', 'AIFunction_SetMinRangeAccuracy', p['acc'][0]), ('call', 'AIFunction_SetMaxRangeAccuracy', p['acc'][1]),
                  ('call', 'AIFunction_SetAccuracyMaxRange', p['acc'][2])]
    idle_calls = []
    if dark_var and profile:
        idle_calls.append(('if', var_is(dark_var, 1),
                           [('call', 'AIFunction_SetIdleViewCone1Alpha', dark_cone[0]), ('call', 'AIFunction_SetIdleViewCone1Length', dark_cone[1])],
                           [('call', 'AIFunction_SetIdleViewCone1Alpha', profile['idle'][0]),
                            ('call', 'AIFunction_SetIdleViewCone1Length', profile['idle'][1])]))
    idle_calls += [('call',) + tuple(c) for c in idle]
    tree = [('if', ev('AIEVENT_CREATE'), setup,
             [('if', ev('AIEVENT_IDLE'), idle_calls, [('call', 'AIFunction_DefaultHandler')])] if idle_calls else
             [('call', 'AIFunction_DefaultHandler')])]
    return script(tree)


# ------------------------------------------------------------------------------------------------ selftest
def selftest():
    G = r'C:/Users/1qdeath/Games/IGI2/app/MISSIONS/'
    a = script([('if', state('AISquadState_Idle'),
                 [('if', squad_ev('AIEVENT_ALARMON'), [('call', 'AISquad_MoveToNode', 430)], None)],
                 [('call', 'AISquad_DefaultHandler')])])
    assert a == open(G + 'location1/LEVEL5/ai/Squad_721.qvm', 'rb').read(), 'Squad_721 differs'
    b = script([('if', state('AISquadState_Idle'),
                 [('if', any_of([squad_ev(e) for e in ALERT_EVENTS]), [('call', 'AISquad_SwitchState', 'AISquadState_HoldArea')],
                   [('call', 'AISquad_DefaultHandler')])],
                 [('call', 'AISquad_DefaultHandler')])])
    assert b == open(G + 'location1/LEVEL5/ai/Squad_3744.qvm', 'rb').read(), 'Squad_3744 differs'
    # (decode what we write with the same reader the game data goes through)
    for blob in (guard(dict(idle=(30, 100), investigate=(45, 120), combat=(60, 120), acc=(80, 20, 120)),
                       idle=[('AIAction_Patrol', 812, 1, 0)], dark_var='EditVariable_1500.nValue'),):
        ver, syms, strs, code = igiqvm.read_qvm(blob)
        assert ver == (8, 7) and code[-1] == 0, 'bad tail'
    print('aisquad selftest: Squad_721 + Squad_3744 re-assembled byte for byte; generated scripts decode')


if __name__ == '__main__':
    selftest()
