"""Turn a compact natural-language request into general design requirements.

Vendored verbatim from AI_3D_FACTORY/app/modules/request_parser.py.
"""

import re


def _number_before(text, patterns, default=None, cast=float):
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return cast(match.group(1))
    return default


def parse_request(request):
    """Parse reusable fit, layout, and envelope requirements from text."""
    text = request.lower()
    item_name = _detect_item_name(text)
    slots = _number_before(
        text,
        [r"(\d+)\s*(?:slots?|items?|positions?)"],
        1,
        int,
    )
    angle = _number_before(
        text,
        [r"(\d+(?:\.\d+)?)\s*(?:degree|degrees|°)"],
        None,
    )
    wall = _number_before(
        text,
        [r"(\d+(?:\.\d+)?)\s*mm\s*(?:walls?|wall thickness)"],
        None,
    )
    clearance = _number_before(
        text,
        [r"(\d+(?:\.\d+)?)\s*mm\s*(?:clearance|gap)"],
        None,
    )
    dimensions = _extract_item_dimensions(text)

    if angle is None and any(
        word in text
        for word in ("tilt", "tilted", "angled", "toward me", "towards me")
    ):
        angle = 15.0

    requirements = []
    if any(word in text for word in ("small", "compact", "tiny")):
        requirements.append("small")
    if any(
        phrase in text
        for phrase in (
            "little material",
            "less material",
            "save material",
            "minimal material",
            "little pla",
            "less pla",
        )
    ):
        requirements.append("material_efficient")

    return {
        "name": f"{item_name} {detect_model_type(text)}",
        "item_name": item_name,
        "model_type": detect_model_type(text),
        "requirements": requirements,
        "slots": max(1, slots),
        "angle": angle,
        "wall_thickness": wall,
        "clearance": clearance,
        "item_dimensions": dimensions,
    }


def detect_model_type(text):
    if any(word in text for word in ("organizer", "organise", "organize", "tray")):
        return "organizer"
    if any(word in text for word in ("stand", "display", "dock")):
        return "stand"
    return "holder"


def _detect_item_name(text):
    known = (
        "controller",
        "phone",
        "headphones",
        "headset",
        "tablet",
        "book",
        "tool",
        "tools",
        "pen",
        "pens",
        "bottle",
    )
    for item in known:
        if re.search(rf"\b{item}\b", text):
            return item.rstrip("s")
    return "item"


def _extract_item_dimensions(text):
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm",
        text,
    )
    if not match:
        return None

    return {
        "width": float(match.group(1)),
        "depth": float(match.group(2)),
        "height": float(match.group(3)),
    }
