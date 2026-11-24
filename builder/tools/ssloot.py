"""ssloot - Sandstorm's optional exploration layer (owner 11-12, batch rc7s): reasons to go in and look round, no new objectives.

  1. A key chain: the armoury key lies on the duty sergeant's table in the rest hut by the east generator (TBA 150); it opens the south armoury beside the west generator (TBA 152)
     (its two doors), where the racks are and a reward that pays later: two medipacks and a Jackhammer on the bench.
     At a locked door a line says where the key is kept; on pickup a line says what it opens.
  2. Caches in side rooms the route never forces: the tool shed (rifle rounds), the food store (a medipack), the garage (grenades),
     the camera room (a silenced MP5SD).
  3. Three readables, picked up with E like any paper: a duty roster (points at the key), a marked map (points at the camera room),
     a delivery note (points at the garage).

ss-world owns the look of the rooms; this owns the pickups and the door locks. No new men, no new objective. Flag SS_LOOT=1 (default on).
Hooks in build_sandstorm.py (sandstorm-redo): ssloot.lib(_SLIB) before _SLIB.install, ssloot.apply(globals()) with the other late hooks.
Models: ss_key_1, ss_note_1 (orchestrator OK 11-12: they replace ss_chipa_1, ss_chipb_1, net 0 LOD with SS_BAY=1). SS_LOOT_MODELS=0 = no models: the key and
the papers use the original briefcase 806_01_1 (KEY_MODEL, NOTE_MODEL).
"""
import math, os
import numpy as np

LOOT = os.environ.get('SS_LOOT', '1') == '1'
MODELS = os.environ.get('SS_LOOT_MODELS', '1') == '1'
KEY_MODEL, NOTE_MODEL = ('ss_key_1', 'ss_note_1') if MODELS else ('806_01_1', '806_01_1')
M = 4096.0

# --- places, in the ssrooms building frames (local x, y, height over the building's floor): every spot sits on a surface ss-world put there
#     s4 rest hut: the duty table 231_03_1 at (1.4, -1.75), top 0.85, the UZI at (1.3, -1.45)
KEY_AT = ('s4', 0.6, -2.1, 0.47 + 0.006, 0.6)            # (rig 11-13: on the duty sergeant's chair seat, ssw_chr_1 top 0.47. On the table top it lay on 205_26_1 behind the chairs and was never taken: a GenericPickup is taken by walking close, the seat height like the roster's bench is)
ARMOURY = (74.5, 103.5, 82.0, 115.0)                       # (ssrooms 'arm', world m)
ARM_DOORS = [(74.52, 106.92), (74.52, 104.69)]             # (the map's two west leaves 4025, 4026, found by position)
NORTH_LEAVES = [(76.82, 113.6, 0.0), (79.03, 113.6, math.pi)]   # (ss-world 11-12: the north wall's bare doorway, x 76.8-78.9 at y 113.6, filled with a pair of the same 'Wooden door' 500_16_1 leaves, 1.11 m each; judge Q23 11-13: the east hinge at its jamb 79.03, the leaves meet at 77.93, no slit)
ARM_HINT = [(77.85, 115.1), (73.2, 105.8)]                 # (where the line shows: the lobby side of the north doors, outside the west pair)
REWARD = [('armoury jackhammer', 'WEAPON_ID_JACKHAMMER', 77.95, 107.35, 0.85 + 0.03, 3.141605, 1.449968, 0.2),
          ('armoury medipack 1', 'WEAPON_ID_MEDIPACK', 78.4, 107.86, 0.85 + 0.03, 0.0, 0.0, 1.1),
          ('armoury medipack 2', 'WEAPON_ID_MEDIPACK', 77.75, 107.86, 0.85 + 0.03, 0.0, 0.0, 1.8)]
CACHES = [('tool shed rifle rounds', 'WEAPON_ID_AK47', 's1', -1.3, 0.75, 0.9 + 0.03, (3.141605, 1.449968, 1.5708)),
          ('food store medipack', 'WEAPON_ID_MEDIPACK', 's5', -1.15, -1.3, 0.64 + 0.03, (0.0, 0.0, 0.4)),
          ('garage grenades', 'WEAPON_ID_GRENADE', 'g1', 0.17, 4.55, 0.9 + 0.4 + 0.03, (0.0, 0.0, 0.0)),
          ('camera room mp5sd', 'WEAPON_ID_MP5SD', 'sc', -4.5, -1.8, 3.57 + 0.85 + 0.03, (3.141605, 1.449968, 0.0))]
NOTES = [('duty roster', 'h1', 0.6, 1.95, 0.46 + 0.01, 0.3,
          "DUTY ROSTER, south compound: Sgt. Jabbar, rest hut by the east generator. The armoury key stays with the duty sergeant."),
         ('marked map', 's3', -0.55, -0.85, 0.47 + 0.008, 0.3,    # (rig 11-13: on the desk it lay on the cup 261_17_1 and was never taken; on the radio man's chair seat as the key)
          "A base plan, the security block ringed in red: 'spare MP5SD issued to the camera room, first floor'."),
         ('delivery note', 's5', -0.95, 0.1, 0.64 + 0.01, 1.2,    # (S7 11-15: 1.28 is the double stack at (-1.15, -2.7); under the note is a single pallet, top 0.63: it floated 0.65 m)
          "DELIVERY NOTE: one crate of hand grenades, signed for at the vehicle garage. Not yet collected.")]
KEY_LINE = "ARMOURY KEY. It opens the south armoury beside the west generator."
LOCK_LINE = "Locked. Pick the lock (hold E), or take the armoury key from the duty sergeant's rest hut by the east generator."   # (fix1120 L1)
PICK_S = 6.0                                               # (fix1120 L1, owner pic 1: "it says locked, there is nowhere you could get a key": the leaves also give to a 6 s lock pick, as the mission's other locked doors)


def _shed_x(b, x):
    """ssrooms.shed pulls what stands on a shed's west wall in by 0.15 m: the same here"""
    return x + 0.15 if b.startswith('s') and b != 'sc' and x < -1.0 else x


def _w(b, x, y, z, yaw=0.0):
    """a spot in a building's frame, z over its floor -> world (x, y, z, yaw)"""
    import ssrooms as R
    return R.W(b, _shed_x(b, x), y, _floor(b) + z, yaw)


def _floor(b):
    import ssrooms as R
    if b.startswith('g'):
        return R.FG
    if b in ('h1', 'sc', 'ps', 'pn', 'kr', 'ad'):
        return R.F0
    return R.FS


# ---------------------------------------------------------------- models (net 0 with ss_chipa_1 / ss_chipb_1, orchestrator OK 11-12)
def _tex():
    """128 x 128: a red key tag (top left), steel (top right), a typed sheet (bottom), a brown clipboard (right strip)"""
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (128, 128), (120, 120, 118))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 63, 63), fill=(150, 30, 22)); d.ellipse((24, 6, 38, 20), fill=(40, 10, 8)); d.text((14, 30), '17', fill=(235, 225, 205))
    for y in range(0, 64, 3):
        c = 132 + (y * 7) % 18; d.line((64, y, 127, y), fill=(c, c, c + 2))
    d.rectangle((0, 64, 95, 127), fill=(226, 222, 206))
    for k in range(12):
        y = 72 + k * 4
        d.line((6, y, 6 + 40 + (k * 13) % 40, y), fill=(70, 70, 76))
    d.rectangle((60, 112, 88, 118), outline=(160, 30, 30))
    d.rectangle((96, 64, 127, 127), fill=(96, 66, 38))
    a = np.asarray(im, float) / 255.0
    return np.dstack([a, np.ones((128, 128))])


def _key():
    """a ring, two keys and a big red tag (orchestrator 11-12: easy to notice), lying flat: origin on the table top. Drawn 1.8x a real key"""
    import modelkit as MK, biprefabs as BP
    k = 1.8
    def bx(x0, y0, z0, x1, y1, z1):
        return BP.box_m(x0 * k, y0 * k, z0 * k, x1 * k, y1 * k, z1 * k)
    ring = [bx(-0.015 + 0.012 * math.cos(a), -0.015 + 0.012 * math.sin(a), 0.0, -0.011 + 0.012 * math.cos(a), -0.011 + 0.012 * math.sin(a), 0.004)
            for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
    keys = [bx(0.0, -0.007, 0.0, 0.055, 0.007, 0.003), bx(0.04, -0.007, 0.0, 0.05, 0.012, 0.003),
            bx(-0.005, 0.01, 0.0, 0.045, 0.02, 0.003)]
    tag = [MK.panel((-0.075 * k, -0.035 * k, 0.0035 * k), (1, 0, 0), (0, 1, 0), 0.07 * k, 0.045 * k, uv=(0.0, 0.0, 0.5, 0.5))]
    tagb = [bx(-0.11, -0.0575, 0.0, -0.04, -0.0125, 0.003)]
    return MK.model([(0, tag + tagb), (1, ring + keys)], [bx(-0.11, -0.06, 0.0, 0.055, 0.025, 0.005)])


def _note():
    """a clipboard with a typed sheet, lying flat: origin on the surface"""
    import modelkit as MK, biprefabs as BP
    bx = BP.box_m
    board = [bx(-0.12, -0.165, 0.0, 0.12, 0.165, 0.006)]
    sheet = [MK.panel((0.0, -0.01, 0.0075), (1, 0, 0), (0, 1, 0), 0.21, 0.28, uv=(0.0, 0.5, 0.74, 1.0))]
    clip = [bx(-0.04, 0.135, 0.006, 0.04, 0.16, 0.016)]
    return MK.model([(0, sheet), (1, board), (2, clip)], [bx(-0.12, -0.165, 0.0, 0.12, 0.165, 0.016)])


def lib(L):
    if not (LOOT and MODELS):
        return
    import ssbay
    assert ssbay.BAY, 'ssloot: ss_key_1/ss_note_1 take the LOD slots of ss_chipa_1/ss_chipb_1, which only go with SS_BAY=1'
    L.texture('ss_loot', _tex)
    L.texture('ss_lootb', lambda: np.dstack([np.full((8, 8, 3), (0.38, 0.26, 0.15)), np.ones((8, 8))]))
    L.add('ss_key_1', _key, ['ss_loot', 'jr_steel'], lod_like='406_68_1')
    L.add('ss_note_1', _note, ['ss_loot', 'ss_lootb', 'ss_cpaint'], lod_like='406_68_1')   # (the clip in ss_cpaint: with ss_chipa_1 gone it is the only _SLIB user of that texture, and ss_mpan_1 in _VLIB reads it)


# ---------------------------------------------------------------- the layer
def apply(G):
    if not LOOT:
        return
    import atmos
    from mission_lib import lit
    m, T, nid, msg = G['m'], G['T'], G['nid'], G['msg']
    pick = G['PICK']
    atmos.ensure_decl(m, 'GenericPickup')
    n = 0
    # the key
    kx, ky, kz, kg = _w(*KEY_AT[:4], KEY_AT[4])
    if 'lootkeyarm' in G['DBG']:                          # (test only: the key on the lobby floor in front of the armoury, so one real-input run does key -> door -> reward)
        kx, ky, kz, kg = 75.4, 116.7, 0.31 + 0.012, 0.0
    key = nid()
    m.add_child(pick, T(key, 'GenericPickup', 'SS armoury key', kx * M, ky * M, kz * M, 0.0, 0.0, float(kg), KEY_MODEL))
    LOOK.append(('key', (kx, ky, kz)))
    got = 'GenericPickup_%d.isPickedUp' % key
    msg('SS_LOOT_KEY', 'SS loot: armoury key', got, KEY_LINE, 6.0)
    # the armoury doors: locked until the key is taken
    doors = []
    for dx, dy in ARM_DOORS:
        best = None
        for i_ in m.byid:
            t_ = m.byid[i_]
            try:
                if str(lit(t_.args[1])) != 'Door':
                    continue
                q = (float(lit(t_.args[3])) / M, float(lit(t_.args[4])) / M, float(lit(t_.args[5])) / M)
            except Exception:
                continue
            d_ = math.hypot(q[0] - dx, q[1] - dy) + abs(q[2] - 0.35)
            if d_ < 0.6 and (best is None or d_ < best[0]):
                best = (d_, i_)
        if best:
            m.set(best[1], 15, False)
            doors.append(best[1])
        else:
            print('ssloot: WARNING no door at (%.1f, %.1f)' % (dx, dy))
    assert len(doors) == 2, 'ssloot: the armoury needs both map doors 4025/4026, found %s' % doors
    src = m.byid.get(doors[0]) if doors else None
    if src is not None:                                    # (a pair of leaves in the north doorway, copies of the west door)
        import copy
        from mission_lib import v
        for hx, hy, g in NORTH_LEAVES:
            d_ = copy.deepcopy(src); i_ = nid(); d_.args[0] = v(i_); d_.args[2] = v('SS loot armoury north door')
            d_.args[3] = v(hx * M); d_.args[4] = v(hy * M); d_.args[11] = v(g)
            m.add_child(4029, d_)
            doors.append(i_)
    areas = []
    for k_, (hx, hy) in enumerate(ARM_HINT):
        a_ = nid()
        m.add_child(4029, T(a_, 'AreaActivate', 'SS loot: at the armoury door %d' % k_, hx * M, hy * M, (0.31 + 1.0) * M, 0.0, 0.0, 0.0,
                                  2.6 * M, 2.6 * M, 2.6 * M, 'CRITERIA_HUMAN0'))
        areas.append(a_)
    picked = ' || '.join('Door_%d.isPicked' % d_ for d_ in doors)   # (fix1120 L1)
    msg('SS_LOOT_LOCK', 'SS loot: armoury locked', '%s == 0 && !(%s) && (%s)' % (got, picked, ' || '.join('AreaActivate_%d.nActive == 1' % a_ for a_ in areas)), LOCK_LINE, 6.0)   # (one line for both doors: one task id, redo 11-13 id budget)
    # the lock (as the originals' scripted doors, L11-L36: lock argument the literal "1", opened only through the open expression):
    # Jones with the key at either door -> all four leaves open. An expression in the lock argument locks nothing (rig 11-13)
    opened = '%s == 1 && (%s)' % (got, ' || '.join('AreaActivate_%d.nActive == 1' % a_ for a_ in areas))
    for d_ in doors:
        m.set(d_, 15, True); m.set(d_, 17, PICK_S); m.set(d_, 18, '1'); m.set(d_, 19, opened); m.set(d_, 20, '0')   # (fix1120 L1: pickable with the literal '1' lock, as garrison door 1834; the open rule = the key, as before)   # (close rule '0': once open they stay open, Jones is never shut inside; as build_sandstorm rig wb15)
    cut_graph(G)
    # the reward on the armoury bench: ss-world's loose AK on that bench goes (orchestrator 11-13: the reward must be what Jones takes there)
    for i_ in [i_ for i_ in m.byid if str(lit(m.byid[i_].args[1])) == 'GunPickup' and str(lit(m.byid[i_].args[2])) == 'SS armoury bench rifle']:
        m.remove(i_)
        print('ssloot: armoury bench AK %d removed, the reward lies there' % i_)
    m.reindex()
    for nm, wid, x, y, z, a, b, g in REWARD:
        m.add_child(pick, T(nid(), 'GunPickup', 'SS ' + nm, x * M, y * M, (0.31 + z) * M + 60.0, a, b, g, wid, '')); n += 1
        LOOK.append((nm, (x, y, 0.31 + z)))
    # caches
    for nm, wid, bld, x, y, z, (a, b, g) in CACHES:
        wx, wy, wz, wg = _w(bld, x, y, z, 0.0)
        m.add_child(pick, T(nid(), 'GunPickup', 'SS cache ' + nm, wx * M, wy * M, wz * M + 60.0, a, b, g + wg if g else wg, wid, '')); n += 1
        LOOK.append((nm, (wx, wy, wz)))
    # readables: a paper you take, the line it says
    for k_, (nm, bld, x, y, z, yaw, text) in enumerate(NOTES):
        wx, wy, wz, wg = _w(bld, x, y, z, yaw)
        p_ = nid()
        m.add_child(pick, T(p_, 'GenericPickup', 'SS paper ' + nm, wx * M, wy * M, wz * M, 0.0, 0.0, float(wg), NOTE_MODEL))
        msg('SS_LOOT_N%d' % k_, 'SS loot: ' + nm, 'GenericPickup_%d.isPickedUp' % p_, text, 8.0)
        LOOK.append((nm, (wx, wy, wz)))
    print('ssloot: key %d at (%.1f, %.1f, %.2f) locks doors %s; %d pickups; %d papers; models %s %s' % (key, kx, ky, kz, doors, n, len(NOTES), KEY_MODEL, NOTE_MODEL))
    G['LOOT_KEY'] = key
    debug(G)


def cut_graph(G):
    """judge Q24 11-13: graph 1 linked the locked armoury through both doorways (11 links), a shortcut men could take through
    the shut leaves. Every link with one end inside the room is dropped and graph 1 written again: the armoury is a graph
    island (no men are in it). Node ids are kept (patrols and hunts refer to them)."""
    import graph as GR
    from navgen import check_graph
    m = G['m']
    nodes, edges = G['GRAPHS'][1], G['GEDGES'][1]
    pos = {n['id']: n['pos'] for n in nodes}
    def inside(i):
        x, y = pos[i][0] / M, pos[i][1] / M
        return 74.55 < x < 82.0 and 103.5 < y < 113.55
    cut = [(a, b) for a, b in edges if inside(a) != inside(b)]
    keep = [e for e in edges if e not in set(cut)]
    check_graph(nodes, keep)
    data, ne, mx = GR.write(nodes, keep, max_nodes=min(2000, ((len(nodes) + 99) // 100) * 100 + 100))
    m.graphs[1] = (data, None)
    G['GEDGES'][1] = keep
    m.set(1, 9, mx); m.set(1, 10, ne)
    print('ssloot: graph 1: %d links into the armoury cut %s, %d -> %d links' % (len(cut), cut, len(edges), ne))


LOOK = []                                                  # (every placed find, world m: the 'lootaudit' camera tour)


def debug(G):
    """test variants: 'lootkey' = Jones starts 1.6 m from the key, facing it; 'lootarm' = at the armoury's lobby door ('lootkeyarm': and the key on the lobby floor ahead);
    'lootc0'..'lootc3' = beside cache N"""
    DBG = G['DBG']
    if 'lootarm' in DBG:
        G['_put_jones']((79.0, 118.6, 0.31), (77.85, 114.0))      # (3.7 m from the test key: a pickup closer than ~2 m is taken at the spawn)
    if 'lootdbg' in DBG:                                   # (test: proves StatusMessages show on this rig, and when the key counts as taken)
        G['msg']('SS_LOOT_DBG0', 'SS loot debug start', 'LevelFlow_10.nTick > 3 * GAME_FREQUENCY', 'DEBUG LOOT: messages work', 8.0)
        G['msg']('SS_LOOT_DBG1', 'SS loot debug key', 'GenericPickup_%d.isPickedUp' % G['LOOT_KEY'], 'DEBUG LOOT: KEY PICKED UP', 30.0)
    if 'lootaudit' in DBG:                                 # (a camera on every find, 4 s each, two angles, from second 4: the 'intro' scenario films it)
        import cutscene as CS
        keys = []
        for nm, (x, y, z) in LOOK + [('north doors', (77.85, 113.6, 1.4)), ('west doors', (74.52, 105.8, 1.4))]:
            for ang in (0.6, 2.4):
                c = ((x + 1.1 * math.cos(ang)) * M, (y + 1.1 * math.sin(ang)) * M, (z + 0.75) * M)
                keys += [CS.key(c, (x * M, y * M, z * M), 3.0, True, fov=0.7), CS.key(c, (x * M, y * M, z * M), 0.0, False, fov=0.7)]
            print('ssloot: audit %s at (%.2f, %.2f, %.2f)' % (nm, x, y, z))
        CS.add_outro(G['m'], G['nid'], 4087, keys, [], 'LevelFlow_10.nTick > 4 * GAME_FREQUENCY')
    for k_, (nm, wid, bld, x, y, z, _r) in enumerate(CACHES):    # ('lootc0'..'lootc3': Jones 1.4 m from cache N, facing it)
        if 'lootc%d' % k_ in DBG:
            fz = 3.57 if bld == 'sc' else 0.0                  # (the camera room is on the security block's first floor)
            sx, sy, sz, _ = _w(bld, x + 1.4 if x < 0 else x - 1.4, y, fz)
            cx, cy, cz, _ = _w(bld, x, y, fz)
            G['_put_jones']((sx, sy, sz), (cx, cy))
    for k_, (nm, bld, x, y, z, yaw, _t) in enumerate(NOTES):     # ('lootn0'..'lootn2': Jones 1.4 m from paper N, facing it)
        if 'lootn%d' % k_ in DBG:
            sx, sy, sz, _ = _w(bld, x + 1.4 if x < 0 else x - 1.4, y, 0.0)
            cx, cy, cz, _ = _w(bld, x, y, 0.0)
            G['_put_jones']((sx, sy, sz), (cx, cy))
    if 'lootkey' in DBG and 'lootkeyarm' not in DBG:
        b, x, y = KEY_AT[0], KEY_AT[1], KEY_AT[2]
        sx, sy, sz, _ = _w(b, x - 1.3, y + 0.3, 0.0)
        kx, ky, kz, _ = _w(b, x, y, 0.0)
        G['_put_jones']((sx, sy, sz), (kx, ky))
