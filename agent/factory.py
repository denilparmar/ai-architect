from langchain.agents import create_agent
from memory.short_term import ShortTermMemory
from llm.factory import get_llm
from observability.logger import get_logger
from config import config

logger = get_logger(__name__)

SYSTEM_PROMPT = """Placeholder for defining the prompt here"""

def build_agent():
    """Create and return a Langchain agent with persistent memory."""
    try:
        llm = get_llm()
        db_uri = config["memory"]["DATABASE_URL"]
        memory = ShortTermMemory(db_uri)
        
        agent = create_agent(
            llm,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=memory.checkpointer,
            middleware=[
                ShortTermMemory.get_summarization_middleware()
            ]
        )
    except Exception:
        memory.close()
        raise
    return agent, memory
