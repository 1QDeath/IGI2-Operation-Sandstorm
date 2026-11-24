"""ssamb - Operation Sandstorm (M1) ambience, SHOBI rework 2026-10-29 (tw-sandstorm).

SHOBI #2 'ambience all wrong' + the 10-29 digest (work/shobi/digest_sandstorm.md section 8): the storm was silent at
ground level (the MP 'wind at top' bed sits at z 46.5 m, 20 m thick), the parked Hinds played running-rotor loops
(removed in the builder), the generators hummed after the shutdown, jets flew over in a grounded storm (removed), no music.
Owner SOUND RULE 10-18: only the ORIGINAL game's banks, at their own volumes (DefineSound lines copied from the source
level), the originals' AmbientArea layouts (L24 'The Airfield' = the original Libyan airfield at dusk, L25 wind_1 bed).
  storm   MP 'sandstorm_wind' (the map's own howl) copied to ground level + COMMON 'wind_1' bed (L25 3489 layout)
  base    L24 one-shots: distant cars (50 + 100 s), dogs (70 + 90 s); L24 '24_inside_gen' inside the airbase buildings;
          L24 'industrial_02' at the hangar; MP 'sandstorm_gen' hum at both base generators (stops with each generator),
          MP 'ventilation_2' in the admin generator room (stops with it); L24 'fuelpump' at the fuel depot (stops with it)
  voices  Arabic shouts outside, guard radio chatter inside (as before)
  music   L24 '24_music' (music flag, the L24 3350 layout); the mp3 + its DefineSound are copied after the write
build(G) -> the extra sample banks for the builder's sound-bank step ([(res, prefixes, vol, qvm)])
"""
import os
import origsounds
from mission_lib import T

M = 4096.0


def build(G):
    m, K, nid = G['m'], G['K'], G['nid']
    LOGIC, NOT_CS = G['LOGIC'], G['NOT_CS']
    P = G['P']
    GEN_A, GEN_B, FUEL_C4 = G['GEN_A'], G['GEN_B'], G['FUEL_C4']
    # the MP SoundGenerators of the two generators stayed in the south compound when the generators moved: they go
    for i in (3735, 3731):
        if i in m.byid:
            m.remove(i)
    # the admin generator room's own MP bed: off once that generator is shut down (and in cutscenes)
    m.set(2950, 18, '%s && !GenericTBA_%d.isFinished' % (NOT_CS, GEN_A))
    # the MP 'wind at top' bed + 04_amb_nature + inside: off during cutscenes like the rest (the originals do it)
    for i in (3764, 3165, 3753):
        m.set(i, 18, NOT_CS)
    AMB = nid()
    m.add_child(LOGIC, T(AMB, 'Container', 'SS ambience (SHOBI 10-29: originals only)', False))
    base_c = (560000.0, 1000000.0, 0.0)
    gen = lambda tid: P(tid)
    areas = [
        # name, pos, size (m), falloff, delay, random, defs, inside, outside, extra condition
        ('SS storm wind at ground level (MP sandstorm_wind)', (560000.0, 900000.0, 40000.0), (10000.0, 10000.0, 140.0), 5.0, 0.0, 0.0,
         'sandstorm_wind', False, True, ''),
        ('SS desert wind bed (L25 3489: COMMON wind_1)', (560000.0, 900000.0, 40000.0), (10000.0, 10000.0, 1000.0), 10.0, 0.0, 0.0,
         'wind_1', False, True, ''),
        ('SS -ambfx- cars distant (L24 3096)', base_c, (2000.0, 2000.0, 500.0), 10.0, 50.0, 100.0, 'car_distant_01,car_distant_02',
         False, True, ''),
        ('SS -ambfx- dogs (L24 3095)', base_c, (2000.0, 2000.0, 500.0), 10.0, 70.0, 90.0, 'dogs_03,dogs_05,dogs_08', False, True, ''),
        ('SS airbase inside gen (L24 3815 24_inside_gen)', base_c, (400.0, 400.0, 120.0), 10.0, 0.0, 0.0, '24_inside_gen', True, False,
         '!(GenericTBA_%d.isFinished && GenericTBA_%d.isFinished)' % (GEN_A, GEN_B)),      # (reviewer: the base hum stops with the power)
        ('SS hangar machinery (L24 3348 industrial_02)', (639513.0, 900829.0, -24000.0), (15.0, 15.0, 15.0), 1.0, 0.0, 0.0,
         'industrial_02', True, False, '!GenericTBA_%d.isFinished' % GEN_B),
        ('SS generator hum (west admin)', gen(GEN_A), (14.0, 14.0, 8.0), 8.0, 0.0, 0.0, 'sandstorm_gen', True, True,
         '!GenericTBA_%d.isFinished' % GEN_A),
        ('SS generator hum (hangar)', gen(GEN_B), (16.0, 16.0, 9.0), 8.0, 0.0, 0.0, 'sandstorm_gen', True, True,
         '!GenericTBA_%d.isFinished' % GEN_B),
        ('SS fuel pump (L24 fuelpump)', P(3898), (14.0, 14.0, 8.0), 6.0, 0.0, 0.0, 'fuelpump', False, True,
         '!ExplodeObject_3898.isExploded'),
        ('SS arab voices airbase', (560000.0, 940000.0, -20000.0), (230.0, 230.0, 80.0), 10.0, 20.0, 40.0,
         'arab_01,arab_02,arab_03,arab_04', False, True, ''),
        ('SS radio chatter west admin', (222700.0, 965800.0, 35000.0), (20.0, 20.0, 8.0), 9.0, 0.0, 0.0, 'tech_radio_01', True, False, ''),
        ('SS radio chatter north admin', (569754.0, 1200766.0, 70000.0), (18.0, 24.0, 10.0), 9.0, 0.0, 0.0, 'tech_radio_01', True, False, ''),
    ]
    for name, pos, size, falloff, delay, rnd, defs_, inside, outside, cond in areas:
        on = NOT_CS + (' && %s' % cond if cond else '')
        m.add_child(AMB, T(nid(), 'AmbientArea', name, *[float(c) for c in pos], 0.0, 0.0, 0.0, *[float(s) for s in size],
                           float(falloff), float(delay), float(rnd), defs_, inside, outside, on, 0.5, False, 0.0))
    K.NOT_CS = NOT_CS
    origsounds.music_area(K, '24_music', pos=(560000.0, 1000000.0, 40000.0), size_m=10000.0)   # L24 3350 (music flag)
    # (brief 21:30: the music is NOT in the intro, it starts a few seconds after control)
    mus = [i for i in m.find('AmbientArea') if str(m.arg(i, 15)) == '24_music']
    assert len(mus) == 1, mus
    m.set(mus[0], 18, '%s && LevelTimer_%d.nTick > 6 * GAME_FREQUENCY' % (NOT_CS, G['CSI']['after']))
    print('ambience: %d areas (storm at ground level, L24 airfield one-shots + interiors, generator hum stops with the '
          'generators) + 24_music' % len(areas))
    return [origsounds.bank('location2/LEVEL4', ('24_inside_gen', 'industrial_02', 'car_distant_0', 'dogs_0', 'fuelpump'))]


def build_classic(G):
    """10-31 restore (owner: back to the pre-rework flow, keep the good additions): the same original-bank ambience on the
    CLASSIC layout - generators stay in the south compound (code pad 152 by generator 4065 (west yard), pad 150 by generator 3674 (east house)), no fuel
    depot objective. The MP south generator hums go (their AmbientArea copies stop with each generator)."""
    m, nid = G['m'], G['nid']
    LOGIC, NOT_CS, P = G['LOGIC'], G['NOT_CS'], G['P']
    for i in (3735, 3731):
        if i in m.byid:
            m.remove(i)
    for i in (2950, 3764, 3165, 3753):
        if i in m.byid:
            m.set(i, 18, NOT_CS)
    AMB = nid()
    m.add_child(LOGIC, T(AMB, 'Container', 'SS ambience (originals only)', False))
    base_c = (560000.0, 1000000.0, 0.0)
    south = (518600.0, 344000.0, 21000.0)
    areas = [
        ('SS storm wind at ground level (MP sandstorm_wind)', (560000.0, 700000.0, 40000.0), (10000.0, 10000.0, 140.0), 5.0, 0.0, 0.0,
         'sandstorm_wind', False, True, ''),
        ('SS desert wind bed (L25 3489: COMMON wind_1)', (560000.0, 700000.0, 40000.0), (10000.0, 10000.0, 1000.0), 10.0, 0.0, 0.0,
         'wind_1', False, True, ''),
        ('SS -ambfx- cars distant (L24 3096)', base_c, (2000.0, 2000.0, 500.0), 10.0, 50.0, 100.0, 'car_distant_01,car_distant_02',
         False, True, ''),
        ('SS -ambfx- dogs (L24 3095)', south, (2000.0, 2000.0, 500.0), 10.0, 70.0, 90.0, 'dogs_03,dogs_05,dogs_08', False, True, ''),
        ('SS airbase inside gen (L24 3815 24_inside_gen)', base_c, (400.0, 400.0, 120.0), 10.0, 0.0, 0.0, '24_inside_gen', True, False, ''),
        ('SS south inside gen (L24 3815 24_inside_gen)', south, (300.0, 300.0, 120.0), 10.0, 0.0, 0.0, '24_inside_gen', True, False,
         '!(GenericTBA_150.isFinished && GenericTBA_152.isFinished)'),
        ('SS hangar machinery (L24 3348 industrial_02)', (639513.0, 900829.0, -24000.0), (15.0, 15.0, 15.0), 1.0, 0.0, 0.0,
         'industrial_02', True, False, ''),
        ('SS generator hum A', P(4065), (14.0, 14.0, 8.0), 8.0, 0.0, 0.0, 'sandstorm_gen', True, True, '!GenericTBA_152.isFinished'),
        ('SS generator hum B', P(3674), (14.0, 14.0, 8.0), 8.0, 0.0, 0.0, 'sandstorm_gen', True, True, '!GenericTBA_150.isFinished'),
        # (11-02: no Arabic shouts / foreign radio chatter: every soldier speaks English) - SS arab voices south
        # (11-02: no Arabic shouts / foreign radio chatter: every soldier speaks English) - SS arab voices airbase
        # (11-02: no Arabic shouts / foreign radio chatter: every soldier speaks English) - SS radio chatter admin
        # (11-02: no Arabic shouts / foreign radio chatter: every soldier speaks English) - SS radio chatter gatehouse
    ]
    for name, pos, size, falloff, delay, rnd, defs_, inside, outside, cond in areas:
        on = NOT_CS + (' && %s' % cond if cond else '')
        m.add_child(AMB, T(nid(), 'AmbientArea', name, *[float(c) for c in pos], 0.0, 0.0, 0.0, *[float(s) for s in size],
                           float(falloff), float(delay), float(rnd), defs_, inside, outside, on, 0.5, False, 0.0))
    K = G['K']
    K.NOT_CS = NOT_CS
    origsounds.music_area(K, '24_music', pos=(560000.0, 700000.0, 40000.0), size_m=10000.0)   # L24 3350 (music flag)
    mus = [i for i in m.find('AmbientArea') if str(m.arg(i, 15)) == '24_music']
    assert len(mus) == 1, mus
    m.set(mus[0], 18, '%s && LevelTimer_%d.nTick > 6 * GAME_FREQUENCY' % (NOT_CS, G['CSI']['after']))
    print('ambience (classic): %d areas + 24_music' % len(areas))
    return [origsounds.bank('location2/LEVEL4', ('24_inside_gen', 'industrial_02', 'car_distant_0', 'dogs_0'))]
