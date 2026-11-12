"""Hairstyles as separate low-poly meshes `npc_<v>_hair_<style>` (100% on `head`, shared by both LODs).

Each style is a thick shell over the analytic head (headshape.Head): columns from the crown down to
a hairline / hem height per azimuth. Bangs are spiky (or blunt) and always end ABOVE the brows, so
the eyes, brows and glasses stay clear. Bobs hang straight down from ear height and are pushed clear
of the head, ears and neck. Buns, tails and sidelocks are swept tubes / ellipsoids. Colour is in
COLOR_0 (the `hair` material is white), so grey elder hair and varied browns are per style.
"""
import math

import numpy as np

from . import face as FACE
from .geo import MB, TAU, X, Y, Z, lerp, norm, smooth, srgb, sweep, ellipsoid
from .headshape import _ell

NECK_R = {"woman": 0.041, "man": 0.050, "kid": 0.034, "keeper": 0.050, "elder": 0.037}

# style name -> builder; filled below. STYLES[v] = [(style, builder)]
STYLES = {}


# ---------------------------------------------------------------- clearance (head, ears, neck)

class Clear:
    def __init__(self, b):
        self.b, self.hs, self.J = b, b.hs, b.J
        J = b.J
        self.n0 = J["neck"] + np.array([0, 0.004, -0.045 * b.lk])
        self.n1 = J["headj"] + np.array([0, 0.004, 0.02])
        self.nr = NECK_R[b.v]
        s = self.hs.s
        self.ears = [(self.hs.ear_centre(sg), np.array([0.0085, 0.0135, 0.0235]) * s) for sg in (1.0, -1.0)]

    def d(self, P):
        P = np.atleast_2d(P)
        d = self.hs.sdf(P)
        a, bb = self.n0, self.n1
        ab = bb - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        dn = np.linalg.norm(P - (a + t[:, None] * ab), axis=1) - self.nr
        d = np.minimum(d, dn)
        for c, r in self.ears:
            d = np.minimum(d, _ell(P, c, r))
        return d

    def push(self, P, clr, mask=None):
        """Move points (horizontally, away from the head axis) until they are clr outside."""
        P = np.array(P, float)
        c = self.hs.C
        sel = self.d(P) < clr
        if mask is not None:
            sel &= mask
        if not sel.any():
            return P
        Q = P[sel]
        dirv = Q - c
        dirv[:, 2] = 0.0
        dirv = norm(dirv + np.array([0, 1e-6, 0]))
        lo = np.zeros(len(Q))
        hi = np.full(len(Q), 0.10)
        for _ in range(28):
            m = 0.5 * (lo + hi)
            ok = self.d(Q + dirv * m[:, None]) >= clr
            hi = np.where(ok, m, hi)
            lo = np.where(ok, lo, m)
        P[sel] = Q + dirv * hi[:, None]
        return P


# ---------------------------------------------------------------- columns and shell

def columns(n_back=18, bang_half=0.0, n_spikes=0, per_spike=4, part=0.0):
    """Azimuths phi (0 = back, pi = front, ascending, closed by the builder) with a dense, aligned
    bang zone: returns phi, kind (0 plain, 1 tip, 2 valley, 3 mid) and spike index."""
    if n_spikes <= 0 or bang_half <= 0:
        phi = np.linspace(0, TAU, n_back + 1)[:-1]
        return phi, np.zeros(len(phi), int), np.zeros(len(phi), int)
    a0, a1 = math.pi - bang_half + part, math.pi + bang_half + part
    nb = n_spikes * per_spike
    pb = np.linspace(a0, a1, nb + 1)
    kind_b = []
    spike = []
    for i in range(nb + 1):
        r = i % per_spike
        kind_b.append(2 if r == 0 else (1 if r == per_spike // 2 else 3))
        spike.append(min(i // per_spike, n_spikes - 1))
    rest = TAU - (a1 - a0)
    nr = max(3, int(round(n_back * rest / TAU)))
    pr = a1 + np.linspace(0, rest, nr + 1)[1:-1]
    phi = np.concatenate([pb, pr]) % TAU
    kind = np.concatenate([kind_b, np.zeros(len(pr), int)])
    spike = np.concatenate([spike, np.zeros(len(pr), int)])
    o = np.argsort(phi)
    return phi[o], kind[o], spike[o]


def frontness(phi):
    return (1 - np.cos(phi)) / 2


def shell(b, mb, base_col, edge_knots, inflate, n_back=24, bangs=None, nsk=7, nhang=0, hang_from=1.40, flare=0.04,
          spikes=None, colfn=None, lat_top=1.40, thick=0.0034, tag="hair", inner_rows=3):
    """Hair shell. edge_knots: [(frontness, z_heroine)]; bangs: dict(half, n, root, tip, sharp, round, part,
    long) or None; inflate(phi, t) -> radial scale about the head centre (t: 0 crown .. 1 edge);
    nhang: rows hanging straight down below hang_from (heroine z) where the edge is lower."""
    hs = b.hs
    s = hs.s
    c = hs.C
    cl = Clear(b)
    if bangs:
        phi, kind, spk = columns(n_back, bangs["half"], bangs["n"], bangs.get("per", 4), bangs.get("part", 0.0))
    else:
        phi, kind, spk = columns(n_back)
    fr = frontness(phi)
    kf, kz = zip(*edge_knots)
    zE = np.interp(fr, kf, kz)
    if bangs:
        k = smooth(1 - math.sin(bangs["half"] / 2) ** 2 - 0.02, 1 - math.sin(bangs["half"] / 2) ** 2 + 0.02, fr)
        n = bangs["n"]
        # longer spikes in the middle, shorter at the sides
        mid = 1 - np.abs((spk + 0.5) / n - 0.5) * 2
        tipz = bangs["tip"] + (1 - mid) * bangs.get("side_up", 0.010)
        zb = np.where(kind == 1, tipz, np.where(kind == 2, bangs["root"], lerp(bangs["root"], tipz, bangs.get("round", 0.45))))
        zE = zE * (1 - k) + zb * k
    zE_n = hs.z(zE)
    hang_z = hs.z(hang_from)
    nl = len(phi)
    lat_hang = hs.lat_at_z(phi, hang_z)
    lat_e = hs.lat_at_z(phi, np.maximum(zE_n, hang_z) if nhang else zE_n)
    nrow = nsk + nhang
    outer = np.zeros((nrow, nl, 3))
    T = np.zeros((nrow, nl))
    for i in range(nsk):
        t = i / (nsk - 1)
        tt = 1 - (1 - t) ** 1.3          # denser toward the edge (spikes, hem)
        lat = lat_top + (lat_e - lat_top) * tt
        D = np.stack([np.sin(phi) * np.cos(lat), np.cos(phi) * np.cos(lat), np.sin(lat)], 1)
        P = hs.point(D)
        k_ = np.broadcast_to(np.asarray(inflate(phi, tt), float), phi.shape)
        if spikes is not None:
            k_ = k_ + spikes(phi, tt)
        outer[i] = c + (P - c) * k_[:, None]
        T[i] = tt
    for j in range(nhang):
        t = (j + 1) / nhang
        top_ = outer[nsk - 1]
        dz = np.maximum(top_[:, 2] - zE_n, 0.0) * t
        rad = top_ - c
        rad[:, 2] = 0
        outer[nsk + j] = top_ + norm(rad) * (flare * dz)[:, None] - np.array([0, 0, 1.0]) * dz[:, None]
        T[nsk + j] = 1.0
    # clearance (outer)
    flat = outer.reshape(-1, 3)
    flat = cl.push(flat, 0.0030 * s)
    outer = flat.reshape(nrow, nl, 3)
    # inner sheet: off the outer surface by `thick` where the hair is free of the skin (bangs, hanging
    # parts), else tucked just inside the scalp
    rows_in = [0] + list(range(max(1, nrow - inner_rows - nhang), nrow))
    inner = []
    for i in rows_in:
        P = outer[i]
        N = norm(P - c)
        if i >= nsk:
            rad = P - c
            rad[:, 2] = 0
            N = norm(rad)
        free = cl.d(P) > (thick + 0.0020 * s)
        Pi = np.where(free[:, None], P - N * thick * s, c + (hs.point(norm(P - c)) - c) * 0.97)
        if i >= nsk or free.any():
            Pi = np.where(free[:, None], cl.push(Pi, 0.0010 * s), Pi)
        inner.append(Pi)
    inner = np.array(inner)
    # assemble: outer rows top->edge, inner rows edge->top, closed in phi, with crown caps
    V = [outer.reshape(-1, 3), inner[::-1].reshape(-1, 3)]
    rows_all = nrow + len(rows_in)
    F = []
    for r in range(rows_all - 1):
        for j in range(nl):
            a = r * nl + j
            bb = r * nl + (j + 1) % nl
            F.append([a, bb, bb + nl, a + nl])
    Vv = np.vstack(V)
    top_o = c + (hs.point(np.array([[0, 0, 1.0]]))[0] - c) * float(np.mean(np.atleast_1d(inflate(np.array([math.pi]), 0.0))))
    top_i = c + (hs.point(np.array([[0, 0, 1.0]]))[0] - c) * 0.97
    io, ii = len(Vv), len(Vv) + 1
    Vv = np.vstack([Vv, top_o, top_i])
    last = (rows_all - 1) * nl
    for j in range(nl):
        F.append([io, j, (j + 1) % nl])
        F.append([ii, last + (j + 1) % nl, last + j])
    # orientation: outer faces away from the centre, inner faces toward it
    Fo = []
    n_out = (nrow - 1) * nl
    n_edge = nl
    for k_, f in enumerate(F):
        p = Vv[f]
        nn = np.cross(p[1] - p[0], p[2] - p[0])
        if len(f) == 4:
            nn = nn + np.cross(p[2] - p[0], p[3] - p[0])
        cc = p.mean(0)
        is_inner = (n_out + n_edge <= k_ < len(F) - 2 * nl) or (k_ >= len(F) - 2 * nl and (k_ - (len(F) - 2 * nl)) % 2 == 1)
        out = nn @ (cc - c) >= 0
        if k_ >= n_out and k_ < n_out + n_edge:
            Fo.append(f)          # the edge band: fixed below
            continue
        Fo.append(f if out != is_inner else f[::-1])
    # edge band: faces point away from the inside of the sheet (toward the edge direction)
    for k_ in range(n_out, n_out + n_edge):
        f = Fo[k_]
        p = Vv[f]
        nn = np.cross(p[1] - p[0], p[2] - p[0]) + np.cross(p[2] - p[0], p[3] - p[0])
        r_ = (k_ - n_out)
        prev = outer[nrow - 2, r_ % nl]
        dirv = p.mean(0) - prev
        Fo[k_] = f if nn @ dirv >= 0 else f[::-1]
    # colour: base, grooves between strands, darker underside
    Cb = np.asarray(base_col, float)
    groove = np.ones(nl)
    if bangs:
        groove = np.where(kind == 2, 0.78, np.where(kind == 3, 0.92, 1.0))
    groove = groove * (0.94 + 0.06 * np.cos(phi * 11.0 + 0.7))
    Co = []
    for i in range(nrow):
        g = 1.0 - (1.0 - groove) * min(1.0, T[i].mean() * 1.4)
        row = Cb[None, :] * g[:, None] * (1.0 - 0.10 * T[i][:, None] ** 3)
        if colfn is not None:
            row = row * colfn(phi, T[i], outer[i])[:, None]
        Co.append(row)
    Ci = [np.tile(Cb * 0.62, (nl, 1)) for _ in rows_in]
    Cc = np.vstack(Co + Ci + [Cb[None] * 1.0, Cb[None] * 0.6])
    mb.add(Vv, Fo, "hair", {"head": 1.0}, C=Cc, tag=tag)
    return outer


def tube(b, mb, path, r, r2, col, n=7, tag="hair", mat="hair"):
    V, F, U, RI = sweep(np.asarray(path, float), np.asarray(r, float), n, r2=np.asarray(r2, float))
    t = np.linspace(0, 1, len(V))
    C = np.tile(np.asarray(col, float), (len(V), 1))
    mb.add(V, F, mat, {"head": 1.0}, C=C, tag=tag)


def bun(b, mb, dirv, dist, radii, col, band=True, nu=10, nv=6, band_col=(1, 1, 1)):
    c = b.head_center()
    Rz = 0.56 * b.P["head"]
    d = norm(np.asarray(dirv, float))
    p = c + d * dist * Rz
    e2 = norm(np.cross(d, X))
    V, F, U = ellipsoid(p, (X, e2, d), np.array(radii) * Rz, nu, nv)
    # soft wrap lines on the bun
    ang = np.arctan2((V - p) @ e2, (V - p) @ X)
    Cc = np.asarray(col, float)[None] * (0.9 + 0.1 * np.cos(ang * 3 + ((V - p) @ d) * 120))[:, None]
    mb.add(V, F, "hair", {"head": 1.0}, C=Cc, tag="bun")
    if band:
        q = p - d * radii[2] * Rz * 0.55
        a = np.linspace(0, TAU, 11)[:-1]
        path = [q + (X * math.cos(t) * radii[0] + e2 * math.sin(t) * radii[1]) * Rz * 0.86 for t in a]
        V, F, U, RI = sweep(path, 0.0055 * b.lk, 5, closed_path=True)
        mb.add(V, F, "cloth_accent", {"head": 1.0}, C=np.tile(band_col, (len(V), 1)), tag="hairband")
    return p


def hz(b, zh):
    return b.hs.z(zh)


def surf(b, phi, zh, k=1.0):
    """Point on the (inflated) head at azimuth phi and heroine height zh."""
    hs = b.hs
    lat = hs.lat_at_z(np.array([phi]), hs.z(zh))[0]
    D = np.array([[math.sin(phi) * math.cos(lat), math.cos(phi) * math.cos(lat), math.sin(lat)]])
    P = hs.point(D)[0]
    return hs.C + (P - hs.C) * k


def bt(v, extra):
    """Bang tip height: just above the brows (heroine units)."""
    return FACE.brow_top(v) + extra


# ---------------------------------------------------------------- styles

def woman_bun(b, mb):
    col = srgb("#3a2620")
    infl = lambda phi, t: 1.072 + 0.030 * frontness(phi) * t * t + 0.012 * (1 - t)
    shell(b, mb, col, [(0.0, 1.352), (0.30, 1.372), (0.44, 1.404), (0.62, 1.404), (0.70, 1.396), (0.77, 1.430), (1.0, 1.445)],
          infl, n_back=18, nsk=7, bangs=dict(half=1.05, n=7, root=1.452, tip=bt("woman", 0.0035), side_up=0.012))
    _sidelocks(b, mb, col, 0.105, 0.016)
    bp = bun(b, mb, (0, 0.48, 0.88), 1.0, (0.40, 0.40, 0.36), col, band_col=(1, 1, 1))
    a = bp + np.array([-0.075, 0.01, 0.03])
    c2 = bp + np.array([0.07, -0.005, -0.015])
    V, F, U, RI = sweep(np.array([a, lerp(a, c2, 0.5), c2]), 0.0032, 5)
    mb.add(V, F, "wood_geta", {"head": 1.0}, tag="kanzashi")
    for kk in range(5):
        ang = TAU * kk / 5
        q = a + np.array([-0.004, 0.014 * math.cos(ang), 0.014 * math.sin(ang)])
        V, F, U = ellipsoid(q, (X, Y, Z), (0.006, 0.0085, 0.0085), 5, 3)
        mb.add(V, F, "cloth_accent", {"head": 1.0}, C=np.tile([1.0, 0.75, 0.8], (len(V), 1)), tag="flower")


def _sidelocks(b, mb, col, length, r):
    hs = b.hs
    for sg in (1.0, -1.0):
        a = surf(b, math.pi - sg * 1.02, 1.425, 1.05)
        a = a + np.array([0, -0.004, 0])
        path = np.array([a, a + np.array([sg * 0.005, -0.004, -length * 0.3]), a + np.array([sg * 0.007, -0.006, -length * 0.62]),
                         a + np.array([sg * 0.006, -0.008, -length * 0.86]), a + np.array([sg * 0.003, -0.010, -length])])
        P = Clear(b).push(path, 0.006 * hs.s)
        tube(b, mb, P, np.array([r, r * 0.92, r * 0.78, r * 0.55, r * 0.15]), np.array([r * 0.5, r * 0.46, r * 0.4, r * 0.3, r * 0.12]),
             col * 0.95, n=7, tag="sidelock")


def woman_bob(b, mb):
    col = srgb("#5a3a28")
    infl = lambda phi, t: 1.085 + 0.012 * (1 - t) + 0.010 * frontness(phi) * t
    shell(b, mb, col, [(0.0, 1.300), (0.40, 1.305), (0.60, 1.318), (0.70, 1.332), (0.75, 1.345), (0.80, 1.438), (1.0, 1.440)],
          infl, n_back=26, nsk=7, nhang=4, hang_from=1.402, flare=0.06, inner_rows=2,
          bangs=dict(half=0.82, n=9, per=2, root=bt("woman", 0.0075), tip=bt("woman", 0.0030), round=0.5, side_up=0.002))


def woman_ponytail(b, mb):
    col = srgb("#211819")
    infl = lambda phi, t: 1.068 + 0.028 * frontness(phi) * t * t + 0.010 * (1 - t)
    shell(b, mb, col, [(0.0, 1.338), (0.30, 1.360), (0.44, 1.404), (0.62, 1.404), (0.70, 1.394), (0.77, 1.430), (1.0, 1.445)],
          infl, n_back=18, nsk=7, bangs=dict(half=1.0, n=6, root=1.450, tip=bt("woman", 0.0040), side_up=0.014, part=0.10))
    s = b.hs.s
    a = surf(b, 0.0, 1.462, 1.06)
    path = [a, a + np.array([0, 0.030, -0.018]) * s, a + np.array([0, 0.052, -0.070]) * s, a + np.array([0, 0.058, -0.125]) * s,
            a + np.array([0, 0.050, -0.175]) * s]
    tube(b, mb, path, np.array([0.020, 0.024, 0.022, 0.016, 0.004]) * s, np.array([0.016, 0.019, 0.017, 0.012, 0.003]) * s,
         col * 0.95, n=8, tag="ponytail")
    q = a + np.array([0, 0.012, -0.006]) * s
    ang = np.linspace(0, TAU, 9)[:-1]
    d = norm(np.array([0, 0.75, -0.4]))
    e1 = X
    e2 = norm(np.cross(d, e1))
    ring = [q + (e1 * math.cos(t) + e2 * math.sin(t)) * 0.016 * s for t in ang]
    V, F, U, RI = sweep(ring, 0.0045 * s, 5, closed_path=True)
    mb.add(V, F, "cloth_accent", {"head": 1.0}, tag="hairtie")


def man_short(b, mb):
    col = srgb("#1f1a1c")
    sp = lambda phi, t: 0.055 * np.clip(np.sin(phi * 9) * 0.5 + 0.5, 0, 1) ** 3 * (t > 0.12) * np.sin(math.pi * t) * (1 - 0.6 * frontness(phi))
    infl = lambda phi, t: 1.062 + 0.020 * frontness(phi) * t
    shell(b, mb, col, [(0.0, 1.322), (0.30, 1.345), (0.44, 1.402), (0.60, 1.402), (0.67, 1.376), (0.73, 1.400), (0.78, 1.438), (1.0, 1.446)],
          infl, n_back=22, nsk=7, spikes=sp, bangs=dict(half=0.95, n=6, root=1.452, tip=bt("man", 0.0055), side_up=0.012, part=-0.12))


def man_crop(b, mb):
    col = srgb("#2e2622")
    stripes = lambda phi, t, P: 0.93 + 0.07 * np.cos(phi * 23)
    infl = lambda phi, t: 1.038 + 0.008 * (1 - t)
    shell(b, mb, col, [(0.0, 1.330), (0.30, 1.352), (0.44, 1.404), (0.60, 1.402), (0.67, 1.382), (0.73, 1.420), (0.82, 1.450),
                       (0.92, 1.455), (1.0, 1.452)], infl, n_back=30, nsk=6, colfn=stripes, inner_rows=2)


def man_slick(b, mb):
    col = srgb("#141213")
    comb = lambda phi, t, P: 0.86 + 0.14 * (0.5 + 0.5 * np.cos(P[:, 0] / b.hs.s * 520.0))
    infl = lambda phi, t: 1.050 + 0.045 * frontness(phi) ** 2 * (1 - t) ** 0.6 * np.clip(t * 4, 0, 1) + 0.010 * (1 - t)
    shell(b, mb, col, [(0.0, 1.326), (0.30, 1.350), (0.44, 1.403), (0.60, 1.402), (0.67, 1.380), (0.73, 1.425), (0.82, 1.456),
                       (0.95, 1.466), (1.0, 1.462)], infl, n_back=30, nsk=7, colfn=comb, inner_rows=2)


def kid_short(b, mb):
    col = srgb("#4a3426")
    sp = lambda phi, t: 0.045 * np.clip(np.sin(phi * 7) * 0.5 + 0.5, 0, 1) ** 3 * (t > 0.3) * np.sin(math.pi * t)
    infl = lambda phi, t: 1.082 + 0.025 * frontness(phi) * t * t
    shell(b, mb, col, [(0.0, 1.336), (0.30, 1.356), (0.44, 1.404), (0.60, 1.404), (0.68, 1.392), (0.76, 1.430), (1.0, 1.445)],
          infl, n_back=18, nsk=7, spikes=sp, bangs=dict(half=1.0, n=6, root=1.452, tip=bt("kid", 0.0035), side_up=0.012))
    c = b.head_center()
    s = b.hs.s
    a = surf(b, math.pi * 0.85, 1.500, 1.07)
    path = np.array([a, a + np.array([0.008, 0.010, 0.026]) * s, a + np.array([0.020, 0.026, 0.040]) * s,
                     a + np.array([0.034, 0.036, 0.036]) * s])
    tube(b, mb, path, np.array([0.014, 0.010, 0.006, 0.002]) * s, np.array([0.010, 0.008, 0.005, 0.002]) * s, col, n=6, tag="cowlick")


def kid_bowl(b, mb):
    col = srgb("#2a2020")
    infl = lambda phi, t: 1.090 + 0.012 * (1 - t) + 0.006 * np.sin(math.pi * t)
    shell(b, mb, col, [(0.0, 1.340), (0.40, 1.384), (0.55, 1.398), (0.72, 1.405), (0.78, 1.426), (1.0, 1.430)], infl,
          n_back=22, nsk=7, inner_rows=3,
          bangs=dict(half=0.98, n=11, per=2, root=bt("kid", 0.0070), tip=bt("kid", 0.0030), round=0.5, side_up=0.004))


def kid_pigtails(b, mb):
    col = srgb("#5b3a26")
    infl = lambda phi, t: 1.075 + 0.020 * frontness(phi) * t * t + 0.012 * (1 - t)
    shell(b, mb, col, [(0.0, 1.345), (0.30, 1.362), (0.44, 1.404), (0.62, 1.404), (0.70, 1.396), (0.77, 1.430), (1.0, 1.445)],
          infl, n_back=18, nsk=7, bangs=dict(half=0.95, n=5, root=1.450, tip=bt("kid", 0.0040), side_up=0.012))
    s = b.hs.s
    for sg in (1.0, -1.0):
        a = surf(b, math.pi * 0.5 - sg * 0.0 + (0.42 if sg > 0 else -0.42) + (math.pi if sg < 0 else 0), 1.432, 1.07)
        a = surf(b, (0.5 * math.pi - 0.45) if sg > 0 else (1.5 * math.pi + 0.45), 1.432, 1.07)
        out = norm(np.array([sg * 1.0, 0.35, 0.0]))
        path = [a, a + (out * 0.022 + np.array([0, 0, -0.012])) * s, a + (out * 0.040 + np.array([0, 0.004, -0.050])) * s,
                a + (out * 0.044 + np.array([0, 0.008, -0.095])) * s]
        tube(b, mb, path, np.array([0.016, 0.018, 0.014, 0.004]) * s, np.array([0.013, 0.015, 0.011, 0.003]) * s, col * 0.95,
             n=7, tag="pigtail")
        q = a + out * 0.012 * s
        V, F, U = ellipsoid(q, (X, Y, Z), np.array([0.009, 0.009, 0.009]) * s, 6, 4)
        mb.add(V, F, "cloth_accent", {"head": 1.0}, C=np.tile([1.0, 0.55, 0.6], (len(V), 1)), tag="hairtie")


def keeper_short(b, mb):
    col = srgb("#24201f")
    sp = lambda phi, t: 0.050 * np.clip(np.sin(phi * 11) * 0.5 + 0.5, 0, 1) ** 3 * (t < 0.55) * (t > 0.08) * np.sin(math.pi * t / 0.55)
    infl = lambda phi, t: 1.050 + 0.004 * (1 - t)
    shell(b, mb, col, [(0.0, 1.330), (0.30, 1.352), (0.44, 1.403), (0.60, 1.402), (0.67, 1.378), (0.73, 1.405), (0.78, 1.432), (1.0, 1.440)],
          infl, n_back=22, nsk=7, spikes=sp, bangs=dict(half=0.92, n=7, root=1.444, tip=bt("keeper", 0.0055), side_up=0.010))


def keeper_crop(b, mb):
    col = srgb("#2e2a26")
    stripes = lambda phi, t, P: 0.93 + 0.07 * np.cos(phi * 23)
    infl = lambda phi, t: 1.036 + 0.006 * (1 - t)
    shell(b, mb, col, [(0.0, 1.334), (0.30, 1.354), (0.44, 1.404), (0.60, 1.402), (0.67, 1.384), (0.73, 1.418), (0.85, 1.440), (1.0, 1.444)],
          infl, n_back=30, nsk=6, colfn=stripes, inner_rows=2)


def keeper_tied(b, mb):
    col = srgb("#3a2a22")
    infl = lambda phi, t: 1.046 + 0.006 * (1 - t)
    shell(b, mb, col, [(0.0, 1.352), (0.30, 1.366), (0.44, 1.404), (0.60, 1.402), (0.67, 1.380), (0.73, 1.408), (0.78, 1.434), (1.0, 1.442)],
          infl, n_back=20, nsk=7, bangs=dict(half=0.90, n=6, root=1.446, tip=bt("keeper", 0.0060), side_up=0.010, part=0.15))
    s = b.hs.s
    a = surf(b, 0.0, 1.372, 1.05)
    path = [a, a + np.array([0, 0.018, -0.006]) * s, a + np.array([0, 0.030, -0.030]) * s, a + np.array([0, 0.030, -0.058]) * s]
    tube(b, mb, path, np.array([0.014, 0.016, 0.012, 0.003]) * s, np.array([0.011, 0.012, 0.009, 0.002]) * s, col * 0.95, n=7, tag="tail")
    V, F, U = ellipsoid(a + np.array([0, 0.008, -0.002]) * s, (X, Y, Z), np.array([0.010, 0.008, 0.010]) * s, 6, 4)
    mb.add(V, F, "cloth_dark", {"head": 1.0}, tag="hairtie")


def _elder_cap(b, mb, col, lo_back=1.340):
    comb = lambda phi, t, P: 0.88 + 0.12 * (0.5 + 0.5 * np.cos(P[:, 0] / b.hs.s * 480.0 + 0.4))
    infl = lambda phi, t: 1.058 + 0.012 * (1 - t)
    shell(b, mb, col, [(0.0, lo_back), (0.30, 1.362), (0.44, 1.405), (0.62, 1.400), (0.70, 1.410), (0.78, 1.436), (0.90, 1.448),
                       (1.0, 1.452)], infl, n_back=30, nsk=7, colfn=comb, inner_rows=2)


def elder_bun(b, mb):
    col = srgb("#bdb8b4")
    _elder_cap(b, mb, col)
    bun(b, mb, (0, 0.80, 0.60), 1.0, (0.34, 0.34, 0.30), col, band_col=(0.75, 0.75, 0.75))


def elder_low(b, mb):
    col = srgb("#d8d4ce")
    _elder_cap(b, mb, col, lo_back=1.345)
    bun(b, mb, (0, 0.96, -0.30), 0.93, (0.36, 0.28, 0.30), col, band=True, band_col=(0.75, 0.75, 0.75))


def elder_short(b, mb):
    col = srgb("#a9a4a0")
    curls = lambda phi, t: 0.022 * np.abs(np.sin(phi * 6 + 0.5) * np.sin(t * 9.0)) * (t > 0.15)
    infl = lambda phi, t: 1.085 + 0.010 * (1 - t)
    shell(b, mb, col, [(0.0, 1.318), (0.40, 1.350), (0.55, 1.388), (0.68, 1.395), (0.76, 1.428), (1.0, 1.442)], infl,
          n_back=20, nsk=7, nhang=2, hang_from=1.400, flare=0.05, spikes=curls,
          bangs=dict(half=0.85, n=4, per=4, root=1.452, tip=bt("elder", 0.0060), round=0.6, side_up=0.008, part=0.25))


STYLES = {
    "woman": [("bun", woman_bun), ("bob", woman_bob), ("ponytail", woman_ponytail)],
    "man": [("short", man_short), ("crop", man_crop), ("slick", man_slick)],
    "kid": [("short", kid_short), ("bowl", kid_bowl), ("pigtails", kid_pigtails)],
    "keeper": [("short", keeper_short), ("crop", keeper_crop), ("tied", keeper_tied)],
    "elder": [("bun", elder_bun), ("low", elder_low), ("short", elder_short)],
}


def build(b, v):
    """-> {style: MB} for variant v (b: a Body of that variant, used for the head and the rig)."""
    out = {}
    for style, fn in STYLES[v]:
        mb = MB(f"npc_{v}_hair_{style}")
        fn(b, mb)
        out[style] = mb
    return out
