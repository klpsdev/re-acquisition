"""Pre-fill the Proposal to Purchase from the analysis plus your saved details."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..db import SettingRow
from ..models import OFFER_PROFILE_FIELDS, Analysis, OfferForm

PROFILE_KEY = "offer_profile"

# Starting values taken from your 23 W Emlen Ave offer. Edit them in the app and
# click "Save as my defaults"; the saved copy (in the database) wins from then on.
DEFAULT_PROFILE = OfferForm(
    buyer_name="SP Real Estate Ventures LLC",
    mortgage_type="other",
    title_company="Providence Abstract 3146 State Route 27, Suites 203-204\nKendall Park, NJ 08824",
    possession="settlement", insp_home=True, assets="not_contingent",
    firm_name="SRV Realty", licensee="Kumar Sadaram NJ lic # 1433732",
    firm_role="buyer_agent", listing_role="seller_agent", valid_days=15,
    presenting_address="578 Buena parkway,\nBridgewater NJ 08807",
    agent_name="Kumar Sadaram", agent_cell="215.873.7964", agent_email="selltosadaram@gmail.com",
    buyer_signed_2="SP Real Estate Ventures LLC", footer_company="SRV Realty",
    initial_deposit=10000,
)


def get_profile(session: Session) -> OfferForm:
    row = session.get(SettingRow, PROFILE_KEY)
    if not row:
        return DEFAULT_PROFILE.model_copy()
    return DEFAULT_PROFILE.model_copy(update={k: v for k, v in row.value.items() if k in OFFER_PROFILE_FIELDS})


def save_profile(session: Session, form: OfferForm) -> OfferForm:
    data = {k: getattr(form, k) for k in OFFER_PROFILE_FIELDS}
    row = session.get(SettingRow, PROFILE_KEY)
    if row:
        row.value = data
    else:
        session.add(SettingRow(key=PROFILE_KEY, value=data))
    session.commit()
    return get_profile(session)


def balance_due(f: OfferForm) -> float | None:
    if not f.price:
        return None
    return round(f.price - (f.initial_deposit or 0) - (f.additional_deposit or 0) - (f.mortgage_amount or 0))


def prefill(a: Analysis, tier: str, profile: OfferForm, close_days: int = 45) -> OfferForm:
    p = a.property
    offer = next(o for o in a.offers if o.tier == tier)
    today = date.today()
    f = profile.model_copy()
    f.property_address = f"{p.street}, {p.city}, {p.state} {p.zip}".strip().rstrip(",")
    f.price = offer.price
    f.settlement_date = (today + timedelta(days=close_days)).strftime("%b %-d, %Y")
    f.buyer_date = today.strftime("%m/%d/%Y")
    if p.listing_office or p.listing_agent_name:
        f.listing_firm = ", ".join(x for x in (p.listing_office, p.listing_agent_name) if x)
    if "septic" in p.utilities.lower():
        f.insp_septic = True
    f.balance_due = balance_due(f)
    return f
