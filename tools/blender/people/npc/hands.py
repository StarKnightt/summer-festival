"""Hands with five separate fingers in a relaxed curl (thumb opposed), skinned to the finger bones
finger_<f>_<1|2>_<L|R> (rig.finger_joints gives the rest joints, which ARE the relaxed pose).

near: palm + thenar pad, round finger tubes (7 sides) with a knuckle bulge and a soft nail tint.
far : the same layout at 4 sides and fewer rings: still reads as a relaxed hand, not a mitten.
"""
import math

import numpy as np

from .geo import loft, lerp, norm, orient_out, ring, sweep, ellipsoid
from .rig import FINGERS, chain, finger_joints, hand_frame


def _poly_param(P, q):
    """Arc length of the closest point on polyline P to q."""
    best, acc, sbest = 1e9, 0.0, 0.0
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        ab = b - a
        L = float(np.linalg.norm(ab))
        t = float(np.clip((q - a) @ ab / max(L * L, 1e-12), 0, 1))
        dd = float(np.linalg.norm(a + ab * t - q))
        if dd < best:
            best, sbest = dd, acc + t * L
        acc += L
    return sbest


def build(mb, J, side, detail="near", mat="skin", meta=None):
    near = detail == "near"
    d, s, n = hand_frame(J, side)
    wr = J[f"wr_{side}"]
    hl = J["P"]["hand"]
    k = hl / 0.15
    FJ = finger_joints(J, side)
    # ---- palm: rings across (s, n) from the wrist to just past the knuckles
    Lp = 0.50 * hl
    ts = np.array([-0.06, 0.0, 0.25, 0.55, 0.85, 1.0]) if near else np.array([-0.06, 0.3, 0.75, 1.0])
    wid = np.interp(ts, [-0.06, 0.0, 0.3, 0.7, 1.0], [0.024, 0.026, 0.033, 0.036, 0.034]) * k
    thk = np.interp(ts, [-0.06, 0.0, 0.3, 0.7, 1.0], [0.016, 0.016, 0.015, 0.013, 0.011]) * k
    rings = []
    for t, w, h in zip(ts, wid, thk):
        c = wr + d * (t * Lp) + n * 0.001 * k + s * 0.001 * k
        rings.append(ring(c, s, n, w, h, p=2.6))
    V, F, U, RI, TH = loft(rings, 12 if near else 8, cap0=True, cap1=True)
    cents = np.array([r.center for r in rings])
    F = orient_out(V, F, lambda q: cents[int(np.argmin(np.linalg.norm(cents - q, axis=1)))])
    wfun = lambda q: chain(float((q - wr) @ d), [0.0], [f"forearm_{side}", f"hand_{side}"], 0.02 * k)
    mb.add(V, F, mat, wfun, tag="palm")
    # thenar pad (the thumb's ball) on the palm side toward the thumb
    if near:
        c = wr + d * 0.20 * hl + s * 0.016 * k + n * 0.008 * k
        V, F, U = ellipsoid(c, (s, n, d), (0.016 * k, 0.009 * k, 0.030 * k), 8, 5)
        mb.add(V, F, mat, {f"hand_{side}": 1.0}, tag="thenar")
    # ---- fingers
    nside = 7 if near else 4
    for f in FINGERS:
        base, mid, tip, r = FJ[f]
        L1 = float(np.linalg.norm(mid - base))
        L2 = float(np.linalg.norm(tip - mid))
        d1 = norm(mid - base)
        d2 = norm(tip - mid)
        back = base - d1 * (0.012 if f != "thumb" else 0.010) * k
        if near:
            pts = [back, base, lerp(base, mid, 0.5), mid, mid + d2 * L2 * 0.45, mid + d2 * L2 * 0.82, tip]
            rr = np.array([1.05, 1.06, 0.97, 1.0, 0.90, 0.82, 0.55]) * r
        else:
            pts = [back, base, mid, mid + d2 * L2 * 0.75, tip]
            rr = np.array([1.05, 1.05, 0.95, 0.80, 0.45]) * r
        pts = np.array(pts)
        flat = 0.82 if f != "thumb" else 0.88       # fingers a little flatter across the nail side
        V, F, U, RI = sweep(pts, rr, nside, r2=rr * flat, up=-n)
        P = np.array([back, base, mid, tip])
        b1, b2 = f"finger_{f}_1_{side}", f"finger_{f}_2_{side}"
        s0 = float(np.linalg.norm(base - back))

        def wf(q, P=P, s0=s0, L1=L1, b1=b1, b2=b2, f=f):
            t = _poly_param(P, q)
            return chain(t, [s0 * 0.9, s0 + L1], [f"hand_{side}", b1, b2], 0.0045 * k)
        C = np.ones((len(V), 3))
        if near:
            # soft nail tint on the back of the last segment
            for i, q in enumerate(V):
                tq = float((q - mid) @ d2)
                if tq > L2 * 0.62 and float((q - tip) @ (-n if f != "thumb" else norm(np.cross(d2, s)))) > -0.0005:
                    C[i] = (1.0, 0.90, 0.88)
        mb.add(V, F, mat, wf, C=C, tag=f"finger_{f}")
    if meta is not None:
        meta.setdefault("grip", {})[side] = dict(point=(wr + d * hl * 0.45 + n * 0.012 * k).tolist(),
                                                 axis=s.tolist(), palm=n.tolist())
