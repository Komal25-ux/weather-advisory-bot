"""Comprehensive test suite for Iteration 2: SOP loader, generic matcher, and deterministic evaluator."""
import os
import tempfile
import pytest
import yaml

from app.policies.loader import load_sops_from_directory, SOPPolicyLoadError
from app.policies.matcher import (
    evaluate_atomic_condition,
    evaluate_sop,
    match_candidate_sops,
    PolicyEvaluationError,
)
from app.policies.evaluator import select_primary_decision
from app.policies.models import (
    ConditionRule,
    ConditionGroup,
    SOPRule,
    SOPAdvice,
    CandidateSOP,
    MatchedCondition,
)


# -------------------------------------------------------------------
# 1. Operators Testing (All 9 operators)
# -------------------------------------------------------------------

@pytest.mark.parametrize(
    "op, actual, expected, expected_result",
    [
        ("equals", "cycling", "cycling", True),
        ("equals", "Cycling", "cycling", True),  # Case-insensitive
        ("equals", "running", "cycling", False),
        ("not_equals", "running", "cycling", True),
        ("not_equals", "cycling", "cycling", False),
        ("greater_than", 45.0, 40.0, True),
        ("greater_than", 40.0, 40.0, False),
        ("greater_than_or_equal", 40.0, 40.0, True),
        ("greater_than_or_equal", 39.9, 40.0, False),
        ("less_than", 20.0, 25.0, True),
        ("less_than", 25.0, 25.0, False),
        ("less_than_or_equal", 25.0, 25.0, True),
        ("less_than_or_equal", 25.1, 25.0, False),
        ("in", "scooter", ["two_wheeler", "scooter", "motorbike"], True),
        ("in", "Scooter", ["two_wheeler", "scooter", "motorbike"], True),
        ("in", "car", ["two_wheeler", "scooter", "motorbike"], False),
        ("not_in", "car", ["two_wheeler", "scooter"], True),
        ("not_in", "scooter", ["two_wheeler", "scooter"], False),
        ("between", 22.0, [15.0, 30.0], True),
        ("between", 15.0, [15.0, 30.0], True),
        ("between", 30.0, [15.0, 30.0], True),
        ("between", 35.0, [15.0, 30.0], False),
    ],
)
def test_all_atomic_operators(op, actual, expected, expected_result):
    cond = ConditionRule(field="test_field", operator=op, value=expected)
    facts = {"test_field": actual}
    matched = evaluate_atomic_condition(cond, facts)
    assert matched.result == expected_result
    assert matched.status == ("PASSED" if expected_result else "FAILED")


def test_unsupported_operator_raises():
    cond = ConditionRule(field="wind", operator="equals", value=10)
    # Manually bypass pydantic validation to test runtime engine guard
    cond.__dict__["operator"] = "regex_match"
    with pytest.raises(PolicyEvaluationError):
        evaluate_atomic_condition(cond, {"wind": 10})


# -------------------------------------------------------------------
# 2. Missing Fields Handling (UNAVAILABLE, never silent 0 or false safe)
# -------------------------------------------------------------------

def test_missing_field_in_facts():
    cond = ConditionRule(field="uv_index", operator="greater_than_or_equal", value=8.0)
    facts = {"temperature_c": 30.0}  # uv_index missing
    matched = evaluate_atomic_condition(cond, facts)
    assert matched.result is False
    assert matched.status == "UNAVAILABLE"
    assert matched.actual is None


def test_required_weather_field_missing_prevents_evaluation():
    sop = SOPRule(
        id="SOP-TEST-UV-001",
        name="Test UV Policy",
        category="outdoor_exercise",
        severity="MEDIUM",
        priority=50,
        description="Requires UV field",
        conditions=ConditionGroup(
            all=[ConditionRule(field="activity", operator="equals", value="running")]
        ),
        required_weather_fields=["uv_index"],
        advice=SOPAdvice(
            recommendation="caution",
            title="UV Warning",
            guidance=["Wear sunscreen"],
            rationale="UV hazard"
        )
    )
    facts_without_uv = {"activity": "running"}
    matched, audit = evaluate_sop(sop, facts_without_uv)
    assert matched is False
    assert len(audit) == 1
    assert audit[0].status == "UNAVAILABLE"
    assert audit[0].field == "uv_index"


# -------------------------------------------------------------------
# 3. Logical Condition Groups (ALL / ANY)
# -------------------------------------------------------------------

def test_and_conditions_all():
    sop = SOPRule(
        id="SOP-CYCLING-WIND-001",
        name="Wind and Cycling",
        category="outdoor_exercise",
        severity="HIGH",
        priority=80,
        description="High wind cycling",
        conditions=ConditionGroup(
            all=[
                ConditionRule(field="activity", operator="equals", value="cycling"),
                ConditionRule(field="wind_speed_kmh", operator="greater_than_or_equal", value=40.0)
            ]
        ),
        required_weather_fields=["wind_speed_kmh"],
        advice=SOPAdvice(
            recommendation="not_recommended",
            title="Wind warning",
            guidance=["Do not cycle"],
            rationale="Unsafe"
        )
    )

    # 1. Both pass -> Matched
    facts_match = {"activity": "cycling", "wind_speed_kmh": 45.0}
    matched, _ = evaluate_sop(sop, facts_match)
    assert matched is True

    # 2. Activity fails -> Fails
    facts_fail_act = {"activity": "running", "wind_speed_kmh": 45.0}
    matched, _ = evaluate_sop(sop, facts_fail_act)
    assert matched is False

    # 3. Wind fails -> Fails
    facts_fail_wind = {"activity": "cycling", "wind_speed_kmh": 25.0}
    matched, _ = evaluate_sop(sop, facts_fail_wind)
    assert matched is False


def test_or_conditions_any():
    # Fuzzy picnic SOP: activity == picnic AND ANY(rain, high wind, high UV)
    sop = SOPRule(
        id="SOP-PICNIC-001",
        name="Picnic Policy",
        category="recreation",
        severity="MEDIUM",
        priority=65,
        description="Picnic check",
        conditions=ConditionGroup(
            all=[ConditionRule(field="activity", operator="equals", value="picnic")],
            any=[
                ConditionRule(field="precipitation_mm", operator="greater_than", value=0.0),
                ConditionRule(field="wind_speed_kmh", operator="greater_than_or_equal", value=30.0),
                ConditionRule(field="uv_index", operator="greater_than_or_equal", value=8.0)
            ]
        ),
        required_weather_fields=["precipitation_mm", "wind_speed_kmh", "uv_index"],
        advice=SOPAdvice(
            recommendation="caution",
            title="Picnic suboptimal",
            guidance=["Consider indoor"],
            rationale="Bad weather"
        )
    )

    # Triggered by wind only
    matched, _ = evaluate_sop(sop, {
        "activity": "picnic",
        "precipitation_mm": 0.0,
        "wind_speed_kmh": 32.0,
        "uv_index": 5.0
    })
    assert matched is True

    # Triggered by precipitation only
    matched, _ = evaluate_sop(sop, {
        "activity": "picnic",
        "precipitation_mm": 2.0,
        "wind_speed_kmh": 15.0,
        "uv_index": 4.0
    })
    assert matched is True

    # None of any matched -> False
    matched, _ = evaluate_sop(sop, {
        "activity": "picnic",
        "precipitation_mm": 0.0,
        "wind_speed_kmh": 12.0,
        "uv_index": 5.0
    })
    assert matched is False


# -------------------------------------------------------------------
# 4. Deterministic Evaluator & Conflict Resolution
# -------------------------------------------------------------------

def test_evaluator_severity_ranking_high_beats_medium():
    cand_high = CandidateSOP(
        sop_id="SOP-WIND-HIGH",
        name="High Wind",
        category="outdoor_exercise",
        severity="HIGH",
        priority=50,
        matched_conditions=[]
    )
    cand_med = CandidateSOP(
        sop_id="SOP-UV-MED",
        name="High UV",
        category="outdoor_exercise",
        severity="MEDIUM",
        priority=90,  # Higher priority but lower severity
        matched_conditions=[]
    )

    all_sops = [
        SOPRule(
            id="SOP-WIND-HIGH",
            name="High Wind",
            category="outdoor_exercise",
            severity="HIGH",
            priority=50,
            description="",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(title="High Wind", guidance=[], rationale="")
        ),
        SOPRule(
            id="SOP-UV-MED",
            name="High UV",
            category="outdoor_exercise",
            severity="MEDIUM",
            priority=90,
            description="",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(title="High UV", guidance=[], rationale="")
        )
    ]

    decision = select_primary_decision([cand_med, cand_high], all_sops)
    assert decision is not None
    assert decision.sop_id == "SOP-WIND-HIGH"
    assert decision.severity == "HIGH"


def test_evaluator_priority_tie_breaking():
    cand1 = CandidateSOP(
        sop_id="SOP-HEAT-1",
        name="Heat Standard",
        category="outdoor_exercise",
        severity="HIGH",
        priority=70,
        matched_conditions=[]
    )
    cand2 = CandidateSOP(
        sop_id="SOP-HEAT-2",
        name="Heat Critical Alert",
        category="outdoor_exercise",
        severity="HIGH",
        priority=95,
        matched_conditions=[]
    )

    all_sops = [
        SOPRule(
            id="SOP-HEAT-1",
            name="Heat Standard",
            category="outdoor_exercise",
            severity="HIGH",
            priority=70,
            description="",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(title="Standard", guidance=[], rationale="")
        ),
        SOPRule(
            id="SOP-HEAT-2",
            name="Heat Critical Alert",
            category="outdoor_exercise",
            severity="HIGH",
            priority=95,
            description="",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(title="Critical", guidance=[], rationale="")
        )
    ]

    decision = select_primary_decision([cand1, cand2], all_sops)
    assert decision is not None
    assert decision.sop_id == "SOP-HEAT-2"
    assert decision.priority == 95


def test_evaluator_id_tie_breaking():
    cand_b = CandidateSOP(
        sop_id="SOP-B",
        name="Policy B",
        category="travel",
        severity="HIGH",
        priority=80,
        matched_conditions=[]
    )
    cand_a = CandidateSOP(
        sop_id="SOP-A",
        name="Policy A",
        category="travel",
        severity="HIGH",
        priority=80,
        matched_conditions=[]
    )

    all_sops = [
        SOPRule(
            id="SOP-B",
            name="Policy B",
            category="travel",
            severity="HIGH",
            priority=80,
            description="",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(title="B", guidance=[], rationale="")
        ),
        SOPRule(
            id="SOP-A",
            name="Policy A",
            category="travel",
            severity="HIGH",
            priority=80,
            description="",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(title="A", guidance=[], rationale="")
        )
    ]

    decision = select_primary_decision([cand_b, cand_a], all_sops)
    assert decision is not None
    assert decision.sop_id == "SOP-A"  # "SOP-A" < "SOP-B"


# -------------------------------------------------------------------
# 5. Production SOP Directory Loading (12 baseline SOPs)
# -------------------------------------------------------------------

def test_load_all_12_baseline_sops():
    sops = load_sops_from_directory("sops")
    assert len(sops) >= 12

    # Check categories covered
    categories = {sop.category for sop in sops}
    assert "outdoor_exercise" in categories
    assert "travel" in categories
    assert "vulnerable_groups" in categories
    assert "recreation" in categories

    # Check severities covered
    severities = {sop.severity for sop in sops}
    assert "LOW" in severities
    assert "MEDIUM" in severities
    assert "HIGH" in severities


# -------------------------------------------------------------------
# 6. Critical Extensibility Test: Add SOP #13 (SOP-FOG-001)
# -------------------------------------------------------------------

def test_critical_extensibility_add_sop_without_code_changes():
    """
    Demonstrates adding a 13th SOP (SOP-FOG-001) via external YAML only.
    The matcher and evaluator immediately evaluate it without any code modifications.
    """
    fog_sop_yaml = """
- id: SOP-FOG-001
  name: Dense Fog Low Visibility Warning
  version: "1.0"
  category: recreation
  severity: HIGH
  priority: 92
  description: Dense fog with visibility under 1 km poses high collision hazards.
  conditions:
    all:
      - field: visibility_km
        operator: less_than
        value: 1.0
  required_weather_fields:
    - visibility_km
  advice:
    recommendation: not_recommended
    title: Outdoor activities are not recommended due to dense fog
    guidance:
      - Postpone outdoor activities until visibility improves.
      - Wear high-visibility fluorescent apparel if outdoor presence is mandatory.
    rationale: Visibility below 1.0 km significantly impairs visual reaction time.
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save baseline recreation SOPs and the new SOP-FOG-001 into tmpdir
        fog_file = os.path.join(tmpdir, "fog.yaml")
        with open(fog_file, "w") as f:
            f.write(fog_sop_yaml)

        # 1. Loader automatically validates and loads it
        loaded_sops = load_sops_from_directory(tmpdir)
        assert len(loaded_sops) == 1
        assert loaded_sops[0].id == "SOP-FOG-001"

        # 2. Matcher evaluates it against visibility facts with ZERO code changes
        facts_fog = {"visibility_km": 0.4}
        candidates = match_candidate_sops(loaded_sops, facts_fog)
        assert len(candidates) == 1
        assert candidates[0].sop_id == "SOP-FOG-001"

        # 3. Evaluator selects it deterministically
        decision = select_primary_decision(candidates, loaded_sops)
        assert decision is not None
        assert decision.sop_id == "SOP-FOG-001"
        assert decision.recommendation == "not_recommended"
        assert decision.severity == "HIGH"
