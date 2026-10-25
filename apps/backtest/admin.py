from django.contrib import admin

from .models import BacktestRun, Decision, ManualTrade, Outcome

admin.site.register(BacktestRun)
admin.site.register(Decision)
admin.site.register(ManualTrade)
admin.site.register(Outcome)
