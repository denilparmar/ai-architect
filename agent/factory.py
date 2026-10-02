import os
from urllib.parse import quote

from langchain.agents import create_agent
from agent.interrupt_middleware import ClarificationInterruptMiddleware, ask_user
from agent.prompts_library import SYSTEM_PROMPTS
from memory.short_term import ShortTermMemory
from llm.factory import get_llm
from observability.logger import get_logger
from config import config

logger = get_logger(__name__)
def build_req_agent():
    """Create and return a Langchain requirement agent with persistent memory."""
    memory = None
    try:
        llm = get_llm()
        memory_config = config["memory"]
        db_user = os.getenv("DB_USER") or 'postgres'
        db_password = os.getenv("DB_PASSWORD") or 'postgres'

        if not db_user or db_password is None:
            raise RuntimeError("DB_USER and DB_PASSWORD must be set in .env")

        db_uri = (
                f"postgresql://{quote(db_user, safe='')}:{quote(db_password, safe='')}"
                f"@{memory_config['host']}:{memory_config['port']}"
                f"/{quote(memory_config['database'], safe='')}"
            )
        memory = ShortTermMemory(db_uri)
        
        agent = create_agent(
            llm,
            system_prompt=SYSTEM_PROMPTS["requirements"],
            tools=[ask_user],
            checkpointer=memory.checkpointer,
            middleware=[
                ShortTermMemory.get_summarization_middleware(),
                ClarificationInterruptMiddleware(),
            ]
        )
    except Exception as e:
        print(f"Error occurred while building the agent. Closing memory. {e}")
        if memory:
            memory.close()
        raise
    return agent, memory
