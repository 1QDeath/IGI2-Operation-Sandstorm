"""lightcal - light calibration for transplanted prefabs (owner A4, 10-13 playtest: 'some crates, boxes and buildings
are too bright, others too dark; Cedar Shadow is far too dark overall, Frostbite too bright').

Root cause (measured on the built overlays, 10-13): a transplanted building keeps the per-instance lightmaps (.olm)
baked in ITS source level under THAT level's sun - in one mission the instances' lightmap means run from 10 to 131 of
255 (Frostbite: 273 instances, 10..131; Cedar Shadow: 172, 18..150). The engine draws a lightmapped model as
texture x lightmap, the terrain as texture x terrain light map (.tlm) - so next to each other on the same ground
one building glows and the next one sits in a shadow that is not there. Vertex-lit models (MP buildings, props)
are lit by the in-game GlobalLightKeyframe object ambient + the DirlightKeyframe sun instead.

The repeatable step (every builder calls it after X.finish() / F.write(), before K.write()):

    import lightcal
    rep = lightcal.calibrate(overlay_dir, target=None, floor=0.55, ceiling=1.35, tint=(1, 1, 1))

* target None = the level's own terrain light (mean of the terrain .tlm over the play area, from the overlay's
  heightmaps.res) - a building then carries the same light as the ground it stands on, which is what the eye expects.
  A number = that lightmap mean (0..255) instead (night levels: see NIGHT_TARGETS).
* every instance's .olm set is scaled (pixels only; the 112-byte header the engine checks against the mesh is kept)
  so that its mean becomes target, clamped to floor*target..ceiling*target of its own contrast - a dark cellar stays
  darker than a lit porch, but no instance is 10x another.
* tint = per-channel BGR multiplier (moonlight blue, sodium orange).

    lightcal.report(overlay_dir)                 # the per-instance means before / after (also written to lightcal.txt)
    lightcal.probe_plan(points)                  # -> a list of (name, pos, look) for dbgrun 'probe' screenshots
    lightcal.measure(png, boxes)                 # mean luminance of screen boxes of an in-game screenshot

In-game check (tools/dbgrun.py 'probe' scenario): stand at the probe spots, screenshot, compare the luminance of a
transplanted wall, a native (MP) wall and the ground next to each other: they should be within ~25 % of each other.
"""
import os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

OLM_RE = re.compile(r'/(\d{4,})[a-z]?_(\d{4})_(\d)\.olm$', re.I)
# lightmap means (0..255) that read right for each preset family, measured against the terrain light of the shipped
# levels: location1 snow day (L13) terrain tlm ~95, night (L11) ~38, dusk (L33) ~70
NIGHT_TARGETS = dict(night=40.0, moonlit=46.0, dusk=70.0, snow_day=92.0, clear_day=96.0, rain=72.0, fog=70.0, dust=80.0)


def olm_instances(path):
    """{task id: [(name, mean, w, h)]} of a lightmaps.res"""
    import prefab
    R = prefab.Res(path)
    inst = {}
    for nm in R.names():
        mm = OLM_RE.search(nm)
        if not mm:
            continue
        b = R.get(nm)
        w, h = struct.unpack_from('<HH', b, 108)
        px = np.frombuffer(b, 'u1', w * h * 4, 112).reshape(-1, 4)[:, :3]
        inst.setdefault(int(mm.group(1)), []).append((nm, float(px.mean()), w, h))
    return R, inst


def terrain_light_mean(overlay_dir, box_m=None):
    """mean of the terrain light map (.tlm, BGR 0..255) of the overlay's heightmaps (finest map), inside box_m
    (x0, y0, x1, y1 metres) or everywhere"""
    import terrain_synth as ts
    hp = os.path.join(overlay_dir, 'heightmaps', 'heightmaps.res')
    if not os.path.exists(hp):
        return None
    res = ts.HeightmapRes.read(hp)
    vals = []
    for idx in res.indices():
        g = res.get(idx, 'tlm')
        if g is None:
            continue
        a = np.asarray(g.data, float)
        if a.ndim == 3 and a.shape[2] >= 3:
            vals.append((idx, float(a[:, :, :3].mean()), a.shape[0] * a.shape[1]))
    if not vals:
        return None
    vals.sort(key=lambda t: t[2], reverse=True)                     # the finest (most cells) map = the play area
    return vals[0][1]


def calibrate(overlay_dir, target=None, floor=0.55, ceiling=1.35, tint=(1.0, 1.0, 1.0), only=None, skip=(), contrast=0.35, log=print):
    """scale every instance's lightmaps in <overlay>/lightmaps/lightmaps.res toward `target` (see module doc):
    new mean = target * (mean / target) ** contrast (0 = every instance exactly the target, 1 = untouched), clamped to
    floor*target .. ceiling*target. only = instance ids to touch (None = all), skip = ids to leave alone.
    -> dict(target, before, after)"""
    path = os.path.join(overlay_dir, 'lightmaps', 'lightmaps.res')
    if not os.path.exists(path):
        log('lightcal: no lightmaps in %s' % overlay_dir)
        return None
    if target is None:
        target = terrain_light_mean(overlay_dir)
        assert target is not None, 'lightcal: no terrain light map to match - give target='
    R, inst = olm_instances(path)
    before, after = {}, {}
    tint = np.asarray(tint, float)
    for tid, names in inst.items():
        if (only is not None and tid not in only) or tid in skip:
            continue
        mean = float(np.mean([m for _, m, _, _ in names]))        # (every .olm of an instance: one bake)
        before[tid] = mean
        want = target * (max(mean, 1.0) / target) ** contrast
        want = float(np.clip(want, floor * target, ceiling * target))
        k = want / max(mean, 1.0)
        for nm, m_, w, h in names:
            i = R.index[nm]
            b = bytearray(R.chunks[i][1])
            a = np.frombuffer(bytes(b[112:112 + w * h * 4]), 'u1').reshape(-1, 4).astype(float)
            a[:, :3] = np.clip(a[:, :3] * k * tint, 0, 255)
            b[112:112 + w * h * 4] = np.round(a).astype('u1').tobytes()
            R.chunks[i] = (R.chunks[i][0], bytes(b), R.chunks[i][2])
        after[tid] = mean * k
    open(path, 'wb').write(R.data())
    rep = dict(target=float(target), before=before, after=after, n=len(before))
    if before:
        log('lightcal: %d instances -> target %.0f (terrain light); means %.0f..%.0f -> %.0f..%.0f, tint %s' % (
            len(before), target, min(before.values()), max(before.values()), min(after.values()), max(after.values()), tuple(tint)))
    with open(os.path.join(overlay_dir, 'lightcal.txt'), 'w') as f:
        f.write('target %.1f\n' % target)
        for tid in sorted(before):
            f.write('%d %.1f -> %.1f\n' % (tid, before[tid], after[tid]))
    return rep


def scale_terrain_light(overlay_dir, k, tint=(1.0, 1.0, 1.0), log=print):
    """multiply every terrain light map (.tlm, BGR) in <overlay>/heightmaps/heightmaps.res by k * tint (BGR order).
    -> (mean before, mean after) of the finest map"""
    import terrain_synth as ts
    hp = os.path.join(overlay_dir, 'heightmaps', 'heightmaps.res')
    res = ts.HeightmapRes.read(hp)
    b0 = terrain_light_mean(overlay_dir)
    mul = np.asarray(tint, float) * float(k)
    for idx in res.indices():
        g = res.get(idx, 'tlm')
        if g is None:
            continue
        a = g.data.astype(float)
        a[:, :, :3] = np.clip(a[:, :, :3] * mul[None, None, :], 0, 255)
        g.data = np.round(a).astype(np.uint8)
    res.write(hp)
    b1 = terrain_light_mean(overlay_dir)
    log('lightcal: terrain light x%.2f tint %s: mean %.0f -> %.0f' % (k, tuple(tint), b0, b1))
    return b0, b1


def level_texture(path, target_mean=172.0, tint=(1.0, 1.0, 1.0)):
    """scale a terrain texture (jpg) so its mean brightness is target_mean (0..255): the shipped snow is 166-193,
    Frostbite's generated snow was 219 (owner A3/A4 10-13: map screen and ground too bright). In place; idempotent."""
    from PIL import Image
    a = np.asarray(Image.open(path).convert('RGB'), float)
    k = target_mean / max(1.0, float(a.mean()))
    if abs(k - 1.0) < 0.01 and tint == (1.0, 1.0, 1.0):
        return float(a.mean())
    a = np.clip(a * k * np.asarray(tint, float)[None, None, :], 0, 255)
    Image.fromarray(a.astype('u1')).save(path, quality=92)
    return float(a.mean())


def report(overlay_dir):
    path = os.path.join(overlay_dir, 'lightmaps', 'lightmaps.res')
    R, inst = olm_instances(path)
    means = sorted((float(np.mean([m for _, m, _, _ in v])), k) for k, v in inst.items())
    t = terrain_light_mean(overlay_dir)
    print('%s: %d instances, lightmap means %.0f..%.0f (median %.0f), terrain light %s' % (
        overlay_dir, len(means), means[0][0], means[-1][0], means[len(means) // 2][0], None if t is None else round(t)))
    return means, t


def measure(png, boxes):
    """mean luminance (0..255) of screen boxes [(name, x0, y0, x1, y1)] of a screenshot"""
    from PIL import Image
    im = np.asarray(Image.open(png).convert('RGB'), float)
    out = {}
    for name, x0, y0, x1, y1 in boxes:
        a = im[y0:y1, x0:x1]
        out[name] = float((0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]).mean())
    return out


if __name__ == '__main__':
    for d in sys.argv[1:]:
        report(d)
