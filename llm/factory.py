from config import config
from observability.logger import get_logger

logger = get_logger(__name__)


def get_llm():
    """Return the right LangChain LLM based on config."""
    provider = config["llm"]["provider"]
    model = config["llm"]["model"]
    logger.info(f"Using LLM provider: {provider}, model: {model}")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model)

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model)
