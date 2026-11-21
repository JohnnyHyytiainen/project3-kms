# test_agent_instructions.py, script för att testa prompten i kms.generation.agent_instructions
# build_prompt() är en ren funktion i agent_instructions.py scriptet. Fråga och hits in, en str ut som svar.
# Inga attrapper(mocks/stubs), inget nät eller riktig modell behövs här.
#
# A1: Numret framför varje källa är träffens rank och INTE platsen i listan.
# Rank 2 och 5. INTE rank 1 och 2.
# Med rank 1 och 2 ger platsen i listan samma nummer och bugs blir svåra att se.
#

from kms.generation.agent_instructions import build_prompt
from kms.retrieval.search import SearchHit


# Helper-funktion för att skapa mina hits för hand
def create_hit(rank, filename, text):
    """
    A built function for hits. build_prompt() only reads rank, filename and text.
    All the other fields only have to be valid and follow its expected values.
    """
    return SearchHit(
        rank=rank,
        distance=0.1,
        text=text,
        document_id=1,
        chunk_index=0,
        filename=filename,
        source_type="pdf",
        courses=["data_platform"],
        source_location=None,
    )


# ====== Del 1: Tester av prompt instructioner ======
# A1: numret är träffens rank, så att t.ex [5] i svaret pekar mot och på rätt källa.
def test_build_prompt_numbers_sources_by_rank():
    hits = [
        create_hit(2, "slides_medallion.pdf", "Silver holds cleaned data."),
        create_hit(5, "notes_bronze.md", "Bronze holds raw data."),
    ]

    prompt = build_prompt("What is silver?", hits)

    # Varje källa(source) ska vara: [rank] filnamn, radbrytning, texten
    assert "[2] slides_medallion.pdf\nSilver holds cleaned data." in prompt
    assert "[5] notes_bronze.md\nBronze holds raw data." in prompt
    # Frågan ska stå sist EFTER alla källor
    assert prompt.endswith("Question: What is silver?")
