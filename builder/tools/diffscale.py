"""diffscale - ONE shared difficulty switch for every soldier AI script (10-18).

The game's difficulty (menu: Easy / Normal / Hard = 0 / 1 / 2; config GOGameDiff(GD_1 / GD_2 / GD_3), measured 10-18) is readable inside AI scripts as
Config_GetActiveDifficultyLevel() - the engine's own COMMON/ai/squaddefault.qvm uses it (only Normal/Hard soldiers
throw grenades). Level scripts expose it as LevelFlow_10.eDifficulty (not needed here).

Our missions are tuned as the owner plays them = Normal (aisquad HARD profile, sharp snipers). apply() appends to the AIEVENT_CREATE branch of a
soldier script:

    if (Config_GetActiveDifficultyLevel() == 0) { Easy:  weaker aim (min/max range accuracy 35 / 8), shorter hearing (0.6) }
    else if (Config_GetActiveDifficultyLevel() == 2) { Hard: sharper aim (+10 / x1.4) }
                                                         # Normal (1) = the script as built (what the owner tested)

Called from mission_lib.Mission.write for every non-squad AI file; IGI_NODIFF=1 disables it (build A/B). Idempotent.
A script that already calls SetHearingRangeFactor (Dark Harbor's storm) keeps its own hearing value.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igiqvm
from igiqvm import Call, Flt, Int, Ident
import alarmai
from alarmai import If, Bin, C, EQ, compile_ai, decompile_ai, to_text

# per script (reviewer 10-18): Easy / Hard are RELATIVE to the script's own literal accuracy (a sniper 95/35, a deliberately
# weak Burned guard 12/3), never above / below it; no literal (engine default, assumed 80/20 like the originals') -> 80/20.
#   Easy: min x0.45, max x0.4 (80/20 -> 36/8) + hearing 0.6        Hard: min +10 (cap 100), max x1.4 (80/20 -> 90/28)
DEFAULT_ACC = (80, 20)
DIFF = 'Config_GetActiveDifficultyLevel'


def _base(body):
    """(min, max) range accuracy literals the script sets itself, else DEFAULT_ACC"""
    got = {}

    def walk(stmts):
        for st in stmts:
            if isinstance(st, If):
                if 'AreaActivate_' in str(st.cond):         # (11-07 additive, Sandstorm gun room: a zone's own accuracy, not the script's base)
                    continue
                walk(st.then); walk(st.els or [])
            elif isinstance(st, Call) and st.name in ('AIFunction_SetMinRangeAccuracy', 'AIFunction_SetMaxRangeAccuracy'):
                if st.args and isinstance(st.args[0], (int, float)) and not isinstance(st.args[0], bool):
                    got.setdefault(st.name, int(st.args[0]))
    walk(body)
    return (got.get('AIFunction_SetMinRangeAccuracy', DEFAULT_ACC[0]), got.get('AIFunction_SetMaxRangeAccuracy', DEFAULT_ACC[1]))


def _calls(mn, mx, hearing=None):
    out = [C('AIFunction_SetMinRangeAccuracy', int(mn)), C('AIFunction_SetMaxRangeAccuracy', int(mx))]
    if hearing:
        out.append(Call('AIFunction_SetHearingRangeFactor', [Flt(hearing)]))
    return out


def _is_create(cond):
    return (isinstance(cond, Bin) and cond.op == '==' and isinstance(cond.a, Call) and cond.a.name == 'AIFunction_GetCurrentEventType'
            and str(cond.b) == 'AIEVENT_CREATE')


def _find_create(stmts):
    for s in stmts:
        if isinstance(s, If):
            if _is_create(s.cond):
                return s
            for blk in (s.then, s.els or []):
                r = _find_create(blk)
                if r is not None:
                    return r
    return None


def apply(data):
    """AI script bytes -> bytes with the difficulty block (or the input when it is not a soldier script / already done)"""
    try:
        ver, body = decompile_ai(data)
    except Exception:
        return data
    text = to_text(body)
    if DIFF in text or 'AIFunction_GetCurrentEventType' not in text or 'AISquad_' in text:
        return data
    cr = _find_create(body)
    if cr is None:                                      # no CREATE branch (never happens in our builds): leave the script alone
        return data
    b0, b1 = _base(body)
    hearing = 0.6 if 'AIFunction_SetHearingRangeFactor' not in text else None     # (storm missions keep their own hearing)
    easy = _calls(max(1, round(b0 * 0.45)), max(1, round(b1 * 0.4)), hearing)
    hard = _calls(min(100, b0 + 10), min(100, max(b1 + 1, round(b1 * 1.4))))
    cr.then.extend([If(EQ(C(DIFF), 0), easy, [If(EQ(C(DIFF), 2), hard)])])
    return compile_ai(body, ver)


def selftest():
    import aiscript, glob
    ok = 0
    for blob in (aiscript.patrol(812, aiscript.HARD), aiscript.sentry(aiscript.HARD), aiscript.sentry(None)):
        out = apply(blob)
        ver, syms, strs, code = igiqvm.read_qvm(out)
        assert DIFF in syms and out != blob and apply(out) == out
        t = to_text(decompile_ai(out)[1])
        assert 'SetMinRangeAccuracy(36)' in t and 'SetMinRangeAccuracy(90)' in t, t
        ok += 1
    G = r'C:/Users/1qdeath/Games/IGI2/app/MISSIONS/'
    n = 0
    for f in sorted(glob.glob(G + 'location*/*/ai/[0-9]*.qvm'))[:400]:
        d = open(f, 'rb').read()
        try:
            igiqvm.read_qvm(apply(d)); n += 1
        except Exception as e:
            print('FAIL', f, e)
    print('diffscale selftest: %d generated + %d original scripts transformed and re-read' % (ok, n))


if __name__ == '__main__':
    selftest()
