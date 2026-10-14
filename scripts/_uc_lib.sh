#!/usr/bin/env bash
# _uc_lib.sh — shared helpers for the scripts/ Unity Catalog demo tooling.
#
# The bundled local UC (uc=local) keeps its signing keys and admin token inside
# the `uc_conf` Docker volume, mounted in the `unitycatalog` container at
# /home/unitycatalog/etc/conf. These helpers read that material out of the
# running container so the host scripts don't need a local copy.
#
# Sourced (not executed) by mint-user-token.sh / bootstrap-users.sh / grant.sh.

# Config (override via env).
UC_SERVER="${UC_SERVER:-http://localhost:8080}"
UC_CONTAINER="${UC_CONTAINER:-unitycatalog}"
UC_CONF_DIR_IN_CONTAINER="${UC_CONF_DIR_IN_CONTAINER:-/home/unitycatalog/etc/conf}"

uc_base="${UC_SERVER%/}/api/2.1/unity-catalog"
uc_control="${UC_SERVER%/}/api/1.0/unity-control"

uc_require_tools() {
  local tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || {
      echo "ERROR: '$tool' is required but not found on PATH." >&2
      exit 1
    }
  done
}

# Confirm the unitycatalog container is running (fail fast with a clear message).
uc_require_container() {
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$UC_CONTAINER" || {
    echo "ERROR: container '$UC_CONTAINER' is not running." >&2
    echo "       Start the local stack first, e.g.: just uc=local demo-auth" >&2
    exit 1
  }
}

# Read a file out of the UC conf dir in the container to stdout.
uc_cat_conf() { docker exec "$UC_CONTAINER" cat "$UC_CONF_DIR_IN_CONTAINER/$1"; }

# The admin service token UC self-signs at startup (metastore OWNER).
uc_admin_token() {
  if [[ -n "${UC_ADMIN_TOKEN:-}" ]]; then
    printf '%s' "$UC_ADMIN_TOKEN"
    return 0
  fi
  uc_cat_conf token.txt | tr -d '[:space:]'
}
