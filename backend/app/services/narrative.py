"""The 'Why this number?' explanation and the offer letter."""
from __future__ import annotations

import json
from datetime import date, timedelta

from ..config import Settings
from ..models import Analysis, LetterTerms, Offer
from . import ai


def _k(x: float) -> str:
    return f"${round(x / 1000):,}K"


def explanation_facts(a: Analysis) -> dict:
    v, u, p = a.valuation, a.underwriting, a.property
    return {
        "address": p.address, "list_price": p.list_price, "days_on_market": p.days_on_market,
        "comps_found": v.comps_found, "comps_used": v.comps_used, "value_low": v.value_low, "value_high": v.value_high,
        "arv": v.arv, "rent_monthly": a.rent.monthly, "rent_low": a.rent.low, "annual_tax": p.annual_tax,
        "rehab": a.rehab_estimate, "mao": u.mao, "binding_constraint": next(c.name for c in u.constraints if c.binding),
        "offers": [{"tier": o.label, "price": o.price, "coc": round(o.economics.coc, 4), "dscr": round(o.economics.dscr, 2),
                    "meets": o.meets_criteria} for o in a.offers],
        "flags": p.flags,
    }


def template_explanation(a: Analysis) -> str:
    v, u, p, r = a.valuation, a.underwriting, a.property, a.rent
    bind = next(c.name for c in u.constraints if c.binding)
    t = next(o for o in a.offers if o.tier == "target")
    s = (f"{v.comps_used} of {v.comps_found} nearby sales were similar enough to use. Adjusted for size, bedrooms, "
         f"baths and condition, they put as-is value at {_k(v.value_low)}–{_k(v.value_high)} and after-repair value "
         f"near {_k(v.arv)}. With ${r.monthly:,.0f}/mo in rent, ${p.annual_tax:,.0f} in taxes and "
         f"${a.rehab_estimate:,.0f} of rehab, the highest price that clears every criterion is ${u.mao:,.0f}; "
         f"the binding rule is {bind}.")
    s += (f" At ${t.price:,.0f} the target offer {'meets' if t.meets_criteria else 'misses'} the criteria with "
          f"{t.economics.coc:.1%} cash-on-cash and a {t.economics.dscr:.2f}x DSCR; at the low rent estimate "
          f"(${r.low:,.0f}) cash-on-cash falls to {t.coc_at_low_rent:.1%}.")
    if p.list_price and u.mao / p.list_price < 0.88:
        s += f" The MAO is {1 - u.mao / p.list_price:.0%} below list, so passing is reasonable unless the seller is motivated."
    return s


def explain(settings: Settings, a: Analysis) -> tuple[str, str]:
    llm = ai.write(settings,
                   "Explain in 2 short paragraphs why the engine's MAO and target offer are what they are, "
                   "and the main uncertainty. Mention the binding constraint.",
                   json.dumps(explanation_facts(a), default=str))
    return (llm, "llm") if llm else (template_explanation(a), "template")


def letter(settings: Settings, a: Analysis, offer: Offer, terms: LetterTerms, polish: bool) -> tuple[str, str]:
    p = a.property
    buyer = terms.buyer or settings.buyer_entity
    today = date.today()
    expires = today + timedelta(days=2)
    emd = round(offer.price * terms.earnest_money_pct / 100 / 100) * 100
    extra: list[str] = []
    flags = " ".join(p.flags).lower()
    if "pool" in flags:
        extra.append("Seller to provide the original permit and final approval for the inground pool, "
                     "or evidence that no permit was required.")
    if "septic" in p.utilities.lower():
        extra.append("Offer is contingent on a satisfactory septic inspection, including a pump-out and "
                     "hydraulic load test, at Buyer's expense.")
    if p.year_built < 1978:
        extra.append("Seller to disclose any known lead-based paint and provide any prior lead-safe "
                     "certification for the property.")
    greet = "[Agent first name]" if terms.agent_name.startswith("[") else terms.agent_name.split()[0]
    financing = terms.financing + ("" if terms.financing.lower().startswith("all cash")
                                   else "; appraisal and financing contingencies apply")
    occupancy = ("Subject to existing leases; Seller to provide copies of all leases, rent roll and security "
                 "deposit ledger" if p.units > 1 else "Delivered vacant at closing")
    listed = f", currently listed at ${p.list_price:,.0f}" if p.list_price else ""
    body = f"""{today:%B} {today.day}, {today.year}

{terms.agent_name}
Re: Offer to purchase {p.street}, {p.city}, {p.state} {p.zip}

Dear {greet},

On behalf of {buyer}, I am pleased to submit the following offer to purchase the above property{listed}.

  Purchase price:        ${offer.price:,.0f}
  Earnest money deposit: ${emd:,.0f} ({terms.earnest_money_pct:g}%), held in escrow within 3 business days of acceptance
  Financing:             {financing}
  Inspection period:     {terms.inspection_days} days from acceptance
  Closing:               On or before {terms.close_days} days from acceptance
  Attorney review:       Subject to the standard 3-business-day New Jersey attorney review period
  Occupancy:             {occupancy}
"""
    if extra:
        body += "\nAdditional conditions:\n" + "\n".join(f"  - {x}" for x in extra) + "\n"
    body += f"""
Our offer reflects recent comparable sales in the immediate area and the property's current condition, including an estimated ${a.rehab_estimate:,.0f} in needed repairs. {buyer} is an experienced local owner of rental property in South Jersey and can move quickly through inspection and closing.

This offer remains open until 5:00 PM Eastern on {expires:%B} {expires.day}, {expires.year}. Please let me know if the seller would like to discuss any of these terms.

Sincerely,

{terms.signer_name}
Authorized agent, {buyer}
{terms.signer_phone} · {terms.signer_email or settings.gmail_sender or settings.smtp_from or "[Email]"}"""
    if polish:
        llm = ai.write(settings, "Lightly polish the cover-letter wording of this offer letter. Keep every number, "
                       "date, term line and condition exactly as written. Return only the letter.", body, 1200)
        if llm:
            return llm, "llm"
    return body, "template"
