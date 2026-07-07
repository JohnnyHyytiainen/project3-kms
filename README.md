
```
project3-kms
├─ .python-version
├─ .github
│  └─ workflows
│     └─ ci.yml
├─ alembic
│  ├─ env.py
│  ├─ README
│  ├─ script.py.mako
│  └─ versions
│     └─ 04a60e3452ef_initial_schema.py
├─ alembic.ini
├─ docker-compose.yml
├─ docs
│  ├─ architecture
│  │  ├─ erd_model.mmd
│  │  ├─ erd_model.png
│  │  ├─ mvp_data_pipeline.png
│  │  └─ overview_kms.mmd
│  ├─ commands_to_have.md
│  ├─ docker_compose_commands.md
│  ├─ file_docs
│  │  ├─ folder_structure_map.mmd
│  │  ├─ folder_structure_map.png
│  │  └─ mvp_v1_docs
│  │     ├─ alembic_model_revision.md
│  │     ├─ boto3_docs_mvp_v1.md
│  │     ├─ config_alembic_docs_mvp_v1.md
│  │     ├─ dependencies_mvp_v1.md
│  │     ├─ docker_compose_docs_mvp_v1.md
│  │     ├─ ingestion_course_mapping_mvp_v1.md
│  │     ├─ postgres_localstack_docs_mvp_v1.md
│  │     └─ S3_LocalStack_docs_mvp_v1.md
│  ├─ project_roadmap.md
│  └─ session_tracking
│     └─ sessions_MvP_v1.md
├─ pyproject.toml
├─ README.md
├─ src
│  └─ kms
│     ├─ config.py
│     ├─ db
│     │  ├─ models.py
│     │  └─ __init__.py
│     ├─ ingestion
│     │  ├─ course_mapping.py
│     │  └─ __init__.py
│     ├─ storage
│     │  ├─ s3_client.py
│     │  └─ __init__.py
│     └─ __init__.py
├─ tests
│  └─ unit
└─ uv.lock

```