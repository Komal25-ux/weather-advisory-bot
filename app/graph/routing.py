"""Conditional edge routing functions for LangGraph workflow."""
import logging
from app.graph.state import WeatherState

logger = logging.getLogger("weather-advisory-bot.graph.routing")


def route_after_intent(state: WeatherState) -> str:
    """
    Branch 1: After intent extraction.
    Routes to handle_intent_clarification if clarification is flagged or activity/location missing.
    Otherwise routes to resolve_location.
    """
    is_clarification = state.get("is_clarification_needed", False)
    has_loc = bool(state.get("location_name"))
    has_act = bool(state.get("activity"))

    if is_clarification or not has_loc or not has_act:
        logger.info("Routing -> handle_intent_clarification (ambiguous or missing input)")
        return "handle_intent_clarification"

    logger.info(f"Routing -> resolve_location for '{state.get('location_name')}'")
    return "resolve_location"


def route_after_location(state: WeatherState) -> str:
    """
    Branch 2: After location resolution.
    Routes to handle_failure if location lookup failed.
    Otherwise routes to fetch_weather.
    """
    error = state.get("error_type")
    lat = state.get("latitude")

    if error == "LOCATION_FAILURE" or lat is None:
        logger.info("Routing -> handle_failure (location resolution failed)")
        return "handle_failure"

    logger.info("Routing -> fetch_weather (coordinates resolved)")
    return "fetch_weather"


def route_after_weather(state: WeatherState) -> str:
    """
    Branch 3: After weather fetching.
    Routes to handle_failure if weather API call failed.
    Otherwise routes to match_sops.
    """
    error = state.get("error_type")
    facts = state.get("weather_facts")

    if error == "WEATHER_FAILURE" or facts is None:
        logger.info("Routing -> handle_failure (weather retrieval failed)")
        return "handle_failure"

    logger.info("Routing -> match_sops (live weather retrieved)")
    return "match_sops"


def route_after_matching(state: WeatherState) -> str:
    """
    Branch 4: After deterministic SOP matching.
    Routes to handle_no_sop if no SOP matched the scenario.
    Otherwise routes to select_decision.
    """
    candidates = state.get("candidate_sops", [])
    if not candidates:
        logger.info("Routing -> handle_no_sop (zero matching policies)")
        return "handle_no_sop"

    logger.info(f"Routing -> select_decision ({len(candidates)} candidate SOPs matched)")
    return "select_decision"
