"""Spot Bitcoin ETF daily net flows (US$ millions) from a CSV export of Farside's table.

farside.co.uk is behind a Cloudflare check that blocks scripts, so the table is saved from
a browser as CSV and imported with: python manage.py import_etf_flows <file.csv>
The CSV needs a date column and a "Total" column; other columns are ignored.
"""

import csv
import datetime

from .base import CollectorError, Point

SOURCE = "farside"
DATE_FORMATS = ("%d %b %Y", "%Y-%m-%d", "%d/%m/%Y")


def parse_csv(lines):
    reader = csv.reader(lines)
    header = None
    points = []
    for row in reader:
        cells = [cell.strip() for cell in row]
        if header is None:
            if "Total" in cells:
                header = cells
            continue
        if not cells or not cells[0]:
            continue
        day = parse_date(cells[0])
        if day is None:
            continue  # summary rows such as "Total" or "Average"
        total = parse_amount(cells[header.index("Total")])
        if total is not None:
            points.append(Point(day, "etf_net_flow_musd", total))
    if header is None:
        raise CollectorError("No 'Total' column found in the ETF flows CSV")
    return points


def parse_date(text):
    for date_format in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, date_format).date()
        except ValueError:
            pass
    return None


def parse_amount(text):
    """Farside writes outflows in brackets, e.g. (12.5) means -12.5; "-" means no data."""
    text = text.replace(",", "").strip()
    if text in ("", "-"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    value = float(text.strip("()"))
    return -value if negative else value
