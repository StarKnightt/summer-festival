"""Small numeric geometry kit: lofts, sweeps, ellipsoids, a mesh builder that carries skin weights,
UVs, material slots and vertex colours, and named-material helpers. Blender Z-up, character faces -Y,
character's left is +X."""
import math

import numpy as np

X, Y, Z = np.eye(3)
TAU = 2 * math.pi


def norm(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def smooth(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return np.asarray(a, float) * (1 - t) + np.asarray(b, float) * t


def rot(axis, deg):
    a = norm(axis)
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    x, y, z = a
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def srgb(h, k=1.0):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return np.array([x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]) * k


def perp_frame(d, hint=Z):
    """Two unit vectors perpendicular to d (e1 ~ hint x d side, e2 ~ hint projected)."""
    d = norm(d)
    h = np.asarray(hint, float)
    if abs(h @ d) > 0.95:
        h = X if abs(d @ X) < 0.9 else Y
    e2 = norm(h - d * (h @ d))
    e1 = np.cross(d, e2)
    return e1, e2


# ---------------------------------------------------------------- primitives (return V, F, extra)

def superellipse(th, p):
    """Unit superellipse point (sin-ish, cos-ish) with exponent p (2 = ellipse, 4+ = rounded box)."""
    s, c = np.sin(th), np.cos(th)
    e = 2.0 / p
    return np.sign(s) * np.abs(s) ** e, np.sign(c) * np.abs(c) ** e


def ring(c, e1, e2, r1, r2, p=2.0, mod=None):
    """A ring callable: theta (0 = +e2) -> points. mod(theta) -> radial multiplier (array)."""
    c, e1, e2 = (np.asarray(v, float) for v in (c, e1, e2))

    def f(th):
        a, b = superellipse(th, p)
        m = mod(th) if mod is not None else 1.0
        return c + np.outer(a * r1 * m, e1) + np.outer(b * r2 * m, e2)
    f.center = c
    return f


def loft(rings, n, cap0=False, cap1=False, close_u=True, th0=0.0, th1=TAU):
    """Quads between rings sampled at n+1 thetas (seam column duplicated). Returns V, F, UV(u, v in
    metres along the centre path), ring index and theta per vertex."""
    th = np.linspace(th0, th1, n + 1)
    pts = [r(th) for r in rings]
    cs = [r.center for r in rings]
    acc = [0.0]
    for i in range(1, len(cs)):
        acc.append(acc[-1] + float(np.linalg.norm(cs[i] - cs[i - 1])))
    V = np.concatenate(pts)
    U = np.concatenate([np.stack([th / TAU, np.full(n + 1, acc[i])], 1) for i in range(len(rings))])
    RI = np.repeat(np.arange(len(rings)), n + 1)
    TH = np.tile(th, len(rings))
    F = []
    w = n + 1
    for i in range(len(rings) - 1):
        for j in range(n):
            a, b = i * w + j, i * w + j + 1
            F.append([a, b, b + w, a + w])
    extra_v, extra_u, extra_ri, extra_th = [], [], [], []
    for k, (flag, ri) in enumerate(((cap0, 0), (cap1, len(rings) - 1))):
        if not flag:
            continue
        ci = len(V) + len(extra_v)
        extra_v.append(cs[ri])
        extra_u.append([0.5, acc[ri]])
        extra_ri.append(ri)
        extra_th.append(0.0)
        base = ri * w
        for j in range(n):
            F.append([ci, base + j + 1, base + j] if k == 0 else [ci, base + j, base + j + 1])
    if extra_v:
        V = np.vstack([V, extra_v])
        U = np.vstack([U, extra_u])
        RI = np.concatenate([RI, extra_ri])
        TH = np.concatenate([TH, extra_th])
    return V, F, U, RI, TH


def orient_out(V, F, inside_fn):
    """Flip faces whose normal points toward inside_fn(face centre) (a point inside the solid)."""
    V = np.asarray(V)
    out = []
    for f in F:
        p = V[f]
        nrm = np.cross(p[1] - p[0], p[2] - p[0])
        if len(f) == 4:
            nrm = nrm + np.cross(p[2] - p[0], p[3] - p[0])
        c = p.mean(0)
        out.append(f if nrm @ (c - inside_fn(c)) >= 0 else f[::-1])
    return out


def ellipsoid(c, axes, radii, nu=12, nv=8, p=2.0):
    """Ellipsoid around c with orthonormal axes (a, b, d) and radii (along a, b, d); d is the pole axis."""
    a, b, d = (np.asarray(v, float) for v in axes)
    ra, rb, rd = radii
    rings = []
    for i in range(nv + 1):
        t = -math.pi / 2 + math.pi * i / nv
        t = np.clip(t, -math.pi / 2 + 0.06, math.pi / 2 - 0.06)
        k = math.cos(t) ** (2.0 / p if p != 2 else 1.0)
        rings.append(ring(np.asarray(c) + d * rd * math.sin(t), a, b, ra * k, rb * k, p))
    V, F, U, RI, TH = loft(rings, nu, cap0=True, cap1=True)
    F = orient_out(V, F, lambda q: np.asarray(c, float) + d * (((q - c) @ d)) * 0.0)
    return V, F, U


def sweep(path, radius, n=8, closed_path=False, cap=True, r2=None, twist=None, up=Z):
    """Tube along a polyline with parallel-transport frames. radius: scalar or per-point array;
    r2 (second radius along e2) for flat bands; twist: per-point angle (rad) of the cross-section."""
    P = np.asarray(path, float)
    m = len(P)
    R1 = np.broadcast_to(np.asarray(radius, float), (m,)).copy()
    R2 = R1.copy() if r2 is None else np.broadcast_to(np.asarray(r2, float), (m,)).copy()
    T = []
    for i in range(m):
        if closed_path:
            t = P[(i + 1) % m] - P[i - 1]
        else:
            t = P[min(i + 1, m - 1)] - P[max(i - 1, 0)]
        T.append(norm(t))
    e1, e2 = perp_frame(T[0], up)
    frames = []
    for i in range(m):
        if i > 0:
            # transport previous frame
            tprev, tcur = T[i - 1], T[i]
            ax = np.cross(tprev, tcur)
            s = np.linalg.norm(ax)
            if s > 1e-8:
                ang = math.degrees(math.atan2(s, tprev @ tcur))
                Rm = rot(ax, ang)
                e1, e2 = Rm @ e1, Rm @ e2
        frames.append((e1.copy(), e2.copy()))
    rings = []
    for i in range(m):
        a, b = frames[i]
        if twist is not None:
            ang = twist[i]
            a, b = a * math.cos(ang) + b * math.sin(ang), -a * math.sin(ang) + b * math.cos(ang)
        rings.append(ring(P[i], a, b, R1[i], R2[i]))
    if closed_path:
        rings.append(rings[0])
    V, F, U, RI, TH = loft(rings, n, cap0=cap and not closed_path, cap1=cap and not closed_path)
    # orient: outward from the path
    def inside(q):
        d = np.linalg.norm(P - q, axis=1)
        return P[int(np.argmin(d))]
    F = orient_out(V, F, inside)
    return V, F, U, RI


# ---------------------------------------------------------------- mesh builder

class MB:
    """Accumulates one skinned mesh: vertices, faces (material slot per face), per-vertex UV, colour
    and bone weights (dict per vertex)."""

    def __init__(self, name, normal_fn=None):
        self.name = name
        self.V, self.F, self.FM, self.FS = [], [], [], []
        self.UV, self.C, self.W = [], [], []
        self.Vb = []          # alternative positions (morph target `face_b`); == V where unchanged
        self.NF = []          # True: normal from normal_fn (the analytic head surface)
        self.A = []           # vertex alpha (COLOR_0.a), 1 by default
        self.normal_fn = normal_fn
        self.parts = []
        self.M = {}           # extra morph targets: name -> list of positions (== V where unchanged)

    def add(self, V, F, mat, W, UV=None, C=None, smooth_shade=True, tag=None, Vb=None, analytic=False, alpha=None,
            morphs=None):
        V = np.asarray(V, float)
        base = len(self.V)
        morphs = morphs or {}
        for name in morphs:
            if name not in self.M:
                self.M[name] = list(np.asarray(self.V, float).reshape(-1, 3))
        for name, L in self.M.items():
            L.extend(np.asarray(morphs[name], float) if name in morphs else V)
        self.V.extend(V)
        self.Vb.extend(V if Vb is None else np.asarray(Vb, float))
        self.NF.extend([bool(analytic)] * len(V))
        self.A.extend(np.ones(len(V)) if alpha is None else np.broadcast_to(np.asarray(alpha, float), (len(V),)))
        for f in F:
            self.F.append([int(i) + base for i in f])
            self.FM.append(mat)
            self.FS.append(smooth_shade)
        n = len(V)
        self.UV.extend(np.zeros((n, 2)) if UV is None else np.asarray(UV, float)[:, :2])
        if C is None:
            C = np.ones((n, 3))
        C = np.asarray(C, float)
        if C.ndim == 1:
            C = np.tile(C, (n, 1))
        self.C.extend(C)
        if callable(W):
            W = [W(p) for p in V]
        elif isinstance(W, dict):
            W = [W] * n
        self.W.extend(W)
        self.parts.append((tag or mat, base, base + n))
        return base

    def tri_count(self):
        return sum(len(f) - 2 for f in self.F)

    def morph_names(self):
        return [n for n, L in self.M.items() if float(np.abs(np.asarray(self.V) - np.asarray(L)).max()) > 1e-7]

    def has_morph(self):
        return len(self.V) > 0 and float(np.abs(np.asarray(self.V) - np.asarray(self.Vb)).max()) > 1e-7


def clean_weights(w, maxn=4):
    items = [(k, v) for k, v in w.items() if v > 1e-4]
    items.sort(key=lambda kv: -kv[1])
    items = items[:maxn]
    s = sum(v for _, v in items) or 1.0
    return {k: v / s for k, v in items}
