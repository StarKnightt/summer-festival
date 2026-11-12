"""The five variants, assembled from body.py parts."""
import math

import numpy as np

from .body import Body
from .geo import TAU, X, Y, Z, lerp, loft, norm, orient_out, ring, rot, smooth, sweep
from .rig import leg_w, mix, side_of, torso_w

T_ = Body.Tube


def _theta_of(path):
    """theta(z) for a lapel path [(theta, z) ...] with z decreasing as theta grows."""
    th = np.array([p[0] for p in path])
    zz = np.array([p[1] for p in path])
    o = np.argsort(zz)
    return lambda z: float(np.interp(z, zz[o], th[o]))


def lapels(b, T, top_z, v_z, end_z, width, mat, wf, cont_left=True, extra_left=None, col=None, open_th=0.50):
    """Collar bands: round the back of the neck at collar height, then down both fronts to a V at
    the chest centre. The wearer's left panel (+X, theta < pi) overlaps the right one. Returns the
    descending (theta, z) points of the left band (for the V patch)."""
    th_n = math.pi - open_th
    back = [(th_n * t, top_z) for t in np.linspace(0, 1, 10)]
    down = [(lerp(th_n, math.pi - 0.012, t ** 1.25), lerp(top_z, v_z, t)) for t in np.linspace(0, 1, 12)[1:]]
    left = back + down
    right = [(TAU - th, z) for th, z in left]
    b.surface_strip(T, right, width, mat, wf, off=0.0055, C=col)
    if cont_left:
        tail = extra_left or [(math.pi + 0.18, v_z - 0.035), (math.pi + 0.42, end_z)]
        k0 = left[-1]
        ext = []
        for (th1, z1) in tail:
            for t in np.linspace(0, 1, 5)[1:]:
                ext.append((lerp(k0[0], th1, t), lerp(k0[1], z1, t)))
            k0 = (th1, z1)
        left = left + ext
    b.surface_strip(T, left, width, mat, wf, off=0.0072, C=col)
    return [(th_n, top_z)] + down


def v_patch(b, T, pts, z_top, z_bot, mat, wf):
    thL = _theta_of(pts)
    b.surface_patch(T, thL, lambda z: TAU - thL(z), min(z_top, pts[0][1] - 0.002), max(z_bot, pts[-1][1]), mat, wf)


def sidelocks(b, length, r):
    J, P = b.J, b.P
    hh = P["head"]
    c = b.head_center()
    for sg in (1, -1):
        a = c + np.array([sg * P["hw"] * hh * 0.47, -P["hd"] * hh * 0.30, 0.02 * hh / 0.235])
        path = [a, a + np.array([sg * 0.008, -0.006, -length * 0.5]), a + np.array([sg * 0.004, -0.010, -length])]
        V, F, U, RI = sweep(np.array(path), np.array([r, r * 0.8, r * 0.25]), 7, r2=np.array([r * 0.55, r * 0.45, r * 0.2]))
        b.mb.add(V, F, "hair", {"head": 1.0}, tag="sidelock")


def spikes_fn(n, amp, lo=0.0):
    return lambda phi, t: amp * np.clip(np.sin(phi * n) * 0.5 + 0.5, 0, 1) ** 3 * (t > lo) * np.sin(math.pi * t)


def frontness(phi):
    return (1 - np.cos(phi)) / 2


def hair_bound(back, side, front, fringe=0.0, nfr=7, frontcut=0.72):
    def f(phi):
        fr = frontness(phi)
        lam = np.interp(fr, [0, 0.5, 0.78, 1.0], [back, side, lerp(side, front, 0.75), front])
        if fringe:
            sp = np.abs(np.sin((phi - math.pi) * nfr)) ** 0.7
            lam = lam - fringe * (1 - sp) * smooth(frontcut, frontcut + 0.12, fr)
        return lam
    return f


def fan(b):
    """Round uchiwa fan held in the right hand (weighted to hand_R)."""
    J, P = b.J, b.P
    side = "R"
    d = J["d0_R"]
    s = np.array([0, -1.0, 0])
    n = -np.cross(d, s)
    n = n / np.linalg.norm(n)
    wr = J["wr_R"]
    g = wr + d * P["hand"] * 0.45 + n * 0.012
    a = norm(s * math.cos(math.radians(40)) + d * math.sin(math.radians(40)))
    h0, h1 = g - a * 0.035, g + a * 0.115
    V, F, U, RI = sweep(np.array([h0, lerp(h0, h1, 0.5), h1]), 0.0065, 6)
    b.mb.add(V, F, "wood_geta", {"hand_R": 1.0}, tag="fan")
    R = 0.115
    c = h1 + a * (R * 0.92)
    e = norm(np.cross(n, a))
    V, F, U = ellipsoid_flat(c, a, e, n, R, R * 0.96, 0.0045)
    dist = np.sqrt((((V - c) @ a) / R) ** 2 + (((V - c) @ e) / R) ** 2)
    C = np.ones((len(V), 3))
    C[dist > 0.86] = 0.62
    C[(dist > 0.3) & (dist < 0.45)] = [1.0, 0.72, 0.72]
    b.mb.add(V, F, "cloth_accent", {"hand_R": 1.0}, C=C, tag="fan")
    b.meta["fan"] = dict(center=c.tolist(), radius=R)


def ellipsoid_flat(c, a, e, n, ra, re, rn):
    from .geo import ellipsoid
    return ellipsoid(c, (a, e, n), (ra, re, rn), 18, 4)


# ================================================================ woman

def woman(b):
    J, P, lk, bw = b.J, b.P, b.lk, b.bw
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = J["ankle_z"] + 0.048 * lk
    T = T_([
        (nb + 0.024, 0.048, 0.044, 0.052, 0.006, 2.0),
        (sz + 0.004, 0.078, 0.062, 0.066, 0.004, 2.0),
        (sz - 0.026, 0.128, 0.080, 0.078, 0.0, 2.3),
        (sz - 0.068, 0.146, 0.096, 0.084, 0.0, 2.3),
        (ch + 0.03, 0.138, 0.106, 0.086, -0.004, 2.2),
        (ch - 0.06, 0.122, 0.092, 0.084, 0.0, 2.2),
        (sp, 0.120, 0.088, 0.088, 0.0, 2.2),
        (hip + 0.04, 0.140, 0.098, 0.112, 0.0, 2.2),
        (hip - 0.10, 0.142, 0.102, 0.110, 0.0, 2.2),
        (kn, 0.134, 0.100, 0.102, 0.0, 2.2),
        (hem, 0.126, 0.100, 0.098, -0.004, 2.2),
    ])
    zs = [r[0] for r in T.r]
    wf = b.robe_weights(hip + 0.02, hem)
    b.tube_mesh(T, zs, "cloth_main", wf, n=24, fold_top=(0.014, 0.03), fold_bot=(0.012, 0.03), tag="robe")
    tw = lambda p: torso_w(J, p)
    pts = lapels(b, T, nb + 0.018, ch + 0.035, ch - 0.02, 0.028, "cloth_accent", tw)
    v_patch(b, T, pts, nb, ch + 0.035, "skin", tw)
    # obi + cord + bow
    z0, z1 = sp - 0.01, ch - 0.005
    b.obi_band(T, z0, z1, 0.013, "cloth_accent", tw)
    zm = (z0 + z1) / 2
    th = np.linspace(0, TAU, 19)[:-1]
    path = T.point(zm, th, off=0.0185)
    V, F, U, RI = sweep(path, 0.0055, 5, closed_path=True)
    b.mb.add(V, F, "cloth_dark", tw, tag="obijime")
    B = T.point(zm + 0.01, 0.0, off=0.03)
    for sg in (1, -1):
        R = rot(Y, -sg * 14)
        b.blob(B + np.array([sg * 0.068, 0.010, 0.012]), (R @ X, Y, R @ Z), (0.064, 0.022, 0.040), "cloth_accent", tw, nu=9, nv=5, tag="bow")
        R2 = rot(Y, sg * 8)
        b.blob(B + np.array([sg * 0.024, 0.004, -0.080]), (R2 @ X, Y, R2 @ Z), (0.024, 0.010, 0.066), "cloth_accent", tw, nu=7, nv=4, tag="bow")
    b.blob(B + np.array([0, 0.016, 0.004]), (X, Y, Z), (0.026, 0.020, 0.034), "cloth_accent", tw, nu=7, nv=4, C=np.full(3, 0.85), tag="bow")
    for side in ("L", "R"):
        b.sleeve(side, -0.012, P["ua"] + P["fa"] * 0.80, [0.054, 0.062, 0.064, 0.066, 0.070], pouch=0.20 * lk)
        b.arm_skin(side, P["ua"] + P["fa"] * 0.55, P["ua"] + P["fa"] + 0.012, 0.027, 0.023)
        b.hand(side)
        b.leg_skin(side, kn - 0.04, J["ankle_z"] + 0.012, 0.042, 0.029)
        b.foot(side)
        b.geta(side, "cloth_accent")
    b.neck(0.041)
    b.head_face("far")


# ================================================================ man (dark yukata, narrow obi)

def man(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = J["ankle_z"] + 0.055 * lk
    T = T_([
        (nb + 0.026, 0.058, 0.052, 0.060, 0.006, 2.0),
        (sz + 0.004, 0.094, 0.072, 0.076, 0.004, 2.0),
        (sz - 0.028, 0.158, 0.094, 0.090, 0.0, 2.4),
        (sz - 0.078, 0.178, 0.110, 0.098, 0.0, 2.4),
        (ch, 0.168, 0.112, 0.098, -0.004, 2.3),
        (sp, 0.150, 0.104, 0.098, 0.0, 2.3),
        (hip + 0.05, 0.152, 0.104, 0.112, 0.0, 2.3),
        (hip - 0.10, 0.155, 0.108, 0.114, 0.0, 2.3),
        (kn, 0.150, 0.108, 0.108, 0.0, 2.3),
        (hem, 0.146, 0.108, 0.106, -0.004, 2.3),
    ])
    zs = [r[0] for r in T.r]
    wf = b.robe_weights(hip + 0.03, hem, sidew=0.055)
    b.tube_mesh(T, zs, "cloth_main", wf, n=24, fold_top=(0.014, 0.03), fold_bot=(0.012, 0.03), tag="robe")
    tw = lambda p: torso_w(J, p)
    pts = lapels(b, T, nb + 0.02, ch + 0.045, hip + 0.05, 0.032, "cloth_main", tw, col=np.full(3, 0.72),
                 extra_left=[(math.pi + 0.2, ch - 0.02), (math.pi + 0.5, hip + 0.06)], open_th=0.46)
    v_patch(b, T, pts, nb, ch + 0.045, "skin", tw)
    # narrow kaku-obi at the hips with a flat knot at the back
    z0, z1 = hip + 0.035, hip + 0.10
    b.obi_band(T, z0, z1, 0.011, "cloth_accent", tw)
    B = T.point((z0 + z1) / 2, 0.0, off=0.02)
    b.blob(B + np.array([0.0, 0.005, 0.0]), (X, Y, Z), (0.07, 0.014, 0.030), "cloth_accent", tw, p=3.0, C=np.full(3, 0.85), tag="knot")
    b.blob(B + np.array([0.035, 0.008, -0.03]), (rot(Y, 30) @ X, Y, rot(Y, 30) @ Z), (0.016, 0.010, 0.05), "cloth_accent", tw, tag="knot")
    for side in ("L", "R"):
        b.sleeve(side, -0.012, P["ua"] + P["fa"] * 0.72, [0.060, 0.070, 0.07, 0.072, 0.076], pouch=0.10 * lk)
        b.arm_skin(side, P["ua"] + P["fa"] * 0.45, P["ua"] + P["fa"] + 0.012, 0.034, 0.028)
        b.hand(side)
        b.leg_skin(side, kn - 0.04, J["ankle_z"] + 0.012, 0.050, 0.034)
        b.foot(side)
        b.geta(side, "cloth_dark")
    b.neck(0.050)
    b.head_face("far")


# ================================================================ kid (jinbei + shorts)

def kid(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = hip - 0.035
    T = T_([
        (nb + 0.018, 0.042, 0.040, 0.044, 0.004, 2.0),
        (sz + 0.002, 0.062, 0.052, 0.056, 0.003, 2.0),
        (sz - 0.022, 0.100, 0.068, 0.066, 0.0, 2.4),
        (ch, 0.112, 0.080, 0.072, 0.0, 2.4),
        (sp, 0.110, 0.080, 0.074, 0.0, 2.4),
        (hip + 0.02, 0.116, 0.082, 0.080, 0.0, 2.4),
        (hem, 0.120, 0.086, 0.084, 0.0, 2.4),
    ])
    zs = [r[0] for r in T.r]

    def wtop(p):
        w = torso_w(J, p)
        for side, sg in (("L", 1), ("R", -1)):
            k = float(smooth(0.5 * P["shw"], 0.95 * P["shw"], sg * p[0])) * float(smooth(ch, sz, p[2])) * 0.5
            if k > 0:
                w = mix((1 - k, w), (k, {f"shoulder_{side}": 1.0}))
        if p[2] < hip + 0.02:
            sL = side_of(p[0], 0.04)
            k = float(smooth(hip + 0.02, hem, p[2])) * 0.35
            w = mix((1 - k, w), (k, {"thigh_L": sL, "thigh_R": 1 - sL}))
        return w
    b.tube_mesh(T, zs, "cloth_main", wtop, n=22, fold_top=(0.010, 0.02), fold_bot=(0.010, 0.02), tag="jinbei")
    tw = lambda p: torso_w(J, p)
    pts = lapels(b, T, nb + 0.014, ch - 0.005, hem + 0.01, 0.020, "cloth_accent", tw,
                 extra_left=[(math.pi + 0.25, ch - 0.04), (math.pi + 0.55, hem + 0.012)], open_th=0.55)
    v_patch(b, T, pts, nb, ch, "skin", tw)
    # little ties at the right side
    tp = T.point(ch - 0.035, math.pi + 0.62, off=0.008)
    for dv in (np.array([-0.012, -0.004, -0.035]), np.array([0.004, -0.006, -0.04])):
        V, F, U, RI = sweep(np.array([tp, tp + dv * 0.5, tp + dv]), 0.0035, 5)
        b.mb.add(V, F, "cloth_accent", tw, tag="tie")
    # shorts (pelvis + two legs)
    S = T_([(hip + 0.055, 0.100, 0.074, 0.074, 0.0, 2.3), (hip - 0.0, 0.110, 0.080, 0.084, 0.0, 2.3),
            (hip - 0.045, 0.100, 0.074, 0.078, 0.0, 2.3)])
    b.tube_mesh(S, [r[0] for r in S.r], "cloth_dark", b.robe_weights(hip + 0.03, hip - 0.045, sidew=0.03, shin_max=0.0, hips_keep=0.4),
                n=20, uv=False, tag="shorts")
    for side, sg in (("L", 1), ("R", -1)):
        x = sg * P["hipw"] * 1.08
        zz = [hip + 0.01, hip - 0.06, kn + 0.045, kn + 0.012]
        rr = [0.060, 0.057, 0.054, 0.056]
        rings = [ring([x, 0.0, z], X, Y, r, r * 0.98) for z, r in zip(zz, rr)]
        rings.append(ring([x, 0.0, zz[-1] + 0.02], X, Y, rr[-1] * 0.8, rr[-1] * 0.8))
        V, F, U, RI, TH = loft(rings, 14)
        F = orient_out(V, F, lambda q: np.array([x, 0.0, q[2]]))
        b.mb.add(V, F, "cloth_dark", lambda p, s=side: leg_w(J, s, p, bw=0.05), tag="shorts")
        b.sleeve(side, -0.010, P["ua"] * 0.80, [0.044, 0.050, 0.050, 0.052], p=2.4)
        b.arm_skin(side, P["ua"] * 0.35, P["ua"] + P["fa"] + 0.008, 0.026, 0.019)
        b.hand(side)
        b.leg_skin(side, kn + 0.05, J["ankle_z"] + 0.01, 0.032, 0.022)
        b.foot(side)
        b.geta(side, "cloth_accent")
    b.neck(0.034)
    b.head_face("far")


# ================================================================ keeper (happi, pants, apron, headband, towel)

def keeper(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = hip - 0.10 * lk
    T = T_([
        (nb + 0.024, 0.056, 0.052, 0.060, 0.006, 2.0),
        (sz + 0.004, 0.094, 0.072, 0.076, 0.004, 2.0),
        (sz - 0.030, 0.160, 0.098, 0.090, 0.0, 2.5),
        (ch + 0.03, 0.172, 0.118, 0.100, -0.004, 2.6),
        (sp, 0.162, 0.112, 0.102, 0.0, 2.6),
        (hip + 0.04, 0.166, 0.114, 0.116, 0.0, 2.6),
        (hem, 0.176, 0.122, 0.122, 0.0, 2.6),
    ])
    zs = [r[0] for r in T.r]
    wf = b.robe_weights(hip + 0.02, hem - 0.25, sidew=0.06, shin_max=0.0, hips_keep=0.5)
    b.tube_mesh(T, zs, "cloth_main", wf, n=24, fold_top=(0.012, 0.025), fold_bot=(0.012, 0.03), tag="happi")
    tw = lambda p: torso_w(J, p)
    pts = lapels(b, T, nb + 0.018, ch + 0.01, hem, 0.045, "cloth_accent", tw,
                 extra_left=[(math.pi - 0.03, ch - 0.06), (math.pi - 0.07, hip), (math.pi - 0.09, hem + 0.006)], open_th=0.62)
    v_patch(b, T, pts, nb, ch + 0.01, "cloth_dark", tw)
    # sash
    z0, z1 = sp - 0.02, sp + 0.045
    b.obi_band(T, z0, z1, 0.012, "cloth_accent", tw, C=np.full(3, 0.92))
    # apron (front, waist to knee)
    A = T_([(z0, 0.162 + 0.02, 0.112 + 0.02, 0.10, 0.0, 2.6), (hip + 0.04, 0.17 + 0.022, 0.114 + 0.024, 0.11, 0.0, 2.6),
            (hem - 0.02, 0.17, 0.13, 0.12, 0.0, 2.6), (kn - 0.03, 0.165, 0.13, 0.12, 0.0, 2.6)])
    rings = [A.ringfn(z) for z in [r[0] for r in A.r]]
    V, F, U, RI, TH = loft(rings, 14, th0=math.pi - 1.1, th1=math.pi + 1.1)
    F = orient_out(V, F, lambda q: np.array([0, A.params(q[2])[4], q[2]]))
    aw = b.robe_weights(hip + 0.0, kn - 0.03, sidew=0.08, shin_max=0.0, hips_keep=0.3)
    b.mb.add(V, F, "cloth_dark", aw, tag="apron")
    # pants (momohiki): pelvis + legs, a darker shade of cloth_dark
    pc = np.full(3, 0.62)
    S = T_([(sp, 0.150, 0.100, 0.096, 0.0, 2.3), (hip, 0.150, 0.104, 0.110, 0.0, 2.3), (hip - 0.06, 0.12, 0.09, 0.096, 0.0, 2.3)])
    b.tube_mesh(S, [r[0] for r in S.r], "cloth_dark", b.robe_weights(hip + 0.02, hip - 0.06, sidew=0.04, shin_max=0.0, hips_keep=0.4),
                n=20, uv=False, C=pc, tag="pants")
    for side in ("L", "R"):
        b.leg_skin(side, hip + 0.01, J["ankle_z"] + 0.06, 0.072, 0.044, mat="cloth_dark", n=12, C=pc)
        b.sleeve(side, -0.012, P["ua"] + P["fa"] * 0.30, [0.064, 0.082, 0.088, 0.092], p=2.6)
        b.arm_skin(side, P["ua"] * 0.6, P["ua"] + P["fa"] + 0.01, 0.040, 0.031, mat="cloth_dark")
        b.hand(side)
        b.tabi(side)
    b.neck(0.050)
    b.head_face("far")
    # twisted headband (hachimaki) + knot at the front right
    c = b.head_center()
    phi = np.linspace(0, TAU, 25)[:-1]
    lam = np.interp(frontness(phi), [0, 1], [0.42, 0.30])
    D = np.stack([np.sin(phi) * np.cos(lam), np.cos(phi) * np.cos(lam), np.sin(lam)], 1)
    path = c + (b.head_point(D) - c) * 1.075
    tw_ang = phi * 6
    V, F, U, RI = sweep(path, 0.011, 7, closed_path=True, r2=0.0075, twist=np.append(tw_ang, tw_ang[0]))
    ang = np.arctan2(V[:, 1] - c[1], V[:, 0] - c[0])
    Cc = np.where((np.sin(ang * 6 + V[:, 2] * 400) > 0)[:, None], np.ones(3), np.array([0.82, 0.82, 0.82]))
    b.mb.add(V, F, "cloth_accent", {"head": 1.0}, C=Cc, tag="hachimaki")
    kp = path[int(len(path) * 0.62)]
    out = norm(kp - c)
    b.blob(kp + out * 0.008, (X, Y, Z), (0.017, 0.017, 0.015), "cloth_accent", {"head": 1.0}, tag="knot")
    for dv in (np.array([-0.02, -0.02, 0.05]), np.array([-0.04, -0.005, 0.03])):
        q = kp + out * 0.01
        V, F, U, RI = sweep(np.array([q, q + dv * 0.5, q + dv]), np.array([0.009, 0.007, 0.004]), 6, r2=np.array([0.004, 0.004, 0.003]))
        b.mb.add(V, F, "cloth_accent", {"head": 1.0}, tag="knot")
    # towel round the neck, ends hanging at the chest
    th = np.linspace(0, TAU, 19)[:-1]
    zt = sz + 0.018 - 0.012 * np.abs(np.sin(th))
    ring_pts = np.stack([0.088 * np.sin(th), 0.006 + 0.074 * np.cos(th), zt], 1)
    V, F, U, RI = sweep(ring_pts, 0.024, 7, closed_path=True, r2=0.011)
    b.mb.add(V, F, "cloth_accent", tw, tag="towel")
    for sg in (1, -1):
        a = np.array([sg * 0.052, -0.062, sz + 0.0])
        path = np.array([a, a + [sg * 0.006, -0.03, -0.06], a + [sg * 0.008, -0.045, -0.15]])
        V, F, U, RI = sweep(path, 0.022, 6, r2=0.006)
        Cc = np.ones((len(V), 3))
        Cc[V[:, 2] < a[2] - 0.11] = [0.65, 0.72, 0.9]
        b.mb.add(V, F, "cloth_accent", tw, C=Cc, tag="towel")


# ================================================================ elder (light yukata, grey bun, uchiwa)

def elder(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = J["ankle_z"] + 0.045 * lk
    hc, hn, hh = P["hunch"]
    T = T_([
        (nb + 0.022, 0.046, 0.042, 0.050, -hn + 0.006, 2.0),
        (sz + 0.004, 0.076, 0.060, 0.072, -hn * 0.8, 2.0),
        (sz - 0.024, 0.122, 0.074, 0.094, -hn * 0.6, 2.3),
        (sz - 0.07, 0.140, 0.090, 0.100, -hn * 0.35, 2.3),
        (ch, 0.134, 0.098, 0.094, -hc, 2.2),
        (sp, 0.124, 0.094, 0.090, 0.0, 2.2),
        (hip + 0.04, 0.138, 0.102, 0.108, 0.0, 2.2),
        (hip - 0.10, 0.140, 0.104, 0.108, 0.0, 2.2),
        (kn, 0.132, 0.102, 0.100, 0.0, 2.2),
        (hem, 0.126, 0.100, 0.096, -0.004, 2.2),
    ])
    zs = [r[0] for r in T.r]
    wf = b.robe_weights(hip + 0.02, hem)
    b.tube_mesh(T, zs, "cloth_main", wf, n=24, fold_top=(0.014, 0.03), fold_bot=(0.012, 0.03), tag="robe")
    tw = lambda p: torso_w(J, p)
    pts = lapels(b, T, nb + 0.016, ch + 0.03, ch - 0.02, 0.026, "cloth_accent", tw, col=np.full(3, 1.0))
    v_patch(b, T, pts, nb, ch + 0.03, "skin", tw)
    z0, z1 = sp - 0.015, sp + 0.12
    b.obi_band(T, z0, z1, 0.013, "cloth_accent", tw, C=np.full(3, 0.9))
    B = T.point((z0 + z1) / 2 + 0.01, 0.0, off=0.032)
    b.blob(B, (X, Y, Z), (0.105, 0.032, 0.082), "cloth_accent", tw, p=4.0, C=np.full(3, 0.8), tag="taiko")
    for side in ("L", "R"):
        b.sleeve(side, -0.012, P["ua"] + P["fa"] * 0.78, [0.052, 0.060, 0.062, 0.064, 0.068], pouch=0.17 * lk)
        b.arm_skin(side, P["ua"] + P["fa"] * 0.55, P["ua"] + P["fa"] + 0.012, 0.026, 0.022)
        b.hand(side)
        b.leg_skin(side, kn - 0.04, J["ankle_z"] + 0.012, 0.040, 0.028)
        b.foot(side)
        b.geta(side, "cloth_dark")
    b.neck(0.037)
    b.head_face("far")
    fan(b)


BUILDERS = {"woman": woman, "man": man, "kid": kid, "keeper": keeper, "elder": elder}
