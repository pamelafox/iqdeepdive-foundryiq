"""Create and publish a Fabric data agent backed by the Contoso ontology."""

import os
import time
from pathlib import Path

import httpx
from azure.identity import AzureDeveloperCliCredential
from dotenv import load_dotenv, set_key

REPO_ROOT = Path(__file__).parents[1]
ENV_PATH = REPO_ROOT / ".env"
FABRIC_API_URL = "https://api.fabric.microsoft.com"
FABRIC_SCOPE = f"{FABRIC_API_URL}/.default"
OPERATION_TIMEOUT_SECONDS = 300

load_dotenv(ENV_PATH, override=True)


def require_env(name: str) -> str:
    """Return a required environment variable or fail with a useful message."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required to create the Fabric data agent.")
    return value


def get_fabric_token(tenant_id: str) -> str:
    """Acquire a Fabric API token and close the credential immediately."""
    credential = AzureDeveloperCliCredential(tenant_id=tenant_id)
    try:
        return credential.get_token(FABRIC_SCOPE).token
    finally:
        credential.close()


def request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    expected_statuses: set[int],
    json: dict | None = None,
) -> httpx.Response:
    """Send a Fabric request and require one of the expected status codes."""
    response = client.request(method, url, json=json)
    if response.status_code not in expected_statuses:
        response.raise_for_status()
        raise RuntimeError(
            f"Unexpected Fabric API status {response.status_code} for {method} {url}."
        )
    return response


def wait_for_operation(
    client: httpx.Client,
    response: httpx.Response,
    *,
    ignored_error_codes: set[str] | None = None,
) -> None:
    """Wait for a Fabric long-running operation when the API returns 202."""
    if response.status_code != httpx.codes.ACCEPTED:
        return

    operation_url = response.headers.get("Location")
    if not operation_url:
        raise RuntimeError("Fabric returned 202 without an operation Location header.")

    deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        operation = request(
            client,
            "GET",
            operation_url,
            expected_statuses={httpx.codes.OK},
        )
        payload = operation.json()
        status = payload.get("status")
        if status == "Succeeded":
            return
        if status in {"Failed", "Cancelled"}:
            error_code = payload.get("error", {}).get("errorCode")
            if error_code in (ignored_error_codes or set()):
                return
            raise RuntimeError(f"Fabric operation {status.lower()}: {payload}")

        retry_after = float(operation.headers.get("Retry-After", "2"))
        time.sleep(min(max(retry_after, 1), 10))

    raise TimeoutError("Timed out waiting for the Fabric operation to complete.")


def list_data_agents(client: httpx.Client, workspace_id: str) -> list[dict]:
    """List data agents in the configured workspace."""
    response = request(
        client,
        "GET",
        f"/v1/workspaces/{workspace_id}/dataAgents",
        expected_statuses={httpx.codes.OK},
    )
    return response.json().get("value", [])


def get_or_create_data_agent(
    client: httpx.Client,
    name: str,
    workspace_id: str,
) -> dict:
    """Return an existing data agent by name or create it with the Fabric API."""
    for item in list_data_agents(client, workspace_id):
        if item.get("displayName") == name:
            print(f"Reusing Fabric data agent '{name}'.")
            return item

    response = request(
        client,
        "POST",
        f"/v1/workspaces/{workspace_id}/dataAgents",
        expected_statuses={httpx.codes.OK, httpx.codes.CREATED, httpx.codes.ACCEPTED},
        json={"artifactType": "LLMPlugin", "displayName": name},
    )
    wait_for_operation(client, response)

    for _ in range(30):
        for item in list_data_agents(client, workspace_id):
            if item.get("displayName") == name:
                return item
        time.sleep(2)

    raise RuntimeError(f"Fabric data agent '{name}' was created but could not be found.")


def main() -> None:
    """Create or update the ontology-backed data agent and publish its staging state."""
    tenant_id = require_env("FABRIC_TENANT_ID")
    workspace_id = require_env("FABRIC_WORKSPACE_ID")
    ontology_id = require_env("FABRIC_ONTOLOGY_ID")
    data_agent_name = os.getenv("FABRIC_DATA_AGENT_NAME", "ContosoDIYDataAgent")

    token = get_fabric_token(tenant_id)
    with httpx.Client(
        base_url=FABRIC_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    ) as client:
        print(f"Creating or reusing Fabric data agent '{data_agent_name}'...")
        data_agent = get_or_create_data_agent(client, data_agent_name, workspace_id)
        data_agent_id = data_agent["id"]
        base_url = f"/v1/workspaces/{workspace_id}/dataAgents/{data_agent_id}"
        settings_response = request(
            client,
            "PATCH",
            f"{base_url}/staging/settings",
            expected_statuses={httpx.codes.OK, httpx.codes.ACCEPTED},
            json={
                "aiInstructions": (
                    "Answer questions about Contoso DIY products, inventory, stores, "
                    "categories, and suppliers using the configured ontology."
                )
            },
        )
        wait_for_operation(client, settings_response)

        print(f"Adding ontology {ontology_id} as the data source...")
        datasource_response = request(
            client,
            "POST",
            f"{base_url}/staging/datasources",
            expected_statuses={
                httpx.codes.OK,
                httpx.codes.CREATED,
                httpx.codes.ACCEPTED,
                httpx.codes.CONFLICT,
            },
            json={
                "type": "FabricItem",
                "itemReference": {
                    "referenceType": "ById",
                    "itemId": ontology_id,
                    "workspaceId": workspace_id,
                },
            },
        )
        wait_for_operation(
            client,
            datasource_response,
            ignored_error_codes={"AlreadyAddedDataSource"},
        )

        print("Publishing the Fabric data agent...")
        publish_response = request(
            client,
            "POST",
            f"{base_url}/staging/publish",
            expected_statuses={httpx.codes.OK, httpx.codes.CREATED, httpx.codes.ACCEPTED},
            json={"publishedDescription": "Contoso DIY ontology data agent"},
        )
        wait_for_operation(client, publish_response)

    mcp_url = (
        f"https://api.fabric.microsoft.com/v1/mcp/workspaces/{workspace_id}"
        f"/dataagents/{data_agent_id}/agent"
    )
    values = {
        "FABRIC_DATA_AGENT_ID": data_agent_id,
        "FABRIC_DATA_AGENT_MCP_URL": mcp_url,
        "FABRIC_DATA_AGENT_NAME": data_agent_name,
    }
    ENV_PATH.touch()
    for key, value in values.items():
        set_key(ENV_PATH, key, value, quote_mode="never")

    print(f"Published Fabric data agent: {data_agent_id}")
    print(f"MCP endpoint: {mcp_url}")


if __name__ == "__main__":
    main()