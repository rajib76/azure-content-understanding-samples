#!/usr/bin/env bash
# Diagnose a Databricks 401: is the credential bad, or is the endpoint unavailable?
#
#   export DATABRICKS_HOST='https://dbc-xxxxxxxx-xxxx.cloud.databricks.com'
#   export DATABRICKS_TOKEN='<token>'
#   bash databricks_check_auth.sh

HOST="${DATABRICKS_HOST:?Set it first:  export DATABRICKS_HOST='https://dbc-xxxxxxxx-xxxx.cloud.databricks.com'}"

if [ -z "${DATABRICKS_TOKEN:-}" ]; then
  echo "DATABRICKS_TOKEN is NOT set in this shell."
  echo "  export DATABRICKS_TOKEN='<token>'    # then re-run"
  exit 1
fi

# Shape only - never print the token itself.
echo "token length : ${#DATABRICKS_TOKEN}"
echo "token prefix : ${DATABRICKS_TOKEN:0:4}...   (a Databricks PAT starts with 'dapi')"
case "$DATABRICKS_TOKEN" in
  dapi*) echo "             looks like a PAT" ;;
  ey*)   echo "             looks like a JWT / OAuth access token" ;;
  *)     echo "             NOT a recognised Databricks token format" ;;
esac
echo

# Simplest authenticated endpoint: who am I? Available on every workspace.
echo "--- GET /api/2.0/preview/scim/v2/Me ---"
code=$(curl -sS -o /tmp/dbx_me.json -w "%{http_code}" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  "${HOST}/api/2.0/preview/scim/v2/Me")
echo "HTTP $code"
head -c 400 /tmp/dbx_me.json; echo; echo

if [ "$code" = "200" ]; then
  echo "Credential is VALID. A 401 from ai-extract would then mean that"
  echo "endpoint rejects this credential type, not that the token is wrong."
else
  echo "Credential is rejected by a basic endpoint too, so the problem is the"
  echo "token itself - not the ai-extract endpoint."
fi
rm -f /tmp/dbx_me.json
