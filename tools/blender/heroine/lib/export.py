"""glTF 2.0 binary export: skinned meshes, one animation per action, morph targets, packed PNGs."""
import contextlib
import io
import json
import os

import bpy

from .common import COLL


def export(path, meta=None):
    sc = bpy.context.scene
    from .anim import FPS
    sc.render.fps, sc.render.fps_base = FPS, 1.0
    col = bpy.data.collections[COLL]
    arm = next(o for o in col.all_objects if o.type == "ARMATURE")
    if meta is not None:
        arm["heroine"] = json.dumps(meta)
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    for o in col.all_objects:
        o.select_set(True)
    vl.objects.active = arm
    # Shape key values at rest (the game drives them).
    for o in col.all_objects:
        if o.type == "MESH" and o.data.shape_keys:
            for kb in o.data.shape_keys.key_blocks[1:]:
                kb.value = 0.0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    opts = dict(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        use_active_scene=True,
        export_yup=True,
        export_apply=False,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_vertex_color="NONE",
        export_attributes=False,
        export_extras=True,
        export_skins=True,
        export_all_influences=False,
        export_def_bones=False,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_force_sampling=True,
        export_frame_step=1,
        export_optimize_animation_size=True,
        export_anim_slide_to_zero=True,
        export_rest_position_armature=True,
        export_morph=True,
        export_morph_normal=True,
        export_morph_animation=False,
        export_leaf_bone=False,
        export_lights=False,
        export_cameras=False,
        export_draco_mesh_compression_enable=False,
        export_bake_animation=False,
    )
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        bpy.ops.export_scene.gltf(**{k: v for k, v in opts.items() if k in props or k == "filepath"})
    for ln in log.getvalue().splitlines():
        if "ERROR" in ln or "WARNING" in ln:
            print("[export]", ln)
    from .glbpost import strip_scale_channels
    print("[export] removed scale channels:", strip_scale_channels(path))
    return os.path.getsize(path)
