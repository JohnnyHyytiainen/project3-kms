# Quick cheatsheet for good commands to have:
Quick and easy commands to test functions in python shell in terminal(REPL)

This is best used to quickly test pure and isolated python functions without needing to start infrastructure such as `Docker`, `S3` or `Databases`.

To open up python shell in terminal I just need to write:
- `python` in terminal.

---
### Testing src/kms/ingestion/course_mapping script
To test my `get_course_tag`-function in my `course_mapping`-script:
- `from kms.ingestion.course_mapping import get_course_tag`
- `get_course_tag("python_course")`

---
### Testing src/kms/ingestion/ingest script
To test both my `build_file_record` and `compute_file_hash`-functions in my `ingest.py` script:
1) Import my tools with:
    - ` from pathlib import Path `
    - ` from kms.ingestion.ingest import build_file_record, compute_file_hash `

2) Set up my testing paths (replace `README.md` with the file I want to test in `repos_for_data` folder)
    - ` repos_root = Path("repos_for_data") `
    - ` test_file = repos_root / "python_course" / "README.md" `

3) Test to generate a `S3-key` AND metadata from path
    - ` record = build_file_record(test_file, repos_root) `
    - ` record `
        - Expected output:
        - `DiscoveredFile(local_path=WindowsPath(...), filename='README.md', s3_key='python/python_course/README.md', course_tag='python', source_type='markdown')`

4) Test chunk-hashing logic (Generate a `SHA-256` fingerprint)
    - ` min_hash = compute_file_hash(test_file) `
    - ` min_hash `
        - Expected output:
        - 'd3a0a0ce48749af3e56949a113fd9161eef213843eb3eebfb1701a7946ec44ae'

---

