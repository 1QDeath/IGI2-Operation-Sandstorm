"""srgunship - Sirocco round 4 (owner 10-24): 'when I call the heli, no matter what and how many enemies are there, the heli
keeps killing them with its machine gun and lands - and it should have a machine gun on it'.

How (igi2-originals howto 2: no original lets an aircraft or AI kill AI - every aircraft kill is SCRIPTED):
- the IGI Black Hawk (710_01_1) carries two Minimi sentry guns (313_08_1, location1/level1) under its stub wings, barrels
  forward: plain EditRigidObj children (the originals hang EditRigidObj children on moving rigids: L24 3271 '106_03_1',
  L13 3111 '107_01_1'), on every copy (flying, waiting, outro);
- it flies a strafing run straight at the relay post (path A), stops in a HOVER facing it, and only then flies down onto
  the landing ground (path B: two guides on ONE helicopter, as Mission 16's 1102);
- while it fires: muzzle flashes (fire-sprite Smoke at each muzzle), tracers (fast fire-sprite Smoke toward the post), the
  engine's own .50 sound (COMMON 'm2hb_loop' on a SoundGenerator child, bursts), rotor loop 'helicopter_1' (COMMON);
- the kills: the ridge is cut into cells over its AI graph nodes; each cell has an invisible ExplodeObject (model 'none',
  no fragments, no fireballs, L32's pattern) that fires when an ALIVE ridge soldier stands in the cell
  (AreaActivate_IdInArea(cell, soldier), L21 1507) and Jones is NOT within the blast's safety box (a man
  who walks into a cell later fires it again); a dust burst where it hits. It lands when every ridge soldier is dead (or after
  max_hover s: a man standing next to Jones is never fired on).
"""
import math
import numpy as np
from mission_lib import T, v
from qast import lit, tasks
import atmos as AT

M = 4096.0
GF = 'GAME_FREQUENCY'
GUN_MODEL, GUN_SRC = '313_08_1', 'location1/level1'
GUNS = ((-2.15, 1.6, 0.15), (2.15, 1.6, 0.15))   # 710_01_1 frame (m): under the stub wings, inboard of the tanks; barrel +y
MUZZLE = (0.0, 1.42, 0.33)                       # (313_08_1 frame: the barrel tip, y 1.34 m)
# the kill blasts (10-25 runs bt2 / ft1 / gs6 / gs7 / gk4): an ExplodeObject's fireball grows with its FALLOFF radius and 0
# fragments + 0 fireballs = it never explodes; buried blasts did not kill (gs6 / gs7). The one that killed every ridge man (gk4):
# radius 7.5 m, falloff 4.5 m, damage x10, 1 fragment + 1 fireball, 1 m over the cell's floor - its fireball is the reason the
# kills hide behind the strafe cutscene (strafe_len; note 10-25)
BLAST_R = 7.5                                    # m
SAFE_R = BLAST_R + 2.5                           # m: no blast while Jones is inside this box around it (half size, at the floor)
LAYERS = 3                                       # blasts per cell (one per firing cycle)
CELL = 10.0                                      # (10-24: 7 m cells = 132 cells x 11 tasks ran the mission out of task ids)


def _loc(origin, yaw, local_m):
    c, s = math.cos(yaw), math.sin(yaw)
    x, y, z = (float(q) * M for q in local_m)
    return (float(origin[0]) + c * x - s * y, float(origin[1]) + s * x + c * y, float(origin[2]) + z)


def heading(a, b):
    """yaw (Gamma convention: 0 = +y, +pi/2 = -x) from a to b"""
    return math.atan2(-(b[0] - a[0]), b[1] - a[1])


def smoke(nid, name, pos, alpha, gamma, n, radius, rand, v0, v1, rgb, life, fade, sprite, size, dsize, intensity, gravity, gen,
          cutoff=600.0, move=False, mode=1):
    """a Smoke task (tasks.md order); gen = 'Generate factor' expression (emission rate)"""
    return T(nid(), 'Smoke', name, *[float(c) for c in pos], float(alpha), float(gamma), int(n), float(radius), float(rand), float(v0),
             float(v1), *AT._rgb(rgb), float(life), float(fade), int(mode), int(sprite), float(size), float(dsize), -1.0, 1.0,
             float(intensity), float(gravity), 0.0, gen, bool(move), float(cutoff), False, 0.0, 0.0)


class Gunship:
    def __init__(self, K, CINE):
        self.K, self.C, self.m = K, CINE, K.m
        for t in ('Smoke', 'ExplodeObject', 'AreaActivate', 'SoundGenerator', 'SequenceCommand', 'LevelTimer', 'EditVariable',
                  'ConditionalContainer', 'SplinePathDynCubeObj', 'SplinePathNodeQTask', 'SplinePathGuideQTask'):
            AT.ensure_decl(self.m, t)

    # ------------------------------------------------------------------ the guns (children of any 710_01_1 copy)
    def guns(self, origin, yaw, fire=None, aim=None, name='gun'):
        """the two mounted guns of a helicopter standing at origin/yaw (its task position) -> [child tasks]. fire = the
        'shooting now' expression (muzzle flashes + tracers), aim = (alpha, gamma) of the tracers (world)"""
        K = self.K
        out = []
        for k, g in enumerate(GUNS):
            p = _loc(origin, yaw, g)
            out.append(T(K.nid(), 'EditRigidObj', '%s %s %d' % (K.PFX, name, k + 1), *p, 0.0, 0.0, float(yaw), GUN_MODEL, 5, False, False))
            if fire:
                mz = _loc(origin, yaw, np.array(g) + np.array(MUZZLE))
                out.append(smoke(K.nid, '%s %s %d muzzle flash' % (K.PFX, name, k + 1), mz, math.pi / 2, yaw, 12, 0.03, 0.45, 1.0, 3.0,
                                 (2.0, 1.5, 0.7), 0.05, 0.04, 0, 0.55, 0.9, 1.0, 0.0, '45 * (%s)' % fire, cutoff=900.0))
                if aim:
                    out.append(smoke(K.nid, '%s %s %d tracers' % (K.PFX, name, k + 1), mz, aim[0], aim[1], 40, 0.0, 0.025, 760.0, 840.0,
                                     (2.0, 1.25, 0.45), 0.5, 0.05, 0, 0.45, 0.0, 1.0, 0.0, '14 * (%s)' % fire, cutoff=900.0))
                    # (Smoke velocity is ~0.1 m/s per unit: 85-95 flew ~9 m/s in game run gs3 - 760-840 = ~80 m/s)
        return out

    def rotor_sound(self, sound='helicopter_1'):
        """the originals' rotor loop on the helicopter itself (L16 1102 / L17 1103: SoundGenerator + one command)"""
        K = self.K
        return T(K.nid(), 'SoundGenerator', '', children=[
            T(K.nid(), 'SequenceCommand', '', '1', 'SoundGenerator_PlaySound("%s")' % sound, '1', 'SequenceCommand_SetCommand(-1)')])

    def gun_sound(self, burst):
        """the engine's own .50 loop while `burst` is true, its tail when it stops (K.siren's on/off pair)"""
        K = self.K
        a, b = K.nid(), K.nid()
        return T(K.nid(), 'SoundGenerator', '', children=[
            T(a, 'SequenceCommand', '', burst, 'SoundGenerator_PlaySound("m2hb_loop")', burst, 'SequenceCommand_SetCommand(%d)' % b),
            T(b, 'SequenceCommand', '', '!(%s)' % burst, 'SoundGenerator_StopSound(), SoundGenerator_PlaySound("m2hb_loop_e")',
              '!(%s)' % burst, 'SequenceCommand_SetCommand(%d)' % a)])

    # ------------------------------------------------------------------ the flight
    def build(self, pad, yaw, when, target, soldiers, spawned=(), nodes=(), extra_cells=(), hover_m=(45.0, 22.0), max_hover=30.0,
              name='gunship', gun_ai=None, kill_cells=True, strafe_len=None, strafe_kill_in_cs=True):
        """pad = landing ground (ground z, units), yaw = its landing yaw; when = flight start; target = the point it strafes
        (ground, units); soldiers = every HumanSoldier id it must kill; spawned = [(ids, 'they exist' expr)] for men in
        ConditionalContainers (an unspawned man counts as dead); nodes = AI graph node positions where men can stand (cells
        are cut over them); extra_cells = [(centre, (hx, hy, hz) half m, blast r m)] (tower platforms...).
        -> dict(tasks, landed, secs, timer, fire, window, land, dead, heli, hover, cells)"""
        K, C = self.K, self.C
        origin = np.array([float(pad[0]), float(pad[1]), float(pad[2]) + C.SKIDS_M * M])
        tgt = np.array([float(c) for c in target])
        # -- where it hovers: hover_m[0] m out from the target, hover_m[1] m up; the run comes in along the same line
        best = None
        for db in range(0, 360, 15):
            a_ = math.radians(db)
            u = np.array([math.cos(a_), math.sin(a_), 0.0])
            H = tgt + u * hover_m[0] * M + np.array([0, 0, hover_m[1] * M])
            mid = H + u * 95 * M + np.array([0, 0, 14 * M])
            far = H + u * 280 * M + np.array([0, 0, 55 * M])
            b1 = (H + origin) / 2 + np.array([0, 0, 8 * M])
            b2 = origin + np.array([0, 0, 6 * M])
            if any(K.blocked(p, q, pad=3 * M) for p, q in ((far, mid), (mid, H), (H, b1), (b1, b2), (b2, origin))):
                continue
            hz = float(K.TERR.height(H[0], H[1]))
            clear = H[2] - (hz if not np.isnan(hz) else -1e9)
            d_lz = math.dist(H[:2], origin[:2]) / M
            score = -abs(d_lz - 45.0) + 0.2 * min(clear / M, 40.0)        # (a short hop down to the pad; open air below)
            if best is None or score > best[0]:
                best = (score, db, u, H, mid, far, b1, b2)
        assert best, 'gunship: no clear strafing run toward the target'
        _, db, u, H, mid, far, b1, b2 = best
        gH = heading(H, tgt)                                  # (nose on the target for the whole run and the hover)
        gL = yaw + 2 * math.pi * round((gH - yaw) / (2 * math.pi))   # (turn the short way round to the landing yaw)
        aim_d = tgt + np.array([0, 0, 1.0 * M]) - H
        aim = (math.pi / 2 + math.atan2(-aim_d[2], math.hypot(aim_d[0], aim_d[1])), heading(H, tgt))   # (Smoke Alpha: 0 = up)
        hid = K.nid()
        # -- the state: window (fire allowed), hover clock, landing go, everybody dead
        dead_terms = ['HumanSoldier_%d.isDead' % s for s in soldiers if not any(s in ids for ids, _ in spawned)]
        for ids, ex in spawned:
            dead_terms.append('(!(%s) || (%s))' % (ex, ' && '.join('HumanSoldier_%d.isDead' % s for s in ids)))
        dead = '(%s)' % ' && '.join(dead_terms) if dead_terms else '1'
        win, hov_t, land, fire_t, burst_t = K.nid(), K.nid(), K.nid(), K.nid(), K.nid()
        spA, secsA = C.spline(hid, [tuple(p) for p in (far, mid, H)], [160.0, 90.0, 3.0], [gH] * 3, name='%s strafing run' % name)
        spB, secsB = C.spline(hid, [tuple(p) for p in (H, b1, b2, origin)], [3.0, 30.0, 12.0, 3.0], [gH, (gH + gL) / 2, gL, gL],
                              name='%s down onto the landing ground' % name)
        guides = [[t_ for t_, d_, p_ in tasks(sp_) if lit(t_.args[1]) == 'SplinePathGuideQTask'][0] for sp_ in (spA, spB)]
        gidA, gidB = (int(lit(g_.args[0])) for g_ in guides)
        for t_, d_, p_ in tasks(spA):                        # (path A starts with `when`, path B with the landing go)
            if lit(t_.args[1]) == 'SequenceCommand':
                t_.args[3] = v(when)
        go_land = 'EditVariable_%d.nValue == 1' % land
        for t_, d_, p_ in tasks(spB):
            if lit(t_.args[1]) == 'SequenceCommand':
                t_.args[3] = v(go_land)
        hovering = 'SplinePathGuideQTask_%d.vPosition > 1.97' % gidA
        window = 'EditVariable_%d.nValue == 1 && EditVariable_%d.nValue == 0' % (win, land)
        # strafe_len (note 10-25, option B): the kills happen behind a short strafe cutscene (L36 pattern) - when it
        # reaches the hover and anyone on the ridge is alive, `go` latches; every occupied cell fires within 0.3 s, the
        # cutscene (the caller's mid, trigger = cs_trigger) starts at 0.35 s; cs_run (an EditVariable the caller mirrors to
        # the cutscene's container) pauses the cells while it runs, keeps the guns firing, and holds the landing
        go, cs_run = K.nid(), K.nid()
        cs_on = 'EditVariable_%d.nValue == 1' % cs_run
        fire = ('%s && (!%s || %s)' % (window, dead, cs_on)) if strafe_len else '%s && !%s' % (window, dead)
        burst = '%s && LevelTimer_%d.nTick < 1.15 * %s' % (fire, burst_t, GF)
        landed_t = K.nid()
        landed = 'LevelTimer_%d.nTick > %.2f * %s' % (landed_t, secsB + 0.5, GF)
        logic = [
            T(win, 'EditVariable', '%s %s may fire' % (K.PFX, name), 0.0, 0.0, 0.0, 0,
              'EditVariable_%d.nValue == 0 && SplinePathGuideQTask_%d.vPosition > 0.85' % (win, gidA), ''),
            T(hov_t, 'LevelTimer', '%s %s hover clock' % (K.PFX, name), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, hovering, '', False),
            T(land, 'EditVariable', '%s %s lands now' % (K.PFX, name), 0.0, 0.0, 0.0, 0,
              ('EditVariable_%d.nValue == 0 && %s && ((%s && LevelTimer_%d.nTick > 2.5 * %s) || LevelTimer_%d.nTick > %.1f * %s)'
               % (land, hovering, dead, hov_t, GF, hov_t, max_hover, GF)) if not strafe_len else
              ('EditVariable_%d.nValue == 0 && %s && !(%s) && ((%s && (EditVariable_%d.nValue == 0 || LevelTimer_%d.nTick > %.1f * %s) && '
               'LevelTimer_%d.nTick > 2.5 * %s) || LevelTimer_%d.nTick > %.1f * %s)'
               % (land, hovering, cs_on, dead, go, fire_t, strafe_len + 1.0, GF, hov_t, GF, hov_t, max_hover + strafe_len, GF)), ''),
            T(fire_t, 'LevelTimer', '%s %s fire clock' % (K.PFX, name), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
              'EditVariable_%d.nValue == 1' % (go if strafe_len else win), '', False),
            T(burst_t, 'LevelTimer', '%s %s bursts' % (K.PFX, name), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, '1',
              'LevelTimer_%d.nTick > 1.7 * %s' % (burst_t, GF), True),
            T(landed_t, 'LevelTimer', '%s %s landing clock' % (K.PFX, name), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, go_land, '', False)]
        if strafe_len:
            logic += [T(go, 'EditVariable', '%s %s strafe go' % (K.PFX, name), 0.0, 0.0, 0.0, 0,
                        'EditVariable_%d.nValue == 0 && %s && !%s && EditVariable_%d.nValue == 0' % (go, hovering, dead, land), ''),
                      T(cs_run, 'EditVariable', '%s %s strafe cutscene running' % (K.PFX, name), 0.0, 0.0, 0.0, 0, '', '')]
        # -- the helicopter (exists while it flies; the waiting set takes over in its place when it has landed)
        kids = [T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_04_1', 0),
                T(K.nid(), 'RotateAttachment', '', 0.785398, 0.0, 0.0, '710_05_1', 0),
                C.pilot(tuple(far), gH, name='pilot (gunship)'), self.rotor_sound(), self.gun_sound(burst)]
        kids += self.guns(far, gH, fire=burst, aim=aim)
        if gun_ai:                                           # (test: the L17 Hind's own AI gun - does Team '0' make it shoot ENEMIES?)
            gp = _loc(far, gH, gun_ai.get('local', (0.0, 3.5, -1.8)))
            kids.append(T(K.nid(), 'AIStationaryGunHolder', '', *gp, 0.0, 0.0, float(gH), '720_05_1', 360.0, 360.0, 150.0,
                          gun_ai.get('on', window), gun_ai.get('team', '0'), '720_07_1', '', -180.0, 180.0, 360.0, 999999999, 90.0, 90.0,
                          1000.0, float(gun_ai.get('accuracy', 0.6)), 'WEAPON_ID_M2HB'))
        h = T(hid, 'EditRigidObj', '%s %s' % (K.PFX, name), *[float(c) for c in far], 0.0, 0.0, float(gH), '710_01_1', 8, False, False,
              children=kids)
        fly_cc = K.nid()
        out = logic + [T(fly_cc, 'ConditionalContainer', '%s %s (flying)' % (K.PFX, name), '(%s) && !(%s)' % (when, landed), '', '',
                         children=[h])] + spA + spB
        # -- the kill cells
        cells = self._cells(nodes, extra_cells)
        sweep_dir = -u[:2]                                     # (near cells first: the line of fire walks away from it)
        proj = [float(np.dot(np.array(c_[0][:2]) - tgt[:2], sweep_dir)) / M for c_ in cells]
        lo_, hi_ = (min(proj), max(proj)) if proj else (0.0, 1.0)
        alive = lambda aid: ' || '.join('(AreaActivate_IdInArea(%d, %d) && !HumanSoldier_%d.isDead)' % (aid, s, s) for s in soldiers)
        cc_kids = []
        self.cell_ids = []
        for k, ((cx, cy, cz), half, br, (bx, by, bz)) in enumerate(cells):
            aid, sid_ = K.nid(), K.nid()
            t0 = (0.4 + 4.0 * (proj[k] - lo_) / max(hi_ - lo_, 1e-6)) if not strafe_len else (0.15 + 0.3 * (proj[k] - lo_) / max(hi_ - lo_, 1e-6))
            sr = SAFE_R if br >= BLAST_R else br + 2.5
            floor_z = bz - 1.0 * M
            cc_kids += [T(aid, 'AreaActivate', '%s %s cell %d' % (K.PFX, name, k + 1), float(cx), float(cy), float(cz),
                          0.0, 0.0, 0.0, 2 * half[0] * M, 2 * half[1] * M, 2 * half[2] * M, 'CRITERIA_HUMAN1'),   # (enemies: L21 3268
                        #  'Enemy Priboi' + AreaActivate_IdInArea(3268, 422); with '' criteria no soldier is ever in it - run gk2)
                        T(sid_, 'AreaActivate', '%s %s cell %d safety' % (K.PFX, name, k + 1), float(bx), float(by), float(floor_z + 1.5 * M),
                          0.0, 0.0, 0.0, 2 * sr * M, 2 * sr * M, 9.0 * M, 'CRITERIA_HUMAN0')]   # (at the floor: from 3 m under it to 6 m over it)
            # (10-25 runs gk1-gk3: a 1116-char trigger never fired - the longest expression in any original is 949 chars: the
            #  live-soldier test is split over two toggles Oa / Ob, each well under that)
            half_ = (len(soldiers) + 1) // 2
            Oa, Ob = K.nid(), K.nid()
            occs = []
            for O_, grp_ in ((Oa, soldiers[:half_]), (Ob, soldiers[half_:])):
                if not grp_:
                    continue
                t_ = ' || '.join('(AreaActivate_IdInArea(%d, %d) && !HumanSoldier_%d.isDead)' % (aid, s_, s_) for s_ in grp_)
                cc_kids.append(T(O_, 'EditVariable', '%s %s cell %d men %s' % (K.PFX, name, k + 1, 'a' if O_ == Oa else 'b'), 0.0, 0.0,
                                 0.0, 0, 'EditVariable_%d.nValue == 0 && (%s)' % (O_, t_), 'EditVariable_%d.nValue == 1 && !(%s)' % (O_, t_)))
                occs.append('EditVariable_%d.nValue == 1' % O_)
            occ = ' || '.join(occs)
            # (10-24: no LevelTimer per cell - igi2.exe caps LevelTimers at 32 per mission (QTaskList 0x8368ba0, 0x20: 'Fatal
            #  error: QTaskList is full'), and ExplodeObjects share a 512-slot list with every Human, SCamera, Glass: so each cell
            #  is a tick counter V (up for 1 s after it fires, then P counts it back down: a 2 s cycle) and its blast + dust live
            #  in ConditionalContainers only while it fires - a man who walks into the cell later fires it again)
            # (10-25 run gs8: an EditVariable steps only when its expression BECOMES true - a 'count while < N' never counts;
            #  so V is a toggle: up when a live man is in the cell and it may fire, down when the cell is empty; C counts the
            #  ups and blast n fires on the n-th (an ExplodeObject fires once: run gs4); no smoke of its own - gk4's black puffs
            #  were the old 'dust' Smokes (colour <= 1 = black smoke in this engine))
            V, C_ = K.nid(), K.nid()
            ev, ec = 'EditVariable_%d.nValue' % V, 'EditVariable_%d.nValue' % C_
            safe = '!AreaActivate_%d.nActive' % sid_
            E_ = [K.nid() for _ in range(LAYERS)]
            # (10-25 run df1: a man who lived through his cell's first blast was never fired on again - V stayed up while he
            #  stood there. V now also drops once the current shot's blast has gone off, so a cell still holding a live man
            #  fires its next blast at once, up to LAYERS)
            spent = ' || '.join('(%s == %d && ExplodeObject_%d.isExploded)' % (ec, n_ + 1, E_[n_]) for n_ in range(LAYERS))
            cc_kids += [T(V, 'EditVariable', '%s %s cell %d firing' % (K.PFX, name, k + 1), 0.0, 0.0, 0.0, 0,
                          '%s == 0 && LevelTimer_%d.nTick > %.2f * %s && %s%s && (%s)'
                          % (ev, fire_t, t0, GF, safe, (' && !(%s)' % cs_on) if strafe_len and not strafe_kill_in_cs else '', occ),
                          '%s == 1 && (!(%s) || %s)' % (ev, occ, spent)),
                        T(C_, 'EditVariable', '%s %s cell %d shots' % (K.PFX, name, k + 1), 0.0, 0.0, 0.0, 0, '%s == 1' % ev, '')]
            self.cell_ids.append(dict(area=aid, safety=sid_, V=V, C=C_, E=[], box=((cx, cy, cz), half), blast=(bx, by, bz)))
            for layer in range(LAYERS):
                self.cell_ids[-1]['E'].append(E_[layer])
                cc_kids.append(T(self.cell_ids[-1]['E'][-1], 'ExplodeObject', '%s %s hit %d.%d' % (K.PFX, name, k + 1, layer + 1),
                                 float(bx), float(by), float(bz), 0.0, 0.0, 0.0, 'none', 'none', 100.0, float(br), float(br) * 0.6, 10.0,
                                 0.0, 1, 1, '%s == %d' % (ec, layer + 1), ''))
        cells_cc = K.nid()
        out.append(T(cells_cc, 'ConditionalContainer', '%s %s kill cells' % (K.PFX, name), window if kill_cells else '0', '', '',
                     children=cc_kids))
        self.info = dict(heli=hid, hover=tuple(float(c) for c in H), gH=gH, run_from_deg=db, far=tuple(float(c) for c in far),
                         secsA=secsA, secsB=secsB, cells=len(cells), aim=aim)
        if strafe_len:
            self.info.update(go=go, cs_run=cs_run, fire_t=fire_t)
        return dict(tasks=out, landed=landed, secs=secsA + secsB, timer=landed_t, fire=fire, burst=burst, window=window, land=go_land,
                    go=go if strafe_len else None, cs_run=cs_run if strafe_len else None, fire_t=fire_t,
                    cs_trigger=('EditVariable_%d.nValue == 1' % go) if strafe_len else None,
                    dead=dead, heli=hid, hover=tuple(float(c) for c in H), cells=cells, guides=(gidA, gidB), hover_clock=hov_t,
                    secsA=secsA, secsB=secsB, gH=gH)

    @staticmethod
    def _cells(nodes, extra):
        """CELL-m cells over the node positions: [((x, y, z) box centre units, (hx, hy, hz) half m, blast r m)]; a box runs from
        1.5 m under the cell's lowest node to 4.5 m over its highest (10-24: a median-centred box missed the relay hut's floor
        where the graph also has roof nodes). extra = [((x, y, floor z) units, half m, blast r m)]"""
        buckets = {}
        for p in nodes:
            k = (int(math.floor(p[0] / (CELL * M))), int(math.floor(p[1] / (CELL * M))))
            buckets.setdefault(k, []).append(tuple(float(c) for c in p))
        out = []
        for (i, j), ps in sorted(buckets.items()):
            P = np.array(ps)
            lo, hi = P[:, 2].min() - 1.5 * M, P[:, 2].max() + 4.5 * M
            blast = (float(P[:, 0].mean()), float(P[:, 1].mean()), float(P[:, 2].min() + 1.0 * M))   # (1 m over where its men stand:
            out.append((((i + 0.5) * CELL * M, (j + 0.5) * CELL * M, (lo + hi) / 2), (CELL / 2, CELL / 2, (hi - lo) / 2 / M), BLAST_R,
                        blast))                                                                    #  the nodes' centroid)
        for (x, y, z), half, br in extra:                    # (a tower platform: a small blast up there, r 3 m shows almost nothing)
            out.append(((x, y, z - 1.5 * M + half[2] * M), half, br, (x, y, z + 1.0 * M)))
        return out
