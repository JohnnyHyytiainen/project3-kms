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
import enum
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from collections import Counter

# Boto3
from botocore.exceptions import ClientError

# SQLAlchemy - ORM
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Import av mina dictionary mappings repots funktioner
from kms.config import settings
from kms.db.models import Course, Document, DocumentStatus, SourceFile
from kms.ingestion.course_mapping import (
    get_course_tag,
    get_mirror_course_tag,
    get_transcript_course_tag,
)
from kms.storage.s3_client import ensure_bucket_exists, get_s3_client, upload_file

# 1a) Filtret, Endast dom här filerna
# Endast dom här filerna är välkommna i mitt data lakehouse JUST NU
# sub-foldern i youtube_transcripts/ där mina transcripts ligger sorterade PER KURS
SUPPORTED_SUFFIXES = {".pdf", ".md"}
MIRROR_TRANSCRIPTS_DIR = "COMPLETE_COURSE_TRANSCRIPTS"


# 1b) Utfallet för EN fil i EN körning. Samma mönster som ExtractionOutcome i extract.py
class IngestOutcome(str, enum.Enum):
    """
    Result of processing ONE file in ONE run.

    NEW_DOCUMENT: content thats never been seen before, uploaded to S3, new row in documents.
    NEW_COPY: Known content found at a new place, new row in source_files ONLY.
    SKIPPED: Nothing written, unreadable file, S3 error or already registered.
    """

    NEW_DOCUMENT = "new_document"
    NEW_COPY = "new_copy"
    SKIPPED = "skipped"


# 1c) Funktionen för filrtet
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
    course_tag: str  # Kursen för DETTA exemplar, blir en rad i courses via source_files
    source_type: str  # "pdf" | "markdown" | "transcript"
    source_path: str  # {repo}/{sökväg i repot}, exemplarets unika plats på disk


# 4) Metadata byggaren. Härled allt från sökvägen
# Skapar all metadata ENBART baserat på filens namn och folder.
# Funktionen öppnar ALDRIG själva filen häftigt nog.
def build_file_record(file_path: Path, repos_root: Path) -> DiscoveredFile:
    """
    Derives everything that CAN BE DERIVED FROM THE PATH ALONE.
    No disk I/O involving file content, just the path structure.

    A "cheap" and easy way to test in isolation (a dummy path suffices no real files are needed).

    NOTE: get_course_tag/get_mirror_course_tag/get_transcript_course_tag may
    raise a KeyError here.
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
        # Spegelmappar: COMPLETE_COURSE_TRANSCRIPTS/repo_done/lektion/fil.md
        # parts[1] är undermappen, parts[2] är spegelmappen som bär kursen
        if relative_to_root.parts[1] == MIRROR_TRANSCRIPTS_DIR:
            course_tag = get_mirror_course_tag(relative_to_root.parts[2])
        else:
            # Platta transcripts/: filnamnet är enda nyckeln (53 rader i dicten)
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
        source_path=relative_to_root.as_posix(),
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


# 6a) Minnet, tre uppslagningar som hämtas EN gång per körning (undviker N+1 problem)
def load_known_documents(session: Session) -> dict[str, int]:
    """
    ONE query: file_hash -> document_id for every document in Postgres.
    A dict instead of a set, a new copy of known content must know WHICH document to point at.
    """
    result = session.execute(select(Document.file_hash, Document.id))
    return {file_hash: document_id for file_hash, document_id in result.all()}


def load_known_paths(session: Session) -> dict[str, int]:
    """
    ONE query: source_path -> document_id for every file already registered.
    Recognizes a file from an earlier run, and catches a path whose content has changed.
    """
    result = session.execute(select(SourceFile.source_path, SourceFile.document_id))
    return {source_path: document_id for source_path, document_id in result.all()}


def load_course_ids(session: Session) -> dict[str, int]:
    """ONE query: course_tag -> course_id for every course in Postgres."""
    result = session.execute(select(Course.course_tag, Course.id))
    return {course_tag: course_id for course_tag, course_id in result.all()}


def get_or_create_course_id(
    course_tag: str, course_ids: dict[str, int], session: Session
) -> int:
    """
    Returns the course id, creates the course row the first time the tag is seen.
    flush() sends the INSERT so Postgres hands out the id, WITHOUT committing.
    The course gets committed together with the file row that needed it.
    """
    # Redan känd, ingen fråga mot databasen alls
    if course_tag in course_ids:
        return course_ids[course_tag]

    # Första gången taggen dyker upp i körningen
    course = Course(course_tag=course_tag)
    session.add(course)
    session.flush()  # INSERT skickas, id finns nu, ingen commit än

    # Uppdatera minnet direkt, nästa fil i samma kurs slipper frågan
    course_ids[course_tag] = course.id
    return course.id


# 6b) Commit med skyddsnät
def commit_or_raise(session: Session, record: DiscoveredFile) -> None:
    """
    Commits, and turns an IntegrityError into a loud stop.
    The explicit checks in ingest_one_file should make this unreachable,
    the UNIQUE rules in Postgres are the safety net if they ever miss.
    """
    try:
        session.commit()
    except IntegrityError:
        session.rollback()  # Sessionen är oanvändbar tills rollback() körts
        raise RuntimeError(
            f"Postgres refused '{record.source_path}', a UNIQUE rule was broken "
            f"that the checks in ingest_one_file did not catch. Stop and investigate!"
        ) from None


# 7) Funktion för att ingesta EN fil i taget
# Tre utfall: nytt dokument, nytt exemplar av känt innehåll, eller överhoppad
def ingest_one_file(
    record: DiscoveredFile,
    known_documents: dict[str, int],
    known_paths: dict[str, int],
    course_ids: dict[str, int],
    s3_client,
    bucket_name: str,
    session: Session,
) -> IngestOutcome:
    """
    Attempting to ingest ONE file.

    NEW_DOCUMENT: new content, uploaded to S3, new row in documents AND source_files.
    NEW_COPY: known content at a new path, new row in source_files only.
    SKIPPED: unreadable file, S3 error, or path already registered with same content.

    Raises RuntimeError when a registered path has gotten NEW content.
    Checked BEFORE any upload, so S3 and Postgres can never drift apart.
    """
    # === FELTYP 1: Lokalt LÄSFEL ===
    try:
        file_hash = compute_file_hash(record.local_path)
    except OSError as e:
        print(f"[SKIPPING] could not read: {record.local_path}: {e}")
        return IngestOutcome.SKIPPED

    # === Sökvägen redan registrerad? FÖRE all nätverks-I/O ===
    if record.source_path in known_paths:
        # Samma innehåll som förra körningen, redan registrerad, inget att göra
        if known_documents.get(file_hash) == known_paths[record.source_path]:
            return IngestOutcome.SKIPPED
        # === FELTYP 3: Innehållskonflikt (Fail Loud) ===
        # Samma sökväg, NYTT innehåll. Upptäcks nu FÖRE uppladdning till S3
        raise RuntimeError(
            f"source_path '{record.source_path}' is already registered with DIFFERENT "
            f"content than what was just calculated. Same path, changed content - "
            f"Requires a manual decision, not an automated solution!"
        )

    # === Känt innehåll på en NY plats = nytt exemplar ===
    # Ingen uppladdning, innehållet ligger redan i S3 exakt en gång
    if file_hash in known_documents:
        document_id = known_documents[file_hash]
        course_id = get_or_create_course_id(record.course_tag, course_ids, session)
        session.add(
            SourceFile(
                document_id=document_id,
                course_id=course_id,
                source_path=record.source_path,
            )
        )
        commit_or_raise(session, record)

        # Uppdaterar minnet DIREKT
        known_paths[record.source_path] = document_id
        return IngestOutcome.NEW_COPY

    # === FELTYP 2: Nätverksfel mot S3 ===
    try:
        upload_file(s3_client, str(record.local_path), bucket_name, record.s3_key)
    except ClientError as e:
        print(f"[SKIPPING] S3-upload failed because: {record.s3_key}: {e}")
        return IngestOutcome.SKIPPED  # Inget skrivs, nästa körning försöker igen

    # === DATABAS: nytt innehåll = ny rad i documents + dess första exemplar ===
    # Kursen hämtas EFTER uppladdningen, misslyckas S3 skapas ingen kurs i onödan
    course_id = get_or_create_course_id(record.course_tag, course_ids, session)
    document = Document(
        s3_key=record.s3_key,
        filename=record.filename,
        source_type=record.source_type,
        file_hash=file_hash,
        status=DocumentStatus.PENDING,  # Extraktionen plockar upp PENDING
    )
    # Exemplaret läggs till via relationen, SQLAlchemy fyller i document_id vid INSERT
    document.source_files.append(
        SourceFile(course_id=course_id, source_path=record.source_path)
    )
    session.add(document)
    commit_or_raise(session, record)

    # Uppdaterar minnet DIREKT, en kopia senare i SAMMA körning måste hitta hit
    known_documents[file_hash] = document.id
    known_paths[record.source_path] = document.id
    return IngestOutcome.NEW_DOCUMENT


# 8) Funktion för orkestrering som sätter upp mina anslutningar och kör igenom varje fil.
def run_ingestion() -> None:
    """
    Sets up the connections, loads what Postgres already knows ONCE,
    runs every file under settings.COURSE_REPOS_ROOT and prints a summary.
    """
    # Startar uppkopplingar
    engine = create_engine(settings.database_url)
    s3_client = get_s3_client()
    # Fail LOUD: Krasch om LocalStack är dött
    ensure_bucket_exists(s3_client, settings.S3_BUCKET_NAME)

    # En räknare per utfall. Counter ger 0 för ett utfall som aldrig inträffat
    outcomes: Counter[IngestOutcome] = Counter()

    # Öppnar en DB session (stängs per automatik när blocket är klart)
    with Session(engine) as session:
        # Minnet hämtas EN gång, tre frågor totalt oavsett antal filer (löser N+1)
        known_documents = load_known_documents(session)
        known_paths = load_known_paths(session)
        course_ids = load_course_ids(session)

        # Hämtar en fil i taget från generatorn (Streamar)
        for file_path in walk_source_files(settings.COURSE_REPOS_ROOT):
            record = build_file_record(file_path, settings.COURSE_REPOS_ROOT)
            outcome = ingest_one_file(
                record,
                known_documents,
                known_paths,
                course_ids,
                s3_client,
                settings.S3_BUCKET_NAME,
                session,
            )
            outcomes[outcome] += 1

    print(
        f"Done. {outcomes[IngestOutcome.NEW_DOCUMENT]} new documents, "
        f"{outcomes[IngestOutcome.NEW_COPY]} new copies, "
        f"{outcomes[IngestOutcome.SKIPPED]} skipped."
    )


# === ENTRYPOINT ===
if __name__ == "__main__":
    run_ingestion()
