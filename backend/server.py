"""LedgerOne — FastAPI backend server on port 8787."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import database as db
import ai_engine
import plaid_client
import telegram_bot
from csv_import import parse_chase_csv


logger = logging.getLogger("ledgerone")

AUTO_SYNC_INTERVAL = 6 * 60 * 60  # 6 hours in seconds


async def auto_sync_loop():
    """Background task: sync Plaid transactions every 6 hours."""
    await asyncio.sleep(10)  # wait for startup
    while True:
        try:
            with db.get_db() as conn:
                token = conn.execute("SELECT value FROM settings WHERE key = 'plaid_access_token'").fetchone()
            if token:
                logger.info("Auto-sync: syncing Plaid transactions...")
                stats = plaid_client.sync_transactions()
                logger.info(f"Auto-sync complete: {stats}")

                # Notify via Telegram
                if stats.get("added", 0) > 0 or stats.get("modified", 0) > 0:
                    telegram_bot.send_notification_sync(
                        f"🔄 *Auto-sync complete*\n\n"
                        f"Added: {stats['added']}\n"
                        f"Modified: {stats['modified']}\n"
                        f"Removed: {stats['removed']}"
                    )
        except Exception as e:
            logger.warning(f"Auto-sync failed: {e}")
        await asyncio.sleep(AUTO_SYNC_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    sync_task = asyncio.create_task(auto_sync_loop())
    await telegram_bot.start_bot()
    yield
    sync_task.cancel()
    await telegram_bot.stop_bot()


app = FastAPI(title="LedgerOne", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:4173",
        # Add your ngrok tunnel origin here for Plaid OAuth institutions, e.g.
        # "https://your-tunnel.ngrok-free.dev",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ─── Dashboard ────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard(month: str = Query(default=None), range: str = Query(default="month")):
    if not month:
        month = datetime.now().strftime("%Y-%m")

    if range == "ytd":
        year = month.split("-")[0]
        summary = db.get_range_summary(f"{year}-01-01", f"{year}-12-31")
    elif range == "mtd":
        today = datetime.now().strftime("%Y-%m-%d")
        summary = db.get_range_summary(f"{month}-01", today)
    else:
        summary = db.get_monthly_summary(month)

    budgets = db.get_budgets(month)
    planned_payments = db.get_planned_payments(month)
    recent = db.get_transactions(month=month, limit=5)
    cash_flow = db.get_cash_flow(0)  # all months — frontend controls range
    accounts = db.get_accounts()

    income = summary["income"]
    spending = summary["spending"]
    left = income - spending
    planned_total = sum(p["amount"] for p in planned_payments)

    # Real balance from Plaid (sum across all linked accounts)
    total_available = sum(a.get("balance_available") or 0 for a in accounts if a.get("balance_available") is not None)
    total_current = sum(a.get("balance_current") or 0 for a in accounts if a.get("balance_current") is not None)

    return {
        "metrics": {
            "income": income,
            "spending": spending,
            "left_to_budget": left,
            "planned_future": planned_total,
            "projected_left": left - planned_total,
            "savings_rate": round((left / income * 100) if income > 0 else 0, 1),
            "balance_available": total_available,
            "balance_current": total_current,
        },
        "budgets": [
            {
                **b,
                "actual": summary["by_category"].get(b["category"], 0),
            }
            for b in budgets
        ],
        "spending_by_category": [
            {"category": cat, "amount": amt}
            for cat, amt in sorted(summary["by_category"].items(), key=lambda x: x[1], reverse=True)
            if amt > 0
        ],
        "planned_payments": planned_payments,
        "recent_transactions": recent,
        "cash_flow": cash_flow,
    }


# ─── Transactions ────────────────────────────────────────

@app.get("/api/transactions")
def list_transactions(
    month: str = None,
    category: str = None,
    status: str = None,
    search: str = None,
    limit: int = 200,
):
    return db.get_transactions(month=month, category=category, status=status, search=search, limit=limit)


class TransactionUpdate(BaseModel):
    category: str | None = None
    status: str | None = None
    merchant: str | None = None


@app.patch("/api/transactions/{tx_id}")
def update_transaction(tx_id: int, body: TransactionUpdate):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    db.update_transaction(tx_id, updates)
    return {"ok": True}


# ─── CSV Import ───────────────────────────────────────────

@app.post("/api/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    account: str = Form("Chase Checking"),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a CSV")

    content = (await file.read()).decode("utf-8-sig")
    stats = parse_chase_csv(content, account_name=account)

    if "error" in stats:
        raise HTTPException(400, stats["error"])

    return stats


# ─── Budgets ──────────────────────────────────────────────

@app.get("/api/budgets")
def list_budgets(month: str = Query(default=None)):
    if not month:
        month = datetime.now().strftime("%Y-%m")

    budgets = db.get_budgets(month)
    summary = db.get_monthly_summary(month)
    planned_payments = db.get_planned_payments(month)
    accounts = db.get_accounts()

    budgeted_cats = {b["category"] for b in budgets}
    unbudgeted = [
        {"category": cat, "actual": amt}
        for cat, amt in summary["by_category"].items()
        if cat not in budgeted_cats and cat not in ("Transfer", "Income") and amt > 0
    ]

    total_available = sum(a.get("balance_available") or 0 for a in accounts if a.get("balance_available") is not None)

    return {
        "month": month,
        "income": summary["income"],
        "balance": total_available,
        "planned_payments": planned_payments,
        "budgets": [
            {
                **b,
                "actual": summary["by_category"].get(b["category"], 0),
            }
            for b in budgets
        ],
        "unbudgeted": sorted(unbudgeted, key=lambda x: x["actual"], reverse=True),
    }


class BudgetUpsert(BaseModel):
    category: str
    planned: float
    color: str = "#2563eb"


@app.put("/api/budgets/{month}")
def upsert_budget(month: str, body: BudgetUpsert):
    db.upsert_budget(month, body.category, body.planned, body.color)
    return {"ok": True}


@app.delete("/api/budgets/{budget_id}")
def delete_budget(budget_id: int):
    db.delete_budget(budget_id)
    return {"ok": True}


@app.post("/api/budgets/{month}/copy-to/{target_month}")
def copy_budgets(month: str, target_month: str):
    """Copy all budget categories from one month to another."""
    source = db.get_budgets(month)
    if not source:
        raise HTTPException(400, f"No budgets found for {month}")
    count = 0
    for b in source:
        db.upsert_budget(target_month, b["category"], b["planned"], b["color"])
        count += 1
    return {"copied": count}


@app.post("/api/budgets/{month}/auto-populate")
def auto_populate_budgets(month: str, months_back: int = Query(default=3)):
    """Auto-create budgets based on average spending per category over the last N months."""
    averages = db.get_category_averages(months_back)
    count = 0
    for cat, avg in averages.items():
        if cat in ("Transfer", "Income"):
            continue
        # Round up to nearest $5 for cleaner numbers
        planned = (int(avg / 5) + 1) * 5
        db.upsert_budget(month, cat, float(planned))
        count += 1
    return {"created": count, "categories": averages}


class PlannedPaymentCreate(BaseModel):
    name: str
    category: str = "Upcoming"
    amount: float
    due_date: str
    notes: str | None = None


class PlannedPaymentUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    amount: float | None = None
    due_date: str | None = None
    notes: str | None = None
    paid: bool | None = None


@app.get("/api/planned-payments")
def list_planned_payments(month: str = Query(default=None), include_paid: bool = False):
    return db.get_planned_payments(month=month, include_paid=include_paid)


@app.post("/api/planned-payments")
def create_planned_payment(body: PlannedPaymentCreate):
    if not body.name.strip():
        raise HTTPException(400, "Name is required")
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be greater than 0")
    try:
        datetime.strptime(body.due_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Due date must use YYYY-MM-DD")

    payment_id = db.add_planned_payment(
        body.name.strip(),
        body.category.strip() or "Upcoming",
        body.amount,
        body.due_date,
        body.notes,
    )
    return {"id": payment_id}


@app.patch("/api/planned-payments/{payment_id}")
def update_planned_payment(payment_id: int, body: PlannedPaymentUpdate):
    updates = body.model_dump(exclude_none=True)
    if "paid" in updates:
        updates["paid"] = 1 if updates["paid"] else 0
    if "due_date" in updates:
        try:
            datetime.strptime(updates["due_date"], "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Due date must use YYYY-MM-DD")
    if "amount" in updates and updates["amount"] <= 0:
        raise HTTPException(400, "Amount must be greater than 0")
    if not updates:
        raise HTTPException(400, "No fields to update")
    db.update_planned_payment(payment_id, updates)
    return {"ok": True}


@app.delete("/api/planned-payments/{payment_id}")
def delete_planned_payment(payment_id: int):
    db.delete_planned_payment(payment_id)
    return {"ok": True}


# ─── Rules ────────────────────────────────────────────────

@app.get("/api/rules")
def list_rules():
    return db.get_rules()


class RuleCreate(BaseModel):
    pattern: str
    category: str


@app.post("/api/rules")
def create_rule(body: RuleCreate):
    rule_id = db.add_rule(body.pattern, body.category)
    return {"id": rule_id}


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    db.delete_rule(rule_id)
    return {"ok": True}


# ─── Accounts ─────────────────────────────────────────────

@app.get("/api/accounts")
def list_accounts():
    return db.get_accounts()


# ─── Cash Flow / Category Breakdown ───────────────────

@app.get("/api/cash-flow/categories/{month}")
def cash_flow_categories(month: str):
    """Get category breakdown for a specific month (for chart tooltips)."""
    return db.get_monthly_categories(month)


# ─── Analytics ────────────────────────────────────────

@app.get("/api/analytics/recurring")
def recurring_transactions():
    return db.detect_recurring()


@app.get("/api/analytics/anomalies")
def spending_anomalies(month: str = Query(default=None)):
    if not month:
        month = datetime.now().strftime("%Y-%m")
    return db.get_category_anomalies(month)


@app.get("/api/analytics/forecast")
def balance_forecast(month: str = Query(default=None)):
    if not month:
        month = datetime.now().strftime("%Y-%m")
    return db.predict_end_of_month(month)


@app.get("/api/analytics/smart-forecast")
def smart_forecast(months_ahead: int = Query(default=3)):
    return db.smart_forecast(months_ahead)


# ─── AI Endpoints ─────────────────────────────────────────

@app.post("/api/ai/categorize")
async def ai_categorize(month: str = Query(default=None)):
    """Auto-categorize all 'Review' transactions for the given month."""
    if not month:
        month = datetime.now().strftime("%Y-%m")

    uncategorized = db.get_transactions(month=month, status="Review")
    if not uncategorized:
        return {"categorized": 0, "results": []}

    results = await ai_engine.categorize_transactions(uncategorized)

    updated = 0
    for r in results:
        if "id" in r and "category" in r:
            db.update_transaction(r["id"], {"category": r["category"], "status": "AI tagged"})
            updated += 1

    return {"categorized": updated, "results": results}


@app.get("/api/ai/insights")
async def ai_insights(month: str = Query(default=None)):
    """Generate AI insight cards for the month."""
    if not month:
        month = datetime.now().strftime("%Y-%m")

    summary = db.get_monthly_summary(month)
    budgets = db.get_budgets(month)
    insights = await ai_engine.generate_insights(summary, budgets)
    return insights


class ChatRequest(BaseModel):
    question: str
    month: str | None = None


@app.post("/api/ai/chat")
async def ai_chat(body: ChatRequest):
    """Answer a free-form question about finances (non-streaming fallback)."""
    month = body.month or datetime.now().strftime("%Y-%m")
    summary = db.get_monthly_summary(month)
    budgets = db.get_budgets(month)
    answer = await ai_engine.chat_query(body.question, summary, budgets)
    return {"answer": answer}


@app.post("/api/ai/chat/stream")
async def ai_chat_stream(body: ChatRequest):
    """Stream a free-form answer about finances."""
    month = body.month or datetime.now().strftime("%Y-%m")
    summary = db.get_monthly_summary(month)
    budgets = db.get_budgets(month)

    async def generate():
        try:
            async for chunk in ai_engine.chat_query_stream(body.question, summary, budgets):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except (GeneratorExit, Exception):
            # Client disconnected — stream cleanup happens automatically
            return

    return StreamingResponse(generate(), media_type="text/event-stream")


class BudgetDraftRequest(BaseModel):
    prompt: str
    use_last_month: bool = False


@app.post("/api/ai/budget-draft")
async def ai_budget_draft(body: BudgetDraftRequest):
    """Generate a budget draft from a conversational prompt."""
    last_month = None
    if body.use_last_month:
        now = datetime.now()
        if now.month == 1:
            prev = f"{now.year - 1}-12"
        else:
            prev = f"{now.year}-{now.month - 1:02d}"
        last_month = db.get_monthly_summary(prev)

    draft = await ai_engine.build_budget_draft(body.prompt, last_month)
    return {"draft": draft}


# ─── Plaid ────────────────────────────────────────────────

@app.post("/api/plaid/create-link-token")
def plaid_create_link_token():
    try:
        link_token = plaid_client.create_link_token()
        return {"link_token": link_token}
    except Exception as e:
        raise HTTPException(500, f"Plaid error: {e}")


class PlaidExchange(BaseModel):
    public_token: str


@app.post("/api/plaid/exchange-token")
def plaid_exchange_token(body: PlaidExchange):
    try:
        result = plaid_client.exchange_public_token(body.public_token)
        return result
    except Exception as e:
        raise HTTPException(500, f"Plaid error: {e}")


@app.post("/api/plaid/sync")
def plaid_sync():
    try:
        stats = plaid_client.sync_transactions()
        if "error" in stats:
            raise HTTPException(400, stats["error"])
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Plaid sync error: {e}")


@app.get("/api/plaid/status")
def plaid_status():
    return plaid_client.get_plaid_status()


# ─── Entry point ──────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
