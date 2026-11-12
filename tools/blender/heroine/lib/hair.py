"""Hair (dark chestnut updo) and the kanzashi hairpin.

heroine_hair (material `hair`):
  cap      shell over the skull, thickness tapering to the hairline (no cap gap)
  bangs    9 wispy locks over the forehead, ending just above the eyes
  sides    a long lock framing each side of the face to the jaw (+ a shorter one behind it)
  updo     8 broad locks swept from the nape and sides up into the bun
  bun      a soft twisted bun at the back of the head
  nape     3 loose fine strands at the nape
heroine_kanzashi (metal_kanzashi, plastic_flower_pink, plastic_flower_white, plastic_bead): a pin
through the bun's left side with three five-petal flowers and two short dangling chains.
"""
import math

import numpy as np

from . import rig
from . import shape as S
from .common import (catmull, frames_along, make_mesh, material, merge_geo, mirror, nearest_on_polyline, norm,
                     orient, smooth, spline_points, tube)

BUN_C = np.array([0.0, 0.122, 1.454])
BUN_AX = norm(np.array([0.0, 0.78, 0.62]))


def cap_thickness(P):
    z, y = P[:, 2], P[:, 1]
    return 0.0045 + 0.0060 * smooth(1.40, 1.50, z) + 0.0035 * smooth(0.0, 0.08, y)


HAIRLINE = np.array([  # |azimuth| (deg, 0 = front), hairline height
    [0, 1.452], [25, 1.446], [50, 1.425], [68, 1.398], [80, 1.384], [92, 1.398], [104, 1.392],
    [125, 1.356], [150, 1.336], [180, 1.330]])


def hair_mask(P):
    d = P - S.HEAD_C
    az = np.degrees(np.abs(np.arctan2(d[:, 0], -d[:, 1])))
    zl = catmull(HAIRLINE, az)[:, 0]
    return smooth(zl - 0.004, zl + 0.012, P[:, 2])


def push_out(P, off):
    """Move points outside the head surface by at least `off`."""
    P = np.array(P, float)
    for _ in range(6):
        f = S.head_sdf(P)
        bad = f < off
        if not bad.any():
            break
        g = S.head_grad(P[bad])
        P[bad] += g * (off - f[bad])[:, None]
    return P


def cap_geo():
    """Hair shell. Outside the hair region it sinks 2.5 mm under the skin, so the hairline is the
    smooth line where the shell crosses the skin (no stair-stepped edge, no gap)."""
    rows, cols = 34, 56
    th = np.linspace(0, np.radians(150), rows + 1)[1:]
    ph = np.linspace(0, 2 * np.pi, cols, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    D = np.stack([np.sin(TH) * np.sin(PH), -np.sin(TH) * np.cos(PH), np.cos(TH)], -1).reshape(-1, 3)
    r0 = S.head_radius(D)
    P0 = S.HEAD_C + D * r0[:, None]
    m = hair_mask(P0)
    t = -0.0025 + (cap_thickness(P0) + 0.0025) * smooth(0.0, 0.8, m)
    r = S.head_radius(D, off=t)
    V = S.HEAD_C + D * r[:, None]
    F = []
    for i in range(rows - 1):
        for j in range(cols):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            F.append((a, b, b + cols, a + cols))
    top = len(V)
    V = np.vstack([V, S.HEAD_C + np.array([0, 0, S.head_radius(np.array([[0, 0, 1.0]]), off=0.0105)[0]])])
    for j in range(cols):
        F.append((top, (j + 1) % cols, j))
    vis = np.r_[m > 1e-3, True]
    F = [f for f in F if any(vis[i] for i in f)]
    used = sorted({i for f in F for i in f})
    remap = {o: k for k, o in enumerate(used)}
    V = V[used]
    F = [tuple(remap[i] for i in f) for f in F]
    F = orient(V, F, lambda C: np.tile(S.HEAD_C, (len(C), 1)))
    return V, F


def lock(ctrl, n, wfn, tfn, outfn, sides=8, twist=0.0, sharp=1.0):
    """A hair lock: a flat lens-section tube along a spline. wfn/tfn: half width/thickness as
    functions of t in [0,1]; outfn(P) -> direction the flat face should face."""
    P = spline_points(ctrl, n)
    T, _, _ = frames_along(P)
    O = norm(outfn(P))
    Nn = norm(O - T * np.sum(O * T, 1, keepdims=True))
    B = np.cross(T, Nn)
    t = np.linspace(0, 1, n)
    w = np.broadcast_to(wfn(t), t.shape)
    th = np.broadcast_to(tfn(t), t.shape)
    a = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    rings = []
    for i in range(n):
        tw = twist * t[i]
        b = B[i] * math.cos(tw) + Nn[i] * math.sin(tw)
        nn = Nn[i] * math.cos(tw) - B[i] * math.sin(tw)
        ca = np.cos(a)
        sa = np.sin(a)
        rings.append(P[i] + np.outer(np.sign(ca) * np.abs(ca) ** sharp * w[i], b) + np.outer(sa * th[i], nn))
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    V[-1] = P[-1] + T[-1] * 0.002
    F = orient(V, F, lambda C: nearest_on_polyline(C, P))
    return V, F, P


def head_out(P):
    return S.head_grad(P)


def bang_locks():
    """Wispy see-through bangs: tapered clumps that overlap at the root and part at the tips."""
    out = []
    spec = [  # root x, tip x, tip z, half width at the root
        (-0.060, -0.070, 1.402, 0.015), (-0.042, -0.052, 1.392, 0.017), (-0.022, -0.034, 1.385, 0.016),
        (-0.004, -0.012, 1.398, 0.017), (0.014, 0.008, 1.386, 0.015), (0.031, 0.030, 1.400, 0.017),
        (0.047, 0.050, 1.390, 0.016), (0.063, 0.071, 1.404, 0.014)]
    for i, (xr, xt, zt, hw) in enumerate(spec):
        sweep = -0.006
        pts = []
        for f, z, off in ((0.0, 1.490, 0.0080), (0.3, 1.466, 0.0128), (0.6, 1.440, 0.0128), (0.85, zt + 0.014, 0.0100),
                          (1.0, zt, 0.0072)):
            x = xr + (xt - xr) * f + sweep * f * f
            p, _ = S.head_front([x], [z], off)
            pts.append(p[0])
        V, F, P = lock(pts, 12, lambda t, hw=hw: hw * (1 - t ** 1.3) * (1 - 0.25 * t) + 0.0005,
                       lambda t: 0.0034 * (1 - 0.65 * t) + 0.0004, head_out, sides=6, sharp=0.7)
        out.append(("bang", V, F))
    # Two fine wisps hanging a little lower between the eyes and at her left temple.
    for (xr, xt, zt) in ((-0.016, -0.020, 1.372), (0.052, 0.060, 1.378)):
        pts = []
        for f, z, off in ((0.0, 1.47, 0.011), (0.5, 1.43, 0.0125), (1.0, zt, 0.0075)):
            p, _ = S.head_front([xr + (xt - xr) * f], [z], off)
            pts.append(p[0])
        V, F, P = lock(pts, 10, lambda t: 0.0035 * (1 - t ** 1.2) + 0.0004, lambda t: 0.0013, head_out, sides=6)
        out.append(("bang", V, F))
    return out


def side_locks():
    """Her left side locks (a long one framing the face to the jaw + a shorter one behind it);
    chain hairSideL."""
    main = [(0.056, -0.046, 1.470), (0.069, -0.046, 1.432), (0.074, -0.048, 1.390), (0.071, -0.050, 1.346),
            (0.064, -0.047, 1.306), (0.058, -0.040, 1.272)]
    main = push_out(np.array(main), 0.005)

    def out_side(P):
        return np.stack([P[:, 0], (P[:, 1] + 0.01) * 0.25, np.zeros(len(P))], 1)

    V1, F1, P1 = lock(main, 18, lambda t: 0.0150 + 0.0040 * np.sin(np.pi * np.clip(t * 1.2, 0, 1)) - 0.0180 * t ** 2.5,
                      lambda t: 0.0045 * (1 - 0.55 * t) + 0.0005, out_side, sides=6, twist=0.30, sharp=0.75)
    back = push_out(np.array([(0.064, -0.026, 1.462), (0.077, -0.024, 1.418), (0.079, -0.026, 1.378),
                              (0.075, -0.030, 1.336)]), 0.005)
    V2, F2, _ = lock(back, 12, lambda t: 0.0120 * (1 - t ** 1.6) + 0.0006, lambda t: 0.0036 * (1 - 0.5 * t) + 0.0005,
                     out_side, sides=6, sharp=0.75)
    return [("sideL", V1, F1), ("sideL2", V2, F2)], P1


def updo_locks():
    out = []
    end_dir = norm(BUN_C - S.HEAD_C + np.array([0, -0.01, -0.012]))
    for k, az in enumerate((-120, -100, -150, 180, 150, 100, 120, -165)):
        a = math.radians(az)
        zl = catmull(HAIRLINE, [abs(az)])[0, 0] + 0.010
        # Start direction: azimuth a, at the hairline height.
        dh = np.array([math.sin(a), -math.cos(a), 0.0])
        lo, hi = -1.2, 1.2
        for _ in range(30):
            el = 0.5 * (lo + hi)
            d = np.array([dh[0] * math.cos(el), dh[1] * math.cos(el), math.sin(el)])
            r = S.head_radius(d[None])[0]
            if S.HEAD_C[2] + d[2] * r < zl:
                lo = el
            else:
                hi = el
        d0 = d
        dirs = []
        for f in np.linspace(0, 1, 6):
            v = norm(d0 * (1 - f) + end_dir * f + np.array([0, 0, 0.12]) * math.sin(math.pi * f) * (k % 2) * 0.3)
            dirs.append(v)
        dirs = np.array(dirs)
        P0 = S.HEAD_C + dirs * S.head_radius(dirs)[:, None]
        t = cap_thickness(P0)
        rise = np.linspace(0, 1, len(dirs))
        r = S.head_radius(dirs, off=t * smooth(0.0, 0.35, rise) + 0.0010 + 0.0016 * smooth(0.0, 0.3, rise))
        pts = S.HEAD_C + dirs * r[:, None]
        V, F, P = lock(pts, 12, lambda t: (0.0165 * (1 - 0.35 * t) + 0.002 * np.sin(np.pi * t)) * (0.35 + 0.65 * smooth(0.0, 0.2, t)),
                       lambda t: (0.0030 + 0.0015 * np.sin(np.pi * t)) * (0.4 + 0.6 * smooth(0.0, 0.2, t)), head_out,
                       sides=6, sharp=0.7)
        out.append(("updo", V, F))
    return out


def bun_geo():
    rows, cols = 14, 28
    th = np.linspace(0.08, np.pi - 0.08, rows)
    ph = np.linspace(0, 2 * np.pi, cols, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    ax = BUN_AX
    u = norm(np.cross(ax, np.array([0, 0, 1.0]) if abs(ax[2]) < 0.9 else np.array([1.0, 0, 0])))
    if u[0] < 0:
        u = -u
    v = np.cross(ax, u)
    h = np.cos(TH)
    # A soft round bun, a little flattened along its axis, with a twisted coil.
    coil = 1 + 0.075 * np.sin(3 * PH + 5.0 * h) * np.sin(TH) ** 2
    rx, ry, rh = 0.047, 0.041, 0.035
    lx = rx * np.sin(TH) * np.cos(PH) * coil
    ly = ry * np.sin(TH) * np.sin(PH) * coil
    lh = rh * h
    P = BUN_C + lx[..., None] * u + ly[..., None] * v + lh[..., None] * ax
    V, F = tube(P.reshape(rows, cols, 3), cap_start=True, cap_end=True)
    F = orient(V, F, lambda C: np.tile(BUN_C, (len(C), 1)))
    return V, F


def nape_strands():
    out = []
    for k, (x0, dx, ln) in enumerate(((-0.024, -0.004, 0.085), (0.004, 0.006, 0.098), (0.027, 0.003, 0.080))):
        root = push_out(np.array([[x0, 0.060, 1.338]]), 0.003)[0]
        pts = [root, root + np.array([dx * 0.3, 0.004, -ln * 0.3]), root + np.array([dx, 0.006, -ln * 0.65]),
               root + np.array([dx * 0.4 - 0.004 * (k - 1), 0.010, -ln])]
        pts = np.array(pts)
        pts[:, 1] = np.maximum(pts[:, 1], 0.064)
        V, F, P = lock(pts, 10, lambda t: 0.0042 * (1 - t ** 1.5) + 0.0004, lambda t: 0.0014 + 0.0003 * (1 - t),
                       lambda P: np.tile([0, 1.0, 0.2], (len(P), 1)), sides=6, twist=0.8)
        out.append(("nape", V, F))
    return out


# ---------------------------------------------------------------- kanzashi (her left side of the bun)

K_PIN0 = np.array([0.084, 0.108, 1.486])
K_PIN1 = np.array([-0.030, 0.148, 1.430])
K_DANGLE = np.array([0.071, 0.098, 1.462])


def _ellipsoid(c, ax, ay, az, R, rows=5, cols=8):
    th = np.linspace(0.25, np.pi - 0.25, rows)
    ph = np.linspace(0, 2 * np.pi, cols, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    L = np.stack([ax * np.sin(TH) * np.cos(PH), ay * np.sin(TH) * np.sin(PH), az * np.cos(TH)], -1)
    P = c + L @ R.T
    V, F = tube(P.reshape(rows, cols, 3), cap_start=True, cap_end=True)
    F = orient(V, F, lambda C: np.tile(c, (len(C), 1)))
    return V, F


def _flower(c, nrm, R, rot=0.0):
    """Five rounded petals around a small centre, slightly cupped, facing nrm."""
    nrm = norm(nrm)
    u = norm(np.cross(nrm, [0, 0, 1.0]))
    v = np.cross(nrm, u)
    rings = []
    a = np.linspace(0, 2 * np.pi, 30, endpoint=False) + rot
    prof = 0.55 + 0.45 * np.abs(np.cos(2.5 * a)) ** 0.6
    for rr, h in ((0.0, 0.0018), (0.35, 0.0022), (0.75, 0.0016), (1.0, 0.0004), (0.75, -0.0010), (0.0, -0.0012)):
        r = R * prof * rr
        cup = 0.0025 * rr * rr
        pts = c + np.outer(r * np.cos(a), u) + np.outer(r * np.sin(a), v) + nrm * (h + cup)
        rings.append(pts)
    V, F = tube(np.array(rings))
    F = orient(V, F, lambda C: np.tile(c + nrm * 0.0008, (len(C), 1)))
    return V, F


def kanzashi_geo():
    parts, mats = [], []
    # Pin: a thin gold stick through the bun.
    P = np.array([K_PIN0, K_PIN1])
    d = norm(K_PIN1 - K_PIN0)
    T, N, B = frames_along(spline_points(P, 6))
    path = spline_points(P, 6)
    a = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    rings = [path[i] + np.outer(np.cos(a), N[i]) * 0.0021 + np.outer(np.sin(a), B[i]) * 0.0021 for i in range(6)]
    V, F = tube(np.array(rings), cap_start=True, cap_end=True)
    F = orient(V, F, lambda C: nearest_on_polyline(C, path))
    parts.append((V, F))
    mats.append(0)
    # Flowers (facing out from her left side, a little back and up).
    nrm = norm(np.array([1.0, 0.45, 0.35]))
    for (c, kind, R, rot) in (((0.073, 0.104, 1.497), 1, 0.0150, 0.2), ((0.067, 0.124, 1.480), 2, 0.0135, 0.9),
                              ((0.074, 0.093, 1.474), 1, 0.0115, 1.7)):
        c = np.array(c)
        V, F = _flower(c, nrm, R, rot)
        parts.append((V, F))
        mats.append(kind)
        V, F = _ellipsoid(c + nrm * 0.0028, 0.0026, 0.0026, 0.0018, np.eye(3))
        parts.append((V, F))
        mats.append(0)
    # Two dangles: gold links and a pink bead at the end.
    for k, dy in enumerate((-0.0045, 0.0055)):
        top = K_DANGLE + np.array([0, dy, 0])
        ln = 0.050 if k == 0 else 0.042
        path = np.array([top + np.array([0, 0, -ln * f]) for f in np.linspace(0, 1, 8)])
        T, N, B = frames_along(path, up_hint=(1, 0, 0))
        rings = [path[i] + np.outer(np.cos(a), N[i]) * 0.0007 + np.outer(np.sin(a), B[i]) * 0.0007 for i in range(len(path))]
        V, F = tube(np.array(rings), cap_start=True, cap_end=True)
        F = orient(V, F, lambda C, path=path: nearest_on_polyline(C, path))
        parts.append((V, F))
        mats.append(0)
        for f in (0.3, 0.6):
            V, F = _ellipsoid(top + np.array([0, 0, -ln * f]), 0.0022, 0.0022, 0.0030, np.eye(3))
            parts.append((V, F))
            mats.append(0)
        V, F = _ellipsoid(top + np.array([0, 0, -ln - 0.003]), 0.0045, 0.0045, 0.0050, np.eye(3), 7, 12)
        parts.append((V, F))
        mats.append(3)
    V, F = merge_geo(parts)
    mi = np.concatenate([np.full(len(f), m) for (v, f), m in zip(parts, mats)])
    return V, F, mi


# ---------------------------------------------------------------- build


def build(col):
    m_hair = material("hair", "#5a3325")
    out = {}

    # Chains (rest pose, barefoot frame).
    sides, side_path = side_locks()
    sp = side_path
    pL = [sp[3], sp[len(sp) * 2 // 3], sp[-1]]
    rig.add_chain("hairSideL", pL, "head")
    rig.add_chain("hairSideR", [S.side(p, -1) for p in pL], "head")
    rig.add_chain("hairBack", [np.array([0.0, 0.068, 1.338]), np.array([0.0, 0.072, 1.31]),
                               np.array([0.0, 0.074, 1.28]), np.array([0.0, 0.076, 1.245])], "head")
    rig.add_chain("hairBun", [BUN_C - BUN_AX * 0.02, BUN_C + BUN_AX * 0.045], "head")
    rig.add_chain("kanzashi", [K_DANGLE, K_DANGLE + np.array([0, 0, -0.025]), K_DANGLE + np.array([0, 0, -0.056])],
                  "hairBun1")

    pieces = []      # (V, F, weights)
    V, F = cap_geo()
    pieces.append((V, F, {"head": np.ones(len(V))}))
    for role, V, F in bang_locks():
        pieces.append((V, F, {"head": np.ones(len(V))}))
    for role, V, F in updo_locks():
        k = smooth(1.40, 1.44, V[:, 2]) * smooth(0.06, 0.10, V[:, 1]) * 0.5
        pieces.append((V, F, {"head": 1 - k, "hairBun1": k}))
    for role, V, F in sides:
        z = V[:, 2]
        J = [np.array([0.07, -0.04, 1.47])] + list(rig.chain_points("hairSideL"))
        W, sp_ = rig.chain(V, J, ["head", "hairSideL1", "hairSideL2"], [0.025, 0.02])
        pieces.append((V, F, W))
        Vm, Fm = mirror(V, F)
        pieces.append((Vm, Fm, {rig.L2R(k) if False else k.replace("hairSideL", "hairSideR"): w for k, w in W.items()}))
    V, F = bun_geo()
    k = smooth(-0.025, 0.005, (V - BUN_C) @ BUN_AX)
    pieces.append((V, F, {"head": 1 - k * 0.85, "hairBun1": k * 0.85}))
    for role, V, F in nape_strands():
        J = list(rig.chain_points("hairBack"))
        W, _ = rig.chain(V, [J[0] + np.array([0, 0, 0.02])] + J, ["head", "hairBack1", "hairBack2", "hairBack3"],
                         [0.01, 0.015, 0.015])
        pieces.append((V, F, W))
    V, F = merge_geo([(p[0], p[1]) for p in pieces])
    W = {}
    o = 0
    for (v, f, w) in pieces:
        for bn, val in w.items():
            W.setdefault(bn, np.zeros(len(V)))[o:o + len(v)] += np.broadcast_to(val, (len(v),))
        o += len(v)
    ob = make_mesh("heroine_hair", V, F, col, [m_hair])
    rig.store(ob, W)
    out["hair"] = ob

    # Kanzashi.
    mats = [material("metal_kanzashi", "#cfa95e"), material("plastic_flower_pink", "#f3a6bd"),
            material("plastic_flower_white", "#efe9e4"), material("plastic_bead", "#e56f8c")]
    V, F, mi = kanzashi_geo()
    ob = make_mesh("heroine_kanzashi", V, F, col, mats, mi)
    J = list(rig.chain_points("kanzashi"))
    below = (K_DANGLE[2] + 0.002 - V[:, 2])
    near = np.linalg.norm(V[:, :2] - K_DANGLE[:2], axis=1) < 0.012
    k1 = smooth(0.0, 0.006, below) * near
    Wc, _ = rig.chain(V, J, ["kanzashi1", "kanzashi2"], [0.006])
    W = {"hairBun1": 1 - k1}
    for bn, w in Wc.items():
        W[bn] = w * k1
    rig.store(ob, W)
    out["kanzashi"] = ob
    return out
