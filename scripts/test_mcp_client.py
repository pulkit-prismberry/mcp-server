#!/usr/bin/env python3
"""Automated MCP Client test script for Contract v3.0 Locked + MCP-2.1 Auth Context Propagation.

Connects to `server.py` over stdio transport using the official MCP Python SDK,
verifies unauthenticated rejection (401), and injects Lean JWT session tokens via
MCP request `meta` (without passing raw tokens or user_context in LLM tool arguments).
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

from data.mock_identities import ALICE_CONTEXT, CHARLIE_CONTEXT, DAVE_CONTEXT
from utils.auth import generate_approval_token, generate_jwt


def _assert_code(raw_text: str, expected_success: bool, expected_code: str | None = None) -> None:
    payload = json.loads(raw_text)
    assert payload.get("success") is expected_success, f"Unexpected success in {payload}"
    if expected_code is not None:
        actual_code = (payload.get("error") or {}).get("code")
        assert actual_code == expected_code, f"Expected {expected_code}, got {actual_code} in {payload}"


async def run_mcp_tests():
    server_params = StdioServerParameters(
        command="python3",
        args=[str(PROJECT_ROOT / "server.py")],
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )

    charlie_jwt = generate_jwt(CHARLIE_CONTEXT, lean=True)
    dave_jwt = generate_jwt(DAVE_CONTEXT, lean=True)
    alice_jwt = generate_jwt(ALICE_CONTEXT, lean=True)

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

            # 3. Test 0: Missing auth context -> 401 UNAUTHORIZED
            print("[Test 0] Calling 'get_ticket_details' WITHOUT token (Expecting 401 UNAUTHORIZED):")
            res0 = await session.call_tool(
                "get_ticket_details",
                arguments={"ticket_id": 101},
            )
            txt0 = res0.content[0].text if res0.content else "{}"
            print(txt0)
            _assert_code(txt0, False, "UNAUTHORIZED")
            print("\n--------------------------------------------------\n")

            # 4. Test 1: Agent-injected Lean JWT in MCP meta (Charlie own ticket 101)
            print("[Test 1] Calling 'get_ticket_details' with Charlie Lean JWT in MCP meta (own ticket 101):")
            res1 = await session.call_tool(
                "get_ticket_details",
                arguments={"ticket_id": 101},
                meta={"authorization": f"Bearer {charlie_jwt}"},
            )
            txt1 = res1.content[0].text if res1.content else "{}"
            print(txt1)
            _assert_code(txt1, True)
            print("\n--------------------------------------------------\n")

            # 5. Test 2: Cross-Tenant Isolation (Dave Org B calling ticket 101 -> 404)
            print("[Test 2] Calling 'get_ticket_details' with Dave Lean JWT in MCP meta (Org B -> Org A 101):")
            res2 = await session.call_tool(
                "get_ticket_details",
                arguments={"ticket_id": 101},
                meta={"authorization": f"Bearer {dave_jwt}"},
            )
            txt2 = res2.content[0].text if res2.content else "{}"
            print(txt2)
            _assert_code(txt2, False, "NOT_FOUND")
            print("\n--------------------------------------------------\n")

            # 6. Test 3: Internal Notes RBAC (Charlie End_Customer adding note -> 403)
            print("[Test 3] Calling 'add_internal_note' with Charlie Lean JWT in MCP meta (Expecting 403):")
            res3 = await session.call_tool(
                "add_internal_note",
                arguments={"ticket_id": 101, "note": "Customer trying to add note"},
                meta={"authorization": f"Bearer {charlie_jwt}"},
            )
            txt3 = res3.content[0].text if res3.content else "{}"
            print(txt3)
            _assert_code(txt3, False, "FORBIDDEN")
            print("\n--------------------------------------------------\n")

            # 7. Test 4: Refund Defense-in-Depth (Alice Org_Admin via MCP meta + HITL approval token)
            print("[Test 4] Calling 'issue_refund' with Alice Lean JWT in MCP meta + approval token ($150.00):")
            approval_tok = generate_approval_token(
                "inv_org_a_001",
                150.00,
                ALICE_CONTEXT["org_id"],
                approver_id=ALICE_CONTEXT["user_id"],
            )
            res4 = await session.call_tool(
                "issue_refund",
                arguments={
                    "invoice_id": "inv_org_a_001",
                    "amount": 150.00,
                    "reason": "Customer overcharge resolution",
                    "idempotency_key": "idemp_mcp_client_final_1",
                    "approval_token": approval_tok,
                },
                meta={"authorization": f"Bearer {alice_jwt}"},
            )
            txt4 = res4.content[0].text if res4.content else "{}"
            print(txt4)
            _assert_code(txt4, True)
            print("\n==================================================")
            print("        All MCP Server tests completed!           ")
            print("==================================================")


def main():
    asyncio.run(run_mcp_tests())


if __name__ == "__main__":
    main()
