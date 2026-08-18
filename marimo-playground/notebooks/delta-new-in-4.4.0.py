import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # What's New in Delta Lake 4.4.0
    ---
    This release brings a lot of quality of life improvements, including the fact that we can now run "this" on Apache Spark 4.2.

    1. `CREATE TABLE` now supports [`identity columns`](https://github.com/delta-io/delta/pull/7062) inside `generated columns`.
    2. `SHOW PARTITIONS` is now supported for partitioned Delta tables.
    3. `VOID` column's are supported.
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
    spark: SparkSession = common.initialize(app_name="DeltaNewIn440")
    return (
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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup the Catalog and Schema
    If you haven't created the `unity.sanctuary` catalog schema combo in your Unity Catalog instance yet, then go ahead and run through the following steps.
    """)
    return


@app.cell
def _(common):
    print(common.unity_catalog_server_url())
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
    ### Tip: In order to execute CREATE SCHEMA you'll need the following permissions
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
    ## Using Auto-Generated Identity Columns

    We'll create a shelter **inventory** table partitioned by `animal_category`.
    Each product gets an auto-generated `id` via
    `BIGINT GENERATED ALWAYS AS IDENTITY` — so the generator below does **not**
    invent that field; Delta assigns it on write.
    """)
    return


@app.cell
def _(
    DataFrame,
    IntegerType,
    SparkSession,
    StringType,
    StructField,
    StructType,
):
    import random
    from dataclasses import dataclass

    @dataclass
    class RescueProduct:
        name: str
        product_type: str
        animal_category: str
        quantity: int

    def generate_rescue_products(total: int = 100) -> list[RescueProduct]:
        """Generate random shelter-supply inventory rows (no identity column)."""
        animal_categories = ["dog", "cat", "other"]
        product_catalog = {
            "blanket": [
                "Fleece Blanket",
                "Thermal Throw",
                "Crate Pad",
                "Waterproof Blanket",
                "Soft Cuddle Blanket",
            ],
            "towel": [
                "Bath Towel",
                "Microfiber Towel",
                "Grooming Towel",
                "Quick-Dry Towel",
                "Absorbent Mat",
            ],
            "food": [
                "Dry Kibble",
                "Wet Food Cans",
                "Puppy Formula",
                "Senior Diet",
                "Grain-Free Mix",
                "Treat Biscuits",
            ],
            "litter": [
                "Clumping Litter",
                "Crystal Litter",
                "Pellet Litter",
                "Litter Liners",
            ],
            "toy": [
                "Chew Bone",
                "Feather Wand",
                "Squeaky Ball",
                "Puzzle Feeder",
                "Catnip Mouse",
            ],
            "bedding": [
                "Kennel Bed",
                "Orthopedic Cushion",
                "Hammock Bed",
                "Nesting Pad",
            ],
            "hygiene": [
                "Shampoo",
                "Ear Cleaner",
                "Nail Clippers",
                "Dental Wipes",
                "Waste Bags",
            ],
        }
        product_types = list(product_catalog.keys())

        products: list[RescueProduct] = []
        for _ in range(total):
            product_type = random.choice(product_types)
            animal = random.choice(animal_categories)
            # litter is mainly for cats; bias a bit for realism
            if product_type == "litter" and random.random() < 0.8:
                animal = "cat"
            name = random.choice(product_catalog[product_type])
            products.append(
                RescueProduct(
                    name=name,
                    product_type=product_type,
                    animal_category=animal,
                    quantity=random.randint(1, 50),
                )
            )
        return products

    def rescue_products_to_dataframe(
        products: list[RescueProduct],
        spark: SparkSession,
    ) -> DataFrame:
        rows = [
            (p.name, p.product_type, p.animal_category, p.quantity)
            for p in products
        ]
        schema = StructType([
            StructField("name", StringType(), nullable=False),
            StructField("product_type", StringType(), nullable=False),
            StructField("animal_category", StringType(), nullable=False),
            StructField("quantity", IntegerType(), nullable=False),
        ])
        return spark.createDataFrame(rows, schema=schema)

    return generate_rescue_products, rescue_products_to_dataframe


@app.cell
def _(
    DataFrame,
    generate_rescue_products,
    rescue_products_to_dataframe,
    spark: "SparkSession",
):
    # ~100 shelter supply products — identity `id` is assigned by Delta on write
    products = generate_rescue_products(total=100)
    products_df: DataFrame = rescue_products_to_dataframe(products, spark)
    return (products_df,)


@app.cell
def _(common, products_df: "DataFrame"):
    uc_schema = "unity.sanctuary"
    uc_table = "inventory"
    props = {"delta.feature.catalogManaged": "supported"}

    ddl = common.create_table_ddl(f"{uc_schema}.{uc_table}", products_df.schema, props)

    # do the following to get 99% of the way to the DDL we need
    print(ddl)
    return uc_schema, uc_table


@app.cell
def _(spark: "SparkSession"):
    # create the inventory table "unity.sanctuary.inventory"
    # add the id column to the generated query from the prior cell.
    # Note: try adding (INCREMENT BY 1) to the end of the id column in the DDL. See how the behavior changes
    # Other Note: if you've already created the table, remember you can use CREATE OR REPLACE TABLE as well.
    spark.sql("""
    CREATE TABLE IF NOT EXISTS unity.sanctuary.inventory (
      id BIGINT GENERATED ALWAYS AS IDENTITY,
      name STRING NOT NULL, 
      product_type STRING NOT NULL, 
      animal_category STRING NOT NULL, 
      quantity INT NOT NULL
    )
    USING DELTA
    TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported')
    PARTITIONED BY (animal_category)
    """)
    return


@app.cell
def _(products_df: "DataFrame", uc_schema, uc_table):
    # add the batch of 100 items to our inventory
    (
        products_df
            .write
            .format("delta")
            .mode("append")
            .saveAsTable(f"{uc_schema}.{uc_table}")
    )
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql(f"select * from unity.sanctuary.inventory ORDER BY id ASC").show(100)
    return


@app.cell
def _(spark: "SparkSession"):
    spark.sql("SHOW PARTITIONS unity.sanctuary.inventory")
    return


@app.cell
def _(spark: "SparkSession"):
    # take a look at the table columns. You'll notice 
    spark.sql("describe extended unity.sanctuary.inventory")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Using the UC CLI to inspect the table
    Simply reuse the same docker environment and run the following command.

    ~~~bash
    docker exec \
      -it unitycatalog \
      bash bin/uc table get --full_name unity.sanctuary.inventory
    ~~~

    and you'll see a formatted table description, like the following:

    ~~~bash
    ┌──────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
    │                 KEY                  │                                                                                   VALUE                                                                                   │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │NAME                                  │inventory                                                                                                                                                                  │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │CATALOG_NAME                          │unity                                                                                                                                                                      │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │SCHEMA_NAME                           │sanctuary                                                                                                                                                                  │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │TABLE_TYPE                            │MANAGED                                                                                                                                                                    │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │DATA_SOURCE_FORMAT                    │DELTA                                                                                                                                                                      │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │COLUMNS                               │{"name":"id","type_text":"bigint","type_json":"{\"name\":\"id\",\"type\":\"long\",\"nullable\":true,\"metadata\":{\"delta.identity.highWaterMark\":100,\"delta.columnMappin│
    │                                      │g.id\":5,\"delta.identity.step\":1,\"delta.columnMapping.physicalName\":\"col-0e879a02-aa83-4b8d-83d2-bd77d4495381\",\"delta.identity.allowExplicitInsert\":false,\"delta.i│
    │                                      │dentity.start\":1}}","type_name":"LONG","type_precision":null,"type_scale":null,"type_interval_type":null,"position":0,"comment":null,"nullable":true,"partition_index":nul│
    │                                      │l}                                                                                                                                                                         │
    │                                      │{"name":"name","type_text":"string","type_json":"{\"name\":\"name\",\"type\":\"string\",\"nullable\":false,\"metadata\":{\"delta.columnMapping.id\":1,\"delta.columnMapping│
    │                                      │.physicalName\":\"col-9bea7084-dfa5-45ac-84ed-168f25240036\"}}","type_name":"STRING","type_precision":null,"type_scale":null,"type_interval_type":null,"position":1,"commen│
    │                                      │t":null,"nullable":false,"partition_index":null}                                                                                                                           │
    │                                      │{"name":"product_type","type_text":"string","type_json":"{\"name\":\"product_type\",\"type\":\"string\",\"nullable\":false,\"metadata\":{\"delta.columnMapping.id\":2,\"del│
    │                                      │ta.columnMapping.physicalName\":\"col-124d33ac-cb77-4713-8d2f-be4b85fa13b2\"}}","type_name":"STRING","type_precision":null,"type_scale":null,"type_interval_type":null,"pos│
    │                                      │ition":2,"comment":null,"nullable":false,"partition_index":null}                                                                                                           │
    │                                      │{"name":"animal_category","type_text":"string","type_json":"{\"name\":\"animal_category\",\"type\":\"string\",\"nullable\":false,\"metadata\":{\"delta.columnMapping.id\":3│
    │                                      │,\"delta.columnMapping.physicalName\":\"col-280ef885-48b7-456e-b297-8f8c436eb9bb\"}}","type_name":"STRING","type_precision":null,"type_scale":null,"type_interval_type":nul│
    │                                      │l,"position":3,"comment":null,"nullable":false,"partition_index":0}                                                                                                        │
    │                                      │{"name":"quantity","type_text":"int","type_json":"{\"name\":\"quantity\",\"type\":\"integer\",\"nullable\":false,\"metadata\":{\"delta.columnMapping.id\":4,\"delta.columnM│
    │                                      │apping.physicalName\":\"col-5a1b1b11-ea2b-4a10-a0f5-fbafd7ec11fc\"}}","type_name":"INT","type_precision":null,"type_scale":null,"type_interval_type":null,"position":4,"com│
    │                                      │ment":null,"nullable":false,"partition_index":null}                                                                                                                        │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │STORAGE_LOCATION                      │s3://uc-warehouse/__unitystorage/tables/59be11b4-7bdc-4bbf-acfe-b6500b3187ca                                                                                               │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │COMMENT                               │null                                                                                                                                                                       │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │PROPERTIES                            │{"delta.checkpoint.writeStatsAsJson":"true","delta.minReaderVersion":"3","delta.feature.vacuumProtocolCheck":"supported","delta.minWriterVersion":"7","delta.randomizeFileP│
    │                                      │refixes":"true","delta.enableInCommitTimestamps":"true","delta.columnMapping.mode":"name","delta.checkpoint.writeStatsAsStruct":"true","delta.lastUpdateVersion":"6","delta│
    │                                      │.feature.catalogManaged":"supported","delta.feature.v2Checkpoint":"supported","delta.enableDeletionVectors":"true","delta.columnMapping.maxColumnId":"5","delta.feature.inC│
    │                                      │ommitTimestamp":"supported","delta.feature.deletionVectors":"supported","delta.feature.appendOnly":"supported","delta.lastCommitTimestamp":"1787090727456","delta.enableRow│
    │                                      │Tracking":"true","delta.checkpointPolicy":"v2","delta.feature.columnMapping":"supported","delta.rowTracking.materializedRowCommitVersionColumnName":"_row-commit-version-co│
    │                                      │l-f2f97d34-3e3b-48fa-ae39-077920ad6154","delta.feature.identityColumns":"supported","delta.feature.rowTracking":"supported","delta.feature.domainMetadata":"supported","io.│
    │                                      │unitycatalog.tableId":"59be11b4-7bdc-4bbf-acfe-b6500b3187ca","delta.rowTracking.materializedRowIdColumnName":"_row-id-col-a7a16a0e-88dd-402f-a777-91928473c9b6","delta.feat│
    │                                      │ure.invariants":"supported"}                                                                                                                                               │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │OWNER                                 │null                                                                                                                                                                       │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │CREATED_AT                            │1787088904212                                                                                                                                                              │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │CREATED_BY                            │null                                                                                                                                                                       │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │UPDATED_AT                            │1787090727652                                                                                                                                                              │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │UPDATED_BY                            │null                                                                                                                                                                       │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │TABLE_ID                              │59be11b4-7bdc-4bbf-acfe-b6500b3187ca                                                                                                                                       │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │VIEW_DEFINITION                       │null                                                                                                                                                                       │
    ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │VIEW_DEPENDENCIES                     │null                                                                                                                                                                       │
    └──────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
    ~~~
    """)
    return


@app.cell(disabled=True)
def _(spark: "SparkSession", uc_table):
    spark.sql(f"drop table unity.sanctuary.{uc_table}")
    return


if __name__ == "__main__":
    app.run()
