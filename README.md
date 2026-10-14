# Run Unity Catalog Locally with Spark and Delta Lake

**unitycatalog-playground** is a complete, interactive environment for running
open source [Unity Catalog](https://github.com/unitycatalog/unitycatalog)
locally on macOS or Linux. It connects Unity Catalog to Apache Spark and Delta
Lake, stores catalog metadata in PostgreSQL, stores managed-table data in
S3-compatible object storage, and provides ready-to-run
[marimo](https://marimo.io/) notebooks.

Use it to create, write, and query catalog-managed Delta tables—not just start a
catalog server.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

## What you get

- **Unity Catalog OSS** for catalogs, schemas, tables, volumes, and credentials
- **Apache Spark + Delta Lake** as the local compute and table engine
- **PostgreSQL** for persistent Unity Catalog metadata
- **RustFS** for local S3-compatible managed-table storage and credential vending
- **marimo notebooks** with runnable Unity Catalog and Delta Lake examples
- **Native Apache Iceberg tables** through Unity Catalog 0.7's Iceberg REST
  catalog, from Spark 4.1 and PyIceberg
- **Local and remote modes** for using the bundled catalog or another UC server

This project complements the
[official Unity Catalog quickstart](https://github.com/unitycatalog/unitycatalog/blob/main/docs/quickstart.md).
The upstream quickstart is the best place to learn the server and APIs. This
playground adds the compute engine, durable metadata database, object storage,
and notebooks needed for an end-to-end local lakehouse.

## Quickstart: run Unity Catalog locally on a Mac

The container images used by the playground support both Apple Silicon
(`arm64`) and Intel (`amd64`) Macs.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with at
  least 4 GB of memory available to Spark
- [Git](https://git-scm.com/)
- [`just`](https://github.com/casey/just), the project command runner

Install and start the prerequisites with Homebrew:

```bash
brew install --cask docker
brew install just
open -a Docker
```

After Docker Desktop is running:

```bash
git clone https://github.com/open-lakehouse/unitycatalog-playground.git
cd unitycatalog-playground
just uc=local start
```

The first start builds the two notebook images and may take several minutes.
When the environment is ready, the command prints a URL for each notebook
service:

```text
http://localhost:2718/?access_token=...   # Delta (marimo-spark)
http://localhost:2719/?access_token=...   # Iceberg (marimo-iceberg)
```

Open the first URL, select `unitycatalog-delta.py`, and run the notebook cells in
order. You will create a Unity Catalog schema and a catalog-managed Delta table,
write sample data through Spark, and query it again.

The local services are available at:

- marimo Delta notebooks (Spark 4.2): <http://localhost:2718>
- marimo Iceberg notebooks (Spark 4.1 + PyIceberg): <http://localhost:2719>
- Unity Catalog API: <http://localhost:8080>
- RustFS object browser: <http://localhost:9001>
- RustFS S3 API: <http://localhost:9000>

To stop the stack while preserving its metadata and table data:

```bash
just uc=local down
```

## Local and remote Unity Catalog modes

One `docker-compose.yaml` supports two modes:

- **Local:** `just uc=local ...` starts the complete stack: Unity Catalog,
  PostgreSQL, RustFS, and both marimo services (Delta on Spark 4.2, Iceberg on
  Spark 4.1).
- **Remote:** `just ...` starts only the notebook services. Configure
  `UC_SERVER_URL`, `UC_SERVER_PORT`, and `UC_TOKEN` in `.env` to connect it to an
  external Unity Catalog server.

Use the same mode when starting and stopping the environment:

```bash
just uc=local start  # build and start the complete local stack
just uc=local logs   # follow logs
just uc=local ps     # show service status
just uc=local down   # stop containers but preserve data

just start           # connect the notebooks to a remote UC server
just down
```

## Configuration

Run `just init` to create `.env` from [`.env.example`](.env.example). The
defaults work for the local quickstart. Edit `.env` to change Spark resources,
ports, PostgreSQL or RustFS settings, the remote UC endpoint, or proxy settings.

For environments that require package proxies:

```dotenv
PYPI_PROXY_URL=https://pypi-proxy.yourcompany.com/simple
MAVEN_PROXY_URL=https://maven-proxy.yourcompany.com/maven2
```

Docker Compose loads `.env` automatically. Leaving those values blank uses
public PyPI and Maven Central.

The notebooks resolve their Spark jars (`delta-spark`, `unitycatalog-spark`,
`hadoop-aws`, the Iceberg runtime, ...) from Maven the first time a Spark session
starts. With `MAVEN_PROXY_URL` set, they go straight to the proxy through a
proxy-first Ivy resolver ([`spark/ivysettings.xml`](spark/ivysettings.xml)).
Resolved jars are cached in your host `~/.ivy2` (bind-mounted into the
containers), so later sessions start faster.

### Network bridge

`marimo-spark` and `marimo-iceberg` join an **external** docker network,
`uc-shared`, so they can also reach a UC server running in a *separate* compose
project. Because the network is
declared `external: true`, it must exist before Compose starts — otherwise you'll
see `network uc-shared declared as external, but could not be found`.

`just up` / `just up-detached` run `just net` first, which creates the network
idempotently. You can also run it on its own:

```bash
just net   # docker network create uc-shared (no-op if it already exists)
```

## Included notebooks

`marimo-spark` (Spark 4.2, port 2718) serves the Delta notebooks in
`marimo-playground/notebooks/`:

- [`unitycatalog-delta.py`](marimo-playground/notebooks/unitycatalog-delta.py)
  creates a schema and a catalog-managed Delta table, `unity.sanctuary.pets`,
  and writes it in batches from the shared pet roster.
- [`metric-views.py`](marimo-playground/notebooks/metric-views.py) demonstrates
  Unity Catalog metric views with reusable dimensions and measures.
- [`delta-new-in-4.4.0.py`](marimo-playground/notebooks/delta-new-in-4.4.0.py)
  explores Delta Lake 4.4 features on Apache Spark 4.2: identity columns and
  `SHOW PARTITIONS`. The full release notes are in
  [`docs/releases/delta-4.4.0-release.md`](docs/releases/delta-4.4.0-release.md).
- [`external-access-unitycatalog-delta-managed-read.py`](marimo-playground/notebooks/databricks/external-access-unitycatalog-delta-managed-read.py)
  demonstrates reading a remote Databricks Unity Catalog table through external
  data access and credential vending.

`marimo-iceberg` (port 2719) serves the native Iceberg notebooks in
`marimo-playground/notebooks/iceberg/`; see
[Native Apache Iceberg with Unity Catalog 0.7](#native-apache-iceberg-with-unity-catalog-07).

Open the marimo URL printed by `just ... start`, select a notebook, and run its
cells in order. Markdown cells provide context and do not need to be executed.

## Native Apache Iceberg with Unity Catalog 0.7

Unity Catalog 0.7 can create and manage Iceberg tables itself, through its
Iceberg REST catalog (IRC) at `/api/2.1/unity-catalog/iceberg`. Any IRC client can
connect: set `warehouse` to the UC catalog name. Namespaces are UC schemas, and
UC vends short-lived S3 credentials per table.

A second notebook service, `marimo-iceberg`, runs these notebooks on
**Spark 4.1.3 + Iceberg 1.11 + PyIceberg 0.12**. Apache Iceberg doesn't publish
an `iceberg-spark-runtime` for Spark 4.2 yet, so the Delta notebooks stay on
the Spark 4.2 `marimo-spark` image.

```bash
just uc=local start   # builds + starts everything, prints both notebook URLs
just url-iceberg      # http://localhost:2719?access_token=...
```

| Notebook | What it covers |
| --- | --- |
| [`iceberg/unitycatalog-iceberg-spark.py`](marimo-playground/notebooks/iceberg/unitycatalog-iceberg-spark.py) | Spark SQL against the IRC: namespaces + properties, a partitioned managed table, `INSERT` / `UPDATE` / `DELETE` / `MERGE`, snapshots + time travel, schema and partition evolution, CTAS + rename, and an external table with `LOCATION` |
| [`iceberg/unitycatalog-pyiceberg.py`](marimo-playground/notebooks/iceberg/unitycatalog-pyiceberg.py) | The same catalog from PyIceberg (no JVM): create with an explicit schema + partition spec, append / overwrite, filtered scans, schema evolution, row-level delete, `inspect.*`, time travel, rename |

Both notebooks build on the same seeded pet roster as the Delta notebook (see
[Shared Sanctuary Data](#shared-sanctuary-data--python-helpers)), so a pet's
`uuid` matches across the Delta and Iceberg tables and they can be joined.

Both notebooks are safe to re-run and end with a disabled teardown cell. Enable
it to drop everything they created. UC deletes a dropped **managed** table's
files in the background after `server.storage-cleanup.initial-delay` (5 minutes
in this playground's config, 7 days upstream). It never deletes **external**
table files.

> [!NOTE]
> `uc=local` runs the official
> [`unitycatalog/unitycatalog:v0.7.0`](https://hub.docker.com/r/unitycatalog/unitycatalog/tags?name=v0.7.0)
> image, pinned by digest in `docker-compose.yaml`. If you are reusing a
> Postgres volume created by UC 0.6, run `just uc=local db-upgrade` once.

## How the local stack works

Spark runs inside the marimo containers. The Delta notebooks use the Unity
Catalog Spark connector; the Iceberg notebooks use Unity Catalog's Iceberg REST
catalog. Unity Catalog stores object definitions in PostgreSQL and vends
short-lived credentials for managed-table data in RustFS. This gives local
development the same basic separation of catalog metadata, compute, and object
storage used by a cloud lakehouse.

## Local Unity Catalog + Postgres + RustFS

`just uc=local …` starts Postgres 16.3 alongside the UC server (same defaults as
upstream [postgres-example.yml](https://github.com/unitycatalog/unitycatalog/blob/main/etc/db/postgres-example.yml)).
Hibernate is pointed at it via [`etc/conf/hibernate.properties`](etc/conf/hibernate.properties).
Catalog metadata lives in the Docker volume `uc_postgres_data` and **survives**
`just down` / restarts. Wipe it with `just uc=local clean` or
`just uc=local down-volumes`.

### RustFS S3 storage

Managed table **data** lives in [RustFS](https://rustfs.com), an S3-compatible
object store, rather than a local file path — so the local stack behaves like a
cloud UC on real object storage (`storage-root.tables=s3://uc-warehouse`). A
one-shot `rustfs-init` service creates the bucket, mints a short-lived STS
credential from RustFS, and renders it into the UC server config so UC can vend
it to Spark. (This UC build has no custom-S3-endpoint support yet, so the STS
token is minted from RustFS rather than assumed by UC directly — see
[`etc/rustfs/bootstrap.sh`](etc/rustfs/bootstrap.sh). UC's own S3 calls, such as
writing Iceberg metadata and cleaning up dropped tables, reach RustFS through
the AWS SDK's `AWS_ENDPOINT_URL_S3` environment variable.)

```bash
just uc=local start
just uc=local rustfs-url
```

Open <http://localhost:9001> and log in with `RUSTFS_ACCESS_KEY` and
`RUSTFS_SECRET_KEY` (both default to `rustfsadmin`) to browse the objects your
notebooks write.

The vended STS credential **expires** (default 12h). If managed-table reads or
writes start failing with credential errors, refresh it — the bucket and its
data are left untouched:

```bash
just uc=local rotate-creds  # re-mint the STS credential + restart UC
```

Object data lives in the `rustfs_data` volume (wiped by
`just uc=local clean` or `just uc=local down-volumes`). Tune the bucket,
credentials, region, and STS lifetime with `RUSTFS_*`, `UC_STORAGE_BUCKET`,
`S3_REGION`, and `STS_DURATION_SECONDS` in `.env`.

## Authentication (optional)

The bundled UC starts with auth **disabled**: no tokens, and every caller can do
everything, including getting S3 credentials for any table. Turn it on to try
Unity Catalog's access control with a set of demo users:

```bash
just uc=local demo-auth                         # start with auth on, seed demo users, print the admin token
just uc=local token-for lisa@uc-demos.dev       # mint a token for a demo user
just uc=local grant grant -t schema -n demo.workshop -p robert@uc-demos.dev -P SELECT
just uc=local auth=disable set-auth             # switch back to open mode (restarts UC)
```

[`docs/uc/authentication.md`](docs/uc/authentication.md) explains why auth matters,
how tokens and grants work here, and what each recipe does.
[`docs/uc/getting-started.md`](docs/uc/getting-started.md) walks through both modes
step by step.

## Stop or reset the environment

Stop containers and networks while keeping PostgreSQL metadata and RustFS table
data:

```bash
just uc=local down
# or: docker compose --profile local-uc down
```

To reset everything, delete the named volumes and the locally built marimo
images:

```bash
just uc=local clean
```

> [!CAUTION]
> `clean` permanently deletes the local Unity Catalog metadata and all managed
> table data stored by the playground.

## Troubleshooting

### Docker is not running

Start Docker Desktop and wait for its engine to become ready:

```bash
open -a Docker
docker info
```

### The `uc-shared` network is missing

The `just` commands create this network automatically. If Compose was invoked
directly or startup was interrupted, recreate it with:

```bash
just net
```

### The first Spark session is slow

Spark downloads Delta Lake (or the Iceberg runtime), the Unity Catalog
connector, Hadoop AWS, and their transitive dependencies the first time a
notebook initializes. They are cached in your host `~/.ivy2`, which is
bind-mounted into both notebook containers, so later sessions and rebuilt
containers start without downloading them again. Behind a corporate network,
set `MAVEN_PROXY_URL` in `.env` so resolution goes straight to your proxy.

### Spark exits or runs out of memory

Give Docker Desktop at least 4 GB of memory for Spark. You can also lower or
raise `SPARK_DRIVER_MEMORY` and `SPARK_DRIVER_CORES` in `.env`, then restart the
marimo container and notebook kernel.

### Managed-table operations fail after several hours

The local RustFS STS credential expires after 12 hours by default. Refresh it
without deleting the bucket or its data:

```bash
just uc=local rotate-creds
```

## Shared Sanctuary Data — Python Helpers

Every notebook, Delta and Iceberg alike, builds its data from one shared module,
[`marimo-playground/notebooks/sanctuary.py`](marimo-playground/notebooks/sanctuary.py).
It's a seeded roster of rescue animals at four shelters (north, south, east,
west). Generation is deterministic: every notebook, engine and rerun produces
the same pets with the same `uuid`s. That means tables written in different
formats join on the pet's `uuid`, for example Delta `unity.sanctuary.pets` with
Iceberg `unity.iceberg_spark.adoptions` (on `pet_uuid`).

The module imports only the Python standard library. Its Spark helpers import
PySpark when they're called, so the Spark 4.2 (Delta) image, the Spark 4.1
(Iceberg) image and PyIceberg can all use it. The table DDL helpers live in
[`common.py`](marimo-playground/notebooks/common.py).

### `Pets` and `Adoption`

```python
@dataclass(frozen=True)
class Pets:
    uuid: str            # roster id, the join key across tables
    name: str
    age: int             # years
    adopted: bool
    species: str         # dog, cat, rabbit, parrot, hamster
    shelter: str         # north, south, east, west
    intake_at: datetime  # within 120 days before sanctuary.AS_OF

@dataclass(frozen=True)
class Adoption:
    adoption_id: int     # BIGINT in Spark
    pet_uuid: str        # Pets.uuid
    pet_name: str
    species: str
    shelter: str
    adopted_at: datetime # between intake_at and AS_OF
    fee: float           # species base fee +/- 20%
```

---

### `roster(total=100, seed=2026)` and `generate_pets(batch_size=10, total=100, seed=2026)`

`roster` returns the first `total` pets. It is prefix-stable, so
`roster(120)[:100] == roster(100)` and extra pets extend the roster without
changing earlier ones. `generate_pets` yields the same roster in batches; the
Delta notebook writes one batch per commit.

```python
pets = generate_pets(batch_size=10, total=100)

first_batch = next(pets)        # list[Pets] with 10 records
for batch in pets:              # iterate remaining batches
    print(batch)
```

---

### `adoptions(pets, start_id=1)` and `adopt(pet, adoption_id)`

`adoptions` returns one `Adoption` per pet with `adopted=True`. `adopt` creates
one for any single pet. Each pet's adoption date and fee are seeded by its
`uuid`, so they don't depend on which other pets are in the list.

---

### `pets_to_dataframe(pets, spark)`, `to_spark_dataframe(records, spark, columns=None)` and `rows(records, columns=None)`

`to_spark_dataframe` turns `Pets` or `Adoption` records into a Spark `DataFrame`
with a non-nullable schema derived from the dataclass. `pets_to_dataframe`
projects it to the 4 columns of the Delta table `unity.sanctuary.pets`
(`sanctuary.PET_COLUMNS`):

| column    | type    | nullable |
| --------- | ------- | -------- |
| `uuid`    | string  | no       |
| `name`    | string  | no       |
| `age`     | integer | no       |
| `adopted` | boolean | no       |

`rows` returns plain dicts, for example to build a PyIceberg write with
`pyarrow.Table.from_pylist(rows(pets), schema=table.schema().as_arrow())`.

```python
df = pets_to_dataframe(first_batch, spark)
df.show()
```

---

### `common.create_table_ddl(table_name, schema, properties)`

Builds a `CREATE TABLE IF NOT EXISTS ... USING DELTA` DDL string from a `StructType` schema and an optional `dict` of `TBLPROPERTIES`.

```python
props = {"delta.feature.catalogManaged": "supported"}
ddl = common.create_table_ddl("sanctuary.pets", df.schema, props)
print(ddl)
```

---

### `common.create_table_using_sql(table_name, schema, properties, spark)`

Executes the DDL produced by `create_table_ddl` via `spark.sql`. Returns an empty `DataFrame` on success.

```python
common.create_table_using_sql("sanctuary.pets", df.schema, props, spark)
```

---

### End-to-end example

The following mirrors the flow in the [`unitycatalog-delta`](marimo-playground/notebooks/unitycatalog-delta.py) notebook:

```python
import common
import sanctuary
from pyspark.sql import functions as F

# 1. Create the schema
spark.sql("CREATE SCHEMA IF NOT EXISTS unity.sanctuary")

# 2. Generate pets
pets = sanctuary.generate_pets(batch_size=10, total=100)
first_batch = next(pets)

# 3. Derive the schema from the first batch
df = sanctuary.pets_to_dataframe(first_batch, spark)
props = {"delta.feature.catalogManaged": "supported"}

# 4. Create the table
common.create_table_using_sql("sanctuary.pets", df.schema, props, spark)

# 5. Write the first batch (overwrite, so a rerun starts again from the same 100 pets)
df.writeTo("sanctuary.pets").overwrite(F.lit(True))

# 6. Write remaining batches
for batch in pets:
    sanctuary.pets_to_dataframe(batch, spark).write.format("delta").mode("append").saveAsTable("sanctuary.pets")

# 7. Verify
spark.sql("SELECT COUNT(*) AS total FROM sanctuary.pets").show()
```

## Frequently asked questions

### Can I run Unity Catalog locally on an Apple Silicon Mac?

Yes. The stack's Unity Catalog, Spark, PostgreSQL, RustFS, and AWS CLI container
images publish `linux/arm64` variants. Docker Desktop selects them automatically
on Apple Silicon. The same stack also supports Intel (`amd64`) Macs.

### Do I need a Databricks account?

No. Local mode uses the open source Unity Catalog server and runs entirely in
Docker. A Databricks account is needed only for examples that explicitly
connect to a Databricks-managed Unity Catalog.

### How is this different from the official Unity Catalog Docker setup?

The official repository provides the authoritative Unity Catalog server,
clients, APIs, and UI. This community playground builds on that server and adds
Spark, Delta Lake, PostgreSQL, S3-compatible storage, credential vending, and
interactive notebooks so you can exercise complete table workflows locally.

### Can the notebooks connect to another Unity Catalog server?

Yes. Run in remote mode and set `UC_SERVER_URL`, `UC_SERVER_PORT`, and
`UC_TOKEN` in `.env`:

```bash
just start
```

### Is this intended for production?

No. The playground is designed for local development, demonstrations, and
experimentation. Use production-grade identity, networking, storage,
observability, backups, and secret management for a deployed environment.

## Contributing

Issues and pull requests are welcome. When reporting a startup problem, include
your Mac architecture, Docker Desktop version, the command you ran, and the
relevant output from:

```bash
just uc=local ps
just uc=local logs
```

## License

Licensed under the [Apache License 2.0](LICENSE).
