"""release.py - build the Sandstorm-only release outputs from scratch (11-23, package worker). Called by make_release.sh.

    python -P work/release/release.py --exe <igi2.exe> [--display <folder>] [--build f1123_1 --md5 86c04c0d...] [--only A,NOFLY,B]

Outputs (all rebuilt from scratch every run; nothing in the live game or C:\\igi2noclip is ever written):
  A      Desktop\\IGI2\\Sandstorm TEST - fly mode\\   full game copy (owner's own GOG copy, personal use): live game minus backups/junk,
         Sirocco removed, campaign [19], clean profile (his settings, no progress/stats), empty savegames, fly mode (IGI2Fly.asi +
         flymode_places.txt + flymode\\FLYMODE_KEYS.txt), a no-Python launcher, READ ME FIRST.txt, REMOVE FLY MODE.bat.
  NOFLY  Desktop\\IGI2\\Sandstorm TEST\\              = A with fly mode removed (made by running A's own REMOVE FLY MODE logic).
  B      dist\\Sandstorm_v1.0\\ (+ .zip)               public delta package: Sandstorm only, no Patch file, no game file that the
         player's own install already has; exe\\ part separate (needs Patch permission, see EXE_NOTICE.txt).
Every output gets MD5SUMS.txt (md5 of every file) and the run checks them back.

--display <folder>: the display worker's release folder (work/release/display/). If it holds dgVoodoo.conf it replaces the game
copy's / goes into the package's exe\\display\\; any *.bat in it is copied next to igi2.exe in A/NOFLY (and into exe\\display\\ in B).
"""
import argparse, hashlib, importlib.util, json, os, re, shutil, struct, subprocess, sys, time, zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPO, 'tools'))
sys.path.insert(1, HERE)
import igiqvm

LIVE = r'C:\Users\1qdeath\Games\IGI2\app'
PRE_PATCH = r'C:\Users\1qdeath\Games\IGI2\app-backup-before-patch'
NOCLIP = r'C:\igi2noclip'
DESK = os.path.join(os.path.expanduser('~'), 'Desktop', 'IGI2')
OUT_A = os.path.join(DESK, 'Sandstorm TEST - fly mode')
OUT_NOFLY = os.path.join(DESK, 'Sandstorm TEST')
PKG_NAME = 'Sandstorm_v1.0'
OUT_B = os.path.join(REPO, 'dist', PKG_NAME)
SCR = os.environ.get('RELEASE_SCRATCH', os.path.join(REPO, 'work', 'release', '_scratch'))
MID, FOLDER, LOC, BASE = 19, 'sandstorm_sp', 'multiplayer', 'sandstorm'
LANGS = ('english', 'USA')
RESFILES = ('missions', 'objectives', 'messages', 'menusystem')
# junk that never goes into a copy (backups, logs, crash dumps, our tools' leftovers)
JUNK_XF = ['*.bak', '*.bak-*', '*.bak*', '*.log', '*.RPT', '*.dmp', '*.mdmp', 'warninglog.txt', 'IGI2Fly.asi', 'IGI2Noclip.asi',
           'flymode*', 'noclip*', '*.tmp']
JUNK_XD = ['savegames', 'savegames*', 'marks', 'marks_sessions', 'flymode', 'dump', 'old_v1']
# the Patch patch's own files (found 11-23 by md5 against app-backup-before-patch; see PATCH_FILES.txt)
END_PICTURE = os.path.join(HERE, 'endscreen', 'congratulations.jpg')     # made by make_endscreen_sandstorm.py
PATCH_ONLY = ['IGI2 Patch.asi', 'version.dll', 'settings.ini']


def say(s):
    print(s, flush=True)


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def sha1(p):
    h = hashlib.sha1()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def walk(d):
    for root, dirs, files in os.walk(d):
        dirs.sort()
        for f in sorted(files):
            yield os.path.relpath(os.path.join(root, f), d).replace(os.sep, '/')


def tree_md5(d, skip=()):
    return {f: md5(os.path.join(d, f)) for f in walk(d) if f not in skip}


def write_md5sums(d):
    t = tree_md5(d, skip=('MD5SUMS.txt',))
    with open(os.path.join(d, 'MD5SUMS.txt'), 'w', newline='\r\n') as f:
        for k, v in t.items():
            f.write('%s *%s\n' % (v, k))
    return t


def check_md5sums(d):
    bad = 0
    n = 0
    for line in open(os.path.join(d, 'MD5SUMS.txt')):
        h, rel = line.rstrip('\r\n').split(' *', 1)
        n += 1
        p = os.path.join(d, rel)
        if not os.path.isfile(p) or md5(p) != h:
            bad += 1
            say('  MD5 MISMATCH %s' % rel)
    extra = [f for f in walk(d) if f != 'MD5SUMS.txt']
    if len(extra) != n:
        say('  file count %d != MD5SUMS %d' % (len(extra), n)); bad += 1
    say('md5 check %s: %d files, %d bad' % (d, n, bad))
    return bad


def du(d):
    return sum(os.path.getsize(os.path.join(d, f)) for f in walk(d))


def rmtree(d):
    if os.path.isdir(d):
        assert os.path.normcase(os.path.abspath(d)) not in (os.path.normcase(LIVE), os.path.normcase(NOCLIP)), d
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', d], check=False)
        if os.path.isdir(d):
            shutil.rmtree(d)


def robocopy(src, dst, xf=(), xd=()):
    cmd = ['robocopy', src, dst, '/MIR', '/XJ', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP']
    if xf:
        cmd += ['/XF'] + list(xf)
    if xd:
        cmd += ['/XD'] + list(xd)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode >= 8:
        sys.exit('robocopy failed (%d): %s' % (r.returncode, r.stdout[-1500:]))


def game_running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq igi2.exe'], capture_output=True, text=True).stdout.lower()
    return 'igi2.exe' in out


# ------------------------------------------------------------------ the repo installer, pointed at a copy
def load_installer(game, stage):
    """import the repo's install.py as a module and point every global at <game> + a staging folder (the live paths are never used)"""
    spec = importlib.util.spec_from_file_location('igi2_install_rel', os.path.join(REPO, 'install.py'))
    I = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(I)
    I.GAME = game
    I.LIST_QVM = os.path.join(game, 'MISSIONS', 'igi2.qvm')
    I.HERE = stage
    I.ORIG = os.path.join(stage, 'backup', 'original')
    I.STATE = os.path.join(stage, 'installed.json')
    I.INTRO_SRC = os.path.join(stage, 'screens', 'intro')
    I.INTRO_STATE = os.path.join(stage, 'installed_intro.json')
    I.game_running = lambda: False          # (checked once by release.py itself: a copy can't be running)
    return I


def make_stage(stage, build_dir, end_picture):
    """staging HERE for install.py: build/sandstorm -> the release build, only Sandstorm's sprite + loading picture (no Sirocco
    mission30.png / 30.jpg), our generic loading card, intro pictures without the Sirocco 'TO BE CONTINUED' end picture"""
    rmtree(stage)
    os.makedirs(os.path.join(stage, 'build'))
    shutil.copytree(build_dir, os.path.join(stage, 'build', 'sandstorm'))
    shutil.copytree(os.path.join(REPO, 'backup', 'original'), os.path.join(stage, 'backup', 'original'))
    os.makedirs(os.path.join(stage, 'sprites'))
    shutil.copy2(os.path.join(REPO, 'sprites', 'sandstorm.png'), os.path.join(stage, 'sprites'))
    os.makedirs(os.path.join(stage, 'loading'))
    for f in ('%d.jpg' % MID, 'generic.jpg'):
        shutil.copy2(os.path.join(REPO, 'loading', f), os.path.join(stage, 'loading', f))
    os.makedirs(os.path.join(stage, 'screens', 'intro'))
    for f in ('codemasters.jpg', 'innerloop.jpg', 'panvision.jpg'):
        shutil.copy2(os.path.join(REPO, 'screens', 'intro', f), os.path.join(stage, 'screens', 'intro', f))
    if end_picture:
        shutil.copy2(end_picture, os.path.join(stage, 'screens', 'intro', 'congratulations.jpg'))


def clean_profile(cfg):
    """the owner's settings + key bindings stay; campaign progress = first entry, every mission stat removed, 1920x1080 display
    (dgVoodoo 'Resolution = max' scales to the laptop screen anyway; 2560x1440 may not be in a laptop's mode list)"""
    data = open(cfg, 'rb').read()
    code_off, code_len = struct.unpack_from('<2I', data, 44)
    trailer = data[code_off + code_len:]
    ver, st = igiqvm.decompile(data)
    txt = igiqvm.stmts_to_qsc(st)
    txt = re.sub(r'GOActiveMission\((\d+), \d+\);', r'GOActiveMission(\1, 0);', txt)
    txt = re.sub(r'GOPlayerMissionStats\([^;]*;\n?', '', txt)
    txt = re.sub(r'GOGfxDisp\(\d+, \d+, (\d+)\);', r'GOGfxDisp(1920, 1080, \1);', txt)
    open(cfg, 'wb').write(igiqvm.compile_stmts(igiqvm.parse_qsc(txt), ver) + trailer)
    assert 'GOPlayerMissionStats' not in igiqvm.stmts_to_qsc(igiqvm.decompile(open(cfg, 'rb').read())[1])


# ------------------------------------------------------------------ A: full test copy with fly mode
def keep_owner_data(game):
    """a rebuild wipes the old copy: first move the owner's F9 marks and savegames out of it (Desktop/IGI2/kept from <copy> <time>/)"""
    if not os.path.isdir(game):
        return
    items = [x for x in ('flymode_marks.txt', 'marks', 'marks_sessions', 'savegames') if os.path.exists(os.path.join(game, x))
             and (os.path.isfile(os.path.join(game, x)) or os.listdir(os.path.join(game, x)))]
    if not items:
        return
    dst = os.path.join(DESK, 'kept from %s %s' % (os.path.basename(game), time.strftime('%Y%m%d-%H%M%S')))
    os.makedirs(dst)
    for x in items:
        shutil.move(os.path.join(game, x), os.path.join(dst, x))
    say('kept the owner data of the old copy (%s) in %s' % (', '.join(items), dst))


def build_A(exe, display, build_dir):
    say('== A: %s' % OUT_A)
    keep_owner_data(OUT_A)
    rmtree(OUT_A)
    os.makedirs(OUT_A)
    xd = JUNK_XD + [os.path.join(LIVE, 'MISSIONS', LOC, FOLDER), os.path.join(LIVE, 'MISSIONS', LOC, 'sirocco_sp')]
    robocopy(LIVE, OUT_A, JUNK_XF, xd)
    for d in os.listdir(os.path.join(OUT_A, 'MISSIONS', LOC)):
        assert d.lower() not in ('sirocco_sp', FOLDER), d
    # the exe under test (v22c now, v22d later) + display setup
    os.remove(os.path.join(OUT_A, 'igi2.exe'))
    shutil.copy2(exe, os.path.join(OUT_A, 'igi2.exe'))
    if display and os.path.isfile(os.path.join(display, 'dgVoodoo.conf')):
        shutil.copy2(os.path.join(display, 'dgVoodoo.conf'), os.path.join(OUT_A, 'dgVoodoo.conf'))
    # end picture: our TO BE CONTINUED picture without the Sirocco line (make_endscreen_sandstorm.py)
    os.makedirs(os.path.join(OUT_A, 'savegames'))
    stage = os.path.join(SCR, 'stage_A')
    make_stage(stage, build_dir, END_PICTURE)
    for lang in LANGS:                                     # language-folder intro pictures: rewritten by write_introscreens
        d = os.path.join(OUT_A, 'SCREENS', 'intro', lang)
        if os.path.isdir(d):
            shutil.rmtree(d)
    I = load_installer(OUT_A, stage)
    I.install('sandstorm')
    ver, st = igiqvm.decompile(open(os.path.join(OUT_A, 'MISSIONS', 'igi2.qvm'), 'rb').read())
    ids = [int(x.args[0]) for x in st]
    assert ids == [MID], ids
    clean_profile(os.path.join(OUT_A, 'config.qvm'))
    # check: the mission folder is byte-identical to the owner's installed one when the same build is installed there
    live_tree = tree_md5(os.path.join(LIVE, 'MISSIONS', LOC, FOLDER))
    a_tree = tree_md5(os.path.join(OUT_A, 'MISSIONS', LOC, FOLDER))
    if md5(os.path.join(LIVE, 'MISSIONS', LOC, FOLDER, 'objects.qvm')) == md5(os.path.join(build_dir, 'objects.qvm')):
        diff = sorted(f for f in set(live_tree) | set(a_tree) if live_tree.get(f) != a_tree.get(f))
        say('A sandstorm_sp vs live sandstorm_sp (same build): %d differing files %s' % (len(diff), diff[:10]))
    # fly mode
    add_fly(OUT_A, exe)
    if display:
        for f in os.listdir(display):
            if f.lower().endswith(('.bat', '.cmd')):
                shutil.copy2(os.path.join(display, f), os.path.join(OUT_A, f))
    sirocco_scan(OUT_A, game_copy=True)
    write_md5sums(OUT_A)
    return I


def add_fly(game, exe):
    spec = importlib.util.spec_from_file_location('flypy', os.path.join(REPO, 'work', 'noclip', 'fly.py'))
    F = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(F)
    ok, bad = F.hooks_ok(os.path.join(game, 'igi2.exe'))
    if not ok:
        say('WARNING: %s does not match the fly-mode hooks at %s: IGI2Fly.asi will refuse to hook (no fly mode) - needs a new asi'
            % (exe, ', '.join(bad)))
    shutil.copy2(os.path.join(NOCLIP, 'flymode', 'IGI2Fly.asi'), os.path.join(game, 'IGI2Fly.asi'))
    assert md5(os.path.join(game, 'IGI2Fly.asi')) == md5(os.path.join(REPO, 'work', 'noclip', 'IGI2Fly.asi')), 'IGI2Fly.asi differs from repo'
    os.makedirs(os.path.join(game, 'flymode'), exist_ok=True)
    keys = open(os.path.join(NOCLIP, 'flymode', 'FLYMODE_KEYS.txt'), encoding='utf-8', errors='replace').read()
    keys = keys.replace('Start: desktop  "IGI2 Fly Mode - Sandstorm"  or  "IGI2 Fly Mode - Sirocco".\n'
                        '       It first copies what is installed now (a few seconds), then the game opens.',
                        'Start: double-click "START GAME.bat" in the game folder (fly mode is always loaded in this copy).\n'
                        '       The game opens with Operation Sandstorm in the mission list.')
    keys = keys.replace(r'C:\igi2noclip\marks\mark_001.bmp', r'<game folder>\marks\mark_001.bmp')
    keys = keys.replace(r'C:\igi2noclip\marks_sessions', r'<game folder>\marks_sessions')
    keys = keys.replace("tell Claude 'marks done'", "send the file + the marks folder")
    keys = keys.replace('"IGI2 Fly Mode - Sirocco"', '').replace(' or  ', ' ')
    assert 'Sirocco' not in keys, keys
    open(os.path.join(game, 'flymode', 'FLYMODE_KEYS.txt'), 'w', newline='\r\n').write(keys.replace('\r\n', '\n'))
    places = json.load(open(os.path.join(REPO, 'work', 'noclip', 'places.json')))['sandstorm']
    with open(os.path.join(game, 'flymode_places.txt'), 'w', newline='\r\n') as f:
        f.write('# written by work/release/release.py - places for F3 / F4\nmission=Sandstorm\n')
        for p in places:
            f.write('%s|%d|%d|%d|%.4f\n' % (p['name'].replace('|', '/'), p['x'], p['y'], p['z'], p.get('yaw', 0.0)))
    tpl = os.path.join(HERE, 'test_src')
    for f in os.listdir(tpl):
        crlf(os.path.join(tpl, f), os.path.join(game, f))
    crlf(os.path.join(HERE, 'nofly_src', 'READ ME FIRST.txt'), os.path.join(game, 'flymode', 'READ ME FIRST (no fly mode).txt'))


def crlf(src, dst):
    """text files for Windows (cmd.exe needs CRLF in .bat files)"""
    t = open(src, encoding='utf-8').read().replace(chr(13) + chr(10), chr(10))
    open(dst, 'w', encoding='utf-8', newline=chr(13) + chr(10)).write(t)


def remove_fly(game):
    """the same steps as A's 'REMOVE FLY MODE.bat' (kept in step with it)"""
    for f in ('IGI2Fly.asi', 'flymode_places.txt', 'flymode_marks.txt', 'flymode.log', 'flymode_maxdamage.txt', 'REMOVE FLY MODE.bat'):
        p = os.path.join(game, f)
        if os.path.exists(p):
            os.remove(p)
    for d in ('flymode', 'marks', 'marks_sessions'):
        if os.path.isdir(os.path.join(game, d)):
            shutil.rmtree(os.path.join(game, d))
    crlf(os.path.join(HERE, 'nofly_src', 'READ ME FIRST.txt'), os.path.join(game, 'READ ME FIRST.txt'))


def build_NOFLY():
    say('== NOFLY: %s' % OUT_NOFLY)
    keep_owner_data(OUT_NOFLY)
    rmtree(OUT_NOFLY)
    robocopy(OUT_A, OUT_NOFLY)
    os.remove(os.path.join(OUT_NOFLY, 'MD5SUMS.txt'))
    remove_fly(OUT_NOFLY)
    left = [f for f in walk(OUT_NOFLY) if re.search(r'(?i)fly', f) and not f.lower().startswith(('missions/', 'common/', 'humanplayer/', 'animtrigger/'))]
    assert not left, left
    write_md5sums(OUT_NOFLY)


# ------------------------------------------------------------------ B: public delta package
def base_ref(game):
    """what the package installer puts into the mission folder before copying its own files: base level (minus qvm) + MP common (minus sounds)"""
    ref = {}
    b = os.path.join(game, 'MISSIONS', LOC, BASE)
    c = os.path.join(game, 'MISSIONS', LOC, 'common')
    for f in walk(b):
        if os.path.basename(f) not in ('mission.qvm', 'objects.qvm'):
            ref[f] = os.path.join(b, f)
    for f in walk(c):
        if f.split('/')[0].lower() != 'sounds':
            ref['common/' + f] = os.path.join(c, f)
    return ref


def build_B(exe, display, build_dir, A):
    say('== B: %s' % OUT_B)
    rmtree(OUT_B)
    os.makedirs(OUT_B)
    tgt = os.path.join(A, 'MISSIONS', LOC, FOLDER)            # the reference install (made by the repo installer on a GOG+Patch copy)
    tree = tree_md5(tgt)
    ref_neo = base_ref(LIVE)                                 # GOG + Patch: the live game's MP folders are untouched by us
    ref_gog = base_ref(PRE_PATCH)                           # GOG without Patch
    mneo = {f: md5(p) for f, p in ref_neo.items()}
    mgog = {f: md5(p) for f, p in ref_gog.items()}
    files, from_game_patch = [], []
    for f, h in tree.items():
        if mneo.get(f) == h or mgog.get(f) == h:
            if mneo.get(f) == h and mgog.get(f) != h:
                from_game_patch.append(f)                   # Patch content (e.g. its multiplayer textures): taken from the player's game, never shipped
            continue
        files.append(f)
        d = os.path.join(OUT_B, 'mission', FOLDER, f)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(os.path.join(tgt, f), d)
    # Patch content inside the builder's own .res files (textures / voice clips it pulled from the owner's GOG+Patch game):
    # each such chunk is swapped for the GOG game's chunk of the same name (patch_chunks.py); the package tree follows
    import patch_chunks as NC
    swapped, nogog = [], []
    for f in files:
        if f.lower().endswith('.res'):
            for name, src, how in NC.depatch(os.path.join(OUT_B, 'mission', FOLDER, f)):
                (swapped if how == 'swapped' else nogog).append('%s: %s <- %s' % (f, name, src))
            tree[f] = md5(os.path.join(OUT_B, 'mission', FOLDER, f))
    with open(os.path.join(HERE, 'PATCH_SWAPPED.txt'), 'w', newline=chr(13) + chr(10)) as fh:
        fh.write('Patch-only chunks swapped for the GOG originals in the package copy: %d; left without a GOG version: %d' % (len(swapped), len(nogog)) + chr(10))
        fh.writelines('  swapped %s' % x + chr(10) for x in swapped)
        fh.writelines('  NO GOG VERSION %s' % x + chr(10) for x in nogog)
    say('B: %d Patch chunks swapped for GOG ones, %d without a GOG version %s' % (len(swapped), len(nogog), nogog))
    assert not nogog, nogog
    # expected tree per base: shipped files as built, everything else = that base's own file
    tree_gog = {f: (h if f in files else mgog.get(f)) for f, h in tree.items()}
    missing_gog = [f for f, h in tree_gog.items() if h is None]
    assert not missing_gog, ('files a GOG-only base cannot provide', missing_gog[:10])
    deleted = sorted(set(f for f in set(ref_neo) | set(ref_gog) if f not in tree))
    # shipped files must not be byte-identical to any Patch file
    patch_md5 = set(md5(os.path.join(LIVE, f)) for f in PATCH_ONLY) | neo_changed_md5()
    leak = [f for f in files if tree[f] in patch_md5]
    assert not leak, ('Patch file in the package', leak)
    # shared files: language texts (identical in GOG and GOG+Patch) + mission pictures; loading pictures are patched in by the installer
    shared = {}
    for rel in ['MENUSYSTEM/missionsprites.res'] + ['LANGUAGE/%s/%s.res' % (l, f) for l in LANGS for f in RESFILES]:
        o_neo, o_gog = md5(os.path.join(LIVE_ORIG(), rel)), md5(os.path.join(PRE_PATCH, rel))
        d = os.path.join(OUT_B, 'shared', rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(os.path.join(A, rel), d)
        shared[rel.replace('/', '\\')] = dict(orig_md5=sorted({o_neo, o_gog}), new_md5=md5(d))
    os.makedirs(os.path.join(OUT_B, 'shared', 'loading'))
    shutil.copy2(os.path.join(REPO, 'loading', '%d.jpg' % MID), os.path.join(OUT_B, 'shared', 'loading', 'loading%02d.jpg' % MID))
    shutil.copy2(os.path.join(REPO, 'loading', 'generic.jpg'), os.path.join(OUT_B, 'shared', 'loading', 'loading.jpg'))
    # exe part (separate: derived from the Patch exe = GOG exe + its large-address flag)
    ex = os.path.join(OUT_B, 'exe')
    os.makedirs(os.path.join(ex, 'hd'))
    shutil.copy2(exe, os.path.join(ex, 'igi2.exe'))
    shutil.copy2(os.path.join(LIVE, 'IGI2HD.asi'), ex)
    for f in sorted(os.listdir(os.path.join(LIVE, 'hd'))):
        if f.lower().endswith('.tga'):
            shutil.copy2(os.path.join(LIVE, 'hd', f), os.path.join(ex, 'hd', f))
    if display and os.path.isdir(display):
        for f in os.listdir(display):
            if f.lower() == 'dgvoodoo.conf' or f.lower().endswith(('.bat', '.cmd')):
                os.makedirs(os.path.join(ex, 'display'), exist_ok=True)
                shutil.copy2(os.path.join(display, f), os.path.join(ex, 'display', f))
    crlf(os.path.join(HERE, 'pkg_src', 'EXE_NOTICE.txt'), os.path.join(ex, 'EXE_NOTICE.txt'))
    exe_orig = {'gog': sha1(os.path.join(PRE_PATCH, 'igi2.exe')), 'patch': sha1(os.path.join(REPO, 'backup', 'igi2.exe.original-6afe26e3'))}
    # campaign list files made here (the installer has no Python to compile a qvm): Sandstorm only / Sandstorm + the 19 originals
    lo = os.path.join(REPO, 'backup', 'original', 'MISSIONS', 'igi2.qvm')
    assert md5(lo) == md5(os.path.join(PRE_PATCH, 'MISSIONS', 'igi2.qvm'))
    ver, st = igiqvm.decompile(open(lo, 'rb').read())
    orig_ids = [int(x.args[0]) for x in st]
    os.makedirs(os.path.join(OUT_B, 'shared', 'list'))
    for name, ids in (('igi2_sandstorm.qvm', [MID]), ('igi2_sandstorm_originals.qvm', [MID] + [i for i in orig_ids if i != MID])):
        open(os.path.join(OUT_B, 'shared', 'list', name), 'wb').write(
            igiqvm.compile_stmts([igiqvm.Call('DefineMissionListItem', [igiqvm.Int(i)]) for i in ids], ver))
    lst = dict(orig_md5=[md5(lo)], only='igi2_sandstorm.qvm', with_originals='igi2_sandstorm_originals.qvm', n_with_originals=1 + len(orig_ids))
    os.makedirs(os.path.join(OUT_B, 'shared', 'intro'))
    shutil.copy2(END_PICTURE, os.path.join(OUT_B, 'shared', 'intro', 'congratulations.jpg'))
    manifest = dict(version='1.0', name='Operation Sandstorm', campaign=[MID],
                    mission=dict(name='Operation Sandstorm', id=MID, location=LOC, base=BASE, folder=FOLDER, own_common='common',
                                 files=sorted(files), deleted=deleted, tree_patch=tree, tree_gog=tree_gog,
                                 size=sum(os.path.getsize(os.path.join(tgt, f)) for f in tree)),
                    shared=shared, loading=['loading%02d.jpg' % MID, 'loading.jpg'], list=lst,
                    exe=dict(new_sha1=sha1(exe), orig_sha1=exe_orig, build=os.path.basename(build_dir)))
    json.dump(manifest, open(os.path.join(OUT_B, 'manifest.json'), 'w'), indent=0)
    os.makedirs(os.path.join(OUT_B, 'installer'))
    shutil.copy2(os.path.join(HERE, 'pkg_src', 'installer', 'sandstorm.ps1'), os.path.join(OUT_B, 'installer'))
    for f in ('install.cmd', 'uninstall.cmd', 'README.md', 'README_AR.md', 'CREDITS.md'):
        crlf(os.path.join(HERE, 'pkg_src', f), os.path.join(OUT_B, f))
    open(os.path.join(OUT_B, 'VERSION'), 'w').write('1.0')
    say('B: %d mission files shipped (%d MB), %d taken from the player game, %d of them Patch content on a Patch base: %s'
        % (len(files), sum(os.path.getsize(os.path.join(OUT_B, 'mission', FOLDER, f)) for f in files) >> 20,
           len(tree) - len(files), len(from_game_patch), from_game_patch))
    sirocco_scan(OUT_B, game_copy=False)
    write_md5sums(OUT_B)
    z = OUT_B + '.zip'
    if os.path.exists(z):
        os.remove(z)
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in walk(OUT_B):
            zf.write(os.path.join(OUT_B, f), PKG_NAME + '/' + f)
    with zipfile.ZipFile(z) as zf:
        assert zf.testzip() is None
    say('zip: %s (%d MB)' % (z, os.path.getsize(z) >> 20))


def LIVE_ORIG():
    return os.path.join(REPO, 'backup', 'original')


_NEO = None


def neo_changed_md5():
    """md5 of every file the Patch patch changed or added (GOG+Patch pristine vs GOG), excluding our own installs"""
    global _NEO
    if _NEO is None:
        p = os.path.join(HERE, 'PATCH_FILES.json')
        _NEO = set(json.load(open(p))['md5'].values()) if os.path.exists(p) else set()
    return _NEO


def sirocco_scan(d, game_copy):
    """no Sirocco anywhere: file names, text files, the mission list, language files, sprites, loading pictures"""
    hits = []
    for f in walk(d):
        low = f.lower()
        if 'sirocco' in low:
            hits.append('name: ' + f)
        if low.endswith(('.txt', '.md', '.json', '.bat', '.py', '.ini', '.res', '.qvm', '.conf')):
            if os.path.getsize(os.path.join(d, f)) < 64 << 20:
                data = open(os.path.join(d, f), 'rb').read()
                if re.search(rb'(?i)sirocco|mission30\.spr|loading30\.jpg|Mission 30 ', data):
                    hits.append('content: ' + f)
    lst = os.path.join(d, 'MISSIONS', 'igi2.qvm')
    if os.path.exists(lst):
        ids = [int(x.args[0]) for x in igiqvm.decompile(open(lst, 'rb').read())[1]]
        if 30 in ids:
            hits.append('campaign list has 30')
    say('sirocco scan %s: %s' % (d, hits or 'clean'))
    assert not hits, hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', required=True)
    ap.add_argument('--display', default='')
    ap.add_argument('--build', default='f1123_1')
    ap.add_argument('--md5', default='86c04c0d96a61c7e02159e82d3a52b3b')
    ap.add_argument('--only', default='A,NOFLY,B')
    a = ap.parse_args()
    only = set(a.only.upper().split(','))
    build_dir = os.path.join(REPO, 'build', a.build)
    if md5(os.path.join(build_dir, 'objects.qvm')) != a.md5:
        sys.exit('build %s objects.qvm is not %s' % (a.build, a.md5))
    if not os.path.isfile(a.exe):
        sys.exit('exe not found: ' + a.exe)
    if a.display and not os.path.isdir(a.display):
        say('display folder %s not there yet: using the live game dgVoodoo.conf (A) / the installer edit (B)' % a.display)
        a.display = ''
    if game_running():
        say('note: igi2.exe is running (the owner plays): only reading his folder')
    os.makedirs(SCR, exist_ok=True)
    t = time.time()
    say('exe %s sha1 %s | build %s %s' % (a.exe, sha1(a.exe)[:8], a.build, a.md5[:8]))
    if 'A' in only:
        build_A(a.exe, a.display, build_dir)
    if 'NOFLY' in only:
        build_NOFLY()
    if 'B' in only:
        build_B(a.exe, a.display, build_dir, OUT_A)
    bad = 0
    for d, k in ((OUT_A, 'A'), (OUT_NOFLY, 'NOFLY'), (OUT_B, 'B')):
        if k in only:
            bad += check_md5sums(d)
            say('%s: %s  %.2f GB' % (k, d, du(d) / 2 ** 30))
    rmtree(SCR)
    say('release done in %.0f s, %d md5 problems' % (time.time() - t, bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
