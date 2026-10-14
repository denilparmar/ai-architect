import json

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from agent.interrupt_middleware import (
    ClarificationInterruptMiddleware,
    ask_user,
    one_tool_call_per_turn,
)
from agent.prompts_library import SYSTEM_PROMPTS
from agent.tools import capacity_calculator
from db_store import DatabaseStore
from llm.factory import get_llm
from memory.short_term import ShortTermMemory
from observability.logger import get_logger
from schemas import RequirementSpec

logger = get_logger(__name__)


def build_req_agent():
    """Create and return a Langchain requirement agent with persistent memory."""
    memory = None
    database = None
    try:
        llm = get_llm()
        database = DatabaseStore()
        memory = ShortTermMemory(database.pool)
        agent = create_agent(
            llm,
            system_prompt=SYSTEM_PROMPTS["requirements"],
            tools=[ask_user],
            response_format=ToolStrategy(RequirementSpec),
            checkpointer=memory.checkpointer,
            middleware=[
                ShortTermMemory.get_summarization_middleware(),
                ClarificationInterruptMiddleware(),
                one_tool_call_per_turn,
            ],
        )
    except Exception as e:
        print(f"Error occurred while building the agent. Closing memory. {e}")
        if database:
            database.close()
        raise
    return agent, memory, database


def build_capacity_agent(requirement_spec):
    try:
        llm = get_llm()
        agent = create_agent(
            llm,
            system_prompt=(
                f"{SYSTEM_PROMPTS['capacity_calculator_prompt']}\n\n"
                "Requirement specification:\n"
                f"{json.dumps(requirement_spec, indent=2)}"
            ),
            tools=[capacity_calculator.calculate_capacity],
        )
    except Exception as e:
        print(f"Error occurred while building the agent. Closing memory. {e}")
        raise
    return agent
