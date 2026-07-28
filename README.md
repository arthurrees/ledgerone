# LedgerOne

Local-first personal budgeting app with Chase bank sync (Plaid) and AI-powered insights via local Ollama.

## Run locally

Backend (must start first):

```bash
cd backend
python server.py
```

The production backend runs on Son of Francis at
`http://100.96.116.18:8787`. AI requests are sent over Tailscale to the
authenticated Dad API gateway on Francis, where Ollama performs inference
locally.

Frontend:

```bash
npm install
npm run dev
```

Frontend runs on Francis at `http://localhost:5173` and proxies `/api` to the
backend on Son of Francis.

## Stack

- **Frontend**: React 19 + Vite, single-page app in `src/`
- **Backend**: Python FastAPI (`backend/server.py`) on port 8787
- **Backend service**: `ledgerone.service` in Arthur's systemd user instance
- **Backend state**: `/home/arthur/Projects/LedgerOne/backend/ledgerone.db`
- **Backend secrets**: `/home/arthur/Projects/LedgerOne/backend/.env` (mode 600)
- **LLM**: Dad API at `http://100.83.194.119:5560/v1`; Ollama remains on Francis
- **Database**: SQLite (`backend/ledgerone.db`, gitignored)
- **AI**: Local Ollama (`qwen3.5-gpu`) for categorization, insights, and chat
- **Bank sync**: Plaid Production API for Chase auto-sync, with Chase CSV fallback

## Features

- Dashboard with monthly income, spending, savings, cash flow, budget status, recent transactions, and AI brief.
- Transactions table with search, filters, review states, and CSV export.
- Budget planning screen with category progress, planned payments, and rules.
- Insights screen for AI prompts and detected patterns.
- Accounts screen with Chase/Plaid Link connection and CSV import fallback.
- CSV import modal with duplicate detection and review preview.

## Configuration

Plaid credentials live in `backend/.env` (gitignored):

```
PLAID_CLIENT_ID=...
PLAID_SECRET=...
PLAID_ENV=production
```

See `CLAUDE.md` for project conventions and architecture details.
