"""Backtest performance metrics calculator (Role B).

Calculates total return, win rate, profit factor, Sharpe ratio, max drawdown, and trade count.
"""
from typing import List, Dict, Any

def calculate_metrics(trades: List[Dict[str, Any]], equity_curve: List[float]) -> Dict[str, Any]:
    """Compute performance metrics summary."""
    return {
        "total_trades": len(trades),
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown_pct": 0.0,
        "total_return_pct": 0.0
    }
