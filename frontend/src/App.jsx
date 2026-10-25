import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./App.css";

const API_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const BUDGET_URL =
  import.meta.env.VITE_BUDGET_API_URL || "http://127.0.0.1:8001";
const ANALYTICS_URL =
  import.meta.env.VITE_ANALYTICS_API_URL || "http://127.0.0.1:8002";
const ALERT_URL = import.meta.env.VITE_ALERT_API_URL || "http://127.0.0.1:8003";
const SAVINGS_URL =
  import.meta.env.VITE_SAVINGS_API_URL || "http://127.0.0.1:8004";

const CATEGORIES = [
  "Food",
  "Transport",
  "Shopping",
  "Bills",
  "Education",
  "Healthcare",
  "Other",
];
const CHART_COLORS = ["#7867e9", "#36a4da", "#3cb89a", "#e5a347", "#e879a5"];

function currentMonth() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function today() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function money(amount = 0) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number(amount) || 0);
}

function requestKey() {
  return crypto.randomUUID();
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      const text = await response.text();
      if (text) detail = text;
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const day = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{day.date}</strong>
      {day.transactions.map((transaction) => (
        <p key={transaction.id}>
          {transaction.description} · {transaction.category} ·{" "}
          {money(transaction.amount)}
        </p>
      ))}
      <b>Daily total: {money(day.total_spending)}</b>
    </div>
  );
}

function YearTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{payload[0].payload.month_name}</strong>
      <p>Spending: {money(payload[0].value)}</p>
      <p>{payload[0].payload.transaction_count} transactions</p>
    </div>
  );
}

export default function App() {
  const [month, setMonth] = useState(currentMonth);
  const [year, setYear] = useState(Number(currentMonth().slice(0, 4)));
  const [reloadToken, setReloadToken] = useState(0);
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [daily, setDaily] = useState([]);
  const [categories, setCategories] = useState([]);
  const [yearly, setYearly] = useState(null);
  const [budget, setBudget] = useState(null);
  const [allocations, setAllocations] = useState(0);
  const [alerts, setAlerts] = useState([]);
  const [wallet, setWallet] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [goals, setGoals] = useState([]);
  const [expenseError, setExpenseError] = useState("");
  const [analyticsError, setAnalyticsError] = useState("");
  const [budgetError, setBudgetError] = useState("");
  const [yearlyError, setYearlyError] = useState("");
  const [savingsError, setSavingsError] = useState("");
  const [alertError, setAlertError] = useState("");
  const [expenseLoading, setExpenseLoading] = useState(true);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [budgetLoading, setBudgetLoading] = useState(true);
  const [yearlyLoading, setYearlyLoading] = useState(false);
  const [savingsLoading, setSavingsLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState("");
  const [expenseForm, setExpenseForm] = useState({
    description: "",
    amount: "",
    category: "Food",
    date: today(),
  });
  const [budgetAmount, setBudgetAmount] = useState("");
  const [allocationAmount, setAllocationAmount] = useState("");
  const [walletAmount, setWalletAmount] = useState("");
  const [goalAmount, setGoalAmount] = useState("");
  const [goalForm, setGoalForm] = useState({
    name: "",
    target_amount: "",
    target_date: "",
  });

  useEffect(() => {
    let active = true;
    setExpenseLoading(true);
    setAnalyticsLoading(true);
    setBudgetLoading(true);
    setSavingsLoading(true);
    setExpenseError("");
    setAnalyticsError("");
    setBudgetError("");
    setSavingsError("");
    setAlertError("");

    const loadExpenses = request(
      `${API_URL}/expenses?month=${encodeURIComponent(month)}&limit=2000`,
    )
      .then((data) => {
        if (active) setExpenses(data);
      })
      .catch((error) => {
        if (active) setExpenseError(error.message);
      })
      .finally(() => {
        if (active) setExpenseLoading(false);
      });

    const loadAnalytics = Promise.all([
      request(`${ANALYTICS_URL}/analytics/summary?month=${month}`),
      request(`${ANALYTICS_URL}/analytics/categories?month=${month}`),
      request(`${ANALYTICS_URL}/analytics/daily?month=${month}`),
    ])
      .then(([monthlySummary, categorySummary, dailySummary]) => {
        if (!active) return;
        setSummary(monthlySummary);
        setCategories(categorySummary.categories);
        setDaily(dailySummary.daily);
      })
      .catch((error) => {
        if (active) setAnalyticsError(error.message);
      })
      .finally(() => {
        if (active) setAnalyticsLoading(false);
      });

    const loadBudget = request(`${BUDGET_URL}/monthly-budgets/${month}`)
      .then((data) => {
        if (!active) return;
        setBudget(data);
        setBudgetAmount(String(data.amount));
      })
      .catch((error) => {
        if (!active) return;
        if (error.status === 404) {
          setBudget(null);
          setBudgetAmount("");
        } else {
          setBudgetError(error.message);
        }
      })
      .finally(() => {
        if (active) setBudgetLoading(false);
      });

    const loadAllocations = request(
      `${SAVINGS_URL}/savings/allocations?month=${month}`,
    )
      .then((data) => {
        if (active) setAllocations(data.allocated);
      })
      .catch((error) => {
        if (active) setSavingsError(error.message);
      });

    const loadAlerts = request(`${ALERT_URL}/alerts?month=${month}`)
      .then((data) => {
        if (active) setAlerts(data.alerts);
      })
      .catch((error) => {
        if (active) setAlertError(error.message);
      });

    const loadSavings = Promise.all([
      request(`${SAVINGS_URL}/savings/balance`),
      request(`${SAVINGS_URL}/savings/transactions?limit=50`),
      request(`${SAVINGS_URL}/savings/goals`),
    ])
      .then(([balance, history, goalList]) => {
        if (!active) return;
        setWallet(balance);
        setTransactions(history.transactions);
        setGoals(goalList);
      })
      .catch((error) => {
        if (active) setSavingsError(error.message);
      })
      .finally(() => {
        if (active) setSavingsLoading(false);
      });

    Promise.all([
      loadExpenses,
      loadAnalytics,
      loadBudget,
      loadAllocations,
      loadAlerts,
      loadSavings,
    ]);
    return () => {
      active = false;
    };
  }, [month, reloadToken]);

  useEffect(() => {
    let active = true;
    setYearlyLoading(true);
    setYearlyError("");
    request(`${ANALYTICS_URL}/analytics/yearly?year=${year}`)
      .then((data) => {
        if (active) setYearly(data);
      })
      .catch((error) => {
        if (active) setYearlyError(error.message);
      })
      .finally(() => {
        if (active) setYearlyLoading(false);
      });
    return () => {
      active = false;
    };
  }, [year, reloadToken]);

  const total = summary?.total_spending ?? 0;
  const remaining = budget ? Number(budget.amount) - total : null;
  const utilization = budget ? (total / Number(budget.amount)) * 100 : null;
  const unallocated = budget
    ? Math.max(Number(budget.amount) - total - allocations, 0)
    : null;
  const monthlyTrend = useMemo(
    () => daily.map((day) => ({ ...day, date: day.date })),
    [daily],
  );

  function refreshData() {
    setReloadToken((value) => value + 1);
  }

  async function submitExpense(event) {
    event.preventDefault();
    setPending("expense");
    setMessage("");
    try {
      await request(`${API_URL}/expenses`, {
        method: "POST",
        body: JSON.stringify({
          ...expenseForm,
          description: expenseForm.description.trim(),
          amount: Number(expenseForm.amount),
        }),
      });
      setExpenseForm({
        description: "",
        amount: "",
        category: "Food",
        date: today(),
      });
      setMessage("Expense saved.");
      refreshData();
    } catch (error) {
      setMessage(`Could not add expense: ${error.message}`);
    } finally {
      setPending("");
    }
  }

  async function deleteExpense(id) {
    setPending(`delete-${id}`);
    setMessage("");
    try {
      await request(`${API_URL}/expenses/${id}`, { method: "DELETE" });
      setMessage("Expense deleted.");
      refreshData();
    } catch (error) {
      setMessage(`Could not delete expense: ${error.message}`);
    } finally {
      setPending("");
    }
  }

  async function saveBudget(event) {
    event.preventDefault();
    const amount = Number(budgetAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setMessage("Enter a positive budget amount.");
      return;
    }
    setPending("budget");
    setMessage("");
    try {
      await request(
        budget
          ? `${BUDGET_URL}/monthly-budgets/${month}`
          : `${BUDGET_URL}/monthly-budgets`,
        {
          method: budget ? "PUT" : "POST",
          body: JSON.stringify(
            budget ? { amount } : { month, amount },
          ),
        },
      );
      setMessage(budget ? "Monthly budget updated." : "Monthly budget created.");
      refreshData();
    } catch (error) {
      setMessage(`Could not save budget: ${error.message}`);
      if (error.status === 409) refreshData();
    } finally {
      setPending("");
    }
  }

  async function allocateSavings(event) {
    event.preventDefault();
    setPending("allocation");
    setMessage("");
    try {
      await request(`${SAVINGS_URL}/savings/allocate`, {
        method: "POST",
        body: JSON.stringify({
          month,
          amount: Number(allocationAmount),
          note: `Monthly savings allocation for ${month}`,
          idempotency_key: requestKey(),
        }),
      });
      setAllocationAmount("");
      setMessage("Funds allocated to savings.");
      refreshData();
    } catch (error) {
      setMessage(`Could not allocate savings: ${error.message}`);
    } finally {
      setPending("");
    }
  }

  async function walletTransaction(type, event) {
    event.preventDefault();
    setPending(type);
    setMessage("");
    try {
      await request(`${SAVINGS_URL}/savings/${type}`, {
        method: "POST",
        body: JSON.stringify({
          amount: Number(walletAmount),
          note: type === "deposit" ? "Savings wallet deposit" : "Savings withdrawal",
          idempotency_key: requestKey(),
        }),
      });
      setWalletAmount("");
      setMessage(type === "deposit" ? "Savings deposited." : "Withdrawal recorded.");
      refreshData();
    } catch (error) {
      setMessage(`Could not complete savings transaction: ${error.message}`);
    } finally {
      setPending("");
    }
  }

  async function createGoal(event) {
    event.preventDefault();
    setPending("goal");
    setMessage("");
    try {
      await request(`${SAVINGS_URL}/savings/goals`, {
        method: "POST",
        body: JSON.stringify({
          name: goalForm.name.trim(),
          target_amount: Number(goalForm.target_amount),
          target_date: goalForm.target_date || null,
        }),
      });
      setGoalForm({ name: "", target_amount: "", target_date: "" });
      setMessage("Savings goal created.");
      refreshData();
    } catch (error) {
      setMessage(`Could not create savings goal: ${error.message}`);
    } finally {
      setPending("");
    }
  }

  async function updateGoal(goalId, operation) {
    const amount = Number(goalAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setMessage("Enter a positive goal transaction amount.");
      return;
    }
    setPending(`goal-${goalId}`);
    setMessage("");
    try {
      await request(`${SAVINGS_URL}/savings/goals/${goalId}/${operation}`, {
        method: "POST",
        body: JSON.stringify({
          amount,
          idempotency_key: requestKey(),
          note: operation === "contribute" ? "Goal contribution" : "Goal withdrawal",
        }),
      });
      setGoalAmount("");
      setMessage(
        operation === "contribute"
          ? "Goal contribution recorded."
          : "Goal withdrawal recorded.",
      );
      refreshData();
    } catch (error) {
      setMessage(`Could not update goal: ${error.message}`);
    } finally {
      setPending("");
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">S</span> SmartSpend
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          <a className="nav-link active" href="#dashboard">▦ &nbsp; Dashboard</a>
          <a className="nav-link" href="#expenses">↗ &nbsp; Expenses</a>
          <a className="nav-link" href="#monthly-analytics">▥ &nbsp; Monthly Analytics</a>
          <a className="nav-link" href="#yearly-analytics">▤ &nbsp; Yearly Analytics</a>
          <a className="nav-link" href="#savings">◉ &nbsp; Savings</a>
        </nav>
        <div className="sidebar-bottom">
          <div className="profile-avatar">SS</div>
          <div>
            <strong>Personal Account</strong>
            <small>Expense management</small>
          </div>
        </div>
      </aside>

      <main className="main-content" id="dashboard">
        <header className="topbar">
          <div>
            <p className="eyebrow">OVERVIEW</p>
            <h1>Dashboard</h1>
            <p className="muted">Track your money. Make smarter decisions.</p>
          </div>
          <label className="month-picker">
            <span>Selected month</span>
            <input
              aria-label="Selected month"
              type="month"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
            />
          </label>
        </header>

        {message && <p className="form-message" role="status">{message}</p>}

        {alertError ? (
          <section className="notice error-notice" role="alert">
            <span>Alerts unavailable: {alertError}</span>
            <button type="button" onClick={refreshData}>Retry</button>
          </section>
        ) : alerts.length > 0 ? (
          <section className="notice warning-notice" aria-label="Budget alerts">
            {alerts.map((alert, index) => (
              <p key={`${alert.type}-${alert.category || index}`}>
                {alert.message}: {money(alert.spent)} of {money(alert.budget)} ({alert.percentage_used}%)
              </p>
            ))}
          </section>
        ) : null}

        <section className="welcome-panel">
          <div>
            <p className="welcome-label">YOUR FINANCES, SIMPLIFIED</p>
            <h2>Take control of your spending.</h2>
            <p>Every expense tells a story. Start tracking yours today.</p>
          </div>
          <div className="welcome-symbol">₹</div>
        </section>

        <section className="stats-grid" aria-label="Monthly overview">
          <article className="stat-card">
            <div className="stat-heading"><span>Monthly spending</span><span className="stat-icon purple">↗</span></div>
            <h2>{analyticsLoading ? "Loading…" : money(total)}</h2>
            <p className="muted">{summary?.transaction_count ?? "—"} transactions in {month}</p>
          </article>
          <article className="stat-card">
            <div className="stat-heading"><span>Monthly budget</span><span className="stat-icon blue">◉</span></div>
            <h2>{budgetLoading ? "Loading…" : budget ? money(budget.amount) : "Not set"}</h2>
            <p className="muted">{budget ? `Saved budget for ${month}` : "Set a budget for this month"}</p>
          </article>
          <article className="stat-card">
            <div className="stat-heading"><span>Budget remaining</span><span className="stat-icon green">✓</span></div>
            <h2 className={remaining !== null && remaining < 0 ? "negative" : ""}>
              {budgetLoading ? "Loading…" : remaining === null ? "—" : money(remaining)}
            </h2>
            {budget && (
              <>
                <div className="progress-track">
                  <div className="progress-value" style={{ width: `${Math.min(Math.max(utilization, 0), 100)}%` }} />
                </div>
                <p className="muted">{utilization.toFixed(1)}% utilized</p>
              </>
            )}
          </article>
        </section>

        <div className="content-grid">
          <section className="panel" id="budgets">
            <div className="panel-heading">
              <div><h2>{budget ? "Edit monthly budget" : "Set monthly budget"}</h2><p>One saved budget for {month}.</p></div>
              <span className="panel-symbol">◉</span>
            </div>
            {budgetError ? (
              <ErrorState message={budgetError} onRetry={refreshData} />
            ) : budgetLoading ? (
              <p className="muted" role="status">Loading saved budget…</p>
            ) : (
              <form onSubmit={saveBudget}>
                <label htmlFor="budget-amount">Budget amount (₹)</label>
                <input
                  id="budget-amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={budgetAmount}
                  onChange={(event) => setBudgetAmount(event.target.value)}
                  required
                />
                <button className="primary-button" type="submit" disabled={pending === "budget"}>
                  {pending === "budget" ? "Saving…" : budget ? "Update budget" : "Create budget"}
                </button>
              </form>
            )}
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div><h2>Monthly summary</h2><p>Actual activity for the selected month.</p></div>
              <span className="panel-symbol">₹</span>
            </div>
            {analyticsError ? (
              <ErrorState message={analyticsError} onRetry={refreshData} />
            ) : analyticsLoading ? (
              <p className="muted" role="status">Loading monthly analytics…</p>
            ) : (
              <div className="summary-list">
                <div><span>Total spending</span><strong>{money(total)}</strong></div>
                <div><span>Transactions</span><strong>{summary?.transaction_count ?? 0}</strong></div>
                <div><span>Average transaction</span><strong>{money(summary?.average_expense ?? 0)}</strong></div>
                <div><span>Savings allocated</span><strong>{money(allocations)}</strong></div>
                <div><span>Unallocated budget</span><strong>{unallocated === null ? "—" : money(unallocated)}</strong></div>
              </div>
            )}
          </section>
        </div>

        <section className="panel transactions-panel" id="expenses">
          <div className="panel-heading">
            <div><h2>Expenses</h2><p>Add a transaction or review expenses in {month}.</p></div>
            <span className="transaction-count">{expenses.length} records</span>
          </div>
          <form className="expense-form" onSubmit={submitExpense}>
            <div>
              <label htmlFor="description">Description</label>
              <input id="description" value={expenseForm.description} maxLength="100" required
                onChange={(event) => setExpenseForm({ ...expenseForm, description: event.target.value })} />
            </div>
            <div>
              <label htmlFor="expense-amount">Amount (₹)</label>
              <input id="expense-amount" type="number" min="0.01" step="0.01" value={expenseForm.amount} required
                onChange={(event) => setExpenseForm({ ...expenseForm, amount: event.target.value })} />
            </div>
            <div>
              <label htmlFor="category">Category</label>
              <select id="category" value={expenseForm.category}
                onChange={(event) => setExpenseForm({ ...expenseForm, category: event.target.value })}>
                {CATEGORIES.map((category) => <option key={category}>{category}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="expense-date">Date</label>
              <input id="expense-date" type="date" value={expenseForm.date} required
                onChange={(event) => setExpenseForm({ ...expenseForm, date: event.target.value })} />
            </div>
            <button className="primary-button" type="submit" disabled={pending === "expense"}>
              {pending === "expense" ? "Saving…" : "Add expense"}
            </button>
          </form>
          {expenseError ? <ErrorState message={expenseError} onRetry={refreshData} /> : expenseLoading ? (
            <p className="muted" role="status">Loading expenses…</p>
          ) : expenses.length === 0 ? (
            <div className="empty-state">No expenses recorded for {month}.</div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead><tr><th>Description</th><th>Category</th><th>Date</th><th>Amount</th><th>Action</th></tr></thead>
                <tbody>{expenses.map((expense) => (
                  <tr key={expense.id}>
                    <td><strong>{expense.description}</strong></td>
                    <td><span className="category-pill">{expense.category}</span></td>
                    <td>{expense.date}</td>
                    <td className="amount-cell">{money(expense.amount)}</td>
                    <td><button className="delete-button" type="button" disabled={pending === `delete-${expense.id}`}
                      onClick={() => deleteExpense(expense.id)} aria-label={`Delete ${expense.description}`}>
                      {pending === `delete-${expense.id}` ? "Deleting…" : "Delete"}
                    </button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel analytics-panel" id="monthly-analytics">
          <div className="panel-heading">
            <div><h2>Monthly Analytics</h2><p>Daily spending with transaction-level details.</p></div>
            <label className="inline-picker">Month
              <input aria-label="Analytics month" type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
            </label>
          </div>
          {analyticsError ? <ErrorState message={analyticsError} onRetry={refreshData} /> : analyticsLoading ? (
            <p className="muted" role="status">Loading monthly charts…</p>
          ) : daily.length === 0 ? (
            <div className="empty-state">No spending data for {month}. Add an expense to see the trend.</div>
          ) : (
            <>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={monthlyTrend} margin={{ top: 12, right: 16, left: 8, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#edf0f5" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={25} />
                    <YAxis tick={{ fontSize: 10 }} tickFormatter={(value) => `₹${value}`} width={75} />
                    <Tooltip content={<ChartTooltip />} />
                    <Line type="monotone" dataKey="total_spending" name="Daily spending"
                      stroke="#6c5ce7" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 6 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <h3 className="chart-subtitle">Category breakdown</h3>
              {categories.length === 0 ? <p className="muted">No category totals available.</p> : (
                <div className="chart-container category-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={categories} dataKey="total_spending" nameKey="category"
                        cx="50%" cy="50%" outerRadius="78%" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                        {categories.map((entry, index) => <Cell key={entry.category} fill={CHART_COLORS[index % CHART_COLORS.length]} />)}
                      </Pie>
                      <Tooltip formatter={(value) => money(value)} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          )}
        </section>

        <section className="panel analytics-panel" id="yearly-analytics">
          <div className="panel-heading">
            <div><h2>Yearly Analytics</h2><p>Calendar-year spending from January through December.</p></div>
            <label className="inline-picker">Year
              <input aria-label="Analytics year" type="number" min="2000" max="2100" value={year}
                onChange={(event) => setYear(Number(event.target.value))} />
            </label>
          </div>
          {yearlyError ? <ErrorState message={yearlyError} onRetry={refreshData} /> : yearlyLoading ? (
            <p className="muted" role="status">Loading yearly analytics…</p>
          ) : yearly ? (
            <>
              <div className="year-stats">
                <div><span>Total yearly spending</span><strong>{money(yearly.total_spending)}</strong></div>
                <div><span>Average per calendar month</span><strong>{money(yearly.average_monthly_spending)}</strong></div>
                <div><span>Highest-spending month</span><strong>{yearly.highest_spending_month
                  ? `${yearly.months.find((entry) => entry.month === yearly.highest_spending_month)?.month_name} · ${money(yearly.highest_spending_amount)}`
                  : "No spending"}</strong></div>
              </div>
              {yearly.total_spending === 0 ? <div className="empty-state">No spending data for {year}.</div> : (
                <div className="chart-container">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={yearly.months} margin={{ top: 12, right: 16, left: 8, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#edf0f5" />
                      <XAxis dataKey="month_name" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} tickFormatter={(value) => `₹${value}`} width={75} />
                      <Tooltip content={<YearTooltip />} />
                      <Bar dataKey="total_spending" name="Monthly spending" fill="#6c5ce7" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              <h3 className="chart-subtitle">Yearly category comparison</h3>
              {yearly.categories.length === 0 ? <p className="muted">No category totals available.</p> : (
                <div className="chart-container category-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={yearly.categories} layout="vertical" margin={{ top: 4, right: 24, left: 20, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#edf0f5" />
                      <XAxis type="number" tick={{ fontSize: 10 }} tickFormatter={(value) => `₹${value}`} />
                      <YAxis type="category" dataKey="category" tick={{ fontSize: 10 }} width={90} />
                      <Tooltip formatter={(value) => money(value)} />
                      <Bar dataKey="total_spending" fill="#36a4da" radius={[0, 5, 5, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          ) : <div className="empty-state">Yearly analytics is unavailable.</div>}
        </section>

        <section className="panel savings-panel" id="savings">
          <div className="panel-heading">
            <div><h2>Savings wallet & goals</h2><p>Only explicit ledger transactions change the savings balance.</p></div>
            <span className="transaction-count">{savingsLoading ? "Loading…" : `Balance ${money(wallet?.balance ?? 0)}`}</span>
          </div>
          {savingsError && <ErrorState message={savingsError} onRetry={refreshData} />}
          <div className="savings-columns">
            <div>
              <h3>Allocate monthly funds</h3>
              {!budget && !budgetLoading ? <p className="muted">Set a monthly budget before allocating unspent funds.</p> : (
                <form onSubmit={allocateSavings}>
                  <p className="muted">Unallocated for {month}: {unallocated === null ? "—" : money(unallocated)}</p>
                  <label htmlFor="allocation-amount">Amount to allocate (₹)</label>
                  <input id="allocation-amount" type="number" min="0.01" step="0.01" max={unallocated ?? undefined}
                    value={allocationAmount} required onChange={(event) => setAllocationAmount(event.target.value)} />
                  <button className="primary-button" type="submit" disabled={pending === "allocation" || !budget || !unallocated}>
                    {pending === "allocation" ? "Allocating…" : "Allocate to savings"}
                  </button>
                </form>
              )}
              <h3 className="spaced-heading">Wallet transaction</h3>
              <label htmlFor="wallet-amount">Amount (₹)</label>
              <input id="wallet-amount" type="number" min="0.01" step="0.01" value={walletAmount}
                onChange={(event) => setWalletAmount(event.target.value)} />
              <div className="button-row">
                <button className="primary-button" disabled={pending === "deposit" || !walletAmount}
                  onClick={(event) => walletTransaction("deposit", event)}>Deposit</button>
                <button className="secondary-button" disabled={pending === "withdraw" || !walletAmount}
                  onClick={(event) => walletTransaction("withdraw", event)}>Withdraw</button>
              </div>
            </div>

            <div>
              <h3>Create savings goal</h3>
              <form onSubmit={createGoal}>
                <label htmlFor="goal-name">Goal name</label>
                <input id="goal-name" value={goalForm.name} maxLength="100" required
                  onChange={(event) => setGoalForm({ ...goalForm, name: event.target.value })} />
                <label htmlFor="goal-target">Target amount (₹)</label>
                <input id="goal-target" type="number" min="0.01" step="0.01" value={goalForm.target_amount} required
                  onChange={(event) => setGoalForm({ ...goalForm, target_amount: event.target.value })} />
                <label htmlFor="goal-date">Target date (optional)</label>
                <input id="goal-date" type="date" value={goalForm.target_date}
                  onChange={(event) => setGoalForm({ ...goalForm, target_date: event.target.value })} />
                <button className="primary-button" type="submit" disabled={pending === "goal"}>
                  {pending === "goal" ? "Creating…" : "Create goal"}
                </button>
              </form>
            </div>
          </div>

          <h3 className="spaced-heading">Goals</h3>
          {goals.length === 0 ? <div className="empty-state">No savings goals yet.</div> : (
            <>
              <label className="goal-amount-label" htmlFor="goal-transaction-amount">Contribution or withdrawal amount (₹)</label>
              <input className="goal-amount-input" id="goal-transaction-amount" type="number" min="0.01" step="0.01"
                value={goalAmount} onChange={(event) => setGoalAmount(event.target.value)} />
              <div className="goal-list">
                {goals.map((goal) => (
                  <article className="goal-card" key={goal.id}>
                    <div className="goal-title"><strong>{goal.name}</strong><span>{money(goal.current_amount)} / {money(goal.target_amount)}</span></div>
                    <div className="progress-track"><div className="progress-value" style={{ width: `${Math.min(goal.progress_pct, 100)}%` }} /></div>
                    <p className="muted">{goal.target_date ? `Target date: ${goal.target_date}` : "No target date"}</p>
                    <div className="button-row">
                      <button className="primary-button" disabled={pending === `goal-${goal.id}` || !goalAmount}
                        onClick={() => updateGoal(goal.id, "contribute")}>Contribute</button>
                      <button className="secondary-button" disabled={pending === `goal-${goal.id}` || !goalAmount || goal.current_amount <= 0}
                        onClick={() => updateGoal(goal.id, "withdraw")}>Withdraw</button>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}

          <h3 className="spaced-heading">Savings activity</h3>
          {transactions.length === 0 ? <div className="empty-state">No savings transactions recorded.</div> : (
            <div className="table-wrapper">
              <table>
                <thead><tr><th>Type</th><th>Details</th><th>Date</th><th>Amount</th></tr></thead>
                <tbody>{transactions.map((transaction) => (
                  <tr key={`${transaction.type}-${transaction.id}`}>
                    <td><span className="category-pill">{transaction.type.replaceAll("_", " ")}</span></td>
                    <td>{transaction.note || transaction.month || "—"}</td>
                    <td>{transaction.created_at.slice(0, 10)}</td>
                    <td className="amount-cell">{money(transaction.amount)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </section>

        <footer>SmartSpend <span>•</span> Personal Finance Analytics Platform</footer>
      </main>
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="error-state" role="alert">
      <span>{message}</span>
      <button type="button" onClick={onRetry}>Retry</button>
    </div>
  );
}
