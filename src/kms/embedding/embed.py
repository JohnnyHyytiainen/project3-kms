# Script för att skapa mina embeddings
# Kod: Engelska
# Kommentarer: Svenska

"""
Embedding step. Extracted documents become vectors in ChromaDB.
Reads chunks from Postgres(SSOT), embeds them via Grunden.ai's bge-m3 embedding model,
UPSERTS them into ChromaDB on vector_id and then and ONLY then marks the document as EMBEDDED.
Chroma is always a derivate of Postgres and can be rebuilt at any time or point in the future.
"""

import enum
from itertools import batched

import chromadb
import openai
from chromadb.api import ClientAPI
from openai import OpenAI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from kms.config import settings
from kms.db.models import Document, DocumentStatus

# --- 1: Konstanter ---
GRUNDEN_BASE_URL = "https://api.grunden.ai/v1"
EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 1024  # låser Chroma-samlingen från första skrivningen.
BATCH_SIZE = 32  # Grundens uppmätta tak per anrop (422 error om större)
MAX_RETRIES = 5  # Skydd och MAX antal försök
COLLECTION_NAME = "kms_chunks"

# Fel som säger något om NÄTET eller TJÄNSTEN, inte om dokumentet.
# Allt annat (fel nyckel, fel modell, för stor batch) är fel i kod eller config.
# Menat att krascha HÖGT och inte hoppa över dokument ett i taget i tystnad
TRANSIENT_ERRORS = (
    openai.APIConnectionError,  # Pekar på NÄTET med timeout inräknad
    openai.RateLimitError,  # 429 som kvarstår efter alla omförsök
    openai.InternalServerError,  # Pekar på 5xx-felkod hos Grunden.ai
)


# --- 2: Utfall(OUTCOME) för ett dokument under en körning ---
class EmbeddingOutcome(str, enum.Enum):
    """
    Results of processing ONE document in ONE run.
    Same principle as ExtractionOutcome-class:
    SKIPPED describes the RUN and not the DOCUMENT.

    A document that is skipped is still EXTRACTED.
    """

    EMBEDDED = "embedded"
    SKIPPED = "skipped"


# --- 3: Texter går in, ut kommer vectors ---
# funktion för att ta in text och få ut vektorer
def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """
    Embeds texts in batches related to BATCH_SIZE variable.
    Returns the vectors in the SAME order as the texts.
    """
    vectors: list[list[float]] = []
    # batched() ger mig immutable tuples om HÖGST 32, den sista kan vara kortare
    for batch in batched(texts, BATCH_SIZE):
        resp = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=list(batch),
            encoding_format="float",  # float för att paketet kommer annars be om base64
        )
        # Sortera på index istället för att lita på att listan kommer i ordning
        vectors.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))

    # Säkerhet: FAILA HÖGT. Tappar servern en text hamnar varje vector efter den på FEL chunk!
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Sent {len(texts)} texts, recieved {len(vectors)} vectors back"
        )
    return vectors


# --- 4: Kursers dokument ---
def course_tags_for(document: Document) -> list[str]:
    """
    Every course the DOCUMENTs content exists in. Via source_files -> courses.

    Sorted and deduplicated so the same document ALWAYS gets the same list.
    """
    return sorted({sf.course.course_tag for sf in document.source_files})


# --- 5: ETT dokument ---
# funktion för att embedda ETT dokument
def embed_one_document(
    document: Document,
    session: Session,
    openai_client: OpenAI,
    collection,
) -> EmbeddingOutcome:
    """
    Embed only ONE document. Order matters here:
    Chroma (the derivative) first, Postgres (the truth) last.

    A crash in between them leaves the document
    EXTRACTED, and the next run overwrites the same IDs.
    """
    # Relationen har ingen ordning, här är det bättre att
    # sortera på själva på positionen
    chunks = sorted(document.chunks, key=lambda c: c.chunk_index)
    texts = [c.content for c in chunks]
    courses = course_tags_for(document)

    try:
        vectors = embed_texts(openai_client, texts)
    except TRANSIENT_ERRORS as e:
        # Ingenting är skrivet, dokumentet står kvar som EXTRACTED och tas nästa körning
        print(f"[SKIPPING] embedding failed for document: {document.id}: {e}")
        return EmbeddingOutcome.SKIPPED

    # Derivatet ska komma FÖRST. ChromaDB tar bara in strängar som ID. Postgres ger uuid.UUID
    collection.upsert(
        ids=[str(c.vector_id) for c in chunks],
        embeddings=vectors,
        documents=texts,
        metadatas=[
            {"courses": courses, "source_type": document.source_type} for _ in chunks
        ],
    )

    # Ta sanningskällan SIST.
    # Först nu är dokumentet faktiskt embeddat
    document.status = DocumentStatus.EMBEDDED
    session.commit()
    return EmbeddingOutcome.EMBEDDED


# --- 6: PREFLIGHT KONTROLL för säkerhetsskull ---
# Funktion för att kontrollera att allting är rätt.
def require_embedding_ready(openai_client: OpenAI) -> None:
    """
    One tiny call before the run: right key, right model, right dimension.
    Fails loud BEFORE any document is touched.
    """
    resp = openai_client.embeddings.create(
        model=EMBEDDING_MODEL, input=["preflight"], encoding_format="float"
    )
    dim = len(resp.data[0].embedding)
    if dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"{EMBEDDING_MODEL} returned dimension {dim}, expected {EMBEDDING_DIM}"
        )


# --- 7: Klienterna(OpenAI + chromaDB API) byggs på ETT ställe ---
# Ska ha samma form som get_s3_client() i s3_client.py
# run_embedding()-funktionen och rebuild.py använder exakt samma klient.
def get_openai_client() -> OpenAI:
    """
    Client for Grunden.ai, through the OpenAI package.
    """
    return OpenAI(
        api_key=settings.GRUNDEN_API_KEY,
        base_url=GRUNDEN_BASE_URL,
        max_retries=MAX_RETRIES,
    )


def get_chroma_client() -> ClientAPI:
    """
    The ChromaDB Client.

    HttpClient() connects already when its created.
    If Chroma is DOWN, this raises a ValueError before heartbeat() is ever reached.
    """
    return chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)


# --- 8: Mini ORKESTRERING ---
def run_embedding() -> None:
    """
    Wires things up and ITERATES over every EXTRACTED document then prints a summary.
    Same shape as run_extraction(), so it becomes an Airflow task in v5,
    without needing a complete rewrite.
    """
    engine = create_engine(settings.database_url)
    openai_client = get_openai_client()
    chroma_client = get_chroma_client()
    # Kolla om ChromaDB är uppe, kolla om Grunden.ai svarar rätt.
    # FAILA HÖGT innan något dokument rörs.
    chroma_client.heartbeat()
    require_embedding_ready(openai_client)

    # Finns samlingen redan ignoreras configuration, den gäller bara när samlingen skapas
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
    )

    counts = {outcome: 0 for outcome in EmbeddingOutcome}

    with Session(engine) as session:
        statement = (
            select(Document)
            .where(Document.status == DocumentStatus.EXTRACTED)
            .order_by(Document.id)
        )
        # .all() av samma skäl som i extract.py: Det committas inne i loopen
        documents = session.execute(statement).scalars().all()
        print(f"Found {len(documents)} EXTRACTED documents")

        for document in documents:
            outcome = embed_one_document(document, session, openai_client, collection)
            counts[outcome] += 1

    print(
        f"DONE - {counts[EmbeddingOutcome.EMBEDDED]} EMBEDDED, "
        f"{counts[EmbeddingOutcome.SKIPPED]} SKIPPED. "
        f"Collection holds {collection.count()} vectors."
    )


# === ENTRYPOINT ===
if __name__ == "__main__":
    run_embedding()
