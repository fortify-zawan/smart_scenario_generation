"""Detect ambiguous phrases in a rule description before parsing."""
from __future__ import annotations

from core.domain.ambiguity import AmbiguityGroup
from core.llm.llm_wrapper import call_llm_json
from core.logging_config import get_logger
from modules.ambiguity.prompts.detector import PROMPT_TEMPLATE, SYSTEM

log = get_logger(__name__)


def detect_ambiguities(description: str, rule=None) -> list[AmbiguityGroup]:
    """Return a list of AmbiguityGroups for genuinely unresolvable phrases.

    Runs before the rule parser so the parser only ever receives clean input.
    Always returns [] on any error — never raises.

    Args:
        description: The raw rule text entered by the user.
        rule:        Parsed Rule object (optional). Reserved for Phase 2 cross-checking;
                     unused in Phase 1.
    """
    try:
        prompt = PROMPT_TEMPLATE.format(description=description)
        data = call_llm_json(prompt, system=SYSTEM)

        raw_groups = data.get("ambiguities", [])
        if not isinstance(raw_groups, list):
            log.warning("detect_ambiguities | unexpected 'ambiguities' type: %s", type(raw_groups))
            return []

        groups: list[AmbiguityGroup] = []
        for item in raw_groups:
            kind = item.get("ambiguity_kind", "")
            if kind not in AmbiguityGroup.VALID_KINDS:
                log.warning(
                    "detect_ambiguities | skipping item with invalid ambiguity_kind=%r phrase=%r",
                    kind, item.get("phrase"),
                )
                continue

            needs_window = bool(item.get("needs_window", False))
            # needs_window is only meaningful for missing_relative_baseline
            if kind != "missing_relative_baseline":
                needs_window = False

            groups.append(AmbiguityGroup(
                phrase=str(item.get("phrase", "")),
                context=str(item.get("context", "")),
                ambiguity_kind=kind,
                needs_window=needs_window,
            ))

        log.info(
            "detect_ambiguities | found %d ambiguity group(s) for description (chars=%d)",
            len(groups), len(description),
        )
        for g in groups:
            log.info("  [%s] %r — %s", g.ambiguity_kind, g.phrase, g.context)

        return groups

    except Exception as exc:
        log.error("detect_ambiguities | failed, returning []: %s", exc)
        return []
