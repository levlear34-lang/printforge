"""PrintForge parametric-generation Kaggle kernel.

Pushed fresh under each visitor's own Kaggle account for each job (see
backend/app/services/kernel_builder.py, which rewrites SPEC_JSON and
kernel-metadata.json's id/title before every push -- this file in the repo
is the template/source of truth).

Why this downloads a real portable Blender build instead of `pip install
bpy`: verified via a real Kaggle run (not assumed) that Kaggle's kernel
image runs Python 3.12, while every bpy PyPI wheel targets either 3.11 (up
to Blender 5.0) or 3.13 (5.2.1+) -- there is no 3.12 build, so `pip install
bpy` fails outright on Kaggle's current image with "no matching
distribution." A downloaded portable Blender binary sidesteps this
entirely: Blender bundles its own Python, so it never touches the kernel's
system Python or that version mismatch, and this is the same "run Blender
headless via subprocess" approach AI_3D_FACTORY already uses locally
(blender_runner.py), just against a Linux tarball instead of a local
Windows install.

The design spec (width/height/slots/etc.) is computed by the backend
BEFORE this kernel is pushed, using the same vendored request_parser.py /
design_agent.py logic as everywhere else in this project -- that's pure
Python math with no Blender/GPU dependency, so running it backend-side
(cheap, instant, testable without burning any Kaggle quota) rather than
duplicating it inside Blender's separate bundled Python interpreter is a
deliberate simplification, not a shortcut around the "parsing/design runs
in a Kaggle kernel" architecture goal -- that goal was about not requiring
a *local Blender install*, which this still fully satisfies. Documented in
CLAUDE.md.
"""
import json
import os
import shutil
import subprocess
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
SPEC_JSON = {}

INNER_SCRIPT = r'''
import bpy
import bmesh
import json
import math
import os
from mathutils import Vector

with open("/kaggle/working/spec.json", encoding="utf-8") as f:
    spec = json.load(f)


def create_box(name, location, dimensions, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def slot_centers(spec):
    width, wall, slots = float(spec["width"]), float(spec["wall_thickness"]), int(spec["slots"])
    slot_width = float(spec["fit_rules"]["slot_width"])
    used_width = slots * slot_width + (slots + 1) * wall
    start = -used_width / 2 + wall + slot_width / 2
    return [start + index * (slot_width + wall) for index in range(slots)]


def create_organizer(spec):
    width, depth, height, wall = (float(spec[key]) for key in ("width", "depth", "height", "wall_thickness"))
    base = wall
    create_box("base", (0, 0, base / 2), (width, depth, base))
    create_box("left_wall", (-width / 2 + wall / 2, 0, height / 2), (wall, depth, height))
    create_box("right_wall", (width / 2 - wall / 2, 0, height / 2), (wall, depth, height))
    create_box("back_wall", (0, depth / 2 - wall / 2, height / 2), (width, wall, height))
    create_box("front_wall", (0, -depth / 2 + wall / 2, height / 2), (width, wall, height))
    for index, left_x in enumerate(slot_centers(spec)[:-1]):
        divider_x = left_x + float(spec["fit_rules"]["slot_width"]) / 2 + wall / 2
        create_box(f"divider_{index + 1}", (divider_x, 0, height / 2), (wall, depth - 2 * wall, height))


def create_tilted_back(spec, name):
    width, depth, height, wall = (float(spec[key]) for key in ("width", "depth", "height", "wall_thickness"))
    base = wall
    angle = math.radians(float(spec["angle"]))
    support_height = max(wall * 3, (height - base - wall * abs(math.sin(angle))) / max(math.cos(angle), 0.1))
    y_reach = support_height / 2 * abs(math.sin(angle)) + wall / 2 * abs(math.cos(angle))
    z_reach = support_height / 2 * abs(math.cos(angle)) + wall / 2 * abs(math.sin(angle))
    return create_box(name, (0, depth / 2 - y_reach, base + z_reach), (width, wall, support_height), (angle, 0, 0))


def create_holder(spec):
    width, depth, wall = (float(spec[key]) for key in ("width", "depth", "wall_thickness"))
    base = wall
    create_box("base", (0, 0, base / 2), (width, depth, base))
    create_tilted_back(spec, "tilted_back")
    item_depth = float(spec["item_dimensions"]["depth"])
    lip_height = max(wall * 2, min(item_depth * 0.35, 24))
    lip_depth = max(wall * 1.5, min(item_depth * 0.3, depth * 0.25))
    for index, x in enumerate(slot_centers(spec)):
        create_box(f"front_lip_{index + 1}", (x, -depth / 2 + lip_depth / 2, base + lip_height / 2),
                   (float(spec["fit_rules"]["slot_width"]), lip_depth, lip_height))
    _add_slot_guides(spec, max(lip_height * 1.5, wall * 3), depth - lip_depth - wall)


def create_stand(spec):
    width, depth, wall = (float(spec[key]) for key in ("width", "depth", "wall_thickness"))
    base = wall
    create_box("base", (0, 0, base / 2), (width, depth, base))
    create_tilted_back(spec, "tilted_back")
    lip_height, lip_depth = wall * 2, max(wall * 2, depth * 0.16)
    for index, x in enumerate(slot_centers(spec)):
        create_box(f"retaining_lip_{index + 1}", (x, -depth / 2 + lip_depth / 2, base + lip_height / 2),
                   (float(spec["fit_rules"]["slot_width"]), lip_depth, lip_height))
    _add_slot_guides(spec, wall * 4, depth - lip_depth - wall)


def _add_slot_guides(spec, guide_height, guide_depth):
    wall = float(spec["wall_thickness"])
    for index, center in enumerate(slot_centers(spec)[:-1]):
        x = center + float(spec["fit_rules"]["slot_width"]) / 2 + wall / 2
        create_box(f"slot_guide_{index + 1}", (x, -wall / 2, wall + guide_height / 2), (wall, guide_depth, guide_height))


def mesh_bounds(objects):
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return {axis: max(getattr(point, axis) for point in points) - min(getattr(point, axis) for point in points) for axis in ("x", "y", "z")}


def validate(objects, spec, report_path):
    bpy.context.view_layer.update()
    bounds = mesh_bounds(objects)
    non_manifold = 0
    for obj in objects:
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        non_manifold += sum(1 for edge in mesh.edges if not edge.is_manifold)
        mesh.free()
    expected = {"x": float(spec["width"]), "y": float(spec["depth"]), "z": float(spec["height"])}
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

generators = {"organizer": create_organizer, "holder": create_holder, "stand": create_stand}
generators[spec["model_type"]](spec)
objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]

preview = "/kaggle/working/preview.png"
report = "/kaggle/working/report.json"
stl = "/kaggle/working/model.stl"

render_preview(objects, preview)
passed = validate(objects, spec, report)

bpy.ops.object.select_all(action="DESELECT")
for obj in objects:
    obj.select_set(True)
# Verified via a real Kaggle run (not assumed): the older addon-based
# export_mesh.stl operator that AI_3D_FACTORY's local Blender 5.2.0 LTS
# still has is gone in the 5.2.1 build Kaggle downloads -- "could not be
# found". wm.stl_export (the newer built-in exporter) exists on both
# versions, confirmed locally, so it's the version-safe choice here.
bpy.ops.wm.stl_export(filepath=stl, export_selected_objects=True)

print("STL_EXPORTED", os.path.exists(stl))
print("VALIDATION_PASSED", passed)
'''


def main():
    with open(os.path.join(WORKDIR, "spec.json"), "w", encoding="utf-8") as f:
        json.dump(SPEC_JSON, f)

    print("=== downloading Blender", BLENDER_VERSION, "===", flush=True)
    t0 = time.time()
    result = subprocess.run(["curl", "-sL", "-o", TARBALL, BLENDER_URL])
    if result.returncode != 0 or not os.path.exists(TARBALL):
        raise RuntimeError("Failed to download Blender")
    print("download took", round(time.time() - t0, 1), "s", flush=True)

    os.makedirs(EXTRACT_DIR, exist_ok=True)
    result = subprocess.run(["tar", "-xf", TARBALL, "-C", EXTRACT_DIR, "--strip-components=1"])
    if result.returncode != 0:
        raise RuntimeError("Failed to extract Blender")

    blender_bin = os.path.join(EXTRACT_DIR, "blender")
    inner_path = os.path.join(WORKDIR, "inner_generate.py")
    with open(inner_path, "w", encoding="utf-8") as f:
        f.write(INNER_SCRIPT)

    print("=== running Blender --background ===", flush=True)
    result = subprocess.run(
        [blender_bin, "--background", "--python", inner_path],
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(result.stdout[-6000:])
    print(result.stderr[-2000:])

    if result.returncode != 0:
        raise RuntimeError(f"Blender run failed with code {result.returncode}")
    if not os.path.exists(os.path.join(WORKDIR, "model.stl")):
        raise RuntimeError("Blender run finished but model.stl was not produced")

    # Everything left in /kaggle/working becomes kernel "output" -- without
    # this cleanup, the ~380MB downloaded Blender tarball and its fully
    # extracted install (thousands of files) would be included in every
    # retrieval alongside the 3 files we actually want. Verified via a real
    # run that skipping this makes `kaggle kernels output` take long enough
    # to blow past a 120s client-side timeout, not just "a bit slower".
    for path in (TARBALL, EXTRACT_DIR, inner_path, os.path.join(WORKDIR, "spec.json")):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)

    print("DONE")


if __name__ == "__main__":
    main()
