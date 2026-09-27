"use client";

import type { Analysis, Criteria, Offer, Tier } from "@/lib/types";
import { monthYear, pct, signedPct, usd, usdK } from "@/lib/format";

/* ---------------- Subject property ---------------- */
export function SubjectCard({ a }: { a: Analysis }) {
  const p = a.property;
  const warn = (f: string) => /unconfirmed|septic|lead|confirm/i.test(f);
  return (
    <section className="card">
      <div className="subject">
        <div className="left">
          <div className="eyebrow">
            {p.property_type}{p.units > 1 ? ` · ${p.units} units` : ""}{p.source.synthetic ? " · synthetic profile" : ""}
          </div>
          <h2>{p.street}</h2>
          <div className="town">{p.city}, {p.state} {p.zip}{p.county ? ` · ${p.county}` : ""}</div>
          <div className="facts">
            {[["Beds / baths", `${p.beds} / ${p.baths}`], ["Living area", `${p.sqft.toLocaleString()} sf`],
              ["Lot", p.lot || "—"], ["Built", String(p.year_built)]].map(([k, v]) => (
              <div className="fact" key={k}><div className="k">{k}</div><div className="v num">{v}</div></div>
            ))}
          </div>
          <div className="chips">
            {p.source.synthetic && <span className="chip bad">Synthetic data generated from the address</span>}
            <span className="chip">{p.utilities}</span>
            <span className="chip">Condition: {p.condition}</span>
            {p.flags.map((f) => <span key={f} className={`chip ${warn(f) ? "warn" : ""}`}>{f}</span>)}
          </div>
        </div>
        <div className="right">
          <div className="eyebrow" style={{ marginBottom: 10 }}>Listing &amp; carrying costs</div>
          <dl className="kv">
            <dt>List price</dt><dd className="num">{usd(p.list_price)}</dd>
            <dt>Status</dt><dd>{p.status}</dd>
            <dt>Days on market</dt><dd className="num">{p.days_on_market ?? "—"}</dd>
            <dt>List $/sf</dt><dd className="num">{p.list_price ? usd(p.list_price / p.sqft) : "—"}</dd>
            <div className="sep" />
            <dt>Property tax</dt><dd className="num">{usd(p.annual_tax)}/yr</dd>
            <dt>Insurance (est.)</dt><dd className="num">{usd(p.annual_insurance)}/yr</dd>
            <dt>Market rent</dt><dd className="num">{usd(a.rent.monthly)}/mo</dd>
            <dt style={{ gridColumn: "1/-1", fontSize: 12, color: "var(--faint)" }}>
              {a.rent.note} · range {usd(a.rent.low)}–{usd(a.rent.high)}
            </dt>
            <dt>Rehab estimate</dt><dd className="num">{usd(a.rehab_estimate)}</dd>
          </dl>
        </div>
      </div>
    </section>
  );
}

/* ---------------- Neighborhood ---------------- */
export function NeighborhoodCard({ a }: { a: Analysis }) {
  const n = a.neighborhood;
  const rows: [string, string, string, string][] = [
    ["Median household income", usd(n.median_household_income), `${signedPct(n.income_growth_5y)} over 5 yrs`,
      (n.income_growth_5y ?? 0) > 0 ? "up" : "dn"],
    ["Median gross rent", usd(n.median_gross_rent), `Subject at ${usd(a.rent.monthly / a.property.units)}/unit`, ""],
    ["Rental vacancy", pct(n.rental_vacancy), (n.rental_vacancy ?? 1) < 0.05 ? "Tight market" : "Soft market",
      (n.rental_vacancy ?? 1) < 0.05 ? "up" : "dn"],
    ["Owner-occupied", pct(n.owner_occupied, 0), (n.owner_occupied ?? 0) > 0.6 ? "Stable, owner-heavy" : "Renter-heavy", ""],
    ["Population change", signedPct(n.population_change_5y), "5-yr", (n.population_change_5y ?? 0) > 0 ? "up" : "dn"],
    ["Poverty rate", pct(n.poverty_rate), "Below federal poverty line", ""],
    ["Rent-to-income", n.median_gross_rent && n.median_household_income
      ? pct((n.median_gross_rent * 12) / n.median_household_income) : "—", "Tract median", ""],
    ["Mean commute", n.mean_commute_min ? `${Math.round(n.mean_commute_min)} min` : "—", "To work", ""],
  ];
  const s = n.demand_score ?? 0;
  return (
    <section className="card">
      <div className="card-h"><h2>Neighborhood scorecard</h2>
        <span className="src">{n.tract_name} · {n.source.provider === "census_acs" ? n.source.detail : "sample values"}</span></div>
      <div className="card-b">
        <div className="nb">
          {rows.map(([k, v, c, d]) => (
            <div className="m" key={k}><div className="k">{k}</div><div className="v num">{v}</div><div className={`c ${d}`}>{c}</div></div>
          ))}
        </div>
        <div className="score">
          <div><div className="eyebrow">Rental demand score</div>
            <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>{s} / 100</div></div>
          <div className="bar"><span style={{ width: `${s}%` }} /></div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- Comps ---------------- */
function CompChart({ a }: { a: Analysis }) {
  const v = a.valuation, list = a.property.list_price, mao = a.underwriting.mao;
  const vals = v.comps.map((c) => c.adjusted_as_is ?? c.sale_price)
    .concat([v.value_low, v.value_high, v.arv], list ? [list] : [], mao ? [mao] : []);
  let mn = Math.min(...vals), mx = Math.max(...vals);
  const pad = (mx - mn) * 0.08; mn -= pad; mx += pad;
  const W = 720, L = 16, R = 16, x = (n: number) => L + ((n - mn) / (mx - mn)) * (W - L - R);
  const step = mx - mn > 150000 ? 50000 : 25000;
  const ticks: number[] = [];
  for (let t = Math.ceil(mn / step) * step; t <= mx; t += step) ticks.push(t);
  const marker = (val: number, label: string, col: string, y: number) => (
    <g key={label}>
      <line x1={x(val)} x2={x(val)} y1={y + 6} y2={86} stroke={col} strokeWidth={1.5} strokeDasharray="3 3" />
      <text x={x(val)} y={y} textAnchor="middle" fontSize={11} fontWeight={600} fill={col}>{label}</text>
    </g>
  );
  const close = list && mao ? Math.abs(x(list) - x(mao)) < 70 : false;
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} 118`} role="img" aria-label="Adjusted comparable values with value range, MAO and list price">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={30} y2={86} stroke="var(--line)" />
            <text x={x(t)} y={102} textAnchor="middle" fontSize={11} fill="var(--faint)" fontFamily="var(--mono)">{usdK(t)}</text>
          </g>
        ))}
        <rect x={x(v.value_low)} y={36} width={x(v.value_high) - x(v.value_low)} height={44} rx={4} fill="var(--accent-soft)" />
        {v.comps.map((c, i) => (
          <circle key={c.address + i} cx={x(c.adjusted_as_is ?? c.sale_price)} cy={58 + ((i % 3) - 1) * 9} r={c.used ? 6 : 4.5}
            fill={c.used ? "var(--accent)" : "var(--panel)"} stroke={c.used ? "var(--panel)" : "var(--faint)"} strokeWidth={1.5}>
            <title>{`${c.address}: ${usd(c.adjusted_as_is)} adjusted`}</title>
          </circle>
        ))}
        {mao > 0 && marker(mao, `MAO ${usdK(mao)}`, "var(--good)", 14)}
        {list && marker(list, `List ${usdK(list)}`, "var(--muted)", close ? 26 : 14)}
      </svg>
    </div>
  );
}

export function CompsCard({ a }: { a: Analysis }) {
  const v = a.valuation;
  const src = a.property.source.provider === "sample" ? "Sample sales" : "Sold within 12 months";
  return (
    <section className="card">
      <div className="card-h"><h2>Comparable sales</h2><span className="src">{src} · adjusted to subject</span></div>
      <div className="card-b">
        <div className="funnel">
          <span><b>{v.comps_found}</b> sales found</span><span>→</span>
          <span><b>{v.comps_similar}</b> similar (score ≥ 70)</span><span>→</span>
          <span><b>{v.comps_used}</b> weighted into value</span>
          <span style={{ marginLeft: "auto" }}>As-is value <b>{usdK(v.value_low)}–{usdK(v.value_high)}</b> · ARV <b>{usdK(v.arv)}</b></span>
        </div>
        <CompChart a={a} />
        <div className="tbl-wrap">
          <table>
            <thead><tr><th>Address</th><th className="r">Dist</th><th className="r">Bd/Ba</th><th className="r">Sq ft</th>
              <th className="r">Built</th><th>Condition</th><th className="r">Sold</th><th className="r">Sale price</th>
              <th className="r">Adjusted</th><th>Similarity</th></tr></thead>
            <tbody>
              {v.comps.map((c, i) => (
                <tr key={c.address + i} className={c.used ? "" : "excluded"}>
                  <td><span className="addr-c">{c.address}</span>{c.units > 1 && <> <span className="chip" style={{ padding: "0 6px" }}>{c.units}F</span></>}</td>
                  <td className="r num">{c.distance_mi.toFixed(1)} mi</td>
                  <td className="r num">{c.beds}/{c.baths}</td>
                  <td className="r num">{c.sqft.toLocaleString()}</td>
                  <td className="r num">{c.year_built}</td>
                  <td>{c.condition}</td>
                  <td className="r num">{monthYear(c.sold_date)}</td>
                  <td className="r num">{usd(c.sale_price)}</td>
                  <td className="r num">{usd(c.adjusted_as_is)}</td>
                  <td><span className="sim"><span className="b"><span style={{ width: `${c.similarity ?? 0}%` }} /></span>
                    <span className="num">{c.similarity}</span></span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/* ---------------- Underwriting ---------------- */
const FIELDS: [keyof Criteria, string, string, number][] = [
  ["interest_rate", "Interest rate", "%", 0.125], ["down_payment", "Down payment", "%", 1],
  ["closing_costs", "Closing costs (of price)", "%", 0.5], ["target_coc", "Target cash-on-cash", "%", 0.5],
  ["min_dscr", "Minimum DSCR", "x", 0.05], ["vacancy", "Vacancy (of rent)", "%", 1],
  ["maintenance_capex", "Maint. + capex (of rent)", "%", 1], ["max_all_in_pct_arv", "Max all-in (of ARV)", "%", 1],
];

export function UnderwritingCard({ a, criteria, onCriteria, rehab, onRehab, busy }: {
  a: Analysis; criteria: Criteria; onCriteria: (c: Criteria) => void;
  rehab: string; onRehab: (v: string) => void; busy: boolean;
}) {
  const u = a.underwriting, e = u.at_mao, c = u.criteria;
  return (
    <section className="card">
      <div className="card-h"><h2>Underwriting</h2>
        <span className="src">{busy ? <span className="recomputing">Recomputing…</span> : "Computed in Python · edit any criterion"}</span></div>
      <div className="card-b">
        <div className="eyebrow" style={{ marginBottom: 8 }}>Investment criteria</div>
        <div className="crit">
          {FIELDS.map(([k, label, unit, step]) => (
            <div className="field" key={k}>
              <label htmlFor={`c-${k}`}>{label}</label>
              <div className="in">
                <input id={`c-${k}`} type="number" step={step} value={criteria[k]} inputMode="decimal"
                  onChange={(ev) => { const n = parseFloat(ev.target.value); if (!isNaN(n)) onCriteria({ ...criteria, [k]: n }); }} />
                <span className="u">{unit}</span>
              </div>
            </div>
          ))}
          <div className="field">
            <label htmlFor="c-mgmt">Management (of rent)</label>
            <div className="in"><input id="c-mgmt" type="number" step={1} value={criteria.management}
              onChange={(ev) => { const n = parseFloat(ev.target.value); if (!isNaN(n)) onCriteria({ ...criteria, management: n }); }} />
              <span className="u">%</span></div>
          </div>
          <div className="field">
            <label htmlFor="c-rehab">Rehab override</label>
            <div className="in"><input id="c-rehab" type="number" step={500} placeholder={String(a.rehab_estimate)} value={rehab}
              onChange={(ev) => onRehab(ev.target.value)} /><span className="u">$</span></div>
          </div>
        </div>
        <div className="mao">
          {u.constraints.map((k) => (
            <div key={k.name} className={`cons ${k.binding ? "bind" : ""}`}>
              <div className="k">Max price for {k.name}</div>
              <div className="v num">{k.max_price > 0 ? usd(k.max_price) : "None"}</div>
              <div className="t">{k.binding ? "Binding constraint" : ""}</div>
            </div>
          ))}
        </div>
        <div className="pl">
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Annual operating statement at MAO</div>
            <dl className="kv">
              <dt>Gross rent</dt><dd className="num">{usd(e.gross_rent)}</dd>
              <dt>Vacancy ({c.vacancy}%)</dt><dd className="num">−{usd(e.vacancy)}</dd>
              <dt>Property tax</dt><dd className="num">−{usd(e.tax)}</dd>
              <dt>Insurance</dt><dd className="num">−{usd(e.insurance)}</dd>
              <dt>Maintenance + capex ({c.maintenance_capex}%)</dt><dd className="num">−{usd(e.maintenance_capex)}</dd>
              {e.septic_reserve > 0 && <><dt>Septic pumping reserve</dt><dd className="num">−{usd(e.septic_reserve)}</dd></>}
              <dt>Management</dt><dd className="num">{e.management ? "−" + usd(e.management) : "Self-managed"}</dd>
              <div className="sep" />
              <dt><b>Net operating income</b></dt><dd className="num"><b>{usd(e.noi)}</b></dd>
              <dt>Debt service</dt><dd className="num">−{usd(e.debt_service)}</dd>
              <dt><b>Cash flow</b></dt>
              <dd className={`num ${e.cash_flow >= 0 ? "pass" : "fail"}`}><b>{usd(e.cash_flow)}</b>{" "}
                <span style={{ color: "var(--faint)", fontWeight: 400 }}>({usd(e.cash_flow / 12)}/mo)</span></dd>
            </dl>
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Cash to close &amp; returns at MAO</div>
            <dl className="kv">
              <dt>Purchase price (MAO)</dt><dd className="num">{usd(u.mao)}</dd>
              <dt>Down payment ({c.down_payment}%)</dt><dd className="num">{usd(e.down_payment)}</dd>
              <dt>Closing costs ({c.closing_costs}%)</dt><dd className="num">{usd(e.closing_costs)}</dd>
              <dt>Rehab</dt><dd className="num">{usd(e.rehab)}</dd>
              <div className="sep" />
              <dt><b>Total cash in</b></dt><dd className="num"><b>{usd(e.cash_in)}</b></dd>
              <dt>Loan @ {c.interest_rate}%, {c.loan_years} yr</dt><dd className="num">{usd(e.loan)}</dd>
              <dt>Cash-on-cash</dt><dd className="num">{pct(e.coc)}</dd>
              <dt>DSCR</dt><dd className="num">{e.dscr.toFixed(2)}x</dd>
              <dt>Cap rate (price + rehab)</dt><dd className="num">{pct(e.cap_rate)}</dd>
              <dt>All-in vs ARV</dt><dd className="num">{pct(e.all_in_pct_arv, 0)}</dd>
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- Offers ---------------- */
function Meter({ label, val, col }: { label: string; val: number; col: string }) {
  return (
    <div className="meter">
      <div className="row"><span>{label}</span><b>{val}%</b></div>
      <div className="b"><span style={{ width: `${val}%`, background: col }} /></div>
    </div>
  );
}

export function OffersCard({ a, selected, onSelect }: { a: Analysis; selected: Tier; onSelect: (t: Tier) => void }) {
  const u = a.underwriting, p = a.property;
  const gap = p.list_price ? u.mao / p.list_price : 1;
  return (
    <section className="card">
      <div className="card-h"><h2>Offer scenarios</h2><span className="src">Built around the maximum allowable offer</span></div>
      <div className="card-b">
        {!u.mao ? <div className="banner">No price satisfies the current criteria. Loosen the criteria or pass on this property.</div>
          : gap < 0.88 ? <div className="banner">MAO is {pct(1 - gap, 0)} below list. Offers at these levels may not be accepted;
            passing is reasonable unless the seller is motivated ({p.days_on_market ?? "?"} days on market).</div> : null}
        <div className="offers">
          {a.offers.map((o: Offer) => {
            const col = o.return_confidence >= 75 ? "var(--good)" : o.return_confidence >= 55 ? "var(--warn)" : "var(--bad)";
            const on = selected === o.tier;
            return (
              <button key={o.tier} type="button" className="offer" aria-pressed={on} onClick={() => onSelect(o.tier)}>
                <div className="tier"><b>{o.label}</b>
                  <span className={`chip ${o.meets_criteria ? "good" : "bad"}`} style={{ padding: "1px 8px" }}>
                    {o.meets_criteria ? "Meets criteria" : "Below criteria"}</span></div>
                <div><div className="price num">{usd(o.price)}</div>
                  <div className="pct">{o.pct_of_list != null ? `${pct(o.pct_of_list)} of list · ` : ""}{pct(o.pct_of_value, 0)} of value</div></div>
                <dl className="kv">
                  <dt>Cash flow</dt><dd className={`num ${o.economics.cash_flow >= 0 ? "" : "fail"}`}>{usd(o.economics.cash_flow / 12)}/mo</dd>
                  <dt>Cash-on-cash</dt><dd className="num">{pct(o.economics.coc)}</dd>
                  <dt>DSCR</dt><dd className="num">{o.economics.dscr.toFixed(2)}x</dd>
                  <dt>Cash in</dt><dd className="num">{usdK(o.economics.cash_in)}</dd>
                </dl>
                <Meter label="Return confidence" val={o.return_confidence} col={col} />
                {o.acceptance_likelihood != null && <Meter label="Acceptance likelihood" val={o.acceptance_likelihood} col="var(--muted)" />}
                <div className="sel">{on ? "Selected" : "Select offer"}</div>
              </button>
            );
          })}
        </div>
        <div className="why">
          <div className="eyebrow">Why {usd(u.mao)} max?</div>
          {a.explanation.split(/\n\n+/).map((para, i) => <p key={i}>{para}</p>)}
          <p style={{ fontSize: 12, color: "var(--faint)" }}>
            {a.explanation_source === "llm" ? "Written by Claude from the computed numbers." : "Templated explanation. Set ANTHROPIC_API_KEY to have Claude write it from the same numbers."}
          </p>
        </div>
      </div>
    </section>
  );
}
