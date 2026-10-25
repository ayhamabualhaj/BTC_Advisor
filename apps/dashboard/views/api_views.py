import datetime

from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.models import AgentName
from apps.dashboard.repositories import report_repository
from apps.dashboard.serializers import (
    AgentRunSerializer,
    BacktestRunSerializer,
    DecisionSerializer,
    PromptHistorySerializer,
)
from apps.dashboard.services import report_service


def parse_bool(value):
    if value is None:
        return None
    if value.lower() in ("true", "1"):
        return True
    if value.lower() in ("false", "0"):
        return False
    raise ValidationError({"backtest": "use true or false"})


class TodayView(APIView):
    """GET /api/decision/today/ — the latest decision with each agent's run."""

    def get(self, request):
        today = report_service.today()
        if today["date"] is None:
            raise NotFound("No agent runs yet; run python manage.py daily_run")
        return Response({
            "date": today["date"],
            "decision": DecisionSerializer(today["decision"]).data if today["decision"] else None,
            "agent_runs": AgentRunSerializer(today["agent_runs"], many=True).data,
        })


class AgentRunListView(generics.ListAPIView):
    """GET /api/agent-runs/?agent=technical&backtest=false&date=2026-10-24"""

    serializer_class = AgentRunSerializer

    def get_queryset(self):
        params = self.request.query_params
        agent = params.get("agent")
        if agent and agent not in AgentName.values:
            raise ValidationError({"agent": f"one of {AgentName.values}"})
        date = params.get("date")
        try:
            date = datetime.date.fromisoformat(date) if date else None
        except ValueError:
            raise ValidationError({"date": "use YYYY-MM-DD"})
        return report_repository.agent_runs(agent, parse_bool(params.get("backtest")), date)


class BacktestRunListView(generics.ListAPIView):
    """GET /api/backtests/?name=opus — runs whose name starts with the given text."""

    serializer_class = BacktestRunSerializer

    def get_queryset(self):
        return report_repository.backtest_runs(self.request.query_params.get("name"))


class CostView(APIView):
    """GET /api/costs/ — API spend per agent (live and backtest) and per day."""

    def get(self, request):
        costs = report_service.costs()
        return Response({
            "total_usd": costs["total_usd"],
            "by_agent": costs["by_agent"],
            "by_day": costs["by_day"],
        })


class PromptHistoryView(APIView):
    """GET /api/prompts/?agent=macro — every prompt version with its results."""

    def get(self, request):
        agent = request.query_params.get("agent")
        if agent and agent not in AgentName.values:
            raise ValidationError({"agent": f"one of {AgentName.values}"})
        return Response(PromptHistorySerializer(report_service.prompt_history(agent), many=True).data)
