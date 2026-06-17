# Deploying the Subchapter K GraphRAG service

A FastAPI service wrapping the definition-centric partnership-tax GraphRAG engine:
authority retrieval, the Layer-0 currency/supersession gate, and the deterministic
outside-basis calculator. It runs out of the box on the in-process SQLite build;
Postgres is the documented production store.

**Honest status.** The running API serves from the SQLite graph built at startup.
`migrate_postgres.py` provisions the Postgres store (schema + seed); pointing the API's
reads at Postgres is one small, documented change (see *The four production swaps*).
Nothing here is verified law — every `/ask` and `/compute` response carries
`verification_required: true` and a disclaimer. An attorney must verify before reliance.

---

## Run locally (no Docker, no Postgres)

```bash
cd deploy
pip install -r requirements.txt
python -m uvicorn app:app --reload      # http://127.0.0.1:8000/docs
python test_api.py                      # 30 checks across every endpoint
```

It runs **OPEN** (no auth) out of the box and logs a loud warning. Set keys before
exposing it anywhere:

```bash
export SUBK_API_KEYS="firm:$(openssl rand -hex 24)"
```

## Run in Docker

```bash
cp .env.example .env          # then edit the secrets
docker compose up --build     # API on http://localhost:8000
```

The stack also starts a pgvector Postgres (`db`), not published to the host. Load the
production schema + seed into it:

```bash
docker compose --profile tools run --rm migrate
```

---

## Endpoints

| Method | Path                | Auth | Purpose |
|--------|---------------------|------|---------|
| GET    | `/health`           | no   | Liveness, graph summary, auth mode |
| GET    | `/`                 | no   | Service metadata |
| POST   | `/ask`              | yes  | Authority neighborhood by tier + computed-term DAG + currency exclusions |
| POST   | `/compute`          | yes  | Deterministic outside-basis waterfall |
| GET    | `/verify?as_of=`    | yes  | Currency report as of a date |
| GET    | `/hubs`             | yes  | List term hubs |
| GET    | `/hubs/{hub_id}`    | yes  | Hub DAG + connected authority by relationship |
| GET    | `/node/{node_id}`   | yes  | Node + its edges |
| GET    | `/docs`             | no   | OpenAPI / Swagger UI |

Every response is `{"data": ..., "meta": {"request_id": ...}}`; errors are
`{"error": {"code", "message", "details"?}, "meta": ...}`. Legal-bearing responses add
`verification_required: true` and a `disclaimer`.

---

## The four production swaps (example → non-example)

This scaffold is swap #4 (serving), with the hooks for the rest.

1. **Store: SQLite → Postgres.** `schema.sql` is already the production DDL;
   `migrate_postgres.py` loads it plus the seed corpus into the database named by
   `DATABASE_URL`. To make the *API* read from Postgres: point `engine_adapter._connect`
   at a `psycopg` connection, switch the handful of `?` placeholders to `%s` in
   `graph.py` / `retrieve.py`, and the table names `node` / `edge` to `tax_node` /
   `tax_edge`. Endpoints, serialization, retrieval logic, and the currency gate do not move.
2. **Retrieval: BM25 → hybrid.** Add an embedding column (pgvector; the `ALTER` is noted
   at the bottom of `schema.sql`), store vectors, run dense kNN fused with the existing
   lexical channel, then a reranker. Graph expansion, the currency filter, and computation
   routing are unchanged.
3. **Enrichment hook → real but gated.** An LLM proposes expanded notes and candidate
   edges as `created_by='llm'`, unverified; an attorney promotes them before they become
   authoritative. The model never writes citable law unreviewed.
4. **Serving.** This service. Done.

---

## Before any non-internal use (the legal-product layer)

- **Auth** — replace the API-key stub (`auth.py`) with real identity (OIDC or signed
  JWTs), per-organization scoping, key rotation via your secrets manager, and
  per-principal rate limiting.
- **Citation verification** — gate outputs through your citation verifier
  (CourtListener / official sources). Never emit an unverified cite as good law.
- **Confidentiality (Rule 1.6)** — `/ask` and `/compute` inputs and audit rows can carry
  matter facts. Encrypt at rest and in transit, restrict access, set a retention policy,
  and use no-train / zero-data-retention settings on any LLM calls.
- **Audit** — replace the stdout hook (`audit.py`) with an append-only / immutable store
  (hash-chained log, WORM bucket, or append-only Postgres with row-level security). Treat
  rows as confidential.
- **Edge / transport** — terminate TLS and enforce rate limiting at the gateway or reverse
  proxy; lock `SUBK_CORS_ORIGINS` down to known origins.
- **Currency maintenance** — the gate is only as good as the corpus. Stand up the process
  to add new authority with validity intervals and supersession edges as the law changes,
  attorney-verified, on a cadence. This is the standing value of the system.

---

## Configuration (environment)

| Var | Default | Meaning |
|-----|---------|---------|
| `SUBK_API_KEYS` | _(unset → OPEN)_ | Comma-separated `label:key` or bare keys |
| `SUBK_CORS_ORIGINS` | `*` | Allowed browser origins, comma-separated |
| `SUBK_DB` | temp dir | Path of the SQLite build the API serves from |
| `DATABASE_URL` | _(unset)_ | Postgres URL for `migrate_postgres.py` (and the API once wired) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `subk` / `changeme` / `subk` | compose Postgres |
| `API_PORT` | `8000` | Host port the compose stack publishes |

---

## Provider portability

The code binds to nothing but a Postgres connection string. Moving between your own infra
and a managed provider (Supabase, PlanetScale, RDS, Cloud SQL) is a `DATABASE_URL` change
plus a run of `migrate_postgres.py`. Adopt a provider's proprietary surfaces (managed auth,
auto-generated APIs, row-level security tied to their identity) only deliberately — those
are the lock-in, not the database itself.
