import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError
from django.utils import timezone
from django.utils.text import slugify

from site_publico.boletim_services import gerar_pdf_boletim
from site_publico.models import ConfiguracaoSite

from usuarioSec.models import EnvioBoletimWhatsApp, ItemEnvioBoletimWhatsApp
from usuarioSec.whatsapp_gateway import WhatsAppGatewayError, enviar_documento


def _legenda(envio, item, escola):
    boletim = item.boletim
    modelo = (envio.mensagem or "").strip()
    if not modelo:
        return (
            f"Olá! Segue o boletim escolar de {boletim.aluno.nome}, referente ao "
            f"{boletim.periodo.nome_periodo} de {boletim.periodo.ano}. "
            f"Documento enviado pela {escola}."
        )

    substituicoes = {
        "{aluno}": boletim.aluno.nome,
        "{periodo}": boletim.periodo.nome_periodo,
        "{ano}": str(boletim.periodo.ano),
        "{turma}": boletim.periodo.turma,
        "{escola}": escola,
    }
    for chave, valor in substituicoes.items():
        modelo = modelo.replace(chave, valor)
    return modelo


class Command(BaseCommand):
    help = "Processa a fila de boletins personalizados enviados pelo WhatsApp."

    def handle(self, *args, **options):
        # Aguarda o container web concluir as migrações quando os dois serviços
        # sobem juntos pela primeira vez.
        while True:
            try:
                ItemEnvioBoletimWhatsApp.objects.filter(status="PROCESSANDO").update(
                    status="ERRO",
                    erro="Envio interrompido durante o processamento. Reenvie este boletim se necessário.",
                )
                EnvioBoletimWhatsApp.objects.filter(status="PROCESSANDO").update(
                    status="PENDENTE"
                )
                break
            except (OperationalError, ProgrammingError):
                time.sleep(3)

        self.stdout.write(self.style.SUCCESS("Worker de boletins do WhatsApp iniciado."))

        while True:
            try:
                envio = (
                    EnvioBoletimWhatsApp.objects
                    .filter(status="PENDENTE")
                    .order_by("criado_em")
                    .first()
                )
            except (OperationalError, ProgrammingError):
                time.sleep(3)
                continue

            if not envio:
                time.sleep(3)
                continue

            envio.status = "PROCESSANDO"
            envio.iniciado_em = timezone.now()
            envio.save(update_fields=["status", "iniciado_em"])

            config = ConfiguracaoSite.objects.first()
            escola = (
                config.nome_escola
                if config and config.nome_escola
                else "E. M. Egídio Cordeiro Aquino"
            )

            try:
                itens = list(
                    envio.itens
                    .filter(status="PENDENTE")
                    .select_related("boletim__aluno", "boletim__periodo")
                    .prefetch_related("boletim__resultados__disciplina")
                    .order_by("id")
                )

                for indice, item in enumerate(itens):
                    item.status = "PROCESSANDO"
                    item.erro = ""
                    item.save(update_fields=["status", "erro"])

                    try:
                        arquivo = gerar_pdf_boletim(item.boletim, config)
                        conteudo = arquivo.getvalue()
                        arquivo.close()

                        aluno_slug = slugify(item.boletim.aluno.nome) or "aluno"
                        periodo_slug = slugify(item.boletim.periodo.nome_periodo) or "periodo"
                        nome_arquivo = (
                            f"boletim-{aluno_slug}-{periodo_slug}-"
                            f"{item.boletim.periodo.ano}.pdf"
                        )

                        enviar_documento(
                            item.jid,
                            conteudo,
                            nome_arquivo,
                            _legenda(envio, item, escola),
                        )

                        item.status = "ENVIADO"
                        item.enviado_em = timezone.now()
                        item.save(update_fields=["status", "enviado_em"])
                    except WhatsAppGatewayError as exc:
                        item.status = "ERRO"
                        item.erro = str(exc)[:500]
                        item.save(update_fields=["status", "erro"])
                    except Exception as exc:
                        item.status = "ERRO"
                        item.erro = f"Falha ao gerar ou enviar o PDF: {exc}"[:500]
                        item.save(update_fields=["status", "erro"])

                    if indice < len(itens) - 1:
                        time.sleep(settings.WA_AKG_BROADCAST_DELAY_MS / 1000)

                enviados = envio.itens.filter(status="ENVIADO").count()
                falhas = envio.itens.filter(status="ERRO").count()
                envio.enviados = enviados
                envio.falhas = falhas
                envio.status = "COM_ERROS" if falhas else "CONCLUIDO"
                envio.concluido_em = timezone.now()
                envio.save(
                    update_fields=[
                        "enviados",
                        "falhas",
                        "status",
                        "concluido_em",
                    ]
                )
            except Exception as exc:
                envio.status = "FALHOU"
                envio.falhas = envio.itens.exclude(status="ENVIADO").count()
                envio.concluido_em = timezone.now()
                envio.save(update_fields=["status", "falhas", "concluido_em"])
                self.stderr.write(f"Falha no lote {envio.pk}: {exc}")
