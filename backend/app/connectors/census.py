"""US Census connector: geocode the address to a tract, then pull ACS 5-year stats.

This is the same public data justicemap.org visualizes (ACS income, race,
poverty by tract), fetched directly from the source. No key is needed for
light use; set CENSUS_API_KEY for higher limits.

  Geocoder: https://geocoding.geo.census.gov/geocoder/
  ACS API:  https://api.census.gov/data/<year>/acs/acs5
"""
from __future__ import annotations

import logging
from datetime import date

import httpx

from ..config import Settings
from ..models import Neighborhood, PropertyProfile, SourceNote
from .base import ConnectorError

log = logging.getLogger(__name__)

GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"

# ACS 5-year variables
VARS = {
    "income": "B19013_001E",          # median household income
    "gross_rent": "B25064_001E",      # median gross rent
    "pop": "B01003_001E",             # total population
    "tenure_total": "B25003_001E",    # occupied housing units
    "owner": "B25003_002E",           # owner-occupied
    "renter": "B25003_003E",          # renter-occupied
    "vac_for_rent": "B25004_002E",    # vacant, for rent
    "vac_rented": "B25004_003E",      # vacant, rented not occupied
    "pov_below": "B17001_002E",       # income below poverty level
    "pov_total": "B17001_001E",       # poverty status determined
    "commute_agg": "B08013_001E",     # aggregate travel time to work (minutes)
    "commuters": "B08303_001E",       # workers who did not work from home
}


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f < 0 else f  # ACS uses large negatives for "not available"


class CensusConnector:
    name = "census_acs"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.s = settings
        self.http = client or httpx.Client(timeout=15)

    def available(self) -> bool:
        return True  # keyless access works; the key only raises rate limits

    def _geocode(self, address: str) -> dict:
        r = self.http.get(GEOCODER, params={
            "address": address, "benchmark": "Public_AR_Current", "vintage": "Current_Current", "format": "json",
        })
        r.raise_for_status()
        matches = r.json().get("result", {}).get("addressMatches", [])
        if not matches:
            raise ConnectorError(f"Census geocoder found no match for '{address}'")
        m = matches[0]
        geos = m.get("geographies", {})
        tract = (geos.get("Census Tracts") or [{}])[0]
        county = (geos.get("Counties") or [{}])[0]
        return {
            "state": tract.get("STATE"), "county": tract.get("COUNTY"), "tract": tract.get("TRACT"),
            "tract_name": tract.get("NAME", "Census tract"), "county_name": county.get("NAME", ""),
            "lat": m.get("coordinates", {}).get("y"), "lon": m.get("coordinates", {}).get("x"),
        }

    def _acs(self, year: int, g: dict) -> dict[str, float | None]:
        params = {
            "get": ",".join(VARS.values()),
            "for": f"tract:{g['tract']}",
            "in": f"state:{g['state']} county:{g['county']}",
        }
        if self.s.census_api_key:
            params["key"] = self.s.census_api_key
        r = self.http.get(f"https://api.census.gov/data/{year}/acs/acs5", params=params)
        r.raise_for_status()
        header, row = r.json()[:2]
        by_code = dict(zip(header, row))
        return {k: _num(by_code.get(code)) for k, code in VARS.items()}

    def locate(self, prop: PropertyProfile) -> dict:
        return self._geocode(f"{prop.street}, {prop.city}, {prop.state} {prop.zip}".strip())

    def neighborhood(self, prop: PropertyProfile) -> Neighborhood | None:
        g = self.locate(prop)
        if not g.get("tract"):
            return None
        year = self.s.census_acs_year
        now = self._acs(year, g)
        try:
            then = self._acs(year - 5, g)
        except httpx.HTTPError:
            then = {}

        def ratio(a, b):
            return a / b if a is not None and b else None

        def growth(k):
            a, b = now.get(k), then.get(k)
            return (a - b) / b if a is not None and b else None

        rental_stock = sum(v or 0 for v in (now["renter"], now["vac_for_rent"], now["vac_rented"]))
        return Neighborhood(
            tract_name=f"{g['tract_name']}, {g['county_name']}".strip(", "),
            median_household_income=now["income"],
            income_growth_5y=growth("income"),
            median_gross_rent=now["gross_rent"],
            rental_vacancy=ratio(now["vac_for_rent"], rental_stock),
            owner_occupied=ratio(now["owner"], now["tenure_total"]),
            population_change_5y=growth("pop"),
            poverty_rate=ratio(now["pov_below"], now["pov_total"]),
            mean_commute_min=ratio(now["commute_agg"], now["commuters"]),
            source=SourceNote(provider="census_acs", detail=f"ACS 5-year {year - 4}–{year}, tract level; growth vs {year - 5}.",
                              as_of=date(year, 12, 31)),
        )
