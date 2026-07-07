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
