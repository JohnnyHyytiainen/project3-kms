# test_ingestion.py script - Unit tester för ingest.py, botten av test pyramiden
# Kod: Engelska
# Kommentarer: Svenska

# Testerna är uppdelade i två delar
#
# Del 1: Rena funktioner + lokalt I/O filsystem (INGEN S3 INGEN POSTGRES, meningen är att det ska gå FORT)
# Testar: is_supported_file, walk_source_files, build_file_record, compute_file_hash funktionerna
#
# Del 2: Minnet (load_known_documents, get_or_create_course_id) och ingest_one_file. SQLite + MagicMock


from pathlib import Path
import hashlib
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from kms.db.models import Base, Course, Document, DocumentStatus, SourceFile
from kms.ingestion.ingest import (
    DiscoveredFile,
    IngestOutcome,
    build_file_record,
    compute_file_hash,
    get_or_create_course_id,
    ingest_one_file,
    is_supported_file,
    load_known_documents,
    walk_source_files,
)


#
# ===== is_supported_file =====
# Testar för supported filtyper, endast pdf och markdown än så länge
def test_is_supported_file_accepts_pdf_and_markdown():
    assert is_supported_file(Path("slides_WoRtH-testing.pdf")) is True
    assert is_supported_file(Path("testing_testing.md")) is True


# Testar mina rejected filtyper tills jag kommer dit i roadmap
def test_is_supported_file_rejects_everything_else():
    assert is_supported_file(Path("scripts.py")) is False
    assert is_supported_file(Path("queries.sql")) is False
    assert is_supported_file(Path("notebooks.ipynb")) is False


# En fil med CAPS ska fortfarande matcha tack vare .suffix.lower()
def test_is_supported_file_is_case_insensitive():
    assert is_supported_file(Path("SLIDES.PDF")) is True


# ===== walk_source_files =====
# tmp_path är inbyggd fixture i pytest. En riktig tom temp folder per test städas automatiskt bort efter
# Ingen mock folder behövs. Filsystemet ÄR den riktiga infrastrukturen bara i en engångsmapp ist för data foldern.


# Test för enbart hittade supported filtyper
def test_walk_source_files_finds_only_supported_types(tmp_path):
    (tmp_path / "notes.md").write_text("innehåll")  # Ska hittas
    (tmp_path / "slides.pdf").write_text("innehåll")  # Ska hittas
    (tmp_path / "python.py").write_text("innehåll")  # SKA INTE HITTAS

    found = {p.name for p in walk_source_files(tmp_path)}

    assert found == {"notes.md", "slides.pdf"}


# Test för att den aldrig hittar .git filer.
def test_walk_source_files_skips_git_directory(tmp_path):
    (tmp_path / "real_file.md").write_text("innehåll")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config.md").write_text("ska aldrig hittas")

    found = {p.name for p in walk_source_files(tmp_path)}

    assert found == {"real_file.md"}


# Test för att att säkerställa att walk_source_files har "mapp i mapp" förståelse(Djupgående genomsökning)
# Dvs, den är recursive och kan gå djupare i folders med sub-folders
def test_walk_source_files_is_recursive(tmp_path):
    nested = tmp_path / "repo_a" / "lektion_1"
    nested.mkdir(parents=True)
    (nested / "deep.md").write_text("innehåll")

    found = list(walk_source_files(tmp_path))

    assert len(found) == 1
    assert found[0].name == "deep.md"


# ===== build_file_record =====
# Tester på riktiga värden från REPO_TO_COURSE_TAG och TRANSCRIPT_TO_COURSE_TAG
# Testerna verifierar mot samma data som den riktiga koden.


# Test för att verifiera att course tag och source typ + s3_key stämmer med verkligheten
def test_build_file_record_for_normal_repo_markdown(tmp_path):
    repo = tmp_path / "python_course"
    repo.mkdir()
    file_path = repo / "intro.md"
    file_path.write_text("innehåll")

    record = build_file_record(file_path, tmp_path)

    assert record.course_tag == "python"
    assert record.source_type == "markdown"
    assert record.s3_key == "python/python_course/intro.md"
    assert record.source_path == "python_course/intro.md"


# Samma som ovan fast för source_type pdf istället för .md
def test_build_file_record_for_pdf(tmp_path):
    repo = tmp_path / "data_modeling_course"
    repo.mkdir()
    file_path = repo / "slides.pdf"
    file_path.write_text("innehåll")

    record = build_file_record(file_path, tmp_path)

    assert record.source_type == "pdf"


# test för att transcript_course_tag fungerar som den ska för dom SÄKRA träffarna.
# "python intro.md" ska bli "python" i TRANSCRIPT_TO_COURSE_TAG
def test_build_file_record_for_youtube_transcript(tmp_path):
    repo = tmp_path / "youtube_transcripts"
    repo.mkdir()
    file_path = repo / "python intro.md"
    file_path.write_text("innehåll")

    record = build_file_record(file_path, tmp_path)

    assert record.source_type == "transcript"
    assert record.course_tag == "python"
    # reproducerar den dokumenterad DUBBEL s3-key från ingest_Script_mvp_v1.md
    # TODO: se över detta när jag är längre fram i projektet
    assert record.s3_key == "youtube_transcripts/youtube_transcripts/python intro.md"


# test för att se så att spelningen av mirror_transcripts fungerar som tänkt.
# Filnamnet ska inte finnas i TRANSCRIPT_TO_COURSE_TAG.
def test_build_file_record_for_mirror_transcript(tmp_path):
    mirror = tmp_path / "youtube_transcripts" / "COMPLETE_COURSE_TRANSCRIPTS"
    lesson = mirror / "python_course_DONE" / "17_pydantic"
    lesson.mkdir(parents=True)
    file_path = lesson / "17_part_1_pydantic.md"
    file_path.write_text("innehåll")

    record = build_file_record(file_path, tmp_path)

    assert record.source_type == "transcript"
    assert record.course_tag == "python"
    # S3-nyckeln ska vara OFÖRÄNDRAD, den bär fortfarande VAR filen ligger
    expected_key = (
        "youtube_transcripts/youtube_transcripts/COMPLETE_COURSE_TRANSCRIPTS/"
        "python_course_DONE/17_pydantic/17_part_1_pydantic.md"
    )
    assert record.s3_key == expected_key

    # source_path saknar kurssegmentet, den är filens plats på disk, inget annat
    assert record.source_path == (
        "youtube_transcripts/COMPLETE_COURSE_TRANSCRIPTS/"
        "python_course_DONE/17_pydantic/17_part_1_pydantic.md"
    )


# Test för att en OKÄND mirror folder som SKA faila HÖGT och FORT.
def test_build_file_record_raises_on_unknown_mirror_folder(tmp_path):
    mirror = tmp_path / "youtube_transcripts" / "COMPLETE_COURSE_TRANSCRIPTS"
    lesson = mirror / "helt_unknown_course_DONE" / "01_intro"
    lesson.mkdir(parents=True)
    file_path = lesson / "01_part_1_intro.md"
    file_path.write_text("innehåll")

    with pytest.raises(KeyError):
        build_file_record(file_path, tmp_path)


# Funktion för att FAILA LOUD ifall ett okänt repo namn upptäcks.
def test_build_file_record_raises_on_unknown_repo(tmp_path):
    repo = tmp_path / "helt_unknown_repo"
    repo.mkdir()
    file_path = repo / "notes.md"
    file_path.write_text("innehåll")

    with pytest.raises(KeyError):
        build_file_record(file_path, tmp_path)


# ===== compute_file_hash =====
# Tester för att kolla hashing logiken
# utf-8 encoding EXPLICIT för att write_text() inte ska bero på lokalt OS.
# Samma windows-Linux problem som .as_posix() redan löser för S3-keys
def test_compute_file_hash_matches_manual_sha256(tmp_path):
    file_path = tmp_path / "known.md"
    content = "known content for hash tests"
    file_path.write_text(content, encoding="utf-8")

    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()

    assert compute_file_hash(file_path) == expected


# OSError ska spridas vidare, funktionen fångar det INTE av design
def test_compute_file_hash_raises_when_file_missing(tmp_path):
    missing = tmp_path / "finns_inte.md"

    with pytest.raises(OSError):
        compute_file_hash(missing)


# ========== DEL 2A ==========
#
# ===== Minnet: load_known_documents + get_or_create_course_id =====
# Stateful test, SQLite in-memory ersätter PostgreSQL databas


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


def test_load_known_documents_empty_db(session):
    assert load_known_documents(session) == {}


# Minnet ska peka hash -> id, inte bara veta ATT hashen finns
def test_load_known_documents_maps_hash_to_id(session):
    doc_a = Document(
        s3_key="python/python_course/a.md",
        filename="a.md",
        source_type="markdown",
        file_hash="hash_a",
    )
    doc_b = Document(
        s3_key="python/python_course/b.md",
        filename="b.md",
        source_type="markdown",
        file_hash="hash_b",
    )
    session.add_all([doc_a, doc_b])
    session.commit()

    assert load_known_documents(session) == {"hash_a": doc_a.id, "hash_b": doc_b.id}


# Samma tagg två gånger = EN rad i courses. Andra anropet frågar inte ens databasen
def test_get_or_create_course_id_creates_once(session):
    course_ids: dict[str, int] = {}

    first = get_or_create_course_id("python", course_ids, session)
    second = get_or_create_course_id("python", course_ids, session)

    assert first == second
    assert course_ids == {"python": first}
    assert len(session.execute(select(Course)).scalars().all()) == 1


# ========== DEL 2B ==========
# 8x scenarior, MagicMock ersätter min S3 client
#
# ===== ingest_one_file =====


@pytest.fixture
def s3_client():
    """
    Standard mock will 'succeed' automatically on
    ALL method/function calls for now.
    """
    return MagicMock()


# Privat funktion - FAAFO(F around and find out)
def _make_record(
    tmp_path, filename="notes.md", content="content", folder="python_course"
):
    """
    Not a Fixture.
    Only built around set parameters,
    NO setup or teardown needed for this.
    Only a normal function will suffice.

    folder decides WHERE the copy lives. Same content in two folders = two copies.
    """
    directory = tmp_path / folder
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / filename
    file_path.write_text(content, encoding="utf-8")
    return DiscoveredFile(
        local_path=file_path,
        filename=filename,
        s3_key=f"python/{folder}/{filename}",
        course_tag="python",
        source_type="markdown",
        source_path=f"{folder}/{filename}",
    )


# Privat funktion - anropar ingest_one_file med TOMT minne om testet inte skickar eget
def _ingest(
    record,
    session,
    s3_client,
    known_documents=None,
    known_paths=None,
    course_ids=None,
):
    """
    Calls ingest_one_file with EMPTY memory unless the test passes its own.

    'is None' and NOT 'or {}': an empty dict is falsy, 'or' would swap the
    test's own dict for a new one and the test could never see what got written to it.
    """
    return ingest_one_file(
        record,
        {} if known_documents is None else known_documents,
        {} if known_paths is None else known_paths,
        {} if course_ids is None else course_ids,
        s3_client,
        "test-bucket",
        session,
    )


# Happy path: nytt innehåll = uppladdning + documents + source_files + courses
def test_happy_path(tmp_path, session, s3_client):
    record = _make_record(tmp_path)
    known_documents: dict[str, int] = {}
    known_paths: dict[str, int] = {}

    result = _ingest(record, session, s3_client, known_documents, known_paths)

    assert result == IngestOutcome.NEW_DOCUMENT
    s3_client.upload_file.assert_called_once()
    saved = session.execute(select(Document)).scalar_one()
    assert saved.s3_key == record.s3_key
    assert saved.status == DocumentStatus.PENDING
    copy = session.execute(select(SourceFile)).scalar_one()
    assert copy.document_id == saved.id
    assert copy.source_path == record.source_path
    assert copy.course.course_tag == "python"
    # Minnet uppdaterat DIREKT, en kopia senare i samma körning ska hitta hit
    assert known_documents == {saved.file_hash: saved.id}
    assert known_paths == {record.source_path: saved.id}


# Samma innehåll på två platser = ETT dokument, TVÅ exemplar.
# Samma fall som transkriptet i lektion 16 och 17 i databricks-kursen.
def test_known_content_at_new_path_becomes_copy(tmp_path, session, s3_client):
    known_documents: dict[str, int] = {}
    known_paths: dict[str, int] = {}
    course_ids: dict[str, int] = {}
    first = _make_record(tmp_path, content="shared lesson", folder="lesson_16")
    second = _make_record(tmp_path, content="shared lesson", folder="lesson_17")

    _ingest(first, session, s3_client, known_documents, known_paths, course_ids)
    result = _ingest(
        second, session, s3_client, known_documents, known_paths, course_ids
    )

    assert result == IngestOutcome.NEW_COPY
    s3_client.upload_file.assert_called_once()  # Innehållet laddas upp EN gång
    document = session.execute(select(Document)).scalar_one()
    copies = session.execute(select(SourceFile)).scalars().all()
    assert {c.source_path for c in copies} == {first.source_path, second.source_path}
    assert all(c.document_id == document.id for c in copies)


# Omkörning: sökvägen redan registrerad med SAMMA innehåll, ingenting skrivs
def test_already_registered_path_is_skipped(tmp_path, session, s3_client):
    known_documents: dict[str, int] = {}
    known_paths: dict[str, int] = {}
    record = _make_record(tmp_path)

    _ingest(record, session, s3_client, known_documents, known_paths)
    result = _ingest(record, session, s3_client, known_documents, known_paths)

    assert result == IngestOutcome.SKIPPED
    s3_client.upload_file.assert_called_once()
    assert len(session.execute(select(SourceFile)).scalars().all()) == 1


# Samma sökväg med NYTT innehåll ska faila HÖGT, och FÖRE uppladdningen.
# upload_file anropad EN gång = bara originalet, den ändrade filen nådde aldrig S3
def test_changed_content_at_known_path_raises_before_upload(
    tmp_path, session, s3_client
):
    known_documents: dict[str, int] = {}
    known_paths: dict[str, int] = {}
    original = _make_record(tmp_path, content="version 1")
    _ingest(original, session, s3_client, known_documents, known_paths)

    changed = _make_record(tmp_path, content="version 2")  # Samma sökväg, nytt innehåll
    with pytest.raises(RuntimeError):
        _ingest(changed, session, s3_client, known_documents, known_paths)

    s3_client.upload_file.assert_called_once()


# Skyddsnätet: sökvägen finns i databasen men INTE i minnet (osynkat).
# Postgres UNIQUE fångar det, rollback() ska lämna sessionen användbar för nästa fil.
def test_integrity_error_crashes_and_session_still_usable(tmp_path, session, s3_client):
    existing = Document(
        s3_key="python/python_course/old.md",
        filename="old.md",
        source_type="markdown",
        file_hash="old_hash_placeholder",
    )
    course = Course(course_tag="python")
    session.add_all([existing, course])
    session.flush()
    session.add(
        SourceFile(
            document_id=existing.id,
            course_id=course.id,
            source_path="python_course/notes.md",
        )
    )
    session.commit()

    record = _make_record(tmp_path, content="helt nytt innehall")  # Samma source_path
    # Kursen FINNS i minnet, bara sökvägen saknas. Det är den luckan som testas
    with pytest.raises(RuntimeError):
        _ingest(record, session, s3_client, course_ids={"python": course.id})

    fresh = Document(
        s3_key="python/python_course/annan_fil.md",
        filename="annan_fil.md",
        source_type="markdown",
        file_hash="ny_hash",
    )
    session.add(fresh)
    session.commit()
    assert "ny_hash" in session.execute(select(Document.file_hash)).scalars().all()


# test för oläsbara filer som skippas pga pathing issues eller andra issues
def test_unreadable_file_skips(tmp_path, session, s3_client):
    missing_path = tmp_path / "finns_inte.md"
    record = DiscoveredFile(
        local_path=missing_path,
        filename="finns_inte.md",
        s3_key="python/python_course/finns_inte.md",
        course_tag="python",
        source_type="markdown",
        source_path="python_course/finns_inte.md",
    )

    result = _ingest(record, session, s3_client)

    assert result == IngestOutcome.SKIPPED
    s3_client.upload_file.assert_not_called()


# S3 nere: ingenting i Postgres, inte ens kursen (den hämtas EFTER uppladdningen)
def test_s3_upload_failure_skips(tmp_path, session, s3_client):
    record = _make_record(tmp_path)
    s3_client.upload_file.side_effect = ClientError(
        error_response={"Error": {"Code": "500", "Message": "simulerat"}},
        operation_name="upload_file",
    )

    result = _ingest(record, session, s3_client)

    assert result == IngestOutcome.SKIPPED
    assert session.execute(select(Document)).first() is None
    assert session.execute(select(Course)).first() is None


# test för känd brist. except IntegrityError fångar INTE
# OperationalError (siblings, inte parent/child). Test för att bevisa att gapet finns kvar.
# Ska faila av sig självt den dagen min kod fixar det.
def test_operational_error_is_not_caught(tmp_path, session, s3_client, monkeypatch):
    record = _make_record(tmp_path)

    def raise_operational_error(*args, **kwargs):
        raise OperationalError(
            "INSERT ..", {}, Exception("Connection lost - Simulated")
        )

    monkeypatch.setattr(session, "commit", raise_operational_error)

    with pytest.raises(OperationalError):
        _ingest(record, session, s3_client)
