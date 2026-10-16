import re
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from site_publico.boletim_importacao import normalizar_nome
from site_publico.models import BoletimAluno, PeriodoBoletim

from .models import (
    EnvioBoletimWhatsApp,
    ItemEnvioBoletimWhatsApp,
    TelefoneDeclaracao,
    declaracao,
)
from .whatsapp_gateway import (
    WhatsAppGatewayError,
    configurado as gateway_configurado,
    enviar_broadcast,
    iniciar_sessao,
    obter_qr,
    obter_sessao,
)


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


def _queryset_contatos(modo, turma="", contato_id=None, tipos=None):
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
    elif modo == "individual":
        pass
    elif modo != "todos":
        raise ValueError("Tipo de envio inválido.")

    return queryset.order_by("declaracao__nomeDoAluno", "tipo", "id")


def _resolver_destinatarios(modo, turma="", contato_id=None, tipos=None):
    queryset = _queryset_contatos(
        modo,
        turma=turma,
        contato_id=contato_id,
        tipos=tipos,
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
):
    tipo, numero, ano = _validar_periodo(tipo, numero, ano)
    contatos = _queryset_contatos(
        modo,
        turma=turma,
        contato_id=contato_id,
        tipos=tipos,
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

    por_nome = defaultdict(list)
    for boletim in boletins:
        por_nome[normalizar_nome(boletim.aluno.nome)].append(boletim)

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
        candidatos = por_nome.get(normalizar_nome(declaracao_aluno.nomeDoAluno), [])

        if len(candidatos) > 1 and declaracao_aluno.turmaDoAluno:
            turma_normalizada = normalizar_nome(declaracao_aluno.turmaDoAluno)
            por_turma = [
                item
                for item in candidatos
                if normalizar_nome(item.periodo.turma) == turma_normalizada
            ]
            if por_turma:
                candidatos = por_turma

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
    }


@login_required
def whatsapp(request):
    turmas = list(
        declaracao.objects.exclude(turmaDoAluno__isnull=True)
        .exclude(turmaDoAluno__exact="")
        .order_by("turmaDoAluno")
        .values_list("turmaDoAluno", flat=True)
        .distinct()
    )

    anos_boletim = list(
        PeriodoBoletim.objects
        .filter(publicado=True, boletins__isnull=False)
        .order_by("-ano")
        .values_list("ano", flat=True)
        .distinct()
    )

    status = "NAO_CONFIGURADO"
    status_detalhe = ""
    if gateway_configurado():
        try:
            resposta = obter_sessao()
            status = str(
                resposta.get("data", {}).get("status") or "DESCONHECIDO"
            ).upper()
        except WhatsAppGatewayError as exc:
            if exc.status_code == 404:
                status = "NAO_CRIADA"
            else:
                status = "INDISPONIVEL"
                status_detalhe = str(exc)

    return render(
        request,
        "whatsapp.html",
        {
            "turmas": turmas,
            "anos_boletim": anos_boletim,
            "envios_boletim": EnvioBoletimWhatsApp.objects.select_related("usuario")[:8],
            "gateway_configurado": gateway_configurado(),
            "gateway_status": status,
            "gateway_status_detalhe": status_detalhe,
            "delay_segundos": round(
                settings.WA_AKG_BROADCAST_DELAY_MS / 1000,
                1,
            ),
        },
    )


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
def whatsapp_destinatarios(request):
    try:
        destinatarios, invalidos, amostra = _resolver_destinatarios(
            request.GET.get("modo") or "todos",
            turma=request.GET.get("turma") or "",
            contato_id=request.GET.get("contato_id") or None,
            tipos=_tipos_selecionados(request),
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
    if not gateway_configurado():
        messages.error(
            request,
            "Configure o WA-AKG no arquivo .env antes de conectar.",
        )
        return redirect("whatsapp")

    try:
        iniciar_sessao()
        messages.success(
            request,
            "Sessão do WhatsApp iniciada. Use o botão “Exibir QR” para vincular o aparelho.",
        )
    except WhatsAppGatewayError as exc:
        messages.error(request, f"Não foi possível iniciar o WhatsApp: {exc}")
    return redirect("whatsapp")


@login_required
@require_GET
def whatsapp_qr(request):
    try:
        dados = obter_qr()
        return JsonResponse({"ok": True, "base64": dados.get("base64")})
    except WhatsAppGatewayError as exc:
        if exc.payload.get("connected"):
            return JsonResponse({"ok": True, "connected": True})
        return JsonResponse(
            {"ok": False, "erro": str(exc)},
            status=exc.status_code or 502,
        )


def _enfileirar_boletins(request):
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

    with transaction.atomic():
        envio = EnvioBoletimWhatsApp.objects.create(
            usuario=request.user,
            tipo_periodo=dados["tipo"],
            numero_periodo=dados["numero"],
            ano=dados["ano"],
            modo=request.POST.get("modo") or "todos",
            turma=(request.POST.get("turma") or "").strip(),
            mensagem=mensagem_pdf,
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


@login_required
@require_POST
def whatsapp_enviar(request):
    if (request.POST.get("conteudo") or "mensagem") == "boletim":
        return _enfileirar_boletins(request)

    mensagem = (request.POST.get("mensagem") or "").strip()
    if not mensagem:
        messages.error(request, "Digite a mensagem antes de enviar.")
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
        resposta = enviar_broadcast(destinatarios, mensagem)
    except WhatsAppGatewayError as exc:
        messages.error(request, f"Falha ao iniciar o envio: {exc}")
        return redirect("whatsapp")

    broadcast_id = resposta.get("data", {}).get("broadcastId")
    complemento = f" Lote #{broadcast_id}." if broadcast_id else ""
    aviso_invalidos = (
        f" {invalidos} telefone(s) inválido(s) foram ignorados."
        if invalidos
        else ""
    )
    messages.success(
        request,
        (
            f"Envio iniciado para {len(destinatarios)} contato(s)."
            f"{complemento}{aviso_invalidos}"
        ),
    )
    return redirect("whatsapp")
