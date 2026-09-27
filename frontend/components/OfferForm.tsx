"use client";

import { usd } from "@/lib/format";
import type { AgencyRole, OfferForm } from "@/lib/types";

type Set = <K extends keyof OfferForm>(k: K, v: OfferForm[K]) => void;

const ROLES: [AgencyRole, string][] = [
  ["seller_agent", "Seller's agent"], ["buyer_agent", "Buyer's agent"],
  ["dual_agent", "Disclosed dual agent"], ["transaction_broker", "Transaction broker"],
];

function Txt({ id, label, value, onChange, wide, placeholder }: {
  id: string; label: string; value: string; onChange: (v: string) => void; wide?: boolean; placeholder?: string;
}) {
  return (
    <div className={`field ${wide ? "span2" : ""}`}><label htmlFor={id}>{label}</label>
      <div className="in"><input id={id} type="text" value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)} /></div></div>
  );
}

function Area({ id, label, value, onChange, hint }: {
  id: string; label: string; value: string; onChange: (v: string) => void; hint?: string;
}) {
  return (
    <div className="field span2"><label htmlFor={id}>{label}{hint && <span className="hint"> · {hint}</span>}</label>
      <div className="in"><textarea id={id} rows={2} value={value} onChange={(e) => onChange(e.target.value)} /></div></div>
  );
}

function Money({ id, label, value, onChange, readOnly }: {
  id: string; label: string; value: number | null; onChange?: (v: number | null) => void; readOnly?: boolean;
}) {
  return (
    <div className="field"><label htmlFor={id}>{label}</label>
      <div className="in"><span className="u">$</span>
        <input id={id} type="number" step={500} value={value ?? ""} readOnly={readOnly}
          onChange={(e) => onChange?.(e.target.value === "" ? null : Number(e.target.value))} /></div></div>
  );
}

function Check({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="chk" htmlFor={id}><input id={id} type="checkbox" checked={checked}
      onChange={(e) => onChange(e.target.checked)} />{label}</label>
  );
}

function Role({ id, label, value, onChange }: { id: string; label: string; value: AgencyRole | null; onChange: (v: AgencyRole | null) => void }) {
  return (
    <div className="field"><label htmlFor={id}>{label}</label><div className="in">
      <select id={id} value={value ?? ""} onChange={(e) => onChange((e.target.value || null) as AgencyRole | null)}>
        <option value="">Not stated</option>
        {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select></div></div>
  );
}

export default function OfferFormFields({ form, set, expectedBalance }: {
  form: OfferForm; set: Set; expectedBalance: number | null;
}) {
  return (
    <div className="ofs">
      <fieldset>
        <legend>Deal</legend>
        <div className="ofgrid">
          <Txt id="of-address" label="Property address" value={form.property_address} onChange={(v) => set("property_address", v)} wide />
          <Money id="of-price" label="Purchase price (from the selected offer)" value={form.price} readOnly />
          <Money id="of-dep" label="Deposit at contract signing" value={form.initial_deposit} onChange={(v) => set("initial_deposit", v)} />
          <Money id="of-dep2" label="Additional deposit" value={form.additional_deposit} onChange={(v) => set("additional_deposit", v)} />
          <Txt id="of-dep2d" label="Additional deposit due on or before" value={form.additional_deposit_date} onChange={(v) => set("additional_deposit_date", v)} />
          <div className="field"><label htmlFor="of-mtype">Financing</label><div className="in">
            <select id="of-mtype" value={form.mortgage_type ?? ""}
              onChange={(e) => set("mortgage_type", (e.target.value || null) as OfferForm["mortgage_type"])}>
              <option value="">None (cash)</option><option value="conventional">Conventional</option>
              <option value="fha">FHA</option><option value="va">VA</option><option value="other">Other mortgage</option>
            </select></div></div>
          <Money id="of-mamt" label="Mortgage amount" value={form.mortgage_amount} onChange={(v) => set("mortgage_amount", v)} />
          <div className="field"><label htmlFor="of-bal">Balance due at settlement</label>
            <div className="in"><span className="u">$</span><input id="of-bal" type="text" readOnly value={form.balance_due?.toLocaleString("en-US") ?? ""} /></div>
            {expectedBalance != null && expectedBalance < 0 && <div className="hint" style={{ color: "var(--bad)" }}>Deposits and mortgage exceed the price.</div>}
          </div>
          <Txt id="of-settle" label="Settlement on or before" value={form.settlement_date} onChange={(v) => set("settlement_date", v)} />
          <Area id="of-title" label="Settlement at the office of (title company)" hint="two lines" value={form.title_company} onChange={(v) => set("title_company", v)} />
        </div>
      </fieldset>

      <fieldset>
        <legend>Terms &amp; conditions</legend>
        <div className="ofgrid">
          <Txt id="of-incl" label="(1) Also included" value={form.also_included} onChange={(v) => set("also_included", v)} placeholder="e.g. refrigerator, washer, dryer" />
          <Txt id="of-excl" label="(1) Specifically excluded" value={form.specifically_excluded} onChange={(v) => set("specifically_excluded", v)} />
          <div className="field"><label htmlFor="of-poss">(2) Possession &amp; occupancy</label><div className="in">
            <select id="of-poss" value={form.possession ?? ""} onChange={(e) => set("possession", (e.target.value || null) as OfferForm["possession"])}>
              <option value="settlement">At time of settlement</option><option value="other">Other</option><option value="">Not stated</option>
            </select></div></div>
          {form.possession === "other"
            ? <Txt id="of-posso" label="Possession: other" value={form.possession_other} onChange={(v) => set("possession_other", v)} />
            : <div />}
          <div className="field span2"><label>(3) Inspections at buyer&apos;s expense</label>
            <div className="chks">
              <Check id="of-i1" label="Home inspection" checked={form.insp_home} onChange={(v) => set("insp_home", v)} />
              <Check id="of-i2" label="Wood-boring insects" checked={form.insp_wood_boring} onChange={(v) => set("insp_wood_boring", v)} />
              <Check id="of-i3" label="On-site waste disposal (septic)" checked={form.insp_septic} onChange={(v) => set("insp_septic", v)} />
            </div></div>
          <Txt id="of-io" label="Other buyer inspection" value={form.insp_other} onChange={(v) => set("insp_other", v)} placeholder="e.g. Sewer scope" />
          <div className="field"><label>Seller&apos;s expense</label>
            <div className="chks"><Check id="of-s1" label="Private well water analysis" checked={form.seller_well} onChange={(v) => set("seller_well", v)} /></div></div>
          <Txt id="of-so" label="Other seller inspection" value={form.seller_other} onChange={(v) => set("seller_other", v)} placeholder="e.g. CO / smoke certification" />
          <div className="field"><label htmlFor="of-assets">(4) Sufficient assets</label><div className="in">
            <select id="of-assets" value={form.assets ?? ""} onChange={(e) => set("assets", (e.target.value || null) as OfferForm["assets"])}>
              <option value="not_contingent">Not contingent on selling other property</option>
              <option value="sale_under_contract">Needs sale of a property under contract</option>
              <option value="sale_not_under_contract">Needs sale of a property not under contract</option>
              <option value="">Not stated</option>
            </select></div></div>
          {form.assets && form.assets !== "not_contingent" &&
            <Txt id="of-assetsp" label="Property being sold" value={form.assets_property} onChange={(v) => set("assets_property", v)} wide />}
          <Area id="of-other" label="(5) Other" hint="up to two lines on the form" value={form.other_terms} onChange={(v) => set("other_terms", v)} />
          <div className="field"><label htmlFor="of-valid">Offer valid for</label><div className="in">
            <input id="of-valid" type="number" min={1} value={form.valid_days ?? ""} onChange={(e) => set("valid_days", e.target.value === "" ? null : Number(e.target.value))} />
            <span className="u">days</span></div></div>
        </div>
      </fieldset>

      <fieldset>
        <legend>Brokerage</legend>
        <div className="ofgrid">
          <Txt id="of-firm" label="Your brokerage (name of firm)" value={form.firm_name} onChange={(v) => set("firm_name", v)} />
          <Txt id="of-lic" label="Licensee(s)" value={form.licensee} onChange={(v) => set("licensee", v)} />
          <Role id="of-frole" label="Your brokerage is working as" value={form.firm_role} onChange={(v) => set("firm_role", v)} />
          <Role id="of-lrole" label="Listing firm is working as" value={form.listing_role} onChange={(v) => set("listing_role", v)} />
          <Txt id="of-lfirm" label="Listing firm (information supplied by)" value={form.listing_firm} onChange={(v) => set("listing_firm", v)} wide />
          <Txt id="of-pfirm" label="Buyer authorizes (presenting firm)" value={form.presenting_firm} onChange={(v) => set("presenting_firm", v)} />
          <Txt id="of-foot" label="Company (form footer)" value={form.footer_company} onChange={(v) => set("footer_company", v)} />
          <Area id="of-paddr" label="Presenting agency address" hint="two lines" value={form.presenting_address} onChange={(v) => set("presenting_address", v)} />
          <Txt id="of-aname" label="Agent's name" value={form.agent_name} onChange={(v) => set("agent_name", v)} />
          <Txt id="of-acell" label="Agent's cell" value={form.agent_cell} onChange={(v) => set("agent_cell", v)} />
          <Txt id="of-aemail" label="Agent's email" value={form.agent_email} onChange={(v) => set("agent_email", v)} />
          <Txt id="of-otel" label="Office tel." value={form.office_tel} onChange={(v) => set("office_tel", v)} />
          <Txt id="of-ofax" label="Office fax" value={form.office_fax} onChange={(v) => set("office_fax", v)} />
        </div>
      </fieldset>

      <fieldset>
        <legend>Buyer</legend>
        <div className="ofgrid">
          <Txt id="of-buyer" label="Buyer (referred to as Buyer)" value={form.buyer_name} onChange={(v) => set("buyer_name", v)} />
          <Txt id="of-bdate" label="Date" value={form.buyer_date} onChange={(v) => set("buyer_date", v)} />
          <Txt id="of-b2" label="Second “Signed” line" value={form.buyer_signed_2} onChange={(v) => set("buyer_signed_2", v)} />
          <Txt id="of-b2d" label="Second date" value={form.buyer_date_2} onChange={(v) => set("buyer_date_2", v)} />
          <Area id="of-baddr" label="Buyer address" hint="two lines" value={form.buyer_address} onChange={(v) => set("buyer_address", v)} />
        </div>
        <p className="hint" style={{ marginTop: 8 }}>
          The buyer signature line stays blank; the PDF goes out unsigned for {usd(form.price)}. Sign it in DocuSign once terms are agreed.
        </p>
      </fieldset>
    </div>
  );
}
