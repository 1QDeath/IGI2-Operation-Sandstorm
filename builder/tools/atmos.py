"""Atmosphere, weather, light and cinematic-camera helpers for IGI 2 missions built with tools/mission_lib.Mission.

Research and evidence: work/research/atmos/atmos.md (same folder).  Every preset value below names the original task it
was copied from.  Things marked GUESS are not in any original level and have not been tested in-game.

Typical use in a builder (after `m = Mission(...)` and `nid = lambda: m.new_id(lo, hi)`):

    sys.path.insert(0, os.path.join(HERE, 'work', 'research', 'atmos'))
    import atmos_recipe as AT
    AT.apply_preset(m, 'night')                       # in-game keyframes, sun/moon, sky dome, stars, clouds, wind
    AT.rain(m, nid, MISSION_CONTAINER, 'storm')       # RainEffect (declaration imported automatically)
    keys = AT.cctv_keys(cam_pos, gate_pos, 6.0, tint='green')     # "we hacked their camera" shot
    ids = AT.add_shot_chain(m, nid, PARENT, [dict(keys=keys, vhf=1.0, noise_loop=True), dict(keys=AT.zoom(...))])

Keyframe dicts are a superset of tools/cutscene.key(): tools/cutscene.add_intro() accepts them too (it ignores the extra
fields 'tod', 'roll', 'target_id', 'link_id'); use cutscene_task()/add_shot_chain() here to honour them.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))           # lives in tools/ (copied from work/research/atmos 10-10)
TOOLS = os.path.join(ROOT, 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import numpy as np                      # noqa: E402
from igiqvm import Call, Ident          # noqa: E402
from mission_lib import T, v, GAME      # noqa: E402
from qast import lit, load              # noqa: E402
import cutscene as CS                   # noqa: E402

M = 4096.0                                          # world units per metre
GF = 'GAME_FREQUENCY'
NONE, LINE, BAND = 'CAMERAFILTER_TYPE_NONE', 'CAMERAFILTER_TYPE_LINE', 'CAMERAFILTER_TYPE_BAND'
BAND_UPDATE, HANDICAM = 'CAMERAFILTER_TYPE_BAND_UPDATE', 'CAMERAFILTER_TYPE_HANDICAM'
DECOMP = os.path.join(ROOT, 'work', 'decomp')
CS_TIME_MIN = 1000.0                                # originals keep cutscene-only light keyframes at Time >= 1000

# where to copy a task declaration from when the base level does not declare it
DECL_SOURCE = {
    'RainEffect': 'location1_level3', 'FlatSkyKeyframe': 'location1_level3', 'OverlayHolder': 'location3_level2',
    'CutScene': 'location1_level1', 'EditCamera': 'location1_level1', 'Smoke': 'location1_level1',
    'LevelTimer': 'location1_level1', 'SequenceCommand': 'location1_level1', 'AmbientArea': 'location1_level1',
    'GlobalLightKeyframe': 'location1_level1', 'DirlightKeyframe': 'location1_level1', 'StatusMessage': 'location1_level1',
    'ConditionalContainer': 'location1_level1', 'EditVariable': 'location1_level1', 'BirdFlock': 'location1_LEVEL7',
    'EditBoneObj': 'location1_level1', 'GenericPickup': 'location2_LEVEL5',
    'PatrolPath': 'location1_level1', 'PatrolPathCommand': 'location1_level1', 'EditRigidObj': 'location1_level1',
    'RotateAttachment': 'location1_level1', 'SplinePathDynCubeObj': 'location1_level1', 'SplinePathNodeQTask': 'location1_level1',
    'SplinePathGuideQTask': 'location1_level1', 'ExplodeObject': 'location1_level1',
    'MissionTimer': 'location2_level1',
    'Ladder': 'location2_LEVEL2', 'DiscardTask': 'location1_level1', 'Lift': 'location1_level2', 'Floor': 'location1_level2',
    'Switch': 'location1_level2', 'Door': 'location1_level2', 'GenericTBA': 'location1_level2', 'SCamera': 'location1_level2',
    'AlarmControl': 'location1_level2',
}


# =============================================================================================== small utilities
def ensure_decl(m, typ):
    """import Task_DeclareParameters(typ) from an original level that declares it (Mission.import_decls)"""
    have = {lit(s.args[0]) for s in m.stmts if isinstance(s, Call) and s.name == 'Task_DeclareParameters'}
    if typ in have:
        return False
    src = os.path.join(DECOMP, '%s_objects.qsc' % DECL_SOURCE[typ])
    got = m.import_decls(src, [typ])
    assert got == [typ], (typ, got)
    return True


def _rgb(x):
    return tuple(float(c) for c in x)


def _setrgb(m, tid, idx, rgb):
    for k, c in enumerate(_rgb(rgb)):
        m.set(tid, idx + k, c)


def _getrgb(m, tid, idx):
    return tuple(float(m.arg(tid, idx + k)) for k in range(3))


def _clone(task, new_id, name=None):
    a = list(task.args)
    a[0] = v(new_id)
    if name is not None:
        a[2] = v(name)
    return Call('Task_New', [x for x in a if not (isinstance(x, Call) and x.name == 'Task_New')])


# =============================================================================================== environment lookup
# argument indexes (Task_New positions; RGB = 3 slots) - see atmos.md section 1
GLK_CAT = [4 + 8 * c for c in range(5)]             # GlobalLightKeyframe: terrain + object categories 1-4: amb(3) fog(3) density link
GLK_SKY, GLK_WATER_AMB, GLK_WATER_COL, GLK_TIME = 44, 47, 50, 53
DLK_BETA, DLK_GAMMA, DLK_FRONT, DLK_BACK, DLK_TIME = 3, 4, 5, 8, 11
FSK_TOP, FSK_TIME = 3, 18                           # FlatSkyKeyframe: top, mid1, mid2, bot1, bot2 (3 each), Time
SKY_FOG_AMOUNT, SKY_ZPOS, SKY_DIST, SKY_FOG_COL, SKY_SNAP, SKY_ANGLE, SKY_DOME = 3, 4, 5, 6, 9, 10, 11
LAYER_TEX, LAYER_SCALE, LAYER_XS, LAYER_YS, LAYER_ALPHA, LAYER_COL = 3, 4, 5, 6, 7, 8
GL_TEXF_AMB, GL_TEXF_SCALE, GL_TEXF_GAMMA = 8, 11, 14
DIRLIGHT_TEX, DIRLIGHT_SIZE, DIRLIGHT_SHADOW = 8, 9, 7
FLARE_DIR, FLARE_COL = 3, 6
WIND_ARGS = 3                                       # main freq, gust freq, main amp, gust amp, constant, lo clamp, hi clamp, phase, direction
LEVELFLOW, LF_START_TIME = 10, 9


def _made(m):
    """ids of keyframes this module added (transition / flash / cutscene looks) - never treated as the base look"""
    if not hasattr(m, '_atmos_made'):
        m._atmos_made = set()
    return m._atmos_made


def env(m):
    """ids of the environment tasks of the base level.  'ingame_*' = the level's own keyframes with Time < 1000
    (gameplay light), sorted by Time (the first one is the look the level starts with); keyframes added by this module
    are excluded.  'cs_*' = cutscene-only keyframes (Time >= 1000, selected by EditCamera 'Time of day')."""
    e = {k: [] for k in ('GlobalLight', 'GlobalLightKeyframe', 'Dirlight', 'DirlightKeyframe', 'FlatSky', 'FlatSkyLayer',
                         'FlatSkyKeyframe', 'Lensflare', 'Wind', 'RainEffect')}
    for i, t in m.byid.items():
        ty = lit(t.args[1])
        if ty in e:
            e[ty].append(i)
    for k in e:
        e[k].sort()
    made = _made(m)
    tg = lambda i: float(m.arg(i, GLK_TIME))
    td = lambda i: float(m.arg(i, DLK_TIME))
    e['ingame_glk'] = sorted([i for i in e['GlobalLightKeyframe'] if tg(i) < CS_TIME_MIN and i not in made], key=lambda i: (tg(i), i))
    e['ingame_dlk'] = sorted([i for i in e['DirlightKeyframe'] if td(i) < CS_TIME_MIN and i not in made], key=lambda i: (td(i), i))
    e['cs_glk'] = [i for i in e['GlobalLightKeyframe'] if tg(i) >= CS_TIME_MIN]
    e['cs_dlk'] = [i for i in e['DirlightKeyframe'] if td(i) >= CS_TIME_MIN]
    times = [tg(i) for i in e['ingame_glk']] + [td(i) for i in e['ingame_dlk']]
    e['t0'] = min(times) if times else 0.0          # SP levels: 12, multiplayer maps: 0
    e['all_times'] = sorted(set([tg(i) for i in e['GlobalLightKeyframe']] + [td(i) for i in e['DirlightKeyframe']] +
                                [float(m.arg(i, FSK_TIME)) for i in e['FlatSkyKeyframe']]))
    return e


def describe(m):
    """print the base level's atmosphere (debug aid)"""
    e = env(m)
    for i in e['GlobalLightKeyframe']:
        print('GLK %d %-22r T=%-9g amb=%s fog=%s dens=%s sky=%s' % (i, m.arg(i, 2), m.arg(i, GLK_TIME), _getrgb(m, i, 4),
                                                                  _getrgb(m, i, 7), m.arg(i, 10), _getrgb(m, i, GLK_SKY)))
    for i in e['DirlightKeyframe']:
        print('DLK %d %-22r T=%-9g beta=%s gamma=%s front=%s back=%s' % (i, m.arg(i, 2), m.arg(i, DLK_TIME), m.arg(i, 3),
                                                                       m.arg(i, 4), _getrgb(m, i, 5), _getrgb(m, i, 8)))
    for i in e['Dirlight']:
        print('Dirlight %d texture=%r size=%s shadow=%s' % (i, m.arg(i, 8), m.arg(i, 9), m.arg(i, 7)))
    for i in e['FlatSky']:
        print('FlatSky %d fog amount=%s z=%s dist=%s fogcol=%s dome=%s' % (i, m.arg(i, 3), m.arg(i, 4), m.arg(i, 5), _getrgb(m, i, 6),
                                                                         [_getrgb(m, i, SKY_DOME + 3 * k) for k in range(5)]))
    for i in e['FlatSkyLayer']:
        print('Layer %d %r scale=%s speed=(%s,%s) alpha=%s col=%s' % (i, m.arg(i, 3), m.arg(i, 4), m.arg(i, 5), m.arg(i, 6),
                                                                    m.arg(i, 7), _getrgb(m, i, 8)))
    for i in e['Wind'] + e['RainEffect'] + e['Lensflare']:
        print(m.typ(i), i, [lit(a) for a in m.task(i).args[3:]])
    print('in-game time', e['t0'], '| LevelFlow start time', m.arg(LEVELFLOW, LF_START_TIME) if LEVELFLOW in m.byid else None)


# =============================================================================================== sun / moon direction
def sun_angles(elev_deg, compass_deg):
    """(Beta, Gamma) for a DirlightKeyframe with the sun/moon `elev_deg` above the horizon in compass direction
    `compass_deg` (0 = north = +y, 90 = east = +x).  Derived from 3 originals where the Lensflare 'Direction' (unit vector
    towards the sun) and the DirlightKeyframe agree: L15 (3867 / 4090), L17 (3968 / 4090), L35 (2474 / 4091):
        e = pi - beta, a = pi - gamma, dir = (cos e cos a, cos e sin a, sin e)"""
    e = math.radians(elev_deg)
    a = math.radians(90.0 - compass_deg)
    return math.pi - e, math.pi - a


def sun_direction(beta, gamma):
    e, a = math.pi - beta, math.pi - gamma
    return (math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e))


# =============================================================================================== presets
# Values are copied from the in-game keyframes of original levels (task ids in 'src'); see atmos.md section 2.
# amb/fog/dens = GlobalLightKeyframe (all 5 categories), front/back = DirlightKeyframe, sky = FlatSky dome
# (top, mid1, mid2, bot1, bot2), sky_fog = (amount, colour), moon = Dirlight sun/moon texture, size, shadow intensity.
PRESETS = {
    'clear_day': dict(
        src='L24 location2/LEVEL4: GLK 4090, DLK 4088, FlatSky 4094, layer 4092, Lensflare 3712',
        amb=(0.30, 0.31, 0.33), fog=(0.577, 0.692, 0.865), dens=0.65,
        front=(1.13, 0.962, 0.788), back=(0.0, 0.0, 0.0),
        sky=[(0.3269, 0.4231, 0.6538), (0.5385, 0.6538, 0.8077), (0.5385, 0.6538, 0.8077), (0.7308, 0.7885, 0.8269), (0.7308, 0.7885, 0.8269)],
        sky_fog=(0.3, (0.7, 0.7, 0.7)), clouds=dict(alpha=0.123, color=(1, 1, 1)), stars=0.0,
        moon=('sun.tex', 32.0, 0.25), flare=(1.135, 0.9615, 0.7885), wind=(1.1, 0.2, 0.02, 0.6, 0.2)),
    'dusk': dict(
        src='L33 location3/level3 (sunset): GLK 4093, DLK 4091, FlatSky 4090, layer 4089, Lensflare 2239',
        amb=(0.472, 0.462, 0.432), fog=(0.577, 0.442, 0.423), dens=0.45,
        front=(1.1, 0.673, 0.327), back=(0.0, 0.0, 0.0),
        sky=[(0.5385, 0.4038, 0.3462), (1.0, 0.7115, 0.4615), (0.3654, 0.3462, 0.3269), (0.8462, 0.3846, 0.25), (0.5192, 0.4038, 0.3269)],
        sky_fog=(0.0, (0.7692, 0.6731, 0.6923)), clouds=dict(alpha=0.4417, color=(0.5769, 0.0, 0.03846)), stars=0.0,
        moon=('sun.tex', 32.0, 0.25), flare=(1.096, 0.6731, 0.3269), wind=(0.3, 0.1, 0.2, 1.5, 0.0)),
    'night': dict(
        src='L11 location1/level1 (night, moon + stars): GLK 4003, DLK 3349, Dirlight 4002, FlatSky 4001, layers 4000/3507, GlobalLight 4004',
        amb=(0.057692, 0.1, 0.18), fog=(0.0, 0.162308, 0.286923), dens=0.85,
        front=(0.096154, 0.153846, 0.25), back=(0.027692, 0.045385, 0.075385),
        sky=[(0.038462, 0.134615, 0.210769), (0.153077, 0.248462, 0.354615), (0.019231, 0.134615, 0.192308),
             (0.076923, 0.153846, 0.25), (0.057692, 0.076923, 0.134615)],
        sky_fog=(0.5, (0.0, 0.0, 0.0)), clouds=dict(alpha=0.2, color=(0.173077, 0.269231, 0.365385)),
        stars=1.0, stars_color=(0.711538, 0.711538, 0.788462),
        moon=('moon.tex', 64.0, 0.25), flare=(0.0, 0.0, 0.0), wind=(0.2, 0.2, 0.5, 0.2, 0.1),
        texfilter=((0.0, 0.0, 0.0), (0.95, 0.95, 0.95), 0.675)),       # opt-in (apply_preset(..., texfilter=True)), see atmos.md 2.6
    'moonlit': dict(
        src='MP chinesetemple (night, bright moon): GLK 4078, DLK 4088, Dirlight 4089, FlatSky 4094, layers 4008/4090, Lensflare 4086',
        amb=(0.096, 0.134, 0.23), fog=(0.0, 0.076, 0.153), dens=0.025,
        amb_obj=(0.0, 0.0385, 0.115), fog_obj=(0.0, 0.0, 0.0), dens_obj=0.1,
        front=(0.289, 0.321, 0.424), back=(0.0, 0.0, 0.0),
        sky=[(0.03692, 0.05461, 0.15), (0.2308, 0.3077, 0.4231), (0.09615, 0.09615, 0.1923), (0.3654, 0.3654, 0.3462), (0.0, 0.0, 0.0)],
        sky_fog=(0.0, (0.53, 0.57, 0.51)), clouds=dict(alpha=0.325, color=(0.3462, 0.25, 0.3846)), stars=0.325, stars_color=(1, 1, 1),
        moon=('moon.tex', 64.0, 0.65), flare=(0.2885, 0.3205, 0.4238), wind=(0.3, 0.01, 0.3, 0.5, 0.0)),
    'snowstorm': dict(
        src='build_whiteout.py section 8 (pre-dawn blizzard, shipped + run in-game 10-09) from L13 "In Game (snowing)" GLK 4003',
        amb=(0.13, 0.15, 0.22), fog=(0.30, 0.34, 0.42), dens=3.0,
        front=(0.20, 0.22, 0.28), back=(0.05, 0.06, 0.09),
        sky=[(0.16, 0.18, 0.23), (0.27, 0.30, 0.36), (0.22, 0.25, 0.30), (0.30, 0.34, 0.42), (0.28, 0.32, 0.39)],
        sky_fog=(0.9, (0.30, 0.34, 0.42)), sky_dist=300.0,
        clouds=dict(alpha=0.85, color=(0.40, 0.43, 0.50), speed=(0.0008, 0.0012)), stars=0.0,
        moon=('', None, None), flare=(0.0, 0.0, 0.0), wind=(0.8, 1.0, 0.9, 0.6, 0.35),
        weather=('snow', 'blizzard')),
    'whiteout': dict(
        src='L13 location1/level3 GLK 4003 "In Game (snowing)" (fog density 10) + FlatSkyKeyframe 4045',
        amb=(0.115385, 0.173077, 0.306923), fog=(0.346154, 0.423077, 0.519231), dens=10.0,
        front=(0.6, 0.6, 0.58), back=(0.0, 0.019231, 0.076923),
        sky=[(0.269231, 0.307692, 0.326923), (0.307692, 0.365385, 0.384615), (0.326923, 0.423077, 0.5),
             (0.615385, 0.615385, 0.615385), (0.365385, 0.423077, 0.519231)],
        stars=0.0, flare=(0.0, 0.0, 0.0), wind=(1.3, 0.9, 0.12, 0.45, 0.0), weather=('snow', 'heavy')),
    'snow_day': dict(
        src='GUESS: daytime overcast snow, L13 snowing fog colour brightened; no original',
        amb=(0.45, 0.47, 0.52), fog=(0.62, 0.65, 0.70), dens=2.5,
        front=(0.45, 0.47, 0.52), back=(0.10, 0.11, 0.13),
        sky=[(0.45, 0.47, 0.50), (0.62, 0.64, 0.67), (0.58, 0.60, 0.64), (0.66, 0.68, 0.71), (0.62, 0.65, 0.70)],
        sky_fog=(0.9, (0.62, 0.65, 0.70)), clouds=dict(alpha=0.8, color=(0.7, 0.72, 0.75), speed=(0.0006, 0.0009)), stars=0.0,
        moon=('', None, None), flare=(0.0, 0.0, 0.0), wind=(0.8, 1.0, 0.9, 0.6, 0.35), weather=('snow', 'heavy')),
    'rain': dict(
        src='L16 location1/LEVEL6 (overcast, rain after 20 s): GLK 4092, DLK 4090, FlatSky 3850, layer 3705, RainEffect 3084, Wind 3662',
        amb=(0.423, 0.404, 0.423), fog=(0.465, 0.504, 0.6), dens=0.63,
        front=(0.865, 0.942, 0.962), back=(0.0, 0.0192, 0.0769),
        sky=[(0.4423, 0.4615, 0.4808), (0.6346, 0.6538, 0.6923), (0.3654, 0.3846, 0.4423), (0.6538, 0.6538, 0.6838), (0.4231, 0.4423, 0.5)],
        sky_fog=(0.145, (0.0, 0.0, 0.0)), clouds=dict(alpha=0.3, color=(0.5385, 0.5962, 0.6538)), stars=0.0,
        moon=('sun.tex', 32.0, 0.25), flare=(0.0, 0.0, 0.0), wind=(0.9, 0.1, 0.1, 0.05, 0.1), weather=('rain', 'normal')),
    'thunderstorm': dict(
        src='GUESS: L16 rain preset with the sun dimmed to 50 % and denser fog; no original has a dark storm',
        amb=(0.30, 0.30, 0.33), fog=(0.35, 0.38, 0.45), dens=1.2,
        front=(0.43, 0.47, 0.48), back=(0.0, 0.02, 0.06),
        sky=[(0.25, 0.26, 0.28), (0.38, 0.40, 0.43), (0.22, 0.23, 0.27), (0.40, 0.40, 0.42), (0.26, 0.27, 0.30)],
        sky_fog=(0.5, (0.35, 0.38, 0.45)), clouds=dict(alpha=0.8, color=(0.35, 0.37, 0.40), speed=(0.0004, 0.0006)), stars=0.0,
        moon=('', None, None), flare=(0.0, 0.0, 0.0), wind=(0.9, 0.6, 0.5, 0.8, 0.3), weather=('rain', 'storm')),
    'fog': dict(
        src='MP forestraid (thick fog + rain): GLK 4090, DLK 4088, FlatSky 4094, layer 4093',
        amb=(0.222, 0.239, 0.29), fog=(0.404, 0.442, 0.481), dens=7.0,
        front=(0.86, 0.88, 0.9), back=(0.0, 0.0, 0.0),
        sky=[(0.3077, 0.3462, 0.3654), (0.4231, 0.4615, 0.5), (0.4231, 0.4423, 0.4423), (0.5192, 0.5577, 0.4615), (0.4231, 0.4808, 0.4808)],
        sky_fog=(1.0, (0.6154, 0.6538, 0.7885)), clouds=dict(alpha=1.0, color=(0.5192, 0.5, 0.5577)), stars=0.0,
        moon=('sun.tex', 32.0, 0.15), flare=(0.0, 0.0, 0.0), wind=(0.6, 0.1, 0.5, 0.8, 0.0)),
    'dust': dict(
        src='build_sandstorm.py section 2 (sandstorm at dusk, shipped + run in-game 10-10) on MP sandstorm GLK 4090 / DLK 4088 / FlatSky 4094',
        amb=(0.42, 0.33, 0.24), fog=(0.70, 0.52, 0.32), dens=2.6,
        front=(0.78, 0.58, 0.38), back=(0.18, 0.13, 0.09),
        sky=[(0.40, 0.30, 0.21), (0.62, 0.47, 0.31), (0.66, 0.50, 0.33), (0.70, 0.53, 0.34), (0.68, 0.51, 0.33)],
        sky_fog=(None, (0.70, 0.52, 0.32)), clouds=dict(color=(0.65, 0.62, 0.47), speed=(0.0003, 0.0009)), stars=0.0,
        flare=(0.0, 0.0, 0.0), wind=(0.9, 0.35, 0.8, 0.9, 0.4), weather=('dust', 'storm')),
}


def _is_star_layer(m, i):
    tex = str(m.arg(i, LAYER_TEX)).lower()
    return 'star' in tex


def set_light(m, kf_ids, amb=None, fog=None, dens=None, amb_obj=None, fog_obj=None, dens_obj=None, sky_color=None):
    """GlobalLightKeyframe(s): terrain + 4 object categories (all set alike unless *_obj given for categories 1-4)"""
    for i in kf_ids:
        for c, base in enumerate(GLK_CAT):
            a, f, d = (amb, fog, dens) if c == 0 else (amb_obj or amb, fog_obj or fog, dens if dens_obj is None else dens_obj)
            if a is not None:
                _setrgb(m, i, base, a)
            if f is not None:
                _setrgb(m, i, base + 3, f)
            if d is not None:
                m.set(i, base + 6, float(d))
        if sky_color is not None:
            _setrgb(m, i, GLK_SKY, sky_color)


def set_sun(m, kf_ids, front=None, back=None, elev_deg=None, compass_deg=None):
    """DirlightKeyframe(s).  Keep the angles (default) so the light matches the baked lightmap shadows."""
    for i in kf_ids:
        if front is not None:
            _setrgb(m, i, DLK_FRONT, front)
        if back is not None:
            _setrgb(m, i, DLK_BACK, back)
        if elev_deg is not None:
            b, g = sun_angles(elev_deg, compass_deg)
            m.set(i, DLK_BETA, round(b, 6))
            m.set(i, DLK_GAMMA, round(g, 6))


def set_sky(m, dome=None, fog_amount=None, fog_color=None, distance=None):
    for i in env(m)['FlatSky']:
        if dome is not None:
            for k, c in enumerate(dome):
                _setrgb(m, i, SKY_DOME + 3 * k, c)
            m.set(i, SKY_SNAP, False)
        if fog_amount is not None:
            m.set(i, SKY_FOG_AMOUNT, float(fog_amount))
        if fog_color is not None:
            _setrgb(m, i, SKY_FOG_COL, fog_color)
        if distance is not None:
            m.set(i, SKY_DIST, float(distance))


def set_layers(m, clouds=None, stars=None, stars_color=None):
    """clouds = dict(alpha, color, speed=(x, y)); stars = alpha of layers whose texture name contains 'star'.
    A star layer can only be shown if the base level has one (L11 k_stars2.tga, L13 / chinesetemple starmap_01.tga,
    L26 stars01.tex): textures are loose files in the mission folder - see atmos.md 2.5."""
    for i in env(m)['FlatSkyLayer']:
        if _is_star_layer(m, i):
            if stars is not None:
                m.set(i, LAYER_ALPHA, float(stars))
            if stars_color is not None:
                _setrgb(m, i, LAYER_COL, stars_color)
        elif clouds:
            if clouds.get('alpha') is not None:
                m.set(i, LAYER_ALPHA, float(clouds['alpha']))
            if clouds.get('color') is not None:
                _setrgb(m, i, LAYER_COL, clouds['color'])
            if clouds.get('speed') is not None:
                m.set(i, LAYER_XS, float(clouds['speed'][0]))
                m.set(i, LAYER_YS, float(clouds['speed'][1]))


def set_wind(m, main_freq, gust_freq, main_amp, gust_amp, constant):
    """Wind = vegetation sway (trees/forests); originals 0.2..1.3 / 0.01..1.0 / 0.002..1 / 0.05..1.5 / 0..0.35"""
    for i in env(m)['Wind']:
        for k, val in enumerate((main_freq, gust_freq, main_amp, gust_amp, constant)):
            m.set(i, WIND_ARGS + k, float(val))


def set_moon(m, texture, size=None, shadow=None):
    """Dirlight 'Sun/Moon Texture': 'sun.tex', 'moon.tex' (COMMON textures.res, available on every map) or '' (none)"""
    for i in env(m)['Dirlight']:
        m.set(i, DIRLIGHT_TEX, texture)
        if size is not None:
            m.set(i, DIRLIGHT_SIZE, float(size))
        if shadow is not None:
            m.set(i, DIRLIGHT_SHADOW, float(shadow))


def set_lensflare(m, color=None, direction=None):
    for i in env(m)['Lensflare']:
        if color is not None:
            _setrgb(m, i, FLARE_COL, color)
        if direction is not None:
            _setrgb(m, i, FLARE_DIR, direction)


def set_texture_filter(m, ambient=(0, 0, 0), scale=(1, 1, 1), gamma=1.0):
    """GlobalLight 'Texture filter': copied once after load into the renderer's global texture filter (igi2.exe 0x5f3f50),
    i.e. it recolours every texture of the level.  Night levels L11/L13 use scale 0.95, gamma 0.675.  How strongly it
    darkens a day map's baked lightmaps is UNCONFIRMED - test in-game before relying on it."""
    for i in env(m)['GlobalLight']:
        _setrgb(m, i, GL_TEXF_AMB, ambient)
        _setrgb(m, i, GL_TEXF_SCALE, scale)
        m.set(i, GL_TEXF_GAMMA, float(gamma))


def apply_preset(m, name, keyframes=None, sun=None, texfilter=False, wind=True):
    """Give the whole level the look of PRESETS[name] by editing its in-game light keyframes (Time < 1000), the
    sun/moon, sky dome, cloud and star layers, lens flare and wind.  keyframes: explicit GLK/DLK ids (default: all
    in-game ones).  sun=(elev_deg, compass_deg) re-aims the sun (else the baked-shadow direction is kept).
    Weather particles are NOT added here - call snow()/rain()/dust() (preset['weather'] names the suggestion)."""
    p = PRESETS[name]
    e = env(m)
    glk = [k for k in (keyframes or e['ingame_glk']) if m.typ(k) == 'GlobalLightKeyframe']
    dlk = [k for k in (keyframes or e['ingame_dlk']) if m.typ(k) == 'DirlightKeyframe']
    set_light(m, glk, p.get('amb'), p.get('fog'), p.get('dens'), p.get('amb_obj'), p.get('fog_obj'), p.get('dens_obj'))
    if sun:
        set_sun(m, dlk, p.get('front'), p.get('back'), sun[0], sun[1])
        d = sun_direction(*sun_angles(sun[0], sun[1]))
        set_lensflare(m, direction=d)
    else:
        set_sun(m, dlk, p.get('front'), p.get('back'))
    if p.get('sky'):
        fa, fc = p.get('sky_fog', (None, None))
        set_sky(m, p['sky'], fa, fc, p.get('sky_dist'))
        for i in e['FlatSkyKeyframe']:                 # only L13 has them: keep them in step with the dome
            if float(m.arg(i, FSK_TIME)) < CS_TIME_MIN:
                for k, c in enumerate(p['sky']):
                    _setrgb(m, i, FSK_TOP + 3 * k, c)
    set_layers(m, p.get('clouds'), p.get('stars'), p.get('stars_color'))
    if p.get('moon'):
        set_moon(m, *p['moon'])
    if p.get('flare') is not None:
        set_lensflare(m, color=p['flare'])
    if wind and p.get('wind'):
        set_wind(m, *p['wind'])
    if texfilter and p.get('texfilter'):
        set_texture_filter(m, *p['texfilter'])
    return p


set_time_of_day = apply_preset                      # alias used in the design notes


# =============================================================================================== animated time of day
def add_light_keyframes(m, nid, time, preset=None, name=None):
    """Clone the level's base in-game GlobalLightKeyframe + DirlightKeyframe (lowest Time) to a new Time; preset (name
    or dict) recolours the clones, None keeps the base look.  Time < 1000 = gameplay, >= 1000 = cutscene-only look.
    The clones are remembered (m._atmos_made) so apply_preset()/fog()/env() never treat them as the base look."""
    e = env(m)
    p = (PRESETS[preset] if isinstance(preset, str) else preset) or {}
    label = name or '%s %g' % (preset if isinstance(preset, str) else 'look', time)
    made = []
    for src, kind in ((e['ingame_glk'][:1], 'GlobalLightKeyframe'), (e['ingame_dlk'][:1], 'DirlightKeyframe')):
        for s in src:
            i = nid()
            m.add_child(lit(m.parent[s].args[0]), _clone(m.task(s), i, label))
            m.set(i, GLK_TIME if kind == 'GlobalLightKeyframe' else DLK_TIME, float(time))
            made.append(i)
            if kind == 'GlobalLightKeyframe':
                set_light(m, [i], p.get('amb'), p.get('fog'), p.get('dens'), p.get('amb_obj'), p.get('fog_obj'), p.get('dens_obj'))
            else:
                set_sun(m, [i], p.get('front'), p.get('back'))
    _made(m).update(made)
    return made


def add_sky_keyframes(m, nid, pairs):
    """FlatSkyKeyframes (L13 4046/4045 pattern): pairs = [(time, dome or None = the FlatSky's current colours)].
    Imports the FlatSkyKeyframe declaration (only L13 declares it)."""
    ensure_decl(m, 'FlatSkyKeyframe')
    sky = env(m)['FlatSky'][0]
    cur = [_getrgb(m, sky, SKY_DOME + 3 * k) for k in range(5)]
    out = []
    for t, dome in pairs:
        i = nid()
        m.add_child(sky, T(i, 'FlatSkyKeyframe', '', *[c for col in (dome or cur) for c in _rgb(col)], float(t)))
        out.append(i)
    _made(m).update(out)
    return out


def start_clock(m, nid, parent, hour, when='1'):
    """LevelFlow_SetTimeOfDay(hour) once `when` is true - the L13 4047 command (IsRun when, Run SetTimeOfDay, IsNext TRUE,
    Next SequenceCommand_SetCommand(-1)), but in its OWN Container under `parent`: SequenceCommands are a per-parent
    sequence (first child active, SetCommand(id) jumps, -1 stops), so appending to a parent that already has one (L13's
    LevelFlow) would never run.  SetTimeOfDay writes the global LevelFlow (igi2.exe 0x5330a0), so any parent works;
    L25 3770 runs a SequenceCommand inside a plain Container.  The clock: LevelFlow 'Start time' + ticks /
    (GAME_FREQUENCY * 3600) (0x533930) = 1 game hour per real hour; SetTimeOfDay(h) sets the tick part to h hours."""
    for t in ('Container', 'SequenceCommand'):
        ensure_decl(m, t)
    box, i = nid(), nid()
    m.add_child(parent, T(box, 'Container', 'clock %g' % hour, False, children=[
        T(i, 'SequenceCommand', 'time of day %g' % hour, when, 'LevelFlow_SetTimeOfDay(%.6f)' % hour, 'TRUE',
          'SequenceCommand_SetCommand(-1)')]))
    return box


def _clock_owner(m, who):
    owner = getattr(m, '_atmos_clock', None)
    assert owner in (None, who), 'the level clock is already driven by %s(); %s() would fight it' % (owner, who)
    m._atmos_clock = who


def animate_time_of_day(m, nid, parent, end_preset, minutes, when='1', sky=True, base_time=100.0):
    """Gameplay light that changes over `minutes` real minutes (e.g. dusk -> night during the mission).
    Start look = the current in-game keyframes (call apply_preset() FIRST); end look = end_preset.
    Keyframes: start look cloned to base_time, end look at base_time + minutes/60; the clock (which starts at 0 and
    sits below both, i.e. on the start look) is set to base_time when `when` becomes true (e.g. add_shot_chain()['done']),
    so nothing moves during the intro on SP (in-game T=12) or MP (T=0) bases.  Pattern inferred from L13 (keyframes
    12 and 12.003386 = 12.2 s apart + SetTimeOfDay(12.0) when the player enters the storm area)."""
    e = env(m)
    t0, tb = e['t0'], float(base_time)
    t1 = tb + minutes / 60.0
    assert minutes > 0 and t0 < tb and t1 < CS_TIME_MIN
    clash = [t for t in e['all_times'] if t0 < t <= t1 or (t1 < t < CS_TIME_MIN and t < t1 + 1.0)]
    assert not clash, 'existing light keyframes at Time %s lie inside the transition window (%g..%g)' % (clash, t0, t1)
    _clock_owner(m, 'animate_time_of_day')
    made = add_light_keyframes(m, nid, tb, None, name='transition start')
    made += add_light_keyframes(m, nid, t1, end_preset, name='transition end')
    p = PRESETS[end_preset] if isinstance(end_preset, str) else end_preset
    if sky and p.get('sky') and e['FlatSky']:
        made += add_sky_keyframes(m, nid, [(tb, None), (t1, p['sky'])])
    made.append(start_clock(m, nid, parent, tb, when))
    return made


# =============================================================================================== weather
RAIN_PRESETS = {      # (is_rain, traceline start m, end m, colour, alpha, density 1..32 (clamped in igi2.exe 0x4d36a9))
    'drizzle': (True, 5.0, 5.0, (1, 1, 1), 0.04, 1),          # L17 3990
    'normal': (True, 50.0, 20.0, (1, 1, 1), 0.25, 1),         # L16 3084
    'heavy': (True, 15.0, 20.0, (1, 1, 1), 0.5, 1),           # MP forestraid 3617
    'storm': (True, 15.0, 20.0, (1, 1, 1), 0.5, 3),           # GUESS: forestraid with density 3
}
SNOW_PRESETS = {
    'light': (False, 10.0, 30.0, (1, 1, 1), 0.5, 1),          # GUESS: L13 with density 1
    'heavy': (False, 10.0, 30.0, (1, 1, 1), 0.5, 3),          # L13 3068
    'blizzard': (False, 10.0, 30.0, (1, 1, 1), 0.6, 4),       # build_whiteout.py (in-game 10-09)
    'whiteout': (False, 10.0, 30.0, (1, 1, 1), 0.7, 6),       # GUESS
}
DUST_PRESETS = {      # GUESS: the snow sprite (COMMON snow.tex) tinted sand-brown; no original does this
    'light': (False, 10.0, 30.0, (0.80, 0.62, 0.42), 0.35, 2),
    'storm': (False, 8.0, 25.0, (0.78, 0.58, 0.38), 0.55, 6),
}


def weather_task(nid, values, active='1', name='weather'):
    is_rain, t0, t1, col, alpha, dens = values
    return T(nid(), 'RainEffect', name, bool(is_rain), float(t0), float(t1), *_rgb(col), float(alpha), int(dens), active)


def _weather(m, nid, parent, table, intensity, active, name):
    ensure_decl(m, 'RainEffect')
    t = weather_task(nid, table[intensity], active, name)
    m.add_child(parent, t)
    return lit(t.args[0])


def rain(m, nid, parent, intensity='normal', active='1'):
    """RainEffect 'Is Rain' TRUE (drop.tga).  active = expression, e.g. 'LevelFlow_10.nTick > 20 * GAME_FREQUENCY' (L16)."""
    return _weather(m, nid, parent, RAIN_PRESETS, intensity, active, 'rain ' + intensity)


def snow(m, nid, parent, intensity='blizzard', active='1'):
    """RainEffect 'Is Rain' FALSE (snow.tex).  L13 starts it with the player entering an area: 'EditVariable_3066.nValue > 0'."""
    return _weather(m, nid, parent, SNOW_PRESETS, intensity, active, 'snow ' + intensity)


def dust(m, nid, parent, intensity='storm', active='1'):
    """GUESS: tinted snow particles as blowing sand; combine with apply_preset(m, 'dust') (fog does the real work)."""
    return _weather(m, nid, parent, DUST_PRESETS, intensity, active, 'dust ' + intensity)


def fog(m, density, color, sky_amount=None, sky_color=None):
    """Only the fog part of the in-game keyframes (+ sky-dome fog).  Original densities: 0.025 (chinesetemple, clear
    night) .. 0.65 (L24 clear day) .. 1.5 (L12/L31) .. 2.6 (our sandstorm) .. 3 (whiteout) .. 7 (forestraid) .. 10 (L13 storm)."""
    e = env(m)
    set_light(m, e['ingame_glk'], fog=color, dens=density)
    set_sky(m, fog_amount=sky_amount, fog_color=sky_color or color)


def ambient_sound(m, nid, parent, name, pos, size_m, sounddef, inside=False, outside=True, on='', falloff=10.0,
                  min_delay=0.0, random_wait=0.0, fade=0.666667):
    """AmbientArea (sound bed / random one-shots).  sounddef = comma list for random picks (L16 3267 thunder).
    Available everywhere (COMMON): wind_1, noise_loop, noise_01..04, camera_move, camera_stop, camera_beep*, zoom_01.
    Level-only (must be copied into the mission's sound bank, see sounds.md): 16_amb_rain, thunder_02..04 (location1/LEVEL6),
    coldwind_01, coldwind_fx_01..04 (location1/level3), cs32_nature_rain (location3/level2), sandstorm_wind (MP sandstorm)."""
    ensure_decl(m, 'AmbientArea')
    i = nid()
    m.add_child(parent, T(i, 'AmbientArea', name, *map(float, pos), 0.0, 0.0, 0.0, *(float(s) for s in size_m), float(falloff),
                          float(min_delay), float(random_wait), sounddef, bool(inside), bool(outside), on, float(fade), False, 0.0))
    return i


def rain_sounds(m, nid, parent, center, size_m=(2000, 2000, 1000), on=''):
    """L16 3280 + 3267 verbatim (rain bed + random thunder every 30-60 s).  Needs 16_amb_rain / thunder_02..04 in the
    mission's own sound bank."""
    a = ambient_sound(m, nid, parent, 'rain bed', center, size_m, '16_amb_rain', False, True, on, 10.0, 19.0, 0.0, 3.0)
    b = ambient_sound(m, nid, parent, 'thunder', center, size_m, 'thunder_02,thunder_03,thunder_04', False, True, on, 10.0, 30.0, 30.0)
    return a, b


def loop_timer(m, nid, parent, period_s, name='loop timer', on='1'):
    """Self-resetting LevelTimer (L21 3977: On '1', Reset 'LevelTimer_3977.nTick == 4 * GAME_FREQUENCY', Initial run TRUE)"""
    ensure_decl(m, 'LevelTimer')
    i = nid()
    m.add_child(parent, T(i, 'LevelTimer', name, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, on,
                          'LevelTimer_%d.nTick > %.3f * %s' % (i, period_s, GF), True))
    return i


def lightning(m, nid, parent, period_s=13.0, flash_s=0.12, flash_time=500.0, on='1',
              amb=(0.85, 0.88, 1.0), front=(1.6, 1.7, 2.0)):
    """EXPERIMENTAL (GUESS, never done in an original): a lightning flash = jump the level clock to a bright light
    keyframe for flash_s seconds every period_s, then back to the in-game time.  Uses the documented clock
    (LevelFlow_SetTimeOfDay, L13 4047) and a 2-command SequenceCommand loop (SequenceCommand_SetCommand(<id>) jumps,
    as L32 2943).  Do NOT combine with animate_time_of_day() (both set the clock).  Pair with rain_sounds() thunder."""
    for t in ('LevelTimer', 'SequenceCommand', 'Container'):
        ensure_decl(m, t)
    e = env(m)
    t0 = e['t0']
    below = [t for t in e['all_times'] if t < CS_TIME_MIN]
    assert max(below + [t0]) < flash_time < min([float(m.arg(i, GLK_TIME)) for i in e['cs_glk']] + [CS_TIME_MIN]),         'flash_time must lie above every gameplay keyframe and below the cutscene ones'
    _clock_owner(m, 'lightning')
    look = dict(amb=amb, fog=None, dens=None, front=front, back=(0.3, 0.3, 0.35))
    add_light_keyframes(m, nid, flash_time, look, name='lightning flash')
    timer = loop_timer(m, nid, parent, period_s, 'lightning timer', on)
    box = nid()
    a, b = nid(), nid()
    t_on = period_s - 0.6
    m.add_child(parent, T(box, 'Container', 'lightning', False, children=[
        T(a, 'SequenceCommand', 'flash on', 'LevelTimer_%d.nTick > %.3f * %s && LevelTimer_%d.nTick < %.3f * %s'
          % (timer, t_on, GF, timer, t_on + flash_s, GF), 'LevelFlow_SetTimeOfDay(%.6f)' % flash_time, '1',
          'SequenceCommand_SetCommand(%d)' % b),
        T(b, 'SequenceCommand', 'flash off', 'LevelTimer_%d.nTick > %.3f * %s' % (timer, t_on + flash_s, GF),
          'LevelFlow_SetTimeOfDay(%.6f)' % t0, '1', 'SequenceCommand_SetCommand(%d)' % a)]))
    return dict(timer=timer, container=box, on=a, off=b)


# =============================================================================================== lights
def lamp(m, nid, parent, model, pos, rot=(0.0, 0.0, 0.0), name='lamp', render_group=5):
    """A lamp is only a model (EditRigidObj); IGI 2 has no dynamic light task - light is baked into lightmaps.
    Lamp models used by originals: 332_01_1 street lamp, 400_22_1 floodlight, 400_24_1 wall light, 400_50_1 ceiling
    light, 231_16_1 desk lamp, 231_23_1 toilet/roof light, 205_08_1 flood light, 260_53_1 lamppost, 360_19_1 siren
    (availability depends on the base map; validate() checks)."""
    i = nid()
    t = T(i, 'EditRigidObj', name, *map(float, pos), *map(float, rot), model, render_group, False, False)
    if parent is None:
        return t                                     # caller places it (e.g. into blink())
    m.add_child(parent, t)
    return i


def glow(m, nid, parent, pos, color=(2.0, 0.35, 0.25), size=0.35, name='glow', cutoff_m=200.0):
    """GUESS: a light-like glow from a Smoke emitter with the fire sprite (Sprite index 0, as every 'Fire!' / 'Torch -
    flame' original) but no velocity, no gravity and no damage.  Use for flares, beacons, alarm lamps; wrap in
    blink() for flashing.  Smoke is declared in 24/25 originals (not chinesetemple)."""
    ensure_decl(m, 'Smoke')
    i = nid()
    t = T(i, 'Smoke', name, *map(float, pos), 0.0, 0.0, 60, 0.0, 0.785398, 0.0, 0.05, *_rgb(color),
          0.25, 0.1, 1, 0, float(size), 0.2, -1.0, 1.0, 0.6, 0.0, 30.0, '', False, float(cutoff_m), False, 0.0, 0.0)
    if parent is None:
        return t                                     # caller places it (e.g. into blink())
    m.add_child(parent, t)
    return i


def blink(m, nid, parent, period_s, on_s, children, name='blinking'):
    """ConditionalContainer that is on for on_s seconds of every period_s (loop_timer + condition), e.g. a flashing
    alarm glow.  children = list of task Calls, e.g. [glow(m, nid, None, pos)] or [lamp(m, nid, None, ...)]."""
    ensure_decl(m, 'ConditionalContainer')
    timer = loop_timer(m, nid, parent, period_s, name + ' timer')
    i = nid()
    m.add_child(parent, T(i, 'ConditionalContainer', name, 'LevelTimer_%d.nTick < %.3f * %s' % (timer, on_s, GF), '', '',
                          children=list(children)))
    return i, timer


# =============================================================================================== camera keyframes
def key(pos, tgt, dur, smooth, fov=1.0, filt=NONE, color=(0.0, 0.0, 0.0), noise=0.5, shake=0.0, tod=-1.0, roll=0.0,
        target_id=-1, link_id=-1):
    """tools/cutscene.key() + 'tod' (EditCamera Time of day: -1 = in-game light, else the light keyframes at that Time),
    'roll' (Beta, dutch angle), 'target_id' (look-at task, follows it), 'link_id' (ride along with a moving task)."""
    k = CS.key(pos, tgt, dur, smooth, fov=fov, filt=filt, color=color, noise=noise, shake=shake)
    k.update(tod=float(tod), roll=float(roll), target_id=int(target_id), link_id=int(link_id))
    return k


def fov_for(width_m, distance_m):
    """FOV (radians) that frames an object width_m wide at distance_m.  Whether EditCamera FOV is horizontal or vertical
    is UNCONFIRMED; originals use 0.007 (scope) .. 0.1 (binoculars) .. 0.6-1.1 (normal) .. 1.4 (wide)."""
    return 2.0 * math.atan(width_m / 2.0 / distance_m)


def zoom(pos, tgt, dur, fov_from=1.0, fov_to=0.4, hold=0.0, **kw):
    """Static camera, smooth FOV change (zoom in when fov_to < fov_from).  Originals: L36 3683 0.7 -> 0.45 in 12.5 s
    (slow push-in), L31 3130 0.4 -> 0.075 in 2 s (binocular zoom), L21 1921 1.0 -> 0.7 in 1.25 s (camcorder zoom),
    L16 3853 1.1 -> 1.4 in 6.5 s (zoom out).  Multi-key moves are interpolated by a 4-point cubic spline (igi2.exe
    0x43cab0 is called for every channel incl. FOV), so a 2-key move is a plain ease."""
    ks = [key(pos, tgt, dur, True, fov=fov_from, **kw), key(pos, tgt, hold, False, fov=fov_to, **kw)]
    return ks


def crash_zoom(pos, tgt, fov_from=1.0, fov_to=0.12, t=0.35, hold=3.0, shake=0.004, **kw):
    """fast punch-in then hold (handheld feel).  GUESS of style; parameters within original ranges."""
    return [key(pos, tgt, t, True, fov=fov_from, **kw), key(pos, tgt, hold, False, fov=fov_to, shake=shake, **kw)]


def dolly(pos_from, pos_to, tgt, dur, fov_from=1.0, fov_to=None, **kw):
    """camera moves pos_from -> pos_to while looking at tgt (L17 3661->3662 pattern)."""
    return [key(pos_from, tgt, dur, True, fov=fov_from, **kw), key(pos_to, tgt, 0.0, False, fov=fov_to or fov_from, **kw)]


def reveal(tgt, dist_m, bearing_deg, elev0_deg, elev1_deg, dur, fov_from=0.5, fov_to=1.1, **kw):
    """zoom out + crane up from close on tgt to a wide establishing view (pull-back reveal of a building)."""
    def cam(e):
        r = dist_m * M * math.cos(math.radians(e))
        return (tgt[0] + r * math.sin(math.radians(bearing_deg)), tgt[1] + r * math.cos(math.radians(bearing_deg)),
                tgt[2] + dist_m * M * math.sin(math.radians(e)))
    return [key(cam(elev0_deg), tgt, dur, True, fov=fov_from, **kw), key(cam(elev1_deg), tgt, 0.0, False, fov=fov_to, **kw)]


def handheld(keys, amount=0.02, period=3.0):
    """Add a slow breathing sway (L31 3217 'Inside cocpit': keys alternate pitch/roll by 0.01-0.02 rad every 2.65-3.5 s).
    Every key longer than 2 * period is split into sub-keys about `period` long: a smooth key's sub-keys walk along its
    move (position, look-at, FOV, colour, noise, shake interpolated towards the next key); a hold key's sub-keys keep the
    pose.  All sub-keys but the last are smooth; the last keeps the original smooth flag (so hard cuts stay cuts).
    amount in radians ('sway' = pitch / roll offsets, applied by cameras())."""
    lerp = lambda u, w, f: tuple(float(x) + (float(y) - float(x)) * f for x, y in zip(u, w))
    out = []
    for idx, k in enumerate(keys):
        nxt = keys[idx + 1] if idx + 1 < len(keys) else None
        n = int(round(k['dur'] / period)) if k['dur'] > 0 else 0
        if n < 2:
            out.append(k)
            continue
        for j in range(n):
            kk = dict(k)
            if k['smooth'] and nxt is not None:
                f = j / float(n)
                kk['pos'], kk['tgt'] = lerp(k['pos'], nxt['pos'], f), lerp(k['tgt'], nxt['tgt'], f)
                kk['color'] = lerp(k['color'], nxt['color'], f)
                for fld in ('fov', 'noise', 'shake'):
                    kk[fld] = k[fld] + (nxt[fld] - k[fld]) * f
            kk['dur'] = k['dur'] / n
            kk['smooth'] = True if j < n - 1 else k['smooth']
            kk['sway'] = (amount if j % 2 else 0.0, amount if j % 4 == 1 else (-amount if j % 4 == 3 else 0.0))
            out.append(kk)
    return out


# --- surveillance / video looks (atmos.md section 4) ------------------------------------------------------------
TINTS = {      # BAND / BAND_UPDATE colour = per-channel multiply, clamped to 0..1 (igi2.exe 0x554d70)
    'green': (0.0, 1.0, 0.0),            # L12 1111 'Security Cam' (0, 2, 0) -> green-only = monochrome green
    'surveillance': (0.6923, 1.0, 0.6538),   # L11 3394/3069 'Surveilance footage' (0.69, 1.04, 0.65)
    'olive': (0.5846, 0.8346, 0.3538),   # L13 3182 'Sequrity CAM'
    'amber': (1.0, 0.72, 0.25),          # GUESS
    'red': (1.0, 0.0, 0.0),              # GUESS (red-only monochrome)
    'cold': (0.55, 0.75, 1.0),           # GUESS
    'grey': (0.75, 0.75, 0.75),          # GUESS: darkens only, a multiply cannot desaturate
}


def static_burst(pos, tgt, dur=0.15, fov=1.0, color=(0.0, 0.5, 0.0), shake=0.025):
    """'signal acquire / lost' frame: LINE filter with noise 1 (L13 3181/3180: 0.125 s, shake 0.025; HQ video links:
    0.1-0.25 s, colour (0, 0.5, 0), shake 0.001)."""
    return key(pos, tgt, dur, False, fov=fov, filt=LINE, color=color, noise=1.0, shake=shake)


def cctv_keys(pos, tgt, dur, tint='green', fov=0.9, burst_in=True, burst_out=True, pan_to=None, label=True,
              shake=0.0, new_camera=True, zoom_to=None):
    """"We hacked into their CCTV camera": BAND_UPDATE (tinted picture + 'CAMERA n' caption; n counts 1..9, +1 at every
    BAND_UPDATE key, igi2.exe 0x554e50 / 0x554085) framed by LINE static bursts - L13 1221 'Sequrity CAM' pattern
    (LINE 0.125 s -> BAND_UPDATE 6 s -> LINE 0.125 s).  label=False uses BAND with noise 0 (no caption, plain tint).
    pan_to = second look-at point for a slow servo pan (security cameras sweep), zoom_to = end FOV (operator zoom).
    Use with a CutScene of vhf=1.0 for a full-screen monitor feed (no letterbox) - see add_shot_chain()."""
    col = TINTS.get(tint, tint)
    filt = BAND_UPDATE if (label and new_camera) else BAND
    noise = 0.5 if label else 0.0
    ks = []
    if burst_in:
        ks.append(static_burst(pos, tgt, 0.125, fov, col if label else (0, 0.5, 0)))
    moving = pan_to is not None or zoom_to is not None
    ks.append(key(pos, tgt, dur, moving, fov=fov, filt=filt, color=col, noise=noise, shake=shake))
    if moving:   # the end key keeps the filter but must not re-increment the camera number: BAND keeps the label (noise != 0)
        ks.append(key(pos, pan_to or tgt, 0.0, False, fov=zoom_to or fov, filt=BAND, color=col, noise=noise, shake=shake))
    if burst_out:
        ks.append(static_burst(pos, pan_to or tgt, 0.125, zoom_to or fov, col if label else (0, 0.5, 0)))
    return ks


def sweep_keys(pos, look_left, look_right, sweeps=2, pan_s=3.0, hold_s=1.5, tint='green', fov=0.9):
    """A security camera panning left-right-left with pauses (SCamera Rotate Gamma Left/Right + Gamma Delay behaviour)."""
    col = TINTS.get(tint, tint)
    ks = [static_burst(pos, look_left, 0.125, fov, col)]
    first = True
    for s in range(sweeps):
        a = look_left if s % 2 == 0 else look_right
        ks.append(key(pos, a, hold_s, False, fov=fov, filt=BAND_UPDATE if first else BAND, color=col, noise=0.5))
        ks.append(key(pos, a, pan_s, True, fov=fov, filt=BAND, color=col, noise=0.5))
        first = False
    last = look_right if sweeps % 2 else look_left
    ks.append(key(pos, last, hold_s, False, fov=fov, filt=BAND, color=col, noise=0.5))
    ks.append(static_burst(pos, last, 0.125, fov, col))
    return ks


def handicam_keys(pos, tgt, steps=((2.0, 1.0), (1.5, 0.7), (2.0, 0.775)), shake=0.007):
    """Camcorder footage: HANDICAM filter draws a running 'HH : MM : SS : FF' timecode (24 fps; igi2.exe 0x555d80);
    L14 1771 'Bridge HandiCam': shake 0.007-0.009, hold/zoom steps FOV 1 -> 0.7 -> 0.775.  steps = (seconds, fov)."""
    ks = []
    for k, (d, f) in enumerate(steps):
        ks.append(key(pos, tgt, d, False, fov=f, filt=HANDICAM, noise=0.5, shake=shake))
        if k + 1 < len(steps):
            ks.append(key(pos, tgt, 0.75, True, fov=f, filt=HANDICAM, noise=0.5, shake=shake))
    return ks


def videolink_keys(pos, tgt, dur, fov=0.7):
    """HQ video-link (Anya/White on the monitor): LINE (0, 0.5, 0); noise 1 bursts around a noise 0.1-0.2 picture
    (L11 3124, L16 3741, L26 1004, L34 1003 ... 19 originals)."""
    return [static_burst(pos, tgt, 0.2, fov, (0, 0.5, 0), 0.001),
            key(pos, tgt, dur, False, fov=fov, filt=LINE, color=(0, 0.5, 0), noise=0.15),
            static_burst(pos, tgt, 0.2, fov, (0, 0.5, 0), 0.001)]


def binocular_keys(pos, tgt, dur, fov_from=0.4, fov_to=0.075, zoom_s=2.0, shake=0.0005):
    """Binocular POV: LINE noise 0, colour (0, 0.2, 0), tiny FOV, small shake (L31 1008 'Beach through binoculars':
    0.4 -> 0.075 -> 0.035; L24 1004 'Binocular view': 0.1).  Add overlay='BINOCULAR' to the shot (OverlayHolder)."""
    return [key(pos, tgt, zoom_s, True, fov=fov_from, filt=LINE, color=(0, 0.2, 0), noise=0.0, shake=0.0001),
            key(pos, tgt, dur, False, fov=fov_to, filt=LINE, color=(0, 0.2, 0), noise=0.0, shake=shake)]


def scope_keys(pos, tgt, dur, fov=0.015):
    """Thermal sniper-scope POV: L32 2002 'Through scope thermo vision': LINE noise 0 colour (0,0,0)/(0,0.1,0), FOV 0.015
    (0.007 for the closest zoom), shake 0.0001 + OverlayHolder OVERLAY_SNIPER with Infrared expression = CutScene.isRun."""
    return [key(pos, tgt, dur, False, fov=fov, filt=LINE, color=(0, 0.1, 0), noise=0.0, shake=0.0001),
            key(pos, tgt, 0.2, False, fov=fov, filt=LINE, color=(0, 0.1, 0), noise=1.0, shake=0.0001)]


def nightvision_keys(pos, tgt, dur, fov=0.9, tod=None, shake=0.0015):
    """GUESS: IGI 2 has no night-vision gadget (weapons: THERMICAL thermal goggles, BARRETTHERMO, BINOCULARS).  Fake NV =
    BAND green tint with noise 0 (no 'CAMERA n' caption) + optionally a bright cutscene light keyframe (tod=<Time from
    cutscene_light(..., preset 'nv')>) so the night scene is lifted before tinting."""
    return [key(pos, tgt, dur, False, fov=fov, filt=BAND, color=(0.25, 1.0, 0.3), noise=0.0, shake=shake,
                tod=-1 if tod is None else tod)]


def _fade_key(k, dur, smooth, color):
    kk = dict(k)
    kk.update(dur=float(dur), smooth=smooth, filt=BAND, color=color, noise=0.0, shake=0.0)
    kk.pop('sway', None)
    return kk


def fade_in(keys, secs=1.5):
    """prepend the original fade-in pair (BAND (0,0,0) smooth -> BAND (1,1,1)); 15 originals, e.g. L11 3484 -> 3483.
    The pair copies the first key's pose, FOV, tod, roll, target and link."""
    return [_fade_key(keys[0], secs, True, (0, 0, 0)), _fade_key(keys[0], 0.0, False, (1, 1, 1))] + keys


def fade_out(keys, secs=2.5):
    """append the original fade-out pair (BAND (1,1,1) smooth -> BAND (0,0,0)); 25 originals, e.g. L17 3655 -> 3654"""
    return keys + [_fade_key(keys[-1], secs, True, (1, 1, 1)), _fade_key(keys[-1], 0.0, False, (0, 0, 0))]


# --- security-camera point of view -------------------------------------------------------------------------------
def scamera_view(m, scam_id, forward_m=0.9):
    """(pos, look-at point, fov) seen from an existing SCamera task.  GUESS of conventions (UNCONFIRMED): world yaw =
    Holder Gamma + Camera Gamma (HumanPlayer convention: facing (-sin g, cos g)); pitch = Camera Alpha (negative = down);
    the lens sits on the bracket ~0.6 m in front of the holder (313_07_1 bracket spans y 0..0.67 m).  The camera is put
    forward_m further along the view so the SCamera's own mesh is not in the shot.  FOV = Viewcone Gamma (max 1 rad).
    Originals never sit exactly on an SCamera: their 'security cam' shots are 16-60 m away (L11 3394/3069, L12 3520,
    L13 3182, L21 1920) - so a free camera with cctv_keys() is equally faithful."""
    a = [lit(x) for x in m.task(scam_id).args]
    # SCamera args: 3-5 holder pos, 6 holder gamma, 7 holder model, 8 visible, 9 camera alpha, 10 camera gamma,
    # 11/12 camera models, 13-15 rotate left/right/speed (deg), 16 gamma delay, 17-19 viewcone alpha/gamma/length, 20 on
    hold, hg, ca, cg, vg = a[3:6], float(a[6]), float(a[9]), float(a[10]), float(a[18])
    yaw = hg + cg
    fwd = (-math.sin(yaw) * math.cos(ca), math.cos(yaw) * math.cos(ca), math.sin(ca))
    lens = (hold[0] - math.sin(hg) * 0.6 * M, hold[1] + math.cos(hg) * 0.6 * M, hold[2])
    pos = tuple(lens[i] + fwd[i] * forward_m * M for i in range(3))
    tgt = tuple(pos[i] + fwd[i] * 30 * M for i in range(3))
    return pos, tgt, min(math.radians(vg), 1.0)


# =============================================================================================== CutScene assembly
def cameras(nid, keys):
    """EditCamera tasks for the keys (like tools/cutscene.cameras, plus tod / roll / target / link / sway)."""
    out, prev = [], None
    for k in keys:
        a, g = CS.look(k['pos'], k['tgt'])
        if prev is not None:      # unwrap against the previous key even across cuts: the spline uses 4 keys (0x43cab0)
            g += 2 * math.pi * round((prev - g) / (2 * math.pi))
        prev = g
        sa, sr = k.get('sway', (0.0, 0.0))
        x, y, z = (float(c) for c in k['pos'])
        r, gr, b = (float(c) for c in k['color'])
        out.append(T(nid(), 'EditCamera', '', x, y, z, round(a + sa, 6), round(float(k.get('roll', 0.0)) + sr, 6), round(g, 6),
                     float(k['fov']), float(k['dur']), int(k.get('link_id', -1)), True, int(k.get('target_id', -1)), True,
                     bool(k['smooth']), float(k.get('tod', -1.0)), k['filt'], float(k['noise']), r, gr, b, float(k['shake'])))
    return out


def cutscene_task(nid, keys, vhf=0.7, vhf_in=0.0, vhf_out=0.0, name=''):
    """CutScene with EditCamera children.  vhf = 'Viewport height factor' (letterbox: 0.7 in all 149 originals);
    1.0 = no bars (igi2.exe 0x43d967 skips the WideScreenFilter when it equals 1.0); vhf_in/out = bar slide times (0 in
    every original, UNCONFIRMED)."""
    cs = nid()
    x, y, z = (float(c) for c in keys[0]['pos'])
    return cs, T(cs, 'CutScene', name, x, y, z, 0.0, 0.0, 0.0, '!CutScene_%d.isFinished' % cs, '', '', 0.0, 1.0,
                 float(vhf), float(vhf_in), float(vhf_out), 0.0, '', '', children=cameras(nid, keys))


def overlay_task(nid, cs, kind='BINOCULAR', infrared=False, show_distance=True):
    """OverlayHolder shown while CutScene cs runs.  kind: BINOCULAR (L24 3340, L31 3848, L33 2404/2432), SNIPER
    (L32 2945, with infrared), ZOOM, LASERDESIGNATOR (enum 0..3, igi2.exe 0x5466ff).  infrared=True sets the same global
    flag as the thermal goggles (igi2.exe 0x546490) -> thermal rendering for the shot."""
    assert kind.upper() in ('BINOCULAR', 'ZOOM', 'SNIPER', 'LASERDESIGNATOR'), kind
    run = 'CutScene_%d.isRun' % cs
    return T(nid(), 'OverlayHolder', '', run, run if infrared else '', Ident('OVERLAY_' + kind.upper()), bool(show_distance))


def sound_cue(nid, cs, at, sound, name='sfx'):
    """voiceless StatusMessage that only plays a sound at a cutscene time (L32 2979 'noise_04' at 0.1 s, 2980 'noise_01')"""
    return T(nid(), 'StatusMessage', name, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'CutScene_%d.nTick > %s*%s' % (cs, at, GF), '', '',
             sound, True, True, 2.0, '')


def noise_loop_area(nid, pos, name='cctv hiss'):
    """L11 2951 verbatim: COMMON 'noise_loop' hiss around the camera of a surveillance shot"""
    return T(nid(), 'AmbientArea', name, *map(float, pos), 0.0, 0.0, 0.0, 15.0, 15.0, 15.0, 0.0, 0.0, 0.0, 'noise_loop',
             True, True, '', 0.0, False, 0.0)


def add_shot_chain(m, nid, parent, shots, kind='intro', trigger=None, label=None):
    """Intro or outro made of several CutScenes played one after another, each in its own ConditionalContainer - the L11
    intro pattern (3532 -> 3062 '!CutScene_3049.isFinished', 3047 'CutScene_3049.isFinished && !CutScene_3041.isFinished',
    ...).  Lets every shot have its own letterbox (vhf), overlay, props and sounds.
    shots: list of dict(keys=[...], vhf=0.7, label='', captions=[(t, key, text[, sound[, secs]])], cues=[(t, sound)],
                        overlay=None | dict(kind='SNIPER', infrared=True, show_distance=True), noise_loop=False,
                        extra=[task Calls])
    kind='outro': trigger = start expression (e.g. 'StatusMessage_<DONE>.isFinishedDisplay'); result['complete'] goes
    into LevelFlow arg 10.  Returns ids (container, cutscenes, skip, after/complete)."""
    for t in ('CutScene', 'EditCamera', 'ConditionalContainer', 'EditVariable', 'StatusMessage', 'LevelTimer'):
        ensure_decl(m, t)
    skip, top = nid(), nid()
    shot_boxes, cs_ids, top_kids = [], [], []
    for k, s in enumerate(shots):
        cs, cs_t = cutscene_task(nid, s['keys'], vhf=s.get('vhf', 0.7), vhf_in=s.get('vhf_in', 0.0), vhf_out=s.get('vhf_out', 0.0))
        kids = [cs_t]
        for c in s.get('captions', ()):      # captions live in the TOP container (L11 2992: timed on CutScene 3124, parent 3532)
            at, tk, txt = c[:3]              # so a line that runs past the cut is not cut off with the shot's box
            top_kids.append(CS.caption(nid, cs, at, tk, secs=c[4] if len(c) > 4 else 5.0, sound=c[3] if len(c) > 3 else ''))
            m.add_text('messages', tk, txt)
        for at, snd in s.get('cues', ()):
            kids.append(sound_cue(nid, cs, at, snd))
        if s.get('overlay'):
            ensure_decl(m, 'OverlayHolder')
            kids.append(overlay_task(nid, cs, **s['overlay']))
        if s.get('noise_loop'):
            kids.append(noise_loop_area(nid, s['keys'][0]['pos']))
        kids += list(s.get('extra', ()))
        cond = ('!CutScene_%d.isFinished' % cs) if not cs_ids else \
               ('CutScene_%d.isFinished && !CutScene_%d.isFinished' % (cs_ids[-1], cs))
        box = nid()
        shot_boxes.append(T(box, 'ConditionalContainer', s.get('label', 'shot %d' % (k + 1)), cond, '', '', children=kids))
        cs_ids.append(cs)
    last = cs_ids[-1]
    out = dict(container=top, cutscenes=cs_ids, skip=skip)
    if kind == 'intro':
        m.add_child(parent, T(top, 'ConditionalContainer', label or 'Intro Cutscene',
                              '!CutScene_%d.isFinished && !EditVariable_%d.nValue' % (last, skip), CS.MENU_OFF, CS.MENU_ON,
                              children=shot_boxes + top_kids))
        m.add_child(parent, T(skip, 'EditVariable', 'CutScene Break Key (intro)', 0.0, 0.0, 0.0, 0,
                              'EditVariable_%d.nValue == 0 && %s' % (skip, CS.BREAK_KEY), ''))
        after = nid()
        m.add_child(parent, T(after, 'LevelTimer', 'time since intro ended', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                              'CutScene_%d.isFinished || EditVariable_%d.nValue == 1' % (last, skip), '', False))
        out.update(intro=top, after=after, done='(CutScene_%d.isFinished || EditVariable_%d.nValue == 1)' % (last, skip))
    else:
        assert trigger, 'outro needs a trigger expression'
        m.add_child(parent, T(top, 'ConditionalContainer', label or 'Outro Cutscene',
                              '%s && !HumanPlayer_0.isDead && EditVariable_%d.nValue == 0' % (trigger, skip), CS.MENU_OFF,
                              CS.MENU_ON, children=shot_boxes + top_kids))
        m.add_child(parent, T(skip, 'EditVariable', 'CutScene Break Key (outro)', 0.0, 0.0, 0.0, 0,
                              'EditVariable_%d.nValue == 0 &&\n(\n (%s && ConditionalContainer_%d.isRun)\n ||\n CutScene_%d.isFinished\n)'
                              % (skip, CS.BREAK_KEY, top, last), ''))
        out.update(outro=top, complete='EditVariable_%d.nValue == 1' % skip)
    return out


def cutscene_light(m, nid, time, preset=None, **overrides):
    """Cutscene-only light keyframes (GLK + DLK at Time >= 1000) for EditCamera key(..., tod=time).  L36 does exactly this
    for interiors: GLK 4021 + DLK 3681 'Light for indoors cutscenes' at Time 2000, used by 9 cameras inside the Launch
    Bunker; L11 uses 1003/1004/1005/1205/1415/1600 for per-shot moods.  preset 'interior' = L36's values; 'nv' = GUESS."""
    assert time >= CS_TIME_MIN
    looks = {'interior': dict(amb=(0.69, 0.65, 0.69), front=(0.8, 0.63, 0.48), back=(0.0, 0.0, 0.0)),
             'nv': dict(amb=(0.35, 0.95, 0.40), fog=(0.05, 0.25, 0.08), dens=0.6, front=(0.30, 0.90, 0.35), back=(0.05, 0.2, 0.05))}
    p = dict(PRESETS.get(preset, looks.get(preset, {})) if preset else {})
    p.update(overrides)
    return add_light_keyframes(m, nid, time, p, name='CS light %g' % time)


# =============================================================================================== buildings / interiors
def _rot(a, b, g):
    """object orientation (alpha, beta, gamma) -> 3x3, same as tools/navgen.rot (gamma = yaw about +z)"""
    ca, sa, cb, sb, cg, sg = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(g), math.sin(g)
    rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
    ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    rz = np.array([[cg, -sg, 0], [sg, cg, 0], [0, 0, 1]])
    return rz @ ry @ rx


def model_lib(m):
    import mef
    res = [os.path.join(m.src, 'models', m.level_name + '.res'),
           os.path.join(GAME, 'MISSIONS', m.location, 'common', 'models', m.location + '.res'),
           os.path.join(GAME, 'COMMON', 'models', 'common.res')]
    return mef.ModelLib(res)


def to_world(m, bid, local_m):
    """point given in metres in a Building's (or any positioned task's) own frame -> world units"""
    pos = np.array([float(m.arg(bid, k)) for k in (3, 4, 5)])
    R = _rot(*[float(m.arg(bid, k)) for k in (6, 7, 8)])
    return tuple(pos + R @ (np.array(local_m, float) * M))


def building_hull(m, bid, lib=None):
    """world-space triangles + AABB of a Building's collision meshes incl. attached sub-models (interiors)"""
    import mef
    lib = lib or model_lib(m)
    meshes = mef._collision_tree(lib, str(m.arg(bid, 9)).lower(), 'union')
    if not meshes:
        return None
    pos = np.array([float(m.arg(bid, k)) for k in (3, 4, 5)])
    R = _rot(*[float(m.arg(bid, k)) for k in (6, 7, 8)])
    tris = np.concatenate([(v @ R.T + pos)[f] for v, f in meshes])
    flat = tris.reshape(-1, 3)
    return dict(lo=flat.min(0), hi=flat.max(0), tris=tris)


def _vertical_hits(tris, p):
    P = np.array(p[:2], float)
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    d1 = (v0[:, 0] - P[0]) * (v1[:, 1] - P[1]) - (v1[:, 0] - P[0]) * (v0[:, 1] - P[1])
    d2 = (v1[:, 0] - P[0]) * (v2[:, 1] - P[1]) - (v2[:, 0] - P[0]) * (v1[:, 1] - P[1])
    d3 = (v2[:, 0] - P[0]) * (v0[:, 1] - P[1]) - (v0[:, 0] - P[0]) * (v2[:, 1] - P[1])
    ins = ((d1 >= 0) & (d2 >= 0) & (d3 >= 0)) | ((d1 <= 0) & (d2 <= 0) & (d3 <= 0))
    t = tris[ins]
    if not len(t):
        return [], []
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ok = np.abs(n[:, 2]) > 1e-6
    t, n = t[ok], n[ok]
    z = t[:, 0, 2] - (n[:, 0] * (P[0] - t[:, 0, 0]) + n[:, 1] * (P[1] - t[:, 0, 1])) / n[:, 2]
    return sorted(z[z > p[2]]), sorted(z[z < p[2]], reverse=True)


def camera_inside(m, pos, lib=None, clearance_m=0.3):
    """Buildings whose geometry is both above and below `pos` (= camera inside / under a roof), with floor and
    ceiling heights; the same test found 209 original cutscene cameras inside buildings (interiors.py)."""
    lib = lib or model_lib(m)
    out = []
    for bid in m.find('Building'):
        h = building_hull(m, bid, lib)
        if h is None or not ((np.array(pos) >= h['lo'] - 1).all() and (np.array(pos) <= h['hi'] + 1).all()):
            continue
        up, dn = _vertical_hits(h['tris'], pos)
        if up and dn:
            out.append(dict(building=bid, name=m.arg(bid, 2), model=m.arg(bid, 9), floor=dn[0], ceiling=up[0],
                            ok=(pos[2] - dn[0] > clearance_m * M and up[0] - pos[2] > clearance_m * M)))
    return out


def interior_shot(m, bid, cam_local_m, look_local_m, dur, cam_end_local_m=None, fov=1.0, tod=-1.0, lib=None, check=True, **kw):
    """Camera inside a building, positions given in metres in the building's own frame (x right, y forward, z up of the
    unrotated model).  Optional dolly to cam_end_local_m.  check=True asserts both camera points are under the building's
    roof and above its floor.  Originals: L21 2001 'Jones enters room' (house 401_12_1), L25 2001/2002 (Priboi's mansion
    431_01_1), L34 1000-1002 (temple 408_07_1), L36 2008/2010 (Launch Bunker 407_20_1, tod 2000)."""
    p0 = to_world(m, bid, cam_local_m)
    tgt = to_world(m, bid, look_local_m)
    p1 = to_world(m, bid, cam_end_local_m) if cam_end_local_m is not None else p0
    if check:
        lib = lib or model_lib(m)
        for p in (p0, p1):
            hits = [h for h in camera_inside(m, p, lib) if h['building'] == bid]
            assert hits and hits[0]['ok'], 'camera %s not inside building %d (%s)' % (p, bid, hits)
    return [key(p0, tgt, dur, True, fov=fov, tod=tod, **kw), key(p1, tgt, 0.0, False, fov=fov, tod=tod, **kw)]
