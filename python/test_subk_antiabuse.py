#!/usr/bin/env python3
"""
test_subk_antiabuse.py — partnership anti-abuse (Treas. Reg. 1.701-2), offline.

Locks the doctrine's reliability contract AND its architectural fit: that adding a third doctrine
required no spine edits, only registration. Asserts: the registry resolves AA aliases; autodetect
routes free text and form-by-field-name; the doctrine model has 3 intent predicates + 7 F&C factors;
provisions detect with traceable quotes; readiness reports intent + principal-purpose + F&C; the
bundle assembles only over AA law; the system prompt is doctrine-aware (mentions 1.701-2 / NEVER
mentions SEE or DS); Layer-B closure still works under the new doctrine.

    python test_subk_antiabuse.py
"""
import subk_antiabuse as aa
import subk_disguised
import subk_doctrine
import subk_intake as si
import subk_llm
import subk_see

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    print("registry — anti-abuse plugs in:")
    check("'aa' alias resolves", subk_doctrine.resolve("aa") is aa)
    check("'antiabuse' alias resolves", subk_doctrine.resolve("antiabuse") is aa)
    check("'1.701-2' alias resolves", subk_doctrine.resolve("1.701-2") is aa)
    check("anti_abuse full key resolves", subk_doctrine.resolve("anti_abuse") is aa)
    check("DOCTRINES registry now lists 3 doctrines",
          set(subk_doctrine.DOCTRINES) == {subk_see.DOCTRINE, subk_disguised.DOCTRINE, aa.DOCTRINE})

    print("autodetect — picks AA from text and from a form:")
    mod, score, _ = subk_doctrine.autodetect(
        "Does this partnership transaction violate the anti-abuse rule under 1.701-2? "
        "A principal purpose appears to be tax reduction inconsistent with the intent of Subchapter K.")
    check("autodetect picks anti-abuse from issue text", mod is aa and score >= 3)
    check("a form with AA field names routes to AA",
          subk_doctrine.pick_for_form({"transaction_described": "x", "principal_purpose_tax_reduction": True,
                                       "partners_related": True}) is aa)

    print("doctrine model — intent + principal-purpose + 7 F&C factors:")
    fc = [f for f in aa.FACTORS if f["id"].startswith("AA.fc.")]
    intent = [f for f in aa.FACTORS if f["id"].startswith("AA.intent.")]
    check("exactly 7 facts-and-circumstances factors (Reg. 1.701-2(c)(1)-(7))", len(fc) == 7)
    check("3 intent-of-Subchapter-K predicates (Reg. 1.701-2(a)(1)-(3))", len(intent) == 3)
    check("every factor cites a 1.701-2 subsection",
          all("1.701-2" in f["reg"] for f in aa.FACTORS))
    r0 = aa.readiness(aa.empty_frame())
    check("empty frame is NOT ready (no transaction described)", r0["ready"] is False)
    check("empty frame reports principal-purpose unreachable", r0["principal_purpose_reachable"] is False)

    print("scope gate — picks the right doctrine:")
    s = si.scope_check("a principal purpose was tax reduction inconsistent with Subchapter K intent")
    check("anti-abuse signals route to the anti-abuse doctrine",
          s["in_scope"] and s["doctrine"] == aa.DOCTRINE)

    print("provision detection — phrase -> traceable quote:")
    text = ("A principal purpose of forming the partnership was tax reduction. All of the partners "
            "are related parties. The arrangement is structured as a step transaction.")
    fr = si.detect_provisions(text, source="memo", doctrine=aa)
    check("detects the principal-purpose phrase",
          fr["fields"]["principal_purpose_tax_reduction"]["value"] is True)
    check("detects related-party language", fr["fields"]["partners_related"]["value"] is True)
    check("detects step-transaction language",
          fr["fields"]["integration_step_transactions"]["value"] is True)
    check("a detected fact carries its source sentence as the quote",
          "principal purpose" in fr["fields"]["principal_purpose_tax_reduction"]["quote"].lower())

    print("readiness — intent + principal-purpose + reachable F&C, names what's blocked:")
    form = {
        "transaction_described": "Contributing partner contributed property A to PRS on 1/1/25; "
                                  "Service partner received a special allocation of all gain on sale "
                                  "of property A on 7/1/25; partners are related.",
        "bona_fide_partnership": True,
        "substantial_business_purpose": False,
        "principal_purpose_tax_reduction": True,
        "inconsistent_with_subk_intent": True,
        "partners_related": True,
        "704_literal_but_purpose_inconsistent": True,
        "benefits_burdens_retained_by_contributor": True,
    }
    r = aa.readiness(si.frame_from_form(form, doctrine=aa))
    check("ready when minimum + an intent predicate + ≥3 F&C are reachable", r["ready"] is True)
    check("principal-purpose test is reachable when both predicates are filled",
          r["principal_purpose_reachable"] is True)
    check("intent predicates reachable list includes AA.intent.1",
          "AA.intent.1" in r["intent_predicates_reachable"])
    check("at least the 3 supplied F&C factors are reachable",
          set(r["fc_factors_reachable"]) >= {"AA.fc.4", "AA.fc.5", "AA.fc.6"})
    check("an un-supplied F&C factor is correctly reported as blocked",
          any(b["id"] == "AA.fc.1" for b in r["factors_blocked"]))

    print("Layer A bundle — anti-abuse law only (no SEE / no DS leaks in):")
    bundle = subk_llm.build_bundle(si.frame_from_form(form, doctrine=aa),
                                    {"status": "verified_external"}, doctrine=aa)
    check("bundle carries the AA doctrine", bundle["doctrine"] == aa.DOCTRINE)
    check("bundle carries AA.* LAW ids", any("LAW:AA." in i["id"] for i in bundle["items"]))
    check("bundle does NOT carry SEE or DS factor ids",
          not any(("LAW:EE." in i["id"] or "LAW:DS." in i["id"]) for i in bundle["items"]))

    print("doctrine-aware framing — runtime knows it's anti-abuse, not SEE or DS:")
    sp = subk_llm.system_prompt(aa)
    check("AA system prompt names the anti-abuse rule and 1.701-2",
          "anti-abuse" in sp and "1.701-2" in sp)
    check("AA system prompt does NOT mention substantial-economic-effect",
          "substantial-economic-effect" not in sp)
    check("AA system prompt does NOT mention the disguised-sale framing",
          "disguised-sale" not in sp)
    check("AA prompt uses a 1.701-2 example tag, not 1.704 or 1.707",
          "1.701-2" in sp and "1.704" not in sp and "1.707" not in sp)
    check("AA declares its own interview script", isinstance(aa.INTERVIEW_SCRIPT, list) and
          len(aa.INTERVIEW_SCRIPT) >= 14)
    check("AA interview script only references real AA fields",
          all(field in aa.FRAME_FIELDS for field, _, _ in aa.INTERVIEW_SCRIPT))

    print("Layer B closure under the new doctrine — grounded analysis is ACCEPTED:")
    good = {
        "propositions": [
            {"text": "A principal purpose of forming the partnership was substantial tax reduction "
                     "[FACT:principal_purpose_tax_reduction], engaging the principal-purpose test "
                     "[LAW:AA.principal_purpose].",
             "type": "LEGAL",
             "supports": ["FACT:principal_purpose_tax_reduction", "LAW:AA.principal_purpose"]},
        ],
        "augmentations": [], "gaps": [], "ultimate_question": "Is this abusive under 1.701-2?",
    }
    v = subk_llm.layer_b_verify(good, bundle["ids"])
    check("a fully-grounded anti-abuse proposition is CLOSED", v["closed"] is True)

    print(f"\nALL {passed} ANTI-ABUSE CHECKS PASSED")


if __name__ == "__main__":
    main()
