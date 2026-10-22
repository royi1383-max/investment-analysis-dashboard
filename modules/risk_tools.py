"""
Risk Tools — the missing risk-first workflows of professional traders and PMs.

  • trade_plan()        — Van Tharp / Minervini position sizing: ATR stop,
                          shares from risk budget (1R), reward/risk, trailing stop
  • portfolio_fit()     — Markowitz lens: does a candidate ADD diversification
                          or duplicate existing risk? Correlations + beta.
  • stress_scenarios()  — scenario P&L via beta + sector sensitivity heuristics
  • monte_carlo()       — 1-year GBM cone from the portfolio's own return history

All deterministic — no AI calls.
"""
import numpy as np
import pandas as pd
import streamlit as st

from utils.cache import get_ticker_info, get_price_history


# ─── ATR ──────────────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, period: int = 14) -> float | None:
    try:
        h, l, c = df["High"].squeeze(), df["Low"].squeeze(), df["Close"].squeeze()
        prev_c = c.shift(1)
        tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
        val = float(tr.rolling(period).mean().iloc[-1])
        return val if val > 0 else None
    except Exception:
        return None


# ─── Trade Planner ────────────────────────────────────────────────────────────

@st.cache_data(ttl=900, show_spinner=False)
def get_trade_inputs(symbol: str) -> dict:
    """Price + ATR + swing low for stop placement."""
    try:
        df = get_price_history(symbol, period="6mo")
        if df.empty or len(df) < 30:
            return {"error": "Not enough price history."}
        close = df["Close"].squeeze()
        price = float(close.iloc[-1])
        atr   = _atr(df)
        swing_low = float(df["Low"].squeeze().iloc[-10:].min())
        return {"price": price, "atr": atr, "swing_low": swing_low, "error": None}
    except Exception as e:
        return {"error": str(e)}


def trade_plan(price: float, atr: float | None, account_size: float,
               risk_pct: float, atr_mult: float = 2.0,
               target_price: float | None = None,
               stop_price: float | None = None) -> dict:
    """
    1R sizing: risk budget = account * risk%; shares = budget / (entry - stop).
    Stop defaults to entry - atr_mult × ATR. Chandelier trail = close - 3×ATR.
    """
    if price <= 0:
        return {"error": "Invalid price."}
    if stop_price is None:
        if not atr:
            return {"error": "No ATR available — set a manual stop."}
        stop_price = price - atr_mult * atr
    if stop_price >= price:
        return {"error": "Stop must be below entry."}

    risk_budget  = account_size * risk_pct / 100
    per_share    = price - stop_price
    shares       = int(risk_budget / per_share)
    position_usd = shares * price
    position_pct = position_usd / account_size * 100 if account_size > 0 else 0

    out = {
        "stop_price":    round(stop_price, 2),
        "stop_dist_pct": round(per_share / price * 100, 2),
        "risk_budget":   round(risk_budget, 2),
        "shares":        shares,
        "position_usd":  round(position_usd, 2),
        "position_pct":  round(position_pct, 2),
        "r1_usd":        round(per_share, 2),
        "chandelier":    round(price - 3 * atr, 2) if atr else None,
        "error":         None,
        "warnings":      [],
    }
    if target_price and target_price > price:
        reward = target_price - price
        out["reward_risk"] = round(reward / per_share, 2)
        out["target_gain_pct"] = round(reward / price * 100, 1)
        if out["reward_risk"] < 2:
            out["warnings"].append(
                f"Reward/Risk {out['reward_risk']} < 2 — most pros skip trades under 2R")
    if position_pct > 25:
        out["warnings"].append(
            f"Position would be {position_pct:.0f}% of the account — "
            f"stop is tight relative to risk budget; cap the position instead")
    return out


# ─── Portfolio Fit ────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def portfolio_fit(symbol: str, holdings: tuple) -> dict:
    """
    Candidate vs existing holdings: pairwise correlations (6mo daily),
    beta vs SPY, and a diversification verdict.
    """
    try:
        cand_df = get_price_history(symbol, period="6mo")
        if cand_df.empty:
            return {"error": f"No data for {symbol}."}
        cand_ret = cand_df["Close"].squeeze().pct_change(fill_method=None).dropna()

        # Beta vs SPY
        spy_ret = get_price_history("SPY", period="6mo")["Close"].squeeze() \
            .pct_change(fill_method=None).dropna()
        joined = pd.concat([cand_ret, spy_ret], axis=1, join="inner").dropna()
        beta = None
        if len(joined) > 40 and joined.iloc[:, 1].var() > 0:
            beta = float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / joined.iloc[:, 1].var())

        corrs = []
        for h in holdings:
            if h.upper() == symbol.upper():
                continue
            try:
                h_ret = get_price_history(h, period="6mo")["Close"].squeeze() \
                    .pct_change(fill_method=None).dropna()
                j = pd.concat([cand_ret, h_ret], axis=1, join="inner").dropna()
                if len(j) > 40:
                    corrs.append({"symbol": h, "corr": round(float(j.corr().iloc[0, 1]), 2)})
            except Exception:
                continue
        corrs.sort(key=lambda x: -x["corr"])
        avg_corr = round(sum(c["corr"] for c in corrs) / len(corrs), 2) if corrs else None
        max_corr = corrs[0] if corrs else None

        if avg_corr is None:
            verdict = "No holdings to compare against."
        elif avg_corr >= 0.7:
            verdict = ("DUPLICATES RISK — moves almost in lockstep with the existing book. "
                       "Adds concentration, not diversification.")
        elif avg_corr >= 0.45:
            verdict = ("PARTIAL OVERLAP — meaningfully correlated with current holdings. "
                       "Size it modestly.")
        else:
            verdict = ("DIVERSIFIER — low correlation to the current book. "
                       "Adds a genuinely different return stream.")

        return {"beta": round(beta, 2) if beta is not None else None,
                "avg_corr": avg_corr, "max_corr": max_corr,
                "corrs": corrs, "verdict": verdict, "error": None}
    except Exception as e:
        return {"error": str(e)}


# ─── Scenario stress test ─────────────────────────────────────────────────────

# Sector sensitivity multipliers on top of beta, per scenario.
SCENARIOS = {
    "Rate Shock (+100bps)": {
        "market": -0.08,
        "sector_mult": {"Technology": 1.4, "Communication Services": 1.3,
                        "Consumer Cyclical": 1.2, "Real Estate": 1.6,
                        "Utilities": 1.3, "Financial Services": 0.5,
                        "Energy": 0.6, "Consumer Defensive": 0.7, "Healthcare": 0.8},
        "desc": "10Y yield jumps 1pp — duration assets (growth, REITs) hit hardest; banks/energy relatively insulated.",
    },
    "2022-Style Bear (-25%)": {
        "market": -0.25,
        "sector_mult": {"Technology": 1.3, "Communication Services": 1.25,
                        "Consumer Cyclical": 1.2, "Consumer Defensive": 0.5,
                        "Healthcare": 0.6, "Energy": 0.3, "Utilities": 0.55,
                        "Financial Services": 0.9},
        "desc": "Broad valuation reset like 2022 — high-multiple growth compresses most, defensives cushion.",
    },
    "AI Sentiment Bust": {
        "market": -0.10,
        "sector_mult": {"Technology": 1.8, "Communication Services": 1.4,
                        "Consumer Defensive": 0.3, "Healthcare": 0.4,
                        "Energy": 0.3, "Utilities": 0.4, "Financial Services": 0.6},
        "desc": "AI capex narrative cracks — semis/megacap tech de-rate sharply, old economy barely moves.",
    },
    "Oil Shock ($120+)": {
        "market": -0.06,
        "sector_mult": {"Energy": -1.5,   # negative mult → gains
                        "Industrials": 1.2, "Consumer Cyclical": 1.4,
                        "Technology": 1.0, "Consumer Defensive": 0.8,
                        "Utilities": 0.9, "Basic Materials": 0.2},
        "desc": "Supply-driven oil spike — energy rallies, consumer and transport-heavy sectors squeezed.",
    },
    "Risk-On Melt-Up (+15%)": {
        "market": 0.15,
        "sector_mult": {"Technology": 1.4, "Communication Services": 1.3,
                        "Consumer Cyclical": 1.3, "Consumer Defensive": 0.4,
                        "Utilities": 0.35, "Healthcare": 0.6,
                        "Financial Services": 1.1, "Energy": 0.8},
        "desc": "Liquidity surge / rate-cut euphoria — high-beta growth leads, defensives lag badly.",
    },
}


@st.cache_data(ttl=3600, show_spinner=False)
def _beta_for(symbol: str) -> float:
    try:
        info = get_ticker_info(symbol)
        b = info.get("beta")
        return float(b) if b is not None else 1.0
    except Exception:
        return 1.0


def stress_scenarios(positions: list[dict]) -> dict:
    """
    positions: [{symbol, value, sector}] → per-scenario portfolio P&L estimate.
    Impact per position = market_move × beta × sector_mult.
    """
    total = sum(p["value"] for p in positions) or 1
    results = {}
    for name, sc in SCENARIOS.items():
        rows, pnl = [], 0.0
        for p in positions:
            beta = _beta_for(p["symbol"])
            mult = sc["sector_mult"].get(p.get("sector", ""), 1.0)
            impact_pct = sc["market"] * beta * mult
            impact_usd = p["value"] * impact_pct
            pnl += impact_usd
            rows.append({"symbol": p["symbol"], "impact_pct": round(impact_pct * 100, 1),
                         "impact_usd": round(impact_usd, 0)})
        rows.sort(key=lambda r: r["impact_usd"])
        results[name] = {
            "desc":       sc["desc"],
            "pnl_usd":    round(pnl, 0),
            "pnl_pct":    round(pnl / total * 100, 1),
            "worst":      rows[0] if rows else None,
            "best":       rows[-1] if rows else None,
            "rows":       rows,
        }
    return results


# ─── Monte Carlo projection ───────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def monte_carlo(symbols_weights: tuple, start_value: float,
                days: int = 252, n_paths: int = 500) -> dict:
    """
    GBM cone for a weighted basket. symbols_weights: ((sym, weight_frac), ...).
    Estimates mu/sigma from 1y of weighted daily returns.
    Returns percentile bands (5/25/50/75/95) over the horizon.
    """
    try:
        rets = None
        for sym, w in symbols_weights:
            ph = get_price_history(sym, period="1y")
            if ph.empty:
                continue
            r = ph["Close"].squeeze().pct_change(fill_method=None).dropna() * w
            rets = r if rets is None else rets.add(r, fill_value=0)
        if rets is None or len(rets) < 60:
            return {"error": "Not enough history for simulation."}

        mu, sigma = float(rets.mean()), float(rets.std())
        rng = np.random.default_rng(42)
        shocks = rng.normal(mu, sigma, size=(n_paths, days))
        paths = start_value * np.cumprod(1 + shocks, axis=1)

        pct = {p: np.percentile(paths, p, axis=0) for p in (5, 25, 50, 75, 95)}
        end_vals = paths[:, -1]
        return {
            "percentiles":  {str(k): v.tolist() for k, v in pct.items()},
            "prob_loss":    round(float((end_vals < start_value).mean()) * 100, 1),
            "median_end":   round(float(np.median(end_vals)), 0),
            "p5_end":       round(float(np.percentile(end_vals, 5)), 0),
            "p95_end":      round(float(np.percentile(end_vals, 95)), 0),
            "ann_vol":      round(sigma * np.sqrt(252) * 100, 1),
            "error":        None,
        }
    except Exception as e:
        return {"error": str(e)}


# ─── Risk of Ruin ─────────────────────────────────────────────────────────────

def _solve_ruin_root(p: float, q: float, payoff: float) -> float:
    """Root r in (0,1), r != 1, of p*r^(payoff+1) - r + q = 0 — the generalized
    (unequal-step) gambler's-ruin equation for a random walk that wins +payoff
    units with probability p and loses -1 unit with probability q. Ruin
    probability from U units of capital is r^U. Returns 1.0 (ruin certain)
    when the walk has no positive drift (p*payoff <= q)."""
    if p * payoff <= q:
        return 1.0

    def g(r: float) -> float:
        return p * (r ** (payoff + 1)) - r + q

    xs = np.linspace(1e-6, 1 - 1e-9, 2000)
    gs = p * (xs ** (payoff + 1)) - xs + q
    for i in range(len(xs) - 1):
        if gs[i] == 0:
            return float(xs[i])
        if gs[i] * gs[i + 1] < 0:
            a, c = float(xs[i]), float(xs[i + 1])
            for _ in range(60):
                m = (a + c) / 2
                if g(a) * g(m) < 0:
                    c = m
                else:
                    a = m
            return float((a + c) / 2)
    return 1.0   # no sign change found in (0,1) → no root below 1, ruin certain


def risk_of_ruin(win_rate: float, avg_win_pct: float, avg_loss_pct: float,
                 risk_per_trade_pct: float, ruin_pct: float = 50.0) -> dict:
    """
    Payoff-adjusted Risk-of-Ruin: probability of losing `ruin_pct`% of capital
    (in units of `risk_per_trade_pct` bets) before the edge compounds it up,
    via the generalized (unequal win/loss size) gambler's-ruin equation.

    Also reports the classic EVEN-MONEY formula (R = ((1-A)/(1+A))^U, A=p-q)
    for comparison — it assumes wins and losses are the same size, which is
    almost never true in trading (here payoff = avg_win/avg_loss), so it can
    disagree sharply with the payoff-adjusted number and is shown for context
    only, not used for the verdict.

    win_rate                 — 0-1 historical win rate
    avg_win_pct/avg_loss_pct — average % gain/loss per trade (loss as positive %)
    risk_per_trade_pct       — % of capital risked per trade (fixed-fractional)
    ruin_pct                 — drawdown %% treated as "ruin" (default 50%)
    """
    if not (0 < win_rate < 1) or avg_win_pct <= 0 or avg_loss_pct <= 0 or risk_per_trade_pct <= 0:
        return {"error": "Need win_rate in (0,1) and positive win/loss/risk inputs."}

    p, q = win_rate, 1 - win_rate
    payoff = avg_win_pct / avg_loss_pct
    units = ruin_pct / risk_per_trade_pct
    expectancy = p * payoff - q   # in R-multiples (R = risk_per_trade)

    # Classic even-money formula — for comparison only, see docstring.
    edge_a = p - q
    classic_ror = 1.0 if edge_a <= 0 else ((1 - edge_a) / (1 + edge_a)) ** units

    # Payoff-adjusted (generalized gambler's ruin) — the number that drives the verdict.
    root = _solve_ruin_root(p, q, payoff)
    payoff_ror = min(1.0, root ** units)

    if expectancy <= 0:
        verdict = "NEGATIVE EXPECTANCY — ruin is a near-certainty over enough trades; fix the edge before sizing up."
    elif payoff_ror >= 0.5:
        verdict = f"Risk of Ruin {payoff_ror*100:.0f}% — too high; cut risk-per-trade or improve the edge."
    elif payoff_ror >= 0.1:
        verdict = f"Risk of Ruin {payoff_ror*100:.1f}% — elevated; most professional systems target under 1-5%."
    else:
        verdict = f"Risk of Ruin {payoff_ror*100:.2f}% — comfortably low at this sizing."

    return {
        "payoff_ror_pct":  round(payoff_ror * 100, 2),
        "classic_ror_pct": round(classic_ror * 100, 2),
        "expectancy_r":    round(expectancy, 3),
        "payoff_ratio":    round(payoff, 2),
        "edge":            round(edge_a, 3),
        "verdict":         verdict,
        "error":           None,
    }


# ─── Murphy's 20-Point Money Management Checklist ─────────────────────────────

MURPHY_CHECKLIST: list[str] = [
    "I have a written trading plan before entering",
    "I never risk more than 5% of equity on a single trade",
    "I always use a protective stop-loss order",
    "I know my exit point BEFORE I enter",
    "I don't add to a losing position (no averaging down)",
    "I diversify — not everything in one market/sector",
    "I don't overtrade relative to my account size",
    "I keep leverage proportional to volatility, not maximized",
    "I have a target reward/risk of at least 2:1 before entering",
    "I cut losses quickly and let winners run",
    "I don't let a winning trade turn into a loss (trail stops)",
    "I review closed trades to learn, not just to relive them",
    "I avoid trading right after a big loss out of frustration",
    "I size positions the same way regardless of conviction 'feel'",
    "I have a max daily/weekly loss limit and I honor it",
    "I don't chase a market that has already moved sharply",
    "I know my total portfolio risk, not just per-trade risk",
    "I keep records of every trade with entry/exit rationale",
    "I don't trade when emotionally compromised (revenge, euphoria)",
    "I periodically re-test whether my edge still exists",
]


def murphy_checklist(answers: dict[int, bool]) -> dict:
    """Score against Murphy's 20-point money-management checklist.
    `answers`: {index (0-19): bool}. Missing indices count as not-yet-answered
    (excluded from the denominator rather than counted as failures)."""
    answered = {i: v for i, v in answers.items() if 0 <= i < len(MURPHY_CHECKLIST)}
    total = len(answered)
    passed = sum(1 for v in answered.values() if v)
    if total == 0:
        return {"passed": 0, "total": 0, "pct": None, "verdict": "Not yet answered", "items": MURPHY_CHECKLIST}
    pct = passed / total * 100
    if pct >= 90:
        verdict = "DISCIPLINED — money management is not the leak in this system"
    elif pct >= 70:
        verdict = "MOSTLY SOUND — a few gaps worth tightening"
    elif pct >= 40:
        verdict = "LEAKY — money-management gaps are likely costing more than bad picks"
    else:
        verdict = "HIGH RISK OF RUIN — the checklist itself IS the strategy fix needed here"
    return {"passed": passed, "total": total, "pct": round(pct, 0),
            "verdict": verdict, "items": MURPHY_CHECKLIST}


# ─── What-If simulator ────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def what_if(holdings: tuple, candidate: str, add_pct: float) -> dict:
    """
    Portfolio impact of adding `candidate` at `add_pct`% (existing scaled down
    proportionally). holdings: ((sym, weight_frac), ...).
    Returns before/after: beta, ann_vol, avg_corr, top_sector share.
    """
    try:
        import pandas as pd

        def _rets(sym):
            ph = get_price_history(sym, period="6mo")
            if ph.empty:
                return None
            return ph["Close"].squeeze().pct_change(fill_method=None).dropna()

        spy = _rets("SPY")
        if spy is None:
            return {"error": "SPY data unavailable"}

        rets = {}
        sectors = {}
        for sym, _w in holdings:
            r = _rets(sym)
            if r is not None:
                rets[sym] = r
                try:
                    sectors[sym] = get_ticker_info(sym).get("sector") or "Unknown"
                except Exception:
                    sectors[sym] = "Unknown"
        cand_r = _rets(candidate)
        if cand_r is None:
            return {"error": f"No data for {candidate}"}
        try:
            cand_sector = get_ticker_info(candidate).get("sector") or "Unknown"
        except Exception:
            cand_sector = "Unknown"
        if not rets:
            return {"error": "No holdings data"}

        def _stats(weight_map, extra=None):
            frames = {s: rets[s] for s in weight_map if s in rets}
            if extra is not None:
                frames[candidate] = cand_r
            df = pd.DataFrame(frames).dropna()
            if len(df) < 40:
                return None
            w = pd.Series({s: weight_map.get(s, 0) for s in df.columns})
            if extra is not None:
                w[candidate] = extra
            w = w / w.sum()
            port = (df * w).sum(axis=1)
            joined = pd.concat([port, spy], axis=1, join="inner").dropna()
            beta = (float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) /
                          joined.iloc[:, 1].var())
                    if joined.iloc[:, 1].var() > 0 else None)
            vol = float(port.std() * (252 ** 0.5) * 100)
            corr_m = df.corr()
            n = len(df.columns)
            avg_corr = (float((corr_m.sum().sum() - n) / (n * n - n))
                        if n > 1 else None)
            # sector shares
            sec_w = {}
            sec_map = dict(sectors)
            if extra is not None:
                sec_map[candidate] = cand_sector
            for s in df.columns:
                sec = sec_map.get(s, "Unknown")
                sec_w[sec] = sec_w.get(sec, 0) + float(w[s])
            top_sec = max(sec_w.items(), key=lambda kv: kv[1]) if sec_w else ("", 0)
            return {"beta": round(beta, 2) if beta is not None else None,
                    "vol": round(vol, 1),
                    "avg_corr": round(avg_corr, 2) if avg_corr is not None else None,
                    "top_sector": top_sec[0], "top_sector_pct": round(top_sec[1] * 100, 1)}

        base_w = {s: w for s, w in holdings}
        before = _stats(base_w)
        f = add_pct / 100
        scaled = {s: w * (1 - f) for s, w in holdings}
        after = _stats(scaled, extra=f)
        if before is None or after is None:
            return {"error": "Insufficient overlapping history"}
        return {"before": before, "after": after,
                "cand_sector": cand_sector, "error": None}
    except Exception as e:
        return {"error": str(e)}
