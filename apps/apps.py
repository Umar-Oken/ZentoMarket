from django.apps import AppConfig


class AppsConfig(AppConfig):
    name = 'apps'

    def ready(self):
        from . import signals  # noqa: F401
