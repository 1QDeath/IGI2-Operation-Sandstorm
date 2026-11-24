"""weather - storm night for IGI 2 custom missions (M7 Dark Harbor: heavy rain, lightning, thunder, rain-deafened guards).

Built on tools/atmos.py (presets, RainEffect, the EXPERIMENTAL lightning clock jump, rain_sounds) - this module wires
them into one call and adds what atmos lacks:
  * the original rain + thunder samples (location1/LEVEL6 bank: 16_amb_rain, thunder_02..04) for K.write(extra_samples)
  * lightning flashes in step with thunder (a thunder one-shot StatusMessage sound a fraction of a second after each flash)
  * guards that hear less in the rain: AIFunction_SetHearingRangeFactor(f) (igi2.exe 0x45eae0: one float, clamped 0..1,
    stored at AI+0x1168; registered like SetIdleViewCone1Length; NO original script uses it) appended to every
    aiscript.setup() call while hearing() is active.

    import weather
    S = weather.storm(K, parent=K.LOGIC, rain='storm', flash_period_s=11.0)  # after K.player()
    weather.hearing(0.45)                                                    # BEFORE K.squad(): guards built after it hear 45 %
    K.write(..., extra_samples=[weather.SAMPLES] + ...)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import atmos as AT
import aiscript
from igiqvm import Flt
from mission_lib import T, GAME

GF = 'GAME_FREQUENCY'
L16 = os.path.join(GAME, 'MISSIONS', 'location1', 'LEVEL6', 'sounds')
SAMPLES = (os.path.join(L16, 'sounds.res'), ('16_amb_rain', 'thunder_'), 1, os.path.join(L16, 'sounds.qvm'))


def storm(K, parent=None, rain='storm', look='thunderstorm', flash_period_s=11.0, flash_s=0.25, thunder_delay_s=0.9,
          center=None, size_m=(3000, 3000, 1500), flash_amb=(2.2, 2.25, 2.6), flash_front=(3.2, 3.3, 3.8), sky_glows=0,
          glow_ring_m=700.0, glow_z_m=None, flash_var=False):
    """night storm: preset look, RainEffect, rain bed + random thunder (L16), lightning flashes with a thunder clap after
    each. Returns dict(rain=id, flash=atmos.lightning dict, thunder=[status message ids], ambience=(bed, thunder))"""
    m, nid = K.m, K.nid
    parent = parent or K.LOGIC
    AT.apply_preset(m, look)
    r = AT.rain(m, nid, parent, rain)
    c = center or K.START
    amb = AT.rain_sounds(m, nid, parent, c, size_m)
    # (10-16 in game: atmos' default flash (amb 0.85, sun 1.6) lifted a rainy night frame only 65 -> 70 of 255: too weak)
    fl = AT.lightning(m, nid, parent, period_s=flash_period_s, flash_s=flash_s, amb=flash_amb, front=flash_front)
    t_on = flash_period_s - 0.6                    # (atmos.lightning: the flash starts 0.6 s before its timer wraps)
    # the clap is keyed to the FLASH timer itself (reviewer 10-16: a separate 3-period timer drifted and its third
    # window lay past its own reset); thunder_delay_s past the flash start, wrapped into the timer's period
    t0 = t_on + thunder_delay_s
    if t0 >= flash_period_s:
        t0 -= flash_period_s
    i = nid()
    # 'Is send once' FALSE: re-sends every time the window comes round (one tick wide); empty text = sound only
    m.add_child(parent, T(i, 'StatusMessage', 'thunder clap', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                          'LevelTimer_%d.nTick > %.3f * %s && LevelTimer_%d.nTick < %.3f * %s' % (fl['timer'], t0, GF, fl['timer'], t0 + 0.05, GF),
                          '', '', 'thunder_02', False, False, 0.3, ''))
    claps = [i]
    out = dict(rain=r, flash=fl, thunder=claps, ambience=amb)
    window = 'LevelTimer_%d.nTick > %.3f * %s && LevelTimer_%d.nTick < %.3f * %s' % (fl['timer'], t_on, GF, fl['timer'], t_on + flash_s, GF)
    out['window'] = window
    if sky_glows:
        # (10-16: the clock-jump flash alone was barely / not visible in screenshots - PROTO_M7M8.md item 3. A ring of
        #  huge white glow sprites in the sky, on only during the flash window, lights the clouds wherever Jones looks)
        import math
        cx, cy, cz = (float(v_) for v_ in (center or K.START))
        gz = cz + (glow_z_m if glow_z_m is not None else 260.0) * 4096.0
        kids = []
        for k in range(sky_glows):
            a = 2 * math.pi * k / sky_glows
            kids.append(AT.glow(m, nid, None, (cx + math.cos(a) * glow_ring_m * 4096.0, cy + math.sin(a) * glow_ring_m * 4096.0, gz),
                                color=(3.0, 3.0, 3.4), size=90.0, name='lightning sky glow %d' % k, cutoff_m=4000.0))
        i = nid()
        m.add_child(parent, T(i, 'ConditionalContainer', 'lightning sky (flash)', window, '', '', children=kids))
        out['sky'] = i
    if flash_var:
        # FLASH = 1 during the flash window (a guard script can widen its view cone: 'lightning reveals you')
        i = nid()
        m.add_child(parent, T(i, 'EditVariable', 'lightning flash on', 0.0, 0.0, 0.0, 0,
                              'EditVariable_%d.nValue == 0 && %s' % (i, window), 'EditVariable_%d.nValue == 1 && !(%s)' % (i, window)))
        out['var'] = i
    return out


_ORIG_SETUP = aiscript.setup
_ORIG_ARG = aiscript._arg


def _arg(a):
    if isinstance(a, float):
        return Flt(a)
    return _ORIG_ARG(a)


def hearing(factor):
    """every AI script made by aiscript.setup() from now on also calls AIFunction_SetHearingRangeFactor(factor)
    (0..1; 1 = the engine default). factor None restores the original setup()."""
    if factor is None:
        aiscript.setup, aiscript._arg = _ORIG_SETUP, _ORIG_ARG
        return

    def setup(profile=aiscript.HARD):
        return list(_ORIG_SETUP(profile)) + [('AIFunction_SetHearingRangeFactor', float(factor))]
    aiscript._arg = _arg
    aiscript.setup = setup


def aisquad_floats():
    """let tools/aisquad.script() take float arguments (AIFunction_SetHearingRangeFactor(0.45)) in THIS process -
    the shared module only knows ints / idents; Flt encodes like the originals' float constants"""
    import aisquad
    if getattr(aisquad, '_dh_float', False):
        return
    orig = aisquad._expr

    def _expr(x):
        if isinstance(x, float):
            return Flt(x)
        return orig(x)
    aisquad._expr = _expr
    aisquad._dh_float = True
