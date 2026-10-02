from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import tool


@tool
def ask_user(question: str) -> str:
    """Ask the user one clarification question and wait for their response."""
    raise RuntimeError("ask_user must be handled by ClarificationInterruptMiddleware")


class ClarificationInterruptMiddleware(HumanInTheLoopMiddleware):
    """Pause ask_user tool calls until the user provides a response."""

    def __init__(self) -> None:
        super().__init__(
            interrupt_on={"ask_user": {"allowed_decisions": ["respond"]}}
        )