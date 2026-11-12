"""Her head: skin (SDF head + ears) and the painted-geometry face (eyes, lashes, brows, mouth,
nose, blush) in ONE mesh `heroine_head` with shape keys `blink` and `smile`.

Face layout (barefoot frame, her left eye; the right is mirrored):
  crown 1.505, chin 1.284 (head 0.221 m). Eye 14.5..44.5 mm out from the centre line (one eye width
  apart), 1.371..1.400 m high (eye line at the middle of the head); warm brown iris with highlights.
  Brows ~1.415, nose tip ~1.341, mouth 1.318, ears 1.358..1.400.
Blink: both lids meet on a soft arc 30% up from the lower lid and the upper lash line folds onto it.
Smile: the eyes bow upward a little (they keep their size), brows and blush lift, the mouth widens
and its corners curl up. Each key only closes or moves, so blink + smile together stay clean.
"""
import math

import numpy as np

from . import rig
from . import shape as S
from . import tex
from .common import catmull, image_from_array, make_mesh, material, merge_geo, mirror, norm, orient

# Eye outline (her left): s from inner (0) to outer (1) corner. Proportions follow the usual
# modern-anime front-view construction (refs/heroine): the eye line sits at the vertical middle of
# the head (crown 1.505, chin 1.284 -> 1.394; eye centre 1.386), one eye width (29 mm) between the
# eyes, eye 30 mm wide and 29 mm tall (about 1/6 of the 0.17 m face, hairline to chin).
EYE_X0, EYE_X1 = 0.0145, 0.0445
TOP = np.array([[0.0, 1.3800], [0.12, 1.3915], [0.40, 1.3995], [0.72, 1.3990], [0.90, 1.3940], [1.0, 1.3868]])
BOT = np.array([[0.0, 1.3762], [0.15, 1.3728], [0.50, 1.3708], [0.82, 1.3726], [1.0, 1.3812]])
CLOSE = 0.30          # blink: both lids meet 30% of the way up from the lower lid (a soft downward arc)
SMILE_LIFT = 0.0012   # smile: the whole eye bows upward a touch - it moves, it never opens or grows
LID_LIFT = 0.0036     # smile: the lower lid rises this far over the bottom of the eye


def _top(s):
    return catmull(TOP, s)[:, 0]


def _bot(s):
    return catmull(BOT, s)[:, 0]


def _lids(s, state):
    """(top, bottom) lid heights for state. Every state is a sum of the basis and two deltas that
    are each a pure closing (blink) or a pure rigid lift (smile), so blink + smile at 1 together
    is the closed lid line lifted: it never inverts and the eye never gets bigger."""
    sc = np.clip(s, 0, 1)
    top, bot = _top(sc), _bot(sc)
    if state == "blink":
        c = bot + CLOSE * (top - bot)
        top, bot = c + 0.0004, c
    if state == "smile":
        u = SMILE_LIFT * np.sin(np.pi * sc) ** 0.8
        top, bot = top + u, bot + u
    return top, bot


def _lid_lift(s, state):
    """How far the lower lid (a skin-coloured band + its lash line) rides up over the bottom of
    the eye: the 'happy eyes' of the smile. The eye itself is not resized. It stays below the
    closed lid line (30% up), so blink + smile is still one clean line."""
    if state != "smile":
        return np.zeros_like(np.asarray(s, float))
    return LID_LIFT * np.sin(np.pi * np.clip(s, 0, 1)) ** 0.8


def lid_geo(state):
    """Lower lid: a skin band tucked under the eye's lower edge (invisible at rest)."""
    cols = 13
    s = np.linspace(0, 1, cols)
    x = EYE_X0 + s * (EYE_X1 - EYE_X0)
    bot = _bot(s)
    X = np.stack([x, x])
    # The band's lower edge is sunk into the skin, so it has no visible edge and casts no shadow.
    if state == "blink":      # closed eyes: the band folds away under the skin
        V = np.vstack([_decal_grid(x, bot - 0.0030, -0.0006), _decal_grid(x, bot - 0.0030, -0.0006)])
        return V, _grid_faces(2, cols)
    V = np.vstack([_decal_grid(x, bot - 0.0030, -0.0006), _decal_grid(x, bot + _lid_lift(s, state), 0.0010)])
    return V, _grid_faces(2, cols)


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
    top, bot = _lids(s, state)
    X = np.tile(x, (rows, 1))
    Z = bot[None, :] + t[:, None] * (top - bot)[None, :]
    V = _decal_grid(X, Z, 0.0007)
    # UVs from the BASIS layout (the texture stays put while the lids move).
    Zb = _bot(s)[None, :] + t[:, None] * (_top(s) - _bot(s))[None, :]
    U = np.stack([(X.ravel() - tex.EYE_X[0]) / (tex.EYE_X[1] - tex.EYE_X[0]),
                  (Zb.ravel() - tex.EYE_Z[0]) / (tex.EYE_Z[1] - tex.EYE_Z[0])], axis=1)
    return V, _grid_faces(rows, cols), U


def lash_geo(state):
    """Upper lash line: a firm band along the top lid, thickest toward the outer corner, ending in
    a short flick out and up."""
    cols = 18
    s = np.linspace(-0.04, 1.0, cols)
    x = EYE_X0 + s * (EYE_X1 - EYE_X0)
    top, bot = _lids(s, state)
    sc = np.clip(s, 0, 1)
    w = 0.0011 + 0.0021 * sc ** 1.1 - 0.0008 * sc ** 6
    if state == "blink":
        w = w * 0.8
    lo = top - 0.0008
    hi = top + w
    # Flick: three extra columns curling out and up past the outer corner.
    fx = EYE_X1 + np.array([0.0018, 0.0034, 0.0047])
    fz_lo = top[-1] + np.array([-0.0003, 0.0007, 0.0019])
    fz_hi = fz_lo + np.array([0.0024, 0.0016, 0.0007])
    xs = np.concatenate([x, fx])
    lo = np.concatenate([lo, fz_lo])
    hi = np.concatenate([hi, fz_hi])
    X = np.stack([xs, xs])
    Z = np.stack([lo, hi])
    V = _decal_grid(X, Z, 0.0015)
    return V, _grid_faces(2, len(xs))


def lower_lash_geo(state):
    """A thin lower-lid line on the outer half (it folds into the closed lid line on a blink)."""
    cols = 9
    s = np.linspace(0.45, 1.0, cols)
    x = EYE_X0 + s * (EYE_X1 - EYE_X0)
    top, bot = _lids(s, state)
    w = 0.00035 + 0.00055 * (s - 0.45) / 0.55
    if state == "smile":
        bot = _bot(s) + _lid_lift(s, state)      # rides on the raised lower lid
    lo, hi = bot - w, bot + 0.0002
    if state == "blink":
        lo = hi = top - 0.0004                   # folds to nothing inside the closed lid line
    X = np.stack([x, x])
    Z = np.stack([lo, hi])
    V = _decal_grid(X, Z, 0.0013)
    return V, _grid_faces(2, cols)


def brow_geo(state):
    """Soft, gently arched brows well above the eyes (they sit just under the bang tips)."""
    cols = 10
    s = np.linspace(0, 1, cols)
    x = 0.0120 + s * 0.0345
    zc = 1.4130 + 0.0032 * np.sin(np.pi * (s * 0.85 + 0.1)) - 0.0022 * s
    if state == "smile":
        zc = zc + 0.0016
    w = 0.0008 + 0.0008 * np.sin(np.pi * np.clip(s * 0.9 + 0.05, 0, 1)) - 0.0003 * s
    X = np.stack([x, x])
    Z = np.stack([zc - w, zc + w])
    V = _decal_grid(X, Z, 0.0012)
    return V, _grid_faces(2, cols)


def blush_geo(state="basis"):
    """Soft oval blush on the cheek (her left), under the outer half of the eye."""
    n = 14
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cx, cz, rx, rz = 0.0370, 1.3595, 0.0105, 0.0042
    if state == "smile":                      # cheeks lift
        cz += 0.0030
        rx, rz = rx * 1.08, rz * 1.15
    X = np.concatenate([[cx], cx + rx * np.cos(a)])
    Z = np.concatenate([[cz], cz + rz * np.sin(a)])
    V, _ = S.head_front(X, Z, 0.0006)
    F = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    return V, F


def mouth_geo(state):
    """A small soft closed mouth with the corners turned up a touch (pleasant, not blank)."""
    cols = 11
    s = np.linspace(-1, 1, cols)
    half = 0.0068 if state != "smile" else 0.0108
    x = s * half
    zc = 1.3180 - 0.0003 * (1 - s * s) + 0.0007 * s ** 4
    w = 0.00045 + 0.00035 * (1 - np.abs(s)) ** 0.7
    if state == "smile":                      # a clear, warm closed smile: wider, corners well up
        zc = 1.3166 + 0.0050 * np.abs(s) ** 2.2
        w = w * 1.45 + 0.0001
    X = np.stack([x, x])
    Z = np.stack([zc - w, zc + w])
    V = _decal_grid(X, Z, 0.0010)
    return V, _grid_faces(2, cols)


def lip_geo(state):
    """A faint lower-lip shade under the mouth line."""
    cols = 7
    s = np.linspace(-1, 1, cols)
    x = s * 0.0035
    zc = 1.3150 + 0.0003 * s * s + (0.0006 if state == "smile" else 0.0)
    w = 0.0004 * (1 - s * s) + 0.00005
    V = _decal_grid(np.stack([x, x]), np.stack([zc - w, zc + w]), 0.0009)
    return V, _grid_faces(2, cols)


def nose_geo():
    """A tiny shadow tick under the nose tip."""
    cols = 5
    s = np.linspace(-1, 1, cols)
    x = 0.0026 * s - 0.0007
    zc = 1.3385 + 0.0005 * s * s
    w = 0.00035 + 0.00025 * (1 - np.abs(s))
    V = _decal_grid(np.stack([x, x]), np.stack([zc - w, zc + w]), 0.0010)
    return V, _grid_faces(2, cols)


def skin_geo():
    """Head skin: rays from the head centre to the SDF surface on a lat-long grid whose rows and
    columns crowd toward the centre of the face (rows ~1.9 mm apart from the nose to the chin,
    columns ~2.5 mm apart at the nose), so the profile on the centre line (bridge, nose tip,
    lips, chin) is carried by real geometry. Skin that is hidden well inside the hair cap is
    left out."""
    from . import hair as H
    # Rows: polar angles chosen so the centre-line profile is sampled at the wanted heights.
    tf = np.linspace(0.02, np.pi - 0.02, 1500)
    Df = np.stack([np.zeros_like(tf), -np.sin(tf), np.cos(tf)], -1)
    zf = S.HEAD_C[2] + Df[:, 2] * S.head_radius(Df)
    zf = np.minimum.accumulate(zf)

    def th_at(z):
        return np.interp(-np.asarray(z), -zf, tf)

    z_rows = np.concatenate([np.arange(1.3990, 1.3525, -0.0042), np.arange(1.3525, 1.3000, -0.0019),
                             np.arange(1.3000, 1.2870, -0.0030)])
    t0, t1 = th_at(1.4032), th_at(z_rows[-1])
    th = np.concatenate([np.linspace(0, t0, 10)[1:], th_at(z_rows), np.linspace(t1, np.pi, 7)[1:-1]])
    half = np.array([0.03, 0.06, 0.095, 0.135, 0.18, 0.235, 0.30, 0.38, 0.47, 0.57, 0.68, 0.80, 0.93, 1.07, 1.22,
                     1.38, 1.55, 1.75, 2.0, 2.3, 2.65])
    ph = np.concatenate([[0.0], half, [np.pi], 2 * np.pi - half[::-1]])
    rows, cols = len(th), len(ph)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    D = np.stack([np.sin(TH) * np.sin(PH), -np.sin(TH) * np.cos(PH), np.cos(TH)], axis=-1).reshape(-1, 3)
    r = S.head_radius(D)
    V = S.HEAD_C + D * r[:, None]
    # Hidden under the hair: more than 13 mm above the hairline at its azimuth.
    d = V - S.HEAD_C
    az = np.degrees(np.abs(np.arctan2(d[:, 0], -d[:, 1])))
    hidden = V[:, 2] > catmull(H.HAIRLINE, az)[:, 0] + 0.013
    F = []
    for i in range(rows - 1):
        for j in range(cols):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            q = (a, b, b + cols, a + cols)
            if not all(hidden[k] for k in q):
                F.append(q)
    bot = len(V)
    V = np.vstack([V, S.HEAD_C - np.array([0, 0, S.head_radius(np.array([[0, 0, -1.0]]))[0]])])
    o = (rows - 1) * cols
    for j in range(cols):
        F.append((bot, o + j, o + (j + 1) % cols))
    used = sorted({i for f in F for i in f})
    remap = {k: n for n, k in enumerate(used)}
    V = V[used]
    F = [tuple(remap[i] for i in f) for f in F]
    F = _outward(V, F)
    return V, F


def _ear_centre(y=0.018, z=1.3790, sink=0.0012):
    """Ear centre: on the head's side surface at (y, z), sunk a touch so it sits flush."""
    lo, hi = 0.0, 0.2
    for _ in range(40):
        m = 0.5 * (lo + hi)
        if S.head_sdf(np.array([[m, y, z]]))[0] < 0:
            lo = m
        else:
            hi = m
    return np.array([0.5 * (lo + hi) - sink, y, z])


# Top just under brow level (1.405), lobe at nose-tip level (1.352), behind the middle of the jaw.
EAR_C = _ear_centre()
EAR_HZ = 0.0265


def ear_geo():
    """Her left ear: a small flattened, slightly cupped oval tilted back."""
    rows, cols = 8, 12
    th = np.linspace(0.15, np.pi - 0.15, rows)
    ph = np.linspace(0, 2 * np.pi, cols, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    lx = 0.0050 * np.sin(TH) * np.cos(PH)
    ly = 0.0130 * np.sin(TH) * np.sin(PH) * (1.0 + 0.18 * np.cos(TH))   # a little wider at the top
    lz = EAR_HZ * np.cos(TH)
    ly = ly + 0.0030 * (lz / EAR_HZ) ** 2               # rim curls back at top and bottom
    P = np.stack([lx, ly, lz], -1).reshape(-1, 3)
    tilt = np.radians(-14)
    R = np.array([[1, 0, 0], [0, math.cos(tilt), -math.sin(tilt)], [0, math.sin(tilt), math.cos(tilt)]])
    P = P @ R.T + EAR_C
    V, F = P, []
    for i in range(rows - 1):
        for j in range(cols):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            F.append((a, b, b + cols, a + cols))
    c = EAR_C
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
        parts, mids, uvs, tags = [], [], [], []

        def add(geo, mi, uv=None, both=True, tag="face"):
            V, F = geo[0], geo[1]
            F = _outward(V, F)
            items = [(V, F)]
            if both:
                items.append(mirror(V, F))
            for (Vk, Fk) in items:
                parts.append((Vk, Fk))
                tags.append(np.full(len(Vk), tag == "ear"))
                mids.append(np.full(len(Fk), mi))
                uvs.append(uv if uv is not None else np.zeros((len(Vk), 2)))

        hv, hf = skin_geo()
        add((hv, hf), 0, both=False)
        add(ear_geo(), 0, tag="ear")
        ev, ef, eu = eye_geo(state)
        add((ev, ef), 1, eu)
        add(lash_geo(state), 2)
        add(lid_geo(state), 0)
        add(lower_lash_geo(state), 2)
        add(brow_geo(state), 3)
        add(mouth_geo(state), 4, both=False)
        add(nose_geo(), 5, both=False)
        add(lip_geo(state), 5, both=False)
        add(blush_geo(state), 6)
        V, F = merge_geo(parts)
        assemble.ear = np.concatenate(tags)
        return V, F, np.concatenate(mids), np.vstack(uvs)

    V, F, mi, UV = assemble("basis")
    ear = assemble.ear
    ob = make_mesh("heroine_head", V, F, col, mats, mi)
    # Normals straight from the analytic head surface (skin and the painted features on it), so
    # the tessellation can never put a facet or a shading dent into the face under a hard toon
    # terminator. The ears keep their own mesh normals.
    me = ob.data
    vn = np.zeros(len(V) * 3)
    me.vertices.foreach_get("normal", vn)
    N = S.head_grad_soft(V)
    N[ear] = vn.reshape(-1, 3)[ear]
    me.normals_split_custom_set_from_vertices([tuple(n) for n in N])
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
