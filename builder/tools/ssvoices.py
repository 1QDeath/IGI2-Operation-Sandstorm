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
        hears shots, a man falls, a grenade, he lost him) are 8 or 14 s apart, and a sergeant, officer or radio man may take such a turn
        3 s before a common soldier;
      - "yes, sir" (G48, ss-judge W9-1) comes only as the answer to an order of his OWN group (same squad, posted within 15 m of the man
        who gave it), so the answer is never louder than the order; once per order, and 21 s pass on the level before the next answer;
      - "what's that?" / "is anyone there?" / the sergeant's "quiet!" (G48, W9-2) are lines of a CALM base: none for 20 s after any
        man's fight event (he sees Jones, a shot, a hit, a death, a grenade, a call for backup), none for 60 s after the alarm goes on,
        and 8 or 14 s apart among themselves;
      - a hit: one of seven sounds in turn (three wordless cries of the friends, the original game's three soldier hit sounds, the
        family's word once in seven), 2.5 s apart on the level;
      - while the mission's hold flag is set (g['SV_HOLD'], a story radio line is playing in play) no shout starts; cries are never held;
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
  Budget (task ids are short, 4096 in all): a list costs 1 id (its StatusMessage) + 1 (its turn) when it has more than one line; ten
  level variables (pain, rest, same-voice, order, answer-rest and calm clocks, last voice, order group, hit turn, death turn). Sound definitions are not script symbols.
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
    # (G48, ss-judge W9-1: no gunshot events: they made the answer land in the middle of a burst. BACKUP_REQUEST is the one that comes
    #  right after an order: the order giver's own ENEMYDETECTION calls his squad for backup, alarmai)
    ('young', 'reply', ('ENEMYDETECTION', 'BACKUP_REQUEST', 'DISTRESSCALL', 'ALARMON', 'LOSTSIGHTOFENEMY'),
     [('yessir', 'Yes, sir!'), ('gun', 'Ready!'), ('ok', 'Yes.')]),   # (the Libyan bank has no answer line: ids 05-07 are not in it)
    ('young', 'grenade', ('GRENADESHOUT', 'GRENADELAND', 'GRENADETHROWN'), [('grenade', 'Get down!'), ('@gv_76', 'Find cover!'), ('cover', 'Hide!'), ('@gv_43', 'Get down! Duck!')]),
    ('young', 'mandown', ('FRIENDLY_DYING', 'DEATH_CRY', 'FRIENDLYDETECTION'), [('mandown', 'They killed him!'), ('@gv_60', 'One of the men is down!'), ('alarm', 'Alarm!'), ('@gv_57', 'Man down!')]),
    ('young', 'see', ('ENEMYDETECTION',), [('see', 'I see him!'), ('@gv_30', 'There he is!'), ('found', 'Here! Here!'), ('@gv_66', 'Get him! Kill him!'), ('enemy', 'Stop!'), ('@gv_35', 'I see him!'),
                                           ('fire', 'Get him! Get him!'), ('@gv_36', 'Intruder!'), ('hold', 'Nobody move!')]),
    # (G48, ss-judge W9-2: "Who's there? Answer!" left this pool. LOSTSIGHTOFENEMY comes all through a firefight and the line reads as a
    #  calm guard's question there; it stays in 'what', which is silent while a fight runs)
    ('young', 'lost', ('LOSTSIGHTOFENEMY',), [('lost', 'I lost him!'), ('@gv_80', 'Where is he now?'), ('search', 'Find him!')]),
    # (G48: "Ready!" left this pool. It is one of the three answers; here it came with no order before it and read as an answer to nobody)
    ('young', 'reload', ('HANDLEWEAPON',), [('reload', "I'm out of ammo!"), ('@gv_22', 'Cover me!')]),
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
    ('scientist', 'see', ('ENEMYDETECTION', 'ENEMYDETECTION_NO_LOF'), [('dontshoot', "Don't shoot!"), ('civilian', "I'm a civilian, a civilian!"), ('please', 'I beg you, oh God!'),
                                                                        ('kids', 'I have children, I beg you!'), ('notme', "It wasn't me! It wasn't me!"), ('take', 'Take everything!')]),
    ('scientist', 'shots', ('GUNSHOT', 'GUNSHOTMISS', 'BULLETIMPACT', 'VISUAL_GUNSHOT', 'EXPLOSION'), [('god', 'Oh God! Oh God!'), ('no', 'No, no, no, no!')]),
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
# G48 (ss-judge W9-2): 'lost' is under the same rest (LOSTSIGHTOFENEMY comes all through a long fight; Sirocco take w9_al).
FLOOD = {'see', 'shots', 'grenade', 'mandown', 'lost', ('radio', 'alarm')}
# G48 (ss-judge W9-2, Sirocco take w9_al: "What's that? / Is anyone there? / I heard something." about 20 of 31 shouts, one every
# 8 s through a continuous alarm firefight; the unengaged men of the level keep getting SEENSOMETHING / REACTTOSUSPICION from it).
# The CALM pools speak only while the level's calm clock stands at 0. EVERY voiced man's script winds it back on his own fight events,
# whether he may shout or not: FIGHT_HOLD ticks on a FIGHT_EVS event, ALARM_HOLD on AIEVENT_ALARMON. A calm line itself winds it
# REST ticks, which is those pools' rest clock (their own, so "What's that?" never delays the "I see him!" that follows it).
# No mission hook: the signal is the men's own events, the same in Sandstorm and Sirocco.
CALM = {'what'}
FIGHT_EVS = ('ENEMYDETECTION', 'ENEMYDETECTION_NO_LOF', 'GUNSHOT', 'GUNSHOTMISS', 'BULLETIMPACT', 'VISUAL_GUNSHOT', 'FRIENDLY_GUNSHOT', 'EXPLOSION',
             'TAKINGDAMAGE', 'FRIENDLY_DAMAGE_SEEN', 'FRIENDLY_DYING', 'DEATH_CRY', 'WOUNDED_CRY', 'GRENADESHOUT', 'GRENADELAND', 'GRENADETHROWN',
             'FLASHBANG', 'BACKUP_REQUEST', 'DISTRESSCALL')
FIGHT_HOLD = 600                                               # ticks: 20 s after the last fight event of any man
ALARM_HOLD = 1800                                              # ticks: 60 s after the alarm goes on
# ss-judge 11-13 (rc7s5, Q12): a reply needs an order. These pools are orders; after one of them a common soldier may answer from the
# 'reply' pool for ORDER_WIN ticks (the shout gate opens 3.2 s after the order starts, so the answer comes 3 to 6 s after it), once.
# G48 (ss-judge W9-1, Sirocco take w9_al: the nearest man said "Yes, sir / Ready / Yes" nine times on a 6.5 s beat to orders 10 to
# 15 dB quieter or not audible at all). The judge's rule: answer only an order the player could hear, i.e. the man who answers is near
# the man who gave it (same squad). Every soldier gets a GROUP number at build time: his squad (the task that holds him), split into
# posts no wider than GROUP_NEAR (start positions, every member within GROUP_NEAR of every other). An order winds the order clock and
# writes the giver's group into SV_OSQ; only a man of that group may answer, once, and then REPLY_REST ticks pass on the level.
# (11-15 first try, dropped: "both men see Jones within 20 m" by AIFunction_GetEventDistance on ENEMYDETECTION. Takes ga1 / ga2 had
#  three audible orders and no answer at all: that the event's place is Jones is not proven, the test seems never to pass.)
ORDERS = {('sergeant', 'see'), ('sergeant', 'lost'), ('officer', 'see'), ('officer', 'alarm')}
ORDER_WIN = 180
# player2 11-15 (film ss_full2, N6): "OFFICER: I want him alive!" came 8 times while the men shot at Jones. A pool in ONCE says its first
# line once per level, then stays on its last line ("Now!"): the turn counter stops at the end instead of going round.
ONCE = {('officer', 'see')}
GROUP_NEAR = 15.0                                              # metres between any two men of one answering group (start positions)
REPLY_REST = 630                                               # ticks: 21 s between two answers on the level
REST = (240, 420)                                              # ticks (GAME_FREQUENCY = 30)
EARLY = 90
SAME = 360                                                     # ticks before the voice that shouted last may shout again
TIMES = max(1, int(os.environ.get('SS_VOICES_X', '1')))        # how many times a shout or cry is started at once (test knob until the rig says 2 is clean)
WU_M = 4096                                                    # world units in a metre (soldier 1347: 712294 units = 173.9 m)
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
                            ('SV_LAST', 'SV last voice', False), ('SV_HIT', 'SV hit turn', False), ('SV_DIE', 'SV death turn', False),
                            ('SV_RREST', 'SV answer rest clock', True), ('SV_CALM', 'SV calm clock', True),
                            ('SV_OSQ', 'SV order group', False)):   # (G48: the new ones last, so the older ones keep their ids)
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


def _groups(m):
    """soldier id -> answering group number (1..N): the squad that holds him, split into posts where every two men stood within
    GROUP_NEAR of each other at level start (G48, ss-judge W9-1). Positions are HumanSoldier arguments 3..5 (world units, WU_M a metre)"""
    from mission_lib import tasks, lit
    squad = {}
    for t_, d_, p_ in tasks(m.stmts):
        if lit(t_.args[1]) == 'HumanSoldier':
            pos = tuple(float(lit(x)) for x in t_.args[3:6])
            squad.setdefault(lit(p_.args[0]) if p_ is not None and p_.name == 'Task_New' else -1, []).append((lit(t_.args[0]), pos))
    out, n, wide = {}, 0, 0
    lim = (GROUP_NEAR * WU_M) ** 2
    d2 = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b))
    for sid, mates in sorted(squad.items()):
        posts = []                                            # (every member of a post within GROUP_NEAR of every other)
        for hid, pos in sorted(mates):
            post = next((p for p in posts if sid != -1 and all(d2(pos, q) <= lim for h_, q in p)), None)
            if post is None:
                posts.append([(hid, pos)])
            else:
                post.append((hid, pos))
        wide += len(posts) > 1
        for p in posts:
            n += 1
            for hid, pos in p:
                out[hid] = n
    print('ssvoices: %d answering groups over %d squads (%d squads split, posts within %.0f m)' % (n, len(squad), wide, GROUP_NEAR))
    return out


def ai(g):
    """call after sstalk.ai, before m.write: each soldier's script gets the prefix of his own voice"""
    from alarmai import Bin, C, EQ, AND, If, EV, _in, E, compile_ai, decompile_ai
    from igiqvm import Call, Str
    m, B, SV = g['m'], g['ST_BARK'], g['SV']
    var = lambda key: 'EditVariable_%d.nValue' % g[key]
    bk, cool, incs = 'EditVariable_%d.nValue' % B['bk'], 'EditVariable_%d.nValue' % B['cool'], 'EditVariable_%d.nValue' % g['ST_INCS']
    pain, rest, same, last, hit, die, order = (var(k_) for k_ in ('SV_PAIN', 'SV_REST', 'SV_SAME', 'SV_LAST', 'SV_HIT', 'SV_DIE', 'SV_ORDER'))
    rrest, calm, osq = var('SV_RREST'), var('SV_CALM'), var('SV_OSQ')
    # G48 (orchestrator 11-15): the mission's own HOLD flag. g['SV_HOLD'] = the name of a level symbol (say 'EditVariable_1234.nValue')
    # that the mission keeps at 0 and sets to anything else while a story radio line plays in play (Anya's objective lines): no shout
    # starts while it is not 0. Nothing is queued: the event is dropped and the next one after the hold speaks, behind the usual gate.
    # Hit cries and death sounds are never held. Not set = no hold (the cutscene gate, sstalk's ST_INCS, is separate and stays).
    # (a tuple of symbols is taken too: an engine string argument is cut at 1023 characters, so a mission with many voiced lines
    #  needs two variables for its rule; Sandstorm's 16 lines do)
    hold = g.get('SV_HOLD') or ()
    hold = (hold,) if isinstance(hold, str) else tuple(hold)
    assert all(re.match(r'[A-Za-z]\w*_\d+\.\w+$', h_) for h_ in hold), "ssvoices: g['SV_HOLD'] must be symbols like 'EditVariable_1234.nValue', not an expression: %r" % (hold,)
    print('ssvoices: shouts hold while %s is not 0' % ' / '.join(hold) if hold else "ssvoices: no hold flag (g['SV_HOLD'] not set)")
    # G48 (reviewer 11-15): the calm clock holds ALARM_HOLD ticks from AIEVENT_ALARMON, which is Sandstorm's whole alarm (60 s). A mission
    # whose alarm runs longer may name its alarm state: g['SV_ALARM'] = one symbol or a tuple of symbols, each 0 while no alarm is on.
    # The calm pools are then also silent while any of them is not 0. Not set = the clock alone.
    alarm = g.get('SV_ALARM') or ()
    alarm = (alarm,) if isinstance(alarm, str) else tuple(alarm)
    assert all(re.match(r'[A-Za-z]\w*_\d+\.\w+$', a_) for a_ in alarm), "ssvoices: g['SV_ALARM'] must be symbols like 'EditVariable_1234.nValue': %r" % (alarm,)
    print('ssvoices: calm lines also wait while %s is not 0' % ' / '.join(alarm) if alarm else "ssvoices: no alarm symbol (g['SV_ALARM'] not set): the calm clock alone")
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

    def prefix(vid, f, grp):
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
                then.append(If(Bin('<', E(tv), E(len(lines) - 1)), [Bin('=', E(tv), Bin('+', E(tv), E(1)))]) if (f, k) in ONCE else step(tv, len(lines)))
            if (f, k) in ORDERS:                               # (G48: the order opens the answer window for the giver's own group only)
                then += [Bin('=', E(order), neg(ORDER_WIN)), Bin('=', E(osq), E(grp))]
            if k == 'reply':
                then += [Bin('=', E(order), E(0)), Bin('=', E(rrest), neg(REPLY_REST))]
            if k in CALM:                                     # (G48: a calm line winds the calm clock: the calm pools' own rest)
                then.append(If(one_in(2), [Bin('=', E(calm), neg(REST[0]))], [Bin('=', E(calm), neg(REST[1]))]))
            if k in FLOOD or (f, k) in FLOOD:
                # a typed man may go EARLY ticks sooner, but only after a common soldier's shout (voices 1..N_YOUNG): a typed man who
                # went early and reset the clock every time left the soldiers' pools silent for the whole fight (reviewer 11-13)
                ready = EQ(rest, 0) if f == 'young' else OR(EQ(rest, 0), AND(Bin('>', E(rest), neg(EARLY)), Bin('<=', E(last), E(n_young))))
                then = [If(ready, then + [If(one_in(2), [Bin('=', E(rest), neg(REST[0]))], [Bin('=', E(rest), neg(REST[1]))])])]
            on = _in(ev, *[EV(e_) for e_ in evs])
            if k == 'reply':
                on = AND(on, Bin('<', E(order), E(0)), EQ(rrest, 0), EQ(osq, grp))
            if k in CALM:
                on = AND(on, EQ(calm, 0), *[EQ(a_, 0) for a_ in alarm])
            blk = If(on, then, [blk] if blk else None)
        # the gate: nobody is shouting, the cooldown is over, no cutscene, and the last shout was another voice (or 12 s ago)
        free = [EQ(bk, 0), EQ(cool, 0), EQ(incs, 0)] + [EQ(h_, 0) for h_ in hold]
        pre = [If(AND(*(free + [OR(Bin('!=', E(last), E(vn)), EQ(same, 0))])), [blk])] if blk else []
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
        # G48: the level's calm clock, wound back by every man's own fight events and by the alarm, outside every gate
        pre.insert(0, If(_in(ev, *[EV(e_) for e_ in FIGHT_EVS]), [If(Bin('>', E(calm), neg(FIGHT_HOLD)), [Bin('=', E(calm), neg(FIGHT_HOLD))])],
                         [If(EQ(ev, EV('ALARMON')), [Bin('=', E(calm), neg(ALARM_HOLD))])]))
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
    groups = _groups(m)
    n, by = 0, {}
    for key, data in list(m.ai_files.items()):
        if not key.isdigit() or not isinstance(data, (bytes, bytearray)) or key not in men or men[key][0] not in who:
            continue
        hid, model = men[key]
        vid = who[hid]
        f = next(v['family'] for v in VOICES if v['id'] == vid)
        ver, body = decompile_ai(bytes(data))
        m.ai_files[key] = compile_ai(prefix(vid, f, groups[hid]) + body, ver)
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
