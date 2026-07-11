# ROADMAP - Projekt 3 (arbetsnamn TBD)
*Senast uppdaterad: 2026-07-11*
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
- [] `docs/project_roadmap.md` - Uppdatera och stycka upp MVP v2 i samma stil som MVP v1

### MVP v2 - Extraktion & Transformation (Silver), HÖGST risk, bör göras tidigt
- ETL läser PENDING filer från S3

- Textextraktion: .pdf (PyMuPDF) + .md (inklusive 53 transkript)

- Chunking-logik (semantiska block)

- Parquet till Silver, status uppdateras via ORM

- *Notera: en PoC är en datapunkt, inte ett bevis. Fortsatt validering på bredare/sämre PDF selection innan v2 kan anses som klar.*

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