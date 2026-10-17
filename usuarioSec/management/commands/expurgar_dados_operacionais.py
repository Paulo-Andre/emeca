from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from historico.models import AuditoriaEvento
from site_publico.models import MensagemContato
from usuarioSec.models import EnvioBoletimWhatsApp, SecurityRateLimit


class Command(BaseCommand):
    help = "Expurga somente dados operacionais conforme a política de retenção."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        agora = timezone.now()
        regras = [
            (
                "rate limits",
                SecurityRateLimit.objects.filter(
                    atualizado_em__lt=agora - timedelta(days=settings.RETENTION_RATE_LIMIT_DAYS)
                ),
            ),
            (
                "lotes WhatsApp concluídos",
                EnvioBoletimWhatsApp.objects.filter(
                    status__in=["CONCLUIDO", "COM_ERROS", "FALHOU"],
                    criado_em__lt=agora - timedelta(days=settings.RETENTION_WHATSAPP_DAYS),
                ),
            ),
            (
                "mensagens de contato",
                MensagemContato.objects.filter(
                    criado_em__lt=agora - timedelta(days=settings.RETENTION_CONTATO_DAYS)
                ),
            ),
            (
                "eventos de auditoria",
                AuditoriaEvento.objects.filter(
                    criado_em__lt=agora - timedelta(days=settings.RETENTION_AUDIT_DAYS)
                ),
            ),
        ]

        for rotulo, queryset in regras:
            quantidade = queryset.count()
            if options["dry_run"]:
                self.stdout.write(f"{rotulo}: {quantidade} registro(s) seriam removidos.")
            else:
                queryset.delete()
                self.stdout.write(f"{rotulo}: {quantidade} registro(s) removidos.")

        self.stdout.write(
            self.style.SUCCESS(
                "Dados acadêmicos, matrículas, históricos e boletins não foram apagados."
            )
        )
