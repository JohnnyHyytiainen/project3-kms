# answers_evaluation.py - Script för att utvärdera output svaren ifrån LLM
# Kör eval settets frågor genom samma väg som /ask och skriver ut svaren för mänsklig granskning och bedömning.
# Kod: Engelska
# Kommentarer: Svenska

"""
Runs every question in the evaluation set through the same path as POST /ask:
search() with k=5, then generate_answer().
Prints one block per question with the sources the model got and its answer,
for manual inspection and grading.

Grading by hand per question, with the labels from CRAG(Meta, 2024):
- Grounded: yes or no. Every claim in the answer is supported by its SOURCES.

- Label: perfect (1), acceptable (0.5), missing (0) or incorrect (-1).

    - Perfect: Answers the question and nothing is made up.
    - Acceptable: A useful but semi-incomplete/incomplete answer.
    - Missing: Says the sources are missing and answers nothing.
    - Incorrect: A wrong or made up answer.
"""

import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from kms.config import settings
from kms.embedding.constants import COLLECTION_NAME
from kms.embedding.embed import (
    get_chroma_client,
    get_openai_client,
    require_embedding_ready,
)
from kms.evaluation.harness import (
    EVAL_DIR,
    expected_documents,
    first_hit_rank,
    load_pairs,
)
from kms.generation.agent import generate_answer
from kms.retrieval.search import SearchHit, search

ASK_K = 5

SEPARATOR = "=" * 80


# ========== 1: EN fråga som text ==========
def format_answer(
    pair_id: str,
    question: str,
    hits: list[SearchHit],
    rank: int | None,
    answer: str,
) -> str:
    """
    Formats one question, the sources the model got and its answer as plain text.
    """
    # rank = platsen för första förväntade dokumentet.
    # None = inget av dom nådde fram till modellen
    reached = f"yes, rank {rank}" if rank is not None else "no"
    lines = [
        SEPARATOR,
        f"{pair_id}  expected document reached the model: {reached}",
        f"Question: {question}",
        "",
        "Sources:",
    ]
    # Samma numrering som modellen såg i build_prompt(): [1] är träffen med rank 1
    for hit in hits:
        lines.append(f"[{hit.rank}] {hit.filename} (distance {hit.distance:.3f})")
        lines.append(hit.text)
        lines.append("")
    lines += ["Answer:", answer, ""]
    # Bedömningsraden fylls i för hand. Label täcker även "underlag saknas" (missing),
    # så raden är densamma på varje fråga, även när rätt dokument men inte rätt stycke nått modellen
    lines.append("Grounded: _   Label: _")
    return "\n".join(lines)


# ========== 2: Körningen av allting ==========
def run_answers(filename: str) -> None:
    """Runs every pair in eval/<FILENAME> through search() and generate_answer()."""
    pairs = load_pairs(EVAL_DIR / filename)

    # Samma uppkoppling som run_eval i harness.py och lifespan i kms.api.main
    engine = create_engine(settings.database_url)
    openai_client = get_openai_client()
    collection = get_chroma_client().get_collection(
        COLLECTION_NAME, embedding_function=None
    )
    require_embedding_ready(openai_client)

    reached = 0
    with Session(engine) as session:
        expected_by_id = expected_documents(session, pairs)
        for pair in pairs:
            hits = search(
                pair.question,
                ASK_K,
                session=session,
                openai_client=openai_client,
                collection=collection,
            )
            rank = first_hit_rank(hits, expected_by_id[pair.id])
            if rank is not None:
                reached += 1
            # Ett anrop till svarsmodellen per fråga, samma funktion som /ask använder
            answer = generate_answer(pair.question, hits)
            # flush: genom tee syns varje svar direkt, inte först när körningen är klar
            print(format_answer(pair.id, pair.question, hits, rank, answer), flush=True)
    engine.dispose()

    print(SEPARATOR)
    print(
        f"{filename}: {len(pairs)} questions, "
        f"expected document reached the model in {reached}"
    )


if __name__ == "__main__":
    run_answers(sys.argv[1] if len(sys.argv) > 1 else "dev.jsonl")
