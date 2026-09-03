"""Objexa "Advanced" pre-processing kernel: expands a vague creative idea
(or applies a requested change to a previous round's output) into a single,
detailed, generation-ready prompt for the existing fast/refined 3D kernels.

Pushed fresh under each visitor's own Kaggle account for each refinement
round (see backend/app/services/kernel_builder.py, which rewrites IDEA/
FEEDBACK and kernel-metadata.json's id/title before every push -- this file
in the repo is the template/source of truth).

Model choice: Qwen/Qwen2.5-1.5B-Instruct (Apache 2.0, ungated, ~2.4GB).
Deliberately small and CPU-only -- text expansion doesn't need a GPU, and
running this step without one means unlimited refinement rounds never touch
the same weekly GPU-hour quota the 3D-generation tiers depend on. Verified
this is fast enough in practice on Kaggle's free CPU tier (see this
kernel's manual verification notes in CLAUDE.md) rather than assumed --
same discipline as every other kernel in this project. accelerator: None
in kernel_builder.py's TIERS registry, same as the parametric tier's
Blender-only kernel, which established that a CPU-only Kaggle kernel is a
proven, working pattern here.
"""
import json
import subprocess
import sys

WORKDIR = "/kaggle/working"
MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"

# Rewritten by kernel_builder.py before each push. IDEA is either the
# visitor's original raw idea (round 1) or the previous round's accepted
# refined_prompt (round 2+); FEEDBACK is empty on round 1, else the
# visitor's requested change ("make it more X").
IDEA = "batman phone holder"
FEEDBACK = ""

MIN_LENGTH = 20
MAX_NEW_TOKENS = 220

SYSTEM_PROMPT = (
    "You expand short, vague 3D-print object ideas into a single detailed "
    "generation prompt for a text-to-3D AI pipeline. Describe the object's "
    "overall shape, pose or orientation, style, proportions, and any details "
    "that improve print quality -- a stable flat base, no thin protruding "
    "parts, a clear and simple silhouette. Reply with ONLY the refined "
    "prompt itself, as one paragraph of plain text -- no quotes, no "
    "markdown, no explanation, no preamble."
)


def _pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=True)


def refine_prompt():
    _pip("transformers", "accelerate")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"Idea: {IDEA!r}")
    print(f"Feedback: {FEEDBACK!r}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float32)
    model.eval()

    if FEEDBACK.strip():
        user_prompt = (
            f'Current prompt: "{IDEA}"\n\n'
            f'Requested change: "{FEEDBACK}"\n\n'
            "Rewrite the prompt to incorporate this change, keeping "
            "everything else about the object consistent."
        )
    else:
        user_prompt = f'Object idea: "{IDEA}"\n\nExpand this into a detailed generation prompt.'

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")

    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated = output[0][inputs["input_ids"].shape[1]:]
    result = tokenizer.decode(generated, skip_special_tokens=True).strip()
    # The model sometimes wraps its answer in quotes despite instructions
    # not to -- strip them so the frontend doesn't display a doubly-quoted
    # prompt back to the visitor.
    return result.strip('"').strip()


def main():
    refined = refine_prompt()
    print("Refined prompt:", refined)

    passed = len(refined) >= MIN_LENGTH
    report = {"passed": passed, "refined_prompt": refined}
    if not passed:
        report["reason"] = f"Model output too short/empty ({len(refined)} chars)."

    with open(f"{WORKDIR}/report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("DONE" if passed else "REFINE_FAILED")


if __name__ == "__main__":
    main()
