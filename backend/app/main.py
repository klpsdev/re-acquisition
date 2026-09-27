"""SPREV Acquisition Engine API.

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import hmac
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .connectors import ConnectorRegistry
from .db import AnalysisRow, ApprovalRow, get_session, init_db
from .models import (Analysis, AnalysisSummary, AnalyzeRequest, ApprovalRequest, ApprovalResponse, LetterRequest,
                     LetterResponse, RecomputeRequest)
from .services import email, narrative
from .services.pipeline import analyze, bundle_from_json, bundle_to_json

logging.basicConfig(level=logging.INFO)
settings = get_settings()
registry = ConnectorRegistry(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="SPREV Acquisition Engine", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """When API_TOKEN is set, only callers presenting it (the Next.js app) get answers."""
    if settings.api_token and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        sent = request.headers.get("x-api-token", "")
        if not hmac.compare_digest(sent, settings.api_token):
            return JSONResponse({"detail": "Missing or invalid API token"}, status_code=401)
    return await call_next(request)


def _load(session: Session, analysis_id: str) -> AnalysisRow:
    row = session.get(AnalysisRow, analysis_id)
    if not row:
        raise HTTPException(404, f"No analysis with id {analysis_id}")
    return row


@app.get("/api/health")
def health():
    e = email.status(settings)  # names of missing settings only, never values
    return {"ok": True, "data_mode": settings.data_mode, "ai": bool(settings.anthropic_api_key),
            "email": {"configured": e["configured"], "missing": e["missing"]}}


@app.get("/api/providers")
def providers():
    return {"data_mode": settings.data_mode, "providers": registry.status(),
            "ai_explanations": bool(settings.anthropic_api_key), "email": email.status(settings)}


@app.post("/api/analyze", response_model=Analysis)
def run_analysis(req: AnalyzeRequest, session: Session = Depends(get_session)):
    try:
        bundle = registry.gather(req.address)
    except RuntimeError as e:
        raise HTTPException(422, str(e)) from e
    a = analyze(settings, bundle, req.criteria, req.rehab_override)
    session.add(AnalysisRow(id=a.id, address=req.address, list_price=a.property.list_price, mao=a.underwriting.mao,
                            inputs=bundle_to_json(bundle), result=a.model_dump(mode="json"), trail=bundle.trail))
    session.commit()
    return a


@app.get("/api/analyses", response_model=list[AnalysisSummary])
def recent(limit: int = 20, session: Session = Depends(get_session)):
    rows = session.scalars(select(AnalysisRow).order_by(AnalysisRow.created_at.desc()).limit(limit)).all()
    return [AnalysisSummary(id=r.id, created_at=r.created_at.isoformat(timespec="seconds"), address=r.address,
                            list_price=r.list_price, mao=r.mao, status=r.status) for r in rows]


@app.get("/api/analyses/{analysis_id}", response_model=Analysis)
def get_analysis(analysis_id: str, session: Session = Depends(get_session)):
    return Analysis(**_load(session, analysis_id).result)


@app.get("/api/analyses/{analysis_id}/trail")
def get_trail(analysis_id: str, session: Session = Depends(get_session)):
    """Which provider supplied each piece of data (and which ones failed)."""
    return {"trail": _load(session, analysis_id).trail}


@app.post("/api/analyses/{analysis_id}/recompute", response_model=Analysis)
def recompute(analysis_id: str, req: RecomputeRequest, session: Session = Depends(get_session)):
    """Re-run underwriting with new criteria against the stored data (no provider calls)."""
    row = _load(session, analysis_id)
    a = analyze(settings, bundle_from_json(row.inputs), req.criteria, req.rehab_override,
                analysis_id=row.id, created_at=row.result["created_at"], explain_with_ai=False)
    row.result, row.mao = a.model_dump(mode="json"), a.underwriting.mao
    session.commit()
    return a


@app.post("/api/analyses/{analysis_id}/letter", response_model=LetterResponse)
def make_letter(analysis_id: str, req: LetterRequest, session: Session = Depends(get_session)):
    a = Analysis(**_load(session, analysis_id).result)
    offer = next(o for o in a.offers if o.tier == req.tier)
    text, source = narrative.letter(settings, a, offer, req.terms, req.polish_with_ai)
    return LetterResponse(tier=offer.tier, price=offer.price, text=text, source=source)


def _default_subject(a: Analysis, price: float) -> str:
    p = a.property
    return f"Offer: {p.street}, {p.city}, {p.state} {p.zip} (${price:,.0f})"


def _send(session: Session, ap: ApprovalRow, a: Analysis) -> ApprovalResponse:
    """Email an approved letter. Never sends twice; records success or the reason it failed."""
    mailer = email.get_mailer(settings)
    to = (ap.agent_email or "").strip()
    base = dict(approval_id=ap.id, sent_to=to or None)
    if ap.sent:
        return ApprovalResponse(**base, status="sent", sent_from=ap.sent_from, message_id=ap.message_id,
                                sent_at=ap.sent_at.isoformat() if ap.sent_at else None,
                                message=f"Already sent to {to}; not sending again.")
    if not mailer:
        return ApprovalResponse(**base, status="approved_not_sent",
                                message=f"Approval #{ap.id} logged. Email isn't set up on the server, so nothing was sent.")
    if not email.valid_email(to):
        return ApprovalResponse(**base, status="approved_not_sent",
                                message=f"Approval #{ap.id} logged. Add a valid agent email to send it.")
    if left := email.placeholders(ap.letter_text):
        return ApprovalResponse(**base, status="approved_not_sent",
                                message=f"Approval #{ap.id} logged but not sent: the letter still has {', '.join(left)}.")
    cc = [c.strip() for c in (settings.email_cc or "").split(",") if email.valid_email(c)]
    msg = email.build_message(mailer.sender, settings.email_sender_name, to, ap.subject or _default_subject(a, ap.price),
                              ap.letter_text, cc)
    try:
        sent = mailer.send(msg)
    except email.EmailError as e:
        ap.send_error = str(e)
        session.commit()
        return ApprovalResponse(**base, status="send_failed", message=f"Approval #{ap.id} logged, but the email failed: {e}")
    ap.sent, ap.sent_at, ap.sent_from = True, datetime.now(timezone.utc), mailer.sender
    ap.provider, ap.message_id, ap.thread_id, ap.send_error = sent.provider, sent.message_id, sent.thread_id, None
    row = session.get(AnalysisRow, ap.analysis_id)
    if row:
        row.status = f"Offer sent ({ap.tier.title()})"
    session.commit()
    return ApprovalResponse(**base, status="sent", sent_from=mailer.sender, sent_at=ap.sent_at.isoformat(),
                            message_id=sent.message_id,
                            message=f"Sent the ${ap.price:,.0f} offer from {mailer.sender} to {to}"
                                    f"{' (cc ' + ', '.join(cc) + ')' if cc else ''}. It's in your Gmail Sent folder.")


@app.post("/api/analyses/{analysis_id}/approve", response_model=ApprovalResponse)
def approve(analysis_id: str, req: ApprovalRequest, session: Session = Depends(get_session)):
    """Human approval gate: records who approved what, against which numbers, then emails it if asked."""
    row = _load(session, analysis_id)
    a = Analysis(**row.result)
    offer = next(o for o in a.offers if o.tier == req.tier)
    if req.send and not email.valid_email(req.agent_email):
        raise HTTPException(422, "Enter a valid agent email address to send the offer.")
    if req.send and (left := email.placeholders(req.letter_text)):
        raise HTTPException(422, f"Fill in these placeholders before sending: {', '.join(left)}")
    snapshot = {"criteria": a.underwriting.criteria.model_dump(), "mao": a.underwriting.mao,
                "constraints": [c.model_dump() for c in a.underwriting.constraints],
                "offer": offer.model_dump(mode="json"),
                "comps_used": [c.model_dump(mode="json") for c in a.valuation.comps if c.used],
                "rehab": a.rehab_estimate, "rent": a.rent.model_dump(mode="json"), "trail": row.trail}
    ap = ApprovalRow(analysis_id=row.id, tier=offer.tier, price=offer.price, approved_by=req.approved_by,
                     agent_email=(req.agent_email or "").strip() or None, letter_text=req.letter_text,
                     subject=(req.subject or "").strip() or _default_subject(a, offer.price), snapshot=snapshot, sent=False)
    session.add(ap)
    row.status = f"Approved {offer.label}"
    session.commit()
    if req.send:
        return _send(session, ap, a)
    return ApprovalResponse(approval_id=ap.id, status="approved_not_sent", sent_to=ap.agent_email,
                            message=f"Approval #{ap.id} logged: {offer.label} offer at ${offer.price:,.0f}, approved by "
                                    f"{req.approved_by}. Not emailed.")


@app.post("/api/approvals/{approval_id}/send", response_model=ApprovalResponse)
def send_approval(approval_id: int, session: Session = Depends(get_session)):
    """Retry sending an approved letter (e.g. after fixing the email setup)."""
    ap = session.get(ApprovalRow, approval_id)
    if not ap:
        raise HTTPException(404, f"No approval #{approval_id}")
    return _send(session, ap, Analysis(**_load(session, ap.analysis_id).result))


@app.get("/api/analyses/{analysis_id}/approvals")
def list_approvals(analysis_id: str, session: Session = Depends(get_session)):
    rows = session.scalars(select(ApprovalRow).where(ApprovalRow.analysis_id == analysis_id)
                           .order_by(ApprovalRow.created_at.desc())).all()
    return [{"id": r.id, "created_at": r.created_at.isoformat(timespec="seconds"), "tier": r.tier, "price": r.price,
             "approved_by": r.approved_by, "agent_email": r.agent_email, "subject": r.subject, "sent": r.sent,
             "sent_at": r.sent_at.isoformat(timespec="seconds") if r.sent_at else None, "sent_from": r.sent_from,
             "send_error": r.send_error} for r in rows]
