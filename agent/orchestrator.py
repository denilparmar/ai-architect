from agent.factory import build_agent
from config import config
from memory.short_term import ShortTermMemory
from observability.logger import get_logger

logger = get_logger(__name__)


def handle_query(question: str, thread_id: str) -> str:
    """Entry point for all user queries - builds the agent and runs it."""
    try:
        logger.info(f"Handling query for session {thread_id}: {question}")
        agent, memory = build_agent()
        agent_config = {"configurable": {"thread_id": thread_id}}
        response = agent.invoke(
            {"messages": [{"role": "user", "content": question}]}, agent_config
        )
        return response["messages"][-1].content
    finally:
        memory.close()


def list_sessions(limit: int = 20) -> list[dict]:
    """Most recently active sessions: thread_id, last_active (ISO timestamp) and preview."""
    memory = ShortTermMemory(config["memory"]["DATABASE_URL"])
    try:
        return memory.list_sessions(limit)
    finally:
        memory.close()


def get_session_history(thread_id: str) -> list[dict]:
    """User/assistant messages of a session as {"role", "content"} dicts."""
    memory = ShortTermMemory(config["memory"]["DATABASE_URL"])
    try:
        return memory.get_history(thread_id)
    finally:
        memory.close()
