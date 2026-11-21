# agent.py
# Skapandet av min agent, och svaret från den
# Kod: Engelska
# Kommentarer: Svenska

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from kms.config import settings
from kms.generation.agent_instructions import ANSWER_INSTRUCTIONS, build_prompt
from kms.retrieval.search import SearchHit


# ===== 1: Modellen =====
# (*) innebär att ALLA tre värden MÅSTE anges MED namn.
# 3x str i rad är enkelt att byta plats på utan att något skriker och säger ifrån.
def build_answer_model(
    *, base_url: str, api_key: str, model_name: str
) -> OpenAIChatModel:
    """
    Builds the answer model from three values:
    address, key and the model name.

    Works with any provider that speaks/uses the OpenAI-compatible API (chat completions).
    Nothing is sent here, the client ONLY connects when the agent runs.
    """
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )


# ===== 2: Agenten =====
# Skapas EN gång när filen importeras, precis som settings i config.py
answer_agent = Agent(
    build_answer_model(
        base_url=settings.ANSWER_BASE_URL,
        api_key=settings.ANSWER_API_KEY,
        model_name=settings.ANSWER_MODEL,
    ),
    instructions=ANSWER_INSTRUCTIONS,
)


# ===== 3: Svaret =====
def generate_answer(question: str, hits: list[SearchHit]) -> str:
    """
    Sends the prompt to the answer model ONCE and returns the answer as plain text.
    Tests swap the model with answer_agent.override(model=TestModel())
    and never call Grunden.
    """
    result = answer_agent.run_sync(build_prompt(question, hits))
    return result.output
