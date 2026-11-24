"""ssvsound - Sandstorm vehicle sounds the way the original levels play them (owner 11-14: "helicopter has no sounds").

Every original level plays a vehicle through ITS OWN sound name in its level sounds.qvm, pointing at a sample of the game's global
COMMON bank (app/COMMON/sounds/sounds.res): L16 DefineSound("16_helicopter", "helicopter_1", .. 50 m, 700 m, loop), L15 "15_helicopter",
L36 "36_heli", L14 "14_helicopter", L17 DefineSound("truck_idle_2", "truck_idle", .. 3.5 m, 100 m, loop). No original calls the COMMON
names ("helicopter_1", "truck_engine", "train_loop_1") from a SoundGenerator; Sandstorm did, and its Hinds, train and trucks were silent.

Correction 11-14 (ss-judge G31, rc7s10 film): the bare COMMON "helicopter_1" DID play, but with COMMON's own define (100 m full, 5000 m
reach) all three Hinds sounded as one flat loop everywhere, into Dhari's room, burying the train and the voices. The level's own defines below
give each a real 3D falloff. (truck_engine is not even a DefineSound in COMMON, only a vehicle group: the trucks were silent, see sstruck audio()).
Samples: COMMON ones are named, not copied (as L16 does). The one exception is the horn: horns exist only in L21's level bank, so foghorn_01
(mono, 2.9 s, the deepest) is copied into ours (125 KB). The builder calls sounds(extra, defs, sb)
next to sstalk/ssvoices (hunk: work/sandstorm/vsound/patch_builder_vsound.py). tools/ssoutro.py (Hinds, train) plays the names below.
Trucks: their own level defines in tools/sstruck.py audio() (judge A1/A7, another session), not here.

Loudness (3D: full volume inside min m, fading out to max m): rotors carry far but sit under the friends' voices (vol 1.0, 6-30 m) at the
distances the troopers talk; engines as COMMON's own truck trigger defines; the train as COMMON's train_loop_1 with a longer tail.
"""
# name, COMMON sample, volume, min m, max m, loop
SOUNDS = [
    ('ssv_hind',      'helicopter_1', 0.85, 25.0, 450.0, True),    # Hind rotor + turbine in flight and on the approach
    ('ssv_hind_idle', 'helicopter_1', 0.55, 15.0, 250.0, True),    # the same Hind settled on its wheels: throttled back, carries less
    ('ssv_train',     'TRAIN_LOOP_1', 0.8,  15.0, 300.0, True),    # the diesel, idling at the platform and pulling
    ('ssv_train_dep', 'truck_revup',  0.9,  10.0, 200.0, False),   # the diesel revving as the train pulls out (once)
    ('ssv_wheels',    'TRAIN_LOOP_2', 0.6,   6.0, 120.0, True),    # wheels on the rails under the crate car, rolling
    ('ssv_horn',      'foghorn_01',   0.8,  20.0, 600.0, False),   # the departure horn (sample copied from L21, see above)
    ('ssv_wind',      'sandstorm_wind', 0.65, 5000.0, 10000.0, True),  # the ending's storm bed (the map's own sample, the map's 0.4 define was faint: judge 11-14)
]
HIND, HIND_IDLE, TRAIN, TRAIN_DEP, WHEELS, HORN, WIND = (s_[0] for s_ in SOUNDS)
COPY = {'foghorn_01': ('location2', 'level1')}                     # samples not in COMMON: copied from that original level's bank


def sounds(extra, defs, sb=None):
    """add the defines to the level group, and the few samples that are not in COMMON to the level bank"""
    import os
    from mission_lib import GAME
    for smp, lv in COPY.items():
        got = [(n_.rsplit('/', 1)[1], b_) for n_, b_ in sb.read_bank(os.path.join(GAME, 'MISSIONS', *lv, 'sounds', 'sounds.res'))[1]
               if n_.rsplit('/', 1)[1].rsplit('.', 1)[0].lower() == smp.lower()]
        assert len(got) == 1, (smp, lv)
        extra.append(got[0])
    for name, smp, vol, lo, hi, loop in SOUNDS:
        defs.append('DefineSound("%s", "%s", 0, 0, 0, %s, %s, %s, -1, -1, -1, -1, %s)' % (name, smp, vol, lo, hi, 'TRUE' if loop else 'FALSE'))
    print('ssvsound: %d vehicle sounds on COMMON samples (%s)' % (len(SOUNDS), ', '.join(s_[0] for s_ in SOUNDS)))
