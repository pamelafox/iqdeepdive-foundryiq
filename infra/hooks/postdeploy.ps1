$ErrorActionPreference = "Stop"

Write-Host "Assigning Search access to the hosted agent identity..."

if (-not $env:AZURE_AI_SEARCH_SERVICE_NAME -or -not $env:AZURE_SUBSCRIPTION_ID -or -not $env:AZURE_RESOURCE_GROUP) {
    Write-Host "Search service or subscription information is not set. Skipping role assignment."
    exit 0
}

$searchScope = "/subscriptions/$($env:AZURE_SUBSCRIPTION_ID)/resourceGroups/$($env:AZURE_RESOURCE_GROUP)/providers/Microsoft.Search/searchServices/$($env:AZURE_AI_SEARCH_SERVICE_NAME)"
$agent = azd ai agent show hr-agent --output json --no-prompt | ConvertFrom-Json
$agentPrincipalId = $agent.instance_identity.principal_id

if (-not $agentPrincipalId) {
    throw "Could not retrieve the hosted identity for hr-agent."
}

Write-Host "Assigning Search Index Data Contributor to hr-agent ($agentPrincipalId)..."
az role assignment create `
    --assignee-object-id $agentPrincipalId `
    --assignee-principal-type ServicePrincipal `
    --role "8ebe5a00-799e-43f5-93ac-243d3dce84a7" `
    --scope $searchScope `
    --only-show-errors `
    --output none

if ($LASTEXITCODE -ne 0) {
    throw "Failed to assign Search Index Data Contributor to hr-agent."
}

Write-Host "Postdeploy setup complete."