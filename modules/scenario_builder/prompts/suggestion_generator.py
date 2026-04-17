"""Prompt strings for modules/scenario_builder/suggestions.py."""

SYSTEM = """You are a test engineer generating AML rule test suggestions.
Output ONLY valid JSON — no explanation, no markdown fences."""

SUGGESTION_PROMPT = """You are a test engineer treating this AML detection rule as a software \
function to be tested with full coverage — both rule logic paths and real-world data edge cases.

Your goal: suggest test scenarios that together cover all meaningful paths through the rule, \
both risky (FIRE) and genuine (NOT_FIRE). Each scenario should target a specific aspect of the \
rule that would reveal a bug if that aspect were implemented incorrectly.

Rule expression: {raw_expression}
Rule type: {rule_type} (stateless = evaluated per transaction; behavioral = aggregates across a sequence)

--- RULE ANATOMY ---
{rule_anatomy}

--- YOUR TASK ---
Think through the rule like an engineer stress-testing it:
- What is the core suspicious behaviour this rule is designed to catch?
- Which conditions are the hardest to satisfy simultaneously?
- What realistic innocent customer behaviour could look superficially similar but should NOT trigger?
- Where are the exact threshold, window, and filter boundaries that, if off-by-one, would cause \
false positives or false negatives?
- What real-world data quirks could silently skew the aggregate?

--- LAYER 1: RULE LOGIC PATTERNS ---
These test threshold, window, operator, and OR-branch logic.
Generate one scenario per pattern below:

{layer1_patterns_list}

--- LAYER 2: DATA REALITY PATTERNS ---
These test how the rule handles real-world banking data quirks.
Use ONLY the schema values in the DATA ENVIRONMENT section — do not invent status names, \
funding method names, or field names.

{schema_context}

Generate one scenario per pattern below:

{layer2_patterns_list}

--- FIELD RULES (apply to ALL patterns) ---
- title: Short label (max 10 words). Name the pattern and what makes it distinctive.
- description: 2-3 sentences. What specifically does this test, and what bug would it catch if \
the rule were implemented incorrectly?
- focus_conditions: List the specific condition or CA names this pattern exercises \
(e.g. "iran_30d_sum > 5000", "transfer_status filter").
- suggested_intent: Describe the account behaviour in plain English. For Data Reality patterns, \
describe the specific data quirk and why it should or should not affect the aggregate. Be specific \
about which filters pass or fail, but do NOT hardcode threshold numbers or country names.
  BAD: "avg to Iran = $510, 3 transactions"
  GOOD: "Customer makes three completed transfers to a high-risk destination that together exceed \
the threshold, plus two that are cancelled mid-processing. The rule should count only the \
completed ones."

Output a JSON array — one object per pattern:
[
  {{
    "pattern_type": "<exact pattern_type string from the lists above>",
    "category": "<rule_logic for Layer 1 | data_reality for Layer 2>",
    "title": "...",
    "description": "...",
    "focus_conditions": ["...", "..."],
    "suggested_intent": "..."
  }},
  ...
]"""
