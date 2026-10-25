import datetime
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

USER_AGENT = "Mozilla/5.0 (BTC-Advisor data collector)"
RETRIES = 3


class CollectorError(Exception):
    """A source could not be reached or returned something unexpected."""


@dataclass(frozen=True)
class Point:
    date: datetime.date
    field: str
    value: float


def get_json(url, params=None, timeout=30):
    """GET a JSON document, retrying a few times on network errors and rate limits."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # 4xx other than "too many requests" will not fix itself on retry.
            if error.code != 429 and error.code < 500:
                raise CollectorError(f"{url} returned HTTP {error.code}") from error
            last_error = error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
        time.sleep(2 ** attempt)
    raise CollectorError(f"{url} failed after {RETRIES} attempts: {last_error}")


def to_ms(day):
    """Midnight UTC of a date, in epoch milliseconds (what the exchanges expect)."""
    return int(datetime.datetime.combine(day, datetime.time(), datetime.UTC).timestamp() * 1000)


def utc_date(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).date()


def date_known_by(ms):
    """Date of a value stamped at a moment, e.g. a funding settlement at 00:00 on the 5th
    belongs to the 4th: it is known at the end of the 4th."""
    return utc_date(ms - 1)
