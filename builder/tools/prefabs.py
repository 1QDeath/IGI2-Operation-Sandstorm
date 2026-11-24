"""prefabs - place buildings/props taken from OTHER levels into a mission (wrapper around tools/prefab.py).

    X = Transplant(kit)
    hq = X.place('location1/level3', 4086, pos=(x, y, z), yaw=1.57, parent=K.static_root())   # + its doors and props
    X.finish(out_dir)     # merged <base>.mtp + models/textures/lightmaps .res -> <out_dir>/overlay ; returns model names

A placed Building keeps its children (props, LightmapInfo) and gets copies of the Door tasks that sit on its shell in
the source level, all moved rigidly: p_new = Rz(yaw_new - yaw_src) (p_src - P_src) + P_new, gamma += yaw_new - yaw_src.
Lightmaps of the source instance (and of its doors/props) are renamed to the new task ids (prefab.merge does it only when
the mission uses the exact source mesh copies). Research + verification: work/research/prefabs/prefabs.md.
"""
import copy, math, os, shutil
import numpy as np
import igiqvm
from igiqvm import Call, Str
from mission_lib import T, v, GAME
from qast import load, tasks, lit
import prefab
import mef as meflib
import navgen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POS3 = {'Building': (3, 6), 'EditRigidObj': (3, 6), 'ExplodeObject': (3, 6), 'Door': (3, 9), 'Ladder': (3, 6),
        'GenericTBA': (3, 6), 'Switch': (3, 6), 'GenericPickup': (3, 6), 'LightmapInfo': None}


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


class Transplant:
    def __init__(self, kit):
        self.kit, self.m = kit, kit.m
        self.base = prefab.Level(kit.m.src)
        self.jobs = {}                                   # source dir -> [Level, set(models), {src task: new task}]
        self.src = {}
        self.placed = []

    def _source(self, rel):
        if rel not in self.src:
            d = os.path.join(GAME, 'MISSIONS', *rel.split('/'))
            dec = os.path.join(ROOT, 'work', 'decomp', '%s_objects.qsc' % rel.replace('/', '_'))
            if os.path.exists(dec):
                st = load(dec)
            else:
                ver, st = igiqvm.decompile(open(os.path.join(d, 'objects.qvm'), 'rb').read())
            byid = {lit(t.args[0]): (t, p) for t, dd, p in tasks(st)}
            G_ = GAME.replace('\\', '/') + '/MISSIONS/'
            loc = rel.split('/')[0]
            lv = prefab.Level(d)
            lib = meflib.ModelLib([os.path.join(d, 'models', lv.name + '.res'),
                                   G_ + '%s/common/models/%s.res' % (loc, loc), GAME + '/COMMON/models/common.res'])
            self.src[rel] = dict(dir=d, st=st, byid=byid, level=lv, lib=lib)
            self.jobs.setdefault(rel, [lv, set(), {}])
        return self.src[rel]

    def _footprint(self, S, t):
        a = [lit(x) for x in t.args[3:] if not isinstance(x, Call)]
        pos, ang, mdl = np.array(a[0:3], float), a[3:6], a[6]
        vs = [vv for vv, f in S['lib'].collision_tree(mdl, 'union')]
        if not vs:
            return pos - 4096 * 3, pos + 4096 * 3
        w = np.concatenate(vs) @ navgen.rot(*ang).T + pos
        return w.min(axis=0), w.max(axis=0)

    def _copy(self, rel, t, P_src, yaw_src, P_new, yaw_new, lm):
        """deep copy of task t (+ its children) with new ids, moved rigidly"""
        S = self.src[rel]
        job = self.jobs[rel]
        t2 = copy.deepcopy(t)
        R = _rz(yaw_new - yaw_src)

        def fix(task):
            old = lit(task.args[0])
            new = self.kit.nid()
            task.args[0] = v(new)
            ty = lit(task.args[1])
            if ty in POS3 and POS3[ty]:
                pi, ri = POS3[ty]
                p = np.array([float(lit(task.args[pi + k])) for k in range(3)])
                q = R @ (p - P_src) + P_new
                for k in range(3):
                    task.args[pi + k] = v(float(q[k]))
                task.args[ri + 2] = v(float(lit(task.args[ri + 2])) + (yaw_new - yaw_src))
            for a in task.args:
                if isinstance(a, Str) and len(a) >= 8 and a.count('_') == 2 and a.replace('_', '').isalnum() and a[0].isdigit():
                    job[1].add(str(a))                   # every model id the copy names
            if prefab.instance_lightmaps(job[0], old):
                lm.setdefault(old, []).append(new)     # (a source placed several times: every copy gets its lightmaps)
            for c in task.args:
                if isinstance(c, Call) and c.name == 'Task_New':
                    fix(c)
            return new
        new_id = fix(t2)
        return t2, new_id

    def place_group(self, rel, src_task, pos, yaw, parent, pivot=None, name=None, on_ground=True, strip_rules=True):
        """(10-31 additive, igi2ed HOWTO) copy a subtree of level rel rigidly - a Container 'Gates' with its Door
        leaves + padlock, a Building with everything under it. Only POS3 types move (Building, EditRigidObj,
        ExplodeObject, Door, Ladder, GenericTBA, Switch, GenericPickup); others are WARNED about, soldiers/AI refused. pivot = source point (world
        units) that lands on pos (default: the first task in the subtree with a position); yaw = turn ADDED to the
        source orientation (radians). on_ground: pos z = the new ground, the pivot keeps its height over the source
        ground. strip_rules: blank the Door script expressions (args 18-20) like place() does. Returns (new id, ids)."""
        S = self._source(rel)
        t, p = S['byid'][src_task]
        if pivot is None:
            for c, cd, cp in tasks([t]):
                ty = lit(c.args[1])
                if ty in POS3 and POS3[ty]:
                    pivot = [float(lit(c.args[POS3[ty][0] + k])) for k in range(3)]
                    break
        assert pivot is not None, ('no positioned task under', rel, src_task)
        P_src = np.array(pivot, float)
        P_new = np.array(pos, float)
        if on_ground:
            import terrain as terrain_mod
            if 'terrain' not in S:
                S['terrain'] = terrain_mod.Terrain(S['dir'], S['st'])
            g = float(S['terrain'].height(P_src[0], P_src[1]))
            if not np.isnan(g):
                P_new[2] += P_src[2] - g
        lm = self.jobs[rel][2]
        t2, new_id = self._copy(rel, t, P_src, 0.0, P_new, float(yaw), lm)
        if name:
            t2.args[2] = v(name)
        bad = sorted({lit(c.args[1]) for c, cd, cp in tasks([t]) if lit(c.args[1]) in ('HumanSoldier', 'HumanAI', 'AISquad', 'HumanPlayer')})
        assert not bad, 'place_group: %s %s holds %s (AI/players need their ai files + graphs: place them with Kit)' % (rel, src_task, bad)
        stay = sorted({lit(c.args[1]) for c, cd, cp in tasks([t]) if lit(c.args[1]) not in POS3 and len(c.args) > 5
                       and all(isinstance(lit(x), float) and abs(lit(x)) > 4096 for x in c.args[3:5])})
        if stay:                                         # positioned types _copy does not move (AmbientArea, AreaActivate, ...)
            print('   place_group WARNING %s %d: these types keep their SOURCE coordinates: %s' % (rel, src_task, ', '.join(stay)))
        ids = []
        for c2, cd2, cp2 in tasks([t2]):
            ids.append(lit(c2.args[0]))
            if strip_rules and lit(c2.args[1]) == 'Door':
                for k in (18, 19, 20):
                    c2.args[k] = v('')
        self.m.add_child(parent, t2)
        self.placed.append((rel, src_task, new_id, []))
        return new_id, ids

    def place(self, rel, src_task, pos, yaw, parent, name=None, doors=True, door_rules=None, on_ground=True):
        """copy instance src_task of level rel (e.g. 'location1/level3') to pos (world units, z = ground of the new
        site) and yaw (radians). Returns (new id, [new door ids])."""
        S = self._source(rel)
        t, p = S['byid'][src_task]
        ty = lit(t.args[1])
        assert ty in ('Building', 'EditRigidObj', 'ExplodeObject', 'GenericPickup'), (rel, src_task, ty)   # + objective items
        P_src = np.array([float(lit(t.args[3 + k])) for k in range(3)])
        yaw_src = float(lit(t.args[8]))
        P_new = np.array(pos, float)
        if on_ground:                                   # pos z = the new ground: keep the source's height above ITS ground
            import terrain as terrain_mod
            if 'terrain' not in S:
                S['terrain'] = terrain_mod.Terrain(S['dir'], S['st'])
            g = float(S['terrain'].height(P_src[0], P_src[1]))
            if not np.isnan(g):
                P_new[2] += P_src[2] - g
        lm = self.jobs[rel][2]
        t2, new_id = self._copy(rel, t, P_src, yaw_src, P_new, float(yaw), lm)
        if name:
            t2.args[2] = v(name)
        self.m.add_child(parent, t2)
        door_ids = []
        if doors:
            # doors that are CHILDREN of the building were already copied with it (reviewer 10-11: 21 doubled doors -
            # two leaves in one doorway); take those copies, and scan the footprint only for the source's loose doors
            own = {lit(c.args[0]) for c, cd, cp in tasks([t])}
            for c2, cd2, cp2 in tasks([t2]):
                if lit(c2.args[1]) == 'Door':
                    for k in (18, 19, 20):
                        c2.args[k] = v('')
                    if door_rules:
                        for k, val in door_rules.items():
                            c2.args[k] = v(val)
                    door_ids.append(lit(c2.args[0]))
            lo, hi = self._footprint(S, t)
            pad = 1.5 * 4096
            for i, (dt, dp) in S['byid'].items():
                if lit(dt.args[1]) != 'Door' or i in own:
                    continue
                q = np.array([float(lit(dt.args[3 + k])) for k in range(3)])
                if np.all(q >= lo - pad) and np.all(q <= hi + pad):
                    d2, did = self._copy(rel, dt, P_src, yaw_src, P_new, float(yaw), lm)
                    for k in (18, 19, 20):                   # the source level's rules mean nothing here
                        d2.args[k] = v('')
                    if door_rules:
                        for k, val in door_rules.items():
                            d2.args[k] = v(val)
                    self.m.add_child(parent, d2)
                    door_ids.append(did)
        self.m.reindex()
        self.placed.append((rel, src_task, new_id, door_ids))
        print('prefab %-18s %s task %d -> %d at (%.0f, %.0f, %.1f) m, %d doors' % (
            lit(t.args[9]), rel, src_task, new_id, P_new[0] / 4096, P_new[1] / 4096, P_new[2] / 4096, len(door_ids)))
        return new_id, door_ids

    def models(self, rel, names):
        """merge these models of level rel too (cutscene props placed later by tools/cine.py: the C-130, chutes,
        the friendly helicopter) - call before finish()"""
        self._source(rel)
        self.jobs[rel][1].update(names)

    def finish(self, out_dir):
        """merge every source into the base level's manifest + banks -> <out_dir>/overlay; returns the model names
        (for Mission.models / validate) and the merged models .res path (for navgen)"""
        stage = os.path.join(out_dir, 'prefab_stage')
        if os.path.isdir(stage):
            shutil.rmtree(stage)
        rep = prefab.merge(self.base, stage, [(lv, sorted(ids), lm) for lv, ids, lm in self.jobs.values()])
        probs = prefab.verify(stage, self.base)
        assert not probs, probs
        ov = os.path.join(out_dir, 'overlay')
        for root, dirs, files in os.walk(stage):
            rel = os.path.relpath(root, stage)
            os.makedirs(os.path.join(ov, rel), exist_ok=True)
            for f in files:
                shutil.copy2(os.path.join(root, f), os.path.join(ov, rel, f))
        provided = prefab.provided_models(stage, self.base.name)
        self.m.models |= provided
        print('prefabs: +%d models, +%d meshes, +%d textures, %d lightmaps, %d warnings' % (
            len(rep['added_vnams']), len(rep['added_meshes']), len(rep['added_textures']), len(rep['lightmaps']), len(rep['warnings'])))
        open(os.path.join(out_dir, 'prefab_warnings.txt'), 'w').write(chr(10).join(rep['warnings']))
        for w in rep['warnings'][:8]:
            print('   prefab warning:', w)
        return provided, os.path.join(stage, 'models', self.base.name + '.res')
