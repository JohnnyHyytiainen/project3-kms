# Kod: Engelska
# Kommentarer: Svenska
# ====================
#
# Tester som är uppdelade i 2 delar.
#
# Del 1: Tester för build_sections_from_markdown() i extract.py
# A1: En sektion per rubrikblock, rubrikraden ligger INNE i sektionens text
# B1: Text före första rubriken blir en egen sektion utan rubrik
# C1: Radintervallen är 1-indexerade, inklusiva, utan hål och utan överlapp
# D1: Fil utan rubriker ger EN sektion, inte noll
# E1: Tom fil ger tom lista, vilket uppströms blir NO_TEXT_EXTRACTED
# F1: "#taggen" utan mellanslag är ingen rubrik
# G1: Regression - rubrikliknande rad inuti ett kodblock delar inte sektionen
#
# Del 2: vector_id och sidmått i extract.py
# A2: Samma file_hash + chunk_index ger samma ID, varje gång
# B2: Ny position eller nytt innehåll ger nytt ID
# C2: ID't är en namnbaserad UUID (version 5), inte slump
# D2: Sidmåtten räknar tomma och korta sidor, gränsen ligger på MIN_CHUNK_SIZE
# E2: En sida med bara blanksteg räknas som tom, inte kort
# F2: "Kort" betyder exakt "chunkern kastade den" - måtten och chunkern får inte glida isär
#
# Del 3: Failure paths(felvägarna) i extract_one_document(), filen läses nu från disk och ska kontrolleras mot file_hash
# A3: Filen saknas på DISK -> FAILED med SOURCE_MISSING och det är committat.
# B3: Filen har ändrats sen ingestion -> RuntimeError, dokumentet ska stå kvar med status PENDING
# C3: Filen GÅR inte att läsa (transient error) -> SKIPPED, dokumentet ska stå kvar med status PENDING

import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from kms.db.models import Course, Document, DocumentStatus, FailureReason, SourceFile
from kms.extraction.chunker import MIN_CHUNK_SIZE
from kms.extraction.chunker import chunk_document
from kms.extraction.chunker import Section
from kms.extraction.extract import build_sections_from_markdown
from kms.extraction.extract import make_vector_id, measure_pages
from kms.extraction.extract import ExtractionOutcome, extract_one_document


# ====== Del 1: Tester för build_sections_from_markdown() logik ======
# ====================================================================
#
def write_markdown(tmp_path: Path, text: str) -> Path:
    """
    Writes the test text to a real file and returns its path.

    build_sections_from_markdown() takes a Path and opens it itself, exactly like
    it does in extract.py after download_file() has fetched the object from bronze.
    tmp_path is pytests own temp directory, one per test, removed afterwards.
    """
    path = tmp_path / "doc.md"
    path.write_text(text, encoding="utf-8")
    return path


MARKDOWN_WITH_PREAMBLE = (
    "Intro line before any heading.\n"
    "\n"
    "# First heading\n"
    "Body of first.\n"
    "\n"
    "## Second heading\n"
    "Body of second.\n"
)


# A1:
def test_markdown_one_section_per_heading_block(tmp_path):
    sections = build_sections_from_markdown(
        write_markdown(tmp_path, MARKDOWN_WITH_PREAMBLE)
    )

    assert len(sections) == 3
    assert sections[1].text.startswith("# First heading")
    assert sections[2].text.startswith("## Second heading")
    # Rubriknivån följer inte med i metadatan, bara rubrikens text.
    assert [s.source_location["heading"] for s in sections] == [
        None,
        "First heading",
        "Second heading",
    ]


# B1:
def test_markdown_preamble_becomes_its_own_section(tmp_path):
    sections = build_sections_from_markdown(
        write_markdown(tmp_path, MARKDOWN_WITH_PREAMBLE)
    )

    assert sections[0].source_location["heading"] is None
    assert sections[0].source_location["line_start"] == 1
    assert "Intro line before any heading." in sections[0].text


# C1:
def test_markdown_line_ranges_are_contiguous_and_inclusive(tmp_path):
    sections = build_sections_from_markdown(
        write_markdown(tmp_path, MARKDOWN_WITH_PREAMBLE)
    )
    ranges = [
        (s.source_location["line_start"], s.source_location["line_end"])
        for s in sections
    ]

    assert ranges == [(1, 2), (3, 5), (6, 7)]
    # Nästa sektion börjar alltid exakt på raden efter den föregåendes slut.
    for (_, previous_end), (next_start, _) in zip(ranges, ranges[1:]):
        assert next_start == previous_end + 1


# D1:
def test_markdown_without_headings_returns_single_section(tmp_path):
    sections = build_sections_from_markdown(
        write_markdown(tmp_path, "Just a paragraph.\nAnd another line.\n")
    )

    assert len(sections) == 1
    assert sections[0].source_location == {
        "heading": None,
        "line_start": 1,
        "line_end": 2,
    }


# E1:
def test_markdown_empty_file_returns_empty_list(tmp_path):
    assert build_sections_from_markdown(write_markdown(tmp_path, "")) == []


# F1:
def test_markdown_hash_without_space_is_not_a_heading(tmp_path):
    text = "#hashtag is not a heading\n####### seven hashes is not either\nplain text\n"
    sections = build_sections_from_markdown(write_markdown(tmp_path, text))

    assert len(sections) == 1
    assert sections[0].source_location["heading"] is None


# G1:
def test_markdown_heading_inside_code_fence_does_not_split(tmp_path):
    text = (
        "# Setup\nRun this:\n\n```bash\n# install dependencies\nuv sync\n```\n\nDone.\n"
    )
    sections = build_sections_from_markdown(write_markdown(tmp_path, text))

    assert len(sections) == 1
    assert sections[0].source_location == {
        "heading": "Setup",
        "line_start": 1,
        "line_end": 9,
    }
    assert "# install dependencies" in sections[0].text


# ====== Del 2: Tester för vector_id och sidmått logik ======
# ====================================================================
#
# A2:
def test_vector_id_is_deterministic():
    assert make_vector_id("abc123", 0) == make_vector_id("abc123", 0)


# B2:
def test_vector_id_changes_with_position_or_content():
    base = make_vector_id("abc123", 0)
    assert make_vector_id("abc123", 1) != base  # Samma innehåll, ny position
    assert make_vector_id("def456", 0) != base  # Nytt innehåll, samma position


# C2:
def test_vector_id_is_name_based_uuid5():
    vector_id = make_vector_id("abc123", 0)
    assert isinstance(vector_id, uuid.UUID)
    assert vector_id.version == 5  # 5 = namnbaserad, 4 innebär slumpmässig


# D2:
def test_measure_pages_counts_empty_and_short_pages():
    sections = [
        Section(text="", source_location={"page": 1}),  # tom
        Section(
            text="x" * (MIN_CHUNK_SIZE - 1), source_location={"page": 2}
        ),  # kort, precis under
        Section(
            text="x" * MIN_CHUNK_SIZE, source_location={"page": 3}
        ),  # precis på gränsen, ger chunk
        Section(text="riktig text " * 20, source_location={"page": 4}),  # vanlig sida
    ]
    assert measure_pages(sections) == (4, 1, 1)


# E2:
def test_measure_pages_whitespace_only_page_is_empty():
    sections = [Section(text="  \n\t \n", source_location={"page": 1})]
    assert measure_pages(sections) == (1, 1, 0)


# F2:
def test_short_page_is_exactly_what_chunker_discards():
    short = Section(text="x" * (MIN_CHUNK_SIZE - 1), source_location={"page": 1})
    kept = Section(text="x" * MIN_CHUNK_SIZE, source_location={"page": 2})
    assert measure_pages([short]) == (1, 0, 1)
    assert chunk_document([short]) == []  # kort enligt måttet = kastad av chunkern
    assert measure_pages([kept]) == (1, 0, 0)
    assert len(chunk_document([kept])) == 1  # på gränsen = behållen


# ====== DEL 3: Failure paths(felvägarna) i extract_one_document() ======
# =======================================================================
#
# Alla TRE vägarna AVSLUTAS INNAN chunks skrivs. På så vis räcker SQLite-session från conftest.py
# Filen skrivs och ska hashas som BYTES: write_text() byter \n mot \r\n på Windows,
# då hade hashen berott på operativsystemet och inte på innehållet (Windows och OS issues...)
SOURCE_PATH = "python_course/notes.md"
CONTENT = "# Rubrik\n\nText som ingestion hashade.\n".encode("utf-8")


def add_pending_document(session: Session, content: bytes) -> Document:
    """
    ONE PENDING markdown document with ONE copy at SOURCE_PATH, committed.
    Same shape as when ingestion writes it: the document and its first copy in the same commit.
    file_hash is the hash of content, what ingestion saw.
    """
    course = Course(course_tag="python")
    session.add(course)
    session.flush()
    document = Document(
        filename="notes.md",
        source_type="markdown",
        file_hash=hashlib.sha256(content).hexdigest(),
        status=DocumentStatus.PENDING,
    )
    document.source_files.append(
        SourceFile(course_id=course.id, source_path=SOURCE_PATH)
    )
    session.add(document)
    session.commit()
    return document


def write_source_file(repos_root: Path, content: bytes) -> None:
    """
    Writes the file where the documents copy points, under repos_root.
    """
    path = repos_root / SOURCE_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(content)


# A3: Filen saknas på disken -> FAILED med SOURCE_MISSING
# rollback() laddar om dokumentet från databasen, bara det som är COMMITTAT finns kvar
def test_missing_source_file_marks_document_failed(tmp_path, session):
    document = add_pending_document(session, CONTENT)
    # Ingen fil skrivs, exemplaret pekar på en fil som inte finns

    outcome = extract_one_document(document, tmp_path, session)

    assert outcome == ExtractionOutcome.FAILED
    session.rollback()
    assert document.status == DocumentStatus.FAILED
    assert document.failure_reason == FailureReason.SOURCE_MISSING


# B3: Filen har ändrats sedan ingestion -> RuntimeError och hela körningen ska stoppas
def test_changed_source_file_stops_the_run(tmp_path, session):
    document = add_pending_document(session, CONTENT)
    write_source_file(tmp_path, CONTENT + b"Rad tillagd efter ingestion.\n")

    with pytest.raises(RuntimeError, match="changed on disk"):
        extract_one_document(document, tmp_path, session)

    session.rollback()
    assert document.status == DocumentStatus.PENDING


# C3: Fil finns men går INTE att läsa (transient error) -> SKIPPED och står kvar som PENDING
# PermissionError blir simulerad, chmod hindrar inte läsning på Windows.
# Patchas där namnet SLÅS UPP (extract.py) inte där funktionen bor (kms.hashing)
def test_unreadable_source_file_is_skipped(tmp_path, session, monkeypatch):
    document = add_pending_document(session, CONTENT)
    write_source_file(tmp_path, CONTENT)

    def raise_permission_error(file_path):
        raise PermissionError(f"Simulated: {file_path} is locked")

    monkeypatch.setattr(
        "kms.extraction.extract.compute_file_hash", raise_permission_error
    )

    outcome = extract_one_document(document, tmp_path, session)

    assert outcome == ExtractionOutcome.SKIPPED
    session.rollback()
    assert document.status == DocumentStatus.PENDING
