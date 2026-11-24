"""mefmesh - full reader/writer for IGI 2 model files (.mef = ILFF form 'OCEM'), render mesh included.

tools/mef.py only decodes the collision part; this module decodes EVERY chunk of every shipped .mef into typed numpy
records and writes them back byte-identically (selftest: `python -P mefmesh.py --selftest`), and it can BUILD a new
vertex-lit rigid model (type 0) from arrays, recomputing every count / size / bounding sphere / collision sphere tree.
The format is documented in work/wreck/FORMAT.md.

    import mefmesh
    m = mefmesh.Mef.read(mef_bytes)              # m.chunks = [Chunk(tag, rec, ...)] in file order
    m.type                                       # 0 vertex-lit rigid, 1 skinned (bones), 3 lightmapped rigid
    r = mefmesh.RigidModel.from_mef(m)           # semantic view: groups (vertices, triangles, texture slot), collision
    data = r.to_mef().write()                    # rebuild (counts, spheres, sphere trees recomputed as needed)
    mefmesh.export_obj(m, 'x.obj')

Chunk tags are stored reversed in the file (HSEM = MESH, XTRV = VRTX, ECAF = FACE, DNER = REND, ...).
Units: 1 m = 4096 (the engine's world unit), z up, +y = model front for vehicles.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import ilff

# ----------------------------------------------------------------------------------------------- record layouts
HSEM_DT = np.dtype([
    ('version', '<f4'),            # 0.16
    ('stamp', '<u4', 7),           # export time: year, month, day, hour, minute, second, ms (lightmaps are keyed to it)
    ('type', '<u4'),               # 0 vertex-lit rigid (32-byte vertices), 1 skinned, 3 lightmapped rigid (28-byte)
    ('pad0', '<u4', 3),
    ('sph_render', '<f4', 4),      # bounding sphere (cx, cy, cz, r) of the render vertices (r = max distance, tight)
    ('sph_coll', '<f4', 4),        # bounding sphere of ALL collision vertices (no collision: = sph_render in 3,199 / 4,173)
    ('sph_coll2', '<f4', 4),       # always == sph_coll in the shipped files
    ('n_rfaces', '<u4'),           # render triangles (= D3DR nf)
    ('n_rverts', '<u4'),           # render vertices (= D3DR nv)
    ('render_bytes', '<u4'),       # len(D3DR)+len(ECAF)+len(DNER)+len(XTRV)+len(PMTL)  (skinned: XTRV counted nv*40)
    ('n_cfaces', '<u4'),           # collision faces, both meshes
    ('n_cverts', '<u4'),           # collision vertices, both meshes
    ('coll_bytes', '<u4'),         # len(HSMC)+len(all XTVC, ECFC, TAMC, HPSC)
    ('radius', '<f4'),             # max |v| from the model ORIGIN (>= every render and collision vertex in all shipped files)
    ('n_magic', '<u2'), ('n_atta', '<u2'), ('n_pverts', '<u2'), ('n_pfaces', '<u2'),
    ('n_portals', '<u2'), ('n_bones', '<u2'), ('n_glows', '<u2'), ('pad1', '<u2'),
    ('tail', '<u4', 9)])           # zeros (70 files: 0xABABABAB = uninitialised exporter memory)
assert HSEM_DT.itemsize == 176

ATTA_DT = np.dtype([('name', 'S16'), ('pos', '<f4', 3), ('rot', '<f4', (3, 3)), ('i0', '<i4'), ('i1', '<i4')])
XTVM_DT = np.dtype([('pos', '<f4', 3), ('id', '<i4')])                       # "magic vertices" (named points)
TROP_DT = np.dtype([('v0', '<u4'), ('nv', '<u4'), ('f0', '<u4'), ('nf', '<u4'), ('id', '<u4')])   # portals
XVTP_DT = np.dtype([('pos', '<f4', 3)])                                      # portal vertices
CFTP_DT = np.dtype([('v', '<u4', 3)])                                        # portal triangles
WOLG_DT = np.dtype([('pos', '<f4', 3), ('size', '<f4'), ('k', '<f4'), ('a', '<f4'), ('b', '<f4'), ('pad', '<u4')])  # glows
PMTL_DT = np.dtype([('w', '<u2'), ('h', '<u2'), ('pad', '<u4')])           # one per lightmap (D3DR[1] of type 3)
ECAF_DT = np.dtype([('v', '<u2', 3)])                                        # render triangles (absolute vertex index)
DNER_DT = {                                                                  # render groups (one per texture-slot use)
    0: np.dtype([('flags', '<u4'), ('centre', '<f4', 3), ('i0', '<u2'), ('ntris', '<u2'), ('v0', '<u2'), ('nverts', '<u2'),
                 ('tex', '<u2'), ('tex_b', '<u2'), ('env_tex', '<u2'), ('env_level', '<u2')]),
    3: np.dtype([('flags', '<u4'), ('centre', '<f4', 3), ('i0', '<u2'), ('ntris', '<u2'), ('v0', '<u2'), ('nverts', '<u2'),
                 ('tex', '<u2'), ('lightmap', '<u2')]),
}
DNER_DT[1] = DNER_DT[0]
XTRV_DT = {
    0: np.dtype([('pos', '<f4', 3), ('nrm', '<f4', 3), ('uv', '<f4', 2)]),                         # vertex-lit
    3: np.dtype([('pos', '<f4', 3), ('uv', '<f4', 2), ('lmuv', '<f4', 2)]),                        # lightmapped
    1: np.dtype([('pos', '<f4', 3), ('nrm', '<f4', 3), ('uv', '<f4', 2), ('weight', '<f4'), ('vi', '<u2'), ('bone', '<u2')]),
}
HSMC_DT = np.dtype([('mesh', [('nfaces', '<u4'), ('nverts', '<u4'), ('nmats', '<u4'), ('nspheres', '<u4'), ('pad', '<u4', 4)], 2)])
XTVC_DT = np.dtype([('pos', '<f4', 3), ('lmuv', '<f4', 2)])                 # (lmuv = 0 in vertex-lit copies)
ECFC_DT = np.dtype([('v', '<u2', 3), ('mat', '<u2'), ('noise', '<u2'), ('pad', '<u2')])
TAMC_DT = np.dtype([('w0', '<u4'), ('id', '<u4'), ('w2', '<u4'), ('surface', '<u4')])
HPSC_DT = np.dtype([('centre', '<f4', 3), ('radius', '<f4'), ('face', '<u2'), ('leaf', '<u2'), ('child', '<u2'), ('sibling', '<u2')])
MANB_DT = np.dtype([('name', 'S16')])                                       # bone names
HPRM_REC = np.dtype([('vi', '<u4'), ('d', '<f4', 3)])                       # morph records (after 16 x u32 counts)
SEMS_DT = np.dtype([('w', '<u4', 7)])                                        # shadow-volume parts
XTVS_DT = np.dtype([('pos', '<f4', 3)])
CAFS_DT = np.dtype([('v', '<u4', 3), ('x', '<u4'), ('n', '<f4', 3)])
EGDE_DT = np.dtype([('v', '<u4', 2)])

SIMPLE = {'ATTA': ATTA_DT, 'XTVM': XTVM_DT, 'TROP': TROP_DT, 'XVTP': XVTP_DT, 'CFTP': CFTP_DT, 'WOLG': WOLG_DT,
          'PMTL': PMTL_DT, 'ECAF': ECAF_DT, 'HSMC': HSMC_DT, 'XTVC': XTVC_DT, 'ECFC': ECFC_DT, 'TAMC': TAMC_DT,
          'HPSC': HPSC_DT, 'MANB': MANB_DT, 'SEMS': SEMS_DT, 'XTVS': XTVS_DT, 'CAFS': CAFS_DT, 'EGDE': EGDE_DT,
          'HSEM': HSEM_DT}
RENDER_TAGS = ('D3DR', 'ECAF', 'DNER', 'XTRV', 'PMTL')
COLL_TAGS = ('HSMC', 'XTVC', 'ECFC', 'TAMC', 'HPSC')


def _rec(data, dt, tag):
    if len(data) % dt.itemsize:
        raise ValueError('%s: %d bytes is not a multiple of %d' % (tag, len(data), dt.itemsize))
    return np.frombuffer(data, dt).copy()


class Chunk:
    """one ILFF chunk. rec = numpy record array (or dict for the compound chunks); align = ILFF align field."""
    __slots__ = ('tag', 'rec', 'align')

    def __init__(self, tag, rec, align=4):
        self.tag, self.rec, self.align = tag, rec, align

    def __repr__(self):
        n = len(self.rec) if hasattr(self.rec, '__len__') else '?'
        return 'Chunk(%s, %s)' % (self.tag, n)


class Mef:
    def __init__(self, chunks, form=b'OCEM', align=4):
        self.chunks, self.form, self.align = chunks, form, align

    # ------------------------------------------------------------------ access
    def get(self, tag, k=0):
        n = 0
        for c in self.chunks:
            if c.tag == tag:
                if n == k:
                    return c.rec
                n += 1
        return None

    def all(self, tag):
        return [c.rec for c in self.chunks if c.tag == tag]

    @property
    def hsem(self):
        h = self.get('HSEM')
        return None if h is None else h[0]

    @property
    def type(self):
        h = self.hsem
        return None if h is None else int(h['type'])

    # ------------------------------------------------------------------ decode
    @classmethod
    def read(cls, data):
        if isinstance(data, str):
            data = open(data, 'rb').read()
        form, ch, hdr = ilff.read(data)
        typ = None
        d3 = None
        nbones = 0
        out = []
        for tag_b, d, al in ch:
            tag = tag_b.decode('latin1')
            if tag == 'HSEM':
                rec = _rec(d, HSEM_DT, tag)
                typ = int(rec[0]['type']); nbones = int(rec[0]['n_bones'])
            elif tag == 'D3DR':
                rec = np.frombuffer(d, '<u4').copy()
                d3 = rec
            elif tag == 'DNER':
                rec = _rec(d, DNER_DT[typ], tag)
            elif tag == 'XTRV':
                rec = _rec(d, XTRV_DT[typ], tag)
            elif tag == 'REIH':                        # hierarchy: u8 children-count per bone, pad to 4, then 3 f32 per bone
                p = (nbones + 3) & ~3
                if len(d) != p + 12 * nbones:
                    raise ValueError('REIH size %d for %d bones' % (len(d), nbones))
                rec = dict(nchild=np.frombuffer(d[:nbones], 'u1').copy(), pad=d[nbones:p],
                           offset=np.frombuffer(d[p:], '<f4').reshape(-1, 3).copy())
            elif tag == 'HPRM':                        # morphs: 16 x u32 record counts, then (vertex, delta xyz) records
                cnt = np.frombuffer(d[:64], '<u4').copy()
                rec = dict(counts=cnt, recs=_rec(d[64:], HPRM_REC, tag))
                if len(rec['recs']) != int(cnt.sum()):
                    raise ValueError('HPRM count mismatch')
            elif tag == 'TXAN':                        # texture animation: u32 list (frame count, frame indices ...)
                rec = np.frombuffer(d, '<u4').copy()
            elif tag in SIMPLE:
                rec = _rec(d, SIMPLE[tag], tag)
            else:
                raise ValueError('unknown chunk %s' % tag)
            out.append(Chunk(tag, rec, al))
        m = cls(out, form, hdr[1] or 4)
        return m

    # ------------------------------------------------------------------ encode
    @staticmethod
    def encode(c):
        r = c.rec
        if c.tag == 'REIH':
            return r['nchild'].astype('u1').tobytes() + bytes(r['pad']) + r['offset'].astype('<f4').tobytes()
        if c.tag == 'HPRM':
            return r['counts'].astype('<u4').tobytes() + r['recs'].tobytes()
        if isinstance(r, np.ndarray):
            return r.tobytes()
        raise TypeError(c.tag)

    def write(self):
        return ilff.write(self.form, [(c.tag.encode('latin1'), self.encode(c), c.align) for c in self.chunks], self.align)


# ----------------------------------------------------------------------------------------------- geometry helpers
def bounding_sphere(P):
    """(cx, cy, cz, r): bbox centre, r = max distance from it (tight for that centre). The shipped spheres use
    another centre (bbox centre in only 232 / 7,258 render spheres) - ours is a valid, slightly looser bound."""
    P = np.asarray(P, float).reshape(-1, 3)
    if not len(P):
        return np.zeros(4, np.float32)
    c = (P.min(0) + P.max(0)) / 2
    c32 = c.astype(np.float32).astype(float)
    r = np.linalg.norm(P - c32, axis=1).max()
    r32 = np.float32(r)
    if float(r32) < r:                                  # never round the radius down
        r32 = np.nextafter(r32, np.float32(np.inf))
    return np.array([*c32, r32], np.float32)


def sphere_tree(V, F):
    """collision sphere tree in the shipped layout (HPSC): node 0 = root, nodes 1..n = leaves in face order
    (face = index, leaf = 1), internal nodes after them, every child index < its parent's (bottom-up creation order),
    children linked as first child (`child`) + next sibling (`sibling`), 0 = none. Every sphere bounds all vertices of
    the faces below it (bbox centre, tight radius). Built top-down by median split along the longest axis."""
    V = np.asarray(V, float); F = np.asarray(F, int)
    n = len(F)
    if n == 0:
        return np.zeros(0, HPSC_DT)
    nodes = np.zeros(2 * n - 1 if n > 1 else 1, HPSC_DT)
    cen = V[F].mean(1)
    for i in range(n):                                   # leaves
        nodes[i + 1 if n > 1 else 0] = (bounding_sphere(V[F[i]])[:3], bounding_sphere(V[F[i]])[3], i, 1, 0, 0)
    if n == 1:
        return nodes
    nxt = [n + 1]                                        # next free internal slot (root goes to 0 at the end)

    def build(ids, is_root=False):
        if len(ids) == 1:
            return ids[0] + 1
        c = cen[ids]
        ax = int(np.argmax(c.max(0) - c.min(0)))
        order = ids[np.argsort(c[:, ax], kind='stable')]
        h = len(order) // 2
        a = build(order[:h]); b = build(order[h:])
        if is_root:
            k = 0
        else:
            k = nxt[0]; nxt[0] += 1
        s = bounding_sphere(V[F[ids].reshape(-1)])
        nodes[k]['centre'] = s[:3]; nodes[k]['radius'] = s[3]
        nodes[k]['face'] = 0xFFFF; nodes[k]['leaf'] = 0
        nodes[k]['child'] = a
        nodes[a]['sibling'] = b
        nodes[b]['sibling'] = 0
        return k

    sys.setrecursionlimit(max(10000, 4 * n))
    build(np.arange(n), is_root=True)
    assert nxt[0] == len(nodes), (nxt[0], len(nodes))
    return nodes


def check_tree(nodes, V, F, tol=0.01):
    """-> list of problems (structure + every sphere bounds its subtree's vertices)"""
    probs = []
    if not len(nodes):
        return probs if not len(F) else ['no tree']
    V = np.asarray(V, float); F = np.asarray(F, int)
    seen = np.zeros(len(nodes), int)
    stack = [(0, None)]
    faces_below = {}
    order = []
    while stack:
        i, par = stack.pop()
        order.append(i)
        c = int(nodes[i]['child'])
        if nodes[i]['leaf']:
            continue
        kids = []
        while c:
            kids.append(c); seen[c] += 1; c = int(nodes[c]['sibling'])
        if len(kids) != 2:
            probs.append('node %d has %d children' % (i, len(kids)))
        for k in kids:
            stack.append((k, i))
    if (seen[1:] != 1).any():
        probs.append('%d nodes not referenced exactly once' % int((seen[1:] != 1).sum()))
    for i in reversed(order):                             # children before parents
        if nodes[i]['leaf']:
            faces_below[i] = [int(nodes[i]['face'])]
        else:
            fs = []
            c = int(nodes[i]['child'])
            while c:
                fs += faces_below.get(c, []); c = int(nodes[c]['sibling'])
            faces_below[i] = fs
        fs = faces_below[i]
        if fs:
            P = V[F[fs].reshape(-1)]
            d = np.linalg.norm(P - nodes[i]['centre'].astype(float), axis=1).max()
            if d > float(nodes[i]['radius']) + tol + 1e-5 * d:
                probs.append('node %d sphere too small by %.3f' % (i, d - float(nodes[i]['radius'])))
                if len(probs) > 10:
                    break
    if len(faces_below.get(0, [])) != len(F):
        probs.append('root covers %d of %d faces' % (len(faces_below.get(0, [])), len(F)))
    return probs


def smooth_normals(P, T, crease_deg=50.0):
    """per-corner normals (area weighted, split at creases) for triangles T over positions P -> (len(T), 3, 3)"""
    P = np.asarray(P, float); T = np.asarray(T, int)
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    area = np.linalg.norm(fn, axis=1, keepdims=True)
    fu = fn / np.maximum(area, 1e-12)
    key = np.round(P / 1.0).astype(np.int64)            # weld coincident positions (1 unit = 0.24 mm)
    _, wid = np.unique(key, axis=0, return_inverse=True)
    wid = wid.reshape(-1)
    acc = {}
    for t in range(len(T)):
        for k in range(3):
            acc.setdefault(int(wid[T[t, k]]), []).append(t)
    cosc = np.cos(np.radians(crease_deg))
    out = np.zeros((len(T), 3, 3))
    for t in range(len(T)):
        for k in range(3):
            fs = acc[int(wid[T[t, k]])]
            fs = [f for f in fs if fu[f] @ fu[t] >= cosc]
            s = fn[fs].sum(0)
            ln = np.linalg.norm(s)
            out[t, k] = s / ln if ln > 0 else fu[t]
    return out


# ----------------------------------------------------------------------------------------------- semantic model
class Group:
    """one render group = one texture slot use: own vertex block + triangles (local indices)"""
    def __init__(self, pos, uv, tris, tex, flags=0x1900, nrm=None, lmuv=None, tex_b=0xFFFF, env_tex=0xFFFF, env_level=0,
                 lightmap=0, centre=None, name=''):
        self.pos = np.asarray(pos, np.float32).reshape(-1, 3)
        self.uv = np.asarray(uv, np.float32).reshape(-1, 2)
        self.nrm = None if nrm is None else np.asarray(nrm, np.float32).reshape(-1, 3)
        self.lmuv = None if lmuv is None else np.asarray(lmuv, np.float32).reshape(-1, 2)
        self.tris = np.asarray(tris, np.int64).reshape(-1, 3)
        self.tex, self.flags, self.tex_b, self.env_tex, self.env_level = tex, flags, tex_b, env_tex, env_level
        self.lightmap, self.centre, self.name = lightmap, centre, name

    def __repr__(self):
        return 'Group(tex=%s, %d verts, %d tris, flags=%#x %s)' % (self.tex, len(self.pos), len(self.tris), self.flags, self.name)


class CollMesh:
    def __init__(self, pos, faces, mat, mats, lmuv=None, noise=None, tree=None, pad=None):
        self.pos = np.asarray(pos, np.float32).reshape(-1, 3)
        self.faces = np.asarray(faces, np.int64).reshape(-1, 3)
        self.mat = np.asarray(mat, np.int64).reshape(-1)
        self.mats = np.asarray(mats, TAMC_DT) if not isinstance(mats, np.ndarray) or mats.dtype != TAMC_DT else mats.copy()
        self.lmuv = np.zeros((len(self.pos), 2), np.float32) if lmuv is None else np.asarray(lmuv, np.float32).reshape(-1, 2)
        self.noise = np.full(len(self.faces), 0xFFFF, np.int64) if noise is None else np.asarray(noise, np.int64).reshape(-1)
        self.pad = np.zeros(len(self.faces), np.int64) if pad is None else np.asarray(pad, np.int64).reshape(-1)
        self.tree = tree                     # HPSC records or None (= rebuild)

    def __repr__(self):
        return 'CollMesh(%d verts, %d faces, %d mats)' % (len(self.pos), len(self.faces), len(self.mats))


class RigidModel:
    """type 0 (vertex-lit) or type 3 (lightmapped) rigid model. Everything not modelled (attachments, magic vertices,
    portals, glows, lightmap descriptors) is carried as the original records."""
    def __init__(self, groups, coll, hsem=None, atta=None, magic=None, portals=None, glows=None, pmtl=None, typ=0,
                 order=None, d3dr_tail=None, extra=None):
        self.groups, self.coll = groups, coll
        self.extra = extra or []             # chunks this class does not model (HPRM, TXAN), written after collision
        self.hsem = np.zeros(1, HSEM_DT)[0] if hsem is None else hsem.copy()
        if hsem is None:
            self.hsem['version'] = 0.16
        self.atta = np.zeros(0, ATTA_DT) if atta is None else atta
        self.magic = np.zeros(0, XTVM_DT) if magic is None else magic
        self.portals = portals if portals is not None else dict(TROP=np.zeros(0, TROP_DT), XVTP=np.zeros(0, XVTP_DT), CFTP=np.zeros(0, CFTP_DT))
        self.glows = glows
        self.pmtl = pmtl
        self.typ = typ
        self.order = order
        self.d3dr_tail = d3dr_tail

    # ---------------------------------------------------------------- from a Mef
    @classmethod
    def from_mef(cls, m):
        typ = m.type
        if typ not in (0, 3):
            raise ValueError('RigidModel handles types 0 and 3, not %s' % typ)
        X = m.get('XTRV'); I = m.get('ECAF')['v'].astype(np.int64); D = m.get('DNER')
        groups = []
        for g in D:
            v0, nv, i0, nt = int(g['v0']), int(g['nverts']), int(g['i0']), int(g['ntris'])
            blk = X[v0:v0 + nv]
            tris = I.reshape(-1)[i0:i0 + 3 * nt].reshape(-1, 3) - v0
            kw = dict(flags=int(g['flags']), centre=g['centre'].copy())
            if typ == 0:
                kw.update(nrm=blk['nrm'], tex_b=int(g['tex_b']), env_tex=int(g['env_tex']), env_level=int(g['env_level']))
            else:
                kw.update(lmuv=blk['lmuv'], lightmap=int(g['lightmap']))
            groups.append(Group(blk['pos'], blk['uv'], tris, int(g['tex']), **kw))
        coll = []
        cv, cf, cm, cs = m.all('XTVC'), m.all('ECFC'), m.all('TAMC'), m.all('HPSC')
        for k in range(len(cv)):
            coll.append(CollMesh(cv[k]['pos'], cf[k]['v'], cf[k]['mat'], cm[k], lmuv=cv[k]['lmuv'], noise=cf[k]['noise'],
                                 tree=cs[k], pad=cf[k]['pad']))
        glows = m.get('WOLG')
        d3 = m.get('D3DR')
        r = cls(groups, coll, hsem=m.hsem, atta=m.get('ATTA'), magic=m.get('XTVM'),
                portals=dict(TROP=m.get('TROP'), XVTP=m.get('XVTP'), CFTP=m.get('CFTP')), glows=glows,
                pmtl=m.get('PMTL'), typ=typ, order=[c.tag for c in m.chunks],
                d3dr_tail=(d3[4:] if typ == 0 else d3[5:]).copy(),
                extra=[c for c in m.chunks if c.tag in ('HPRM', 'TXAN', 'REIH', 'MANB')])
        if any(c.tag in ('REIH', 'MANB') for c in r.extra):
            raise ValueError('bones in a rigid model')
        return r

    # ---------------------------------------------------------------- to a Mef
    def all_render_pos(self):
        return np.concatenate([g.pos for g in self.groups]) if self.groups else np.zeros((0, 3), np.float32)

    def to_mef(self, recompute_spheres=True, recompute_centres=True, rebuild_trees=None, stamp=None):
        """rebuild every chunk. rebuild_trees: None = only where CollMesh.tree is None, True = always."""
        typ = self.typ
        h = self.hsem.copy()
        if stamp is not None:
            h['stamp'] = stamp
        # ---- render
        xt = []; idx = []; dn = np.zeros(len(self.groups), DNER_DT[typ])
        v0 = i0 = 0
        for k, g in enumerate(self.groups):
            nv = len(g.pos)
            if nv > 65535 or v0 + nv > 65536:
                raise ValueError('vertex index overflow (u16)')
            blk = np.zeros(nv, XTRV_DT[typ])
            blk['pos'] = g.pos; blk['uv'] = g.uv
            if typ == 0:
                blk['nrm'] = g.nrm
            else:
                blk['lmuv'] = g.lmuv
            xt.append(blk)
            t = g.tris
            if len(t) and (t.min() < 0 or t.max() >= nv):
                raise ValueError('group %d triangle index out of range' % k)
            idx.append(t + v0)
            if i0 > 65535 or len(t) > 65535 or v0 > 65535:
                raise ValueError('group %d: index start %d / %d triangles / vertex start %d exceed u16' % (k, i0, len(t), v0))
            d = dn[k]
            d['flags'] = g.flags
            if (recompute_centres or g.centre is None) and nv:
                d['centre'] = g.pos.astype(np.float64).mean(0).astype(np.float32)   # (shipped: the vertex mean)
            elif g.centre is not None:
                d['centre'] = g.centre
            d['i0'] = i0; d['ntris'] = len(t); d['v0'] = v0; d['nverts'] = nv
            d['tex'] = g.tex
            if typ == 0:
                d['tex_b'] = g.tex_b; d['env_tex'] = g.env_tex; d['env_level'] = g.env_level
            else:
                d['lightmap'] = g.lightmap
            v0 += nv; i0 += 3 * len(t)
        X = np.concatenate(xt) if xt else np.zeros(0, XTRV_DT[typ])
        if len(X) > 65536:
            raise ValueError('%d render vertices: u16 indices' % len(X))
        I = np.zeros(sum(len(t) for t in idx), ECAF_DT)
        if len(I):
            I['v'] = np.concatenate(idx)
        nf, ng, nv = len(I), len(dn), len(X)
        tail = self.d3dr_tail if self.d3dr_tail is not None else np.zeros(5 if typ == 0 else 6, '<u4')
        if typ == 0:
            d3 = np.array([4, nf, ng, nv] + list(tail), '<u4')
        else:
            d3 = np.array([4, len(self.pmtl) if self.pmtl is not None else 0, nf, ng, nv] + list(tail), '<u4')
        # ---- collision
        coll_chunks = []
        hsmc = np.zeros(1, HSMC_DT)
        cfaces = cverts = 0
        for k, c in enumerate(self.coll):
            V = np.zeros(len(c.pos), XTVC_DT); V['pos'] = c.pos; V['lmuv'] = c.lmuv
            F = np.zeros(len(c.faces), ECFC_DT); F['v'] = c.faces; F['mat'] = c.mat; F['noise'] = c.noise; F['pad'] = c.pad
            if len(c.faces) and (c.faces.max() >= len(c.pos) or c.mat.max() >= max(1, len(c.mats))):
                raise ValueError('collision mesh %d: bad vertex/material index' % k)
            if len(c.pos) > 65535:
                raise ValueError('collision mesh %d: too many vertices for u16' % k)
            if 2 * len(c.faces) - 1 > 65535:
                raise ValueError('collision mesh %d: %d faces -> %d sphere nodes > u16 (max 32768 faces)'
                                 % (k, len(c.faces), 2 * len(c.faces) - 1))
            if rebuild_trees or c.tree is None:
                S = sphere_tree(c.pos, c.faces)
            else:
                S = c.tree
            hsmc[0]['mesh'][k] = (len(F), len(V), len(c.mats), len(S), (0, 0, 0, 0))
            coll_chunks += [Chunk('XTVC', V), Chunk('ECFC', F), Chunk('TAMC', c.mats.copy()), Chunk('HPSC', S)]
            cfaces += len(F); cverts += len(V)
        # ---- header
        Pr = X['pos'].astype(float) if nv else np.zeros((0, 3))
        Pc = np.concatenate([c.pos for c in self.coll]).astype(float) if self.coll and sum(len(c.pos) for c in self.coll) else None
        if recompute_spheres:
            h['sph_render'] = bounding_sphere(Pr)
            sc = bounding_sphere(Pc) if Pc is not None else h['sph_render']
            h['sph_coll'] = sc; h['sph_coll2'] = sc
            src = np.concatenate([Pr, Pc]) if Pc is not None else Pr     # (shipped: radius >= every vertex)
            rr = np.linalg.norm(src, axis=1).max() if len(src) else 0.0
            r32 = np.float32(rr)
            if float(r32) < rr:
                r32 = np.nextafter(r32, np.float32(np.inf))
            h['radius'] = r32
        h['type'] = typ
        h['n_rfaces'] = nf; h['n_rverts'] = nv
        h['render_bytes'] = d3.nbytes + I.nbytes + dn.nbytes + X.nbytes + (self.pmtl.nbytes if self.pmtl is not None and typ == 3 else 0)
        h['n_cfaces'] = cfaces; h['n_cverts'] = cverts
        h['coll_bytes'] = (hsmc.nbytes + sum(c.rec.nbytes for c in coll_chunks)) if self.coll else 0
        h['n_magic'] = len(self.magic); h['n_atta'] = len(self.atta)
        h['n_pverts'] = len(self.portals['XVTP']); h['n_pfaces'] = len(self.portals['CFTP']); h['n_portals'] = len(self.portals['TROP'])
        h['n_bones'] = 0
        h['n_glows'] = len(self.glows) if self.glows is not None else 0
        # ---- chunks in the shipped order
        ch = [Chunk('HSEM', np.array([h], HSEM_DT)), Chunk('ATTA', self.atta.copy()), Chunk('XTVM', self.magic.copy()),
              Chunk('TROP', self.portals['TROP'].copy()), Chunk('XVTP', self.portals['XVTP'].copy()),
              Chunk('CFTP', self.portals['CFTP'].copy())]
        if self.glows is not None:
            ch.append(Chunk('WOLG', self.glows.copy()))
        ch += [Chunk('D3DR', d3), Chunk('ECAF', I), Chunk('DNER', dn), Chunk('XTRV', X)]
        if typ == 3 and self.pmtl is not None:
            ch.append(Chunk('PMTL', self.pmtl.copy()))
        if self.coll:
            ch.append(Chunk('HSMC', hsmc))
            ch += coll_chunks
        ch += [Chunk(c.tag, c.rec, c.align) for c in self.extra]
        return Mef(ch)


# ----------------------------------------------------------------------------------------------- OBJ export
def export_obj(m, path, name=None, tex_names=None, world=None):
    """render mesh (+ collision meshes as separate objects) -> Wavefront OBJ (y-up converted: OBJ x = x, y = z, z = -y,
    metres). One 'g' per render group, 'usemtl tex<slot>' (or the texture name from tex_names)."""
    name = name or os.path.splitext(os.path.basename(path))[0]
    lines = ['# IGI 2 mef -> obj (tools/mefmesh.py), metres, y up', 'o %s' % name]
    S = 1.0 / 4096.0

    def tr(p):
        p = np.asarray(p, float)
        if world is not None:
            p = p @ world[0].T + world[1]
        return np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1) * S

    vi = ti = ni = 1
    if m.type in (0, 1, 3):
        X = m.get('XTRV'); I = m.get('ECAF')['v'].reshape(-1); D = m.get('DNER')
        nv = len(X) if m.type != 1 else int(m.get('D3DR')[4])
        X = X[:nv]
        P = tr(X['pos'])
        for p in P:
            lines.append('v %.5f %.5f %.5f' % tuple(p))
        for t in X['uv']:
            lines.append('vt %.5f %.5f' % (t[0], 1.0 - t[1]))
        has_n = 'nrm' in X.dtype.names
        if has_n:
            N = X['nrm'].astype(float)
            if world is not None:
                N = N @ world[0].T
            for n_ in np.stack([N[:, 0], N[:, 2], -N[:, 1]], 1):
                lines.append('vn %.4f %.4f %.4f' % tuple(n_))
        for k, g in enumerate(D):
            tex = int(g['tex'])
            tn = tex_names[tex] if tex_names and tex < len(tex_names) else ('tex%d' % tex if tex != 0xFFFF else 'none')
            lines.append('g group%d' % k)
            lines.append('usemtl %s' % tn.strip())
            tri = I[int(g['i0']):int(g['i0']) + 3 * int(g['ntris'])].reshape(-1, 3)
            for a, b, c in tri + 1:
                if has_n:
                    lines.append('f %d/%d/%d %d/%d/%d %d/%d/%d' % (a, a, a, b, b, b, c, c, c))
                else:
                    lines.append('f %d/%d %d/%d %d/%d' % (a, a, b, b, c, c))
        vi += len(P)
    for k, (V, F) in enumerate(zip(m.all('XTVC'), m.all('ECFC'))):
        lines.append('o %s_collision%d' % (name, k))
        for p in tr(V['pos']):
            lines.append('v %.5f %.5f %.5f' % tuple(p))
        for a, b, c in F['v'].astype(int) + vi:
            lines.append('f %d %d %d' % (a, b, c))
        vi += len(V)
    open(path, 'w').write('\n'.join(lines) + '\n')
    return path


# ----------------------------------------------------------------------------------------------- game scan + selftest
GAME = r'C:\Users\1qdeath\Games\IGI2\app'


def iter_game_mefs(game=GAME):
    """yield (resource name, .res path, bytes) for every .mef entry of every .res in the game folder (read-only)"""
    import glob
    for p in sorted(glob.glob(os.path.join(game, '**', '*.res'), recursive=True)):
        try:
            form, ch, h = ilff.read(p)
        except Exception:
            continue
        for n, t, b in ilff.entries(ch):
            if n and n.lower().endswith('.mef'):
                yield n, p, b


def semantic_check(m):
    """recompute every derived field from the decoded content and compare with the stored one -> list of mismatches"""
    bad = []
    h = m.hsem
    if h is None:
        return bad
    typ = m.type
    d3 = m.get('D3DR'); X = m.get('XTRV'); I = m.get('ECAF'); D = m.get('DNER')
    if typ == 0:
        nf, ng, nv = d3[1], d3[2], d3[3]
    elif typ == 3:
        nf, ng, nv = d3[2], d3[3], d3[4]
        if d3[1] != (len(m.get('PMTL')) if m.get('PMTL') is not None else 0):
            bad.append('D3DR lightmap count')
    else:
        nf, ng, nv = d3[1], d3[2], d3[4]
        if d3[5] != len(X) or d3[3] + d3[4] != len(X):
            bad.append('D3DR skin record count')
    if (nf, ng) != (len(I), len(D)) or (typ != 1 and nv != len(X)):
        bad.append('D3DR counts')
    if (h['n_rfaces'], h['n_rverts']) != (nf, nv):
        bad.append('HSEM render counts')
    xb = X.nbytes if typ != 1 else int(nv) * 40
    rb = d3.nbytes + I.nbytes + D.nbytes + xb + sum(p.nbytes for p in m.all('PMTL'))
    if h['render_bytes'] != rb:
        bad.append('HSEM render bytes')
    s0 = v0 = 0
    for g in D:
        if g['i0'] != s0 or g['v0'] != v0:
            bad.append('group ranges'); break
        seg = I['v'].reshape(-1)[s0:s0 + 3 * int(g['ntris'])]
        if len(seg) and (seg.min() < v0 or seg.max() >= v0 + g['nverts']):
            bad.append('group index range'); break
        s0 += 3 * int(g['ntris']); v0 += int(g['nverts'])
    if s0 != 3 * nf or v0 != nv:
        bad.append('group totals')
    cnt = dict(n_magic=len(m.get('XTVM')), n_atta=len(m.get('ATTA')), n_pverts=len(m.get('XVTP')),
               n_pfaces=len(m.get('CFTP')), n_portals=len(m.get('TROP')),
               n_glows=len(m.get('WOLG')) if m.get('WOLG') is not None else 0,
               n_bones=len(m.get('MANB')) if m.get('MANB') is not None else 0)
    for k, v in cnt.items():
        if h[k] != v:
            bad.append('HSEM ' + k)
    cb = sum(c.rec.nbytes for c in m.chunks if c.tag in COLL_TAGS)
    if h['coll_bytes'] != cb:
        bad.append('HSEM coll bytes')
    cv = m.all('XTVC'); cf = m.all('ECFC')
    if (h['n_cfaces'], h['n_cverts']) != (sum(len(x) for x in cf), sum(len(x) for x in cv)):
        bad.append('HSEM coll counts')
    hs = m.get('HSMC')
    if hs is not None:
        for k in range(2):
            e = hs[0]['mesh'][k]
            want = (len(cf[k]), len(cv[k]), len(m.all('TAMC')[k]), len(m.all('HPSC')[k]))
            if (e['nfaces'], e['nverts'], e['nmats'], e['nspheres']) != want:
                bad.append('HSMC counts')
            if want[3] != max(0, 2 * want[0] - 1) and want[0]:
                bad.append('sphere count != 2n-1')
    # render sphere tight
    if typ in (0, 3) and len(X):
        P = X['pos'].astype(float)
        s = h['sph_render'].astype(float)
        d = np.linalg.norm(P - s[:3], axis=1).max()
        if d > s[3] * (1 + 1e-4) + 0.05:
            bad.append('render sphere does not bound')
    return bad


def selftest(game=GAME, limit=None, verbose=True, trees=False):
    import collections, hashlib
    stats = collections.Counter()
    seen = set()
    fails = []
    for n, p, b in iter_game_mefs(game):
        stats['entries'] += 1
        hsh = hashlib.sha1(b).digest()
        if hsh in seen:
            continue
        seen.add(hsh)
        stats['unique'] += 1
        if b[:4] != b'ILFF':
            stats['not ILFF (skipped: %s)' % b[:4].decode('latin1')] += 1
            continue
        try:
            m = Mef.read(b)
        except Exception as e:
            fails.append((n, p, 'read: %s' % e)); continue
        stats['parsed'] += 1
        stats['type %s' % m.type] += 1
        for c in m.chunks:
            stats['chunk ' + c.tag] += 1
        if m.write() == b:
            stats['round-trip identical'] += 1
        else:
            fails.append((n, p, 'round trip differs'))
        bad = semantic_check(m)
        if bad:
            stats['semantic mismatches'] += 1
            if len(fails) < 50:
                fails.append((n, p, 'semantic: %s' % bad))
        else:
            stats['semantic ok'] += 1
        if trees:
            for V, F, S in zip(m.all('XTVC'), m.all('ECFC'), m.all('HPSC')):
                if len(F):
                    pr = check_tree(S, V['pos'], F['v'], tol=0.05)
                    stats['sphere trees ok' if not pr else 'sphere trees BAD'] += 1
                    if pr:
                        fails.append((n, p, 'tree: %s' % pr[:2]))
        if m.type in (0, 3):
            try:
                r = RigidModel.from_mef(m)
                b2 = r.to_mef(recompute_spheres=False, recompute_centres=False).write()
                if b2 == b:
                    stats['rebuilt from RigidModel identical'] += 1
                else:
                    stats['rebuilt from RigidModel differs'] += 1
                    if len(fails) < 50:
                        fails.append((n, p, 'rebuild differs'))
            except Exception as e:
                fails.append((n, p, 'rebuild: %s' % e))
        if limit and stats['parsed'] >= limit:
            break
    if verbose:
        for k in sorted(stats):
            print('%-45s %d' % (k, stats[k]))
        for f in fails[:30]:
            print('FAIL', f)
    return stats, fails


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':           # --selftest [--trees] [limit]
        args = sys.argv[2:]
        tr = '--trees' in args
        args = [a for a in args if a != '--trees']
        st, fl = selftest(limit=int(args[0]) if args else None, trees=tr)
        sys.exit(1 if fl else 0)
    elif len(sys.argv) > 2 and sys.argv[1] == '--obj':
        export_obj(Mef.read(open(sys.argv[2], 'rb').read()), sys.argv[3])
    else:
        print(__doc__)
