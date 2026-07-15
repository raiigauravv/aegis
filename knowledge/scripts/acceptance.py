"""Full live acceptance sweep: every deployed endpoint + every pipeline path.

Prints a pass/fail matrix. Exit 0 only if every check passes.
Usage: AWS_PROFILE=aegis-dev python knowledge/scripts/acceptance.py <api-base>
"""

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

import boto3

BASE = sys.argv[1].rstrip("/")
ACCT = "490004650850"
INTAKE = f"aegis-dev-intake-{ACCT}"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append((name, bool(ok), note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def req(path: str, data=None, method=None, raw=False):
    url = f"{BASE}{path}"
    body = None
    if data is not None:
        body = data.encode() if raw else json.dumps(data).encode()
    r = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method=method or ("POST" if body else "GET"),
    )
    try:
        with urllib.request.urlopen(r, timeout=35) as resp:
            txt = resp.read()
            ctype = resp.headers.get("content-type", "")
            if "json" not in ctype:  # binary/text endpoints (e.g. PNG curve)
                return resp.status, {"bytes": len(txt)}
            return resp.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return e.code, {}


def wait_status(tid, targets, tries=45):
    for _ in range(tries):
        time.sleep(1.0)
        s, t = req(f"/tickets/{tid}")
        if s == 200 and t["meta"]["status"] in targets:
            return t
    return None


s3 = boto3.client("s3")
sqs = boto3.client("sqs")
cw = boto3.client("cloudwatch")
budgets = boto3.client("budgets")

print("\n=== 1. Core API + text pipeline ===")
s, r = req("/hello")
check("hello_world GET /hello", s == 200 and "alive" in json.dumps(r))

s, r = req(
    "/tickets",
    {
        "subject": "acc",
        "text": "I was double charged and I suspect fraud. "
        "My card 4111 1111 1111 1111, call 416-555-0134, email jane@example.com, postal M5V 2T6.",
    },
)
tid = r.get("ticket_id")
check("POST /tickets returns 202+id", s == 202 and bool(tid), tid or "")
t = wait_status(tid, {"awaiting_approval", "enriched"}) if tid else None
check("text ticket enriched", t is not None, t["meta"]["status"] if t else "timeout")
if t:
    m = t["meta"]
    check("PII redacted (4 entities)", m.get("pii_found") == 4, f"pii_found={m.get('pii_found')}")
    check("raw PII not persisted", "4111 1111" not in m["text"] and "416-555-0134" not in m["text"])
    check("language detected", m.get("language") == "en", str(m.get("language")))
    check("sentiment scored", m.get("sentiment") is not None, str(m.get("sentiment")))
    check("risk tier 3 (fraud kw)", m.get("risk_tier") == 3, f"tier={m.get('risk_tier')}")
    check("trace has ingest+enrich", {"intake_router", "enrich_nlp"} <= {e["service"] for e in t["trace"]})

print("\n=== 2. Document + voice pipelines (S3 drops) ===")
run = str(int(time.time()))


def make_pdf(text):
    stream = f"BT /F1 12 Tf 40 750 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    xref = []
    for i, o in enumerate(objs, 1):
        xref.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    st = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for x in xref:
        out += f"{x:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size "
        + str(len(objs) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(st).encode()
        + b"\n%%EOF"
    )
    return out


pdf_key = f"acc/{run}/doc.pdf"
s3.put_object(
    Bucket=INTAKE, Key=pdf_key, Body=make_pdf("INVOICE NS-9001 amount due 250.00 CAD ref CUST-7100")
)


def find_by_key(key, targets, tries=40):
    dyn = boto3.resource("dynamodb").Table("aegis-dev-tickets")
    for _ in range(tries):
        time.sleep(3)
        scan = dyn.scan(
            FilterExpression="SK = :m AND #s.#k = :key",
            ExpressionAttributeNames={"#s": "source", "#k": "key"},
            ExpressionAttributeValues={":m": "META", ":key": key},
        )
        if scan["Items"] and scan["Items"][0]["status"] in targets:
            return scan["Items"][0]
    return None


pdf_item = find_by_key(pdf_key, {"enriched", "awaiting_approval"})
check(
    "PDF drop -> extracted -> enriched",
    pdf_item is not None,
    f"NS-9001 found={'NS-9001' in (pdf_item.get('text', '') if pdf_item else '')}",
)

# voice via macOS say (best-effort; skip cleanly if tooling absent)
voice_ok_setup = shutil.which("say") and shutil.which("afconvert")
if voice_ok_setup:
    subprocess.run(
        ["say", "-o", "/tmp/acc.aiff", "I cannot log into my account since this morning"], check=False
    )
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "/tmp/acc.aiff", "/tmp/acc.wav"], check=False
    )
    voice_key = f"acc/{run}/voice.wav"
    s3.upload_file("/tmp/acc.wav", INTAKE, voice_key)
    voice_item = find_by_key(voice_key, {"enriched", "awaiting_approval"}, tries=60)
    check(
        "voice drop -> transcribed -> enriched",
        voice_item is not None,
        (voice_item.get("text", "")[:40] if voice_item else "timeout"),
    )
else:
    check("voice path (skipped: no say/afconvert)", True, "tooling unavailable")

print("\n=== 3. Knowledge base (RAG) ===")
s, r = req("/kb/search?q=what+are+the+etransfer+limits&k=3")
check(
    "KB grounded search",
    s == 200 and not r.get("insufficient_knowledge") and len(r.get("results", [])) > 0,
    r["results"][0]["doc_id"] if r.get("results") else "",
)
check(
    "KB citations carry provenance",
    bool(r.get("results")) and all({"doc_id", "section", "version", "score"} <= set(x) for x in r["results"]),
)
s, r = req("/kb/search?q=how+do+I+pilot+a+helicopter+to+the+moon&k=3")
check("KB refuses off-topic (fabrication defense)", s == 200 and r.get("insufficient_knowledge") is True)

print("\n=== 4. MCP tool server + allowlists ===")


def mcp(agent, name, args=None, method="tools/call"):
    return req(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {"agent": agent, "name": name, "arguments": args or {}},
        },
    )


s, r = mcp("research_agent", "search_knowledge_base", {"query": "card limits", "k": 2})
check("MCP allowed call (research->KB)", s == 200 and "result" in r)
s, r = mcp("drafting_agent", "check_customer_context", {"customer_ref": "CUST-7100", "ticket_id": tid})
check("MCP denies drafting->CRM", r.get("error", {}).get("code") == -32001)
s, r = mcp("triage_agent", None, method="tools/list")
check(
    "MCP tools/list filtered per agent",
    [x["name"] for x in r.get("result", {}).get("tools", [])] == ["extract_entities"],
)
s, r = mcp("research_agent", "drop_everything")
check("MCP unknown tool rejected", r.get("error", {}).get("code") == -32602)

print("\n=== 5. Moderation gate ===")
lam = boto3.client("lambda")


def moderate(draft):
    resp = lam.invoke(FunctionName="aegis-dev-moderation-gate", Payload=json.dumps({"draft": draft}).encode())
    return json.loads(resp["Payload"].read())


v = moderate("Your refund of $45 arrives within 5 business days. Call 416-555-0134. We guarantee it.")
check(
    "moderation blocks leaky/uncited/policy draft",
    v.get("pass") is False and len(v.get("reasons", [])) >= 3,
    f"{len(v.get('reasons', []))} reasons",
)
v = moderate("Your e-transfer limit is $10,000 per day [1]. Review pending transfers in the app [2].")
check("moderation passes clean cited draft", v.get("pass") is True)

print("\n=== 6. Bandit routing + learning ===")
if pdf_item:  # tier-1 ticket, eligible for bandit
    ptid = pdf_item["ticket_id"]
    s, r = req(f"/tickets/{ptid}/route", {})
    check(
        "bandit routes tier-1 ticket",
        s == 200
        and r.get("bandit") is True
        and r.get("arm") in ["fast_draft", "deep_research", "clarify_first", "escalate_human"],
        r.get("arm", ""),
    )
    s, r = req(f"/tickets/{ptid}/feedback", {"action": "approve"})
    check("feedback accepted (reward=1.0)", s == 200 and r.get("reward") == 1.0)
    lt = wait_status(ptid, {"approved"}, tries=15)
    learned = lt and any(e["service"] == "bandit_policy" and e["step"] == "learn" for e in lt["trace"])
    check("bandit learned from feedback", bool(learned))
if tid:  # tier-3 ticket from section 1
    s, r = req(f"/tickets/{tid}/route", {})
    check(
        "tier-3 bypasses bandit (governance)", r.get("arm") == "escalate_human" and r.get("bandit") is False
    )

print("\n=== 7. Governance surfaces ===")
s, r = req("/approvals")
check("approval queue lists tier-3", s == 200 and any(x["ticket_id"] == tid for x in r.get("tickets", [])))
s, r = req(f"/tickets/{tid}/audit")
check(
    "audit trail returns full chain",
    s == 200 and "pipeline_steps" in r and "human_actions" in r and "pii_note" in r,
)

print("\n=== 8. Observability + cost guards ===")
s, r = req("/scorecard")
check("scorecard endpoint live", s == 200 and "retrieval" in r)
s, _ = req("/bandit/curve")
check("bandit curve served", s == 200)
dlq = sqs.get_queue_attributes(
    QueueUrl=f"https://sqs.us-east-1.amazonaws.com/{ACCT}/aegis-dev-ingest-dlq",
    AttributeNames=["ApproximateNumberOfMessages"],
)
depth = int(dlq["Attributes"]["ApproximateNumberOfMessages"])
check("DLQ empty (no poison messages)", depth == 0, f"depth={depth}")
dash = cw.list_dashboards()["DashboardEntries"]
check(
    "CloudWatch dashboard exists",
    any("aegis" in d["DashboardName"].lower() for d in dash),
    ",".join(d["DashboardName"] for d in dash) or "none",
)
alarms = cw.describe_alarms(AlarmNamePrefix="aegis")["MetricAlarms"]
check("DLQ alarm configured", any("dlq" in a["AlarmName"].lower() for a in alarms))
buds = budgets.describe_budgets(AccountId=ACCT)["Budgets"]
check("budget alarms present ($5/$20)", sum(1 for b in buds if b["BudgetName"].startswith("aegis")) >= 2)

# cleanup bench artifacts
for key in (pdf_key,):
    s3.delete_object(Bucket=INTAKE, Key=key)

print("\n" + "=" * 50)
passed = sum(1 for _, ok, _ in results if ok)
print(f"RESULT: {passed}/{len(results)} checks passed")
if passed != len(results):
    print("FAILED:", [n for n, ok, _ in results if not ok])
    sys.exit(1)
