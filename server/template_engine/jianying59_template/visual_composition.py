"""Whole-frame composition planning shared by stickers and flower text.

This module deliberately plans relationships, not a fixed ``four corners``
layout.  A template is a static 180-second poster: the upper/lower photo walls,
two text tracks and one sticker skin must read as one frame while the central
drama window stays clean.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualComposition:
    """A deterministic whole-frame composition for one template seed.

    ``relation`` is intentionally a small finite vocabulary.  It creates real
    variation without pretending that a local script can make an AI aesthetic
    judgement for every drama.  Geometry is later constrained by the actual
    central-window height and by the two text safe zones.
    """

    seed: int
    relation: str
    top_focus_side: int
    bottom_focus_side: int
    top_weight: str
    bottom_weight: str

    @property
    def pattern(self) -> str:
        return self.relation


def text_positions(*, composition: VisualComposition, central_window_boundary_ratio: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return text anchors wholly inside the upper/lower photo-wall bands.

    ``central_window_boundary_ratio`` is the actual normalized Y boundary of
    the central window (not half of it).  The old formula confused these two
    units, so a normal 0.71 boundary was treated as 0.35 and text could land in
    the black central window.  Text is horizontally centred as confirmed; the
    only controlled variation left is its safe vertical position and rotation.
    """
    if not 0.0 < central_window_boundary_ratio < 1.0:
        raise ValueError("central_window_boundary_ratio must be within (0, 1)")
    band = 1.0 - central_window_boundary_ratio
    if band < 0.12:
        raise ValueError("central window leaves no safe text band")
    rng = random.Random(f"{composition.seed}:flower-text-position")
    # Keep a conservative 50% of the available photo-wall band between the
    # anchor and the drama window.  Flower styles have a non-trivial visible
    # bounding box, so the anchor itself must not sit on the boundary.
    offset = rng.uniform(0.50, 0.74) * band
    blessing = (0.0, round(central_window_boundary_ratio + offset, 6))
    drama = (0.0, round(-central_window_boundary_ratio - offset, 6))
    return blessing, drama


def decide_visual_composition(*, seed: int) -> VisualComposition:
    """Choose a bounded, asymmetric relationship without runtime AI."""
    rng = random.Random(f"{seed}:template-visual-composition")
    relation = rng.choice((
        "diagonal_counterweight",
        "upper_frame_lower_response",
        "lower_support_upper_response",
        "edge_linked_flow",
    ))
    top_side = rng.choice((-1, 1))
    # The two walls may vary in visual weight, but their focal clusters must
    # answer diagonally.  Allowing a same-side pair made the template read as
    # two unrelated piles on one edge instead of one full-frame composition.
    bottom_side = -top_side
    top_weight = rng.choice(("main", "support"))
    bottom_weight = "support" if top_weight == "main" else "main"
    return VisualComposition(
        seed=seed,
        relation=relation,
        top_focus_side=top_side,
        bottom_focus_side=bottom_side,
        top_weight=top_weight,
        bottom_weight=bottom_weight,
    )
