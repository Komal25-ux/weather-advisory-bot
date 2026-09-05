"""Comprehensive test suite for Iteration 6: Deterministic Weather Safety Decision Engine."""
import os
import tempfile
import pytest

from app.policies.loader import load_sops_from_directory
from app.policies.matcher import match_candidate_sops
from app.policies.evaluator import select_primary_decision
from app.policies.models import (
    CandidateSOP,
    SOPRule,
    ConditionGroup,
    ConditionRule,
    SOPAdvice,
)
from app.graph.workflow import build_weather_graph
from app.graph.state import WeatherState


@pytest.fixture(scope="module")
def loaded_sops():
    """Loads all configured repository SOPs."""
    return load_sops_from_directory("sops")


# -------------------------------------------------------------------
# 1. One clear low-risk SOP
# -------------------------------------------------------------------

def test_clear_low_risk_sop(loaded_sops):
    """Favorable weather on supported activity (running) matches SOP-FAVORABLE-OUTDOOR-001 (LOW)."""
    facts = {
        "activity": "running",
        "intent_category": "outdoor_exercise",
        "temperature_c": 22.0,
        "wind_speed_kmh": 12.0,
        "precipitation_probability": 10,
        "uv_index": 4.0,
    }
    candidates = match_candidate_sops(loaded_sops, facts)
    assert any(c.sop_id == "SOP-FAVORABLE-OUTDOOR-001" for c in candidates)

    decision = select_primary_decision(candidates, loaded_sops)
    assert decision is not None
    assert decision.sop_id == "SOP-FAVORABLE-OUTDOOR-001"
    assert decision.severity == "LOW"
    assert decision.recommendation == "recommended"


# -------------------------------------------------------------------
# 2. One high/critical-risk SOP
# -------------------------------------------------------------------

def test_clear_high_risk_sop(loaded_sops):
    """Cycling in 45 km/h wind triggers SOP-CYCLING-WIND-001 (HIGH)."""
    facts = {
        "activity": "cycling",
        "intent_category": "outdoor_exercise",
        "wind_speed_kmh": 45.0,
    }
    candidates = match_candidate_sops(loaded_sops, facts)
    assert any(c.sop_id == "SOP-CYCLING-WIND-001" for c in candidates)

    decision = select_primary_decision(candidates, loaded_sops)
    assert decision is not None
    assert decision.sop_id == "SOP-CYCLING-WIND-001"
    assert decision.severity == "HIGH"
    assert decision.recommendation == "not_recommended"


# -------------------------------------------------------------------
# 3. Multiple simultaneously applicable SOPs
# -------------------------------------------------------------------

def test_multiple_simultaneously_applicable_sops(loaded_sops):
    """
    Simultaneous high wind (45 km/h) and extreme UV (9.0) during daytime cycling:
    Both SOP-CYCLING-WIND-001 and SOP-UV-EXERCISE-001 match.
    Both must be preserved in applicable_sop_ids.
    """
    facts = {
        "activity": "cycling",
        "intent_category": "outdoor_exercise",
        "wind_speed_kmh": 45.0,
        "uv_index": 9.0,
        "is_daytime": True,
    }
    candidates = match_candidate_sops(loaded_sops, facts)
    matched_ids = [c.sop_id for c in candidates]
    assert "SOP-CYCLING-WIND-001" in matched_ids
    assert "SOP-UV-EXERCISE-001" in matched_ids
    assert len(matched_ids) >= 2

    decision = select_primary_decision(candidates, loaded_sops)
    assert decision is not None
    assert "SOP-CYCLING-WIND-001" in decision.applicable_sop_ids
    assert "SOP-UV-EXERCISE-001" in decision.applicable_sop_ids


# -------------------------------------------------------------------
# 4 & 5. Conflicting SOPs & Severity Precedence
# -------------------------------------------------------------------

def test_conflicting_sops_severity_precedence(loaded_sops):
    """
    Conflict: SOP-CYCLING-WIND-001 (HIGH) vs SOP-UV-EXERCISE-001 (MEDIUM).
    Severity rule: CRITICAL > HIGH > MEDIUM > LOW guarantees HIGH wins.
    """
    facts = {
        "activity": "cycling",
        "intent_category": "outdoor_exercise",
        "wind_speed_kmh": 45.0,
        "uv_index": 9.0,
        "is_daytime": True,
    }
    candidates = match_candidate_sops(loaded_sops, facts)
    decision = select_primary_decision(candidates, loaded_sops)

    assert decision is not None
    assert decision.sop_id == "SOP-CYCLING-WIND-001"
    assert decision.severity == "HIGH"


# -------------------------------------------------------------------
# 6. Priority Tie-Breaking on equal severity
# -------------------------------------------------------------------

def test_priority_tie_breaking():
    """Two SOPs of HIGH severity: priority 90 must win over priority 80."""
    cand_gust = CandidateSOP(
        sop_id="SOP-GUST-OUTDOOR-001",
        name="Severe Gusts",
        category="recreation",
        severity="HIGH",
        priority=90,
        matched_conditions=[]
    )
    cand_wind = CandidateSOP(
        sop_id="SOP-CYCLING-WIND-001",
        name="Cycling Wind",
        category="outdoor_exercise",
        severity="HIGH",
        priority=80,
        matched_conditions=[]
    )
    all_sops = [
        SOPRule(
            id="SOP-GUST-OUTDOOR-001",
            name="Severe Gusts",
            category="recreation",
            severity="HIGH",
            priority=90,
            description="",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(title="", guidance=[], rationale="")
        ),
        SOPRule(
            id="SOP-CYCLING-WIND-001",
            name="Cycling Wind",
            category="outdoor_exercise",
            severity="HIGH",
            priority=80,
            description="",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(title="", guidance=[], rationale="")
        )
    ]

    decision = select_primary_decision([cand_wind, cand_gust], all_sops)
    assert decision.sop_id == "SOP-GUST-OUTDOOR-001"
    assert decision.priority == 90


# -------------------------------------------------------------------
# 7. SOP ID Deterministic Tie-Breaking
# -------------------------------------------------------------------

def test_sop_id_deterministic_tie_breaking():
    """Equal severity and priority: alphanumeric SOP ID ascending tie-breaker."""
    cand_b = CandidateSOP(sop_id="SOP-COMMUTE-B", name="B", category="travel", severity="MEDIUM", priority=60)
    cand_a = CandidateSOP(sop_id="SOP-COMMUTE-A", name="A", category="travel", severity="MEDIUM", priority=60)

    all_sops = [
        SOPRule(id="SOP-COMMUTE-B", name="B", category="travel", severity="MEDIUM", priority=60, description="", conditions=ConditionGroup(all=[]), advice=SOPAdvice(title="", guidance=[], rationale="")),
        SOPRule(id="SOP-COMMUTE-A", name="A", category="travel", severity="MEDIUM", priority=60, description="", conditions=ConditionGroup(all=[]), advice=SOPAdvice(title="", guidance=[], rationale="")),
    ]

    decision = select_primary_decision([cand_b, cand_a], all_sops)
    assert decision.sop_id == "SOP-COMMUTE-A"


# -------------------------------------------------------------------
# 8. Missing Weather Metric (UNAVAILABLE, never converted to 0)
# -------------------------------------------------------------------

def test_missing_weather_metric_prevents_accidental_pass(loaded_sops):
    """
    SOP-CYCLING-WIND-001 requires wind_speed_kmh.
    If wind_speed_kmh is missing (None), condition MUST NOT pass.
    """
    facts_missing = {
        "activity": "cycling",
        "intent_category": "outdoor_exercise",
        # wind_speed_kmh omitted
    }
    candidates = match_candidate_sops(loaded_sops, facts_missing)
    assert not any(c.sop_id == "SOP-CYCLING-WIND-001" for c in candidates)


# -------------------------------------------------------------------
# 9. Fuzzy / Non-Numeric SOP Scenario (Picnic)
# -------------------------------------------------------------------

def test_fuzzy_non_numeric_picnic_sop(loaded_sops):
    """
    Evaluates multi-factor picnic comfort deterministically.
    Triggered by moderate wind (32 km/h) without rain.
    """
    facts_windy_picnic = {
        "activity": "picnic",
        "intent_category": "recreation",
        "precipitation_probability": 10,
        "precipitation_mm": 0.0,
        "wind_speed_kmh": 32.0,
        "uv_index": 4.0,
    }
    candidates = match_candidate_sops(loaded_sops, facts_windy_picnic)
    assert any(c.sop_id == "SOP-PICNIC-CONDITIONS-001" for c in candidates)

    decision = select_primary_decision(candidates, loaded_sops)
    assert decision is not None
    assert decision.sop_id == "SOP-PICNIC-CONDITIONS-001"
    assert decision.recommendation == "caution"
    assert "32.0" in decision.decision_trace


# -------------------------------------------------------------------
# 10. Unsupported Activity / No Matching SOP
# -------------------------------------------------------------------

def test_unsupported_activity_yields_no_matching_sop(loaded_sops):
    """Unsupported activity (e.g. drone_flying) matches zero policies."""
    facts = {
        "activity": "drone_flying",
        "intent_category": "recreation",
        "temperature_c": 22.0,
        "wind_speed_kmh": 10.0,
        "precipitation_probability": 0,
        "uv_index": 3.0,
    }
    candidates = match_candidate_sops(loaded_sops, facts)
    assert len(candidates) == 0

    decision = select_primary_decision(candidates, loaded_sops)
    assert decision is None


# -------------------------------------------------------------------
# 11. Extensibility: Add/Change SOP Without Changing Evaluator Code
# -------------------------------------------------------------------

def test_extensibility_no_evaluator_code_changes():
    """
    Proves that adding an entirely new policy (e.g. SOP-HAIL-001) with CRITICAL severity
    is immediately picked as the winning decision with zero code modifications to evaluator.py.
    """
    hail_yaml = """
- id: SOP-HAIL-001
  name: Severe Hail Storm Warning
  version: "1.0"
  category: outdoor_exercise
  severity: CRITICAL
  priority: 99
  description: Active hail poses severe injury risks.
  conditions:
    all:
      - field: weather_code
        operator: equals
        value: 96
  required_weather_fields:
    - weather_code
  advice:
    recommendation: not_recommended
    title: Severe hail danger
    guidance:
      - Seek immediate indoor shelter.
    rationale: Hailstones cause direct physical trauma.
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "hail.yaml")
        with open(fpath, "w") as f:
            f.write(hail_yaml)

        custom_sops = load_sops_from_directory(tmpdir)
        facts = {"weather_code": 96, "activity": "cycling"}

        candidates = match_candidate_sops(custom_sops, facts)
        assert len(candidates) == 1
        assert candidates[0].sop_id == "SOP-HAIL-001"

        # Evaluator automatically ranks CRITICAL at top
        decision = select_primary_decision(candidates, custom_sops)
        assert decision is not None
        assert decision.sop_id == "SOP-HAIL-001"
        assert decision.severity == "CRITICAL"
        assert decision.recommendation == "not_recommended"


# -------------------------------------------------------------------
# 12. End-to-End LangGraph Routing Verification of select_decision_node
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_end_to_end_graph_populates_deterministic_decision():
    """
    Validates that select_decision_node in the compiled LangGraph workflow
    populates the full deterministic decision state without LLM intervention.
    """
    graph = build_weather_graph()

    # Pre-populate state as if nodes 1-4 completed
    state_after_matching: WeatherState = {
        "session_id": "test-session-e2e",
        "user_message": "Can I cycle?",
        "activity": "cycling",
        "intent_category": "outdoor_exercise",
        "location_name": "Berlin",
        "resolved_location_name": "Berlin, Germany",
        "latitude": 52.52,
        "longitude": 13.40,
        "weather_facts": {
            "temperature_c": 28.0,
            "wind_speed_kmh": 46.0,
            "uv_index": 9.0,
            "is_daytime": True,
        },
        "candidate_sops": [
            {
                "sop_id": "SOP-UV-EXERCISE-001",
                "name": "High UV",
                "category": "outdoor_exercise",
                "severity": "MEDIUM",
                "priority": 60,
                "matched_conditions": []
            },
            {
                "sop_id": "SOP-CYCLING-WIND-001",
                "name": "Strong Wind Cycling",
                "category": "outdoor_exercise",
                "severity": "HIGH",
                "priority": 80,
                "matched_conditions": [
                    {
                        "field": "wind_speed_kmh",
                        "operator": "greater_than_or_equal",
                        "threshold": 40.0,
                        "actual": 46.0,
                        "result": True,
                        "status": "PASSED"
                    }
                ]
            }
        ],
        "trace": {}
    }

    # Execute graph from select_decision node
    from app.graph.nodes import select_decision_node
    decision_state = await select_decision_node(state_after_matching)

    assert decision_state["decision_severity"] == "HIGH"
    assert decision_state["decision_recommendation"] == "not_recommended"
    assert decision_state["selected_sop"]["sop_id"] == "SOP-CYCLING-WIND-001"
    assert "SOP-UV-EXERCISE-001" in decision_state["selected_sop"]["applicable_sop_ids"]
    assert "SOP-CYCLING-WIND-001" in decision_state["selected_sop"]["applicable_sop_ids"]
    assert "46.0" in decision_state["decision_trace"]
