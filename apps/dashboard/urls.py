from django.urls import path

from .views import page_views

urlpatterns = [
    path("", page_views.today, name="today"),
    path("advise/", page_views.advise, name="advise"),
    path("agents/<str:agent>/", page_views.agent_detail, name="agent_detail"),
    path("signals/", page_views.signals, name="signals"),
    path("signals/overview/", page_views.signals_overview, name="signals_overview"),
    path("profit/", page_views.profit, name="profit"),
    path("models/", page_views.models, name="models"),
    path("backtests/", page_views.backtests, name="backtests"),
    path("costs/", page_views.costs, name="costs"),
    path("prompts/", page_views.prompts, name="prompts"),
]
