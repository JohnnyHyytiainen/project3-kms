# conftest.py - Körs automatiskt av Pytest INNAN någon testfil i mappen tests/unit/ importeras.
# Ligger här och INTE i tests/ så en framtida tests/integration/-folder INTE ska påverkas.
# Den ska använda RIKTIGA .env värden mot riktig LocalStack/Postgres. Unit lagret ska inte behöva det alls.

# .env är redan .gitignored och Ci pipens checkout saknar den helt.
# Utan den här kraschar VARJE testfil vid import INNAN ett enda test hinner köras,
# eftersom att kms.config skapar Settings() redan vid modul-import och KRÄVER alla fält

import os

_UNIT_TEST_DEFAULTS = {
    "DB_USER": "test",
    "DB_PASSWORD": "test",
    "DB_NAME": "test",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "GRUNDEN_API_KEY": "test",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_ENDPOINT_URL": "http://localhost:4566",
}

# setdefault - RÖR aldrig en variabel som REDAN FINNS.
for key, value in _UNIT_TEST_DEFAULTS.items():
    os.environ.setdefault(key, value)
