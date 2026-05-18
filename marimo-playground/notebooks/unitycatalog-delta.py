import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Getting Started with Catalog Managed Tables
    Before we can begin, we'll need to get Unity Catalog up and running.

    ## Using Docker
    1. Install `docker` and then run `docker-compose up` - this will configure UC and turn on `server.managed-table.enabled=true` in the server.properties of the Unity Catalog server which allows this new functionality to work.
    > Note: [colima](https://github.com/abiosoft/colima) is a lightweight container runtime that is docker compatible. It's also Open Source.

    ## From Sources
    1. Install Java 17 (`brew install openjdk@17`).
    > Tip: [`jenv`](https://github.com/jenv/jenv) is a great utility for managing multiple java installations.

    2. Clone [Unity Catalog](https://github.com/unitycatalog/unitycatalog) from Github.
    3. Build and Launch the **unitycatalog server**
       > `bin/sbt compile && bin/start-uc-server`

    ---
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import os
    import marimo as mo
    import getpass

    from pyspark.conf import SparkConf
    from pyspark.sql import SparkSession, DataFrame
    from pyspark.sql.types import (
        StructType, StructField, 
        StringType, IntegerType, BooleanType
    )

    DELTA_VERSION='4.1.0'
    UNITY_CATALOG_VERSION='0.4.0'
    return (
        BooleanType,
        DELTA_VERSION,
        DataFrame,
        IntegerType,
        SparkConf,
        SparkSession,
        StringType,
        StructField,
        StructType,
        UNITY_CATALOG_VERSION,
        mo,
    )


@app.cell
def _():
    # if you're running this without the docker compose file, you'll need to change this to the url of your Unity Catalog server
    unity_catalog_server_url = "http://unitycatalog:8080"

    catalog = 'unity'
    schema = 'default'
    return catalog, unity_catalog_server_url


@app.cell
def _(DELTA_VERSION, UNITY_CATALOG_VERSION, catalog, unity_catalog_server_url):
    config = {
        "spark.jars.packages": f"io.delta:delta-spark_4.1_2.13:{DELTA_VERSION}," +
        f"io.unitycatalog:unitycatalog-spark_2.13:{UNITY_CATALOG_VERSION}",
        "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
        "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        f"spark.sql.catalog.{catalog}": "io.unitycatalog.spark.UCSingleCatalog",
        f"spark.sql.catalog.{catalog}.uri": unity_catalog_server_url,
        f"spark.sql.catalog.{catalog}.token": "",
        "spark.sql.defaultCatalog": catalog,
    }
    return (config,)


@app.cell
def _(SparkConf, SparkSession, config):
    spark_config = (
        SparkConf()
            .setMaster('local[*]')
            .setAppName("DeltaCatalogManagedTables")
    )
    for k, v in config.items():
        spark_config = spark_config.set(k, v)

    # build the session
    spark: SparkSession = SparkSession.builder.config(conf=spark_config).getOrCreate()
    return (spark,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Let's create our first Unity Catalog managed Delta Table
    For this exercise, we are going to create a table representing `Pets`. Each pet is being cared for at our Rescue, and there is a status for each pet (adopted) which is a boolean. Other than that we'll have basic metadata about when we received the animal (dogs in this case since I love them).

    1. We `should` create a new `Schema` in our `catalog` called `sanctuary`. This is where we will track the animals we are rescuing and their current status.
    2. Once we have our `unity.sanctuary` location created, we can start to work with our Pet data.
    """)
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql(f"""
      CREATE SCHEMA IF NOT EXISTS unity.sanctuary
    """)
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


@app.cell
def _(DataFrame, SparkSession, StructType):
    def create_table_ddl(
        table_name: str,
        schema: StructType,
        properties: dict[str, str],
    ) -> str:
        tbl_properties = ""
        if properties:
            props = ", ".join(f"'{k}' = '{v}'" for k, v in properties.items())
            tbl_properties = f"TBLPROPERTIES ({props})"

        col_defs = ", ".join(
            f"{field.name} {field.dataType.simpleString().upper()} {'NOT NULL' if not field.nullable else ''}"
            for field in schema.fields
        )
        return (
            f"CREATE TABLE IF NOT EXISTS {table_name}\n"
            f"({col_defs})\n"
            f"USING DELTA\n"
            f"{tbl_properties}"
        ).strip()

    def create_table_using_sql(
        table_name: str,
        schema: StructType,
        properties: dict[str, str],
        spark: SparkSession,
    ) -> DataFrame:
        ddl = create_table_ddl(table_name, schema, properties)
        return spark.sql(ddl)


    return create_table_ddl, create_table_using_sql


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
    ddl = create_table_ddl(f"{uc_schema}.{uc_table}", pets_schema, props)
    return ddl, df, pets_schema, props, uc_schema, uc_table


@app.cell
def _(ddl):
    print(ddl)
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
    res = create_table_using_sql(f"{uc_schema}.{uc_table}", pets_schema, props, spark)
    return (res,)


@app.cell
def _(res):
    # Empty DataFrame is the result from the creation
    res.show()
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
      "columns": [],
      "storage_location": "file:///Users/scott.haines/git/databricks/unitycatalog/etc/data/__unitystorage/tables/b00a83fb-59ba-403c-bb55-f1c244420379",
      "comment": null,
      "properties": {
        "delta.checkpointPolicy": "v2",
        "delta.enableRowTracking": "true",
        "delta.minReaderVersion": "3",
        "delta.feature.vacuumProtocolCheck": "supported",
        "delta.minWriterVersion": "7",
        "delta.enableInCommitTimestamps": "true",
        "delta.rowTracking.materializedRowCommitVersionColumnName": "_row-commit-version-col-224b7744-724c-4abe-afa6-78d4ef97ac83",
        "delta.feature.rowTracking": "supported",
        "delta.lastUpdateVersion": "0",
        "delta.feature.catalogManaged": "supported",
        "delta.feature.v2Checkpoint": "supported",
        "delta.feature.domainMetadata": "supported",
        "delta.enableDeletionVectors": "true",
        "delta.rowTracking.materializedRowIdColumnName": "_row-id-col-17a4b93b-c459-4eaf-b217-610129dc7ffa",
        "io.unitycatalog.tableId": "b00a83fb-59ba-403c-bb55-f1c244420379",
        "delta.feature.inCommitTimestamp": "supported",
        "delta.feature.invariants": "supported",
        "delta.feature.appendOnly": "supported",
        "delta.feature.deletionVectors": "supported",
        "delta.lastCommitTimestamp": "1771972354296",
        "table_type": "MANAGED"
      },
      "owner": null,
      "created_at": 1771972355009,
      "created_by": null,
      "updated_at": 1771972355009,
      "updated_by": null,
      "table_id": "b00a83fb-59ba-403c-bb55-f1c244420379"
    }
    ~~~

    Using the `table_id` and `storage_location` values from the prior command, we can now view the commit detail.

    ~~~bash
    curl -X GET "http://localhost:8080/api/2.1/unity-catalog/delta/preview/commits" \
      -H "Content-Type: application/json" \
      -d '{"table_id":"b00a83fb-59ba-403c-bb55-f1c244420379", "table_uri":"file:///Users/scott.haines/git/databricks/unitycatalog/etc/data/managed/unity/default/tables/__unitystorage/tables/b00a83fb-59ba-403c-bb55-f1c244420379", "start_version":0}' \
    | jq .
    ~~~

    running this command will result in the following response:

    ~~~json
    {
      "commits": [
        {
          "version": 9,
          "timestamp": 1771972598719,
          "file_name": "00000000000000000009.4a586067-31dd-45c3-b477-11499de55167.json",
          "file_size": 5649,
          "file_modification_timestamp": 1771972598737
        }
      ],
      "latest_table_version": 9
    }
    ~~~

    If I want to view the files in my table, I can do so by viewing the table's `_delta_log` from the `table_uri`.

    ~~~bash
    tree etc/data/__unitystorage/tables/b00a83fb-59ba-403c-bb55-f1c244420379/_delta_log
    ~~~
    > Note: I'm using `tree` to print the directory structure.
    ~~~bash
    etc/data/__unitystorage/tables/b00a83fb-59ba-403c-bb55-f1c244420379/_delta_log
    ├── _staged_commits
    │   ├── 00000000000000000001.6153315c-b34e-4c63-bedc-0d5b82b575e2.json
    │   ├── 00000000000000000002.c78e2815-f6f2-442e-9b92-d33acdc86be8.json
    │   ├── 00000000000000000003.77080479-e72f-4529-a6a5-292060fbc5cb.json
    │   ├── 00000000000000000004.63b8fb58-0e4c-4fd1-9083-b856b82b48fb.json
    │   ├── 00000000000000000005.bb23d0b9-1ecc-48ae-a71f-edf47f0a02fd.json
    │   ├── 00000000000000000006.13f788bb-7fd4-48f4-bd04-7ad35b635055.json
    │   ├── 00000000000000000007.ff6b6fb7-abb1-4e1b-b0c3-d1bbe6b917f9.json
    │   ├── 00000000000000000008.34a8dda7-5e2b-4903-a06d-dc7725006a6f.json
    │   └── 00000000000000000009.4a586067-31dd-45c3-b477-11499de55167.json
    ├── 00000000000000000000.crc
    ├── 00000000000000000000.json
    ├── 00000000000000000001.crc
    ├── 00000000000000000001.json
    ├── 00000000000000000002.crc
    ├── 00000000000000000002.json
    ├── 00000000000000000003.crc
    ├── 00000000000000000003.json
    ├── 00000000000000000004.crc
    ├── 00000000000000000004.json
    ├── 00000000000000000005.crc
    ├── 00000000000000000005.json
    ├── 00000000000000000006.crc
    ├── 00000000000000000006.json
    ├── 00000000000000000007.crc
    ├── 00000000000000000007.json
    ├── 00000000000000000008.crc
    ├── 00000000000000000008.json
    ├── 00000000000000000009.crc
    └── 00000000000000000009.json
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
    return (dt,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Limitations
    At this point in time there are some limitations when using Catalog Managed Tables given this feature is still experimental.

    1. `DeltaTableBuilder` will fail to generate a new Catalog Managed Table. This is a known limitation and we're working on support.
    2. Vacuum Support - `DeltaTable.forName(spark, "unity.sanctuary.pets").vacuum()` will fail with `UnsupportedOperationException` **[DELTA_UNSUPPORTED_VACUUM_ON_MANAGED_TABLE]**.
    """)
    return


@app.cell
def _(dt):
    # this will fail at this point in time (Delta 4.1 with Unity Catalog 0.4.0)
    dt.vacuum()
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


@app.cell(disabled=True)
def _():
    import subprocess
    result = subprocess.run(["java", "-version"], capture_output=True, text=True)
    print(result.stderr)
    return


if __name__ == "__main__":
    app.run()
