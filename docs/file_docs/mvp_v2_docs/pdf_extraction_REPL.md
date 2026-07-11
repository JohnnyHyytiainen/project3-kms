# Docs regarding findings with Python REPL:
När jag testar att att spåra efter "fälla 1" i pdf dokumenten hittar jag en intressant sak. Det är inga isolerade händelser att PDF'er innehåller få tecken. Stora delar av många PDFer innehåller extremt få tecken. Test jag kört i python REPL:


```python
rom pathlib import Path
from kms.extraction.pdf_extractor import extract_pages
from kms.config import settings

THRESHOLD = 120  # tecken per sida i snitt - under detta flaggas dokumentet

for pdf_path in settings.COURSE_REPOS_ROOT.rglob("*.pdf"):
    if ".git" in pdf_path.parts:
        continue
    try:
        pages = extract_pages(pdf_path)
    except Exception as e:
        print(f"[FEL] {pdf_path.relative_to(settings.COURSE_REPOS_ROOT)}: {e}")
        continue
    total_chars = sum(len(p.text) for p in pages)
    avg_per_page = total_chars / len(pages) if pages else 0
    if avg_per_page < THRESHOLD:
        print(f"[LÅGT] {pdf_path.relative_to(settings.COURSE_REPOS_ROOT)}: "
              f"{len(pages)} sidor, {avg_per_page:.0f} tecken/sida i snitt")
```

Resultat är detta:
```
[LÅGT] programmering_inom_dataplatform_development\#0 Installation - PgAdmin with PostgreSQL.pdf: 27 sidor, 53 tecken/sida i snitt  
[LÅGT] programmering_inom_dataplatform_development\#1 PyCharm - Importing Projects & Dependencies.pdf: 18 sidor, 66 tecken/sida i snitt  
[LÅGT] programmering_inom_dataplatform_development\#5.5 Data Platform Development - Psycopg3, PostgreSQL & Environment Variables.pdf: 61 sidor, 47 tecken/sida i snitt  
[LÅGT] programmering_inom_dataplatform_development\#6 Data Platform Development - ETL & ELT, Filetypes (CSV, JSON, PARQUET).pdf: 80 sidor, 99 tecken/sida i snitt  
[LÅGT] programmering_inom_dataplatform_development\#9 Data Platform Development - Lab Recap & Docker.pdf: 79 sidor, 94 tecken/sida i snitt  
[LÅGT] AI_engineering_course\03_linear_regression\slides_linear_regression.pdf: 8 sidor, 55 tecken/sida i snitt  
[LÅGT] AI_engineering_course\04_logistic_regression\slides_logistic_regression.pdf: 6 sidor, 47 tecken/sida i snitt  
[LÅGT] AI_engineering_course\05_knn\slides_knn.pdf: 3 sidor, 62 tecken/sida i snitt  
[LÅGT] AI_engineering_course\06_random_forest\slides_random_forest_XG_boost.pdf: 4 sidor, 68 tecken/sida i snitt
[LÅGT] AI_engineering_course\07_pydantic\slides_LLM_theory.pdf: 6 sidor, 51 tecken/sida i snitt
[LÅGT] AI_engineering_course\06_random_forest\extra\slides_decision_tree.pdf: 4 sidor, 53 tecken/sida i snitt
[LÅGT] AI_engineering_four_weeks_course\03_gemini\slides_LLM_theory.pdf: 6 sidor, 51 tecken/sida i snitt
[LÅGT] ai_intro_course_two_weeks\a1_llm_theory\slides_LLM_theory.pdf: 6 sidor, 51 tecken/sida i snitt
[LÅGT] cloud_databricks_azure_course\02_databricks_navigation\slides_what_is_databricks.pdf: 7 sidor, 0 tecken/sida i snitt
[LÅGT] cloud_databricks_azure_course\04_medallion_architecture\slide_medallion_architecture.pdf: 5 sidor, 0 tecken/sida i snitt
[LÅGT] cloud_databricks_azure_course\05_bronze_layer\slides_databricks_de_concepts.pdf: 11 sidor, 0 tecken/sida i snitt
[LÅGT] data_engineering_course\05_extract_load_api_dlt\slides_dlt_api.pdf: 2 sidor, 114 tecken/sida i snitt
[LÅGT] data_modeling_course\02_database_types\NoSQL_examples.pdf: 5 sidor, 0 tecken/sida i snitt
[LÅGT] data_warehouse_course\07_extract_load_api_dlt\slides_dlt_api.pdf: 2 sidor, 112 tecken/sida i snitt
[LÅGT] duckdb_sql_analytics_course\07_grouping_data\slides_grouping_data.pdf: 4 sidor, 114 tecken/sida i snitt
[LÅGT] llmops_course\03_LLM_intro\slides_LLM_theory.pdf: 6 sidor, 51 tecken/sida i snitt
```