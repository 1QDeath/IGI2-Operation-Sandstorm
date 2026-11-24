"""ssbrain - Sandstorm garrison behaviour pass (owner G09, 11-13: 'make the enemies better'). Last AI pass of build_sandstorm.py, after every
other script writer (ssgarr.eyes, alarmai.Hunt, diffscale, sstalk, ssvoices). Behind env SS_BRAIN (default on).

What it changes, per armed man (the 'U scientists' flee by design and stay as they are), all inside the script's CREATE branch or as one
extra top-level statement - the engine's own DefaultHandler and the squad brain (alarmai.Hunt + COMMON squaddefault) still do the fighting:
  * combat and investigate sight as the ORIGINAL levels set them (census of 1665 original scripts, 11-13: combat cone 60 deg / 120-250 m,
    investigate 45 deg / 120-250 m, AccuracyMaxRange 125-150 m). Ours set them on 4 men of 124: the rest fought with the engine default.
    The calm (idle) cones stay as ssgarr.sight() set them (owner item 10: a calm man sees what is near him), so sneaking is unchanged.
  * every man who sees Jones calls for backup (AIAction_CallForBackup(45), as alarmai's soldiers) - 21 men lacked it (gun room crew,
    machine room, tunnel post / rockets, lone lookouts).
  * the bodies / dying friend / blast / gunshot event priorities of ssgarr.EARLY for the men that never got them (truck troops, drivers,
    stair teams): an idle man otherwise misses them (owner 64).
Accuracy itself (Min/Med/MaxRangeAccuracy and the difficulty block) is NOT touched: fair, not aimbots.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igiqvm import Call, Int, Ident
from alarmai import decompile_ai, compile_ai, to_text, If, Bin

BRAIN = os.environ.get('SS_BRAIN', '1') == '1'
COMBAT = (60, 150)            # (cone alpha deg, length m) - the originals' commonest pair with the 150 m range (L11-L36 census)
INVESTIGATE = (45, 150)
ACC_RANGE = 150
BACKUP_M = 45
SKIP_SQUADS = ('U scientists',)
NO_BACKUP = ('U gun room crew',)      # (review 11-13: the gun fight's event pool (gun_ai, 0x16bbf4) - no new backup calls beside the M2HB)
EARLY = ('DEAD', 'DELETE', 'PATROLCOMMANDPROCESSED', 'DANGERSTATETIMEOUT', 'ALARMOFF', 'ALARMON', 'FLASHBANG', 'GRENADETHROWN', 'GRENADELAND',
         'GRENADESHOUT', 'ENEMYDETECTION', 'ENEMYDETECTION_NO_LOF', 'TAKINGDAMAGE', 'GUNSHOT', 'FRIENDLY_DYING', 'FRIENDLYDETECTION', 'EXPLOSION')
MARK = 'AIFunction_SetInvestigateViewCone1Alpha'


def _is_create(c):
    return isinstance(c, Bin) and c.op == '==' and 'AIEVENT_CREATE' in (str(c.a), str(c.b))


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


def transform(data, backup=True):
    """soldier AI script bytes -> bytes with the behaviour block (unchanged when not a soldier script or already done). -> (bytes, list of what changed)"""
    try:
        ver, body = decompile_ai(data)
    except Exception:
        return data, []
    text = to_text(body)
    if 'AIFunction_GetCurrentEventType' not in text or 'AISquad_' in text or 'AIFunction_DefaultHandler' not in text:
        return data, []
    cr = _find_create(body)
    if cr is None:
        return data, []
    did, add = [], []
    if 'AIFunction_SetEventPriority' not in text:
        cr.then[0:0] = [Call('AIFunction_SetEventPriority', [Ident('AIEVENT_' + e)]) for e in EARLY]; did.append('priority')
    if 'SetCombatViewCone1Length' not in text:
        add += [Call('AIFunction_SetCombatViewCone1Alpha', [Int(COMBAT[0])]), Call('AIFunction_SetCombatViewCone1Length', [Int(COMBAT[1])])]; did.append('combat')
    if MARK not in text:
        add += [Call('AIFunction_SetInvestigateViewCone1Alpha', [Int(INVESTIGATE[0])]), Call('AIFunction_SetInvestigateViewCone1Length', [Int(INVESTIGATE[1])])]; did.append('investigate')
    if 'AIFunction_SetAccuracyMaxRange' not in text:
        add += [Call('AIFunction_SetAccuracyMaxRange', [Int(ACC_RANGE)])]; did.append('range')
    i = next((k + 1 for k, s in enumerate(cr.then) if isinstance(s, Call) and str(s.name) == 'AIFunction_DefaultHandler'), len(cr.then))
    cr.then[i:i] = add                                     # (after the DefaultHandler in CREATE: it sets the type's defaults first)
    if backup and 'AIAction_CallForBackup' not in text:
        body[0:0] = [If(Bin('==', Call('AIFunction_GetCurrentEventType', []), Ident('AIEVENT_ENEMYDETECTION')), [Call('AIAction_CallForBackup', [Int(BACKUP_M)])])]
        did.append('backup')
    if not did:
        return data, []
    return compile_ai(body, ver), did


def apply(g):
    """builder pass: every armed man's script in m.ai_files"""
    if not BRAIN:
        print('ssbrain: off (SS_BRAIN=0)')
        return
    m, lit = g['m'], g['lit']
    from collections import Counter
    cnt, men = Counter(), 0
    for key, (sid, hids) in g['SQUAD_IDS'].items():
        if key in SKIP_SQUADS:
            continue
        for h in hids:
            if h not in m.byid:                                # (review 11-13: men removed by noai / ssfew / nogarrison stay listed in SQUAD_IDS)
                continue
            aid = next((c.args[0] for c in m.byid[h].args if hasattr(c, 'args') and str(c.args[1]).strip('"') == 'HumanAI'), None)
            if aid is None:
                continue
            k = str(lit(aid))
            old = m.ai_files.get(k)
            if not isinstance(old, (bytes, bytearray)):
                continue
            new, did = transform(bytes(old), backup=key not in NO_BACKUP)
            if did:
                m.ai_files[k] = new; men += 1; cnt.update(did)
    print('ssbrain: %d men changed %s' % (men, dict(cnt)))


def patch_build(build_dir, skip_ids=()):
    """test only: the same transform on a built mission's ai/<HumanAI id>.qvm files (skip_ids = HumanAI ids to leave)"""
    import glob
    from collections import Counter
    cnt, men = Counter(), 0
    for f in glob.glob(os.path.join(build_dir, 'ai', '[0-9]*.qvm')):
        if int(os.path.basename(f)[:-4]) in skip_ids:
            continue
        old = open(f, 'rb').read()
        new, did = transform(old)
        if did:
            open(f, 'wb').write(new); men += 1; cnt.update(did)
    return men, dict(cnt)


def selftest():
    import aiscript
    for blob in (aiscript.patrol(812, aiscript.HARD), aiscript.sentry(aiscript.HARD), aiscript.sentry(None)):
        out, did = transform(blob)
        t = to_text(decompile_ai(out)[1])
        assert 'SetCombatViewCone1Length(' in t and 'SetInvestigateViewCone1Length(' in t and 'CallForBackup(45)' in t and transform(out)[1] == [], (did, t)
    t = to_text(decompile_ai(transform(aiscript.sentry(None))[0])[1])
    assert 'SetCombatViewCone1Length(150)' in t and 'SetAccuracyMaxRange(150)' in t, t
    print('ssbrain selftest ok')


if __name__ == '__main__':
    selftest()
