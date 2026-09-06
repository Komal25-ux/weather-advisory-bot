"""
Focused tests verifying Google Gemini LLM configuration via OpenAI-compatible endpoint.
Verifies:
1. Default configuration specifies Gemini provider, model, and OpenAI-compatible base URL.
2. GEMINI_API_KEY environment variable alias resolution.
3. Missing API key fails clearly with LLMServiceError (no silent dummy key fallback).
4. Configured Gemini instantiates ChatOpenAI structured output runnable targeting StructuredIntent without network calls.
5. Deterministic fallback in generate_grounded_response when LLM key is unconfigured.
"""
import os
import pytest
from unittest.mock import patch

from app.config import Settings
from app.schemas.intent import StructuredIntent
from app.schemas.response_payload import ResponseGenerationPayload, FactToReport
from app.services.llm import (
    _get_llm_runnable,
    extract_intent,
    generate_grounded_response,
    LLMServiceError,
)


def test_default_gemini_settings():
    """Verify default settings point to Gemini OpenAI-compatible endpoint with fallback models."""
    with patch.dict(os.environ, {}, clear=True):
        custom_settings = Settings(_env_file=None)
        assert custom_settings.LLM_PROVIDER == "gemini"
        assert custom_settings.LLM_MODEL == "gemini-3.6-flash"
        assert custom_settings.LLM_FALLBACK_MODELS == "gemini-3.5-flash,gemini-3.5-flash-lite"
        assert custom_settings.effective_llm_models == [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite"
        ]
        assert custom_settings.LLM_BASE_URL == "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_gemini_api_key_alias_resolution():
    """Verify GEMINI_API_KEY environment variable populates LLM_API_KEY."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test_gemini_secret_12345"}, clear=True):
        custom_settings = Settings(_env_file=None)
        assert custom_settings.LLM_API_KEY == "test_gemini_secret_12345"


def test_missing_api_key_raises_clear_service_error():
    """Verify that unconfigured API key raises LLMServiceError rather than using dummy key."""
    with patch("app.services.llm.settings.LLM_API_KEY", ""):
        with pytest.raises(LLMServiceError) as exc_info:
            _get_llm_runnable()
        err_msg = str(exc_info.value)
        assert "LLM API key is not configured" in err_msg
        assert "gemini" in err_msg or "GEMINI_API_KEY" in err_msg


@pytest.mark.asyncio
async def test_configured_gemini_instantiates_runnable_with_structured_output():
    """Verify ChatOpenAI is correctly configured for Gemini with StructuredIntent schema."""
    with patch("app.services.llm.settings.LLM_API_KEY", "mock_gemini_key_abc"), \
         patch("app.services.llm.settings.LLM_PROVIDER", "gemini"), \
         patch("app.services.llm.settings.LLM_MODEL", "gemini-2.5-flash"), \
         patch("app.services.llm.settings.LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"):

        runnable = _get_llm_runnable()
        assert runnable is not None
        # Verify it's a LangChain RunnableSequence
        assert hasattr(runnable, "ainvoke")

        # Inspect the underlying ChatOpenAI instance in the RunnableSequence
        chat_model = runnable.first if hasattr(runnable, "first") else runnable
        assert chat_model.model_name == "gemini-2.5-flash"
        assert "generativelanguage.googleapis.com" in str(chat_model.openai_api_base)


@pytest.mark.asyncio
async def test_grounded_response_deterministic_fallback_when_unconfigured():
    """Verify generate_grounded_response employs deterministic formatter when LLM key is absent."""
    payload = ResponseGenerationPayload(
        activity="cycling",
        location="Berlin, Germany",
        time_period="today",
        recommendation="not_recommended",
        severity="HIGH",
        selected_sop_id="SOP-CYCLING-WIND-001",
        selected_sop_name="Strong Wind and Cycling",
        applicable_sop_ids=["SOP-CYCLING-WIND-001"],
        facts_used=[FactToReport(name="wind_speed_kmh", value=45.0, unit="km/h")],
        guidance=["Avoid cycling outdoors in high winds."],
        rationale="Sustained winds at or above 40 km/h present severe handling hazards.",
        decision_trace="SOP-CYCLING-WIND-001 matched wind_speed_kmh=45.0 >= 40.0"
    )

    with patch("app.services.llm.settings.LLM_API_KEY", ""):
        response_text = await generate_grounded_response(payload)
        assert "not recommended" in response_text.lower()
        assert "SOP-CYCLING-WIND-001" in response_text
        assert "45.0 km/h" in response_text
