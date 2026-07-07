# Ingestion script - course_mapping
# Kommentarer: Svenska
# Kod: Engelska


# Nyckel: exakt samma foldernamn på disk
# Värde: kort course_tag som används i S3 key name space - {course_tag}/{repo_name}/{relative path}
REPO_TO_COURSE_TAG: dict[str, str] = {
    "AI_engineering_course": "ai_engineering",
    "AI_engineering_four_weeks_course": "ai_engineering_4wk",
    "ai_intro_course_two_weeks": "ai_intro_2wk",
    "cloud_databricks_azure_course": "cloud_databricks_azure",
    "data_modeling_course": "data_modeling",
    "data_platform_course": "data_platform",
    "data_visualisation_bi_course": "data_viz_bi",
    "data_warehouse_course": "data_warehouse",
    "data_engineering_course": "data_engineering",
    "duckdb_sql_analytics_course": "sql_analytics",
    "llmops_course": "llmops",
    "programmering_inom_dataplatform_development": "data_platform_development",
    "python_course": "python",
    "youtube_transcripts": "youtube_transcripts",
}


# Funktion för att skapa mina course_tags för varje repo
def get_course_tag(repo_name: str) -> str:
    """
    Looks up the course_tag for a repo name.

    Throws a clear error if repo_name is missing. NOT a silent fallback.
    A new or renamed repo should force a deliberate decision (adding
    a line here), rather than slipping through with the wrong tag.
    """
    try:
        return REPO_TO_COURSE_TAG[repo_name]
    except KeyError:
        raise KeyError(
            f"Unknown repo '{repo_name}' - Add it to REPO_TO_COURSE_TAG in course_mapping.py before ingestion can continue"
        ) from None


TRANSCRIPT_TO_COURSE_TAG: dict[str, str] = {
    # Säkra träffar - kursnamn eller specifik lektionsmapp matchar exakt
    "SQL analytics course with DuckDB - course structure.md": "sql_analytics",
    "SQL analytics course with DuckDB - CRUD operations tutorial.md": "sql_analytics",
    "SQL analytics course with DuckDB - dlt to load sakila data from SQLite into DuckDB.md": "sql_analytics",
    "SQL analytics course with DuckDB - joins concepts.md": "sql_analytics",
    "SQL analytics course with DuckDB - joins with sakila database tutorial.md": "sql_analytics",
    "SQL analytics course with DuckDB - pandas and duckdb (1).md": "sql_analytics",
    "SQL analytics course with DuckDB - pandas and duckdb.md": "sql_analytics",
    "SQL analytics course with DuckDB - Sakila BI dashboard using Evidence (1).md": "sql_analytics",
    "SQL analytics course with DuckDB - Sakila BI dashboard using Evidence.md": "sql_analytics",
    "SQL analytics course with DuckDB - set theory part 2 (using Sakila) (1).md": "sql_analytics",
    "SQL analytics course with DuckDB - set theory part 2 (using Sakila).md": "sql_analytics",
    "SQL analytics course with DuckDB - setup duckdb.md": "sql_analytics",
    "SQL analytics course with DuckDB - strings concepts.md": "sql_analytics",
    "SQL analytics course with DuckDB - strings tutorial.md": "sql_analytics",
    "SQL analytics course with DuckDB - subquery tutorial.md": "sql_analytics",
    "SQL analytics course with DuckDB - views tutorial.md": "sql_analytics",
    "SQL analytics with DuckDB - introduction.md": "sql_analytics",
    "python intro.md": "python",
    "Python fundamentals.md": "python",
    "Python_oop_1.md": "python",
    "pytest unit testing.md": "python",
    "Pydantic fundamentals.md": "python",
    "Packaging in python.md": "python",
    "Terraform setup.md": "cloud_databricks_azure",
    "FastAPI and scikit-learn API connect to streamlit frontend.md": "cloud_databricks_azure",
    "Data platform course structure.md": "data_platform",
    # Osäkra - fallback till samma flata tagg som redan finns i REPO_TO_COURSE_TAG.
    # TODO: Uppgradera raderna nedan till en specifik course_tag i takt med att jag vet mer.
    "An introduction to the vector database LanceDB.md": "youtube_transcripts",
    "API trafiklab (1).md": "youtube_transcripts",
    "API trafiklab.md": "youtube_transcripts",
    "Azure static web app deploy react app.md": "youtube_transcripts",
    "Chat with your excel data - xlwings lite (1).md": "youtube_transcripts",
    "Chat with your excel data - xlwings lite.md": "youtube_transcripts",
    "Course structure for Azure two weeks course.md": "youtube_transcripts",
    "data processing course  structure.md": "youtube_transcripts",
    "data storytelling.md": "youtube_transcripts",
    "dbt modeling snowflake.md": "youtube_transcripts",
    "docker setup windows.md": "youtube_transcripts",
    "Fastapi CRUD app.md": "youtube_transcripts",
    "Hands on regularization.md": "youtube_transcripts",
    "How does LLM work_.md": "youtube_transcripts",
    "Logistic regression hands on with scikit learn.md": "youtube_transcripts",
    "Logistic regression theory.md": "youtube_transcripts",
    "Modern data stack - deploy dockerized dashboard into Azure web app.md": "youtube_transcripts",
    "Modern data stack - dockerize your data pipeline.md": "youtube_transcripts",
    "Modern data stack - using dlt to extract and load api data to snowflake.md": "youtube_transcripts",
    "pandas_read_excel.md": "youtube_transcripts",
    "postgres sink.md": "youtube_transcripts",
    "Pydantic with gemini to structure output in a much neater way.md": "youtube_transcripts",
    "pydanticAI chatbot.md": "youtube_transcripts",
    "PydanticAI fundamentals - outputting structured pydantic model.md": "youtube_transcripts",
    "Serving PydanticAI Gemini Model with FastAPI Tutorial (1).md": "youtube_transcripts",
    "Serving PydanticAI Gemini Model with FastAPI Tutorial.md": "youtube_transcripts",
    "XGBoost hands on tutorial for classification.md": "youtube_transcripts",
}


def get_transcript_course_tag(filename: str) -> str:
    """
    Looks up the course_tag for a transcript file based on the filename.

    Same pattern as get_course_tag(): explicit dictionary, raises KeyError on failure.
    The difference: the table is already complete for all 53 known filenames (either
    a specific tag or the intentional "youtube_transcripts" fallback).
    An unknown filename therefore implies that I was sent additional transcripts
    since the last update, not that something was overlooked.
    """
    try:
        return TRANSCRIPT_TO_COURSE_TAG[filename]
    except KeyError:
        raise KeyError(
            f"Unknown transcript '{filename}' - add it to TRANSCRIPT_TO_COURSE_TAG "
            f"in course_mapping.py before ingestion can continue"
        ) from None
