"""Ambiguity detection and resolution module — public API."""
from __future__ import annotations

from core.domain.ambiguity import AmbiguityResolution
from modules.ambiguity.detector import detect_ambiguities
from modules.ambiguity.resolver import get_baseline_options


def enrich_description(description: str, resolutions: list[AmbiguityResolution]) -> str:
    """Append a Clarifications block to a description string.

    If resolutions is empty, returns the original description unchanged.
    The block format is already understood by the detector prompt — phrases
    covered by a Clarifications block are never re-flagged.

    Example output:
        Alert if customer sends significant amount to Iran recently

        Clarifications:
        - "significant amount" → > $5,000
        - "recently" → within the last 30 days
    """
    if not resolutions:
        return description
    lines = ["\n\nClarifications:"]
    for r in resolutions:
        lines.append(f'- "{r.phrase}" → {r.resolved_text}')
    return description + "\n".join(lines)


__all__ = ["detect_ambiguities", "enrich_description", "get_baseline_options"]
