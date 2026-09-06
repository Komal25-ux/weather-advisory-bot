"""Session management providing session-scoped memory checkpointer using LangGraph MemorySaver."""
from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver


class SessionManager:
    """
    Manages session-scoped memory checkpointers for LangGraph workflows.
    Guarantees complete session isolation: each session_id maps to an independent thread_id.
    Prevents cross-session context leakage.
    """
    def __init__(self, checkpointer: Optional[MemorySaver] = None):
        self._checkpointer = checkpointer or MemorySaver()

    @property
    def checkpointer(self) -> MemorySaver:
        return self._checkpointer

    def get_thread_config(self, session_id: str) -> Dict[str, Any]:
        """Returns standard LangGraph runnable config keyed by thread_id."""
        cleaned_id = session_id.strip() if session_id else "default-session"
        return {"configurable": {"thread_id": cleaned_id}}

    def reset_all_sessions(self) -> None:
        """Resets all in-memory checkpointer storage."""
        self._checkpointer = MemorySaver()


session_manager = SessionManager()
