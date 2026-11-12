"""Analytic anime heads (signed distance fields), one per variant, shared by both LODs, the hair,
the glasses and the face decals.

The construction is the heroine's (tools/blender/heroine/lib/shape.py): a round cranium and ONE broad
lower-face volume blended into it (no separate cheek blobs, so no crease beside the nose), a small
chin and a tiny nose tip. Each variant changes the proportions (the man and keeper get a wider,
squarer jaw and a bigger chin, the kid a rounder, fuller face with a small chin, the elder slightly
softer cheeks). Everything is authored in the heroine's units (her barefoot frame: crown 1.505, chin
1.291, facing -Y) and mapped onto the NPC by a uniform scale s = head height / 0.214 that puts her
crown on the NPC's head top.

Head normals come from the SDF gradient (bl.make_mesh sets them as custom normals), so the game's
hard toon terminator crosses the face cleanly whatever the tessellation.
"""
import math

import numpy as np

from .geo import norm

HER_CROWN, HER_CHIN = 1.505, 1.291
HER_HEAD = HER_CROWN - HER_CHIN          # 0.214
HER_C = np.array([0.0, 0.005, 1.400])     # ray centre for tessellation (heroine units)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1.0 - h) + a * h - k * h * (1.0 - h)


def _ell(P, c, r):
    q = (P - np.asarray(c)) / np.asarray(r)
    k0 = np.linalg.norm(q, axis=-1)
    k1 = np.linalg.norm(q / np.asarray(r), axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


# Shape parameters in heroine units: cranium, the lower-face volume, chin, nose tip, optional jaw
# corners (gonion) for the square adult-male jaw. k_* are blend radii.
_BASE = dict(cran_c=(0.0, 0.010, 1.412), cran_r=(0.079, 0.089, 0.093),
             jaw_c=(0.0, -0.011, 1.360), jaw_r=(0.0675, 0.068, 0.066), k_cj=0.036,
             chin_c=(0.0, -0.041, 1.309), chin_r=(0.023, 0.023, 0.018), k_chin=0.024,
             nose_c=(0.0, -0.0768, 1.345), nose_r=(0.0034, 0.0058, 0.0062), k_nose=0.004,
             gon=None)
SHAPES = {
    "woman": dict(_BASE),
    "elder": dict(_BASE, jaw_r=(0.066, 0.067, 0.066), jaw_c=(0.0, -0.010, 1.358), chin_r=(0.022, 0.022, 0.018),
                  cran_r=(0.078, 0.088, 0.092)),
    "man": dict(_BASE, cran_r=(0.080, 0.091, 0.092), jaw_c=(0.0, -0.009, 1.354), jaw_r=(0.0705, 0.070, 0.068),
                chin_c=(0.0, -0.040, 1.306), chin_r=(0.029, 0.024, 0.019), k_chin=0.020,
                nose_c=(0.0, -0.0774, 1.344), nose_r=(0.0036, 0.0060, 0.0064),
                gon=dict(c=(0.050, 0.004, 1.330), r=(0.020, 0.030, 0.024), k=0.026)),
    "keeper": dict(_BASE, cran_r=(0.080, 0.090, 0.092), jaw_c=(0.0, -0.010, 1.355), jaw_r=(0.070, 0.069, 0.067),
                   chin_c=(0.0, -0.040, 1.307), chin_r=(0.027, 0.023, 0.019), k_chin=0.021,
                   nose_c=(0.0, -0.0772, 1.344), nose_r=(0.0035, 0.0059, 0.0063),
                   gon=dict(c=(0.049, 0.004, 1.331), r=(0.019, 0.029, 0.023), k=0.026)),
    "kid": dict(_BASE, cran_c=(0.0, 0.010, 1.414), cran_r=(0.083, 0.090, 0.091), jaw_c=(0.0, -0.012, 1.364),
                jaw_r=(0.069, 0.066, 0.060), k_cj=0.040, chin_c=(0.0, -0.038, 1.314), chin_r=(0.019, 0.019, 0.015),
                k_chin=0.026, nose_c=(0.0, -0.0745, 1.346), nose_r=(0.0030, 0.0048, 0.0052)),
}


class Head:
    """Analytic head of variant v, positioned on the NPC skeleton J."""

    def __init__(self, v, J):
        P = J["P"]
        self.v = v
        self.s = P["head"] / HER_HEAD
        top = J["top"]
        # heroine (0, 0.005, crown) -> (0, top_y + 0.005, top_z)
        self.O = np.array([0.0, top[1] + 0.005 - 0.005 * self.s, top[2] - HER_CROWN * self.s])
        self.prm = SHAPES[v]
        self.C = self.npc(HER_C)

    # ------------------------------------------------------------ frames
    def npc(self, p):
        """heroine units -> NPC Blender coords."""
        return self.O + np.asarray(p, float) * self.s

    def her(self, p):
        return (np.asarray(p, float) - self.O) / self.s

    def z(self, zh):
        """heroine height -> NPC height."""
        return self.O[2] + zh * self.s

    # ------------------------------------------------------------ field
    def sdf(self, P):
        q = self.her(P)
        p = self.prm
        d = smin(_ell(q, p["cran_c"], p["cran_r"]), _ell(q, p["jaw_c"], p["jaw_r"]), p["k_cj"])
        if p["gon"]:
            g = p["gon"]
            for sg in (1.0, -1.0):
                c = np.array(g["c"]) * np.array([sg, 1.0, 1.0])
                d = smin(d, _ell(q, c, g["r"]), g["k"])
        d = smin(d, _ell(q, p["chin_c"], p["chin_r"]), p["k_chin"])
        d = smin(d, _ell(q, p["nose_c"], p["nose_r"]), p["k_nose"])
        return d * self.s

    def grad(self, P, h=1e-4):
        P = np.atleast_2d(np.asarray(P, float))
        g = np.zeros_like(P)
        for k in range(3):
            e = np.zeros(3)
            e[k] = h
            g[:, k] = (self.sdf(P + e) - self.sdf(P - e)) / (2 * h)
        return norm(g)

    def radius(self, D, off=0.0, c=None):
        """Distance along unit directions D (N,3) from c (default the head centre) to sdf = off."""
        c = self.C if c is None else np.asarray(c, float)
        D = np.atleast_2d(D)
        lo = np.zeros(len(D))
        hi = np.full(len(D), 0.3)
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            inside = self.sdf(c + D * mid[:, None]) - off < 0
            lo = np.where(inside, mid, lo)
            hi = np.where(inside, hi, mid)
        return 0.5 * (lo + hi)

    def point(self, D, off=0.0):
        D = norm(np.atleast_2d(D))
        return self.C + D * self.radius(D, off)[:, None]

    def front(self, x, z, off=0.0):
        """Point on the front of the head above (x, z) (NPC coords), pushed `off` along the normal;
        returns (P, N)."""
        x = np.atleast_1d(np.asarray(x, float))
        z = np.atleast_1d(np.asarray(z, float))
        n = len(x)
        y0 = self.C[1] - 0.25
        lo = np.full(n, y0)
        hi = np.full(n, self.C[1] + 0.05)
        found = np.zeros(n, bool)
        yy = lo.copy()
        step = 0.002
        for _ in range(200):
            f = self.sdf(np.stack([x, yy, z], 1))
            newly = (f < 0) & ~found
            hi = np.where(newly, yy, hi)
            lo = np.where(newly, yy - step, lo)
            found |= newly
            yy = yy + step
            if found.all():
                break
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            inside = self.sdf(np.stack([x, mid, z], 1)) < 0
            hi = np.where(inside, mid, hi)
            lo = np.where(inside, lo, mid)
        P = np.stack([x, 0.5 * (lo + hi), z], 1)
        N = self.grad(P)
        return P + N * off, N

    def face(self, u, zh, off=0.0):
        """Face coords in heroine units (u lateral, +left; zh heroine height) -> (P, N) on the face."""
        u = np.atleast_1d(np.asarray(u, float))
        zh = np.atleast_1d(np.asarray(zh, float))
        return self.front(u * self.s, self.z(zh), off * self.s)

    # ------------------------------------------------------------ meshes
    def skin(self, rows, cols):
        """Lat-long head skin: rays from the head centre to the surface. -> V, F."""
        th = np.linspace(0, np.pi, rows + 2)[1:-1]
        ph = np.linspace(0, 2 * np.pi, cols, endpoint=False)
        TH, PH = np.meshgrid(th, ph, indexing="ij")
        D = np.stack([np.sin(TH) * np.sin(PH), -np.sin(TH) * np.cos(PH), np.cos(TH)], axis=-1).reshape(-1, 3)
        V = self.C + D * self.radius(D)[:, None]
        F = []
        for i in range(rows - 1):
            for j in range(cols):
                a = i * cols + j
                b = i * cols + (j + 1) % cols
                F.append((a, b, b + cols, a + cols))
        top, bot = len(V), len(V) + 1
        Dt, Db = np.array([[0, 0, 1.0]]), np.array([[0, 0, -1.0]])
        V = np.vstack([V, self.C + Dt * self.radius(Dt)[:, None], self.C + Db * self.radius(Db)[:, None]])
        o = (rows - 1) * cols
        for j in range(cols):
            F.append((top, (j + 1) % cols, j))
            F.append((bot, o + j, o + (j + 1) % cols))
        F = orient(V, F, lambda c: np.tile(self.C, (len(c), 1)))
        return V, F

    def ear_centre(self, sg=1.0):
        """Ear centre on the side of the head (her ear: y 0.014, z 1.379), sunk a touch to sit flush."""
        q = np.array([0.0, 0.014, 1.379])
        p0 = self.npc(q)
        lo, hi = 0.0, 0.2
        for _ in range(40):
            m = 0.5 * (lo + hi)
            if self.sdf(np.array([[sg * m, p0[1], p0[2]]]))[0] < 0:
                lo = m
            else:
                hi = m
        return np.array([sg * (0.5 * (lo + hi) - 0.0012 * self.s), p0[1], p0[2]])

    def ear(self, sg, rows=8, cols=12):
        """A small flattened, slightly cupped oval tilted back (the heroine's ear)."""
        s = self.s
        th = np.linspace(0.15, np.pi - 0.15, rows)
        ph = np.linspace(0, 2 * np.pi, cols, endpoint=False)
        TH, PH = np.meshgrid(th, ph, indexing="ij")
        lx = 0.0048 * np.sin(TH) * np.cos(PH)
        ly = 0.0115 * np.sin(TH) * np.sin(PH) * (1.0 + 0.18 * np.cos(TH))
        lz = 0.0210 * np.cos(TH)
        ly = ly + 0.0026 * (lz / 0.0210) ** 2
        Pl = np.stack([lx * sg, ly, lz], -1).reshape(-1, 3) * s
        t = math.radians(-14)
        R = np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)], [0, math.sin(t), math.cos(t)]])
        c = self.ear_centre(sg)
        V = Pl @ R.T + c
        F = []
        for i in range(rows - 1):
            for j in range(cols):
                a = i * cols + j
                b = i * cols + (j + 1) % cols
                F.append((a, b, b + cols, a + cols))
        F = orient(V, F, lambda q: np.tile(c, (len(q), 1)))
        return V, F

    # ------------------------------------------------------------ hair helpers
    def lat_at_z(self, phi, zt, c=None):
        """Latitude (from the head centre) whose surface point at azimuth phi (0 = back, pi = front)
        has height zt (NPC metres). Vectorised over phi."""
        c = self.C if c is None else c
        phi = np.atleast_1d(phi)
        zt = np.broadcast_to(np.asarray(zt, float), phi.shape)
        lo = np.full(phi.shape, -1.4)
        hi = np.full(phi.shape, 1.45)
        for _ in range(36):
            m = 0.5 * (lo + hi)
            D = np.stack([np.sin(phi) * np.cos(m), np.cos(phi) * np.cos(m), np.sin(m)], 1)
            z = c[2] + D[:, 2] * self.radius(D, c=c)
            below = z < zt
            lo = np.where(below, m, lo)
            hi = np.where(below, hi, m)
        return 0.5 * (lo + hi)


def orient(V, F, inside_fn):
    """Flip faces whose normal points toward inside_fn(centres)."""
    V = np.asarray(V)
    out = []
    C = np.array([V[list(f)].mean(0) for f in F])
    I = inside_fn(C)
    for f, c, ins in zip(F, C, I):
        p = V[list(f)]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if len(f) == 4:
            n = n + np.cross(p[2] - p[0], p[3] - p[0])
        out.append(tuple(f) if n @ (c - ins) >= 0 else tuple(f[::-1]))
    return out
