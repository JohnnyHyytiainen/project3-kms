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

import pytest
from fastapi.testclient import TestClient

from kms.api.main import app, get_chroma_collection, get_embedding_client, get_session


# ====== Fixture: Klienten med utbytta beroenden ======
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
