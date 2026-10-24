import logging
import re
from collections import defaultdict
from hashlib import sha256
from datetime import timezone as datetime_timezone

from django.utils.dateparse import parse_datetime
from django.utils import timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.db.models import Q, OuterRef, Subquery
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from site_publico.boletim_importacao import normalizar_nome
from site_publico.models import BoletimAluno, PeriodoBoletim

logger = logging.getLogger(__name__)

from .access_control import usuario_tem_modulo
from .sessao_whatsapp import (
    sessao_atual_id, criar_sessao_isolada,
    limpeza_historico_pendente, marcar_limpeza_historico_pendente,
)
from .agenda_android import AgendaImportError, MAX_VCF_BYTES, processar_agenda_vcf
from .limpeza_historico_whatsapp import limpar_emeca_e_criar_sessao_nova
from .anexos_boletim_whatsapp import salvar_anexo, mensagem_com_anexo, apagar_anexo
from .models import (
    EnvioBoletimWhatsApp,
    ContatoAgendaWhatsApp,
    ConversaExcluidaWhatsApp,
    EstadoConversaWhatsApp,
    EtiquetaConversaWhatsApp,
    GrupoOcultoWhatsApp,
    ItemEnvioBoletimWhatsApp,
    IdentidadeContatoWhatsApp,
    LeituraChatWhatsApp,
    MensagemOcultaWhatsApp,
    TelefoneDeclaracao,
    declaracao,
)
from .whatsapp_gateway import (
    WhatsAppGatewayError,
    apagar_agendamento,
    apagar_etiqueta,
    apagar_mensagem,
    apagar_resposta_automatica,
    baixar_midia_mensagem,
    baixar_midia_por_caminho,
    atualizar_etiquetas_chat,
    bloquear_contato,
    buscar_mensagens,
    configurado as gateway_configurado,
    confirmar_operacao_wa,
    criar_agendamento,
    criar_etiqueta,
    criar_grupo,
    criar_resposta_automatica,
    editar_mensagem,
    encaminhar_mensagem,
    enviar_broadcast,
    enviar_broadcast_midia,
    enviar_mensagem_chat,
    enviar_midia,
    enviar_presenca,
    favoritar_mensagem,
    gerenciar_chat,
    iniciar_sessao,
    pausar_sessao,
    desvincular_sessao,
    excluir_historico_sessao,
    listar_agendamentos,
    listar_chats,
    listar_chats_pagina,
    listar_contatos,
    listar_etiquetas,
    listar_grupos,
    listar_respostas_automaticas,
    listar_etiquetas_chat,
    marcar_chat_como_lido,
    obter_config_sistema,
    obter_foto_perfil,
    obter_perfil_contato,
    obter_mensagens_chat,
    obter_qr,
    obter_sessao,
    reagir_mensagem,
    responder_mensagem_citada,
    salvar_config_sistema,
    sair_grupo,
    verificar_numeros,
)


CORES_ETIQUETAS_WA = [
    {"id": i, "hex": cor, "nome": nome}
    for i, (cor, nome) in enumerate([
        ("#FF0000", "Vermelho"), ("#FF7F00", "Laranja"),
        ("#FFFF00", "Amarelo"), ("#00FF00", "Verde"),
        ("#0000FF", "Azul"), ("#4B0082", "Índigo"),
        ("#9400D3", "Roxo"), ("#FF1493", "Rosa"),
        ("#00CED1", "Turquesa"), ("#32CD32", "Verde-lima"),
        ("#FFD700", "Dourado"), ("#FF69B4", "Rosa-claro"),
        ("#8B4513", "Marrom"), ("#2F4F4F", "Verde-escuro"),
        ("#696969", "Cinza"), ("#708090", "Cinza-azulado"),
        ("#778899", "Ardósia"), ("#B0C4DE", "Azul-gelo"),
        ("#ADD8E6", "Azul-claro"), ("#F0E68C", "Areia"),
    ])
]


TIPOS_CONTATO = {"PAI", "MAE", "RESPONSAVEL"}
ROTULOS_CONTATO = {
    "PAI": "Pai",
    "MAE": "Mãe",
    "RESPONSAVEL": "Responsável",
}
TIPOS_PERIODO = {"BIMESTRE", "TRIMESTRE"}


def _normalizar_jid(telefone):
    digitos = re.sub(r"\D", "", telefone or "")
    if digitos.startswith("00"):
        digitos = digitos[2:]

    # Só trata 55 como código do Brasil quando o comprimento confirma isso.
    # Assim, números do DDD 55 não são cortados por engano.
    if digitos.startswith("55") and len(digitos) in (12, 13):
        nacional = digitos[2:]
    else:
        nacional = digitos

    if len(nacional) not in (10, 11):
        return None

    ddd = nacional[:2]
    if not ddd.isdigit() or ddd[0] == "0":
        return None

    return f"55{nacional}@s.whatsapp.net"


def _tipos_selecionados(request):
    tipos = (
        request.GET.getlist("tipos")
        if request.method == "GET"
        else request.POST.getlist("tipos")
    )
    return [tipo for tipo in tipos if tipo in TIPOS_CONTATO]


def _queryset_contatos(modo, turma="", contato_id=None, tipos=None, periodo_boletim_id=None):
    queryset = TelefoneDeclaracao.objects.select_related("declaracao")

    if modo == "individual":
        if not contato_id:
            raise ValueError("Selecione um responsável.")
        queryset = queryset.filter(pk=contato_id)
    else:
        if tipos is None:
            tipos = ["PAI", "MAE", "RESPONSAVEL"]
        queryset = queryset.filter(tipo__in=tipos)

    if modo == "turma":
        turma = (turma or "").strip()
        if not turma:
            raise ValueError("Selecione uma turma.")
        queryset = queryset.filter(declaracao__turmaDoAluno__iexact=turma)
    elif modo == "turma_boletim":
        # O período é um registro específico em Boletins (turma, ano e etapa).
        # Nunca relacionar por nome: usar exclusivamente o vínculo com
        # Declarações confirmado no cadastro do aluno.
        try:
            periodo_id = int(periodo_boletim_id)
        except (TypeError, ValueError):
            raise ValueError("Selecione uma turma cadastrada em Boletins.") from None
        if periodo_id < 1 or not PeriodoBoletim.objects.filter(pk=periodo_id).exists():
            raise ValueError("A turma de Boletins selecionada não existe.")
        declaracoes_da_turma = (
            BoletimAluno.objects.filter(
                periodo_id=periodo_id, aluno__declaracao__isnull=False,
            ).values("aluno__declaracao_id")
        )
        queryset = queryset.filter(declaracao_id__in=declaracoes_da_turma)
    elif modo == "individual":
        pass
    elif modo != "todos":
        raise ValueError("Tipo de envio inválido.")

    return queryset.order_by("declaracao__nomeDoAluno", "tipo", "id")


def _resolver_destinatarios(modo, turma="", contato_id=None, tipos=None, periodo_boletim_id=None):
    queryset = _queryset_contatos(
        modo,
        turma=turma,
        contato_id=contato_id,
        tipos=tipos,
        periodo_boletim_id=periodo_boletim_id,
    )

    destinatarios = []
    invalidos = 0
    vistos = set()
    amostra = []

    for contato in queryset:
        jid = _normalizar_jid(contato.telefone)
        if not jid:
            invalidos += 1
            continue
        if jid in vistos:
            continue
        vistos.add(jid)
        destinatarios.append(jid)
        if len(amostra) < 8:
            numero = re.sub(r"\D", "", contato.telefone or "")
            mascarado = f"••••{numero[-4:]}" if len(numero) >= 4 else "não informado"
            amostra.append(
                {
                    "aluno": contato.declaracao.nomeDoAluno,
                    "tipo": ROTULOS_CONTATO.get(contato.tipo, contato.tipo),
                    "telefone": mascarado,
                }
            )

    return destinatarios, invalidos, amostra


def _validar_periodo(tipo, numero, ano):
    tipo = (tipo or "").strip().upper()
    if tipo not in TIPOS_PERIODO:
        raise ValueError("Escolha Bimestre ou Trimestre.")

    try:
        numero = int(numero)
        ano = int(ano)
    except (TypeError, ValueError):
        raise ValueError("Selecione o período e o ano letivo.") from None

    limite = 4 if tipo == "BIMESTRE" else 3
    if numero < 1 or numero > limite:
        raise ValueError(
            f"Para {tipo.lower()}, selecione um período entre 1 e {limite}."
        )

    return tipo, numero, ano


def _resolver_boletins_destinatarios(
    modo,
    tipo,
    numero,
    ano,
    turma="",
    contato_id=None,
    tipos=None,
    periodo_boletim_id=None,
):
    tipo, numero, ano = _validar_periodo(tipo, numero, ano)
    periodo_selecionado = None
    if modo == "turma_boletim":
        # Diferentemente da turma informada em Declarações, o identificador
        # aponta para UM período específico e publicado, sem depender de
        # nomes de turmas que podem se repetir entre anos ou etapas.
        try:
            periodo_id = int(periodo_boletim_id)
        except (TypeError, ValueError):
            raise ValueError("Selecione uma turma cadastrada em Boletins.") from None
        periodo_selecionado = PeriodoBoletim.objects.filter(
            pk=periodo_id, publicado=True,
            tipo=tipo, numero=numero, ano=ano,
        ).first()
        if periodo_selecionado is None:
            raise ValueError(
                "A turma selecionada não corresponde ao ano e período "
                "publicados. Selecione novamente a turma do Boletim."
            )

    contatos = _queryset_contatos(
        modo,
        turma=turma,
        contato_id=contato_id,
        tipos=tipos,
        periodo_boletim_id=periodo_selecionado.pk if periodo_selecionado else None,
    )

    boletins = (
        BoletimAluno.objects
        .filter(
            periodo__tipo=tipo,
            periodo__numero=numero,
            periodo__ano=ano,
            periodo__publicado=True,
        )
        .select_related("aluno", "periodo")
        .prefetch_related("resultados__disciplina")
    )
    if periodo_selecionado is not None:
        boletins = boletins.filter(periodo_id=periodo_selecionado.pk)

    # O boletim só pode ser associado ao aluno da mesma Declaração.
    # Nunca enviar boletim por mera igualdade de nome (homônimos).
    por_declaracao = defaultdict(list)
    for boletim in boletins:
        if boletim.aluno.declaracao_id:
            por_declaracao[boletim.aluno.declaracao_id].append(boletim)

    itens = []
    vistos = set()
    invalidos = 0
    sem_boletim = set()
    ambiguos = set()

    for contato in contatos:
        jid = _normalizar_jid(contato.telefone)
        if not jid:
            invalidos += 1
            continue

        declaracao_aluno = contato.declaracao
        candidatos = por_declaracao.get(declaracao_aluno.pk, [])
        if turma:
            candidatos = [
                item for item in candidatos
                if normalizar_nome(item.periodo.turma) == normalizar_nome(turma)
            ]

        if not candidatos:
            sem_boletim.add(declaracao_aluno.pk)
            continue
        if len(candidatos) != 1:
            ambiguos.add(declaracao_aluno.pk)
            continue

        boletim = candidatos[0]
        chave = (jid, boletim.pk)
        if chave in vistos:
            continue
        vistos.add(chave)
        itens.append(
            {
                "jid": jid,
                "boletim": boletim,
                "tipo_contato": contato.tipo,
            }
        )

    return {
        "itens": itens,
        "invalidos": invalidos,
        "sem_boletim": len(sem_boletim),
        "ambiguos": len(ambiguos),
        "alunos": len({item["boletim"].pk for item in itens}),
        "tipo": tipo,
        "numero": numero,
        "ano": ano,
        "turma_selecionada": periodo_selecionado.turma if periodo_selecionado else turma,
    }


def _pode_desconectar_whatsapp(usuario):
    """Apenas a Administração EMECA pode controlar a sessão institucional."""
    return usuario_tem_modulo(usuario, "administracao", strict=True)


@login_required
def whatsapp(request):
    # Esta página é independente da disponibilidade do gateway remoto.
    # Com limpeza pendente não consultar WA-AKG (que pode estar em purga,
    # lento ou com banco bloqueado) apenas para desenhar a interface.
    turmas = []
    turmas_boletim = []
    anos_boletim = []
    envios = []
    db_indisponivel = False
    try:
        turmas = list(
            declaracao.objects.exclude(turmaDoAluno__isnull=True)
            .exclude(turmaDoAluno__exact="")
            .order_by("turmaDoAluno")
            .values_list("turmaDoAluno", flat=True).distinct()
        )
        anos_boletim = list(
            PeriodoBoletim.objects.filter(
                publicado=True, boletins__isnull=False,
            ).order_by("-ano").values_list("ano", flat=True).distinct()
        )
        turmas_boletim = list(
            PeriodoBoletim.objects.filter(
                boletins__isnull=False,
            ).distinct().order_by("-ano", "-numero", "turma", "pk")
        )
        sessao_id = sessao_atual_id()
        limpeza_pendente = limpeza_historico_pendente()
        # Materializar dentro do bloco try; erros de SQLite em QuerySet lazy
        # anteriormente escapavam durante render() e retornavam erro 500.
        envios = list(
            EnvioBoletimWhatsApp.objects.filter(sessao=sessao_id).annotate(
                primeiro_erro=Subquery(
                    ItemEnvioBoletimWhatsApp.objects.filter(
                        envio_id=OuterRef("pk"), status="ERRO",
                    ).exclude(erro="").order_by("id").values("erro")[:1]
                ),
            ).select_related("usuario")[:8]
        )
    except DatabaseError as exc:
        logger.error("Falha temporária em dados do painel WhatsApp: %s", type(exc).__name__)
        db_indisponivel = True
        # Estado conservador: não oferecer reconexão/desconexão enquanto
        # não for possível confirmar a sessão e o estado de limpeza.
        sessao_id = ""
        limpeza_pendente = True

    status = "NAO_CONFIGURADO"
    status_detalhe = ""
    if db_indisponivel:
        status = "INDISPONIVEL"
        status_detalhe = "Banco temporariamente indisponível. Nenhuma operação foi executada."
    elif limpeza_pendente:
        status = "LIMPEZA_PENDENTE"
        status_detalhe = (
            "A limpeza da sessão anterior ficou incompleta. "
            "Não tente reconectar, repetir a exclusão ou trocar de conta "
            "até confirmar o estado do histórico no WA-AKG."
        )
    elif gateway_configurado():
        try:
            resposta = obter_sessao()
            if not isinstance(resposta, dict):
                raise WhatsAppGatewayError("Resposta de sessão inválida.")
            dados = resposta.get("data")
            if not isinstance(dados, dict):
                raise WhatsAppGatewayError("Dados de sessão inválidos no gateway.")
            status = str(dados.get("status") or "DESCONHECIDO").upper()
        except WhatsAppGatewayError as exc:
            status = "NAO_CRIADA" if exc.status_code == 404 else "INDISPONIVEL"
            status_detalhe = (
                "O WA-AKG não respondeu. A conta e as mensagens não foram modificadas."
                if status == "INDISPONIVEL" else ""
            )
        except Exception as exc:
            # A disponibilidade da tela não pode depender de parse de JSON,
            # timeout de socket ou erro inesperado do gateway remoto.
            logger.error("Consulta de estado WhatsApp indisponível: %s", type(exc).__name__)
            status = "INDISPONIVEL"
            status_detalhe = (
                "Falha temporária na consulta do WhatsApp. "
                "Nenhuma operação de conexão ou exclusão foi executada."
            )

    return render(request, "whatsapp.html", {
        "turmas": turmas,
        "turmas_boletim": turmas_boletim,
        "anos_boletim": anos_boletim,
        "envios_boletim": envios,
        "gateway_configurado": gateway_configurado(),
        "gateway_status": status,
        "gateway_status_detalhe": status_detalhe,
        "pode_desconectar": _pode_desconectar_whatsapp(request.user),
        "limpeza_pendente": limpeza_pendente,
        "wa_sessao_id": sessao_id,
        "delay_segundos": round(settings.WA_AKG_BROADCAST_DELAY_MS / 1000, 1),
    })


@login_required
@require_GET
def whatsapp_buscar_contatos(request):
    termo = (request.GET.get("q") or "").strip()
    if len(termo) < 2:
        return JsonResponse({"results": []})

    contatos = (
        TelefoneDeclaracao.objects.select_related("declaracao")
        .filter(
            Q(declaracao__nomeDoAluno__icontains=termo)
            | Q(declaracao__nomePai__icontains=termo)
            | Q(declaracao__nomeMae__icontains=termo)
            | Q(declaracao__nomeResponsavel__icontains=termo)
        )
        .order_by("declaracao__nomeDoAluno", "tipo", "id")[:30]
    )

    results = [
        {
            "id": contato.id,
            "aluno": contato.declaracao.nomeDoAluno,
            "turma": contato.declaracao.turmaDoAluno or "",
            "tipo": ROTULOS_CONTATO.get(contato.tipo, contato.tipo),
            "telefone": contato.telefone,
        }
        for contato in contatos
    ]
    return JsonResponse({"results": results})


@login_required
@require_GET
def whatsapp_buscar_contatos_wa(request):
    """Busca números da agenda Android e contatos reais do WA-AKG, sem duplicar."""
    termo = (request.GET.get("q") or "").strip()[:100]
    if len(termo) < 2:
        return JsonResponse({"results": []})

    termo_norm = termo.casefold()
    termo_digitos = re.sub(r"\D", "", termo)
    results = []
    vistos = set()

    # A agenda importada tem prioridade para nomes e números da Secretaria.
    filtro = Q(nome__icontains=termo)
    if termo_digitos:
        filtro |= Q(telefone_jid__contains=termo_digitos)
    importados = (
        ContatoAgendaWhatsApp.objects
        .filter(sessao=sessao_atual_id())
        .filter(filtro)
        .order_by("nome", "telefone_jid")[:50]
    )
    for contato in importados:
        jid = contato.telefone_jid
        if jid in vistos:
            continue
        vistos.add(jid)
        results.append({
            "jid": jid, "nome": contato.nome,
            "telefone": jid.split("@")[0],
            "profilePic": "", "origem": "agenda_android",
        })
        if len(results) >= 30:
            return JsonResponse({"results": results})

    try:
        payload = listar_contatos()
        contatos = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(contatos, list):
            contatos = []
    except WhatsAppGatewayError as exc:
        # Contatos importados continuam pesquisáveis mesmo com gateway offline.
        if results:
            return JsonResponse({"results": results, "aviso": "WA-AKG temporariamente indisponível."})
        return JsonResponse({"results": [], "erro": str(exc)}, status=exc.status_code or 502)

    for contato in contatos:
        if not isinstance(contato, dict):
            continue
        jid = str(contato.get("jid") or "")
        lid = str(contato.get("lid") or "")
        alt = str(contato.get("remoteJidAlt") or "")
        telefone_jid = str(contato.get("phoneJid") or "")
        nome = (
            contato.get("name")
            or contato.get("verifiedName")
            or contato.get("notify")
            or ""
        )
        phone_jid = next(
            (item.replace("@c.us", "@s.whatsapp.net")
             for item in (telefone_jid, alt, jid) if _jid_eh_telefone(item)),
            "",
        )
        telefone = re.sub(r"\D", "", phone_jid.split("@")[0]) if phone_jid else ""
        haystack = " ".join([str(nome), telefone, jid, lid, alt]).casefold()
        if termo_norm not in haystack and (
            not termo_digitos or termo_digitos not in re.sub(r"\D", "", haystack)
        ):
            continue
        chave = phone_jid or jid or lid
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        results.append({
            "jid": phone_jid or jid or lid,
            "nome": nome or (telefone if telefone else "Contato sem identificação"),
            "telefone": telefone,
            "profilePic": contato.get("profilePic") or "",
        })
        if len(results) >= 30:
            break
    return JsonResponse({"results": results})


@login_required
@require_GET
def whatsapp_destinatarios(request):
    try:
        destinatarios, invalidos, amostra = _resolver_destinatarios(
            request.GET.get("modo") or "todos",
            turma=request.GET.get("turma") or "",
            contato_id=request.GET.get("contato_id") or None,
            tipos=_tipos_selecionados(request),
            periodo_boletim_id=request.GET.get("periodo_boletim_id") or None,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "quantidade": len(destinatarios),
            "invalidos": invalidos,
            "amostra": amostra,
        }
    )


@login_required
@require_GET
def whatsapp_boletins_preview(request):
    try:
        dados = _resolver_boletins_destinatarios(
            request.GET.get("modo") or "todos",
            request.GET.get("boletim_tipo") or "",
            request.GET.get("boletim_numero") or "",
            request.GET.get("boletim_ano") or "",
            turma=request.GET.get("turma") or "",
            contato_id=request.GET.get("contato_id") or None,
            tipos=_tipos_selecionados(request),
            periodo_boletim_id=request.GET.get("periodo_boletim_id") or None,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "quantidade": len(dados["itens"]),
            "alunos": dados["alunos"],
            "invalidos": dados["invalidos"],
            "sem_boletim": dados["sem_boletim"],
            "ambiguos": dados["ambiguos"],
        }
    )


@login_required
@require_POST
def whatsapp_conectar(request):
    if limpeza_historico_pendente():
        messages.error(
            request,
            "A sessão anterior está pendente de limpeza. Finalize a limpeza "
            "em Gerenciamento para liberar uma nova conexão."
        )
        return redirect("whatsapp_gerenciamento")
    if _validar_sessao_cliente(request) is not None:
        messages.error(request, "A conta WhatsApp foi alterada. Reabra a página.")
        return redirect("whatsapp")
    if not gateway_configurado():
        messages.error(
            request,
            "Configure o WA-AKG no arquivo .env antes de conectar.",
        )
        return redirect("whatsapp")

    try:
        # Não permitir reutilização do mesmo Session do WA-AKG após logout:
        # esse registro precisa ser eliminado antes de outro QR Code.
        try:
            sessao = obter_sessao()
        except WhatsAppGatewayError as exc:
            if exc.status_code != 404:
                raise
            sessao = {}
        if isinstance(sessao, dict):
            dados = sessao.get("data") or {}
            estado = str((dados if isinstance(dados, dict) else {}).get("status") or "").upper()
            if estado == "LOGGED_OUT":
                messages.error(
                    request,
                    "Esta sessão foi desvinculada. Finalize a exclusão do histórico "
                    "em Gerenciamento antes de conectar outro número."
                )
                return redirect("whatsapp")
        iniciar_sessao()
        messages.success(
            request,
            "Sessão do WhatsApp iniciada. Use o botão “Exibir QR” para vincular o aparelho.",
        )
    except WhatsAppGatewayError as exc:
        messages.error(request, f"Não foi possível iniciar o WhatsApp: {exc}")
    return redirect("whatsapp")


@login_required
@require_POST
def whatsapp_desconectar(request):
    """Pausar preserva dados. Desvincular apaga definitivamente ESTA sessão."""
    if _validar_sessao_cliente(request) is not None:
        messages.error(request, "A conta WhatsApp foi alterada. Reabra a página.")
        return redirect("whatsapp")
    if not _pode_desconectar_whatsapp(request.user):
        return HttpResponseForbidden(
            "Somente administradores podem desconectar o WhatsApp."
        )

    destino = "whatsapp_gerenciamento" if request.POST.get("origem") == "gerenciamento" else (
        "whatsapp_mensagens" if request.POST.get("origem") == "mensagens" else "whatsapp"
    )
    acao = (request.POST.get("acao") or "").strip()
    if acao not in ("pausar", "desvincular", "isolar", "finalizar_limpeza"):
        messages.error(request, "Ação de desconexão inválida.")
        return redirect(destino)

    if acao != "pausar":
        esperada = {"desvincular": "DESVINCULAR", "isolar": "ISOLAR",
                    "finalizar_limpeza": "APAGAR"}[acao]
        if (
            request.POST.get("confirmacao") != esperada
            or request.POST.get("confirmar_exclusao") != "APAGAR_HISTORICO"
        ):
            messages.error(
                request, "Confirme a exclusão PERMANENTE das mensagens da sessão."
            )
            return redirect(destino)

    if not gateway_configurado():
        messages.error(request, "Integração do WhatsApp não configurada.")
        return redirect(destino)

    try:
        sessao_id = sessao_atual_id()
        pendente = limpeza_historico_pendente()
        sessao_remota_ja_excluida = False
        try:
            sessao = obter_sessao()
        except WhatsAppGatewayError as exc:
            # Se o WA-AKG concluiu a purga mas o EMECA falhou ao rotacionar
            # o ponteiro, permitir finalizar só quando temos pendência
            # previamente registrada E a sessão não existe mais no WA-AKG.
            if (exc.status_code == 404 and pendente
                    and acao == "finalizar_limpeza"):
                sessao = {}
                sessao_remota_ja_excluida = True
            else:
                raise
        sessao = sessao if isinstance(sessao, dict) else {}
        dados = sessao.get("data") or {}
        dados = dados if isinstance(dados, dict) else {}
        status = str(dados.get("status") or sessao.get("status") or "").upper()

        if acao == "pausar":
            if status in {"STOPPED", "LOGGED_OUT", "NAO_CRIADA"}:
                messages.info(request, "O WhatsApp já está desconectado.")
                return redirect(destino)
            resposta = pausar_sessao()
            if not isinstance(resposta, dict) or resposta.get("status") is not True:
                raise WhatsAppGatewayError("O WA-AKG não confirmou a pausa.")
            messages.success(
                request, "Conexão pausada. Nenhum histórico foi excluído."
            )
            return redirect(destino)

        # Somente LOGGED_OUT pode ser limpo. Uma falha de rede (DISCONNECTED)
        # nunca deve apagar registros do atendimento institucional.
        if status == "CONNECTED" and acao != "finalizar_limpeza":
            marcar_limpeza_historico_pendente(sessao_id)
            resposta = desvincular_sessao()
            if not isinstance(resposta, dict) or resposta.get("status") is not True:
                raise WhatsAppGatewayError("O WA-AKG não confirmou o logout.")
        elif status == "LOGGED_OUT":
            marcar_limpeza_historico_pendente(sessao_id)
        elif not sessao_remota_ja_excluida:
            raise WhatsAppGatewayError(
                "É preciso desvincular realmente o WhatsApp. "
                "Não é permitido apagar histórico de uma sessão pausada ou ativa."
            )

        # O socket pode levar alguns segundos para fechar após logout().
        # Se o endpoint recusar (409), não liberar a próxima conexão.
        import time
        resposta_limpeza = None
        if sessao_remota_ja_excluida:
            resposta_limpeza = {
                "status": True,
                "data": {"alreadyDeleted": True, "mediaWarning": False},
            }
        else:
            for tentativa in range(8):
                try:
                    resposta_limpeza = excluir_historico_sessao(sessao_id)
                    break
                except WhatsAppGatewayError as exc:
                    if exc.status_code != 409 or tentativa == 7:
                        raise
                    time.sleep(1)
        if not isinstance(resposta_limpeza, dict) or resposta_limpeza.get("status") is not True:
            raise WhatsAppGatewayError("O WA-AKG não confirmou a remoção do histórico.")

        resultado = limpar_emeca_e_criar_sessao_nova(sessao_id)
        if (resposta_limpeza.get("data") or {}).get("mediaWarning"):
            messages.warning(
                request,
                "Mensagens removidas do banco, porém alguns arquivos de mídia "
                "não puderam ser excluídos do armazenamento. Verifique o servidor."
            )
        messages.success(
            request,
            "Conta desvinculada e histórico desta sessão apagado do WA-AKG "
            "e do EMECA. A nova conexão começará com uma sessão vazia. "
            "Os registros apagados não poderão ser recuperados por este sistema."
        )
    except (WhatsAppGatewayError, ValueError) as exc:
        logger.warning(
            "Desconexão WhatsApp incompleta na sessão %s: %s",
            locals().get("sessao_id", "indisponível"), exc,
        )
        messages.error(
            request,
            "A exclusão do histórico não foi concluída. NÃO conecte outro número. "
            f"Verifique a sessão anterior e tente finalizar a limpeza: {exc}"
        )
    except DatabaseError:
        logger.exception(
            "Falha de banco durante a desconexão do WhatsApp. "
            "Verifique a migração usuarioSec.0018 e o estado da sessão."
        )
        messages.error(
            request,
            "Erro no banco de dados ao desconectar o WhatsApp. Não conecte outro "
            "número. Verifique as migrações com 'python manage.py showmigrations "
            "usuarioSec' e execute 'python manage.py migrate' se necessário. "
            "O logout pode já ter ocorrido; consulte os logs antes de repetir a ação."
        )
    except Exception:
        logger.exception(
            "Erro inesperado ao desconectar WhatsApp. Verifique se o logout "
            "ou a exclusão remota já ocorreram antes de repetir a ação."
        )
        messages.error(
            request,
            "Não foi possível concluir a desconexão. Não conecte outro número "
            "nem repita a exclusão antes de verificar os logs do servidor: "
            "a operação pode ter sido parcialmente executada."
        )
    return redirect(destino)


@login_required
@require_GET
def whatsapp_qr(request):
    # Nunca recrie sessão ou gere QR enquanto a limpeza anterior está pendente.
    if limpeza_historico_pendente():
        return JsonResponse({
            "ok": False,
            "erro": "A limpeza da conta anterior está pendente. Conclua-a em Gerenciamento antes de conectar outro número.",
        }, status=409)
    try:
        sessao = obter_sessao()
        dados_sessao = (sessao.get("data") or {}) if isinstance(sessao, dict) else {}
        estado = str(dados_sessao.get("status") or "").upper()
        if estado == "CONNECTED":
            return JsonResponse({"ok": True, "connected": True})
        if estado in {"LOGGED_OUT"}:
            return JsonResponse({
                "ok": False,
                "erro": "A sessão foi desvinculada. Finalize a limpeza do histórico em Gerenciamento.",
            }, status=409)
        if estado not in {"SCAN_QR", "STARTING", "CONNECTING", "DISCONNECTED"}:
            return JsonResponse({
                "ok": False,
                "erro": "A sessão ainda não está pronta. Clique em Conectar WhatsApp e tente novamente.",
            }, status=409)
        resultado = obter_qr()
        return JsonResponse({"ok": True, "base64": resultado.get("base64")})
    except WhatsAppGatewayError as exc:
        if exc.payload.get("connected"):
            return JsonResponse({"ok": True, "connected": True})
        if exc.status_code == 404:
            return JsonResponse({
                "ok": False,
                "erro": "Sessão não encontrada no WA-AKG. Recarregue a página e utilize Conectar WhatsApp. Nenhum histórico foi apagado.",
            }, status=409)
        return JsonResponse({
            "ok": False,
            "erro": "Serviço WhatsApp temporariamente indisponível. Tente novamente em instantes."
            if exc.status_code is None or exc.status_code >= 500 else str(exc),
        }, status=503 if exc.status_code is None or exc.status_code >= 500 else exc.status_code)


def _enfileirar_boletins(request):
    if request.POST.get("modo") == "turma_boletim":
        messages.error(
            request,
            "Turmas do Boletim é uma opção para comunicados. "
            "Para enviar os PDFs personalizados, selecione Por turma e o período.",
        )
        return redirect("whatsapp")
    if not gateway_configurado():
        messages.error(request, "A integração com o WhatsApp ainda não está configurada.")
        return redirect("whatsapp")

    try:
        sessao = obter_sessao()
        status = str(sessao.get("data", {}).get("status") or "").upper()
    except WhatsAppGatewayError as exc:
        messages.error(request, f"Não foi possível verificar o WhatsApp: {exc}")
        return redirect("whatsapp")

    if status != "CONNECTED":
        messages.error(request, "Conecte o WhatsApp antes de colocar boletins na fila.")
        return redirect("whatsapp")

    mensagem_pdf = (request.POST.get("mensagem_boletim") or "").strip()
    anexo_boletim = request.FILES.get("anexo_boletim")
    try:
        formato_boletim = _validar_anexo_campanha(anexo_boletim)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("whatsapp")
    if len(mensagem_pdf) > 1200:
        messages.error(
            request,
            "A mensagem que acompanha o boletim deve ter no máximo 1.200 caracteres.",
        )
        return redirect("whatsapp")

    try:
        dados = _resolver_boletins_destinatarios(
            request.POST.get("modo") or "todos",
            request.POST.get("boletim_tipo") or "",
            request.POST.get("boletim_numero") or "",
            request.POST.get("boletim_ano") or "",
            turma=request.POST.get("turma") or "",
            contato_id=request.POST.get("contato_id") or None,
            tipos=_tipos_selecionados(request),
            periodo_boletim_id=request.POST.get("periodo_boletim_id") or None,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("whatsapp")

    if not dados["itens"]:
        messages.error(
            request,
            "Nenhum boletim publicado foi encontrado para os destinatários selecionados nesse período.",
        )
        return redirect("whatsapp")

    referencia_anexo = ""
    if anexo_boletim:
        try:
            referencia_anexo = salvar_anexo(anexo_boletim, formato_boletim["nome"])
        except (OSError, ValueError):
            messages.error(request, "Não foi possível armazenar o anexo de forma privada.")
            return redirect("whatsapp")

    try:
        with transaction.atomic():
            envio = EnvioBoletimWhatsApp.objects.create(
                usuario=request.user,
                sessao=sessao_atual_id(),
                tipo_periodo=dados["tipo"],
                numero_periodo=dados["numero"],
                ano=dados["ano"],
                modo=request.POST.get("modo") or "todos",
                turma=dados["turma_selecionada"],
                mensagem=(mensagem_com_anexo(mensagem_pdf, referencia_anexo)
                          if referencia_anexo else mensagem_pdf),
                total=len(dados["itens"]),
                ignorados=(
                    dados["invalidos"]
                    + dados["sem_boletim"]
                    + dados["ambiguos"]
                ),
            )
            ItemEnvioBoletimWhatsApp.objects.bulk_create(
                [
                    ItemEnvioBoletimWhatsApp(
                        envio=envio,
                        boletim=item["boletim"],
                        jid=item["jid"],
                        tipo_contato=item["tipo_contato"],
                    )
                    for item in dados["itens"]
                ]
            )

    except Exception:
        apagar_anexo(referencia_anexo)
        raise

    avisos = []
    if dados["sem_boletim"]:
        avisos.append(f'{dados["sem_boletim"]} aluno(s) sem boletim publicado')
    if dados["invalidos"]:
        avisos.append(f'{dados["invalidos"]} telefone(s) inválido(s)')
    if dados["ambiguos"]:
        avisos.append(f'{dados["ambiguos"]} aluno(s) com cadastro ambíguo')
    complemento = f" Ignorados: {', '.join(avisos)}." if avisos else ""

    messages.success(
        request,
        (
            f'{len(dados["itens"])} PDF(s) de boletim foram colocados na fila '
            f'para {dados["alunos"]} aluno(s).{complemento}'
        ),
    )
    return redirect("whatsapp")


def _confirmar_destinatarios_turma_boletim(destinatarios):
    """Valida TODOS os JIDs da turma antes de iniciar qualquer transmissão.

    Corrige o nono dígito brasileiro usando a resposta oficial do WhatsApp,
    sem aceitar JIDs LID não associados nem outros números. A consulta pode
    ignorar números inexistentes, mas qualquer resposta ambígua bloqueia o
    disparo inteiro. Nenhum documento escolar é usado nesta opção.
    """
    from .management.commands.processar_envios_whatsapp import (
        _jid_eh_mesmo_numero_confirmado,
    )

    confirmados = []
    vistos = set()
    inexistentes = 0
    for indice in range(0, len(destinatarios), 50):
        bloco = destinatarios[indice:indice + 50]
        numeros = [jid.split("@", 1)[0] for jid in bloco]
        resposta = confirmar_operacao_wa(
            verificar_numeros(numeros), "verificação de contatos da turma de Boletins",
        )
        dados = resposta.get("data")
        resultados = dados.get("results") if isinstance(dados, dict) else None
        if not isinstance(resultados, list) or len(resultados) != len(numeros):
            raise WhatsAppGatewayError(
                "O WhatsApp não confirmou todos os números da turma. Nenhum envio iniciado."
            )
        por_numero = {}
        for entrada in resultados:
            if not isinstance(entrada, dict):
                raise WhatsAppGatewayError("Resposta inválida ao validar a turma. Nenhum envio iniciado.")
            numero = str(entrada.get("number") or "")
            if numero not in numeros or numero in por_numero:
                raise WhatsAppGatewayError("Resposta ambígua ao validar a turma. Nenhum envio iniciado.")
            por_numero[numero] = entrada
        for jid, numero in zip(bloco, numeros):
            entrada = por_numero.get(numero)
            if entrada is None or type(entrada.get("exists")) is not bool:
                raise WhatsAppGatewayError(
                    "Não foi possível verificar um responsável. Nenhum envio iniciado."
                )
            if entrada["exists"] is False:
                inexistentes += 1
                continue
            jid_confirmado = entrada.get("jid")
            if not _jid_eh_mesmo_numero_confirmado(jid, jid_confirmado):
                raise WhatsAppGatewayError(
                    "O WhatsApp devolveu um destinatário diferente do cadastrado. "
                    "Revise a turma antes de enviar; nenhuma mensagem foi transmitida."
                )
            if jid_confirmado not in vistos:
                confirmados.append(jid_confirmado)
                vistos.add(jid_confirmado)
    return confirmados, inexistentes


@login_required
@require_POST
def whatsapp_enviar(request):
    if _validar_sessao_cliente(request) is not None:
        messages.error(request, "A conta WhatsApp foi alterada. Nenhuma mensagem foi enviada.")
        return redirect("whatsapp")
    if (request.POST.get("conteudo") or "mensagem") == "boletim":
        return _enfileirar_boletins(request)

    modo_envio = request.POST.get("modo") or "todos"
    if modo_envio == "turma_boletim" and limpeza_historico_pendente():
        messages.error(
            request, "A limpeza da conexão WhatsApp está pendente. "
            "Nenhuma mensagem será enviada até a sessão ser verificada.",
        )
        return redirect("whatsapp")

    mensagem = (request.POST.get("mensagem") or "").strip()
    anexo = request.FILES.get("anexo")
    try:
        formato_anexo = _validar_anexo_campanha(anexo)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("whatsapp")
    if not mensagem and not anexo:
        messages.error(request, "Digite uma mensagem ou anexe uma imagem/PDF.")
        return redirect("whatsapp")
    if len(mensagem) > 4000:
        messages.error(
            request,
            "A mensagem deve ter no máximo 4.000 caracteres.",
        )
        return redirect("whatsapp")

    try:
        destinatarios, invalidos, _ = _resolver_destinatarios(
            request.POST.get("modo") or "todos",
            turma=request.POST.get("turma") or "",
            contato_id=request.POST.get("contato_id") or None,
            tipos=_tipos_selecionados(request),
            periodo_boletim_id=request.POST.get("periodo_boletim_id") or None,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("whatsapp")

    if not destinatarios:
        messages.error(
            request,
            "Nenhum número de WhatsApp válido foi encontrado para esse envio.",
        )
        return redirect("whatsapp")

    try:
        nao_localizados = 0
        if modo_envio == "turma_boletim":
            destinatarios, nao_localizados = _confirmar_destinatarios_turma_boletim(
                destinatarios
            )
            if not destinatarios:
                messages.error(
                    request,
                    "Nenhum número dessa turma foi confirmado pelo WhatsApp. Nada foi enviado.",
                )
                return redirect("whatsapp")

        if len(destinatarios) == 1:
            jid = destinatarios[0]
            if modo_envio == "turma_boletim":
                # Validado integralmente antes, não consultar outra vez no
                # formato legado: isso poderia retornar um JID diferente.
                jid_real = jid
            else:
                numero = jid.split("@")[0]
                check = verificar_numeros([numero])
                resultados = (
                    check.get("data", {}).get("results", [])
                    if isinstance(check, dict)
                    else []
                )
                valido = next((item for item in resultados if item.get("exists")), None)
                if not valido:
                    messages.error(
                        request,
                        "O número selecionado não foi localizado no WhatsApp.",
                    )
                    return redirect("whatsapp")
                jid_real = valido.get("jid") or jid
            if anexo:
                resposta = confirmar_operacao_wa(
                    enviar_midia(
                        jid_real, anexo.read(), formato_anexo["nome"],
                        formato_anexo["mime"], formato_anexo["tipo"], mensagem,
                    ),
                    "envio individual de anexo",
                )
            else:
                resposta = confirmar_operacao_wa(
                    enviar_mensagem_chat(jid_real, mensagem), "envio individual",
                )
            broadcast_id = None
        else:
            if anexo:
                resposta = confirmar_operacao_wa(
                    enviar_broadcast_midia(
                        destinatarios, mensagem, anexo.read(),
                        formato_anexo["nome"], formato_anexo["mime"],
                    ),
                    "disparo de imagem/PDF",
                )
            else:
                resposta = confirmar_operacao_wa(
                    enviar_broadcast(destinatarios, mensagem), "envio coletivo",
                )
            broadcast_id = (resposta.get("data") or {}).get("broadcastId")
    except WhatsAppGatewayError as exc:
        messages.error(request, f"Falha ao enviar a mensagem: {exc}")
        return redirect("whatsapp")

    complemento = f" Lote #{broadcast_id}." if broadcast_id else ""
    aviso_invalidos = (
        f" {invalidos} telefone(s) inválido(s) foram ignorados."
        if invalidos
        else ""
    )
    if nao_localizados:
        aviso_invalidos += (
            f" {nao_localizados} número(s) não registrado(s) no WhatsApp foram ignorados."
        )
    messages.success(
        request,
        (
            f"Envio iniciado para {len(destinatarios)} contato(s)."
            f"{complemento}{aviso_invalidos}"
        ),
    )
    return redirect("whatsapp")



def _validar_anexo_campanha(arquivo):
    """Uma única imagem ou PDF; conteúdo verificado, não só a extensão.

    A mesma validação serve aos anexos opcionais dos boletins. Nunca
    persiste os bytes quando o tipo é desconhecido.
    """
    if not arquivo:
        return None
    if arquivo.size <= 0 or arquivo.size > 25 * 1024 * 1024:
        raise ValueError("O anexo deve ter entre 1 byte e 25 MB.")
    nome = str(arquivo.name or "").lower().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    extensao = nome.rsplit(".", 1)[-1] if "." in nome else ""
    cabecalho = arquivo.read(16)
    arquivo.seek(0)
    formatos = {
        "jpg": ("image/jpeg", cabecalho.startswith(b"\xff\xd8\xff"), "imagem.jpg", "image"),
        "jpeg": ("image/jpeg", cabecalho.startswith(b"\xff\xd8\xff"), "imagem.jpg", "image"),
        "png": ("image/png", cabecalho.startswith(b"\x89PNG\r\n\x1a\n"), "imagem.png", "image"),
        "webp": ("image/webp", cabecalho[:4] == b"RIFF" and cabecalho[8:12] == b"WEBP", "imagem.webp", "image"),
        "pdf": ("application/pdf", cabecalho.startswith(b"%PDF-"), "documento.pdf", "document"),
    }
    formato = formatos.get(extensao)
    if not formato or not formato[1]:
        raise ValueError("Anexe somente imagens JPG, PNG, WEBP ou documentos PDF válidos.")
    mime, _, nome_seguro, tipo = formato
    return {"mime": mime, "nome": nome_seguro, "tipo": tipo}


def _jid_eh_telefone(jid):
    return bool(jid and str(jid).endswith(("@s.whatsapp.net", "@c.us")))


def _contatos_wa():
    try:
        resposta = listar_contatos()
        contatos = resposta.get("data") if isinstance(resposta, dict) else []
        return contatos if isinstance(contatos, list) else []
    except WhatsAppGatewayError:
        return []


def _identidades_wa():
    """Vínculos persistentes; não depender do cache local de cada worker."""
    return list(
        IdentidadeContatoWhatsApp.objects.filter(sessao=sessao_atual_id())
        .values("jid", "telefone_jid", "nome_exibicao", "origem")
    )


def _contatos_persistidos_wa(identidades=None):
    return [
        {
            "jid": dado["jid"],
            "lid": dado["jid"] if dado["jid"].endswith("@lid") else "",
            "remoteJidAlt": dado["telefone_jid"],
            # O apelido manual é aplicado depois da mesclagem.
        }
        for dado in (identidades if identidades is not None else _identidades_wa())
        if dado["telefone_jid"]
    ]


_CAMPOS_JID_WA = (
    "jid", "id", "lid", "remoteJidAlt", "phoneJid", "pnJid", "phoneNumberJid"
)
_CAMPOS_NOME_WA = (
    "name", "verifiedName", "notify", "pushName", "pushname",
    "displayName", "fullName", "shortName", "businessName",
)
_ROTULOS_INVALIDOS_WA = {
    "", "contato whatsapp", "whatsapp", "unknown", "sem nome",
    "contato sem identificação", "número não identificado",
}


def _nome_disponivel_no_wa(registro, *, perfil=False):
    """Nome realmente retornado pelo WA-AKG; nunca gerar nome a partir de LID."""
    if not isinstance(registro, dict):
        return ""
    campos = (
        ("notify", "pushName", "pushname", "displayName", "fullName", "shortName", "name", "verifiedName")
        if perfil else _CAMPOS_NOME_WA
    )
    for fonte in (registro, registro.get("data")):
        if not isinstance(fonte, dict):
            continue
        for campo in campos:
            nome = fonte.get(campo)
            if not isinstance(nome, str):
                continue
            nome = nome.strip()
            if (
                nome and len(nome) <= 160
                and nome.casefold() not in _ROTULOS_INVALIDOS_WA
                and not nome.endswith(("@lid", "@s.whatsapp.net", "@c.us"))
            ):
                return nome
    return ""


def _jids_do_registro(registro):
    """Somente vínculos JID explícitos do WhatsApp; jamais juntar por nome/foto."""
    if not isinstance(registro, dict):
        return set()
    valores = set()
    for fonte in (registro, registro.get("data")):
        if not isinstance(fonte, dict):
            continue
        for campo in _CAMPOS_JID_WA:
            valor = fonte.get(campo)
            if isinstance(valor, str):
                valores.add(valor.strip())
    extras = registro.get("aliases")
    if isinstance(extras, list):
        valores.update(str(item or "").strip() for item in extras)
    return {
        valor for valor in valores
        if valor.endswith(("@lid", "@s.whatsapp.net", "@c.us", "@g.us"))
    }


def _mapa_aliases_wa(contatos, chats=()):
    """Componentes conexos de JIDs, inclusive ligações transitivas LID/telefone."""
    vizinhos = defaultdict(set)
    for registro in list(contatos) + list(chats):
        ids = _jids_do_registro(registro)
        for jid in ids:
            vizinhos[jid].update(ids - {jid})
            if jid.endswith("@c.us"):
                normalizado = jid.replace("@c.us", "@s.whatsapp.net")
                vizinhos[jid].add(normalizado)
                vizinhos[normalizado].add(jid)

    grupos = {}
    for jid in sorted(vizinhos):
        if jid in grupos:
            continue
        componente = set()
        pendentes = [jid]
        while pendentes:
            atual = pendentes.pop()
            if atual in componente:
                continue
            componente.add(atual)
            pendentes.extend(vizinhos[atual] - componente)
        aliases = tuple(sorted(componente))
        for item in aliases:
            grupos[item] = aliases
    return grupos


def _aliases_contato_wa(jid, contatos=None):
    """Retorna o JID informado e aliases com ligação comprovada no WA-AKG."""
    jid = str(jid or "").strip()
    if not jid:
        return []
    registros = list(contatos if contatos is not None else _contatos_wa())
    registros.extend(_contatos_persistidos_wa())
    grupos = _mapa_aliases_wa(registros)
    return [jid] + [item for item in grupos.get(jid, ()) if item != jid]


def _mapa_nomes_telefones_escola_wa():
    """Carrega os nomes da base escolar UMA vez por atualização.

    A implementação anterior percorria a tabela inteira para cada um dos
    até 1.591 chats, causando milhares de leituras e travamentos visuais.
    """
    mapa = {}
    registros = TelefoneDeclaracao.objects.select_related("declaracao").all()
    for registro in registros.iterator(chunk_size=500):
        salvo = re.sub(r"\D", "", registro.telefone or "")
        if not salvo:
            continue
        sem_55 = salvo[2:] if salvo.startswith("55") and len(salvo) in (12, 13) else salvo
        dec = registro.declaracao
        if registro.tipo == "PAI":
            nome = dec.nomePai or f"Pai de {dec.nomeDoAluno}"
        elif registro.tipo == "MAE":
            nome = dec.nomeMae or f"Mãe de {dec.nomeDoAluno}"
        elif registro.tipo == "RESPONSAVEL":
            nome = dec.nomeResponsavel or f"Responsável por {dec.nomeDoAluno}"
        else:
            nome = dec.nomeDoAluno or ""
        if not nome:
            continue
        for variante in {salvo, sem_55, "55" + sem_55}:
            mapa.setdefault(variante, nome)
    return mapa


def _nome_local_por_telefone(phone_jid, *, mapa=None):
    """Consulta índice de telefones, não a tabela inteira por conversa."""
    digitos = re.sub(r"\D", "", str(phone_jid or "").split("@")[0])
    if not digitos:
        return ""
    base = mapa if mapa is not None else _mapa_nomes_telefones_escola_wa()
    return base.get(digitos) or (
        base.get(digitos[2:]) if digitos.startswith("55") else ""
    ) or ""


def _enriquecer_chats(chats):
    """Consolida LID/telefone com ligações explícitas e preserva o histórico."""
    chats = [dict(item) for item in (chats or []) if isinstance(item, dict) and item.get("jid")]
    if not chats:
        return []

    identidades = _identidades_wa()
    nomes_agenda = dict(
        ContatoAgendaWhatsApp.objects.filter(
            sessao=sessao_atual_id()
        ).values_list("telefone_jid", "nome")
    )
    nomes_escola = None  # lazy: carregar somente se algum chat precisar
    nomes_manuais = {
        item["jid"]: item["nome_exibicao"]
        for item in identidades if item["origem"] == "MANUAL" and item["nome_exibicao"]
    }
    nomes_perfil = {
        item["jid"]: item["nome_exibicao"]
        for item in identidades if item["origem"] == "METADATA" and item["nome_exibicao"]
    }
    contatos = _contatos_wa() + _contatos_persistidos_wa(identidades)
    # Registros @lid antigos nem sempre têm o telefone na tabela Contact.
    # O histórico recebido pode conter senderJid (telefone) e pushName,
    # informados diretamente pelo WhatsApp. Consultar no máximo três LIDs
    # novos por atualização e guardar o resultado em cache por alguns minutos.
    grupos_previos = _mapa_aliases_wa(contatos, chats)
    consultas = 0
    for chat in chats:
        jid = str(chat["jid"])
        if not jid.endswith("@lid") or not gateway_configurado():
            continue
        aliases = grupos_previos.get(jid, (jid,))
        if any(_jid_eh_telefone(item) for item in aliases):
            continue
        chave_cache = "emeca:whatsapp:lid:" + sha256(
            (sessao_atual_id() + "/" + jid).encode("utf-8")
        ).hexdigest()
        identidade = cache.get(chave_cache)
        if identidade is None:
            if consultas >= 3:
                continue
            consultas += 1
            mensagens, disponivel = _mensagens_para_contar([jid])
            telefone = ""
            nome_perfil = ""
            for msg in sorted(
                mensagens, key=lambda m: str(m.get("timestamp") or ""), reverse=True
            ):
                if msg.get("fromMe") is True:
                    continue
                if not telefone:
                    candidato = str(msg.get("senderJid") or "")
                    if _jid_eh_telefone(candidato):
                        telefone = candidato.replace("@c.us", "@s.whatsapp.net")
                if not nome_perfil:
                    nome_perfil = _nome_disponivel_no_wa(msg, perfil=True)
                if telefone and nome_perfil:
                    break
            identidade = {"telefone": telefone, "nome": nome_perfil}
            # Uma associação comprovada pelo senderJid precisa sobreviver a
            # reinícios e a processos Gunicorn com caches diferentes.
            if telefone or nome_perfil:
                salvo, criado = IdentidadeContatoWhatsApp.objects.get_or_create(
                    sessao=sessao_atual_id(),
                    jid=jid,
                    defaults={
                        "telefone_jid": telefone,
                        "nome_exibicao": nome_perfil[:160],
                        "origem": "METADATA",
                    },
                )
                if not criado and salvo.origem == "METADATA":
                    alterou = False
                    if telefone and salvo.telefone_jid != telefone:
                        salvo.telefone_jid = telefone
                        alterou = True
                    if nome_perfil and salvo.nome_exibicao != nome_perfil[:160]:
                        salvo.nome_exibicao = nome_perfil[:160]
                        alterou = True
                    if alterou:
                        salvo.save(update_fields=["telefone_jid", "nome_exibicao", "atualizado_em"])
            if disponivel:
                cache.set(chave_cache, identidade, 900 if telefone or nome_perfil else 120)
            else:
                cache.set(chave_cache, identidade, 45)
        if identidade.get("telefone") or identidade.get("nome"):
            # Persistir também associações obtidas antes desta versão,
            # ainda presentes em cache, para que o histórico seja uniforme.
            telefone_confirmado = identidade.get("telefone") or ""
            if _jid_eh_telefone(telefone_confirmado):
                salvo, criado = IdentidadeContatoWhatsApp.objects.get_or_create(
                    sessao=sessao_atual_id(),
                    jid=jid,
                    defaults={
                        "telefone_jid": telefone_confirmado,
                        "nome_exibicao": str(identidade.get("nome") or "")[:160],
                        "origem": "METADATA",
                    },
                )
                if not criado and salvo.origem == "METADATA" and not salvo.telefone_jid:
                    salvo.telefone_jid = telefone_confirmado
                    salvo.save(update_fields=["telefone_jid", "atualizado_em"])
            contatos.append({
                "jid": jid,
                "lid": jid,
                "remoteJidAlt": identidade.get("telefone") or "",
                "notify": identidade.get("nome") or "",
                "name": identidade.get("nome") or "",
            })
    grupos_aliases = _mapa_aliases_wa(contatos, chats)
    contatos_por_id = defaultdict(list)
    for contato in contatos:
        if not isinstance(contato, dict):
            continue
        for jid in _jids_do_registro(contato):
            contatos_por_id[jid].append(contato)

    unidos = defaultdict(list)
    for chat in chats:
        jid = str(chat["jid"])
        aliases = grupos_aliases.get(jid, (jid,))
        telefones = sorted(
            item.replace("@c.us", "@s.whatsapp.net")
            for item in aliases if _jid_eh_telefone(item)
        )
        chave = telefones[0] if telefones else aliases[0]
        unidos[chave].append(chat)

    resultado = []
    genericos = {"", "contato whatsapp", "whatsapp", "unknown", "sem nome"}
    for chave, partes in unidos.items():
        ids = set()
        for parte in partes:
            jid = str(parte["jid"])
            ids.update(grupos_aliases.get(jid, (jid,)))
        aliases = sorted(ids)
        telefones = sorted({
            jid.replace("@c.us", "@s.whatsapp.net")
            for jid in aliases if _jid_eh_telefone(jid)
        })
        phone_jid = telefones[0] if telefones else ""

        # Não descartar mensagens de uma das metades: ambos os JIDs
        # permanecem nos aliases usados pelo endpoint de histórico.
        ultimo = max(
            partes,
            key=lambda item: str((item.get("lastMessage") or {}).get("timestamp") or ""),
        )
        merged = dict(ultimo)
        merged["jid"] = phone_jid or str(ultimo["jid"])
        merged["aliases"] = [merged["jid"]] + [
            jid for jid in aliases if jid != merged["jid"]
        ]
        merged["phoneJid"] = phone_jid
        merged["photoJid"] = phone_jid or str(ultimo["jid"])

        contatos_grupo = []
        vistos_contatos = set()
        for jid in aliases:
            for contato in contatos_por_id.get(jid, []):
                identificador = id(contato)
                if identificador not in vistos_contatos:
                    vistos_contatos.add(identificador)
                    contatos_grupo.append(contato)

        nomes = []
        apelidos = []
        for contato in contatos_grupo:
            for chave_nome in ("name", "verifiedName"):
                nome = str(contato.get(chave_nome) or "").strip()
                apelido = str(contato.get("notify") or "").strip()
                if nome.casefold() not in genericos:
                    # Name=pushName não comprova que foi salvo no telefone.
                    if not (phone_jid and apelido and nome.casefold() == apelido.casefold()
                            and not contato.get("verifiedName")):
                        nomes.append(nome)
            if contato.get("notify"):
                apelidos.append(str(contato["notify"]).strip())

        for parte in partes:
            nome = str(parte.get("name") or "").strip()
            apelido = str(parte.get("notify") or "").strip()
            if nome.casefold() not in genericos:
                if not (phone_jid and apelido and nome.casefold() == apelido.casefold()):
                    nomes.append(nome)
            if apelido:
                apelidos.append(apelido)

        nome = nomes[0] if nomes else ""
        if not nome:
            # Para contatos sem telefone, aceitar também o nome de perfil e
            # metadados históricos; com telefone, preferir número ao pushName.
            nome = next(
                (
                    _nome_disponivel_no_wa(contato, perfil=True)
                    for contato in contatos_grupo
                    if not phone_jid and _nome_disponivel_no_wa(contato, perfil=True)
                ),
                "",
            )
        if not nome and phone_jid:
            nome = nomes_agenda.get(phone_jid) or ""
            if not nome:
                if nomes_escola is None:
                    nomes_escola = _mapa_nomes_telefones_escola_wa()
                nome = _nome_local_por_telefone(phone_jid, mapa=nomes_escola)
        if not nome and not phone_jid:
            nome = next(
                (texto for texto in apelidos if texto.casefold() not in genericos),
                "",
            )
        nome_manual = next(
            (nomes_manuais[jid] for jid in [merged["jid"], *aliases] if jid in nomes_manuais),
            "",
        )
        nome_remoto = next(
            (nomes_perfil[jid] for jid in [merged["jid"], *aliases] if jid in nomes_perfil),
            "",
        )
        # A agenda Android relaciona nomes somente a telefones reais.
        # Um ID @lid sem número comprovado continua sem vínculo.
        nome_agenda = nomes_agenda.get(phone_jid, "") if phone_jid else ""
        merged["name"] = (
            nome_manual or nome_agenda or nome
            or (nome_remoto if not phone_jid else "")
        )
        merged["nomeAgenda"] = bool(nome_agenda)
        merged["nomeManual"] = bool(nome_manual)
        merged["notify"] = next(
            (texto for texto in apelidos if texto.casefold() not in genericos), ""
        )

        fotos = [
            item.get("profilePic") for item in contatos_grupo + partes
            if item.get("profilePic")
        ]
        merged["profilePic"] = next(
            (foto for foto in fotos if str(foto).startswith(("https://", "http://"))),
            "",
        )
        resultado.append(merged)

    # Mostrar os últimos estados confirmados pelo WA-AKG sem consultar a
    # API remota uma vez para cada botão ou conversa (a lista pode ser grande).
    estados = {
        obj.jid: obj for obj in EstadoConversaWhatsApp.objects.filter(
            sessao=sessao_atual_id(),
            jid__in=[item["jid"] for item in resultado],
        )
    }
    for item in resultado:
        estado = estados.get(item["jid"])
        item["fixado"] = bool(estado and estado.fixado)
        item["silenciado"] = bool(estado and estado.silenciado)
        item["arquivado"] = bool(estado and estado.arquivado)
        item["bloqueado"] = bool(estado and estado.bloqueado)

    # Uma consulta para todas as etiquetas, sem executar 1.500 requisições
    # remotas por atualização. O WA-AKG permanece a fonte das atribuições.
    jids = [item["jid"] for item in resultado]
    etiquetas_por_jid = defaultdict(list)
    for etiqueta in EtiquetaConversaWhatsApp.objects.filter(
        sessao=sessao_atual_id(), jid__in=jids
    ).order_by("nome").values("jid", "etiqueta_id", "nome", "cor"):
        etiquetas_por_jid[etiqueta["jid"]].append({
            "id": etiqueta["etiqueta_id"],
            "name": etiqueta["nome"],
            "colorHex": etiqueta["cor"],
        })
    for item in resultado:
        item["etiquetas"] = etiquetas_por_jid.get(item["jid"], [])
    # Fixadas aparecem no topo, mesmo quando recebem mensagens outras contas.
    resultado.sort(
        key=lambda item: (
            bool(item["fixado"]),
            str((item.get("lastMessage") or {}).get("timestamp") or ""),
        ),
        reverse=True,
    )
    return resultado


def _etiquetas_visiveis_da_conversa(jid):
    return list(
        EtiquetaConversaWhatsApp.objects.filter(
            sessao=sessao_atual_id(), jid=jid
        ).order_by("nome").values("etiqueta_id", "nome", "cor")
    )


def _sincronizar_etiquetas_wa(jid, etiquetas):
    """Atualiza cache local SOMENTE após confirmação do WA-AKG.

    A resposta da edição de etiquetas usa 'success:true' e uma lista no
    nível raiz; a consulta usa 'status:true' e 'data.labels'.
    """
    if not isinstance(etiquetas, list):
        raise WhatsAppGatewayError("WA-AKG não devolveu a lista de etiquetas.")
    ids = set()
    with transaction.atomic():
        for item in etiquetas:
            if not isinstance(item, dict) or not str(item.get("id") or "").strip():
                continue
            label_id = str(item["id"])
            ids.add(label_id)
            EtiquetaConversaWhatsApp.objects.update_or_create(
                sessao=sessao_atual_id(), jid=jid, etiqueta_id=label_id,
                defaults={
                    "nome": str(item.get("name") or "Etiqueta")[:100],
                    "cor": str(item.get("colorHex") or "#94a3b8")[:16],
                }
            )
        base = EtiquetaConversaWhatsApp.objects.filter(
            sessao=sessao_atual_id(), jid=jid
        )
        if ids:
            base.exclude(etiqueta_id__in=ids).delete()
        else:
            base.delete()
    return _etiquetas_visiveis_da_conversa(jid)


def _instante_mensagem_whatsapp(valor):
    """Converte timestamp ISO/epoch sem supor fuso horário local."""
    if valor in (None, ""):
        return None
    if isinstance(valor, (int, float)):
        try:
            return timezone.datetime.fromtimestamp(float(valor), tz=datetime_timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    data = parse_datetime(str(valor))
    if data is None:
        return None
    if timezone.is_naive(data):
        data = timezone.make_aware(data, datetime_timezone.utc)
    return data


def _mensagens_para_contar(aliases):
    """Busca mensagens recentes em todos os JIDs vinculados, sem duplicar IDs."""
    unicas = {}
    disponivel = False
    for alias in dict.fromkeys(aliases):
        try:
            payload = obter_mensagens_chat(alias)
        except WhatsAppGatewayError:
            continue
        disponivel = True
        mensagens = payload.get("data") if isinstance(payload, dict) else []
        if isinstance(mensagens, dict):
            mensagens = mensagens.get("messages") or []
        if not isinstance(mensagens, list):
            continue
        for msg in mensagens:
            if not isinstance(msg, dict):
                continue
            chave = (msg.get("keyId") or msg.get("id")
                     or f'{msg.get("timestamp")}-{msg.get("content")}-{msg.get("fromMe")}')
            unicas[str(chave)] = msg
    return list(unicas.values()), disponivel


def _sincronizar_nao_lidas(usuario, chats):
    """Notificações por operador a partir da primeira sincronização do EMECA.

    O endpoint de chats do WA-AKG não traz unreadCount. A primeira leitura
    registra somente a referência; mensagens posteriores são computadas pelo
    histórico, considerando apenas mensagens recebidas e distintas.
    """
    if not chats:
        return chats

    jids = [str(chat["jid"]) for chat in chats]
    estados = {
        estado.jid: estado
        for estado in LeituraChatWhatsApp.objects.filter(
            usuario=usuario, sessao=sessao_atual_id(), jid__in=jids
        )
    }
    for chat in chats:
        jid = str(chat["jid"])
        ultima = _instante_mensagem_whatsapp(
            (chat.get("lastMessage") or {}).get("timestamp")
        )
        estado = estados.get(jid)
        if estado is None:
            estado, _ = LeituraChatWhatsApp.objects.get_or_create(
                usuario=usuario,
                sessao=sessao_atual_id(),
                jid=jid,
                defaults={"ultima_verificacao_em": ultima},
            )
            estados[jid] = estado
        elif ultima and (not estado.ultima_verificacao_em or ultima > estado.ultima_verificacao_em):
            anterior = estado.ultima_verificacao_em
            mensagens, disponivel = _mensagens_para_contar(chat.get("aliases") or [jid])
            if disponivel:
                recebidas = 0
                for msg in mensagens:
                    instante = _instante_mensagem_whatsapp(msg.get("timestamp"))
                    if not instante or (anterior and instante <= anterior):
                        continue
                    if msg.get("fromMe") is True:
                        continue
                    # Não contar envelopes técnicos TEXT sem conteúdo.
                    if str(msg.get("type") or "").upper() == "TEXT" and not str(msg.get("content") or "").strip():
                        continue
                    recebidas += 1
                estado.nao_lidas += recebidas
                estado.ultima_verificacao_em = ultima
                estado.save(update_fields=["nao_lidas", "ultima_verificacao_em"])
        chat["naoLidas"] = estado.nao_lidas
    return chats


def _marcar_como_vista_no_emeca(usuario, jid, mensagens=None):
    """Limpa notificações do operador após abrir uma conversa com sucesso."""
    instantes = [
        _instante_mensagem_whatsapp(msg.get("timestamp"))
        for msg in (mensagens or [])
        if isinstance(msg, dict)
    ]
    vistos = [item for item in instantes if item is not None]
    ultimo = max(vistos) if vistos else timezone.now()
    estado, _ = LeituraChatWhatsApp.objects.get_or_create(
        usuario=usuario, sessao=sessao_atual_id(), jid=jid,
        defaults={"ultima_verificacao_em": ultimo},
    )
    if estado.ultima_verificacao_em and estado.ultima_verificacao_em > ultimo:
        ultimo = estado.ultima_verificacao_em
    estado.ultima_verificacao_em = ultimo
    estado.nao_lidas = 0
    estado.save(update_fields=["ultima_verificacao_em", "nao_lidas"])


@login_required
@require_POST
def whatsapp_identificar_contato_api(request):
    """Define apelido interno ou une um LID a uma conversa telefônica existente.

    Não altera a agenda do WhatsApp nem inventa telefone a partir do LID.
    A vinculação é uma confirmação explícita feita pelo operador.
    """
    jid = (request.POST.get("jid") or "").strip()
    nome = (request.POST.get("nome") or "").strip()
    telefone = (request.POST.get("telefone_jid") or "").strip().replace(
        "@c.us", "@s.whatsapp.net"
    )
    if not re.fullmatch(r"[0-9]{5,25}@(lid|s\.whatsapp\.net)", jid):
        return JsonResponse({"ok": False, "erro": "Contato inválido."}, status=400)
    if len(nome) > 160 or any(ord(char) < 32 for char in nome):
        return JsonResponse({"ok": False, "erro": "Nome inválido."}, status=400)
    if telefone and (
        not jid.endswith("@lid")
        or not re.fullmatch(r"[0-9]{10,15}@s\.whatsapp\.net", telefone)
    ):
        return JsonResponse({"ok": False, "erro": "Selecione uma conversa telefônica válida."}, status=400)

    try:
        payload = listar_chats()
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)
    chats = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(chats, list):
        chats = []
    disponiveis = {
        str(chat.get("jid") or "")
        for chat in chats if isinstance(chat, dict)
    }
    # Não permitir que um operador informe um JID inexistente/aleatório.
    if jid not in disponiveis:
        # Pode existir apenas na tabela Contact, como alias do chat telefônico.
        registro_contato = any(
            jid in _jids_do_registro(contato) for contato in _contatos_wa()
        )
        ja_registrado = IdentidadeContatoWhatsApp.objects.filter(
            sessao=sessao_atual_id(), jid=jid
        ).exists()
        if not (ja_registrado or registro_contato):
            return JsonResponse({"ok": False, "erro": "Contato não encontrado nas conversas."}, status=400)
    if telefone and telefone not in disponiveis:
        return JsonResponse({
            "ok": False,
            "erro": "O número escolhido precisa constar na lista de conversas do WhatsApp.",
        }, status=400)

    with transaction.atomic():
        if nome or telefone:
            IdentidadeContatoWhatsApp.objects.update_or_create(
                sessao=sessao_atual_id(),
                jid=jid,
                defaults={
                    "telefone_jid": telefone,
                    "nome_exibicao": nome,
                    "origem": "MANUAL",
                },
            )
        else:
            IdentidadeContatoWhatsApp.objects.filter(
                sessao=sessao_atual_id(), jid=jid, origem="MANUAL"
            ).delete()
    if jid.endswith("@lid"):
        cache.delete("emeca:whatsapp:lid:" + sha256(
            (sessao_atual_id() + "/" + jid).encode("utf-8")
        ).hexdigest())
    return JsonResponse({"ok": True, "jid": jid, "nome": nome, "telefone_jid": telefone})


def _validar_sessao_cliente(request):
    """Impede operações de abas antigas após a troca da conta WhatsApp."""
    informada = (
        request.headers.get("X-EMECA-WA-SESSION")
        or request.POST.get("wa_session_id")
        or request.GET.get("wa_session_id")
        or ""
    ).strip()
    if informada and informada != sessao_atual_id():
        return JsonResponse({
            "ok": False,
            "erro": "A conta do WhatsApp foi alterada. Recarregue a página antes de continuar.",
            "sessao_alterada": True,
        }, status=409)
    return None


def _limite_exclusao_conversa_wa(usuario, aliases):
    """Maior corte já registrado para qualquer JID associado à conversa."""
    limites = ConversaExcluidaWhatsApp.objects.filter(
        usuario=usuario, sessao=sessao_atual_id(),
        jid__in=aliases
    ).values_list("ultima_mensagem_em", flat=True)
    datas = [_instante_mensagem_whatsapp(valor) for valor in limites]
    return max((data for data in datas if data is not None), default=None)


def _combinar_chats_e_grupos_wa(chats):
    """Inclui grupos existentes ainda sem mensagens na caixa de entrada.

    O endpoint chat do WA-AKG só enumera JIDs que já possuem mensagem,
    enquanto o endpoint de grupos guarda metadados inclusive após criação.
    """
    ocultos = set(GrupoOcultoWhatsApp.objects.filter(
        sessao=sessao_atual_id()
    ).values_list("jid", flat=True))
    existentes = [
        chat for chat in (chats if isinstance(chats, list) else [])
        if isinstance(chat, dict) and chat.get("jid") not in ocultos
    ]
    jids = {str(chat.get("jid") or "") for chat in existentes}
    try:
        payload = listar_grupos()
        grupos = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(grupos, list):
            return existentes
        for grupo in grupos:
            if not isinstance(grupo, dict):
                continue
            jid = str(grupo.get("jid") or "")
            if not jid.endswith("@g.us") or jid in jids or jid in ocultos:
                continue
            existentes.append({
                "jid": jid, "name": grupo.get("subject") or "Grupo sem nome",
                "notify": grupo.get("subject") or "Grupo sem nome",
                "lastMessage": {}, "profilePic": "",
                "groupChat": True,
            })
            jids.add(jid)
    except WhatsAppGatewayError:
        # Sem impedir a leitura das mensagens se a rota de grupos falhar.
        pass
    return existentes


def _filtrar_conversas_excluidas_wa(usuario, chats):
    """Oculta até chegar mensagem posterior ao momento da exclusão."""
    if not chats:
        return chats
    jids = {
        identificador for chat in chats
        for identificador in [chat.get("jid"), *(chat.get("aliases") or [])]
        if identificador
    }
    grupos_ocultos = set(
        GrupoOcultoWhatsApp.objects.filter(
            sessao=sessao_atual_id(), jid__in=jids
        ).values_list("jid", flat=True)
    )
    chats = [
        chat for chat in chats
        if chat.get("jid") not in grupos_ocultos and
        not set(chat.get("aliases") or []).intersection(grupos_ocultos)
    ]
    cortes = {
        linha.jid: _instante_mensagem_whatsapp(linha.ultima_mensagem_em)
        for linha in ConversaExcluidaWhatsApp.objects.filter(
            usuario=usuario, sessao=sessao_atual_id(), jid__in=jids
        )
    }
    visiveis = []
    for chat in chats:
        aliases = [chat.get("jid"), *(chat.get("aliases") or [])]
        limite = max(
            (cortes[jid] for jid in aliases if jid in cortes and cortes[jid] is not None),
            default=None,
        )
        if limite is None:
            visiveis.append(chat)
            continue
        ultima = _instante_mensagem_whatsapp(
            (chat.get("lastMessage") or {}).get("timestamp")
        )
        if ultima is not None and ultima > limite:
            visiveis.append(chat)
    return visiveis


@login_required
def whatsapp_mensagens(request):
    # Não consultar o gateway quando uma limpeza destrutiva está incompleta.
    # O usuário ainda consegue abrir a página e entender o bloqueio.
    status = "NAO_CONFIGURADO"
    status_detalhe = ""
    chats = []
    db_indisponivel = False
    try:
        pendente = limpeza_historico_pendente()
        sessao_id = sessao_atual_id()
    except DatabaseError as exc:
        logger.error("Estado da sessão WhatsApp indisponível: %s", type(exc).__name__)
        pendente = True
        sessao_id = ""
        db_indisponivel = True

    if pendente:
        status = "LIMPEZA_PENDENTE"
        status_detalhe = (
            "A limpeza anterior não foi concluída. Por segurança, não é possível "
            "consultar mensagens nem alterar a conexão até reconciliar a sessão."
        )
    elif gateway_configurado():
        try:
            resposta = obter_sessao()
            data = resposta.get("data") if isinstance(resposta, dict) else {}
            data = data if isinstance(data, dict) else {}
            status = str(data.get("status") or (
                resposta.get("status") if isinstance(resposta, dict) else ""
            ) or "DESCONHECIDO").upper()
        except WhatsAppGatewayError:
            status = "INDISPONIVEL"
            status_detalhe = "O WhatsApp está temporariamente indisponível."

    return render(request, "whatsapp_mensagens.html", {
        "gateway_configurado": gateway_configurado() and not db_indisponivel,
        "gateway_status": status,
        "gateway_status_detalhe": status_detalhe,
        "pode_desconectar": _pode_desconectar_whatsapp(request.user) and not pendente,
        "limpeza_pendente": pendente,
        "wa_sessao_id": sessao_id,
        "chats_iniciais": chats,
    })


@login_required
@require_GET
def whatsapp_chats_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    if not gateway_configurado():
        return JsonResponse(
            {"ok": False, "erro": "Integração ainda não configurada."},
            status=503,
        )

    # A caixa pode ter milhares de conversas. Não solicitar as 25 páginas
    # de 500 contatos na mesma requisição: usar uma página por chamada.
    try:
        tamanho = int(request.GET.get("limit") or "30")
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "erro": "Limite inválido."}, status=400)
    tamanho = max(1, min(50, tamanho))
    cursor = (request.GET.get("before") or "").strip()
    if len(cursor) > 64 or (cursor and parse_datetime(cursor) is None):
        return JsonResponse({"ok": False, "erro": "Cursor inválido."}, status=400)

    try:
        payload = listar_chats_pagina(limit=tamanho, before=cursor)
        if not isinstance(payload, dict) or payload.get("status") is False:
            raise WhatsAppGatewayError("A consulta de conversas não foi confirmada.")
        bruto = payload.get("data")
        bruto = bruto if isinstance(bruto, list) else []
        chats = _sincronizar_nao_lidas(
            request.user,
            _filtrar_conversas_excluidas_wa(
                request.user,
                _enriquecer_chats(bruto if cursor else _combinar_chats_e_grupos_wa(bruto)),
            ),
        )
        meta = payload.get("meta") or {}
        proximo = meta.get("nextBefore") if isinstance(meta, dict) else None
        # Se não houver cursor, a API não tem mais páginas. Não adivinhar.
        proximo = str(proximo) if isinstance(proximo, str) and proximo else None
        return JsonResponse({
            "ok": True,
            "chats": chats,
            "totalNaoLidas": sum(chat.get("naoLidas", 0) for chat in chats),
            "nextBefore": proximo,
            "sessao_id": sessao_atual_id(),
        })
    except WhatsAppGatewayError as exc:
        return JsonResponse(
            {"ok": False, "erro": str(exc)},
            status=exc.status_code or 502,
        )
    except Exception as exc:
        # Expor só o tipo do erro nos logs, nunca JID, payload ou token.
        logger.error("Falha na listagem paginada do WhatsApp: %s", type(exc).__name__)
        return JsonResponse({
            "ok": False,
            "erro": "Não foi possível carregar as conversas. Tente atualizar.",
        }, status=503)


@login_required
@require_GET
def whatsapp_chat_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.GET.get("jid") or "").strip()
    if not jid or len(jid) > 120:
        return JsonResponse({"ok": False, "erro": "Conversa inválida."}, status=400)

    contatos = _contatos_wa()
    aliases = _aliases_contato_wa(jid, contatos)
    mensagens_por_id = {}
    erros = []

    for alias in aliases:
        try:
            payload = obter_mensagens_chat(alias)
            mensagens = payload.get("data") if isinstance(payload, dict) else []
            if isinstance(mensagens, dict):
                mensagens = mensagens.get("messages") or []
            if not isinstance(mensagens, list):
                continue
            for msg in mensagens:
                if not isinstance(msg, dict):
                    continue
                chave = (
                    msg.get("keyId")
                    or msg.get("id")
                    or f'{msg.get("timestamp")}-{msg.get("content")}-{msg.get("fromMe")}'
                )
                mensagens_por_id[str(chave)] = msg
        except WhatsAppGatewayError as exc:
            erros.append(exc)

    mensagens = list(mensagens_por_id.values())
    mensagens.sort(key=lambda item: str(item.get("timestamp") or ""))
    limite = _limite_exclusao_conversa_wa(request.user, aliases)
    if limite is not None:
        mensagens = [
            msg for msg in mensagens
            if (data := _instante_mensagem_whatsapp(msg.get("timestamp")))
            is not None and data > limite
        ]
    ocultas = set(
        MensagemOcultaWhatsApp.objects.filter(
            usuario=request.user, sessao=sessao_atual_id(),
            mensagem_id__in=[
                str(msg.get("keyId") or msg.get("id") or "")
                for msg in mensagens
            ]
        ).values_list("mensagem_id", flat=True)
    )
    if ocultas:
        mensagens = [
            msg for msg in mensagens
            if str(msg.get("keyId") or msg.get("id") or "") not in ocultas
        ]

    if not mensagens and erros and len(erros) == len(aliases):
        exc = erros[0]
        return JsonResponse(
            {"ok": False, "erro": str(exc)},
            status=exc.status_code or 502,
        )

    for alias in aliases:
        try:
            marcar_chat_como_lido(alias)
            break
        except WhatsAppGatewayError:
            continue

    # Alguns contatos antigos não possuem name na tabela Contact, mas o
    # pushName vem nas mensagens recebidas.
    nome = next(
        (
            str(msg.get("pushName") or "").strip()
            for msg in reversed(mensagens)
            if not msg.get("fromMe") and str(msg.get("pushName") or "").strip()
        ),
        "",
    )

    _marcar_como_vista_no_emeca(request.user, jid, mensagens)
    return JsonResponse(
        {
            "ok": True,
            "mensagens": mensagens,
            "aliases": aliases,
            "nome": nome,
        }
    )


@login_required
@require_GET
def whatsapp_perfil_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    """Perfil de conversa retornado pelo WA-AKG, sem adivinhar telefone pelo LID.

    Dados privados só são entregues a usuários autenticados; não expomos
    URLs remotas de mídia nem detalhes internos de autenticação do WA-AKG.
    """
    jid = (request.GET.get("jid") or "").strip()
    if not jid or len(jid) > 120 or not re.fullmatch(
        r"[0-9-]{5,85}@(lid|s\.whatsapp\.net|c\.us|g\.us)", jid
    ):
        return JsonResponse({"ok": False, "erro": "Contato inválido."}, status=400)

    if not gateway_configurado():
        return JsonResponse(
            {"ok": False, "erro": "Integração WhatsApp não configurada."},
            status=503,
        )

    contatos = _contatos_wa()
    aliases = _aliases_contato_wa(jid, contatos)
    ids = set(aliases)
    localizados = [
        contato for contato in contatos
        if isinstance(contato, dict) and _jids_do_registro(contato).intersection(ids)
    ]
    identidades = _identidades_wa()
    apelido_manual = next(
        (item["nome_exibicao"] for item in identidades
         if item["jid"] in ids and item["origem"] == "MANUAL"
         and item["nome_exibicao"]),
        "",
    )
    telefone_jid = next(
        (item.replace("@c.us", "@s.whatsapp.net")
         for item in aliases if _jid_eh_telefone(item)),
        "",
    )
    nome_agenda = (
        ContatoAgendaWhatsApp.objects.filter(
            sessao=sessao_atual_id(), telefone_jid=telefone_jid
        ).values_list("nome", flat=True).first() if telefone_jid else ""
    ) or ""
    nome_salvo = next(
        (_nome_disponivel_no_wa(contato)
         for contato in localizados
         if _nome_disponivel_no_wa(contato)),
        "",
    )
    nome_perfil = next(
        (_nome_disponivel_no_wa(contato, perfil=True)
         for contato in localizados
         if _nome_disponivel_no_wa(contato, perfil=True)),
        "",
    )
    sobre = ""
    for contato in localizados:
        for fonte in (contato, contato.get("data")):
            if not isinstance(fonte, dict):
                continue
            for chave in ("about", "aboutText", "statusText", "description"):
                valor = fonte.get(chave)
                if isinstance(valor, str) and valor.strip():
                    sobre = valor.strip()[:300]
                    break
            if sobre:
                break
        if sobre:
            break
    nome = apelido_manual or nome_agenda or nome_salvo or nome_perfil
    # O WA-AKG pode consultar o recado/"Sobre" em tempo real pelo Baileys.
    # A ausência desse recurso ou restrições de privacidade não impedem abrir
    # as informações de contato já sincronizadas.
    try:
        dados_remotos = obter_perfil_contato(telefone_jid or jid)
        dados_remotos = dados_remotos.get("data") if isinstance(dados_remotos, dict) else None
        if isinstance(dados_remotos, dict):
            status_remoto = dados_remotos.get("about")
            if isinstance(status_remoto, str) and status_remoto.strip():
                sobre = status_remoto.strip()[:300]
            nome_perfil = nome_perfil or str(dados_remotos.get("notify") or "").strip()[:160]
            nome = nome or str(dados_remotos.get("name") or "").strip()[:160]
    except WhatsAppGatewayError:
        pass
    return JsonResponse({
        "ok": True,
        "perfil": {
            "jid": jid,
            "nome": nome or (
                ("+" + telefone_jid.split("@")[0]) if telefone_jid
                else "Contato sem identificação"
            ),
            "nomeSalvo": nome_salvo,
            "nomePerfil": nome_perfil,
            "telefoneJid": telefone_jid,
            "sobre": sobre,
            "fotoDisponivel": any(
                bool(contato.get("profilePic")) for contato in localizados
            ),
        },
    })


@login_required
@require_POST
def whatsapp_foto_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    if not jid or len(jid) > 120:
        return JsonResponse({"ok": False, "erro": "Contato inválido."}, status=400)

    aliases = _aliases_contato_wa(jid)
    for alias in aliases:
        try:
            payload = obter_foto_perfil(alias)
            url = payload.get("profilePicUrl") if isinstance(payload, dict) else None
            if url and str(url).startswith(("https://", "http://")):
                return JsonResponse({"ok": True, "url": url, "jid": alias})
        except WhatsAppGatewayError:
            continue

    return JsonResponse({"ok": True, "url": None})

@login_required
@require_POST
def whatsapp_nova_conversa_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    numero = re.sub(r"\D", "", request.POST.get("numero") or "")
    mensagem = (request.POST.get("mensagem") or "").strip()

    if not jid and numero:
        if numero.startswith("00"):
            numero = numero[2:]
        if not numero.startswith("55") and len(numero) in (10, 11):
            numero = "55" + numero
        try:
            check = verificar_numeros([numero])
        except WhatsAppGatewayError as exc:
            return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)
        resultados = check.get("data", {}).get("results", []) if isinstance(check, dict) else []
        valido = next((item for item in resultados if item.get("exists")), None)
        if not valido:
            return JsonResponse({"ok": False, "erro": "Esse número não foi localizado no WhatsApp."}, status=400)
        jid = valido.get("jid") or ""

    if not jid:
        return JsonResponse({"ok": False, "erro": "Selecione um contato ou informe um número."}, status=400)
    arquivo = request.FILES.get("arquivo")
    if not mensagem and not arquivo:
        return JsonResponse({"ok": False, "erro": "Digite uma mensagem ou escolha um arquivo."}, status=400)
    if len(mensagem) > 4000:
        return JsonResponse({"ok": False, "erro": "Mensagem muito longa."}, status=400)
    if arquivo:
        if arquivo.size > 25 * 1024 * 1024:
            return JsonResponse({"ok": False, "erro": "O arquivo deve ter no máximo 25 MB."}, status=400)
        nome = arquivo.name or "arquivo"
        extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
        if extensao in {"exe", "msi", "bat", "cmd", "com", "scr", "ps1", "vbs", "js", "jar"}:
            return JsonResponse({"ok": False, "erro": "Esse tipo de arquivo não é permitido."}, status=400)
        content_type = (arquivo.content_type or "application/octet-stream").lower()
        tipo = ("image" if content_type.startswith("image/") else
                "video" if content_type.startswith("video/") else
                "audio" if content_type.startswith("audio/") else "document")

    try:
        if arquivo:
            resposta = confirmar_operacao_wa(
                enviar_midia(jid, arquivo.read(), nome, content_type, tipo, mensagem),
                "envio de anexo",
            )
        else:
            resposta = confirmar_operacao_wa(
                enviar_mensagem_chat(jid, mensagem), "nova conversa",
            )
        return JsonResponse({"ok": True, "jid": jid, "resposta": resposta})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_excluir_conversa_api(request):
    """Exclui a conversa apenas da visualização do operador no EMECA.

    Sem DELETE no WA-AKG: preserva a caixa de outros atendentes, o histórico
    auditável da escola e as mensagens no aparelho vinculado.
    """
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    if not jid or len(jid) > 120:
        return JsonResponse({"ok": False, "erro": "Conversa inválida."}, status=400)
    if request.POST.get("confirmacao") != "EXCLUIR":
        return JsonResponse({"ok": False, "erro": "Confirme a exclusão da conversa."}, status=400)
    if not gateway_configurado():
        return JsonResponse({"ok": False, "erro": "WhatsApp indisponível."}, status=503)

    try:
        resposta = listar_chats()
        if not isinstance(resposta, dict) or resposta.get("status") is False:
            raise WhatsAppGatewayError("Não foi possível conferir a conversa no WA-AKG.")
        brutos = resposta.get("data") or []
        chats = _enriquecer_chats(brutos if isinstance(brutos, list) else [])
        chat = next((
            item for item in chats
            if jid == item.get("jid") or jid in (item.get("aliases") or [])
        ), None)
        if chat is None:
            return JsonResponse({"ok": False, "erro": "Conversa não localizada."}, status=404)
        instante = _instante_mensagem_whatsapp(
            (chat.get("lastMessage") or {}).get("timestamp")
        )
        # Evitar que repositórios sem timestamp façam o chat reaparecer sem
        # nova mensagem; o momento da ação passa a ser o corte.
        instante = max(
            [instante, timezone.now()] if instante is not None else [timezone.now()]
        ).isoformat()
        aliases = [
            alias for alias in dict.fromkeys(
                [chat.get("jid"), *(chat.get("aliases") or [])]
            ) if alias
        ][:30]
        with transaction.atomic():
            for alias in aliases:
                ConversaExcluidaWhatsApp.objects.update_or_create(
                    usuario=request.user, sessao=sessao_atual_id(), jid=alias,
                    defaults={"ultima_mensagem_em": instante},
                )
        return JsonResponse({
            "ok": True,
            "jid": chat["jid"],
            "mensagem": (
                "Conversa removida da sua lista. O histórico do WhatsApp "
                "e dos demais operadores foi preservado."
            ),
        })
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_gerenciar_chat_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    acao = (request.POST.get("acao") or "").strip()
    ativo = str(request.POST.get("ativo") or "1").lower() not in {"0", "false", "nao", "não"}

    if not jid or len(jid) > 120:
        return JsonResponse({"ok": False, "erro": "Conversa inválida."}, status=400)
    campos = {"pin": "fixado", "archive": "arquivado", "mute": "silenciado"}
    if acao not in {*campos, "read"}:
        return JsonResponse({"ok": False, "erro": "Ação inválida."}, status=400)
    try:
        resposta = gerenciar_chat(jid, acao, ativo)
        if acao == "read":
            _marcar_como_vista_no_emeca(request.user, jid)
            return JsonResponse({"ok": True, "resposta": resposta, "acao": acao})
        estado, _ = EstadoConversaWhatsApp.objects.get_or_create(
            sessao=sessao_atual_id(), jid=jid
        )
        campo = campos[acao]
        setattr(estado, campo, ativo)
        estado.save(update_fields=[campo, "atualizado_em"])
        return JsonResponse({
            "ok": True, "resposta": resposta, "acao": acao,
            "ativo": ativo, "estado": {
                "fixado": estado.fixado, "silenciado": estado.silenciado,
                "arquivado": estado.arquivado, "bloqueado": estado.bloqueado,
            },
        })
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_enviar_midia_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    legenda = (request.POST.get("legenda") or "").strip()
    arquivo = request.FILES.get("arquivo")

    if not jid or len(jid) > 120:
        return JsonResponse({"ok": False, "erro": "Conversa inválida."}, status=400)
    if not arquivo:
        return JsonResponse({"ok": False, "erro": "Selecione um arquivo."}, status=400)
    if arquivo.size > 25 * 1024 * 1024:
        return JsonResponse(
            {"ok": False, "erro": "O arquivo deve ter no máximo 25 MB."},
            status=400,
        )

    nome = arquivo.name or "arquivo"
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    bloqueadas = {"exe", "msi", "bat", "cmd", "com", "scr", "ps1", "vbs", "js", "jar"}
    if extensao in bloqueadas:
        return JsonResponse(
            {"ok": False, "erro": "Esse tipo de arquivo não é permitido."},
            status=400,
        )

    content_type = (arquivo.content_type or "application/octet-stream").lower()
    if content_type.startswith("image/"):
        tipo = "image"
    elif content_type.startswith("video/"):
        tipo = "video"
    elif content_type.startswith("audio/"):
        tipo = "audio"
    else:
        tipo = "document"

    try:
        resposta = confirmar_operacao_wa(
            enviar_midia(jid, arquivo.read(), nome, content_type, tipo, legenda),
            "envio de arquivo na conversa",
        )
        return JsonResponse({"ok": True, "tipo": tipo, "resposta": resposta})
    except WhatsAppGatewayError as exc:
        return JsonResponse(
            {"ok": False, "erro": str(exc)},
            status=exc.status_code or 502,
        )


@login_required
@require_POST
def whatsapp_responder_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    try:
        dados = request.POST
        jid = (dados.get("jid") or "").strip()
        texto = (dados.get("mensagem") or "").strip()
        if not jid or len(jid) > 120:
            raise ValueError("Conversa inválida.")
        if not texto:
            raise ValueError("Digite uma mensagem.")
        if len(texto) > 4000:
            raise ValueError("A mensagem deve ter no máximo 4.000 caracteres.")

        resposta = confirmar_operacao_wa(
            enviar_mensagem_chat(jid, texto), "mensagem de conversa",
        )
        return JsonResponse({"ok": True, "resposta": resposta})
    except ValueError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=400)
    except WhatsAppGatewayError as exc:
        return JsonResponse(
            {"ok": False, "erro": str(exc)},
            status=exc.status_code or 502,
        )



@login_required
@require_GET
def whatsapp_buscar_mensagens_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    q = (request.GET.get("q") or "").strip()
    jid = (request.GET.get("jid") or "").strip()
    tipo = (request.GET.get("type") or "").strip()
    try:
        page = max(int(request.GET.get("page") or 1), 1)
    except ValueError:
        page = 1

    if not q and not jid:
        return JsonResponse({"ok": False, "erro": "Informe uma busca ou conversa."}, status=400)

    try:
        # Conversas unificadas por LID/telefone podem ter mensagens
        # armazenadas sob mais de um JID. Pesquisar todos os aliases conhecidos.
        aliases = _aliases_contato_wa(jid) if jid else []
        if not aliases:
            aliases = [jid] if jid else [""]
        mensagens_por_id = {}
        paginas = []
        for alias in aliases[:12]:
            payload = buscar_mensagens(q=q, jid=alias, tipo=tipo, page=page, limit=50)
            if isinstance(payload, dict) and payload.get("status") is False:
                raise WhatsAppGatewayError(str(payload.get("message") or "Busca recusada pelo WA-AKG."))
            encontrados = payload.get("data") if isinstance(payload, dict) else []
            if not isinstance(encontrados, list):
                encontrados = []
            for msg in encontrados:
                if isinstance(msg, dict):
                    ident = str(msg.get("keyId") or msg.get("id") or (
                        f'{msg.get("timestamp")}-{msg.get("content")}-{msg.get("fromMe")}'
                    ))
                    mensagens_por_id[ident] = msg
            pagination = payload.get("pagination") if isinstance(payload, dict) else None
            if isinstance(pagination, dict):
                paginas.append(pagination)
        mensagens = sorted(
            mensagens_por_id.values(),
            key=lambda msg: str(msg.get("timestamp") or ""),
        )
        limite = _limite_exclusao_conversa_wa(
            request.user, _aliases_contato_wa(jid)
        ) if jid else None
        if limite is not None:
            mensagens = [
                msg for msg in mensagens
                if (data := _instante_mensagem_whatsapp(msg.get("timestamp")))
                is not None and data > limite
            ]
        ids = [
            str(msg.get("keyId") or msg.get("id") or "")
            for msg in mensagens
        ]
        ocultas = set(
            MensagemOcultaWhatsApp.objects.filter(
                usuario=request.user, sessao=sessao_atual_id(),
                mensagem_id__in=ids
            ).values_list("mensagem_id", flat=True)
        )
        if ocultas:
            mensagens = [
                msg for msg in mensagens
                if str(msg.get("keyId") or msg.get("id") or "") not in ocultas
            ]
        return JsonResponse({
            "ok": True,
            "mensagens": mensagens,
            "pagination": {
                "total": sum(int(p.get("total") or 0) for p in paginas),
                "page": page, "limit": 50,
            },
        })
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_acao_mensagem_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    message_id = (request.POST.get("message_id") or "").strip()
    acao = (request.POST.get("acao") or "").strip()
    texto = (request.POST.get("texto") or "").strip()
    emoji = (request.POST.get("emoji") or "").strip()
    from_me = str(request.POST.get("from_me") or "").lower() in {"1", "true", "sim"}

    if not jid or not message_id or len(jid) > 120 or len(message_id) > 190:
        return JsonResponse({"ok": False, "erro": "Mensagem inválida."}, status=400)

    # Remover da tela do operador não apaga o conteúdo em WA-AKG nem no celular.
    if acao == "hide_local":
        MensagemOcultaWhatsApp.objects.get_or_create(
            usuario=request.user,
            sessao=sessao_atual_id(),
            mensagem_id=message_id
        )
        return JsonResponse({
            "ok": True, "acao": "hide_local",
            "mensagem": "Mensagem ocultada somente para você no EMECA."
        })

    try:
        if acao == "reply":
            if not texto:
                raise ValueError("Digite a resposta.")
            resposta = responder_mensagem_citada(jid, message_id, texto)
        elif acao == "star":
            resposta = favoritar_mensagem(jid, message_id, True, from_me)
        elif acao == "unstar":
            resposta = favoritar_mensagem(jid, message_id, False, from_me)
        elif acao == "react":
            resposta = reagir_mensagem(jid, message_id, emoji)
        elif acao == "edit":
            if not from_me:
                raise ValueError("Somente mensagens enviadas pela escola podem ser editadas.")
            if not texto:
                raise ValueError("Digite o novo texto.")
            resposta = editar_mensagem(jid, message_id, texto)
        elif acao == "delete":
            if not from_me:
                raise ValueError("Somente mensagens enviadas pela escola podem ser apagadas para todos.")
            # Nunca confiar só no from_me enviado pelo navegador: conferir
            # o remetente diretamente no histórico desta sessão WA-AKG.
            mensagem_encontrada = None
            for alias in _aliases_contato_wa(jid)[:12]:
                historico = obter_mensagens_chat(alias)
                dados = historico.get("data") if isinstance(historico, dict) else []
                if isinstance(dados, dict):
                    dados = dados.get("messages") or []
                if not isinstance(dados, list):
                    continue
                mensagem_encontrada = next(
                    (item for item in dados if isinstance(item, dict) and
                     str(item.get("keyId") or item.get("id") or "") == message_id),
                    None
                )
                if mensagem_encontrada is not None:
                    break
            if mensagem_encontrada is None:
                raise ValueError(
                    "Mensagem não localizada no histórico recente do WhatsApp. "
                    "Não é seguro solicitar exclusão para todos."
                )
            if not mensagem_encontrada.get("fromMe"):
                raise ValueError("A mensagem não foi enviada pela escola.")
            resposta = apagar_mensagem(
                str(mensagem_encontrada.get("remoteJid") or jid), message_id
            )
            if not isinstance(resposta, dict) or (
                resposta.get("status") is not True and resposta.get("success") is not True
            ) or resposta.get("status") is False or resposta.get("success") is False:
                raise WhatsAppGatewayError(
                    str((resposta or {}).get("error") or (resposta or {}).get("message")
                        or "WA-AKG não confirmou a solicitação de exclusão.")
                )
            # A revogação pode levar alguns segundos para refletir no MySQL;
            # evitar que reapareça na caixa deste operador durante o intervalo.
            MensagemOcultaWhatsApp.objects.get_or_create(
                usuario=request.user, sessao=sessao_atual_id(),
                mensagem_id=message_id
            )
            return JsonResponse({
                "ok": True, "resposta": resposta, "acao": acao,
                "mensagem": "Exclusão para todos solicitada ao WhatsApp."
            })
        else:
            raise ValueError("Ação de mensagem inválida.")
        return JsonResponse({"ok": True, "resposta": resposta})
    except ValueError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=400)
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_encaminhar_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    from_jid = (request.POST.get("from_jid") or "").strip()
    message_id = (request.POST.get("message_id") or "").strip()
    destinos = [item.strip() for item in request.POST.getlist("to_jids") if item.strip()]
    if not from_jid or not message_id or not destinos:
        return JsonResponse({"ok": False, "erro": "Informe a mensagem e o destino."}, status=400)
    if len(destinos) > 20:
        return JsonResponse({"ok": False, "erro": "Encaminhe para no máximo 20 conversas por vez."}, status=400)
    try:
        resposta = encaminhar_mensagem(from_jid, message_id, destinos)
        return JsonResponse({"ok": True, "resposta": resposta})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_bloqueio_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    bloquear = str(request.POST.get("bloquear") or "1").lower() not in {"0", "false", "nao", "não"}
    if not jid or len(jid) > 120 or jid.endswith("@g.us"):
        return JsonResponse({"ok": False, "erro": "Selecione um contato individual válido."}, status=400)
    try:
        resposta = bloquear_contato(jid, bloquear)
        estado, _ = EstadoConversaWhatsApp.objects.get_or_create(
            sessao=sessao_atual_id(), jid=jid
        )
        estado.bloqueado = bloquear
        estado.save(update_fields=["bloqueado", "atualizado_em"])
        return JsonResponse({
            "ok": True, "resposta": resposta,
            "bloqueado": estado.bloqueado,
        })
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_presenca_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    presence = (request.POST.get("presence") or "").strip()
    if presence not in {"composing", "recording", "paused", "available", "unavailable"}:
        return JsonResponse({"ok": False, "erro": "Presença inválida."}, status=400)
    try:
        resposta = enviar_presenca(jid, presence)
        return JsonResponse({"ok": True, "resposta": resposta})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_GET
def whatsapp_etiquetas_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.GET.get("jid") or "").strip()
    try:
        gerais = listar_etiquetas()
        if not isinstance(gerais, dict) or gerais.get("status") is False:
            raise WhatsAppGatewayError(
                str((gerais or {}).get("message") or "WA-AKG não retornou etiquetas.")
            )
        todas = gerais.get("data", {}).get("labels", []) or []
        atuais = []
        if jid:
            payload = listar_etiquetas_chat(jid)
            if isinstance(payload, dict):
                if payload.get("status") is False:
                    raise WhatsAppGatewayError(str(payload.get("message") or "Erro ao consultar etiquetas da conversa."))
                atuais = payload.get("data", {}).get("labels", []) or payload.get("labels", []) or []
        # Reconciliar a apresentação do EMECA com a lista confirmada pelo WA.
        if jid:
            _sincronizar_etiquetas_wa(jid, atuais)
        return JsonResponse({"ok": True, "etiquetas": todas, "atuais": atuais})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_etiquetas_criar_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    """Permite criar etiquetas dentro da conversa sem sair da caixa de entrada."""
    nome = (request.POST.get("nome") or "").strip()
    try:
        cor = int(request.POST.get("cor") or 0)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "erro": "Cor inválida."}, status=400)
    if not 1 <= len(nome) <= 50 or not 0 <= cor <= 19:
        return JsonResponse({"ok": False, "erro": "Informe nome (até 50 caracteres) e cor válida."}, status=400)
    try:
        jid = (request.POST.get("jid") or "").strip()
        if not jid or len(jid) > 120:
            return JsonResponse({"ok": False, "erro": "Selecione uma conversa."}, status=400)
        resposta = criar_etiqueta(nome, cor)
        etiqueta = (resposta.get("data") or {}).get("label")
        if not isinstance(etiqueta, dict) or not etiqueta.get("id"):
            raise WhatsAppGatewayError("WA-AKG criou etiqueta sem retornar identificador.")
        # Criar etiqueta dentro da conversa deve também aplicá-la imediatamente.
        try:
            atribuicao = atualizar_etiquetas_chat(jid, [str(etiqueta["id"])], "add")
        except WhatsAppGatewayError as exc:
            return JsonResponse({
                "ok": False,
                "erro": "Etiqueta criada, mas não associada à conversa: " + str(exc),
                "etiqueta_criada": True,
            }, status=502)
        etiquetas_atualizadas = atribuicao.get("labels")
        if not isinstance(etiquetas_atualizadas, list):
            raise WhatsAppGatewayError("WA-AKG não confirmou as etiquetas da conversa.")
        visiveis = _sincronizar_etiquetas_wa(jid, etiquetas_atualizadas)
        return JsonResponse({
            "ok": True,
            "etiqueta": etiqueta,
            "etiquetas_conversa": visiveis,
        })
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_etiquetas_atualizar_api(request):
    erro_sessao = _validar_sessao_cliente(request)
    if erro_sessao is not None:
        return erro_sessao
    jid = (request.POST.get("jid") or "").strip()
    action = (request.POST.get("action") or "").strip()
    label_ids = [item.strip() for item in request.POST.getlist("label_ids") if item.strip()]
    if not jid or action not in {"add", "remove"} or not label_ids:
        return JsonResponse({"ok": False, "erro": "Dados de etiqueta inválidos."}, status=400)
    try:
        resposta = atualizar_etiquetas_chat(jid, label_ids, action)
        atuais = resposta.get("labels") if isinstance(resposta, dict) else None
        visiveis = _sincronizar_etiquetas_wa(jid, atuais)
        return JsonResponse({"ok": True, "resposta": resposta, "etiquetas_conversa": visiveis})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)



@login_required
@require_GET
def whatsapp_midia_recebida(request, message_id):
    if _validar_sessao_cliente(request) is not None:
        return HttpResponse(status=409)
    try:
        media_url = (request.GET.get("media") or "").strip()
        if media_url:
            conteudo, content_type, disposition = baixar_midia_por_caminho(media_url)
        else:
            conteudo, content_type, disposition = baixar_midia_mensagem(message_id)
        resposta = HttpResponse(conteudo, content_type=content_type)
        if content_type.startswith(("image/", "video/", "audio/")):
            resposta["Content-Disposition"] = "inline"
        elif disposition:
            resposta["Content-Disposition"] = disposition
        resposta["Cache-Control"] = "private, max-age=300"
        return resposta
    except WhatsAppGatewayError as exc:
        return JsonResponse(
            {"ok": False, "erro": str(exc)},
            status=exc.status_code or 502,
        )



@login_required
def whatsapp_importar_agenda(request):
    """Importa agenda Android sem tocar mensagens, sessões ou dados WA-AKG."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Apenas administradores podem importar a agenda.")
    if request.method == "GET":
        return render(request, "whatsapp_importar_agenda.html", {
            "total_agenda": ContatoAgendaWhatsApp.objects.filter(
                sessao=sessao_atual_id()
            ).count(),
        })
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método não permitido."}, status=405)
    arquivo = request.FILES.get("arquivo")
    if not arquivo or not arquivo.name.lower().endswith(".vcf"):
        return JsonResponse({
            "ok": False, "erro": "Selecione um arquivo de contatos .vcf exportado do Android."
        }, status=400)
    if arquivo.size > MAX_VCF_BYTES:
        return JsonResponse({
            "ok": False, "erro": "O arquivo deve ter no máximo 8 MB."
        }, status=400)
    modo = (request.POST.get("modo") or "previa").strip()
    if modo not in ("previa", "importar"):
        return JsonResponse({"ok": False, "erro": "Operação inválida."}, status=400)
    try:
        resultado = processar_agenda_vcf(
            arquivo.read(),
            sessao=sessao_atual_id(),
            aplicar=(modo == "importar"),
        )
    except AgendaImportError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=400)
    return JsonResponse({
        "ok": True, "modo": modo, "resultado": resultado,
    })


@login_required
def whatsapp_gerenciamento(request):
    if request.method == "POST":
        if _validar_sessao_cliente(request) is not None:
            messages.error(request, "A conta WhatsApp foi trocada. Atualize a página.")
            return redirect("whatsapp_gerenciamento")
        acao = (request.POST.get("acao") or "").strip()
        if acao in {"apagar_etiqueta", "sair_grupo", "remover_grupo"} and not _pode_desconectar_whatsapp(request.user):
            return HttpResponseForbidden("Somente administradores podem excluir etiquetas ou gerenciar a participação em grupos.")
        try:
            if acao == "criar_etiqueta":
                nome = (request.POST.get("nome") or "").strip()
                cor = int(request.POST.get("cor") or 0)
                if not 1 <= len(nome) <= 80 or not 0 <= cor < len(CORES_ETIQUETAS_WA):
                    raise ValueError("Informe o nome da etiqueta e escolha uma cor válida.")
                criar_etiqueta(nome, cor)
                messages.success(request, "Etiqueta criada no WhatsApp.")
            elif acao == "apagar_etiqueta":
                label_id = (request.POST.get("id") or "").strip()
                if not label_id or len(label_id) > 120 or request.POST.get("confirmacao") != "EXCLUIR":
                    raise ValueError("Confirme qual etiqueta deseja excluir.")
                apagar_etiqueta(label_id)
                EtiquetaConversaWhatsApp.objects.filter(
                    sessao=sessao_atual_id(), etiqueta_id=label_id
                ).delete()
                messages.success(request, "Etiqueta excluída e removida das conversas. Mensagens preservadas.")
            elif acao == "criar_auto_resposta":
                palavra = (request.POST.get("palavra") or "").strip()
                resposta = (request.POST.get("resposta") or "").strip()
                match_type = (request.POST.get("match_type") or "EXACT").strip()
                trigger_type = (request.POST.get("trigger_type") or "ALL").strip()
                if not palavra or not resposta:
                    raise ValueError("Informe a palavra-chave e a resposta.")
                criar_resposta_automatica(palavra, resposta, match_type, trigger_type)
                messages.success(request, "Resposta automática criada.")
            elif acao == "apagar_auto_resposta":
                apagar_resposta_automatica((request.POST.get("id") or "").strip())
                messages.success(request, "Resposta automática removida.")
            elif acao == "criar_agendamento":
                numero = re.sub(r"\D", "", request.POST.get("numero") or "")
                jid = _normalizar_jid(numero)
                conteudo = (request.POST.get("conteudo") or "").strip()
                enviar_em = (request.POST.get("enviar_em") or "").strip()
                if not jid or not conteudo or not enviar_em:
                    raise ValueError("Informe número válido, mensagem e data/hora.")
                resposta = criar_agendamento(jid, conteudo, enviar_em)
                if not isinstance(resposta, dict) or (
                    resposta.get("status") is not True and resposta.get("success") is not True
                ) or resposta.get("status") is False or resposta.get("success") is False:
                    raise WhatsAppGatewayError(
                        str((resposta or {}).get("message")
                            or "WA-AKG não confirmou o agendamento.")
                    )
                messages.success(
                    request,
                    "Mensagem agendada e confirmada pelo WA-AKG. "
                    "O envio depende de a conta continuar conectada no horário."
                )
            elif acao == "apagar_agendamento":
                apagar_agendamento((request.POST.get("id") or "").strip())
                messages.success(request, "Agendamento removido.")
            elif acao == "configurar_sistema":
                timezone = (request.POST.get("timezone") or "America/Sao_Paulo").strip()
                salvar_config_sistema(
                    "EMECA WhatsApp",
                    "",
                    "/favicon.ico",
                    timezone,
                    False,
                )
                messages.success(request, "Configuração do WA-AKG atualizada.")
            elif acao == "criar_grupo":
                assunto = (request.POST.get("assunto") or "").strip()
                numeros = [
                    _normalizar_jid(item)
                    for item in re.split(r"[,;\n]+", request.POST.get("participantes") or "")
                ]
                participantes = [item for item in numeros if item]
                if not assunto or not participantes:
                    raise ValueError("Informe o nome do grupo e pelo menos um telefone válido.")
                criado = criar_grupo(assunto, participantes)
                if not isinstance(criado, dict) or (
                    criado.get("status") is not True
                    and criado.get("success") is not True
                ):
                    raise WhatsAppGatewayError(
                        str((criado or {}).get("message") or
                            "O WA-AKG não confirmou a criação do grupo.")
                    )
                dados = criado.get("data") or {}
                jid_novo = (dados.get("group") or {}).get("id") if isinstance(dados, dict) else ""
                if jid_novo:
                    messages.success(
                        request,
                        "Grupo criado no WhatsApp. Abra Mensagens e atualize "
                        "a lista para iniciar o atendimento."
                    )
                else:
                    messages.success(request, "Grupo criado. Aguarde a sincronização.")
            elif acao in {"sair_grupo", "remover_grupo"}:
                jid = (request.POST.get("jid") or "").strip()
                if not re.fullmatch(r"[0-9-]{5,85}@g\.us", jid):
                    raise ValueError("Selecione um grupo WhatsApp válido.")
                confirmacao = "SAIR" if acao == "sair_grupo" else "REMOVER"
                if request.POST.get("confirmacao") != confirmacao:
                    raise ValueError("Confirme a ação antes de continuar.")
                resultado_grupos = listar_grupos()
                if not isinstance(resultado_grupos, dict) or resultado_grupos.get("status") is False:
                    raise WhatsAppGatewayError("Não foi possível verificar os grupos da sessão.")
                grupos_atuais = resultado_grupos.get("data") or []
                if not isinstance(grupos_atuais, list) or not any(
                    isinstance(grupo, dict) and grupo.get("jid") == jid
                    for grupo in grupos_atuais
                ):
                    raise ValueError("Grupo não localizado nesta conta WhatsApp.")
                if acao == "sair_grupo":
                    sair_grupo(jid)
                GrupoOcultoWhatsApp.objects.update_or_create(
                    sessao=sessao_atual_id(), jid=jid,
                    defaults={"motivo": "SAIU" if acao == "sair_grupo" else "REMOVIDO"},
                )
                if acao == "sair_grupo":
                    messages.success(request, "A conta institucional saiu do grupo. O histórico antigo foi preservado.")
                else:
                    messages.success(request, "Grupo removido da lista EMECA. A conta continua participante no WhatsApp.")
            else:
                raise ValueError("Ação inválida.")
        except (ValueError, WhatsAppGatewayError) as exc:
            messages.error(request, str(exc))
        return redirect("whatsapp_gerenciamento")

    dados = {
        "gateway_configurado": gateway_configurado(),
        "gateway_status": "NAO_CONFIGURADO",
        "limpeza_pendente": limpeza_historico_pendente(),
        "wa_sessao_id": sessao_atual_id(),
        "pode_desconectar": _pode_desconectar_whatsapp(request.user),
        "etiquetas": [],
        "cores_etiquetas": CORES_ETIQUETAS_WA,
        "auto_respostas": [],
        "agendamentos": [],
        "historico_agendamentos": [],
        "grupos": [],
        "config_sistema": {},
    }
    if gateway_configurado():
        try:
            sessao = obter_sessao()
            dados["gateway_status"] = str(
                (sessao.get("data") or {}).get("status") or sessao.get("status") or ""
            ).upper()
        except WhatsAppGatewayError:
            dados["gateway_status"] = "INDISPONIVEL"
        try:
            labels = listar_etiquetas()
            dados["etiquetas"] = labels.get("data", {}).get("labels", []) if isinstance(labels, dict) else []
        except WhatsAppGatewayError:
            pass
        try:
            payload = listar_respostas_automaticas()
            dados["auto_respostas"] = payload.get("data", []) if isinstance(payload, dict) else []
        except WhatsAppGatewayError:
            pass
        try:
            payload = listar_agendamentos("pending")
            dados["agendamentos"] = payload.get("data", []) if isinstance(payload, dict) else []
            hist = listar_agendamentos("history")
            dados["historico_agendamentos"] = hist.get("data", []) if isinstance(hist, dict) else []
        except WhatsAppGatewayError:
            pass
        try:
            payload = listar_grupos()
            grupos = payload.get("data", []) if isinstance(payload, dict) else []
            grupos_ocultos = set(
                GrupoOcultoWhatsApp.objects.filter(
                    sessao=sessao_atual_id()
                ).values_list("jid", flat=True)
            )
            dados["grupos"] = [
                grupo for grupo in grupos
                if isinstance(grupo, dict) and grupo.get("jid") not in grupos_ocultos
            ] if isinstance(grupos, list) else []
        except WhatsAppGatewayError:
            pass
        try:
            payload = obter_config_sistema()
            dados["config_sistema"] = payload.get("data", {}) if isinstance(payload, dict) else {}
        except WhatsAppGatewayError:
            pass

    return render(request, "whatsapp_gerenciamento.html", dados)



@login_required
@require_GET
def whatsapp_foto_imagem(request):
    if _validar_sessao_cliente(request) is not None:
        return HttpResponse(status=409)
    jid = (request.GET.get("jid") or "").strip()
    if not jid or len(jid) > 120:
        return HttpResponse(status=404)

    for alias in _aliases_contato_wa(jid):
        try:
            payload = obter_foto_perfil(alias)
            url = payload.get("profilePicUrl") if isinstance(payload, dict) else None
            if not url or not str(url).startswith("https://"):
                continue

            req = Request(
                str(url),
                headers={"User-Agent": "Mozilla/5.0 EMECA-WhatsApp/1.0"},
                method="GET",
            )
            with urlopen(req, timeout=10) as response:
                content_type = response.headers.get("Content-Type") or ""
                if not content_type.startswith("image/"):
                    continue
                tamanho = response.headers.get("Content-Length")
                if tamanho and int(tamanho) > 5 * 1024 * 1024:
                    continue
                conteudo = response.read(5 * 1024 * 1024 + 1)
                if len(conteudo) > 5 * 1024 * 1024:
                    continue
                resposta = HttpResponse(conteudo, content_type=content_type)
                resposta["Cache-Control"] = "private, max-age=900"
                resposta["Content-Security-Policy"] = "default-src 'none'"
                return resposta
        except (WhatsAppGatewayError, HTTPError, URLError, ValueError):
            continue

    return HttpResponse(status=404)
