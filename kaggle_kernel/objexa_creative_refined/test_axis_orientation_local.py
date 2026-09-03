"""Regression test for the OBJ-import axis-orientation fix in run.py's
import_mesh(). NOT part of the pytest suite (needs a real Blender install,
not just bpy) -- run manually with:

    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" ^
        --background --python kaggle_kernel/objexa_creative_refined/test_axis_orientation_local.py

Exists because the bug this guards against is easy to silently reintroduce:
if a future edit to import_mesh() drops the up_axis="Z" argument (e.g. during
a refactor, or by copying the fast tier's un-parameterized call by mistake),
nothing in the normal test suite or even a casual look at the diff would
catch it -- the kernel would still run successfully, still pass the mesh
quality/manifold checks, and just quietly produce sideways models again,
exactly like the real "standing Ciri figure" production bug this fixed.

Uses a synthetic OBJ (not a real Kaggle-downloaded mesh) so this runs free,
offline, in seconds -- no Kaggle quota, no network. It mimics the one
property of TripoSR's real output that actually matters here: the file's own
Z axis is its tallest, matching what a real retrieved TripoSR mesh showed
(bounding_box x=0.48/y=0.57/z=0.93 in the job that surfaced this bug).
A real end-to-end Kaggle run should still be used to confirm this against
actual TripoSR output before trusting a change to this file in production --
this test only proves the Blender-side axis handling itself is correct.
"""
import os
import tempfile

import bpy
from mathutils import Vector

# X=1 (narrowest), Y=1.5 (medium), Z=3 (tallest) in file coordinates --
# deliberately asymmetric on all three axes so any axis permutation or
# unwanted rotation is detectable, not just an up/down flip.
SYNTHETIC_OBJ = """\
v -0.5 -0.75 0.0
v 0.5 -0.75 0.0
v 0.5 0.75 0.0
v -0.5 0.75 0.0
v -0.5 -0.75 3.0
v 0.5 -0.75 3.0
v 0.5 0.75 3.0
v -0.5 0.75 3.0
f 1 2 3 4
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""


def import_mesh(path):
    """Verbatim copy of run.py's INNER_SCRIPT import_mesh() -- keep these
    two in sync. Kaggle "script" kernels must be single self-contained
    files (documented precedent in this repo -- see the fast/refined
    kernels' own duplicated print-readiness code), so this can't just
    import the real one.
    """
    bpy.ops.wm.obj_import(filepath=path, up_axis="Z", forward_axis="Y")
    imported = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if len(imported) > 1:
        bpy.context.view_layer.objects.active = imported[0]
        bpy.ops.object.join()
        imported = [bpy.context.view_layer.objects.active]
    return imported[0]


def world_bounds(obj):
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs, ys, zs = [c.x for c in corners], [c.y for c in corners], [c.z for c in corners]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def main():
    fd, path = tempfile.mkstemp(suffix=".obj")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(SYNTHETIC_OBJ)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    obj = import_mesh(path)
    x, y, z = world_bounds(obj)
    os.remove(path)

    print(f"RESULT bounds=({x:.3f}, {y:.3f}, {z:.3f})")

    assert z > x and z > y, (
        f"REGRESSION: expected Z to remain the tallest axis after import "
        f"(file was authored Z-tall, matching TripoSR's real convention), "
        f"got bounds ({x:.3f}, {y:.3f}, {z:.3f}) -- import_mesh() no longer "
        f"preserves orientation. Check up_axis/forward_axis in both this "
        f"file and run.py's INNER_SCRIPT."
    )
    print("PASSED: Z-tall orientation preserved through import_mesh().")


if __name__ == "__main__":
    main()
