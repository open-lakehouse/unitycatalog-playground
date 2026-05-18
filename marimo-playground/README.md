# marimo-playground

A [marimo](https://marimo.io) notebook playground for exploring Unity Catalog.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync
```

## Running Notebooks

Notebooks live in the `notebooks/` directory. Use `uv run` so marimo picks up the project's virtual environment.

```bash
# Open an existing notebook
uv run marimo edit notebooks/unitycatalog-delta.py

# Create a new notebook
uv run marimo edit notebooks/my_new_notebook.py

# Run a notebook as a read-only app
uv run marimo run notebooks/unitycatalog-delta.py
```
