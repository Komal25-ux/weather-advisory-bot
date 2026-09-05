"""LLM service skeleton for Iteration 1."""
from typing import List, Dict, Optional
from app.schemas.intent import StructuredIntent


async def extract_intent(
    user_message: str,
    chat_history: Optional[List[Dict[str, str]]] = None
) -> StructuredIntent:
    """
    Placeholder: calls LLM for structured intent extraction.
    Full implementation scheduled for Iteration 4.
    """
    raise NotImplementedError("LLM intent extraction will be implemented in Iteration 4.")


async def generate_grounded_response(
    decision_payload: Dict,
) -> str:
    """
    Placeholder: verbalizes deterministic decision into user-facing response.
    Full implementation scheduled for Iteration 7.
    """
    raise NotImplementedError("LLM response generation will be implemented in Iteration 7.")
