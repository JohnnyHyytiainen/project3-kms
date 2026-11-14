# agent_instructions.py
# Vad agenten får veta: instruktionen och prompten
# Kod: Engelska
# Kommentarer: Svenska

# Importerar ALDRIG agent.py. Pilen går bara åt ett håll: agent.py -> den här filen
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
