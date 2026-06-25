#!/usr/bin/env python3
"""
test_subk_llm.py — the reasoning sandwich's deterministic halves, offline.

The Anthropic call needs a key/network, so it isn't exercised here. What IS tested is everything
that makes the sandwich safe: the law/fact classifier, the Layer-A bundle (stable IDs), and the
Layer-B closure verifier — fed a hand-written 'model output' to prove it accepts grounded
analysis and REJECTS invented law, prose/array mismatches, and smuggled legal conclusions.

    python test_subk_llm.py
"""
import lawfact
import mask
import subk_see
import subk_intake
import subk_llm

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    print("law/fact classifier (the reusable module):")
    check("applied legal outcome is a conclusion of law",
          lawfact.is_conclusion_of_law("This receipt is taxable in Missouri"))
    check("the §704(b) ultimate conclusion is flagged",
          lawfact.is_conclusion_of_law("The allocation has substantial economic effect"))
    check("a statistic is factual", not lawfact.is_conclusion_of_law("Revenue fell 12% from 2019 to 2024"))
    check("describing the test is factual",
          not lawfact.is_conclusion_of_law("The economic-effect test requires capital-account maintenance"))
    check("a normative duty is a conclusion of law", lawfact.is_conclusion_of_law("The partner must restore the deficit"))

    print("Layer A — verified bundle with stable IDs:")
    frame = subk_intake.frame_from_form({"allocation_at_issue": "99% depreciation to A",
                                         "qualified_income_offset": True, "capital_account_balances": "A100k/B100k"})
    bundle = subk_llm.build_bundle(frame, {"status": "verified_external", "as_of": "2026-06-23"})
    check("bundle stamps LAW ids for factors", any(i["id"] == "LAW:EE.alt" for i in bundle["items"]))
    check("bundle stamps FACT ids for filled fields", "FACT:qualified_income_offset" in bundle["ids"])
    check("bundle_key is stable for the same bundle", subk_llm.bundle_key(bundle) == subk_llm.bundle_key(bundle))

    print("Layer B — closure ACCEPTS grounded analysis:")
    good = {
        "propositions": [
            {"text": "The agreement contains a qualified income offset [FACT:qualified_income_offset], "
                     "which is the alternate economic-effect test [LAW:EE.alt].",
             "type": "LEGAL", "supports": ["FACT:qualified_income_offset", "LAW:EE.alt"]},
        ],
        "augmentations": [
            {"text": "Special allocations of depreciation are common in real-estate partnerships.",
             "category": "BUSINESS", "source": "general practice"}],
        "gaps": ["no deficit-restoration provision in the record"],
        "ultimate_question": "Does the allocation have substantial economic effect?",
    }
    v = subk_llm.layer_b_verify(good, bundle["ids"])
    check("a fully-grounded, well-tagged analysis is CLOSED", v["closed"] is True)
    check("the ultimate conclusion is returned flagged for the attorney", "NEEDS_HUMAN" in v["conclusion"])

    print("Layer B — closure REJECTS unsafe output:")
    invented = {"propositions": [{"text": "Under [LAW:IRC-9999] this is fine.", "type": "LEGAL",
                                  "supports": ["LAW:IRC-9999"]}], "augmentations": [], "gaps": [],
                "ultimate_question": "?"}
    check("a support ID not in the bundle is rejected (invented law)",
          subk_llm.layer_b_verify(invented, bundle["ids"])["closed"] is False)

    mismatch = {"propositions": [{"text": "It satisfies the primary test [LAW:EE.primary].", "type": "LEGAL",
                                  "supports": ["LAW:EE.alt"]}], "augmentations": [], "gaps": [], "ultimate_question": "?"}
    pr = subk_llm.layer_b_verify(mismatch, bundle["ids"])["propositions"][0]
    check("inline tag not in supports[] is caught (prose/array mismatch)",
          pr["verdict"] == "rejected" and any("mismatch" in p for p in pr["problems"]))

    unsupported = {"propositions": [{"text": "This clearly has economic effect.", "type": "LEGAL",
                                     "supports": []}], "augmentations": [], "gaps": [], "ultimate_question": "?"}
    check("a LEGAL proposition with no support is rejected → NEEDS_HUMAN",
          subk_llm.layer_b_verify(unsupported, bundle["ids"])["closed"] is False)

    smuggled = {"propositions": [], "ultimate_question": "?", "gaps": [],
                "augmentations": [{"text": "Therefore the allocation is respected and has economic effect.",
                                   "category": "BUSINESS", "source": "x"}]}
    av = subk_llm.layer_b_verify(smuggled, bundle["ids"])
    check("a legal conclusion smuggled into an augmentation is rejected",
          av["closed"] is False and av["augmentations"][0]["verdict"] == "rejected")

    nosrc = {"propositions": [], "ultimate_question": "?", "gaps": [],
             "augmentations": [{"text": "Depreciation rules changed in 1986.", "category": "HISTORICAL", "source": ""}]}
    check("an uncited augmentation is rejected (must be sourced + flagged)",
          subk_llm.layer_b_verify(nosrc, bundle["ids"])["augmentations"][0]["verdict"] == "rejected")

    print("masking — client identity is tokenized before send, restored locally:")
    mk = mask.Masker()
    sent = mk.mask("Acme Holdings LLC paid $245,000 (EIN 12-3456789)")
    check("entity / amount / EIN are masked", all(t in sent for t in ("[ENTITY_1]", "[AMOUNT_1]", "[EIN_1]")))
    check("masking round-trips losslessly", mk.unmask(sent) == "Acme Holdings LLC paid $245,000 (EIN 12-3456789)")
    fr2 = subk_intake.frame_from_form({"allocation_at_issue": "Acme Holdings LLC gets 99% of depreciation",
                                       "capital_account_balances": "A $100,000"})
    b2 = subk_llm.build_bundle(fr2, {"status": "verified_external"})
    user, _ = subk_llm._masked_user(b2, "does the allocation have economic effect?")
    check("LAW items are NOT masked (model needs the real reg)", "1.704-1(b)(2)(ii)" in user)
    check("FACT identifiers ARE masked in the wire payload", "Acme Holdings LLC" not in user and "[ENTITY_1]" in user)

    print("redaction — real names captured at intake are scrubbed to codes BEFORE send:")
    import redact
    r = redact.Redactor()
    check("derives a code from a real name", r.add_name("John Doe") == "JoDo")
    check("redacts the full name AND the surname", r.redact("John Doe and Doe signed") == "JoDo and JoDo signed")
    check("scan flags an un-rostered caption name", "Smith" in redact.scan_candidates("See Smith v. Jones"))
    check("scan ignores a name already in the roster", "Doe" not in redact.scan_candidates("Officer Doe testified", r))
    frd = subk_intake.frame_from_form({"allocation_at_issue": "John Doe gets 99% of depreciation",
                                       "qualified_income_offset": True})
    brd = subk_llm.build_bundle(frd, {"status": "verified_external"})
    user, _ = subk_llm._masked_user(brd, "does it have economic effect?", redactor=r)
    check("a real name in a FACT is replaced by its code in the wire payload",
          "John Doe" not in user and "JoDo" in user)
    check("LAW reg text is never redacted (model needs the real reg)", "1.704-1(b)(2)(ii)" in user)

    print("egress invariant — fail-closed at the one exit:")
    rc = redact.Redactor(); rc.add_name("John Doe", code="Contributing partner")
    try:
        subk_llm.assert_clean("the Contributing partner contributed land", rc)
        check("a clean (redacted) payload passes the invariant", True)
    except subk_llm.EgressBlocked:
        check("a clean (redacted) payload passes the invariant", False)
    raised = False
    try:
        subk_llm.assert_clean("John Doe contributed land", rc)   # a name survived redaction
    except subk_llm.EgressBlocked as e:
        raised = True
        check("the error never contains the leaked name", "John" not in str(e) and "Doe" not in str(e))
    check("a surviving registered name is refused (fail-closed)", raised)

    print("egress audit log — provable record, no names:")
    import json as _json, tempfile, os as _os
    logf = _os.path.join(tempfile.mkdtemp(), "egress.jsonl")
    _os.environ["SUBK_EGRESS_LOG"] = logf
    msk = mask.Masker(); msk.mask("$100,000")
    subk_llm._egress_log("anthropic", "claude-opus-4-8", "key123", "Contributing partner gets [AMOUNT_1]", rc, msk)
    rec = _json.loads(open(logf).read().splitlines()[-1])
    check("logs a sha256 of the scrubbed payload", len(rec["payload_sha256"]) == 64)
    check("logs roles, not names", "Contributing partner" in rec["roles"] and "John Doe" not in str(rec))
    check("records the mask count + a chain hash", rec["masks"] == 1 and "chain" in rec)
    del _os.environ["SUBK_EGRESS_LOG"]

    print(f"\nALL {passed} SANDWICH-SAFETY CHECKS PASSED")


if __name__ == "__main__":
    main()
