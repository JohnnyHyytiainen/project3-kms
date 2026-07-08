# ingestion script för mina filer
# Kod: Engelska
# Kommentarer: Svenska
#
# Knyter ihop mina filer (Agerar orkestrator)
# course_mapping.py - Vilken kurs en fil hör till
# s3_client.py hur en fil laddas upp
# db/models.py, vad som sparas i PostgreSQL
# if __name__.... samma kod fungerar som vanliga script nu och som AIRFLOW task i MVP  V5

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Boto3
from botocore.exceptions import ClientError

# SQLAlchemy - ORM
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Import av mina dictionary mappings repots funktioner
from kms.config import settings
from kms.db.models import Document, DocumentStatus
from kms.ingestion.course_mapping import get_course_tag, get_transcript_course_tag
from kms.storage.s3_client import ensure_bucket_exists, get_s3_client, upload_file

# 1) Filtret, Endast dom här filerna
# Endast dom här filerna är välkommna i mitt data lakehouse JUST NU
SUPPORTED_SUFFIXES = {".pdf", ".md"}


# 1) Funktionen för filrtet
# Funktion för att filtrera och hitta mina "supported" filtyper.
def is_supported_file(file_path: Path) -> bool:
    """
    version 0 filter. ONLY PDF and MARKDOWN will be ingested. (Transcripts are also .md)
    The difference between 'markdown' and 'transcripts' will be determined later depending
    on WHICH folder the file is in, not the file extension.

    Code and scripts will be disregarded for now.
    """
    return file_path.suffix.lower() in SUPPORTED_SUFFIXES


# 2) Generator, streamar mina sökvägar en i taget.
# Funktion för att gå igenom mina filer
def walk_source_files(repos_root: Path) -> Iterator[Path]:
    """
    A generator, 'yield' instead of 'return' + a list.
    Goes through all files recursively (rglob),
    uses 'yield' to save RAM.

    This generator yields one file at a time, keeping nothing in memory other than its current position in the process.
    It applies the same 'stream, dont load everything concept as compute_file_hash below,
    but at the file level rather than the byte level, which becomes relevant the day repos_for_data grows in size.

    The .git exclusion uses the exact same logic already demonstrated in counting_script.py reused, not reinvented.
    """
    for path in repos_root.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        if not is_supported_file(path):
            continue
        yield path


# 3) Dataklass, en strikt "behållare" för min METADATA (Fakta om filerna) enbart genom att titta på filens adress
# Decorator för dataclass funktion
@dataclass
class DiscoveredFile:
    """
    Everything I know about a file before it is hashed or uploaded.
    (A files metadata)

    A data class instead of a tuple, field names are explicit, so there is
    no risk of mixing up the order of, say, course_tag and source_type later in the code.

    Deliberately not a Pydantic model here:
    Pydantic validates data coming from OUTSIDE (like .env in config.py)
    this is data that I have already calculated from trusted dictionaries
    so there is no reason to validate it again.

    This is what the file 'transforms into' before being sent to the database.
    Much safer than a dictionary, since Python knows exactly which fields exist.
    """

    local_path: Path  # Lokala pathen på min dator
    filename: str  # Filnamnet
    s3_key: str  # Min S3 KEY
    course_tag: str  # Document.course_tag, SEMANTIK, vad filen HANDLAR OM
    source_type: str  # "pdf" | "markdown" | "transcript"


# 4) Metadata byggaren. Härled allt från sökvägen
# Skapar all metadata ENBART baserat på filens namn och folder.
# Funktionen öppnar ALDRIG själva filen häftigt nog.
def build_file_record(file_path: Path, repos_root: Path) -> DiscoveredFile:
    """
    Derives everything that CAN BE DERIVED FROM THE PATH ALONE.
    No disk I/O involving file content, just the path structure.

    A "cheap" and easy way to test in isolation (a dummy path suffices no real files are needed).

    NOTE: get_course_tag/get_transcript_course_tag may raise a KeyError here.
    It is NOT caught in this function, nor should it be caught in a broad
    try/except block around an individual file, an unknown repo name should
    stop the ENTIRE run, not be silently skipped.
    """

    # Räknar ut vart jag är (t.ex python_course/01_course_structure/README.md)
    relative_to_root = file_path.relative_to(repos_root)
    repo_name = relative_to_root.parts[0]
    relative_within_repo = file_path.relative_to(repos_root / repo_name)

    # Slår upp kursens tag via min explicita mapping (course_mapping.py)
    # Failar HÖGT om den INTE finns.
    s3_course_segment = get_course_tag(repo_name)

    # Specialhantering för just YT-transcripts semantiska tag
    # Finkornig, semantiskt korrekt tag PER fil.
    if repo_name == "youtube_transcripts":
        course_tag = get_transcript_course_tag(file_path.name)
        source_type = "transcript"
    else:
        course_tag = s3_course_segment
        source_type = "pdf" if file_path.suffix.lower() == ".pdf" else "markdown"

    # Bygg S3-key. as_posix() skyddar mot windows issues med backslashes (\)
    s3_key = f"{s3_course_segment}/{repo_name}/{relative_within_repo.as_posix()}"

    # Returnerar min data class
    return DiscoveredFile(
        local_path=file_path,
        filename=file_path.name,
        s3_key=s3_key,
        course_tag=course_tag,
        source_type=source_type,
    )


# 5) HASH FUNKTION.
# Läser varje fil i bits om 8kb för att spara på RAM och skapar mitt "fingeravtryck" för varje fil.
# Skapar unik SHA-256bit hash. Innehållet blir filens identitet
def compute_file_hash(file_path: Path) -> str:
    """
    SHA-256 hash of files CONTENT (Not the filename or filepath).

    Function reads the file in 8192 byte chunks rather than loading the
    ENTIRE file into memory using .read_bytes(). This makes no
    noticeable difference for small .md files but would
    matter significantly if a PDF were 500 MB. A RAM cost I dont want
    for something as simple as a fingerprint.

    Does NOT catch errors here, exceptions like PermissionError are allowed to propagate by design
    the one using this function decides how to handle a read error,
    not the function itself, which is intended solely for hashing.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# 6) Funktion för att göra query mot postgres DB, använder python set
# för att optimera för HASTIGHET. En fråga mot postgres,
# HELA file_hash column till ett set. Undviker N+1
def load_existing_hashes(session: Session) -> set[str]:
    """
    Function to query Postgres,
    instead of querying the database 100 times, function execute a single SQL query:
    SELECT file_hash FROM documents.

    All the results are stored in a Python set to increase speed when searching.
    """
    result = session.execute(select(Document.file_hash))
    return set(result.scalars().all())


# 7) Funktion för att ingesta EN fil i taget
# True = en ny rad skriven. False = hoppas över pga 3 orsaker som står kommenterade i koden
def ingest_one_file(
    record: DiscoveredFile,
    existing_hashes: set[str],
    s3_client,
    bucket_name: str,
    session: Session,
) -> bool:
    """
    Attempting to ingest ONE file.
    True = new line written.
    False = Skipped for 1 of 3 reasons.

    1: File cannot be read
    2: Transient network error with S3
    3: Same s3_key DIFFERENT hash.
    """
    # === FELTYP 1: Lokalt LÄSFEL ===
    try:
        file_hash = compute_file_hash(record.local_path)
    except OSError as e:
        print(f"[SKIPPING] could not read: {record.local_path}: {e}")
        return False  # Avbryt för DENNA fil, returnera False (misslyckades)

    # === Deduplication . FÖRE någon nätverks/disk(I/O) operation ===
    if file_hash in existing_hashes:
        return False  # Fil finns redan i DB, hoppa över i tystnad

    # === FELTYP 2: Nätverkfel mot S3 ===
    # Transient network error mot S3
    try:
        upload_file(s3_client, str(record.local_path), bucket_name, record.s3_key)
    except ClientError as e:
        print(f"[SKIPPING] S3-upload failed because: {record.s3_key}: {e}")
        return False  # S3 nere, avbryt. Postgres raden skapas INTE, den försöker nästa igen nästa run.

    # === DATABAS: Förbereder för att spara METADATAN ===
    document = Document(
        s3_key=record.s3_key,
        filename=record.filename,
        source_type=record.source_type,
        course_tag=record.course_tag,
        file_hash=file_hash,
        status=DocumentStatus.PENDING,  # Framtida Airflow + PyMuPDF vet nu att PENDING väntar på extraction.
    )
    session.add(document)  # lägger till temporärt i minne

    # === FELTYP 3: Innehållskonflikt (Fail Loud) ===
    # Samma s3_key men ANNAN hash som innebär att en "gammal" sökväg har fått nytt innehåll. Det SKA faila HÖGT.
    try:
        session.commit()
    except IntegrityError:
        session.rollback()  # Sessionen är oanvändbar tills rollback() har körts. Rensar temporärt minne för att undvika DB låsning
        # Stopp. 'from None' klipper bort en rörig SQLAlchemy log och visar bara felet.
        raise RuntimeError(
            f"s3_key '{record.s3_key}' already exists in Postgres with a DIFFERENT "
            f"hash then what was just calculated. Same Path, changed content - "
            f"Requires a manual decision, not an automated solution!"
        ) from None

    # === Uppdaterar minnet DIREKT ===
    # Om samma fil hittas IGEN i körningen måste systemet veta om det
    existing_hashes.add(file_hash)
    return True  # Filen laddades upp och loggades


# 8) Funktion för orkestrering som sätter upp mina anslutningar och kör igenom varje fil.
def run_ingestion() -> None:
    """
    This function only sets up the connections to start all loops
    under settings.COURSE_REPOS_ROOT and prints a summary.
    """
    # Startar uppkopplingar
    engine = create_engine(settings.database_url)
    s3_client = get_s3_client()
    # Fail LOUD: Krasch om LocalStack är dött
    ensure_bucket_exists(s3_client, settings.S3_BUCKET_NAME)

    # Counter av ingested och skippade
    ingested_count = 0
    skipped_count = 0

    # Öppnar en DB session (stängs per automatik när blocket är klart)
    with Session(engine) as session:
        # Hämtar hashes EN gång(Löser N+1 issues)
        existing_hashes = load_existing_hashes(session)

        # Hämtar en fil i taget från generatorn (Streamar)
        for file_path in walk_source_files(settings.COURSE_REPOS_ROOT):
            # Bygger min metadata (Ren python funktion)
            record = build_file_record(file_path, settings.COURSE_REPOS_ROOT)
            # Försöker ladda upp och logga
            was_ingested = ingest_one_file(
                record, existing_hashes, s3_client, settings.S3_BUCKET_NAME, session
            )
            # räknar ut resultat för min summering
            if was_ingested:
                ingested_count += 1
            else:
                skipped_count += 1
    print(f"Done. {ingested_count} new files ingested, {skipped_count} skipped files.")


# === ENTRYPOINT ===
if __name__ == "__main__":
    run_ingestion()
