"""Dataclasses representing detected and resolved ambiguities in a rule description."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AmbiguityGroup:
    phrase: str
    """Exact ambiguous substring from the rule text."""

    context: str
    """1-2 sentences explaining why this phrase cannot be evaluated deterministically."""

    ambiguity_kind: str
    """
    One of four values — the detector must commit, never use 'either':

    'missing_scalar_threshold'  — vague magnitude with no numeric anchor
                                   (e.g. "significant amount", "unusually large")
                                   UI: number input + operator + unit

    'missing_relative_baseline' — implies comparison to a historical baseline
                                   (e.g. "more than normal", "above average")
                                   UI: LLM-generated radio options

    'missing_window'            — aggregation period not specified
                                   (e.g. "total transactions" with no time window)
                                   UI: window picker

    'underspecified_description' — description has no concrete AML structure at all
                                   (e.g. "suspicious behaviour", "fraud scenarios")
                                   UI: guidance card only, does not block Apply
    """

    needs_window: bool
    """
    True if no aggregation window is present in the original text.
    Only meaningful for 'missing_relative_baseline'; always False for the other kinds.
    """

    VALID_KINDS = frozenset({
        "missing_scalar_threshold",
        "missing_relative_baseline",
        "missing_window",
        "underspecified_description",
    })


@dataclass
class AmbiguityResolution:
    """A resolved value for one detected AmbiguityGroup.

    Only created for missing_scalar_threshold, missing_window, and
    missing_relative_baseline. underspecified_description has no resolution.

    resolved_text is a human-readable string injected into the Clarifications
    block appended to the original description:
      e.g.  "> $5,000"  |  "within the last 30 days"  |  "2x the 30-day average"
    """
    phrase: str
    resolved_text: str
