#!/usr/bin/env python3
"""Automated MCP Client test script for Contract v2.3 Final.

Connects to `server.py` over stdio transport using the official MCP Python SDK,
lists the 6 canonical tools + health probe, and executes actual tool calls via JSON-RPC.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def run_mcp_tests():
    server_params = StdioServerParameters(
        command="python3",
        args=[str(PROJECT_ROOT / "server.py")],
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )

    print("==================================================")
    print("      Connecting to MCP Server via stdio...       ")
    print("==================================================\n")

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize MCP connection
            init_result = await session.initialize()
            print(f"Connected! Server: {init_result.serverInfo.name} | Protocol: {init_result.protocolVersion}\n")

            # 2. List all tools
            tools_response = await session.list_tools()
            tool_names = [t.name for t in tools_response.tools]
            print(f"Canonical Tools Registered ({len(tool_names)}):")
            for name in tool_names:
                print(f"  - {name}")
            print("\n--------------------------------------------------\n")

            # 3. Test Tool 1: get_ticket_details as Charlie (own ticket 101)
            print("[Test 1] Calling 'get_ticket_details' as Charlie (own ticket 101):")
            res1 = await session.call_tool(
                "get_ticket_details",
                arguments={"ticket_id": 101, "user_context": "charlie"}
            )
            print(res1.content[0].text if res1.content else "No content")
            print("\n--------------------------------------------------\n")

            # 4. Test Tool 2: Cross-Tenant Isolation (Dave Org B calling ticket 101 -> 404)
            print("[Test 2] Calling 'get_ticket_details' as Dave (Org B accessing Org A ticket):")
            res2 = await session.call_tool(
                "get_ticket_details",
                arguments={"ticket_id": 101, "user_context": "dave"}
            )
            print(res2.content[0].text if res2.content else "No content")
            print("\n--------------------------------------------------\n")

            # 5. Test Tool 5: Internal Notes RBAC (Charlie End_Customer adding note -> 403)
            print("[Test 3] Calling 'add_internal_note' as Charlie (End_Customer -> Expecting 403):")
            res3 = await session.call_tool(
                "add_internal_note",
                arguments={"ticket_id": 101, "note": "Customer trying to add note", "user_context": "charlie"}
            )
            print(res3.content[0].text if res3.content else "No content")
            print("\n--------------------------------------------------\n")

            # 6. Test Tool 6: Refund Defense-in-Depth (Alice Org_Admin with approval token)
            print("[Test 4] Calling 'issue_refund' as Alice with approval token ($150.00):")
            from utils.auth import generate_approval_token, ALICE_CONTEXT
            token = generate_approval_token("inv_org_a_001", 150.00, ALICE_CONTEXT["org_id"])
            res4 = await session.call_tool(
                "issue_refund",
                arguments={
                    "invoice_id": "inv_org_a_001",
                    "amount": 150.00,
                    "reason": "Customer overcharge resolution",
                    "idempotency_key": "idemp_mcp_client_final_1",
                    "approval_token": token,
                    "user_context": "alice",
                }
            )
            print(res4.content[0].text if res4.content else "No content")
            print("\n==================================================")
            print("        All MCP Server tests completed!           ")
            print("==================================================")


def main():
    asyncio.run(run_mcp_tests())


if __name__ == "__main__":
    main()
