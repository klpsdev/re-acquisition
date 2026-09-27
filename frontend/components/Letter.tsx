"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { usd } from "@/lib/format";
import type { Analysis, ApprovalResult, EmailStatus, LetterTerms, OfferForm, Tier } from "@/lib/types";
import OfferFormFields from "./OfferForm";

const DEFAULT_TERMS: LetterTerms = {
  buyer: null, agent_name: "[Listing agent name]", earnest_money_pct: 1, inspection_days: 10, close_days: 45,
  financing: "Conventional investor loan, 25% down", signer_name: "[Your name]", signer_phone: "[Phone]",
};

const EMAIL_RE = /^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$/;

export default function LetterCard({ a, tier, aiAvailable, email, onApproved }: {
  a: Analysis; tier: Tier; aiAvailable: boolean; email?: EmailStatus; onApproved: () => void;
}) {
  const [terms, setTerms] = useState<LetterTerms>(DEFAULT_TERMS);
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [source, setSource] = useState<"template" | "llm">("template");
  const [loading, setLoading] = useState(false);
  const [approved, setApproved] = useState(false);
  const [approver, setApprover] = useState("");
  const [agentEmail, setAgentEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [subjectDirty, setSubjectDirty] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApprovalResult | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [copied, setCopied] = useState("Copy letter");
  const [form, setForm] = useState<OfferForm | null>(null);
  const [attachPdf, setAttachPdf] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const formFor = useRef<string>("");
  const reqId = useRef(0);
  const offer = a.offers.find((o) => o.tier === tier)!;

  const calcBalance = (f: OfferForm) =>
    f.price == null ? null : Math.round(f.price - (f.initial_deposit ?? 0) - (f.additional_deposit ?? 0) - (f.mortgage_amount ?? 0));

  // Load the pre-filled Proposal to Purchase once per analysis; afterwards a tier change only updates the price.
  useEffect(() => {
    if (formFor.current === a.id && form) {
      setForm((f) => (f ? { ...f, price: offer.price, balance_due: calcBalance({ ...f, price: offer.price }) } : f));
      return;
    }
    formFor.current = a.id;
    api.offerForm(a.id, tier, terms.close_days).then(setForm).catch(() => setForm(null));
    // Pre-fill the listing agent from the listing, when the data source has it.
    if (a.property.listing_agent_email && !agentEmail) setAgentEmail(a.property.listing_agent_email);
    if (a.property.listing_agent_name && terms.agent_name.startsWith("["))
      setTerms((t) => ({ ...t, agent_name: a.property.listing_agent_name! }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.id, offer.price]);

  const setField = <K extends keyof OfferForm>(k: K, v: OfferForm[K]) =>
    setForm((f) => {
      if (!f) return f;
      const next = { ...f, [k]: v };
      next.balance_due = calcBalance(next);
      return next;
    });

  async function previewPdf() {
    if (!form) return;
    const win = window.open("", "_blank");
    setPdfBusy(true);
    try {
      const url = URL.createObjectURL(await api.offerPdf(form));
      if (win) win.location.href = url; else window.location.href = url;
    } catch (e) {
      win?.close();
      setStatus({ ok: false, msg: `Couldn't build the PDF: ${(e as Error).message}` });
    } finally { setPdfBusy(false); }
  }

  async function downloadPdf() {
    if (!form) return;
    setPdfBusy(true);
    try {
      const url = URL.createObjectURL(await api.offerPdf(form));
      const link = document.createElement("a");
      const street = (form.property_address || "property").split(",")[0].replace(/[^A-Za-z0-9]+/g, "_");
      link.href = url; link.download = `${street}_Offer-unsigned.pdf`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      setStatus({ ok: false, msg: `Couldn't build the PDF: ${(e as Error).message}` });
    } finally { setPdfBusy(false); }
  }

  async function saveDefaults() {
    if (!form) return;
    try { await api.saveProfile(form); setProfileMsg("Saved. New offers will start with these details."); }
    catch (e) { setProfileMsg(`Couldn't save: ${(e as Error).message}`); }
    setTimeout(() => setProfileMsg(null), 4000);
  }

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

  const p = a.property;
  const defaultSubject = `Offer: ${p.street}, ${p.city}, ${p.state} ${p.zip} (${usd(offer.price)})`;
  useEffect(() => { if (!subjectDirty) setSubject(defaultSubject); }, [defaultSubject, subjectDirty]);

  // Regenerate when the offer, its price, or the terms change, unless the user has edited the text.
  useEffect(() => {
    setApproved(false); setStatus(null); setResult(null); setConfirming(false);
    if (dirty) return;
    const t = setTimeout(() => generate(false), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.id, tier, offer.price, JSON.stringify(terms)]);

  const canEmail = !!email?.configured;
  const emailOk = EMAIL_RE.test(agentEmail.trim());
  const unfilled = Array.from(new Set(text.match(/\[[A-Z][^\]\n]{1,40}\]/g) ?? []));
  const ready = approved && !!approver.trim() && text.length > 20 && !busy && result?.status !== "sent";

  async function approve(send: boolean) {
    setStatus(null); setBusy(true); setConfirming(false);
    try {
      const r = await api.approve(a.id, {
        tier, letter_text: text, approved_by: approver.trim(), agent_email: agentEmail.trim() || undefined,
        subject: subject.trim() || undefined, send, offer_form: attachPdf ? form : null,
      });
      setResult(r);
      setStatus({ ok: r.status !== "send_failed", msg: r.message });
      onApproved();
    } catch (e) {
      setStatus({ ok: false, msg: `Approval failed: ${(e as Error).message}` });
    } finally { setBusy(false); }
  }

  async function retry() {
    if (!result) return;
    setBusy(true);
    try {
      const r = await api.resend(result.approval_id);
      setResult(r); setStatus({ ok: r.status !== "send_failed", msg: r.message }); onApproved();
    } catch (e) {
      setStatus({ ok: false, msg: `Retry failed: ${(e as Error).message}` });
    } finally { setBusy(false); }
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
            <div className="field"><label htmlFor="t-phone">Your phone</label><div className="in">
              <input id="t-phone" type="text" value={terms.signer_phone} onChange={(e) => set("signer_phone", e.target.value)} /></div></div>
            <div className="field"><label htmlFor="t-semail">Your email</label><div className="in">
              <input id="t-semail" type="email" placeholder={email?.sender ?? "you@gmail.com"} value={terms.signer_email ?? ""}
                onChange={(e) => set("signer_email", e.target.value || null)} /></div></div>
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

            <div className="ptp">
              <div className="ptp-h">
                <label className="chk" htmlFor="attach-pdf">
                  <input id="attach-pdf" type="checkbox" checked={attachPdf} onChange={(e) => setAttachPdf(e.target.checked)} />
                  <b>Attach Proposal to Purchase (PDF)</b>
                </label>
                <div className="ptp-actions">
                  <button className="btn" type="button" onClick={() => setFormOpen((o) => !o)} aria-expanded={formOpen} disabled={!form}>
                    {formOpen ? "Hide form fields" : "Edit form fields"}</button>
                  <button className="btn" type="button" onClick={previewPdf} disabled={!form || pdfBusy}>{pdfBusy ? "Building…" : "Preview PDF"}</button>
                  <button className="btn" type="button" onClick={downloadPdf} disabled={!form || pdfBusy}>Download</button>
                </div>
              </div>
              {form ? (
                <div className="ptp-sum">
                  {usd(form.price)} · deposit {usd(form.initial_deposit)} · balance {usd(form.balance_due)} · settle by {form.settlement_date || "—"}
                  {" "}· {form.firm_name || "no brokerage"} · valid {form.valid_days ?? "—"} days
                </div>
              ) : <div className="ptp-sum">Loading the form…</div>}
              {formOpen && form && (
                <>
                  <OfferFormFields form={form} set={setField} expectedBalance={calcBalance(form)} />
                  <div className="ptp-actions" style={{ marginTop: 10 }}>
                    <button className="btn" type="button" onClick={saveDefaults}>Save my details as defaults</button>
                    {profileMsg && <span className="hint">{profileMsg}</span>}
                  </div>
                </>
              )}
            </div>

            <div className="who">
              <div className="field"><label htmlFor="agent-email">Send to (listing agent email)</label><div className="in">
                <input id="agent-email" type="email" placeholder="agent@brokerage.com" value={agentEmail}
                  onChange={(e) => setAgentEmail(e.target.value)} aria-invalid={!!agentEmail && !emailOk} /></div></div>
              <div className="field"><label htmlFor="approver">Approved by</label><div className="in">
                <input id="approver" type="text" placeholder="Your name" value={approver} onChange={(e) => setApprover(e.target.value)} /></div></div>
            </div>
            <div className="field" style={{ marginTop: 8 }}><label htmlFor="subject">Email subject</label><div className="in">
              <input id="subject" type="text" value={subject} onChange={(e) => { setSubject(e.target.value); setSubjectDirty(true); }} /></div></div>
            {canEmail && unfilled.length > 0 && (
              <div className="sendfrom" style={{ color: "var(--warn)" }}>
                Fill in {unfilled.join(", ")} before sending (edit the fields on the left or the letter itself).
              </div>
            )}
            <div className="sendfrom">
              {canEmail ? <>Sends from <b>{email?.sender}</b> via Gmail. A copy stays in your Sent folder and replies come to your inbox.</>
                : <>Email isn&apos;t set up on the server, so approvals are logged but not sent.
                  {email?.missing?.length ? <> Missing on sprev-api: <b>{email.missing.join(", ")}</b>.</> : null}</>}
            </div>
            <div className="actions">
              <label className="approve" htmlFor="approveBox">
                <input type="checkbox" id="approveBox" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
                I reviewed the numbers and approve this offer
              </label>
              {aiAvailable && <button className="btn" type="button" onClick={() => generate(true)} disabled={loading}>Polish with Claude</button>}
              <button className="btn" type="button" onClick={() => generate(false)} disabled={loading}>Regenerate</button>
              <button className="btn" type="button" onClick={copy}>{copied}</button>
              {canEmail ? (
                <>
                  <button className="btn" type="button" disabled={!ready} onClick={() => approve(false)}>Approve, don&apos;t send</button>
                  <button className="btn primary" type="button" style={{ padding: "9px 18px" }}
                    disabled={!ready || !emailOk || unfilled.length > 0} onClick={() => setConfirming(true)}>Approve &amp; send…</button>
                </>
              ) : (
                <button className="btn primary" type="button" style={{ padding: "9px 18px" }}
                  disabled={!ready} onClick={() => approve(false)}>Approve &amp; log</button>
              )}
            </div>
            {confirming && (
              <div className="confirm" role="alertdialog" aria-label="Confirm sending the offer">
                <div>Send the <b>{offer.label.toLowerCase()} offer of {usd(offer.price)}</b> for {p.street} to <b>{agentEmail.trim()}</b> from <b>{email?.sender}</b>?
                  {attachPdf && form ? <> The unsigned <b>Proposal to Purchase PDF</b> is attached.</> : null}
                  {" "}This emails the agent immediately and can&apos;t be unsent.</div>
                <div className="confirm-actions">
                  <button className="btn" type="button" onClick={() => setConfirming(false)}>Cancel</button>
                  <button className="btn primary" type="button" style={{ padding: "9px 18px" }} disabled={busy}
                    onClick={() => approve(true)}>{busy ? "Sending…" : "Send offer now"}</button>
                </div>
              </div>
            )}
            {status && (
              <div className={status.ok ? "status" : "error"}>
                {result?.status === "sent" && <b>Sent. </b>}{status.msg}
                {result?.status === "send_failed" && <> <button className="btn" type="button" style={{ marginLeft: 8 }} disabled={busy} onClick={retry}>Retry send</button></>}
                {result?.status === "approved_not_sent" && canEmail && !!result.sent_to && (
                  <> <button className="btn" type="button" style={{ marginLeft: 8 }} disabled={busy} onClick={retry}>Send this approval now</button></>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
