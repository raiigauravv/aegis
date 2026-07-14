"""Grounded retrieval over the versioned FAISS index.

Invoked two ways:
  - API Gateway: GET /kb/search?q=...&k=5 (demo/debug surface)
  - direct invoke {"q": "...", "k": 5} (the MCP search_knowledge_base tool, Phase 6/7)

Cold start loads the pinned index version from S3 and the MiniLM model baked
into the container image. Results below SCORE_THRESHOLD are dropped; an empty
result set returns insufficient_knowledge=true — the caller must NOT draft an
answer from nothing (fabrication defense #1).
"""

import json
import os
import time
from pathlib import Path
from typing import Any

import boto3
import faiss
import numpy as np
from aegis_core.tracing import get_logger
from fastembed import TextEmbedding

logger = get_logger("kb_query")

INDEX_PREFIX = os.environ.get("INDEX_PREFIX", "index/v1")
SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "0.35"))

_state: dict[str, Any] = {}


def _load() -> None:
    if _state:
        return
    t0 = time.perf_counter()
    bucket = os.environ["INDEX_BUCKET"]
    s3 = boto3.client("s3")
    local = Path("/tmp/index")
    local.mkdir(parents=True, exist_ok=True)
    for name in ("index.faiss", "chunks.json", "manifest.json"):
        s3.download_file(bucket, f"{INDEX_PREFIX}/{name}", str(local / name))
    _state["index"] = faiss.read_index(str(local / "index.faiss"))
    _state["chunks"] = json.loads((local / "chunks.json").read_text())
    _state["manifest"] = json.loads((local / "manifest.json").read_text())
    _state["model"] = TextEmbedding(
        "sentence-transformers/all-MiniLM-L6-v2",
        cache_dir=os.environ.get("MODEL_DIR", "/opt/model"),
        local_files_only=True,
    )
    logger.info(
        "index loaded",
        extra={
            "step": "load_index",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "detail": {"version": str(_state["manifest"]["version"]), "chunks": str(len(_state["chunks"]))},
        },
    )


def search(q: str, k: int = 5) -> dict[str, Any]:
    _load()
    t0 = time.perf_counter()
    qvec = np.array(list(_state["model"].embed([q])), dtype="float32")
    qvec /= np.linalg.norm(qvec, axis=1, keepdims=True)
    scores, ids = _state["index"].search(qvec, k)
    results = []
    for score, i in zip(scores[0], ids[0], strict=True):
        if i < 0 or score < SCORE_THRESHOLD:
            continue
        c = _state["chunks"][i]
        results.append(
            {
                "doc_id": c["doc_id"],
                "section": c["section"],
                "version": c["version"],
                "effective_date": c["effective_date"],
                "score": round(float(score), 4),
                "text": c["text"],
            }
        )
    latency = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "search",
        extra={"step": "search", "latency_ms": latency, "detail": {"q": q[:80], "hits": str(len(results))}},
    )
    return {
        "query": q,
        "index_version": _state["manifest"]["version"],
        "insufficient_knowledge": len(results) == 0,
        "results": results,
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if "routeKey" in event:  # API Gateway
        params = event.get("queryStringParameters") or {}
        q = (params.get("q") or "").strip()
        if not q:
            return {"statusCode": 400, "body": json.dumps({"error": "missing q parameter"})}
        k = min(int(params.get("k", 5)), 10)
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(search(q, k)),
        }
    return search(event["q"], min(int(event.get("k", 5)), 10))  # direct invoke
