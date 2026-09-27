"use client";

import { pct, usd, usdK } from "@/lib/format";
import type { Analysis, AnalysisSummary, ProvidersResponse, Tier } from "@/lib/types";

export default function Rail({ a, tier, recent, providers, onOpen }: {
  a: Analysis; tier: Tier; recent: AnalysisSummary[]; providers: ProvidersResponse | null; onOpen: (id: string) => void;
}) {
  const v = a.valuation, u = a.underwriting, p = a.property;
  const sel = a.offers.find((o) => o.tier === tier)!;
  const binding = u.constraints.find((c) => c.binding)?.name ?? "";
  const c = v.confidence, r = 26, C = 2 * Math.PI * r;
  const col = c >= 75 ? "var(--good)" : c >= 55 ? "var(--warn)" : "var(--bad)";
  return (
    <aside className="rail">
      <section className="card sum"><div className="card-b">
        <div className="eyebrow">Maximum allowable offer</div>
        <div className="big num">{u.mao ? usd(u.mao) : "No deal"}</div>
        <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
          {u.mao ? `${p.list_price ? pct(u.mao / p.list_price) + " of list · " : ""}capped by ${binding.toLowerCase()}` : "Criteria cannot be met at any price"}
        </div>
        <dl className="kv" style={{ marginTop: 14 }}>
          <dt>List price</dt><dd className="num">{usd(p.list_price)}</dd>
          <dt>As-is value</dt><dd className="num">{usdK(v.value_low)}–{usdK(v.value_high)}</dd>
          <dt>After-repair value</dt><dd className="num">{usdK(v.arv)}</dd>
          <dt>Rent</dt><dd className="num">{usd(a.rent.monthly)}/mo</dd>
          <dt>Rehab</dt><dd className="num">{usd(a.rehab_estimate)}</dd>
          <div className="sep" />
          <dt>Selected offer</dt><dd className="num" style={{ color: "var(--accent)", fontWeight: 600 }}>{usd(sel.price)}</dd>
        </dl>
      </div></section>

      <section className="card"><div className="card-b">
        <div className="eyebrow" style={{ marginBottom: 10 }}>Underwriting confidence</div>
        <div className="conf">
          <svg className="ring" viewBox="0 0 64 64" aria-label={`${c}% confidence`}>
            <circle cx={32} cy={32} r={r} fill="none" stroke="var(--line)" strokeWidth={6} />
            <circle cx={32} cy={32} r={r} fill="none" stroke={col} strokeWidth={6} strokeLinecap="round"
              strokeDasharray={`${(C * c) / 100} ${C}`} transform="rotate(-90 32 32)" />
            <text x={32} y={37} textAnchor="middle" fontSize={15} fontWeight={600} fill="var(--ink)" fontFamily="var(--mono)">{c}%</text>
          </svg>
          <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
            Comps {Math.round(v.comp_confidence)}/100 ({v.comps_used} used, ±{pct(v.spread_pct)} spread) · rent {Math.round(v.rent_confidence)}/100
            {p.source.synthetic ? " · synthetic data penalty" : ""}
          </div>
        </div>
      </div></section>

      <section className="card"><div className="card-b">
        <div className="eyebrow" style={{ marginBottom: 10 }}>Primary risks</div>
        <ul className="risks">
          {a.risks.map((k) => (
            <li key={k.text}><i className={k.severity === "high" ? "h" : k.severity === "medium" ? "m" : "l"} /><span>{k.text}</span></li>
          ))}
        </ul>
      </div></section>

      {recent.length > 0 && (
        <section className="card"><div className="card-b">
          <div className="eyebrow" style={{ marginBottom: 6 }}>Recent analyses</div>
          <ul className="recent">
            {recent.map((x) => (
              <li key={x.id} onClick={() => onOpen(x.id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onOpen(x.id)}>
                <span className="ra">{x.address.split(",")[0]}</span><span className="num">{usdK(x.mao)}</span>
                <span className="rs">{x.status}</span><span className="rs num">{x.list_price ? usdK(x.list_price) + " list" : ""}</span>
              </li>
            ))}
          </ul>
        </div></section>
      )}

      {providers && (
        <section className="card"><div className="card-b">
          <div className="eyebrow" style={{ marginBottom: 8 }}>Data sources · {providers.data_mode} mode</div>
          <div className="providers">
            {providers.providers.map((pr) => (
              <div key={pr.id} title={pr.provides}><i className={pr.active ? "on" : ""} />{pr.name}</div>
            ))}
            <div><i className={providers.ai_explanations ? "on" : ""} />Claude explanations</div>
          </div>
        </div></section>
      )}
    </aside>
  );
}
