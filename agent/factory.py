# import json
# import re

from contextlib import asynccontextmanager

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.interrupt_middleware import (ClarificationInterruptMiddleware,
                                        ask_user, one_tool_call_per_turn)
from agent.prompts_library import SYSTEM_PROMPTS
from agent.tools import capacity_calculator
from db_store import DatabaseStore
from llm.factory import get_llm
from memory.short_term import ShortTermMemory
from observability.logger import get_logger
from schemas import ComponentChoices, RequirementSpec

# CapacitySpec

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


_AWS_DOCS_SERVER = StdioServerParameters(
    command="uvx", args=["awslabs.aws-documentation-mcp-server"]
)


def _mcp_tool_to_langchain(session: ClientSession, mcp_tool) -> StructuredTool:
    async def call(**kwargs) -> str:
        result = await session.call_tool(name=mcp_tool.name, arguments=kwargs)
        text = "".join(c.text for c in result.content if hasattr(c, "text"))
        if result.is_error:
            raise RuntimeError(f"MCP tool {mcp_tool.name} failed: {text}")
        return text

    return StructuredTool(
        name=mcp_tool.name,
        description=mcp_tool.description or mcp_tool.name,
        args_schema=mcp_tool.input_schema,
        coroutine=call,
        handle_tool_error=True,
    )


@asynccontextmanager
async def build_component_agent():
    """Yield the component selection agent wired to the AWS documentation MCP tools.

    The MCP server subprocess lives only inside this context, so invoke the agent
    within it.
    """
    async with stdio_client(_AWS_DOCS_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            yield create_agent(
                get_llm(),
                system_prompt=SYSTEM_PROMPTS["components_selection"],
                tools=[_mcp_tool_to_langchain(session, t) for t in mcp_tools],
                response_format=ToolStrategy(ComponentChoices),
            )


def build_capacity_agent(requirement_spec):
    capacity_results = None
    try:
        # llm = get_llm()
        # agent = create_agent(
        #     llm,
        #     system_prompt=(
        #         f"{SYSTEM_PROMPTS['capacity_calculator_prompt']}\n\n"
        #         "Requirement specification:\n"
        #         f"{json.dumps(requirement_spec, indent=2)}"
        #     ),
        #     tools=[capacity_calculator.calculate_capacity],
        #     response_format=ToolStrategy(CapacitySpec),
        # )
        capacity_results = capacity_calculator.calculate_capacity(requirement_spec)
    except Exception as e:
        print(f"Error occurred while building the agent. Closing memory. {e}")
        raise
    return capacity_results
