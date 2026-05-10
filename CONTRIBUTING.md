# Contributing Guide

## Setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/sq6111/CS-GY-9223-Open-Source
cd CS-GY-9223-Open-Source
uv sync --all-packages
```

## Workflow

- Branch from `Hw2` for HW2 work.
- Keep commit history small and reviewable before opening the PR.
- Regenerate `chat_client_service_api_client` whenever the FastAPI OpenAPI contract changes.

## Required Checks

```bash
uv run ruff check .
uv run mypy .
uv run pytest --cov=components --cov-report=term-missing
uv run mkdocs build --strict
```

## Generated Client Regeneration

```bash
uv run python -c "from chat_client_service.main import app; import json, pathlib; pathlib.Path('openapi-chat-client-service.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
uv run openapi-python-client generate --path openapi-chat-client-service.json --config openapi-python-client-config.yml --meta uv --output-path components/chat_client_service_api_client --overwrite
```

## Quality Expectations

- `mypy` runs in strict mode.
- `ruff` must pass on handwritten code.
- Coverage must stay at or above the `90%` threshold in the root `pyproject.toml`.
- Component READMEs and mkdocs pages must be updated with code changes.
