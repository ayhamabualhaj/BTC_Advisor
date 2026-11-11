from django.core.management.base import BaseCommand

from apps.data import assets


class AssetCommand(BaseCommand):
    """A command that works on one asset: `--asset gold` (default: Bitcoin)."""

    def add_arguments(self, parser):
        parser.add_argument("--asset", choices=sorted(assets.ASSETS), default=assets.DEFAULT,
                            help="Which market (default: btc)")

    def execute(self, *args, **options):
        with assets.use(options["asset"]):
            return super().execute(*args, **options)
