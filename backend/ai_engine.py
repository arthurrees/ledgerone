"""Local AI engine using Ollama for categorization and insights."""

import json
from collections.abc import AsyncGenerator

import httpx

OLLAMA_URL = "http://localhost:11434"
# Standardized on Arthur's GPU-optimized model (qwen3.5-gpu: num_gpu 99 + num_ctx 24576
# baked in, loads 100% on the RTX 3070, no CPU spill, shared resident instance across apps).
MODEL_HEAVY = "qwen3.5-gpu"     # structured JSON tasks (categorize, budget draft)
MODEL_FAST = "qwen3.5-gpu"      # conversational tasks (insights, chat)


async def _chat(system: str, user: str, temperature: float = 0.3, model: str = MODEL_HEAVY) -> str:
    """Send a non-streaming chat request to Ollama."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _chat_stream(system: str, user: str, temperature: float = 0.3, model: str = MODEL_FAST) -> AsyncGenerator[str, None]:
    """Send a streaming chat request to Ollama, yielding content chunks.

    Cancellation-safe: if the caller stops iterating (client disconnect),
    the httpx stream and Ollama request are cleaned up automatically.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "options": {"temperature": temperature},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            try:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
            except (GeneratorExit, Exception):
                # Client disconnected or stream cancelled — close the response
                await resp.aclose()
                raise


def _strip_fences(raw: str) -> str:
    """Strip markdown code fences from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    return raw.strip()


async def categorize_transactions(transactions: list[dict]) -> list[dict]:
    """Ask AI to categorize transactions. Uses heavy model for accurate JSON."""
    if not transactions:
        return []

    tx_lines = "\n".join(
        f"- ID {t['id']}: {t['merchant']} | ${abs(t['amount']):.2f} | {t['original_desc']}"
        for t in transactions
    )

    system = """You are a personal finance categorizer. Classify each transaction into exactly one category.
Valid categories: Groceries, Dining, Gas, Subscriptions, Shopping, Entertainment, Health, Travel, Transfer, Income, Personal, Utilities, Transportation, Tuition, Uncategorized.

Respond with ONLY a JSON array. Each element: {"id": <number>, "category": "<category>"}
No explanation, no markdown, just the JSON array."""

    user = f"Categorize these transactions:\n{tx_lines}"

    raw = await _chat(system, user, temperature=0.1, model=MODEL_HEAVY)
    raw = _strip_fences(raw)

    try:
        results = json.loads(raw)
        return results if isinstance(results, list) else []
    except json.JSONDecodeError:
        return []


async def generate_insights(summary: dict, budgets: list[dict]) -> list[dict]:
    """Generate spending insight cards. Uses fast model."""
    budget_lines = "\n".join(
        f"- {b['category']}: planned ${b['planned']}, actual ${summary['by_category'].get(b['category'], 0):.2f}"
        for b in budgets
    )

    system = """You are a concise personal finance advisor. Given the user's monthly summary, generate 2-4 actionable insight cards.

Respond with ONLY a JSON array. Each element: {"title": "<short title>", "body": "<1-2 sentence insight>", "action": "<short button label>"}
No explanation, no markdown, just the JSON array."""

    user = f"""Monthly summary:
- Income: ${summary['income']:.2f}
- Spending: ${summary['spending']:.2f}
- Surplus: ${summary['income'] - summary['spending']:.2f}

Budget vs actual:
{budget_lines}"""

    raw = await _chat(system, user, temperature=0.4, model=MODEL_FAST)
    raw = _strip_fences(raw)

    try:
        results = json.loads(raw)
        return results if isinstance(results, list) else []
    except json.JSONDecodeError:
        return []


async def chat_query_stream(question: str, summary: dict, budgets: list[dict]) -> AsyncGenerator[str, None]:
    """Stream a free-form answer about finances. Uses fast model."""
    budget_lines = "\n".join(
        f"- {b['category']}: planned ${b['planned']}, actual ${summary['by_category'].get(b['category'], 0):.2f}"
        for b in budgets
    )

    system = """You are a helpful personal finance assistant. The user will ask about their spending.
Answer concisely using the provided data. Be specific with numbers. If you can't answer from the data, say so.
Keep responses under 3 sentences."""

    user = f"""My financial data this month:
- Income: ${summary['income']:.2f}
- Spending: ${summary['spending']:.2f}
- Surplus: ${summary['income'] - summary['spending']:.2f}

Budget breakdown:
{budget_lines}

Question: {question}"""

    async for chunk in _chat_stream(system, user, temperature=0.5, model=MODEL_FAST):
        yield chunk


async def chat_query(question: str, summary: dict, budgets: list[dict]) -> str:
    """Non-streaming fallback for chat."""
    budget_lines = "\n".join(
        f"- {b['category']}: planned ${b['planned']}, actual ${summary['by_category'].get(b['category'], 0):.2f}"
        for b in budgets
    )

    system = """You are a helpful personal finance assistant. The user will ask about their spending.
Answer concisely using the provided data. Be specific with numbers. If you can't answer from the data, say so.
Keep responses under 3 sentences."""

    user = f"""My financial data this month:
- Income: ${summary['income']:.2f}
- Spending: ${summary['spending']:.2f}
- Surplus: ${summary['income'] - summary['spending']:.2f}

Budget breakdown:
{budget_lines}

Question: {question}"""

    return await _chat(system, user, temperature=0.5, model=MODEL_FAST)


async def build_budget_draft(prompt: str, last_month_summary: dict | None = None) -> list[dict]:
    """Generate a budget draft. Uses heavy model for accurate JSON."""
    context = ""
    if last_month_summary:
        context = f"\nLast month's actuals:\n- Income: ${last_month_summary['income']:.2f}\n- Spending: ${last_month_summary['spending']:.2f}\n"
        for cat, amt in last_month_summary.get("by_category", {}).items():
            context += f"- {cat}: ${amt:.2f}\n"

    system = """You are a budget planner. Given the user's goals, suggest monthly budget categories and amounts.

Respond with ONLY a JSON array. Each element: {"category": "<name>", "planned": <number>, "color": "<hex>"}
Use these colors: Groceries=#2563eb, Dining=#c2410c, Gas=#16803c, Subscriptions=#7c3aed, Shopping=#b7791f, Entertainment=#0891b2, Health=#be185d, Travel=#4f46e5, Utilities=#737373, Personal=#a3a3a3, Tuition=#dc2626, Transportation=#0d9488
No explanation, no markdown, just the JSON array."""

    user = f"Plan my budget: {prompt}{context}"

    raw = await _chat(system, user, temperature=0.4, model=MODEL_HEAVY)
    raw = _strip_fences(raw)

    try:
        results = json.loads(raw)
        return results if isinstance(results, list) else []
    except json.JSONDecodeError:
        return []
