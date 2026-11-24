"""origsounds - use the REAL game's ambience + music in a custom mission (owner 10-18: generated / downloaded wind, rain,
bells, loops were 'disgusting'; SOUND RULE: only original banks, at the original volumes).

  K.write(..., extra_samples=[origsounds.bank('location1/level3', ('coldwind', '13_inside_gen', 'wolf_', 'owl_', 'aircraft_0'))])
  origsounds.add_music(out, 'location1/level3', '13_music')         # AFTER K.write: copies 13_music.mp3 + its DefineSound
  origsounds.music_area(K, '13_music', size_m=10000)                # BEFORE K.write (an AmbientArea, music flag on)
Sample defs (volume / loop / range) are copied from the source level's own sounds.qvm (spkit.write extra_samples 4th item).
"""
import os, sys, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import igiqvm
from qast import lit
from mission_lib import T, GAME
from igiqvm import Call

M = 4096.0


def src_dir(level):
    return os.path.join(GAME, 'MISSIONS', *level.split('/'), 'sounds')


def bank(level, prefixes, vol=1):
    d = src_dir(level)
    return (os.path.join(d, 'sounds.res'), tuple(prefixes), vol, os.path.join(d, 'sounds.qvm'))


def add_music(out, level, name):
    """copy <name>.mp3 into the build's sounds folder and add the source level's own DefineSound line for it"""
    d = src_dir(level)
    shutil.copy2(os.path.join(d, name + '.mp3'), os.path.join(out, 'sounds', name + '.mp3'))
    _v, st = igiqvm.decompile(open(os.path.join(d, 'sounds.qvm'), 'rb').read())
    line = None
    for grp in st:
        for d_ in (grp.args if isinstance(grp, Call) else []):
            if isinstance(d_, Call) and d_.name == 'DefineSound' and str(lit(d_.args[0])).lower() == name.lower():
                line = igiqvm.stmts_to_qsc([d_]).strip().rstrip(';')
    assert line, ('no DefineSound for', name, 'in', d)
    p = os.path.join(out, 'sounds', 'sounds.qvm')
    ver, sst = igiqvm.decompile(open(p, 'rb').read())
    qsc = igiqvm.stmts_to_qsc(sst) + '\nDefineGroup(\n    "MUSIC",\n    %s\n);\n' % line
    open(p, 'wb').write(igiqvm.compile_stmts(igiqvm.parse_qsc(qsc), ver))
    print('music: %s.mp3 + %s' % (name, line))


def music_area(K, name, pos=None, size_m=10000.0, falloff=10.0, fade=0.666667):
    """the level-wide music AmbientArea as the originals have it (inside + outside, 'music' flag TRUE); off during cutscenes"""
    on = getattr(K, 'NOT_CS', '')
    pos = pos or K.START
    amb = K.nid()
    K.m.add_child(K.LOGIC, T(amb, 'Container', '%s music' % K.PFX, False))
    K.m.add_child(amb, T(K.nid(), 'AmbientArea', '%s music %s' % (K.PFX, name), *[float(c) for c in pos], 0.0, 0.0, 0.0,
                         size_m, size_m, size_m, float(falloff), 0.0, 0.0, name, True, True, on, float(fade), True, 0.0))
