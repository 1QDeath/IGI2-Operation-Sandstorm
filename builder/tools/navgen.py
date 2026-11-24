"""Generate IGI 2 AI graphs for a level that has none (e.g. a multiplayer map).

Pipeline (a small Recast-style heightfield):
  1. static collision geometry: terrain heightmap (tools/terrain.py) + the exact collision mesh of every
     Building / EditRigidObj / ExplodeObject / GenericTBA / Switch (tools/mef.py). Doors and ladders are
     NOT obstacles (doors open, ladders are not walkable by AI).
  2. rasterise into vertical solid spans per grid column (cell = CS units), merge them
  3. walkable surfaces = tops of walkable spans with AGENT_H clearance; 4-neighbour links where the
     height step <= CLIMB and the shared clearance >= AGENT_H; erode the border by ERODE cells
  4. cluster surfaces per tile (fine tiles on model floors, coarse tiles on terrain), one node per cluster
     at the surface farthest from walls; link nodes of touching clusters when a straight walk between
     them stays on connected surfaces and never crosses a doorway
  5. every door gets two NODECRITERIA_DOOR nodes (one per side) linked through the doorway, like the
     original graphs, so the AI opens doors instead of walking into them
  6. graphs = connected components of the node graph (each exported graph is ONE component: unreachable
     path searches flood the engine's 1280-entry path pool and crash it)
Units: 1 m = 4096.
"""
import math
import numpy as np
import scipy.sparse as sp
import scipy.sparse.csgraph as csg

import igiqvm
from qast import lit, tasks
import mef as meflib

CS = 1024.0           # grid cell (0.25 m)
SAMPLE = 480.0        # triangle sample spacing (< CS/2)
MERGE_GAP = 700.0     # samples closer than this in one column belong to one solid span
AGENT_H = 7200.0      # clearance a soldier needs (1.75 m)
CLIMB = 1700.0        # max step between neighbouring cells (0.41 m)
WALK_COS = math.cos(math.radians(46))
TERRAIN_SLOPE = math.radians(40)
ERODE = 1
LOW_STEP = 1000.0
OBSTACLE_TYPES = ('Building', 'EditRigidObj', 'ExplodeObject', 'GenericTBA', 'AlarmControl')


YAW_SIGN = 1.0


def rot(a, b, g):
    """object orientation (alpha, beta, gamma) -> 3x3; gamma = yaw about +z (verified with the sewer turns)"""
    g = g * YAW_SIGN
    ca, sa, cb, sb, cg, sg = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(g), math.sin(g)
    rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
    ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    rz = np.array([[cg, -sg, 0], [sg, cg, 0], [0, 0, 1]])
    return rz @ ry @ rx


class NavGen:
    def __init__(self, mission, terrain, models, bounds, skip_ids=(), mesh_mode='0'):
        self.m, self.terrain, self.lib = mission, terrain, models
        self.mesh_mode = mesh_mode
        x0, y0, x1, y1 = bounds
        self.x0, self.y0 = x0, y0
        self.nx, self.ny = int((x1 - x0) // CS) + 1, int((y1 - y0) // CS) + 1
        self.skip = set(skip_ids)
        self.log = []
        self.max_dev = None             # build(max_dev_m=): every link must follow the walk surface within this (units)

    # ------------------------------------------------------------------ 1. geometry
    def instances(self):
        out = []
        for t, d, p in tasks(self.m.stmts):
            ty = lit(t.args[1])
            i = lit(t.args[0])
            if ty not in OBSTACLE_TYPES or i in self.skip:
                continue
            a = [lit(x) for x in t.args[3:] if not isinstance(x, igiqvm.Call)]
            pos, ang, model = a[0:3], a[3:6], a[6]
            if not isinstance(model, str) or model.lower() == 'none':
                continue
            out.append((i, ty, model, np.array(pos, float), ang))
        return out

    def triangles(self):
        tris = []
        for i, ty, model, pos, ang in self.instances():
            for v, f in self.lib.collision_tree(model, self.mesh_mode):   # shell + attached interiors
                w = v @ rot(*ang).T + pos
                tris.append(w[f])
        return np.concatenate(tris) if tris else np.zeros((0, 3, 3))

    # ------------------------------------------------------------------ 2. spans
    def rasterise(self):
        T = self.triangles()
        e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
        nrm = np.cross(e1, e2)
        ln = np.linalg.norm(nrm, axis=1)
        keep = ln > 1e-6
        T, nrm, ln = T[keep], nrm[keep], ln[keep]
        walk = np.abs(nrm[:, 2]) / ln >= WALK_COS
        L = np.max(np.stack([np.linalg.norm(T[:, 1] - T[:, 0], axis=1), np.linalg.norm(T[:, 2] - T[:, 0], axis=1),
                             np.linalg.norm(T[:, 2] - T[:, 1], axis=1)]), axis=0)
        nsub = np.maximum(1, np.ceil(L / SAMPLE)).astype(int)
        cells, zs, ws = [], [], []
        for n in np.unique(nsub):
            idx = np.nonzero(nsub == n)[0]
            ii, jj = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
            msk = ii + jj <= n
            u, w_ = ii[msk] / n, jj[msk] / n                       # barycentric lattice
            for chunk in np.array_split(idx, max(1, len(idx) * len(u) // 4_000_000 + 1)):
                tt = T[chunk]
                P = tt[:, None, 0] + u[None, :, None] * (tt[:, None, 1] - tt[:, None, 0]) + w_[None, :, None] * (tt[:, None, 2] - tt[:, None, 0])
                cx = np.floor((P[..., 0] - self.x0) / CS).astype(np.int64)
                cy = np.floor((P[..., 1] - self.y0) / CS).astype(np.int64)
                ok = (cx >= 0) & (cy >= 0) & (cx < self.nx) & (cy < self.ny)
                cells.append((cy * self.nx + cx)[ok]); zs.append(P[..., 2][ok])
                ws.append(np.broadcast_to(walk[chunk][:, None], cx.shape)[ok])
        cell = np.concatenate(cells); z = np.concatenate(zs); wk = np.concatenate(ws)
        self.log.append('triangles %d, samples %d' % (len(T), len(cell)))
        # terrain: a 0.5 m slab under the surface (so things below it, like the sewer, stay open)
        gx, gy = np.meshgrid(self.x0 + (np.arange(self.nx) + 0.5) * CS, self.y0 + (np.arange(self.ny) + 0.5) * CS)
        tz = self.terrain.height(gx, gy)
        dzdx = np.gradient(tz, CS, axis=1); dzdy = np.gradient(tz, CS, axis=0)
        tslope_ok = np.arctan(np.hypot(dzdx, dzdy)) <= TERRAIN_SLOPE
        tcell = np.arange(self.nx * self.ny).reshape(self.ny, self.nx)
        tok = ~np.isnan(tz) & ~self.discarded(gx, gy)
        self.tz = tz
        return cell, z, wk, tcell[tok], tz[tok], tslope_ok[tok]

    def discarded(self, gx, gy):
        """terrain holes cut by DiscardTask (width/height in heightmap cells)"""
        out = np.zeros(gx.shape, bool)
        step = self.terrain.maps[0][3]
        for i in self.m.find('DiscardTask'):
            x, y, z, w, h = [lit(a) for a in self.m.byid[i].args[3:8]]
            out |= (np.abs(gx - x) <= w * step / 2) & (np.abs(gy - y) <= h * step / 2)
        return out

    def spans(self):
        cell, z, wk, tcell, tz, tslope = self.rasterise()
        # model samples -> spans per column
        o = np.lexsort((z, cell)); cell, z, wk = cell[o], z[o], wk[o]
        brk = np.ones(len(cell), bool)
        brk[1:] = (cell[1:] != cell[:-1]) | (z[1:] - z[:-1] > MERGE_GAP)
        sid = np.cumsum(brk) - 1
        n = sid[-1] + 1
        s_cell = cell[brk]
        s_lo = z[brk]
        s_hi = np.full(n, -np.inf); np.maximum.at(s_hi, sid, z)
        top = z >= s_hi[sid] - 150                                   # samples at the top of their span
        s_walk = np.zeros(n, bool); np.logical_or.at(s_walk, sid, wk & top)
        s_ter = np.zeros(n, bool)
        # terrain slabs
        all_cell = np.concatenate([s_cell, tcell]); all_lo = np.concatenate([s_lo, tz - 2048])
        all_hi = np.concatenate([s_hi, tz]); all_walk = np.concatenate([s_walk, tslope])
        all_ter = np.concatenate([s_ter, np.ones(len(tcell), bool)])
        o = np.lexsort((all_lo, all_cell))
        c, lo, hi, w, te = all_cell[o], all_lo[o], all_hi[o], all_walk[o], all_ter[o]
        # merge overlapping spans (terrain slab vs building floor etc.); the merged top keeps the flags of whatever is on top
        out_c, out_lo, out_hi, out_w, out_t = [], [], [], [], []
        brk = np.ones(len(c), bool)
        runmax = hi.copy()
        # sequential merge (vectorised per column is awkward; columns are short)
        cur = 0
        for k in range(1, len(c) + 1):
            if k == len(c) or c[k] != c[cur] or lo[k] > runmax[cur] + MERGE_GAP:
                out_c.append(c[cur]); out_lo.append(lo[cur]); out_hi.append(runmax[cur]); out_w.append(w[cur]); out_t.append(te[cur])
                cur = k
            else:
                if hi[k] >= runmax[cur] - 150:
                    w[cur] = w[k] if hi[k] > runmax[cur] + 150 else (w[cur] or w[k])
                    te[cur] = te[k] if hi[k] > runmax[cur] + 150 else (te[cur] or te[k])
                runmax[cur] = max(runmax[cur], hi[k])
        return (np.array(out_c), np.array(out_lo), np.array(out_hi), np.array(out_w), np.array(out_t))

    # ------------------------------------------------------------------ 3. surfaces
    def surfaces(self):
        c, lo, hi, w, te = self.spans()
        nxt_same = np.zeros(len(c), bool); nxt_same[:-1] = c[1:] == c[:-1]
        ceil = np.full(len(c), np.inf); ceil[:-1] = np.where(nxt_same[:-1], lo[1:], np.inf)
        ok = ceil - hi >= AGENT_H                    # every top with head room is a candidate; walkability below
        F = dict(cell=c[ok], z=hi[ok], ceil=ceil[ok], terrain=te[ok], walk=w[ok])
        n = len(F['cell'])
        start = np.searchsorted(F['cell'], np.arange(self.nx * self.ny + 1))
        nb = np.full((n, 4), -1, np.int64)
        cx, cy = F['cell'] % self.nx, F['cell'] // self.nx
        for d, (dx, dy) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
            qx, qy = cx + dx, cy + dy
            valid = (qx >= 0) & (qy >= 0) & (qx < self.nx) & (qy < self.ny)
            qc = np.where(valid, qy * self.nx + qx, 0)
            s0, s1 = start[qc], start[qc + 1]
            best = np.full(n, np.inf)
            for k in range(int((s1 - s0).max()) if n else 0):
                j = s0 + k
                vk = valid & (j < s1)
                jj = np.where(vk, j, 0)
                dz = np.abs(F['z'][jj] - F['z'])
                clear = np.minimum(F['ceil'][jj], F['ceil']) - np.maximum(F['z'][jj], F['z'])
                good = vk & (dz <= CLIMB) & (clear >= AGENT_H) & (dz < best)
                nb[good, d] = jj[good]; best[good] = dz[good]
        # low obstacles (door thresholds, kerbs, the foot of a thin wall in a doorway): a non-walkable top
        # within LOW_STEP of a walkable neighbour is walkable (Recast's low-hanging-obstacle filter, sideways)
        alive = F['walk'].copy()
        for d in range(4):
            j = nb[:, d]; jj = np.maximum(j, 0)
            alive |= (j >= 0) & F['walk'][jj] & (np.abs(F['z'][jj] - F['z']) <= LOW_STEP)
        nb[~alive] = -1
        nb[(nb >= 0) & ~alive[np.maximum(nb, 0)]] = -1
        for _ in range(ERODE):
            border = alive & (np.any(nb < 0, axis=1) | np.any(~alive[np.maximum(nb, 0)] & (nb >= 0), axis=1))
            alive &= ~border
        nb[~alive] = -1
        nb[(nb >= 0) & ~alive[np.maximum(nb, 0)]] = -1
        # distance to the nearest border (in cells) for node placement
        dist = np.full(n, -1)
        front = np.nonzero(alive & np.any(nb < 0, axis=1))[0]
        dist[front] = 0
        d = 0
        while len(front):
            d += 1
            cand = nb[front].ravel(); cand = cand[cand >= 0]
            cand = np.unique(cand[dist[cand] < 0])
            dist[cand] = d; front = cand
        dist[~alive] = -1
        F.update(nb=nb, alive=alive, dist=dist, start=start)
        F['x'] = self.x0 + (F['cell'] % self.nx + 0.5) * CS
        F['y'] = self.y0 + (F['cell'] // self.nx + 0.5) * CS
        self.F = F
        self.log.append('surfaces %d alive %d' % (n, alive.sum()))
        return F

    # ------------------------------------------------------------------ 4/5. nodes and links
    def doors(self):
        out = []
        for i in self.m.find('Door'):
            a = [lit(x) for x in self.m.byid[i].args[3:] if not isinstance(x, igiqvm.Call)]
            pos, ang, model = np.array(a[0:3], float), a[6:9], a[9]
            meshes = self.lib.collision(model)
            if not meshes or not len(meshes[0][0]):
                continue
            v = meshes[0][0]
            R = rot(*ang)
            lo, hi = v.min(0), v.max(0)
            corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]) @ R.T + pos
            c = ((lo + hi) / 2) @ R.T + pos
            ext = hi - lo
            horiz = [ext[k] * np.linalg.norm(R[:2, k]) for k in range(3)]     # horizontal extent of each model axis
            k = int(np.argmax(horiz))
            wdir = R[:2, k] / max(1e-9, np.linalg.norm(R[:2, k]))
            nrm = np.array([-wdir[1], wdir[0], 0.0])
            out.append(dict(id=i, center=c, normal=nrm, width=horiz[k], corners=corners, zlo=corners[:, 2].min(), zhi=corners[:, 2].max()))
        return out

    def door_mask(self, doors):
        F = self.F
        mask = np.zeros(len(F['cell']), bool)
        for dr in doors:
            xs, ys = dr['corners'][:, 0], dr['corners'][:, 1]
            # the leaf sweeps a disc of radius = width around the hinge; mark the doorway band generously
            cxy = dr['center'][:2]
            r = dr['width'] * 0.55 + CS
            sel = (np.hypot(F['x'] - cxy[0], F['y'] - cxy[1]) <= r) & (F['z'] >= dr['zlo'] - 2500) & (F['z'] <= dr['zlo'] + 4000)
            mask |= sel
        return mask

    def surface_at(self, x, y, z, maxdz=3000, alive_only=True, avoid=None, radius=6):
        F = self.F
        cx, cy = int((x - self.x0) // CS), int((y - self.y0) // CS)
        best, bd = -1, 1e18
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                qx, qy = cx + dx, cy + dy
                if not (0 <= qx < self.nx and 0 <= qy < self.ny):
                    continue
                c = qy * self.nx + qx
                for j in range(F['start'][c], F['start'][c + 1]):
                    if alive_only and not F['alive'][j]:
                        continue
                    if avoid is not None and avoid[j]:
                        continue
                    dzz = abs(F['z'][j] - z)
                    if dzz > maxdz:
                        continue
                    dd = math.hypot(F['x'][j] - x, F['y'][j] - y) + dzz * 2 - F['dist'][j] * 300
                    if dd < bd:
                        best, bd = j, dd
        return best

    def walk(self, a, b, door_mask, allow_door=False):
        """straight walk on connected surfaces from surface a to surface b (4-neighbour steps along the
        segment; a diagonal step may go x-first or y-first)"""
        F = self.F
        nb = F['nb']
        ax, ay = F['cell'][a] % self.nx, F['cell'][a] // self.nx
        bx, by = F['cell'][b] % self.nx, F['cell'][b] // self.nx
        n = max(abs(bx - ax), abs(by - ay))
        cur = a
        px, py = ax, ay
        D = {(1, 0): 0, (-1, 0): 1, (0, 1): 2, (0, -1): 3}
        # owner 10-11 'soldiers float / sink': igi2.exe puts a LIVING AI soldier's feet on the straight line between his
        # graph node and the next one (ground collision 0x50c820 never ray-casts for AI; dead bodies and the player do).
        # So with max_dev set, every surface the walk crosses must lie within max_dev of the a->b chord.
        tol, za, zb = (None if allow_door else self.max_dev), F['z'][a], F['z'][b]   # (doorways: thresholds step)
        L2 = float((bx - ax) ** 2 + (by - ay) ** 2) or 1.0

        def on_chord(s_):
            if tol is None:
                return True
            cx_, cy_ = F['cell'][s_] % self.nx, F['cell'][s_] // self.nx
            t_ = min(1.0, max(0.0, ((cx_ - ax) * (bx - ax) + (cy_ - ay) * (by - ay)) / L2))
            return abs(F['z'][s_] - (za + t_ * (zb - za))) <= tol
        for k in range(1, n + 1):
            tx = int(round(ax + (bx - ax) * k / n)); ty = int(round(ay + (by - ay) * k / n))
            sx, sy = tx - px, ty - py
            nxt = -1
            if sx and sy:                                   # diagonal: x then y, or y then x
                for first, second in (((sx, 0), (0, sy)), ((0, sy), (sx, 0))):
                    m1 = nb[cur, D[first]]
                    if m1 < 0 or (door_mask[m1] and not allow_door) or not on_chord(m1):
                        continue
                    m2 = nb[m1, D[second]]
                    if m2 >= 0 and (allow_door or not door_mask[m2]) and on_chord(m2):
                        nxt = m2
                        break
            else:
                m1 = nb[cur, D[(sx, sy)]]
                if m1 >= 0 and (allow_door or not door_mask[m1]) and on_chord(m1):
                    nxt = m1
            if nxt < 0:
                return False
            cur = nxt
            px, py = tx, ty
        return cur == b or (F['cell'][cur] == F['cell'][b] and abs(F['z'][cur] - F['z'][b]) <= CLIMB)

    def bridge(self, sa, sb, allowed, door_mask, max_cells=4000):
        """surfaces sa, sb are connected through `allowed` surfaces but not by a straight walk:
        BFS a path, then string-pull it into straight-walkable legs. -> list of surfaces [sa, ..., sb] or None"""
        F = self.F
        nb = F['nb']
        prev = {sa: -1}
        q = [sa]; qi = 0
        while qi < len(q) and len(prev) < max_cells:
            u = q[qi]; qi += 1
            if u == sb:
                break
            for d in range(4):
                w = nb[u, d]
                if w >= 0 and w not in prev and allowed(w):
                    prev[w] = u; q.append(w)
        if sb not in prev:
            return None
        path = [sb]
        while prev[path[-1]] != -1:
            path.append(prev[path[-1]])
        path.reverse()
        pts, i = [sa], 0
        while path[i] != sb:
            j = len(path) - 1
            while j > i + 1 and not self.walk(path[i], path[j], door_mask):
                j -= 1
            if j == i + 1 and not self.walk(path[i], path[j], door_mask):
                return None
            pts.append(path[j]); i = j
        return pts

    def build(self, fine_tile=8, coarse_tile=18, min_cluster=10, link_radius=2, closed_doors=(), max_dev_m=None, long_link_m=None):
        """closed_doors: door task ids the AI must never path through (locked / switch-operated).
        max_dev_m: links must follow the walk surface within this many metres (see walk); neighbour clusters whose
        centres cannot be linked get bridge nodes where the ground bends. long_link_m: extra straight links up to this
        length where the ground allows (flat valley floors, roads) so paths need fewer nodes (= fewer path-pool entries)"""
        self.max_dev = max_dev_m * 4096.0 if max_dev_m else None
        F = self.surfaces()
        doors = self.doors()
        dmask = self.door_mask(doors)
        alive = F['alive']
        n = len(F['cell'])
        cx, cy = F['cell'] % self.nx, F['cell'] // self.nx
        tile = np.where(F['terrain'], coarse_tile, fine_tile)
        tkey = np.where(F['terrain'], 1, 0)
        tx, ty = cx // tile, cy // tile
        # connected sub-clusters inside each tile (edges between surfaces of the same tile and kind)
        rows, cols = [], []
        for d in range(4):
            j = F['nb'][:, d]
            ok = alive & (j >= 0)
            ok[ok] &= (tx[j[ok]] == tx[ok]) & (ty[j[ok]] == ty[ok]) & (tkey[j[ok]] == tkey[ok]) & ~dmask[ok] & ~dmask[j[ok]]
            rows.append(np.nonzero(ok)[0]); cols.append(j[ok])
        A = sp.coo_matrix((np.ones(sum(len(r) for r in rows)), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
        ncl, lab = csg.connected_components(A, directed=False)
        lab = np.where(alive & ~dmask, lab, -1)
        size = np.bincount(lab[lab >= 0], minlength=ncl)
        # node of each cluster: surface farthest from the border (ties: nearest the cluster centroid)
        order = np.lexsort((-F['dist'], lab))
        ls = lab[order]
        first = np.ones(len(ls), bool); first[1:] = ls[1:] != ls[:-1]
        pick = order[first & (ls >= 0)]
        pick = pick[size[lab[pick]] >= min_cluster]
        nodes = {int(lab[j]): int(j) for j in pick}
        cl_ids = sorted(nodes)
        node_surf = np.array([nodes[c] for c in cl_ids])
        cl_index = {c: k for k, c in enumerate(cl_ids)}
        # cluster adjacency (any neighbour link between two clusters), plus 2-ring candidates
        good = np.zeros(ncl + 1, bool); good[cl_ids] = True
        pairs = []
        for d in range(4):
            j = F['nb'][:, d]
            ok = (lab >= 0) & (j >= 0)
            a_, b_ = lab[ok], lab[j[ok]]
            keep = (a_ != b_) & (b_ >= 0)
            a_, b_ = a_[keep], b_[keep]
            keep = good[a_] & good[b_]
            pairs.append(np.stack([np.minimum(a_[keep], b_[keep]), np.maximum(a_[keep], b_[keep])], 1))
        adj = {tuple(r) for r in np.unique(np.concatenate(pairs), axis=0).tolist()} if pairs else set()
        # walkable straight links
        edges = set()
        failed = []
        for p, q in adj:
            sa, sb = nodes[p], nodes[q]
            if self.walk(sa, sb, dmask) or self.walk(sb, sa, dmask):
                edges.add((cl_index[p], cl_index[q]))
            else:
                failed.append((p, q))
        # clusters that touch but whose centres cannot see each other (stairs, L-shaped corridors):
        # connect them through extra nodes along a string-pulled path inside the two clusters
        extra_nodes = []
        n_bridged = 0
        uf = {}
        def find(x):
            while uf.get(x, x) != x:
                uf[x] = uf.get(uf[x], uf[x]); x = uf[x]
            return x
        for a_, b_ in edges:
            uf[find(a_)] = find(b_)
        for p, q in failed:
            ia, ib = cl_index[p], cl_index[q]
            if find(ia) == find(ib) and self.max_dev is None:
                continue                                   # already connected some other way
            # (ground-following links: bridge every failed neighbour pair, or paths make long detours)
            pts = self.bridge(nodes[p], nodes[q], lambda w, p=p, q=q: lab[w] in (p, q), dmask)
            if not pts:
                continue
            chain = [ia]
            for s_ in pts[1:-1]:
                chain.append(len(cl_ids) + len(extra_nodes)); extra_nodes.append(int(s_))
            chain.append(ib)
            for u_, v_ in zip(chain, chain[1:]):
                edges.add((min(u_, v_), max(u_, v_)))
            uf[find(ia)] = find(ib)
            n_bridged += 1
        self.log.append('cluster links: %d straight, %d failed, %d bridged with %d extra nodes' % (len(adj) - len(failed), len(failed), n_bridged, len(extra_nodes)))
        # extra links to second neighbours (smoother paths) when the straight walk is clear
        node_surf = np.concatenate([node_surf, np.array(extra_nodes, dtype=node_surf.dtype)]) if extra_nodes else node_surf
        nbr = {k: set() for k in range(len(node_surf))}
        for a_, b_ in edges:
            nbr[a_].add(b_); nbr[b_].add(a_)
        for a_ in list(nbr):
            for b_ in list(nbr[a_]):
                for c_ in list(nbr[b_]):
                    if c_ != a_ and c_ not in nbr[a_] and a_ < c_:
                        sa, sc = node_surf[a_], node_surf[c_]
                        if math.hypot(F['x'][sa] - F['x'][sc], F['y'][sa] - F['y'][sc]) < 15 * 4096 and self.walk(sa, sc, dmask):
                            edges.add((a_, c_))
        if long_link_m:
            # per node and 45-degree sector: the farthest node within 4 hops, 12..long_link_m away, whose straight walk
            # (ground-following) is clear
            nbr = {k: set() for k in range(len(node_surf))}
            for a_, b_ in edges:
                nbr[a_].add(b_); nbr[b_].add(a_)
            added, lmax = 0, long_link_m * 4096.0
            for a_ in range(len(node_surf)):
                ring, front = {a_}, {a_}
                for _ in range(4):
                    front = {w for u in front for w in nbr[u]} - ring
                    ring |= front
                sa = node_surf[a_]
                cand = []
                for c_ in ring:
                    if c_ <= a_ or c_ in nbr[a_]:
                        continue
                    sc = node_surf[c_]
                    dx, dy = F['x'][sc] - F['x'][sa], F['y'][sc] - F['y'][sa]
                    dd = math.hypot(dx, dy)
                    if 12 * 4096 <= dd <= lmax:
                        cand.append((int((math.atan2(dy, dx) + math.pi) / (math.pi / 4)) % 8, -dd, c_))
                cand.sort()
                done = set()
                for sec, _, c_ in cand:
                    if sec in done:
                        continue
                    if self.walk(sa, node_surf[c_], dmask):
                        edges.add((a_, c_)); done.add(sec); added += 1
            self.log.append('long links (12..%.0f m): %d' % (long_link_m, added))
        node_list = [dict(s=int(s), crit='') for s in node_surf]
        # doors: one node each side, linked through the doorway, each linked to nearby nodes on its own side
        self.door_pairs = []
        for dr in doors:
            if dr['id'] in closed_doors:
                continue
            pair = []
            for sgn in (1, -1):
                p = dr['center'] + dr['normal'] * sgn * (dr['width'] * 0.5 + 2600)
                s = self.surface_at(p[0], p[1], dr['zlo'] + 200, maxdz=2500, avoid=dmask, radius=4)
                pair.append(s)
            if min(pair) < 0 or pair[0] == pair[1]:
                self.log.append('door %d: no floor on both sides' % dr['id'])
                continue
            if not self.walk(pair[0], pair[1], dmask, allow_door=True):
                self.log.append('door %d: doorway not walkable' % dr['id'])
                continue
            ka, kb = len(node_list), len(node_list) + 1
            node_list += [dict(s=int(pair[0]), crit='NODECRITERIA_DOOR'), dict(s=int(pair[1]), crit='NODECRITERIA_DOOR')]
            edges.add((ka, kb))
            for k_, s in ((ka, pair[0]), (kb, pair[1])):
                near = sorted(range(len(node_surf)), key=lambda q: math.hypot(F['x'][node_surf[q]] - F['x'][s], F['y'][node_surf[q]] - F['y'][s]) + 3 * abs(F['z'][node_surf[q]] - F['z'][s]))[:8]
                got = 0
                for q in near:
                    sq = node_surf[q]
                    if math.hypot(F['x'][sq] - F['x'][s], F['y'][sq] - F['y'][s]) > 12 * 4096:
                        break
                    if self.walk(s, sq, dmask) or self.walk(sq, s, dmask):
                        edges.add((k_, q)); got += 1
                        if got >= 3:
                            break
            self.door_pairs.append((dr['id'], ka, kb))
        self.nodes, self.edges = node_list, edges
        self.dmask = dmask
        self.log.append('nodes %d (doors %d) edges %d' % (len(node_list), len(self.door_pairs), len(edges)))
        return node_list, edges

    def components(self, min_nodes=4):
        n = len(self.nodes)
        e = np.array(sorted(self.edges)) if self.edges else np.zeros((0, 2), int)
        A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
        ncomp, lab = csg.connected_components(A, directed=False)
        comps = [np.nonzero(lab == c)[0] for c in range(ncomp)]
        comps = [c for c in comps if len(c) >= min_nodes]
        comps.sort(key=len, reverse=True)
        return comps

    def export(self, comp, material_model=11, light=0.3, min_sep=900.0, jitter=100.0):
        """one connected component -> (graph .dat bytes, node positions, nEdges, maxNodes)

        The game's A* (igi2.exe+0x1c6370) re-opens a node when a new path is EQUAL or better
        (fcomp + test ah,0x41), so a zero-length edge makes it ping-pong between the two nodes forever
        and the whole game hangs (seen: a door node generated on top of a cluster node). Nodes closer
        than min_sep are merged (door nodes win) and every position gets a tiny deterministic jitter so
        that no two routes cost exactly the same. The originals' shortest edge is 4103 units."""
        import graph as G
        F = self.F
        P = {k: np.array([float(F['x'][self.nodes[k]['s']]), float(F['y'][self.nodes[k]['s']]), float(F['z'][self.nodes[k]['s']])])
             for k in comp}
        rep, placed = {}, {}
        for k in sorted(comp, key=lambda k: (self.nodes[k]['crit'] == '', k)):       # door nodes first: they survive
            cell = tuple((P[k] // min_sep).astype(int))
            hit = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for q in placed.get((cell[0] + dx, cell[1] + dy, cell[2] + dz), ()):
                            if hit is None and np.linalg.norm(P[q] - P[k]) < min_sep:
                                hit = q
            if hit is None:
                rep[k] = k; placed.setdefault(cell, []).append(k)
            else:
                rep[k] = hit
        keep = [k for k in comp if rep[k] == k]
        ids = {k: i + 1 for i, k in enumerate(keep)}
        nodes = []
        for k in keep:
            s = self.nodes[k]['s']
            rng = np.random.default_rng(int(k) * 7919 + 17)
            jx, jy = rng.uniform(-jitter, jitter, 2)
            z_ = float(P[k][2])
            if self.max_dev is not None and F['terrain'][s]:        # (the jitter moves it off its cell: re-sample)
                z_ = float(self.terrain.height(P[k][0] + jx, P[k][1] + jy))
            nodes.append(dict(id=ids[k], pos=(float(P[k][0] + jx), float(P[k][1] + jy), z_),
                              material=1 if F['terrain'][s] else material_model, light=light,
                              terrain=1 if F['terrain'][s] else 0, crit=self.nodes[k]['crit']))
        moved = {}                                         # links whose end points changed by a merge
        for a, b in self.edges:
            if a in rep and b in rep and rep[a] != rep[b]:
                key = (min(rep[a], rep[b]), max(rep[a], rep[b]))
                moved[key] = moved.get(key, False) or (rep[a] == a and rep[b] == b)
        # re-check the moved links on the walk grid; drop the ones that are not walkable unless that would
        # split the graph (kruskal-style: original links first, then re-walked ones, then the rest only if needed)
        sv = lambda k: self.nodes[k]['s']
        good, bad = [], []
        for (a, b), orig in moved.items():
            thru = bool(self.nodes[a]['crit'] and self.nodes[b]['crit'])         # door-to-door link crosses the doorway
            ok = orig or self.walk(sv(a), sv(b), self.dmask, allow_door=thru) or self.walk(sv(b), sv(a), self.dmask, allow_door=thru)
            (good if ok else bad).append((a, b))
        uf = {}
        def find(x):
            while uf.get(x, x) != x:
                uf[x] = uf.get(uf[x], uf[x]); x = uf[x]
            return x
        for a, b in good:
            uf[find(a)] = find(b)
        kept_bad = []
        for a, b in bad:
            if find(a) != find(b):
                uf[find(a)] = find(b); kept_bad.append((a, b))
        self.merge_log = 'merged %d nodes, %d moved links re-walked, %d dropped, %d kept for connectivity' % (
            len(comp) - len(keep), sum(1 for o in moved.values() if not o), len(bad) - len(kept_bad), len(kept_bad))
        edges = sorted({(min(ids[a], ids[b]), max(ids[a], ids[b])) for a, b in good + kept_bad})
        self.merged = len(comp) - len(keep)
        check_graph(nodes, edges)
        self.last_edges = edges                            # (spkit: patrol routes walk these links)
        data, ne, mx = G.write(nodes, edges, max_nodes=min(2000, ((len(nodes) + 99) // 100) * 100 + 100))
        return data, nodes, ne, mx


def check_graph(nodes, edges, min_edge=512.0):
    """hard limits of the game's graph code (igi2.exe A* at +0x1c6370 and loader)"""
    def need(ok, why):
        if not ok:
            raise ValueError('graph rejected: ' + why)
    pos = {n['id']: n['pos'] for n in nodes}
    need(len(nodes) < 2000, 'A* open/closed arrays hold 2000 node slots (rep stosd 0x7d0)')
    need(sorted(pos) == list(range(1, len(nodes) + 1)), 'node ids must be 1..N')
    deg = {}
    for a, b in edges:
        need(a != b and a in pos and b in pos, 'bad edge %s-%s' % (a, b))
        d = math.dist(pos[a], pos[b])
        need(d >= min_edge, 'edge %d-%d is only %.0f units long: the game A* would loop forever' % (a, b, d))
        deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
    need(max(deg.values(), default=0) <= 64, 'a node holds at most 64 edges (the next field is its path cost)')
    need(len(set(edges)) == len(edges), 'duplicate edges')


def generate(mission, bounds, model_res, cache_dir=None, terrain=None, **build_args):
    """NavGen.build() with an on-disk cache keyed by the tool sources, the obstacle instances and the parameters"""
    import hashlib, os, pickle, terrain as terrain_mod
    lib = meflib.ModelLib(model_res)
    T = terrain or terrain_mod.Terrain(mission.src, mission.stmts)
    nv = NavGen(mission, T, lib, bounds)
    h = hashlib.sha1()
    h.update(open(T.hm_path, 'rb').read())                     # generated terrains: the heights are part of the key
    h.update(repr([(round(x0, 3), round(y0, 3), round(sx, 5), round(sy, 5), round(z0, 3)) for arr, x0, y0, sx, sy, z0 in T.maps]).encode())
    here = os.path.dirname(os.path.abspath(__file__))
    for f in ('navgen.py', 'mef.py', 'terrain.py'):
        src = open(os.path.join(here, f), 'rb').read()
        if f == 'navgen.py':                                 # export()/check_graph() only post-process: keep the cache
            head, rest = src.split(b'    def export(', 1)
            src = head + b'def generate(' + rest.split(b'\ndef generate(', 1)[1]
        h.update(src)
    h.update(repr(sorted((i, ty, mdl, tuple(np.round(p, 2)), tuple(np.round(a, 5))) for i, ty, mdl, p, a in nv.instances())).encode())
    doors = [(i, [lit(x) for x in mission.byid[i].args[3:15]]) for i in mission.find('Door')]
    h.update(repr(doors).encode())
    h.update(repr((bounds, sorted(build_args.items()), CS, AGENT_H, CLIMB, ERODE, LOW_STEP)).encode())
    key = h.hexdigest()[:16]
    path = os.path.join(cache_dir, 'nav_%s.pkl' % key) if cache_dir else None
    nv.max_dev = build_args['max_dev_m'] * 4096.0 if build_args.get('max_dev_m') else None
    if path and os.path.exists(path):
        st = pickle.load(open(path, 'rb'))
        nv.F, nv.nodes, nv.edges, nv.door_pairs, nv.dmask, nv.log = st['F'], st['nodes'], st['edges'], st['door_pairs'], st['dmask'], st['log']
        nv.log = nv.log + ['(cached %s)' % key]
        return nv
    nv.build(**build_args)
    if path:
        os.makedirs(cache_dir, exist_ok=True)
        pickle.dump(dict(F=nv.F, nodes=nv.nodes, edges=nv.edges, door_pairs=nv.door_pairs, dmask=nv.dmask, log=nv.log), open(path, 'wb'))
    return nv
