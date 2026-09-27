"""RentCast connector: property records, sale listing, rent AVM and value comps.

Docs: https://developers.rentcast.io/reference
Auth: X-Api-Key header. The free tier has a small monthly request allowance,
so the registry caches results per address for the life of the process.

Note: RentCast's value comparables are recent *listings* (active and
inactive), with list prices rather than confirmed closed-sale prices. When an
MLS/RESO connector is configured, the registry prefers its closed sales.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import httpx

from ..config import Settings
from ..models import Comp, PropertyProfile, RentEstimate, SourceNote
from .base import ConnectorError

log = logging.getLogger(__name__)
BASE = "https://api.rentcast.io/v1"

_TYPE_MAP = {
    "Single Family": ("Single-family", 1), "Townhouse": ("Townhouse", 1), "Condo": ("Condo", 1),
    "Multi-Family": ("Multi-family", 2), "Duplex": ("Two-family", 2), "Triplex": ("Three-family", 3),
    "Quadruplex": ("Four-family", 4), "Manufactured": ("Manufactured", 1),
}


def _date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


class RentCastConnector:
    name = "rentcast"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.s = settings
        self.http = client or httpx.Client(timeout=20)

    def available(self) -> bool:
        return bool(self.s.rentcast_api_key)

    def _get(self, path: str, **params):
        params = {k: v for k, v in params.items() if v is not None}
        r = self.http.get(f"{BASE}{path}", params=params, headers={"X-Api-Key": self.s.rentcast_api_key or "",
                                                                     "Accept": "application/json"})
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise ConnectorError(f"RentCast {path} returned {r.status_code}: {r.text[:200]}")
        return r.json()

    # ---- property -------------------------------------------------------
    def property_profile(self, address: str) -> PropertyProfile | None:
        data = self._get("/properties", address=address)
        rec = (data or [None])[0] if isinstance(data, list) else data
        if not rec:
            return None
        ptype, units = _TYPE_MAP.get(rec.get("propertyType", ""), (rec.get("propertyType") or "Single-family", 1))
        taxes = rec.get("propertyTaxes") or {}
        latest_tax = taxes[max(taxes, key=lambda y: int(y))]["total"] if taxes else None
        lot = rec.get("lotSize")
        year = rec.get("yearBuilt") or 1970

        listing = None
        try:
            ls = self._get("/listings/sale", address=address)
            listing = (ls or [None])[0] if isinstance(ls, list) else ls
        except ConnectorError as e:
            log.info("RentCast listing lookup failed: %s", e)

        flags = []
        if year < 1978:
            flags.append("Pre-1978: NJ lead-safe inspection at tenant turnover")
        feats = rec.get("features") or {}
        if feats.get("pool"):
            flags.append("Pool on record: confirm permit status")

        return PropertyProfile(
            address=address,
            street=rec.get("addressLine1") or address.split(",")[0],
            city=rec.get("city", ""), state=rec.get("state", "NJ"), zip=rec.get("zipCode", ""),
            county=rec.get("county", "") and f"{rec['county']} County",
            property_type=ptype, units=units,
            beds=rec.get("bedrooms") or 0, baths=rec.get("bathrooms") or 0,
            sqft=int(rec.get("squareFootage") or 0), lot=f"{lot / 43560:.2f} ac" if lot else "",
            year_built=year, condition="Good",  # no provider knows condition; set it after a walkthrough
            utilities="Unknown: confirm sewer vs septic",
            list_price=(listing or {}).get("price"),
            status=(listing or {}).get("status", "Off market"),
            days_on_market=(listing or {}).get("daysOnMarket"),
            annual_tax=latest_tax or 0, annual_insurance=0,  # insurance filled by the pipeline's estimator
            flags=flags, lat=rec.get("latitude"), lon=rec.get("longitude"),
            listing_agent_name=((listing or {}).get("listingAgent") or {}).get("name"),
            listing_agent_email=((listing or {}).get("listingAgent") or {}).get("email"),
            listing_agent_phone=((listing or {}).get("listingAgent") or {}).get("phone"),
            listing_office=((listing or {}).get("listingOffice") or {}).get("name"),
            source=SourceNote(provider="rentcast", detail="Public record + listing.", as_of=date.today()),
        )

    # ---- rent -----------------------------------------------------------
    def rent_estimate(self, prop: PropertyProfile) -> RentEstimate | None:
        d = self._get("/avm/rent/long-term", address=prop.address,
                      bedrooms=prop.beds or None, bathrooms=prop.baths or None, squareFootage=prop.sqft or None)
        if not d or not d.get("rent"):
            return None
        mult = max(prop.units, 1) if prop.units > 1 else 1
        note = "RentCast long-term rent AVM" + (f" × {prop.units} units (verify unit mix)" if mult > 1 else "")
        return RentEstimate(monthly=d["rent"] * mult, low=d.get("rentRangeLow", d["rent"]) * mult,
                            high=d.get("rentRangeHigh", d["rent"]) * mult, note=note,
                            source=SourceNote(provider="rentcast", detail="Rent AVM.", as_of=date.today()))

    # ---- comps ----------------------------------------------------------
    def comps(self, prop: PropertyProfile) -> list[Comp] | None:
        d = self._get("/avm/value", address=prop.address, compCount=15)
        if not d:
            return None
        out: list[Comp] = []
        for c in d.get("comparables", []):
            price = c.get("price")
            when = _date(c.get("removedDate")) or _date(c.get("listedDate"))
            if not price or not when or not c.get("squareFootage"):
                continue
            _, units = _TYPE_MAP.get(c.get("propertyType", ""), ("", 1))
            out.append(Comp(
                address=c.get("formattedAddress", "").split(",")[0], distance_mi=round(c.get("distance", 0), 2),
                beds=c.get("bedrooms") or 0, baths=c.get("bathrooms") or 0, sqft=int(c["squareFootage"]),
                year_built=c.get("yearBuilt") or prop.year_built, condition="Good",
                sold_date=when, sale_price=price, units=units,
            ))
        return out or None
