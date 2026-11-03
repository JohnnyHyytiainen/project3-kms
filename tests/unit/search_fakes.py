# search_fakes.py - attrapper(mocks/stubs) för sökvägen, delas mellan retrieval/ och api/
#
# Kod: Engelska
# Kommentarer: Svenska
#
# Används av retrieval/test_retrieval_search.py + api/test_api.py scripten.
# INGEN TESTFIL - filen börjar ej på test_*, så att pytest samlar aldrig in filen och kör den.
# Ska INTE ligga i conftest.py - conftest är config för det ALLA tester behöver.
# Vanlig modul-import tack vare pythonpath i .toml filen.

import uuid
from types import SimpleNamespace

from kms.db.models import Chunk, Course, Document, DocumentStatus, SourceFile


# ====== Testdubbletter: attrapper(mocks) för Grunden, Chroma och sessionen ======
class FakeEmbeddings:
    """Stand-in for client.embeddings. Records every call, returns one vector per text."""

    def __init__(self, vector=(0.1, 0.2, 0.3)):
        self.calls = []
        # Exakt samma vector för varje text. Uppstarts kontroll kräver korpusens längd
        self.vector = list(vector)

    def create(self, *, model, input, encoding_format):
        self.calls.append(
            {"model": model, "input": input, "encoding_format": encoding_format}
        )
        # Samma form som Grundens svar: resp.data[i].index och resp.data[i].embedding
        data = [
            SimpleNamespace(index=i, embedding=self.vector) for i, _ in enumerate(input)
        ]
        return SimpleNamespace(data=data)


class FakeClient:
    """Stand-in for the OpenAI client. Only .embeddings is used, by search() and at startup."""

    def __init__(self, **kwargs):
        self.embeddings = FakeEmbeddings(**kwargs)


class FakeCollection:
    """Stand-in for the Chroma collection. Answers query() with fixed ids and distances."""

    def __init__(self, ids, distances):
        self.ids = ids
        self.distances = distances
        self.queries = []  # Varje fråga sparas så att testet kan granska den.

    def query(self, *, query_embeddings, n_results, include):
        self.queries.append(
            {
                "query_embeddings": query_embeddings,
                "n_results": n_results,
                "include": include,
            }
        )
        # En lista per fråga, precis som ChromaDB. search() skickar alltid EN fråga
        return {"ids": [self.ids], "distances": [self.distances]}


class FakeResult:
    """What session.execute() returns. search() only calls .scalars() on it."""

    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return iter(self.rows)


class FakeSession:
    """
    Stand-in for an SQLAlchemy session.
    execute() ignores the statement and hands back the rows it was given, in that order.
    """

    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement):
        return FakeResult(self.rows)


def make_chunk(chunk_index, content, *, course_tags=("data_platform",)):
    """
    A real Chunk with a real Document and SourceFiles, never added to a session.
    search() reads exactly the same attributes as in a real run.
    """
    document = Document(
        id=1,
        filename="slides_medallion.pdf",
        source_type="pdf",
        status=DocumentStatus.EMBEDDED,
    )
    # Kurserna går samma väg som dom gör i databasen: source_files -> courses
    document.source_files = [
        SourceFile(course=Course(course_tag=tag)) for tag in course_tags
    ]
    return Chunk(
        chunk_index=chunk_index,
        content=content,
        vector_id=uuid.uuid4(),
        source_location={"page": chunk_index + 1},
        document=document,
    )
