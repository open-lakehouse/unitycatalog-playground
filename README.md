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

`just up` / `just up-detached` / `just jars` run `just net` first, which creates
the network idempotently. You can also run it on its own:

```bash
just net   # docker network create uc-shared (no-op if it already exists)
```

## Pre-download Spark jars (optional, faster startup)

By default each notebook resolves its jars (`delta-spark`, `unitycatalog-spark`,
`hadoop-aws`, and their transitive dependencies) from Maven the **first time** a
Spark session is created. That resolution can take several minutes and needs
network access — and it repeats on a fresh container or whenever the Ivy cache
is cleared.

`just jars` does that resolution **once, up front**, and drops the jars into
`./spark/jars` (bind-mounted to `/spark/jars` in the container). A notebook that
reads from that directory then starts Spark straight off the local classpath —
no per-session Maven round-trip.

```bash
just build   # the image must exist first
just jars    # resolve + download into ./spark/jars
just up      # start the environment
```

> note: `just jars` resolves through `MAVEN_PROXY_URL` (from your `.env`) when it is
> set. It does this with a proxy-only Ivy resolver (`spark/ivysettings.xml`) so
> resolution goes **straight to the proxy** instead of trying the firewalled
> `repo1.maven.org` / `spark-packages` defaults first. With `MAVEN_PROXY_URL` blank,
> it resolves from public Maven Central as usual.

The downloaded jars are git-ignored (the directory is kept via
`spark/jars/.gitkeep`), so they never get committed. Re-running `just jars` is
safe — existing jars are not re-downloaded. The coordinates it fetches live in
the `jars_packages` variable at the top of the `[Justfile](Justfile)`; keep them
in sync with the `spark.jars.packages` used in the notebooks.

**When to use it**

- ✅ You want fast, repeatable notebook startup (especially across container
rebuilds, or behind a slow/locked-down corporate network).
- ✅ You're iterating in the `[delta_4.3_playground](marimo-playground/notebooks/delta_4.3_playground.py)`
notebook, which **prefers** `/spark/jars` and only falls back to Maven when the
directory is empty.
- ⏭️ You can skip it for a quick one-off run — the notebooks still resolve from
Maven automatically when `./spark/jars` is empty (e.g. a local `uv` run, where
`/spark/jars` doesn't exist at all).

> tip: The first cell of `delta_4.3_playground` prints which path is active —
> `Jar source: local (...)` vs `Jar source: Maven (...)` — so you can confirm the
> pre-downloaded jars are being used.

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
[`etc/rustfs/bootstrap.sh`](etc/rustfs/bootstrap.sh).)

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

## Tear Down the Environment

Stop containers and networks (keeps the Postgres volume):

```bash
just uc=local down
# or: docker compose --profile local-uc down
```

Also delete named volumes (wipes local UC Postgres metadata **and** all RustFS
managed-table data) and the marimo image:

```bash
just clean
```

## Catalog Managed Tables — Python Helpers

The helper module at `[delta/python/catalog-managed.py](delta/python/catalog-managed.py)` provides a set of reusable utilities for creating and populating catalog-managed Delta tables via PySpark. These same helpers are used interactively in the `[marimo-playground/notebooks/unitycatalog-delta.py](marimo-playground/notebooks/unitycatalog-delta.py)` notebook.

### `Pets` dataclass

A simple dataclass representing a rescue animal record.

```python
@dataclass
class Pets:
    uuid: str    # unique identifier
    name: str    # pet name
    age: int     # age in years
    adopted: bool
```

---

### `generate_pets(batch_size=10, total=100)`

Generates `total` random `Pets` records and yields them in batches of `batch_size`.

```python
pets = generate_pets(batch_size=10, total=100)

first_batch = next(pets)        # list[Pets] with 10 records
for batch in pets:              # iterate remaining batches
    print(batch)
```

---

### `pets_to_dataframe(pets, spark)`

Converts a `list[Pets]` batch into a Spark `DataFrame` with an explicit schema.

```python
df = pets_to_dataframe(first_batch, spark)
df.show()
```

Schema:


| column    | type    | nullable |
| --------- | ------- | -------- |
| `uuid`    | string  | no       |
| `name`    | string  | no       |
| `age`     | integer | no       |
| `adopted` | boolean | no       |


---

### `create_table_ddl(table_name, schema, properties)`

Builds a `CREATE TABLE IF NOT EXISTS ... USING DELTA` DDL string from a `StructType` schema and an optional `dict` of `TBLPROPERTIES`.

```python
props = {"delta.feature.catalogManaged": "supported"}
ddl = create_table_ddl("sanctuary.pets", df.schema, props)
print(ddl)
```

---

### `create_table_using_sql(table_name, schema, properties, spark)`

Executes the DDL produced by `create_table_ddl` via `spark.sql`. Returns an empty `DataFrame` on success.

```python
create_table_using_sql("sanctuary.pets", df.schema, props, spark)
```

---

### End-to-end example

The following mirrors the flow in the `[unitycatalog-delta](marimo-playground/notebooks/unitycatalog-delta.py)` notebook:

```python
# 1. Create the schema
spark.sql("CREATE SCHEMA IF NOT EXISTS unity.sanctuary")

# 2. Generate pets
pets = generate_pets(batch_size=10, total=100)
first_batch = next(pets)

# 3. Derive the schema from the first batch
df = pets_to_dataframe(first_batch, spark)
props = {"delta.feature.catalogManaged": "supported"}

# 4. Create the table
create_table_using_sql("sanctuary.pets", df.schema, props, spark)

# 5. Write the first batch
df.write.format("delta").mode("append").saveAsTable("sanctuary.pets")

# 6. Write remaining batches
for batch in pets:
    pets_to_dataframe(batch, spark).write.format("delta").mode("append").saveAsTable("sanctuary.pets")

# 7. Verify
spark.sql("SELECT COUNT(*) AS total FROM sanctuary.pets").show()
```

