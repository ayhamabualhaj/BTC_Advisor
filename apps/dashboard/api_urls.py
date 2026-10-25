from django.urls import path

from .views import api_views

urlpatterns = [
    path("decision/today/", api_views.TodayView.as_view(), name="api_today"),
    path("agent-runs/", api_views.AgentRunListView.as_view(), name="api_agent_runs"),
    path("backtests/", api_views.BacktestRunListView.as_view(), name="api_backtests"),
    path("costs/", api_views.CostView.as_view(), name="api_costs"),
    path("prompts/", api_views.PromptHistoryView.as_view(), name="api_prompts"),
]
