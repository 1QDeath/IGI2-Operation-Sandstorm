"""lodfix - far objects that do not pop out (owner 10-11: 'in the cutscenes buildings, the street and the trees are not
shown far away, you need to get close').

IGI 2 has no global view distance: every model is drawn while  distance * min(tan(fov/2), 1) < cutoff  where cutoff =
ModelLODSettings 'Distance to cutoff' (m). The global lod.qvm is applied first, then the LEVEL's own lod.qvm, which
wins. install.py copies the multiplayer base folder, so our missions inherited the MP maps' performance values
(Timberland: sheds 300 m instead of 1400, cabin 500 instead of 1500, trucks 250 ...). Doors on those buildings had
100-150 m (holes in far buildings); models without any entry get 10 x their radius. Forest tasks have their own far
plane (arg 20 'View cutoff (m)'): ours were 100-250 m, the original levels use 400-1200.

    import lodfix
    lodfix.apply(m, overlay_dir, base_dir)     # writes overlay_dir/lod.qvm + raises every Forest's view cutoff
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import igiqvm
from igiqvm import Call, Int, Flt, Str
from qast import lit, tasks

GAME = r'C:\Users\1qdeath\Games\IGI2\app'
MODEL_RE = re.compile(r'^\d{3}_\d{2}_\d$')
BUILDING_CUT = 1500.0         # m: a building / prop / vehicle we place
DOOR_CUT = 1500.0             # doors / gates sit in buildings: never vanish before them
FENCE_CUT = 700.0
FOREST_CUT = {'default': 900.0, 'small': 400.0}


def read(path):
    ver, st = igiqvm.decompile(open(path, 'rb').read())
    ent = {}
    for c in st:
        if isinstance(c, Call) and c.name == 'Task_New' and str(c.args[1]) == 'ModelLODSettings':
            mdl = str(c.args[3]).lower()
            if mdl not in ent:                                  # (the first entry for a model wins)
                ent[mdl] = [float(lit(a)) for a in c.args[4:9]]
    return ver, st, ent


def mission_models(m):
    """every model name referenced by the mission's tasks -> (all, door models)"""
    allm, doors = set(), set()
    for t, d, p in tasks(m.stmts):
        ty = lit(t.args[1])
        for a in t.args[3:]:
            if isinstance(a, Call):
                continue
            s = lit(a)
            if isinstance(s, str) and MODEL_RE.match(s.lower()):
                allm.add(s.lower())
                if ty in ('Door', 'Lift'):
                    doors.add(s.lower())
    return allm, doors


def build(m, base_dir, extra=None):
    """-> (lod.qvm bytes, report lines).  extra = {model: [5 floats] or 'copy:<model>'} for models whose names the
    regex cannot see (new skins, bi_* / fb_* prefabs): a VNAM without any line gets 10 x its radius as cut-off, so a
    new soldier skin vanished beyond ~10 m (owner 10-14: 'characters disappear')."""
    gver, gst, G = read(os.path.join(GAME, 'lod.qvm'))
    lp = os.path.join(base_dir, 'lod.qvm')
    ver, st, L = read(lp) if os.path.exists(lp) else (gver, gst, {})
    allm, doors = mission_models(m)
    out, notes = {}, []
    for mdl, v in L.items():
        if v[4] >= 10000:                                        # forests (the Forest task's far plane decides)
            out[mdl] = v
        elif mdl in G and G[mdl][4] >= v[4]:
            out[mdl] = list(G[mdl]); out[mdl][4] = max(G[mdl][4], 1000.0)
            notes.append('%s: base map %g m -> %g m' % (mdl, v[4], out[mdl][4]))
        else:
            out[mdl] = list(v); out[mdl][4] = max(v[4], 1000.0)
    for mdl in sorted(allm):
        if mdl.startswith('940_') or mdl.startswith('900_'):
            continue
        big = mdl[0] in '4567' or mdl[:2] in ('30', '31', '33', '34', '36') or mdl in doors
        # (big = buildings 4xx, doors 5xx, vehicles 6xx, aircraft 7xx, walls/fences/containers/poles; small props
        #  1xx/2xx keep the originals' short cut-offs - nobody sees a keyboard 1 km away, and they cost frames)
        cut = DOOR_CUT if mdl in doors else FENCE_CUT if mdl[:3] in ('303', '336', '340') else BUILDING_CUT if big else 150.0
        cur = out.get(mdl) or G.get(mdl)
        if cur is None:
            out[mdl] = [60.0, 120.0, 240.0, 480.0, cut]
            notes.append('%s: no entry (10 x radius) -> %g m' % (mdl, cut))
        elif not big and cur[4] >= 60.0:
            continue
        elif cur[4] < cut:
            out[mdl] = list(cur); out[mdl][4] = cut
            notes.append('%s: %g m -> %g m' % (mdl, cur[4], cut))
    for mdl, v in (extra or {}).items():
        if isinstance(v, str) and v.startswith('copy:'):
            src = v[5:].lower()
            v = out.get(src) or G.get(src)
            assert v is not None, ('lodfix extra: no LOD line to copy for', mdl, src)
        out[mdl.lower()] = [float(x) for x in v]
        notes.append('%s: added %s' % (mdl, out[mdl.lower()]))
    decl = [c for c in (st if L else gst) if isinstance(c, Call) and c.name == 'Task_DeclareParameters']
    rows = [Call('Task_New', [Int(-1), Str('ModelLODSettings'), Str(mdl), Str(mdl)] + [Flt(x) for x in v])
            for mdl, v in sorted(out.items())]
    data = igiqvm.compile_stmts(decl + rows, ver)
    v2, st2 = igiqvm.decompile(data)                              # round trip
    assert len([c for c in st2 if isinstance(c, Call) and c.name == 'Task_New']) == len(rows)
    return data, notes


def raise_forests(m, far=None):
    """every Forest task's 'View cutoff (m)' (arg 20) -> at least 900 m (low bushes 400 m)"""
    n = 0
    for t, d, p in tasks(m.stmts):
        if lit(t.args[1]) != 'Forest':
            continue
        cur = float(lit(t.args[20]))
        small = str(lit(t.args[6])).lower() == '940_22_1' or 'bush' in str(lit(t.args[2])).lower()
        want = far or FOREST_CUT['small' if small else 'default']
        if cur < want:
            t.args[20] = Flt(want); n += 1
    return n


def apply(m, overlay_dir, base_dir, forest_far=None, extra=None):
    data, notes = build(m, base_dir, extra)
    os.makedirs(overlay_dir, exist_ok=True)
    open(os.path.join(overlay_dir, 'lod.qvm'), 'wb').write(data)
    nf = raise_forests(m, forest_far)
    print('lodfix: %d model cut-offs raised / added, %d forests drawn farther' % (len(notes), nf))
    return notes
