"""Chase CSV import and deduplication."""

import csv
import hashlib
import io
from datetime import datetime

from database import get_account_by_name, insert_transaction, apply_rules


def parse_chase_csv(file_content: str, account_name: str = "Chase Checking") -> dict:
    """Parse a Chase CSV export and return import stats.

    Chase CSVs typically have columns:
      Transaction Date, Post Date, Description, Category, Type, Amount, Memo
    or the credit card format:
      Transaction Date, Post Date, Description, Category, Type, Amount
    """
    reader = csv.DictReader(io.StringIO(file_content))

    account = get_account_by_name(account_name)
    if not account:
        return {"error": f"Account '{account_name}' not found"}

    stats = {"total": 0, "imported": 0, "duplicates": 0, "need_review": 0}
    imported_rows = []

    for row in reader:
        stats["total"] += 1

        # Chase uses different column names across card types
        date_raw = row.get("Transaction Date") or row.get("Date", "")
        description = row.get("Description", "").strip()
        amount_str = row.get("Amount", "0").replace(",", "")

        if not date_raw or not description:
            continue

        # Parse date — Chase uses MM/DD/YYYY
        try:
            date_obj = datetime.strptime(date_raw.strip(), "%m/%d/%Y")
            date_iso = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue

        try:
            amount = float(amount_str)
        except ValueError:
            continue

        # Build a dedup hash: date + amount + description + account
        hash_input = f"{date_iso}|{amount}|{description}|{account_name}"
        tx_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        # Derive merchant from description (strip trailing location/ID info)
        merchant = _clean_merchant(description)

        # Apply rules for auto-categorization
        category = apply_rules(merchant)
        status = "Rule" if category else "Review"
        if not category:
            stats["need_review"] += 1
            category = _guess_category_from_chase(row)

        tx = {
            "date": date_iso,
            "merchant": merchant,
            "original_desc": description,
            "amount": amount,
            "category": category,
            "account_id": account["id"],
            "status": status,
            "source": "csv",
            "hash": tx_hash,
        }

        try:
            insert_transaction(tx)
            stats["imported"] += 1
            imported_rows.append(tx)
        except Exception:
            # Duplicate hash — already imported
            stats["duplicates"] += 1

    return stats


def _clean_merchant(description: str) -> str:
    """Extract a readable merchant name from Chase description."""
    # Remove common suffixes like store numbers, locations, dates
    merchant = description.split("#")[0].strip()
    merchant = merchant.split("  ")[0].strip()
    # Remove trailing digits that look like store IDs
    parts = merchant.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) >= 3:
        merchant = parts[0]
    return merchant


def _guess_category_from_chase(row: dict) -> str:
    """Use Chase's own category column as a fallback hint."""
    chase_cat = row.get("Category", "").strip()
    mapping = {
        "Food & Drink": "Dining",
        "Groceries": "Groceries",
        "Gas": "Gas",
        "Shopping": "Shopping",
        "Entertainment": "Entertainment",
        "Bills & Utilities": "Subscriptions",
        "Health & Wellness": "Health",
        "Travel": "Travel",
        "Automotive": "Gas",
        "Personal": "Personal",
    }
    return mapping.get(chase_cat, chase_cat or "Uncategorized")
