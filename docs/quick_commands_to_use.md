# quick and easy commands to use when needed

- To run tests locally:
    - `uv run pytest`  
    
- Running tests with just loading bar with fails showing up:
    - `uv run pytest -q`


- To start API layer:
    - `uv run uvicorn kms.api.main:app --reload`

- Linting + formatting:
    - `uv run ruff check .`
    - `uv run ruff format --check .`

- Start API 
    - `uv run uvicorn kms.api.main:app --reload`