#!/usr/bin/env bash
# grant.sh — grant or revoke a Unity Catalog privilege for a principal.
#
# Wraps the Grants REST API (PATCH /api/2.1/unity-catalog/permissions/{type}/{name}).
# Privileges may be written with spaces ("USE CATALOG") or underscores
# (USE_CATALOG) — the latter avoids shell/just quoting headaches. Matching is
# case-insensitive. The admin bearer token is read from the running unitycatalog
# container (uc_conf/token.txt) when auth is enabled.
#
# Usage:
#   scripts/grant.sh <grant|revoke> -t <type> -n <name> -p <principal> -P <privilege>
#   scripts/grant.sh --help
#   just uc=local grant <grant|revoke> -t <type> -n <name> -p <principal> -P <privilege>
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_uc_lib.sh
source "$HERE/_uc_lib.sh"

# --- enum values (mirror io.unitycatalog.client.model.{Privilege,SecurableType}) ---
PRIVILEGES=(
  "CREATE CATALOG" "USE CATALOG" "CREATE SCHEMA" "USE SCHEMA" "CREATE TABLE"
  "SELECT" "MODIFY" "CREATE FUNCTION" "EXECUTE" "CREATE VOLUME" "READ VOLUME"
  "CREATE MODEL" "CREATE EXTERNAL LOCATION" "READ FILES" "WRITE FILES"
  "CREATE EXTERNAL TABLE" "CREATE EXTERNAL VOLUME" "CREATE MANAGED STORAGE"
  "CREATE STORAGE CREDENTIAL"
)
SECURABLE_TYPES=(
  metastore catalog schema table function volume registered_model
  external_location credential
)

usage() {
  cat <<EOF
grant.sh — grant or revoke a Unity Catalog privilege for a principal.

USAGE:
  scripts/grant.sh <grant|revoke> -t <type> -n <name> -p <principal> -P <privilege>
  just uc=local grant <grant|revoke> -t <type> -n <name> -p <principal> -P <privilege>

ARGUMENTS:
  grant|revoke           add (grant) or remove (revoke) the privilege
  -t, --type <type>      securable type (see list below)
  -n, --name <name>      securable full name (catalog, catalog.schema,
                         catalog.schema.table)
  -p, --principal <id>   principal to grant to (user email or group)
  -P, --privilege <priv> privilege (spaces or underscores both accepted)

EXAMPLES:
  just uc=local grant grant  -t catalog -n demo            -p lisa@uc-demos.dev  -P USE_CATALOG
  just uc=local grant grant  -t table   -n demo.workshop.pets -p robert@uc-demos.dev -P SELECT
  just uc=local grant revoke -t schema  -n demo.workshop   -p jules@uc-demos.dev -P MODIFY

SECURABLE TYPES:
EOF
  printf '  %s\n' "${SECURABLE_TYPES[@]}"
  echo
  echo "PRIVILEGES:"
  printf '  %s\n' "${PRIVILEGES[@]}"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -eq 0 ]]; then
  usage
  exit 0
fi

ACTION="" TYPE="" NAME="" PRINCIPAL="" PRIV=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    grant|revoke)   ACTION="$1"; shift ;;
    -t|--type)      TYPE="${2:-}"; shift 2 ;;
    -n|--name)      NAME="${2:-}"; shift 2 ;;
    -p|--principal) PRINCIPAL="${2:-}"; shift 2 ;;
    -P|--privilege) PRIV="${2:-}"; shift 2 ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "ERROR: unknown argument '$1'. Run 'scripts/grant.sh --help'." >&2; exit 2 ;;
  esac
done

[[ "$ACTION" == "grant" || "$ACTION" == "revoke" ]] || { echo "ERROR: first argument must be 'grant' or 'revoke'." >&2; exit 2; }
for v in TYPE NAME PRINCIPAL PRIV; do
  [[ -n "${!v}" ]] || { echo "ERROR: missing required option for $v. Run 'scripts/grant.sh --help'." >&2; exit 2; }
done

# Normalize: type lowercased; privilege uppercased with underscores -> spaces.
TYPE="$(printf '%s' "$TYPE" | tr 'A-Z' 'a-z')"
PRIV="$(printf '%s' "$PRIV" | tr 'a-z_' 'A-Z ')"

contains() { local needle="$1"; shift; local x; for x in "$@"; do [[ "$x" == "$needle" ]] && return 0; done; return 1; }
contains "$TYPE" "${SECURABLE_TYPES[@]}" || { echo "ERROR: invalid securable type '$TYPE'. Run 'scripts/grant.sh --help'." >&2; exit 2; }
contains "$PRIV" "${PRIVILEGES[@]}"      || { echo "ERROR: invalid privilege '$PRIV'. Run 'scripts/grant.sh --help'." >&2; exit 2; }

uc_require_tools jq curl docker
uc_require_container

TOKEN="$(uc_admin_token)"
AUTH_ARGS=()
[[ -n "$TOKEN" ]] && AUTH_ARGS=(-H "Authorization: Bearer $TOKEN")

if [[ "$ACTION" == "grant" ]]; then
  PAYLOAD="$(jq -cn --arg p "$PRINCIPAL" --arg priv "$PRIV" '{changes:[{principal:$p, add:[$priv], remove:[]}]}')"
  verb="granted"
else
  PAYLOAD="$(jq -cn --arg p "$PRINCIPAL" --arg priv "$PRIV" '{changes:[{principal:$p, add:[], remove:[$priv]}]}')"
  verb="revoked"
fi

ENC_NAME="$(jq -rn --arg n "$NAME" '$n|@uri')"
PERM_URL="$uc_base/permissions/${TYPE}/${ENC_NAME}"

echo "== $ACTION '$PRIV' on $TYPE '$NAME' for '$PRINCIPAL' =="
HTTP_BODY="$(mktemp)"
trap 'rm -f "$HTTP_BODY"' EXIT
CODE="$(curl -sS -m 30 -o "$HTTP_BODY" -w '%{http_code}' \
  -X PATCH "$PERM_URL" \
  ${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"} \
  -H 'Content-Type: application/json' \
  -d "$PAYLOAD")"

if [[ "$CODE" == 2* ]]; then
  echo "  $verb '$PRIV' ($CODE). Current privilege assignments:"
  jq . "$HTTP_BODY" 2>/dev/null || cat "$HTTP_BODY"
else
  echo "ERROR: $ACTION failed (HTTP $CODE):" >&2
  cat "$HTTP_BODY" >&2
  exit 1
fi
