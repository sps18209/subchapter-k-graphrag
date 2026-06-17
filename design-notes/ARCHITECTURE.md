# Tax Authority GraphRAG — Architecture & Proof Slice

Converged plan from the multiplayer loop (two passes, reconciled). Proof slice: IRC
§ 1031 (like-kind exchanges). Designed to plug into the existing `legal-ai-shared-infra`
pattern, not fork it.

---

## Assumptions surfaced

- Integrates with the legal-AI suite conventions: Postgres source of truth, preflight
  gates, assumption registry, a citation/currency hard gate, audit log.
- Slice = § 1031. Chosen for cross-reference density, a clean temporal story (TCJA
  limited it to real property effective 2018-01-01), and live rulings to link.
- Public data only: govinfo USLM XML (Title 26), eCFR XML (26 CFR), IRB (rulings),
  CourtListener (cases — already wired in the suite).
- Slice goal: prove deterministic structural extraction + the currency gate end to
  end, on one section, runnable offline on a fixture. `extract_structural.py` does this.

---

## The multiplayer loop, compressed

**Pass A — forward / structural-first.** Acquire corpus, parse a deterministic
structural graph from the XML, store, enrich with an LLM, build retrieval, add the
verifier gate last, then output skills. Dependency-clean and mirrors proven infra.
*Weakness:* value only appears at the end; long time to first trustable answer; treats
the graph as the product when the verifier is arguably the load-bearing piece.

**Pass B — inverted / failure-first.** Start from the failure mode that destroys a tax
tool: a confidently cited stale or hallucinated authority (malpractice, § 6662 / § 6694
penalty exposure). Make the *currency verifier* a standalone product that ships in days,
make the graph **lazy** (construct the local authority neighborhood just-in-time per
question), primitive = the Authority Chain, not the Provision. *Weakness:* a purely lazy
graph can't answer "show everything that cites § 1031" or map a doctrine, and flat
seeding loses the cross-reference structure that makes tax hard.

**Merge (the recreate).** The two weaknesses cancel once you split the graph by *cost*:

- Structural extraction is **cheap** (the XML already carries section structure and
  cross-references), so there is no reason to go lazy on it. Precompute it.
- Semantic extraction (holdings, doctrine, fact patterns) is the **expensive** LLM part,
  so make *that* lazy and demand-driven with permanent caching. The graph fills in along
  the contour of real questions instead of by brute force.
- The verifier is **both** the smallest shippable unit (Pass B) **and** the hard gate
  inside retrieval (Pass A). Build it first; reuse it as the gate.

That resolves Pass A's slow-time-to-value and Pass B's weak doctrine-level reasoning at
the same time.

---

## Architecture — four layers, build Layer 0 first

**Layer 0 — Currency / Supersession Verifier (ship standalone).**
Input: a citation. Output: still good law? modified / superseded / obsoleted by what, as
of what date? Needs only the citation registry + supersession edges + effective dates —
tiny. Independently sellable as a point tool. Becomes the hard gate for Layers 1–3.
Backed by `v_stale_authority`.

**Layer 1 — Deterministic structural graph (precompute, zero LLM).**
Parse USLM/eCFR XML and ruling/case text into typed nodes and edges. Authority tier and
validity intervals assigned at ingest. Powers "what cites § 1031", doctrine maps,
high-quality retrieval expansion. This is `extract_structural.py` plus an XML feeder.

**Layer 2 — Semantic enrichment (lazy, LLM, cached forever).**
When a question touches a node, extract its holding / issue / fact pattern / plain-language
gloss and its embedding, then cache permanently (`enrichment_status` flips to `enriched`).
You pay only for what is asked; the result accrues into the precomputed graph.

**Layer 3 — GraphRAG retrieval + gate + output.**
Vector seed over enriched nodes → graph expansion along `cross_references` / `cites` /
`defines` using Layer 1 structure → currency filter (Layer 0, as-of the transaction date)
→ authority-tier rerank → assemble context. Then: assumption registry logs unverified
facts, confidence tagging (substantial authority / reasonable basis / MLTN from tier +
agreement), and the existing `doctrinal-synthesis`, `loophole-operator`,
`legal-adversarial-analysis` (IRS Exam / Appeals / Tax Court personas), and
`legal-draft-assembly` (opinion letter) skills consume it.

---

## Cost model (why "too much data" does not bite)

| Layer | Over what | LLM calls | When paid |
|-------|-----------|-----------|-----------|
| 0 verifier | supersession edges only | none | once, tiny |
| 1 structural | full slice corpus | none (parse only) | once, cheap |
| 2 semantic | only nodes a question touches | 1 per node, cached | on demand |
| 3 retrieval | per query | embed query + synth | per query |

The expensive operation (LLM extraction) never runs over the whole corpus. It runs over
the nodes real questions reach, once each, then is cached. Brute-force Microsoft-style
GraphRAG over all of Title 26 is the thing you are explicitly *not* doing.

---

## Build sequence

1. `schema.sql` → Postgres up (done).
2. Layer 0 verifier over a hand-seeded § 1031 supersession set; ship as a CLI/endpoint.
3. `extract_structural.py` (done) + USLM/eCFR XML feeder → populate Layer 1 for § 1031.
4. Wire Layer 0 `v_stale_authority` as the retrieval hard gate.
5. Layer 2 lazy enrichment + pgvector seed.
6. Layer 3 expansion + rerank; hand off to existing output skills.
7. Replicate to the next subchapter. The slice is a template.

---

## FMEA — top failure modes and the guard

- **Stale authority cited as good law** → Layer 0 hard gate; `created_by='attorney'`
  override required and logged, identical posture to the litigation citation gate.
- **Reg out-ranked by a ruling** → `authority_tier` rerank is mandatory, not optional.
- **PLR/TAM treated as precedent** → tier 6, excluded from the authority retrieval path
  by query filter (`authority_tier <= 4`); IRC § 6110(k)(3).
- **Wrong temporal version** → every node/edge carries `valid_from`/`valid_to`; retrieval
  is always as-of a transaction date; missing date → open assumption, not a guess.
- **Graph rot** → the product is the re-ingest pipeline (USLM/eCFR point-in-time feeds,
  IRB weekly), not the one-time graph. Diff → patch → audit.
- **Regex citation collisions** (e.g. `1.1031(a)-1` emitting a spurious `§ 1`) → span
  masking in the extractor; covered by the fixture.

---

## How it reuses what already exists

`legal-evidence-graph` (typed node/edge model), `legal-citation-verifier` (CourtListener
existence check, here extended with IRB supersession), `legal-assumption-registry`,
`legal-adversarial-analysis`, `legal-draft-assembly`, `rag-architect` (retrieval), the
Neo4j/`ingest.py` muscle from Pointdexer (optional traversal replica), and the
`legal-ai-shared-infra` preflight/audit spine. The net new code is the XML feeder, the
supersession verifier, and the lazy-enrichment cache.
