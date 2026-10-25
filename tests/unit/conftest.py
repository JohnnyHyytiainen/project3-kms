# conftest.py - Körs automatiskt av Pytest INNAN någon testfil i mappen tests/unit/ importeras.
# Ligger här och INTE i tests/ så en framtida tests/integration/-folder INTE ska påverkas.
# Den ska använda RIKTIGA .env värden mot riktig Postgres. Unit lagret ska inte behöva det alls.

# .env är redan .gitignored och Ci pipens checkout saknar den helt.
# Utan den här kraschar VARJE testfil vid import INNAN ett enda test hinner köras,
# eftersom att kms.config skapar Settings() redan vid modul-import och KRÄVER alla fält

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# models.py importerar endast SQLAlchemy och aldrig kms.config, därför är importen safe här
# Ovanför alla env variabler nedanför
from kms.db.models import Base, Course, Document, SourceFile


_UNIT_TEST_DEFAULTS = {
    "DB_USER": "test",
    "DB_PASSWORD": "test",
    "DB_NAME": "test",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "CHROMA_HOST": "localhost",
    "CHROMA_PORT": "8006",
    "GRUNDEN_API_KEY": "test",
}

# setdefault - RÖR aldrig en variabel som REDAN FINNS.
for key, value in _UNIT_TEST_DEFAULTS.items():
    os.environ.setdefault(key, value)


# === Delad fixture: Session =====
@pytest.fixture
def session():
    """
    A brand new empty SQLite in-memory DB per test.
    Function scoped - Pytest-default.

    Each test gets its own instance,
    zero risk for a test row from a test to leak into the next test.
    """
    engine = create_engine("sqlite:///:memory:")

    # Bara tabellerna ingestionen skriver till. chunks har JSONB som SQLite inte kan rendera,
    # därför byggs INTE hela Base.metadata. courses och source_files saknar JSONB och går bra.
    Base.metadata.create_all(
        engine,
        tables=[Document.__table__, Course.__table__, SourceFile.__table__],
    )

    with Session(engine) as session:
        yield session  # testet körs här

    engine.dispose()  # körs även om testet failar (teardown)
