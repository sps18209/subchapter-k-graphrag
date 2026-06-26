#!/usr/bin/env python3
"""
subk_disguised.py — the disguised-sale doctrine model (IRC 707(a)(2)(B); Treas. Reg. 1.707-3 to -5).
Data + deterministic helpers ONLY. No LLM.

This is the Layer-A authority checklist for the disguised-sale doctrine and the deterministic spine
of its reliability contract: given the facts provided, it states up front exactly which factors of
the test the tool CAN reach and which it CANNOT (and what's missing).

The 2-year presumption (Reg. 1.707-3(c)/(d)) drives everything: a contribution + a related
distribution within 2 years is PRESUMED to be a disguised sale unless the facts clearly establish
otherwise; outside 2 years, presumed NOT a sale unless the facts clearly establish it is. Either
presumption can be rebutted only by the facts-and-circumstances factors in Reg. 1.707-3(b)(2).
"""
from __future__ import annotations

DOCTRINE = "disguised_sale"
ROOT_CITE = "Treas. Reg. 1.707-3"

# Layer-A authority checklist. Order tracks the reg's analytic sequence: existence -> presumption
# -> 10-factor rebuttal -> encumbered-property rules -> exceptions.
FACTORS = [
    {"id": "DS.basic", "label": "Existence — was there a contribution AND a related distribution?",
     "reg": "Treas. Reg. 1.707-3(a)",
     "needs": ["contribution_described", "distribution_described"]},
    {"id": "DS.two_year", "label": "Two-year presumption: within 2 years -> presumed sale; outside "
     "-> presumed not. Either is REBUTTABLE only by the 10-factor analysis.",
     "reg": "Treas. Reg. 1.707-3(c)/(d)",
     "needs": ["transfers_within_two_years"]},
    # The 10 facts-and-circumstances factors of Reg. 1.707-3(b)(2).
    {"id": "DS.fc", "label": "Facts-and-circumstances analysis — the 10-factor rebuttal test "
     "(Reg. 1.707-3(b)(2))", "reg": "Treas. Reg. 1.707-3(b)(2)"},
    {"id": "DS.fc.1", "label": "(i) Timing and amount of subsequent transfer can be determined "
     "with reasonable certainty at time of contribution", "reg": "Treas. Reg. 1.707-3(b)(2)(i)",
     "needs": ["timing_amount_certainty"]},
    {"id": "DS.fc.2", "label": "(ii) Transferor has a legally enforceable right to the "
     "subsequent transfer", "reg": "Treas. Reg. 1.707-3(b)(2)(ii)",
     "needs": ["legally_enforceable_right"]},
    {"id": "DS.fc.3", "label": "(iii) Right is secured (e.g., escrow, letter of credit) — "
     "transfer not subject to entrepreneurial risk", "reg": "Treas. Reg. 1.707-3(b)(2)(iii)",
     "needs": ["entrepreneurial_risk"]},
    {"id": "DS.fc.4", "label": "(iv) Distributee partner can/does receive disproportionate "
     "distribution / interest decreases", "reg": "Treas. Reg. 1.707-3(b)(2)(iv)",
     "needs": ["disproportionate_distribution"]},
    {"id": "DS.fc.5", "label": "(v) Distributee has special right to receive distributions "
     "of operating cash flow", "reg": "Treas. Reg. 1.707-3(b)(2)(v)",
     "needs": ["special_distribution_right"]},
    {"id": "DS.fc.6", "label": "(vi) Subsequent transfer is large relative to formula-distributable "
     "partnership income", "reg": "Treas. Reg. 1.707-3(b)(2)(vi)",
     "needs": ["distribution_vs_income"]},
    {"id": "DS.fc.7", "label": "(vii) Distributee has no obligation to return all or part of "
     "the distribution", "reg": "Treas. Reg. 1.707-3(b)(2)(vii)",
     "needs": ["obligation_to_return"]},
    {"id": "DS.fc.8", "label": "(viii) Distributee's right to subsequent transfer covered by "
     "binding obligation / not at partnership's discretion", "reg": "Treas. Reg. 1.707-3(b)(2)(viii)",
     "needs": ["binding_agreement"]},
    {"id": "DS.fc.9", "label": "(ix) Partnership held money/marketable securities in excess of "
     "reasonable business needs (anticipatory)", "reg": "Treas. Reg. 1.707-3(b)(2)(ix)",
     "needs": ["anticipatory_cash_holding"]},
    {"id": "DS.fc.10", "label": "(x) Distribution timed and structured to coincide with "
     "contribution / circumstances suggest sale", "reg": "Treas. Reg. 1.707-3(b)(2)(x)",
     "needs": ["sale_equivalent_circumstances"]},
    # Encumbered property and exceptions.
    {"id": "DS.encumbered", "label": "Encumbered property: contribution of property subject to "
     "a liability — separate disguised-sale rules apply",
     "reg": "Treas. Reg. 1.707-5", "needs": ["liability_encumbrance"]},
    {"id": "DS.exc.guaranteed", "label": "Exception: guaranteed payment for capital "
     "(not treated as part of a sale)", "reg": "Treas. Reg. 1.707-4(a)",
     "needs": ["guaranteed_payment"]},
    {"id": "DS.exc.preferred", "label": "Exception: reasonable preferred return on capital",
     "reg": "Treas. Reg. 1.707-4(a)", "needs": ["preferred_return"]},
    {"id": "DS.exc.opcash", "label": "Exception: operating cash flow distributions (presumed not "
     "part of a sale up to formula amount)", "reg": "Treas. Reg. 1.707-4(b)",
     "needs": ["operating_cash_flow"]},
    {"id": "DS.exc.preform", "label": "Exception: reimbursement of preformation capital "
     "expenditures (Reg. 1.707-4(d) limits)", "reg": "Treas. Reg. 1.707-4(d)",
     "needs": ["preformation_expenditures"]},
]

FRAME_FIELDS = {
    "parties": "anonymized party roster — ROLE labels (Contributing partner, etc.)",
    "contribution_described": "what property/cash was contributed, when, by whom",
    "distribution_described": "what was distributed, when, to whom",
    "transfers_within_two_years": "did the contribution and distribution occur within 2 years of each other?",
    # The 10 F&C factors.
    "timing_amount_certainty": "(i) at time of contribution, were the timing and amount of the "
                               "subsequent transfer determinable with reasonable certainty?",
    "legally_enforceable_right": "(ii) does the transferor have a legally enforceable right to the "
                                 "subsequent transfer?",
    "entrepreneurial_risk": "(iii) is the right secured (escrow, letter of credit) so the transfer "
                            "isn't subject to entrepreneurial risk?",
    "disproportionate_distribution": "(iv) can/does the distributee receive disproportionate "
                                     "distributions (interest decreases)?",
    "special_distribution_right": "(v) does the distributee have a special right to operating cash flow?",
    "distribution_vs_income": "(vi) is the transfer large relative to the partner's formula-"
                              "distributable share of partnership income?",
    "obligation_to_return": "(vii) does the distributee have any obligation to return the distribution?",
    "binding_agreement": "(viii) is the right to the transfer covered by a binding obligation rather "
                         "than left to the partnership's discretion?",
    "anticipatory_cash_holding": "(ix) did the partnership hold money/marketable securities in excess "
                                 "of reasonable business needs in anticipation of the transfer?",
    "sale_equivalent_circumstances": "(x) is the distribution timed/structured to coincide with the "
                                     "contribution in a way that suggests a sale?",
    # Encumbered + exceptions.
    "liability_encumbrance": "was the contributed property subject to a liability (qualified or not)?",
    "guaranteed_payment": "is the distribution a guaranteed payment for capital (Reg. 1.707-4(a))?",
    "preferred_return": "is the distribution a reasonable preferred return (Reg. 1.707-4(a))?",
    "operating_cash_flow": "is the distribution an operating-cash-flow distribution (Reg. 1.707-4(b))?",
    "preformation_expenditures": "is the distribution reimbursement of preformation capital "
                                  "expenditures (Reg. 1.707-4(d))?",
}
REQUIRED_MINIMUM = ["contribution_described", "distribution_described"]

# Scope signals — phrases in the issue text that indicate the disguised-sale doctrine.
SCOPE_SIGNALS = [
    "disguised sale", "707(a)(2)(B)", "707(a)(2)", "section 707", "1.707-3", "1.707-4", "1.707-5",
    "two-year", "two year", "presumption", "contribution and distribution", "contribution followed by",
    "preformation", "preferred return", "guaranteed payment for capital", "qualified liability",
]

# Deterministic provision detectors — literal phrases the intake finds in pasted facts or in an
# agreement, with the matched sentence saved as the field's verbatim quote.
PROVISION_PATTERNS = {
    "transfers_within_two_years": r"(?:within|less than|under)\s+(?:24\s+months|two\s+years|2\s+years)",
    "binding_agreement": r"(?:binding (?:obligation|agreement)|required to distribute|shall distribute)",
    "preferred_return": r"preferred return",
    "guaranteed_payment": r"guaranteed payment(?:\s+for\s+capital)?",
    "preformation_expenditures": r"preformation (?:expenditure|capital expenditure|capex)",
    "operating_cash_flow": r"operating cash[-\s]flow distribution",
    "liability_encumbrance": r"(?:subject to (?:a |the )?(?:liability|mortgage|encumbrance)|"
                              r"qualified liability)",
}

# Doctrine-aware framing for the runtime (system prompt, manifest, interview).
DESCRIPTION = "the disguised-sale test (IRC 707(a)(2)(B); Treas. Reg. 1.707-3 to -5)"
EXAMPLE_TAG = "[LAW:1.707-3(c)]"
ULTIMATE_CONCLUSION_PHRASE = ("whether the contribution + distribution IS a disguised sale of "
                              "property (or of a partnership interest)")
ISSUE_FIELDS = ["contribution_described", "distribution_described"]

# Interview script — each entry: (field, kind, prompt). kind is 'text' or 'yn'.
INTERVIEW_SCRIPT = [
    ("contribution_described", "text",
     "Describe the CONTRIBUTION — what was transferred, when, by which role"),
    ("distribution_described", "text",
     "Describe the DISTRIBUTION — what was distributed, when, to which role"),
    ("transfers_within_two_years", "yn",
     "Did the contribution and the distribution occur within 2 YEARS of each other?"),
    ("liability_encumbrance", "yn",
     "Was the contributed property subject to a liability (mortgage, encumbrance, qualified liability)?"),
    # The 10 facts-and-circumstances factors (Reg. 1.707-3(b)(2)(i)-(x)).
    ("timing_amount_certainty", "yn",
     "At the time of contribution, were the TIMING and AMOUNT of the distribution determinable "
     "with reasonable certainty?"),
    ("legally_enforceable_right", "yn",
     "Did the transferor have a LEGALLY ENFORCEABLE RIGHT to the distribution?"),
    ("entrepreneurial_risk", "yn",
     "Was the right SECURED (escrow / letter of credit) so the distribution wasn't subject to "
     "entrepreneurial risk?"),
    ("disproportionate_distribution", "yn",
     "Was the distribution DISPROPORTIONATE relative to the partner's interest?"),
    ("special_distribution_right", "yn",
     "Did the distributee have a SPECIAL right to receive operating cash flow?"),
    ("distribution_vs_income", "text",
     "Size of the distribution relative to the partner's formula share of partnership income "
     "(e.g. 'roughly equal' / 'far exceeds')"),
    ("obligation_to_return", "yn",
     "Does the distributee have any OBLIGATION TO RETURN the distribution?"),
    ("binding_agreement", "yn",
     "Was the right to the distribution covered by a BINDING obligation (not partnership "
     "discretion)?"),
    ("anticipatory_cash_holding", "yn",
     "Did the partnership hold cash / marketable securities in EXCESS of reasonable business needs?"),
    ("sale_equivalent_circumstances", "text",
     "Any other circumstances suggesting the contribution + distribution was, in substance, a sale"),
    # Exceptions.
    ("guaranteed_payment", "yn",
     "Is the distribution a GUARANTEED PAYMENT for capital (Reg. 1.707-4(a))?"),
    ("preferred_return", "yn",
     "Is the distribution a reasonable PREFERRED RETURN (Reg. 1.707-4(a))?"),
    ("operating_cash_flow", "yn",
     "Is the distribution an OPERATING CASH FLOW distribution (Reg. 1.707-4(b))?"),
    ("preformation_expenditures", "yn",
     "Is the distribution a reimbursement of PREFORMATION capital expenditures (Reg. 1.707-4(d))?"),
]


def empty_frame() -> dict:
    return {"doctrine": DOCTRINE,
            "fields": {f: {"value": None, "quote": None, "source": None} for f in FRAME_FIELDS},
            "sources": []}


def _present(frame: dict) -> set:
    return {f for f, v in frame["fields"].items() if v.get("value") is not None}


def evaluable(frame: dict) -> tuple[list, list]:
    """Which leaf factors CAN be evaluated vs CANNOT (and what's missing). Same contract as
    subk_see — the orchestrator can dispatch generically."""
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
    """Top-level go/no-go. We need the minimum (a contribution + a distribution), and at minimum the
    two-year-window fact (which drives the presumption); the F&C factors then rebut the presumption.
    A useful run also needs at least 3 of the 10 F&C factors filled (or the analysis is too thin)."""
    have = _present(frame)
    missing_min = [f for f in REQUIRED_MINIMUM if f not in have]
    can, cannot = evaluable(frame)
    fc_can = [c for c in can if c["id"].startswith("DS.fc.")]
    presumption_reachable = any(c["id"] == "DS.two_year" for c in can)
    return {
        "ready": not missing_min and presumption_reachable and len(fc_can) >= 3,
        "missing_minimum": missing_min,
        "presumption_reachable": presumption_reachable,
        "fc_factors_reachable": [c["id"] for c in fc_can],
        "factors_evaluable": [c["id"] for c in can],
        "factors_blocked": cannot,
    }


def authority_cites() -> list:
    seen, out = set(), []
    for fac in [{"reg": ROOT_CITE}] + FACTORS:
        if fac["reg"] not in seen:
            seen.add(fac["reg"])
            out.append(fac["reg"])
    return out


if __name__ == "__main__":
    f = empty_frame()
    print(f"{DOCTRINE}: {len(FACTORS)} factors ({sum(1 for x in FACTORS if x['id'].startswith('DS.fc.'))} F&C), "
          f"{len(FRAME_FIELDS)} frame fields")
    print("authority cites:", ", ".join(authority_cites()[:6]) + " …")
    print("empty-frame readiness:", readiness(f))
