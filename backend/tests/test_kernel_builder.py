from app.services import kernel_builder


def test_build_kernel_parametric_injects_spec():
    kernel_dir, kernel_id = kernel_builder.build_kernel(
        "parametric", "abc123", "testuser", spec={"model_type": "stand", "width": 100}
    )
    try:
        with open(f"{kernel_dir}/run.py", encoding="utf-8") as f:
            content = f.read()
        assert '"model_type": "stand"' in content
        assert kernel_id == "testuser/printforge-abc123"
    finally:
        kernel_builder.cleanup(kernel_dir)


def test_build_kernel_creative_injects_prompt():
    kernel_dir, kernel_id = kernel_builder.build_kernel(
        "fast", "abc123", "testuser", prompt="a spooky Batman phone holder"
    )
    try:
        with open(f"{kernel_dir}/run.py", encoding="utf-8") as f:
            content = f.read()
        assert 'PROMPT = "a spooky Batman phone holder"' in content
    finally:
        kernel_builder.cleanup(kernel_dir)


def test_build_kernel_prompt_injection_handles_quotes_and_backslashes():
    """Regression guard for the exact backslash-mangling bug AI_3D_FACTORY's
    kaggle_generator.write_prompt hit -- re.sub's *string* replacement form
    reinterprets backslash escapes; using a replacement function avoids it.
    """
    tricky = 'a "quoted" \\ prompt'
    kernel_dir, kernel_id = kernel_builder.build_kernel("refined", "xyz789", "testuser", prompt=tricky)
    try:
        with open(f"{kernel_dir}/run.py", encoding="utf-8") as f:
            content = f.read()
        namespace = {}
        for line in content.splitlines():
            if line.startswith("PROMPT = "):
                exec(line, namespace)
                break
        assert namespace["PROMPT"] == tricky
    finally:
        kernel_builder.cleanup(kernel_dir)


def test_tiers_have_expected_accelerators():
    assert kernel_builder.TIERS["parametric"]["accelerator"] is None
    assert kernel_builder.TIERS["fast"]["accelerator"] == "NvidiaTeslaT4"
    assert kernel_builder.TIERS["refined"]["accelerator"] == "NvidiaTeslaT4"
    # CPU-only on purpose -- see refine tier's docstring in kernel_builder.py.
    assert kernel_builder.TIERS["refine"]["accelerator"] is None


def test_build_kernel_refine_injects_idea_and_feedback():
    kernel_dir, kernel_id = kernel_builder.build_kernel(
        "refine", "xyz789", "testuser", idea="a batman phone holder", feedback="make it more armored"
    )
    try:
        with open(f"{kernel_dir}/run.py", encoding="utf-8") as f:
            content = f.read()
        assert 'IDEA = "a batman phone holder"' in content
        assert 'FEEDBACK = "make it more armored"' in content
    finally:
        kernel_builder.cleanup(kernel_dir)


def test_build_kernel_refine_round_one_has_empty_feedback():
    kernel_dir, kernel_id = kernel_builder.build_kernel(
        "refine", "abc111", "testuser", idea="a dragon figurine", feedback=""
    )
    try:
        with open(f"{kernel_dir}/run.py", encoding="utf-8") as f:
            content = f.read()
        assert 'FEEDBACK = ""' in content
    finally:
        kernel_builder.cleanup(kernel_dir)
