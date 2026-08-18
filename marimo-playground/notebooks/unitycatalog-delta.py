import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Getting Started with Catalog Managed Tables
    Before we can begin, we'll need to get Unity Catalog up and running.

    ## Using Docker
    1. Install `docker` and then run `docker-compose up` - this will configure UC and turn on `server.managed-table.enabled=true` in the server.properties of the Unity Catalog server which allows this new functionality to work.
    > Note: [colima](https://github.com/abiosoft/colima) is a lightweight container runtime that is docker compatible. It's also Open Source.

    ---
    """)
    return


@app.cell
def _():
    import marimo as mo

    from pyspark.sql import SparkSession, DataFrame
    from pyspark.sql.types import (
        StructType, StructField, 
        StringType, IntegerType, BooleanType
    )

    # notebooks/common.py owns the environment setup shared by every notebook
    # here: artifact versions and the Unity Catalog endpoint come from the
    # environment, and `initialize` assembles the Spark config (Maven proxy,
    # local Ivy repo, S3A/RustFS switches) and builds the session.
    import common

    catalog = common.CATALOG
    spark: SparkSession = common.initialize(app_name="DeltaCatalogManagedTables")
    return (
        BooleanType,
        DataFrame,
        IntegerType,
        SparkSession,
        StringType,
        StructField,
        StructType,
        catalog,
        common,
        mo,
        spark,
    )


@app.cell(disabled=True, hide_code=True)
def _(common):
    print(common.unity_catalog_server_url())
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Let's create our first Unity Catalog managed Delta Table
    For this exercise, we are going to create a table representing `Pets`. Each pet is being cared for at our Rescue, and there is a status for each pet (adopted) which is a boolean. Other than that we'll have basic metadata about when we received the animal (dogs in this case since I love them).

    1. We `should` create a new `Schema` in our `catalog` called `sanctuary`. This is where we will track the animals we are rescuing and their current status.
    2. Once we have our `unity.sanctuary` location created, we can start to work with our Pet data.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    > Note: You can check for available catalogs by hitting http://localhost:8080/api/2.1/unity-catalog/catalogs

    If the named catalog **unity** doesn't exist. Please execute the following API call.

    ~~~bash
    curl -X POST "http://localhost:8080/api/2.1/unity-catalog/catalogs" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "unity",
        "comment": "example catalog for uc playground"
      }'
    ~~~
    """)
    return


@app.cell
def _(catalog, spark: "SparkSession"):
    # pin the session catalog to 'unity'
    spark.catalog.setCurrentCatalog(catalog)
    return


@app.cell
def _(spark: "SparkSession"):
    # Check for the catalog called "unity"
    spark.catalog.listCatalogs()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tip: In order to execute CREATE SCHEMA you'll need the following permissions
    1. You'll need `USE CATALOG` on the catalog `unity`
    2. You'll need `CREATE SCHEMA` for the catalog `unity`
    """)
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql("CREATE SCHEMA IF NOT EXISTS unity.sanctuary")
    return


@app.cell
def _(spark: "SparkSession"):
    # this is a way of setting unity.sanctuary automagicaly
    spark.catalog.setCurrentDatabase("sanctuary")
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql("DESCRIBE SCHEMA unity.sanctuary").show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Next we'll create some helpers to make it easy to work with our `Pets`
    This includes data generators, and helper methods for creating data to work with in this notebook.
    """)
    return


@app.cell
def _(
    BooleanType,
    DataFrame,
    IntegerType,
    SparkSession,
    StringType,
    StructField,
    StructType,
):
    import uuid
    import random
    from dataclasses import dataclass, fields
    from typing import Iterator

    # 1. Pets dataclass
    @dataclass
    class Pets:
        uuid: str
        name: str
        age: int
        adopted: bool

    def generate_pets(batch_size: int = 10, total: int = 100) -> Iterator[list[Pets]]:
        names = [
            "Luna", "Milo", "Bella", "Charlie", "Max",
            "Lucy", "Cooper", "Daisy", "Buddy", "Lily",
            "Rocky", "Molly", "Bear", "Lola", "Duke",
            "Sadie", "Tucker", "Zoe", "Oliver", "Stella",
            "Archie", "Rosie", "Leo", "Cleo", "Finn",
            "Nova", "Jasper", "Willow", "Atlas", "Ivy",
            "Theo", "Ruby", "Gus", "Nala", "Remy",
            "Pepper", "Beau", "Coco", "Arlo", "Hazel",
            "Scout", "Freya", "Hugo", "Maple", "Rufus",
            "Juniper", "Otis", "Penny", "Bentley", "Sage",
            "Winston", "Piper", "Clover", "Dexter", "Wren",
            "Biscuit", "Tilly", "Monty", "Fern", "Chester",
            "Poppy", "Bruno", "Skye", "Ziggy", "Opal",
            "Roux", "Nimbus", "Dottie", "Cosmo", "Waffles",
        ]
        pets = [
            Pets(
                uuid=str(uuid.uuid4()),
                name=random.choice(names),
                age=random.randint(1, 15),
                adopted=random.choice([True, False]),
            )
            for _ in range(total)
        ]
        for i in range(0, len(pets), batch_size):
            yield pets[i : i + batch_size]

    def pets_to_dataframe(pets: list[Pets], spark: SparkSession) -> DataFrame:
        """
        given a list of pets, create a dataframe
        """
        rows = [
            (p.uuid, p.name, p.age, p.adopted)
            for p in pets
        ]
        schema = StructType([
            StructField("uuid",    StringType(),  nullable=False),
            StructField("name",    StringType(),  nullable=False),
            StructField("age",     IntegerType(), nullable=False),
            StructField("adopted", BooleanType(), nullable=False),
        ])
        return spark.createDataFrame(rows, schema=schema)


    return generate_pets, pets_to_dataframe


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Now let's create some helpers to make creating tables a breeze
    This includes generating DDLs from DataFrames and more.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Let's Generate some Pet's and Create our first Managed Commits
    """)
    return


@app.cell
def _(generate_pets):
    # create 100 pets across 10 batches
    pets = generate_pets(batch_size=10, total=100)
    return (pets,)


@app.cell
def _(pets):
    # we'll fetch the first batch and use it to create our new Table
    litter_one = next(pets, None)
    return (litter_one,)


@app.cell
def _(create_table_ddl, litter_one, pets_to_dataframe, spark: "SparkSession"):
    df = pets_to_dataframe(litter_one, spark)
    pets_schema = df.schema
    props = {'delta.feature.catalogManaged': 'supported'}

    uc_schema = 'sanctuary'
    uc_table = 'pets'

    # note: because we are using the io.unitycatalog.spark.UCSingleCatalog the defaultCatalog `unity`
    # is left out of our table name.
    ddl = common.create_table_ddl(f"{uc_schema}.{uc_table}", pets_schema, props)
    return ddl, df, pets_schema, props, uc_schema, uc_table


@app.cell
def _(ddl):
    print(ddl)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## UC Permissions
    In order to create a table within a Schema owned by a Catalog (`catalog.schema`), you'll need the following permission🥇

    1. `CREATE TABLE`

    2. In order to `view` the data, you will also need `SELECT` on the table.
    """)
    return


@app.cell
def _(
    create_table_using_sql,
    pets_schema,
    props,
    spark: "SparkSession",
    uc_schema,
    uc_table,
):
    # we will create the new table
    res = common.create_table_using_sql(f"{uc_schema}.{uc_table}", pets_schema, props, spark)
    return


@app.cell
def _(df, uc_schema, uc_table):
    # Now let's insert some batches
    df.write.format("delta").mode("append").saveAsTable(f"{uc_schema}.{uc_table}")
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql("select * from sanctuary.pets").show()
    return


@app.cell
def _(pets, pets_to_dataframe, spark: "SparkSession", uc_schema, uc_table):
    for litter in pets:
        pets_to_dataframe(litter, spark).write.format("delta").mode("append").saveAsTable(f"{uc_schema}.{uc_table}")
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql("select count(*) as total from sanctuary.pets").show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Use Unity Catalog API to view the Delta Commits
    > Note: This requires downloading the unitycatalog sources and installing `jq` : `brew install jq`
    1. Open up a `terminal` session and `cd /path/to/unitycatalog`
    2. Hit the REST API to view our new table:

    ~~~bash
    bin/uc table get --full_name unity.sanctuary.pets --output json | jq .
    ~~~

    You should see something similar:

    ~~~json
    {
      "name": "pets",
      "catalog_name": "unity",
      "schema_name": "sanctuary",
      "table_type": "MANAGED",
      "data_source_format": "DELTA",
      "columns": [
        {
          "name": "uuid",
          "type_text": "string",
          "type_json": "{\"name\":\"uuid\",\"type\":\"string\",\"nullable\":false,\"metadata\":{\"delta.columnMapping.id\":1,\"delta.columnMapping.physicalName\":\"col-86da5885-d589-45cb-b083-ea013601ce0d\"}}",
          "type_name": "STRING",
          "type_precision": null,
          "type_scale": null,
          "type_interval_type": null,
          "position": 0,
          "comment": null,
          "nullable": false,
          "partition_index": null
        },
        {
          "name": "name",
          "type_text": "string",
          "type_json": "{\"name\":\"name\",\"type\":\"string\",\"nullable\":false,\"metadata\":{\"delta.columnMapping.id\":2,\"delta.columnMapping.physicalName\":\"col-91c45aa2-7506-4749-b5d3-3e958759a62e\"}}",
          "type_name": "STRING",
          "type_precision": null,
          "type_scale": null,
          "type_interval_type": null,
          "position": 1,
          "comment": null,
          "nullable": false,
          "partition_index": null
        },
        {
          "name": "age",
          "type_text": "int",
          "type_json": "{\"name\":\"age\",\"type\":\"integer\",\"nullable\":false,\"metadata\":{\"delta.columnMapping.id\":3,\"delta.columnMapping.physicalName\":\"col-940e01ca-4465-4fa3-a0ca-baf9225b9bfa\"}}",
          "type_name": "INT",
          "type_precision": null,
          "type_scale": null,
          "type_interval_type": null,
          "position": 2,
          "comment": null,
          "nullable": false,
          "partition_index": null
        },
        {
          "name": "adopted",
          "type_text": "boolean",
          "type_json": "{\"name\":\"adopted\",\"type\":\"boolean\",\"nullable\":false,\"metadata\":{\"delta.columnMapping.id\":4,\"delta.columnMapping.physicalName\":\"col-2fc9c227-11fd-4a22-ab19-0e63b205e38a\"}}",
          "type_name": "BOOLEAN",
          "type_precision": null,
          "type_scale": null,
          "type_interval_type": null,
          "position": 3,
          "comment": null,
          "nullable": false,
          "partition_index": null
        }
      ],
      "storage_location": "s3://uc-warehouse/__unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4",
      "comment": null,
      "properties": {
        "delta.checkpoint.writeStatsAsJson": "true",
        "delta.minReaderVersion": "3",
        "delta.feature.vacuumProtocolCheck": "supported",
        "delta.minWriterVersion": "7",
        "delta.enableInCommitTimestamps": "true",
        "delta.randomizeFilePrefixes": "true",
        "delta.columnMapping.mode": "name",
        "delta.checkpoint.writeStatsAsStruct": "true",
        "delta.lastUpdateVersion": "0",
        "delta.feature.catalogManaged": "supported",
        "delta.feature.v2Checkpoint": "supported",
        "delta.enableDeletionVectors": "true",
        "delta.columnMapping.maxColumnId": "4",
        "delta.feature.inCommitTimestamp": "supported",
        "delta.feature.appendOnly": "supported",
        "delta.feature.deletionVectors": "supported",
        "delta.lastCommitTimestamp": "1787082939265",
        "delta.checkpointPolicy": "v2",
        "delta.enableRowTracking": "true",
        "delta.feature.columnMapping": "supported",
        "delta.rowTracking.materializedRowCommitVersionColumnName": "_row-commit-version-col-a79b21b6-0fc9-4875-89c4-afdc380a7ae2",
        "delta.feature.rowTracking": "supported",
        "delta.feature.domainMetadata": "supported",
        "delta.rowTracking.materializedRowIdColumnName": "_row-id-col-88447c69-dc4c-4cff-914e-5b2136357d5c",
        "io.unitycatalog.tableId": "c60bf1ab-d115-4ed9-9638-633a6896e8d4",
        "delta.feature.invariants": "supported"
      },
      "owner": null,
      "created_at": 1787082944715,
      "created_by": null,
      "updated_at": 1787082944715,
      "updated_by": null,
      "table_id": "c60bf1ab-d115-4ed9-9638-633a6896e8d4",
      "view_definition": null,
      "view_dependencies": null
    }
    ~~~

    Using the `table_id` and `storage_location` values from the prior command, we can now view the commit detail.

    ~~~bash
    curl -X GET "http://localhost:8080/api/2.1/unity-catalog/delta/preview/commits" \
      -H "Content-Type: application/json" \
      -d '{"table_id":"c60bf1ab-d115-4ed9-9638-633a6896e8d4", "table_uri":"file:///Users/scott.haines/git/databricks/unitycatalog/etc/data/managed/unity/default/tables/__unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4", "start_version":0}' \
    | jq .
    ~~~

    running this command will result in the following response:

    ~~~json
    {
      "commits": [
        {
          "version": 10,
          "timestamp": 1787082987129,
          "file_name": "00000000000000000010.5751b014-04b7-489b-99c6-09c023ea23cf.json",
          "file_size": 2312,
          "file_modification_timestamp": 1787082987000
        }
      ],
      "latest_table_version": 10
    }
    ~~~

    If I want to view the files in my table, I can do so by viewing the table's `_delta_log` from the `table_uri` using the `rc` client from `rustfs`.

    ## Setting up the RustFS Client
    1. `brew install rustfs/tap/rc`
    2. `rc alias set local http://localhost:9000 {user} {pwd}`

    ~~~bash
    rc object list local/uc-warehouse/__unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log
    ~~~

    ~~~bash
    [                   ]         0B __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/_sidecars/
    [                   ]         0B __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/_staged_commits/
    [2026-08-18 19:55:39]   3.57 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000000.crc
    [2026-08-18 19:55:39]   2.94 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000000.json
    [2026-08-18 19:55:59]   5.39 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000001.crc
    [2026-08-18 19:55:59]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000001.json
    [2026-08-18 19:56:11]   7.08 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000002.crc
    [2026-08-18 19:56:11]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000002.json
    [2026-08-18 19:56:13]   8.78 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000003.crc
    [2026-08-18 19:56:13]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000003.json
    [2026-08-18 19:56:15]  10.47 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000004.crc
    [2026-08-18 19:56:15]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000004.json
    [2026-08-18 19:56:17]  12.17 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000005.crc
    [2026-08-18 19:56:17]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000005.json
    [2026-08-18 19:56:19]  13.86 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000006.crc
    [2026-08-18 19:56:19]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000006.json
    [2026-08-18 19:56:21]  15.55 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000007.crc
    [2026-08-18 19:56:21]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000007.json
    [2026-08-18 19:56:23]  17.25 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000008.crc
    [2026-08-18 19:56:23]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000008.json
    [2026-08-18 19:56:25]  18.93 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000009.crc
    [2026-08-18 19:56:25]   2.25 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000009.json
    [2026-08-18 19:56:29]   7.03 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000010.checkpoint.c436da4b-f942-4f26-b301-f536787e3838.json
    [2026-08-18 19:56:29]  20.62 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000010.crc
    [2026-08-18 19:56:27]   2.26 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/00000000000000000010.json
    [2026-08-18 19:56:30]   7.30 KiB __unitystorage/tables/c60bf1ab-d115-4ed9-9638-633a6896e8d4/_delta_log/_last_checkpoint
    ~~~
    """)
    return


@app.cell
def _(mo, spark: "SparkSession"):
    # View the Delta History using DeltaTable
    from delta.tables import DeltaTable

    dt = DeltaTable.forName(spark, "unity.sanctuary.pets")

    # view history
    mo.ui.table(dt.history())
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Cleaning up Tables and Schemas
    When you are all done with your table and it is time to retire it. Then you'll need to delete the table (or tables) prior to removing the schema from Unity Catalog.

    1. Let's drop the `unity.sanctuary.pets` first
    2. Then we can remove the `schema` (`unity.sanctuary`)

    Just enable the disabled cells (using the `...`) icon and run them.
    """)
    return


@app.cell(disabled=True)
def _(spark: "SparkSession"):
    spark.sql(f"""
    DROP TABLE unity.sanctuary.pets
    """)
    return


@app.cell(disabled=True)
def _(spark: "SparkSession"):
    spark.sql("DROP SCHEMA unity.sanctuary")
    return


if __name__ == "__main__":
    app.run()
