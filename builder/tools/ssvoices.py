"""ssvoices - the owner's friends' recorded voices in Operation Sandstorm (owner 11-12, reworked 11-13), behind env SS_VOICES=1.

WHAT THE PLAYER GETS
  Soldiers shout in Iraqi Arabic with real voices, each shout with its English line at the bottom left.
  THIRTEEN VOICES, a fixed one per man (owner 11-13 after playing: "they all look the same, they all feel the same"):
      every ordinary soldier   -> one of five young-soldier voices: three real speakers (the friend who read the page, and two more who
                                  read it in the owner's videos) and two natural variants (a slightly bigger man, a slightly smaller one)
      ssm05_1  heavy sergeant  -> Sergeant Jabbar, two voices     ssm11_1  black vest -> Captain Saad, two voices
      the man at the set in the comms room -> Salam the radio man (ss-judge C11: nobody else has the radio lines)
      bubsci_1 lab coats  -> Dr Nizar, two
  Men are dealt their voices in soldier-id order, so men of one post sound different. A man keeps his voice for the whole mission.
  NO LOOPS (owner 11-13: "he's saying the same sentence... it's being repeated too many times"):
      - every situation has a pool of lines; all voices of a family share the pool's turn, so the next shout of that kind is the next
        SENTENCE whoever says it. A pool holds the friends' words AND the original game's Libyan guard barks for that moment (owner
        11-15, G47: "a mix of my friends' voices and the original game's Libyan soldiers' sounds"; before that, G05, 11-13: "keep
        only the ones we added, mix them with the real game's sounds, don't add extra stories. I am not recording any more");
      - the same voice does not shout twice in a row for 12 s (another man takes the turn);
      - one shout at a time on the level, 3.2 s apart at least (sstalk's gate); shouts on the events the engine floods (he sees Jones,
        hears shots, a man falls, a grenade) are 8 or 14 s apart; "yes, sir" comes only as the answer to a sergeant's or officer's order, and a sergeant, officer or radio man may take such a turn 3 s before a common soldier;
      - a hit: one of seven sounds in turn (three wordless cries of the friends, the original game's three soldier hit sounds, the
        family's word once in seven), 2.5 s apart on the level;
      - a death: every second death keeps the game's own groan; the others are a gasp, a breath, and "mother" once in six deaths.
  General Dhari speaks Arabic in the opening and in the server room (captions stay English); the camera operator and the aide answer.
  The radio man works his set in the comms room (scene sheet friends_11-10/sheets/18_comms.md).

DATA.  work/sandstorm/voices/friends_11-10: voices.json (the 13 voices), clips/v/<voice>_<word>.wav (cut.py variants(): the speaker's own
  take, shifted for a variant, or the fallback speaker's where he never said the word), clips/x/*.wav (the game's own Libyan guard
  barks and hit sounds, copied at the friends' loudness: game data, strip before the repo goes public) and clips/<id>.wav (cutscene and scene lines).
  A word without a clip for every voice of its family is not in the game.

HOW (engine facts are sstalk's, work/sandstorm/voices/ENGINE_NOTES.md)
  Shouts ride on tools/sstalk.py's bark machine (its kind variable, cooldown and clock): with SS_VOICES=1 sstalk's own bark lists are empty
  and this module adds one caption list per (family, situation). Each soldier's AI script gets a prefix for HIS voice: his real AI event
  picks the situation, AIAction_PlaySound says the pool's next line in his voice from his own position, the level shows its caption.
  The engine's own squad barks (GV_NN_01/02, English radio lines in this mission's common bank) cannot follow a man (the engine picks the
  voice from the digit sum of the soldier's task POINTER, decomp aisquad.c), so where the young family has a situation those GV slots are
  left undefined (silent). Death: the dying man's own script gets AIEVENT_DEAD (the engine's ai_death_1..4 are in the game-wide COMMON
  bank and stay untouched; it plays none on a one-shot kill). A hit is not a shout: the cry plays at once, outside the gate, no caption.
  Loud (owner 11-13: "really low"): every DefineSound is volume 1 (the engine clamps higher, soundsys.c) and full volume out to 15 m
  (Miles 3D: about 6 dB down for each doubling beyond that).
  Budget (task ids are short, 4096 in all): a list costs 1 id (its StatusMessage) + 1 (its turn) when it has more than one line; six
  level variables (pain, rest, same-voice and order clocks, last voice, hit turn, death turn). Sound definitions are not script symbols.
"""
import csv, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FR = os.path.join(ROOT, 'work', 'sandstorm', 'voices', 'friends_11-10')
CLIPS = os.path.join(FR, 'clips')
VCLIPS = os.path.join(CLIPS, 'v')
SHEETS = os.path.join(FR, 'sheets')
ON = os.environ.get('SS_VOICES', '1') == '1'

TYPE_BY_MODEL = {'ssm05_1': 'sergeant', 'ssm11_1': 'officer', 'bubsci_1': 'scientist',
                 'ssm03_1': 'sergeant', 'ssm17_1': 'sergeant', 'ssm15_1': 'officer'}   # (ss-soldiers' looks_1113: the grey-haired cap-and-vest man and
                                                                 # the brown beret lead groups like the heavy sergeant; the leather jacket is an officer)
# the common soldiers' five voices go with the look (ss-soldiers' list 11-13: skin = look and age): the young faces get the two higher
# voices, the men in their thirties the two middle ones, the grey beard and the balaclava the deep ones. A model that is not listed
# takes the next of all five.
LOOK = {'ssm02_1': ('ya', 'yc'), 'ssm06_1': ('yc', 'ya'), 'ssm07_1': ('yc', 'ya'), 'ssm10_1': ('ya', 'yc'),
        'ssm01_1': ('ya2', 'yb2'), 'ssm04_1': ('yb2', 'ya2'), 'ssm08_1': ('ya2', 'yb2'),
        'ssm09_1': ('yb2', 'yb'), 'ssm12_1': ('yb',),
        'ssm05_1': ('sa', 'sb'), 'ssm03_1': ('sb', 'sa'), 'ssm17_1': ('sa', 'sb'), 'ssm11_1': ('oa', 'ob'), 'ssm15_1': ('ob', 'oa')}
WHO = {'young': 'SOLDIER', 'sergeant': 'SERGEANT', 'officer': 'OFFICER', 'radio': 'SALAM', 'scientist': 'SCIENTIST'}
VOL = {'shout': (1.0, 15.0, 90.0), 'pain': (1.0, 12.0, 70.0), 'death': (1.0, 12.0, 70.0), 'talk': (1.0, 6.0, 30.0)}   # volume, full to, gone at (m). Owner 11-13 'really low': full volume out to 30 m (was 8.5 / 6 m: sstalk's bark), volume 1 = the engine's maximum; ss-judge 11-13: 30 m gave no cue where a man is, so 15 m, about 6 dB down per doubling beyond
_SPEC = json.load(open(os.path.join(FR, 'voices.json'), encoding='utf-8')) if os.path.isfile(os.path.join(FR, 'voices.json')) else {'voices': [], 'pool': {}}
VOICES = _SPEC['voices']                                       # [{id, family, from, shift, ...}], the order is the voice number (1..)
FAMILY = {}
for _v in VOICES:
    FAMILY.setdefault(_v['family'], []).append(_v['id'])

# (family, situation, AI events, [(word, English caption)]) in priority order per family: the first situation whose event matches wins.
# A word that starts with '@' is one of the GAME'S OWN guard lines (owner G05, 11-13: "keep only the ones we added, mix them with the real
# game's sounds... I am not recording any more"; owner 11-15, G47: "a mix of my friends' voices and the original game's Libyan soldiers'
# sounds"): '@gv_NN' is the ORIGINAL Libya-location guard bark gv_NN (MISSIONS/location2/common, Arabic, 49 recordings; catalogue
# work/sandstorm/voices/friends_11-10/LIBYA_CATALOGUE.md), copied at the friends' loudness (cut.py stock(), clips/x/gv_NN.wav). Until
# G47 these were the English multiplayer radio lines (mpr<voice>_<line>): none is left in a pool. They take their turn in the pool like
# any other line, with their own caption (the catalogue's meaning), so nothing shouts over anything. A Libyan line is one recording:
# whoever's turn it is says it in the original actor's voice.
# ORDER (orchestrator 11-15: "the player must HEAR the mix in an ordinary fight"): in a pool with Libyan lines the two sources alternate
# from its first shout for as long as it has Libyan lines (the friends' remaining lines follow), and some of those pools open with the Libyan line (shots, alarm, all clear), so a fight has both sources
# inside its first shouts (rig takes lg*: with the sergeant's attack pool Libyan-first too, three Libyan lines came in a row). Only readings the catalogue calls 'sure' are in a pool, each with its caption.
# A word is in at most two pools of its family, so one sentence does not come back from every kind of event.
CATS = [
    ('young', 'reply', ('ENEMYDETECTION', 'GUNSHOT', 'BULLETIMPACT', 'GUNSHOTMISS', 'ALARMON', 'BACKUP_REQUEST', 'DISTRESSCALL', 'LOSTSIGHTOFENEMY'),
     [('yessir', 'Yes, sir!'), ('gun', 'Ready!'), ('ok', 'Yes.')]),   # (the Libyan bank has no answer line: ids 05-07 are not in it)
    ('young', 'grenade', ('GRENADESHOUT', 'GRENADELAND', 'GRENADETHROWN'), [('grenade', 'Get down!'), ('@gv_76', 'Find cover!'), ('cover', 'Hide!'), ('@gv_43', 'Get down! Duck!')]),
    ('young', 'mandown', ('FRIENDLY_DYING', 'DEATH_CRY', 'FRIENDLYDETECTION'), [('mandown', 'They killed him!'), ('@gv_60', 'One of the men is down!'), ('alarm', 'Alarm!'), ('@gv_57', 'Man down!')]),
    ('young', 'see', ('ENEMYDETECTION',), [('see', 'I see him!'), ('@gv_30', 'There he is!'), ('found', 'Here! Here!'), ('@gv_66', 'Get him! Kill him!'), ('enemy', 'Stop!'), ('@gv_35', 'I see him!'),
                                           ('fire', 'Get him! Get him!'), ('@gv_36', 'Intruder!'), ('hold', 'Nobody move!')]),
    ('young', 'lost', ('LOSTSIGHTOFENEMY',), [('lost', 'I lost him!'), ('@gv_80', 'Where is he now?'), ('search', 'Find him!'), ('who', "Who's there? Answer!")]),
    ('young', 'reload', ('HANDLEWEAPON',), [('reload', "I'm out of ammo!"), ('@gv_22', 'Cover me!'), ('gun', 'Ready!')]),
    ('young', 'alarm', ('ALARMON',), [('@gv_17', 'Sound the alarm!'), ('alarm', 'Alarm!'), ('hurry', 'Move!')]),
    ('young', 'shots', ('GUNSHOT', 'BULLETIMPACT', 'GUNSHOTMISS', 'EXPLOSION'), [('@gv_41', "We're under fire!"), ('shots', 'Where from?'), ('@gv_84', 'Take cover!'), ('cover', 'Hide!')]),
    ('young', 'what', ('SEENSOMETHING', 'REACTTOSUSPICION'), [('what', 'I heard something.'), ('@gv_47', "What's that?"), ('who', "Who's there? Answer!"), ('@gv_49', 'Is anyone there?')]),
    ('young', 'clear', ('SEARCHOVER',), [('@gv_94', 'False alarm.'), ('back', 'Nothing here.'), ('@gv_90', 'Nothing new.'), ('nothing', 'Relax.')]),
    ('sergeant', 'mandown', ('FRIENDLY_DYING', 'DEATH_CRY', 'FRIENDLYDETECTION', 'FRIENDLY_DAMAGE_SEEN'), [('cowards', 'Cowards!'), ('advance', 'Advance!')]),
    ('sergeant', 'see', ('ENEMYDETECTION',), [('surround', 'Surround him!'), ('@gv_64', 'Fire at will!'), ('bring', 'Bring him!'), ('@gv_63', 'Open fire!'), ('advance', 'Advance!'), ('come', 'Come here!')]),
    ('sergeant', 'lost', ('LOSTSIGHTOFENEMY',), [('spread', 'Spread out!'), ('@gv_13', 'Search the area!'), ('right', 'Right!'), ('left', 'Left!'), ('up', 'Up there!')]),
    # (ss-judge Q25, 11-13: "Hold your fire!" here played when JONES fired at a group and read as friendly fire. The clip is out of play:
    # no event says a guard shot his own man)
    ('sergeant', 'shots', ('GUNSHOT', 'BULLETIMPACT', 'GUNSHOTMISS', 'EXPLOSION'), [('spread', 'Spread out!'), ('@gv_11', 'Hold the position!')]),
    ('sergeant', 'what', ('SEENSOMETHING', 'REACTTOSUSPICION', 'SEARCHOVER'), [('quiet', 'Quiet!'), ('where', 'Hey, where are you going?')]),
    ('officer', 'see', ('ENEMYDETECTION',), [('alive', 'I want him alive!'), ('now', 'Now!')]),
    ('officer', 'alarm', ('ALARMON',), [('attention', 'Stand to!'), ('gate', 'Shut the gates!'), ('command', 'Inform command!')]),
    ('officer', 'lost', ('LOSTSIGHTOFENEMY', 'SEARCHOVER', 'FRIENDLY_DYING', 'DEATH_CRY'), [('guards', 'Where are the guards?'), ('excuses', 'I want no excuses!')]),
    ('radio', 'alarm', ('ALARMON', 'BACKUP_REQUEST', 'DISTRESSCALL', 'ENEMYDETECTION'), [('backup', 'Requesting backup!'), ('hello', 'Hello? Hello?')]),
    ('radio', 'mandown', ('FRIENDLY_DYING', 'DEATH_CRY', 'FRIENDLYDETECTION', 'FRIENDLY_DAMAGE_SEEN'), [('silent', "The guards don't answer!")]),
    ('radio', 'lost', ('LOSTSIGHTOFENEMY',), [('noanswer', 'No answer.'), ('dead', 'The line is dead.')]),
    ('radio', 'clear', ('SEARCHOVER',), [('normal', 'All normal.'), ('received', 'Received.'), ('over', 'Out.')]),
    ('scientist', 'see', ('ENEMYDETECTION', 'ENEMYDETECTION_NO_LOF'), [('civilian', "I'm a civilian, a civilian!"), ('dontshoot', "Don't shoot!"), ('please', 'I beg you, oh God!'),
                                                                        ('kids', 'I have children, I beg you!'), ('notme', "It wasn't me! It wasn't me!"), ('take', 'Take everything!')]),
    ('scientist', 'shots', ('GUNSHOT', 'GUNSHOTMISS', 'BULLETIMPACT', 'VISUAL_GUNSHOT', 'EXPLOSION'), [('civilian', "I'm a civilian, a civilian!"), ('god', 'Oh God! Oh God!'), ('no', 'No, no, no, no!')]),   # (fix1120 L10, owner pic 43: shot at, a scientist must shout the friends' 'civilian' line first)
    ('scientist', 'mandown', ('FRIENDLY_DYING', 'DEATH_CRY', 'FRIENDLY_DAMAGE_SEEN', 'ALARMON'), [('run', 'Run!'), ('guards', 'Guards! Guards!')]),
]
# a hit: the man's own cry at once, whatever else is being shouted, no caption (rig vcf3: behind the shout gate a hit never got its turn).
# One level turn runs through PAIN_SEQ, so two cries in a row are never the same sound; 'pw' is the family's word cry ("they got me", "my
# eye", "oh God": voices.json pool), a family without one cries p1 there. One level clock keeps cries PAIN_GAP ticks apart.
PAIN_SEQ = ('p1', '@ai_hit_01', 'p2', '@ai_hit_02', 'p3', 'pw', '@ai_hit_03')   # ('@ai_hit_NN': the original campaign's own soldier hit sounds)
PAIN_GAP = 75
# a death, on the dying man's own AIEVENT_DEAD, no caption: the level's death turn runs through DEATH_SEQ. None = no sound from here (the
# game's own groan, or nothing on a one-shot kill); 'dw' is "mother...", once in six (owner 11-13: "he says mother, or oh God, that's it").
DEATH_SEQ = ('d1', None, 'd2', None, 'dw', None)               # (None = the game's own death groan: every second death)
# WHERE HE WAS HIT (orchestrator 11-13, owner OK; exe v15 b91205b4, write-up exe_v15_hitcry_sheet.md): with SS_HITPART=1 a man's script
# reads his own last hit part, AIFunction_GetScriptIntegerValue(-2) = the engine's HUMANDAMAGE_PART 0..16, on TAKINGDAMAGE and on DEAD
# only (before his first hit the field reads 0 = right foot). On every second cry of the level's hit turn the man says the word for the
# part, if the friends recorded one: "my leg" for feet and legs, "my shoulder" for an upper arm, "my hand" for hand and lower arm,
# "my stomach" for the upper body and the groin; chest, back and head have no word and take the turn's ordinary sound, as do the
# cries in between. A head kill gets the cut-off breath (d2) or nothing, never "mother".
# ON by default since G29 (11-14, proof sheet friends_11-10/proof/G29_hitpart_sheet.md) and NEEDS exe v15 b91205b4 or newer: on exe v14
# and older slot -2 is not the hit part but whatever lies before the script's integer slots (SS_HITPART=0 for a build on an older exe).
HITPART = os.environ.get('SS_HITPART', '1') in ('1', 'dbg')
# SS_HITPART=dbg (test builds only): every hit and every death of any man says one of 17 different words of soldier voice 1, by the
# raw part number, so a recording shows which part the engine reported (detect.py reads the word). No other cry plays.
HITPART_DBG = os.environ.get('SS_HITPART', '0') == 'dbg'
DBG_WORDS = ('see', 'found', 'enemy', 'fire', 'hold', 'lost', 'search', 'who', 'alarm', 'hurry', 'shots', 'cover', 'what', 'back', 'nothing', 'ok', 'reload')
if HITPART_DBG:
    assert os.environ.get('SS_DEBUG'), 'SS_HITPART=dbg is for test builds only (SS_DEBUG set)'
PART_WORD = (('bl', (0, 1, 2, 6, 7, 8)), ('bs', (5, 11)), ('ba', (3, 4, 9, 10)), ('bb', (12, 15)))
PART_HEAD = 16
# SHOWCASE ONLY (SS_VOICES_STAGE=young_leg,young_belly,young_shoulder): the young family's hit cries become these clips, said in this
# order whatever part of a man is hit. The game cannot pick a cry by body part (Human_HitSound draws one of four at random and no script
# can read the part), so a film that shows 'my leg' is staged. Never set for a build that ships.
STAGED = [i for i in os.environ.get('SS_VOICES_STAGE', '').split(',') if i]
if STAGED:
    assert os.environ.get('SS_DEBUG'), 'SS_VOICES_STAGE is for showcase test builds only (SS_DEBUG set): unset it'   # (a release build must never carry it)
# FLOOD lists: their events come many times a second for as long as the fight lasts. Behind the plain shout gate one such list filled
# every slot (rig vcf3: 'see' every 3.3 s; vcf4, vcf5: 'Move!' five times running; a 1-in-N chance per event did nothing against a
# flood). So these lists also wait for a rest clock: after one of them REST ticks pass before the next (8 or 14 s; 11-13 the owner found
# 5 and 9 s still too much talk). A typed man (sergeant, officer, radio, scientist) may go EARLY ticks sooner: in the 11-13 storage
# house take a common soldier took both turns and the sergeant none.
FLOOD = {'see', 'shots', 'grenade', 'mandown', ('radio', 'alarm')}
# ss-judge 11-13 (rc7s5, Q12): a reply needs an order. These pools are orders; after one of them a common soldier may answer from the
# 'reply' pool for ORDER_WIN ticks (the shout gate opens 3.2 s after the order starts, so the answer comes 3 to 6 s after it), once.
ORDERS = {('sergeant', 'see'), ('sergeant', 'lost'), ('officer', 'see'), ('officer', 'alarm')}
ORDER_WIN = 180
REST = (240, 420)                                              # ticks (GAME_FREQUENCY = 30)
EARLY = 90
SAME = 360                                                     # ticks before the voice that shouted last may shout again
TIMES = max(1, int(os.environ.get('SS_VOICES_X', '1')))        # how many times a shout or cry is started at once (test knob until the rig says 2 is clean)
SELF_HIT = 6000                                                # world units (4096 = 1 m): a hit this near a man's eyes is on him, not on his neighbour
# this mission's English squad barks (build_sandstorm._EN event -> GV ids) go silent where the young family has the situation recorded
GV_COVER = {'see': ('EnemySpotted', 'EnemyFound', 'EnemyDetected', 'Engaging', 'HurryUp'), 'alarm': ('RaiseAlarm',), 'grenade': ('Grenade',), 'mandown': ('ManDown',),
            'shots': ('GunShotHeard', 'TakeCover'), 'what': ('WhatsThat', 'Stop', 'HoldArea'), 'lost': ('LostTarget', 'SearchArea'),
            'clear': ('BackToIdle', 'FalseAlarm', 'Acknowledge'), 'reload': ('ManStationaryGun',)}
# General Dhari and the men who answer him: clip id = the voice def the cutscene asks for (build_sandstorm.vo)
SCENE_DEFS = ('ss_ic3', 'ss_ic4', 'ss_gen_stop', 'ss_gen_there', 'ss_dhari3', 'ss_o_clean', 'ss_dhari2', 'ss_gen_yes1', 'ss_gen_yes2',
              # S19 (owner playtest 11-15: the ending's searchers spoke English): the friends' takes, levelled to -14 LUFS (clips/ss_o_*.wav):
              # v2 11-16 (review S19_review_1 points 5 + 6: in v1 a plain soldier ordered his sergeant "Search!"): the sergeant orders, the
              # soldier answers, one soldier voice for both soldier lines. Clips made by work/sandstorm/voices/friends_11-10/s19clips.py:
              # ss_o_nada -> ss_o_nada2.wav = young_back "ماكو شي" (Nothing here.); ss_o_call -> ss_o_call2.wav = sergeant_come "تعال هنا!"
              # (Come here!) + 0.35 s + young_yessir "حاضر سيدي" (Yes, sir.). v1 files (ss_o_nada/call/come/srch.wav) stay untouched for batch 1.
              'ss_o_nada', 'ss_o_call')
CLIP_SRC = {'ss_o_nada': 'ss_o_nada2', 'ss_o_call': 'ss_o_call2'}   # cutscene voice def -> clip file stem in CLIPS (default: the def name)
# his friend said more than the page line here: the English caption follows what is said (manifest.csv has the Arabic)
CAPTION = {'ss_o_nada': 'SOLDIER: Nothing here.',
           'ss_o_call': 'SERGEANT: Come here! - SOLDIER: Yes, sir.',
           'ss_o_clean': 'GENERAL DHARI: The train is clean? Good, put your men on it. I want every car searched and every station watched. Understood?',
           'ss_dhari2': 'GENERAL DHARI: One man did all this, and he has the chip. I want to know who sent him. Search everywhere. In the end we get him, wherever he runs.'}


def clip(i):
    p = os.path.join(CLIPS, i + '.wav')
    return p if os.path.isfile(p) else None


XCLIPS = os.path.join(CLIPS, 'x')


def xname(voice, word):
    """the game's own sample behind '@...': a Libyan guard bark (gv_NN, one recording whoever shouts) or a hit sound (ai_hit_NN).
    Nothing else: the English radio voices (mpr<k>_<line>) left the pools with voice pass 2 (G47)"""
    w = word[1:]
    assert w.startswith('ai_') or w.startswith('gv_'), "ssvoices: '%s' is not a Libyan bark or a hit sound (no English radio lines since G47)" % word
    return w


def vclip(voice, word):
    p = os.path.join(XCLIPS, xname(voice, word) + '.wav') if word.startswith('@') else os.path.join(VCLIPS, '%s_%s.wav' % (voice, word))
    return p if os.path.isfile(p) else None


def actor(name):
    """build_sandstorm.vo: a friend's take for cutscene voice def `name`, or None"""
    return clip(CLIP_SRC.get(name, name)) if ON and name in SCENE_DEFS else None


def caption(name, text):
    """the caption of cutscene line `name`: the friends' wording where it differs and his take is in"""
    return CAPTION.get(name, text) if actor(name) else text


def defname(voice, word):
    d = 'vx_%s' % xname(voice, word) if word.startswith('@') else 'v%s_%s' % (voice, word)
    assert len(d) <= 15, d
    return d


def _stage_def(i):
    return 'vz_%s' % i.split('_', 1)[1]


# SS_VOICES_ONLYX=1 (test builds only, G47 proof takes): a pool that has Libyan lines keeps ONLY those, so a short fight on the rig
# plays every one of them through its real pool, event and caption. Pools without a Libyan line are as in the release.
# SS_VOICES_ONLYX=2 (test builds only, the per-sample strip): the common soldier's "sees Jones" pool holds EVERY Libyan line of all
# pools, 1.5 s apart, the ids of SS_VOICES_ONLYX_FIRST first, and the sergeants and officers have no "sees Jones" pool (they would take
# every turn), so a long fight plays the samples one after the other through the level bank, each with its caption.
ONLYX = os.environ.get('SS_VOICES_ONLYX', '0') in ('1', '2')
ONLYX_ALL = os.environ.get('SS_VOICES_ONLYX', '0') == '2'
if ONLYX:
    assert os.environ.get('SS_DEBUG'), 'SS_VOICES_ONLYX is for test builds only (SS_DEBUG set)'
if ONLYX_ALL:
    REST = (45, 45)
if ONLYX:
    print('ssvoices: SS_VOICES_ONLYX=%s (proof build, not for release)' % os.environ['SS_VOICES_ONLYX'])


def cats():
    """the pools that exist: only words every voice of the family has a clip for"""
    out = []
    for f, k, evs, lines in CATS:
        have = [(w, en) for w, en in lines if FAMILY.get(f) and all(vclip(v, w) for v in FAMILY[f])]
        if ONLYX and any(w.startswith('@') for w, en in have):
            have = [(w, en) for w, en in have if w.startswith('@')]
        if ONLYX_ALL and (f, k) == ('young', 'see'):
            have = sorted({(w, en) for f2, k2, e2, l2 in CATS for w, en in l2 if w.startswith('@gv_')})
            first = ['@gv_' + x for x in os.environ.get('SS_VOICES_ONLYX_FIRST', '').split(',') if x]
            have = sorted(have, key=lambda l_: (first.index(l_[0]) if l_[0] in first else len(first), l_[0]))
        if ONLYX_ALL and k == 'see' and f in ('sergeant', 'officer'):
            continue
        if have:
            out.append((f, k, evs, have))
    return out


# G47 guard (reviewer 11-15): cats() drops a word without a clip silently, which is right for a friend's take that was never recorded
# but would ship a build with NO Libyan lines if clips/x/gv_NN.wav went missing (git-ignored files made by cut.py stock()).
for _f, _k, _e, _l in CATS:
    for _w, _en in _l:
        assert not _w.startswith('@') or os.path.isfile(os.path.join(XCLIPS, xname(None, _w) + '.wav')) or not VOICES,             'ssvoices: %s (%s %s) has no clip clips/x/%s.wav: run friends_11-10/cut.py stock()' % (_w, _f, _k, _w[1:])


def family_of(model):
    return TYPE_BY_MODEL.get(model, 'young')


def sheet_overlay(paths):
    """sstalk.scenes: a sheet in friends_11-10/sheets replaces the sheet of the same name"""
    if not ON or not os.path.isdir(SHEETS):
        return paths
    over = {f: os.path.join(SHEETS, f) for f in os.listdir(SHEETS) if re.match(r'\d\d_.*\.md$', f)}
    return sorted([over.pop(os.path.basename(p), p) for p in paths] + list(over.values()), key=os.path.basename)


def only_recorded(scene):
    """a friends' sheet plays only the lines that have a clip (a missing line is not in the game)"""
    if os.path.dirname(os.path.abspath(scene.path)) == os.path.abspath(SHEETS):
        scene.lines = [l for l in scene.lines if clip(l.id)]
    return scene


# ------------------------------------------------------------------------------------------------ the level side
def stage(g):
    """right after sstalk.stage: one caption list per (family, situation), on sstalk's bark variables"""
    import sstalk
    m, T, LOGIC, B = g['m'], g['T'], g['LOGIC'], g['ST_BARK']
    assert not B['table'], 'ssvoices: sstalk still has its own bark lists'
    new = sstalk.ids_alloc(m)
    table, n_id = {}, 0
    for code, (f, k, evs, lines) in enumerate(cats(), 1):
        turn = None
        if len(lines) > 1:                                    # (one line = no counter: the list never moves)
            turn = new(); n_id += 1
            m.add_child(LOGIC, T(turn, 'EditVariable', 'SV turn %s %s' % (f, k), 0.0, 0.0, 0.0, 0, '', ''))
        texts = ['%s: %s' % (WHO[f], en) for w, en in lines]
        wide = max(len(x) for x in texts)
        for (w, en), x in zip(lines, texts):
            m.add_text('messages', 'SV%d_%s' % (code, w.upper().replace('@', 'X')), x + ' ' * (wide - len(x)))   # (the list's number in the key: a word may sit in two pools, each pads to its own width)
        keys = ','.join(['SV%d_%s' % (code, w.upper().replace('@', 'X')) for w, en in lines] * 3)
        assert len(keys) < 950, (f, k)
        msg = new(); n_id += 1
        m.add_child(LOGIC, T(-1, 'ConditionalContainer', 'SV %s %s' % (f, k), 'EditVariable_%d.nValue == %d' % (B['bk'], code), '', '', children=[
            T(msg, 'StatusMessage', 'SV %s %s' % (f, k), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'TRUE', keys, '', '', False, True, round((sstalk.HOLD_S + 0.2) * len(lines) * 3, 2), '')]))
        table[(f, k)] = (code, evs, lines, turn)
    g['SV'] = table
    for key, name, rule in (('SV_PAIN', 'SV pain clock', True), ('SV_REST', 'SV rest clock', True), ('SV_SAME', 'SV same voice clock', True), ('SV_ORDER', 'SV order clock', True),
                            ('SV_LAST', 'SV last voice', False), ('SV_HIT', 'SV hit turn', False), ('SV_DIE', 'SV death turn', False)):
        g[key] = pc = new(); n_id += 1                        # (a clock's rule adds its value every tick: set negative, it walks back up to 0 one tick at a time)
        m.add_child(LOGIC, T(pc, 'EditVariable', name, 0.0, 0.0, 0.0, 0, 'EditVariable_%d.nValue < 0' % pc if rule else '', ''))
    if STAGED:
        print('ssvoices: STAGED hit cries %s (showcase build, not for release)' % STAGED)
    if HITPART:
        print('ssvoices: hit cries by body part ON (needs exe v15 or newer)')
    print('ssvoices: %d task ids' % n_id)
    print('ssvoices: %d caption lists, %d shout lines (%s)' % (len(table), sum(len(v[2]) for v in table.values()),
          ', '.join('%s %d' % (f, sum(len(v[2]) for (f2, k), v in table.items() if f2 == f)) for f in WHO if any(f2 == f for f2, k in table))))


def _men(m):
    """AI id (str) -> (soldier id, model)"""
    from mission_lib import tasks, lit
    out = {}
    for t_, d_, p_ in tasks(m.stmts):
        if lit(t_.args[1]) != 'HumanSoldier':
            continue
        a7 = lit(t_.args[7]) if len(t_.args) > 7 and not hasattr(t_.args[7], 'args') else None     # (the model argument)
        model = a7 if isinstance(a7, str) and re.match(r'[a-z]+\d*_\d$', a7) else next(
            (a for a in (lit(x) for x in t_.args[2:] if not hasattr(x, 'args')) if isinstance(a, str) and re.match(r'[a-z]+\d*_\d$', a)), '')
        for c in t_.args:
            if hasattr(c, 'args') and len(c.args) > 1 and lit(c.args[1]) == 'HumanAI':
                out[str(lit(c.args[0]))] = (lit(t_.args[0]), model)
    return out


def cast(men, pin=None):
    """soldier id -> voice id. Dealt in soldier-id order per family (men of one squad have neighbouring ids), so mates sound different;
    pin = {soldier id: family} for a man whose job fixes his family (the comms room's radio man)"""
    pin, out, k = pin or {}, {}, {}
    for hid, model in sorted(men.values()):
        f = pin.get(hid) or family_of(model)
        vs = [v for v in LOOK.get(model, ()) if v in FAMILY.get(f, ())] or FAMILY.get(f)
        if vs:
            key = (f, tuple(vs))                              # (one turn per group of looks that share voices)
            near = {out[h_] for h_ in out if hid - h_ <= 6}   # (the men just before him in the roster are his post: not their voice, if he has a choice)
            for _ in range(len(vs)):
                v = vs[k.get(key, 0) % len(vs)]
                k[key] = k.get(key, 0) + 1
                if v not in near:
                    break
            out[hid] = v
    return out


def ai(g):
    """call after sstalk.ai, before m.write: each soldier's script gets the prefix of his own voice"""
    from alarmai import Bin, C, EQ, AND, If, EV, _in, E, compile_ai, decompile_ai
    from igiqvm import Call, Str
    m, B, SV = g['m'], g['ST_BARK'], g['SV']
    var = lambda key: 'EditVariable_%d.nValue' % g[key]
    bk, cool, incs = 'EditVariable_%d.nValue' % B['bk'], 'EditVariable_%d.nValue' % B['cool'], 'EditVariable_%d.nValue' % g['ST_INCS']
    pain, rest, same, last, hit, die, order = (var(k_) for k_ in ('SV_PAIN', 'SV_REST', 'SV_SAME', 'SV_LAST', 'SV_HIT', 'SV_DIE', 'SV_ORDER'))
    ev = C('AIFunction_GetCurrentEventType')
    # TIMES: the same sound started N times in one script run adds up in the mixer (+6 dB for two). The clips are at full scale and
    # DefineSound volume is capped at 1, so this is the only way left to lift a shout over the gunfire (rig 11-13: shouts 13 dB under it)
    play = lambda d: [Call('AIAction_PlaySound', [Str(d), E(0), E(0)]) for _ in range(TIMES)]
    neg = lambda n: Bin('-', E(0), E(n))
    OR = lambda a, b: Bin('||', a, b)
    # AIFunction_GetRandomValue(n) is a FLOAT in [0, n) (decomp humanai.c): '== 0' is true once in 65536, '< 1' once in n
    one_in = lambda n: Bin('<', C('AIFunction_GetRandomValue', n), E(1))
    # A script cannot tell a one-shot kill from another death: the hit that kills sends no TAKINGDAMAGE, and a per-man mark was tried in
    # HumanSoldier_<him>.nHits: the assignment stops the script (rig vch31 against vch30).
    # AIEVENT_TAKINGDAMAGE goes to the man who is hit AND to every man of his team within 5 m of the hit (decomp humansoldier.c: flags 0x22,
    # radius 20480; humanai.c HumanAI_SendEventHandler). The hit itself is on his own body: under SELF_HIT world units from his eyes
    mine = Bin('<', C('AIFunction_GetEventDistance'), E(SELF_HIT))
    step = lambda v_, n: If(Bin('>=', E(v_), E(n - 1)), [Bin('=', E(v_), E(0))], [Bin('=', E(v_), Bin('+', E(v_), E(1)))])

    n_young = len(FAMILY.get('young', ()))
    assert [v['family'] for v in VOICES[:n_young]] == ['young'] * n_young, 'voices.json: the young voices come first'

    def prefix(vid, f):
        vn = [v['id'] for v in VOICES].index(vid) + 1
        blk = None
        for (f2, k), (code, evs, lines, turn) in reversed(list(SV.items())):
            if f2 != f:
                continue
            then = [Bin('=', E(bk), E(code)), Bin('=', E(cool), E(1)), Bin('=', E(last), E(vn)), Bin('=', E(same), neg(SAME))]
            if turn is None:
                then += play(defname(vid, lines[0][0]))
            else:
                tv = 'EditVariable_%d.nValue' % turn
                then += [If(EQ(tv, n_), play(defname(vid, w))) for n_, (w, en) in enumerate(lines)]
                then.append(step(tv, len(lines)))
            if (f, k) in ORDERS:
                then.append(Bin('=', E(order), neg(ORDER_WIN)))
            if k == 'reply':
                then.append(Bin('=', E(order), E(0)))
            if k in FLOOD or (f, k) in FLOOD:
                # a typed man may go EARLY ticks sooner, but only after a common soldier's shout (voices 1..N_YOUNG): a typed man who
                # went early and reset the clock every time left the soldiers' pools silent for the whole fight (reviewer 11-13)
                ready = EQ(rest, 0) if f == 'young' else OR(EQ(rest, 0), AND(Bin('>', E(rest), neg(EARLY)), Bin('<=', E(last), E(n_young))))
                then = [If(ready, then + [If(one_in(2), [Bin('=', E(rest), neg(REST[0]))], [Bin('=', E(rest), neg(REST[1]))])])]
            on = _in(ev, *[EV(e_) for e_ in evs])
            blk = If(AND(on, Bin('<', E(order), E(0))) if k == 'reply' else on, then, [blk] if blk else None)
        # the gate: nobody is shouting, the cooldown is over, no cutscene, and the last shout was another voice (or 12 s ago)
        pre = [If(AND(EQ(bk, 0), EQ(cool, 0), EQ(incs, 0), OR(Bin('!=', E(last), E(vn)), EQ(same, 0))), [blk])] if blk else []
        if STAGED and f == 'young':
            seq = [_stage_def(i) for i in STAGED]
        else:
            seq = [defname(vid, s_ if vclip(vid, s_) else 'p1') for s_ in PAIN_SEQ]
        cry = [If(EQ(hit, n_), play(d)) for n_, d in enumerate(seq)]
        if HITPART and not (STAGED and f == 'young'):
            part = C('AIFunction_GetScriptIntegerValue', -2)   # (a literal: a call's arguments cannot hold a Bin, so not neg(2))
            word = cry                                        # (innermost else: a part without a word)
            for slot, parts in reversed(PART_WORD):
                if vclip(vid, slot):
                    word = [If(_in(part, *parts), play(defname(vid, slot)), word)]
            cry = [If(_in(hit, *range(0, len(seq), 2)), word, cry)]
        cry = cry + [step(hit, len(seq))]
        if HITPART_DBG:
            cry = [If(EQ(C('AIFunction_GetScriptIntegerValue', -2), n_), play(defname(VOICES[0]['id'], w_))) for n_, w_ in enumerate(DBG_WORDS)]
        pre.insert(0, If(AND(EQ(ev, EV('TAKINGDAMAGE')), mine, EQ(pain, 0), EQ(incs, 0)), [Bin('=', E(pain), neg(PAIN_GAP))] + cry))
        dead = [If(EQ(die, n_), play(defname(vid, s_))) for n_, s_ in enumerate(DEATH_SEQ) if s_ and vclip(vid, s_)]
        if HITPART and vclip(vid, 'd2'):
            head = [If(_in(die, *range(0, len(DEATH_SEQ), 2)), play(defname(vid, 'd2')))]
            dead = [If(EQ(C('AIFunction_GetScriptIntegerValue', -2), PART_HEAD), head, dead)]
        if HITPART_DBG:
            dead = [If(EQ(C('AIFunction_GetScriptIntegerValue', -2), n_), play(defname(VOICES[0]['id'], w_))) for n_, w_ in enumerate(DBG_WORDS)]
        pre.append(If(EQ(ev, EV('DEAD')), dead + [step(die, len(DEATH_SEQ))]))
        return pre

    men = _men(m)
    pin = {}                                                  # (the man at the set in the comms room is the radio man whatever model the roster gave him)
    if 'U comms' in g.get('SQUAD_IDS', {}):
        pin[g['SQUAD_IDS']['U comms'][1][0]] = 'radio'
    who = cast(men, pin)
    n, by = 0, {}
    for key, data in list(m.ai_files.items()):
        if not key.isdigit() or not isinstance(data, (bytes, bytearray)) or key not in men or men[key][0] not in who:
            continue
        hid, model = men[key]
        vid = who[hid]
        f = next(v['family'] for v in VOICES if v['id'] == vid)
        ver, body = decompile_ai(bytes(data))
        m.ai_files[key] = compile_ai(prefix(vid, f) + body, ver)
        by[vid] = by.get(vid, 0) + 1
        n += 1
    g['SV_MEN'], g['SV_CAST'] = by, who
    print('ssvoices: %d soldier scripts carry a voice (%s)' % (n, ', '.join('%s %d' % (v['id'], by.get(v['id'], 0)) for v in VOICES)))


# ------------------------------------------------------------------------------------------------ the sound banks
def sounds(extra, defs, sb):
    """before the level bank is written: every voice's pool words and cries become samples and DefineSounds (scene lines go in through sstalk and vo)"""
    used = {}
    for f, k, evs, lines in cats():
        for v in FAMILY[f]:
            for w, en in lines:
                used[(v, w)] = 'shout'
    for v in VOICES:
        for s_ in set(PAIN_SEQ) | {'p3'} | ({slot for slot, parts in PART_WORD} if HITPART else set()):
            if vclip(v['id'], s_):
                used[(v['id'], s_)] = 'pain'
        for s_ in DEATH_SEQ:
            if s_ and vclip(v['id'], s_):
                used[(v['id'], s_)] = 'death'
    size, seen = 0, set()                                     # (several voices share one of the game's samples: one definition)
    for (v, w), kind in sorted(used.items()):
        d = defname(v, w)
        if d in seen:
            continue
        seen.add(d)
        data = sb.riff_to_ilsf(open(vclip(v, w), 'rb').read(), flags=0x1001)
        size += len(data)
        extra.append((d + '.wav', data))
        defs.append('DefineSound("%s", "%s", 0, 0, 0, %s, %s, %s, -1, -1, -1, -1, FALSE)' % ((d, d) + VOL[kind]))
    for i in STAGED:
        d = _stage_def(i)
        extra.append((d + '.wav', sb.riff_to_ilsf(open(clip(i), 'rb').read(), flags=0x1001)))
        defs.append('DefineSound("%s", "%s", 0, 0, 0, %s, %s, %s, -1, -1, -1, -1, FALSE)' % ((d, d) + VOL['pain']))
    print('ssvoices: %d clips in the level bank: %d of the friends\' (%d voices), %d of the game\'s own; %.1f MB' % (
          len(seen), sum(not d.startswith('vx_') for d in seen), len(VOICES), sum(d.startswith('vx_') for d in seen), size / 1048576.0))


def gv(defs, en):
    """build_sandstorm's GV DefineSound lines (English radio barks) minus the situations the young family has recorded. en = its _EN table"""
    have = {k for f, k, evs, lines in cats() if f == 'young'}
    drop = {gid for k in have for e_ in GV_COVER.get(k, ()) for gid in en.get(e_, ((), ()))[0]}
    keep = [d for d in defs if int(re.search(r'"GV_(\d\d)_', d).group(1)) not in drop]
    if 75 in drop or not any('"GV_75_01"' in d for d in keep):   # (the engine plays GV_75_01 itself on every grenade, and the group may not be empty: sstalk's near-silent def)
        keep = [d for d in keep if '"GV_75_01"' not in d] + ['DefineSound("GV_75_01", "mpr1_3_5", 0, 0, 0, 0.01, 1, 2, -1, -1, -1, -1, FALSE)']
    print('ssvoices: %d of %d English squad bark defs stay (situations without a recording)' % (len(keep) - 1, len(defs)))
    return keep


def status():
    """every word of every family: in a pool, or not used"""
    rows = list(csv.DictReader(open(os.path.join(FR, 'voices.csv'), encoding='utf-8-sig')))
    pool = {}
    for f, k, evs, lines in cats():
        for w, en in lines:
            pool.setdefault((f, w), []).append(k)
    seen = set()
    for r in rows:
        key = (r['family'], r['word'])
        if key in seen:
            continue
        seen.add(key)
        use = '+'.join(pool.get(key, [])) or ('hit' if r['word'] in PAIN_SEQ else 'death' if r['word'] in DEATH_SEQ else '')
        print('%-10s %-12s %-16s %s' % (r['family'], r['word'], use or '-', r['english']))


if __name__ == '__main__':
    status()
