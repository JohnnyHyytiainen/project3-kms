# extract.py - Script för att orkestrera chunking, pdf_extractor och parquet_writer scripts.
# Kod: Engelska
# Kommentarer: Svenska
#
# Scriptet vet endast VAD som ska hända med dokument och i vilken ordning
# Scriptet har ingen aning om HUR stegen utförs, det ligger i ovannämnda script + s3_client scriptet.
# Exakt samma uppdelning av arbete som ingest.py redan använder sig utav
#
# Hämta det som har status PENDING ur Postgres, hämta hem filen från S3, konvertera till text, chunka upp filen
# Skriv parquet till silver, skriv chunk rader och uppdatera status i Postgres.

import enum
import tempfile
from collections.abc import Callable
from pathlib import Path

from botocore.exceptions import ClientError
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from kms.config import settings
from kms.db.models import Chunk, Document, DocumentStatus
from kms.extraction.chunker import Section, chunk_document
from kms.extraction.pdf_extractor import PdfExtractionError, extract_pages
from kms.storage.parquet_writer import write_chunks_to_parquet
from kms.storage.s3_client import download_file, ensure_bucket_exists, get_s3_client


# --- 1: Extraherings outcome ---
# Vad händer med -ett- dokument under en körning
class ExtractionOutcome(str, enum.Enum):
    """
    Result of processing ONE document in ONE run.

    Not the same hting as DocumentStatus by design.
    SKIPPED is not a state a document can be in, a skipped document
    is still pending and unprocessed.

    Skipped only describes the previous/current RUN, not the DOCUMENT ITSELF.
    """

    EXTRACTED = "extracted"
    FAILED = "failed"
    SKIPPED = "skipped"


# --- 2: Section byggande, en per filtyp ---
def build_sections_from_pdfs(local_path: Path) -> list[Section]:
    """
    Turns a PDF into chunkable units that chunk_document()-function expects.

    Only thing carried over from PDF-structure is the page number.
    Its course, filename and source_type are already columns on the Document row,
    all are reachable through their document_id.
    """
    pages = extract_pages(local_path)
    return [
        Section(text=page.text, source_location={"page: page.page_number"})
        for page in pages
    ]


# Registret över filtyper systemet kan hantera.
# s3key = Document.source_type, värde = funktionen som kan just den filtypen.
#
# Att lägga till markdown eller transkript senare är EN ny funktion och EN rad här.
SECTION_BUILDERS: dict[str, Callable[[Path], list[Section]]] = {
    "pdf": build_sections_from_pdfs,
}


# --- 3: Helper funktion för dokument som misslyckas ---
# privat funktion FAAFO
def _mark_failed(
    session: Session, document: Document, message: str
) -> ExtractionOutcome:
    """
    Marks a document as unusable, and documents why.

    Commit here instead of later in the run.
    A later commit during run leads to a later crash and information
    cannot erase what was already learned about earlier documents.

    error_message is a note to a human, not a log line,
    capped and truncated to 1000 chars.
    """
    document.status = DocumentStatus.FAILED
    document.error_message = message[:1000]
    session.commit()
    print(f"[FAILED] {document.s3_key}: {message}")
    return ExtractionOutcome.FAILED


# --- 4: Funktion för att extrahera ETT dokument ---
def extract_one_document(
    document: Document,
    s3_client,
    bucket_name: str,
    session: Session,
) -> ExtractionOutcome:
    """
    Only ONE document is processed.

    document.id already exists - the row came from a SELECT and not from session.add().

    The flush() timing problem that the parquet_writers schema guards against,
    belongs to ingest.py script and NOT to this function.
    """
    # KeyError här betyder att frågan längst ner hämtade en filtyp som inte finns i registret
    # KeyError innebär alltså ett fel i koden här och inte i ett dokument.
    builder = SECTION_BUILDERS[document.source_type]

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = Path(tmp_dir) / document.filename

        # --- Hämtar hem bronze data från S3 bucket ---
        try:
            download_file(s3_client, bucket_name, document.s3_key, str(local_path))
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("404", "NoSuchKey"):
                # Objektet saknas i S3 bucket. Det är fakta om själva DOKUMENTET (se extraction_logic_flowchart_mvp_v2)
                return _mark_failed(
                    session, document, f"S3 object missing: {document.s3_key}"
                )
            # Alla andra issues är fakta om INFRASTRUKTUREN i sig (se extraction_logic_flowchart_mvp_v2)
            # Att sätta FAILED här hade varit missvisande då det är infrastrukturen och inte dokumentet det handlar om.
            # Failed här hade raderat PENDING som i sin tur är det enda som gör en omkörning möjlig.
            print(f"[SKIPPING] S3 download failed for {document.s3_key}: {e}")
            return ExtractionOutcome.SKIPPED

        # --- Gör om filen till TEXT ---
        try:
            sections = builder(local_path)
        except PdfExtractionError as e:
            # Filen kan inte läsas. Fakta om DOKUMENTET (se extraction_logic_flowchart_mvp_v2)
            return _mark_failed(session, document, f"extraction failed: {e}")

        chunks = chunk_document(sections)

        # --- Mätpunkt ---
        # Ett dokument utan chunks är inte extraherat. Krasch ska inte ske riktigt ännu:
        # Först måste jag veta hur MÅNGA av de 134st PDF'er som hamnar här.
        # Anledning: För att göra antalet möjligt att göra SQL queries mot.
        if not chunks:
            return _mark_failed(
                session, document, "0 chunks: all sections below MIN_CHUNK_SIZE"
            )

        # --- Sidoeffekt 1/2: skriv Parquet till S3 ---
        # Nyckeln byggs av dokumentets existerande s3_key och aldrig från grunden.
        # Att den är förutsägbar är det som gör en omkörning ofarlig,
        # samma dokument skriver alltid över samma fil istället för att skapa en ny
        # (Idempotens)
        silver_key = f"silver/{document.s3_key}.parquet"
        try:
            write_chunks_to_parquet(
                chunks, document.id, silver_key, s3_client, bucket_name
            )
        except ClientError as e:
            print(f" === [SKIPPING] parquet upload failed for {silver_key}: {e} === ")
            return ExtractionOutcome.SKIPPED

        # --- Sidoeffekt 2/2: skriv till Postgres med EN transaktion ---
        # Rensar först eventuella chunk-rader från tidigare försök som blivit avbrutna.
        # Samma tanke som att .parquet skrivs över,
        # körningen ska gå att göra om UTAN att lämna dubbletter efter sig.
        # (Idempotens även här)
        session.execute(delete(Chunk).where(Chunk.document_id == document.id))

        # source_location skickas som en vanlig dict(hash table) här.
        # Postgres columnen är JSONB(binary) och tar emot dicten direkt.
        # I Parquetfilen blir samma fält en JSON string.
        # Samma data, två lagringsformat.
        session.add_all(
            [
                Chunk(
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    source_location=chunk.source_location,
                    char_count=chunk.char_count,
                )
                for chunk in chunks
            ]
        )
        document.status = DocumentStatus.EXTRACTED
        document.error_message = None
        session.commit()

    return ExtractionOutcome.EXTRACTED


# --- 5: Funktion som fungerar som min ORKESTRERING ---
def run_extraction() -> None:
    """
    Sets up the connection, ITERATES over every PENDING document then prints a summary in terminal.

    Same shape as run_ingestion() by design: a function that only wires things
    up and iterates is the same thing as a Airflow task,
    this way in MVP v5 there will be no need rewrite this file.
    """
    engine = create_engine(settings.database_url)
    s3_client = get_s3_client()
    # FAILA HÖGT om LocalStack är dött. S3 Bucket finns redan efter ingestion är körd,
    # men anropet är gratis och gör det här skriptet körbart på egen hand och standalone.
    ensure_bucket_exists(s3_client, settings.S3_BUCKET_NAME)

    counts = {outcome: 0 for outcome in ExtractionOutcome}

    with Session(engine) as session:
        # Filter på source_type läses direkt UR registret.
        # Ska jag lägga till andra filtyper gör jag det i
        # build_sections_from_pdfs()-FUNKTIONEN och då expanderar den här frågan automatiskt.
        # Filtyper som inte ännu har en byggare hämtas aldrig, dom hoppas alltså inte över i tystnad
        # dom ligger endast kvar som PENDING tills modulen finns/är byggd.
        statement = (
            select(Document)
            .where(Document.status == DocumentStatus.PENDING)
            .where(Document.source_type.in_(SECTION_BUILDERS.keys()))
            .order_by(Document.id)
        )

        # .all() istället för att streama: raderna innehåller lite metadata,
        # och commitas inne i loopen.
        # Att iterera över en öppen databas-markör samtidigt som man committar är en fälla att undvika.
        # Därför ska allting hämtas klart först.
        documents = session.execute(statement).scalars().all()
        print(
            f"Found {len(documents)} PENDING documents "
            f"of type: {sorted(SECTION_BUILDERS)}"
        )

        for document in documents:
            outcome = extract_one_document(
                document, s3_client, settings.S3_BUCKET_NAME, session
            )
            counts[outcome] += 1

    print(
        f"DONE - {counts[ExtractionOutcome.EXTRACTED]} EXTRACTED, "
        f"{counts[ExtractionOutcome.FAILED]} FAILED, "
        f"{counts[ExtractionOutcome.SKIPPED]} SKIPPED."
    )


# === ENTRYPOINT ===
if __name__ == "__main__":
    run_extraction()
