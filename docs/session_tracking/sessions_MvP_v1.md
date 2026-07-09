# Session tracking notes for MvP v1
*Started: 2026-07-02*
*Completed:*
---
**Thursday 2026-07-02**
*Goals for today:*
- Setup repo and folder structure
    - **Done**

---
**Friday 2026-07-03**
*Goals for today:*

- Add correct deps needed for repo
    - **Done**

- Start to setup `docker-compose.yml`, `LocalStack S3` and `PostgreSQL`
    - **Done**

- Start compiling own written docs regarding setup for `Docker, LocalStack S3 and Postgres` with good to have quick commands and reasoning behind for project report later on.
    - **Done**

- Setup `CI-Pipe` with linting and formatting using `github-actions`
    - **Done**

- Write `config.py`-theory docs regarding `alembic`
    - **Done**

- Write `src/kms/config.py`-script
    - **Done**

- Start working on `db/models.py`, the most central file that everything else is built upon.
    - **Done**

- Write docs regarding `models.py`
    - **Done**
---

**Monday 2026-07-06**
*Goals for today:*

- Write docs regarding `boto3`-deps
    - **Done**

- Write docs regarding `src/kms/storage/s3_client.py` and S3/LocalStack.
    - **Done**

- Update `config.py`-script to include AWS values
    **Done**

- Implement `s3_client.py` script
    - **Done**

---

**Tuesday 2026-07-07**
*Goals for today*

- Write brief course mapping docs
    - **Done**

- Write and implement  ingestion `course_mapping.py`script
    **Done**

---
**Wednesday 2026-07-08**
*Goals for today:*

- Write own docs regarding `src/kms/ingestion/ingest.py`-script. The most critical script in MVP V1, the actual file that connects the rest of my scripts.
    - **Done**

- Implement script and write the code for `ingest.py`
    - **Done**

---

**Thursday 2026-07-09**
*Goals for today:*

- Docs regarding unit testing `tests/unit/test_ingestion.py`
    - **Done**

- Write and implement testing script to test logic in `src/kms/ingestion/ingest.py` script
    - **Done**

- Expand on docs regarding testing and implementation into `CI/CD-Pipeline` and its importance.
    - *Ongoing*

- Update `ci.yml` script to include `test_ingestion.py`-logic for every PR before a merge to main
    *ongoing*

