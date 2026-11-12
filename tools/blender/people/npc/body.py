"""Procedural bodies and outfits for the five NPC variants. Each variant is ONE skinned mesh with
material slots skin / hair / face / cloth_main / cloth_accent / cloth_dark / wood_geta | cloth_shoe.
Only what can be seen is modelled (no body under the robes)."""
import math

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .geo import (MB, TAU, X, Y, Z, ellipsoid, lerp, loft, norm, orient_out, ring, rot, smooth,
                  superellipse, sweep)
from .rig import arm_s, arm_w, chain, leg_w, mix, side_of, skeleton, torso_w

# texture atlas for cloth_main: 5 columns, each tiling vertically (see tex.py)
COLUMNS = {"woman": 0, "man": 1, "kid": 2, "keeper": 3, "elder": 4}
NCOL = 5
TILES_PER_COL = 4          # motifs around a reference circumference
TEX_ASPECT = 0.5           # texture height / width  (1000 x 500)

# body width scale per variant (vs the woman)
BW = {"woman": 1.0, "man": 1.17, "kid": 0.80, "keeper": 1.15, "elder": 0.98}

F_EYE = (0.06, 0.035, 0.06)


class Body:
    def __init__(self, v):
        self.v = v
        self.J = skeleton(v)
        self.P = self.J["P"]
        self.lk = self.J["lk"]
        self.bw = BW[v]
        from .headshape import Head
        self.hs = Head(v, self.J)
        self.mb = MB(f"npc_{v}_body", normal_fn=self.hs.grad)
        self.geta_mb = None                  # MB for the right geta (npc_X_geta_R); None = skip it
        self.cref = 0.95 * self.bw          # reference circumference for the pattern
        self.meta = {}

    # ------------------------------------------------------------ uv helpers
    def main_uv(self, U, circ, u_scale=None):
        """Loft UV (u 0..1 around, v metres) -> cloth_main atlas column."""
        col = COLUMNS[self.v]
        k = min(1.0, circ / self.cref) if u_scale is None else u_scale
        u = (col + 0.004 + np.clip(U[:, 0], 0, 1) * k * 0.992) / NCOL
        # isotropic: one column width (1/NCOL of the width) spans cref metres
        v = U[:, 1] / self.cref * (1.0 / NCOL) / TEX_ASPECT
        return np.stack([u, v], 1)

    # ------------------------------------------------------------ head + face
    def head_point(self, d, inflate=1.0, center_scale=None):
        """Point on the analytic head along direction(s) d from the head centre, scaled by inflate
        about that centre."""
        d = np.asarray(d, float)
        shp = d.shape
        D = d.reshape(-1, 3)
        p = self.hs.point(D)
        if inflate != 1.0:
            p = self.hs.C + (p - self.hs.C) * inflate
        return p.reshape(shp)

    def head_center(self):
        return self.hs.C.copy()

    def head_face(self, detail="near"):
        """Analytic head skin + ears + the painted face (look A; look B as the face_b morph)."""
        from . import face as FACE
        J = self.J
        hs = self.hs
        rows, cols, er, ec = (26, 32, 7, 10) if detail == "near" else (13, 18, 4, 7)
        V, F = hs.skin(rows, cols)
        c = hs.C

        def wf(p):
            if p[2] < J["headj"][2] + 0.02 and p[1] > c[1] - 0.02:
                k = float(smooth(J["headj"][2] - 0.02, J["headj"][2] + 0.03, p[2]))
                return {"head": k, "neck": 1 - k}
            return {"head": 1.0}
        self.mb.add(V, F, "skin", wf, tag="head", analytic=True)
        for sg in (1.0, -1.0):
            V, F = hs.ear(sg, er, ec)
            self.mb.add(V, F, "skin", {"head": 1.0}, tag="ear")
        for Va, Vb, F, Cc, tag, mv in FACE.build_pair(hs, self.v, detail):
            Cc = np.minimum(Cc, 0.96)       # nothing in the face reaches full white (no glowing blobs)
            self.mb.add(Va, F, "face", {"head": 1.0}, C=Cc, tag="face_" + tag, Vb=Vb, analytic=True, morphs=mv)
        self.headV = None

    @staticmethod
    def sphere_dirs(nlon, lats, lon0=0.0, lon1=TAU):
        phi = np.linspace(lon0, lon1, nlon + 1)
        D = []
        for la in lats:
            D.append(np.stack([np.sin(phi) * math.cos(la), np.cos(phi) * math.cos(la),
                               np.full_like(phi, math.sin(la))], 1))
        return np.array(D)  # (nlat, nlon+1, 3)

    @staticmethod
    def grid_faces(nr, nc):
        F = []
        w = nc + 1
        for i in range(nr - 1):
            for j in range(nc):
                a = i * w + j
                F.append([a, a + 1, a + 1 + w, a + w])
        return F

    def head(self, nlon=22, nlat=14):
        lats = np.linspace(-math.pi / 2 + 0.12, math.pi / 2 - 0.12, nlat)
        D = self.sphere_dirs(nlon, lats)
        Pts = self.head_point(D).reshape(-1, 3)
        F = self.grid_faces(nlat, nlon)
        w = nlon + 1
        bot = len(Pts)
        topi = bot + 1
        bp = self.head_point(np.array([0, 0, -1.0]))
        tp = self.head_point(np.array([0, 0, 1.0]))
        Pts = np.vstack([Pts, bp, tp])
        for j in range(nlon):
            F.append([bot, j + 1, j])
            a = (nlat - 1) * w + j
            F.append([topi, a, a + 1])
        c = self.head_center()
        F = orient_out(Pts, F, lambda q: c)
        J = self.J

        def wf(p):
            if p[2] < J["headj"][2] + 0.02 and p[1] > c[1] - 0.02:
                k = float(smooth(J["headj"][2] - 0.02, J["headj"][2] + 0.03, p[2]))
                return {"head": k, "neck": 1 - k}
            return {"head": 1.0}
        self.mb.add(Pts, F, "skin", wf, tag="head")
        self.headV, self.headF = Pts, F
        self.bvh = BVHTree.FromPolygons([tuple(p) for p in Pts], [tuple(f) for f in F])

    def face_hit(self, u, v):
        """Project face coords (u lateral +left, v up, metres around the eye line) onto the head."""
        J, P = self.J, self.P
        hh = P["head"]
        zc = J["chin_z"] + 0.42 * hh
        o = Vector((u, J["top"][1] - 1.0, zc + v))
        hit = self.bvh.ray_cast(o, Vector((0, 1, 0)), 3.0)
        if hit[0] is None:
            return None, None
        return np.array(hit[0]), np.array(hit[1])

    def face_poly(self, uv, cols, layer, center_col=None):
        """Filled convex polygon (fan) on the face, projected; cols per outline vertex."""
        uv = np.asarray(uv, float)
        cu = uv.mean(0)
        pts, C = [], []
        for (u, v), c in zip(np.vstack([cu[None], uv]), [center_col if center_col is not None else cols[0]] + list(cols)):
            p, n = self.face_hit(u, v)
            pts.append(p + n * (0.0009 + 0.0007 * layer))
            C.append(c)
        n = len(uv)
        F = [[0, 1 + i, 1 + (i + 1) % n] for i in range(n)]
        # orient toward the viewer (-Y)
        V = np.array(pts)
        F = [f if np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])[1] < 0 else f[::-1] for f in F]
        self.mb.add(V, F, "face", {"head": 1.0}, C=np.array(C), tag="face")

    def face_stroke(self, uv, width, col, layer, taper=True):
        uv = np.asarray(uv, float)
        m = len(uv)
        L, R = [], []
        for i in range(m):
            t = uv[min(i + 1, m - 1)] - uv[max(i - 1, 0)]
            t = t / max(np.linalg.norm(t), 1e-9)
            nrm2 = np.array([-t[1], t[0]])
            wv = width * (math.sin(math.pi * (i / (m - 1))) ** 0.5 if taper else 1.0)
            wv = max(wv, width * 0.25)
            L.append(uv[i] + nrm2 * wv / 2)
            R.append(uv[i] - nrm2 * wv / 2)
        pts = []
        for (u, v) in L + R:
            p, n = self.face_hit(u, v)
            pts.append(p + n * (0.0009 + 0.0007 * layer))
        V = np.array(pts)
        F = [[i, i + 1, m + i + 1, m + i] for i in range(m - 1)]
        F = [f if np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])[1] < 0 else f[::-1] for f in F]
        self.mb.add(V, F, "face", {"head": 1.0}, C=np.tile(col, (len(V), 1)), tag="face")

    def face(self, style):
        hh = self.P["head"]
        k = hh / 0.235
        dark = np.array([0.045, 0.025, 0.04])
        iris = np.array([0.30, 0.16, 0.10]) if style.get("iris") is None else np.array(style["iris"])
        brow = np.array(style.get("brow", (0.16, 0.09, 0.06)))
        ex = style.get("ex", 0.040) * k
        ew, eh = style.get("ew", 0.0115) * k, style.get("eh", 0.0155) * k
        ev = style.get("ev", 0.0)
        for sg in (1, -1):
            cx = sg * ex
            if style.get("closed"):
                arc = [(cx + ew * 1.2 * t, ev + eh * 0.25 - eh * 0.55 * t * t) for t in np.linspace(-1, 1, 7)]
                self.face_stroke(arc, 0.0042 * k, dark, 1)
            else:
                n = 14
                a = np.linspace(0, TAU, n, endpoint=False)
                ov = np.stack([cx + ew * np.sin(a), ev + eh * np.cos(a)], 1)
                cols = [dark if math.cos(t) > -0.2 else lerp(dark, iris, 0.55) for t in a]
                self.face_poly(ov, cols, 1, center_col=lerp(dark, iris, 0.75))
                # upper lash line
                lash = [(cx + ew * 1.25 * math.sin(t) + sg * 0.002 * k * (t > 0), ev + eh * 0.95 * math.cos(t) + 0.0015 * k)
                        for t in np.linspace(-1.9, 1.9, 9)]
                self.face_stroke(lash, 0.0042 * k, dark, 2)
                # highlight (upper outer) + small lower glint
                hl = np.stack([cx + sg * ew * 0.3 + ew * 0.36 * np.sin(a[::2]),
                               ev + eh * 0.38 + ew * 0.36 * np.cos(a[::2])], 1)
                self.face_poly(hl, [np.ones(3)] * len(hl), 3)
                hl2 = np.stack([cx - sg * ew * 0.3 + ew * 0.17 * np.sin(a[::2]),
                                ev - eh * 0.45 + ew * 0.17 * np.cos(a[::2])], 1)
                self.face_poly(hl2, [np.full(3, 0.9)] * len(hl2), 3)
            # brow
            bv = ev + eh * style.get("browh", 1.75)
            br = [(cx + sg * ew * 1.3 * t, bv + 0.0035 * k * (1 - t * t) - sg * 0.0 * t) for t in np.linspace(-1, 1, 6)]
            self.face_stroke(br, style.get("brow_w", 0.0032) * k, brow, 1)
            # blush
            if style.get("blush", True):
                a8 = np.linspace(0, TAU, 10, endpoint=False)
                bl = np.stack([cx + sg * 0.008 * k + 0.012 * k * np.sin(a8), ev - eh * 1.45 + 0.0055 * k * np.cos(a8)], 1)
                self.face_poly(bl, [np.array([0.98, 0.55, 0.52])] * 10, 0)
        # mouth
        mv = -0.42 * hh * 0.42 - 0.012 * k + style.get("mv", 0.0)
        mw = style.get("mw", 0.012) * k
        if style.get("open"):
            a = np.linspace(0, math.pi, 8)
            poly = [(mw * math.cos(t), mv - 0.0005) for t in (0, math.pi)]
            poly = [(-mw, mv)] + [(mw * math.cos(math.pi - t), mv - 0.012 * k * math.sin(t)) for t in a[1:-1]] + [(mw, mv)]
            self.face_poly(poly, [np.array([0.42, 0.13, 0.14])] * len(poly), 1)
        else:
            sm = [(mw * t, mv + 0.0035 * k * t * t) for t in np.linspace(-1, 1, 7)]
            self.face_stroke(sm, 0.0028 * k, np.array([0.38, 0.12, 0.11]), 1)

    def ears(self):
        J, P = self.J, self.P
        hh = P["head"]
        c = self.head_center()
        for sg in (1, -1):
            p = np.array([sg * P["hw"] * hh * 0.49, c[1] + 0.012, J["chin_z"] + 0.44 * hh])
            V, F, U = ellipsoid(p, (Y, X, Z), (0.017 * hh / 0.235, 0.008 * hh / 0.235, 0.026 * hh / 0.235), 8, 5)
            self.mb.add(V, F, "skin", {"head": 1.0}, tag="ear")

    # ------------------------------------------------------------ hair
    def hair_cap(self, bound, inflate, spikes=None, colfn=None, nlon=26, nrow=8, mat="hair"):
        """Closed hair shell: outer surface (inflate(phi, t)) down to the latitude bound(phi), an
        inner surface inside the skull, joined at the hairline. phi: 0 = back, pi = front."""
        sgrid = np.linspace(0, 1, nlon + 1)
        phi = TAU * sgrid + 0.45 * np.sin(TAU * sgrid)  # denser at the front (phi = pi) for the bangs
        lat_top = math.pi / 2 - 0.10
        rows_o, rows_i = [], []
        c = self.head_center()
        for i in range(nrow):
            t = i / (nrow - 1)
            lat = lat_top - (lat_top - bound(phi)) * t
            D = np.stack([np.sin(phi) * np.cos(lat), np.cos(phi) * np.cos(lat), np.sin(lat)], 1)
            base = self.head_point(D)
            s = np.broadcast_to(np.asarray(inflate(phi, t), float), phi.shape).copy()
            if spikes is not None:
                s = s + spikes(phi, t)
            rows_o.append(c + (base - c) * s[:, None])
            rows_i.append(c + (base - c) * 0.96)
        Vo = np.concatenate(rows_o)
        Vi = np.concatenate(rows_i[::-1])
        V = np.vstack([Vo, Vi])
        w = nlon + 1
        F = self.grid_faces(2 * nrow, nlon)
        # caps
        n0 = len(V)
        tp_o = c + (self.head_point(np.array([0, 0, 1.0])) - c) * float(np.atleast_1d(inflate(np.array([0.0]), 0.0))[0])
        tp_i = c + (self.head_point(np.array([0, 0, 1.0])) - c) * 0.96
        V = np.vstack([V, tp_o, tp_i])
        last = (2 * nrow - 1) * w
        for j in range(nlon):
            F.append([n0, j, j + 1])
            F.append([n0 + 1, last + j + 1, last + j])
        # orient: the folded sheet is consistently wound, so test one outer face and flip all;
        # caps: outer cap faces out, inner cap faces in.
        def nrm_of(f):
            p = V[f]
            return np.cross(p[1] - p[0], p[2] - p[0]), p.mean(0)
        nsheet = (2 * nrow - 1) * nlon
        n_, fc_ = nrm_of(F[nlon // 2])
        flip = (n_ @ (fc_ - c)) < 0
        Fo = [f[::-1] if flip else f for f in F[:nsheet]]
        for k, f in enumerate(F[nsheet:]):
            n_, fc_ = nrm_of(f)
            outer = (k % 2 == 0)
            ok = (n_ @ (fc_ - c)) >= 0
            Fo.append(f if ok == outer else f[::-1])
        C = None
        if colfn is not None:
            C = np.vstack([colfn(phi, i / (nrow - 1)) for i in range(nrow)] + [np.ones((nrow * w, 3))] + [np.ones((2, 3))])
        self.mb.add(V, Fo, mat, {"head": 1.0}, C=C, tag="hair")
        return V

    def bun(self, dirv, dist, radii, mat="hair", band=True, nu=12, nv=8, band_n=6, mb=None, C=None):
        mb = mb or self.mb
        c = self.head_center()
        Rz = 0.56 * self.P["head"]
        d = norm(dirv)
        p = c + d * dist * Rz
        a, b = norm(np.cross(d, X)), X
        V, F, U = ellipsoid(p, (X, norm(np.cross(d, X)), d), np.array(radii) * Rz, nu, nv)
        mb.add(V, F, mat, {"head": 1.0}, C=C, tag="bun")
        if band:
            q = p - d * radii[2] * Rz * 0.55
            ang = np.linspace(0, TAU, 13)[:-1]
            e1, e2 = X, norm(np.cross(d, X))
            path = [q + (e1 * math.cos(t) * radii[0] + e2 * math.sin(t) * radii[1]) * Rz * 0.86 for t in ang]
            V, F, U, RI = sweep(path, 0.006 * self.lk, band_n, closed_path=True)
            mb.add(V, F, "cloth_accent", {"head": 1.0}, tag="hairband")
        return p

    # ------------------------------------------------------------ neck, hands, arms, legs, feet
    def neck(self, r):
        J = self.J
        a = J["neck"] + [0, 0.004, -0.045 * self.lk]
        b = J["headj"] + [0, 0.004, 0.02]
        path = [lerp(a, b, t) for t in np.linspace(0, 1, 5)]
        V, F, U, RI = sweep(path, r, 10, cap=False)
        self.mb.add(V, F, "skin", lambda p: torso_w(J, p), tag="neck")

    def hand(self, side, mat="skin"):
        """Far LOD hand: five low-poly fingers in the relaxed rest curl (see hands.py)."""
        from . import hands
        hands.build(self.mb, self.J, side, "far", mat, meta=self.meta)

    def arm_skin(self, side, s0, s1, r0, r1, mat="skin", n=10):
        J = self.J
        d = J[f"d0_{side}"]
        ua = J[f"ua_{side}"]
        ss = np.linspace(s0, s1, 7)
        path = [ua + d * s for s in ss]
        rr = np.interp(ss, [s0, s1], [r0, r1])
        V, F, U, RI = sweep(path, rr, n, cap=False, up=np.array([0, -1.0, 0]))
        self.mb.add(V, F, mat, lambda p: arm_w(self.J, side, p), tag="arm")

    def leg_skin(self, side, z0, z1, r0, r1, mat="skin", n=10, C=None):
        J = self.J
        th = J[f"th_{side}"]
        zz = np.linspace(z0, z1, 6)
        path = [np.array([th[0], 0.0, z]) for z in zz]
        rr = np.interp(zz, [z1, z0], [r1, r0])
        V, F, U, RI = sweep(path, rr, n, cap=False, up=np.array([0, -1.0, 0]))
        self.mb.add(V, F, mat, lambda p: leg_w(J, side, p), C=C, tag="leg")

    def foot(self, side, mat="skin", grow=1.0, extra_h=0.0, sole_top=None):
        J = self.J
        lk = self.lk
        an = J[f"an_{side}"]
        x = an[0]
        sole = J["sole"] if sole_top is None else sole_top
        y0, y1 = an[1] + J["heel"], an[1] - J["toe"]
        ts = np.array([0.0, 0.12, 0.3, 0.55, 0.8, 0.95, 1.0])
        hw = np.array([0.024, 0.029, 0.031, 0.036, 0.038, 0.030, 0.012]) * lk * grow
        hh = np.array([0.050, 0.068, 0.072, 0.050, 0.032, 0.024, 0.012]) * lk * grow
        hh = hh + extra_h * np.array([1, 1, 1, 0.8, 0.5, 0.4, 0.3])
        rings = []
        for t, w, h in zip(ts, hw, hh):
            y = lerp(y0, y1, t)
            c = np.array([x + 0.004 * (1 if side == "L" else -1) * t, y, sole + h * 0.5])
            rings.append(ring(c, X, Z, w, h * 0.5, p=2.6))
        V, F, U, RI, TH = loft(rings, 10, cap0=True, cap1=True)
        F = orient_out(V, F, lambda q: np.array([x, q[1], sole + 0.02 * lk]))

        def wf(p):
            k = float(smooth(sole + 0.055 * lk, sole + 0.085 * lk, p[2])) * float(smooth(an[1] - 0.03, an[1] + 0.01, p[1]))
            return {f"foot_{side}": 1 - k * 0.7, f"shin_{side}": k * 0.7}
        self.mb.add(V, F, mat, wf, tag="foot")

    def geta(self, side, strap_mat="cloth_accent"):
        """Geta sandal. The left one goes into this mesh; the right one into self.geta_mb (the
        separate npc_X_geta_R mesh, built once and shared by both LODs) or is skipped."""
        mb = self.mb if side == "L" else self.geta_mb
        if mb is None:
            return
        J = self.J
        lk = self.lk
        an = J[f"an_{side}"]
        x = an[0]
        sole = J["sole"]
        y0, y1 = an[1] + J["heel"] + 0.012 * lk, an[1] - J["toe"] - 0.012 * lk
        cy = (y0 + y1) / 2
        hl = (y0 - y1) / 2
        hw = 0.047 * lk
        th = 0.018 * lk
        rings = [ring([x, cy, sole - th], X, Y, hw, hl, p=4), ring([x, cy, sole], X, Y, hw, hl, p=4)]
        V, F, U, RI, TH = loft(rings, 20, cap0=True, cap1=True)
        F = orient_out(V, F, lambda q: np.array([x, cy, sole - th / 2]))
        C = np.tile([1.0, 0.96, 0.9], (len(V), 1))
        C[V[:, 2] > sole - 0.002] = [1.0, 1.0, 1.0]
        mb.add(V, F, "wood_geta", {f"foot_{side}": 1.0}, C=C, smooth_shade=False, tag="geta")
        for ty in (y1 + hl * 0.42, y0 - hl * 0.38):
            rings = [ring([x, ty, 0.0], X, Y, hw * 0.92, 0.011 * lk, p=6), ring([x, ty, sole - th], X, Y, hw * 0.92, 0.011 * lk, p=6)]
            V, F, U, RI, TH = loft(rings, 12, cap0=True, cap1=True)
            F = orient_out(V, F, lambda q: np.array([x, ty, (sole - th) / 2]))
            mb.add(V, F, "wood_geta", {f"foot_{side}": 1.0}, C=np.tile([0.8, 0.74, 0.68], (len(V), 1)), smooth_shade=False, tag="geta")
        # hanao (thong strap): toe post -> instep peak, and peak -> both sides
        sg = 1.0 if side == "L" else -1.0
        post = np.array([x - sg * 0.006 * lk, an[1] - J["toe"] * 0.62, sole])
        peak = np.array([x, an[1] - J["toe"] * 0.22, sole + 0.045 * lk])
        Lp = np.array([x + 0.036 * lk, an[1] + 0.006, sole + 0.004])
        Rp = np.array([x - 0.036 * lk, an[1] + 0.006, sole + 0.004])
        arcs = [[post, lerp(post, peak, 0.5) + [0, 0, 0.012 * lk], peak]]
        for e in (Lp, Rp):
            m = lerp(peak, e, 0.5) + np.array([0, 0, 0.012 * lk]) + (e - peak) * np.array([0.25, 0, 0])
            arcs.append([peak, m, e])
        for a in arcs:
            V, F, U, RI = sweep(np.array(a), 0.0065 * lk, 6)
            mb.add(V, F, strap_mat, {f"foot_{side}": 1.0}, tag="hanao")

    def tabi(self, side):
        """Keeper: split-toe work boots (jika-tabi) in cloth_shoe, thin dark sole. The right boot goes
        into self.geta_mb (npc_keeper_geta_R) with a dark sock foot left in this mesh under it."""
        J = self.J
        lk = self.lk
        an = J[f"an_{side}"]
        if side == "R":
            # the sock (jika-tabi liner) that shows when the right boot is hidden
            self.foot(side, mat="cloth_dark", grow=1.0, sole_top=0.016)
            if self.geta_mb is None:
                return
            body_mb, self.mb = self.mb, self.geta_mb
            try:
                self._tabi(side)
            finally:
                self.mb = body_mb
            return
        self._tabi(side)

    def _tabi(self, side):
        J = self.J
        lk = self.lk
        an = J[f"an_{side}"]
        self.foot(side, mat="cloth_shoe", grow=1.12, extra_h=J["sole"] - 0.014, sole_top=0.014)
        # sole
        x = an[0]
        y0, y1 = an[1] + J["heel"] + 0.01, an[1] - J["toe"] - 0.008
        cy, hl = (y0 + y1) / 2, (y0 - y1) / 2
        rings = [ring([x, cy, 0.0], X, Y, 0.043 * lk, hl, p=3), ring([x, cy, 0.016], X, Y, 0.043 * lk, hl, p=3)]
        V, F, U, RI, TH = loft(rings, 16, cap0=True, cap1=True)
        F = orient_out(V, F, lambda q: np.array([x, cy, 0.008]))
        self.mb.add(V, F, "cloth_shoe", {f"foot_{side}": 1.0}, C=np.full((len(V), 3), 0.45), tag="sole")
        # ankle cuff
        zz = np.linspace(J["sole"] + 0.03 * lk, J["ankle_z"] + 0.10 * lk, 4)
        path = [np.array([x, an[1] + 0.008, z]) for z in zz]
        V, F, U, RI = sweep(path, np.linspace(0.043, 0.040, 4) * lk, 10, cap=False, up=np.array([0, -1.0, 0]))
        self.mb.add(V, F, "cloth_shoe", lambda p: leg_w(J, side, p), tag="cuff")

    # ------------------------------------------------------------ garment tubes
    class Tube:
        """Horizontal-ring garment: rings (z, rx, ryf, ryb, cy, p) interpolated in z."""

        def __init__(self, rings):
            self.r = sorted(rings, key=lambda r: -r[0])

        def params(self, z):
            zs = [r[0] for r in self.r][::-1]
            arr = np.array([r for r in self.r][::-1], float)
            return [float(np.interp(z, zs, arr[:, k])) for k in range(6)]

        def point(self, z, th, off=0.0):
            _, rx, ryf, ryb, cy, p = self.params(z)
            a, b = superellipse(np.asarray(th, float), p)
            ry = np.where(b > 0, ryb, ryf)
            x = a * (rx + off)
            y = cy + b * (ry + off)
            return np.stack([x, y, np.full_like(x, z)], -1)

        def normal(self, z, th):
            e = 1e-3
            p0 = self.point(z, th)
            pt = self.point(z, th + e)
            pz = self.point(z + e, th)
            n = np.cross(pt - p0, pz - p0)
            return norm(n)

        def ringfn(self, z, off=0.0, scale=1.0):
            _, rx, ryf, ryb, cy, p = self.params(z)

            def f(th):
                a, b = superellipse(th, p)
                ry = np.where(b > 0, ryb, ryf)
                return np.stack([a * (rx * scale + off), cy + b * (ry * scale + off), np.full_like(th, z)], -1)
            f.center = np.array([0, cy, z])
            return f

    def tube_mesh(self, T, zs, mat, wfun, n=24, fold_top=None, fold_bot=None, uv=True, C=None, off=0.0, tag=None):
        rings = []
        if fold_top is not None:
            rings.append(T.ringfn(zs[0] - fold_top[1], off=off - fold_top[0]))
        rings += [T.ringfn(z, off=off) for z in zs]
        if fold_bot is not None:
            rings.append(T.ringfn(zs[-1] + fold_bot[1], off=off - fold_bot[0]))
        V, F, U, RI, TH = loft(rings, n)
        F = orient_out(V, F, lambda q: np.array([0, T.params(q[2])[4], q[2]]))
        if fold_top is not None:
            # the fold-in row faces inward: keep the outward rule except it is fine for silhouettes
            pass
        UV = None
        if uv:
            circ = 2 * math.pi * float(np.mean([T.params(z)[1] for z in zs])) * 0.9
            UV = self.main_uv(U, circ)
        cols = C(V) if callable(C) else C
        self.mb.add(V, F, mat, wfun, UV=UV, C=cols, tag=tag or mat)
        return V

    def surface_strip(self, T, path_tz, width, mat, wfun, off=0.004, C=None, tag=None):
        """A band of given width following (theta, z) points over a Tube surface."""
        P, N = [], []
        for th, z in path_tz:
            P.append(T.point(z, th, off=off))
            N.append(T.normal(z, th))
        P, N = np.array(P), np.array(N)
        m = len(P)
        L, R = [], []
        for i in range(m):
            t = norm(P[min(i + 1, m - 1)] - P[max(i - 1, 0)])
            b = norm(np.cross(N[i], t))
            L.append(P[i] + b * width / 2)
            R.append(P[i] - b * width / 2)
        V = np.array(L + R)
        F = [[i, i + 1, m + i + 1, m + i] for i in range(m - 1)]
        F = [f if np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]]) @ N[min(f[0] % m, m - 1)] > 0 else f[::-1] for f in F]
        self.mb.add(V, F, mat, wfun, C=C, tag=tag or mat)

    def surface_patch(self, T, th_lo, th_hi, z0, z1, mat, wfun, off=0.0035, nz=9, nt=6, C=None):
        """Patch between two theta(z) curves (callables) from z0 (top) to z1."""
        V = []
        for i in range(nz):
            z = lerp(z0, z1, i / (nz - 1))
            a, b = th_lo(z), th_hi(z)
            for j in range(nt + 1):
                V.append(T.point(z, lerp(a, b, j / nt), off=off))
        V = np.array(V)
        F = self.grid_faces(nz, nt)
        F = orient_out(V, F, lambda q: np.array([0, T.params(q[2])[4], q[2]]))
        self.mb.add(V, F, mat, wfun, C=C, tag=mat)

    def robe_weights(self, z_hip, z_hem, sidew=0.05, shin_max=0.85, hips_keep=0.08):
        J = self.J

        def wf(p):
            z = p[2]
            if z >= z_hip:
                w = torso_w(J, p)
                # shoulders: the top outer corners follow the shoulder bones a little
                for side, sg in (("L", 1), ("R", -1)):
                    k = float(smooth(0.45 * self.P["shw"], 0.95 * self.P["shw"], sg * p[0])) * \
                        float(smooth(J["chest"][2], J["shoulder_z"], z)) * 0.55
                    if k > 0:
                        w = mix((1 - k, w), (k, {f"shoulder_{side}": 1.0}))
                return w
            f = float(np.clip((z_hip - z) / (z_hip - z_hem), 0, 1))
            sL = side_of(p[0], sidew * self.lk)
            wh = 1 - float(smooth(0.0, 0.45, f)) * (1 - hips_keep)
            wl = 1 - wh
            sh = float(smooth(0.35, 1.0, f)) * shin_max
            return {"hips": wh, "thigh_L": wl * (1 - sh) * sL, "shin_L": wl * sh * sL,
                    "thigh_R": wl * (1 - sh) * (1 - sL), "shin_R": wl * sh * (1 - sL)}
        return wf

    def sleeve(self, side, s0, s1, radii, pouch=0.0, mat="cloth_main", p=2.0, C=None):
        """Sleeve tube along the rest arm line; optional hanging pouch (tamoto) under the forearm."""
        J, P = self.J, self.P
        d = J[f"d0_{side}"]
        ua = J[f"ua_{side}"]
        e1 = np.array([0, -1.0, 0])
        e2 = norm(np.cross(d, e1))
        ss = np.linspace(s0, s1, len(radii))
        rings = [ring(ua + d * s, e1, e2, r, r * 1.02, p=p) for s, r in zip(ss, radii)]
        # cuff fold
        rings.append(ring(ua + d * (s1 - 0.025 * self.lk), e1, e2, radii[-1] * 0.82, radii[-1] * 0.82, p=p))
        V, F, U, RI, TH = loft(rings, 14)

        def inside(q):
            s = float((q - ua) @ d)
            return ua + d * s
        F = orient_out(V, F, inside)
        circ = 2 * math.pi * float(np.mean(radii))
        UV = self.main_uv(U, circ)
        self.mb.add(V, F, mat, lambda q: arm_w(J, side, q, bw=0.05), UV=UV, C=C, tag="sleeve")
        if pouch > 0:
            sa, sb = P["ua"] - 0.035 * self.lk, s1 - 0.006
            stations = np.linspace(0, 1, 9)
            rings = []
            top_off = radii[-2] * 0.55
            for t in stations:
                m = (1 - abs(2 * t - 1) ** 3.5) ** 0.3
                m = max(m, 0.12)
                s = lerp(sa, sb, t)
                tp = ua + d * s
                depth = pouch * m
                hgt = depth + top_off
                c = tp + np.array([0, 0.004, -(hgt / 2) + top_off * 0.6])
                rings.append(ring(c, np.array([0, 1.0, 0]), Z, 0.026 * self.lk * (0.6 + 0.4 * m), hgt / 2, p=3.2))
            V, F, U, RI, TH = loft(rings, 12, cap0=True, cap1=True)
            cents = np.array([r.center for r in rings])
            F = orient_out(V, F, lambda q: cents[int(np.argmin(np.linalg.norm(cents - q, axis=1)))])
            UV = self.main_uv(U, 2 * pouch + 0.06, u_scale=0.9)
            sl = f"sleeve_{side}1"

            def wf(q):
                s = float((q - ua) @ d)
                top = (ua + d * s)[2]
                qq = float(np.clip((top - q[2]) / max(pouch, 1e-6), 0, 1.2))
                k = float(smooth(0.05, 0.55, qq))
                return mix((1 - k, arm_w(J, side, q, bw=0.05)), (k, {sl: 1.0}))
            self.mb.add(V, F, mat, wf, UV=UV, C=C, tag="pouch")

    def obi_band(self, T, z0, z1, off, mat, wfun, C=None, n=24, p_front=None):
        rings = [T.ringfn(z0, off=off * 0.3), T.ringfn(z0, off=off), T.ringfn(z1, off=off), T.ringfn(z1, off=off * 0.3)]
        V, F, U, RI, TH = loft(rings, n)
        F = orient_out(V, F, lambda q: np.array([0, T.params(q[2])[4], q[2]]))
        self.mb.add(V, F, mat, wfun, C=C, tag="obi")

    def blob(self, c, axes, radii, mat, w, nu=10, nv=6, C=None, p=2.0, tag=None):
        V, F, U = ellipsoid(c, axes, radii, nu, nv, p=p)
        self.mb.add(V, F, mat, w, C=C, tag=tag or mat)
        return V
