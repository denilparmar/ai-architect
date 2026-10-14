from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from config import config
from llm.factory import get_llm
from observability.logger import get_logger

logger = get_logger(__name__)


class ShortTermMemory:
    """Postgres-backed checkpointer for thread-scoped conversation state."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool
        self.checkpointer = PostgresSaver(self._pool)
        self.checkpointer.setup()  # creates tables on first run; safe to repeat
        logger.info("Short-term memory initialised (backend=postgres)")

    @staticmethod
    def config_for(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def clear(self, thread_id: str) -> None:
        self.checkpointer.delete_thread(thread_id)

    @staticmethod
    def get_summarization_middleware() -> SummarizationMiddleware:
        return SummarizationMiddleware(
            model=get_llm(),
            trigger=("tokens", config["memory"]["summarize_at_tokens"]),
            keep=("messages", config["memory"]["keep_last_messages"]),
        )
