"""Rules-based rehab estimate, used when no walkthrough number exists yet.

Replace with your contractor's line items once you have them; pass
`rehab_override` to /api/analyze or /recompute to use your own number.
"""
from __future__ import annotations

from ..models import PropertyProfile

PER_SQFT = {"Dated": 11.0, "Good": 5.0, "Updated": 2.0, "Renovated": 0.0}
POOL_REMOVAL = 12_000
LEAD_SAFE = 1_500  # NJ lead-safe inspection + typical remediation allowance, pre-1978 rentals


def estimate_rehab(prop: PropertyProfile) -> float:
    if prop.rehab_hint is not None:
        return prop.rehab_hint
    total = prop.sqft * PER_SQFT.get(prop.condition, 5.0)
    flags = " ".join(prop.flags).lower()
    if "pool" in flags:
        total += POOL_REMOVAL
    if prop.year_built < 1978:
        total += LEAD_SAFE
    return round(total / 500) * 500
