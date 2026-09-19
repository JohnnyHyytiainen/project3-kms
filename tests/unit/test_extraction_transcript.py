# test_extraction_transcript.py. Unit tester för extract.py och build_sections_from_transcript() funktionen botten av testpyramiden
# Kod: Engelska
# Kommentarer: Svenska
# ====================
# Eget test script då test_extraction.py redan bör cunker.py och markdown parsern
# transcript parser funktionen har redan tillräckligt många egna edge cases och bör vara stand-alone test script
#
# Tester som är uppdelade i 5 delar.
#
# Del 1: Grundkontrakt. Struktur, innehåll och metadata.
# A1: Section per Timestamp i filens ordning med RÄTT text i RÄTT sektion
# B1: Timestamp ligger i source_location och ALDRIG i texten. Tvärtom mot markdown
# C1: Ett segment kan sträcka sig över flera rader, row split inuti ska bevaras
#
# Del 2: Front matter och raderna före nästa stämpel (Timestamp)
# A2:
# B2:
# C2:
#
# Del 3: Tomma resultat
# A3:
# B3:
# C3:
#
# Del 4: Stämpelns form(Timestamps form). Vad som räknas som gräns
# A4: Stämpel mitt i en mening är tal och ingen gräns, ^-ankaret är avsiktligt
# B4: Felformade markörer delar inte, uttrycket är strikt med flit
# C4: Regression. Tredels timestampen [1:00:33] är en ny gräns. Finns i 3 fall i materialet.
#
# Del 5: Egenskaper och stabilitet
# A5: Ingen text försvinner och ingen dubbleras
# B5: Trasiga byte kraschar inte, errors="replace" är en del av kontraktet

import pytest
from pathlib import Path

from kms.extraction.extract import build_sections_from_transcripts


def write_transcript(tmp_path: Path, text: str) -> Path:
    """
    Writes the test text to a real file and returns its path.

    Same shape as write_markdown() in test_extraction.py.
    build_sections_from_transcripts() takes a Path and opens it itself,
    the same way it does in extract.py after download_file() has fetched the object from bronze.
    """
    path = tmp_path / "transcript.md"
    path.write_text(text, encoding="utf-8")
    return path


# Menat att spegla den riktiga formen i repos_for_data/youtube_transcripts/ foldern
# front matter, en titelrad och sen ett block per timestamp med blankrad mellan.
TRANSCRIPT_WITH_FRONT_MATTER = (
    "---\n"
    'title: "A gentle introduction to AI"\n'
    "video_id: 6fjd0i_n35c\n"
    "source_type: youtube_transcript\n"
    "---\n"
    "\n"
    "# A gentle introduction to AI\n"
    "\n"
    "**[00:00]** First segment speech.\n"
    "\n"
    "**[00:12]** Second segment speech.\n"
    "\n"
    "**[00:24]** Third segment speech.\n"
)


# ===== Del 1: Mitt grundkontrakt =====
#
# A1:
def test_transcript_one_section_per_timestamp(tmp_path):
    sections = build_sections_from_transcripts(
        write_transcript(tmp_path, TRANSCRIPT_WITH_FRONT_MATTER)
    )

    # Rätt text i rätt sektion och att sektionerna kommer i filens ordning.
    assert len(sections) == 3
    assert [s.text for s in sections] == [
        "First segment speech.",
        "Second segment speech.",
        "Third segment speech.",
    ]
    assert [s.source_location["timestamp"] for s in sections] == [
        "00:00",
        "00:12",
        "00:24",
    ]


# B1:
def test_transcript_timestamp_is_metadata_and_not_text(tmp_path):
    sections = build_sections_from_transcripts(
        write_transcript(tmp_path, TRANSCRIPT_WITH_FRONT_MATTER)
    )

    # Skillnaden mellan markdown parsern där rubriken stannar INNE i texten.
    # Här är timestampen UTANFÖR. En rubrik är en mening som beskriver något och ska embeddas
    # En timestamp är en koordinat.
    for section in sections:
        assert "**[" not in section.text
    assert sections[0].source_location == {"timestamp": "00:00"}


# C1:
def test_transcript_segment_spanning_several_lines(tmp_path):
    # Strikt defensivt test. Kursmaterialet idag har 0 multiline segment, funktionen
    # lovar dock inte en rad per segment och chunkern tar emot texten som en stor klump.
    text = (
        "**[00:00]** First line in the segment.\n"
        "Second line in the same segment.\n"
        "\n"
        "**[00:12]** Next segment.\n"
    )
    sections = build_sections_from_transcripts(write_transcript(tmp_path, text))

    assert len(sections) == 2
    assert sections[0].text == (
        "First line in the segment.\nSecond line in the same segment."
    )


# ====== Del 2: Front matter och raderna FÖRE första timestampen ======
#
# A2:
def test_transcript_front_matter_and_title_are_dropped(tmp_path):
    sections = build_sections_from_transcripts(
        write_transcript(tmp_path, TRANSCRIPT_WITH_FRONT_MATTER)
    )
    joined = "\n".join(s.text for s in sections)

    # Alla filer i kursmaterialet har front matter.
    # Läckte den in skulle varje transcripts första chunk börja med YAML metadata i stället för med tal.
    assert "video_id" not in joined
    assert "# A gentle introduction to AI" not in joined


# B2:
def test_transcript_without_front_matter_still_parses(tmp_path):
    text = "**[00:00]** Straight into the speech.\n"
    sections = build_sections_from_transcripts(write_transcript(tmp_path, text))

    # Borttagning av front matter är städning och inte förutsättning!
    assert len(sections) == 1
    assert sections[0].text == "Straight into the speech."


# C2:
def test_transcript_without_timestamps_returns_empty_list(tmp_path):
    text = '---\ntitle: "x"\n---\n\n# Just a title\n\nProse with no timestamps.\n'
    sections = build_sections_from_transcripts(write_transcript(tmp_path, text))

    assert sections == []


# ===== Del 3: TOMMA resultat =====
#
#
# A3:
def test_transcript_empty_file_returns_empty_list(tmp_path):
    assert build_sections_from_transcripts(write_transcript(tmp_path, "")) == []


# B3:
def test_transcript_only_front_matter_returns_empty_list(tmp_path):
    text = '---\ntitle: "A video without transcript"\nvideo_id: abc123\n---\n'
    assert build_sections_from_transcripts(write_transcript(tmp_path, text)) == []


# C3:
def test_transcript_timestamp_without_speech_produces_no_section(tmp_path):
    # Strikt defensivt test. Kursmaterialet har just nu NOLL tomma segment.
    # close_section()-guard behövs för att det inte ska fyllas på med tomma chunks utan timestamp i db.
    # Utan den blir det huvudvärk när det är dags för embedding.

    text = "**[00:00]** Real speech.\n\n**[00:12]**\n\n**[00:24]** More speech.\n"
    sections = build_sections_from_transcripts(write_transcript(tmp_path, text))

    assert len(sections) == 2
    assert [s.source_location["timestamp"] for s in sections] == ["00:00", "00:24"]


# ===== Del 4: Timestampens FORM =====
#
#
# A4:
def test_transcript_marker_inside_a_sentence_is_not_a_boundary(tmp_path):
    # Mätt mot materialet. En fil har en marker mitt i raden.
    # ^ anchor i uttrycket är vad som gör den till tal istället för gräns
    text = "**[00:00]** Talking begins here **[00:12]** and still talking.\n"
    sections = build_sections_from_transcripts(write_transcript(tmp_path, text))

    assert len(sections) == 1
    assert sections[0].source_location == {"timestamp": "00:00"}
    assert "**[00:12]**" in sections[0].text


# B4:
# Pytest decorator
@pytest.mark.parametrize(
    "marker",
    [
        "**[5:30]**",  # ensiffrig minut
        "[00:30]",  # utan fetstil
        "*[00:30]*",  # enkel asterisk
    ],
)
def test_transcript_malformed_marker_is_not_a_boundary(tmp_path, marker):
    # Defensivt här med. Ingen av formerna finns i materialet idag, det kan dock ändras.
    # Testet fryser att uttrycket är strikt, går att göra mindre strikt i framtiden om så behövs.
    text = f"**[00:00]** A Real segment.\n\n{marker} Not a boundary.\n"
    sections = build_sections_from_transcripts(write_transcript(tmp_path, text))

    assert len(sections) == 1
    assert marker in sections[0].text


# C4:
def test_transcript_hour_long_timestamp_opens_a_new_section(tmp_path):
    text = (
        "**[59:00]** Last segment before the hour.\n"
        "\n"
        "**[1:00:01]** First segment after the hour.\n"
    )
    sections = build_sections_from_transcripts(write_transcript(tmp_path, text))

    assert len(sections) == 2
    assert sections[1].text == "First segment after the hour."
    assert sections[1].source_location == {"timestamp": "1:00:01"}


# ===== Del 5: Egenskaper och stabilitet =====
#
#
# A5:
def test_transcript_no_speech_is_lost_or_duplicated(tmp_path):
    sections = build_sections_from_transcripts(
        write_transcript(tmp_path, TRANSCRIPT_WITH_FRONT_MATTER)
    )
    joined = "\n".join(s.text for s in sections)

    # En bugg med gränserna gör antingen att text tappas eller att den dupliceras.
    # count() == 1 ska fånga båda två utan att fallen räknas upp en och en.
    for phrase in (
        "First segment speech.",
        "Second segment speech.",
        "Third segment speech.",
    ):
        assert joined.count(phrase) == 1


# B5:
def test_transcript_invalid_utf8_does_not_raise(tmp_path):
    path = tmp_path / "transcript.md"
    path.write_bytes(b"**[00:00]** Broken byte \xe9 in the middle.\n")

    sections = build_sections_from_transcripts(path)

    assert len(sections) == 1
    assert "in the middle." in sections[0].text
