"""RESO Web API connector: closed sales and active listings from an MLS feed.

Works with any RESO Web API (OData) endpoint, including Bridge Interactive
(Zillow Group's MLS data platform) and most MLS vendor feeds, e.g. Bright MLS
for South Jersey. You need a data license from the MLS or vendor; having an
agent login is not the same as having API/redistribution rights.

  RESO_BASE_URL      e.g. https://api.bridgedataoutput.com/api/v2/OData/<dataset>
  RESO_ACCESS_TOKEN  bearer token issued by the vendor

Field names follow the RESO Data Dictionary (ClosePrice, LivingArea, ...).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from ..config import Settings
from ..models import Comp, PropertyProfile
from ..util import haversine_mi
from .base import ConnectorError

log = logging.getLogger(__name__)

SELECT = ",".join([
    "ListingKey", "UnparsedAddress", "StandardStatus", "PropertySubType", "BedroomsTotal",
    "BathroomsTotalDecimal", "BathroomsTotalInteger", "LivingArea", "YearBuilt", "ClosePrice", "CloseDate",
    "ListPrice", "DaysOnMarket", "Latitude", "Longitude", "NumberOfUnitsTotal", "PostalCode",
])


def _condition_from(remarks: str | None) -> str:
    r = (remarks or "").lower()
    if any(w in r for w in ("fully renovated", "completely renovated", "gut reno", "brand new kitchen")):
        return "Renovated"
    if any(w in r for w in ("updated", "remodeled", "new roof", "new hvac")):
        return "Updated"
    if any(w in r for w in ("tlc", "as-is", "as is", "needs work", "investor special", "handyman")):
        return "Dated"
    return "Good"


class ResoConnector:
    name = "reso_mls"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.s = settings
        self.http = client or httpx.Client(timeout=25)

    def available(self) -> bool:
        return bool(self.s.reso_base_url and self.s.reso_access_token)

    def _query(self, flt: str, top: int = 100, select: str = SELECT) -> list[dict]:
        r = self.http.get(
            f"{self.s.reso_base_url.rstrip('/')}/Property",
            params={"$filter": flt, "$top": top, "$select": select + ",PublicRemarks"},
            headers={"Authorization": f"Bearer {self.s.reso_access_token}", "Accept": "application/json"},
        )
        if r.status_code >= 400:
            raise ConnectorError(f"RESO query failed {r.status_code}: {r.text[:200]}")
        return r.json().get("value", [])

    def active_listing(self, prop: PropertyProfile) -> dict | None:
        street = prop.street.replace("'", "''")
        rows = self._query(f"contains(UnparsedAddress,'{street}') and PostalCode eq '{prop.zip}'", top=5)
        return rows[0] if rows else None

    def comps(self, prop: PropertyProfile) -> list[Comp] | None:
        since = (date.today() - timedelta(days=365)).isoformat()
        flt = (f"StandardStatus eq 'Closed' and CloseDate ge {since} and PostalCode eq '{prop.zip}'"
               f" and LivingArea ge {int(prop.sqft * 0.6)} and LivingArea le {int(prop.sqft * 1.5)}")
        rows = self._query(flt, top=100)
        out: list[Comp] = []
        for x in rows:
            if not x.get("ClosePrice") or not x.get("LivingArea"):
                continue
            dist = 0.0
            if prop.lat and prop.lon and x.get("Latitude") and x.get("Longitude"):
                dist = haversine_mi(prop.lat, prop.lon, x["Latitude"], x["Longitude"])
            out.append(Comp(
                address=(x.get("UnparsedAddress") or "").split(",")[0], distance_mi=round(dist, 2),
                beds=x.get("BedroomsTotal") or 0,
                baths=x.get("BathroomsTotalDecimal") or x.get("BathroomsTotalInteger") or 0,
                sqft=int(x["LivingArea"]), year_built=x.get("YearBuilt") or prop.year_built,
                condition=_condition_from(x.get("PublicRemarks")),
                sold_date=date.fromisoformat(x["CloseDate"][:10]), sale_price=x["ClosePrice"],
                units=x.get("NumberOfUnitsTotal") or 1,
            ))
        out.sort(key=lambda c: c.distance_mi)
        return out[:15] or None
