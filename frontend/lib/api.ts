import type { Analysis, AnalysisSummary, ApprovalResult, Criteria, LetterTerms, Offer, OfferForm, ProvidersResponse, Tier } from "./types";

// Render's free plan puts the API to sleep after ~15 idle minutes; the first request then gets a
// 502/503/504 while it boots (30-60 s). Retry those quietly and tell the page we're waiting.
const WAKE_STATUSES = new Set([502, 503, 504]);
let onWaking: ((waking: boolean) => void) | null = null;
export function setWakeListener(fn: ((waking: boolean) => void) | null) { onWaking = fn; }

async function fetchWithWake(url: string, init: RequestInit): Promise<Response> {
  const delays = [2000, 4000, 8000, 12000, 15000, 20000]; // ~60 s total
  for (let attempt = 0; ; attempt++) {
    let res: Response | null = null;
    try { res = await fetch(url, init); } catch { /* network blip while the server restarts */ }
    if (res && !WAKE_STATUSES.has(res.status)) { onWaking?.(false); return res; }
    if (attempt >= delays.length) {
      onWaking?.(false);
      if (res) return res;
      throw new Error("The server didn't respond");
    }
    onWaking?.(true);
    await new Promise((r) => setTimeout(r, delays[attempt]));
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetchWithWake(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  providers: () => call<ProvidersResponse>("/providers"),
  recent: () => call<AnalysisSummary[]>("/analyses?limit=8"),
  get: (id: string) => call<Analysis>(`/analyses/${id}`),
  analyze: (address: string, criteria?: Criteria) =>
    call<Analysis>("/analyze", { method: "POST", body: JSON.stringify({ address, criteria }) }),
  recompute: (id: string, criteria: Criteria, rehab_override?: number | null) =>
    call<Analysis>(`/analyses/${id}/recompute`, { method: "POST", body: JSON.stringify({ criteria, rehab_override }) }),
  letter: (id: string, tier: Tier, terms: LetterTerms, polish_with_ai = false, price_override: number | null = null) =>
    call<{ tier: Tier; price: number; text: string; source: "template" | "llm" }>(`/analyses/${id}/letter`, {
      method: "POST", body: JSON.stringify({ tier, terms, polish_with_ai, price_override }),
    }),
  atPrice: (id: string, tier: Tier, price: number) =>
    call<Offer>(`/analyses/${id}/at-price?tier=${tier}&price=${encodeURIComponent(price)}`),
  offerForm: (id: string, tier: Tier, closeDays = 45) =>
    call<OfferForm>(`/analyses/${id}/offer-form?tier=${tier}&close_days=${closeDays}`),
  saveProfile: (form: OfferForm) => call<OfferForm>("/offer-profile", { method: "PUT", body: JSON.stringify(form) }),
  offerPdf: async (form: OfferForm): Promise<Blob> => {
    const res = await fetchWithWake("/api/offer-pdf", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form), cache: "no-store" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.blob();
  },
  approve: (id: string, body: { tier: Tier; letter_text: string; approved_by: string; agent_email?: string;
                                 subject?: string; send: boolean; offer_form?: OfferForm | null;
                                 price_override?: number | null }) =>
    call<ApprovalResult>(`/analyses/${id}/approve`, { method: "POST", body: JSON.stringify(body) }),
  resend: (approvalId: number) => call<ApprovalResult>(`/approvals/${approvalId}/send`, { method: "POST" }),
};
