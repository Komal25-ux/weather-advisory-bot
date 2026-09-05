"""Graph nodes skeleton for Iteration 1."""
from app.graph.state import WeatherState


async def parse_intent_node(state: WeatherState) -> WeatherState:
    """Extract structured user intent using LLM."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")


async def resolve_location_node(state: WeatherState) -> WeatherState:
    """Resolve location name to latitude/longitude."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")


async def fetch_weather_node(state: WeatherState) -> WeatherState:
    """Fetch forecast from Open-Meteo API."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")


async def match_sops_node(state: WeatherState) -> WeatherState:
    """Evaluate candidate SOPs deterministically against weather facts."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")


async def select_decision_node(state: WeatherState) -> WeatherState:
    """Select winning SOP using Severity > Priority > ID."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")


async def generate_response_node(state: WeatherState) -> WeatherState:
    """Generate grounded advisory response via LLM."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")


async def handle_intent_clarification_node(state: WeatherState) -> WeatherState:
    """Request clarification for ambiguous intent."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")


async def handle_failure_node(state: WeatherState) -> WeatherState:
    """Handle honest location or weather failure."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")


async def handle_no_sop_node(state: WeatherState) -> WeatherState:
    """Handle absence of applicable policy without fabricating advice."""
    raise NotImplementedError("Graph nodes will be implemented in Iteration 5.")
