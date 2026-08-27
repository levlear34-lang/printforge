"""Assemble a per-job copy of a Kaggle kernel template, ready to push.

Templates live in kaggle_kernel/<tier_key>/ at the repo root (sibling to
backend/, not inside it -- consistent with AI_3D_FACTORY's layout). Each
build call copies the template into a fresh temp directory, rewrites
kernel-metadata.json's id/title to the visitor's own username + a
job-scoped slug, and injects either the computed design spec (parametric)
or the raw prompt text (fast/refined creative tiers) as a literal in run.py.
"""
import json
import os
import re
import shutil
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
KERNEL_TEMPLATES_DIR = os.path.join(REPO_ROOT, "kaggle_kernel")

# T4 requested explicitly for every creative-tier push -- Kaggle's default
# GPU (P100) has a compute capability current PyTorch/diffusers wheels no
# longer support, the same real issue AI_3D_FACTORY's Shap-E/SD-TripoSR
# kernels already hit and documented. The parametric tier needs no GPU at
# all (pure geometry + a downloaded Blender binary), hence None.
TIERS = {
    "parametric": {
        "template_dir": os.path.join(KERNEL_TEMPLATES_DIR, "printforge_parametric"),
        "accelerator": None,
    },
    "fast": {
        "template_dir": os.path.join(KERNEL_TEMPLATES_DIR, "printforge_creative_fast"),
        "accelerator": "NvidiaTeslaT4",
    },
    "refined": {
        "template_dir": os.path.join(KERNEL_TEMPLATES_DIR, "printforge_creative_refined"),
        "accelerator": "NvidiaTeslaT4",
    },
    # Milestone 8: the opt-in "Advanced" prompt-refinement pre-processing
    # step. CPU-only on purpose -- text expansion doesn't need a GPU, and
    # skipping the accelerator means unlimited refinement rounds never
    # touch the same weekly GPU-hour quota the tiers above depend on.
    "refine": {
        "template_dir": os.path.join(KERNEL_TEMPLATES_DIR, "printforge_prompt_refiner"),
        "accelerator": None,
    },
}


def _slug(job_id):
    return re.sub(r"[^a-z0-9-]", "", f"printforge-{job_id}".lower())


def build_kernel(tier_key, job_id, username, spec=None, prompt=None, idea=None, feedback=None):
    """Copy the tier's template into a fresh temp dir, ready to `kaggle
    kernels push -p <returned dir>`. Returns (kernel_dir, kernel_id).
    """
    if tier_key not in TIERS:
        raise ValueError(f"Unknown kernel tier: {tier_key}")

    template_dir = TIERS[tier_key]["template_dir"]
    dest_dir = tempfile.mkdtemp(prefix="pf_kernel_")
    for name in os.listdir(template_dir):
        shutil.copy2(os.path.join(template_dir, name), os.path.join(dest_dir, name))

    kernel_id = f"{username}/{_slug(job_id)}"
    meta_path = os.path.join(dest_dir, "kernel-metadata.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["id"] = kernel_id
    meta["title"] = _slug(job_id)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    run_path = os.path.join(dest_dir, "run.py")
    with open(run_path, encoding="utf-8") as f:
        content = f.read()

    if spec is not None:
        content = content.replace(
            "SPEC_JSON = {}",
            f"SPEC_JSON = {json.dumps(spec)}",
        )
    if prompt is not None:
        content = re.sub(
            r'^PROMPT = ".*"$',
            lambda _match: f"PROMPT = {json.dumps(prompt)}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    if idea is not None:
        content = re.sub(
            r'^IDEA = ".*"$',
            lambda _match: f"IDEA = {json.dumps(idea)}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    if feedback is not None:
        content = re.sub(
            r'^FEEDBACK = ".*"$',
            lambda _match: f"FEEDBACK = {json.dumps(feedback)}",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    with open(run_path, "w", encoding="utf-8") as f:
        f.write(content)

    return dest_dir, kernel_id


def cleanup(kernel_dir):
    shutil.rmtree(kernel_dir, ignore_errors=True)
