# test_retrieval_search.py - Tester för search i kms.retrieval.search
# =========
# search() ska testas direkt utan HTTP. Beroenden skickas in som argument direkt,
# så att varken patchning eller overrides behövs här.
# Grunden, Chroma och session är attrapper. Chunkarna är RIKTIGA orm-objekt som lever in memory.
#
# Attrapperna(mocks) bevisar INTE: att WHERE-filter hittar rätt rader i Postgres.
# FakeSession lämnar ut de rows den fick oavsett vad frågan säger. Det är integrationstestens jobb.
#
# Del 1: Ordningen och innehållet
# A1: Träffarna följer Chromas ordning, även när raderna kommer i en annan ordning
# B1: Kurserna, platsen och dokumentets fält kommer från raden, kurserna sorterade
#
# Del 2: Felvägen
# A2: En vektor utan chunkrad kastar, i stället för att hoppas över i tysthet
#
# Del 3: Anropen
# A3: Frågan embeddas med korpusens modell och format, och k blir n_results
#


import uuid
from types import SimpleNamespace

import pytest

from kms.db.models import Chunk, Course, Document, DocumentStatus, SourceFile
from kms.embedding.constants import EMBEDDING_MODEL
from kms.retrieval.search import search


# ====== Testdubbletter: attrapper(mocks) för Grunden, Chroma och sessionen ======
class FakeEmbeddings:
    """Stand-in for client.embeddings. Records every call, returns one vector per text."""

    def __init__(self):
        self.calls = []

    def create(self, *, model, input, encoding_format):
        self.calls.append(
            {"model": model, "input": input, "encoding_format": encoding_format}
        )
        # Samma form som Grundens svar: resp.data[i].index och resp.data[i].embedding
        data = [
            SimpleNamespace(index=i, embedding=[0.1, 0.2, 0.3])
            for i, _ in enumerate(input)
        ]
        return SimpleNamespace(data=data)


class FakeClient:
    """Stand-in for the OpenAI client. Only .embeddings is used by search()."""

    def __init__(self):
        self.embeddings = FakeEmbeddings()


class FakeCollection:
    """Stand-in for the Chroma collection. Answers query() with fixed ids and distances."""

    def __init__(self, ids, distances):
        self.ids = ids
        self.distances = distances
        self.queries = []  # Varje fråga sparas så att testet kan granska den.

    def query(self, *, query_embeddings, n_results, include):
        self.queries.append(
            {
                "query_embeddings": query_embeddings,
                "n_results": n_results,
                "include": include,
            }
        )
        # En lista per fråga, precis som ChromaDB. search() skickar alltid EN fråga
        return {"ids": [self.ids], "distances": [self.distances]}


class FakeResult:
    """What session.execute() returns. search() only calls .scalars() on it."""

    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return iter(self.rows)


class FakeSession:
    """
    Stand-in for an SQLAlchemy session.
    execute() ignores the statement and hands back the rows it was given, in that order.
    """

    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement):
        return FakeResult(self.rows)


def make_chunk(chunk_index, content, *, course_tags=("data_platform",)):
    """
    A real Chunk with a real Document and SourceFiles, never added to a session.
    search() reads exactly the same attributes as in a real run.
    """
    document = Document(
        id=1,
        filename="slides_medallion.pdf",
        source_type="pdf",
        status=DocumentStatus.EMBEDDED,
    )
    # Kurserna går samma väg som dom gör i databasen: source_files -> courses
    document.source_files = [
        SourceFile(course=Course(course_tag=tag)) for tag in course_tags
    ]
    return Chunk(
        chunk_index=chunk_index,
        content=content,
        vector_id=uuid.uuid4(),
        source_location={"page": chunk_index + 1},
        document=document,
    )


# ====== Del 1: Ordningen och innehållet ======
# A1:
def test_search_keeps_chroma_order_when_rows_come_in_another_order():
    first, second, third = make_chunk(0, "a"), make_chunk(1, "b"), make_chunk(2, "c")
    # Chroma: närmast först. Den ordningen är sökningens svar
    collection = FakeCollection(
        ids=[str(third.vector_id), str(first.vector_id), str(second.vector_id)],
        distances=[0.1, 0.2, 0.3],
    )
    # Postgres lovar ingen ordning - raderna kommer i en annan ordning än Chromas
    session = FakeSession([first, second, third])

    hits = search(
        "silver layer",
        3,
        session=session,
        openai_client=FakeClient(),
        collection=collection,
    )

    assert [h.text for h in hits] == ["c", "a", "b"]
    assert [h.rank for h in hits] == [1, 2, 3]
    assert [h.distance for h in hits] == [0.1, 0.2, 0.3]


# B1:
def test_search_takes_courses_and_source_location_from_the_row():
    # Samma innehåll i två kurser, i ordning som inte är sorterad
    chunk = make_chunk(4, "silver", course_tags=("data_platform", "ai_engineering"))
    collection = FakeCollection(ids=[str(chunk.vector_id)], distances=[0.25])

    [hit] = search(
        "silver layer",
        1,
        session=FakeSession([chunk]),
        openai_client=FakeClient(),
        collection=collection,
    )

    # Alla kurser, sorterade, så att samma dokument ALLTID ger samma lista
    assert hit.courses == ["ai_engineering", "data_platform"]
    assert hit.source_location == {"page": 5}
    assert hit.filename == "slides_medallion.pdf"
    assert hit.source_type == "pdf"
    assert hit.document_id == 1
    assert hit.chunk_index == 4


# ====== Del 2: Felvägen(failure path) ======
# A2:
def test_search_raises_when_a_vector_has_no_chunk_row():
    known = make_chunk(0, "a")
    # En vektor i Chroma som saknar en rad i Postgres: indexet är INTE i synk
    orphan_id = str(uuid.uuid4())
    collection = FakeCollection(
        ids=[str(known.vector_id), orphan_id], distances=[0.1, 0.2]
    )

    # match: felet ska namnge EXAKT den vektorn som saknar rad
    with pytest.raises(RuntimeError, match=orphan_id):
        search(
            "silver layer",
            2,
            session=FakeSession([known]),
            openai_client=FakeClient(),
            collection=collection,
        )


# ====== Del 3: Anropen ======
# A3:
# Två värden för k, inget av dom standardvärdet 5. Ett hårdkodat tal kan bara träffa ett av dem
@pytest.mark.parametrize("k", [3, 7])
def test_search_embeds_with_corpus_model_and_passes_k_on(k):
    chunk = make_chunk(0, "a")
    client = FakeClient()
    collection = FakeCollection(ids=[str(chunk.vector_id)], distances=[0.1])

    search(
        "silver layer",
        k,
        session=FakeSession([chunk]),
        openai_client=client,
        collection=collection,
    )

    # Exakt ett anrop mot Grunden.ai, med frågan som enda text och korpusens modell
    assert client.embeddings.calls == [
        {
            "model": EMBEDDING_MODEL,
            "input": ["silver layer"],
            "encoding_format": "float",
        }
    ]
    # Exakt en fråga mot Chroma: k blir n_results, och vektorn är den Grunden.ai gav
    [query] = collection.queries
    assert query["n_results"] == k
    assert query["query_embeddings"] == [[0.1, 0.2, 0.3]]
    assert query["include"] == ["distances"]
