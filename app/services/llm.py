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


RESPONSE_GENERATOR_SYSTEM_PROMPT = """You are an accurate, grounded advisory response verbalizer for an automated safety system.
The safety decision and policy evaluation have ALREADY been executed deterministically by application logic. You are strictly verbalizing the established decision.

STRICT CONSTRAINTS:
1. YOU MUST NEVER OVERRIDE, MODIFY, OR CONTRADICT THE DETERMINISTIC RECOMMENDATION:
   - If recommendation is 'not_recommended': State clearly that the activity is NOT recommended under policy.
   - If recommendation is 'caution': State that caution and protective measures are advised.
   - If recommendation is 'recommended': State that conditions appear broadly favorable under policy.
2. USE ONLY SUPPLIED WEATHER FACTS:
   - Quote exact numeric values from 'facts_used' (e.g. '43.2 km/h').
   - NEVER calculate, estimate, round differently, or invent weather numbers.
   - If a metric value is 'UNAVAILABLE', explicitly state that it is unavailable.
3. CITE THE APPLICABLE STANDARD OPERATING PROCEDURE:
   - Explicitly cite the policy ID (e.g. 'SOP-CYCLING-WIND-001') and policy name.
   - State the severity level (e.g. 'HIGH').
   - If 'applicable_sop_ids' contains multiple policies, acknowledge that multiple policies matched and that this primary policy took precedence due to severity/priority ranking.
4. COMMUNICATE ESSENTIAL CONTEXT:
   - Clearly state the activity, location, and relevant time period.
   - Include the key guidance bullets and rationale from the SOP.
   - Keep the answer concise, professional, and well-structured in markdown.
"""


def format_deterministic_advisory(payload: "ResponseGenerationPayload") -> str:
    """
    Deterministic template verbalizer used as a guaranteed grounded fallback.
    Ensures that even on LLM outage, zero hallucination occurs and decisions remain fully auditable.
    """
    rec_title = {
        "not_recommended": f"**{payload.activity.capitalize()} is not recommended in {payload.location} ({payload.time_period}).**",
        "caution": f"**Caution is advised for {payload.activity} in {payload.location} ({payload.time_period}).**",
        "recommended": f"**Conditions appear broadly favorable for {payload.activity} in {payload.location} ({payload.time_period}).**"
    }.get(payload.recommendation, f"**Advisory for {payload.activity} in {payload.location}.**")

    facts_lines = []
    for f in payload.facts_used:
        val_str = f"{f.value} {f.unit}".strip() if f.value != "UNAVAILABLE" else "Unavailable"
        facts_lines.append(f"- **{f.name}**: {val_str}")
    facts_block = "\n".join(facts_lines)

    multi_policy_note = ""
    if len(payload.applicable_sop_ids) > 1:
        other_policies = [p for p in payload.applicable_sop_ids if p != payload.selected_sop_id]
        multi_policy_note = (
            f"\n*Note: {len(payload.applicable_sop_ids)} policies matched this scenario. "
            f"Primary policy `{payload.selected_sop_id}` took precedence based on severity ({payload.severity}). "
            f"Other matched policies: {', '.join(other_policies)}.*\n"
        )

    guidance_block = "\n".join([f"- {g}" for g in payload.guidance]) if payload.guidance else "- Follow standard precautions."
    rationale_str = f"\n*{payload.rationale}*" if payload.rationale else ""

    return f"""{rec_title}

{facts_block}

**Policy Evaluation:**
- **Primary Policy:** `{payload.selected_sop_id}` — {payload.selected_sop_name}
- **Severity Level:** {payload.severity}
{multi_policy_note}
**Guidance:**
{guidance_block}
{rationale_str}
""".strip()


async def generate_grounded_response(
    payload: Any,
    custom_runnable: Optional[Any] = None
) -> str:
    """
    Verbalizes the deterministic decision into natural language while strictly
    preserving safety recommendation, weather numbers, and SOP citations.
    """
    from app.schemas.response_payload import ResponseGenerationPayload
    if not isinstance(payload, ResponseGenerationPayload):
        payload = ResponseGenerationPayload.model_validate(payload)

    # Prompt constructing user context strictly bounded by trusted facts
    prompt_content = f"""Deterministic Decision Input:
- Activity: {payload.activity}
- Location: {payload.location}
- Time Period: {payload.time_period}
- Recommendation: {payload.recommendation}
- Severity: {payload.severity}
- Primary Policy ID: {payload.selected_sop_id}
- Primary Policy Name: {payload.selected_sop_name}
- All Applicable Policy IDs: {payload.applicable_sop_ids}
- Facts Used: {[{'name': f.name, 'value': f.value, 'unit': f.unit} for f in payload.facts_used]}
- Guidance: {payload.guidance}
- Rationale: {payload.rationale}
- Decision Trace: {payload.decision_trace}
"""

    messages = [
        SystemMessage(content=RESPONSE_GENERATOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt_content)
    ]

    try:
        if custom_runnable is not None:
            runnable = custom_runnable
        else:
            api_key = settings.LLM_API_KEY or "dummy_key_for_testing"
            runnable = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=api_key,
                base_url=settings.LLM_BASE_URL,
                timeout=settings.LLM_TIMEOUT_SECONDS,
                temperature=0.2
            )

        if hasattr(runnable, "ainvoke"):
            response_msg = await runnable.ainvoke(messages)
        elif hasattr(runnable, "invoke"):
            response_msg = runnable.invoke(messages)
        elif callable(runnable):
            import inspect
            if inspect.iscoroutinefunction(runnable):
                response_msg = await runnable(messages)
            else:
                response_msg = runnable(messages)
        else:
            raise LLMServiceError(f"Unsupported runnable type: {type(runnable)}")

        content = response_msg.content if hasattr(response_msg, "content") else str(response_msg)

        # Defense-in-depth guardrail verification:
        # 1. Ensure recommendation is not inverted
        if payload.recommendation == "not_recommended":
            low_content = content.lower()
            if "is safe" in low_content or "is recommended" in low_content and "not recommended" not in low_content:
                logger.warning("LLM output violated safety recommendation. Falling back to deterministic advisory.")
                return format_deterministic_advisory(payload)

        # 2. Ensure primary SOP ID is cited
        if payload.selected_sop_id not in content:
            content += f"\n\n**Policy:** `{payload.selected_sop_id}` — {payload.selected_sop_name} (Severity: {payload.severity})"

        return content

    except Exception as e:
        logger.warning(f"LLM grounded response generation unavailable ({e}). Employing deterministic advisory fallback.")
        return format_deterministic_advisory(payload)
