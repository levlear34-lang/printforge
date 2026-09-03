"""Tests for kaggle_kernel/objexa_creative_refined/run.py's
fit_prompt_to_token_budget() -- the fix for a real production bug where a
120-token AI-refined prompt got silently truncated by Stable Diffusion's
77-token CLIP limit, losing guidance (base stability, target scale) that
never reached the image model, no warning surfaced anywhere.

Imports the actual kernel file directly rather than duplicating the
function here: unlike the Blender-side axis-orientation fix (which needs a
real Blender/bpy environment a plain pytest run doesn't have), this
function has zero heavy dependencies at module level -- run.py only imports
torch/diffusers/tsr/bpy *inside* generate_mesh()'s body, deferred until
that function actually runs on Kaggle. So the real, shipped kernel code is
what gets tested here, not a copy that could quietly drift from it.
"""
import importlib.util
import os

import pytest

KERNEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "kaggle_kernel", "objexa_creative_refined", "run.py"
)


def _load_kernel_module():
    spec = importlib.util.spec_from_file_location("objexa_creative_refined_run", KERNEL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kernel = _load_kernel_module()


def _word_count_tokens(text):
    """Stand-in for CLIP's real tokenizer -- deliberately a different (and
    cruder) counting scheme than real subword tokenization, so a passing
    test proves the *algorithm* (budget math, sentence/word-boundary
    truncation, suffix preservation) is correct in general, not tuned to
    CLIP's specific token boundaries.
    """
    return len(text.split())


def test_short_prompt_is_not_truncated():
    prompt = "a small dragon figurine"
    full, was_truncated, used = kernel.fit_prompt_to_token_budget(
        prompt, kernel.CONCEPT_IMAGE_SUFFIX, _word_count_tokens, max_tokens=77, special_tokens=2
    )
    assert was_truncated is False
    assert used == prompt
    assert full == prompt + kernel.CONCEPT_IMAGE_SUFFIX


def test_long_prompt_is_truncated_at_a_sentence_boundary():
    first_sentence = "Create a standing figure holding a sword."
    prompt = (
        f"{first_sentence} "
        "She stands on a stable flat base. "
        "The structure should measure approximately 120mm tall."
    )
    # Budget sized to fit exactly the first sentence (7 tokens) and no more,
    # once the suffix's own token cost is reserved.
    budget = _word_count_tokens(first_sentence)
    max_tokens = budget + 2 + _word_count_tokens(kernel.CONCEPT_IMAGE_SUFFIX)

    full, was_truncated, used = kernel.fit_prompt_to_token_budget(
        prompt, kernel.CONCEPT_IMAGE_SUFFIX, _word_count_tokens, max_tokens=max_tokens, special_tokens=2
    )
    assert was_truncated is True
    assert used == first_sentence
    # The suffix must survive intact even when the prompt was cut.
    assert full.endswith(kernel.CONCEPT_IMAGE_SUFFIX)


def test_truncation_never_drops_the_suffix():
    prompt = "word " * 200  # absurdly long, guarantees truncation
    full, was_truncated, used = kernel.fit_prompt_to_token_budget(
        prompt, kernel.CONCEPT_IMAGE_SUFFIX, _word_count_tokens, max_tokens=77, special_tokens=2
    )
    assert was_truncated is True
    assert full.endswith(kernel.CONCEPT_IMAGE_SUFFIX)


def test_run_on_sentence_with_no_period_falls_back_to_word_boundary():
    prompt = "a " * 50 + "figure"  # one long sentence, no punctuation at all
    full, was_truncated, used = kernel.fit_prompt_to_token_budget(
        prompt, kernel.CONCEPT_IMAGE_SUFFIX, _word_count_tokens, max_tokens=15, special_tokens=2
    )
    assert was_truncated is True
    assert used  # fell back to a real word-boundary truncation, not empty
    assert not used.endswith(" ")


def test_prompt_fitting_exactly_within_budget_is_not_marked_truncated():
    prompt = "one two three four five"
    suffix = ", six seven"
    budget = 10 - 2 - _word_count_tokens(suffix)
    assert _word_count_tokens(prompt) == budget  # test premise: fits exactly

    full, was_truncated, used = kernel.fit_prompt_to_token_budget(
        prompt, suffix, _word_count_tokens, max_tokens=10, special_tokens=2
    )
    assert was_truncated is False
    assert used == prompt


def test_degenerate_case_suffix_alone_exceeds_budget():
    full, was_truncated, used = kernel.fit_prompt_to_token_budget(
        "anything", kernel.CONCEPT_IMAGE_SUFFIX, _word_count_tokens, max_tokens=3, special_tokens=2
    )
    assert was_truncated is True
    assert used == ""


@pytest.mark.parametrize("prompt", ["", "a"])
def test_handles_trivial_prompts_without_crashing(prompt):
    full, was_truncated, used = kernel.fit_prompt_to_token_budget(
        prompt, kernel.CONCEPT_IMAGE_SUFFIX, _word_count_tokens, max_tokens=77, special_tokens=2
    )
    assert isinstance(full, str)
