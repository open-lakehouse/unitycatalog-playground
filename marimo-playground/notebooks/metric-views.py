import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Unity Catalog Metric Views (new in UC 0.6.0)
    ---
    A **metric view** is a view-like object that defines reusable **dimensions**
    (grouping columns) and **measures** (named aggregations) over a source — a
    table/view or a SQL query — expressed in YAML. Consumers read the measures
    with the `measure(...)` function and `GROUP BY` the dimensions, so the
    aggregation logic lives in one governed place in Unity Catalog instead of
    being copy-pasted across queries.

    This notebook walks through the full lifecycle against the bundled local UC:

    1. Bootstrap a brand-new `ecomm` catalog via the UC REST API.
    2. Build a catalog-managed Delta table `ecomm.consumer.orders` of fake
       e-commerce orders.
    3. Define a metric view `ecomm.consumer.orders_last_7_day_sales` with a
       `region` dimension and a `last_7_day_sales` measure.
    4. List, describe, and query it with `measure(...)`.

    > **Prerequisites.** Metric views need **Apache Spark 4.2+** (the
    > `CREATE VIEW ... WITH METRICS` DDL landed in 4.2) and the **UC 0.6.0**
    > Spark 4.2 connector (`io.unitycatalog:unitycatalog-spark_4.2_2.13:0.6.0`).
    """)
    return


@app.cell
def _():
    import random
    import uuid
    from dataclasses import dataclass
    from datetime import datetime, timedelta, timezone

    import marimo as mo
    from pyspark.sql import DataFrame, SparkSession
    from pyspark.sql.types import (
        DoubleType,
        IntegerType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    # notebooks/common.py owns the shared environment setup: artifact versions
    # and the Unity Catalog endpoint come from the environment, and `initialize`
    # assembles the Spark config (Maven proxy, local Ivy repo, S3A/RustFS
    # switches) and builds the session.
    import common

    CATALOG = "ecomm"
    SCHEMA = "consumer"
    TABLE = "orders"
    METRIC_VIEW = "orders_last_7_day_sales"

    FQ_SCHEMA = f"{CATALOG}.{SCHEMA}"
    FQ_TABLE = f"{CATALOG}.{SCHEMA}.{TABLE}"
    FQ_METRIC_VIEW = f"{CATALOG}.{SCHEMA}.{METRIC_VIEW}"

    # Register a Spark catalog named `ecomm` bound to the same UC server.
    # `UCSingleCatalog` maps the Spark-catalog name -> the UC catalog name, so the
    # only extra we pass is the (correctly named) Delta REST API toggle for it.
    spark: SparkSession = common.initialize(
        app_name="MetricViews",
        catalog=CATALOG,
        extra_config={f"spark.sql.catalog.{CATALOG}.deltaRestApi.enabled": "true"},
    )
    return (
        CATALOG,
        DataFrame,
        DoubleType,
        FQ_METRIC_VIEW,
        FQ_SCHEMA,
        FQ_TABLE,
        IntegerType,
        SCHEMA,
        SparkSession,
        StringType,
        StructField,
        StructType,
        TimestampType,
        common,
        dataclass,
        datetime,
        mo,
        random,
        spark,
        timedelta,
        timezone,
        uuid,
    )


@app.cell
def _(common):
    # Sanity-check the versions + endpoint this session is wired to.
    print("UC Spark connector:", f"unitycatalog-spark_{common.SPARK_VERSION}_2.13:{common.UNITY_CATALOG_VERSION}")
    print("Delta Lake:", common.DELTA_VERSION)
    print("UC server:", common.unity_catalog_server_url())
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Bootstrap the `ecomm` catalog via the UC REST API

    Unlike the other notebooks (which reuse the pre-created `unity` catalog), this
    one creates its own `ecomm` catalog so the demo is self-contained. The cell
    below `POST`s to the Unity Catalog catalogs API. It is **idempotent**: it
    `GET`s the catalog first and only creates it when missing (treating a `409
    ALREADY_EXISTS` as success), so re-running the notebook is safe.

    The equivalent curl call:

    ~~~bash
    curl -X POST "http://localhost:8080/api/2.1/unity-catalog/catalogs" \
      -H "Content-Type: application/json" \
      -d '{"name": "ecomm", "comment": "E-commerce domain catalog for the metric-view demo"}'
    ~~~
    """)
    return


@app.cell
def _(CATALOG, common):
    import json
    import urllib.error
    import urllib.request

    def _uc_headers(token: str, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _catalog_exists(base_url: str, name: str, token: str) -> bool:
        req = urllib.request.Request(
            f"{base_url}/api/2.1/unity-catalog/catalogs/{name}",
            headers=_uc_headers(token),
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return False
            raise

    def _create_catalog(base_url: str, name: str, token: str, comment: str) -> dict:
        payload = json.dumps({"name": name, "comment": comment}).encode()
        req = urllib.request.Request(
            f"{base_url}/api/2.1/unity-catalog/catalogs",
            data=payload,
            headers=_uc_headers(token, json_body=True),
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    _base_url = common.unity_catalog_server_url()
    _token = common.unity_catalog_token()

    try:
        if _catalog_exists(_base_url, CATALOG, _token):
            print(f"Catalog '{CATALOG}' already exists at {_base_url}")
        else:
            _info = _create_catalog(
                _base_url,
                CATALOG,
                _token,
                "E-commerce domain catalog for the metric-view demo",
            )
            print(f"Created catalog '{CATALOG}': {_info}")
    except urllib.error.HTTPError as err:
        if err.code == 409:
            print(f"Catalog '{CATALOG}' already exists (409 ALREADY_EXISTS)")
        else:
            raise

    # readiness token so downstream cells run *after* the catalog exists
    ecomm_ready = CATALOG
    return (ecomm_ready,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Create the `consumer` schema

    With the catalog in place, create the `consumer` schema and pin the session
    to `ecomm.consumer`. (`CREATE SCHEMA` needs `USE CATALOG` + `CREATE SCHEMA`
    on `ecomm`; the bundled local UC runs without auth so this just works.)
    """)
    return


@app.cell
def _(FQ_SCHEMA, SCHEMA, ecomm_ready, spark: "SparkSession"):
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {FQ_SCHEMA}")
    spark.catalog.setCurrentCatalog(ecomm_ready)
    spark.catalog.setCurrentDatabase(SCHEMA)
    schema_ready = FQ_SCHEMA
    return (schema_ready,)


@app.cell
def _(schema_ready, spark: "SparkSession"):
    spark.sql(f"DESCRIBE SCHEMA {schema_ready}").show(truncate=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Fake dataset: `ecomm.consumer.orders`

    We generate ~500 fake orders. Each row carries:

    | column | type | notes |
    | --- | --- | --- |
    | `order_id` | STRING | uuid |
    | `customer_id` | STRING | `CUST-#####` |
    | `product_id` | STRING | `SKU-####` |
    | `created_at` | TIMESTAMP | UTC, spread over the last ~21 days (biased recent) |
    | `status` | STRING | enum: PLACED / PAID / SHIPPED / DELIVERED / CANCELLED / RETURNED |
    | `amount` | DOUBLE | order cost |
    | `quantity` | INT | units in the order |
    | `region` | STRING | ISO 3166-1 alpha-2 (US, GB, DE, ...) |
    | `currency` | STRING | ISO 4217, derived from region |
    | `channel` | STRING | WEB / MOBILE / STORE |
    | `payment_method` | STRING | CARD / PAYPAL / ... |

    `created_at` is spread across the last few weeks (biased toward *recent*) so
    the `last_7_day_sales` metric view has a healthy mix of in-window and
    out-of-window rows to filter on.
    """)
    return


@app.cell
def _(
    DataFrame,
    DoubleType,
    IntegerType,
    SparkSession,
    StringType,
    StructField,
    StructType,
    TimestampType,
    dataclass,
    datetime,
    random,
    timedelta,
    timezone,
    uuid,
):
    @dataclass
    class Order:
        order_id: str
        customer_id: str
        product_id: str
        created_at: datetime
        status: str
        amount: float
        quantity: int
        region: str
        currency: str
        channel: str
        payment_method: str

    # ISO 3166-1 alpha-2 region -> ISO 4217 currency
    REGION_CURRENCY = {
        "US": "USD",
        "CA": "CAD",
        "GB": "GBP",
        "DE": "EUR",
        "FR": "EUR",
        "JP": "JPY",
        "BR": "BRL",
        "IN": "INR",
        "AU": "AUD",
        "SG": "SGD",
    }
    ORDER_STATUSES = ["PLACED", "PAID", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED"]
    STATUS_WEIGHTS = [0.10, 0.20, 0.20, 0.35, 0.10, 0.05]
    CHANNELS = ["WEB", "MOBILE", "STORE"]
    PAYMENT_METHODS = ["CARD", "PAYPAL", "APPLE_PAY", "GOOGLE_PAY", "GIFT_CARD"]
    PRODUCT_IDS = [f"SKU-{n:04d}" for n in range(1, 26)]

    def generate_orders(total: int = 500, window_days: int = 21) -> list[Order]:
        """Generate random e-commerce orders spread over the last `window_days`.

        `created_at` uses a triangular distribution biased toward *now* (mode ~3
        days ago), so the trailing-7-day window is well populated while still
        leaving older rows for the metric-view filter to exclude.
        """
        regions = list(REGION_CURRENCY.keys())
        now = datetime.now(timezone.utc)
        orders: list[Order] = []
        for _ in range(total):
            region = random.choice(regions)
            age_days = random.triangular(0.0, float(window_days), 3.0)
            created_at = now - timedelta(
                days=age_days,
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            orders.append(
                Order(
                    order_id=str(uuid.uuid4()),
                    customer_id=f"CUST-{random.randint(1, 2000):05d}",
                    product_id=random.choice(PRODUCT_IDS),
                    created_at=created_at,
                    status=random.choices(ORDER_STATUSES, weights=STATUS_WEIGHTS, k=1)[0],
                    amount=round(random.uniform(5.0, 500.0), 2),
                    quantity=random.randint(1, 5),
                    region=region,
                    currency=REGION_CURRENCY[region],
                    channel=random.choice(CHANNELS),
                    payment_method=random.choice(PAYMENT_METHODS),
                )
            )
        return orders

    def orders_to_dataframe(orders: list[Order], spark: SparkSession) -> DataFrame:
        rows = [
            (
                o.order_id,
                o.customer_id,
                o.product_id,
                o.created_at,
                o.status,
                o.amount,
                o.quantity,
                o.region,
                o.currency,
                o.channel,
                o.payment_method,
            )
            for o in orders
        ]
        schema = StructType([
            StructField("order_id", StringType(), nullable=False),
            StructField("customer_id", StringType(), nullable=False),
            StructField("product_id", StringType(), nullable=False),
            StructField("created_at", TimestampType(), nullable=False),
            StructField("status", StringType(), nullable=False),
            StructField("amount", DoubleType(), nullable=False),
            StructField("quantity", IntegerType(), nullable=False),
            StructField("region", StringType(), nullable=False),
            StructField("currency", StringType(), nullable=False),
            StructField("channel", StringType(), nullable=False),
            StructField("payment_method", StringType(), nullable=False),
        ])
        return spark.createDataFrame(rows, schema=schema)

    return generate_orders, orders_to_dataframe


@app.cell
def _(DataFrame, generate_orders, orders_to_dataframe, spark: "SparkSession"):
    orders_df: DataFrame = orders_to_dataframe(generate_orders(total=500), spark)
    orders_df.show(5, truncate=False)
    return (orders_df,)


@app.cell
def _(FQ_TABLE, common, orders_df: "DataFrame"):
    # `create_table_ddl` renders 99% of the DDL from the DataFrame schema. We add
    # the catalog-managed feature flag + partition-by below in the explicit
    # CREATE so re-runs are deterministic.
    props = {"delta.feature.catalogManaged": "supported"}
    print(common.create_table_ddl(FQ_TABLE, orders_df.schema, props))
    return


@app.cell
def _(FQ_TABLE, spark: "SparkSession"):
    # Catalog-managed Delta table, partitioned by the metric-view dimension.
    spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {FQ_TABLE} (
      order_id STRING NOT NULL,
      customer_id STRING NOT NULL,
      product_id STRING NOT NULL,
      created_at TIMESTAMP NOT NULL,
      status STRING NOT NULL,
      amount DOUBLE NOT NULL,
      quantity INT NOT NULL,
      region STRING NOT NULL,
      currency STRING NOT NULL,
      channel STRING NOT NULL,
      payment_method STRING NOT NULL
    )
    USING DELTA
    TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported')
    PARTITIONED BY (region)
    """)
    table_ready = FQ_TABLE
    return (table_ready,)


@app.cell
def _(orders_df: "DataFrame", table_ready):
    # overwrite (not append) keeps counts stable across full notebook re-runs
    (
        orders_df.write
        .format("delta")
        .mode("overwrite")
        .saveAsTable(table_ready)
    )
    written = True
    return (written,)


@app.cell
def _(FQ_TABLE, spark: "SparkSession", written):
    # Confirm the load and how many rows land inside the trailing-7-day window
    # the metric view will filter on.
    _ = written
    spark.sql(f"""
    SELECT
      COUNT(*) AS total_orders,
      MIN(created_at) AS earliest,
      MAX(created_at) AS latest,
      SUM(CASE WHEN created_at >= current_timestamp() - INTERVAL 7 DAYS THEN 1 ELSE 0 END) AS rows_last_7_days
    FROM {FQ_TABLE}
    """).show(truncate=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Create the metric view

    `CREATE VIEW ... WITH METRICS LANGUAGE YAML` defines the view. The YAML body
    (delimited by `$$ ... $$`) declares:

    - `source` — the table/view (or SQL query) the metrics compute over.
    - `filter` *(optional)* — a `WHERE`-like row filter. Here it scopes the view
      to the **trailing 7 days** via `current_timestamp() - INTERVAL 7 DAYS` and
      drops CANCELLED / RETURNED orders. Because it uses `current_timestamp()`,
      the window slides forward on every query.
    - `dimensions` — grouping columns (`region`).
    - `measures` — named aggregations read later via `measure(...)`.

    Metric views don't support `CREATE OR REPLACE VIEW`, so we `DROP VIEW IF
    EXISTS` first to keep the cell idempotent.

    > **Note on YAML indentation:** the YAML string is intentionally written at
    > column 0 (not indented to match the Python block) because the YAML body is
    > whitespace-sensitive.
    """)
    return


@app.cell
def _(FQ_METRIC_VIEW, FQ_TABLE, spark: "SparkSession", written):
    _ = written
    spark.sql(f"DROP VIEW IF EXISTS {FQ_METRIC_VIEW}")

    create_metric_view = f"""CREATE VIEW {FQ_METRIC_VIEW}
    WITH METRICS
    LANGUAGE YAML
    AS $$
    version: "0.1"
    source: {FQ_TABLE}
    filter: created_at >= current_timestamp() - INTERVAL 7 DAYS AND status NOT IN ('CANCELLED', 'RETURNED')
    dimensions:
      - name: region
        expr: region
    measures:
      - name: last_7_day_sales
        expr: sum(amount)
      - name: order_count
        expr: count(1)
      - name: avg_order_amount
        expr: avg(amount)
    $$"""

    print(create_metric_view)
    spark.sql(create_metric_view)
    metric_view_ready = FQ_METRIC_VIEW
    return (metric_view_ready,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## List and inspect the metric view

    A metric view shows up on both the **view** surface (`SHOW VIEWS`) and the
    **table** surface (`SHOW TABLES`, alongside its source table). `DESCRIBE
    EXTENDED` reports the dimension/measure columns and the `METRIC_VIEW` type
    plus its stored properties (`metric_view.from.name`, `metric_view.where`).
    """)
    return


@app.cell
def _(FQ_SCHEMA, metric_view_ready, spark: "SparkSession"):
    _ = metric_view_ready
    print("SHOW VIEWS:")
    spark.sql(f"SHOW VIEWS IN {FQ_SCHEMA}").show(truncate=False)
    print("SHOW TABLES:")
    spark.sql(f"SHOW TABLES IN {FQ_SCHEMA}").show(truncate=False)
    return


@app.cell
def _(FQ_METRIC_VIEW, metric_view_ready, spark: "SparkSession"):
    _ = metric_view_ready
    spark.sql(f"DESCRIBE EXTENDED {FQ_METRIC_VIEW}").show(truncate=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Query the metric view

    Read each measure through the `measure(...)` function and `GROUP BY` the
    dimension(s). Spark rewrites this into the aggregations defined in the YAML
    (`sum(amount)`, `count(1)`, `avg(amount)`) over the filtered source.

    > Selecting a measure column directly (e.g. `SELECT last_7_day_sales ...`) is
    > **not** supported — it must go through `measure(...)`.
    """)
    return


@app.cell
def _(FQ_METRIC_VIEW, metric_view_ready, spark: "SparkSession"):
    _ = metric_view_ready
    spark.sql(f"""
    SELECT
      region,
      measure(last_7_day_sales) AS last_7_day_sales,
      measure(order_count) AS orders,
      measure(avg_order_amount) AS avg_order_amount
    FROM {FQ_METRIC_VIEW}
    GROUP BY region
    ORDER BY last_7_day_sales DESC
    """).show(truncate=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Inspect from the UC CLI (optional)

    The metric view is a governed UC object, so you can inspect it with the
    bundled CLI in the running container:

    ~~~bash
    docker exec -it unitycatalog \
      bash bin/uc table get --full_name ecomm.consumer.orders_last_7_day_sales
    ~~~

    ### Fallback: parquet external source

    The upstream doc uses a **parquet external** table as the source (because it
    launches without `delta-spark`). If a metric view over a managed Delta source
    ever misbehaves on your build, you can reproduce the doc's path instead:

    ~~~sql
    CREATE TABLE ecomm.consumer.events (region STRING, cnt INT)
    USING parquet LOCATION '/tmp/uc_events_src';
    INSERT INTO ecomm.consumer.events VALUES ('US', 1), ('US', 2), ('EU', 3);
    ~~~

    ...then point the metric view's `source` at `ecomm.consumer.events`.
    """)
    return


@app.cell(disabled=True)
def _(FQ_METRIC_VIEW, FQ_TABLE, spark: "SparkSession"):
    # Enable this cell to tear the demo objects back down.
    spark.sql(f"DROP VIEW IF EXISTS {FQ_METRIC_VIEW}")
    spark.sql(f"DROP TABLE IF EXISTS {FQ_TABLE}")
    return


if __name__ == "__main__":
    app.run()
