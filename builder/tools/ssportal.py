"""ssportal - S1 (owner 11-15: props vanish and come back when he turns or side-steps; inside and outside): the indoor cause, fixed.

    python -P tools/ssportal.py <build dir> [--dry]          (the build calls apply(out) last, after ssprune + ssperf)

The engine registers every sector object (EditRigidObj, pickups, switches, ...) in ONE portal sector of the original map's buildings
(tools/sectorcheck.py replays that rule from the decompiled engine). A prop whose geometry lies inside a sector but which is registered in
no sector, or in another one, is drawn only through portal rectangles while the camera is inside a building, so it drops out whenever no
such portal is on screen: S1 p3 / p4 (rc7s25, sewer stand sewb): merged room 'SS room sw2' + 'SS sewer water' (registered none, geometry in
the sewer sectors) vanished for 7.5 deg of turn; with EditRigidObj arg 12 TRUE ('Excluded from clipping against portals' = no sector
registration, plain frustum test) they were drawn in every picture (WT work/films/proof_11-15/S1/p4_REVIEW.md).

This sets arg 12 TRUE only on EditRigidObj that sectorcheck classes NONE_INSIDE / WRONG_SECTOR / SPANS AND that were proven on the rigs (PROVEN below,
decision 82: ssb2 17 of the 33 class hits), not on all.
Cost: an object registered in no sector is frustum-drawn already while the camera is outside every sectored building (outdoors, our own
shells: hall, gun room, Bulwark), so for those the flag only adds the indoor case; the few flagged props that were registered INSIDE a
sector (sewer floor pieces 432_12_1, frig collision boxes, house props) are now frustum-tested from everywhere - a handful of small models.
Other sector types (Switch 2209 alarm button, ExplodeObject, pickups) have no such flag: they are listed, not changed (N1: position only).
Env SS_PORTAL=0 = off. Re-running is harmless (flagged objects class as FLAGGED).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igiqvm
from qast import tasks, lit

FIX = ('NONE_INSIDE', 'WRONG_SECTOR', 'SPANS')
KEEP_MODELS = {'300_11_1'}     # (p6 11-17, stand proof: the original map's stone wall pieces 300_11_1 (ssb2 2860 / 2861 / 3776) poke into the roof shed 2859 and
                               #  are registered in the personnel house 3485 on purpose: the portal test hides them from inside the shed. Flagged they cut a stone
                               #  slab through the shed (WT work/films/proof_11-15/S1/p6_proof_slab.jpg). Left as the map has them: 30 flagged on ssb2)
# (PLAN decision 82, 11-17: an object is flagged only if its own room was spun on base AND fix with no vanish and nothing new showing through;
#  one that no stand has seen stays as the map has it. Rig A/B p5 / p9 / p10 / p11, WT work/films/proof_11-15/S1/S1_COVERAGE.md: 17 of the 30.
#  Unseen, left: overhead shaft parts 432_08_1 / 432_11_1, bulkhead 2923 (60.2, 69.2), roof lamp 261_10_1, the beam-like 303_05_1 / wi303_05_1.)
#  model -> object origins (m, sectorcheck pos_m on ssb2), matched within 0.5 m (ids move every build, positions do not). SS_PORTAL_ALL=1 = every class hit.
PROVEN_NAMES = {'SS room sw2', 'SS sewer water'}         # (ours, by task name: their origins are computed from the pieces and move when the room changes.
                                                         #  Base drops sw2 at sewb sewW sewS s2926 and the water at 8 sewer stands; fix draws both every frame)
# (11-17 ss-int, orch-2 decision after the ssb3 gate: the map-object part of PROVEN is OFF by default, SS_PORTAL_MAP=1 turns it on.
#  3953 flagged (433_04_1 at 72.4, 132.2, the shaft-foot room under the sewer hole) = the sewer entry is dead: on ssb3f the route stops 1.9 m
#  short of the shaft at wp 53 (70.9, 131.1; e6 + n9) while ssb2f walks in and drops into the sewer (A/B M/work/ssint/cands/ssb3/note/
#  wp53_ab_ssb2f_vs_ssb3f.jpg). Only the two seen pops stay flagged: PROVEN_NAMES.)
PROVEN_MAP = os.environ.get('SS_PORTAL_MAP') == '1'
PROVEN = {
    '432_12_1': [(72.9, 57.2), (88.5, 180.9), (86.2, -3.5), (86.2, 20.8), (86.2, 44.9), (72.3, 82.2), (84.2, 94.9),
                 (101.9, 169.0), (101.9, 144.6), (75.7, 192.8)],      # sewer bulkheads: clean on fix (sewW sewN sewS s2921 s2924 s2925 sewE s2926)
    '433_04_1': [(93.0, 206.0), (86.5, -33.3), (72.4, 132.2)],         # shaft-foot grates: clean on fix (shaftN shaftS shaftW)
    '300_04_1': [(72.3, 118.4), (128.0, 240.4)],                       # large-house walls 3038 / 3001: clean on fix (lhS, lhN)
}


def _hit(r):
    """the PROVEN key this row matches (name or (model, x, y)), None if none"""
    if (r.get('name') or '') in PROVEN_NAMES:
        return r['name']
    if not PROVEN_MAP:
        return None
    x, y = r['pos_m'][:2]
    for a, b in PROVEN.get(r['model'], ()):
        if abs(x - a) < 0.5 and abs(y - b) < 0.5:
            return (r['model'], a, b)
    return None


def _proven(r):
    if os.environ.get('SS_PORTAL_ALL') == '1':
        return r['model'] not in KEEP_MODELS
    return _hit(r) is not None


def _false(a):
    return (isinstance(a, igiqvm.Ident) and str(a).upper() == 'FALSE') or (isinstance(lit(a), int) and not isinstance(lit(a), bool) and lit(a) == 0)


def apply(out, log=print, dry=False):
    if os.environ.get('SS_PORTAL', '1') == '0':
        log('ssportal: off (SS_PORTAL=0)'); return 0
    import sectorcheck
    res = sectorcheck.check(out, pieces=False)
    bad = {int(r['id']): r for r in res['rows'] if r['type'] == 'EditRigidObj' and r['cls'] in FIX and _proven(r)}
    if os.environ.get('SS_PORTAL_ALL') != '1':              # (review 11-17: a moved or renamed proven object must not drop its flag in silence)
        got = {_hit(r) for r in res['rows'] if r['type'] == 'EditRigidObj'}
        want = set(PROVEN_NAMES) | ({(m, a, b) for m, pts in PROVEN.items() for a, b in pts} if PROVEN_MAP else set())
        for k in sorted(want - got, key=str):
            log('ssportal: WARNING: proven %s matches no EditRigidObj in this build (moved or renamed?): its S1 fix is NOT applied' % (k,))
    for r in res['rows']:
        if r['type'] == 'EditRigidObj' and r['cls'] in FIX and int(r['id']) not in bad:
            log('ssportal: %d %s %s at (%.1f, %.1f): left as the map registers it (%s)' % (int(r['id']), r['model'], r['cls'], r['pos_m'][0], r['pos_m'][1],
                'KEEP_MODELS' if r['model'] in KEEP_MODELS else 'not proven on the rigs, decision 82'))
    other = [r for r in res['rows'] if r['type'] != 'EditRigidObj' and r['cls'] in FIX]
    p = os.path.join(out, 'objects.qvm')
    ver, st = igiqvm.decompile(open(p, 'rb').read())
    done = []
    for t, d, par in tasks(st):
        if lit(t.args[1]) != 'EditRigidObj' or not isinstance(lit(t.args[0]), int) or int(lit(t.args[0])) not in bad:
            continue
        if len(t.args) > 12 and _false(t.args[12]):
            t.args[12] = igiqvm.Ident('TRUE')
            done.append(int(lit(t.args[0])))
    for i in done:
        r = bad[i]
        log('ssportal: %5d %-13s %-28s %-11s registered %s, real %s' % (i, r['model'], (r['name'] or '')[:28], r['cls'], r['registered'] or 'none',
            ', '.join('%s %d%%' % (k, round(v * 100)) for k, v in list(r['real'].items())[:3])))
    for i in sorted(set(bad) - set(done)):
        log('ssportal: %d %s %s: arg 12 not FALSE - left' % (i, bad[i]['model'], bad[i]['cls']))
    for r in other:
        log('ssportal: %d %s %s %s: no portal flag on this type - left (N1)' % (r['id'], r['type'], r['model'], r['cls']))
    if done and not dry:
        open(p + '.portal.tmp', 'wb').write(igiqvm.compile_stmts(st, ver)); os.replace(p + '.portal.tmp', p)
        q = os.path.join(out, 'objects.qsc')
        if os.path.exists(q):                              # (tmp + replace: a hard-linked probe build never writes through to its source)
            open(q + '.portal.tmp', 'w', encoding='latin1').write(igiqvm.stmts_to_qsc(st)); os.replace(q + '.portal.tmp', q)
    log('ssportal: portal clipping off on %d EditRigidObj (sectorcheck %s), %d other sector objects left%s'
        % (len(done), '/'.join(FIX), len(other), ' (dry run)' if dry else ''))
    return len(done)


if __name__ == '__main__':
    apply(sys.argv[1], dry='--dry' in sys.argv[2:])
