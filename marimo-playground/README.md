# marimo-playground

A [marimo](https://marimo.io) notebook playground for exploring Unity Catalog.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.
`pyproject.toml` has one dependency group per notebook image: `delta` (the
default, Spark 4.2) and `iceberg` (Spark 4.1 + PyIceberg). They conflict, so the
virtual environment holds one at a time.

```bash
# From the repo root: install the Delta group, then clean uv.lock for CI
just sync
# ...or the Iceberg group instead
just sync-iceberg
```

Behind a PyPI proxy, uv writes the proxy's URLs into `uv.lock` on every sync.
`just sync` rewrites them back to public PyPI so the GitHub build can use the
lock; run `just clean-lock` yourself after any other `uv` command that changes
it. After editing `pyproject.toml`, run `just lock`, which also re-exports
`requirements.lock` and `requirements-iceberg.lock` (the hash-pinned files the
Docker images install).

## Running Notebooks

Notebooks live in the `notebooks/` directory. Use `uv run --frozen` so marimo
picks up the project's virtual environment without re-locking `uv.lock`.

```bash
# Open an existing notebook
uv run --frozen marimo edit notebooks/unitycatalog-delta.py

# Create a new notebook
uv run --frozen marimo edit notebooks/my_new_notebook.py

# Run a notebook as a read-only app
uv run --frozen marimo run notebooks/unitycatalog-delta.py

# Iceberg notebooks (after `just sync-iceberg`)
SPARK_VERSION=4.1 uv run --frozen --no-default-groups --group iceberg marimo edit notebooks/iceberg/
```
