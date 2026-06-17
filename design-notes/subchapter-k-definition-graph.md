# Subchapter K GraphRAG — Definition-Centric Model

Pivot from a document-centric graph to a **definition-centric** one. In Subchapter K
the cross-reference density is definitional, so defined terms are the hub nodes and the
sections, regs, rulings, and cases attach to them. Same `schema.sql` foundation and same
four layers; this file is the delta plus the worked seed.

> **Unverified seed data.** Citations are graph hypotheses, `created_by='attorney'`
> confirmation required before any is treated as authority. Ruling/case pin cites in
> particular must be confirmed. Illustrative, not exhaustive.

---

## 1. The new modeling primitive: the computed term

- **statutory term** — defined in the Code text (e.g. §751 unrealized receivables /
  inventory items; §7701 definitions). One `defines` edge from the defining provision.
- **interpretive term** — meaning supplied mainly by case/ruling (e.g. "partnership"
  via Culbertson intent; the §1.701-2 anti-abuse gloss). Edges arrive as `interprets`.
- **computed term** — NOT defined in one place; the output of a scattered algorithm
  (outside basis, inside basis, capital account, amount realized). Modeled as a hub
  whose inbound edges *are* the formula. This is the primitive normal legal graphs lack.

A computed-term hub plus its inbound `computes` / `adjusts` / `uses` edges is a
**computation DAG**: walk it and you assemble the worksheet, every step authority-traced,
every authority's edge cases ruling-enriched.

---

## 2. Schema delta (on top of schema.sql)

```sql
-- term subtype on the existing node_type='defined_term'
ALTER TABLE tax_node ADD COLUMN term_subtype TEXT
    CHECK (term_subtype IN ('statutory','interpretive','computed'));

-- edge: carry the mechanics of a computation edge
ALTER TABLE tax_edge ADD COLUMN direction  TEXT
    CHECK (direction IN ('increase','decrease','constraint','initialize'));
ALTER TABLE tax_edge ADD COLUMN mechanism  TEXT;   -- short human description

-- extend the edge_type vocabulary
--   add: 'computes','adjusts','uses','informs'   (keep cross_references/cites/etc.)
-- 'computes'  provision -> computed term   (initializer)
-- 'adjusts'   provision -> computed term   (+ direction, + mechanism)
-- 'uses'      provision -> term            (constraint / dependency, no value change)
-- 'interprets' ruling|case -> term         (supplies/refines meaning)
-- 'informs'   ruling|case -> provision     (clarifies a section's operation)
```

Query the hub: "everything that feeds outside basis" is a single hop —
`SELECT * FROM tax_edge WHERE dst_id = 'term-outside-basis'`.

---

## 3. Worked seed: OUTSIDE BASIS as a computation DAG

Hub node: `term-outside-basis` (node_type=`defined_term`, term_subtype=`computed`).

| Source authority | edge_type | direction | mechanism | informed by (interprets/informs) |
|---|---|---|---|---|
| §722 (26 U.S.C. 722) | computes | initialize | contributed property: carryover basis + money | Rev. Rul. 99-5 (DRE→partnership) |
| §742 (26 U.S.C. 742) | computes | initialize | purchased/inherited interest: cost (§1012) or §1014 | Rev. Rul. 84-53 (single-basis rule) |
| §705(a)(1) | adjusts | increase | distributive share of income, incl. tax-exempt | |
| §752(a) | adjusts | increase | increase in share of liabilities = deemed money contribution | Crane / Tufts; §1.752-2 (recourse), §1.752-3 (nonrecourse) |
| §705(a)(2) | adjusts | decrease | distributive share of loss + nondeductible noncapital expense | |
| §733 | adjusts | decrease | distributions reduce basis | Rev. Rul. 99-6 (partnership→DRE) |
| §752(b) | adjusts | decrease | decrease in share of liabilities = deemed money distribution | Canal Corp (debt-financed distribution / §707 overlap) |
| §704(d) | uses | constraint | loss allowed only to extent of basis | |

That table is the basis formula expressed as graph edges. The interpreting authorities
are not loose citations; each hangs off the exact provision whose edge case it resolves.

---

## 3b. Sequencing and the zero-floor (the computed-term execution rule)

Retrieving the inputs is not enough; a computed term has to *run*, and basis runs in a
fixed order with a hard floor. Two additions make the DAG executable:

- **Edge `sequence` + `ordering_group`.** Each `computes`/`adjusts` edge carries an
  `ordering_group` in {`increase`, `distribution`, `reduce`, `loss_limited`} and a
  `sequence` within it. The hub executes groups in that order: increases first
  (§722, §705(a)(1), §752(a)), then distributions and liability decreases (§733, §752(b)),
  then basis-reducing items (§705(a)(2)(B), §705(a)(3)), then loss-limited items (§704(d)).
- **Hub `floor` + `overflow_edge`.** The hub floors at zero. Each floor has a typed
  overflow: a distribution that breaches the floor routes to a §731(a) gain node; a loss
  that cannot be absorbed routes to a §704(d) suspended-loss carryforward node. Overflow
  is not discarded, it becomes its own node.

```sql
ALTER TABLE tax_edge ADD COLUMN ordering_group TEXT
    CHECK (ordering_group IN ('increase','distribution','reduce','loss_limited'));
ALTER TABLE tax_edge ADD COLUMN sequence SMALLINT;
-- computed-term hub gets: floor (default 0) + overflow_edge -> {§731(a) gain | §704(d) carryforward}
```

Ordering is load-bearing, not cosmetic: a distribution can strip basis that would
otherwise have absorbed a loss, so reordering the groups changes the number. This rule is
verified against the IRS LB&I unit (PAR-P-002) and is implemented and self-validated in
the companion workbook `outside-basis.xlsx` (Sally Smith and Joe Johnson examples both
reproduce the IRS figures).

## 4. Inside basis hub (sketch)

Hub: `term-inside-basis` (computed).

- `computes`/initialize: §723 (contributed property carryover); cost for purchased.
- `adjusts`: §743(b) on transfer of an interest; §734(b) on distribution.
- `uses`/trigger: §754 election (or substantial built-in loss / substantial basis
  reduction, the >$250k thresholds) gates whether §743(b)/§734(b) apply.
- `uses`/allocation: §755 allocates the adjustment among assets.
- informed by: §754-election rulings and the §743/§755 regs.

Capital account (§704(b), §1.704-1(b)(2)(iv) substantial economic effect) is a separate
computed-term hub, interrelated with but distinct from basis.

---

## 5. Why this is the differentiated feature

The definition-dependency graph is to partnership tax what the cross-walk was to ERISA:
the thing nobody else has. No product models basis as a traceable computation graph with
the controlling section and its interpreting rulings first-class on every edge. It also
fits lazy enrichment perfectly: the hubs are where questions concentrate (everyone asks
about basis), so the expensive semantic layer enriches the highest-value nodes first by
construction. Cost profile, corrected: cheap structural skeleton, with semantic spend
concentrated and well-targeted at the definition hubs rather than spread thin.
