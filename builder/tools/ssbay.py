"""ssbay - Sandstorm's use points (owner 11-07, items 85, 86): how Jones steals the chip, and every panel he works at. Flag SS_BAY=1, default 0 until proven.

Hooks in build_sandstorm.py: models(globals()) beside the other X.models of the set piece, lib(_SLIB, _orig_tex) before _SLIB.install, apply(globals()) before the final write.

What the original clips really do (read from COMMON/models/new.res, work/sandstorm/bay/fk.py, atta.py, hands.py):
- A use pops Jones to the use point + 0.85 m along its local +y, feet on the floor, facing it (rig b1, b4: 248.72 -> 247.87, 267.87 -> 267.02; Activate Offset 0). The originals' cabinet 262_07_1 and its clip agree.
- A clip carries props in its ATTA chunk, drawn by the engine in the clip's frame (x right, y forward, z up, origin at his feet) or on a hand bone. turn_wheel carries its own turning wheel 515_04_1 at (-0.01, 0.86, 1.12).
  The builder placed a second wheel 27 cm higher (1.39). That was the owner's 'duplicated' (85), and why his hands missed it.
- tba_sabotage IS the originals' 'open a panel, cut a wire': knife 111_01_1 in the right hand, panel 262_05_1 at (0.13, 0.58, 0.905) levered up from 1.9 s to 81 degrees at 3.24 s on its left edge, the knife laid down at
  (0.37, 0.69, 0.95) from 3.87 to 5.78 s, wire 262_06_1 at (0.49, 0.44, 0.79) torn out at 5.04-5.31 s. The originals cut the clip at 4-5 s, before the wire. Here it runs to the end.
- tba_filing_search: left hand planted at (-0.29, 1.10, 1.25) from 1.2 to 3.2 s, right hand working at (-0.1, 0.85, 1.22), up to (0, 0.8, 1.45) at the end.
- tba_hack_code_pad: fingers at z 1.11-1.31, y 0.72-0.84, the map computer in the left hand. A 360_16_1 pad is 0.36 m tall from its origin, so its origin belongs 1.03 m over the floor. The pads stood at 1.25-1.35.

The steal, two uses, both new, on original clips and props:
1. Lock box: a waist-high box bolted to the missile under the guidance hatch, built round the clip's own numbers. Jones levers the lid with his knife, lays the knife on the box, tears the lock wire out. The clip draws lid and wire while it runs, so the
   box's own lid and wire (ss_gbc_1) hide during the use, and the same parts in their end pose (ss_gbo_1) stay after it.
2. Hatch: the wire cut, the hatch above springs open on a red module. Jones plants his left hand inside the hatch, takes the handle and lifts the module out. CHIP stays the id of this last use, so every rule that reads it stands.
"""
import math, os
import numpy as np

BAY = os.environ.get('SS_BAY', '1') == '1'
HERE = os.path.dirname(os.path.abspath(__file__))
PLAY = {'tba_sabotage': 6.4, 'tba_filing_search': 3.85}    # (seconds of a use: the clip to its end, less the last frames)
STAND = 0.85                                               # m, use point to where the engine stands him
PAD_Z = 1.03                                               # m over the floor, origin of a 360_16_1 code pad
OBJ5 = 'Open the cage from the control room. At the missile, cut the lock wire on the guidance box, then pull the chip from its hatch.'
# world frame of the set piece: he faces +x on the gantry (rig: floor at z = F)
S1 = (247.87, 238.0)                                       # step 1 stand, the use point stays where the chip's was
S2 = (247.60, 237.9)                                       # step 2 stand: left hand on the hatch's back plate, right hand on the module's handle
O = (248.5, 237.8)                                         # model origin of the box parts, on the floor
BOX = (248.22, 237.20, 248.90, 238.35)                     # x0, y0, x1, y1
TOP = 0.905                                                # the clip's lid rests here
CUT_Z, CHIP_Z = 0.9, 1.22                                  # use points over the floor
HOLE = (248.30, 237.49, 248.54, 237.88)                    # under the lid, clip footprint x 0.13..0.50, y 0.43..0.66
TRAY = 0.66                                                # his fingers reach 0.68 down there at 4.7 s
HATCH = (248.72, 238.0, 1.25)                              # centre on the skin
HW, HH = 0.30, 0.33
HINGE = (248.71, 238.0 + HW)
MOD = (248.60, 238.0, 1.23)                                # the module's centre, handle bar at x 248.45
LID0 = ((533.71, 2376.54, 3708.07), (0.0, 0.0, 0.0, 1.0))
WIRE0 = ((1988.85, 1792.49, 3249.17), (0.0, 0.0, 0.0, 1.0))
LID1 = ((533.71, 2376.54, 3708.07), None)                  # (end quaternions read from the clip in _clip_end)
WIRE1 = ((1988.85, 1662.25, 3249.17), None)
OPEN_STEPS = [(0.00, 0.12, -18.0), (0.12, 0.24, -48.0), (0.24, 0.36, -80.0), (0.36, 0.48, -100.0)]   # (spring-loaded hatch: seconds after the cut, swing)
DOOR_END = -105.0
HAND = [(2.75, 2.95, 0.097, 0.834, 1.252), (2.95, 3.15, 0.137, 0.79, 1.395), (3.15, 3.35, 0.139, 0.779, 1.422), (3.35, 3.55, 0.138, 0.778, 1.421), (3.55, 3.75, 0.183, 0.707, 1.362)]   # (t0, t1, x, y, z: the right palm over the end of tba_filing_search, work/sandstorm/bay/fk.py; the module rides in it)


def _qmat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _clip_end():
    """the last keys of the lid and the wire in tba_sabotage: the pose the static parts must take"""
    import struct, ilff
    import prefab
    form, ch, h = ilff.read(open(os.path.join(prefab.GAME, 'COMMON', 'models', 'new.res'), 'rb').read())
    body = [b for n, t, b in ilff.entries(ch) if n and n.endswith('anims/tba_sabotage.iff')][0]
    f2, c2, _ = ilff.read(body)
    d = dict((c[0], c[1]) for c in c2)
    a, tv = d[b'ATTA'], d[b'TNVE']
    out = {}
    for i in range(0, len(a), 80):
        e = a[i:i + 80]
        nm = e[:16].split(b'\0')[0].decode('latin1')
        p = struct.unpack_from('<4i', e, 64)[3] * 4
        if not p or nm not in ('262_05_1', '262_06_1'):
            continue
        while True:
            nx = struct.unpack_from('<I', tv, p + 8)[0]
            pos = struct.unpack_from('<3f', tv, p + 12)
            quat = struct.unpack_from('<4f', tv, p + 24)
            if not nx:
                break
            p = nx * 4
        out[nm] = (pos, quat)
    return out


def _orig_part(name, pose):
    """an original model's triangles by texture, placed by a clip pose into the box's model frame (clip -> world: x y z -> y, -x, z at S1, less O) -> {tex name: part}"""
    import prefab, mefmesh
    lv = prefab.Level(os.path.join(prefab.GAME, 'MISSIONS', 'location3', 'LEVEL4'))
    mefn, texs = lv.find_vnam(name).entry(name)
    r = mefmesh.RigidModel.from_mef(mefmesh.Mef.read(lv.find_resource('LOCAL:models/%s.mef' % mefn, 'models')[1]))
    pos, q = pose
    R = _qmat(q)
    W = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    out = {}
    org = np.array([(S1[0] - O[0]) * 4096, (S1[1] - O[1]) * 4096, 0.0])
    for g in r.groups:
        P = (g.pos @ R.T + np.array(pos)) @ W.T + org
        tri = g.pos[g.tris]
        if g.nrm is not None:
            N0 = g.nrm
        else:
            fn = -np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            N0 = np.zeros_like(g.pos)
            for k in range(3):
                np.add.at(N0, g.tris[:, k], fn)
            N0 = N0 / np.maximum(np.linalg.norm(N0, axis=1, keepdims=True), 1e-9)
        out.setdefault(texs[g.tex], []).append((P.astype(np.float32), np.asarray(g.tris), (N0 @ R.T @ W.T).astype(np.float32), np.asarray(g.uv).astype(np.float32)))
    return out


def _b(x0, y0, z0, x1, y1, z1):
    """a box in world x y over the floor z -> model frame"""
    import biprefabs as BP
    return BP.box_m(x0 - O[0], y0 - O[1], z0, x1 - O[0], y1 - O[1], z1)


def _u(ox, oy, oz):
    """the same for a model that IS a use point at (ox, oy, floor + oz), turned pi / 2: a use point with no model of its own engages only in a narrow cone, the prompt flickers (rig c1, h3)"""
    import biprefabs as BP
    return lambda x0, y0, z0, x1, y1, z1: BP.box_m(y0 - oy, ox - x1, z0 - oz, y1 - oy, ox - x0, z1 - oz)


# ---------------------------------------------------------------- looks (judge 11-08 R04: the box read as plain blocks)
A_FRONT, A_SIDE, A_TOP = (0.0, 0.0, 0.5, 0.5), (0.5, 0.0, 0.75, 0.5), (0.75, 0.0, 1.0, 0.5)
A_MODF, A_MODS, A_PCB, A_STEEL = (0.0, 0.5, 0.25, 0.75), (0.25, 0.5, 0.5, 0.75), (0.5, 0.5, 0.75, 0.75), (0.75, 0.5, 1.0, 0.75)
A_DARK, A_HATCH, A_WIRE, A_OLIVE = (0.0, 0.75, 0.25, 1.0), (0.25, 0.75, 0.5, 1.0), (0.5, 0.75, 0.75, 1.0), (0.75, 0.75, 1.0, 1.0)


def _atlas():
    """one 512 x 512 painted sheet for the box, the hatch and the module: worn olive steel with rivets, a hazard band and an Arabic plate,
    a red module face with grille and label, a circuit board for the insides, brushed steel, the hatch in the missile's paint with its stencil"""
    import altex
    from PIL import Image, ImageDraw
    N = 512
    rng = np.random.default_rng(85)
    img = Image.new('RGB', (N, N), (60, 64, 46))
    d = ImageDraw.Draw(img)
    px = lambda r: (int(r[0] * N), int(r[1] * N), int(r[2] * N) - 1, int(r[3] * N) - 1)

    def fill(r, rgb):
        d.rectangle(px(r), fill=tuple(int(c * 255) for c in rgb))

    def rivets(r, step, col=(44, 46, 34), hi=(118, 120, 96)):
        x0, y0, x1, y1 = px(r)
        for x in range(x0 + 8, x1 - 4, step):
            for y in (y0 + 7, y1 - 7):
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=col); d.point((x - 1, y - 1), fill=hi)
        for y in range(y0 + 8, y1 - 4, step):
            for x in (x0 + 7, x1 - 7):
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=col); d.point((x - 1, y - 1), fill=hi)

    def text(r, t, pt, col, bold=True):
        x0, y0, x1, y1 = px(r)
        shown, f, bb = altex._draw_line(d, N, x0, x1, y0, t, pt, col, bold)
        d.text(((x0 + x1 - (bb[2] - bb[0])) // 2 - bb[0], (y0 + y1 - (bb[3] - bb[1])) // 2 - bb[1]), shown, font=f, fill=col)

    olive = (0.31, 0.34, 0.24)
    for r in (A_FRONT, A_SIDE, A_TOP, A_OLIVE):
        fill(r, olive)
    # front: frame, hazard band, plate, vents
    x0, y0, x1, y1 = px(A_FRONT)
    d.rectangle((x0 + 3, y0 + 3, x1 - 3, y1 - 3), outline=(38, 41, 30), width=3)
    for k in range(-2, 16):
        xa = x0 + k * 18
        d.polygon([(xa, y0 + 16), (xa + 9, y0 + 16), (xa + 23, y0 + 44), (xa + 14, y0 + 44)], fill=(214, 168, 30))
    d.rectangle((x0, y0 + 13, x1, y0 + 16), fill=(30, 30, 26)); d.rectangle((x0, y0 + 44, x1, y0 + 47), fill=(30, 30, 26))
    d.rectangle((x0 + 40, y0 + 66, x1 - 40, y0 + 130), fill=(222, 218, 200), outline=(40, 40, 36), width=2)
    text((A_FRONT[0] + 0.09, A_FRONT[1] + 0.135, A_FRONT[2] - 0.09, A_FRONT[1] + 0.2), 'قفل منظومة التوجيه', 30, (20, 20, 18))
    text((A_FRONT[0] + 0.09, A_FRONT[1] + 0.2, A_FRONT[2] - 0.09, A_FRONT[1] + 0.25), 'خطر - لا تفتح', 22, (170, 20, 16))
    for k in range(7):
        yy = y0 + 160 + k * 11
        d.rectangle((x0 + 70, yy, x1 - 70, yy + 5), fill=(26, 28, 22)); d.line((x0 + 70, yy + 6, x1 - 70, yy + 6), fill=(96, 102, 76))
    d.text((x0 + 14, y1 - 26), 'GL-07   0441', fill=(196, 192, 170))
    rivets(A_FRONT, 40)
    # side: ribs
    x0, y0, x1, y1 = px(A_SIDE)
    for k in range(5):
        xx = x0 + 14 + k * 24
        d.rectangle((xx, y0 + 20, xx + 8, y1 - 20), fill=(74, 80, 58)); d.line((xx + 9, y0 + 20, xx + 9, y1 - 20), fill=(34, 36, 28), width=2)
    rivets(A_SIDE, 36)
    # top: tread plate
    fill(A_TOP, (0.27, 0.28, 0.25))
    x0, y0, x1, y1 = px(A_TOP)
    for yy in range(y0 + 6, y1, 14):
        for xx in range(x0 + 6 + (yy // 14 % 2) * 7, x1 - 4, 14):
            d.line((xx, yy, xx + 6, yy + 4), fill=(110, 112, 102), width=2)
    rivets(A_TOP, 42, (30, 30, 28), (150, 150, 140))
    # module face: red enamel, grille, label, screws, hazard strip
    fill(A_MODF, (0.58, 0.10, 0.07))
    x0, y0, x1, y1 = px(A_MODF)
    d.rectangle((x0 + 4, y0 + 4, x1 - 4, y1 - 4), outline=(70, 10, 8), width=3)
    for k in range(6):
        yy = y0 + 18 + k * 9
        d.rounded_rectangle((x0 + 20, yy, x0 + 66, yy + 4), 2, fill=(24, 6, 6))
    d.rectangle((x0 + 74, y0 + 16, x1 - 14, y0 + 70), fill=(232, 228, 214), outline=(30, 30, 30))
    text((A_MODF[0] + 0.15, A_MODF[1] + 0.035, A_MODF[2] - 0.03, A_MODF[1] + 0.09), 'وحدة التوجيه', 16, (10, 10, 10))
    d.text((x0 + 80, y0 + 54), 'GU-7  0214', fill=(20, 20, 20))
    for xx, yy in ((x0 + 12, y0 + 12), (x1 - 12, y0 + 12), (x0 + 12, y1 - 12), (x1 - 12, y1 - 12)):
        d.ellipse((xx - 5, yy - 5, xx + 5, yy + 5), fill=(170, 168, 160)); d.line((xx - 3, yy, xx + 3, yy), fill=(60, 60, 60), width=2)
    d.rectangle((x0 + 20, y1 - 46, x1 - 20, y1 - 30), fill=(214, 168, 30))
    for k in range(9):
        xa = x0 + 20 + k * 11
        d.polygon([(xa, y1 - 30), (xa + 5, y1 - 30), (xa + 11, y1 - 46), (xa + 6, y1 - 46)], fill=(24, 22, 20))
    # module side: red with ribs
    fill(A_MODS, (0.52, 0.09, 0.06))
    x0, y0, x1, y1 = px(A_MODS)
    for k in range(8):
        yy = y0 + 10 + k * 15
        d.line((x0 + 6, yy, x1 - 6, yy), fill=(90, 14, 10), width=3); d.line((x0 + 6, yy + 3, x1 - 6, yy + 3), fill=(170, 40, 30))
    # circuit board: muted green, dull solder traces, components with shadows, dirt (judge 11-08: the first was neon)
    fill(A_PCB, (0.05, 0.12, 0.07))
    x0, y0, x1, y1 = px(A_PCB)
    for k in range(46):
        xa, ya = int(rng.integers(x0, x1)), int(rng.integers(y0, y1))
        xb = int(np.clip(xa + rng.integers(-40, 40), x0, x1)); yb = int(np.clip(ya + rng.integers(-40, 40), y0, y1))
        d.line((xa, ya, xb, ya, xb, yb), fill=(92, 84, 46), width=1)
    for k in range(14):
        xa, ya = int(rng.integers(x0 + 8, x1 - 30)), int(rng.integers(y0 + 8, y1 - 20))
        w_, h_ = int(rng.integers(10, 26)), int(rng.integers(6, 14))
        d.rectangle((xa + 2, ya + 2, xa + w_ + 3, ya + h_ + 3), fill=(8, 16, 10))           # shadow
        d.rectangle((xa, ya, xa + w_, ya + h_), fill=(26, 26, 28)); d.line((xa, ya, xa + w_, ya), fill=(70, 70, 72))
    d.rectangle((x0 + 30, y0 + 40, x1 - 30, y1 - 40), outline=(96, 92, 74), width=2)
    # brushed steel
    x0, y0, x1, y1 = px(A_STEEL)
    for yy in range(y0, y1 + 1):
        c = int(128 + rng.normal(0, 9)); d.line((x0, yy, x1, yy), fill=(c, c + 1, c + 2))
    fill(A_DARK, (0.07, 0.07, 0.07))
    # hatch: the missile's paint, stencil, orange edge, rivets
    fill(A_HATCH, (0.80, 0.80, 0.77))
    x0, y0, x1, y1 = px(A_HATCH)
    d.rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), outline=(196, 90, 30), width=6)
    text((A_HATCH[0] + 0.03, A_HATCH[1] + 0.07, A_HATCH[2] - 0.03, A_HATCH[1] + 0.13), 'فتحة الخدمة', 22, (40, 40, 40))
    d.text((x0 + 30, y0 + 74), 'G-BAY 7', fill=(50, 50, 50))
    for xx in (x0 + 12, x1 - 12):
        for yy in range(y0 + 14, y1 - 6, 24):
            d.ellipse((xx - 3, yy - 3, xx + 3, yy + 3), fill=(110, 110, 104))
    # wires: red, yellow, blue, black, green, white
    x0, y0, x1, y1 = px(A_WIRE)
    w_ = (x1 - x0) // 6
    for k, col in enumerate(((170, 24, 18), (214, 168, 30), (30, 60, 150), (20, 20, 20), (30, 120, 50), (200, 200, 190))):
        d.rectangle((x0 + k * w_, y0, x0 + (k + 1) * w_ - 2, y1), fill=col)
        d.line((x0 + k * w_ + 3, y0, x0 + k * w_ + 3, y1), fill=tuple(min(255, c + 70) for c in col))
    a = np.asarray(img, float) / 255.0
    g = altex.noise(N, N, 85)
    a = a * (0.86 + 0.18 * g[..., None])
    r0, c0, r1, c1 = int(A_PCB[1] * N), int(A_PCB[0] * N), int(A_PCB[3] * N), int(A_PCB[2] * N)
    a[r0:r1, c0:c1] *= (0.72 + 0.3 * g[r0:r1, c0:c1, None] ** 2)
    return np.dstack([np.clip(a, 0, 1), np.ones((N, N))])


def _xf(ox, oy, oz):
    """world (x, y, floor z) -> the frame of a model that is a use point at (ox, oy, floor + oz), turned pi / 2"""
    P = lambda p: (p[1] - oy, ox - p[0], p[2] - oz)
    V = lambda v: (v[1], -v[0], v[2])
    return P, V


def _sub(r, f):
    return (r[0] + (r[2] - r[0]) * f[0], r[1] + (r[3] - r[1]) * f[1], r[0] + (r[2] - r[0]) * f[2], r[1] + (r[3] - r[1]) * f[3])


def _cube(xf, x0, y0, z0, x1, y1, z1, faces):
    """a box in world metres from textured panels; faces = {'front' (-x, toward Jones), 'back', 'left' (+y), 'right' (-y), 'top', 'bottom': atlas rect}"""
    import modelkit as MK
    P, V = xf
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    w, d_, h = x1 - x0, y1 - y0, z1 - z0
    spec = {'front': ((x0, cy, cz), (0, -1, 0), (0, 0, 1), d_, h), 'back': ((x1, cy, cz), (0, 1, 0), (0, 0, 1), d_, h),
            'left': ((cx, y1, cz), (-1, 0, 0), (0, 0, 1), w, h), 'right': ((cx, y0, cz), (1, 0, 0), (0, 0, 1), w, h),
            'top': ((cx, cy, z1), (0, -1, 0), (1, 0, 0), d_, w), 'bottom': ((cx, cy, z0), (0, -1, 0), (-1, 0, 0), d_, w)}
    return [MK.panel(P(spec[k_][0]), V(spec[k_][1]), V(spec[k_][2]), spec[k_][3], spec[k_][4], uv=r) for k_, r in faces.items()]


def _all(r):
    return {k_: r for k_ in ('front', 'back', 'left', 'right', 'top', 'bottom')}


def _box_body():
    import modelkit as MK
    xf = _xf(S1[0] + STAND, S1[1], CUT_Z)
    _b = _u(S1[0] + STAND, S1[1], CUT_Z)
    x0, y0, x1, y1 = BOX
    a0, b0, a1, b1 = HOLE
    L = 0.025                                              # the top lip overhangs the body
    p = []
    p += _cube(xf, x0 - 0.02, y0 - 0.02, 0.0, x1, y1 + 0.02, 0.07, _all(A_DARK))                                    # plinth
    p += _cube(xf, x0, y0, 0.07, x1, y1, TOP - 0.035, {'front': _sub(A_FRONT, (0, 0.1, 1, 1)), 'left': A_SIDE, 'right': A_SIDE, 'back': A_OLIVE})
    p += _cube(xf, x0 - L, y0 - L, TOP - 0.035, x1, y1 + L, TOP - 0.012, {'front': _sub(A_FRONT, (0, 0.0, 1, 0.1)), 'left': A_STEEL, 'right': A_STEEL, 'bottom': A_DARK})
    tz = TOP - 0.012
    W_, D_ = y1 - y0 + 2 * L, x1 - x0 + L
    for (xa, ya, xb, yb) in ((x0 - L, y0 - L, x1, b0), (x0 - L, b1, x1, y1 + L), (x0 - L, b0, a0, b1), (a1, b0, x1, b1)):   # the top round the hole
        f_ = ((y1 + L - yb) / W_, (x1 - xb) / D_, (y1 + L - ya) / W_, (x1 - xa) / D_)
        p += _cube(xf, xa, ya, tz, xb, yb, TOP, {'top': _sub(A_TOP, f_)})
    for (xa, ya, xb, yb) in ((a0 - 0.03, b0 - 0.03, a0, b1 + 0.03), (a1, b0 - 0.03, a1 + 0.03, b1 + 0.03), (a0, b0 - 0.03, a1, b0), (a0, b1, a1, b1 + 0.03)):
        p += _cube(xf, xa, ya, TOP, xb, yb, TOP + 0.008, _all(A_STEEL))                                               # steel rim
    for xa, ya in ((x0 + 0.03, y0 + 0.03), (x0 + 0.03, y1 - 0.06), (x1 - 0.12, y0 + 0.03), (x1 - 0.12, y1 - 0.06)):   # bolts
        p += _cube(xf, xa, ya, TOP, xa + 0.03, ya + 0.03, TOP + 0.012, _all(A_STEEL))
    p += _cube(xf, a0, b0, TRAY - 0.02, a1, b1, TRAY, {'top': A_PCB})                                                 # the board in the tray
    for xa, ya, xb, yb, f_ in ((a0, b0, a0 + 0.004, b1, 'back'), (a1 - 0.004, b0, a1, b1, 'front'), (a0, b0, a1, b0 + 0.004, 'left'), (a0, b1 - 0.004, a1, b1, 'right')):
        p += _cube(xf, xa, ya, TRAY, xb, yb, TOP - 0.004, {f_: A_DARK})
    for y_ in (b0 + 0.06, b1 - 0.06):                                                                                  # the wire's posts
        p += _cube(xf, a0 + 0.02, y_ - 0.02, TRAY, a0 + 0.05, y_ + 0.02, 0.81, _all(A_STEEL))
    for k_ in range(6):                                                                                                # a loom of thin wires
        y_ = b0 + 0.04 + k_ * 0.05
        p += _cube(xf, a0 + 0.07, y_, TRAY, a1 - 0.03, y_ + 0.012, TRAY + 0.012, _all(_sub(A_WIRE, (k_ / 6, 0, (k_ + 1) / 6, 1))))
    for k_ in range(4):                                                                                                # a cable from the back corner into the missile
        z_ = 0.55 + k_ * 0.1
        p += _cube(xf, x1 - 0.02, y0 + 0.10 + k_ * 0.015, z_, x1 + 0.10 - k_ * 0.012, y0 + 0.14 + k_ * 0.015, z_ + 0.11, _all(_sub(A_WIRE, (3 / 6, 0, 4 / 6, 1))))
    return MK.model([(0, p)], [_b(x0, y0, 0.0, x1, y1, TOP)])


def _pose_model(lid, wire):
    import modelkit as MK
    a = _orig_part('262_05_1', lid)
    b = _orig_part('262_06_1', wire)
    slots = ['261_01_1', '261_07_1', '261_06_1']
    groups = []
    for k_, t_ in enumerate(slots):
        ps = a.get(t_, []) + b.get(t_, [])
        if ps:
            groups.append((k_, ps))
    x0, y0, x1, y1 = HOLE[0], HOLE[1], HOLE[2], HOLE[3]
    return MK.model(groups, [_b(x0, y0, 0.0, x1, y1, TRAY)])


def _hatch_rim():
    import modelkit as MK
    xf = _xf(S2[0] + STAND, S2[1], CHIP_Z)
    _b = _u(S2[0] + STAND, S2[1], CHIP_Z)
    x, y, z = HATCH
    t = x - 0.03
    p = []
    for (ya, za, yb, zb) in ((y - HW - 0.05, z - HH - 0.05, y - HW, z + HH + 0.05), (y + HW, z - HH - 0.05, y + HW + 0.05, z + HH + 0.05),
                             (y - HW, z - HH - 0.05, y + HW, z - HH), (y - HW, z + HH, y + HW, z + HH + 0.05)):
        p += _cube(xf, t, ya, za, x + 0.08, yb, zb, _all(A_STEEL))
    p += _cube(xf, x - 0.002, y - HW, z - HH, x + 0.02, y + HW, z + HH, {'front': A_PCB})                    # the board at the back
    for (ya, za, yb, zb) in ((y - HW, z - HH, y - HW + 0.005, z + HH), (y + HW - 0.005, z - HH, y + HW, z + HH),
                             (y - HW, z - HH, y + HW, z - HH + 0.005), (y - HW, z + HH - 0.005, y + HW, z + HH)):
        p += _cube(xf, t, ya, za, x, yb, zb, _all(A_DARK))                                                     # the recess walls
    for z_ in (MOD[2] - 0.115, MOD[2] + 0.095):                                                                # the module's rails
        p += _cube(xf, t + 0.004, MOD[1] - 0.12, z_, x - 0.002, MOD[1] + 0.12, z_ + 0.02, _all(A_STEEL))
    return MK.model([(0, p)], [_b(x - 0.03, y - HW - 0.05, z - HH - 0.05, x + 0.08, y + HW + 0.05, z + HH + 0.05)])


def _hatch_door():
    """origin on the hinge (+y edge of the hatch), shut along -y, on the skin (outer face at x -0.02)"""
    import biprefabs as BP, modelkit as MK
    w = 2 * HW
    q = MK.panel((-0.021, -w / 2, 0.0), (0, -1, 0), (0, 0, 1), w, 2 * HH, uv=A_HATCH)         # outside, the missile's paint
    r = MK.panel((0.001, -w / 2, 0.0), (0, 1, 0), (0, 0, 1), w, 2 * HH, uv=A_STEEL)
    edges = [BP.box_m(-0.02, -w, -HH, 0.0, -w + 0.004, HH), BP.box_m(-0.02, -0.004, -HH, 0.0, 0.0, HH), BP.box_m(-0.02, -w, -HH, 0.0, 0.0, -HH + 0.004), BP.box_m(-0.02, -w, HH - 0.004, 0.0, 0.0, HH)]
    bars = [BP.box_m(-0.035, -w + 0.05, z_ - 0.02, -0.021, -0.05, z_ + 0.02) for z_ in (-HH + 0.08, HH - 0.08)] + [BP.box_m(-0.035, -w + 0.02, -0.06, -0.021, -w + 0.05, 0.06)]
    return MK.model([(0, [q, r]), (1, edges + bars)], [BP.box_m(-0.02, -0.04, -0.04, 0.0, 0.0, 0.04)])


def _module():
    """the guidance module, origin at its centre: red enamel face with grille and label toward -x (Jones), ribbed sides, steel frame and carrying handle, pins behind"""
    import biprefabs as BP, modelkit as MK
    p = [MK.panel((-0.121, 0.0, 0.0), (0, -1, 0), (0, 0, 1), 0.22, 0.18, uv=A_MODF),
         MK.panel((0.0, -0.111, 0.0), (-1, 0, 0), (0, 0, 1), 0.24, 0.18, uv=A_MODS), MK.panel((0.0, 0.111, 0.0), (1, 0, 0), (0, 0, 1), 0.24, 0.18, uv=A_MODS),
         MK.panel((0.0, 0.0, 0.091), (0, -1, 0), (1, 0, 0), 0.22, 0.24, uv=A_MODS), MK.panel((0.0, 0.0, -0.091), (0, -1, 0), (-1, 0, 0), 0.22, 0.24, uv=A_MODS),
         MK.panel((0.121, 0.0, 0.0), (0, 1, 0), (0, 0, 1), 0.22, 0.18, uv=A_DARK)]
    st = BP.box_m
    steel = [st(-0.128, -0.112, -0.092, -0.12, -0.10, 0.092), st(-0.128, 0.10, -0.092, -0.12, 0.112, 0.092), st(-0.128, -0.112, 0.082, -0.12, 0.112, 0.092), st(-0.128, -0.112, -0.092, -0.12, 0.112, -0.082),
             st(-0.175, -0.085, -0.014, -0.128, -0.065, 0.014), st(-0.175, 0.065, -0.014, -0.128, 0.085, 0.014), st(-0.185, -0.085, -0.016, -0.165, 0.085, 0.016)]
    pins = [st(0.12, -0.08, -0.06, 0.14, 0.08, 0.06)]
    return MK.model([(0, p), (1, steel), (2, pins)], [BP.box_m(-0.02, -0.02, -0.02, 0.02, 0.02, 0.02)])


def models(G):
    if not BAY:
        return
    G['X'].models('location3/LEVEL4', ['262_05_1', '262_06_1', '111_01_1'])


def tone_scientists(ovl):
    """judge 11-08: the scientists' coats (bubsci_1, near pure white, mean 0.83) glowed in the dark hall. The copy merged into this mission's overlay is
    pulled down to an off-white grey with a little grime; folds, the visor and the badge keep their contrast. Only this mission's copy changes."""
    import ilff, igitex, wreck, altex
    p = wreck._ensure_overlay(ovl, 'sandstorm')['textures']
    form, ch, hdr = ilff.read(open(p, 'rb').read())
    key = b'LOCAL:textures/bubsci_1.tex'
    k = next((i for i, (t, d, a) in enumerate(ch) if t == b'NAME' and d.rstrip(b'\0').lower() == key.lower()), None)
    if k is None or ch[k + 1][0] != b'BODY':
        print('ssbay: bubsci_1 texture not in the overlay, coats left as they are'); return
    im = np.array(igitex.decode(ch[k + 1][1]), np.float32)
    rgb = im[..., :3]
    lum = rgb.mean(2, keepdims=True)
    sat = rgb.max(2, keepdims=True) - rgb.min(2, keepdims=True)
    cloth = ((lum > 0.45) & (sat < 0.12)).astype(np.float32)
    g = altex.noise(im.shape[0], im.shape[1], 36)[..., None]
    grey = lum * 0.66 * np.array((0.97, 0.96, 0.91), np.float32) * (0.92 + 0.12 * g)
    im[..., :3] = rgb * (1 - cloth) + grey * cloth
    rim = ((rgb[..., 2:3] > rgb[..., 0:1] + 0.08) & (lum > 0.18)).astype(np.float32)    # (judge A02: the hood's cyan face ring read as a teal fringe next to the grey)
    im[..., :3] = im[..., :3] * (1 - rim) + lum * 0.55 * np.array((0.95, 0.95, 0.92), np.float32) * rim
    ch[k + 1] = (b'BODY', wreck.tex_mode2(np.clip(im, 0, 1)), ch[k + 1][2])
    tmp = p + '.bay.tmp'
    open(tmp, 'wb').write(ilff.write(form, ch, hdr[1] or 4))
    os.replace(tmp, p)
    print('ssbay: scientist coats toned, mean %.2f -> %.2f' % (float(lum.mean()), float(im[..., :3].mean())))


def lib(L, orig_tex, ovl=None):
    if not BAY:
        return
    if ovl and os.environ.get('SS_SCITONE', '1') == '1':
        tone_scientists(ovl)
    for t_ in ('261_01_1', '261_07_1', '261_06_1'):
        L.texture('ss_g' + t_, (lambda s_: (lambda: orig_tex('location3/LEVEL4', s_)))(t_))
    end = _clip_end()
    slots = ['ss_g261_01_1', 'ss_g261_07_1', 'ss_g261_06_1']
    L.texture('ss_gbay', _atlas)
    L.add('ss_gbx_1', _box_body, ['ss_gbay'], lod_like='406_68_1')
    L.add('ss_gbc_1', lambda: _pose_model(LID0, WIRE0), slots, lod_like='406_68_1')
    L.add('ss_gbo_1', lambda: _pose_model(end['262_05_1'], end['262_06_1']), slots, lod_like='406_68_1')
    L.add('ss_ghr_1', _hatch_rim, ['ss_gbay'], lod_like='406_68_1')
    L.add('ss_ghd_1', _hatch_door, ['ss_gbay', 'jr_steel'], lod_like='406_68_1')
    L.add('ss_gmd_1', _module, ['ss_gbay', 'jr_steel', 'jr_dark'], lod_like='406_68_1')


def _set_tba(m, tid, pos, anim, sprite, sound, active):
    for k_, c_ in enumerate(pos):
        m.set(tid, 3 + k_, float(c_))
    m.set(tid, 9, 'ss_ghr_1'); m.set(tid, 10, 'ss_ghr_1')
    m.set(tid, 24, active); m.set(tid, 25, anim); m.set(tid, 26, PLAY[anim]); m.set(tid, 27, sprite); m.set(tid, 28, sound)


def fix_pads(G):
    """item 86: the three code pads level with his fingers. The gate's and the sand door's walls stand plain; the gun room's pad (ss-gunroom) gets the same height"""
    m = G['m']
    gun = [i_ for i_ in m.byid if lit_name(m, i_) == 'SS gun room door lock pad']
    for tid, floor in [(G['GATE_PAD'], G['SB'].F), (G['SAND_PAD'], G['SD_G'])] + [(i_, G['GN'].FZ) for i_ in gun]:
        m.set(tid, 5, (floor + PAD_Z) * 4096.0)
        print('ssbay: pad %d origin %.2f m over the floor' % (tid, PAD_Z))


def fix_generators(G):
    """the map's two generator panels 337_12_1 stand 1.0-1.14 m over the floor, under the code pad clip's hands at 1.11-1.31: pick_lock's both hands work at z 1.03-1.09, y 0.78-0.81, on them"""
    m = G['m']
    for tid in (150, 152):
        m.set(tid, 25, 'pick_lock')
    print('ssbay: generators on pick_lock')


def clear_chairs(G):
    """the chairs at the two server desks stood where the engine puts Jones: he worked with one in his legs. They go back behind him, out of his way"""
    from mission_lib import lit
    m = G['m']
    for tid in (G['COMPUTER'], G['SECURITY_PC']):
        p = [float(lit(m.byid[tid].args[3 + k_])) for k_ in range(2)]
        g = float(lit(m.byid[tid].args[8]))
        fx, fy = -math.sin(g), math.cos(g)
        st = (p[0] + fx * STAND * 4096, p[1] + fy * STAND * 4096)
        for i_ in list(m.byid):
            t_ = m.byid[i_]
            try:
                if str(lit(t_.args[1])) != 'EditRigidObj' or not str(lit(t_.args[9])).endswith('261_06_1'):
                    continue
                q = (float(lit(t_.args[3])), float(lit(t_.args[4])))
            except Exception:
                continue
            if math.hypot(q[0] - st[0], q[1] - st[1]) < 1.0 * 4096:
                m.set(i_, 3, st[0] + fx * 0.9 * 4096 + fy * 0.5 * 4096); m.set(i_, 4, st[1] + fy * 0.9 * 4096 - fx * 0.5 * 4096)
                print('ssbay: chair %d moved clear of the stand at use point %d' % (i_, tid))


def steal(G):
    m, T, nid, F, LOGIC, CHIP = G['m'], G['T'], G['nid'], G['SB'].F, G['LOGIC'], G['CHIP']
    U = lambda x, y, z: (x * 4096.0, y * 4096.0, z * 4096.0)
    rigid = lambda name, x, y, z, g, model: T(nid(), 'EditRigidObj', name, *U(x, y, z), 0.0, 0.0, g, model, 5, False, False)
    cc = lambda name, cond, kids: m.add_child(LOGIC, T(nid(), 'ConditionalContainer', name, cond, '', '', children=kids))
    # out with the wheel
    gone = [t_ for t_, n_ in ((i_, lit_name(m, i_)) for i_ in list(m.byid)) if n_.startswith('SS guidance bay wheel')]
    for t_ in gone:
        m.remove(t_)
    # step 1: the lock box
    CUT = nid()
    G['BAY_CUT'] = CUT
    cage = G['CAGE_PC']
    done = 'GenericTBA_%d.isFinished' % CUT
    shut = '!GenericTBA_%d.isInUse && !%s' % (CUT, done)
    if 'bayaudit' in G['DBG']:                             # (the doubles have no use running: the box hides for the first, the hatch opens for the second)
        done = 'LevelFlow_10.nTick > 58 * GAME_FREQUENCY'
        shut = 'LevelFlow_10.nTick < 14 * GAME_FREQUENCY'
    gone_chip = 'GenericTBA_%d.isFinished' % CHIP
    if 'baydone' in G['DBG']:                              # (test: the theft done, as at the ending)
        done, shut, gone_chip = '1', '0', '1'
    if 'baycam2' in G['DBG']:                              # (step 2 alone: the wire counts as cut 3 s in)
        done = 'LevelFlow_10.nTick > 3 * GAME_FREQUENCY'
    m.add_child(LOGIC, T(CUT, 'GenericTBA', 'SS guidance lock box', *U(S1[0] + STAND, S1[1], F + CUT_Z), 0.0, 0.0, math.pi / 2, 'ss_gbx_1', 'ss_gbx_1',
                         100.0, 0.0, 0.0, 0.0, 0.0, 0, 0, '', '', 0.0, 0.0, 0.0, False, '!GenericTBA_%d.isFinished && GenericTBA_%d.isFinished' % (CUT, cage), 'tba_sabotage', PLAY['tba_sabotage'],
                         'STATUSSCREEN:a_sabotage.spr', 'tba_sabotage'))
    cc('SS lock box shut', shut, [rigid('', O[0], O[1], F, 0.0, 'ss_gbc_1')])
    foot = G.get('SS_FOOT_BOX', '0')                       # (the ending's replay shows the box before the cut: ssoutro draws the rest, the clip its lid and wire)
    cc('SS lock box open', '%s && !(%s)' % (done, foot), [rigid('', O[0], O[1], F, 0.0, 'ss_gbo_1')])
    # step 2: the hatch and the module
    _set_tba(m, CHIP, U(S2[0] + STAND, S2[1], F + CHIP_Z), 'tba_filing_search', 'STATUSSCREEN:a_sabotage.spr', 'tba_sabotage', '!GenericTBA_%d.isFinished && %s' % (CHIP, done))
    hz = F + HATCH[2]
    t1 = nid()
    m.add_child(LOGIC, T(t1, 'LevelTimer', 'SS hatch springs', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, done, '', False))
    cc('SS hatch shut', '!(%s)' % done, [rigid('', HINGE[0], HINGE[1], hz, 0.0, 'ss_ghd_1')])
    for k_, (a_, b_, ang) in enumerate(OPEN_STEPS):
        cc('SS hatch swing %d' % k_, '%s && LevelTimer_%d.nTick >= %.2f * GAME_FREQUENCY && LevelTimer_%d.nTick < %.2f * GAME_FREQUENCY' % (done, t1, a_, t1, b_),
           [rigid('', HINGE[0], HINGE[1], hz, math.radians(ang), 'ss_ghd_1')])
    cc('SS hatch open', 'LevelTimer_%d.nTick >= %.2f * GAME_FREQUENCY && !(%s)' % (t1, OPEN_STEPS[-1][1], foot), [rigid('', HINGE[0], HINGE[1], hz, math.radians(DOOR_END), 'ss_ghd_1')])
    t2 = nid()
    m.add_child(LOGIC, T(t2, 'LevelTimer', 'SS module in his hand', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'GenericTBA_%d.isInUse' % CHIP, '!GenericTBA_%d.isInUse' % CHIP, False))
    path = HAND
    cc('SS module in its socket', '%s && !(%s) && LevelTimer_%d.nTick < %.2f * GAME_FREQUENCY' % (done, gone_chip, t2, path[0][0]), [rigid('', MOD[0], MOD[1], F + MOD[2], 0.0, 'ss_gmd_1')])
    for k_, (a_, b_, x_, y_, z_) in enumerate(path):
        cc('SS module lifted %d' % k_, 'GenericTBA_%d.isInUse && LevelTimer_%d.nTick >= %.2f * GAME_FREQUENCY && LevelTimer_%d.nTick < %.2f * GAME_FREQUENCY' % (CHIP, t2, a_, t2, b_),
           [rigid('', S2[0] + y_, S2[1] - x_, F + z_, 0.0, 'ss_gmd_1')])
    G['msg']('SS_LOCKWIRE', 'SS lock wire cut', 'GenericTBA_%d.isFinished' % CUT, "ANYA: Lock wire's out, the hatch is open. Now the chip, pull it!", 5.0)
    print('ssbay: lock box %d, chip %d: stands %s %s, wheel tasks removed %d' % (CUT, CHIP, S1, S2, len(gone)))


def lit_name(m, i):
    from mission_lib import lit
    try:
        return str(lit(m.byid[i].args[2]))
    except Exception:
        return ''


def debug(G):
    """test variants, never in a release. 'bayopen': the cage stands open, the chip and both pads usable from the start, no launch clock. 'bayaudit': a double of Jones on every use point playing its clip, a side and a front view of each, from second 4"""
    m, DBG = G['m'], G['DBG']
    if 'bayopen' in DBG:
        cage = G['CAGE_PC']
        m.set(G['CAGE_GATE'], 19, '1')
        m.set(cage, 24, '0')
        m.set(G['GATE_PAD'], 24, '!GenericTBA_%d.isFinished' % G['GATE_PAD'])
        m.set(G['SAND_PAD'], 24, '!GenericTBA_%d.isFinished' % G['SAND_PAD'])
        m.set(G['LAUNCH'], 9, '0')
        for tid in ([G['BAY_CUT']] if 'BAY_CUT' in G else []) + [G['CHIP']]:
            s_ = str(m.arg(tid, 24)).replace('GenericTBA_%d.isFinished' % cage, '1')
            m.set(tid, 24, s_)
        if 'BAY_CUT' not in G:
            m.set(G['CHIP'], 24, '!GenericTBA_%d.isFinished' % G['CHIP'])
        print('ssbay: bayopen test variant')
    if 'bayaudit' in DBG:
        audit(G)
    if 'baycam' in DBG:                                    # a real use seen from the side: a cutscene camera starts with it
        import cutscene as CS
        F = G['SB'].F
        for tid, st, ang in ((G['BAY_CUT'], S1, 1.0), (G['CHIP'], S2, -1.0))[1 if 'baycam2' in DBG else 0:]:
            near = ((st[0] + 0.55) * 4096, (st[1] - 0.1) * 4096, (F + 1.1) * 4096)
            c = ((st[0] + 0.5) * 4096, (st[1] + ang * 2.0) * 4096, (F + 1.4) * 4096)
            CS.add_outro(m, G['nid'], 4087, [CS.key(c, near, 7.0, True, fov=0.75), CS.key(c, near, 0.0, False, fov=0.75)], [], 'GenericTBA_%d.isInUse' % tid)


def audit(G):
    import atmos, cutscene as CS
    from mission_lib import lit
    m, K, nid, LOGIC = G['m'], G['K'], G['nid'], G['LOGIC']
    tris = K._tris()[0]
    keys, n = [], 0
    for i_ in sorted(m.byid):
        t_ = m.byid[i_]
        try:
            if str(lit(t_.args[1])) != 'GenericTBA':
                continue
            anim = str(lit(t_.args[25]))
            if not anim or 'map marker' in str(lit(t_.args[2])):
                continue
            p = [float(lit(t_.args[3 + k_])) for k_ in range(3)]
            g = float(lit(t_.args[8]))
        except Exception as e_:
            print('ssbay: audit skips', i_, e_); continue
        fx, fy = -math.sin(g), math.cos(g)                 # the use point's +y
        st = (p[0] + fx * STAND * 4096, p[1] + fy * STAND * 4096)
        up_, dn_ = atmos._vertical_hits(tris, (st[0], st[1], p[2] + 512))
        floor = dn_[0] if dn_ else p[2] - 1.0 * 4096
        pos = (st[0], st[1], floor)
        box = nid()
        m.add_child(LOGIC, G['T'](box, 'ConditionalContainer', 'SS double %d' % i_, 'LevelFlow_10.nTick > %d * GAME_FREQUENCY && LevelFlow_10.nTick < %d * GAME_FREQUENCY' % (3 + n * 6, 11 + n * 6), '', ''))
        K.actor(box, pos, (p[0], p[1]), 'jones2_1', anim='%s, %s' % (anim, anim), name='double of %d' % i_)
        rx, ry = fy, -fx                                   # his right
        near = (st[0] + (p[0] - st[0]) * 0.65, st[1] + (p[1] - st[1]) * 0.65, floor + 1.1 * 4096)
        for side, name in ((1.0, 'right'), (-1.0, 'left')):
            c = (near[0] + rx * side * 1.9 * 4096, near[1] + ry * side * 1.9 * 4096, floor + 1.35 * 4096)
            keys += [CS.key(c, near, 3.0, True, fov=0.75), CS.key(c, near, 0.0, False, fov=0.75)]
        print('ssbay: audit %d %s %s stand (%.2f, %.2f) floor %.2f, point %.2f over it, shots from %.0f s' % (i_, str(lit(t_.args[2])), anim, st[0] / 4096, st[1] / 4096, floor / 4096, (p[2] - floor) / 4096, 4 + n * 6))
        n += 1
    CS.add_outro(m, nid, 4087, keys, [], 'LevelFlow_10.nTick > 4 * GAME_FREQUENCY')


# ---------------------------------------------------------------- the two scientists at the missile (orchestrator 11-08, from ss-hands runs hands_ai0, hands_ai)
# They carried Makarovs and shot a walking Jones at 1.2 m during the 6.4 s box use. Scientists are not fighters: no weapon; on sight, a shot, a body or the
# alert they run for the hall alarm button on the Bulwark's east face; one who reaches it alive puts the base below on alert (U_ALARM, the bay's own alert).
# Shot first, nobody calls. They stay killable (owner 36). Their desks and clips (ss-hands' p109) stay as they are.
SCI_RUN = (232.4, 247.0)                                   # in front of the hall alarm button at (231.46, 247.0), graph 6
FLEE = ('ENEMYDETECTION', 'ENEMYDETECTION_NO_LOF', 'TAKINGDAMAGE', 'GUNSHOT', 'GUNSHOTMISS', 'VISUAL_GUNSHOT', 'BULLETIMPACT', 'FRIENDLY_DYING', 'FRIENDLY_DAMAGE_SEEN',
        'FRIENDLY_GUNSHOT', 'EXPLOSION', 'GRENADELAND', 'GRENADETHROWN', 'GRENADESHOUT', 'ALARMON', 'DISTRESSCALL', 'DEATH_CRY', 'WOUNDED_CRY', 'BACKUP_REQUEST',
        'ALERT', 'ALERT_RESPONSE', 'LOSTSIGHTOFENEMY', 'SQUADCOMBATIDLE', 'HANDLEWEAPON', 'REACTTOSUSPICION', 'SEENSOMETHING')


def scientists(G):
    import alarmai
    from igiqvm import Call, Ident
    from mission_lib import lit
    m, T, nid, LOGIC = G['m'], G['T'], G['nid'], G['LOGIC']
    if 'U scientists' not in G['SQUAD_IDS']:
        return
    sid, hids = G['SQUAD_IDS']['U scientists']
    hids = [h for h in hids if h in m.byid]                # (noenemies builds drop the men, SQUAD_IDS keeps them)
    if not hids:
        return
    nodes = G['GRAPHS'][6]
    tgt = min(nodes, key=lambda q: math.hypot(q['pos'][0] / 4096.0 - SCI_RUN[0], q['pos'][1] / 4096.0 - SCI_RUN[1]) + 3 * abs(q['pos'][2] / 4096.0 - G['SB'].F))
    node = int(tgt['id'])
    ev = alarmai.C('AIFunction_GetCurrentEventType')
    run = [alarmai.C('AIAction_RunToNode', node, 1)]
    calm_var = G['_UA']
    pri = [Call('AIFunction_SetEventPriority', [Ident('AIEVENT_' + e)]) for e in ('DEAD', 'DELETE') + FLEE]
    flee_if = alarmai.OR(*[alarmai.EQ(ev, 'AIEVENT_' + e) for e in FLEE])
    area = nid()
    tx, ty, tz = tgt['pos']
    m.add_child(LOGIC, T(area, 'AreaActivate', 'SS scientists reach the alarm', float(tx), float(ty), float(G['SB'].F * 4096.0 + 4096.0), 0.0, 0.0, 0.0,
                         4.0 * 4096.0, 4.0 * 4096.0, 3.0 * 4096.0, 'CRITERIA_HUMAN'))
    for h in hids:
        _w = os.environ.get('SS_SCIWEAPON', 'KNIFE')         # (judge A02: with no weapon at all the engine never plays a stand clip, the man froze in an empty rifle hold; a knife lets the work clips run, rig si)
        m.set(h, 9, ('Human_AddWeapon("WEAPON_ID_%s");' % _w) if _w else ';')   # (no weapon; ';' not '': '' = AV storm, ssboom)
        aid = next(c.args[0] for c in m.byid[h].args if hasattr(c, 'args') and str(c.args[1]).strip('"') == 'HumanAI')
        k = str(lit(aid))
        old = m.ai_files.get(k)
        clip = 'scientist_standing_studying'
        try:
            ver, body = alarmai.decompile_ai(bytes(old))
            txt = alarmai.to_text(body)
            import re
            mm = re.search(r'SetStandActionAnimation\("([^"]+)"\)', txt)
            if mm:
                clip = mm.group(1)
        except Exception:
            ver = (8, 7)
        calm = [Call('AIFunction_SetStandActionAnimation', [__import__('igiqvm').Str(clip)]), alarmai.C('AIAction_PlayAnimation', 1, 0)]
        # (judge A02: at the button, or shut in by the cage gate, RunToNode had nowhere to go and he stood frozen for a minute: there he plays the originals'
        #  nervous 'scientist_confused_studying' instead, on every idle)
        cower = [Call('AIFunction_SetStandActionAnimation', [__import__('igiqvm').Str('scientist_confused_studying')]), alarmai.C('AIAction_PlayAnimation', 1, 0)]
        # (S17 11-15, ss-life request: the cage gate is a CLOSED door for the AI graph now, so after the console RunToNode(<alarm button>) has no path
        #  out of the cage either: they cower inside it; the alarm comes from the witness clock / the hall men. Was: If(at the button || gate shut, cower, run))
        flee = cower
        sc = alarmai.compile_ai([alarmai.If(alarmai.EQ(ev, 'AIEVENT_CREATE'), pri + [alarmai.C('AIFunction_DefaultHandler')],
                                            [alarmai.If(flee_if, flee,
                                                        [alarmai.If(alarmai.EQ(ev, 'AIEVENT_IDLE'),
                                                                    [alarmai.If(alarmai.EQ(calm_var, 1), flee, calm)],
                                                                    [alarmai.C('AIFunction_DefaultHandler')])])])], ver)
        m.ai_files[k] = sc
    reach = ' || '.join('(AreaActivate_IdInArea(%d, %d) && !HumanSoldier_%d.isDead)' % (area, h, h) for h in hids)
    U = G['U_ALARM']
    old = str(lit(m.byid[U].args[7]))
    lat = nid()                                            # (rc7c: appended whole, the reach clause took U's rule past the engine's 1023 chars; its own latch, one short term in U)
    hold = nid()                                           # (rig sj, sk: an instant alarm brought the hall men during the 11 s at the missile; he must stand 4 s at the button, time to drop him)
    m.add_child(LOGIC, T(hold, 'EditVariable', 'SS a scientist at the button', 0.0, 0.0, 0.0, 0, '(%s) && EditVariable_%d.nValue < 100000' % (reach, hold), ''))
    m.add_child(LOGIC, T(lat, 'EditVariable', 'SS a scientist raised the alarm', 0.0, 0.0, 0.0, 0, 'EditVariable_%d.nValue == 0 && EditVariable_%d.nValue > 4 * GAME_FREQUENCY' % (lat, hold), ''))
    m.set(U, 7, '(%s) || (EditVariable_%d.nValue == 0 && EditVariable_%d.nValue == 1)' % (old, U, lat))
    assert len(str(lit(m.byid[U].args[7]))) <= 1023, ('U_ALARM rule too long', len(str(lit(m.byid[U].args[7]))))
    G['msg']('SS_SCIALARM', 'SS a scientist reached the alarm', 'EditVariable_%d.nValue > 0' % hold, 'SCIENTIST: Intruder at the missile! Help!', 4.0)
    print('ssbay: scientists %s unarmed, run to graph 6 node %d at (%.1f, %.1f) on sight; reaching it = base alert' % (hids, node, tx / 4096.0, ty / 4096.0))
    if 'scicam' in G['DBG']:                               # (test: a camera on the alarm button when a scientist gets there, the proof he fled and called it)
        import cutscene as CS
        F = G['SB'].F
        c, l = (239.0 * 4096, 249.5 * 4096, (F + 2.6) * 4096), (tx, ty, (F + 1.0) * 4096)
        CS.add_outro(m, nid, 4087, [CS.key(c, l, 8.0, True, fov=0.8), CS.key(c, l, 0.0, False, fov=0.8)], [], 'EditVariable_%d.nValue == 1' % lat)


def apply(G):
    if BAY:
        fix_pads(G)
        fix_generators(G)
        clear_chairs(G)
        steal(G)
        if os.environ.get('SS_SCIFLEE', '1') == '1':
            scientists(G)
    debug(G)
