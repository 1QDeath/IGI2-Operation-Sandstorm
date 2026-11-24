"""lipsync - talking mouths in cutscenes, the originals' way (shared, additive; first user: Joyride 10-31).

How the original game does it (read from the decompiled levels): a voiced StatusMessage has a last parameter "Morph QTask IDs"
= a comma list of the EditBoneObj actor ids that SPEAK this line; while the sound plays the engine morphs their faces.
  L11 2994 CV10_CAMP_02_GUARD -> '3074' (the left guard, clip left_guard_talking)
  L11 2992 CV11_INTRO_01_WHITE -> '3111, 3125' (White, both shot copies)
  L21 3319 CV20_CAMP_01_LENEH -> '3459' (the Senator at his desk); L36 3572 cv30_outro_01_jones -> '3912'
Our cutscene.caption() / atmos.add_shot_chain wrote '' there, so nobody's mouth moved (owner 10-31).

    import lipsync
    lipsync.link(m, msg_id, [actor_id, ...])                  # one line
    lipsync.auto(m, top_container_id, {'JONES': ('jones',), 'ANYA': ('anya',)})
        # every voiced caption under the cutscene chain `top` whose text starts with 'JONES:' gets the ids of every EditBoneObj whose
        # model starts with 'jones' that exists in the SAME shot box (the ConditionalContainer holding its CutScene) - or anywhere in
        # the chain when the caption is not tied to a shot. Returns [(msg id, key, [actor ids])].
A line spoken off screen (radio) simply finds no actor and is left alone.
"""
import re
from qast import lit, tasks
from mission_lib import v

_CS = re.compile(r'CutScene_(\d+)\.nTick')


def link(m, msg_id, actor_ids):
    t = m.byid[msg_id]
    assert str(lit(t.args[1])) == 'StatusMessage', msg_id
    t.args[-1] = v(', '.join(str(int(a)) for a in actor_ids))
    return t


def _kids(t):
    return [a for a in t.args if hasattr(a, 'name') and a.name == 'Task_New']


def auto(m, top, speakers, texts=None):
    texts = texts if texts is not None else (getattr(m, 'text', {}) or {}).get('messages', {})
    root = m.byid[top]
    # shot boxes: CutScene id -> the actors (id, model) under the same ConditionalContainer
    box_of, actors_all, shared = {}, [], []          # shared = (condition, actors) of CutScene-less boxes (an actor held over shots)
    for box in _kids(root):
        if str(lit(box.args[1])) != 'ConditionalContainer':
            continue
        cs_ids, acts = [], []
        for t, d, p in tasks([box]):
            ty = str(lit(t.args[1]))
            if ty == 'CutScene':
                cs_ids.append(int(lit(t.args[0])))
            elif ty == 'EditBoneObj':
                acts.append((int(lit(t.args[0])), str(lit(t.args[11])).lower()))
        for c in cs_ids:
            box_of[c] = acts
        if not cs_ids and acts:
            shared.append((str(lit(box.args[3])), acts))
        actors_all += acts
    for t, d, p in tasks([root]):                       # (actors placed straight under the chain top count for every shot)
        if str(lit(t.args[1])) == 'EditBoneObj' and (int(lit(t.args[0])), str(lit(t.args[11])).lower()) not in actors_all:
            actors_all.append((int(lit(t.args[0])), str(lit(t.args[11])).lower()))
    out = []
    for t, d, p in tasks([root]):
        if str(lit(t.args[1])) != 'StatusMessage' or not str(lit(t.args[12])).strip():
            continue
        key = str(lit(t.args[10]))
        txt = str(texts.get(key, ''))
        who = next((s for s in speakers if txt.upper().startswith(s.upper() + ':')), None)
        if who is None:
            continue
        mm = _CS.search(str(lit(t.args[9])))
        if mm:
            c_ = int(mm.group(1))
            pool = list(box_of.get(c_, []))
            # a shared box is on screen during this CutScene when its condition names it (or names its neighbours' chain:
            # 'CutScene_<before>.isFinished && !CutScene_<after>.isFinished' - the ids bracket c_)
            for cond, acts in shared:
                ids_ = [int(x) for x in re.findall(r'CutScene_(\d+)\.isFinished', cond)]
                if 'CutScene_%d.' % c_ in cond or (len(ids_) >= 2 and min(ids_) < c_ <= max(ids_)):
                    pool += acts
        else:
            pool = actors_all
        ids = [i for i, mdl in pool if any(mdl.startswith(pre) for pre in speakers[who])]
        if ids:
            link(m, int(lit(t.args[0])), ids)
            out.append((int(lit(t.args[0])), key, ids))
    return out
