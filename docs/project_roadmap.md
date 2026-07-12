# ROADMAP - Projekt 3 (arbetsnamn TBD)
*Senast uppdaterad: 2026-07-12*
*status: MVP-staging finslipad, ej längre "lös"*

## Status och tidsram
8 veckors byggfönster (juli–26 aug) innan terminsstart. Projektval + estimeringsplan låses 30 September, ca 5 veckor in på terminen, MVP v1–v3 bör då redan fungera.

## Process - gäller alla MVP steg

Skriv lokalt --> testa --> fungerar det, containerisera --> iterera.

CI (Ruff lint + format) sätts upp dag 1 vid repo-skapande, oavsett MVP-fas, **inte valfritt**. Tester läggs till i CI-pipen per PR i takt med att de blir implementerbara, testdjupet växer, inte CI-pipens existens.

## MVP-stadier

## MVP v1 - Ingestion & Metadata (grunden)
*Tagg: `v1.0`*

Mål: En komplett Bronze layer pipeline i Docker - kursrepon in i S3
(LocalStack), metadata loggad i Postgres, redo för extraktion i MVP v2.

### Infrastruktur & Datamodell
- [x] `docker-compose.yml` - LocalStack (S3) + PostgreSQL
- [x] `.env.example` - miljövariabel-mall (DB-url, AWS_ENDPOINT_URL, Grunden.ai-nycklar)
- [x] `pyproject.toml` - dependencies
- [x] `alembic.ini` + `alembic/versions/0001_initial.py` - Document (PENDING -> EXTRACTED -> EMBEDDED -> FAILED), Chunk, User
- [x] `src/kms/db/models.py` - SQLAlchemy-modeller för samma tre tabeller

### Ingestion (`src/kms/ingestion/`, `src/kms/storage/`)
- [x] `src/kms/config.py` - central konfiguration (paths, DB-url, S3-endpoint)
- [x] `src/kms/storage/s3_client.py` - S3/LocalStack-klient (boto3)
- [x] `src/kms/ingestion/course_mapping.py` - explicit repo -> course_tag, inte auto-inference
- [x] `src/kms/ingestion/ingest.py` - lokala kursrepon -> S3 med name-space `{course_tag}/{repo_namn}/{relativ_sökväg}`, metadata till Postgres (status: PENDING), filtyp-filter (PDF/md/transkript)
- [x] `file_hash`-deduplicering vid omkörning

### CI/CD
- [x] `.github/workflows/ci.yml` - Ruff lint + format (dag 1, inte valfritt)
- [x] `tests/unit/test_ingestion.py` - initiala unit tests

### Dokumentation
- [x] `README.md` - inkl. attribution + referera till KC + Debbie
- [x] `docs/architecture/overview_kms.mmd` - Overview flowchart
- [x] `docs/architecture/erd_model.mmd` - Document/Chunk/User (första ERD model)
- [x] `docs/project_roadmap.md` - Uppdatera och stycka upp MVP v2 i samma stil som MVP v1

## MVP v2 - Extraktion & Transformation
*Tag: `v2.0`. Pågående, Silver - HÖGSTA risken i hela projektet, bör göras tidigt*

### Extraction (`src/kms/extraction/`)
- [/] `pdf_extractor.py` - PDF -> Ren text. Landa på rätt nivå. `get_text("text")` -> `sort=True` -> `get_text("dict")` -> `pymupdf4llm.to_markdown()`. Se `docs/file_docs/mvp_v2_docs/pdf_extraction_docs_mvp_v2.md` för förklaring.
- [/] Sidhuvud/sidfot-filtrering - "Fälla nr 3", KRITISKT *innan* chunking sker.
- [/] Tabellhantering - "Fälla nr 2", `page.find_tables()` eller `pymupdf4llm`.
- [ ] `transcript_parser.py` - `youtube_transcripts`-grenen hanteras separat från vanliga `.md`-kursdokument (samma `source_type`, olika struktur, avgörs via `s3_key-prefix`/`course_tag` och inte `source_type` ensamt). Behåller `[HH:MM:SS]`-tidsstämplar som `chunk-metadata` (bekräftat finns i materialet).
- [ ] Vanliga `.md`-kursdokument, enklaste extraktionsfallet, redan strukturerad text
- [ ] Script för att hämta hem korrekt transcript ifrån rätt video hittad i varje .md docs.

### Chunking (`src/kms/extraction/chunker.py`)
- [ ] Strukturmedveten `chunking`: Dela på md-rubriker (`# / ##`), samma kod som för PDF.
- [/] Storlek + overlap konfigurerbart, startpunkt 200–600 token / 10–20% overlap (se `pdf_chunking_docs_mvp_v2.md`), inte hårdkodat, ska kunna fine-tunas empiriskt mot MVP v4s eval-harness senare vid behov.
- [/] `Minimum lenght`-filter - kastar bort sannolikt brus (isolerade sidfotsrester) innan embedding.
- [ ] Metadata per chunk -> `Chunk.source_location` (JSONB, finns redan i schemat): sida (PDF), rubrik/radintervall (markdown), tidsstämpel-intervall (transkript)


### Silver-lagring och status uppdatering
- [ ] `.parquet` bor i samma `S3-bucket` som resterande data men med nytt `silver/`-prefix. Återanvänder refan befintlig infrastruktur och ingen ny `bucket` behövs.
- [ ] `src/kms/storage/parquet_writer.py` - `Chunkad text` -> `Parquet` samma SoC princip som `s3_client.py` (Storage vet HUR, extraction vet VAD).
- [ ] `src/kms/extraction/extract.py` - orchestrator, analog till `ingest.py`: Hämtar `PENDING`-dokument, extraherar, chunkar och skriver `.parquet`+ `Chunk`-rader, uppdaterar `Document.status` -> `EXTRACTED` eller `FAILED`.
- [ ] Implementera felkategorier för `extract.py`. Samma three level tänk som `ingest.py` (läs/verktygsfel -> skip och logga)

### Config
- [ ] `config.py` - Nya `Settings`-fält: `chunk`-storlek/overlap-defaults med `S3_SILVER_PREFIX`.

### CI/CD
- [ ] `tests/unit/test_extraction.py` - rena funktioner (`extractor`, `chunker`) testbara utan `I/O`, samma uppdelning som `ingest.py` testerna.
- [ ] Testdata: **minst** en medvetet "smutsig" PDF (två kolumner, tabell, sidfot) utöver PoC:ens enkla fall annars blir aldrig Fälla 1–3 testad på riktigt. 

### Dokumentation
- [x] `docs/file_docs/mvp_v2_docs/pdf_extraction_docs_mvp_v2.md`
- [x] `docs/file_docs/mvp_v2_docs/pdf_chunking_docs_mvp_v2.md`
- [x] `docs/architecture/` - Dokumentera och lägg in extraktions och chunking diagram
- [] `docs/project_roadmap.md` - Uppdatera och stycka upp MVP v3 i samma stil som MVP v1+v2


    
```





### MVP v3 - Intelligence & Sök (RAG engine)
- **ChromaDB** (ändrat från Qdrant i originalutkastet, redan bevisat mönster som funkar, rätt skala för v0. Qdrant sparas till framtida iteration om/när skala kräver det)

- Script: Parquet-chunks --> Grunden.ai embeddings (`bge-m3`) --> ChromaDB

- Vektor-ID länkas till `Postgres` via `SQLAlchemy`

### MVP v4 - API & RAG-djup (Serving)
- FastAPI

- Retrieval-pipeline: vektorsökning --> `bge-reranker-v2-m3` omrankning --> `glm-5.2`-generering
*(Det här är retrieve -> rerank -> generate, inte "hybrid search" i teknisk mening, hybrid search betyder specifikt vektor + nyckelord kombinerat. Äkta hybrid search är en möjlig framtida investering/plan, inte v0.)*

- **Källspårning (XAI)** - varje svar returnerar en sources array med exakta chunk-referenser, samma mönster som glossary_db. Inte valfritt, det är hela poängen med use caset ("konkret exempel, inte en hallucination")  

- Fallback vid låg relevans, svara ärligt, inte påhittat  

- **Auth:** enkel API-key/bearer-token i v0, inte full JWT. Personligt verktyg, ingen multi-tenant roll hantering än. JWT sparas som framtida investering om behovet uppstår.  

- **Eval-harness:** 40–60 handskrivna fråga -> förväntad källa par. Mäter recall@k och faithfulness mot källan. Högsta marginalnytta i hela RAG-depth investeringen för rapporten, det ger metod + mätbart resultat, inte bara "jag byggde en app".

### MVP v4.5 - Agentisk förbättringsloop (bounded)
*(Byggs efter MVP v4 är klar OCH mätt via eval-harnesset, annars vet jag inte om loopen faktiskt förbättrar något eller bara lägger till latens)*  

- Confidence-mått på reranker-resultatet (tröskel satt empiriskt mot eval-harnessets recall@k/faithfulness)  

- Vid hög confidence: generera som i MVP v4  

- Vid låg confidence: modellen omformulerar frågan, ett nytt hämta + rerank försök (max 1x), OM fortfarande lågt efter det: svara ärligt att underlag saknas, hellre än att gissa..

- Litteratur: Self-RAG / Corrective RAG (CRAG), bounded självkorrigering, inte ett fritt agent-ramverk med verktygsval. Mät förbättringen mot MVP v4 baseline med samma eval-set.

### MVP v5 - Orkestrering & Analys (Complete Lakehouse)
- Airflow DAGs knyter ihop v1–v3 (serving-lagret i v4 körs separat som egen tjänst, inte som DAG-steg)

- Gold-marts via dbt + DuckDB: dokumentation täckning per kurs, snittlängd transkript, etc.

### MVP v6 - Produktionsdeployment
*(Saknades i original roadmappen, en av de tre kärninvesteringarna i hela projektet, får inte falla mellan stolarna bara för att den övas på separat först)*  
- CD till SSH-VM(?), byggd på lärdomar från den separata deployment dry-run

- Reverse proxy + TLS, secrets-hantering, grundläggande monitoring

## Risker

| Risk | Status | Kommentar |
|---|---|---|
| Extraktionskvalitet (PDF) | Delvis de-riskad | En PoC ≠ bevis - testa på bredare/sämre urval innan v2 låses |
| Scope creep (audio/video) | Mitigerad | Exkluderat från v0, 53 transkript räcker |
| Hallucination | Mitigerad via design | Strikt system-prompt + källspårning (MVP v4) |
| **Dataskydd/PII** | **Delvis de-riskad** | Inga riktiga individer identifierbara i output. Fiktiva exempelnamn i kursmaterial okej. Strategi (gliner-multi-pii vs. manuell granskning) ej beslutad - kräver mer utforskning |