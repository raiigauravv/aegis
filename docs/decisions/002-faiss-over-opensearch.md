# ADR-002: FAISS-in-Lambda over OpenSearch / Kendra / Pinecone

**Status:** Accepted · 2026-07-13

## Context

The knowledge base is ~40 documents ⇒ roughly 2K chunks. Embeddings are all-MiniLM-L6-v2 (384-dim
float32): 2,000 × 384 × 4 B ≈ 3 MB — trivially inside Lambda memory. OpenSearch Serverless has no free
tier and would dominate the entire cost model; managed vector stores add a network hop and an
operational dependency for zero retrieval-quality gain at this scale.

## Decision

FAISS index built offline (`make build-index`), serialized to S3 under `index/v<N>/`, loaded by the
query Lambda at cold start and cached across invocations. **Index versions are immutable** — the query
Lambda pins a version; rollback = repoint an environment variable. Rebuilds run weekly via EventBridge
or on KB change.

## Consequences

- $0 vector-store cost; retrieval latency is in-process (no network hop).
- Reproducibility: eval runs cite the exact index version, so hit@3/MRR numbers are replayable.
- Cold start pays the S3 fetch (~single-digit MB, negligible).

## Revisit when

- Index > ~200 MB or KB > ~100K chunks (memory pressure), or
- Updates must be visible in < minutes (rebuild cadence too slow), or
- Hybrid BM25+vector or fine-grained ACL filtering is required.

Then: OpenSearch Serverless, keeping the same `search_knowledge_base` MCP tool contract so agents
never notice the swap.
