from django.contrib import admin

from .models import AgentRun, MemoryCase, PromptVersion


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ("date", "agent", "rule_score", "opus_score", "direction", "cost_usd", "is_backtest")
    list_filter = ("agent", "direction", "is_backtest")
    date_hierarchy = "date"


@admin.register(PromptVersion)
class PromptVersionAdmin(admin.ModelAdmin):
    list_display = ("agent", "version", "created_at")
    list_filter = ("agent",)


@admin.register(MemoryCase)
class MemoryCaseAdmin(admin.ModelAdmin):
    list_display = ("date", "agent", "return_7d_pct")
    list_filter = ("agent",)
