from apps.data import assets
from apps.data.models import MarketData


def rows():
    """The current asset's daily closes (Bitcoin unless the code runs inside assets.use)."""
    asset = assets.current()
    return MarketData.objects.filter(source=asset.price_source, field=asset.price_field("close"))


def closes(start, end):
    """{date: close} from start to end inclusive."""
    return dict(rows().filter(date__range=(start, end)).values_list("date", "value"))


def latest_close_date():
    row = rows().order_by("-date").first()
    return row.date if row else None
