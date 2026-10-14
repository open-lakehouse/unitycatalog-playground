# unitycatalog-playground

This project makes use of the open source Unity Catalog project and introduces a full notebook environment for simplifying how you work with UC OSS.

---

## Configure the Environment (optional proxies)

The build can pull Python packages through a custom PyPI proxy, which is **required when building internally at Databricks** (the public PyPI is not reachable on the corporate network). Copy the example env file and fill in the proxy values you need:

```bash
cp .env.example .env   # or: just init
```

Then edit `.env`:

```bash
# Optional PyPI proxy used at build time (blank = public PyPI)
PYPI_PROXY_URL=https://pypi-proxy.yourcompany.com/simple
# Optional Maven proxy passed to the Spark container at run time (blank = Maven Central)
MAVEN_PROXY_URL=https://maven-proxy.yourcompany.com/maven2
```

`docker compose` automatically loads `.env`, so these values are applied when you build and run below. Leaving them blank uses the public defaults.

The notebooks resolve their Spark jars (`delta-spark`, `unitycatalog-spark`, `hadoop-aws`, ...) from Maven the first time a Spark session starts. With `MAVEN_PROXY_URL` set, they go straight to the proxy through a proxy-first Ivy resolver ([`spark/ivysettings.xml`](spark/ivysettings.xml)). Resolved jars are cached in your host `~/.ivy2` (bind-mounted into the containers), so later sessions start faster.

## Build the Docker Environment

```bash
docker compose build
```

> note: This honors `PYPI_PROXY_URL` from your `.env`. You can also build the image directly with
> `docker build -t marimo-spark .`, optionally passing `--build-arg PYPI_PROXY_URL=https://pypi-proxy.your-company.com/simple`.

## Choose your Unity Catalog (local vs remote)

A single `docker-compose.yaml` backs both modes. The bundled `unitycatalog`
service sits behind a Compose [profile](https://docs.docker.com/compose/how-tos/profiles/)
(`local-uc`), so a plain `up` starts only `marimo-spark`. Every `just` recipe
takes a `uc` switch that toggles that profile:

| Mode | What you get |
| --- | --- |
| `remote` (default) | Only the `marimo-spark` notebook container. Point it at an external UC via `UC_SERVER_URL` / `UC_SERVER_PORT` / `UC_TOKEN` in `.env`. |
| `local` | Enables the `local-uc` profile: bundled `unitycatalog` + Postgres 16.3 metadata DB + [RustFS](https://rustfs.com) S3 object store (managed-table storage) **plus** `marimo-spark`, wired together for an all-in-one local stack. |

```bash
just up              # remote UC (default)  -> docker compose up
just uc=local up     # bundled local UC + marimo -> docker compose --profile local-uc up
just uc=local start  # build + bring up local UC detached, then print the marimo URL
just uc=local down   # tear down the local stack
```

The `uc` switch works with every recipe (`build`, `up`, `up-detached`, `start`,
`logs`, `ps`, `down`, …), so pass the same `uc=...` value you used to start the
stack when you tear it down.

### Network bridge

`marimo-spark` joins an **external** docker network, `uc-shared`, so it can also
reach a UC server running in a *separate* compose project. Because the network is
declared `external: true`, it must exist before Compose starts — otherwise you'll
see `network uc-shared declared as external, but could not be found`.

`just up` / `just up-detached` run `just net` first, which creates the network
idempotently. You can also run it on its own:

```bash
just net   # docker network create uc-shared (no-op if it already exists)
```

## Run the Environment

```bash
docker compose up
```

You will see the `marimo` and `unitycatalog` containers come up.


In order to run the full notebook environment, copy the ➜  URL: [http://0.0.0.0:2718?access_token=TOKEN](http://0.0.0.0:2718?access_token=TOKEN) and run it in your favorite browser.

## Using the Notebook

Once you're in the notebook environment (marimo), you simply need to **run** each cell in order (you can skip the markdown cells since they are just there to add additional context). 

You'll see a view like the one below:



  
  
When you are finished with the notebook example, you can simple **tear down the environment**.

Congrats. You've now officially written a Catalog Managed Table using Delta Lake and Unity Catalog.

## More Delta Notebooks

`marimo-spark` (port 2718) serves every notebook in `marimo-playground/notebooks/`:

| Notebook | What it covers |
| --- | --- |
| [`unitycatalog-delta.py`](marimo-playground/notebooks/unitycatalog-delta.py) | The default notebook: a catalog-managed Delta table, `unity.sanctuary.pets`, written in batches from the shared pet roster |
| [`delta-new-in-4.4.0.py`](marimo-playground/notebooks/delta-new-in-4.4.0.py) | Delta Lake 4.4.0 on Spark 4.2: identity columns (`GENERATED ALWAYS AS IDENTITY`) and `SHOW PARTITIONS` on a partitioned catalog-managed table. The full release notes are in [`docs/releases/delta-4.4.0-release.md`](docs/releases/delta-4.4.0-release.md) |
| [`metric-views.py`](marimo-playground/notebooks/metric-views.py) | Unity Catalog metric views: bootstraps an `ecomm` catalog, builds an orders table, defines a metric view with a `region` dimension and a 7-day sales measure, then queries it with `measure(...)` |
| [`databricks/external-access-unitycatalog-delta-managed-read.py`](marimo-playground/notebooks/databricks/external-access-unitycatalog-delta-managed-read.py) | Reads managed tables in a Databricks Unity Catalog from local Spark through external data access and credential vending |

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

> note: `uc=local` runs the official
> [`unitycatalog/unitycatalog:v0.7.0`](https://hub.docker.com/r/unitycatalog/unitycatalog/tags?name=v0.7.0)
> image, pinned by digest in `docker-compose.yaml`. If you are
> reusing a Postgres volume created by UC 0.6, run `just uc=local db-upgrade`
> once.

## Local Unity Catalog + Postgres + RustFS

`just uc=local …` starts Postgres 16.3 alongside the UC server (same defaults as
upstream [postgres-example.yml](https://github.com/unitycatalog/unitycatalog/blob/main/etc/db/postgres-example.yml)).
Hibernate is pointed at it via [`etc/conf/hibernate.properties`](etc/conf/hibernate.properties).
Catalog metadata lives in the Docker volume `uc_postgres_data` and **survives**
`just down` / restarts. Wipe it with `just clean` or `just down-volumes`.

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
just uc=local start        # brings up RustFS + init + UC + marimo
just uc=local rustfs-url    # print the RustFS console (:9001) + S3 API (:9000) URLs
```

Open the console at `http://localhost:9001` and log in with `RUSTFS_ACCESS_KEY` /
`RUSTFS_SECRET_KEY` (defaults `rustfsadmin` / `rustfsadmin`) to browse the objects
your notebooks write.

The vended STS credential **expires** (default 12h). If managed-table reads or
writes start failing with credential errors, refresh it — the bucket and its
data are left untouched:

```bash
just uc=local rotate-creds  # re-mint the STS credential + restart UC
```

Object data lives in the `rustfs_data` volume (wiped by `just clean` /
`just down-volumes`). Tune the bucket, credentials, region, and STS lifetime via
`RUSTFS_*` / `UC_STORAGE_BUCKET` / `S3_REGION` / `STS_DURATION_SECONDS` in `.env`.

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

## Tear Down the Environment

Stop containers and networks (keeps the Postgres volume):

```bash
just uc=local down
# or: docker compose --profile local-uc down
```

Also delete named volumes (wipes local UC Postgres metadata **and** all RustFS
managed-table data) and the locally built marimo images:

```bash
just clean
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

