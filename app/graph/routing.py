"""Conditional edge routing skeleton for Iteration 1."""
from app.graph.state import WeatherState


def route_after_intent(state: WeatherState) -> str:
    """Route to clarification or location resolution."""
    raise NotImplementedError("Routing functions will be implemented in Iteration 5.")


def route_after_location(state: WeatherState) -> str:
    """Route to failure handler or weather fetching."""
    raise NotImplementedError("Routing functions will be implemented in Iteration 5.")


def route_after_weather(state: WeatherState) -> str:
    """Route to failure handler or SOP matching."""
    raise NotImplementedError("Routing functions will be implemented in Iteration 5.")


def route_after_matching(state: WeatherState) -> str:
    """Route to no-SOP handler or decision selection."""
    raise NotImplementedError("Routing functions will be implemented in Iteration 5.")
