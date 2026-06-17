# ERISA GraphRAG — Cross-Walk Seed + Semantic Contract

Two things in one file: (1) the `parallel_provision` seed table that powers the
headline feature, and (2) the Layer 2 semantic-enrichment contract. Same four-layer
architecture and `schema.sql` as the tax slice; ERISA adds one edge type
(`parallel_provision`) and the enrichment contract below.

> **Unverified seed data.** Every citation here is a starting hypothesis for the
> graph, `created_by='attorney'` confirmation required before any of it is treated as
> authority. Subsection pin cites in particular must be confirmed. Scope: qualified
> retirement plans. Title IV/PBGC and welfare (COBRA/HIPAA) rows are marked CARVE for v1.

---

## 1. Cross-walk seed (ERISA Title I ↔ IRC)

Mapping types: `mirror` (substantively parallel), `parallel` (related but different
remedy/role, e.g. labor duty vs excise tax), `erisa_only`, `irc_only`. The asymmetric
rows (one-sided) are as valuable as the mirrors: the graph should *know* where no
counterpart exists.

| Topic | ERISA § (29 U.S.C.) | IRC § (26 U.S.C.) | Agency / reg | Mapping | Notes |
|---|---|---|---|---|---|
| Participation: min age & service | §202 (1052) | §410(a) | Treasury · 26 CFR 1.410(a)-3 | parallel | thresholds aligned, text differs |
| Coverage testing | — | §410(b) | Treasury · 1.410(b)-2 | irc_only | qualification-side only |
| Vesting standards | §203 (1053) | §411(a) | Treasury · 1.411(a)-3 | mirror | |
| Benefit accrual | §204(b) (1054) | §411(b) | Treasury · 1.411(b)-1 | mirror | |
| Anti-cutback (accrued benefit) | §204(g) (1054g) | §411(d)(6) | Treasury · 1.411(d)-4 | mirror | core protective rule |
| QJSA / QPSA survivor annuity | §205 (1055) | §401(a)(11) & §417 | Treasury · 1.401(a)-20 | mirror | |
| Anti-alienation + QDRO | §206(d) (1056d) | §401(a)(13) & §414(p) | Treasury · 1.401(a)-13 | mirror | QDRO defined at §414(p) |
| Min funding (single-employer) | §302–303 (1082–1083) | §412 & §430 | Treasury / PBGC | mirror | PPA-era split |
| Min funding (multiemployer) | §304 (1084) | §431 | Treasury / PBGC | mirror | |
| Funding-based benefit restrictions | §206(g) (1056g) | §436 | Treasury · 1.436-1 | mirror | |
| Prohibited transactions | §406 (1106) | §4975 | DOL + Treasury | parallel | ERISA = labor remedy; IRC = excise tax |
| PT exemptions | §408 (1108) | §4975(d) + PTEs | DOL · 29 CFR 2550.408b-2 | parallel | class exemptions live DOL-side |
| Fiduciary duties (prudence/loyalty) | §404 (1104) | — (echoes §401(a)(2) exclusive benefit) | DOL · 29 CFR 2550.404a-1 | erisa_only | the labor-law heart of Title I |
| Definition of fiduciary | §3(21) (1002(21)) | — | DOL · 29 CFR 2510.3-21 | erisa_only | the vacated/re-proposed rule lives here |
| Co-fiduciary & breach liability | §405, §409 (1105, 1109) | — | — | erisa_only | |
| Reporting (Form 5500) | §§101–104 (1021–1024) | §6058 & §6059 | joint DOL/IRS/PBGC | parallel | one filing, three masters |
| Contribution/benefit limits | — | §415 | Treasury · 1.415 | irc_only | |
| Top-heavy | — | §416 | Treasury · 1.416-1 | irc_only | |
| Nondiscrimination | — | §401(a)(4) | Treasury · 1.401(a)(4) | irc_only | |
| Controlled group / common control | §210 (1060) | §414(b)(c)(m)(o) | Treasury · 1.414(c) | mirror | definitions cross-incorporated |
| Plan termination (PBGC) | §4041–4044 (1341–1344) | §4980 reversion excise | PBGC (Title IV) | parallel | **CARVE v1** |
| COBRA continuation | §§601–608 (1161–1168) | §4980B | DOL/Treasury | parallel | **CARVE v1** (welfare) |
| HIPAA portability | §§701–707 (1181–1187) | §9801 et seq. | DOL/Treasury/HHS | parallel | **CARVE v1** (welfare) |

The `parallel_provision` edge gets a `mapping_type` property (the column above) and a
`confidence`. Seeded mirrors enter at attorney confidence; LLM-proposed mirrors (below)
enter at `confidence < 1` until promoted.

---

## 2. Layer 2 semantic-enrichment contract

Runs lazily, only when a question reaches a node, then caches forever
(`enrichment_status` → `enriched`). Model returns ONLY JSON; cites only refs present in
the source text; never asserts a cross-walk it cannot ground.

**Provision / regulation node:**
```json
{
  "node_id": "29-u-s-c-1104",
  "plain_language": "one-sentence gloss",
  "operative_rule": "if <condition> then <obligation/consequence>",
  "defined_terms_used": ["fiduciary", "plan asset"],
  "conditions": ["..."],
  "exceptions": [{"ref": "29-u-s-c-1108", "summary": "..."}],
  "practice_tags": ["fiduciary", "prudence", "loyalty"],
  "parallel_provision_hint": {
    "suspected_irc": "26-u-s-c-401-a-2",
    "mapping_type": "parallel",
    "confidence": 0.4,
    "basis": "exclusive-benefit overlap; NOT a 1:1 mirror"
  },
  "embedding_text": "canonical RULE statement, not raw prose"
}
```

**Ruling / DOL Advisory Opinion / case node:**
```json
{
  "node_id": "rev-proc-2021-30",
  "issue": "...",
  "holding": "...",
  "doctrine": "what it stands for, one line",
  "fact_pattern": "salient facts",
  "authorities_applied": ["29-u-s-c-1104", "26-u-s-c-4975"],
  "treatment": {"follows": [], "distinguishes": [], "limits": []},
  "source": {"agency_or_court": "IRS", "authority_tier": 4},
  "good_law_flag": "defer_to_layer_0",
  "embedding_text": "issue + holding, normalized"
}
```

Two ERISA-specific moves: (a) embeddings are built over a normalized **rule statement**,
not raw text, so retrieval is semantic over the rule not the prose; (b)
`parallel_provision_hint` lets the model *propose* cross-walk edges during enrichment as
hypotheses (`created_by='llm'`, low confidence) that an attorney promotes to
`confidence=1`. That is how the expensive cross-walk gets built semi-automatically
without ever fabricating a mirror, matching the assumption-registry / attorney-gate
discipline already in the suite.

---

## 3. Connectors worth stitching in (registry scan)

For ERISA's two messy, non-XML layers (case law and reference resolution):

- **CourtListener** (free, `extract_citations`, `call_endpoint`) — case layer +
  doubles as the citation-existence half of the Layer 0 verifier. Already the suite's
  conceptual backbone; an MCP version exists.
- **Descrybe Legal Engine** ("clean, structured U.S. primary law", `find_case_from_reference`,
  `get_case_passages`) — a structured-primary-law feeder that directly offsets the
  "structural extraction is cheaper in tax than ERISA" gap.

No connector exists for DOL/EBSA guidance, the Federal Register, or eCFR, so the
**regulations + DOL Advisory Opinion layer stays a direct-API integration** (govinfo
USLM, eCFR, Federal Register API, EBSA), the same fetch pattern the suite already uses.
