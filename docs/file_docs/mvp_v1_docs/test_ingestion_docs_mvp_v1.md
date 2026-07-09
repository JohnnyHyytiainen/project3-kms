# Docs regarding testing of ingestion script and implementation in CI pipe
*Written 2026-07-09*

Reasoning behind building my first tests towards my ingestion script is because the ingest script is the closest script to my data source, it is about as far upstream one can come before getting in contact with the data itself.

### The 'testing pyramid'
The *testing pyramid* is a framework used in software development made to create a balanced mix of automated tests. Basically what that means is that it includes writing many small and fast tests at the bottom layer of the pyramid and slower tests the further up the pyramid you scale. This will save time and catch pesky bugs faster. If you think of the pyramid in three sections it could look something like this;

1) **Unit tests, the bottom of the pyramid**. Unit testing here are supposed to be fast and check the smallest parts of my code, individual functions, classes or methods in isolation. These tests are "supposed" to make up the majority of the tests and the cost of them is low in writing time and fixing time.

2) **Integration tests, the middle of the pyramid**. The integration tests are supposed to check how different parts/modules of my codebase works together. They are here to make sure all the pieces can talk to each other correctly before entering production. They make up the second biggest part of the pyramid, they take longer time to run compared to the unit tests but are the next step in testing.

3) **End-to-end(E2E) or UI tests, the top of the pyramid**. The E2E tests *verify* the entire platform/application. They are supposed to simulate a real user using your platform/app/product. These tests are slow and take the longest time to run and the cost for them are the most expensive and fragile. Lets say if a button might have changed position in the dashboard or in the UI they will break.
---

## Data testing pyramid
With these 3 steps above you have an entire testing pyramid from the software development perspective. There are several different types of testing pyramids. There is for example a data testing pyramid that is devided into 4 steps.

1) **Data Quality**. This bottom layer tests the accuracy and consistency of your data and make the foundation. These run against individual fields and values, they are fast and targeted and make up the LARGEST share of a test suite, when *ONE* fails you're supposed to know exactly which column or metric to investigate.

2) **Structural**. This second layer tests and checks the data schemas and tables. These tests operate at the `DATABASE`-level. A schema check examines for example an entire table at once, and *not* just a single column. The scope might be wide but these checks still stay cheap and fast to run(Thank the DB engine gods!) which is why they sit just above the most `granular` checks rather than higher up in the pyramid.

3) **Functional**. This third layer tests your business logic. These checks are meant to validate the data transformation logic and business rules. What that means is that they need to run against already processed data rather than `SSOT`/`Bronze`/`Raw data`. They take longer to set up and often requires more domain knowledge to write and to write well.

4) **ETL & Migration**. This top layer is supposed to test the entire pipeline from end-to-end. These tests span across multiple systems and validate the full movement of data from source to destination (From `SSOT raw data` all the way up to your aggregated and ready to use in the `serving layer`). These tests are the *most* resource intensive checks and are typically run after a load completes or during a migration project rather than on *every* pipeline run.

(Source; https://soda.io/blog/practical-guide-data-testing-methods-tools-best-practices)

---

## Building my own testing pyramid
I will first implement testing of my ingestion logic in this project and go the route of several fast and isolated tests, fewer and slower integration tests in the middle and a few E2E tests at the top since I have only implemented the first ingestion script in my pipeline. 

To do this i will replace real infrastructure with test doubles, a pattern im already familiar with without even knowing it. `LocalStack` **IS** a test double for `S3` but on an `infrastructure level`(An entirely faked service within a container). For my first testing(2026-07-09) I will use 2 variants/phases.

- Phase 1:  `SQLite in memory` will replace `Postgres`.
- Phase 2: `MagicMock` will replace my `S3`-client.

```mermaid
---
config:
  theme: neo-dark
---
flowchart TB
    subgraph PHASE1["Fas 1, rena funktioner, bara lokalt filsystem"]
        T1["test_is_supported_file"]
        T2["test_walk_source_files"]
        T3["test_build_file_record"]
        T4["test_compute_file_hash"]
        TMP["tmp_path: riktig temp mapp från pytest"]
        T2 --> TMP
        T3 --> TMP
        T4 --> TMP
    end

    subgraph PHASE2["Fas 2, statefulla funktioner, test doubles ersätter infra"]
        T5["test_load_existing_hashes"]
        T6["test_ingest_one_file: 5 scenarier"]
        SQLITE["SQLite in-memory: ersätter Postgres"]
        MOCK["MagicMock: ersätter S3-klienten"]
        T5 --> SQLITE
        T6 --> SQLITE
        T6 --> MOCK
    end

    PHASE1 -. "samma två fas mönster som ingest.py scriptet själv." .-> PHASE2
```