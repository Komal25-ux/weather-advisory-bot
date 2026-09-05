"""FastAPI application entrypoint skeleton for Iteration 1."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.schemas.api import HealthResponse, ChatRequest, ChatResponse
from app.policies.loader import load_sops_from_directory

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("weather-advisory-bot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Weather-Advisory Support Bot service...")
    logger.info(f"Environment: {settings.ENVIRONMENT}, LLM Model: {settings.LLM_MODEL}")
    try:
        app.state.sops = load_sops_from_directory(settings.SOPS_DIR)
        logger.info(f"Loaded {len(app.state.sops)} SOPs into application state.")
    except Exception as e:
        logger.error(f"Failed to load SOP policies during startup: {e}")
        app.state.sops = []
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
    Main chat endpoint.
    Orchestration via LangGraph StateMachine scheduled for Iteration 5.
    """
    raise NotImplementedError("Chat orchestration scheduled for Iteration 5.")
