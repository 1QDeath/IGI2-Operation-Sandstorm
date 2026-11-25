"""release2.py - the owner's release spec of 11-23 (package worker): three CLEAN outputs.

  1 FULL   dist/Sandstorm_Full/   Setup.exe + Sandstorm-N.dat : the ORIGINAL GOG game (pristine files, app-backup-before-patch) + Sandstorm
                                  + our exe + display setup + our ASI loader / HD menu; campaign = Sandstorm only (owner's own copy)
  2 ADDON  dist/Sandstorm_Addon/  Setup.exe + Sandstorm.dat   : add-on for a GOG IGI 2, plain or patched (base detected): Sandstorm after
                                  the 19 original missions, unlocked, our end picture
  3 FLY    Desktop/IGI2/Sandstorm TEST - fly mode/            : output 1's game + fly mode, for the owner's laptop
No output carries a patch file or the patch's name (scanned).
Clean = only what the game needs + installer/uninstaller + one short readme (no logs, md5 lists, test files, backups, our scripts).
Setup.exe = work/release/setup/Setup.cs compiled with the .NET Framework 4 csc (no downloads). md5 checks stay internal (work/release/_check).

    python -P work/release/release2.py --exe <igi2.exe> [--display work/release/display] [--build f1123_1 --md5 <32>] [--only FULL,ADDON,FLY]
"""
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import release as R                                     # helpers + the reference install of the release build into a game copy
import patch_chunks as NC
igiqvm = R.igiqvm

REPO = R.REPO
DIST = os.path.join(REPO, 'dist')
OUT_FULL = os.path.join(DIST, 'Sandstorm_Full')
OUT_ADDON = os.path.join(DIST, 'Sandstorm_Addon')
OUT_FLY = R.OUT_A
SCR = os.path.join(HERE, '_scratch2')
CHECK = os.path.join(HERE, '_check')
SETUP_SRC = os.path.join(HERE, 'setup')
AVATAR = r'C:\Users\1qdeath\Pictures\Discord_avatar.png'
ART = os.path.join(HERE, 'installer_art')        # welcome.png / header.png / icon.ico (Jones in the sandstorm), used when present
CSC = r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
FWDIR = os.path.dirname(CSC)
PART = 1900 * 1024 * 1024                               # each data file stays under 2 GB
MID = R.MID
GOG_ID = '1207658666'
BRAND = {'made_by': 'Made by 1QDeath', 'discord': 'Discord: 1QDeath', 'title': 'Operation Sandstorm'}
ASILOADER = os.path.join(HERE, 'asiloader', 'version.dll')   # our own ASI loader (asiloader.c): loads IGI2HD.asi / IGI2Fly.asi
EXTRA_RES = ('854x480, 1024x768, 1280x720, 1280x800, 1280x1024, 1366x768, 1440x900, 1600x900, 1600x1200, 1680x1050, '
             '1920x1080, 1920x1200, 2560x1080, 2560x1440, 2560x1600, 3840x2160')       # (coordinator 11-23: 16 = dgVoodoo max)
SHARP_CONF = {'Antialiasing': '4x', 'Filtering': '16'}    # the owner's look, put back after the display script's Sharp setting
MPA_EXE = r'C:\Users\1qdeath\.claude\uploads\8e3f0c2a-bb0b-44dc-a11d-32989ee56748\b09d6b97-igi2.exe'   # a real other-version exe (owner, 11-24)
PATCH_MARK = 'IGI2 Patch.asi'          # present = a GOG game with the community widescreen patch (other base tree)
CLEAN_JUNK = re.compile(r'(?i)(\.bak|\.log$|\.rpt$|^md5sums\.txt$|^warninglog\.txt$|^flymode|^marks|\.tmp$|^savegames/.+|'
                        r'read me first|^start game\.bat$|^remove fly mode\.bat$|\.display-backup$)')

say = R.say
md5 = R.md5
walk = R.walk


def clean_tree(d):
    """the clean rule: drop logs, md5 lists, backups, test/fly leftovers (savegames/ stays as an empty folder)"""
    gone = []
    for f in list(walk(d)):
        if CLEAN_JUNK.search(f):
            os.remove(os.path.join(d, f)); gone.append(f)
    for root, dirs, files in os.walk(d, topdown=False):
        for x in dirs:
            p = os.path.join(root, x)
            if not os.listdir(p) and os.path.relpath(p, d).lower() not in ('savegames',) and re.search(r'(?i)^(marks|flymode)', x):
                os.rmdir(p)
    return gone


def readme(path, text):
    open(path, 'w', encoding='utf-8', newline='\r\n').write(text.strip('\n') + '\n')


# ------------------------------------------------------------------ the full game stage (Patch base): the release install on a copy
def full_stage(exe, display, build_dir):
    """the pristine GOG game (no patch file) + the release install of the build, done by the repo installer on this copy"""
    st = os.path.join(SCR, 'full')
    R.rmtree(st)
    R.robocopy(R.PRE_PATCH, st, R.JUNK_XF, R.JUNK_XD)
    os.remove(os.path.join(st, 'igi2.exe'))
    shutil.copy2(exe, os.path.join(st, 'igi2.exe'))
    os.makedirs(os.path.join(st, 'savegames'), exist_ok=True)
    stage = os.path.join(SCR, 'stage_full')
    R.make_stage(stage, build_dir, R.END_PICTURE)
    for rel in ['MENUSYSTEM/loadingscreen.res', 'MENUSYSTEM/missionsprites.res', 'MISSIONS/igi2.qvm'] + \
               ['LANGUAGE/%s/%s.res' % (l, f) for l in R.LANGS for f in R.RESFILES]:            # the GOG originals
        shutil.copy2(os.path.join(R.PRE_PATCH, rel), os.path.join(stage, 'backup', 'original', rel))
    I = R.load_installer(st, stage)
    I.install('sandstorm')
    ids = [int(x.args[0]) for x in igiqvm.decompile(open(os.path.join(st, 'MISSIONS', 'igi2.qvm'), 'rb').read())[1]]
    assert ids == [MID], ids
    R.clean_profile(os.path.join(st, 'config.qvm'))
    # the builder's own .res files carry 18 textures / voice clips taken from the patched game: the GOG ones instead
    msp = os.path.join(st, 'MISSIONS', R.LOC, R.FOLDER)
    sw = 0
    for f in walk(msp):
        p = os.path.join(msp, f)
        if f.lower().endswith('.res'):
            if os.stat(p).st_nlink > 1:                # never write through a hard link into the base game
                data = open(p, 'rb').read(); os.remove(p); open(p, 'wb').write(data)
            res = NC.depatch(p)
            assert all(x[2] == 'swapped' for x in res), res
            sw += len(res)
    # display: our setup script; the GOG dgVoodoo.conf keeps Resolution = max, 4x AA, 16x filtering (the owner's look) + our mode list
    if display and os.path.isfile(os.path.join(display, 'IGI2_Display_Setup.cmd')):
        shutil.copy2(os.path.join(display, 'IGI2_Display_Setup.cmd'), st)
    conf = os.path.join(st, 'dgVoodoo.conf')
    t = open(conf, 'rb').read().decode('latin1')
    t = re.sub(r'(?m)^(ExtraEnumeratedResolutions[ \t]*=)[^\r\n]*', lambda m: m.group(1) + ' ' + EXTRA_RES, t)
    dx = re.search(r'(?ms)^\[DirectX\].*?(?=^\[)', t)
    sec = dx.group(0)
    for k, v in list(SHARP_CONF.items()) + [('Resolution', 'max')]:
        sec, n = re.subn(r'(?m)^(%s[ \t]*=)[^\r\n]*' % k, lambda m: m.group(1) + ' ' + v, sec)
        assert n == 1, k
    t = t[:dx.start()] + sec + t[dx.end():]
    # v1.3: the two keys a plain GOG copy lacked (dxcore.dll crash at start): refresh rates listed, borderless fullscreen
    for secname, k, v in (('General', 'EnumerateRefreshRates', 'true'), ('GeneralExt', 'FullscreenAttributes', 'fake'), ('GeneralExt', 'PresentationModel', 'flip_discard'), ('GeneralExt', 'FPSLimit', '60')):
        m2 = re.search(r'(?ms)^\[%s\][^\r\n]*\r?\n(.*?)(?=^\[|\Z)' % secname, t)
        body, n = re.subn(r'(?m)^(%s[ \t]*=)[^\r\n]*' % k, lambda m: m.group(1) + ' ' + v, m2.group(1))
        assert n == 1, k
        t = t[:m2.start(1)] + body + t[m2.end(1):]
    open(conf, 'wb').write(t.encode('latin1'))
    # our ASI loader + HD menu add-on
    shutil.copy2(ASILOADER, os.path.join(st, 'version.dll'))
    shutil.copy2(os.path.join(R.LIVE, 'IGI2HD.asi'), st)
    os.makedirs(os.path.join(st, 'hd'), exist_ok=True)
    for f in os.listdir(os.path.join(R.LIVE, 'hd')):
        if f.lower().endswith('.tga'):
            shutil.copy2(os.path.join(R.LIVE, 'hd', f), os.path.join(st, 'hd', f))
    gone = clean_tree(st)
    readme(os.path.join(st, 'Sandstorm - README.txt'), FULL_README)
    neo = set(json.load(open(os.path.join(HERE, 'PATCH_FILES.json')))['md5'].values())
    hit = [f for f in walk(st) if md5(os.path.join(st, f)) in neo]
    assert not hit, ('patch files in the full game', hit[:10])
    say('full stage: %s (GOG base, %d chunks swapped, %d junk files dropped, 0 patch files)' % (st, sw, len(gone)))
    return st


FULL_README = '''
OPERATION SANDSTORM - IGI 2

Start the game from the desktop shortcut or igi2.exe and pick Operation Sandstorm.
Picture settings: IGI2_Display_Setup.cmd. Uninstall: Windows Settings > Apps.
Frame rate: capped at 60 - change FPSLimit in dgVoodoo.conf for more.
'''

ADDON_README = '''
OPERATION SANDSTORM 1.6 - a new IGI 2 mission

Run Setup.exe, pick your IGI 2 folder, Install. Sandstorm comes after the original missions and is unlocked.
Uninstall: Windows Settings > Apps > Operation Sandstorm (every changed file comes back).
Frame rate: capped at 60 - change FPSLimit in dgVoodoo.conf (game folder) for more.
'''

FLY_README = '''
OPERATION SANDSTORM - TEST COPY WITH FLY MODE (Made by 1QDeath)

Start igi2.exe. Only Operation Sandstorm is in the mission list. Fresh profile, no saves.

FLY MODE
  F6        fly on / off (off = you drop to the floor below, no damage)
  Mouse     look, you fly where you look      W A S D  move      Space / E  up      C / Ctrl / Q  down
  Shift     hold = 4 x faster                 -  /  =  slower / faster (1 ... 128 m/s)
  F4 / F3   next / previous named place (objectives, secrets, cutscene sets)     F5  back to before the last jump
  While flying you cannot die, walls do not stop you, fire / use / map are off until F6.

F9 MARK = report a bug at the exact spot: saves the place + a screen picture, numbered #1, #2 ...
  list: flymode_marks.txt     pictures: marks\\mark_001.bmp ...     (both in this folder)
  After each "what is wrong here:" write what you saw, then send the file and the marks folder.

'''


# ------------------------------------------------------------------ 3: fly copy
def fly_copy(st, exe):
    say('== FLY: %s' % OUT_FLY)
    R.keep_owner_data(OUT_FLY)
    R.rmtree(OUT_FLY)
    R.robocopy(st, OUT_FLY)
    os.remove(os.path.join(OUT_FLY, 'Sandstorm - README.txt'))
    for f in ('IGI2_Display_Setup.cmd',):
        if os.path.exists(os.path.join(OUT_FLY, f)):
            os.remove(os.path.join(OUT_FLY, f))                      # (laptop test copy: no scripts)
    R.add_fly(OUT_FLY, exe)
    for f in ('START GAME.bat', 'REMOVE FLY MODE.bat', 'READ ME FIRST.txt'):
        os.remove(os.path.join(OUT_FLY, f))
    shutil.rmtree(os.path.join(OUT_FLY, 'flymode'))
    readme(os.path.join(OUT_FLY, 'Sandstorm fly mode - README.txt'), FLY_README)
    assert os.path.isfile(os.path.join(OUT_FLY, 'IGI2Fly.asi')) and os.path.isfile(os.path.join(OUT_FLY, 'flymode_places.txt'))


# ------------------------------------------------------------------ 2: add-on payload for the original GOG game
def addon_payload(st, exe, display):
    pay = os.path.join(SCR, 'addon')
    R.rmtree(pay)
    os.makedirs(pay)
    LOC, BASE, FOLDER = R.LOC, R.BASE, R.FOLDER
    tgt = os.path.join(st, 'MISSIONS', LOC, FOLDER)
    tree = R.tree_md5(tgt)
    mneo = {f: md5(p) for f, p in R.base_ref(R.LIVE).items()}
    mgog = {f: md5(p) for f, p in R.base_ref(R.PRE_PATCH).items()}
    files = []
    for f, h in tree.items():
        if mgog.get(f) == h:                           # the player's own file goes there (on a patched game: its patched version)
            continue
        d = os.path.join(pay, 'mission', f)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(os.path.join(tgt, f), d)
        files.append(f)
    swapped = []
    for f in files:
        if f.lower().endswith('.res'):
            swapped += [x for x in NC.depatch(os.path.join(pay, 'mission', f)) if x[2] == 'swapped']
            assert not [x for x in NC.depatch(os.path.join(pay, 'mission', f)) if x[2] != 'swapped']
    tree_gog, tree_patch = {}, {}
    for f in tree:
        tree_gog[f] = md5(os.path.join(pay, 'mission', f)) if f in files else mgog.get(f)
        tree_patch[f] = md5(os.path.join(pay, 'mission', f)) if f in files else mneo.get(f)
    assert None not in tree_gog.values(), [f for f, h in tree_gog.items() if h is None][:5]
    assert None not in tree_patch.values(), [f for f, h in tree_patch.items() if h is None][:5]
    deleted = sorted(f for f in set(mgog) | set(mneo) if f not in tree)
    shared = {}      # (v1.1: no whole language / menu files any more - Setup adds our entries to the player's own files, any version)
    meta = json.load(open(os.path.join(build_dir_of(st), 'meta.json')))
    lang = {f: meta['text'][f] for f in R.RESFILES if meta['text'].get(f)}
    # the mission picture: the chunks our install added to missionsprites.res (by name, vs the GOG original)
    import recipe as RC0
    gname = {n for n, t, d, a in RC0.pairs(os.path.join(R.PRE_PATCH, 'MENUSYSTEM', 'missionsprites.res'))[2] if n}
    sprites = {}
    os.makedirs(os.path.join(pay, 'shared', 'sprites'))
    for n, t, d, a in RC0.pairs(os.path.join(st, 'MENUSYSTEM', 'missionsprites.res'))[2]:
        if n and n not in gname and t == b'BODY':
            k = 'shared/sprites/%d.bin' % len(sprites)
            open(os.path.join(pay, k.replace('/', os.sep)), 'wb').write(d)
            sprites[n] = k
    assert sprites, 'no mission picture found'
    os.makedirs(os.path.join(pay, 'shared', 'loading'))
    shutil.copy2(os.path.join(REPO, 'loading', '%d.jpg' % MID), os.path.join(pay, 'shared', 'loading', 'loading%02d.jpg' % MID))
    shutil.copy2(os.path.join(REPO, 'loading', 'generic.jpg'), os.path.join(pay, 'shared', 'loading', 'loading.jpg'))
    os.makedirs(os.path.join(pay, 'shared', 'intro'))
    shutil.copy2(R.END_PICTURE, os.path.join(pay, 'shared', 'intro', 'congratulations.jpg'))
    # the mission list: the 19 originals, then Sandstorm LAST (finishing it = the end of the campaign = our end picture)
    lo = os.path.join(R.PRE_PATCH, 'MISSIONS', 'igi2.qvm')
    ver, sts = igiqvm.decompile(open(lo, 'rb').read())
    ids = [int(x.args[0]) for x in sts if int(x.args[0]) != MID] + [MID]
    open(os.path.join(pay, 'shared', 'igi2.qvm'), 'wb').write(
        igiqvm.compile_stmts([igiqvm.Call('DefineMissionListItem', [igiqvm.Int(i)]) for i in ids], ver))
    # a profile for a game that was never started (no config.qvm yet): first-run profile, everything up to Sandstorm unlocked
    cfg = open(os.path.join(REPO, 'backup', 'config.qvm.after-firstrun'), 'rb').read()
    co, cl = struct.unpack_from('<2I', cfg, 44)
    v2, s2 = igiqvm.decompile(cfg)
    txt = igiqvm.stmts_to_qsc(s2)
    txt = re.sub(r'GOActiveMission\((\d+), \d+\);', lambda m: 'GOActiveMission(%s, %d);' % (m.group(1), len(ids) - 1), txt)
    txt = re.sub(r'GOPlayerMissionStats\([^;]*;\n?', '', txt)
    open(os.path.join(pay, 'shared', 'config_default.qvm'), 'wb').write(igiqvm.compile_stmts(igiqvm.parse_qsc(txt), v2) + cfg[co + cl:])
    os.makedirs(os.path.join(pay, 'exe', 'hd'))
    shutil.copy2(exe, os.path.join(pay, 'exe', 'igi2.exe'))
    hd = []        # (GitHub-clean: the HD menu pictures are upscales of the game's own art -> not in the add-on; no ASI loader needed then)
    extra_res = EXTRA_RES
    if display and os.path.isfile(os.path.join(display, 'IGI2_Display_Setup.cmd')):
        os.makedirs(os.path.join(pay, 'display'))
        shutil.copy2(os.path.join(display, 'IGI2_Display_Setup.cmd'), os.path.join(pay, 'display'))
    # ---- GitHub-clean: no game content. Every .res becomes a recipe (references into the player's own game + our chunks);
    #      igi2.exe is not shipped: Setup.exe patches the player's own exe with our byte patches
    import recipe as RC
    os.makedirs(os.path.join(pay, 'recipe'))
    def root_gog(rel):
        return os.path.join(R.PRE_PATCH, rel)
    orig_set = {os.path.normcase(r) for r in walk(os.path.join(REPO, 'backup', 'original'))}
    def root_patch(rel):
        if os.path.normcase(rel.replace('\\', '/')) in orig_set:
            return os.path.join(REPO, 'backup', 'original', rel)        # the patched game's own language / menu files, before our installs
        return os.path.join(R.LIVE, rel)
    recipes, ref_total, own_total = [], 0, 0
    targets = [('mission', f, os.path.join(pay, 'mission', f)) for f in files if f.lower().endswith('.res')] + \
              []
    for k, (kind, rel, path) in enumerate(targets):
        want = md5(path)
        binname = 'recipe/%03d.bin' % k
        rec, refb, ownb = RC.res_recipe(path, os.path.join(pay, binname))
        blob = open(os.path.join(pay, binname), 'rb').read()
        got, _ = RC.resolve(rec, blob, root_gog)
        assert hashlib.md5(got).hexdigest() == want, ('recipe does not rebuild', rel)
        gotp, other = RC.resolve(rec, blob, root_patch)
        if kind == 'mission':
            tree_patch[rel] = hashlib.md5(gotp).hexdigest()
        os.remove(path)
        recipes.append(dict(kind=kind, rel=rel, bin=binname, rec=rec))
        ref_total += refb; own_total += ownb
    files = [f for f in files if not f.lower().endswith('.res')]
    # mission files that are byte-identical to a file of the player's game (e.g. stock AI squad scripts): copied from it at install
    whole = RC.gog_files()
    copies = {}
    for f in list(files):
        h = md5(os.path.join(pay, 'mission', f))
        if h in whole:
            copies[f] = whole[h]
            os.remove(os.path.join(pay, 'mission', f))
            files.remove(f)
    gog_exe = os.path.join(R.PRE_PATCH, 'igi2.exe'); neo_exe = os.path.join(REPO, 'backup', 'igi2.exe.original-6afe26e3')
    exe_patch = RC.exe_patch2(gog_exe, exe, [gog_exe, neo_exe])       # (v1.1: by content - every replaced byte must hold the GOG original)
    for k in (gog_exe, neo_exe):
        out, err = RC.apply_exe_patch2(open(k, 'rb').read(), exe_patch)
        assert out == open(exe, 'rb').read(), (k, err)
    for k in [MPA_EXE] if os.path.exists(MPA_EXE) else []:
        out, err = RC.apply_exe_patch2(open(k, 'rb').read(), exe_patch)
        say('exe patch on the community 1.3 exe: %s' % (err or 'all %d runs apply' % len(exe_patch['runs'])))
    os.remove(os.path.join(pay, 'exe', 'igi2.exe'))
    say('addon copies from the player game: %d files' % len(copies))
    say('addon recipes: %d .res files, %d MB taken from the player game at install, %d MB of our own chunks; exe patch %d runs + %d tail bytes'
        % (len(recipes), ref_total >> 20, own_total >> 20, len(exe_patch['runs']), len(exe_patch['tail']) // 2))
    readme(os.path.join(pay, 'Sandstorm - README.txt'), ADDON_README)
    exe_orig = [R.sha1(os.path.join(R.PRE_PATCH, 'igi2.exe')), R.sha1(os.path.join(REPO, 'backup', 'igi2.exe.original-6afe26e3'))]
    setup = dict(mode='addon', product='Operation Sandstorm', version='1.6', key='IGI2_OperationSandstorm', lang=lang, sprites=sprites,
                 publisher='1QDeath', made_by=BRAND['made_by'], discord=BRAND['discord'], thanks='',
                 welcome='This adds Operation Sandstorm, a new single-player mission, to your IGI 2: Covert Strike (any version: '
                         'GOG, retail / CD with the official patches, other stores, community patches). Your original missions stay; '
                         'Sandstorm comes after them in the mission list and is unlocked at once.',
                 gog_id=GOG_ID, default_dir='', folder=FOLDER, location=LOC, base=BASE, own_common='common',
                 files=sorted(files), deleted=deleted, tree=tree_gog, tree_patch=tree_patch, patch_mark=PATCH_MARK, hd=hd, shared=shared,
                 loading=['loading%02d.jpg' % MID, 'loading.jpg'], exe_orig_sha1=exe_orig, exe_new_sha1=R.sha1(exe), exe_patch=exe_patch, recipes=recipes, copies=copies,
                 n_ids=len(ids), extra_res=extra_res, sharp_conf=SHARP_CONF, size=sum(os.path.getsize(os.path.join(tgt, f)) for f in tree), mission_id=MID)
    say('addon payload: %d mission files, %d Patch chunks swapped for GOG ones, list %s' % (len(files), len(swapped), ids))
    return pay, setup


_BUILD = {}


def build_dir_of(st):
    return _BUILD['dir']


def full_setup(st):
    size = sum(os.path.getsize(os.path.join(st, f)) for f in walk(st))
    return dict(mode='full', product='IGI 2 - Operation Sandstorm', version='1.6', key='IGI2_OperationSandstorm_Full',
                publisher='1QDeath', made_by=BRAND['made_by'], discord=BRAND['discord'], thanks='',
                welcome='This installs IGI 2: Covert Strike with Operation Sandstorm, a new single-player mission.',
                default_dir=r'C:\Games\IGI2 Sandstorm', size=size, mission_id=MID, sharp_conf=SHARP_CONF)


# ------------------------------------------------------------------ packing + Setup.exe
def pack(src, out, setup, name):
    """src tree -> <out>/<name>-<n>.dat zip parts (deflate level 9, each < 2 GB) + Setup.exe; setup.json goes into part 1"""
    R.rmtree(out)
    os.makedirs(out)
    files = sorted(walk(src))
    setup['files_total'] = len(files)
    setup['bytes_total'] = sum(os.path.getsize(os.path.join(src, f)) for f in files)
    parts, cur, n = [], None, 0
    def newpart():
        nonlocal cur, n
        if cur:
            cur.close()
        n += 1
        p = os.path.join(out, '%s-%d.dat' % (name, n)) if setup['mode'] == 'full' else os.path.join(out, '%s.dat' % name)
        parts.append(p)
        cur = zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=False)
    newpart()
    cur.writestr('_setup/placeholder', b'')
    for f in files:
        if os.path.getsize(parts[-1]) + os.path.getsize(os.path.join(src, f)) // 2 > PART and setup['mode'] == 'full':
            newpart()
        cur.write(os.path.join(src, f), f)
    cur.close()
    setup['parts'] = [os.path.basename(p) for p in parts]
    if setup['mode'] != 'full':
        assert len(parts) == 1
    # setup.json into part 1 (re-open in append mode)
    with zipfile.ZipFile(parts[0], 'a', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr('_setup/setup.json', json.dumps(setup))
    for p in parts:
        assert os.path.getsize(p) < 2 ** 31 - 1, p
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None, p
    shutil.copy2(setup_exe(), os.path.join(out, 'Setup.exe'))
    say('packed %s: %s' % (out, ', '.join('%s %d MB' % (os.path.basename(p), os.path.getsize(p) >> 20) for p in parts)))


_EXE = None


def setup_exe():
    global _EXE
    if _EXE:
        return _EXE
    from PIL import Image
    b = os.path.join(SCR, 'setupbuild')
    os.makedirs(b, exist_ok=True)
    ico = os.path.join(b, 'avatar.ico')
    im = Image.open(AVATAR).convert('RGBA')
    im.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    png = os.path.join(b, 'avatar.png')
    im.resize((256, 256), Image.LANCZOS).save(png)
    _EXE = os.path.join(b, 'Setup.exe')
    refs = ['System.dll', 'System.Core.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll', 'System.Web.Extensions.dll',
            'Microsoft.CSharp.dll', os.path.join(FWDIR, 'System.IO.Compression.dll'), os.path.join(FWDIR, 'System.IO.Compression.FileSystem.dll')]
    cmd = [CSC, '/nologo', '/target:winexe', '/platform:anycpu', '/optimize+', '/out:' + _EXE, '/win32icon:' + ico,
           '/resource:%s,avatar.png' % png] + ['/resource:%s,%s' % (os.path.join(ART, f), f) for f in ('welcome.png', 'header.png')
                                                if os.path.isfile(os.path.join(ART, f))] +           ['/reference:' + r for r in refs] + [os.path.join(SETUP_SRC, 'Setup.cs')]
    if os.path.isfile(os.path.join(ART, 'icon.ico')):
        cmd = [x if not x.startswith('/win32icon:') else '/win32icon:' + os.path.join(ART, 'icon.ico') for x in cmd]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit('csc failed:\n' + r.stdout[-4000:] + r.stderr[-2000:])
    return _EXE


def scan(d, word, label):
    hits = []
    for f in walk(d):
        if re.search(word, f, re.I):
            hits.append('name ' + f)
        p = os.path.join(d, f)
        if os.path.getsize(p) < 300 << 20 and re.search(word.encode(), open(p, 'rb').read(), re.I):
            hits.append('content ' + f)
    say('%s scan %s for %s: %s' % (label, d, word, hits or 'clean'))
    return hits


def check_record(d, tag):
    """internal md5 record of an output (kept OUTSIDE the output, work/release/_check/<tag>.md5)"""
    os.makedirs(CHECK, exist_ok=True)
    t = R.tree_md5(d)
    open(os.path.join(CHECK, tag + '.md5'), 'w').write(''.join('%s *%s\n' % (h, f) for f, h in t.items()))
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', required=True)
    ap.add_argument('--display', default=os.path.join(HERE, 'display'))
    ap.add_argument('--build', default='f1123_1')
    ap.add_argument('--md5', default='86c04c0d96a61c7e02159e82d3a52b3b')
    ap.add_argument('--only', default='FULL,ADDON,FLY')
    a = ap.parse_args()
    only = set(a.only.upper().split(','))
    build_dir = os.path.join(REPO, 'build', a.build)
    _BUILD['dir'] = build_dir
    if md5(os.path.join(build_dir, 'objects.qvm')) != a.md5:
        sys.exit('build %s objects.qvm is not %s' % (a.build, a.md5))
    t0 = time.time()
    R.rmtree(SCR)
    os.makedirs(SCR)
    say('exe %s sha1 %s | build %s %s' % (a.exe, R.sha1(a.exe)[:8], a.build, a.md5[:8]))
    st = full_stage(a.exe, a.display, build_dir)
    R.sirocco_scan(st, game_copy=True)
    bad = []
    if 'FLY' in only:
        fly_copy(st, a.exe)
        bad += scan(OUT_FLY, 'sirocco', 'FLY') + scan(OUT_FLY, 'patch', 'FLY')
        check_record(OUT_FLY, 'fly')
    if 'ADDON' in only:
        pay, setup = addon_payload(st, a.exe, a.display)
        bad += scan(pay, 'sirocco', 'ADDON') + scan(pay, 'patch', 'ADDON')
        pack(pay, OUT_ADDON, setup, 'Sandstorm')
        check_record(pay, 'addon_payload')
        bad += scan(OUT_ADDON, 'patch', 'ADDON output')
    if 'FULL' in only:
        bad += scan(st, 'patch', 'FULL')
        check_record(st, 'full_payload')
        pack(st, OUT_FULL, full_setup(st), 'Sandstorm')
        bad += scan(OUT_FULL, 'patch', 'FULL output')
    for d in (OUT_FULL, OUT_ADDON, OUT_FLY):
        if os.path.isdir(d):
            say('%s  %.2f GB, %d files' % (d, R.du(d) / 2 ** 30, len(list(walk(d)))))
    R.rmtree(SCR)
    say('release2 done in %.0f s, %d scan hits' % (time.time() - t0, len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
