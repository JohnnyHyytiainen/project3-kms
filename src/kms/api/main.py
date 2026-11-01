# main.py - KMS servering, själva FastAPI appen
# Kod: Engelska
# Kommentarer: Svenska

"""
Serving layer for the KMS. The FastAPI app lives here and no where else.
GET /health: endpoint to prove that the process starts - Liveness only.
GET /search: endpoint for searches - Question in and sources out. NO reranking, NO generation.
"""

from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from chromadb.api.models.Collection import Collection
from fastapi import Depends, FastAPI, Query, Request
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from kms.config import settings
from kms.embedding.constants import COLLECTION_NAME
from kms.embedding.embed import (
    get_chroma_client,
    get_openai_client,
    require_embedding_ready,
)
from kms.retrieval.search import SearchHit, search


# ===== 1: Klienterna skapas EN GÅNG när servern startar =====
# async är ett krav ifrån FastAPI här. Det som blockerar görs INNAN servern tar emot trafik och allt är tomt.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Varje client har sin egen pool. Skapas de per anrop kastas poolen varje gång
    app.state.engine = create_engine(settings.database_url)
    app.state.openai_client = get_openai_client()
    # get_collection och INTE get_or_create_collection.
    # Sökningen får ALDRIG skapa ett tomt index.
    # Saknas samlingen ska servern INTE starta alls.
    app.state.collection = get_chroma_client().get_collection(
        COLLECTION_NAME, embedding_function=None
    )
    # Rätt nyckel, rätt modell, rätt dimension, innan första frågan
    require_embedding_ready(app.state.openai_client)
    yield
    # Allt efter yield körs när servern stängs
    app.state.engine.dispose()


# Appen ska startas EN GÅNG på modulnivå. Uvicorn letar upp den via 'kms.api.main:app'
app = FastAPI(
    title="KMS platform",
    description="Search over the course material. Sources first, no generation at the moment.",
    lifespan=lifespan,
)


# ===== 2: Beroenden, lämnas ut per anrop med Depends =====
# lifespan skapar klienterna en gång. Funktionerna under lämnar bara ut dom.
def get_session(request: Request) -> Iterator[Session]:
    """One session PER request, borrowed from SQLAlchemy engine pool and returned afterwards."""
    # yield - FastAPI kör raderna efter yield när anropet är klart - även när något går fel
    with Session(request.app.state.engine) as session:
        yield session


def get_embedding_client(request: Request) -> OpenAI:
    """The client that embeds the question. Same model as the corpus."""
    return request.app.state.openai_client


def get_chroma_collection(request: Request) -> Collection:
    """The collection the search reads from. Created once in lifespan."""
    return request.app.state.collection


# Typ + depends i ett och samma namn. Samma tre ska återanvändas av /ask-endpoint senare.
SessionDep = Annotated[Session, Depends(get_session)]
EmbeddingClientDep = Annotated[OpenAI, Depends(get_embedding_client)]
CollectionDep = Annotated[Collection, Depends(get_chroma_collection)]


# ===== 3: Svarets form =====
class SearchResponse(BaseModel):
    question: str
    hits: list[SearchHit]


# HEALTH ENDPOINT
@app.get("/health")
def health_endpoint() -> dict[str, str]:
    """
    Endpoint for liveness only. Prove that process is up and answers.
    Says NOTHING regarding Postgres, Chroma or Grunden.ai.
    """
    return {"status": "ok"}


# SEARCH ENDPOINT
@app.get("/search")
def search_endpoint(
    q: Annotated[str, Query(min_length=1, description="The question")],
    session: SessionDep,
    openai_client: EmbeddingClientDep,
    collection: CollectionDep,
    # k är sist: en parameter med standardvärde måste stå efter dem utan
    k: Annotated[int, Query(ge=1, le=20, description="Number of sources")] = 5,
) -> SearchResponse:
    """
    Embeds the question using bge-m3, fetches the K nearest chunks from ChromaDB and their text,
    document, course and source_location from Postgres.
    """
    hits = search(
        q,
        k,
        session=session,
        openai_client=openai_client,
        collection=collection,
    )
    return SearchResponse(question=q, hits=hits)
