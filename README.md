# AML Rule Tester

A Streamlit app with two entry points for generating and validating synthetic AML transaction data:

1. **Standalone Scenario Builder** — describe a scenario in plain English, get transactions immediately. No rule parsing, no validation loop.
2. **Full Rule Tester** — enter a formal AML rule, get fully parsed, validated, and corrected test cases with aggregate proofs.

**LLM is used for:** rule parsing, transaction generation, sequence correction, prototype generation, context extraction, coverage suggestions.
**Fully deterministic (no LLM):** all validation — aggregate computation and condition evaluation.

---

## Running the app

```bash
cd new_rule_tester
export ANTHROPIC_API_KEY=sk-ant-...   # required — get yours at console.anthropic.com
streamlit run app.py
```

Logs are written to `logs/aml_tester.log` (rotated daily).

---

## The Two Flows

### Flow 1 — Standalone Scenario Builder

> Sidebar: **Scenario Builder** button

No rule syntax required. Describe the behaviour you want to test in plain English. The app extracts just enough structure to seed the generator (rule type, relevant attributes, high-risk countries) without parsing formal conditions.

```
User enters free-form description
        ↓
Ambiguity check (optional pre-check before extraction)
        ↓
extract_context() → ScenarioContext
  .rule_type: "behavioral" | "stateless"
  .relevant_attributes: [...]
  .high_risk_countries: [...]
        ↓
User confirms context + picks scenario type + intent
        ↓
ScenarioSession.generate() / generate_prototypes()
        ↓
Transactions table — refine with feedback in a loop
        ↓
Coverage suggestions load in background
```

**No validation loop.** Because there are no parsed conditions to evaluate against, output is returned directly from the generator.

---

### Flow 2 — Full Rule Tester

> Sidebar: **Rule Input** step

Formal rule text → parsed structure → validated + corrected test cases with deterministic aggregate proofs.

```
User enters NL rule
        ↓
Page 1 — Rule Input
  Ambiguity check → parse_rule() → Rule object
  (conditions, computed_attrs, windows, thresholds, filters, OR groups)
  User reviews parsed conditions
        ↓
        ├── stateless ──→ Page 2a — Prototype Review
        │   LLM generates risky + genuine Prototype attribute sets
        │   User refines prototypes with feedback (accumulated across rounds)
        │   User sets count → stateless orchestrator: generate → validate → correct
        │   User reviews transactions → Add to Suite
        │
        └── behavioral ──→ Page 2b — Test Case Builder
            Coverage suggestions pre-fetched in background thread
            User picks scenario type + optional intent
            Behavioral orchestrator: generate → validate → correct loop
            User reviews transactions + aggregate values
            User can give feedback → loop C: regenerate with feedback carried forward
            User approves → added to test suite
                ↓
Page 3 — Test Suite
  All approved cases with transactions and validation results
  Export: CSV / JSON / XLSX
```

---

## Two Rule Types

### Stateless
Evaluates each transaction in isolation. No time windows, no aggregation.

Example: *"Transaction to Iran with send amount > $100"*
→ Each transaction either passes all conditions or not.

### Behavioral
Evaluates patterns over a sequence of transactions. Requires aggregation, counting, or time windows.

Example: *"Sum of transfers to Iran in last 30 days > $5,000"*
→ The rule fires based on aggregate values computed across the full sequence.

---

## How Rules are Represented

### Computed Attributes

The rule parser extracts all intermediate quantities as named **ComputedAttrs** before any condition is evaluated. Each CA is computed once (in order) and injected into every transaction so later CAs and conditions can reference it.

Three CA modes:

**Scalar** — one aggregate over filtered transactions in a window:
```
iran_30d_sum   = sum(send_amount)[30d]  where receive_country_code in ["Iran"]
cash_7d_count  = count(transaction_id)[7d]  where transaction_type == "Cash"
prior_6m_count = count(transaction_id)[6m, exclude_last=7d]   ← prior period window
```

**Group** — aggregate per distinct value of a group-by attribute; the per-group result is injected back into each transaction:
```
recipient_7d_sum = sum(send_amount)[7d]  group_by=recipient_id
# → t.attributes["recipient_7d_sum"] holds that recipient's 7d total for each txn
```

**Derived** — combines two scalar CAs with `ratio` or `difference`:
```
cash_ratio = ratio(cash_7d_count / prior_6m_count)
net_flow   = difference(inbound_30d_sum - outbound_30d_sum)
```

Conditions then compare a CA's value to a threshold:
```
iran_30d_sum > 5000
cash_ratio > 3.0
net_flow > 5000
```

### Filters and OR Groups

Each CA can have a list of `FilterClause` predicates (AND/OR chained). Conditions can be grouped into OR groups: the rule fires if **any one group** has all its conditions satisfied.

---

## The Generate → Validate → Correct Loop

This is the core engine for the Full Rule Tester (behavioral and stateless). All three actors run on every case generation.

```
Generator (LLM)
  Input:  rule description + schema + scenario type + intent + feedback history
  Output: 10–20 transactions with realistic dates, amounts, countries
  Approach: reads the rule text and reasons about aggregates itself
      ↓
Validator (deterministic — no LLM)
  Input:  Rule object + transaction list
  Output: computed aggregates dict + per-condition PASS/FAIL + overall pass/fail
  Example:
    { "sum(send_amount)[30d]": 3200.0 }
    Condition: sum(send_amount)[30d] > 5000 → FAIL (actual: 3200.0)
      ↓ if passed → done
      ↓ if failed (up to 3 attempts)
Corrector (LLM)
  Input:  schema + rule + current transactions + exact aggregate values
          + shortfall arithmetic (computed by Python, not LLM)
          + constraint: preserve background transactions
  Output: repaired transaction list
      ↓
Validator again → repeat up to MAX_ATTEMPTS = 4 (= 3 real correction passes)
```

**Key asymmetry:** the generator is rule-description-first (creative, flexible); the corrector is diagnostic-first (surgical, precise). The corrector receives pre-computed shortfall values from Python — it never has to do the arithmetic itself.

### Shortfall arithmetic example

For a rule like *"recent cash sum > 2× prior cash sum"*, the corrector receives:

```
COMPUTED ATTR REPAIR: cash_ratio > 2.0 [FAIL, current=0.857]
  cash_ratio = cash_7d_count / prior_6m_count
  Current: cash_7d_count=1800.0, prior_6m_count=2100.0, cash_ratio=0.857
  Required: cash_7d_count > 2.0 × 2100.0 = 4200.00 (with 5% buffer → aim for 4410.00)
  Shortfall: +2610.00 needed in cash_7d_count
  → Add filter-matching transactions in the RECENT 7d window.
  → Do NOT add filter-matching transactions to the PRIOR period — raises denominator.
```

---

## Coverage Suggestions

Auto-generated for every rule in a background thread. Each suggestion pre-fills the scenario type and intent field. `expected_outcome` (FIRE / NOT_FIRE) is determined by Python from the pattern type — never by the LLM.

| Pattern | Scenario | Description |
|---|---|---|
| `typical_trigger` | risky | Comfortable margin above all thresholds |
| `volume_structuring` | risky | Many small transactions that together cross the threshold |
| `boundary_just_over` | risky | Aggregate barely exceeds threshold |
| `boundary_at_threshold` | genuine | Aggregate exactly at threshold — must NOT fire |
| `near_miss_one_clause` | genuine | All conditions met except one |
| `or_branch_trigger` | risky | Only one OR branch fires |
| `or_branch_all_fail` | genuine | All OR branches stay below threshold |
| `window_edge_inside` | risky | Activity concentrated at the edge of the time window |
| `window_edge_outside` | genuine | Activity falls just outside the window |
| `filter_partial_match` | genuine | Transactions match some but not all filter conditions |
| `group_isolation` | risky | Only one group crosses the group-level threshold |
| `filter_empty` | genuine | No transactions match the rule's filter |

---

## Project Structure

```
new_rule_tester/
├── app.py                             Streamlit entry point, page router, sidebar
│
├── core/                              Shared infrastructure — no module imports back into here
│   ├── logging_config.py              get_logger() — centralised logging setup
│   ├── domain/
│   │   ├── models.py                  All dataclasses: Rule, RuleCondition, ComputedAttr,
│   │   │                              DerivedAttr, FilterClause, Transaction,
│   │   │                              BehavioralTestCase, Prototype, ScenarioContext,
│   │   │                              ScenarioResult, TestSuggestion,
│   │   │                              ValidationResult, ConditionResult
│   │   └── ambiguity.py               AmbiguityGroup dataclass, AmbiguityResolution dataclass
│   ├── config/
│   │   ├── schema.yml                 Canonical attribute names, types, aliases, allowed values
│   │   └── schema_loader.py           canonical_name(), normalize_country_values(),
│   │                                  format_attributes_for_prompt()
│   └── llm/
│       └── llm_wrapper.py             call_llm(), call_llm_json() — Anthropic SDK wrapper
│
├── modules/                           Capability modules — each owns its logic + prompts
│   │
│   ├── ambiguity/                     Detect + resolve ambiguous phrases before parse or generation
│   │   ├── __init__.py                detect_ambiguities(), enrich_description(), get_baseline_options()
│   │   ├── detector.py                detect_ambiguities(description) → list[AmbiguityGroup]
│   │   ├── resolver.py                get_baseline_options() — LLM-generated options for baseline cards
│   │   └── prompts/
│   │       ├── detector.py
│   │       └── resolver.py
│   │
│   ├── rule_parser/                   Parse NL rule text into structured Rule object
│   │   ├── __init__.py                parse_rule(description) → Rule
│   │   ├── parser.py
│   │   └── prompts/parser.py
│   │
│   ├── scenario_builder/              Session-based scenario generation
│   │   ├── __init__.py                extract_context(), ScenarioSession, generate_suggestions
│   │   ├── extractor.py               extract_context() — lightweight context extraction
│   │   ├── session.py                 ScenarioSession — owns feedback history + suggestions thread
│   │   ├── generator.py               generate_behavioral_sequence(), generate_stateless_sequence()
│   │   ├── prototype.py               generate_prototypes(), generate_single_prototype()
│   │   ├── suggestions.py             generate_suggestions() → list[TestSuggestion]
│   │   └── prompts/
│   │       ├── extractor.py
│   │       ├── sequence_generator.py
│   │       ├── prototype_generator.py
│   │       └── suggestion_generator.py
│   │
│   └── validation_correction/         Deterministic validation + LLM-based correction
│       ├── __init__.py                run_behavioral(), run(), run_single()
│       ├── aggregate_compute.py       compute_aggregates() — pure Python, no LLM
│       ├── rule_engine.py             evaluate_behavioral_sequence(), evaluate_stateless_sequence()
│       ├── corrector.py               correct_behavioral_sequence(), correct_stateless_transaction()
│       ├── behavioral_orchestrator.py run() — Loop B + Loop C
│       ├── stateless_orchestrator.py  run(), run_single() — generate → validate → correct
│       └── prompts/corrector.py
│
├── ui/
│   ├── state.py                       Session state init, reset, go_to(), log_status()
│   ├── suggestion_loader.py           Background thread for suggestion pre-fetch (Full Rule Tester)
│   ├── ambiguity_ui.py                render_ambiguity_cards(), clear_card_state() — shared resolution cards
│   └── pages/
│       ├── rule_input.py              Page 1 — rule entry + condition review
│       ├── prototype_review.py        Page 2a — stateless prototype review + case generation
│       ├── test_case_builder.py       Page 2b — behavioral test case builder + suggestions panel
│       ├── scenario_input.py          Standalone scenario builder page
│       └── test_suite.py              Page 3 — test suite viewer + export
│
├── export/
│   └── exporter.py                    CSV / JSON / XLSX export
│
├── scripts/
│   └── run_batch_test.py              CLI batch tester — reads test_rules.csv, runs all rules
│
├── tests/
│   ├── test_scenario_builder.py       Unit tests — ScenarioSession, ScenarioContext (no LLM calls)
│   └── test_ambiguity_resolution.py   Unit tests — AmbiguityResolution, enrich_description, resolver fallback
│
├── docs/superpowers/specs/
│   └── module-api-reference.md        Full module API reference with input/output tables
│
└── logs/
    └── aml_tester.log                 Daily-rotating debug log (git-ignored)
```

---

## Schema and Attribute Naming

`core/config/schema.yml` is the single source of truth for all transaction attribute names. The LLM is always given the canonical names and instructed not to use aliases.

Key canonical names:

| Canonical name | Type | Notes |
|---|---|---|
| `send_amount` | numeric | Amount sent |
| `receive_amount` | numeric | Amount received |
| `send_country_code` | categorical | Full country name, e.g. `"United Kingdom"` |
| `receive_country_code` | categorical | Full country name matching `rule.high_risk_countries` exactly |
| `transaction_type` | categorical | e.g. `"cash_withdrawal"`, `"bank_transfer"` |
| `payin_method` | categorical | e.g. `"card"`, `"wallet"` |
| `transaction_id` | string | Used as the attribute for `count` aggregations |
| `created_at` | datetime | ISO date `YYYY-MM-DD`; anchors all window calculations |

Country values must match the strings in `rule.high_risk_countries` exactly (e.g. `"Iran"` not `"IR"`). `schema_loader.normalize_country_values()` converts ISO codes to full names after LLM generation.

---

## Logging

All modules use `from core.logging_config import get_logger`. Logs go to `logs/aml_tester.log`.

| Level | Used for |
|---|---|
| DEBUG | Full prompt text, full LLM responses, per-aggregate computed values |
| INFO | LLM call metadata (model, chars, elapsed), rule parse result, validation pass/fail per condition, corrector shortfall details |
| WARNING | Failed convergence, condition_group_connector mismatches |
| ERROR | LLM JSON parse failures with raw response preview |

```bash
# Tail during a run
tail -f logs/aml_tester.log

# Filter to failures only
grep "FAIL\|ERROR\|WARNING" logs/aml_tester.log
```

---

## Batch Testing

```bash
cd new_rule_tester
export ANTHROPIC_API_KEY=sk-ant-...
python3 scripts/run_batch_test.py                       # all rules in test_rules.csv
python3 scripts/run_batch_test.py --rules R01 R08       # specific rules only
python3 scripts/run_batch_test.py --rules R01 --repeat 3  # run 3 times; PASS only if all pass
```

Outputs an HTML + JSON report in the working directory.

---

## Key Design Decisions

**Two separate entry points for two use cases.** The Standalone Scenario Builder skips rule parsing and validation entirely — useful when you want transactions fast without writing a formal rule. The Full Rule Tester provides deterministic validation proofs for compliance use cases.

**Generator is rule-description-first.** The generator prompt does not inject pre-computed arithmetic. It gives the LLM the rule text and lets it reason about aggregates itself. This keeps the generator simple and model-agnostic.

**Corrector is diagnostic-first.** The corrector receives exact current aggregate values and pre-computed shortfall arithmetic from Python. It never has to do the math itself. The corrector is the precision instrument; the generator just needs to be close enough.

**Validation is 100% deterministic.** No LLM is involved in deciding whether a sequence passes. `aggregate_compute.py` runs pure Python arithmetic over transaction attributes. Pass/fail results are reproducible and trustworthy regardless of LLM behaviour.

**Feedback accumulates.** All prior user feedback strings travel with the session through every generator and corrector call — `ScenarioSession` for the standalone builder, `BehavioralTestCase.user_feedback_history` for the full tester. Earlier instructions are never dropped.

**Background threads for suggestions.** Coverage suggestions are generated in a daemon thread so they never block navigation. The UI polls on each rerun and shows a spinner until results arrive.

**Prompts are co-located with their module.** Each module under `modules/` has its own `prompts/` subfolder. This keeps prompt strings physically close to the logic that uses them and makes edits easy to review without touching Python logic.

**`call_llm_json` uses `raw_decode`.** The JSON parser uses `json.JSONDecoder().raw_decode()` rather than `json.loads()`, which gracefully handles cases where the model appends explanation text after the JSON object.
