"""Radio voice-over lines from Windows' built-in text-to-speech (System.Speech, offline - nothing downloaded).

  make(lines, out_dir, rate=22050)   lines = {key: (voice, text)}  voice = 'Zira' (Anya) | 'David' | 'Mark'
  -> out_dir/<key>.wav  (16-bit mono PCM), processed to sound like a field radio:
     band-pass 300-3400 Hz, soft clipping, low static floor, squelch clicks at both ends.
"""
import os, subprocess, tempfile, wave
import numpy as np

PS = r'''
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({rate}, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SelectVoice('Microsoft {voice} Desktop')
$s.Rate = {speed}
$s.SetOutputToWaveFile('{path}', $fmt)
$s.Speak([IO.File]::ReadAllText('{text_path}'))
$s.Dispose()
'''


def tts(voice, text, path, rate=22050, speed=0):
    with tempfile.TemporaryDirectory() as td:
        tp = os.path.join(td, 'line.txt')
        open(tp, 'w', encoding='utf-8').write(text)
        script = PS.format(rate=rate, voice=voice, speed=speed, path=path.replace("'", "''"), text_path=tp.replace("'", "''"))
        sp = os.path.join(td, 'say.ps1')
        open(sp, 'w', encoding='utf-8-sig').write(script)
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', sp], check=True, capture_output=True)


def _read(path):
    w = wave.open(path, 'rb')
    rate, n = w.getframerate(), w.getnframes()
    x = np.frombuffer(w.readframes(n), '<i2').astype(np.float64) / 32768.0
    w.close()
    return x, rate


def _write(path, x, rate):
    y = (np.clip(x, -1, 1) * 32767).astype('<i2')
    w = wave.open(path, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    w.writeframes(y.tobytes()); w.close()


def _bandpass(x, rate, lo=300.0, hi=3400.0):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / rate)
    g = 1.0 / np.sqrt(1 + (lo / np.maximum(f, 1)) ** 4) / np.sqrt(1 + (f / hi) ** 8)
    return np.fft.irfft(X * g, len(x))


def radio(x, rate, seed=0, drive=2.2):
    rng = np.random.default_rng(seed)
    x = x / max(1e-6, np.abs(x).max())
    y = _bandpass(x, rate)
    y = np.tanh(drive * y) / np.tanh(drive)                  # soft clipping: overdriven handset
    pad = int(0.12 * rate)
    y = np.concatenate([np.zeros(pad), y, np.zeros(pad)])
    hiss = _bandpass(rng.normal(0, 1, len(y)), rate, 900, 3200)
    y = y * 0.85 + hiss / max(1e-6, np.abs(hiss).max()) * 0.035
    for at in (0, len(y) - int(0.06 * rate)):                # squelch: short bursts of static at key-up / key-down
        n = int(0.06 * rate)
        y[at:at + n] += _bandpass(rng.normal(0, 1, n), rate, 1200, 3400) * np.linspace(0.35, 0.05, n)
    return np.clip(y / max(1e-6, np.abs(y).max()) * 0.9, -1, 1)


# ---------------------------------------------------------------------------- Kokoro (neural TTS, offline, Apache-2.0)
# owner 10-13 ('try a better free voice engine than SAPI'): Kokoro-82M through kokoro-onnx (pip, Apache-2.0; model files
# kokoro-v1.0.onnx + voices-v1.0.bin from github.com/thewh1teagle/kokoro-onnx/releases, downloaded 10-13 into
# work/blackice/dl/kokoro/). Each SAPI voice name maps to a Kokoro voice; unknown names fall back to SAPI.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOKORO_DIR = os.path.join(ROOT, 'work', 'blackice', 'dl', 'kokoro')
KOKORO_VOICES = {'Zira': 'af_heart',      # Anya
                 'David': 'am_michael',   # pilots, soldiers, Kestrel, Jones
                 'Mark': 'bm_george',     # Volkov, Hale
                 'Elena': 'bf_emma', 'Soldier': 'am_adam', 'Jones': 'am_onyx', 'Pilot': 'bm_daniel', 'Driver': 'am_eric'}
# owner 10-23 ('AI voice of Anya and Jones - clone the originals or better ones'): no cloning of the actors; Kokoro style
# vectors blended toward the ORIGINAL game's Anya / Jones by pitch + band-limited timbre (work/sirocco/voice/match.py over
# 119 original clips). 'Anya' = her radio voice (a lighter radio filter), 'AnyaHQ' / 'DJones' = in person (no radio filter)
KOKORO_BLENDS = {'Anya': ('af_jessica', 0.65, 'bf_alice'), 'AnyaHQ': ('af_jessica', 0.65, 'bf_alice'),
                 'DJones': ('am_fenrir', 0.5, 'am_liam')}
RAW_VOICES = {'AnyaHQ', 'DJones'}
RADIO_DRIVE = {'Anya': 1.3}
ENGINE = os.environ.get('VOICE_ENGINE', 'kokoro')
_K = [None]


def kokoro_available():
    try:
        import kokoro_onnx, soundfile  # noqa
    except ImportError:
        return False
    return os.path.exists(os.path.join(KOKORO_DIR, 'kokoro-v1.0.onnx')) and os.path.exists(os.path.join(KOKORO_DIR, 'voices-v1.0.bin'))


def engine_for(voice):
    return 'kokoro' if ENGINE == 'kokoro' and (voice in KOKORO_VOICES or voice in KOKORO_BLENDS) and kokoro_available() else 'sapi'


def tts_kokoro(voice, text, path, rate=22050, speed=0):
    import soundfile as sf
    from kokoro_onnx import Kokoro
    if _K[0] is None:
        _K[0] = Kokoro(os.path.join(KOKORO_DIR, 'kokoro-v1.0.onnx'), os.path.join(KOKORO_DIR, 'voices-v1.0.bin'))
    if voice in KOKORO_BLENDS:                                # (a blend of two style vectors)
        a_, w_, b_ = KOKORO_BLENDS[voice]
        V_ = np.load(os.path.join(KOKORO_DIR, 'voices-v1.0.bin'))
        kv = (w_ * V_[a_] + (1.0 - w_) * V_[b_]).astype(np.float32)
        lang_ = 'en-gb' if a_[0] == 'b' else 'en-us'
    else:
        kv = KOKORO_VOICES[voice]
        lang_ = 'en-gb' if kv[0] == 'b' else 'en-us'
    s, sr = _K[0].create(text, voice=kv, speed=1.0 + 0.08 * speed, lang=lang_)
    s = np.asarray(s, np.float64)
    if sr != rate:                                            # resample to the game rate (linear: speech, band-limited later)
        n = int(round(len(s) * rate / sr))
        s = np.interp(np.linspace(0, len(s) - 1, n), np.arange(len(s)), s)
    _write(path, s / max(1e-6, np.abs(s).max()) * 0.9, rate)


def make(lines, out_dir, rate=22050, speed=0, raw=False, chain=None):
    """lines = {key: (voice, text)} -> {key: out_dir/<key>.wav}.  chain = None (auto: radio_chain(voice, raw)) | 'r2' |
    'r1' | 'raw'.  (10-29: the dry TTS is cached in work/voice_cache/dry, so a new filter never re-synthesizes.)"""
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    for k, (key, (voice, text)) in enumerate(sorted(lines.items())):
        path = os.path.join(out_dir, key + '.wav')
        ch = chain or radio_chain(voice, raw)
        x, r = _read(dry_tts(voice, text, rate, speed))
        if ch == 'r2':
            x = radio2(x, r, seed=k, drive=min(R2_DRIVE_MAX, RADIO_DRIVE.get(voice, R2_DRIVE_MAX)))
        elif ch == 'r1':
            x = radio(x, r, seed=k, drive=RADIO_DRIVE.get(voice, 2.2))
        _write(path, x, r)
        out[key] = path
    return out


def dry_tts(voice, text, rate=22050, speed=0):
    """the unfiltered TTS line (Kokoro or SAPI, as engine_for(voice)), cached by engine + voice + text + speed + rate in
    work/voice_cache/dry (written atomically: several builders share the cache)"""
    import hashlib
    eng = engine_for(voice)
    vdef = KOKORO_BLENDS.get(voice) or KOKORO_VOICES.get(voice) if eng == 'kokoro' else SAPI_FOR.get(voice, voice)
    h = hashlib.sha1(('dry|%s|%s|%s|%s|%s|%d' % (eng, voice, vdef, text, speed, rate)).encode()).hexdigest()[:16]   # (review:
    # the voice's DEFINITION is in the key - a retuned blend gives new audio)
    d = os.path.join(ROOT, 'work', 'voice_cache', 'dry')
    path = os.path.join(d, '%s_%s.wav' % (eng, h))
    if not os.path.exists(path):
        os.makedirs(d, exist_ok=True)
        tmp = path[:-4] + '.%d.tmp.wav' % os.getpid()
        if eng == 'kokoro':
            tts_kokoro(voice, text, tmp, rate, speed)
        else:
            tts(SAPI_FOR.get(voice, voice if voice in ('Zira', 'David', 'Mark') else ('Zira' if voice.startswith('Anya') else 'David')),
                text, tmp, rate, speed)
        safe_replace(tmp, path)
    return path


def safe_replace(tmp, dst):
    """os.replace that tolerates a parallel builder: on Windows it fails while another process has dst open - if dst
    exists by then (the other builder made the same file), keep that one and drop ours"""
    try:
        os.replace(tmp, dst)
    except OSError:
        if not os.path.exists(dst):
            raise
        try:
            os.remove(tmp)
        except OSError:
            pass


# ---------------------------------------------------------------------------- the 10-29 radio chain (SHOBI rework)
# SHOBI: 'the voice acting does not feel right'. Measured (work/shobi/voice/measure.py + ltas.py, 54 ORIGINAL Anya clips
# vs the dry Kokoro 'Anya' blend): the original Anya is high-passed, BRIGHT (spectral centroid 3.3 kHz, 33 % of the
# energy above 3.4 kHz, crest 17.3 dB) over a constant hiss bed 23 dB under the loudest 20 ms frame (bed centroid 2.7 kHz);
# radio() above (300-3400 Hz telephone band, drive 2.2) gave 0.6 % above 3.4 kHz = muffled.  radio2(): 300 Hz high-pass
# (4th order) + the measured tonal EQ (1/3-octave, relative to 1 kHz) + 6 kHz low-pass + tanh drive <= 1.3 + the hiss bed
# + the squelch clicks.  Default for every Kokoro radio voice of missions 1-4 (R2_MISSIONS: 'Anya', 'Zira', 'Pilot', ...);
# SAPI voices and the other missions keep radio(); VOICE_RADIO=r1 = the old chain everywhere, r2all = r2 everywhere.
# In-person voices (RAW_VOICES, raw=True) stay unfiltered.
RADIO_CHAIN = os.environ.get('VOICE_RADIO', 'r2')
R2_DRIVE_MAX = 1.3
R2_LP_ORDER = 2                                           # 12 dB/oct above 6 kHz (the original keeps some air)
R2_COMP = 2.5                                             # leveller ratio (crest 19.4 -> 18.5 dB; the original 17.3)
R2_VERSION = 1                                            # bump after any change of radio2(): it is in the K.vo cache key
R2_VOICES = set()                                         # opt-in by name for non-Kokoro voices (none by default)
SAPI_FOR = {}                                             # SAPI fallback name for blend voices (default: Zira / David)
KOKORO_BLENDS['DJonesRadio'] = KOKORO_BLENDS['DJones']    # Jones heard over the radio (filtered); 'DJones' = in person
EQ_R2 = [(112, -7.3), (141, -7.3), (178, -7.3), (224, -7.3), (283, -7.3), (356, -7.3), (449, -8.1), (566, -6.4), (713, -2.7),
         (898, -0.3), (1131, 0.3), (1425, 1.6), (1796, 4.3), (2263, 6.6), (2851, 7.6), (3592, 8.5), (4525, 9.8), (5702, 10.0),
         (7184, 10.0), (9051, 10.0)]   # dB, fitted (work/shobi/voice/fit_eq.py): in-band (330-5800 Hz) error 1.2 dB vs the
                                       # ORIGINAL Anya; result <300 Hz 1.3 % / >3.4 kHz 21 % (orig 2.8 / 33, old radio() 0.6 %),
                                       # centroid 2.5 kHz (orig 3.3, old 0.7), crest 18.5 dB (17.3), bed -22.7 dB (-23.1)
HISS_R2 = [(356, 0.0), (449, -0.1), (566, 0.2), (713, -0.5), (898, -1.7), (1131, -2.3), (1425, -2.4), (1796, -2.2), (2263, -1.2),
           (2851, -2.2), (3592, -3.5), (4525, -3.7), (5702, -3.2), (7184, -3.5), (9051, -3.7)]   # the original bed's shape


R2_MISSIONS = {19, 30, 20, 27}                            # the SHOBI rework (M1-M4); other missions keep radio() unless
                                                          # VOICE_RADIO=r2all (review 10-29: M5-M12 must not change silently)


def radio_chain(voice, raw=False, mission_id=None):
    """'raw' (in person: raw=True or RAW_VOICES) | 'r2' (Kokoro radio voices of R2_MISSIONS - or of every mission with
    VOICE_RADIO=r2all - and R2_VOICES) | 'r1' (the old radio(): SAPI voices, other missions, VOICE_RADIO=r1)"""
    if raw or voice in RAW_VOICES:
        return 'raw'
    if voice in R2_VOICES:
        return 'r2'
    if engine_for(voice) == 'kokoro' and (RADIO_CHAIN == 'r2all' or (RADIO_CHAIN == 'r2' and mission_id in R2_MISSIONS)):
        return 'r2'
    return 'r1'


def r2_tag():
    """the radio2 settings as a short tag for cache keys (any retune of the tables / leveller / drive = new files)"""
    import hashlib
    return 'r2v%d.%s' % (R2_VERSION, hashlib.sha1(repr((EQ_R2, HISS_R2, R2_COMP, R2_LP_ORDER, R2_DRIVE_MAX)).encode()).hexdigest()[:6])


def _level(y, rate, ratio=2.0, thr_db=-18.0, att_s=0.002, rel_s=0.10):
    """a gentle feed-forward leveller (peak envelope, attack / release) - the originals' crest is ~17 dB"""
    a_, r_ = np.exp(-1.0 / (att_s * rate)), np.exp(-1.0 / (rel_s * rate))
    ax = np.abs(y)
    env = np.empty_like(ax)
    e = 0.0
    for i, v in enumerate(ax):                               # (one pass, ~0.1 s per line in numpy-free python: fine for TTS)
        e = a_ * e + (1 - a_) * v if v > e else r_ * e + (1 - r_) * v
        env[i] = e
    pk = max(1e-9, float(env.max()))
    lev = 20 * np.log10(np.maximum(env, 1e-9) / pk)
    over = np.maximum(0.0, lev - thr_db)
    g = 10 ** (-(over - over / ratio) / 20.0)
    out = y * g
    return out / max(1e-6, np.abs(out).max())


def _table_gain(f, table):
    c = np.log(np.array([a for a, _ in table], float))
    g = np.array([b for _, b in table], float)
    return 10.0 ** (np.interp(np.log(np.maximum(f, 1.0)), c, g) / 20.0)


def radio2(x, rate, seed=0, drive=1.3, hp=300.0, lp=6000.0, hiss_db=-23.0, eq=True, squelch=True, lp_order=R2_LP_ORDER,
           comp=R2_COMP):
    """the 10-29 radio chain (see above): x float mono -> float mono, peak 0.9, 0.12 s longer at both ends"""
    rng = np.random.default_rng(seed)
    x = np.asarray(x, np.float64)
    x = x / max(1e-6, np.abs(x).max())
    pad = int(0.12 * rate)
    x = np.concatenate([np.zeros(pad), x, np.zeros(pad)])
    f = np.fft.rfftfreq(len(x), 1.0 / rate)
    band = 1.0 / np.sqrt(1 + (hp / np.maximum(f, 1.0)) ** 8) / np.sqrt(1 + (f / lp) ** (2 * lp_order))
    y = np.fft.irfft(np.fft.rfft(x) * band * (_table_gain(f, EQ_R2) if eq else 1.0), len(x))
    y = y / max(1e-6, np.abs(y).max())
    if comp:                                                 # a gentle leveller: 2:1 above -14 dB of the peak envelope
        y = _level(y, rate, ratio=comp)
    y = np.tanh(drive * y) / np.tanh(drive)                  # a gentle overdrive (<= 1.3)
    n = int(0.02 * rate)
    fr = y[:len(y) // n * n].reshape(-1, n)
    peak = float(np.sqrt((fr ** 2).mean(1)).max())
    hband = 1.0 / np.sqrt(1 + (hp / np.maximum(f, 1.0)) ** 8) / np.sqrt(1 + (f / lp) ** 8)    # (bed: 4th-order LP)
    hiss = np.fft.irfft(np.fft.rfft(rng.normal(0, 1, len(y))) * hband * _table_gain(f, HISS_R2), len(y))
    hiss *= peak * 10 ** (hiss_db / 20.0) / max(1e-9, float(np.sqrt((hiss ** 2).mean())))
    y = y + hiss
    if squelch:                                              # key-up / key-down: a short burst of static at both ends
        m = int(0.06 * rate)
        for at in (0, len(y) - m):
            b = np.fft.irfft(np.fft.rfft(rng.normal(0, 1, m)) * _table_gain(np.fft.rfftfreq(m, 1.0 / rate),
                                                                            [(900, -30), (1500, 0), (3500, 0), (5000, -30)]), m)
            y[at:at + m] += b / max(1e-9, np.abs(b).max()) * 0.3 * np.linspace(1.0, 0.15, m)
    return np.clip(y / max(1e-6, np.abs(y).max()) * 0.9, -1, 1)


# ---------------------------------------------------------------------------- recorded lines (voice actors, Neonix)
ACTORS = os.path.join(ROOT, 'work', 'voice_actors')
# ss-int 11-15: a Sandstorm build (build_sandstorm.py is __main__) reads the FROZEN intro voices, as the release trees did since 11-14
# (relbuild52 = installed rc7s25); the live work/voice_actors/sandstorm is mid-rework. SS_LIVE_ACTORS=1 builds with the live takes.
if (os.path.basename(getattr(__import__('sys').modules.get('__main__'), '__file__', '') or '') == 'build_sandstorm.py'
        and not os.environ.get('SS_LIVE_ACTORS')):
    ACTORS = os.path.join(ROOT, 'work', 'sandstorm', 'freeze', 'voice_actors_rc7s17')
MISSION_DIRS = {19: ('sandstorm',), 30: ('sirocco',), 20: ('cedar', 'atlas'), 27: ('frostbite',)}


def actor_wav(name, build=None, mission_id=None):
    """a recorded line for voice def `name`: work/voice_actors/<build name>/<name>.wav (build = the Kit folder without
    '_sp', e.g. 'atlas'), the mission's short name (MISSION_DIRS: 'cedar' for 20), or flat work/voice_actors/<name>.wav
    -> path or None"""
    dirs = []
    if build:
        dirs.append(os.path.join(ACTORS, build))
    for d in MISSION_DIRS.get(mission_id, ()):
        dirs.append(os.path.join(ACTORS, d))
    dirs.append(ACTORS)
    for d in dirs:
        p = os.path.join(d, name + '.wav')
        if os.path.isfile(p):
            return p
    return None


def read_any(path, rate=22050):
    """a WAV of any common format (16/24/32-bit PCM or float, mono or stereo, any rate) -> (float mono, rate)"""
    try:
        import soundfile as sf
        x, r = sf.read(path, dtype='float64', always_2d=True)
        x = x.mean(1)
    except Exception:
        w = wave.open(path, 'rb')
        r, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
        w.close()
        assert sw == 2, '%s: %d-bit PCM (use 16-bit PCM)' % (path, sw * 8)
        x = np.frombuffer(raw, '<i2').astype(np.float64) / 32768.0
        if ch > 1:
            x = x.reshape(-1, ch).mean(1)
    if r != rate:
        try:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(r), int(rate))
            x = resample_poly(x, rate // g, int(r) // g)
        except Exception:
            x = np.interp(np.linspace(0, len(x) - 1, int(round(len(x) * rate / r))), np.arange(len(x)), x)
    return np.asarray(x, np.float64), rate


def recorded(src, dst, chain='r2', rate=22050, seed=0):
    """a voice actor's line -> the game format (16-bit PCM mono 22050 Hz): DC removed, 30 ms fades, peak 0.9, then the
    radio chain for radio speakers ('r2' / 'r1'; 'raw' = in person, unfiltered) -> seconds"""
    x, r = read_any(src, rate)
    x = x - float(np.mean(x))
    fd = min(len(x) // 4, int(0.03 * r))
    if fd > 0:
        x[:fd] *= np.linspace(0, 1, fd)
        x[-fd:] *= np.linspace(1, 0, fd)
    x = x / max(1e-6, np.abs(x).max()) * 0.9
    if chain == 'r2':
        x = radio2(x, r, seed=seed)
    elif chain == 'r1':
        x = radio(x, r, seed=seed, drive=1.3)
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    tmp = dst[:-4] + '.%d.tmp.wav' % os.getpid()
    _write(tmp, x, r)
    safe_replace(tmp, dst)
    return len(x) / float(r)


def take_text(rec):
    """the text a recorded take was recorded for: work/voice_actors/<mission>/_script.json {def: text} written by
    tools/voicescript.py next to the takes -> text or None (no sheet there)"""
    import json
    p = os.path.join(os.path.dirname(rec), '_script.json')
    try:
        return json.load(open(p, encoding='utf-8')).get(os.path.basename(rec)[:-4])
    except Exception:
        return None


if __name__ == '__main__':
    import sys
    p = make({'test_anya': ('Zira', sys.argv[1] if len(sys.argv) > 1 else 'Jones, this is Anya. Do you read me?')},
             os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'voice'))
    x, r = _read(p['test_anya'])
    print(p['test_anya'], '%.2f s at %d Hz' % (len(x) / r, r))
