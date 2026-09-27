// Mirrors backend/app/models.py. Keep the two in sync (or generate from /openapi.json).

export type Tier = "aggressive" | "target" | "competitive" | "stretch";
export type Condition = "Dated" | "Good" | "Updated" | "Renovated";

export interface SourceNote { provider: string; detail: string; as_of: string | null; synthetic: boolean }

export interface PropertyProfile {
  address: string; street: string; city: string; state: string; zip: string; county: string;
  property_type: string; units: number; beds: number; baths: number; sqft: number; lot: string;
  year_built: number; condition: Condition; utilities: string; list_price: number | null; status: string;
  days_on_market: number | null; annual_tax: number; annual_insurance: number; flags: string[];
  rehab_hint: number | null; lat: number | null; lon: number | null; source: SourceNote;
}

export interface RentEstimate { monthly: number; low: number; high: number; note: string; source: SourceNote }

export interface Neighborhood {
  tract_name: string; median_household_income: number | null; income_growth_5y: number | null;
  median_gross_rent: number | null; rental_vacancy: number | null; owner_occupied: number | null;
  population_change_5y: number | null; poverty_rate: number | null; mean_commute_min: number | null;
  demand_score: number | null; source: SourceNote;
}

export interface Comp {
  address: string; distance_mi: number; beds: number; baths: number; sqft: number; year_built: number;
  condition: Condition; sold_date: string; sale_price: number; units: number;
  similarity: number | null; adjusted_as_is: number | null; adjusted_arv: number | null; used: boolean;
}

export interface Criteria {
  interest_rate: number; down_payment: number; closing_costs: number; target_coc: number; min_dscr: number;
  vacancy: number; maintenance_capex: number; management: number; max_all_in_pct_arv: number; loan_years: number;
}

export interface Valuation {
  comps: Comp[]; as_is_value: number; value_low: number; value_high: number; arv: number; spread_pct: number;
  comps_found: number; comps_similar: number; comps_used: number; comp_confidence: number;
  rent_confidence: number; confidence: number;
}

export interface Economics {
  price: number; gross_rent: number; vacancy: number; egi: number; tax: number; insurance: number;
  maintenance_capex: number; management: number; septic_reserve: number; opex: number; noi: number;
  loan: number; debt_service: number; down_payment: number; closing_costs: number; rehab: number;
  cash_in: number; cash_flow: number; coc: number; dscr: number; cap_rate: number; all_in_pct_arv: number;
}

export interface Constraint { name: string; max_price: number; binding: boolean }
export interface Underwriting { criteria: Criteria; rehab: number; constraints: Constraint[]; mao: number; at_mao: Economics }

export interface Offer {
  tier: Tier; label: string; price: number; pct_of_list: number | null; pct_of_value: number;
  meets_criteria: boolean; economics: Economics; coc_at_low_rent: number; return_confidence: number;
  acceptance_likelihood: number | null;
}

export interface Risk { severity: "high" | "medium" | "low"; text: string }

export interface Analysis {
  id: string; created_at: string; property: PropertyProfile; rent: RentEstimate; neighborhood: Neighborhood;
  valuation: Valuation; rehab_estimate: number; underwriting: Underwriting; offers: Offer[]; risks: Risk[];
  explanation: string; explanation_source: "template" | "llm"; data_trail?: string[];
}

export interface AnalysisSummary { id: string; created_at: string; address: string; list_price: number | null; mao: number; status: string }

export interface LetterTerms {
  buyer?: string | null; agent_name: string; earnest_money_pct: number; inspection_days: number;
  close_days: number; financing: string; signer_name: string; signer_phone: string; signer_email?: string | null;
}

export interface Provider { id: string; name: string; active: boolean; provides: string }
export interface EmailStatus { configured: boolean; provider: string | null; sender: string | null; missing?: string[] }
export interface ProvidersResponse { data_mode: string; providers: Provider[]; ai_explanations: boolean; email?: EmailStatus }
export interface ApprovalResult {
  approval_id: number; status: "approved_not_sent" | "sent" | "send_failed"; message: string;
  sent_from: string | null; sent_to: string | null; sent_at: string | null; message_id: string | null;
}
