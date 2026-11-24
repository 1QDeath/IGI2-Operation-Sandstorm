"""graphcover - the AI graphs' COVER data (graphs/graphcover<N>.dat) the engine's combat AI uses (shared, additive; Sandstorm 11-01).

Why (owner 11-01: 'original enemies crouch, peek, dodge and move to cover; ours stand and shoot'): the engine loads per-graph cover
items from MISSION:graphs/graphcover<task id>.dat (AIGraph_LoadNodeCoverData, after the graph). The original levels ship them
(location2/LEVEL4: graphcover1..3.dat); the editor wrote them when 'Update & Display CoverInfo' was ticked. Our navgen graphs had
none, so a soldier had no node to take cover at - he stands and shoots. The game never computes it itself.

What a cover item is (igi2-decomp aigraph.c AIGraph_DecideCoverItemForNode; OpenIGI Igi2AiGraph.Runtime.UpdateCover):
from each node, at 0.3 / 0.5 / 1.2 / 1.9 m over it, a 2 m line in each of 32 directions (the first due east (+x), turning left);
a line that meets an object (rigid objects, splines, forest - not the ground, not a human) sets bit <height> of that direction's
word. The node is cover when more than 2 directions are blocked low (bits 0-2) but open at 1.9 m (bit 3 clear).
File: ILFF form 'AICC': 'AICH' {count, version 1}, then one 'AICN' per item: 12 bytes (list pointers, ignored), 32 int32 words,
int32 node id (the graph's 1-based node id).

    import graphcover
    data, n = graphcover.build(tris, [(node_id, (x, y, z)), ...])     # tris: (N, 3, 3) world collision triangles (navgen.triangles())
    open(out + '/graphs/graphcover%d.dat' % gid, 'wb').write(data)
"""
import math
import struct
import numpy as np
import ilff

M = 4096.0
HEIGHTS = (0.3 * M, 0.5 * M, 1.2 * M, 1.9 * M)
REACH = 8192.0
DIRS = 32


def _rays():
    a = np.array([k * float(np.float32(6.2831855)) * 0.03125 for k in range(DIRS)])
    return np.stack([np.cos(a), np.sin(a), np.zeros(DIRS)], axis=1) * REACH


def node_words(tris, lo, hi, pos, dirs=None):
    """the 32 direction words of one node (tris = the candidate triangles near it)"""
    dirs = _rays() if dirs is None else dirs
    words = [0] * DIRS
    if not len(tris):
        return words
    v0 = tris[:, 0]; e1 = tris[:, 1] - v0; e2 = tris[:, 2] - v0
    for h, dz in enumerate(HEIGHTS):
        o = np.array([pos[0], pos[1], pos[2] + dz])
        near = (lo[:, 2] <= o[2]) & (hi[:, 2] >= o[2])
        if not near.any():
            continue
        V0, E1, E2 = v0[near], e1[near], e2[near]
        for k, d in enumerate(dirs):
            pv = np.cross(d, E2); det = np.einsum('ij,ij->i', E1, pv)
            ok = np.abs(det) > 1e-9
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            tv = o - V0
            u = np.einsum('ij,ij->i', tv, pv) * inv
            qv = np.cross(tv, E1)
            w = (qv @ d) * inv
            t = np.einsum('ij,ij->i', E2, qv) * inv
            if (ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (t > 0) & (t <= 1.0)).any():
                words[k] |= 1 << h
    return words


def items(tris, nodes):
    """-> [(node id, words)] of the nodes that are cover (the engine's rule)"""
    tris = np.asarray(tris, float)
    lo, hi = tris.min(axis=1), tris.max(axis=1)
    dirs = _rays()
    out = []
    for nid, pos in nodes:
        sel = (hi[:, 0] >= pos[0] - REACH) & (lo[:, 0] <= pos[0] + REACH) & (hi[:, 1] >= pos[1] - REACH) & \
              (lo[:, 1] <= pos[1] + REACH) & (hi[:, 2] >= pos[2] + HEIGHTS[0]) & (lo[:, 2] <= pos[2] + HEIGHTS[-1])
        if not sel.any():
            continue
        words = node_words(tris[sel], lo[sel], hi[sel], pos, dirs)
        if sum(1 for b in words if (b & 7) and not (b & 8)) > 2:
            out.append((int(nid), words))
    return out


def encode(cover):
    chunks = [(b'AICH', struct.pack('<2i', len(cover), 1), 4)]
    for nid, words in cover:
        chunks.append((b'AICN', b'\0' * 12 + struct.pack('<32i', *words) + struct.pack('<i', nid), 4))
    return ilff.write(b'AICC', chunks)


def decode(data):
    form, chunks, _ = ilff.read(data)
    assert form == b'AICC', form
    n, ver = struct.unpack_from('<2i', chunks[0][1])
    out = [(struct.unpack_from('<i', b, 140)[0], list(struct.unpack_from('<32i', b, 12))) for tag, b, _ in chunks[1:] if tag == b'AICN']
    assert len(out) == n and ver == 1, (n, len(out), ver)
    return out


def build(tris, nodes):
    cover = items(tris, nodes)
    return encode(cover), len(cover)


def selftest():
    """round-trip the shipped L24 cover files through decode/encode (same items, same words)"""
    import glob
    for f in glob.glob(r'C:/Users/1qdeath/Games/IGI2/app/MISSIONS/location2/LEVEL4/graphs/graphcover*.dat'):
        d = open(f, 'rb').read()
        a = decode(d)
        b = decode(encode(a))
        assert a == b, f
        print('graphcover selftest %s: %d items, round trip OK' % (f.rsplit('/', 1)[-1], len(a)))


if __name__ == '__main__':
    selftest()
