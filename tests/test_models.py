"""Test suite for Iteration 1 data models and schema validation."""
import pytest
from pydantic import ValidationError

from app.schemas.intent import StructuredIntent
from app.schemas.weather import WeatherFacts
from app.schemas.api import ChatRequest, ChatResponse, HealthResponse, TraceResponse
from app.policies.models import (
    SOPRule,
    ConditionRule,
    ConditionGroup,
    SOPAdvice,
    MatchedCondition,
    CandidateSOP,
    DeterministicDecision,
)
from app.graph.state import WeatherState


def test_structured_intent_valid():
    intent = StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location="Bhopal",
        time_reference="today",
        target_group="general",
        confidence=0.95,
        is_clarification_needed=False
    )
    assert intent.activity == "cycling"
    assert intent.location == "Bhopal"
    assert intent.confidence == 0.95


def test_weather_facts_valid():
    facts = WeatherFacts(
        temperature_c=28.5,
        wind_speed_kmh=42.0,
        wind_gusts_kmh=55.0,
        precipitation_mm=1.5,
        precipitation_probability=65,
        uv_index=7.2,
        target_period="today",
        is_daytime=True
    )
    assert facts.temperature_c == 28.5
    assert facts.wind_speed_kmh == 42.0
    assert facts.precipitation_probability == 65


def test_sop_rule_and_conditions_valid():
    cond1 = ConditionRule(
        field="activity",
        operator="equals",
        value="cycling"
    )
    cond2 = ConditionRule(
        field="wind_speed_kmh",
        operator="greater_than_or_equal",
        value=40.0
    )
    advice = SOPAdvice(
        recommendation="not_recommended",
        title="High Wind Cycling Warning",
        guidance=["Avoid cycling in strong winds."],
        rationale="Strong winds make two-wheeled balance hazardous."
    )
    sop = SOPRule(
        id="SOP-CYCLING-WIND-001",
        name="Strong Wind and Cycling",
        version="1.0",
        category="outdoor_exercise",
        severity="HIGH",
        priority=80,
        description="Cycling is unsafe when winds reach 40 km/h.",
        conditions=ConditionGroup(all=[cond1, cond2]),
        required_weather_fields=["wind_speed_kmh"],
        advice=advice
    )
    assert sop.id == "SOP-CYCLING-WIND-001"
    assert sop.severity == "HIGH"
    assert sop.priority == 80
    assert len(sop.conditions.all) == 2


def test_sop_rule_invalid_severity():
    with pytest.raises(ValidationError):
        SOPRule(
            id="INVALID-001",
            name="Invalid Severity Policy",
            category="general",
            severity="EXTREME",  # Invalid, only CRITICAL, HIGH, MEDIUM, LOW allowed
            priority=50,
            description="Testing invalid severity",
            conditions=ConditionGroup(all=[]),
            advice=SOPAdvice(
                recommendation="caution",
                title="Title",
                guidance=[],
                rationale="Rationale"
            )
        )


def test_candidate_sop_and_decision_models():
    matched_cond = MatchedCondition(
        field="wind_speed_kmh",
        operator="greater_than_or_equal",
        threshold=40.0,
        actual=42.0,
        result=True,
        status="PASSED"
    )
    candidate = CandidateSOP(
        sop_id="SOP-CYCLING-WIND-001",
        name="Strong Wind and Cycling",
        category="outdoor_exercise",
        severity="HIGH",
        priority=80,
        matched_conditions=[matched_cond]
    )
    assert candidate.sop_id == "SOP-CYCLING-WIND-001"
    assert len(candidate.matched_conditions) == 1

    decision = DeterministicDecision(
        sop_id=candidate.sop_id,
        sop_name=candidate.name,
        severity=candidate.severity,
        recommendation="not_recommended",
        priority=candidate.priority,
        matched_conditions=candidate.matched_conditions,
        guidance=["Avoid cycling."],
        rationale="High wind risk.",
        decision_trace="wind_speed_kmh (42.0) >= 40.0"
    )
    assert decision.recommendation == "not_recommended"
    assert decision.severity == "HIGH"


def test_api_models():
    req = ChatRequest(
        session_id="session-123",
        message="Can I cycle today?"
    )
    assert req.session_id == "session-123"
    assert req.message == "Can I cycle today?"

    trace = TraceResponse(
        activity="cycling",
        location_query="Bhopal",
        resolved_location="Bhopal, India",
        latitude=23.25,
        longitude=77.42,
        selected_sop_id="SOP-CYCLING-WIND-001",
        decision_severity="HIGH"
    )
    resp = ChatResponse(
        session_id=req.session_id,
        response_type="SUCCESS",
        response="Cycling is not recommended today.",
        sop_id="SOP-CYCLING-WIND-001",
        severity="HIGH",
        recommendation="not_recommended",
        trace=trace
    )
    assert resp.response_type == "SUCCESS"
    assert resp.trace.latitude == 23.25


def test_weather_state_typed_dict():
    state: WeatherState = {
        "session_id": "test-session",
        "user_message": "Is it safe to cycle?",
        "chat_history": [],
        "activity": "cycling",
        "intent_category": "outdoor_exercise",
        "location_name": "Bhopal",
        "time_reference": "today",
        "target_group": "general",
        "latitude": 23.25,
        "longitude": 77.42,
        "timezone": "Asia/Kolkata",
        "weather_facts": {"wind_speed_kmh": 42.0},
        "candidate_sops": [],
        "response_type": "SUCCESS",
        "trace": {}
    }
    assert state["session_id"] == "test-session"
    assert state["activity"] == "cycling"
    assert state["weather_facts"]["wind_speed_kmh"] == 42.0
