# AML Scenario Builder

A Streamlit app for generating synthetic AML transaction data from plain-English descriptions. No formal rule syntax required.

**LLM is used for:** context extraction, transaction generation, prototype generation, coverage suggestions, ambiguity detection.

---

## Running the app

```bash
cd scenario_builder_p1
export ANTHROPIC_API_KEY=sk-ant-...   # required — get yours at console.anthropic.com
streamlit run app.py
```

Logs are written to `logs/aml_tester.log` (rotated daily).

---

## Flow

Describe the behaviour you want to test in plain English. The app extracts just enough structure to seed the generator (rule type, relevant attributes, high-risk countries) without parsing formal conditions.

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

## Coverage Suggestions

Auto-generated in a background thread after context extraction. Each suggestion pre-fills the scenario type and intent field.

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
scenario_builder_p1/
├── app.py                             Streamlit entry point, sidebar
│
├── core/                              Shared infrastructure
│   ├── logging_config.py              get_logger() — centralised logging setup
│   ├── domain/
│   │   ├── models.py                  Dataclasses: ScenarioContext, ScenarioResult,
│   │   │                              Transaction, Prototype, TestSuggestion
│   │   └── ambiguity.py               AmbiguityGroup, AmbiguityResolution dataclasses
│   ├── config/
│   │   ├── schema.yml                 Canonical attribute names, types, aliases, allowed values
│   │   └── schema_loader.py           canonical_name(), normalize_country_values(),
│   │                                  format_attributes_for_prompt()
│   └── llm/
│       └── llm_wrapper.py             call_llm(), call_llm_json() — Anthropic SDK wrapper
│
├── modules/
│   ├── ambiguity/                     Detect + resolve ambiguous phrases before extraction
│   │   ├── __init__.py                detect_ambiguities(), enrich_description(), get_baseline_options()
│   │   ├── detector.py                detect_ambiguities(description) → list[AmbiguityGroup]
│   │   ├── resolver.py                get_baseline_options() — LLM-generated baseline options
│   │   └── prompts/
│   │
│   └── scenario_builder/              Session-based scenario generation
│       ├── __init__.py                extract_context(), ScenarioSession, generate_suggestions
│       ├── extractor.py               extract_context() — lightweight context extraction
│       ├── session.py                 ScenarioSession — owns feedback history + suggestions thread
│       ├── generator.py               generate_behavioral_sequence(), generate_stateless_sequence()
│       ├── prototype.py               generate_prototypes(), generate_single_prototype()
│       ├── suggestions.py             generate_suggestions() → list[TestSuggestion]
│       └── prompts/
│
├── ui/
│   ├── state.py                       Session state init, reset, log_status()
│   ├── suggestion_loader.py           Background thread for suggestion pre-fetch
│   ├── ambiguity_ui.py                render_ambiguity_cards(), clear_card_state()
│   └── pages/
│       └── scenario_input.py          Scenario builder page
│
└── logs/
    └── aml_tester.log                 Daily-rotating debug log (git-ignored)
```

---

## Schema and Attribute Naming

`core/config/schema.yml` is the single source of truth for all transaction attribute names. The LLM is always given the canonical names and instructed not to use aliases.

| Canonical name | Type | Notes |
|---|---|---|
| `send_amount` | numeric | Amount sent |
| `receive_amount` | numeric | Amount received |
| `send_country_code` | categorical | Full country name, e.g. `"United Kingdom"` |
| `receive_country_code` | categorical | Full country name matching high-risk countries exactly |
| `transaction_type` | categorical | e.g. `"cash_withdrawal"`, `"bank_transfer"` |
| `payin_method` | categorical | e.g. `"card"`, `"wallet"` |
| `transaction_id` | string | Used as the attribute for `count` aggregations |
| `created_at` | datetime | ISO date `YYYY-MM-DD`; anchors all window calculations |

Country values must match the strings in `high_risk_countries` exactly (e.g. `"Iran"` not `"IR"`). `schema_loader.normalize_country_values()` converts ISO codes to full names after LLM generation.

---

## Logging

All modules use `from core.logging_config import get_logger`. Logs go to `logs/aml_tester.log`.

| Level | Used for |
|---|---|
| DEBUG | Full prompt text, full LLM responses |
| INFO | LLM call metadata (model, chars, elapsed), context extraction result |
| WARNING | Ambiguity detection fallbacks |
| ERROR | LLM JSON parse failures with raw response preview |

```bash
# Tail during a run
tail -f logs/aml_tester.log
```

---

## Key Design Decisions

**Generator is rule-description-first.** The generator prompt gives the LLM the description and lets it reason about what transactions make sense. No pre-computed arithmetic is injected.

**Feedback accumulates.** All prior user feedback strings travel with the session through every generator call via `ScenarioSession`. Earlier instructions are never dropped.

**Background threads for suggestions.** Coverage suggestions are generated in a daemon thread so they never block navigation. The UI polls on each rerun and shows a spinner until results arrive.

**Prompts are co-located with their module.** Each module under `modules/` has its own `prompts/` subfolder. This keeps prompt strings physically close to the logic that uses them.

**`call_llm_json` uses `raw_decode`.** The JSON parser uses `json.JSONDecoder().raw_decode()` rather than `json.loads()`, which gracefully handles cases where the model appends explanation text after the JSON object.
