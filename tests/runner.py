from django.conf import settings
from django.test.runner import DiscoverRunner


class Runner(DiscoverRunner):
    """Runs the tests with the defaults, not the user's .env: they assume Opus as AI_MODEL."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        settings.AI_MODEL = "claude-opus-5-5"
