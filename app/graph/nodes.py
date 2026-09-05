import logging
from typing import Dict, Any, List

from app.config import settings
from app.graph.state import WeatherState
from app.services.llm import extract_intent
from app.services.geocoding import (
    resolve_location,
    LocationResolutionError,
)
from app.services.weather import (
    fetch_weather_facts,
    WeatherFetchError,
    WeatherDataValidationError,
)
from app.policies.loader import load_sops_from_directory
from app.policies.matcher import match_candidate_sops

logger = logging.getLogger("weather-advisory-bot.graph.nodes")

# Cache loaded policies for the graph runner
_LOADED_SOPS = None


def _get_sops():
    global _LOADED_SOPS
    if _LOADED_SOPS is None:
        try:
            _LOADED_SOPS = load_sops_from_directory(settings.SOPS_DIR)
        except Exception as e:
            logger.error(f"Failed to load SOPs in graph node: {e}")
            _LOADED_SOPS = []
    return _LOADED_SOPS


async def parse_intent_node(state: WeatherState) -> Dict[str, Any]:
    """Node 1: Extracts structured user intent using LLM structured output."""
    user_msg = state.get("user_message", "")
    history = state.get("chat_history", [])

    try:
        intent = await extract_intent(user_message=user_msg, chat_history=history)
        needs_clarification = (
            intent.is_clarification_needed or
            not intent.location_name or
            not intent.activity
        )
        return {
            "activity": intent.activity,
            "intent_category": intent.intent_category,
            "location_name": intent.location_name,
            "time_reference": intent.time_reference or "today",
            "target_group": intent.target_group or "general",
            "intent_confidence": intent.confidence,
            "is_clarification_needed": needs_clarification,
            "trace": {
                **state.get("trace", {}),
                "extracted_activity": intent.activity,
                "extracted_location": intent.location_name,
                "time_reference": intent.time_reference,
                "target_group": intent.target_group,
            }
        }
    except Exception as e:
        logger.error(f"Intent extraction node error: {e}")
        return {
            "is_clarification_needed": True,
            "error_type": "INTENT_FAILURE",
            "error_message": str(e)
        }


async def resolve_location_node(state: WeatherState) -> Dict[str, Any]:
    """Node 2: Deterministically resolves location name to coordinates via Open-Meteo Geocoding."""
    loc_name = state.get("location_name")
    if not loc_name:
        return {
            "error_type": "LOCATION_FAILURE",
            "error_message": "Missing location name for resolution."
        }

    try:
        geo = await resolve_location(loc_name)
        return {
            "resolved_location_name": geo.resolved_name,
            "latitude": geo.latitude,
            "longitude": geo.longitude,
            "country": geo.country,
            "admin1": geo.admin1,
            "timezone": geo.timezone,
            "error_type": None,
            "error_message": None,
            "trace": {
                **state.get("trace", {}),
                "resolved_location": geo.resolved_name,
                "coordinates": {"lat": geo.latitude, "lon": geo.longitude},
                "timezone": geo.timezone,
            }
        }
    except LocationResolutionError as e:
        logger.warning(f"Location resolution failed for '{loc_name}': {e}")
        return {
            "error_type": "LOCATION_FAILURE",
            "error_message": str(e)
        }


async def fetch_weather_node(state: WeatherState) -> Dict[str, Any]:
    """Node 3: Deterministically fetches and normalizes weather facts from Open-Meteo."""
    lat = state.get("latitude")
    lon = state.get("longitude")
    time_ref = state.get("time_reference", "today")
    tz = state.get("timezone", "auto")

    if lat is None or lon is None:
        return {
            "error_type": "WEATHER_FAILURE",
            "error_message": "Cannot fetch weather without valid coordinates."
        }

    try:
        facts = await fetch_weather_facts(
            latitude=lat,
            longitude=lon,
            time_reference=time_ref,
            timezone=tz
        )
        facts_dict = facts.model_dump()
        return {
            "weather_facts": facts_dict,
            "error_type": None,
            "error_message": None,
            "trace": {
                **state.get("trace", {}),
                "weather_facts": facts_dict
            }
        }
    except (WeatherFetchError, WeatherDataValidationError) as e:
        logger.warning(f"Weather fetch failed at ({lat}, {lon}): {e}")
        return {
            "error_type": "WEATHER_FAILURE",
            "error_message": str(e)
        }


async def match_sops_node(state: WeatherState) -> Dict[str, Any]:
    """Node 4: Evaluates candidate SOPs deterministically against weather facts."""
    sops = _get_sops()
    facts = state.get("weather_facts") or {}

    # Combine weather facts with intent facts (activity, intent_category, target_group)
    combined_facts = {
        **facts,
        "activity": state.get("activity"),
        "intent_category": state.get("intent_category"),
        "target_group": state.get("target_group", "general")
    }

    candidates = match_candidate_sops(sops, combined_facts)
    cand_dicts = [c.model_dump() for c in candidates]

    return {
        "candidate_sops": cand_dicts,
        "trace": {
            **state.get("trace", {}),
            "matched_sop_count": len(candidates),
            "candidate_sop_ids": [c.sop_id for c in candidates]
        }
    }


async def select_decision_node(state: WeatherState) -> Dict[str, Any]:
    """
    Node 5: State contract placeholder for Iteration 6.
    Establishes state contract without premature safety logic.
    """
    candidates = state.get("candidate_sops", [])
    if candidates:
        top = candidates[0]
        return {
            "selected_sop": top,
            "decision_severity": top.get("severity", "LOW"),
            "decision_recommendation": "caution",
            "matched_reasons": top.get("matched_conditions", []),
            "decision_trace": f"Matched candidate {top.get('sop_id')}"
        }
    return {}


async def generate_response_node(state: WeatherState) -> Dict[str, Any]:
    """
    Node 6: Minimal integration response node for graph routing testing.
    Full LLM grounded composition scheduled for Iteration 7.
    """
    selected = state.get("selected_sop") or {}
    sop_id = selected.get("sop_id", "UNKNOWN")
    return {
        "response_type": "SUCCESS",
        "response": f"Policy evaluated: {sop_id}. Grounded guidance prepared for {sop_id}."
    }


async def handle_intent_clarification_node(state: WeatherState) -> Dict[str, Any]:
    """Failure Branch A: Requests necessary user clarification without giving advice."""
    loc = state.get("location_name")
    act = state.get("activity")

    if not loc and not act:
        msg = "Could you please specify which outdoor activity you are planning and in which city or location?"
    elif not loc:
        msg = f"Which city or location are you planning for {act}?"
    else:
        msg = f"What outdoor activity are you considering in {loc}?"

    return {
        "response_type": "INTENT_CLARIFICATION",
        "response": msg
    }


async def handle_failure_node(state: WeatherState) -> Dict[str, Any]:
    """Failure Branch B: Honest failure handling for location or weather lookup."""
    err_type = state.get("error_type", "WEATHER_FAILURE")
    loc = state.get("resolved_location_name") or state.get("location_name") or "that location"

    if err_type == "LOCATION_FAILURE":
        msg = f"I couldn't resolve that location, so I can't retrieve the weather needed for this recommendation."
        resp_type = "LOCATION_FAILURE"
    else:
        msg = f"I couldn't retrieve live weather data for {loc} right now, so I can't provide a weather-based safety recommendation."
        resp_type = "WEATHER_FAILURE"

    return {
        "response_type": resp_type,
        "response": msg
    }


async def handle_no_sop_node(state: WeatherState) -> Dict[str, Any]:
    """Failure Branch C: Refuses to fabricate advice when no SOP applies."""
    act = state.get("activity", "that activity")
    loc = state.get("resolved_location_name") or state.get("location_name") or "your location"
    facts = state.get("weather_facts", {})
    temp = facts.get("temperature_c")
    wind = facts.get("wind_speed_kmh")

    weather_summary = f" (Temperature: {temp}°C, Wind: {wind} km/h)" if temp is not None else ""
    msg = (
        f"I don't have an applicable safety policy for {act} under the current weather scenario in {loc}{weather_summary}, "
        "so I cannot provide a safety recommendation."
    )
    return {
        "response_type": "NO_SOP",
        "response": msg
    }
