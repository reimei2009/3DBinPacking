"""Fixture-only Level 6 external feasibility policy for nesting compounds."""

from __future__ import annotations

from typing import Any

from ..schemas import Item
from .level_05_algorithms import LoadBearingFeasibilityPolicy, build_level_05_feasibility_policy


def build_level_06_compound_fixture_policy(
    compound_items: list[Item], config: dict[str, Any]
) -> LoadBearingFeasibilityPolicy:
    """Reuse the active Level 5 external policy on projected compound roots.

    Nested children are absent from the candidate list by design. Their weight
    and effective chain height are already represented by their root compound.
    The independent compound validator remains the acceptance authority.
    """
    # Delayed imports avoid a module cycle with the Level 5 pipeline while
    # allowing this fixture factory to accept the normal unresolved YAML config.
    from .level_04_pipeline import _rules as stackability_rules
    from .level_05_pipeline import load_bearing_rules

    stackability_rules(config)
    load_bearing_rules(config)
    return build_level_05_feasibility_policy(
        compound_items,
        config,
        support_policy_id="level_06_compound_geometry_payload_exact_support",
        policy_id="level_06_compound_geometry_payload_exact_support_stackability_load_bearing",
    )
