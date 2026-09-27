"""Chooses which connector answers each question, with fallbacks.

In DATA_MODE=sample everything comes from the built-in samples.
In DATA_MODE=live each question walks a chain of configured providers and
falls back to sample data (flagged synthetic) only if none can answer:

  property profile : RentCast  → sample
  listing / price  : RESO MLS  (enriches the profile when configured)
  rent             : RentCast  → sample
  neighborhood     : Census ACS → sample
  comps            : RESO MLS closed sales → RentCast listings → sample
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import Settings
from ..models import Comp, Neighborhood, PropertyProfile, RentEstimate
from .census import CensusConnector
from .rentcast import RentCastConnector
from .reso import ResoConnector
from .sample import SampleConnector

log = logging.getLogger(__name__)


@dataclass
class DataBundle:
    property: PropertyProfile
    rent: RentEstimate
    neighborhood: Neighborhood
    comps: list[Comp]
    trail: list[str] = field(default_factory=list)   # which provider answered what, and failures


class ConnectorRegistry:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.sample = SampleConnector()
        self.census = CensusConnector(settings)
        self.rentcast = RentCastConnector(settings)
        self.reso = ResoConnector(settings)
        self._cache: dict[str, DataBundle] = {}

    @property
    def live(self) -> bool:
        return self.s.data_mode.lower() == "live"

    def status(self) -> list[dict]:
        rows = [
            ("sample", "Built-in sample data", True, "Always on; fallback for everything"),
            ("census_acs", "US Census ACS 5-year (tract)", self.live and self.census.available(), "Neighborhood stats; free key"),
            ("rentcast", "RentCast", self.live and self.rentcast.available(), "Property record, rent AVM, value comps"),
            ("reso_mls", "MLS via RESO Web API / Bridge", self.live and self.reso.available(), "Closed-sale comps, active listing"),
        ]
        return [dict(id=i, name=n, active=a, provides=p) for i, n, a, p in rows]

    def _chain(self, label: str, trail: list[str], steps):
        for conn, fn in steps:
            if conn is not self.sample and not (self.live and conn.available()):
                continue
            try:
                out = fn()
            except Exception as e:  # noqa: BLE001 - a provider failure should never sink the analysis
                log.warning("%s via %s failed: %s", label, conn.name, e)
                msg = " ".join(str(e).split())[:220]
                trail.append(f"{label}: {conn.name} failed: {msg or type(e).__name__}")
                continue
            if out:
                trail.append(f"{label}: {conn.name}")
                return out
            if conn is not self.sample:
                trail.append(f"{label}: {conn.name} found no match for this address")
        raise RuntimeError(f"No provider could answer {label}")

    def gather(self, address: str) -> DataBundle:
        key = address.strip().lower()
        if key in self._cache:
            return self._cache[key]
        trail: list[str] = []
        prop = self._chain("property", trail, [
            (self.rentcast, lambda: self.rentcast.property_profile(address)),
            (self.sample, lambda: self.sample.property_profile(address)),
        ])

        if self.live and self.reso.available():
            try:
                lst = self.reso.active_listing(prop)
                if lst:
                    prop.list_price = lst.get("ListPrice") or prop.list_price
                    prop.days_on_market = lst.get("DaysOnMarket") or prop.days_on_market
                    prop.status = lst.get("StandardStatus") or prop.status
                    trail.append("listing: reso_mls")
            except Exception as e:  # noqa: BLE001
                trail.append(f"listing: reso_mls failed: {' '.join(str(e).split())[:220]}")

        if not prop.annual_insurance:
            prop.annual_insurance = round(max(1200, prop.sqft * 0.9 + prop.units * 300), -1)
            trail.append("insurance: estimated from size")

        rent = self._chain("rent", trail, [
            (self.rentcast, lambda: self.rentcast.rent_estimate(prop)),
            (self.sample, lambda: self.sample.rent_estimate(prop)),
        ])
        nb = self._chain("neighborhood", trail, [
            (self.census, lambda: self.census.neighborhood(prop)),
            (self.sample, lambda: self.sample.neighborhood(prop)),
        ])
        comps = self._chain("comps", trail, [
            (self.reso, lambda: self.reso.comps(prop)),
            (self.rentcast, lambda: self.rentcast.comps(prop)),
            (self.sample, lambda: self.sample.comps(prop)),
        ])
        bundle = DataBundle(prop, rent, nb, comps, trail)
        if not any("failed" in t for t in trail):   # retry failed providers on the next run
            self._cache[key] = bundle
        return bundle
