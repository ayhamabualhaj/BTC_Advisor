from django.contrib import admin

from .models import MarketData


@admin.register(MarketData)
class MarketDataAdmin(admin.ModelAdmin):
    list_display = ("date", "source", "field", "value")
    list_filter = ("source", "field")
    date_hierarchy = "date"
