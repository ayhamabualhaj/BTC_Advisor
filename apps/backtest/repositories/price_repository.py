from apps.data.models import MarketData


def closes(start, end):
    """{date: BTC close} from start to end inclusive."""
    rows = MarketData.objects.filter(source="binance", field="close", date__range=(start, end))
    return dict(rows.values_list("date", "value"))
