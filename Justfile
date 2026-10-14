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

# Bundled-UC auth mode for `set-auth` (uc=local): "enable" or "disable", e.g.
# `just uc=local auth=enable set-auth`. Saved to .env as UC_AUTHORIZATION, which
# rustfs-init renders into server.properties on every `up`.
auth := ""

# External docker network marimo-spark joins so it can also reach a UC server
# running in a separate compose project. `just net` creates it idempotently.
shared_network := "uc-shared"

# Name/tag of the marimo + spark image built from the local Dockerfile.
image := "marimo-spark"
tag   := "local"

# Optional pip proxy used at image build time (corporate mirrors, etc).
# Override per-invocation, e.g. `just pypi_proxy_url=https://pypi.acme.com/simple build`.
pypi_proxy_url := ""

# The compose service that hosts the marimo notebook UI.
marimo_service := "marimo-spark"

# Spark 4.1 + Iceberg + PyIceberg notebook service (UC 0.7 native Iceberg), on :2719.
iceberg_service := "marimo-iceberg"
iceberg_image := "marimo-iceberg"

# Directory containing the marimo project (local, non-docker workflow).
notebook_dir := "marimo-playground"

# ---- Meta -------------------------------------------------------------------

# Show all available recipes (default when running bare `just`).
default:
    @just --list

alias help := default

# ---- Full lifecycle ---------------------------------------------------------

# Build the image and bring the whole environment up (foreground).
up-all: build up

# Build the images, bring the environment up detached, then print both marimo URLs + tokens.
start: build up-detached url url-iceberg

# ---- Environment file -------------------------------------------------------

# .env supplies the optional PYPI_PROXY_URL / MAVEN_PROXY_URL proxies used internally.
# Create .env from .env.example if it doesn't already exist (idempotent).
init:
    @test -f .env && echo ".env already exists — leaving it untouched (edit it to set PYPI_PROXY_URL / MAVEN_PROXY_URL)." || { cp .env.example .env && echo "Created .env from .env.example — set PYPI_PROXY_URL / MAVEN_PROXY_URL if building internally (e.g. Databricks)."; }

# ---- Docker image -----------------------------------------------------------

# Override the proxy ad-hoc with: just --set pypi_proxy_url https://.../simple build
# Build the marimo-spark + marimo-iceberg images via compose.
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

# Follow logs for just the Spark 4.1 / Iceberg marimo service.
logs-iceberg:
    {{compose}} logs -f {{iceberg_service}}

# Print a marimo notebook URL + access token (waits for the container to boot).
url service=marimo_service port="2718":
    #!/usr/bin/env bash
    set -euo pipefail
    for _ in $(seq 1 30); do
        line=$({{compose}} logs {{service}} 2>/dev/null \
            | grep -oE 'http://[0-9.]+:{{port}}[^[:space:]]*access_token=[A-Za-z0-9_-]+' \
            | tail -n1 || true)
        if [ -n "${line}" ]; then
            token=$(printf '%s' "${line}" | sed -E 's/.*access_token=//')
            localhost_url=$(printf '%s' "${line}" | sed -E 's#http://[0-9.]+:#http://localhost:#')
            echo ""
            echo "marimo ({{service}}) is ready — open it in your browser:"
            echo "  ${localhost_url}"
            echo ""
            echo "  access token: ${token}"
            exit 0
        fi
        sleep 1
    done
    echo "No marimo URL found yet for {{service}} — it may still be starting. Try: just url {{service}} {{port}}   (or: {{compose}} logs {{service}})"

# Print the Iceberg notebook (marimo-iceberg, :2719) URL + access token.
url-iceberg: (url iceberg_service "2719")

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
rotate-creds: _reload-uc

# Run once on a uc_postgres_data volume created by UC 0.6 (new volumes don't
# need it): hbm2ddl=update never alters existing columns, so property values
# longer than 255 chars fail until uc_properties.property_value is widened.
# Widen uc_properties.property_value for UC 0.7 (uc=local, existing Postgres volume).
db-upgrade:
    {{compose}} exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER TABLE uc_properties ALTER COLUMN property_value TYPE text;"'

# Restart the environment (down + up detached).
restart: down up-detached

# Waits for rustfs-init to exit before the restart, so UC never starts against a
# half-rendered server.properties.
# Re-render the uc_conf volume (fresh STS creds + UC_AUTHORIZATION), then restart UC.
_reload-uc:
    {{s3_endpoint_env}} {{compose}} up -d --force-recreate --no-deps rustfs-init
    @test "$(docker wait rustfs-init)" = 0 || { echo "rustfs-init failed; see: docker logs rustfs-init" >&2; exit 1; }
    {{compose}} restart unitycatalog

# ---- Authentication (uc=local) ----------------------------------------------
# See docs/uc/authentication.md for why these matter and how UC auth works.

# Fail fast when a recipe that manages the bundled UC is run without uc=local.
_require-local:
    #!/usr/bin/env bash
    if [ "{{uc}}" != "local" ]; then
        echo "This recipe manages the bundled Unity Catalog; run it with uc=local (e.g. just uc=local demo-auth)." >&2
        exit 1
    fi

# Persist the bundled-UC auth mode as UC_AUTHORIZATION in .env.
_save-auth mode: init
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{mode}}" in
        enable|disable) ;;
        *) echo "auth must be 'enable' or 'disable' (got '{{mode}}'), e.g. just uc=local auth=enable set-auth" >&2; exit 2 ;;
    esac
    if grep -q '^UC_AUTHORIZATION=' .env; then
        sed -i.bak 's/^UC_AUTHORIZATION=.*/UC_AUTHORIZATION={{mode}}/' .env && rm -f .env.bak
    else
        printf '\nUC_AUTHORIZATION=%s\n' "{{mode}}" >> .env
    fi
    echo "Saved UC_AUTHORIZATION={{mode}} in .env."

# A stopped stack needs nothing here: the next `up` renders the saved mode.
# Re-render + restart UC only if it is already running.
_reload-uc-if-running:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "$(docker ps -q --filter name='^unitycatalog$' --filter status=running)" ]; then
        {{just_executable()}} uc={{uc}} _reload-uc
    fi

# Block until the UC REST API answers: HTTP 200 with auth off, 401 with auth on.
_wait-uc:
    #!/usr/bin/env bash
    set -euo pipefail
    base="${UC_SERVER:-http://localhost:8080}"
    printf 'Waiting for Unity Catalog at %s ' "$base"
    for _ in $(seq 1 60); do
        code="$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$base/api/2.1/unity-catalog/catalogs" || true)"
        case "$code" in
            200) echo " ready, auth disabled (unauthenticated requests get 200)."; exit 0 ;;
            401) echo " ready, auth enabled (unauthenticated requests get 401)."; exit 0 ;;
        esac
        printf '.'
        sleep 2
    done
    echo
    echo "Unity Catalog did not answer within 120s. Check: just uc=local logs" >&2
    exit 1

# Build, start the bundled UC with auth disabled (open, no tokens), and print the marimo URLs.
demo-noauth: _require-local (_save-auth "disable") build _reload-uc-if-running up-detached _wait-uc url url-iceberg

# Build, start the bundled UC with auth enabled, seed the demo personas, and print the admin token + marimo URLs.
demo-auth: _require-local (_save-auth "enable") build _reload-uc-if-running up-detached _wait-uc bootstrap-users url url-iceberg
    @echo ""
    @echo "Admin token (metastore OWNER, never expires). Persona tokens: just uc=local token-for <email>"
    @{{just_executable()}} token

# Usage: just uc=local auth=enable set-auth   (or auth=disable). Saved to .env so
# later `up` / `restart` keep it. UC reads server.properties only at startup, so
# a running server is re-rendered and restarted; a stopped stack picks the mode
# up on the next `just uc=local up`.
# Turn bundled-UC auth on or off without a rebuild (saves to .env, restarts UC).
set-auth: _require-local (_save-auth auth)
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "$(docker ps -q --filter name='^unitycatalog$' --filter status=running)" ]; then
        echo "unitycatalog is not running; the new mode applies on the next: just uc=local up-detached"
        exit 0
    fi
    {{just_executable()}} uc={{uc}} _reload-uc _wait-uc

# Same identity as etc/conf/token.txt inside the container. UC re-signs it on
# every start, but the signing key persists in the uc_conf volume, so old copies
# keep working until `just down-volumes` / `just clean`.
# Print the admin token UC self-signs at startup (metastore OWNER, no expiry).
token:
    @bash -c 'source scripts/_uc_lib.sh && uc_require_container && uc_admin_token' && echo

# Usage: just uc=local token-for scott@uc-demos.dev   (EXP_DAYS=7 shortens the 30-day default)
# Mint a bearer token for a UC user, signed with the server's own key (no identity provider needed).
token-for email:
    @scripts/mint-user-token.sh "{{email}}"

# Idempotent: existing users and grants are left in place.
# Seed the demo personas (power-user, scott, jules, lisa, robert) and their grants on demo.workshop.
bootstrap-users:
    @scripts/bootstrap-users.sh

# Usage: just uc=local grant grant  -t schema -n demo.workshop -p robert@uc-demos.dev -P SELECT
#        just uc=local grant revoke -t schema -n demo.workshop -p robert@uc-demos.dev -P SELECT
#        just uc=local grant --help
# Grant or revoke a Unity Catalog privilege for a user (runs as the admin token).
[positional-arguments]
grant *args:
    @scripts/grant.sh "$@"

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

# Wipe volumes and remove the locally built marimo-spark / marimo-iceberg images.
clean: down-volumes
    -docker image rm {{image}}:{{tag}}
    -docker image rm {{iceberg_image}}:{{tag}}

# ---- Local notebook workflow (uv, no docker) --------------------------------
#
# pyproject.toml has one dependency group per notebook image: `delta` (default,
# Spark 4.2) and `iceberg` (Spark 4.1 + PyIceberg). They conflict, so the venv
# holds one at a time; switching between them re-syncs pyspark.
#
# Behind a PyPI proxy, uv re-locks on every sync and writes the proxy's URLs
# into uv.lock; clean-lock points them back at public PyPI for CI. --frozen
# keeps `uv run` from re-locking (and re-dirtying uv.lock) after a sync.

iceberg_group := "--no-default-groups --group iceberg"
export_flags  := "--frozen --format requirements-txt --no-emit-project --no-default-groups"

# Install the Delta (Spark 4.2) dependencies with uv, then clean uv.lock.
sync:
    cd {{notebook_dir}} && uv sync
    @{{just_executable()}} clean-lock

# Install the Iceberg (Spark 4.1 + PyIceberg) dependencies with uv, then clean uv.lock.
sync-iceberg:
    cd {{notebook_dir}} && uv sync {{iceberg_group}}
    @{{just_executable()}} clean-lock

# Re-lock after editing pyproject.toml, clean uv.lock, and re-export both image requirements files.
lock:
    cd {{notebook_dir}} && uv lock
    @{{just_executable()}} clean-lock
    cd {{notebook_dir}} && uv export {{export_flags}} --group delta --output-file requirements.lock
    cd {{notebook_dir}} && uv export {{export_flags}} --group iceberg --output-file requirements-iceberg.lock

# Rewrite private PyPI proxy URLs in uv.lock to public PyPI (idempotent).
clean-lock:
    @scripts/clean-uv-lock.py

# Fail if uv.lock references a private index or the image requirements files are stale (CI guard).
check-lock:
    #!/usr/bin/env bash
    set -euo pipefail
    scripts/clean-uv-lock.py --check
    cd {{notebook_dir}}
    stale=0
    for pair in delta:requirements.lock iceberg:requirements-iceberg.lock; do
        group="${pair%%:*}" file="${pair#*:}"
        if ! diff -u <(grep -v '^ *#' "$file") \
                     <(uv export {{export_flags}} --group "$group" | grep -v '^ *#') >/dev/null; then
            echo "$file is out of date with uv.lock; run \`just lock\`" >&2
            stale=1
        fi
    done
    exit "$stale"

# Open the Unity Catalog notebook locally in edit mode.
edit: sync
    cd {{notebook_dir}} && uv run --frozen marimo edit notebooks/unitycatalog-delta.py

# Run the Unity Catalog notebook locally as a read-only app.
run: sync
    cd {{notebook_dir}} && uv run --frozen marimo run notebooks/unitycatalog-delta.py

# Open the native Iceberg notebooks locally (Spark 4.1 + PyIceberg).
edit-iceberg: sync-iceberg
    cd {{notebook_dir}} && SPARK_VERSION=4.1 uv run --frozen {{iceberg_group}} marimo edit notebooks/iceberg/
