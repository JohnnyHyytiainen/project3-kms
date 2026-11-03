# test_api.py - Tester för API't i kms.api.main. Använder TestClient och nätverk behövs ej.
#
# Appen testas genom HTTP exakt så som en klient ser den med:
# Statuskod och svarets form i JSON.
# Uppstart (Lifespan) körs inte här. TestClient utan with-statement startar aldrig appen.
# Beroenden byts ut med app.dependency_overrides - FastAPIs eget sätt.
#
# DEL 1: Validering av frågan - Statuskod 422
# A1: Tom q ger 422 och felet SKA peka på q
# B1: Saknat q ger 422, samma plats som A1 MEN annan orsak(Q finns inte ALLS)!
# C1: K ett steg UTANFÖR gränserna, 0 och 21 ska ge statuskod 422 och felet ska peka på k(Så kallad gränsvärdesanalys)
#
# DEL 2: Svar genom endpointen - Statuskod 200
# A2: k precis INNANFÖR gränserna 1 och 20, ger kod 200 och  k når ChromaDB som n_results.
# B2: Formen på svaret, det som en klient läser: question, hits och varje träffs fält.
#
#

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from kms.api.main import app, get_chroma_collection, get_embedding_client, get_session
from search_fakes import FakeClient, FakeCollection, FakeSession, make_chunk


# ====== Fixtures: Attrapper(mocks/stubs) som svarar, och klienten som använder dem med utbytta beroenden ======
def unused_dependency():
    """
    A stand-in for dependencies the request never gets to use.
    FastAPI still calls it before q is validated, therefore it has to exist.
    """
    return None


@pytest.fixture
def client():
    """
    A TestClient without lifespan with all three dependencies replaced.
    The overrides are cleared afterwards so they never leak into another test.
    """
    app.dependency_overrides[get_session] = unused_dependency
    app.dependency_overrides[get_embedding_client] = unused_dependency
    app.dependency_overrides[get_chroma_collection] = unused_dependency
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def fakes():
    """
    One chunk, and the three stand-ins that lead up to it.
    The test gets the same instance as answering_client, so it's possible to inspect what was sent.
    """
    chunk = make_chunk(0, "The silver layer holds cleaned data.")
    return SimpleNamespace(
        chunk=chunk,
        session=FakeSession([chunk]),
        openai_client=FakeClient(),
        collection=FakeCollection(ids=[str(chunk.vector_id)], distances=[0.12]),
    )


@pytest.fixture
def answering_client(fakes):
    """
    A TestClient without lifespan where the dependencies hand out the fakes.
    It is cleared afterwards, the same way as client.
    """
    app.dependency_overrides[get_session] = lambda: fakes.session
    app.dependency_overrides[get_embedding_client] = lambda: fakes.openai_client
    app.dependency_overrides[get_chroma_collection] = lambda: fakes.collection
    yield TestClient(app)
    app.dependency_overrides.clear()


# ========== DEL 1: VALIDERING AV FRÅGAN - STATUSKOD 422 ==========
#
# A1: Validering (Statuskod: 422)
def test_empty_q_returns_422(client):
    response = client.get("/search", params={"q": ""})

    assert response.status_code == 422
    # Felet ska ENDAST gälla q och INGET annat. Statuskod 422 kan lika gärna komma från k
    error = response.json()["detail"][0]
    assert error["loc"] == ["query", "q"]


# B1: Validering (Statuskod: 422 fast annan orsak - q finns INTE ALLS)
def test_missing_q_returns_422(client):
    response = client.get("/search")

    assert response.status_code == 422
    error = response.json()["detail"][0]
    # Samma plats och mönster som A1 men här saknas q
    assert error["loc"] == ["query", "q"]
    assert error["type"] == "missing"


# C1: Test av gränserna (1-20. Ett steg utanför på varsin sida, alltså 0-21)
@pytest.mark.parametrize("k", [0, 21])
def test_k_out_of_bounds_returns_422(client, k):
    # Gränserna är mellan 1-20. Testar ett steg utanför på varsin sida.
    response = client.get("/search", params={"q": "silver layer", "k": k})

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["query", "k"]


# ========== DEL 2: SVAR GENOM ENDPOINT - STATUSKOD 200 ==========
#
# A2: Gränserna -INNANFÖR- och att k faktiskt NÅR ChromaDB
@pytest.mark.parametrize("k", [1, 20])
def test_k_at_bounds_returns_200_and_reaches_chroma(answering_client, fakes, k):
    response = answering_client.get("/search", params={"q": "silver layer", "k": k})

    assert response.status_code == 200
    # Endpoint ska skicka klientens k vidare. Om K fastnar på 3, 9, eller 5 syns här.
    assert fakes.collection.queries[0]["n_results"] == k


# B2: Formen på svaret. Det som Streamlit och eval-harness kommer att läsa
def test_search_returns_question_and_hits(answering_client, fakes):
    response = answering_client.get("/search", params={"q": "silver layer"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"question", "hits"}
    assert body["question"] == "silver layer"
    # En chunk i mocken ger exakt EN träff och texten ska komma från chunken
    [hit] = body["hits"]
    assert hit["text"] == fakes.chunk.content
    # Fälten skrivs ut för hand, det är kontraktet mot klienten. Byter ett fält namn ska testet gå rött DIREKT
    assert set(hit) == {
        "rank",
        "distance",
        "text",
        "document_id",
        "chunk_index",
        "filename",
        "source_type",
        "courses",
        "source_location",
    }
