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


EYE_XZ = (0.0295, 1.3858)     # eye centre (her left): x, z
EYE_TURN = 20.0               # deg the eye plane is turned outward (as on anime figures)
EYE_R = 0.11                  # the eye plane is a very gentle dome of this radius


def _base_sdf(P):
    cran = _ell(P, (0.0, 0.010, 1.412), (0.079, 0.089, 0.093))
    # One broad, softly blended lower-face volume: a smooth oval from the cheekbones to the chin.
    jaw = _ell(P, (0.0, -0.011, 1.360), (0.0675, 0.068, 0.066))
    d = smin(cran, jaw, 0.036)
    chin = _ell(P, (0.0, -0.047, 1.309), (0.023, 0.024, 0.018))
    return smin(d, chin, 0.024)


def _eye_y():
    lo, hi = -0.2, 0.0
    for _ in range(50):
        m = 0.5 * (lo + hi)
        if _base_sdf(np.array([[EYE_XZ[0], m, EYE_XZ[1]]]))[0] < 0:
            hi = m
        else:
            lo = m
    return 0.5 * (lo + hi)


EYE_Y = _eye_y() + 0.0022     # the eye planes sit a little behind the nose bridge


def _ss(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _eye_planes(P, d):
    """Each eye sits on a nearly flat plane turned EYE_TURN degrees outward (instead of on the
    round of the face), so the painted eye keeps its shape from three-quarter and side views."""
    t = np.radians(EYE_TURN)
    front = 1.0 - _ss(-0.035, -0.012, P[..., 1])
    for s in (-1.0, 1.0):
        n = np.array([s * np.sin(t), -np.cos(t), 0.0])
        C = np.array([s * EYE_XZ[0], EYE_Y, EYE_XZ[1]])
        sph = np.linalg.norm(P - (C - n * EYE_R), axis=-1) - EYE_R
        q = np.hypot((P[..., 0] - C[0]) / 0.021, (P[..., 2] - C[2]) / 0.020)
        w = (1.0 - _ss(0.72, 1.55, q)) * front
        d = d * (1 - w) + sph * w
    return d


# Profile on the centre line. Outward displacement (m) of the front of the face as a function of
# (x, z), in two layers: a BROAD one that sets the face plane (forehead, a soft dip at the nose
# bridge, a fuller mouth area and a chin that comes forward instead of receding), and a NARROW one
# with the nose and lips, which only the silhouette sees (shading normals leave it out).
NOSE_TIP_Z, NOSE_ROOT_Z, NOSE_H = 1.3500, 1.3880, 0.0098
BROAD = np.array([  # z, displacement
    [1.284, 0.0000], [1.290, 0.0048], [1.297, 0.0082], [1.304, 0.0030], [1.311, 0.0012], [1.320, 0.0025],
    [1.332, 0.0018], [1.344, 0.0008], [1.356, -0.0016], [1.368, -0.0032], [1.380, -0.0041], [1.390, -0.0040],
    [1.400, -0.0024], [1.410, -0.0008], [1.420, 0.0000], [1.440, 0.0000]])


def _gauss(v, s):
    return np.exp(-(v / s) ** 2)


def _relief(P, soft=False):
    x, z = P[..., 0], P[..., 2]
    zc = np.clip(z, BROAD[0, 0], BROAD[-1, 0])
    b = catmull(BROAD, zc.ravel())[:, 0].reshape(zc.shape)
    # Wider at the mouth (a soft fullness), narrow at the chin (small and round) and the bridge dip.
    h = b * _gauss(x, np.interp(z, [1.284, 1.301, 1.313, 1.335, 1.365], [0.0135, 0.0145, 0.0180, 0.0180, 0.0130]))
    # Nose: a slightly scooped line from the bridge down to a small pointed, upturned tip, cut
    # back sharply underneath to a short philtrum. Narrow, so the front view stays soft.
    u = np.clip((NOSE_ROOT_Z - z) / (NOSE_ROOT_Z - NOSE_TIP_Z), 0.0, 1.0)
    up = u ** 2.2
    under = 1.0 - _ss(0.0, 0.0080, NOSE_TIP_Z - z)
    nose = NOSE_H * np.where(z >= NOSE_TIP_Z, up, under) * _gauss(x, 0.0034 + 0.0022 * u)
    # Lips: two small bumps either side of the mouth line (1.318).
    lips = (0.0020 * _gauss(z - 1.3226, 0.0028) * _gauss(x, 0.0105)
            + 0.0026 * _gauss(z - 1.3134, 0.0029) * _gauss(x, 0.0090)
            - 0.0006 * _gauss(z - 1.3180, 0.0016) * _gauss(x, 0.0110))
    if soft:   # shading sees the dips in full, half of the mouth/chin fullness, a trace of the nose
        return np.where(h > 0, 0.5 * h, h) + 0.12 * nose
    return h + nose + lips


def _head(P, soft):
    P = np.asarray(P, float)
    d = _eye_planes(P, _base_sdf(P))
    front = 1.0 - _ss(-0.040, -0.018, P[..., 1])
    return d - _relief(P, soft) * front


def head_sdf(P):
    """Signed distance (approx.) to her head: round cranium, soft oval face, eye planes turned
    outward, and a real anime profile on the centre line (bridge dip, small pointed nose, lips,
    rounded chin)."""
    return _head(P, False)


def head_sdf_soft(P):
    """The same head WITHOUT the lips and with only a trace of the nose. Shading normals come
    from this surface (see head_grad_soft): the profile is in the silhouette, but a hard toon
    terminator sees one soft face with no crease beside the nose."""
    return _head(P, True)


def head_grad(P, h=1e-4, sdf=None):
    sdf = sdf or head_sdf
    P = np.asarray(P, float)
    g = np.zeros_like(P)
    for k in range(3):
        e = np.zeros(3)
        e[k] = h
        g[:, k] = (sdf(P + e) - sdf(P - e)) / (2 * h)
    return norm(g)


def head_grad_soft(P):
    return head_grad(P, h=4e-4, sdf=head_sdf_soft)


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
