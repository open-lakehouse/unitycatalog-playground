# AGENTS.md

Guidance for coding agents working in this repository.

This repo is a **Unity Catalog OSS playground**: a Dockerized (or local `uv`)
marimo + Spark notebook environment for exploring catalog-managed Delta tables.

Prefer the `just` recipes in the root `Justfile` over raw `docker compose`
commands. Run `just` (or `just help`) to list them.

## Prerequisites

- Docker with the Compose plugin
- [`just`](https://github.com/casey/just)
- [`uv`](https://docs.astral.sh/uv/) for the local (non-Docker) notebook workflow
- The external Docker network `uc-shared` (created automatically by `just net`,
  `just up`, `just up-detached`, and `just jars`)

## Corporate network: Python and Maven

Public PyPI and Maven Central are often unreachable on certain corporate
networks. **Only** point installs at `pypi.org` or `repo1.maven.org` if the 
user doesn't have MAVEN_PROXY_URL or PYPI_PROXY_URL set in their environment.

### Python — use the local uv registry

For **any** Python install, sync, or package resolution (`uv`, `pip`, Docker
image builds that install Python deps):

1. Read the user's uv config at `~/.config/uv/uv.toml`.
2. Use the index URL(s) defined there. Do not invent a different PyPI mirror
   and do not fall back to public PyPI if that file is present and contains a corporate proxy.
3. Prefer `uv` over `pip`. `uv` already honors `~/.config/uv/uv.toml`
   (including `index-url` and `[[index]]`). Do not pass `--index-url` /
   `--extra-index-url` unless you are copying the values from that file.
4. For Docker / Compose image builds, set `PYPI_PROXY_URL` to the same
   `index-url` from `~/.config/uv/uv.toml` (see `.env` below). The `Justfile`
   currently defaults `pypi_proxy_url` to that Databricks proxy; keep it in
   sync with the uv config rather than hard-coding a different URL.

Typical contents of `~/.config/uv/uv.toml`:

```toml
index-url = "https://pypi-proxy.your-company.com/simple"
[[index]]
url = "https://pypi-proxy.alt.your-company.com/simple/"
default = true
```

Local notebook deps:

```bash
just sync
# equivalent: cd marimo-playground && uv sync
```

### Maven — use `MAVEN_PROXY_URL`

For **any** Maven / Ivy / Spark jar resolution (`just jars`, `spark-submit
--packages`, notebook `spark.jars.packages`, publishing or fetching artifacts):

1. Use the `MAVEN_PROXY_URL` environment variable as the Maven repository root.
   Typical value: `https://maven-proxy.dev.databricks.com` (append a Nexus
   group path if required, e.g. `.../repository/.../`).
2. Never resolve against `repo1.maven.org` or `spark-packages` first when
   `MAVEN_PROXY_URL` is set — those hosts are firewalled and stall Ivy.
3. Compose, the notebooks, and `just jars` all read **`MAVEN_PROXY_URL`**.
   `just jars` renders `spark/ivysettings.xml` into a **proxy-first** Ivy
   resolver so artifacts go straight to the proxy, with the local Ivy repo
   (`~/.ivy2/local`, or `/opt/ivy2/local` in the container) used only for
   SNAPSHOTs the proxy does not have.

4. If `MAVEN_PROXY_URL` is unset, ask before assuming public Maven Central.

## First-time setup

```bash
just init          # copies .env.example -> .env if missing (idempotent)
```

Then edit `.env`:

| Variable | Purpose |
| --- | --- |
| `PYPI_PROXY_URL` | PyPI index used when **building** the `marimo-spark` image. Set from `~/.config/uv/uv.toml`. |
| `MAVEN_PROXY_URL` | Maven2 root used at **run time** by Spark / `just jars`. |
| `UC_SERVER_URL` / `UC_SERVER_PORT` / `UC_TOKEN` | Unity Catalog endpoint. Defaults talk to the bundled `unitycatalog` service. |
| `POSTGRES_*` | Local UC Postgres (`uc=local`). Keep in sync with `etc/conf/hibernate.properties`. |
| `HOST_IVY_DIR` | Host Ivy repo bind-mounted into the container (default `~/.ivy2`). |
| `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` | RustFS root credentials (`uc=local`). Local-only dev defaults (`rustfsadmin`). |
| `UC_STORAGE_BUCKET` | S3 bucket used as the UC managed-tables storage root (default `uc-warehouse`). |
| `S3_REGION` | Region label for S3/STS (default `us-east-1`; RustFS is region-agnostic). |
| `STS_DURATION_SECONDS` | Lifetime of the STS credential UC vends (default `43200` = 12h max). |
| `RUSTFS_API_PORT` / `RUSTFS_CONSOLE_PORT` | Host ports for the RustFS S3 API / web console (default `9000` / `9001`). |
| `S3_ENDPOINT_URL` | S3 endpoint Spark's S3A client targets. Leave blank — `just uc=local` sets it to `http://rustfs:9000`. |

`docker compose` loads `.env` automatically.

## Build and run (Docker)

Two Unity Catalog modes share one `docker-compose.yaml`. The bundled
`unitycatalog` service is behind the Compose profile `local-uc`. Every `just`
recipe accepts `uc=remote` (default) or `uc=local`.

| Mode | What starts |
| --- | --- |
| `remote` (default) | Only `marimo-spark`. Point it at an external UC via `.env`. |
| `local` | Bundled `unitycatalog` + Postgres metadata DB + `rustfs` object store (+ `rustfs-init` bootstrap) **plus** `marimo-spark`. |

```bash
just build                 # build marimo-spark (honors PYPI_PROXY_URL)
just rebuild               # no-cache rebuild
just jars                  # optional: pre-download Spark jars into ./spark/jars
just up                    # remote UC, foreground
just uc=local up           # bundled local UC + marimo, foreground
just uc=local start        # build + up -d + print the marimo URL/token
just url                   # print http://localhost:2718?access_token=...
just logs / just logs-marimo
just ps
just down                  # stop containers/networks; keep named volumes (alias: just stop)
just down-volumes          # down + delete named volumes (wipes local UC Postgres + RustFS data)
just clean                 # down-volumes + delete the local marimo-spark image
just uc=local rotate-creds # re-mint the RustFS STS credential UC vends + restart UC (after ~12h)
just uc=local rustfs-url   # print the RustFS console + S3 API URLs
```

`just start` is the usual happy path: build, start detached, print the notebook
URL. Open the printed `http://localhost:2718?access_token=...` URL in a browser.

Pass the **same** `uc=...` value to `down` / `logs` / `ps` that you used to
start the stack.

### Local UC Postgres

With `uc=local`, Unity Catalog stores catalog metadata in Postgres 16.3 (same
image/credentials as upstream `etc/db/postgres-example.yml`). Config lives in
`etc/conf/hibernate.properties`; the JDBC driver is already on the server
classpath. Data is in the named volume `uc_postgres_data` and survives
`just down` / restarts — use `just clean` or `just down-volumes` to wipe it.

### Local UC storage (RustFS)

With `uc=local`, managed table DATA lives in **RustFS** (an S3-compatible object
store), not a local file path — so `storage-root.tables=s3://<bucket>` and the
stack behaves like a cloud UC. On startup the one-shot `rustfs-init` service:

1. waits for RustFS, creates `UC_STORAGE_BUCKET` if missing;
2. mints a short-lived STS `AssumeRole` credential from RustFS;
3. renders `etc/conf` into the `uc_conf` volume, injecting the bucket/region and
   those creds into `server.properties`.

Why STS: this UC build (`newfrontdocker/unitycatalog:v0.6.0`) has **no custom S3
endpoint support** (that's the still-open unitycatalog PR #1636). Its credential
vendor returns static creds to Spark only when a **session token** is present,
else it falls back to AWS STS (unreachable). RustFS — like MinIO — rejects a
token it didn't issue, so `rustfs-init` mints a real RustFS STS token for UC to
vend. The bootstrap logic lives in `etc/rustfs/bootstrap.sh`.

The vended STS credential **expires** (default 12h, `STS_DURATION_SECONDS`).
When managed-table reads/writes start failing with credential errors, refresh
it with `just uc=local rotate-creds` (re-mints + restarts UC; bucket data is
untouched). Object data is in the `rustfs_data` volume; `uc_conf` is regenerated
each `up`. The notebooks set the client-side `fs.s3a.endpoint` / path-style /
plaintext toggles from `S3_ENDPOINT_URL` (injected as `http://rustfs:9000` by
`just uc=local`); UC still vends the credentials.

#### Troubleshooting: `403 Forbidden` / `AccessDeniedException` on managed tables

Symptom — a `CREATE TABLE`, write, or read against a `unity.*` managed table
fails with something like:

```
java.nio.file.AccessDeniedException: s3://uc-warehouse/__unitystorage/tables/<uuid>/_delta_log/_last_checkpoint:
getFileStatus on s3://.../_last_checkpoint:
software.amazon.awssdk.services.s3.model.S3Exception: Forbidden
(Service: S3, Status Code: 403, Request ID: ...)
```

**This is an expired/invalid credential, not a missing object.** A brand-new
table has no `_last_checkpoint` yet, so a valid credential would get a `404`
(mapped to "not found"). A **`403`** means RustFS is *rejecting the credential*
Spark is using.

Root cause — UC reads `server.properties` (and thus the STS token) **only at
startup**. The STS token lives ~12h, but the `unitycatalog` container often runs
longer. A later `just uc=local up` re-runs `rustfs-init` and writes a **fresh**
token into the `uc_conf` volume, but if it only *recreates `marimo-spark`* and
leaves `unitycatalog` **Running** (not restarted), UC keeps vending the stale
in-memory token. RustFS rejects it → `403`. Confirm with
`docker ps` — if `unitycatalog` shows a much longer uptime than its STS lifetime
(e.g. `Up 5 days`), it's serving an expired credential.

Fix:

```bash
just uc=local rotate-creds   # re-mint STS token + restart UC so it reloads it
```

Then **restart the Spark session** so it re-fetches the now-valid vended
credential — S3A caches the filesystem/credential for the life of a session, so
an already-running notebook keeps hitting the stale one. Either restart the
marimo kernel and re-run from the `common.initialize(...)` cell, or
`docker restart marimo-spark` and reopen the printed URL.

### Network

`marimo-spark` joins the **external** Docker network `uc-shared`. Compose fails
with `network uc-shared declared as external, but could not be found` if it is
missing. `just up` / `just up-detached` / `just jars` create it via `just net`.

### Pre-downloaded Spark jars

Notebooks resolve `delta-spark`, `unitycatalog-spark`, `hadoop-aws`, and
transitive deps from Maven on first Spark session unless `./spark/jars` is
populated. That can take minutes behind a firewall.

```bash
just build
just jars          # uses MAVEN_PROXY_URL / ivysettings.xml; safe to re-run
just uc=local start
```

Coordinates live in `jars_packages` at the top of the `Justfile`. Keep them in
sync with `spark.jars.packages` in the notebooks. Downloaded jars are
git-ignored (`spark/jars/.gitkeep` keeps the directory).

`delta_4.3_playground` prefers `/spark/jars` and falls back to Maven when empty.
Its first cell prints `Jar source: local (...)` vs `Jar source: Maven (...)`.

## Local notebooks (no Docker)

Python **3.10+**, Java **21** (see `marimo-playground/.python-version` and
`.java-version`).

```bash
just sync          # uv sync in marimo-playground/ (uses ~/.config/uv/uv.toml)
just edit          # marimo edit notebooks/unitycatalog-delta.py
just run           # marimo run (read-only app)
```

Or from `marimo-playground/`:

```bash
uv sync
uv run marimo edit notebooks/unitycatalog-delta.py
uv run marimo edit notebooks/my_new_notebook.py
```

For a local `uv` run, point `UC_SERVER_URL` at a reachable UC (typically
`http://localhost:8080`) and export `MAVEN_PROXY_URL` so Spark jar resolution
uses the corporate Maven proxy.

## Project layout

```
Justfile                         # task runner — start here
docker-compose.yaml              # marimo-spark + optional unitycatalog + postgres + rustfs (+init) (profile local-uc)
Dockerfile                       # apache/spark + marimo + pyspark + delta-spark
.env.example                     # PYPI_PROXY_URL, MAVEN_PROXY_URL, UC_*, POSTGRES_*, HOST_IVY_DIR, RUSTFS_*/S3_*
etc/conf/server.properties       # bundled UC server template (managed tables; s3:// storage-root, @S3_*@ placeholders)
etc/conf/hibernate.properties    # local UC → Postgres JDBC (uc=local)
etc/conf/*.log4j2.properties     # UC server/CLI logging (copied into the uc_conf volume by rustfs-init)
etc/rustfs/bootstrap.sh          # rustfs-init: create bucket + mint STS creds + render server.properties
spark/ivysettings.xml            # proxy-first Ivy template (@MAVEN_PROXY_URL@)
spark/jars/                      # pre-downloaded jars from `just jars` (git-ignored)
marimo-playground/
  pyproject.toml / uv.lock
  notebooks/
    unitycatalog-delta.py        # default entrypoint (catalog-managed tables)
    unitycatalog-0.5-delta.py
    delta_4.2_enhancements.py
    delta_4.3_playground.py      # prefers /spark/jars
    databricks/external-access-unitycatalog-delta-managed-read.py
delta/python/catalog-managed.py  # Pets helpers used by the notebooks
delta/scala/catalog-managed.scala
```

The Docker image entrypoint opens `marimo-playground/notebooks/unitycatalog-delta.py`
on port **2718**. Notebooks are bind-mounted, so host edits appear in the
container. The bundled UC server listens on **8080** when `uc=local`, with
Postgres on **5432** (metadata volume `uc_postgres_data`) and RustFS on **9000**
(S3 API) / **9001** (console), backed by the `rustfs_data` volume.

## Exploring the notebooks

1. Start the stack (`just uc=local start`) and open the printed marimo URL.
2. Run cells **in order**. Skip markdown cells; they are context only.
3. The default notebook walks through creating a catalog-managed Delta table
   (`unity.sanctuary.pets`) using helpers in `delta/python/catalog-managed.py`:
   `Pets`, `generate_pets`, `pets_to_dataframe`, `create_table_ddl`,
   `create_table_using_sql`.
4. Spark sessions honor `MAVEN_PROXY_URL` / `spark/ivysettings.xml` and, when
   present, jars in `/spark/jars`.

## Agent conventions

- Use `just` recipes; do not invent parallel Compose invocations unless a
  recipe is missing.
- Do not commit `.env`, `spark/jars/*.jar`, or secrets (`UC_TOKEN`, AWS keys
  in `server.properties`). `etc/conf/server.properties` is a **template** with
  `@S3_*@` placeholders; the rendered copy with live creds lives only in the
  `uc_conf` volume (never on disk) — leave the placeholders in the committed file.
- Do not add `--remove-orphans` to `docker compose down` from recipes — it can
  delete a UC server started by another Compose project on the shared network.
- Keep `Justfile` `jars_packages` aligned with notebook `spark.jars.packages`.
- When adding Python dependencies, edit `marimo-playground/pyproject.toml` and
  run `uv sync` (registry from `~/.config/uv/uv.toml`). Mirror new runtime
  deps in the `Dockerfile` `pip install` list if the image needs them too.
- When adding Spark / Maven coordinates, resolve them through
  `MAVEN_PROXY_URL`.
