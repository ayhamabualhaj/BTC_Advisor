from rest_framework import serializers

from apps.agents.models import AgentRun, PromptVersion
from apps.backtest.models import BacktestRun, Decision


class AgentRunSerializer(serializers.ModelSerializer):
    prompt_version = serializers.IntegerField(source="prompt_version.version", default=None)

    class Meta:
        model = AgentRun
        fields = ["id", "date", "agent", "rule_score", "opus_score", "direction", "reasons", "key_data",
                  "suggested_stop_loss", "prompt_version", "input_tokens", "output_tokens", "cost_usd",
                  "is_backtest", "error", "created_at"]


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = ["date", "technical_score", "derivatives_score", "macro_score", "signal",
                  "threshold", "agents_required", "created_at"]


class BacktestRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = BacktestRun
        fields = ["id", "name", "start_date", "end_date", "settings", "trade_count", "win_rate",
                  "total_profit_pct", "max_drawdown_pct", "buy_and_hold_pct", "created_at"]


class PromptVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptVersion
        fields = ["agent", "version", "prompt_text", "notes", "created_at"]


class PromptHistorySerializer(serializers.Serializer):
    version = PromptVersionSerializer()
    runs = serializers.IntegerField()
    backtest_runs = serializers.IntegerField()
    errors = serializers.IntegerField()
    cost_usd = serializers.DecimalField(max_digits=12, decimal_places=6)
    avg_opus_score = serializers.FloatField(allow_null=True)
    hit_rate_7d = serializers.FloatField(allow_null=True)
    judged_calls = serializers.IntegerField()
