from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase


class ProjectSetupTests(SimpleTestCase):
    def test_project_apps_are_installed(self):
        for label in ("data", "agents", "backtest", "dashboard"):
            self.assertTrue(apps.is_installed(f"apps.{label}"), label)

    def test_env_example_lists_every_setting_read_from_env(self):
        # Lesson from Chess Coach: .env.example must match settings exactly.
        example = (settings.BASE_DIR / ".env.example").read_text()
        keys = {line.split("=")[0] for line in example.splitlines() if "=" in line}
        source = (settings.BASE_DIR / "config" / "settings.py").read_text()
        for key in keys:
            self.assertIn(f'"{key}"', source, key)
        for key in ("SECRET_KEY", "ANTHROPIC_API_KEY", "FRED_API_KEY"):
            self.assertIn(key, keys)
