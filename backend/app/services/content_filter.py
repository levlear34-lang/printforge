"""Basic keyword-based content filter for creation prompts.

Deliberately "basic," per the project spec -- this blocks clearly abusive
content (hate speech, sexual content, explicit violence) via a wordlist
match, not a trained classifier. It is not exhaustive and won't catch
creative evasion (leetspeak, spacing tricks, non-English slurs); a proper
moderation ML model or third-party API is future work if abuse becomes a
real problem in practice. The goal here is to stop the obvious cases
plainly and honestly, matching the spec's "reject with a clear message,
don't silently drop" requirement -- not to be a complete safety system.

Matching is whole-word (regex word boundaries) and case-insensitive, so it
doesn't false-positive on innocuous substrings (e.g. a slur that's also a
substring of an unrelated word).
"""
import re

# Deliberately modest starter lists, one per category the spec names.
# Extend these as real abuse patterns show up in practice -- not an attempt
# to be a complete/canonical list of every slur or explicit term.
_HATE_SPEECH_TERMS = [
    "nigger", "nigga", "faggot", "retard", "kike", "spic", "chink",
    "tranny", "subhuman",
]
_SEXUAL_CONTENT_TERMS = [
    "porn", "pornographic", "explicit sex", "sex toy", "dildo", "hentai",
    "nude child", "child porn", "cp",
]
_VIOLENCE_TERMS = [
    "behead", "beheading", "mass shooting", "school shooting", "genocide",
    "torture device", "suicide vest", "pipe bomb", "how to make a bomb",
]

_ALL_TERMS = _HATE_SPEECH_TERMS + _SEXUAL_CONTENT_TERMS + _VIOLENCE_TERMS
_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in _ALL_TERMS) + r")\b",
    re.IGNORECASE,
)


class ContentFilterError(Exception):
    """The prompt was rejected by the content filter."""


def check_prompt(text):
    match = _PATTERN.search(text or "")
    if match:
        raise ContentFilterError(
            "This request contains content we can't generate (hate speech, "
            "sexual content, or explicit violence). Please rephrase and "
            "try again."
        )
