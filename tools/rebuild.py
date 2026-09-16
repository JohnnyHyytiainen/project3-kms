# rebuild.py - Bygger om hela lagret ur repos_for_data/
# Anledningen: S3-bucket och localstack behåller inte data
# Vid varje avstängning av docker så försvinner datan. Syftet är att
# kringgå data persistancy issues.
#
# Kod: Engelska
# Kommentarer: Svenska
#
# Ordningen scriptet körs med är:
# Kontrollera, fråga, töm, ingest, extract.
# Körs med: uv run python tools/rebuild.py

import time

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import create_engine, text

from kms.config import settings
from kms.extraction.extract import run_extraction
from kms.ingestion.ingest import run_ingestion
from kms.storage.s3_client import get_s3_client

# Endast tables som byggs ur repos_for_data/ folder får stå här
# users, alembic_versions går inte att bygga om och rörs ALDRIG
# Räknas upp en och en av design, CASCADE hade även tömt framtida tables som
# pekar på documents utan att någon ber om det.
DERIVED_TABLES = ("chunks", "documents")


# ===== 1: Kontrollera FÖRST innan något annat =====
def check_localstack() -> None:
    """
    Stops the run before anything is truncated if LocalStack is not answering.

    list_buckets() is a read only call. An empty list is a valid answer:
    LocalStack is up and running but was restarted, which is why this script
    even exists.
    """
    try:
        get_s3_client().list_buckets()
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(
            f"LocalStack is not answering at {settings.AWS_ENDPOINT_URL}: {e}. "
            f"Nothing has been truncated. Start the containers and try to run again."
        ) from None


# ===== 2: Ja eller nej frågan =====
def confirm_rebuild() -> bool:
    """
    Shows what is about to be truncated and THEN asks.

    The Password is NEVER printed.
    Only host, port and DB name.

    Requires a strict 'yes' to be typed to continue to run.
    """
    print("This will TRUNCATE and rebuild from repos_for_data/:")
    print(f" Database: {settings.DB_NAME} @ {settings.DB_HOST}:{settings.DB_PORT}")
    print(f" Tables:   {', '.join(DERIVED_TABLES)}")
    print(f" Bucket:   {settings.S3_BUCKET_NAME} @ {settings.AWS_ENDPOINT_URL}")
    answer = input("Type 'yes' to continue: ")
    # Exakt 'yes'. Ett slarvigt 'y' eller en Enter ska inte räcka för att tömma något.
    return answer.strip().lower() == "yes"


# ===== 3: Töm det ursprungliga =====
def truncate_derived_tables() -> None:
    """
    Empties the derived tables in ONE statement.

    RESTART IDENTITY resets id counters.
    Reason is: To give the same document its same id on EVERY
    rebuild and so that document_id in the Parquet files stays
    reproducible.
    """
    engine = create_engine(settings.database_url)
    # engine.begin() = EN transaktion.
    # Tabellnamnen kommer från konstanten ovan, aldrig från användaren, därför är f-strängen ofarlig här.
    with engine.begin() as connection:
        connection.execute(
            text(f"TRUNCATE TABLE {', '.join(DERIVED_TABLES)} RESTART IDENTITY")
        )
    engine.dispose()


# ===== 4: Orkestrering =====
def main() -> None:
    check_localstack()

    if not confirm_rebuild():
        print("Aborted. NOTHING was changed.")
        return

    # Ordningen är låst: extraktionen arbetar bara på PENDING rows.
    # och dom skapas av ingestion. MVP v3 läggs embedding till som en rad här.
    steps = [
        ("truncate", truncate_derived_tables),
        ("ingestion", run_ingestion),
        ("extraction", run_extraction),
    ]

    # Klockan startar EFTER frågan, väntan på ett svar ska inte räknas in i tiden.
    timings: dict[str, float] = {}
    for name, step in steps:
        print(f"\n=== {name} ===")
        start = time.perf_counter()
        step()
        timings[name] = time.perf_counter() - start

    print("\n=== REBUILD DONE ===")
    for name, seconds in timings.items():
        print(f"  {name:<12}{seconds:6.1f} s")
    print(f"  {'total':<12}{sum(timings.values()):6.1f} s")


# === ENTRYPOINT ===
if __name__ == "__main__":
    main()
