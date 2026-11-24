"""albuild - asset library (2026-10-31): buildings and doors of OTHER NATIONS for any custom mission, made from the ORIGINAL
game's buildings (their real geometry, interiors, props, lightmaps and working doors) re-dressed per theme with altex,
plus weathered wall / post signs in the right language. Additive: nothing existing changed.

Why originals and not new meshes: the owner (10-31) wants original-asset quality; the original buildings are lightmapped,
furnished (barracks beds, command-centre consoles, armoury gun racks) and their doors work. A theme VARIANT is a new
virtual model (<theme><5 digits>_1, LODs _2.._5) that uses the SAME mesh (so the instance's transplanted lightmaps still
match: lightmaps are keyed by task + mesh copy, research/prefabs) with its texture slots pointing at re-toned copies.
The stock model stays untouched (other buildings / the MP map keep the original look).

    import prefabs, albuild
    X = prefabs.Transplant(K)
    D = albuild.Dresser(K, X)
    bid, doors = D.place('cn', 'cn_hq', pos, yaw, parent=DYN, name='PLA HQ')      # a catalog key (BUILDINGS below)
    bid, doors = D.place('ar', ('location2/LEVEL2', 4078), pos, yaw, parent=DYN)  # or any original instance
    D.sign('cn_restricted', wall_pos, gamma, parent=DYN)                          # a plate on a wall (+y = its face)
    D.post_sign('av_jetblast', ground_pos, gamma, parent=DYN)                     # a sign board on two posts
    PROVIDED, MERGED = X.finish(OUT_DIR)                                          # (the usual)
    D.finish(OVERLAY, MAP)              # after X.finish: variants + signs into the overlay, task models switched
    lodfix.apply(m, OVERLAY, base, extra={**other, **D.lod_rows()})              # (NEW names need rows, owner 10-18)

Doors that come with a building are themed too (a door variant per door model); `door_theme=False` keeps them stock.
Put buildings with doors under the DYNAMIC root (owner rule 13).
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp
import altex
import modelkit as MK
import biprefabs as BP
from mission_lib import T, v
from qast import lit, tasks

M = 4096.0
THEMES = list(altex.THEMES)
PFX = {'cn': 'cn', 'ar': 'ar', 'sea': 'se', 'nato': 'nt', 'alpine': 'ap', 'liv_desert': 'ld', 'liv_grey': 'lg', 'liv_green': 'lv',
       'liv_black': 'lb'}

# The catalog: key -> (source level, source task id, original model, what it is / its interior). Every entry is a FURNISHED
# original instance (its children = the props inside); 'theme' = the themes it was checked with in the asset lab.
def size_m(key):
    """(x, y, z) metres of a catalog building (research catalog; for camera distances / spacing)"""
    import json
    if not hasattr(size_m, 'cat'):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'research', 'prefabs', 'catalog.json')
        size_m.cat = {e['id']: e for e in json.load(open(p))}
    return tuple(size_m.cat[BUILDINGS[key][2]]['size_m'])


BUILDINGS = {
    # --- command / admin
    'cn_hq':        ('location3/LEVEL5', 4085, '407_01_1', 'command centre, 2 floors on stilts: consoles, radar screens, 8 doors, a radio mast', 'cn nato alpine'),
    'office_ru':    ('location1/level3', 4086, '413_01_1', 'office building: desks, filing cabinets, computers, 5 doors', 'nato alpine'),
    'admin_lib':    ('location2/LEVEL6', 3891, '434_24_1', 'admin block on columns: offices, an alarm switch, 5 doors', 'ar nato'),
    # --- barracks / quarters
    'barracks_l':   ('location3/LEVEL5', 4084, '407_03_1', 'L-shaped barracks: bunks, lockers, tables, 15 doors', 'cn nato sea'),
    'hall_cn':      ('location3/level3', 3862, '406_68_1', 'Chinese hall (curved roof): 8 beds, chairs - officers quarters', 'cn'),
    'barracks_lib': ('location2/LEVEL2', 4029, '401_85_1', 'flat-roof barracks house: beds, lockers, a terminal, 1 door', 'ar sea'),
    # --- guard / gate
    'guardhouse':   ('location2/LEVEL2', 4078, '401_86_1', 'guard house with a tower, 2 floors: tables, crates, beds', 'ar sea'),
    'gatehouse':    ('location2/LEVEL2', 4047, '401_88_1', 'gatehouse with a stone arch, stairs to the top, a gate switch', 'ar'),
    # --- vehicles / aircraft / storage
    'garage':       ('location3/LEVEL5', 4077, '407_05_1', 'vehicle garage: 2 roll doors, trucks, oil drums, a switch', 'cn nato alpine'),
    'hangar':       ('location2/LEVEL4', 4074, '434_05_1', 'arched aircraft hangar (open ends)', 'alpine ar nato'),
    'armoury':      ('location2/LEVEL4', 4065, '434_06_1', 'storage / armoury: 22 GUN PICKUPS on racks, crates, 3 doors', 'nato alpine ar'),
    'warehouse':    ('location2/LEVEL6', 4072, '434_25_1', 'large warehouse: crates, shelves, 5 doors', 'alpine nato sea'),
    # --- comms / tower
    'tower':        ('location2/LEVEL4', 2040, '434_03_1', 'airfield control tower: radio room, maps, tables, 4 doors', 'alpine sea ar'),
    'radio_cabin':  ('location3/level1', 3776, '406_28_1', 'radio cabin (camo roof): radios, consoles, 2 doors', 'sea cn'),
}

# role overrides per original texture (classify() is a guess; these were checked in the previews)
ROLE = {'436_06_1': 'detail', '407_12_1': 'metal', 'pole': 'metal', 'multi': 'metal', 'metal_tiles': 'roof', 'brickwall': 'wall!',
        'cement': 'wall', 'metal_roof': 'roof', '407_04_1': 'metal', 'barracks': 'metal', '460_46_1': 'roof', '407_45_1': 'metal',
        '432_05_1': 'wall', '432_01_1': 'wall', '432_02_1': 'wall', '432_06_1': 'wall', '405_21_1': 'detail', '405_08_1': 'detail',
        '431_11_1': 'wood', '433_23_1': 'wall', '433_37_1': 'roof', '433_24_1': 'metal', '433_03_1': 'roof', '433_32_1': 'wall',
        '433_34_1': 'roof', '433_33_1': 'metal', '406_15_1': 'roof!', 'ornamentnew': 'detail', '800_02_1': 'detail', '407_29_1': 'detail',
        'sida': 'detail', '407_34_1': 'roof', 'wall_tile': 'detail', 'ceil2': 'detail', '413_08_1_argb8888': 'glass',
        '413_06_1': 'detail', '413_21_1': 'detail', '436_05_1': 'detail', '436_02_1': 'detail', '433_44_1': 'detail',
        '407_07_1': 'metal', '407_05_1': 'wall', '407_06_1': 'metal', '433_21_1': 'wall', '433_22_1': 'metal', '433_18_1': 'detail',
        '433_20_1': 'metal', '433_12_1': 'metal', '400_23_1': 'wall', '433_10_1': 'metal', '406_33_1': 'detail', '406_34_1': 'detail'}

LOD_CUT = 1500.0


def variant_name(theme, src_vn):
    """'407_01_1' + cn -> 'cn40701_1' (LOD k: last digit k); fits the engine's 15 chars + LOD bump rule"""
    d = src_vn.replace('_', '')[:-1]
    out = '%s%s_1' % (PFX[theme], d)
    assert src_vn.endswith('_1') and len(out) <= 15, ('variant name', src_vn, out)
    return out


class Dresser:
    def __init__(self, kit, X):
        self.K, self.m, self.X = kit, kit.m, X
        self.items = []                 # (task id, src model, theme, door ids, door_theme)
        self.signs = []                 # (task id, sign id, kind)
        self.made = {}                  # variant name -> source model
        self.retoned = {}

    # ------------------------------------------------------------------ placement (before X.finish)
    def place(self, theme, what, pos, yaw, parent, name=None, door_theme=True, sanitize=True, door_root=None, prop_cap=None, **kw):
        """theme None = the stock original (for side-by-side comparisons). sanitize: drop the source level's logic
        children (terminals, switches, TBAs, sequences: their expressions name SOURCE tasks), keep geometry, props,
        gun pickups (the armoury racks) and the doors (rules cleared = ordinary doors that open with E).
        RECOMMENDED: parent = the STATIC root + door_root = the DYNAMIC root: the shell and its props stay static, the doors
        move into a container under Dynamic (they only open there, owner rule 13). 24 furnished buildings with all their
        props under Dynamic overflowed an engine pool of 1000 at load (asset lab 10-31: CRASH igi2.exe+0x1b0f07)."""
        assert theme is None or theme in altex.THEMES, theme
        rel, src, model = (BUILDINGS[what][:3] if isinstance(what, str) else (what[0], what[1], None))
        if kw.pop('fit', True) and kw.get('on_ground', True):
            z, dz = self.ground_z(rel, src, float(pos[2]))
            pos = (pos[0], pos[1], z); kw['on_ground'] = False
        bid, doors = self.X.place(rel, src, pos, yaw, parent, name=name or 'AL %s %s' % (theme or 'stock', what), **kw)
        model = model or str(lit(self.m.byid[bid].args[9]))
        if sanitize:
            self.sanitize(bid)
            doors = [d for d in doors if d in self.m.byid]
        if prop_cap:
            self.cap_props(bid, prop_cap)
        if door_root is not None and doors:
            self.move_doors(doors, door_root, 'AL doors of %s' % (name or what))
        if theme is not None:
            self.items.append((bid, model, theme, doors, door_theme, 9))
        return bid, doors

    def cap_props(self, root, per_model):
        """keep at most per_model copies of each prop model inside a building (the command centre carries 71 x 205_25_1):
        the ENGINE has a 1000-entry rigid-object list (asset lab 10-31: 1526 EditRigidObj = CRASH igi2.exe+0x1b0f07 at load;
        the busiest original level has 848). Spreads the kept copies over the building (every k-th)."""
        from collections import defaultdict
        by = defaultdict(list)
        for t_, d_, p_ in tasks([self.m.byid[root]]):
            if lit(t_.args[1]) == 'EditRigidObj' and lit(t_.args[0]) != root:
                by[str(lit(t_.args[9]))].append(lit(t_.args[0]))
        gone = 0
        for mdl, ids in by.items():
            if len(ids) > per_model:
                keep = set(ids[::max(1, len(ids) // per_model)][:per_model])
                for i_ in ids:
                    if i_ not in keep and i_ in self.m.byid:
                        self.m.remove(i_); gone += 1
        return gone

    def move_doors(self, doors, door_root, label):
        """detach Door tasks from a building subtree into a new container under door_root (positions are absolute)"""
        from mission_lib import T as _T
        cid = self.K.nid()
        self.m.add_child(door_root, _T(cid, 'Container', label, False))
        for d in doors:
            t_ = self.m.byid[d]
            self.m.remove(d)
            self.m.add_child(cid, t_)
        return cid

    KEEP = {'Building', 'EditRigidObj', 'LightmapInfo', 'Door', 'ExplodeObject', 'Container', 'GunPickup', 'RotateAttachment'}

    def sanitize(self, root):
        """(Glasshouse / Sirocco recipe) -> (dropped, cleared)"""
        import re
        from mission_lib import v as _v
        m = self.m
        refx = re.compile(r'[A-Z][A-Za-z0-9]+(?:_[A-Z][A-Za-z0-9]+)*_[0-9]+[.]')
        drop = [lit(t_.args[0]) for t_, d_, p_ in tasks([m.byid[root]]) if lit(t_.args[1]) not in self.KEEP]
        for i_ in drop:
            if i_ in m.byid:
                m.remove(i_)
        cleared = 0
        for t_, d_, p_ in tasks([m.byid[root]]):
            if lit(t_.args[1]) == 'Door':
                for k_ in (18, 19, 20):
                    t_.args[k_] = _v('')
            for k_, a_ in enumerate(t_.args):
                if isinstance(lit(a_), str) and refx.search(str(lit(a_))):
                    t_.args[k_] = _v(''); cleared += 1
        m.reindex()
        return len(drop), cleared

    def ground_z(self, rel, src, ground_z, tol_m=1.5):
        """z for an instance so it STANDS on ground_z: the source's own height above its ground when that is normal
        (|dz| <= tol_m: foundations, steps), else its collision bottom on the ground (the source sat on a pier, a deck or
        flew: L26 admin block on the docks, the L11 C-130 in the air - asset lab 10-31 had both floating)"""
        import terrain as terrain_mod
        S = self.X._source(rel)
        t_, p_ = S['byid'][src]
        P = np.array([float(lit(t_.args[3 + k])) for k in range(3)])
        if 'terrain' not in S:
            S['terrain'] = terrain_mod.Terrain(S['dir'], S['st'])
        g = float(S['terrain'].height(P[0], P[1]))
        dz = P[2] - g if not np.isnan(g) else 1e9
        if abs(dz) <= tol_m * M:
            return ground_z + dz, dz / M
        lo, hi = self.X._footprint(S, t_)
        bottom = float(lo[2]) - P[2]                     # (collision bottom relative to the origin)
        return ground_z - bottom, -bottom / M

    def theme_task(self, tid, theme, arg=None):
        """re-style ANY placed task's model (an aircraft EditRigidObj, a helicopter, a truck, a door) with a theme or livery;
        the model must be in the merged manifest (X.place / X.models / cine). arg = the model argument (default: 9, Door 12)"""
        ty = str(lit(self.m.byid[tid].args[1]))
        arg = arg if arg is not None else (12 if ty == 'Door' else 9)
        self.items.append((tid, str(lit(self.m.byid[tid].args[arg])), theme, [], False, arg))
        return tid

    def sign(self, sid, pos, gamma, parent, name=None):
        """a wall plate: pos = the point ON the wall (its back), gamma = the plate's facing (+y out of the wall)"""
        i = self.K.nid()
        self.m.add_child(parent, T(i, 'EditRigidObj', name or 'AL sign %s' % sid, float(pos[0]), float(pos[1]), float(pos[2]),
                                   0.0, 0.0, float(gamma), self._sign_model(sid, 'plate'), 5, False, False))
        self.signs.append((i, sid, 'plate'))
        return i

    def post_sign(self, sid, pos, gamma, parent, name=None):
        i = self.K.nid()
        self.m.add_child(parent, T(i, 'EditRigidObj', name or 'AL post sign %s' % sid, float(pos[0]), float(pos[1]), float(pos[2]),
                                   0.0, 0.0, float(gamma), self._sign_model(sid, 'post'), 5, False, False))
        self.signs.append((i, sid, 'post'))
        return i

    @staticmethod
    def _sign_model(sid, kind):
        return ('alp_%s_1' if kind == 'post' else 'als_%s_1') % sid[:9]

    # ------------------------------------------------------------------ after X.finish
    def finish(self, overlay_dir, level_name, sign_set=()):
        """sign_set = [(sign id, 'plate'|'post')] built now and placed later (after navgen: D.sign / D.post_sign)"""
        base = level_name.replace('\\', '/').split('/')[-1]
        mp = os.path.join(overlay_dir, base + '.mtp')
        tp = os.path.join(overlay_dir, 'textures', base + '.res')
        mm = mtp.read(mp)
        form, ch, hdr = ilff.read(open(tp, 'rb').read())
        bodies = {}
        for k, (tag, data, al) in enumerate(ch):
            if tag == b'NAME' and k + 1 < len(ch):
                bodies[data.rstrip(b'\0').decode('latin1')] = k + 1
        report = []

        def tex_variant(tname, theme):
            key = (tname, theme)
            if key in self.retoned:
                return self.retoned[key]
            src_key = 'LOCAL:textures/%s.tex' % tname
            if src_key not in bodies:
                self.retoned[key] = None; return None
            b = ch[bodies[src_key]][1]
            if not altex.supported(b):
                self.retoned[key] = None; return None
            rgb, a, hdr_ = altex.read(b)
            role = ROLE.get(tname.strip()) or altex.classify(rgb, tname.strip())   # (shipped names can end in a space)
            if role.rstrip('!') in ('glass', 'detail') and not altex.THEMES[theme].get(role.rstrip('!')):
                self.retoned[key] = None; return None
            out = altex.retone(rgb, role, theme, seed=sum(map(ord, tname)) % 991)
            nn = '%s_%s' % (PFX[theme], tname.strip())[:24]
            ch.append((b'NAME', ('LOCAL:textures/%s.tex' % nn).encode('latin1') + b'\0', 4))
            ch.append((b'BODY', altex.write_like(b, out, a), 4))
            bodies['LOCAL:textures/%s.tex' % nn] = len(ch) - 1
            mm['TEXF'].append(nn)
            mm['GTT'].append([len(mm['TEXF']) - 1, -1])
            self.retoned[key] = len(mm['GTT']) - 1
            assert self.retoned[key] < mtp.COMMON_BIT and len(mm['TEXF']) - 1 < mtp.COMMON_BIT
            report.append('%s %s -> %s (%s)' % (theme, tname, nn, role))
            return self.retoned[key]

        def model_variant(src_vn, theme):
            new1 = variant_name(theme, src_vn)
            if new1 in self.made:
                return new1
            if src_vn not in mm['VNAM']:
                return None
            for lod in range(1, 6):
                s = src_vn[:-1] + str(lod)
                if s not in mm['VNAM']:
                    break
                mods_i, gtts = mm['INST'][mm['VNAM'].index(s)]
                ng = []
                for gi in gtts:
                    if gi >= mtp.COMMON_BIT:
                        ng.append(gi); continue
                    ti, pal = mm['GTT'][gi]
                    if ti >= mtp.COMMON_BIT:
                        ng.append(gi); continue
                    r = tex_variant(mm['TEXF'][ti], theme)
                    ng.append(gi if r is None else r)
                mm['VNAM'].append(new1[:-1] + str(lod))
                mm['INST'].append([mods_i, ng])
            self.made[new1] = src_vn
            return new1

        n_sw = 0
        for bid, model, theme, doors, door_theme, marg in self.items:
            nv = model_variant(model, theme)
            assert nv, 'model %s of task %d is not in the merged manifest' % (model, bid)
            self.m.set(bid, marg, nv); n_sw += 1
            if door_theme:
                for did in doors:
                    dm = str(lit(self.m.byid[did].args[12]))         # (Door: arg 12 = Model, decl location3/LEVEL5)
                    if dm in mm['VNAM']:
                        dv = model_variant(dm, theme)
                        if dv:
                            self.m.set(did, 12, dv); n_sw += 1
        mm_bytes = mtp.write(mm)
        open(tp, 'wb').write(ilff.write(form, ch, hdr[1] or 4))
        open(mp, 'wb').write(mm_bytes)
        # signs: modelkit plates / post boards (vertex-lit, like the originals' small signs)
        want = [(sid, kind) for i, sid, kind in self.signs] + list(sign_set)
        if want:
            lib = MK.Library()
            lib.texture('al_steel', lambda: BP.tex_steel(64, seed=7, base=(0.40, 0.40, 0.41)))
            lib.texture('al_galv', lambda: BP.tex_steel(64, seed=8, base=(0.55, 0.56, 0.57)))
            for sid, kind in want:
                nm = self._sign_model(sid, kind)
                if nm in lib.builders:
                    continue
                tn = 'alsg_%s' % sid[:12]
                lib.texture(tn, lambda sid=sid: altex.sign(sid))
                w, h = altex.SIGNS[sid][3]
                if kind == 'post':
                    lib.add(nm, lambda w=w, h=h: _post_sign(w, h), ['al_galv', tn], lod_like='406_68_1')
                else:
                    lib.add(nm, lambda w=w, h=h: _plate(w, h), ['al_steel', tn], lod_like='406_68_1')
            lib.install(overlay_dir, level_name)
            self.sign_models = list(lib.names)
        else:
            self.sign_models = []
        names = set(self.sign_models)
        for nv, src in self.made.items():
            for lod in range(1, 6):
                n_ = nv[:-1] + str(lod)
                if n_ in mm['VNAM']:
                    names.add(n_)
        self.m.models |= {n.lower() + '.mef' for n in names}
        n_rigid = sum(1 for t_, d_, p_ in tasks(self.m.stmts) if lit(t_.args[1]) == 'EditRigidObj')
        print('albuild: %d EditRigidObj in the mission (engine list 1000, busiest original 848)%s' % (
            n_rigid, '  <-- WARNING: over budget, use prop_cap= / fewer buildings' if n_rigid > 900 else ''))
        assert n_rigid < 1000, 'EditRigidObj %d >= 1000: the game crashes at load (igi2.exe+0x1b0f07)' % n_rigid
        print('albuild: %d variants (%s), %d re-toned textures, %d task models switched, %d signs' % (
            len(self.made), ', '.join('%s<-%s' % kv for kv in self.made.items()), len(report), n_sw, len(want)))
        self.report = report
        return names

    def place_object(self, rel, src, pos, yaw, parent, name=None, livery=None):
        """any original object (aircraft, vehicle) standing on the ground at pos, sanitised, optionally in a livery"""
        z, dz = self.ground_z(rel, src, float(pos[2]))
        oid, _d = self.X.place(rel, src, (pos[0], pos[1], z), yaw, parent, name=name, doors=False, on_ground=False)
        self.sanitize(oid)
        if livery:
            self.theme_task(oid, livery)
        return oid

    def lod_rows(self):
        """{name: row} for lodfix extra: variants copy their source model's row, signs get 900 m"""
        import lodfix
        G = lodfix.read(os.path.join(lodfix.GAME, 'lod.qvm'))[2]
        out = {}
        for nv, src in self.made.items():                 # (no row anywhere: lodfix's own default for a placed building)
            out[nv] = list(G[src.lower()]) if src.lower() in G else [60.0, 120.0, 240.0, 480.0, LOD_CUT]
            out[nv][4] = max(out[nv][4], LOD_CUT)
        for n in getattr(self, 'sign_models', []):
            out[n] = [200.0, 400.0, 600.0, 800.0, 900.0]
        return out


SUN_TINT = {'cn': (1.0, 1.0, 1.0), 'ar': (0.93, 0.99, 1.06), 'sea': (0.95, 1.0, 1.03), 'nato': (1.02, 1.0, 0.99),
            'alpine': (1.05, 1.0, 0.96)}         # (BGR multipliers: desert warm, alpine cold)


def neutral_lightmaps(overlay_dir, ids, strength=0.85, tint=(1.0, 1.0, 1.0), log=print):
    """remove the SOURCE level's colour cast from these instances' lightmaps (a building from the snow level L13 came out
    blue in a desert, asset lab 10-31): every .olm's channel means are pulled toward their grey (strength 0..1), then
    `tint` (BGR) gives this level's sun colour. Brightness is lightcal.calibrate's job - call this BEFORE it."""
    import lightcal
    path = os.path.join(overlay_dir, 'lightmaps', 'lightmaps.res')
    R, inst = lightcal.olm_instances(path)
    n = 0
    for tid in (inst if ids is None else ids):              # (ids None = every instance: props + doors carry their own)
        for nm, mean, w, h in inst.get(int(tid), []):
            i = R.index[nm]
            b = bytearray(R.chunks[i][1])
            a = np.frombuffer(bytes(b[112:112 + w * h * 4]), 'u1').reshape(-1, 4).astype(float)
            cm = a[:, :3].mean(0) + 1e-3
            k = (1 - strength) + strength * (cm.mean() / cm)
            a[:, :3] = np.clip(a[:, :3] * k * np.asarray(tint, float), 0, 255)
            b[112:112 + w * h * 4] = np.round(a).astype('u1').tobytes()
            R.chunks[i] = (R.chunks[i][0], bytes(b), R.chunks[i][2]); n += 1
    open(path, 'wb').write(R.data())
    log('albuild: %d lightmaps of %d instances neutralised (strength %.2f, tint %s)' % (n, len(inst if ids is None else ids), strength, tuple(tint)))
    return n


def check_budget(m, limit=1000, warn=900):
    """call right before K.write (after EVERY placement, signs included): the engine has a 1000-entry rigid-object list
    (asset lab 10-31: 1526 EditRigidObj = CRASH igi2.exe+0x1b0f07 at load; the busiest original level has 848)"""
    n = sum(1 for t_, d_, p_ in tasks(m.stmts) if lit(t_.args[1]) == 'EditRigidObj')
    print('albuild budget: %d EditRigidObj (limit %d)%s' % (n, limit, '  <-- WARNING' if n > warn else ''))
    assert n < limit, 'EditRigidObj %d >= %d: the game crashes at load (igi2.exe+0x1b0f07)' % (n, limit)
    return n


# ===================================================================================================== sign meshes
def _plate(w, h, d=0.025):
    """back at y 0 (on the wall), face +y; origin = plate centre"""
    pl = BP.box_m(-w / 2, 0.0, -h / 2, w / 2, d, h / 2, uv=1.0)
    face = MK.panel((0.0, d + 0.012, 0.0), (-1, 0, 0), (0, 0, 1), w * 0.98, h * 0.98)    # (Sandstorm owner 115: 3 mm flickered from the side)
    return MK.model([(0, [pl]), (1, [face])], [pl])


def _post_sign(w, h, top=None):
    top = top if top is not None else h + 1.0
    steel = []
    for x in (-w / 2 + 0.12, w / 2 - 0.12):
        steel.append(BP.box_m(x - 0.04, -0.04, 0.0, x + 0.04, 0.04, top))
    board = BP.box_m(-w / 2, 0.04, top - h, w / 2, 0.07, top, uv=1.0)
    face = MK.panel((0.0, 0.082, top - h / 2), (-1, 0, 0), (0, 0, 1), w * 0.98, h * 0.98)
    return MK.model([(0, steel + [board]), (1, [face])], [board] + steel)


# ===================================================================================================== offline previews
def preview(out_png, specs, size=(640, 400)):
    """specs = [(theme or None, catalog key)] -> contact sheet, the original and its theme variants (mefrender)"""
    import modelpreview as MP, prefab
    from PIL import Image, ImageDraw
    tiles = []
    for theme, key in specs:
        rel, src, model = BUILDINGS[key][:3]
        lv = prefab.Level(os.path.join(prefab.GAME, 'MISSIONS', *rel.split('/')))
        orig_tex = MP._tex

        def themed(lv_, name, theme=theme):
            img = orig_tex(lv_, name)
            if img is None or theme is None:
                return img
            role = ROLE.get(name.strip()) or altex.classify(img[..., :3], name)
            if role in ('glass', 'detail'):
                return img
            return np.dstack([altex.retone(img[..., :3], role, theme, seed=sum(map(ord, name)) % 991), img[..., 3]])
        MP._tex = themed
        try:
            im = MP.preview(lv, model, size=size)
        finally:
            MP._tex = orig_tex
        tiles.append(('%s  %s (%s)' % (key, theme or 'ORIGINAL', model), im))
    cols = 3
    W, H = size
    rows = (len(tiles) + cols - 1) // cols
    sh = Image.new('RGB', (cols * W, rows * (H + 18)), 'black')
    dr = ImageDraw.Draw(sh)
    for k, (label, im) in enumerate(tiles):
        x, y = (k % cols) * W, (k // cols) * (H + 18)
        sh.paste(im.convert('RGB').resize(size), (x, y + 18)); dr.text((x + 4, y + 3), label, fill='yellow')
    sh.save(out_png)
    return out_png


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'preview':
        specs = []
        for a in sys.argv[3:]:
            th, key = a.split(':')
            specs.append((None if th == 'orig' else th, key))
        print(preview(sys.argv[2], specs))
