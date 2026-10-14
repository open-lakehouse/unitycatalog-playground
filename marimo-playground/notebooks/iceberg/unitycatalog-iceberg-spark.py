import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Native Apache Iceberg tables in Unity Catalog 0.7 — Apache Spark
    ---
    Unity Catalog 0.7 turns its **Iceberg REST catalog** (IRC) into a full
    read/write catalog, on by default (`server.iceberg-table.enabled=true`).
    Iceberg clients create, commit, rename and drop **native Iceberg tables**
    through `/api/2.1/unity-catalog/iceberg`, and UC governs them like any other
    table.

    *Native* means there's no Delta underneath: no conversion, no UniForm. This
    also differs from Databricks managed Iceberg tables. And as with Delta, a
    UC Iceberg table is:

    - **managed** when it is created **without** a `LOCATION` (UC picks the
      storage path under its managed root and reclaims it after `DROP`), or
    - **external** when it is created **with** a `LOCATION` you own.

    Once a table exists, access is identical for both.

    This notebook drives the whole lifecycle from Spark, using Iceberg's own
    REST `SparkCatalog` (no UC Spark connector involved):

    1. Wire Spark to UC's Iceberg REST catalog and inspect the `/v1/config` handshake.
    2. Create a namespace (= UC schema) and update its properties.
    3. Create a **managed**, hidden-partitioned Iceberg table and load it.
    4. Row-level `UPDATE` / `DELETE` / `MERGE INTO`, snapshots and time travel.
    5. Schema and partition evolution, and what UC records about the table.
    6. `CREATE OR REPLACE TABLE ... AS SELECT` (staged create) and `RENAME`.
    7. An **external** Iceberg table at a `LOCATION`.

    > **Prerequisites.** Run this from the **`marimo-iceberg`** service
    > (`just uc=local start`, then open the `:2719` URL). Iceberg ships
    > `iceberg-spark-runtime` only for **Spark 4.0 / 4.1**, so this image runs
    > Spark 4.1 with Iceberg 1.11, the combination UC 0.7 is tested against.
    """)
    return


@app.cell
def _():
    import json
    from dataclasses import replace
    from datetime import timedelta
    from urllib.parse import urlparse

    import marimo as mo
    from pyspark.sql import SparkSession

    # iceberg_common wires Spark's Iceberg REST SparkCatalog to UC (uri,
    # warehouse, S3FileIO + the RustFS endpoint) and reuses the proxy-first Ivy
    # resolver from ../common.py.
    import iceberg_common as ic

    # ../sanctuary.py: the seeded pet roster shared with the Delta and PyIceberg
    # notebooks (importable once iceberg_common has put ../ on sys.path).
    import sanctuary

    CATALOG = ic.CATALOG
    SCHEMA = "iceberg_spark"
    FQ_SCHEMA = f"{CATALOG}.{SCHEMA}"
    ADOPTIONS = f"{FQ_SCHEMA}.adoptions"
    SHELTER_STATS = f"{FQ_SCHEMA}.adoptions_by_shelter"
    SHELTER_SUMMARY = f"{FQ_SCHEMA}.shelter_summary"
    ARCHIVE = f"{FQ_SCHEMA}.adoptions_archive"

    # The Iceberg REST catalog only serves UC catalogs that already exist (an
    # unknown warehouse is a 404), so make sure `unity` is there first.
    ic.ensure_catalog(CATALOG)

    spark: SparkSession = ic.initialize_spark(app_name="UCIcebergSpark", catalog=CATALOG)
    return (
        ADOPTIONS,
        ARCHIVE,
        CATALOG,
        FQ_SCHEMA,
        SCHEMA,
        SHELTER_STATS,
        SHELTER_SUMMARY,
        SparkSession,
        ic,
        json,
        mo,
        replace,
        sanctuary,
        spark,
        timedelta,
        urlparse,
    )


@app.cell
def _(CATALOG, ic, spark: "SparkSession"):
    print("Spark:", spark.version)
    print("Iceberg runtime:", f"iceberg-spark-runtime-{ic.SPARK_VERSION}_2.13:{ic.ICEBERG_VERSION}")
    print("UC Iceberg REST catalog (uri):", ic.iceberg_rest_uri())
    print("warehouse (UC catalog):", CATALOG)
    print("S3 endpoint override:", ic.s3_endpoint() or "(none: AWS S3)")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## The Iceberg REST handshake

    The Spark catalog `unity` is registered as:

    ~~~properties
    spark.sql.catalog.unity           = org.apache.iceberg.spark.SparkCatalog
    spark.sql.catalog.unity.type      = rest
    spark.sql.catalog.unity.uri       = http://unitycatalog:8080/api/2.1/unity-catalog/iceberg
    spark.sql.catalog.unity.warehouse = unity          # the UC catalog name
    spark.sql.catalog.unity.io-impl   = org.apache.iceberg.aws.s3.S3FileIO
    ~~~

    On startup the client calls `GET /v1/config?warehouse=unity`. UC answers with
    a `prefix` override (`catalogs/unity`), so every later call goes to
    `/v1/catalogs/unity/...`, plus the list of `endpoints` this server supports.
    In 0.7 that list covers namespace create/drop/properties, table
    create/commit/drop/rename, and a per-table **`/credentials`** endpoint that
    lets long-running clients renew the storage credentials UC vends.
    """)
    return


@app.cell
def _(CATALOG, ic, json):
    _config = ic.uc_api(f"/v1/config?warehouse={CATALOG}", base=ic.ICEBERG_REST_PATH)
    print(json.dumps(_config, indent=2))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Namespaces are UC schemas

    `CREATE NAMESPACE` becomes `POST /v1/catalogs/unity/namespaces`, which creates
    the UC schema `unity.iceberg_spark`. `ALTER NAMESPACE ... SET DBPROPERTIES`
    uses the namespace-properties endpoint that is new in 0.7. Iceberg
    namespace properties, including Spark's `comment` and `owner`, are stored
    as UC schema properties.
    """)
    return


@app.cell
def _(FQ_SCHEMA, spark: "SparkSession"):
    spark.sql(f"""
    CREATE NAMESPACE IF NOT EXISTS {FQ_SCHEMA}
    COMMENT 'Native Iceberg tables written by Spark'
    WITH DBPROPERTIES ('owner_team' = 'devrel')
    """)
    spark.sql(f"ALTER NAMESPACE {FQ_SCHEMA} SET DBPROPERTIES ('purpose' = 'uc-0.7-reference')")
    namespace_ready = FQ_SCHEMA
    return (namespace_ready,)


@app.cell
def _(CATALOG, ic, json, namespace_ready, spark: "SparkSession"):
    spark.sql(f"SHOW NAMESPACES IN {CATALOG}").show(truncate=False)
    spark.sql(f"DESCRIBE NAMESPACE EXTENDED {namespace_ready}").show(truncate=False)

    # The same object through the UC schemas API.
    _schema = ic.uc_api(f"/schemas/{namespace_ready}")
    print(json.dumps({k: _schema.get(k) for k in ("full_name", "comment", "properties")}, indent=2))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A managed Iceberg table

    No `LOCATION`, so this is a **managed** table: UC allocates its storage under
    the managed root (`s3://uc-warehouse/__unitystorage/...` in the local RustFS
    stack), writes the first `metadata.json` itself, and vends credentials scoped
    to that path.

    The table uses Iceberg **hidden partitioning**: `days(adopted_at)` is derived
    from the timestamp, so queries filter on `adopted_at` and never reference a
    partition column.

    `CREATE OR REPLACE` keeps the notebook re-runnable. On a re-run Iceberg
    swaps in the original schema and partition spec with no current snapshot,
    and keeps the earlier snapshots in the table's history.
    """)
    return


@app.cell
def _(ADOPTIONS, namespace_ready, spark: "SparkSession"):
    _ = namespace_ready
    spark.sql(f"""
    CREATE OR REPLACE TABLE {ADOPTIONS} (
      adoption_id BIGINT NOT NULL COMMENT 'surrogate key',
      pet_uuid    STRING NOT NULL COMMENT 'sanctuary roster uuid (unity.sanctuary.pets.uuid)',
      pet_name    STRING,
      species     STRING,
      shelter     STRING,
      adopted_at  TIMESTAMP,
      fee         DOUBLE
    )
    USING iceberg
    PARTITIONED BY (species, days(adopted_at))
    TBLPROPERTIES ('format-version' = '2')
    """)
    adoptions_ready = ADOPTIONS
    return (adoptions_ready,)


@app.cell
def _(adoptions_ready, ic, json, spark: "SparkSession"):
    spark.sql(f"DESCRIBE TABLE EXTENDED {adoptions_ready}").show(50, truncate=False)

    # UC's view of the same table: a MANAGED table whose format is ICEBERG.
    _table = ic.uc_table(adoptions_ready)
    print(json.dumps(
        {k: _table.get(k) for k in ("full_name", "table_type", "data_source_format", "storage_location")},
        indent=2,
    ))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Load the sanctuary's adoptions

    The rows come from the shared sanctuary roster in `notebooks/sanctuary.py`.
    The Delta notebook writes the same 100 pets to `unity.sanctuary.pets`, and
    here every pet with `adopted = true` gets one adoption. `pet_uuid` is that
    pet's roster `uuid`, so this Iceberg table joins with the Delta table on it.

    The adoptions are appended in two batches with `DataFrameWriterV2`. Each
    write is one Iceberg commit (one snapshot), sent to UC as
    `POST /v1/catalogs/unity/namespaces/iceberg_spark/tables/adoptions`.
    """)
    return


@app.cell
def _(sanctuary):
    roster = sanctuary.roster()
    roster_adoptions = sanctuary.adoptions(roster)
    print(f"{len(roster)} pets in the roster, {len(roster_adoptions)} adopted")
    return roster, roster_adoptions


@app.cell
def _(adoptions_ready, roster_adoptions, sanctuary, spark: "SparkSession"):
    for _batch in (roster_adoptions[:30], roster_adoptions[30:]):
        sanctuary.to_spark_dataframe(_batch, spark).writeTo(adoptions_ready).append()
    loaded = True
    return (loaded,)


@app.cell
def _(adoptions_ready, loaded, spark: "SparkSession"):
    _ = loaded
    spark.sql(f"""
    SELECT species, COUNT(*) AS adoptions, ROUND(SUM(fee), 2) AS fees
    FROM {adoptions_ready}
    GROUP BY species
    ORDER BY adoptions DESC
    """).show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Row-level changes: `UPDATE`, `DELETE`, `MERGE INTO`

    The Iceberg SQL extensions (`IcebergSparkSessionExtensions`) add row-level
    DML. Every statement is one atomic commit through UC's Iceberg REST catalog.
    Concurrent writers are resolved with Iceberg's optimistic `requirements`
    checks on the commit.
    """)
    return


@app.cell
def _(
    adoptions_ready,
    loaded,
    replace,
    roster,
    roster_adoptions,
    sanctuary,
    spark: "SparkSession",
):
    _ = loaded
    # The south shelter waives fees for senior-friendly species.
    spark.sql(f"UPDATE {adoptions_ready} SET fee = 0.0 WHERE shelter = 'south' AND species IN ('cat', 'rabbit')")

    # Hamsters moved to a partner program.
    spark.sql(f"DELETE FROM {adoptions_ready} WHERE species = 'hamster'")

    # One MERGE: three dog adoptions billed without the 20% event discount
    # match and get the corrected fee; three pets still waiting in the roster
    # are adopted at last and don't match, so they're inserted (ids from 1001).
    _corrections = [
        replace(_a, fee=round(_a.fee * 0.8, 2)) for _a in roster_adoptions if _a.species == "dog"
    ][:3]
    _waiting = [_p for _p in roster if not _p.adopted][:3]
    _new = [sanctuary.adopt(_p, adoption_id=1001 + _i) for _i, _p in enumerate(_waiting)]
    sanctuary.to_spark_dataframe(_corrections + _new, spark).createOrReplaceTempView("adoption_updates")
    spark.sql(f"""
    MERGE INTO {adoptions_ready} AS t
    USING adoption_updates AS s
    ON t.adoption_id = s.adoption_id
    WHEN MATCHED THEN UPDATE SET t.fee = s.fee
    WHEN NOT MATCHED THEN INSERT *
    """)
    dml_done = True
    return (dml_done,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Snapshots, time travel and data files

    Every commit above is an Iceberg snapshot. The `ancestors_of` procedure walks
    the current snapshot's lineage, and `VERSION AS OF <snapshot_id>` reads any
    of them. The `_file`, `_partition` and `_spec_id` **metadata columns** show
    which data files hold each row. Spark wrote those files to RustFS with the
    credentials UC vended.

    > **UC 0.7.0:** Iceberg *metadata tables* (`adoptions.snapshots`,
    > `.files`, `.history`, ...) don't resolve from Spark yet. Iceberg clients
    > first try `loadTable(namespace=iceberg_spark.adoptions, table=snapshots)`
    > and fall back to the metadata table only on `NoSuchTableException`. UC
    > answers `NoSuchNamespaceException` instead. PyIceberg's `table.inspect`
    > is unaffected (see the PyIceberg notebook).
    """)
    return


@app.cell
def _(CATALOG, adoptions_ready, dml_done, spark: "SparkSession"):
    _ = dml_done
    snapshots = spark.sql(f"CALL {CATALOG}.system.ancestors_of(table => '{adoptions_ready}')")
    snapshots.show(truncate=False)
    return (snapshots,)


@app.cell
def _(adoptions_ready, snapshots, spark: "SparkSession"):
    # ancestors_of lists the current snapshot first and the oldest ancestor last.
    _rows = snapshots.collect()
    for _label, _snap in (("first", _rows[-1]), ("current", _rows[0])):
        _count = spark.sql(
            f"SELECT COUNT(*) AS n FROM {adoptions_ready} VERSION AS OF {_snap.snapshot_id}"
        ).first().n
        print(f"{_label:>8} snapshot {_snap.snapshot_id}: {_count} rows")
    return


@app.cell
def _(adoptions_ready, dml_done, spark: "SparkSession"):
    _ = dml_done
    spark.sql(f"""
    SELECT _spec_id AS spec_id,
           _partition AS partition,
           COUNT(*) AS rows,
           COUNT(DISTINCT _file) AS files,
           MIN(_file) AS sample_file
    FROM {adoptions_ready}
    GROUP BY _spec_id, _partition
    ORDER BY rows DESC
    LIMIT 5
    """).show(truncate=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Schema and partition evolution

    Both are metadata-only commits: existing data files are not rewritten.
    `ADD COLUMN` assigns a new Iceberg field id. `ADD PARTITION FIELD` starts a
    new partition spec that applies to data written from now on. UC keeps its
    own column list in sync with the Iceberg schema, so the new column also
    shows up in the UC tables API.
    """)
    return


@app.cell
def _(adoptions_ready, dml_done, spark: "SparkSession"):
    _ = dml_done
    # Guarded so this cell can also be re-run on its own.
    if "microchipped" not in spark.table(adoptions_ready).columns:
        spark.sql(f"ALTER TABLE {adoptions_ready} ADD COLUMN microchipped BOOLEAN COMMENT 'chip registered at adoption'")
    _partition_fields = [
        _row.data_type
        for _row in spark.sql(f"DESCRIBE TABLE {adoptions_ready}").collect()
        if _row.col_name.startswith("Part ")
    ]
    if "shelter" not in _partition_fields:
        spark.sql(f"ALTER TABLE {adoptions_ready} ADD PARTITION FIELD shelter")
    spark.sql(f"UPDATE {adoptions_ready} SET microchipped = species IN ('dog', 'cat')")
    evolved = True
    return (evolved,)


@app.cell
def _(adoptions_ready, evolved, ic, spark: "SparkSession"):
    _ = evolved
    spark.sql(f"DESCRIBE TABLE {adoptions_ready}").show(truncate=False)

    # The UPDATE above rewrote every row, so all data now sits under the new spec.
    spark.sql(f"SELECT _spec_id AS spec_id, COUNT(*) AS rows FROM {adoptions_ready} GROUP BY _spec_id").show()

    _uc_columns = ic.uc_table(adoptions_ready)["columns"]
    print("UC columns:", [(c["name"], c["type_name"]) for c in _uc_columns])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## `CREATE OR REPLACE TABLE ... AS SELECT` (a staged create) and `RENAME`

    Iceberg's `SparkCatalog` runs CTAS/RTAS atomically. The first time, it
    *stages* the create (`createTable` with `stage-create: true`), writes the
    data, then commits the table in one step. Readers never see an empty table.
    Staged creates are new in UC 0.7. On re-runs the table already exists, so
    the same statement becomes an atomic replace.

    `ALTER TABLE ... RENAME TO` maps to `POST /v1/catalogs/unity/tables/rename`.
    """)
    return


@app.cell
def _(SHELTER_STATS, SHELTER_SUMMARY, adoptions_ready, evolved, spark: "SparkSession"):
    _ = evolved
    spark.sql(f"""
    CREATE OR REPLACE TABLE {SHELTER_STATS}
    USING iceberg
    AS SELECT shelter,
              species,
              COUNT(*)            AS adoptions,
              ROUND(SUM(fee), 2)  AS fees,
              ROUND(AVG(CAST(microchipped AS INT)) * 100, 1) AS pct_microchipped
       FROM {adoptions_ready}
       GROUP BY shelter, species
    """)

    # Re-runnable rename: clear the previous run's target first. RENAME TO takes
    # a name relative to the source catalog, so drop the `unity.` prefix.
    spark.sql(f"DROP TABLE IF EXISTS {SHELTER_SUMMARY}")
    spark.sql(f"ALTER TABLE {SHELTER_STATS} RENAME TO {SHELTER_SUMMARY.split('.', 1)[1]}")
    summary_ready = SHELTER_SUMMARY
    return (summary_ready,)


@app.cell
def _(FQ_SCHEMA, summary_ready, spark: "SparkSession"):
    spark.sql(f"SELECT * FROM {summary_ready} ORDER BY shelter, adoptions DESC").show()
    spark.sql(f"SHOW TABLES IN {FQ_SCHEMA}").show(truncate=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## An external Iceberg table

    Adding `LOCATION` makes the table **external**: you choose the path, and UC
    registers the table and vends credentials for that path. Dropping it
    removes only the catalog entry; the files stay where you put them.

    Here the location is a prefix in the same bucket that backs the managed
    root (derived from the managed table's `storage_location`). With
    `server.authorization=enable`, creating it also requires privileges on a
    matching UC **external location**.
    """)
    return


@app.cell
def _(ARCHIVE, SCHEMA, adoptions_ready, evolved, ic, urlparse):
    _ = evolved
    _managed_location = ic.uc_table(adoptions_ready)["storage_location"]
    _parsed = urlparse(_managed_location)
    archive_location = f"{_parsed.scheme}://{_parsed.netloc}/external/{SCHEMA}/{ARCHIVE.rsplit('.', 1)[1]}"
    print("managed table location: ", _managed_location)
    print("external table location:", archive_location)
    return (archive_location,)


@app.cell
def _(
    ARCHIVE,
    adoptions_ready,
    archive_location,
    sanctuary,
    spark: "SparkSession",
    timedelta,
):
    spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {ARCHIVE} (
      adoption_id  BIGINT NOT NULL,
      pet_uuid     STRING NOT NULL,
      pet_name     STRING,
      species      STRING,
      shelter      STRING,
      adopted_at   TIMESTAMP,
      fee          DOUBLE,
      microchipped BOOLEAN
    )
    USING iceberg
    LOCATION '{archive_location}'
    """)
    # Archive adoptions older than 30 days, relative to the roster's AS_OF time.
    _cutoff = (sanctuary.AS_OF - timedelta(days=30)).isoformat()
    spark.sql(f"""
    INSERT OVERWRITE {ARCHIVE}
    SELECT adoption_id, pet_uuid, pet_name, species, shelter, adopted_at, fee, microchipped
    FROM {adoptions_ready}
    WHERE adopted_at < TIMESTAMP '{_cutoff}'
    """)
    archive_ready = ARCHIVE
    return (archive_ready,)


@app.cell
def _(adoptions_ready, archive_ready, ic, spark: "SparkSession"):
    print("archived rows:", spark.table(archive_ready).count())
    for _name in (adoptions_ready, archive_ready):
        _t = ic.uc_table(_name)
        print(f"{_t['full_name']:<40} {_t['table_type']:<9} {_t['data_source_format']:<8} {_t['storage_location']}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Dropping tables

    - **Managed**: `DROP TABLE` removes the table from UC and, in the same
      transaction, queues a storage-cleanup task. A background worker deletes
      the data after `server.storage-cleanup.initial-delay`. The default is
      `P7D`; the playground sets `PT5M`. This delay is not an undrop window.
      Until cleanup finishes, the path is protected from reuse.
    - **External**: `DROP TABLE` removes only the catalog entry. Files under the
      `LOCATION` are left untouched.

    Enable the cell below to tear the demo down.
    """)
    return


@app.cell(disabled=True)
def _(ADOPTIONS, ARCHIVE, FQ_SCHEMA, SHELTER_STATS, SHELTER_SUMMARY, spark: "SparkSession"):
    for _table in (SHELTER_SUMMARY, SHELTER_STATS, ARCHIVE, ADOPTIONS):
        spark.sql(f"DROP TABLE IF EXISTS {_table}")
    spark.sql(f"DROP NAMESPACE IF EXISTS {FQ_SCHEMA}")
    return


if __name__ == "__main__":
    app.run()
