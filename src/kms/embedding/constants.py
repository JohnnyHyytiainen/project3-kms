# constants.py - Embeddingens fakta på ETT ställe
# Kod: Engelska
# Kommentarer: Svenska

"""
Facts about the embedding provider, the model and the index.

Used by and imported by the embedding step, the reconciliation, the rebuild and the search.
Values here are supposed to change together with the INDEX and not per environment.
Changing EMBEDDING_MODEL or EMBEDDING_DIM menas a FULL rebuild,
otherwise questions and corpus are compared on two DIFFERENT maps.
Values that change per environment such as keys, hosts etc will live in config.py.
"""

# ===== Leverantören: Grunden.ai =====
GRUNDEN_BASE_URL = "https://api.grunden.ai/v1"
BATCH_SIZE = 32  # Grundens uppmätta tak per anrop (422 err om större)
MAX_RETRIES = 5  # Skydd och MAX antal försök

# ===== Modellen: Corpus och fråga som MÅSTE embeddas med samma =====
EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 1024  # låser Chroma samlingen från första skrivningen.

# ===== Indexet: samlingen i Chroma =====
COLLECTION_NAME = "kms_chunks"
