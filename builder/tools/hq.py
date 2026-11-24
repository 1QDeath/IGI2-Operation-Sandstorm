"""hq - an IGI headquarters scene for an outro (Operation Sirocco, 10-11): the operations room, Anya at her desk,
agents and technicians at work, Jones walking in for the debrief (work/inv/hq/report.md).

The originals stage HQ scenes inside cutscene containers kilometres BELOW the terrain: the operations room ctrl_01_1
(a global COMMON model; its lightmapped copies only exist in location1 levels - here Mission 12's 3892, from the same
source level as the railway), actors as EditBoneObj, cameras with 'time of day' 1000 = light keyframes at Time 1000
(L31 'CS Anya HQ' DirlightKeyframe: pitch -0.5236, yaw 3.7699, colour 0.577/1/0.615). Room frame (yaw 0, metres):
upper floor z -2.68, pit z -3.23 west of the glass rail x ~ 1.0, Anya's desk at x 3.5..5, console rows x 8.5..17.

    H = hq.HQ(K, X, base_m=(x, y, z))       # BEFORE X.finish(): the room copy + Anya's model are merged
    ...
    shots, persistent = H.debrief(lines)    # AFTER: shot dicts for cutscene.add_chain, plus the container with the
                                            # room / extras that spans every HQ shot (add it to the outro box)
"""
import math
import numpy as np
from mission_lib import T, v
import cutscene as CS
import atmos

M = 4096.0
ROOM_SRC = ('location1/level2', 3892)       # lightmapped ctrl_01_1 of the Mission 12 intro (room yaw 2.96 there)
TOD = 1000.0
HQ_FRONT = (0.577, 1.0, 0.615)              # L31 3478 'CS Anya HQ'
HQ_SUN = (-0.523599, 3.769911)


class HQ:
    def __init__(self, K, X, base_m):
        self.K, self.m = K, K.m
        self.B = np.array(base_m, float) * M
        for typ in ('EditBoneObj', 'CutScene', 'EditCamera', 'AmbientArea', 'StatusMessage', 'ConditionalContainer'):
            atmos.ensure_decl(self.m, typ)
        X.models('location2/level1', ['anya_1'])
        self.holder = K.nid()
        self.m.add_child(K._dynamic_root(), T(self.holder, 'ConditionalContainer', '%s HQ room (holder)' % K.PFX, '0', '', ''))
        self.room, _ = X.place(ROOM_SRC[0], ROOM_SRC[1], tuple(self.B), 0.0, self.holder, name='%s IGI operations room' % K.PFX,
                               doors=False, on_ground=False)
        orig = self.m.location_skins
        self.m.location_skins = lambda: orig() | {'anya_1', 'scientist'}    # (validate: cutscene actor skins)

    # ------------------------------------------------------------------ helpers (room frame, metres)
    def P(self, x, y, z):
        return (float(self.B[0] + x * M), float(self.B[1] + y * M), float(self.B[2] + z * M))

    def actor(self, pos_m, gamma, model, anim, loop=True, speed=1.0, weapon='', name='HQ'):
        i = self.K.nid()
        return i, T(i, 'EditBoneObj', '%s %s' % (self.K.PFX, name), *self.P(*pos_m), 0.0, 0.0, float(gamma), bool(loop), True, model,
                    True, weapon, '', anim, float(speed), 0.0)

    def key(self, pos_m, look_m, dur, smooth, fov=1.0, filt=CS.NONE, color=(0.0, 0.0, 0.0), noise=0.0):
        return dict(CS.key(self.P(*pos_m), self.P(*look_m), dur, smooth, fov=fov, filt=filt, color=color, noise=noise), tod=TOD)

    def cameras(self, keys):
        out, prev = [], None
        for k in keys:
            a, g = CS.look(k['pos'], k['tgt'])
            if prev is not None:
                g += 2 * math.pi * round((prev - g) / (2 * math.pi))
            prev = g if k['smooth'] else None
            r, gr, b = (float(c) for c in k['color'])
            out.append(T(self.K.nid(), 'EditCamera', '', *[float(c) for c in k['pos']], round(a, 6), 0.0, round(g, 6), float(k['fov']),
                         float(k['dur']), -1, True, -1, True, bool(k['smooth']), float(k.get('tod', -1.0)), k['filt'],
                         float(k['noise']), r, gr, b, 0.0))
        return out

    def light(self):
        """light keyframes at Time 1000 (the HQ look): neutral ambient, no fog, the L31 green-white key light"""
        made = atmos.add_light_keyframes(self.m, self.K.nid, TOD, preset=dict(amb=(0.36, 0.37, 0.38), fog=(0.3, 0.3, 0.3), dens=0.0,
                                                                              amb_obj=(0.30, 0.31, 0.33), fog_obj=(0.3, 0.3, 0.3),
                                                                              dens_obj=0.0, front=HQ_FRONT, back=(0.0, 0.0, 0.0)),
                                         name='%s HQ look' % self.K.PFX)
        for i in made:
            if self.m.typ(i) == 'DirlightKeyframe':
                self.m.set(i, atmos.DLK_BETA, HQ_SUN[0]); self.m.set(i, atmos.DLK_GAMMA, HQ_SUN[1])
        return made

    # ------------------------------------------------------------------ the debrief
    CAST = [((-1.69, 3.46, -3.23), 5.68, 'igiagent1_1', 'cutscene_talk1'),     # two agents talking in the pit
            ((-1.01, 4.31, -3.23), 2.42, 'scientist', 'cutscene_talk2'),
            ((8.1, -2.6, -2.68), 5.08, 'scientist', 'scientist_kneeling_consolework'),   # at the consoles
            ((10.2, 0.5, -2.68), 5.8, 'scientist', 'scientist_kneeling_consolework'),
            ((14.6, 3.3, -2.68), 3.14, 'scientist', 'scientist_standing_studying'),
            ((2.14, 4.10, -2.68), 0.0, 'igiagent2_1', 'white_stand_look_forward_talk'),
            ((-6.2, -4.6, -3.23), 1.2, 'igiagent3_1', 'stand_look_about')]

    def debrief(self, lines, jones='jones2_1', agent_lines=(), cast=None):
        """lines: dict of (voice def, text, who) for the keys 'title', 'anya1', 'jones1', 'anya2', 'agent', 'anya3', 'jones2'.
        cast = the people in the room [(pos m, gamma, skin, anim)] (default HQ.CAST; 10-23 Sirocco: IT staff, no armed agents)
        -> (shots for cutscene.add_chain, persistent container task)"""
        K, m = self.K, self.m
        self.light()
        # --- the room and the people who are always there (one container across every HQ shot)
        room = m.byid[self.room]
        m.parent[self.room].args.remove(room)
        m.remove(self.holder)
        extras = [room]
        for pos, g, mdl, anim in (cast or self.CAST):
            extras.append(self.actor(pos, g, mdl, anim, name='HQ extra %s' % mdl)[1])
        amb = [T(K.nid(), 'AmbientArea', '%s HQ hum' % K.PFX, *self.P(4.0, 0.0, -1.5), 0.0, 0.0, 0.0, 30.0, 20.0, 12.0, 0.0, 0.0, 0.0,
                 'hqamb', True, True, '', 0.5, False, 0.0),
               T(K.nid(), 'AmbientArea', '%s HQ keyboards' % K.PFX, *self.P(4.0, -0.8, -1.5), 0.0, 0.0, 0.0, 8.0, 8.0, 6.0, 0.0, 0.0, 0.0,
                 'hqkeyb2', True, True, '', 0.5, False, 0.0)]
        extras += amb
        shots = []
        say = lambda cs_id, at, k: self._say(cs_id, at, lines[k])
        # A. establishing: the operations room, high corner, slow push
        ka = [self.key((6.6, -6.1, -0.3), (-3.5, 2.5, -2.4), 7.0, True, fov=1.05),
              self.key((5.6, -5.4, -0.6), (-3.5, 2.5, -2.6), 0.0, False, fov=0.95)]
        ka = [dict(CS.key(ka[0]['pos'], ka[0]['tgt'], 1.5, True, filt=CS.BAND, color=(0, 0, 0), noise=0.0, fov=1.05), tod=TOD),
              dict(CS.key(ka[0]['pos'], ka[0]['tgt'], 0.0, False, filt=CS.BAND, color=(1, 1, 1), noise=0.0, fov=1.05), tod=TOD)] + ka
        shots.append(self._shot('HQ establishing', ka, [], [(0.8, 'title')], lines))
        # B. Anya types (L31 3158/2931/2932 dolly, 1.7 m above the floor, looking down at her hands)
        anya_k, anya_t = self.actor((4.28, -0.85, -2.72), math.pi / 2, 'anya_1', 'anya_at_keyboard', name='HQ Anya typing')
        kb = [self.key((3.57, 0.24, -0.95), (4.70, -1.20, -2.05), 4.5, True, fov=1.0),
              self.key((3.36, -0.45, -0.95), (4.62, -1.32, -2.10), 4.5, True, fov=0.95),
              self.key((3.20, -0.95, -0.95), (4.55, -1.10, -2.05), 0.0, False, fov=0.9)]
        shots.append(self._shot('HQ Anya typing', kb, [anya_t], [(0.5, 'anya1')], lines))
        # C. Jones walks in between the console rows (generic_walk carries him 6.4 m in 8 s, played once)
        jw, jw_t = self.actor((12.9, -0.55, -2.68), math.pi / 2, jones, 'generic_walk', loop=False, name='HQ Jones walks in')
        anya_k2, anya_t2 = self.actor((4.28, -0.85, -2.72), math.pi / 2, 'anya_1', 'anya_at_keyboard', name='HQ Anya (walk-in)')
        kc = [self.key((3.9, 1.3, -1.25), (12.5, -0.6, -1.3), 4.0, True, fov=0.8),
              self.key((3.9, 1.0, -1.25), (7.0, -0.6, -1.5), 0.0, False, fov=0.9)]
        shots.append(self._shot('HQ Jones arrives', kc, [jw_t, anya_t2], [(0.6, 'jones1')], lines))
        # D. the two-shot: Anya turns from the screens and talks, Jones at ease beside her desk
        anya_d, anya_dt = self.actor((4.28, -0.85, -2.72), math.pi / 2, 'anya_1', 'anya_talking', name='HQ Anya talking')
        jd, jd_t = self.actor((6.05, -0.30, -2.68), math.atan2(-(4.28 - 6.05), (-0.85 + 0.30)), jones, 'jones_at_ease_looking_left',
                              name='HQ Jones listening')
        kd = [self.key((2.2, 1.9, -1.05), (5.1, -0.6, -1.55), 9.0, True, fov=0.8),
              self.key((2.4, 1.5, -1.10), (5.1, -0.6, -1.60), 0.0, False, fov=0.72)]
        shots.append(self._shot('HQ debrief', kd, [anya_dt, jd_t], [(0.5, 'anya2'), (None, 'agent')], lines))
        # E. close on Anya, then Jones; fade out on the hook
        anya_e, anya_et = self.actor((4.28, -0.85, -2.72), math.pi / 2, 'anya_1', 'anya_talking', name='HQ Anya (close)')
        je, je_t = self.actor((6.05, -0.30, -2.68), math.atan2(-(4.28 - 6.05), (-0.85 + 0.30)), jones, 'jones_at_ease_looking_left',
                              name='HQ Jones (close)')
        ke = [self.key((2.9, 0.4, -1.15), (4.35, -0.85, -1.45), 7.0, True, fov=0.62),
              self.key((2.9, 0.2, -1.15), (4.35, -0.85, -1.45), 0.0, False, fov=0.58),
              self.key((4.4, 1.6, -1.05), (6.05, -0.30, -1.0), 5.0, True, fov=0.7),
              self.key((4.5, 1.5, -1.05), (6.05, -0.30, -1.0), 2.5, True, fov=0.68, filt=CS.BAND, color=(1, 1, 1)),
              self.key((4.5, 1.5, -1.05), (6.05, -0.30, -1.0), 0.0, False, fov=0.68, filt=CS.BAND, color=(0, 0, 0))]
        shots.append(self._shot('HQ the hook', ke, [anya_et, je_t], [(0.4, 'anya3'), (7.3, 'jones2')], lines))
        first, last = shots[0]['cs'], shots[-1]['cs']
        persist = K.nid()
        pc = T(persist, 'ConditionalContainer', '%s HQ room and staff' % K.PFX,
               '(CutScene_%d.isRun || CutScene_%d.isFinished) && !CutScene_%d.isFinished' % (first, first, last), '', '',
               children=extras)
        return shots, pc

    def _say(self, cs_id, at, line):
        vdef, text, who = line
        if vdef is None:                                    # a title card without voice
            key = '%s_HQ_TITLE' % self.K.PFX
            self.m.add_text('messages', key, text)
            return CS.caption(self.K.nid, cs_id, at, key, secs=4.0, sound=''), 4.0
        name, secs = self.K.vo(vdef, text, who)
        key = vdef.upper()
        self.m.add_text('messages', key, text)
        return CS.caption(self.K.nid, cs_id, at, key, secs=secs + 0.3, sound=name), secs + 0.3

    def _shot(self, name, keys, actors, caps, lines):
        cs = self.K.nid()
        cams = self.cameras(keys)
        dur = sum(k['dur'] for k in keys)
        cs_t = T(cs, 'CutScene', '%s %s' % (self.K.PFX, name), *[float(c) for c in keys[0]['pos']], 0.0, 0.0, 0.0,
                 '!CutScene_%d.isFinished' % cs, '', '', 0.0, 1.0, 0.7, 0.0, 0.0, 0.0, '', '', children=cams)
        tasks_ = [cs_t] + list(actors)
        t_ = 0.0
        for at, k in caps:
            at = t_ + 0.4 if at is None else at
            msg, secs = self._say(cs, at, lines[k])
            tasks_.append(msg)
            t_ = at + secs
        if t_ > dur - 0.3:                                  # the shot lasts until its last line is spoken
            extra = t_ - dur + 0.6
            keys[-2 if len(keys) > 1 and keys[-1]['dur'] == 0 else -1]['dur'] += extra
            cams = self.cameras(keys)
            cs_t.args = [a for a in cs_t.args if not (hasattr(a, 'name') and a.name == 'Task_New')] + cams
            dur = sum(k['dur'] for k in keys)
        return dict(cs=cs, tasks=tasks_, dur=dur, name=name)
