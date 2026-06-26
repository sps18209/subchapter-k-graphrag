#!/usr/bin/env python3
"""
subk_see.py — the substantial-economic-effect doctrine model (IRC 704(b);
Treas. Reg. 1.704-1(b)). Data + deterministic helpers ONLY. No LLM.

This is the Layer-A authority checklist for the analysis sandwich and the backbone of the
tool's RELIABILITY CONTRACT: given the facts provided, it states up front exactly which
factors of the test it CAN reach and which it CANNOT (and what's missing). The model never
decides scope — this deterministic mapping does.

Each factor cites the reg subsection that governs it; those cites are verifiable live against
eCFR (see cite_verify), so the checklist is machine-checked law, not an assertion.
"""
from __future__ import annotations

DOCTRINE = "substantial_economic_effect"
ROOT_CITE = "Treas. Reg. 1.704-1(b)"

# The Layer-A authority checklist. Parent rows (no "needs") are categories; leaf rows carry the
# fact-frame fields required to evaluate that factor. Order tracks the reg's analytic sequence:
# economic effect first (one of three ways), then substantiality.
FACTORS = [
    {"id": "EE", "label": "Economic effect — does the allocation actually affect the partners' "
     "economic arrangement?", "reg": "Treas. Reg. 1.704-1(b)(2)(ii)"},
    {"id": "EE.primary", "label": "Primary test: capital accounts maintained + liquidation per "
     "positive capital accounts + UNCONDITIONAL deficit-restoration obligation",
     "reg": "Treas. Reg. 1.704-1(b)(2)(ii)(b)",
     "needs": ["capital_account_maintenance", "liquidation_per_positive_ca", "deficit_restoration_obligation"]},
    {"id": "EE.capacct", "label": "Capital accounts maintained under the (b)(2)(iv) rules",
     "reg": "Treas. Reg. 1.704-1(b)(2)(iv)", "needs": ["capital_account_maintenance"]},
    {"id": "EE.alt", "label": "Alternate test: qualified income offset (for partners without a "
     "full DRO)", "reg": "Treas. Reg. 1.704-1(b)(2)(ii)(d)",
     "needs": ["qualified_income_offset", "capital_account_balances"]},
    {"id": "EE.equiv", "label": "Economic-effect equivalence ('dumb-but-lucky' deemed test)",
     "reg": "Treas. Reg. 1.704-1(b)(2)(ii)(i)", "needs": ["capital_account_balances"]},
    {"id": "SUB", "label": "Substantiality — is the economic effect substantial, apart from tax?",
     "reg": "Treas. Reg. 1.704-1(b)(2)(iii)"},
    {"id": "SUB.aftertax", "label": "Overall after-tax test (no partner's after-tax position "
     "enhanced with none substantially diminished)", "reg": "Treas. Reg. 1.704-1(b)(2)(iii)(a)",
     "needs": ["tax_motivation", "capital_account_balances"]},
    {"id": "SUB.shift", "label": "Shifting tax consequences within a single year",
     "reg": "Treas. Reg. 1.704-1(b)(2)(iii)(b)", "needs": ["tax_motivation"]},
    {"id": "SUB.trans", "label": "Transitory allocations that offset across years",
     "reg": "Treas. Reg. 1.704-1(b)(2)(iii)(c)", "needs": ["offsetting_later_years"]},
]

# Fact-frame fields the intake fills. Each value carries a verbatim quote (or null) + a source
# locator, so Layer B can string-match the quote back to the document it came from.
FRAME_FIELDS = {
    "parties": "anonymized party roster — short codes only (e.g. RoSm), never real names",
    "allocation_at_issue": "the specific allocation being tested (prerequisite for everything)",
    "capital_account_maintenance": "does the agreement maintain capital accounts per (b)(2)(iv)?",
    "liquidation_per_positive_ca": "are liquidating distributions made per positive capital accounts?",
    "deficit_restoration_obligation": "is there an unconditional obligation to restore a deficit?",
    "qualified_income_offset": "does the agreement contain a qualified income offset?",
    "capital_account_balances": "the partners' capital-account balances / history",
    "contributions": "contributions made",
    "distributions": "distributions made",
    "tax_motivation": "facts bearing on whether the allocation is tax-motivated (substantiality)",
    "offsetting_later_years": "are there offsetting allocations in later years (transitory)?",
}
# The minimum needed even to ATTEMPT the analysis.
REQUIRED_MINIMUM = ["allocation_at_issue"]

# Scope signals — phrases in the issue text that indicate the SEE doctrine.
SCOPE_SIGNALS = [
    "economic effect", "substantial", "allocat", "capital account", "704(b)", "section 704",
    "special allocation", "deficit restoration", "qualified income offset", "distributive share",
]

# Deterministic provision detectors — literal phrases found in pasted facts or an agreement; the
# matched sentence becomes the field's verbatim quote.
PROVISION_PATTERNS = {
    "qualified_income_offset": r"qualified income offset",
    "deficit_restoration_obligation": r"(deficit restoration|restore[sd]?\b[^.]{0,40}deficit|"
                                      r"negative capital account[^.]{0,50}restore)",
    "capital_account_maintenance": r"capital account[^.]{0,60}(maintain|in accordance|"
                                   r"1\.704-1\(b\)\(2\)\(iv\)|section 704\(b\))",
    "liquidation_per_positive_ca": r"liquidat[^.]{0,80}capital account",
}

# Doctrine-aware framing used by the runtime (system prompt, manifest, interview). Keeping these
# WITH the doctrine model means a new doctrine drops in with no spine edits.
DESCRIPTION = "the substantial-economic-effect test (IRC 704(b); Treas. Reg. 1.704-1(b))"
EXAMPLE_TAG = "[LAW:1.704-1(b)(2)(ii)(b)]"
ULTIMATE_CONCLUSION_PHRASE = "whether the allocation HAS substantial economic effect"
ISSUE_FIELDS = ["allocation_at_issue"]   # principal field(s) used to compose the issue string

# Interview script — each entry: (field, kind, prompt). kind is 'text' or 'yn'.
INTERVIEW_SCRIPT = [
    ("allocation_at_issue", "text",
     "Allocation being tested (e.g. '99% of depreciation to the contributing partner')"),
    ("capital_account_maintenance", "yn",
     "Does the agreement maintain capital accounts per Reg. 1.704-1(b)(2)(iv)?"),
    ("liquidation_per_positive_ca", "yn",
     "Are liquidating distributions made per positive capital accounts?"),
    ("deficit_restoration_obligation", "yn",
     "Is there an UNCONDITIONAL deficit-restoration obligation?"),
    ("qualified_income_offset", "yn",
     "Does the agreement contain a qualified income offset?"),
    ("capital_account_balances", "text", "Capital-account balances (use ROLE labels; vague amounts OK)"),
    ("tax_motivation", "text", "Any facts suggesting the allocation is tax-motivated?"),
]


def empty_frame() -> dict:
    return {"doctrine": DOCTRINE,
            "fields": {f: {"value": None, "quote": None, "source": None} for f in FRAME_FIELDS},
            "sources": []}


def _present(frame: dict) -> set:
    return {f for f, v in frame["fields"].items() if v.get("value") is not None}


def evaluable(frame: dict) -> tuple[list, list]:
    """Which leaf factors CAN be evaluated (all required fields present) vs CANNOT (and what's
    missing). This is the reliability contract in code: the tool reports its own reach."""
    have = _present(frame)
    can, cannot = [], []
    for fac in FACTORS:
        if "needs" not in fac:
            continue
        missing = [n for n in fac["needs"] if n not in have]
        row = {"id": fac["id"], "label": fac["label"], "reg": fac["reg"], "missing": missing}
        (cannot if missing else can).append(row)
    return can, cannot


def readiness(frame: dict) -> dict:
    """Top-level go / no-go: do we have the minimum, and can we reach economic effect at all?"""
    have = _present(frame)
    missing_min = [f for f in REQUIRED_MINIMUM if f not in have]
    can, cannot = evaluable(frame)
    # An economic-effect conclusion needs at least ONE of the three EE paths fully satisfied.
    ee_paths = [c for c in can if c["id"] in ("EE.primary", "EE.alt", "EE.equiv")]
    return {
        "ready": not missing_min and bool(ee_paths),
        "missing_minimum": missing_min,
        "economic_effect_paths_reachable": [c["id"] for c in ee_paths],
        "factors_evaluable": [c["id"] for c in can],
        "factors_blocked": cannot,
    }


def authority_cites() -> list[str]:
    """Every reg cite in the factor tree — Layer A verifies each against eCFR before use."""
    seen, out = set(), []
    for fac in [{"reg": ROOT_CITE}] + FACTORS:
        if fac["reg"] not in seen:
            seen.add(fac["reg"])
            out.append(fac["reg"])
    return out


if __name__ == "__main__":
    f = empty_frame()
    print(f"{DOCTRINE}: {len(FACTORS)} factors, {len(FRAME_FIELDS)} fact-frame fields")
    print("authority cites:", ", ".join(authority_cites()))
    print("empty-frame readiness:", readiness(f))
