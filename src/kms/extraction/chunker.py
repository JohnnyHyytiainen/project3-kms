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


# ===== 1: DATACLASS =====
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
