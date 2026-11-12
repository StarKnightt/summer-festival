"""Skin she shows (neck and chest V, arms, hands, lower legs, bare feet) and her geta.

Only skin that can be seen is modelled: the torso under the yukata and the thighs inside the
narrow skirt are left out (no poke-through, fewer triangles). Left side built, right mirrored.
"""
import numpy as np

from . import rig
from . import shape as S
from .common import (catmull, frames_along, make_mesh, material, merge_geo, mirror, nearest_on_polyline,
                     norm, orient, smooth, spline_points, tube)

# ---------------------------------------------------------------- neck and chest

NECK = np.array([
    [1.060, 0.116, 0.072, 0.000],
    [1.100, 0.128, 0.080, -0.006],
    [1.150, 0.140, 0.078, -0.002],
    [1.190, 0.148, 0.071, 0.004],
    [1.214, 0.134, 0.065, 0.006],
    [1.232, 0.088, 0.053, 0.010],
    [1.250, 0.046, 0.042, 0.012],
    [1.275, 0.039, 0.037, 0.012],
    [1.320, 0.038, 0.036, 0.012],
    [1.365, 0.034, 0.032, 0.012],
])


def neck_geo():
    zs = np.concatenate([np.linspace(1.06, 1.20, 8), np.linspace(1.21, 1.26, 6), np.linspace(1.275, 1.365, 5)])
    r = catmull(NECK, zs)
    ph = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    rings = []
    for z, (a, b, yc) in zip(zs, r):
        x, y = S.superellipse(ph, a, b, yc, 2.2)
        rings.append(np.stack([x, y, np.full_like(x, z)], 1))
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    F = orient(V, F, lambda C: np.stack([np.zeros(len(C)), np.full(len(C), 0.005), C[:, 2]], 1))
    return V, F


# ---------------------------------------------------------------- arms and hands (left)


def arm_geo():
    hp = rig.hand_points()
    d, w, n = hp["d"], hp["w"], hp["n"]
    ctrl = [np.array([0.085, 0.004, 1.192]), S.SH + np.array([-0.01, 0, 0.0]), S.SH * 0.5 + S.ELB * 0.5, S.ELB,
            S.ELB * 0.5 + S.WRI * 0.5, S.WRI + d * 0.012]
    P = spline_points(ctrl, 30)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    L = s[-1]
    s_sh = np.linalg.norm(S.SH - ctrl[0])
    s_el = s_sh + S.UP_LEN
    rad = catmull([[0, 0.040], [s_sh, 0.040], [s_sh + 0.08, 0.035], [s_el - 0.02, 0.029], [s_el, 0.028],
                   [s_el + 0.06, 0.030], [L - 0.03, 0.022], [L, 0.021]], s)[:, 0]
    flat = smooth(s_el + 0.05, L, s)           # the wrist flattens (palm axis)
    T, N, B = frames_along(P, up_hint=(0, -1, 0))
    k = 14
    a = np.linspace(0, 2 * np.pi, k, endpoint=False)
    rings = []
    for i in range(len(P)):
        # Blend the ring axes toward the hand frame near the wrist.
        ax1 = norm(N[i] * (1 - flat[i]) + w * flat[i])
        ax1 = norm(ax1 - T[i] * (ax1 @ T[i]))
        ax2 = np.cross(T[i], ax1)
        r1 = rad[i] * (1 + 0.12 * flat[i])
        r2 = rad[i] * (1 - 0.22 * flat[i])
        rings.append(P[i] + np.outer(np.cos(a), ax1) * r1 + np.outer(np.sin(a), ax2) * r2)
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    F = orient(V, F, lambda C: nearest_on_polyline(C, P))
    return V, F


def _finger(p0, d, n, L, r0, curl=1.0):
    p1 = p0 + d * L * 0.40 + n * L * 0.05 * curl
    p2 = p1 + norm(d + n * 0.45 * curl) * L * 0.33
    p3 = p2 + norm(d * 0.6 + n * 0.8 * curl) * L * 0.27
    P = spline_points([p0 - d * 0.006, p0, p1, p2, p3], 10)
    T, N, B = frames_along(P, up_hint=n)
    t = np.linspace(0, 1, len(P))
    rr = r0 * (1 - 0.22 * t)
    a = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    rings = [P[i] + np.outer(np.cos(a), B[i]) * rr[i] + np.outer(np.sin(a), N[i]) * rr[i] * 0.85 for i in range(len(P))]
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    V[-1] = P[-1] + T[-1] * rr[-1] * 0.8          # round fingertip
    F = orient(V, F, lambda C: nearest_on_polyline(C, P))
    return V, F, P


def hand_geo():
    """Palm, four slender relaxed fingers and a thumb. Returns parts with their role."""
    hp = rig.hand_points()
    d, w, n = hp["d"], hp["w"], hp["n"]
    W0 = hp["wrist"]
    # Palm: rings along d.
    ts = np.array([-0.008, 0.0, 0.015, 0.035, 0.055, 0.072, 0.082, 0.088])
    hw = np.array([0.020, 0.021, 0.026, 0.032, 0.034, 0.033, 0.030, 0.022])
    hh = np.array([0.014, 0.0135, 0.0125, 0.0115, 0.011, 0.0100, 0.0090, 0.0070])
    a = np.linspace(0, 2 * np.pi, 14, endpoint=False)
    rings = []
    for t, x, y in zip(ts, hw, hh):
        c = W0 + d * t + n * 0.001
        ca, sa = np.cos(a), np.sin(a)
        sx = np.sign(ca) * np.abs(ca) ** (2 / 2.6)
        sy = np.sign(sa) * np.abs(sa) ** (2 / 2.6)
        rings.append(c + np.outer(sx * x, w) + np.outer(sy * y, n))
    pv, pf = tube(np.array(rings), cap_start=True, cap_end=True)
    axis = np.array([W0 + d * t for t in ts])
    pf = orient(pv, pf, lambda C: nearest_on_polyline(C, axis))
    parts = [("palm", pv, pf)]
    kn = hp["knuck"]
    for off, L, r, c in ((0.0215, 0.062, 0.0070, 0.9), (0.0072, 0.069, 0.0073, 1.0),
                         (-0.0075, 0.065, 0.0068, 1.1), (-0.0215, 0.052, 0.0060, 1.25)):
        p0 = kn + w * off - d * 0.004 - n * 0.0005 * 0 - d * 0.0
        dd = norm(d - w * off * 1.2)
        fv, ff, _ = _finger(p0, dd, n, L, r, c)
        parts.append(("finger", fv, ff))
    t0 = hp["thumb0"]
    tdir = norm(hp["thumb1"] - t0)
    P = spline_points([t0 - tdir * 0.012, t0, t0 + tdir * 0.026, t0 + tdir * 0.044 + d * 0.008 + n * 0.006,
                       t0 + tdir * 0.056 + d * 0.016 + n * 0.012], 10)
    T, N, B = frames_along(P, up_hint=n)
    tt = np.linspace(0, 1, len(P))
    rr = 0.0098 - 0.0028 * tt
    a8 = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    rings = [P[i] + np.outer(np.cos(a8), B[i]) * rr[i] + np.outer(np.sin(a8), N[i]) * rr[i] * 0.85 for i in range(len(P))]
    tv, tf = tube(np.array(rings), cap_start=True, cap_end=True)
    tv[-1] = P[-1] + T[-1] * rr[-1] * 0.8
    tf = orient(tv, tf, lambda C: nearest_on_polyline(C, P))
    parts.append(("thumb", tv, tf))
    return parts


def hand_weights(role, V):
    hp = rig.hand_points()
    d = hp["d"]
    along = (V - hp["wrist"]) @ d
    wf = smooth(-0.012, 0.004, along)            # forearm -> hand across the wrist
    W = {"forearm_L": 1 - wf, "hand_L": wf}
    if role == "finger":
        k = smooth(-0.004, 0.014, (V - hp["knuck"]) @ d)
        W = {"hand_L": 1 - k, "fingers_L": k}
    elif role == "thumb":
        k = smooth(0.004, 0.022, (V - hp["thumb0"]) @ norm(hp["thumb1"] - hp["thumb0"]))
        W = {"hand_L": 1 - k, "thumb_L": k}
    return W


# ---------------------------------------------------------------- lower legs, feet, geta (left)

FOOT = np.array([
    # y, half-width, top z, bottom z
    [-0.1735, 0.010, 0.011, 0.005],
    [-0.166, 0.024, 0.016, 0.003],
    [-0.150, 0.034, 0.021, 0.001],
    [-0.125, 0.039, 0.028, 0.000],
    [-0.090, 0.040, 0.040, 0.000],
    [-0.050, 0.036, 0.058, 0.000],
    [-0.010, 0.032, 0.076, 0.000],
    [0.020, 0.030, 0.088, 0.000],
    [0.045, 0.028, 0.070, 0.000],
    [0.060, 0.024, 0.048, 0.002],
    [0.0685, 0.012, 0.028, 0.008],
])
FOOT_X = 0.074
FOOT_P = 2.6


def foot_ring(y, ph):
    r = catmull(FOOT, np.atleast_1d(y))[0]
    hw, top, bot = r
    c, s = np.cos(ph), np.sin(ph)
    x = FOOT_X + hw * np.sign(c) * np.abs(c) ** (2 / FOOT_P)
    z = 0.5 * (top + bot) + 0.5 * (top - bot) * np.sign(s) * np.abs(s) ** (2 / FOOT_P)
    return x, z


def foot_top(dx, y):
    """Height of the top of the foot at lateral offset dx from the foot centre line."""
    hw, top, bot = catmull(FOOT, np.atleast_1d(y))[0]
    c = np.clip(np.abs(dx) / hw, 0, 1) ** (FOOT_P / 2)
    s = np.sqrt(np.clip(1 - c * c, 0, 1))
    return 0.5 * (top + bot) + 0.5 * (top - bot) * s ** (2 / FOOT_P)


def foot_geo():
    ys = np.concatenate([np.linspace(-0.1735, -0.10, 6), np.linspace(-0.08, 0.04, 6), np.linspace(0.05, 0.0685, 4)])
    ph = np.linspace(0, 2 * np.pi, 18, endpoint=False)
    rings = []
    for y in ys:
        x, z = foot_ring(y, ph)
        rings.append(np.stack([x, np.full_like(x, y), z], 1))
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    ax = np.stack([np.full(len(ys), FOOT_X), ys, np.array([0.5 * sum(catmull(FOOT, [y])[0][1:]) for y in ys])], 1)
    F = orient(V, F, lambda C: nearest_on_polyline(C, ax))
    return V, F


def shin_geo():
    up = norm(S.KNEE - S.ANKLE)
    P = spline_points([S.KNEE + up * 0.07, S.KNEE, S.ANKLE + np.array([0, 0, -0.03])], 16)
    z = P[:, 2]
    rad = catmull([[0.045, 0.024], [0.075, 0.025], [0.12, 0.030], [0.22, 0.038], [0.33, 0.046], [0.44, 0.044],
                   [0.52, 0.046]], z)[:, 0]
    T, N, B = frames_along(P, up_hint=(0, -1, 0))
    a = np.linspace(0, 2 * np.pi, 14, endpoint=False)
    rings = []
    for i in range(len(P)):
        # Calf fuller at the back (+Y).
        off = np.array([0, 0.25 * rad[i] * smooth(0.12, 0.30, z[i]) * (1 - smooth(0.36, 0.46, z[i])), 0])
        ring = P[i] + np.outer(np.cos(a), np.array([1, 0, 0])) * rad[i] * 0.92 + np.outer(np.sin(a), np.array([0, 1, 0])) * rad[i]
        back = np.clip(np.sin(a), 0, None)[:, None]
        rings.append(ring + back * off)
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    F = orient(V, F, lambda C: nearest_on_polyline(C, P))
    return V, F


def geta_geo():
    """Wooden geta: a rounded plate with two teeth below (the sole is SOLE = 50 mm)."""
    yc, hl, hw = -0.046, 0.114, 0.047
    t = np.linspace(0, 2 * np.pi, 32, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    ox = hw * np.sign(c) * np.abs(c) ** (2 / 5.0)
    oy = yc + hl * np.sign(s) * np.abs(s) ** (2 / 5.0)
    rings = []
    for z, k in ((-0.016, 0.985), (-0.0145, 1.0), (-0.0015, 1.0), (0.0, 0.985)):
        rings.append(np.stack([FOOT_X + ox * k, yc + (oy - yc) * k, np.full_like(ox, z)], 1))
    pv, pf = tube(np.array(rings), cap_start=True, cap_end=True)
    pf = orient(pv, pf, lambda C: np.tile([FOOT_X, yc, -0.008], (len(C), 1)))
    parts = [(pv, pf)]
    for (y0, y1) in ((0.028, 0.047), (-0.131, -0.112)):
        xs = (FOOT_X - 0.044, FOOT_X + 0.044)
        zs = (-S.SOLE, -0.016)
        V = np.array([[x, y, z] for z in zs for y in (y0, y1) for x in xs])
        F = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        cc = V.mean(0)
        F = orient(V, F, lambda C: np.tile(cc, (len(C), 1)))
        parts.append((V, F))
    return merge_geo(parts)


def hanao_geo():
    """Red thong strap: from the toe post between the first two toes over the instep to both sides
    of the plate."""
    x0 = FOOT_X - 0.011
    r = 0.0050

    def on_foot(x, y, lift=0.0):
        return np.array([x, y, float(np.ravel(foot_top(x - FOOT_X, y))[0]) + r * 0.7 + lift])

    post_top = np.array([x0, -0.120, 0.022])
    parts = []
    for sx in (1, -1):
        pts = [np.array([x0, -0.126, 0.0]), post_top, on_foot(x0 + 0.006 * sx, -0.104, 0.002),
               on_foot(FOOT_X + 0.020 * sx, -0.078, 0.003), on_foot(FOOT_X + 0.034 * sx, -0.052, 0.0),
               np.array([FOOT_X + 0.046 * sx, -0.038, 0.002])]
        P = spline_points(pts, 15)
        T, N, B = frames_along(P, up_hint=(0, 0, 1))
        a = np.linspace(0, 2 * np.pi, 6, endpoint=False)
        rings = [P[i] + np.outer(np.cos(a), N[i]) * r * 0.75 + np.outer(np.sin(a), B[i]) * r for i in range(len(P))]
        V, F = tube(np.array(rings), cap_start=True, cap_end=True)
        F = orient(V, F, lambda C: nearest_on_polyline(C, P))
        parts.append((V, F))
    # A little knot on top of the toe post.
    k = 10
    th = np.linspace(0.3, np.pi - 0.3, 5)
    ph = np.linspace(0, 2 * np.pi, k, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    c = post_top + np.array([0, 0.002, 0.004])
    V = c + np.stack([0.0075 * np.sin(TH) * np.cos(PH), 0.0065 * np.sin(TH) * np.sin(PH), 0.0055 * np.cos(TH)], -1)
    V, F = tube(V[::-1].reshape(5, k, 3), cap_start=True, cap_end=True)
    F = orient(V, F, lambda C: np.tile(c, (len(C), 1)))
    parts.append((V, F))
    return merge_geo(parts)


# ---------------------------------------------------------------- build


def build(col):
    m_skin = bpy_mat_skin()
    m_wood = material("wood_geta", "#c9a072")
    m_hanao = material("cloth_hanao", "#c63a40")
    out = {}

    # Neck + chest.
    V, F = neck_geo()
    ob = make_mesh("heroine_neck", V, F, col, [m_skin])
    rig.store(ob, rig.spine_weights(V))
    out["neck"] = ob

    # Arms + hands (one mesh for both sides).
    av, af = arm_geo()
    parts = [(av, af)]
    WL = [rig.arm_weights(av, 1, hand=False)]
    for role, v, f in hand_geo():
        parts.append((v, f))
        WL.append(hand_weights(role, v))
    left_V, left_F = merge_geo(parts)
    left_W = {}
    o = 0
    for (v, f), w in zip(parts, WL):
        for bn, val in w.items():
            arr = left_W.setdefault(bn, np.zeros(len(left_V)))
            arr[o:o + len(v)] += np.broadcast_to(val, (len(v),))
        o += len(v)
    rv, rf = mirror(left_V, left_F)
    V, F = merge_geo([(left_V, left_F), (rv, rf)])
    W = {}
    n = len(left_V)
    for bn, val in left_W.items():
        W.setdefault(bn, np.zeros(len(V)))[:n] += val
        W.setdefault(rig.L2R(bn), np.zeros(len(V)))[n:] += val
    ob = make_mesh("heroine_arms", V, F, col, [m_skin])
    rig.store(ob, W)
    out["arms"] = ob

    # Lower legs + feet.
    sv, sf = shin_geo()
    fv, ff = foot_geo()
    lv, lf = merge_geo([(sv, sf), (fv, ff)])
    lw = rig.leg_weights(lv, 1)
    rv, rf = mirror(lv, lf)
    V, F = merge_geo([(lv, lf), (rv, rf)])
    W = {}
    n = len(lv)
    for bn, val in lw.items():
        W.setdefault(bn, np.zeros(len(V)))[:n] += val
        W.setdefault(rig.L2R(bn), np.zeros(len(V)))[n:] += val
    ob = make_mesh("heroine_legs", V, F, col, [m_skin])
    rig.store(ob, W)
    out["legs"] = ob

    # Geta (wood) + hanao (red straps).
    gv, gf = geta_geo()
    hv, hf = hanao_geo()
    lv, lf = merge_geo([(gv, gf), (hv, hf)])
    mid = np.concatenate([np.zeros(len(gf)), np.ones(len(hf))])
    rv, rf = mirror(lv, lf)
    V, F = merge_geo([(lv, lf), (rv, rf)])
    ob = make_mesh("heroine_geta", V, F, col, [m_wood, m_hanao], np.concatenate([mid, mid]))
    n = len(lv)
    rig.store(ob, {"foot_L": np.r_[np.ones(n), np.zeros(n)], "foot_R": np.r_[np.zeros(n), np.ones(n)]})
    out["geta"] = ob
    return out


def bpy_mat_skin():
    return material("skin", "#f2cfbb")
