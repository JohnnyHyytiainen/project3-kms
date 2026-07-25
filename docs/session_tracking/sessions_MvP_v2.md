# Session tracking notes for MvP v2
*Started: 2026-07-11*
*Completed:*
---

**Saturday 2026-07-11**
*Goals for today:*

- Start MvP v2 planning and break it up in detailed tasks in `project_roadmap.md`, same as MVP v1
    - **Done**

- Write PDF extraction docs regerding extraction + chunking of PDFs using `PyMuPDF`-deps
    - **Done** 

- Add `PyMuPDF` dependency to repo using `uv add pymupdf`
    - **Done**

- Branch out and start writing `src/kms/extraction/pdf_extractor.py` script
    - *semi-done*

---

**Sunday 2026-07-12**
*Goals for today:*

- Continue working on `src/kms/extraction/pdf_extractor.py` script
    - *semi-done?*

- Add experimental PoC extraction script to test `pymupdf4llm`-deps to see if ORC works better
    - **Done**

- Start working on `chunker.py` - Chunking script
    - *semi-done?*

---

**Thursday 2026-07-23**
*Goals for today:*

- Document discovered infinity loop in `chunker.py` + decide tail for chunking logic
    - **Done**

- Implement `chunker.py` infinite bug fix + overlapping tail bug
    - **Done**

- Write tests for testing logic regarding `chunker.py` script
    **Done**

---
**Thursday 2026-07-23**
*Goals for today:*
- Start writing own docs regarding `chunk_section()`-function for better understanding
    - **Done**

- Implement understanding of `chunk_section()` into real code.
    - **Done**

- Add more unit tests for chunking and indexing logic in `test_extraction.py`-script.
    - **Done, 13/13 tests passed**

---

**Saturday 2026-07-25**
*Goals for today:*

- Add new dependency - `PyArrow` to use for my `parquet_writer.py` script thats supposed to be called on by `extract.py` script.
    - *ongoing*

- Add brief overview docs regarding `PyArrow` + parquet writing script.
    - *ongoing*

- Write `src/kms/storage/parquet_writer.py` script and test it.
    - *ongoing*