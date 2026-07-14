"""Build a versioned FAISS index from knowledge/docs/*.md.

Chunking is heading-aware: each `## section` becomes one chunk carrying
{doc_id, section, version, effective_date} — this metadata is the provenance
that citations surface. Long sections are split at ~420 tokens with 50 overlap.

Output: knowledge/index/v<N>/{index.faiss, chunks.json, manifest.json}
Index versions are immutable; rollback = repoint (ADR-002).

Run: python knowledge/scripts/build_index.py [--version N]
"""

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import faiss
import numpy as np
from fastembed import TextEmbedding

ROOT = Path(__file__).resolve().parents[1]
# ONNX MiniLM via fastembed: identical model family, ~40MB runtime instead of
# torch's ~2GB — keeps the kb_query Lambda cold start in single-digit seconds.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MAX_TOKENS = 420  # ~ playbook's 300-500 window
OVERLAP = 50


def _approx_tokens(text: str) -> list[str]:
    return text.split()


def parse_doc(path: Path) -> tuple[dict[str, str], list[tuple[str, str]]]:
    raw = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n", raw, re.DOTALL)
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines() if ": " in line)
    body = raw[m.end() :]
    sections = re.split(r"\n## ", body)
    out = []
    for sec in sections[1:]:  # sections[0] is the H1 title block
        heading, _, text = sec.partition("\n")
        out.append((heading.strip(), text.strip()))
    return meta, out


def chunk_section(heading: str, text: str) -> list[str]:
    words = _approx_tokens(text)
    if len(words) <= MAX_TOKENS:
        return [f"{heading}\n{text}"]
    chunks, start = [], 0
    while start < len(words):
        window = words[start : start + MAX_TOKENS]
        chunks.append(f"{heading}\n{' '.join(window)}")
        start += MAX_TOKENS - OVERLAP
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, default=1)
    args = ap.parse_args()

    chunks: list[dict[str, str]] = []
    for path in sorted((ROOT / "docs").glob("*.md")):
        meta, sections = parse_doc(path)
        for heading, text in sections:
            for piece in chunk_section(heading, text):
                chunks.append(
                    {
                        "doc_id": meta["doc_id"],
                        "section": heading,
                        "version": meta["version"],
                        "effective_date": meta["effective_date"],
                        "text": piece,
                    }
                )

    model = TextEmbedding(MODEL_NAME)
    vecs = np.array(list(model.embed([c["text"] for c in chunks])), dtype="float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)

    out = ROOT / "index" / f"v{args.version}"
    out.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(out / "index.faiss"))
    (out / "chunks.json").write_text(json.dumps(chunks))
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "version": args.version,
                "model": MODEL_NAME,
                "chunks": len(chunks),
                "dim": int(vecs.shape[1]),
                "built_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
    )
    print(f"index v{args.version}: {len(chunks)} chunks, dim {vecs.shape[1]} -> {out}")


if __name__ == "__main__":
    main()
