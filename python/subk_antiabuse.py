#!/usr/bin/env python3
"""
subk_antiabuse.py — partnership anti-abuse rule (Treas. Reg. 1.701-2). Data + deterministic helpers
ONLY. No LLM.

This is the most explicitly facts-and-circumstances doctrine in Subchapter K: the regulation itself
catalogs SEVEN factors (Reg. 1.701-2(c)) for whether a partnership has been "formed or availed of in
connection with a transaction a principal purpose of which is to reduce substantially the present
value of the partners' aggregate federal tax liability in a manner inconsistent with the intent of
Subchapter K" (Reg. 1.701-2(b)). The doctrinal frame is itself a three-part Subchapter-K-intent test
(Reg. 1.701-2(a)) — bona fide partnership + substantial business purpose, form-respects-substance,
and proper reflection — plus the separate aggregate-vs-entity remedy in 1.701-2(e).

This module exports the same shape every other doctrine does (see subk_see / subk_disguised), so it
drops into the registry without any spine edits.
"""
from __future__ import annotations

DOCTRINE = "anti_abuse"
ROOT_CITE = "Treas. Reg. 1.701-2"

# Layer-A authority checklist. Analytic order: intent-of-Subchapter-K predicate -> principal-purpose
# test -> seven F&C factors -> aggregate-vs-entity remedy.
FACTORS = [
    # Reg. 1.701-2(a) — the three intent-of-Subchapter-K requirements; any failure invites recast.
    {"id": "AA.intent", "label": "Intent of Subchapter K — three requirements (must all be met)",
     "reg": "Treas. Reg. 1.701-2(a)"},
    {"id": "AA.intent.1", "label": "(a)(1) Partnership is BONA FIDE and each partnership transaction "
     "is entered into for a SUBSTANTIAL BUSINESS PURPOSE",
     "reg": "Treas. Reg. 1.701-2(a)(1)",
     "needs": ["bona_fide_partnership", "substantial_business_purpose"]},
    {"id": "AA.intent.2", "label": "(a)(2) FORM of each partnership transaction RESPECTS the "
     "substance of the underlying economic arrangement",
     "reg": "Treas. Reg. 1.701-2(a)(2)", "needs": ["form_respects_substance"]},
    {"id": "AA.intent.3", "label": "(a)(3) Tax consequences PROPERLY REFLECT the partners' income "
     "(subject to Subchapter K's own contemplated exceptions)",
     "reg": "Treas. Reg. 1.701-2(a)(3)", "needs": ["proper_reflection"]},
    # Reg. 1.701-2(b) — the principal-purpose test; the predicate for Commissioner recast.
    {"id": "AA.principal_purpose", "label": "(b) Principal-purpose test: was a principal purpose of "
     "forming OR availing of the partnership to reduce the present value of the partners' aggregate "
     "federal tax liability in a manner INCONSISTENT with the intent of Subchapter K?",
     "reg": "Treas. Reg. 1.701-2(b)",
     "needs": ["principal_purpose_tax_reduction", "inconsistent_with_subk_intent"]},
    # Reg. 1.701-2(c) — the SEVEN facts-and-circumstances factors.
    {"id": "AA.fc", "label": "Facts-and-circumstances analysis — the 7 factors of Reg. 1.701-2(c)",
     "reg": "Treas. Reg. 1.701-2(c)"},
    {"id": "AA.fc.1", "label": "(c)(1) Partners' aggregate tax under the partnership is SUBSTANTIALLY "
     "LESS than if they had owned the assets and conducted the activities DIRECTLY",
     "reg": "Treas. Reg. 1.701-2(c)(1)", "needs": ["aggregate_vs_direct_tax"]},
    {"id": "AA.fc.2", "label": "(c)(2) Aggregate tax is substantially less than if purportedly "
     "separate transactions designed to achieve a particular end result were INTEGRATED and treated "
     "as a single transaction (step-transaction)",
     "reg": "Treas. Reg. 1.701-2(c)(2)", "needs": ["integration_step_transactions"]},
    {"id": "AA.fc.3", "label": "(c)(3) A partner necessary to the claimed tax result has a NOMINAL "
     "interest, is substantially PROTECTED from loss (indemnity, guaranty, preference), or has little/"
     "no participation in profits other than a preferred return for use of capital",
     "reg": "Treas. Reg. 1.701-2(c)(3)", "needs": ["nominal_partner_protected"]},
    {"id": "AA.fc.4", "label": "(c)(4) Substantially all of the partners are RELATED (directly or "
     "indirectly) to one another",
     "reg": "Treas. Reg. 1.701-2(c)(4)", "needs": ["partners_related"]},
    {"id": "AA.fc.5", "label": "(c)(5) Allocations LITERALLY comply with §§ 704(b) and 704(c) but "
     "with results INCONSISTENT with the purpose of those rules (special scrutiny when income/gain is "
     "specially allocated to a partner insulated from loss or with a nominal residual interest)",
     "reg": "Treas. Reg. 1.701-2(c)(5)", "needs": ["704_literal_but_purpose_inconsistent"]},
    {"id": "AA.fc.6", "label": "(c)(6) Benefits and burdens of ownership of property NOMINALLY "
     "CONTRIBUTED to the partnership are in substantial part RETAINED by the contributor (or related)",
     "reg": "Treas. Reg. 1.701-2(c)(6)", "needs": ["benefits_burdens_retained_by_contributor"]},
    {"id": "AA.fc.7", "label": "(c)(7) Benefits and burdens of partnership property are in substantial "
     "part SHIFTED to the distributee partner (or related) before or after distribution",
     "reg": "Treas. Reg. 1.701-2(c)(7)", "needs": ["benefits_burdens_shifted_to_distributee"]},
    # Reg. 1.701-2(e) — separate Commissioner remedy treating the partnership as aggregate.
    {"id": "AA.aggregate", "label": "(e) Abuse of entity treatment: Commissioner may treat the "
     "partnership as an AGGREGATE of its partners to carry out the purpose of any provision of the "
     "Code or regulations",
     "reg": "Treas. Reg. 1.701-2(e)", "needs": ["aggregate_vs_entity_application"]},
]

FRAME_FIELDS = {
    "parties": "anonymized party roster — ROLE labels (Contributing partner, etc.)",
    "transaction_described": "the partnership transaction at issue (what, when, who); the predicate "
                              "for everything else",
    # Intent-of-Subchapter-K predicate (Reg. 1.701-2(a)).
    "bona_fide_partnership": "(a)(1) is the partnership BONA FIDE — real pooling, real business?",
    "substantial_business_purpose": "(a)(1) does each partnership transaction have a SUBSTANTIAL "
                                     "non-tax business purpose?",
    "form_respects_substance": "(a)(2) does the form of each transaction respect the substance of the "
                                "underlying economic arrangement?",
    "proper_reflection": "(a)(3) do the tax consequences properly reflect the partners' income?",
    # Reg. 1.701-2(b) principal-purpose test.
    "principal_purpose_tax_reduction": "(b) was a PRINCIPAL PURPOSE of forming or availing of the "
                                        "partnership to substantially reduce present-value tax?",
    "inconsistent_with_subk_intent": "(b) is the resulting tax reduction INCONSISTENT with the intent "
                                      "of Subchapter K?",
    # The 7 F&C factors of Reg. 1.701-2(c).
    "aggregate_vs_direct_tax": "(c)(1) aggregate tax under partnership form substantially less than "
                                "direct ownership",
    "integration_step_transactions": "(c)(2) tax reduction depends on NOT integrating purportedly "
                                      "separate transactions",
    "nominal_partner_protected": "(c)(3) a necessary partner has a nominal interest / is protected "
                                  "from loss / has little participation other than a preferred return",
    "partners_related": "(c)(4) substantially all partners are related",
    "704_literal_but_purpose_inconsistent": "(c)(5) allocations are literal §704 compliance but "
                                             "results inconsistent with the purpose of those rules",
    "benefits_burdens_retained_by_contributor": "(c)(6) benefits and burdens of contributed property "
                                                  "are substantially retained by the contributor",
    "benefits_burdens_shifted_to_distributee": "(c)(7) benefits and burdens of partnership property "
                                                "are substantially shifted to the distributee",
    # Reg. 1.701-2(e) — separate aggregate-treatment remedy.
    "aggregate_vs_entity_application": "(e) is aggregate (not entity) treatment necessary to carry "
                                        "out the purpose of another Code/regulation provision?",
}

# The minimum needed even to ATTEMPT the analysis. Without a described transaction, there is no
# predicate to test for abuse.
REQUIRED_MINIMUM = ["transaction_described"]

# Scope signals — phrases in the issue text that indicate the anti-abuse doctrine.
SCOPE_SIGNALS = [
    "anti-abuse", "anti abuse", "antiabuse", "1.701-2", "701-2", "intent of subchapter k",
    "principal purpose", "abuse of subchapter k", "substantial business purpose",
    "form respects substance", "proper reflection", "step transaction",
    "aggregate treatment", "aggregate vs entity", "recast", "recharacterize",
]

# Deterministic provision detectors — literal phrases the intake finds; the matched sentence is the
# field's verbatim quote.
PROVISION_PATTERNS = {
    "principal_purpose_tax_reduction": r"principal purpose[^.]{0,80}(?:reduc|tax)",
    "substantial_business_purpose": r"substantial business purpose",
    "form_respects_substance": r"(?:form (?:respects?|matches?)\s+substance|substance over form)",
    "partners_related": r"(?:related part(?:y|ies)|all (?:of\s+)?the\s+partners[^.]{0,40}related)",
    "integration_step_transactions": r"step[\s-]transaction|integrated[^.]{0,40}transaction",
    "nominal_partner_protected": r"(?:nominal (?:interest|partner)|protected from (?:any )?loss|"
                                  r"loss guaranty|indemnit(?:y|ies)|distribution preference)",
    "aggregate_vs_entity_application": r"aggregate treatment|aggregate of (?:its )?partners",
}

# Doctrine-aware framing for the runtime.
DESCRIPTION = ("the partnership anti-abuse rule (Treas. Reg. 1.701-2) — a facts-and-circumstances "
               "test for whether a transaction's tax results are inconsistent with the intent of "
               "Subchapter K")
EXAMPLE_TAG = "[LAW:1.701-2(b)]"
ULTIMATE_CONCLUSION_PHRASE = ("whether the partnership or transaction is abusive within the meaning "
                              "of Treas. Reg. 1.701-2(b), or whether aggregate treatment under "
                              "1.701-2(e) applies")
ISSUE_FIELDS = ["transaction_described"]

# Interview script — each entry: (field, kind, prompt). 'yn' = yes/no/unknown, 'text' = free-form.
INTERVIEW_SCRIPT = [
    ("transaction_described", "text",
     "Describe the partnership transaction at issue (what, when, who; refer to parties by ROLE)"),
    # Intent-of-Subchapter-K predicate.
    ("bona_fide_partnership", "yn",
     "(a)(1) Is the partnership BONA FIDE — real economic pooling, real activity?"),
    ("substantial_business_purpose", "yn",
     "(a)(1) Does each partnership transaction have a SUBSTANTIAL non-tax business purpose?"),
    ("form_respects_substance", "yn",
     "(a)(2) Does the FORM of each transaction respect the SUBSTANCE of the underlying economic "
     "arrangement?"),
    ("proper_reflection", "yn",
     "(a)(3) Do the tax consequences PROPERLY REFLECT the partners' income?"),
    # Principal-purpose test.
    ("principal_purpose_tax_reduction", "yn",
     "(b) Was a PRINCIPAL PURPOSE of forming or availing of the partnership to SUBSTANTIALLY REDUCE "
     "the present value of the partners' aggregate federal tax liability?"),
    ("inconsistent_with_subk_intent", "yn",
     "(b) Is the resulting tax reduction INCONSISTENT with the intent of Subchapter K?"),
    # The 7 F&C factors of Reg. 1.701-2(c).
    ("aggregate_vs_direct_tax", "yn",
     "(c)(1) Is the partners' aggregate tax SUBSTANTIALLY LESS than if they had owned the assets and "
     "conducted the activities DIRECTLY?"),
    ("integration_step_transactions", "yn",
     "(c)(2) Does the tax reduction depend on NOT integrating purportedly separate transactions that "
     "were designed to achieve a particular end result?"),
    ("nominal_partner_protected", "yn",
     "(c)(3) Does any partner NECESSARY to the tax result have a NOMINAL interest, is substantially "
     "PROTECTED FROM LOSS (indemnity/guaranty/preference), or has little/no profit participation "
     "other than a preferred return?"),
    ("partners_related", "yn",
     "(c)(4) Are SUBSTANTIALLY ALL the partners RELATED (directly or indirectly)?"),
    ("704_literal_but_purpose_inconsistent", "yn",
     "(c)(5) Do the allocations LITERALLY comply with §§ 704(b)/(c) but produce results INCONSISTENT "
     "with the purpose of those rules?"),
    ("benefits_burdens_retained_by_contributor", "yn",
     "(c)(6) Are the benefits and burdens of property NOMINALLY CONTRIBUTED substantially RETAINED "
     "by the contributor (or a related party)?"),
    ("benefits_burdens_shifted_to_distributee", "yn",
     "(c)(7) Are the benefits and burdens of partnership property substantially SHIFTED to the "
     "distributee (or a related party) before or after the distribution?"),
    # Aggregate-vs-entity remedy.
    ("aggregate_vs_entity_application", "yn",
     "(e) Is AGGREGATE (not entity) treatment necessary to carry out the purpose of another Code or "
     "regulation provision?"),
]


def empty_frame() -> dict:
    return {"doctrine": DOCTRINE,
            "fields": {f: {"value": None, "quote": None, "source": None} for f in FRAME_FIELDS},
            "sources": []}


def _present(frame: dict) -> set:
    return {f for f, v in frame["fields"].items() if v.get("value") is not None}


def evaluable(frame: dict) -> tuple[list, list]:
    """Which leaf factors CAN be evaluated vs CANNOT (and what's missing). Same contract as
    subk_see / subk_disguised."""
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
    """Top-level go/no-go. We need a described transaction; AT LEAST ONE of the (a)(1)-(3) intent
    predicates filled (so the principal-purpose framing has something to anchor to); and at least
    3 of the 7 F&C factors filled (or the analysis is too thin to be useful)."""
    have = _present(frame)
    missing_min = [f for f in REQUIRED_MINIMUM if f not in have]
    can, cannot = evaluable(frame)
    intent_can = [c for c in can if c["id"].startswith("AA.intent.")]
    fc_can = [c for c in can if c["id"].startswith("AA.fc.")]
    principal_can = [c for c in can if c["id"] == "AA.principal_purpose"]
    return {
        "ready": (not missing_min) and bool(intent_can) and len(fc_can) >= 3,
        "missing_minimum": missing_min,
        "intent_predicates_reachable": [c["id"] for c in intent_can],
        "principal_purpose_reachable": bool(principal_can),
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
    n_fc = sum(1 for x in FACTORS if x["id"].startswith("AA.fc."))
    n_intent = sum(1 for x in FACTORS if x["id"].startswith("AA.intent."))
    print(f"{DOCTRINE}: {len(FACTORS)} factors ({n_intent} intent, {n_fc} F&C, "
          f"+ principal-purpose + aggregate), {len(FRAME_FIELDS)} frame fields")
    print("authority cites:", ", ".join(authority_cites()[:5]) + " …")
    print("empty-frame readiness:", readiness(f)["ready"], "(blocked:",
          len(readiness(f)["factors_blocked"]), "factors)")
