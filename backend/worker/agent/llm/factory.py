from worker.agent.llm.base import LLMProvider
from worker.agent.llm.groq_provider import GroqProvider


def make_provider(model: str | None = None) -> LLMProvider:
    return GroqProvider(model)
