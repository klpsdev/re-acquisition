"""Built-in sample data: three South Jersey properties plus a synthetic fallback.

Every figure here is illustrative. Any address that isn't one of the three
samples gets a deterministic synthetic profile derived from a hash of the
address, clearly marked `synthetic=True`, so the full workflow can be demoed.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re
from dataclasses import dataclass, field
from datetime import date

from ..models import Comp, Neighborhood, PropertyProfile, RentEstimate, SourceNote
from ..util import months_before

TODAY = date.today()


@dataclass
class _Sample:
    key: str
    street: str
    city: str
    county: str
    zip: str
    property_type: str
    units: int
    beds: float
    baths: float
    sqft: int
    lot: str
    year_built: int
    list_price: float
    status: str
    dom: int
    tax: float
    insurance: float
    rent: float
    rent_low: float
    rent_high: float
    rent_note: str
    rehab: float
    condition: str
    utilities: str
    flags: list[str]
    tract: dict
    comps: list[tuple] = field(default_factory=list)


# comps: (address, dist_mi, beds, baths, sqft, year, condition, months_ago, sale_price, units)
SAMPLES: list[_Sample] = [
    _Sample(
        key="woodbury", street="218 Carpenter St", city="Woodbury", county="Gloucester County", zip="08096",
        property_type="Two-family", units=2, beds=4, baths=2, sqft=1980, lot="0.11 ac", year_built=1925,
        list_price=285000, status="Active", dom=23, tax=6900, insurance=2400,
        rent=3000, rent_low=2850, rent_high=3150, rent_note="Unit A 2bd $1,550 · Unit B 2bd $1,450",
        rehab=14000, condition="Dated", utilities="Public sewer & water",
        flags=["Pre-1978: NJ lead-safe inspection at tenant turnover", "Separate electric meters"],
        tract=dict(name="Census tract 5012, Gloucester Co.", inc=71400, inc_g=.118, own=.52, vac=.041,
                   rent=1480, pop=.012, pov=.108, commute=24),
        comps=[
            ("104 Hopkins St", .3, 4, 2, 1860, 1920, "Updated", 3, 292000, 2),
            ("37 Glover St", .5, 4, 2, 2050, 1930, "Dated", 5, 268500, 2),
            ("512 N Broad St", .8, 5, 2, 2240, 1910, "Updated", 7, 309000, 2),
            ("29 Cooper St", .4, 4, 2, 1900, 1925, "Dated", 9, 262000, 2),
            ("66 Delaware St", 1.1, 4, 2, 1780, 1948, "Renovated", 4, 318000, 2),
            ("9 Aberdeen Pl", 1.6, 3, 1.5, 1540, 1955, "Updated", 6, 251000, 1),
            ("301 Glover St", .6, 4, 2, 2010, 1915, "Dated", 11, 258000, 2),
        ]),
    _Sample(
        key="deptford", street="47 Hessian Ave", city="Deptford Township", county="Gloucester County", zip="08096",
        property_type="Single-family", units=1, beds=3, baths=1.5, sqft=1620, lot="0.29 ac", year_built=1968,
        list_price=309900, status="Active · price cut", dom=41, tax=7400, insurance=1900,
        rent=2650, rent_low=2450, rent_high=2800, rent_note="3bd SFR, garage, fenced yard",
        rehab=22000, condition="Dated", utilities="Public sewer & water",
        flags=["Inground pool: permit status unconfirmed", "Pool removal quote needed"],
        tract=dict(name="Census tract 5014.02, Gloucester Co.", inc=88900, inc_g=.094, own=.78, vac=.036,
                   rent=1720, pop=.018, pov=.061, commute=27),
        comps=[
            ("12 Fox Run Rd", .4, 3, 1.5, 1580, 1966, "Dated", 4, 296000, 1),
            ("210 Almonesson Rd", .9, 3, 2, 1700, 1972, "Updated", 6, 329000, 1),
            ("8 Cooper Ave", .6, 3, 1, 1450, 1962, "Dated", 8, 271500, 1),
            ("55 Hessian Ave", .2, 3, 1.5, 1640, 1968, "Updated", 2, 318000, 1),
            ("119 Wilson Ln", 1.3, 4, 2, 1920, 1975, "Renovated", 5, 362000, 1),
            ("31 Blackwood Rd", 2.4, 3, 1.5, 1600, 1959, "Dated", 10, 279000, 1),
            ("402 Mantua Pk", 1.8, 2, 1, 1100, 1950, "Dated", 3, 219000, 1),
        ]),
    _Sample(
        key="sicklerville", street="16 Laurel Oak Ct", city="Sicklerville", county="Camden County", zip="08081",
        property_type="Single-family", units=1, beds=4, baths=2.5, sqft=2240, lot="0.46 ac", year_built=1994,
        list_price=339000, status="Active", dom=12, tax=8300, insurance=2100,
        rent=2950, rent_low=2800, rent_high=3100, rent_note="4bd colonial, 2-car garage",
        rehab=12000, condition="Good", utilities="Private septic · public water",
        flags=["Septic: order inspection & pump history", "Add septic-use clause to lease"],
        tract=dict(name="Census tract 6077.03, Camden Co.", inc=96200, inc_g=.131, own=.81, vac=.029,
                   rent=1860, pop=.034, pov=.052, commute=33),
        comps=[
            ("22 Laurel Oak Ct", .1, 4, 2.5, 2180, 1994, "Good", 5, 344000, 1),
            ("7 Pin Oak Dr", .5, 4, 2.5, 2300, 1997, "Updated", 3, 359000, 1),
            ("140 Sicklerville Rd", 1.4, 4, 2, 2050, 1988, "Good", 8, 322000, 1),
            ("3 Birch Hollow Ct", .7, 4, 2.5, 2400, 2001, "Updated", 6, 368500, 1),
            ("58 Chestnut Ridge Dr", .9, 4, 2.5, 2210, 1995, "Good", 2, 338000, 1),
            ("11 Spring Ln", 2.8, 3, 2, 1760, 1979, "Dated", 9, 281000, 1),
        ]),
]


def _synthesize(address: str) -> _Sample:
    h = int(hashlib.sha256(address.lower().encode()).hexdigest()[:12], 16)
    rnd = random.Random(h)
    base = SAMPLES[h % len(SAMPLES)]
    s = copy.deepcopy(base)
    parts = [p.strip() for p in address.split(",") if p.strip()]
    s.key = "synthetic"
    s.street = parts[0] if parts else address
    s.city = parts[1] if len(parts) > 1 else base.city
    tail = " ".join(parts[2:]) if len(parts) > 2 else ""
    zm = re.search(r"\b(\d{5})\b", tail) or re.search(r"\b(\d{5})\b", address)
    if zm and zm.group(1) != base.zip:
        s.zip = zm.group(1)
        s.county = ""          # unknown; the Census connector fills the real county in live mode
    k = 0.9 + rnd.random() * 0.2
    s.sqft = round(base.sqft * k / 10) * 10
    s.list_price = round(base.list_price * (0.94 + rnd.random() * 0.12) / 100) * 100
    rk = 0.95 + rnd.random() * 0.1
    s.rent, s.rent_low, s.rent_high = (round(v * rk / 25) * 25 for v in (base.rent, base.rent_low, base.rent_high))
    s.tax = round(base.tax * (0.9 + rnd.random() * 0.2) / 10) * 10
    s.rehab = round(base.rehab * (0.7 + rnd.random() * 0.8) / 500) * 500
    s.dom = int(5 + rnd.random() * 50)
    s.comps = []
    for i, c in enumerate(base.comps):
        donor = base.comps[(i + 2) % len(base.comps)][0].split(" ", 1)[1]
        s.comps.append((f"{10 + int(rnd.random() * 490)} {donor}", round(c[1] * (0.7 + rnd.random() * 0.6), 1),
                        *c[2:8], round(c[8] * (0.95 + rnd.random() * 0.1) / 500) * 500, c[9]))
    return s


class SampleConnector:
    """Answers all four questions from the built-in samples. Always available."""
    name = "sample"

    def __init__(self) -> None:
        self._cache: dict[str, _Sample] = {}

    def available(self) -> bool:
        return True

    def _find(self, address: str) -> _Sample:
        key = address.strip().lower()
        if key in self._cache:
            return self._cache[key]
        hit = next((s for s in SAMPLES if s.street.lower() in key), None)
        s = hit or _synthesize(address)
        self._cache[key] = s
        return s

    def _note(self, s: _Sample, detail: str) -> SourceNote:
        synthetic = s.key == "synthetic"
        return SourceNote(provider="sample", detail=("Synthetic, generated from the address. " if synthetic else "Sample values. ") + detail,
                          as_of=TODAY, synthetic=synthetic)

    def property_profile(self, address: str) -> PropertyProfile:
        s = self._find(address)
        return PropertyProfile(
            address=address, street=s.street, city=s.city, state="NJ", zip=s.zip, county=s.county,
            property_type=s.property_type, units=s.units, beds=s.beds, baths=s.baths, sqft=s.sqft, lot=s.lot,
            year_built=s.year_built, condition=s.condition, utilities=s.utilities, list_price=s.list_price,
            status=s.status, days_on_market=s.dom, annual_tax=s.tax, annual_insurance=s.insurance,
            flags=list(s.flags), rehab_hint=s.rehab, source=self._note(s, "Listing and tax record."),
        )

    def rent_estimate(self, prop: PropertyProfile) -> RentEstimate:
        s = self._find(prop.address)
        return RentEstimate(monthly=s.rent, low=s.rent_low, high=s.rent_high, note=s.rent_note,
                            source=self._note(s, "Rent estimate."))

    def neighborhood(self, prop: PropertyProfile) -> Neighborhood:
        s = self._find(prop.address)
        t = s.tract
        return Neighborhood(
            tract_name=t["name"], median_household_income=t["inc"], income_growth_5y=t["inc_g"],
            median_gross_rent=t["rent"], rental_vacancy=t["vac"], owner_occupied=t["own"],
            population_change_5y=t["pop"], poverty_rate=t["pov"], mean_commute_min=t["commute"],
            source=self._note(s, "Modeled on ACS 5-year tract fields."),
        )

    def comps(self, prop: PropertyProfile) -> list[Comp]:
        s = self._find(prop.address)
        return [
            Comp(address=c[0], distance_mi=c[1], beds=c[2], baths=c[3], sqft=c[4], year_built=c[5],
                 condition=c[6], sold_date=months_before(TODAY, c[7]), sale_price=c[8], units=c[9])
            for c in s.comps
        ]
