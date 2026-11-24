"""ssfew - owner 77 (11-07): the missile side down to 5 men so he can finish the game. SS_FEWMEN=0 gives the full garrison back, nothing below is deleted from the
builders: this pass runs last, on the finished mission. Surface, sewer, the machine room above the lift and the scientists are not touched; the trucks keep their drivers."""
import os, re
from qast import lit

FEWMEN = os.environ.get('SS_FEWMEN', '0') == '1'
KEEP = (('U lift landing', 0), ('U road post', 0), ('U cage', 0), ('U gate post', 0), ('U tunnel post', 0))
SPARED = ('U machine room', 'U scientists')
if os.environ.get('SS_FEW_ROCKETS'):                      # (test only 11-07, owner 14: the 3 rocket men alone, to see a rocket hit)
    KEEP = (('U tunnel rockets', 0), ('U tunnel rockets', 1), ('U tunnel rockets', 2))


def apply(g):
    m, SQ, tasks, v = g['m'], g['SQUAD_IDS'], g['tasks'], g['v']
    keep = {SQ[k][1][i] for k, i in KEEP if k in SQ}
    gone = set()

    def drop_ai(h):
        aid = next((lit(c.args[0]) for c in m.byid[h].args if hasattr(c, 'args') and lit(c.args[1]) == 'HumanAI'), None)
        if aid is not None:
            m.ai_files.pop(str(aid), None)

    for key, (sid, hids) in list(SQ.items()):
        if not key.startswith('U ') or key in SPARED:
            continue
        stay = [h for h in hids if h in keep]
        for h in hids:
            if h not in stay and h in m.byid:
                drop_ai(h); gone.add(h)
        if stay:
            for h in hids:
                if h not in stay and h in m.byid:
                    m.remove(h)
        elif sid in m.byid:
            m.remove(sid)
            m.ai_files.pop('Squad_%d' % sid, None)      # (review 17: its squad script goes with it)
    n = 0
    pat = re.compile(r'HumanSoldier_(\d+)\.isDead')
    for t_, d_, p_ in tasks(m.stmts):
        for k_, a_ in enumerate(t_.args):
            if type(a_).__name__ == 'Str' and 'HumanSoldier_' in str(a_):
                dead = '(0)' if str(a_).endswith('.nTick > 0') or lit(t_.args[1]) == 'LevelTimer' else '(1)'   # (a clock must not start on a man who was never there: 01:30 the hall alarm rang at 1.5 s)
                s = pat.sub(lambda h: dead if int(h.group(1)) in gone else h.group(0), str(a_))
                if s != str(a_):
                    t_.args[k_] = v(s); n += 1
    g['ENEMY_COUNT'][0] -= len(gone)
    left = [h for h in re.findall(r'HumanSoldier_(\d+)', ' '.join(str(a_) for t_, d_, p_ in tasks(m.stmts) for a_ in t_.args if type(a_).__name__ == 'Str')) if int(h) in gone]
    assert not left, ('ssfew: rules still name removed men', left[:6])
    bad = [lit(t_.args[0]) for t_, d_, p_ in tasks(m.stmts) if lit(t_.args[1]) == 'LevelTimer' and any('(1)' in str(a_) for a_ in t_.args if type(a_).__name__ == 'Str')]
    assert not bad, ('ssfew: a LevelTimer starts on a removed man', bad)
    print('ssfew: %d men removed on the missile side, %d kept, %d rules patched' % (len(gone), len(keep), n))
