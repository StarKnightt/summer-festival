"""Festival stall kit + street props -> public/models/stalls.glb

  E:\\blender\\blender-5.1.2-windows-x64\\blender.exe --background --factory-startup --python-exit-code 1 \\
      --python tools/blender/stalls/build.py -- --out public/models/stalls.glb

Blender axes: X right, -Y = front of every stall (= +Z in glTF), Z up. Every top-level node sits at
the world origin, which is the ground centre of its footprint. Deterministic (fixed seeds).
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

sys.dont_write_bytecode = True
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import kit  # noqa: E402
from kit import (MB, R, S, T, box, cyl, hexc, lathe, make_obj, material, mix, ngon_sheet, prism,  # noqa: E402
                 shade, slab, sphere, surf, torus, tube, empty)

TEX_DIR = os.path.join(HERE, "textures")
rng = random.Random(7)

# ----------------------------------------------------------------------------- palette (sRGB hex)
C = {k: hexc(v) for k, v in dict(
    wood="#C99A63", wood_mid="#A8764A", wood_dark="#6B4529", wood_pale="#E2C59A", lacquer="#9A2420",
    black="#2B211D", white="#F6F0E4", cream="#F3E3C3", red="#D63A3A", pink="#F08DAB", blue="#3C7BCB",
    green="#4AA25A", orange="#EE8A2E", indigo="#2F3B7A", indigo2="#5B6BB0", yellow="#F2C14E",
    teal="#2FA39A", iron="#3A3836", steel="#AEB4BA", tub="#5DB6E8", tub_in="#3E9BD9",
    paper_red="#E04436", paper_white="#F7EEDC", gold="#E6B53C", stone="#A7A39B", stone2="#8E8A83",
    terracotta="#B95E3A", bamboo="#B8B05C", leaf="#4E9A3E", noodle="#B8763B", cardboard="#C29A62",
).items()}

# shared materials (white base: colour comes from COLOR_0) -------------------------------------
MAT_NAMES = ["wood_frame", "wood_lacquer", "cloth_awning", "cloth_noren", "cloth_canopy", "metal_iron",
             "metal_tin", "metal_bike", "plastic_misc", "plastic_tub", "plastic_candy", "plastic_bottle",
             "plastic_cup", "plastic_glass", "plastic_ice", "plastic_wax", "plastic_food",
             "plastic_mask_parts", "plastic_furin", "paper_lantern", "paper_poi", "stone_step",
             "cloth_plush", "cloth_furin_strip"]


def setup_materials():
    for n in MAT_NAMES:
        material(n)
    material("water_tub", color=hexc("#4FB0E0"))
    material("glow_flame", color=hexc("#FFC45A"), emissive=hexc("#FFB040"))


# ----------------------------------------------------------------------------- helpers


def M(x=0.0, y=0.0, z=0.0, rz=0.0, rx=0.0, ry=0.0, s=None):
    m = T(x, y, z) @ R("Z", rz) @ R("Y", ry) @ R("X", rx)
    if s is not None:
        m = m @ (S(*s) if isinstance(s, (tuple, list)) else S(s))
    return m


def bx(mb, sx, sy, sz, x, y, z, col, mat="wood_frame", bevel=0.006, rz=0.0, rx=0.0, ry=0.0):
    """Box with its bottom-centre at (x, y, z)."""
    mb.add(box(sx, sy, sz, bevel=bevel, center=(0, 0, sz / 2)), col, mat, M(x, y, z, rz, rx, ry))


def beam(mb, p0, p1, sy, sz, col, mat="wood_frame", bevel=0.006):
    """Rectangular beam between two points (cross-section sy x sz)."""
    a, b = Vector(p0), Vector(p1)
    d = b - a
    L = d.length
    q = d.normalized().to_track_quat("X", "Z")
    m = T(*((a + b) / 2)) @ q.to_matrix().to_4x4()
    mb.add(box(L, sy, sz, bevel=bevel), col, mat, m)


def stick(mb, p0, p1, r, col, mat="wood_frame", n=6):
    mb.add(tube([p0, p1], r, n), col, mat)


def by_z(levels):
    """Colour by world z: levels = [(z_max, col), ...] ascending; last entry catches the rest."""
    def f(c, n):
        for zmax, col in levels:
            if c.z <= zmax:
                return col
        return levels[-1][1]
    return f


def gloss(col, hi, L=(-0.45, -0.55, 0.7), k=0.86):
    Ld = Vector(L).normalized()

    def f(c, n):
        return hi if n.dot(Ld) > k else col
    return f


# ----------------------------------------------------------------------------- reusable props


def chochin_geo(h=0.32, r=0.12, n=10, rings=10):
    """Paper chochin lantern hanging below the origin: (paper geo, caps geo, cord geo)."""
    cap_h = 0.035 * h / 0.32
    body_h = h - 2 * cap_h
    prof = []
    for i in range(rings + 1):
        t = i / rings
        rr = r * (0.66 + 0.34 * math.sin(math.pi * t) ** 0.8)
        if 0 < i < rings and i % 2 == 1:
            rr *= 0.965
        prof.append((rr, -cap_h - t * body_h))
    paper = lathe(prof[::-1], n, cap0=False, cap1=False)
    cr = r * 0.62
    top = cyl(cr * 1.04, cap_h, n, z0=-cap_h)
    bot = cyl(cr * 1.04, cap_h, n, z0=-h)
    return paper, top, bot


def add_chochin(mb, x, y, z, h=0.32, r=0.12, paper_col=None, band=None, cord=0.06, mat_paper="paper_lantern", n=10,
                rings=10):
    """Hang a lantern whose cord top is at (x, y, z)."""
    paper_col = paper_col or C["paper_red"]
    paper, top, bot = chochin_geo(h, r, n, rings)
    zt = z - cord
    m = T(x, y, zt)
    if band is not None:
        cap_h = 0.035 * h / 0.32
        body_h = h - 2 * cap_h

        def pc(c, nn):
            t = (zt - cap_h - c.z) / body_h
            return band if (0.1 < t < 0.2 or 0.8 < t < 0.9) else paper_col
        mb.add(paper, pc, mat_paper, m)
    else:
        mb.add(paper, paper_col, mat_paper, m)
    mb.add(top, C["black"], "wood_lacquer", m)
    mb.add(bot, C["black"], "wood_lacquer", m)
    if cord > 0:
        mb.add(box(0.008, 0.008, cord, center=(0, 0, cord / 2)), C["black"], "wood_lacquer", T(x, y, zt))
        mb.add(torus(0.012, 0.003, 8, 3), C["black"], "wood_lacquer", T(x, y, z) @ R("X", 90))


def lantern_obj(name, parent, hook, h=0.32, r=0.12, red=True, cord=0.06, band=True, n=10, rings=10):
    mb = MB()
    pc = C["paper_red"] if red else C["paper_white"]
    bc = C["white"] if red else C["red"]
    add_chochin(mb, 0, 0, 0, h, r, pc, bc if band else None, cord, n=n, rings=rings)
    # origin = the hook at the top of the cord (pivot for swinging)
    return _place(make_obj(name, mb, parent=parent, props={"role": "lantern"}), hook)


def _place(ob, loc):
    ob.location = loc
    return ob


def bowl_geo(r=0.06, h=0.045, n=12):
    return lathe([(0, 0.004), (r * 0.55, 0.0), (r, h), (r * 0.93, h), (r * 0.5, 0.008), (0, 0.008)], n)


def cooler(mb, x, y, rz=0.0, col=None):
    col = col or C["blue"]
    m = M(x, y, 0, rz)
    mb.add(box(0.5, 0.32, 0.3, bevel=0.025, center=(0, 0, 0.15)), col, "plastic_misc", m)
    mb.add(box(0.52, 0.34, 0.06, bevel=0.02, center=(0, 0, 0.32)), C["white"], "plastic_misc", m)
    mb.add(box(0.2, 0.03, 0.03, bevel=0.01, center=(0, 0, 0.365)), C["white"], "plastic_misc", m)


def stool(mb, x, y, h=0.42, col=None):
    col = col or C["wood_mid"]
    mb.add(cyl(0.15, 0.04, 12, bevel=0.008, z0=h - 0.04), col, "wood_frame", T(x, y, 0))
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.3
        stick(mb, (x + 0.1 * math.cos(a), y + 0.1 * math.sin(a), h - 0.04),
              (x + 0.14 * math.cos(a), y + 0.14 * math.sin(a), 0), 0.014, C["wood_dark"])


def cardboard(mb, x, y, z=0.0, s=(0.4, 0.3, 0.26), rz=0.0):
    m = M(x, y, z, rz)
    mb.add(box(*s, bevel=0.006, center=(0, 0, s[2] / 2)), C["cardboard"], "wood_frame", m)
    mb.add(box(s[0] + 0.002, 0.05, 0.003, center=(0, 0, s[2])), shade(C["cardboard"], 0.7), "wood_frame", m)


# ----------------------------------------------------------------------------- stall frame


class Stall:
    W, D = 2.6, 1.6
    HF, HB = 2.15, 2.4

    def __init__(self, key, c1, c2, counter=True, cd=0.4, ch=0.86, skirt=None, canopy=None):
        self.key = key
        self.name = "stall_" + key
        self.root = empty(self.name, size=0.5, kind="ARROWS", props={"kind": "stall"})
        self.mb = MB()
        self.c1, self.c2 = c1, c2
        self.cd, self.ch = cd, ch
        self.front = -0.80          # counter front face (y)
        self.top_front = -0.84      # counter top front edge
        self.frame()
        self.awning()
        self.valance()
        self.corner_lanterns()
        self.back_canopy(canopy or shade(c1, 0.78))
        if counter:
            self.counter(skirt or c1)

    # structure
    def frame(self):
        mb, W, D = self.mb, self.W, self.D
        px, py = W / 2 - 0.05, D / 2 - 0.05
        self.px, self.py = px, py
        for sx in (-1, 1):
            bx(mb, 0.075, 0.075, self.HF, sx * px, -py, 0, C["wood"])
            bx(mb, 0.075, 0.075, self.HB, sx * px, py, 0, C["wood"])
            # side rails: sloped top, lower stretcher
            beam(mb, (sx * px, -py, self.HF - 0.05), (sx * px, py, self.HB - 0.05), 0.065, 0.08, C["wood_mid"])
            beam(mb, (sx * px, -py, 0.22), (sx * px, py, 0.22), 0.05, 0.06, C["wood_mid"])
            # foot blocks
            bx(mb, 0.13, 0.13, 0.04, sx * px, -py, 0, C["wood_dark"], bevel=0.01)
            bx(mb, 0.13, 0.13, 0.04, sx * px, py, 0, C["wood_dark"], bevel=0.01)
        beam(mb, (-px - 0.06, -py, self.HF - 0.05), (px + 0.06, -py, self.HF - 0.05), 0.07, 0.09, C["wood_mid"])
        beam(mb, (-px - 0.06, py, self.HB - 0.05), (px + 0.06, py, self.HB - 0.05), 0.07, 0.09, C["wood_mid"])
        beam(mb, (-px, py, 0.22), (px, py, 0.22), 0.05, 0.06, C["wood_mid"])
        # middle rafter
        beam(mb, (0, -py, self.HF - 0.02), (0, py, self.HB - 0.02), 0.05, 0.05, C["wood_mid"])

    def roof_z(self, y):
        py = self.py
        lin = self.HF + 0.035 + (self.HB - self.HF) * (y + py) / (2 * py)
        y0, y1 = self.awn_y
        return lin + 0.06 * math.sin(math.pi * (y - y0) / (y1 - y0))

    def awning(self):
        W = self.W
        self.awn_y = (-self.D / 2 - 0.32, self.D / 2 + 0.07)
        y0, y1 = self.awn_y
        hw = W / 2 + 0.14
        nstripe = 13

        def fn(u, v):
            x = -hw + 2 * hw * u
            y = y0 + (y1 - y0) * v
            # cloth sags a touch between the side beams
            z = self.roof_z(y) - 0.025 * math.sin(math.pi * u) * math.sin(math.pi * v)
            return (x, y, z + 0.03)
        sw = 2 * hw / nstripe
        c1, c2 = self.c1, self.c2

        def col(c, n):
            k = int((c.x + hw) / sw + 1e-4)
            return c1 if k % 2 == 0 else c2
        self.mb.add(slab(fn, nstripe, 6, 0.022), col, "cloth_awning")
        # rolled front edge (tube) for a soft finished edge
        zf = self.roof_z(y0) + 0.03 - 0.011
        self.mb.add(tube([(-hw, y0, zf), (hw, y0, zf)], 0.016, 8), c1, "cloth_awning")
        self.front_edge = (y0, zf - 0.016)

    def valance(self):
        y0, ztop = self.front_edge
        y = y0 + 0.025
        hw = self.W / 2 - 0.16
        n, gap, h = 5, 0.014, 0.30
        pw = (2 * hw - (n - 1) * gap) / n
        mb = MB()
        for i in range(n):
            x0 = -hw + i * (pw + gap)

            def fn(u, v, x0=x0):
                return (x0 + pw * u, y + 0.004 * math.sin(math.pi * u), ztop - h + h * v)
            band = self.c2

            def col(c, nn, band=band):
                return band if c.z > ztop - 0.25 * h else self.c1
            mb.add(slab(fn, 2, 4, 0.006), col, "cloth_noren")
        # a stitched rod sleeve along the top
        mb.add(tube([(-hw - 0.02, y + 0.002, ztop + 0.005), (hw + 0.02, y + 0.002, ztop + 0.005)], 0.011, 6),
               C["wood_mid"], "wood_frame")
        ob = make_obj(f"wind_{self.key}_valance", mb, origin=(0, y, ztop), parent=self.root,
                      props={"role": "wind", "pin": "top"})
        self.valance_ob = ob

    def corner_lanterns(self):
        y0, ztop = self.front_edge
        for i, sx in enumerate((-1, 1)):
            x = sx * (self.W / 2 - 0.06)
            red = self.key not in ("lantern",)
            lantern_obj(f"lantern_{self.key}_{i}", self.root, (x, y0 + 0.05, ztop - 0.005), h=0.30, r=0.105,
                        red=red, cord=0.07)

    def back_canopy(self, col):
        py = self.py + 0.045
        hw = self.W / 2 - 0.02
        z0, z1 = 0.62, self.HB - 0.1

        def fn(u, v):
            return (-hw + 2 * hw * u, py + 0.012 * math.sin(math.pi * u * 4) ** 2, z0 + (z1 - z0) * v)
        lite = mix(col, C["white"], 0.15)

        def cc(c, n):
            return lite if (c.z > z1 - 0.18) else col
        self.mb.add(slab(fn, 8, 3, 0.01), cc, "cloth_canopy")
        # short side curtains (top only) for a cosy booth silhouette
        for sx in (-1, 1):
            x = sx * (self.px + 0.045)

            def fs(u, v, x=x, sx=sx):
                yy = -self.py + 2 * self.py * (u if sx > 0 else 1 - u)
                zt = self.roof_z(yy) - 0.02
                return (x, yy, zt - 0.32 + 0.32 * v)
            self.mb.add(slab(fs, 4, 1, 0.008), self.c1, "cloth_canopy")

    def counter(self, skirt):
        mb = self.mb
        W, cd, ch = self.W, self.cd, self.ch
        f = self.front
        yc = f + cd / 2
        bx(mb, W - 0.2, cd, ch - 0.045, 0, yc, 0, C["wood_mid"], bevel=0.01)
        bx(mb, W - 0.12, cd + 0.08, 0.045, 0, yc - 0.0, ch - 0.045, C["wood_pale"], bevel=0.012)
        # cloth skirt across the front
        hw = W / 2 - 0.14
        z0, z1 = 0.06, ch - 0.07

        def fn(u, v):
            return (-hw + 2 * hw * u, f - 0.012 - 0.006 * math.sin(math.pi * u * 6) ** 2, z0 + (z1 - z0) * v)
        c1, c2 = skirt, self.c2

        def col(c, n):
            return c2 if (z1 - 0.13 < c.z < z1 - 0.05) else c1
        mb.add(slab(fn, 12, 5, 0.006), col, "cloth_canopy")
        self.counter_top = ch

    # anchors
    def anchors(self, keeper=(0, 0.2), cam=None, target=None, use_y=None):
        k = self.key
        empty(f"keeper__{k}", (keeper[0], keeper[1], 0), self.root, size=0.3, kind="SINGLE_ARROW",
              props={"anchor": "keeper", "stall": self.name})
        uy = self.top_front - 1.1 if use_y is None else use_y
        empty(f"use__{k}", (0, uy, 0), self.root, rot=R("Z", 180).to_quaternion(), size=0.3, kind="SINGLE_ARROW",
              props={"anchor": "use", "stall": self.name})
        if cam is not None:
            d = Vector(target) - Vector(cam)
            # glTF local -Z (= Blender local +Y after the Y-up conversion) points at the target
            q = d.to_track_quat("Y", "Z")
            empty(f"cam__{k}", cam, self.root, rot=q, size=0.2, kind="ARROWS",
                  props={"anchor": "cam", "stall": self.name, "fov": 50})
            empty(f"cam_target__{k}", target, self.root, size=0.1, kind="SPHERE",
                  props={"anchor": "cam_target", "stall": self.name})

    def fx(self, name, loc):
        empty(f"{name}__{self.key}", loc, self.root, size=0.12, kind="SPHERE",
              props={"anchor": name, "stall": self.name})

    def finish(self):
        make_obj(f"{self.name}_body", self.mb, parent=self.root)


# ----------------------------------------------------------------------------- stalls


def stall_goldfish():
    s = Stall("goldfish", C["red"], C["white"], counter=False)
    mb = s.mb
    # tub -----------------------------------------------------------------------
    tw, td, th, wall = 1.6, 0.8, 0.45, 0.045
    cy = -0.55
    tub_out, tub_in = C["tub"], C["tub_in"]
    bx(mb, tw, wall, th, 0, cy - td / 2 + wall / 2, 0, tub_out, "plastic_tub", 0.01)
    bx(mb, tw, wall, th, 0, cy + td / 2 - wall / 2, 0, tub_out, "plastic_tub", 0.01)
    bx(mb, wall, td - 2 * wall, th, -tw / 2 + wall / 2, cy, 0, tub_out, "plastic_tub", 0.01)
    bx(mb, wall, td - 2 * wall, th, tw / 2 - wall / 2, cy, 0, tub_out, "plastic_tub", 0.01)
    # inner wall faces (lighter so the water reads as shallow) + floor
    for sgn in (-1, 1):
        bx(mb, tw - 2 * wall, 0.004, th - 0.07, 0, cy + sgn * (td / 2 - wall - 0.002), 0.06, tub_in, "plastic_tub", 0)
        bx(mb, 0.004, td - 2 * wall, th - 0.07, sgn * (tw / 2 - wall - 0.002), cy, 0.06, tub_in, "plastic_tub", 0)
    bx(mb, tw - 2 * wall, td - 2 * wall, 0.06, 0, cy, 0, hexc("#9AD6F2"), "plastic_tub", 0)
    # pebbles on the floor
    for i in range(14):
        px = rng.uniform(-0.68, 0.68)
        pyy = cy + rng.uniform(-0.28, 0.28)
        pr = rng.uniform(0.018, 0.03)
        mb.add(sphere(pr, 6, 3, rz=pr * 0.5), rng.choice([C["stone"], C["white"], hexc("#C9B8A0")]),
               "stone_step", T(px, pyy, 0.06))
    # rounded rim
    hx, hy = tw / 2 - 0.02, td / 2 - 0.02
    pts = []
    for cx_, cy_, a0 in ((hx, -hy, -90), (hx, hy, 0), (-hx, hy, 90), (-hx, -hy, 180)):
        for k in range(3):
            a = math.radians(a0 + 45 * k)
            pts.append((cx_ - 0.03 * math.cos(math.radians(a0 + 45)) + 0.03 * math.cos(a) * 0,
                        cy + cy_, th))
    rim = [(hx, cy - hy, th), (hx, cy + hy, th), (-hx, cy + hy, th), (-hx, cy - hy, th)]
    mb.add(tube(rim, 0.026, 6, closed=True, caps=False), hexc("#8ACDF2"), "plastic_tub")
    # water surface (the game animates it and spawns fish)
    wz = th - 0.07
    wmb = MB()
    iw, idp = tw - 2 * wall - 0.01, td - 2 * wall - 0.01
    wmb.add(surf(lambda u, v: (-iw / 2 + iw * u, cy - idp / 2 + idp * v, wz), 16, 8), kit.WHITE, "water_tub",
            uvmap=True)
    make_obj("water_tub", wmb, origin=(0, cy, wz), parent=s.root, props={"role": "water"})
    # back table ------------------------------------------------------------------
    tz = 0.72
    bx(mb, 2.0, 0.42, 0.04, 0, 0.5, tz - 0.04, C["wood_pale"], bevel=0.01)
    for sx in (-0.93, 0.93):
        for sy in (0.33, 0.67):
            bx(mb, 0.045, 0.045, tz - 0.04, sx, sy, 0, C["wood_mid"])
    beam(mb, (-0.93, 0.5, 0.15), (0.93, 0.5, 0.15), 0.03, 0.04, C["wood_mid"])
    # bowl stacks
    bcols = [C["white"], hexc("#FBD3DF"), hexc("#CDE9F7"), hexc("#FFF1B8")]
    for j, x in enumerate((-0.75, -0.6, 0.62)):
        for k in range(5):
            mb.add(bowl_geo(0.06, 0.042), bcols[(j + k) % 4], "plastic_misc", T(x, 0.45 + 0.03 * (j % 2), tz + 0.011 * k))
    # poi tray with fanned scoopers
    bx(mb, 0.36, 0.22, 0.03, -0.2, 0.47, tz, C["wood_dark"], bevel=0.006)
    for k in range(9):
        poi(mb, -0.33 + 0.032 * k, 0.47, tz + 0.03 + 0.004 * (k % 3), rz=8 * (k % 3) - 8)
    # bucket and net
    mb.add(lathe([(0, 0), (0.1, 0), (0.12, 0.2), (0.115, 0.2), (0.095, 0.01), (0, 0.01)], 14), C["steel"],
           "metal_tin", T(0.25, 0.5, tz))
    mb.add(torus(0.12, 0.006, 14, 3), C["iron"], "metal_tin", T(0.25, 0.5, tz + 0.2))
    # water bags with goldfish hanging from the left side rail
    stick(mb, (-s.px, -s.py, 1.62), (-s.px, s.py, 1.62), 0.004, C["white"], "plastic_misc", 4)
    for k in range(3):
        bag(mb, -s.px, -0.4 + 0.2 * k, 1.46)
    # stool for the keeper and a spare poi box by the tub
    stool(mb, 0.95, 0.1)
    bx(mb, 0.24, 0.16, 0.08, 0.98, -0.95 + 0.0, 0, C["wood_mid"], bevel=0.006)
    for k in range(4):
        poi(mb, 0.92 + 0.035 * k, -0.95, 0.08 + 0.004 * k, rz=90)
    cooler(mb, -0.9, 0.2, rz=90, col=C["red"])
    s.anchors(keeper=(0.0, 0.05), use_y=cy - td / 2 - 0.55,
              cam=(0, cy - 1.4 / math.tan(math.radians(55)), wz + 1.4), target=(0, cy, wz))
    s.finish()
    return s


def poi(mb, x, y, z, rz=0.0):
    m = M(x, y, z, rz)
    mb.add(torus(0.042, 0.005, 10, 3), C["red"], "plastic_misc", m)
    mb.add(cyl(0.039, 0.002, 10, caps=True, z0=-0.001), C["white"], "paper_poi", m)
    mb.add(box(0.1, 0.014, 0.006, center=(0.092, 0, 0)), C["red"], "plastic_misc", m)


def bag(mb, x, y, z):
    """Small water bag with a goldfish, hanging from a string at (x, y, z) top."""
    prof = [(0.0, -0.11), (0.03, -0.105), (0.05, -0.08), (0.052, -0.05), (0.035, -0.02), (0.012, 0.0), (0.0, 0.003)]
    fish = hexc("#FF7A2A")
    clear = hexc("#CFEFF8")

    def col(c, n):
        return fish if (z - 0.085 < c.z < z - 0.05 and n.y < -0.2) else clear
    mb.add(lathe(prof, 8), col, "plastic_glass", T(x, y, z))
    mb.add(box(0.004, 0.004, 0.16, center=(0, 0, 0.08)), C["red"], "plastic_misc", T(x, y, z))


def stall_candyapple():
    s = Stall("candyapple", C["pink"], C["white"], cd=0.55)
    mb = s.mb
    top = s.counter_top
    # stepped display rack (white with pink trim)
    ys = (-0.735, -0.585, -0.435)
    rack_w = 1.34
    for i, y in enumerate(ys):
        h = 0.06 + 0.1 * i
        bx(mb, rack_w, 0.15, h, 0, y, top, C["white"], bevel=0.008)
        bx(mb, rack_w + 0.01, 0.012, 0.02, 0, y - 0.075, top + h - 0.02, C["pink"], bevel=0.003)
    apples = []
    xs = [[-0.55, -0.33, -0.11, 0.11, 0.33, 0.55], [-0.44, -0.22, 0.0, 0.22, 0.44], [-0.44, -0.22, 0.0, 0.22, 0.44]]
    for i, y in enumerate(ys):
        zt = top + 0.06 + 0.1 * i
        for x in xs[i]:
            apples.append((x, y, zt, 0.046, "red"))
    # side tray of small green / pink ones
    bx(mb, 0.3, 0.22, 0.025, 0.93, -0.6, top, C["wood_dark"], bevel=0.005)
    for k, (dx, dy) in enumerate(((-0.07, -0.05), (0.07, -0.05), (-0.07, 0.06), (0.07, 0.06))):
        apples.append((0.93 + dx, -0.6 + dy, top + 0.025, 0.033, "green" if k % 2 == 0 else "pink"))
    for i, (x, y, z, r, kind) in enumerate(apples):
        candy_apple(f"apple_{i:02d}", s.root, x, y, z, r, kind)
    # syrup pot on a burner
    px, py = -0.98, -0.55
    bx(mb, 0.24, 0.24, 0.09, px, py, top, C["iron"], "metal_iron", 0.01)
    mb.add(lathe([(0, 0), (0.1, 0), (0.105, 0.13), (0.112, 0.135), (0.112, 0.14), (0.098, 0.14), (0.094, 0.01),
                  (0, 0.01)], 14), C["steel"], "metal_tin", T(px, py, top + 0.09))
    mb.add(cyl(0.095, 0.004, 14, z0=0.11), hexc("#C4121F"), "plastic_candy", T(px, py, top + 0.09))
    stick(mb, (px + 0.03, py, top + 0.2), (px - 0.02, py + 0.02, top + 0.12), 0.006, C["wood_pale"])
    for sx in (-1, 1):
        mb.add(torus(0.02, 0.005, 8, 3), C["iron"], "metal_tin", T(px + sx * 0.112, py, top + 0.2) @ R("X", 90))
    # spare apples in a crate behind the counter
    crate_geo(mb, 0.8, 0.45, 0.0, s=(0.45, 0.32, 0.26))
    for k in range(6):
        mb.add(sphere(0.045, 8, 5), hexc("#B91D24"), "plastic_candy",
               T(0.66 + 0.1 * (k % 3), 0.38 + 0.12 * (k // 3), 0.25))
    stool(mb, -0.6, 0.35)
    s.anchors(keeper=(0.0, 0.25), cam=(0.25, -1.55, 1.42), target=(0.0, -0.58, top + 0.12))
    s.finish()
    return s


def candy_apple(name, parent, x, y, z, r, kind):
    cols = {"red": (hexc("#D41429"), hexc("#FF9C9C")), "green": (hexc("#7CC242"), hexc("#E2F7B5")),
            "pink": (hexc("#F27CA8"), hexc("#FFE0EC"))}
    base, hi = cols[kind]
    mb = MB()
    prof = [(0.0, -0.78 * r), (0.35 * r, -0.86 * r)]
    for k in range(1, 8):
        t = k / 8
        a = math.pi * t
        prof.append((r * math.sin(a) * (1.0 + 0.06 * math.sin(a)), -r * math.cos(a) * 0.92))
    prof += [(0.3 * r, 0.9 * r), (0.0, 0.74 * r)]
    mb.add(lathe(prof, 12), gloss(base, hi, k=0.88), "plastic_candy", T(0, 0, 0))
    # candy drip collar at the bottom
    mb.add(cyl(r * 0.62, 0.006, 10, z0=-0.86 * r), shade(base, 0.85), "plastic_candy")
    mb.add(box(0.007, 0.007, 0.15, center=(0, 0, 0.75 * r + 0.06)), C["wood_pale"], "wood_frame")
    ob = make_obj(name, mb, parent=parent, props={"role": "pickup", "kind": kind})
    ob.location = (x, y, z + 0.86 * r)
    return ob


def crate_geo(mb, x, y, z, s=(0.5, 0.36, 0.3), rz=0.0, col=None):
    col = col or C["wood"]
    sx, sy, sz = s
    m = M(x, y, z, rz)
    dark = shade(col, 0.8)
    for zz in (0.02, sz * 0.55):
        h = sz * 0.36
        for sgn in (-1, 1):
            mb.add(box(sx, 0.018, h, bevel=0.004, center=(0, sgn * (sy / 2 - 0.009), zz + h / 2)), col, "wood_frame", m)
            mb.add(box(0.018, sy - 0.036, h, bevel=0.004, center=(sgn * (sx / 2 - 0.009), 0, zz + h / 2)), col,
                   "wood_frame", m)
    for cx in (-1, 1):
        for cy in (-1, 1):
            mb.add(box(0.04, 0.04, sz, bevel=0.005, center=(cx * (sx / 2 - 0.02), cy * (sy / 2 - 0.02), sz / 2)),
                   dark, "wood_frame", m)
    mb.add(box(sx - 0.02, sy - 0.02, 0.015, center=(0, 0, 0.0075)), dark, "wood_frame", m)


def stall_shavedice():
    s = Stall("shavedice", C["blue"], C["white"], cd=0.45)
    mb = s.mb
    top = s.counter_top
    mx, my = -0.5, -0.6
    red, silver = hexc("#C2352F"), C["steel"]
    # machine: base, column, arm, housing, ice block, top crank wheel
    bx(mb, 0.28, 0.26, 0.04, mx, my + 0.02, top, red, "metal_iron", 0.01)
    bx(mb, 0.07, 0.06, 0.6, mx, my + 0.12, top + 0.04, red, "metal_iron", 0.012)
    bx(mb, 0.07, 0.2, 0.05, mx, my + 0.05, top + 0.6, red, "metal_iron", 0.012)
    mb.add(lathe([(0.085, 0), (0.09, 0.004), (0.09, 0.11), (0.08, 0.12), (0.06, 0.12), (0.06, 0.01), (0.03, 0.0)], 14),
           silver, "metal_tin", T(mx, my, top + 0.3))
    bx(mb, 0.11, 0.11, 0.12, mx, my, top + 0.42, hexc("#D8F3FB"), "plastic_ice", 0.01)
    stick(mb, (mx, my, top + 0.54), (mx, my, top + 0.66), 0.012, silver, "metal_tin", 8)
    mb.add(torus(0.08, 0.008, 16, 4), silver, "metal_tin", T(mx, my, top + 0.69))
    for k in range(3):
        a = 2 * math.pi * k / 3
        stick(mb, (mx, my, top + 0.69), (mx + 0.08 * math.cos(a), my + 0.08 * math.sin(a), top + 0.69), 0.005, silver,
              "metal_tin", 4)
    stick(mb, (mx + 0.08, my, top + 0.69), (mx + 0.08, my, top + 0.75), 0.008, C["black"], "plastic_misc", 6)
    # cup with shaved ice under the blade
    cup_geo(mb, mx, my, top + 0.04, h=0.08, ice=hexc("#E8323C"))
    # syrup bottles
    for k, colr in enumerate(("#E3343A", "#38B54A", "#2F80E2", "#F2C631")):
        bottle(mb, -0.05 + 0.14 * k, -0.62, top, hexc(colr))
    # stacked cups
    for k, x in enumerate((0.62, 0.74)):
        for j in range(9 - 2 * k):
            cup_geo(mb, x, -0.6, top + 0.016 * j, h=0.08, ice=None)
    # flag bracket from the right front post + the flag
    fx0, fx1 = 0.78, s.px - 0.04
    zr = 1.74
    yb = -s.py - 0.06
    stick(mb, (s.px, yb, zr), (fx0 - 0.03, yb, zr), 0.008, C["wood_dark"], "wood_frame", 6)
    stick(mb, (s.px - 0.01, -s.py - 0.04, zr), (s.px - 0.01, yb, zr), 0.01, C["wood_dark"], "wood_frame", 6)
    flag_ice(s, fx0, fx1, yb - 0.004, zr - 0.015)
    # ice blocks in a cooler + stool
    cooler(mb, 0.85, 0.35, col=C["white"])
    stool(mb, -0.7, 0.35)
    s.fx("fx_mist", (mx, my, top + 0.19))
    s.anchors(keeper=(-0.2, 0.2), cam=(-0.05, -1.55, 1.45), target=(-0.15, -0.6, top + 0.2))
    s.finish()
    return s


def cup_geo(mb, x, y, z, h=0.08, ice=None):
    prof = [(0.0, 0.0), (0.036, 0.0), (0.0425, 0.45 * h), (0.0455, 0.7 * h), (0.05, h), (0.047, h), (0.034, 0.006),
            (0.0, 0.006)]

    def col(c, n):
        t = (c.z - z) / h
        return C["blue"] if 0.45 < t < 0.7 and abs(n.z) < 0.5 else C["white"]
    mb.add(lathe(prof, 10), col, "plastic_cup", T(x, y, z))
    if ice is not None:
        def ic(c, n):
            return ice if c.z > z + h + 0.035 else C["white"]
        mb.add(sphere(0.052, 10, 5, rz=0.06), ic, "plastic_ice", T(x, y, z + h - 0.01))


def bottle(mb, x, y, z, col):
    prof = [(0, 0), (0.034, 0), (0.036, 0.004), (0.036, 0.05), (0.036, 0.11), (0.036, 0.15), (0.026, 0.18), (0.013, 0.195), (0.013, 0.215),
            (0.016, 0.218), (0.016, 0.235), (0.006, 0.25), (0, 0.25)]

    def cc(c, n):
        t = c.z - z
        if t > 0.212:
            return C["white"]
        if 0.05 < t < 0.11 and abs(n.z) < 0.5:
            return C["white"]
        return col
    mb.add(lathe(prof, 10), cc, "plastic_bottle", T(x, y, z))


def flag_ice(s, x0, x1, y, ztop):
    """Kakigori-style flag: white cloth, blue waves at the bottom, a red ice-crystal symbol (no text)."""
    w, h = x1 - x0, 0.5
    cv = kit.Canvas(256, 320, "#f8f6ef")
    cv.rect(0, 0.94, 1, 1, "#d8262d")
    # waves (three blue layers, scalloped)
    cv.wave_band(0.24, 0.035, 2.5, 0.0, "#2c62c4")
    cv.wave_band(0.17, 0.03, 3.0, 0.3, "#5a8fe0")
    cv.wave_band(0.09, 0.025, 3.5, 0.6, "#2c62c4")
    for k in range(6):
        cv.ring(0.08 + 0.17 * k, 0.22, 0.05, 0.04, 0.012, "#f8f6ef", 0.2, 2.9)
    # red ice crystal: six arms with side branches, ring in the middle
    cx, cy = 0.5, 0.6
    for k in range(6):
        a = math.pi / 2 + k * math.pi / 3
        ex, ey = cx + 0.26 * math.cos(a) * 0.8, cy + 0.26 * math.sin(a)
        cv.line((cx, cy), (ex, ey), 0.045, "#d8262d")
        for t, L in ((0.55, 0.09), (0.8, 0.06)):
            bxp, byp = cx + (ex - cx) * t, cy + (ey - cy) * t
            for da in (-0.8, 0.8):
                cv.line((bxp, byp), (bxp + L * math.cos(a + da) * 0.8, byp + L * math.sin(a + da)), 0.032, "#d8262d")
    cv.ellipse(cx, cy, 0.08, 0.065, "#d8262d")
    cv.ellipse(cx, cy, 0.04, 0.032, "#f8f6ef")
    img = cv.to_image("tex_flag_ice", os.path.join(TEX_DIR, "flag_ice.png"))
    material("fabric_flag_ice", image=img)
    mb = MB()
    mb.add(slab(lambda u, v: (x0 + w * u, y - 0.004 * math.sin(math.pi * u), ztop - h + h * v), 4, 6, 0.004),
           kit.WHITE, "fabric_flag_ice", uvmap=True)
    make_obj("wind_flag_ice", mb, origin=((x0 + x1) / 2, y, ztop), parent=s.root, props={"role": "wind", "pin": "top"})


def stall_ringtoss():
    s = Stall("ringtoss", C["green"], C["white"], cd=0.28, ch=0.5)
    mb = s.mb
    top = s.counter_top
    # low platform with 9 pegs ------------------------------------------------------
    pz = 0.32
    bx(mb, 1.05, 0.8, pz - 0.02, 0, 0.05, 0, C["wood_mid"], bevel=0.012)
    bx(mb, 1.0, 0.75, 0.02, 0, 0.05, pz - 0.02, hexc("#C8332D"), "cloth_canopy", 0.004)
    band = [hexc("#E04040"), hexc("#F2C14E"), hexc("#3C7BCB")]
    k = 0
    for j, yy in enumerate((-0.2, 0.05, 0.3)):
        for xx in (-0.3, 0.0, 0.3):
            pmb = MB()
            prof = [(0, 0), (0.035, 0), (0.035, 0.012), (0.018, 0.02), (0.018, 0.14), (0.0185, 0.175), (0.018, 0.19),
                    (0.014, 0.205), (0, 0.212)]

            def pc(c, n, j=j):
                return band[j] if 0.14 < c.z < 0.175 else C["wood_pale"]
            pmb.add(lathe(prof, 8), pc, "wood_frame")
            ob = make_obj(f"peg_{k}", pmb, parent=s.root, props={"role": "peg", "row": j})
            ob.location = (xx, yy, pz)
            k += 1
    # back shelf with prizes ------------------------------------------------------------
    sy0, sy1 = 0.5, 0.76
    tiers = (0.72, 1.07, 1.42)
    for z in tiers:
        bx(mb, 2.24, sy1 - sy0, 0.03, 0, (sy0 + sy1) / 2, z - 0.03, C["wood_pale"], bevel=0.006)
        bx(mb, 2.24, 0.012, 0.04, 0, sy0 - 0.006, z - 0.045, hexc("#C8332D"), "wood_frame", 0.003)
    for x in (-1.12, 0.0, 1.12):
        bx(mb, 0.04, sy1 - sy0, tiers[-1] + 0.02, x, (sy0 + sy1) / 2, 0, C["wood_mid"])
    t1, t2, t3 = tiers
    plush(mb, -0.85, 0.62, t1, hexc("#F6B3C8"), "bear")
    plush(mb, -0.42, 0.62, t1, hexc("#FFD95A"), "chick")
    plush(mb, 0.05, 0.62, t1, hexc("#8CC8F0"), "whale")
    plush(mb, 0.5, 0.62, t1, hexc("#F5F1EA"), "bunny")
    toy_ball(mb, 0.9, 0.62, t1, 0.06)
    toy_drum(mb, -0.85, 0.62, t2)
    spin_top(mb, -0.45, 0.62, t2)
    glass_bottle(mb, -0.12, 0.62, t2)
    robot(mb, 0.25, 0.62, t2)
    toy_car(mb, 0.62, 0.62, t2)
    toy_ball(mb, 0.92, 0.62, t2, 0.045, hexc("#56B85C"))
    lucky_cat(mb, 0.0, 0.62, t3)
    plush(mb, -0.6, 0.62, t3, hexc("#7DC67A"), "frog")
    plush(mb, 0.6, 0.62, t3, hexc("#B98A5E"), "bear")
    toy_drum(mb, -0.95, 0.62, t3, 0.8)
    spin_top(mb, 0.95, 0.62, t3)
    # rope rings on the counter ------------------------------------------------------------
    rx, ry = -0.85, -0.68
    stick(mb, (rx, ry, top), (rx, ry, top + 0.17), 0.012, C["wood_dark"], "wood_frame", 6)
    bx(mb, 0.18, 0.18, 0.02, rx, ry, top, C["wood_dark"], bevel=0.005)
    for k in range(7):
        mb.add(ring_geo(), ring_col, "cloth_canopy", T(rx + 0.004 * ((k % 3) - 1), ry, top + 0.035 + 0.022 * k) @ R("Z", 40 * k))
    rmb = MB()
    rmb.add(ring_geo(), ring_col, "cloth_canopy")
    ob = make_obj("ring_proto", rmb, parent=s.root, props={"role": "ring"})
    ob.location = (-0.55, -0.66, top + 0.012)
    stool(mb, 0.95, 0.3)
    s.anchors(keeper=(0.85, 0.2), cam=(0, -1.75, 1.45), target=(0, 0.05, 0.32))
    s.finish()
    return s


def ring_geo():
    return torus(0.068, 0.012, 16, 5)


def ring_col(c, n):
    a = math.atan2(c.y, c.x)
    return hexc("#D9C08C") if int((a + math.pi) / (2 * math.pi) * 16) % 2 else hexc("#C8332D")


def eyes(mb, x, y, z, sep, r=0.009, col=None):
    col = col or C["black"]
    for sx in (-1, 1):
        mb.add(sphere(r, 6, 4, rz=r * 1.2), col, "plastic_misc", T(x + sx * sep, y, z))


def plush(mb, x, y, z, col, kind):
    m = T(x, y, z)
    if kind == "whale":
        mb.add(sphere(0.13, 12, 7, rz=0.08), col, "cloth_plush", m @ T(0, 0, 0.075) @ S(1, 0.75, 1))
        mb.add(prism([(-0.02, 0), (0.02, 0), (0.07, 0.06), (0.0, 0.03), (-0.07, 0.06)], -0.01, 0.01), col,
               "cloth_plush", m @ T(0.13, 0.0, 0.07) @ R("Y", 90) @ R("Z", 90))
        eyes(mb, x - 0.06, y - 0.075, z + 0.09, 0.0, 0.01)
        eyes(mb, x - 0.04, y - 0.08, z + 0.09, 0.0, 0.0)
        mb.add(sphere(0.07, 8, 4, rz=0.03), C["white"], "cloth_plush", m @ T(-0.02, -0.02, 0.03))
        return
    body_h = 0.17
    mb.add(sphere(0.1, 12, 7, rz=0.09), col, "cloth_plush", m @ T(0, 0, 0.09))
    mb.add(sphere(0.085, 12, 7, rz=0.075), col, "cloth_plush", m @ T(0, -0.01, 0.235))
    hz = z + 0.235
    if kind == "bear":
        for sx in (-1, 1):
            mb.add(sphere(0.03, 8, 4), col, "cloth_plush", T(x + sx * 0.06, y, hz + 0.065))
        mb.add(sphere(0.032, 8, 4, rz=0.024), C["cream"], "cloth_plush", T(x, y - 0.075, hz - 0.02))
        mb.add(sphere(0.01, 6, 3), C["black"], "plastic_misc", T(x, y - 0.1, hz - 0.01))
    elif kind == "bunny":
        for sx in (-1, 1):
            mb.add(sphere(0.024, 8, 4, rz=0.075), col, "cloth_plush", T(x + sx * 0.035, y, hz + 0.12) @ R("Y", sx * 12))
            mb.add(sphere(0.012, 6, 3, rz=0.05), C["pink"], "cloth_plush", T(x + sx * 0.035, y - 0.017, hz + 0.12) @ R("Y", sx * 12))
    elif kind == "chick":
        mb.add(prism([(-0.02, 0), (0.02, 0), (0, 0.03)], -0.012, 0.012), C["orange"], "cloth_plush",
               T(x, y - 0.085, hz - 0.012) @ R("X", 90) @ R("X", 0))
        mb.add(sphere(0.02, 6, 3, rz=0.035), col, "cloth_plush", T(x, y, hz + 0.085))
    elif kind == "frog":
        for sx in (-1, 1):
            mb.add(sphere(0.03, 8, 4), col, "cloth_plush", T(x + sx * 0.045, y - 0.02, hz + 0.06))
            mb.add(sphere(0.016, 6, 3), C["white"], "plastic_misc", T(x + sx * 0.045, y - 0.045, hz + 0.065))
            mb.add(sphere(0.008, 6, 3), C["black"], "plastic_misc", T(x + sx * 0.045, y - 0.058, hz + 0.066))
        mb.add(torus(0.03, 0.004, 10, 3), hexc("#C8332D"), "plastic_misc", T(x, y - 0.077, hz - 0.03) @ R("X", 90))
        return
    eyes(mb, x, y - 0.078, hz + 0.012, 0.032, 0.01)
    for sx in (-1, 1):
        mb.add(sphere(0.014, 6, 3, rz=0.008), C["pink"], "cloth_plush", T(x + sx * 0.05, y - 0.068, hz - 0.012))


def toy_ball(mb, x, y, z, r, col=None):
    col = col or hexc("#E8473F")

    def cc(c, n):
        return C["white"] if abs(n.z) < 0.3 else col
    mb.add(sphere(r, 10, 6), cc, "plastic_misc", T(x, y, z + r))


def toy_drum(mb, x, y, z, s=1.0):
    m = T(x, y, z) @ S(s)
    mb.add(cyl(0.006, 0.12, 6), C["wood_dark"], "wood_frame", m)
    dm = m @ T(0, 0, 0.18) @ R("X", 90)

    def cc(c, n):
        return C["cream"] if abs(n.dot((dm.to_3x3() @ Vector((0, 0, 1))).normalized())) > 0.9 else hexc("#C8332D")
    mb.add(cyl(0.055, 0.045, 12, z0=-0.0225, bevel=0.004), cc, "wood_frame", dm)
    for sx in (-1, 1):
        mb.add(box(0.06, 0.003, 0.003, center=(sx * 0.085, 0, 0.18)), C["black"], "plastic_misc", m)
        mb.add(sphere(0.011, 6, 3), C["white"], "plastic_misc", m @ T(sx * 0.115, 0, 0.18))
    mb.add(box(0.006, 0.006, 0.07, center=(0, 0, 0.12 + 0.035)), C["wood_dark"], "wood_frame", m)


def spin_top(mb, x, y, z):
    def cc(c, n):
        k = int((c.z - z) / 0.012)
        return [hexc("#E04040"), hexc("#F2C14E"), hexc("#3C7BCB"), hexc("#4AA25A")][k % 4]
    mb.add(lathe([(0, 0), (0.02, 0.02), (0.05, 0.045), (0.052, 0.055), (0.012, 0.065), (0.008, 0.095), (0, 0.095)], 12),
           cc, "wood_frame", T(x, y, z))


def glass_bottle(mb, x, y, z):
    prof = [(0, 0), (0.034, 0), (0.036, 0.01), (0.036, 0.11), (0.022, 0.13), (0.026, 0.145), (0.016, 0.16),
            (0.014, 0.2), (0.016, 0.205), (0, 0.205)]

    def cc(c, n):
        return C["blue"] if c.z - z > 0.198 else hexc("#A9E3EE")
    mb.add(lathe(prof, 10), cc, "plastic_glass", T(x, y, z))
    mb.add(sphere(0.012, 6, 4), hexc("#E6F6FA"), "plastic_glass", T(x, y, z + 0.14))


def robot(mb, x, y, z):
    body = hexc("#8FA6BF")
    m = T(x, y, z)
    mb.add(box(0.09, 0.06, 0.08, bevel=0.008, center=(0, 0, 0.065)), body, "plastic_misc", m)
    mb.add(box(0.08, 0.06, 0.06, bevel=0.01, center=(0, 0, 0.14)), body, "plastic_misc", m)
    for sx in (-1, 1):
        mb.add(box(0.03, 0.04, 0.025, bevel=0.005, center=(sx * 0.025, 0, 0.0125)), C["red"], "plastic_misc", m)
        mb.add(box(0.02, 0.02, 0.06, bevel=0.005, center=(sx * 0.058, 0, 0.07)), C["red"], "plastic_misc", m)
        mb.add(sphere(0.008, 6, 3), C["yellow"], "plastic_misc", m @ T(sx * 0.018, -0.031, 0.145))
    stick(mb, (x, y, z + 0.17), (x, y, z + 0.2), 0.003, C["black"], "plastic_misc", 4)
    mb.add(sphere(0.01, 6, 3), C["red"], "plastic_misc", T(x, y, z + 0.205))


def toy_car(mb, x, y, z):
    m = T(x, y, z) @ R("Z", 20)
    mb.add(box(0.15, 0.07, 0.04, bevel=0.012, center=(0, 0, 0.03)), hexc("#F2C14E"), "plastic_misc", m)
    mb.add(box(0.08, 0.062, 0.035, bevel=0.012, center=(-0.01, 0, 0.065)), hexc("#9ED8F0"), "plastic_misc", m)
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.add(cyl(0.017, 0.012, 8, z0=-0.006), C["black"], "plastic_misc",
                   m @ T(sx * 0.045, sy * 0.036, 0.017) @ R("X", 90))


def lucky_cat(mb, x, y, z):
    """Original beckoning-cat figurine: round white cat in a blue scarf holding a little fish, on a
    red cushion, one paw raised, eyes closed in a smile."""
    m = T(x, y, z)
    mb.add(box(0.2, 0.17, 0.04, bevel=0.015, center=(0, 0, 0.02)), hexc("#C8332D"), "cloth_plush", m)
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.add(sphere(0.012, 6, 3), C["gold"], "plastic_misc", m @ T(sx * 0.09, sy * 0.075, 0.04))
    white = hexc("#FBF7F0")
    mb.add(sphere(0.075, 12, 7, rz=0.08), white, "plastic_misc", m @ T(0, 0, 0.115))
    mb.add(sphere(0.07, 12, 7, rz=0.06), white, "plastic_misc", m @ T(0, -0.005, 0.235))
    for sx in (-1, 1):
        mb.add(prism([(-0.025, 0), (0.025, 0), (0.0, 0.045)], -0.012, 0.012), white, "plastic_misc",
               m @ T(sx * 0.042, 0, 0.27) @ R("Y", -sx * 22) @ R("X", 90))
        mb.add(prism([(-0.014, 0), (0.014, 0), (0.0, 0.028)], -0.003, 0.003), C["pink"], "plastic_misc",
               m @ T(sx * 0.042, -0.0125, 0.275) @ R("Y", -sx * 22) @ R("X", 90))
        # closed smiling eyes (arcs)
        arc = [(sx * 0.024 + 0.012 * math.cos(a), -0.059, 0.24 + 0.008 * math.sin(a))
               for a in (math.pi * k / 4 for k in range(5))]
        mb.add(tube([(m @ Vector(p))[:] for p in arc], 0.0032, 4), C["black"], "plastic_misc")
        mb.add(sphere(0.011, 6, 3, rz=0.006), C["pink"], "plastic_misc", m @ T(sx * 0.04, -0.055, 0.218))
        mb.add(box(0.03, 0.002, 0.002, center=(sx * 0.06, -0.06, 0.222)), C["black"], "plastic_misc", m)
    mb.add(sphere(0.008, 6, 3), C["pink"], "plastic_misc", m @ T(0, -0.067, 0.225))
    # scarf + bell
    mb.add(torus(0.058, 0.012, 14, 4), hexc("#3C7BCB"), "cloth_plush", m @ T(0, -0.003, 0.18) @ S(1, 1, 0.8))
    mb.add(sphere(0.016, 8, 4), C["gold"], "plastic_misc", m @ T(0, -0.065, 0.165))
    # raised left paw, right paw holds a fish
    mb.add(sphere(0.022, 8, 4, rz=0.04), white, "plastic_misc", m @ T(-0.07, -0.02, 0.27) @ R("Y", 15))
    mb.add(sphere(0.022, 8, 4), white, "plastic_misc", m @ T(0.05, -0.065, 0.1))
    mb.add(sphere(0.022, 8, 4, rz=0.012), C["orange"], "plastic_misc", m @ T(0.03, -0.08, 0.085) @ R("Y", 25) @ S(1.6, 1, 1))
    mb.add(prism([(0, 0), (0.025, 0.015), (0.025, -0.015)], -0.004, 0.004), C["orange"], "plastic_misc",
           m @ T(0.055, -0.085, 0.072) @ R("Y", 25) @ R("X", 90))


def stall_masks():
    s = Stall("masks", C["orange"], C["white"], cd=0.35)
    mb = s.mb
    top = s.counter_top
    # pegboard wall
    by = 0.7
    bx(mb, 2.2, 0.04, 0.95, 0, by, 0.88, hexc("#E9D8B8"), bevel=0.008)
    bx(mb, 2.26, 0.05, 0.05, 0, by, 1.83, C["wood_mid"], bevel=0.008)
    bx(mb, 2.26, 0.05, 0.05, 0, by, 0.84, C["wood_mid"], bevel=0.008)
    for ix in range(21):
        for iz in range(9):
            x, z = -1.0 + ix * 0.1, 0.95 + iz * 0.1
            mb.add(surf(lambda u, v, x=x, z=z: (x - 0.007 + 0.014 * u, by - 0.0205, z - 0.007 + 0.014 * v), 1, 1),
                   hexc("#9E8466"), "wood_frame")
    kinds = ["fox", "cat_white", "cat_black", "goofy", "oni", "tengu", "bird", "rabbit", "dragon", "turtle", "frog", "sun"]
    atlas = mask_atlas(kinds)
    rows = (1.63, 1.36, 1.09)
    cols = (-0.75, -0.25, 0.25, 0.75)
    for i, kd in enumerate(kinds):
        x, z = cols[i % 4], rows[i // 4]
        z -= 0.0 if kd != "rabbit" else 0.025
        ob = build_mask(f"mask_{i:02d}", kd, i, s.root, atlas)
        ob.location = (x, by - 0.032, z)
        ob.rotation_euler = (0, math.radians(rng.uniform(-4, 4)), 0)
        stick(mb, (x, by - 0.02, z + 0.1), (x, by - 0.06, z + 0.105), 0.004, C["black"], "metal_tin", 4)
    # counter: pinwheels in a pot, a mask lying flat, a cash tin
    px, py = 0.85, -0.62
    mb.add(cyl(0.06, 0.1, 10, 0.07, bevel=0.005), C["terracotta"], "wood_frame", T(px, py, top))
    for k, colr in enumerate((C["red"], C["blue"], C["yellow"])):
        pinwheel(mb, px - 0.06 + 0.06 * k, py + 0.01 * k, top + 0.32 + 0.05 * (k % 2), colr, k)
    bx(mb, 0.2, 0.14, 0.07, -0.85, -0.6, top, C["steel"], "metal_tin", 0.008)
    stool(mb, -0.85, 0.3)
    s.anchors(keeper=(-0.95, 0.2), cam=(0, -0.75, 1.4), target=(0, by - 0.05, 1.36))
    s.finish()
    return s


def pinwheel(mb, x, y, z, col, k):
    stick(mb, (x, y, z), (x, y + 0.01, z - 0.32), 0.004, C["wood_pale"], "wood_frame", 4)
    m = T(x, y - 0.012, z) @ R("X", 90) @ R("Z", 25 * k)
    for b in range(4):
        mb.add(ngon_sheet([(0, 0), (0.05, 0.0), (0.0, 0.05)], 0.002), col if b % 2 == 0 else C["white"],
               "plastic_misc", m @ R("Z", 90 * b) @ R("X", 12))
    mb.add(sphere(0.008, 6, 3), C["yellow"], "plastic_misc", T(x, y - 0.016, z))


# ----------------------------------------------------------------------------- masks

MASK_SPECS = {
    # base half-width, half-height, colour, bumps [(angle_deg, height, half-width_rad)], chin point
    "fox": dict(rx=0.08, rz=0.095, bumps=[(62, 0.075, 0.28), (118, 0.075, 0.28), (270, 0.03, 0.5)], base="#FBF8F1"),
    "cat_white": dict(rx=0.088, rz=0.09, bumps=[(55, 0.05, 0.3), (125, 0.05, 0.3)], base="#FBF8F1"),
    "cat_black": dict(rx=0.088, rz=0.09, bumps=[(55, 0.05, 0.3), (125, 0.05, 0.3)], base="#2B2A33"),
    "goofy": dict(rx=0.088, rz=0.105, bumps=[], base="#F6D7B0"),
    "oni": dict(rx=0.092, rz=0.1, bumps=[(270, -0.01, 0.6)], base="#D8352E", square=0.25),
    "tengu": dict(rx=0.082, rz=0.108, bumps=[], base="#C0392B"),
    "bird": dict(rx=0.09, rz=0.095, bumps=[(90, 0.025, 0.25), (72, 0.02, 0.15), (108, 0.02, 0.15)], base="#6FB8E8"),
    "rabbit": dict(rx=0.08, rz=0.085, bumps=[(75, 0.12, 0.17), (105, 0.12, 0.17)], base="#FBF8F1"),
    "dragon": dict(rx=0.095, rz=0.1, bumps=[(90, 0.02, 0.5)], base="#2FA37C", square=0.15),
    "turtle": dict(rx=0.09, rz=0.1, bumps=[], base="#7CC26A"),
    "frog": dict(rx=0.1, rz=0.085, bumps=[(62, 0.04, 0.32), (118, 0.04, 0.32)], base="#5DBB4A"),
    "sun": dict(rx=0.088, rz=0.088, bumps=[], rays=14, base="#F7C531"),
}


def mask_outline(kd, N=40):
    sp = MASK_SPECS[kd]
    pts = []
    for i in range(N):
        a = 2 * math.pi * i / N - math.pi / 2
        x, z = sp["rx"] * math.cos(a), sp["rz"] * math.sin(a)
        sq = sp.get("square", 0)
        if sq:
            k = max(abs(math.cos(a)), abs(math.sin(a)))
            x, z = x / (1 - sq + sq * k * 1.0) * (1 - sq * 0.3), z / (1 - sq + sq * k) * (1 - sq * 0.3)
        rr = 0.0
        ad = math.degrees(a) % 360
        for (ang, hgt, hw) in sp["bumps"]:
            d = math.radians(((ad - ang + 180) % 360) - 180)
            if abs(d) < hw:
                t = 1 - abs(d) / hw
                rr += hgt * (t ** 1.4)
        if sp.get("rays"):
            rr += 0.022 * abs(math.sin(sp["rays"] / 2 * a))
        L = math.hypot(x, z)
        k = (L + rr) / L
        pts.append((x * k, z * k))
    return pts


def mask_mapping(kd):
    pts = mask_outline(kd)
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    span = max(max(xs) - min(xs), max(zs) - min(zs)) * 1.06
    return cx, cz, span


def mask_atlas(kinds):
    cv = kit.Canvas(1024, 768, "#ffffff")
    for i, kd in enumerate(kinds):
        col, row = i % 4, i // 4
        cv.set_region(col / 4, 1 - (row + 1) / 3, (col + 1) / 4, 1 - row / 3)
        cx, cz, span = mask_mapping(kd)

        def P(x, z):
            return (0.5 + (x - cx) / span, 0.5 + (z - cz) / span)

        def Rr(r):
            return r / span
        sp = MASK_SPECS[kd]
        cv.fill(sp["base"])
        paint_mask(cv, kd, P, Rr)
    img = cv.to_image("tex_masks", os.path.join(TEX_DIR, "masks.png"))
    material("plastic_mask", image=img)
    return img


def paint_mask(cv, kd, P, Rr):
    blk, red, wht, pink = "#231c1c", "#d62f2f", "#fbf8f1", "#f49ab0"

    def E(x, z, rx, rz, col, rot=0.0):
        cx, cz = P(x, z)
        cv.ellipse(cx, cz, Rr(rx), Rr(rz), col, rot)

    def Ln(p0, p1, w, col):
        cv.line(P(*p0), P(*p1), Rr(w), col)

    def Arc(x, z, rx, rz, w, col, a0, a1):
        cx, cz = P(x, z)
        cv.ring(cx, cz, Rr(rx), Rr(rz), Rr(w), col, a0, a1)
    if kd == "fox":
        for sx in (-1, 1):
            cv.poly([P(sx * 0.03, 0.09), P(sx * 0.075, 0.155), P(sx * 0.08, 0.08)], red)
            Ln((sx * 0.018, 0.012), (sx * 0.06, 0.03), 0.012, red)
            Ln((sx * 0.022, 0.01), (sx * 0.058, 0.026), 0.005, blk)
            Ln((sx * 0.04, -0.035), (sx * 0.075, -0.03), 0.005, red)
            Ln((sx * 0.04, -0.048), (sx * 0.072, -0.05), 0.005, red)
        E(0, 0.062, 0.008, 0.018, red)
        E(0, 0.045, 0.004, 0.008, "#f2b134")
        E(0, -0.075, 0.012, 0.009, blk)
        Arc(0, -0.085, 0.018, 0.01, 0.004, red, -math.pi + 0.4, -0.4)
    elif kd in ("cat_white", "cat_black"):
        inner = pink
        eye = "#5aa7e0" if kd == "cat_white" else "#f2c531"
        line = blk if kd == "cat_white" else "#f3e7d3"
        for sx in (-1, 1):
            cv.poly([P(sx * 0.035, 0.085), P(sx * 0.07, 0.125), P(sx * 0.075, 0.075)], inner)
            E(sx * 0.038, 0.012, 0.017, 0.02, eye)
            E(sx * 0.038, 0.012, 0.005, 0.016, blk)
            E(sx * 0.033, 0.02, 0.004, 0.004, wht)
            for dz in (-0.03, -0.042):
                Ln((sx * 0.03, dz), (sx * 0.085, dz + sx * 0 + (dz + 0.036) * 0.6), 0.003, line)
        if kd == "cat_white":
            E(-0.05, 0.06, 0.03, 0.022, "#f0a040")
        cv.poly([P(-0.01, -0.02), P(0.01, -0.02), P(0, -0.032)], pink)
        Arc(-0.01, -0.035, 0.01, 0.008, 0.003, line, -math.pi, 0)
        Arc(0.01, -0.035, 0.01, 0.008, 0.003, line, -math.pi, 0)
    elif kd == "goofy":
        for sx in (-1, 1):
            Arc(sx * 0.035, 0.02, 0.018, 0.012, 0.006, blk, 0.2, math.pi - 0.2)
            Arc(sx * 0.035, 0.055, 0.02, 0.008, 0.005, blk, 0.3, math.pi - 0.3)
            E(sx * 0.055, -0.025, 0.02, 0.014, "#f28a8a")
        E(0, -0.05, 0.034, 0.026, "#b8242a")
        E(0, -0.04, 0.028, 0.01, wht)
        E(0, -0.064, 0.016, 0.009, "#ef7d86")
        E(0, -0.005, 0.009, 0.007, "#e6a77a")
    elif kd == "oni":
        for sx in (-1, 1):
            E(sx * 0.037, 0.012, 0.021, 0.019, wht)
            E(sx * 0.034, 0.01, 0.009, 0.01, blk)
            E(sx * 0.031, 0.015, 0.003, 0.003, wht)
            Ln((sx * 0.015, 0.045), (sx * 0.06, 0.055), 0.012, "#f7e7a0")
        E(0, -0.012, 0.012, 0.009, "#a8201c")
        E(0, -0.055, 0.045, 0.02, "#7a1512")
        E(0, -0.048, 0.045, 0.012, "#d8352e")
        cv.poly([P(-0.03, -0.06), P(-0.018, -0.06), P(-0.024, -0.04)], wht)
        cv.poly([P(0.03, -0.06), P(0.018, -0.06), P(0.024, -0.04)], wht)
        Arc(0, -0.052, 0.042, 0.016, 0.004, blk, -math.pi + 0.2, -0.2)
    elif kd == "tengu":
        for sx in (-1, 1):
            Ln((sx * 0.015, 0.048), (sx * 0.065, 0.06), 0.016, blk)
            E(sx * 0.035, 0.022, 0.014, 0.012, "#f2c531")
            E(sx * 0.035, 0.022, 0.006, 0.008, blk)
        E(0, -0.075, 0.04, 0.025, wht)
        Arc(0, -0.045, 0.02, 0.01, 0.004, blk, -math.pi + 0.3, -0.3)
    elif kd == "bird":
        for sx in (-1, 1):
            E(sx * 0.038, 0.02, 0.026, 0.027, wht)
            E(sx * 0.036, 0.018, 0.012, 0.014, blk)
            E(sx * 0.031, 0.024, 0.004, 0.004, wht)
            E(sx * 0.06, -0.035, 0.016, 0.012, "#f49ab0")
        E(0, -0.04, 0.05, 0.035, "#cfe9f7")
        cv.poly([P(-0.03, 0.09), P(0.0, 0.12), P(0.03, 0.09)], "#2c62c4")
    elif kd == "rabbit":
        for sx in (-1, 1):
            cv.poly([P(sx * 0.016, 0.09), P(sx * 0.03, 0.19), P(sx * 0.044, 0.09)], pink)
            E(sx * 0.035, 0.008, 0.012, 0.016, "#d23a4a")
            E(sx * 0.032, 0.014, 0.004, 0.004, wht)
            E(sx * 0.055, -0.03, 0.014, 0.01, "#f7b7c6")
        cv.poly([P(-0.01, -0.02), P(0.01, -0.02), P(0, -0.03)], pink)
        Ln((0, -0.03), (0, -0.042), 0.003, blk)
        Arc(-0.008, -0.042, 0.008, 0.007, 0.003, blk, -math.pi, 0)
        Arc(0.008, -0.042, 0.008, 0.007, 0.003, blk, -math.pi, 0)
    elif kd == "dragon":
        cv.rect(0, 0.82, 1, 1, "#d8352e")
        for k in range(7):
            x = -0.09 + k * 0.03
            cv.poly([P(x - 0.016, 0.085), P(x, 0.06), P(x + 0.016, 0.085)], "#d8352e")
        for sx in (-1, 1):
            E(sx * 0.04, 0.025, 0.02, 0.016, "#f2c531", sx * 0.3)
            E(sx * 0.04, 0.025, 0.005, 0.013, blk)
            Ln((sx * 0.018, 0.05), (sx * 0.07, 0.05), 0.008, "#f2c531")
            E(sx * 0.016, -0.04, 0.007, 0.005, blk)
            for k in range(3):
                Ln((sx * 0.05, -0.02 - 0.015 * k), (sx * 0.085, -0.025 - 0.02 * k), 0.004, "#1e6e52")
        E(0, -0.07, 0.05, 0.016, "#f7e7a0")
        Arc(0, -0.06, 0.045, 0.012, 0.004, blk, -math.pi + 0.2, -0.2)
    elif kd == "turtle":
        hexc_ = "#f2d36b"
        for k, (x, z) in enumerate(((0, 0.06), (-0.035, 0.045), (0.035, 0.045))):
            pts = [P(x + 0.018 * math.cos(a), z + 0.016 * math.sin(a)) for a in (math.pi / 3 * j for j in range(6))]
            cv.poly(pts, hexc_)
        for sx in (-1, 1):
            E(sx * 0.035, 0.0, 0.01, 0.013, blk)
            E(sx * 0.032, 0.005, 0.003, 0.003, wht)
            E(sx * 0.058, -0.028, 0.014, 0.01, "#f49ab0")
        Arc(0, -0.035, 0.028, 0.02, 0.005, blk, -math.pi + 0.4, -0.4)
    elif kd == "frog":
        for sx in (-1, 1):
            E(sx * 0.052, 0.07, 0.024, 0.024, wht)
            E(sx * 0.052, 0.066, 0.011, 0.013, blk)
            E(sx * 0.047, 0.072, 0.004, 0.004, wht)
            E(sx * 0.06, -0.01, 0.016, 0.01, "#f49ab0")
            E(sx * 0.012, 0.02, 0.003, 0.002, "#2f6b2a")
        Arc(0, 0.0, 0.06, 0.04, 0.005, "#2f6b2a", -math.pi + 0.5, -0.5)
        E(0, -0.06, 0.05, 0.02, "#bfe58c")
    elif kd == "sun":
        E(0, 0, 0.074, 0.074, "#ffd84a")
        for sx in (-1, 1):
            Arc(sx * 0.03, 0.012, 0.014, 0.01, 0.005, blk, 0.2, math.pi - 0.2)
            E(sx * 0.048, -0.02, 0.014, 0.01, "#f4867a")
        Arc(0, -0.018, 0.03, 0.026, 0.006, "#c2352f", -math.pi + 0.5, -0.5)


def build_mask(name, kd, idx, parent, atlas):
    pts = mask_outline(kd)
    N = len(pts)
    cx, cz, span = mask_mapping(kd)
    col, row = idx % 4, idx // 4
    sp = MASK_SPECS[kd]
    hw = max(abs(p[0]) for p in pts)
    hh = max(abs(p[1]) for p in pts)

    def uvof(x, z):
        u = 0.5 + (x - cx) / span
        v = 0.5 + (z - cz) / span
        return ((col + u) / 4, 1 - (row + 1) / 3 + v / 3)

    def depth(x, z, t):
        # front surface y (towards -y): dome + horizontal curvature so the mask wraps a face
        return -0.03 * (1 - t * t) - 0.004 + 0.032 * (x / 0.1) ** 2

    K = 3
    V, F, UV = [], [], []
    V.append((0.0, depth(0, 0, 0), 0.0))
    uvs = [uvof(0, 0)]
    for k in range(1, K + 1):
        t = k / K
        for (x, z) in pts:
            V.append((x * t, depth(x * t, z * t, t), z * t))
            uvs.append(uvof(x * t, z * t))

    def ring(k, i):
        return 1 + (k - 1) * N + (i % N)
    # front faces: normal must point -y. Outline is CCW in (x, z) seen from -y.
    for i in range(N):
        f = (0, ring(1, i + 1), ring(1, i))
        F.append(f)
    for k in range(1, K):
        for i in range(N):
            F.append((ring(k, i), ring(k, i + 1), ring(k + 1, i + 1), ring(k + 1, i)))
    # check orientation with the first face and flip all front faces if needed
    a, b, c = (Vector(V[j]) for j in F[0])
    if (b - a).cross(c - a).y > 0:
        F = [tuple(reversed(f)) for f in F]
    UV = [[uvs[j] for j in f] for f in F]
    nf = len(F)
    # back: outline offset back by the shell thickness, closed by a single n-gon
    base = len(V)
    th = 0.011
    for (x, z) in pts:
        V.append((x, depth(x, z, 1.0) + th, z))
    back = tuple(base + i for i in range(N))
    a, b, c = (Vector(V[j]) for j in back[:3])
    back = back if (b - a).cross(c - a).y > 0 else tuple(reversed(back))
    F.append(back)
    UV.append([(0.98, 0.002)] * N)
    for i in range(N):
        o0, o1 = ring(K, i), ring(K, i + 1)
        q = (o0, base + i, base + (i + 1) % N, o1)
        F.append(q)
        UV.append([uvs[o0], uvs[o0], uvs[o1], uvs[o1]])
    # rim face orientation: make outward
    mb = MB()
    mb.add((V, F, UV), kit.WHITE, "plastic_mask", uvmap=True)
    # fix rim orientation via a quick test on the first rim quad
    parts = MB()
    mf = mask_features(kd, depth)
    ob_mb = mb
    if mf is not None:
        for g, colr in mf:
            ob_mb.add(g, colr, "plastic_mask_parts")
    ob = make_obj(name, ob_mb, parent=parent, sharp=60, props={"role": "mask", "kind": kd})
    # make the back n-gon / rim normals consistent (outward) with Blender's recalc
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def mask_features(kd, depth):
    out = []
    if kd == "tengu":
        out.append((lathe([(0.016, 0), (0.012, 0.05), (0.006, 0.085), (0.0, 0.095)], 8, cap0=True), hexc("#C0392B")))
        out[-1] = (_xf(out[-1][0], T(0, depth(0, -0.01, 0) + 0.005, -0.01) @ R("X", 98)), hexc("#C0392B"))
    elif kd == "bird":
        g = lathe([(0.02, 0), (0.0, 0.04)], 8, cap0=True)
        out.append((_xf(g, T(0, depth(0, -0.012, 0.1) + 0.004, -0.012) @ R("X", 95) @ S(1, 0.7, 1)), hexc("#F2B134")))
    elif kd == "oni":
        for sx in (-1, 1):
            g = lathe([(0.013, 0), (0.008, 0.025), (0.0, 0.04)], 8, cap0=True)
            out.append((_xf(g, T(sx * 0.05, depth(sx * 0.05, 0.08, 0.85) + 0.008, 0.075) @ R("Y", sx * 25) @ R("X", -15)),
                        hexc("#F4E3A1")))
    elif kd == "dragon":
        for sx in (-1, 1):
            g = lathe([(0.009, 0), (0.006, 0.03), (0.0, 0.05)], 6, cap0=True)
            out.append((_xf(g, T(sx * 0.06, depth(sx * 0.06, 0.09, 0.9) + 0.01, 0.085) @ R("Y", sx * 35)), hexc("#F2C531")))
        g = sphere(0.022, 8, 4, rz=0.012)
        out.append((_xf(g, T(0, depth(0, -0.035, 0.3) - 0.004, -0.035) @ R("X", 90)), hexc("#3BB88E")))
    elif kd == "goofy":
        g = sphere(0.012, 8, 4)
        out.append((_xf(g, T(0, depth(0, -0.005, 0.1) - 0.004, -0.005)), hexc("#F0B48C")))
    return out


def _xf(geo, m):
    V, F, UV = geo
    return [tuple(m @ Vector(v)) for v in V], F, UV


def stall_lantern():
    s = Stall("lantern", C["indigo"], C["indigo2"], cd=0.42)
    mb = s.mb
    top = s.counter_top
    # waiting lanterns on the counter (bottom caps resting on the board)
    for k, (x, red, sq) in enumerate(((-0.95, False, 1.0), (-0.7, True, 1.0), (-0.45, False, 1.0), (-0.18, True, 0.32))):
        h = 0.26 * sq
        zt = top + h
        paper, tp, bt = chochin_geo(0.26, 0.095)
        m = T(x, -0.6, top) @ S(1, 1, sq) @ T(0, 0, 0.26)
        pc = C["paper_red"] if red else C["paper_white"]
        mb.add(paper, pc, "paper_lantern", m)
        mb.add(tp, C["black"], "wood_lacquer", m)
        mb.add(bt, C["black"], "wood_lacquer", m)
    # lantern_light on a little T-stand
    lx, ly = 0.3, -0.56
    bx(mb, 0.16, 0.16, 0.025, lx - 0.12, ly, top, C["wood_dark"], bevel=0.006)
    stick(mb, (lx - 0.12, ly, top), (lx - 0.12, ly, top + 0.5), 0.012, C["wood_dark"], "wood_frame", 6)
    stick(mb, (lx - 0.12, ly, top + 0.5), (lx + 0.02, ly, top + 0.5), 0.009, C["wood_dark"], "wood_frame", 6)
    ob = lantern_obj("lantern_light", s.root, (lx, ly, top + 0.49), h=0.3, r=0.11, red=False, cord=0.04, n=18,
                     rings=16)
    ob["role"] = "light_target"
    # candle on a dish + flame
    cx, cy = 0.68, -0.6
    mb.add(lathe([(0, 0), (0.04, 0), (0.05, 0.012), (0.046, 0.014), (0.0, 0.006)], 12), C["steel"], "metal_tin",
           T(cx, cy, top))
    cmb = MB()
    cmb.add(cyl(0.013, 0.075, 10), C["white"], "plastic_wax")
    cmb.add(cyl(0.0022, 0.012, 4, z0=0.075), C["black"], "plastic_misc")
    cob = make_obj("candle_wick", cmb, parent=s.root, props={"role": "candle"})
    cob.location = (cx, cy, top + 0.008)
    fmb = MB()
    flame_prof = [(0, 0), (0.006, 0.004), (0.0075, 0.01), (0.005, 0.018), (0.0, 0.03)]

    def fc(c, n):
        return hexc("#FFF2B0") if c.z < 0.012 else hexc("#FFB347")
    fmb.add(lathe(flame_prof, 8), fc, "glow_flame")
    fob = make_obj("flame", fmb, parent=cob, props={"role": "flame"})
    fob.location = (0, 0, 0.083)
    # matchbox + matches
    mx, my = 0.88, -0.55

    def mbc(c, n):
        return C["red"] if n.z > 0.5 else (C["white"] if abs(n.x) > 0.5 else hexc("#E8C25A"))
    mb.add(box(0.055, 0.036, 0.016, bevel=0.002, center=(0, 0, 0.008)), mbc, "paper_poi", M(mx, my, top, 15))
    for k in range(2):
        stick(mb, (mx - 0.06, my - 0.04 - 0.012 * k, top + 0.002), (mx - 0.01, my - 0.05 - 0.01 * k, top + 0.002),
              0.0018, C["wood_pale"], "wood_frame", 4)
        mb.add(sphere(0.004, 6, 3), hexc("#8A1E1E"), "plastic_misc", T(mx - 0.06, my - 0.04 - 0.012 * k, top + 0.003))
    # crate of folded lanterns behind
    crate_geo(mb, -0.75, 0.42, 0.0)
    for k in range(3):
        mb.add(cyl(0.09, 0.08, 10), C["paper_red"] if k % 2 else C["paper_white"], "paper_lantern",
               T(-0.88 + 0.13 * k, 0.42, 0.3) @ R("X", 90) @ T(0, 0, -0.04))
    stool(mb, 0.6, 0.3)
    s.anchors(keeper=(0.0, 0.2), cam=(lx - 0.25, -1.2, 1.32), target=(lx, ly, top + 0.3))
    s.finish()
    return s


def stall_food_a():
    s = Stall("food_a", C["yellow"], C["white"], cd=0.5, skirt=hexc("#C8332D"))
    mb = s.mb
    top = s.counter_top
    gx, gy = -0.1, -0.56
    bx(mb, 1.1, 0.46, 0.09, gx, gy, top, C["iron"], "metal_iron", 0.012)
    bx(mb, 1.06, 0.44, 0.02, gx, gy, top + 0.09, hexc("#2A2A2D"), "metal_iron", 0.004)
    for sx in (-1, 1):
        bx(mb, 0.012, 0.44, 0.03, gx + sx * 0.53, gy, top + 0.09, C["steel"], "metal_tin", 0.002)
    bx(mb, 1.06, 0.012, 0.03, gx, gy + 0.22, top + 0.09, C["steel"], "metal_tin", 0.002)
    pz = top + 0.11
    # noodle pile: lumpy mound + strands + toppings
    r2 = random.Random(11)
    for k in range(5):
        x = gx - 0.18 + 0.1 * k + r2.uniform(-0.03, 0.03)
        y = gy + r2.uniform(-0.06, 0.06)
        rr = r2.uniform(0.09, 0.12)
        mb.add(sphere(rr, 10, 5, rz=rr * 0.6), C["noodle"], "plastic_food", T(x, y, pz))
    for k in range(18):
        x0 = gx - 0.22 + r2.uniform(0, 0.44)
        y0 = gy + r2.uniform(-0.1, 0.1)
        pts = []
        for j in range(6):
            t = j / 5
            pts.append((x0 + 0.12 * t * math.cos(k) + 0.015 * math.sin(9 * t + k),
                        y0 + 0.08 * t * math.sin(k * 1.7) + 0.015 * math.cos(7 * t + k),
                        pz + 0.035 + 0.02 * math.sin(math.pi * t) + 0.005 * k % 0.02))
        mb.add(tube(pts, 0.0045, 4, caps=False), hexc("#C98845"), "plastic_food")
    for k in range(26):
        x = gx - 0.2 + r2.uniform(0, 0.4)
        y = gy + r2.uniform(-0.09, 0.09)
        kind = k % 4
        colr = [hexc("#7DBE4A"), hexc("#EE8A3A"), hexc("#E0485A"), hexc("#E6B9A0")][kind]
        sz = [(0.03, 0.02, 0.006), (0.025, 0.006, 0.006), (0.012, 0.004, 0.004), (0.028, 0.018, 0.006)][kind]
        mb.add(box(*sz), colr, "plastic_food", M(x, y, pz + 0.04 + r2.uniform(0, 0.02), r2.uniform(0, 180), r2.uniform(-20, 20)))
    # spatulas
    for sx in (-1, 1):
        m = M(gx + 0.36 + sx * 0.05, gy - 0.05, pz, 90 + sx * 10)
        mb.add(box(0.1, 0.08, 0.003, center=(0, 0, 0.002)), C["steel"], "metal_tin", m)
        mb.add(tube([(0.05, 0, 0.004), (0.12, 0, 0.03), (0.2, 0, 0.04)], 0.008, 6), C["wood_dark"], "wood_frame", m)
    # food packs + sauce bottles
    for k in range(4):
        bx(mb, 0.2, 0.13, 0.035, 0.9, -0.58, top + 0.036 * k, hexc("#EDEDE6"), "plastic_misc", 0.006)
    for k, colr in enumerate(("#5A3220", "#F5E9A8")):
        mb.add(lathe([(0, 0), (0.03, 0), (0.032, 0.14), (0.02, 0.16), (0.006, 0.19), (0, 0.19)], 10), hexc(colr),
               "plastic_bottle", T(0.6 + 0.08 * k, -0.45, top))
    cardboard(mb, -0.85, 0.45)
    cardboard(mb, -0.8, 0.45, 0.26, (0.34, 0.26, 0.2), 10)
    stool(mb, 0.75, 0.35)
    s.fx("fx_steam", (gx, gy, pz + 0.18))
    s.anchors(keeper=(-0.1, 0.1))
    s.finish()
    return s


def stall_food_b():
    s = Stall("food_b", C["teal"], C["white"], cd=0.5)
    mb = s.mb
    top = s.counter_top
    gx, gy = -0.2, -0.56
    bx(mb, 0.7, 0.46, 0.1, gx, gy, top, C["iron"], "metal_iron", 0.012)
    pz = top + 0.1
    bx(mb, 0.64, 0.42, 0.04, gx, gy, pz, hexc("#2A2A2D"), "metal_iron", 0.006)
    pz += 0.04
    r2 = random.Random(5)
    for i in range(6):
        for j in range(4):
            x = gx - 0.25 + 0.1 * i
            y = gy - 0.15 + 0.1 * j
            mb.add(torus(0.032, 0.006, 10, 3), hexc("#1C1C1E"), "metal_iron", T(x, y, pz))
            if (i + j) % 5 != 3:
                def tc(c, n, z0=pz):
                    return hexc("#8A4B22") if n.z > 0.55 else hexc("#D59A4A")
                mb.add(sphere(0.03, 8, 5), tc, "plastic_food", T(x, y, pz + 0.006) @ R("Z", r2.uniform(0, 90)))
    # picks
    for k in range(2):
        stick(mb, (gx + 0.38, gy - 0.1 + 0.03 * k, pz - 0.035), (gx + 0.52, gy - 0.16 + 0.03 * k, pz - 0.03), 0.003,
              C["steel"], "metal_tin", 4)
    # boat trays with balls, sauce and toppings
    for t, (tx, ty) in enumerate(((0.45, -0.6), (0.72, -0.6))):
        boat = [(-0.1, -0.035), (-0.06, -0.05), (0.06, -0.05), (0.1, -0.035), (0.1, 0.035), (0.06, 0.05),
                (-0.06, 0.05), (-0.1, 0.035)]
        mb.add(prism(boat, 0, 0.018), C["wood_pale"], "wood_frame", M(tx, ty, top, 10 * t))
        for k in range(6):
            bxp = tx - 0.06 + 0.06 * (k % 3)
            byp = ty - 0.022 + 0.044 * (k // 3)

            def tc(c, n, zz=top + 0.045):
                if n.z > 0.75:
                    return hexc("#4A2412")
                return hexc("#D59A4A")
            mb.add(sphere(0.026, 8, 5), tc, "plastic_food", T(bxp, byp, top + 0.044))
            mb.add(sphere(0.008, 4, 2, rz=0.002), hexc("#2E7D32"), "plastic_food", T(bxp, byp, top + 0.071))
    # batter bowl + ladle
    mb.add(lathe([(0, 0), (0.09, 0), (0.12, 0.09), (0.115, 0.09), (0.085, 0.008), (0, 0.008)], 14), C["steel"],
           "metal_tin", T(-0.82, -0.55, top))
    mb.add(cyl(0.11, 0.004, 14, z0=0.07), hexc("#F2E6C2"), "plastic_food", T(-0.82, -0.55, top))
    stick(mb, (-0.82, -0.55, top + 0.06), (-0.72, -0.5, top + 0.2), 0.005, C["steel"], "metal_tin", 4)
    # octopus sign on the counter board: original little octopus figure
    octo(mb, 0.95, -0.45, top)
    cooler(mb, 0.85, 0.35, col=C["teal"])
    stool(mb, -0.7, 0.35)
    s.fx("fx_steam", (gx, gy, pz + 0.16))
    s.anchors(keeper=(-0.2, 0.1))
    s.finish()
    return s


def octo(mb, x, y, z):
    col = hexc("#EE6A5A")
    mb.add(sphere(0.06, 10, 6, rz=0.07), col, "plastic_misc", T(x, y, z + 0.1))
    for k in range(6):
        a = 2 * math.pi * k / 6
        pts = [(x + 0.03 * math.cos(a), y + 0.03 * math.sin(a), z + 0.05),
               (x + 0.06 * math.cos(a), y + 0.06 * math.sin(a), z + 0.015),
               (x + 0.09 * math.cos(a + 0.4), y + 0.09 * math.sin(a + 0.4), z + 0.012)]
        mb.add(tube(pts, [0.014, 0.011, 0.006], 6), col, "plastic_misc")
    eyes(mb, x, y - 0.058, z + 0.11, 0.02, 0.009)
    mb.add(torus(0.022, 0.004, 10, 3), hexc("#3C7BCB"), "cloth_plush", T(x, y, z + 0.155))


# ----------------------------------------------------------------------------- gate & props


def gate():
    root = empty("gate", size=0.6, kind="ARROWS", props={"kind": "gate"})
    mb = MB()
    lac, blk = C["lacquer"], C["black"]
    px = 3.95
    H = 4.2
    for sx in (-1, 1):
        x = sx * px
        mb.add(box(0.46, 0.46, 0.22, bevel=0.03, center=(0, 0, 0.11)), C["stone"], "stone_step", T(x, 0, 0))
        mb.add(cyl(0.13, H - 0.2, 14, 0.12), lac, "wood_lacquer", T(x, 0, 0.2))
        mb.add(cyl(0.15, 0.1, 14, bevel=0.01), blk, "wood_lacquer", T(x, 0, 0.2))
        # diagonal braces under the lower beam
        mb.add(tube([(x - sx * 0.1, 0, 3.0), (x - sx * 0.55, 0, 3.63)], (0.045, 0.06), 4), lac, "wood_lacquer")
    # lower beam
    mb.add(box(8.3, 0.16, 0.18, bevel=0.015, center=(0, 0, 3.72)), lac, "wood_lacquer")
    # top beam (shimaki) and cap (kasagi) with up-turned ends
    def bent(L, w, h, z, lift, n=24):
        pts = []
        for i in range(n + 1):
            t = -1 + 2 * i / n
            pts.append((t * L / 2, 0, z + lift * abs(t) ** 3))
        return tube(pts, (h / 2, w / 2), 4)
    mb.add(bent(8.9, 0.22, 0.2, 4.08, 0.12), lac, "wood_lacquer")
    mb.add(bent(9.5, 0.32, 0.12, 4.25, 0.22), blk, "wood_lacquer")
    # central plaque (blank, no text) + struts
    mb.add(box(0.06, 0.08, 0.36, center=(0, 0, 3.98)), lac, "wood_lacquer")
    mb.add(box(0.7, 0.06, 0.32, bevel=0.02, center=(0, -0.08, 3.98)), hexc("#1E1E22"), "wood_lacquer")
    mb.add(box(0.6, 0.02, 0.22, center=(0, -0.115, 3.98)), C["cream"], "paper_poi")
    for k in range(5):
        a = math.pi / 2 + 2 * math.pi * k / 5
        mb.add(cyl(0.032, 0.01, 10), C["gold"], "metal_tin",
               T(0.04 * math.cos(a), -0.126, 3.98 + 0.04 * math.sin(a)) @ R("X", 90))
    mb.add(cyl(0.02, 0.012, 10), hexc("#C8332D"), "metal_tin", T(0, -0.13, 3.98) @ R("X", 90))
    make_obj("gate_frame", mb, parent=root)
    xs = [-3.0 + i for i in range(7)]
    for i, x in enumerate(xs):
        lm = MB()
        add_chochin(lm, 0, 0, 0, 0.46, 0.17, C["paper_red"] if i % 2 == 0 else C["paper_white"],
                    C["white"] if i % 2 == 0 else C["red"], cord=0.06)
        ob = make_obj(f"gatelantern_{i}", lm, parent=root, props={"role": "lantern"})
        ob.location = (x, 0, 3.63)
    # tall standing lanterns at the post bases (andon on a post)
    for i, sx in enumerate((-1, 1)):
        am = MB()
        am.add(box(0.36, 0.36, 0.08, bevel=0.015, center=(0, 0, 0.04)), C["stone"], "stone_step")
        am.add(box(0.09, 0.09, 1.0, bevel=0.01, center=(0, 0, 0.58)), lac, "wood_lacquer")
        am.add(box(0.3, 0.3, 0.04, bevel=0.008, center=(0, 0, 1.1)), blk, "wood_lacquer")
        for cx_ in (-1, 1):
            for cy_ in (-1, 1):
                am.add(box(0.03, 0.03, 0.5, center=(cx_ * 0.13, cy_ * 0.13, 1.37)), blk, "wood_lacquer")
        am.add(box(0.25, 0.25, 0.48, center=(0, 0, 1.37)), C["paper_white"], "paper_lantern")
        am.add(prism([(-0.21, -0.21), (0.21, -0.21), (0.21, 0.21), (-0.21, 0.21)], 1.62, 1.66, bevel=0.01), blk,
               "wood_lacquer")
        am.add(lathe([(0.2, 0), (0.0, 0.14)], 4, cap0=True, phase=math.pi / 4), blk, "wood_lacquer",
               T(0, 0, 1.66) @ S(1.41))
        am.add(sphere(0.03, 6, 3), C["gold"], "metal_tin", T(0, 0, 1.82))
        ob = make_obj(f"gate_andon_{i}", am, parent=root, props={"role": "lantern"})
        ob.location = (sx * 4.45, 0, 0)
    return root


def lantern_string_unit():
    root = empty("lantern_string_unit", size=0.2, props={"kind": "lantern_unit"})
    for nm, red in (("lantern_red", True), ("lantern_white", False)):
        lantern_obj(nm, root, (0, 0, 0), h=0.32, r=0.12, red=red, cord=0.05)
    return root


def furin():
    root = empty("furin", size=0.1, props={"kind": "furin"})
    mb = MB()
    # hook ring + string
    mb.add(torus(0.008, 0.002, 8, 3), C["black"], "plastic_misc", R("X", 90))
    mb.add(box(0.002, 0.002, 0.03, center=(0, 0, -0.023)), C["white"], "plastic_misc")
    # glass bell: shell with an open bottom
    prof = [(0.0, -0.035), (0.012, -0.036), (0.026, -0.045), (0.036, -0.065), (0.042, -0.09), (0.044, -0.104),
            (0.040, -0.104), (0.038, -0.09), (0.032, -0.068), (0.022, -0.05), (0.01, -0.042), (0.0, -0.041)]

    def bc(c, n):
        if c.z < -0.098:
            return C["white"]
        if -0.075 < c.z < -0.06 and n.y < -0.3:
            return hexc("#FF7A2A")
        return hexc("#A8D8F0")
    mb.add(lathe(prof, 14), bc, "plastic_furin")
    # clapper string + glass bead
    mb.add(box(0.0015, 0.0015, 0.09, center=(0, 0, -0.085)), C["white"], "plastic_misc")
    mb.add(sphere(0.008, 8, 4), hexc("#A8D8F0"), "plastic_furin", T(0, 0, -0.1))
    make_obj("furin_bell", mb, parent=root)
    smb = MB()
    w, h = 0.04, 0.17

    def sc(c, n):
        return hexc("#3C7BCB") if c.z < -h * 0.75 else (C["red"] if c.z > -0.02 else hexc("#FBF4E2"))
    smb.add(slab(lambda u, v: (-w / 2 + w * u, 0.0, -h + h * v), 1, 5, 0.0015), sc, "cloth_furin_strip")
    ob = make_obj("wind_furin_strip", smb, parent=root, props={"role": "wind", "pin": "top"})
    ob.location = (0, 0, -0.13)
    return root


def nobori():
    root = empty("nobori", size=0.3, props={"kind": "nobori"})
    mb = MB()
    H = 3.2
    # base: water-filled weight
    mb.add(lathe([(0, 0), (0.24, 0), (0.26, 0.03), (0.25, 0.1), (0.2, 0.13), (0.06, 0.15), (0.05, 0.2), (0, 0.2)], 16),
           hexc("#4F5560"), "plastic_misc")
    mb.add(cyl(0.022, H - 0.15, 8, z0=0.15), hexc("#D9D2C4"), "metal_tin")
    mb.add(cyl(0.012, 0.66, 6), hexc("#D9D2C4"), "metal_tin", T(0.0, 0, H - 0.05) @ R("Y", 90))
    mb.add(sphere(0.03, 8, 4), C["gold"], "metal_tin", T(0, 0, H))
    make_obj("nobori_pole", mb, parent=root)
    cv = kit.Canvas(256, 768, "#FAF7F0")
    cv.rect(0, 0.86, 1, 1, "#D8262D")
    cv.rect(0, 0, 1, 0.07, "#D8262D")
    cv.rect(0.0, 0.0, 0.1, 1.0, "#D8262D")
    for k in range(4):
        cv.ellipse(0.32 + 0.18 * k, 0.93, 0.04, 0.013, "#FAF7F0")
    # emblem: blue wave circle with a red five-petal flower
    cx, cy = 0.56, 0.6
    cv.ellipse(cx, cy, 0.36, 0.12, "#2C62C4")
    cv.ellipse(cx, cy, 0.3, 0.1, "#FAF7F0")
    for k in range(3):
        cv.ring(cx - 0.18 + 0.18 * k, cy - 0.05, 0.11, 0.035, 0.018, "#2C62C4", 0.1, math.pi - 0.1)
    for k in range(5):
        a = math.pi / 2 + k * 2 * math.pi / 5
        cv.ellipse(cx + 0.11 * math.cos(a), cy + 0.036 * math.sin(a), 0.085, 0.03, "#D8262D", 0)
    cv.ellipse(cx, cy, 0.05, 0.016, "#F2C531")
    # lower: three wave scallops
    for k in range(3):
        cv.ring(0.3 + 0.24 * k, 0.2, 0.12, 0.04, 0.03, "#2C62C4", 0.0, math.pi)
        cv.ring(0.3 + 0.24 * k, 0.2, 0.06, 0.02, 0.02, "#2C62C4", 0.0, math.pi)
    img = cv.to_image("tex_nobori", os.path.join(TEX_DIR, "nobori.png"))
    material("fabric_flag_nobori", image=img)
    cm = MB()
    w, h = 0.6, 1.9
    zt = H - 0.08
    cm.add(slab(lambda u, v: (0.03 + w * u, -0.025, zt - h + h * v), 4, 10, 0.004), kit.WHITE, "fabric_flag_nobori",
           uvmap=True)
    ob = make_obj("wind_nobori_cloth", cm, parent=root, origin=(0.03 + w / 2, -0.025, zt),
                  props={"role": "wind", "pin": "top+pole"})
    return root


def bench():
    root = empty("bench", size=0.3, props={"kind": "prop"})
    mb = MB()
    L, Dp, Hs = 1.6, 0.4, 0.43
    for k in range(3):
        bx(mb, L, 0.12, 0.035, 0, -0.13 + 0.13 * k, Hs - 0.035, C["wood"] if k % 2 else shade(C["wood"], 0.93),
           bevel=0.008)
    for sx in (-1, 1):
        for sy in (-1, 1):
            bx(mb, 0.06, 0.06, Hs - 0.035, sx * (L / 2 - 0.12), sy * 0.15, 0, C["wood_mid"], bevel=0.008)
        bx(mb, 0.05, 0.36, 0.05, sx * (L / 2 - 0.12), 0, Hs - 0.085, C["wood_mid"])
        bx(mb, 0.04, 0.32, 0.04, sx * (L / 2 - 0.12), 0, 0.1, C["wood_mid"])
    bx(mb, L - 0.3, 0.04, 0.05, 0, 0, 0.1, C["wood_mid"])
    make_obj("bench_mesh", mb, parent=root)
    return root


def steps():
    root = empty("steps", size=0.3, props={"kind": "prop"})
    mb = MB()
    W = 1.6
    st = [C["stone"], shade(C["stone"], 0.94), C["stone2"]]
    # front step, middle step, stoop landing (front = -Y)
    bx(mb, W, 1.5, 0.15, 0, 0.0, 0, st[0], "stone_step", 0.02)
    bx(mb, W - 0.04, 1.2, 0.15, 0, 0.15, 0.15, st[1], "stone_step", 0.02)
    bx(mb, W - 0.08, 0.9, 0.15, 0, 0.3, 0.3, st[2], "stone_step", 0.02)
    # cheek stones
    for sx in (-1, 1):
        bx(mb, 0.16, 0.9, 0.5, sx * (W / 2 + 0.08), 0.3, 0, shade(C["stone2"], 0.9), "stone_step", 0.025)
        bx(mb, 0.18, 0.18, 0.06, sx * (W / 2 + 0.08), -0.04, 0.0, shade(C["stone2"], 0.85), "stone_step", 0.02)
    # door frame on the landing (posts + lintel) so it reads as a doorway stoop
    for sx in (-1, 1):
        bx(mb, 0.1, 0.1, 2.15, sx * 0.62, 0.7, 0.45, C["wood_dark"], bevel=0.01)
    bx(mb, 1.44, 0.12, 0.12, 0, 0.7, 2.6, C["wood_dark"], bevel=0.012)
    bx(mb, 1.14, 0.03, 2.15, 0, 0.73, 0.45, hexc("#E9DFC9"), "paper_poi", 0.0)
    for k in range(1, 4):
        bx(mb, 0.025, 0.04, 2.15, -0.57 + 0.285 * k, 0.715, 0.45, C["wood_mid"], bevel=0.0)
    for k in range(1, 6):
        bx(mb, 1.14, 0.04, 0.025, 0, 0.715, 0.45 + 0.358 * k, C["wood_mid"], bevel=0.0)
    make_obj("steps_mesh", mb, parent=root)
    return root


def crate():
    root = empty("crate", size=0.2, props={"kind": "prop"})
    mb = MB()
    crate_geo(mb, 0, 0, 0)
    make_obj("crate_mesh", mb, parent=root)
    return root


def barrel():
    root = empty("barrel", size=0.2, props={"kind": "prop"})
    mb = MB()
    H = 0.64
    prof = [(0.0, 0.0), (0.2, 0.0)] + [(0.2 + 0.05 * math.sin(math.pi * t / 8), H * t / 8) for t in range(1, 8)] + \
        [(0.2, H), (0.185, H), (0.185, H - 0.02), (0.0, H - 0.02)]
    staves = [C["wood"], shade(C["wood"], 0.88)]

    def sc(c, n):
        if c.z > H - 0.025 and n.z > 0.5:
            return C["wood_pale"]
        a = math.atan2(c.y, c.x)
        return staves[int((a + math.pi) / (2 * math.pi) * 18) % 2]
    mb.add(lathe(prof, 18), sc, "wood_frame")
    for z in (0.1, 0.32, 0.54):
        rr = 0.2 + 0.05 * math.sin(math.pi * z / H) + 0.004
        mb.add(lathe([(rr, z - 0.022), (rr, z + 0.022)], 18), C["iron"], "metal_iron")
    make_obj("barrel_mesh", mb, parent=root)
    return root


def potted_plant():
    root = empty("potted_plant", size=0.2, props={"kind": "prop"})
    mb = MB()
    tc = C["terracotta"]
    mb.add(lathe([(0, 0), (0.13, 0), (0.17, 0.24), (0.19, 0.25), (0.19, 0.29), (0.165, 0.29), (0.15, 0.26), (0, 0.26)],
                 16), lambda c, n: shade(tc, 0.85) if c.z > 0.24 else tc, "stone_step")
    mb.add(cyl(0.155, 0.01, 14, z0=0.255), hexc("#4A3426"), "stone_step")
    bam = C["bamboo"]

    def bcol(c, n):
        return shade(bam, 0.75) if (c.z * 100) % 22 < 1.6 else bam
    canes = [(-0.11, -0.02), (0.0, 0.0), (0.11, -0.02)]
    tops = []
    for (x, y) in canes:
        p0 = (x, y, 0.2)
        p1 = (x * 1.6, y, 1.25)
        pts = [tuple(p0[i] + (p1[i] - p0[i]) * t / 8 for i in range(3)) for t in range(9)]
        mb.add(tube(pts, 0.008, 5), bcol, "wood_frame")
        tops.append(p1)
    for z in (0.62, 0.98):
        t = (z - 0.2) / 1.05
        xa = -0.11 * (1 + 0.6 * t) - 0.03
        mb.add(tube([(xa, -0.035, z), (-xa, -0.035, z)], 0.006, 5), bam, "wood_frame")
    # vines winding up each cane, leaves and morning glories
    r2 = random.Random(3)
    leaf = [(0, 0), (0.025, 0.02), (0.03, 0.045), (0.015, 0.06), (0.0, 0.05), (-0.015, 0.06), (-0.03, 0.045),
            (-0.025, 0.02)]
    flowers = [hexc("#3E5FD0"), hexc("#8A56C9"), hexc("#E46AA6")]
    for ci, (x, y) in enumerate(canes):
        pts = []
        for k in range(26):
            t = k / 25
            z = 0.27 + 0.95 * t
            xc = x * (1 + 0.6 * (z - 0.2) / 1.05)
            a = t * 9 + ci
            pts.append((xc + 0.017 * math.cos(a), y + 0.017 * math.sin(a), z))
        mb.add(tube(pts, 0.0035, 4, caps=False), hexc("#5E9A3A"), "cloth_plush")
        for k in range(3, 26, 3):
            p = Vector(pts[k])
            a = r2.uniform(0, 360)
            m = T(*p) @ R("Z", a) @ R("X", r2.uniform(50, 80)) @ S(r2.uniform(0.8, 1.2))
            g = ngon_sheet(leaf, 0.002)
            mb.add(g, hexc("#4E9A3E") if k % 3 else hexc("#6BB04A"), "cloth_plush", m)
        for k in range(6, 25, 5):
            p = Vector(pts[k])
            a = r2.uniform(-60, 60)
            col = flowers[(k + ci) % 3]
            m = T(*p) @ R("Z", a) @ R("X", 100) @ T(0, 0, 0.01)

            def fc(c, n, col=col, m=m):
                d = (m.inverted() @ c)
                return C["white"] if math.hypot(d.x, d.y) < 0.012 else col
            mb.add(lathe([(0.004, 0.0), (0.012, 0.022), (0.036, 0.036), (0.034, 0.038), (0.01, 0.025), (0.003, 0.003)],
                         6), fc, "cloth_plush", m)
    make_obj("potted_plant_mesh", mb, parent=root)
    return root


def bicycle():
    """Old step-through town bike, parked side-on along X (front wheel at +X)."""
    root = empty("bicycle", size=0.3, props={"kind": "prop"})
    mb = MB()
    body = hexc("#6FC0B0")
    dark, chrome = hexc("#2A2A2C"), C["steel"]
    R_ = 0.33
    wx = (-0.53, 0.53)
    for x in wx:
        m = T(x, 0, R_) @ R("X", 90)
        mb.add(torus(R_ - 0.02, 0.02, 28, 4), dark, "plastic_misc", m)
        mb.add(torus(R_ - 0.045, 0.007, 28, 3), chrome, "metal_tin", m)
        mb.add(cyl(0.025, 0.08, 8, z0=-0.04), chrome, "metal_tin", m)
        for k in range(8):
            a = math.pi * k / 8
            p0 = (x + 0.3 * math.cos(a), 0, R_ + 0.3 * math.sin(a))
            p1 = (x - 0.3 * math.cos(a), 0, R_ - 0.3 * math.sin(a))
            mb.add(tube([p0, p1], 0.0022, 3, caps=False), chrome, "metal_tin")
        # fender
        def fen(u, v, x=x):
            a = math.radians(15 + 150 * u)
            return (x + 0.36 * math.cos(a), -0.035 + 0.07 * v, R_ + 0.36 * math.sin(a))
        mb.add(slab(fen, 14, 1, 0.004), body, "metal_bike")
    bb = (-0.04, 0, 0.3)
    head_t, head_b = (0.4, 0, 0.84), (0.44, 0, 0.7)
    seat_t = (-0.2, 0, 0.82)
    rear = (wx[0], 0, R_)
    front = (wx[1], 0, R_)
    mb.add(tube([head_b, (0.3, 0, 0.55), (0.12, 0, 0.38), bb], 0.022, 8), body, "metal_bike")
    mb.add(tube([head_t, head_b], 0.026, 8), body, "metal_bike")
    mb.add(tube([bb, seat_t], 0.02, 8), body, "metal_bike")
    for sy in (-1, 1):
        mb.add(tube([(bb[0], sy * 0.03, bb[2]), (rear[0], sy * 0.05, rear[2])], 0.011, 6), body, "metal_bike")
        mb.add(tube([(-0.17, sy * 0.02, 0.72), (rear[0], sy * 0.05, rear[2])], 0.01, 6), body, "metal_bike")
        mb.add(tube([(head_b[0], sy * 0.02, head_b[2]), (0.5, sy * 0.045, 0.45), (front[0], sy * 0.05, front[2])],
                    0.011, 6), chrome, "metal_tin")
    # chain guard
    def guard(u, v):
        a = 2 * math.pi * u
        return (-0.28 + 0.27 * math.cos(a) * (0.4 + 0.6 * v), 0.065, 0.31 + 0.07 * math.sin(a) * (0.4 + 0.6 * v))
    mb.add(slab(lambda u, v: (-0.5 + 0.55 * u, 0.065, 0.27 + 0.09 * v - 0.03 * u), 6, 1, 0.004), body, "metal_bike")
    mb.add(cyl(0.09, 0.012, 14, z0=-0.006), chrome, "metal_tin", T(bb[0], 0.05, bb[2]) @ R("X", 90))
    for sy in (-1, 1):
        mb.add(tube([(bb[0], sy * 0.05, bb[2]), (bb[0] + sy * 0.12, sy * 0.06, bb[2] - sy * 0.08)], 0.009, 5), chrome,
               "metal_tin")
        mb.add(box(0.09, 0.06, 0.02, bevel=0.004, center=(bb[0] + sy * 0.12, sy * 0.1, bb[2] - sy * 0.08)), dark,
               "plastic_misc")
    # seat, post
    mb.add(tube([seat_t, (-0.21, 0, 0.9)], 0.012, 6), chrome, "metal_tin")
    mb.add(sphere(0.1, 10, 5, rz=0.035), hexc("#5A3A2A"), "plastic_misc", T(-0.23, 0, 0.93) @ S(1.3, 0.7, 1))
    # stem + swept handlebar + grips + bell + lamp
    mb.add(tube([head_t, (0.37, 0, 0.98)], 0.012, 6), chrome, "metal_tin")
    hb = [(0.22, -0.27, 0.98), (0.3, -0.24, 0.99), (0.37, -0.12, 0.99), (0.37, 0.0, 0.98), (0.37, 0.12, 0.99),
          (0.3, 0.24, 0.99), (0.22, 0.27, 0.98)]
    mb.add(tube(hb, 0.011, 6), chrome, "metal_tin")
    for sy in (-1, 1):
        mb.add(tube([(0.25, sy * 0.262, 0.98), (0.16, sy * 0.28, 0.975)], 0.016, 6), dark, "plastic_misc")
    mb.add(cyl(0.022, 0.015, 10), chrome, "metal_tin", T(0.33, 0.14, 1.0))
    mb.add(cyl(0.04, 0.06, 10, 0.045), chrome, "metal_tin", T(0.48, 0, 0.8) @ R("Y", 90))
    # front basket (wire-ish: frame + bars)
    bxx, bzz = 0.62, 0.86
    bw, bd, bh = 0.26, 0.34, 0.2
    corners = [(bxx - bw / 2, -bd / 2), (bxx + bw / 2, -bd / 2), (bxx + bw / 2, bd / 2), (bxx - bw / 2, bd / 2)]
    for z in (bzz, bzz + bh):
        mb.add(tube([(cx, cy, z) for cx, cy in corners], 0.006, 4, closed=True, caps=False), chrome, "metal_tin")
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        nb = 5 if abs(y1 - y0) > 0.1 else 4
        for k in range(nb):
            t = k / nb
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            mb.add(tube([(x, y, bzz), (x, y, bzz + bh)], 0.003, 3, caps=False), chrome, "metal_tin")
    mb.add(box(bw, bd, 0.006, center=(bxx, 0, bzz)), chrome, "metal_tin")
    mb.add(tube([(0.47, 0, 0.84), (bxx - bw / 2, 0, bzz + 0.02)], 0.008, 4), chrome, "metal_tin")
    # rear rack
    for sy in (-1, 1):
        mb.add(tube([(-0.2, sy * 0.06, 0.74), (-0.75, sy * 0.06, 0.74), (rear[0] - 0.02, sy * 0.06, R_)], 0.007, 4),
               chrome, "metal_tin")
    for k in range(4):
        x = -0.28 - 0.14 * k
        mb.add(tube([(x, -0.06, 0.74), (x, 0.06, 0.74)], 0.006, 4), chrome, "metal_tin")
    # kickstand
    mb.add(tube([(-0.4, 0.04, 0.32), (-0.46, 0.17, 0.0)], 0.009, 5), chrome, "metal_tin")
    make_obj("bicycle_mesh", mb, parent=root)
    return root


# ----------------------------------------------------------------------------- main


def main():
    kit.lower_priority()
    a = kit.script_args()
    out = os.path.abspath(a.get("out", os.path.join(REPO, "public", "models", "stalls.glb")))
    kit.reset_scene()
    kit.MATS.clear()
    setup_materials()
    for fn in (stall_goldfish, stall_candyapple, stall_shavedice, stall_ringtoss, stall_masks, stall_lantern,
               stall_food_a, stall_food_b):
        fn()
    gate()
    lantern_string_unit()
    furin()
    nobori()
    bench()
    steps()
    crate()
    barrel()
    potted_plant()
    bicycle()
    bpy.context.view_layer.update()
    tris = sum(kit.tri_count(o) for o in bpy.context.scene.objects if o.type == "MESH")
    print(f"[stalls] {len([o for o in bpy.context.scene.objects if o.type == 'MESH'])} meshes, {tris} tris")
    if a.get("blend"):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a["blend"]))
    kit.export_glb(out)
    k = kit.glb_strip_tags(out)
    kit.glb_compact_colors(out)
    n = os.path.getsize(out)
    print(f"[stalls] wrote {out} ({n / 1024:.0f} KiB), renamed {k} anchor nodes")


if __name__ == "__main__":
    main()
