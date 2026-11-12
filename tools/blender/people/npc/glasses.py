"""Glasses and sunglasses: `npc_<v>_glasses` and `npc_<v>_sunglasses`, 100% on `head`.

Laid out in the heroine's face units (headshape.Head maps them onto each variant): each lens is centred
on the eye (sized from face.eye_extent over both face looks, so neither look pokes out), its top stays
under the brows, the bridge rests on the nose bridge and the arms run back along the side of the head
to the ear tops with a few millimetres of clearance (Clear: head SDF + ears). Frames carry their colour
in COLOR_0 (`glasses_frame` is white); lenses are a separate `glasses_lens` material whose tint AND
opacity ride in COLOR_0 (rgb, a), because the game's toon pass keeps `transparent` but not `opacity`.
"""
import math

import numpy as np

from . import face as FACE
from .geo import MB, TAU, norm, srgb, sweep, superellipse
from .hair import Clear

# per variant: (shape exponent for glasses, frame colour, sunglasses exponent, sunglasses frame colour)
SPEC = {
    "woman": dict(g_p=2.0, g_col=srgb("#8a6a3c"), g_r=0.00075, s_p=2.6, s_col=srgb("#1b1a1c")),   # thin gold round
    "man": dict(g_p=4.0, g_col=srgb("#1c1c20"), g_r=0.00100, s_p=3.4, s_col=srgb("#141416")),     # dark rectangles
    "keeper": dict(g_p=3.6, g_col=srgb("#2a2420"), g_r=0.00100, s_p=3.4, s_col=srgb("#141416")),
    "elder": dict(g_p=2.2, g_col=srgb("#9c9ea4"), g_r=0.00080, s_p=2.8, s_col=srgb("#222024")),    # silver round
    "kid": dict(g_p=2.0, g_col=srgb("#c43a3a"), g_r=0.00110, s_p=2.2, s_col=srgb("#d0383c")),     # red plastic shades
}
LENS_CLEAR = (srgb("#dfe8f0"), 0.20)
LENS_SUN = (srgb("#16181c"), 0.88)


def _layout(b, v, sun):
    """Lens centre / radii (heroine units) for variant v."""
    uo, zt, zb = FACE.eye_extent(v)
    ui = min(L["x0"] for L in FACE.LOOKS[v].values())
    brow_lo = min(L["brow"]["z0"] - L["brow"]["w0"] / 2 for L in FACE.LOOKS[v].values())
    uc = 0.5 * (ui + uo)
    rx = 0.5 * (uo - ui) + (0.0055 if sun else 0.0045)
    zc = 0.5 * (zt + zb) - 0.0008
    rz = 0.5 * (zt - zb) + (0.0075 if sun else 0.0060)
    top = brow_lo - 0.0010
    if zc + rz > top:
        rz = max(0.5 * (zt - zb) + 0.0025, top - zc)
    return uc, rx, zc, rz


def build(b, v, sun):
    hs = b.hs
    s = hs.s
    sp = SPEC[v]
    p = sp["s_p"] if sun else sp["g_p"]
    fcol = sp["s_col"] if sun else sp["g_col"]
    fr = (0.00120 if sun else sp["g_r"]) * s            # rim tube radius (NPC metres)
    lcol, lalpha = LENS_SUN if sun else LENS_CLEAR
    cl = Clear(b)
    uc, rx, zc, rz = _layout(b, v, sun)
    mb = MB(f"npc_{v}_{'sun' if sun else ''}glasses")

    # lens plane: in front of the most forward skin under the lens, wrapping back 6 deg at the outer side
    uu, zz = np.meshgrid(np.linspace(uc - rx, uc + rx, 9), np.linspace(zc - rz, zc + rz, 7))
    P, _ = hs.face(uu.ravel(), zz.ravel())
    yh = hs.her(P)[:, 1]
    k_wrap = math.tan(math.radians(6.0))
    y0 = float((yh - k_wrap * (uu.ravel() - uc)).min()) - 0.0065

    def lens_y(u):
        return y0 + k_wrap * (np.abs(u) - uc)

    th = np.linspace(0, TAU, 25)[:-1]
    a_, c_ = superellipse(th, p)            # a_ ~ sin (lateral), c_ ~ cos (vertical)
    # a slightly flattened top for the rectangular shapes, a droop at the outer-lower corner (cat-eye-free)
    rims = []
    for sg in (1.0, -1.0):
        u = sg * (uc + a_ * rx)
        z = zc + c_ * rz * np.where(c_ < 0, 1.0, 0.96)
        Ph = np.stack([u, lens_y(u), z], 1)
        Pn = hs.npc(Ph)
        V, F, U, RI = sweep(Pn, fr, 5, closed_path=True)
        mb.add(V, F, "glasses_frame", {"head": 1.0}, C=fcol, tag="rim")
        rims.append((sg, Ph))
        # lens: a fan just behind the rim centre line
        Lc = hs.npc(np.array([sg * uc, lens_y(sg * uc) + 0.0003, zc]))
        Lr = hs.npc(np.stack([u, lens_y(u) + 0.0003, z], 1))
        Lr = Lc + (Lr - Lc) * 0.985
        V = np.vstack([Lc[None], Lr])
        n = len(Lr)
        F = [[0, 1 + (j + 1) % n, 1 + j] for j in range(n)]
        # outward = -Y
        p0, p1, p2 = V[F[0]]
        if np.cross(p1 - p0, p2 - p0)[1] > 0:
            F = [f[::-1] for f in F]
        mb.add(V, F, "glasses_lens", {"head": 1.0}, C=lcol, alpha=lalpha, tag="lens")
        # glint: a short diagonal sliver near the upper outer corner, in front of the lens
        gl_u = sg * (uc + np.array([0.15, 0.45, 0.42, 0.12]) * rx)
        gl_z = zc + np.array([0.20, 0.62, 0.70, 0.28]) * rz
        G = hs.npc(np.stack([gl_u, lens_y(gl_u) - 0.0002, gl_z], 1))
        Fg = [[0, 1, 2, 3]]
        q0, q1, q2 = G[[0, 1, 2]]
        if np.cross(q1 - q0, q2 - q0)[1] > 0:
            Fg = [[3, 2, 1, 0]]
        mb.add(G, Fg, "glasses_lens", {"head": 1.0}, C=np.ones(3), alpha=0.55 if not sun else 0.45, tag="glint")

    # bridge: from the inner rims (a touch above centre), dipping toward the nose bridge
    zb_ = zc + 0.25 * rz
    ui = uc - rx
    Pn_, _ = hs.face(np.array([0.0]), np.array([zb_ - 0.002]))
    ynose = hs.her(Pn_)[0, 1]
    yb = min(lens_y(ui), ynose - 0.0018)
    path = np.array([[ui, lens_y(ui), zb_], [ui * 0.55, 0.5 * (lens_y(ui) + yb), zb_ + 0.0012],
                     [0.0, yb, zb_ + 0.0018], [-ui * 0.55, 0.5 * (lens_y(ui) + yb), zb_ + 0.0012],
                     [-ui, lens_y(ui), zb_]])
    V, F, U, RI = sweep(hs.npc(path), fr * 0.95, 5)
    mb.add(V, F, "glasses_frame", {"head": 1.0}, C=fcol, tag="bridge")
    # nose pads (metal frames) : small blobs resting on the nose sides
    if not sun and sp["g_p"] < 3.0:
        for sg in (1.0, -1.0):
            Pp, Np = hs.face(np.array([sg * 0.0065]), np.array([zc - 0.006]), off=0.0006)
            V, F, U, RI = sweep(np.array([Pp[0], Pp[0] + np.array([0, -0.0016 * s, 0.0016 * s])]), 0.0012 * s, 5)
            mb.add(V, F, "glasses_frame", {"head": 1.0}, C=fcol * 1.15, tag="pad")

    # arms: hinge at the outer rim, back along the side of the head to the ear top, then down behind it
    ec = [hs.ear_centre(sg) for sg in (1.0, -1.0)]
    for sg, e in zip((1.0, -1.0), ec):
        uh = sg * (uc + rx * 1.02)
        hinge = hs.npc(np.array([uh, lens_y(uh) + 0.0006, zc + 0.35 * rz]))
        ear_top = e + np.array([0.0, 0.002 * s, 0.0215 * s])
        n = 9
        t = np.linspace(0, 1, n)
        pts = []
        for ti in t:
            q = hinge * (1 - ti) + ear_top * ti
            q[2] = hinge[2] * (1 - ti) + ear_top[2] * ti + 0.003 * s * math.sin(math.pi * ti)
            pts.append(q)
        pts += [ear_top + np.array([0, 0.010, -0.006]) * s, ear_top + np.array([0, 0.015, -0.018]) * s,
                ear_top + np.array([0, 0.014, -0.028]) * s]
        pts = np.array(pts)
        # push sideways (x) until clear of skin and ears
        clr = (0.0022 + fr / s) * s
        for i in range(len(pts)):
            q = pts[i].copy()
            if i == 0:
                continue
            lo, hi = 0.0, 0.08
            if cl.d(q)[0] < clr:
                for _ in range(30):
                    m = 0.5 * (lo + hi)
                    if cl.d(q + np.array([sg * m, 0, 0]))[0] >= clr:
                        hi = m
                    else:
                        lo = m
                q = q + np.array([sg * hi, 0, 0])
            pts[i] = q
        # monotone in x near the hinge (no kink back toward the face)
        for i in range(1, 4):
            if sg * pts[i, 0] < sg * pts[i - 1, 0] - 0.002 * s:
                pts[i, 0] = pts[i - 1, 0] - sg * 0.002 * s
        r = np.full(len(pts), fr * 0.95)
        r[-3:] *= np.array([1.05, 1.15, 1.2])
        V, F, U, RI = sweep(pts, r, 5, r2=r * (1.4 if sun or p > 3 else 1.0))
        mb.add(V, F, "glasses_frame", {"head": 1.0}, C=fcol, tag="arm")
    mb.layout = dict(uc=uc, rx=rx, zc=zc, rz=rz, y0=y0)
    return mb
