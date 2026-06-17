"""
calculator.py — the deterministic outside-basis engine.

The graph ROUTES basis questions here. It never reasons a number out of retrieved
text, because LLMs drop the floor and mis-order the steps. Ordering and the zero-floor
match IRS LB&I Process Unit PAR-P-002 (rev. 11/05/2024) and the validated workbook:
increases first, then distributions/liability decreases (floor 0, excess = §731(a) gain),
then basis-reducing items, then losses limited by §704(d) (excess suspended).

This is run-time compute, not graph data. Pure stdlib; no network, no model.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class BasisInputs:
    beginning_basis: float = 0.0
    cash_contributed: float = 0.0            # §722
    property_contributed_basis: float = 0.0  # §722 (adjusted basis, NOT FMV)
    liability_increase: float = 0.0          # §752(a)
    income_taxable: float = 0.0              # §705(a)(1)(A)
    income_tax_exempt: float = 0.0           # §705(a)(1)(B)
    depletion_excess: float = 0.0            # §705(a)(1)(C)
    cash_distributed: float = 0.0            # §733
    property_distributed_basis: float = 0.0  # §733 / §732
    liability_decrease: float = 0.0          # §752(b)
    nondeductible: float = 0.0               # §705(a)(2)(B)
    oil_gas_depletion: float = 0.0           # §705(a)(3)
    losses: float = 0.0                      # §705(a)(2)(A) / §704(d)


def compute_outside_basis(i: BasisInputs) -> dict:
    trace = [("A. Beginning basis", i.beginning_basis, i.beginning_basis)]

    increases = (i.cash_contributed + i.property_contributed_basis + i.liability_increase
                 + i.income_taxable + i.income_tax_exempt + i.depletion_excess)
    b = i.beginning_basis + increases
    trace.append(("B. + increases  [§722, §752(a), §705(a)(1)]", increases, b))

    distributions = i.cash_distributed + i.property_distributed_basis + i.liability_decrease
    sec731a_gain = max(0.0, distributions - b)            # §731(a): excess distribution = gain
    b = max(0.0, b - distributions)                       # floor at zero
    trace.append(("C. - distributions  [§733, §752(b)] (floor 0)", -distributions, b))

    reductions = i.nondeductible + i.oil_gas_depletion
    b = max(0.0, b - reductions)
    trace.append(("D. - nondeductible/depletion  [§705(a)(2)(B), (a)(3)] (floor 0)", -reductions, b))

    loss_allowed = min(i.losses, b)                       # §704(d): limited to remaining basis
    loss_suspended = i.losses - loss_allowed
    b = b - loss_allowed
    trace.append(("E. - loss allowed  [§704(d) limit]", -loss_allowed, b))

    return {
        "ending_basis": round(b, 2),
        "sec731a_gain": round(sec731a_gain, 2),
        "sec704d_loss_allowed": round(loss_allowed, 2),
        "sec704d_loss_suspended": round(loss_suspended, 2),
        "trace": trace,
        "authorities": ["IRC 722", "IRC 742", "IRC 752", "IRC 705",
                        "IRC 733", "IRC 704(d)", "IRC 731(a)"],
    }


def format_result(r: dict) -> str:
    lines = ["Outside-basis computation (deterministic engine):", ""]
    for label, delta, running in r["trace"]:
        lines.append(f"  {label:<48} {delta:>14,.0f}   ->  {running:>14,.0f}")
    lines += [
        "",
        f"  Ending outside basis        : {r['ending_basis']:>14,.0f}",
        f"  §731(a) gain (excess dist.) : {r['sec731a_gain']:>14,.0f}",
        f"  §704(d) loss allowed        : {r['sec704d_loss_allowed']:>14,.0f}",
        f"  §704(d) loss suspended      : {r['sec704d_loss_suspended']:>14,.0f}",
        "",
        "  Authorities: " + ", ".join(r["authorities"]),
        "  Not tax advice; verify against primary authority.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # Self-validation against the two IRS LB&I worked examples.
    sally = compute_outside_basis(BasisInputs(beginning_basis=45000, losses=125000))
    assert sally["sec704d_loss_allowed"] == 45000 and sally["sec704d_loss_suspended"] == 80000, sally
    joe = compute_outside_basis(BasisInputs(beginning_basis=245000, cash_distributed=465000))
    assert joe["sec731a_gain"] == 220000 and joe["ending_basis"] == 0, joe
    print("calculator self-test PASS (Sally 45k/80k; Joe 220k gain / 0 basis)")
    print()
    print(format_result(joe))
