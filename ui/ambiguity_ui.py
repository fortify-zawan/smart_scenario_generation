"""Shared ambiguity resolution UI.

Renders per-kind resolution cards for both the Full Rule Tester (rule_input.py)
and the Standalone Scenario Builder (scenario_input.py).

Public API:
    render_ambiguity_cards(ambiguities, description) -> list[AmbiguityResolution] | None
    clear_card_state() -> None
"""
from __future__ import annotations

import streamlit as st

from core.domain.ambiguity import AmbiguityGroup, AmbiguityResolution
from modules.ambiguity import get_baseline_options

# ── Session state keys ─────────────────────────────────────────────────────────
_CARD_VALUES   = "ambiguity_card_values"     # dict[phrase, resolved_text]
_APPLY_CLICKED = "_ambiguity_apply_clicked"
_SKIP_CLICKED  = "_ambiguity_skip_clicked"

# ── Input options ──────────────────────────────────────────────────────────────
_OPERATORS      = [">", ">=", "<", "<="]
_UNITS          = ["USD", "count", "%"]
_DURATION_UNITS = ["days", "weeks", "months"]

_STRUCTURED_KINDS = frozenset({
    "missing_scalar_threshold",
    "missing_window",
    "missing_relative_baseline",
})


def render_ambiguity_cards(
    ambiguities: list[AmbiguityGroup],
    description: str,
) -> list[AmbiguityResolution] | None:
    """Render resolution cards for all detected ambiguities.

    Call this on every rerun while ambiguities are pending. Returns a value
    only once, on the rerun triggered by a button click.

    Returns:
        list[AmbiguityResolution]  Apply was clicked; one entry per resolved
                                   structured card. Empty list if only
                                   underspecified_description ambiguities present.
        []                         Skip was clicked. Caller proceeds with the
                                   original unmodified description.
        None                       Cards are rendered but no action yet.
    """
    if _CARD_VALUES not in st.session_state:
        st.session_state[_CARD_VALUES] = {}

    # ── Handle deferred button returns ────────────────────────────────────────
    if st.session_state.get(_APPLY_CLICKED):
        del st.session_state[_APPLY_CLICKED]
        structured = [a for a in ambiguities if a.ambiguity_kind in _STRUCTURED_KINDS]
        return [
            AmbiguityResolution(
                phrase=ag.phrase,
                resolved_text=st.session_state[_CARD_VALUES].get(ag.phrase, ""),
            )
            for ag in structured
            if st.session_state[_CARD_VALUES].get(ag.phrase)
        ]

    if st.session_state.get(_SKIP_CLICKED):
        del st.session_state[_SKIP_CLICKED]
        return []

    # ── Separate by kind ──────────────────────────────────────────────────────
    structured = [a for a in ambiguities if a.ambiguity_kind in _STRUCTURED_KINDS]
    guidance   = [a for a in ambiguities if a.ambiguity_kind == "underspecified_description"]

    # Guidance cards first (non-blocking)
    for ag in guidance:
        _render_underspecified_card(ag)

    # Structured resolution cards
    for ag in structured:
        if ag.ambiguity_kind == "missing_scalar_threshold":
            _render_threshold_card(ag)
        elif ag.ambiguity_kind == "missing_window":
            _render_window_card(ag)
        elif ag.ambiguity_kind == "missing_relative_baseline":
            _render_baseline_card(ag, description)

    # ── Action buttons ────────────────────────────────────────────────────────
    all_filled = all(
        bool(st.session_state[_CARD_VALUES].get(ag.phrase))
        for ag in structured
    )

    col_apply, col_skip = st.columns([2, 1])
    with col_apply:
        if st.button(
            "Apply & Continue",
            type="primary",
            disabled=not all_filled,
            key="ambiguity_apply_btn",
            help="Fill in all fields above to enable" if not all_filled else None,
        ):
            st.session_state[_APPLY_CLICKED] = True
            st.rerun()
    with col_skip:
        if st.button(
            "Skip and continue anyway",
            type="secondary",
            key="ambiguity_skip_btn",
        ):
            st.session_state[_SKIP_CLICKED] = True
            st.rerun()

    return None


def clear_card_state() -> None:
    """Remove all card input and baseline cache keys from session state.

    Call this before rendering new ambiguities so stale values from a previous
    detection run don't pre-fill the new cards.
    """
    st.session_state.pop(_CARD_VALUES, None)
    keys_to_remove = [k for k in st.session_state if k.startswith("_bline_opts_")]
    for k in keys_to_remove:
        del st.session_state[k]


# ── Per-kind card renderers ────────────────────────────────────────────────────

def _render_threshold_card(ag: AmbiguityGroup) -> None:
    with st.container(border=True):
        st.markdown(f'**"{ag.phrase}"**')
        st.caption(ag.context)
        col_op, col_val, col_unit = st.columns([1, 2, 1])
        operator = col_op.selectbox(
            "Operator",
            _OPERATORS,
            key=f"thresh_op_{ag.phrase}",
            label_visibility="collapsed",
        )
        value = col_val.number_input(
            "Value",
            min_value=0.0,
            step=1.0,
            value=0.0,
            key=f"thresh_val_{ag.phrase}",
            label_visibility="collapsed",
        )
        unit = col_unit.selectbox(
            "Unit",
            _UNITS,
            key=f"thresh_unit_{ag.phrase}",
            label_visibility="collapsed",
        )
        if value > 0:
            if unit == "USD":
                formatted = f"{operator} ${value:,.0f}"
            elif unit == "%":
                formatted = f"{operator} {value:.1f}%"
            else:
                formatted = f"{operator} {value:.0f}"
            st.session_state[_CARD_VALUES][ag.phrase] = formatted
        else:
            st.session_state[_CARD_VALUES].pop(ag.phrase, None)


def _render_window_card(ag: AmbiguityGroup) -> None:
    with st.container(border=True):
        st.markdown(f'**"{ag.phrase}"**')
        st.caption(ag.context)
        col_dur, col_unit = st.columns(2)
        duration = col_dur.number_input(
            "Duration",
            min_value=1,
            step=1,
            value=30,
            key=f"win_dur_{ag.phrase}",
            label_visibility="collapsed",
        )
        unit = col_unit.selectbox(
            "Unit",
            _DURATION_UNITS,
            key=f"win_unit_{ag.phrase}",
            label_visibility="collapsed",
        )
        exclude = st.checkbox(
            "Exclude last N days from this window (for prior-period patterns)",
            key=f"win_excl_{ag.phrase}",
        )
        excl_text = ""
        if exclude:
            col_ed, col_eu = st.columns(2)
            excl_dur = col_ed.number_input(
                "Exclude duration",
                min_value=1,
                step=1,
                value=7,
                key=f"win_edur_{ag.phrase}",
                label_visibility="collapsed",
            )
            excl_unit = col_eu.selectbox(
                "Exclude unit",
                _DURATION_UNITS,
                key=f"win_eunit_{ag.phrase}",
                label_visibility="collapsed",
            )
            excl_text = f" excluding the last {int(excl_dur)} {excl_unit}"
        resolved = f"within the last {int(duration)} {unit}{excl_text}"
        st.session_state[_CARD_VALUES][ag.phrase] = resolved


def _render_baseline_card(ag: AmbiguityGroup, description: str) -> None:
    with st.container(border=True):
        st.markdown(f'**"{ag.phrase}"**')
        st.caption(ag.context)
        # Fetch options once; cache under a key scoped to this phrase
        cache_key = f"_bline_opts_{ag.phrase}"
        if cache_key not in st.session_state:
            with st.spinner("Generating options…"):
                st.session_state[cache_key] = get_baseline_options(
                    phrase=ag.phrase,
                    context=ag.context,
                    description=description,
                )
        options = st.session_state[cache_key]
        all_choices = options + ["Write my own"]
        choice = st.radio(
            "How should this baseline be computed?",
            all_choices,
            key=f"bline_choice_{ag.phrase}",
        )
        if choice == "Write my own":
            custom = st.text_input(
                "Describe the baseline",
                key=f"bline_custom_{ag.phrase}",
                placeholder="e.g. 3x the customer's 60-day average send amount",
            )
            if custom.strip():
                st.session_state[_CARD_VALUES][ag.phrase] = custom.strip()
            else:
                st.session_state[_CARD_VALUES].pop(ag.phrase, None)
        else:
            st.session_state[_CARD_VALUES][ag.phrase] = choice


def _render_underspecified_card(_ag: AmbiguityGroup) -> None:
    with st.container(border=True):
        st.warning(
            "This description doesn't contain enough structure for the engine — "
            "no transaction attributes, thresholds, or patterns were found."
        )
        st.markdown(
            "**Edit your description above to include something concrete. Examples:**\n"
            "- *Alert if customer sends > $5,000 to Iran in a single transaction*\n"
            "- *Flag accounts with 10 or more cash transactions in a 7-day window*\n"
            "- *Sum of transfers to high-risk countries in last 30 days > $10,000*"
        )
