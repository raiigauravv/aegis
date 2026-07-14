"""MCP-style tool server for AEGIS agents (JSON-RPC 2.0 over POST /mcp).

Methods: tools/list, tools/call — the shapes agents speak. Every call carries
the calling agent's identity in params.agent; the YAML allowlist is enforced
HERE, server-side: a drafting agent asking for check_customer_context gets a
JSON-RPC error AND a security event in the trace log. Patterns reused from the
OpenHive MCP PRs #6963/#6818.

Tools:
  search_knowledge_base(query, k)   -> kb_query Lambda (grounded, cited chunks)
  get_ticket_history(ticket_id)     -> trace + feedback from DynamoDB
  extract_entities(text)            -> Presidio-lite regex entities (deterministic)
  check_customer_context(customer)  -> mock CRM (fixture data)
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import boto3
import yaml
from aegis_core import store
from aegis_core.models import TraceEvent
from aegis_core.tracing import get_logger

logger = get_logger("mcp_tools")
_lambda = None

_MOCK_CRM = {
    "CUST-7100": {"segment": "premium", "tenure_years": 6, "open_tickets": 1, "churn_risk": "low"},
    "CUST-7101": {"segment": "everyday", "tenure_years": 2, "open_tickets": 3, "churn_risk": "high"},
}


def _allowlists() -> dict[str, list[str]]:
    raw = yaml.safe_load((Path(__file__).parent / "allowlists.yaml").read_text())
    out: dict[str, list[str]] = {}
    for agent, tools in raw["agents"].items():
        flat: list[str] = []
        for t in tools or []:
            if isinstance(t, str):
                flat.append(t)
        out[agent] = flat
    return out


def tool_search_knowledge_base(args: dict[str, Any]) -> dict[str, Any]:
    global _lambda
    if _lambda is None:
        _lambda = boto3.client("lambda")
    resp = _lambda.invoke(
        FunctionName=os.environ["KB_QUERY_FUNCTION"],
        Payload=json.dumps({"q": args["query"], "k": int(args.get("k", 5))}).encode(),
    )
    result: dict[str, Any] = json.loads(resp["Payload"].read())
    return result


def tool_get_ticket_history(args: dict[str, Any]) -> dict[str, Any]:
    ticket = store.get_ticket(args["ticket_id"])
    if ticket is None:
        return {"error": "not found"}
    return {"trace": ticket["trace"], "feedback": ticket["feedback"]}


_ENTITY_PATTERNS = {
    "error_code": r"\b(?:NS|P)-\d{3}\b",
    "incident_id": r"\bINC-\d{6}\b",
    "invoice_no": r"\bNS-\d{4}\b",
    "customer_ref": r"\bCUST-\d{4}\b",
    "amount": r"\$?\d{1,3}(?:,\d{3})*\.\d{2}\b",
}


def tool_extract_entities(args: dict[str, Any]) -> dict[str, Any]:
    text = args["text"]
    return {
        "entities": {
            name: sorted(set(re.findall(pattern, text)))
            for name, pattern in _ENTITY_PATTERNS.items()
            if re.search(pattern, text)
        }
    }


def tool_check_customer_context(args: dict[str, Any]) -> dict[str, Any]:
    return {"customer": _MOCK_CRM.get(args["customer_ref"], {"segment": "unknown"})}


TOOLS: dict[str, Any] = {
    "search_knowledge_base": tool_search_knowledge_base,
    "get_ticket_history": tool_get_ticket_history,
    "extract_entities": tool_extract_entities,
    "check_customer_context": tool_check_customer_context,
}


def _rpc_error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def handle_rpc(req: dict[str, Any]) -> dict[str, Any]:
    rpc_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}
    agent = str(params.get("agent", ""))

    if method == "tools/list":
        allowed = _allowlists().get(agent, [])
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": [{"name": t} for t in TOOLS if t in allowed]},
        }
    if method != "tools/call":
        return _rpc_error(rpc_id, -32601, f"method not found: {method}")

    tool = str(params.get("name", ""))
    if tool not in TOOLS:
        return _rpc_error(rpc_id, -32602, f"unknown tool: {tool}")

    allowed = _allowlists().get(agent, [])
    if tool not in allowed:
        # SECURITY EVENT: allowlist violation is logged with full attribution.
        ticket_id = str((params.get("arguments") or {}).get("ticket_id", "n/a"))
        logger.error(
            "tool allowlist violation",
            extra={
                "ticket_id": ticket_id,
                "step": "allowlist_denial",
                "detail": {"agent": agent, "tool": tool},
            },
        )
        if ticket_id != "n/a":
            store.append_trace(
                TraceEvent(
                    ticket_id=ticket_id,
                    service="mcp_tools",
                    step="allowlist_denial",
                    detail={"agent": agent, "tool": tool, "severity": "security"},
                )
            )
        return _rpc_error(rpc_id, -32001, f"agent '{agent}' is not allowed to call '{tool}'")

    start = time.perf_counter()
    result = TOOLS[tool](params.get("arguments") or {})
    logger.info(
        f"tool {tool} ok",
        extra={
            "step": "tool_call",
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "detail": {"agent": agent, "tool": tool},
        },
    )
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if "routeKey" in event:  # API Gateway
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64

            body = base64.b64decode(body).decode()
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            return {"statusCode": 400, "body": json.dumps(_rpc_error(None, -32700, "parse error"))}
        resp = handle_rpc(req)
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(resp),
        }
    return handle_rpc(event)  # direct invoke
