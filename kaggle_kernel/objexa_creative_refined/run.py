"""Objexa creative "refined" tier Kaggle kernel (Stable Diffusion -> TripoSR).

Pushed fresh under each visitor's own Kaggle account for each job (see
backend/app/services/kernel_builder.py, which rewrites PROMPT and
kernel-metadata.json's id/title before every push -- this file in the repo
is the template/source of truth).

Ported from AI_3D_FACTORY's
kaggle_kernel/sd_triposr_generator/generate_mesh_refined.py (the SD->TripoSR
generation itself, verbatim -- same transformers-pin workaround, same model
choices) plus app/modules/mesh_quality.py (the raw-mesh sanity check) plus
app/controllers/blender/process_creative_mesh.py (the print-readiness
stage, ported to a downloaded portable Blender the same way
objexa_creative_fast/run.py and objexa_parametric/run.py already
do). This file is deliberately a separate kernel/slot from
objexa_creative_fast/ -- the fast tier must keep working unmodified
regardless of what happens here, same discipline AI_3D_FACTORY's own two
kernels followed.

The print-readiness INNER_SCRIPT/mesh-quality-check code below is
duplicated from objexa_creative_fast/run.py rather than shared, since
Kaggle "script" kernels are pushed as a single self-contained file with no
sibling-module imports -- the same constraint that already applies to
objexa_parametric/run.py. Keep both in sync if that logic changes.
"""
import json
import os
import re
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

TRIPOSR_DIR = os.path.join(WORKDIR, "TripoSR")

# Rewritten by kernel_builder.py before each push.
PROMPT = "a spooky haunted castle"

SD_MODEL = "CompVis/stable-diffusion-v1-4"
TRIPOSR_MODEL = "stabilityai/TripoSR"
MC_RESOLUTION = 256
FOREGROUND_RATIO = 0.85

TARGET_SIZE_MM = 80.0
MIN_WALL_MM = 1.5

MIN_VERTICES = 100
MIN_FACES = 100
MIN_DIMENSION = 0.3
MAX_DIMENSION = 5.0
MIN_VOLUME = 0.005

# Stable Diffusion 1.4's CLIP text encoder hard-caps at 77 tokens (2 of which
# are the BOS/EOS special tokens CLIP always adds) and silently drops
# anything past that -- no error, no truncation warning from the library
# itself. Found via a real production bug: the Advanced-mode AI prompt
# refiner produces long, detailed prompts *by design* (that's the whole
# point of Milestone 8's refinement feature), and a 120-token refined prompt
# for a "standing Ciri figure... sword drawn... stable flat base..." lost
# its entire back half above the ~68-70 word/token mark -- including the
# base-stability and scale guidance -- with nothing in the kernel or the
# job's result surfacing that it happened. This isn't specific to
# AI-refined prompts either: Quick mode can also send an arbitrarily long
# creative prompt straight to the refined tier, so the fix lives here, at
# the actual point of use, not upstream in the shared prompt-refiner kernel.
CLIP_MAX_TOKENS = 77
CLIP_SPECIAL_TOKENS = 2
CONCEPT_IMAGE_SUFFIX = ", 3d asset, product photo, single object, centered, plain background"


def fit_prompt_to_token_budget(prompt, suffix, count_tokens, max_tokens=CLIP_MAX_TOKENS, special_tokens=CLIP_SPECIAL_TOKENS):
    """Fit `prompt` + `suffix` inside a hard token budget, truncating `prompt`
    (never `suffix` -- it's short and carries generation-quality guidance
    rembg/TripoSR depend on, e.g. "single object, centered", so it must
    survive intact) at a sentence boundary where possible.

    `count_tokens` is injected (a real CLIP tokenizer at runtime, a cheap
    stand-in in tests) specifically so this algorithm -- the part that's
    actually easy to get subtly wrong (off-by-one budget math, cutting
    mid-word, dropping the suffix) -- can be unit tested without needing the
    real ~1.7GB CLIP tokenizer available in a fast, offline test suite.

    Returns (full_prompt_with_suffix, was_truncated, prompt_portion_used).
    """
    budget = max_tokens - special_tokens - count_tokens(suffix)
    if budget <= 0:
        # Degenerate case (suffix alone doesn't fit) -- not expected in
        # practice given how short CONCEPT_IMAGE_SUFFIX is, but fail safe
        # rather than send a negative-budget prompt to the tokenizer.
        return suffix.lstrip(", "), True, ""

    if count_tokens(prompt) <= budget:
        return f"{prompt}{suffix}", False, prompt

    sentences = re.split(r"(?<=[.!?])\s+", prompt.strip())
    kept = ""
    for sentence in sentences:
        candidate = f"{kept} {sentence}".strip() if kept else sentence
        if count_tokens(candidate) > budget:
            break
        kept = candidate

    if not kept:
        # Not even one full sentence fits (e.g. one long run-on sentence) --
        # fall back to a word boundary instead of an arbitrary token cut, so
        # the result is still readable text, not a chopped-off half-word.
        for word in prompt.split():
            candidate = f"{kept} {word}".strip() if kept else word
            if count_tokens(candidate) > budget:
                break
            kept = candidate

    return f"{kept}{suffix}", True, kept


def _pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=True)


def generate_mesh():
    if not os.path.exists(TRIPOSR_DIR):
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/VAST-AI-Research/TripoSR.git", TRIPOSR_DIR],
            check=True,
        )
    requirements_path = f"{TRIPOSR_DIR}/requirements.txt"
    with open(requirements_path) as f:
        lines = [line for line in f if not line.strip().lower().startswith("transformers")]
    filtered_requirements_path = os.path.join(WORKDIR, "triposr_requirements_filtered.txt")
    with open(filtered_requirements_path, "w") as f:
        f.writelines(lines)

    _pip(
        "-r", filtered_requirements_path,
        "diffusers", "transformers", "accelerate", "safetensors", "onnxruntime",
    )

    sys.path.insert(0, TRIPOSR_DIR)

    import numpy as np
    import rembg
    import torch
    from diffusers import StableDiffusionPipeline
    from PIL import Image
    from tsr.system import TSR
    from tsr.utils import remove_background, resize_foreground

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    print(f"Prompt: {PROMPT}")

    print("Generating concept image with Stable Diffusion...")
    pipe = StableDiffusionPipeline.from_pretrained(
        SD_MODEL, torch_dtype=torch.float16 if device == "cuda" else torch.float32
    )
    pipe = pipe.to(device)

    count_tokens = lambda text: len(pipe.tokenizer(text, truncation=False)["input_ids"])
    full_prompt, was_truncated, prompt_used = fit_prompt_to_token_budget(PROMPT, CONCEPT_IMAGE_SUFFIX, count_tokens)
    if was_truncated:
        print(
            f"WARNING: prompt is {count_tokens(PROMPT)} CLIP tokens, over the "
            f"{CLIP_MAX_TOKENS}-token budget -- truncated to fit. "
            f"Used: {prompt_used!r}"
        )

    negative_prompt = "multiple objects, cropped, blurry, text, watermark, collage"
    image = pipe(full_prompt, negative_prompt=negative_prompt, num_inference_steps=30).images[0]
    del pipe
    if device == "cuda":
        torch.cuda.empty_cache()
    image.save(os.path.join(WORKDIR, "concept.png"))

    print("Reconstructing mesh with TripoSR...")
    model = TSR.from_pretrained(TRIPOSR_MODEL, config_name="config.yaml", weight_name="model.ckpt")
    model.renderer.set_chunk_size(8192)
    model.to(device)

    rembg_session = rembg.new_session()
    clean_image = remove_background(image, rembg_session)
    clean_image = resize_foreground(clean_image, FOREGROUND_RATIO)
    clean_image = np.array(clean_image).astype(np.float32) / 255.0
    clean_image = clean_image[:, :, :3] * clean_image[:, :, 3:4] + (1 - clean_image[:, :, 3:4]) * 0.5
    clean_image = Image.fromarray((clean_image * 255.0).astype(np.uint8))

    with torch.no_grad():
        scene_codes = model([clean_image], device=device)
    meshes = model.extract_mesh(scene_codes, True, resolution=MC_RESOLUTION)

    obj_path = os.path.join(WORKDIR, "mesh.obj")
    meshes[0].export(obj_path)
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
    # up_axis="Z", forward_axis="Y" is NOT Blender's default for wm.obj_import
    # (which is up_axis="Y") -- it's deliberate and load-bearing. Found via a
    # real production bug: a "standing Ciri figure, sword drawn, ~120mm tall"
    # prompt came back as a collapsed/lying-down blob despite passing
    # validation. Root cause, confirmed by comparing the raw TripoSR mesh's
    # own bounding box (tallest along its file-Z, e.g. 0.48/0.57/0.93) against
    # the final exported STL (tallest along Y at 83mm, Z shrunk to 47mm) --
    # not a scaling artifact, a genuine axis reassignment. TripoSR's raw .obj
    # output does not follow the Wavefront OBJ format's own Y-up convention;
    # it's already Z-up (matching Blender's native convention). Blender's
    # default silently assumes standard OBJ Y-up and "corrects" for it,
    # rotating an already-correct mesh onto its side. Verified locally with a
    # synthetic asymmetric test box before touching this file (not guessed):
    # bpy.ops.wm.obj_import(filepath=path) with no args reproduces the exact
    # bug pattern (file-Z-tall -> Blender-Y-tall, rot_euler 90 deg about X);
    # up_axis="Z" (any forward_axis) keeps file-Z-tall as Blender-Z-tall with
    # zero rotation applied, i.e. treats the file as already being in
    # Blender's own convention, which is what it actually is. See
    # test_axis_orientation_local.py (same directory) for a repeatable,
    # Kaggle-free regression check of this exact behavior -- rerun it if this
    # function or the Blender version ever changes.
    bpy.ops.wm.obj_import(filepath=path, up_axis="Z", forward_axis="Y")
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
                 os.path.join(WORKDIR, "mesh.obj"), TRIPOSR_DIR,
                 os.path.join(WORKDIR, "concept.png"),
                 os.path.join(WORKDIR, "triposr_requirements_filtered.txt")):
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
