# Experiment script - One time script för att testa verktyget pymupdf4llm och OCR
# INTE del av src/kms/ pipelinen
# Kod: Engelska
# Kommentarer: Svenska
#
# Jämför page.get("text"), baseline som redan är testat.
# Mot -> pymupdf4llm.to_markdown(), kanditat som kanske kan lösa mina problem med bilder i PDFs.

from pathlib import Path

import fitz
import pymupdf4llm

REPO_ROOT = Path("repos_for_data")

# Grupp 2: Skärmdump heavy procedurguider, programmering_inom_dataplatform_development
GROUP_2 = [
    REPO_ROOT
    / "programmering_inom_dataplatform_development"
    / "#0 Installation - PgAdmin with PostgreSQL.pdf",
    REPO_ROOT
    / "programmering_inom_dataplatform_development"
    / "#1 PyCharm - Importing Projects & Dependencies.pdf",
    REPO_ROOT
    / "programmering_inom_dataplatform_development"
    / "#5.5 Data Platform Development - Psycopg3, PostgreSQL & Environment Variables.pdf",
    REPO_ROOT
    / "programmering_inom_dataplatform_development"
    / "#6 Data Platform Development - ETL & ELT, Filetypes (CSV, JSON, PARQUET).pdf",
    REPO_ROOT
    / "programmering_inom_dataplatform_development"
    / "#9 Data Platform Development - Lab Recap & Docker.pdf",
]

# Grupp 3: 100% bild, 0 fonter
GROUP_3 = [
    REPO_ROOT
    / "cloud_databricks_azure_course"
    / "02_databricks_navigation"
    / "slides_what_is_databricks.pdf",
    REPO_ROOT
    / "cloud_databricks_azure_course"
    / "05_bronze_layer"
    / "slides_databricks_de_concepts.pdf",
    REPO_ROOT / "data_modeling_course" / "02_database_types" / "NoSQL_examples.pdf",
]


def compare_one(path: Path) -> tuple[int, int, int]:
    """
    Runs both extraction paths on one PDF, returns (pages, before_chars, after_chars).

    page_cunks=True on the pymupdf4llm call is NOT optional here, without it the whole
    document collapses into one string and the page number is lost, which breaks the
    same source_location contract ExtractedPage already protects.
    """
    doc = fitz.open(path)
    before = sum(len(page.get_text("text")) for page in doc)
    n_pages = len(doc)
    doc.close()

    md_pages = pymupdf4llm.to_markdown(path, page_chunks=True)
    after = sum(len(p["text"]) for p in md_pages)

    return n_pages, before, after


# ===== Kör över BÅDA grupperna, skriver en sammanfattningstabell över det hela =====
print(f"{'fil':<55s} {'sidor':>6s} {'före':>8s} {'efter':>8s} {'faktor':>8s}")
for label, files in [("Grupp 2", GROUP_2), ("Grupp 3", GROUP_3)]:
    print(f"--- {label} ---")
    for path in files:
        n_pages, before, after = compare_one(path)
        factor = after / before if before else float("inf")
        print(
            f"{path.name[:55]:<55s} {n_pages:>6d} {before:>8d} {after:>8d} {factor:>7.1f}x"
        )
