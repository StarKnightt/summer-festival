"""Procedural textures (numpy, deterministic): the yukata's morning-glory tile and the eyes.

All colours are sRGB and kept mid-range for toon shading under warm light (no pure white/black).
"""
import math

import numpy as np

from .common import hash1

YUKATA_TILE_M = 0.45      # one texture tile covers 45 x 45 cm of fabric


def _hex(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def _ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def _blend(img, col, a):
    a = np.clip(a, 0, 1)[..., None]
    img[:] = img * (1 - a) + np.asarray(col)[None, None, :] * a


def _wrap(d, n):
    return (d + n / 2) % n - n / 2


def yukata_tile(N=1024, seed=7):
    """Deep indigo cotton with pale pink and white morning glories, a few muted leaves and light-blue
    swirls. Seamless (every element is drawn on a torus)."""
    rng = np.random.default_rng(seed)
    Y, X = np.mgrid[0:N, 0:N].astype(np.float32)
    base = _hex("#2b3a6c")
    img = np.ones((N, N, 3), np.float32) * base
    # Cotton: a faint weave and soft value noise (tileable sums of sines).
    weave = 0.012 * np.sin(X * 2 * math.pi / 4.0) * np.sin(Y * 2 * math.pi / 4.0)
    cloud = sum(0.018 * math.cos(p) * np.sin(2 * math.pi * (kx * X + ky * Y) / N + p)
                for kx, ky, p in ((1, 2, 0.3), (3, 1, 1.7), (2, 5, 2.9), (5, 3, 4.1)))
    img *= (1 + weave + cloud)[..., None]

    def dist(cx, cy):
        dx = _wrap(X - cx, N)
        dy = _wrap(Y - cy, N)
        return dx, dy

    # Swirls first (behind the flowers): Archimedean spirals with a tail.
    swirl_col = _hex("#8fbbe2")
    swirls = [(150, 820, 34, 0.4), (610, 300, 30, 2.2), (880, 700, 36, 4.0), (380, 560, 26, 1.1),
              (930, 120, 28, 5.3)]
    for cx, cy, R, rot in swirls:
        dx, dy = dist(cx, cy)
        r = np.hypot(dx, dy)
        th = (np.arctan2(dy, dx) - rot) % (2 * math.pi)
        best = np.full_like(r, 1e9)
        for k in range(3):  # spiral r = R * (th + 2 pi k) / (3 pi)
            rs = R * (th + 2 * math.pi * k) / (3 * math.pi)
            ok = (th + 2 * math.pi * k) < 3.2 * math.pi
            best = np.where(ok, np.minimum(best, np.abs(r - rs)), best)
        stroke = 1 - _ss(2.2, 3.4, best)
        stroke *= _ss(0, 6, r)
        _blend(img, swirl_col, 0.9 * stroke)
        # A gentle tail sweeping away from the outer end of the spiral.
        ang = rot + 3.2 * math.pi
        ex, ey = cx + R * 1.07 * math.cos(ang), cy + R * 1.07 * math.sin(ang)
        for i in range(36):
            t = i / 35
            px = ex + (t * 70) * math.cos(ang + math.pi / 2) + 18 * math.sin(t * 3)
            py = ey + (t * 70) * math.sin(ang + math.pi / 2) + 18 * math.cos(t * 3)
            ddx, ddy = dist(px, py)
            d = np.hypot(ddx, ddy)
            _blend(img, swirl_col, 0.9 * (1 - _ss(2.2 * (1 - 0.5 * t), 3.4 * (1 - 0.5 * t), d)))

    # Leaves: muted blue-teal hearts, partly hidden by the flowers.
    leaf_col = _hex("#3a6475")
    leaf_vein = _hex("#4d7a8a")
    leaves = [(300, 180, 46, 0.6), (720, 520, 40, 2.5), (90, 450, 42, 4.2), (520, 900, 44, 1.4),
              (860, 950, 38, 3.3), (980, 400, 36, 5.6)]
    for cx, cy, R, rot in leaves:
        dx, dy = dist(cx, cy)
        c, s = math.cos(rot), math.sin(rot)
        u = (dx * c + dy * s) / R
        v = (-dx * s + dy * c) / R
        # Heart: two lobes at the base, a point at +u.
        lobe = np.minimum(np.hypot(u + 0.25, v - 0.38), np.hypot(u + 0.25, v + 0.38)) - 0.55
        tip = np.abs(v) - 0.95 * np.clip(1 - u, 0, 1) ** 1.1 * (u > -0.2)
        d = np.minimum(lobe, np.where(u > -0.2, tip, 9))
        a = 1 - _ss(-0.02, 0.03, d)
        _blend(img, leaf_col, 0.92 * a)
        vein = (1 - _ss(0.015, 0.04, np.abs(v))) * (u > -0.5) * (u < 0.85) * a
        _blend(img, leaf_vein, 0.8 * vein)

    # Morning glories: a round five-pointed trumpet face, paler star rays, a pale throat.
    flowers = [(140, 140, 92, "p"), (470, 260, 78, "w"), (820, 210, 88, "p"), (250, 560, 84, "w"),
               (640, 650, 94, "p"), (980, 560, 74, "w"), (120, 900, 80, "p"), (420, 840, 70, "p"),
               (800, 880, 86, "w"), (560, 470, 46, "p"), (980, 820, 44, "p"), (330, 380, 40, "w")]
    for i, (cx, cy, R, kind) in enumerate(flowers):
        dx, dy = dist(cx, cy)
        r = np.hypot(dx, dy)
        th = np.arctan2(dy, dx) + hash1(i) * 6.28
        rr = R * (1 + 0.075 * np.cos(5 * th))            # five soft points
        a = 1 - _ss(rr - 1.5, rr + 1.0, r)
        if kind == "p":
            rim, mid, ray, edge = _hex("#ef9fb7"), _hex("#f7c9d6"), _hex("#fbe4ea"), _hex("#b86a86")
        else:
            rim, mid, ray, edge = _hex("#e3e1ee"), _hex("#efedf2"), _hex("#f6f4f2"), _hex("#8f8ab0")
        q = np.clip(r / np.maximum(rr, 1), 0, 1)
        col = rim[None, None] * q[..., None] + mid[None, None] * (1 - q[..., None])
        mask = a[..., None]
        img[:] = img * (1 - mask) + col * mask
        # Star rays (five pale bands from the throat to the points).
        band = np.abs(np.sin(2.5 * th))
        rays = (1 - _ss(0.10, 0.22, band)) * _ss(0.15, 0.3, q) * (1 - _ss(0.8, 0.98, q)) * a
        _blend(img, ray, 0.75 * rays)
        # Thin darker rim so the flower reads on the indigo.
        rimline = (1 - _ss(0.0, 2.2, np.abs(r - rr))) * _ss(0.5, 0.9, q)
        _blend(img, edge, 0.7 * rimline)
        # Throat.
        _blend(img, _hex("#f4ead0"), 1 - _ss(0.16 * R, 0.16 * R + 2, r))
        _blend(img, _hex("#e6c98f"), 1 - _ss(0.06 * R, 0.06 * R + 1.5, r))
    return np.clip(img, 0, 1)


# ---------------------------------------------------------------- eyes
# The eye texture covers the rectangle EYE_U (x, metres, inner -> outer) x EYE_V (z, metres) of
# her left eye; the right eye uses it mirrored (same UVs on the mirrored geometry).
EYE_X = (0.0130, 0.0460)
EYE_Z = (1.3680, 1.4030)
IRIS_C = (0.0298, 1.3858)
IRIS_R = (0.0094, 0.0124)


def eye_texture(N=256):
    Y, X = np.mgrid[0:N, 0:N].astype(np.float32)
    x = EYE_X[0] + (X + 0.5) / N * (EYE_X[1] - EYE_X[0])
    z = EYE_Z[1] - (Y + 0.5) / N * (EYE_Z[1] - EYE_Z[0])      # row 0 is the top
    img = np.ones((N, N, 3), np.float32) * _hex("#f1ebe4")
    # Lash shadow across the top of the eye white.
    zt = (z - EYE_Z[0]) / (EYE_Z[1] - EYE_Z[0])
    _blend(img, _hex("#b9b0bf"), 0.75 * _ss(0.55, 0.85, zt))
    cx, cz = IRIS_C
    rx, rz = IRIS_R
    e = np.hypot((x - cx) / rx, (z - cz) / rz)
    aa = 0.06
    iris = 1 - _ss(1 - aa, 1, e)
    # Amber-brown iris: dark at the top (under the lashes), warm amber glowing at the bottom.
    k = np.clip((z - (cz - rz)) / (2 * rz), 0, 1)
    top, low = _hex("#4a2414"), _hex("#d4974e")
    icol = low[None, None] * (1 - k[..., None]) ** 1.0 + top[None, None] * k[..., None]
    icol = icol * (1 - 0.35 * _ss(0.55, 1.0, e))[..., None] + _hex("#4a2414") * 0.35 * _ss(0.55, 1.0, e)[..., None]
    img[:] = img * (1 - iris[..., None]) + icol * iris[..., None]
    # Fine radial streaks and a soft ring.
    ang = np.arctan2(z - cz, x - cx)
    streak = 0.5 + 0.5 * np.sin(ang * 22)
    _blend(img, _hex("#f0c27a"), 0.18 * streak * _ss(0.35, 0.7, e) * (1 - _ss(0.75, 0.95, e)) * (1 - k) * iris)
    ring = (1 - _ss(0.0, 0.07, np.abs(e - 0.97))) * iris
    _blend(img, _hex("#3e1d10"), 0.85 * ring)
    # Pupil.
    ep = np.hypot((x - cx) / (rx * 0.42), (z - (cz + 0.0005)) / (rz * 0.45))
    _blend(img, _hex("#331a10"), 1 - _ss(0.92, 1.0, ep))
    # Highlights: a big soft one upper-outer, a small one lower-inner, a sparkle.
    for (hx, hz, hr, a) in ((cx + 0.36 * rx, cz + 0.44 * rz, 0.36 * rx, 1.0), (cx - 0.40 * rx, cz - 0.50 * rz, 0.17 * rx, 0.9),
                            (cx + 0.50 * rx, cz - 0.20 * rz, 0.10 * rx, 0.8)):
        d = np.hypot(x - hx, (z - hz) * 0.9)
        _blend(img, _hex("#fbf6ef"), a * (1 - _ss(hr * 0.75, hr, d)))
    return np.clip(img, 0, 1)
