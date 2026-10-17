import atexit

from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from agent.factory import (build_capacity_agent, build_component_agent,
                           build_req_agent)
from observability.logger import get_logger
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from schemas import ComponentChoices, RequirementSpec, unknown_references

load_dotenv(Path(__file__).parent.parent / ".env")

logger = get_logger(__name__)
_agent = None
_memory = None
_database = None
# Max graph steps per agent run (each resume after a question is a new run).
REQUIREMENTS_RECURSION_LIMIT = 25

# Max graph steps for the component agent (doc searches + final structured answer).
COMPONENT_RECURSION_LIMIT = 25
MAX_VALIDATION_RETRIES = 2


def _close_database() -> None:
    if _database:
        _database.close()


atexit.register(_close_database)


def handle_query(question: str, thread_id: str) -> str:
    """Entry point for all user queries - reuses the agent and runs it."""
    global _agent, _memory, _database
    logger.info("Handling query for session %s", thread_id)
    try:
        if _agent is None:
            _agent, _memory, _database = build_req_agent()
        agent_config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": REQUIREMENTS_RECURSION_LIMIT,
        }
        try:
            response = _agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                agent_config,
            )
            result = _handle_interrupts(_agent, response, agent_config)
        except GraphRecursionError as e:
            raise RuntimeError(
                "requirements agent couldn't produce a valid spec after "
                f"{REQUIREMENTS_RECURSION_LIMIT} steps"
            ) from e
        spec = result.get("structured_response")
        if spec is None:
            raise RuntimeError("requirements agent finished without a structured spec")
        requirement_spec = spec.model_dump(mode="json")
        print("\nFinal Structured Requirement Spec (JSON):")
        print(spec.model_dump_json(indent=2))
        #_database.save_requirement_specs(thread_id, requirement_spec)

        # Call the capacity agent, which generates and saves sizing specs.
        capacity_results = invoke_capacity_agent(requirement_spec, thread_id)

        # sizing_spec_data = _database.get_sizing_specs(thread_id)
        # print("\nPrinting the sizing_spec_data now:")
        # print(sizing_spec_data)

        # call to component selection agent
        handle_component_selection(requirement_spec,capacity_results)

        # call to cost estimation agent

        # call to architecture composer agent (include design critic agent to verify)
        logger.info("Successfully handled query for session %s", thread_id)
        return spec.model_dump_json(indent=2)
    except Exception:
        logger.exception("Failed to handle query for session %s", thread_id)
        raise


def invoke_capacity_agent(requirement_spec, thread_id):
    """Invoke the capacity agent to calculate sizing specs based on the requirement spec."""
    """."""
    capacity_results = build_capacity_agent(requirement_spec)
    return capacity_results



def _handle_interrupts(agent, result, config: dict) -> dict:
    """Collect clarification answers and resume human-in-the-loop tool calls."""
    while result.get("__interrupt__"):
        interrupt = result["__interrupt__"][0]
        interrupt_data = interrupt.value
        logger.info(f"Handling interrupt: {interrupt_data}")

        action_requests = interrupt_data.get("action_requests", [])
        if not action_requests:
            logger.warning("Interrupt did not contain any action requests")
            break

        decisions = []
        for action_request in action_requests:
            question = (
                action_request["args"].get("question") or action_request["description"]
            )
            user_input = ""
            while not user_input:
                user_input = input(f"[HITL] {question} ").strip()
                if not user_input:
                    logger.info("Empty clarification response; asking again")
            decisions.append({"type": "respond", "message": user_input})

        result = agent.invoke(Command(resume={"decisions": decisions}), config)
    return result


async def _select_components(requirement_spec: dict, capacity_results) -> ComponentChoices:
    spec = RequirementSpec.model_validate(requirement_spec)
    async with build_component_agent() as agent:
        return await _run_component_agent(agent, spec, requirement_spec, capacity_results)


async def _run_component_agent(agent, spec, requirement_spec, capacity_results) -> ComponentChoices:
    messages = [
        {
            "role": "user",
            "content": (
                "1. Requirement Specification (JSON):\n"
                f"{json.dumps(requirement_spec, indent=2)}\n\n"
                "2. Capacity Calculation Results (JSON):\n"
                f"{json.dumps(capacity_results, indent=2, default=str)}\n\n"
                "3. Retrieved Architecture Guidelines: search the AWS documentation with "
                "the provided tools to ground service and instance type choices. For "
                "`kb:` references use only the documentation URL path (letters, digits, "
                "_ - . / only), e.g. kb:AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html"
            ),
        }
    ]
    config = {"recursion_limit": COMPONENT_RECURSION_LIMIT}
    for attempt in range(MAX_VALIDATION_RETRIES + 1):
        try:
            result = await agent.ainvoke({"messages": messages}, config)
        except GraphRecursionError as e:
            raise RuntimeError(
                "component agent couldn't produce a valid design after "
                f"{COMPONENT_RECURSION_LIMIT} steps"
            ) from e
        design = result.get("structured_response")
        if design is None:
            raise RuntimeError("component agent finished without a structured design")
        bad_refs = unknown_references(design, spec)
        if not bad_refs:
            return design
        if attempt == MAX_VALIDATION_RETRIES:
            raise RuntimeError(f"component design has unknown references: {bad_refs}")
        messages = result["messages"] + [
            {
                "role": "user",
                "content": (
                    f"These based_on references are not in the requirement spec: {bad_refs}. "
                    "Return the full corrected design."
                ),
            }
        ]


def handle_component_selection(requirement_spec: dict, capacity_results) -> ComponentChoices:
    design = asyncio.run(_select_components(requirement_spec, capacity_results))
    print("\nSelected components (JSON):")
    print(design.model_dump_json(indent=2))
    return design
