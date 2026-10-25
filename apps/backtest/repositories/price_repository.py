from apps.data.models import MarketData


def closes(start, end):
    """{date: BTC close} from start to end inclusive."""
    rows = MarketData.objects.filter(source="binance", field="close", date__range=(start, end))
    return dict(rows.values_list("date", "value"))


def latest_close_date():
    row = MarketData.objects.filter(source="binance", field="close").order_by("-date").first()
    return row.date if row else None
