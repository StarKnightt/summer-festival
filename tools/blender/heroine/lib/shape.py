"""Her proportions, joints and the analytic surfaces the body, clothes and rig share.

Barefoot frame (the floor under her bare feet is z = 0; the whole model is lifted by SOLE, the
geta height, at the end of the build). Blender frame: +Z up, facing -Y, +X her left.

About 1.58 m to the top of the hair when standing in geta: 1.53 m barefoot (skull 1.505 + hair),
head 0.22 m chin to crown (6.95 heads barefoot), slim and gentle, long-legged anime proportions.
"""
import numpy as np

from .common import catmull, norm, smin, smooth

SOLE = 0.050          # geta: 16 mm plate + 34 mm teeth
HEAD_C = np.array([0.0, 0.005, 1.400])
CROWN_Z, CHIN_Z = 1.505, 1.291

J = {
    "root": (0.0, 0.0, 0.0),
    "hips": (0.0, 0.000, 0.880),
    "spine": (0.0, 0.000, 0.960),
    "spine1": (0.0, -0.004, 1.050),
    "spine2": (0.0, -0.002, 1.140),
    "neck": (0.0, 0.012, 1.235),
    "head": (0.0, 0.012, 1.315),
    "head_end": (0.0, 0.012, 1.500),
}

# Arms in a relaxed A: 30 degrees out from vertical, elbows a touch bent, palms in.
CLAV = np.array([0.025, 0.000, 1.212])
SH = np.array([0.150, 0.006, 1.212])
UP_LEN, FORE_LEN = 0.245, 0.215
_a1 = norm(np.array([0.5, 0.0, -0.866]))
ELB = SH + _a1 * UP_LEN
_a2 = norm(np.array([0.49, -0.08, -0.866]))
WRI = ELB + _a2 * FORE_LEN
HIP = np.array([0.085, 0.000, 0.800])
KNEE = np.array([0.078, -0.008, 0.440])
ANKLE = np.array([0.072, 0.020, 0.075])
BALL = np.array([0.076, -0.098, 0.018])
TOE = np.array([0.078, -0.168, 0.012])
HEEL_Y = 0.064


def side(p, s):
    p = np.array(p, dtype=float)
    p[..., 0] *= s
    return p


# ---------------------------------------------------------------- yukata body surface
# Rings: z, half-width a, half-depth b, centre y. The cloth surface (the skin under it is inset).
YUKATA = np.array([
    [0.070, 0.108, 0.084, -0.006],
    [0.120, 0.110, 0.084, -0.006],
    [0.250, 0.118, 0.085, -0.006],
    [0.400, 0.130, 0.088, -0.004],
    [0.550, 0.145, 0.092, 0.000],
    [0.700, 0.160, 0.098, 0.006],
    [0.800, 0.168, 0.100, 0.008],
    [0.880, 0.160, 0.095, 0.005],
    [0.950, 0.136, 0.086, 0.000],
    [1.000, 0.123, 0.081, 0.000],
    [1.050, 0.128, 0.085, -0.004],
    [1.100, 0.140, 0.092, -0.008],
    [1.150, 0.150, 0.086, -0.002],
    [1.180, 0.165, 0.082, 0.002],
    [1.205, 0.177, 0.078, 0.004],
    [1.228, 0.178, 0.074, 0.006],
    [1.246, 0.160, 0.068, 0.008],
    [1.256, 0.118, 0.059, 0.010],
    [1.262, 0.058, 0.050, 0.012],
])
SUPER = 2.3   # superellipse exponent of the cross-sections (a little boxy, like cloth over a body)


def yukata_ring(z):
    """(a, b, yc) of the yukata cross-section at heights z."""
    r = catmull(YUKATA[:, [0, 1, 2, 3]], np.atleast_1d(z))
    return r[:, 0], r[:, 1], r[:, 2]


def superellipse(phi, a, b, yc, p=SUPER):
    """Points on a superellipse ring. phi = 0 is her front (-Y), increasing toward her left (+X)."""
    s, c = np.sin(phi), np.cos(phi)
    x = a * np.sign(s) * np.abs(s) ** (2.0 / p)
    y = yc - b * np.sign(c) * np.abs(c) ** (2.0 / p)
    return x, y


def yukata_point(phi, z, off=0.0):
    a, b, yc = yukata_ring(z)
    x, y = superellipse(phi, a + off, b + off, yc)
    return np.stack([x, y, np.broadcast_to(z, x.shape)], axis=-1)


def yukata_front_y(x, z):
    """y of the yukata front surface at (x, z) (on the -Y side)."""
    a, b, yc = yukata_ring(z)
    u = np.clip(np.abs(x) / a, 0, 0.999)
    return yc - b * (1 - u ** SUPER) ** (1.0 / SUPER)


# ---------------------------------------------------------------- head surface (SDF)


def _ell(P, c, r):
    q = (P - np.asarray(c)) / np.asarray(r)
    k0 = np.linalg.norm(q, axis=-1)
    k1 = np.linalg.norm(q / np.asarray(r), axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def head_sdf(P):
    """Signed distance (approx.) to her head: round cranium, soft cheeks, narrow anime jaw, small
    chin, a hint of a nose."""
    P = np.asarray(P, float)
    cran = _ell(P, (0.0, 0.010, 1.412), (0.079, 0.089, 0.093))
    # One broad, softly blended lower-face volume (no separate cheek blobs, which left a crease
    # beside the nose): a smooth oval from the cheekbones to a small, round chin at 1.291.
    jaw = _ell(P, (0.0, -0.011, 1.360), (0.0675, 0.068, 0.066))
    d = smin(cran, jaw, 0.036)
    chin = _ell(P, (0.0, -0.041, 1.309), (0.023, 0.023, 0.018))
    d = smin(d, chin, 0.024)
    nose = _ell(P, (0.0, -0.0768, 1.345), (0.0034, 0.0058, 0.0062))   # just a tiny tip
    d = smin(d, nose, 0.004)
    return d


def head_grad(P, h=1e-4):
    P = np.asarray(P, float)
    g = np.zeros_like(P)
    for k in range(3):
        e = np.zeros(3)
        e[k] = h
        g[:, k] = (head_sdf(P + e) - head_sdf(P - e)) / (2 * h)
    return norm(g)


def head_radius(D, c=HEAD_C, off=0.0, sdf=None):
    """Distance along unit directions D (N,3) from c to the surface sdf = off (bisection)."""
    sdf = sdf or head_sdf
    lo = np.zeros(len(D))
    hi = np.full(len(D), 0.25)
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        f = sdf(c + D * mid[:, None]) - off
        inside = f < 0
        lo = np.where(inside, mid, lo)
        hi = np.where(inside, hi, mid)
    return 0.5 * (lo + hi)


def head_front(x, z, off=0.0):
    """Point on the head's front surface (offset `off` along the normal) above (x, z)."""
    x = np.atleast_1d(np.asarray(x, float))
    z = np.atleast_1d(np.asarray(z, float))
    n = len(x)
    y = np.full(n, -0.20)
    # March from the front until inside, then bisect.
    lo = y.copy()
    hi = np.full(n, 0.05)
    step = 0.002
    found = np.zeros(n, bool)
    yy = y.copy()
    for _ in range(140):
        P = np.stack([x, yy, z], axis=1)
        f = head_sdf(P)
        newly = (f < 0) & ~found
        hi = np.where(newly, yy, hi)
        lo = np.where(newly, yy - step, lo)
        found |= newly
        yy = yy + step
        if found.all():
            break
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        f = head_sdf(np.stack([x, mid, z], axis=1))
        inside = f < 0
        hi = np.where(inside, mid, hi)
        lo = np.where(inside, lo, mid)
    P = np.stack([x, 0.5 * (lo + hi), z], axis=1)
    N = head_grad(P)
    return P + N * off, N
