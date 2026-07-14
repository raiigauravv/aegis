"""Extraction benchmark: labeled synthetic documents through the PRODUCTION path.

Generates invoices with known golden fields as born-digital PDFs and as rendered
PNG images (screenshot-like), drops them into the intake bucket, waits for the
deployed pipeline (intake_router -> extract_text -> enrich_nlp), then scores
field-level accuracy from the text that actually reached DynamoDB.

Columns produced: classical path (pdfplumber / Tesseract). The multimodal
Nova Lite column is PENDING BEDROCK (support case 178397104900264) and will be
added to the same harness when quota unlocks.

Writes evals/golden/extraction_results.json (consumed by run_eval.py) and
docs/extraction-benchmark.md.

Usage: AWS_PROFILE=aegis-dev python evals/run_extraction_bench.py [n_docs_per_type]
"""

import io
import json
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
BUCKET = "aegis-dev-intake-490004650850"
TABLE = "aegis-dev-tickets"


def golden_fields(i: int) -> dict[str, str]:
    return {
        "invoice_no": f"NS-{4000 + i}",
        "amount": f"{100 + i * 7}.{i % 9}0 CAD",
        "customer": f"CUST-{7100 + i}",
        "due_date": f"2026-08-{(i % 27) + 1:02d}",
    }


def doc_text(f: dict[str, str]) -> list[str]:
    return [
        "NORTHSTAR BANK - INVOICE",
        f"Invoice number: {f['invoice_no']}",
        f"Customer reference: {f['customer']}",
        f"Amount due: {f['amount']}",
        f"Due date: {f['due_date']}",
        "Questions? Contact support through the NorthStar app.",
    ]


def make_pdf(lines: list[str]) -> bytes:
    stream_parts = ["BT /F1 12 Tf 40 760 Td 16 TL"]
    for line in lines:
        safe = line.replace("(", r"\(").replace(")", r"\)")
        stream_parts.append(f"({safe}) Tj T*")
    stream_parts.append("ET")
    stream = " ".join(stream_parts).encode()
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
    start = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for x in xref:
        out += f"{x:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size "
        + str(len(objs) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(start).encode()
        + b"\n%%EOF"
    )
    return out


def make_png(lines: list[str]) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 400), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except OSError:
        font = ImageFont.load_default()
    y = 30
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 44
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    s3 = boto3.client("s3")
    dynamo = boto3.resource("dynamodb").Table(TABLE)

    run_id = datetime.now(UTC).strftime("%H%M%S")
    uploads: dict[str, dict] = {}  # key -> {"golden":..., "kind":...}
    for i in range(n):
        fields = golden_fields(i)
        lines = doc_text(fields)
        pdf_key = f"bench/{run_id}/invoice-{i}.pdf"
        png_key = f"bench/{run_id}/invoice-{i}.png"
        s3.put_object(Bucket=BUCKET, Key=pdf_key, Body=make_pdf(lines))
        s3.put_object(Bucket=BUCKET, Key=png_key, Body=make_png(lines))
        uploads[pdf_key] = {"golden": fields, "kind": "pdf"}
        uploads[png_key] = {"golden": fields, "kind": "image"}
    print(f"uploaded {len(uploads)} documents, waiting for pipeline...")

    deadline = time.time() + 600
    results: dict[str, dict] = {}
    while time.time() < deadline and len(results) < len(uploads):
        time.sleep(15)
        scan = dynamo.scan(
            FilterExpression="SK = :m AND contains(#src.#k, :run)",
            ExpressionAttributeNames={"#src": "source", "#k": "key"},
            ExpressionAttributeValues={":m": "META", ":run": f"bench/{run_id}/"},
        )
        for item in scan["Items"]:
            key = item["source"]["key"]
            if key in results or item["status"] not in ("enriched", "awaiting_approval"):
                continue
            trace = dynamo.query(
                KeyConditionExpression="PK = :pk",
                ExpressionAttributeValues={":pk": item["PK"]},
            )["Items"]
            extract = next((t for t in trace if t.get("step") == "extract"), {})
            results[key] = {
                "text": item.get("text", ""),
                "method": (extract.get("detail") or {}).get("method", "?"),
                "latency_ms": float(extract.get("latency_ms", 0)),
            }
        print(f"  {len(results)}/{len(uploads)} done")

    by_kind: dict[str, dict[str, list[float]]] = {}
    for key, meta in uploads.items():
        r = results.get(key)
        if r is None:
            continue
        text = norm(r["text"])
        hits = sum(1 for v in meta["golden"].values() if norm(v) in text)
        bucket = by_kind.setdefault(meta["kind"], {"acc": [], "lat": [], "methods": []})
        bucket["acc"].append(hits / len(meta["golden"]))
        bucket["lat"].append(r["latency_ms"])
        bucket["methods"].append(r["method"])

    summary = {
        "run_id": run_id,
        "docs_per_type": n,
        "completed": len(results),
        "types": {},
    }
    for kind, data in by_kind.items():
        summary["types"][kind] = {
            "field_accuracy": round(statistics.mean(data["acc"]), 4),
            "median_latency_ms": round(statistics.median(data["lat"]), 1),
            "method": max(set(data["methods"]), key=data["methods"].count),
            "n": len(data["acc"]),
        }
    out = ROOT / "evals" / "golden" / "extraction_results.json"
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))

    md = [
        "# Extraction benchmark (classical path, production pipeline)",
        "",
        f"Run `{run_id}` — {n} docs/type through the LIVE intake → extract_text → enrich flow.",
        "Field accuracy = share of golden fields (invoice no, amount, customer, due date)",
        "present in the text persisted to DynamoDB.",
        "",
        "| Input | Method | Field accuracy | Median latency | Cost/1K docs |",
        "|---|---|---|---|---|",
    ]
    for kind, s in summary["types"].items():
        md.append(
            f"| {kind} | {s['method']} | {s['field_accuracy']:.2%} | "
            f"{s['median_latency_ms'] / 1000:.1f}s | ~$0 (OSS in Lambda) |"
        )
    md += [
        "| any (multimodal Nova Lite) | **pending Bedrock quota** | — | — | — |",
        "",
        "The multimodal column and the data-derived routing rule land when support case",
        "178397104900264 unlocks Bedrock on-demand quota.",
    ]
    (ROOT / "docs" / "extraction-benchmark.md").write_text("\n".join(md) + "\n")
    print("wrote docs/extraction-benchmark.md")


if __name__ == "__main__":
    main()
