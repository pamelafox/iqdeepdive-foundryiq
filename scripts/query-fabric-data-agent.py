"""Query the configured Fabric Data Agent through its MCP endpoint."""

import argparse
import asyncio
import os
from pathlib import Path

import httpx
from azure.identity import AzureDeveloperCliCredential
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

REPO_ROOT = Path(__file__).parents[1]
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

load_dotenv(REPO_ROOT / ".env", override=True)


async def query_data_agent(mcp_url: str, tenant_id: str, question: str) -> str:
    """Authenticate, discover, and call the Fabric Data Agent's MCP tool."""
    credential = AzureDeveloperCliCredential(tenant_id=tenant_id)
    try:
        token = credential.get_token(FABRIC_SCOPE)
    finally:
        credential.close()

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token.token}"},
        follow_redirects=True,
        timeout=httpx.Timeout(30, read=300),
    ) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                if not tools.tools:
                    raise RuntimeError("The Fabric data agent exposed no MCP tools.")

                tool = tools.tools[0]
                properties = tool.inputSchema.get("properties", {})
                if not properties:
                    raise RuntimeError(f"MCP tool '{tool.name}' has no input properties.")

                question_argument = next(iter(properties))
                result = await session.call_tool(
                    tool.name,
                    {question_argument: question},
                )
                answers = [block.text for block in result.content if block.type == "text"]
                return "\n".join(answers)


def parse_args() -> argparse.Namespace:
    """Parse the question and optional endpoint override."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="Question to ask the Fabric data agent")
    parser.add_argument(
        "--mcp-url",
        default=os.getenv("FABRIC_DATA_AGENT_MCP_URL"),
        help="Fabric Data Agent MCP URL (defaults to FABRIC_DATA_AGENT_MCP_URL)",
    )
    return parser.parse_args()


def main() -> None:
    """Authenticate, query the configured data agent, and print its answer."""
    args = parse_args()
    if not args.mcp_url:
        raise RuntimeError(
            "FABRIC_DATA_AGENT_MCP_URL is required unless --mcp-url is provided."
        )

    tenant_id = os.environ["FABRIC_TENANT_ID"]
    answer = asyncio.run(query_data_agent(args.mcp_url, tenant_id, args.question))
    print(answer)


if __name__ == "__main__":
    main()