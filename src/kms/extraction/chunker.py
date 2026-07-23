# Chunker.py - Script för att stycka upp alla dokument i bitar
# Kod: Engelska
# Kommentarer: Svenska
#
# Source-agnostisk, bryr sig inte vartifrån texten kommer utan enbart om just TEXTEN + metadatan.
# Storlek är mätt i tecken och inte tokens som första level.

from dataclasses import dataclass

# ===== KONSTANTER =====
# "Rimliga" värden att testa första gången med, tuning kan behövas
TARGET_CHUNK_SIZE = 1500  # Tecken, ungefär 300 tokens
OVERLAP_SIZE = 300  # 20% av TARGET_CHUNK
MIN_CHUNK_SIZE = 50  # Tröskelvärde, under 50 och säkert bara 'brus'


STEP_SIZE = TARGET_CHUNK_SIZE - OVERLAP_SIZE
# pre conditions - Utan dom här håller varkent variant eller invariant
assert STEP_SIZE > 0, "OVERLAP_SIZE must be less than TARGET_CHUNK_SIZE"
assert MIN_CHUNK_SIZE <= OVERLAP_SIZE, (
    "otherwise, tail fragments may/will be lost without coverage"
)


# ===== 1: DATACLASSES =====
# TextChunk + Section
@dataclass
class TextChunk:
    """
    This class has no idea which document its working on,
    extract.py is the one that knows and does the mapping.
    """

    chunk_index: int
    content: str
    source_location: dict
    char_count: int


@dataclass
class Section:
    """
    One chunkable unit of a document, a PDF page, A markdown header block,
    A transcript time-segment.

    Same reasoning as ExtractedPage + TextChunk:
    Explicit field names, no ambiguity later about which text+metadata key:value-pair
    that belongs together.

    chunk_document() recieves a list of these.
    chunk_section() itself never sees one directly since it still only takes,
    text + source_location without changing anything.
    """

    text: str
    source_location: dict


# ===== 2: Chunking funktion =====
def chunk_section(
    text: str, source_location: dict, start_index: int = 0
) -> list[TextChunk]:
    """
    Function that splits ONE section(PDF page, markdowns body) into
    appropriate sized chunks.

    Recieves text + metadata that is needed for source_location.
    Pure function, no I/O, DB. Easy to test with strings.

    Simplificated on purpose. Splits on raw character position, can possible cut mid-word/sentence.
    Needs testing before fine-tuning.
    """
    text = text.strip()

    if len(text) < MIN_CHUNK_SIZE:
        return []

    if len(text) <= TARGET_CHUNK_SIZE:
        return [
            TextChunk(
                chunk_index=start_index,
                content=text,
                source_location=source_location,
                char_count=len(text),
            )
        ]

    chunks = []
    position = 0
    index = start_index
    text_len = len(text)

    while position < text_len:
        end = min(position + TARGET_CHUNK_SIZE, text_len)
        piece = text[position:end].strip()

        if len(piece) >= MIN_CHUNK_SIZE:
            chunks.append(
                TextChunk(
                    chunk_index=index,
                    content=piece,
                    source_location=source_location,
                    char_count=len(piece),
                )
            )
            index += 1

        # OVILLKORLIG, Varje varv MÅSTE flytta fram position.
        position += STEP_SIZE
        # Overlap skapas här. Target_chunk_size - overlap_size
        if text_len - position <= OVERLAP_SIZE:
            break

    return chunks


# ===== 3: Document level chunking funktion =====
def chunk_document(sections: list[Section]) -> list[TextChunk]:
    """
    Loops chunk_section() over every section of one document, keeping
    chunk_index running and consistent across the ENTIRE document.
    No need of resetting per section, same idea as a books page numbers and not resetting page nr per chapter.

    Sequential by design - Each call needs to know HOW many chunks previous sections produced,
    so that next_index iterates forward through the loop.
    Same shape as run_ingestion() hash set in ingest.py.

    Terminates trivially - A for loop over an already-known-lenght list,
    no while loop with a computed condition.
    No need for invariant/termination proof like chunk_section() needed.
    """
    all_chunks: list[TextChunk] = []
    next_index = 0

    # Varje anrop MÅSTE veta HUR MÅNGA chunks som redan skapats
    # Det är för att kunna fortsätta räkna rätt.
    for section in sections:
        section_chunks = chunk_section(
            section.text, section.source_location, start_index=next_index
        )
        # om sektionen är/var för liten så rör sig inte section_chunks [] och next_index alls
        # Nästa sektion fortsätter exakt där SENAST framgångsrika sektion slutade.
        all_chunks.extend(section_chunks)
        next_index += len(section_chunks)

    return all_chunks
