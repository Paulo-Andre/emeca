import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError
from django.utils import timezone
from django.utils.text import slugify

from site_publico.boletim_services import gerar_pdf_boletim
from site_publico.models import ConfiguracaoSite

from usuarioSec.models import EnvioBoletimWhatsApp, ItemEnvioBoletimWhatsApp, TelefoneDeclaracao
from usuarioSec.sessao_whatsapp import sessao_atual_id
from usuarioSec.whatsapp_gateway import WhatsAppGatewayError, enviar_documento, confirmar_operacao_wa
from usuarioSec.whatsapp_views import _normalizar_jid


def _legenda(envio, item, escola):
    boletim = item.boletim
    modelo = (envio.mensagem or "").strip()
    if not modelo:
        return (
            f"Olá! Segue o boletim escolar de {boletim.aluno.nome_oficial}, referente ao "
            f"{boletim.periodo.nome_periodo} de {boletim.periodo.ano}. "
            f"Documento enviado pela {escola}."
        )

    substituicoes = {
        "{aluno}": boletim.aluno.nome_oficial,
        "{periodo}": boletim.periodo.nome_periodo,
        "{ano}": str(boletim.periodo.ano),
        "{turma}": boletim.periodo.turma,
        "{escola}": escola,
    }
    for chave, valor in substituicoes.items():
        modelo = modelo.replace(chave, valor)
    return modelo


def validar_destinatario_do_boletim(item):
    """Barreira de privacidade antes de transmitir documentos escolares.

    O lote pode ter sido criado antes da alteração de telefone, de Declaração
    ou da retirada da publicação do período. Nunca enviar com esses dados
    desatualizados: exige uma nova seleção pela Secretaria.
    """
    boletim = item.boletim
    if not boletim.periodo.publicado:
        raise WhatsAppGatewayError(
            "Boletim deixou de estar publicado. Revise e selecione novamente."
        )
    declaracao_id = boletim.aluno.declaracao_id
    if not declaracao_id:
        raise WhatsAppGatewayError(
            "Boletim está sem vínculo confirmado com Declarações."
        )
    telefones = TelefoneDeclaracao.objects.filter(declaracao_id=declaracao_id)
    if not any(
        _normalizar_jid(telefone.telefone) == item.jid
        for telefone in telefones
    ):
        raise WhatsAppGatewayError(
            "Contato não pertence mais ao cadastro atual da Declaração. "
            "Revise os destinatários antes de criar outro envio."
        )


def confirmar_aceite_documento(resposta):
    """Aceite da API não é comprovante de entrega no aparelho destinatário."""
    return confirmar_operacao_wa(resposta, "envio do PDF do boletim")


def recuperar_lotes_obsoletos():
    limite = timezone.now() - timedelta(hours=6)
    obsoletos = EnvioBoletimWhatsApp.objects.filter(
        status="PROCESSANDO",
        iniciado_em__lt=limite,
    )
    for envio in obsoletos:
        envio.itens.filter(status="PROCESSANDO").update(
            status="ERRO",
            erro="Processamento interrompido há mais de 6 horas.",
        )
        EnvioBoletimWhatsApp.objects.filter(
            pk=envio.pk,
            status="PROCESSANDO",
        ).update(status="PENDENTE")


def claim_proximo_lote():
    candidato_id = (
        EnvioBoletimWhatsApp.objects
        .filter(status="PENDENTE", sessao=sessao_atual_id())
        .order_by("criado_em")
        .values_list("pk", flat=True)
        .first()
    )
    if candidato_id is None:
        return None

    assumido = EnvioBoletimWhatsApp.objects.filter(
        pk=candidato_id,
        status="PENDENTE",
    ).update(
        status="PROCESSANDO",
        iniciado_em=timezone.now(),
    )
    if assumido != 1:
        return None
    return EnvioBoletimWhatsApp.objects.get(pk=candidato_id)


class Command(BaseCommand):
    help = "Processa a fila de boletins personalizados enviados pelo WhatsApp."

    def handle(self, *args, **options):
        while True:
            try:
                recuperar_lotes_obsoletos()
                break
            except (OperationalError, ProgrammingError):
                time.sleep(3)

        self.stdout.write(self.style.SUCCESS("Worker de boletins do WhatsApp iniciado."))

        while True:
            try:
                envio = claim_proximo_lote()
            except (OperationalError, ProgrammingError):
                time.sleep(3)
                continue

            if not envio:
                time.sleep(3)
                continue

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
                        # O usuário pode ter alterado a Declaração ou o contato
                        # enquanto o lote aguardava na fila.
                        validar_destinatario_do_boletim(item)
                        arquivo = gerar_pdf_boletim(item.boletim, config)
                        conteudo = arquivo.getvalue()
                        arquivo.close()

                        aluno_slug = slugify(item.boletim.aluno.nome_oficial) or "aluno"
                        periodo_slug = slugify(item.boletim.periodo.nome_periodo) or "periodo"
                        nome_arquivo = (
                            f"boletim-{aluno_slug}-{periodo_slug}-"
                            f"{item.boletim.periodo.ano}.pdf"
                        )

                        if envio.sessao != sessao_atual_id():
                            raise WhatsAppGatewayError(
                                "Conta WhatsApp alterada: envio da sessão anterior cancelado."
                            )
                        resposta_gateway = enviar_documento(
                            item.jid,
                            conteudo,
                            nome_arquivo,
                            _legenda(envio, item, escola),
                            sessao_id=envio.sessao,
                        )
                        # HTTP 200 com status:false ou resposta vazia nunca
                        # deve gerar um falso "ENVIADO".
                        confirmar_aceite_documento(resposta_gateway)

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
