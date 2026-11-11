"""How the pages show stored numbers: a readable name and a sensible rounding for each field.

Display only: nothing here feeds a score. The stored values keep their full precision.
"""

import os
import re

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.filter
def domain(agent):
    """An agent's domain without its asset ("gold_macro" -> "macro"): the name of its colour."""
    return str(agent).removeprefix("gold_")


@register.filter
def lower_unless_name(label):
    """A market's name inside a sentence: "Bitcoin" keeps its capital, "Gold" becomes "gold"."""
    return label if label == "Bitcoin" else label.lower()

# Names for the fields of AgentRun.key_data, which are code names (rsi_14, dxy_change_1m_pct).
LABELS = {
    "close": "Close", "rsi_14": "RSI (14 days)", "sma_20": "20-day average", "sma_50": "50-day average",
    "sma_200": "200-day average", "support": "Support", "resistance": "Resistance", "near_support": "Near support",
    "near_resistance": "Near resistance", "change_7d_pct": "7-day change", "change_30d_pct": "30-day change",
    "macd_cross_3d": "MACD cross (last 3 days)", "volatility_14d_pct": "Daily volatility (14 days)",
    "price_vs_sma_20_pct": "Price vs 20-day average", "price_vs_sma_50_pct": "Price vs 50-day average",
    "price_vs_sma_200_pct": "Price vs 200-day average",
    "funding_rate": "Funding rate (last)", "funding_rate_7d_avg": "Funding rate (7-day average)",
    "funding_rate_30d_avg": "Funding rate (30-day average)", "long_account_ratio": "Accounts long",
    "long_account_share": "Accounts long", "long_account_ratio_90d_avg": "Accounts long (90-day average)",
    "price_change_3d_pct": "Price change (3 days)", "open_interest_change_3d_pct": "Open interest change (3 days)",
    "long_liquidations_usd_1d": "Long liquidations (1 day)", "short_liquidations_usd_1d": "Short liquidations (1 day)",
    "long_liquidations_usd_3d_avg": "Long liquidations (3-day average)",
    "dxy": "Dollar index", "nasdaq": "Nasdaq", "nasdaq_sma_50": "Nasdaq 50-day average",
    "nasdaq_vs_sma_50_pct": "Nasdaq vs its 50-day average", "cpi_yoy_pct": "Inflation (CPI, year on year)",
    "cpi_surprise_pct": "CPI vs its recent trend", "treasury_2y": "2-year Treasury yield",
    "treasury_2y_change_20d": "2-year yield change (20 days)", "cuts_expected": "Rate cut expected",
    "fed_target_upper": "Fed target (upper)", "fed_funds_effective": "Fed funds rate",
    "fed_rate_change_60d": "Fed move (last 60 days)", "two_year_minus_fed_funds_pct": "2-year yield minus Fed funds",
    "dxy_change_1m_pct": "Dollar change (1 month)", "dxy_change_2w_pct": "Dollar change (2 weeks)",
    "etf_net_flow_5d_musd": "ETF net flow (5 days)", "nasdaq_change_5d_pct": "Nasdaq change (5 days)",
    "nasdaq_change_20d_pct": "Nasdaq change (20 days)", "sp500_change_20d_pct": "S&P 500 change (20 days)",
    "vix": "VIX", "move": "MOVE (bond volatility)", "nfci": "Financial conditions (NFCI)",
    "vix_change_20d": "VIX change (20 days)", "move_change_20d_pct": "MOVE change (20 days)",
    "btc_change_1d_pct": "Bitcoin today", "nasdaq_change_1d_pct": "Nasdaq today",
    "dxy_change_5d_pct": "Dollar change (5 days)", "dxy_change_20d_pct": "Dollar change (20 days)",
    "dxy_change_60d_pct": "Dollar change (60 days)", "dxy_vs_sma_50_pct": "Dollar vs its 50-day average",
    "gold_minus_dxy_20d_pct": "Gold's 20-day move minus the dollar's",
    "gold_dxy_correlation_60d": "Gold-dollar correlation (60 days)",
    "treasury_10y": "10-year Treasury yield", "treasury_10y_change_20d": "10-year yield, 20-day change",
    "real_yield_10y": "10-year real yield", "real_yield_10y_change_5d": "Real yield, 5-day change",
    "real_yield_10y_change_20d": "Real yield, 20-day change",
    "btc_minus_dxy_20d_pct": "Bitcoin's 20-day move minus the dollar's",
    "btc_dxy_correlation_60d": "Bitcoin-dollar correlation (60 days)",
}
# Shown as percentages although their names do not end in _pct.
YIELDS = {"treasury_2y", "treasury_10y", "real_yield_10y", "fed_target_upper", "fed_funds_effective"}
PRICES = {"close", "sma_20", "sma_50", "sma_200", "support", "resistance"}
FED_MOVES = {1: "Hike", -1: "Cut", 0: "None"}
# "rsi_14 = 34.0068 points down (-0.10)": how ai/ml.py words what pushed a logistic model.
PUSH = re.compile(r"^(\w+) = (\S+) points (up|down) \(([+-][\d.]+)\)$")
# "cpi_yoy_pct = 3.9349 (weight 19%)": the same for a forest.
WEIGHT = re.compile(r"^(\w+) = (\S+) \(weight (\d+)%\)$")


@register.filter
def field_label(key):
    return LABELS.get(key) or str(key).replace("_pct", "").replace("_", " ").capitalize()


def number(value, digits):
    return f"{value:,.{digits}f}"


@register.filter
def field_value(value, key=""):
    """A stored number in the unit its field name implies."""
    if value is None or value == "":
        return "–"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if not isinstance(value, (int, float)):
        return value
    if key == "fed_rate_change_60d":
        return FED_MOVES.get(value, value)
    if key.startswith("funding_rate"):
        return f"{value * 100:.4f}%"  # stored as a share per 8 hours
    if key.startswith("long_account"):
        return f"{value * 100:.1f}%"
    if key.endswith("_pct"):
        return f"{value:+.2f}%" if "change" in key or "_vs_" in key or "surprise" in key or "minus" in key else f"{value:.2f}%"
    if key in YIELDS:
        return f"{value:.2f}%"
    if key in PRICES or "_usd" in key:
        return f"${number(value, 0)}"
    if key.endswith("_musd"):
        return f"${number(value, 0)}M"
    if "change" in key:
        return f"{value:+.2f}"
    return number(value, 0 if abs(value) >= 1000 else 2)


def reason_value(key, raw):
    try:
        return field_value(float(raw), key)
    except ValueError:
        return raw


@register.filter
def ml_reason(line):
    """An ML reason with the field's readable name and rounded value."""
    pushed = PUSH.match(line)
    if pushed:
        key, raw, way, size = pushed.groups()
        arrow = "▲ pushes the score up" if way == "up" else "▼ pushes the score down"
        return f"{field_label(key)} {reason_value(key, raw)}: {arrow}"
    weighted = WEIGHT.match(line)
    if weighted:
        key, raw, weight = weighted.groups()
        return f"{field_label(key)} {reason_value(key, raw)} (weight {weight}%)"
    return line


@register.filter
def signed(value, digits=1):
    """+3.1 / -2.0: a number that always shows its sign."""
    if value is None or value == "":
        return "–"
    return f"{value:+.{int(digits)}f}"


@register.filter
def strategy_name(name):
    """"rules:technical" -> "Rules · Technical": the saved backtest names, readable."""
    return " · ".join(part.replace("_", " ").capitalize() for part in str(name).split(":"))


@register.simple_tag
def versioned_static(path):
    """A static file's URL with its last-modified time, so the browser never shows a stale
    stylesheet or script after an edit."""
    found = finders.find(path)
    return f"{static(path)}?v={int(os.path.getmtime(found))}" if found else static(path)
