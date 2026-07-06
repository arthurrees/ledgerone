"""LedgerOne Telegram bot — check balance, spending, forecast, ask AI from your phone."""

import asyncio
import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

import database as db
import ai_engine

logger = logging.getLogger("ledgerone.telegram")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Store authorized chat IDs (first user to /start becomes the owner)
_owner_chat_id: int | None = None
_app: Application | None = None


def _current_month() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m")


def _fmt(n: float) -> str:
    return f"${abs(n):,.2f}"


# ─── Commands ────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global _owner_chat_id
    if _owner_chat_id is None:
        _owner_chat_id = update.effective_chat.id
        _save_chat_id(_owner_chat_id)
        logger.info(f"Telegram owner set: chat_id={_owner_chat_id}")

    await update.message.reply_text(
        "🏦 *LedgerOne Bot*\n\n"
        "Commands:\n"
        "/balance — Current bank balance\n"
        "/spending — This month's spending breakdown\n"
        "/forecast — End-of-month balance prediction\n"
        "/recurring — Detected recurring charges\n"
        "/sync — Trigger a Plaid sync now\n"
        "/ask <question> — Ask AI about your finances\n\n"
        "Or just type a question and I'll answer it.",
        parse_mode="Markdown",
    )


async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    accounts = db.get_accounts()
    if not accounts:
        await update.message.reply_text("No accounts linked.")
        return

    lines = []
    total = 0
    for a in accounts:
        bal = a.get("balance_available") or a.get("balance_current")
        if bal is not None:
            lines.append(f"• {a['name']}: *{_fmt(bal)}*")
            total += bal

    if len(accounts) > 1:
        lines.append(f"\n*Total: {_fmt(total)}*")

    await update.message.reply_text(
        "💰 *Account Balances*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def cmd_spending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    month = _current_month()
    summary = db.get_monthly_summary(month)

    lines = [
        f"📊 *Spending — {month}*\n",
        f"Income: *{_fmt(summary['income'])}*",
        f"Spending: *{_fmt(summary['spending'])}*",
        f"Net: *{_fmt(summary['income'] - summary['spending'])}*\n",
        "*By category:*",
    ]

    cats = sorted(summary["by_category"].items(), key=lambda x: x[1], reverse=True)
    for cat, amt in cats:
        if amt > 0:
            lines.append(f"  {cat}: {_fmt(amt)}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_forecast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    month = _current_month()
    f = db.predict_end_of_month(month)

    emoji = "✅" if f["projected_end_balance"] >= 0 else "⚠️"
    await update.message.reply_text(
        f"🔮 *Forecast — {month}*\n\n"
        f"Current balance: *{_fmt(f['current_balance'])}*\n"
        f"Daily spend rate: *{_fmt(f['daily_spend_rate'])}/day*\n"
        f"Days remaining: *{f['days_remaining']}*\n"
        f"Projected spending: *{_fmt(f['projected_additional_spending'])}*\n\n"
        f"{emoji} Projected end balance: *{_fmt(f['projected_end_balance'])}*",
        parse_mode="Markdown",
    )


async def cmd_recurring(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    recurring = db.detect_recurring()
    if not recurring:
        await update.message.reply_text("No recurring transactions detected yet.")
        return

    lines = ["🔄 *Recurring Charges*\n"]
    for r in recurring[:10]:
        lines.append(
            f"• *{r['merchant']}* — {_fmt(r['avg_amount'])}/mo "
            f"({r['month_count']} months, {r['category']})"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await update.message.reply_text("⏳ Syncing with Plaid...")

    try:
        import plaid_client
        stats = plaid_client.sync_transactions()
        if "error" in stats:
            await update.message.reply_text(f"❌ Sync error: {stats['error']}")
        else:
            await update.message.reply_text(
                f"✅ *Sync complete*\n\n"
                f"Added: {stats['added']}\n"
                f"Modified: {stats['modified']}\n"
                f"Removed: {stats['removed']}",
                parse_mode="Markdown",
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Sync failed: {e}")


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    question = " ".join(ctx.args) if ctx.args else ""
    if not question:
        await update.message.reply_text("Usage: /ask <your question>\nExample: /ask Can I afford a $200 purchase?")
        return

    await _handle_question(update, question)


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages as AI questions."""
    if not _is_owner(update):
        return
    if not update.message or not update.message.text:
        return

    await _handle_question(update, update.message.text)


async def _handle_question(update: Update, question: str):
    """Ask AI and send the response."""
    month = _current_month()
    summary = db.get_monthly_summary(month)
    budgets = db.get_budgets(month)

    thinking_msg = await update.message.reply_text("🤔 Thinking...")

    try:
        answer = await ai_engine.chat_query(question, summary, budgets)
        await thinking_msg.edit_text(f"🤖 {answer}")
    except Exception as e:
        await thinking_msg.edit_text(f"❌ AI error: {e}")


# ─── Notifications (called from server.py) ───────────────

async def send_notification(text: str):
    """Send a push notification to the bot owner."""
    if not _app or not _owner_chat_id:
        return
    try:
        await _app.bot.send_message(
            chat_id=_owner_chat_id,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Failed to send Telegram notification: {e}")


def send_notification_sync(text: str):
    """Sync wrapper for sending notifications from non-async code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(send_notification(text))
        else:
            loop.run_until_complete(send_notification(text))
    except RuntimeError:
        # No event loop — create one
        asyncio.run(send_notification(text))


# ─── Auth helpers ────────────────────────────────────────

def _is_owner(update: Update) -> bool:
    """Only the first user to /start can use the bot."""
    if _owner_chat_id is None:
        return True  # not set yet, will be set on /start
    return update.effective_chat.id == _owner_chat_id


def _save_chat_id(chat_id: int):
    """Persist chat ID in the database."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("telegram_chat_id", str(chat_id)),
        )


def _load_chat_id():
    """Load persisted chat ID from database."""
    global _owner_chat_id
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'telegram_chat_id'"
        ).fetchone()
        if row:
            _owner_chat_id = int(row["value"])
            logger.info(f"Loaded Telegram chat_id: {_owner_chat_id}")


# ─── Bot lifecycle ───────────────────────────────────────

async def start_bot():
    """Initialize and start the Telegram bot (called from server.py lifespan)."""
    global _app

    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return

    _load_chat_id()

    _app = Application.builder().token(BOT_TOKEN).build()

    _app.add_handler(CommandHandler("start", cmd_start))
    _app.add_handler(CommandHandler("balance", cmd_balance))
    _app.add_handler(CommandHandler("spending", cmd_spending))
    _app.add_handler(CommandHandler("forecast", cmd_forecast))
    _app.add_handler(CommandHandler("recurring", cmd_recurring))
    _app.add_handler(CommandHandler("sync", cmd_sync))
    _app.add_handler(CommandHandler("ask", cmd_ask))
    _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    try:
        await _app.initialize()
        await _app.start()
        await _app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started")
    except Exception as e:
        logger.error(f"Telegram bot failed to start: {e}")
        _app = None


async def stop_bot():
    """Gracefully stop the Telegram bot."""
    global _app
    if _app:
        try:
            await _app.updater.stop()
            await _app.stop()
            await _app.shutdown()
        except Exception as e:
            logger.warning(f"Error stopping Telegram bot: {e}")
        _app = None
        logger.info("Telegram bot stopped")
