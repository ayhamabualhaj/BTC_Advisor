from django.utils import timezone

from apps.data.models import MarketData


def save_points(source, points):
    """Insert or update points; collecting the same range twice is safe."""
    now = timezone.now()
    rows = [
        MarketData(date=p.date, source=source, field=p.field, value=p.value, fetched_at=now)
        for p in points
    ]
    MarketData.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["date", "source", "field"],
        update_fields=["value", "fetched_at"],
        batch_size=500,
    )
    return len(rows)


def dates_for(source, field, start, end):
    return set(
        MarketData.objects.filter(source=source, field=field, date__range=(start, end))
        .values_list("date", flat=True)
    )


def fields_for(source):
    return sorted(set(MarketData.objects.filter(source=source).values_list("field", flat=True)))
