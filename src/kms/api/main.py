# main.py - KMS servering, själva FastAPI appen
# Kod: Engelska
# Kommentarer: Svenska

"""
Serving layer for the KMS. The FastAPI app lives here and no where else.
Step 1: Only the GET /health endpoint to prove that the process starts,
that the kms package imports and that a request gets an answer.
"""

from fastapi import FastAPI

# Appen ska startas EN GÅNG på modulnivå. Uvicorn letar upp den via 'kms.api.main:app'

app = FastAPI(
    title="KMS platform",
    description="Search over the course material. Sources first, no generation at the moment.",
)


# Använder def och inte async def - Sköning i nästa steg anropar blockerade klienter:
# SQLAlchemy, openAI och Chroma. FastAPI kör vanliga def i en trådpool så att en långsam
# sökning inte blockerar alla andra anrop.
@app.get("/health")
def health_endpoint() -> dict[str, str]:
    """
    Endpoint for liveness only. Prove that process is up and answers.
    Says NOTHING regarding Postgres, Chroma or Grunden.ai.
    """
    return {"status": "ok"}
