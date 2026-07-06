import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import {
  ArrowDownToLine,
  Bot,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Download,
  Filter,
  Gauge,
  Landmark,
  LayoutDashboard,
  ListChecks,
  Loader2,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Tags,
  Trash2,
  Upload,
  WalletCards,
  X,
} from 'lucide-react'
import * as api from './api'
import './App.css'

const navItems = [
  { id: 'Dashboard', icon: LayoutDashboard },
  { id: 'Transactions', icon: ListChecks },
  { id: 'Budgets', icon: Gauge },
  { id: 'Insights', icon: Sparkles },
  { id: 'Accounts', icon: WalletCards },
  { id: 'Settings', icon: Settings },
]

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function fmtMonth(iso) {
  const [y, m] = iso.split('-')
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${names[parseInt(m, 10) - 1]} ${y}`
}

function shiftMonth(iso, delta) {
  const [y, m] = iso.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function fmtDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${names[d.getMonth()]} ${d.getDate()}`
}

function fmtDollars(n) {
  return '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtAmount(n) {
  return (n > 0 ? '+' : '-') + '$' + Math.abs(n).toFixed(2)
}

function buildDashboardRanges() {
  const now = new Date()
  const ranges = [{ value: 'mtd', label: 'MTD' }]

  // Last 12 months
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const label = `${names[d.getMonth()]}-${String(d.getFullYear()).slice(2)}`
    ranges.push({ value: val, label })
  }

  ranges.push({ value: 'ytd', label: 'YTD' })
  return ranges
}

function App() {
  // If returning from Plaid OAuth, go straight to Accounts view
  const isOAuthReturn = new URLSearchParams(window.location.search).has('oauth_state_id')
  const [activeView, setActiveView] = useState(isOAuthReturn ? 'Accounts' : 'Dashboard')
  const [importOpen, setImportOpen] = useState(false)
  const [connected, setConnected] = useState(false)
  const [month, setMonth] = useState(currentMonth)
  const [refreshKey, setRefreshKey] = useState(0)
  const [dashRange, setDashRange] = useState('month')  // 'mtd', 'month', or 'ytd'
  const dashRanges = useMemo(() => buildDashboardRanges(), [])

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), [])

  const viewProps = { month, setMonth, refreshKey, refresh }

  const views = {
    Dashboard: <DashboardView {...viewProps} range={dashRange} />,
    Transactions: <TransactionsView {...viewProps} />,
    Budgets: <BudgetsView {...viewProps} />,
    Insights: <InsightsView {...viewProps} />,
    Accounts: <AccountsView connected={connected} setConnected={setConnected} />,
    Settings: <SettingsView />,
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark">
            <CircleDollarSign size={22} />
          </div>
          <div>
            <strong>LedgerOne</strong>
            <span>Local finance server</span>
          </div>
        </div>

        <nav className="nav-list">
          {navItems.map(({ id, icon: Icon }) => (
            <button
              className={activeView === id ? 'nav-item active' : 'nav-item'}
              key={id}
              onClick={() => setActiveView(id)}
              type="button"
            >
              <Icon size={18} />
              <span>{id}</span>
            </button>
          ))}
        </nav>

        <div className="sync-card">
          <div className={connected ? 'sync-icon synced' : 'sync-icon'}>
            <Landmark size={18} />
          </div>
          <strong>{connected ? 'Plaid linked' : 'Manual mode'}</strong>
          <span>{connected ? 'Chase sync ready' : 'CSV fallback enabled'}</span>
          <button className="ghost full" type="button" onClick={() => setActiveView('Accounts')}>
            Configure
          </button>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <div>
              <p className="eyebrow">Personal Budget</p>
              <h1>{activeView}</h1>
            </div>
            {activeView === 'Dashboard' && (
              <select
                className="dash-range-select"
                value={dashRange === 'mtd' ? 'mtd' : dashRange === 'ytd' ? 'ytd' : month}
                onChange={(e) => {
                  const v = e.target.value
                  if (v === 'mtd') {
                    setDashRange('mtd')
                    setMonth(currentMonth())
                  } else if (v === 'ytd') {
                    setDashRange('ytd')
                    setMonth(currentMonth())
                  } else {
                    setDashRange('month')
                    setMonth(v)
                  }
                }}
              >
                {dashRanges.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            )}
          </div>
          <div className="top-actions">
            <button className="icon-button" type="button" aria-label="Search">
              <Search size={18} />
            </button>
            <button className="secondary" type="button" onClick={refresh}>
              <RefreshCw size={17} />
              Refresh
            </button>
            <button className="primary" type="button" onClick={() => setImportOpen(true)}>
              <Upload size={17} />
              Import CSV
            </button>
          </div>
        </header>

        {views[activeView]}
      </main>

      {importOpen && <ImportModal onClose={() => setImportOpen(false)} onImported={refresh} />}
    </div>
  )
}

// ─── Hooks ──────────────────────────────────────────────

function useApi(fetcher, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let stale = false
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting loading on dep change is the point of this fetch hook
    setLoading(true)
    fetcher()
      .then((d) => { if (!stale) setData(d) })
      .catch((e) => { if (!stale) setError(e.message) })
      .finally(() => { if (!stale) setLoading(false) })
    return () => { stale = true }
  }, deps)

  return { data, loading, error, setData }
}

// ─── Dashboard ──────────────────────────────────────────

function DashboardView({ month, refreshKey, range }) {
  const { data, loading } = useApi(() => api.fetchDashboard(month, range), [month, range, refreshKey])
  const { data: forecast } = useApi(() => api.fetchForecast(month), [month, refreshKey])
  const { data: smartForecast } = useApi(() => api.fetchSmartForecast(3), [refreshKey])
  const { data: anomalies } = useApi(() => api.fetchAnomalies(month), [month, refreshKey])
  const { data: recurring } = useApi(() => api.fetchRecurring(), [refreshKey])

  if (loading || !data) return <LoadingState />

  const m = data.metrics
  const balance = m.balance_available ?? m.balance_current
  const hasBalance = balance != null
  const afterPlanned = hasBalance ? balance - (m.planned_future || 0) : null
  const metrics = [
    { label: 'Income', value: fmtDollars(m.income), delta: '', tone: 'good' },
    { label: 'Spending', value: fmtDollars(m.spending), delta: '', tone: 'neutral' },
    { label: 'Balance', value: hasBalance ? fmtDollars(balance) : '—', delta: '', tone: hasBalance ? (balance >= 100 ? 'good' : 'warn') : 'neutral' },
    { label: 'Future Planned', value: fmtDollars(m.planned_future || 0), delta: '', tone: 'neutral' },
    { label: 'After Bills', value: afterPlanned != null ? fmtDollars(afterPlanned) : '—', delta: '', tone: afterPlanned != null ? (afterPlanned >= 0 ? 'good' : 'warn') : 'neutral' },
    { label: 'Savings Rate', value: `${m.savings_rate}%`, delta: '', tone: m.savings_rate >= 15 ? 'good' : 'warn' },
  ]

  return (
    <div className="page-grid">
      <section className="metric-grid" aria-label="Monthly summary">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            {metric.delta && <small className={metric.tone}>{metric.delta}</small>}
          </article>
        ))}
      </section>

      <CashFlowPanel cashFlow={data.cash_flow} />

      <section className="panel">
        <PanelHeader title="Budget Status" action={fmtMonth(month)} icon={Gauge} />
        {data.budgets.length > 0 ? (
          <BudgetList budgets={data.budgets} compact />
        ) : (
          <EmptyState message="No budgets set for this month" />
        )}
      </section>

      <section className="panel">
        <PanelHeader title="Spending Breakdown" action={fmtMonth(month)} icon={Tags} />
        {(data.spending_by_category || []).length > 0 ? (
          <SpendingBreakdown categories={data.spending_by_category} />
        ) : (
          <EmptyState message="No spending data this month" />
        )}
      </section>

      <section className="panel">
        <PanelHeader title="Future Planned" action={fmtMonth(month)} icon={CalendarDays} />
        {(data.planned_payments || []).length > 0 ? (
          <PlannedPaymentList payments={data.planned_payments} compact />
        ) : (
          <EmptyState message="No future payments planned this month" />
        )}
      </section>

      <section className="panel">
        <PanelHeader title="This Month Pace" action={forecast ? `${forecast.days_remaining}d left` : ''} icon={Gauge} />
        {forecast ? (
          <div className="forecast-panel">
            <div className="forecast-row">
              <span>Daily spend rate</span>
              <strong>{fmtDollars(forecast.daily_spend_rate)}/day</strong>
            </div>
            <div className="forecast-row">
              <span>Projected remaining</span>
              <strong className="warn">{fmtDollars(forecast.projected_additional_spending)}</strong>
            </div>
            <div className="forecast-row forecast-total">
              <span>End-of-month balance</span>
              <strong className={forecast.projected_end_balance >= 0 ? 'good' : 'warn'}>{fmtDollars(forecast.projected_end_balance)}</strong>
            </div>
          </div>
        ) : <LoadingState />}
      </section>

      <section className="panel wide">
        <PanelHeader title="Smart Forecast" action="Next 3 months" icon={Sparkles} />
        {smartForecast ? (
          <div className="smart-forecast">
            <div className="sf-summary">
              <SummaryItem label="Avg income" value={fmtDollars(smartForecast.summary.weighted_income)} tone="good" />
              <SummaryItem label="Avg spending" value={fmtDollars(smartForecast.summary.weighted_spending)} />
              <SummaryItem label="Avg net" value={fmtDollars(smartForecast.summary.weighted_income - smartForecast.summary.weighted_spending)} tone={smartForecast.summary.weighted_income >= smartForecast.summary.weighted_spending ? 'good' : 'warn'} />
            </div>

            <div className="sf-months">
              {smartForecast.forecast.map((f) => (
                <div className="sf-month-card" key={f.month}>
                  <strong>{fmtMonth(f.month)}</strong>
                  <div className="sf-month-row">
                    <span>Income</span><span className="good">{fmtDollars(f.projected_income)}</span>
                  </div>
                  <div className="sf-month-row">
                    <span>Spending</span><span>{fmtDollars(f.projected_spending)}</span>
                  </div>
                  <div className="sf-month-row sf-net">
                    <span>Net</span><span className={f.projected_net >= 0 ? 'good' : 'warn'}>{f.projected_net >= 0 ? '+' : ''}{fmtDollars(f.projected_net)}</span>
                  </div>
                </div>
              ))}
            </div>

            <h3 style={{ marginTop: 14, marginBottom: 8 }}>Category Projections</h3>
            <div className="sf-categories">
              {smartForecast.by_category.map((c) => (
                <div className="sf-cat-row" key={c.category}>
                  <span className="spending-dot" style={{ background: CATEGORY_COLORS[c.category] || '#4e6178' }} />
                  <span className="sf-cat-name">{c.category}</span>
                  <span className="sf-cat-amount">{fmtDollars(c.projected)}/mo</span>
                  <span className={c.trend === 'rising' ? 'warn' : c.trend === 'falling' ? 'good' : 'neutral'}>
                    {c.trend === 'rising' ? '↑' : c.trend === 'falling' ? '↓' : '→'} {c.trend}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : <LoadingState />}
      </section>

      {anomalies && anomalies.length > 0 && (
        <section className="panel">
          <PanelHeader title="Spending Alerts" action={`${anomalies.length} flagged`} icon={Filter} />
          <div className="anomaly-list">
            {anomalies.map((a) => (
              <div className="anomaly-row" key={a.category}>
                <strong>{a.category}</strong>
                <span>{fmtDollars(a.current)} vs avg {fmtDollars(a.average)}</span>
                <span className="warn">+{a.pct_over}% over</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel">
        <PanelHeader title="AI Brief" action="" icon={Bot} />
        <AiBrief month={month} />
      </section>

      {recurring && recurring.length > 0 && (
        <section className="panel">
          <PanelHeader title="Recurring" action={`${recurring.length} detected`} icon={RefreshCw} />
          <div className="recurring-list">
            {recurring.slice(0, 8).map((r) => (
              <div className="recurring-row" key={r.merchant}>
                <div>
                  <strong>{r.merchant}</strong>
                  <span>{r.category} · {r.month_count} months</span>
                </div>
                <strong>{fmtDollars(r.avg_amount)}/mo</strong>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel wide">
        <PanelHeader title="Recent Transactions" action={`${data.recent_transactions.length} shown`} icon={ListChecks} />
        {data.recent_transactions.length > 0 ? (
          <TransactionTable transactions={data.recent_transactions} compact />
        ) : (
          <EmptyState message="No transactions yet — import a CSV to get started" />
        )}
      </section>
    </div>
  )
}

// ─── Cash Flow Panel ────────────────────────────────────

const RANGE_OPTIONS = [
  { label: 'This Month', value: 1 },
  { label: '3 Months', value: 3 },
  { label: '6 Months', value: 6 },
  { label: 'All', value: 0 },
]

function CashFlowPanel({ cashFlow }) {
  const [range, setRange] = useState(4)  // default to all data (since we only have ~4 months)
  const [tab, setTab] = useState('flow')  // 'flow' | 'compare'
  const [tooltip, setTooltip] = useState(null)
  const [tooltipData, setTooltipData] = useState(null)
  const tooltipRef = useRef(null)

  // Filter cash flow by range
  const filtered = useMemo(() => {
    if (range === 0 || range >= cashFlow.length) return cashFlow
    return cashFlow.slice(-range)
  }, [cashFlow, range])

  const maxVal = Math.max(...filtered.map((c) => Math.max(c.income, c.spending)), 1)

  async function handleBarHover(month) {
    if (tooltip === month) return
    setTooltip(month)
    try {
      const cats = await api.fetchMonthCategories(month)
      setTooltipData({ month, categories: cats })
    } catch {
      setTooltipData(null)
    }
  }

  function handleBarLeave() {
    setTooltip(null)
    setTooltipData(null)
  }

  // Comparison: show spending change between consecutive months
  const comparison = useMemo(() => {
    if (filtered.length < 2) return []
    return filtered.slice(1).map((curr, i) => {
      const prev = filtered[i]
      const spendDelta = curr.spending - prev.spending
      const incomeDelta = curr.income - prev.income
      return {
        month: curr.month,
        prevMonth: prev.month,
        spending: curr.spending,
        prevSpending: prev.spending,
        spendDelta,
        spendPct: prev.spending > 0 ? ((spendDelta / prev.spending) * 100) : 0,
        income: curr.income,
        prevIncome: prev.income,
        incomeDelta,
        incomePct: prev.income > 0 ? ((incomeDelta / prev.income) * 100) : 0,
      }
    })
  }, [filtered])

  return (
    <section className="panel wide">
      <div className="cashflow-header">
        <div className="panel-header" style={{ marginBottom: 0 }}>
          <div>
            <CalendarDays size={18} />
            <h2>Cash Flow</h2>
          </div>
        </div>
        <div className="cashflow-controls">
          <div className="tab-group">
            <button className={tab === 'flow' ? 'tab active' : 'tab'} type="button" onClick={() => setTab('flow')}>Chart</button>
            <button className={tab === 'compare' ? 'tab active' : 'tab'} type="button" onClick={() => setTab('compare')}>Compare</button>
          </div>
          <div className="range-group">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={range === opt.value ? 'range-btn active' : 'range-btn'}
                type="button"
                onClick={() => setRange(opt.value)}
              >{opt.label}</button>
            ))}
          </div>
        </div>
      </div>

      {tab === 'flow' ? (
        filtered.length > 0 ? (
          <>
            <div className="chart" aria-label="Income and spending chart" style={{ gridTemplateColumns: `repeat(${filtered.length}, 1fr)` }}>
              {filtered.map((item) => (
                <div
                  className="chart-group"
                  key={item.month}
                  onMouseEnter={() => handleBarHover(item.month)}
                  onMouseLeave={handleBarLeave}
                  style={{ position: 'relative' }}
                >
                  <div className="bars">
                    <span className="income-bar" style={{ height: `${(item.income / maxVal) * 160}px` }} title={`Income: ${fmtDollars(item.income)}`} />
                    <span className="spend-bar" style={{ height: `${(item.spending / maxVal) * 160}px` }} title={`Spending: ${fmtDollars(item.spending)}`} />
                  </div>
                  <small>{fmtMonth(item.month).split(' ')[0]}</small>
                  <div className="bar-amounts">
                    <small className="good">{fmtDollars(item.income)}</small>
                    <small style={{ color: 'var(--accent-strong)' }}>{fmtDollars(item.spending)}</small>
                  </div>

                  {tooltip === item.month && tooltipData && tooltipData.month === item.month && (
                    <div className="bar-tooltip" ref={tooltipRef}>
                      <strong>{fmtMonth(item.month)}</strong>
                      {tooltipData.categories.map((cat) => (
                        <div className="tooltip-row" key={cat.category}>
                          <span>{cat.category || 'Uncategorized'}</span>
                          <span>
                            {cat.income > 0 && <span className="good">+{fmtDollars(cat.income)}</span>}
                            {cat.spending > 0 && <span style={{ color: 'var(--accent-strong)' }}> -{fmtDollars(cat.spending)}</span>}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="legend">
              <span><i className="income-dot" /> Income</span>
              <span><i className="spend-dot" /> Spending</span>
            </div>
          </>
        ) : (
          <EmptyState message="Import transactions to see cash flow" />
        )
      ) : (
        comparison.length > 0 ? (
          <div className="compare-grid">
            {comparison.map((c) => (
              <div className="compare-card" key={c.month}>
                <div className="compare-header">
                  <strong>{fmtMonth(c.prevMonth)}</strong>
                  <ChevronRight size={16} />
                  <strong>{fmtMonth(c.month)}</strong>
                </div>
                <div className="compare-rows">
                  <div className="compare-row">
                    <span>Spending</span>
                    <span>{fmtDollars(c.prevSpending)} → {fmtDollars(c.spending)}</span>
                    <span className={c.spendDelta <= 0 ? 'good' : 'warn'}>
                      {c.spendDelta > 0 ? '+' : ''}{fmtDollars(c.spendDelta)} ({c.spendPct > 0 ? '+' : ''}{c.spendPct.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="compare-row">
                    <span>Income</span>
                    <span>{fmtDollars(c.prevIncome)} → {fmtDollars(c.income)}</span>
                    <span className={c.incomeDelta >= 0 ? 'good' : 'warn'}>
                      {c.incomeDelta > 0 ? '+' : ''}{fmtDollars(c.incomeDelta)} ({c.incomePct > 0 ? '+' : ''}{c.incomePct.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="compare-row">
                    <span>Net change</span>
                    <span></span>
                    <span className={c.incomeDelta - c.spendDelta >= 0 ? 'good' : 'warn'}>
                      {(c.incomeDelta - c.spendDelta) >= 0 ? '+' : ''}{fmtDollars(c.incomeDelta - c.spendDelta)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState message="Need at least 2 months of data to compare" />
        )
      )}
    </section>
  )
}

const CATEGORY_COLORS = {
  Tuition: '#dc2626',
  Dining: '#c2410c',
  Shopping: '#b7791f',
  Groceries: '#2563eb',
  Transportation: '#0d9488',
  Gas: '#16803c',
  Entertainment: '#0891b2',
  Subscriptions: '#7c3aed',
  Health: '#be185d',
  Personal: '#a3a3a3',
  Utilities: '#737373',
  Transfer: '#4e6178',
  Income: '#00d4aa',
}

function SpendingBreakdown({ categories }) {
  const total = categories.reduce((s, c) => s + c.amount, 0)

  return (
    <div className="spending-breakdown">
      <div className="spending-bar-track">
        {categories.map((cat) => {
          const pct = total > 0 ? (cat.amount / total) * 100 : 0
          if (pct < 1) return null
          return (
            <span
              key={cat.category}
              className="spending-bar-segment"
              style={{ width: `${pct}%`, background: CATEGORY_COLORS[cat.category] || '#4e6178' }}
              title={`${cat.category}: ${fmtDollars(cat.amount)} (${pct.toFixed(0)}%)`}
            />
          )
        })}
      </div>
      <div className="spending-list">
        {categories.map((cat) => {
          const pct = total > 0 ? (cat.amount / total) * 100 : 0
          return (
            <div className="spending-row" key={cat.category}>
              <span className="spending-dot" style={{ background: CATEGORY_COLORS[cat.category] || '#4e6178' }} />
              <span className="spending-label">{cat.category}</span>
              <span className="spending-amount">{fmtDollars(cat.amount)}</span>
              <span className="spending-pct">{pct.toFixed(0)}%</span>
            </div>
          )
        })}
        <div className="spending-row spending-total">
          <span className="spending-dot" style={{ background: 'transparent' }} />
          <span className="spending-label">Total</span>
          <span className="spending-amount">{fmtDollars(total)}</span>
          <span className="spending-pct"></span>
        </div>
      </div>
    </div>
  )
}

function AiBrief({ month }) {
  const [brief, setBrief] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSummarize() {
    setLoading(true)
    try {
      const data = await api.aiInsights(month)
      setBrief(data)
    } catch {
      setBrief(null)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <p style={{ color: 'var(--muted)', fontSize: 14 }}>Generating insights...</p>

  if (!brief) {
    return (
      <div className="brief">
        <p style={{ color: 'var(--muted-strong)' }}>Get AI-powered spending insights and recommendations.</p>
        <button className="primary" type="button" onClick={handleSummarize}>
          <Sparkles size={16} />
          Summarize {fmtMonth(month)}
        </button>
      </div>
    )
  }

  if (brief.length === 0) {
    return (
      <div className="brief">
        <p style={{ color: 'var(--muted-strong)' }}>No insights available — add more transactions first.</p>
        <button className="secondary" type="button" onClick={handleSummarize}>
          <RefreshCw size={16} />
          Try again
        </button>
      </div>
    )
  }

  return (
    <div className="brief">
      <strong>{brief[0].title}</strong>
      <p>{brief[0].body}</p>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="secondary" type="button" onClick={handleSummarize}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
    </div>
  )
}

// ─── Transactions ───────────────────────────────────────

function TransactionsView({ month, refreshKey, refresh }) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data: transactions, loading } = useApi(
    () => api.fetchTransactions({ month, search: search || undefined, status: statusFilter || undefined }),
    [month, refreshKey, search, statusFilter],
  )

  function handleExport() {
    if (!transactions || transactions.length === 0) return
    const headers = ['Date', 'Merchant', 'Category', 'Account', 'Status', 'Amount']
    const csvRows = [headers.join(',')]
    for (const tx of transactions) {
      csvRows.push([
        tx.date,
        `"${(tx.merchant || '').replace(/"/g, '""')}"`,
        tx.category,
        `"${(tx.account || '').replace(/"/g, '""')}"`,
        tx.status,
        tx.amount.toFixed(2),
      ].join(','))
    }
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ledgerone-${month}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading || !transactions) return <LoadingState />

  return (
    <section className="panel full-width">
      <div className="filter-row">
        <label className="search-box">
          <Search size={18} />
          <input
            placeholder="Search merchant, category, or amount"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <button className="secondary" type="button"><CalendarDays size={17} /> {fmtMonth(month)}</button>
        <button
          className="secondary"
          type="button"
          onClick={() => setStatusFilter(statusFilter === 'Review' ? '' : 'Review')}
          style={statusFilter ? { borderColor: 'var(--warn)' } : {}}
        >
          <Filter size={17} /> {statusFilter || 'All Status'}
        </button>
        <button className="secondary" type="button" onClick={handleExport}><Download size={17} /> Export</button>
      </div>
      {transactions.length > 0 ? (
        <TransactionTable transactions={transactions} onUpdate={refresh} />
      ) : (
        <EmptyState message="No transactions match your filters" />
      )}
    </section>
  )
}

// ─── Budgets ────────────────────────────────────────────

function BudgetsView({ month, setMonth, refreshKey, refresh }) {
  const { data, loading } = useApi(() => api.fetchBudgets(month), [month, refreshKey])
  const { data: rules, loading: rulesLoading } = useApi(() => api.fetchRules(), [refreshKey])

  const [addOpen, setAddOpen] = useState(false)
  const [newCat, setNewCat] = useState('')
  const [newPlanned, setNewPlanned] = useState('')
  const [budgetPrompt, setBudgetPrompt] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [paymentName, setPaymentName] = useState('')
  const [paymentCategory, setPaymentCategory] = useState('Upcoming')
  const [paymentAmount, setPaymentAmount] = useState('')
  const [paymentDueDate, setPaymentDueDate] = useState(`${month}-01`)
  const [paymentNotes, setPaymentNotes] = useState('')

  const [newRulePattern, setNewRulePattern] = useState('')
  const [newRuleCat, setNewRuleCat] = useState('')

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset default due date when active month changes
    setPaymentDueDate(`${month}-01`)
  }, [month])

  if (loading || !data) return <LoadingState />

  const totalBudgeted = data.budgets.reduce((s, b) => s + b.planned, 0)
  const totalActual = data.budgets.reduce((s, b) => s + (b.actual || 0), 0)
  const totalPlannedPayments = (data.planned_payments || []).reduce((s, p) => s + p.amount, 0)
  const balance = data.balance ?? null

  async function handleAddBudget(e) {
    e.preventDefault()
    if (!newCat || !newPlanned) return
    await api.upsertBudget(month, newCat, parseFloat(newPlanned))
    setNewCat('')
    setNewPlanned('')
    setAddOpen(false)
    refresh()
  }

  async function handleAddPlannedPayment(e) {
    e.preventDefault()
    if (!paymentName || !paymentAmount || !paymentDueDate) return
    await api.createPlannedPayment({
      name: paymentName,
      category: paymentCategory || 'Upcoming',
      amount: parseFloat(paymentAmount),
      due_date: paymentDueDate,
      notes: paymentNotes || null,
    })
    setPaymentName('')
    setPaymentCategory('Upcoming')
    setPaymentAmount('')
    setPaymentNotes('')
    refresh()
  }

  async function handleBuildDraft() {
    if (!budgetPrompt) return
    setDrafting(true)
    try {
      const res = await api.aiBudgetDraft(budgetPrompt, true)
      if (res.draft && res.draft.length > 0) {
        for (const item of res.draft) {
          await api.upsertBudget(month, item.category, item.planned, item.color || '#2563eb')
        }
        refresh()
        setBudgetPrompt('')
      }
    } finally {
      setDrafting(false)
    }
  }

  async function handleAddRule(e) {
    e.preventDefault()
    if (!newRulePattern || !newRuleCat) return
    await api.createRule(newRulePattern, newRuleCat)
    setNewRulePattern('')
    setNewRuleCat('')
    refresh()
  }

  return (
    <div className="page-grid">
      <section className="panel wide">
        <div className="month-switcher">
          <button className="icon-button" type="button" aria-label="Previous month" onClick={() => setMonth(shiftMonth(month, -1))}><ChevronLeft size={18} /></button>
          <div>
            <p className="eyebrow">Budget Plan</p>
            <h2>{fmtMonth(month)}</h2>
          </div>
          <button className="icon-button" type="button" aria-label="Next month" onClick={() => setMonth(shiftMonth(month, 1))}><ChevronRight size={18} /></button>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            <button className="secondary" type="button" onClick={async () => { await api.autoPopulateBudgets(month); refresh() }} title="Generate budgets from your average spending">
              <Sparkles size={15} /> Auto-fill
            </button>
            <button className="secondary" type="button" onClick={async () => { await api.copyBudgets(shiftMonth(month, -1), month); refresh() }} title="Copy last month's budget">
              <ChevronRight size={15} /> Copy prev
            </button>
            <button className="primary add-budget" type="button" onClick={() => setAddOpen(!addOpen)}><Plus size={15} /> Add</button>
          </div>
        </div>

        {addOpen && (
          <form onSubmit={handleAddBudget} style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
            <input placeholder="Category name" value={newCat} onChange={(e) => setNewCat(e.target.value)} style={{ border: '1px solid var(--line)', borderRadius: 3, padding: '0 10px', minHeight: 34, background: 'var(--panel)', color: 'var(--ink)', flex: 1 }} />
            <input placeholder="Amount" type="number" value={newPlanned} onChange={(e) => setNewPlanned(e.target.value)} style={{ border: '1px solid var(--line)', borderRadius: 3, padding: '0 10px', minHeight: 34, background: 'var(--panel)', color: 'var(--ink)', width: 110 }} />
            <button className="primary" type="submit">Save</button>
          </form>
        )}

        <div className="budget-summary">
          <SummaryItem label="Balance" value={balance != null ? fmtDollars(balance) : '—'} tone={balance != null ? (balance >= 100 ? 'good' : 'warn') : 'neutral'} />
          <SummaryItem label="Income this month" value={fmtDollars(data.income)} />
          <SummaryItem label="Budgeted" value={fmtDollars(totalBudgeted)} />
          <SummaryItem label="Spent so far" value={fmtDollars(totalActual)} tone={totalActual > totalBudgeted ? 'warn' : 'good'} />
          <SummaryItem label="Bills remaining" value={fmtDollars(totalPlannedPayments)} />
        </div>
        {data.budgets.length > 0 ? (
          <BudgetList budgets={data.budgets} onDelete={async (id) => { await api.deleteBudget(id); refresh() }} onUpdate={async (id, planned) => { const b = data.budgets.find(x => x.id === id); if (b) await api.upsertBudget(month, b.category, planned, b.color); refresh() }} />
        ) : (
          <EmptyState message="No budget categories yet — click Auto-fill or Add" />
        )}

        {(data.unbudgeted || []).length > 0 && (
          <div style={{ marginTop: 14 }}>
            <h3 style={{ color: 'var(--warn)', marginBottom: 8 }}>Unbudgeted Spending</h3>
            {data.unbudgeted.map((u) => (
              <div key={u.category} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--line)', fontSize: 12 }}>
                <span style={{ color: 'var(--ink)', fontWeight: 700 }}>{u.category}</span>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ color: 'var(--warn)' }}>{fmtDollars(u.actual)}</span>
                  <button className="ghost" type="button" style={{ minHeight: 24, fontSize: 10 }} onClick={async () => { const planned = Math.ceil(u.actual / 5) * 5; await api.upsertBudget(month, u.category, planned); refresh() }}>
                    + Budget
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel ai-budget-panel">
        <PanelHeader title="AI Budget Builder" action="Draft only" icon={Bot} />
        <div className="budget-coach">
          <p>Plan the month conversationally, then let AI draft category targets for review.</p>
          <label className="budget-prompt">
            <Sparkles size={18} />
            <textarea
              placeholder="Example: I want to save $700, keep dining lower, and account for a trip this month..."
              value={budgetPrompt}
              onChange={(e) => setBudgetPrompt(e.target.value)}
            />
          </label>
          <div className="coach-actions">
            <button className="secondary" type="button" disabled={drafting} onClick={() => { setBudgetPrompt('Use the same categories and amounts as last month'); handleBuildDraft() }}>
              <SlidersHorizontal size={17} />
              Use last month
            </button>
            <button className="primary" type="button" disabled={drafting || !budgetPrompt} onClick={handleBuildDraft}>
              {drafting ? <Loader2 size={17} className="spin" /> : <Sparkles size={17} />}
              {drafting ? 'Building...' : 'Build draft'}
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <PanelHeader title="Future Planned Payments" action={fmtMonth(month)} icon={CalendarDays} />
        <form className="planned-payment-form" onSubmit={handleAddPlannedPayment}>
          <input placeholder="Payment name" value={paymentName} onChange={(e) => setPaymentName(e.target.value)} />
          <div className="planned-payment-grid">
            <input placeholder="Category" value={paymentCategory} onChange={(e) => setPaymentCategory(e.target.value)} />
            <input placeholder="Amount" type="number" min="0" step="0.01" value={paymentAmount} onChange={(e) => setPaymentAmount(e.target.value)} />
          </div>
          <input type="date" value={paymentDueDate} onChange={(e) => setPaymentDueDate(e.target.value)} />
          <input placeholder="Notes, optional" value={paymentNotes} onChange={(e) => setPaymentNotes(e.target.value)} />
          <button className="primary" type="submit"><Plus size={17} /> Add planned payment</button>
        </form>
        {(data.planned_payments || []).length > 0 ? (
          <PlannedPaymentList
            payments={data.planned_payments}
            onPaid={async (payment) => { await api.updatePlannedPayment(payment.id, { paid: true }); refresh() }}
            onDelete={async (payment) => { await api.deletePlannedPayment(payment.id); refresh() }}
          />
        ) : (
          <EmptyState message="Add tuition, rent, travel, or other future payments for this month" />
        )}
      </section>

      <section className="panel">
        <PanelHeader title="Rules" action={rulesLoading ? '...' : `${(rules || []).length} active`} icon={SlidersHorizontal} />
        <div className="rule-list">
          {(rules || []).map((rule) => (
            <div className="rule" key={rule.id}>
              <Tags size={17} />
              <div>
                <strong>{rule.pattern}</strong>
                <span>{rule.category}</span>
              </div>
              <button className="icon-button tiny" type="button" onClick={async () => { await api.deleteRule(rule.id); refresh() }} aria-label="Delete rule">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          <form onSubmit={handleAddRule} style={{ display: 'flex', gap: 8 }}>
            <input placeholder="Merchant" value={newRulePattern} onChange={(e) => setNewRulePattern(e.target.value)} style={{ border: '1px solid var(--line)', borderRadius: 7, padding: '0 10px', minHeight: 34, background: 'var(--panel)', color: 'var(--ink)', flex: 1 }} />
            <input placeholder="Category" value={newRuleCat} onChange={(e) => setNewRuleCat(e.target.value)} style={{ border: '1px solid var(--line)', borderRadius: 7, padding: '0 10px', minHeight: 34, background: 'var(--panel)', color: 'var(--ink)', flex: 1 }} />
            <button className="primary" type="submit" style={{ minHeight: 34, fontSize: 13 }}>Add</button>
          </form>
        </div>
      </section>
    </div>
  )
}

// ─── Insights ───────────────────────────────────────────

function InsightsView({ month, refreshKey }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [asking, setAsking] = useState(false)
  const { data: insights, loading } = useApi(() => api.aiInsights(month), [month, refreshKey])
  const abortRef = useRef(null)

  // Cancel any running AI query on unmount
  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  async function handleAsk(q) {
    const text = q || question
    if (!text) return

    // Abort previous request if still running
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setAsking(true)
    setAnswer('')
    try {
      await api.aiChatStream(text, month, (chunk) => {
        setAnswer((prev) => prev + chunk)
      }, controller.signal)
    } catch (e) {
      if (e.name !== 'AbortError') {
        setAnswer('Error: ' + e.message)
      }
    } finally {
      setAsking(false)
    }
  }

  const quickQuestions = [
    'What changed since last month?',
    'Which subscriptions should I review?',
    'Where am I overspending?',
    'How much can I save by end of month?',
  ]

  return (
    <div className="page-grid">
      <section className="panel wide">
        <PanelHeader title="Ask AI" action="Uses local ledger data" icon={Sparkles} />
        <label className="ai-prompt">
          <Bot size={20} />
          <input
            placeholder="Can I afford a $500 purchase this month?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
          />
          <button className="primary" type="button" disabled={asking || !question} onClick={() => handleAsk()}>
            {asking ? 'Thinking...' : 'Ask'}
          </button>
        </label>
        {answer && (
          <div style={{ marginTop: 14, padding: 14, background: 'var(--subtle)', borderRadius: 8, border: '1px solid var(--line)' }}>
            <p style={{ color: 'var(--ink)', fontSize: 14, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{answer}</p>
          </div>
        )}
        <div className="question-grid">
          {quickQuestions.map((q) => (
            <button key={q} type="button" onClick={() => { setQuestion(q); handleAsk(q) }}>{q}</button>
          ))}
        </div>
      </section>

      {loading ? (
        <LoadingState />
      ) : (
        (insights || []).map((card, i) => (
          <article className="panel insight-card" key={i}>
            <Sparkles size={18} />
            <h3>{card.title}</h3>
            <p>{card.body}</p>
            <button className="ghost" type="button">{card.action}</button>
          </article>
        ))
      )}
    </div>
  )
}

// ─── Accounts ───────────────────────────────────────────

function AccountsView({ connected, setConnected }) {
  const [linkToken, setLinkToken] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [syncStats, setSyncStats] = useState(null)
  const [plaidError, setPlaidError] = useState(null)
  const [receivedRedirectUri, setReceivedRedirectUri] = useState(null)

  // Check Plaid status on mount
  useEffect(() => {
    api.plaidStatus().then((s) => { if (s.linked) setConnected(true) }).catch(() => {})
  }, [])

  // Detect OAuth redirect return (URL will have oauth_state_id param)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('oauth_state_id')) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reading the OAuth redirect URI from window.location must happen on mount
      setReceivedRedirectUri(window.location.href)
      // Re-create link token to complete OAuth
      api.plaidCreateLinkToken()
        .then((res) => setLinkToken(res.link_token))
        .catch((e) => setPlaidError('Failed to resume OAuth: ' + e.message))
    }
  }, [])

  // Get a link token when user wants to connect
  async function handleStartLink() {
    setPlaidError(null)
    try {
      const res = await api.plaidCreateLinkToken()
      setLinkToken(res.link_token)
    } catch (e) {
      setPlaidError('Failed to create link token: ' + e.message)
    }
  }

  async function handleSync() {
    setSyncing(true)
    setSyncStats(null)
    try {
      const stats = await api.plaidSync()
      setSyncStats(stats)
    } catch (e) {
      setPlaidError('Sync failed: ' + e.message)
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="page-grid">
      <section className="panel wide">
        <PanelHeader title="Data Connections" action="Chase preferred" icon={Landmark} />
        <div className="connection-list">
          <div className="connection-row">
            <div className="connection-icon"><Landmark size={18} /></div>
            <div>
              <strong>Chase via Plaid</strong>
              <span>{connected ? 'Connected — click Sync to pull latest transactions' : 'Use Plaid Link for automatic transaction sync'}</span>
            </div>
            <span className="status">{connected ? 'Connected' : 'Not linked'}</span>
            {connected ? (
              <button className="secondary" type="button" onClick={handleSync} disabled={syncing}>
                <RefreshCw size={17} />
                {syncing ? 'Syncing...' : 'Sync'}
              </button>
            ) : linkToken ? (
              <PlaidLinkButton
                linkToken={linkToken}
                receivedRedirectUri={receivedRedirectUri}
                onError={(msg) => setPlaidError(msg)}
                onSuccess={(publicToken) => {
                  api.plaidExchangeToken(publicToken).then(() => {
                    setConnected(true)
                    setLinkToken(null)
                    handleSync()
                  }).catch((e) => setPlaidError(e.message))
                }}
              />
            ) : (
              <button className="primary" type="button" onClick={handleStartLink}>Connect Plaid</button>
            )}
          </div>

          {syncStats && (
            <div style={{ padding: '12px', background: 'var(--subtle)', borderRadius: 8, border: '1px solid var(--line)' }}>
              <p style={{ color: 'var(--good)', fontSize: 14 }}>
                Sync complete — {syncStats.added} added, {syncStats.modified} modified, {syncStats.removed} removed
              </p>
            </div>
          )}

          {plaidError && (
            <div style={{ padding: '12px', background: 'var(--bad-soft)', borderRadius: 8, border: '1px solid var(--bad)' }}>
              <p style={{ color: 'var(--bad)', fontSize: 14 }}>{plaidError}</p>
            </div>
          )}

          <ConnectionRow
            title="Chase CSV Import"
            detail="Upload downloaded Chase CSV files when Plaid is unavailable or paused"
            status="Fallback ready"
            action="Import CSV"
          />
          <ConnectionRow
            title="Local SQLite Store"
            detail="All data stored locally in ledgerone.db"
            status="Active"
            action="View schema"
          />
        </div>
      </section>

      <section className="panel">
        <PanelHeader title="Privacy" action="Local-first" icon={ShieldCheck} />
        <ul className="check-list">
          <li><CheckCircle2 size={17} /> No Chase password stored</li>
          <li><CheckCircle2 size={17} /> Plaid tokens stay server-side</li>
          <li><CheckCircle2 size={17} /> CSV imports can run offline</li>
          <li><CheckCircle2 size={17} /> AI receives summarized data only</li>
        </ul>
      </section>
    </div>
  )
}

function PlaidLinkButton({ linkToken, onSuccess, onError, receivedRedirectUri }) {
  const config = {
    token: linkToken,
    onSuccess: (publicToken) => onSuccess(publicToken),
    onExit: (err, metadata) => {
      if (err) {
        console.error('Plaid Link error:', err)
        console.error('Plaid Link metadata:', metadata)
        if (onError) onError(`${err.error_code}: ${err.error_message}`)
      }
    },
  }
  if (receivedRedirectUri) {
    config.receivedRedirectUri = receivedRedirectUri
  }

  const { open, ready } = usePlaidLink(config)

  useEffect(() => {
    if (ready) open()
  }, [ready, open])

  return (
    <button className="primary" type="button" disabled={!ready} onClick={() => open()}>
      Link Account
    </button>
  )
}

// ─── Settings ───────────────────────────────────────────

function SettingsView() {
  return (
    <section className="panel full-width settings-grid">
      <SettingRow title="Server URL" detail="http://localhost:8787" />
      <SettingRow title="Plaid environment" detail="Production, with CSV fallback" />
      <SettingRow title="Duplicate detection" detail="Match date, amount, merchant, and account" />
      <SettingRow title="AI mode" detail="Summaries and categorization suggestions require review" />
      <SettingRow title="Backup cadence" detail="Weekly encrypted SQLite backup" />
    </section>
  )
}

// ─── Shared Components ──────────────────────────────────

function LoadingState() {
  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: 200, color: 'var(--muted)' }}>
      <Loader2 size={24} className="spin" />
    </div>
  )
}

function EmptyState({ message }) {
  return <p style={{ color: 'var(--muted)', fontSize: 14, padding: '20px 0', textAlign: 'center' }}>{message}</p>
}

function PanelHeader({ title, action, icon: Icon }) {
  return (
    <div className="panel-header">
      <div>
        <Icon size={18} />
        <h2>{title}</h2>
      </div>
      {action && <button className="ghost" type="button">{action}</button>}
    </div>
  )
}

function TransactionTable({ transactions, compact = false, onUpdate }) {
  const rows = compact ? transactions.slice(0, 5) : transactions
  const [editingId, setEditingId] = useState(null)
  const [editCat, setEditCat] = useState('')
  const [editMerchant, setEditMerchant] = useState('')
  const [rulePrompt, setRulePrompt] = useState(null)

  const CATEGORIES = ['Groceries', 'Dining', 'Gas', 'Shopping', 'Subscriptions', 'Entertainment', 'Health', 'Travel', 'Transportation', 'Tuition', 'Transfer', 'Income', 'Personal', 'Utilities', 'Uncategorized']

  function startEdit(tx) {
    if (compact) return
    setEditingId(tx.id)
    setEditCat(tx.category)
    setEditMerchant(tx.merchant)
    setRulePrompt(null)
  }

  async function saveEdit(tx) {
    const updates = {}
    if (editCat !== tx.category) updates.category = editCat
    if (editMerchant !== tx.merchant) updates.merchant = editMerchant
    if (Object.keys(updates).length > 0) {
      if (updates.category) updates.status = 'Manual'
      await api.updateTransaction(tx.id, updates)
      // If category changed, offer to create a rule
      if (updates.category) {
        setRulePrompt({ merchant: editMerchant || tx.merchant, category: editCat, txId: tx.id })
        setEditingId(null)
        return
      }
    }
    setEditingId(null)
    onUpdate?.()
  }

  async function createRuleFromPrompt() {
    if (!rulePrompt) return
    // Extract a clean keyword from the merchant name (first 2 words usually)
    const words = rulePrompt.merchant.replace(/[^a-zA-Z\s']/g, '').trim().split(/\s+/)
    const pattern = words.slice(0, 2).join(' ')
    await api.createRule(pattern, rulePrompt.category)
    setRulePrompt(null)
    onUpdate?.()
  }

  return (
    <div className="table-wrap">
      {rulePrompt && (
        <div className="rule-prompt-bar">
          <span>Create rule: <strong>{rulePrompt.merchant.split(' ').slice(0, 2).join(' ')}</strong> → <strong>{rulePrompt.category}</strong>?</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="primary" type="button" style={{ minHeight: 26, fontSize: 10, padding: '0 10px' }} onClick={createRuleFromPrompt}>Yes, create rule</button>
            <button className="ghost" type="button" style={{ minHeight: 26, fontSize: 10 }} onClick={() => { setRulePrompt(null); onUpdate?.() }}>No thanks</button>
          </div>
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Merchant</th>
            <th>Category</th>
            <th>Account</th>
            <th>Status</th>
            <th className="amount">Amount</th>
            {!compact && <th aria-label="Actions"></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((tx) => (
            editingId === tx.id ? (
              <tr key={tx.id} className="editing-row">
                <td>{fmtDate(tx.date)}</td>
                <td>
                  <input
                    value={editMerchant}
                    onChange={(e) => setEditMerchant(e.target.value)}
                    className="edit-input"
                    autoFocus
                  />
                </td>
                <td>
                  <select value={editCat} onChange={(e) => setEditCat(e.target.value)} className="edit-select">
                    {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </td>
                <td>{tx.account}</td>
                <td><span className={tx.status === 'Review' ? 'status warning' : 'status'}>{tx.status}</span></td>
                <td className={tx.amount > 0 ? 'amount good' : 'amount'}>{fmtAmount(tx.amount)}</td>
                <td>
                  <div style={{ display: 'flex', gap: 3 }}>
                    <button className="primary" type="button" style={{ minHeight: 24, fontSize: 10, padding: '0 8px', borderRadius: 3 }} onClick={() => saveEdit(tx)}>Save</button>
                    <button className="ghost" type="button" style={{ minHeight: 24, fontSize: 10 }} onClick={() => setEditingId(null)}>
                      <X size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ) : (
              <tr key={tx.id} onClick={() => startEdit(tx)} style={compact ? {} : { cursor: 'pointer' }}>
                <td>{fmtDate(tx.date)}</td>
                <td className="merchant">{tx.merchant}</td>
                <td><span className="category-pill">{tx.category}</span></td>
                <td>{tx.account}</td>
                <td><span className={tx.status === 'Review' ? 'status warning' : 'status'}>{tx.status}</span></td>
                <td className={tx.amount > 0 ? 'amount good' : 'amount'}>{fmtAmount(tx.amount)}</td>
                {!compact && <td><button className="icon-button tiny" type="button" aria-label="Edit transaction" onClick={(e) => { e.stopPropagation(); startEdit(tx) }}><MoreHorizontal size={16} /></button></td>}
              </tr>
            )
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BudgetList({ budgets, compact = false, onDelete, onUpdate }) {
  const [editingId, setEditingId] = useState(null)
  const [editVal, setEditVal] = useState('')

  return (
    <div className="budget-list">
      {budgets.map((budget) => {
        const actual = budget.actual || 0
        const percent = budget.planned > 0 ? Math.min((actual / budget.planned) * 100, 130) : 0
        const remaining = budget.planned - actual
        const isEditing = editingId === budget.id
        return (
          <div className="budget-row" key={budget.category || budget.id}>
            <div className="budget-row-top">
              <strong>{budget.category}</strong>
              <span>
                {compact
                  ? `${fmtDollars(actual)} / ${fmtDollars(budget.planned)}`
                  : remaining >= 0
                    ? <span className="good">{fmtDollars(remaining)} remaining</span>
                    : <span className="warn">{fmtDollars(Math.abs(remaining))} over</span>
                }
              </span>
            </div>
            <div className="progress-track">
              <span
                className={remaining < 0 ? 'progress-fill over' : 'progress-fill'}
                style={{ width: `${Math.min(percent, 100)}%`, background: remaining < 0 ? undefined : budget.color }}
              />
            </div>
            {!compact && (
              <div className="budget-row-bottom">
                {isEditing ? (
                  <form onSubmit={(e) => { e.preventDefault(); onUpdate?.(budget.id, parseFloat(editVal)); setEditingId(null) }} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    <span>Planned $</span>
                    <input type="number" value={editVal} onChange={(e) => setEditVal(e.target.value)} style={{ width: 80, border: '1px solid var(--accent)', borderRadius: 3, padding: '2px 6px', minHeight: 24, background: 'var(--panel)', color: 'var(--ink)', fontSize: 12 }} autoFocus />
                    <button className="primary" type="submit" style={{ minHeight: 24, fontSize: 10, padding: '0 8px' }}>OK</button>
                  </form>
                ) : (
                  <span style={{ cursor: 'pointer' }} onClick={() => { setEditingId(budget.id); setEditVal(String(budget.planned)) }} title="Click to edit">
                    Planned {fmtDollars(budget.planned)}
                  </span>
                )}
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span>Actual {fmtDollars(actual)}</span>
                  {onDelete && (
                    <button className="icon-button tiny" type="button" onClick={() => onDelete(budget.id)} aria-label={`Delete ${budget.category} budget`}>
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function PlannedPaymentList({ payments, compact = false, onPaid, onDelete }) {
  return (
    <div className="planned-payment-list">
      {payments.map((payment) => (
        <div className="planned-payment-row" key={payment.id}>
          <div>
            <strong>{payment.name}</strong>
            <span>{fmtDate(payment.due_date)} - {payment.category}</span>
            {!compact && payment.notes && <small>{payment.notes}</small>}
          </div>
          <div className="planned-payment-actions">
            <strong>{fmtDollars(payment.amount)}</strong>
            {!compact && (
              <>
                <button className="icon-button tiny" type="button" onClick={() => onPaid?.(payment)} aria-label={`Mark ${payment.name} paid`}>
                  <CheckCircle2 size={14} />
                </button>
                <button className="icon-button tiny" type="button" onClick={() => onDelete?.(payment)} aria-label={`Delete ${payment.name}`}>
                  <Trash2 size={14} />
                </button>
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function ImportModal({ onClose, onImported }) {
  const fileRef = useRef(null)
  const [file, setFile] = useState(null)
  const [account, setAccount] = useState('')
  const [accounts, setAccounts] = useState([])
  const [stats, setStats] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [done, setDone] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    api.fetchAccounts().then((accts) => {
      setAccounts(accts)
      if (accts.length > 0) setAccount(accts[0].name)
    }).catch(() => {})
  }, [])

  function handleFile(f) {
    if (f && f.name.endsWith('.csv')) setFile(f)
  }

  async function handleImport() {
    if (!file) return
    setUploading(true)
    try {
      const result = await api.importCSV(file, account)
      setStats(result)
      setDone(true)
      onImported()
    } catch (e) {
      setStats({ error: e.message })
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="import-title">
        <div className="modal-header">
          <div>
            <p className="eyebrow">CSV Fallback</p>
            <h2 id="import-title">Import Chase Transactions</h2>
          </div>
          <button className="icon-button" type="button" aria-label="Close import" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div
          className="drop-zone"
          style={dragOver ? { borderColor: 'var(--accent)' } : {}}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]) }}
        >
          {file ? (
            <>
              <CheckCircle2 size={28} style={{ color: 'var(--good)' }} />
              <strong>{file.name}</strong>
              <span>{(file.size / 1024).toFixed(1)} KB</span>
            </>
          ) : (
            <>
              <ArrowDownToLine size={28} />
              <strong>Drop a Chase CSV file here</strong>
              <span>Expected columns: Transaction Date, Description, Amount</span>
              <button className="secondary" type="button" onClick={() => fileRef.current?.click()}>
                <Upload size={17} /> Choose file
              </button>
            </>
          )}
          <input ref={fileRef} type="file" accept=".csv" hidden onChange={(e) => handleFile(e.target.files[0])} />
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
            Account:
            <select
              value={account}
              onChange={(e) => setAccount(e.target.value)}
              style={{ background: 'var(--panel)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 7, padding: '6px 10px', font: 'inherit' }}
            >
              {accounts.map((a) => <option key={a.id} value={a.name}>{a.name}</option>)}
              {accounts.length === 0 && <option>No accounts linked</option>}
            </select>
          </label>
        </div>

        {stats && !stats.error && (
          <div className="import-preview">
            <SummaryItem label="Total rows" value={stats.total} />
            <SummaryItem label="Imported" value={stats.imported} tone="good" />
            <SummaryItem label="Duplicates" value={stats.duplicates} />
            <SummaryItem label="Need review" value={stats.need_review} tone={stats.need_review > 0 ? 'warn' : 'neutral'} />
          </div>
        )}

        {stats?.error && (
          <p style={{ color: 'var(--bad)', fontSize: 14, marginBottom: 14 }}>{stats.error}</p>
        )}

        <div className="modal-actions">
          <button className="ghost" type="button" onClick={onClose}>{done ? 'Done' : 'Cancel'}</button>
          {!done && (
            <button className="primary" type="button" disabled={!file || uploading} onClick={handleImport}>
              {uploading ? 'Importing...' : 'Import'}
            </button>
          )}
        </div>
      </section>
    </div>
  )
}

function SummaryItem({ label, value, tone = 'neutral' }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  )
}

function ConnectionRow({ title, detail, status, action, onAction }) {
  return (
    <div className="connection-row">
      <div className="connection-icon"><Landmark size={18} /></div>
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      <span className="status">{status}</span>
      <button className="secondary" type="button" onClick={onAction}>{action}</button>
    </div>
  )
}

function SettingRow({ title, detail }) {
  return (
    <div className="setting-row">
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      <button className="icon-button" type="button" aria-label={`${title} settings`}>
        <Settings size={17} />
      </button>
    </div>
  )
}

export default App
