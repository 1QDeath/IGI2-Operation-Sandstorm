"""IGI 2 model (.mef) collision meshes.

A .mef is an ILFF 'OCEM' file. HSMC = collision header (two meshes):
  [faces0, verts0, mats0, spheres0, 0,0,0,0, faces1, verts1, mats1, spheres1, ...]
followed by, per mesh: XTVC (vertices, 20 bytes: x, y, z float32 + 8 bytes),
ECFC (faces, 12 bytes: a, b, c uint16 + 3 x uint16 material/flags), TAMC (materials), HPSC (sphere tree).
"""
import struct
import numpy as np
import ilff


def collision(mef_bytes, drop_portals=True):
    """-> list of (verts Nx3 float, faces Mx3 int, face flags Mx3) for each collision mesh in the model.

    TAMC entries are 4 x uint32; word 1 = (sub-material << 16) | 0xFFFF for real surfaces, while
    0xFFFF0000 | k marks the sheet that closes doorway k (a portal) - those are NOT walls for characters
    once the door is open, so they are dropped by default."""
    _, ch, _ = ilff.read(mef_bytes)
    meshes, verts, faces = [], None, None
    for tag, data, al in ch:
        if tag == b'XTVC':
            verts = np.frombuffer(data, dtype='<f4').reshape(-1, 5)[:, :3].astype(float)
        elif tag == b'ECFC' and verts is not None:
            faces = np.frombuffer(data, dtype='<u2').reshape(-1, 6)
        elif tag == b'TAMC' and faces is not None:
            mats = np.frombuffer(data, dtype='<u4').reshape(-1, 4) if len(data) else np.zeros((0, 4), np.uint32)
            portal = np.array([(e[1] >> 16) == 0xFFFF and (e[1] & 0xFFFF) != 0xFFFF for e in mats], bool)
            keep = np.ones(len(faces), bool)
            if drop_portals and len(mats):
                mi = faces[:, 3].astype(int)
                keep = ~portal[np.clip(mi, 0, len(mats) - 1)]
            meshes.append((verts, faces[keep, :3].astype(int), faces[keep, 3:].copy()))
            verts, faces = None, None
    return meshes


class ModelLib:
    """lazy model lookup across several .res files (first hit wins: level, location common, global common)"""
    def __init__(self, res_paths):
        self.index = {}
        for p in res_paths:
            try:
                _, ch, _ = ilff.read(p)
            except Exception:
                continue
            for n, t, b in ilff.entries(ch):
                if n and n.lower().endswith('.mef'):
                    k = n.split('/')[-1][:-4].lower()
                    self.index.setdefault(k, b)
        self.cache = {}

    def collision(self, name):
        name = name.lower()
        if name not in self.cache:
            self.cache[name] = collision(self.index[name]) if name in self.index else None
        return self.cache[name]

    def attached(self, name):
        name = name.lower()
        k = ('atta', name)
        if k not in self.cache:
            self.cache[k] = attachments(self.index[name]) if name in self.index else []
        return self.cache[k]

    def collision_tree(self, name, mode='union'):
        return _collision_tree(self, name.lower(), mode)


def attachments(mef_bytes):
    """ATTA chunk: 72-byte entries = name[16], position[3] float32, 3x3 matrix[9] float32, 2 x int32"""
    _, ch, _ = ilff.read(mef_bytes)
    out = []
    for tag, data, al in ch:
        if tag == b'ATTA':
            for k in range(len(data) // 72):
                e = data[k * 72:(k + 1) * 72]
                vals = struct.unpack('<12f2i', e[16:72])
                out.append((e[:16].split(b'\0')[0].decode('latin1').lower(), np.array(vals[:3]), np.array(vals[3:12]).reshape(3, 3)))
    return out


ATTA_TRANSPOSE = True          # best fit to the multiplayer spawn points (Sandstorm 241/244, Chinese Temple 230/233)


def _collision_tree(lib, name, mode, depth=0):
    """collision meshes of a model plus all attached sub-models (interiors, stairs, lamps...) in the model's frame"""
    if depth > 4 or name not in lib.index:
        return []
    meshes = lib.collision(name) or []
    use = {'0': meshes[:1], '1': meshes[1:2] or meshes[:1], 'union': meshes}[mode]
    out = [(v, f) for v, f, fl in use if len(f)]
    for sub, pos, mat in lib.attached(name):
        R = mat.T if ATTA_TRANSPOSE else mat
        for v, f in _collision_tree(lib, sub, mode, depth + 1):
            out.append((v @ R.T + pos, f))
    return out
