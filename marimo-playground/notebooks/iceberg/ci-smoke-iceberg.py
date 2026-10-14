import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium")


@app.cell
def _():
    import uuid

    import iceberg_common as ic
    import pyarrow as pa

    catalog = ic.ensure_catalog("ci", comment="Catalog created by the CI smoke notebooks")
    namespace = "smoke_iceberg"
    name = f"events_{uuid.uuid4().hex[:12]}"
    table = f"{namespace}.{name}"

    spark = ic.initialize_spark(app_name="UnityCatalogPlaygroundCIIcebergSmoke", catalog=catalog)

    try:
        # Spark -> UC Iceberg REST catalog: managed table create + write.
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {namespace}")
        spark.sql(f"CREATE TABLE {table} (id BIGINT, value STRING) USING iceberg")
        spark.sql(f"INSERT INTO {table} VALUES (1, 'hello'), (2, 'unity-catalog')")

        # PyIceberg reads Spark's write, then appends through the same catalog.
        pyiceberg_table = ic.load_pyiceberg_catalog(catalog).load_table((namespace, name))
        read = pyiceberg_table.scan().to_arrow().num_rows
        assert read == 2, f"PyIceberg expected 2 rows, found {read}"
        pyiceberg_table.append(
            pa.Table.from_pylist(
                [{"id": 3, "value": "pyiceberg"}],
                schema=pyiceberg_table.schema().as_arrow(),
            )
        )

        # Spark sees PyIceberg's commit once its cached table is refreshed.
        spark.sql(f"REFRESH TABLE {table}")
        count = spark.table(table).count()
        assert count == 3, f"Spark expected 3 rows, found {count}"

        spark.sql(f"DROP TABLE {table}")
        print(f"CI_ICEBERG_SMOKE_OK rows={count}")
    finally:
        spark.stop()

    return


if __name__ == "__main__":
    app.run()
