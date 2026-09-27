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
| List price, DOM, status | RESO MLS (enriches the record) | Bright MLS: `RESO_BASE_URL`, `RESO_TOKEN_URL`, `RESO_CLIENT_ID`, `RESO_CLIENT_SECRET` (see below) |
| Rent estimate | RentCast → sample | same RentCast key |
| Neighborhood (tract income, rent, vacancy, owner-occupancy, poverty, commute, 5-yr growth) | Census ACS → sample | A free `CENSUS_API_KEY` ([sign up](https://api.census.gov/data/key_signup.html)); it arrives by email in minutes |
| Comps | RESO closed sales → RentCast listings → sample | MLS feed, or RentCast |
| Explanation / letter polish | Claude → template | `ANTHROPIC_API_KEY` |

**Bright MLS setup:**

1. **Apply for access.** Bright MLS provides a RESO Web API. Request data access through Bright's developer program ([brightmls.com/benefits/developers](https://www.brightmls.com/benefits/developers)); you'll need to be a Bright subscriber or work through one. During onboarding Bright issues a test **client ID and secret**, then production credentials once your use is approved.
2. **Start on the test endpoint:** `RESO_BASE_URL=https://bright-reso.tst.brightmls.com/RESO/OData/bright`.
3. **Set the OAuth fields.** Put the token URL from Bright's Authentication page into `RESO_TOKEN_URL`, along with `RESO_CLIENT_ID` and `RESO_CLIENT_SECRET`. If Bright specifies a scope, set `RESO_SCOPE`. If the token request returns 401, try `RESO_TOKEN_AUTH=basic`.
4. **Switch to production** after approval: `RESO_BASE_URL=https://bright-reso.brightmls.com/RESO/OData/bright`, plus the production ID and secret.

Bright follows the RESO Data Dictionary 1.7, so the fields the connector reads (`ClosePrice`, `CloseDate`, `LivingArea`, `BedroomsTotal`, ...) are standard. Check `$metadata` if a query is rejected.

`GET /api/analyses/{id}/trail` shows which provider answered each question for a given analysis, and which ones failed.

**About the sources:**

- **Census ACS** is the same public tract data that justicemap.org maps. The engine pulls it straight from api.census.gov.
- **Zillow** retired its public listing and Zestimate APIs. Zillow data now comes through the **Bridge API** (Zillow Group's MLS platform), which is a RESO Web API, so `connectors/reso.py` covers it. Bridge requires approval from the MLS.
- **MLS (Bright MLS for South Jersey)** also needs a data license or IDX/VOW agreement for API access. An agent login alone doesn't grant API or redistribution rights, so confirm your permitted use before building production features on it.
- **RentCast comps** are recent listings with list prices, not confirmed closed sales. Treat them as a fallback until an MLS feed is connected.
- **Condition** isn't in any feed. It defaults to "Good" for live records. The RESO connector infers it from listing remarks ("TLC", "fully renovated"). Override the rehab number in the UI after a walkthrough.

## Sending offers from Gmail

Approved offers are emailed **from your own Gmail account** through the Gmail API. They land in your Sent folder, and agents' replies come back to your inbox. The app uses the Gmail API over HTTPS because Render's free plan blocks outgoing email (SMTP) ports.

The app only ever asks for the `gmail.send` permission. It can send as you, but it can't read your mail.

**One-time setup (about 15 minutes):**

1. **Create a Google Cloud project.** Go to [console.cloud.google.com](https://console.cloud.google.com), create a project (for example "SPREV Offers"), then open **APIs & Services → Library**, search for **Gmail API**, and click **Enable**.
2. **Set up the consent screen.** Go to **APIs & Services → OAuth consent screen** (called "Google Auth Platform" in newer consoles):
   - User type: **External**. App name: anything. Support email: your Gmail.
   - Under **Audience**, add your Gmail as a test user.
   - Then click **Publish app** so it moves to "In production". This matters: while the app is in *Testing*, Google expires the authorization after **7 days** and sending stops. You don't need Google's verification for your own account; you'll just click past an "unverified app" warning once.
3. **Create a client.** Go to **Credentials → Create credentials → OAuth client ID**, choose application type **Desktop app**, and copy the **Client ID** and **Client secret**.
4. **Authorize on your own computer.** This opens a browser:
   ```bash
   python3 backend/scripts/gmail_auth.py --client-id YOUR_ID.apps.googleusercontent.com --client-secret YOUR_SECRET
   ```
   Sign in with the Gmail account you want to send from, then allow "Send email on your behalf". The script sends you a test email and prints four values.
5. **Add the values to Render.** In **sprev-api → Environment**, add the four printed values: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` and `GMAIL_SENDER`. Optionally add:
   - `EMAIL_SENDER_NAME`, for example "Lalith, SP Real Estate Ventures"
   - `EMAIL_CC`, a comma-separated list of addresses to copy on every offer, such as a partner

   Then click **Save, rebuild, and deploy**.

When it's working, the Data sources card shows **Email sending · you@gmail.com** with a green dot.

**How sending works in the app:**

1. Fill in the letter terms: agent name, your name and your phone. **Send is blocked while any `[placeholder]` remains**, both in the page and on the server.
2. Enter the agent's email and your name, and tick **I reviewed the numbers and approve this offer**.
3. Click **Approve & send…**. A confirmation shows the price, the property, the recipient and your sending address. Click **Send offer now**.
4. The approval is saved with a snapshot of the numbers, then emailed.
   - The Gmail message ID and send time are stored, and the address's status becomes "Offer sent".
   - An approval is never emailed twice.
   - If a send fails, the reason is shown along with a **Retry send** button.

**Stopping or revoking access:** remove the Gmail variables from Render, or revoke the app at [myaccount.google.com/permissions](https://myaccount.google.com/permissions). Treat the refresh token like a password.

**Not on Render's free plan?** SMTP works too. Set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=465`, `SMTP_USERNAME` to your Gmail address, and `SMTP_PASSWORD` to a [Google app password](https://myaccount.google.com/apppasswords) (this needs 2-Step Verification). The Gmail API is used whenever both are configured.

## Proposal to Purchase PDF

Each emailed offer can carry a filled-in **NJ Proposal to Purchase (FORM#001)** as a PDF attachment, named like `218_Carpenter_St_Offer-unsigned.pdf`.

- **Template:** `backend/app/templates/proposal_to_purchase_form001.pdf` is the blank form, made from your 23 W Emlen Ave offer with the DocuSign layer removed (values, checkmarks, signature and envelope ID). `backend/app/services/offer_pdf.py` writes the values onto it at the form's own coordinates, shrinks long text to fit, and draws the checkmarks as shapes.
- **Pre-filling:** the address, price, dates and listing firm come from the analysis. Your standard details come from saved defaults: buyer entity, SRV Realty and Kumar's licensee line, title company, agent contact, usual inspections and valid days. Change them in the letter card under **Edit form fields**, then click **Save my details as defaults**.
- **Money:** balance due = price − deposits − mortgage amount. The app recalculates it as you type, and the server rejects a PDF whose price doesn't match the approved offer or whose balance doesn't add up.
- **Unsigned on purpose:** the buyer signature line stays blank. Sign in DocuSign once terms are agreed.
- **Record:** each approval stores the exact form it was sent with, and `GET /api/approvals/{id}/pdf` regenerates that PDF.

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

## Deploying for a demo (Render)

1. In [Render](https://dashboard.render.com), choose **New → Blueprint** and select this repo. `render.yaml` creates three things on free plans:
   - `sprev-api`, the FastAPI service
   - `sprev-web`, the Next.js app
   - `sprev-db`, a Postgres database
2. When Render asks for **SITE_USERNAME** and **SITE_PASSWORD**, enter the login you want your people to use. Leave RENTCAST_API_KEY and ANTHROPIC_API_KEY blank for now to stay in sample mode.
3. Wait for both services to go live, then open the `sprev-web` URL and sign in.
4. If Render named the API something other than `https://sprev-api.onrender.com`, open sprev-web → Environment, set **BACKEND_URL** to the API's real URL, and click **Manual Deploy**. BACKEND_URL is read at build time, so it only takes effect after a redeploy.

How access is locked down:

- **The web app** asks for SITE_USERNAME / SITE_PASSWORD before showing anything (`frontend/proxy.ts`).
- **The API** only answers requests that carry `API_TOKEN`. Render generates the token and shares it between the two services. The browser never sees it; the Next.js server attaches it when it forwards `/api/*`.
- **The public API URL** returns 401 to anyone else. `/api/health` stays open for Render's health check.

Free-plan limits:

- **Cold starts:** services sleep after about 15 minutes idle, so the first load after a break takes 30–60 seconds. Open the app a minute before a demo.
- **Database expiry:** the free Postgres database expires after 30 days. Upgrade it, or re-create it, before relying on the approval history.

**Other hosts:**

- **Frontend:** deploy `frontend/` to Vercel with `BACKEND_URL`, `API_TOKEN`, `SITE_USERNAME` and `SITE_PASSWORD` set.
- **Backend:** deploy `backend/` anywhere that runs a Dockerfile, with `DATABASE_URL` and the same `API_TOKEN`.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/analyze` | `{address, criteria?, rehab_override?}` → full analysis (stored) |
| POST | `/api/analyses/{id}/recompute` | New criteria or rehab against the stored data, with no provider calls |
| POST | `/api/analyses/{id}/letter` | `{tier, terms, polish_with_ai}` → letter text |
| POST | `/api/analyses/{id}/approve` | Logs who approved which offer (snapshot of criteria, comps, MAO); with `send: true`, emails it to `agent_email` |
| POST | `/api/approvals/{id}/send` | Retries sending an approved offer (never sends twice) |
| GET | `/api/analyses/{id}/approvals` | Approval and send history for an analysis |
| GET | `/api/analyses/{id}/offer-form?tier=` | Proposal to Purchase pre-filled for one offer tier |
| POST | `/api/offer-pdf` | Render a filled Proposal to Purchase (PDF) |
| GET/PUT | `/api/offer-profile` | Your saved offer-form defaults |
| GET | `/api/approvals/{id}/pdf` | The PDF that was attached to an approved offer |
| GET | `/api/analyses` | Recent analyses |
| GET | `/api/analyses/{id}` / `/trail` | One analysis / its data provenance |
| GET | `/api/providers` | Which connectors are active |

## Next steps

1. **Follow-ups:** track agent replies (Gmail thread IDs are already stored with each sent offer) and flag offers with no response after 48 hours.
2. **Per-user login:** the site currently has one shared password. Add individual accounts (for example Clerk or Auth.js) so the approvals log records who approved each offer.
3. **Pipeline tracking:** track statuses beyond "Approved" (Offer sent → Countered → Under contract → Passed), which also produces the training data for the acceptance model.
4. **Rehab line items:** replace the $/sf rule with a walkthrough checklist (roof, HVAC, kitchen, baths, flooring, paint).
5. **Strategy presets:** add buy-and-hold, BRRRR (refi at ARV) and flip, each with its own criteria and MAO rule.

Not legal or financial advice. Have a New Jersey attorney review offer terms and contracts.
