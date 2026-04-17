"""Prompt strings for modules/scenario_builder/extractor.py."""

SYSTEM = """\
You are an AML scenario context extractor. Given a description of an AML scenario or rule,
extract the minimal structured context needed to generate test transactions.

Output ONLY valid raw JSON — no markdown fences, no explanation, no trailing text.
"""

PROMPT_TEMPLATE = """\
# DESCRIPTION
{description}

# CANONICAL ATTRIBUTE NAMES AVAILABLE
{schema_context}

# TASK
Extract the scenario context. Return this exact JSON shape:
{{
  "description": "<the original description, unchanged>",
  "relevant_attributes": ["<canonical attr name>", ...],
  "rule_type": "<stateless|behavioral>",
  "high_risk_countries": ["<full country name>", ...]
}}

RULE TYPE DECISION:
- "stateless": each transaction evaluated independently, no time windows, no sums/counts across transactions
- "behavioral": involves sum/count/average over time, time windows (e.g. 30d, 7d), or patterns across multiple transactions

RELEVANT ATTRIBUTES: use only canonical names from the list above. Include every attribute
the description implies will be compared, filtered, or aggregated.

HIGH RISK COUNTRIES: full names only (e.g. "Iran" not "IR"). Empty list if none mentioned.
Do NOT flag "USD" or currency codes as countries.\
"""
