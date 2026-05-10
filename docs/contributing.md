# Contributing

## Setup

```bash
uv sync --all-packages
```

## Checks

```bash
uv run ruff check .
uv run mypy .
uv run pytest --cov=components --cov-report=term-missing
uv run mkdocs build --strict
```

## Generated Client

Regenerate `chat_client_service_api_client` whenever the FastAPI OpenAPI schema changes.

## Documentation

Update:

- the root `README.md`
- the component README for each changed package
- the mkdocs pages under `docs/`
