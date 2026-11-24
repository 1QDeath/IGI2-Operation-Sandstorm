"""itskins - NEW character skins for Operation Iron Tsar (owner 10-13 standing rule: new soldier skins and faces).

Same recipe as tools/skinforge.py (Black Ice): a skin = a VNAM whose INST reuses a shipped character MESH with new
textures PAINTED over the layout of the shipped ones (their luminance = the folds and seams), nothing copied in.

  Chinese mercenaries, winter   (mesh chn_1: body 2048^2 'ch_chn_01' layout, head 512x1024 'ch_chn_02' layout)
    itmc1_1  snow camouflage (white / grey splinter), white fur cap, a young face
    itmc2_1  dark blue-grey padded uniform, brown fur cap, a broad stubbled face
    itmc3_1  olive padded uniform with grey blotches, dark fur cap, a lean older face
  Volkov's Russian bodyguards   (mesh resg_1: body 'ch_resg_01', head 'ch_resg_00' - skinforge's layout notes)
    itbg1_1  itbg2_1  black winter combat uniforms, black watch caps, two faces
  itvol_1   General Arkady Volkov: grey-green general's greatcoat, gold shoulder boards, grey papakha, old face, moustache
  itkes_1   the Kestrel envoy: black civilian overcoat, a black knit mask with only the eyes showing

    import itskins
    itskins.add_skins(overlay_dir, 'chinesetemple')
    itskins.NAMES
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, wreck
import skinforge as SF

GAME = wreck.GAME
MERCS = ['itmc1_1', 'itmc2_1', 'itmc3_1']
GUARDS = ['itbg1_1', 'itbg2_1']
VOLKOV = 'itvol_1'
ENVOY = 'itkes_1'
NAMES = MERCS + GUARDS + [VOLKOV, ENVOY]

_lum, _noise, _rect, recolor, _soft = SF._lum, SF._noise, SF._rect, SF.recolor, SF._soft_ellipse


def camo(img, sl, cols, rng, scale=6, keep_shading=0.85):
    """winter camouflage over region sl: cols = [base, blotch1, blotch2] picked by two noise fields; keeps the shading"""
    reg = img[sl]
    L = _lum(reg)
    sh = (1 - keep_shading) + keep_shading * np.clip(L / max(1e-6, float(np.percentile(L, 90))), 0, 1.3)
    h, w = reg.shape[:2]
    n1 = _noise(h, w, rng, scale=scale, octaves=3)
    n2 = _noise(h, w, rng, scale=scale * 2, octaves=2)
    col = np.empty((h, w, 3))
    col[:] = cols[0]
    col[n1 > 0.58] = cols[1]
    if len(cols) > 2:
        col[(n2 > 0.62) & (n1 <= 0.58)] = cols[2]
    reg[..., :3] = np.clip(col * sh[..., None], 0, 1)
    return img


# ------------------------------------------------------------------------------------------------ chn body (ch_chn_01 layout)
# (dumped work/irontsar6/skins/ch_chn_01s.png, fractions of the 2048^2 sheet):
#   shirt with webbing straps x 0..0.60 y 0..0.45   trousers x 0..0.57 y 0.45..0.88   bottom strip x 0..0.57 y 0.88..1
#   pocket x 0.60..0.83 y 0.07..0.30   crotch x 0.60..0.83 y 0.30..0.50   bare torso x 0.83..1 y 0.17..0.50
#   hands x 0.87..0.97 y 0.07..0.165 (kept)   boot x 0.59..0.76 y 0.50..0.68 (kept)   cloth x 0.76..1 y 0.50..0.68
#   lower right trousers x 0.57..1 y 0.68..1
MERC_KIT = [
    dict(cols=[(0.80, 0.82, 0.84), (0.58, 0.60, 0.63), (0.40, 0.42, 0.44)], scale=5, hat=(0.86, 0.85, 0.82)),    # snow camo
    dict(cols=[(0.24, 0.27, 0.33), (0.21, 0.24, 0.30)], scale=9, hat=(0.36, 0.25, 0.16)),                         # blue-grey padded
    dict(cols=[(0.33, 0.34, 0.24), (0.47, 0.48, 0.45), (0.24, 0.25, 0.18)], scale=7, hat=(0.14, 0.12, 0.11)),     # olive + grey
]


def merc_body(k):
    rng = np.random.default_rng(600 + k)
    img = SF.shipped('ch_chn_01').copy()
    kit = MERC_KIT[k]
    for box in ((0.0, 0.0, 0.60, 0.45), (0.0, 0.45, 0.57, 0.88), (0.20, 0.88, 0.57, 1.0), (0.60, 0.07, 0.83, 0.30),
                (0.60, 0.30, 0.83, 0.50), (0.83, 0.17, 1.0, 0.50), (0.76, 0.50, 1.0, 0.68), (0.57, 0.68, 1.0, 1.0)):
        camo(img, _rect(img, *box), kit['cols'], rng, scale=kit['scale'])
    # quilting on the padded jacket (the shirt region): soft horizontal seams every ~5 % of the sheet
    H, W = img.shape[:2]
    if k in (1, 2):
        ys = np.arange(int(0.03 * H), int(0.45 * H), int(0.05 * H))
        for y in ys:
            img[y:y + 6, 0:int(0.60 * W), :3] *= 0.72
    # the webbing straps of the shirt keep their darker shading; snow dust on the shoulders
    n = _noise(int(0.07 * H), int(0.60 * W), rng, scale=4)
    a_ = np.clip((n - 0.6) / 0.2, 0, 1)[..., None] * 0.5
    img[0:int(0.07 * H), 0:int(0.60 * W), :3] = img[0:int(0.07 * H), 0:int(0.60 * W), :3] * (1 - a_) + a_ * np.array([0.9, 0.92, 0.96])
    # dark wool gloves over the hands (winter)
    recolor(img, _rect(img, 0.87, 0.07, 0.97, 0.165), (0.17, 0.16, 0.15), keep_shading=0.8)
    return img


MERC_FACES = [((0.86, 0.74, 0.60), 0.0, 0.0, 0.40, (0.92, 0.96, 0.95, 0.90)),
              ((0.78, 0.64, 0.50), 0.70, 0.4, 0.55, (1.10, 1.02, 1.0, 1.08)),
              ((0.82, 0.68, 0.54), 0.20, 0.8, 0.50, (0.95, 1.05, 1.10, 0.93))]


def merc_head(k):
    """ch_chn_02 layout (512 rows x 1024 cols, face mirrored about x 0.5): black hair band y 0..0.13, ears x ~0.24 / 0.77,
    the face y 0.13..0.72, the shoulders / collar below 0.70. -> a new face (warp, tone, stubble, brows, age) + a fur cap
    with ear flaps over the hair and ears + a fur coat collar over the neck"""
    rng = np.random.default_rng(700 + k)
    img = SF.shipped('ch_chn_02').copy()
    H, W = img.shape[:2]
    tone, beard, age, brow, geo = MERC_FACES[k]
    orig_L = _lum(img).copy()
    SF._warp_face(img, *geo, y0=0.13, y1=0.88)
    sk = _rect(img, 0.0, 0.13, 1.0, 0.88)
    reg = img[sk]
    L = _lum(reg)[..., None]
    reg[..., :3] = np.clip(np.asarray(tone)[None, None, :] * (0.32 + 0.98 * L / max(1e-6, float(np.percentile(L, 92)))), 0, 1)
    img[sk] = reg
    if beard > 0:                                         # stubble round the jaw (mouth ~ y 0.67, x 0.5)
        m_ = _soft(H, W, 0.72 * H, 0.5 * W, 0.13 * H, 0.20 * W, 0.5) - _soft(H, W, 0.68 * H, 0.5 * W, 0.025 * H, 0.06 * W, 0.6)
        a = np.clip(m_, 0, 1) * (0.55 + 0.45 * _noise(H, W, rng, scale=1, octaves=2)) * beard
        img[..., :3] = img[..., :3] * (1 - 0.7 * a[..., None]) + 0.07 * a[..., None]
    for xc in (0.43, 0.57):                               # brows (eyes ~ y 0.24)
        e_ = _soft(H, W, 0.19 * H, xc * W, 0.012 * H * (1 + brow), 0.05 * W, 0.7)
        img[..., :3] *= 1 - 0.6 * brow * e_[..., None]
    if age > 0:
        for xc in (0.42, 0.58):
            f_ = _soft(H, W, 0.58 * H, xc * W, 0.09 * H, 0.006 * W, 0.8)
            img[..., :3] *= 1 - 0.35 * age * f_[..., None]
        for yc in (0.08, 0.11):
            f_ = _soft(H, W, (yc + 0.04) * H, 0.5 * W, 0.004 * H, 0.10 * W, 0.8)
            img[..., :3] *= 1 - 0.25 * age * f_[..., None]
    # the fur cap: over the hair band, flaps down over the ears (x < 0.30, x > 0.70 down to y 0.42)
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    edge = 0.135 + np.where((xx < 0.30) | (xx > 0.70), 0.29, 0.0)
    a = np.clip((edge - yy) / 0.014, 0, 1)
    fur = np.asarray(MERC_KIT[k]['hat'])[None, None, :] * (0.6 + 0.65 * _noise(H, W, rng, scale=2, octaves=3))[..., None]
    img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.clip(fur, 0, 1) * a[..., None]
    st = _soft(H, W, 0.06 * H, 0.5 * W, 18, 18, 0.3)             # the cap badge: a red star
    img[..., :3] = img[..., :3] * (1 - st[..., None]) + np.array([0.80, 0.12, 0.10]) * st[..., None]
    # the fur collar over the neck / shoulders (the black band at the bottom and the bare sides)
    from scipy import ndimage as _nd
    dark = _nd.gaussian_filter(((orig_L < 0.10) & (yy > 0.62)).astype(float), 3.0)      # the shipped black collar band
    col = np.clip(dark * 1.6 + np.clip((yy - 0.40) / 0.05, 0, 1) * ((xx < 0.15) | (xx > 0.85)), 0, 1)
    collar = np.asarray(MERC_KIT[k]['hat'])[None, None, :] * 0.8 * (0.6 + 0.6 * _noise(H, W, rng, scale=2, octaves=2))[..., None]
    img[..., :3] = img[..., :3] * (1 - col[..., None]) + np.clip(collar, 0, 1) * col[..., None]
    return img


# ------------------------------------------------------------------------------------------------ resg bodies (skinforge layout notes)
def resg_body(kind, seed):
    """kind 'guard' black winter combat dress | 'general' Volkov's greatcoat | 'envoy' black civilian overcoat"""
    rng = np.random.default_rng(seed)
    img = SF.shipped('ch_resg_01').copy()
    H, W = img.shape[:2]
    cloth = {'guard': (0.10, 0.10, 0.11), 'general': (0.30, 0.32, 0.27), 'envoy': (0.07, 0.07, 0.08)}[kind]
    wool = {'guard': 0.25, 'general': 0.35, 'envoy': 0.15}[kind]
    for box in ((0.0, 0.0, 0.59, 0.44), (0.0, 0.44, 0.56, 1.0), (0.56, 0.44, 0.80, 0.83)):
        recolor(img, _rect(img, *box), cloth, keep_shading=0.85, rng=rng, wool=wool)
    if kind == 'general':
        for k in range(6):                                # gold buttons, two rows
            y = int((0.06 + 0.06 * k) * H)
            for x in (int(0.265 * W), int(0.325 * W)):
                img[y - 6:y + 6, x - 6:x + 6, :3] = (0.85, 0.72, 0.30)
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.55, 0.45, 0.20)    # the gold parade belt
        img[0:int(0.025 * H), int(0.12 * W):int(0.47 * W), :3] = (0.62, 0.10, 0.10)  # red collar tabs
        for x0 in (0.02, 0.46):                           # broad gold shoulder boards with red edging
            img[int(0.03 * H):int(0.075 * H), int(x0 * W):int((x0 + 0.11) * W), :3] = (0.82, 0.68, 0.26)
            img[int(0.03 * H):int(0.034 * H), int(x0 * W):int((x0 + 0.11) * W), :3] = (0.62, 0.10, 0.10)
        recolor(img, _rect(img, 0.75, 0.83, 1.0, 1.0), (0.06, 0.05, 0.05), keep_shading=0.6)      # polished boots
    elif kind == 'guard':
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] = (0.05, 0.05, 0.05)    # a black webbing belt
        for x in (0.10, 0.19, 0.40, 0.49):               # magazine pouches on the chest
            img[int(0.20 * H):int(0.30 * H), int(x * W):int((x + 0.06) * W), :3] *= 0.6
        recolor(img, _rect(img, 0.75, 0.83, 1.0, 1.0), (0.09, 0.08, 0.08), keep_shading=0.7)
    else:
        img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] *= 0.7               # the coat's own belt, no buckle
        recolor(img, _rect(img, 0.75, 0.83, 1.0, 1.0), (0.05, 0.05, 0.05), keep_shading=0.5)
    n = _noise(int(0.08 * H), int(0.59 * W), rng, scale=4)      # snow dust on the shoulders
    a_ = np.clip((n - 0.62) / 0.2, 0, 1)[..., None] * 0.45
    img[0:int(0.08 * H), 0:int(0.59 * W), :3] = img[0:int(0.08 * H), 0:int(0.59 * W), :3] * (1 - a_) + a_ * np.array([0.9, 0.92, 0.96])
    recolor(img, _rect(img, 0.82, 0.33, 1.0, 0.44), (0.08, 0.07, 0.07) if kind != 'general' else (0.30, 0.22, 0.14), keep_shading=0.8)
    return img


RESG_FACES = {'bg1': ((0.84, 0.66, 0.56), 0.6, 0.2, 0.55, (1.08, 0.98, 1.0, 1.04)),
              'bg2': ((0.88, 0.70, 0.60), 0.0, 0.1, 0.35, (0.94, 1.02, 1.06, 0.92)),
              'volkov': ((0.84, 0.64, 0.56), 0.0, 1.0, 1.0, (1.08, 0.96, 1.04, 1.10))}


def resg_head(face, hat, seed, mask=False):
    """hat 'watch' (black knit cap, no flaps) | 'papakha' (grey astrakhan, gold badge); mask = the envoy's black knit
    mask over the whole head with an eye slit"""
    rng = np.random.default_rng(seed)
    img = SF.shipped('ch_resg_00').copy()
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    if mask:
        knit = (0.06 + 0.05 * _noise(H, W, rng, scale=1, octaves=2))[..., None] * np.array([1.0, 1.0, 1.05])
        rib = (np.sin(xx * W * 0.9) > 0.6)[..., None] * 0.02
        slit = _soft(H, W, 0.335 * H, 0.5 * W, 0.045 * H, 0.16 * W, 0.25)       # the eye opening (both eyes)
        a = np.clip(1.0 - slit, 0, 1)[..., None]
        img[..., :3] = img[..., :3] * (1 - a) + np.clip(knit + rib, 0, 1) * a
        sk = slit[..., None] * 0.15                       # a little colour back in the skin round the eyes
        img[..., :3] *= 1 - sk
        return img
    if face:
        tone, beard, age, brow, geo = face
        SF._warp_face(img, *geo)
        sk = _rect(img, 0.0, 0.18, 1.0, 0.78)
        reg = img[sk]
        L = _lum(reg)[..., None]
        reg[..., :3] = np.clip(np.asarray(tone)[None, None, :] * (0.35 + 0.95 * L / max(1e-6, float(np.percentile(L, 92)))), 0, 1)
        img[sk] = reg
        if beard > 0:
            m_ = _soft(H, W, 0.62 * H, 0.5 * W, 0.13 * H, 0.17 * W, 0.5) - _soft(H, W, 0.585 * H, 0.5 * W, 0.022 * H, 0.05 * W, 0.6)
            a = np.clip(m_, 0, 1) * (0.55 + 0.45 * _noise(H, W, rng, scale=1, octaves=2)) * beard
            img[..., :3] = img[..., :3] * (1 - 0.75 * a[..., None]) + 0.08 * a[..., None]
        if hat == 'papakha':                               # Volkov: a heavy grey moustache, grey brows
            mm_ = _soft(H, W, 0.548 * H, 0.5 * W, 0.012 * H, 0.07 * W, 0.6)
            img[..., :3] = img[..., :3] * (1 - 0.85 * mm_[..., None]) + 0.55 * mm_[..., None] * np.array([0.9, 0.88, 0.85])
        for xc in (0.455, 0.545):
            e_ = _soft(H, W, 0.333 * H, xc * W, 0.006 * H * (1 + brow), 0.03 * W, 0.7)
            img[..., :3] = img[..., :3] * (1 - 0.7 * brow * e_[..., None]) + (0.35 * e_[..., None] if hat == 'papakha' else 0)
        if age > 0:
            for xc in (0.44, 0.56):
                f_ = _soft(H, W, 0.56 * H, xc * W, 0.05 * H, 0.004 * W, 0.8)
                img[..., :3] *= 1 - 0.4 * age * f_[..., None]
            for yc in (0.255, 0.275, 0.295):
                f_ = _soft(H, W, yc * H, 0.5 * W, 0.002 * H, 0.08 * W, 0.8)
                img[..., :3] *= 1 - 0.3 * age * f_[..., None]
    if hat == 'watch':
        edge = 0.235 + np.where((xx < 0.21) | (xx > 0.79), 0.08, 0.0)
        a = np.clip((edge - yy) / 0.012, 0, 1)
        knit = (0.07 + 0.05 * _noise(H, W, rng, scale=1, octaves=2))[..., None] * np.ones(3)
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + knit * a[..., None]
    else:
        edge = 0.24
        a = np.clip((edge - yy) / 0.012, 0, 1)
        curls = (0.45 + 0.35 * _noise(H, W, rng, scale=1, octaves=3))[..., None] * np.array([0.92, 0.92, 0.95])
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + curls * a[..., None]
        st = _soft(H, W, 0.10 * H, 0.5 * W, 16, 16, 0.3)
        img[..., :3] = img[..., :3] * (1 - st[..., None]) + np.array([0.85, 0.70, 0.28]) * st[..., None]
    return img


# ------------------------------------------------------------------------------------------------ registration
def _textures():
    out = {}
    for k, vn in enumerate(MERCS):
        out[vn] = [('it_mcbody%d' % k, merc_body(k)), ('it_mchead%d' % k, merc_head(k))]
    out['itbg1_1'] = [('it_bgbody', resg_body('guard', 801)), ('it_bghead1', resg_head(RESG_FACES['bg1'], 'watch', 811))]
    out['itbg2_1'] = [('it_bgbody', None), ('it_bghead2', resg_head(RESG_FACES['bg2'], 'watch', 812))]
    out[VOLKOV] = [('it_volbody', resg_body('general', 821)), ('it_volhead', resg_head(RESG_FACES['volkov'], 'papakha', 822))]
    out[ENVOY] = [('it_kesbody', resg_body('envoy', 831)), ('it_keshead', resg_head(None, None, 832, mask=True))]
    return out


MESH_OF = {'itmc1_1': 'chn1_1', 'itmc2_1': 'chn1_1', 'itmc3_1': 'chn1_1'}


def add_skins(overlay_dir, level_name, log=print):
    paths = wreck._ensure_overlay(overlay_dir, level_name)
    m = mtp.read(paths['mtp'])
    clash = [n for n in NAMES if n in m['VNAM']]
    if clash:
        raise ValueError('skins already in %s: %s' % (paths['mtp'], clash))
    mp_mtp = os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'multiplayer.mtp')
    chn_mesh, _ = SF._mesh_entry(mp_mtp, 'chn1_1')
    resg_mesh, _ = SF._mesh_entry(mp_mtp, 'resg1_1')
    mform, mch, mhdr = ilff.read(open(paths['models'], 'rb').read())
    have_m = {d.rstrip(b'\0').decode('latin1') for t, d, a in mch if t == b'NAME'}
    for mesh_name in (chn_mesh, resg_mesh):              # every MODS entry in the overlay's own bank
        key = 'LOCAL:models/%s.mef' % mesh_name
        if key not in have_m:
            ch_, names_ = SF._bank(os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'models', 'multiplayer.res'))
            assert key in names_, key
            mch.append((b'NAME', key.encode('latin1') + b'\0', 4)); mch.append((b'BODY', ch_[names_[key]][1], 4))
        if mesh_name not in m['MODS']:
            m['MODS'].append(mesh_name)
    form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
    have_t = {d.rstrip(b'\0').decode('latin1') for t, d, a in ch if t == b'NAME'}
    gtt = {}

    def add_tex(tname, img):
        key = 'LOCAL:textures/%s.tex' % tname
        if key not in have_t:
            ch.append((b'NAME', key.encode('latin1') + b'\0', 4)); ch.append((b'BODY', wreck.tex_mode2(img), 4)); have_t.add(key)
        if tname not in m['TEXF']:
            m['TEXF'].append(tname)
        ti = m['TEXF'].index(tname)
        for i, (t_, pl) in enumerate(m['GTT']):
            if t_ == ti and pl == -1:
                gtt[tname] = i; break
        else:
            m['GTT'].append([ti, -1]); gtt[tname] = len(m['GTT']) - 1

    for vn, slots in _textures().items():
        for tname, img in slots:
            if img is not None:
                add_tex(tname, img)
        mesh = chn_mesh if vn in MERCS else resg_mesh
        m['VNAM'].append(vn); m['INST'].append([m['MODS'].index(mesh), [gtt[t] for t, _ in slots]])
    for path, blob in ((paths['textures'], ilff.write(form, ch, hdr[1] or 4)), (paths['models'], ilff.write(mform, mch, mhdr[1] or 4)),
                       (paths['mtp'], mtp.write(m))):
        tmp = path + '.it.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    b2 = wreck.Bank(paths['mtp'], paths['models'], paths['textures'])
    probs = [n for n in NAMES if b2.res.get(n) is None]
    if set(b2.m['TEXF']) - set(b2.tex):
        probs.append('TEXF entries without a texture: %s' % sorted(set(b2.m['TEXF']) - set(b2.tex))[:5])
    log('itskins: %s registered (meshes %s / %s), problems %s' % (NAMES, chn_mesh, resg_mesh, probs or 'none'))
    assert not probs, probs
    return NAMES


def preview(out_dir):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    for vn, slots in _textures().items():
        for tname, img in slots:
            if img is not None:
                h, w = img.shape[:2]
                Image.fromarray((np.clip(img[..., :3], 0, 1) * 255).astype('u1')).resize((w // 4, h // 4)).save(os.path.join(out_dir, tname + '.png'))


if __name__ == '__main__':
    preview(sys.argv[1] if len(sys.argv) > 1 else 'itskins_preview')
