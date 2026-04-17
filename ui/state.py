"""Session state manager — centralises all st.session_state access."""
import streamlit as st


def init_state():
    """Initialise all session state keys with defaults on first load."""
    defaults = {
        "step": "scenario_input",
        "api_key": "",              # Anthropic API key (set via Settings in sidebar)
        "rule": None,               # domain.models.Rule
        "risky_proto": None,        # domain.models.Prototype
        "genuine_proto": None,      # domain.models.Prototype
        "risky_proto_approved": False,   # True after user approves risky prototype
        "genuine_proto_approved": False, # True after user approves genuine prototype
        "risky_cases": None,        # list[Transaction] for the current draft (not yet added to suite)
        "genuine_cases": None,      # list[Transaction] for the current draft (not yet added to suite)
        "risky_case_groups": [],    # list[list[Transaction]] — all approved risky prototype groups
        "genuine_case_groups": [],  # list[list[Transaction]] — all approved genuine prototype groups
        "stateless_sequence": None, # list[Transaction] (flattened all groups, for export)
        "behavioral_cases": [],     # list[BehavioralTestCase]
        "current_case": None,       # BehavioralTestCase being reviewed
        "status_log": [],           # list of progress messages shown during generation
        "suggestions": None,        # list[TestSuggestion] | None — None means not yet generated
        "prefill_scenario_type": None,        # behavioral: set by "Use this suggestion"
        "prefill_intent": None,               # behavioral: set by "Use this suggestion"
        "prefill_expected_outcome": None,     # behavioral: "FIRE" or "NOT_FIRE"
        "prefill_proto_scenario_type": None,  # stateless: set by "Use this suggestion"
        "prefill_proto_intent": None,         # stateless: set by "Use this suggestion"
        "ambiguities": [],                    # list[AmbiguityGroup] — detected before parsing
        "clarification_stage": "idle",        # "idle" | "needs_clarification" | "clear"
        # Standalone scenario builder state
        "scenario_context": None,             # ScenarioContext — after extract_context() runs
        "scenario_session": None,             # ScenarioSession — created after context is confirmed
        "scenario_result": None,              # ScenarioResult — last result from generate() or refine()
        "scenario_risky_proto": None,         # Prototype — stateless risky prototype
        "scenario_genuine_proto": None,       # Prototype — stateless genuine prototype
        "scenario_input_step": "input",       # "input" | "context_review" | "result"
        "scenario_prefill_type": None,        # set by "Use this suggestion"
        "scenario_prefill_intent": None,      # set by "Use this suggestion"
        "scenario_ambiguities": [],           # list[AmbiguityGroup] pending resolution
        "scenario_pending_description": "",   # description saved during ambiguity hold
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_state():
    """Reset all session state to defaults (start a new rule)."""
    defaults = {
        "step": "scenario_input",
        "rule": None,
        "risky_proto": None,
        "genuine_proto": None,
        "risky_proto_approved": False,
        "genuine_proto_approved": False,
        "risky_cases": None,
        "genuine_cases": None,
        "risky_case_groups": [],
        "genuine_case_groups": [],
        "stateless_sequence": None,
        "behavioral_cases": [],
        "current_case": None,
        "status_log": [],
        "suggestions": None,
        "prefill_scenario_type": None,
        "prefill_intent": None,
        "prefill_expected_outcome": None,
        "prefill_proto_scenario_type": None,
        "prefill_proto_intent": None,
        "ambiguities": [],
        "clarification_stage": "idle",
        # Standalone scenario builder state
        "scenario_context": None,
        "scenario_session": None,
        "scenario_result": None,
        "scenario_risky_proto": None,
        "scenario_genuine_proto": None,
        "scenario_input_step": "input",
        "scenario_prefill_type": None,
        "scenario_prefill_intent": None,
        "scenario_ambiguities": [],
        "scenario_pending_description": "",
    }
    for key, value in defaults.items():
        st.session_state[key] = value


def go_to(step: str):
    st.session_state.step = step


def log_status(msg: str):
    st.session_state.status_log.append(msg)


def clear_status_log():
    st.session_state.status_log = []
