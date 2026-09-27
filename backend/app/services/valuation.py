"""Comparable-sales valuation.

1. Score each comp's similarity to the subject (0-99).
2. Keep comps scoring >= SIM_THRESHOLD, best MAX_USED of them.
3. Adjust each kept comp's price to the subject (size, beds, baths, condition).
4. Similarity-weighted mean = as-is value; weighted std dev = the range.
5. ARV = the same comps adjusted as if the subject were renovated.
"""
from __future__ import annotations

import math
from datetime import date

from ..models import CONDITION_RANK, Comp, PropertyProfile, RentEstimate, Valuation
from ..util import clamp, months_between

SIM_THRESHOLD = 70
MAX_USED = 6

# Adjustment grid. Tune these to your market; they're the levers a local appraiser would use.
PPSF_ADJ = 110        # $ per sq ft of living-area difference
BED_ADJ = 7500        # $ per bedroom
BATH_ADJ = 6000       # $ per bathroom
COND_STEP = 9000      # $ per condition step (Dated → Good → Updated → Renovated)


def similarity(subject: PropertyProfile, c: Comp, today: date) -> int:
    s = 100.0
    s -= c.distance_mi * 9
    s -= abs(c.sqft - subject.sqft) / max(subject.sqft, 1) * 60
    s -= abs(c.beds - subject.beds) * 7
    s -= abs(c.baths - subject.baths) * 5
    s -= months_between(c.sold_date, today) * 1.2
    s -= abs(c.year_built - subject.year_built) * 0.25
    if (c.units > 1) != (subject.units > 1):
        s -= 35  # multifamily vs single-family trade differently
    return int(clamp(round(s), 0, 99))


def value_property(subject: PropertyProfile, comps: list[Comp], rent: RentEstimate,
                   today: date | None = None) -> Valuation:
    today = today or date.today()
    subj_rank = CONDITION_RANK[subject.condition]
    scored: list[Comp] = []
    for c in comps:
        c = c.model_copy()
        c.similarity = similarity(subject, c, today)
        base = (c.sale_price + (subject.sqft - c.sqft) * PPSF_ADJ + (subject.beds - c.beds) * BED_ADJ
                + (subject.baths - c.baths) * BATH_ADJ)
        rank = CONDITION_RANK[c.condition]
        c.adjusted_as_is = round(base + (subj_rank - rank) * COND_STEP)
        c.adjusted_arv = round(base + (3 - rank) * COND_STEP * 0.9)
        scored.append(c)

    scored.sort(key=lambda c: c.similarity or 0, reverse=True)
    similar = [c for c in scored if (c.similarity or 0) >= SIM_THRESHOLD]
    used = similar[:MAX_USED]
    if not used:  # nothing close: fall back to the best three so there's still a number, with low confidence
        used = scored[:3]
    for c in used:
        c.used = True

    w = sum(c.similarity or 1 for c in used) or 1
    val = sum(c.adjusted_as_is * (c.similarity or 1) for c in used) / w
    arv = max(val, sum(c.adjusted_arv * (c.similarity or 1) for c in used) / w)
    sd = math.sqrt(sum((c.similarity or 1) * (c.adjusted_as_is - val) ** 2 for c in used) / w)
    cv = sd / val if val else 1

    comp_conf = min(1, len(similar[:MAX_USED]) / 5) * 50 + clamp(1 - cv / 0.09, 0, 1) * 50
    width = (rent.high - rent.low) / rent.monthly if rent.monthly else 1
    rent_conf = clamp(1 - (width - 0.05) / 0.15, 0, 1) * 100
    penalty = sum(4 for f in subject.flags if any(k in f.lower() for k in ("unconfirmed", "septic", "quote", "confirm")))
    if subject.source.synthetic:
        penalty += 10
    conf = int(clamp(round(comp_conf * 0.6 + rent_conf * 0.4 - penalty), 20, 96))

    return Valuation(
        comps=scored, as_is_value=round(val), value_low=round(val - sd), value_high=round(val + sd), arv=round(arv),
        spread_pct=cv, comps_found=len(scored), comps_similar=len(similar), comps_used=len(used),
        comp_confidence=round(comp_conf, 1), rent_confidence=round(rent_conf, 1), confidence=conf,
    )
