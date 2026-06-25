# Subchapter K · GraphRAG

A definition-centric retrieval system for U.S. partnership tax (Subchapter K, IRC §§701–777),
plus a self-contained browser demo. Terms are hubs; statutes, regulations, rulings, and cases
attach to them by typed edges. Basis questions are routed to a deterministic calculator instead
of being reasoned out of text. A currency layer hard-gates stale, removed, and revoked authority
by transaction date.

There are two ways to use it.

## 1 · Web demo — no setup

Open **`index.html`** in any browser: double-click it, or serve the folder and visit the local
address:

```
python -m http.server 8000      # then open http://localhost:8000
```

It runs the whole system client-side. Ask a question, explore each term **hub** (with its formula
DAG and connected authority), run the deterministic **basis engine** on deliberately hard cases,
and move the **"as of"** date to watch the currency gate turn authority on and off. Nothing is
sent anywhere — the corpus and logic are embedded in the file.

## 2 · Python system — `python/`

The authoritative engine: a SQLite graph, a deterministic outside-basis calculator, a BM25 +
graph-expansion retriever, and a currency/supersession gate. Pure standard library, no install,
no network.

```
cd python
python test_subk.py                                                  # 40 checks
python parity_test.py                                                # 640 checks: JS demo == Python (needs node)
python tui.py                                                        # interactive terminal UI
python query.py "what feeds a partner's outside basis"
python query.py --verify 2026-06-01
python query.py --compute --inputs '{"beginning_basis":245000,"cash_distributed":465000}'
```

`tui.py` is an interactive REPL over the same engine (`ask`, `asof`, `verify`, `cite`,
`source`, `compute`, `hubs`, `hub`, `node`, `horizon`) — the terminal counterpart to the web
demo. The one-shot `query.py` is better for scripting and piping.

`assistant.py` (`subk-chat`) is a plain-English front door: it routes natural language to the
right tool and the engine still produces every answer. With `SUBK_CITE_PROVIDER=online`,
citations are checked live against their primary source (eCFR / US Code / Federal Register /
IRS), `source`/`cite` fetch the actual current text, and `python cite_verify.py --audit`
sweeps the whole corpus against those sources. `horizon.py` separately scans *proposed*
federal tax bills (Congress.gov / govinfo) — clearly labeled "not law," never in the graph.

`schema.sql` is the production Postgres DDL the SQLite runtime mirrors. See `python/README.md`
for the four-layer architecture and what is real vs. a stand-in (BM25 for embeddings, SQLite for
Postgres/Neo4j, a wired LLM-enrichment hook).

## 3 · API service — `deploy/`

A FastAPI service that wraps the `python/` engine for deployment: `/ask`, `/compute`, `/verify`,
`/hubs`, `/node`, with OIDC-or-API-key auth, a tamper-evident (hash-chained) audit trail, and the
unverified-seed disclaimer carried in every response. It boots on the SQLite engine with no Postgres required, and is
provider-agnostic — Postgres is a `DATABASE_URL` swap.

```
cd deploy
pip install -r requirements.txt
python -m uvicorn app:app --reload      # http://127.0.0.1:8000/docs
python test_api.py                      # 30 checks across every endpoint
```

Docker: `cp .env.example .env`, then `docker compose up --build`. The stack also stands up a
pgvector Postgres; `docker compose --profile tools run --rm migrate` loads `schema.sql` + the seed
into it. Full run instructions, the four production swaps, and the legal-product checklist (auth,
citation verification, Rule 1.6 data handling, audit store) are in **`deploy/DEPLOY.md`**.

## What's in here

```
index.html        self-contained web demo (the thing to share)
python/           the runnable system, tests, schema, and its README
deploy/           FastAPI service over the engine (Docker, Postgres migration, DEPLOY.md)
web-src/          sources for the demo + scripts to regenerate it
design-notes/     earlier design exploration, kept for history
```

- **`web-src/`** holds `engine.js` (the JS port of the engine, held to parity with the Python
  by `python/parity_test.py` — 640 cross-language checks via `web-src/parity_runner.js`),
  `data.json` (the corpus exported from the graph), and the HTML template. Run
  `python web-src/build.py` to rebuild `index.html`, or `python python/export_web_data.py` to
  regenerate `data.json` from the graph.
- **`design-notes/`** holds earlier architecture notes, the definition-graph writeup, an ERISA
  cross-walk seed, and the validated basis workbook (`outside-basis.xlsx`). These are kept for
  history; the working system in `python/` and `index.html` is authoritative and supersedes the
  early `schema.early.sql`.

## Posture

Everything in the corpus is **unverified seed for attorney review, not citable ground**. Recent
(2024–2026) items were checked against IRS / Federal Register / eCFR sources and tagged verified,
superseded, reported, or context before encoding. This is a demonstration and a working tool, not
legal or tax advice, and not a substitute for primary-source research or professional judgment.
