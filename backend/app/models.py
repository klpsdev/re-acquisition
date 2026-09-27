"""The standardized objects every connector feeds and every service reads.

Connectors translate provider-specific payloads into these models, so the
underwriting engine never knows (or cares) where the data came from.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Condition = Literal["Dated", "Good", "Updated", "Renovated"]
CONDITION_RANK: dict[str, int] = {"Dated": 0, "Good": 1, "Updated": 2, "Renovated": 3}


class SourceNote(BaseModel):
    """Provenance for a block of data: where it came from, when, and at what level."""
    provider: str
    detail: str = ""
    as_of: date | None = None
    synthetic: bool = False


class PropertyProfile(BaseModel):
    address: str
    street: str
    city: str
    state: str = "NJ"
    zip: str = ""
    county: str = ""
    property_type: str = "Single-family"
    units: int = 1
    beds: float
    baths: float
    sqft: int
    lot: str = ""
    year_built: int
    condition: Condition = "Good"
    utilities: str = "Public sewer & water"
    list_price: float | None = None
    status: str = "Unknown"
    days_on_market: int | None = None
    annual_tax: float
    annual_insurance: float
    flags: list[str] = Field(default_factory=list)
    rehab_hint: float | None = None      # a provider's or your own rehab number, if known
    lat: float | None = None
    lon: float | None = None
    source: SourceNote


class RentEstimate(BaseModel):
    monthly: float
    low: float
    high: float
    note: str = ""
    source: SourceNote


class Neighborhood(BaseModel):
    tract_name: str
    median_household_income: float | None = None
    income_growth_5y: float | None = None
    median_gross_rent: float | None = None
    rental_vacancy: float | None = None
    owner_occupied: float | None = None
    population_change_5y: float | None = None
    poverty_rate: float | None = None
    mean_commute_min: float | None = None
    demand_score: int | None = None
    source: SourceNote


class Comp(BaseModel):
    address: str
    distance_mi: float
    beds: float
    baths: float
    sqft: int
    year_built: int
    condition: Condition = "Good"
    sold_date: date
    sale_price: float
    units: int = 1
    # Filled in by the valuation service
    similarity: int | None = None
    adjusted_as_is: float | None = None
    adjusted_arv: float | None = None
    used: bool = False


class Criteria(BaseModel):
    """Your acquisition rules. The MAO is the highest price that satisfies all of them."""
    interest_rate: float = 6.75          # %
    down_payment: float = 25.0           # % of price
    closing_costs: float = 3.0           # % of price
    target_coc: float = 6.0              # cash-on-cash, %
    min_dscr: float = 1.20
    vacancy: float = 6.0                 # % of gross rent
    maintenance_capex: float = 8.0       # % of gross rent
    management: float = 0.0              # % of gross rent (0 = self-managed)
    max_all_in_pct_arv: float = 85.0     # (price + rehab) / ARV
    loan_years: int = 30


class Valuation(BaseModel):
    comps: list[Comp]
    as_is_value: float
    value_low: float
    value_high: float
    arv: float
    spread_pct: float
    comps_found: int
    comps_similar: int
    comps_used: int
    comp_confidence: float
    rent_confidence: float
    confidence: int


class Economics(BaseModel):
    price: float
    gross_rent: float
    vacancy: float
    egi: float
    tax: float
    insurance: float
    maintenance_capex: float
    management: float
    septic_reserve: float
    opex: float
    noi: float
    loan: float
    debt_service: float
    down_payment: float
    closing_costs: float
    rehab: float
    cash_in: float
    cash_flow: float
    coc: float
    dscr: float
    cap_rate: float
    all_in_pct_arv: float


class Constraint(BaseModel):
    name: str
    max_price: float
    binding: bool = False


class Underwriting(BaseModel):
    criteria: Criteria
    rehab: float
    constraints: list[Constraint]
    mao: float
    at_mao: Economics


class Offer(BaseModel):
    tier: Literal["aggressive", "target", "competitive", "stretch"]
    label: str
    price: float
    pct_of_list: float | None
    pct_of_value: float
    meets_criteria: bool
    economics: Economics
    coc_at_low_rent: float
    return_confidence: int
    acceptance_likelihood: int | None


class Risk(BaseModel):
    severity: Literal["high", "medium", "low"]
    text: str


class Analysis(BaseModel):
    id: str
    created_at: str
    property: PropertyProfile
    rent: RentEstimate
    neighborhood: Neighborhood
    valuation: Valuation
    rehab_estimate: float
    underwriting: Underwriting
    offers: list[Offer]
    risks: list[Risk]
    explanation: str
    explanation_source: Literal["template", "llm"]


class AnalyzeRequest(BaseModel):
    address: str = Field(min_length=5)
    criteria: Criteria | None = None
    rehab_override: float | None = None


class RecomputeRequest(BaseModel):
    criteria: Criteria
    rehab_override: float | None = None


class LetterTerms(BaseModel):
    buyer: str | None = None
    agent_name: str = "[Listing agent name]"
    earnest_money_pct: float = 1.0
    inspection_days: int = 10
    close_days: int = 45
    financing: str = "Conventional investor loan, 25% down"
    signer_name: str = "[Your name]"


class LetterRequest(BaseModel):
    tier: Literal["aggressive", "target", "competitive", "stretch"]
    terms: LetterTerms = Field(default_factory=LetterTerms)
    polish_with_ai: bool = False


class LetterResponse(BaseModel):
    tier: str
    price: float
    text: str
    source: Literal["template", "llm"]


class ApprovalRequest(BaseModel):
    tier: Literal["aggressive", "target", "competitive", "stretch"]
    letter_text: str
    approved_by: str = Field(min_length=1)
    agent_email: str | None = None


class ApprovalResponse(BaseModel):
    approval_id: int
    status: Literal["approved_not_sent", "sent"]
    message: str


class AnalysisSummary(BaseModel):
    id: str
    created_at: str
    address: str
    list_price: float | None
    mao: float
    status: str
