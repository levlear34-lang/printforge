"""Produce dimensions and fit rules from parsed requirements, not product names.

Vendored verbatim from AI_3D_FACTORY/app/modules/design_agent.py.
"""

DEFAULT_ITEM = {"width": 55.0, "depth": 35.0, "height": 90.0}


def design_model(model):
    item = dict(DEFAULT_ITEM)
    item.update(model.get("item_dimensions") or {})

    requirements = set(model.get("requirements", []))
    slots = max(1, int(model.get("slots") or 1))
    wall = float(
        model.get("wall_thickness")
        or (4 if "material_efficient" in requirements else 5)
    )
    clearance = float(model.get("clearance") or 2)
    model_type = model.get("model_type", "holder")

    angle = float(
        model.get("angle")
        if model.get("angle") is not None
        else (15 if model_type in ("holder", "stand") else 0)
    )

    slot_width = item["width"] + 2 * clearance
    width = slots * slot_width + (slots + 1) * wall
    depth = max(item["depth"] + 2 * clearance + wall * 2, 45.0)
    height = max(item["height"] + wall * 2, 45.0)

    if "small" in requirements and not model.get("item_dimensions"):
        width *= 0.85
        depth *= 0.85
        height *= 0.85

    if model_type == "organizer":
        height = max(item["height"] * 0.65, 35.0)
        angle = 0
    elif model_type in ("holder", "stand"):
        height = max(item["height"] * 0.8 + wall * 2, 55.0)

    return {
        "name": model.get("name", "item holder"),
        "model_type": model_type,
        "item_name": model.get("item_name", "item"),
        "width": round(width, 2),
        "depth": round(depth, 2),
        "height": round(height, 2),
        "wall_thickness": wall,
        "slots": slots,
        "angle": max(0.0, min(angle, 60.0)),
        "clearance": clearance,
        "item_dimensions": item,
        "fit_rules": {
            "slot_width": round(slot_width, 2),
            "minimum_wall": wall,
            "clearance": clearance,
        },
    }


# Safety floors below which a wall/clearance value stops being physically
# sensible regardless of which alternative is asking for less of it.
MIN_WALL = 2.0
MIN_CLEARANCE = 1.0


def _score_variant(design):
    """Heuristically score a design on four independent axes, each in [0, 1].

    These are deliberately simple proxies (not a physics simulation) meant to
    rank alternatives relative to each other for the same request, not to be
    an absolute quality measure.
    """
    item = design["item_dimensions"]
    wall = design["wall_thickness"]
    clearance = design["clearance"]
    width, depth, height = design["width"], design["depth"], design["height"]
    angle = design["angle"]

    ideal_clearance = max(1.5, min(item["width"], item["depth"]) * 0.04)
    fit_clearance = max(0.0, 1.0 - abs(clearance - ideal_clearance) / max(ideal_clearance, 1.0))

    wall_score = min(1.0, wall / 3.0) if wall < 3.0 else max(0.3, 1.0 - (wall - 3.0) / 6.0)
    overhang_score = max(0.0, 1.0 - max(0.0, angle - 45.0) / 45.0)
    printability = (wall_score + overhang_score) / 2

    footprint = width * depth
    aspect = footprint / max(height, 1.0)
    stability = min(1.0, aspect / 40.0) * max(0.3, 1.0 - angle / 90.0)

    slots = design.get("slots", 1)
    items_volume = item["width"] * item["depth"] * item["height"] * slots
    shell_volume_proxy = wall * (2 * (width * depth) + 2 * (width * height) + 2 * (depth * height))
    material_use = max(0.0, 1.0 - shell_volume_proxy / max(items_volume * 6, 1.0))

    scores = {
        "fit_clearance": round(fit_clearance, 3),
        "printability": round(printability, 3),
        "stability": round(stability, 3),
        "material_use": round(material_use, 3),
    }
    scores["total"] = round(sum(scores.values()) / len(scores), 3)
    return scores


def design_alternatives(model):
    """Produce 2-3 scored design alternatives (compact/stable/material_saving).

    Each is built by perturbing wall thickness and clearance around whatever
    design_model() resolved for the plain request, then re-running the same
    fit math -- so alternatives never drift from the request's explicit fit
    rules (angle, item dimensions) the way the base design wouldn't.
    """
    base = design_model(model)
    base_wall = base["wall_thickness"]
    base_clearance = base["clearance"]

    def variant(label, **overrides):
        request = dict(model)
        request.update(overrides)
        design = design_model(request)
        design["variant"] = label
        design["scores"] = _score_variant(design)
        return design

    alternatives = [
        variant("compact", clearance=max(MIN_CLEARANCE, round(base_clearance * 0.6, 2))),
        variant("stable", wall_thickness=round(base_wall * 1.5, 2)),
        variant(
            "material_saving",
            wall_thickness=max(MIN_WALL, round(base_wall * 0.7, 2)),
        ),
    ]
    alternatives.sort(key=lambda design: design["scores"]["total"], reverse=True)
    return alternatives
