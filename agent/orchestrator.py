import atexit

from langgraph.types import Command

from agent.factory import build_req_agent
from observability.logger import get_logger


logger = get_logger(__name__)
_agent = None
_memory = None


def _close_memory() -> None:
    if _memory:
        _memory.close()


atexit.register(_close_memory)


def handle_query(question: str, thread_id: str) -> str:
    """Entry point for all user queries - reuses the agent and runs it."""
    global _agent, _memory

    logger.info(f"Handling query for session {thread_id}: {question}")
    if _agent is None:
        _agent, _memory = build_req_agent()
    agent_config = {"configurable": {"thread_id": thread_id}}
    response = _agent.invoke({"messages": [{"role": "user", "content": question}]}, agent_config)
    result = _handle_interrupts(_agent, response, agent_config)
    final_message = result["messages"][-1].content
    print("\nFinal Structured Requirement Spec (JSON):")
    print(final_message)
    return final_message

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
            question = action_request["args"].get("question") or action_request["description"]
            user_input = ""
            while not user_input:
                user_input = input(f"[HITL] {question} ").strip()
                if not user_input:
                    logger.info("Empty clarification response; asking again")
            decisions.append({"type": "respond", "message": user_input})

        result = agent.invoke(Command(resume={"decisions": decisions}), config)
    return result


