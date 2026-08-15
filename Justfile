# unitycatalog-playground — task runner
#
# Run `just` (or `just help`) to see all available recipes.
# Requires: docker (with the compose plugin). Local notebook recipes also require `uv`.

# ---- Configuration ----------------------------------------------------------

# Which Unity Catalog to target (a single docker-compose.yaml backs both modes;
# `local` just enables the bundled `unitycatalog` service via a compose profile):
#   "remote" (default) -> only marimo-spark; talks to an external UC (one you run
#                         separately, or a managed UC). Configure the endpoint via
#                         UC_SERVER_URL / UC_SERVER_PORT / UC_TOKEN in .env.
#   "local"            -> also spins up the bundled `unitycatalog` container
#                         alongside marimo-spark (compose profile `local-uc`).
# Override per-invocation, e.g. `just uc=local up` or `just uc=local start`.
uc := "remote"

# Resolve the chosen `uc` mode to a compose profile flag. Add new modes here.
compose_profile := if uc == "local" { "--profile local-uc" } else if uc == "remote" { "" } else { error("uc must be 'local' or 'remote', got '" + uc + "'") }

# Base docker compose invocation used by every recipe below.
compose := "docker compose " + compose_profile

# When targeting the bundled local UC, managed tables live in the in-network
# RustFS S3 object store; point the notebooks' Spark S3A client at it. Empty for
# remote UC (real S3 / AWS default endpoint), so `just up` is unaffected. `up`,
# `up-detached`, and `rotate-creds` export this so it reaches the marimo-spark
# container (a shell env var overrides any blank S3_ENDPOINT_URL in .env).
s3_endpoint_url := if uc == "local" { "http://rustfs:9000" } else { "" }
s3_endpoint_env := if s3_endpoint_url != "" { "S3_ENDPOINT_URL=" + s3_endpoint_url } else { "" }

# External docker network marimo-spark joins so it can also reach a UC server
# running in a separate compose project. `just net` creates it idempotently.
shared_network := "uc-shared"

# Name/tag of the marimo + spark image built from the local Dockerfile.
image := "marimo-spark"
tag   := "latest"

# Optional pip proxy used at image build time (corporate mirrors, etc).
# Override per-invocation, e.g. `just pypi_proxy_url=https://pypi.acme.com/simple build`.
pypi_proxy_url := ""

# The compose service that hosts the marimo notebook UI.
marimo_service := "marimo-spark"

# Directory containing the marimo project (local, non-docker workflow).
notebook_dir := "marimo-playground"

# Host directory where pre-downloaded Spark jars land (bind-mounted to /spark/jars).
jars_dir := "spark/jars"

# Maven coordinates pre-downloaded by `just jars` to speed up notebook startup.
# Keep these in sync with the `spark.jars.packages` used in the notebooks.

# uncomment this to copy the public uc jars
jars_packages := "io.delta:delta-spark_4.2_2.13:4.4.0,io.unitycatalog:unitycatalog-spark_4.2_2.13:0.6.0,org.apache.hadoop:hadoop-aws:3.4.2,software.amazon.awssdk:bundle:2.29.52"
# ---- Meta -------------------------------------------------------------------

# Show all available recipes (default when running bare `just`).
default:
    @just --list

alias help := default

# ---- Full lifecycle ---------------------------------------------------------

# Build the image and bring the whole environment up (foreground).
up-all: build up

# Build the image, bring the environment up detached, then print the marimo URL + token.
start: build up-detached url

# ---- Environment file -------------------------------------------------------

# .env supplies the optional PYPI_PROXY_URL / MAVEN_PROXY_URL proxies used internally.
# Create .env from .env.example if it doesn't already exist (idempotent).
init:
    @test -f .env && echo ".env already exists — leaving it untouched (edit it to set PYPI_PROXY_URL / MAVEN_PROXY_URL)." || { cp .env.example .env && echo "Created .env from .env.example — set PYPI_PROXY_URL / MAVEN_PROXY_URL if building internally (e.g. Databricks)."; }

# ---- Docker image -----------------------------------------------------------

# Override the proxy ad-hoc with: just --set pypi_proxy_url https://.../simple build
# Build the marimo-spark image via compose (auto-loads .env for PYPI_PROXY_URL).
build: init
    {{ if pypi_proxy_url != "" { "PYPI_PROXY_URL=" + pypi_proxy_url } else { "" } }} {{compose}} build

# Force a clean rebuild with no layer cache.
rebuild: init
    {{ if pypi_proxy_url != "" { "PYPI_PROXY_URL=" + pypi_proxy_url } else { "" } }} {{compose}} build --no-cache

# Stage a locally-built delta-spark wheel for a pre-release override build. The
# wheel is copied into spark/delta-override/ (git-ignored); set the printed
# DELTA_SPARK_WHEEL value in .env, then `just rebuild` to bake it into the image.
# Usage: just stage-delta ~/Desktop/delta-4.4.0/python/delta_spark-4.4.0-py3-none-any.whl
stage-delta wheel:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f "{{wheel}}" ]; then
        echo "No such wheel: {{wheel}}" >&2
        exit 1
    fi
    mkdir -p spark/delta-override
    cp -v "{{wheel}}" spark/delta-override/
    name="$(basename "{{wheel}}")"
    echo ""
    echo "Staged spark/delta-override/${name}"
    echo "Now set in .env:  DELTA_SPARK_WHEEL=${name}"
    echo "Then rebuild:     just rebuild"

# ---- Spark jars -------------------------------------------------------------

# Resolution runs inside the marimo-spark image via spark-submit (Ivy). When
# MAVEN_PROXY_URL is set (from .env) it renders spark/ivysettings.xml into a
# proxy-first resolver, so Ivy skips the firewalled repo1.maven.org /
# spark-packages defaults and pulls releases from the proxy; artifacts the proxy
# lacks (e.g. locally `sbt publishLocal`-ed delta-spark / unitycatalog-spark
# builds) fall through to the mounted host Ivy repo at /opt/ivy2/local — the same
# repo the notebooks resolve from (SPARK_JARS_IVY=/opt/ivy2). Downloaded jars are
# still staged under /tmp/ivy so only THIS run's set is copied to ./spark/jars.
# ./spark is bind-mounted to /spark (see docker-compose.yaml). Re-runnable:
# existing jars are not re-copied, and it requires the image — run `just build`
# first if needed.
# Pre-download notebook jars (+ transitive deps) into ./spark/jars for fast startup.
jars: init net
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p {{jars_dir}}
    {{compose}} run --rm --no-deps -T --entrypoint bash {{marimo_service}} -lc '
        set -euo pipefail
        ivy_args="--conf spark.jars.ivy=/tmp/ivy"
        if [ -n "${MAVEN_PROXY_URL:-}" ]; then
            sed -e "s#@MAVEN_PROXY_URL@#${MAVEN_PROXY_URL}#g" \
                -e "s#@IVY_LOCAL_ROOT@#/opt/ivy2/local#g" \
                /spark/ivysettings.xml > /tmp/ivysettings.xml
            ivy_args="$ivy_args --conf spark.jars.ivySettings=/tmp/ivysettings.xml"
            echo "Using proxy-first Ivy resolver: ${MAVEN_PROXY_URL}"
        fi
        printf "pass\n" > /tmp/noop.py
        "$SPARK_HOME"/bin/spark-submit \
            --packages "{{jars_packages}}" \
            $ivy_args \
            /tmp/noop.py
        cp -vn /tmp/ivy/jars/*.jar /spark/jars/
    '
    echo ""
    echo "Pre-downloaded jars now in {{jars_dir}}/ :"
    ls -1 {{jars_dir}}/*.jar 2>/dev/null | sed "s#^#  #" || echo "  (none found)"

# ---- Environment (docker compose) -------------------------------------------

# marimo-spark joins `{{shared_network}}` (declared `external: true` in the
# compose file), so it must exist before compose can start anything — otherwise
# you get "network ... declared as external, but could not be found".
# Create the shared external docker network if it's missing (idempotent).
net:
    @docker network inspect {{shared_network}} >/dev/null 2>&1 \
        && echo "docker network '{{shared_network}}' already present." \
        || { echo "Creating external docker network '{{shared_network}}'..."; docker network create {{shared_network}} >/dev/null; }

# Start the environment in the foreground (add `uc=local` for the bundled UC).
up: init net
    {{s3_endpoint_env}} {{compose}} up

# Start the environment in the background (detached).
up-detached: init net
    {{s3_endpoint_env}} {{compose}} up -d

# Show running compose services.
ps:
    {{compose}} ps

# Follow logs for all services (Ctrl-C to stop).
logs:
    {{compose}} logs -f

# Follow logs for just the marimo notebook service.
logs-marimo:
    {{compose}} logs -f {{marimo_service}}

# Print the marimo notebook URL + access token (waits for the container to boot).
url:
    #!/usr/bin/env bash
    set -euo pipefail
    for _ in $(seq 1 30); do
        line=$({{compose}} logs {{marimo_service}} 2>/dev/null \
            | grep -oE 'http://[0-9.]+:2718[^[:space:]]*access_token=[A-Za-z0-9_-]+' \
            | tail -n1 || true)
        if [ -n "${line}" ]; then
            token=$(printf '%s' "${line}" | sed -E 's/.*access_token=//')
            localhost_url=$(printf '%s' "${line}" | sed -E 's#http://[0-9.]+:#http://localhost:#')
            echo ""
            echo "marimo is ready — open it in your browser:"
            echo "  ${localhost_url}"
            echo ""
            echo "  access token: ${token}"
            exit 0
        fi
        sleep 1
    done
    echo "No marimo URL found yet — the container may still be starting. Try: just url   (or: just logs-marimo)"

# Log in to the console with RUSTFS_ACCESS_KEY / RUSTFS_SECRET_KEY
# (defaults: rustfsadmin / rustfsadmin).
# Print the RustFS console + S3 API URLs (uc=local).
rustfs-url:
    @echo "RustFS console: http://localhost:${RUSTFS_CONSOLE_PORT:-9001}"
    @echo "RustFS S3 API:  http://localhost:${RUSTFS_API_PORT:-9000}"

# Use when managed-table reads/writes start failing with expired- or invalid-
# credential errors. uc=local only; the STS lifetime defaults to 12h
# (STS_DURATION_SECONDS in .env). The bucket + its data are left untouched.
# Re-mint the RustFS STS credential UC vends to Spark, then restart UC to load it.
rotate-creds:
    {{s3_endpoint_env}} {{compose}} up -d --force-recreate --no-deps rustfs-init
    {{compose}} restart unitycatalog

# Restart the environment (down + up detached).
restart: down up-detached

# ---- Teardown ---------------------------------------------------------------

# Stop and remove this project's containers and networks.
# Named volumes are kept, so a subsequent `just uc=local up` / `just restart`
# restores the same catalog metadata (`uc_postgres_data`) and managed table data
# (`rustfs_data`). The `uc_conf` volume is regenerated on the next `up`.
# Note: no --remove-orphans — it would delete containers on this project's
# network that aren't in this compose file (e.g. a UC server from another
# project). Run `docker compose down --remove-orphans` by hand if you want that.
down:
    {{compose}} down

# Tear down the environment (counterpart to `just start`).
alias stop := down

# Wipes local UC Postgres metadata (`uc_postgres_data`) AND all RustFS
# managed-table data (`rustfs_data`).
# Like `down`, but also deletes named volumes.
down-volumes:
    {{compose}} down --volumes

# Wipe volumes and remove the locally built marimo-spark image.
clean: down-volumes
    -docker image rm {{image}}:{{tag}}

# ---- Local notebook workflow (uv, no docker) --------------------------------

# Install the marimo project's Python dependencies with uv.
sync:
    cd {{notebook_dir}} && uv sync

# Open the Unity Catalog notebook locally in edit mode.
edit:
    cd {{notebook_dir}} && uv run marimo edit notebooks/unitycatalog-delta.py

# Run the Unity Catalog notebook locally as a read-only app.
run:
    cd {{notebook_dir}} && uv run marimo run notebooks/unitycatalog-delta.py
