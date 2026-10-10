from django.apps import AppConfig


class HistoricoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "historico"

    def ready(self):
        # Registra PRAGMAs defensivos/concorrentes para o SQLite.
        from . import db  # noqa: F401
