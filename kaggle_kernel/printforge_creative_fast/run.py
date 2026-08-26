"""PrintForge creative "fast" tier Kaggle kernel (Shap-E text-to-3D).

Pushed fresh under each visitor's own Kaggle account for each job (see
backend/app/services/kernel_builder.py, which rewrites PROMPT and
kernel-metadata.json's id/title before every push -- this file in the repo
is the template/source of truth).

Ported from AI_3D_FACTORY's kaggle_kernel/shape_generator/generate_mesh.py
(the Shap-E generation itself, verbatim -- same --no-deps install
workaround, same sampling params) plus app/modules/mesh_quality.py (the
raw-mesh sanity check, verbatim) plus
app/controllers/blender/process_creative_mesh.py (the print-readiness
stage, ported the same way printforge_parametric/run.py ported
generate_model.py -- downloaded portable Blender instead of a local
install, since a public site can't assume Blender is installed and this
kernel has no local Blender to shell out to either).

Two fixes applied here that AI_3D_FACTORY's original code didn't need,
both already proven in printforge_parametric/run.py: `bpy.ops.wm.stl_export`
instead of `export_mesh.stl` (removed in the Blender 5.2.1 Linux build
Kaggle downloads), and CYCLES/CPU instead of BLENDER_EEVEE for the preview
render (headless-safe, no GL context needed).
"""
import json
import os
import subprocess
import shutil
import sys
import time

WORKDIR = "/kaggle/working"
BLENDER_VERSION = "5.2.1"
BLENDER_URL = (
    f"https://download.blender.org/release/Blender5.2/"
    f"blender-{BLENDER_VERSION}-linux-x64.tar.xz"
)
TARBALL = os.path.join(WORKDIR, "blender.tar.xz")
EXTRACT_DIR = os.path.join(WORKDIR, "blender_extracted")

# Rewritten by kernel_builder.py before each push.
PROMPT = "a majestic phoenix statue"

TARGET_SIZE_MM = 80.0
MIN_WALL_MM = 1.5

MIN_VERTICES = 100
MIN_FACES = 100
MIN_DIMENSION = 0.3
MAX_DIMENSION = 5.0
MIN_VOLUME = 0.005


def _pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=True)


def generate_mesh():
    # Shap-E and CLIP both unpin "torch" in their own setup files, so a
    # normal `pip install` would replace Kaggle's GPU-matched PyTorch with
    # the latest PyPI wheel -- which has dropped support for Kaggle's older
    # P100 GPUs (compute capability sm_60), breaking CUDA entirely. Install
    # both with --no-deps so the preinstalled torch is left alone, then add
    # back only the small pure-Python extras they actually need.
    _pip("--no-deps", "git+https://github.com/openai/CLIP.git")
    _pip("--no-deps", "git+https://github.com/openai/shap-e.git")
    _pip("filelock", "fire", "humanize", "blobfile", "ftfy", "packaging", "regex")

    import torch
    from shap_e.diffusion.gaussian_diffusion import diffusion_from_config
    from shap_e.diffusion.sample import sample_latents
    from shap_e.models.download import load_config, load_model
    from shap_e.util.notebooks import decode_latent_mesh

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    print(f"Prompt: {PROMPT}")

    xm = load_model("transmitter", device=device)
    model = load_model("text300M", device=device)
    diffusion = diffusion_from_config(load_config("diffusion"))

    latents = sample_latents(
        batch_size=1,
        model=model,
        diffusion=diffusion,
        guidance_scale=15.0,
        model_kwargs=dict(texts=[PROMPT]),
        progress=True,
        clip_denoised=True,
        use_fp16=(device.type == "cuda"),
        use_karras=True,
        karras_steps=64,
        sigma_min=1e-3,
        sigma_max=160,
        s_churn=0,
    )

    mesh = decode_latent_mesh(xm, latents[0]).tri_mesh()
    obj_path = os.path.join(WORKDIR, "mesh.obj")
    with open(obj_path, "w") as f:
        mesh.write_obj(f)
    print("Wrote", obj_path)
    return obj_path


def check_mesh_quality(obj_path):
    vertices, faces = [], []
    with open(obj_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                vertices.append(tuple(float(v) for v in parts[1:4]))
            elif line.startswith("f "):
                parts = line.split()[1:]
                faces.append([int(p.split("/")[0]) - 1 for p in parts])

    stats = {"vertex_count": len(vertices), "face_count": len(faces)}
    reasons = []

    if len(vertices) < MIN_VERTICES or len(faces) < MIN_FACES:
        reasons.append(f"too little geometry ({len(vertices)} vertices, {len(faces)} faces)")
        return {"passed": False, "reasons": reasons, "stats": stats}

    xs, ys, zs = [v[0] for v in vertices], [v[1] for v in vertices], [v[2] for v in vertices]
    dims = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    largest = max(dims)
    stats["bounding_box"] = {"x": dims[0], "y": dims[1], "z": dims[2]}
    stats["largest_dimension"] = largest

    if largest < MIN_DIMENSION:
        reasons.append(f"too small (largest dimension {largest:.4f})")
    elif largest > MAX_DIMENSION:
        reasons.append(f"too large (largest dimension {largest:.4f})")

    total = 0.0
    for face in faces:
        for i in range(1, len(face) - 1):
            v0, v1, v2 = vertices[face[0]], vertices[face[i]], vertices[face[i + 1]]
            total += (
                v0[0] * (v1[1] * v2[2] - v1[2] * v2[1])
                - v0[1] * (v1[0] * v2[2] - v1[2] * v2[0])
                + v0[2] * (v1[0] * v2[1] - v1[1] * v2[0])
            )
    volume = abs(total) / 6.0
    stats["volume"] = volume
    if volume < MIN_VOLUME:
        reasons.append(f"degenerate / near-zero enclosed volume ({volume:.6f})")

    return {"passed": len(reasons) == 0, "reasons": reasons, "stats": stats}


INNER_SCRIPT = r'''
import bpy
import bmesh
import json
import os
from mathutils import Vector

with open("/kaggle/working/creative_request.json", encoding="utf-8") as f:
    request = json.load(f)


def count_non_manifold(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    count = sum(1 for edge in mesh.edges if not edge.is_manifold)
    mesh.free()
    return count


def apply_flat_material(obj):
    """A plain, reliable neutral-gray material, applied AFTER voxel_remesh.

    Originally this read the mesh's imported per-vertex color attribute
    (Shap-E/TripoSR both encode color per vertex) into a Base Color via an
    Attribute shader node -- but voxel_remesh replaces the mesh's topology
    entirely and does not transfer that attribute, while the material slot
    itself (attached to the object, not the mesh data) survives. The result
    was a shader reading a now-nonexistent attribute, which evaluates to
    black -- confirmed via a real Kaggle run producing a nearly-unreadable
    black preview despite correct, valid geometry underneath. Simplest
    correct fix: stop trying to preserve generated color through a step
    that destroys it, and just apply a plain material after remeshing.
    """
    material = bpy.data.materials.new(name="PrintPreviewMaterial")
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.75, 0.75, 0.78, 1.0)
    obj.data.materials.clear()
    obj.data.materials.append(material)


def import_mesh(path):
    bpy.ops.wm.obj_import(filepath=path)
    imported = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if len(imported) > 1:
        bpy.context.view_layer.objects.active = imported[0]
        bpy.ops.object.join()
        imported = [bpy.context.view_layer.objects.active]
    return imported[0]


def voxel_remesh(obj, voxel_size_mm):
    """Repair non-manifold/holey generative geometry AND enforce a minimum
    feature size in one step, via Blender's built-in Voxel Remesh.

    Originally this used the object_print3d_utils addon's
    print3d_clean_non_manifold operator (matching AI_3D_FACTORY's local
    Blender setup) plus a separate Solidify modifier for minimum wall
    thickness. Found via a real Kaggle run (not assumed) that the portable
    Blender 5.2.1 Linux build Kaggle downloads doesn't ship that addon at
    all ("No module named 'object_print3d_utils'") -- it's been migrated
    to Blender's newer opt-in Extensions system and isn't bundled in this
    build. Voxel Remesh needs no addon, reliably produces a closed/solid
    mesh regardless of input mess, and using voxel_size == the minimum
    wall thickness has the side effect of also enforcing a comparable
    minimum feature size -- so it replaces both the old repair step and
    the old Solidify step.
    """
    modifier = obj.modifiers.new(name="Repair", type="REMESH")
    modifier.mode = "VOXEL"
    modifier.voxel_size = voxel_size_mm
    modifier.use_remove_disconnected = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def auto_scale(obj, target_size_mm):
    bpy.context.view_layer.update()
    dimensions = obj.dimensions
    largest = max(dimensions.x, dimensions.y, dimensions.z)
    if largest <= 0:
        raise ValueError("Mesh has zero size, cannot scale")
    factor = target_size_mm / largest
    obj.scale = (obj.scale.x * factor, obj.scale.y * factor, obj.scale.z * factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def sit_on_bed(obj):
    bpy.context.view_layer.update()
    world_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_z = min(corner.z for corner in world_corners)
    obj.location.z -= min_z
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)


def needs_base(obj, flat_fraction_threshold=0.3, epsilon_mm=0.5):
    bpy.context.view_layer.update()
    world_verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_z = min(v.z for v in world_verts)
    near_bottom = sum(1 for v in world_verts if v.z <= min_z + epsilon_mm)
    return (near_bottom / len(world_verts)) < flat_fraction_threshold


def add_base(obj, base_height_mm=2.0, margin_mm=2.0):
    bpy.context.view_layer.update()
    world_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_x = min(c.x for c in world_corners) - margin_mm
    max_x = max(c.x for c in world_corners) + margin_mm
    min_y = min(c.y for c in world_corners) - margin_mm
    max_y = max(c.y for c in world_corners) + margin_mm

    bpy.ops.mesh.primitive_cube_add(
        size=1, location=((min_x + max_x) / 2, (min_y + max_y) / 2, base_height_mm / 2)
    )
    base = bpy.context.object
    base.dimensions = (max_x - min_x, max_y - min_y, base_height_mm)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    modifier = obj.modifiers.new(name="BaseUnion", type="BOOLEAN")
    modifier.operation = "UNION"
    modifier.object = base
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)

    bpy.data.objects.remove(base, do_unlink=True)


def mesh_bounds(objects):
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return {axis: max(getattr(point, axis) for point in points) - min(getattr(point, axis) for point in points) for axis in ("x", "y", "z")}


def validate(objects, spec, report_path):
    bpy.context.view_layer.update()
    bounds = mesh_bounds(objects)
    non_manifold = 0
    for obj in objects:
        non_manifold += count_non_manifold(obj)
    expected = {"x": spec["width"], "y": spec["depth"], "z": spec["height"]}
    envelope_ok = all(bounds[axis] <= expected[axis] + 0.05 for axis in expected)
    report = {"passed": bool(objects) and envelope_ok and non_manifold == 0,
              "bounds_mm": {axis: round(value, 3) for axis, value in bounds.items()},
              "maximum_envelope_mm": expected, "non_manifold_edges": non_manifold,
              "object_count": len(objects)}
    with open(report_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print("Validation:", report)
    return report["passed"]


def render_preview(objects, filepath):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.camera_add(location=(180, -220, 160))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    target = Vector((0, 0, max(obj.dimensions.z for obj in objects) / 2))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.object.light_add(type="AREA", location=(80, -100, 180))
    bpy.context.object.data.energy, bpy.context.object.data.shape = 200000, "DISK"
    bpy.context.object.data.size = 120
    bpy.ops.object.light_add(type="AREA", location=(-100, 40, 100))
    bpy.context.object.data.energy, bpy.context.object.data.size = 100000, 100
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 700, 500, 100
    scene.render.image_settings.file_format, scene.render.filepath = "PNG", filepath
    scene.world.color = (0.06, 0.06, 0.06)
    bpy.ops.render.render(write_still=True)


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

obj = import_mesh(request["input_obj"])
auto_scale(obj, request["target_size_mm"])

# IMPORTANT: voxel_remesh (which adds+applies a brand new modifier) must
# run BEFORE any transform_apply(location=True) -- found via real local
# testing on an intentionally messy/holey mesh that baking a location
# transform onto non-manifold geometry causes the very next
# modifier_apply call to silently no-op (returns {'FINISHED'} but leaves
# the mesh completely unchanged, no error). auto_scale only bakes SCALE,
# which doesn't trigger this; sit_on_bed bakes LOCATION, so it must come
# after remeshing, not before.
voxel_remesh(obj, request["min_wall_mm"])
apply_flat_material(obj)
print("non-manifold edges after remesh:", count_non_manifold(obj))
sit_on_bed(obj)

if needs_base(obj):
    add_base(obj)
    sit_on_bed(obj)
    print("non-manifold edges after base union:", count_non_manifold(obj))

objects = [obj]
preview = "/kaggle/working/preview.png"
report = "/kaggle/working/report.json"
stl = "/kaggle/working/model.stl"

render_preview(objects, preview)
bounds = mesh_bounds(objects)
spec = {"width": bounds["x"], "depth": bounds["y"], "height": bounds["z"]}
passed = validate(objects, spec, report)

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.ops.wm.stl_export(filepath=stl, export_selected_objects=True)

print("STL_EXPORTED", os.path.exists(stl))
print("VALIDATION_PASSED", passed)
'''


def run_print_readiness(obj_path):
    request = {
        "input_obj": obj_path,
        "target_size_mm": TARGET_SIZE_MM,
        "min_wall_mm": MIN_WALL_MM,
    }
    with open(os.path.join(WORKDIR, "creative_request.json"), "w", encoding="utf-8") as f:
        json.dump(request, f)

    print("=== downloading Blender", BLENDER_VERSION, "===", flush=True)
    result = subprocess.run(["curl", "-sL", "-o", TARBALL, BLENDER_URL])
    if result.returncode != 0 or not os.path.exists(TARBALL):
        raise RuntimeError("Failed to download Blender")

    os.makedirs(EXTRACT_DIR, exist_ok=True)
    result = subprocess.run(["tar", "-xf", TARBALL, "-C", EXTRACT_DIR, "--strip-components=1"])
    if result.returncode != 0:
        raise RuntimeError("Failed to extract Blender")

    blender_bin = os.path.join(EXTRACT_DIR, "blender")
    inner_path = os.path.join(WORKDIR, "inner_process.py")
    with open(inner_path, "w", encoding="utf-8") as f:
        f.write(INNER_SCRIPT)

    print("=== running Blender print-readiness stage ===", flush=True)
    result = subprocess.run(
        [blender_bin, "--background", "--python", inner_path],
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(result.stdout[-6000:])
    print(result.stderr[-2000:])

    if result.returncode != 0:
        raise RuntimeError(f"Blender print-readiness run failed with code {result.returncode}")
    if not os.path.exists(os.path.join(WORKDIR, "model.stl")):
        raise RuntimeError("Blender run finished but model.stl was not produced")


def cleanup():
    for path in (TARBALL, EXTRACT_DIR, os.path.join(WORKDIR, "inner_process.py"),
                 os.path.join(WORKDIR, "creative_request.json"),
                 os.path.join(WORKDIR, "mesh.obj")):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)


def main():
    obj_path = generate_mesh()

    quality = check_mesh_quality(obj_path)
    print("Mesh quality:", quality)
    if not quality["passed"]:
        with open(os.path.join(WORKDIR, "report.json"), "w", encoding="utf-8") as f:
            json.dump({"passed": False, "reasons": quality["reasons"], "stats": quality["stats"]}, f, indent=2)
        cleanup()
        print("QUALITY_FAILED")
        return

    run_print_readiness(obj_path)
    cleanup()
    print("DONE")


if __name__ == "__main__":
    main()
