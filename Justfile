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

# External docker network marimo-spark joins so it can also reach a UC server
# running in a separate compose project. `just net` creates it idempotently.
shared_network := "uc-shared"

# Name/tag of the marimo + spark image built from the local Dockerfile.
image := "marimo-spark"
tag   := "latest"

# Optional pip proxy used at image build time (corporate mirrors, etc).
# Override per-invocation, e.g. `just pip_index_url=https://pypi.acme.com/simple build`.
pip_index_url := "https://pypi-proxy.cloud.databricks.com/simple"

# The compose service that hosts the marimo notebook UI.
marimo_service := "marimo-spark"

# Directory containing the marimo project (local, non-docker workflow).
notebook_dir := "marimo-playground"

# Host directory where pre-downloaded Spark jars land (bind-mounted to /spark/jars).
jars_dir := "spark/jars"

# Maven coordinates pre-downloaded by `just jars` to speed up notebook startup.
# Keep these in sync with the `spark.jars.packages` used in the notebooks. The
# unitycatalog 0.5.0-SNAPSHOT is intentionally omitted — it resolves from the
# local Ivy repo (publishLocal), not a Maven repository. Add iceberg here once a
# notebook references it (no Spark 4.1 runtime is published yet).

# uncomment this to copy the public uc jars
jars_packages := "io.delta:delta-spark_4.1_2.13:4.2.0,io.unitycatalog:unitycatalog-spark_2.13:0.4.1,org.apache.hadoop:hadoop-aws:3.4.2,software.amazon.awssdk:bundle:2.29.52"
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

# .env supplies the optional PIP_INDEX_URL / MAVEN_PROXY proxies used internally.
# Create .env from .env.example if it doesn't already exist (idempotent).
init:
    @test -f .env && echo ".env already exists — leaving it untouched (edit it to set PIP_INDEX_URL / MAVEN_PROXY)." || { cp .env.example .env && echo "Created .env from .env.example — set PIP_INDEX_URL / MAVEN_PROXY if building internally (e.g. Databricks)."; }

# ---- Docker image -----------------------------------------------------------

# Override the proxy ad-hoc with: just --set pip_index_url https://.../simple build
# Build the marimo-spark image via compose (auto-loads .env for PIP_INDEX_URL).
build: init
    {{ if pip_index_url != "" { "PIP_INDEX_URL=" + pip_index_url } else { "" } }} {{compose}} build

# Force a clean rebuild with no layer cache.
rebuild: init
    {{ if pip_index_url != "" { "PIP_INDEX_URL=" + pip_index_url } else { "" } }} {{compose}} build --no-cache

# ---- Spark jars -------------------------------------------------------------

# Resolution runs inside the marimo-spark image via spark-submit (Ivy). When
# MAVEN_PROXY is set (from .env) it renders spark/ivysettings.xml into a
# proxy-only resolver, so Ivy skips the firewalled repo1.maven.org /
# spark-packages defaults and pulls everything from the proxy. ./spark is
# bind-mounted to /spark (see docker-compose.yaml). Re-runnable: existing jars
# are not re-copied, and it requires the image — run `just build` first if needed.
# Pre-download notebook jars (+ transitive deps) into ./spark/jars for fast startup.
jars: init net
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p {{jars_dir}}
    {{compose}} run --rm --no-deps -T --entrypoint bash {{marimo_service}} -lc '
        set -euo pipefail
        ivy_args="--conf spark.jars.ivy=/tmp/ivy"
        if [ -n "${MAVEN_PROXY:-}" ]; then
            sed -e "s#@MAVEN_PROXY@#${MAVEN_PROXY}#g" \
                -e "s#@IVY_LOCAL_ROOT@#/tmp/ivy/local#g" \
                /spark/ivysettings.xml > /tmp/ivysettings.xml
            ivy_args="$ivy_args --conf spark.jars.ivySettings=/tmp/ivysettings.xml"
            echo "Using proxy-first Ivy resolver: ${MAVEN_PROXY}"
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
    {{compose}} up

# Start the environment in the background (detached).
up-detached: init net
    {{compose}} up -d

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

# Restart the environment (down + up detached).
restart: down up-detached

# ---- Teardown ---------------------------------------------------------------

# Stop and remove this project's containers, networks, and persistent volumes.
# Note: no --remove-orphans — it would delete containers on this project's
# network that aren't in this compose file (e.g. a UC server from another
# project). Run `docker compose down --remove-orphans` by hand if you want that.
down:
    {{compose}} down --volumes

# Tear down the environment (counterpart to `just start`).
alias stop := down

# Same as `down` but also removes the locally built image.
clean: down
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
