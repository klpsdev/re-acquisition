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


def test_failed_provider_is_reported_with_reason_and_synthetic_uses_typed_zip():
    from app.connectors.registry import ConnectorRegistry as Reg

    def handler(req: httpx.Request):
        return httpx.Response(401, json={"message": "Your subscription is inactive"})

    s = Settings(data_mode="live", rentcast_api_key=" k \n")
    assert s.rentcast_api_key == "k"
    reg = Reg(s)
    reg.rentcast.http = _client(handler)
    b = reg.gather("214 Harvard Ave, Stratford, NJ 08084")
    fails = [t for t in b.trail if "rentcast failed" in t]
    assert fails and "subscription is inactive" in fails[0]
    assert b.property.zip == "08084" and b.property.source.synthetic
    assert "214 harvard ave, stratford, nj 08084" not in reg._cache   # retried next time
    a = analyze(s, b, explain_with_ai=False)
    assert a.data_trail == b.trail


# ---- email --------------------------------------------------------------------

def _gmail_settings(**kw):
    return Settings(gmail_client_id="cid", gmail_client_secret="sec", gmail_refresh_token="rt",
                    gmail_sender="me@gmail.com", **kw)


def test_gmail_mailer_refreshes_token_and_sends_raw_mime():
    import base64
    from email import message_from_bytes

    from app.services.email import GmailApiMailer, build_message

    seen = {}

    def handler(req: httpx.Request):
        if req.url.host == "oauth2.googleapis.com":
            assert b"grant_type=refresh_token" in req.content and b"refresh_token=rt" in req.content
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3599})
        assert req.headers["Authorization"] == "Bearer at"
        seen["raw"] = json.loads(req.content)["raw"]
        return httpx.Response(200, json={"id": "18f0abc", "threadId": "18f0abc"})

    m = GmailApiMailer(_gmail_settings(), client=_client(handler))
    msg = build_message("me@gmail.com", "Lalith", "agent@brokerage.com", "Offer: 1 Main St ($200,000)",
                        "Dear Agent,\n\nOffer attached.", cc=["partner@example.com"])
    sent = m.send(msg)
    assert sent.message_id == "18f0abc"
    parsed = message_from_bytes(base64.urlsafe_b64decode(seen["raw"]))
    assert parsed["To"] == "agent@brokerage.com" and parsed["Cc"] == "partner@example.com"
    assert parsed["From"] == "Lalith <me@gmail.com>" and "Offer attached." in parsed.get_payload()


def test_gmail_invalid_grant_explains_the_fix():
    from app.services.email import EmailError, GmailApiMailer, build_message

    m = GmailApiMailer(_gmail_settings(), client=_client(
        lambda req: httpx.Response(400, json={"error": "invalid_grant"})))
    with pytest.raises(EmailError, match="gmail_auth.py"):
        m.send(build_message("me@gmail.com", None, "a@b.com", "s", "body text"))


def test_approve_and_send_records_message_and_never_sends_twice(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    from app.services import email as email_mod
    from app.services.email import SentMessage

    sends = []

    class FakeMailer:
        provider, sender = "gmail_api", "me@gmail.com"

        def send(self, msg):
            sends.append(msg)
            return SentMessage("gmail_api", "msg-1", "thr-1")

    monkeypatch.setattr(email_mod, "_mailer", FakeMailer())
    with TestClient(main.app) as client:
        a = client.post("/api/analyze", json={"address": WOODBURY}).json()
        letter = client.post(f"/api/analyses/{a['id']}/letter", json={"tier": "target", "terms": {"agent_name": "Dana Reyes", "signer_name": "Lalith",
                                                   "signer_phone": "856-555-0100", "signer_email": "me@gmail.com"}}).json()["text"]
        bad = client.post(f"/api/analyses/{a['id']}/approve", json={
            "tier": "target", "letter_text": letter, "approved_by": "Lalith", "agent_email": "nope", "send": True})
        assert bad.status_code == 422
        r = client.post(f"/api/analyses/{a['id']}/approve", json={
            "tier": "target", "letter_text": letter, "approved_by": "Lalith",
            "agent_email": "agent@brokerage.com", "send": True}).json()
        assert r["status"] == "sent" and r["sent_from"] == "me@gmail.com" and r["message_id"] == "msg-1"
        assert sends[0]["Subject"].startswith("Offer: 218 Carpenter St")
        again = client.post(f"/api/approvals/{r['approval_id']}/send").json()
        assert again["status"] == "sent" and len(sends) == 1
        hist = client.get(f"/api/analyses/{a['id']}/approvals").json()
        assert hist[0]["sent"] and hist[0]["agent_email"] == "agent@brokerage.com"
        assert client.get("/api/analyses").json()[0]["status"].startswith("Offer sent")


def test_migration_adds_email_columns_to_existing_approvals_table(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from app import db

    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE analyses (id VARCHAR(32) PRIMARY KEY, created_at TIMESTAMP, address VARCHAR(300), "
                       "list_price FLOAT, mao FLOAT, status VARCHAR(40), inputs JSON, result JSON, trail JSON)"))
        c.execute(text("CREATE TABLE approvals (id INTEGER PRIMARY KEY, analysis_id VARCHAR(32), created_at TIMESTAMP, "
                       "tier VARCHAR(20), price FLOAT, approved_by VARCHAR(120), agent_email VARCHAR(200), "
                       "letter_text TEXT, snapshot JSON, sent BOOLEAN)"))
    old = db.engine
    db.engine = eng
    try:
        db.init_db()
    finally:
        db.engine = old
    cols = {c["name"] for c in inspect(eng).get_columns("approvals")}
    assert {"sent_at", "message_id", "send_error", "subject"} <= cols


def test_send_is_blocked_while_letter_has_placeholders(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    from app.services import email as email_mod
    class FakeMailer:
        provider, sender = "gmail_api", "me@gmail.com"

        def send(self, msg):
            raise AssertionError("must not send")

    monkeypatch.setattr(email_mod, "_mailer", FakeMailer())
    with TestClient(main.app) as client:
        a = client.post("/api/analyze", json={"address": WOODBURY}).json()
        letter = client.post(f"/api/analyses/{a['id']}/letter", json={"tier": "target"}).json()["text"]
        assert "[Your name]" in letter
        r = client.post(f"/api/analyses/{a['id']}/approve", json={
            "tier": "target", "letter_text": letter, "approved_by": "Lalith",
            "agent_email": "agent@brokerage.com", "send": True})
        assert r.status_code == 422 and "[Your name]" in r.json()["detail"]
        filled = client.post(f"/api/analyses/{a['id']}/letter", json={"tier": "target", "terms": {"agent_name": "Dana Reyes", "signer_name": "Lalith",
                                                   "signer_phone": "856-555-0100", "signer_email": "me@gmail.com"}}).json()["text"]
        assert email_mod.placeholders(filled) == []
        assert "Dear Dana," in filled and "856-555-0100 · me@gmail.com" in filled


# ---- Proposal to Purchase PDF ---------------------------------------------------

def test_offer_pdf_contains_the_deal_values_and_no_signature():
    import io

    import pdfplumber

    from app.services import offer_pdf
    from app.services.offer_form import DEFAULT_PROFILE, balance_due

    f = DEFAULT_PROFILE.model_copy(update=dict(property_address="218 Carpenter St, Woodbury, NJ 08096", price=233000,
                                               settlement_date="Nov 11, 2026", buyer_date="09/27/2026"))
    f.balance_due = balance_due(f)
    assert f.balance_due == 223000
    text = pdfplumber.open(io.BytesIO(offer_pdf.render(f))).pages[0].extract_text()
    for s in ("218 Carpenter St, Woodbury, NJ 08096", "233,000", "10,000", "223,000", "Nov 11, 2026",
              "SRV Realty", "PROPOSAL TO PURCHASE"):
        assert s in text, s
    assert "Docusign" not in text and "Lalith Phani" not in text
    assert offer_pdf.filename(f) == "218_Carpenter_St_Offer-unsigned.pdf"


def test_offer_form_prefill_profile_and_pdf_attached_on_send(monkeypatch):
    from email import message_from_bytes

    from fastapi.testclient import TestClient

    from app import main
    from app.services import email as email_mod
    from app.services.email import SentMessage

    sent = []

    class FakeMailer:
        provider, sender = "gmail_api", "me@gmail.com"

        def send(self, msg):
            sent.append(message_from_bytes(msg.as_bytes()))
            return SentMessage("gmail_api", "m", "t")

    monkeypatch.setattr(email_mod, "_mailer", FakeMailer())
    with TestClient(main.app) as client:
        a = client.post("/api/analyze", json={"address": WOODBURY}).json()
        target = next(o for o in a["offers"] if o["tier"] == "target")
        form = client.get(f"/api/analyses/{a['id']}/offer-form?tier=target").json()
        assert form["price"] == target["price"] and form["property_address"].startswith("218 Carpenter St")
        assert form["balance_due"] == target["price"] - 10000 and form["firm_name"] == "SRV Realty"

        prof = client.put("/api/offer-profile", json={**form, "agent_cell": "856-555-0100"}).json()
        assert prof["agent_cell"] == "856-555-0100"
        assert client.get(f"/api/analyses/{a['id']}/offer-form?tier=target").json()["agent_cell"] == "856-555-0100"

        pdf = client.post("/api/offer-pdf", json=form)
        assert pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"

        letter = client.post(f"/api/analyses/{a['id']}/letter", json={"tier": "target", "terms": {
            "agent_name": "Dana Reyes", "signer_name": "Lalith", "signer_phone": "856-555-0100",
            "signer_email": "me@gmail.com"}}).json()["text"]
        wrong = client.post(f"/api/analyses/{a['id']}/approve", json={
            "tier": "target", "letter_text": letter, "approved_by": "Lalith", "agent_email": "agent@brokerage.com",
            "send": True, "offer_form": {**form, "price": 1}})
        assert wrong.status_code == 422 and "doesn't match" in wrong.json()["detail"]
        r = client.post(f"/api/analyses/{a['id']}/approve", json={
            "tier": "target", "letter_text": letter, "approved_by": "Lalith", "agent_email": "agent@brokerage.com",
            "send": True, "offer_form": form}).json()
        assert r["status"] == "sent"
        parts = [p for p in sent[0].walk() if p.get_filename()]
        assert parts[0].get_filename() == "218_Carpenter_St_Offer-unsigned.pdf"
        assert parts[0].get_payload(decode=True)[:4] == b"%PDF"
        assert client.get(f"/api/approvals/{r['approval_id']}/pdf").content[:4] == b"%PDF"
