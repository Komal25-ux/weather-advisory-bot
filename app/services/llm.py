import logging
from typing import List, Dict, Optional, Any
from pydantic import ValidationError
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.schemas.intent import StructuredIntent

logger = logging.getLogger("weather-advisory-bot.services.llm")


class LLMServiceError(Exception):
    """Raised when the LLM provider API call fails or times out."""
    pass


class IntentExtractionError(Exception):
    """Base exception for intent extraction failures."""
    pass


class IntentValidationError(IntentExtractionError):
    """Raised when LLM output violates schema constraints."""
    pass


INTENT_EXTRACTION_SYSTEM_PROMPT = """You are a strict, factual information extraction component for a weather safety advisory system.
Your sole responsibility is to extract the user's intended activity, location, time window, and target group into structured data.

Rules:
1. Extract the following fields:
   - activity: The specific outdoor action (e.g., 'cycling', 'running', 'picnic', 'park', 'two_wheeler', 'walking', 'drone_flying').
     Normalize paraphrases into canonical terms (e.g. 'pedal my bike' -> 'cycling', 'take my kid to playground' -> activity: 'park', target_group: 'child').
   - intent_category: The operational category: 'outdoor_exercise', 'travel', 'recreation', or 'vulnerable_groups'.
   - location_name: The explicit geographic name/city if stated (e.g. 'Bhopal', 'London', 'Paris'). If NOT mentioned, return null. DO NOT invent a location.
   - time_reference: The temporal reference (e.g. 'today', 'this evening', 'tomorrow', 'this afternoon', 'now'). Default to 'today' if not specified.
   - target_group: 'child', 'elderly', or 'general'.
   - is_clarification_needed: Set to true ONLY if the message is too ambiguous to identify an outdoor activity or context (e.g., 'Should I go?', 'What about me?').
   - ambiguity_reason: Provide a concise reason if clarification is needed.

2. Contextual Follow-up Resolution:
   If prior conversation history is provided, retain unchanged context from earlier turns (e.g., if Turn 1 mentioned location 'Bhopal' and Turn 2 asks 'What about this evening?', retain location 'Bhopal' and activity from Turn 1 while updating time_reference to 'this evening').

3. ABSOLUTE CONSTRAINTS:
   - DO NOT make safety evaluations (never say whether something is safe or recommended).
   - DO NOT invent weather conditions, forecasts, or temperatures.
   - DO NOT reference policy IDs or thresholds.
   - Return structured data strictly adhering to the schema.
"""


def _get_llm_runnable(custom_runnable: Optional[Any] = None) -> Any:
    """Returns a structured-output runnable using the configured LLM provider."""
    if custom_runnable is not None:
        return custom_runnable

    api_key = settings.LLM_API_KEY or "dummy_key_for_testing"
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=api_key,
        base_url=settings.LLM_BASE_URL,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        temperature=0.0
    )
    return llm.with_structured_output(StructuredIntent)


async def extract_intent(
    user_message: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    custom_runnable: Optional[Any] = None
) -> StructuredIntent:
    """
    Extracts structured intent from user message and chat history using LLM structured output.
    Enforces application-level Pydantic schema validation.
    """
    cleaned_message = user_message.strip()
    if not cleaned_message:
        return StructuredIntent(
            is_clarification_needed=True,
            ambiguity_reason="Empty user message provided."
        )

    messages = [SystemMessage(content=INTENT_EXTRACTION_SYSTEM_PROMPT)]

    # Add previous turns to support follow-up context resolution
    if chat_history:
        for turn in chat_history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=cleaned_message))

    runnable = _get_llm_runnable(custom_runnable)

    try:
        if hasattr(runnable, "ainvoke"):
            raw_result = await runnable.ainvoke(messages)
        elif hasattr(runnable, "invoke"):
            raw_result = runnable.invoke(messages)
        elif callable(runnable):
            import inspect
            if inspect.iscoroutinefunction(runnable):
                raw_result = await runnable(messages)
            else:
                raw_result = runnable(messages)
        else:
            raise LLMServiceError(f"Unsupported LLM runnable type: {type(runnable)}")

        # Validate structured result
        if isinstance(raw_result, StructuredIntent):
            return raw_result
        elif isinstance(raw_result, dict):
            try:
                return StructuredIntent.model_validate(raw_result)
            except ValidationError as ve:
                raise IntentValidationError(f"Structured LLM output failed schema validation: {ve}") from ve
        else:
            raise IntentValidationError(f"Expected StructuredIntent, got {type(raw_result)}: {raw_result}")

    except (IntentValidationError, IntentExtractionError):
        raise
    except Exception as e:
        logger.error(f"LLM intent extraction call failed: {e}")
        raise LLMServiceError(f"LLM intent extraction service error: {e}") from e


async def generate_grounded_response(
    decision_payload: Dict,
) -> str:
    """
    Placeholder: verbalizes deterministic decision into user-facing response.
    Full implementation scheduled for Iteration 7.
    """
    raise NotImplementedError("LLM response generation will be implemented in Iteration 7.")
