"""
Glossary — central dictionary of investing terms for the educational layer.

Usage:
  from modules.glossary import TIP
  st.metric("Sharpe", "1.4", help=TIP["sharpe"])

Every entry is a plain-language explanation with the practical "so what".
"""

TIP: dict[str, str] = {
    # ── Valuation ────────────────────────────────────────────────────────────
    "forward_pe": "Forward P/E: price ÷ NEXT year's expected earnings. What you pay for $1 of future profit. High-growth stocks justify higher P/E — always judge vs. growth rate and sector, not in isolation.",
    "ps": "Price/Sales: market cap ÷ annual revenue. The go-to for unprofitable growth companies. Software can sustain 10x+; retail rarely above 2x.",
    "peg": "PEG: P/E ÷ growth rate. Under ~1.5 = paying a fair price for the growth. Over 3 = growth already fully priced in.",
    "ev_ebitda": "EV/EBITDA: company value (incl. debt) ÷ operating cash profit. Better than P/E for comparing companies with different debt loads.",
    "dcf": "DCF (Discounted Cash Flow): today's value of all future cash the business will generate. The output is only as good as the growth and discount assumptions — that's why the sensitivity table matters.",
    "wacc": "WACC / discount rate: the annual return investors demand for holding this company's risk. Higher risk (beta) → higher WACC → lower present value of future cash.",
    "terminal_value": "Terminal Value: the value of ALL cash flows beyond the 5-year projection, in one number. If it dominates the DCF (>80%), the valuation leans on far-future guesses — be skeptical.",
    "intrinsic_value": "Intrinsic Value: what the business is 'really' worth per share by DCF math, vs. what the market charges today. A margin of safety = buying well below it.",

    # ── Profitability / quality ──────────────────────────────────────────────
    "gross_margin": "Gross Margin: % of revenue left after direct costs. Software: 70-90%. Hardware: 30-50%. Retail: 20-35%. Falling gross margin = pricing power eroding.",
    "profit_margin": "Net Margin: % of revenue that becomes actual profit. Compare within the sector — 5% is great for a grocer, weak for software.",
    "roe": "ROE: profit generated per $1 of shareholders' equity. Above 15-20% consistently = a quality compounder. Beware: high debt inflates ROE artificially.",
    "fcf": "Free Cash Flow: real cash left after running AND investing in the business. Harder to fake than accounting earnings — 'profit is an opinion, cash is a fact'.",
    "ocf_ni": "Cash Backing (OCF/NI): operating cash flow ÷ net income. Near or above 1 = earnings are real cash. Well below 1 = paper profits built on accruals — a classic red flag.",
    "sbc": "Stock-Based Compensation: paying employees in shares. Doesn't burn cash but silently dilutes you. Over ~10% of revenue = your ownership shrinks meaningfully every year.",
    "dilution": "Dilution: the company issuing new shares, shrinking your slice of the pie. Share count growing 4%+/yr means the business must grow that much just to keep your per-share value flat.",
    "rule_of_40": "Rule of 40: revenue growth % + profit margin % ≥ 40 = a healthy growth company. A SaaS growing 50% losing 5% passes; growing 10% losing 20% fails.",

    # ── Technical ────────────────────────────────────────────────────────────
    "rsi": "RSI (0-100): momentum speedometer. Above 70 = overbought (stretched, pullback risk). Below 30 = oversold (potential bounce). In strong uptrends RSI can stay 60-80 for months — overbought ≠ sell.",
    "macd": "MACD: trend-momentum gauge from two moving averages. MACD line above its signal line = bullish momentum; crossing below = momentum fading.",
    "ma200": "200-day Moving Average: the long-term trend line. Price above a rising MA200 = healthy uptrend. Institutions watch it — breaks below often trigger selling.",
    "ma50": "50-day Moving Average: the medium-term trend. In strong stocks, pullbacks to the MA50 that hold are classic add points.",
    "atr": "ATR (Average True Range): how many $ the stock moves on a typical day. The building block for stop placement — a stop inside 1 ATR will get hit by pure noise.",
    "bollinger": "Bollinger Bands: volatility envelope around the 20-day average. A tight squeeze = energy building for a big move; walking the upper band = strong trend.",
    "golden_cross": "Golden Cross: MA50 crossing above MA200 — long-term trend turning up. Death Cross = the reverse.",
    "breakout": "Breakout: price clearing a resistance level (e.g. a 20d/55d high) on volume. The Turtle system buys these mechanically — trends often start here.",
    "rs_line": "Relative Strength vs SPY: the stock's return minus the index's. Positive RS in a falling market = institutions defending the name — a leadership tell.",

    # ── Risk / portfolio ─────────────────────────────────────────────────────
    "beta": "Beta: sensitivity to the market. 1.0 = moves with the S&P. 2.0 = twice the swing both ways. High-beta rallies harder in risk-on, bleeds harder in risk-off.",
    "sharpe": "Sharpe Ratio: return earned per unit of volatility. Above 1 = good, above 2 = excellent. Two funds with equal returns — the higher-Sharpe one gave you a smoother ride.",
    "sortino": "Sortino Ratio: like Sharpe but only penalizes DOWNSIDE volatility — upside swings shouldn't count against you.",
    "max_drawdown": "Max Drawdown: worst peak-to-trough loss. The number that tests your stomach — a 50% drawdown needs a 100% gain just to break even.",
    "var": "VaR 95%: the daily loss you'd exceed only 1 day in 20. A rough 'how bad is a bad day' yardstick — real crashes exceed it.",
    "volatility": "Annualized Volatility: how wildly the price swings per year. Under 20% = calm; over 50% = expect gut-wrenching moves both ways.",
    "correlation": "Correlation (-1 to +1): how much two holdings move together. A portfolio of 0.9-correlated stocks is ONE bet wearing different tickers. True diversification needs low/negative correlations.",
    "risk_parity": "Risk Parity (Dalio): size positions by RISK, not dollars — volatile holdings get less capital so each position contributes equal risk. Prevents one wild stock dominating your fate.",
    "kelly": "Kelly %: the mathematically optimal bet size given your win rate and payoff. Pros use HALF-Kelly — full Kelly assumes your estimates are perfect (they aren't).",
    "r_multiple": "R (risk unit): 1R = the $ you risk to your stop. A 3R winner pays for 3 losers. Think in R, not %, and position sizing becomes mechanical.",
    "reward_risk": "Reward/Risk: potential gain ÷ potential loss at your stop. Under 2R most pros pass — you need to be right too often to make money.",
    "position_sizing": "Position Sizing: decide the LOSS you can tolerate first (e.g. 1% of account), divide by the stop distance — that's your share count. Risk decides size, not conviction.",
    "stop_loss": "Stop Loss: the pre-committed exit that caps a loss. Place it where the thesis is WRONG (below support / 2×ATR), not at a round % that means nothing.",
    "chandelier": "Chandelier / Trailing Stop: an exit that ratchets UP as price rises (e.g. highest close − 3×ATR) — never down. Lets winners run while protecting gains.",
    "hedging": "Hedging: paying to cap downside — protective puts, collars, or a short pair. Costs return in calm markets; earns its keep in crashes. Insurance, not a trade.",
    "leverage": "Leverage: amplifying exposure with borrowed money or derivatives. Doubles gains AND losses — a 50% leveraged drawdown can be unrecoverable. Pros lever low-vol books, not single hot stocks.",
    "drift": "Drift: how far a position's weight has wandered from its target. Winners bloat, losers shrink — unmanaged drift concentrates your risk exactly where valuations rose most.",
    "rebalancing": "Rebalancing: trimming what grew and topping up what lagged, back to target weights. Mechanically sells high / buys low — but weigh transaction costs before acting.",
    "monte_carlo": "Monte Carlo: simulating hundreds of possible futures from the portfolio's own volatility. Plan for the whole 5%-95% cone, not the median path.",
    "stress_test": "Stress Test: 'what happens to my portfolio if X' — rate shock, bear market, sector bust. Reveals hidden concentration BEFORE the scenario happens.",

    # ── Market / macro ───────────────────────────────────────────────────────
    "vix": "VIX: options-implied fear gauge. Under 15 = complacency; 20-30 = worry; over 30 = panic (historically often a buying zone for the brave).",
    "yield_curve": "Yield Curve (10Y-2Y): long minus short rates. Inverted (negative) = bond market pricing a slowdown — historically preceded recessions by 6-18 months.",
    "hy_spread": "High-Yield Spread: extra yield junk bonds pay over Treasuries. Widening = credit stress building — often leads equity selloffs by weeks.",
    "dxy": "Dollar Index (DXY): strong dollar shrinks the overseas earnings of US multinationals and pressures emerging markets.",
    "risk_on_off": "Risk-On / Risk-Off: the market's appetite. Risk-on = money flows to growth and high-beta; risk-off = to cash, gold, defensives. Fighting the regime is expensive.",
    "market_breadth": "Breadth: how MANY stocks participate in a rally. An index at highs carried by 5 mega-caps while most stocks fall = a fragile rally.",

    # ── Institutional / flow ─────────────────────────────────────────────────
    "13f": "13F: quarterly SEC filing where big funds disclose holdings — 45 days late. Useful for ideas and conviction signals, useless for timing.",
    "mspr": "MSPR (-100..+100): monthly insider buy/sell balance. Insiders sell for many reasons but BUY for only one — clusters of buying are the strongest legal signal.",
    "insider": "Insider Transactions: executives trading their own stock. One sale = noise (taxes, diversification). Multiple executives buying together = they see something.",
    "short_interest": "Short Interest: % of shares bet AGAINST the stock. Over 15-20% = heavy skepticism — and squeeze fuel if good news forces shorts to buy back.",
    "call_put_ratio": "Call/Put Ratio: options bets up vs down. Above ~1.3 = unusually bullish positioning; typical market runs 0.7-0.9 (put hedging is normal).",
    "institutional_ownership": "Institutional Ownership: % held by funds. 60-90% = validated but well-discovered. Very low = either undiscovered or avoided for a reason.",
    "smart_money": "Smart Money: what informed investors (funds, insiders) DO with money, vs. what commentators say. Filings and flows over opinions.",

    # ── Strategy / trading ───────────────────────────────────────────────────
    "alpha": "Alpha: return above what the market gave you. Beating SPY by picking = alpha; riding a rising market = beta. Most funds fail to sustain alpha — respect how hard it is.",
    "momentum_factor": "Momentum: winners keep winning for months (12-1 effect) — the most robust factor in academic finance. Fails violently at sharp market turns.",
    "value_factor": "Value: cheap-vs-fundamentals stocks outperform long-term — but 'cheap' can stay cheap for years, and some cheap stocks are cheap for a reason (value traps).",
    "quality_factor": "Quality: high margins + high ROE + low debt compound quietly. Pay a fair price for a wonderful company (Buffett) rather than a wonderful price for a fair one.",
    "seasonality": "Seasonality: repeating calendar patterns (e.g. 'sell in May', September weakness). A mild tailwind for timing at the margin — never a thesis by itself.",
    "expectancy": "Expectancy: average $ made per trade over many trades = (win% × avg win) − (loss% × avg loss). Positive expectancy + position sizing = a system; anything else is gambling.",
    "conviction": "Conviction (1-10): how strongly the analysis supports acting. High conviction = bigger (but still capped) size. Low conviction + action = gambling.",
    "time_horizon": "Time Horizon: when the thesis should play out. Mismatched horizon is a classic error — buying a 2-year story and panic-selling at a 2-week dip.",
}


def tip(key: str) -> str:
    """Safe lookup — returns empty string for unknown keys."""
    return TIP.get(key, "")
