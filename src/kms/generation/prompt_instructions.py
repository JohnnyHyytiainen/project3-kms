# answer.py
# Kod: Engelska
# Kommentarer: Svenska

from pydantic_ai import Agent

from kms.retrieval.search import SearchHit

# ===== 1: Instruktionerna(prompten) =====
ANSWER_INSTRUCTIONS = (
    "Answer in the same language the user inputs. Answer only from the numbered sources in the prompt. "
    "If the sources do not contain the answer, say that the sources are missing. "
    "Cite each source you use with its number in brackets, like [1]."
)


# ===== 2: Prompten ur träffarna =====
def build_prompt(question: str, hits: list[SearchHit]) -> str:
    """
    Builds the prompt from the numbered hits and the question.
    The number of each source is the hit's rank, so [2] in the answer
    points at the hit with rank 2.
    """
    sources = "\n\n".join(f"[{hit.rank}] {hit.filename}\n{hit.text}" for hit in hits)
    return f"Sources:\n\n{sources}\n\nQuestion: {question}"


# ===== 3: Svaret =====
def generate_answer(
    question: str,
    hits: list[SearchHit],
    *,
    agent: Agent[None, str],
) -> str:
    """
    Sends the prompt to the answer model ONCE and returns the answer as plain text.
    The agent comes in as an argument and is created once elsewhere,
    so a test can pass in an agent with a test model instead.
    """
    result = agent.run_sync(build_prompt(question, hits))
    return result.output
