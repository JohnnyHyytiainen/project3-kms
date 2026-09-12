# test_extraction.py. Unit tester för chunker.py, botten av testpyramiden
# Kod: Engelska
# Kommentarer: Svenska
# ====================
# Testerna är delade i 5 delar.
#
# Del 1: Regression tests för infinity loops (bug som hittades tidigare i chunker.py)
# A1: "a"*1726  --> 2 chunks [1500, 526]
# B1: "a"*2449 --> oändlig loop
# C1: "ord "*400 --> OK 2 chunks [1499, 399]
# D1: "a"*1200 + " "1500 + "b"*1000  --> oändlig loop
#
# Del 2: Gränsvärden för MIN_CHUNK_SIZE
# A2: testar MIN_CHUNK_SIZE
# B2: testar TARGET_CHUNK_SIZE
#
# Del 3: Duplicate chunk + tail overlap tester.
# A3: Testar DUPLICATE CHUNK + TAIL OVERLAP logik
#
# Del 4: Tester för chunk_document() logik.
# A4: Verifierar att en section mitt i dokument som är för kort eller tomt ignoreras utan att avbryta loopen,
# och att `chunk_index` fortsätter att öka från rätt nummer.
# B4: Testar att next_index räknas sekventiellt när tidigare section delats upp i flera chunks.
# C4: Verifierar att tom section returnerar ett tomt index
#
# Del 5: Tester för build_sections_from_markdown() i extract.py
# A5: En sektion per rubrikblock, rubrikraden ligger INNE i sektionens text
# B5: Text före första rubriken blir en egen sektion utan rubrik
# C5: Radintervallen är 1-indexerade, inklusiva, utan hål och utan överlapp
# D5: Fil utan rubriker ger EN sektion, inte noll
# E5: Tom fil ger tom lista, vilket uppströms blir NO_TEXT_EXTRACTED
# F5: "#taggen" utan mellanslag är ingen rubrik
# G5: Regression - rubrikliknande rad inuti ett kodblock delar inte sektionen
import pytest
from pathlib import Path

from kms.extraction.chunker import MIN_CHUNK_SIZE, TARGET_CHUNK_SIZE
from kms.extraction.chunker import chunk_section, chunk_document
from kms.extraction.chunker import Section
from kms.extraction.extract import build_sections_from_markdown


#
def make_positional_text(n: int) -> str:
    """
    Sequential numbers ("0123456789101112") instead of "a" * n.

    A homogeneous text means that every sub string trivially exists within,
    every longer string, regardless of actual position.
    With sequential digits, a sub string unambiguously indicates WHICH position it originated from.
    """
    parts, total, i = [], 0, 0
    while total < n:
        s = str(i)
        parts.append(s)
        total += len(s)
        i += 1
    return "".join(parts)[:n]


# ===== Del 1: Regression tester för infinity loops =====
# Alla fyra fall, A1, B1, C1, D1 testas här.
# =======================================================
# A1
def test_control_case_terminates_and_splits_correctly():
    """Test A1: Normal long text, no odd edges."""
    result = chunk_section("a" * 1726, {"page": 1})
    assert [c.char_count for c in result] == [1500, 526]


# B1
def test_short_tail_49_chars_no_longer_infinity_loop():
    """Test B1: Previous cause of infinity loop - tail(49tokens) never reached 50."""
    result = chunk_section("a" * 2449, {"page": 1})
    assert [c.char_count for c in result] == [1500, 1249]


# C1
def test_whitespace_boundary_matches_known_answer():
    """Test C1: Whitespace test, edge against .strip() and overlap at the same time."""
    result = chunk_section("ord " * 400, {"page": 1})
    assert [c.char_count for c in result] == [1499, 399]
    # .strip() förskjutning, likhet vid 299 och INTE 300 pga OVERLAP_SIZE = 300
    assert result[0].content[-299:] == result[1].content[:299]
    assert result[0].content[-300:] != result[1].content[:300]


# D1
def test_blank_run_mid_document_no_longer_infinity_loop():
    """
    "Test D1: A completely blank chunk in the middle of the text, not at the end.
    The rest of the document (1000 characters) must finish chunking after
    the blank chunk, not just 'the loop ends without a crash'"
    """
    text = "a" * 1200 + " " * 1500 + "b" * 1000
    result = chunk_section(text, {"page": 1})
    assert result[0].char_count == 1200
    assert "b" * 1000 in result[1].content


# ====== Del 2: Gränsvärden tester av chunking logik ======
# Tester av två fall för chunking logik, A2, B2,  testas här.
# =========================================================
# Konstant decorator för att använda i A2 testet
@pytest.mark.parametrize(
    "size,expected_chunk",
    [
        (MIN_CHUNK_SIZE - 1, False),  # 49 tecken --> FÖR KORT ska ej bli en chunk
        (MIN_CHUNK_SIZE, True),  # 50 tecken --> EXAKT på gränsen, SKA bli en chunk
    ],
)

# A2
def test_min_chunk_size_boundary(size, expected_chunk):
    result = chunk_section("a" * size, {"page": 1})
    assert (len(result) == 1) == expected_chunk


# Konstant decorator för att använda i B2 testet
@pytest.mark.parametrize(
    "size,expected_chunks",
    [
        (TARGET_CHUNK_SIZE, 1),  # 1500 --> Får plats i EN chunk
        (TARGET_CHUNK_SIZE + 1, 2),  # 1500 +1 --> TVINGAS delas upp i två chunks
    ],
)

# B2
def test_target_chunk_size_boundary(size, expected_chunks):
    result = chunk_section("a" * size, {"page": 1})
    assert len(result) == expected_chunks


# ====== Del 3: Duplicate chunks och TAIL OVERLAP LOGIK ======
# Test av Ett fall för OVERLAP och DUPLICATE logik, testas här.
# =========================================================
# Konstant decorator för att använda i A3 testet
@pytest.mark.parametrize("n", [2450, 2500])  # verifierat duplicate case
def test_no_chunk_is_a_pure_subset_of_neighbor(n):
    text = make_positional_text(n)
    result = chunk_section(text, {"page": 1})
    for i in range(len(result) - 1):
        assert result[i + 1].content not in result[i].content


# ====== Del 4: Test av chunk_document() logik ======
# ===================================================
# A4
def test_chunk_document_blank_section_mid_document():
    """
    Test A4: Verifies that a section in the middle of the document
    that is too short or empty is ignored without breaking the loop,
    and that `chunk_index` continues incrementing from the correct number.
    """
    sections = [
        Section(text="a" * 1500, source_location={"page": 1}),
        Section(
            text="     ",
            source_location={"page": 2},  # TOM SEKTION (< MIN_CHUNK_SIZE)
        ),
        Section(text="B" * 1500, source_location={"page": 3}),
    ]

    result = chunk_document(sections)

    # Ska endast generera 2 chunks totalt, page 1 + 3
    assert len(result) == 2

    # verifiering av första chunken på page 1
    assert result[0].content == "a" * 1500
    assert result[0].chunk_index == 0
    assert result[0].source_location == {"page": 1}

    # verifiering av andra chunken på page 3
    # Index ska vara 1(indexing börjar från 0 as always)
    assert result[1].content == "B" * 1500
    assert result[1].chunk_index == 1
    assert result[1].source_location == {"page": 3}


# B4
def test_chunk_document_maintains_sequential_index_across_sections():
    """
    Test B4: Tests and verifies that next_index is counted up sequentially when
    when a previous section has been forced to split into multiple chunks.
    """
    sections = [
        Section(
            text="a" * 2000,
            source_location={"page": 1},  # 2000 --> 2 chunks pga TARGET_CHUNK_SIZE
        ),
        Section(
            text="b" * 1500,
            source_location={"page": 2},  # 1500 --> 1 chunk pga TARGET_CHUNK_SIZE
        ),
    ]
    result = chunk_document(sections)

    # Förväntat, 3 sections, a = 2 chunks, b = 1 chunk == 3 chunks totalt
    assert len(result) == 3
    # Chunk_index ska vara 0 + 1 för page 1 och 2 för page 2
    assert [chunk.chunk_index for chunk in result] == [0, 1, 2]

    # Verifiering att metadata + text följer med korrekt på sista chunken
    assert result[2].content == "b" * 1500
    assert result[2].source_location == {"page": 2}


# C4
def test_chunk_document_empty_input_returns_empty_list():
    """
    Verifies trivial termination with an empty list of sections.
    """
    result = chunk_document([])
    assert result == []


# ====== Del 5: Tester för build_sections_from_markdown() logik ======
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
