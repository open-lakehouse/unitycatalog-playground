#!/bin/sh
# Bootstraps the RustFS object store for the bundled local Unity Catalog (uc=local).
#
#   1. wait for the RustFS S3 API to answer
#   2. create the UC storage bucket if it does not exist
#   3. mint a short-lived STS credential (AssumeRole) from RustFS
#   4. render etc/conf into the shared `uc_conf` volume, injecting the bucket /
#      region into server.properties and appending the freshly-minted creds
#
# Why STS instead of the static root key: UC's v0.6 credential vendor
# (AwsCredentialVendor) only returns static credentials verbatim to Spark when a
# *session token* is present; otherwise it falls back to AWS STS AssumeRole,
# which cannot reach RustFS (the server has no custom-endpoint support yet, see
# unitycatalog PR #1636). RustFS — like MinIO — rejects a session token it did
# not issue, so the token must be a real RustFS STS token. We mint one here and
# hand it to UC, which echoes it to Spark. Spark reads/writes s3://<bucket>/…
# using the client-side endpoint configured in the notebooks.
#
# The STS credential expires (default 12h). Re-mint + reload it with:
#   just uc=local rotate-creds
set -eu

ENDPOINT="${RUSTFS_ENDPOINT:-http://rustfs:9000}"
BUCKET="${UC_STORAGE_BUCKET:-uc-warehouse}"
REGION="${S3_REGION:-us-east-1}"
DURATION="${STS_DURATION_SECONDS:-43200}"

# Sign S3/STS calls to RustFS with the long-term root key (required to call
# AssumeRole — temporary creds and service accounts cannot).
export AWS_ACCESS_KEY_ID="${RUSTFS_ACCESS_KEY:-rustfsadmin}"
export AWS_SECRET_ACCESS_KEY="${RUSTFS_SECRET_KEY:-rustfsadmin}"
export AWS_DEFAULT_REGION="$REGION"

log() { echo "[rustfs-init] $*"; }

log "waiting for RustFS at ${ENDPOINT} ..."
i=0
until aws --endpoint-url "$ENDPOINT" s3api list-buckets >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    log "ERROR: RustFS did not become ready in time" >&2
    exit 1
  fi
  sleep 2
done
log "RustFS is up."

if aws --endpoint-url "$ENDPOINT" s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  log "bucket s3://${BUCKET} already exists."
else
  log "creating bucket s3://${BUCKET} ..."
  aws --endpoint-url "$ENDPOINT" s3api create-bucket --bucket "$BUCKET" >/dev/null
fi

log "minting STS credentials (duration ${DURATION}s) ..."
creds="$(aws --endpoint-url "$ENDPOINT" sts assume-role \
  --role-arn "arn:aws:iam::000000000000:role/unity-catalog" \
  --role-session-name "unity-catalog-bootstrap" \
  --duration-seconds "$DURATION" \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
  --output text)"

ak="$(printf '%s\n' "$creds" | awk '{print $1}')"
sk="$(printf '%s\n' "$creds" | awk '{print $2}')"
st="$(printf '%s\n' "$creds" | awk '{print $3}')"

if [ -z "$ak" ] || [ -z "$sk" ] || [ -z "$st" ]; then
  log "ERROR: failed to obtain STS credentials from RustFS" >&2
  exit 1
fi

log "rendering UC config into /conf ..."
# Copy every shipped config file (hibernate + log4j2) as-is, then render
# server.properties. bucket/region are simple values so sed is safe; the
# base64-ish STS credentials are appended with printf (never passed through sed)
# so special characters can't break the substitution — Java Properties keeps the
# last definition of each key, so these override the blank lines in the template.
for f in /templates/*.properties; do
  bn="$(basename "$f")"
  [ "$bn" = "server.properties" ] && continue
  cp -f "$f" "/conf/$bn"
done

sed \
  -e "s|@S3_BUCKET@|${BUCKET}|g" \
  -e "s|@S3_REGION@|${REGION}|g" \
  /templates/server.properties > /conf/server.properties

{
  printf '\n# --- injected at runtime by etc/rustfs/bootstrap.sh (RustFS STS creds) ---\n'
  printf 's3.accessKey.0=%s\n' "$ak"
  printf 's3.secretKey.0=%s\n' "$sk"
  printf 's3.sessionToken.0=%s\n' "$st"
} >> /conf/server.properties

log "done. UC storage-root -> s3://${BUCKET} (creds valid for ~${DURATION}s)"
