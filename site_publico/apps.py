from django.apps import AppConfig


class SitePublicoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "site_publico"
    verbose_name = "Site público da escola"

    def ready(self):
        # Conecta a sincronização somente dos campos de identificação dos boletins.
        from . import signals  # noqa: F401
