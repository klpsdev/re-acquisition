"""Fill the NJ "Proposal to Purchase" (FORM#001) with the offer's details.

The blank form (templates/proposal_to_purchase_form001.pdf) is the flattened form
with the DocuSign layer stripped out. We draw the values on a transparent overlay
at the form's own coordinates (PDF points, origin bottom-left, page 612 x 1008)
and merge it onto the blank.

The buyer signature lines are deliberately left empty: the PDF goes out unsigned,
exactly like the "-unsigned" file it was modeled on. Sign it through DocuSign or
by hand once the terms are agreed.
"""
from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from ..models import OfferForm

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "proposal_to_purchase_form001.pdf"
PAGE = (612, 1008)
FONT = "Helvetica"

# Checkbox squares on the form: (x, y) of the lower-left corner, and side length.
BOXES = {
    "mortgage_fha": (314.2, 771.8, 10.3), "mortgage_va": (349.4, 771.8, 10.1),
    "mortgage_conventional": (378.0, 771.8, 10.1), "mortgage_other": (449.0, 771.8, 10.3),
    "possession_settlement": (490.6, 605.8, 8.0), "possession_other": (58.1, 589.2, 8.0),
    "insp_wood_boring": (69.8, 566.4, 8.2), "insp_home": (335.3, 567.8, 8.0),
    "insp_septic": (69.8, 555.4, 8.0), "insp_other": (335.3, 555.4, 8.0),
    "seller_well": (69.8, 523.4, 8.2), "seller_other": (335.3, 523.4, 8.2),
    "assets_not_contingent": (85.7, 449.5, 8.2), "assets_sale_under_contract": (85.7, 428.2, 7.9),
    "assets_sale_not_under_contract": (85.7, 387.8, 8.2),
    "firm_seller_agent": (60.2, 241.4, 7.9), "firm_buyer_agent": (200.4, 241.4, 7.9),
    "firm_dual_agent": (309.8, 241.4, 7.9), "firm_transaction_broker": (457.7, 240.0, 8.2),
    "listing_seller_agent": (60.2, 194.2, 7.9), "listing_buyer_agent": (200.4, 194.2, 7.9),
    "listing_dual_agent": (309.8, 194.2, 7.9), "listing_transaction_broker": (457.7, 194.2, 7.9),
}

MONEY_CENTER_X = 411  # the $ blanks run from about x=380 to x=442


def _money(v: float | None) -> str:
    return "" if v in (None, 0) else f"{v:,.0f}"


def _text(c: canvas.Canvas, s: str | None, x: float, y: float, max_w: float, size: float = 10,
          align: str = "left", min_size: float = 6) -> None:
    s = (s or "").strip()
    if not s:
        return
    while size > min_size and stringWidth(s, FONT, size) > max_w:
        size -= 0.25
    if stringWidth(s, FONT, size) > max_w:  # still too long at min size: trim
        while s and stringWidth(s + "…", FONT, size) > max_w:
            s = s[:-1]
        s += "…"
    c.setFont(FONT, size)
    y += size * 0.22  # coordinates are the bottom of the writing line; lift the baseline off the rule
    if align == "center":
        c.drawCentredString(x, y, s)
    elif align == "right":
        c.drawRightString(x, y, s)
    else:
        c.drawString(x, y, s)


def _check(c: canvas.Canvas, key: str) -> None:
    """A drawn check mark (vector, so it looks the same in every PDF viewer)."""
    x, y, s = BOXES[key]
    c.saveState()
    c.setLineWidth(max(1.1, s * 0.15))
    c.setLineCap(1)
    c.setLineJoin(1)
    p = c.beginPath()
    p.moveTo(x + s * 0.18, y + s * 0.52)
    p.lineTo(x + s * 0.42, y + s * 0.22)
    p.lineTo(x + s * 0.88, y + s * 0.86)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


def render(f: OfferForm) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    c.setFillColorRGB(0.05, 0.05, 0.15)
    c.setStrokeColorRGB(0.05, 0.05, 0.15)

    # Parties and property
    _text(c, f.buyer_name, 30, 915, 420, 10)
    _text(c, f.presenting_firm, 30, 899.5, 262, 9.5)
    _text(c, f.property_address, 30, 885, 545, 10.5)

    # Money
    _text(c, _money(f.price), MONEY_CENTER_X, 872.5, 58, 10, "center")
    _text(c, _money(f.initial_deposit), MONEY_CENTER_X, 854.5, 58, 10, "center")
    _text(c, _money(f.additional_deposit), MONEY_CENTER_X, 831.5, 58, 10, "center")
    _text(c, f.additional_deposit_date, 160, 816.5, 245, 9.5)
    _text(c, _money(f.balance_due), MONEY_CENTER_X, 798.5, 58, 10, "center")
    if f.mortgage_type:
        _check(c, f"mortgage_{f.mortgage_type}")
    _text(c, _money(f.mortgage_amount), MONEY_CENTER_X, 762, 58, 10, "center")

    # Settlement
    _text(c, f.settlement_date, 389, 712, 140, 10, "center")
    lines = [ln for ln in (f.title_company or "").splitlines() if ln.strip()]
    if lines:
        _text(c, lines[0], 28, 697, 322, 11)
    if len(lines) > 1:
        _text(c, " ".join(lines[1:]), 28, 683.5, 540, 11)

    # (1) Fixtures
    _text(c, f.also_included, 332, 650.5, 252, 9)
    _text(c, f.specifically_excluded, 152, 621.5, 430, 9)

    # (2) Possession
    if f.possession == "settlement":
        _check(c, "possession_settlement")
    elif f.possession == "other":
        _check(c, "possession_other")
        _text(c, f.possession_other, 100, 590.5, 480, 9)

    # (3) Inspections
    for key, on in (("insp_wood_boring", f.insp_wood_boring), ("insp_home", f.insp_home),
                    ("insp_septic", f.insp_septic), ("seller_well", f.seller_well)):
        if on:
            _check(c, key)
    if f.insp_other:
        _check(c, "insp_other")
        _text(c, f.insp_other, 380, 556.5, 200, 9)
    if f.seller_other:
        _check(c, "seller_other")
        _text(c, f.seller_other, 382, 523.5, 198, 9)

    # (4) Sufficient assets
    if f.assets == "not_contingent":
        _check(c, "assets_not_contingent")
    elif f.assets == "sale_under_contract":
        _check(c, "assets_sale_under_contract")
        _text(c, f.assets_property, 100, 416.5, 330, 9)
    elif f.assets == "sale_not_under_contract":
        _check(c, "assets_sale_not_under_contract")
        _text(c, f.assets_property, 100, 377.5, 320, 9)

    # (5) Other terms: up to two lines
    other = (f.other_terms or "").replace("\n", " ").strip()
    if other:
        words, first = other.split(), ""
        while words and stringWidth((first + " " + words[0]).strip(), FONT, 9) <= 490:
            first = (first + " " + words.pop(0)).strip()
        _text(c, first, 92, 361, 492, 9)
        _text(c, " ".join(words), 23, 345.5, 560, 9)

    # Brokerage disclosure
    _text(c, f.firm_name, 30, 296, 478, 12)
    _text(c, f.licensee, 30, 282, 470, 12)
    if f.firm_role:
        _check(c, f"firm_{f.firm_role}")
    _text(c, f.listing_firm, 39, 220, 445, 10)
    if f.listing_role:
        _check(c, f"listing_{f.listing_role}")
    _text(c, str(f.valid_days) if f.valid_days else "", 54, 166.5, 110, 12)

    # Presenting agency (left column)
    addr = [ln for ln in (f.presenting_address or "").splitlines() if ln.strip()]
    if addr:
        _text(c, addr[0], 25, 127, 190, 12)
    if len(addr) > 1:
        _text(c, " ".join(addr[1:]), 25, 113.3, 190, 12)
    _text(c, f.office_tel, 90, 101, 125, 11)
    _text(c, f.office_fax, 90, 88.5, 125, 11)
    _text(c, f.agent_name, 87, 74.5, 130, 12)
    _text(c, f.agent_cell, 92, 63, 124, 12)
    _text(c, f.agent_email, 89, 51.5, 128, 12)

    # Buyer block (signature line stays blank on purpose)
    _text(c, f.buyer_date, 366, 127, 175, 12)
    _text(c, f.buyer_signed_2, 372, 113, 200, 10)
    _text(c, f.buyer_date_2, 366, 101, 175, 10)
    baddr = [ln for ln in (f.buyer_address or "").splitlines() if ln.strip()]
    if baddr:
        _text(c, baddr[0], 372, 88.5, 208, 9)
    if len(baddr) > 1:
        _text(c, " ".join(baddr[1:]), 332, 77, 250, 9)

    _text(c, f.footer_company, 78, 19, 380, 11)
    c.showPage()
    c.save()

    base = PdfReader(str(TEMPLATE))
    overlay = PdfReader(io.BytesIO(buf.getvalue()))
    w = PdfWriter()
    page = base.pages[0]
    page.merge_page(overlay.pages[0])
    w.add_page(page)
    w.add_metadata({"/Title": f"Proposal to Purchase - {f.property_address}", "/Author": f.buyer_name or "",
                    "/Producer": "SPREV Acquisition Engine"})
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def filename(f: OfferForm) -> str:
    street = (f.property_address or "property").split(",")[0]
    safe = "".join(ch if ch.isalnum() else "_" for ch in street).strip("_")
    return f"{safe}_Offer-unsigned.pdf"
