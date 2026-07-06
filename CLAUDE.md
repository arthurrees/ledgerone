# LedgerOne

Local-first personal budgeting app with Chase bank sync and AI-powered insights.

> **Public GitHub repo (portfolio).** This is published as a public portfolio project.
> Never commit real credentials or financial data. `backend/.env`, `backend/*.db`, and the
> internal `SESSION_LOG.md` (which holds real balances and account details) are gitignored
> and stay local. Use `backend/.env.example` as the template for your own keys.

## Architecture

- **Frontend**: React 19 + Vite, single-page app in `src/`
- **Backend**: Python FastAPI on port 8787, in `backend/`
- **Database**: SQLite (`backend/ledgerone.db`, gitignored)
- **AI**: Local Ollama (`qwen3.5-gpu`) for categorization, insights, and chat
- **Bank sync**: Plaid Production API for Chase auto-sync, with CSV fallback

## Running

```bash
# Backend (must start first)
cd backend && python server.py

# Frontend
npm run dev
```

Backend runs on `:8787`, frontend on `:5173` (or next available port).
API calls use Vite's proxy (`/api` → `localhost:8787`), so the frontend uses relative URLs.

## Project Structure

```
LedgerOne/
├── src/
│   ├── App.jsx          # All views (Dashboard, Transactions, Budgets, Insights, Accounts, Settings)
│   ├── api.js           # API client — all fetch calls to backend (relative URLs, proxied by Vite)
│   ├── App.css          # Full styling (dark theme)
│   └── index.css        # CSS variables and globals
├── backend/
│   ├── server.py        # FastAPI app, all endpoints
│   ├── database.py      # SQLite schema, queries, helpers
│   ├── csv_import.py    # Chase CSV parser with dedup
│   ├── ai_engine.py     # Ollama integration (categorize, insights, chat, budget draft)
│   ├── plaid_client.py  # Plaid Link flow, token exchange, transaction sync
│   ├── .env             # PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV (gitignored)
│   └── requirements.txt # Python deps (fastapi, uvicorn, python-multipart, httpx, plaid-python, python-dotenv)
├── vite.config.js       # Vite config — proxy /api to :8787, ngrok host allowed
└── .gitignore
```

## Key Conventions

- All API routes are under `/api/` — see `backend/server.py` for the full list
- CORS allows `localhost:5173`, `5174`, `4173`, and the ngrok tunnel domain
- Vite proxies `/api/*` and `/health` to `localhost:8787` so frontend uses relative URLs
- Transactions use a SHA-256 hash for dedup (date + amount + description + account)
- Plaid transactions use `plaid_{transaction_id}` as the hash
- Rules engine does case-insensitive substring matching on merchant names
- AI endpoints send summarized data to Ollama, never raw transaction dumps
- Budget months use `YYYY-MM` format (e.g. `2026-05`)

## Plaid Integration

- Chase does NOT use OAuth (`OAuth: False` from Plaid institution query)
- Production access was granted 2026-05-09; institution registration can take up to 24 hours
- Plaid error `INSTITUTION_REGISTRATION_REQUIRED` means registration is still propagating
- Link token does NOT need a redirect_uri for Chase (non-OAuth institution)
- For OAuth institutions, expose the dev server via an ngrok tunnel and add that host to
  `vite.config.js` (`allowedHosts`) and `server.py` (CORS `allow_origins`)
- PlaidLinkButton logs full error details to browser console via onExit callback

## TODO

- [ ] Inline transaction editing — click a row to change category/merchant (action menu exists but is non-functional)
- [ ] Auto-categorize button — one-click AI categorization of all "Review" transactions in the Transactions filter bar
- [ ] Month navigation on Dashboard — add month switcher (currently locked to current month)
- [ ] Plaid Chase link — retry after 2026-05-10 once institution registration propagates

## Sensitive Files (gitignored)

- `backend/.env` — Plaid API keys
- `backend/ledgerone.db` — all financial data
- `backend/__pycache__/`
