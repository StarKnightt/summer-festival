"""Anime faces painted as thin geometry (vertex colours, `face` material) on the analytic head.

Style follows the heroine (tools/blender/heroine/lib/head.py): eyes about 1/6 of the face height on
the head's vertical middle, one eye width apart, an iris that is dark under the lid and warm at the
bottom with a dark rim, a pupil and highlights, a firm upper lash line with a small outer flick and a
thin lower lid line, soft brows, a tiny nose tick, a small mouth and light blush. Adult men get
narrower eyes, heavier brows and (in headshape.py) a stronger jaw; the elder gets crow's feet, an
under-eye line, smile folds and grey brows; the kid a rounder face and bigger eyes.

Every variant has two looks (A and B: eye shape, brow and mouth). They are built with IDENTICAL
topology, so look B is stored as the morph target `face_b` on the near and far meshes (look A is the
basis). Nothing scales the eyes: within a variant both looks keep the eye's width and height within
a few percent; only the shape (lid curves, tilt), brows and mouth change.

All look coordinates are in the heroine's units (u lateral, + = the wearer's left; heights on her
barefoot frame), mapped per variant by headshape.Head.
"""
import math

import numpy as np

from .geo import lerp, smooth, srgb


def catmull(knots, x):
    T = np.asarray(knots, dtype=float)
    xs, ys = T[:, 0], T[:, 1:]
    n = len(xs)
    x = np.clip(np.atleast_1d(np.asarray(x, dtype=float)), xs[0], xs[-1])
    m = np.zeros_like(ys)
    for i in range(n):
        if i == 0:
            m[i] = (ys[1] - ys[0]) / (xs[1] - xs[0])
        elif i == n - 1:
            m[i] = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        else:
            m[i] = (ys[i + 1] - ys[i - 1]) / (xs[i + 1] - xs[i - 1])
    i = np.clip(np.searchsorted(xs, x, side="right") - 1, 0, n - 2)
    x0, x1 = xs[i], xs[i + 1]
    h = (x1 - x0)[:, None]
    t = ((x - x0) / (x1 - x0))[:, None]
    t2, t3 = t * t, t * t * t
    r = ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i]
         + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1])
    return r[:, 0]


def C(h):
    return srgb(h)


# ---------------------------------------------------------------- looks
# Heroine reference (woman A): eye 14.5..44.5 mm out, lids TOP/BOT below, iris centre 1.3858.
HER_TOP = [[0, 1.3800], [0.12, 1.3915], [0.40, 1.3995], [0.72, 1.3990], [0.90, 1.3940], [1.0, 1.3868]]
HER_BOT = [[0, 1.3762], [0.15, 1.3728], [0.50, 1.3708], [0.82, 1.3726], [1.0, 1.3812]]

PALETTE = {   # per variant (vertex colours cannot change between looks)
    "woman": dict(iris_top="#3d1f14", iris_low="#c98a4a", ring="#341a10", pupil="#2a140c", lash="#2e1d1a",
                  brow="#5e3c2e", mouth="#9a4a44", lip="#d39784", nose="#d39784", blush="#f0a09a", white="#f3ede6"),
    "man": dict(iris_top="#2c1a12", iris_low="#8a6040", ring="#25150e", pupil="#1e110b", lash="#231816",
                brow="#2e2220", mouth="#8a4a42", lip="#c98d7a", nose="#c98d7a", blush="#e6a08e", white="#efeae4"),
    "kid": dict(iris_top="#46240f", iris_low="#dba052", ring="#3a1d0e", pupil="#2a150b", lash="#2f1e19",
                brow="#6a4532", mouth="#a04844", lip="#e0a090", nose="#d8a08c", blush="#f39a94", white="#f5f0ea"),
    "keeper": dict(iris_top="#2a1b14", iris_low="#7c5a40", ring="#24160f", pupil="#1d110b", lash="#211715",
                   brow="#2a201e", mouth="#8c463e", lip="#c48a76", nose="#c48a76", blush="#e09a88", white="#efe9e2"),
    "elder": dict(iris_top="#2e2420", iris_low="#7a6656", ring="#2a201c", pupil="#211915", lash="#3a2c28",
                  brow="#9a938e", mouth="#9a5a52", lip="#d4a090", nose="#cf9a88", blush="#eea8a0", white="#efe9e2",
                  line="#c08a7c"),
}


def _brow(x0, x1, z0, arch, slope, w0, w1, wa=0.0):
    """Brow centre line z(s) = z0 + arch*sin(pi(0.85 s + 0.1)) - slope*s; width w(s) (full)."""
    return dict(x0=x0, x1=x1, z0=z0, arch=arch, slope=slope, w0=w0, w1=w1, wa=wa)


LOOKS = {
    "woman": {
        "A": dict(x0=0.0145, x1=0.0445, top=HER_TOP, bot=HER_BOT, iris=(0.51, 1.3858, 0.0094, 0.0124),
                  lash=(0.0011, 0.0021), flick=1.0, lower=1.0, crease=0.00045,
                  brow=_brow(0.0120, 0.0465, 1.4130, 0.0032, 0.0022, 0.0013, 0.0007, 0.0006),
                  mouth=dict(z=1.3180, hw=0.0066, smile=0.0007, open=0.0, skew=0.0, w=0.00055),
                  blush=(0.0370, 1.3595, 0.0100, 0.0040)),
        "B": dict(x0=0.0145, x1=0.0445,
                  top=[[0, 1.3796], [0.12, 1.3898], [0.40, 1.3984], [0.72, 1.3996], [0.90, 1.3966], [1.0, 1.3904]],
                  bot=[[0, 1.3766], [0.15, 1.3722], [0.50, 1.3712], [0.82, 1.3742], [1.0, 1.3866]],
                  iris=(0.52, 1.3862, 0.0094, 0.0124), lash=(0.0012, 0.0023), flick=1.25, lower=0.8, crease=0.0,
                  brow=_brow(0.0125, 0.0460, 1.4152, 0.0016, 0.0006, 0.0010, 0.0005, 0.0004),
                  mouth=dict(z=1.3176, hw=0.0058, smile=0.0010, open=0.0036, skew=0.0, w=0.00050),
                  blush=(0.0370, 1.3600, 0.0095, 0.0036)),
    },
    "man": {
        "A": dict(x0=0.0150, x1=0.0450,
                  top=[[0, 1.3815], [0.12, 1.3888], [0.40, 1.3934], [0.72, 1.3936], [0.90, 1.3908], [1.0, 1.3852]],
                  bot=[[0, 1.3790], [0.15, 1.3762], [0.50, 1.3750], [0.82, 1.3762], [1.0, 1.3822]],
                  iris=(0.50, 1.3846, 0.0085, 0.0108), lash=(0.0009, 0.0017), flick=0.25, lower=0.6, crease=0.0,
                  brow=_brow(0.0100, 0.0480, 1.4060, 0.0010, 0.0004, 0.0030, 0.0018, 0.0006),
                  mouth=dict(z=1.3168, hw=0.0080, smile=0.0003, open=0.0, skew=0.0, w=0.00050),
                  blush=(0.0370, 1.3600, 0.0, 0.0)),
        "B": dict(x0=0.0150, x1=0.0450,
                  top=[[0, 1.3818], [0.12, 1.3898], [0.40, 1.3938], [0.72, 1.3926], [0.90, 1.3888], [1.0, 1.3828]],
                  bot=[[0, 1.3792], [0.15, 1.3760], [0.50, 1.3748], [0.82, 1.3752], [1.0, 1.3802]],
                  iris=(0.50, 1.3844, 0.0085, 0.0108), lash=(0.0009, 0.0016), flick=0.1, lower=0.5, crease=0.0,
                  brow=_brow(0.0105, 0.0478, 1.4078, 0.0016, 0.0018, 0.0034, 0.0016, 0.0004),
                  mouth=dict(z=1.3170, hw=0.0074, smile=0.0002, open=0.0, skew=0.0011, w=0.00052),
                  blush=(0.0370, 1.3600, 0.0, 0.0)),
    },
    "kid": {
        "A": dict(x0=0.0150, x1=0.0470,
                  top=[[0, 1.3810], [0.12, 1.3945], [0.40, 1.4035], [0.72, 1.4036], [0.90, 1.3986], [1.0, 1.3896]],
                  bot=[[0, 1.3770], [0.15, 1.3720], [0.50, 1.3694], [0.82, 1.3712], [1.0, 1.3800]],
                  iris=(0.51, 1.3868, 0.0110, 0.0142), lash=(0.0011, 0.0019), flick=0.7, lower=0.8, crease=0.0,
                  brow=_brow(0.0160, 0.0440, 1.4200, 0.0030, 0.0012, 0.0011, 0.0006, 0.0004),
                  mouth=dict(z=1.3180, hw=0.0062, smile=0.0010, open=0.0062, skew=0.0, w=0.00050),
                  blush=(0.0385, 1.3585, 0.0118, 0.0048)),
        "B": dict(x0=0.0150, x1=0.0470,
                  top=[[0, 1.3812], [0.12, 1.3952], [0.40, 1.4030], [0.72, 1.4026], [0.90, 1.3972], [1.0, 1.3882]],
                  bot=[[0, 1.3774], [0.15, 1.3716], [0.50, 1.3690], [0.82, 1.3700], [1.0, 1.3786]],
                  iris=(0.50, 1.3862, 0.0110, 0.0142), lash=(0.0011, 0.0018), flick=0.4, lower=0.8, crease=0.0,
                  brow=_brow(0.0155, 0.0445, 1.4215, 0.0038, 0.0004, 0.0012, 0.0007, 0.0004),
                  mouth=dict(z=1.3185, hw=0.0072, smile=0.0019, open=0.0, skew=0.0, w=0.00055),
                  blush=(0.0385, 1.3590, 0.0122, 0.0050)),
    },
    "keeper": {
        "A": dict(x0=0.0150, x1=0.0450,
                  top=[[0, 1.3808], [0.12, 1.3892], [0.40, 1.3946], [0.72, 1.3950], [0.90, 1.3922], [1.0, 1.3862]],
                  bot=[[0, 1.3784], [0.15, 1.3752], [0.50, 1.3738], [0.82, 1.3750], [1.0, 1.3818]],
                  iris=(0.50, 1.3848, 0.0088, 0.0112), lash=(0.0010, 0.0018), flick=0.35, lower=0.6, crease=0.0,
                  brow=_brow(0.0100, 0.0478, 1.4048, 0.0012, -0.0022, 0.0032, 0.0018, 0.0006),
                  mouth=dict(z=1.3172, hw=0.0084, smile=0.0006, open=0.0068, skew=0.0, w=0.00055),
                  blush=(0.0370, 1.3600, 0.0, 0.0)),
        "B": dict(x0=0.0150, x1=0.0450,
                  top=[[0, 1.3806], [0.12, 1.3896], [0.40, 1.3950], [0.72, 1.3946], [0.90, 1.3910], [1.0, 1.3850]],
                  bot=[[0, 1.3786], [0.15, 1.3750], [0.50, 1.3738], [0.82, 1.3744], [1.0, 1.3808]],
                  iris=(0.50, 1.3848, 0.0088, 0.0112), lash=(0.0010, 0.0018), flick=0.3, lower=0.6, crease=0.0,
                  brow=_brow(0.0102, 0.0476, 1.4092, 0.0030, 0.0006, 0.0030, 0.0016, 0.0005),
                  mouth=dict(z=1.3178, hw=0.0086, smile=0.0017, open=0.0, skew=0.0, w=0.00058),
                  blush=(0.0370, 1.3600, 0.0, 0.0)),
    },
    "elder": {
        "A": dict(x0=0.0150, x1=0.0440,
                  top=[[0, 1.3800], [0.12, 1.3868], [0.40, 1.3916], [0.72, 1.3914], [0.90, 1.3882], [1.0, 1.3826]],
                  bot=[[0, 1.3782], [0.15, 1.3770], [0.50, 1.3764], [0.82, 1.3768], [1.0, 1.3798]],
                  iris=(0.50, 1.3842, 0.0080, 0.0098), lash=(0.0009, 0.0015), flick=0.2, lower=0.0, crease=0.00040,
                  brow=_brow(0.0125, 0.0460, 1.4110, 0.0022, 0.0028, 0.0013, 0.0006, 0.0004),
                  mouth=dict(z=1.3172, hw=0.0068, smile=0.0013, open=0.0, skew=0.0, w=0.00050),
                  blush=(0.0370, 1.3595, 0.0092, 0.0036), lines=1.0),
        "B": dict(x0=0.0150, x1=0.0440,
                  top=[[0, 1.3802], [0.12, 1.3874], [0.40, 1.3924], [0.72, 1.3918], [0.90, 1.3880], [1.0, 1.3818]],
                  bot=[[0, 1.3780], [0.15, 1.3762], [0.50, 1.3754], [0.82, 1.3758], [1.0, 1.3792]],
                  iris=(0.50, 1.3840, 0.0080, 0.0098), lash=(0.0009, 0.0015), flick=0.1, lower=0.0, crease=0.00040,
                  brow=_brow(0.0122, 0.0462, 1.4114, 0.0016, 0.0034, 0.0012, 0.0005, 0.0003),
                  mouth=dict(z=1.3170, hw=0.0050, smile=0.0004, open=0.0026, skew=0.0, w=0.00048),
                  blush=(0.0370, 1.3595, 0.0088, 0.0034), lines=1.0),
    },
}

# Topmost brow point and bang limit per variant (heroine units): bangs end above the brows, glasses
# stay below them. Filled by brow_top().


def brow_top(v):
    z = -1.0
    for L in LOOKS[v].values():
        b = L["brow"]
        s = np.linspace(0, 1, 30)
        zc = b["z0"] + b["arch"] * np.sin(np.pi * (s * 0.85 + 0.1)) - b["slope"] * s
        w = b["w0"] * (1 - s) + b["w1"] * s + b["wa"] * np.sin(np.pi * s)
        z = max(z, float((zc + w / 2).max()))
    return z


def eye_extent(v):
    """(u_outer, z_top, z_bottom) over both looks, heroine units: for sizing the glasses."""
    uo, zt, zb = 0.0, -1.0, 9.0
    for L in LOOKS[v].values():
        s = np.linspace(0, 1, 40)
        zt = max(zt, float(catmull(L["top"], s).max()))
        zb = min(zb, float(catmull(L["bot"], s).min()))
        uo = max(uo, L["x1"])
    return uo, zt, zb


# ---------------------------------------------------------------- geometry helpers

class Parts:
    """Decal parts: (V (n,3), F, C (n,3), tag)."""

    def __init__(self, head):
        self.h = head
        self.items = []

    def grid(self, U, Z, cols, off, tag):
        """Grid of face coords U, Z (rows, cols) at offset off (heroine m) -> faces outward."""
        rows, nc = U.shape
        P, N = self.h.face(U.ravel(), Z.ravel(), off)
        F = []
        for r in range(rows - 1):
            for c in range(nc - 1):
                a = r * nc + c
                F.append([a, a + 1, a + nc + 1, a + nc])
        F = _orient(P, F, N)
        self.items.append((P, F, np.asarray(cols, float).reshape(-1, 3), tag))

    def polar(self, cu, cz, R, A, ring_uz, cols, ccol, off, tag):
        """Centre + rings: ring_uz (nr, na, 2)."""
        ring_uz = np.asarray(ring_uz, float)
        nr, na = ring_uz.shape[:2]
        U = np.concatenate([[cu], ring_uz[..., 0].ravel()])
        Zz = np.concatenate([[cz], ring_uz[..., 1].ravel()])
        P, N = self.h.face(U, Zz, off)
        F = [[0, 1 + j, 1 + (j + 1) % na] for j in range(na)]
        for i in range(nr - 1):
            for j in range(na):
                a = 1 + i * na + j
                b = 1 + i * na + (j + 1) % na
                F.append([a, b, b + na, a + na])
        F = _orient(P, F, N)
        Cc = np.vstack([np.asarray(ccol, float)[None], np.asarray(cols, float).reshape(-1, 3)])
        self.items.append((P, F, Cc, tag))

    def stroke(self, us, zs, widths, col, off, tag, cols2=None):
        """A band along a polyline in face coords with per-point full width."""
        us, zs = np.asarray(us, float), np.asarray(zs, float)
        m = len(us)
        w = np.broadcast_to(np.asarray(widths, float), (m,))
        L, R = [], []
        for i in range(m):
            t = np.array([us[min(i + 1, m - 1)] - us[max(i - 1, 0)], zs[min(i + 1, m - 1)] - zs[max(i - 1, 0)]])
            t = t / max(np.linalg.norm(t), 1e-9)
            nn = np.array([-t[1], t[0]])
            L.append([us[i] + nn[0] * w[i] / 2, zs[i] + nn[1] * w[i] / 2])
            R.append([us[i] - nn[0] * w[i] / 2, zs[i] - nn[1] * w[i] / 2])
        G = np.array([L, R])
        cc = np.asarray(col, float)
        if cols2 is None:
            cols2 = np.tile(cc, (2, m, 1))
        self.grid(G[..., 0], G[..., 1], cols2, off, tag)

    def mirrored(self, fn):
        """Build fn(sg) for sg = +1 (wearer's left) and -1."""
        for sg in (1.0, -1.0):
            fn(sg)


def _orient(P, F, N):
    out = []
    for f in F:
        p = P[f]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if len(f) == 4:
            n = n + np.cross(p[2] - p[0], p[3] - p[0])
        out.append(f if n @ N[f].mean(0) >= 0 else f[::-1])
    return out


def _ss(e0, e1, x):
    return float(smooth(e0, e1, x))


# ---------------------------------------------------------------- the face

def build(head, v, look, detail="near", blink=0.0, smile=0.0):
    """All face decals of variant v in `look` ('A' | 'B') -> Parts. detail: 'near' | 'far'.
    blink / smile (0..1) only move vertices (same topology), so the differences are morph targets:
    blink drops the upper lid onto the lower one (the white, iris and highlights collapse under the
    lash line, which becomes a closed-eye arc); smile lifts the mouth corners, widens the mouth a
    touch and raises the lower lids (a happy squint)."""
    L = LOOKS[v][look]
    pal = {k: C(h) for k, h in PALETTE[v].items()}
    near = detail == "near"
    pp = Parts(head)
    x0, x1 = L["x0"], L["x1"]
    ew = x1 - x0

    def top0(s):
        return catmull(L["top"], s)

    def bot0(s):
        return catmull(L["bot"], s)

    def bot(s):
        t_, b_ = top0(s), bot0(s)
        ss = np.clip(np.asarray(s, float), 0, 1)
        return b_ + smile * 0.18 * (t_ - b_) * np.sin(np.pi * ss) ** 0.7

    def top(s):
        t_, b_ = top0(s), bot(s)
        return t_ + blink * (b_ + 0.02 * (t_ - b_) - t_)

    def eye(sg):
        # --- eye white between the lids, a lash shadow across its top
        ns, nt = (13, 6) if near else (6, 3)
        s = (1 - np.cos(np.linspace(0, math.pi, ns))) / 2
        t = np.linspace(0, 1, nt)
        U = np.tile(sg * (x0 + s * ew), (nt, 1))
        Z = bot(s)[None, :] + t[:, None] * (top(s) - bot(s))[None, :]
        cols = np.array([[lerp(pal["white"], C("#b8aebd"), 0.8 * _ss(0.5, 0.92, tt)) for _ in s] for tt in t])
        pp.grid(U, Z, cols, 0.0007, "eye")
        # --- iris (polar), clamped between the lids
        sc, zc, rx, rz = L["iris"]
        cu = sg * (x0 + sc * ew)
        rings = [0.22, 0.42, 0.56, 0.70, 0.83, 0.93, 1.0] if near else [0.40, 1.0]
        na = 20 if near else 10
        ang = np.linspace(0, 2 * math.pi, na, endpoint=False)
        R_, C_ = [], []
        for r in rings:
            row, crow = [], []
            for a in ang:
                u = cu + rx * r * math.sin(a)
                z = zc + rz * r * math.cos(a)
                ss_ = float(np.clip((sg * u - x0) / ew, 0.0, 1.0))
                zcl = float(np.clip(z, bot(ss_)[0] + 0.00035, top(ss_)[0] - 0.00025))
                row.append([u, zcl])
                k = float(np.clip((z - (zc - rz)) / (2 * rz), 0, 1))
                c = pal["iris_low"] * (1 - k) + pal["iris_top"] * k
                c = c * (1 - 0.35 * _ss(0.55, 1.0, r)) + pal["iris_top"] * 0.35 * _ss(0.55, 1.0, r)
                if r >= 0.99:
                    c = lerp(c, pal["ring"], 0.85)
                if r <= 0.30:
                    c = pal["pupil"]
                elif r <= 0.45 and near:
                    c = lerp(c, pal["pupil"], 0.55)
                crow.append(c)
            R_.append(row)
            C_.append(crow)
        pp.polar(cu, float(np.clip(zc, bot(sc)[0], top(sc)[0])), rx, rz, R_, C_, pal["pupil"], 0.0010, "iris")
        # --- highlights: a big soft one upper-outer, a small one lower-inner, a sparkle (heroine)
        hls = ((0.36, 0.44, 0.36, 12), (-0.40, -0.50, 0.17, 8), (0.50, -0.20, 0.10, 6)) if near else ((0.36, 0.40, 0.42, 6),)
        for ox, oz, hr, n in hls:
            hu, hz = cu + sg * ox * rx, zc + oz * rz
            if blink > 0:
                sh = float(np.clip((sg * hu - x0) / ew, 0.0, 1.0))
                hz = float(np.clip(hz, bot(sh)[0], top(sh)[0]))
                hr = hr * (1 - blink)
            a = np.linspace(0, 2 * math.pi, n, endpoint=False)
            ring = [[[hu + hr * rx * math.sin(q), hz + hr * rx * 1.1 * math.cos(q)] for q in a]]
            pp.polar(hu, hz, 0, 0, ring, [[C("#fbf6ef")] * n], C("#fbf6ef"), 0.0016, "highlight")
        # --- upper lash line: thickest toward the outer corner, a small flick out and up
        w0, w1 = L["lash"]
        ncol = 16 if near else 8
        s = np.linspace(-0.04, 1.0, ncol)
        sc_ = np.clip(s, 0, 1)
        tp = top(sc_)
        w = w0 + w1 * sc_ ** 1.1 - 0.0008 * sc_ ** 6
        lo, hi = tp - 0.0008, tp + w
        fl = L["flick"]
        fx = x1 + np.array([0.0018, 0.0034, 0.0047]) * max(fl, 0.05)
        flo = tp[-1] + np.array([-0.0003, 0.0007, 0.0019]) * fl
        fhi = flo + np.array([0.0024, 0.0016, 0.0007]) * max(fl, 0.3)
        if not near:
            fx, flo, fhi = fx[:1], flo[:1], fhi[:1]
        xs = sg * np.concatenate([x0 + s * ew, fx])
        U = np.stack([xs, xs])
        Z = np.stack([np.concatenate([lo, flo]), np.concatenate([hi, fhi])])
        pp.grid(U, Z, np.tile(pal["lash"], (2, len(xs), 1)), 0.0015, "lash")
        if near:
            # thin lower lid line on the outer half
            s = np.linspace(0.45, 1.0, 8)
            bt = bot(s)
            w = (0.00030 + 0.00050 * (s - 0.45) / 0.55) * L["lower"] + 1e-6
            xs = sg * (x0 + s * ew)
            pp.grid(np.stack([xs, xs]), np.stack([bt - w, bt + 0.0002 * min(L["lower"], 1.0) + 1e-6]),
                    np.tile(lerp(pal["lash"], pal["mouth"], 0.35), (2, 8, 1)), 0.0013, "lash")
            # eyelid crease (soft) above the lash line
            s = np.linspace(0.12, 0.92, 6)
            zc_ = top(s) + 0.0042 + 0.0006 * np.sin(np.pi * s)
            xs = sg * (x0 + s * ew)
            wc = L["crease"] * np.sin(np.pi * np.linspace(0.1, 0.9, 6)) + 1e-6
            pp.grid(np.stack([xs, xs]), np.stack([zc_ - wc / 2, zc_ + wc / 2]),
                    np.tile(lerp(pal["lash"], pal["nose"], 0.55), (2, 6, 1)), 0.0009, "crease")
        # --- brow
        b = L["brow"]
        nb = 9 if near else 5
        s = np.linspace(0, 1, nb)
        xs = sg * (b["x0"] + s * (b["x1"] - b["x0"]))
        zcb = b["z0"] + b["arch"] * np.sin(np.pi * (s * 0.85 + 0.1)) - b["slope"] * s - 0.0008 * blink + 0.0004 * smile
        w = b["w0"] * (1 - s) + b["w1"] * s + b["wa"] * np.sin(np.pi * s)
        w = w * (0.55 + 0.45 * np.sin(np.pi * np.clip(s * 0.9 + 0.1, 0, 1)) ** 0.5)
        cols = np.tile(pal["brow"], (2, nb, 1))
        pp.grid(np.stack([xs, xs]), np.stack([zcb - w / 2, zcb + w / 2]), cols, 0.0012, "brow")
        # --- elder: crow's feet, under-eye line (both looks)
        if L.get("lines") and near:
            for k, (a0, da) in enumerate(((0.10, 0.0026), (-0.25, 0.0022))):
                ux = x1 + 0.0022 + np.linspace(0, 1, 4) * 0.0050
                uz = top0(1.0)[0] - 0.0012 + a0 * 0.01 + np.linspace(0, 1, 4) * (0.0016 if k == 0 else -0.0018)
                wl = 0.00045 * np.sin(np.linspace(0.3, 2.8, 4)) * L["lines"] + 1e-6
                pp.stroke(sg * ux, uz, wl, pal["line"], 0.0009, "line")
            s = np.linspace(0.30, 0.95, 5)
            pp.stroke(sg * (x0 + s * ew), bot0(s) - 0.0034 - 0.0006 * np.sin(np.pi * s),
                      0.00042 * np.sin(np.linspace(0.3, 2.8, 5)) * L["lines"] + 1e-6, pal["line"], 0.0009, "line")

    pp.mirrored(eye)

    def cheek(sg):
        bu, bz, brx, brz = L["blush"]
        bz = bz + 0.0012 * smile
        nr = 12 if near else 8
        a = np.linspace(0, 2 * math.pi, nr, endpoint=False)
        rr = (0.6, 1.0) if near else (1.0,)
        ring = [[[sg * bu + brx * f * math.sin(q), bz + brz * f * math.cos(q)] for q in a] for f in rr]
        cols = [[pal["blush"]] * nr for _ in rr]
        pp.polar(sg * bu, bz, brx, brz, ring, cols, pal["blush"], 0.0006, "blush")
        if L.get("lines") and near:
            # smile fold from beside the nose wing toward the mouth corner
            t = np.linspace(0, 1, 5)
            us = 0.0105 + 0.0040 * t + 0.0008 * np.sin(np.pi * t)
            zs = 1.3405 - 0.0190 * t
            pp.stroke(sg * us, zs, 0.00050 * np.sin(np.linspace(0.3, 2.8, 5)) * L["lines"] + 1e-6, pal["line"],
                      0.0009, "line")

    pp.mirrored(cheek)
    # --- nose: a tiny shadow tick under the tip, on the wearer's right
    nn = 5 if near else 3
    s = np.linspace(-1, 1, nn)
    nz = 1.3385 * (1.0 if v != "kid" else 1.0) + 0.0005 * s * s
    nwid = 0.00070 + 0.00050 * (1 - np.abs(s))
    pp.stroke(0.0026 * s - 0.0007, nz, nwid, pal["nose"], 0.0010, "nose")
    # --- mouth: three rows (dark line, dark, a warmer lower edge / tongue); closed looks collapse
    # the rows to a soft line, open looks spread them into a small D
    M = L["mouth"]
    nm = 11 if near else 7
    s = np.linspace(-1, 1, nm)
    sm = s * (1 + M["skew"] / max(M["hw"], 1e-6) * 0.0)
    zl = M["z"] - 0.0003 * (1 - s * s) + (M["smile"] + 0.0020 * smile) * s ** 2 + M["skew"] * np.clip(s, 0, 1) ** 2
    u = s * M["hw"] * (1 + 0.10 * smile)
    op = M["open"] * np.clip(1 - s * s, 0, 1) ** 0.85
    wl = M["w"] * (0.55 + 0.45 * np.clip(1 - np.abs(s), 0, 1) ** 0.6)
    rows_z = [zl + wl / 2, zl - wl / 2 - op * 0.45, zl - wl / 2 - op]
    rc = [pal["mouth"] * 0.62, pal["mouth"] * 0.72, lerp(pal["mouth"], C("#e08a80"), 0.75 if M["open"] > 0 else 0.25)]
    U = np.tile(u, (3, 1))
    pp.grid(U, np.array(rows_z), np.array([[c] * nm for c in rc]), 0.0010, "mouth")
    if near:
        # faint lower-lip shade
        s = np.linspace(-1, 1, 7)
        zc_ = M["z"] - 0.0030 - M["open"] * 0.9 + 0.0003 * s * s
        w = 0.0004 * (1 - s * s) + 5e-5
        pp.grid(np.tile(s * 0.0035, (2, 1)), np.stack([zc_ - w, zc_ + w]), np.tile(pal["lip"], (2, 7, 1)), 0.0009, "lip")
    return pp


MORPHS = ("blink", "smile")


def build_pair(head, v, detail):
    """Both looks + the expression morphs with identical topology:
    -> list of (V_A, V_B, F, C, tag, {morph: V})  (blink / smile are deltas on look A)."""
    a = build(head, v, "A", detail).items
    b = build(head, v, "B", detail).items
    ex = {m: build(head, v, "A", detail, **{m: 1.0}).items for m in MORPHS}
    assert len(a) == len(b), (v, detail)
    out = []
    for i, ((Va, Fa, Ca, ta), (Vb, Fb, Cb, tb)) in enumerate(zip(a, b)):
        assert Va.shape == Vb.shape and ta == tb, (v, ta, Va.shape, Vb.shape)
        mv = {}
        for m in MORPHS:
            Vm, Fm, Cm, tm = ex[m][i]
            assert Vm.shape == Va.shape and tm == ta, (v, m, ta)
            mv[m] = Vm
        out.append((Va, Vb, Fa, Ca, ta, mv))
    return out
