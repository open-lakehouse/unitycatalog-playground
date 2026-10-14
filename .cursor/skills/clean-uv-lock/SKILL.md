---
name: clean-uv-lock
description: Rewrites private PyPI proxy URLs in marimo-playground/uv.lock back to public PyPI so the GitHub build can install from it. Use whenever uv.lock is modified (uv sync, uv lock, uv add, uv run, editing pyproject.toml), before committing, or when uv.lock shows up in git status/diff.
---

# Clean uv.lock

Behind a corporate network, `~/.config/uv/uv.toml` points uv at a PyPI proxy, and
uv writes that proxy into every `registry =` and file `url =` in `uv.lock`.
GitHub runners can't reach the proxy, so a committed proxy lock fails CI. uv also
re-locks against the proxy on every `uv sync` / `uv run`, so the lock gets dirty
again after any local install.

## Rule

Whenever `marimo-playground/uv.lock` has been modified, clean it before finishing
the task or committing:

```bash
just clean-lock
just check-lock   # must print "clean (public PyPI only)"
```

`just clean-lock` runs `scripts/clean-uv-lock.py`. It's idempotent: it swaps the
proxy host for `pypi.org/simple` (registries) and `files.pythonhosted.org`
(files), which keeps every hash valid.

## When to apply

- After any `uv sync`, `uv lock`, `uv add` / `uv remove`, or plain `uv run` in
  `marimo-playground/`
- After editing `marimo-playground/pyproject.toml`
- When `git status` or `git diff` lists `marimo-playground/uv.lock`

`just sync`, `just edit`, `just run` and `just edit-iceberg` already clean the
lock themselves (they sync, clean, then use `uv run --frozen`). Prefer them over
raw `uv` commands.

## Don'ts

- Don't run `uv run` without `--frozen` after cleaning; it re-locks against the
  proxy and re-dirties the file. Use `just sync` first, then `uv run --frozen ...`.
- Don't re-lock against public PyPI to "fix" the lock (`--index-url https://pypi.org/simple`).
  Public PyPI is often unreachable here; resolve through the proxy, then clean.
- Don't hand-edit URLs in `uv.lock`.

## If the script refuses

`unrecognized URL layout for <host>` means the proxy doesn't mirror
`files.pythonhosted.org`'s `/packages/...` paths, so nothing was written. On a
network that can reach public PyPI, re-lock without the proxy:

```bash
cd marimo-playground && uv lock --no-config --default-index https://pypi.org/simple
```
