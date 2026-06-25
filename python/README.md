# Subchapter K GraphRAG

A working, offline, **definition-centric** retrieval system for partnership tax
(Subchapter K, IRC §§701-777). Terms are hubs; statutes, regulations, rulings, and
cases attach to them by typed edges. Basis questions are routed to a deterministic
calculator instead of being reasoned out of text. A currency layer hard-gates stale,
removed, and revoked authority by transaction date.

Pure Python standard library. No network, no model download, no external database.
Runs as-is.

```
python tui.py                # interactive terminal UI (REPL over the engine)
python query.py "what feeds a partner's outside basis"
python query.py "CAMT corporate alternative minimum tax partnership election"
python query.py --verify 2026-06-01
python query.py --compute --inputs '{"beginning_basis":245000,"cash_distributed":465000}'
python test_subk.py          # 40 checks
python parity_test.py        # 640 checks: engine.js port == Python engine (needs `node`)
```

## Why definition-centric

Black-letter partnership tax is a web of defined terms. "Outside basis" is not a
sentence in one section; it is an algorithm scattered across §722, §742, §705, §733,
§752, §704(d), and §731(a). Modeling the term as a **hub** whose inbound edges *are*
the computation makes that structure explicit and retrievable: ask about basis and you
get the whole ordered input set, not whichever section happened to match your keywords.

## Four layers

**Layer 0 — currency / supersession gate** (`graph.applicable`, `graph.currency_report`).
Every time-sensitive node carries a validity interval; revoke/remove relationships are
typed `supersedes` edges. As of a transaction date the gate hard-blocks anything not yet
effective, expired, removed, or revoked. This caught the author's own seed going stale:
§199A was encoded as sunsetting after 2025, but OBBBA made it permanent.

**Layer 1 — deterministic structural graph** (`seed_subk.py`, `seed_recent.py`,
`graph.py`). Curated nodes and typed edges loaded into SQLite. Cheap, no model.

**Layer 2 — semantic enrichment** (`enrich.py`, gated). The `synthesis` field is hand-authored
plain-law text. An enricher (offline `stub` or `openai`) can PROPOSE a draft gloss, but drafts
are quarantined — never written to the graph, so retrieval can't cite them — until an attorney
PROMOTES one (`enrichment_status` → `enriched`, the only writer). `test_enrich.py` proves the
gate. Disabled by default; nothing here depends on it to run.

**Layer 3 — GraphRAG retrieval** (`retrieve.py`). Lexical seed (BM25), optionally **fused
with a dense embedding seed** by Reciprocal Rank Fusion when `SUBK_EMBED_PROVIDER` is set
(`embeddings.py`) → graph expansion (2 hops; a computed-term hub pulls its entire input
DAG) → authority-tier rerank with the seeds preserved through truncation → currency filter
→ assemble with citations. Basis questions are flagged and routed to the calculator.

## The calculator is not graph data

Two separate jobs. The **graph** reasons about *authority* (it ingests legal text and
answers "which rules apply, in what order"). The **calculator** (`calculator.py`) computes
*numbers* at run time. They are deliberately decoupled because language models mis-order
the basis waterfall and drop the zero-floor. The graph routes a basis question to the
engine; the engine returns the figure with a step trace. The engine self-validates against
the two IRS LB&I worked examples (Sally Smith: §704(d) loss 45k allowed / 80k suspended;
Joe Johnson: §731(a) gain 220k / ending basis 0).

## What is real vs. stand-in

| Piece | Here | Production swap |
|---|---|---|
| Retrieval | BM25 default; **hybrid wired** | set `SUBK_EMBED_PROVIDER` → dense+BM25 fused by RRF (hashing offline stand-in / OpenAI); vectors persist in pgvector |
| Store | SQLite (default) | Postgres — **wired**: set `DATABASE_URL` and `graph.pg_connect` serves from `schema.sql`'s `tax_node`/`tax_edge` with identical results (`test_postgres_parity.py`) |
| Semantic layer | hand-authored `synthesis` | lazy LLM enrichment, cached |
| Calculator | outside basis | + inside basis / §743(b) and §704(b) capital-account engines |

The architecture (definition hubs, computed-term DAGs, currency gate, computation routing)
is the real, transferable part. The substitutions above are honest scope limits, not hidden
gaps.

## Recent developments — verified before encoding

The whole point of this system is to never carry hallucinated authority, so the 2024-2026
items in `seed_recent.py` were checked against IRS / Federal Register / eCFR / firm sources
before being added. Each node's `synthesis` carries a tag: `[VERIFIED]`, `[VERIFIED-superseded]`,
`[REPORTED]` (real item, a specific cite unconfirmed), or `[CONTEXT]` (enforcement program
/ form mechanic, not authority). Confirmed and encoded: Rev. Rul. 2024-14 (real, **revoked**
2025 by Notice 2025-34); the §1.6011-18 basis-shifting TOI reg (final 1/14/2025, TD 10028) —
Notice 2025-23 **announced** its removal and waived penalties, but the eCFR (current through
6/12/2026) shows it **still codified**, so it is encoded as in force (the prior seed wrongly
recorded a 3/6/2026 removal — a currency error the June-2026 re-check caught); the **CAMT
interim-notice stack** (Notice 2025-27/28/46/49 and 2026-7, plus the underlying Sept-2024
proposed regs REG-112129-23 with partnership-specific Prop. §§1.56A-5/-20) — the corporate
AMT runs on stacked interim notices, no final regs as of early 2026; Form 7217; §1062 farmland
installment payment-deferral election (OBBBA, Form 1062) with Notice 2026-3 estimated-tax
relief; the §761(a) clean-energy elect-out for §6417. OBBBA (P.L. 119-21) is modeled as an
amending event with `amends`/`enacts` edges.

## Copyright & verification posture

Nodes store only **primary-authority citations** plus original plain-law synthesis. No
third-party prose (treatise or practice-note text) is reproduced. Every node and edge is
**unverified seed for attorney review**, not citable ground — study notes carry imprecision
(e.g., a contribution note that says basis tracks FMV where §722 actually uses *adjusted*
basis), so the graph surfaces structure to check, it does not certify it.

## Files

- `seed_subk.py` — core corpus + subsection/sub-definition leaf nodes
- `seed_recent.py` — verified 2024-2026 layer + supersession chain
- `graph.py` — SQLite store, currency/supersession gate, integrity check
- `calculator.py` — deterministic outside-basis engine (self-validating)
- `retrieve.py` — Layer 3 retrieval (BM25 + optional dense fusion + expansion + rerank + currency + routing)
- `embeddings.py` — pluggable embedders (hashing offline stand-in / OpenAI) + the dense index for hybrid retrieval
- `enrich.py` — gated Layer-2 enrichment: an LLM (stub/OpenAI) drafts glosses; an attorney promotes them (the only writer)
- `cite_verify.py` — citation verification: classify + check against corpus/format (offline), plus optional live primary-source lookup (eCFR / US Code / Federal Register / IRS rulings / CourtListener + US Tax Court DAWSON for the T.C. memos CourtListener misses) via `SUBK_CITE_PROVIDER=online`; reports the section's last-amended date, `--source` fetches the actual current text, and `--audit` sweeps every corpus citation against the live sources
- `query.py` — one-shot CLI
- `tui.py` — interactive terminal UI / REPL (ask, asof, verify, cite, source, compute, hubs, hub, node, horizon)
- `assistant.py` — plain-English front door: routes natural language to the right tool (rules / local Ollama model / OpenAI); the engine still produces every answer
- `horizon.py` — SEPARATE scan of PROPOSED federal tax bills (govinfo BILLS / Congress.gov). Bills are not law and never enter the graph or currency gate; output is labeled "NOT authority". Works with the shared `DEMO_KEY`; set `GOVINFO_API_KEY` for higher limits
- `subk_see.py` / `subk_intake.py` / `subk_analyze.py` — fact-intensive **substantial-economic-effect analyzer**. `subk_analyze.py --capabilities` states exactly what can/can't be ingested; the tool reports which factors of the §704(b) test it can and cannot reach from the facts given. `subk_see` is the doctrine model (factor tree + fact-frame), `subk_intake` the read-only ingestion engine
- `subk_llm.py` — the **reasoning sandwich** (Layer A → Anthropic → Layer B): Layer A assembles a verified, ID-stamped bundle; the pinned model reasons into a restricted schema where every legal proposition must cite a bundle ID; Layer B proves the legal content of the output traces entirely back to the bundle (rejecting invented law, prose/array mismatches, and legal conclusions smuggled into augmentations) and flags the ultimate conclusion for the attorney. Runs only with `--run` + `ANTHROPIC_API_KEY`; both verification layers are fully offline
- `lawfact.py` — standalone, dependency-free **conclusion-of-law vs. conclusion-of-fact classifier** (the Layer-B augmentation gate; reusable in other projects)
- `test_assistant.py` — proves NL routing + that the engine (not the router) answers
- `test_subk.py` — 40 checks
- `parity_test.py` — 640 cross-language checks proving `web-src/engine.js` matches this
  engine on retrieval, computation, currency, DAGs, and the applicability gate (runs the
  same battery through Node and asserts byte-for-byte agreement; needs `node` on PATH)
- `test_postgres_parity.py` — proves the production Postgres store returns results
  identical to SQLite across node/neighbors/applicable/currency/lexical + hybrid retrieval
  (skips without `DATABASE_URL`; needs psycopg)
- `test_hybrid.py` — hybrid (dense + lexical) retrieval checks, offline and deterministic
- `test_enrich.py` — proves the enrichment gate: drafts are not citable until an attorney promotes them
- `test_cite_verify.py` — proves the citation gate: corpus-backed vs well-formed vs unrecognized cites
- `test_horizon.py` — proves the proposed-legislation scan parses/labels bills as NOT-authority (offline)
- `schema.sql` — production Postgres DDL the SQLite store mirrors

## Extending

Add authority by appending a node tuple and its edges in `seed_subk.py` (the leaf-node
block shows the pattern: every subsection gets its own note). New computed terms get a hub
node plus inbound `computes`/`adjusts`/`uses` edges with `seq`/`grp`/`direction`, and
`overflow` edges for floor behavior. New time-sensitive or revoked authority gets a validity
interval and, if applicable, a `supersedes` edge. Run `python test_subk.py` and
`python graph.py` (integrity + currency self-check) after any change. If the change touches
the graph corpus, also run `python export_web_data.py && python web-src/build.py` to refresh
the demo, then `python parity_test.py` to confirm the JS port still matches.
