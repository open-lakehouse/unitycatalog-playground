import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Native Apache Iceberg tables in Unity Catalog 0.7 — PyIceberg
    ---
    [PyIceberg](https://py.iceberg.apache.org/) is a pure-Python Iceberg client:
    no JVM and no Spark. It talks to Unity Catalog through the same **Iceberg
    REST catalog** (`/api/2.1/unity-catalog/iceberg`) as the Spark notebook,
    and reads and writes Parquet data files directly with PyArrow, using the
    short-lived storage credentials UC vends for each table.

    In UC 0.7 the Iceberg REST catalog is read/write and governed. A table created
    without a location is a **managed** native Iceberg table. With a location
    it is **external**. This notebook:

    1. Loads a PyIceberg `RestCatalog` bound to the UC catalog `unity`.
    2. Creates a namespace (= UC schema) and updates its properties.
    3. Creates a **managed** partitioned Iceberg table from a PyIceberg schema.
    4. Overwrites, appends and scans with filter pushdown.
    5. Inspects snapshots, partitions and files, and time-travels.
    6. Evolves the schema, deletes rows, and renames a table.
    7. Shows what UC records about the table, and how drop/purge behave.

    > Run this from the **`marimo-iceberg`** service (`:2719`), which ships
    > `pyiceberg[pyarrow,pandas]`. PyIceberg needs no Spark, so the notebook
    > also runs under `just edit-iceberg` on your laptop: point `UC_SERVER_URL`
    > at `http://localhost:8080` and `S3_ENDPOINT_URL` at `http://localhost:9000`.
    """)
    return


@app.cell
def _():
    import json

    import marimo as mo
    import pyarrow as pa
    import pyiceberg
    from pyiceberg.expressions import And, EqualTo, GreaterThanOrEqual
    from pyiceberg.partitioning import PartitionField, PartitionSpec
    from pyiceberg.schema import Schema
    from pyiceberg.transforms import IdentityTransform, MonthTransform
    from pyiceberg.types import (
        BooleanType,
        IntegerType,
        NestedField,
        StringType,
        TimestamptzType,
    )

    # iceberg_common builds the RestCatalog properties (uri, warehouse, token,
    # RustFS endpoint) from the same env vars the Spark notebooks use.
    import iceberg_common as ic

    # ../sanctuary.py: the seeded pet roster shared with the Delta and Spark
    # notebooks (importable once iceberg_common has put ../ on sys.path).
    import sanctuary

    CATALOG = ic.CATALOG
    NAMESPACE = "iceberg_py"
    PETS = f"{NAMESPACE}.pets"
    ADOPTED_STAGING = f"{NAMESPACE}.adopted_staging"
    ADOPTED = f"{NAMESPACE}.adopted_pets"

    # The UC catalog must exist before the REST handshake (unknown warehouse -> 404).
    ic.ensure_catalog(CATALOG)
    catalog = ic.load_pyiceberg_catalog(CATALOG)
    return (
        ADOPTED,
        ADOPTED_STAGING,
        And,
        BooleanType,
        CATALOG,
        EqualTo,
        GreaterThanOrEqual,
        IdentityTransform,
        IntegerType,
        MonthTransform,
        NAMESPACE,
        NestedField,
        PETS,
        PartitionField,
        PartitionSpec,
        Schema,
        StringType,
        TimestamptzType,
        catalog,
        ic,
        json,
        mo,
        pa,
        pyiceberg,
        sanctuary,
    )


@app.cell
def _(CATALOG, catalog, ic, json, pyiceberg):
    print("PyIceberg:", pyiceberg.__version__)
    print("catalog:", type(catalog).__name__, "->", ic.iceberg_rest_uri(), f"(warehouse={CATALOG})")
    _props = {k: ("***" if k == "token" else v) for k, v in ic.pyiceberg_properties(CATALOG).items()}
    print(json.dumps(_props, indent=2))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Namespaces

    A namespace is a UC schema inside the `unity` catalog. Namespace properties
    can be updated in place (new in 0.7) and come back as UC schema properties.
    """)
    return


@app.cell
def _(NAMESPACE, catalog):
    catalog.create_namespace_if_not_exists(
        NAMESPACE,
        properties={"comment": "Native Iceberg tables written by PyIceberg", "owner_team": "devrel"},
    )
    print(catalog.update_namespace_properties(NAMESPACE, updates={"purpose": "uc-0.7-reference"}))
    print("namespaces:", catalog.list_namespaces())
    print("properties:", catalog.load_namespace_properties(NAMESPACE))
    namespace_ready = NAMESPACE
    return (namespace_ready,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A managed, partitioned Iceberg table

    The columns are the shared `sanctuary.Pets` record (`notebooks/sanctuary.py`),
    in field order. The first four (`uuid`, `name`, `age`, `adopted`) are the
    Delta table `unity.sanctuary.pets`, and both tables hold the same seeded pets.

    The schema carries explicit Iceberg field ids. The partition spec uses
    **hidden partitioning**: `identity(species)` and `month(intake_at)`. No
    `location` is passed, so UC creates a **managed** table under its managed
    root and writes the first `metadata.json` itself.
    """)
    return


@app.cell
def _(
    BooleanType,
    IdentityTransform,
    IntegerType,
    MonthTransform,
    NestedField,
    PartitionField,
    PartitionSpec,
    Schema,
    StringType,
    TimestamptzType,
):
    PETS_SCHEMA = Schema(
        NestedField(1, "uuid", StringType(), required=True, doc="sanctuary roster id"),
        NestedField(2, "name", StringType(), required=True),
        NestedField(3, "age", IntegerType(), required=True, doc="years"),
        NestedField(4, "adopted", BooleanType(), required=True),
        NestedField(5, "species", StringType(), required=True),
        NestedField(6, "shelter", StringType(), required=True),
        NestedField(7, "intake_at", TimestamptzType(), required=True),
        identifier_field_ids=[1],
    )
    PETS_SPEC = PartitionSpec(
        PartitionField(source_id=5, field_id=1000, transform=IdentityTransform(), name="species"),
        PartitionField(source_id=7, field_id=1001, transform=MonthTransform(), name="intake_month"),
    )
    return PETS_SCHEMA, PETS_SPEC


@app.cell
def _(PETS, PETS_SCHEMA, PETS_SPEC, catalog, namespace_ready):
    _ = namespace_ready
    pets = catalog.create_table_if_not_exists(
        PETS,
        schema=PETS_SCHEMA,
        partition_spec=PETS_SPEC,
        properties={"format-version": "2"},
    )
    print(pets)
    return (pets,)


@app.cell
def _(CATALOG, PETS, ic, json, pets):
    # UC's view of the same table: MANAGED + ICEBERG, at a UC-allocated path.
    _uc = ic.uc_table(f"{CATALOG}.{PETS}")
    print(json.dumps(
        {k: _uc.get(k) for k in ("full_name", "table_type", "data_source_format", "storage_location")},
        indent=2,
    ))
    print("metadata:", pets.metadata_location)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Write: overwrite, then append

    PyIceberg writes Parquet files to the table location with the credentials
    from `loadTable`, then commits a new snapshot through UC. The rows are the
    100-pet sanctuary roster, written in two commits. They are built against the
    table's **current** Arrow schema, so columns added later (see *schema
    evolution* below) are simply null for older batches. The first write is an
    `overwrite`, so re-running the notebook resets the data.
    """)
    return


@app.cell
def _(pa, sanctuary):
    def to_arrow(table, rows: list[dict]) -> pa.Table:
        """Rows as an Arrow table matching `table`'s current schema."""
        return pa.Table.from_pylist(rows, schema=table.schema().as_arrow())

    roster = sanctuary.roster()
    return roster, to_arrow


@app.cell
def _(pets, roster, sanctuary, to_arrow):
    pets.overwrite(to_arrow(pets, sanctuary.rows(roster[:60])))
    pets.append(to_arrow(pets, sanctuary.rows(roster[60:])))
    loaded = True
    return (loaded,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Scan with filter pushdown

    `row_filter` is pruned against partition values and column stats, so only
    matching files are read. `selected_fields` projects columns.
    """)
    return


@app.cell
def _(And, EqualTo, GreaterThanOrEqual, loaded, pets):
    _ = loaded
    seniors_waiting = pets.scan(
        row_filter=And(EqualTo("adopted", False), GreaterThanOrEqual("age", 10)),
        selected_fields=("name", "species", "age", "intake_at"),
    ).to_pandas().sort_values("age", ascending=False)
    seniors_waiting
    return


@app.cell
def _(loaded, pets):
    _ = loaded
    pets.scan().to_pandas().groupby(["species", "adopted"]).size().unstack(fill_value=0)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Schema evolution and row-level delete

    `update_schema()` adds a column as a metadata-only commit (new field id;
    existing files are untouched). The next batch includes the new column: 20
    new arrivals that extend the shared roster (pets 101-120), with dogs and
    cats chipped at intake. `delete()` removes matching rows; PyIceberg
    rewrites only the affected files.
    """)
    return


@app.cell
def _(BooleanType, loaded, pets, sanctuary, to_arrow):
    _ = loaded
    if "microchipped" not in pets.schema().column_names:
        with pets.update_schema() as _update:
            _update.add_column("microchipped", BooleanType(), doc="chip registered at intake")

    _arrivals = sanctuary.roster(sanctuary.ROSTER_SIZE + 20)[sanctuary.ROSTER_SIZE:]
    pets.append(to_arrow(pets, [
        {**_row, "microchipped": _row["species"] in ("dog", "cat")} for _row in sanctuary.rows(_arrivals)
    ]))
    pets.delete(delete_filter="species == 'parrot' AND adopted == true")
    evolved = True
    print(pets.schema())
    return (evolved,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Snapshots, partitions, files and time travel

    `table.inspect` exposes the Iceberg metadata tables as Arrow. Every write
    above is a snapshot, and `scan(snapshot_id=...)` reads any of them.
    """)
    return


@app.cell
def _(evolved, pets):
    _ = evolved
    pets.inspect.snapshots().to_pandas()[["committed_at", "snapshot_id", "operation", "summary"]]
    return


@app.cell
def _(evolved, pets):
    _ = evolved
    pets.inspect.partitions().to_pandas()[["partition", "record_count", "file_count", "spec_id"]]
    return


@app.cell
def _(evolved, pets):
    _ = evolved
    _snapshots = pets.inspect.snapshots().to_pylist()
    for _label, _snap in (("first", _snapshots[0]), ("current", _snapshots[-1])):
        _rows = pets.scan(snapshot_id=_snap["snapshot_id"]).to_arrow().num_rows
        print(f"{_label:>8} snapshot {_snap['snapshot_id']} ({_snap['operation']}): {_rows} rows")

    print("\nsample data files:")
    for _path in pets.inspect.files().column("file_path").to_pylist()[:3]:
        print(" ", _path)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Copy into a second table, then rename it

    Create a staging table with the evolved schema, fill it with the adopted
    pets, and rename it into place (`POST /v1/catalogs/unity/tables/rename`).
    The existence checks (`HEAD` on a table) return the spec's `204` in UC 0.7.
    """)
    return


@app.cell
def _(ADOPTED, ADOPTED_STAGING, EqualTo, catalog, evolved, pets):
    _ = evolved
    # Re-runnable: clear the previous run's tables first.
    for _name in (ADOPTED_STAGING, ADOPTED):
        if catalog.table_exists(_name):
            catalog.drop_table(_name)

    _staging = catalog.create_table(ADOPTED_STAGING, schema=pets.schema())
    _staging.append(pets.scan(row_filter=EqualTo("adopted", True)).to_arrow())
    catalog.rename_table(ADOPTED_STAGING, ADOPTED)

    adopted = catalog.load_table(ADOPTED)
    print("staging exists:", catalog.table_exists(ADOPTED_STAGING))
    print(f"{ADOPTED}: {adopted.scan().to_arrow().num_rows} rows")
    return (adopted,)


@app.cell
def _(CATALOG, NAMESPACE, adopted, catalog, ic):
    _ = adopted
    for _ident in catalog.list_tables(NAMESPACE):
        _t = ic.uc_table(f"{CATALOG}.{NAMESPACE}.{_ident[-1]}")
        print(f"{_t['full_name']:<32} {_t['table_type']:<8} {_t['data_source_format']:<8} {_t['storage_location']}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Drop vs. purge

    - `catalog.drop_table(...)` sends `purgeRequested=false`.
      `catalog.purge_table(...)` sends `purgeRequested=true`, which UC 0.7
      accepts.
    - For **managed** tables, UC owns the storage either way. The drop queues a
      storage-cleanup task, and a background worker deletes the data after
      `server.storage-cleanup.initial-delay` (`PT5M` in the playground,
      default `P7D`). This delay is not an undrop window.
    - For **external** tables, dropping only removes the catalog entry.

    Enable the cell below to tear the demo down.
    """)
    return


@app.cell(disabled=True)
def _(ADOPTED, NAMESPACE, PETS, catalog):
    for _name in (ADOPTED, PETS):
        if catalog.table_exists(_name):
            catalog.purge_table(_name)
    catalog.drop_namespace(NAMESPACE)
    return


if __name__ == "__main__":
    app.run()
