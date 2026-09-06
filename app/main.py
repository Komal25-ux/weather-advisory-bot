"""FastAPI application entrypoint skeleton for Iteration 1."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas.api import HealthResponse, ChatRequest, ChatResponse, TraceResponse
from app.policies.loader import load_sops_from_directory
from app.graph.workflow import build_weather_graph

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("weather-advisory-bot")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Weather-Advisory Support Bot service...")
    logger.info(f"Environment: {settings.ENVIRONMENT}, LLM Model: {settings.LLM_MODEL}")
    try:
        app.state.sops = load_sops_from_directory(settings.SOPS_DIR)
        logger.info(f"Loaded {len(app.state.sops)} SOPs into application state.")
        # Compile LangGraph state machine with session checkpointer
        app.state.graph = build_weather_graph()
        logger.info("Compiled LangGraph state machine with session-scoped checkpointer.")
    except Exception as e:
        logger.error(f"Failed to load SOP policies or compile graph during startup: {e}")
        app.state.sops = []
        app.state.graph = None
        raise
    yield
    logger.info("Shutting down Weather-Advisory Support Bot service...")


app = FastAPI(
    title="Weather-Advisory Support Bot API",
    description="Deterministic-first safety advisory system powered by LangGraph and Open-Meteo",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
async def health_check() -> HealthResponse:
    """System health and readiness check reporting loaded SOP count."""
    loaded_count = len(getattr(app.state, "sops", []))
    return HealthResponse(
        status="ok",
        loaded_sops_count=loaded_count,
        version="1.0.0"
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint orchestrating user queries through the LangGraph StateGraph.
    Maintains session-scoped memory via checkpointer keyed by session_id.
    """
    graph = getattr(app.state, "graph", None)
    if graph is None:
        graph = build_weather_graph()
        app.state.graph = graph

    cleaned_session_id = request.session_id.strip() if request.session_id else "default-session"
    cleaned_message = request.message.strip()

    initial_state = {
        "session_id": cleaned_session_id,
        "user_message": cleaned_message,
    }

    final_state = await graph.ainvoke(initial_state)

    selected_sop = final_state.get("selected_sop") or {}
    applicable_sops = selected_sop.get("applicable_sop_ids") or []
    if not applicable_sops and selected_sop.get("sop_id"):
        applicable_sops = [selected_sop.get("sop_id")]

    location = final_state.get("resolved_location_name") or final_state.get("location_name")
    time_period = final_state.get("time_reference")

    trace = TraceResponse(
        activity=final_state.get("activity"),
        intent_category=final_state.get("intent_category"),
        location_query=final_state.get("location_name"),
        resolved_location=final_state.get("resolved_location_name"),
        latitude=final_state.get("latitude"),
        longitude=final_state.get("longitude"),
        time_reference=final_state.get("time_reference"),
        target_group=final_state.get("target_group"),
        matched_sop_count=len(applicable_sops),
        candidate_sop_ids=applicable_sops,
        selected_sop_id=selected_sop.get("sop_id"),
        decision_severity=final_state.get("decision_severity"),
        decision_trace=final_state.get("decision_trace"),
    )

    return ChatResponse(
        session_id=cleaned_session_id,
        response_type=final_state.get("response_type", "SUCCESS"),
        response=final_state.get("response", ""),
        sop_id=selected_sop.get("sop_id"),
        sop_name=selected_sop.get("name"),
        severity=final_state.get("decision_severity"),
        recommendation=final_state.get("decision_recommendation"),
        location=location,
        time_period=time_period,
        applicable_sop_ids=applicable_sops,
        weather_facts=final_state.get("weather_facts"),
        decision_trace=final_state.get("decision_trace"),
        trace=trace,
    )


# Serve frontend if static assets exist
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Weather Advisory Support Bot API is running. Frontend index.html not found."}
