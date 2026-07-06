const BASE = '';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export function fetchDashboard(month, range = 'month') {
  const params = new URLSearchParams();
  if (month) params.set('month', month);
  if (range) params.set('range', range);
  const q = params.toString();
  return request(`/api/dashboard${q ? '?' + q : ''}`);
}

export function fetchTransactions({ month, category, status, search, limit } = {}) {
  const params = new URLSearchParams();
  if (month) params.set('month', month);
  if (category) params.set('category', category);
  if (status) params.set('status', status);
  if (search) params.set('search', search);
  if (limit) params.set('limit', limit);
  const q = params.toString();
  return request(`/api/transactions${q ? '?' + q : ''}`);
}

export function updateTransaction(id, updates) {
  return request(`/api/transactions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export function importCSV(file, account = 'Chase Checking') {
  const form = new FormData();
  form.append('file', file);
  form.append('account', account);
  return request('/api/import/csv', { method: 'POST', body: form });
}

export function fetchBudgets(month) {
  const q = month ? `?month=${month}` : '';
  return request(`/api/budgets${q}`);
}

export function upsertBudget(month, category, planned, color = '#2563eb') {
  return request(`/api/budgets/${month}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, planned, color }),
  });
}

export function deleteBudget(id) {
  return request(`/api/budgets/${id}`, { method: 'DELETE' });
}

export function copyBudgets(fromMonth, toMonth) {
  return request(`/api/budgets/${fromMonth}/copy-to/${toMonth}`, { method: 'POST' });
}

export function autoPopulateBudgets(month, monthsBack = 3) {
  return request(`/api/budgets/${month}/auto-populate?months_back=${monthsBack}`, { method: 'POST' });
}

export function fetchPlannedPayments(month, includePaid = false) {
  const params = new URLSearchParams();
  if (month) params.set('month', month);
  if (includePaid) params.set('include_paid', 'true');
  const q = params.toString();
  return request(`/api/planned-payments${q ? '?' + q : ''}`);
}

export function createPlannedPayment(payment) {
  return request('/api/planned-payments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payment),
  });
}

export function updatePlannedPayment(id, updates) {
  return request(`/api/planned-payments/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export function deletePlannedPayment(id) {
  return request(`/api/planned-payments/${id}`, { method: 'DELETE' });
}

export function fetchRules() {
  return request('/api/rules');
}

export function createRule(pattern, category) {
  return request('/api/rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern, category }),
  });
}

export function deleteRule(id) {
  return request(`/api/rules/${id}`, { method: 'DELETE' });
}

export function fetchAccounts() {
  return request('/api/accounts');
}

export function fetchRecurring() {
  return request('/api/analytics/recurring');
}

export function fetchAnomalies(month) {
  const q = month ? `?month=${month}` : '';
  return request(`/api/analytics/anomalies${q}`);
}

export function fetchForecast(month) {
  const q = month ? `?month=${month}` : '';
  return request(`/api/analytics/forecast${q}`);
}

export function fetchSmartForecast(monthsAhead = 3) {
  return request(`/api/analytics/smart-forecast?months_ahead=${monthsAhead}`);
}

export function fetchMonthCategories(month) {
  return request(`/api/cash-flow/categories/${month}`);
}

export function aiCategorize(month) {
  const q = month ? `?month=${month}` : '';
  return request(`/api/ai/categorize${q}`, { method: 'POST' });
}

export function aiInsights(month) {
  const q = month ? `?month=${month}` : '';
  return request(`/api/ai/insights${q}`);
}

export function aiChat(question, month) {
  return request('/api/ai/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, month }),
  });
}

export async function aiChatStream(question, month, onChunk, signal) {
  const res = await fetch(`${BASE}/api/ai/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, month }),
    signal,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') return;
        try {
          const data = JSON.parse(payload);
          if (data.content) onChunk(data.content);
        } catch {
          // ignore malformed SSE chunks
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

export function aiBudgetDraft(prompt, useLastMonth = false) {
  return request('/api/ai/budget-draft', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, use_last_month: useLastMonth }),
  });
}

// Plaid

export function plaidCreateLinkToken() {
  return request('/api/plaid/create-link-token', { method: 'POST' });
}

export function plaidExchangeToken(publicToken) {
  return request('/api/plaid/exchange-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ public_token: publicToken }),
  });
}

export function plaidSync() {
  return request('/api/plaid/sync', { method: 'POST' });
}

export function plaidStatus() {
  return request('/api/plaid/status');
}
