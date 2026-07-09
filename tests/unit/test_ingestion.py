# test_ingestion.py script - Unit tester för ingest.py, botten av test pyramiden
# Kod: Engelska
# Kommentarer: Svenska

# Testerna är uppdelade i två delar
#
# Del 1: Rena funktioner + lokalt I/O filsystem (INGEN S3 INGEN POSTGRES, meningen är att det ska gå FORT)
# Testar: is_supported_file, walk_source_files, build_file_record, compute_file_hash funktionerna
#
# Del 2: Rena funktioner som testar: load_existing_hashes, ingest_one_file. Kommer räva SQLite + MagicMock deps


from pathlib import Path
import hashlib
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from kms.db.models import Base, Document, DocumentStatus
from kms.ingestion.ingest import (
    DiscoveredFile,
    build_file_record,
    compute_file_hash,
    ingest_one_file,
    is_supported_file,
    load_existing_hashes,
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
# ===== load_existing_hashes =====
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

    # ENBART document tabellen. Sqlite krockar med JSONB som är postgres specifik.
    # SQLite vet inte hur jsonb ska renderas. SQLite kraschar om HELA base.metadata byggs.
    # Fixen: isolera och bygg enbart det som behövs för testet med tables=[Document.__table__]
    Base.metadata.create_all(engine, tables=[Document.__table__])

    with Session(engine) as session:
        yield session  # testet körs här

    engine.dispose()  # körs även om testet failar (teardown)


# test för att ladda hashes
def test_load_existing_hashes_empty_db(session):
    assert load_existing_hashes(session) == set()


def test_load_existing_hashes_returns_all_hashes(session):
    session.add_all(
        [
            Document(
                s3_key="python/python_course/a.md",
                filename="a.md",
                source_type="markdown",
                course_tag="python",
                file_hash="hash_a",
            ),
            Document(
                s3_key="python/python_course/b.md",
                filename="B.md",
                source_type="markdown",
                course_tag="python",
                file_hash="hash_b",
            ),
        ]
    )
    session.commit()

    assert load_existing_hashes(session) == {"hash_a", "hash_b"}


# ========== DEL 2B ==========
# 6x scenarior, MagicMock ersätter min S3 client
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
def _make_record(tmp_path, filename="notes.md", content="content", s3_key=None):
    """
    Not a Fixture.
    Only built around set parameters,
    NO setup or teardown needed for this.
    Only a normal function will suffice.
    """
    file_path = tmp_path / filename
    file_path.write_text(content, encoding="utf-8")
    return DiscoveredFile(
        local_path=file_path,
        filename=filename,
        s3_key=s3_key or f"python/python_course/{filename}",
        course_tag="python",
        source_type="markdown",
    )


# Funktion för att testa happy path (Den ideala, error fria pathen)
# Definition: the ideal workflow where everything works perfectly
def test_happy_path(tmp_path, session, s3_client):
    record = _make_record(tmp_path)

    result = ingest_one_file(record, set(), s3_client, "test-bucket", session)

    assert result is True
    s3_client.upload_file.assert_called_once()
    saved = session.execute(select(Document)).scalar_one()
    assert saved.s3_key == record.s3_key
    assert saved.status == DocumentStatus.PENDING


# Test för deduplication
def test_dedup_skips_before_any_io(tmp_path, session, s3_client):
    content = "known content"
    record = _make_record(tmp_path, content=content)
    existing_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    result = ingest_one_file(record, {existing_hash}, s3_client, "test-bucket", session)

    assert result is False
    s3_client.upload_file.assert_not_called()  # Aldrig ens försökt, INTE BARA "FEL RESULTAT"
    assert session.execute(select(Document)).first() is None


# test för oläsbara filer som skippas pga pathing issues eller andra issues
def test_unreadable_file_skips(tmp_path, session, s3_client):
    missing_path = tmp_path / "finns_inte.md"
    record = DiscoveredFile(
        local_path=missing_path,
        filename="finns_inte.md",
        s3_key="python/python_course/finns_inte.md",
        course_tag="python",
        source_type="markdown",
    )

    result = ingest_one_file(record, set(), s3_client, "test-bucket", session)

    assert result is False
    s3_client.upload_file.assert_not_called()


# Testar för att upload failure ska skippas
def test_s3_upload_failure_skips(tmp_path, session, s3_client):
    record = _make_record(tmp_path)
    s3_client.upload_file.side_effect = ClientError(
        error_response={"Error": {"Code": "500", "Message": "simulerat"}},
        operation_name="upload_file",
    )

    result = ingest_one_file(record, set(), s3_client, "test-bucket", session)

    assert result is False
    assert session.execute(select(Document)).first() is None


# Test för IntegrityError på existerande dokument på samma s3_key och en insert med SAMMA
# s3_key händer men med annan HASH. Det är anledningen till varför rollback() finns.
# rollback() ska ha städat sessionen så den fortfarande går att använda för nästa fil.
def test_integrity_error_crashes_and_session_still_usable(tmp_path, session, s3_client):
    # Sar ett existerande dokument pa samma s3_key - nasta insert med SAMMA
    # key men ANNAN hash ar precis scenariot IntegrityError-grenen finns for.
    existing = Document(
        s3_key="python/python_course/notes.md",
        filename="notes.md",
        source_type="markdown",
        course_tag="python",
        file_hash="old_hash_placeholder",
    )
    session.add(existing)
    session.commit()

    record = _make_record(tmp_path, content="helt nytt innehall")

    with pytest.raises(RuntimeError):
        ingest_one_file(record, set(), s3_client, "test-bucket", session)

    fresh = Document(
        s3_key="python/python_course/annan_fil.md",
        filename="annan_fil.md",
        source_type="markdown",
        course_tag="python",
        file_hash="ny_hash",
    )
    session.add(fresh)
    session.commit()
    assert "ny_hash" in session.execute(select(Document.file_hash)).scalars().all()


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
        ingest_one_file(record, set(), s3_client, "test-bucket", session)
