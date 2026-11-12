"""Her head: skin (SDF head + ears) and the painted-geometry face (eyes, lashes, brows, mouth,
nose, blush) in ONE mesh `heroine_head` with shape keys `blink` and `smile`.

Face layout (barefoot frame, her left eye; the right is mirrored):
  eye 15..53 mm out from the centre line, 1.350..1.389 m high; iris amber-brown, two highlights.
  brows ~1.405, nose tip 1.350, mouth 1.316, chin 1.284.
Blink: the eye decals collapse onto the lower lid curve and the upper lash line drops onto it,
which reads as a soft closed anime eye. Smile: cheeks push the lower lids up a little, the eyes
narrow, the mouth corners curl up.
"""
import math

import numpy as np

from . import rig
from . import shape as S
from . import tex
from .common import catmull, image_from_array, make_mesh, material, merge_geo, mirror, norm, orient

# Eye outline (her left): s from inner (0) to outer (1) corner.
EYE_X0, EYE_X1 = 0.0165, 0.0515
TOP = np.array([[0.0, 1.3625], [0.12, 1.3780], [0.40, 1.3885], [0.72, 1.3870], [0.90, 1.3800], [1.0, 1.3715]])
BOT = np.array([[0.0, 1.3570], [0.15, 1.3520], [0.50, 1.3500], [0.82, 1.3525], [1.0, 1.3640]])


def _top(s):
    return catmull(TOP, s)[:, 0]


def _bot(s):
    return catmull(BOT, s)[:, 0]


def _decal_grid(xs, zs, off):
    """Project a (rows, cols) grid of (x, z) onto the face; returns points (rows*cols, 3)."""
    P, _ = S.head_front(xs.ravel(), zs.ravel(), off)
    return P


def _grid_faces(rows, cols):
    F = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = r * cols + c
            F.append((a, a + 1, a + cols + 1, a + cols))
    return F


def _outward(V, F):
    return orient(V, F, lambda C: np.tile(S.HEAD_C, (len(C), 1)) + (C - S.HEAD_C) * 0.5)


def eye_geo(state):
    """Left eye decal for state in ('basis', 'blink', 'smile'): (V, F, UV)."""
    cols, rows = 15, 9
    s = np.linspace(0, 1, cols)
    t = np.linspace(0, 1, rows)
    x = EYE_X0 + s * (EYE_X1 - EYE_X0)
    top, bot = _top(s), _bot(s)
    if state == "smile":
        bot = bot + 0.0060 * np.sin(np.pi * s) ** 0.8
        top = top - 0.0025 * np.sin(np.pi * s)
    if state == "blink":
        top = bot + 0.0004
    X = np.tile(x, (rows, 1))
    Z = bot[None, :] + t[:, None] * (top - bot)[None, :]
    V = _decal_grid(X, Z, 0.0007)
    # UVs from the BASIS layout (the texture stays put while the lids move).
    Zb = _bot(s)[None, :] + t[:, None] * (_top(s) - _bot(s))[None, :]
    U = np.stack([(X.ravel() - tex.EYE_X[0]) / (tex.EYE_X[1] - tex.EYE_X[0]),
                  (Zb.ravel() - tex.EYE_Z[0]) / (tex.EYE_Z[1] - tex.EYE_Z[0])], axis=1)
    return V, _grid_faces(rows, cols), U


def lash_geo(state):
    """Upper lash line: a band along the top lid, thick at the outer end, with a little flick."""
    cols = 18
    s = np.linspace(-0.03, 1.0, cols)
    x = EYE_X0 + s * (EYE_X1 - EYE_X0)
    top, bot = _top(np.clip(s, 0, 1)), _bot(np.clip(s, 0, 1))
    w = 0.0010 + 0.0032 * np.clip(s, 0, 1) ** 1.3
    if state == "smile":
        top = top - 0.0025 * np.sin(np.pi * np.clip(s, 0, 1))
    if state == "blink":
        top = bot + 0.0004
        w = w * 0.75
    lo = top - 0.0009
    hi = top + w
    # Flick: three extra columns curling out and up past the outer corner.
    fx = EYE_X1 + np.array([0.0022, 0.0042, 0.0058])
    fz_lo = top[-1] + np.array([-0.0002, 0.0010, 0.0026]) - (0.001 if state == "blink" else 0.0)
    fz_hi = fz_lo + np.array([0.0030, 0.0020, 0.0008])
    xs = np.concatenate([x, fx])
    lo = np.concatenate([lo, fz_lo])
    hi = np.concatenate([hi, fz_hi])
    X = np.stack([xs, xs])
    Z = np.stack([lo, hi])
    V = _decal_grid(X, Z, 0.0015)
    return V, _grid_faces(2, len(xs))


def lower_lash_geo(state):
    cols = 9
    s = np.linspace(0.45, 1.0, cols)
    x = EYE_X0 + s * (EYE_X1 - EYE_X0)
    bot = _bot(s)
    if state == "smile":
        bot = bot + 0.0060 * np.sin(np.pi * s) ** 0.8
    w = 0.0004 + 0.0007 * (s - 0.45) / 0.55
    X = np.stack([x, x])
    Z = np.stack([bot - w, bot + 0.0002])
    V = _decal_grid(X, Z, 0.0013)
    return V, _grid_faces(2, cols)


def brow_geo(state):
    cols = 10
    s = np.linspace(0, 1, cols)
    x = 0.0150 + s * 0.0350
    zc = 1.4040 + 0.0045 * np.sin(np.pi * (s * 0.85 + 0.1)) - 0.002 * s
    if state == "smile":
        zc = zc + 0.0012
    w = 0.0011 + 0.0011 * np.sin(np.pi * np.clip(s * 0.9 + 0.05, 0, 1))
    X = np.stack([x, x])
    Z = np.stack([zc - w, zc + w])
    V = _decal_grid(X, Z, 0.0012)
    return V, _grid_faces(2, cols)


def blush_geo():
    """Soft oval blush on the cheek (her left)."""
    n = 14
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cx, cz, rx, rz = 0.0460, 1.3410, 0.0125, 0.0055
    X = np.concatenate([[cx], cx + rx * np.cos(a)])
    Z = np.concatenate([[cz], cz + rz * np.sin(a)])
    V, _ = S.head_front(X, Z, 0.0006)
    F = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    return V, F


def mouth_geo(state):
    """A small soft mouth line, centred."""
    cols = 11
    s = np.linspace(-1, 1, cols)
    half = 0.0085 if state != "smile" else 0.0098
    x = s * half
    zc = 1.3160 - 0.0006 * (1 - s * s)
    if state == "smile":
        zc = 1.3155 + 0.0030 * s ** 2 - 0.0006
    w = 0.00055 + 0.00035 * (1 - np.abs(s))
    X = np.stack([x, x])
    Z = np.stack([zc - w, zc + w])
    V = _decal_grid(X, Z, 0.0010)
    return V, _grid_faces(2, cols)


def nose_geo():
    """A tiny shadow tick under the nose tip."""
    cols = 5
    s = np.linspace(-1, 1, cols)
    x = 0.0030 * s - 0.0008
    zc = 1.3445 + 0.0006 * s * s
    w = 0.0004 + 0.0003 * (1 - np.abs(s))
    V = _decal_grid(np.stack([x, x]), np.stack([zc - w, zc + w]), 0.0010)
    return V, _grid_faces(2, cols)


def skin_geo():
    """Head skin: rays from the head centre to the SDF surface (lat-long), plus ears."""
    rows, cols = 40, 48
    th = np.linspace(0, np.pi, rows + 2)[1:-1]
    ph = np.linspace(0, 2 * np.pi, cols, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    D = np.stack([np.sin(TH) * np.sin(PH), -np.sin(TH) * np.cos(PH), np.cos(TH)], axis=-1).reshape(-1, 3)
    r = S.head_radius(D)
    V = S.HEAD_C + D * r[:, None]
    F = []
    for i in range(rows - 1):
        for j in range(cols):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            F.append((a, b, b + cols, a + cols))
    top = len(V)
    bot = top + 1
    V = np.vstack([V, S.HEAD_C + np.array([0, 0, S.head_radius(np.array([[0, 0, 1.0]]))[0]]),
                   S.HEAD_C - np.array([0, 0, S.head_radius(np.array([[0, 0, -1.0]]))[0]])])
    for j in range(cols):
        F.append((top, (j + 1) % cols, j))
        o = (rows - 1) * cols
        F.append((bot, o + j, o + (j + 1) % cols))
    F = _outward(V, F)
    return V, F


def ear_geo():
    """Her left ear: a small flattened, slightly cupped oval tilted back."""
    rows, cols = 8, 12
    th = np.linspace(0.15, np.pi - 0.15, rows)
    ph = np.linspace(0, 2 * np.pi, cols, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    lx = 0.0045 * np.sin(TH) * np.cos(PH)
    ly = 0.0105 * np.sin(TH) * np.sin(PH)
    lz = 0.0175 * np.cos(TH)
    ly = ly + 0.0025 * (lz / 0.0175) ** 2               # rim curls back at top and bottom
    P = np.stack([lx, ly, lz], -1).reshape(-1, 3)
    tilt = np.radians(-14)
    R = np.array([[1, 0, 0], [0, math.cos(tilt), -math.sin(tilt)], [0, math.sin(tilt), math.cos(tilt)]])
    P = P @ R.T + np.array([0.0715, 0.016, 1.369])
    V, F = P, []
    for i in range(rows - 1):
        for j in range(cols):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            F.append((a, b, b + cols, a + cols))
    c = np.array([0.0715, 0.016, 1.369])
    F = orient(V, F, lambda C: np.tile(c, (len(C), 1)))
    return V, F


def build(col):
    """-> {"head": object}. Materials: skin, eye (texture), face_line, face_brow, face_mouth,
    face_nose, face_blush."""
    m_skin = material("skin", "#f2cfbb")
    eye_img = image_from_array("T_heroine_eye", tex.eye_texture(256))
    m_eye = material("eye", "#f1ebe4", eye_img)
    m_line = material("face_line", "#3c2723")
    m_brow = material("face_brow", "#6a4535")
    m_mouth = material("face_mouth", "#a05048")
    m_nose = material("face_nose", "#d39784")
    m_blush = material("face_blush", "#eea39d")
    mats = [m_skin, m_eye, m_line, m_brow, m_mouth, m_nose, m_blush]

    def assemble(state):
        parts, mids, uvs = [], [], []

        def add(geo, mi, uv=None, both=True):
            V, F = geo[0], geo[1]
            F = _outward(V, F)
            items = [(V, F)]
            if both:
                items.append(mirror(V, F))
            for (Vk, Fk) in items:
                parts.append((Vk, Fk))
                mids.append(np.full(len(Fk), mi))
                uvs.append(uv if uv is not None else np.zeros((len(Vk), 2)))

        hv, hf = skin_geo()
        add((hv, hf), 0, both=False)
        add(ear_geo(), 0)
        ev, ef, eu = eye_geo(state)
        add((ev, ef), 1, eu)
        add(lash_geo(state), 2)
        add(lower_lash_geo(state), 2)
        add(brow_geo(state), 3)
        add(mouth_geo(state), 4, both=False)
        add(nose_geo(), 5, both=False)
        add(blush_geo(), 6)
        V, F = merge_geo(parts)
        return V, F, np.concatenate(mids), np.vstack(uvs)

    V, F, mi, UV = assemble("basis")
    ob = make_mesh("heroine_head", V, F, col, mats, mi)
    from .common import set_uv_vertex
    set_uv_vertex(ob, UV)
    ob.shape_key_add(name="Basis", from_mix=False)
    for name in ("blink", "smile"):
        Vk, _, _, _ = assemble(name)
        sk = ob.shape_key_add(name=name, from_mix=False)
        sk.data.foreach_set("co", Vk.ravel())
        sk.slider_min, sk.slider_max = 0.0, 1.0
        sk.value = 0.0
    rig.store(ob, {"head": np.ones(len(V))})
    return {"head": ob}
