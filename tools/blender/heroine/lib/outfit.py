"""Yukata, collar, obi and bow, and the hanging sleeves.

heroine_yukata  cloth_yukata (morning-glory tile)  body shell neck->ankle with the V opening,
                okumi edge ridge (left panel over right), collar band; cloth_collar: white
                under-collar line inside the V
heroine_obi     cloth_obi (marigold-coral) band + butterfly bow (two loops each side, two tails);
                cloth_obijime cord, plastic_obidome bead
heroine_sleeve_L / _R  cloth_yukata  sleeve tube round the arm + the hanging pocket (furi)
"""
import math

import numpy as np

from . import rig
from . import shape as S
from . import tex
from .common import (catmull, frames_along, image_from_array, make_mesh, material, merge_geo, mirror,
                     nearest_on_polyline, norm, orient, set_uv_loops, set_uv_vertex, smooth, spline_points, tube)

TILE = tex.YUKATA_TILE_M
NPH = 64
V_TOP = 1.235          # top of the V opening (where it meets the neck ring)
V_BOT = 1.118          # where the collars cross
V_HALF = 0.056         # half width of the V at V_TOP


def v_half(z):
    return V_HALF * np.clip((z - V_BOT) / (V_TOP - V_BOT), 0, 1.2)


# ---------------------------------------------------------------- weights


def skirt_weights(P):
    """Lower body: hips, then thighs/shins of BOTH legs blended across the front/back centre, so
    the narrow tube follows small steps without tearing."""
    n = len(P)
    W = {}
    for s in (1, -1):
        Q = np.array(P, float)
        Q[:, 0] *= s
        Wl, _ = rig.chain(Q, [S.HIP, S.KNEE, S.ANKLE], ["thigh_L", "shin_L"], [0.07])
        crease = S.HIP[2] - 0.01 + 0.03 * smooth(0.0, 0.08, Q[:, 1])
        k = smooth(crease - 0.03, crease + 0.07, Q[:, 2])
        ks = smooth(-0.055, 0.055, Q[:, 0])       # this leg's side of the tube
        for bn, w in Wl.items():
            W = rig.merge(W, {bn if s > 0 else rig.L2R(bn): w * (1 - k) * ks})
        W = rig.merge(W, {"hips": k * ks})
    return W


def body_weights(P, phi=None):
    """Whole shell: spine above the hips, skirt below; the shoulder area follows the arms; a share
    of the hem centre front/back goes to the skirtF1 / skirtB1 sway bones."""
    n = len(P)
    up = rig.spine_weights(P)
    lo = skirt_weights(P)
    k = smooth(0.83, 0.90, P[:, 2])
    W = rig.merge(rig.scale(lo, 1), {})
    W = {bn: w * (1 - k) for bn, w in lo.items()}
    W = rig.merge(W, {bn: w * k for bn, w in up.items()})
    for s in (1, -1):
        ksh = smooth(0.105, 0.16, P[:, 0] * s) * smooth(1.12, 1.18, P[:, 2])
        if not np.any(ksh > 0):
            continue
        Wa = rig.arm_weights(P, s, hand=False)
        W = {bn: w * (1 - ksh) for bn, w in W.items()}
        W = rig.merge(W, {bn: w * ksh for bn, w in Wa.items()})
    if phi is not None:
        low = 1 - smooth(0.16, 0.56, P[:, 2])
        kf = 0.85 * low * np.clip(np.cos(phi), 0, 1) ** 1.6
        kb = 0.85 * low * np.clip(-np.cos(phi), 0, 1) ** 1.6
        W = {bn: w * (1 - kf - kb) for bn, w in W.items()}
        W["skirtF1"] = kf
        W["skirtB1"] = kb
    return W


# ---------------------------------------------------------------- yukata shell


def shell_geo():
    zs = np.concatenate([np.linspace(0.075, 0.80, 16), np.linspace(0.83, 1.10, 10), np.linspace(1.115, 1.262, 17)])
    ph = np.linspace(0, 2 * np.pi, NPH, endpoint=False)
    rings, zrow = [], []
    # Hem: a folded edge (inner lip) so the opening has thickness.
    for z, off in ((0.092, -0.006), (0.068, -0.0035), (0.068, 0.0)):
        rings.append(S.yukata_point(ph, np.full_like(ph, z), off))
        zrow.append(z)
    for z in zs:
        rings.append(S.yukata_point(ph, np.full_like(ph, z)))
        zrow.append(z)
    R = np.array(rings)
    rows = len(R)
    V = R.reshape(-1, 3)
    F = []
    for r in range(rows - 1):
        for c in range(NPH):
            c2 = (c + 1) % NPH
            F.append((r * NPH + c, r * NPH + c2, (r + 1) * NPH + c2, (r + 1) * NPH + c))
    # Outward from the axis, except the hem's inner lip (rows 0-1) which faces in.
    def inside(C):
        return np.stack([np.zeros(len(C)), np.zeros(len(C)), C[:, 2]], 1)
    F = orient(V, F, inside)
    F = [tuple(reversed(f)) if r < 1 else f for f, r in zip(F, [i // NPH for i in range(len(F))])]
    # Cut the V opening.
    C = np.array([V[list(f)].mean(0) for f in F])
    cut = (C[:, 1] < 0) & (C[:, 2] > V_BOT) & ((np.abs(C[:, 0]) < v_half(C[:, 2])) | ((C[:, 2] > V_TOP) & (np.abs(C[:, 0]) < 0.052)))
    F = [f for f, k in zip(F, cut) if not k]
    phi = np.tile(ph, rows)
    rowi = np.repeat(np.arange(rows), NPH)
    coli = np.tile(np.arange(NPH), rows)
    return V, F, phi, rowi, coli


def okumi_geo():
    """The edge of the over (left) panel running down the front on her right."""
    zs = np.linspace(0.072, 0.985, 30)
    x = -0.030 - 0.040 * (0.985 - zs) / 0.91
    y = S.yukata_front_y(x, zs)
    P = np.stack([x, y - 0.0005, zs], 1)
    T, N, B = frames_along(P, up_hint=(0, -1, 0))
    a = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    rings = [P[i] + np.outer(np.cos(a), np.array([1.0, 0, 0])) * 0.0035 + np.outer(np.sin(a), np.array([0, 1.0, 0])) * 0.0028
             for i in range(len(P))]
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    F = orient(V, F, lambda C: nearest_on_polyline(C, P))
    return V, F


def collar_path():
    """Collar centre line: from the crossing up her right V edge, round the back of the neck, down
    her left V edge, across the crossing to under the obi (left panel over right)."""
    def vpt(x, z, out=0.003):
        y = S.yukata_front_y(np.array([x]), np.array([z]))[0]
        return np.array([x, y - out, z])

    left_v = [vpt(v_half(z) - 0.004, z) for z in (1.226, 1.200, 1.170, 1.142)]
    back = [np.array([0.056, -0.022, 1.246]), np.array([0.060, 0.012, 1.254]), np.array([0.042, 0.046, 1.262]),
            np.array([0.0, 0.062, 1.268])]
    right_side = [S.side(p, -1) for p in reversed(back[:-1])]
    right_v = [S.side(p, -1) for p in reversed(left_v)]
    cross = vpt(0.0, V_BOT + 0.002)
    tail = [vpt(-0.028, 1.100), vpt(-0.050, 1.082)]
    right_up = [S.side(p, -1) for p in reversed(left_v)]                 # crossing -> her right neck
    right_side = [S.side(p, -1) for p in back[:-1]]                      # front -> back
    left_side = back[-2::-1]                                             # back -> front
    ctrl = [cross + np.array([0.004, 0, -0.004])] + right_up + right_side + [back[-1]] + left_side + left_v + [cross] + tail
    return np.array(ctrl)


def collar_geo():
    ctrl = collar_path()
    P = spline_points(ctrl, 90)
    T, _, _ = frames_along(P)
    n = norm(np.stack([P[:, 0], P[:, 1] - 0.01, np.zeros(len(P))], 1))
    i_back = int(np.argmax(P[:, 1]))
    W = []
    for i in range(len(P)):
        w = norm(np.cross(n[i], T[i]))
        if P[i, 1] > 0.02:
            hint = np.array([0, 0, -1.0])
        else:
            hint = np.array([1.0 if i > i_back else -1.0, 0, -0.6])
        W.append(w if w @ hint > 0 else -w)
    W = np.array(W)
    wid = 0.025 * np.ones(len(P))
    sec = [(-0.0018, 0.0022), (0.0, 0.0046), (1.0, 0.0038), (1.04, 0.0008), (1.0, -0.0010), (0.0, -0.0006)]
    rings = []
    for i in range(len(P)):
        ring = [P[i] + W[i] * (u * wid[i] if abs(u) > 0.01 else u) + n[i] * h for (u, h) in sec]
        rings.append(ring)
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    Vn = np.asarray(V)
    mid = P + W * 0.0125 + n * 0.0018
    F = orient(Vn, F, lambda C: nearest_on_polyline(C, mid))
    # Han-eri: the white under-collar along the V and the back of the neck (not past the crossing).
    i_cross = len(P) - 1 - int(np.argmin(np.linalg.norm(P[::-1] - ctrl[-3], axis=1)))
    he = []
    for i in range(0, i_cross + 1):
        he.append([P[i] - W[i] * 0.0085 + n[i] * 0.0016, P[i] + W[i] * 0.004 + n[i] * 0.0016,
                   P[i] + W[i] * 0.004 + n[i] * 0.0002, P[i] - W[i] * 0.0085 + n[i] * 0.0002])
    hv, hf = tube(np.array(he), cap_start=True, cap_end=True)
    hmid = P[:i_cross + 1] - W[:i_cross + 1] * 0.002 + n[:i_cross + 1] * 0.0009
    hf = orient(hv, hf, lambda C: nearest_on_polyline(C, hmid))
    return (V, F), (hv, hf)


# ---------------------------------------------------------------- obi and bow

OBI_Z0, OBI_Z1 = 0.978, 1.112
OBI_T = 0.0185


def obi_geo():
    ph = np.linspace(0, 2 * np.pi, NPH, endpoint=False)
    prof = [(-1.0, 0.003), (-0.96, 0.012), (-0.84, 0.0175), (-0.5, OBI_T), (0.0, OBI_T), (0.5, OBI_T),
            (0.84, 0.0175), (0.96, 0.012), (1.0, 0.003)]
    rings = []
    for zn, off in prof:
        z = 0.5 * (OBI_Z0 + OBI_Z1) + 0.5 * (OBI_Z1 - OBI_Z0) * zn
        rings.append(S.yukata_point(ph, np.full_like(ph, z), off))
    V, F = tube(np.array(rings))
    F = orient(V, F, lambda C: np.stack([np.zeros(len(C)), np.zeros(len(C)), C[:, 2]], 1))
    return V, F


def cord_geo():
    zc = 1.040
    ph = np.linspace(0, 2 * np.pi, 56, endpoint=False)
    P = S.yukata_point(ph, np.full_like(ph, zc), OBI_T + 0.0025)
    T = norm(np.roll(P, -1, 0) - np.roll(P, 1, 0))
    up = np.array([0, 0, 1.0])
    Nn = norm(np.cross(T, up))
    a = np.linspace(0, 2 * np.pi, 6, endpoint=False)
    rings = np.array([P[i] + np.outer(np.cos(a), Nn[i]) * 0.0032 + np.outer(np.sin(a), up) * 0.0032 for i in range(len(P))])
    R, C = rings.shape[:2]
    V = rings.reshape(-1, 3)
    F = []
    for r in range(R):
        r2 = (r + 1) % R
        for c in range(C):
            c2 = (c + 1) % C
            F.append((r * C + c, r * C + c2, r2 * C + c2, r2 * C + c))
    F = orient(V, F, lambda Cc: nearest_on_polyline(Cc, np.vstack([P, P[:1]])))
    # Obidome: a small coral-pink bead on the cord at the front.
    c = P[0] + np.array([0, -0.006, 0])
    th = np.linspace(0.2, np.pi - 0.2, 6)
    pp = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    TH, PP = np.meshgrid(th, pp, indexing="ij")
    B = c + np.stack([0.011 * np.sin(TH) * np.cos(PP), 0.006 * np.sin(TH) * np.sin(PP), 0.008 * np.cos(TH)], -1)
    bv, bf = tube(B.reshape(6, 12, 3), cap_start=True, cap_end=True)
    bf = orient(bv, bf, lambda Cc: np.tile(c, (len(Cc), 1)))
    return (V, F), (bv, bf)


def _yback(x, z, extra):
    a, b, yc = S.yukata_ring(np.atleast_1d(z))
    u = np.clip(np.abs(x) / a, 0, 0.999)
    return yc + b * (1 - u ** S.SUPER) ** (1 / S.SUPER) + extra


KNOT = np.array([0.0, 0.124, 1.046])


def lens(ctrl, n, wfn, tfn, out, sides=8):
    from .hair import lock
    return lock(ctrl, n, wfn, tfn, lambda P: np.tile(out, (len(P), 1)), sides=sides, sharp=0.75)


def bow_geo():
    parts = []
    # Knot: a rounded box.
    th = np.linspace(0.12, np.pi - 0.12, 8)
    ph = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    sx = np.sign(np.sin(TH) * np.cos(PH)) * np.abs(np.sin(TH) * np.cos(PH)) ** 0.6
    sy = np.sign(np.sin(TH) * np.sin(PH)) * np.abs(np.sin(TH) * np.sin(PH)) ** 0.6
    sz = np.sign(np.cos(TH)) * np.abs(np.cos(TH)) ** 0.6
    K = KNOT + np.stack([0.027 * sx, 0.021 * sy, 0.035 * sz], -1)
    kv, kf = tube(K.reshape(8, 16, 3), cap_start=True, cap_end=True)
    kf = orient(kv, kf, lambda C: np.tile(KNOT, (len(C), 1)))
    parts.append(("knot", kv, kf))
    out_back = np.array([0, 1.0, 0.15])
    for s in (1, -1):
        # Upper loop: wide, rising out to the side.
        up = [KNOT + np.array([0.012 * s, 0.006, 0.010]), KNOT + np.array([0.060 * s, 0.020, 0.040]),
              KNOT + np.array([0.115 * s, 0.020, 0.068]), KNOT + np.array([0.150 * s, 0.010, 0.074])]
        V, F, _ = lens(up, 12, lambda t: 0.016 + 0.034 * np.sin(np.pi * np.clip(t * 0.92 + 0.04, 0, 1)) ** 0.7,
                       lambda t: 0.007 + 0.010 * np.sin(np.pi * t), out_back)
        parts.append(("loop", V, F))
        lo = [KNOT + np.array([0.012 * s, 0.004, -0.010]), KNOT + np.array([0.055 * s, 0.016, -0.034]),
              KNOT + np.array([0.100 * s, 0.014, -0.058]), KNOT + np.array([0.122 * s, 0.006, -0.066])]
        V, F, _ = lens(lo, 11, lambda t: 0.012 + 0.024 * np.sin(np.pi * np.clip(t * 0.92 + 0.04, 0, 1)) ** 0.7,
                       lambda t: 0.006 + 0.008 * np.sin(np.pi * t), out_back)
        parts.append(("loop", V, F))
    return parts


def tail_ctrl(s):
    """Hanging tail on her left (s=1) or right (s=-1)."""
    pts = []
    for f, x, z in ((0.0, 0.016, 1.030), (0.25, 0.028, 0.975), (0.55, 0.040, 0.905), (0.8, 0.048, 0.850),
                    (1.0, 0.052, 0.805 if s > 0 else 0.830)):
        x = x * s
        y = _yback(np.array([x]), z, 0.020 + 0.006 * (1 - f))[0]
        pts.append(np.array([x, y, z]))
    return np.array(pts)


def tail_geo(s):
    ctrl = tail_ctrl(s)
    V, F, P = lens(ctrl, 16, lambda t: 0.034 + 0.010 * t - 0.03 * np.clip((t - 0.93) / 0.07, 0, 1),
                   lambda t: 0.0045 + 0.001 * (1 - t), np.array([0, 1.0, -0.05]), sides=6)
    return V, F, P


# ---------------------------------------------------------------- sleeves (left)

SLEEVE_R = 0.052
SLEEVE_DROP = 0.380        # pocket bottom below the wrist (rest pose)


def arm_axis():
    a1 = norm(S.ELB - S.SH)
    start = S.SH - a1 * 0.005
    P = spline_points([start, S.SH, S.ELB, S.WRI + norm(S.WRI - S.ELB) * 0.006], 26)
    return P


def axis_at_x(x):
    P = arm_axis()
    return np.stack([np.interp(x, P[:, 0], P[:, k]) for k in range(3)], -1)


def sleeve_geo():
    P = arm_axis()
    T, N, B = frames_along(P, up_hint=(0, -1, 0))
    k = 18
    a = np.linspace(0, 2 * np.pi, k, endpoint=False)
    s = np.linspace(0, 1, len(P))
    rad = SLEEVE_R * (0.88 + 0.12 * smooth(0.0, 0.3, s))
    rings = [P[i] + np.outer(np.cos(a), N[i]) * rad[i] + np.outer(np.sin(a), B[i]) * rad[i] for i in range(len(P))]
    tv, tf = tube(np.array(rings))
    tf = orient(tv, tf, lambda C: nearest_on_polyline(C, P))
    # Cuff: a turned-in lip so the opening has thickness and the inside never shows a backface.
    Tn = T[-1]
    lip = [P[-1] + np.outer(np.cos(a), N[-1]) * (rad[-1] - 0.0045) + np.outer(np.sin(a), B[-1]) * (rad[-1] - 0.0045) + Tn * 0.001,
           P[-1] + np.outer(np.cos(a), N[-1]) * (rad[-1] - 0.0055) + np.outer(np.sin(a), B[-1]) * (rad[-1] - 0.0055) - Tn * 0.05]
    lv = np.vstack([np.array(rings[-1]), lip[0], lip[1]])
    from .common import grid_faces
    lf = grid_faces(3, k, True)
    lf = orient(lv, lf, lambda C: nearest_on_polyline(C, P[-4:]))
    lf = [tuple(reversed(f)) for f in lf[k:]] + lf[:k]
    # Pocket (furi): a soft pillow hanging below the arm, top edge inside the tube.
    x_in, x_out = 0.178, S.WRI[0] - 0.004
    cols, rows = 16, 18
    sx = np.linspace(0, 1, cols)
    xs = x_in + sx * (x_out - x_in)
    ax = axis_at_x(xs)
    ztop = ax[:, 2] - 0.010
    zb = S.WRI[2] - SLEEVE_DROP
    rc_out, rc_in = 0.075, 0.050
    zbot = np.full(cols, zb)
    m = xs > x_out - rc_out
    zbot[m] = zb + rc_out - np.sqrt(np.clip(rc_out ** 2 - (xs[m] - (x_out - rc_out)) ** 2, 0, None))
    m = xs < x_in + rc_in
    zbot[m] = zb + rc_in - np.sqrt(np.clip(rc_in ** 2 - (x_in + rc_in - xs[m]) ** 2, 0, None))
    v = np.linspace(0, 1, rows)
    edge = np.sin(np.pi * sx) ** 0.35
    Tv = catmull([[0, 0.034], [0.12, 0.013], [0.35, 0.0085], [0.8, 0.0065], [0.95, 0.004], [1.0, 0.0]], v)[:, 0]
    ring_list = []
    for i in range(rows):
        z = ztop + v[i] * (zbot - ztop)
        t = Tv[i] * edge
        yc = ax[:, 1] + 0.004 * np.sin(np.pi * sx)
        front = np.stack([xs, yc - t, z], 1)
        back = np.stack([xs, yc + t, z], 1)[::-1][1:-1]
        ring_list.append(np.vstack([front, back]))
    R = np.array(ring_list)
    pv, pf = tube(R)
    pf = orient(pv, pf, lambda C: np.stack([C[:, 0], np.interp(C[:, 0], xs, ax[:, 1]), C[:, 2]], 1))
    return (tv, tf), (lv, lf), (pv, pf), xs, ztop


def sleeve_chain():
    xm = 0.300
    top = axis_at_x(np.array([xm]))[0] - np.array([0, 0, 0.012])
    zb = S.WRI[2] - SLEEVE_DROP
    p1 = np.array([xm + 0.015, top[1], top[2] - 0.24])
    p2 = np.array([xm + 0.030, top[1], zb + 0.025])
    return [top, p1, p2]


def sleeve_weights(V, xs_top, ztop):
    zt = np.interp(V[:, 0], xs_top, ztop, left=ztop[0], right=ztop[-1])
    d = zt - V[:, 2]
    # Arm part: project to the arm chain using the point on the axis above.
    A = axis_at_x(np.clip(V[:, 0], xs_top[0] - 0.05, S.WRI[0] + 0.01))
    Q = np.where((d > 0)[:, None], A, V)
    Wa = rig.arm_weights(Q, 1, hand=False)
    karm = 1 - smooth(0.05, 0.17, d)
    J = sleeve_chain()
    Ws, _ = rig.chain(V, J, ["sleeve_L1", "sleeve_L2"], [0.06])
    W = rig.scale(Wa, 1)
    for bn in W:
        W[bn] = W[bn] * karm
    W = rig.merge(W, Ws, 1)
    for bn in Ws:
        W[bn] = W[bn] - Ws[bn] + Ws[bn] * (1 - karm)
    return W


# ---------------------------------------------------------------- build


def build(col):
    img = image_from_array("T_heroine_yukata", tex.yukata_tile(1024))
    m_yuk = material("cloth_yukata", "#2b3a6c", img)
    m_col = material("cloth_collar", "#ece6dc")
    m_obi = material("cloth_obi", "#f0974c")
    m_cord = material("cloth_obijime", "#86c7c1")
    m_dome = material("plastic_obidome", "#ee8a9c")
    out = {}

    # --- yukata body + okumi + collar + han-eri (one mesh, two materials).
    V, F, phi, rowi, coli = shell_geo()
    ov, of = okumi_geo()
    (cv, cf), (hv, hf) = collar_geo()
    allV, allF = merge_geo([(V, F), (ov, of), (cv, cf), (hv, hf)])
    mi = np.concatenate([np.zeros(len(F) + len(of) + len(cf)), np.ones(len(hf))])
    ob = make_mesh("heroine_yukata", allV, allF, col, [m_yuk, m_col], mi)
    n_shell = len(V)
    K = 2.0

    def uv(pi, vids):
        out_uv = []
        cs = [coli[v] if v < n_shell else None for v in vids]
        if all(c is not None for c in cs):
            if max(cs) - min(cs) > NPH // 2:
                cs = [c + NPH if c < NPH // 2 else c for c in cs]
            for v, c in zip(vids, cs):
                out_uv.append((c / NPH * K, allV[v][2] / TILE))
        else:
            for v in vids:
                p = allV[v]
                out_uv.append((p[0] / TILE + 0.3, p[2] / TILE + p[1] * 3))
        return out_uv

    set_uv_loops(ob, uv)
    phi_all = np.concatenate([phi, np.arctan2(allV[n_shell:, 0], -allV[n_shell:, 1])])
    W = body_weights(allV, phi_all)
    rig.store(ob, W)
    out["yukata"] = ob

    # --- obi + bow + cord.
    rig.add_chain("skirtF", [np.array([0, -0.100, 0.640]), np.array([0, -0.092, 0.090])], "hips")
    rig.add_chain("skirtB", [np.array([0, 0.112, 0.640]), np.array([0, 0.092, 0.090])], "hips")
    for s, nm in ((1, "obiTailL"), (-1, "obiTailR")):
        c = tail_ctrl(s)
        P = spline_points(c, 21)
        rig.add_chain(nm, [P[2], P[11], P[20]], "spine")
    parts, mats, Ws = [], [], []
    V, F = obi_geo()
    parts.append((V, F)); mats.append(0); Ws.append(rig.spine_weights(V))
    kw = rig.spine_weights(KNOT[None])
    for role, V, F in bow_geo():
        parts.append((V, F)); mats.append(0)
        Ws.append({bn: np.full(len(V), w[0]) for bn, w in kw.items()})
    for s, nm in ((1, "obiTailL"), (-1, "obiTailR")):
        V, F, P = tail_geo(s)
        J = [KNOT + np.array([0.0, 0.0, 0.0])] + list(rig.chain_points(nm))
        Wc, _ = rig.chain(V, J, ["_base", nm + "1", nm + "2"], [0.02, 0.04])
        base = Wc.pop("_base")
        Wc = rig.merge(Wc, {bn: base * w[0] for bn, w in kw.items()})
        parts.append((V, F)); mats.append(0); Ws.append(Wc)
    (cv, cf), (bv, bf) = cord_geo()
    parts.append((cv, cf)); mats.append(1); Ws.append(rig.spine_weights(cv))
    parts.append((bv, bf)); mats.append(2); Ws.append(rig.spine_weights(bv))
    V, F = merge_geo(parts)
    mi = np.concatenate([np.full(len(f), m) for (v, f), m in zip(parts, mats)])
    ob = make_mesh("heroine_obi", V, F, col, [m_obi, m_cord, m_dome], mi)
    W, o = {}, 0
    for (v, f), w in zip(parts, Ws):
        for bn, val in w.items():
            W.setdefault(bn, np.zeros(len(V)))[o:o + len(v)] += np.broadcast_to(val, (len(v),))
        o += len(v)
    rig.store(ob, W)
    out["obi"] = ob

    # --- sleeves.
    J = sleeve_chain()
    rig.add_chain("sleeve_L", J, "forearm_L")
    rig.add_chain("sleeve_R", [S.side(p, -1) for p in J], "forearm_R")
    (tv, tf), (lv, lf), (pv, pf), xs, ztop = sleeve_geo()
    V, F = merge_geo([(tv, tf), (lv, lf), (pv, pf)])
    W = sleeve_weights(V, xs, ztop)
    for s, nm in ((1, "heroine_sleeve_L"), (-1, "heroine_sleeve_R")):
        if s > 0:
            Vs, Fs, Wsd = V, F, W
        else:
            Vs, Fs = mirror(V, F)
            Wsd = {rig.L2R(bn) if bn.endswith("_L") else bn.replace("sleeve_L", "sleeve_R"): w for bn, w in W.items()}
        ob = make_mesh(nm, Vs, Fs, col, [m_yuk])
        set_uv_vertex(ob, np.stack([Vs[:, 0] * s / TILE + 0.17, Vs[:, 2] / TILE + Vs[:, 1] * 0.5], 1))
        rig.store(ob, Wsd)
        out[nm] = ob
    return out
