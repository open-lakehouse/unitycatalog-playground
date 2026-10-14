# AGENTS.md

Guidance for coding agents working in this repository.

This repo is a **Unity Catalog OSS playground**: a Dockerized (or local `uv`)
marimo + Spark notebook environment for exploring catalog-managed Delta tables
and (UC 0.7+) native Apache Iceberg tables through UC's Iceberg REST catalog.

Prefer the `just` recipes in the root `Justfile` over raw `docker compose`
commands. Run `just` (or `just help`) to list them.

## Prerequisites

- Docker with the Compose plugin
- [`just`](https://github.com/casey/just)
- [`uv`](https://docs.astral.sh/uv/) for the local (non-Docker) notebook workflow
- The external Docker network `uc-shared` (created automatically by `just net`,
  `just up`, and `just up-detached`)

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
# equivalent: cd marimo-playground && uv sync && just clean-lock
```

#### Dependency groups and lock files

`marimo-playground/pyproject.toml` declares one dependency group per notebook
image, marked as conflicting so one `uv.lock` holds both Spark lines:

| Group | Contents | Exported to | Installed by |
| --- | --- | --- | --- |
| `delta` (default) | `pyspark==4.2.0`, `delta-spark==4.4.0` | `requirements.lock` | `Dockerfile` (`marimo-spark`) |
| `iceberg` | `pyspark==4.1.3`, `pyiceberg[...]==0.12.0` | `requirements-iceberg.lock` | `Dockerfile.iceberg` (`marimo-iceberg`) |

The images install the exported files with `pip --require-hashes` against
public PyPI (or `PYPI_PROXY_URL`). They contain only versions and hashes, so
they don't depend on which index produced `uv.lock`. After editing
`pyproject.toml`, run **`just lock`**: it re-locks through the proxy, cleans
`uv.lock`, and re-exports both requirements files. Keep `pyspark` in each group
on the same line as that image's base (`apache/spark:4.2.0` / `4.1.3`).

#### Keep `uv.lock` on public PyPI

uv writes the proxy from `~/.config/uv/uv.toml` into every URL in
`marimo-playground/uv.lock`, so the lock only installs where that proxy is
reachable. It also re-locks against the proxy on every `uv sync` / `uv run`. So
**whenever `uv.lock` is modified, run `just clean-lock`** (then
`just check-lock`) before finishing or committing. The project skill
`.cursor/skills/clean-uv-lock/` has the details. `just sync` / `sync-iceberg` /
`edit` / `run` / `edit-iceberg` already clean it and launch marimo with
`uv run --frozen`; a bare `uv run` re-dirties the lock. CI runs
`just check-lock`, which also fails if either requirements file is stale.

### Maven — use `MAVEN_PROXY_URL`

For **any** Maven / Ivy / Spark jar resolution (`spark-submit --packages`,
notebook `spark.jars.packages`, publishing or fetching artifacts):

1. Use the `MAVEN_PROXY_URL` environment variable as the Maven repository root.
   Typical value: `https://maven-proxy.dev.databricks.com` (append a Nexus
   group path if required, e.g. `.../repository/.../`).
2. Never resolve against `repo1.maven.org` or `spark-packages` first when
   `MAVEN_PROXY_URL` is set — those hosts are firewalled and stall Ivy.
3. Compose and the notebooks read **`MAVEN_PROXY_URL`**.
   `common.ivy_config()` renders `spark/ivysettings.xml` into a **proxy-first** Ivy
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
| `PYPI_PROXY_URL` | PyPI index used when **building** the `marimo-spark` and `marimo-iceberg` images. Set from `~/.config/uv/uv.toml`. |
| `MAVEN_PROXY_URL` | Maven2 root used at **run time** by Spark jar resolution in the notebooks. |
| `SPARK_VERSION` | Spark line for `marimo-spark` Maven coordinates (default `4.2`). `marimo-iceberg` pins `4.1`. |
| `ICEBERG_VERSION` | `iceberg-spark-runtime-4.1_2.13` / `iceberg-aws-bundle` version for `marimo-iceberg` (default `1.11.0`). |
| `UC_ICEBERG_CATALOG` | UC catalog used as the Iceberg REST `warehouse` + Spark catalog name (default `unity`). |
| `UC_SERVER_URL` / `UC_SERVER_PORT` / `UC_TOKEN` | Unity Catalog endpoint. Defaults talk to the bundled `unitycatalog` service. |
| `UC_AUTHORIZATION` | `enable` / `disable` (default). Rendered into the bundled UC's `server.authorization` by `rustfs-init` (`uc=local`). Written by `just uc=local auth=... set-auth` / `demo-auth` / `demo-noauth`. |
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
| `remote` (default) | `marimo-spark` + `marimo-iceberg`. Point them at an external UC via `.env`. |
| `local` | Bundled `unitycatalog` (official `unitycatalog/unitycatalog:v0.7.0`, digest-pinned) + Postgres metadata DB + `rustfs` object store (+ `rustfs-init` bootstrap) **plus** both marimo services. |

Two notebook services run side by side:

| Service | Image | Port | Notebooks |
| --- | --- | --- | --- |
| `marimo-spark` | `Dockerfile` (Spark 4.2, Delta) | **2718** | `notebooks/*.py` (Delta, metric views) |
| `marimo-iceberg` | `Dockerfile.iceberg` (Spark 4.1.3, Iceberg 1.11, PyIceberg 0.12) | **2719** | `notebooks/iceberg/` |

```bash
just build                 # build marimo-spark + marimo-iceberg
just rebuild               # no-cache rebuild
just up                    # remote UC, foreground
just uc=local up           # bundled local UC + marimo, foreground
just uc=local start        # build + up -d + print both marimo URLs/tokens
just url                   # print http://localhost:2718?access_token=... (marimo-spark)
just url-iceberg           # print http://localhost:2719?access_token=... (marimo-iceberg)
just logs / just logs-marimo / just logs-iceberg
just ps
just down                  # stop containers/networks; keep named volumes (alias: just stop)
just down-volumes          # down + delete named volumes (wipes local UC Postgres + RustFS data)
just clean                 # down-volumes + delete the local marimo images
just uc=local rotate-creds # re-mint the RustFS STS credential UC vends + restart UC (after ~12h)
just uc=local rustfs-url   # print the RustFS console + S3 API URLs
just uc=local db-upgrade   # once, on a uc_postgres_data volume created by UC 0.6
just uc=local demo-noauth  # build + start with auth disabled + print URLs
just uc=local demo-auth    # build + start with auth enabled + seed demo users + print admin token/URLs
just uc=local auth=enable set-auth   # flip auth (saved to .env, re-renders uc_conf, restarts UC)
just uc=local token        # print the admin (metastore OWNER) token
just uc=local token-for <email>      # mint a token for a UC user (scripts/mint-user-token.sh)
just uc=local bootstrap-users        # seed demo users + grants on demo.workshop (idempotent)
just uc=local grant <grant|revoke> -t <type> -n <name> -p <principal> -P <privilege>
```

`just start` is the usual happy path: build, start detached, print the notebook
URLs. Open the printed `http://localhost:2718?access_token=...` (Delta) or
`http://localhost:2719?access_token=...` (Iceberg) URL in a browser.

Pass the **same** `uc=...` value to `down` / `logs` / `ps` that you used to
start the stack.

### Local UC Postgres

With `uc=local`, Unity Catalog stores catalog metadata in Postgres 16.3 (same
image/credentials as upstream `etc/db/postgres-example.yml`). Config lives in
`etc/conf/hibernate.properties`; the JDBC driver is already on the server
classpath. Data is in the named volume `uc_postgres_data` and survives
`just down` / restarts — use `just clean` or `just down-volumes` to wipe it.

Upgrading a volume created by UC 0.6: Hibernate's `hbm2ddl=update` adds new
tables/columns but never widens existing ones, and 0.7 stores Iceberg/namespace
properties longer than 255 chars in `uc_properties.property_value`. Run
`just uc=local db-upgrade` once (or `just clean` to start fresh).

### Local UC storage (RustFS)

With `uc=local`, managed table DATA lives in **RustFS** (an S3-compatible object
store), not a local file path — so `storage-root.tables=s3://<bucket>` and the
stack behaves like a cloud UC. On startup the one-shot `rustfs-init` service:

1. waits for RustFS, creates `UC_STORAGE_BUCKET` if missing;
2. mints a short-lived STS `AssumeRole` credential from RustFS;
3. renders `etc/conf` into the `uc_conf` volume, injecting the bucket/region and
   those creds into `server.properties`.

Why STS: this UC build (`unitycatalog/unitycatalog:v0.7.0`) has **no
custom S3 endpoint support** (that's the still-open unitycatalog PR #1636). Its credential
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

UC 0.7 also does **server-side** S3 I/O: the Iceberg REST catalog writes each
table's first `metadata.json`, and the storage-cleanup worker deletes dropped
managed tables. With no endpoint property, the server reaches RustFS through
the AWS SDK's `AWS_ENDPOINT_URL_S3=http://rustfs:9000` env var. The SDK then
uses virtual-hosted addressing (`uc-warehouse.rustfs`), so Compose gives
`rustfs` `RUSTFS_SERVER_DOMAINS=rustfs` and a `<bucket>.rustfs` network alias.

Dropped **managed** tables are not deleted inline: UC queues a row in
`uc_storage_cleanup_tasks` and a background worker deletes the storage after
`server.storage-cleanup.initial-delay` (upstream default `P7D`; the template
uses `PT5M` so the playground reclaims space quickly). The worker processes
one task per `poll-interval` (`PT1M`). External tables are never deleted.

### Local UC authentication

`server.authorization` comes from `UC_AUTHORIZATION` in `.env` (default
`disable`): `rustfs-init` renders it into `server.properties` on every `up`, and
UC reads it only at startup. Change it with `just uc=local auth=enable|disable
set-auth` (or `demo-auth` / `demo-noauth`), never by editing the rendered file.
Those recipes re-render `uc_conf` and restart UC when it's running.

UC accepts only its own `internal`-issuer RS512 JWTs on API requests, signed
with the key it keeps in `uc_conf` (`private_key.der`, `key_id.txt`), for an
**enabled** UC user. `token.txt` is the `admin` service token (metastore OWNER,
no expiry). `scripts/mint-user-token.sh` signs user tokens with the same key, so
no identity provider is needed; `server.allowed-issuers` / `server.audiences`
only apply to external-IdP token exchange at `POST /auth/tokens` and stay blank.
`scripts/` (`_uc_lib.sh`, `bootstrap-users.sh`, `grant.sh`) read the key and
admin token out of the running `unitycatalog` container and need `jq`,
`openssl`, `curl`, `uuidgen`.

Objects created while auth was disabled have no owner and no hierarchy links in
`casbin_rule`, so even `admin` needs explicit grants on them; the `demo` catalog
from `bootstrap-users` is created with auth on. `down-volumes` / `clean`
regenerate the signing key and wipe users, so re-run `demo-auth`. See
`docs/uc/authentication.md` (why + recipes) and `docs/uc/getting-started.md`
(walkthrough).

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

`marimo-spark` and `marimo-iceberg` join the **external** Docker network `uc-shared`. Compose fails
with `network uc-shared declared as external, but could not be found` if it is
missing. `just up` / `just up-detached` create it via `just net`.

### Spark jar resolution

Notebooks resolve their Spark packages from Maven on the first Spark session:
`delta-spark`, `unitycatalog-spark`, and `hadoop-aws` for `marimo-spark`
(`common.spark_config()`), and `iceberg-spark-runtime-4.1_2.13` +
`iceberg-aws-bundle` for `marimo-iceberg` (`iceberg_common.iceberg_spark_config()`).
Both go through the proxy-first Ivy settings (`common.ivy_config()`), and the
host `~/.ivy2` bind mount caches the artifacts after the first session. The
first resolution can take minutes behind a firewall.

## Local notebooks (no Docker)

Python **3.10+**, Java **21** (see `marimo-playground/.python-version` and
`.java-version`).

```bash
just sync          # uv sync the `delta` group (uses ~/.config/uv/uv.toml) + clean-lock
just sync-iceberg  # uv sync the `iceberg` group instead + clean-lock
just edit          # sync, then marimo edit notebooks/unitycatalog-delta.py
just run           # sync, then marimo run (read-only app)
just lock          # after editing pyproject.toml: uv lock + clean-lock + export both requirements files
just clean-lock    # rewrite proxy URLs in uv.lock to public PyPI
just check-lock    # fail if uv.lock references a private index or a requirements file is stale
```

Or from `marimo-playground/`, after `just sync` (`--frozen` keeps uv.lock clean):

```bash
uv run --frozen marimo edit notebooks/unitycatalog-delta.py
uv run --frozen marimo edit notebooks/my_new_notebook.py
```

For a local `uv` run, point `UC_SERVER_URL` at a reachable UC (typically
`http://localhost:8080`) and export `MAVEN_PROXY_URL` so Spark jar resolution
uses the corporate Maven proxy.

The Iceberg notebooks run locally too, from the `iceberg` dependency group
(`pyspark==4.1.3` + PyIceberg). `just edit-iceberg` swaps the venv to that group
(and `just edit` swaps it back). Against `uc=local`, also export
`S3_ENDPOINT_URL=http://localhost:9000`:

```bash
UC_SERVER_URL=http://localhost:8080 S3_ENDPOINT_URL=http://localhost:9000 just edit-iceberg
```

## Project layout

```
Justfile                         # task runner — start here
docker-compose.yaml              # marimo-spark + marimo-iceberg + optional unitycatalog + postgres + rustfs (+init) (profile local-uc)
Dockerfile                       # apache/spark 4.2 (digest-pinned) + requirements.lock (:2718)
Dockerfile.iceberg               # apache/spark 4.1.3 (digest-pinned) + requirements-iceberg.lock (:2719)
.github/workflows/local-stack.yml  # CI: check-lock, build both images, uc=local up, run both smoke notebooks
.env.example                     # PYPI_PROXY_URL, MAVEN_PROXY_URL, SPARK/ICEBERG_VERSION, UC_*, POSTGRES_*, HOST_IVY_DIR, RUSTFS_*/S3_*
etc/conf/server.properties       # bundled UC 0.7 server template (managed Delta + Iceberg; s3:// storage-root, @S3_*@ placeholders)
etc/conf/hibernate.properties    # local UC → Postgres JDBC (uc=local)
etc/conf/*.log4j2.properties     # UC server/CLI logging (copied into the uc_conf volume by rustfs-init)
etc/rustfs/bootstrap.sh          # rustfs-init: create bucket + mint STS creds + render server.properties (incl. UC_AUTHORIZATION)
scripts/                         # uc=local auth tooling (mint-user-token.sh, bootstrap-users.sh, grant.sh, _uc_lib.sh) + clean-uv-lock.py
.cursor/skills/clean-uv-lock/    # agent skill: clean uv.lock whenever it changes
spark/ivysettings.xml            # proxy-first Ivy template (@MAVEN_PROXY_URL@)
spark/delta-override/            # optional local delta-spark wheel from `just stage-delta` (git-ignored)
docs/uc/getting-started.md       # walkthrough: no-auth vs auth modes, demo personas, live grants
docs/uc/authentication.md        # why UC auth matters, how tokens/grants work here, the auth recipes
docs/releases/delta-4.4.0-release.md  # Delta Lake 4.4.0 release notes (companion to delta-new-in-4.4.0.py)
marimo-playground/
  pyproject.toml / uv.lock       # `delta` + `iceberg` dependency groups (see "Dependency groups")
  requirements.lock              # `delta` group export (hashes) installed by Dockerfile
  requirements-iceberg.lock      # `iceberg` group export (hashes) installed by Dockerfile.iceberg
  notebooks/
    unitycatalog-delta.py        # default entrypoint (catalog-managed tables)
    ci-smoke.py                  # CI: create/write/count/drop a catalog-managed Delta table
    delta-new-in-4.4.0.py        # Delta 4.4.0: identity columns, SHOW PARTITIONS
    metric-views.py              # UC metric views over a catalog-managed Delta table (ecomm catalog)
    common.py                    # shared Spark/UC/Ivy config (ivy_config, spark_config, initialize) + Delta DDL helpers
    sanctuary.py                 # shared seeded pet roster + adoptions (stdlib only) used by every notebook
    iceberg/                     # served by marimo-iceberg (:2719)
      iceberg_common.py          # IRC URI, UC REST helpers, Spark + PyIceberg catalog config
      unitycatalog-iceberg-spark.py  # Spark SQL: namespaces, managed/external, DML, evolution, rename
      unitycatalog-pyiceberg.py      # PyIceberg: create, append, scan, schema evolution, rename
      ci-smoke-iceberg.py        # CI: Spark create/insert -> PyIceberg read/append -> Spark count/drop
    databricks/external-access-unitycatalog-delta-managed-read.py
delta/scala/catalog-managed.scala
```

The `marimo-spark` entrypoint serves the `marimo-playground/notebooks/` directory
on port **2718**; `marimo-iceberg` serves the `notebooks/iceberg/` directory on
**2719**. Notebooks are bind-mounted, so host edits appear in both
containers. The bundled UC server listens on **8080** when `uc=local`, with
Postgres on **5432** (metadata volume `uc_postgres_data`) and RustFS on **9000**
(S3 API) / **9001** (console), backed by the `rustfs_data` volume.

## CI (`.github/workflows/local-stack.yml`)

Runs on every pull request and on pushes to `main`, against public PyPI and
Maven Central (no proxies):

1. `just check-lock`: `uv.lock` has no private index URLs, and
   `requirements.lock` / `requirements-iceberg.lock` match `uv.lock`.
2. `just uc=local build`, then `just uc=local up-detached`; waits for UC (:8080),
   `marimo-spark` (:2718) and `marimo-iceberg` (:2719).
3. `marimo export html` runs `notebooks/ci-smoke.py` in `marimo-spark` (prints
   `CI_NOTEBOOK_SMOKE_OK`) and `notebooks/iceberg/ci-smoke-iceberg.py` in
   `marimo-iceberg` (prints `CI_ICEBERG_SMOKE_OK`); each step greps for its marker.

Run the same smoke tests locally after `just uc=local start`:

```bash
docker exec marimo-spark marimo export html /opt/workspace/marimo-playground/notebooks/ci-smoke.py -o /tmp/s.html
docker exec marimo-iceberg marimo export html /opt/workspace/marimo-playground/notebooks/iceberg/ci-smoke-iceberg.py -o /tmp/i.html
```

## Exploring the notebooks

1. Start the stack (`just uc=local start`) and open the printed marimo URL.
2. Run cells **in order**. Skip markdown cells; they are context only.
3. The default notebook walks through creating a catalog-managed Delta table
   (`unity.sanctuary.pets`) using `sanctuary.generate_pets` /
   `sanctuary.pets_to_dataframe` and `common.create_table_ddl` /
   `common.create_table_using_sql`.

### Shared data (`notebooks/sanctuary.py`)

All notebooks (Delta and Iceberg) generate data from `sanctuary.py`, a seeded,
deterministic, prefix-stable pet roster (`roster(100)` is the first 100 of
`roster(120)`). Pet `uuid`s are identical in every table, so Delta
`unity.sanctuary.pets.uuid` joins Iceberg `unity.iceberg_spark.adoptions.pet_uuid`
and `unity.iceberg_py.pets.uuid`. Keep it stdlib-only at import time (the
PyIceberg notebook has no Spark), keep `PET_COLUMNS` matching the Delta table,
and don't change `SEED` / `AS_OF` / the draw order casually: that changes every
generated row, so existing tables stop lining up with fresh runs. Notebooks
write the roster idempotently (overwrite / `CREATE OR REPLACE` first), so
reruns don't duplicate `uuid`s.
4. Spark sessions honor `MAVEN_PROXY_URL` / `spark/ivysettings.xml`.

### Native Iceberg notebooks (UC 0.7, `marimo-iceberg` on :2719)

UC 0.7 serves an Iceberg REST catalog at
`<UC_SERVER_URL>/api/2.1/unity-catalog/iceberg`. The client `warehouse` is the UC
catalog name (`unity`, override with `UC_ICEBERG_CATALOG`), Iceberg namespaces are
UC schemas, and `loadTable` vends short-lived S3 credentials per table.
`iceberg_common.ensure_catalog()` creates the catalog through the UC REST API
when it is missing (fresh `uc_postgres_data` volume).

- `unitycatalog-iceberg-spark.py` (`unity.iceberg_spark`): `/v1/config` handshake,
  namespace properties, partitioned managed table, append / UPDATE / DELETE /
  MERGE, snapshots + time travel, schema and partition evolution, CTAS + rename,
  and an external table with `LOCATION`.
- `unitycatalog-pyiceberg.py` (`unity.iceberg_py`): the same catalog from PyIceberg
  with no JVM: create with an explicit schema/spec, append/overwrite, filtered
  scans, schema evolution, row-level delete, `inspect.*`, time travel, rename.

Both are idempotent (safe to re-run) and end with a **disabled** teardown cell.
To verify headless: `docker exec -w /opt/workspace/marimo-playground/notebooks/iceberg marimo-iceberg python3 <notebook>.py`.

Upstream 0.7.0 issues the notebooks work around (remove each one once it's
fixed upstream):

| Issue | Workaround |
| --- | --- |
| `loadTable` sends `client.refresh-credentials-endpoint` without `s3.session-token-expires-at-ms` when the vended token has no expiry, so Iceberg Java fails with `Invalid S3 Credentials` | `iceberg_common` sets `client.refresh-credentials-enabled=false` when `S3_ENDPOINT_URL` is set (PyIceberg is unaffected) |
| `loadTable` on a missing namespace returns `NoSuchNamespaceException`, not `NoSuchTableException`, so Spark metadata tables (`t.snapshots`, `t.files`, ...) don't resolve | Spark notebook uses `system.ancestors_of` and the `_file` / `_partition` / `_spec_id` metadata columns; PyIceberg's `inspect.*` works |

Expected noise: a `RESTMetricsReporter: Failed to report metrics` WARN in the
container log after the CTAS + rename cell. Spark reports scan metrics for the
pre-rename name and UC correctly returns 404. Spark `RENAME TO` takes a
catalog-relative target (`schema.table`); cross-namespace rename is unsupported.

## Agent conventions

- Use `just` recipes; do not invent parallel Compose invocations unless a
  recipe is missing.
- Do not commit `.env`, `spark/delta-override/*.whl`, or secrets (`UC_TOKEN`, AWS keys
  in `server.properties`). `etc/conf/server.properties` is a **template** with
  `@S3_*@` placeholders; the rendered copy with live creds lives only in the
  `uc_conf` volume (never on disk) — leave the placeholders in the committed file.
- Do not add `--remove-orphans` to `docker compose down` from recipes — it can
  delete a UC server started by another Compose project on the shared network.
- Delta / UC Spark coordinates live in `common.spark_config()`.
  Iceberg coordinates live in `iceberg_common.iceberg_spark_config()`; keep
  `ICEBERG_VERSION` and the `marimo-iceberg` Spark line (4.1) in step with
  published `iceberg-spark-runtime-<spark>_2.13` artifacts.
- When adding Python dependencies, edit `marimo-playground/pyproject.toml` and
  put them in the right group (`[project] dependencies` for both images,
  `delta` or `iceberg` for one), then run `just lock` (registry from
  `~/.config/uv/uv.toml`; cleans `uv.lock` and re-exports the requirements
  files the images install). Never commit lock files that fail `just check-lock`.
- When adding Spark / Maven coordinates, resolve them through
  `MAVEN_PROXY_URL`.
