"""recon - flicker-safe 'overhead' cutscene keys: a recon-drone feed and photo-snap frames (shared, additive; Joyride 10-31).

Why (owner 10-31: 'top-down / high camera shots flicker roads, buildings and objects'; work/hero/sky_render.md has the engine
facts): a camera 350-600 m over the ground (our satellite shots, the HALO '3rd person towards ground' clones) sits where
  * the engine's fixed 0.1 m near plane leaves a 24-bit depth step of d^2 / (0.1 m * 2^24) = 0.07 m at 350 m, 0.19 m at 560 m:
    the same size as a road deck (+0.15-0.20 m), a pad (+0.2 m) or a flat roof's trim -> they z-fight from frame to frame;
  * the terrain is tessellated per frame from the view (E *= sx^0.4) and coarsely at altitude: as the camera moves or its FOV
    creeps, the ground mesh rises over roads / pads in some frames and not in others;
  * every model's LOD is chosen per frame from distance * FOV factor: a FOV creep walks models across LOD thresholds -> popping.
The originals never hold a high camera on the base: L11's 1 km shot looks at falling Jones, the map mostly culled, its water
hidden 'to avoid Z-fighting' (CC 2251). This module keeps the camera LOW instead: a drone 70-160 m over the ground looking down at
~35-55 deg (slant 100-250 m: depth step <= 0.04 m, fine terrain, full LODs), constant FOV (no creep), a straight steady track.

    import recon
    keys = recon.drone_keys(key, ground, a, b, dur, alt_m=110.0, look_ahead_m=90.0, burst=0.25)     # atmos.key as `key`
    keys = recon.photo_keys(key, [(cam, tgt), ...], dur)      # still frames, each opened by a 0.08 s white flash
    sounds: COMMON 'camera_stop' (shutter click), 'zoom_01' (lens), 'noise_04' (feed acquire) - one-shots via sound cues
Filters (atmos): drone feed = LINE colour (0, 0.12, 0) noise 0.06 (a faint scan-line video look, like the originals' camera POVs);
photos = BAND (0.86, 0.88, 0.84) still + BAND (2.4, 2.4, 2.4) flash. Both read the light at `tod` (-1 = the in-game light).
"""
import math

M = 4096.0
LINE, BAND = 'CAMERAFILTER_TYPE_LINE', 'CAMERAFILTER_TYPE_BAND'
FEED = dict(filt=LINE, color=(0.0, 0.12, 0.0), noise=0.06)
PHOTO = dict(filt=BAND, color=(0.86, 0.88, 0.84), noise=0.0)
FLASH = dict(filt=BAND, color=(2.4, 2.4, 2.4), noise=0.0)
MAX_SLANT_M = 260.0                 # the flicker-safe limit asserted below (depth step <= 0.04 m)


def _lerp(a, b, f):
    return tuple(float(a[k] + (b[k] - a[k]) * f) for k in range(3))


def drone_keys(key, ground, a, b, dur, alt_m=110.0, look_ahead_m=90.0, fov=0.8, burst=0.25, tod=-1.0, shake=0.0008):
    """a straight drone pass from a to b (world units, x/y; z from `ground(x, y)` units) alt_m over the ground under it, looking
    look_ahead_m ahead along the track at the ground: LINE burst -> one smooth key -> a duplicate end pose (no spline bend)"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L

    def pose(p):
        cam = (p[0], p[1], ground(p[0], p[1]) + alt_m * M)
        tx, ty = p[0] + ux * look_ahead_m * M, p[1] + uy * look_ahead_m * M
        tgt = (tx, ty, ground(tx, ty))
        slant = math.dist(cam, tgt) / M
        assert slant <= MAX_SLANT_M, 'recon.drone_keys: slant %.0f m > %.0f m (the flicker band)' % (slant, MAX_SLANT_M)
        return cam, tgt
    c0, t0 = pose(a)
    c1, t1 = pose(b)
    ks = []
    if burst:
        ks.append(key(c0, t0, burst, False, fov=fov, filt=LINE, color=(0.0, 0.0, 0.0), noise=1.0, shake=0.01, tod=tod))
    ks += [key(c0, t0, dur - burst, True, fov=fov, shake=shake, tod=tod, **FEED),
           key(c1, t1, 0.0, False, fov=fov, shake=shake, tod=tod, **FEED),
           key(c1, t1, 0.0, False, fov=fov, shake=shake, tod=tod, **FEED)]
    return ks


def photo_keys(key, frames, dur, fov=0.55, flash_s=0.08, tod=-1.0):
    """still photographs (hard cuts, no motion): frames = [(cam, tgt), ...] each held dur/len(frames), opened by a white flash;
    -> (keys, [start times of the frames]) - put a 'camera_stop' cue at each start"""
    hold = dur / float(len(frames))
    ks, at = [], []
    for k, (cam, tgt) in enumerate(frames):
        slant = math.dist(cam, tgt) / M
        assert slant <= MAX_SLANT_M, 'recon.photo_keys: slant %.0f m > %.0f m' % (slant, MAX_SLANT_M)
        at.append(round(k * hold, 3))
        ks.append(key(cam, tgt, flash_s, False, fov=fov, tod=tod, **FLASH))
        ks.append(key(cam, tgt, hold - flash_s, False, fov=fov, tod=tod, **PHOTO))
    ks.append(dict(ks[-1], dur=0.0))
    return ks, at
