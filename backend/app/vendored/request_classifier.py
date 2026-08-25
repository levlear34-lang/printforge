"""Classify a request as parametric (has explicit measurements) or creative.

Vendored from AI_3D_FACTORY/app/modules/request_classifier.py, with only the
import path adjusted (relative import within this package instead of the
original project's flat `modules` package).

Parametric requests carry measurable specs (mm dimensions, degrees, wall
thickness, clearance, an explicit slot/item count) and route to the existing
deterministic pipeline. Everything else -- vague or themed requests with no
measurable specs -- is creative and routes to the generative pipeline.

Reuses request_parser's own dimension/angle/wall/clearance extraction rather
than duplicating it, so those can't silently drift out of sync. The one
deliberate deviation is slot counting: request_parser also treats a bare
"N items" as a slot count (useful once a request is already known
parametric), but for classification that's too generic a signal -- "3 items"
shows up in creative requests too ("give me 3 items with a dragon theme") --
so only the more structural "slots"/"positions" wording counts here.
"""
from .request_parser import _extract_item_dimensions, _number_before

SLOT_COUNT_PATTERN = r"(\d+)\s*(?:slots?|positions?)"
ANGLE_PATTERN = r"(\d+(?:\.\d+)?)\s*(?:degree|degrees|°)"
WALL_PATTERN = r"(\d+(?:\.\d+)?)\s*mm\s*(?:walls?|wall thickness)"
CLEARANCE_PATTERN = r"(\d+(?:\.\d+)?)\s*mm\s*(?:clearance|gap)"


def classify_request(text):
    """Return "parametric" or "creative".

    A request with both explicit measurements and thematic language (e.g.
    "Batman phone holder, 70x12x150mm items") is classified parametric: the
    generative pipeline has no way to honor exact dimensions, so when real
    specs are present the deterministic pipeline is always the better fit.
    """
    lowered = text.lower()
    has_measurement = any(
        _number_before(lowered, [pattern], None) is not None
        for pattern in (SLOT_COUNT_PATTERN, ANGLE_PATTERN, WALL_PATTERN, CLEARANCE_PATTERN)
    )
    has_dimensions = _extract_item_dimensions(lowered) is not None
    return "parametric" if (has_measurement or has_dimensions) else "creative"
