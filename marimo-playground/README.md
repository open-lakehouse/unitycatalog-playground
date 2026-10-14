# marimo-playground

A [marimo](https://marimo.io) notebook playground for exploring Unity Catalog.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies (from the repo root), then clean uv.lock for CI
just sync
```

Behind a PyPI proxy, uv writes the proxy's URLs into `uv.lock` on every sync.
`just sync` rewrites them back to public PyPI so the GitHub build can install
from the lock; run `just clean-lock` yourself after any other `uv` command that
changes it.

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
```
