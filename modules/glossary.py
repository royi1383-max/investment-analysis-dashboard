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

    # ── Backtesting / performance ────────────────────────────────────────────
    "cagr": "CAGR: the smoothed annual growth rate — what constant yearly return would produce the same end result. Lets you compare periods of different lengths fairly.",
    "win_rate": "Win Rate: % of trades that made money. Meaningless alone — a 30% win rate with big winners beats a 70% win rate with big losers. Always pair with payoff ratio.",
    "profit_factor": "Profit Factor: gross profits ÷ gross losses. Above 1.5 = solid system; below 1 = losing system. More honest than win rate.",
    "equity_curve": "Equity Curve: your account value over time. The SHAPE matters — a smooth rise beats a jagged one with the same endpoint; deep valleys are drawdowns you'd have had to sit through.",
    "benchmark": "Benchmark (vs Buy & Hold / SPY): a strategy is only good if it beats just… holding. Many backtests win in trends and lose the moment you include sideways markets.",
    "backtest": "Backtest: running a strategy on past data. Beware: the past is one sample — overfit parameters look brilliant historically and fail live. Test on different periods.",

    # ── Scanning / scoring ───────────────────────────────────────────────────
    "rvol": "Relative Volume: today's volume vs the 20-day average. Above 1.5x = unusual interest (institutions moving); breakouts on high RVOL are far more reliable than quiet ones.",
    "rs": "Relative Strength vs SPY: the stock/sector return minus the index's over the same window. Positive = leadership; institutions hide in the names that fall least and rally most.",
    "momentum_dir": "Momentum Direction (↑→↓): whether 1-month relative strength is accelerating or fading vs the 3-month baseline. ↑ = money rotating IN now; ↓ = leadership fading.",
    "weekly_score": "Weekly Score: composite of 5 pillars — model (fundamentals+technicals), analysts, options flow, breakout setup, momentum bonus. Built to surface stocks in BUYABLE condition now, not just good companies.",
    "bull_pct": "Bull %: share of analysts rating Buy/Strong Buy. Above 70% = strong consensus (but crowded); below 50% = controversial — check who's right.",
    "breakout_score": "Breakout Setup score: BB squeeze + proximity to 52-week high + tight range + volume surge. High = coiled spring; the move often follows the squeeze.",
    "composite_health": "Market Health Composite: weighted blend of VIX, yield curve, rates, CPI, credit spreads, trend. Above 70 = risk-on conditions; below 40 = defense first.",
    "sector_rotation": "Sector Rotation: money constantly moves between sectors as the cycle turns. Riding the sectors gaining relative strength (and avoiding the losers) is a return source independent of stock picking.",
    "grade": "Grade (A-F): letter summary of a sector's trend + relative strength + momentum acceleration. A/B = leadership; D/F = avoid or watch for reversal setups only.",

    # ── Fund methodologies (who, how it's computed, what it means for the stock) ──
    "minervini_method": "Mark Minervini (US Investing Champion) buys ONLY stocks in a confirmed Stage-2 uptrend. The 7-point template checks price vs MA50/150/200, that the MAs are stacked and rising, and that price is ≥30% off the 52w low and within 25% of the high. Calculation: pure moving-average comparisons — no opinion. Meaning: 7/7 = institutions are accumulating; below 5 = he wouldn't touch it regardless of the story.",
    "turtle_method": "The Turtles (Richard Dennis's famous experiment) proved trading can be taught with mechanical rules: buy a breakout above the 20-day high (System 1) or 55-day high (System 2), exit on a 10/20-day low. Calculation: Donchian channel highs/lows, nothing else. Meaning: a LONG BREAKOUT signal = the trend just asserted itself; 'in channel' = no signal, wait.",
    "trend_following_method": "Managed-futures funds (AQR, Man AHL) ride trends with zero fundamental input. Three votes here: price>MA200, MA50>MA200, and 12-1 momentum (12-month return excluding the last month — the academic construction). Meaning: 3/3 LONG = all timeframes agree; MIXED = chop risk; fighting a 0/3 signal is fighting the tape.",
    "kelly_method": "Kelly Criterion (John Kelly, Bell Labs; used by Ed Thorp) computes the bet size that maximizes long-run growth: f* = W − (1−W)/R, from your win rate W and win/loss ratio R (here: monthly return history). Meaning: the % of capital the math supports. Pros use HALF-Kelly because estimates are noisy — full Kelly with wrong inputs ruins you.",
    "druckenmiller_method": "Stanley Druckenmiller (30% annually for 30 years, no losing year): ride strong momentum WHEN the macro backdrop supports it, concentrate hard when everything aligns, cut instantly when the tape turns. Checks here: 3M/6M momentum strength, price vs MA50 (the tape), market regime (macro). Meaning: 3/3 = his 'bet big' setup; less = probe size or stand aside.",
    "factor_method": "Factor investing (AQR, Fama-French): decades of data show stocks with certain traits — cheap (Value), rising (Momentum), profitable (Quality), calm (Low-Vol), small (Size) — earn excess returns over time. The radar scores this stock 1-10 on each. Meaning: it tells you WHICH type of fund would buy this stock, and which factor crash would hurt it.",
    "risk_parity_method": "Ray Dalio's All-Weather logic: dollars are not risk. A portfolio 'balanced' in dollars is usually dominated by its most volatile position. Risk parity sizes each position inversely to its volatility so each contributes EQUAL risk. Calculation here: weight ∝ 1/volatility (6-month daily). Meaning: the gap column shows where your risk is secretly concentrated.",
    "panel_method": "Investment-committee process: independent analyses first (each persona), then a moderator weighs them BY RELEVANCE to this specific stock, surfaces the strongest disagreement, and commits to one decision with position sizing. This mirrors how real funds make decisions — the debate matters more than any single opinion.",
    "buffett_method": "Warren Buffett: 'a wonderful company at a fair price beats a fair company at a wonderful price.' The moat shows up in NUMBERS — consistently high ROE (≥15%), fat gross margins (pricing power), low debt. Price test: owner-earnings (FCF) yield vs bonds. Checks here compute exactly that. Meaning: quality without a fair price = wait; a fair price without quality = pass.",
    "munger_method": "Charlie Munger: 'Invert, always invert.' Don't look for reasons to buy — look for reasons you'd LOSE, and only act when there are none. The filter lists disqualifiers: heavy leverage, weak economics (low ROE), cash burn, accounting red flags, heavy short interest. Zero flags = permission to proceed to the bull case.",
    "lynch_method": "Peter Lynch (Magellan, 29%/yr): first CLASSIFY the company — Fast Grower / Stalwart / Slow Grower / Cyclical / Turnaround / Asset Play — because each type has different rules. Then PEG: P/E ÷ growth < 1 = bargain. Cyclicals invert the logic: buy at HIGH P/E (trough earnings). Meaning: most investing errors are type errors — treating a cyclical like a growth stock.",
    "graham_method": "Ben Graham (Buffett's teacher): price must sit BELOW a conservative intrinsic floor. Graham Number = √(22.5 × EPS × book value/share) — the max price where P/E×P/B ≤ 22.5. Demand a 30%+ margin of safety below it. Meaning: built for mature, profitable, asset-backed businesses — growth stocks always fail it, and that's information too.",
    "greenblatt_method": "Joel Greenblatt's Magic Formula (40%/yr in backtests): rank ALL stocks on just two numbers — earnings yield (EBIT/EV = how cheap) and return on capital (how good) — buy the best combined ranks. Checks here: EBITDA/EV ≥ 8% and ROA ≥ 12%. Meaning: quality AND cheapness together, mechanically, no stories.",
    "canslim_method": "William O'Neil's CANSLIM (studied every winning stock since 1953): C-urrent quarterly EPS +25%, A-nnual growth +25%, N-ew highs, S-mall supply (float), L-eader vs market, I-nstitutional sponsorship, M-arket direction. Meaning: winners share a profile BEFORE their big runs — growth + momentum + timing, all seven together.",
    "bogle_method": "Jack Bogle (founder of Vanguard): most active picking loses to simply indexing after costs. The test: did this stock beat SPY over 6M and 1Y? If indexing keeps winning, the effort and risk of picking aren't being paid for. The most humbling checklist in investing — run it on every position.",
    "shiller_method": "Robert Shiller (Nobel 2013): regular P/E lies at cycle turns — earnings collapse in recessions making stocks look 'expensive' at the bottom. CAPE fixes this: price ÷ average of 10 YEARS of inflation-adjusted earnings. Historic mean ~17. The single best known predictor of 10-year forward returns: CAPE 35+ has meant near-zero real decade returns; CAPE <15 preceded the best decades. A DECADE compass, useless for timing months.",
    "buffett_indicator": "Buffett called total market cap ÷ GDP 'probably the best single measure of where valuations stand.' Logic: the stock market can't grow faster than the economy forever. ~100% = historically fair; >180% = 'playing with fire' (his words from 1999 — before the dot-com crash proved him right). Calculation here: Wilshire 5000 index ÷ US GDP from FRED.",
    "fear_greed": "Fear & Greed composite (CNN-style, computed locally): 5 signals averaged 0-100 — VIX level, S&P momentum, market breadth (equal-weight RSP vs cap-weight SPY), credit appetite (junk bond momentum), and safe-haven demand (gold vs its trend). Extreme fear (<25) has historically been the BEST entry zone; extreme greed (>75) the time to trim. An emotions thermometer for the whole market — use it contrarian.",
    "piotroski_method": "Joseph Piotroski (Chicago, 2000): 9 binary checks on the financial statements — profitability (ROA>0, OCF>0, improving), low accruals (cash backs earnings), improving leverage/liquidity/margins/efficiency, no dilution. Score 8-9 among cheap stocks beat 0-2 by ~7.5%/yr in his study. Meaning: separates VALUE from VALUE TRAPS — cheap + strengthening vs cheap + dying.",
    "altman_method": "Edward Altman (NYU, 1968): Z-Score predicts bankruptcy from 5 ratios — working capital, retained earnings, EBIT, market cap vs liabilities, asset turnover. Z>2.99 = safe; 1.81-2.99 = grey; <1.81 = distress zone (~80-90% of bankruptcies flagged 1y ahead in studies). Run it on ANY 'cheap' stock before buying the dip — cheapness with a failing Z is how value investors get wiped out.",
    "templeton_method": "Sir John Templeton: 'buy at the point of maximum pessimism' — he bought 100 NYSE stocks under $1 in 1939 as war broke out. The mechanical translation: deep drawdown (≥35% off the high) + washed-out sentiment + business quality INTACT (profitable, cash-generating, decent F-Score). The quality test is what separates his method from catching falling knives.",
    "opportunity_lens": "Opportunity Lens: the composite score measures NOW — so a great business in a temporary drawdown scores low exactly when it may be the best buy. This lens splits the read: QUALITY (momentum-free fundamentals — is the business intact?) vs CONDITION (price action). Quality-high + condition-low = ON SALE candidate; quality-low + condition-low = falling knife. Entry is gated by REVERSAL READINESS, not hope.",
    "reversal_signals": "Reversal Readiness (0-5): higher low forming, RSI positive divergence (price falls but momentum refuses to confirm), volatility contraction (a base), price reclaiming a rising MA20, and down-day volume drying up (sellers exhausted). One signal = noise. Three+ = a bottoming PROCESS. The classic sequence: higher low → base → MA20 reclaim.",
    "falling_knife": "Falling Knife: a stock dropping fast where the FUNDAMENTALS are breaking too. 'It's cheap' is the bait; deteriorating business is the hook. Distinguish from 'on sale': check whether margins/ROE/F-Score are holding while the price falls. Never average down before that check.",
}


def tip(key: str) -> str:
    """Safe lookup — returns empty string for unknown keys."""
    return TIP.get(key, "")
