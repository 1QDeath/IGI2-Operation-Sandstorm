"""Transplant models (buildings, props, vehicles...) from one IGI 2 level into another mission's resources.

How the engine finds a model (igi2.exe, addresses and evidence in prefabs.md):
  * per mission it loads four manifests, in this order (Level() models all but new.mtp, which holds only animations):
        COMMON/common.mtp, COMMON/new.mtp, <common path>/<location>.mtp, <level path>/<level name>.mtp
    and with each one '<dir>/textures/<name>.res' + '<dir>/models/<name>.res'. A missing manifest/.res is FATAL.
  * a task names a 'virtual model' (VNAM, e.g. '400_10_1'). The engine resolves LOD 1..5 by bumping the last
    character ('400_10_1', '400_10_2', ...) and stops at the first name no manifest has. First manifest wins,
    names compare case-sensitively.
  * VNAM -> INST -> one mesh in MODS ('LOCAL:models/<mef>.mef') + one texture per slot through GTT -> TEXF
    ('LOCAL:textures/<tex>.tex'). Resource names are global and the FIRST registration of a name wins.
  * a mesh's ATTA attachments are resolved the same way (VNAM + LODs), or as SVOL shadow volumes.
  * per-instance lightmaps: '<task id %04d>_<attachment node %04d>_<lod>.olm' in <mission>/lightmaps/lightmaps.res
    (node = depth-first index in the attachment tree, 0 = the model itself).
  * models/textures/lightmaps .res files have NO PATH chunk (unlike sounds.res) - never add one.

Command line:
  python prefab.py show  <source level dir> <model id> [...]
  python prefab.py merge <source level dir> <target level dir> <out dir> <model id>[,<id>...] [--lightmap SRC=NEW ...]
  python prefab.py selftest

Python:
  src = Level(r'...\\MISSIONS\\location1\\level1'); dst = Level(r'...\\MISSIONS\\multiplayer\\sandstorm')
  rep = merge(dst, out_dir, [(src, ['400_10_1'], {4010: 1700})])      # lightmaps of task 4010 -> new task 1700
  rep['files'] -> the rewritten <level>.mtp, models/<level>.res, textures/<level>.res, lightmaps/lightmaps.res
  Level(dst.dir, files_dir=out_dir) reads the merged files back (chain further merges, closure(), verify()).
"""
import copy, os, re, struct, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = HERE                                     # lives in tools/ (copied from work/research/prefabs 10-10)
sys.path.insert(0, HERE); sys.path.insert(0, TOOLS)
import numpy as np
import ilff, igiqvm, mtp
import mef as meflib

GAME = r'C:\Users\1qdeath\Games\IGI2\app'
MAX_LOD = 5
LM_RE = re.compile(r'^LOCAL:(?:missions/location\d+/level\d+/)?lightmaps/(\d{4,})([a-z]?)_(\d{4})_(\d)\.olm$', re.I)


# ----------------------------------------------------------------------------- resource files
class Res:
    """an ILFF 'IRES' archive kept as an ordered chunk list (byte-exact rewrite with ilff.write)"""
    def __init__(self, path, must_exist=True):
        self.path = path
        if path and os.path.exists(path):
            self.raw = open(path, 'rb').read()
            self.form, self.chunks, self.hdr = ilff.read(self.raw)
        elif must_exist:
            raise FileNotFoundError(path)
        else:
            self.raw, self.form, self.chunks, self.hdr = None, b'IRES', [], (0, 4, 0)
        self.index = {}
        for i, (t, b, a) in enumerate(self.chunks):
            if t == b'NAME' and i + 1 < len(self.chunks):
                self.index.setdefault(b.rstrip(b'\0').decode('latin1'), i + 1)
        self.added = []
        assert not any(t == b'PATH' for t, b, a in self.chunks), '%s has a PATH chunk (not a model/texture/lightmap bank?)' % path

    def names(self):
        return list(self.index)

    def get(self, name):
        i = self.index.get(name)
        return self.chunks[i][1] if i is not None else None

    def has(self, name):
        return name in self.index

    def add(self, name, body):
        assert name not in self.index, name
        self.chunks.append((b'NAME', name.encode('latin1') + b'\0', 4))
        self.chunks.append((b'BODY', bytes(body), 4))
        self.index[name] = len(self.chunks) - 1
        self.added.append(name)

    def data(self):
        return ilff.write(self.form, self.chunks, self.hdr[1] or 4)

    def clone(self):
        c = Res.__new__(Res)
        c.path, c.raw, c.form, c.hdr = self.path, self.raw, self.form, self.hdr
        c.chunks, c.index, c.added = list(self.chunks), dict(self.index), []
        return c


# ----------------------------------------------------------------------------- one level and its manifest chain
def _define_mission(level_dir):
    """DefineMission args of <level_dir>/mission.qvm as Python values, or None"""
    p = os.path.join(level_dir, 'mission.qvm')
    if not os.path.exists(p):
        return None
    from qast import lit
    for c in igiqvm.decompile(open(p, 'rb').read())[1]:
        if isinstance(c, igiqvm.Call) and c.name == 'DefineMission':
            return [lit(x) for x in c.args]
    return None


class Layer:
    def __init__(self, kind, mtp_path, models_path, textures_path, must_exist=True):
        self.kind, self.mtp_path = kind, mtp_path
        self.m = mtp.read(mtp_path)
        self.models = Res(models_path, must_exist)
        self.textures_path = textures_path
        self._textures = None
        self.vnam = {n: i for i, n in reversed(list(enumerate(self.m['VNAM'])))}     # first occurrence wins
        self.svol = {n.lower(): n for n in reversed(self.m['SVOL'])}

    @property
    def textures(self):
        if self._textures is None:
            self._textures = Res(self.textures_path, False)
        return self._textures

    def entry(self, vn):
        """VNAM -> (mef name, [texture names])"""
        mi, g = self.m['INST'][self.vnam[vn]]
        mef = self.m['MODS'][mi] if mi < mtp.COMMON_BIT else None
        texs = []
        for gi in g:
            t, pl = self.m['GTT'][gi] if gi < mtp.COMMON_BIT else (None, None)
            texs.append(self.m['TEXF'][t] if t is not None and t < mtp.COMMON_BIT else None)
        if mef is None or None in texs:
            raise NotImplementedError('%s uses 0x2000 (common.mtp) references - none of the shipped manifests do' % vn)
        return mef, texs


class Level:
    """a level / mission folder: <dir>/<name>.mtp + models/ + textures/ + lightmaps/, plus its location + COMMON layers"""
    def __init__(self, level_dir, level_name=None, common_dir=None, location=None, files_dir=None):
        """level_dir: an installed level / mission folder (its mission.qvm gives location, common path, level name).
        files_dir: read the level's own manifest + .res files from here instead (e.g. a previous merge output)."""
        self.dir = level_dir
        a = _define_mission(level_dir)
        self.mission_id = None
        if a:
            self.mission_id = a[0]
            location = location or a[11]
            level_name = level_name or a[12]
            common_dir = common_dir or os.path.join(GAME, *str(a[9]).replace('\\', '/').split('/'))
        if level_name is None:
            mt = [f for f in os.listdir(level_dir) if f.lower().endswith('.mtp')]
            assert len(mt) == 1, 'cannot guess the level name in %s: %s' % (level_dir, mt)
            level_name = mt[0][:-4]
        self.name, self.location, self.common_dir = level_name, location, common_dir

        def ci(d, f):                     # case-insensitive child (LEVEL5 vs level5 folders)
            if os.path.isdir(d):
                for x in os.listdir(d):
                    if x.lower() == f.lower():
                        return os.path.join(d, x)
            return os.path.join(d, f)

        def layout(root):
            return dict(mtp=ci(root, level_name + '.mtp'), models=os.path.join(ci(root, 'models'), level_name + '.res'),
                        textures=os.path.join(ci(root, 'textures'), level_name + '.res'),
                        lightmaps=os.path.join(ci(root, 'lightmaps'), 'lightmaps.res'))
        self.paths = layout(level_dir)
        if files_dir:                     # files a merge did not rewrite still come from the level folder
            alt = layout(files_dir)
            self.paths = {k: (alt[k] if os.path.exists(alt[k]) else p) for k, p in self.paths.items()}
        self.layers = [Layer('global', os.path.join(GAME, 'COMMON', 'common.mtp'), os.path.join(GAME, 'COMMON', 'models', 'common.res'),
                             os.path.join(GAME, 'COMMON', 'textures', 'common.res'))]
        if common_dir and location:                       # the engine aborts when any of these three files is missing
            for f in (location + '.mtp', os.path.join('models', location + '.res'), os.path.join('textures', location + '.res')):
                if not os.path.exists(os.path.join(common_dir, f)):
                    raise FileNotFoundError('location file missing (fatal in the game too): %s' % os.path.join(common_dir, f))
            self.layers.append(Layer('location', os.path.join(common_dir, location + '.mtp'), os.path.join(common_dir, 'models', location + '.res'),
                                     os.path.join(common_dir, 'textures', location + '.res')))
        self.layers.append(Layer('level', self.paths['mtp'], self.paths['models'], self.paths['textures']))
        self.level = self.layers[-1]
        self._lightmaps = None

    @property
    def lightmaps(self):
        if self._lightmaps is None:
            self._lightmaps = Res(self.paths['lightmaps'], False)
        return self._lightmaps

    # --- engine-order lookups
    def find_vnam(self, vn):
        for L in self.layers:                    # load order: COMMON, location, level ; exact (case-sensitive) compare
            if vn in L.vnam:
                return L
        return None

    def find_svol(self, name):
        for L in self.layers:                    # _stricmp
            if name.lower() in L.svol:
                return L, L.svol[name.lower()]
        return None, None

    def find_resource(self, name, kind):
        for L in self.layers:
            r = L.models if kind == 'models' else L.textures
            if r.has(name):
                return L, r.get(name)
        return None, None

    def lods(self, model_id):
        """the engine's LOD expansion (0x5039a0): bump the last character until a name is missing (max 5)"""
        out, n = [], model_id
        for _ in range(MAX_LOD):
            if self.find_vnam(n) is None:
                break
            out.append(n)
            n = n[:-1] + chr(ord(n[-1]) + 1)
        return out


# ----------------------------------------------------------------------------- dependency closure
def closure(src, model_ids):
    """every VNAM / mesh / texture / shadow volume the given model ids need in `src` (attachments recursively).
    -> dict(vnams={vn: dict(layer, mef, textures)}, svols={name: layer}, unresolved=[(parent, name)], order=[vn...])"""
    vnams, svols, unresolved, order, seen = {}, {}, [], [], set()
    todo = list(model_ids)
    while todo:
        mid = todo.pop(0)
        if mid in seen:
            continue
        seen.add(mid)
        lods = src.lods(mid)
        if not lods:
            unresolved.append((None, mid)); continue
        for vn in lods:
            if vn in vnams:
                continue
            L = src.find_vnam(vn)
            mefn, texs = L.entry(vn)
            vnams[vn] = dict(layer=L, mef=mefn, textures=texs); order.append(vn)
            body = src.find_resource('LOCAL:models/%s.mef' % mefn, 'models')[1]
            if body is None:
                raise RuntimeError('%s: mesh %s missing from every models .res' % (vn, mefn))
            for a, pos, m in meflib.attachments(body):
                if src.find_vnam(a):
                    todo.append(a)
                else:
                    SL, real = src.find_svol(a)
                    if SL:
                        svols[real] = SL
                    else:
                        unresolved.append((vn, a))    # bone / attach point names ('bombbackpack') or absent models
    return dict(vnams=vnams, svols=svols, unresolved=unresolved, order=order)


def task_model(src, task_id):
    """the model id a task of src's objects.qvm names (first string argument that resolves as a VNAM)"""
    if not hasattr(src, '_tasks'):
        from qast import tasks, lit
        st = igiqvm.decompile(open(os.path.join(src.dir, 'objects.qvm'), 'rb').read())[1]
        src._tasks = {}
        for t, d, p in tasks(st):
            i = lit(t.args[0])
            if isinstance(i, int):
                src._tasks[i] = [str(lit(a)) for a in t.args[3:] if isinstance(a, igiqvm.Str)]
    for a in src._tasks.get(int(task_id), []):
        if src.find_vnam(a):
            return a
    return None


def lightmap_nodes(src, model_id):
    """depth-first attachment tree (LOD-1 names). This matches the '<task>_<node>_<lod>.olm' node numbering for 537 of
    618 shipped multi-node instances only (lm_order_test.py) - informative, merge() does not rely on it."""
    out = []

    def walk(vn, depth):
        out.append(vn)
        if depth > 6:
            return
        L = src.find_vnam(vn)
        body = src.find_resource('LOCAL:models/%s.mef' % L.entry(vn)[0], 'models')[1]
        for a, pos, m in meflib.attachments(body):
            if src.find_vnam(a):
                walk(a, depth + 1)
    if src.find_vnam(model_id):
        walk(model_id, 0)
    return out


def lod_name(vn1, lod):
    return vn1[:-1] + chr(ord(vn1[-1]) + lod - 1)


def instance_lightmaps(src, task_id):
    """the .olm entries a placed instance (task id) owns in src's lightmaps.res -> [(name, node, lod)]"""
    out = []
    for name in src.lightmaps.names():
        mm = LM_RE.match(name)
        if mm and int(mm.group(1)) == int(task_id):
            out.append((name, int(mm.group(3)), int(mm.group(4))))
    return out


# ----------------------------------------------------------------------------- lightmap donors (10-11)
_DONORS = {}
DONOR_LEVELS = ['multiplayer/sandstorm', 'multiplayer/redstone', 'multiplayer/timberland', 'multiplayer/jungle',
                'multiplayer/chinesetemple', 'multiplayer/forestraid']


def _donor_level(rel):
    if rel not in _DONORS:
        try:
            _DONORS[rel] = Level(os.path.join(GAME, 'MISSIONS', *rel.split('/')))
        except Exception:
            _DONORS[rel] = None
    return _DONORS[rel]


def _mesh_of(lv, vn):
    L = lv.find_vnam(vn)
    return lv.find_resource('LOCAL:models/%s.mef' % L.entry(vn)[0], 'models')[1] if L else None


def lightmap_donor(root, target, used_mesh):
    """owner 10-11 ('the towers are super bright'): an instance whose source lightmaps cannot be used (the mission uses
    another copy of one of its meshes -> the engine gives it a blank, full-bright lightmap) borrows the lightmaps of an
    instance of the SAME model in another level that ships exactly the meshes the mission uses (same mesh bytes = same
    tree, node numbering and face counts; only the bake's sun differs). -> (Level, task id) or None"""
    import json
    cands = []
    cat = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'research', 'prefabs', 'catalog.json')
    if os.path.exists(cat):
        if not hasattr(lightmap_donor, 'cat'):
            lightmap_donor.cat = {e['id']: e for e in json.load(open(cat))}
        e = lightmap_donor.cat.get(root)
        cands += [(rel, int(t)) for rel, t in (e or {}).get('instances_with_lightmaps', [])]
    for rel in DONOR_LEVELS:
        lv = _donor_level(rel)
        if lv is None:
            continue
        ids = sorted({int(LM_RE.match(n).group(1)) for n in lv.lightmaps.names() if LM_RE.match(n)})
        cands += [(rel, t) for t in ids if task_model(lv, t) == root]
    want = {}
    for rel, t in cands:
        lv = _donor_level(rel)
        if lv is None or not instance_lightmaps(lv, t) or task_model(lv, t) != root:
            continue
        ok = True
        for vn in closure(lv, [root])['order']:
            if vn not in want:
                tm = used_mesh.get(vn)
                want[vn] = tm if tm is not None else _mesh_of(target, vn)
            if want[vn] is None or _mesh_of(lv, vn) != want[vn]:
                ok = False
                break
        if ok:
            return lv, t
    return None


# ----------------------------------------------------------------------------- comparisons
def geometry_key(mef_bytes):
    """export-noise-free identity of a mesh: render xyz + faces + collision verts (ignores timestamps, lightmap UVs)"""
    _, ch, _ = ilff.read(mef_bytes)
    h = []
    d = {}
    for t, x, a in ch:
        d.setdefault(t, []).append(x)
    if b'D3DR' in d and b'XTRV' in d:
        r = d[b'D3DR'][0]; ints = struct.unpack('<%di' % (len(r) // 4), r)
        nv = {44: ints[4] if len(ints) > 4 else 0, 36: ints[3] if len(ints) > 3 else 0, 40: ints[5] if len(ints) > 5 else 0}.get(len(r), 0)
        if nv and len(d[b'XTRV'][0]) % nv == 0:
            st = len(d[b'XTRV'][0]) // nv
            xyz = np.frombuffer(d[b'XTRV'][0], 'u1').reshape(nv, st)[:, :12]
            h.append(zlib.crc32(np.round(np.frombuffer(xyz.tobytes(), '<f4'), 1).tobytes()))
        h.append(zlib.crc32(d.get(b'ECAF', [b''])[0]))
    for x in d.get(b'XTVC', []):
        h.append(zlib.crc32(x))
    return tuple(h)


# ----------------------------------------------------------------------------- merge
def merge(target, out_dir, jobs, write=True):
    """target: Level (the BASE level the mission folder is a copy of, or Level(base, files_dir=previous output)).
    jobs: [(src Level, [model ids], {src task id: new task id} for lightmaps)].
    Writes <out_dir>/<name>.mtp, models/<name>.res, textures/<name>.res (+ lightmaps/lightmaps.res when the target
    has one or lightmaps were copied). A no-op merge reproduces the inputs byte for byte. Returns a report dict."""
    if write:
        g, o = os.path.normcase(os.path.realpath(GAME)), os.path.normcase(os.path.realpath(out_dir))
        if o == g or o.startswith(g + os.sep):
            raise ValueError('refusing to write into the game folder: %s' % out_dir)
    T = target.level
    m = copy.deepcopy({k: v for k, v in T.m.items() if k != '_raw'})
    m['_raw'] = T.m['_raw']
    models, textures, lights = T.models.clone(), T.textures.clone(), target.lightmaps.clone()
    rep = dict(added_vnams=[], skipped_vnams=[], added_meshes=[], added_textures=[], reused_textures=[], added_svols=[],
               lightmaps=[], warnings=[], files={})
    mods_idx = {n: i for i, n in reversed(list(enumerate(m['MODS'])))}
    texf_idx = {n: i for i, n in reversed(list(enumerate(m['TEXF'])))}
    gtt_idx = {}
    for i, (t, pl) in enumerate(m['GTT']):
        gtt_idx.setdefault((t, pl), i)
    transplanted = set()
    used_mesh = {}                                # VNAM -> mesh bytes the merged mission will really use
    for src, ids, lm_map in jobs:
        cl = closure(src, ids)
        for p, a in cl['unresolved']:
            rep['warnings'].append('%s: attachment %r not found in %s (bone/attach point or absent model; skipped by the engine too)' % (p, a, src.dir) if p else
                                   'model %s not found in %s' % (a, src.dir))
        for vn in cl['order']:
            it = cl['vnams'][vn]
            if vn in transplanted:
                rep['skipped_vnams'].append((vn, 'this merge', 'added by an earlier job'))
                continue
            have = target.find_vnam(vn)
            src_body = src.find_resource('LOCAL:models/%s.mef' % it['mef'], 'models')[1]
            if have is not None:
                hm, ht = have.entry(vn)
                tb = target.find_resource('LOCAL:models/%s.mef' % hm, 'models')[1]
                same = tb is not None and geometry_key(tb) == geometry_key(src_body)
                used_mesh[vn] = tb
                rep['skipped_vnams'].append((vn, have.kind, 'same geometry' if same else 'DIFFERENT geometry'))
                if not same:
                    rep['warnings'].append('%s already exists in the target %s manifest with different geometry - the target copy wins' % (vn, have.kind))
                continue
            # mesh
            mname = 'LOCAL:models/%s.mef' % it['mef']
            L, existing = target.find_resource(mname, 'models')
            if existing is None and models.has(mname):
                L, existing = T, models.get(mname)
            if it['mef'] not in mods_idx:
                m['MODS'].append(it['mef']); mods_idx[it['mef']] = len(m['MODS']) - 1
            used_mesh[vn] = src_body if existing is None else existing
            # every MODS/TEXF entry of a manifest must be in ITS OWN bank (all 25 shipped manifests; the engine frees the
            # other layers' banks - 10-10 Frostbite: 'Failed to load resource LOCAL:textures/300_29_1.tex', MP common had it)
            if not models.has(mname):
                models.add(mname, src_body if existing is None else existing)
                if existing is None:
                    rep['added_meshes'].append(it['mef'])
            if existing is not None and geometry_key(existing) != geometry_key(src_body):
                rep['warnings'].append('mesh %s is already registered by the target %s layer with different geometry (first wins)' % (it['mef'], L.kind))
            # textures
            g = []
            for tex in it['textures']:
                tname = 'LOCAL:textures/%s.tex' % tex
                sbody = src.find_resource(tname, 'textures')[1]
                if sbody is None:
                    raise RuntimeError('%s: texture %s is in the manifest but in no textures .res of %s' % (vn, tex, src.dir))
                L, existing = target.find_resource(tname, 'textures')
                if existing is None and textures.has(tname):
                    L, existing = T, textures.get(tname)
                if tex not in texf_idx:
                    m['TEXF'].append(tex); texf_idx[tex] = len(m['TEXF']) - 1
                if not textures.has(tname):                      # own bank (see the MODS note above)
                    textures.add(tname, sbody if existing is None else existing)
                if existing is None:
                    rep['added_textures'].append(tex)
                elif tex not in rep['added_textures'] and tex not in {r[0] for r in rep['reused_textures']}:
                    rep['reused_textures'].append((tex, L.kind, 'same' if existing == sbody else 'DIFFERENT content'))
                    if existing != sbody:
                        rep['warnings'].append('texture %s already in the target %s layer with different bytes (usually another resolution '
                                               'of the same image) - first registration wins, the target version is used' % (tex, L.kind))
                key = (texf_idx[tex], -1)
                if key not in gtt_idx:
                    m['GTT'].append(list(key)); gtt_idx[key] = len(m['GTT']) - 1
                g.append(gtt_idx[key])
            m['INST'].append([mods_idx[it['mef']], g])
            m['VNAM'].append(vn)
            rep['added_vnams'].append(vn); transplanted.add(vn)
        for name, L in cl['svols'].items():
            TL, real = target.find_svol(name)
            if TL or name.lower() in {x.lower() for x in m['SVOL']}:
                continue
            body = src.find_resource('LOCAL:models/%s.mef' % name, 'models')[1]
            m['SVOL'].append(name)
            if not target.find_resource('LOCAL:models/%s.mef' % name, 'models')[1] and not models.has('LOCAL:models/%s.mef' % name):
                models.add('LOCAL:models/%s.mef' % name, body)
            rep['added_svols'].append(name)
        # per-instance lightmaps: an .olm is only accepted with the exact mesh copy it was baked for (0x54f0bb)
        taken = set()
        for name in lights.names():
            mm = LM_RE.match(name)
            if mm:
                taken.add((int(mm.group(1)), mm.group(2), int(mm.group(3)), int(mm.group(4))))
        for s_id, n_ids in (lm_map or {}).items():
          for n_id in (n_ids if isinstance(n_ids, (list, tuple)) else [n_ids]):
            s_id, n_id = int(s_id), int(n_id)
            got = instance_lightmaps(src, s_id)
            root = task_model(src, s_id)
            if not got or root is None:
                rep['warnings'].append('no lightmaps / no model for source task %s in %s' % (s_id, src.dir)); continue
            # all-or-nothing per instance: every mesh of the instance's tree must be the exact source copy, so the
            # (not fully decoded) node numbering cannot matter - same meshes => same tree => same nodes
            bad = []
            for vn in closure(src, [root])['order']:
                sL = src.find_vnam(vn)
                smesh = src.find_resource('LOCAL:models/%s.mef' % sL.entry(vn)[0], 'models')[1]
                tmesh = used_mesh.get(vn)
                if tmesh is None:
                    tL = target.find_vnam(vn)
                    tmesh = target.find_resource('LOCAL:models/%s.mef' % tL.entry(vn)[0], 'models')[1] if tL else None
                if tmesh != smesh:
                    bad.append(vn)
            lm_src = src
            if bad:
                donor = lightmap_donor(root, target, used_mesh)
                if donor is None:
                    # no level ships those exact meshes: copy the source's set anyway. The engine checks every .olm against
                    # its node's mesh (timestamp + face count, 0x54f0bb) and gives only the mismatching nodes (here: the
                    # other copies, e.g. furniture) a blank lightmap - the shell keeps its shading instead of all-blank
                    # (owner 10-11: blank = 'super bright' towers and buildings)
                    rep['warnings'].append('lightmaps of source task %d copied though the mission uses other copies of %s (those '
                                           'nodes get default lightmaps)' % (s_id, ', '.join(bad[:6])))
                else:
                    lm_src, d_id = donor
                    got = instance_lightmaps(lm_src, d_id)
                    rep['warnings'].append('lightmaps of source task %d: borrowed from %s task %d (same meshes as the mission uses)' % (
                        s_id, lm_src.dir, d_id))
            clash = [(n, l) for name, n, l in got if (n_id, LM_RE.match(name).group(2), n, l) in taken]
            if clash:
                rep['warnings'].append('lightmaps for task %d already in the target (task id taken?) - not copied' % n_id)
                continue
            for name, node, lod in got:
                suffix = LM_RE.match(name).group(2)
                new = 'LOCAL:lightmaps/%04d%s_%04d_%d.olm' % (n_id, suffix, node, lod)
                lights.add(new, lm_src.lightmaps.get(name)); taken.add((n_id, suffix, node, lod)); rep['lightmaps'].append((name, new))
    out = dict(mtp=mtp.write(m), models=models.data(), textures=textures.data())
    if lights.raw is not None or lights.added:
        out['lightmaps'] = lights.data()
    rel = dict(mtp=target.name + '.mtp', models=os.path.join('models', target.name + '.res'),
               textures=os.path.join('textures', target.name + '.res'), lightmaps=os.path.join('lightmaps', 'lightmaps.res'))
    if write:
        for k, data in out.items():
            p = os.path.join(out_dir, rel[k])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'wb').write(data)
            rep['files'][k] = p
    rep['bytes'] = out
    return rep


def verify(out_dir, target):
    """re-read merged files: every manifest entry must resolve to a resource somewhere in the mission's chain"""
    problems = []
    raw = open(os.path.join(out_dir, target.name + '.mtp'), 'rb').read()
    p = 12
    while p < len(raw):                                   # walk it like the engine (0x503a90): size rounded up to 4
        sz = struct.unpack('>I', raw[p + 4:p + 8])[0]
        if sz % 4:
            problems.append('manifest chunk %r is %d bytes (not 4-aligned): the engine would lose the following chunks' % (raw[p:p + 4], sz))
        p += 8 + ((sz + 3) & ~3)
    if p != len(raw):
        problems.append('manifest chunk walk ends at %d, file is %d bytes' % (p, len(raw)))
    m = mtp.read(os.path.join(out_dir, target.name + '.mtp'))
    models = Res(os.path.join(out_dir, 'models', target.name + '.res'))
    textures = Res(os.path.join(out_dir, 'textures', target.name + '.res'))
    lower = target.layers[:-1]
    for n in m['MODS']:                                   # own bank only (true for every shipped manifest)
        if not models.has('LOCAL:models/%s.mef' % n):
            problems.append('mesh %s is not in the own models .res of this manifest' % n)
    for n in m['SVOL']:
        nm = 'LOCAL:models/%s.mef' % n
        if not models.has(nm) and not any(L.models.has(nm) for L in lower):
            problems.append('shadow volume %s not in any models .res' % n)
    for n in m['TEXF']:
        if not textures.has('LOCAL:textures/%s.tex' % n):
            problems.append('texture %s is not in the own textures .res of this manifest' % n)
    if len(m['VNAM']) != len(m['INST']):
        problems.append('VNAM/INST count mismatch')
    for vn, (mi, g) in zip(m['VNAM'], m['INST']):
        if mi >= len(m['MODS']) or any(x >= len(m['GTT']) for x in g):
            problems.append('%s: index out of range' % vn)
    for t, pl in m['GTT']:
        if t >= len(m['TEXF']):
            problems.append('GTT texture index out of range')
    for p in (os.path.join(out_dir, 'models', target.name + '.res'), os.path.join(out_dir, 'textures', target.name + '.res'),
              os.path.join(out_dir, 'lightmaps', 'lightmaps.res')):
        if os.path.exists(p):
            form, ch, h = ilff.read(p)
            if any(t == b'PATH' for t, b, a in ch):
                problems.append('%s has a PATH chunk' % p)
            if ilff.write(form, ch, h[1]) != open(p, 'rb').read():
                problems.append('%s does not re-serialise byte-identically' % p)
    return problems


def provided_models(out_dir, name):
    """model names a merged level manifest provides (for Mission.models / validate())"""
    return {v.lower() + '.mef' for v in mtp.read(os.path.join(out_dir, name + '.mtp'))['VNAM']}


# ----------------------------------------------------------------------------- CLI
def _show(src, ids):
    cl = closure(src, ids)
    for vn in cl['order']:
        it = cl['vnams'][vn]
        print('%-12s %-8s mesh %-12s textures %s' % (vn, it['layer'].kind, it['mef'], ', '.join(it['textures'])))
    for n, L in cl['svols'].items():
        print('shadow volume %s (%s)' % (n, L.kind))
    for p, a in cl['unresolved']:
        print('unresolved attachment %s -> %s' % (p, a))


def selftest():
    import shutil
    ok = True
    base = os.path.join(HERE, 'out', 'selftest')
    targets = [os.path.join(GAME, 'MISSIONS', *p.split('/')) for p in
               ('location1/level1', 'location2/LEVEL3', 'location3/LEVEL5', 'location3/level1', 'multiplayer/sandstorm', 'multiplayer/jungle')]
    # 1. no-op merges reproduce every input byte for byte
    for t in targets:
        lv = Level(t)
        rep = merge(lv, None, [], write=False)
        for k, data in rep['bytes'].items():
            same = data == open(lv.paths[k], 'rb').read()
            ok &= same
            print('no-op %-26s %-9s byte-identical: %s' % (os.path.relpath(t, GAME), k, same))
    # 2. merging models the target already has is also a no-op
    lv = Level(os.path.join(GAME, 'MISSIONS', 'location1', 'level1'))
    rep = merge(lv, None, [(lv, ['400_10_1', '414_02_1'], {})], write=False)
    for k, data in rep['bytes'].items():
        same = data == open(lv.paths[k], 'rb').read()
        ok &= same
        print('self-merge location1/level1 %-9s byte-identical: %s  (skipped %d vnams)' % (k, same, len(rep['skipped_vnams'])))
    # 3. a real transplant: the location1 mine building + its attachments into Sandstorm, with its lightmaps
    src = Level(os.path.join(GAME, 'MISSIONS', 'location1', 'level1'))
    dst = Level(os.path.join(GAME, 'MISSIONS', 'multiplayer', 'sandstorm'))
    out = os.path.join(base, 'sandstorm_minebuilding')
    if os.path.isdir(out):
        shutil.rmtree(out)
    rep = merge(dst, out, [(src, ['400_10_1'], {4010: 1700})])
    print('transplant 400_10_1 -> sandstorm: +%d vnams %s, +%d meshes, +%d textures, %d textures reused, +%d lightmaps, %d warnings' % (
        len(rep['added_vnams']), rep['added_vnams'], len(rep['added_meshes']), len(rep['added_textures']), len(rep['reused_textures']),
        len(rep['lightmaps']), len(rep['warnings'])))
    for w in rep['warnings']:
        print('  warn:', w)
    probs = verify(out, dst)
    print('verify:', probs or 'OK'); ok &= not probs
    merged = Level(dst.dir, files_dir=out)
    lods = merged.lods('400_10_1')
    print('engine LOD expansion in merged Sandstorm: 400_10_1 ->', lods); ok &= lods == src.lods('400_10_1')
    c_src, c_dst = closure(src, ['400_10_1']), closure(merged, ['400_10_1'])
    same = c_src['order'] == c_dst['order'] and all(
        geometry_key(merged.find_resource('LOCAL:models/%s.mef' % c_dst['vnams'][v]['mef'], 'models')[1]) ==
        geometry_key(src.find_resource('LOCAL:models/%s.mef' % c_src['vnams'][v]['mef'], 'models')[1]) and
        c_dst['vnams'][v]['textures'] == c_src['vnams'][v]['textures'] and
        all(merged.find_resource('LOCAL:textures/%s.tex' % t, 'textures')[1] == src.find_resource('LOCAL:textures/%s.tex' % t, 'textures')[1]
            or dst.find_resource('LOCAL:textures/%s.tex' % t, 'textures')[1] is not None          # name pre-existed: target wins
            for t in c_src['vnams'][v]['textures'])
        for v in c_src['order'])
    print('merged closure == source closure (meshes, texture slots, texture bytes unless the name pre-existed):', same); ok &= same
    lm = instance_lightmaps(merged, 1700)
    print('lightmaps now owned by task 1700:', len(lm), 'nodes', sorted({n for _, n, _ in lm})); ok &= len(lm) == len(instance_lightmaps(src, 4010))
    # 4. idempotent: merging the same model into the merged files changes nothing
    rep2 = merge(merged, None, [(src, ['400_10_1'], {})], write=False)
    idem = all(rep2['bytes'][k] == open(rep['files'][k], 'rb').read() for k in rep['files'])
    print('second merge into the output is a byte-identical no-op:', idem); ok &= idem
    # 5. target already ships its own copies of the meshes -> lightmaps must NOT be copied
    tb = Level(os.path.join(GAME, 'MISSIONS', 'multiplayer', 'timberland'))
    rep3 = merge(tb, None, [(src, ['400_10_1'], {4010: 1700})], write=False)
    nolm = not rep3['lightmaps'] and any('NOT copied' in w for w in rep3['warnings'])
    print('timberland already has 400_10_1 (other copies): lightmaps withheld:', nolm); ok &= nolm
    # 6. never write into the game folder
    try:
        merge(dst, os.path.join(GAME, 'MISSIONS', 'multiplayer', 'sandstorm'), [], write=True); refused = False
    except ValueError:
        refused = True
    print('refuses an out dir inside the game folder:', refused); ok &= refused
    print('SELFTEST', 'PASSED' if ok else 'FAILED')
    return ok


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0] == 'selftest':
        sys.exit(0 if selftest() else 1)
    if a[0] == 'show':
        _show(Level(a[1]), a[2:])
    elif a[0] == 'merge':
        lm = {}
        rest = a[5:]
        for i, x in enumerate(rest):
            if x == '--lightmap':
                s, n = rest[i + 1].split('='); lm[int(s)] = int(n)
        src, dst = Level(a[1]), Level(a[2])
        rep = merge(dst, a[3], [(src, a[4].split(','), lm)])
        for k in ('added_vnams', 'skipped_vnams', 'added_meshes', 'added_textures', 'reused_textures', 'added_svols', 'lightmaps', 'warnings'):
            print(k, rep[k])
        print('verify:', verify(a[3], dst) or 'OK')
        for k, p in rep['files'].items():
            print('wrote', p)
