import re
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError
from django.utils import timezone
from django.utils.text import slugify

from site_publico.boletim_services import gerar_pdf_boletim
from site_publico.models import BoletimAluno, ConfiguracaoSite

from usuarioSec.models import EnvioBoletimWhatsApp, ItemEnvioBoletimWhatsApp, TelefoneDeclaracao
from usuarioSec.sessao_whatsapp import sessao_atual_id
from usuarioSec.anexos_boletim_whatsapp import (
    extrair_mensagem_anexo, ler_anexo, apagar_anexo,
)
from usuarioSec.whatsapp_gateway import (
    WhatsAppGatewayError, enviar_documento, enviar_midia,
    confirmar_operacao_wa, verificar_numeros,
)
from usuarioSec.whatsapp_views import _normalizar_jid


def _legenda(envio, item, escola):
    boletim = item.boletim
    modelo, _ = extrair_mensagem_anexo(envio.mensagem)
    modelo = modelo.strip()
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
    # Buscar novamente o boletim: os objetos carregados quando o lote
    # começou podem estar desatualizados em disparos para muitas famílias.
    boletim = BoletimAluno.objects.select_related(
        "aluno", "aluno__declaracao", "periodo",
    ).get(pk=item.boletim_id)
    item.boletim = boletim
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


def _jid_eh_mesmo_numero_confirmado(jid_cadastro, jid_whatsapp):
    """Somente equivalência explícita de telefone brasileiro e 9º dígito.

    JID @lid ou um outro número não pode ser inferido como o responsável.
    O WhatsApp pode devolver o número móvel no formato legado sem o 9.
    """
    padrao = r"55[1-9][0-9][0-9]{8,9}@s\\.whatsapp\\.net"
    if not isinstance(jid_cadastro, str) or not isinstance(jid_whatsapp, str):
        return False
    if not re.fullmatch(padrao, jid_cadastro) or not re.fullmatch(padrao, jid_whatsapp):
        return False
    if jid_cadastro == jid_whatsapp:
        return True

    original = jid_cadastro.split("@", 1)[0]
    confirmado = jid_whatsapp.split("@", 1)[0]
    maior, menor = sorted((original, confirmado), key=len, reverse=True)
    # 55 + DDD(2) + 9 + 8 dígitos = 13; legado sem o 9 = 12.
    return len(maior) == 13 and len(menor) == 12 and (
        maior[:4] == menor[:4] and maior[4] == "9" and maior[5:] == menor[4:]
    )


def confirmar_jid_whatsapp_do_boletim(item):
    """Consulta o número registrado para usar exclusivamente o JID verificado.

    Falha fechada: não aceita @lid, JID inesperado, outro DDD/assinante,
    retorno ambíguo ou usuário que não existe. Nunca inventa associações.
    """
    jid_cadastro = item.jid
    if not re.fullmatch(r"55[1-9][0-9][0-9]{8,9}@s\\.whatsapp\\.net", jid_cadastro or ""):
        raise WhatsAppGatewayError(
            "Telefone cadastrado não está num formato seguro para envio do boletim."
        )
    numero = jid_cadastro.split("@", 1)[0]
    resposta = confirmar_operacao_wa(
        verificar_numeros([numero]), "verificação do destinatário do boletim"
    )
    dados = resposta.get("data")
    registros = dados.get("results") if isinstance(dados, dict) else None
    if not isinstance(registros, list) or len(registros) != 1 or not isinstance(registros[0], dict):
        raise WhatsAppGatewayError(
            "Verificação do destinatário foi inconclusiva. Boletim não enviado."
        )
    resultado = registros[0]
    if str(resultado.get("number") or numero) != numero:
        raise WhatsAppGatewayError(
            "Verificação retornou um telefone diferente. Boletim não enviado."
        )
    if resultado.get("exists") is not True:
        raise WhatsAppGatewayError(
            "Telefone do responsável não foi encontrado no WhatsApp. Boletim não enviado."
        )
    jid_confirmado = resultado.get("jid")
    if not _jid_eh_mesmo_numero_confirmado(jid_cadastro, jid_confirmado):
        raise WhatsAppGatewayError(
            "O WhatsApp devolveu identificador não correspondente ao cadastro. "
            "Confira o telefone do responsável antes de enviar o boletim."
        )
    return jid_confirmado


def processar_item(envio, item, config, escola):
    """Processa um único PDF; sucesso significa aceite pela API, não entrega.

    Em timeout a mensagem pode ter sido aceita pelo WhatsApp; o item vira
    ERRO e NÃO é retransmitido automaticamente, evitando duplicidade.
    """
    item.status = "PROCESSANDO"
    item.erro = ""
    item.save(update_fields=["status", "erro"])
    try:
        validar_destinatario_do_boletim(item)
        if envio.sessao != sessao_atual_id():
            raise WhatsAppGatewayError(
                "Conta WhatsApp alterada: envio da sessão anterior cancelado."
            )
        # Usar o JID realmente confirmado por onWhatsApp(), não aquele
        # montado a partir do telefone cadastrado. Em caso de divergência
        # não justificável pelo 9º dígito, não gerar nem transmitir o PDF.
        jid_confirmado = confirmar_jid_whatsapp_do_boletim(item)
        arquivo = gerar_pdf_boletim(item.boletim, config)
        try:
            conteudo = arquivo.getvalue()
        finally:
            arquivo.close()

        aluno_slug = slugify(item.boletim.aluno.nome_oficial) or "aluno"
        periodo_slug = slugify(item.boletim.periodo.nome_periodo) or "periodo"
        nome_arquivo = (
            f"boletim-{aluno_slug}-{periodo_slug}-"
            f"{item.boletim.periodo.ano}.pdf"
        )
        resposta = enviar_documento(
            jid_confirmado, conteudo, nome_arquivo,
            _legenda(envio, item, escola),
            sessao_id=envio.sessao,
        )
        confirmar_aceite_documento(resposta)

        # O PDF é individual. Se existir um anexo extra na campanha, ele é
        # transmitido ao MESMO JID, como outra mensagem individual.
        # Falha após PDF confirmado NÃO causa reenvio automático do boletim.
        _, referencia_anexo = extrair_mensagem_anexo(envio.mensagem)
        if referencia_anexo:
            try:
                dados_anexo, nome_anexo, mime_anexo, tipo_anexo = ler_anexo(referencia_anexo)
                resposta_anexo = enviar_midia(
                    jid_confirmado, dados_anexo, nome_anexo, mime_anexo,
                    tipo_anexo, "",
                )
                confirmar_operacao_wa(resposta_anexo, "anexo complementar do boletim")
            except (WhatsAppGatewayError, OSError, ValueError) as exc:
                raise WhatsAppGatewayError(
                    "PDF principal aceito pelo WA-AKG, mas o anexo complementar "
                    "não foi confirmado. Verifique o recebimento antes de repetir."
                ) from exc

        item.status = "ENVIADO"
        item.enviado_em = timezone.now()
        item.save(update_fields=["status", "enviado_em"])
    except WhatsAppGatewayError as exc:
        item.status = "ERRO"
        item.erro = str(exc)[:500]
        item.save(update_fields=["status", "erro"])
    except Exception:
        # Não armazenar exceções contendo caminhos, payloads, tokens ou
        # documentos. Logs detalhados ficam restritos à observabilidade.
        item.status = "ERRO"
        item.erro = "Falha técnica ao gerar ou enviar o PDF. Conferir logs."
        item.save(update_fields=["status", "erro"])
    return item.status


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
                    processar_item(envio, item, config, escola)
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
            finally:
                # Remove o anexo privado após o processamento definitivo do lote.
                # Nunca remove o PDF individual gerado só em memória.
                try:
                    _, referencia_anexo = extrair_mensagem_anexo(envio.mensagem)
                    apagar_anexo(referencia_anexo)
                except (OSError, ValueError):
                    self.stderr.write(f"Não foi possível limpar anexo privado do lote {envio.pk}.")

