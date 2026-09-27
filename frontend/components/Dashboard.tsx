"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, setWakeListener } from "@/lib/api";
import { usdK } from "@/lib/format";
import type { Analysis, AnalysisSummary, Criteria, ProvidersResponse, Tier } from "@/lib/types";
import { CompsCard, NeighborhoodCard, OffersCard, SubjectCard, UnderwritingCard } from "./Cards";
import LetterCard from "./Letter";
import Rail from "./Rail";

const SAMPLES = [
  { address: "218 Carpenter St, Woodbury, NJ 08096", label: "218 Carpenter St, Woodbury", list: 285000 },
  { address: "47 Hessian Ave, Deptford Township, NJ 08096", label: "47 Hessian Ave, Deptford Township", list: 309900 },
  { address: "16 Laurel Oak Ct, Sicklerville, NJ 08081", label: "16 Laurel Oak Ct, Sicklerville", list: 339000 },
];
const STEPS = ["Property profile", "Neighborhood", "Comparable sales", "Underwriting", "Offers & letter"];
const DEFAULT_CRITERIA: Criteria = {
  interest_rate: 6.75, down_payment: 25, closing_costs: 3, target_coc: 6, min_dscr: 1.2, vacancy: 6,
  maintenance_capex: 8, management: 0, max_all_in_pct_arv: 85, loan_years: 30,
};

export default function Dashboard() {
  const [address, setAddress] = useState(SAMPLES[0].address);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [criteria, setCriteria] = useState<Criteria>(DEFAULT_CRITERIA);
  const [rehab, setRehab] = useState("");
  const [tier, setTier] = useState<Tier>("target");
  const [step, setStep] = useState(0);
  const [running, setRunning] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<AnalysisSummary[]>([]);
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  // Set when we load a stored analysis, so restoring its criteria doesn't trigger a recompute.
  const skipRecompute = useRef(false);
  const [waking, setWaking] = useState(false);
  useEffect(() => { setWakeListener(setWaking); return () => setWakeListener(null); }, []);

  const loadRecent = useCallback(() => { api.recent().then(setRecent).catch(() => {}); }, []);

  const run = useCallback(async (addr: string) => {
    if (!addr.trim()) return;
    setRunning(true); setError(null); setStep(0);
    const tick = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 300);
    try {
      const a = await api.analyze(addr.trim(), criteria);
      setRehab(""); setAnalysis(a); setTier("target"); setStep(STEPS.length);
      loadRecent();
    } catch (e) {
      setError(`Analysis failed: ${(e as Error).message}. If this keeps happening, check that sprev-api is Live in Render and look at its Logs.`);
      setStep(0);
    } finally {
      clearInterval(tick); setRunning(false);
    }
  }, [criteria, loadRecent]);

  // Open in a working state: providers, recent list, and the first sample.
  useEffect(() => {
    api.providers().then(setProviders).catch(() => {});
    run(SAMPLES[0].address);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Criteria or rehab edits re-run the Python underwriting against stored data (debounced).
  useEffect(() => {
    if (!analysis) return;
    if (skipRecompute.current) { skipRecompute.current = false; return; }
    const rehabNum = rehab.trim() === "" ? null : Number(rehab);
    if (rehabNum !== null && isNaN(rehabNum)) return;
    setRecomputing(true);
    const t = setTimeout(() => {
      api.recompute(analysis.id, criteria, rehabNum)
        .then((a) => { setAnalysis(a); setError(null); })
        .catch((e) => setError(`Recompute failed: ${(e as Error).message}`))
        .finally(() => setRecomputing(false));
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [criteria, rehab]);

  const open = async (id: string) => {
    try {
      const a = await api.get(id);
      skipRecompute.current = true;
      setAnalysis(a); setAddress(a.property.address); setCriteria(a.underwriting.criteria); setRehab(""); setTier("target");
      setStep(STEPS.length); window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) { setError((e as Error).message); }
  };

  return (
    <div className="wrap">
      <header className="top">
        <div className="brand">
          <div className="mark" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M3 9.5 10 3.5l7 6V17H3V9.5Z" stroke="var(--accent-ink)" strokeWidth="1.8" strokeLinejoin="round" />
              <path d="M7 13.5h6M7 11h3" stroke="var(--accent-ink)" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </div>
          <div>
            <h1>SPREV Acquisition Engine</h1>
            <p>SP Real Estate Ventures LLC · South Jersey rental underwriting</p>
          </div>
        </div>
        {providers?.data_mode !== "live" && <span className="demo-chip">Sample data mode</span>}
      </header>

      <form className="run" onSubmit={(e) => { e.preventDefault(); run(address); }} autoComplete="off">
        <label className="addr" htmlFor="addrInput">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.8" /><path d="m13.5 13.5 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <input id="addrInput" type="text" value={address} onChange={(e) => setAddress(e.target.value)}
            placeholder="Enter a property address, e.g. 123 Main Street, Camden, NJ" aria-label="Property address" />
        </label>
        <button className="btn primary" type="submit" disabled={running}>{running ? "Analyzing…" : "Run analysis"}</button>
      </form>
      <div className="samples">
        <span className="lbl">Sample properties:</span>
        {SAMPLES.map((s) => (
          <button key={s.address} type="button" className="sample"
            aria-pressed={analysis?.property.street ? s.address.startsWith(analysis.property.street) : false}
            onClick={() => { setAddress(s.address); run(s.address); }}>
            {s.label} <span className="st num">{usdK(s.list)}</span>
          </button>
        ))}
      </div>

      <div className="pipe" aria-label="Analysis pipeline">
        {STEPS.map((s, i) => (
          <div key={s} className={`step ${i < step ? "done" : i === step && running ? "active" : ""}`}><i /><b>{s}</b></div>
        ))}
      </div>
      {waking && <div className="status">Waking up the server (it sleeps when idle on the free plan). This takes up to a minute…</div>}
      {error && <div className="error">{error}</div>}

      {analysis && (
        <div className={`grid ${running ? "busy" : ""}`}>
          <main className="main">
            <SubjectCard a={analysis} />
            <NeighborhoodCard a={analysis} />
            <CompsCard a={analysis} />
            <UnderwritingCard a={analysis} criteria={criteria} onCriteria={setCriteria} rehab={rehab} onRehab={setRehab} busy={recomputing} />
            <OffersCard a={analysis} selected={tier} onSelect={setTier} />
            <LetterCard a={analysis} tier={tier} aiAvailable={!!providers?.ai_explanations} email={providers?.email} onApproved={loadRecent} />
          </main>
          <Rail a={analysis} tier={tier} recent={recent} providers={providers} onOpen={open} />
        </div>
      )}

      <p className="foot">
        Figures come from the providers listed under Data sources; in sample mode they are illustrative, and unknown addresses get a
        synthetic profile. Underwriting, MAO and offer tiers are computed by the Python API. Approvals are logged with a snapshot of
        the numbers; an offer is emailed only after you approve it and confirm the send. Not legal or financial advice; have an attorney review offers.
      </p>
    </div>
  );
}
