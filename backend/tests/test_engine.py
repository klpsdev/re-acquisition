import json
import os

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sprev.db")

from app.config import Settings  # noqa: E402
from app.connectors import ConnectorRegistry  # noqa: E402
from app.connectors.census import CensusConnector  # noqa: E402
from app.connectors.rentcast import RentCastConnector  # noqa: E402
from app.models import Criteria  # noqa: E402
from app.services.pipeline import analyze  # noqa: E402
from app.services.underwriting import annual_debt_service  # noqa: E402

S = Settings(data_mode="sample")
WOODBURY = "218 Carpenter St, Woodbury, NJ 08096"


def test_debt_service_matches_amortization_table():
    # $200,000 at 6.75% over 30 years = $1,297.20/mo
    assert annual_debt_service(200_000, 6.75, 30) / 12 == pytest.approx(1297.20, abs=0.01)


def test_mao_satisfies_every_rule_and_one_binds():
    a = analyze(S, ConnectorRegistry(S).gather(WOODBURY), explain_with_ai=False)
    u, c = a.underwriting, a.underwriting.criteria
    e = u.at_mao
    assert e.coc >= c.target_coc / 100 - 1e-6
    assert e.dscr >= c.min_dscr - 1e-6
    assert (u.mao + u.rehab) / a.valuation.arv <= c.max_all_in_pct_arv / 100 + 1e-6
    assert sum(x.binding for x in u.constraints) == 1


def test_stricter_criteria_lower_the_mao():
    reg = ConnectorRegistry(S)
    base = analyze(S, reg.gather(WOODBURY), explain_with_ai=False).underwriting.mao
    strict = analyze(S, reg.gather(WOODBURY), Criteria(target_coc=10, interest_rate=7.5),
                     explain_with_ai=False).underwriting.mao
    assert strict < base


def test_offer_tiers_are_ordered_and_stretch_fails_criteria():
    a = analyze(S, ConnectorRegistry(S).gather(WOODBURY), explain_with_ai=False)
    prices = [o.price for o in a.offers]
    assert prices == sorted(prices)
    assert all(o.meets_criteria for o in a.offers[:3])
    assert not a.offers[3].meets_criteria


def test_unknown_address_is_flagged_synthetic():
    a = analyze(S, ConnectorRegistry(S).gather("123 Main Street, Camden, NJ"), explain_with_ai=False)
    assert a.property.source.synthetic
    assert a.risks[0].text.startswith("Synthetic")


# ---- connector parsing, with provider responses mocked --------------------

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_census_connector_parses_geocoder_and_acs():
    from app.connectors.census import VARS
    from app.models import PropertyProfile, SourceNote

    def handler(req: httpx.Request):
        if "geocoding" in req.url.host:
            return httpx.Response(200, json={"result": {"addressMatches": [{
                "coordinates": {"x": -75.15, "y": 39.84},
                "geographies": {"Census Tracts": [{"STATE": "34", "COUNTY": "015", "TRACT": "501200",
                                                   "NAME": "Census Tract 5012"}],
                                "Counties": [{"NAME": "Gloucester County"}]}}]}})
        year = int(req.url.path.split("/")[2])
        vals = {"income": 71400 if year == 2023 else 63860, "gross_rent": 1480, "pop": 4100 if year == 2023 else 4050,
                "tenure_total": 1700, "owner": 884, "renter": 816, "vac_for_rent": 35, "vac_rented": 5,
                "pov_below": 430, "pov_total": 3980, "commute_agg": 38400, "commuters": 1600}
        header = list(VARS.values()) + ["state", "county", "tract"]
        row = [str(vals[k]) for k in VARS] + ["34", "015", "501200"]
        return httpx.Response(200, json=[header, row])

    c = CensusConnector(Settings(), client=_client(handler))
    prop = PropertyProfile(address=WOODBURY, street="218 Carpenter St", city="Woodbury", zip="08096", beds=4,
                           baths=2, sqft=1980, year_built=1925, annual_tax=6900, annual_insurance=2400,
                           source=SourceNote(provider="test"))
    nb = c.neighborhood(prop)
    assert nb.median_household_income == 71400
    assert nb.income_growth_5y == pytest.approx(71400 / 63860 - 1)
    assert nb.owner_occupied == pytest.approx(884 / 1700)
    assert nb.rental_vacancy == pytest.approx(35 / (816 + 35 + 5))
    assert nb.mean_commute_min == pytest.approx(24)


def test_rentcast_connector_maps_property_and_comps():
    def handler(req: httpx.Request):
        assert req.headers["X-Api-Key"] == "k"
        p = req.url.path
        if p.endswith("/properties"):
            return httpx.Response(200, json=[{"addressLine1": "218 Carpenter St", "city": "Woodbury", "state": "NJ",
                "zipCode": "08096", "county": "Gloucester", "propertyType": "Duplex", "bedrooms": 4, "bathrooms": 2,
                "squareFootage": 1980, "lotSize": 4800, "yearBuilt": 1925, "latitude": 39.84, "longitude": -75.15,
                "propertyTaxes": {"2024": {"total": 6700}, "2025": {"total": 6900}}}])
        if p.endswith("/listings/sale"):
            return httpx.Response(200, json=[{"price": 285000, "status": "Active", "daysOnMarket": 23}])
        if p.endswith("/avm/value"):
            return httpx.Response(200, json={"price": 280000, "comparables": [
                {"formattedAddress": "104 Hopkins St, Woodbury, NJ", "propertyType": "Duplex", "bedrooms": 4,
                 "bathrooms": 2, "squareFootage": 1860, "yearBuilt": 1920, "price": 292000,
                 "removedDate": "2026-06-20T00:00:00.000Z", "distance": 0.31}]})
        return httpx.Response(404)

    rc = RentCastConnector(Settings(rentcast_api_key="k"), client=_client(handler))
    prop = rc.property_profile(WOODBURY)
    assert (prop.units, prop.annual_tax, prop.list_price, prop.days_on_market) == (2, 6900, 285000, 23)
    assert any("lead-safe" in f for f in prop.flags)
    comps = rc.comps(prop)
    assert comps[0].sale_price == 292000 and comps[0].units == 2


# ---- API round trip ----------------------------------------------------------

def test_api_analyze_recompute_letter_approve():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"address": WOODBURY})
        assert r.status_code == 200, r.text
        a = r.json()
        r2 = client.post(f"/api/analyses/{a['id']}/recompute", json={"criteria": {**Criteria().model_dump(), "target_coc": 9}})
        assert r2.json()["underwriting"]["mao"] <= a["underwriting"]["mao"]
        letter = client.post(f"/api/analyses/{a['id']}/letter", json={"tier": "target"}).json()
        assert "attorney review" in letter["text"].lower() and "lead-based paint" in letter["text"]
        ap = client.post(f"/api/analyses/{a['id']}/approve",
                         json={"tier": "target", "letter_text": letter["text"], "approved_by": "Lalith"}).json()
        assert ap["status"] == "approved_not_sent"
        assert client.get("/api/analyses").json()[0]["status"].startswith("Approved")


def test_api_token_is_enforced_when_set():
    from fastapi.testclient import TestClient

    from app import main

    main.settings.api_token = "secret"
    try:
        with TestClient(main.app) as client:
            assert client.get("/api/health").status_code == 200
            assert client.get("/api/providers").status_code == 401
            assert client.get("/api/providers", headers={"x-api-token": "wrong"}).status_code == 401
            assert client.get("/api/providers", headers={"x-api-token": "secret"}).status_code == 200
    finally:
        main.settings.api_token = None


def test_reso_oauth_client_credentials_fetches_caches_and_refreshes_token():
    from app.connectors.reso import ResoConnector
    from app.models import PropertyProfile, SourceNote

    calls = {"token": 0, "query": 0}

    def handler(req: httpx.Request):
        if req.url.path.endswith("/token"):
            calls["token"] += 1
            body = dict(x.split("=") for x in req.content.decode().split("&"))
            assert body["grant_type"] == "client_credentials" and body["client_id"] == "cid"
            return httpx.Response(200, json={"access_token": f"t{calls['token']}", "expires_in": 3600})
        calls["query"] += 1
        if calls["query"] == 2:  # simulate the token being revoked mid-session
            return httpx.Response(401)
        assert req.headers["Authorization"].startswith("Bearer t")
        return httpx.Response(200, json={"value": [{
            "UnparsedAddress": "104 Hopkins St, Woodbury, NJ 08096", "BedroomsTotal": 4, "BathroomsTotalInteger": 2,
            "LivingArea": 1860, "YearBuilt": 1920, "ClosePrice": 292000, "CloseDate": "2026-06-20",
            "Latitude": 39.84, "Longitude": -75.15, "NumberOfUnitsTotal": 2, "PublicRemarks": "Updated kitchen"}]})

    s = Settings(reso_base_url="https://bright-reso.tst.brightmls.com/RESO/OData/bright",
                 reso_token_url="https://auth.example.com/token", reso_client_id="cid", reso_client_secret="sec")
    conn = ResoConnector(s, client=_client(handler))
    assert conn.available()
    prop = PropertyProfile(address=WOODBURY, street="218 Carpenter St", city="Woodbury", zip="08096", beds=4,
                           baths=2, sqft=1980, year_built=1925, annual_tax=6900, annual_insurance=2400, units=2,
                           lat=39.84, lon=-75.15, source=SourceNote(provider="test"))
    first = conn.comps(prop)
    assert first[0].sale_price == 292000 and first[0].condition == "Updated"
    conn.comps(prop)            # 401 → refresh → retry
    conn.comps(prop)            # reuses refreshed token
    assert calls["token"] == 2
