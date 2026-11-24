"""patch_files.py - list exactly which files of the owner's game are the Patch patch's (11-23, package worker).

Compares a reconstruction of the pristine GOG+Patch game (the live folder, with the Patch version put back for every file we changed
later: exe, loadingscreen.res, mainmenu.qvm, dgVoodoo.conf) against app-backup-before-patch (GOG only). Our own files (missions,
IGI2HD.asi + hd, language-folder intro pictures, backups, logs, savegames, profile) are left out.
-> work/release/PATCH_FILES.json (+ .txt). Read-only on the game folders.  python -P work/release/patch_files.py
"""
import hashlib, json, os, re

LIVE = r'C:\Users\1qdeath\Games\IGI2\app'
PRE = r'C:\Users\1qdeath\Games\IGI2\app-backup-before-patch'
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_VERSION_OF = {                              # files we changed after Patch: where Patch's own version is kept
    'igi2.exe': os.path.join(REPO, 'backup', 'igi2.exe.original-6afe26e3'),
    'MENUSYSTEM/loadingscreen.res': os.path.join(REPO, 'backup', 'original', 'MENUSYSTEM', 'loadingscreen.res'),
    'MENUSYSTEM/mainmenu.qvm': os.path.join(LIVE, 'MENUSYSTEM', 'mainmenu.qvm.bak-20261103-menufix'),
    'dgVoodoo.conf': os.path.join(LIVE, 'dgVoodoo.conf.bak-20261012-035722-pre-854'),
}
for r in ['MENUSYSTEM/missionsprites.res', 'MISSIONS/igi2.qvm'] + ['LANGUAGE/%s/%s.res' % (l, f) for l in ('english', 'USA')
                                                                for f in ('missions', 'objectives', 'messages', 'menusystem')]:
    PATCH_VERSION_OF[r] = os.path.join(REPO, 'backup', 'original', r.replace('/', os.sep))
OURS = re.compile(r'(?i)(\.bak|\.log$|\.rpt$|^savegames|^config\.qvm$|^warninglog\.txt$|^igi2hd\.asi|^hd/|^screens/intro/(english|usa)/|'
                  r'^missions/multiplayer/(sandstorm_sp|sirocco_sp)/)')


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def walk(d):
    out = {}
    for root, dirs, files in os.walk(d):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), d).replace(os.sep, '/')
            out[rel.lower()] = (rel, os.path.join(root, f))
    return out


live, pre = walk(LIVE), walk(PRE)
res = {'added': [], 'changed': [], 'md5': {}}
for k, (rel, p) in sorted(live.items()):
    if OURS.search(rel):
        continue
    src = PATCH_VERSION_OF.get(rel, p)
    h = md5(src)
    if k not in pre:
        res['added'].append(rel)
    elif md5(pre[k][1]) != h:
        res['changed'].append(rel)
    else:
        continue
    res['md5'][rel] = h
json.dump(res, open(os.path.join(HERE, 'PATCH_FILES.json'), 'w'), indent=1)
with open(os.path.join(HERE, 'PATCH_FILES.txt'), 'w', newline='\r\n') as f:
    f.write('Files of the GOG + Patch IGI 2 that the Patch patch added or changed (vs the GOG game before Patch), %d + %d.\n'
            'None of them is in the Sandstorm package. Made by work/release/patch_files.py.\n\nADDED\n' % (len(res['added']), len(res['changed'])))
    f.writelines('  %s\n' % r for r in res['added'])
    f.write('\nCHANGED\n')
    f.writelines('  %s\n' % r for r in res['changed'])
print('patch: %d added, %d changed' % (len(res['added']), len(res['changed'])))
