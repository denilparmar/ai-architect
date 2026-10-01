from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import config
from llm.factory import get_llm
from observability.logger import get_logger

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
                "autocommit": True,  # required by PostgresSaver
                "prepare_threshold": 0,  # avoids issues with PgBouncer
                "row_factory": dict_row,  # required by PostgresSaver
            },
        )
        self.checkpointer = PostgresSaver(self._pool)
        self.checkpointer.setup()  # creates tables on first run; safe to repeat
        logger.info("Short-term memory initialised (backend=postgres)")

    @staticmethod
    def config_for(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """Return the most recently active threads with a preview of their first question."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """SELECT thread_id, MAX(checkpoint->>'ts') AS last_active
                   FROM checkpoints
                   WHERE checkpoint_ns = ''
                   GROUP BY thread_id
                   ORDER BY last_active DESC
                   LIMIT %s""",
                (limit,),
            ).fetchall()
        for row in rows:
            history = self.get_history(row["thread_id"])
            row["preview"] = next(
                (m["content"] for m in history if m["role"] == "user"), ""
            )
        return rows

    def get_history(self, thread_id: str) -> list[dict]:
        """Return the user/assistant messages of a thread as {"role", "content"} dicts."""
        state = self.checkpointer.get_tuple(self.config_for(thread_id))
        if state is None:
            return []
        roles = {"human": "user", "ai": "assistant"}
        return [
            {"role": roles[m.type], "content": m.text}
            for m in state.checkpoint["channel_values"].get("messages", [])
            if m.type in roles
            and m.text
            # skip the synthetic summary SummarizationMiddleware injects
            and m.additional_kwargs.get("lc_source") != "summarization"
        ]

    def clear(self, thread_id: str) -> None:
        self.checkpointer.delete_thread(thread_id)

    def close(self) -> None:
        self._pool.close()

    @staticmethod
    def get_summarization_middleware() -> SummarizationMiddleware:
        return SummarizationMiddleware(
            model=get_llm(),
            trigger=("tokens", config["memory"]["summarize_at_tokens"]),
            keep=("messages", config["memory"]["keep_last_messages"]),
        )
