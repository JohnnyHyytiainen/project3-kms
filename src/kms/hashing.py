# hashing.py modul - Handlar om innehållets identitet och delas av ingestion och extraction.
# Kod: Engelska
# Kommentarer: Svenska
#
# EN funktion med två anropare.
# ingest.py hashar filer för att ge innehållet sin egna identitet(documents.file_hash).
# extract.py hashar SAMMA fil igen för att kontrollera att filen på disken fortfarande ÄR det innehållet.
#
# Ändras hashreglerna vid t.ex normalisering före hashing ska det ändras HÄR.

import hashlib
from pathlib import Path


# Läser varje fil i 8kb bits för att spara på RAM och skapa unik identifierare för varje fil.
# Skapar unik SHA-256bit hash. Innehållet är menat bli filens identitet.
def compute_file_hash(file_path: Path) -> str:
    """
    SHA-256 hash of files CONTENT (Not the filename or filepath).

    Function reads the file in 8192 byte chunks rather than loading the
    ENTIRE file into memory using .read_bytes(). This makes no
    noticeable difference for small .md files but would
    matter significantly if a PDF were 500 MB. A RAM cost I dont want
    for something as simple as a fingerprint.

    Does NOT catch errors here, exceptions like PermissionError are allowed to propagate by design
    the one using this function decides how to handle a read error,
    not the function itself, which is intended solely for hashing.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
