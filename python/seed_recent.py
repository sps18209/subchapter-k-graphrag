"""
seed_recent.py — the 2024-2025 recent-developments layer.

Only encodes what was VERIFIED against current sources (June 2026). Each node's
synthesis carries a verification tag:
  [VERIFIED]            confirmed against IRS / Federal Register / firm analyses
  [VERIFIED-superseded] real but revoked/removed in 2025 (see supersession edges)
  [REPORTED]            underlying item real, a specific cite/notice number unconfirmed
  [CONTEXT]             enforcement program or form mechanic, not legal authority

This layer demonstrates the currency + supersession gate on live recent law,
including catching the author's own graph going stale (199A) and a real revoke chain.

tier 5 = sub-regulatory form / program. Edge types add: amends, enacts, supersedes.
"""

NODES = [
    # ---- 2025 legislation ----
    ("obbba", "provision", "P.L. 119-21 (OBBBA)", "One Big Beautiful Bill Act", 1, None,
     "[VERIFIED] Signed July 4, 2025. Made 199A permanent, restored EBITDA-based 163(j), and enacted new 1062.",
     ["OBBBA", "P.L. 119-21", "2025 tax act", "permanent"], "2025-07-04", None),
    ("s1062", "provision", "IRC 1062", "Qualified farmland installment election", 1, None,
     "[VERIFIED] OBBBA election to pay the net income tax on gain from a sale of qualified farmland to a qualified farmer in 4 equal annual installments (a payment-deferral mechanism, NOT a gain exclusion); IRS implemented via Form 1062 (Dec. 2025). Effective for sales in tax years beginning after July 4, 2025.",
     ["1062", "farmland", "installment", "Form 1062", "payment deferral"], "2025-07-04", None),
    ("n2026_03", "ruling", "Notice 2026-3", "Sec. 1062 farmland election — estimated-tax relief", 4, None,
     "[REPORTED] Estimated-tax relief tied to the §1062 farmland installment election: a taxpayer may exclude 75% of the applicable net tax liability from required annual estimated payments (§§6654/6655); penalty relief is automatic for compliant returns or via Form 843 annotated 'Abatement requested pursuant to Notice 2026-3'. Reported via practitioner sources; primary IRB cite to confirm.",
     ["2026-3", "1062", "estimated tax", "6654", "6655", "farmland", "Form 843"], "2026-01-01", None),

    # ---- CAMT / partnership: Notice 2025-28 + its three methods ----
    ("n2025_28", "ruling", "Notice 2025-28", "CAMT-partnership interim guidance", 4, None,
     "[VERIFIED] Issued July 29, 2025 (IRB 2025-34, 316; Aug 18, 2025); partially withdraws the 2024 CAMT proposed regs for partnerships and gives corporate partners simplified AFSI methods. Confirmed still operative by Notice 2026-7.",
     ["2025-28", "CAMT", "AFSI", "partnership", "56A"], "2025-07-29", None),
    ("n2025_28_td", "ruling", "Notice 2025-28 (top-down election)", "CAMT top-down election", 4, None,
     "[VERIFIED] Lets a corporate partner treat 80% of its own financial-statement income as its distributive share of AFSI, avoiding bottom-up math.",
     ["top-down", "80%", "CAMT", "distributive share"], "2025-07-29", None),
    ("n2025_28_ti", "ruling", "Notice 2025-28 (taxable-income election)", "CAMT taxable-income election", 4, None,
     "[VERIFIED] A simplified path mapping AFSI to regular taxable income for partners with a small interest.",
     ["taxable-income election", "small interest", "CAMT", "minority partner"], "2025-07-29", None),
    ("n2025_28_fk", "ruling", "Notice 2025-28 (full Subchapter K method)", "CAMT full Subchapter K method", 4, None,
     "[VERIFIED] Aligns the CAMT treatment of partnership contributions and distributions with regular Subchapter K rules.",
     ["full subchapter K", "contributions", "distributions", "CAMT"], "2025-07-29", None),

    # ---- CAMT interim-notice stack post-dating 2025-28 + the underlying proposed regs ----
    # (added June 2026 from primary-source research: the corporate AMT runs entirely on
    #  stacked interim notices — no final regs exist as of early 2026.)
    ("n2025_27", "ruling", "Notice 2025-27", "CAMT applicable-corporation interim guidance", 4, None,
     "[VERIFIED] CAMT interim guidance, IRB 2025-26 (June 23, 2025); part of the stacked interim-notice regime for the corporate AMT (§56A) pending proposed/final regulations. Specific operative content to confirm against the notice.",
     ["2025-27", "CAMT", "56A", "applicable corporation", "interim"], "2025-06-23", None),
    ("n2025_46", "ruling", "Notice 2025-46", "CAMT additional interim guidance", 4, None,
     "[VERIFIED] CAMT interim guidance, IRB 2025-43 (Oct 20, 2025); continues the stacked interim-notice regime for the corporate AMT (§56A). Later modified by Notice 2026-7.",
     ["2025-46", "CAMT", "56A", "interim"], "2025-10-20", None),
    ("n2025_49", "ruling", "Notice 2025-49", "CAMT additional interim guidance", 4, None,
     "[VERIFIED] CAMT interim guidance (irs.gov drop n-25-49), issued late 2025 after Notice 2025-46; reiterates that a corporate partner takes into account only its distributive share of partnership AFSI under §56A(c)(2)(D)(i), and that Treasury intends to partially withdraw the Sept 2024 CAMT proposed regs and reissue. Exact IRB cite/date to confirm. Later modified by Notice 2026-7.",
     ["2025-49", "CAMT", "56A", "distributive share", "AFSI", "partnership"], "2025-11-01", None),
    ("n2026_07", "ruling", "Notice 2026-7", "CAMT additional interim guidance", 4, None,
     "[VERIFIED] Additional CAMT interim guidance (irs.gov drop n-26-07), Part III of the IRB; MODIFIES (does not withdraw) Notices 2025-46 and 2025-49, transition/applicability Feb 18, 2026. Confirms Notice 2025-28 remains operative and that NO final CAMT regulations exist as of early 2026.",
     ["2026-7", "CAMT", "56A", "interim"], "2026-02-18", None),
    ("camt_propreg", "regulation", "Prop. Treas. Reg. 1.56A (REG-112129-23)", "CAMT proposed regs — partnership AFSI", 3, None,
     "[VERIFIED] CAMT proposed regulations, 89 FR 75062 (Sept 13, 2024), RIN 1545-BQ84. Contains Subchapter-K-specific Prop. §1.56A-5 (a partner's distributive share of partnership AFSI; bottom-up / applicable method) and Prop. §1.56A-20 (applying Part II Subchapter K principles via a deferred-sale method for §721(a) contributions). PROPOSED, not final; Treasury intends to partially withdraw and reissue. The interim notices govern in the meantime.",
     ["56A", "CAMT", "proposed reg", "REG-112129-23", "1.56A-5", "1.56A-20", "AFSI", "partnership"], "2024-09-13", None),

    # ---- Form 7217 ----
    ("form7217", "ruling", "Form 7217", "Partner property-distribution report", 5, None,
     "[VERIFIED] TY2024+; any partner receiving a §732 property distribution files a separate Form 7217 per distribution date (money and marketable-securities-as-money excluded).",
     ["7217", "property distribution", "732", "reporting"], "2024-01-01", None),

    # ---- Basis-shifting enforcement cluster (the real revoke/remove chain) ----
    ("rr2024_14", "ruling", "Rev. Rul. 2024-14", "Basis-shifting economic substance", 4, None,
     "[VERIFIED-superseded] Applied the §7701(o) economic substance doctrine to related-party basis-shifting via §§732(b)/734(b)/743(b); REVOKED in 2025 by Notice 2025-34.",
     ["2024-14", "economic substance", "basis shifting", "7701(o)", "revoked"], "2024-06-17", None),
    ("n2024_54", "ruling", "Notice 2024-54", "Basis-shifting proposed-reg notice", 4, None,
     "[VERIFIED-superseded] Announced forthcoming basis-shifting regs; withdrawn by Notice 2025-23 and revoked by Notice 2025-34.",
     ["2024-54", "basis shifting", "withdrawn"], "2024-06-17", None),
    ("reg6011_18", "regulation", "Treas. Reg. 1.6011-18", "Basis-shifting transaction of interest", 3, None,
     "[VERIFIED] Final 1/14/2025 (TD 10028, 90 FR 2972) designating related-party basis-shifting as a reportable transaction of interest. Notice 2025-23 (Apr 2025) announced its removal and waived disclosure penalties, but the section REMAINS CODIFIED in the eCFR (current through 6/12/2026) with no removing Treasury Decision in effect — still on the books, though effectively unenforced. Corrected June 2026 against the official eCFR after the prior seed wrongly recorded a 3/6/2026 removal.",
     ["1.6011-18", "transaction of interest", "TOI", "reportable", "codified", "eCFR"], "2025-01-14", None),
    ("n2025_23", "ruling", "Notice 2025-23", "Removes basis-shifting TOI reg", 4, None,
     "[VERIFIED] Issued April 17, 2025; announced removal of Treas. Reg. 1.6011-18, waived disclosure penalties, and withdrew Notice 2024-54.",
     ["2025-23", "removal", "penalty relief", "TOI"], "2025-04-17", None),
    ("n2025_34", "ruling", "Notice 2025-34", "Revokes 2024-14 and 2024-54", 4, None,
     "[VERIFIED] 2025 notice revoking Rev. Rul. 2024-14 and Notice 2024-54 with penalty relief.",
     ["2025-34", "revokes", "2024-14", "2024-54"], "2025-05-01", None),

    # ---- Clean energy elect-out ----
    ("s761a_ce", "regulation", "IRC 761(a) / Treas. Reg. 1.761-2", "Clean-energy elect-out of Subch. K", 3, None,
     "[VERIFIED] Final regs (late 2024) let qualifying unincorporated clean-energy co-ownership arrangements elect out of Subchapter K to ease §6417 direct-pay credit collection.",
     ["761(a)", "elect out", "clean energy", "6417", "direct pay"], "2024-11-01", None),
    ("s6417", "provision", "IRC 6417", "Elective (direct) payment of credits", 1, None,
     "[VERIFIED] IRA-2022 elective/direct-pay mechanism for certain energy credits; interacts with the §761(a) clean-energy elect-out.",
     ["6417", "direct pay", "elective payment", "energy credit"], "2023-01-01", None),

    # ---- Reported (underlying real, specific cite to confirm) ----
    ("dpl_rules", "regulation", "Disregarded Payment Loss (DPL) rules", "Cross-border DPL tracking", 3, None,
     "[REPORTED] Final 2025 regs on disregarded payment losses tied to the dual-consolidated-loss regime (§1503(d)); a reported sunset via Notice 2025-44 folding DPL into DCL logic is UNCONFIRMED — verify the notice number.",
     ["DPL", "disregarded payment loss", "DCL", "1503(d)", "cross-border"], "2025-01-01", None),

    # ---- Context (enforcement program / form mechanic, not authority) ----
    ("lpc_ai", "ruling", "Large Partnership Compliance (AI/ML)", "AI-assisted LPC audit selection", 5, None,
     "[CONTEXT] IRS Large Partnership Compliance program using ML to select large, multi-tiered passthroughs for audit; an enforcement program, not legal authority. A 'Rapid LPC Field Audit' expansion is reported to have stalled on budget/staffing — UNCONFIRMED.",
     ["LPC", "large partnership", "AI audit", "enforcement"], "2024-01-01", None),
    ("k23_dfe", "ruling", "Schedules K-2/K-3 domestic filing exception", "K-2/K-3 small-partnership relief", 5, None,
     "[CONTEXT] Domestic filing exception and partner-notification rules let qualifying small/domestic partnerships skip K-2/K-3; specific 2025 threshold and 'Part XII QDD' changes UNCONFIRMED — verify against current instructions.",
     ["K-2", "K-3", "domestic filing exception", "QDD", "Part XII"], "2024-01-01", None),
]

# Edges: amends / enacts / supersedes (src acts on dst), plus relationships.
EDGES = [
    ("obbba", "s199A", "amends", None, None, None, "made 199A permanent (no 2025 sunset)"),
    ("obbba", "s163j", "amends", None, None, None, "restored EBITDA-based ATI"),
    ("obbba", "s1062", "enacts", None, None, None, "created 1062"),

    ("n2025_28", "n2025_28_td", "cross_references", None, None, None, "method of the notice"),
    ("n2025_28", "n2025_28_ti", "cross_references", None, None, None, "method of the notice"),
    ("n2025_28", "n2025_28_fk", "cross_references", None, None, None, "method of the notice"),
    ("n2025_28_fk", "s721", "cross_references", None, None, None, "aligns contributions with Subch. K"),
    ("n2025_28", "s704b", "cross_references", None, None, None, "distributive-share AFSI"),

    # the CAMT interim-notice stack + the proposed regs it implements/withdraws
    ("n2025_27", "n2025_28", "cross_references", None, None, None, "earlier CAMT interim notice"),
    ("n2025_46", "n2025_28", "cross_references", None, None, None, "continues the interim-notice stack"),
    ("n2025_49", "n2025_46", "cross_references", None, None, None, "continues the interim-notice stack"),
    ("n2026_07", "n2025_49", "amends", None, None, None, "modifies (does not withdraw)"),
    ("n2026_07", "n2025_46", "amends", None, None, None, "modifies (does not withdraw)"),
    ("n2026_07", "n2025_28", "cross_references", None, None, None, "confirms 2025-28 remains operative"),
    ("n2025_28", "camt_propreg", "amends", None, None, None, "partially withdraws the 2024 CAMT proposed regs for partnerships"),
    ("n2025_49", "camt_propreg", "cross_references", None, None, None, "Treasury intends partial withdrawal/reissue"),
    ("camt_propreg", "s721", "cross_references", None, None, None, "Prop. 1.56A-20 deferred-sale method for 721(a) contributions"),
    ("camt_propreg", "s704b", "cross_references", None, None, None, "Prop. 1.56A-5 partner distributive share of AFSI"),
    ("n2026_03", "s1062", "cross_references", None, None, None, "estimated-tax relief for the 1062 farmland election"),

    ("form7217", "s732", "implements", None, None, None, "reports §732 distributed-property basis"),
    ("form7217", "s731c", "cross_references", None, None, None, "marketable-securities-as-money excluded"),

    # the real revoke / remove chain
    ("rr2024_14", "s743b", "interprets", None, None, None, "economic substance on basis adjustment"),
    ("rr2024_14", "s734b", "interprets", None, None, None, "economic substance on basis adjustment"),
    ("reg6011_18", "s743b", "interprets", None, None, None, "designated basis-shifting reportable"),
    # Notice 2025-23 ANNOUNCED removal of 1.6011-18 and waived penalties, but the section
    # is still codified per the eCFR (6/12/2026) — so this is context, not supersession.
    ("n2025_23", "reg6011_18", "informs", None, None, None, "announced removal & waived disclosure penalties; section still codified per eCFR 6/12/2026"),
    ("n2025_23", "n2024_54", "supersedes", None, None, None, "withdraws the notice"),
    ("n2025_34", "rr2024_14", "supersedes", None, None, None, "revokes the ruling"),
    ("n2025_34", "n2024_54", "supersedes", None, None, None, "revokes the notice"),

    ("s761a_ce", "s6417", "cross_references", None, None, None, "elect-out eases direct pay"),
    ("s761a_ce", "s721", "cross_references", None, None, None, "elect-out of Subchapter K"),
    ("dpl_rules", "s704b", "cross_references", None, None, None, "passthrough cross-border losses"),
]
