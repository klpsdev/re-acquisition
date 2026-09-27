"""RESO Web API connector: closed sales and active listings from an MLS feed.

Works with any RESO Web API (OData) endpoint: Bright MLS (South Jersey),
Bridge Interactive (Zillow Group), and most MLS vendor feeds. You need a data
license from the MLS; an agent login is not the same as API/redistribution rights.

Two ways to authenticate:

  A. OAuth 2 client credentials (Bright MLS):
       RESO_BASE_URL       https://bright-reso.tst.brightmls.com/RESO/OData/bright   (test)
                           https://bright-reso.brightmls.com/RESO/OData/bright       (production)
       RESO_TOKEN_URL      token endpoint from Bright's onboarding / Authentication page
       RESO_CLIENT_ID      client id issued by Bright
       RESO_CLIENT_SECRET  client secret issued by Bright
       RESO_SCOPE          optional, only if Bright specifies one
       RESO_TOKEN_AUTH     "body" (default) sends id/secret as form fields; "basic" sends HTTP Basic
     Tokens are fetched on demand and reused until shortly before they expire.

  B. Static bearer token (Bridge and some vendors):
       RESO_BASE_URL, RESO_ACCESS_TOKEN

Field names follow the RESO Data Dictionary (ClosePrice, LivingArea, ...).
"""
from __future__ import annotations

import logging
import threading
import time
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

        self._token: str | None = None
        self._token_expires = 0.0
        self._lock = threading.Lock()

    @property
    def uses_oauth(self) -> bool:
        return bool(self.s.reso_token_url and self.s.reso_client_id and self.s.reso_client_secret)

    def available(self) -> bool:
        return bool(self.s.reso_base_url and (self.uses_oauth or self.s.reso_access_token))

    def _bearer(self, force_refresh: bool = False) -> str:
        if not self.uses_oauth:
            return self.s.reso_access_token or ""
        with self._lock:
            if self._token and not force_refresh and time.time() < self._token_expires:
                return self._token
            data = {"grant_type": "client_credentials"}
            if self.s.reso_scope:
                data["scope"] = self.s.reso_scope
            auth = None
            if self.s.reso_token_auth.lower() == "basic":
                auth = (self.s.reso_client_id, self.s.reso_client_secret)
            else:
                data |= {"client_id": self.s.reso_client_id, "client_secret": self.s.reso_client_secret}
            r = self.http.post(self.s.reso_token_url, data=data, auth=auth, headers={"Accept": "application/json"})
            if r.status_code >= 400:
                raise ConnectorError(f"RESO token request failed {r.status_code}: {r.text[:200]}")
            body = r.json()
            self._token = body["access_token"]
            self._token_expires = time.time() + max(60, int(body.get("expires_in", 3600)) - 60)
            return self._token

    def _query(self, flt: str, top: int = 100, select: str = SELECT) -> list[dict]:
        url = f"{self.s.reso_base_url.rstrip('/')}/Property"
        params = {"$filter": flt, "$top": top, "$select": select + ",PublicRemarks"}
        r = self.http.get(url, params=params, headers={"Authorization": f"Bearer {self._bearer()}",
                                                       "Accept": "application/json"})
        if r.status_code == 401 and self.uses_oauth:  # token revoked or expired early: refresh once
            r = self.http.get(url, params=params, headers={"Authorization": f"Bearer {self._bearer(True)}",
                                                           "Accept": "application/json"})
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
