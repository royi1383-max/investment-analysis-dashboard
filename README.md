# Investment Analysis Dashboard

A growth-focused stock & ETF research tool built with Python and Streamlit. Combines market data, fundamentals, technicals, and macro context into a single interactive dashboard, with an AI-assisted screener and expert-panel view powered by the Claude API.

> Personal research project — not financial advice.

## Features

- **Fundamental & technical analysis** — scoring, momentum, seasonality, risk metrics
- **Sector & market context** — sector strength/comparison, market health, macro/geo impact
- **Institutional & insider data** — SEC 13F filings, institutional holdings
- **Options & analyst data** — options flow, earnings, analyst estimates (via Finnhub)
- **AI-assisted tools** — AI stock screener and an "expert panel" view using the Anthropic API
- **Portfolio tools** — paper portfolio simulation, portfolio health checks, price alerts, backtesting
- **Weekly picks** — a recurring screen for candidate ideas

## Tech stack

Python, Streamlit, pandas, numpy, plotly, yfinance, Finnhub, FRED API, Anthropic API

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your own API keys
streamlit run app.py
```

Free API keys needed: [Anthropic](https://console.anthropic.com), [FRED](https://fred.stlouisfed.org/docs/api/api_key.html), [Finnhub](https://finnhub.io).

## Project structure

- `app.py` — main Streamlit app / page layout
- `modules/` — one module per analysis feature (fundamentals, technicals, momentum, macro, scoring, portfolio, backtesting, etc.)
- `utils/` — shared helpers (data caching)
- `config.py` — tickers, scoring weights, and app configuration
