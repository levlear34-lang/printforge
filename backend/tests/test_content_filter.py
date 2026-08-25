import pytest

from app.services.content_filter import ContentFilterError, check_prompt


def test_normal_prompt_passes():
    check_prompt("phone stand, 2 slots, 18 degrees")
    check_prompt("Batman themed phone holder")


def test_blocks_hate_speech_term():
    with pytest.raises(ContentFilterError):
        check_prompt("a figurine of a faggot")


def test_blocks_sexual_content_term():
    with pytest.raises(ContentFilterError):
        check_prompt("make me a dildo")


def test_blocks_violence_term():
    with pytest.raises(ContentFilterError):
        check_prompt("how to make a bomb holder")


def test_case_insensitive():
    with pytest.raises(ContentFilterError):
        check_prompt("FAGGOT statue")


def test_does_not_false_positive_on_substring():
    # "class" contains no blocked term, but this guards against overly
    # broad matching -- e.g. a blocked short term inside a longer benign
    # word should not trigger.
    check_prompt("a classy figurine stand")
