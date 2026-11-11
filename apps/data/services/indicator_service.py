"""Builds each agent's numbers for a decision date from stored data up to that date only.

These snapshots are the `key_data` that the rule scores use and that Opus is shown.
A value is None when its data is missing; the scoring rules skip those criteria.
"""

from apps.data.indicators import levels, macro, momentum, relative, trend
from apps.data.repositories.market_data_repository import series

# 200-day average plus room for MACD warm-up.
PRICE_HISTORY_DAYS = 260
# Ignore a data series whose latest value is older than this many days.
MAX_STALE_DAYS = 5
# NFCI is weekly and published 5 days after its week ends, so it is up to 13 days old.
WEEKLY_STALE_DAYS = 14
# The Nasdaq's previous close may be up to a long weekend back.
NASDAQ_GAP_DAYS = 4
# A year of CPI needs 13 months; one more print in case a month was never published.
CPI_PRINTS = 14
# The dollar agent compares 60 trading days of the dollar index with Bitcoin on the same days.
DOLLAR_DAYS = 61
# The long/short ratio is judged against its own recent average.
LS_HISTORY_DAYS = 90


def values(source, field, date, limit, max_stale_days=MAX_STALE_DAYS):
    rows = series(source, field, date, limit)
    if not rows or (date - rows[-1][0]).days > max_stale_days:
        return []
    return [value for _, value in rows]


def rounded(value, digits=4):
    return round(value, digits) if isinstance(value, float) else value


def cpi_observations(date):
    """The latest CPI prints as [(month number, value)], each with the month it measures.

    Monthly series are only refreshed once a month, so they are not checked for staleness.
    A print stored without its month (collected before months were kept) cannot be placed,
    so the series is left out rather than guessed: run collect_data --source fred.
    """
    prints = series("fred", "cpi", date, CPI_PRINTS)
    months = dict(series("fred", "cpi_month", date, CPI_PRINTS))
    if any(day not in months for day, _ in prints):
        return []
    return [(macro.month_number(months[day]), value) for day, value in prints]


def technical_snapshot(date):
    closes = values("binance", "close", date, PRICE_HISTORY_DAYS)
    highs = values("binance", "high", date, PRICE_HISTORY_DAYS)
    lows = values("binance", "low", date, PRICE_HISTORY_DAYS)
    if not closes:
        return {"close": None}
    close = closes[-1]
    snapshot = {
        "close": close,
        "sma_20": trend.sma(closes, 20),
        "sma_50": trend.sma(closes, 50),
        "sma_200": trend.sma(closes, 200),
        "rsi_14": momentum.rsi(closes, 14),
        "macd_cross_3d": momentum.macd_cross(closes, 3),
        "change_7d_pct": trend.pct_change(closes, 7),
        "change_30d_pct": trend.pct_change(closes, 30),
        "volatility_14d_pct": trend.volatility(closes, 14),
        **levels.support_resistance(highs, lows, close),
    }
    return {key: rounded(value) for key, value in snapshot.items()}


def derivatives_snapshot(date):
    funding = values("bybit", "funding_rate", date, 30)
    open_interest = values("bybit", "open_interest", date, 8)
    closes = values("binance", "close", date, 8)
    long_ratio = values("bybit", "long_account_ratio", date, LS_HISTORY_DAYS)
    long_liq = values("okx", "long_liquidations_usd", date, 3)
    short_liq = values("okx", "short_liquidations_usd", date, 3)
    snapshot = {
        "funding_rate": funding[-1] if funding else None,
        "funding_rate_7d_avg": trend.sma(funding, 7),
        "funding_rate_30d_avg": trend.sma(funding, 30),
        "open_interest_change_3d_pct": trend.pct_change(open_interest, 3),
        "price_change_3d_pct": trend.pct_change(closes, 3),
        "long_account_ratio": long_ratio[-1] if long_ratio else None,
        "long_account_ratio_90d_avg": trend.sma(long_ratio, len(long_ratio)) if long_ratio else None,
        "long_liquidations_usd_1d": long_liq[-1] if long_liq else None,
        "long_liquidations_usd_3d_avg": trend.sma(long_liq, 3),
        "short_liquidations_usd_1d": short_liq[-1] if short_liq else None,
    }
    return {key: rounded(value, 6) for key, value in snapshot.items()}


def macro_snapshot(date):
    dxy = values("yahoo", "dxy_close", date, 30)
    nasdaq = values("yahoo", "nasdaq_close", date, 60)
    sp500 = values("yahoo", "sp500_close", date, 30)
    target = values("fred", "fed_target_upper", date, 60)
    fed_funds = values("fred", "fed_funds_effective", date, 5)
    treasury_2y = values("fred", "treasury_2y", date, 30)
    cpi = cpi_observations(date)
    etf = values("farside", "etf_net_flow_musd", date, 5)
    snapshot = {
        "dxy": dxy[-1] if dxy else None,
        # Ten trading days is two calendar weeks.
        "dxy_change_2w_pct": trend.pct_change(dxy, 10),
        "dxy_change_1m_pct": trend.pct_change(dxy, 20),
        "nasdaq": nasdaq[-1] if nasdaq else None,
        "nasdaq_sma_50": trend.sma(nasdaq, 50),
        # In trading days: a week and about a month.
        "nasdaq_change_5d_pct": trend.pct_change(nasdaq, 5),
        "nasdaq_change_20d_pct": trend.pct_change(nasdaq, 20),
        "sp500_change_20d_pct": trend.pct_change(sp500, 20),
        "fed_target_upper": target[-1] if target else None,
        "fed_rate_change_60d": macro.last_rate_change(target, 60) if target else None,
        "treasury_2y": treasury_2y[-1] if treasury_2y else None,
        "fed_funds_effective": fed_funds[-1] if fed_funds else None,
        # In percentage points over about a month of trading days.
        "treasury_2y_change_20d": treasury_2y[-1] - treasury_2y[-21] if len(treasury_2y) >= 21 else None,
        "cuts_expected": macro.cuts_expected(
            treasury_2y[-1] if treasury_2y else None, fed_funds[-1] if fed_funds else None
        ),
        "cpi_yoy_pct": macro.yoy_inflation(cpi),
        "cpi_surprise_pct": macro.cpi_surprise(cpi),
        "etf_net_flow_5d_musd": trend.rolling_sum(etf, 5),
    }
    return {key: rounded(value) for key, value in snapshot.items()}


def stress_snapshot(date):
    """Fear in US markets: stock volatility (VIX), bond volatility (MOVE), financial conditions (NFCI)."""
    vix = values("fred", "vix", date, 21)
    move = values("yahoo", "move_close", date, 21)
    nfci = values("fred", "nfci", date, 1, max_stale_days=WEEKLY_STALE_DAYS)
    snapshot = {
        "vix": vix[-1] if vix else None,
        # Over about a month of trading days, in VIX points.
        "vix_change_20d": vix[-1] - vix[-21] if len(vix) >= 21 else None,
        "move": move[-1] if move else None,
        "move_change_20d_pct": trend.pct_change(move, 20),
        "nfci": nfci[-1] if nfci else None,
    }
    return {key: rounded(value) for key, value in snapshot.items()}


def dollar_snapshot(date):
    """The dollar index's moves over 5, 20 and 60 trading days, and Bitcoin against it.

    The index does not trade at weekends, so its last close stands until Monday; Bitcoin is
    compared with it on the index's own trading days.
    """
    empty = {"dxy_change_5d_pct": None, "dxy_change_20d_pct": None, "dxy_change_60d_pct": None,
             "dxy_vs_sma_50_pct": None, "btc_minus_dxy_20d_pct": None, "btc_dxy_correlation_60d": None}
    rows = series("yahoo", "dxy_close", date, DOLLAR_DAYS)
    if len(rows) < DOLLAR_DAYS or (date - rows[-1][0]).days > MAX_STALE_DAYS:
        return empty
    dxy = [value for _, value in rows]
    # Enough calendar days of Bitcoin to cover the index's 61 trading days.
    btc = dict(series("binance", "close", date, (date - rows[0][0]).days + 1))
    btc_on_dxy_days = [btc.get(day) for day, _ in rows]
    if date not in btc or any(close is None for close in btc_on_dxy_days):
        return empty
    dxy_20d = trend.pct_change(dxy, 20)
    btc_20d = (btc[date] / btc_on_dxy_days[-21] - 1) * 100
    snapshot = {
        "dxy_change_5d_pct": trend.pct_change(dxy, 5),
        "dxy_change_20d_pct": dxy_20d,
        "dxy_change_60d_pct": trend.pct_change(dxy, 60),
        "dxy_vs_sma_50_pct": (dxy[-1] / trend.sma(dxy, 50) - 1) * 100,
        "btc_minus_dxy_20d_pct": btc_20d - dxy_20d,
        "btc_dxy_correlation_60d": relative.correlation(relative.returns(dxy), relative.returns(btc_on_dxy_days)),
    }
    return {key: rounded(value) for key, value in snapshot.items()}


def riskon_snapshot(date):
    """Today's move of Bitcoin and of the Nasdaq; the Nasdaq's is None unless it traded on `date`.

    The Nasdaq closes at 20:00-21:00 UTC, before Bitcoin's daily close at 24:00 UTC, so both
    are known by the end of `date`.
    """
    btc = series("binance", "close", date, 2)
    nasdaq = series("yahoo", "nasdaq_close", date, 2)
    btc_known = len(btc) == 2 and btc[-1][0] == date and (date - btc[0][0]).days == 1
    nasdaq_known = len(nasdaq) == 2 and nasdaq[-1][0] == date and (date - nasdaq[0][0]).days <= NASDAQ_GAP_DAYS
    snapshot = {
        "btc_change_1d_pct": (btc[1][1] / btc[0][1] - 1) * 100 if btc_known else None,
        "nasdaq_change_1d_pct": (nasdaq[1][1] / nasdaq[0][1] - 1) * 100 if nasdaq_known else None,
    }
    return {key: rounded(value) for key, value in snapshot.items()}
