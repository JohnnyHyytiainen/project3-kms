# search.py - Sökningen: En fråga in och källor ut.
# Kod: Engelska
# Kommentarer: Svenska

"""
The RETRIEVAL step. The question becomes a vector with the SAME function AND model
that embedded the entire corpus. Chroma (The derivative) returns the nearest(Top K) vector_ids,
Postgres (The truth) returns what they point at. No reranking and no generation.
"""

import uuid

from chromadb.api.models.Collection import Collection
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from kms.db.models import Chunk
from kms.embedding.embed import course_tags_for, embed_texts


# ===== 1: Formen på EN träff =====
# Pydantic och inte dict - FastAPI validerar svaret och visar formen i SwaggerUI.
# Samma form är det som Streamlit och eval-harness kommer att läsa.
class SearchHit(BaseModel):
    rank: int  # 1 = närmast frågan
    distance: float  # Cosinusavstånd, 1 - cosine. Lägre "poäng" == närmare
    text: str  # Chunkens text ur Postgres
    document_id: int
    chunk_index: int
    filename: str
    source_type: str
    courses: list[str]
    source_location: dict | None  # sidor för PDF, rad för .md, tid för transcript


# ===== 2: Sökningen =====
def search(
    question: str,
    k: int,
    *,
    session: Session,
    openai_client: OpenAI,
    collection: Collection,
) -> list[SearchHit]:
    """
    Embeds the question and fetches the K nearest vectors from Chroma and looks up their chunk rows in PSQL.
    Returns hits in Chromas order.

    Fails LOUDLY if a vector has no chunk row:
    The index is out of sync and every answer after that COULD point at the wrong source.
    """
    # Samma funktion som embeddade korpusen. Exakt samma modell och format.
    query_vector = embed_texts(openai_client, [question])[0]

    # Endast ID och AVSTÅND ur Chroma. Texten finns där med, men Postgres är SANNINGEN
    # och filnamn, kurs och source_location finns ENDAST i Postgres.
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=k,
        include=["distances"],
    )
    # [0]: en fråga in ger en lista med svar PER fråga
    vector_ids = result["ids"][0]
    distances = result["distances"][0]

    # WHERE vector_id IN (..), Postgres lovar INGEN ordning på raderna över huvudtaget
    statement = select(Chunk).where(
        Chunk.vector_id.in_([uuid.UUID(v) for v in vector_ids])
    )
    chunks_by_id = {str(c.vector_id): c for c in session.execute(statement).scalars()}

    hits: list[SearchHit] = []
    # Ordningen kommer från Chroma, innehållet från Postgres
    for rank, (vector_id, distance) in enumerate(zip(vector_ids, distances), start=1):
        chunk = chunks_by_id.get(vector_id)
        if chunk is None:
            raise RuntimeError(
                f"Vector {vector_id} has no chunk row in Postgres. "
                f"The Index is out of sync, run the reconciliation."
            )
        document = chunk.document
        hits.append(
            SearchHit(
                rank=rank,
                distance=distance,
                text=chunk.content,
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                filename=document.filename,
                source_type=document.source_type,
                courses=course_tags_for(document),
                source_location=chunk.source_location,
            )
        )
    return hits
