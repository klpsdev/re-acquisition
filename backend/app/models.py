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
    listing_agent_name: str | None = None
    listing_agent_email: str | None = None
    listing_agent_phone: str | None = None
    listing_office: str | None = None
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
    data_trail: list[str] = Field(default_factory=list)   # which provider answered what; failures with reasons


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
    signer_phone: str = "[Phone]"
    signer_email: str | None = None      # defaults to the Gmail sender when email is set up


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
    letter_text: str = Field(min_length=20)
    offer_form: "OfferForm | None" = None   # when set, the filled Proposal to Purchase PDF is attached
    approved_by: str = Field(min_length=1)
    agent_email: str | None = None
    subject: str | None = None
    send: bool = False            # True = email the letter to agent_email right after logging the approval


class ApprovalResponse(BaseModel):
    approval_id: int
    status: Literal["approved_not_sent", "sent", "send_failed"]
    message: str
    sent_from: str | None = None
    sent_to: str | None = None
    sent_at: str | None = None
    message_id: str | None = None


class AnalysisSummary(BaseModel):
    id: str
    created_at: str
    address: str
    list_price: float | None
    mao: float
    status: str


MortgageType = Literal["fha", "va", "conventional", "other"]
AgencyRole = Literal["seller_agent", "buyer_agent", "dual_agent", "transaction_broker"]


class OfferForm(BaseModel):
    """Every blank on the NJ Proposal to Purchase (FORM#001). Empty fields stay blank on the PDF."""
    buyer_name: str = ""
    presenting_firm: str = ""
    property_address: str = ""
    price: float | None = None
    initial_deposit: float | None = None
    additional_deposit: float | None = None
    additional_deposit_date: str = ""
    balance_due: float | None = None
    mortgage_type: MortgageType | None = None
    mortgage_amount: float | None = None
    settlement_date: str = ""
    title_company: str = ""               # up to two lines
    also_included: str = ""
    specifically_excluded: str = ""
    possession: Literal["settlement", "other"] | None = "settlement"
    possession_other: str = ""
    insp_wood_boring: bool = False
    insp_home: bool = True
    insp_septic: bool = False
    insp_other: str = ""
    seller_well: bool = False
    seller_other: str = ""
    assets: Literal["not_contingent", "sale_under_contract", "sale_not_under_contract"] | None = "not_contingent"
    assets_property: str = ""
    other_terms: str = ""
    firm_name: str = ""
    licensee: str = ""
    firm_role: AgencyRole | None = "buyer_agent"
    listing_firm: str = ""
    listing_role: AgencyRole | None = "seller_agent"
    valid_days: int | None = 15
    presenting_address: str = ""          # up to two lines
    office_tel: str = ""
    office_fax: str = ""
    agent_name: str = ""
    agent_cell: str = ""
    agent_email: str = ""
    buyer_date: str = ""
    buyer_signed_2: str = ""
    buyer_date_2: str = ""
    buyer_address: str = ""
    footer_company: str = ""


# Fields that describe you and your brokerage (saved as defaults), vs. ones that change per deal.
OFFER_PROFILE_FIELDS = (
    "buyer_name", "presenting_firm", "mortgage_type", "title_company", "possession", "insp_wood_boring", "insp_home",
    "insp_septic", "insp_other", "seller_well", "seller_other", "assets", "firm_name", "licensee", "firm_role",
    "listing_role", "valid_days", "presenting_address", "office_tel", "office_fax", "agent_name", "agent_cell",
    "agent_email", "buyer_signed_2", "buyer_address", "footer_company", "initial_deposit",
)


ApprovalRequest.model_rebuild()
