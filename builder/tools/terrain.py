"""Terrain height sampling for an IGI 2 level (heightmaps.res + the level's TerrainMap tasks).

Verified layout (work/research/terrain/terrain.md 3.2: 103 shipped forests and AI graph nodes fit to < 1 cm):
  * heightmapNNN.thm = 52-byte header + W*H float32 heights (row = y, column = x)
  * TerrainMap(index, W, H, Px, Py, z0, WorldW m, WorldH m, ...): samples are CENTRED on (Px, Py):
      x = Px + (i - (W-1)/2) * WorldW*4096/W     y = Py + (j - (H-1)/2) * WorldH*4096/H     z = height + z0
    (10-10: this module used Px - W/2*step and WorldW for both axes - half a cell off, up to 2.7 m on slopes)
"""
import glob, os
import numpy as np
import ilff, igiqvm
from qast import load, tasks, lit


class Terrain:
    def __init__(self, level_dir, stmts=None, hm_path=None):
        """hm_path: an explicit heightmaps.res (a generated terrain); default = the level's own"""
        hp = hm_path or (glob.glob(os.path.join(level_dir, '[Hh][Ee][Ii][Gg][Hh][Tt][Mm][Aa][Pp][Ss]', 'heightmaps.res')) or [None])[0]
        self.hm_path = hp
        _, ch, _ = ilff.read(hp)
        hm = {}
        for n, t, b in ilff.entries(ch):
            if n and n.endswith('.thm'):
                w, h = np.frombuffer(b[44:52], '<u4')
                hm[int(n[-7:-4])] = np.frombuffer(b[52:52 + int(w) * int(h) * 4], dtype='<f4').reshape(int(h), int(w))
        if stmts is None:
            stmts = load(os.path.join(level_dir, 'objects.qvm'))
        tz = None
        for t, d, p in tasks(stmts):
            if lit(t.args[1]) == 'Terrain':
                tz = float(lit(t.args[5]))                   # the engine copies the Terrain z into every TerrainMap
        self.maps = []                      # (array, x0, y0, sx, sy, z0) finest first
        for t, d, p in tasks(stmts):
            if lit(t.args[1]) == 'TerrainMap':
                a = [lit(x) for x in t.args[3:] if not isinstance(x, igiqvm.Call)]
                idx, nw, nh, cx, cy, z0, ww, wh = a[:8]
                arr = hm[idx]
                assert arr.shape == (nh, nw), ('heightmap%03d' % idx, arr.shape, nw, nh)
                sx, sy = ww * 4096.0 / nw, wh * 4096.0 / nh
                self.maps.append((arr, cx - (nw - 1) * sx / 2.0, cy - (nh - 1) * sy / 2.0, sx, sy, tz if tz is not None else z0))
        self.maps.sort(key=lambda m: m[3] * m[4])

    def height(self, x, y):
        """world z of the ground at (x, y) (bilinear, finest map covering the point); nan outside"""
        x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
        out = np.full(np.broadcast(x, y).shape, np.nan)
        for arr, x0, y0, sx, sy, z0 in reversed(self.maps):      # coarse first, finer maps overwrite
            h, w = arr.shape
            i = (x - x0) / sx; j = (y - y0) / sy
            ok = (i >= 0) & (j >= 0) & (i <= w - 1) & (j <= h - 1)
            ic = np.clip(i, 0, w - 1.000001); jc = np.clip(j, 0, h - 1.000001)
            ii = ic.astype(int); jj = jc.astype(int); fi = ic - ii; fj = jc - jj
            z = (arr[jj, ii] * (1 - fi) * (1 - fj) + arr[jj, ii + 1] * fi * (1 - fj) +
                 arr[jj + 1, ii] * (1 - fi) * fj + arr[jj + 1, ii + 1] * fi * fj) + z0
            out = np.where(ok, z, out)
        return out if out.shape else float(out)
