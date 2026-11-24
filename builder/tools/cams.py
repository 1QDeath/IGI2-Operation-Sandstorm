"""cams - security camera kinds (owner 10-12: 'make the cameras soft so you can destroy them; in missions 1, 2, 3 most
cameras soft, some of them metal that cannot be destroyed').

The originals mix two SCamera kinds (survey of every original objects.qvm, 10-12):
  SOFT   holder 335_01_1, camera 335_02_1, destroyed 335_03_1, 'Max damage factor' 0.5 (0.1/0.2 rarely)  - 63 cameras
  METAL  holder 313_07_1, camera 313_06_1, destroyed 313_06_1 (= no visible damage), factor 50       - 30 cameras
The multiplayer maps (our missions' bases) only have METAL ones. 335_0x_1 ship in multiplayer/common/models.
SCamera args: 7 holder model, 11 camera model, 12 destroyed model, 21 max damage factor.
"""
from qast import lit

SOFT = ('335_01_1', '335_02_1', '335_03_1', 0.5)
METAL = ('313_07_1', '313_06_1', '313_06_1', 50.0)


def kind(m, cid):
    return 'soft' if str(lit(m.byid[cid].args[11])) == SOFT[1] else 'metal'


def set_kind(m, cid, k):
    holder, cam, dead, dmg = SOFT if k == 'soft' else METAL
    m.set(cid, 7, holder); m.set(cid, 11, cam); m.set(cid, 12, dead); m.set(cid, 21, float(dmg))


def soften(m, cam_ids, metal=None, metal_every=4):
    """most cameras soft, every metal_every-th one (or the ids in `metal`) stays metal -> {id: kind}"""
    out = {}
    for k_, c in enumerate(sorted(cam_ids)):
        hard = (c in metal) if metal is not None else (k_ % metal_every == metal_every - 1)
        set_kind(m, c, 'metal' if hard else 'soft')
        out[c] = 'metal' if hard else 'soft'
    return out
