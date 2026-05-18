import marimo

__generated_with = "0.23.1"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Delta 4.2: Unity Catalog Managed Tables Enhancements
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

    SPARK_VERSION='4.1'
    DELTA_VERSION='4.2.0'
    UNITY_CATALOG_VERSION='0.4.1'
    MAVEN_PROXY = os.environ.get("MAVEN_PROXY", "").strip()
    return (
        BooleanType,
        DELTA_VERSION,
        DataFrame,
        IntegerType,
        MAVEN_PROXY,
        SPARK_VERSION,
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
def _(
    DELTA_VERSION,
    MAVEN_PROXY,
    SPARK_VERSION,
    UNITY_CATALOG_VERSION,
    catalog,
    unity_catalog_server_url,
):
    config = {
        "spark.jars.packages": f"io.delta:delta-spark_{SPARK_VERSION}_2.13:{DELTA_VERSION},"
        f"io.unitycatalog:unitycatalog-spark_2.13:{UNITY_CATALOG_VERSION}",
        "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
        "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        f"spark.sql.catalog.{catalog}": "io.unitycatalog.spark.UCSingleCatalog",
        f"spark.sql.catalog.{catalog}.uri": unity_catalog_server_url,
        f"spark.sql.catalog.{catalog}.token": "",
        "spark.sql.defaultCatalog": catalog,
    }
    if MAVEN_PROXY:
        config = {"spark.jars.repositories": MAVEN_PROXY, **config}
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
    # Let's create a Unity Catalog managed Delta Table
    In order to use the new `REPLACE TABLE` and `REPLACE TABLE AS SELECT` capabilities, we'll need to create a table that we can replace. In this case, we can reuse the `unity.sanctuary.pets` table from the [Catalog Managed Tables](https://delta.io/blog/2026-02-02-delta-catalog-managed-tables/) tutorial.

    1. We'll create a new `Schema` in our `catalog` called `sanctuary`. This is where we will track the animals we are rescuing and their current status.
    2. Once we have our `unity.sanctuary` location created, we can start to work with our Pet data.
    3. Then once we have written into the `pets` table, we can create another table to use as our **replacement**.
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
            StructField("uuid",    StringType(),  nullable=True),
            StructField("name",    StringType(),  nullable=True),
            StructField("age",     IntegerType(), nullable=True),
            StructField("adopted", BooleanType(), nullable=True),
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
    return


@app.cell
def _(df, uc_schema, uc_table):
    # Now let's insert some batches
    df.write.format("delta").mode("append").saveAsTable(f"{uc_schema}.{uc_table}")
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql("select * from sanctuary.pets")
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
    ## Using Replace Table to overwrite your table
    Let's say we had a successful adoption event and now have no more pets available, and that we only want to be using the `pets` table to show available pets going forwards.

    We hear about a neighboring animal rescue that has too many pets, we have the space now, and can update our table with all new pets we agree to take on. Given we also want to modify the schema we can do both in one transaction.
    """)
    return


@app.cell
def _(
    create_table_ddl,
    create_table_using_sql,
    generate_pets,
    pets_to_dataframe,
    spark: "SparkSession",
):
    # rinse and repeat of the process from earlier
    # create more generated pets, ages, etc
    more_pets = generate_pets(batch_size=20, total=40)
    more_pets_df = pets_to_dataframe(next(more_pets, None), spark)
    m_props = {'delta.feature.catalogManaged': 'supported'}
    other_uc_table = 'other_rescues_pets'

    other_ddl = create_table_ddl(f"sanctuary.{other_uc_table}", more_pets_df.schema, m_props)
    create_table_using_sql(f"sanctuary.{other_uc_table}", more_pets_df.schema, m_props, spark)
    return more_pets_df, other_uc_table


@app.cell
def _(more_pets_df, other_uc_table, uc_schema):
    from pyspark.sql.functions import col, lit
    # just reset the pets to being available
    adoptable_pets = more_pets_df.withColumn('adopted', lit(False))

    # now write the new pets into our other table (other_rescues_pets)
    adoptable_pets.write.format("delta").mode("append").saveAsTable(f"{uc_schema}.{other_uc_table}")
    return


@app.cell
def _(other_uc_table, spark: "SparkSession", uc_schema):
    # just to show that the table exists (this is also catalog managed, with the same schema as the table we
    # want to replace)
    spark.sql(f"select * from {uc_schema}.{other_uc_table}")
    return


@app.cell(disabled=True)
def _(spark: "SparkSession", uc_schema, uc_table):
    spark.sql(f"DESCRIBE TABLE EXTENDED {uc_schema}.{uc_table}")
    return


@app.cell
def _(other_uc_table, spark: "SparkSession", uc_schema, uc_table):
    # we are going to replace our current table
    # with the other rescues available pets
    # this is a complete overwrite of the table rows (preserving the tableId, properties, and still managed by Unity Catalog)
    spark.sql(f"""
    REPLACE TABLE {uc_schema}.{uc_table}
    AS SELECT * 
    FROM {uc_schema}.{other_uc_table}
    """)
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql("select * from sanctuary.pets")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## View the Table History
    If you want to take a look at the RTAS operation, you can easily use `DESCRIBE HISTORY {table_name}` to view the recent transactions.

    ~~~python
    (
        spark.sql(f"DESCRIBE HISTORY {uc_schema}.{uc_table} LIMIT 5")
        .select("version", "operation")
        .show(truncate=False)
    )
    ~~~

    ~~~text
    +-------+-----------------------+
    |version|operation              |
    +-------+-----------------------+
    |22     |REPLACE TABLE AS SELECT|
    |21     |WRITE                  |
    |20     |WRITE                  |
    |19     |WRITE                  |
    |18     |WRITE                  |
    |17     |WRITE                  |
    |16     |WRITE                  |
    ...
    +-------+-----------------------+
    ~~~
    """)
    return


@app.cell
def _(spark: "SparkSession", uc_schema, uc_table):
    (
        spark.sql(f"DESCRIBE HISTORY {uc_schema}.{uc_table} LIMIT 5")
        .select("version", "operation")
        .show(truncate=False)
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Cleaning up Tables and Schemas
    When you are all done with your table and it is time to retire it. Then you'll need to delete the table (or tables) prior to removing the schema from Unity Catalog.

    1. Let's drop the `unity.sanctuary.pets` and `unity.sanctuary.other_rescues_pets` so we can then remove the `schema`.
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
    spark.sql(f"""
    DROP TABLE unity.sanctuary.other_rescues_pets
    """)
    return


@app.cell(disabled=True)
def _(spark: "SparkSession"):
    spark.sql("DROP SCHEMA unity.sanctuary")
    return


if __name__ == "__main__":
    app.run()
