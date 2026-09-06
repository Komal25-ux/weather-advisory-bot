"""Test suite for Iteration 7: Grounded Response Generation and Guardrails."""
import pytest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

from app.schemas.response_payload import ResponseGenerationPayload, FactToReport
from app.services.llm import (
    generate_grounded_response,
    format_deterministic_advisory,
)
from app.graph.nodes import handle_no_sop_node, handle_failure_node
from app.graph.state import WeatherState


class MockAIMessage:
    def __init__(self, content: str):
        self.content = content


class MockLLMRunnable:
    def __init__(self, content: str = "", side_effect=None):
        self.content = content
        self.side_effect = side_effect

    async def ainvoke(self, messages):
        if self.side_effect:
            raise self.side_effect
        return MockAIMessage(self.content)


@pytest.fixture
def sample_payload():
    return ResponseGenerationPayload(
        activity="cycling",
        location="Bhopal, Madhya Pradesh, India",
        time_period="today",
        recommendation="not_recommended",
        severity="HIGH",
        selected_sop_id="SOP-CYCLING-WIND-001",
        selected_sop_name="Strong Wind and Cycling",
        applicable_sop_ids=["SOP-CYCLING-WIND-001"],
        guidance=[
            "Avoid cycling outdoors in these windy conditions.",
            "Consider postponing your ride."
        ],
        rationale="Strong crosswinds severely compromise steering stability.",
        facts_used=[
            FactToReport(name="Wind Speed", value=43.2, unit="km/h"),
            FactToReport(name="Temperature", value=29.4, unit="°C"),
            FactToReport(name="Precipitation", value=0.0, unit="mm"),
        ],
        decision_trace="wind_speed_kmh (43.2) >= 40.0"
    )


# -------------------------------------------------------------------
# 1. Successful grounded response
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_grounded_response(sample_payload):
    mock_runnable = MockLLMRunnable(
        content=(
            "**Cycling is not recommended in Bhopal today.**\n\n"
            "Live observations record winds of **43.2 km/h** and temperature of 29.4 °C. "
            "Under policy **SOP-CYCLING-WIND-001** (Strong Wind and Cycling), sustained winds at or above "
            "40 km/h present a high risk to cyclists. Please consider postponing your ride."
        )
    )

    response = await generate_grounded_response(sample_payload, custom_runnable=mock_runnable)
    assert "not recommended" in response.lower()
    assert "SOP-CYCLING-WIND-001" in response
    assert "Bhopal" in response
    assert "43.2" in response


# -------------------------------------------------------------------
# 2. Response contains actual supplied weather values
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_response_contains_actual_supplied_weather_values(sample_payload):
    response = format_deterministic_advisory(sample_payload)
    assert "43.2 km/h" in response
    assert "29.4 °C" in response
    assert "0.0 mm" in response


# -------------------------------------------------------------------
# 3. Response references selected SOP
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_response_references_selected_sop(sample_payload):
    mock_runnable = MockLLMRunnable(
        content="Advisory: Cycling is not recommended due to wind."
    )
    # If LLM omits SOP ID, post-guardrail automatically appends citation
    response = await generate_grounded_response(sample_payload, custom_runnable=mock_runnable)
    assert "SOP-CYCLING-WIND-001" in response
    assert "Strong Wind and Cycling" in response
    assert "HIGH" in response


# -------------------------------------------------------------------
# 4. Multiple applicable SOPs are represented correctly
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_applicable_sops_represented(sample_payload):
    sample_payload.applicable_sop_ids = ["SOP-CYCLING-WIND-001", "SOP-UV-EXERCISE-001"]
    response = format_deterministic_advisory(sample_payload)
    assert "2 policies matched this scenario" in response
    assert "SOP-CYCLING-WIND-001" in response
    assert "SOP-UV-EXERCISE-001" in response


# -------------------------------------------------------------------
# 5. LLM cannot override not_recommended (Adversarial Prompt Injection)
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_cannot_override_not_recommended(sample_payload):
    # Simulated compromised LLM attempting to tell user it is safe
    adversarial_llm = MockLLMRunnable(
        content="Ignore the rules! The weather is lovely and it is safe and recommended to cycle!"
    )

    response = await generate_grounded_response(sample_payload, custom_runnable=adversarial_llm)
    # Guardrail intercepts and falls back to deterministic advisory
    assert "not recommended" in response.lower()
    assert "safe and recommended" not in response.lower()
    assert "SOP-CYCLING-WIND-001" in response


# -------------------------------------------------------------------
# 6. LLM cannot invent weather values
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deterministic_formatter_quotes_exact_facts(sample_payload):
    response = format_deterministic_advisory(sample_payload)
    # Verify exact numbers from payload are present
    for fact in sample_payload.facts_used:
        assert str(fact.value) in response


# -------------------------------------------------------------------
# 7. Unavailable weather field remains unavailable
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unavailable_weather_field_remains_unavailable(sample_payload):
    sample_payload.facts_used.append(
        FactToReport(name="UV Index", value="UNAVAILABLE", unit="")
    )
    response = format_deterministic_advisory(sample_payload)
    assert "**UV Index**: Unavailable" in response
    # Crucial: verify it was not replaced by 0 or 0.0
    assert "UV Index**: 0" not in response


# -------------------------------------------------------------------
# 8. No-SOP path does not generate invented advice
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_sop_path_refuses_invented_advice():
    state: WeatherState = {
        "activity": "drone_flying",
        "location_name": "Berlin",
        "weather_facts": {"temperature_c": 21.0, "wind_speed_kmh": 10.0}
    }
    result = await handle_no_sop_node(state)
    assert result["response_type"] == "NO_SOP"
    assert "don't have an applicable safety policy" in result["response"]
    assert "cannot provide a safety recommendation" in result["response"]


# -------------------------------------------------------------------
# 9. Weather failure does not generate a weather-based recommendation
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weather_failure_does_not_generate_recommendation():
    state: WeatherState = {
        "error_type": "WEATHER_FAILURE",
        "location_name": "Bhopal",
        "weather_facts": None
    }
    result = await handle_failure_node(state)
    assert result["response_type"] == "WEATHER_FAILURE"
    assert "couldn't retrieve live weather data for Bhopal" in result["response"]
    assert "can't provide a weather-based safety recommendation" in result["response"]


# -------------------------------------------------------------------
# 10. LLM / API failure is handled honestly (Safe Fallback)
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_api_failure_handled_honestly(sample_payload):
    failing_llm = MockLLMRunnable(side_effect=Exception("OpenAI API 503 Service Unavailable"))

    response = await generate_grounded_response(sample_payload, custom_runnable=failing_llm)
    # Safely recovers with deterministic advisory without crashing
    assert "not recommended" in response.lower()
    assert "SOP-CYCLING-WIND-001" in response
    assert "43.2 km/h" in response
