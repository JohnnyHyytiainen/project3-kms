# test_embedding.py - tester för att säkerställa UPSERT före commit, rätt dimensioner
# och att inga texter inte ger några anrop. Ej mot grunden utan fake klient (Duck typing)
# ====================
# Testerna är delade i 4 delar.
# Embedding steget i embed.py. Allting körs utan nätverk och utan DB.
# Grunden, chroma och psql ersätts av mockade objekt. Syftet är att testa logiken runt anropen
# och inte om grunden eller mina dependencies fungerar.
#
# Del 1: embed_texts()
# A1: Inga texter ger inga anrop och en tom list []
# B1: Omgångarna av texter, testar 1 omgång, 32 omgångar, 33 och 63(skriker i terminal)
# C1: Ordningen, servern kan svara i en annan ordning än tänkt och gör att vektorerna hamnar på fel chunk.
# Detta kan orsaka att sökningen ljuger.
# D1: Test när en vektor saknas. Varje vektor efter en lucka hänt hade då givit en vektor fast på helt fel chunk.
# Här SKA koden krascha högt istället för att förgifta datan
# E1: Test för modellen och formatet. "float" vs base64 formatet.
#
# Del 2: Tester på riktiga databasobjekt utan databas.
# SQLAlchemy låter mig skapa allting in-memory.
# A2: Test för course_tag, skicka in samma exempel ifrån samma kurs.
#
# Del 3: Tester för embeddingen av dokument och anrop(requests och responses)
# A3: Upsert ska hända INNAN commit
# B3: Embedding av dokument
# C3: Rätt vektor på rätt chunk
# D3: OpenAI felkoder och httpx2 issues (NÄTET)
# E3: Config eller fel nycklar
#
# Del 4: Tester av dimension och embeddingen
# A4: Preflight test, ska passera med förväntad dimension
# B4: Användandet av annan embedding modell som INTE är just bge-m3 med 1024 dimensioner array.
#
#
#

import uuid
from types import SimpleNamespace

import pytest
import httpx2
import openai

from kms.db.models import Chunk, Course, Document, DocumentStatus, SourceFile
from kms.embedding.embed import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    EmbeddingOutcome,
    course_tags_for,
    embed_one_document,
    embed_texts,
    require_embedding_ready,
)


# ====== Testdubbletter: Mockade beroenden enbart för att testa logiken ======
# ============================================================================
#
class FakeEmbeddings:
    """
    Standin for client.embeddings.
    Records every call and returns fake vectors for testing purposes.

    The fake vector for a text is its LENGTH, repeated dim times. This should
    make every vector traceable back to the text it originated from, which the order tests rely on.
    """

    def __init__(self, *, dim=4, reverse=False, drop_last=False, error=None):
        self.calls = []  # Varje anrop ska sparas för att testerna ska kunna räkna och granska någonting
        self.dim = dim
        self.reverse = reverse  # Ger svaren i omvänd ordning men med rätt index på varje post iallafall
        self.drop_last = drop_last  # Tappa/slarva bort sista vektorn i svaret
        self.error = error  # Släng error istället för att svara.

    def create(self, *, model, input, encoding_format):
        self.calls.append(
            {"model": model, "input": input, "encoding_format": encoding_format}
        )
        if self.error is not None:
            raise self.error
        # SimpleNamespace är ett tomt objekt med de attribut som tilldelas den.
        # Byggd med samma form som Grundens svar kräver: resp.data[i].index och resp.data[i].embedding
        data = [
            SimpleNamespace(index=i, embedding=[float(len(text))] * self.dim)
            for i, text in enumerate(input)
        ]
        if self.reverse:
            data.reverse()
        if self.drop_last:
            data.pop()
        return SimpleNamespace(data=data)


# Mockade OpenAI klienten som behövs för testerna.
class FakeClient:
    """Standin for the OpenAI client and nothing more. embeddings is used by embed.py"""

    def __init__(self, **kwargs):
        self.embeddings = FakeEmbeddings(**kwargs)


class FakeCollection:
    """Stands in for the Chroma collection. Records upserts in a shared log."""

    def __init__(self, log):
        self.log = log  # Samma lista som sessionen skriver i, så ordningen syns
        self.upserts = []  # Allt som skickades, så testet kan granska innehållet

    def upsert(self, *, ids, embeddings, documents, metadatas):
        self.log.append("upsert")
        self.upserts.append(
            {
                "ids": ids,
                "embeddings": embeddings,
                "documents": documents,
                "metadatas": metadatas,
            }
        )


class FakeSession:
    """Stands in for an SQLAlchemy session. Only commit() is used by embed_one_document()."""

    def __init__(self, log):
        self.log = log

    def commit(self):
        self.log.append("commit")


def make_document(chunk_texts, course_tags, source_type="pdf"):
    """
    A real Document with real Chunks and SourceFiles, never added to a session.
    SQLAlchemy lets ORM objects live in memory without a database, so the code
    under test reads exactly the same attributes it reads in a real run.
    """
    document = Document(id=1, source_type=source_type, status=DocumentStatus.EXTRACTED)
    # En chunk per text, med position i ordning och ett slumpat vector_id
    document.chunks = [
        Chunk(chunk_index=i, content=text, vector_id=uuid.uuid4())
        for i, text in enumerate(chunk_texts)
    ]
    # Ett exemplel per kurstagg, samma väg som i databasen: source_files -> courses
    document.source_files = [
        SourceFile(course=Course(course_tag=tag)) for tag in course_tags
    ]
    return document


# OpenAI package bygger sina fel kring en request eller ett response ifrån httpx2 och dess eget HTTP-lager
# Inget anrop görs, objekten är bara de skal som felen kräver i testerna.
FAKE_REQUEST = httpx2.Request("POST", "https://api.grunden.ai/v1/embeddings")


def make_status_error(error_class, status_code):
    """Builds an openai error that looks like it came from a real HTTP response."""
    response = httpx2.Response(status_code, request=FAKE_REQUEST)
    return error_class("fake error", response=response, body=None)


# ====== Del 1: Test för embed_texts() ======
# ===========================================
#
# A1:
def test_embed_texts_no_texts_makes_no_calls():
    client = FakeClient()

    assert embed_texts(client, []) == []
    # Den andra asserten är meningen: inte ett enda anrop mot grunden ska göras.
    # Det är meningen att köra testerna mot mockade klienten.
    assert client.embeddings.calls == []


# B1:
@pytest.mark.parametrize(
    "n_texts, expected_batch_sizes",
    [
        (1, [1]),
        (32, [32]),  # Det EXAKTA taket: endast en omgång och inte två
        (33, [32, 1]),  # Ett över taket: en till, kort omgång
        (63, [32, 31]),
    ],
)
def test_embed_texts_batches_at_32(n_texts, expected_batch_sizes):
    client = FakeClient()
    texts = [f"text {i}" for i in range(n_texts)]

    vectors = embed_texts(client, texts)

    # Storleken på varje batch i samma ordning som dom skickades
    assert [len(c["input"]) for c in client.embeddings.calls] == expected_batch_sizes
    assert len(vectors) == n_texts


# C1:
def test_embed_texts_keeps_text_order_when_server_reorders():
    client = FakeClient(dim=1, reverse=True)

    # Olika längd på texterna, så att varje vektor går att känna igen i output: "a" blir -> [1.0]
    vectors = embed_texts(client, ["a", "bb", "ccc"])

    assert vectors == [[1.0], [2.0], [3.0]]


# D1:
def test_embed_texts_raises_when_server_drops_a_vector():
    client = FakeClient(drop_last=True)

    with pytest.raises(RuntimeError):
        embed_texts(client, ["a", "bb", "ccc"])


# E1:
def test_embed_texts_sends_model_and_float_format():
    client = FakeClient()

    # 40 texter kommer bli TVÅ omgångar(32 är taket). Påståendet ska gälla vid VARJE anrop och inte bara det första
    embed_texts(client, [f"text {i}" for i in range(40)])

    for call in client.embeddings.calls:
        assert call["model"] == EMBEDDING_MODEL
        assert call["encoding_format"] == "float"


# ====== Del 2: Tester för course_tags_for() ======
# =================================================
#
# A2:
def test_course_tags_are_sorted_and_deduplicated():
    # "sql" två gånger ska ge exakt samma innehåll i två exemplar inom SAMMA kurs
    document = make_document(["text"], ["sql", "ai_engineering", "sql"])

    assert course_tags_for(document) == ["ai_engineering", "sql"]


# ====== Del 3: Tester för embed_one_document()-funktionen ======
# ===============================================================
#
# A3:
def test_upsert_happens_before_commit():
    log = []
    document = make_document(["first chunk", "second chunk"], ["sql"])

    embed_one_document(document, FakeSession(log), FakeClient(), FakeCollection(log))

    # Derivatet först, SSOT sist
    assert log == ["upsert", "commit"]


# B3:
def test_successful_document_becomes_embedded():
    log = []
    document = make_document(["first chunk"], ["sql"])

    outcome = embed_one_document(
        document, FakeSession(log), FakeClient(), FakeCollection(log)
    )

    assert outcome == EmbeddingOutcome.EMBEDDED
    assert document.status == DocumentStatus.EMBEDDED


# C3:
def test_upsert_sends_string_ids_in_chunk_order_with_metadata():
    log = []
    collection = FakeCollection(log)
    document = make_document(["a", "bb", "ccc"], ["sql", "ai_engineering"], "markdown")
    # Relationen har ingen egentlig ordning i databasen. Så här vänds relationen med flit.
    document.chunks = list(reversed(document.chunks))

    embed_one_document(document, FakeSession(log), FakeClient(dim=1), collection)

    sent = collection.upserts[0]
    in_order = sorted(document.chunks, key=lambda c: c.chunk_index)
    assert sent["ids"] == [str(c.vector_id) for c in in_order]
    assert all(
        isinstance(i, str) for i in sent["ids"]
    )  # ChromaDB tar bara emot strings
    assert sent["documents"] == ["a", "bb", "ccc"]
    assert sent["embeddings"] == [
        [1.0],
        [2.0],
        [3.0],
    ]  # Rätt vektor tilldelas till rätt chunk
    assert sent["metadatas"][0] == {
        "courses": ["ai_engineering", "sql"],
        "source_type": "markdown",
    }


# D3:
@pytest.mark.parametrize(
    "error",
    [
        openai.APIConnectionError(request=FAKE_REQUEST),  # Nätet(Nätverk issues)
        make_status_error(openai.RateLimitError, 429),  # För många anrop(Rate limits)
        make_status_error(
            openai.InternalServerError, 500
        ),  # Fel hos Grunden(Issue hos provider)
    ],
)
def test_transient_error_skips_without_writing(error):
    log = []
    document = make_document(["first chunk"], ["sql"])

    outcome = embed_one_document(
        document, FakeSession(log), FakeClient(error=error), FakeCollection(log)
    )

    assert outcome == EmbeddingOutcome.SKIPPED
    assert log == []  # Varken upsert eller commit.
    assert document.status == DocumentStatus.EXTRACTED


# E3:
def test_other_error_crashes_without_writing():
    log = []
    document = make_document(["first chunk"], ["sql"])
    error = make_status_error(openai.AuthenticationError, 401)  # Fel nyckel

    with pytest.raises(openai.AuthenticationError):
        embed_one_document(
            document, FakeSession(log), FakeClient(error=error), FakeCollection(log)
        )

    assert log == []
    assert document.status == DocumentStatus.EXTRACTED


# ====== Del 4: Test av require_embedding_ready()-funktionen ======
# =================================================================
#
# A4:
def test_preflight_passes_with_expected_dimension():
    client = FakeClient(dim=EMBEDDING_DIM)

    require_embedding_ready(client)  # Inget fel här är hela testet

    assert len(client.embeddings.calls) == 1


# B4:
def test_preflight_raises_on_wrong_dimension():
    client = FakeClient(
        dim=768
    )  # En annan modells dimension som inte är 1024-array som bge-m3 är

    with pytest.raises(RuntimeError):
        require_embedding_ready(client)
