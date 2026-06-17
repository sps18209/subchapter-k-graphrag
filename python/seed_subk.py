"""
seed_subk.py — the Subchapter K corpus (Layer 1 structural + seeded Layer 2 semantic).

Definition-centric: TERM nodes are hubs; provisions/regs/rulings/cases attach by typed
edges. `synthesis` strings are ORIGINAL plain-law glosses (facts are not copyrightable);
no Thomson Reuters / McKee prose is stored. Citations point only to PRIMARY authority.
Everything here is unverified SEED for attorney review, not citable ground.

authority_tier: 1 statute, 3 regulation, 4 ruling / precedential case.
term_subtype:   statutory | interpretive | computed   (terms only).
"""

# ---- NODES -------------------------------------------------------------------
# (id, ntype, citation, label, tier, term_subtype, synthesis, tags, valid_from, valid_to)
NODES = [
    # ---- TERMS (hubs) ----
    ("t_outside_basis", "term", "Outside basis", "Partner's basis in its interest", 1, "computed",
     "Cash + adjusted basis of contributed property + share of liabilities, adjusted annually; never below zero.",
     ["basis", "outside basis", "distribution", "loss limitation"], None, None),
    ("t_inside_basis", "term", "Inside basis", "Partnership's basis in its assets", 1, "computed",
     "Carryover from contributions; adjustable under §743(b)/§734(b) only with a §754 election.",
     ["basis", "inside basis", "754", "step-up"], None, None),
    ("t_capital_account", "term", "704(b) book capital account", "Economic-equity capital account", 1, "computed",
     "Maintained under Treas. Reg. 1.704-1(b)(2)(iv); measures economic equity; may be negative; distinct from tax basis and FMV.",
     ["capital account", "704(b)", "substantial economic effect", "book"], None, None),
    ("t_partnership_liability", "term", "Partnership liability", "Recourse vs nonrecourse liability", 1, "interpretive",
     "Recourse if a partner bears the economic risk of loss; nonrecourse if none does. A partner's share is part of outside basis under §752.",
     ["liability", "recourse", "nonrecourse", "752"], None, None),
    ("t_hot_assets", "term", "Hot assets", "Unrealized receivables & inventory", 1, "statutory",
     "Unrealized receivables (§751(c)) and inventory (§751(d)); generate ordinary income on a sale of an interest or a disproportionate distribution.",
     ["hot assets", "751", "ordinary income", "unrealized receivables", "inventory"], None, None),
    ("t_disguised_sale", "term", "Disguised sale", "Contribution that is in substance a sale", 1, "interpretive",
     "A contribution plus a related transfer that in substance is a sale; tested under §707 and the 1.707 regs; two-year presumption.",
     ["disguised sale", "707", "two-year", "qualified liability"], None, None),
    ("t_built_in_gain", "term", "Built-in gain (704(c))", "Precontribution gain/loss", 1, "statutory",
     "Difference between FMV and adjusted basis of contributed property at contribution; allocated back to the contributing partner under §704(c).",
     ["built-in gain", "704(c)", "ceiling rule", "remedial", "curative"], None, None),
    ("t_754_election", "term", "Section 754 election", "Inside-basis adjustment election", 1, "statutory",
     "Election enabling inside-basis adjustments under §743(b) (transfers) and §734(b) (distributions); generally irrevocable.",
     ["754", "election", "743(b)", "734(b)"], None, None),
    ("t_partnership_status", "term", "Partnership status", "Whether a partnership exists", 1, "interpretive",
     "Whether an arrangement is a partnership for tax purposes; a facts-and-circumstances / intent inquiry.",
     ["partnership", "existence", "intent", "Culbertson", "Luna"], None, None),
    ("t_marketable_securities", "term", "Marketable securities (731(c))", "Securities treated as money", 1, "statutory",
     "Treated as money under §731(c) for distribution gain, reduced by the partner's share of built-in gain in the securities.",
     ["marketable securities", "731(c)", "money"], None, None),
    ("t_qualified_liability", "term", "Qualified liability", "Liability outside disguised-sale", 3, "statutory",
     "A liability (e.g., debt >2 years old encumbering contributed property) whose assumption does not by itself trigger the disguised-sale rules.",
     ["qualified liability", "707-5", "encumbered"], None, None),

    # ---- PROVISIONS (statute) ----
    ("s721", "provision", "IRC 721", "Nonrecognition on contribution", 1, None,
     "No gain or loss on a contribution of property for a partnership interest (subject to exceptions).",
     ["contribution", "nonrecognition", "721"], None, None),
    ("s721b", "provision", "IRC 721(b)", "Investment-company exception", 1, None,
     "Nonrecognition does not apply to a contribution to an investment company that diversifies; built-in GAIN only.",
     ["investment company", "diversification", "721(b)"], None, None),
    ("s722", "provision", "IRC 722", "Initial outside basis (contribution)", 1, None,
     "Initial outside basis = cash contributed + adjusted basis of contributed property (+ §721(b) gain).",
     ["722", "initial basis", "contribution"], None, None),
    ("s723", "provision", "IRC 723", "Initial inside basis (contribution)", 1, None,
     "Partnership's basis in contributed property = the contributor's adjusted basis (carryover).",
     ["723", "carryover", "inside basis"], None, None),
    ("s724", "provision", "IRC 724", "Character of contributed property", 1, None,
     "Preserves ordinary/capital character of contributed receivables, inventory, and capital-loss property for stated periods.",
     ["724", "character", "five-year"], None, None),
    ("s704b", "provision", "IRC 704(b)", "Allocations / substantial economic effect", 1, None,
     "Allocations are respected if they have substantial economic effect or match the partners' interests in the partnership.",
     ["704(b)", "allocation", "substantial economic effect"], None, None),
    ("s704c", "provision", "IRC 704(c)", "Built-in gain allocations", 1, None,
     "Built-in gain or loss on contributed property is allocated to the contributing partner.",
     ["704(c)", "built-in gain", "contributed property"], None, None),
    ("s704d", "provision", "IRC 704(d)", "Loss limitation", 1, None,
     "A partner's distributive share of loss is allowed only to the extent of outside basis; the excess is suspended.",
     ["704(d)", "loss limitation", "suspended loss"], None, None),
    ("s704d3", "provision", "IRC 704(d)(3)", "Charitable / FTC in basis limit (TCJA)", 1, None,
     "Charitable contributions and foreign taxes are inside the §704(d) limit; donated built-in-gain property reduces basis only by the property's basis share.",
     ["704(d)(3)", "charitable", "foreign tax", "TCJA"], "2018-01-01", None),
    ("s705", "provision", "IRC 705", "Basis adjustment rules", 1, None,
     "Umbrella rule for adjusting outside basis by income, contributions, liabilities, distributions, losses, and nondeductible items.",
     ["705", "basis adjustment"], None, None),
    ("s705a1A", "provision", "IRC 705(a)(1)(A)", "Increase: taxable income", 1, None,
     "Outside basis increases by the partner's distributive share of taxable income, including capital gain.",
     ["705(a)(1)(A)", "income", "increase"], None, None),
    ("s705a1B", "provision", "IRC 705(a)(1)(B)", "Increase: tax-exempt income", 1, None,
     "Outside basis increases by the partner's share of tax-exempt income.",
     ["705(a)(1)(B)", "tax-exempt", "increase"], None, None),
    ("s705a1C", "provision", "IRC 705(a)(1)(C)", "Increase: excess depletion", 1, None,
     "Outside basis increases by percentage depletion exceeding the basis of depletable property.",
     ["705(a)(1)(C)", "depletion", "increase"], None, None),
    ("s705a2A", "provision", "IRC 705(a)(2)(A)", "Decrease: losses", 1, None,
     "Outside basis decreases by the partner's distributive share of losses, including capital loss.",
     ["705(a)(2)(A)", "loss", "decrease"], None, None),
    ("s705a2B", "provision", "IRC 705(a)(2)(B)", "Decrease: nondeductible expense", 1, None,
     "Outside basis decreases by the partner's share of nondeductible, noncapital expenditures.",
     ["705(a)(2)(B)", "nondeductible", "decrease"], None, None),
    ("s705a3", "provision", "IRC 705(a)(3)", "Decrease: oil & gas depletion", 1, None,
     "Outside basis decreases by the partner's share of depletion on oil and gas property.",
     ["705(a)(3)", "depletion", "decrease"], None, None),
    ("s705b", "provision", "IRC 705(b)", "Alternative basis rule", 1, None,
     "When the general rule is impractical, basis may be figured as the partner's share of the partnership's adjusted basis in its property.",
     ["705(b)", "alternative", "proportionate"], None, None),
    ("s707", "provision", "IRC 707", "Partner-partnership transactions", 1, None,
     "Governs transactions between a partner and the partnership, including disguised sales and guaranteed payments.",
     ["707", "disguised sale", "guaranteed payment"], None, None),
    ("s707c", "provision", "IRC 707(c)", "Guaranteed payments", 1, None,
     "Payments fixed without regard to income are ordinary income to the partner and generally deductible by the partnership.",
     ["707(c)", "guaranteed payment", "ordinary"], None, None),
    ("s731", "provision", "IRC 731", "Gain/loss on distribution", 1, None,
     "A partner recognizes gain only if money distributed exceeds outside basis; no loss except in limited liquidations.",
     ["731", "distribution", "gain"], None, None),
    ("s731a1", "provision", "IRC 731(a)(1)", "Gain on excess distribution", 1, None,
     "Gain to the extent money (incl. marketable securities and liability relief) distributed exceeds outside basis; generally capital.",
     ["731(a)(1)", "excess distribution", "gain"], None, None),
    ("s731a2", "provision", "IRC 731(a)(2)", "Loss on liquidation only", 1, None,
     "No loss on a current distribution; loss only on liquidation receiving solely cash, receivables, and/or inventory.",
     ["731(a)(2)", "loss", "liquidation"], None, None),
    ("s731c", "provision", "IRC 731(c)", "Marketable securities as money", 1, None,
     "Marketable securities are treated as money for distribution gain, reduced by the partner's share of built-in gain.",
     ["731(c)", "marketable securities", "money"], None, None),
    ("s732", "provision", "IRC 732", "Basis of distributed property", 1, None,
     "Distributed-property basis carries over, capped at outside basis less money (§732(a)(2)); liquidation takes remaining basis (§732(b)).",
     ["732", "distributed property", "basis"], None, None),
    ("s733", "provision", "IRC 733", "Basis reduction on distribution", 1, None,
     "Outside basis is reduced (not below zero) by money distributed plus the basis of property distributed.",
     ["733", "distribution", "decrease"], None, None),
    ("s734b", "provision", "IRC 734(b)", "Inside-basis adjustment (distribution)", 1, None,
     "Partnership adjusts inside basis on a distribution if a §754 election is in effect or there is a substantial basis reduction.",
     ["734(b)", "inside basis", "distribution", "754"], None, None),
    ("s736", "provision", "IRC 736", "Retiring-partner payments", 1, None,
     "Liquidation payments to a retiring or deceased partner split between property payments (§736(b)) and other payments (§736(a)).",
     ["736", "retirement", "liquidation"], None, None),
    ("s741", "provision", "IRC 741", "Sale of a partnership interest", 1, None,
     "Sale of an interest yields capital gain or loss equal to amount realized less outside basis, subject to §751.",
     ["741", "sale", "capital gain"], None, None),
    ("s742", "provision", "IRC 742", "Basis of purchased interest", 1, None,
     "Initial outside basis of a purchased interest = cost (cash + property) plus share of liabilities.",
     ["742", "purchase", "cost basis"], None, None),
    ("s743b", "provision", "IRC 743(b)", "Inside-basis adjustment (transfer)", 1, None,
     "On a sale/exchange of an interest, with a §754 election or substantial built-in loss, inside basis is adjusted for the transferee.",
     ["743(b)", "transfer", "step-up", "754"], None, None),
    ("s751", "provision", "IRC 751", "Hot assets", 1, None,
     "Recharacterizes as ordinary income the partner's share of unrealized receivables and inventory on a sale or disproportionate distribution.",
     ["751", "hot assets", "ordinary income"], None, None),
    ("s751b", "provision", "IRC 751(b)", "Disproportionate distributions", 1, None,
     "A distribution that shifts a partner's interest in hot assets is treated as a deemed sale producing ordinary income.",
     ["751(b)", "disproportionate", "ordinary income"], None, None),
    ("s752", "provision", "IRC 752", "Treatment of liabilities", 1, None,
     "A partner's share of liabilities is part of outside basis: an increase is a deemed contribution, a decrease a deemed distribution.",
     ["752", "liability", "deemed contribution", "deemed distribution"], None, None),
    ("s752a", "provision", "IRC 752(a)", "Liability increase = contribution", 1, None,
     "An increase in a partner's share of liabilities is treated as a contribution of money, raising outside basis.",
     ["752(a)", "liability increase", "increase"], None, None),
    ("s752b", "provision", "IRC 752(b)", "Liability decrease = distribution", 1, None,
     "A decrease in a partner's share of liabilities is treated as a distribution of money, lowering outside basis.",
     ["752(b)", "liability decrease", "decrease"], None, None),
    ("s754", "provision", "IRC 754", "Optional basis-adjustment election", 1, None,
     "Election that turns on the inside-basis adjustments of §743(b) and §734(b); once made, generally irrevocable.",
     ["754", "election", "irrevocable"], None, None),
    ("s755", "provision", "IRC 755", "Allocation of basis adjustment", 1, None,
     "Allocates a §743(b) or §734(b) adjustment among partnership assets by relative built-in gain and loss.",
     ["755", "allocation", "adjustment"], None, None),
    ("s737", "provision", "IRC 737", "Precontribution gain on distribution", 1, None,
     "A distribution to a partner who contributed 704(c) property within 7 years can trigger recognition of precontribution gain.",
     ["737", "seven-year", "704(c)", "mixing bowl"], None, None),
    ("s709", "provision", "IRC 709", "Organizational & syndication expenses", 1, None,
     "Organizational expenses may be amortized; syndication expenses must be capitalized and are not amortizable.",
     ["709", "organizational", "syndication"], None, None),
    ("s1012", "provision", "IRC 1012", "Cost basis", 1, None,
     "Basis of purchased property is its cost.", ["1012", "cost"], None, None),
    ("s351e", "provision", "IRC 351(e)", "Investment-company definition", 1, None,
     "Defines the investment-company concept imported into §721(b).", ["351(e)", "investment company"], None, None),
    ("s163j", "provision", "IRC 163(j)", "Business interest limitation", 1, None,
     "Deductible business interest limited to interest income plus 30% of adjusted taxable income; OBBBA restored the more favorable EBITDA-based ATI for years after 2024.",
     ["163(j)", "interest", "limitation", "EBITDA", "OBBBA"], "2018-01-01", None),
    ("s199A", "provision", "IRC 199A", "Qualified business income deduction", 1, None,
     "Up to a 20% deduction for qualified business income from a passthrough; made PERMANENT by OBBBA (P.L. 119-21), with expanded phase-in thresholds and a $400 minimum (199A(i)).",
     ["199A", "QBI", "passthrough deduction", "permanent", "OBBBA"], "2018-01-01", None),
    ("s1061", "provision", "IRC 1061", "Carried-interest holding period", 1, None,
     "Three-year holding period for long-term capital gain on certain carried interests.",
     ["1061", "carried interest", "three-year"], None, None),
    ("s7704", "provision", "IRC 7704", "Publicly traded partnerships", 1, None,
     "A publicly traded partnership is taxed as a C-corp unless 90% or more of income is qualifying passive income.",
     ["7704", "PTP", "publicly traded"], None, None),

    # ---- REGULATIONS ----
    ("r1704_1", "regulation", "Treas. Reg. 1.704-1", "Allocations / SEE safe harbor", 3, None,
     "Capital-account maintenance plus the substantial-economic-effect safe harbor for allocations.",
     ["1.704-1", "capital account", "safe harbor"], None, None),
    ("r1704_2", "regulation", "Treas. Reg. 1.704-2", "Minimum gain / nonrecourse deductions", 3, None,
     "Rules for partnership minimum gain and the allocation of nonrecourse deductions.",
     ["1.704-2", "minimum gain", "nonrecourse deductions"], None, None),
    ("r1704_3", "regulation", "Treas. Reg. 1.704-3", "704(c) allocation methods", 3, None,
     "Traditional, traditional-with-curative, and remedial methods; the ceiling rule.",
     ["1.704-3", "traditional", "curative", "remedial", "ceiling rule"], None, None),
    ("r1707_3", "regulation", "Treas. Reg. 1.707-3", "Disguised-sale general rule", 3, None,
     "General disguised-sale test and the two-year presumption.",
     ["1.707-3", "disguised sale", "two-year"], None, None),
    ("r1707_4", "regulation", "Treas. Reg. 1.707-4", "Disguised-sale exceptions", 3, None,
     "Guaranteed payments, preferred returns, operating cash flow, and preformation reimbursements that are not disguised sales.",
     ["1.707-4", "preferred return", "operating cash flow", "preformation"], None, None),
    ("r1707_5", "regulation", "Treas. Reg. 1.707-5", "Liabilities & qualified liabilities", 3, None,
     "Liability assumptions, qualified liabilities, and debt-financed distributions; current rules apply to transfers on/after Oct 4, 2019.",
     ["1.707-5", "qualified liability", "debt-financed distribution"], "2019-10-04", None),
    ("r1752_1", "regulation", "Treas. Reg. 1.752-1", "Recourse vs nonrecourse definitions", 3, None,
     "Defines recourse and nonrecourse liabilities for partnership tax purposes.",
     ["1.752-1", "recourse", "nonrecourse", "definition"], None, None),
    ("r1752_2", "regulation", "Treas. Reg. 1.752-2", "Recourse liability allocation", 3, None,
     "Allocates recourse liabilities to the partner who bears the economic risk of loss.",
     ["1.752-2", "recourse", "economic risk of loss"], None, None),
    ("r1752_3", "regulation", "Treas. Reg. 1.752-3", "Nonrecourse liability allocation", 3, None,
     "Three-tier allocation of nonrecourse liabilities: minimum gain, 704(c) gain, then profits.",
     ["1.752-3", "nonrecourse", "three-tier", "minimum gain"], None, None),
    ("r1751_1", "regulation", "Treas. Reg. 1.751-1", "Hot-asset computation", 3, None,
     "Mechanics for computing ordinary income from hot assets on sales and disproportionate distributions.",
     ["1.751-1", "hot assets"], None, None),
    ("r1731_2", "regulation", "Treas. Reg. 1.731-2", "Marketable securities as money", 3, None,
     "Implements §731(c): which securities count and the built-in-gain reduction.",
     ["1.731-2", "marketable securities"], None, None),
    ("r1736_1", "regulation", "Treas. Reg. 1.736-1", "Retirement-payment allocation", 3, None,
     "Allocates retiring-partner payments between §736(a) and §736(b).",
     ["1.736-1", "retirement"], None, None),
    ("r1709_2", "regulation", "Treas. Reg. 1.709-2", "Org / syndication definitions", 3, None,
     "Defines organizational expenses (amortizable) versus syndication expenses (capitalized).",
     ["1.709-2", "organizational", "syndication"], None, None),

    # ---- RULINGS / PROCEDURES ----
    ("rr84_52", "ruling", "Rev. Rul. 84-52", "GP-to-LP conversion; unitary basis", 4, None,
     "Conversion of a general to a limited partnership is not a taxable exchange; a partner has one unitary basis.",
     ["84-52", "conversion", "unitary basis"], None, None),
    ("rr99_5", "ruling", "Rev. Rul. 99-5", "Single-member LLC to partnership", 4, None,
     "Converting a disregarded single-member LLC to a partnership: treated as a sale/contribution with basis consequences.",
     ["99-5", "conversion", "disregarded entity"], None, None),
    ("rr99_6", "ruling", "Rev. Rul. 99-6", "Partnership to disregarded entity", 4, None,
     "Converting a partnership to a disregarded entity: deemed liquidating distribution then asset purchase.",
     ["99-6", "conversion", "liquidation"], None, None),
    ("rp93_27", "ruling", "Rev. Proc. 93-27", "Profits interest for services", 4, None,
     "Receipt of a partnership profits interest for services is generally not a taxable event.",
     ["93-27", "profits interest", "services"], None, None),
    ("rp2001_43", "ruling", "Rev. Proc. 2001-43", "Nonvested profits interest", 4, None,
     "Clarifies profits-interest treatment for substantially nonvested interests.",
     ["2001-43", "profits interest", "vesting"], None, None),

    # ---- CASES ----
    ("c_culbertson", "case", "Culbertson", "Partnership existence = intent", 4, None,
     "Whether a partnership exists turns on the parties' good-faith intent to join together to carry on a business.",
     ["Culbertson", "partnership", "intent"], None, None),
    ("c_luna", "case", "Luna v. Commissioner", "Multi-factor partnership test", 4, None,
     "Lists factors (agreement, control over income/capital, shared responsibilities, conduct) for whether a partnership exists.",
     ["Luna", "partnership", "factors"], None, None),
    ("c_canal", "case", "Canal Corp. v. Commissioner", "Debt-financed distribution recast", 4, None,
     "A leveraged distribution was recast as a disguised sale where the partner's indemnity lacked economic substance.",
     ["Canal", "disguised sale", "debt-financed", "indemnity"], None, None),
    ("c_tufts", "case", "Commissioner v. Tufts", "Nonrecourse debt in amount realized", 4, None,
     "Nonrecourse liability is included in amount realized even if it exceeds the property's value (Crane/Tufts line).",
     ["Tufts", "Crane", "nonrecourse", "amount realized"], None, None),
    ("c_azimzadeh", "case", "Azimzadeh v. Commissioner", "Records & partnership existence", 4, None,
     "Inadequate records shift the burden to the taxpayer; an unsubstantiated partnership was treated as a sole proprietorship.",
     ["Azimzadeh", "records", "burden", "partnership"], None, None),
]

# ---- EDGES -------------------------------------------------------------------
# (src, dst, etype, direction, seq, group, mechanism)
#   etypes: computes adjusts uses defines interprets informs implements cross_references cites overflow
E = []
def edge(src, dst, etype, direction=None, seq=None, group=None, mechanism=""):
    E.append((src, dst, etype, direction, seq, group, mechanism))

# Outside-basis computation DAG (ordered, with floor + overflow)
edge("s722", "t_outside_basis", "computes", "initialize", 0, "increase", "contributed: cash + adjusted basis")
edge("s742", "t_outside_basis", "computes", "initialize", 0, "increase", "purchased: cost + liabilities")
edge("s705a1A", "t_outside_basis", "adjusts", "increase", 1, "increase", "taxable income incl. capital gain")
edge("s705a1B", "t_outside_basis", "adjusts", "increase", 2, "increase", "tax-exempt income")
edge("s705a1C", "t_outside_basis", "adjusts", "increase", 3, "increase", "excess percentage depletion")
edge("s752a", "t_outside_basis", "adjusts", "increase", 4, "increase", "liability increase = deemed contribution")
edge("s733", "t_outside_basis", "adjusts", "decrease", 5, "distribution", "distributions: money + property basis")
edge("s752b", "t_outside_basis", "adjusts", "decrease", 6, "distribution", "liability decrease = deemed distribution")
edge("s705a2B", "t_outside_basis", "adjusts", "decrease", 7, "reduce", "nondeductible noncapital expense")
edge("s705a3", "t_outside_basis", "adjusts", "decrease", 8, "reduce", "oil & gas depletion")
edge("s705a2A", "t_outside_basis", "adjusts", "decrease", 9, "loss_limited", "distributive share of loss")
edge("s704d", "t_outside_basis", "uses", "constraint", None, "loss_limited", "loss allowed only to extent of basis")
edge("s705b", "t_outside_basis", "uses", "constraint", None, None, "alternative proportionate computation")
edge("t_outside_basis", "s731a1", "overflow", None, None, None, "distribution > basis => §731(a) gain")
edge("t_outside_basis", "s704d", "overflow", None, None, None, "loss > basis => §704(d) suspended")

# Inside-basis DAG
edge("s723", "t_inside_basis", "computes", "initialize", 0, None, "carryover from contribution")
edge("s743b", "t_inside_basis", "adjusts", None, None, None, "transferee step-up/down on sale of interest")
edge("s734b", "t_inside_basis", "adjusts", None, None, None, "adjustment on distribution")
edge("s743b", "s754", "uses", None, None, None, "requires §754 election (or substantial built-in loss)")
edge("s734b", "s754", "uses", None, None, None, "requires §754 election (or substantial basis reduction)")
edge("s755", "t_inside_basis", "uses", None, None, None, "allocates the adjustment among assets")

# Capital account
edge("r1704_1", "t_capital_account", "computes", "initialize", None, None, "maintenance rules 1.704-1(b)(2)(iv)")
edge("s704b", "t_capital_account", "uses", None, None, None, "SEE safe harbor keyed to capital accounts")

# defines (authority -> term)
edge("s751", "t_hot_assets", "defines")
edge("r1752_1", "t_partnership_liability", "defines")
edge("s704c", "t_built_in_gain", "defines")
edge("s754", "t_754_election", "defines")
edge("s731c", "t_marketable_securities", "defines")
edge("r1707_5", "t_qualified_liability", "defines")
edge("r1707_3", "t_disguised_sale", "defines")

# implements (reg -> statute)
for r, s in [("r1704_1", "s704b"), ("r1704_2", "s704b"), ("r1704_3", "s704c"),
             ("r1707_3", "s707"), ("r1707_4", "s707"), ("r1707_5", "s707"),
             ("r1752_1", "s752"), ("r1752_2", "s752"), ("r1752_3", "s752"),
             ("r1751_1", "s751"), ("r1731_2", "s731c"), ("r1736_1", "s736"), ("r1709_2", "s709")]:
    edge(r, s, "implements", mechanism="regulation implements statute")

# cross_references
for a, b in [("s722", "s723"), ("s731", "s732"), ("s732", "s733"), ("s731", "s733"),
             ("s741", "s751"), ("s736", "s751b"), ("s736", "s731"), ("s731c", "s751"),
             ("s704c", "s737"), ("s721", "s721b"), ("s721b", "s351e"), ("s721b", "s721"),
             ("s754", "s743b"), ("s754", "s734b"), ("s707", "s707c"), ("s707", "s752"),
             ("s751", "s751b"), ("s731a1", "s731"), ("s731a2", "s731"), ("s752a", "s752"),
             ("s752b", "s752"), ("s704d3", "s704d"), ("s742", "s1012")]:
    edge(a, b, "cross_references", mechanism="related provision")

# uses (liability term feeds 752 adjustments)
edge("s752a", "t_partnership_liability", "uses", mechanism="share of liabilities")
edge("s752b", "t_partnership_liability", "uses", mechanism="share of liabilities")

# interprets (case -> term)
edge("c_culbertson", "t_partnership_status", "interprets")
edge("c_luna", "t_partnership_status", "interprets")
edge("c_azimzadeh", "t_partnership_status", "interprets")
edge("c_canal", "t_disguised_sale", "interprets")
edge("c_tufts", "t_partnership_liability", "interprets")

# informs (ruling -> provision/term)
edge("rr84_52", "t_outside_basis", "informs", mechanism="unitary basis")
edge("rr99_5", "s722", "informs", mechanism="DRE -> partnership conversion")
edge("rr99_6", "s731", "informs", mechanism="partnership -> DRE conversion")
edge("rp93_27", "s721", "informs", mechanism="profits interest not taxable")
edge("rp2001_43", "s721", "informs", mechanism="nonvested profits interest")

# ===== DENSIFICATION: subsection & sub-definition leaf nodes (each individually noted) =====
NODES += [
    ("s751c", "provision", "IRC 751(c)", "Unrealized receivables", 1, None,
     "Rights to payment for goods/services not yet in income; an ordinary-income hot asset under §751.",
     ["751(c)", "unrealized receivables", "ordinary"], None, None),
    ("s751d", "provision", "IRC 751(d)", "Inventory items", 1, None,
     "Property held for sale plus other non-capital/non-1231 assets; a hot asset under §751.",
     ["751(d)", "inventory", "ordinary"], None, None),
    ("s736a", "provision", "IRC 736(a)", "Retiring partner: other payments", 1, None,
     "Payments not for partnership property are a distributive share or a guaranteed payment (ordinary).",
     ["736(a)", "guaranteed payment", "goodwill"], None, None),
    ("s736b", "provision", "IRC 736(b)", "Retiring partner: property payments", 1, None,
     "Payments for the partner's share of partnership property are liquidating distributions under §731 (capital, except §751(b)).",
     ["736(b)", "property", "liquidation"], None, None),
    ("s732a1", "provision", "IRC 732(a)(1)", "Distributed-property basis: carryover", 1, None,
     "In a current distribution, distributed property takes the partnership's basis (carryover).",
     ["732(a)(1)", "carryover"], None, None),
    ("s732a2", "provision", "IRC 732(a)(2)", "Distributed-property basis: cap", 1, None,
     "Distributed-property basis cannot exceed outside basis less money distributed in the same distribution.",
     ["732(a)(2)", "cap", "outside basis"], None, None),
    ("s732b", "provision", "IRC 732(b)", "Distributed-property basis: liquidation", 1, None,
     "In liquidation, distributed property takes the partner's remaining outside basis (after money).",
     ["732(b)", "liquidation", "substituted basis"], None, None),
    ("s704c1B", "provision", "IRC 704(c)(1)(B)", "Seven-year mixing-bowl (distribution)", 1, None,
     "Distributing contributed 704(c) property to another partner within 7 years triggers the contributor's built-in gain or loss.",
     ["704(c)(1)(B)", "seven-year", "mixing bowl"], None, None),
    ("s721c", "provision", "IRC 721(c)", "Foreign-partner built-in gain", 1, None,
     "Nonrecognition can be overridden where built-in-gain property is contributed to a partnership with related foreign partners (Treas. Reg. 1.721(c)).",
     ["721(c)", "foreign partner", "built-in gain"], None, None),
    ("s707a", "provision", "IRC 707(a)", "Partner not acting as a partner", 1, None,
     "Transactions where a partner deals with the partnership as a non-partner; the statutory anchor for disguised sales.",
     ["707(a)", "disguised sale", "non-partner"], None, None),
    ("s707b", "provision", "IRC 707(b)", "Related-party loss/character rules", 1, None,
     "Disallows losses and recharacterizes gain on sales between a partner and a controlled partnership.",
     ["707(b)", "related party", "loss disallowance"], None, None),
    ("r1752_3_t1", "regulation", "Treas. Reg. 1.752-3(a)(1)", "Nonrecourse tier 1: minimum gain", 3, None,
     "First tier of nonrecourse allocation: a partner's share of partnership minimum gain.",
     ["1.752-3", "tier 1", "minimum gain"], None, None),
    ("r1752_3_t2", "regulation", "Treas. Reg. 1.752-3(a)(2)", "Nonrecourse tier 2: 704(c) gain", 3, None,
     "Second tier: the 704(c) built-in gain the partner would be allocated on a deemed sale.",
     ["1.752-3", "tier 2", "704(c) gain"], None, None),
    ("r1752_3_t3", "regulation", "Treas. Reg. 1.752-3(a)(3)", "Nonrecourse tier 3: profits", 3, None,
     "Third tier: remaining nonrecourse liabilities by the partner's share of profits.",
     ["1.752-3", "tier 3", "profits"], None, None),
    ("r1704_3b", "regulation", "Treas. Reg. 1.704-3(b)", "704(c) traditional method", 3, None,
     "Traditional method; limited by the ceiling rule (tax items capped at actual partnership items).",
     ["1.704-3(b)", "traditional", "ceiling rule"], None, None),
    ("r1704_3c", "regulation", "Treas. Reg. 1.704-3(c)", "704(c) curative method", 3, None,
     "Traditional method with curative allocations of other actual items to cure ceiling-rule distortions.",
     ["1.704-3(c)", "curative"], None, None),
    ("r1704_3d", "regulation", "Treas. Reg. 1.704-3(d)", "704(c) remedial method", 3, None,
     "Remedial method; creates offsetting notional items to fully cure ceiling-rule distortions.",
     ["1.704-3(d)", "remedial", "notional"], None, None),
    ("r1707_4_gp", "regulation", "Treas. Reg. 1.707-4(a)", "Disguised-sale exception: guaranteed payment", 3, None,
     "Reasonable guaranteed payments for capital are generally not part of a disguised sale.",
     ["1.707-4", "guaranteed payment", "exception"], None, None),
    ("r1707_4_pref", "regulation", "Treas. Reg. 1.707-4(a)", "Disguised-sale exception: preferred return", 3, None,
     "Reasonable preferred returns are presumed not part of a disguised sale (with a rate safe harbor).",
     ["1.707-4", "preferred return", "exception"], None, None),
    ("r1707_4_ocf", "regulation", "Treas. Reg. 1.707-4(a)", "Disguised-sale exception: operating cash flow", 3, None,
     "Operating cash flow distributions within limits are presumed not part of a disguised sale.",
     ["1.707-4", "operating cash flow", "exception"], None, None),
    ("r1707_4_pre", "regulation", "Treas. Reg. 1.707-4(b)", "Disguised-sale exception: preformation", 3, None,
     "Reimbursement of certain preformation capital expenditures is not part of a disguised sale.",
     ["1.707-4(b)", "preformation", "reimbursement"], None, None),
]

edge("s751c", "t_hot_assets", "defines")
edge("s751d", "t_hot_assets", "defines")
edge("s751", "s751c", "cross_references", mechanism="defined term")
edge("s751", "s751d", "cross_references", mechanism="defined term")
edge("s724", "s751c", "cross_references", mechanism="character borrows 751(c)")
edge("s724", "s751d", "cross_references", mechanism="character borrows 751(d)")
edge("s736", "s736a", "cross_references", mechanism="payment split")
edge("s736", "s736b", "cross_references", mechanism="payment split")
edge("s736b", "s751b", "cross_references", mechanism="hot assets in property payment")
edge("s736b", "s731", "cross_references", mechanism="distribution rules")
edge("s736a", "s707c", "cross_references", mechanism="guaranteed-payment character")
edge("s732", "s732a1", "cross_references", mechanism="current-distribution basis")
edge("s732", "s732a2", "cross_references", mechanism="basis cap")
edge("s732", "s732b", "cross_references", mechanism="liquidation basis")
edge("s732a2", "t_outside_basis", "uses", direction="constraint", mechanism="cap at outside basis")
edge("s704c1B", "s737", "cross_references", mechanism="mixing-bowl pair")
edge("s704c1B", "s704c", "cross_references", mechanism="704(c) anti-abuse")
edge("s721c", "s721b", "cross_references", mechanism="contribution exception")
edge("s721c", "s704c", "cross_references", mechanism="remedial-method condition")
edge("s707a", "t_disguised_sale", "defines")
edge("s707", "s707a", "cross_references", mechanism="statutory hook")
edge("s707", "s707b", "cross_references", mechanism="related-party rules")
edge("r1752_3_t1", "s752", "implements", mechanism="nonrecourse tier 1")
edge("r1752_3_t2", "s752", "implements", mechanism="nonrecourse tier 2")
edge("r1752_3_t3", "s752", "implements", mechanism="nonrecourse tier 3")
edge("r1752_3_t1", "t_partnership_liability", "uses")
edge("r1752_3_t2", "t_partnership_liability", "uses")
edge("r1752_3_t3", "t_partnership_liability", "uses")
edge("r1752_3_t2", "t_built_in_gain", "uses", mechanism="704(c) gain feeds tier 2")
edge("r1704_3b", "s704c", "implements", mechanism="traditional method")
edge("r1704_3c", "s704c", "implements", mechanism="curative method")
edge("r1704_3d", "s704c", "implements", mechanism="remedial method")
edge("r1704_3b", "t_built_in_gain", "uses")
edge("r1704_3c", "t_built_in_gain", "uses")
edge("r1704_3d", "t_built_in_gain", "uses")
edge("r1707_4_gp", "s707", "implements", mechanism="disguised-sale exception")
edge("r1707_4_pref", "s707", "implements", mechanism="disguised-sale exception")
edge("r1707_4_ocf", "s707", "implements", mechanism="disguised-sale exception")
edge("r1707_4_pre", "s707", "implements", mechanism="disguised-sale exception")
edge("r1707_4_gp", "t_disguised_sale", "uses")
edge("r1707_4_pref", "t_disguised_sale", "uses")
edge("r1707_4_ocf", "t_disguised_sale", "uses")
edge("r1707_4_pre", "t_disguised_sale", "uses")

EDGES = E
