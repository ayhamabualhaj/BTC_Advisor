from django.urls import path

from .views import page_views

# "/" chooses the market; every page then lives under /btc/ or /gold/.
urlpatterns = [
    path("", page_views.home, name="home"),
    path("<str:asset>/", page_views.today, name="today"),
    path("<str:asset>/advise/", page_views.advise, name="advise"),
    path("<str:asset>/agents/", page_views.agents, name="agents"),
    path("<str:asset>/agents/<str:agent>/", page_views.agent_detail, name="agent_detail"),
    path("<str:asset>/signals/", page_views.signals, name="signals"),
    path("<str:asset>/signals/overview/", page_views.signals_overview, name="signals_overview"),
    path("<str:asset>/profit/", page_views.profit, name="profit"),
    path("<str:asset>/models/", page_views.models, name="models"),
    path("<str:asset>/backtests/", page_views.backtests, name="backtests"),
    path("<str:asset>/costs/", page_views.costs, name="costs"),
    path("<str:asset>/prompts/", page_views.prompts, name="prompts"),
]
