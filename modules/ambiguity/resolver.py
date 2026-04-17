"""Generate concrete baseline formula options for missing_relative_baseline phrases."""
from __future__ import annotations

from core.llm.llm_wrapper import call_llm_json
from core.logging_config import get_logger
from modules.ambiguity.prompts.resolver import PROMPT_TEMPLATE, SYSTEM

log = get_logger(__name__)

FALLBACK_OPTIONS: list[str] = [
    "2x the 30-day average send amount",
    "3x the customer's 90-day average send amount",
    "1.5x the 6-month average send amount",
]


def get_baseline_options(phrase: str, context: str, description: str) -> list[str]:
    """Generate 3-4 concrete baseline formula options for a missing_relative_baseline phrase.

    Returns FALLBACK_OPTIONS on any error — never raises.

    Args:
        phrase:      The exact ambiguous substring (e.g. "more than normal").
        context:     The AmbiguityGroup.context explaining why this was flagged.
        description: The full original rule/scenario description.
    """
    try:
        prompt = PROMPT_TEMPLATE.format(
            phrase=phrase,
            context=context,
            description=description,
        )
        data = call_llm_json(prompt, system=SYSTEM)
        options = data.get("options", [])
        if not isinstance(options, list) or len(options) < 2:
            log.warning("get_baseline_options | unexpected options shape: %r", options)
            return FALLBACK_OPTIONS
        result = [str(o) for o in options if str(o).strip()]
        log.info("get_baseline_options | generated %d options for phrase=%r", len(result), phrase)
        return result
    except Exception as exc:
        log.error("get_baseline_options | failed, returning fallback: %s", exc)
        return FALLBACK_OPTIONS
