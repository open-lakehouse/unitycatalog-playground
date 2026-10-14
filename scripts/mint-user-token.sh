#!/usr/bin/env bash
# mint-user-token.sh — mint an RS512 Unity Catalog bearer token for a user,
# WITHOUT an external identity provider.
#
# The bundled local UC (server.authorization=enable) accepts any JWT that is:
#   - signed with the server's internal RSA key (uc_conf/private_key.der),
#   - issued by "internal" with the matching key id (uc_conf/key_id.txt), and
#   - whose `sub` is the email of an ENABLED user in the UC database.
# That's exactly what UC's own AuthDecorator validates, so a locally-minted token
# is indistinguishable from one obtained via OIDC token-exchange. See
# docs/uc/getting-started.md for the walkthrough.
#
# The signing key + admin token live in the `uc_conf` Docker volume; this script
# reads them out of the running `unitycatalog` container.
#
# Usage:
#   scripts/mint-user-token.sh <email>
#   just uc=local token-for <email>
#
# Environment overrides:
#   UC_SERVER    UC base URL                       (default http://localhost:8080)
#   UC_CONTAINER unitycatalog container name        (default unitycatalog)
#   EXP_DAYS     token lifetime in days             (default 30)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_uc_lib.sh
source "$HERE/_uc_lib.sh"

EMAIL="${1:-}"
if [[ -z "$EMAIL" ]]; then
  echo "usage: $0 <email>   (e.g. $0 scott@uc-demos.dev)" >&2
  exit 2
fi
EXP_DAYS="${EXP_DAYS:-30}"

uc_require_tools jq openssl curl docker
uc_require_container

# Pull the signing material out of the container into a private temp dir.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
uc_cat_conf private_key.der > "$WORK/private_key.der"
KEY_ID="$(uc_cat_conf key_id.txt | tr -d '[:space:]')"
[[ -s "$WORK/private_key.der" ]] || { echo "ERROR: could not read private_key.der (is auth enabled?)" >&2; exit 1; }
[[ -n "$KEY_ID" ]] || { echo "ERROR: could not read key_id.txt (is auth enabled?)" >&2; exit 1; }

# Best-effort existence check so we can warn early (the token only authenticates
# for an ENABLED user). Non-fatal: bootstrap mints right after creating users.
ADMIN_TOKEN="$(uc_admin_token || true)"
if [[ -n "$ADMIN_TOKEN" ]]; then
  USERS_JSON="$(curl -fsS -m 15 -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$uc_control/scim2/Users" 2>/dev/null || true)"
  if [[ -n "$USERS_JSON" ]]; then
    FOUND="$(printf '%s' "$USERS_JSON" | jq -r --arg e "$EMAIL" '
      ([.Resources, .resources] | map(select(. != null)) | add // [])
      | map(select((((.emails // []) | map(.value | ascii_downcase)) | index($e | ascii_downcase))
        or ((.userName // "") | ascii_downcase) == ($e | ascii_downcase)))
      | (.[0].displayName // .[0].userName // "") ' 2>/dev/null || true)"
    if [[ -z "$FOUND" ]]; then
      echo "WARNING: no ENABLED user '$EMAIL' found in UC — token will not authenticate" >&2
      echo "         until the user exists. Run: just uc=local bootstrap-users" >&2
    fi
  fi
fi

IAT="$(date +%s)"
EXP=$(( IAT + EXP_DAYS * 24 * 3600 ))
JTI="$(uuidgen | tr 'A-Z' 'a-z')"

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

HEADER_JSON="$(jq -cn --arg kid "$KEY_ID" '{kid: $kid, alg: "RS512", typ: "JWT"}')"
PAYLOAD_JSON="$(jq -cn \
  --arg sub "$EMAIL" \
  --arg email "$EMAIL" \
  --argjson iat "$IAT" \
  --argjson exp "$EXP" \
  --arg jti "$JTI" \
  '{sub: $sub, email: $email, iss: "internal", iat: $iat, exp: $exp, jti: $jti, type: "ACCESS"}')"

SIGNING_INPUT="$(printf '%s' "$HEADER_JSON" | b64url).$(printf '%s' "$PAYLOAD_JSON" | b64url)"
SIGNATURE="$(printf '%s' "$SIGNING_INPUT" | openssl dgst -sha512 -sign "$WORK/private_key.der" -keyform DER | b64url)"
TOKEN="$SIGNING_INPUT.$SIGNATURE"

{
  echo "Minted token for <$EMAIL>"
  echo "  iss : internal"
  echo "  sub : $EMAIL"
  echo "  exp : $EXP ($EXP_DAYS days)"
  echo "  kid : $KEY_ID"
} >&2

printf '%s\n' "$TOKEN"
