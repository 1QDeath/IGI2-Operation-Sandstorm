"""Reusable building blocks for IGI 2 custom missions (built on igiqvm / ilff / graph).

A Mission wraps one base level's decompiled objects and offers:
  * safe ID allocation (never 900-999: those are menu screens -> Esc/restart crash; always < 4096)
  * helpers to add tasks, squads, soldiers (+ their AI script files), objectives, status messages
  * validate(): unique ids, reserved ids, expression references resolve to tasks of the right
    type, models exist in the level/location/common resources, every HumanAI/AISquad has an AI
    file, every text key exists, weapon ids are valid, the compiled objects.qvm round-trips.
  * write(): objects.qvm, mission.qvm, ai/*.qvm and patched language .res files
"""
import math, os, random, re, shutil, struct
import igiqvm, ilff, graph
from igiqvm import Call, Int, Flt, Str, Ident, Neg
from qast import load, tasks, lit

GAME = r'C:\Users\1qdeath\Games\IGI2\app'
RESERVED = set(range(900, 1000))          # menu screen ids (mainmenu/ingamemenu)
MAX_ID = 4096
TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)

WEAPONS = {'AK47', 'APC', 'AUG', 'BARRET', 'BARRETTHERMO', 'BINOCULARS', 'COLT', 'DESERTEAGLE', 'DRAGUNOV',
           'FLASHBANG', 'G11', 'G36', 'GLOCK', 'GRENADE', 'HK104', 'JACKHAMMER', 'KNIFE', 'LASERDESIGNATOR', 'M16A2',
           'M2HB', 'MAC10', 'MAKAROV', 'MEDIPACK', 'MIL', 'MINIMI', 'MP5SD', 'PROXIMITYMINE', 'PSG1', 'PSG1SD',
           'RPG18', 'RPG7', 'RPG_IR', 'SENTRY', 'SMG2', 'SMOKEGRENADE', 'SOCOM', 'SPAS12', 'T80', 'THERMICAL',
           'TYPE64SMG', 'UZI', 'UZIX2'}


def v(x):
    if isinstance(x, (Call, Int, Flt, Str, Ident, Neg)):
        return x
    if isinstance(x, bool):
        return Ident('TRUE' if x else 'FALSE')
    if isinstance(x, int):
        return Neg(Int(-x)) if x < 0 else Int(x)
    if isinstance(x, float):
        return Neg(Flt(-x)) if x < 0 else Flt(x)
    if isinstance(x, str):
        return Str(x)
    raise TypeError(x)


def T(i, typ, name, *params, children=()):
    return Call('Task_New', [v(i), Str(typ), Str(name)] + [v(p) for p in params] + list(children))


def res_names(path):
    if not os.path.exists(path):
        return set()
    _, ch, _ = ilff.read(path)
    return {n.split('/')[-1].lower() for n, t, b in ilff.entries(ch) if n}


class Mission:
    def __init__(self, location, level_dir, level_name, seed=1):
        """location='location1', level_dir='level1' (folder under MISSIONS/<location>), level_name='level1' (file prefix)"""
        self.location, self.level_dir, self.level_name = location, level_dir, level_name
        self.src = os.path.join(GAME, 'MISSIONS', location, level_dir)
        decomp = os.path.join(ROOT, 'work', 'decomp', '%s_%s_objects.qsc' % (location, level_dir))
        if not os.path.exists(decomp):
            ver, st = igiqvm.decompile(open(os.path.join(self.src, 'objects.qvm'), 'rb').read())
            open(decomp, 'w', encoding='latin1', newline='\n').write(igiqvm.stmts_to_qsc(st))
        self.stmts = load(decomp)
        self.graphs = {}                        # generated AI graphs: id -> (graph .dat bytes, graphcover .dat bytes)
        self.rng = random.Random(seed)
        self.ai_files = {}                      # 'NNN' or 'Squad_NNN' -> template bytes
        self.text = {}                          # res file -> {key: text}
        self.reindex()
        self.used = set(self.byid)
        self.models = set()
        for p in (os.path.join(self.src, 'models', level_name + '.res'),
                  os.path.join(GAME, 'MISSIONS', location, 'common', 'models', location + '.res'),
                  os.path.join(GAME, 'COMMON', 'models', 'common.res')):
            self.models |= res_names(p)

    # ------------------------------------------------------------- lookup
    def reindex(self):
        self.byid, self.parent = {}, {}
        for t, d, p in tasks(self.stmts):
            i = lit(t.args[0])
            if isinstance(i, int) and i >= 0:
                self.byid[i] = t
                self.parent[i] = p

    def task(self, i):
        return self.byid[i]

    def typ(self, i):
        return lit(self.byid[i].args[1])

    def arg(self, i, idx):
        return lit(self.byid[i].args[idx])

    def set(self, i, idx, val):
        self.byid[i].args[idx] = v(val)

    def children(self, i):
        return [a for a in self.byid[i].args if isinstance(a, Call)]

    def add_child(self, parent_id, task):
        self.byid[parent_id].args.append(task)
        self.reindex()
        return task

    def new_id(self, lo=1, hi=MAX_ID):
        for i in range(lo, hi):
            if i in RESERVED or i in self.used:
                continue
            if os.path.exists(os.path.join(self.src, 'ai', '%d.qvm' % i)) or os.path.exists(os.path.join(self.src, 'ai', 'Squad_%d.qvm' % i)):
                continue
            self.used.add(i)
            return i
        if (lo, hi) == (1100, 2600):                        # (squad / soldier ids: that range is only the originals'
            return self.new_id(20, MAX_ID)                  #  habit - a big map with many transplants fills it, 10-11)
        raise RuntimeError('no free id in %d-%d' % (lo, hi))

    def reuse_id(self):
        """an id of a task removed from this level: when the free ranges are spent (ids stop at MAX_ID; 118 men and the rooms fill them)"""
        for i in sorted(getattr(self, 'freed', ())):
            if i in RESERVED or i < 20 or i in self.byid:
                continue
            if os.path.exists(os.path.join(self.src, 'ai', '%d.qvm' % i)) or os.path.exists(os.path.join(self.src, 'ai', 'Squad_%d.qvm' % i)):
                continue
            self.freed.discard(i)
            self.reused = getattr(self, 'reused', set()) | {i}
            return i
        raise RuntimeError('no free id and none to reuse')

    def remove(self, i):
        """delete task i (and its subtree) from its parent"""
        t, par = self.byid[i], self.parent[i]
        old = set(self.byid)
        if par is None:
            self.stmts.remove(t)
        else:
            par.args.remove(t)
        self.reindex()
        self.freed = getattr(self, 'freed', set()) | (old - set(self.byid))

    def import_decls(self, src_qsc, types=None):
        """copy Task_DeclareParameters for task types this level does not declare (e.g. SP types into an MP base)"""
        have = {lit(s.args[0]) for s in self.stmts if isinstance(s, Call) and s.name == 'Task_DeclareParameters'}
        add = [s for s in load(src_qsc) if isinstance(s, Call) and s.name == 'Task_DeclareParameters'
               and lit(s.args[0]) not in have and (types is None or lit(s.args[0]) in types)]
        n = max(k for k, s in enumerate(self.stmts) if isinstance(s, Call) and s.name == 'Task_DeclareParameters') + 1
        self.stmts[n:n] = add
        return [lit(s.args[0]) for s in add]

    def find(self, typ=None, name=None):
        return [i for i, t in self.byid.items() if (typ is None or lit(t.args[1]) == typ) and (name is None or name.lower() in str(lit(t.args[2])).lower())]

    def disable(self, i, why='disabled'):
        """turn a Container/ConditionalContainer (and its subtree) off by making it a ConditionalContainer('0')"""
        t = self.byid[i]
        kids = [a for a in t.args if isinstance(a, Call)]
        t.args = [Int(i), Str('ConditionalContainer'), Str('%s (%s)' % (lit(t.args[2]), why)), Str('0'), Str(''), Str('')] + kids
        self.reindex()

    # ------------------------------------------------------------- AI graph helpers
    def graph_nodes(self, g):
        if g in self.graphs:
            import tempfile
            f = tempfile.NamedTemporaryFile(delete=False, suffix='.dat'); f.write(self.graphs[g][0]); f.close()
            recs = graph.parse(f.name); os.unlink(f.name)
        else:
            recs = graph.parse(os.path.join(self.src, 'graphs', 'graph%d.dat' % g))
        out, cur = [], None
        for k, t, val in recs:
            if t == 8:
                cur = {'pos': val, 'crit': ''}; out.append(cur)
            elif t == 9 and cur is not None:
                cur['crit'] = val
        return [n['pos'] for n in out if n['crit'] == '']

    def soldier_positions(self):
        return [tuple(lit(x) for x in t.args[3:6]) for t in self.byid.values() if lit(t.args[1]) in ('HumanSoldier', 'HumanPlayer')]

    def pick(self, g, n, center=None, radius=None, zlo=-1e18, zhi=1e18, spacing=12000, avoid=9000, extra_avoid=()):
        cand = [p for p in self.graph_nodes(g) if zlo <= p[2] <= zhi and
                (center is None or math.hypot(p[0] - center[0], p[1] - center[1]) <= radius)]
        self.rng.shuffle(cand)
        occupied = self.soldier_positions() + list(extra_avoid)
        got = []
        d2 = lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1]) + abs(a[2] - b[2]) * 2
        for p in cand:
            if all(d2(p, q) >= spacing for q in got) and all(d2(p, q) >= avoid for q in occupied):
                got.append(p)
                if len(got) == n:
                    return got
        raise RuntimeError('graph %d: wanted %d got %d (cand %d)' % (g, n, len(got), len(cand)))

    # ------------------------------------------------------------- AI script templates
    def ai_template(self, kind):
        """generic | hold | squad | squad_hold — copied from the base level's own ai folder"""
        ai = os.path.join(self.src, 'ai')
        if not os.path.isdir(ai) or not os.listdir(ai):   # multiplayer maps ship no AI scripts (Jungle: no ai/ folder): use a campaign level's
            ai = os.path.join(GAME, 'MISSIONS', 'location2', 'level1', 'ai')
        sigs = {'generic': {'AIFunction_GetCurrentEventType', 'AIEVENT_CREATE', 'AIFunction_DefaultHandler'},
                'squad': {'AISquad_DefaultHandler'}}
        for f in sorted(os.listdir(ai)):
            p = os.path.join(ai, f)
            try:
                _, syms, _, _ = igiqvm.read_qvm(open(p, 'rb').read())
            except Exception:
                continue
            if kind in sigs and set(syms) == sigs[kind] and (f.startswith('Squad_') == (kind == 'squad')):
                return open(p, 'rb').read()
            if kind == 'squad_hold' and f.startswith('Squad_') and 'AISquadState_HoldArea' in syms and 'AISquad_DefaultHandler' in syms and len(syms) <= 14:
                return open(p, 'rb').read()
            if kind == 'hold' and not f.startswith('Squad_') and 'AIFunction_SetMinRangeAccuracy' in syms and 'AIAction_Idle' in syms and len(syms) <= 15:
                return self._sharpen(open(p, 'rb').read()) if getattr(self, 'sharp_hold', True) else open(p, 'rb').read()
        if kind == 'hold':
            # this level has no sniper/hold script: borrow Mission 35's (references only global AI functions)
            other = os.path.join(GAME, 'MISSIONS', 'location3', 'LEVEL5', 'ai', '575.qvm')
            _, syms, _, _ = igiqvm.read_qvm(open(other, 'rb').read())
            assert all(x.startswith(('AIFunction_', 'AIEVENT_', 'AIAction_')) for x in syms), syms
            return self._sharpen(open(other, 'rb').read()) if getattr(self, 'sharp_hold', True) else open(other, 'rb').read()
        if kind == 'squad_hold':
            return self.ai_template('squad')
        raise RuntimeError('no %s AI template in %s' % (kind, ai))

    @staticmethod
    def _sharpen(data):
        """bump view cone / accuracy literals of a 'hold' AI script (same byte sizes)"""
        b = bytearray(data)
        code_off = struct.unpack_from('<I', b, 44)[0]
        for m in re.finditer(rb'(?:\x09.|\x0a..)\x00\x18', bytes(b[code_off:]), re.S):
            i = code_off + m.start()
            if b[i] == 0x09:
                b[i + 1] = min(b[i + 1] + 15, 95) if b[i + 1] < 100 else b[i + 1]
            else:
                val = struct.unpack_from('<h', b, i + 1)[0]
                struct.pack_into('<h', b, i + 1, min(int(val * 1.3), 260))
        return bytes(b)

    # ------------------------------------------------------------- soldiers / squads
    def squad(self, parent_id, name, sqtype, members, alarm_switch=-1, alarm_control=-1):
        """members: list of dict(pos, model, weapons[list], ai_type, graph, ai='generic'|'hold'|<script bytes>, name='', gamma)"""
        sid = self.new_id(1100, 2600)
        kids = []
        for m in members:
            hid, aid = self.new_id(1100, 2600), self.new_id(1100, 2600)
            wp = ',\n'.join('Human_AddWeapon("WEAPON_ID_%s")' % w for w in m['weapons']) + ';'
            gamma = m.get('gamma', round(self.rng.uniform(0, 2 * math.pi), 6))
            pos = m['pos']
            kids.append(T(hid, 'HumanSoldier', m.get('name', ''), float(pos[0]), float(pos[1]), float(pos[2]), gamma,
                          m['model'], 1, wp, 1, -1,
                          children=[T(aid, 'HumanAI', '', m['ai_type'], 'HUMANAI_ANIMTYPE_SOLDIER_RIFLE', m['graph'])]))
            ai = m.get('ai', 'generic')                 # bytes = a ready AI script (tools/aiscript.py: patrol / sentry)
            self.ai_files[str(aid)] = ai if isinstance(ai, (bytes, bytearray)) else self.ai_template(ai)
            m['id'] = hid
        t = T(sid, 'AISquad', name, 2, Ident(sqtype), alarm_switch, alarm_control, -1, 30, 5, 60, children=kids)
        self.ai_files['Squad_%d' % sid] = self.ai_template('squad_hold' if sqtype == 'AIType_Defensive' else 'squad')
        self.add_child(parent_id, t)
        return sid, [m['id'] for m in members]

    # ------------------------------------------------------------- text
    def add_text(self, resfile, key, text):
        self.text.setdefault(resfile, {})[key] = text

    # ------------------------------------------------------------- validation
    def validate(self, extra_text_keys=()):
        problems = []
        ids = [lit(t.args[0]) for t, d, p in tasks(self.stmts)]
        pos_ids = [i for i in ids if isinstance(i, int) and i >= 0]
        dup = sorted(set(i for i in pos_ids if pos_ids.count(i) > 1))
        if dup: problems.append('duplicate ids %s' % dup[:10])
        if any(i >= MAX_ID for i in pos_ids): problems.append('id >= 4096')
        bad_res = sorted(i for i in pos_ids if i in RESERVED)
        if bad_res: problems.append('RESERVED menu ids used %s' % bad_res[:10])
        types = {lit(t.args[0]): lit(t.args[1]) for t, d, p in tasks(self.stmts)}
        alias = {'Wire': 'Wire', 'Car': 'Car'}
        for t, d, p in tasks(self.stmts):
            for a in t.args:
                if isinstance(a, Str):
                    for typ, n in re.findall(r'\b([A-Z][A-Za-z0-9]+(?:_[A-Z][A-Za-z0-9]+)*)_(\d+)\.(?:n|is|v|f)', a):
                        n = int(n)
                        if n not in types:
                            problems.append('task %s refs missing %s_%d' % (lit(t.args[0]), typ, n))
                        elif types[n] != typ:
                            problems.append('task %s refs %s_%d but id %d is a %s' % (lit(t.args[0]), typ, n, n, types[n]))
        declared = {lit(s.args[0]) for s in self.stmts if isinstance(s, Call) and s.name == 'Task_DeclareParameters'}
        import json as _j
        builtin = set(_j.load(open(os.path.join(ROOT, 'work', 'known_script_api.json'))).get('builtin_types', []))
        for typ in sorted({lit(t.args[1]) for t, d, p in tasks(self.stmts)} - declared - builtin):
            problems.append('task type %s used but not declared' % typ)
        # every Type.property / Function( used in script strings must exist somewhere in the original missions
        import json
        api = json.load(open(os.path.join(ROOT, 'work', 'known_script_api.json')))
        kp, kf = set(api['props']), set(api['funcs'])
        for t, d, p in tasks(self.stmts):
            for a in t.args:
                if isinstance(a, Str):
                    for typ, prop in re.findall(r'([A-Z][A-Za-z0-9]+)_\d+\.([A-Za-z]\w*)', a):
                        if typ + '.' + prop not in kp:
                            problems.append('task %s uses unknown property %s.%s' % (lit(t.args[0]), typ, prop))
                    for fn in re.findall(r'([A-Z][A-Za-z0-9]+_[A-Za-z]\w*)\s*\(', a):
                        if fn not in kf:
                            problems.append('task %s uses unknown function %s' % (lit(t.args[0]), fn))
        # models used by NEW/changed tasks must exist
        for t, d, p in tasks(self.stmts):
            for a in t.args:
                if isinstance(a, Str) and re.fullmatch(r'\d{3,4}_\d{2}_\d', a):
                    if (a.lower() + '.mef') not in self.models:
                        problems.append('task %s uses model %s not in level resources' % (lit(t.args[0]), a))
                if isinstance(a, Str):
                    for w in re.findall(r'WEAPON_ID_([A-Z0-9_]+)', a):
                        if w not in WEAPONS:
                            problems.append('task %s unknown weapon %s' % (lit(t.args[0]), w))
        skins = self.location_skins()
        for t, d, p in tasks(self.stmts):
            if lit(t.args[1]) in ('HumanSoldier', 'HumanPlayer') and str(lit(t.args[7])) not in skins:
                problems.append('task %s uses skin %s not used anywhere in %s' % (lit(t.args[0]), lit(t.args[7]), self.location))
            if lit(t.args[1]) == 'EditBoneObj' and str(lit(t.args[11])) not in skins:      # cutscene actors (Kit.actor)
                problems.append('actor %s uses skin %s not used anywhere in %s' % (lit(t.args[0]), lit(t.args[11]), self.location))
        # squads must be able to reach their alarm switch on their own AI graph (else: unreachable-target searches)
        gcache = {}
        for t, d, p in tasks(self.stmts):
            if lit(t.args[1]) != 'AISquad' or lit(t.args[5]) in (-1, None):
                continue
            sw = lit(t.args[5])
            if sw not in self.byid:
                problems.append('squad %s alarm switch %s missing' % (lit(t.args[0]), sw)); continue
            spos = [lit(x) for x in self.byid[sw].args[3:6]]
            for c in t.args:
                if isinstance(c, Call) and lit(c.args[1]) == 'HumanSoldier':
                    for a in c.args:
                        if isinstance(a, Call) and lit(a.args[1]) == 'HumanAI':
                            g = lit(a.args[-1])
                            nodes = gcache.setdefault(g, self.graph_nodes(g))
                            if min(math.dist(spos, n) for n in nodes) > 15000:
                                problems.append('squad %s (%s): alarm switch %d unreachable from graph %d' % (lit(t.args[0]), lit(t.args[2]), sw, g))
        # AI files
        _aid = os.path.join(self.src, 'ai')
        have = set(os.path.splitext(f)[0] for f in (os.listdir(_aid) if os.path.isdir(_aid) else [])) | set(self.ai_files)
        for t, d, p in tasks(self.stmts):
            ty = lit(t.args[1]); i = lit(t.args[0])
            if ty == 'HumanAI' and str(i) not in have: problems.append('HumanAI %d has no ai file' % i)
            if ty == 'AISquad' and ('Squad_%d' % i) not in have: problems.append('AISquad %d has no ai file' % i)
        # round trip
        data = igiqvm.compile_stmts(self.stmts)
        v2, st2 = igiqvm.decompile(data)
        if igiqvm.compile_stmts(st2, v2) != data: problems.append('objects.qvm does not round-trip')
        return problems

    def location_skins(self):
        import glob
        skins = set()
        for mtp in (os.path.join(GAME, 'MISSIONS', self.location, 'common', self.location + '.mtp'), os.path.join(GAME, 'COMMON', 'common.mtp')):
            if os.path.exists(mtp):
                txt = open(mtp, 'rb').read().decode('latin1')
                skins |= {n for n in re.findall(r'[a-z][a-z0-9]*\d_1(?=\x00)', txt)} | {n for n in re.findall(r'[a-z]+_1(?=\x00)', txt)}
        for f in glob.glob(os.path.join(ROOT, 'work', 'decomp', '%s_*_objects.qsc' % self.location)):
            for t, d, p in tasks(load(f)):
                if lit(t.args[1]) in ('HumanSoldier', 'HumanPlayer'):
                    skins.add(str(lit(t.args[7])))
        return skins

    # ------------------------------------------------------------- output
    def write(self, out_dir, mission_id, folder, sprite, debug=False, own_common=None):
        """own_common: None, or the folder (under MISSIONS/<location>) whose models/textures/mtp the installer links
        into <mission>/common - the mission then uses that as its 'common' path, with its own common/sounds bank
        (e.g. a multiplayer map with the Libya guard voices instead of the English MP radio lines)."""
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(os.path.join(out_dir, 'ai'))
        open(os.path.join(out_dir, 'objects.qsc'), 'w', encoding='latin1', newline='\n').write(igiqvm.stmts_to_qsc(self.stmts))
        open(os.path.join(out_dir, 'objects.qvm'), 'wb').write(igiqvm.compile_stmts(self.stmts))
        path = 'missions/%s/%s' % (self.location, folder)
        mission = [Call('DefineMission', [v(mission_id), Str('S'), Str('N'), Str('G'), Str('L'),
                                          Str('Mission %d Name' % mission_id), Str('Mission %d Desc' % mission_id), Str(''),
                                          Str(path), Str(path + '/common' if own_common else 'missions/%s/common' % self.location), Str(path),
                                          Str(self.location), Str(self.level_name), Str(sprite)])]
        open(os.path.join(out_dir, 'mission.qvm'), 'wb').write(igiqvm.compile_stmts(mission))
        for k, data in self.ai_files.items():
            if not str(k).startswith('Squad_') and os.environ.get('IGI_NODIFF') != '1':   # (10-18) one shared difficulty switch
                import diffscale
                data = diffscale.apply(data)
            open(os.path.join(out_dir, 'ai', '%s.qvm' % k), 'wb').write(data)
        if self.graphs:
            os.makedirs(os.path.join(out_dir, 'graphs'))
            for g, (gd, cover) in self.graphs.items():
                open(os.path.join(out_dir, 'graphs', 'graph%d.dat' % g), 'wb').write(gd)
                if cover is not None:
                    open(os.path.join(out_dir, 'graphs', 'graphcover%d.dat' % g), 'wb').write(cover)
        import json
        json.dump({'id': mission_id, 'location': self.location, 'base': self.level_dir, 'folder': folder,
                   'debug': bool(debug), 'text': self.text, 'own_common': own_common},
                  open(os.path.join(out_dir, 'meta.json'), 'w'), indent=1)


def write_lang(path_in, path_out, lang, entries):
    form, ch, h = ilff.read(path_in)
    names = {}
    for i, (tag, data, al) in enumerate(ch):
        if tag == b'NAME':
            names[data.rstrip(b'\0').decode('latin1')] = i
    path_idx = next((i for i, c in enumerate(ch) if c[0] == b'PATH'), None)
    new = []
    for key, text in entries.items():
        full = 'LOCAL:%s/%s' % (lang, key)
        if full in names:
            ch[names[full] + 1] = (b'CSTR', text.encode('latin1') + b'\0', 4)
        else:
            new += [(b'NAME', full.encode('latin1') + b'\0', 4), (b'CSTR', text.encode('latin1') + b'\0', 4)]
    if path_idx is not None:
        tag, data, al = ch[path_idx]
        lst = data.rstrip(b'\0').decode('latin1')
        lst += ''.join(';LOCAL:%s/%s' % (lang, k) for k in entries if ('LOCAL:%s/%s' % (lang, k)) not in names)
        ch[path_idx] = (b'PATH', lst.encode('latin1') + b'\0', al)
        ins = path_idx - 1
        ch = ch[:ins] + new + ch[ins:]
    else:
        ch = ch + new
    os.makedirs(os.path.dirname(path_out), exist_ok=True)
    open(path_out, 'wb').write(ilff.write(form, ch, h[1]))
