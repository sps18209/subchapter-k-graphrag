# Deploying the Subchapter K GraphRAG service

A FastAPI service wrapping the definition-centric partnership-tax GraphRAG engine:
authority retrieval, the Layer-0 currency/supersession gate, and the deterministic
outside-basis calculator. It runs out of the box on the in-process SQLite build, and
reads from the production Postgres store the moment `DATABASE_URL` is set.

**Honest status.** With no `DATABASE_URL` the API builds and serves the in-process SQLite
graph at startup. Set `DATABASE_URL` (after `migrate_postgres.py` loads schema + seed) and
the same API reads from Postgres instead — the store swap is wired and verified
(`python/test_postgres_parity.py` asserts the two stores return identical results). Nothing
here is verified law — every `/ask` and `/compute` response carries
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

By default `DATABASE_URL` is commented out in `.env`, so the API boots on SQLite with no
further setup. The stack also starts a pgvector Postgres (`db`), not published to the host.

**To serve from Postgres instead:**

```bash
docker compose --profile tools run --rm migrate   # load schema.sql + seed into Postgres
# then uncomment DATABASE_URL in .env and restart the API:
docker compose up -d api
```

Order matters: migrate before the API reads from Postgres. If `DATABASE_URL` points at an
un-migrated database, the API fails fast at startup with a message telling you to run the
migration. Point `DATABASE_URL` at a managed provider (Supabase/Neon/RDS/Cloud SQL) by
changing the host — nothing else moves.

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

Swaps #1 (store) and #4 (serving) are **done**; #2 (hybrid retrieval) and #3 (gated
enrichment) are the remaining hooks.

1. **Store: SQLite → Postgres. ✅ Done.** `schema.sql` is the production DDL;
   `migrate_postgres.py` loads it plus the seed corpus into the database named by
   `DATABASE_URL`. Setting `DATABASE_URL` is now all it takes to make the API read from
   Postgres: `engine_adapter._connect` returns `graph.pg_connect(url)`, a thin wrapper that
   rewrites the SQLite-shaped queries (`?`→`%s`, `node`/`edge`→`tax_node`/`tax_edge`) and
   normalizes Postgres `DATE`/`TEXT[]` back to the engine's string types. Endpoints,
   serialization, retrieval logic, and the currency gate did not move — and
   `python/test_postgres_parity.py` proves both stores return identical results.
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
| `DATABASE_URL` | _(unset → SQLite)_ | Postgres URL. Set it and the API reads from Postgres; used by `migrate_postgres.py` too |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `subk` / `changeme` / `subk` | compose Postgres |
| `API_PORT` | `8000` | Host port the compose stack publishes |

---

## Provider portability

The code binds to nothing but a Postgres connection string. Moving between your own infra
and a managed provider (Supabase, PlanetScale, RDS, Cloud SQL) is a `DATABASE_URL` change
plus a run of `migrate_postgres.py`. Adopt a provider's proprietary surfaces (managed auth,
auto-generated APIs, row-level security tied to their identity) only deliberately — those
are the lock-in, not the database itself.
