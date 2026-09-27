"""Deterministic underwriting: the operating statement, returns, and the MAO.

The MAO is the highest price that satisfies every rule in Criteria:
  - cash-on-cash >= target
  - DSCR >= minimum
  - (price + rehab) <= max % of ARV
Each rule is solved independently by bisection (all three are monotonic in
price), and the lowest answer wins. That rule is reported as "binding".
"""
from __future__ import annotations

from ..models import Constraint, Criteria, Economics, PropertyProfile, RentEstimate, Underwriting

SEPTIC_RESERVE = 450  # $/yr: pumping every ~3 years plus inspection


def annual_debt_service(loan: float, rate_pct: float, years: int) -> float:
    n = years * 12
    i = rate_pct / 100 / 12
    if loan <= 0:
        return 0.0
    if i == 0:
        return loan / n * 12
    return loan * i / (1 - (1 + i) ** -n) * 12


def economics(prop: PropertyProfile, rent_monthly: float, price: float, rehab: float, arv: float,
              c: Criteria) -> Economics:
    gross = rent_monthly * 12
    vac = gross * c.vacancy / 100
    egi = gross - vac
    maint = gross * c.maintenance_capex / 100
    mgmt = gross * c.management / 100
    septic = SEPTIC_RESERVE if "septic" in prop.utilities.lower() else 0
    opex = prop.annual_tax + prop.annual_insurance + maint + mgmt + septic
    noi = egi - opex
    down = price * c.down_payment / 100
    loan = price - down
    ds = annual_debt_service(loan, c.interest_rate, c.loan_years)
    closing = price * c.closing_costs / 100
    cash_in = down + closing + rehab
    cf = noi - ds
    return Economics(
        price=price, gross_rent=gross, vacancy=vac, egi=egi, tax=prop.annual_tax, insurance=prop.annual_insurance,
        maintenance_capex=maint, management=mgmt, septic_reserve=septic, opex=opex, noi=noi, loan=loan,
        debt_service=ds, down_payment=down, closing_costs=closing, rehab=rehab, cash_in=cash_in, cash_flow=cf,
        coc=cf / cash_in if cash_in else 0, dscr=noi / ds if ds else 99.0,
        cap_rate=noi / (price + rehab) if price + rehab else 0,
        all_in_pct_arv=(price + rehab) / arv if arv else 0,
    )


def _max_price(ok, lo: float = 10_000, hi: float = 5_000_000) -> float:
    if not ok(lo):
        return 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


def underwrite(prop: PropertyProfile, rent: RentEstimate, rehab: float, arv: float, c: Criteria) -> Underwriting:
    def econ(p):
        return economics(prop, rent.monthly, p, rehab, arv, c)

    rules = [
        (f"Cash-on-cash ≥ {c.target_coc:g}%", _max_price(lambda p: econ(p).coc >= c.target_coc / 100)),
        (f"DSCR ≥ {c.min_dscr:.2f}", _max_price(lambda p: econ(p).dscr >= c.min_dscr)),
        (f"All-in ≤ {c.max_all_in_pct_arv:g}% of ARV", max(0.0, arv * c.max_all_in_pct_arv / 100 - rehab)),
    ]
    mao = min(v for _, v in rules)
    mao = float(int(mao // 500 * 500))
    binding = min(rules, key=lambda r: r[1])[0]
    constraints = [Constraint(name=n, max_price=round(v), binding=(n == binding)) for n, v in rules]
    return Underwriting(criteria=c, rehab=rehab, constraints=constraints, mao=mao, at_mao=econ(max(mao, 1)))
