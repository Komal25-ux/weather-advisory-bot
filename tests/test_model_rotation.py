"""Unit and integration tests for Gemini model rotation, provider resilience,
and honest INTENT_FAILURE graph routing."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from app.config import settings
from app.services.llm import (
    _is_retryable_provider_error,
    _invoke_with_model_rotation,
    _get_llm_runnable,
    extract_intent,
    generate_grounded_response,
    LLMServiceError,
)
from app.schemas.intent import StructuredIntent
from app.schemas.response_payload import ResponseGenerationPayload, FactToReport
from app.graph.workflow import build_weather_graph
from app.graph.state import WeatherState


class MockRateLimitError(Exception):
    def __init__(self, message="Error code: 429 - RESOURCE_EXHAUSTED"):
        super().__init__(message)
        self.status_code = 429


class MockAuthError(Exception):
    def __init__(self, message="Error code: 401 - Unauthorized"):
        super().__init__(message)
        self.status_code = 401


class MockServerError(Exception):
    def __init__(self, message="Error code: 503 - Service Unavailable"):
        super().__init__(message)
        self.status_code = 503


# ===================================================================
# 1. Retryable Error Detection Tests
# ===================================================================

def test_is_retryable_provider_error():
    assert _is_retryable_provider_error(MockRateLimitError()) is True
    assert _is_retryable_provider_error(MockServerError()) is True
    assert _is_retryable_provider_error(Exception("Connection timed out after 15s")) is True
    assert _is_retryable_provider_error(Exception("Quota exceeded for metric")) is True

    # Non-retryable
    assert _is_retryable_provider_error(MockAuthError()) is False
    assert _is_retryable_provider_error(ValueError("Invalid argument")) is False
    assert _is_retryable_provider_error(TypeError("NoneType is not callable")) is False


# ===================================================================
# 2. Model Rotation Behavior Tests (Tasks 1 & 3)
# ===================================================================

@pytest.mark.asyncio
async def test_primary_model_succeeds():
    """Scenario 1: Primary model succeeds, fallbacks are not called."""
    attempted_models: List[str] = []

    async def mock_invoke(model: str):
        attempted_models.append(model)
        return "success"

    result = await _invoke_with_model_rotation(
        mock_invoke,
        models=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
        operation_name="Test Op"
    )

    assert result == "success"
    assert attempted_models == ["gemini-3.6-flash"]


@pytest.mark.asyncio
async def test_primary_model_429_rotates_to_secondary():
    """Scenario 2: Primary model encounters 429, rotates to gemini-3.5-flash and succeeds."""
    attempted_models: List[str] = []

    async def mock_invoke(model: str):
        attempted_models.append(model)
        if model == "gemini-3.6-flash":
            raise MockRateLimitError()
        return "fallback_success"

    result = await _invoke_with_model_rotation(
        mock_invoke,
        models=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
        operation_name="Test Op"
    )

    assert result == "fallback_success"
    assert attempted_models == ["gemini-3.6-flash", "gemini-3.5-flash"]


@pytest.mark.asyncio
async def test_primary_and_secondary_fail_rotates_to_third():
    """Scenario 3: Primary and secondary fail, third model succeeds."""
    attempted_models: List[str] = []

    async def mock_invoke(model: str):
        attempted_models.append(model)
        if model == "gemini-3.6-flash":
            raise MockRateLimitError()
        if model == "gemini-3.5-flash":
            raise MockServerError()
        return "third_model_success"

    result = await _invoke_with_model_rotation(
        mock_invoke,
        models=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
        operation_name="Test Op"
    )

    assert result == "third_model_success"
    assert attempted_models == ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]


@pytest.mark.asyncio
async def test_all_models_fail_raises_llm_service_error():
    """Scenario 4: All models fail with retryable errors -> raises LLMServiceError."""
    attempted_models: List[str] = []

    async def mock_invoke(model: str):
        attempted_models.append(model)
        raise MockRateLimitError(f"429 on {model}")

    with pytest.raises(LLMServiceError) as exc_info:
        await _invoke_with_model_rotation(
            mock_invoke,
            models=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
            operation_name="Test Op"
        )

    assert "Test Op failed" in str(exc_info.value)
    assert attempted_models == ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]


@pytest.mark.asyncio
async def test_non_retryable_error_aborts_rotation_immediately():
    """Scenario 5: Non-retryable error (e.g. 401 Auth) aborts rotation immediately without trying fallbacks."""
    attempted_models: List[str] = []

    async def mock_invoke(model: str):
        attempted_models.append(model)
        raise MockAuthError("Invalid API key")

    with pytest.raises(LLMServiceError) as exc_info:
        await _invoke_with_model_rotation(
            mock_invoke,
            models=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
            operation_name="Test Op"
        )

    assert "Invalid API key" in str(exc_info.value)
    # Crucial: exactly 1 attempt made, never rotated to fallbacks
    assert attempted_models == ["gemini-3.6-flash"]


@pytest.mark.asyncio
async def test_custom_runnable_bypasses_model_rotation():
    """Scenario 6: Custom runnable passed to extract_intent completely bypasses model rotation."""
    mock_runnable = AsyncMock()
    mock_runnable.ainvoke.return_value = StructuredIntent(
        activity="running",
        location_name="Munich",
        time_reference="today"
    )

    with patch("app.services.llm._invoke_with_model_rotation") as mock_rotation:
        result = await extract_intent(
            "Can I run in Munich today?",
            custom_runnable=mock_runnable
        )

        assert result.activity == "running"
        assert result.location_name == "Munich"
        # Verify model rotation was completely bypassed
        mock_rotation.assert_not_called()
        mock_runnable.ainvoke.assert_called_once()


# ===================================================================
# 3. Intent Extraction with Real Model Rotation (Tasks 1 & 2)
# ===================================================================

@pytest.mark.asyncio
async def test_extract_intent_rotates_on_429():
    """extract_intent rotates from primary to fallback model when primary returns 429."""
    attempted_models: List[str] = []

    def mock_get_runnable(model_name=None, custom_runnable=None):
        attempted_models.append(model_name)
        mock_r = AsyncMock()
        if model_name == "gemini-3.6-flash":
            mock_r.ainvoke.side_effect = MockRateLimitError()
        else:
            mock_r.ainvoke.return_value = StructuredIntent(
                activity="cycling",
                location_name="Berlin",
                time_reference="today"
            )
        return mock_r

    with patch("app.services.llm._get_llm_runnable", side_effect=mock_get_runnable), \
         patch("app.services.llm.settings.LLM_MODEL", "gemini-3.6-flash"), \
         patch("app.services.llm.settings.LLM_FALLBACK_MODELS", "gemini-3.5-flash"):

        intent = await extract_intent("Can I cycle in Berlin today?")

        assert intent.activity == "cycling"
        assert intent.location_name == "Berlin"
        assert attempted_models == ["gemini-3.6-flash", "gemini-3.5-flash"]


# ===================================================================
# 4. Graph Workflow INTENT_FAILURE Routing (Task 2)
# ===================================================================

@pytest.mark.asyncio
async def test_graph_intent_llm_failure_routes_to_intent_failure():
    """Scenario 7: LLM intent extraction failure routes to INTENT_FAILURE, NOT clarification."""
    graph = build_weather_graph()

    with patch("app.graph.nodes.extract_intent", side_effect=LLMServiceError("All models exhausted")), \
         patch("app.graph.nodes.fetch_weather_facts") as mock_weather:

        state: WeatherState = {
            "session_id": "test-llm-outage",
            "user_message": "Can I cycle in Berlin today?"
        }
        final_state = await graph.ainvoke(state)

        # 1. response_type is INTENT_FAILURE (distinct from INTENT_CLARIFICATION)
        assert final_state["response_type"] == "INTENT_FAILURE"

        # 2. Honest unavailability message
        assert "language-model service is temporarily unavailable" in final_state["response"]
        assert "safely evaluate the request without completing intent extraction" in final_state["response"]

        # 3. Weather API was NEVER called
        mock_weather.assert_not_called()


@pytest.mark.asyncio
async def test_graph_genuine_ambiguous_routes_to_clarification():
    """Scenario 8: Genuine user ambiguity still returns INTENT_CLARIFICATION."""
    graph = build_weather_graph()

    mock_intent = StructuredIntent(
        activity=None,
        location_name=None,
        is_clarification_needed=True,
        ambiguity_reason="User gave vague question"
    )

    with patch("app.graph.nodes.extract_intent", return_value=mock_intent):
        state: WeatherState = {
            "session_id": "test-ambig",
            "user_message": "Should I go?"
        }
        final_state = await graph.ainvoke(state)

        assert final_state["response_type"] == "INTENT_CLARIFICATION"
        assert "specify which outdoor activity" in final_state["response"]


@pytest.mark.asyncio
async def test_graph_missing_location_routes_to_clarification():
    """Scenario 9: Successful extraction missing location returns INTENT_CLARIFICATION."""
    graph = build_weather_graph()

    mock_intent = StructuredIntent(
        activity="cycling",
        location_name=None,
        is_clarification_needed=False
    )

    with patch("app.graph.nodes.extract_intent", return_value=mock_intent):
        state: WeatherState = {
            "session_id": "test-missing-loc",
            "user_message": "Can I cycle today?"
        }
        final_state = await graph.ainvoke(state)

        assert final_state["response_type"] == "INTENT_CLARIFICATION"
        assert "Which city or location" in final_state["response"]


# ===================================================================
# 5. Grounded Response Fallback on Model Failure (Tasks 1 & 3)
# ===================================================================

@pytest.mark.asyncio
async def test_grounded_response_falls_back_to_deterministic_when_all_models_fail():
    """Scenario 10: If all LLM models fail during response generation, deterministic formatter is used."""
    payload = ResponseGenerationPayload(
        activity="cycling",
        location="Berlin, Germany",
        time_period="today",
        recommendation="not_recommended",
        severity="HIGH",
        selected_sop_id="SOP-CYCLING-WIND-001",
        selected_sop_name="High Wind Advisory for Cycling",
        applicable_sop_ids=["SOP-CYCLING-WIND-001"],
        guidance=["Avoid exposed roads."],
        rationale="High crosswinds.",
        facts_used=[FactToReport(name="Wind Speed", value=45.0, unit="km/h")],
        decision_trace="wind_speed_kmh (45.0) >= 35.0"
    )

    with patch("app.services.llm.settings.LLM_API_KEY", "valid_key"), \
         patch("app.services.llm.ChatOpenAI") as mock_chat_cls:

        mock_instance = AsyncMock()
        mock_instance.ainvoke.side_effect = MockRateLimitError("429 Quota Exceeded")
        mock_chat_cls.return_value = mock_instance

        response = await generate_grounded_response(payload)

        # Deterministic advisory fallback produced
        assert "Cycling is not recommended in Berlin, Germany (today)" in response
        assert "SOP-CYCLING-WIND-001" in response
        assert "45.0 km/h" in response
        assert "**Severity Level:** HIGH" in response
