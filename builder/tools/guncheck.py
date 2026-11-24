"""guncheck.py <build dir | objects.qvm | objects.qsc> [--quiet] : build gate for cutscene / posed actors' guns (owner 11-15 S10, S21).

The engine draws an EditBoneObj's WeaponModel only while the clip it plays has an ATTA entry named 'weapon' (X3_CUTSCENES.md 2.2:
1018 of the 1244 clips have it; tense_to_kneel, crouch_jump_land, scientist_* ... do not). So:
  GUNLESS  an ARMED actor (WeaponModel not '' / 'none', or a WeaponModel Expression) on a clip WITHOUT 'weapon':
           the gun vanishes for that clip's length ("they hold air and aim with air, then the gun appears after 1-2 s").
  AIR      an UNARMED actor on a clip whose 'weapon' sits in the RIGHT hand (bone 24 = the two-hand rifle pose):
           he holds an invisible rifle. The originals never do it (their unarmed men use only the clips in ORIG_UNARMED).
  UNKNOWN  a clip name the game does not have (the actor freezes / plays nothing).
Every EditBoneObj of the level is checked, cutscene or play. Exit 1 on any hit. --quiet prints only the summary line.
Clip data: COMMON/models/new.res + common.res (anims/<clip>.iff, ATTA records of 80 bytes: name 16 bytes, bone index int at +68)."""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ilff, igiqvm
from qast import tasks, lit

from mission_lib import GAME                                # (the same game path every builder uses, also on the node14 build host)
RES = [os.path.join(GAME, 'COMMON', 'models', 'new.res'), os.path.join(GAME, 'COMMON', 'models', 'common.res')]
# clips the 19 original SP levels give to actors with no weapon (read from work/originals/data/*.pkl, 11-15); the right-hand ones among
# them (cutscene_talk1/2 are bone 23) are gestures the originals accept without a gun
ORIG_UNARMED = {'anya_at_keyboard', 'anya_pose_idle', 'anya_talking', 'climb_fence_with_transform', 'climb_ladder', 'corpse', 'cutscene_talk1',
                'cutscene_talk2', 'fly_chopper', 'freefall_anim', 'generic_walk', 'hack_computer', 'hacking', 'hands_on_head', 'igiagent_signaling_to_jones',
                'jones_airlift', 'jones_at_ease_looking_left', 'jones_hanging_on_truck', 'jones_in_back_of_truck', 'jones_in_ekrano',
                'jones_jumps_running_from_wall', 'jones_jumps_with_chute', 'jones_recovers', 'kneeling_by_parachute', 'out_of_airvent', 'preripcord',
                'priboi_injured_leg_talk', 'priboy_bed_still', 'priboy_bed_talking', 'priboy_driving_truck', 'priboy_goes_through_briefcase',
                'priboy_in_back_of_truck', 'push_button_1st', 'ripcord', 'scientist_confused_studying', 'scientist_kneeling_consolework',
                'scientist_leaning_studying', 'scientist_standing_studying', 'senator_at_desk_looking_right', 'senator_at_desk_looks_up_right',
                'slide_wire', 'stand_nogun', 'stand_with_chute', 'turn_winch', 'white_idle', 'white_stand_look_forward_talk', 'white_stand_look_right_talk',
                'wo_talk_look_forward', 'wo_talk_look_left'}
_CL = None


def clips():
    """clip name -> (seconds or None, bone of its 'weapon' entry or None)"""
    global _CL
    if _CL is not None:
        return _CL
    import json
    secs = {k: d['sec'] for k, d in json.load(open(os.path.join(HERE, '..', 'work', 'originals', 'data', 'anim_durations.json'))).items()}
    out = {}
    for p in RES:
        form, ch, h = ilff.read(open(p, 'rb').read())
        for n, t, body in ilff.entries(ch):
            if not (n and n.lower().endswith('.iff') and '/anims/' in n.lower().replace('local:', '/')):
                continue
            k = n.split('/')[-1][:-4].lower()
            if k in out:
                continue
            a = {c[0]: c[1] for c in ilff.read(body)[1]}.get(b'ATTA') or b''
            bone = None
            for i in range(0, len(a) - 79, 80):
                if a[i:i + 16].split(b'\0')[0] == b'weapon':
                    bone = struct.unpack_from('<i', a, i + 68)[0]
                    break
            out[k] = (secs.get(k), bone)
    _CL = out
    return out


def load(path):
    if os.path.isdir(path):
        path = os.path.join(path, 'objects.qvm')
    if path.endswith('.qvm'):
        return igiqvm.decompile(open(path, 'rb').read())[1]
    return igiqvm.parse_qsc(open(path, encoding='latin1').read())


def actors(st):
    """(id, name, skin, weapon, expression, [clips], parent chain names) of every EditBoneObj"""
    par = {}
    for t, d, p in tasks(st):
        for a_ in t.args:
            if isinstance(a_, igiqvm.Call) and a_.name == 'Task_New':
                par[id(a_)] = t
    out = []
    for t, d, p in tasks(st):
        if str(lit(t.args[1])) != 'EditBoneObj':
            continue
        a = [lit(x) for x in t.args if not isinstance(x, igiqvm.Call)]
        chain, q = [], par.get(id(t))
        while q is not None and len(chain) < 6:
            chain.append('%s %s' % (lit(q.args[0]), lit(q.args[2])))
            q = par.get(id(q))
        out.append((a[0], str(a[2]), str(a[11]), str(a[13]), str(a[14]), [c.strip().lower() for c in str(a[15]).split(',') if c.strip()], chain))
    return out


def check(st):
    CL = clips()
    hits = []
    for aid, name, skin, gun, expr, cl, chain in actors(st):
        armed = gun not in ('', 'none') or bool(expr)
        for k, c in enumerate(cl):
            if c not in CL:
                hits.append(('UNKNOWN', aid, name, skin, gun, c, None, k, chain))
                continue
            sec, bone = CL[c]
            if armed and bone is None:
                hits.append(('GUNLESS', aid, name, skin, gun, c, sec, k, chain))
            elif not armed and bone == 24 and c not in ORIG_UNARMED:
                hits.append(('AIR', aid, name, skin, gun or "''", c, sec, k, chain))
    return hits


def main(argv):
    path = argv[1]
    st = load(path)
    hits = check(st)
    n_act = len(actors(st))
    if '--quiet' not in argv:
        for kind, aid, name, skin, gun, c, sec, k, chain in hits:
            print('%-7s %5s %-34s skin %-9s gun %-9s clip %d %-28s %s s   in %s' % (kind, aid, name[:34], skin, gun, k, c, '%.2f' % sec if sec else '?', ' < '.join(chain[:3])))
    kinds = {}
    for h in hits:
        kinds[h[0]] = kinds.get(h[0], 0) + 1
    print('guncheck %s: %d actors, %d hits %s -> %s' % (path, n_act, len(hits), kinds or '', 'FAIL' if hits else 'PASS'))
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
