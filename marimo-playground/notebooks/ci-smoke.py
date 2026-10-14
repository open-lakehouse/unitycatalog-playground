import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import uuid
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    import common
    from pyspark.sql.types import LongType, StringType, StructField, StructType

    catalog = "ci"
    catalogs_url = (
        f"{common.unity_catalog_server_url()}"
        "/api/2.1/unity-catalog/catalogs"
    )
    create_catalog = Request(
        catalogs_url,
        data=json.dumps(
            {
                "name": catalog,
                "comment": "Catalog created by the CI smoke notebook",
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(create_catalog, timeout=30):
            pass
    except HTTPError as exc:
        if exc.code != 409:
            raise
        exc.close()

    spark = common.initialize(
        app_name="UnityCatalogPlaygroundCISmoke",
        catalog=catalog,
    )
    table = f"smoke.events_{uuid.uuid4().hex[:12]}"

    try:
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.smoke")

        schema = StructType(
            [
                StructField("id", LongType(), nullable=False),
                StructField("value", StringType(), nullable=False),
            ]
        )
        properties = {"delta.feature.catalogManaged": "supported"}
        common.create_table_using_sql(table, schema, properties, spark)

        rows = [(1, "hello"), (2, "unity-catalog")]
        dataframe = spark.createDataFrame(rows, schema=schema)
        dataframe.write.format("delta").mode("append").saveAsTable(table)

        count = spark.table(table).count()
        assert count == len(rows), f"expected {len(rows)} rows, found {count}"
        spark.sql(f"DROP TABLE {table}")
        print(f"CI_NOTEBOOK_SMOKE_OK rows={count}")
    finally:
        spark.stop()

    return


if __name__ == "__main__":
    app.run()
