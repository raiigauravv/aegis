from typing import Any

from .handler import handle_rpc


def _call(agent: str, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"agent": agent, "name": tool, "arguments": arguments or {}},
        }
    )


def test_drafting_agent_cannot_reach_crm() -> None:
    resp = _call("drafting_agent", "check_customer_context", {"customer_ref": "CUST-7100"})
    assert resp["error"]["code"] == -32001
    assert "not allowed" in resp["error"]["message"]


def test_research_agent_can_extract_entities() -> None:
    resp = _call(
        "research_agent",
        "extract_entities",
        {"text": "error NS-403 on invoice NS-4007, charged $145.50 ref CUST-7101"},
    )
    entities = resp["result"]["entities"]
    assert entities["error_code"] == ["NS-403"]
    assert entities["invoice_no"] == ["NS-4007"]
    assert entities["customer_ref"] == ["CUST-7101"]
    assert "145.50" in entities["amount"][0]


def test_tools_list_is_filtered_per_agent() -> None:
    resp = handle_rpc(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"agent": "triage_agent"}}
    )
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["extract_entities"]


def test_unknown_agent_gets_nothing() -> None:
    resp = _call("evil_agent", "search_knowledge_base", {"query": "x"})
    assert resp["error"]["code"] == -32001


def test_unknown_tool_and_method() -> None:
    assert _call("research_agent", "drop_tables")["error"]["code"] == -32602
    resp = handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "bogus", "params": {}})
    assert resp["error"]["code"] == -32601
