"""ssintro - Sandstorm's new opening (owner 11-06 items 72, 73), behind env SS_INTRO2=1 until proven. Replaces the 87 s slide show.

Anya on the HQ link -> one real camera in the colonel's server room: Kral and the colonel, a sergeant brought in, the colonel shoots him ->
Anya: that was our man -> from the sky down the canyon, the airbase sinking behind the ridge, the two pickets on the ridge, into Jones' eyes ->
control, and Jones says 'Great. Just how I like it'.

Called from build_sandstorm.py with its globals():
  picket(G)    after the squads, before alarmai.Hunt: the second man on the ridge (own rng state, the other squads do not move)
  keys(G)      in section 8b: -> (camera keys, captions) in place of shots(INTRO)
  stage(G)     after CSI exists: the men in the room, the two on the ridge, Jones' first line

Facts:
- The picture of the room comes only from the two real, breakable cameras 'office' and 'office side' (section 8b feed_cam).
- A man who changes pose = one EditBoneObj per phase in a ConditionalContainer on the cutscene clock (ssoutro's rig): the pistol appears on a hard cut, the fall starts on the shot.
- The shot is the sound file ss_ic5 (silence, then the pistol), so picture and sound share one clock (work/sandstorm/intro2/make_voices.py).
- 11-14 (owner: no Josef Priboi in Iraq): Kral is a silent broker with his own face (sssoldiers ssm19_1); only General Dhari speaks.
- Squads keep running in cutscenes, so the two pickets join after the intro and actors stand on their spots until then (item 22 pattern).
- Item 20: the fall looks north-north-west of the rail line, the train never enters the frame.
"""
import math, os, wave
DROP_ACTORS = []                                   # (G43 11-14: intro actors removed just before m.write, see build_sandstorm.py)
import atmos, weather
import cutscene as CS
from mission_lib import T

M = 4096.0
FLOOR = 5.29                                   # the server room floor, m
# the room's two real cameras (section 8b): lens 0.3 m out of the holder, x 48.5-52.6, y 234.9-240.5
# (owner 11-07 'no stuff behind the man', rig grid c4: at x 50.2 on the north wall the lens stands in the recess beside the wall's step, out of the room's cell, and from z 7.5 up the
#  engine drops the desk, chair, boxes and far shelves. At x 49.2 all of it is drawn at every height. Keep room cameras out of that recess: x <= 49.5)
CAM_N, CAM_S = [50.5, 235.15, 7.1], [49.2, 240.2, 7.1]         # (z set by ceiling())
CAM_W = [48.03, 238.47, 7.1]                   # (the west wall, 0.3 m in from it, the room turned as the building: inward normal (0.94, -0.35))
LOOK_W, LOOK_W2 = (51.1, 238.3, FLOOR + 0.6), (51.35, 238.2, FLOOR + 0.5)
LOOK_W3 = (51.25, 237.75, FLOOR + 0.1)          # (after the shot: ~13 deg right and down from LOOK_W2, his head at (51.0, 237.2) ~10 deg right of centre, the colonel still in)
# (rig i1: nobody stands on a camera's line to the man who talks; seen from the south wall Kral left, colonel in the middle, the sergeant right of him)
# (judge J05 11-08: with Hadi south-east of him the colonel faced the south camera and seemed to stare into the lens. Hadi now stands east of him: the colonel turns side-on
#  to that camera. Guards 0.3 m in front of the door and 0.4 m off the shelf; Hadi falls south-west onto open floor, J06)
# (judge 11-08 b: shelf 2952 fills x 52.37-53.59, y 237.50-239.17 at body height (scenecheck); every man stays 0.3 m clear of it and 0.75 m from the next)
COL_XY, KRAL_XY, SGT_XY, G1_XY, G2_XY = (50.8, 239.0), (49.55, 236.9), (51.75, 238.5), (52.05, 239.25), (51.4, 239.4)
FALL_TO = (51.25, 237.63)                      # (judge 11-08: 10 degrees off his standing facing, so the swap at the shot does not pop. He falls south-south-west: from the south camera the body lies right of the office chair (x 49.75-50.57, y 236.79-237.60), not behind it, nobody on that side: rig j6r / j7r, a guard south of him stood over the body's arm; both guards now stand north, behind him)
HADI_FACE = (51.11, 237.73)                    # (he watches Kral, the buyer, while the colonel talks behind his shoulder)
G1_FACE = (52.0, 236.8)                        # (the guard behind Hadi faces down the room, rifle away from Hadi)                      # he faces this way when shot from behind, and falls onto it
LOOK_K = (50.35, 236.75, FLOOR + 0.6)          # from the north wall, looking down: Kral, the shelves behind him
LOOK_K2 = (50.05, 236.85, FLOOR + 0.95)        # the operator pushes in on him
LOOK_C = (51.15, 238.6, FLOOR + 0.5)           # from the south wall, looking down: the colonel, the sergeant and his guards
LOOK_N1 = (50.4, 238.1, FLOOR + 0.75)          # (a small push in while Kral talks)
LOOK_N0 = (50.2, 238.0, FLOOR + 0.6)           # (the south camera first holds Kral's back and the colonel's face while Kral talks)
LOOK_C2 = (51.25, 238.7, FLOOR + 0.8)          # the push in on the colonel and the sergeant
CAM_TOP = 7.77                                 # (a wall camera under the ceiling, its own holder out of the picture)
FOV = 0.95
NOISE = 0.28                                   # (the feed's bars, 0.5 by default, were heavy on a 20 s scene)
TINT = 'surveillance'
HADI_POSE = 'hands_on_head'                    # (judge J06: 'handcuffed' slowed down left his arms hanging forward, free; this one is a prisoner at a glance)
COL_PISTOL = 'stand_clean_weapon_pistol, stand_clean_weapon_pistol, reload_pistol, zaleb_aims_alternativly_at_jones'   # (rc7k judge: 2 x stand_pistol = 7 s nobody moving on camera 4. Now he wipes the pistol through 'What have we here' and 'slack here', checks the magazine on 'easily fixed' (2.58 + 2.58 + 2.54 = 7.7 s, the old 7.74), then the aim on Kral's quip)
LISTEN = 'stand_nogun'                         # (a man who is not speaking: no gestures, J05)
WARM = 0.6                                     # the black glance at the fall's first view that opens the intro (its outdoor load stalls there, on black)
HOLD = 4.2                                     # on the room after the shot: he reaches the floor at about 1.9 s, then ~2 s of the blood spreading (orchestrator 11-10: k8r showed 0.7 s of it)
GAP = 0.35                                     # between two lines on one shot
SGT_SKIN, KRAL_SKIN, PISTOL, RIFLE = 'ssm13_1', 'pat_1', '138_01_1', '107_01_1'
FALL_S = 18.0                                  # seconds of the descent
EYE_H = 1.62                                   # Jones' eye over his feet: checked on the rig, the last key and the first frame of play must line up
TALK_C = 'white_stand_look_forward_talk, white_stand_look_right_talk'
TALK_K = 'white_stand_look_right_talk, stand_nogun'
# (11-07: past the monitor that filled half the old frame, on her face; the clear voice goes with the face)
HQ_A = ('hq', (4.42, -2.30, -1.27), (4.32, -0.85, -1.36), (4.40, -2.12, -1.28))
HQ_B = ('hq', (4.72, -2.15, -1.30), (4.44, -0.85, -1.45), (4.62, -2.02, -1.31))
HQ_FOV = 0.46
HQ_FOV2 = 0.36                                 # (judge J08: the second HQ shot a close-up on her face, not the same frame again)
HQ_CLEAN = dict(filt=CS.NONE, color=(0.0, 0.0, 0.0), noise=0.0)   # (judge J08: under the green video-link lines HQ read as surveillance; her own room is seen plainly)
WALL_G = 2.786                                 # (the mesh's screens face its +y, into the room)
WALL_P = (50.0 - 0.5 * 0.335, 240.36 - 0.5 * 0.943, 6.99)      # (the wall point behind the middle, its end at the stub by the door corridor; the origin stands 0.5 m in front of the wall)
S = {}                                         # clock marks of this build


def U(p):
    return tuple(c * M for c in p)


def radio_link(path, name):
    """owner 11-07: Anya is clear when her face is on screen and a weak but hearable radio link when she is only heard (to Jones, over a camera feed).
    On top of voice.radio2: a narrower band, a slow fade, soft static, a few ticks, short dips between words. Same result on every build (seed = the def name) -> new wav path"""
    import hashlib, numpy as np
    src = hashlib.sha1(open(path, 'rb').read()).hexdigest()[:10]
    out = os.path.join(os.path.dirname(os.path.dirname(path)) if os.path.basename(os.path.dirname(path)) == 'tmp' else os.path.dirname(path), 'link', '%s_%s.wav' % (name, src))
    if os.path.exists(out):
        return out
    w = wave.open(path, 'rb'); r = w.getframerate(); x = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(float) / 32768.0; w.close()
    rng = np.random.default_rng(int(hashlib.sha1(name.encode()).hexdigest()[:8], 16))
    n = len(x); t = np.arange(n) / float(r)
    f = np.fft.rfftfreq(n, 1.0 / r)
    band = np.clip((f - 240.0) / 220.0, 0.0, 1.0) / (1.0 + (f / 3300.0) ** 8)
    y = np.fft.irfft(np.fft.rfft(x) * band, n)
    y = np.tanh(y * 2.1) / 2.1                             # the small speaker
    y = y * (1.0 + 0.10 * np.sin(2 * np.pi * 3.3 * t + 1.0) + 0.07 * np.sin(2 * np.pi * 7.1 * t))   # the signal breathing
    active = np.convolve(np.abs(x), np.ones(441) / 441.0, 'same')
    k = 0.7
    while k < n / float(r) - 0.5:                          # a short dip now and then: a bad link, never a lost word
        d = rng.uniform(0.035, 0.08); i0, i1 = int(k * r), int((k + d) * r)
        y[i0:i1] *= rng.uniform(0.3, 0.55)
        k += rng.uniform(1.3, 2.6)
    h = rng.standard_normal(n + 64)
    h = np.convolve(h, [1, -0.6], 'same')[:n]              # static, a bit louder while she speaks (the carrier opens)
    y = y + h * (0.0045 + 0.012 * np.clip(active / max(active.max(), 1e-6) * 3.0, 0, 1)) * (1.0 + 0.5 * np.sin(2 * np.pi * 0.7 * t + 2.0))
    for s_ in rng.uniform(0.2, max(0.3, n / float(r) - 0.2), int(n / float(r) * 0.9) + 1):   # ticks
        i0 = int(s_ * r); l_ = int(rng.uniform(0.003, 0.012) * r)
        y[i0:i0 + l_] += rng.standard_normal(len(y[i0:i0 + l_])) * rng.uniform(0.05, 0.12)
    y = y / max(np.abs(y).max(), 1e-6) * 0.9
    os.makedirs(os.path.dirname(out), exist_ok=True)
    w = wave.open(out + '.tmp', 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(r); w.writeframes((y * 32767).astype('<i2').tobytes()); w.close()
    os.replace(out + '.tmp', out)
    return out


def bang_at():
    """the shot, seconds into ss_ic5 (since 11-14 only a breath of silence, then the pistol: Kral is silent)"""
    w_ = wave.open(os.path.join(__import__('voice').ACTORS, 'sandstorm', 'ss_ic5.synsrc.wav'), 'rb')
    s_ = w_.getnframes() / float(w_.getframerate()); w_.close()
    w_ = wave.open(os.path.join(__import__('voice').ACTORS, 'sandstorm', 'ss_ic5.wav'), 'rb')
    a_ = w_.getnframes() / float(w_.getframerate()); w_.close()
    assert a_ >= s_ + 0.85, 'ss_ic5.wav has no shot in it: run python -P work/sandstorm/intro2/make_voices.py'
    assert s_ < 0.2, 'ss_ic5.synsrc.wav is %.2f s: the old Priboi line is still in work/voice_actors/sandstorm (owner 11-14: Kral is silent) - run make_voices.py' % s_
    return s_ + 0.85


def storm_once(G):
    """(redo qa DT04, 11-14: the level's 'sandstorm_wind' def loops and a StatusMessage has no stop) -> 'ss_storm1': the same MP sample decoded
    once to a PCM wav and registered in the builder's VO table, whose DefineSound lines never loop. Played once over the fall."""
    import subprocess, tempfile
    import soundbank as sb, wreck
    p = os.path.join(G['VO_CACHE'], 'ss_storm1_mpwind.wav')
    if not os.path.exists(p):
        got = [b for n, b in sb.read_bank(os.path.join(wreck.GAME, 'MISSIONS', 'multiplayer', 'sandstorm', 'sounds', 'sounds.res'))[1]
               if n.rsplit('/', 1)[-1].rsplit('.', 1)[0].lower() == 'sandstorm_wind']
        assert len(got) == 1, len(got)
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'w.wav')
            open(src, 'wb').write(sb.ilsf_to_riff(got[0]))
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-ac', '1', '-ar', '22050', '-sample_fmt', 's16', p + '.tmp.wav'], check=True)
        os.replace(p + '.tmp.wav', p)
    w_ = wave.open(p, 'rb'); secs = w_.getnframes() / float(w_.getframerate()); w_.close()
    G['VO']['ss_storm1'] = (p, secs)
    return 'ss_storm1', secs


def ceiling(G, which):
    """z (m) of a room camera, just under the ceiling at its lens, so it looks down on the men as a real one does (rig i1: at head height)"""
    c_ = {'N': CAM_N, 'S': CAM_S, 'W': CAM_W}[which]
    tri = G['K']._tris()[0]
    above = atmos._vertical_hits(tri, (c_[0] * M, c_[1] * M, 6.6 * M))[0]
    hits = sorted(z / M for z in above if z > 6.6 * M)
    z_ = min(next((z for z in hits if z > 7.4), hits[0]) - 0.3, CAM_TOP)   # (rig k2: on the west wall the first hit was a shelf top at 6.64, the camera hung under it)
    c_[2] = z_ - 0.07
    print('intro2: room camera %s at z %.2f m, ceiling %.2f' % (which, z_, z_ + 0.3))
    return z_


def cctv(pos, look, dur, burst_in=True, burst_out=True, new_camera=True, pan_to=None, zoom_to=None, label=True):
    """label=False: no 'CAMERA n' overlay (the engine only counts up, so a camera seen again would show the wrong number, judge 11-08)"""
    ks = atmos.cctv_keys(U(pos), U(look), dur, tint=TINT, fov=FOV, burst_in=burst_in, burst_out=burst_out, new_camera=new_camera, pan_to=U(pan_to) if pan_to else None, zoom_to=zoom_to, label=label)
    return [dict(k_, indoor=True, noise=NOISE if (k_['filt'] != atmos.LINE and label) else k_['noise']) for k_ in ks]


def flash(pos, look):
    """the shot knocks the feed out for a moment: a green static frame (judge J07: a BAND (1,1,1) key is the plain picture, it read as a grey glitch)"""
    return [dict(atmos.static_burst(U(pos), U(look), 0.1, FOV, (0.0, 0.5, 0.0)), indoor=True)]


def catmull(q, s):
    """s in 0..1 over the spans of q = [(u, ...values)]: a smooth line through every row"""
    n = len(q)
    i = max(k_ for k_ in range(n - 1) if q[k_][0] <= s) if s < q[-1][0] else n - 2
    u = (s - q[i][0]) / (q[i + 1][0] - q[i][0])
    a, b, c, d = q[max(i - 1, 0)], q[i], q[i + 1], q[min(i + 2, n - 1)]
    return [0.5 * (2 * b[k_] + (c[k_] - a[k_]) * u + (2 * a[k_] - 5 * b[k_] + 4 * c[k_] - d[k_]) * u * u + (3 * b[k_] - a[k_] - 3 * c[k_] + d[k_]) * u ** 3)
            for k_ in range(1, len(b))]


def descent(G):
    """camera keys of the fall: the base under the ridge, a long look at the two pickets (a slow zoom), then down into Jones' eyes, level, north (START_GAMMA)"""
    TERR, START = G['TERR'], G['START']
    gz = float(TERR.height(START[0], START[1]))
    E = (START[0], START[1], gz + EYE_H * M)
    pk = G['PICKET_MID']                           # the point between the two men, at chest height (m from E)
    #      u     camera (m from his eyes)  look at (m from his eyes)     fov
    # (rig i2: at look x -8 the rail line just touched the right edge in the first seconds: the look starts further west, item 20)
    PATH = [(0.00, -16.0, -62.0, 88.0, -48.0, 230.0, 8.0, 1.0), (0.34, -10.0, -46.0, 52.0, -30.0, 170.0, 12.0, 1.0),
            (0.60, -4.0, -30.0, 24.0, pk[0], pk[1], pk[2], 0.6), (0.76, -2.0, -20.0, 13.0, pk[0], pk[1], pk[2], 0.45),
            (0.90, -0.5, -7.0, 4.0, 1.0, 30.0, 7.0, 0.85), (1.00, 0.0, 0.0, 0.0, 0.0, 60.0, 0.0, 1.0)]
    n = 60
    keys, low = [], 1e9
    for i in range(n + 1):
        v = catmull(PATH, i / float(n))
        p = (E[0] + v[0] * M, E[1] + v[1] * M, E[2] + v[2] * M)
        tgt = (E[0] + v[3] * M, E[1] + v[4] * M, E[2] + v[5] * M)
        c = float(TERR.height(p[0], p[1]))
        low = min(low, (p[2] - c) / M)
        if i < n and p[2] < c + 1.4 * M:
            p = (p[0], p[1], c + 1.4 * M)
        keys.append(CS.key(p, tgt, 0.0 if i == n else FALL_S / n, i < n, fov=round(v[6], 3)))
    print('intro2: fall %.1f s, %d keys, lowest clearance %.1f m, ends at %s' % (FALL_S, len(keys), low, [round(c / M, 2) for c in E]))
    return keys, E


def keys(G):
    shots, vo = G['shots'], G['vo']
    ks, caps = shots([(('ss_ia1', 'AnyaHQ'), "ANYA: Al-Saqr Air Base, western Iraq. Night flights, General Dhari running the base tonight, and a European arms dealer who has just sold him something. "
                       "We have one man inside, and a tap on their cameras. This came in an hour ago.", HQ_A)], 'SS_CS', fade_in=True)
    ks = [dict(k_, fov=HQ_FOV, **HQ_CLEAN) for k_ in ks]
    # (orchestrator 11-10, rc7p2 takes p8i1-5: the cut to the fall froze ~1 s at 0 fps in 4 of 5 takes, the first outdoor view loading. The intro now opens on a
    #  black glance at the fall's first view, right after the loading screen, so that load stalls on black and the cut later finds it ready)
    f_, S['eye'] = descent(G)
    ks = [CS.key(f_[0]['pos'], f_[0]['tgt'], WARM, False, fov=f_[0]['fov'], filt=CS.BAND, color=(0.0, 0.0, 0.0), noise=0.0)] + ks
    caps = [(round(c_[0] + WARM, 2),) + tuple(c_[1:]) for c_ in caps]
    t = sum(k_['dur'] for k_ in ks)
    # ---- the room
    S['room0'] = t
    # (orchestrator 11-14, owner: "josef breboy most not be in iraq". Kral spoke Priboi's own recorded lines: he is a SILENT broker now, and only General
    #  Dhari speaks, in the friend's Arabic take (or the build's 'David' voice without it). ss_ic5 is only the pistol: silence, then the shot, one clock)
    for d_ in ('ss_ic3', 'ss_ic4', 'ss_ic5'):
        assert G['voice'].actor_wav(d_, 'sandstorm'), 'no %s.wav: run python -P work/sandstorm/intro2/make_voices.py (the wavs are not in git)' % d_
    n = {d_: vo(d_, x_, 'David', True)[1] for d_, x_ in (('ss_ic3', 'C'), ('ss_ic4', 'C'), ('ss_ic5', ''))}
    TX = {'ss_ic3': 'GENERAL DHARI: So, what is this here?',          # (ss-judge Q28 / M26: what the friend says, manifest.csv l.81-82, not Zaleb's L21 words)
          'ss_ic4': 'GENERAL DHARI: I think our guard has grown a little lax... and that must be dealt with.'}
    cap = lambda at, d_, secs=None: caps.append((round(at, 2), 'SS_CI_' + d_[-1], TX[d_], d_, secs or n[d_] + 0.2))
    t0 = t + 0.125                                  # (the static burst in front of the first feed)
    # (judge F02 11-08: 9 s on one camera with Kral still read as a loop. Kral's first line on the north wall camera, then the south camera takes his second line
    #  over the colonel's face and stays on the room while the operator pans to the colonel and Hadi: one long move, no cut back)
    d0 = 2.6                                        # (11-14: Kral silent - the broker waiting by the desk, the camera drifts onto him)
    ks += cctv(CAM_S, LOOK_K, d0, pan_to=LOOK_K2, zoom_to=0.82)
    t += 0.125 + d0 + 0.125
    # (judge H01 11-08: 13 s on one camera pan read as everyone frozen. Camera 3 now takes only Kral's second line; camera 4, on the west wall, takes the colonel
    #  from his first word: he holds the pistol low while he talks, raises it on Kral's quip, the shot, the fall. Labels 2, 3, 4, nothing seen twice)
    t1 = t + 0.125
    d1 = 2.2                                        # (11-14: the north camera's pan from Kral to the general and Hadi, no words)
    ks += cctv(CAM_N, LOOK_N0, d1, pan_to=LOOK_N1, zoom_to=0.85)
    t += 0.125 + d1 + 0.125
    tw = t + 0.125
    S['s1'] = tw + 0.3                              # (the colonel's first line, on the cut into camera 4: the pistol appears there)
    t2 = S['s1'] + n['ss_ic3'] + GAP + n['ss_ic4'] + 0.3
    BANG = bang_at()
    G['feed_cam'](U((CAM_W[0] - 0.3 * 0.94, CAM_W[1] + 0.3 * 0.35, ceiling(G, 'W'))), -math.pi / 2 - 0.36, 'office west')
    ks += cctv(CAM_W, LOOK_W, t2 + BANG - tw, burst_out=False, pan_to=LOOK_W2, zoom_to=0.85) + flash(CAM_W, LOOK_W2)
    cap(S['s1'], 'ss_ic3'); cap(S['s1'] + n['ss_ic3'] + GAP, 'ss_ic4')
    S['shot_snd'] = t2                              # (stage(): a caption-less StatusMessage plays ss_ic5 here, the originals' one-shot: empty Text, cutscene message)
    S['t2'] = t2
    S['aim'] = S['s1']
    S['bang'] = t2 + BANG
    ks += cctv(CAM_W, LOOK_W2, HOLD, burst_in=False, new_camera=False, pan_to=LOOK_W3, zoom_to=1.0)   # (the operator follows him down: his head and the pool fully in frame, k8r had them on the edge)
    t = S['bang'] + 0.1 + HOLD + 0.125
    S['hq2'] = t
    # ---- back to Anya
    k2, c2 = shots([(('ss_ia2', 'AnyaHQ'), "ANYA: That was Sergeant Hadi, our man inside. His last message was one word: dawn. "
                     "Whatever they are doing, it ends at dawn, and you are all we have left.", HQ_B)], 'SS_CT')
    ks += [dict(k_, fov=HQ_FOV2, **HQ_CLEAN) for k_ in k2]
    caps += [(round(c_[0] + t, 2),) + tuple(c_[1:]) for c_ in c2]
    t += sum(k_['dur'] for k_ in k2)
    # ---- the fall
    S['fall'] = t
    S['storm_def'] = storm_once(G)[0]
    ks += f_
    d3, s3 = vo('ss_ia3', "ANYA: Cut the power in the south compound. That opens the sewer into the airbase. Hack their server, take Kral's laptop, and find out what Hadi died for.", 'Anya')
    d4, s4 = vo('ss_ia4', 'ANYA: The sandstorm is your only cover. Good luck, Jones.', 'Anya')
    caps += [(round(t + 0.8, 2), 'SS_CF_1', "ANYA: Cut the power in the south compound. That opens the sewer into the airbase. Hack their server, take Kral's laptop, and find out what Hadi died for.", d3, s3 + 0.3),
             (round(t + 0.8 + s3 + 0.5, 2), 'SS_CF_2', 'ANYA: The sandstorm is your only cover. Good luck, Jones.', d4, s4 + 0.3)]
    assert 0.8 + s3 + 0.5 + s4 + 2.5 < FALL_S, ('the last seconds of the fall are for the wind and the ridge', s3, s4)
    print('intro2: room feed %.1f-%.1f s, shot at %.2f s, fall from %.1f s, total %.1f s' % (S['s1'] - d0, t, S['bang'], t, t + FALL_S))
    # (ss-judge A2/A3, orchestrator 11-14: the level beds are off in cutscenes and the intro was voices over dead air. The originals' recipe (L16 3950
    #  'SoundFX'): AmbientAreas inside the cutscene container. One per bed, around the camera keys of its own shots, on only in its window:
    #  HQ room tone under both Anya shots, video-link hiss under the hacked room feed, the storm over the fall (an AmbientArea, plus the 18.6 s storm sample once (one-shot def ss_storm1, storm_once) as a sound-only StatusMessage from the first frame of the fall: rig kr3/kr4 had the area silent for the fall's first ~9 s, positional beds round a fast sky camera start late). 4 task ids)
    t_, at_ = 0.0, []
    for k_ in ks:
        at_.append((t_, k_)); t_ += k_['dur']
    end_ = t_ + 1.0
    S['amb'] = []
    for nm_, def_, wins_, pad_, fo_ in (('SS intro HQ room tone', 'hqamb', ((0.0, S['room0']), (S['hq2'], S['fall'] + 0.7)), 6.0, 8.0),   # (+0.7 s: no dip while the storm fades in, rig kr4)
                                         ('SS intro room feed hiss', 'noise_loop', ((S['room0'], S['hq2']),), 6.0, 8.0),
                                         ('SS intro storm over the fall', 'sandstorm_wind', ((S['fall'], end_),), 40.0, 30.0)):
        pts_ = [k_['pos'] for t0_, k_ in at_ if any(a_ <= t0_ < b_ for a_, b_ in wins_)]
        lo_ = [min(p_[i_] for p_ in pts_) - pad_ * M for i_ in range(3)]; hi_ = [max(p_[i_] for p_ in pts_) + pad_ * M for i_ in range(3)]
        S['amb'].append((nm_, def_, wins_, [(l_ + h_) / 2 for l_, h_ in zip(lo_, hi_)], [(h_ - l_) / M for l_, h_ in zip(lo_, hi_)], fo_))
    return ks, caps


def stage(G):
    """the men, after CSI exists"""
    K, m, nid, CSI = G['K'], G['m'], G['nid'], G['CSI']
    lipsync, cap_msg, GCAP = G['lipsync'], G['_cap_msg'], G['_GCAP']
    tick = lambda s_: '%.2f * GAME_FREQUENCY' % s_
    cs = CSI['cs']
    box = lambda cond, name: _box(m, nid, CSI['intro'], cond, name)
    z = FLOOR * M
    p3 = lambda xy: (xy[0] * M, xy[1] * M, z)
    to = lambda xy: (xy[0] * M, xy[1] * M)
    # the colonel talks to Kral, turns to the sergeant on the cut to his own feed, and the pistol is up on the last cut
    # (judge J05: each man listens while the other talks. Phases: Kral's lines (<= s1), the colonel's lines (s1..t2), Kral's last line (t2..aim), the pistol (aim..))
    b0 = box('CutScene_%d.nTick <= %s' % (cs, tick(S['s1'])), 'SS Kral waits by the desk')
    b0a = box('CutScene_%d.nTick > %s && CutScene_%d.nTick <= %s' % (cs, tick(S['s1']), cs, tick(S['t2'])), 'SS General Dhari talks to the sergeant')
    b0b = box('CutScene_%d.nTick > %s && CutScene_%d.nTick <= %s' % (cs, tick(S['t2']), cs, tick(S['bang'])), 'SS Kral watches the shot')
    b1 = box('CutScene_%d.nTick > %s' % (cs, tick(S['aim'])), 'SS General Dhari aims')
    KRAL_SKIN = 'ssm19_1' if G.get('SOLDIERS') else 'pat_1'   # (orchestrator 11-14: pat_1 is the originals' Senator and read as Josef Priboi; ssm19_1 = Kral's own face, sssoldiers)
    COL_SKIN = 'ssm18_1' if G.get('SOLDIERS') else 'alseao_1'   # (ss-general 11-10: the colonel is the ending's older man, sssoldiers.GENERAL, one face in both scenes; assign() leaves a named new skin alone)
    K.actor(b0, p3(COL_XY), to(SGT_XY), COL_SKIN, anim='stand_pistol', weapon=PISTOL, name='intro General Dhari to the sergeant')   # (owner 11-15 S10 class, player2 N10: empty right hand on cameras 2-3, the pistol popped into it at camera 4: he holds it low from the first frame)   # (11-14 review: nobody speaks on cameras 2 and 3 now, so no talking gestures until his first line)   # (one man from the start to Kral's answer: the south camera sees Kral's line run into his, no swap in shot)
    col2 = K.actor(b1, p3(COL_XY), to(SGT_XY), COL_SKIN, anim=COL_PISTOL, weapon=PISTOL, name='intro General Dhari with the pistol')
    m.set(col2, 9, False); m.set(col2, 17, 0.35)     # (once through, then held; 0.35 s blend from the low pistol into the aim)
    K.actor(b0, p3(KRAL_XY), to(COL_XY), KRAL_SKIN, anim=LISTEN, name='intro arms broker Kral')      # (11-14: silent, he only watches)
    K.actor(b0a, p3(KRAL_XY), to(COL_XY), KRAL_SKIN, anim=LISTEN, name='intro Kral listens')
    K.actor(b0b, p3(KRAL_XY), to(COL_XY), KRAL_SKIN, anim=LISTEN, name='intro Kral waits')
    # the sergeant, hands bound, and the two men who brought him; they stay at their posts when he falls
    b2 = box('CutScene_%d.nTick <= %s' % (cs, tick(S['bang'])), 'SS the sergeant stands')
    b3 = box('CutScene_%d.nTick > %s' % (cs, tick(S['bang'])), 'SS the sergeant falls')
    m.set(K.actor(b2, p3(SGT_XY), to(HADI_FACE), SGT_SKIN, anim=HADI_POSE, name='intro sergeant Hadi'), 9, False)   # (owner 84, J06: hands on his head, played once long before he is seen, then held: no hand moves)
    K.actor(b3, p3(KRAL_XY), to(COL_XY), KRAL_SKIN, anim=LISTEN, name='intro Kral watches')
    m.set(K.actor(b3, p3(SGT_XY), to(FALL_TO), SGT_SKIN, anim='stand_die_headshot', name='intro sergeant Hadi falls'), 9, False)   # (turned away on the static frame: shot from behind he falls forward onto open floor, not onto the colonel; the last pose holds)
    try:
        import ssblood                               # (ss-general 11-10, owner 120: the engine draws no pool under a cutscene actor; a flat pool where his head lands, on when it reaches the floor)
    except ImportError:
        ssblood = None
    if ssblood and ssblood.MODEL in getattr(G['_VLIB'], 'builders', {}):   # (registered by ssgeneral.models with SS_GEN2=1; no new LOD row from here)
        ssblood.place_growing(m, CSI['intro'], nid, lambda dt: 'CutScene_%d.nTick > %s' % (cs, tick(S['bang'] + 1.9 + dt)), 50.72, 237.32, FLOOR, 2.62, name='SS intro Hadi blood pool')   # (orchestrator 11-10: it spreads, five blobs over 1.8 s; k9r: the chair seat hid half of it at (51.0, 237.2), 0.3 m toward camera 4 onto the open floor)
    # (judge H02 11-08: the guard behind Hadi stood inside him and his rifle ran into the rack, there is no free spot for a second man there: one guard, north-west
    #  of Hadi. H01: on "What have we here?" he jabs Hadi with the rifle butt, a beat in the long pan where nobody moved)
    # (owner G07 11-13: 'when he talks the soldier shouldn't move... while he kills our agent he moved his AK'. The jab is gone, and so is the double guard
    #  where b0a and b1 overlapped (s1..t2). One man for the whole scene at attention: stand_ak47 looped, the steadiest rifle stand (cutanim: 1.0 deg))
    K.actor(CSI['intro'], p3(G2_XY), to(SGT_XY), 'alarm2_1', anim='stand_ak47', weapon=RIFLE, name='intro room guard')
    for d_, a_ in (('ss_ic3', col2), ('ss_ic4', col2)):
        lipsync.link(m, cap_msg(GCAP[d_][1]), [a_])
    import atmos as _atm
    for nm_, def_, wins_, c_, sz_, fo_ in S['amb']:
        on_ = ' || '.join('(CutScene_%d.nTick > %s && CutScene_%d.nTick <= %s)' % (cs, tick(a_), cs, tick(b_)) for a_, b_ in wins_)
        _atm.ambient_sound(m, nid, CSI['intro'], nm_, c_, sz_, def_, True, True, on_, fo_)
        print('intro2: bed %s %s %.0fx%.0fx%.0f m, %s' % (def_, [round(x_ / M, 1) for x_ in c_], sz_[0], sz_[1], sz_[2], [(round(a_, 1), round(b_, 1)) for a_, b_ in wins_]))
    m.add_child(CSI['intro'], T(nid(), 'StatusMessage', 'SS intro storm over the fall (sound only)', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                'CutScene_%d.nTick > %s * GAME_FREQUENCY' % (cs, round(S['fall'] + 0.05, 2)), '', '', S['storm_def'], True, True, 1.0, ''))   # (a one-shot def: ends by itself, qa DT04)
    m.add_child(CSI['intro'], T(nid(), 'StatusMessage', 'SS intro the shot', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,   # (the pistol: no caption, sound only)
                                'CutScene_%d.nTick > %s * GAME_FREQUENCY' % (cs, round(S['shot_snd'], 2)), '', '', 'ss_ic5', True, True, 1.0, ''))
    # the two pickets on the ridge
    pk = [G['SQUAD_IDS'][k_][1][0] for k_ in ('S landing zone pickets', 'S ridge mate')]
    pos = [tuple(float(G['lit'](m.byid[h_].args[k_])) for k_ in (3, 4, 5)) for h_ in pk]
    for h_, q_, o_, clip_, sk_ in zip(pk, pos, pos[::-1], ('right_guard_talking', 'left_guard_talking'), ('alarm1_1', 'alarm2_1')):
        _aid = K.actor(CSI['intro'], q_, o_, sk_, anim=clip_, weapon=RIFLE, name='intro ridge picket')
        if os.environ.get('SS_LIVE_PICKETS', '1') == '1':   # (G43 11-14: the live pickets stand there from load and the intro films them; the actor keeps its id
            DROP_ACTORS.append(_aid)                        #  until every nid() is done, then the builder removes it, so no later task id shifts)
    print('intro2: ridge pickets %s m apart %.1f' % ([[round(c_ / M, 1) for c_ in q_] for q_ in pos], math.dist(pos[0], pos[1]) / M))
    video_wall(G)
    # control: his first line
    _, secs = G['orig']('cv30_camp_04_jones')
    i_ = nid()
    m.add_child(G['LOGIC'], T(i_, 'StatusMessage', 'SS Jones first line', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'LevelTimer_%d.nTick > 0.5 * GAME_FREQUENCY' % CSI['after'],
                              'SS_JONES0', '', 'cv30_camp_04_jones', True, False, max(4.0, secs + 0.5), ''))
    m.add_text('messages', 'SS_JONES0', 'JONES: Great. Just how I like it.')


def video_wall(G):
    """owner 81, pictures floating behind Hadi and the general: ssoutro stood the 3.5 m video wall free in the middle of the room, in every scene, showing Jones before he ever came.
    It belongs to the ending only, on the north wall behind Dhari, in his second camera's view. Rig plan: that wall runs (48.6, 240.85) - (51.7, 239.75), the room turned as the
    building. build_wall: the back of the frame is 0.5 m behind the origin"""
    m, lit, CSO = G['m'], G['lit'], G['CSO']
    ids = [i_ for i_ in m.find('EditRigidObj') if str(lit(m.byid[i_].args[2])) == 'SS base video wall']
    if not ids:
        return
    i_ = ids[0]
    t_ = m.byid[i_]
    for k_, c_ in ((3, WALL_P[0] * M), (4, WALL_P[1] * M), (5, WALL_P[2] * M), (8, WALL_G)):
        m.set(i_, k_, float(c_))
    m.parent[i_].args.remove(t_)
    m.add_child(CSO['outro'], t_)                  # (no box of its own: the ids 402-2753 are nearly all used)
    print('intro2: video wall on the north wall %s, ending only' % (WALL_P,))


def _box(m, nid, parent, cond, name):
    b = nid()
    m.add_child(parent, T(b, 'ConditionalContainer', name, cond, '', ''))
    return b


def picket(G):
    """a second man beside the ridge picket: the teaser's pair. Own rng state, so no other squad moves"""
    m, sid = G['m'], G['SQUAD_IDS']['S landing zone pickets'][1][0]
    lit = G['lit']
    p = [float(lit(m.byid[sid].args[k_])) for k_ in (3, 4, 5)]
    st = m.rng.getstate()
    weather.hearing(0.4)                           # (a canyon sentry like the rest of this section, not the sniper template)
    G['squad']('S ridge mate', 1, (p[0], p[1]), 11000.0, [G['AK']], G['C2N'], G['LES'], zlo=p[2] - 2.5 * M, zhi=p[2] + 2.5 * M, where='out', patrol=0.0, spacing=2500.0)
    weather.hearing(None)
    m.rng.setstate(st)
    q = [float(lit(m.byid[G['SQUAD_IDS']['S ridge mate'][1][0]].args[k_])) for k_ in (3, 4, 5)]
    S_ = G['START']
    G['PICKET_MID'] = ((p[0] + q[0]) / 2.0 / M - S_[0] / M, (p[1] + q[1]) / 2.0 / M - S_[1] / M, (p[2] + q[2]) / 2.0 / M + 1.3 - EYE_H)   # (m from his eyes; the ground at START is 0.06 m)
