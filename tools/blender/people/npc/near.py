"""Near LOD (`npc_X_near`): the same five people, bound to the same skeleton, modelled for close-ups.

What differs from the far mesh (`npc_X_body`, unchanged):
- garments are lofted through smooth (monotone-cubic) ring profiles at higher resolution: rounded,
  sloped shoulders, a torso that tapers into the obi, a hem with a slight flare and soft fold ridges;
- sleeves (sode) are soft, thick, draped panels: a rounded tube round the arm that runs into a deep
  bag hanging behind and below the forearm (weighted to `sleeve_X1`, so it hangs under gravity in
  every clip), with rounded corners and a dark cuff opening the forearm comes out of;
- collars are thick bands, the wearer's left over the right; the front overlap runs down to the hem;
- obi with rounded edges and a knot or bow at the back (woman bow, man flat knot, kid soft heko-obi
  bow, elder rounded taiko, keeper sash);
- anime faces: eye whites, an iris that is dark on top with a lighter lower half and a dark rim, a
  pupil, two catch-lights, a thick upper lash line with a flick, lower lash, brows, nose hint, mouth;
- relaxed mitten hands with the fingers curled a little toward the palm.
Feet, legs, heads, hair outlines and hands sit exactly where the far mesh has them."""
import math

import numpy as np

from . import outfits as OF
from .body import COLUMNS, Body
from .geo import (MB, TAU, X, Y, Z, ellipsoid, lerp, loft, norm, orient_out, ring, rot, smooth,
                  superellipse, sweep)
from .rig import arm_w, chain, leg_w, mix, side_of, torso_w


# ---------------------------------------------------------------- smooth profile interpolation

def pchip(xs, ys, x):
    """Monotone cubic (Fritsch-Carlson) interpolation; no overshoot, C1."""
    xs = np.asarray(xs, float)
    ys = np.asarray(ys, float)
    n = len(xs)
    h = np.diff(xs)
    dl = np.diff(ys) / h
    m = np.zeros(n)
    m[0], m[-1] = dl[0], dl[-1]
    for i in range(1, n - 1):
        if dl[i - 1] * dl[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / dl[i - 1] + w2 / dl[i])
    x = np.clip(np.asarray(x, float), xs[0], xs[-1])
    i = np.clip(np.searchsorted(xs, x) - 1, 0, n - 2)
    t = (x - xs[i]) / h[i]
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i] +
            (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])


class SoftTube(Body.Tube):
    """Body.Tube with C1 (monotone cubic) ring interpolation and optional fold ridges:
    fold(theta, z) -> extra radius in metres."""

    def __init__(self, rings, fold=None):
        super().__init__(rings)
        a = np.array(self.r[::-1], float)       # ascending z
        self.zs, self.cols = a[:, 0], a[:, 1:]
        self.fold = fold

    def params(self, z):
        return [float(z)] + [float(pchip(self.zs, self.cols[:, k], z)) for k in range(5)]

    def point(self, z, th, off=0.0):
        _, rx, ryf, ryb, cy, p = self.params(z)
        th = np.asarray(th, float)
        a, b = superellipse(th, p)
        ry = np.where(b > 0, ryb, ryf)
        f = self.fold(th, z) if self.fold is not None else 0.0
        off = np.asarray(off, float) + f
        x = a * (rx + off)
        y = cy + b * (ry + off)
        return np.stack([x, y, np.full_like(x, z)], -1)

    def ringfn(self, z, off=0.0, scale=1.0):
        def f(th):
            return self.point(z, th, off)
        f.center = np.array([0, self.params(z)[4], z])
        return f

    def out_normal(self, z, th):
        return -self.normal(z, th)          # Tube.normal points inward


def make_folds(z_top, z_hem, amp, n=(5, 8, 11), seed=0, front_quiet=0.0):
    """Soft vertical fold ridges growing toward the hem (periodic in theta)."""
    rng = np.random.RandomState(seed)
    ph = rng.uniform(0, TAU, len(n))
    wt = [1.0, 0.55, 0.3][:len(n)]

    def f(th, z):
        k = float(smooth(z_top, z_hem, z)) ** 1.4
        if k <= 0:
            return 0.0 * np.asarray(th, float)
        th = np.asarray(th, float)
        w = sum(a * np.sin(nn * th + p) for a, nn, p in zip(wt, n, ph)) / sum(wt)
        if front_quiet:
            w = w * (1 - front_quiet * np.exp(-((th - math.pi) / 0.5) ** 2))
        return amp * k * w
    return f


def theta_of_xy(x, y, cy=0.0):
    return np.mod(np.arctan2(x, y - cy), TAU)


# ---------------------------------------------------------------- the near body

class NearBody(Body):
    def __init__(self, v):
        super().__init__(v)
        self.mb = MB(f"npc_{v}_near", normal_fn=self.hs.grad)

    # ------------------------------------------------------------ UV helper for surface pieces
    def uv_from_pos(self, V, z_top, circ):
        V = np.asarray(V, float)
        th = theta_of_xy(V[:, 0], V[:, 1])
        U = np.stack([th / TAU, z_top - V[:, 2]], 1)
        return self.main_uv(U, circ)

    # ------------------------------------------------------------ robe
    def robe(self, T, zs, wf, n=40, tag="robe", fold_top=(0.014, 0.03), fold_bot=(0.012, 0.03), shade_folds=True,
             mat="cloth_main", uv=True, C=None):
        def col(V):
            c = np.ones((len(V), 3))
            if shade_folds and T.fold is not None:
                th = theta_of_xy(V[:, 0], V[:, 1])
                fv = np.array([float(np.atleast_1d(T.fold(np.array([t]), z))[0]) for t, z in zip(th, V[:, 2])])
                c *= np.clip(1.0 + 9.0 * fv, 0.84, 1.0)[:, None]
            if C is not None:
                c *= np.asarray(C, float)
            return c
        return self.tube_mesh(T, zs, mat, wf, n=n, fold_top=fold_top, fold_bot=fold_bot, uv=uv, C=col, tag=tag)

    def thick_strip(self, T, path_tz, width, thick, mat, wfun, off=0.002, C=None, tag=None, nsec=7, caps=True,
                    uv_top=None, circ=None):
        """A band with a rounded-rectangle cross-section (width x thick) lying on a tube surface."""
        m = len(path_tz)
        offs = np.broadcast_to(np.asarray(off, float), (m,))
        widths = np.broadcast_to(np.asarray(width, float), (m,))
        P, N = [], []
        for (th, z), o in zip(path_tz, offs):
            P.append(T.point(z, th, off=o))
            N.append(T.out_normal(z, th))
        P, N = np.array(P), norm(np.array(N))
        rings = []
        for i in range(m):
            t = norm(P[min(i + 1, m - 1)] - P[max(i - 1, 0)])
            nn = norm(N[i] - t * (N[i] @ t))
            bv = norm(np.cross(nn, t))
            rings.append(ring(P[i] + nn * thick / 2, bv, nn, widths[i] / 2, thick / 2, p=3.2))
        V, F, U, RI, TH = loft(rings, nsec, cap0=caps, cap1=caps)
        cents = np.array([r.center for r in rings])
        F = orient_out(V, F, lambda q: cents[int(np.argmin(np.linalg.norm(cents - q, axis=1)))])
        UV = self.uv_from_pos(V, uv_top, circ) if uv_top is not None else None
        self.mb.add(V, F, mat, wfun, UV=UV, C=C, tag=tag or mat)

    def obi_soft(self, T, z0, z1, off, mat, wfun, C=None, n=40, round_h=0.008):
        """Obi band with rounded top and bottom edges."""
        zz = [z0, z0 + round_h * 0.45, z0 + round_h, z1 - round_h, z1 - round_h * 0.45, z1]
        oo = [off * 0.25, off * 0.82, off, off, off * 0.82, off * 0.25]
        rings = [T.ringfn(z, off=o) for z, o in zip(zz, oo)]
        V, F, U, RI, TH = loft(rings, n)
        F = orient_out(V, F, lambda q: np.array([0, T.params(q[2])[4], q[2]]))
        self.mb.add(V, F, mat, wfun, C=C, tag="obi")

    # ------------------------------------------------------------ sleeves
    def sleeve_panel(self, side, s0, s1, R, D, D_top=None, R_top=None, y_open=None, ext=0.06, r_tail=0.05, r_bb=0.06,
                     r_tb=0.06, r_top=0.03, tback=0.017, yfall=0.07, sag=0.02, hang=(0.45, 1.0), hang_k=0.95,
                     ns=(7, 6), ny=10, mat="cloth_main", tag="sode"):
        """Kimono sleeve: a soft tube round the arm (radius R) that runs into a thick bag reaching D
        behind the arm axis, from the shoulder (s0) to the cuff (s1); behind the cuff the bag hangs on
        to s1 + ext with rounded corners. Coordinates: s along the rest arm, y backward (+Y)."""
        J, P = self.J, self.P
        sg = 1.0 if side == "L" else -1.0
        d = J[f"d0_{side}"]
        ua = J[f"ua_{side}"]
        kb = np.array([0, 1.0, 0])
        m = norm(np.cross(d, kb)) * sg                      # lateral (outward)
        D_top = D * 0.32 if D_top is None else D_top
        R_top = R * 0.70 if R_top is None else R_top
        y_open = R * 0.8 if y_open is None else y_open
        s_b = s1 + ext

        def Rs(s):
            return R_top + (R - R_top) * float(smooth(s0, s0 + 0.14 * self.lk, s))

        def yb(s):
            y = D_top + (D - D_top) * float(smooth(0.0, 0.6, (s - s0) / (s_b - s0)))
            if s < s0 + r_tb:
                q = (s0 + r_tb - s) / r_tb
                y -= r_tb * (1 - math.sqrt(max(0.0, 1 - q * q)))
            if s > s_b - r_bb:
                q = (s - (s_b - r_bb)) / r_bb
                y -= r_bb * (1 - math.sqrt(max(0.0, 1 - q * q)))
            return y

        def yf(s):
            if s <= s1 + 1e-6:
                return -Rs(s)
            q = max(0.0, (s - (s_b - r_tail)) / r_tail)
            return y_open + r_tail * (1 - math.sqrt(max(0.0, 1 - q * q)))

        def es(s, arm):
            e = 1.0
            if s < s0 + r_top:
                q = (s0 + r_top - s) / r_top
                e *= math.sqrt(max(0.0, 1 - q * q))
            if not arm and s > s_b - r_top * 0.6:
                q = (s - (s_b - r_top * 0.6)) / (r_top * 0.6)
                e *= math.sqrt(max(0.0, 1 - q * q))
            return e

        def hi(y, s):
            Rr = Rs(s)
            if y < 0:
                return math.sqrt(max(Rr * Rr - y * y, 0.0))
            return tback + (Rr - tback) * (1 - float(smooth(0.0, yfall, y)))

        def edge(y, lo, hi_, rr, close_lo):
            e = 1.0
            if y > hi_ - rr:
                q = (y - (hi_ - rr)) / rr
                e *= math.sqrt(max(0.0, 1 - q * q))
            if close_lo and y < lo + rr:
                q = (lo + rr - y) / rr
                e *= math.sqrt(max(0.0, 1 - q * q))
            return e

        # stations: rounded top, arm part, cuff wall, tail with rounded bottom
        n1, n2 = ns
        top = [s0 + r_top * (1 - math.cos(a)) for a in np.linspace(0, math.pi / 2, 4)]
        arm_st = list(np.linspace(s0 + r_top, s1, n1)[1:])
        tail_st = [s1 + 0.004] + list(np.linspace(s1 + 0.004, s_b - r_top * 0.6, n2)[1:]) + \
            [s_b - r_top * 0.6 + r_top * 0.6 * math.sin(a) for a in np.linspace(0, math.pi / 2, 4)[1:]]
        stations = [(s, True) for s in top + arm_st] + [(s, False) for s in tail_st]
        g = (1 - np.cos(np.linspace(0, math.pi, ny))) / 2          # dense at both ends
        rows, Wl, UVl, Cl = [], [], [], []
        ua_len = P["ua"]
        circ = 2 * (D + R)
        for s, arm in stations:
            lo, hi_ = yf(s), yb(s)
            ys = lo + (hi_ - lo) * g
            e_s = es(s, arm)
            outer, inner = [], []
            for y in ys:
                h = hi(y, s) * edge(y, lo, hi_, tback * 1.3, close_lo=not arm) * e_s
                base = ua + d * (s + sag * (max(y, 0.0) / D) ** 2) + kb * y
                outer.append(base + m * h)
                inner.append(base - m * h)
            ring_pts = outer + inner[-2:0:-1]
            ring_y = list(ys) + list(ys[-2:0:-1])
            ring_c = [1.0] * len(outer) + [0.9] * (len(ring_y) - len(outer))
            rows.append(np.array(ring_pts))
            for y, c in zip(ring_y, ring_c):
                w = arm_w(J, side, ua + d * min(s, s1), bw=0.06)
                kh = hang_k * float(smooth(0.012, 0.085, y)) * float(smooth(hang[0] * ua_len, hang[1] * ua_len, s))
                if not arm:
                    kh = max(kh, hang_k * float(smooth(y_open * 0.5, y_open + 0.04, y)))
                if s < 0.35 * ua_len and y > 0.02:
                    kc = float(smooth(0.02, 0.10, y)) * (1 - float(smooth(0.0, 0.35 * ua_len, s))) * 0.5
                    w = mix((1 - kc, w), (kc, {"chest": 1.0}))
                Wl.append(mix((1 - kh, w), (kh, {f"sleeve_{side}1": 1.0})))
                UVl.append([(y + R) / circ, s])
                Cl.append([c, c, c])
        nr, nc = len(rows), len(rows[0])
        V = np.concatenate(rows)
        F = []
        for i in range(nr - 1):
            for j in range(nc):
                a, b_ = i * nc + j, i * nc + (j + 1) % nc
                F.append([a, b_, b_ + nc, a + nc])
        # orientation: outward from the panel mid-plane
        mids = []
        for f in F:
            q = V[f].mean(0)
            s = float((q - ua) @ d)
            y = float(q @ kb - ua @ kb)
            mids.append(ua + d * s + kb * y)
        Fo = []
        for f, c in zip(F, mids):
            p_ = V[f]
            nrm = np.cross(p_[1] - p_[0], p_[2] - p_[0]) + np.cross(p_[2] - p_[0], p_[3] - p_[0])
            Fo.append(f if nrm @ (p_.mean(0) - c) >= 0 else f[::-1])
        UV = self.main_uv(np.array(UVl), circ, u_scale=0.9)
        self.mb.add(V, Fo, mat, Wl, UV=UV, C=np.array(Cl), tag=tag)
        # dark cuff opening, just outside the cuff wall, facing down the arm
        sc = s1 + 0.0055
        ys = np.linspace(-R, y_open, 9)
        pts = []
        for y in ys:
            h = hi(y, s1) * 0.86
            pts.append(ua + d * sc + kb * y * 0.92 + m * h)
        for y in ys[::-1]:
            h = hi(y, s1) * 0.86
            pts.append(ua + d * sc + kb * y * 0.92 - m * h)
        pts = np.array(pts)
        c = pts.mean(0)
        V2 = np.vstack([c[None], pts])
        F2 = [[0, 1 + i, 1 + (i + 1) % len(pts)] for i in range(len(pts))]
        F2 = [f if np.cross(V2[f[1]] - V2[f[0]], V2[f[2]] - V2[f[0]]) @ d > 0 else f[::-1] for f in F2]
        W2 = lambda q: arm_w(J, side, q, bw=0.04)
        self.mb.add(V2, F2, mat, W2, UV=np.tile(self.main_uv(np.array([[0.5, s1]]), circ)[0], (len(V2), 1)),
                    C=np.full((len(V2), 3), 0.32), tag="cuff")

    def sleeve_tube(self, side, s0, s1, r0, r1, p=2.1, depth=1.12, r_top=0.03, n=18, nst=8, mat="cloth_main",
                    lip=0.022, C=None, tag="sleeve", r_start=0.72):
        """Short wide sleeve (jinbei, happi): soft flared tube, dome at the shoulder, rolled cuff and a
        dark opening."""
        J = self.J
        sg = 1.0 if side == "L" else -1.0
        d = J[f"d0_{side}"]
        ua = J[f"ua_{side}"]
        kb = np.array([0, 1.0, 0])
        m = norm(np.cross(d, kb)) * sg
        rings = []
        for a in np.linspace(0.12, math.pi / 2, 4):
            s = s0 + r_top * (1 - math.cos(a))
            r = r0 * r_start * math.sin(a)
            rings.append(ring(ua + d * s + kb * 0.004, m, kb, r, r * depth, p=p))
        for s in np.linspace(s0 + r_top, s1, nst)[1:]:
            t = (s - s0) / (s1 - s0)
            r = lerp(r0 * r_start, r0, float(smooth(0.0, 0.35, t))) + (r1 - r0) * t ** 1.2
            rings.append(ring(ua + d * s + kb * 0.004 * (1 + t), m, kb, r, r * depth, p=p))
        # rolled cuff: outward round lip then back inside
        rl = r1
        sl = s1
        for a in np.linspace(0.5, math.pi, 4):
            s = sl + lip * 0.4 * math.sin(a)
            r = rl - lip * 0.35 * (1 - math.cos(a))
            rings.append(ring(ua + d * s + kb * 0.008, m, kb, r, r * depth, p=p))
        rings.append(ring(ua + d * (sl - lip) + kb * 0.008, m, kb, rl * 0.78, rl * 0.78 * depth, p=p))
        V, F, U, RI, TH = loft(rings, n, cap0=True)
        F = orient_out(V, F, lambda q: ua + d * float((q - ua) @ d))
        circ = TAU * (r0 + r1) / 2
        UV = self.main_uv(U, circ)
        self.mb.add(V, F, mat, lambda q: arm_w(J, side, q, bw=0.05), UV=UV, C=C, tag=tag)
        # dark opening inside the cuff
        sc = sl - lip * 0.6
        th = np.linspace(0, TAU, 17)[:-1]
        a_, b_ = superellipse(th, p)
        pts = np.array([ua + d * sc + kb * 0.008 + m * (a * rl * 0.8) + kb * (b * rl * 0.8 * depth) for a, b in zip(a_, b_)])
        c = pts.mean(0)
        V2 = np.vstack([c[None], pts])
        F2 = [[0, 1 + i, 1 + (i + 1) % len(pts)] for i in range(len(pts))]
        F2 = [f if np.cross(V2[f[1]] - V2[f[0]], V2[f[2]] - V2[f[0]]) @ d > 0 else f[::-1] for f in F2]
        self.mb.add(V2, F2, mat, lambda q: arm_w(J, side, q, bw=0.04), UV=np.zeros((len(V2), 2)) + 0.001,
                    C=np.full((len(V2), 3), 0.30), tag="cuff")

    # ------------------------------------------------------------ hands
    def hand_soft(self, side, mat="skin", curl=34.0):
        """Near LOD hand: palm, thenar pad and five separate fingers in a relaxed curl (hands.py)."""
        from . import hands
        hands.build(self.mb, self.J, side, "near", mat, meta=self.meta)

    # ------------------------------------------------------------ face decals
    def _proj(self, u, v, layer):
        p, n = self.face_hit(u, v)
        if p is None:
            return None
        return p + n * (0.0008 + 0.00065 * layer)

    def deco_polar(self, center, rings_uv, cols, center_col, layer, mat="face", w=None):
        """Polar-grid decal projected onto the head: centre + rings (nr, na, 2); cols (nr, na, 3)."""
        rings_uv = np.asarray(rings_uv, float)
        nr, na = rings_uv.shape[:2]
        V = [self._proj(center[0], center[1], layer)]
        C = [center_col]
        for i in range(nr):
            for j in range(na):
                V.append(self._proj(rings_uv[i, j, 0], rings_uv[i, j, 1], layer))
                C.append(cols[i][j])
        V = np.array(V)
        F = [[0, 1 + j, 1 + (j + 1) % na] for j in range(na)]
        for i in range(nr - 1):
            for j in range(na):
                a = 1 + i * na + j
                b = 1 + i * na + (j + 1) % na
                F.append([a, b, b + na, a + na])
        F = [f if np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])[1] < 0 else f[::-1] for f in F]
        self.mb.add(V, F, mat, w or {"head": 1.0}, C=np.array(C), tag="face")

    def deco_grid(self, grid_uv, cols, layer, mat="face"):
        """Rectangular grid decal (nr, nc, 2)."""
        g = np.asarray(grid_uv, float)
        nr, nc = g.shape[:2]
        V = np.array([self._proj(g[i, j, 0], g[i, j, 1], layer) for i in range(nr) for j in range(nc)])
        F = []
        for i in range(nr - 1):
            for j in range(nc - 1):
                a = i * nc + j
                F.append([a, a + 1, a + 1 + nc, a + nc])
        F = [f if np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])[1] < 0 else f[::-1] for f in F]
        self.mb.add(V, F, mat, {"head": 1.0}, C=np.asarray(cols, float).reshape(-1, 3), tag="face")

    def deco_stroke(self, uv, widths, col, layer, mat="face"):
        uv = np.asarray(uv, float)
        m = len(uv)
        widths = np.broadcast_to(np.asarray(widths, float), (m,))
        L, R = [], []
        for i in range(m):
            t = uv[min(i + 1, m - 1)] - uv[max(i - 1, 0)]
            t = t / max(np.linalg.norm(t), 1e-9)
            nn = np.array([-t[1], t[0]])
            L.append(uv[i] + nn * widths[i] / 2)
            R.append(uv[i] - nn * widths[i] / 2)
        grid = np.stack([np.array(L), np.array(R)], 0)
        col = np.asarray(col, float)
        cols = np.tile(col if col.ndim == 1 else col[None], (2, m, 1)) if col.ndim == 1 else np.stack([col, col], 0)
        self.deco_grid(grid, cols, layer, mat)

    def near_eye(self, sg, st, k):
        dark = np.array(st.get("lash", (0.03, 0.018, 0.025)))
        I = np.array(st["iris"], float)
        ex, ew, eh = st["ex"] * k, st["ew"] * k, st["eh"] * k
        ev = st.get("ev", 0.0) * k
        tilt = st.get("tilt", 0.08)
        cx = sg * ex
        up_k, lo_k = st.get("up_k", 0.42), st.get("lo_k", 0.55)
        lo_h = st.get("lo_h", 0.86)

        def uu(t):
            return cx + sg * ew * t

        def upper(t):
            return ev + tilt * eh * t + eh * 0.95 * np.clip(1 - t * t, 0, 1) ** up_k

        def lower(t):
            return ev + tilt * eh * t - eh * lo_h * np.clip(1 - t * t, 0, 1) ** lo_k

        # eye white (grid between the lids), shaded under the upper lid
        ts = np.sin(np.linspace(-1, 1, 13) * math.pi / 2) * 0.985
        rs = np.array([0.0, 0.35, 0.65, 0.85, 1.0])
        grid, cols = [], []
        white = np.array(st.get("white", (0.93, 0.93, 0.96)))
        shade = np.array([0.62, 0.66, 0.80])
        for r in rs:
            row, crow = [], []
            for t in ts:
                row.append([uu(t), lerp(lower(t), upper(t), r)])
                crow.append(lerp(white, shade, float(smooth(0.6, 1.0, r)) * 0.85))
            grid.append(row)
            cols.append(crow)
        self.deco_grid(np.array(grid), np.array(cols), 1)
        # iris: polar grid, clamped between the lids
        icx = cx + sg * st.get("ix", 0.03) * ew
        icy = ev - st.get("iy", 0.04) * eh
        iw, ih = st.get("irw", 0.64) * ew, st.get("irh", 0.98) * eh
        na = 18
        rr = [0.2, 0.36, 0.52, 0.7, 0.86, 1.0]
        ang = np.linspace(0, TAU, na, endpoint=False)
        R_, C_ = [], []
        light = np.clip(I * 1.9 + 0.05, 0, 1)
        for r in rr:
            row, crow = [], []
            for a in ang:
                u = icx + iw * r * math.sin(a)
                v = icy + ih * r * math.cos(a)
                t = float(np.clip((u - cx) / (sg * ew), -0.999, 0.999))
                v = float(np.clip(v, lower(t) + 0.0006 * k, upper(t) - 0.0004 * k))
                row.append([u, v])
                ca = math.cos(a)
                c = I.copy()
                c = lerp(c, dark, 0.82 * float(smooth(-0.25, 0.70, ca)))                 # dark top
                band = float(smooth(0.30, 0.55, r)) * (1 - float(smooth(0.80, 0.97, r)))
                c = lerp(c, light, 0.75 * band * float(smooth(0.05, -0.75, ca)))           # light lower half
                if r <= 0.36:
                    c = lerp(c, dark, 0.9 if r < 0.3 else 0.6)                             # pupil
                if r >= 0.99:
                    c = lerp(c, dark, 0.7)                                                 # rim
                crow.append(c)
            R_.append(row)
            C_.append(crow)
        self.deco_polar([icx, icy], R_, C_, dark * 0.8, 2)
        # upper lash line with an outer flick, thick toward the outer corner
        lw = st.get("lash_w", 0.0060) * k
        tl = np.linspace(-1.04, 1.0, 13)
        pts = [[uu(t), upper(t) + lw * 0.22] for t in tl]
        pts += [[uu(1.10), upper(1.0) + 0.06 * eh], [uu(1.20), upper(1.0) + 0.16 * eh * st.get("flick", 1.0)]]
        tt = np.linspace(0, 1, len(pts))
        wd = lw * (0.50 + 0.65 * tt ** 0.9)
        wd[-2] *= 0.75
        wd[-1] = lw * 0.15
        self.deco_stroke(pts, wd, dark, 3)
        # lower lash (outer part)
        if st.get("lower_lash", True):
            tl = np.linspace(0.15, 1.02, 7)
            pts = [[uu(t), lower(t) - 0.0004 * k] for t in tl]
            wd = st.get("lower_w", 0.0011) * k * np.sin(np.linspace(0.25, 1.0, 7) * math.pi / 1.15 + 0.2)
            self.deco_stroke(pts, np.abs(wd) + 0.0004 * k, np.array(st.get("lower_col", (0.28, 0.15, 0.13))), 3)
        # catch-lights (same world side on both eyes)
        hs = st.get("hl", 1.0)
        a8 = np.linspace(0, TAU, 12, endpoint=False)
        for (ox, oy, rx, ry, c) in ((0.34, 0.38, 0.30, 0.25, 1.0), (-0.30, -0.48, 0.13, 0.11, 0.95)):
            hc = [icx + ox * iw, icy + oy * ih]
            ring_ = [[hc[0] + rx * hs * iw * math.sin(a), hc[1] + ry * hs * ih * math.cos(a)] for a in a8]
            self.deco_polar(hc, [ring_], [[np.full(3, c)] * len(a8)], np.full(3, c), 4)
        # brow
        bcol = np.array(st.get("brow", (0.16, 0.09, 0.06)))
        bw = st.get("brow_w", 0.0030) * k
        bh = ev + eh * st.get("browh", 1.12) + 0.006 * k
        tb = np.linspace(-1.0, 1.15, 8)
        arch = st.get("arch", 0.0035) * k
        pts = [[cx + sg * ew * (t * 1.0 - 0.05), bh + arch * (1 - ((t - 0.1) / 1.2) ** 2) - st.get("brow_tilt", 0.0) * k * t]
               for t in tb]
        wd = bw * np.interp(np.linspace(0, 1, 8), [0, 0.3, 1], [1.0, 0.95, 0.35])
        self.deco_stroke(pts, wd, bcol, 1)
        # eyelid crease (soft, above the lash)
        if st.get("crease", True):
            tc = np.linspace(-0.3, 0.95, 6)
            pts = [[uu(t), upper(t) + 0.30 * eh + lw * 0.3] for t in tc]
            self.deco_stroke(pts, 0.0008 * k, np.array(st.get("crease_col", (0.55, 0.32, 0.28))), 1)
        # elder: soft smile crease under the eye
        if st.get("smile_crease"):
            tc = np.linspace(0.55, 1.15, 5)
            pts = [[uu(t), lower(min(t, 1.0)) - 0.0028 * k + 0.002 * k * (t - 0.55)] for t in tc]
            self.deco_stroke(pts, 0.0009 * k, np.array((0.62, 0.40, 0.35)), 1)

    def near_face(self, st):
        hh = self.P["head"]
        k = hh / 0.235
        for sg in (1, -1):
            self.near_eye(sg, st, k)
            if st.get("blush", True):
                a = np.linspace(0, TAU, 12, endpoint=False)
                cx = sg * (st["ex"] * k + 0.004 * k)
                cy = st.get("ev", 0.0) * k - st["eh"] * k * 1.25 - 0.004 * k
                rx, ry = 0.0125 * k, 0.0055 * k
                rings = [[[cx + rx * f * math.sin(t), cy + ry * f * math.cos(t)] for t in a] for f in (0.55, 1.0)]
                bc = np.array(st.get("blush_col", (0.93, 0.42, 0.40)))
                self.deco_polar([cx, cy], rings, [[bc] * 12, [bc] * 12], bc, 0)
        # nose hint (skin material, follows the skin tint): a small shade on the wearer's right of the tip
        nv = st.get("nose_v", -0.030) * k
        pts = [[-0.0018 * k, nv + 0.004 * k], [-0.0032 * k, nv], [-0.0012 * k, nv - 0.0022 * k]]
        self.deco_stroke(pts, np.array([0.0012, 0.0022, 0.0012]) * k, np.array([0.80, 0.62, 0.58]), 0, mat="skin")
        # mouth
        mv = -0.42 * hh * 0.42 - 0.012 * k + st.get("mv", 0.0) * k
        mw = st.get("mw", 0.010) * k
        mc = np.array(st.get("mouth_col", (0.42, 0.13, 0.12)))
        if st.get("open"):
            a = np.linspace(0, math.pi, 9)
            hgt = st.get("mh", 0.009) * k
            top = [[mw * math.cos(math.pi - t), mv + 0.0015 * k * math.sin(t) ** 2] for t in a]
            bot = [[mw * 0.9 * math.cos(t), mv - hgt * math.sin(t)] for t in a[1:-1]]
            outline = np.array(top + bot)
            c = outline.mean(0)
            rings = [[list(c + (q - c) * 0.55) for q in outline], [list(q) for q in outline]]
            tongue = np.array([0.85, 0.36, 0.36])
            cols = [[lerp(mc, tongue, float(smooth(0, -hgt, q[1] - mv))) for q in outline]] * 2
            self.deco_polar(list(c), rings, cols, lerp(mc, tongue, 0.4), 1)
        else:
            sm = st.get("smile", 0.0030) * k
            pts = [[mw * t, mv + sm * t * t] for t in np.linspace(-1, 1, 9)]
            wd = st.get("mouth_w", 0.0019) * k * (0.45 + 0.55 * np.sin(np.linspace(0, math.pi, 9)))
            self.deco_stroke(pts, wd, mc, 1)

    # ------------------------------------------------------------ bows and knots
    def lobe(self, base, dirv, length, width, thick, mat, wf, up=None, droop=0.0, pinch=0.45, nst=9, nar=12,
             p=2.4, C=None, tag="bow", twist=0.0, crease=True):
        """Soft pillow lobe (bow wing, obi end): pinched at the base, full in the middle, round tip."""
        dirv = norm(dirv)
        up = Z if up is None else np.asarray(up, float)
        e_up = norm(up - dirv * (up @ dirv))
        e_th = norm(np.cross(dirv, e_up))
        ts = np.linspace(0.0, 1.0, nst)
        rings, cents = [], []
        for t in ts:
            c = base + dirv * length * t - Z * droop * t * t
            prof = lerp(pinch, 1.0, float(smooth(0.0, 0.45, t)))
            if t > 0.72:
                q = (t - 0.72) / 0.28
                prof *= math.sqrt(max(0.0, 1 - q * q)) if t < 1.0 else 0.15
            a = twist * t
            eu = e_up * math.cos(a) + e_th * math.sin(a)
            et = -e_up * math.sin(a) + e_th * math.cos(a)
            rings.append(ring(c, et, eu, thick * max(prof, 0.2), width * prof, p=p))
            cents.append(c)
        V, F, U, RI, TH = loft(rings, nar, cap0=True, cap1=True)
        cents = np.array(cents)
        F = orient_out(V, F, lambda q: cents[int(np.argmin(np.linalg.norm(cents - q, axis=1)))])
        if C is None:
            C = np.ones((len(V), 3))
            if crease:
                # soft fold lines along the lobe
                vv = (V - base) @ e_up / max(width, 1e-6)
                C *= np.clip(1.0 - 0.10 * np.exp(-((np.abs(vv) - 0.35) / 0.12) ** 2), 0.85, 1.0)[:, None]
        self.mb.add(V, F, mat, wf, C=C, tag=tag)


# ================================================================ shared pieces

def lapels_soft(b, T, top_z, v_z, end_z, width, thick, mat, wf, extra_left=None, col=None, open_th=0.50, off=0.002,
                uv_top=None, circ=None):
    """Thick collar bands: round the back of the neck, down both fronts to a V; the wearer's left band
    rides over the right one and continues across. Returns the left band's descending points."""
    th_n = math.pi - open_th
    back = [(th_n * t, top_z) for t in np.linspace(0, 1, 9)]
    down = [(lerp(th_n, math.pi - 0.012, t ** 1.25), lerp(top_z, v_z, t)) for t in np.linspace(0, 1, 13)[1:]]
    left = back + down
    right = [(TAU - th, z) for th, z in left]
    b.thick_strip(T, right, width, thick, mat, wf, off=off, C=col, uv_top=uv_top, circ=circ, tag="collar")
    tail = extra_left or [(math.pi + 0.18, v_z - 0.035), (math.pi + 0.42, end_z)]
    k0 = left[-1]
    ext = []
    for (th1, z1) in tail:
        for t in np.linspace(0, 1, 5)[1:]:
            ext.append((lerp(k0[0], th1, t), lerp(k0[1], z1, t)))
        k0 = (th1, z1)
    full = left + ext
    offs = [off + thick * 0.95 * float(smooth(math.pi * 0.45, math.pi * 0.8, th)) for th, z in full]
    b.thick_strip(T, full, width, thick, mat, wf, off=offs, C=col, uv_top=uv_top, circ=circ, tag="collar")
    return [(th_n, top_z)] + down


def overlap_edge(b, T, th0, z0, th1, z1, wf, uv_top, circ, width=0.010, thick=0.0035, mat="cloth_main"):
    """The left front panel's edge running down to the hem (a soft raised fold)."""
    path = [(lerp(th0, th1, t), lerp(z0, z1, t)) for t in np.linspace(0, 1, 12)]
    b.thick_strip(T, path, width, thick, mat, wf, off=0.0015, C=np.full(3, 0.9), uv_top=uv_top, circ=circ,
                  nsec=6, tag="okumi")


def soft_bow(b, B, wf, wing=(0.095, 0.050, 0.022), tail=(0.11, 0.034, 0.008), knot=(0.028, 0.024, 0.034),
             wing_up=0.25, wing_droop=0.0, tail_spread=0.35, mat="cloth_accent", knot_col=0.86, tail_tw=0.0,
             nst=8, nar=11):
    """Bow at the back: knot, two pillowy wings, two hanging ends."""
    for sg in (1, -1):
        dv = np.array([sg * 1.0, 0.25, wing_up])
        b.lobe(B + np.array([sg * 0.012, 0.010, 0.0]), dv, wing[0], wing[1], wing[2], mat, wf, droop=wing_droop,
               pinch=0.38, nst=nst, nar=nar, tag="bow")  # wing
        dv = np.array([sg * tail_spread, 0.12, -1.0])
        b.lobe(B + np.array([sg * 0.006, 0.006, -0.006]), dv, tail[0], tail[1], tail[2], mat, wf, up=np.array([sg * 1.0, 0, 0.3]),
               pinch=0.55, nst=7, nar=10, p=2.8, tag="bow", twist=tail_tw * sg, crease=False)
    b.blob(B + np.array([0, 0.016, 0.0]), (X, Y, Z), knot, mat, wf, nu=12, nv=7, p=2.5, C=np.full(3, knot_col), tag="bow")


def hair_hi(b, bound, inflate, spikes=None, colfn=None, nlon=34, nrow=10):
    return b.hair_cap(bound, inflate, spikes=spikes, colfn=colfn, nlon=nlon, nrow=nrow)


def sidelocks_soft(b, length, r):
    J, P = b.J, b.P
    hh = P["head"]
    c = b.head_center()
    for sg in (1, -1):
        a = c + np.array([sg * P["hw"] * hh * 0.47, -P["hd"] * hh * 0.30, 0.02 * hh / 0.235])
        path = np.array([a, a + np.array([sg * 0.006, -0.004, -length * 0.3]), a + np.array([sg * 0.008, -0.007, -length * 0.62]),
                         a + np.array([sg * 0.006, -0.010, -length * 0.86]), a + np.array([sg * 0.003, -0.012, -length])])
        V, F, U, RI = sweep(path, np.array([r, r * 0.92, r * 0.78, r * 0.55, r * 0.18]), 9,
                            r2=np.array([r * 0.55, r * 0.5, r * 0.45, r * 0.35, r * 0.15]))
        b.mb.add(V, F, "hair", {"head": 1.0}, tag="sidelock")


def limbs(b, side, arm=None, leg=None, foot=True, geta=None):
    if arm:
        b.arm_skin(side, *arm[:4], mat=arm[4] if len(arm) > 4 else "skin", n=12)
    b.hand_soft(side)
    if leg:
        b.leg_skin(side, *leg[:4], mat=leg[4] if len(leg) > 4 else "skin", n=12, C=leg[5] if len(leg) > 5 else None)
    if foot:
        b.foot(side)
    if geta:
        b.geta(side, geta)


# ================================================================ woman

def woman(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = J["ankle_z"] + 0.048 * lk
    z0, z1 = sp - 0.01, ch - 0.005                 # obi
    T = SoftTube([
        (nb + 0.024, 0.048, 0.044, 0.052, 0.006, 2.0),
        (nb + 0.004, 0.064, 0.054, 0.060, 0.005, 2.0),
        (sz - 0.010, 0.106, 0.070, 0.072, 0.003, 2.0),
        (sz - 0.030, 0.146, 0.082, 0.078, 0.0, 2.0),
        (sz - 0.054, 0.170, 0.090, 0.082, 0.0, 2.0),
        (sz - 0.082, 0.164, 0.098, 0.084, 0.0, 2.05),
        (sz - 0.115, 0.146, 0.102, 0.086, -0.002, 2.1),
        (ch + 0.03, 0.134, 0.104, 0.086, -0.004, 2.1),
        (z1 + 0.012, 0.124, 0.094, 0.084, -0.002, 2.1),
        (sp, 0.118, 0.088, 0.088, 0.0, 2.1),
        (hip + 0.04, 0.136, 0.098, 0.110, 0.0, 2.1),
        (hip - 0.10, 0.140, 0.102, 0.110, 0.0, 2.1),
        (kn, 0.130, 0.100, 0.102, 0.0, 2.1),
        (hem, 0.138, 0.106, 0.104, -0.004, 2.05),
    ], fold=make_folds(hip - 0.05, hem, 0.007 * lk, seed=1, front_quiet=0.6))
    zs = list(np.linspace(nb + 0.024, sz - 0.11, 10)) + list(np.linspace(sz - 0.11, z1 + 0.012, 4)[1:]) + \
        list(np.linspace(z1 + 0.012, z0 - 0.01, 3)[1:]) + list(np.linspace(z0 - 0.01, hip - 0.10, 4)[1:]) + \
        list(np.linspace(hip - 0.10, hem, 6)[1:])
    wf = b.robe_weights(hip + 0.02, hem)
    b.robe(T, zs, wf, n=36)
    tw = lambda p: torso_w(J, p)
    circ = TAU * 0.13 * 0.9
    pts = lapels_soft(b, T, nb + 0.018, ch + 0.035, z1 - 0.01, 0.030, 0.006, "cloth_accent", tw)
    OF.v_patch(b, T, pts, nb, ch + 0.035, "skin", tw)
    overlap_edge(b, T, math.pi + 0.40, z0, math.pi + 0.46, hem + 0.004, wf, nb + 0.024, circ)
    # obi + cord + bunko bow
    b.obi_soft(T, z0, z1, 0.014, "cloth_accent", tw)
    zm = (z0 + z1) / 2
    th = np.linspace(0, TAU, 27)[:-1]
    path = T.point(zm, th, off=0.0195)
    V, F, U, RI = sweep(path, 0.0050, 5, closed_path=True)
    b.mb.add(V, F, "cloth_dark", tw, tag="obijime")
    B = T.point(zm + 0.008, 0.0, off=0.03)
    soft_bow(b, B, tw, wing=(0.098, 0.050, 0.022), tail=(0.12, 0.034, 0.008), knot=(0.028, 0.022, 0.036),
             wing_up=0.30, tail_spread=0.30)
    for side in ("L", "R"):
        b.sleeve_panel(side, 0.035, P["ua"] + P["fa"] * 0.80, 0.048, 0.205 * lk, ext=0.075 * lk, sag=0.02)
        limbs(b, side, arm=(P["ua"] + P["fa"] * 0.55, P["ua"] + P["fa"] + 0.012, 0.027, 0.023),
              leg=(kn - 0.04, J["ankle_z"] + 0.012, 0.042, 0.029), geta="cloth_accent")
    b.neck(0.041)
    b.head_face("near")


# ================================================================ man

def man(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = J["ankle_z"] + 0.055 * lk
    z0, z1 = hip + 0.035, hip + 0.10
    T = SoftTube([
        (nb + 0.026, 0.058, 0.052, 0.060, 0.006, 2.0),
        (nb + 0.004, 0.078, 0.064, 0.070, 0.005, 2.0),
        (sz - 0.010, 0.132, 0.084, 0.084, 0.003, 2.0),
        (sz - 0.032, 0.180, 0.098, 0.092, 0.0, 2.0),
        (sz - 0.058, 0.206, 0.106, 0.096, 0.0, 2.0),
        (sz - 0.088, 0.200, 0.112, 0.098, 0.0, 2.05),
        (sz - 0.125, 0.180, 0.114, 0.100, -0.002, 2.1),
        (ch, 0.166, 0.112, 0.098, -0.004, 2.15),
        (sp, 0.150, 0.104, 0.098, 0.0, 2.15),
        (z1 + 0.01, 0.148, 0.102, 0.104, 0.0, 2.15),
        (hip - 0.10, 0.155, 0.108, 0.114, 0.0, 2.15),
        (kn, 0.150, 0.108, 0.108, 0.0, 2.1),
        (hem, 0.156, 0.112, 0.110, -0.004, 2.05),
    ], fold=make_folds(hip - 0.02, hem, 0.008 * lk, seed=2, front_quiet=0.5))
    zs = list(np.linspace(nb + 0.026, sz - 0.12, 10)) + list(np.linspace(sz - 0.12, z1 + 0.01, 5)[1:]) + \
        list(np.linspace(z1 + 0.01, z0 - 0.01, 3)[1:]) + list(np.linspace(z0 - 0.01, hem, 7)[1:])
    wf = b.robe_weights(hip + 0.03, hem, sidew=0.055)
    b.robe(T, zs, wf, n=40)
    tw = lambda p: torso_w(J, p)
    circ = TAU * 0.15 * 0.9
    pts = lapels_soft(b, T, nb + 0.02, ch + 0.045, hip + 0.10, 0.034, 0.006, "cloth_main", tw, col=np.full(3, 0.72),
                      extra_left=[(math.pi + 0.2, ch - 0.02), (math.pi + 0.5, z1)], open_th=0.46,
                      uv_top=nb + 0.026, circ=circ)
    OF.v_patch(b, T, pts, nb, ch + 0.045, "skin", tw)
    overlap_edge(b, T, math.pi + 0.50, z0, math.pi + 0.52, hem + 0.004, wf, nb + 0.026, circ)
    b.obi_soft(T, z0, z1, 0.012, "cloth_accent", tw)
    # kai-no-kuchi style flat knot at the back: a folded block, one end up-left, one end down-right
    B = T.point((z0 + z1) / 2, 0.0, off=0.018)
    b.blob(B + np.array([0.0, 0.004, 0.0]), (X, Y, Z), (0.062, 0.013, 0.030), "cloth_accent", tw, nu=16, nv=8, p=2.8,
           C=np.full(3, 0.86), tag="knot")
    b.lobe(B + np.array([0.02, 0.012, 0.006]), np.array([-0.55, 0.15, 0.85]), 0.085, 0.022, 0.006, "cloth_accent", tw,
           up=np.array([0.85, 0, 0.55]), pinch=0.8, nst=7, nar=10, p=3.0, tag="knot", crease=False)
    b.lobe(B + np.array([-0.02, 0.012, -0.006]), np.array([0.6, 0.15, -0.8]), 0.09, 0.022, 0.006, "cloth_accent", tw,
           up=np.array([0.8, 0, 0.6]), pinch=0.8, nst=7, nar=10, p=3.0, tag="knot", crease=False)
    for side in ("L", "R"):
        b.sleeve_panel(side, 0.04, P["ua"] + P["fa"] * 0.72, 0.056, 0.14 * lk, ext=0.035 * lk, r_bb=0.05,
                       r_tail=0.04, sag=0.012, tback=0.019)
        limbs(b, side, arm=(P["ua"] + P["fa"] * 0.45, P["ua"] + P["fa"] + 0.012, 0.034, 0.028),
              leg=(kn - 0.04, J["ankle_z"] + 0.012, 0.050, 0.034), geta="cloth_dark")
    b.neck(0.050)
    b.head_face("near")


# ================================================================ kid

def kid(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = hip - 0.035
    T = SoftTube([
        (nb + 0.018, 0.042, 0.040, 0.044, 0.004, 2.0),
        (nb + 0.002, 0.054, 0.046, 0.050, 0.004, 2.0),
        (sz - 0.008, 0.084, 0.058, 0.060, 0.002, 2.0),
        (sz - 0.022, 0.110, 0.064, 0.064, 0.0, 2.0),
        (sz - 0.040, 0.128, 0.070, 0.068, 0.0, 2.05),
        (sz - 0.062, 0.120, 0.076, 0.070, 0.0, 2.1),
        (ch, 0.110, 0.080, 0.072, 0.0, 2.15),
        (sp, 0.108, 0.080, 0.074, 0.0, 2.15),
        (hip + 0.02, 0.116, 0.082, 0.080, 0.0, 2.15),
        (hem, 0.124, 0.090, 0.086, 0.0, 2.1),
    ], fold=make_folds(sp, hem, 0.004, seed=3, front_quiet=0.6))
    zs = list(np.linspace(nb + 0.018, sz - 0.06, 8)) + list(np.linspace(sz - 0.06, hem, 7)[1:])

    def wtop(p):
        w = torso_w(J, p)
        for side, sg in (("L", 1), ("R", -1)):
            kk = float(smooth(0.5 * P["shw"], 0.95 * P["shw"], sg * p[0])) * float(smooth(ch, sz, p[2])) * 0.5
            if kk > 0:
                w = mix((1 - kk, w), (kk, {f"shoulder_{side}": 1.0}))
        if p[2] < hip + 0.02:
            sL = side_of(p[0], 0.04)
            kk = float(smooth(hip + 0.02, hem, p[2])) * 0.35
            w = mix((1 - kk, w), (kk, {"thigh_L": sL, "thigh_R": 1 - sL}))
        return w
    b.robe(T, zs, wtop, n=36, tag="jinbei", fold_top=(0.010, 0.02), fold_bot=(0.010, 0.02))
    tw = lambda p: torso_w(J, p)
    pts = lapels_soft(b, T, nb + 0.014, ch - 0.005, hem + 0.01, 0.020, 0.005, "cloth_accent", tw,
                      extra_left=[(math.pi + 0.25, ch - 0.04), (math.pi + 0.55, hem + 0.012)], open_th=0.55)
    OF.v_patch(b, T, pts, nb, ch, "skin", tw)
    tp = T.point(ch - 0.035, math.pi + 0.62, off=0.009)
    for dv in (np.array([-0.012, -0.004, -0.035]), np.array([0.004, -0.006, -0.04])):
        V, F, U, RI = sweep(np.array([tp, tp + dv * 0.5, tp + dv]), 0.0035, 6)
        b.mb.add(V, F, "cloth_accent", tw, tag="tie")
    # soft heko-obi: a light sash at the waist and a big floppy bow at the back
    zo0, zo1 = hip + 0.03, hip + 0.075
    b.obi_soft(T, zo0, zo1, 0.010, "cloth_accent", tw, C=np.full(3, 0.95), n=36, round_h=0.009)
    B = T.point((zo0 + zo1) / 2, 0.0, off=0.022)
    hw = lambda p: mix((0.7, torso_w(J, p)), (0.3, {"hips": 1.0}))
    soft_bow(b, B, hw, wing=(0.085, 0.040, 0.020), tail=(0.17, 0.030, 0.007), knot=(0.022, 0.018, 0.026),
             wing_up=-0.05, wing_droop=0.03, tail_spread=0.22, knot_col=0.9, tail_tw=0.5)
    # shorts
    S = OF.T_([(hip + 0.055, 0.100, 0.074, 0.074, 0.0, 2.2), (hip - 0.0, 0.110, 0.080, 0.084, 0.0, 2.2),
               (hip - 0.045, 0.100, 0.074, 0.078, 0.0, 2.2)])
    b.tube_mesh(S, [r[0] for r in S.r], "cloth_dark", b.robe_weights(hip + 0.03, hip - 0.045, sidew=0.03, shin_max=0.0, hips_keep=0.4),
                n=28, uv=False, tag="shorts")
    for side, sg in (("L", 1), ("R", -1)):
        x = sg * P["hipw"] * 1.08
        zz = [hip + 0.01, hip - 0.06, kn + 0.045, kn + 0.014]
        rr = [0.060, 0.058, 0.056, 0.058]
        rings = [ring([x, 0.0, z], X, Y, r, r * 0.98) for z, r in zip(zz, rr)]
        rings.append(ring([x, 0.0, zz[-1] + 0.006], X, Y, rr[-1] * 0.94, rr[-1] * 0.94))
        rings.append(ring([x, 0.0, zz[-1] + 0.02], X, Y, rr[-1] * 0.8, rr[-1] * 0.8))
        V, F, U, RI, TH = loft(rings, 18)
        F = orient_out(V, F, lambda q: np.array([x, 0.0, q[2]]))
        b.mb.add(V, F, "cloth_dark", lambda p, s=side: leg_w(J, s, p, bw=0.05), tag="shorts")
        b.sleeve_tube(side, 0.022, P["ua"] * 0.80, 0.040, 0.054, p=2.1, depth=1.1, r_top=0.022, lip=0.016)
        limbs(b, side, arm=(P["ua"] * 0.35, P["ua"] + P["fa"] + 0.008, 0.026, 0.019),
              leg=(kn + 0.05, J["ankle_z"] + 0.01, 0.032, 0.022), geta="cloth_accent")
    b.neck(0.034)
    b.head_face("near")


# ================================================================ keeper

def keeper(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = hip - 0.10 * lk
    T = SoftTube([
        (nb + 0.024, 0.056, 0.052, 0.060, 0.006, 2.0),
        (nb + 0.004, 0.076, 0.064, 0.070, 0.005, 2.0),
        (sz - 0.010, 0.128, 0.086, 0.084, 0.003, 2.0),
        (sz - 0.034, 0.172, 0.100, 0.092, 0.0, 2.0),
        (sz - 0.062, 0.186, 0.108, 0.098, 0.0, 2.0),
        (sz - 0.095, 0.180, 0.116, 0.100, 0.0, 2.05),
        (ch + 0.03, 0.172, 0.120, 0.102, -0.004, 2.2),
        (sp, 0.162, 0.112, 0.102, 0.0, 2.2),
        (hip + 0.04, 0.168, 0.116, 0.116, 0.0, 2.2),
        (hem, 0.182, 0.126, 0.124, 0.0, 2.15),
    ], fold=make_folds(sp, hem, 0.005, seed=4, front_quiet=0.8))
    zs = list(np.linspace(nb + 0.024, sz - 0.08, 9)) + list(np.linspace(sz - 0.08, hem, 9)[1:])
    wf = b.robe_weights(hip + 0.02, hem - 0.25, sidew=0.06, shin_max=0.0, hips_keep=0.5)
    b.robe(T, zs, wf, n=40, tag="happi", fold_top=(0.012, 0.025), fold_bot=(0.012, 0.03))
    tw = lambda p: torso_w(J, p)
    pts = lapels_soft(b, T, nb + 0.018, ch + 0.01, hem, 0.046, 0.007, "cloth_accent", tw,
                      extra_left=[(math.pi - 0.03, ch - 0.06), (math.pi - 0.06, sp - 0.03)], open_th=0.62)
    OF.v_patch(b, T, pts, nb, ch + 0.01, "cloth_dark", tw)
    z0, z1 = sp - 0.02, sp + 0.045
    b.obi_soft(T, z0, z1, 0.013, "cloth_accent", tw, C=np.full(3, 0.92), round_h=0.009)
    B = T.point((z0 + z1) / 2, 0.0, off=0.02)
    b.blob(B + np.array([0.0, 0.004, 0.0]), (X, Y, Z), (0.04, 0.014, 0.026), "cloth_accent", tw, nu=14, nv=8, p=2.6,
           C=np.full(3, 0.85), tag="knot")
    for sg in (1, -1):
        b.lobe(B + np.array([sg * 0.01, 0.01, -0.005]), np.array([sg * 0.45, 0.15, -1.0]), 0.08, 0.018, 0.006,
               "cloth_accent", tw, up=np.array([1.0, 0, 0.4]), pinch=0.8, nst=6, nar=10, p=3.0, tag="knot", crease=False)
    # apron (front, waist to knee) with softly rounded lower corners
    A = OF.T_([(z0, 0.162 + 0.02, 0.112 + 0.02, 0.10, 0.0, 2.4), (hip + 0.04, 0.17 + 0.022, 0.114 + 0.024, 0.11, 0.0, 2.4),
               (hem - 0.02, 0.17, 0.13, 0.12, 0.0, 2.4), (kn - 0.03, 0.165, 0.13, 0.12, 0.0, 2.4)])
    zA = list(np.linspace(z0, kn - 0.03, 9))
    rows = []
    for z in zA:
        f = float(smooth(kn + 0.03, kn - 0.03, z))
        half = 1.1 - 0.12 * f ** 2
        th = np.linspace(math.pi - half, math.pi + half, 19)
        p = A.ringfn(z)(th)
        p[:, 2] += 0.03 * (np.abs(th - math.pi) / half) ** 6 * f
        rows.append(p)
    V = np.concatenate(rows)
    F = b.grid_faces(len(zA), 18)
    F = orient_out(V, F, lambda q: np.array([0, A.params(q[2])[4], q[2]]))
    aw = b.robe_weights(hip + 0.0, kn - 0.03, sidew=0.08, shin_max=0.0, hips_keep=0.3)
    b.mb.add(V, F, "cloth_dark", aw, tag="apron")
    pc = np.full(3, 0.62)
    S = OF.T_([(sp, 0.150, 0.100, 0.096, 0.0, 2.2), (hip, 0.150, 0.104, 0.110, 0.0, 2.2), (hip - 0.06, 0.12, 0.09, 0.096, 0.0, 2.2)])
    b.tube_mesh(S, [r[0] for r in S.r], "cloth_dark", b.robe_weights(hip + 0.02, hip - 0.06, sidew=0.04, shin_max=0.0, hips_keep=0.4),
                n=28, uv=False, C=pc, tag="pants")
    for side in ("L", "R"):
        b.leg_skin(side, hip + 0.01, J["ankle_z"] + 0.06, 0.072, 0.044, mat="cloth_dark", n=16, C=pc)
        b.sleeve_tube(side, 0.025, P["ua"] + P["fa"] * 0.30, 0.050, 0.072, p=2.25, depth=1.12, r_top=0.026, lip=0.012,
                      r_start=0.82)
        b.arm_skin(side, P["ua"] * 0.6, P["ua"] + P["fa"] + 0.01, 0.040, 0.031, mat="cloth_dark", n=12)
        b.hand_soft(side)
        b.tabi(side)
    b.neck(0.050)
    b.head_face("near")
    c = b.head_center()
    phi = np.linspace(0, TAU, 37)[:-1]
    lam = np.interp(OF.frontness(phi), [0, 1], [0.42, 0.30])
    D = np.stack([np.sin(phi) * np.cos(lam), np.cos(phi) * np.cos(lam), np.sin(lam)], 1)
    path = c + (b.head_point(D) - c) * 1.075
    tw_ang = phi * 6
    V, F, U, RI = sweep(path, 0.011, 8, closed_path=True, r2=0.0075, twist=np.append(tw_ang, tw_ang[0]))
    ang = np.arctan2(V[:, 1] - c[1], V[:, 0] - c[0])
    Cc = np.where((np.sin(ang * 6 + V[:, 2] * 400) > 0)[:, None], np.ones(3), np.array([0.82, 0.82, 0.82]))
    b.mb.add(V, F, "cloth_accent", {"head": 1.0}, C=Cc, tag="hachimaki")
    kp = path[int(len(path) * 0.62)]
    out = norm(kp - c)
    b.blob(kp + out * 0.008, (X, Y, Z), (0.017, 0.017, 0.015), "cloth_accent", {"head": 1.0}, nu=10, nv=6, tag="knot")
    for dv in (np.array([-0.02, -0.02, 0.05]), np.array([-0.04, -0.005, 0.03])):
        q = kp + out * 0.01
        V, F, U, RI = sweep(np.array([q, q + dv * 0.5, q + dv]), np.array([0.009, 0.007, 0.004]), 7, r2=np.array([0.004, 0.004, 0.003]))
        b.mb.add(V, F, "cloth_accent", {"head": 1.0}, tag="knot")
    th = np.linspace(0, TAU, 25)[:-1]
    zt = sz + 0.018 - 0.012 * np.abs(np.sin(th))
    ring_pts = np.stack([0.090 * np.sin(th), 0.006 + 0.076 * np.cos(th), zt], 1)
    V, F, U, RI = sweep(ring_pts, 0.024, 9, closed_path=True, r2=0.011)
    b.mb.add(V, F, "cloth_accent", tw, tag="towel")
    for sg in (1, -1):
        a = np.array([sg * 0.052, -0.064, sz + 0.0])
        path = np.array([a, a + [sg * 0.004, -0.02, -0.04], a + [sg * 0.007, -0.034, -0.09], a + [sg * 0.008, -0.045, -0.15]])
        V, F, U, RI = sweep(path, 0.022, 8, r2=0.0065)
        Cc = np.ones((len(V), 3))
        Cc[V[:, 2] < a[2] - 0.11] = [0.65, 0.72, 0.9]
        b.mb.add(V, F, "cloth_accent", tw, C=Cc, tag="towel")


# ================================================================ elder

def elder(b):
    J, P, lk = b.J, b.P, b.lk
    nb, sz = J["neck_base"], J["shoulder_z"]
    ch, sp, hip, kn = J["chest"][2], J["spine"][2], P["hip"], J["knee_z"]
    hem = J["ankle_z"] + 0.045 * lk
    hc, hn, hh = P["hunch"]
    z0, z1 = sp - 0.015, sp + 0.12
    T = SoftTube([
        (nb + 0.022, 0.046, 0.042, 0.050, -hn + 0.006, 2.0),
        (nb + 0.004, 0.062, 0.052, 0.062, -hn * 0.9, 2.0),
        (sz - 0.010, 0.104, 0.066, 0.082, -hn * 0.75, 2.0),
        (sz - 0.030, 0.136, 0.076, 0.094, -hn * 0.6, 2.0),
        (sz - 0.054, 0.160, 0.084, 0.098, -hn * 0.45, 2.0),
        (sz - 0.082, 0.154, 0.090, 0.098, -hn * 0.3, 2.05),
        (sz - 0.115, 0.140, 0.096, 0.096, -hn * 0.15, 2.1),
        (ch, 0.132, 0.098, 0.094, -hc, 2.1),
        (sp, 0.124, 0.094, 0.090, 0.0, 2.1),
        (hip + 0.04, 0.136, 0.102, 0.108, 0.0, 2.1),
        (hip - 0.10, 0.140, 0.104, 0.108, 0.0, 2.1),
        (kn, 0.132, 0.102, 0.100, 0.0, 2.1),
        (hem, 0.140, 0.106, 0.102, -0.004, 2.05),
    ], fold=make_folds(hip - 0.05, hem, 0.007 * lk, seed=5, front_quiet=0.6))
    zs = list(np.linspace(nb + 0.022, sz - 0.11, 10)) + list(np.linspace(sz - 0.11, z1 + 0.01, 4)[1:]) + \
        list(np.linspace(z1 + 0.01, z0 - 0.01, 4)[1:]) + list(np.linspace(z0 - 0.01, hem, 8)[1:])
    wf = b.robe_weights(hip + 0.02, hem)
    b.robe(T, zs, wf, n=40)
    tw = lambda p: torso_w(J, p)
    circ = TAU * 0.13 * 0.9
    pts = lapels_soft(b, T, nb + 0.016, ch + 0.03, z1 - 0.01, 0.028, 0.006, "cloth_accent", tw, col=np.full(3, 1.0))
    OF.v_patch(b, T, pts, nb, ch + 0.03, "skin", tw)
    overlap_edge(b, T, math.pi + 0.40, z0, math.pi + 0.46, hem + 0.004, wf, nb + 0.022, circ)
    b.obi_soft(T, z0, z1, 0.013, "cloth_accent", tw, C=np.full(3, 0.9))
    # rounded taiko knot
    B = T.point((z0 + z1) / 2 + 0.01, 0.0, off=0.034)
    b.blob(B, (X, Y, Z), (0.102, 0.030, 0.082), "cloth_accent", tw, nu=20, nv=10, p=2.8, C=np.full(3, 0.82), tag="taiko")
    b.blob(B + np.array([0, 0.006, 0.07]), (X, Y, Z), (0.098, 0.022, 0.016), "cloth_accent", tw, nu=16, nv=6, p=2.4,
           C=np.full(3, 0.74), tag="taiko")
    for side in ("L", "R"):
        b.sleeve_panel(side, 0.035, P["ua"] + P["fa"] * 0.78, 0.046, 0.18 * lk, ext=0.065 * lk, sag=0.018)
        limbs(b, side, arm=(P["ua"] + P["fa"] * 0.55, P["ua"] + P["fa"] + 0.012, 0.026, 0.022),
              leg=(kn - 0.04, J["ankle_z"] + 0.012, 0.040, 0.028), geta="cloth_dark")
    b.neck(0.037)
    b.head_face("near")
    OF.fan(b)


BUILDERS = {"woman": woman, "man": man, "kid": kid, "keeper": keeper, "elder": elder}
