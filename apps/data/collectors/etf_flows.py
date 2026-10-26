"""Spot Bitcoin ETF daily net flows (US$ millions) from Farside's table.

farside.co.uk is behind a Cloudflare check that blocks scripts, so the table is copied from
a browser and imported with: python manage.py import_etf_flows <file>
The file may be a CSV, tab-separated text, or the table pasted as one cell per line (what
Firefox copies). It needs a date column and a "Total" column; other columns are ignored.
A trading day's flows are only complete after the US close (some funds report the next
morning), so each value is dated one day after its trading day, like FRED's daily series.
"""

import csv
import datetime

from .base import CollectorError, Point

SOURCE = "farside"
KNOWN_AFTER = datetime.timedelta(days=1)
DATE_FORMATS = ("%d %b %Y", "%Y-%m-%d", "%d/%m/%Y")


def table_rows(lines):
    """The table as lists of cells, whatever way it was copied."""
    first = [line for line in lines if line.strip()][:3]
    if any("," in line for line in first):
        return list(csv.reader(lines))
    if any("\t" in line for line in first):
        return list(csv.reader(lines, delimiter="\t"))
    # One cell per line: the header runs up to "Total", then each row has as many cells.
    cells = [line.strip() for line in lines if line.strip()]
    if "Total" not in cells:
        return []
    width = cells.index("Total") + 1
    return [cells[i:i + width] for i in range(0, len(cells), width)]


def parse_csv(lines):
    header = None
    points = []
    for row in table_rows(lines):
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
        total_at = header.index("Total")
        funds = cells[1:total_at]
        total = parse_amount(cells[total_at])
        if not total and funds and all(cell in ("", "-") for cell in funds):
            continue  # no fund reported (a holiday, or today before the data is in): not a real 0
        if total is not None:
            points.append(Point(day + KNOWN_AFTER, "etf_net_flow_musd", total))
    if header is None:
        raise CollectorError("No 'Total' column found in the ETF flows file")
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
