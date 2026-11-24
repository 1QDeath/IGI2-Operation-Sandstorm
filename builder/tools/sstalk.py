"""sstalk - Sandstorm soldiers who talk (owner 11-06 items 59, 60), behind env SS_TALK=1 until proven.

WHAT THE PLAYER GETS
  Men standing together tell each other stories in Iraqi Arabic, heard close up, the English line at the bottom left of the screen, in order. Kill a speaker,
  alert him or raise the alarm and the talk stops at once, the line on screen goes too. Walk off and the line goes; walk back and they carry on with the next one.
  In a fight men shout (see you, where is he, man down, grenade...), each shout with its English line, driven by the soldier's own AI events.

THE RECORDING SHEETS ARE THE DATA.  work/sandstorm/voices/NN_<scene>.md, one file per scene, and barks.md. This module parses those tables, so a changed line in a sheet
is a changed line in the game. tools/sstalk.py html writes the printable work/sandstorm/voices/RECORDING_SHEETS.html.

DROPPING RECORDINGS IN.  Put <line id>.wav (or .mp3 .m4a .ogg .flac .opus) in work/sandstorm/voices/recordings/, any rate, then build. ingest() trims, cleans and levels each
one into voices/processed/ (ffmpeg), a line with a file then runs on its real length. `python -P tools/sstalk.py status` says what is still missing.
No file = SILENCE: the subtitle still plays on a timing estimated from the Arabic, no placeholder sound (the original mumble options read as a bug beside real lines).

ENGINE FACTS (igi2-decomp, each proven on the rig, see work/sandstorm/voices/ENGINE_NOTES.md)
  THE SYMBOL TABLE IS 4999 ENTRIES AND FULL = THE LOAD HANGS FOREVER at 80 % (igi2.exe+0x48b90, closed hash, no resize). A StatusMessage with an id takes 5 symbols. Id -1 takes none, but
    StatusMessage_CleanUp deletes every id-less StatusMessage on a save load. So ONE saved StatusMessage per scene and per bark kind, its Text a list of keys: the engine shows them in turn,
    each for Duration * its length / the total length, so trailing spaces set a line's time.
  StatusMessage arg 'Cutscene message' True = no box, no typing, bottom left, wide font, only the newest one drawn. Works in play.
  A ConditionalContainer going false sends the Remove event to its children: StatusMessage_RemoveHandler takes the text off the screen at once. It is the only safe cut:
    StatusMessageScreen_ClearMessages leaves a stale slot and the message's own later RemoveMessage hits a null reference. Coming back, the list goes on with the next line.
  One container per scene whose condition is 'Jones in earshot && every speaker alive && nobody alerted && calm', so at most one scene runs (earshot boxes are kept apart at build
    time: different groups never overlap) and far scenes cost nothing.
  SoundGenerators replay a sound on a container's Register, so the voices sit in their own container that only ever goes false for good (a speaker dead or alerted). A voice carries on
    fading with distance if Jones walks off. StatusMessage.nTickSendt changes on every new line of the list: two counters turn that into the line number the voices wait for.
  AI QVMs can write level variables: Bin('=', 'EditVariable_N.nValue', value) (QVM_OpAssign, op 0x2a). That is the link from an AI event to the level: bark kind and 'stop talking'.
  LevelTimers are capped at 32 (fatal QTaskList is full): tick counters are EditVariables, whose rules ADD their value every tick.
  Budget: 5 ids and 8 symbols a scene, 3 more ids with voices; 2 ids and 7 symbols a bark kind.
"""
import glob, hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V_DIR = os.path.join(ROOT, 'work', 'sandstorm', 'voices')
REC = os.environ.get('SS_TALK_REC') or os.path.join(V_DIR, 'recordings')   # (test builds point this at test tones)
PROC = os.environ.get('SS_TALK_PROC') or os.path.join(V_DIR, 'processed')
EXTS = ('.wav', '.mp3', '.m4a', '.ogg', '.flac', '.opus', '.aac', '.wma')
GAP = (0.30, 0.45, 0.25, 0.60, 0.35, 0.50)                   # the beat between two lines, varied so it does not tick like a clock
HOLD_S, COOLDOWN_S = 2.4, 3.2                                 # a bark stays this long on screen, the next can come this long after its start
TALK_VOL, TALK_MIN, TALK_MAX = 0.8, 3.0, 17.0                 # conversation: full up to 3 m, gone at 17 m
BARK_VOL, BARK_MIN, BARK_MAX = 1.0, 8.5, 90.0                 # a shout carries (the GV defs use 8.5 .. 120)
TARGET_DB = -19.0                                             # active RMS of a processed line: the mission's English lines measure about this


# ------------------------------------------------------------------------------------------------ the sheets
class Line:
    def __init__(s, id_, who, ar, lat, en, cat=''):
        s.id, s.who, s.ar, s.lat, s.en, s.cat = id_, who, ar, lat, en, cat


class Scene:
    def __init__(s, path):
        s.path, s.key, s.title, s.place, s.squad, s.note = path, '', '', '', '', ''
        s.earshot = 16.0
        s.men, s.lines = {}, []                               # men: letter -> (name, who he is, man index in the squad)


def _cells(row):
    return [c.strip() for c in row.strip().strip('|').split('|')]


def parse(path):
    s = Scene(path)
    s.key = os.path.basename(path)[3:-3]
    table = None
    for raw in open(path, encoding='utf-8'):
        t = raw.strip()
        if t.startswith('# '):
            s.title = t[2:].strip()
        elif t.startswith('Place:'):
            s.place = t[6:].strip()
        elif t.startswith('Squad:'):
            s.squad = t[6:].strip().strip('`')
        elif t.startswith('Earshot:'):
            s.earshot = float(t[8:].replace('m', '').strip())
        elif t.startswith('Scene:'):
            s.note = t[6:].strip()
        elif t.startswith('|'):
            c = _cells(t)
            if c[0] == 'Speaker':
                table = 'men'
            elif c[0] == 'ID':
                table = 'lines'
            elif set(c[0]) <= set('-: '):
                pass
            elif table == 'men':
                s.men[c[0]] = (c[1], c[2], int(c[3]))
            elif table == 'lines':
                assert len(c) == 5, (path, t)
                assert c[1] in s.men, (path, c)
                s.lines.append(Line(c[0], c[1], c[2], c[3], c[4]))
    return s


def scenes():
    import ssvoices                                           # (owner 11-12: with SS_VOICES=1 a sheet in voices/friends_11-10/sheets replaces the sheet of the same name)
    return [s for s in (ssvoices.only_recorded(parse(f)) for f in ssvoices.sheet_overlay(sorted(glob.glob(os.path.join(V_DIR, '[0-9][0-9]_*.md'))))) if s.lines]


def barks():
    """barks.md: '## <category>' sections, one table each; every line a variant"""
    out, cat = {}, None
    import ssvoices
    if ssvoices.ON:                                           # (owner 11-12: the friends' recorded shouts replace these lists, one list per voice: tools/ssvoices.py)
        return out
    p = os.path.join(V_DIR, 'barks.md')
    for raw in open(p, encoding='utf-8'):
        t = raw.strip()
        if t.startswith('## '):
            cat = t[3:].split()[0]
            out[cat] = []
        elif t.startswith('|') and cat:
            c = _cells(t)
            if c[0] == 'ID' or set(c[0]) <= set('-: '):
                continue
            assert len(c) == 5, t
            out[cat].append(Line(c[0], c[1], c[2], c[3], c[4], cat))
    return out


# which AI events fire which bark category, in priority order (the first match wins); a category with no lines is skipped
EVENTS = [('grenade', ('GRENADESHOUT', 'GRENADELAND')), ('hit', ('TAKINGDAMAGE',)), ('mandown', ('FRIENDLY_DYING', 'DEATH_CRY', 'FRIENDLYDETECTION', 'FRIENDLY_DAMAGE_SEEN')),
          ('see', ('ENEMYDETECTION',)), ('lost', ('LOSTSIGHTOFENEMY',)), ('backup', ('BACKUP_REQUEST', 'DISTRESSCALL')), ('throw', ('GRENADETHROWN',)), ('reload', ('HANDLEWEAPON',)),
          ('alarm', ('ALARMON',)), ('shots', ('GUNSHOT', 'BULLETIMPACT', 'GUNSHOTMISS', 'EXPLOSION')), ('what', ('SEENSOMETHING', 'REACTTOSUSPICION')), ('clear', ('SEARCHOVER',))]
STOP_EVENTS = ('ENEMYDETECTION', 'TAKINGDAMAGE', 'FRIENDLY_DYING', 'DEATH_CRY', 'FRIENDLYDETECTION', 'FRIENDLY_DAMAGE_SEEN', 'EXPLOSION', 'GRENADELAND', 'GUNSHOT', 'BULLETIMPACT')


# ------------------------------------------------------------------------------------------------ recordings
def _find(i):
    for e in EXTS:
        p = os.path.join(REC, i + e)
        if os.path.exists(p):
            return p
    return None


def _proc(i):
    import ssvoices                                           # (a friend's finished clip of that id wins: already cut, cleaned and levelled by friends_11-10/cut.py)
    return (ssvoices.clip(i) if ssvoices.ON else None) or os.path.join(PROC, i + '.wav')


def _secs(p):
    with wave.open(p, 'rb') as w:
        return w.getnframes() / float(w.getframerate())


def ingest(ids, log=print):
    """recordings -> processed 22050 Hz mono 16-bit, ends trimmed, levelled. A file is redone when its size or time changes; a bad file is reported and skipped, never stops a build"""
    found = [(i, _find(i)) for i in ids if _find(i)]
    if not found:
        return 0
    if not shutil.which('ffmpeg'):
        stale = [i for i, s in found if not have(i)]
        if stale:
            log('sstalk WARNING: no ffmpeg here, %d recordings NOT in this build (%s...): build on the PC or run tools/sstalk.py ingest there' % (len(stale), stale[0]))
        return 0
    import numpy as np
    os.makedirs(PROC, exist_ok=True)
    idx_p = os.path.join(PROC, 'index.json')
    try:
        idx = json.load(open(idx_p))
    except Exception:
        idx = {}
    n = 0
    for i, src in found:
        st = os.stat(src)
        stamp = '%s %d %d' % (os.path.basename(src), st.st_size, int(st.st_mtime))
        dst = _proc(i)
        if idx.get(i) == stamp and os.path.exists(dst):
            continue
        tmp = dst + '.tmp.wav'
        trim = 'silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.04'
        try:
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-af', 'highpass=f=90,%s,areverse,%s,areverse' % (trim, trim), '-ac', '1', '-ar', '22050', '-sample_fmt', 's16', tmp], check=True)
            with wave.open(tmp, 'rb') as w:
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float) / 32768.0
            if len(pcm) < 2205:
                raise ValueError('empty after trimming')
            win = 441
            e = np.array([np.mean(pcm[k:k + win] ** 2) for k in range(0, len(pcm) - win, win)]) + 1e-12
            act = e[e > e.max() * 0.03]
            g = 10 ** ((TARGET_DB - 10 * math.log10(float(act.mean()))) / 20.0)
            pcm = pcm * min(g, 0.97 / max(1e-6, float(np.abs(pcm).max())))
            with wave.open(tmp, 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
                w.writeframes((pcm * 32767).astype('<i2').tobytes())
            os.replace(tmp, dst)
            idx[i] = stamp
            n += 1
        except Exception as e_:
            log('sstalk WARNING: recording %s skipped: %s' % (src, e_))
            if os.path.exists(tmp):
                os.remove(tmp)
    json.dump(idx, open(idx_p, 'w'), indent=0)
    if n:
        log('sstalk: %d recordings processed' % n)
    return n


def have(i):
    return os.path.exists(_proc(i))


def est_secs(ln):
    """no recording: how long a man takes to say it. Iraqi talk runs about 13 characters a second; the English must also stay readable (17 a second)"""
    return max(1.5, 0.4 + len(re.sub(r'[^\w]', '', ln.ar)) / 11.0, 0.5 + len(ln.en) / 17.0)


def line_secs(ln):
    return _secs(_proc(ln.id)) + 0.25 if have(ln.id) else est_secs(ln)


def defname(i):
    return 'st_' + i


# ------------------------------------------------------------------------------------------------ the level side
def ids_alloc(m):
    def f():
        try:
            return m.new_id(2753, 4096)
        except RuntimeError:
            return m.new_id(20, 402)
    return f


def stage(g):
    """after every squad exists and U_ALARM is known: the scene containers. g = the builder's globals"""
    m, T, LOGIC, SQ, ua = g['m'], g['T'], g['LOGIC'], g['SQUAD_IDS'], g['_UA']
    import atmos
    for t in ('ConditionalContainer', 'SequenceCommand', 'SoundGenerator', 'EditVariable', 'EditRigidObj', 'Container'):
        atmos.ensure_decl(m, t)
    new = ids_alloc(m)
    sc_all = [s for s in scenes() if s.squad in SQ and (os.environ.get('SS_TALK_SILENT') == '1' or any(have(l.id) for l in s.lines))]   # (orchestrator 11-14 C13: caption-only scenes cut)
    missing = [s.key for s in scenes() if s.squad not in SQ]
    all_ids = [l.id for s in sc_all for l in s.lines] + [l.id for c in barks().values() for l in c]
    assert len(all_ids) == len(set(all_ids)), [i for i in all_ids if all_ids.count(i) > 1][:5]
    ingest(all_ids)
    incs = new()                                              # (a cutscene running: nobody chats or shouts over it. Its rules are set in ai(), when every cutscene exists)
    m.add_child(LOGIC, T(incs, 'EditVariable', 'ST in a cutscene', 0.0, 0.0, 0.0, 0, '', ''))
    g['ST_INCS'] = incs
    out = {}
    n_lines = n_rec = 0
    tours = []
    for s in sc_all:                                          # (different groups must never talk at once: earshot boxes apart, or on different floors. The bigger box of a clash shrinks)
        P = [[float(m.arg(SQ[s.squad][1][v[2]], k)) for k in (3, 4, 5)] for v in s.men.values()]
        s.c = [sum(p[k] for p in P) / len(P) for k in range(3)]
    clash = True
    while clash:
        clash = False
        for a_ in sc_all:
            for b_ in sc_all:
                if a_ is not b_ and a_.earshot >= b_.earshot and abs(a_.c[2] - b_.c[2]) < 3.3 * 4096:
                    e_ = (a_.earshot + b_.earshot) * 2048.0
                    if abs(a_.c[0] - b_.c[0]) < e_ and abs(a_.c[1] - b_.c[1]) < e_:
                        a_.earshot -= 0.5
                        assert a_.earshot >= 4.0, 'sstalk: %s sits on top of %s' % (a_.key, b_.key)
                        clash = True
    for s in sc_all:
        hids = SQ[s.squad][1]
        who = {k: hids[v[2]] for k, v in s.men.items()}
        c, e = s.c, s.earshot * 4096.0
        z, stop, cc, msg = new(), new(), new(), new()
        m.add_child(LOGIC, T(z, 'AreaActivate', 'ST earshot ' + s.key, c[0], c[1], c[2] + 1.2 * 4096.0, 0.0, 0.0, 0.0, e, e, 3.3 * 4096, 'CRITERIA_HUMAN0'))
        m.add_child(LOGIC, T(stop, 'EditVariable', 'ST alerted ' + s.key, 0.0, 0.0, 0.0, 0, '', ''))
        calm = ua + ' == 0' if s.squad.startswith('U ') else 'EditVariable_1500.nValue == 0'
        alive = ['!HumanSoldier_%d.isDead' % h for h in who.values()] + ['EditVariable_%d.nValue == 0' % stop]
        rule = ' && '.join(['AreaActivate_%d.nActive' % z, 'EditVariable_%d.nValue == 0' % incs, calm] + alive)
        times = [line_secs(ln) + GAP[k % len(GAP)] for k, ln in enumerate(s.lines)]    # (a line's time on screen includes the beat after it)
        texts = ['%s: %s' % (s.men[ln.who][0].upper(), ln.en) for ln in s.lines]
        cps = max(len(x) / y for x, y in zip(texts, times))    # (the engine shares Duration by string length: trailing spaces make every line last its time)
        keys = []
        for ln, x, y in zip(s.lines, texts, times):
            keys.append('ST_' + ln.id.upper())
            m.add_text('messages', keys[-1], x + ' ' * (int(round(y * cps)) - len(x)))
        assert len(','.join(keys)) < 950, s.key
        kids = [T(msg, 'StatusMessage', 'ST talk ' + s.key, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'TRUE', ','.join(keys), '', '', True, True, round(sum(times), 2), '')]
        voiced = [(k, ln) for k, ln in enumerate(s.lines) if have(ln.id)]
        if voiced:                                            # (line number: every new line changes nTickSendt. seen follows it, count adds one on the tick they differ)
            count, seen, vc = new(), new(), new()
            tick = 'StatusMessage_%d.nTickSendt' % msg
            kids += [T(count, 'EditVariable', 'ST line ' + s.key, 0.0, 0.0, 0.0, 0, '%s != EditVariable_%d.nValue' % (tick, seen), ''),
                     T(seen, 'EditVariable', 'ST line tick ' + s.key, 0.0, 0.0, 0.0, 0, '%s - EditVariable_%d.nValue' % (tick, seen), '')]
            sg = [T(-1, 'SoundGenerator', '', children=[T(-1, 'SequenceCommand', '', 'EditVariable_%d.nValue == %d' % (count, k + 1), 'SoundGenerator_PlaySound("%s")' % defname(ln.id),
                                                          'TRUE', 'SequenceCommand_SetCommand(-1)')]) for k, ln in voiced]
            m.add_child(LOGIC, T(vc, 'ConditionalContainer', 'ST voices ' + s.key, ' && '.join(alive), '', '', children=[
                T(-1, 'EditRigidObj', 'ST voice ' + s.key, c[0], c[1], c[2] + 1.5 * 4096.0, 0.0, 0.0, 0.0, 'none', 5, False, False, children=sg)]))
            n_rec += len(voiced)
        n_lines += len(s.lines)
        s.secs = sum(times)
        m.add_child(LOGIC, T(cc, 'ConditionalContainer', 'ST scene ' + s.key, rule, '', '', children=kids))
        out[s.key] = dict(stop=stop, aids=[_aid(m, h) for h in who.values()], cc=cc, hids=list(who.values()), z=z)
        tours.append((s.key, c))
    print('sstalk: %d scenes, %d lines, %d with a recording, %.0f s of talk; squads not in this build: %s; earshots cut %s' % (
        len(sc_all), n_lines, n_rec, sum(s.secs for s in sc_all), missing, {s.key: s.earshot for s in sc_all if s.earshot != parse(s.path).earshot}))
    g['ST_SCENES'], g['ST_TOUR'] = out, tours
    if 'talktour' in g['DBG']:                                # (test: the builder's tour drops the first 7 stops of its list)
        g['_ttour'][:] = [(0.0, 0.0, 0.0)] * 7 + [(c_[0] + 3000.0, c_[1] + 3000.0, c_[2]) for k_, c_ in tours]
    if 'talkquiet' in g['DBG'] or 'talktour' in g['DBG']:     # (test: a camera must not end the calm)
        m.set(1500, 7, '0')
    _bark_level(g, new)


def _aid(m, hid):
    from mission_lib import lit
    for c in m.children(hid):
        if lit(c.args[1]) == 'HumanAI':
            return lit(c.args[0])
    raise KeyError(hid)


def _bark_level(g, new):
    """the subtitles of the barks: an AI writes its kind into BK. The kind's container comes on, its message goes on to the next line of its list, the clock takes BK back after HOLD_S, which
    cuts the line. The list holds each line three times so a long fight does not run off the end. Every line is padded to one length: each lasts just over HOLD_S"""
    m, T, LOGIC = g['m'], g['T'], g['LOGIC']
    bk, cool, clock = new(), new(), new()
    for i, n in ((bk, 'ST bark kind'), (cool, 'ST bark cooldown'), (clock, 'ST bark clock')):
        m.add_child(LOGIC, T(i, 'EditVariable', n, 0.0, 0.0, 0.0, 0, '', ''))
    table = {}
    for k, (cat, lines) in enumerate(barks().items()):
        wide = max(len('SOLDIER: ' + ln.en) for ln in lines)
        for ln in lines:
            x = 'SOLDIER: ' + ln.en
            m.add_text('messages', 'ST_' + ln.id.upper(), x + ' ' * (wide - len(x)))
        keys = ','.join(['ST_' + ln.id.upper() for ln in lines] * 3)
        assert len(keys) < 950, cat
        msg, cc, turn = new(), new(), new()
        m.add_child(LOGIC, T(turn, 'EditVariable', 'ST bark turn ' + cat, 0.0, 0.0, 0.0, 0, '', ''))
        m.add_child(LOGIC, T(cc, 'ConditionalContainer', 'ST bark ' + cat, 'EditVariable_%d.nValue == %d' % (bk, k + 1), '', '', children=[
            T(msg, 'StatusMessage', 'ST bark ' + cat, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'TRUE', keys, '', '', False, True, round((HOLD_S + 0.2) * len(lines) * 3, 2), '')]))
        table[cat] = (k + 1, lines, turn)
    a, b, c = new(), new(), new()
    F = 'GAME_FREQUENCY'
    m.add_child(LOGIC, T(new(), 'Container', 'ST bark clock', False, children=[
        T(a, 'SequenceCommand', '', 'EditVariable_%d.nValue != 0' % bk, 'EditVariable_%d.nValue = LevelFlow_10.nTick' % clock, 'TRUE', 'SequenceCommand_SetCommand(%d)' % b),
        T(b, 'SequenceCommand', '', 'LevelFlow_10.nTick > EditVariable_%d.nValue + %.1f * %s' % (clock, HOLD_S, F), 'EditVariable_%d.nValue = 0' % bk, 'TRUE', 'SequenceCommand_SetCommand(%d)' % c),
        T(c, 'SequenceCommand', '', 'LevelFlow_10.nTick > EditVariable_%d.nValue + %.1f * %s' % (clock, COOLDOWN_S, F), 'EditVariable_%d.nValue = 0' % cool, 'TRUE', 'SequenceCommand_SetCommand(%d)' % a)]))
    g['ST_BARK'] = dict(bk=bk, cool=cool, table=table)
    print('sstalk: %d bark lines in %d kinds' % (sum(len(v[1]) for v in table.values()), len(table)))


# ------------------------------------------------------------------------------------------------ the AI side
def ai(g):
    """call LAST, after every session's AI edits, before m.write: every soldier's script gets a prefix that turns his real events into a bark number, and the men of a scene
    an 'alerted' flag. The script's own event chain runs after the prefix unchanged"""
    import alarmai
    from alarmai import Bin, C, EQ, AND, If, EV, _in, E, compile_ai, decompile_ai
    from igiqvm import Call, Str
    m, B = g['m'], g['ST_BARK']
    from mission_lib import tasks, lit
    for key, sc in list(g['ST_SCENES'].items()):              # (a test variant took the men out after stage(): the scene goes with them)
        if any(h not in m.byid for h in sc['hids']):
            m.remove(sc['cc']); m.remove(sc['z']); m.reindex()
            g['ST_SCENES'].pop(key)
    cs = [lit(t_.args[0]) for t_, d_, p_ in tasks(m.stmts) if lit(t_.args[1]) == 'CutScene' and isinstance(lit(t_.args[0]), int) and lit(t_.args[0]) >= 0]
    on = ' || '.join('CutScene_%d.isRun' % c_ for c_ in cs) or '0'
    incs = 'EditVariable_%d.nValue' % g['ST_INCS']
    m.set(g['ST_INCS'], 7, '%s == 0 && (%s)' % (incs, on))    # (the rules add to the value every tick they are true)
    m.set(g['ST_INCS'], 8, '%s > 0 && !(%s)' % (incs, on))
    bk, cool = 'EditVariable_%d.nValue' % B['bk'], 'EditVariable_%d.nValue' % B['cool']
    ev = C('AIFunction_GetCurrentEventType')
    blk = None
    for cat, evs in reversed(EVENTS):
        if not B['table'].get(cat, (0, ()))[1]:
            continue
        k, lines, turn = B['table'][cat]
        then = [Bin('=', E(bk), E(k)), Bin('=', E(cool), E(1))]
        if any(have(ln.id) for ln in lines):                  # (his own voice from his own position: the turn counter walks the list in step with the subtitles)
            tv = 'EditVariable_%d.nValue' % turn
            for n_, ln in enumerate(lines):
                if have(ln.id):
                    then.append(If(EQ(tv, n_), [Call('AIAction_PlaySound', [Str(defname(ln.id)), E(0), E(0)])]))
            then.append(If(EQ(tv, len(lines) - 1), [Bin('=', E(tv), E(0))], [Bin('=', E(tv), Bin('+', E(tv), E(1)))]))
        blk = If(_in(ev, *[EV(e_) for e_ in evs]), then, [blk] if blk else None)
    prefix = [If(AND(EQ(bk, 0), EQ(cool, 0), EQ(incs, 0)), [blk])] if blk else []
    if 'talkfight' in g['DBG']:                               # (test only: the men miss, so the bot lives long enough to hear the barks)
        prefix.append(If(EQ(ev, EV('ENEMYDETECTION')), [C('AIFunction_SetMinRangeAccuracy', 1), C('AIFunction_SetMedRangeAccuracy', 1), C('AIFunction_SetMaxRangeAccuracy', 1)]))
    stop_for = {}
    for sc in g['ST_SCENES'].values():
        for a in sc['aids']:
            stop_for[str(a)] = sc['stop']
    n = 0
    for key, data in list(m.ai_files.items()):
        if not key.isdigit() or not isinstance(data, (bytes, bytearray)):
            continue
        ver, body = decompile_ai(bytes(data))
        pre = list(prefix)
        if key in stop_for:
            pre.insert(0, If(_in(ev, *[EV(e_) for e_ in STOP_EVENTS]), [Bin('=', E('EditVariable_%d.nValue' % stop_for[key]), E(1))]))
        m.ai_files[key] = compile_ai(pre + body, ver)
        n += 1
    print('sstalk: %d soldier scripts carry the talk prefix, %d of them scene men' % (n, len(stop_for)))


# ------------------------------------------------------------------------------------------------ the sound bank
def sounds(extra, defs, sb):
    """before the level bank is written: every processed line becomes a sample and a DefineSound. extra / defs = the builder's lists, sb = soundbank"""
    n = 0
    for s in scenes():
        for ln in s.lines:
            if have(ln.id):
                extra.append((defname(ln.id) + '.wav', sb.riff_to_ilsf(open(_proc(ln.id), 'rb').read(), flags=0x1001)))
                import ssvoices                                # (owner 11-13 'really low': a friend's scene line is full volume to 6 m, heard to 30 m)
                defs.append('DefineSound("%s", "%s", 0, 0, 0, %s, %s, %s, -1, -1, -1, -1, FALSE)' % ((defname(ln.id), defname(ln.id)) + (ssvoices.VOL['talk'] if ssvoices.ON and ssvoices.clip(ln.id) else (TALK_VOL, TALK_MIN, TALK_MAX))))
                n += 1
    for lines in barks().values():
        for ln in lines:
            if have(ln.id):
                extra.append((defname(ln.id) + '.wav', sb.riff_to_ilsf(open(_proc(ln.id), 'rb').read(), flags=0x1001)))
                defs.append('DefineSound("%s", "%s", 0, 0, 0, %s, %s, %s, -1, -1, -1, -1, FALSE)' % (defname(ln.id), defname(ln.id), BARK_VOL, BARK_MIN, BARK_MAX))
                n += 1
    if n:
        print('sstalk: %d voice lines in the level bank' % n)


def status():
    ss, bk = scenes(), barks()
    tot = hav = wait = 0
    for s in ss:
        k = sum(1 for l in s.lines if _find(l.id) or have(l.id))
        print('%-14s %3d of %3d recorded   %s' % (s.key, k, len(s.lines), s.title))
        wait += sum(1 for l in s.lines if _find(l.id) and not have(l.id))
        tot += len(s.lines); hav += k
    for c, ls in bk.items():
        k = sum(1 for l in ls if _find(l.id) or have(l.id))
        print('bark %-9s %3d of %3d recorded' % (c, k, len(ls)))
        wait += sum(1 for l in ls if _find(l.id) and not have(l.id))
        tot += len(ls); hav += k
    print('total %d of %d%s' % (hav, tot, ', %d of them not processed yet: run tools/sstalk.py ingest on the PC' % wait if wait else ''))


def html():
    """the printable sheets for the speakers"""
    esc = lambda x: x.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    o = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Sandstorm recording sheets</title><style>',
         'body{font:15px/1.5 Segoe UI,Tahoma,Arial,sans-serif;color:#222;background:#fff;max-width:1100px;margin:0 auto;padding:16px}',
         'h1{font-size:26px}h2{font-size:20px;margin-top:36px;border-bottom:2px solid #444;padding-bottom:4px;break-before:page}',
         'table{border-collapse:collapse;width:100%;margin:10px 0}td,th{border:1px solid #bbb;padding:6px 8px;vertical-align:top;text-align:left}th{background:#eee}',
         '.ar{direction:rtl;text-align:right;font-size:19px;line-height:1.7;font-family:Segoe UI,Tahoma,Arial,sans-serif}.id{font-family:Consolas,monospace;font-size:12px;white-space:nowrap}',
         '.lat{font-style:italic}.n{color:#555}</style></head><body>']
    o.append(open(os.path.join(V_DIR, 'README.md'), encoding='utf-8').read().split('<!-- html -->')[1] if os.path.exists(os.path.join(V_DIR, 'README.md')) else '')
    for s in scenes():
        o.append('<h2>%s</h2><p class="n">%s</p><p>%s</p><table><tr><th>Speaker</th><th>Name</th><th>Who he is</th></tr>' % (esc(s.title), esc(s.place), esc(s.note)))
        for k, v in s.men.items():
            o.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (k, esc(v[0]), esc(v[1])))
        o.append('</table><table><tr><th>File name</th><th>Who</th><th>Iraqi Arabic</th><th>Reading guide</th><th>English</th></tr>')
        for l in s.lines:
            o.append('<tr><td class="id">%s</td><td>%s</td><td class="ar">%s</td><td class="lat">%s</td><td>%s</td></tr>' % (l.id, l.who, esc(l.ar), esc(l.lat), esc(l.en)))
        o.append('</table>')
    o.append('<h2>Combat shouts</h2><p>Shout these. Short, breathless, a man under fire. Each speaker can record any line.</p>')
    for c, ls in barks().items():
        o.append('<h3>%s</h3><table><tr><th>File name</th><th>Who</th><th>Iraqi Arabic</th><th>Reading guide</th><th>English</th></tr>' % esc(c))
        for l in ls:
            o.append('<tr><td class="id">%s</td><td>%s</td><td class="ar">%s</td><td class="lat">%s</td><td>%s</td></tr>' % (l.id, l.who, esc(l.ar), esc(l.lat), esc(l.en)))
        o.append('</table>')
    o.append('</body></html>')
    p = os.path.join(V_DIR, 'RECORDING_SHEETS.html')
    open(p, 'w', encoding='utf-8', newline=chr(10)).write(chr(10).join(o))
    print(p)


if __name__ == '__main__':
    {'status': status, 'html': html, 'ingest': lambda: ingest([l.id for s in scenes() for l in s.lines] + [l.id for c in barks().values() for l in c])}[sys.argv[1] if len(sys.argv) > 1 else 'status']()
