# pdf_extractor.py script för att extrahera data ifrån mina PDFer.
# Kod: Engelska
# Kommentarer: Svenska
#
# Extraherar ren text ur PDFs, sida för sida.
# Nivå 1 av grund före glans: get_text("text") default.
# Går över till dict läget eller pymupdf4llm visar sig behöva det(Största sannolikhet)

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


# ===== 1: DATACLASS =====
# Strikt behållare för en sidas extraherade innehåll
# Decorator
@dataclass
class ExtractedPage:
    """
    One pages worth of extracted text, with its page number perserved.

    Dataclass instead of a plain string, same reasoning av DiscoveredFile in ingest.py script:
    Explicit field names, NO ambiguity later when this feeds Chunk.source_location during chunking phase.
    Page number MUST survive this step - Losing it here means it can NEVER be added back downstream.
    """

    page_number: int  # 1 indexerat, matchar hur en människa räknar sidor
    text: str


# ===== 2: EXTRACTION FUNKTION =====
# Funktion som öppnar och läser PDF, sida för sida.
def extract_pages(pdf_path: Path) -> list[ExtractedPage]:
    """
    Opens PDF and extracts text page by page.

    Level 1 in the ladder: page.get_text("text"),
    MuPDFs own block based extraction,
    verified against real multi-column layout to correctly separate colums.

    NOT escalated to use sort=True, testing showed merges of columns incorrectly.

    Returns a list rather than a generator - Unlike walk_source_files,
    later steps will need ALL pages of ONE document available at once to compare across pages,
    not a single pass stream.

    Wont catch exceptions here.
    """
    with fitz.open(pdf_path) as doc:
        pages = [
            ExtractedPage(page_number=i + 1, text=page.get_text("text"))
            for i, page in enumerate(doc)
        ]
    return pages
