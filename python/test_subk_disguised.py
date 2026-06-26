#!/usr/bin/env python3
"""
test_subk_disguised.py — the disguised-sale doctrine's reliability contract, offline.

Asserts the deterministic guarantees: doctrine registry resolves and autodetects; scope is gated;
provisions detect with traceable quotes; the 10 F&C factors are reachable when filled; readiness
correctly reports presumption + F&C; the bundle assembles only over disguised-sale law (no SEE
factors leaking in); the existing Layer-B closure still works under the new doctrine.

    python test_subk_disguised.py
"""
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
    print("doctrine registry — pluggable:")
    check("'see' alias resolves to SEE", subk_doctrine.resolve("see") is subk_see)
    check("'ds' alias resolves to disguised-sale", subk_doctrine.resolve("ds") is subk_disguised)
    check("'disguised_sale' full key resolves", subk_doctrine.resolve("disguised_sale") is subk_disguised)
    check("an unknown name is None", subk_doctrine.resolve("not_a_doctrine") is None)
    mod, score, _ = subk_doctrine.autodetect("Did the contribution and subsequent distribution within 2 years "
                                              "constitute a disguised sale under section 707(a)(2)(B)?")
    check("autodetect picks disguised sale from issue text", mod is subk_disguised and score >= 2)
    mod2, _, _ = subk_doctrine.autodetect("Does this special allocation have substantial economic effect?")
    check("autodetect picks SEE when the issue is allocations/704(b)", mod2 is subk_see)
    check("a form with disguised-sale FIELD NAMES routes to disguised sale",
          subk_doctrine.pick_for_form({"contribution_described": "x", "transfers_within_two_years": True,
                                       "binding_agreement": True}) is subk_disguised)
    check("a form with SEE field names routes to SEE",
          subk_doctrine.pick_for_form({"allocation_at_issue": "x",
                                       "qualified_income_offset": True}) is subk_see)
    check("an empty or tied form returns None (caller falls back)",
          subk_doctrine.pick_for_form({}) is None and subk_doctrine.pick_for_form({"parties": "x"}) is None)

    print("doctrine model — factors and readiness contract:")
    fc = [f for f in subk_disguised.FACTORS if f["id"].startswith("DS.fc.")]
    check("exactly 10 facts-and-circumstances factors (Reg. 1.707-3(b)(2))", len(fc) == 10)
    check("every factor cites a 1.707- subsection", all("1.707" in f["reg"] for f in subk_disguised.FACTORS))
    f0 = subk_disguised.empty_frame()
    r0 = subk_disguised.readiness(f0)
    check("empty frame is NOT ready (no contribution/distribution)", r0["ready"] is False)
    check("empty frame correctly says presumption unreachable", r0["presumption_reachable"] is False)

    print("scope gate — picks the right doctrine:")
    scope_ds = si.scope_check("the contribution and a distribution within two years constituted a sale")
    check("disguised-sale signals route to the disguised-sale doctrine",
          scope_ds["in_scope"] and scope_ds["doctrine"] == subk_disguised.DOCTRINE)
    scope_unrelated = si.scope_check("my client got a speeding ticket")
    check("unrelated text is out of scope across all doctrines", scope_unrelated["in_scope"] is False)

    print("provision detection — phrase -> traceable quote:")
    text = ("The contribution and the distribution occurred within two years. The Agreement contains "
            "a binding obligation to distribute, and a preferred return is provided.")
    fr = si.detect_provisions(text, source="agreement", doctrine=subk_disguised)
    check("detects the 2-year window", fr["fields"]["transfers_within_two_years"]["value"] is True)
    check("detects the binding agreement", fr["fields"]["binding_agreement"]["value"] is True)
    check("detects the preferred-return exception", fr["fields"]["preferred_return"]["value"] is True)
    check("a detected fact carries its source sentence as the quote",
          "two years" in fr["fields"]["transfers_within_two_years"]["quote"].lower())

    print("readiness — reports presumption + reachable F&C, names what's blocked:")
    form = {
        "contribution_described": "Contributing partner transferred Blackacre on Jan 1",
        "distribution_described": "Cash of $1M distributed to Contributing partner on Jun 1",
        "transfers_within_two_years": True,
        "legally_enforceable_right": True,
        "entrepreneurial_risk": False,
        "binding_agreement": True,
    }
    r = subk_disguised.readiness(si.frame_from_form(form, doctrine=subk_disguised))
    check("ready when minimum + presumption + ≥3 F&C are reachable", r["ready"] is True)
    check("presumption is reachable", r["presumption_reachable"] is True)
    check("at least the 3 supplied F&C factors are reachable",
          set(r["fc_factors_reachable"]) >= {"DS.fc.2", "DS.fc.3", "DS.fc.8"})
    check("an un-supplied F&C factor is correctly reported as blocked",
          any(b["id"] == "DS.fc.6" for b in r["factors_blocked"]))

    print("Layer A bundle — disguised-sale law only (no SEE factors leak in):")
    bundle = subk_llm.build_bundle(si.frame_from_form(form, doctrine=subk_disguised),
                                   {"status": "verified_external"}, doctrine=subk_disguised)
    check("bundle has the disguised-sale root cite", bundle["doctrine"] == subk_disguised.DOCTRINE)
    check("bundle carries DS.* LAW ids", any("LAW:DS." in i["id"] for i in bundle["items"]))
    check("bundle does NOT carry SEE factor ids", not any("LAW:EE." in i["id"] for i in bundle["items"]))

    print("doctrine-aware framing — system prompt + interview are NOT hard-coded to SEE:")
    sp_see = subk_llm.system_prompt(subk_see)
    sp_ds = subk_llm.system_prompt(subk_disguised)
    check("SEE system prompt names the SEE test", "substantial-economic-effect" in sp_see)
    check("DS system prompt names the DS test (not SEE)",
          "disguised-sale" in sp_ds and "substantial-economic-effect" not in sp_ds)
    check("DS prompt uses a 1.707 example tag, not 1.704", "1.707" in sp_ds and "1.704" not in sp_ds)
    check("DS prompt forbids the DS ultimate conclusion (not SEE's)",
          "disguised sale" in sp_ds and "HAS substantial economic effect" not in sp_ds)
    check("the universal closure rule is in both", all("TRACE ENTIRELY TO THE PROVIDED BUNDLE" in s
                                                       for s in (sp_see, sp_ds)))
    check("SEE declares its own interview script", isinstance(subk_see.INTERVIEW_SCRIPT, list)
          and len(subk_see.INTERVIEW_SCRIPT) >= 4)
    check("DS declares its own interview script with the 10 F&C fields",
          {field for field, _, _ in subk_disguised.INTERVIEW_SCRIPT}
              >= {"contribution_described", "distribution_described", "transfers_within_two_years",
                  "legally_enforceable_right", "binding_agreement", "guaranteed_payment"})
    check("interview script only references real doctrine fields (no typos)",
          all(field in subk_disguised.FRAME_FIELDS for field, _, _ in subk_disguised.INTERVIEW_SCRIPT)
          and all(field in subk_see.FRAME_FIELDS for field, _, _ in subk_see.INTERVIEW_SCRIPT))

    print("Layer B closure under the new doctrine — grounded analysis is ACCEPTED:")
    good = {
        "propositions": [
            {"text": "The contribution + distribution within 2 years triggers the presumed-sale "
                     "rule [LAW:DS.two_year], with [FACT:transfers_within_two_years].",
             "type": "LEGAL", "supports": ["LAW:DS.two_year", "FACT:transfers_within_two_years"]},
        ],
        "augmentations": [], "gaps": [], "ultimate_question": "Is it a disguised sale?",
    }
    v = subk_llm.layer_b_verify(good, bundle["ids"])
    check("a fully-grounded disguised-sale proposition is CLOSED", v["closed"] is True)

    print(f"\nALL {passed} DISGUISED-SALE CHECKS PASSED")


if __name__ == "__main__":
    main()
