def format_run(run):
    win = f"{run.win_rate:5.1f}%" if run.win_rate is not None else "    -"
    return (f"{run.name:<26} trades {run.trade_count:3d}  win {win}  "
            f"profit {run.total_profit_pct:+7.2f}%  max drawdown {run.max_drawdown_pct:6.2f}%  "
            f"days in market {run.settings.get('days_in_market', 0):3d}")


def format_hold(run):
    return (f"{'buy and hold':<26} profit {run.buy_and_hold_pct:+7.2f}%  "
            f"max drawdown {run.settings.get('buy_and_hold_drawdown_pct', 0):6.2f}%")
