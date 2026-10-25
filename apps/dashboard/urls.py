from django.urls import path

from .views import page_views

urlpatterns = [
    path("", page_views.today, name="today"),
    path("agents/<str:agent>/", page_views.agent_detail, name="agent_detail"),
    path("backtests/", page_views.backtests, name="backtests"),
    path("costs/", page_views.costs, name="costs"),
    path("prompts/", page_views.prompts, name="prompts"),
]
