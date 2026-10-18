# Project safeguards

- Scope: this repository only. Do not modify pharmacy, R1000, crypto or unrelated projects.
- Prefer reusing verified source code, scope changes in a feature branch and Draft PR; no merge without explicit approval.
- This is a **public** repository. Never commit API keys, raw RTMS XML/JSON, personal transaction records, proprietary licensed data, or private credentials.
- No recurring nationwide collection, backfill, automated real-estate recommendation, model promotion, or scheduled workflow without explicit approval.
- Fail closed on API errors, missing pages, changed schemas, inconsistent total counts, and unverified permissions. Missing is never the numeric value zero.
- Raw payload hashes, retrieved_at, reference period, source version, and audit receipts must be preserved in private durable storage before admission.
- Treat current 10-digit legal-dong codes and RTMS five-digit LAWD codes separately; track historical code changes and do not join by names alone.
- Document C/D claims and estimated values separately from authenticated A/B source facts. No price forecasts without out-of-time validation.
