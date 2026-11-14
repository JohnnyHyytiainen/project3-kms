# agent.py
# Skapandet av min agent, och svaret från den
# Kod: Engelska
# Kommentarer: Svenska

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from kms.config import settings
from kms.embedding.constants import GRUNDEN_BASE_URL
from kms.generation.agent_instructions import ANSWER_INSTRUCTIONS, build_prompt
from kms.retrieval.search import SearchHit

# ===== 1: Agenten =====
# Skapas EN gång när filen importeras, precis som settings i config.py
answer_agent = Agent(
    OpenAIChatModel(
        settings.ANSWER_MODEL,
        provider=OpenAIProvider(
            base_url=GRUNDEN_BASE_URL, api_key=settings.GRUNDEN_API_KEY
        ),
    ),
    instructions=ANSWER_INSTRUCTIONS,
)


# ===== 2: Svaret =====
def generate_answer(question: str, hits: list[SearchHit]) -> str:
    """
    Sends the prompt to the answer model ONCE and returns the answer as plain text.
    Tests swap the model with answer_agent.override(model=TestModel())
    and never call Grunden.
    """
    result = answer_agent.run_sync(build_prompt(question, hits))
    return result.output
