#!/usr/bin/env python3
"""Point uv.lock at public PyPI instead of a private PyPI proxy.

uv records the index that resolved each package, so a lock written behind a
corporate proxy (~/.config/uv/uv.toml) only installs where that proxy is
reachable, and GitHub runners can't reach it. The proxy serves files at the
same /packages/... paths as files.pythonhosted.org, so swapping the host keeps
every sha256 valid.

Usage: scripts/clean-uv-lock.py [--check] [LOCKFILE]

  --check   exit 1 if LOCKFILE references a private index, without rewriting it
  LOCKFILE  defaults to marimo-playground/uv.lock
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

PYPI_SIMPLE = "https://pypi.org/simple"
PYPI_FILES = "https://files.pythonhosted.org"
DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "marimo-playground" / "uv.lock"

REGISTRY = re.compile(r'registry = "([^"]+)"')


def private_registries(text: str) -> list[str]:
    return sorted({u for u in REGISTRY.findall(text) if u.rstrip("/") != PYPI_SIMPLE})


def clean(text: str) -> str:
    for registry in private_registries(text):
        base = re.sub(r"/simple/?$", "", registry)
        text = text.replace(f'registry = "{registry}"', f'registry = "{PYPI_SIMPLE}"')
        text = text.replace(f'url = "{base}/packages/', f'url = "{PYPI_FILES}/packages/')
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("lockfile", nargs="?", type=Path, default=DEFAULT_LOCK)
    args = parser.parse_args()

    lock: Path = args.lockfile
    original = lock.read_text()
    registries = private_registries(original)
    if not registries:
        print(f"{lock}: clean (public PyPI only)")
        return 0
    if args.check:
        print(
            f"{lock}: references private index(es) {', '.join(registries)}; "
            "run `just clean-lock`",
            file=sys.stderr,
        )
        return 1

    cleaned = clean(original)
    hosts = {urlsplit(r).netloc for r in registries}
    leftover = sorted(h for h in hosts if h in cleaned)
    if leftover:
        # The proxy doesn't mirror files.pythonhosted.org's /packages/ layout
        # (e.g. Nexus/Artifactory), so the host can't simply be swapped.
        print(
            f"{lock}: unrecognized URL layout for {', '.join(leftover)}; nothing written. "
            "Re-lock against public PyPI instead: "
            "uv lock --no-config --default-index https://pypi.org/simple",
            file=sys.stderr,
        )
        return 1

    lock.write_text(cleaned)
    print(f"{lock}: rewrote {', '.join(sorted(hosts))} -> pypi.org / files.pythonhosted.org")
    return 0


if __name__ == "__main__":
    sys.exit(main())
