#!/bin/sh
set -eu

echo "Assigning Search access to the hosted agent identity..."

if [ -z "${AZURE_AI_SEARCH_SERVICE_NAME:-}" ] || [ -z "${AZURE_SUBSCRIPTION_ID:-}" ] || [ -z "${AZURE_RESOURCE_GROUP:-}" ]; then
    echo "Search service or subscription information is not set. Skipping role assignment."
    exit 0
fi

SEARCH_SCOPE="/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP}/providers/Microsoft.Search/searchServices/${AZURE_AI_SEARCH_SERVICE_NAME}"
AGENT_PRINCIPAL_ID=$(azd ai agent show hr-agent --output json --no-prompt | python3 -c "import json, sys; print(json.load(sys.stdin)['instance_identity']['principal_id'])")

echo "Assigning Search Index Data Contributor to hr-agent (${AGENT_PRINCIPAL_ID})..."
az role assignment create \
    --assignee-object-id "$AGENT_PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "8ebe5a00-799e-43f5-93ac-243d3dce84a7" \
    --scope "$SEARCH_SCOPE" \
    --only-show-errors \
    --output none

echo "Postdeploy setup complete."