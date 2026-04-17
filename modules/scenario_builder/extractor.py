"""Lightweight LLM context extraction for the standalone scenario builder path."""
from __future__ import annotations

from core.config.schema_loader import format_attributes_for_prompt
from core.domain.models import ScenarioContext
from core.llm.llm_wrapper import call_llm_json
from core.logging_config import get_logger
from modules.scenario_builder.prompts.extractor import PROMPT_TEMPLATE, SYSTEM

log = get_logger(__name__)

_VALID_RULE_TYPES = {"stateless", "behavioral"}


def extract_context(description: str) -> ScenarioContext:
    """Extract minimal scenario context from a free-form description.

    Returns a ScenarioContext with relevant_attributes, rule_type, and
    high_risk_countries. Never raises — falls back to a minimal context on any error.

    Args:
        description: Raw text entered by the user.
    """
    try:
        schema_context = format_attributes_for_prompt(show_aliases=False)
        prompt = PROMPT_TEMPLATE.format(
            description=description,
            schema_context=schema_context,
        )
        data = call_llm_json(prompt, system=SYSTEM)

        rule_type = data.get("rule_type", "behavioral")
        if rule_type not in _VALID_RULE_TYPES:
            log.warning("extract_context | invalid rule_type=%r, defaulting to behavioral", rule_type)
            rule_type = "behavioral"

        attrs = [str(a) for a in data.get("relevant_attributes", []) if a]
        countries = [str(c) for c in data.get("high_risk_countries", []) if c]

        ctx = ScenarioContext(
            description=str(data.get("description", description)),
            relevant_attributes=attrs,
            rule_type=rule_type,
            high_risk_countries=countries,
        )
        log.info(
            "extract_context | rule_type=%s attrs=%s countries=%s",
            ctx.rule_type, ctx.relevant_attributes, ctx.high_risk_countries,
        )
        return ctx

    except Exception as exc:
        log.error("extract_context | failed, returning minimal context: %s", exc)
        return ScenarioContext(
            description=description,
            relevant_attributes=[],
            rule_type="behavioral",
            high_risk_countries=[],
        )
