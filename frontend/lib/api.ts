import type { Analysis, AnalysisSummary, Criteria, LetterTerms, ProvidersResponse, Tier } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
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
  letter: (id: string, tier: Tier, terms: LetterTerms, polish_with_ai = false) =>
    call<{ tier: Tier; price: number; text: string; source: "template" | "llm" }>(`/analyses/${id}/letter`, {
      method: "POST", body: JSON.stringify({ tier, terms, polish_with_ai }),
    }),
  approve: (id: string, tier: Tier, letter_text: string, approved_by: string, agent_email?: string) =>
    call<{ approval_id: number; status: string; message: string }>(`/analyses/${id}/approve`, {
      method: "POST", body: JSON.stringify({ tier, letter_text, approved_by, agent_email: agent_email || null }),
    }),
};
