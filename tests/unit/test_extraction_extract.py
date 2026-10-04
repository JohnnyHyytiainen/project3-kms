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

import uuid
from pathlib import Path

from kms.extraction.chunker import MIN_CHUNK_SIZE
from kms.extraction.chunker import chunk_document
from kms.extraction.chunker import Section
from kms.extraction.extract import build_sections_from_markdown
from kms.extraction.extract import make_vector_id, measure_pages


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


# A5:
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


# B5:
def test_markdown_preamble_becomes_its_own_section(tmp_path):
    sections = build_sections_from_markdown(
        write_markdown(tmp_path, MARKDOWN_WITH_PREAMBLE)
    )

    assert sections[0].source_location["heading"] is None
    assert sections[0].source_location["line_start"] == 1
    assert "Intro line before any heading." in sections[0].text


# C5:
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


# D5:
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


# E5:
def test_markdown_empty_file_returns_empty_list(tmp_path):
    assert build_sections_from_markdown(write_markdown(tmp_path, "")) == []


# F5:
def test_markdown_hash_without_space_is_not_a_heading(tmp_path):
    text = "#hashtag is not a heading\n####### seven hashes is not either\nplain text\n"
    sections = build_sections_from_markdown(write_markdown(tmp_path, text))

    assert len(sections) == 1
    assert sections[0].source_location["heading"] is None


# G5:
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
