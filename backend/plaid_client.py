"""Plaid integration for LedgerOne — link accounts and sync transactions."""

import os
from datetime import datetime, timedelta

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest

import database as db

# Map Plaid environment string to host
_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def _get_client() -> plaid_api.PlaidApi:
    config = plaid.Configuration(
        host=_ENV_MAP.get(os.getenv("PLAID_ENV", "production"), plaid.Environment.Production),
        api_key={
            "clientId": os.getenv("PLAID_CLIENT_ID"),
            "secret": os.getenv("PLAID_SECRET"),
        },
    )
    api_client = plaid.ApiClient(config)
    return plaid_api.PlaidApi(api_client)


def create_link_token(user_id: str = "ledgerone-user") -> str:
    """Create a Plaid Link token for the frontend."""
    client = _get_client()

    redirect_uri = os.getenv("PLAID_REDIRECT_URI")
    kwargs = dict(
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
        client_name="LedgerOne",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en",
    )
    if redirect_uri:
        kwargs["redirect_uri"] = redirect_uri

    request = LinkTokenCreateRequest(**kwargs)

    response = client.link_token_create(request)
    return response.link_token


def exchange_public_token(public_token: str) -> dict:
    """Exchange a public token from Link for an access token. Store it in the DB."""
    client = _get_client()

    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request)

    access_token = response.access_token
    item_id = response.item_id

    # Store access token and item_id in settings table
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("plaid_access_token", access_token),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("plaid_item_id", item_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("plaid_cursor", ""),
        )

    return {"item_id": item_id}


def sync_transactions() -> dict:
    """Sync transactions using the Plaid transactions/sync endpoint.

    Uses a cursor to only fetch new/modified/removed transactions since last sync.
    Returns stats about what was synced.
    """
    client = _get_client()

    with db.get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'plaid_access_token'").fetchone()
        if not row:
            return {"error": "No Plaid account linked. Connect via Plaid Link first."}
        access_token = row["value"]

        cursor_row = conn.execute("SELECT value FROM settings WHERE key = 'plaid_cursor'").fetchone()
        cursor = cursor_row["value"] if cursor_row else ""

    added = []
    modified = []
    removed = []
    has_more = True

    while has_more:
        request = TransactionsSyncRequest(
            access_token=access_token,
            cursor=cursor or "",
        )
        response = client.transactions_sync(request)

        added.extend(response.added)
        modified.extend(response.modified)
        removed.extend(response.removed)
        has_more = response.has_more
        cursor = response.next_cursor

    # Save cursor for next sync
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("plaid_cursor", cursor),
        )

    stats = {"added": 0, "modified": 0, "removed": 0}

    # Fetch real account details from Plaid
    plaid_accounts = _fetch_plaid_accounts()

    # Update existing accounts with real names/types/balances if we got fresh data
    if plaid_accounts:
        with db.get_db() as conn:
            for plaid_id, info in plaid_accounts.items():
                conn.execute(
                    """UPDATE accounts SET name = ?, type = ?,
                       balance_current = ?, balance_available = ?,
                       balance_updated = datetime('now')
                       WHERE plaid_id = ?""",
                    (info["name"], info["type"],
                     info["balance_current"], info["balance_available"],
                     plaid_id),
                )
        _account_cache.clear()

    # Process added transactions
    for tx in added:
        account_info = plaid_accounts.get(tx.account_id, {})
        account_name = account_info.get("name") or _resolve_account_name(tx.account_id)
        account_type = account_info.get("type", "checking")

        account = db.get_account_by_name(account_name)
        if not account:
            # Create the account with real info from Plaid
            with db.get_db() as conn:
                conn.execute(
                    "INSERT INTO accounts (name, type, institution, plaid_id) VALUES (?, ?, ?, ?)",
                    (account_name, account_type, "Chase", tx.account_id),
                )
            account = db.get_account_by_name(account_name)

        raw_merchant = tx.merchant_name or tx.name or "Unknown"
        merchant = _clean_merchant_name(raw_merchant, tx.name or "")
        category = db.apply_rules(merchant) or db.apply_rules(raw_merchant)
        status = "Rule" if category else "Review"
        if not category:
            # Use Plaid's personal_finance_category if available
            if hasattr(tx, "personal_finance_category") and tx.personal_finance_category:
                category = _map_plaid_category(tx.personal_finance_category.primary)
                if category != "Uncategorized":
                    status = "Matched"
            else:
                category = "Uncategorized"

        tx_data = {
            "date": str(tx.date),
            "merchant": merchant,
            "original_desc": tx.name or merchant,
            "amount": -tx.amount,  # Plaid uses positive for debits, we use negative
            "category": category,
            "account_id": account["id"],
            "status": status,
            "source": "plaid",
            "hash": f"plaid_{tx.transaction_id}",
        }

        try:
            db.insert_transaction(tx_data)
            stats["added"] += 1
        except Exception:
            # Duplicate
            pass

    # Process modified transactions
    for tx in modified:
        with db.get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM transactions WHERE hash = ?",
                (f"plaid_{tx.transaction_id}",),
            ).fetchone()
            if existing:
                raw_merchant = tx.merchant_name or tx.name or "Unknown"
                merchant = _clean_merchant_name(raw_merchant, tx.name or "")
                conn.execute(
                    "UPDATE transactions SET amount = ?, merchant = ?, original_desc = ?, date = ? WHERE id = ?",
                    (-tx.amount, merchant, tx.name or merchant, str(tx.date), existing["id"]),
                )
                stats["modified"] += 1

    # Process removed transactions
    for tx in removed:
        with db.get_db() as conn:
            conn.execute(
                "DELETE FROM transactions WHERE hash = ?",
                (f"plaid_{tx.transaction_id}",),
            )
            stats["removed"] += 1

    # Update last sync time
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("plaid_last_sync", datetime.now().isoformat()),
        )

    return stats


# Account ID → name cache (populated during sync)
_account_cache: dict[str, str] = {}


def _fetch_plaid_accounts() -> dict[str, dict]:
    """Fetch account details from Plaid and return a mapping of account_id → info."""
    with db.get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'plaid_access_token'").fetchone()
        if not row:
            return {}

    client = _get_client()
    request = AccountsGetRequest(access_token=row["value"])
    response = client.accounts_get(request)

    result = {}
    for acct in response.accounts:
        # Build a friendly name: "Chase Checking (...1234)"
        institution = "Chase"
        subtype = str(acct.subtype) if acct.subtype else str(acct.type)
        acct_type = subtype.replace("_", " ").title()
        mask = acct.mask or acct.account_id[-4:]
        name = f"{institution} {acct_type} (...{mask})"

        balances = acct.balances
        result[acct.account_id] = {
            "name": name,
            "type": str(acct.type),  # depository, credit, loan, etc.
            "subtype": str(acct.subtype) if acct.subtype else None,
            "balance_current": balances.current,
            "balance_available": balances.available,
        }
    return result


def _resolve_account_name(plaid_account_id: str) -> str:
    """Map a Plaid account ID to a friendly name."""
    if plaid_account_id in _account_cache:
        return _account_cache[plaid_account_id]

    # Check if we already have it in DB
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT name FROM accounts WHERE plaid_id = ?", (plaid_account_id,)
        ).fetchone()
        if row:
            _account_cache[plaid_account_id] = row["name"]
            return row["name"]

    # Fallback — will be created during sync
    name = f"Chase Account ({plaid_account_id[-4:]})"
    _account_cache[plaid_account_id] = name
    return name


import re


def _clean_merchant_name(merchant: str, original_desc: str) -> str:
    """Clean up ugly Plaid merchant names into human-readable form.

    Examples:
      "PY *DEXTER CREAMERY DEXTER MI 05/04" → "Dexter Creamery"
      "MICH STATE UNIV STU ACCTS 181436833 WEB ID: 3386005984" → "Mich State Univ Stu Accts"
      "TST*LAND SHARK BAR AN East Lansing MI 04/17" → "Land Shark Bar"
    """
    name = merchant

    # Strip common prefixes (PY *, TST*, SQ *, SP *, etc.)
    name = re.sub(r'^(PY|TST|SQ|SP|DD|CKE)\s*\*\s*', '', name)

    # Strip trailing location info (CITY ST MM/DD)
    name = re.sub(r'\s+[A-Z]{2}\s+\d{2}/\d{2}$', '', name)

    # Strip trailing reference numbers (long digit sequences, WEB ID:, transaction#:, PPD ID:)
    name = re.sub(r'\s+(WEB ID|PPD ID|transaction#)\s*:?\s*\S+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+\d{6,}.*$', '', name)

    # Strip trailing city/state patterns ("EAST LANSING MI", "ANN ARBOR MI")
    name = re.sub(r'\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?\s+[A-Z]{2}\s*$', '', name)
    name = re.sub(r'\s+[A-Z ]{2,20}\s+[A-Z]{2}\s*$', '', name)

    # Title case
    name = name.strip()
    if name.isupper() or name.islower():
        name = name.title()

    # Final cleanup
    name = re.sub(r'\s+', ' ', name).strip()

    return name if name else merchant


def _map_plaid_category(primary: str) -> str:
    """Map Plaid's personal_finance_category to our categories."""
    mapping = {
        "FOOD_AND_DRINK": "Dining",
        "GROCERIES": "Groceries",
        "TRANSPORTATION": "Gas",
        "ENTERTAINMENT": "Entertainment",
        "SHOPPING": "Shopping",
        "GENERAL_MERCHANDISE": "Shopping",
        "RENT_AND_UTILITIES": "Utilities",
        "SUBSCRIPTION": "Subscriptions",
        "MEDICAL": "Health",
        "TRAVEL": "Travel",
        "TRANSFER_IN": "Transfer",
        "TRANSFER_OUT": "Transfer",
        "INCOME": "Income",
        "LOAN_PAYMENTS": "Transfer",
        "BANK_FEES": "Fees",
        "PERSONAL_CARE": "Personal",
    }
    return mapping.get(primary, "Uncategorized")


def get_plaid_status() -> dict:
    """Check if Plaid is linked and when last synced."""
    with db.get_db() as conn:
        token = conn.execute("SELECT value FROM settings WHERE key = 'plaid_access_token'").fetchone()
        last_sync = conn.execute("SELECT value FROM settings WHERE key = 'plaid_last_sync'").fetchone()

    return {
        "linked": token is not None,
        "last_sync": last_sync["value"] if last_sync else None,
    }
