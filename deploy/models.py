"""
models.py — request validation models. Response shapes come from engine_adapter
and are wrapped in a {data, meta} envelope by app.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    as_of: str | None = Field(
        default=None,
        description="Transaction date YYYY-MM-DD for the currency gate. Omit for 'today'.",
    )


class BasisInputs(BaseModel):
    """Mirrors calculator.BasisInputs. All fields default to 0.0; FMV is never an input."""
    beginning_basis: float = 0.0
    cash_contributed: float = 0.0
    property_contributed_basis: float = 0.0
    liability_increase: float = 0.0
    income_taxable: float = 0.0
    income_tax_exempt: float = 0.0
    depletion_excess: float = 0.0
    cash_distributed: float = 0.0
    property_distributed_basis: float = 0.0
    liability_decrease: float = 0.0
    nondeductible: float = 0.0
    oil_gas_depletion: float = 0.0
    losses: float = 0.0
