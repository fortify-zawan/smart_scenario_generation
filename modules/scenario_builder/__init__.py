"""Scenario Builder module — public API.

Standalone path (user provides free-form description):
    from modules.scenario_builder import extract_context, ScenarioSession

    ctx = extract_context("transfers to Iran exceeding $5000 in 30 days")
    session = ScenarioSession(seed=ctx, scenario_type="risky")
    result = session.generate(intent="gradual accumulation")
    result = session.refine("make the amounts more varied")
    suggestions = session.get_suggestions()  # None if still loading

Pre-seeded path (Rule from rule_parser):
    from modules.scenario_builder import ScenarioSession

    session = ScenarioSession(seed=rule, scenario_type="risky")
    result = session.generate(intent="boundary case")
"""
from modules.scenario_builder.extractor import extract_context
from modules.scenario_builder.session import ScenarioSession
from modules.scenario_builder.suggestions import generate_suggestions

__all__ = ["extract_context", "ScenarioSession", "generate_suggestions"]
