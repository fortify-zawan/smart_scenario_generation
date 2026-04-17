"""Standalone Scenario Builder page.

Flow:
  1. User enters a free-form description → extract_context() runs
  2. User reviews extracted context (rule_type, attributes, countries)
  3. User picks scenario_type + intent → session.generate()
  4. Transactions table shown + suggestions loaded in background
  5. User can refine via feedback → session.refine()
  For stateless rules: step 3 shows prototypes first, then generates transactions.
"""
import streamlit as st

from core.domain.models import ScenarioContext, ScenarioResult
from modules.ambiguity import detect_ambiguities, enrich_description
from ui.ambiguity_ui import clear_card_state, render_ambiguity_cards
from modules.scenario_builder import ScenarioSession, extract_context
from ui.state import clear_status_log


# ── Constants ─────────────────────────────────────────────────────────────────

_SCENARIO_BADGE = {
    "risky":   ":red[RISKY]",
    "genuine": ":green[GENUINE]",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _render_transactions_table(result: ScenarioResult) -> None:
    """Render the transactions from a ScenarioResult as a Streamlit table."""
    if not result.transactions:
        st.warning("No transactions generated.")
        return

    import pandas as pd

    rows = []
    for t in result.transactions:
        row = {"id": t.id, "tag": t.tag}
        row.update(t.transaction_attrs)
        row.update(t.user_attrs)
        row.update(t.recipient_attrs)
        rows.append(row)

    df = pd.DataFrame(rows)
    tag_col = df.pop("tag")
    id_col = df.pop("id")
    df.insert(0, "tag", tag_col)
    df.insert(0, "id", id_col)
    st.dataframe(df, use_container_width=True)


def _render_conflict_warnings(result: ScenarioResult) -> None:
    if not result.conflict_warnings:
        return
    with st.expander(f"⚠ {len(result.conflict_warnings)} feedback conflict(s) detected", expanded=False):
        for c in result.conflict_warnings:
            st.caption(f"**{c.get('field', '?')}**: {c.get('issue', str(c))}")


def _render_suggestions_panel(session: ScenarioSession) -> None:
    """Show the suggestions panel. Polls session on each rerun."""
    with st.expander("Coverage Suggestions", expanded=True):
        if not session.suggestions_ready:
            st.caption("⏳ Loading suggestions…")
            if st.button("↻ Check", key="refresh_suggestions", use_container_width=True):
                st.rerun()
            return

        suggestions = session.get_suggestions()
        if not suggestions:
            st.caption("No suggestions available.")
            return

        st.caption("Click **Use** to pre-fill the form.")
        for s in suggestions:
            badge = _SCENARIO_BADGE.get(s.scenario_type, s.scenario_type)
            title = s.title if len(s.title) <= 57 else s.title[:54] + "..."
            desc = s.description if len(s.description) <= 180 else s.description[:177] + "..."
            with st.container(border=True):
                st.markdown(f"{badge}  \n**{title}**")
                st.caption(desc)
                if st.button("Use this suggestion", key=f"use_suggestion_{s.id}", use_container_width=True):
                    st.session_state.scenario_prefill_type = s.scenario_type
                    st.session_state.scenario_prefill_intent = s.suggested_intent
                    st.session_state.scenario_input_step = "context_review"
                    st.rerun()


# ── Page sections ──────────────────────────────────────────────────────────────

def _render_input_section() -> None:
    """Step 1: User enters description."""
    st.markdown("## Scenario Builder")
    st.markdown(
        "Describe the scenario you want to test. No formal rule syntax needed — "
        "just describe the account behaviour and what should trigger (or not trigger) an alert."
    )

    description = st.text_area(
        "Scenario description",
        placeholder="e.g. A customer makes frequent transfers to high-risk countries totalling over $10,000 in a month",
        height=120,
        key="scenario_description_input",
    )

    if st.button("Extract Context →", type="primary", disabled=not description.strip()):
        clear_status_log()
        with st.spinner("Checking for ambiguities…"):
            ambiguities = detect_ambiguities(description.strip())
        if ambiguities:
            st.session_state.scenario_ambiguities = ambiguities
            st.session_state.scenario_pending_description = description.strip()
            clear_card_state()
            st.rerun()
        else:
            _do_extract(description.strip())
        return

    # Show ambiguity resolution cards if detection flagged something on a prior run
    ambiguities = st.session_state.get("scenario_ambiguities", [])
    if ambiguities:
        pending = st.session_state.get("scenario_pending_description", "")

        resolutions = render_ambiguity_cards(ambiguities, pending)

        if resolutions is not None:
            # Apply or Skip — clear ambiguity state and proceed
            st.session_state.scenario_ambiguities = []
            st.session_state.scenario_pending_description = ""
            enriched = enrich_description(pending, resolutions) if resolutions else pending
            _do_extract(enriched)


def _do_extract(description: str) -> None:
    """Run extract_context, create session, and start suggestions prefetch before context review."""
    with st.spinner("Extracting context…"):
        ctx = extract_context(description)
    # Create the session now so suggestions start loading while the user reviews
    # context and picks scenario type. scenario_type doesn't affect suggestions.
    session = ScenarioSession(seed=ctx, scenario_type="risky")
    session.start_prefetch()
    st.session_state.scenario_context = ctx
    st.session_state.scenario_session = session
    st.session_state.scenario_result = None
    st.session_state.scenario_risky_proto = None
    st.session_state.scenario_genuine_proto = None
    st.session_state.scenario_input_step = "context_review"
    st.rerun()


def _render_context_review() -> None:
    """Step 2: User reviews extracted context and picks scenario type."""
    ctx: ScenarioContext = st.session_state.scenario_context
    session: ScenarioSession | None = st.session_state.get("scenario_session")

    main_col, suggestions_col = st.columns([3, 1.4], gap="large")

    if session is not None:
        with suggestions_col:
            _render_suggestions_panel(session)

    with main_col:
        st.markdown("## Extracted Context")
        st.markdown("Review what was extracted from your description. Click **← Back** to edit if something looks wrong.")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Rule Type", ctx.rule_type.capitalize())
            st.caption("**Relevant attributes:**")
            st.write(", ".join(ctx.relevant_attributes) if ctx.relevant_attributes else "None detected")
        with col2:
            if ctx.high_risk_countries:
                st.caption("**High-risk countries:**")
                st.write(", ".join(ctx.high_risk_countries))

        st.divider()

        scenario_type_options = ["risky", "genuine"]
        prefill_type = st.session_state.get("scenario_prefill_type")
        default_type_idx = scenario_type_options.index(prefill_type) if prefill_type in scenario_type_options else 0
        scenario_type = st.radio(
            "Scenario type",
            scenario_type_options,
            index=default_type_idx,
            horizontal=True,
            format_func=lambda x: "🔴 Risky (should trigger)" if x == "risky" else "🟢 Genuine (should not trigger)",
        )

        prefill_intent = st.session_state.get("scenario_prefill_intent", "")
        intent = st.text_input(
            "Intent (optional)",
            value=prefill_intent or "",
            placeholder="e.g. Gradual accumulation of transfers just above the threshold",
            key="scenario_intent_input",
        )
        st.session_state.scenario_prefill_type = None
        st.session_state.scenario_prefill_intent = None

        col_back, col_gen = st.columns([1, 3])
        with col_back:
            if st.button("← Back"):
                st.session_state.scenario_input_step = "input"
                st.rerun()
        with col_gen:
            if st.button("Generate Scenario →", type="primary"):
                _do_generate(ctx, scenario_type, intent)


def _do_generate(ctx: ScenarioContext, scenario_type: str, intent: str) -> None:
    """Generate the first scenario, reusing the pre-created session from _do_extract."""
    session: ScenarioSession | None = st.session_state.get("scenario_session")
    if session is None:
        session = ScenarioSession(seed=ctx, scenario_type=scenario_type)
        st.session_state.scenario_session = session
    else:
        # Update the scenario_type the user selected; suggestions are already loading
        session._scenario_type = scenario_type

    if ctx.rule_type == "stateless":
        with st.spinner("Generating prototypes…"):
            risky_proto, genuine_proto = session.generate_prototypes()
        st.session_state.scenario_risky_proto = risky_proto
        st.session_state.scenario_genuine_proto = genuine_proto
        st.session_state.scenario_result = None
    else:
        with st.spinner("Generating scenario…"):
            result = session.generate(intent=intent)
        st.session_state.scenario_result = result

    st.session_state.scenario_input_step = "result"
    st.rerun()


def _render_behavioral_result() -> None:
    """Step 3 (behavioral): Show transactions and allow refinement."""
    session: ScenarioSession = st.session_state.scenario_session
    result: ScenarioResult = st.session_state.scenario_result

    st.markdown(f"## Generated Scenario — {_SCENARIO_BADGE.get(session._scenario_type, '')}")

    if result.feedback_history:
        with st.expander(f"Feedback history ({len(result.feedback_history)} round(s))", expanded=False):
            for i, fb in enumerate(result.feedback_history, 1):
                st.caption(f"{i}. {fb}")

    _render_conflict_warnings(result)
    _render_transactions_table(result)

    st.divider()
    st.markdown("### Refine")
    feedback = st.text_area(
        "Feedback",
        placeholder="e.g. Make the amounts more varied and spread across multiple weeks",
        key="scenario_refine_input",
        height=80,
    )
    col_refine, col_new = st.columns([3, 1])
    with col_refine:
        if st.button("↻ Regenerate with feedback", disabled=not feedback.strip(), type="primary"):
            with st.spinner("Regenerating…"):
                new_result = session.refine(feedback.strip())
            st.session_state.scenario_result = new_result
            st.rerun()
    with col_new:
        if st.button("Start over"):
            st.session_state.scenario_input_step = "input"
            st.session_state.scenario_session = None
            st.session_state.scenario_result = None
            st.rerun()


def _render_stateless_result() -> None:
    """Step 3 (stateless): Show prototypes, allow refinement, then generate transactions."""
    session: ScenarioSession = st.session_state.scenario_session
    risky_proto = st.session_state.scenario_risky_proto
    genuine_proto = st.session_state.scenario_genuine_proto
    result: ScenarioResult | None = st.session_state.scenario_result

    if result is None:
        st.markdown("## Prototype Review")
        st.markdown("Review the example transaction profiles. Refine if needed, then generate transactions.")

        for proto, label in [(risky_proto, "Risky"), (genuine_proto, "Genuine")]:
            scenario_type = proto.scenario_type
            badge = _SCENARIO_BADGE.get(scenario_type, scenario_type)
            st.markdown(f"### {badge} {label} Prototype")
            st.json(proto.attributes)
            feedback = st.text_input(
                f"Refine {label} prototype",
                key=f"proto_feedback_{scenario_type}",
                placeholder="e.g. Make it look more like a business account",
            )
            if st.button(f"↻ Regenerate {label}", key=f"regen_proto_{scenario_type}"):
                with st.spinner(f"Regenerating {label} prototype…"):
                    updated, _ = session.refine_prototype(
                        scenario_type=scenario_type,
                        feedback=feedback,
                        current_prototype=proto,
                    )
                if scenario_type == "risky":
                    st.session_state.scenario_risky_proto = updated
                else:
                    st.session_state.scenario_genuine_proto = updated
                st.rerun()

        st.divider()
        col_n_risky, col_n_genuine, col_gen = st.columns([1, 1, 2])
        with col_n_risky:
            n_risky = st.number_input("# Risky", min_value=1, max_value=20, value=5, key="n_risky")
        with col_n_genuine:
            n_genuine = st.number_input("# Genuine", min_value=1, max_value=20, value=5, key="n_genuine")
        with col_gen:
            st.markdown("")
            if st.button("Generate Transactions →", type="primary"):
                with st.spinner("Generating transactions…"):
                    result = session.generate_from_prototypes(
                        risky_proto=st.session_state.scenario_risky_proto,
                        genuine_proto=st.session_state.scenario_genuine_proto,
                        n_risky=int(n_risky),
                        n_genuine=int(n_genuine),
                    )
                st.session_state.scenario_result = result
                st.rerun()
    else:
        st.markdown("## Generated Transactions")
        _render_transactions_table(result)
        if st.button("← Back to prototypes"):
            st.session_state.scenario_result = None
            st.rerun()


# ── Main render ────────────────────────────────────────────────────────────────

def render() -> None:
    step = st.session_state.get("scenario_input_step", "input")

    if step == "input":
        _render_input_section()
    elif step == "context_review":
        _render_context_review()
    elif step == "result":
        session: ScenarioSession | None = st.session_state.get("scenario_session")
        if session is None:
            st.session_state.scenario_input_step = "input"
            st.rerun()
        elif session.rule_type == "stateless":
            _render_stateless_result()
        else:
            _render_behavioral_result()
    else:
        st.session_state.scenario_input_step = "input"
        st.rerun()
