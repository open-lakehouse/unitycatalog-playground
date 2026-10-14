"""Shared Spark + PyIceberg bootstrap for the UC 0.7 native Iceberg notebooks.

Both clients talk to Unity Catalog through its Iceberg REST catalog (IRC):

    <UC server>/api/2.1/unity-catalog/iceberg      (catalog `uri`)
    warehouse = <UC catalog name>                  (selects the UC catalog)

The `GET /v1/config?warehouse=<catalog>` handshake hands the client a
`prefix` of `catalogs/<catalog>`, so every namespace/table call lands on that
UC catalog. Iceberg namespaces are UC schemas; Iceberg tables are UC tables with
`data_source_format=ICEBERG`. On every `loadTable`/`createTable`, UC vends
short-lived storage credentials (plus a refresh endpoint) in the table config.

    import iceberg_common as ic

    ic.ensure_catalog()                      # UC catalog must exist first
    spark = ic.initialize_spark("MyApp")     # Iceberg SparkCatalog -> UC IRC
    catalog = ic.load_pyiceberg_catalog()    # PyIceberg RestCatalog -> UC IRC

This module lives next to the Iceberg notebooks (marimo puts the notebook's
directory on sys.path) and reuses the UC endpoint + proxy-first Ivy logic from
the parent `notebooks/common.py`.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common  # noqa: E402

from pyspark.conf import SparkConf  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402

__all__ = [
    "CATALOG",
    "ICEBERG_REST_PATH",
    "ICEBERG_VERSION",
    "SPARK_VERSION",
    "ensure_catalog",
    "iceberg_rest_uri",
    "iceberg_spark_config",
    "initialize_spark",
    "load_pyiceberg_catalog",
    "pyiceberg_properties",
    "s3_endpoint",
    "uc_api",
    "uc_table",
]

ICEBERG_VERSION: str = os.environ.get("ICEBERG_VERSION", "1.11.0").strip()
SPARK_VERSION: str = common.SPARK_VERSION
ICEBERG_REST_PATH: str = "/api/2.1/unity-catalog/iceberg"

# UC catalog the notebooks use as the Iceberg `warehouse`. Delta and Iceberg
# tables can share one UC catalog; the Iceberg notebooks keep to their own schemas.
CATALOG: str = os.environ.get("UC_ICEBERG_CATALOG", "unity").strip() or "unity"

# Spark lines Apache Iceberg publishes iceberg-spark-runtime for.
_ICEBERG_SPARK_LINES = ("4.0", "4.1")


def iceberg_rest_uri(server_url: str | None = None) -> str:
    """The UC Iceberg REST catalog base URI (the Iceberg client's `uri`)."""
    server_url = common.unity_catalog_server_url() if server_url is None else server_url
    return f"{server_url.rstrip('/')}{ICEBERG_REST_PATH}"


def s3_endpoint() -> str:
    """Client-side S3 endpoint override (RustFS for `uc=local`), or "" for AWS S3."""
    return os.environ.get("S3_ENDPOINT_URL", "").strip()


def _s3_region() -> str:
    return os.environ.get("S3_REGION", "us-east-1").strip() or "us-east-1"


def uc_api(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    base: str = "/api/2.1/unity-catalog",
) -> dict[str, Any]:
    """Call the UC REST API (`path` is relative to `base`) and return the JSON body."""
    token = common.unity_catalog_token()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{common.unity_catalog_server_url()}{base}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req) as resp:
        payload = resp.read().decode()
    return json.loads(payload) if payload else {}


def uc_table(full_name: str) -> dict[str, Any]:
    """UC's TableInfo for `catalog.schema.table`, with a convenience `full_name`."""
    info = uc_api(f"/tables/{full_name}")
    info["full_name"] = ".".join(info[k] for k in ("catalog_name", "schema_name", "name"))
    return info


def ensure_catalog(name: str = CATALOG, comment: str = "Unity Catalog playground") -> str:
    """Create the UC catalog if it is missing (idempotent); return its name.

    The Iceberg REST catalog only serves catalogs that already exist in UC: an
    unknown `warehouse` gets a 404 from `/v1/config`, so create it up front.
    """
    try:
        uc_api(f"/catalogs/{name}")
        return name
    except urllib.error.HTTPError as err:
        if err.code != 404:
            raise
    try:
        uc_api("/catalogs", method="POST", body={"name": name, "comment": comment})
    except urllib.error.HTTPError as err:
        if err.code != 409:  # created concurrently
            raise
    return name


def iceberg_spark_config(
    catalog: str = CATALOG,
    warehouse: str | None = None,
    server_url: str | None = None,
    token: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Spark settings that register `catalog` as Iceberg's REST SparkCatalog on UC.

    `warehouse` is the UC catalog name (defaults to `catalog`, so Spark names and
    UC names line up). `extra` is applied last.
    """
    if SPARK_VERSION not in _ICEBERG_SPARK_LINES:
        raise RuntimeError(
            f"SPARK_VERSION={SPARK_VERSION}: Apache Iceberg has no iceberg-spark-runtime "
            f"for this Spark line (supported: {', '.join(_ICEBERG_SPARK_LINES)}). Open this "
            "notebook from the marimo-iceberg service (http://localhost:2719, Spark 4.1) "
            "or run `just edit-iceberg` locally."
        )
    warehouse = catalog if warehouse is None else warehouse
    token = common.unity_catalog_token() if token is None else token
    prefix = f"spark.sql.catalog.{catalog}"

    config = {
        "spark.jars.packages": ",".join([
            f"org.apache.iceberg:iceberg-spark-runtime-{SPARK_VERSION}_2.13:{ICEBERG_VERSION}",
            # S3FileIO + the AWS SDK it needs for s3:// table locations.
            f"org.apache.iceberg:iceberg-aws-bundle:{ICEBERG_VERSION}",
        ]),
        "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        prefix: "org.apache.iceberg.spark.SparkCatalog",
        f"{prefix}.type": "rest",
        f"{prefix}.uri": iceberg_rest_uri(server_url),
        f"{prefix}.warehouse": warehouse,
        f"{prefix}.io-impl": "org.apache.iceberg.aws.s3.S3FileIO",
        "spark.sql.defaultCatalog": catalog,
    }
    if token:
        config[f"{prefix}.token"] = token

    # UC vends the S3 credentials (and region) per table; the endpoint and
    # path-style addressing are client-side, so set them for RustFS here.
    # Catalog properties are merged under the per-table config UC returns.
    endpoint = s3_endpoint()
    if endpoint:
        config[f"{prefix}.s3.endpoint"] = endpoint
        config[f"{prefix}.s3.path-style-access"] = "true"
        config[f"{prefix}.client.region"] = _s3_region()
        # The local stack vends a static, pre-minted STS token (s3.sessionToken.0),
        # so UC sends `client.refresh-credentials-endpoint` without
        # `s3.session-token-expires-at-ms`. Iceberg's refreshing credentials
        # provider rejects that ("s3.session-token-expires-at-ms not set"), so use
        # the vended credentials as-is; `just uc=local rotate-creds` renews them.
        config[f"{prefix}.client.refresh-credentials-enabled"] = "false"

    config.update(common.ivy_config())

    if extra:
        config.update(extra)
    return config


def initialize_spark(
    app_name: str = "UnityCatalogIceberg",
    catalog: str = CATALOG,
    warehouse: str | None = None,
    master: str = common.DEFAULT_MASTER,
    extra_config: dict[str, str] | None = None,
) -> SparkSession:
    """Build (or reuse) a SparkSession whose `catalog` is UC's Iceberg REST catalog."""
    conf = SparkConf().setMaster(master).setAppName(app_name)
    # See common.initialize: driver memory must be set before the JVM starts.
    conf = conf.set("spark.driver.memory", common.SPARK_DRIVER_MEMORY)
    if common.SPARK_DRIVER_CORES.isdigit():
        conf = conf.set("spark.driver.cores", common.SPARK_DRIVER_CORES)

    for key, value in iceberg_spark_config(catalog, warehouse, extra=extra_config).items():
        conf = conf.set(key, value)

    return SparkSession.builder.config(conf=conf).getOrCreate()


def pyiceberg_properties(
    warehouse: str = CATALOG,
    server_url: str | None = None,
    token: str | None = None,
) -> dict[str, str]:
    """PyIceberg RestCatalog properties for UC's Iceberg REST catalog."""
    token = common.unity_catalog_token() if token is None else token
    props = {
        "type": "rest",
        "uri": iceberg_rest_uri(server_url),
        "warehouse": warehouse,
    }
    if token:
        props["token"] = token
    endpoint = s3_endpoint()
    if endpoint:
        # PyArrow's S3 filesystem uses path-style addressing unless
        # s3.force-virtual-addressing is set, which is what RustFS needs.
        props["s3.endpoint"] = endpoint
        props["s3.region"] = _s3_region()
    return props


def load_pyiceberg_catalog(name: str = CATALOG, warehouse: str | None = None):
    """Load a PyIceberg RestCatalog bound to the UC catalog `warehouse`."""
    from pyiceberg.catalog import load_catalog

    return load_catalog(name, **pyiceberg_properties(name if warehouse is None else warehouse))
