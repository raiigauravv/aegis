"""AEGIS evaluation harness.

Currently implemented suites (all local, deterministic, reproducible):
  retrieval  — hit@3 and MRR of the FAISS index against the golden question set
  redaction  — PII detection precision/recall on the crafted suite (Phase 4)
  extraction — OCR field accuracy on the labeled benchmark (Phase 3)

Pending Bedrock quota (documented, not faked): groundedness LLM-judge,
fabrication canaries, end-to-end Q->cited-answer suite.

Exit code is non-zero if any suite falls below evals/thresholds.yaml — this is
what lets CI block a deploy (Phase 9).

Run: python evals/run_eval.py [suite ...]
"""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def eval_retrieval() -> dict[str, float]:
    import faiss
    import numpy as np
    from fastembed import TextEmbedding

    idx_dir = sorted((ROOT / "knowledge" / "index").glob("v*"))[-1]
    index = faiss.read_index(str(idx_dir / "index.faiss"))
    chunks = json.loads((idx_dir / "chunks.json").read_text())
    golden = [
        json.loads(line)
        for line in (ROOT / "knowledge" / "golden" / "retrieval.jsonl").read_text().splitlines()
    ]
    model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    qvecs = np.array(list(model.embed([g["question"] for g in golden])), dtype="float32")
    qvecs /= np.linalg.norm(qvecs, axis=1, keepdims=True)
    _, ids = index.search(qvecs, 10)

    hits3, rr = 0, 0.0
    for g, row in zip(golden, ids, strict=True):
        ranked_docs = []
        for i in row:  # dedupe chunk hits to doc ranking
            d = chunks[i]["doc_id"]
            if d not in ranked_docs:
                ranked_docs.append(d)
        if g["expected_doc_id"] in ranked_docs[:3]:
            hits3 += 1
        if g["expected_doc_id"] in ranked_docs:
            rr += 1 / (ranked_docs.index(g["expected_doc_id"]) + 1)
    n = len(golden)
    return {"n": n, "hit_at_3": round(hits3 / n, 4), "mrr": round(rr / n, 4)}


def eval_redaction() -> dict[str, float]:
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "services" / "enrich_nlp"))
    from redactor import detect  # noqa: PLC0415

    sys.path.insert(0, str(ROOT / "evals" / "golden"))
    from redaction import CASES  # noqa: PLC0415

    tp = fp = fn = 0
    for text, labeled in CASES:
        expected = set()
        for etype, substr in labeled:
            start = text.index(substr)
            expected.add((etype, start, start + len(substr)))
        got = {(r.entity_type, r.start, r.end) for r in detect(text)}

        def _match(a: tuple, b: tuple) -> bool:  # type + span overlap
            return a[0] == b[0] and a[1] < b[2] and a[2] > b[1]

        for e in expected:
            if any(_match(e, g) for g in got):
                tp += 1
            else:
                fn += 1
        for g in got:
            if not any(_match(e, g) for e in expected):
                fp += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "cases": len(CASES),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }


def eval_extraction() -> dict[str, float]:
    """Reads the latest run_extraction_bench.py results (bench needs live infra,
    so it runs on demand/nightly, not per-PR)."""
    results = json.loads((ROOT / "evals" / "golden" / "extraction_results.json").read_text())
    types = results["types"]
    return {
        "field_accuracy_pdf": types.get("pdf", {}).get("field_accuracy", 0.0),
        "field_accuracy_ocr": types.get("image", {}).get("field_accuracy", 0.0),
        "completed": results["completed"],
    }


def eval_adversarial() -> dict[str, float]:
    """Reads the latest run_adversarial.py results (needs live infra; on-demand/nightly)."""
    results = json.loads((ROOT / "evals" / "golden" / "adversarial_results.json").read_text())
    return {
        "total": results["total"],
        "blocked_rate": round(results["blocked"] / results["total"], 4),
    }


SUITES = {
    "retrieval": eval_retrieval,
    "redaction": eval_redaction,
    "extraction": eval_extraction,
    "adversarial": eval_adversarial,
}


def main() -> None:
    wanted = sys.argv[1:] or list(SUITES)
    thresholds = yaml.safe_load((ROOT / "evals" / "thresholds.yaml").read_text())
    failures = []
    scorecard = {}
    for name in wanted:
        if name not in SUITES:
            print(f"suite '{name}' not implemented yet, skipping")
            continue
        result = SUITES[name]()
        scorecard[name] = result
        for metric, floor in thresholds.get(name, {}).items():
            got = result.get(metric)
            ok = got is not None and got >= floor
            print(f"{name}.{metric}: {got} (floor {floor}) {'PASS' if ok else 'FAIL'}")
            if not ok:
                failures.append(f"{name}.{metric}")
    print("\nscorecard:", json.dumps(scorecard, indent=2))
    if len(wanted) == len(SUITES):  # full run -> persist for the frontend/README
        from datetime import UTC, datetime

        scorecard["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        (ROOT / "evals" / "scorecard.json").write_text(json.dumps(scorecard, indent=2))
    if failures:
        print(f"\nEVAL GATE FAILED: {failures}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
