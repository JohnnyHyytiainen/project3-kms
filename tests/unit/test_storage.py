# test_storage.py. Unit tester för parquet_writer.py, botten av testpyramiden
# Kod: Engelska
# Kommentarer: Svenska
# ====================
# Ingen Docker, ingen LocalStack, ingen DB behövs för NÅGOT av testerna.
# parquet_writer.py är "dum" och tar endast emot primitiva datatypes (int, str, floats etc)
# och tar aldrig emot ORM objects. HUR/VAD gränserna är det som gör unit testsa möjliga här.
#
# Testerna är delade i 2 delar.
#
# Del 1: _build_chunk_table(), enbart en ren funktion.
# A1: document_id stämplas på VARJE enskild rad
# B1: kolumnnamn + typer matchar deklarationen (oberoende andrahandsåsikt)
# C1: samtliga fält är deklarerade not null
# D1: source_location JSON-serialiseras och överlever roundtrip
# E1: chunkarnas ordning och värden bevaras rad för rad
# F1: tom lista ger 0 rader med intakt schema.
# G1: fel datatype i en kolumn avvisas av det explicita schemat
#
# Del 2: write_chunks_to_parquet() - skalet, S3 ersatt av en spion
# A2: bucket_name och s3_key vidarebefordras HELT oförändrade
# B2: den uppladdade filen är läsbar Parquet med korrekt schema och data
# C2: ingen permanent fil lämnas kvar på disk
# D2: null document_id kastar OCH ingen uppladdning sker
#
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from kms.extraction.chunker import TextChunk
from kms.storage.parquet_writer import _build_chunk_table, write_chunks_to_parquet


# === Förväntningar ===
# PARQUET_SCHEMA importeras INTE hit.
EXPECTED_COLUMNS = [
    "document_id",
    "chunk_index",
    "content",
    "source_location",
    "char_count",
]
EXPECTED_TYPES = ["int64", "int64", "string", "string", "int64"]

# parquet_writer får aldrig anropa något på klient, enbart skicka den vidare.
SENTINEL_CLIENT = object()

BUCKET = "kms-test-bucket"
S3_KEY = "silver/python/python_course/README.md.parquet"


# ====== FIXTURES ======
@pytest.fixture
def sample_chunks() -> list[TextChunk]:
    """
    Three chunks where two of them are sharing the same source_location.

    Identical source_location on chunk 0 and 1 is supposed to mirror real output,
    where every chunk from the SAME PDF page carries the SAME dict.
    """
    return [
        TextChunk(
            chunk_index=0,
            content="Data engineering is about pipelines.",
            source_location={"page": 7, "source_type": "pdf"},
            char_count=36,
        ),
        TextChunk(
            chunk_index=1,
            content="Idempotency means safe re-runs.",
            source_location={"page": 7, "source_type": "pdf"},
            char_count=31,
        ),
        TextChunk(
            chunk_index=2,
            content="Columnar storage groups values by column.",
            source_location={"page": 8, "source_type": "pdf"},
            char_count=41,
        ),
    ]


@pytest.fixture
def upload_spy(monkeypatch) -> list[dict]:
    """
    Replaces upload_file with a "spy" recording every call.

    Patch target is kms.storage.parquet_writer.upload_file and NOT
    kms.storage.s3_client.upload_file.

    parquet_writer does 'from ... import upload_file',
    binding the function into its OWN namespace.
    Patching the origin module leaves that binding untouched.

    File bytes are read INSIDE the fake call. The temp directory is deleted
    the moment write_chunks_to_parquet exits its with block, so reading
    afterwards is impossible.
    """
    calls: list[dict] = []

    def fake_upload_file(client, local_path, bucket_name, key) -> None:
        calls.append(
            {
                "client": client,
                "local_path": local_path,
                "bucket_name": bucket_name,
                "key": key,
                "data": Path(local_path).read_bytes(),
            }
        )

    monkeypatch.setattr(
        "kms.storage.parquet_writer.upload_file",
        fake_upload_file,
    )
    return calls


# ====== Del 1: _build_chunk_table(), ren funktion ======
# =======================================================
# A1
def test_document_id_is_stamped_on_every_row(sample_chunks):
    """Test A1: TextChunk should know nothing about its document.
    This function is supposed to add it."""
    table = _build_chunk_table(sample_chunks, document_id=42)

    assert table.num_rows == 3
    assert table.column("document_id").to_pylist() == [42, 42, 42]


# B1
def test_table_uses_declared_columns_and_types(sample_chunks):
    """
    Test B1: Independant second opinion on the schema.

    Litteraly written out instead of compared against PARQUET_SCHEMA,
    comparing to the constant it would still pass if the constant itself was changed incorrectly.
    """
    table = _build_chunk_table(sample_chunks, document_id=42)

    assert table.schema.names == EXPECTED_COLUMNS
    assert [str(t) for t in table.schema.types] == EXPECTED_TYPES


# C1
def test_all_fields_are_declared_non_nullable(sample_chunks):
    """
    Test C1: Every field must be declared non nullable.

    pa.table() does NOT enforce this flag since its only metadata at this stage.
    pq.write_table() enforces it, verified later in the D2 test.
    """
    table = _build_chunk_table(sample_chunks, document_id=42)

    assert [field.nullable for field in table.schema] == [False] * 5


# D1
def test_source_location_survives_json_roundtrip(sample_chunks):
    """
    Test D1: The dict is flattened to JSON string on write.

    Parquets strict per column typing does not tolerate a free dict
    in the same the way that Postgres JSONB does.

    Whatever goes in must come back out IDENTICAL.
    """
    table = _build_chunk_table(sample_chunks, document_id=42)
    stored = table.column("source_location").to_pylist()

    assert stored[0] == '{"page": 7, "source_type": "pdf"}'
    assert [json.loads(s) for s in stored] == [c.source_location for c in sample_chunks]


# E1
def test_chunk_values_and_order_are_preserved(sample_chunks):
    """
    Test E1: Testing row order.
    The elements in chunk_index 0,1,2 MUST stay 0,1,2
    """
    table = _build_chunk_table(sample_chunks, document_id=42)

    assert table.column("chunk_index").to_pylist() == [0, 1, 2]
    assert table.column("content").to_pylist() == [c.content for c in sample_chunks]
    assert table.column("char_count").to_pylist() == [36, 31, 41]


# F1
def test_empty_chunk_list_returns_empty_table_with_intact_schema():
    """
    Test F1: chunk_document() returns [],
    when every section falls below MIN_CHUNK_SIZE.
    A real path, not a hypothetical path.

    Documents CURRENT behaviour: no crash, zero rows, schema is intact.
    """
    table = _build_chunk_table([], document_id=42)

    assert table.num_rows == 0
    assert table.schema.names == EXPECTED_COLUMNS
    assert [str(t) for t in table.schema.types] == EXPECTED_TYPES


# G1
def test_wrong_column_type_is_rejected_by_explicit_schema():
    """
    Test G1: The entire point of declaring PARQUET_SCHEMA by hand,
    and not letting pyarrow infer it.

    With inference this row would produce a string-typed chunk_index column.

    The failure would show up later as a schema mismatch when DuckDB unions the silver layer.
    """
    broken = [
        TextChunk(
            chunk_index="noll",  # Menat att vara int och inte en str
            content="x" * 60,
            source_location={"page": 1},
            char_count=60,
        )
    ]

    with pytest.raises(pa.ArrowInvalid):
        _build_chunk_table(broken, document_id=42)


# ======     Del 2: write_chunks_to_parquet()     ======
# ======================================================
# A2
def test_bucket_and_key_are_forwarded_unchanged(sample_chunks, upload_spy):
    """
    Test A2: The function receives a fully built key and should/must NEVER touch it.

    Proves the HOW/WHAT boundary,
    no course_tag parsing,
    no prefix building,
    no filename derivation happens inside this module.
    """
    write_chunks_to_parquet(
        chunks=sample_chunks,
        document_id=42,
        s3_key=S3_KEY,
        client=SENTINEL_CLIENT,
        bucket_name=BUCKET,
    )

    assert len(upload_spy) == 1
    assert upload_spy[0]["key"] == S3_KEY
    assert upload_spy[0]["bucket_name"] == BUCKET
    assert upload_spy[0]["client"] is SENTINEL_CLIENT


# B2
def test_uploaded_bytes_are_readable_parquet(sample_chunks, upload_spy):
    """
    Test B2: Reads the uploaded bytes back through pyarrow.

    Verifies the footer story end to end: the schema travels INSIDE the
    file, so a reader needs no external DDL to recover the data types.
    """
    write_chunks_to_parquet(
        chunks=sample_chunks,
        document_id=42,
        s3_key=S3_KEY,
        client=SENTINEL_CLIENT,
        bucket_name=BUCKET,
    )

    table = pq.read_table(pa.BufferReader(upload_spy[0]["data"]))

    assert table.num_rows == 3
    assert table.schema.names == EXPECTED_COLUMNS
    assert [str(t) for t in table.schema.types] == EXPECTED_TYPES
    assert table.column("document_id").to_pylist() == [42, 42, 42]
    assert table.column("content").to_pylist() == [c.content for c in sample_chunks]


# C2
def test_no_permanent_file_is_left_on_disk(sample_chunks, upload_spy):
    """
    Test C2: Verifies the docstring claim literally.

    A real temp file is written, TemporaryDirectory removes both
    the file + its parent directory on exit, including on exceptions.
    """
    write_chunks_to_parquet(
        chunks=sample_chunks,
        document_id=42,
        s3_key=S3_KEY,
        client=SENTINEL_CLIENT,
        bucket_name=BUCKET,
    )

    local_path = Path(upload_spy[0]["local_path"])

    assert not local_path.exists()
    assert not local_path.parent.exists()


# D2
def test_null_document_id_aborts_before_upload(sample_chunks, upload_spy):
    """
    Test D2: The guarantee this design relies on instead of a manual guard.

    document.id is None until SQLAlchemy flushes.
    pq.write_table should refuse to write nulls into a non nullable column,
    so that the exception fires BEFORE-- upload_file is reached.

    No corrupt object SHOULD NEVER EVER reach S3-bucket.

    If a future pyarrow release stops enforcing this, THIS test fails and
    the decision to skip an explicit guard gets revisited with evidence.
    """
    with pytest.raises(pa.ArrowInvalid):
        write_chunks_to_parquet(
            chunks=sample_chunks,
            document_id=None,
            s3_key=S3_KEY,
            client=SENTINEL_CLIENT,
            bucket_name=BUCKET,
        )

    assert upload_spy == []
