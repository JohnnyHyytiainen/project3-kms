# parquet_writer.py - Script för att användas av extract.py
# Kod: Engelska
# Kommentarer: Svenska
#
# Tunn wrapper runtomkring PyArrow som ska serialisera mina chunks till Parquet och sen
# ladda upp till S3-bucket. Dumt script - Vet endast HUR den ska skriva en parquet fil
# Ingenting mer, ingenting mindre.

import json
import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from kms.extraction.chunker import TextChunk
from kms.storage.s3_client import upload_file


# Bestämmer EGET explicit schema. PyArrow ska inte få välja åt mig.
# source_location är extremt viktig, den ska vara en fri dict.
# Serialiseras till JSON sträng för att säkerställa stabil columntype oavsett form på dict.

# PyArrow Schema:
PARQUET_SCHEMA = pa.schema(
    [
        pa.field("document_id", pa.int64()),
        pa.field("chunk_index", pa.int64()),
        pa.field("content", pa.string()),
        pa.field("source_location", pa.string()),
        pa.field("char_count", pa.int64()),
    ]
)


# Clean transformation funktion, ingenting med I/O - Ger funktionen fixtures direkt.
# Pivat funktion FAAFO (F around and find out)
def _build_chunk_table(chunks: list[TextChunk], document_id: int) -> pa.Table:
    """
    Converts a row based list of TextChunks into
    column based pyarrow Table.

    document_id is added to EVERY row.
    TextChunk object itself intentionally contains,
    no information about which document it belongs to.
    """
    return pa.table(
        {
            "document_id": [document_id] * len(chunks),
            "chunk_index": [c.chunk_index for c in chunks],
            "content": [c.content for c in chunks],
            "source_location": [json.dumps(c.source_location) for c in chunks],
            "char_count": [c.char_count for c in chunks],
        },
        schema=PARQUET_SCHEMA,
    )


# Funktion för att skriva mina chunks till Parquet och ladda upp till S3-Bucket
def write_chunks_to_parquet(
    chunks: list[TextChunk],
    document_id: int,
    s3_key: str,
    client,
    bucket_name: str,
) -> None:
    """
    Serializes document chunks to .parquet and uploads to S3-bucket with given key.

    s3_key arrives built fully. Function NEVER constructs,
    paths from course_tags OR filenames.
    Same HOW and not WHAT logic as s3_client.py.

    Local file is a tempfile, cleaned up automatically.

    No permanent file on disk is created.
    """
    table = _build_chunk_table(chunks, document_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = Path(tmp_dir) / "chunks.parquet"
        pq.write_table(table, local_path)
        upload_file(client, str(local_path), bucket_name, s3_key)
