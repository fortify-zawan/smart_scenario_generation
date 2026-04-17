"""ScenarioSession — stateful scenario building session.

Owns the full conversation for one scenario:
- feedback history accumulation (never drops prior feedback)
- background suggestions prefetch thread
- behavioral: generate() / refine()
- stateless: generate_prototypes() / refine_prototype() / generate_from_prototypes()
"""
from __future__ import annotations

import threading
from typing import Union

from core.domain.models import (
    Prototype,
    Rule,
    ScenarioContext,
    ScenarioResult,
    TestSuggestion,
    Transaction,
)
from modules.scenario_builder.prototype import generate_prototypes as _gen_prototypes
from modules.scenario_builder.prototype import generate_single_prototype as _gen_single_proto
from modules.scenario_builder.generator import generate_behavioral_sequence, generate_stateless_sequence
from modules.scenario_builder.suggestions import generate_suggestions
from core.logging_config import get_logger

log = get_logger(__name__)


class ScenarioSession:
    """Manages a single scenario building conversation.

    seed can be:
    - ScenarioContext: standalone path — produced by extract_context()
    - Rule: pre-seeded path — produced by rule_parser, passed directly

    Usage (behavioral):
        session = ScenarioSession(seed=ctx_or_rule, scenario_type="risky")
        result = session.generate(intent="...")
        result = session.refine("make amounts higher")
        suggestions = session.get_suggestions()  # None if still loading

    Usage (stateless):
        session = ScenarioSession(seed=ctx_or_rule, scenario_type="risky")
        risky_proto, genuine_proto = session.generate_prototypes()
        risky_proto, conflicts = session.refine_prototype("risky", "more aggressive", risky_proto)
        result = session.generate_from_prototypes(risky_proto, genuine_proto, n_risky=5, n_genuine=5)
    """

    def __init__(self, seed: Union[ScenarioContext, Rule], scenario_type: str) -> None:
        self._seed = seed
        self._scenario_type = scenario_type
        # Behavioral feedback history (all rounds, never dropped)
        self._feedback_history: list[str] = []
        # Stateless: separate feedback per prototype type
        self._risky_feedback_history: list[str] = []
        self._genuine_feedback_history: list[str] = []
        # Background suggestions thread state
        self._suggestions: list[TestSuggestion] | None = None
        self._suggestions_done = threading.Event()
        self._prefetch_started = False

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def rule_type(self) -> str:
        """"stateless" or "behavioral" — derived from the seed."""
        return self._seed.rule_type

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _as_rule(self) -> Rule:
        """Return the seed as a Rule.

        If seed is ScenarioContext, wraps it in a minimal Rule with empty
        conditions and computed_attrs so the existing generators work without
        any modification. The generators only read:
        - rule.raw_expression     <- context.description
        - rule.relevant_attributes
        - rule.high_risk_countries
        - rule.computed_attrs     <- [] (used only for attribute set computation)
        - rule.conditions         <- [] (used only for attribute set computation)
        """
        if isinstance(self._seed, Rule):
            return self._seed
        return Rule(
            description=self._seed.description,
            rule_type=self._seed.rule_type,
            relevant_attributes=self._seed.relevant_attributes,
            conditions=[],
            raw_expression=self._seed.description,
            high_risk_countries=self._seed.high_risk_countries,
        )

    def start_prefetch(self) -> None:
        """Start background suggestions prefetch. No-op if already started.

        Called automatically by generate() and generate_prototypes(), but can
        also be called earlier (e.g. right after __init__) to begin loading
        suggestions before the user triggers generation.
        """
        if self._prefetch_started:
            return
        self._prefetch_started = True
        rule = self._as_rule()

        def _worker() -> None:
            try:
                results = generate_suggestions(rule)
            except Exception as exc:
                log.error("ScenarioSession | suggestions prefetch failed: %s", exc)
                results = []
            self._suggestions = results
            self._suggestions_done.set()
            log.info("ScenarioSession | suggestions prefetch done, count=%d", len(results))

        t = threading.Thread(target=_worker, daemon=True, name="scenario-suggestion-loader")
        t.start()

    # keep private alias for the two internal callers
    _start_prefetch = start_prefetch

    # ── Behavioral path ────────────────────────────────────────────────────────

    def generate(self, intent: str) -> ScenarioResult:
        """Generate a behavioral scenario. Also kicks off the background suggestions prefetch.

        This is the first call for behavioral rules. Call refine() for subsequent rounds.
        """
        rule = self._as_rule()
        transactions, conflicts = generate_behavioral_sequence(
            rule=rule,
            scenario_type=self._scenario_type,
            intent=intent,
            feedback_history=list(self._feedback_history),
        )
        self._start_prefetch()
        return ScenarioResult(
            transactions=transactions,
            conflict_warnings=conflicts,
            feedback_history=list(self._feedback_history),
        )

    def refine(self, feedback: str) -> ScenarioResult:
        """Accumulate feedback and regenerate the behavioral scenario.

        All prior feedback strings are preserved — earlier instructions are never dropped.
        """
        self._feedback_history.append(feedback)
        rule = self._as_rule()
        transactions, conflicts = generate_behavioral_sequence(
            rule=rule,
            scenario_type=self._scenario_type,
            intent="",
            feedback_history=list(self._feedback_history),
        )
        return ScenarioResult(
            transactions=transactions,
            conflict_warnings=conflicts,
            feedback_history=list(self._feedback_history),
        )

    # ── Stateless path ─────────────────────────────────────────────────────────

    def generate_prototypes(self) -> tuple[Prototype, Prototype]:
        """Generate a risky + genuine prototype pair for stateless rules.

        Also kicks off the background suggestions prefetch.
        Returns (risky_prototype, genuine_prototype).
        """
        rule = self._as_rule()
        risky, genuine = _gen_prototypes(rule)
        self._start_prefetch()
        return risky, genuine

    def refine_prototype(
        self,
        scenario_type: str,
        feedback: str,
        current_prototype: Prototype,
    ) -> tuple[Prototype, list[dict]]:
        """Regenerate a single prototype with accumulated feedback.

        Args:
            scenario_type: "risky" or "genuine"
            feedback:       New feedback string to add
            current_prototype: The prototype from the last round

        Returns:
            (updated_prototype, conflict_warnings)
        """
        if scenario_type == "risky":
            self._risky_feedback_history.append(feedback)
            history = list(self._risky_feedback_history)
        else:
            self._genuine_feedback_history.append(feedback)
            history = list(self._genuine_feedback_history)

        rule = self._as_rule()
        updated, conflicts = _gen_single_proto(
            rule=rule,
            scenario_type=scenario_type,
            feedback_history=history,
            current_attrs=current_prototype.attributes,
        )
        return updated, conflicts

    def generate_from_prototypes(
        self,
        risky_proto: Prototype,
        genuine_proto: Prototype,
        n_risky: int,
        n_genuine: int,
    ) -> ScenarioResult:
        """Generate stateless transactions from approved prototypes."""
        rule = self._as_rule()
        transactions = generate_stateless_sequence(
            rule=rule,
            risky_proto=risky_proto,
            genuine_proto=genuine_proto,
            n_risky=n_risky,
            n_genuine=n_genuine,
        )
        return ScenarioResult(transactions=transactions)

    # ── Suggestions ────────────────────────────────────────────────────────────

    def get_suggestions(self) -> list[TestSuggestion] | None:
        """Return suggestions if background prefetch is complete, None if still loading.

        The UI should call this on each rerun and show a spinner until it returns non-None.
        """
        return self._suggestions if self._suggestions_done.is_set() else None

    @property
    def suggestions_ready(self) -> bool:
        """True once the background suggestions prefetch thread has finished."""
        return self._suggestions_done.is_set()
