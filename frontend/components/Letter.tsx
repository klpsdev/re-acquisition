"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { usd } from "@/lib/format";
import type { Analysis, LetterTerms, Tier } from "@/lib/types";

const DEFAULT_TERMS: LetterTerms = {
  buyer: null, agent_name: "[Listing agent name]", earnest_money_pct: 1, inspection_days: 10, close_days: 45,
  financing: "Conventional investor loan, 25% down", signer_name: "[Your name]",
};

export default function LetterCard({ a, tier, aiAvailable, onApproved }: {
  a: Analysis; tier: Tier; aiAvailable: boolean; onApproved: () => void;
}) {
  const [terms, setTerms] = useState<LetterTerms>(DEFAULT_TERMS);
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [source, setSource] = useState<"template" | "llm">("template");
  const [loading, setLoading] = useState(false);
  const [approved, setApproved] = useState(false);
  const [approver, setApprover] = useState("");
  const [agentEmail, setAgentEmail] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [copied, setCopied] = useState("Copy letter");
  const reqId = useRef(0);
  const offer = a.offers.find((o) => o.tier === tier)!;

  async function generate(polish = false) {
    const id = ++reqId.current;
    setLoading(true);
    try {
      const r = await api.letter(a.id, tier, terms, polish);
      if (id === reqId.current) { setText(r.text); setSource(r.source); setDirty(false); }
    } catch (e) {
      if (id === reqId.current) setStatus({ ok: false, msg: `Couldn't generate the letter: ${(e as Error).message}` });
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }

  // Regenerate when the offer, its price, or the terms change, unless the user has edited the text.
  useEffect(() => {
    setApproved(false); setStatus(null);
    if (dirty) return;
    const t = setTimeout(() => generate(false), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.id, tier, offer.price, JSON.stringify(terms)]);

  async function approve() {
    setStatus(null);
    try {
      const r = await api.approve(a.id, tier, text, approver.trim(), agentEmail.trim());
      setStatus({ ok: true, msg: r.message });
      onApproved();
    } catch (e) {
      setStatus({ ok: false, msg: `Approval failed: ${(e as Error).message}` });
    }
  }

  async function copy() {
    try { await navigator.clipboard.writeText(text); setCopied("Copied"); }
    catch { (document.getElementById("letter") as HTMLTextAreaElement)?.select(); setCopied("Selected, press Ctrl+C"); }
    setTimeout(() => setCopied("Copy letter"), 1800);
  }

  const set = <K extends keyof LetterTerms>(k: K, v: LetterTerms[K]) => { setDirty(false); setTerms({ ...terms, [k]: v }); };
  const num = (v: string) => parseFloat(v) || 0;

  return (
    <section className="card">
      <div className="card-h"><h2>Offer letter</h2>
        <span className="src">{offer.label} offer · {usd(offer.price)} · {loading ? "generating…" : source === "llm" ? "polished by Claude" : "draft for your review"}</span></div>
      <div className="card-b">
        <div className="letter-grid">
          <div className="terms">
            <div className="field"><label htmlFor="t-buyer">Buyer</label><div className="in">
              <input id="t-buyer" type="text" placeholder="SP Real Estate Ventures, LLC" value={terms.buyer ?? ""}
                onChange={(e) => set("buyer", e.target.value || null)} /></div></div>
            <div className="field"><label htmlFor="t-agent">Listing agent</label><div className="in">
              <input id="t-agent" type="text" value={terms.agent_name} onChange={(e) => set("agent_name", e.target.value)} /></div></div>
            <div className="field"><label htmlFor="t-signer">Signed by</label><div className="in">
              <input id="t-signer" type="text" value={terms.signer_name} onChange={(e) => set("signer_name", e.target.value)} /></div></div>
            <div className="field"><label htmlFor="t-emd">Earnest money (of price)</label><div className="in">
              <input id="t-emd" type="number" step={0.5} value={terms.earnest_money_pct} onChange={(e) => set("earnest_money_pct", num(e.target.value))} />
              <span className="u">%</span></div></div>
            <div className="field"><label htmlFor="t-insp">Inspection period</label><div className="in">
              <input id="t-insp" type="number" step={1} value={terms.inspection_days} onChange={(e) => set("inspection_days", num(e.target.value))} />
              <span className="u">days</span></div></div>
            <div className="field"><label htmlFor="t-close">Close within</label><div className="in">
              <input id="t-close" type="number" step={5} value={terms.close_days} onChange={(e) => set("close_days", num(e.target.value))} />
              <span className="u">days</span></div></div>
            <div className="field"><label htmlFor="t-fin">Financing</label><div className="in">
              <select id="t-fin" value={terms.financing} onChange={(e) => set("financing", e.target.value)}>
                <option>Conventional investor loan, 25% down</option>
                <option>DSCR loan, 25% down</option>
                <option>All cash</option>
              </select></div></div>
          </div>
          <div>
            <textarea id="letter" spellCheck aria-label="Offer letter text" value={text}
              onChange={(e) => { setText(e.target.value); setDirty(true); }} />
            <div className="who">
              <div className="field"><label htmlFor="approver">Approved by</label><div className="in">
                <input id="approver" type="text" placeholder="Your name" value={approver} onChange={(e) => setApprover(e.target.value)} /></div></div>
              <div className="field"><label htmlFor="agent-email">Agent email (optional)</label><div className="in">
                <input id="agent-email" type="text" placeholder="agent@brokerage.com" value={agentEmail} onChange={(e) => setAgentEmail(e.target.value)} /></div></div>
            </div>
            <div className="actions">
              <label className="approve" htmlFor="approveBox">
                <input type="checkbox" id="approveBox" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
                I reviewed the numbers and approve this offer
              </label>
              {aiAvailable && <button className="btn" type="button" onClick={() => generate(true)} disabled={loading}>Polish with Claude</button>}
              <button className="btn" type="button" onClick={() => generate(false)} disabled={loading}>Regenerate</button>
              <button className="btn" type="button" onClick={copy}>{copied}</button>
              <button className="btn primary" type="button" style={{ padding: "9px 18px" }}
                disabled={!approved || !approver.trim() || !text} onClick={approve}>Approve &amp; log</button>
            </div>
            {status && <div className={status.ok ? "status" : "error"}>{status.msg}</div>}
          </div>
        </div>
      </div>
    </section>
  );
}
