# project3-kms - A Knowledge Management System

![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![CI](https://github.com/JohnnyHyytiainen/project3-kms/actions/workflows/ci.yml/badge.svg)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063?)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?)
![Docker](https://img.shields.io/badge/Docker%20Compose-2496ED?)

**Status:** MVP v1 complete (tagged `v1.0.0`) · MVP v2 built and verified end-to-end · MVP v3 (embeddings) next

## 1. Problem & Approach

Data engineering students face scattered course material - unindexed slides, markdown repos, hours of video transcripts. Generic LLM tools hallucinate freely and have no awareness of a specific curriculum's actual content.

`project3-kms` is a Retrieval-Augmented Generation (RAG) knowledge system built over a real corpus - 745 PDF, markdown and transcript files across 13 course repositories from a data engineering program (STI, DE25) - organized through a **medallion-layered pipeline** (`Bronze` -> `Silver` -> `Gold`). **The design goal**: every answer traces back to its exact source chunk, not a plausible-sounding guess.

Built as a **thesis project**, staged across six MVPs. Ingestion and metadata are complete (MVP v1); extraction and chunking are built and verified against the real corpus (MVP v2). Embeddings, a source-cited retrieve -> rerank -> generate API, a bounded self-correction loop and production deployment follow through MVP v6.

```mermaid
---
config:
  theme: neo-dark
---
flowchart LR
    SRC["Course material<br/>PDF · Markdown · Transcripts"] --> ING["Ingestion<br/>v1 - done"]
    ING --> BRONZE[("PostgreSQL<br/>Bronze")]
    BRONZE --> EXT["Extraction & Chunking<br/>v2 - done"]
    EXT --> SILVER[("PostgreSQL chunks<br/>Silver")]
    SILVER --> EMB["Embeddings<br/>v3 - next"]
    EMB --> VDB[("ChromaDB")]
    VDB --> API["RAG API<br/>retrieve -> rerank -> generate<br/>v4"]
    API --> OUT["Answer + cited sources"]
```

## 2. The Corpus, Measured

Every figure below was counted against disk and against the database, never estimated. The gaps between them are the interesting part.

| | |
|---|---|
| Supported files on disk (PDF + markdown/transcript) | **745** |
| Currently ingested | **473** |
| Rows in `documents` after content-hash dedup | **407** |
| Content duplicates collapsed | **66 (14.0 %)** |
| Unique PDFs among them | **94** -> 90 `EXTRACTED`, 4 `FAILED` |
| Full rebuild from an empty stack | **~46 s** (21.4 s ingestion + 24.9 s extraction) via `tools/rebuild.py` |
| Test suite | **89 unit tests**, 0 integration |

Three of those gaps are open work, stated here rather than hidden:

- **272 transcript files are not ingested yet.** They live in mirror folders whose names carry the course they belong to, while the ingestion path currently derives the course tag from the filename. Deriving it from the folder instead unlocks all 272 at once and costs no new mapping rules - the twelve folder names already match existing keys exactly.

- **The 14 % dedup rate is a provenance problem, not just a storage win.** A file reused across two courses collapses to one row with one `course_tag`, which is correct for storage and wrong for course-filtered retrieval. A `document_course` junction table has to land *before* anything is embedded - adding metadata after indexing means re-embedding everything.

- **The 4 failed PDFs were opened and looked at.** They are handwritten notes and text-stored-as-image: two distinct OCR problems, not one. The quieter failure matters more - a full slide deck that extracts to a single chunk is marked `EXTRACTED` with no error at all, and becomes a vector that promises more than it holds.

## 3. Tech Stack

| Layer | Built | Planned |
|---|---|---|
| **Ingestion** | `Python 3.12`, `SQLAlchemy 2.0`, `Alembic`, `psycopg3` | - |
| **Extraction** | `PyMuPDF`, `pymupdf4llm` | OCR fallback, table extraction, header/footer filtering |
| **Storage** | `PostgreSQL` | `ChromaDB (vectors)` |
| **AI layer** | - | `Grunden.ai` - `bge-m3` embeddings, `bge-reranker-v2-m3`, `glm-5.2` |
| **Serving** | - | `FastAPI` |
| **Orchestration** | - | `Airflow`, `dbt` + `DuckDB` |
| **Ops** | `Docker Compose`, `GitHub Actions CI`, `pytest` (89 unit), `Ruff` | integration tests, reverse proxy + `TLS`, `CD` |

## 4. Key Decisions

- **Course tags come from an explicit mapping, and an unknown repo crashes the run.** Three error types are handled differently on purpose: an unreadable file is skipped, while a changed file at a known path and an unrecognised repo name both stop the run. Inferring the tag with a regex would have been shorter and would have silently mislabelled hundreds of files the first time a repo was renamed.

- **`Document.status` is a `VARCHAR` holding the enum name, not a native Postgres `ENUM`.** A native enum turns every new status value into a migration. The trade-off is written down because it has a sharp edge: SQLAlchemy persists the *name*, so `WHERE status = 'pending'` returns zero rows without an error - the column contains `'PENDING'`. Raw SQL and dbt models further down the pipeline have to match on the name.

- **A failed document gets a reason code on its own row - no crash, no dead-letter table.** Four codes separate "the PDF had no extractable text" from "it had text, below the threshold". The second answer means the document had content all along and the threshold is what's wrong. Naming the codes after what is actually broken, rather than after where the code noticed, is what makes them readable six months later.

- **Postgres is the source of truth for chunk text; the vector store is always a derivative.** ChromaDB can be dropped and rebuilt from Postgres at any time, and never holds anything that exists nowhere else. `ChromaDB` over `Qdrant` for the same reason a corpus this size doesn't yet justify a dedicated vector service - `Qdrant` stays on the table if measured latency ever demands it.

- **Source citation is mandatory, not a feature toggle.** Every answer returns the exact chunk(s) it came from. Without that, the system is just another chatbot that sounds confident.

- **The eval-harness ships before the self-correction loop.** MVP v4's baseline gets measured against 40-60 question/source pairs before MVP v4.5 adds any self-correction - otherwise there is no way to tell whether the loop helps or just adds latency.

## 5. Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Docker.

> **The course material is not redistributed and is not part of this repository.** The pipeline reads from a local `repos_for_data/` directory, which is gitignored. Cloning gives you the system, not the corpus.

**1. Clone and install**

`git clone https://github.com/JohnnyHyytiainen/project3-kms.git`  

`cd project3-kms`  

`uv sync`


**2. Configure environment**

`cp .env.example .env`

Fill in `DB_USER`, `DB_PASSWORD` and `DB_NAME`. `docker-compose.yml` reads the same three variables, so Postgres and the application cannot disagree about them. `GRUNDEN_API_KEY` can stay as a placeholder until the embedding step runs.

**3. Start infrastructure** (Postgres on `:5436`, ChromaDB on `:8006`)

`docker-compose up -d`

**4. Apply the database schema**

`uv run alembic upgrade head`

**5. Run ingestion, then extraction**


`uv run python -m kms.ingestion.ingest`  
`uv run python -m kms.extraction.extract`

**6. Full rebuild**

`uv run python tools/rebuild.py`

Checks that ChromaDB and Grunden.ai answer, asks for confirmation, empties the derived tables and the vector collection, then reruns ingestion, extraction and embedding, reconciles Postgres against ChromaDB and prints the time per step. The truncate is required: the dedup check reads from Postgres, so without it ingestion would skip every file.

> **A container restart needs no rebuild.** Postgres and ChromaDB keep their data in Docker volumes. Changed course material only reaches the index through a full rebuild, and `repos_for_data/` stays the only real source of truth.

## 6. Attribution

Course material used in this project - PDFs, markdown, and video transcripts - comes from the STI Data Engineering program (DE25) and is used **with written permission from the course instructors, obtained before ingestion began**. The material itself is not redistributed and is not part of this repository.

- **Debbie Lau** - [github.com/Db-Lau](https://github.com/Db-Lau)
- **Kokchun Giang** - [github.com/kokchun](https://github.com/kokchun)
- **Kristoffer Johansson** - [github.com/Krillinator](https://github.com/Krillinator) · [inspiira.se](https://inspiira.se/)

Courses developed and delivered via [AIgineerAB](https://github.com/AIgineerAB) - Debbie and Kokchun's company and by [Kristoffer Johansson](https://inspiira.se/)

## 7. License

MIT - see [LICENSE](https://github.com/JohnnyHyytiainen/project3-kms/blob/main/LICENSE).

## 8. Author

Johnny Hyytiäinen - [github.com/JohnnyHyytiainen](https://github.com/JohnnyHyytiainen) for portfolio, LinkedIn, and other projects.
