"""ssbase - Sandstorm v5 (2026-11-04): the NEW underground missile base, replaces the L34 Lab Cave shell (owner: 'that is the China map').
Mission-specific (only build_sandstorm.py imports it). Every wall, floor and ceiling is a NEW vertex-lit mesh (tools/modelkit) textured
from the map's OWN textures (textures below are composites of them with light baked in, bay by bay); nothing is copied from a level.

  ss_hall_1   the hall: a low TRUCK GALLERY (west, 13 m) opening into a tall SILO HALL (east, 26 m, the pit + the missile), control room,
              guard quarters, crane, ducts, lamps. Closed on all sides, collision = thick slabs.
  ss_tun1..4  the truck tunnel: a real ramp from the blast gate up to the sand door (hairpin under the hill), ribbed, lit, walkable.
  ss_port_1   the portal: the last stretch of tunnel, headwall, apron in the hillside.
  ss_bgate_1 / ss_sgate_1  roll-up gates (Doors that slide up in a wall slot): the vehicle blast gate, the sand door.

World metres. x east, y north. Lift arrives at the west wall (V.VEST_*), the gate is on the east wall.
"""
import math, os
import numpy as np
import biprefabs as BP
import modelkit as MK
import searchlight as SL
import mefmesh

# S14 (owner 11-15: men under the gun room shot him through the wall): every built shell was material 6 (NormalMetal, penetration 4),
# so an AK / Minimi round (power 12) went through one wall, floor or stair of ours whatever its thickness (gunshot.c: power - 4 in,
# - 4 out). These shells get material 12 (Runway: penetration 20, concrete footsteps / holes / dust, the originals' thick concrete),
# set over collision mesh 0 by modelkit.Library at build time. The two steel blast gates get 5 (StrongMetal, also 20: metal sounds).
# Props, see-through mesh (cage, lift landing gates) and small steel models stay at 6 (MATERIAL/material.qvm: 6 NormalMetal 4, 12 Runway 20,
# 5 StrongMetal 20, 18 Fence 0.1, 21 HumanCollision = collision mesh 1).
BULLET_STOP = {'ss_hall_1': 12, 'ss_gunr_1': 12, 'ss_shaft_1': 12, 'ss_way_1': 12, 'ss_shed_1': 12, 'ss_bulw_1': 12, 'ss_port_1': 12,
               'ss_tun1_1': 12, 'ss_tun2_1': 12, 'ss_tun3_1': 12, 'ss_tun4_1': 12, 'ss_bgate_1': 5, 'ss_sgate_1': 5}
if os.environ.get('SS_BULLETSTOP', '1') != '0':
    MK.SURFACE.update(BULLET_STOP)

M = 4096.0
F = -34.0                                                  # hall floor (m)
X0, X1, Y0, Y1 = 172.0, 268.0, 196.0, 256.0                # hall inside
BAY = 12.0
XS = 232.0                                                 # the gallery ends / the silo hall starts
CG, CS = F + 13.0, F + 26.0                                # ceilings: gallery, silo hall
PIT = (244.0, 232.0, 256.0, 244.0)                         # the silo pit (one floor bay)
PIT_Z = F - 5.0
PIT_C = ((PIT[0] + PIT[2]) / 2, (PIT[1] + PIT[3]) / 2)
LOBBY_DOOR = (225.4, 228.0, 2.5)                           # the doorway from the lift vestibule (y0, y1, height)
GATE_Y0, GATE_Y1, GATE_H = 217.0, 227.0, 6.5               # the blast gate opening in the east wall
GATE_X = X1 + 0.45                                         # the leaf's plane (in the wall's slot)
ROAD_Y = 225.0
CTRL = (246.0, 197.0, 266.0, 208.0)                        # control room inside (x0, y0, x1, y1), floor F, ceiling F + 3.6
CTRL_H = 3.6
CTRL_DOOR_Y = (201.9, 203.1)                               # its door gap in the west wall (x = CTRL[0]): 501_04_1, 1.2 m
QUARTERS = (176.0, 249.0, 226.0, 256.0)                    # guard quarters block on the north wall
ROOMS = ((178.0, 189.0), (194.0, 205.0), (210.0, 222.0))    # its rooms (x): a door in the south wall of each, in the middle
TW, TH, TCH = 4.5, 6.5, 5.3                                # tunnel half width, height, chamfer start height
SLOPE_FLAT_A, SLOPE_FLAT_B = 24.0, 14.0                    # flat run behind the gate / before the sand door (m)
DOOR_SLIDE = 6.75
T_ROOF_DROP = 0.45
GARRISON2 = os.environ.get('SS_GARRISON2', '1') == '1'          # (owner 11-05, 55-56: the soldiers live in the Bulwark, tools/ssgarr.py, not in rooms on the north wall)
GUNROOM = os.environ.get('SS_GUNROOM', '1') == '1'             # (owner 11-06, 63: the three-stop lift and the gun room, tools/ssgun.py, behind this flag until proven)
SS_PORTAL_EDGE = os.environ.get('SS_PORTAL_EDGE', '1') == '1'   # (S7 11-17: the sand door drift's lane edges come down to the ground past the revetments; 0 = rc7s25 shape)
SS_TRACK_EDGE = os.environ.get('SS_TRACK_EDGE', '1') == '1'     # (S7 11-17: the tyre tracks stop at the apron's edge instead of hanging over its drop; 0 = ssb2 shape)
EXPOSED_SEGS = 5                                           # the last tunnel segments stand out of the hill


# ------------------------------------------------------------------------------------------------ textures (the map's own, light baked in)
def _tile(a, nx, ny, W, H):
    from PIL import Image
    im = np.asarray(Image.fromarray((np.clip(a[..., :3], 0, 1) * 255).astype(np.uint8)).resize((max(1, W // nx), max(1, H // ny)), Image.BILINEAR), float) / 255.0
    return np.tile(im, (ny + 1, nx + 1, 1))[:H, :W]


def _noise(h, w, seed, oct_=(4, 8, 16, 32)):
    from PIL import Image
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    for k, o in enumerate(oct_):
        g = (rng.random((o, o)) * 255).astype(np.uint8)
        out += np.asarray(Image.fromarray(g).resize((w, h), Image.BICUBIC), float) / 255.0 * (0.5 ** k)
    return out / out.max()


def _rgba(img):
    return np.clip(np.dstack([img, np.ones(img.shape[:2])]), 0, 1)


WARM = np.array([1.04, 0.95, 0.82])


COOL = np.array([0.56, 0.62, 0.59])
POOL = np.array([0.98, 0.84, 0.60])


def _concrete(a, pool, base, gain, cool=COOL):
    """the texture's detail in grey, tinted cool, warm only where a lamp's pool falls (pool 0..1)"""
    L = a.mean(2, keepdims=True)
    L = L / max(float(L.mean()), 1e-3) * 0.5
    t = cool * (1 - pool[..., None]) + POOL * pool[..., None]
    return L * (base + gain * pool)[..., None] * t


def tex_bw(get):
    """a wall bay (12 x 13 m): tied concrete slabs, a lamp's pool at the top third, painted dado, floor grime"""
    n = 512
    a = _tile(get('409_17_1'), 3, 3, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    p = np.exp(-(((u - 0.5) / 0.26) ** 2 + ((v - 0.40) / 0.30) ** 2))
    img = _concrete(a, p, 0.42 + 0.14 * v, 0.62) * (0.84 + 0.3 * _noise(n, n, 3))[..., None]
    d = v > 0.905
    paint = np.array([0.13, 0.16, 0.13]) * (0.8 + 0.4 * _noise(n, n, 5))[..., None]
    img[d] = paint[d]
    img[(v > 0.897) & (v <= 0.905)] = (0.52, 0.37, 0.09)
    g = np.clip((v - 0.965) / 0.035, 0, 1)
    return _rgba(img * (1 - 0.6 * g)[..., None])


def tex_bu(get):
    n = 512
    a = _tile(get('409_17_1'), 3, 3, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    return _rgba(_concrete(a, np.zeros((n, n)), 0.20 + 0.26 * v, 0.0) * (0.8 + 0.35 * _noise(n, n, 7))[..., None])


def tex_bf(get):
    """a floor bay (12 x 12 m): dark concrete with joints, a warm lamp's pool in the middle, oil and tyre marks"""
    n = 512
    a = _tile(get('409_10_1'), 2, 2, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    p = np.exp(-(np.hypot(u - 0.5, v - 0.5) / 0.24) ** 2)
    img = _concrete(a, p, 0.26 + 0.0 * v, 0.62, cool=np.array([0.52, 0.56, 0.56]))
    img *= (0.80 + 0.40 * _noise(n, n, 11))[..., None]
    img *= (1 - 0.35 * (_noise(n, n, 12, (3, 6, 12)) > 0.72))[..., None]
    for k in (0, n // 2):
        img[k:k + 3, :] *= 0.45
        img[:, k:k + 3] *= 0.45
    return _rgba(img)


def tex_bc(get):
    n = 256
    a = _tile(get('436_11_1'), 2, 2, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    p = np.exp(-(np.hypot(u - 0.5, v - 0.5) / 0.20) ** 2)
    return _rgba(_concrete(a, p, 0.10, 0.34))


LAMP_U = 0.75                                              # (the lamps hang on the ribs at arc 9 + 12k: u = arc / BAY = 0.75 of each bay)


def _pool_u(u, w, c=LAMP_U):
    """a lamp's pool round u = c, periodic over the bay"""
    d = np.abs(((u - c + 0.5) % 1.0) - 0.5)
    return np.exp(-(d / w) ** 2)


def tex_tw(get):
    """a tunnel wall bay (12 x 5.3 m): rough concrete, the pool of the lamp on this wall (owner 11-13: centred on it, warm, falling off to dark half way
    to the next), a dark dado"""
    n = 256
    a = _tile(get('409_17_1'), 3, 1, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    p = np.clip(_pool_u(u, 0.13) * np.exp(-((v - 0.26) / 0.48) ** 2) + 0.38 * _pool_u(u, 0.34) * np.exp(-((v - 0.45) / 0.75) ** 2), 0, 1)
    img = _concrete(a, p, 0.24, 0.98) * (0.85 + 0.3 * _noise(n, n, 21))[..., None]
    d = v > 0.80
    img[d] = (np.array([0.12, 0.14, 0.12]) * (0.85 + 0.3 * _noise(n, n, 23))[..., None])[d]
    img[(v > 0.785) & (v <= 0.80)] = (0.52, 0.36, 0.08)
    return _rgba(img)


def tex_tw2(get):
    """judge E14: the way down's lining (stairs, passage, corridor, lift room): the tunnel bay's concrete with a flatter light (0.50 at the bay's edge, not 0.34): it read near black between lamps"""
    n = 256
    a = _tile(get('409_17_1'), 3, 1, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    p = np.exp(-(((u - 0.5) / 0.32) ** 2 + ((v - 0.30) / 0.55) ** 2))
    img = _concrete(a, p, 0.52, 0.36) * (0.88 + 0.24 * _noise(n, n, 24))[..., None]
    d = v > 0.80
    img[d] = (np.array([0.16, 0.18, 0.16]) * (0.85 + 0.3 * _noise(n, n, 25))[..., None])[d]
    img[(v > 0.785) & (v <= 0.80)] = (0.52, 0.36, 0.08)
    return _rgba(img)


def tex_drum(get):
    """judge E02: an oil drum's skin (u round it, v up, 1 m a tile): olive paint over rust, two rolling hoops, a stencil band"""
    n = 128
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    rust = _noise(n, n, 26, (4, 8, 16, 32))
    img = np.array([0.30, 0.34, 0.20]) * (0.8 + 0.3 * _noise(n, n, 27))[..., None]
    img = np.where((rust > 0.68)[..., None], np.array([0.36, 0.20, 0.10]) * (0.8 + 0.3 * rust)[..., None], img)
    for h in (0.33, 0.66):
        img[np.abs(v - h) < 0.025] *= 0.55
        img[np.abs(v - h - 0.03) < 0.01] *= 1.3
    img[(v > 0.45) & (v < 0.55)] = img[(v > 0.45) & (v < 0.55)] * 0.5 + np.array([0.55, 0.50, 0.30]) * 0.5
    return _rgba(img)


def tex_tf(get):
    """a tunnel floor bay (9 m wide, 12 m long): u across, v along; wheel ruts, a dashed centre line, a lamp's pool"""
    n = 256
    a = _tile(get('409_10_1'), 2, 3, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    side = 0.62 + 0.38 * np.maximum(np.exp(-(u / 0.22) ** 2), np.exp(-((1 - u) / 0.22) ** 2))      # (the two wall lamps light the floor's edges more)
    p = np.clip(_pool_u(v, 0.15) * side + 0.3 * _pool_u(v, 0.34), 0, 1)                        # (owner 11-13: under the lamps, not between them)
    img = _concrete(a, p, 0.17, 0.78, cool=np.array([0.5, 0.54, 0.54])) * (0.8 + 0.4 * _noise(n, n, 22))[..., None]
    img *= (1 - 0.22 * (np.exp(-((u - 0.27) / 0.06) ** 2) + np.exp(-((u - 0.73) / 0.06) ** 2)))[..., None]
    img[(np.abs(u - 0.5) < 0.012) & (v > 0.25) & (v < 0.75)] = (0.50, 0.38, 0.10)
    return _rgba(img)


def tex_tfw(get):
    """the way-down corridor's floor: the tunnel floor as it was before the lamp pools moved (one soft band mid-bay), the corridor has its own lamps"""
    n = 256
    a = _tile(get('409_10_1'), 2, 3, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    p = np.exp(-((v - 0.5) / 0.22) ** 2)
    img = _concrete(a, p, 0.22, 0.42, cool=np.array([0.5, 0.54, 0.54])) * (0.8 + 0.4 * _noise(n, n, 22))[..., None]
    img *= (1 - 0.22 * (np.exp(-((u - 0.27) / 0.06) ** 2) + np.exp(-((u - 0.73) / 0.06) ** 2)))[..., None]
    img[(np.abs(u - 0.5) < 0.012) & (v > 0.25) & (v < 0.75)] = (0.50, 0.38, 0.10)
    return _rgba(img)


def tex_tc(get):
    """the tunnel's ceiling (u across, v along): lit over the lamps, near the walls"""
    n = 128
    a = _tile(get('436_11_1'), 2, 2, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    side = 0.45 + 0.55 * np.maximum(np.exp(-(u / 0.25) ** 2), np.exp(-((1 - u) / 0.25) ** 2))
    return _rgba(_concrete(a, np.clip(_pool_u(v, 0.15) * side + 0.25 * _pool_u(v, 0.32), 0, 1), 0.10, 0.52))


def tex_tch(get):
    """the chamfer between wall and ceiling (u along, v across 0-0.2): right over the lamps, the brightest of the ceiling"""
    n = 128
    a = _tile(get('436_11_1'), 2, 2, n, n)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    return _rgba(_concrete(a, np.clip(_pool_u(u, 0.12) + 0.3 * _pool_u(u, 0.32), 0, 1), 0.10, 0.70))


def _hazard(w, h, band=40):
    y, x = np.mgrid[0:h, 0:w]
    k = ((x + y) // band) % 2
    return np.where(k[..., None] > 0, np.array([0.05, 0.05, 0.05]), np.array([0.62, 0.47, 0.07]))


def tex_gate(get, sand=False, outside=False):
    """a blast gate (10.6 x 6.75 m): riveted steel panels, hazard band at the foot, a stencil. sand: the inner face of the sand door;
    outside: its outer face, sand-painted plates with no marking at all, it is a hidden door"""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1024, 512
    a = _tile(get('432_06_1'), 2, 1, W, H) if outside else _tile(get('406_49_1'), 4, 2, W, H)
    v, u = np.mgrid[0:1:H * 1j, 0:1:W * 1j]
    img = a * (0.82 + 0.3 * _noise(H, W, 31))[..., None]
    if outside:                                             # (judge R11: the sand tile x 2.6 clipped to one flat white, rendered flat brown; now sand-painted steel plates, as bright: the Door renders it at about half)
        st = _tile(get('406_49_1'), 6, 3, W, H)
        lum = st[..., :3].mean(2) / max(float(st[..., :3].mean()), 1e-3)
        img = np.array([1.0, 0.86, 0.62]) * ((0.70 + 0.30 * np.clip(lum, 0.4, 1.8)) * (0.84 + 0.24 * _noise(H, W, 31)))[..., None]
        streak = _noise(H, W, 36, (2, 48, 96))                 # rust and dust run down from the joints
        img *= (0.90 + 0.16 * streak)[..., None]
        for x_ in np.arange(0.0, 1.0, 1.0 / 6.0):              # plate joints: a dark seam, a lit lip
            k = int(x_ * W)
            img[:, k:k + 4] *= 0.5
            img[:, k + 4:k + 6] *= 1.15
        for y_ in (0.34, 0.67):
            k = int(y_ * H)
            img[k:k + 4, :] *= 0.5
            img[k + 4:k + 6, :] *= 1.15
        for x_ in np.arange(0.0, 1.0, 1.0 / 6.0):              # rivets along the seams
            for yy in range(10, H - 10, 26):
                k = int(x_ * W) + 10
                img[yy:yy + 4, k:k + 4] *= 0.62
                img[yy:yy + 2, k:k + 2] *= 1.3
        for y_ in (0.34, 0.67):
            for xx in range(12, W - 12, 26):
                k = int(y_ * H) + 10
                img[k:k + 4, xx:xx + 4] *= 0.62
                img[k:k + 2, xx:xx + 2] *= 1.3
        d = np.clip((v - 0.72) / 0.2, 0, 1) * (0.35 + 0.65 * _noise(H, W, 35, (3, 6, 12)))     # sand drifted up the plates
        sand = _tile(get('432_06_1'), 3, 2, W, H)[..., :3] * np.array([0.92, 0.98, 1.08]) * 1.9
        img = img * (1 - d[..., None]) + np.clip(sand, 0, 1) * d[..., None]
    else:
        hz = _hazard(W, H)
        wear = (0.72 + 0.4 * _noise(H, W, 32))[..., None]
        b = (v > 0.86)
        img[b] = (hz * wear)[b]
        b = (v < 0.05)
        img[b] = (hz * wear)[b]
    if outside:
        return _rgba(img)
    for x_ in (0.0, 0.25, 0.5, 0.75):                       # panel joints, the leaf's ribs
        k = int(x_ * W)
        img[:, k:k + 5] *= 0.35
    for y_ in (0.28, 0.56):
        k = int(y_ * H)
        img[k:k + 5, :] *= 0.35
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', 92)
        f2 = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', 34)
    except OSError:
        f = f2 = ImageFont.load_default()
    import altex
    t = 'GATE 2' if sand else 'BLAST DOOR'
    ta = altex._shape_ar('البوابة 2' if sand else 'باب واقي')       # (judge M22 11-14: Arabic over the English, like the door signs)
    t2 = altex._shape_ar('ابتعد') + '  /  KEEP CLEAR'
    fa = ImageFont.truetype(r'C:\Windows\Fonts\segoeuib.ttf', 50)
    f = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', 44)  # (judge R14: one stencil over the middle read 'LAST DOOR' from the tunnel bend: one on each half)
    f2 = ImageFont.truetype(r'C:\Windows\Fonts\segoeuib.ttf', 24)
    for cx_ in (0.25 * W + 6, 0.75 * W + 6):               # one stencil on each half of the leaf, clear of the 0.5 joint, between the 0.28 / 0.56 ribs
        for s_, fn_, y_ in ((ta, fa, 150), (t, f, 212), (t2, f2, 256)):
            tw_ = d.textlength(s_, font=fn_)
            assert tw_ < 0.44 * W, (s_, tw_)
            d.text((cx_ - tw_ / 2, y_), s_, font=fn_, fill=(170, 146, 76))
    return _rgba(np.asarray(im, float) / 255.0)


def tex_hz(get):
    wear = (0.72 + 0.4 * _noise(128, 128, 33))[..., None]
    return _rgba(_hazard(128, 128, 32) * wear)


def tex_lamp(get):
    return _rgba(np.tile(np.array([1.0, 0.92, 0.72]), (32, 32, 1)))


def tex_drn(get):
    """a steel drain grate in the tunnel floor (mapped 0..1): a dark frame, bars across, black between"""
    n = 64
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    img = np.zeros((n, n, 3)) + np.array([0.05, 0.05, 0.05])
    bar = (np.abs(((u * 9) % 1.0) - 0.5) > 0.28)
    img = np.where(bar[..., None], np.array([0.30, 0.29, 0.27]) * (0.8 + 0.4 * _noise(n, n, 39))[..., None], img)
    edge = (u < 0.08) | (u > 0.92) | (v < 0.12) | (v > 0.88)
    img = np.where(edge[..., None], np.array([0.34, 0.33, 0.30]), img)
    return _rgba(img)


def tex_lampb(get):
    """a caged bulkhead lamp's face (judge R15): dark steel rim, a frosted lens bright in its middle, three cage bars across it. Mapped 0..1 on the lens"""
    n = 128
    v, u = np.mgrid[-1:1:n * 1j, -1:1:n * 1j]
    r = np.maximum(np.abs(u), np.abs(v) * 1.0)
    lens = np.clip(1.0 - 0.45 * (u ** 2 + v ** 2), 0, 1)
    img = np.array([1.0, 0.90, 0.68]) * (0.62 + 0.38 * lens)[..., None]
    img = np.where((r > 0.80)[..., None], np.array([0.20, 0.21, 0.22]) * (0.8 + 0.4 * _noise(n, n, 38))[..., None], img)
    img = np.where(((r > 0.74) & (r <= 0.80))[..., None], np.array([0.42, 0.40, 0.36]), img)
    for c_ in (-0.4, 0.0, 0.4):                              # the cage
        img = np.where((np.abs(u - c_) < 0.05)[..., None] & (r <= 0.80)[..., None], np.array([0.16, 0.16, 0.17]), img)
    img = np.where((np.abs(v) < 0.04)[..., None] & (r <= 0.80)[..., None], np.array([0.16, 0.16, 0.17]), img)
    return _rgba(img)


def tex_rail(get):
    """safety-yellow paint on a steel pipe (judge R12, the shaft rail): worn to the steel in places, grime"""
    n = 128
    st = _tile(get('406_49_1'), 2, 2, n, n)[..., :3]
    wear = _noise(n, n, 39, (4, 8, 16, 32))
    paint = np.array([0.78, 0.60, 0.10]) * (0.82 + 0.3 * _noise(n, n, 40))[..., None]
    img = np.where((wear > 0.72)[..., None], st * 0.9, paint)
    img *= (0.85 + 0.2 * _noise(n, n, 41, (2, 32, 64)))[..., None]
    return _rgba(img)


def tex_paint(get):
    return _rgba((0.62 + 0.25 * _noise(64, 64, 34, (4, 8, 16)))[..., None] * np.array([0.72, 0.54, 0.12]))


def tex_sign(get):
    """the checkpoint sign: white stencil on red"""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 512, 128
    a = np.zeros((H, W, 3)) + np.array([0.46, 0.08, 0.06])
    a *= (0.8 + 0.3 * _noise(H, W, 37))[..., None]
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    import altex
    fa = ImageFont.truetype(r'C:\Windows\Fonts\segoeuib.ttf', 44)     # (judge M22 11-14: Arabic over the English)
    f = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', 38)
    ta, t = altex._shape_ar('نقطة تفتيش'), 'CHECKPOINT'
    d.text(((W - d.textlength(ta, font=fa)) / 2, 8), ta, font=fa, fill=(214, 206, 188))
    d.text(((W - d.textlength(t, font=f)) / 2, 72), t, font=f, fill=(214, 206, 188))
    d.rectangle((6, 6, W - 7, H - 7), outline=(214, 206, 188), width=4)
    return _rgba(np.asarray(im, float) / 255.0)


SAND_TILE = 4.8                                            # (metres per repeat of tex_dune: two of the ground's ripple tiles, four of its grit; world-planar like the ground)
DUNE_TINT = (0.823, 0.882, 1.069)                         # (11-12, tour 5ad05d93 gap portal pad v1 at the apron's seam: the old cover rendered 0.612 0.470 0.298 from texture 0.647 0.615 0.551 (gain 0.95 0.76 0.54), the ground beside it 0.533 0.414 0.276; round 2, tour 7c823d76: the dune 9 / 4 % over the ground beside it at back 20 / right side, x 0.94 0.94 0.93)


def _terrain_tex(name):
    from PIL import Image
    return np.asarray(Image.open(os.path.join(TERRAIN_TEX, name)).convert('RGB'), float) / 255.0


TERRAIN_TEX = os.path.join(r'C:\Users\1qdeath\Games\IGI2\app', 'MISSIONS', 'multiplayer', 'sandstorm', 'textures')


def tex_dune(get):
    """owner 11-12: the ground's own sand for the dune cover: sand1 (the ripples) tiled twice and sand2 (the grit) four times over SAND_TILE m, grit as the ground's detail
    pass (multiplied round its mean), then DUNE_TINT"""
    n = 512
    s1 = _tile(_terrain_tex('sand1.tga'), 2, 2, n, n)
    s2 = _tile(_terrain_tex('sand2.tga'), 4, 4, n, n)
    g = s2 / s2.reshape(-1, 3).mean(0)
    rip = s1.mean(2, keepdims=True) / s1.mean()                 # (11-12 walk dune1: at the seam the ground showed grit, no ripples (its sand1 tile is broad): the ripples down to 12 %)
    img = s1.reshape(-1, 3).mean(0) * (1.0 + 0.12 * (rip - 1.0)) * (0.55 + 0.45 * g) * np.asarray(DUNE_TINT)
    return _rgba(img)


def tex_rev(get):
    """orchestrator 11-12: cast concrete for the portal's revetments, frame and lintel (409_17_1's tile grid read as a dark tiled plane; a sand-stained try read as
    see-through against the drift): cool grey, formwork lift lines every 1.2 m, tie holes, faint rain streaks; lit evenly like ss_dune. 4 m a tile"""
    n = 256
    rng = np.random.default_rng(83)
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    a = np.array([0.60, 0.60, 0.585]) * (0.90 + 0.14 * _noise(n, n, 84))[..., None]
    a *= (0.95 + 0.07 * _noise(n, n, 85, (2, 64, 128)))[..., None]
    for k in range(1, 4):                                      # formwork lifts (4 m tile, 1.2-1.4 m apart) and tie holes along them
        y_ = int(k * n / 3.3)
        a[y_:y_ + 2] *= 0.72
        a[y_ + 2:y_ + 3] *= 1.08
        for x_ in range(12, n, 32):
            a[y_ - 9:y_ - 6, x_:x_ + 3] *= 0.55
    for x_ in rng.integers(0, n - 5, 10):                      # faint rain streaks
        a[:, x_:x_ + int(rng.integers(2, 4))] *= 0.94
    for _ in range(40):                                        # chips and pores
        x_, y_ = rng.integers(0, n - 4, 2)
        a[y_:y_ + int(rng.integers(1, 4)), x_:x_ + int(rng.integers(1, 4))] *= 0.78
    return _rgba(a)

def tex_rock(get):
    """the terrain's own rock face (rock_01.tga), for the half-buried rocks"""
    return _rgba(_tile(_terrain_tex('rock_01.tga'), 1, 1, 256, 256) * np.asarray(DUNE_TINT) * 0.95)


def tex_scrub(get):
    """dry desert scrub seen close: grey-olive twigs and leaves over shade"""
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(81)
    im = Image.new('RGB', (128, 128), (70, 66, 46))
    d = ImageDraw.Draw(im)
    for _ in range(260):
        x, y = rng.integers(0, 128, 2)
        c = [(118, 112, 70), (96, 98, 60), (140, 128, 86), (58, 54, 36)][int(rng.integers(0, 4))]
        d.line([x, y, x + rng.integers(-6, 7), y + rng.integers(-6, 7)], fill=c, width=int(rng.integers(1, 3)))
    return _rgba(np.asarray(im, float) / 255.0)


def tex_track(get):
    """a tyre track in the sand: the dune sand pressed darker, tread bars across"""
    a = tex_dune(get)[..., :3][:128, :128] * 0.78
    v = np.arange(128)[:, None]
    a = np.where(((v // 8) % 2 == 0)[..., None], a * 0.88, a)
    return _rgba(a)


def _dim(name, tint):
    return lambda get: _rgba(np.asarray(get(name), float)[..., :3] * np.asarray(tint))


TEXTURES = {'ss_bw': tex_bw, 'ss_bu': tex_bu, 'ss_bf': tex_bf, 'ss_bc': tex_bc, 'ss_tw': tex_tw, 'ss_tf': tex_tf, 'ss_tfw': tex_tfw, 'ss_tc': tex_tc,
            'ss_gate': tex_gate, 'ss_sgate': lambda g: tex_gate(g, True, True), 'ss_sgatei': lambda g: tex_gate(g, True), 'ss_hz': tex_hz, 'ss_lamp': tex_lamp, 'ss_lampb': tex_lampb, 'ss_tch': tex_tch, 'ss_drn': tex_drn, 'ss_tw2': tex_tw2, 'ss_drum': tex_drum, 'ss_rail': tex_rail, 'ss_paint': tex_paint,
            'ss_shc': _dim('400_83_1', (0.40, 0.44, 0.42)), 'ss_sign': tex_sign, 'ss_cc': _dim('409_17_1', (0.40, 0.44, 0.42)), 'ss_corr': _dim('433_12_1', (0.36, 0.40, 0.38)), 'ss_duct': _dim('409_20_1', (0.36, 0.38, 0.38)),
            'ss_stl': _dim('406_49_1', (0.62, 0.66, 0.62)), 'ss_sand': _dim('432_06_1', (0.92, 0.98, 1.08)), 'ss_dune': tex_dune, 'ss_rev': tex_rev, 'ss_rock': tex_rock, 'ss_scrub': tex_scrub, 'ss_track': tex_track}   # (owner 11-12: ss_sand = the ground's own sand, was 432_06_1 x tint)


# ------------------------------------------------------------------------------------------------ mesh helper
class Mesh:
    """parts per texture slot, world metres, around `origin`"""
    def __init__(self, origin, slots):
        self.o, self.slots = np.asarray(origin, float), list(slots)
        self.g = {s: [] for s in slots}
        self.coll, self.glow = [], []

    def quad(self, slot, a, b, c, d, n, uv=None):
        """four corners in order round the face (world m), n = the side it faces (seen from there); uv per corner"""
        Q = (np.array([a, b, c, d], float) - self.o) * M
        n = np.asarray(n, float); n = n / np.linalg.norm(n)
        Tr = SL._orient(Q, np.array([(0, 1, 2), (0, 2, 3)]), np.tile(n, (4, 1)), np.tile(n, (2, 1)))
        Uv = np.array(uv if uv is not None else [(0, 1), (1, 1), (1, 0), (0, 0)], float)
        self.g[slot].append((Q, Tr, np.tile(n, (4, 1)), Uv))

    def box(self, slot, x0, y0, z0, x1, y1, z1, uv=0.25, solid=True):
        o = self.o
        p = BP.box_m(x0 - o[0], y0 - o[1], z0 - o[2], x1 - o[0], y1 - o[1], z1 - o[2], uv=uv)
        if slot:
            self.g[slot].append(p)
        if solid:
            self.coll.append(p)

    def hull(self, slot, pts, uv=0.25, solid=True):
        p = MK.hull_m(np.asarray(pts, float) - self.o, uv=uv)
        if slot:
            self.g[slot].append(p)
        if solid:
            self.coll.append(p)

    def cyl(self, slot, r, a0, a1, axis, at, uv=0.5, seg=10):
        """a pipe along 'x' / 'y' from a0 to a1; at = the other two world coordinates"""
        o = self.o
        ax = 0 if axis == 'x' else 1
        at2 = (at[0] - o[1 - ax], at[1] - o[2])
        self.g[slot].append(BP.cyl_axis(r, a0 - o[ax], a1 - o[ax], axis, seg, at=at2, uv=uv))

    def lamp(self, p, size=900.0, rgb=(1.0, 0.82, 0.55)):
        self.glow.append(((p[0] - self.o[0]) * M, (p[1] - self.o[1]) * M, (p[2] - self.o[2]) * M, size, rgb))

    def model(self, alpha=(), even=()):
        even = tuple(s_ for s_ in tuple(even) + tuple(getattr(self, 'even_default', ())) if s_ in self.g)     # (a model can ask for its own evenly lit slots: the portal's ss_dune; the builder still passes ss_sand, which it no longer has)
        """even = slots lit evenly: the engine lights vertex-lit faces from the level's SUN by their normals, underground a wall facing it stood out bright
        (rv2): every normal up, the light is baked into the textures"""
        for s in even:
            self.g[s] = [(P_, T_, np.tile((0.0, 0.0, 1.0), (len(P_), 1)), U_) for P_, T_, N_, U_ in self.g[s]]
        groups = [(i, self.g[s]) for i, s in enumerate(self.slots) if self.g[s]]
        gl = None
        if self.glow:
            gl = np.zeros(len(self.glow), mefmesh.WOLG_DT)
            for i, (x, y, z, sz, c) in enumerate(self.glow):
                gl[i] = ((x, y, z), sz, c[0], c[1], c[2], 0xABABABAB)
        return MK.model(groups, self.coll, glows=gl, alpha_slots=tuple(i for i, s in enumerate(self.slots) if s in alpha))


def _cut(a0, a1, cuts):
    """the intervals of a0..a1 outside the sorted (c0, c1) cuts"""
    out, a = [], a0
    for c0, c1 in sorted(cuts):
        if c0 > a:
            out.append((a, c0))
        a = max(a, c1)
    if a < a1:
        out.append((a, a1))
    return out


def wall(me, plane_axis, plane, face, t0, t1, z0, z1, slot, ztop=None, H=None, tbase=0.0, step=BAY):
    """a wall plane x = plane (plane_axis 'x') or y = plane, seen from side `face` (+1 / -1 along the axis), bay by bay: u per `step` m,
    v from the bay's top ztop over H m (the texture's light stays on the bays)"""
    ztop = z1 if ztop is None else ztop
    H = (z1 - z0) if H is None else H
    t = t0
    while t < t1 - 1e-6:
        k = math.floor((t - tbase) / step + 1e-9)
        t2 = min(tbase + (k + 1) * step, t1)
        u0, u1 = (t - tbase) / step - k, (t2 - tbase) / step - k
        v0, v1 = (ztop - z1) / H, (ztop - z0) / H
        pt = (lambda t_, z_: (plane, t_, z_)) if plane_axis == 'x' else (lambda t_, z_: (t_, plane, z_))
        n = (face, 0, 0) if plane_axis == 'x' else (0, face, 0)
        me.quad(slot, pt(t, z0), pt(t2, z0), pt(t2, z1), pt(t, z1), n, [(u0, v1), (u1, v1), (u1, v0), (u0, v0)])
        t = t2


# ------------------------------------------------------------------------------------------------ the hall
HALL_SLOTS = ['ss_bw', 'ss_bu', 'ss_bf', 'ss_bc', 'ss_lamp', 'ss_paint', 'ss_hz', 'ss_stl', 'ss_duct', 'ss_corr', '560_04_1', 'ss_cc',
              '400_82_1', 'sr_glass', '436_05_1', '400_94_1', '433_13_1_argb8888']
S_MESH = '433_13_1_argb8888'
S_STEEL, S_DUCT, S_CORR, S_DOOR, S_PLAIN, S_PLATE, S_GLASS, S_FAN, S_PANEL = 'ss_stl', 'ss_duct', 'ss_corr', '560_04_1', 'ss_cc', '400_82_1', 'sr_glass', '436_05_1', '400_94_1'
ORIGIN = ((X0 + X1) / 2, (Y0 + Y1) / 2, F)


def box_in(me, slot, x0, y0, z0, x1, y1, z1, skip=''):
    """six faces looking INTO a box: dark rock behind thin walls"""
    me.quad(slot, (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (0, 0, 1))
    me.quad(slot, (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (0, 0, -1))
    me.quad(slot, (x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (0, 1, 0))
    me.quad(slot, (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1), (0, -1, 0))
    if '-' not in skip:
        me.quad(slot, (x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1), (1, 0, 0))
    if '+' not in skip:
        me.quad(slot, (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), (-1, 0, 0))


def hall_model():
    me = Mesh(ORIGIN, HALL_SLOTS)
    t = 1.0
    # --- floor: bays (the pit bay left out), a thick slab under them
    for i in range(int((X1 - X0) / BAY)):
        for j in range(int((Y1 - Y0) / BAY)):
            x, y = X0 + i * BAY, Y0 + j * BAY
            if (x, y) == (PIT[0], PIT[1]):
                continue
            me.quad('ss_bf', (x, y, F), (x + BAY, y, F), (x + BAY, y + BAY, F), (x, y + BAY, F), (0, 0, 1))
    me.box(None, X0 - t, Y0 - t, F - t, PIT[0], Y1 + t, F)
    me.box(None, PIT[2], Y0 - t, F - t, X1 + 2.0, Y1 + t, F)      # (owner 11-04: a gap between the gate and the tunnel, fall hazard: the slab runs on under both)
    me.box(S_STEEL, X1 - 0.1, GATE_Y0 - 0.3, F - 0.3, X1 + 1.7, GATE_Y1 + 0.3, F + 0.012, uv=0.25, solid=False)   # (owner 65: the plate's bright sand tone made a pale strip across the road at the open gate)
    me.box(None, PIT[0], Y0 - t, F - t, PIT[2], PIT[1], F)
    me.box(None, PIT[0], PIT[3], F - t, PIT[2], Y1 + t, F)
    # --- ceilings
    for j in range(int((Y1 - Y0) / BAY)):
        y = Y0 + j * BAY
        for i in range(int((X1 - X0) / BAY)):
            x = X0 + i * BAY
            z = CG if x < XS else CS
            me.quad('ss_bc', (x, y, z), (x + BAY, y, z), (x + BAY, y + BAY, z), (x, y + BAY, z), (0, 0, -1))
    me.box(None, X0 - t, Y0 - t, CG, XS, Y1 + t, CG + 0.6)
    me.box(None, XS, Y0 - t, CS, X1 + t, Y1 + t, CS + 0.6)
    # --- walls: west (the lobby doorway), south + north, the step over the gallery, east (the gate)
    dy0, dy1, dh = LOBBY_DOOR
    me.box('ss_bf', 170.9, dy0, F - 0.3, X0, dy1, F, uv=0.25)   # (owner 61: the doorway from the lift had no floor of its own, the sky colour showed through a strip of it)
    if GUNROOM:                                             # (the gun room goes through this wall: the wall above and below it, the lobby door under it)
        import ssgun
        c0, c1, cz0, cz1 = ssgun.HALL_CUT
        for a, b in ((Y0, c0), (c1, Y1)):
            wall(me, 'x', X0, 1, a, b, F, CG, 'ss_bw', tbase=Y0)
            me.box(None, X0 - t, a - (t if a == Y0 else 0.0), F, X0, b + (t if b == Y1 else 0.0), CG + 0.6)
        for a, b in ((c0, dy0), (dy1, c1)):
            wall(me, 'x', X0, 1, a, b, F, cz0, 'ss_bw', ztop=CG, H=13.0, tbase=Y0)
            me.box(None, X0 - t, a, F, X0, b, cz0)
        wall(me, 'x', X0, 1, dy0, dy1, F + dh, cz0, 'ss_bw', ztop=CG, H=13.0, tbase=Y0)
        me.box(None, X0 - t, dy0, F + dh, X0, dy1, cz0)
        wall(me, 'x', X0, 1, c0, c1, cz1, CG, 'ss_bw', ztop=CG, H=13.0, tbase=Y0)
        me.box(None, X0 - t, c0, cz1, X0, c1, CG + 0.6)
    else:
        for a, b in _cut(Y0, Y1, [(dy0, dy1)]):
            wall(me, 'x', X0, 1, a, b, F, CG, 'ss_bw', tbase=Y0)
        wall(me, 'x', X0, 1, dy0, dy1, F + dh, CG, 'ss_bw', ztop=CG, H=13.0, tbase=Y0)
        me.box(None, X0 - t, Y0 - t, F, X0, dy0, CG + 0.6); me.box(None, X0 - t, dy1, F, X0, Y1 + t, CG + 0.6)
        me.box(None, X0 - t, dy0, F + dh, X0, dy1, CG + 0.6)
    me.box(S_STEEL, X0 - 1.25, dy0 - 0.16, F, X0 + 0.04, dy0, F + dh + 0.16, uv=0.5)   # the doorway's steel frame (its reveals)
    me.box(S_STEEL, X0 - 1.25, dy1, F, X0 + 0.04, dy1 + 0.16, F + dh + 0.16, uv=0.5)
    me.box(S_STEEL, X0 - 1.25, dy0, F + dh, X0 + 0.04, dy1, F + dh + 0.16, uv=0.5)
    for yw, fc in ((Y0, 1), (Y1, -1)):
        wall(me, 'y', yw, fc, X0, X1, F, F + 13.0, 'ss_bw', tbase=X0)
        wall(me, 'y', yw, fc, XS, X1, F + 13.0, CS, 'ss_bu', tbase=X0)
    me.box(None, X0 - t, Y0 - t, F, X1 + t, Y0, CS + 0.6); me.box(None, X0 - t, Y1, F, X1 + t, Y1 + t, CS + 0.6)
    wall(me, 'x', XS, 1, Y0, Y1, CG, CS, 'ss_bu', tbase=Y0)
    me.box(None, XS - 0.2, Y0, CG, XS, Y1, CS)
    gy0, gy1, gh = GATE_Y0, GATE_Y1, GATE_H
    for a, b in _cut(Y0, Y1, [(gy0, gy1)]):
        wall(me, 'x', X1, -1, a, b, F, F + 13.0, 'ss_bw', tbase=Y0)
    wall(me, 'x', X1, -1, gy0, gy1, F + gh, F + 13.0, 'ss_bw', ztop=F + 13.0, H=13.0, tbase=Y0)
    wall(me, 'x', X1, -1, Y0, Y1, F + 13.0, CS, 'ss_bu', tbase=Y0)
    # the gate wall: 0.4 m front leaf, the slot (0.3 m), 0.4 m back leaf, thick concrete above
    for x0, x1 in ((X1, X1 + 0.4), (X1 + 0.8, X1 + 1.3)):
        me.box(None, x0, Y0 - t, F, x1, gy0, CS + 0.6); me.box(None, x0, gy1, F, x1, Y1 + t, CS + 0.6)
    me.box(None, X1, gy0, F + gh, X1 + 0.4, gy1, CS + 0.6)
    me.box(None, X1 + 0.8, gy0, F + gh, X1 + 1.3, gy1, CS + 0.6)
    me.box(None, X1 + 0.4, Y0 - t, F + gh + 7.2, X1 + 0.8, Y1 + t, CS + 0.6)
    me.box(None, X1 + 0.4, Y0 - t, F, X1 + 0.8, gy0 - 0.25, F + gh + 7.2); me.box(None, X1 + 0.4, gy1 + 0.25, F, X1 + 0.8, Y1 + t, F + gh + 7.2)
    for a, b in ((gy0 - 0.7, gy0), (gy1, gy1 + 0.7)):       # hazard-striped jambs + the lintel beam: the gate reads as a gate
        me.box('ss_hz', X1 - 0.12, a, F, X1 + 0.4, b, F + gh + 0.7, uv=0.5, solid=True)
    me.box('ss_hz', X1 - 0.12, gy0 - 0.7, F + gh, X1 + 0.4, gy1 + 0.7, F + gh + 0.7, uv=0.5)
    me.box(S_STEEL, X1 - 0.5, gy0 - 1.1, F + gh + 0.7, X1, gy1 + 1.1, F + gh + 1.3, uv=0.5, solid=False)
    # --- the step's girder + the columns under it
    me.box(S_STEEL, XS - 0.6, Y0, CG - 1.4, XS + 0.6, Y1, CG + 0.2, uv=0.25, solid=False)
    for y in (208.0, 232.0 + 12.0):
        me.box(S_PLAIN, XS - 0.6, y - 0.6, F, XS + 0.6, y + 0.6, CG - 1.4)
        me.box('ss_hz', XS - 0.64, y - 0.64, F, XS + 0.64, y + 0.64, F + 1.3, uv=0.75, solid=False)
    # --- the gallery: roof girders, columns, ducts, lamps
    for k in range(1, 5):
        x = X0 + k * BAY
        me.box(S_STEEL, x - 0.25, Y0, CG - 0.9, x + 0.25, Y1, CG, uv=0.25, solid=False)
    for x in (196.0, 220.0):
        for y in (208.0, 244.0):
            me.box(S_PLAIN, x - 0.5, y - 0.5, F, x + 0.5, y + 0.5, CG - 0.9)
            me.box('ss_hz', x - 0.54, y - 0.54, F, x + 0.54, y + 0.54, F + 1.3, uv=0.75, solid=False)
    me.box(S_DUCT, X0, Y1 - 3.0, CG - 2.6, XS - 0.6, Y1 - 1.6, CG - 1.5, uv=0.25, solid=False)
    me.box(S_DUCT, X0, Y0 + 1.6, CG - 2.6, XS - 0.6, Y0 + 3.0, CG - 1.5, uv=0.25, solid=False)
    for x in np.arange(180.0, 230.0, 12.0):
        me.box(S_STEEL, x - 0.05, Y1 - 3.05, CG - 1.5, x + 0.05, Y1 - 1.55, CG, solid=False)
        me.box(S_STEEL, x - 0.05, Y0 + 1.55, CG - 1.5, x + 0.05, Y0 + 3.05, CG, solid=False)
    me.cyl(S_DUCT, 0.16, X0, XS, 'x', (Y1 - 0.4, F + 7.6))
    me.cyl(S_DUCT, 0.11, X0, XS, 'x', (Y1 - 0.4, F + 7.1))
    me.cyl(S_DUCT, 0.16, X0, X1, 'x', (Y0 + 0.4, F + 7.6))
    me.quad(S_FAN, (X0 + 0.02, 244.0, F + 6.0), (X0 + 0.02, 247.0, F + 6.0), (X0 + 0.02, 247.0, F + 9.0), (X0 + 0.02, 244.0, F + 9.0), (1, 0, 0))
    me.quad(S_FAN, (X0 + 0.02, 204.0, F + 6.0), (X0 + 0.02, 207.0, F + 6.0), (X0 + 0.02, 207.0, F + 9.0), (X0 + 0.02, 204.0, F + 9.0), (1, 0, 0))
    for i in range(5):
        for j in range(5):
            x, y = X0 + (i + 0.5) * BAY, Y0 + (j + 0.5) * BAY
            me.box('ss_lamp', x - 1.3, y - 0.14, CG - 1.4, x + 1.3, y + 0.14, CG - 1.25, solid=False)
            me.box(S_STEEL, x - 1.4, y - 0.2, CG - 1.26, x + 1.4, y + 0.2, CG - 1.14, solid=False)
            for dx in (-1.1, 1.1):
                me.box(S_STEEL, x + dx - 0.02, y - 0.02, CG - 1.14, x + dx + 0.02, y + 0.02, CG, solid=False)
            me.lamp((x, y, CG - 1.5))
    # --- the silo hall: wall floods, crane rails, the crane over the pit
    for i in range(3):
        x = XS + (i + 0.5) * BAY
        for yw, s in ((Y0, 1), (Y1, -1)):
            me.box('ss_lamp', x - 0.7, yw + s * 0.5 - 0.1, F + 11.0, x + 0.7, yw + s * 0.5 + 0.1, F + 11.3, solid=False)
            me.box(S_STEEL, x - 0.9, min(yw, yw + s * 0.45), F + 11.3, x + 0.9, max(yw, yw + s * 0.7), F + 11.5, solid=False)
            me.lamp((x, yw + s * 0.8, F + 10.9), 1400.0)
        for j in range(5):
            y = Y0 + (j + 0.5) * BAY
            me.box('ss_lamp', x - 1.3, y - 0.14, CS - 1.4, x + 1.3, y + 0.14, CS - 1.25, solid=False)
            me.box(S_STEEL, x - 1.4, y - 0.2, CS - 1.26, x + 1.4, y + 0.2, CS - 1.14, solid=False)
            for dx in (-1.1, 1.1):
                me.box(S_STEEL, x + dx - 0.02, y - 0.02, CS - 1.14, x + dx + 0.02, y + 0.02, CS, solid=False)
            me.lamp((x, y, CS - 1.5), 1100.0)
    for y0, y1 in ((Y0, Y0 + 1.2), (Y1 - 1.2, Y1)):
        me.box(S_STEEL, XS, y0, F + 19.0, X1, y1, F + 20.0, uv=0.25, solid=False)
    me.box(S_STEEL, 248.6, Y0 + 1.0, F + 20.0, 251.4, Y1 - 1.0, F + 21.4, uv=0.25, solid=False)   # the bridge
    me.box('ss_hz', 248.55, Y0 + 1.0, F + 20.3, 251.45, Y1 - 1.0, F + 20.9, uv=0.5, solid=False)
    me.box(S_STEEL, 247.8, PIT_C[1] - 9.6, F + 19.0, 252.2, PIT_C[1] - 6.4, F + 20.0, uv=0.5, solid=False)   # the trolley
    me.box(S_DUCT, 249.97, PIT_C[1] - 8.03, F + 15.2, 250.03, PIT_C[1] - 7.97, F + 19.0, solid=False)
    me.box(S_STEEL, 249.7, PIT_C[1] - 8.2, F + 14.8, 250.3, PIT_C[1] - 7.8, F + 15.2, solid=False)
    for y_ in (PIT_C[1] - 3.0, PIT_C[1] + 3.0):
        me.box('ss_lamp', 248.9, y_ - 0.5, F + 19.7, 251.1, y_ + 0.5, F + 19.95, solid=False)
        me.lamp((250.0, y_, F + 19.6), 2600.0, (0.78, 0.88, 1.0))
    # --- the pit: walls, floor, rails round it (a bridge to the gantry's first platform on the west side)
    px0, py0, px1, py1 = PIT
    wall(me, 'x', px0, 1, py0, py1, PIT_Z, F, S_PANEL, H=5.0, tbase=py0, step=4.0)
    wall(me, 'x', px1, -1, py0, py1, PIT_Z, F, S_PANEL, H=5.0, tbase=py0, step=4.0)
    wall(me, 'y', py0, 1, px0, px1, PIT_Z, F, S_PANEL, H=5.0, tbase=px0, step=4.0)
    wall(me, 'y', py1, -1, px0, px1, PIT_Z, F, S_PANEL, H=5.0, tbase=px0, step=4.0)
    me.box(S_PLATE, px0, py0, PIT_Z - 0.5, px1, py1, PIT_Z, uv=0.25)
    for bx in ((px0 - 0.5, py0, px0, py1), (px1, py0, px1 + 0.5, py1), (px0 - 0.5, py0 - 0.5, px1 + 0.5, py0), (px0 - 0.5, py1, px1 + 0.5, py1 + 0.5)):
        me.box(None, bx[0], bx[1], PIT_Z - 0.5, bx[2], bx[3], F)
    for a in ((px0 - 0.3, py0 - 0.3, px1 + 0.3, py0), (px0 - 0.3, py1, px1 + 0.3, py1 + 0.3), (px0 - 0.3, py0 - 0.3, px0, py1 + 0.3), (px1, py0 - 0.3, px1 + 0.3, py1 + 0.3)):
        me.box('ss_hz', a[0], a[1], F, a[2], a[3], F + 0.03, uv=0.5, solid=False)
    bry0, bry1 = PIT_C[1] - 1.1, PIT_C[1] + 1.1
    me.box(S_PLATE, px0, bry0, F - 0.1, PIT_C[0] - 3.45, bry1, F, uv=0.25)
    for y_ in (bry0, bry1):                                 # (wb20: nothing kept a man on the bridge: a fall into the pit is a dead end)
        me.box(S_PANEL, px0, y_ - 0.03, F, PIT_C[0] - 3.45, y_ + 0.03, F + 1.08)
    for rail_z in (F + 0.55, F + 1.05):
        for a in ((px0 - 0.05, py0 - 0.05, px1 + 0.05, py0 + 0.03), (px0 - 0.05, py1 - 0.03, px1 + 0.05, py1 + 0.05), (px1 - 0.03, py0, px1 + 0.05, py1)):
            me.box(S_PANEL, a[0], a[1], rail_z - 0.03, a[2], a[3], rail_z + 0.03, solid=False)
        me.box(S_PANEL, px0 - 0.03, py0, rail_z - 0.03, px0 + 0.05, bry0, rail_z + 0.03, solid=False)
        me.box(S_PANEL, px0 - 0.03, bry1, rail_z - 0.03, px0 + 0.05, py1, rail_z + 0.03, solid=False)
    for x in np.arange(px0, px1 + 0.1, 2.0):
        for y in (py0, py1):
            me.box(S_PANEL, x - 0.03, y - 0.03, F, x + 0.03, y + 0.03, F + 1.08, solid=False)
    for y in list(np.arange(py0, bry0 + 0.1, 2.0)) + [bry0, bry1] + list(np.arange(py1, bry1 - 0.1, -2.0)):
        me.box(S_PANEL, px0 - 0.03, y - 0.03, F, px0 + 0.03, y + 0.03, F + 1.08, solid=False)
    for y in np.arange(py0, py1 + 0.1, 2.0):
        me.box(S_PANEL, px1 - 0.03, y - 0.03, F, px1 + 0.03, y + 0.03, F + 1.08, solid=False)
    # (owner 11-04: the missile behind a cage: a mesh fence to 3.4 m all round, one gate on the west side opened from the control station)
    ch = 3.4
    me.box(None, px0 - 0.05, py0 - 0.05, F, px1 + 0.05, py0 + 0.05, F + ch)
    me.box(None, px0 - 0.05, py1 - 0.05, F, px1 + 0.05, py1 + 0.05, F + ch)
    me.box(None, px1 - 0.05, py0, F, px1 + 0.05, py1, F + ch)
    me.box(None, px0 - 0.05, py0, F, px0 + 0.05, bry0, F + ch); me.box(None, px0 - 0.05, bry1, F, px0 + 0.05, py1, F + ch)
    uvf = lambda L_: [(0, ch / 2), (L_ / 2, ch / 2), (L_ / 2, 0), (0, 0)]
    for f_ in (1, -1):
        me.quad(S_MESH, (px0, py0, F), (px1, py0, F), (px1, py0, F + ch), (px0, py0, F + ch), (0, f_, 0), uvf(px1 - px0))
        me.quad(S_MESH, (px0, py1, F), (px1, py1, F), (px1, py1, F + ch), (px0, py1, F + ch), (0, f_, 0), uvf(px1 - px0))
        me.quad(S_MESH, (px1, py0, F), (px1, py1, F), (px1, py1, F + ch), (px1, py0, F + ch), (f_, 0, 0), uvf(py1 - py0))
        me.quad(S_MESH, (px0, py0, F), (px0, bry0, F), (px0, bry0, F + ch), (px0, py0, F + ch), (f_, 0, 0), uvf(bry0 - py0))
        me.quad(S_MESH, (px0, bry1, F), (px0, py1, F), (px0, py1, F + ch), (px0, bry1, F + ch), (f_, 0, 0), uvf(py1 - bry1))
    for x in np.arange(px0, px1 + 0.1, 3.0):
        for y in (py0, py1):
            me.box(S_STEEL, x - 0.06, y - 0.06, F, x + 0.06, y + 0.06, F + ch + 0.05, solid=False)
    for y in (py0, bry0, bry1, py1):
        me.box(S_STEEL, px0 - 0.06, y - 0.06, F, px0 + 0.06, y + 0.06, F + ch + 0.05, solid=False)
    for y in np.arange(py0, py1 + 0.1, 3.0):
        me.box(S_STEEL, px1 - 0.06, y - 0.06, F, px1 + 0.06, y + 0.06, F + ch + 0.05, solid=False)
    for a in ((px0, py0 - 0.05, px1, py0 + 0.05), (px0, py1 - 0.05, px1, py1 + 0.05), (px1 - 0.05, py0, px1 + 0.05, py1), (px0 - 0.05, py0, px0 + 0.05, bry0), (px0 - 0.05, bry1, px0 + 0.05, py1)):
        me.box(S_STEEL, a[0], a[1], F + ch - 0.05, a[2], a[3], F + ch + 0.05, solid=False)
    # --- floor paint: the truck road to the gate, the parking bays
    Z = F + 0.015
    for y in (ROAD_Y - 6.0, ROAD_Y + 6.0):
        me.box('ss_paint', X0 + 2.0, y - 0.09, F, X1 - 0.2, y + 0.09, Z, solid=False, uv=0.5)
    for x in np.arange(X0 + 4.0, X1 - 2.0, 6.0):
        me.box('ss_paint', x, ROAD_Y - 0.07, F, x + 2.6, ROAD_Y + 0.07, Z, solid=False, uv=0.5)
    for cx, cy in TEL_SPOTS:
        for a in ((cx - 8.0, cy - 2.6, cx + 8.0, cy - 2.44), (cx - 8.0, cy + 2.44, cx + 8.0, cy + 2.6),
                  (cx - 8.0, cy - 2.6, cx - 7.84, cy + 2.6), (cx + 7.84, cy - 2.6, cx + 8.0, cy + 2.6)):
            me.box('ss_paint', a[0], a[1], F, a[2], a[3], Z, solid=False, uv=0.5)
    # --- concrete barriers along the road: cover, and something near the walking line
    for cx, cy, ax in COVER:
        L_, b, t_ = 2.0, 0.34, 0.14
        dx_, dy_ = (L_, b) if ax == 'x' else (b, L_)
        ex_, ey_ = (L_, t_) if ax == 'x' else (t_, L_)
        me.hull(S_PLAIN, [(cx + a_ * dx_, cy + c_ * dy_, F) for a_ in (-1, 1) for c_ in (-1, 1)] + [(cx + a_ * ex_, cy + c_ * ey_, F + 1.05) for a_ in (-1, 1) for c_ in (-1, 1)], uv=0.4)
        me.box('ss_hz', cx - ex_, cy - ey_, F + 1.05, cx + ex_, cy + ey_, F + 1.08, uv=0.5, solid=False)
    # --- the quarters: three real rooms along the north wall, each with a real door (owner 11-04: 'doors that do not open')
    qx0, qy0, qx1, qy1 = QUARTERS
    h_, w_ = 3.3, 0.2
    a_ = qx0
    for rx0, rx1 in () if GARRISON2 else ROOMS:
        if rx0 > a_:
            me.box(S_CORR, a_, qy0, F, rx0, qy1, F + h_, uv=0.25)   # (solid store between the rooms)
        c_ = (rx0 + rx1) / 2
        me.box(S_CORR, rx0, qy0, F, c_ - 0.6, qy0 + w_, F + h_, uv=0.25)
        me.box(S_CORR, c_ + 0.6, qy0, F, rx1, qy0 + w_, F + h_, uv=0.25)
        me.box(S_CORR, c_ - 0.6, qy0, F + 2.14, c_ + 0.6, qy0 + w_, F + h_, uv=0.25)
        me.box('ss_lamp', c_ - 1.2, 252.3, F + h_ - 0.05, c_ + 1.2, 252.6, F + h_, solid=False)
        me.lamp((c_, 252.45, F + h_ - 0.15), 500.0)
        a_ = rx1
    if a_ < qx1 and not GARRISON2:
        me.box(S_CORR, a_, qy0, F, qx1, qy1, F + h_, uv=0.25)
    if not GARRISON2:
        me.box(S_STEEL, qx0 - 0.2, qy0 - 0.3, F + h_, qx1 + 0.2, qy1, F + h_ + 0.2, uv=0.25)
    # --- the control room: thick walls, a window band looking on the missile, a door gap in the west wall
    cx0, cy0, cx1, cy1 = CTRL
    w, h, wn = 0.25, CTRL_H, 0.25
    sill, head = 1.05, 2.5
    d0, d1 = CTRL_DOOR_Y
    me.box(S_PLAIN, cx0 - w, cy0 - w, F, cx1 + w, cy0, F + h, uv=0.25)                         # south
    me.box(S_PLAIN, cx1, cy0, F, cx1 + w, cy1 + w, F + h, uv=0.25)                              # east
    me.box(S_PLAIN, cx0 - w, cy0, F, cx0, d0, F + h, uv=0.25); me.box(S_PLAIN, cx0 - w, d1, F, cx0, cy1 + w, F + h, uv=0.25)   # west
    me.box(S_PLAIN, cx0 - w, d0, F + 2.14, cx0, d1, F + h, uv=0.25)
    me.box(S_PLAIN, cx0, cy1, F, cx1, cy1 + wn, F + sill, uv=0.25)                              # north: under + over the windows
    me.box(S_PLAIN, cx0, cy1, F + head, cx1, cy1 + wn, F + h, uv=0.25)
    me.box(S_GLASS, cx0, cy1 + 0.1, F + sill, cx1, cy1 + 0.14, F + head, solid=True, uv=0.25)
    for x in np.arange(cx0, cx1 + 0.1, 2.5):
        me.box(S_STEEL, x - 0.05, cy1 + 0.04, F + sill, x + 0.05, cy1 + 0.2, F + head, solid=False, uv=0.5)
    me.box(S_STEEL, cx0 - w - 0.1, cy0 - w - 0.1, F + h, cx1 + w + 0.1, cy1 + wn + 0.1, F + h + 0.25, uv=0.25)   # the roof
    me.box('ss_lamp', (cx0 + cx1) / 2 - 3.0, (cy0 + cy1) / 2 - 0.15, F + h - 0.1, (cx0 + cx1) / 2 + 3.0, (cy0 + cy1) / 2 + 0.15, F + h, solid=False)
    me.lamp(((cx0 + cx1) / 2, (cy0 + cy1) / 2, F + h - 0.2), 700.0)
    me.box('ss_hz', cx0 - w - 0.02, cy1 + wn, F, cx0 - w, cy1 + wn + 0.02, F + 0.01, solid=False)
    bk = 2.0
    ax0, ay0, ax1, ay1, az0, az1 = X0 - bk, Y0 - bk, X1 + bk, Y1 + bk, PIT_Z - bk, CS + bk
    box_in(me, 'ss_bc', ax0, ay0, az0, XS, ay1, CG + bk, skip='+-x')     # (the gallery's rock stays under the corridor at -15.6: rv8 a box to CS cut the stairs)
    _bw = ((ay0, 221.0, az0, CG + bk), (231.0, ay1, az0, CG + bk), (221.0, 231.0, F + 4.8, CG + bk))
    if GUNROOM:                                             # (this rock face would stand inside the gun room, x 170)
        _c0, _c1, _z0, _z1 = ssgun.HALL_CUT
        _bw = ((ay0, _c0 - 0.5, az0, CG + bk), (_c1 + 0.5, ay1, az0, CG + bk), (_c0 - 0.5, 221.0, az0, _z0), (231.0, _c1 + 0.5, az0, _z0), (221.0, 231.0, F + 4.8, _z0), (_c0 - 0.5, _c1 + 0.5, _z1, CG + bk))
    for y0_, y1_, z0_, z1_ in _bw:   # (west: round the lift vestibule, x 167.8-171: a whole wall stood in it, rv8 r035)
        me.quad('ss_bc', (ax0, y0_, z0_), (ax0, y1_, z0_), (ax0, y1_, z1_), (ax0, y0_, z1_), (1, 0, 0))
    box_in(me, 'ss_bc', XS, ay0, az0, ax1, ay1, az1, skip='+-x')
    gy0_, gy1_, gt_ = GATE_Y0 - 1.6, GATE_Y1 + 1.6, F + GATE_H + 1.6   # (owner 38: this rock face closed the open gate: a dark see-only wall, the tunnel behind it unseen)
    for y0_, y1_, z0_, z1_ in ((ay0, gy0_, az0, az1), (gy1_, ay1, az0, az1), (gy0_, gy1_, gt_, az1), (gy0_, gy1_, az0, F - 1.0)):
        me.quad('ss_bc', (ax1, y0_, z0_), (ax1, y1_, z0_), (ax1, y1_, z1_), (ax1, y0_, z1_), (-1, 0, 0))
    me.quad('ss_bc', (XS + 0.3, ay0, CG + bk), (XS + 0.3, ay1, CG + bk), (XS + 0.3, ay1, az1), (XS + 0.3, ay0, az1), (1, 0, 0))
    return me.model(alpha=(S_GLASS, S_MESH), even=[s_ for s_ in HALL_SLOTS if s_ not in (S_GLASS, S_MESH)])


TEL_SPOTS = ((190.0, 214.0), (212.0, 214.0), (190.0, 236.0), (212.0, 236.0))
if GARRISON2:
    TEL_SPOTS = ((188.0, 214.0), (206.0, 214.0), (188.0, 236.0), (206.0, 236.0))
COVER = ((181.0, 219.0, 'x'), (201.0, 231.0, 'x'), (221.0, 219.0, 'x'), (236.0, 231.0, 'x'), (240.0, 219.0, 'y'), (260.0, 231.0, 'x'))   # concrete barriers along the truck road
if GARRISON2:
    COVER = tuple(c_ for c_ in COVER if c_[0] != 221.0) + ((214.0, 216.5, 'x'),)


def gate_model(hidden=False):
    """the roll-up leaf: 10.5 m wide (y), 6.8 m high, 0.3 m thick; origin = the bottom centre; ribs on its faces. Slots [face, steel]"""
    hw, h = 5.25, 6.8
    me = Mesh((0, 0, 0), ['face', 'rib', 'back'])
    me.quad('face', (0.15, -hw, 0), (0.15, hw, 0), (0.15, hw, h), (0.15, -hw, h), (1, 0, 0))
    me.quad('back', (-0.15, hw, 0), (-0.15, -hw, 0), (-0.15, -hw, h), (-0.15, hw, h), (-1, 0, 0))   # (seen from -x: u runs toward -y)
    me.box('rib', -0.14, -hw, h - 0.02, 0.14, hw, h, solid=False)
    me.box(None, -0.15, -hw, 0, 0.15, hw, h)
    for z in (2.3, 4.5):
        for s in (-0.19, 0.15)[:1 if hidden else 2]:
            me.box('rib', s, -hw, z, s + 0.04, hw, z + 0.12, solid=False, uv=0.5)
    # (a Door slides in its local x-y plane: turned up in the game by alpha +90, so here local y = world z, local z = -world y)
    R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    for k_ in me.g:
        me.g[k_] = [(P_ @ R.T, T_, N_ @ R.T, U_) for P_, T_, N_, U_ in me.g[k_]]
    me.coll = [(P_ @ R.T, T_, N_ @ R.T, U_) for P_, T_, N_, U_ in me.coll]
    return me.model(even=['face', 'rib'] if hidden else ())


# ------------------------------------------------------------------------------------------------ the tunnel
def tunnel_path(L1=112.0, R1=10.0, R2=15.0, L2=66.0, R3=15.0, L3=20.0, door_flat=20.0):
    """the centre line from the gate's outer face: east, right onto the long ramp south, a hairpin (right) under the hill, north, right
    again (over the first ramp, 30 m above it), east to the sand door -> pts [(x, y)], s [m]. The numbers keep it under the ground (check())"""
    p = np.array([X1 + 1.3, (GATE_Y0 + GATE_Y1) / 2]); h = 0.0     # heading (rad, 0 = east)
    pts = [p.copy()]

    def run(L, step=6.0):
        nonlocal p
        n = max(1, int(round(L / step)))
        d = np.array([math.cos(h), math.sin(h)])
        for _ in range(n):
            p = p + d * (L / n)
            pts.append(p.copy())

    def arc(R, deg, turn, step=15.0):                       # turn -1 = right, +1 = left
        nonlocal p, h
        n = max(1, int(round(deg / step)))
        da = math.radians(deg / n) * turn
        c = p + R * turn * np.array([-math.sin(h), math.cos(h)])
        for _ in range(n):
            h2 = h + da
            p = c - R * turn * np.array([-math.sin(h2), math.cos(h2)])
            h = h2
            pts.append(p.copy())
    run(6.0)
    arc(R1, 90.0, -1)
    run(L1)
    arc(R2, 180.0, -1)
    run(L2)
    arc(R3, 90.0, -1)
    run(L3)
    run(door_flat, 4.0)
    P = np.array(pts)
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    return P, s


def tunnel_z(s, door_z):
    a, b = SLOPE_FLAT_A, s[-1] - SLOPE_FLAT_B
    return F + (door_z - F) * np.clip((s - a) / (b - a), 0.0, 1.0)


def sections(P):
    """left / right wall points at every path point (mitred)"""
    d = np.gradient(P, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    n = np.stack([-d[:, 1], d[:, 0]], 1)                    # left of the heading
    return d, n


class Tunnel:
    def __init__(self, door_z_fn):
        self.P, self.s = tunnel_path()
        self.door = self.P[-1]
        self.door_z = door_z_fn(float(self.door[0]), float(self.door[1]))
        self.z = tunnel_z(self.s, self.door_z)
        self.d, self.n = sections(self.P)
        self.ribs = np.arange(9.0, self.s[-1] - 6.0, BAY)
        self.exposed = len(self.P) - 1 - EXPOSED_SEGS

    def part_ranges(self, nparts=4):
        k = np.linspace(0, len(self.P) - 1, nparts + 1).astype(int)
        return [(int(a), int(b)) for a, b in zip(k[:-1], k[1:])]

    def seg_mesh(self, i0, i1, slots):
        P, s, z, n, d = self.P, self.s, self.z, self.n, self.d
        c = (P[i0] + P[i1]) / 2
        me = Mesh((c[0], c[1], (z[i0] + z[i1]) / 2), slots)
        W, H, C = TW, TH, TCH
        ct = 1.2                                            # the chamfer's width
        for i in range(i0, i1):
            a, b = P[i], P[i + 1]
            na, nb = n[i], n[i + 1]
            za, zb = z[i], z[i + 1]
            if i >= self.exposed:                           # (where the hill stops the shell is seen from outside: clear of the inner faces)
                for sgn in (1, -1):
                    qa, qb, oa, ob = a + sgn * na * (W + 0.3), b + sgn * nb * (W + 0.3), a + sgn * na * (W + 1.5), b + sgn * nb * (W + 1.5)
                    me.hull('ss_sand', [(q_[0], q_[1], zz_) for q_, zb_ in ((qa, za), (qb, zb), (oa, za), (ob, zb)) for zz_ in (zb_ - 0.6, zb_ + H + 1.2)], uv=0.2, solid=False)
                la_, ra_, lb_, rb_ = a + na * (W + 0.3), a - na * (W + 0.3), b + nb * (W + 0.3), b - nb * (W + 0.3)
                me.hull('ss_sand', [(q_[0], q_[1], zz_) for q_, zb_ in ((la_, za), (ra_, za), (lb_, zb), (rb_, zb)) for zz_ in (zb_ + H + 0.85, zb_ + H + 1.2)], uv=0.2, solid=False)
            rs = None
            la, ra, lb, rb = a + na * W, a - na * W, b + nb * W, b - nb * W
            ua, ub = s[i] / BAY, s[i + 1] / BAY
            nrm = np.cross((b[0] - a[0], b[1] - a[1], zb - za), (na[0], na[1], 0.0))
            nrm = nrm if nrm[2] > 0 else -nrm
            pa = lambda q, zz: (q[0], q[1], zz)
            # floor: u across, v along
            me.quad('ss_tf', pa(ra, za), pa(la, za), pa(lb, zb), pa(rb, zb), nrm, [(0, ua), (1, ua), (1, ub), (0, ub)])
            # the kerbs along both walls: 30 cm wide, 12 cm high, seen only (job A lining)
            for sgn in (1, -1):
                ka, kb = a + sgn * na * (W - 0.3), b + sgn * nb * (W - 0.3)
                wa_, wb_ = a + sgn * na * W, b + sgn * nb * W
                me.quad('ss_cc', pa(ka, za + 0.12), pa(kb, zb + 0.12), pa(wb_, zb + 0.12), pa(wa_, za + 0.12), nrm, [(s[i] / 2.0, 0), (s[i + 1] / 2.0, 0), (s[i + 1] / 2.0, 0.15), (s[i] / 2.0, 0.15)])
                me.quad('ss_cc', pa(ka, za), pa(kb, zb), pa(kb, zb + 0.12), pa(ka, za + 0.12), (-sgn * (na[0] + nb[0]) / 2, -sgn * (na[1] + nb[1]) / 2, 0.0),
                        [(s[i] / 2.0, 0.2), (s[i + 1] / 2.0, 0.2), (s[i + 1] / 2.0, 0.26), (s[i] / 2.0, 0.26)])
            # walls (seen from the inside)
            for sgn, q0, q1 in ((1, la, lb), (-1, ra, rb)):
                nw = (-sgn * (na[0] + nb[0]) / 2, -sgn * (na[1] + nb[1]) / 2, 0.0)
                me.quad('ss_tw', pa(q0, za), pa(q1, zb), pa(q1, zb + C), pa(q0, za + C), nw, [(ua, 1), (ub, 1), (ub, 0), (ua, 0)])
                q2, q3 = a + sgn * na * (W - ct), b + sgn * nb * (W - ct)
                nc = (nw[0], nw[1], -1.0)
                me.quad('ss_tch', pa(q0, za + C), pa(q1, zb + C), pa(q3, zb + H), pa(q2, za + H), nc, [(ua, 0), (ub, 0), (ub, 0.2), (ua, 0.2)])   # (owner 11-13: its own pool, over the lamps)
                # collision: thick wall, thick chamfer
                o0, o1 = a + sgn * na * (W + 1.5), b + sgn * nb * (W + 1.5)
                me.hull(rs, [pa(q0, za - 0.6), pa(q1, zb - 0.6), pa(o0, za - 0.6), pa(o1, zb - 0.6), pa(q0, za + C), pa(q1, zb + C), pa(o0, za + C), pa(o1, zb + C)], uv=0.2)
                me.hull(rs, [pa(q0, za + C), pa(q1, zb + C), pa(o0, za + C), pa(o1, zb + C), pa(q2, za + H), pa(q3, zb + H), pa(o0, za + H + 0.6), pa(o1, zb + H + 0.6), pa(q2, za + H + 0.6), pa(q3, zb + H + 0.6)], uv=0.2)
            if i < self.exposed:                            # (rock behind the thin render faces: a camera pushed into the wall sees dark, not the world)
                for sgn in (1, -1):
                    o0_, o1_ = a + sgn * na * (W + 2.0), b + sgn * nb * (W + 2.0)
                    me.quad('ss_tc', pa(o0_, za - 1.0), pa(o1_, zb - 1.0), pa(o1_, zb + H + 1.2), pa(o0_, za + H + 1.2), (-sgn * na[0], -sgn * na[1], 0.0), [(0, 0), (1, 0), (1, 0.2), (0, 0.2)])
                ol, or_, ol2, or2 = a + na * (W + 2.0), a - na * (W + 2.0), b + nb * (W + 2.0), b - nb * (W + 2.0)
                me.quad('ss_tc', pa(or_, za + H + 1.2), pa(ol, za + H + 1.2), pa(ol2, zb + H + 1.2), pa(or2, zb + H + 1.2), (0, 0, -1), [(0, 0), (1, 0), (1, 0.2), (0, 0.2)])
                me.quad('ss_tc', pa(or_, za - 1.0), pa(ol, za - 1.0), pa(ol2, zb - 1.0), pa(or2, zb - 1.0), (0, 0, 1), [(0, 0), (1, 0), (1, 0.2), (0, 0.2)])
            la2, ra2, lb2, rb2 = a + na * (W - ct), a - na * (W - ct), b + nb * (W - ct), b - nb * (W - ct)
            if i >= self.exposed - 1:                      # (cl3: the ground skin shows through the ceiling strip where the hill runs out over the roof: a dropped steel-grey soffit under it)
                me.hull('ss_tc', [pa(q_, zz_ + H + dz_) for q_, zz_ in ((a - na * (W - ct + 0.5), za), (a + na * (W - ct + 0.5), za), (b - nb * (W - ct + 0.5), zb), (b + nb * (W - ct + 0.5), zb)) for dz_ in (-T_ROOF_DROP, -0.02)], uv=0.2, solid=False)
            me.quad('ss_tc', pa(ra2, za + H), pa(la2, za + H), pa(lb2, zb + H), pa(rb2, zb + H), (0, 0, -1), [(0, ua), (1, ua), (1, ub), (0, ub)])
            me.hull(rs, [pa(ra2, za + H), pa(la2, za + H), pa(rb2, zb + H), pa(lb2, zb + H), pa(ra2, za + H + 0.6), pa(la2, za + H + 0.6), pa(rb2, zb + H + 0.6), pa(lb2, zb + H + 0.6)], uv=0.2)
            me.hull(None, [pa(ra, za), pa(la, za), pa(rb, zb), pa(lb, zb), pa(ra, za - 0.6), pa(la, za - 0.6), pa(rb, zb - 0.6), pa(lb, zb - 0.6)])
            # pipes along the right wall, a cable tray on the left (flat prisms, seen only)
            for off, zo, r_ in ((W - 0.22, 4.1, 0.13), (W - 0.2, 3.6, 0.09)):
                q0, q1 = a - na * off, b - nb * off
                me.hull('ss_stl', [(q0[0] + dx, q0[1] + dy, za + zo + dz) for dx in (-r_, r_) for dy in (-r_, r_) for dz in (-r_, r_)] +
                        [(q1[0] + dx, q1[1] + dy, zb + zo + dz) for dx in (-r_, r_) for dy in (-r_, r_) for dz in (-r_, r_)], uv=0.5, solid=False)
            q0, q1 = a + na * (W - 0.18), b + nb * (W - 0.18)
            q2, q3 = a + na * (W - 0.02), b + nb * (W - 0.02)
            me.hull('ss_stl', [pa(q0, za + 4.3), pa(q1, zb + 4.3), pa(q2, za + 4.3), pa(q3, zb + 4.3), pa(q0, za + 4.4), pa(q1, zb + 4.4), pa(q2, za + 4.4), pa(q3, zb + 4.4)], uv=0.5, solid=False)
        # steel ribs + lamps every bay
        for sr in self.ribs:
            if not (s[i0] <= sr < s[i1]):
                continue
            k = int(np.searchsorted(s, sr, 'right') - 1)
            t_ = (sr - s[k]) / max(s[k + 1] - s[k], 1e-6)
            c0 = P[k] * (1 - t_) + P[k + 1] * t_; zz = z[k] * (1 - t_) + z[k + 1] * t_
            n_ = n[k] * (1 - t_) + n[k + 1] * t_; n_ = n_ / np.linalg.norm(n_)
            d_ = np.array([n_[1], -n_[0]])
            w = 0.22
            for sgn in (1, -1):
                q0 = c0 + sgn * n_ * (W - 0.24); q1 = c0 + sgn * n_ * W
                me.hull('ss_stl', [(q[0] + d_[0] * e, q[1] + d_[1] * e, zz + h_) for q in (q0, q1) for e in (-w, w) for h_ in (0.0, C)], uv=0.5, solid=False)
                q2 = c0 + sgn * n_ * (W - ct - 0.24); q3 = c0 + sgn * n_ * (W - ct)
                me.hull('ss_stl', [(q[0] + d_[0] * e, q[1] + d_[1] * e, zz + C) for q in (q0, q1) for e in (-w, w)] +
                        [(q[0] + d_[0] * e, q[1] + d_[1] * e, zz + H) for q in (q2, q3) for e in (-w, w)], uv=0.5, solid=False)
            qa, qb = c0 - n_ * (W - ct), c0 + n_ * (W - ct)
            me.hull('ss_stl', [(q[0] + d_[0] * e, q[1] + d_[1] * e, zz + h_) for q in (qa, qb) for e in (-w, w) for h_ in (H - 0.26, H)], uv=0.5, solid=False)
            for sgn in (1, -1):                            # (job A: a drain grate in front of the kerb, under each lamp)
                g0, g1 = c0 + sgn * n_ * (W - 0.62), c0 + sgn * n_ * (W - 0.32)
                gz = (z[k + 1] - z[k]) / max(s[k + 1] - s[k], 1e-6) * 0.3 * (1.0 if np.dot(d_, P[k + 1] - P[k]) > 0 else -1.0)   # (on the ramp's slope)
                me.quad('ss_drn', (g0[0] - d_[0] * 0.3, g0[1] - d_[1] * 0.3, zz + 0.012 - gz), (g1[0] - d_[0] * 0.3, g1[1] - d_[1] * 0.3, zz + 0.012 - gz),
                        (g1[0] + d_[0] * 0.3, g1[1] + d_[1] * 0.3, zz + 0.012 + gz), (g0[0] + d_[0] * 0.3, g0[1] + d_[1] * 0.3, zz + 0.012 + gz), (0.0, 0.0, 1.0), [(0, 0), (1, 0), (1, 1), (0, 1)])
            for sgn in (1, -1):                            # (owner 11-13: a glowing cube on a dark wall; now a steel bulkhead, its lens facing the road, the wall lit round it)
                lc = c0 + sgn * n_ * (W - 0.15)
                me.hull('ss_stl', [(lc[0] + n_[0] * a_ + d_[0] * b_, lc[1] + n_[1] * a_ + d_[1] * b_, zz + h_) for a_ in (-0.16, 0.15) for b_ in (-0.16, 0.16) for h_ in (4.72, 4.98)],
                        uv=0.5, solid=False)            # (reviewer: along the wall, not the world axes: an angled rib's box hid the lens)
                fc = c0 + sgn * n_ * (W - 0.316)
                me.quad('ss_lampb', (fc[0] - d_[0] * 0.13, fc[1] - d_[1] * 0.13, zz + 4.76), (fc[0] + d_[0] * 0.13, fc[1] + d_[1] * 0.13, zz + 4.76),
                        (fc[0] + d_[0] * 0.13, fc[1] + d_[1] * 0.13, zz + 4.94), (fc[0] - d_[0] * 0.13, fc[1] - d_[1] * 0.13, zz + 4.94), (-sgn * n_[0], -sgn * n_[1], 0.0), [(0, 1), (1, 1), (1, 0), (0, 0)])
                me.lamp((lc[0] - sgn * n_[0] * 0.3, lc[1] - sgn * n_[1] * 0.3, zz + 4.75), 900.0)
        return me

    def at(self, s_):
        """(x, y, z, heading unit vector, left unit vector) at arc s_"""
        x, y, z = (float(np.interp(s_, self.s, c_)) for c_ in (self.P[:, 0], self.P[:, 1], self.z))
        k = int(np.clip(np.searchsorted(self.s, s_) - 1, 0, len(self.s) - 2))
        d = self.P[k + 1] - self.P[k]; d = d / np.linalg.norm(d)
        return x, y, z, d, np.array([-d[1], d[0]])

    def check(self, ground):
        """(margin m, at) along the line: the ground over the tunnel's roof slab; the last stretch comes out of the hill by design"""
        m_ = []
        for i, (p, z_) in enumerate(zip(self.P, self.z)):
            top = z_ + TH + 0.6
            g = min(ground(float(p[0] + self.n[i, 0] * o), float(p[1] + self.n[i, 1] * o)) for o in (-5.5, 0.0, 5.5))
            m_.append(g - top)
        return np.array(m_)


POST_S = 212.0                                             # the checkpoint on the north ramp (arc m)


def post_mesh(T_):
    """the tunnel checkpoint: staggered concrete barriers (a chicane, cover for both sides), a guard booth, a boom, a lamp"""
    x0, y0, z0, d0, n0 = T_.at(POST_S)
    me = Mesh((x0, y0, z0), ['ss_cc', 'ss_hz', 'ss_corr', 'ss_stl', 'ss_lamp', 'ss_sign'])

    def barrier(s_, lat0, lat1):
        x, y, z, d, n = T_.at(s_)
        c = np.array([x, y])
        pts = []
        for e, hw_ in ((-0.22, 0.42), (0.22, 0.42)):
            pass
        for sa in (-0.3, 0.3):
            for lat in (lat0, lat1):
                q = c + d * sa + n * lat
                zf = z + (T_.at(s_ + 1.0)[2] - z) * sa
                pts.append((q[0], q[1], zf - 0.1))
        low = list(pts)
        top = []
        for sa in (-0.14, 0.14):
            for lat in (lat0, lat1):
                q = c + d * sa + n * lat
                zf = z + (T_.at(s_ + 1.0)[2] - z) * sa
                top.append((q[0], q[1], zf + 1.0))
        me.hull('ss_cc', low + top, uv=0.5)
        q = c + n * ((lat0 + lat1) / 2)
    for s_, a, b in ((POST_S - 7.0, -4.45, 0.9), (POST_S + 3.0, -0.9, 4.45), (POST_S + 12.0, -4.45, 0.2)):
        barrier(s_, a, b)
    # the booth against the left wall, past the second barrier
    xb, yb, zb, d, n = T_.at(POST_S - 1.5)
    c = np.array([xb, yb]) + n * 3.1
    rect = lambda za: [(c[0] + d[0] * e + n[0] * f, c[1] + d[1] * e + n[1] * f, za) for e in (-1.3, 1.3) for f in (-1.2, 1.3)]
    me.hull('ss_corr', rect(zb - 0.3) + rect(zb + 2.5), uv=0.4)
    rtop = [(c[0] + d[0] * e + n[0] * f, c[1] + d[1] * e + n[1] * f, zb + za) for e in (-1.5, 1.5) for f in (-1.4, 1.5) for za in (2.5, 2.62)]
    me.hull('ss_stl', rtop, uv=0.5, solid=False)
    # the sign over the road, facing the man coming up the ramp, a red lamp on the booth
    xs, ys, zs, ds, ns = T_.at(POST_S - 16.0)
    c2 = np.array([xs, ys])
    a1, b1 = c2 + ns * 1.9, c2 - ns * 1.9
    # (orchestrator 11-13: one quad read mirrored from the gate side: a 4 cm steel board, the sign 5 mm off each face, the text the right way round from both)
    me.hull('ss_stl', [(q_[0] + ds[0] * e, q_[1] + ds[1] * e, zz) for q_ in (a1, b1) for e in (-0.02, 0.02) for zz in (zs + 4.1, zs + 5.05)], uv=0.5, solid=False)
    for sg in (-1, 1):
        o_ = ds * (0.025 * sg)
        p_, q_ = (a1, b1) if sg < 0 else (b1, a1)          # (left to right as the man on that side sees it; l6 tour: patch103 had it backwards on both faces)
        me.quad('ss_sign', (p_[0] + o_[0], p_[1] + o_[1], zs + 4.1), (q_[0] + o_[0], q_[1] + o_[1], zs + 4.1), (q_[0] + o_[0], q_[1] + o_[1], zs + 5.05),
                (p_[0] + o_[0], p_[1] + o_[1], zs + 5.05), (sg * ds[0], sg * ds[1], 0.0), [(0, 1), (1, 1), (1, 0), (0, 0)])
    for q_ in (a1, b1):
        me.box('ss_stl', q_[0] - 0.04, q_[1] - 0.04, zs + 5.05, q_[0] + 0.04, q_[1] + 0.04, zs + TH + 0.05, solid=False)
    me.lamp((c[0], c[1], zb + 2.8), 800.0, (1.0, 0.16, 0.08))
    me.box('ss_sign', c[0] - 0.09, c[1] - 0.09, zb + 2.62, c[0] + 0.09, c[1] + 0.09, zb + 2.8, solid=False)
    # the boom: a raised striped pole across the free lane
    xp, yp, zp, d2, n2 = T_.at(POST_S + 3.0)
    a_ = np.array([xp, yp]) - n2 * 1.1
    me.hull('ss_hz', [(a_[0] + d2[0] * e, a_[1] + d2[1] * e, zp + h) for e in (-0.09, 0.09) for h in (0.0, 1.2)] +
            [(a_[0] - n2[0] * 0.2 + d2[0] * e, a_[1] - n2[1] * 0.2 + d2[1] * e, zp + h) for e in (-0.09, 0.09) for h in (0.0, 1.2)], uv=0.5)
    b_ = a_ - n2 * 3.2
    me.hull('ss_hz', [(a_[0], a_[1], zp + 1.1), (a_[0], a_[1], zp + 1.22), (b_[0], b_[1], zp + 3.9), (b_[0], b_[1], zp + 4.02),
                      (a_[0] + d2[0] * 0.1, a_[1] + d2[1] * 0.1, zp + 1.1), (b_[0] + d2[0] * 0.1, b_[1] + d2[1] * 0.1, zp + 3.9)], uv=0.5, solid=False)
    return me


TUN_SLOTS = ['ss_tf', 'ss_tw', 'ss_tc', 'ss_lamp', 'ss_stl', 'ss_sand', 'ss_lampb', 'ss_tch', 'ss_cc', 'ss_drn']
TUN_EVEN = TUN_SLOTS[:5] + ['ss_lampb', 'ss_tch', 'ss_cc', 'ss_drn']
GATE_SLOTS = {'ss_bgate_1': ['ss_gate', 'ss_stl', 'ss_gate'], 'ss_sgate_1': ['ss_sgate', 'ss_stl', 'ss_sgatei']}
PORT_SLOTS = ['ss_dune', 'ss_cc', 'ss_rock', 'ss_scrub', 'ss_track', 'ss_rev']   # (11-12 ss_e18: a 13th slot (index 12) drew see-through in the game: only the slots it uses)


def dune_z(T_, ground, dx, dy, z, X, Y):
    """the drift's height (absolute z) at door-frame X (out of the door +), Y; None = no sand here (the lane in front of the door)"""
    W, H = TW, TH
    if X > 1.3 and abs(Y) < 6.8 - 1e-6:
        return None
    Xr = min(X, 0.2)
    zr = float(np.interp(dx + Xr, T_.P[T_.exposed - 2:, 0], T_.z[T_.exposed - 2:])) + H + 1.2     # (the tunnel roof's sand line)
    crest = zr + 1.5 + 1.6 * float(np.clip((Xr + 6.0) / 6.2, 0.0, 1.0)) ** 2                    # (up over the headwall's top, z + 10)
    crest += 0.35 * math.sin(0.31 * X + 0.17 * Y) + 0.25 * math.sin(0.11 * X - 0.23 * Y + 1.0)  # (soft undulation, no flat top)
    sm = lambda t: t * t * (3.0 - 2.0 * t)
    g = float(ground(dx + X, dy + Y))
    yc = Y - 1.2                                                                                 # (windward north: the crest sits north of the axis, its slope longer)
    plat, wd = (6.0, 20.0) if yc > 0 else (5.6, 16.0)
    h = crest - (crest - (g - 0.8)) * sm(min(max((abs(yc) - plat) / wd, 0.0), 1.0))         # (rounded: flat at the crest, flat where it meets the ground)
    if X > 1.3:                                                                                  # (the shoulders run on beside the revetments and round down to the ground)
        h = h - (h - (g - 0.8)) * sm(min((X - 1.3) / 22.0, 1.0))
        wt = z + (7.6 + (min(X, 8.0) - 1.3) * (0.3 - 7.6) / 6.7) - 0.25 + (abs(Y) - 6.8) * 0.9   # (banked against the revetment, under its head)
        if X > 8.0 and SS_PORTAL_EDGE:                     # (S7 11-17, propaudit 1674: past the revetment's end the lane edge stayed at z + 0.05 while the ground falls
            wt += (min(z + 0.05, g - 0.3) - (z + 0.05)) * sm(min((X - 8.0) / 1.5, 1.0))   #  away: a 0.5-1.05 m sand shelf along the truck lane. It comes down 0.3 m under the ground)
        h = min(h, wt)
    if X < -18.0:                                                                                # (west: the drift runs out into the hill)
        h = h - (h - (g - 0.8)) * sm(min((-18.0 - X) / 8.0, 1.0))
    if T_.__dict__.get('_cut_x') is None:                      # (where the terrain is cut over the roof (hole()), the drift must be the ground: never under it there)
        ex = float(T_.P[T_.exposed][0]); xb = ex
        for x in np.arange(dx, ex, -0.5):
            zc = float(np.interp(x, T_.P[T_.exposed:, 0], T_.z[T_.exposed:])) + H
            if min(ground(x, dy + o) for o in (-5.5, 0.0, 5.5)) > zc + 1.2:
                xb = x; break
        T_._cut_x = xb - dx
    if T_._cut_x - 3.0 <= X <= 1.3 and abs(Y) <= 7.9:
        h = max(h, float(ground(dx + X, dy + Y)) + 0.1)
    return h


def dune(me, T_, ground, dx, dy, z):
    """one heightfield mesh in door-frame cells: vertices under the ground sit 0.5 m below it (a skirt, no seam line), cells with all four corners buried are left out,
    the lane in front of the door is left open. Solid: it is what you walk on over the tunnel (the old berm hulls are gone)"""
    xa = min(float(T_.P[T_.exposed][0]) - dx - 6.0, -27.0)
    Xs = np.r_[np.arange(1.3, xa, -1.0)[::-1], np.arange(2.3, 24.01, 1.0)]
    Ys = np.r_[-np.arange(6.8, 28.01, 1.0)[::-1], np.linspace(-5.8, 5.8, 13), np.arange(6.8, 28.01, 1.0)]
    nx, ny = len(Xs), len(Ys)
    Pz = np.full((nx, ny), np.nan); G = np.zeros((nx, ny)); live = np.zeros((nx, ny), bool)
    for i, X in enumerate(Xs):
        for j, Y in enumerate(Ys):
            g = float(ground(dx + X, dy + Y)); G[i, j] = g
            h = dune_z(T_, ground, dx, dy, z, X, Y)
            if h is None:
                continue
            live[i, j] = h > g - 0.15
            Pz[i, j] = max(h, g - 0.5)
    P, U, T = [], [], []
    idx = -np.ones((nx, ny), int)
    for i in range(nx):
        for j in range(ny):
            if not np.isnan(Pz[i, j]):
                idx[i, j] = len(P)
                x, y = dx + Xs[i], dy + Ys[j]
                P.append((x - me.o[0], y - me.o[1], Pz[i, j] - me.o[2])); U.append((x / SAND_TILE, y / SAND_TILE))
    for i in range(nx - 1):
        for j in range(ny - 1):
            q = [idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]]
            if min(q) < 0 or not (live[i, j] or live[i + 1, j] or live[i + 1, j + 1] or live[i, j + 1]):
                continue
            T += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    P = np.array(P) * M; T = np.array(T); U = np.array(U)
    N = np.tile((0.0, 0.0, 1.0), (len(P), 1))
    T = SL._orient(P, T, N, np.tile((0.0, 0.0, 1.0), (len(T), 1)))
    part = (P, T, N, U)
    me.g['ss_dune'].append(part)
    me.coll.append(part)
    # half-buried rocks (the terrain's rock), scrub clumps, on the drift's surface
    rng = np.random.default_rng(91)
    for X, Y, kind in ((-14.0, 13.0, 'r'), (-6.0, -12.5, 'r'), (-10.0, 17.0, 's'), (-2.0, 12.0, 's'), (-16.0, -11.0, 's'),     # (judge Q04: the rocks by the
                       (2.0, -14.5, 's'), (-20.0, 14.0, 's'), (-15.0, -15.0, 'r')):                                    #  revetments read floating on the skyline)
        h = dune_z(T_, ground, dx, dy, z, X, Y)
        g = float(ground(dx + X, dy + Y))
        zc = max(h, g) if h is not None else g
        if kind == 'r':                                    # (orchestrator 11-12: they sat on the drift: smaller, tilted, sunk past half their height below the lowest ground under them)
            s = rng.uniform(0.35, 0.7, 3) * (1.3, 1.0, 0.8)
            loc = np.array([(s[0] * rng.uniform(0.7, 1) * c_, s[1] * rng.uniform(0.7, 1) * s_, zz * s[2]) for c_, s_ in ((1, 0), (0.6, 0.8), (-0.5, 0.9), (-1, 0), (-0.4, -0.9), (0.7, -0.7))
                            for zz in (-1.0, rng.uniform(0.6, 1.0))])
            ax = rng.normal(size=3)
            ax[2] = 0.0
            ax /= np.linalg.norm(ax)
            an = rng.uniform(0.35, 0.65)
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            Rr = np.eye(3) + math.sin(an) * K + (1 - math.cos(an)) * K @ K
            zl = min(max(dune_z(T_, ground, dx, dy, z, X + ox_, Y + oy_) or -99.0, float(ground(dx + X + ox_, dy + Y + oy_))) for ox_ in (-s[0], 0.0, s[0]) for oy_ in (-s[1], 0.0, s[1]))
            pts = loc @ Rr.T + np.array([dx + X, dy + Y, zl - 0.35 * s[2]])
            pts[:, 2] -= max(0.0, float(pts[:, 2].max()) - (zc + 0.15))   # (judge Q04: never more than 0.15 m proud of the drift: no stone on the skyline)
            me.hull('ss_rock', [tuple(q_) for q_ in pts], uv=0.8, solid=False)
        else:                                              # (l6: on the lowest drift under the clump, not its centre's height: no tuft hanging off a slope)
            zc = min(max(dune_z(T_, ground, dx, dy, z, X + ox_, Y + oy_) or -99.0, float(ground(dx + X + ox_, dy + Y + oy_))) for ox_ in (-0.8, 0.0, 0.8) for oy_ in (-0.8, 0.0, 0.8))
            for k in range(3):
                ox, oy, r_ = rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(0.25, 0.45)
                me.hull('ss_scrub', [(dx + X + ox + r_ * c_, dy + Y + oy + r_ * s_, zc - 0.05) for c_, s_ in ((1, 0), (0.5, 0.87), (-0.5, 0.87), (-1, 0), (-0.5, -0.87), (0.5, -0.87))] +
                        [(dx + X + ox + 0.5 * r_ * c_, dy + Y + oy + 0.5 * r_ * s_, zc + rng.uniform(0.3, 0.55)) for c_, s_ in ((1, 0), (-0.5, 0.87), (-0.5, -0.87))], uv=1.5, solid=False)


def rev_sand(me, dx, dy, z, sg):
    """the sand on a wing revetment (judge Q04 reopened 11-13): one continuous lip over the sloped top edge, built on shared cross-sections so there are no
    gaps, from the headwall to exactly the wall's end; where the wall is under ~3 m its face runs down to the ground as a pile; a smooth pile along the inner foot
    elsewhere (clear of the trucks' lane, |y| > 4.3; none under the south drums). Seen only"""
    sm = lambda t: (lambda c: c * c * (3.0 - 2.0 * c))(min(max(t, 0.0), 1.0))
    Xs = np.linspace(1.3, 8.0, 16)

    def sec(X):
        T = z + 7.6 + (X - 1.3) * (0.3 - 7.6) / 6.7          # (the wall's top at X)
        hw = T - z
        h = (0.16 + 0.1 * math.sin(1.7 * X + sg)) * min(1.0, hw / 0.8)          # (the crest over the top, smooth along the wall)
        d = hw + 0.05 if hw <= 2.9 else 0.35                                    # (a lip high up, the whole face where it is under 2.9 m: no section hanging half way)
        bo = min(1.9, max(0.3, 0.9 * d))                                        # (its toe out from the face)
        return [(X, 6.95, T - 0.35), (X, 6.45, T + h), (X, 6.06, T - 0.06), (X, 6.2 - bo, T - d), (X, 6.25, T - d - 0.05)]

    S = [sec(X) for X in Xs]
    for A, B in zip(S[:-1], S[1:]):
        me.hull('ss_dune', [(dx + X, dy + sg * Y, Z) for X, Y, Z in A + B], uv=1.0 / SAND_TILE, solid=False)
        if A[3][2] > z + 0.2 >= B[3][2]:                       # (where the lip becomes the pile: the pile's end rises to the lip, filled to the ground)
            me.hull('ss_dune', [(dx + X, dy + sg * Y, Z) for X, Y, Z in [A[3], A[4], (A[3][0], A[3][1], z - 0.05), (A[4][0], A[4][1], z - 0.05)] + B[2:]],
                    uv=1.0 / SAND_TILE, solid=False)

    def foot(X):
        hf = (0.35 + 0.5 * (8.0 - X) / 6.7) * (1.0 + 0.12 * math.sin(2.1 * X + 0.7 * sg))
        if sg < 0:                                             # (no sand under the drums, x 2.1-4.9: it tapers away either side)
            hf *= 1.0 - sm((X - 1.5) / 0.6) * (1.0 - sm((X - 4.9) / 0.6))
        return hf

    Xf = np.linspace(1.3, 8.0, 12)
    for xa, xb in zip(Xf[:-1], Xf[1:]):
        ha, hb = foot(xa), foot(xb)
        if max(ha, hb) < 0.03:
            continue
        me.hull('ss_dune', [(dx + X, dy + sg * Y, Zz) for X, hh in ((xa, ha), (xb, hb)) for Y, Zz in ((6.25, z - 0.05), (6.25, z + hh), (6.2 - 1.3 * hh - 0.1, z - 0.05), (6.2 - 0.55 * hh, z + 0.55 * hh))],
                uv=1.0 / SAND_TILE, solid=False)


def tracks(me, ground, dx, dy, z):
    """tyre tracks out of the door: two pairs pressed into the apron's sand and on across the ground toward the trucks' line (y - 4 by x + 16), 6 cm over it"""
    for lane in (-1.0, 1.4):
        for wy in (-0.95, 0.95):
            pts = []
            for X in np.arange(1.6, 34.01, 1.0):
                Y = lane + wy - 4.0 * min(max((X - 4.0) / 12.0, 0.0), 1.0) - 0.1 * max(X - 16.0, 0.0)
                g = z + 0.05 if X < 9.0 else float(ground(dx + X, dy + Y)) + 0.1      # (review: 5 mm over the apron sand flickered, 1 m steps dip under the ground)
                pts.append((dx + X, dy + Y, g))
            for (x0, y0, z0), (x1, y1, z1) in zip(pts[:-1], pts[1:]):
                if SS_TRACK_EDGE and abs(z1 - z0) > 0.3:   # (S7 11-17, propaudit 1674: the apron ends at X ~8.7 over a 1.4-2.3 m drop; the X 8.6 -> 9.6 quad of each
                    continue                                #  track hung over it, up to 1.6 m in the air. Only those 4 go (look_5: kept steps <= 0.14 m))
                me.quad('ss_track', (x0, y0 - 0.17, z0), (x1, y1 - 0.17, z1), (x1, y1 + 0.17, z1), (x0, y0 + 0.17, z0), (0, 0, 1), [(0, 0), (1, 0), (1, 0.35), (0, 0.35)])


def portal_model(T_, ground):
    """the sand door's headwall in the hillside: door slot, hazard jambs, wing walls, an apron out onto the sand. Door plane x = door x + 0.45"""
    dx, dy = float(T_.door[0]), float(T_.door[1])
    z = T_.door_z
    me = Mesh((dx, dy, z), PORT_SLOTS)
    me.even_default = ('ss_dune', 'ss_rev')
    W, H = TW, TH
    hw, top = 9.0, z + 9.5
    # the two leaves with the slot between them (the leaf rolls up behind the front one)
    for x0, x1, lab in ((dx, dx + 0.4, 'back'), (dx + 0.8, dx + 1.3, 'front')):
        me.box('ss_dune', x0, dy - hw, z - 1.0, x1, dy - 5.0, top, uv=0.2)
        me.box('ss_dune', x0, dy + 5.0, z - 1.0, x1, dy + hw, top, uv=0.2)
        me.box('ss_dune', x0, dy - 5.0, z + GATE_H, x1, dy + 5.0, top, uv=0.2)
    me.box('ss_dune', dx + 0.4, dy - hw, z - 1.0, dx + 0.8, dy - 5.3, top, uv=0.2)
    me.box('ss_dune', dx + 0.4, dy + 5.3, z - 1.0, dx + 0.8, dy + hw, top, uv=0.2)
    me.box('ss_dune', dx - 0.1, dy - hw, top, dx + 1.5, dy + hw, top + 0.5, uv=0.2)
    me.box('ss_cc', dx - 0.6, dy - 5.3, z - 0.8, dx + 1.6, dy + 5.3, z + 0.012, uv=0.2)   # (the door's sill: no gap under the leaf)
    # (owner 11-12 + judge E02: the hard-faced berm hulls and wing wedges read as an object sitting on the desert. One drift heightfield in the terrain's own sand,
    #  rounded, skirts under the ground, over the exposed tunnel and round the headwall; the wings are concrete revetments it banks against)
    dune(me, T_, ground, dx, dy, z)
    for sg in (-1, 1):                                     # the wing revetments (concrete, sloped top), the old sand wings' shape
        y0, y1 = dy + sg * 6.2, dy + sg * 6.8
        me.hull('ss_rev', [(dx + 1.3, y0, z - 6.0), (dx + 1.3, y1, z - 6.0), (dx + 8.0, y0, z - 6.0), (dx + 8.0, y1, z - 6.0),
                           (dx + 1.3, y0, z + 7.6), (dx + 1.3, y1, z + 7.6), (dx + 8.0, y0, z + 0.3), (dx + 8.0, y1, z + 0.3)], uv=0.25)
        me.hull('ss_rev', [(dx + X_, Y_, z + Z_ + e_) for X_, Z_ in ((1.3, 7.6), (8.0, 0.3)) for Y_ in (min(y0, y1) - 0.04, max(y0, y1) + 0.04) for e_ in (-0.15, 0.15)],
                uv=0.5, solid=False)                       # (the revetment's coping along its sloped top; judge Q04: the flat head hung over the slope like a loose rock)
        rev_sand(me, dx, dy, z, sg)
    me.box('ss_cc', dx + 1.3, dy - 6.2, z - 6.0, dx + 9.0, dy + 6.2, z, uv=0.2)   # (a truck apron under drifted sand)
    me.quad('ss_dune', (dx + 1.3, dy - 6.2, z + 0.03), (dx + 9.0, dy - 6.2, z + 0.03), (dx + 9.0, dy + 6.2, z + 0.03), (dx + 1.3, dy + 6.2, z + 0.03), (0, 0, 1),
            [((dx + 1.3) / SAND_TILE, (dy - 6.2) / SAND_TILE), ((dx + 9.0) / SAND_TILE, (dy - 6.2) / SAND_TILE), ((dx + 9.0) / SAND_TILE, (dy + 6.2) / SAND_TILE), ((dx + 1.3) / SAND_TILE, (dy + 6.2) / SAND_TILE)])   # (the apron under blown sand, on the ground's own tiling)
    me.hull('ss_dune', [(dx + 9.0, dy + o_, z + 0.02) for o_ in (-6.4, 6.4)] + [(dx + 15.0, dy + o_, z - 6.0) for o_ in (-9.5, 9.5)] + [(dx + 9.0, dy + o_, z - 6.0) for o_ in (-6.4, 6.4)], uv=1.0 / SAND_TILE)   # (the apron's lip under a sand ramp)
    # (judge E02 11-12: the concrete frame and lintel proud of the headwall, sand drifted over the lintel and at the jambs' feet, three oil drums by the south wing. Seen only)
    fx0, fx1, ht = dx + 1.3, dx + 1.9, z + GATE_H
    for sg in (-1, 1):
        me.box('ss_rev', fx0, min(dy + sg * 5.0, dy + sg * 6.0), z - 0.3, fx1, max(dy + sg * 5.0, dy + sg * 6.0), ht + 1.5, uv=0.5, solid=False)
        me.box('ss_rev', fx1, min(dy + sg * 5.1, dy + sg * 5.9), ht + 0.1, fx1 + 0.12, max(dy + sg * 5.1, dy + sg * 5.9), ht + 1.4, uv=0.5, solid=False)   # (the jamb's cap stone)
        me.hull('ss_dune', [(fx0, dy + sg * 5.0, z - 0.2), (fx0, dy + sg * 6.2, z - 0.2), (dx + 3.8, dy + sg * 5.35, z - 0.2), (dx + 3.8, dy + sg * 6.2, z - 0.2),
                            (fx1 + 0.05, dy + sg * 5.15, z + 0.8), (fx1 + 0.05, dy + sg * 6.2, z + 1.5), (dx + 2.7, dy + sg * 6.2, z + 0.7)], uv=1.0 / SAND_TILE, solid=False)
        for k_, (x_, y_, h_, r_) in enumerate(((3.0, 4.7, 0.22, 1.1), (6.5, 5.2, 0.3, 1.3), (11.0, 5.6, 0.25, 1.6))):    # sand blown onto the apron's edges, clear of the trucks' lane (|y| < 4.25)
            me.hull('ss_dune', [(dx + x_ + r_ * c__, dy + sg * (y_ + 0.5 * r_ * s__), z - 0.05) for c__, s__ in ((1, 0), (0.7, 0.7), (0, 1), (-0.7, 0.7), (-1, 0), (0, -0.4))] +
                    [(dx + x_, dy + sg * (y_ + 0.15), z + h_), (dx + x_ + 0.4 * r_, dy + sg * (y_ + 0.25), z + 0.6 * h_)], uv=1.0 / SAND_TILE, solid=False)
    me.box('ss_rev', fx0, dy - 6.0, ht, fx1, dy + 6.0, ht + 1.5, uv=0.5, solid=False)
    me.box('ss_rev', fx1, dy - 6.1, ht + 1.3, fx1 + 0.15, dy + 6.1, ht + 1.5, uv=0.5, solid=False)
    me.hull('ss_dune', [(fx0, dy - 6.8, ht + 1.5), (fx0, dy + 6.8, ht + 1.5), (fx1 + 0.2, dy - 6.0, ht + 1.5), (fx1 + 0.2, dy + 6.0, ht + 1.5),
                        (fx0, dy - 6.8, ht + 2.7), (fx0, dy + 6.8, ht + 2.5), (fx0 + 0.35, dy - 2.5, ht + 2.25), (fx0 + 0.4, dy + 3.0, ht + 2.1)], uv=1.0 / SAND_TILE, solid=False)
    # (Q04 11-13: the drums by the south wing are gone: from the apron the pile always cut them)
    tracks(me, ground, dx, dy, z)
    return me


def hole(T_, ground, cell, x0g, y0g, inside_margin=0.0):
    """the terrain to cut at the portal: from the door plane back to where the ground rises over the roof slab; narrower than the outer walls"""
    dx, dy = float(T_.door[0]), float(T_.door[1])
    x_back = dx - 40.0
    ex = float(T_.P[T_.exposed][0])
    for x in np.arange(dx, ex, -0.5):                       # (rv16: the ground ran through the tunnel's sloping roof: cut back to where it clears that roof, not the door's)
        zc = float(np.interp(x, T_.P[T_.exposed:, 0], T_.z[T_.exposed:])) + TH
        if min(ground(x, dy + o) for o in (-5.5, 0.0, 5.5)) > zc + 1.2:
            x_back = x
            break
    else:
        x_back = ex
    print('v5 sand door: ground over the roof: ' + ' '.join('%.0f:%.1f/%.1f' % (x, ground(x, dy), float(np.interp(x, T_.P[T_.exposed:, 0], T_.z[T_.exposed:])) + TH) for x in np.arange(ex - 8.0, dx + 1.0, 4.0)))
    return (x_back, dy - 4.9, dx + 1.0, dy + 4.9)


# ------------------------------------------------------------------------------------------------ what stands in the hall (originals, EditRigidObj)
def props():
    """(name, model, x, y, z, yaw): the map's own crates, generators, tanks, trucks"""
    P = []
    for k, (x, y, yaw) in enumerate(((176.0, 200.0, 0.0), (178.4, 200.2, 0.4), (176.2, 202.6, 1.2), (226.0, 199.6, 0.2), (228.6, 200.0, 1.0),
                                     (237.0, 253.0, 0.3), (239.8, 253.2, 0.0), (262.0, 253.0, 0.8), (264.6, 252.8, 0.0), (262.4, 250.2, 0.5))):
        P.append(('SS base crates %d' % k, '330_01_1' if k % 2 else '330_02_1', x, y, F, yaw))
    for k, x in enumerate((186.0, 196.5, 207.0)):
        P.append(('SS base generator %d' % k, '337_11_1', x, 199.2, F, 0.0))
    for k, (x, y, yaw) in enumerate(((183.6, 222.4, 0.3), (186.2, 221.8, 1.1), (214.0, 229.6, 0.5), (216.6, 230.2, 0.0), (229.0, 233.6, 0.9), (242.0, 214.0, 0.2), (244.6, 213.4, 0.7))):
        P.append(('SS road crates %d' % k, '330_02_1' if k % 2 else '330_01_1', x, y, F, yaw))
    for k, (x, y) in enumerate(((201.2, 203.0), (233.9, 250.1))):       # (406_50_1 is a 3.4 x 7.5 m tank: more than one here stood inside each other)
        P.append(('SS fuel drum %d' % k, '406_50_1', x, y, F, 0.0))
    P.append(('SS fuel truck', '600_00_1', 226.0, 241.0, F, 0.0))
    P.append(('SS road crates 8', '330_01_1', 198.0, 222.5, F, 0.4))
    P.append(('SS road crates 9', '330_02_1', 227.0, 228.0, F, 0.2))
    for k, (x, y, md, yaw) in enumerate(((180.0, 254.6, '330_01_1', 0.0), (187.4, 254.4, '260_11_1', 0.0), (196.0, 254.6, '330_02_1', 0.3), (203.0, 254.2, '260_11_1', 1.6), (212.0, 254.6, '330_01_1', 0.5), (220.0, 254.2, '260_11_1', 0.0),
                                         (186.2, 253.2, '261_06_1', 2.0), (201.8, 253.0, '261_06_1', 1.0), (218.8, 253.2, '261_06_1', 2.6))):
        P.append(('SS room prop %d' % k, md, x, y, F, yaw))
    # (S5 11-15: these were 231_02_1 = a three-seat SOFA (render) with an office chair facing it. Now the game's office desk; its user side
    #  (drawers, -x) turned to the chair in the north (gamma -pi/2), the plain side to the south wall)
    P.append(('SS control desk 1', '231_15_1', 250.0, 199.4, F, -math.pi / 2))
    P.append(('SS control desk 2', '231_15_1', 262.0, 199.4, F, -math.pi / 2))
    P.append(('SS control chair 1', '261_06_1', 250.0, 200.8, F, 2.8))
    P.append(('SS control chair 2', '261_06_1', 262.0, 200.8, F, 3.4))
    for k, x in enumerate((250.0, 256.0, 262.0)):           # (owner 40: the game's own desks + terminals along the window)
        P.append(('SS control window desk %d' % k, '231_15_1', x, 207.2, F, math.pi / 2))
    for k, y in enumerate((198.4, 199.7, 201.0, 202.3, 203.6, 204.9)):   # (owner 44: a wall of servers)
        P.append(('SS server cabinet %d' % k, '261_05_1' if k % 2 else '261_04_1', 265.3, y, F, math.pi / 2))
    for k, (x, y, md, yaw) in enumerate(((247.6, 198.6, '261_32_1', 0.0), (254.0, 197.7, '205_36_1', math.pi / 2), (258.0, 197.7, '205_36_1', math.pi / 2),
                                         # the hall: machines and servers round the silo, stores along the walls
                                         (246.5, 250.6, '261_04_1', 0.0), (248.0, 250.6, '261_05_1', 0.0), (249.5, 250.6, '261_04_1', 0.0), (251.0, 250.6, '261_05_1', 0.0),
                                         (253.5, 251.0, '231_15_1', math.pi / 2), (258.0, 247.0, '205_35_1', 0.3), (260.0, 248.5, '205_36_1', 1.2), (262.5, 246.0, '205_35_1', 2.4),
                                         (260.2, 236.0, '660_01_1', 0.0), (236.7, 247.5, '330_01_1', 0.2), (238.0, 247.6, '330_01_1', 0.0), (237.4, 248.85, '330_01_1', 0.4),
                                         (214.0, 197.6, '261_32_1', 0.0), (211.0, 197.6, '261_32_1', 0.0), (237.75, 198.0, '330_01_1', 0.2), (239.0, 198.0, '330_01_1', 0.0),
                                         (240.0, 198.1, '333_03_1', 0.0), (240.8, 198.8, '333_03_1', 0.0), (243.0, 198.2, '205_36_1', 1.57), (236.0, 197.8, '261_32_1', 0.0),
                                         (262.0, 199.0, '333_03_1', 0.0))):
        if x > 246.0 and y < 207.0 and md == '333_03_1':
            continue
        P.append(('SS base equipment %d' % k, md, x, y, F, yaw))
    if GARRISON2:
        import ssgarr
        P = ssgarr.fix_props(P) + ssgarr.props()
    return P


# chapter review stands underground (name, eye point x, y; z = feet)
REVIEW = [('lift_bottom', 170.5, 226.7, F), ('hall_west', 176.0, 226.7, F), ('gallery', 201.0, 225.0, F), ('silo', 240.0, 225.0, F),
          ('pit', 243.0, 238.0, F), ('control', 252.0, 203.0, F), ('console', 256.0, 204.6, F), ('gate_in', 262.0, 222.0, F)]


# ------------------------------------------------------------------------------------------------ the railway's bed (owner 11-04: 'the train is not on the railway')
BED_HW, BED_FOOT, BED_D = 4.9, 3.6, 2.4                    # top half width, slope width, depth under the top (m)


def bed_meshes(x0, x1, yc, top, step=90.0):
    """a ballast embankment under the L12 double track: the rails lie on it, its toes run under the sand. World m -> [Mesh]"""
    out = []
    x = x0
    while x < x1 - 1e-6:
        x2 = min(x + step, x1)
        me = Mesh(((x + x2) / 2, yc, top), ['410_19_1'])
        me.hull('410_19_1', [(x_, yc + s_ * BED_HW, top) for x_ in (x, x2) for s_ in (-1, 1)] +
                [(x_, yc + s_ * (BED_HW + BED_FOOT), top - BED_D) for x_ in (x, x2) for s_ in (-1, 1)], uv=0.5)
        out.append(me)
        x = x2
    return out


def buffer_stop(x, ys, z):
    """steel buffer stops at the end of both tracks: a frame, a hazard beam -> Mesh (origin (x, mid y, z))"""
    me = Mesh((x, sum(ys) / len(ys), z), ['406_49_1', 'ss_hz'])
    for y in ys:
        me.box('406_49_1', x - 2.0, y - 0.95, z - 0.1, x - 1.7, y - 0.65, z + 1.4, uv=0.5)
        me.box('406_49_1', x - 2.0, y + 0.65, z - 0.1, x - 1.7, y + 0.95, z + 1.4, uv=0.5)
        me.hull('406_49_1', [(x - 3.9, y + s, z) for s in (-0.8, 0.8)] + [(x - 3.9, y + s, z + 0.1) for s in (-0.8, 0.8)] +
                [(x - 2.0, y + s, z + 1.2) for s in (-0.8, 0.8)] + [(x - 1.7, y + s, z + 1.2) for s in (-0.8, 0.8)], uv=0.5)
        me.box('ss_hz', x - 1.7, y - 1.35, z + 0.85, x - 1.35, y + 1.35, z + 1.3, uv=0.5)
    return me


# ------------------------------------------------------------------------------------------------ the way down, dressed (critic rv3: 'one blurry tan blotch')
WAYD_SLOTS = ['ss_tw', 'ss_tfw', 'ss_tc', 'ss_lamp', 'ss_stl', 'ss_hz', 'ss_duct', 'ss_lampb', 'ss_tw2']


def way_decor(V):
    """see-only lining of the stairs, passage, corridor and lift room (1.5 cm off the concrete): walls in bays with a lamp's pool, dado, floor, ceiling,
    wall lamps, pipes, hazard frames. World m"""
    e = 0.015
    z0, h = V.TOP_Z, 2.4
    hx0, hy0, hx1, hy1 = V.shaft_rect()
    r0, c0, c1, wy, cx0, cx1, sy1, sy0 = 158.5, 231.5, 233.3, 233.6, 176.6, 178.4, 238.7, 236.9
    zc = z0 + 4.6
    me = Mesh((170.0, 232.0, z0), WAYD_SLOTS)
    me.box(None, r0 - 0.25, c0, z0 - 0.25, r0 - 0.05, c0 + 0.2, z0)   # (a model needs a collision part: this one sits inside the wall)
    B4 = 4.0
    # corridor
    wall(me, 'y', c0 + e, 1, hx0 + 0.3, cx1, z0, z0 + h, 'ss_tw2', step=B4, tbase=hx0)
    wall(me, 'y', c1 - e, -1, hx0 + 0.3, cx0, z0, z0 + h, 'ss_tw2', step=B4, tbase=hx0)
    wall(me, 'y', c1 - e, -1, cx0 + V.CELL_DOOR_W, cx1, z0, z0 + h, 'ss_tw2', step=B4, tbase=hx0)
    wall(me, 'x', cx1 - e, -1, c0, sy1, z0, z0 + h, 'ss_tw2', step=B4, tbase=c0)
    me.quad('ss_tfw', (hx0 + 0.3, c0, z0 + 0.012), (cx1, c0, z0 + 0.012), (cx1, c1, z0 + 0.012), (hx0 + 0.3, c1, z0 + 0.012), (0, 0, 1), [(0, 5), (0, 0), (1, 0), (1, 5)])
    me.quad('ss_tw2', (hx0 + 0.3, c0, z0 + h - e), (cx1, c0, z0 + h - e), (cx1, c1, z0 + h - e), (hx0 + 0.3, c1, z0 + h - e), (0, 0, -1), [(0, 0.05), (5, 0.05), (5, 0.6), (0, 0.6)])   # (judge E14: was tex_tc)
    # passage
    wall(me, 'x', cx0 + e, 1, wy, sy0, z0, z0 + h, 'ss_tw2', step=B4, tbase=c0)
    wall(me, 'y', sy1 - e, -1, cx0, cx1, z0, z0 + h, 'ss_tw2', step=B4, tbase=cx0)
    me.quad('ss_tfw', (cx0, wy, z0 + 0.012), (cx1, wy, z0 + 0.012), (cx1, sy1, z0 + 0.012), (cx0, sy1, z0 + 0.012), (0, 0, 1), [(0, 0), (1, 0), (1, 1), (0, 1)])
    me.quad('ss_tw2', (cx0, wy, z0 + h - e), (cx1, wy, z0 + h - e), (cx1, sy1, z0 + h - e), (cx0, sy1, z0 + h - e), (0, 0, -1), [(0, 0.05), (0.45, 0.05), (0.45, 0.6), (0, 0.6)])
    # lift room
    wall(me, 'x', r0 + e, 1, hy0, c1, z0, zc, 'ss_tw2', step=B4, tbase=hy0)
    wall(me, 'y', hy0 + e, 1, r0, hx0, z0, zc, 'ss_tw2', step=B4, tbase=r0)
    wall(me, 'y', c1 - e, -1, r0, hx0 + 0.3, z0, zc, 'ss_tw2', step=B4, tbase=r0)
    me.quad('ss_tfw', (r0, hy0, z0 + 0.012), (hx0, hy0, z0 + 0.012), (hx0, c1, z0 + 0.012), (r0, c1, z0 + 0.012), (0, 0, 1), [(0, 0), (2, 0), (2, 3), (0, 3)])
    me.quad('ss_tw2', (r0, hy0, zc - e), (hx0, hy0, zc - e), (hx0, c1, zc - e), (r0, c1, zc - e), (0, 0, -1), [(0, 0.05), (1.2, 0.05), (1.2, 0.6), (0, 0.6)])
    # stairs: the side walls follow the slope, 32 steps 0.30 x 0.25 from the shed down to the passage
    sx0, sx1, top, rise_run = 167.0, 176.6, V.SHED[2], 0.25 / 0.30
    fl = lambda x_: top - rise_run * (x_ - sx0)
    for x in np.arange(sx0, sx1 - 0.01, 1.2):
        x2 = min(x + 1.2, sx1)
        if x >= sx0 + 3.6 - 1e-6:                          # (judge R15: tex_tc read as a black void over the stairs, and the first bay was lost to float: the walls' concrete, lit)
            me.quad('ss_tw2', (x, sy0, fl(x) + 2.33), (x2, sy0, fl(x2) + 2.33), (x2, sy1, fl(x2) + 2.33), (x, sy1, fl(x) + 2.33), (0, 0, -1), [(0.1, 0.05), (0.4, 0.05), (0.4, 0.5), (0.1, 0.5)])
        for yw, f_ in ((sy0 + e, 1), (sy1 - e, -1)):
            u0, u1 = (x - sx0) / B4, (x2 - sx0) / B4
            zt1, zt2 = min(fl(x) + 2.35, top + 0.06), min(fl(x2) + 2.35, top + 0.06)   # (owner 39: the lining rose through the shed floor: a one-sided wedge, seen on the left only)
            me.quad('ss_tw2', (x, yw, fl(x)), (x2, yw, fl(x2)), (x2, yw, zt2), (x, yw, zt1), (0, f_, 0), [(u0, 1), (u1, 1), (u1, 0), (u0, 0)])
    xr_ = sx0 + 3.6                                         # (judge R15: the step from the stair ceiling up to the shed floor's underside (top - 0.05, ray test), and that underside to the hatch)
    me.quad('ss_tw2', (xr_, sy0, fl(xr_) + 2.33), (xr_, sy1, fl(xr_) + 2.33), (xr_, sy1, top - 0.07), (xr_, sy0, top - 0.07), (-1, 0, 0), [(0.1, 0.05), (0.4, 0.05), (0.4, 0.2), (0.1, 0.2)])
    me.quad('ss_tw2', (170.12, sy0, top - 0.07), (xr_, sy0, top - 0.07), (xr_, sy1, top - 0.07), (170.12, sy1, top - 0.07), (0, 0, -1), [(0.1, 0.05), (0.25, 0.05), (0.25, 0.4), (0.1, 0.4)])
    # rock behind the thin concrete: corridor + passage + lift room
    zb0, zb1 = z0 - 1.0, z0 + 3.4
    uvd = [(0, 0), (1, 0), (1, 0.2), (0, 0.2)]
    me.quad('ss_tc', (r0 - 1.0, hy0 - 1.0, zb0), (r0 - 1.0, 234.3, zb0), (r0 - 1.0, 234.3, zc + 1.0), (r0 - 1.0, hy0 - 1.0, zc + 1.0), (1, 0, 0), uvd)        # lift room, west
    me.quad('ss_tc', (r0 - 1.0, hy0 - 1.0, zb0), (hx1 + 1.0, hy0 - 1.0, zb0), (hx1 + 1.0, hy0 - 1.0, zc + 1.0), (r0 - 1.0, hy0 - 1.0, zc + 1.0), (0, 1, 0), uvd)   # south
    me.quad('ss_tc', (r0 - 1.0, 234.3, zb0), (175.8, 234.3, zb0), (175.8, 234.3, zb1), (r0 - 1.0, 234.3, zb1), (0, -1, 0), uvd)                                 # north of the corridor
    me.quad('ss_tc', (hx1 + 0.5, c0 - 1.0, zb0), (cx1 + 1.0, c0 - 1.0, zb0), (cx1 + 1.0, c0 - 1.0, zb1), (hx1 + 0.5, c0 - 1.0, zb1), (0, 1, 0), uvd)             # south of the corridor
    me.quad('ss_tc', (cx1 + 1.0, c0 - 1.0, zb0), (cx1 + 1.0, sy1 + 1.2, zb0), (cx1 + 1.0, sy1 + 1.2, zb1), (cx1 + 1.0, c0 - 1.0, zb1), (-1, 0, 0), uvd)           # east of the passage
    # lamps + cages every 4 m along the corridor, two on the stairs, one in the passage, two in the lift room
    pts = [(x, c0 + 0.1, z0 + 2.0, 1) for x in np.arange(hx0 + 2.0, cx1, 4.0)] + [(177.5, 238.6, z0 + 2.0, -1), (172.0, sy0 + 0.1, fl(172.0) + 2.0, 1), (175.5, sy1 - 0.1, fl(175.5) + 2.0, -1),
                                                                                  (160.8, hy0 + 0.1, z0 + 3.0, 1), (160.8, c1 - 0.1, z0 + 3.0, -1)]
    pts.append((168.9, sy1 - 0.1, fl(168.9) + 2.0, -1))     # (judge E14 11-12: a third lamp at the stairs' top)
    for x, y, z, sg in ((cx0 + 0.1, 235.6, z0 + 2.0, 1), (r0 + 0.1, (hy0 + c1) / 2, z0 + 3.0, 1)):   # (judge E14: fill lamps on the passage's and the lift room's west walls, facing +x)
        x1 = x + sg * 0.05
        me.box('ss_stl', min(x, x1), y - 0.12, z - 0.08, max(x, x1), y + 0.12, z + 0.08, solid=False)
        xf = x1 + sg * 0.006
        me.quad('ss_lampb', (xf, y + 0.11, z - 0.07), (xf, y - 0.11, z - 0.07), (xf, y - 0.11, z + 0.07), (xf, y + 0.11, z + 0.07), (sg, 0, 0), [(0, 1), (1, 1), (1, 0), (0, 0)])
        me.box('ss_stl', min(x - sg * 0.1, x), y - 0.14, z + 0.08, max(x, x1 + sg * 0.02), y + 0.14, z + 0.11, solid=False)
        me.lamp((x1 + sg * 0.1, y, z), 420.0, (1.0, 0.8, 0.5))
    for x, y, z, sg in pts:
        y1 = y + sg * 0.05
        me.box('ss_stl', x - 0.12, min(y, y1), z - 0.08, x + 0.12, max(y, y1), z + 0.08, solid=False)   # (judge R15: a glowing cube; now a steel housing, the lens on it)
        yf = y1 + sg * 0.006
        me.quad('ss_lampb', (x - 0.11, yf, z - 0.07), (x + 0.11, yf, z - 0.07), (x + 0.11, yf, z + 0.07), (x - 0.11, yf, z + 0.07), (0, sg, 0), [(0, 1), (1, 1), (1, 0), (0, 0)])
        me.quad('ss_lampb', (x - 0.11, min(y, y1) + 0.005, z - 0.086), (x + 0.11, min(y, y1) + 0.005, z - 0.086), (x + 0.11, max(y, y1) - 0.005, z - 0.086), (x - 0.11, max(y, y1) - 0.005, z - 0.086), (0, 0, -1), [(0, 0.35), (1, 0.35), (1, 0.65), (0, 0.65)])
        me.box('ss_stl', x - 0.14, min(y - sg * 0.1, y), z + 0.08, x + 0.14, max(y, y1 + sg * 0.02), z + 0.11, solid=False)
        me.lamp((x, y1 + sg * 0.1, z), 420.0, (1.0, 0.8, 0.5))
    # pipes along the corridor's north wall and down the stairs, a cable tray
    for zp, r_ in ((z0 + 2.12, 0.07), (z0 + 1.95, 0.05)):
        me.cyl('ss_duct', r_, hx0 + 0.3, cx0, 'x', (c1 - 0.14, zp), uv=0.5, seg=8)
    a_, b_ = (sx0 + 1.2, sy1 - 0.12, fl(sx0 + 1.2) + 2.1), (sx1, sy1 - 0.12, fl(sx1) + 2.1)
    me.hull('ss_duct', [(a_[0], a_[1] + o_, a_[2] + o2) for o_ in (-0.06, 0.06) for o2 in (-0.06, 0.06)] + [(b_[0], b_[1] + o_, b_[2] + o2) for o_ in (-0.06, 0.06) for o2 in (-0.06, 0.06)], uv=0.5, solid=False)
    # hazard frames: the cell door, the lift room's mouth
    d0, d1 = cx0, cx0 + V.CELL_DOOR_W
    me.box('ss_hz', d0 - 0.1, c1 - 0.04, z0, d0, c1, z0 + 2.2, uv=0.5, solid=False)
    me.box('ss_hz', d1, c1 - 0.04, z0, d1 + 0.1, c1, z0 + 2.2, uv=0.5, solid=False)
    me.box('ss_hz', d0 - 0.1, c1 - 0.04, z0 + 2.16, d1 + 0.1, c1, z0 + 2.26, uv=0.5, solid=False)
    return me


# ------------------------------------------------------------------------------------------------ the train's skin (owner 11-04: 'simple boxes up close')
def tex_car(rgb, seed):
    """a 1 m steel panel: seams, rivets along them, rust and dust streaks. The cars map a texture once per metre"""
    n = 128
    v, u = np.mgrid[0:1:n * 1j, 0:1:n * 1j]
    s = 0.84 + 0.26 * _noise(n, n, seed)
    s *= 0.92 + 0.12 * np.sin(u * 19.0 + 3.0 * _noise(n, n, seed + 1, (3, 6)))   # (rv13: thresholded streaks repeated each metre read as camouflage)
    img = np.tile(np.asarray(rgb, float), (n, n, 1)) * s[..., None]
    img[:3, :] *= 0.4; img[:, :2] *= 0.55
    for k in range(4):
        cy, cx = int(n * 0.06), int(n * (0.125 + 0.25 * k))
        for yy, xx in ((cy, cx), (cx, int(n * 0.04))):
            img[max(yy - 2, 0):yy + 2, max(xx - 2, 0):xx + 2] = img[max(yy - 2, 0):yy + 2, max(xx - 2, 0):xx + 2] * 0.5 + 0.12
    d = (np.clip((v - 0.55) / 0.45, 0, 1) * (0.5 + 0.5 * _noise(n, n, seed + 2)))[..., None] * 0.35   # dust low on the panel
    return _rgba(img * (1 - d) + np.array([0.60, 0.48, 0.33]) * d)


def tex_track(a, tint):
    return np.dstack([np.clip(a[..., :3] * np.asarray(tint), 0, 1), np.ones(a.shape[:2])])


def drift(x0, x1, yc, z):
    """sand drifted over the rails at the west end of the line: the track runs into the dune, no hard edge"""
    me = Mesh(((x0 + x1) / 2, yc, z), ['ss_sand'])
    hw = 8.5
    foot = z - 1.0                                         # (S7 11-15: was z - 0.5: the ground falls away there, one corner hung 0.42 m in the air)
    me.hull('ss_sand', [(x1, yc + o_, foot) for o_ in (-hw, hw)] + [(x0, yc + o_, foot) for o_ in (-hw, hw)] + [(x0, yc + o_, z + 0.75) for o_ in (-hw + 2, hw - 2)] + [(x0 + (x1 - x0) * 0.35, yc + o_, z + 0.42) for o_ in (-hw + 3, hw - 3)], uv=0.12, solid=False)
    me.box(None, x0 - 0.2, yc - 0.1, z - 1.0, x0, yc + 0.1, z - 0.8)
    return me


def drift_east(xf0, xf1, x1, yc, rail_top, ground, core=3.3, side=3.0, cover=0.12, skin=0.06, under=0.35, fade=1.5):
    """(N3 11-17, ss-ending) sand drifted over the rails at the EAST end, where the dune rises over the line: without it the ballast goes under
    the sand first and ~10 m of bare sleepers and rail heads taper into the sand at the terrain's 3 % grade (editor S7_1817). A terrain-following
    mound (ground(x, y) = terrain z, m): over the track (|y - yc| <= core) max(ground + skin, rail_top + cover); a lee face from xf0 (buried)
    to xf1 (full) where the rails go in; it fades into the dune from x1 - fade to x1 and to the sides over `side` m. Its borders lie `under` m
    below the terrain, so every seam with the terrain is a crossing at >= ~10 degrees, never a long sliver. Seen only. World m -> Mesh"""
    xs = sorted(set([round(v, 3) for v in np.arange(xf0 - 1.0, xf1 + 1.01, 0.5)] + [round(v, 3) for v in np.arange(xf1 + 1.0, x1 - fade, 1.0)] +
                    [round(v, 3) for v in np.arange(x1 - fade - 0.5, x1 + 0.01, 0.5)]))
    ys = list(np.arange(-(core + side + 0.5), core + side + 0.51, 0.5))
    sm = lambda t: (lambda c: c * c * (3 - 2 * c))(min(1.0, max(0.0, t)))
    me = Mesh(((xs[0] + xs[-1]) / 2, yc, rail_top), ['ss_sand'])
    P = np.zeros((len(xs), len(ys), 3))
    for i, x in enumerate(xs):
        wx = sm((x - xf0) / (xf1 - xf0)) * (1.0 - sm((x - (x1 - fade)) / fade))
        for j, dy in enumerate(ys):
            g = ground(x, yc + dy)
            b = max(skin, rail_top + cover - g)                # over the terrain at the track
            h = -under + (b + under) * wx                      # the lee face and the east fade
            h = h + (-under - h) * sm((abs(dy) - core) / side)  # the sides
            P[i, j] = (x, yc + dy, g + h)
    N = np.zeros_like(P)                                       # smooth normals (the sun lights it by them)
    gx, gy = np.gradient(P[:, :, 2], np.array(xs), np.array(ys))
    N[:, :, 0], N[:, :, 1], N[:, :, 2] = -gx, -gy, 1.0
    N /= np.linalg.norm(N, axis=2, keepdims=True)
    nj = len(ys)
    T = []
    for i in range(len(xs) - 1):
        for j in range(nj - 1):
            a, b_, c, d = i * nj + j, (i + 1) * nj + j, (i + 1) * nj + j + 1, i * nj + j + 1
            T += [(a, b_, c), (a, c, d)]
    T = np.array(T)
    Pf = (P.reshape(-1, 3) - me.o) * M
    Nf = N.reshape(-1, 3)
    T = SL._orient(Pf, T, Nf, Nf[T].mean(1))
    U = (P.reshape(-1, 3)[:, :2] - me.o[:2]) * 0.12           # (the west drift's sand scale)
    me.g['ss_sand'].append((Pf, T, Nf, U))
    me.box(None, xs[0], yc - 0.1, rail_top - 1.4, xs[0] + 0.2, yc + 0.1, rail_top - 1.2)   # (a model needs a collision piece: buried)
    me.grid = P                                                # (for the offline check)
    return me


def cage_gate_model():
    """the cage's gate: a steel frame with bars, 2.2 m wide, 3.3 m high, origin = bottom centre; built lying down like the blast gate (it slides up)"""
    hw, h = 1.08, 3.3
    me = Mesh((0, 0, 0), ['ss_hz', 'ss_stl'])
    me.box('ss_hz', -0.05, -hw, 0.0, 0.05, hw, 0.18, uv=0.5)
    me.box('ss_hz', -0.05, -hw, h - 0.18, 0.05, hw, h, uv=0.5)
    for y in (-hw, hw - 0.1):
        me.box('ss_stl', -0.05, y, 0.0, 0.05, y + 0.1, h, uv=0.5)
    for y in np.arange(-0.8, 0.81, 0.32):
        me.box('ss_stl', -0.025, y - 0.025, 0.18, 0.025, y + 0.025, h - 0.18, uv=0.5, solid=False)
    me.box('ss_stl', -0.05, -hw, 1.5, 0.05, hw, 1.6, uv=0.5)
    me.box(None, -0.06, -hw, 0.0, 0.06, hw, h)
    R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    for k_ in me.g:
        me.g[k_] = [(P_ @ R.T, T_, N_ @ R.T, U_) for P_, T_, N_, U_ in me.g[k_]]
    me.coll = [(P_ @ R.T, T_, N_ @ R.T, U_) for P_, T_, N_, U_ in me.coll]
    return me.model()
