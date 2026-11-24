"""ssboom - owner 96 + 111 (11-08 playtest): explosive barrels, fuel tanks and small drums next to the airbase's soldier groups, behind
SS_BOOM=1 (default 0 until proven). Shoot one and it blows up and kills the men beside it.

What the engine really has (checked 11-08, evidence in work/sandstorm/boom/README.md):
- The originals' shootable objects are plain ExplodeObjects with an EMPTY 'Explosion expression' (they go off on damage alone).
  Recipes copied 1:1 from the decompiled levels (work/originals, eo dump of all 19 SP levels + the MP maps):
    barrel     333_01_1 -> 342_02_1   damage scale 1.5, radius 2, falloff 1.5, damage 1, delay 0.2, 2-3 fragments/fireballs, explo_03_l
               (location2/LEVEL5: 23 on sandbags, location3 L4/L5/L1: 25 more)
    fuel tank  406_50_1 -> 460_36_1   damage scale 10, radius 2-40, falloff 1.5-5.5, damage 1-70, delay 1, explo_04_xl
               (the Sandstorm MP map itself ships five: 3892, 3893, 3486, 3897, 3898 - kept by the builder, burn out via K.burn_out)
    jerry can  360_24_1 -> 360_25_1   damage scale 2, radius 2, falloff 1.5, damage 1, delay 1, explo_01_s   (location3/level1)
  The originals' radius 2 m barely leaves a 3.4 x 7.5 m tank's own hull: nobody next to one dies. New barrels / jerry cans keep the
  originals' models, health, delay, fragments and sounds, radius 3 / 2.5 m, damage 3 / 2 (rig-tuned: the men 2-2.6 m away die, Jones
  10 m away is untouched); the MP tanks keep the map's own numbers and simply go off in the chain (raising them hurt Jones at 12.6 m).
- Placement rule (owner 96): fuel depot, guard posts, trucks - each cluster within ~2.5 m of a group's spawn spots and at
  least SAFE_M from every waypoint of the real-input walk route (work/qa/route_sandstorm_full6.txt) and the sewer ladder tops,
  so an enemy round meant for Jones cannot set off a barrel beside him. The build prints both distances per cluster.
  NOT at the generators: A and B are objectives the player stands at (every route passes 5.4 m from generator A's yard).
- Caps: ExplodeObjects are not EditRigidObj and no release rule names them (0 new symbols), no Humans added; LOD rows +4 at most
  (333_01_1, 342_02_1, 360_24_1, 360_25_1; ssrooms may already add two of them).

Owner 111 (blood): nothing to build - the engine already draws a blood pool under every body (bloodpool.tex, Blood option ON in
config.qvm), it stays (rig 11-08: 75-90 s seen), bodies never vanish, and guards who find a body react through FRIENDLYDETECTION
(ssgarr.eyes + sstalk man-down barks: "No no no, get up! Get up, brother!"). A script-placed pool is impossible (no decal task, no
runtime position call). Evidence: work/sandstorm/boom/README.md.

Debug words (SS_DEBUG, test builds only):
  boomtest=<cluster>   Jones on open ground ~12 m from that cluster, facing it, and DEBUG messages for each of its objects going off and
                       for each man within 6 m of it dying ('DEBUG: BOOM <obj>', 'DEBUG: DEAD <man>'); prints the DBG_AIM line for dbgrun aim
  boomdist=<m>         the distance for boomtest (default 12);  boomat=x,y  force Jones's spot (sight checks become warnings)
  bloodtest=<squad key>/<k> [blooddist=<m>]   Jones facing that man, 'DEBUG: SHOT MAN <id> DEAD' / 'DEBUG: ALARM ON' (SS_BOOM off too)
  unarmed=<m>          men within m metres carry no gun - TEST ONLY: 887-3387 first-chance AVs at igi2.exe+0x3bf6a (bm6, bl3, bl4)
"""
import math, os

BOOM = os.environ.get('SS_BOOM', '1') == '1'                 # (on since rc7d, sandstorm-redo)
M = 4096.0
SAFE_M = 8.0                       # (clusters must stay this far from the walk route / ladder tops)

# kind -> (model, destroyed, damage scale (health), radius m, falloff m, damage, delay s, fragments, fireballs, sound)
KINDS = {
    'barrel': ('333_01_1', '342_02_1', 1.5, 3.0, 2.0, 3.0, 0.2, 3, 3, 'explo_03_l'),
    'barrel2': ('333_02_1', '342_02_1', 1.5, 3.0, 2.0, 3.0, 0.2, 3, 3, 'explo_03_l'),   # (the ochre-rust drum with the grey lid, location1/level1; 33 in the originals)
    'jerry':  ('360_24_1', '360_25_1', 2.0, 2.5, 1.5, 2.0, 0.4, 3, 2, 'explo_01_s'),
}
# Tuned on the rig 11-08 (work/sandstorm/boom/README.md): bm6 radius 4 / falloff 6 / damage 30 barrels + MP tanks raised to 6 / 9 / 50 killed Jones
# 10.1 m away; bm7 2.5 / 2.0 / 30 + tanks 3.5 / 2.5 / 50 took 2/3 of his health; bm8 3 / 2 / 3 + tanks 4.5 / 1.5 / 5 still about half (the
# red flash came with the tanks' 1 s delay); bm9 the same barrels with the MP tanks at the map's own numbers: both guards dead, Jones untouched.
# So the MP tanks are NOT changed (they still go off in the chain) and the damage stays near the originals' (barrel 1); the radius covers the men.
REACH_MAX = 6.0
assert all(v[3] + v[4] <= REACH_MAX for v in KINDS.values())
SOURCES = {'location2/LEVEL5': ['333_01_1', '342_02_1'], 'location1/level1': ['333_02_1'], 'location3/level1': ['360_24_1', '360_25_1']}

# cluster: name, the squad it serves, MP tanks beside it (unchanged, they go off in the chain), new objects (kind, x, y, yaw) in world metres
CLUSTERS = [
    ('yard', 'N sewer exit yard', (3893, 3892),                 # guard post at the sewer exit; chain into the yard's two MP tanks
     [('barrel', 99.3, 195.0, 0.0), ('barrel2', 99.5, 196.0, 0.7), ('barrel', 100.3, 195.5, 1.9)]),
    ('depot', 'N east pad and fuel depot', (3897, 3898),       # the east pad's fuel depot: a drum in the gap between its two MP tanks by the
     [('barrel', 219.1, 203.2, 0.4),                            #  1st man (the tanks lie side by side, he stands between them), drums by the 2nd
      ('barrel', 208.6, 189.3, 0.0), ('barrel2', 209.4, 189.9, 1.1), ('jerry', 208.9, 190.6, 0.4)]),
    ('pad', 'N north pad guards', (),                           # fuel drums for the north pad's Hind
     [('barrel', 155.6, 255.2, 0.0), ('barrel2', 156.4, 255.8, 1.2), ('barrel', 155.3, 256.1, 2.3)]),   # (8.6-9.5 m from Hind 3901, whose charge blast is 5 + 3 m: it may still set them off - fuel by the chopper; not tested)
    ('mouth', 'N tunnel mouth', (),                             # guard post at the north tunnel mouth
     [('barrel', 132.0, 315.6, 0.0), ('barrel2', 132.9, 316.1, 0.9), ('jerry', 131.3, 316.3, 1.6)]),
]
# NOT at generators A / B: both are objectives the player must stand at (every walk route passes 5.4 m from generator A's yard)
LADDERS = [(93.2, 205.9), (73.2, 131.7)]                        # sewer shaft tops (Building 3907, 3956)


def models(g):
    """before X.finish: merge the barrel and jerry can models of the originals"""
    if not BOOM:
        return
    for rel, names in SOURCES.items():
        g['X'].models(rel, names)


def _route_pts(here):
    import re
    p = os.path.join(here, 'work', 'sandstorm', 'boom', 'route_check.txt')   # (a copy of work/qa/route_sandstorm_full6.txt: work/qa never reaches the build nodes)
    if not os.path.exists(p):
        return []
    out = []
    for tok in open(p).read().split(';'):
        mt = re.match(r'\s*(-?\d+),(-?\d+)', tok)
        if mt:
            out.append((int(mt.group(1)) / M, int(mt.group(2)) / M))
    return out


def _seg_d(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.hypot(p[0] - a[0] - t * ax, p[1] - a[1] - t * ay)


def apply(g):
    """after every squad is placed, before the builder's debug loop: the clusters and the boomtest words"""
    blood_debug(g)
    if not BOOM:
        return
    m, T, nid, K, SQ = g['m'], g['T'], g['nid'], g['K'], g['SQUAD_IDS']
    from qast import lit
    DBG = g.get('DEBUG', '') or ''
    route = _route_pts(g['HERE'])
    surf_route = [p for p in route]                           # (the walk's underground legs lie far from every cluster anyway)
    tank_par = lit(m.parent[3893].args[0])
    made = {}                                                  # cluster -> [(id, kind, (x, y, z))]
    for name, key, tanks, items in CLUSTERS:
        men = [tuple(float(m.arg(h, k)) / M for k in (3, 4, 5)) for h in SQ.get(key, (0, []))[1] if h in m.byid]
        made[name] = []
        for tid in tanks:                                     # (blast numbers untouched: bm9 raising them hurt Jones at 12.6 m; their FIRE is capped below)
            if tid not in m.byid or m.typ(tid) != 'ExplodeObject':
                print('ssboom: WARN tank %d missing' % tid); continue
            made[name].append((tid, 'tank', tuple(float(m.arg(tid, k)) / M for k in (3, 4, 5))))
            _tame_fire(m, tid)
        for kind, x, y, yaw in items:
            mdl, dst, hp, rad, fall, dmg, dly, frg, fb, snd = KINDS[kind]
            z = float(K.TERR.height(x * M, y * M)) / M
            if men:                                         # (terrain z; the builder's men can stand ~0.9 m high, seatcheck is the proof)
                zm = min(men, key=lambda p_: math.hypot(p_[0] - x, p_[1] - y))[2]
                if z != z:
                    z = zm
                if abs(z - zm) > 0.8:
                    print('ssboom: note %s %s at (%.1f, %.1f): terrain z %.2f, nearest man at %.2f' % (name, kind, x, y, z, zm))
            i = nid()
            m.add_child(tank_par, T(i, 'ExplodeObject', 'SS boom %s %s' % (name, kind), x * M, y * M, z * M, 0.0, 0.0, float(yaw),
                                    mdl, dst, float(hp), float(rad), float(fall), float(dmg), float(dly), int(frg), int(fb), '', snd))
            made[name].append((i, kind, (x, y, z)))
        objs = [p for i, k, p in made[name]]
        cx, cy = sum(p[0] for p in objs) / len(objs), sum(p[1] for p in objs) / len(objs)
        dmen = [min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in [p for i, k, p in made[name] if k != 'tank']) for q in men]
        assert surf_route or 'boomnear' in DBG, 'ssboom: route file work/sandstorm/boom/route_check.txt missing: the safety check cannot run'
        new = [p for i, k, p in made[name] if k != 'tank']
        droute = min([_seg_d((p[0], p[1]), a, b) for p in new for a, b in zip(surf_route, surf_route[1:])] or [float('inf')])   # (PC check 11-08: yard 9.8, depot 18.6, pad 12.6, mouth 65.5 m)
        close = [round(min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in men), 2) for p in new if men]
        assert not close or min(close) > 0.8, ('ssboom: a man spawns inside a %s object' % name, close)    # (review 11-08: squads are placed by a spot search, barrels are fixed)
        if not men or min(min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in new) for q in men) > 4.0:
            print('ssboom: WARN %s: no man within 4 m of its objects (squad moved?) - nobody dies there' % name)
        dlad = min(math.hypot(p[0] - lx, p[1] - ly) for p in new for lx, ly in LADDERS)
        flag = '' if min(droute, dlad) >= SAFE_M else '  <-- TOO NEAR THE ROUTE'
        print('ssboom: %-5s %d objects at (%.1f, %.1f): men %s m, route %.1f m, ladder %.1f m%s' % (
            name, len(objs), cx, cy, [round(d_, 1) for d_ in dmen], droute, dlad, flag))
        assert not flag or 'boomnear' in DBG, ('ssboom: cluster %s within %.1f m of the walk route' % (name, min(droute, dlad)))
    g['BOOM_MADE'] = made
    print('ssboom: %d new explosive objects beside %d MP tanks (unchanged)' % (
        sum(1 for v_ in made.values() for i, k, p in v_ if k != 'tank'), sum(1 for v_ in made.values() for i, k, p in v_ if k == 'tank')))
    _debug(g, made, DBG)


def _unarmed(g, centre):
    """test word 'unarmed=<m>': men within m metres of centre carry no gun (bm5r, bl2r: Jones was shot dead right after his first burst,
    so nothing was filmed after it). Their AI, eyes and alarm are untouched"""
    m, SQ = g['m'], g['SQUAD_IDS']
    r = next((float(p[8:]) for p in (g.get('DEBUG', '') or '').split(';') if p.startswith('unarmed=')), 0.0)
    n = 0
    for key, (sid, hids) in SQ.items():
        for h in hids:
            if h in m.byid and math.hypot(float(m.arg(h, 3)) / M - centre[0], float(m.arg(h, 4)) / M - centre[1]) < r:
                m.set(h, 9, ''); n += 1                    # (HumanSoldier: 3-5 pos, 6 gamma, 7 model, 8 team, 9 weapon; as the builder's 'unarmedlift')
    if r:
        print('debug: unarmed: %d men within %.0f m carry no gun' % (n, r))


def blood_debug(g):
    """'bloodtest=<squad key>/<k>' (works with SS_BOOM off too): Jones on open ground ~14 m from that man, facing him; DEBUG messages
    when he dies and when the surface alarm (EditVariable_1500) goes on; prints the DBG_AIM line (chest height)"""
    m, K, msg, SQ = g['m'], g['K'], g['msg'], g['SQUAD_IDS']
    import numpy as np
    for p in [p for p in (g.get('DEBUG', '') or '').split(';') if p.startswith('bloodtest=')]:
        key, k = p[10:].rsplit('/', 1)
        h = SQ[key][1][int(k)]
        hx, hy, hz = (float(m.arg(h, j)) / M for j in (3, 4, 5))
        best = None
        bd = next((float(q[10:]) for q in (g.get('DEBUG', '') or '').split(';') if q.startswith('blooddist=')), None)
        for dist in ((bd, bd + 1.0, bd + 2.0) if bd else (14.0, 11.0, 17.0)):
            for b in range(0, 360, 10):
                sx, sy = hx + math.sin(math.radians(b)) * dist, hy + math.cos(math.radians(b)) * dist
                sz = float(K.TERR.height(sx * M, sy * M)) / M
                if sz != sz or abs(sz - hz) > 1.5:
                    continue
                if K.blocked(np.array([sx * M, sy * M, (sz + 1.6) * M]), np.array([hx * M, hy * M, (hz + 1.2) * M])):
                    continue
                best = (sx, sy, sz); break
            if best:
                break
        assert best, ('bloodtest: no clear spot round man', h)
        g['_put_jones'](best, (hx, hy))
        _unarmed(g, (hx, hy))
        gam = math.atan2(-(hx - best[0]), hy - best[1])
        msg('SS_DBG_BD', 'DEBUG blood man dead', 'HumanSoldier_%d.isDead' % h, 'DEBUG: SHOT MAN %d DEAD' % h, 30.0)
        msg('SS_DBG_BA', 'DEBUG alarm on', 'EditVariable_1500.nValue == 1', 'DEBUG: ALARM ON', 30.0)
        print('debug: bloodtest man %d (%s/%s) at (%.1f, %.1f, %.1f); DBG_AIM=%d,%d,%d,40,1.2 DBG_AIM_HEAD=%.4f' % (
            h, key, k, hx, hy, hz, hx * M, hy * M, (hz + 1.25) * M, gam))


FIRE_S, SMOKE_S = 18, 50                                     # (K.burn_out gave these MP tanks 50 s of flames and 110 s of smoke)


def _tame_fire(m, tid):
    """judge A01 (11-08, real rig footage jb1): a barrel chained into the yard tanks; their MP flames (2 emitters a tank, 100 particles growing
    to ~3 m, flying up to 3 m/s, 0.5 damage/s each) whited out the screen for ~30 s and burned Jones to death ~20 s later at ~5 m from the
    emitters. For the tanks beside our drums only: flames 18 s, smoke 50 s, slower smaller flame particles (they stay at the tank). The
    flames still hurt whoever stands in them (damage per second and radius unchanged). Smoke args: 8 particles, 11/12 velocity,
    21 size delta, 27 generate expression ('<n> * (LevelTimer_<t>.nTick < <s> * GAME_FREQUENCY)'), 30 damage flag"""
    import re
    from qast import lit
    from mission_lib import v
    n = 0
    for cc, t in list(m.byid.items()):
        if m.typ(cc) != 'ConditionalContainer' or str(lit(t.args[3])).strip() != 'ExplodeObject_%d.isExploded' % tid:
            continue
        for c in m.children(cc):
            if lit(c.args[1]) != 'Smoke':
                continue
            fire = str(lit(c.args[30])).upper() == 'TRUE'
            g = str(lit(c.args[27]))
            g2 = re.sub(r'< *\d+ \* GAME_FREQUENCY', '< %d * GAME_FREQUENCY' % (FIRE_S if fire else SMOKE_S), g)
            assert g2 != g or not g, ('ssboom: tank %d Smoke %s generate expression not understood' % (tid, lit(c.args[0])), g)
            c.args[27] = v(g2)
            if fire:
                c.args[8] = v(70)
                c.args[11] = v(0.8); c.args[12] = v(1.5)
                c.args[21] = v(1.2)
            else:
                c.args[8] = v(250)
            n += 1
    print('ssboom: tank %d fire capped (%d emitters: flames %d s, smoke %d s)' % (tid, n, FIRE_S, SMOKE_S))


def relight(g, out):
    """after ssworld.relight (the overlay is in <out>): rc7d showed the barrels as flat salmon boxes - the texture drawn about 1.8 x bright,
    no shading. ssworld bakes '<id>_0000_<lod>.olm' for every lightmapped object, but an ExplodeObject reads '<id>a_<node>_<lod>.olm'
    (location2/LEVEL5: barrels 3556 / 3359 carry only 3556a_0000_1..3.olm; all 69 'a' lightmaps there belong to ExplodeObjects), so the
    engine found none and drew its blank doubled default. Copy each new object's bake to the 'a' name (the plain one stays, harmless)."""
    if not BOOM:
        return
    import prefab
    path = os.path.join(out, 'overlay', 'lightmaps', 'lightmaps.res')
    if not os.path.exists(path):
        print('ssboom: WARN no lightmaps.res - barrels stay unlit'); return
    R = prefab.Res(path)
    n, miss = 0, []
    for name, items in (g.get('BOOM_MADE') or {}).items():
        for i, kind, p in items:
            if kind == 'tank':                                 # (the MP tanks are not ours and read fine)
                continue
            got = 0
            for lod in range(1, 6):
                src, dst = 'LOCAL:lightmaps/%04d_0000_%d.olm' % (i, lod), 'LOCAL:lightmaps/%04da_0000_%d.olm' % (i, lod)
                if R.has(src) and not R.has(dst):
                    R.add(dst, R.get(src)); got += 1
            n += got
            if not got:
                miss.append(i)
    open(path, 'wb').write(R.data())
    print('ssboom: %d lightmaps copied to the ExplodeObject names%s' % (n, ', NO bake for %s (SS_WORLD off?)' % miss if miss else ''))


def _debug(g, made, DBG):
    m, K, msg, SQ = g['m'], g['K'], g['msg'], g['SQUAD_IDS']
    parts = [p for p in DBG.split(';') if p]
    dist = next((float(p[9:]) for p in parts if p.startswith('boomdist=')), 12.0)
    for p in parts:
        if not p.startswith('boomtest='):
            continue
        name = p[9:]
        objs = made[name]
        cx = sum(q[2][0] for q in objs) / len(objs); cy = sum(q[2][1] for q in objs) / len(objs); cz = sum(q[2][2] for q in objs) / len(objs)
        key = next(k for n, k, t, it in CLUSTERS if n == name)
        import numpy as np
        men = [tuple(float(m.arg(h, k)) / M for k in (3, 4, 5)) for h in SQ[key][1] if h in m.byid]
        best = None
        at = next(([float(c) for c in q[7:].split(',')] for q in parts if q.startswith('boomat=')), None)

        def under_terrain(sx, sy, sz, tx, ty, tz):             # (bm2r: K.blocked does not see the terrain; Jones faced a slope)
            for f in [k / 20.0 for k in range(1, 20)]:
                x_, y_, z_ = sx + (tx - sx) * f, sy + (ty - sy) * f, (sz + 1.6) + (tz - sz - 1.6) * f
                h_ = float(K.TERR.height(x_ * M, y_ * M)) / M
                if h_ == h_ and h_ > z_ - 0.1:
                    return True
            return False
        for b in range(0, 360, 10):                            # open ground, clear sight AND a clear line of fire past the men (bm1r: a man stood in it)
            sx, sy = cx + math.sin(math.radians(b)) * dist, cy + math.cos(math.radians(b)) * dist
            if at:
                sx, sy = at
            sz = float(K.TERR.height(sx * M, sy * M)) / M
            if (sz != sz or abs(sz - cz) > 2.5) and not at:
                continue
            for tq in sorted([q for q in objs if q[1] != 'tank'], key=lambda q: math.hypot(q[2][0] - sx, q[2][1] - sy)):
                tx, ty, tz = tq[2]
                if min([_seg_d(p_[:2], (sx, sy), (tx, ty)) for p_ in men] or [9.0]) < 1.3:
                    continue
                if K.blocked(np.array([sx * M, sy * M, (sz + 1.6) * M]), np.array([tx * M, ty * M, (tz + 0.45) * M])) or under_terrain(sx, sy, sz, tx, ty, tz + 0.45):
                    if not at:
                        continue
                    print('debug: boomat: WARN sight check fails for target %d (taken anyway)' % tq[0])
                if best is None or abs(sz - cz) < abs(best[2] - cz):
                    best = (sx, sy, sz, b, tq)
                break
        assert best, ('boomtest: no clear spot round', name)
        sx, sy, sz, b, tgt = best
        g['_put_jones']((sx, sy, sz), (tgt[2][0], tgt[2][1]))
        _unarmed(g, (cx, cy))
        gam = math.atan2(-(tgt[2][0] - sx), tgt[2][1] - sy)
        print('debug: boomtest %s: Jones %.1f m away; DBG_AIM=%d,%d,%d,40,2.5 DBG_AIM_HEAD=%.4f (target %d %s)' % (
            name, math.hypot(cx - sx, cy - sy), tgt[2][0] * M, tgt[2][1] * M, (tgt[2][2] + 0.45) * M, gam, tgt[0], tgt[1]))
        for i, k, q in objs:
            msg('SS_DBG_B%d' % i, 'DEBUG boom %d' % i, 'ExplodeObject_%d.isExploded' % i, 'DEBUG: BOOM %s %d' % (k, i), 30.0)
        for h in [h for key2, (sid, hids) in SQ.items() for h in hids if h in m.byid]:
            hp = tuple(float(m.arg(h, k)) / M for k in (3, 4, 5))
            if math.hypot(hp[0] - cx, hp[1] - cy) < 6.0 and abs(hp[2] - cz) < 3.0:
                msg('SS_DBG_D%d' % h, 'DEBUG dead %d' % h, 'HumanSoldier_%d.isDead' % h, 'DEBUG: DEAD %d (%.1f m)' % (h, math.hypot(hp[0] - cx, hp[1] - cy)), 30.0)
                print('debug: boomtest watches man %d at %.1f m' % (h, math.hypot(hp[0] - cx, hp[1] - cy)))
