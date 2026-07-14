# Extraction benchmark (classical path, production pipeline)

Run `045319` — 10 docs/type through the LIVE intake → extract_text → enrich flow.
Field accuracy = share of golden fields (invoice no, amount, customer, due date)
present in the text persisted to DynamoDB.

| Input | Method | Field accuracy | Median latency | Cost/1K docs |
|---|---|---|---|---|
| pdf | pdf_text | 100.00% | 0.1s | ~$0 (OSS in Lambda) |
| image | ocr | 100.00% | 1.1s | ~$0 (OSS in Lambda) |
| any (multimodal Nova Lite) | **pending Bedrock quota** | — | — | — |

The multimodal column and the data-derived routing rule land when support case
178397104900264 unlocks Bedrock on-demand quota.
