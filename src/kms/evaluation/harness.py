# harness.py - Evaluation harness script.
# Mäter hämtningen mot eval-setet
# Kod: Engelska
# Kommentarer: Svenska

"""
The evaluation step in the project. Every question in the evaluation set goes through search(), the same function that
/search uses and it is compared against the documents the answer is in.

Two measurements, both on DOCUMENTS and NOT on text:
- Hit rate@k: The share of the questions with at least one expected document in TOP k.
- MRR: Mean of 1 / rank of the first expected document, 0 when none came up.

K counts CHUNKS and not documents. One document can take one or more places in top k.
"""

import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from kms.config import settings
from kms.embedding.constants import COLLECTION_NAME
from kms.embedding.embed import (
    get_chroma_client,
    get_openai_client,
    require_embedding_ready,
)
from kms.ingestion.ingest import load_known_paths
from kms.retrieval.search import SearchHit, search

# Körs direkt ifrån root som rebuild och reconcile scripten
EVAL_DIR = Path("eval")

# EN sökning per fråga med största K. De mindre K räknas ur samma lista.
K_VALUES = (1, 3, 5, 10)
MAX_K = max(K_VALUES)


# ========== 1: Formen på ETT av paren =========
# Använder Pydantic för att validera fälten, om ett fält saknas, har fel typ så stoppas raden
class EvaluationPair(BaseModel):
    id: str
    question: str
    expected_sources: list[str]


# ========== 2: Laddaren ==========
# Funktion som laddar mina pairs
def load_pairs(path: Path) -> list[EvaluationPair]:
    """
    Reads ONE pair per line. Fails LOUDLY and FAST with file, line number and on DUPLICATED id.

    The SAME id twice makes the before and after result impossible to compare.
    """
    pairs: list[EvaluationPair] = []
    # Välj encoding då Windows default INTE är utf-8 och å/ä/ö kommer leda till att saker kraschar/går sönder
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue  # En tom rad sist i filen ska vara ofarligt
            try:
                pairs.append(EvaluationPair.model_validate_json(line))
            except ValidationError as e:
                # Trasig JSON, BOM eller fel fält(Field) ska ALLA hamna här, MED radnummer.
                raise ValueError(f"{path}, line {line_no}: {e}") from e

    ids = [pair.id for pair in pairs]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"{path}: duplicate IDs {duplicates}")
    return pairs


# ========== 3: source_path -> dokumentet ==========
# Funktion för mina FÖRVÄNTADE dokument
def expected_documents(
    session: Session, pairs: list[EvaluationPair]
) -> dict[str, set[int]]:
    """
    Function that translates every expected source_path to its document_id,
    in the SAME database that the search READS from.

    Fails with EVERY unknown path and not just the first by design.
    """
    # Samma fråga som ingestion använder. Dvs: source_path -> document_id för ALLA filer
    known_paths = load_known_paths(session)

    unknown = sorted(
        {s for pair in pairs for s in pair.expected_sources if s not in known_paths}
    )
    if unknown:
        raise ValueError("Unknown source_path in eval set:\n" + "\n".join(unknown))

    # En mängd per fråga: kopior av samma fil blir exakt SAMMA document_id och räknas endast en gång
    return {pair.id: {known_paths[s] for s in pair.expected_sources} for pair in pairs}


# ========== 4: EN fråga ==========
# Funktion för att ranka min FÖRSTA hit
def first_hit_rank(hits: list[SearchHit], expected: set[int]) -> int | None:
    """Rank of the first hits whose document IS expected. None = Nothing in top K."""
    for hit in hits:
        if hit.document_id in expected:
            return hit.rank
    return None


# ========== 5: Måtten ==========
# Funktion för att summera alla mått.
# Hit rate och MRR
def summarize_hits(ranks: list[int | None]) -> dict[str, float]:
    """Hit rate@k for every k in K_VALUES and MRR over MAX_K."""
    n = len(ranks)
    scores = {}
    for k in K_VALUES:
        # En träff på plats nummer 4 räknas för k=5 och k=10, men inte för k=1 eller för k=3
        scores[f"hit_rate@{k}"] = sum(1 for r in ranks if r is not None and r <= k) / n
    # Ingen träff ger 0, därför bör summan delas med ALLA frågor och inte bara för träffarna
    scores[f"mrr@{MAX_K}"] = sum(1 / r for r in ranks if r is not None) / n
    return scores


# ========== 6: Körningen av allting ==========
# Funktion för att köra allting
def run_eval(filename: str) -> dict[str, float]:
    """Runs every pair in eval/<FILENAME> through search() and prints out result."""
    pairs = load_pairs(EVAL_DIR / filename)

    # Samma motor som lifespan i kms.api.main: samma modell, samma samling
    engine = create_engine(settings.database_url)
    openai_client = get_openai_client()
    collection = get_chroma_client().get_collection(
        COLLECTION_NAME, embedding_function=None
    )
    # Fel nyckel eller fel dimensioner stoppas här, innan den ens når första frågan
    require_embedding_ready(openai_client)

    ranks: list[int | None] = []
    # EN session för både översättning OCH sökning - Samma databasläge
    with Session(engine) as session:
        expected_by_id = expected_documents(session, pairs)
        for pair in pairs:
            hits = search(
                pair.question,
                MAX_K,
                session=session,
                openai_client=openai_client,
                collection=collection,
            )
            rank = first_hit_rank(hits, expected_by_id[pair.id])
            ranks.append(rank)
            # "-" innebär att inget förväntat dokument kom upp i topp MAX_k
            shown = rank if rank is not None else "-"
            print(f"{pair.id} rank {shown:>2} {pair.question}")
    engine.dispose()

    scores = summarize_hits(ranks)
    print(f"\n{filename}: {len(pairs)} questions")
    for name, value in scores.items():
        print(f"  {name:<14} {value:.2f}")
    return scores


if __name__ == "__main__":
    # dev.jsonl som standard. Hold-out bara när den anges uttryckligen.
    run_eval(sys.argv[1] if len(sys.argv) > 1 else "dev.jsonl")
