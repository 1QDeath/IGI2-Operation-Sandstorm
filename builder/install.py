"""Install / uninstall custom IGI 2 missions (any number side by side).

  python install.py install <name>      e.g. ironfist, aftershock
  python install.py uninstall <name>
  python install.py status

Campaign (11-14, owner 11-08 'two missions only'): the mission list is Sandstorm (19) -> Sirocco (30) and nothing else, so the
game ends after Sirocco (its stats, then the end credits, then the main menu). Add --with-originals (or INSTALL_WITH_ORIGINALS=1)
to any install/uninstall to list the 19 original missions (and any other installed custom mission) after our two again; it lasts
until the next install/uninstall without the switch. The originals' stats in config.qvm are never touched.

Savegames (11-15, G43): an update invalidates mid-mission saves. The game applies a save by task id, so a save of an old build
corrupts the new one (crash a few seconds in). Every install/uninstall moves that mission's saves (savegames/*-*-<id>-*.igi2save) to
<game>/savegames_bak-<date>-<build>/ and prints how many; nothing is deleted. Campaign progress, stats and carry-over (savegames/missions) stay.

End picture (11-15, SF_DESIGN 2.5 / I1): a build with endscreen/congratulations.jpg installs it as NEW files
SCREENS/intro/english|USA/congratulations.jpg (shown after the last stats instead of the stock / Neonix picture, which is never touched);
uninstall, or installing another build of the same mission, deletes them again (only while byte-identical to what was written).

Intro / end pictures (11-23, fix1123 E2, owner: no Neonix picture anywhere): the engine shows SCREENS/intro/<language>/<name> before
SCREENS/intro/<name> (introscreen.c), so every install / uninstall writes screens/intro/*.jpg (ours: the stock Codemasters / Innerloop /
Pan Vision splashes from before the Neonix patch, and our end picture) as NEW files into SCREENS/intro/english|USA. The Neonix files
in SCREENS/intro are never touched. congratulations.jpg: a build's own endscreen/ picture wins; ours only while no installed build has one.
A language-folder file that we did not write (installed_intro.json keeps what we wrote) is never overwritten.

Each build/<name>/ contains objects.qvm, mission.qvm, ai/*.qvm and meta.json:
  {"id": 38, "location": "location1", "base": "level1", "folder": "aftershock", "text": {"missions": {...}, ...}}
Language files and the campaign list (MISSIONS/igi2.qvm) are regenerated from the pristine
originals in backup/original + every installed mission, so missions never clobber each other.
Nothing original is overwritten without a backup.
"""
import json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
import igiqvm
from mission_lib import write_lang

GAME = r'C:\Users\1qdeath\Games\IGI2\app'
LIST_QVM = os.path.join(GAME, 'MISSIONS', 'igi2.qvm')
ORIG = os.path.join(HERE, 'backup', 'original')
STATE = os.path.join(HERE, 'installed.json')
LANGS = ('english', 'USA')
RESFILES = ('missions', 'objectives', 'messages', 'menusystem')   # (menusystem: the loading-screen tips, level<id>tips/...)


def game_running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq igi2.exe'], capture_output=True, text=True).stdout.lower()
    return 'igi2.exe' in out


def backup_originals():
    o = os.path.join(ORIG, 'MISSIONS', 'igi2.qvm')
    if not os.path.exists(o):
        os.makedirs(os.path.dirname(o), exist_ok=True); shutil.copy2(LIST_QVM, o)
    o = os.path.join(ORIG, 'MENUSYSTEM', 'missionsprites.res')
    if not os.path.exists(o):
        os.makedirs(os.path.dirname(o), exist_ok=True); shutil.copy2(os.path.join(GAME, 'MENUSYSTEM', 'missionsprites.res'), o)
    o = os.path.join(ORIG, 'MENUSYSTEM', 'loadingscreen.res')
    if not os.path.exists(o):
        shutil.copy2(os.path.join(GAME, 'MENUSYSTEM', 'loadingscreen.res'), o)
    for lang in LANGS:
        for f in RESFILES:
            o = os.path.join(ORIG, 'LANGUAGE', lang, f + '.res')
            if not os.path.exists(o):
                os.makedirs(os.path.dirname(o), exist_ok=True)
                shutil.copy2(os.path.join(GAME, 'LANGUAGE', lang, f + '.res'), o)


def original_ids():
    custom = {(m['location'].lower(), m['folder'].lower()) for m in load_state().values()}
    ids = set()
    for loc in os.listdir(os.path.join(GAME, 'MISSIONS')):
        ld = os.path.join(GAME, 'MISSIONS', loc)
        if not os.path.isdir(ld):
            continue
        for lev in os.listdir(ld):
            mq = os.path.join(ld, lev, 'mission.qvm')
            if (loc.lower(), lev.lower()) in custom or not os.path.exists(mq):
                continue
            ver, st = igiqvm.decompile(open(mq, 'rb').read())
            ids |= {int(c.args[0]) for c in st if isinstance(c, igiqvm.Call) and c.name == 'DefineMission'}
    return ids


def original_progress():
    """the player's campaign progress before any custom mission was installed: {difficulty: index}"""
    import re
    p = os.path.join(ORIG, 'progress.json')
    if not os.path.exists(p):
        src = os.path.join(HERE, 'backup', 'config.qvm.before-ironfist')
        if not os.path.exists(src):
            src = os.path.join(GAME, 'config.qvm')
        ver, st = igiqvm.decompile(open(src, 'rb').read())
        prog = {a: int(b) for a, b in re.findall(r'GOActiveMission\((\d+), (\d+)\);', igiqvm.stmts_to_qsc(st))}
        os.makedirs(ORIG, exist_ok=True)
        json.dump(prog, open(p, 'w'))
    return json.load(open(p))


def fix_config(n_missions, removed_ids=()):
    """keep the player profile consistent: every campaign entry unlocked (index n-1), no stats for removed missions"""
    import re, time
    cfg = os.path.join(GAME, 'config.qvm')
    if not os.path.exists(cfg):
        return
    data = open(cfg, 'rb').read()
    os.makedirs(os.path.join(HERE, 'backup', 'config'), exist_ok=True)
    shutil.copy2(cfg, os.path.join(HERE, 'backup', 'config', 'config.qvm.%s' % time.strftime('%Y%m%d_%H%M%S')))
    import struct
    code_off, code_len = struct.unpack_from('<2I', data, 44)
    trailer = data[code_off + code_len:]                 # the game appends junk after the code; keep it
    ver, st = igiqvm.decompile(data)
    txt = igiqvm.stmts_to_qsc(st)
    base = original_progress()
    n_custom = len(load_state())
    txt = re.sub(r'GOActiveMission\((\d+), \d+\);',
                 lambda mm: 'GOActiveMission(%s, %d);' % (mm.group(1), n_missions - 1), txt)   # owner 10-27: every entry unlocked (all 19 originals too)
    for rid in removed_ids:
        txt = re.sub(r'GOPlayerMissionStats\(\s*%d,[^;]*;\n?' % rid, '', txt)
    open(cfg, 'wb').write(igiqvm.compile_stmts(igiqvm.parse_qsc(txt), ver) + trailer)


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def regenerate(state):
    """campaign list + language files = originals + all installed missions (newest first in the list)"""
    ver, st = igiqvm.decompile(open(os.path.join(ORIG, 'MISSIONS', 'igi2.qvm'), 'rb').read())
    ids = [int(c.args[0]) for c in st]
    # story order first: finishing a mission loads the NEXT one in this list (seen 10-10: Cedar Shadow -> Sandstorm)
    # Whiteout -> Sandstorm -> Sirocco -> Cedar Shadow -> Frostbite -> Iron Tsar -> Persian Dawn -> Iron Fist, then anything else
    # 10-16 M8 Eagle's Nest = 40, after Iron Tsar (28) and M7 Dark Harbor (39), before Persian Dawn (29).
    # 11-14 (Q26, orchestrator, owner 11-08 'two missions only'): the campaign is Sandstorm -> Sirocco and ENDS there. The list holds
    # only these two, so Sirocco is the LAST entry: after its stats the game takes the no-next-mission path (event 8) instead of
    # loading another mission. The old campaign (and the 19 originals) come back only with --with-originals / INSTALL_WITH_ORIGINALS=1.
    # (old list: [19, 30, 44, 20, 27, 38, 18, 28, 39, 40, 29, 41, 42, 43, 37])
    CAMPAIGN = [19, 30]
    WITH_ORIGINALS = '--with-originals' in sys.argv or os.environ.get('INSTALL_WITH_ORIGINALS') == '1'
    have = {m['id'] for m in state.values()}
    custom = [i for i in CAMPAIGN if i in have]
    if WITH_ORIGINALS:                                                # (11-14: any other installed custom mission only with the switch)
        custom += [m['id'] for m in sorted(state.values(), key=lambda m: m['order'], reverse=True) if m['id'] not in custom]
    top = [m['id'] for m in state.values() if m.get('top')]           # --test / --top: the mission under test first
    if not os.environ.get('INSTALL_INPLACE'):
        custom = top + [i for i in custom if i not in top]
    elif top and top[0] in custom:                                    # 10-18: INSTALL_INPLACE=1 (next-mission tests): the test mission starts, the list continues in
        k_ = custom.index(top[0]); custom = custom[k_:] + custom[:k_]  # campaign order after it (so 'next' is the real next); the rest wraps round behind
    ids = custom if (custom and not WITH_ORIGINALS) else custom + [i for i in ids if i not in custom]    # (11-14: stock 11-36 only with the switch, or with no custom mission installed)
    open(LIST_QVM, 'wb').write(igiqvm.compile_stmts([igiqvm.Call('DefineMissionListItem', [igiqvm.Int(i)]) for i in ids], ver))
    for lang in LANGS:
        for f in RESFILES:
            entries = {}
            for m in state.values():
                entries.update(m['text'].get(f, {}))
            src = os.path.join(ORIG, 'LANGUAGE', lang, f + '.res')
            dst = os.path.join(GAME, 'LANGUAGE', lang, f + '.res')
            if entries:
                write_lang(src, dst, lang, entries)
            else:
                shutil.copy2(src, dst)
    write_sprites()
    write_loadingscreens(state)
    write_introscreens(state)
    return ids


def write_loadingscreens(state):
    """loading pictures (owner 10-12): MENUSYSTEM/loadingscreen.res = the original + its generic picture without the
    'NEONIX PATCH' logo (loading/generic.jpg, work/loading/deneonix.py) + 'loading<id>.jpg' for every installed mission
    with a loading/<id>.jpg (igi2.exe 0x429140 looks up LOCAL:menusystem/loading%02d.jpg by mission id first)"""
    orig = os.path.join(ORIG, 'MENUSYSTEM', 'loadingscreen.res')
    if not os.path.exists(orig):
        return
    import ilff
    form, ch, hdr = ilff.read(orig)
    ch = list(ch)
    names = {d.rstrip(b'\0').decode('latin1'): i for i, (t, d, a) in enumerate(ch) if t == b'NAME'}
    ldir = os.path.join(HERE, 'loading')
    body_al = ch[names['LOCAL:menusystem/loading.jpg'] + 1][2]
    done = []
    gen = os.path.join(ldir, 'generic.jpg')
    if os.path.exists(gen):
        k = names['LOCAL:menusystem/loading.jpg'] + 1
        ch[k] = (ch[k][0], open(gen, 'rb').read(), ch[k][2])
        done.append('generic')
    for m in sorted(state.values(), key=lambda m: m['id']):
        p = os.path.join(ldir, '%d.jpg' % m['id'])
        nm = 'LOCAL:menusystem/loading%02d.jpg' % m['id']
        if not os.path.exists(p):
            continue
        if nm in names:
            ch[names[nm] + 1] = (b'BODY', open(p, 'rb').read(), ch[names[nm] + 1][2])
        else:
            ch += [(b'NAME', nm.encode('latin1') + b'\0', 4), (b'BODY', open(p, 'rb').read(), body_al)]
        done.append(str(m['id']))
    open(os.path.join(GAME, 'MENUSYSTEM', 'loadingscreen.res'), 'wb').write(ilff.write(form, ch, align=hdr[1], pad_last=True))
    print('loading pictures: %s' % ', '.join(done))


def write_sprites():
    """mission-select pictures: sprites/<name>.png -> '<name>.spr' in MENUSYSTEM/missionsprites.res (original +
    ours; the missions' DefineMission names the sprite, e.g. mission20.spr)"""
    import missionsprite as MS
    orig = os.path.join(ORIG, 'MENUSYSTEM', 'missionsprites.res')
    if not os.path.exists(orig):
        return
    dst = os.path.join(GAME, 'MENUSYSTEM', 'missionsprites.res')
    sdir = os.path.join(HERE, 'sprites')
    pngs = sorted(f for f in os.listdir(sdir) if f.lower().endswith('.png')) if os.path.isdir(sdir) else []
    if not pngs:
        shutil.copy2(orig, dst)
        return
    tpl = MS._template(open(orig, 'rb').read())
    n = MS.merge(orig, dst, {f[:-4] + '.spr': MS.make(os.path.join(sdir, f), tpl) for f in pngs})
    print('mission pictures: %d (%s)' % (n, ', '.join(f[:-4] for f in pngs)))


def move_saves(mission_id, label):
    """G43 root cause (11-15): the game applies a savegame by TASK ID with no check, so a mid-mission save of an OLD build lands on
    whatever task has that id in the new build (an old AI node on a new soldier: igi2.exe+0xfabc3 / 0x45cfd5 crashes on the owner's PC).
    Every install / uninstall of a mission moves its saves savegames/<a>-<b>-<id>-<slot>.igi2save to <game>/savegames_bak-<date>-<label>/
    (outside savegames/, so the menu no longer offers them). Never deletes. -> number moved"""
    import time
    src = os.path.join(GAME, 'savegames')
    if not os.path.isdir(src):
        return 0
    hits = []
    for f in sorted(os.listdir(src)):
        parts = f[:-len('.igi2save')].split('-') if f.lower().endswith('.igi2save') else []
        if len(parts) == 4 and parts[2] == str(mission_id) and os.path.isfile(os.path.join(src, f)):
            hits.append(f)
    if hits:
        dst = os.path.join(GAME, 'savegames_bak-%s-%s' % (time.strftime('%Y%m%d'), label))
        os.makedirs(dst, exist_ok=True)
        for f in hits:
            to = os.path.join(dst, f)
            if os.path.exists(to):                                   # (a second install the same day: keep both)
                to = os.path.join(dst, '%s.%s' % (f, time.strftime('%H%M%S')))
            shutil.move(os.path.join(src, f), to)
        print('savegames: %d mid-mission save(s) of mission %d moved to %s (an update invalidates mid-mission saves)' % (len(hits), mission_id, dst))
    else:
        print('savegames: no mid-mission save of mission %d' % mission_id)
    return len(hits)


ENDSCREEN = os.path.join('endscreen', 'congratulations.jpg')    # inside a build dir (sfcand.sh puts sf-story's committed picture there)


def _md5(p):
    import hashlib
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def endscreen_remove(meta):
    """delete the language-folder end pictures an earlier install of this mission wrote (only if still byte-identical: never a foreign file)"""
    for p, h in meta.get('endscreen_files', []):
        if os.path.isfile(p) and _md5(p) == h:
            os.remove(p)
            print('  end picture removed: %s' % p)
            d = os.path.dirname(p)
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        elif os.path.isfile(p):
            print('  end picture %s changed since install, left alone' % p)


def endscreen_check(build, state):
    """before anything is copied: refuse when a language-folder end picture exists that no installed mission wrote (a foreign file)"""
    if not os.path.isfile(os.path.join(build, ENDSCREEN)):
        return
    ours = {h for m in state.values() for p, h in m.get('endscreen_files', [])}
    if os.path.exists(INTRO_STATE):                                  # (fix1123 E2) our default end picture (write_introscreens) is ours too
        ours |= set(json.load(open(INTRO_STATE)).values())
    for lang in LANGS:
        dst = os.path.join(GAME, 'SCREENS', 'intro', lang, 'congratulations.jpg')
        if os.path.isfile(dst) and _md5(dst) not in ours:
            sys.exit('install.py: %s exists and is not ours - refusing to overwrite it (the end picture is installed only as a new file)' % dst)


def endscreen_install(build, meta):
    """SF_DESIGN 2.5 / I1 (R14): after the last mission's stats the engine shows SCREENS/intro/<language>/congratulations.jpg when it exists,
    else the stock / Neonix picture (introscreen.c 145-158). A build that carries endscreen/congratulations.jpg gets it as NEW files in the
    english + USA language folders; the stock SCREENS/intro/congratulations.jpg (Neonix) is never touched, a foreign file in a language
    folder is never overwritten; uninstall (and the next install of this mission) deletes ours again."""
    src = os.path.join(build, ENDSCREEN)
    if not os.path.isfile(src):
        return
    h = _md5(src)
    files = []
    for lang in LANGS:
        dst = os.path.join(GAME, 'SCREENS', 'intro', lang, 'congratulations.jpg')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        files.append([dst, h])
        print('  end picture: %s (%s)' % (dst, h))
    meta['endscreen_files'] = files


INTRO_SRC = os.path.join(HERE, 'screens', 'intro')             # (fix1123 E2) our intro / end pictures, one jpg per stock name
INTRO_STATE = os.path.join(HERE, 'installed_intro.json')         # language-folder files install.py wrote: {path: md5}


def write_introscreens(state):
    """(fix1123 E2) SCREENS/intro/<lang>/<name>.jpg = screens/intro/<name>.jpg for english + USA (the engine takes the language folder
    first). congratulations.jpg is skipped while an installed build carries its own (endscreen_install wrote it). Never overwrites a file
    we did not write; never touches SCREENS/intro/<name>.jpg itself (the Neonix pictures stay as they are, unused)."""
    if not os.path.isdir(INTRO_SRC):
        return
    rec = json.load(open(INTRO_STATE)) if os.path.exists(INTRO_STATE) else {}
    build_end = any(m.get('endscreen_files') for m in state.values())
    done, kept = [], []
    for f in sorted(os.listdir(INTRO_SRC)):
        if not f.lower().endswith('.jpg') or (f.lower() == 'congratulations.jpg' and build_end):
            continue
        src = os.path.join(INTRO_SRC, f)
        h = _md5(src)
        for lang in LANGS:
            dst = os.path.join(GAME, 'SCREENS', 'intro', lang, f)
            if os.path.isfile(dst):
                cur = _md5(dst)
                if cur == h:
                    rec[dst] = h
                    continue
                if rec.get(dst) != cur:
                    kept.append(dst)                             # a foreign file: leave it
                    continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            rec[dst] = h
            done.append('%s/%s' % (lang, f))
    json.dump(rec, open(INTRO_STATE, 'w'), indent=1)
    print('intro pictures: %s%s' % (', '.join(done) or 'up to date', ''.join('; NOT ours, left alone: %s' % k for k in kept)))


def install(name):
    if game_running():
        sys.exit('IGI 2 is running - close it first')
    build = os.path.join(HERE, 'build', name)
    meta = json.load(open(os.path.join(build, 'meta.json')))
    if meta.get('debug') and '--test' not in sys.argv:
        sys.exit('%s is a TEST build (debug variant) - refusing to install without --test' % name)
    if ('--test' in sys.argv or '--top' in sys.argv) and not os.environ.get('COMPUTERNAME', '').upper().startswith('IGI2-TEST'):
        # (11-02 owner order: the owner's PC only gets RELEASE copies. A --test install swaps out the release entry and its
        #  uninstall then deletes the shared folder = the release is gone. Test installs run on the rig via tools/vpstest.py.)
        sys.exit('install.py: --test / --top installs only run on the rig (tools/vpstest.py); this PC gets release copies only')
    originals = original_ids()
    if meta['id'] in originals:
        sys.exit('mission id %d belongs to an original mission' % meta['id'])
    loc_dir = os.path.join(GAME, 'MISSIONS', meta['location'])
    original_dirs = {d.lower() for d in os.listdir(loc_dir)} - {m['folder'].lower() for m in load_state().values()}
    if meta['folder'].lower() in original_dirs or meta['folder'].lower() in ('common', meta['base'].lower()):
        sys.exit('target folder %s would overwrite an original level folder' % meta['folder'])
    backup_originals()
    state = load_state()
    endscreen_check(build, state)
    for n in [n for n, m in state.items() if n != name and m['id'] == meta['id'] and m['folder'] == meta['folder']]:
        endscreen_remove(state.pop(n))                 # release <-> test build of the same mission: swap
    if name in state:
        endscreen_remove(state[name])
    clash = [n for n, m in state.items() if n != name and (m['id'] == meta['id'] or m['folder'] == meta['folder'])]
    if clash:
        sys.exit('id/folder clash with installed mission %s' % clash)
    target = os.path.join(GAME, 'MISSIONS', meta['location'], meta['folder'])
    base = os.path.join(GAME, 'MISSIONS', meta['location'], meta['base'])
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(base, target, ignore=shutil.ignore_patterns('mission.qvm', 'objects.qvm'))
    for f in ('mission.qvm', 'objects.qvm'):
        shutil.copy2(os.path.join(build, f), target)
    os.makedirs(os.path.join(target, 'ai'), exist_ok=True)      # (the multiplayer Jungle base ships no ai/ folder)
    for f in os.listdir(os.path.join(build, 'ai')):
        shutil.copy2(os.path.join(build, 'ai', f), os.path.join(target, 'ai', f))
    if os.path.isdir(os.path.join(build, 'graphs')):         # generated AI graphs (multiplayer bases ship none)
        os.makedirs(os.path.join(target, 'graphs'), exist_ok=True)
        for f in os.listdir(os.path.join(build, 'graphs')):
            shutil.copy2(os.path.join(build, 'graphs', f), os.path.join(target, 'graphs', f))
    if meta.get('own_common'):                                # the mission's own 'common' folder: MP models/textures
        src = os.path.join(GAME, 'MISSIONS', meta['location'], meta['own_common'])   # linked, sounds from the build
        dst = os.path.join(target, 'common')
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            if rel.split(os.sep)[0].lower() == 'sounds':
                continue
            os.makedirs(os.path.join(dst, rel), exist_ok=True)
            for f in files:
                try:
                    os.link(os.path.join(root, f), os.path.join(dst, rel, f))     # hard link: no extra disk space
                except OSError:
                    shutil.copy2(os.path.join(root, f), os.path.join(dst, rel, f))
    overlay = os.path.join(build, 'overlay')                    # generated map files: heightmaps, textures, forests ...
    if os.path.isdir(overlay):
        for root, dirs, files in os.walk(overlay):
            rel = os.path.relpath(root, overlay)
            os.makedirs(os.path.join(target, rel), exist_ok=True)
            for f in files:
                dst = os.path.join(target, rel, f)
                if os.path.exists(dst) and os.stat(dst).st_nlink > 1:
                    os.remove(dst)                              # never write through a hard link into an original
                shutil.copy2(os.path.join(root, f), dst)
    for f in meta.get('drop_files', []):                        # base-level files the mission must not inherit
        p_ = os.path.join(target, f)
        if os.path.isfile(p_):
            os.remove(p_)
    for sub in ('sounds', os.path.join('common', 'sounds')):   # sound banks made by the builder
        if os.path.isdir(os.path.join(build, sub)):
            for root, dirs, files in os.walk(os.path.join(build, sub)):
                rel = os.path.relpath(root, build)
                os.makedirs(os.path.join(target, rel), exist_ok=True)
                for f in files:
                    shutil.copy2(os.path.join(root, f), os.path.join(target, rel, f))
    fix_sound_banks(target, meta['location'], meta['folder'])
    meta['order'] = max([m['order'] for n, m in state.items() if n != name] + [0]) + 1     # last installed = top of the list
    for m_ in state.values():
        m_.pop('top', None)
    if '--test' in sys.argv or '--top' in sys.argv:
        meta['top'] = True
    endscreen_install(build, meta)
    state[name] = meta
    json.dump(state, open(STATE, 'w'), indent=1)
    ids = regenerate(state)
    fix_config(len(ids))
    print('installed %s (mission %d) -> %s' % (name, meta['id'], target))
    move_saves(meta['id'], name)
    print('campaign list:', ids)


def fix_sound_banks(target, location, folder):
    """every sounds.res must carry a PATH entry naming the folder it is loaded from, or the game silently registers
    none of its samples (copied level folders kept the original level's name: no alarm siren, ambience or voices)"""
    import soundbank as sb
    for root, dirs, files in os.walk(target):
        for f in files:
            if f.lower() != 'sounds.res':
                continue
            rel = os.path.relpath(root, target).replace(os.sep, '/').lower()
            want = 'LOCAL:missions/%s/%s/%s' % (location.lower(), folder.lower(), rel)
            p = os.path.join(root, f)
            name, n, problems = sb.check_bank(p, want)
            if problems:
                data = sb.rebase_bank(p, want, strict=False)                 # read BEFORE opening for write (that truncates)
                if os.stat(p).st_nlink > 1:                    # never write through a hard link into an original file
                    os.remove(p)
                open(p, 'wb').write(data)
                name2, n2, problems2 = sb.check_bank(p, want)
                assert not problems2 and n2 == n, (p, problems2)
                print('  sound bank fixed: %s (%d samples, was %s)' % (os.path.relpath(p, target), n, name))


def uninstall(name):
    if game_running():
        sys.exit('IGI 2 is running - close it first')
    state = load_state()
    meta = state.pop(name, None)
    if meta:
        target = os.path.join(GAME, 'MISSIONS', meta['location'], meta['folder'])
        if os.path.isdir(target):
            shutil.rmtree(target)
        endscreen_remove(meta)
    json.dump(state, open(STATE, 'w'), indent=1)                     # 10-23: before fix_config, which counts load_state() (was one mission stale)
    if os.path.exists(os.path.join(ORIG, 'MISSIONS', 'igi2.qvm')):
        ids = regenerate(state)
        fix_config(len(ids), [meta['id']] if meta else [])
    if meta:
        move_saves(meta['id'], 'uninstall-' + name)
    print('uninstalled', name)


def clear_test_stats():
    ids = [m['id'] for m in load_state().values()]
    fix_config(len(regenerate(load_state())), ids)
    print('cleared saved stats for custom missions', ids)


def status():
    for n, m in load_state().items():
        print(n, m['id'], m['location'] + '/' + m['folder'], 'base', m['base'])


if __name__ == '__main__':
    cmd = sys.argv[1]
    {'install': lambda: install(sys.argv[2]), 'uninstall': lambda: uninstall(sys.argv[2]), 'status': status, 'clear-test-stats': clear_test_stats}[cmd]()
