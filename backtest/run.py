"""Run the chosen strategy end to end: data -> signals -> engine -> metrics.

Default produces three artifacts under backtest/results/:
  research/  gross edge, risk halts OFF  (measures the strategy itself)
  risk/      live risk overlay ON        (daily -3%, kill -10%, 2-day cooldown)
  is/, oos/  70/30 in-sample vs out-of-sample (research cfg)

Usage:
    python -m backtest.run            # all of the above + summary table
    python -m backtest.run --trend    # same, but the trend-only baseline strategy
"""
import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from app.strategy.trend import TrendParams, compute_signals
from backtest.data import load_candles
from backtest.engine import BTConfig, run_backtest
from backtest.metrics import compute_metrics, save_results

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
log = logging.getLogger("backtest.run")
ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "backtest" / "results"

# chosen production strategy (regime switch) — see RESUME.md / backtest/README.md
PROD = TrendParams(entry_mode="regime", ema_fast=20, ema_slow=50,
                   adx_trend=22, adx_range=18, rsi_os=25, rsi_ob=75,
                   trend_stop_mult=2.0, trend_trail_mult=4.0,
                   mr_stop_mult=1.5, mr_tp_rr=1.0)
# trend-only baseline (--trend)
TREND = TrendParams(entry_mode="ema_cross", ema_fast=21, ema_slow=55,
                    adx_min=25.0, use_htf_filter=False)

RESEARCH_CFG = BTConfig(daily_loss_pct=1e9, max_dd_pct=1e9)                     # edge (fixed sizing = neutral)
RISK_CFG = BTConfig(daily_loss_pct=3.0, max_dd_pct=10.0, dd_cooldown_days=2.0,  # live overlay
                    sizing="anti_martingale")  # press winners — best fit for the trend edge
# the trend-only baseline exits via engine-level ATR trailing (its signals carry none)
TREND_EXITS = dict(use_tp=False, atr_stop_mult=1.5, trail_atr_mult=4.0)


def run(sig, cfg, label, outdir):
    trades, equity, state = run_backtest(sig, cfg)
    m = compute_metrics(trades, equity, state, benchmark=sig["close"])
    save_results(trades, equity, m, outdir, label)
    log.info("[%s] %s", label, json.dumps(m, default=str))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trend", action="store_true", help="use the trend-only baseline")
    args = ap.parse_args()

    params = TREND if args.trend else PROD
    research = BTConfig(**{**RESEARCH_CFG.__dict__, **(TREND_EXITS if args.trend else {})})
    risk = BTConfig(**{**RISK_CFG.__dict__, **(TREND_EXITS if args.trend else {})})

    df_tf, df_htf = load_candles()
    sig = compute_signals(df_tf, df_htf, params)
    split = sig.index[int(len(sig) * 0.7)]

    rows = {
        "research": run(sig, research, "research", RESULTS / "research"),
        "risk_managed": run(sig, risk, "risk", RESULTS / "risk"),
        "in_sample": run(sig[sig.index < split], research, "in_sample", RESULTS / "is"),
        "out_sample": run(sig[sig.index >= split], research, "out_sample", RESULTS / "oos"),
    }
    cols = ["total_return_pct", "cagr_pct", "profit_factor", "sharpe", "sortino",
            "calmar", "max_drawdown_pct", "alpha_annual_pct", "beta", "treynor_annual",
            "win_rate_pct", "trades", "kill_switch_hits"]
    tbl = pd.DataFrame(rows).T
    print("\n=== %s strategy ===" % ("TREND-ONLY" if args.trend else "REGIME"))
    print(tbl[[c for c in cols if c in tbl.columns]].to_string())


if __name__ == "__main__":
    main()
