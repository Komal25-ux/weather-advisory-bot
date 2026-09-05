"""Focused unit tests for Iteration 4: Structured LLM Intent Extraction."""
import pytest

from app.schemas.intent import StructuredIntent
from app.services.llm import (
    extract_intent,
    LLMServiceError,
    IntentValidationError,
)


class MockLLMRunnable:
    """Mock simulating a LangChain Runnable with .ainvoke() for structured output."""
    def __init__(self, return_value=None, side_effect=None):
        self.return_value = return_value
        self.side_effect = side_effect

    async def ainvoke(self, messages):
        if self.side_effect:
            if isinstance(self.side_effect, Exception):
                raise self.side_effect
            raise Exception(str(self.side_effect))
        return self.return_value


@pytest.mark.asyncio
async def test_clear_intent():
    """Verify direct extraction of activity, location, time, and target group."""
    mock_runnable = MockLLMRunnable(return_value=StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="Bhopal",
        time_reference="today",
        target_group="general",
        confidence=0.98,
        is_clarification_needed=False
    ))

    intent = await extract_intent(
        "Is it safe to cycle in Bhopal today?",
        custom_runnable=mock_runnable
    )
    assert intent.activity == "cycling"
    assert intent.location_name == "Bhopal"
    assert intent.location == "Bhopal"
    assert intent.time_reference == "today"
    assert intent.target_group == "general"
    assert intent.is_clarification_needed is False


@pytest.mark.asyncio
async def test_paraphrased_intent():
    """Verify mapping of paraphrases to canonical activity and category."""
    mock_runnable = MockLLMRunnable(return_value=StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name=None,
        time_reference="today",
        target_group="general",
        confidence=0.92,
        is_clarification_needed=False
    ))

    intent = await extract_intent(
        "Would riding my bike outside be okay with these conditions?",
        custom_runnable=mock_runnable
    )
    assert intent.activity == "cycling"
    assert intent.intent_category == "outdoor_exercise"


@pytest.mark.asyncio
async def test_missing_location():
    """Verify query with activity but no location leaves location_name as None without guessing."""
    mock_runnable = MockLLMRunnable(return_value=StructuredIntent(
        activity="running",
        intent_category="outdoor_exercise",
        location_name=None,
        time_reference="today",
        target_group="general"
    ))

    intent = await extract_intent("Can I go for a run today?", custom_runnable=mock_runnable)
    assert intent.activity == "running"
    assert intent.location_name is None
    assert intent.location is None


@pytest.mark.asyncio
async def test_missing_activity():
    """Verify query with location but no activity leaves activity as None."""
    mock_runnable = MockLLMRunnable(return_value=StructuredIntent(
        activity=None,
        intent_category=None,
        location_name="London",
        time_reference="today",
        target_group="general"
    ))

    intent = await extract_intent("What is it like outside in London?", custom_runnable=mock_runnable)
    assert intent.activity is None
    assert intent.location_name == "London"


@pytest.mark.asyncio
async def test_relative_time_this_evening():
    """Verify contextual follow-up preserving previous location and updating time reference."""
    mock_runnable = MockLLMRunnable(return_value=StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="Bhopal",
        time_reference="this evening",
        target_group="general"
    ))

    history = [
        {"role": "user", "content": "Can I cycle in Bhopal today?"},
        {"role": "assistant", "content": "Advisory response..."}
    ]
    intent = await extract_intent(
        "What about this evening?",
        chat_history=history,
        custom_runnable=mock_runnable
    )
    assert intent.location_name == "Bhopal"
    assert intent.activity == "cycling"
    assert intent.time_reference == "this evening"


@pytest.mark.asyncio
async def test_target_group_children():
    """Verify recognition of vulnerable demographic (child)."""
    mock_runnable = MockLLMRunnable(return_value=StructuredIntent(
        activity="park",
        intent_category="vulnerable_groups",
        location_name="Paris",
        time_reference="this afternoon",
        target_group="child"
    ))

    intent = await extract_intent(
        "Can I take my kid to the park in Paris this afternoon?",
        custom_runnable=mock_runnable
    )
    assert intent.activity == "park"
    assert intent.target_group == "child"
    assert intent.time_reference == "this afternoon"
    assert intent.location_name == "Paris"


@pytest.mark.asyncio
async def test_ambiguous_request():
    """Verify ambiguous requests trigger is_clarification_needed=True without guessing."""
    mock_runnable = MockLLMRunnable(return_value=StructuredIntent(
        activity=None,
        intent_category=None,
        location_name=None,
        is_clarification_needed=True,
        ambiguity_reason="Unspecified activity and location."
    ))

    intent = await extract_intent("Should I go?", custom_runnable=mock_runnable)
    assert intent.is_clarification_needed is True
    assert intent.ambiguity_reason is not None


@pytest.mark.asyncio
async def test_empty_message_returns_clarification_without_llm():
    """Verify blank user message returns immediate clarification without calling LLM."""
    intent = await extract_intent("   ")
    assert intent.is_clarification_needed is True
    assert "Empty user message" in intent.ambiguity_reason


@pytest.mark.asyncio
async def test_malformed_invalid_llm_output():
    """Verify that unparseable or invalid structured output raises IntentValidationError."""
    # confidence > 1.0 violates ge=0.0, le=1.0 constraint
    mock_runnable = MockLLMRunnable(return_value={
        "activity": "cycling",
        "confidence": 99.0
    })

    with pytest.raises(IntentValidationError):
        await extract_intent("Is it safe to cycle?", custom_runnable=mock_runnable)


@pytest.mark.asyncio
async def test_llm_api_failure():
    """Verify that LLM timeout or network failures raise LLMServiceError."""
    mock_runnable = MockLLMRunnable(side_effect=Exception("Connection timed out to LLM provider"))

    with pytest.raises(LLMServiceError) as exc_info:
        await extract_intent("Can I cycle today?", custom_runnable=mock_runnable)
    assert "LLM intent extraction service error" in str(exc_info.value)
