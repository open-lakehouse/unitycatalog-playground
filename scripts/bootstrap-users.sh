#!/usr/bin/env bash
# bootstrap-users.sh — seed the auth-enabled local UC with demo personas.
#
# Idempotent. Requires the local stack running with auth enabled
# (just uc=local demo-auth). Uses the built-in `admin` service token (metastore
# OWNER, read from the container) for all privileged operations.
#
# Creates five @uc-demos.dev users and wires a teaching-friendly RBAC layout:
#
#   admin (built-in)      true metastore OWNER — runs this bootstrap
#   power-user            metastore CREATE CATALOG / STORAGE CREDENTIAL /
#                         EXTERNAL LOCATION; creates & OWNS catalog `demo`
#                         and schema `demo.workshop`
#   scott                 author  on demo.workshop (USE/CREATE TABLE/SELECT/MODIFY)
#   jules                 read-write on demo.workshop (USE/SELECT/MODIFY)
#   lisa                  read-only  on demo.workshop (USE/SELECT)
#   robert                no grants (demonstrates 403; grant live in the guide)
#
# Schema-level SELECT/MODIFY inherit down to tables created later (e.g. via the
# marimo/Spark notebook), so the personas work without pre-creating a table.
#
# Usage:  just uc=local bootstrap-users     (or: scripts/bootstrap-users.sh)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_uc_lib.sh
source "$HERE/_uc_lib.sh"

DEMO_CATALOG="${DEMO_CATALOG:-demo}"
DEMO_SCHEMA="${DEMO_SCHEMA:-workshop}"

uc_require_tools jq curl docker uuidgen openssl
uc_require_container

ADMIN_TOKEN="$(uc_admin_token)"
[[ -n "$ADMIN_TOKEN" ]] || { echo "ERROR: no admin token — is auth enabled? (just uc=local demo-auth)" >&2; exit 1; }

# Fail fast if auth is actually disabled (admin token then meaningless).
code="$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$uc_base/catalogs" || true)"
if [[ "$code" != "401" ]]; then
  echo "WARNING: unauthenticated /catalogs returned HTTP $code (expected 401)." >&2
  echo "         Auth may be disabled; personas/tokens only matter with auth=enable." >&2
fi

acurl() { curl -sS -m 30 -H "Authorization: Bearer $ADMIN_TOKEN" "$@"; }

# --- 1. create users (SCIM) -------------------------------------------------
create_user() {
  local email="$1" name="$2" body resp code
  body="$(jq -cn --arg n "$name" --arg e "$email" \
    '{schemas:["urn:ietf:params:scim:schemas:core:2.0:User"], displayName:$n, active:true, emails:[{value:$e, primary:true}]}')"
  local tmp; tmp="$(mktemp)"
  code="$(acurl -o "$tmp" -w '%{http_code}' -X POST "$uc_control/scim2/Users" \
    -H 'Content-Type: application/scim+json' -d "$body" || true)"
  if [[ "$code" == 2* ]]; then
    echo "  created user $email"
  elif grep -qiE 'already|exist|conflict' "$tmp" || [[ "$code" == "409" ]]; then
    echo "  user $email already exists"
  else
    echo "  ERROR creating $email (HTTP $code):" >&2; cat "$tmp" >&2; rm -f "$tmp"; exit 1
  fi
  rm -f "$tmp"
}

echo "== creating demo users =="
create_user "power-user@uc-demos.dev" "Power User"
create_user "scott@uc-demos.dev"      "Scott"
create_user "jules@uc-demos.dev"      "Jules"
create_user "lisa@uc-demos.dev"       "Lisa"
create_user "robert@uc-demos.dev"     "Robert"

# --- 2. grant helper (PATCH permissions with the admin token) ---------------
# grant_priv <type> <name> <principal> <PRIV[,PRIV,...]>
grant_priv() {
  local type="$1" name="$2" principal="$3" privs="$4"
  local add enc url tmp code
  add="$(printf '%s' "$privs" | jq -Rc 'split(",")')"
  enc="$(jq -rn --arg n "$name" '$n|@uri')"
  url="$uc_base/permissions/${type}/${enc}"
  tmp="$(mktemp)"
  code="$(acurl -o "$tmp" -w '%{http_code}' -X PATCH "$url" -H 'Content-Type: application/json' \
    -d "$(jq -cn --arg p "$principal" --argjson add "$add" '{changes:[{principal:$p, add:$add, remove:[]}]}')" || true)"
  if [[ "$code" == 2* ]]; then
    echo "  granted [$privs] on $type $name -> $principal"
  else
    echo "  ERROR granting [$privs] on $type $name -> $principal (HTTP $code):" >&2; cat "$tmp" >&2; rm -f "$tmp"; exit 1
  fi
  rm -f "$tmp"
}

echo "== granting metastore privileges to power-user =="
grant_priv metastore metastore "power-user@uc-demos.dev" "CREATE CATALOG,CREATE STORAGE CREDENTIAL,CREATE EXTERNAL LOCATION"

# --- 3. create demo catalog + schema AS power-user (so it owns them) --------
echo "== creating catalog '$DEMO_CATALOG' + schema '$DEMO_CATALOG.$DEMO_SCHEMA' as power-user =="
PU_TOKEN="$("$HERE/mint-user-token.sh" "power-user@uc-demos.dev" 2>/dev/null)"
[[ -n "$PU_TOKEN" ]] || { echo "ERROR: failed to mint power-user token" >&2; exit 1; }

pucurl() { curl -sS -m 30 -H "Authorization: Bearer $PU_TOKEN" "$@"; }

create_or_skip() {  # <description> <url> <json-body>
  local desc="$1" url="$2" body="$3" tmp code
  tmp="$(mktemp)"
  code="$(pucurl -o "$tmp" -w '%{http_code}' -X POST "$url" -H 'Content-Type: application/json' -d "$body" || true)"
  if [[ "$code" == 2* ]]; then
    echo "  created $desc"
  elif grep -qiE 'already|exist|conflict' "$tmp" || [[ "$code" == "409" ]]; then
    echo "  $desc already exists"
  else
    echo "  ERROR creating $desc (HTTP $code):" >&2; cat "$tmp" >&2; rm -f "$tmp"; exit 1
  fi
  rm -f "$tmp"
}

create_or_skip "catalog $DEMO_CATALOG" "$uc_base/catalogs" \
  "$(jq -cn --arg n "$DEMO_CATALOG" '{name:$n, comment:"uc-demos workshop catalog (owned by power-user)"}')"
create_or_skip "schema $DEMO_CATALOG.$DEMO_SCHEMA" "$uc_base/schemas" \
  "$(jq -cn --arg n "$DEMO_SCHEMA" --arg c "$DEMO_CATALOG" '{name:$n, catalog_name:$c}')"

# --- 4. persona privilege matrix on the demo catalog/schema -----------------
# SELECT/MODIFY granted at the schema level inherit down to its tables.
echo "== applying persona privilege matrix on $DEMO_CATALOG.$DEMO_SCHEMA =="
# scott — author
grant_priv catalog "$DEMO_CATALOG"                 "scott@uc-demos.dev" "USE CATALOG"
grant_priv schema  "$DEMO_CATALOG.$DEMO_SCHEMA"     "scott@uc-demos.dev" "USE SCHEMA,CREATE TABLE,SELECT,MODIFY"
# jules — read-write
grant_priv catalog "$DEMO_CATALOG"                 "jules@uc-demos.dev" "USE CATALOG"
grant_priv schema  "$DEMO_CATALOG.$DEMO_SCHEMA"     "jules@uc-demos.dev" "USE SCHEMA,SELECT,MODIFY"
# lisa — read-only
grant_priv catalog "$DEMO_CATALOG"                 "lisa@uc-demos.dev"  "USE CATALOG"
grant_priv schema  "$DEMO_CATALOG.$DEMO_SCHEMA"     "lisa@uc-demos.dev"  "USE SCHEMA,SELECT"
# robert — intentionally no grants (the guide grants live to demo RBAC)

cat <<EOF

Bootstrap complete.

Personas (mint a token with:  just uc=local token-for <email>):
  power-user@uc-demos.dev  owns catalog '$DEMO_CATALOG' + schema '$DEMO_SCHEMA'; can create catalogs
  scott@uc-demos.dev       author     on $DEMO_CATALOG.$DEMO_SCHEMA (create tables, read, write)
  jules@uc-demos.dev       read-write on $DEMO_CATALOG.$DEMO_SCHEMA
  lisa@uc-demos.dev        read-only  on $DEMO_CATALOG.$DEMO_SCHEMA
  robert@uc-demos.dev      no grants  (expect 403 until you grant him access)

Admin (metastore OWNER) token:  just uc=local token
Next: see docs/uc/getting-started.md for the notebook + permissions walkthrough.
EOF
