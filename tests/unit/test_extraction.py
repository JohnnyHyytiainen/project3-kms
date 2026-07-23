# test_extraction.py. Unit tester för chunker.py, botten av testpyramiden
# Kod: Engelska
# Kommentarer: Svenska
# ====================
# Testerna är delade i 3 delar.
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
import pytest

from kms.extraction.chunker import MIN_CHUNK_SIZE, TARGET_CHUNK_SIZE, chunk_section


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
