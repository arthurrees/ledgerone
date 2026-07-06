"""SQLite database layer for LedgerOne."""

import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "ledgerone.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                type        TEXT NOT NULL DEFAULT 'checking',
                institution TEXT NOT NULL DEFAULT 'Chase',
                plaid_id    TEXT,
                balance_current   REAL,
                balance_available REAL,
                balance_updated   TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                merchant        TEXT NOT NULL,
                original_desc   TEXT NOT NULL,
                amount          REAL NOT NULL,
                category        TEXT,
                account_id      INTEGER NOT NULL REFERENCES accounts(id),
                status          TEXT NOT NULL DEFAULT 'Review',
                source          TEXT NOT NULL DEFAULT 'csv',
                plaid_tx_id     TEXT UNIQUE,
                hash            TEXT UNIQUE,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS budgets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                month       TEXT NOT NULL,
                category    TEXT NOT NULL,
                planned     REAL NOT NULL DEFAULT 0,
                color       TEXT NOT NULL DEFAULT '#2563eb',
                UNIQUE(month, category)
            );

            CREATE TABLE IF NOT EXISTS planned_payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'Upcoming',
                amount      REAL NOT NULL DEFAULT 0,
                due_date    TEXT NOT NULL,
                notes       TEXT,
                paid        INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern     TEXT NOT NULL UNIQUE,
                category    TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
            CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
            CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id);
            CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(hash);
            CREATE INDEX IF NOT EXISTS idx_planned_due_date ON planned_payments(due_date);
        """)

        # No seeded accounts or rules — Plaid creates accounts on link,
        # and rules are added by the user or during transaction sync.


# --------------- Query helpers ---------------

def get_accounts() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def get_account_by_name(name: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def get_transactions(
    month: str | None = None,
    category: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[dict]:
    query = "SELECT t.*, a.name as account FROM transactions t JOIN accounts a ON t.account_id = a.id WHERE 1=1"
    params: list = []

    if month:
        query += " AND t.date LIKE ?"
        params.append(f"{month}%")
    if category:
        query += " AND t.category = ?"
        params.append(category)
    if status:
        query += " AND t.status = ?"
        params.append(status)
    if search:
        query += " AND (t.merchant LIKE ? OR t.category LIKE ? OR t.original_desc LIKE ?)"
        params.extend([f"%{search}%"] * 3)

    query += " ORDER BY t.date DESC, t.id DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def insert_transaction(tx: dict) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO transactions (date, merchant, original_desc, amount, category, account_id, status, source, hash)
               VALUES (:date, :merchant, :original_desc, :amount, :category, :account_id, :status, :source, :hash)""",
            tx,
        )
        return cur.lastrowid


def update_transaction(tx_id: int, updates: dict):
    allowed = {"category", "status", "merchant"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [tx_id]
    with get_db() as conn:
        conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ?", values)


def get_budgets(month: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM budgets WHERE month = ? ORDER BY category", (month,)
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_budget(month: str, category: str, planned: float, color: str = "#2563eb"):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO budgets (month, category, planned, color)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(month, category) DO UPDATE SET planned = excluded.planned, color = excluded.color""",
            (month, category, planned, color),
        )


def delete_budget(budget_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))


def get_planned_payments(month: str | None = None, include_paid: bool = False) -> list[dict]:
    query = "SELECT * FROM planned_payments WHERE 1=1"
    params: list = []

    if month:
        query += " AND due_date LIKE ?"
        params.append(f"{month}%")
    if not include_paid:
        query += " AND paid = 0"

    query += " ORDER BY due_date ASC, id ASC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def add_planned_payment(name: str, category: str, amount: float, due_date: str, notes: str | None = None) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO planned_payments (name, category, amount, due_date, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (name, category or "Upcoming", amount, due_date, notes),
        )
        return cur.lastrowid


def update_planned_payment(payment_id: int, updates: dict):
    allowed = {"name", "category", "amount", "due_date", "notes", "paid"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [payment_id]
    with get_db() as conn:
        conn.execute(f"UPDATE planned_payments SET {set_clause} WHERE id = ?", values)


def delete_planned_payment(payment_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM planned_payments WHERE id = ?", (payment_id,))


def get_rules() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM rules ORDER BY pattern").fetchall()
        return [dict(r) for r in rows]


def add_rule(pattern: str, category: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT OR REPLACE INTO rules (pattern, category) VALUES (?, ?)",
            (pattern, category),
        )
        return cur.lastrowid


def delete_rule(rule_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))


def apply_rules(tx_merchant: str) -> str | None:
    """Return the category for the first matching rule, or None."""
    with get_db() as conn:
        rules = conn.execute("SELECT pattern, category FROM rules").fetchall()
        merchant_lower = tx_merchant.lower()
        for rule in rules:
            if rule["pattern"].lower() in merchant_lower:
                return rule["category"]
    return None


def get_range_summary(start_date: str, end_date: str) -> dict:
    """Compute income, spending, and category actuals for a date range."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spending
               FROM transactions
               WHERE date >= ? AND date <= ?""",
            (start_date, end_date),
        ).fetchone()

        category_actuals = conn.execute(
            """SELECT category, COALESCE(SUM(ABS(amount)), 0) as actual
               FROM transactions
               WHERE date >= ? AND date <= ? AND amount < 0 AND category != 'Transfer'
               GROUP BY category""",
            (start_date, end_date),
        ).fetchall()

        return {
            "income": row["income"],
            "spending": row["spending"],
            "by_category": {r["category"]: r["actual"] for r in category_actuals},
        }


def get_monthly_summary(month: str) -> dict:
    """Compute income, spending, and budget actuals for a month."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spending
               FROM transactions
               WHERE date LIKE ?""",
            (f"{month}%",),
        ).fetchone()

        category_actuals = conn.execute(
            """SELECT category, COALESCE(SUM(ABS(amount)), 0) as actual
               FROM transactions
               WHERE date LIKE ? AND amount < 0 AND category != 'Transfer'
               GROUP BY category""",
            (f"{month}%",),
        ).fetchall()

        return {
            "income": row["income"],
            "spending": row["spending"],
            "by_category": {r["category"]: r["actual"] for r in category_actuals},
        }


def get_cash_flow(months: int = 6) -> list[dict]:
    """Get income and spending totals per month for the last N months (0 = all)."""
    with get_db() as conn:
        query = """SELECT
                strftime('%Y-%m', date) as month,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spending
               FROM transactions
               GROUP BY strftime('%Y-%m', date)
               ORDER BY month DESC"""
        if months > 0:
            query += " LIMIT ?"
            rows = conn.execute(query, (months,)).fetchall()
        else:
            rows = conn.execute(query).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_category_averages(months_back: int = 3) -> dict[str, float]:
    """Get average spending per category over the last N months."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT category, AVG(monthly_total) as avg_spending
               FROM (
                   SELECT category, strftime('%Y-%m', date) as month,
                          SUM(ABS(amount)) as monthly_total
                   FROM transactions
                   WHERE amount < 0
                   GROUP BY category, month
                   ORDER BY month DESC
               )
               GROUP BY category
               HAVING COUNT(*) > 0""",
        ).fetchall()
        return {r["category"]: round(r["avg_spending"], 2) for r in rows}


def detect_recurring(min_months: int = 2) -> list[dict]:
    """Detect recurring transactions by merchant pattern across months."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT merchant,
                COUNT(DISTINCT strftime('%Y-%m', date)) as month_count,
                AVG(ABS(amount)) as avg_amount,
                MIN(ABS(amount)) as min_amount,
                MAX(ABS(amount)) as max_amount,
                MAX(date) as last_seen,
                category
               FROM transactions
               WHERE amount < 0
               GROUP BY LOWER(merchant)
               HAVING COUNT(DISTINCT strftime('%Y-%m', date)) >= ?
               ORDER BY month_count DESC, avg_amount DESC""",
            (min_months,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_category_anomalies(month: str, threshold: float = 1.5) -> list[dict]:
    """Find categories where spending is significantly above average."""
    with get_db() as conn:
        # Get current month spending by category
        current = conn.execute(
            """SELECT category, SUM(ABS(amount)) as current_total
               FROM transactions
               WHERE date LIKE ? AND amount < 0 AND category NOT IN ('Transfer', 'Income')
               GROUP BY category""",
            (f"{month}%",),
        ).fetchall()

        # Get historical averages (all months except current)
        averages = conn.execute(
            """SELECT category, AVG(monthly_total) as avg_total
               FROM (
                   SELECT category, strftime('%Y-%m', date) as m, SUM(ABS(amount)) as monthly_total
                   FROM transactions
                   WHERE amount < 0 AND category NOT IN ('Transfer', 'Income')
                     AND strftime('%Y-%m', date) != ?
                   GROUP BY category, m
               )
               GROUP BY category""",
            (month,),
        ).fetchall()

        avg_map = {r["category"]: r["avg_total"] for r in averages}
        anomalies = []
        for row in current:
            cat = row["category"]
            curr = row["current_total"]
            avg = avg_map.get(cat)
            if avg and avg > 0 and curr > avg * threshold:
                anomalies.append({
                    "category": cat,
                    "current": round(curr, 2),
                    "average": round(avg, 2),
                    "delta": round(curr - avg, 2),
                    "pct_over": round(((curr - avg) / avg) * 100, 1),
                })
        return sorted(anomalies, key=lambda x: x["delta"], reverse=True)


def predict_end_of_month(month: str) -> dict:
    """Predict end-of-month balance based on current spending pace."""
    import calendar
    year, mon = map(int, month.split('-'))
    days_in_month = calendar.monthrange(year, mon)[1]
    today = datetime.now()
    days_elapsed = min(today.day, days_in_month)

    with get_db() as conn:
        row = conn.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spending
               FROM transactions WHERE date LIKE ?""",
            (f"{month}%",),
        ).fetchone()

        # Get current balance
        balance_row = conn.execute(
            "SELECT COALESCE(SUM(balance_available), 0) as bal FROM accounts WHERE balance_available IS NOT NULL"
        ).fetchone()

    income = row["income"]
    spending = row["spending"]
    balance = balance_row["bal"]

    if days_elapsed > 0:
        daily_spend_rate = spending / days_elapsed
        remaining_days = days_in_month - days_elapsed
        projected_additional = daily_spend_rate * remaining_days
    else:
        daily_spend_rate = 0
        projected_additional = 0

    return {
        "current_balance": round(balance, 2),
        "days_elapsed": days_elapsed,
        "days_remaining": days_in_month - days_elapsed,
        "daily_spend_rate": round(daily_spend_rate, 2),
        "projected_additional_spending": round(projected_additional, 2),
        "projected_end_balance": round(balance - projected_additional, 2),
    }


def smart_forecast(months_ahead: int = 3) -> dict:
    """Forecast future income/spending based on historical monthly patterns.

    Analyzes per-category monthly averages and trends, then projects forward.
    """
    with get_db() as conn:
        # Get all months with data
        months_data = conn.execute(
            """SELECT strftime('%Y-%m', date) as month,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spending
               FROM transactions
               GROUP BY month
               ORDER BY month"""
        ).fetchall()

        if not months_data:
            return {"historical": [], "forecast": [], "by_category": []}

        # Per-category monthly breakdown
        cat_data = conn.execute(
            """SELECT strftime('%Y-%m', date) as month, category,
                COALESCE(SUM(ABS(amount)), 0) as total
               FROM transactions
               WHERE amount < 0 AND category NOT IN ('Transfer')
               GROUP BY month, category
               ORDER BY month"""
        ).fetchall()

        # Build category averages
        cat_months = {}
        for row in cat_data:
            cat = row["category"]
            if cat not in cat_months:
                cat_months[cat] = []
            cat_months[cat].append({"month": row["month"], "total": row["total"]})

        # Income patterns
        income_data = conn.execute(
            """SELECT strftime('%Y-%m', date) as month,
                COALESCE(SUM(amount), 0) as total
               FROM transactions
               WHERE amount > 0 AND category NOT IN ('Transfer')
               GROUP BY month
               ORDER BY month"""
        ).fetchall()

    # Calculate averages and trends
    historical = [dict(r) for r in months_data]

    # Simple average for projection
    avg_income = sum(r["income"] for r in months_data) / len(months_data) if months_data else 0
    avg_spending = sum(r["spending"] for r in months_data) / len(months_data) if months_data else 0

    # Use last 3 months weighted average (more recent = more weight)
    recent = months_data[-3:] if len(months_data) >= 3 else months_data
    weights = [1, 2, 3][-len(recent):]
    total_weight = sum(weights)
    weighted_income = sum(r["income"] * w for r, w in zip(recent, weights)) / total_weight
    weighted_spending = sum(r["spending"] * w for r, w in zip(recent, weights)) / total_weight

    # Generate forecast months
    last_month = months_data[-1]["month"]
    year, mon = map(int, last_month.split('-'))
    forecast_months = []
    for i in range(1, months_ahead + 1):
        m = mon + i
        y = year
        while m > 12:
            m -= 12
            y += 1
        forecast_month = f"{y}-{m:02d}"
        forecast_months.append({
            "month": forecast_month,
            "projected_income": round(weighted_income, 2),
            "projected_spending": round(weighted_spending, 2),
            "projected_net": round(weighted_income - weighted_spending, 2),
        })

    # Per-category forecasts
    category_forecasts = []
    for cat, entries in cat_months.items():
        totals = [e["total"] for e in entries]
        avg = sum(totals) / len(totals)
        # Weighted average of last 3
        recent_totals = totals[-3:] if len(totals) >= 3 else totals
        w = [1, 2, 3][-len(recent_totals):]
        tw = sum(w)
        weighted = sum(t * wt for t, wt in zip(recent_totals, w)) / tw

        trend = "stable"
        if len(totals) >= 2:
            if totals[-1] > avg * 1.2:
                trend = "rising"
            elif totals[-1] < avg * 0.8:
                trend = "falling"

        category_forecasts.append({
            "category": cat,
            "avg_monthly": round(avg, 2),
            "projected": round(weighted, 2),
            "trend": trend,
            "months_seen": len(entries),
        })

    category_forecasts.sort(key=lambda x: x["projected"], reverse=True)

    return {
        "historical": historical,
        "forecast": forecast_months,
        "by_category": category_forecasts,
        "summary": {
            "avg_income": round(avg_income, 2),
            "avg_spending": round(avg_spending, 2),
            "weighted_income": round(weighted_income, 2),
            "weighted_spending": round(weighted_spending, 2),
        },
    }


def get_monthly_categories(month: str) -> list[dict]:
    """Get spending breakdown by category for a specific month."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT category,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spending,
                COUNT(*) as count
               FROM transactions
               WHERE date LIKE ?
               GROUP BY category
               ORDER BY spending DESC""",
            (f"{month}%",),
        ).fetchall()
        return [dict(r) for r in rows]
