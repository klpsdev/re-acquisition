"""Address in → Analysis out. The one place the steps are wired together."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..config import Settings
from ..connectors import DataBundle
from ..models import Analysis, Comp, Criteria, Neighborhood, PropertyProfile, RentEstimate
from . import narrative
from .offers import build_offers, demand_score, risks
from .rehab import estimate_rehab
from .underwriting import underwrite
from .valuation import value_property


def bundle_to_json(b: DataBundle) -> dict:
    return {"property": b.property.model_dump(mode="json"), "rent": b.rent.model_dump(mode="json"),
            "neighborhood": b.neighborhood.model_dump(mode="json"),
            "comps": [c.model_dump(mode="json") for c in b.comps], "trail": b.trail}


def bundle_from_json(d: dict) -> DataBundle:
    return DataBundle(PropertyProfile(**d["property"]), RentEstimate(**d["rent"]), Neighborhood(**d["neighborhood"]),
                      [Comp(**c) for c in d["comps"]], d.get("trail", []))


def analyze(settings: Settings, b: DataBundle, criteria: Criteria | None = None,
            rehab_override: float | None = None, analysis_id: str | None = None,
            created_at: str | None = None, explain_with_ai: bool = True) -> Analysis:
    criteria = criteria or Criteria()
    prop, rent = b.property, b.rent
    nb = b.neighborhood.model_copy()
    nb.demand_score = demand_score(nb)
    rehab = rehab_override if rehab_override is not None else estimate_rehab(prop)
    val = value_property(prop, b.comps, rent)
    uw = underwrite(prop, rent, rehab, val.arv, criteria)
    offers = build_offers(prop, rent, val, uw)
    a = Analysis(
        id=analysis_id or uuid.uuid4().hex[:12],
        created_at=created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        property=prop, rent=rent, neighborhood=nb, valuation=val, rehab_estimate=rehab, underwriting=uw,
        offers=offers, risks=risks(prop, rent, val, uw, rehab), explanation="", explanation_source="template",
        data_trail=list(b.trail),
    )
    if explain_with_ai:
        a.explanation, a.explanation_source = narrative.explain(settings, a)
    else:
        a.explanation = narrative.template_explanation(a)
    return a
