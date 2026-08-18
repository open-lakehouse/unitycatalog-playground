"""Shared Spark + Unity Catalog bootstrap for the playground notebooks.

Every notebook here needs the same environment setup: resolve the artifact
versions and the Unity Catalog endpoint from the environment, assemble the
Spark config (proxy-first Ivy resolver, S3A switches for the bundled RustFS
store), and build the session. `initialize()` does all of it:

    from common import initialize

    spark = initialize(app_name="DeltaNewIn440")

marimo puts the notebook's directory on `sys.path`, so notebooks in this
directory can import this module directly. The Docker image bind-mounts this
directory, so host edits apply to the container too.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from pyspark.conf import SparkConf
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StructType

__all__ = [
    "CATALOG",
    "DEFAULT_APP_NAME",
    "DEFAULT_MASTER",
    "DELTA_VERSION",
    "HADOOP_VERSION",
    "MAVEN_PROXY_URL",
    "SPARK_VERSION",
    "UNITY_CATALOG_VERSION",
    "create_table_ddl",
    "create_table_using_sql",
    "initialize",
    "spark_config",
    "unity_catalog_server_url",
    "unity_catalog_token",
]


def _spark_version() -> str:
    """Return SPARK_VERSION trimmed to major.minor.

    SPARK_VERSION feeds the Scala artifact coordinates in spark.jars.packages
    (e.g. delta-spark_<major.minor>_2.13), so trim whatever is set to just
    major.minor (e.g. "4.2.0" -> "4.2"). Falls back to "4.2" if unparseable.
    """
    raw = os.environ.get("SPARK_VERSION", "4.2").strip()
    match = re.match(r"(\d+\.\d+)", raw)
    return match.group(1) if match else "4.2"


DELTA_VERSION: str = os.environ.get("DELTA_VERSION", "4.4.0-rc1-SNAPSHOT").strip()
HADOOP_VERSION: str = os.environ.get("HADOOP_VERSION", "3.4.2").strip()
MAVEN_PROXY_URL: str = os.environ.get("MAVEN_PROXY_URL", "").strip()
SPARK_VERSION: str = _spark_version()
UNITY_CATALOG_VERSION: str = os.environ.get("UNITY_CATALOG_VERSION", "0.6.0-rc1-SNAPSHOT").strip()

CATALOG: str = "unity"
DEFAULT_APP_NAME: str = "DeltaCatalogManagedTables"
DEFAULT_MASTER: str = "local[*]"


def unity_catalog_server_url() -> str:
    """Return the Unity Catalog server URL, from the UC_SERVER_URL env var.

    UC_SERVER_URL may be either:
      - a bare host (e.g. `unitycatalog`), combined with UC_SERVER_PORT to form
        http://<host>:<port> — the default for the local/in-docker quickstart, or
      - a full URL including the scheme (e.g. https://uc.openlakehousedemos.dev),
        which is used verbatim (handy for a remote, auth-enabled UC server).
    Defaults to the in-network `unitycatalog` hostname; for a local (uv) run use
    http://localhost:8080.
    """
    server = os.environ.get("UC_SERVER_URL", "unitycatalog")
    if server.startswith(("http://", "https://")):
        return server.rstrip("/")
    return f"http://{server}:{os.environ.get('UC_SERVER_PORT', '8080')}"


def unity_catalog_token() -> str:
    """Bearer token for auth-enabled Unity Catalog servers (set via UC_TOKEN).

    Empty for the local docker/quickstart server, which runs without auth.
    """
    return os.environ.get("UC_TOKEN", "")


def _render_ivy_settings(proxy: str, ivy_dir: str | None) -> str | None:
    """Render spark/ivysettings.xml (proxy-first + local chain) to a temp file.

    Returns the rendered file path, or None if the template can't be found
    (so the caller can fall back to `spark.jars.repositories`).
    """
    local_root = f"{ivy_dir or Path.home() / '.ivy2'}/local"
    candidates = [
        Path("/spark/ivysettings.xml"),
        # repo-relative path for local (uv) runs
        Path(__file__).resolve().parents[2] / "spark" / "ivysettings.xml",
    ]
    template = next((p for p in candidates if p.is_file()), None)
    if template is None:
        return None
    rendered = (
        template.read_text()
        .replace("@MAVEN_PROXY_URL@", proxy)
        .replace("@IVY_LOCAL_ROOT@", local_root)
    )
    out = Path(tempfile.gettempdir()) / "ivysettings-rendered.xml"
    out.write_text(rendered)
    return str(out)


def spark_config(
    catalog: str = CATALOG,
    server_url: str | None = None,
    token: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build the Spark settings that wire Delta + Unity Catalog together.

    `extra` is applied last, so a notebook can override or add to anything here.
    """
    server_url = unity_catalog_server_url() if server_url is None else server_url
    token = unity_catalog_token() if token is None else token

    config = {
        "spark.jars.packages": f"io.delta:delta-spark_{SPARK_VERSION}_2.13:{DELTA_VERSION}," +
        f"io.unitycatalog:unitycatalog-spark_{SPARK_VERSION}_2.13:{UNITY_CATALOG_VERSION},org.apache.hadoop:hadoop-aws:{HADOOP_VERSION}",
        "spark.jars.repositories": "https://central.sonatype.com/repository/maven-snapshots/",
        "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
        "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        f"spark.sql.catalog.{catalog}": "io.unitycatalog.spark.UCSingleCatalog",
        f"spark.sql.catalog.{catalog}.uri": server_url,
        f"spark.sql.catalog.{catalog}.token": token,
        "spark.sql.defaultCatalog": catalog,
        "spark.hadoop.fs.s3.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
        "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
        # Enable only the UC Delta API
        "spark.sql.catalog.uc.deltaRestApi.enabled": "true",
    }

    # When the local stack backs Unity Catalog with the bundled RustFS object
    # store, managed tables live on s3://…. UC vends the S3 credentials at query
    # time, but the endpoint / path-style / plaintext-HTTP switches are
    # client-side, so set them here from S3_ENDPOINT_URL. Leave it empty for AWS
    # S3 or a remote UC on real S3 (this block is then skipped); `just uc=local`
    # sets it to the in-network RustFS service automatically.
    s3_endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip()
    if s3_endpoint:
        config["spark.hadoop.fs.s3a.endpoint"] = s3_endpoint
        config["spark.hadoop.fs.s3a.endpoint.region"] = os.environ.get("S3_REGION", "us-east-1").strip() or "us-east-1"
        config["spark.hadoop.fs.s3a.path.style.access"] = "true"
        config["spark.hadoop.fs.s3a.connection.ssl.enabled"] = "false"

    # When running inside the docker container, the host's local Ivy repository is
    # bind-mounted (see docker-compose.yaml) and SPARK_JARS_IVY is set to /opt/ivy2.
    # Pointing Spark at it makes any locally published unitycatalog-spark SNAPSHOT
    # resolvable from `${SPARK_JARS_IVY}/local`. Running locally (`just run`/uv)
    # leaves SPARK_JARS_IVY unset, so Spark uses the default ~/.ivy2 on your laptop.
    ivy_dir = os.environ.get("SPARK_JARS_IVY")
    if ivy_dir:
        config["spark.jars.ivy"] = ivy_dir

    if MAVEN_PROXY_URL:
        # Behind the firewall, resolve everything through a proxy-first Ivy
        # resolver (spark/ivysettings.xml) instead of Spark's default
        # `spark.jars.repositories`, which only APPENDS the proxy and so probes
        # the unreachable repo1.maven.org / spark-packages first (the "Connection
        # refused" noise) and can let a locally published delta-spark shadow the
        # release. _render_ivy_settings renders the template; on miss it falls
        # back to the old append behaviour so resolution still works.
        rendered = _render_ivy_settings(MAVEN_PROXY_URL, ivy_dir)
        if rendered:
            config["spark.jars.ivySettings"] = rendered
        else:
            config["spark.jars.repositories"] = MAVEN_PROXY_URL

    if extra:
        config.update(extra)

    return config


def initialize(
    app_name: str = DEFAULT_APP_NAME,
    catalog: str = CATALOG,
    master: str = DEFAULT_MASTER,
    server_url: str | None = None,
    token: str | None = None,
    extra_config: dict[str, str] | None = None,
) -> SparkSession:
    """Build (or reuse) the SparkSession the notebooks run against."""
    conf = SparkConf().setMaster(master).setAppName(app_name)
    for key, value in spark_config(catalog, server_url, token, extra_config).items():
        conf = conf.set(key, value)

    return SparkSession.builder.config(conf=conf).getOrCreate()


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
