# Investment Dashboard — Setup

Runs entirely on your own computer at `http://localhost:8501`.
Nothing is uploaded anywhere; your API keys stay in a local file.

---

## One-time setup (~10 minutes)

### 1. Install Python
Get Python 3.12 or newer (Windows): https://python.org

**Important:** during install, tick **"Add Python to PATH"**. If you miss it,
the scripts below won't find Python.

### 2. Get your API keys (all free)

The dashboard runs without any keys, but AI and macro features stay disabled.
Get your **own** keys — don't reuse someone else's, or you'll share their
daily limits and, for Anthropic, their bill.

| Key | What it powers | Where | Free tier |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Expert Panel, Panel Verdict, Macro, AI Screener | https://console.anthropic.com | **paid per use** |
| `FRED_API_KEY` | Market Health (rates, CPI, yield curve) | https://fred.stlouisfed.org/docs/api/api_key.html | free |
| `FINNHUB_API_KEY` | Analyst ratings, price targets, insider data | https://finnhub.io | 60 calls/min |
| `ALPHA_VANTAGE_API_KEY` | News sentiment scores | https://www.alphavantage.co/support/#api-key | **25/day** |
| `FMP_API_KEY` | Rating actions, Congress trades | https://site.financialmodelingprep.com/developer/docs | 250/day |
| `SEC_CONTACT_EMAIL` | Your own email, sent only to sec.gov (13F tracker asks API users to identify themselves) | — | not a key |

> **Anthropic costs real money per request.** It's the only paid one. The
> Expert Panel is a single batched call per stock (cached 2 hours), so normal
> use is cheap — but it is not free. Set a spend limit in the console.
> Skip this key entirely if you only want the non-AI features.

### 3. Run setup

Double-click **`setup_and_run.bat`**

It checks Python, creates your `.env` from the template, opens it in Notepad
so you can paste your keys, installs all packages into a private folder
(`%LOCALAPPDATA%\InvestmentDashboard\venv`; your system Python is not modified), and launches the dashboard.

Paste each key after the `=` with no quotes and no spaces:

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
```

Save, close Notepad, press any key in the black window.

First run takes 1–2 minutes to install packages. Browser opens automatically.

---

## Make it always-on (optional but recommended)

So you never have to start it manually:

Double-click **`install_autostart.bat`**

- Starts automatically at every Windows login
- Runs hidden in the background (no console window)
- Restarts itself automatically if it ever crashes
- Always available at **http://localhost:8501**

Bookmark `http://localhost:8501` and it behaves like any website — except it's
running on your own machine.

To turn it off later: **`uninstall_autostart.bat`**

---

## Daily use

Open **http://localhost:8501** in any browser.

If the page doesn't load:
1. Wait ~15 seconds (it may still be starting)
2. Refresh
3. Still nothing? Double-click `setup_and_run.bat` and watch for errors

---

## Notes

- **Data is delayed**, not real-time. Sourced from Yahoo Finance. Don't trade
  off a live price here.
- **Not investment advice.** Scores, AI opinions, and DCF valuations are
  research aids built on assumptions you can change in the UI.
- If a key's daily limit runs out, that section shows a message and the rest of
  the dashboard keeps working.
- `.env` holds your keys — never share or upload that file.
- The dashboard listens on `127.0.0.1` only: other devices on your network cannot open it.
- It saves your watchlist, portfolios and alerts as small `.json` files in this folder.
