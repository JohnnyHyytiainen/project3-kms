# test_pdf_extractor.py script - Unit tester för pdf_extractor.py, botten av test pyramiden
# Kod: Engelska
# Kommentarer: Svenska
# ====================
# Testerna är uppdelade i två delar (A+B)
#
# A: Test för bytes som inte är en PDF. Ska kasta PdfExtractionError
#
# B: Test för tom fil. Ska kasta PdfExtractionError, EmptyFileError.

import pytest

from kms.extraction.pdf_extractor import PdfExtractionError, extract_pages

# extract_pages - Filer som inte går att öppna som PDF
# PyMuPDF kastar sina egna fel som ärger RuntimeError, pdf_extractor.py scriptet
# översätter RuntimeError till PdfExtractionError som extract.py scriptet sätter som FAILED


# ===== A: Fel bytes i filen =====
def test_extract_pages_raises_on_bytes_that_are_not_a_pdf(tmp_path):
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"this is not a PDF\n")

    with pytest.raises(PdfExtractionError):
        extract_pages(pdf_path)


# ===== B: Tom fil. PyMuPDF ska kasta EmptyFileError, en sub-class till FileDataError =====
def test_extract_pages_raises_on_empty_file(tmp_path):
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"")

    with pytest.raises(PdfExtractionError):
        extract_pages(pdf_path)
