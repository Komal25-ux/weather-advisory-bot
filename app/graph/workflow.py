from typing import Any, Optional, Dict
import logging
from langgraph.graph import StateGraph, START, END

from app.graph.state import WeatherState
from app.graph.nodes import (
    parse_intent_node,
    resolve_location_node,
    fetch_weather_node,
    match_sops_node,
    select_decision_node,
    generate_response_node,
    handle_intent_clarification_node,
    handle_failure_node,
    handle_no_sop_node,
)
from app.graph.routing import (
    route_after_intent,
    route_after_location,
    route_after_weather,
    route_after_matching,
)

logger = logging.getLogger("weather-advisory-bot.graph.workflow")


def build_weather_graph(checkpointer: Optional[Any] = None) -> Any:
    """
    Constructs and compiles the real LangGraph StateGraph with explicit conditional edges
    and session-scoped memory checkpointing.
    """
    builder = StateGraph(WeatherState)

    # 1. Register all primary and failure nodes
    builder.add_node("parse_intent", parse_intent_node)
    builder.add_node("resolve_location", resolve_location_node)
    builder.add_node("fetch_weather", fetch_weather_node)
    builder.add_node("match_sops", match_sops_node)
    builder.add_node("select_decision", select_decision_node)
    builder.add_node("generate_response", generate_response_node)

    builder.add_node("handle_intent_clarification", handle_intent_clarification_node)
    builder.add_node("handle_failure", handle_failure_node)
    builder.add_node("handle_no_sop", handle_no_sop_node)

    # 2. Add entrypoint
    builder.add_edge(START, "parse_intent")

    # 3. Add conditional edge 1: Intent -> Clarification OR Location Resolution
    builder.add_conditional_edges(
        "parse_intent",
        route_after_intent,
        {
            "handle_intent_clarification": "handle_intent_clarification",
            "resolve_location": "resolve_location"
        }
    )

    # 4. Add conditional edge 2: Location -> Failure OR Weather Fetch
    builder.add_conditional_edges(
        "resolve_location",
        route_after_location,
        {
            "handle_failure": "handle_failure",
            "fetch_weather": "fetch_weather"
        }
    )

    # 5. Add conditional edge 3: Weather -> Failure OR SOP Matching
    builder.add_conditional_edges(
        "fetch_weather",
        route_after_weather,
        {
            "handle_failure": "handle_failure",
            "match_sops": "match_sops"
        }
    )

    # 6. Add conditional edge 4: SOP Matching -> No-SOP OR Decision Selection
    builder.add_conditional_edges(
        "match_sops",
        route_after_matching,
        {
            "handle_no_sop": "handle_no_sop",
            "select_decision": "select_decision"
        }
    )

    # 7. Linear completion path: Decision -> Response Generation -> END
    builder.add_edge("select_decision", "generate_response")
    builder.add_edge("generate_response", END)

    # 8. Terminal failure edges
    builder.add_edge("handle_intent_clarification", END)
    builder.add_edge("handle_failure", END)
    builder.add_edge("handle_no_sop", END)

    # 9. Compile the graph with checkpointer
    if checkpointer is False:
        # Allows explicitly disabling checkpointer if requested
        compiled_graph = builder.compile()
    elif checkpointer is not None:
        compiled_graph = builder.compile(checkpointer=checkpointer)
    else:
        from app.services.session import session_manager
        compiled_graph = builder.compile(checkpointer=session_manager.checkpointer)

    if checkpointer is not False:
        import uuid
        orig_ainvoke = compiled_graph.ainvoke
        orig_invoke = compiled_graph.invoke

        def _ensure_config(input_data: Any, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            cfg = dict(config or {})
            configurable = dict(cfg.get("configurable", {}))
            if "thread_id" not in configurable:
                if isinstance(input_data, dict) and input_data.get("session_id"):
                    configurable["thread_id"] = str(input_data["session_id"]).strip()
                else:
                    configurable["thread_id"] = f"auto-{uuid.uuid4().hex[:8]}"
            cfg["configurable"] = configurable
            return cfg

        async def auto_thread_ainvoke(input_data: Any, config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
            cfg = _ensure_config(input_data, config)
            return await orig_ainvoke(input_data, config=cfg, **kwargs)

        def auto_thread_invoke(input_data: Any, config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
            cfg = _ensure_config(input_data, config)
            return orig_invoke(input_data, config=cfg, **kwargs)

        compiled_graph.ainvoke = auto_thread_ainvoke
        compiled_graph.invoke = auto_thread_invoke

    logger.info("LangGraph StateGraph compiled successfully with checkpointer.")
    return compiled_graph
