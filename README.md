# SPREV Acquisition Engine

Address in → property profile, neighborhood scorecard, comps, deterministic underwriting, maximum allowable offer (MAO), four offer tiers, and a draft offer letter behind a human approval step.

```
Next.js (frontend/)  ──/api/* proxy──▶  FastAPI (backend/)  ──▶  Connectors: Sample · Census ACS · RentCast · RESO/MLS
                                              │
                                              └──▶ Postgres / SQLite: every analysis + every approval (audit trail)
```

The math lives in one place: `backend/app/services/`. The frontend only displays results and sends edits back. When Claude is connected, it writes the explanation and polishes the letter, but it never computes a number.

## Run it locally

**Option A: Docker (one command)**

```bash
docker compose up --build
# app:      http://localhost:3000
# API docs: http://localhost:8000/docs
```

**Option B: two terminals**

```bash
# 1. API
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # defaults to sample data + SQLite, no keys needed
uvicorn app.main:app --reload --port 8000

# 2. Web
cd frontend
npm install
npm run dev                     # http://localhost:3000, proxies /api to localhost:8000
```

Run the tests with `cd backend && pytest`. They cover the amortization math, the MAO rules, offer tiers, Census/RentCast parsing against mocked responses, and a full analyze → recompute → letter → approve round trip.

## Turning on real data

Set `DATA_MODE=live` in `backend/.env`, then add whichever keys you have. Each question walks a chain of providers. If none of them can answer, it falls back to sample data, and the UI flags that data as synthetic.

| Question | Chain | What you need |
|---|---|---|
| Property record (beds, baths, sqft, taxes, year) | RentCast → sample | `RENTCAST_API_KEY` ([rentcast.io](https://www.rentcast.io/api)) |
| List price, DOM, status | RESO MLS (enriches the record) | `RESO_BASE_URL`, `RESO_ACCESS_TOKEN` |
| Rent estimate | RentCast → sample | same RentCast key |
| Neighborhood (tract income, rent, vacancy, owner-occupancy, poverty, commute, 5-yr growth) | Census ACS → sample | Nothing. It works keyless; a free `CENSUS_API_KEY` raises the limits |
| Comps | RESO closed sales → RentCast listings → sample | MLS feed, or RentCast |
| Explanation / letter polish | Claude → template | `ANTHROPIC_API_KEY` |

`GET /api/analyses/{id}/trail` shows which provider answered each question for a given analysis, and which ones failed.

**About the sources:**

- **Census ACS** is the same public tract data that justicemap.org maps. The engine pulls it straight from api.census.gov.
- **Zillow** retired its public listing and Zestimate APIs. Zillow data now comes through the **Bridge API** (Zillow Group's MLS platform), which is a RESO Web API, so `connectors/reso.py` covers it. Bridge requires approval from the MLS.
- **MLS (Bright MLS for South Jersey)** also needs a data license or IDX/VOW agreement for API access. An agent login alone doesn't grant API or redistribution rights, so confirm your permitted use before building production features on it.
- **RentCast comps** are recent listings with list prices, not confirmed closed sales. Treat them as a fallback until an MLS feed is connected.
- **Condition** isn't in any feed. It defaults to "Good" for live records. The RESO connector infers it from listing remarks ("TLC", "fully renovated"). Override the rehab number in the UI after a walkthrough.

## Where to change the rules

| What | File |
|---|---|
| Default criteria (rate, down payment, CoC, DSCR, vacancy, maintenance, ARV cap) | `backend/app/models.py` → `Criteria` (the UI can override every one) |
| Comp similarity scoring and the adjustment grid ($/sf, bed, bath, condition) | `backend/app/services/valuation.py` |
| Operating statement, MAO solver, septic reserve | `backend/app/services/underwriting.py` |
| Offer tiers (92 / 96 / 100 / 104% of MAO), acceptance heuristic, risk flags | `backend/app/services/offers.py` |
| Rehab rules ($/sf by condition, pool removal, NJ lead-safe allowance) | `backend/app/services/rehab.py` |
| Letter terms and NJ-specific clauses (attorney review, pool permit, septic, lead) | `backend/app/services/narrative.py` |
| Add a data provider | Add a class in `backend/app/connectors/` with the methods in `base.py`, then insert it into a chain in `registry.py` |

The acceptance-likelihood curve is a placeholder heuristic. Once roughly 50 offers are logged in the `approvals` table, fit it to your actual accepted and rejected offers.

## Deploying for a demo

**Render (simplest, one blueprint):** push this folder to a GitHub repo, then in Render choose New → Blueprint and select the repo. `render.yaml` creates the API, the web app and a Postgres database. If Render assigns different service URLs, update `CORS_ORIGINS` on the API and `BACKEND_URL` on the web service. `BACKEND_URL` is read at build time, so redeploy the web service after changing it.

**Vercel + Railway/Render:** deploy `frontend/` to Vercel with `BACKEND_URL` set to the API's public URL. Deploy `backend/` anywhere that runs a Dockerfile, and give it a Postgres `DATABASE_URL`.

Before sharing the link, put the app behind a login. Vercel password protection or Cloudflare Access both work, and so does basic auth at the proxy. The API has no authentication yet.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/analyze` | `{address, criteria?, rehab_override?}` → full analysis (stored) |
| POST | `/api/analyses/{id}/recompute` | New criteria or rehab against the stored data, with no provider calls |
| POST | `/api/analyses/{id}/letter` | `{tier, terms, polish_with_ai}` → letter text |
| POST | `/api/analyses/{id}/approve` | Logs who approved which offer, with a snapshot of criteria, comps and MAO |
| GET | `/api/analyses` | Recent analyses |
| GET | `/api/analyses/{id}` / `/trail` | One analysis / its data provenance |
| GET | `/api/providers` | Which connectors are active |

## Next steps

1. **Email delivery:** send the letter from `approve()` in `backend/app/main.py` via SMTP, SendGrid or the Gmail API, then set `sent=True`. Approval is already required first.
2. **Auth:** add a login (for example Clerk or Auth.js on the frontend, and a shared API token on the backend) so the approvals log records real users.
3. **Pipeline tracking:** track statuses beyond "Approved" (Offer sent → Countered → Under contract → Passed), which also produces the training data for the acceptance model.
4. **Rehab line items:** replace the $/sf rule with a walkthrough checklist (roof, HVAC, kitchen, baths, flooring, paint).
5. **Strategy presets:** add buy-and-hold, BRRRR (refi at ARV) and flip, each with its own criteria and MAO rule.

Not legal or financial advice. Have a New Jersey attorney review offer terms and contracts.
