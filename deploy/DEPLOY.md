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

All four swaps are **done**. The remaining work is the legal-product layer below
(auth, audit store, citation verification, Rule 1.6 data handling).

1. **Store: SQLite → Postgres. ✅ Done.** `schema.sql` is the production DDL;
   `migrate_postgres.py` loads it plus the seed corpus into the database named by
   `DATABASE_URL`. Setting `DATABASE_URL` is now all it takes to make the API read from
   Postgres: `engine_adapter._connect` returns `graph.pg_connect(url)`, a thin wrapper that
   rewrites the SQLite-shaped queries (`?`→`%s`, `node`/`edge`→`tax_node`/`tax_edge`) and
   normalizes Postgres `DATE`/`TEXT[]` back to the engine's string types. Endpoints,
   serialization, retrieval logic, and the currency gate did not move — and
   `python/test_postgres_parity.py` proves both stores return identical results.
2. **Retrieval: BM25 → hybrid. ✅ Done.** Set `SUBK_EMBED_PROVIDER` and the lexical seed is
   fused with a dense (embedding) seed by Reciprocal Rank Fusion — a node ranked high by
   either channel seeds retrieval. The embedder is pluggable: `hashing` (pure-stdlib,
   offline, deterministic stand-in) or `openai` (real semantic embeddings, needs
   `OPENAI_API_KEY`). On Postgres, `migrate_postgres.py` stores vectors in a pgvector column
   with an HNSW index (the kNN-at-scale path); at the current corpus size the engine fuses
   in-memory. Graph expansion, the currency filter, and computation routing did not move,
   and `python/test_hybrid.py` + the hybrid cases in `test_postgres_parity.py` cover it.
   Unset `SUBK_EMBED_PROVIDER` = BM25-only (default).
3. **Enrichment: hook → real but gated. ✅ Done.** `python/enrich.py` drafts a plain-language
   gloss (PROPOSE); the draft is quarantined — it is never written to the graph, so retrieval
   and the currency gate cannot surface it — and an attorney applies it (PROMOTE, the only
   writer, attributed; `enrichment_status` → `enriched`). The model never writes citable law.
   Providers: `stub` (offline, no key) or `openai` (`SUBK_ENRICH_PROVIDER`, needs
   `OPENAI_API_KEY`); enrichment sends ONLY public corpus text. `python/test_enrich.py`
   proves the gate.
4. **Serving.** This service. Done.

---

## Before you add an LLM API key (data egress)

A key turns on two outbound paths with very different risk. Know which you are enabling:

| Path | Env | What leaves the building | Risk |
|------|-----|--------------------------|------|
| **Enrichment** | `SUBK_ENRICH_PROVIDER=openai` | ONLY public corpus text (citation / label / existing note) | **Low** — no client-matter data |
| **Query embedding** | `SUBK_EMBED_PROVIDER=openai` | every `/ask` **question** verbatim | **High** — questions can carry matter facts (Rule 1.6) |

So the safe order is: enable **enrichment** with a key first (public text only); keep query
embedding on the offline `hashing` provider until your data-handling posture is set.

**Checklist before a real key touches the system:**

- [ ] **Account posture** — use a zero-data-retention / no-train OpenAI org with a signed DPA
  (the standard API does not train on inputs by default, but ZDR is the bar for matter data);
  set the data region you need.
- [ ] **Secret handling** — key lives in a secrets manager or the process env, NEVER in code
  or a committed file. `.env` is gitignored; scope and rotate the key.
- [ ] **Data minimization** — keep `SUBK_EMBED_PROVIDER=hashing` (queries stay local) until
  you have decided questions won't carry privileged facts, or you redact them first.
- [ ] **Egress control** — outbound only to `api.openai.com` over TLS; consider an allowlist or
  proxy. Enrichment input is auditable (it is corpus text).
- [ ] **Auth + audit first** — replace the API-key stub with real identity and the stdout audit
  hook with an immutable store BEFORE exposing the service, since `/ask` inputs and audit rows
  carry matter data.
- [ ] **Gate intact** — never auto-apply model output; enrichment stays attorney-promoted
  (`test_enrich.py` is the regression guard).

Bottom line: the enrichment key is low-risk by design (public text, quarantined, attorney-gated);
the thing to be careful with is turning the *query embedder* to `openai`.

---

## Before any non-internal use (the legal-product layer)

- **Auth — ✅ OIDC implemented.** `auth.py` verifies real OIDC/JWT bearer tokens against
  your IdP's JWKS (signature, issuer, audience, expiry) when `SUBK_OIDC_ISSUER` +
  `SUBK_OIDC_AUDIENCE` are set; the principal is the token's email/sub and an org claim
  carries the tenant. `test_auth.py` covers it. Still to wire for full production: a
  per-organization *authorization* policy (the org claim is captured; enforce it per route)
  and per-principal rate limiting at the gateway. Set up an IdP to get the issuer/audience.
- **Citation verification — ✅ structural + live primary-source.** `python/cite_verify.py`
  classifies a citation (statute / reg / ruling / case / public law / FR) and grades it:
  `in_corpus` (attorney-curated), `well_formed` (valid format), or `unrecognized` (likely
  error) — always, offline. With `SUBK_CITE_PROVIDER=online` it also checks the cite against
  the **authoritative primary source for its type**: regulations → **eCFR** (which also
  reports the "up to date as of" date), statutes/IRC → **US Code** (Cornell LII), `X FR Y` →
  **Federal Register**, Rev. Rul./Rev. Proc./Notice → **IRS** (irs.gov recent-guidance
  folder), cases → **CourtListener** (the only type needing a key — a free
  `COURTLISTENER_TOKEN`; everything else needs none). Network failures fall back to the
  offline verdict. It runs over every model draft in `enrich.py` (`cite_check`), so a
  hallucinated or removed cite is caught before promotion; `test_cite_verify.py` covers the
  offline path. Known limit: the IRS drop folder holds recent guidance, so a pre-2000s
  ruling reports "not in recent folder — check the IRB archive" rather than a false negative.
- **Confidentiality (Rule 1.6)** — `/ask` and `/compute` inputs and audit rows can carry
  matter facts. Encrypt at rest and in transit, restrict access, set a retention policy,
  and use no-train / zero-data-retention settings on any LLM calls.
- **Audit — ✅ tamper-evident implemented.** `audit.py` writes a hash-chained, append-only
  log (each record links to the prior hash; `audit.py verify <file>` detects any
  alteration, drop, or reorder). Set `SUBK_AUDIT_LOG` to persist to a file. Still to wire:
  point the sink at an immutable store (WORM bucket or append-only Postgres with RLS) and
  treat rows as confidential.
- **Edge / transport** — terminate TLS and enforce rate limiting at the gateway or reverse
  proxy; lock `SUBK_CORS_ORIGINS` down to known origins.
- **Currency maintenance** — the gate is only as good as the corpus. Stand up the process
  to add new authority with validity intervals and supersession edges as the law changes,
  attorney-verified, on a cadence. This is the standing value of the system.

---

## Configuration (environment)

| Var | Default | Meaning |
|-----|---------|---------|
| `SUBK_API_KEYS` | _(unset → OPEN)_ | api-key mode: comma-separated `label:key` or bare keys |
| `SUBK_OIDC_ISSUER` / `SUBK_OIDC_AUDIENCE` | _(unset)_ | Set both → OIDC mode: verify real JWTs from your IdP |
| `SUBK_OIDC_JWKS_URL` / `SUBK_OIDC_ORG_CLAIM` | _(discovered)_ / `org_id` | Optional JWKS override; the org/tenant claim |
| `SUBK_AUDIT_LOG` | _(stdout only)_ | Append hash-chained audit records to this file too |
| `SUBK_CORS_ORIGINS` | `*` | Allowed browser origins, comma-separated |
| `SUBK_DB` | temp dir | Path of the SQLite build the API serves from |
| `DATABASE_URL` | _(unset → SQLite)_ | Postgres URL. Set it and the API reads from Postgres; used by `migrate_postgres.py` too |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `subk` / `changeme` / `subk` | compose Postgres |
| `SUBK_EMBED_PROVIDER` | _(unset → BM25-only)_ | `hashing` (offline stdlib) or `openai` — enables hybrid dense+lexical retrieval |
| `SUBK_EMBED_DIM` | `256` | Hashing-embedder dimension (must match the migrated pgvector column) |
| `OPENAI_API_KEY` / `SUBK_EMBED_MODEL` | _(unset)_ / `text-embedding-3-small` | For `SUBK_EMBED_PROVIDER=openai` |
| `API_PORT` | `8000` | Host port the compose stack publishes |

---

## Provider portability

The code binds to nothing but a Postgres connection string. Moving between your own infra
and a managed provider (Supabase, PlanetScale, RDS, Cloud SQL) is a `DATABASE_URL` change
plus a run of `migrate_postgres.py`. Adopt a provider's proprietary surfaces (managed auth,
auto-generated APIs, row-level security tied to their identity) only deliberately — those
are the lock-in, not the database itself.
