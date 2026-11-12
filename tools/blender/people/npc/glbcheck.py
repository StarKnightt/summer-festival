"""Checks on the exported GLB itself, the way the game plays it (pure numpy, no Blender).

Every clip is evaluated on every variant exactly as three.js does: tracks are bound by bone NAME to
that variant's own nodes (rest transforms where a clip has no track), keys are interpolated
linearly (slerp for rotations), node matrices are composed down the hierarchy, and the shoe meshes
are skinned with the file's joints, weights and inverse bind matrices. Nothing is taken from the
Blender scene, so this also proves the leg-unit rest scales (glbtools.leg_units) do their job.

  feet      lowest point of each shoe over the clip (mm above the floor): right = npc_<v>_geta_R,
            left = the foot_L vertices of npc_<v>_body
  slip      locomotion clips: sampled at 240 Hz; whenever a shoe's lowest vertex is within 3 mm of
            the floor its horizontal velocity is compared with the ground's. The ground speed
            itself (clipSpeed) is the mean backward speed of those contact points, per variant.
  seams     loops: last key equals first key on every track; one-shots: first and last pose equal
            the idle's first pose
  travel    horizontal range of the hips over the clip
"""
import math

import numpy as np

from . import glbtools as G


def _quat_mats(q):
    q = q / np.linalg.norm(q)
    return G.quat_mat(q)


def _slerp(a, b, u):
    d = float(a @ b)
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + (b - a) * u
    else:
        th = math.acos(min(d, 1.0))
        q = (math.sin((1 - u) * th) * a + math.sin(u * th) * b) / math.sin(th)
    return q / np.linalg.norm(q)


class Model:
    def __init__(self, js, binc, variants):
        self.js, self.bin = js, binc
        nodes = js["nodes"]
        self.idx = {n.get("name"): i for i, n in enumerate(nodes)}
        self.parent = {}
        for i, n in enumerate(nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self.var = {}
        for v in variants:
            top = self.idx[f"npc_{v}"]
            order = G.subtree(js, top)                    # parents before children
            self.var[v] = dict(top=top, order=order, byname={nodes[i]["name"]: i for i in order})
        self.rest = {}
        for i, n in enumerate(nodes):
            self.rest[i] = (np.array(n.get("translation", [0, 0, 0]), float), np.array(n.get("rotation", [0, 0, 0, 1]), float),
                            np.array(n.get("scale", [1, 1, 1]), float))
        self.anims = {}
        for an in js.get("animations", []):
            tr = []
            for ch in an["channels"]:
                s = an["samplers"][ch["sampler"]]
                assert s.get("interpolation", "LINEAR") == "LINEAR"
                tr.append((nodes[ch["target"]["node"]]["name"], ch["target"]["path"],
                           G.accessor(js, binc, s["input"]).astype(np.float64)[:, 0],
                           G.accessor(js, binc, s["output"]).astype(np.float64)))
            self.anims[an["name"]] = tr
        self._skin = {}

    def duration(self, clip):
        return max(float(t[-1]) for _, _, t, _ in self.anims[clip])

    def sample(self, clip, t):
        """{(bone, path): value} at time t."""
        out = {}
        for bone, path, ts, vs in self.anims[clip]:
            if t <= ts[0]:
                out[(bone, path)] = vs[0]
            elif t >= ts[-1]:
                out[(bone, path)] = vs[-1]
            else:
                i = int(np.searchsorted(ts, t, side="right")) - 1
                u = (t - ts[i]) / (ts[i + 1] - ts[i])
                out[(bone, path)] = _slerp(vs[i], vs[i + 1], u) if path == "rotation" else vs[i] + (vs[i + 1] - vs[i]) * u
        return out

    def world(self, v, vals=None):
        """World matrices of variant v's nodes with the sampled values bound by bone name."""
        vals = vals or {}
        V = self.var[v]
        nodes = self.js["nodes"]
        W = {}
        for i in V["order"]:
            nm = nodes[i]["name"]
            T, R, S = self.rest[i]
            T = vals.get((nm, "translation"), T)
            R = vals.get((nm, "rotation"), R)
            M = np.eye(4)
            M[:3, :3] = _quat_mats(np.asarray(R, float)) * S[None, :]
            M[:3, 3] = T
            p = self.parent.get(i)
            W[i] = (W[p] @ M) if p in W else M
        return W

    def skin(self, v, mesh_name, select=None):
        """(positions, joints, weights, joint node list, inverse bind matrices) of a skinned
        mesh node; select(names, joints, weights) -> boolean mask of the vertices to keep."""
        key = (v, mesh_name)
        if key in self._skin:
            return self._skin[key]
        js, binc = self.js, self.bin
        node = js["nodes"][self.var[v]["byname"][mesh_name]]
        sk = js["skins"][node["skin"]]
        ibm = G.accessor(js, binc, sk["inverseBindMatrices"]).astype(np.float64).reshape(-1, 4, 4).transpose(0, 2, 1)
        P, Jn, Wt = [], [], []
        for prim in js["meshes"][node["mesh"]]["primitives"]:
            a = prim["attributes"]
            P.append(G.accessor(js, binc, a["POSITION"]).astype(np.float64))
            Jn.append(G.accessor(js, binc, a["JOINTS_0"]).astype(np.int64))
            w = G.accessor(js, binc, a["WEIGHTS_0"]).astype(np.float64)
            ct = js["accessors"][a["WEIGHTS_0"]]["componentType"]
            Wt.append(w / (255.0 if ct == 5121 else 65535.0 if ct == 5123 else 1.0))
        P, Jn, Wt = np.vstack(P), np.vstack(Jn), np.vstack(Wt)
        if select is not None:
            names = [js["nodes"][j]["name"] for j in sk["joints"]]
            m = select(names, Jn, Wt)
            P, Jn, Wt = P[m], Jn[m], Wt[m]
        self._skin[key] = (np.hstack([P, np.ones((len(P), 1))]), Jn, Wt, sk["joints"], ibm)
        return self._skin[key]

    def skinned(self, v, mesh_name, W, select=None):
        P, Jn, Wt, joints, ibm = self.skin(v, mesh_name, select)
        M = np.array([W[j] for j in joints]) @ ibm                    # (nj, 4, 4)
        out = np.einsum("vk,vkij,vj->vi", Wt, M[Jn], P)
        return out[:, :3]


def _left_foot(names, Jn, Wt):
    j = names.index("foot_L")
    return ((Jn == j) * Wt).sum(axis=1) > 0.5


def feet(model, v, W):
    """Skinned shoe vertices (glTF space: Y up, the character faces +Z): {"L": (n, 3), "R": ...}."""
    return {"R": model.skinned(v, f"npc_{v}_geta_R", W), "L": model.skinned(v, f"npc_{v}_body", W, _left_foot)}


def rest_check(model, variants):
    """Rest pose: skinning must reproduce the stored vertices (the leg-unit scales cancel)."""
    out = {}
    for v in variants:
        W = model.world(v)
        P = model.skin(v, f"npc_{v}_geta_R")[0][:, :3]
        out[v] = round(float(np.abs(model.skinned(v, f"npc_{v}_geta_R", W) - P).max()) * 1000, 4)
    return out


def clip_feet(model, v, clip, rate=30.0):
    """Lowest point of each shoe over the clip and the hips' horizontal range."""
    T = model.duration(clip)
    n = max(2, int(round(T * rate)) + 1)
    lo = {"L": [], "R": []}
    hips = []
    hi = model.var[v]["byname"]["hips"]
    for t in np.linspace(0.0, T, n):
        W = model.world(v, model.sample(clip, t))
        F = feet(model, v, W)
        for s in F:
            lo[s].append(float(F[s][:, 1].min()))
        hips.append(W[hi][:3, 3].copy())
    hips = np.array(hips)
    r = lambda a: [round(float(min(a)) * 1000, 1), round(float(max(a)) * 1000, 1)]
    both = np.minimum(lo["L"], lo["R"])
    return dict(soleL_mm=r(lo["L"]), soleR_mm=r(lo["R"]), lowestOfBoth_mm=r(both),
                hipsTravel_cm=[round(float(np.ptp(hips[:, 0])) * 100, 2), round(float(np.ptp(hips[:, 2])) * 100, 2)],
                hipsHeight_m=[round(float(hips[:, 1].min()), 4), round(float(hips[:, 1].max()), 4)])


def slip(model, v, clip, speed=None, rate=240.0, contact=0.003):
    """Planted-foot slip of an in-place locomotion loop on variant v. Returns the measured ground
    speed (mean backward speed of the contact points) and the slip against `speed` (or against
    that measurement when speed is None)."""
    T = model.duration(clip)
    m = int(round(T * rate))
    dt = T / m
    P = {"L": [], "R": []}
    for i in range(m):
        W = model.world(v, model.sample(clip, i * dt))
        F = feet(model, v, W)
        for s in F:
            P[s].append(F[s])
    rec = []
    for s in P:
        A = np.array(P[s])
        for i in range(m):
            k = int(np.argmin(A[i, :, 1]))
            y = A[i, k, 1]
            if y > contact:
                continue
            vel = (A[(i + 1) % m, k] - A[(i - 1) % m, k]) / (2 * dt)
            rec.append((s, i * dt, y, vel[0], vel[2]))
    if not rec:
        return dict(error="no contact")
    vz = np.array([r[4] for r in rec])
    vx = np.array([r[3] for r in rec])
    measured = float(-vz.mean())
    sp = measured if speed is None else speed
    sl = np.hypot(vx, vz + sp)
    w = int(np.argmax(sl))
    ys = np.array([r[2] for r in rec])
    both = [min(P["L"][i][:, 1].min(), P["R"][i][:, 1].min()) for i in range(m)]
    return dict(speed=round(sp, 4), measuredSpeed=round(measured, 4), cycle_s=round(T, 4), samples=int(len(rec)),
                maxSlip_cm_s=round(float(sl.max()) * 100, 2), p95Slip_cm_s=round(float(np.percentile(sl, 95)) * 100, 2),
                meanSlip_cm_s=round(float(sl.mean()) * 100, 2), worstAt=f"{rec[w][0]} t={rec[w][1]:.3f}s",
                contactHeight_mm=[round(float(ys.min()) * 1000, 1), round(float(ys.max()) * 1000, 1)],
                lowestSole_mm=[round(float(min(both)) * 1000, 1), round(float(max(both)) * 1000, 1)])


def seams(model, loops, oneshots, ref="idle"):
    """Loops: largest difference between a track's first and last key (rotation in degrees,
    translation in mm). One-shots: the same against the idle's first key, at both ends."""
    def ang(a, b):
        return math.degrees(2 * math.acos(min(1.0, abs(float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))))))
    out = {}
    ref0 = {(b, p): vs[0] for b, p, ts, vs in model.anims[ref]}
    for clip, tr in model.anims.items():
        worst_r = worst_t = 0.0
        for b, p, ts, vs in tr:
            pairs = [(vs[0], vs[-1])] if clip in loops else [(vs[0], ref0[(b, p)]), (vs[-1], ref0[(b, p)])] if clip in oneshots else []
            for a, c in pairs:
                if p == "rotation":
                    worst_r = max(worst_r, ang(a, c))
                else:
                    worst_t = max(worst_t, float(np.linalg.norm(a - c)) * 1000)
        out[clip] = dict(kind="loop" if clip in loops else "one-shot", rot_deg=round(worst_r, 3), pos_mm=round(worst_t, 3))
    return out


def tracks(model):
    """Per clip: channel count, whether head and neck have a rotation track, translation tracks."""
    out = {}
    for clip, tr in model.anims.items():
        rot = {b for b, p, _, _ in tr if p == "rotation"}
        out[clip] = dict(rotation=len(rot), translation=sorted(b for b, p, _, _ in tr if p == "translation"),
                         head="head" in rot, neck="neck" in rot, keys=int(sum(len(ts) for _, _, ts, _ in tr)))
    return out


def head_turn(model, v, clip, rate=30.0):
    """Largest heading of head and chest away from straight ahead over the clip (degrees)."""
    T = model.duration(clip)
    n = int(round(T * rate)) + 1
    by = model.var[v]["byname"]
    W0 = model.world(v)
    out = {}
    for b in ("chest", "head"):
        R0 = W0[by[b]][:3, :3]
        mx = 0.0
        for t in np.linspace(0, T, n):
            W = model.world(v, model.sample(clip, t))
            f = W[by[b]][:3, :3] @ R0.T @ np.array([0.0, 0.0, 1.0])
            mx = max(mx, abs(math.degrees(math.atan2(f[0], f[2]))))
        out[b] = round(mx, 1)
    return out
