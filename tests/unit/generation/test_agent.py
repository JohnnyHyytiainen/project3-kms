# test_agent.py - Tester för svarsmodellen(response model) i kms.generation.agent scriptet
# Kod: Engelska
# Kommentarer: Svenska
#
# Del 1: Test av build_answer_model() funktionen med de tre värden som når modellen
# A1: Två uppsättningar av values, inget av dom från settings, modellen får exakt dom.
#
# Del 2: Test för answer_agent variabeln. Byggd från svarsinställningarna och INTE från embedding modellen
# A2: adress, nyckel och modellnamnet kommer ifrån ANSWER_* i src.kms.config.py


import pytest

from kms.config import settings
from kms.embedding.constants import GRUNDEN_BASE_URL
from kms.generation.agent import answer_agent, build_answer_model


# ====== Del 1: Test för build_answer_model() ======
# ==================================================
# Två uppsättningar av values, ett hardcoded value i
# funktionen kan bara stämma med ett value
#
# A1:
@pytest.mark.parametrize(
    ("base_url", "api_key", "model_name"),
    [
        ("http://provider-a.test/v1", "key-a", "model-a"),
        ("http://provider-b.test/v1", "key-b", "model-b"),
    ],
)
def test_build_answer_model_uses_given_values(base_url, api_key, model_name):
    model = build_answer_model(
        base_url=base_url, api_key=api_key, model_name=model_name
    )

    assert model.model_name == model_name
    # OpenAI-klienten lägger alltid till ett snedstreck sist i adressen
    assert model.base_url.rstrip("/") == base_url
    assert model.client.api_key == api_key


# ====== Del 2: Test för answer_agent variabeln ======
# ====================================================
# Agenten skapas bara vid import med värden som
# conftest.py lämnar till settings
#
# A2:
def test_answer_agent_is_built_from_answer_settings():
    # Svarets värden skiljer sig embeddingens med flit
    assert settings.ANSWER_BASE_URL != GRUNDEN_BASE_URL
    assert settings.ANSWER_API_KEY != settings.GRUNDEN_API_KEY

    model = answer_agent.model

    assert model.model_name == settings.ANSWER_MODEL
    assert model.base_url.rstrip("/") == settings.ANSWER_BASE_URL
    assert model.client.api_key == settings.ANSWER_API_KEY
