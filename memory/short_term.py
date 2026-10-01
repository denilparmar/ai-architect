from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from observability.logger import get_logger
from langchain.agents.middleware import SummarizationMiddleware
from config import config
from llm.factory import get_llm

logger = get_logger(__name__)


class ShortTermMemory:
    """Postgres-backed checkpointer for thread-scoped conversation state."""

    def __init__(self, db_uri: str, max_pool_size: int = 10):
        # A pool (not a single connection) so a long-running app survives
        # dropped connections and can serve concurrent requests.
        self._pool = ConnectionPool(
            conninfo=db_uri,
            max_size=max_pool_size,
            open=True,
            kwargs={
                "autocommit": True,        # required by PostgresSaver
                "prepare_threshold": 0,    # avoids issues with PgBouncer
                "row_factory": dict_row,   # required by PostgresSaver
            },
        )
        self.checkpointer = PostgresSaver(self._pool)
        self.checkpointer.setup()  # creates tables on first run; safe to repeat
        logger.info("Short-term memory initialised (backend=postgres)")

    @staticmethod
    def config_for(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def clear(self, thread_id: str) -> None:
        self.checkpointer.delete_thread(thread_id)

    def close(self) -> None:
        self._pool.close()

    @staticmethod
    def get_summarization_middleware() -> SummarizationMiddleware:
        return SummarizationMiddleware(
            model=get_llm(),
            trigger=("tokens", config["memory"]["summarize_at_tokens"]),
            keep=("messages", config["memory"]["keep_last_messages"])
        )