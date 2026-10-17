# Script för att stämma av Postgres & Chroma
# Reconciliation
# Kod: Engelska
# Kommentarer: Svenska

"""
Reconciliation step - Proves that PostgreSQL (the truth) and ChromaDB (The derivative)
are in sync -AFTER- the embedding step has run.

Three checks against REAL data:
1) Every chunk of an EMBEDDED document has its vectors in Chroma.
2) Every vector in Chroma has its chunk row in Postgres.
3) No document is WITHOUT a course - Meaning a row in source_files.

No change in logic, fails LOUDLY with every problem listed and not just the first
"""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from kms.config import settings
from kms.db.models import Chunk, Document, DocumentStatus
from kms.embedding.embed import COLLECTION_NAME, get_chroma_client

# Sample size över hur många IDn som ska visas per fel. ALLA IDn är irrelevant
SAMPLE_SIZE = 6


# --- 1: Postgres sidan (SANNINGEN) ---
def load_postgres_ids(session: Session) -> tuple[set[str], set[str]]:
    """
    Returns all_ids, embedded_ids, both as strings.

    all_ids: Every chunk row, whichever status its document has.
    embedded_ids: Only chunks from documents in Postgres with status is EMBEDDED.
    """
    # En och endast en fråga: chunkens vector_id och documents status bredvid varandra
    statement = select(Chunk.vector_id, Document.status).join(Chunk.document)
    rows = session.execute(statement).all()

    # str() på PSQL sidan, samma str() som embed_one_document() använde när den skrev till Chroma.
    # Åt andra hållet är det uuid.UUID() på Chromas IDn, krasch på exakt det främmande ID som
    # kontrollen finns till för att hitta.
    all_ids = {str(vector_id) for vector_id, _ in rows}
    embedded_ids = {
        str(vector_id)
        for vector_id, status in rows
        if status == DocumentStatus.EMBEDDED
    }
    return all_ids, embedded_ids


# --- 2: ChromaDBs sida (derivatet) ---
def load_chroma_ids() -> set[str]:
    """
    Every ID in the collection. Only IDs - NO vectors, texts or metadata.

    Designed to fail LOUDLY if get() returned fewer IDs than count() says exists.
    """
    collection = get_chroma_client().get_collection(
        COLLECTION_NAME, embedding_function=None
    )
    # include=[] ger bara IDn. Klienten sätter ingen gräns, serverns är omätt över 7820.
    ids = collection.get(include=[])["ids"]

    # Skydd om servern har en gräns som inte är bekräftad ännu.
    expected = collection.count()
    if len(ids) != expected:
        raise RuntimeError(
            f"Chroma get() returned {len(ids)} IDs but count() says {expected}. "
            f"The server may put a cap on get(), fetch IDs in pages instead."
        )
    return set(ids)


# --- 3: Kurserna som endast bor i Postgres ---
def load_documents_without_course(session: Session) -> list[int]:
    """
    IDs of documents with no row in source_files and therefore no course.

    The schema allows for it: The foreign key points FROM source_files TO documents.
    Ingestion is what guarantees it, which is why it has to be checked as well.
    """
    statement = (
        select(Document.id).where(~Document.source_files.any()).order_by(Document.id)
    )
    return list(session.execute(statement).scalars().all())


# --- 4: Avstämningen (reconciliation) ---
def run_reconciliation() -> None:
    """
    Compares the two systems in BOTH of its directions and checks the courses.
    Prints a summary and raises RuntimeError with every problem if anything is off.

    Has the same shape as run_embedding(): runs alone or as the last step in rebuild.py.
    """
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        all_ids, embedded_ids = load_postgres_ids(session)
        without_course = load_documents_without_course(session)

    chroma_ids = load_chroma_ids()

    # Första riktningen. Sanningen(PSQL) -> Derivatet(Chroma). Bara det PSQL påstår är EMBEDDED.
    missing_vectors = embedded_ids - chroma_ids
    # Andra riktningen. Derivatet(Chroma) -> Sanningen(PSQL). Mot ALLA chunked rows.
    # En vector UTAN rad är alltid fel och SKA alltid vara fel oavsett status.
    orphan_vectors = chroma_ids - all_ids

    print(f"Postgres: {len(all_ids)} chunk rows, {len(embedded_ids)} EMBEDDED")
    print(f"Chroma:   {len(chroma_ids)} vectors")

    # Samla alla olika typer av fel INNAN något kastas för att ge HELA bilden på en körning som output.
    problems: list[str] = []
    if missing_vectors:
        sample = sorted(missing_vectors)[:SAMPLE_SIZE]
        problems.append(f"{len(missing_vectors)} chunk rows without a vector: {sample}")
    if orphan_vectors:
        sample = sorted(orphan_vectors)[:SAMPLE_SIZE]
        problems.append(f"{len(orphan_vectors)} vectors without a chunk row: {sample}")
    if without_course:
        sample = without_course[:SAMPLE_SIZE]
        problems.append(f"{len(without_course)} documents without a course: {sample}")

    if problems:
        raise RuntimeError("Reconciliation FAILED:\n  " + "\n  ".join(problems))

    print(
        "Reconciliation is OK: both directions are empty, every document has a course."
    )


# === ENTRYPOINT ===
if __name__ == "__main__":
    run_reconciliation()
