# test_hashing.py - Unit tester för hashing.py
# Kod: Engelska
# Kommentarer: Svenska

import hashlib

import pytest

from kms.hashing import compute_file_hash


# ===== compute_file_hash =====
# Tester för att kolla hashing logiken
# utf-8 encoding EXPLICIT för att write_text() inte ska bero på lokalt OS.
# Samma windows-Linux problem som .as_posix()
def test_compute_file_hash_matches_manual_sha256(tmp_path):
    file_path = tmp_path / "known.md"
    content = "known content for hash tests"
    file_path.write_text(content, encoding="utf-8")

    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()

    assert compute_file_hash(file_path) == expected


# OSError ska spridas vidare, funktionen fångar det INTE av design
def test_compute_file_hash_raises_when_file_missing(tmp_path):
    missing = tmp_path / "finns_inte.md"

    with pytest.raises(OSError):
        compute_file_hash(missing)
