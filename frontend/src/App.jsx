import { useEffect, useMemo, useState } from "react";
import "./App.css";

const CATEGORIES = [
  "Food", "Transport", "Shopping", "Bills",
  "Education", "Healthcare", "Other"
];

const INITIAL_BUDGET = 20000;

function loadExpenses() {
  try {
    const data = JSON.parse(localStorage.getItem("smartspend-expenses") || "[]");
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function money(amount) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(amount);
}

export default function App() {
  const [expenses, setExpenses] = useState(loadExpenses);
  const [budget] = useState(INITIAL_BUDGET);
  const [message, setMessage] = useState("");

  const [form, setForm] = useState({
    description: "",
    amount: "",
    category: "Food",
    date: new Date().toLocaleDateString("en-CA"),
  });

  useEffect(() => {
    try {
      localStorage.setItem("smartspend-expenses", JSON.stringify(expenses));
    } catch {
      setMessage("Browser storage is unavailable or full.");
    }
  }, [expenses]);

  const total = useMemo(
    () => expenses.reduce((sum, expense) => sum + expense.amount, 0),
    [expenses]
  );

  const categoryTotals = useMemo(() => {
    return expenses.reduce((totals, expense) => {
      totals[expense.category] =
        (totals[expense.category] || 0) + expense.amount;
      return totals;
    }, {});
  }, [expenses]);

  function updateField(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  function addExpense(event) {
    event.preventDefault();

    const description = form.description.trim();
    const amount = Number(form.amount);

    if (!description || !Number.isFinite(amount) || amount <= 0 || !form.date) {
      setMessage("Please enter valid expense details.");
      return;
    }

    setExpenses((previous) => [
      {
        id: crypto.randomUUID(),
        description,
        amount,
        category: form.category,
        date: form.date,
      },
      ...previous,
    ]);

    setForm({
      description: "",
      amount: "",
      category: "Food",
      date: new Date().toLocaleDateString("en-CA"),
    });

    setMessage("Expense added successfully.");
  }

  function deleteExpense(id) {
    setExpenses((previous) => previous.filter((expense) => expense.id !== id));
    setMessage("Expense deleted.");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-icon">S</span> SmartSpend</div>
        <p className="nav-label">WORKSPACE</p>
        <nav>
          <a className="nav-link active" href="#dashboard">▦ &nbsp; Dashboard</a>
          <a className="nav-link" href="#expenses">↗ &nbsp; Expenses</a>
          <a className="nav-link" href="#budgets">◎ &nbsp; Budgets</a>
          <a className="nav-link" href="#analytics">▥ &nbsp; Analytics</a>
        </nav>
        <div className="sidebar-bottom">
          <div className="profile-avatar">SS</div>
          <div><strong>Personal Account</strong><small>Expense management</small></div>
        </div>
      </aside>

      <main className="main-content" id="dashboard">
        <header className="topbar">
          <div>
            <p className="eyebrow">OVERVIEW</p>
            <h1>Dashboard</h1>
            <p className="muted">Track your money. Make smarter decisions.</p>
          </div>
          <span className="preview-badge"><span /> Frontend Preview</span>
        </header>

        <section className="welcome-panel">
          <div>
            <p className="welcome-label">YOUR FINANCES, SIMPLIFIED</p>
            <h2>Take control of your spending.</h2>
            <p>Every expense tells a story. Start tracking yours today.</p>
          </div>
          <div className="welcome-symbol">₹</div>
        </section>

        <section className="stats-grid">
          <article className="stat-card">
            <div className="stat-heading"><span>Total expenses</span><span className="stat-icon purple">↗</span></div>
            <h2>{money(total)}</h2>
            <p className="muted">All expenses recorded</p>
          </article>
          <article className="stat-card">
            <div className="stat-heading"><span>Monthly budget</span><span className="stat-icon blue">◎</span></div>
            <h2>{money(budget)}</h2>
            <p className="muted">Demo budget</p>
          </article>
          <article className="stat-card">
            <div className="stat-heading"><span>Budget remaining</span><span className="stat-icon green">✓</span></div>
            <h2 className={budget - total < 0 ? "negative" : ""}>{money(budget - total)}</h2>
            <div className="progress-track">
              <div
                className="progress-value"
                style={{ width: `${Math.min((total / budget) * 100, 100)}%` }}
              />
            </div>
            <p className="muted">{budget > 0 ? Math.round((total / budget) * 100) : 0}% of demo budget used</p>
          </article>
        </section>

        <div className="content-grid">
          <section className="panel" id="expenses">
            <div className="panel-heading">
              <div><h2>Add an expense</h2><p>Record a new transaction.</p></div>
              <span className="panel-symbol">＋</span>
            </div>

            <form onSubmit={addExpense}>
              <label htmlFor="description">Description</label>
              <input id="description" name="description" value={form.description}
                onChange={updateField} placeholder="e.g. Grocery shopping" maxLength={100} required />

              <div className="form-row">
                <div>
                  <label htmlFor="amount">Amount (₹)</label>
                  <input id="amount" name="amount" type="number" min="0.01" step="0.01"
                    value={form.amount} onChange={updateField} placeholder="500" required />
                </div>
                <div>
                  <label htmlFor="category">Category</label>
                  <select id="category" name="category" value={form.category} onChange={updateField}>
                    {CATEGORIES.map((category) => <option key={category}>{category}</option>)}
                  </select>
                </div>
              </div>

              <label htmlFor="date">Date</label>
              <input id="date" name="date" type="date" value={form.date} onChange={updateField} required />

              <button className="primary-button" type="submit">＋ Add expense</button>
              <p className="form-message" role="status">{message}</p>
            </form>
          </section>

          <section className="panel" id="analytics">
            <div className="panel-heading">
              <div><h2>Spending breakdown</h2><p>Expenses by category.</p></div>
              <span className="panel-symbol">▥</span>
            </div>

            {Object.keys(categoryTotals).length === 0 ? (
              <div className="empty-chart">
                <div className="empty-chart-icon">▥</div>
                <strong>No spending data yet</strong>
                <p>Add your first expense to see your breakdown.</p>
              </div>
            ) : (
              <div className="category-list">
                {Object.entries(categoryTotals)
                  .sort((a, b) => b[1] - a[1])
                  .map(([category, amount], index) => (
                    <div className="category-row" key={category}>
                      <div className="category-info">
                        <span className={`category-dot dot-${index % 5}`} />
                        <span>{category}</span>
                        <strong>{money(amount)}</strong>
                      </div>
                      <div className="progress-track">
                        <div className={`category-progress bar-${index % 5}`}
                          style={{ width: `${total ? (amount / total) * 100 : 0}%` }} />
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </section>
        </div>

        <section className="panel transactions-panel" id="budgets">
          <div className="panel-heading">
            <div><h2>Recent transactions</h2><p>Your latest recorded expenses.</p></div>
            <span className="transaction-count">{expenses.length} records</span>
          </div>

          <div className="table-wrapper">
            <table>
              <thead><tr><th>Description</th><th>Category</th><th>Date</th><th>Amount</th><th>Action</th></tr></thead>
              <tbody>
                {expenses.length === 0 ? (
                  <tr><td colSpan="5" className="empty-table">No transactions yet. Add your first expense above.</td></tr>
                ) : expenses.map((expense) => (
                  <tr key={expense.id}>
                    <td><strong>{expense.description}</strong></td>
                    <td><span className="category-pill">{expense.category}</span></td>
                    <td>{expense.date}</td>
                    <td className="amount-cell">{money(expense.amount)}</td>
                    <td><button className="delete-button" type="button"
                      onClick={() => deleteExpense(expense.id)} aria-label={`Delete ${expense.description}`}>Delete</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <footer>SmartSpend <span>•</span> Personal Expense Analytics Platform</footer>
      </main>
    </div>
  );
}
