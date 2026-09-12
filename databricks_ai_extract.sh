#!/usr/bin/env bash
# Databricks ai_extract — REST call
#
# Usage:
#   export DATABRICKS_HOST='https://dbc-xxxxxxxx-xxxx.cloud.databricks.com'
#   export DATABRICKS_TOKEN='<your token>'
#   bash ~/databricks_ai_extract.sh
#
# Do not paste the token into this file; keep it in the environment.

set -euo pipefail

HOST="${DATABRICKS_HOST:?Set it first:  export DATABRICKS_HOST='https://dbc-xxxxxxxx-xxxx.cloud.databricks.com'}"

: "${DATABRICKS_TOKEN:?Set it first:  export DATABRICKS_TOKEN='<your token>'}"

curl -sS -X POST "${HOST}/api/2.0/ai-functions/ai-extract" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
  "content": "Invoice #12345 from Acme Corp for $1,250.00 dated 2024-01-15",
  "schema": {
    "vendor_name": { "type": "string" },
    "total_amount": { "type": "number" }
  },
  "options": {
    "enable_confidence_scores": true,
    "enable_citations": true
  }
}'
echo
