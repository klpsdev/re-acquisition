"""Four offer tiers around the MAO, plus risk flags and the neighborhood score."""
from __future__ import annotations

import math

from ..models import Neighborhood, Offer, PropertyProfile, RentEstimate, Risk, Underwriting, Valuation
from ..util import clamp
from .underwriting import economics

TIERS = [("aggressive", "Aggressive", 0.92), ("target", "Target", 0.96),
         ("competitive", "Competitive", 1.00), ("stretch", "Stretch", 1.04)]


def acceptance_likelihood(price: float, list_price: float | None, dom: int | None) -> int | None:
    """Rough odds a seller accepts, from price/list and days on market.

    A heuristic placeholder: replace with a model fit on your own offer history
    (offer %, DOM, season, list-price cuts → accepted?) once you have ~50 offers logged.
    """
    if not list_price:
        return None
    ratio = price / list_price
    center = 0.90 - ((dom or 25) - 25) / 400   # stale listings accept lower
    return int(clamp(round(100 / (1 + math.exp(-(ratio - center) * 18))), 2, 97))


def build_offers(prop: PropertyProfile, rent: RentEstimate, val: Valuation, uw: Underwriting) -> list[Offer]:
    c, mao = uw.criteria, uw.mao
    out: list[Offer] = []
    for tier, label, f in TIERS:
        price = round(mao * f / 1000) * 1000
        if tier == "competitive":
            price = mao
        if tier == "stretch" and prop.list_price:
            price = min(price, round(prop.list_price / 1000) * 1000)
        e = economics(prop, rent.monthly, price, uw.rehab, val.arv, c)
        lo = economics(prop, rent.low, price, uw.rehab, val.arv, c)
        meets = (e.coc >= c.target_coc / 100 - 1e-9 and e.dscr >= c.min_dscr - 1e-9
                 and price + uw.rehab <= val.arv * c.max_all_in_pct_arv / 100 + 1)
        ret_conf = val.confidence - max(0.0, (price / mao if mao else 2) - 0.92) * 140
        if lo.coc < c.target_coc / 100:
            ret_conf -= 6
        out.append(Offer(
            tier=tier, label=label, price=price,
            pct_of_list=price / prop.list_price if prop.list_price else None,
            pct_of_value=price / val.as_is_value if val.as_is_value else 0,
            meets_criteria=meets, economics=e, coc_at_low_rent=lo.coc,
            return_confidence=int(clamp(round(ret_conf), 15, 97)),
            acceptance_likelihood=acceptance_likelihood(price, prop.list_price, prop.days_on_market),
        ))
    return out


def demand_score(nb: Neighborhood) -> int:
    g = nb.income_growth_5y or 0
    v = nb.rental_vacancy if nb.rental_vacancy is not None else 0.05
    p = nb.population_change_5y or 0
    pov = nb.poverty_rate if nb.poverty_rate is not None else 0.08
    return int(clamp(round(50 + g * 150 + (0.05 - v) * 500 + p * 300 - (pov - 0.08) * 150), 10, 98))


def risks(prop: PropertyProfile, rent: RentEstimate, val: Valuation, uw: Underwriting, rehab: float) -> list[Risk]:
    out: list[Risk] = []
    if prop.source.synthetic:
        out.append(Risk(severity="high", text="Synthetic profile: numbers are illustrative only"))
    ref = prop.list_price or val.as_is_value
    if ref and prop.annual_tax / ref > 0.022:
        out.append(Risk(severity="high", text=f"Property tax is {prop.annual_tax / ref:.2%} of price, a large share of NOI"))
    elif rent.monthly:
        out.append(Risk(severity="medium", text=f"Property tax ${prop.annual_tax:,.0f}/yr is {prop.annual_tax / (rent.monthly * 12):.0%} of gross rent"))
    if prop.list_price and uw.mao and uw.mao / prop.list_price < 0.9:
        out.append(Risk(severity="high", text=f"MAO is {1 - uw.mao / prop.list_price:.0%} under list; low odds of acceptance"))
    if not uw.mao:
        out.append(Risk(severity="high", text="No price meets the current criteria"))
    if val.comps_similar < 5:
        out.append(Risk(severity="medium", text=f"Only {val.comps_similar} highly comparable sales"))
    for f in prop.flags:
        fl = f.lower()
        if any(k in fl for k in ("unconfirmed", "septic", "quote", "lead", "confirm")):
            out.append(Risk(severity="high" if "unconfirmed" in fl else "medium", text=f))
    if "unknown" in prop.utilities.lower():
        out.append(Risk(severity="medium", text="Sewer vs septic not confirmed"))
    out.append(Risk(severity="low", text=f"Rehab estimate ${rehab:,.0f} is unverified until a walkthrough"))
    return out[:7]
