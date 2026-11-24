"""aiscript - write IGI 2 per-soldier AI scripts (ai/<HumanAI id>.qvm) with the event dispatch the originals use.

Every original AI script is one if / else-if chain on AIFunction_GetCurrentEventType() (work/aidis.py dumps them):

    if (GetCurrentEventType() == AIEVENT_CREATE) { AIFunction_DefaultHandler(); <setup calls> }
    else if (GetCurrentEventType() == AIEVENT_IDLE) { <idle calls, e.g. AIAction_Patrol(path, 1, 0)> }
    else AIFunction_DefaultHandler();

Byte layout (v8.7): PUSHII GetCurrentEventType, CALL 0, BRA +0, PUSHII AIEVENT_X, 0x24 (==), BF <else>, body
(each call + POP), BRA <end>, else: ... ; end: BRK. selftest() re-assembles originals byte for byte.

    script(create=[('AIFunction_SetIdleViewCone1Length', 120)], idle=[('AIAction_Patrol', 812, 1, 0)])
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igiqvm
from igiqvm import Call, Int, Ident

EQ = 0x24
BF = 0x04
BRA = 0x03
POP = 0x18


def _arg(a):
    if isinstance(a, (Int, Ident, Call)):
        return a
    if isinstance(a, int):
        return Int(a)
    if isinstance(a, str):
        return Ident(a)
    raise TypeError(a)


def _call(spec):
    name, *args = spec
    return Call(name, [_arg(a) for a in args])


def assemble(branches, default=True, ver=(8, 7), bra_to_end=True):
    """branches = [(event ident, [call specs])]; the first call of the CREATE branch is usually DefaultHandler.
    bra_to_end: each branch ends with BRA to the end (level4/500.qvm style; level1/550.qvm jumps +0 instead)."""
    en = igiqvm.Encoder()
    c = en.c
    fix_end = []
    for event, calls in branches:
        en.emit(Call('AIFunction_GetCurrentEventType', []))
        en.push_ident(en.sym(event))
        c.append(EQ)
        c.append(BF); bf = len(c); c += b'\0\0\0\0'
        for spec in calls:
            en.emit(_call(spec)); c.append(POP)
        c.append(BRA); fix_end.append(len(c)); c += b'\0\0\0\0'
        struct.pack_into('<i', c, bf, len(c) - (bf + 4))
    if default:
        en.emit(Call('AIFunction_DefaultHandler', [])); c.append(POP)
    end = len(c)
    for f in fix_end:
        struct.pack_into('<i', c, f, (end if bra_to_end else f + 4) - (f + 4))
    c.append(0x00)

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
                      o_strT, o_strD, len(strT), len(strD), o_code, len(c))
    hdr += b'\0' * (base - len(hdr))
    return hdr + symT + symD + strT + strD + bytes(c)


# the sharpest original guards (location1/LEVEL6/ai/545.qvm, a patrolling roof guard): +- deg cone halves, metres,
# accuracy percent at min range / at max range, max range m
HARD = dict(idle=(30, 100), investigate=(45, 120), combat=(60, 120), acc=(80, 20, 120))


# owner 10-12 'make it sneakable': the ORIGINAL default guard. 1533 of 1665 original AI scripts (92 %) set no view cone and
# no accuracy at all (survey 10-12) - the engine's per-type defaults; the 132 that do are mostly snipers (250-400 m cones)
NORMAL = None


def setup(profile=HARD):
    p = profile
    if p is None:
        return [('AIFunction_DefaultHandler',)]
    return [('AIFunction_DefaultHandler',),
            ('AIFunction_SetIdleViewCone1Alpha', p['idle'][0]), ('AIFunction_SetIdleViewCone1Length', p['idle'][1]),
            ('AIFunction_SetInvestigateViewCone1Alpha', p['investigate'][0]),
            ('AIFunction_SetInvestigateViewCone1Length', p['investigate'][1]),
            ('AIFunction_SetCombatViewCone1Alpha', p['combat'][0]), ('AIFunction_SetCombatViewCone1Length', p['combat'][1]),
            ('AIFunction_SetMinRangeAccuracy', p['acc'][0]), ('AIFunction_SetMaxRangeAccuracy', p['acc'][1]),
            ('AIFunction_SetAccuracyMaxRange', p['acc'][2])]


def patrol(path_id, profile=HARD):
    """walks his PatrolPath (walk / wait / look commands), again and again (the path ends with 'quit' -> idle again)"""
    return assemble([('AIEVENT_CREATE', setup(profile)), ('AIEVENT_IDLE', [('AIAction_Patrol', path_id, 1, 0)])])


def sentry(profile=HARD, pattern='AILOOKAROUND_PATTERN_180_CLOCKWISE'):
    """stands his post but keeps scanning (location1/level1/ai/518.qvm idle: look around, then tell the squad)"""
    return assemble([('AIEVENT_CREATE', setup(profile)),
                     ('AIEVENT_IDLE', [('AIAction_LookAround', pattern, 1), ('AIFunction_PassEventOnToSquad',)])])


def selftest():
    G = r'C:/Users/1qdeath/Games/IGI2/app/MISSIONS/'
    ok = 0
    a = assemble([('AIEVENT_CREATE', setup())] + [('AIEVENT_IDLE', [('AIAction_Patrol', 800, 1, 0)])])
    assert a == open(G + 'location1/LEVEL6/ai/545.qvm', 'rb').read(), 'LEVEL6/545 differs'
    ok += 1
    b = assemble([('AIEVENT_CREATE', [('AIFunction_DefaultHandler',)]),
                  ('AIEVENT_IDLE', [('AIAction_Patrol', 603, 5, Ident('AIACTIONFLAG_NONE'))])])
    assert b == open(G + 'location1/level4/ai/500.qvm', 'rb').read(), 'level4/500 differs'
    ok += 1
    print('aiscript selftest: %d originals re-assembled byte for byte' % ok)


if __name__ == '__main__':
    selftest()
