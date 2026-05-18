import marimo

__generated_with = "0.20.1"
app = marimo.App(width="medium", app_title="Unity Catalog OSS")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Reading Remote Unity Catalog Tables (locally)
    > This notebook tests out the `USE EXTERNAL SCHEMA` permissions for Databrick's Unity Catalog

    See [Access Databricks data using external systems](https://docs.databricks.com/aws/en/external-access/) to understand the full scope of this notebook.

    See the [Unity Catalog Credential Vending](https://docs.databricks.com/aws/en/external-access/credential-vending) to learn more about how this functionality works from a location outside of Databricks.

    ---
    In order to utilize this functionality, you'll need to have `admin permissions` and enable the **External data access** feature of your `metastore`. You can enable this feature by doing the following:

    1. From your Databricks workspace, click on the **Catalog** tab on the left.
    2. You'll see a view with the hierarchical layout of your "Unity Catalog", and at the top you'll see a "gear" icon. Click on the "gear" icon which will take you to the `/governance/metastore` url in your workspace.
    3. You'll see a few options in a table including the **Metastore ID**, **Region**, **External delta sharing**, and **External data access**.
    4. Enable **External data access** and you'll be good to go.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import os
    import marimo as mo
    import getpass
    from delta import configure_spark_with_delta_pip

    return configure_spark_with_delta_pip, getpass, mo


@app.cell
def _(getpass):
    # Databricks Account Information
    account_id = getpass.getpass('databricks_account_id') # this is in your main account
    return (account_id,)


@app.cell
def _(getpass):
    # Databricks Workspace Information
    # > the {dbc-dcaXXXXX-XXXX} is your `deployment name` of your workspace.
    # workspace_url should look like https://dbc-dcaXXXXX-XXXX.cloud.databricks.com
    workspace_url=getpass.getpass('workspace_url')

    # ensure we don't leak credentials
    databricks_clientID = getpass.getpass("clientId")
    databricks_secret = getpass.getpass("secret")
    return databricks_clientID, databricks_secret, workspace_url


@app.cell
def _():
    # Catalog Information
    catalog='scotts_playground'
    schema='demo_prod'
    table='orders'
    return (catalog,)


@app.cell
def _(
    account_id,
    catalog,
    configure_spark_with_delta_pip,
    databricks_clientID,
    databricks_secret,
    workspace_url,
):
    from pyspark.sql import SparkSession

    # generate a new SparkSession with Unity Catalog support

    builder = (
        SparkSession.builder
        .appName("DeltaCatalogManagedTables")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "io.unitycatalog.spark.UCSingleCatalog")
        .config(f"spark.sql.catalog.{catalog}", "io.unitycatalog.spark.UCSingleCatalog")
        .config(f"spark.sql.catalog.{catalog}.uri", workspace_url)
        .config(f"spark.sql.catalog.{catalog}.auth.type", "oauth")
        .config(f"spark.sql.catalog.{catalog}.auth.oauth.uri", f"https://accounts.cloud.databricks.com/oidc/accounts/{account_id}/v1/token")
        .config(f"spark.sql.catalog.{catalog}.auth.oauth.clientId", databricks_clientID)
        .config(f"spark.sql.catalog.{catalog}.auth.oauth.clientSecret", databricks_secret)
        .config("spark.sql.defaultCatalog", catalog)
        .config("spark.hadoop.fs.s3.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    )

    extra_packages = [
        "io.unitycatalog:unitycatalog-spark_2.13:0.4.0",
        "org.apache.hadoop:hadoop-aws:3.4.1"
    ]

    spark = configure_spark_with_delta_pip(
        builder, extra_packages=extra_packages
    ).getOrCreate()
    return (spark,)


@app.cell
def _(spark):
    # check if we can read from Unity Catalog

    spark.sql("select * from demo_prod.orders").show()
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
