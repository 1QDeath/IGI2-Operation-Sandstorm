"""ssblood - a blood pool for a man shot in a cutscene (orchestrator, rc7p: "there is no blood" where Hadi is shot on the intro's camera 4).

The engine draws its own pool (bloodpool.tex, GOIsBlood) only under a dead HumanSoldier; a cutscene actor (EditBoneObj) gets none, and no task
type places a decal (ss-boom, work/sandstorm/boom/README.md). A cutscene's fall is scripted, so the spot is known: this is one flat model
on the floor, shown by a ConditionalContainer on the cutscene clock.

Model row: ss_blood_1 takes the row ss_g_mouse_1 had (ssgeneral folds its mouse into its chair model), so the LOD table count stays the same.

Use (the owner of the cutscene):
    import ssblood
    ssblood.models(G['_VLIB'])                       # once, where the mission's own models are added (ssgeneral.models does it)
    ssblood.place(m, parent_id, nid, cond, x, y, z, yaw)   # world metres; the pool's long axis along yaw; cond = the cutscene clock condition
"""
import math
import numpy as np
import biprefabs as BP, modelkit as MK
from mission_lib import T

M = 4096.0
MODEL = 'ss_blood_1'
W, H = 0.72, 0.52          # m: one blob; place_growing() lays five of them, turned and offset, into a pool ~1.1 x 0.9 m that spreads
LIFT = 0.012               # over the floor (owner 120: 12 mm proud, no flicker)


def _tex(n=256, seed=11):
    """RGBA: a dark, wet pool with a ragged edge and a few drops round it; alpha 0 outside"""
    rng = np.random.default_rng(seed)
    v, u = np.mgrid[-1:1:n * 1j, -1:1:n * 1j]
    a = np.arctan2(v, u)
    r = np.hypot(u, v)
    edge = 0.62 + 0.10 * np.sin(3 * a + 0.7) + 0.06 * np.sin(5 * a + 2.1) + 0.04 * np.sin(9 * a + 0.3)
    edge += 0.05 * BP._noise(n, rng, 4) - 0.025
    lobe = np.hypot((u - 0.42) / 0.30, (v + 0.30) / 0.22) < 1.0     # (a run where the floor dips)
    inside = (r < edge) | lobe
    drops = np.zeros_like(r, bool)
    for _ in range(14):
        cx, cy = rng.uniform(-0.9, 0.9, 2)
        if math.hypot(cx, cy) < 0.7:
            continue
        drops |= np.hypot(u - cx, v - cy) < rng.uniform(0.015, 0.045)
    shade = 0.85 + 0.15 * BP._noise(n, rng, 6)
    depth = np.clip(1.0 - r / np.maximum(edge, 0.05), 0, 1)
    # bright, fresh red: the CCTV tint multiplies red by 0.69 (atmos 'surveillance') and the room is dim; at 0.3 it read as a dark stain (rc7p k8r)
    red = (0.88 - 0.22 * depth) * shade
    img = np.dstack([red, 0.035 + 0.02 * depth, 0.03 + 0.015 * depth, np.where(inside | drops, 0.95, 0.0)])
    wet = np.exp(-(((u + 0.18) * 3.2) ** 2 + ((v + 0.22) * 6.0) ** 2))   # (a wet highlight)
    img[..., 0] = np.minimum(1.0, img[..., 0] + 0.10 * wet)
    img[..., 1] += 0.22 * wet * inside; img[..., 2] += 0.20 * wet * inside
    return np.clip(img, 0, 1)


def build_pool():
    s = MK.panel((0.0, 0.0, LIFT), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), W, H)
    return MK.model([(0, [s])], [BP.box_m(-0.02, -0.02, 0.0, 0.02, 0.02, 0.005)], alpha_slots=(0,))


def models(lib):
    if MODEL in getattr(lib, 'builders', {}):
        return
    lib.texture('sb_pool', _tex, alpha=True)
    lib.add(MODEL, build_pool, ['sb_pool'], lod_like='740_01_1')


def place(m, parent, nid, cond, x, y, z, yaw, name='SS blood pool'):
    """a ConditionalContainer on `cond` under `parent` holding the pool at world (x, y) metres, floor z; -> container id"""
    c_ = nid()
    m.add_child(parent, T(c_, 'ConditionalContainer', name, cond, '', '', children=[
        T(nid(), 'EditRigidObj', '', x * M, y * M, z * M, 0.0, 0.0, yaw, MODEL, 5, False, False)]))
    return c_


GROW = [(0.0, 0.00, 0.00, 0.0), (0.35, 0.20, 0.07, 0.9), (0.75, -0.12, 0.22, 2.1), (1.2, 0.32, -0.15, 3.6), (1.8, 0.06, -0.30, 5.0)]   # (s after the first, along yaw m, across m, turn)


def place_growing(m, parent, nid, cond_at, x, y, z, yaw, name='SS blood pool'):
    """the pool spreads: five blobs of the one model, each a little higher (no z-fight), turned and offset, shown one after another.
    cond_at(dt) -> the clock condition dt seconds after the first blob (e.g. lambda dt: 'CutScene_9.nTick > %d' % tick(bang + 1.9 + dt)).
    Centre (x, y) = under his head; yaw = the direction he fell. -> container ids"""
    out = []
    ca, sa = -math.sin(yaw), math.cos(yaw)                          # (yaw's forward, engine gamma: atan2(-dx, dy))
    for k_, (dt, al, ac, turn) in enumerate(GROW):
        px, py = x + al * ca + ac * sa, y + al * sa - ac * ca
        c_ = nid()
        m.add_child(parent, T(c_, 'ConditionalContainer', '%s %d' % (name, k_), cond_at(dt), '', '', children=[
            T(nid(), 'EditRigidObj', '', px * M, py * M, (z + 0.002 * k_) * M, 0.0, 0.0, yaw + turn, MODEL, 5, False, False)]))
        out.append(c_)
    return out
