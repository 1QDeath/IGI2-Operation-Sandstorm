"""skinforge - NEW character skins for Operation Black Ice (owner 10-13: 'new soldier skins and faces, several faces').

A skin = a VNAM whose INST reuses a character MESH with its own textures (sirocco_tex recipe, as burnt.py). Nothing
is copied from another game: the new textures are PAINTED over the layout of the shipped ones (the layout = where the
mesh's UVs land: jacket, trousers, hands, boots, the mirrored face), so the mesh wears them.

  Gulag guards  (mesh resg_1, 2 slots: body 1024^2 'ch_resg_01' layout, head 512x1024 'ch_resg_00' layout)
    bigd1_1 .. bigd3_1  greatcoat (grey-brown wool, belt, red collar tabs, shoulder boards), ushanka, 3 faces
    bigdc_1             the commandant: officer greatcoat (blue-grey), papakha, a 4th face
  Elena         (mesh anya_1: 'ch_aya_01' body 2048^2, 'anyaface' 2048x1024, eyes, hair, lashes)
    elena_1             padded grey prison jacket, dark hair, pale tired face

    import skinforge
    skinforge.add_skins(overlay_dir, 'jungle')         # registers the VNAMs + textures in the overlay (after prefabs)
    skinforge.NAMES                                    # for Mission.location_skins()

The painting is procedural (numpy + PIL): the shipped texture gives the shading (its luminance), new colour and
pattern layers are multiplied over it, so folds and seams stay.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff, mtp, igitex, wreck

GAME = wreck.GAME
NAMES = ['bigd1_1', 'bigd2_1', 'bigd3_1', 'bigdc_1', 'elena_1']
GUARDS = ['bigd1_1', 'bigd2_1', 'bigd3_1']


# ------------------------------------------------------------------------------------------------ reading the shipped textures
def _bank(path):
    form, ch, hdr = ilff.read(open(path, 'rb').read())
    names = {d.rstrip(b'\0').decode('latin1'): i + 1 for i, (t, d, a) in enumerate(ch) if t == b'NAME'}
    return ch, names


def shipped(name):
    """float RGBA of a shipped texture (MP common, then location1 / location2 common)"""
    for rel in ('MISSIONS/multiplayer/common/textures/multiplayer.res', 'MISSIONS/location1/common/textures/location1.res',
                'MISSIONS/location2/common/textures/location2.res', 'COMMON/textures/common.res'):
        ch, names = _bank(os.path.join(GAME, *rel.split('/')))
        key = 'LOCAL:textures/%s.tex' % name
        if key in names:
            return igitex.decode(ch[names[key]][1])
    raise KeyError(name)


def _lum(img):
    return 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]


def _noise(h, w, rng, scale=8, octaves=3):
    out = np.zeros((h, w))
    for o in range(octaves):
        k = scale * 2 ** o
        g = rng.random((h // k + 2, w // k + 2))
        yy = np.linspace(0, h / k, h); xx = np.linspace(0, w / k, w)
        yi, xi = np.floor(yy).astype(int), np.floor(xx).astype(int)
        yf, xf = (yy - yi)[:, None], (xx - xi)[None, :]
        a = g[yi][:, xi]; b = g[yi][:, xi + 1]; c = g[yi + 1][:, xi]; d = g[yi + 1][:, xi + 1]
        out += ((a * (1 - xf) + b * xf) * (1 - yf) + (c * (1 - xf) + d * xf) * yf) / 2 ** o
    return (out - out.min()) / (out.max() - out.min() + 1e-9)


def _rect(img, x0, y0, x1, y1):
    """fractional rectangle -> slice"""
    H, W = img.shape[:2]
    return slice(int(y0 * H), int(y1 * H)), slice(int(x0 * W), int(x1 * W))


def recolor(img, sl, rgb, keep_shading=0.9, sat_gain=1.0, rng=None, wool=0.0):
    """paint region sl with colour rgb, keeping the original luminance as shading"""
    out = img
    reg = out[sl]
    L = _lum(reg)
    Ln = L / max(1e-6, float(np.percentile(L, 90)))
    sh = (1 - keep_shading) + keep_shading * np.clip(Ln, 0, 1.3)
    col = np.asarray(rgb, float)[None, None, :] * sh[..., None]
    if wool and rng is not None:
        n = _noise(reg.shape[0], reg.shape[1], rng, scale=2, octaves=2)
        col = col * (1 - wool + wool * (0.8 + 0.4 * n))[..., None]
    reg[..., :3] = np.clip(col, 0, 1)
    return out


def _box_fill(img, sl, rgb):
    img[sl][..., :3] = np.asarray(rgb, float)
    return img


# ------------------------------------------------------------------------------------------------ the guard body (ch_resg_01 layout)
# layout (fractions of the 1024^2 sheet, from the dumped picture work/blackice/skins/ch_resg_01.png):
#   upper jacket/vest       x 0.00..0.59  y 0.00..0.44
#   trousers                x 0.00..0.56  y 0.44..1.00
#   helmet/hat (top right)  x 0.59..1.00  y 0.00..0.33
#   boot sole / hands       x 0.59..0.82 / 0.82..1.00  y 0.33..0.44
#   sleeve (inner cloth)    x 0.56..0.80  y 0.44..0.83
#   belt / pouch            x 0.80..1.00  y 0.50..0.70 ; collar badge patch x 0.56..0.64 y 0.83..0.93
#   boots                   x 0.75..1.00  y 0.83..1.00
def guard_body(kind, seed):
    rng = np.random.default_rng(seed)
    img = shipped('ch_resg_01').copy()
    coat = {0: (0.42, 0.38, 0.30), 1: (0.38, 0.35, 0.29), 2: (0.45, 0.40, 0.31), 3: (0.30, 0.33, 0.40)}[kind]   # (3 = officer blue-grey)
    recolor(img, _rect(img, 0.0, 0.0, 0.59, 0.44), coat, keep_shading=0.85, rng=rng, wool=0.35)       # the greatcoat body
    recolor(img, _rect(img, 0.0, 0.44, 0.56, 1.0), coat, keep_shading=0.85, rng=rng, wool=0.35)       # ... hangs over the legs
    recolor(img, _rect(img, 0.56, 0.44, 0.80, 0.83), coat, keep_shading=0.85, rng=rng, wool=0.35)     # sleeves
    # the double row of brass buttons down the chest (the chest seam runs down the middle of the jacket region)
    H, W = img.shape[:2]
    for k in range(6):
        y = int((0.06 + 0.06 * k) * H)
        for x in (int(0.265 * W), int(0.325 * W)):
            img[y - 5:y + 5, x - 5:x + 5, :3] = (0.78, 0.66, 0.30)
    # belt: a dark leather band across the waist of the jacket region, brass buckle
    img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] *= 0.0
    img[int(0.40 * H):int(0.44 * H), 0:int(0.59 * W), :3] += (0.16, 0.11, 0.07)
    img[int(0.405 * H):int(0.435 * H), int(0.27 * W):int(0.32 * W), :3] = (0.75, 0.62, 0.28)
    # snow dust on the shoulders (soft, before the tabs)
    n = _noise(int(0.08 * H), int(0.59 * W), rng, scale=4)
    a_ = np.clip((n - 0.6) / 0.2, 0, 1)[..., None] * 0.55
    img[0:int(0.08 * H), 0:int(0.59 * W), :3] = img[0:int(0.08 * H), 0:int(0.59 * W), :3] * (1 - a_) + a_ * np.array([0.9, 0.92, 0.96])
    # red collar tabs (a thin red band along the top edge of the jacket region) and shoulder boards
    tab = (0.62, 0.10, 0.10) if kind != 3 else (0.80, 0.70, 0.25)
    img[0:int(0.025 * H), int(0.12 * W):int(0.47 * W), :3] = tab
    for x0 in (0.02, 0.46):
        img[int(0.03 * H):int(0.07 * H), int(x0 * W):int((x0 + 0.11) * W), :3] = tab
    # gloves: dark wool mitts over the hands
    recolor(img, _rect(img, 0.82, 0.33, 1.0, 0.44), (0.22, 0.20, 0.17), keep_shading=0.8)
    # felt boots (valenki) for two of them, leather for the others
    if kind in (1, 2):
        recolor(img, _rect(img, 0.75, 0.83, 1.0, 1.0), (0.36, 0.33, 0.28), keep_shading=0.7)
    return img


# ------------------------------------------------------------------------------------------------ the guard head (ch_resg_00 layout)
# 512 (w) x 1024 (h)?? no: decoded shape (512, 1024, 4) = 512 rows x 1024 columns: the face is mirrored about x 0.5, the
# hair strip runs across the top (y 0..0.22), the face y 0.18..0.75, the neck below, black (unused) y 0.78..1.
def _soft_ellipse(H, W, cy, cx, ry, rx, feather=0.35):
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.hypot((yy - cy) / max(ry, 1), (xx - cx) / max(rx, 1))
    return np.clip((1.0 - d) / feather, 0, 1)


def _warp_face(img, jaw, eyes, nose, cheeks, y0=0.18, y1=0.78):
    """symmetric geometry change of the mirrored face sheet (centre x 0.5): jaw > 1 widens the lower face, eyes moves
    the eyes apart, nose > 1 lengthens the nose / mid face, cheeks > 1 fills the cheeks out"""
    from scipy import ndimage
    H, W = img.shape[:2]
    ys, ye = int(y0 * H), int(y1 * H)
    reg = img[ys:ye].copy()
    h, w = reg.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    cx = w / 2.0
    v = yy / h                                           # 0 top of the face band .. 1 the neck
    dx = xx - cx
    # horizontal scale: eyes band (v ~0.25), cheeks (v ~0.5), jaw (v ~0.75); sample from a SMALLER |dx| to widen
    sx = 1.0 + (eyes - 1.0) * np.exp(-((v - 0.25) / 0.10) ** 2) + (cheeks - 1.0) * np.exp(-((v - 0.50) / 0.12) ** 2)         + (jaw - 1.0) * np.exp(-((v - 0.78) / 0.14) ** 2)
    src_x = cx + dx / sx
    # vertical: stretch the middle (nose) band around v 0.45
    src_y = yy - (nose - 1.0) * h * 0.18 * np.tanh((v - 0.45) / 0.15)
    out = np.empty_like(reg)
    for c in range(reg.shape[2]):
        out[..., c] = ndimage.map_coordinates(reg[..., c], [src_y, src_x], order=1, mode='nearest')
    img[ys:ye] = out
    return img


def guard_head(face, hat, seed):
    rng = np.random.default_rng(seed)
    img = shipped('ch_resg_00').copy()
    H, W = img.shape[:2]
    tone, beard, age, brow, geo = face
    _warp_face(img, *geo)
    # --- skin tone (keep the shading)
    sk = _rect(img, 0.0, 0.18, 1.0, 0.78)
    reg = img[sk]
    L = _lum(reg)[..., None]
    reg[..., :3] = np.clip(np.asarray(tone, float)[None, None, :] * (0.35 + 0.95 * L / max(1e-6, float(np.percentile(L, 92)))), 0, 1)
    img[sk] = reg
    # --- beard / stubble: a soft mask round mouth and jaw (an ellipse minus the mouth), speckled
    if beard > 0:
        m_ = _soft_ellipse(H, W, 0.62 * H, 0.5 * W, 0.13 * H, 0.17 * W, 0.5)
        m_ -= _soft_ellipse(H, W, 0.585 * H, 0.5 * W, 0.022 * H, 0.05 * W, 0.6)
        n = _noise(H, W, rng, scale=1, octaves=2)
        a = np.clip(m_, 0, 1) * (0.55 + 0.45 * n) * beard
        img[..., :3] = img[..., :3] * (1 - 0.75 * a[..., None]) + 0.08 * a[..., None]
    # --- moustache (commandant, face 2)
    if age >= 0.9 or beard == 0.25:
        mm_ = _soft_ellipse(H, W, 0.546 * H, 0.5 * W, 0.009 * H, 0.055 * W, 0.6)
        img[..., :3] = img[..., :3] * (1 - 0.8 * mm_[..., None]) + 0.06 * mm_[..., None]
    # --- eyebrows: soft arcs over the eyes (x 0.455 / 0.545 of the sheet, y ~0.335), thickness by brow
    for xc in (0.455, 0.545):
        e_ = _soft_ellipse(H, W, 0.333 * H, xc * W, 0.006 * H * (1 + brow), 0.03 * W, 0.7)
        img[..., :3] = img[..., :3] * (1 - 0.7 * brow * e_[..., None])
    # --- age: nasolabial folds + forehead lines, soft
    if age > 0:
        for xc in (0.44, 0.56):
            f_ = _soft_ellipse(H, W, 0.56 * H, xc * W, 0.05 * H, 0.004 * W, 0.8)
            img[..., :3] *= 1 - 0.35 * age * f_[..., None]
        for yc in (0.255, 0.275):
            f_ = _soft_ellipse(H, W, yc * H, 0.5 * W, 0.002 * H, 0.08 * W, 0.8)
            img[..., :3] *= 1 - 0.25 * age * f_[..., None]
    # --- the hat over the hair strip and the ear flaps (soft lower edge)
    n = _noise(H, W, rng, scale=3, octaves=3)
    furc = np.array([0.55, 0.52, 0.47]) if hat == 'ushanka' else np.array([0.16, 0.15, 0.14])
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    edge = 0.235 + np.where((xx < 0.21) | (xx > 0.79), 0.30, 0.0) * (hat == 'ushanka')
    a = np.clip((edge - yy) / 0.012, 0, 1)
    fur = furc[None, None, :] * (0.65 + 0.6 * n)[..., None]
    img[..., :3] = img[..., :3] * (1 - a[..., None]) + np.clip(fur, 0, 1) * a[..., None]
    cy, cx = int(0.10 * H), int(0.5 * W)
    st = _soft_ellipse(H, W, cy, cx, 15, 15, 0.3)
    badge = np.array([0.75, 0.12, 0.10]) if hat == 'ushanka' else np.array([0.80, 0.68, 0.25])
    img[..., :3] = img[..., :3] * (1 - st[..., None]) + badge * st[..., None]
    return img


FACES = [((0.86, 0.68, 0.58), 0.0, 0.0, 0.45, (0.88, 0.94, 0.92, 0.86)),   # young, thin, clean-shaven, fair
         ((0.78, 0.60, 0.50), 0.85, 0.6, 0.6, (1.12, 1.04, 1.0, 1.06)),   # broad, weathered, dark stubble
         ((0.90, 0.72, 0.62), 0.25, 0.3, 0.5, (0.96, 1.08, 1.12, 0.95)),  # long face, wide eyes, moustache, pale
         ((0.80, 0.63, 0.52), 0.0, 0.9, 0.8, (1.06, 0.97, 1.05, 1.12))]   # the commandant: older, heavy, heavy brows


# ------------------------------------------------------------------------------------------------ Elena (anya_1 textures)
def elena_body():
    rng = np.random.default_rng(77)
    img = shipped('ch_aya_01').copy()
    H, W = img.shape[:2]
    # the sweater (top-left 0..0.6 x 0..0.46) -> a grey quilted prison jacket
    sl = _rect(img, 0.0, 0.0, 0.61, 0.46)
    recolor(img, sl, (0.40, 0.40, 0.38), keep_shading=0.8, rng=rng, wool=0.2)
    reg = img[sl]
    yy, xx = np.mgrid[0:reg.shape[0], 0:reg.shape[1]]
    quilt = ((yy % 64) < 3) | ((xx % 64) < 3)
    reg[quilt, :3] *= 0.65
    # a cloth number patch on the chest
    img[int(0.30 * H):int(0.34 * H), int(0.10 * W):int(0.22 * W), :3] = (0.85, 0.82, 0.70)
    img[int(0.31 * H):int(0.33 * H), int(0.12 * W):int(0.20 * W), :3] = (0.1, 0.1, 0.1)
    # trousers stay dark; the hair (0.55..0.80 x 0.63..1.0) -> dark brown
    recolor(img, _rect(img, 0.55, 0.63, 0.80, 1.0), (0.22, 0.14, 0.09), keep_shading=0.9)
    return img


def elena_face():
    img = shipped('anyaface').copy()
    # paler, tired: desaturate a little, darken under the eyes (the face sheet is mirrored around x 0.5)
    L = _lum(img)[..., None]
    img[..., :3] = np.clip(img[..., :3] * 0.6 + 0.4 * np.repeat(L, 3, axis=2) * np.array([1.0, 0.93, 0.9]), 0, 1)
    H, W = img.shape[:2]
    for xc in (0.43, 0.57):
        e_ = _soft_ellipse(H, W, 0.475 * H, xc * W, 0.022 * H, 0.035 * W, 0.8)
        img[..., :3] *= 1 - 0.18 * e_[..., None]
    import colorsys
    src = shipped('anyaface')
    r, g, b = src[..., 0], src[..., 1], src[..., 2]
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    hue = np.where(mx - mn > 1e-4, ((g - b) / np.maximum(mx - mn, 1e-4)) % 6.0, 0.0) * 60.0   # (red-max hue, degrees)
    sat = (mx - mn) / np.maximum(mx, 1e-4)
    hair = np.clip((hue - 24.0) / 8.0, 0, 1) * np.clip((sat - 0.12) / 0.08, 0, 1)            # blonde ~35-45 deg, skin ~10-20
    face = _soft_ellipse(H, W, 0.62 * H, 0.5 * W, 0.40 * H, 0.15 * W, 0.15)
    hair = hair * (1 - face)
    from scipy import ndimage
    hair = ndimage.gaussian_filter(hair, 2.0)
    Lh = _lum(img)[..., None]
    dark = np.clip(Lh * np.array([0.40, 0.27, 0.17]) * 1.1, 0, 1)
    img[..., :3] = img[..., :3] * (1 - hair[..., None]) + dark * hair[..., None]
    return img


def elena_hair():
    img = shipped('anyahair_argb8888').copy()
    L = _lum(img)[..., None]
    img[..., :3] = np.clip(np.repeat(L, 3, axis=2) * np.array([0.42, 0.28, 0.18]), 0, 1)
    return img


# ------------------------------------------------------------------------------------------------ registration
def _mesh_entry(level_mtp, vn):
    mm = mtp.read(level_mtp)
    i = mm['VNAM'].index(vn)
    mi, g = mm['INST'][i]
    return mm['MODS'][mi], [mm['TEXF'][mm['GTT'][x][0]] for x in g]


def add_skins(overlay_dir, level_name, which=None, log=print):
    """VNAMs bigd1..3_1, bigdc_1 (mesh resg_1, 2 slots) and elena_1 (mesh anya_1, 5 slots) with painted textures"""
    paths = wreck._ensure_overlay(overlay_dir, level_name)
    m = mtp.read(paths['mtp'])
    want = list(which or NAMES)
    clash = [n for n in want if n in m['VNAM']]
    if clash:
        raise ValueError('skins already in %s: %s' % (paths['mtp'], clash))
    mp_mtp = os.path.join(GAME, 'MISSIONS', 'multiplayer', 'common', 'multiplayer.mtp')
    l2_mtp = os.path.join(GAME, 'MISSIONS', 'location2', 'common', 'location2.mtp')
    resg_mesh, _ = _mesh_entry(mp_mtp, 'resg1_1')
    anya_mesh, anya_tex = _mesh_entry(l2_mtp, 'anya_1')
    # the meshes must be in the overlay's own model bank (every MODS entry in its own bank)
    mform, mch, mhdr = ilff.read(open(paths['models'], 'rb').read())
    have_m = {d.rstrip(b'\0').decode('latin1') for t, d, a in mch if t == b'NAME'}
    import prefab as pf
    for mesh_name in (resg_mesh, anya_mesh):
        key = 'LOCAL:models/%s.mef' % mesh_name
        if key not in have_m:
            body = None
            for rel in ('MISSIONS/multiplayer/common/models/multiplayer.res', 'MISSIONS/location2/common/models/location2.res',
                        'COMMON/models/common.res'):
                ch_, names_ = _bank(os.path.join(GAME, *rel.split('/')))
                if key in names_:
                    body = ch_[names_[key]][1]; break
            assert body is not None, key
            mch.append((b'NAME', key.encode('latin1') + b'\0', 4)); mch.append((b'BODY', body, 4))
        if mesh_name not in m['MODS']:
            m['MODS'].append(mesh_name)
    form, ch, hdr = ilff.read(open(paths['textures'], 'rb').read())
    have_t = {d.rstrip(b'\0').decode('latin1') for t, d, a in ch if t == b'NAME'}
    gtt = {}

    def add_tex(tname, img, alpha=False):
        key = 'LOCAL:textures/%s.tex' % tname
        if key not in have_t:
            tb = wreck.tex_mode67(img) if alpha else wreck.tex_mode2(img)
            ch.append((b'NAME', key.encode('latin1') + b'\0', 4)); ch.append((b'BODY', tb, 4)); have_t.add(key)
        if tname not in m['TEXF']:
            m['TEXF'].append(tname)
        ti = m['TEXF'].index(tname)
        for i, (t_, pl) in enumerate(m['GTT']):
            if t_ == ti and pl == -1:
                gtt[tname] = i; break
        else:
            m['GTT'].append([ti, -1]); gtt[tname] = len(m['GTT']) - 1
        return tname

    def copy_shipped(tname, alpha=False):
        key = 'LOCAL:textures/%s.tex' % tname
        if key not in have_t:
            for rel in ('MISSIONS/location2/common/textures/location2.res', 'MISSIONS/multiplayer/common/textures/multiplayer.res'):
                ch_, names_ = _bank(os.path.join(GAME, *rel.split('/')))
                if key in names_:
                    ch.append((b'NAME', key.encode('latin1') + b'\0', 4)); ch.append((b'BODY', ch_[names_[key]][1], 4)); have_t.add(key); break
        if tname not in m['TEXF']:
            m['TEXF'].append(tname)
        ti = m['TEXF'].index(tname)
        for i, (t_, pl) in enumerate(m['GTT']):
            if t_ == ti and pl == -1:
                gtt[tname] = i; break
        else:
            m['GTT'].append([ti, -1]); gtt[tname] = len(m['GTT']) - 1
        return tname

    made = []
    for k, vn in enumerate(GUARDS + ['bigdc_1']):
        if vn not in want:
            continue
        kind = 3 if vn == 'bigdc_1' else k
        body = add_tex('bi_gdbody%d' % kind, guard_body(kind, 100 + kind))
        head = add_tex('bi_gdhead%d' % kind, guard_head(FACES[kind], 'papakha' if kind == 3 else 'ushanka', 200 + kind))
        m['VNAM'].append(vn); m['INST'].append([m['MODS'].index(resg_mesh), [gtt[body], gtt[head]]])
        made.append(vn)
    if 'elena_1' in want:
        slots = [add_tex('bi_elbody', elena_body()), add_tex('bi_elface', elena_face()), copy_shipped('anyaeye'),
                 add_tex('bi_elhair', elena_hair(), alpha=True), copy_shipped('anyalash_argb8888')]
        m['VNAM'].append('elena_1'); m['INST'].append([m['MODS'].index(anya_mesh), [gtt[s] for s in slots]])
        made.append('elena_1')
    for path, blob in ((paths['textures'], ilff.write(form, ch, hdr[1] or 4)), (paths['models'], ilff.write(mform, mch, mhdr[1] or 4)),
                       (paths['mtp'], mtp.write(m))):
        tmp = path + '.sk.tmp'
        open(tmp, 'wb').write(blob)
        os.replace(tmp, path)
    b2 = wreck.Bank(paths['mtp'], paths['models'], paths['textures'])
    probs = [n for n in made if b2.res.get(n) is None]
    if set(b2.m['TEXF']) - set(b2.tex):
        probs.append('TEXF entries without a texture: %s' % sorted(set(b2.m['TEXF']) - set(b2.tex))[:5])
    log('skinforge: %s registered (meshes %s / %s), problems %s' % (made, resg_mesh, anya_mesh, probs or 'none'))
    assert not probs, probs
    return made


def preview(out_dir):
    """write the painted textures as PNGs (to look at them)"""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    for k in range(4):
        Image.fromarray((np.clip(guard_body(k, 100 + k), 0, 1) * 255).astype('u1')).save(os.path.join(out_dir, 'gdbody%d.png' % k))
        Image.fromarray((np.clip(guard_head(FACES[k], 'papakha' if k == 3 else 'ushanka', 200 + k), 0, 1) * 255).astype('u1')).save(os.path.join(out_dir, 'gdhead%d.png' % k))
    Image.fromarray((np.clip(elena_body(), 0, 1) * 255).astype('u1')).save(os.path.join(out_dir, 'elbody.png'))
    Image.fromarray((np.clip(elena_face(), 0, 1) * 255).astype('u1')).save(os.path.join(out_dir, 'elface.png'))


if __name__ == '__main__':
    preview(sys.argv[1] if len(sys.argv) > 1 else 'skins_preview')
