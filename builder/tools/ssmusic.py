"""ssmusic - Sandstorm's own score (work/sandstorm/music, composed for this mission) in place of the borrowed 24_music.
Same path as origsounds: mp3 in the mission's sounds folder, a DefineSound in group MUSIC, level-wide AmbientAreas with the music flag.
Surface and underground crossfade by height (zone); alarm, fight and finale switch by condition, where only the fade-in exists.
  ssmusic.areas(globals())   # BEFORE K.write, after ssamb.build_classic: turns ssamb's 24_music area into the 4 ss_* areas
                             # priority: finale (chip pulled) > fight (spotted, or the alarm up top) > underground > surface
  ssmusic.install(out)       # AFTER the sounds.qvm write, instead of origsounds.add_music(out, ..., '24_music')
"""
import os, re, shutil
import igiqvm
from mission_lib import T

HERE = os.path.dirname(os.path.abspath(__file__))
MP3 = os.path.join(HERE, '..', 'work', 'sandstorm', 'music', 'mp3')
TRACKS = ('ss_surface', 'ss_alarm', 'ss_below', 'ss_finale')
VOL = 1.0       # (rig 11-04: the engine plays a music bed at 0.64 x this, so 1.0 = -4 dB)
# DefineSound min / max distance. The engine plays a bed by distance from its AmbientArea's centre, however big the box: rig 11-04, same
# file, 200 m from the centre -11 dB, 48 m -2 dB (the originals' 20 / 1000). This far out the level is the same all over the map.
FLAT = (5000, 10000)
# the world under the score: DefineSound (volume, min, max) (owner 11-04 items 23, 25; measured with work/sandstorm/music/tools/mixgain.py)
WORLD = {'sandstorm_wind': (0.4,) + FLAT, 'sandstorm_gen': (0.5, 4, 50), 'industrial_02': (0.25, 1, 5)}
FADE_MUSIC = 2.0   # s, a track started by a condition (alarm, fight, finale) fades in; the one it replaces stops dead
# a walking crossfade by height, everywhere (shed stairs, sewer ladders). Rig 11-05: two mp3s can run at once, and past its box edge a bed
# fades over Falloff metres. The lowest outdoor ground is -7.4, the machine room -15.3, the sewer -20.6.
GROUND_Z, DEEP_Z, FALLOFF_M, ZONE_H = -7.6, -14.5, 6.0, 1000.0
FADE_BED = 3.0     # s, wind and other looping beds: going indoors or underground crossfades instead of cutting
FIGHT_HOLD_S = 20  # GAME_FREQUENCY seconds (rig: 12 ran about 7 real s) the fight music stays after the last sighting
# the zones, one place to repoint when the base moves. UNDERGROUND = (centre, FULL size) in metres, world axes (AreaActivate sizes are full extents: rig P4a, work/joyride/ORCH_NOTES.md). Not the builder's BELOW
# (that misses hall A); keep it under the surface and off the sewer (x < 100).
# Other triggers: areas(G, below_cond='AreaActivate_123.nActive', finale_cond='...', alarm_cond='...') overrides any of the three.
UNDERGROUND = ((192.5, 235.0, -48.0), (145.0, 120.0, 74.0))     # x 120-265, y 175-295, z -85..-11


FID = set()


def _last_area(m):
    return max((i for i in m.find('AmbientArea') if str(m.arg(i, 15)) == 'ss_below'))


def zone(m, i, z, up=True):
    """box from height z up (or down) over the whole map; past z the sound dies over FALLOFF_M. AmbientArea sizes are HALF extents"""
    m.set(i, 5, (z + (ZONE_H if up else -ZONE_H)) * 4096.0)
    m.set(i, 11, ZONE_H); m.set(i, 12, FALLOFF_M)


def indoor_var(m, K, nv):
    """EditVariable, 1 while Jones is under a roof on the surface (rig wd1: the wind stood at full level inside the admin hall). The rooms are the
    walkable floors with a ceiling over them in the map's own nav data, joined into boxes; AreaActivate sizes are FULL extents"""
    import numpy as np
    from scipy import ndimage
    F = nv.F
    ok = (F['z'] > -5.0 * 4096) & (F['ceil'] - F['z'] < 9.0 * 4096)
    x, y, z = F['x'][ok], F['y'][ok], F['z'][ok]
    c = 1.0 * 4096
    ix, iy = ((x - x.min()) / c).astype(int), ((y - y.min()) / c).astype(int)
    g = np.zeros((ix.max() + 1, iy.max() + 1), bool); g[ix, iy] = True
    lab, n = ndimage.label(ndimage.binary_closing(g, iterations=2))
    boxes = []
    for k in range(1, n + 1):
        q = lab[ix, iy] == k
        if q.sum() < 12:
            continue
        boxes.append((int(q.sum()), x[q].min(), x[q].max(), y[q].min(), y[q].max(), z[q].min(), z[q].max()))
    boxes = sorted(boxes, reverse=True)[:24]
    v, ids = fid(m), []
    for a_, x0, x1, y0, y1, z0, z1 in boxes:
        i = fid(m); ids.append(i)
        m.add_child(K.LOGIC, T(i, 'AreaActivate', 'SS indoors', float(x0 + x1) / 2, float(y0 + y1) / 2, float(z0 + z1) / 2 + 2.0 * 4096, 0.0, 0.0, 0.0,
                               float(x1 - x0) + 0.5 * 4096, float(y1 - y0) + 0.5 * 4096, float(z1 - z0) + 6.0 * 4096, 'CRITERIA_HUMAN0'))
    any_ = ' || '.join('AreaActivate_%d.nActive' % i for i in ids)
    m.add_child(K.LOGIC, T(v, 'EditVariable', 'SS indoors', 0.0, 0.0, 0.0, 0, 'EditVariable_%d.nValue == 0 && (%s)' % (v, any_), 'EditVariable_%d.nValue == 1 && !(%s)' % (v, any_)))
    print('music: %d indoor boxes for the wind: %s' % (len(ids), [(round(b_[1] / 4096), round(b_[3] / 4096), round((b_[2] - b_[1]) / 4096), round((b_[4] - b_[3]) / 4096)) for b_ in boxes]))
    return v


def fid(m):
    """a burned id: new_id's range is used up by dropped children (m.used), so these sit unused in no task; the builder never gets them back"""
    i = next(i for i in range(2753, 1601, -1) if i in m.used and i not in m.byid and i not in FID)
    FID.add(i)
    return i


def fight_var(m, K, armed, hold_s=FIGHT_HOLD_S):
    """EditVariable, 1 from a new sighting until hold_s after the last one. nSpotted only ever counts up (the stats screen) and is not 0 at the
    start (rig: the alarm track played on load), so two counters follow it: c counts, d catches up, silently until `armed`"""
    v, t, d, c = [fid(m) for _ in range(4)]
    new = 'EditVariable_%d.nValue > EditVariable_%d.nValue' % (c, d)
    m.add_child(K.LOGIC, T(v, 'EditVariable', 'SS music: fight', 0.0, 0.0, 0.0, 0, 'EditVariable_%d.nValue == 0 && %s && %s' % (v, new, armed),
                           'EditVariable_%d.nValue == 1 && !(%s) && LevelTimer_%d.nTick > %d * GAME_FREQUENCY' % (v, new, t, hold_s)))
    m.add_child(K.LOGIC, T(t, 'LevelTimer', 'SS music: fight over', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           'EditVariable_%d.nValue == 1' % v, '%s || EditVariable_%d.nValue == 0' % (new, v), False))
    m.add_child(K.LOGIC, T(d, 'EditVariable', 'SS music: sightings handled', 0.0, 0.0, 0.0, 0,
                           '%s && (EditVariable_%d.nValue == 1 || !(%s))' % (new, v, armed), ''))
    m.add_child(K.LOGIC, T(c, 'EditVariable', 'SS music: sightings', 0.0, 0.0, 0.0, 0, 'EditVariable_%d.nValue < HumanPlayer_0.nSpotted' % c, ''))
    return 'EditVariable_%d.nValue == 1' % v


def areas(G, fade=FADE_MUSIC, below_cond=None, finale_cond=None, alarm_cond='EditVariable_1500.nValue == 1'):
    m, K = G['m'], G['K']
    for i in m.find('AmbientArea'):                  # every looping bed fades, not only the music (random one-shots keep theirs)
        if not float(m.arg(i, 13)) and not float(m.arg(i, 14)):
            m.set(i, 19, max(float(m.arg(i, 19)), FADE_BED))
    if below_cond is None:                           # the default zone: UNDERGROUND
        (cx, cy, cz), (hx, hy, hz) = UNDERGROUND
        bx = K.nid()
        m.add_child(K.LOGIC, T(bx, 'AreaActivate', 'SS music: Jones underground', cx * 4096, cy * 4096, cz * 4096, 0.0, 0.0, 0.0,
                               hx * 4096, hy * 4096, hz * 4096, 'CRITERIA_HUMAN0'))
        below_cond = 'AreaActivate_%d.nActive' % bx
    below = '(%s)' % below_cond
    alarm = alarm_cond
    chip = '(%s)' % (finale_cond or G['CHIPPED'])
    mus = [i for i in m.find('AmbientArea') if str(m.arg(i, 15)) == '24_music']
    assert len(mus) == 1, mus
    base = m.arg(mus[0], 18)                         # NOT_CS + 'a few seconds after control'
    fight = fight_var(m, K, 'LevelTimer_%d.nTick > 5 * GAME_FREQUENCY' % G['CSI']['after'])
    hot = '(%s || (%s && !%s))' % (fight, alarm, below)       # a fight anywhere; the base alarm only up on the surface
    calm = '%s && !%s && !%s' % (base, chip, hot)    # surface and below both run when calm: their boxes crossfade them by height
    conds = {'ss_surface': calm, 'ss_alarm': '%s && !%s && %s' % (base, chip, hot), 'ss_below': calm,
             'ss_finale': '%s && %s' % (base, chip)}
    if os.environ.get('SSMUSIC_TEST') == 'off':      # rig check: the world alone
        conds = dict.fromkeys(TRACKS, '0')
    elif os.environ.get('SSMUSIC_TEST'):             # rig check: each track 20 s in turn
        tick = 'LevelTimer_%d.nTick' % G['CSI']['after']
        conds = {n: '%s > %d * GAME_FREQUENCY && %s <= %d * GAME_FREQUENCY' % (tick, 5 + i * 20, tick, 5 + (i + 1) * 20) for i, n in enumerate(TRACKS)}
    par_id = K.LOGIC
    pos =[float(m.arg(mus[0], i)) for i in (3, 4, 5)]
    m.set(mus[0], 15, 'ss_surface'); m.set(mus[0], 18, conds['ss_surface']); m.set(mus[0], 19, float(fade))
    zone(m, mus[0], GROUND_Z)
    indoors = indoor_var(m, K, G['nv'])
    for i in m.find('AmbientArea'):                  # the storm stays above ground the same way, not by a switch
        if str(m.arg(i, 15)) in ('sandstorm_wind', 'wind_1') and float(m.arg(i, 9)) > 1000:
            zone(m, i, GROUND_Z)
            m.set(i, 18, '%s && EditVariable_%d.nValue == 0' % (G['NOT_CS'], indoors))
    for name in TRACKS[1:]:
        m.add_child(par_id, T(fid(m), 'AmbientArea', '%s music %s' % (K.PFX, name), *pos, 0.0, 0.0, 0.0, 10000.0, 10000.0, 10000.0,
                              10.0, 0.0, 0.0, name, True, True, conds[name], float(fade), True, 0.0))
        if name == 'ss_below':
            zone(m, _last_area(m), DEEP_Z, up=False)
    print('music: 4 own tracks, areas switch on alarm / below / chip')


def install(out):
    p = os.path.join(out, 'sounds', 'sounds.qvm')
    ver, sst = igiqvm.decompile(open(p, 'rb').read())
    lines = []
    for n in TRACKS:
        shutil.copy2(os.path.join(MP3, n + '.mp3'), os.path.join(out, 'sounds', n + '.mp3'))
        lines.append('DefineSound("%s", "%s", 0, 0, 0, %s, %d, %d, -1, -1, -1, -1, TRUE)' % ((n, n, VOL) + FLAT))
    qsc = igiqvm.stmts_to_qsc(sst)
    for n, (v, lo, hi) in WORLD.items():
        qsc, k = re.subn(r'(DefineSound\("%s", "%s", 0, 0, 0, )[\d.e+-]+, [\d.e+-]+, [\d.e+-]+' % (n, n), lambda h: '%s%s, %d, %d' % (h.group(1), v, lo, hi), qsc)
        assert k == 1, n
    qsc += '\nDefineGroup(\n    "MUSIC",\n    %s\n);\n' % ',\n    '.join(lines)
    open(p, 'wb').write(igiqvm.compile_stmts(igiqvm.parse_qsc(qsc), ver))
    print('music: %s' % ', '.join(TRACKS))
