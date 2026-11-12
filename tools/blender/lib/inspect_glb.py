"""Re-import an exported GLB, print/record its inventory, and render Eevee previews of every
top-level node (street-level 3/4 view ~3 m away, 1.6 m up, plus a front close-up).

  blender.exe --background --factory-startup --python-exit-code 1 --python tools/blender/lib/inspect_glb.py \
      -- --glb public/models/stalls.glb --out tools/blender/stalls/previews --readme tools/blender/stalls/README.md
Options: --nodes a,b,c (subset)  --no-render  --lineup (one overview image of all nodes side by side)
         --poses (for rigged files: also render each clip at its mid frame)
"""
import json
import math
import os
import re
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402

GPU_LOGGED = False


def base_name(n):
    return re.sub(r"\.\d{3}$", "", n)


def descendants(ob):
    out = []
    for c in ob.children:
        out.append(c)
        out.extend(descendants(c))
    return out


def tris_of(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def world_bbox(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    found = False
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
            found = True
    if not found:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    return lo, hi


def patch_materials():
    """Preview only: multiply the vertex colour (COLOR_0) into base colour, make glow_ emissive."""
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        if not any(n.type == "VERTEX_COLOR" for n in nt.nodes):
            vc = nt.nodes.new("ShaderNodeVertexColor")
            vc.layer_name = ""
            inp = bsdf.inputs["Base Color"]
            mixn = nt.nodes.new("ShaderNodeMix")
            mixn.data_type = "RGBA"
            mixn.blend_type = "MULTIPLY"
            mixn.inputs["Factor"].default_value = 1.0
            if inp.is_linked:
                src = inp.links[0].from_socket
                nt.links.new(src, mixn.inputs[6])
            else:
                mixn.inputs[6].default_value = inp.default_value
            nt.links.new(vc.outputs["Color"], mixn.inputs[7])
            nt.links.new(mixn.outputs[2], inp)
        bsdf.inputs["Roughness"].default_value = 0.8
        if m.name.startswith("glow_"):
            src = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].is_linked else None
            if src is not None:
                nt.links.new(src, bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 4.0


def setup_render(sc, res=(960, 720)):
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    try:
        sc.eevee.taa_render_samples = 16
    except Exception:
        pass
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"
    w = bpy.data.worlds.new("PreviewWorld")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.62, 0.74, 0.88, 1)
    bg.inputs[1].default_value = 0.9
    sc.world = w
    sun_d = bpy.data.lights.new("PrevSun", "SUN")
    sun_d.energy = 3.2
    sun_d.angle = math.radians(3)
    sun = bpy.data.objects.new("PrevSun", sun_d)
    sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    me = bpy.data.meshes.new("PrevGround")
    s = 40
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    gm = bpy.data.materials.new("PrevGround")
    gm.use_nodes = True
    b = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = kit.hexc("#b8ab94")
    b.inputs["Roughness"].default_value = 1.0
    me.materials.append(gm)
    g = bpy.data.objects.new("PrevGround", me)
    sc.collection.objects.link(g)
    camd = bpy.data.cameras.new("PrevCam")
    camd.lens = 30
    camd.clip_start = 0.02
    cam = bpy.data.objects.new("PrevCam", camd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam, g


def aim(cam, loc, target):
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = d.to_track_quat("-Z", "Y")


def render(sc, path):
    global GPU_LOGGED
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    if not GPU_LOGGED:
        import gpu
        r = gpu.platform.renderer_get()
        print("[gpu]", r, "|", gpu.platform.vendor_get(), "| backend", gpu.platform.backend_type_get())
        if re.search(r"swiftshader|llvmpipe|software|basic render", r, re.I) and "--allow-software" not in sys.argv:
            raise RuntimeError("CPU rasteriser: " + r)
        GPU_LOGGED = True


def fit_dist(lo, hi, cam, minimum):
    rad = (hi - lo).length / 2
    fov = cam.data.angle
    return max(minimum, rad / math.sin(fov / 2) * 0.95)


def main():
    kit.lower_priority()
    a = kit.script_args()
    glb = os.path.abspath(a["glb"])
    out = os.path.abspath(a.get("out", os.path.join(os.path.dirname(glb), "previews")))
    kit.reset_scene()
    sc = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=glb)
    gjs, _ = kit.glb_read(glb)
    roots = {gjs["nodes"][i].get("name", "") for i in gjs["scenes"][0]["nodes"]}
    # (the importer also adds bone-shape helpers such as "Icosphere": not part of the file)
    tops = [o for o in sc.objects if o.parent is None and base_name(o.name) in roots]
    want = a.get("nodes")
    if isinstance(want, str):
        want = want.split(",")
        tops = [o for o in tops if base_name(o.name) in want]
    tops.sort(key=lambda o: o.name)
    inv = []
    for t in tops:
        objs = [t] + descendants(t)
        meshes = [o for o in objs if o.type == "MESH"]
        tris = sum(tris_of(o) for o in meshes)
        empties = sorted({base_name(o.name) for o in objs if o.type == "EMPTY" and o is not t})
        lo, hi = world_bbox(objs)
        mats = sorted({s.material.name for o in meshes for s in o.material_slots if s.material})
        named = sorted({base_name(o.name) for o in objs if o is not t and o.type == "MESH"})
        inv.append(dict(node=base_name(t.name), type=t.type, tris=tris, meshes=len(meshes), named=named,
                        empties=empties, materials=mats,
                        size=[round(hi.x - lo.x, 2), round(hi.y - lo.y, 2), round(hi.z - lo.z, 2)],
                        bbox=[[round(v, 3) for v in lo], [round(v, 3) for v in hi]]))
    clips = []
    for act in bpy.data.actions:
        fr = act.frame_range
        clips.append(dict(name=act.name, frames=int(round(fr[1] - fr[0])) + 1,
                          seconds=round((fr[1] - fr[0]) / 30.0, 3)))
    size = os.path.getsize(glb)
    total = sum(i["tris"] for i in inv)
    report = dict(file=os.path.relpath(glb).replace("\\", "/") if False else os.path.basename(glb),
                  bytes=size, tris=total, nodes=inv, clips=clips,
                  textures=[dict(name=i.name, size=list(i.size)) for i in bpy.data.images if i.size[0] > 0])
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "inventory.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(f"[inspect] {os.path.basename(glb)}: {size / 1024:.0f} KiB, {total} tris, {len(inv)} top nodes, {len(clips)} clips")
    for i in inv:
        print(f"[inspect]  {i['node']:<22} {i['tris']:>6} tris  {i['size']}  empties={i['empties']}")
    for c in clips:
        print(f"[inspect]  clip {c['name']} {c['seconds']} s")

    if "readme" in a:
        write_table(os.path.abspath(a["readme"]), report)

    if a.get("no-render"):
        return
    patch_materials()
    cam, ground = setup_render(sc)
    allt = [o for o in sc.objects if o.parent is None and o.name not in ("PrevSun", "PrevGround", "PrevCam")]

    def show_only(t):
        keep = set([t] + descendants(t)) if t is not None else None
        for o in sc.objects:
            if o.name.startswith("Prev"):
                continue
            hide = (keep is not None and o not in keep) or (base_name(o.name) not in roots and o.parent is None
                                                            and o.type == "MESH")
            o.hide_render = hide

    if a.get("lineup"):
        show_only(None)
        x = 0.0
        orig = {}
        for t in tops:
            lo, hi = world_bbox([t] + descendants(t))
            w = hi.x - lo.x
            orig[t] = t.location.copy()
            t.location.x += x - lo.x
            x += w + 0.6
        bpy.context.view_layer.update()
        lo, hi = world_bbox([o for o in sc.objects if o.type == "MESH" and not o.name.startswith("Prev")])
        c = (lo + hi) / 2
        aim(cam, (c.x, lo.y - (hi.x - lo.x) * 0.75, (hi.z - lo.z) * 1.4 + 1.5), (c.x, c.y, c.z * 0.6))
        sc.render.resolution_x, sc.render.resolution_y = 1800, 700
        render(sc, os.path.join(out, "_lineup.png"))
        sc.render.resolution_x, sc.render.resolution_y = 960, 720
        for t, p in orig.items():
            t.location = p
        bpy.context.view_layer.update()

    for t in tops:
        show_only(t)
        objs = [t] + descendants(t)
        lo, hi = world_bbox(objs)
        c = (lo + hi) / 2
        nm = base_name(t.name)
        # game view: 3/4 from front-right, 3 m (more if the node is big), eye 1.6 m
        D = fit_dist(lo, hi, cam, 3.0)
        yaw = math.radians(35)
        eye_z = max(1.6, c.z + 0.2) if hi.z > 2.6 else 1.6
        loc = (c.x + math.sin(yaw) * D, c.y - math.cos(yaw) * D, eye_z)
        aim(cam, loc, (c.x, c.y, min(c.z, eye_z - 0.3) if hi.z > 0.8 else c.z))
        render(sc, os.path.join(out, f"{nm}_game.png"))
        # front close-up
        D = fit_dist(lo, hi, cam, 0.3) * 1.1
        aim(cam, (c.x - 0.15 * D, c.y - D, c.z + 0.25 * D), (c.x, c.y, c.z))
        render(sc, os.path.join(out, f"{nm}_front.png"))
        # the node's own mini-game camera anchor, if any (checks the cam / cam_target empties)
        ce = next((o for o in objs if base_name(o.name) == "cam" and o.type == "EMPTY"), None)
        ct = next((o for o in objs if base_name(o.name) == "cam_target" and o.type == "EMPTY"), None)
        if ce is not None and ct is not None:
            lens = cam.data.lens
            cam.data.sensor_fit = "VERTICAL"
            cam.data.angle = math.radians(50)
            aim(cam, ce.matrix_world.translation, ct.matrix_world.translation)
            render(sc, os.path.join(out, f"{nm}_cam.png"))
            cam.data.sensor_fit = "AUTO"
            cam.data.lens = lens
        if a.get("poses") and t.type == "ARMATURE":
            ad = t.animation_data or t.animation_data_create()
            for act in bpy.data.actions:
                if not act.name.startswith(nm + "_"):
                    continue
                ad.action = act
                if len(act.slots):
                    ad.action_slot = act.slots[0]
                fr = act.frame_range
                for k, f in enumerate((fr[0] + (fr[1] - fr[0]) * 0.25, fr[0] + (fr[1] - fr[0]) * 0.6)):
                    sc.frame_set(int(round(f)))
                    D = fit_dist(lo, hi, cam, 0.3) * 1.1
                    aim(cam, (c.x + 0.6 * D, c.y - 0.8 * D, c.z + 0.45 * D), (c.x, c.y, c.z))
                    render(sc, os.path.join(out, f"{act.name}_{k}.png"))
            ad.action = None
            sc.frame_set(1)


def write_table(readme, rep):
    lines = ["<!-- inventory:start (generated by tools/blender/lib/inspect_glb.py from the exported GLB) -->",
             "",
             f"File: `{rep['file']}`, **{rep['bytes'] / 1024:.0f} KiB**, **{rep['tris']} triangles**, "
             f"{len(rep['nodes'])} top-level nodes.",
             "",
             "| node | tris | size w×d×h (m) | named meshes | empties |",
             "|---|---:|---|---|---|"]
    for i in rep["nodes"]:
        nm = ", ".join(f"`{n}`" for n in i["named"] if not n.startswith(i["node"] + "_")) or "-"
        em = ", ".join(f"`{e}`" for e in i["empties"]) or "-"
        s = i["size"]
        lines.append(f"| `{i['node']}` | {i['tris']} | {s[0]} × {s[1]} × {s[2]} | {nm} | {em} |")
    if rep["clips"]:
        lines += ["", "| clip | frames @30 | seconds |", "|---|---:|---:|"]
        for c in rep["clips"]:
            lines.append(f"| `{c['name']}` | {c['frames']} | {c['seconds']} |")
    if rep["textures"]:
        lines += ["", "Textures: " + ", ".join(f"`{t['name']}` {t['size'][0]}×{t['size'][1]}" for t in rep["textures"])]
    lines += ["", "<!-- inventory:end -->"]
    block = "\n".join(lines)
    txt = open(readme, encoding="utf-8").read() if os.path.exists(readme) else ""
    if "<!-- inventory:start" in txt:
        txt = re.sub(r"<!-- inventory:start.*?<!-- inventory:end -->", lambda m: block, txt, flags=re.S)
    else:
        txt = txt + "\n\n## Inventory\n\n" + block + "\n"
    with open(readme, "w", encoding="utf-8") as f:
        f.write(txt)


if __name__ == "__main__":
    main()
