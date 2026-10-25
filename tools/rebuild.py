# rebuild.py - Bygger om hela lagret ur repos_for_data/
# Anledningen: ändrat kursmaterial når indexet bara med en full ombyggnad
#
# Kod: Engelska
# Kommentarer: Svenska
#
# Ordningen scriptet körs med är:
# Kontrollera, fråga, töm(truncate), töm(drop collection - chroma), ingest, extract och embed,
# och till sist stäm av(reconcile). Reconciliation steget LÄSER bara, den rättar ingenting utan skriker endast vid fel.
# Körs med: uv run python tools/rebuild.py

import time

from sqlalchemy import create_engine, text

from kms.config import settings
from kms.embedding.embed import (
    COLLECTION_NAME,
    get_chroma_client,
    get_openai_client,
    require_embedding_ready,
    run_embedding,
)
from kms.embedding.reconcile import run_reconciliation
from kms.extraction.extract import run_extraction
from kms.ingestion.ingest import run_ingestion

# Endast tables som byggs ur repos_for_data/ folder får stå här
# users, alembic_versions går inte att bygga om och rörs ALDRIG
# Räknas upp en och en av design, CASCADE hade även tömt framtida tables som
# pekar på documents utan att någon ber om det.
DERIVED_TABLES = ("chunks", "source_files", "documents", "courses")


# ===== 1: Kontroll för att chroma + grunden client är uppe och nåbara innan något annat =====
def check_embedding_services() -> None:
    """
    Stops a run before anything is truncated IF Chroma OR Grunden.ai is unreachable.

    The same checks the run_embedding()-function makes itself.
    A full rebuild runs them twice using only one tiny extra call.
    This way, run_embedding()-function still works on its own.
    """
    # Chroma - Klienten ansluter redan när den skapas.
    # heartbeat() är inbyggd metod i Chroma och gör kontrollen synlig i själva koden här.
    get_chroma_client().heartbeat()
    # Grunden - Rätt nyckel, rätt modell, rätt dimension. Ett anrop med endast en text.
    require_embedding_ready(get_openai_client())


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
    print(
        f" Vectors:  {COLLECTION_NAME} @ {settings.CHROMA_HOST}:{settings.CHROMA_PORT}"
    )
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


# ===== 4: Töm vectors, likt truncate_derived_tables() funktionen fast för vektorer =====
def drop_collection() -> None:
    """
    Deletes the ChromaDB collection. To ensure vectors for removed files aren't kept.

    run_embedding() creates it again with the correct settings (cosine and no embedding function),
    this way the settings live in ONE place and ONE place only: embed.py script.
    """
    client = get_chroma_client()
    # fungerar likt DROP TABLE IF EXISTS.
    # Existerar data? Töm. Existerar ingen data? Finns inget att tömma.
    if COLLECTION_NAME in [collection.name for collection in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)


# ===== 5: Orkestrering =====
def main() -> None:
    check_embedding_services()

    if not confirm_rebuild():
        print("Aborted. NOTHING was changed.")
        return

    # Ordningen är låst: extraktionen arbetar bara på PENDING rows.
    # embeddingen tar bara EXTRACTED rows. Varje steg skapar statusen som nästa steg letar efter.
    steps = [
        ("truncate", truncate_derived_tables),
        ("drop chroma", drop_collection),
        ("ingestion", run_ingestion),
        ("extraction", run_extraction),
        ("embedding", run_embedding),
        ("reconcile", run_reconciliation),
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
