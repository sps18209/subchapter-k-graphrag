#!/usr/bin/env python3
"""
test_subk_analyze.py — the substantial-economic-effect analyzer's RELIABILITY CONTRACT, offline.

Asserts the deterministic guarantees: scope is gated, provisions are detected from text with a
traceable quote, the fact-frame reports exactly which factors it can and cannot reach, and the
authority checklist cites real reg subsections. No network, no model.

    python test_subk_analyze.py
"""
import subk_see
import subk_intake as si

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    print("doctrine model:")
    check("empty frame is NOT ready (no allocation at issue)", subk_see.readiness(subk_see.empty_frame())["ready"] is False)
    check("every factor cites Treas. Reg. 1.704-1", all("1.704-1" in f["reg"] for f in subk_see.FACTORS))
    check("authority cites are de-duped and rooted", subk_see.ROOT_CITE in subk_see.authority_cites())

    print("scope gate:")
    check("a §704(b) allocation question is in scope",
          si.scope_check("does this special allocation of depreciation have economic effect under 704(b)")["in_scope"])
    check("an unrelated matter is declined",
          si.scope_check("my client got a speeding ticket in Missouri")["in_scope"] is False)

    print("deterministic provision detection (phrase -> traceable quote):")
    text = ("The Agreement maintains capital accounts in accordance with Treas. Reg. "
            "1.704-1(b)(2)(iv). The Agreement contains a qualified income offset. No partner has "
            "a deficit restoration obligation.")
    fr = si.detect_provisions(text, source="agreement")
    check("detects qualified income offset", fr["fields"]["qualified_income_offset"]["value"] is True)
    check("detects capital-account maintenance", fr["fields"]["capital_account_maintenance"]["value"] is True)
    check("detects deficit-restoration language", fr["fields"]["deficit_restoration_obligation"]["value"] is True)
    check("a detected fact carries a verbatim quote from the source",
          "qualified income offset" in fr["fields"]["qualified_income_offset"]["quote"].lower())

    print("the contract: reports what it CAN and CANNOT reach:")
    form = {"allocation_at_issue": "99% of depreciation to Partner A",
            "qualified_income_offset": True, "capital_account_balances": "A: 100k, B: 100k"}
    r = subk_see.readiness(si.frame_from_form(form))
    check("with allocation + QIO + balances, the ALTERNATE economic-effect path is reachable",
          "EE.alt" in r["economic_effect_paths_reachable"])
    check("substantiality is correctly reported as BLOCKED (no tax-motivation facts)",
          any(b["id"] == "SUB.shift" for b in r["factors_blocked"]))
    check("the block names the missing field",
          any("tax_motivation" in b["missing"] for b in r["factors_blocked"]))

    print("light path accepts only the closed vocabulary:")
    fr2 = si.frame_from_form({"allocation_at_issue": "x", "made_up_field": "ignored"})
    check("unknown keys are ignored", "made_up_field" not in fr2["fields"])
    check("known key is taken with attorney-input source", fr2["fields"]["allocation_at_issue"]["source"] == "attorney input")

    print("anonymized party intake (codes never real names):")
    parties = si.parse_parties("RoSm:contributing, ToJo:service")
    check("parses codes + roles", parties == [{"code": "RoSm", "role": "contributing"},
                                              {"code": "ToJo", "role": "service"}])
    check("roster text is codes only", si.roster_text(parties) == "RoSm (contributing); ToJo (service)")
    check("a real name is flagged as identifying", si.looks_identifying("Robert Smith") is True)
    check("a short code is not flagged", si.looks_identifying("RoSm") is False)
    fr = si.frame_from_form({"allocation_at_issue": "x", "parties": si.roster_text(parties)})
    check("the roster enters the frame as a fact field", fr["fields"]["parties"]["value"] == "RoSm (contributing); ToJo (service)")

    print("role-based representation (parties are what they ARE, not names/codes):")
    used = set()
    check("a partner role becomes a functional label", si.role_label("contributing", used) == "Contributing partner")
    check("a recurring role is disambiguated", si.role_label("contributing", used) == "Contributing partner 2")
    check("a non-partner role is kept as-is", si.role_label("plaintiff", set()) == "Plaintiff")
    import subk_analyze
    import redact
    rd = redact.Redactor()
    labels = subk_analyze._parties_to_roster([("John Doe", "contributing"), ("handle", "service")], rd)
    check("roster labels are ROLES, not the name/handle", labels == ["Contributing partner", "Service partner"])
    check("a real name scrubs to its ROLE label (not a code)",
          rd.redact("John Doe contributed land") == "Contributing partner contributed land")

    print(f"\nALL {passed} ANALYZER-CONTRACT CHECKS PASSED")


if __name__ == "__main__":
    main()
