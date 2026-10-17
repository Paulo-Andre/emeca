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
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from site_publico.boletim_importacao import normalizar_nome
from site_publico.models import BoletimAluno, PeriodoBoletim

from .models import (
    EnvioBoletimWhatsApp,
    ItemEnvioBoletimWhatsApp,
    IdentidadeContatoWhatsApp,
    LeituraChatWhatsApp,
    TelefoneDeclaracao,
    declaracao,
)
from .whatsapp_gateway import (
    WhatsAppGatewayError,
    apagar_agendamento,
    apagar_mensagem,
    apagar_resposta_automatica,
    baixar_midia_mensagem,
    baixar_midia_por_caminho,
    atualizar_etiquetas_chat,
    bloquear_contato,
    buscar_mensagens,
    configurado as gateway_configurado,
    criar_agendamento,
    criar_etiqueta,
    criar_grupo,
    criar_resposta_automatica,
    editar_mensagem,
    encaminhar_mensagem,
    enviar_broadcast,
    enviar_mensagem_chat,
    enviar_midia,
    enviar_presenca,
    favoritar_mensagem,
    gerenciar_chat,
    iniciar_sessao,
    listar_agendamentos,
    listar_chats,
    listar_contatos,
    listar_etiquetas,
    listar_grupos,
    listar_respostas_automaticas,
    listar_etiquetas_chat,
    marcar_chat_como_lido,
    obter_config_sistema,
    obter_foto_perfil,
    obter_mensagens_chat,
    obter_qr,
    obter_sessao,
    reagir_mensagem,
    responder_mensagem_citada,
    salvar_config_sistema,
    verificar_numeros,
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
def whatsapp_buscar_contatos_wa(request):
    termo = (request.GET.get("q") or "").strip()
    if len(termo) < 2:
        return JsonResponse({"results": []})

    try:
        payload = listar_contatos()
        contatos = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(contatos, list):
            contatos = []
    except WhatsAppGatewayError as exc:
        return JsonResponse({"results": [], "erro": str(exc)}, status=exc.status_code or 502)

    termo_norm = termo.casefold()
    termo_digitos = re.sub(r"\D", "", termo)
    results = []
    vistos = set()

    for contato in contatos:
        if not isinstance(contato, dict):
            continue
        jid = str(contato.get("jid") or "")
        lid = str(contato.get("lid") or "")
        alt = str(contato.get("remoteJidAlt") or "")
        nome = (
            contato.get("name")
            or contato.get("verifiedName")
            or contato.get("notify")
            or ""
        )
        phone_jid = next(
            (
                item for item in (alt, jid)
                if _jid_eh_telefone(item)
            ),
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
            "nome": nome or "Contato WhatsApp",
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
        if len(destinatarios) == 1:
            jid = destinatarios[0]
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
            resposta = enviar_mensagem_chat(jid_real, mensagem)
            broadcast_id = None
        else:
            resposta = enviar_broadcast(destinatarios, mensagem)
            broadcast_id = resposta.get("data", {}).get("broadcastId")
    except WhatsAppGatewayError as exc:
        messages.error(request, f"Falha ao enviar a mensagem: {exc}")
        return redirect("whatsapp")

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
        IdentidadeContatoWhatsApp.objects.filter(sessao=settings.WA_AKG_SESSION_ID)
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


def _nome_local_por_telefone(phone_jid):
    """Usa a base da escola como fallback quando o WA-AKG não possui nome."""
    digitos = re.sub(r"\D", "", str(phone_jid or "").split("@")[0])
    if not digitos:
        return ""

    candidatos = {digitos}
    if digitos.startswith("55"):
        candidatos.add(digitos[2:])

    telefones = TelefoneDeclaracao.objects.select_related("declaracao").all()
    for registro in telefones:
        salvo = re.sub(r"\D", "", registro.telefone or "")
        salvo_sem_55 = salvo[2:] if salvo.startswith("55") else salvo
        if salvo not in candidatos and salvo_sem_55 not in candidatos:
            continue

        dec = registro.declaracao
        if registro.tipo == "PAI":
            return dec.nomePai or f"Pai de {dec.nomeDoAluno}"
        if registro.tipo == "MAE":
            return dec.nomeMae or f"Mãe de {dec.nomeDoAluno}"
        if registro.tipo == "RESPONSAVEL":
            return dec.nomeResponsavel or f"Responsável por {dec.nomeDoAluno}"
        return dec.nomeDoAluno or ""

    return ""


def _enriquecer_chats(chats):
    """Consolida LID/telefone com ligações explícitas e preserva o histórico."""
    chats = [dict(item) for item in (chats or []) if isinstance(item, dict) and item.get("jid")]
    if not chats:
        return []

    identidades = _identidades_wa()
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
        chave_cache = "emeca:whatsapp:lid:" + sha256(jid.encode("utf-8")).hexdigest()
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
                    sessao=settings.WA_AKG_SESSION_ID,
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
                    sessao=settings.WA_AKG_SESSION_ID,
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
            nome = _nome_local_por_telefone(phone_jid)
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
        merged["name"] = nome_manual or nome or (nome_remoto if not phone_jid else "")
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

    resultado.sort(
        key=lambda item: str((item.get("lastMessage") or {}).get("timestamp") or ""),
        reverse=True,
    )
    return resultado


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
        for estado in LeituraChatWhatsApp.objects.filter(usuario=usuario, jid__in=jids)
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
        usuario=usuario, jid=jid,
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
            sessao=settings.WA_AKG_SESSION_ID, jid=jid
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
                sessao=settings.WA_AKG_SESSION_ID,
                jid=jid,
                defaults={
                    "telefone_jid": telefone,
                    "nome_exibicao": nome,
                    "origem": "MANUAL",
                },
            )
        else:
            IdentidadeContatoWhatsApp.objects.filter(
                sessao=settings.WA_AKG_SESSION_ID, jid=jid, origem="MANUAL"
            ).delete()
    if jid.endswith("@lid"):
        cache.delete("emeca:whatsapp:lid:" + sha256(jid.encode("utf-8")).hexdigest())
    return JsonResponse({"ok": True, "jid": jid, "nome": nome, "telefone_jid": telefone})


@login_required
def whatsapp_mensagens(request):
    status = "NAO_CONFIGURADO"
    status_detalhe = ""
    chats = []

    if gateway_configurado():
        try:
            resposta = obter_sessao()
            status = str(
                resposta.get("data", {}).get("status")
                or resposta.get("status")
                or "DESCONHECIDO"
            ).upper()
            if status == "CONNECTED":
                payload = listar_chats()
                chats = payload.get("data") if isinstance(payload, dict) else []
                if not isinstance(chats, list):
                    chats = []
                chats = _sincronizar_nao_lidas(request.user, _enriquecer_chats(chats))
        except WhatsAppGatewayError as exc:
            status = "INDISPONIVEL"
            status_detalhe = str(exc)

    return render(
        request,
        "whatsapp_mensagens.html",
        {
            "gateway_configurado": gateway_configurado(),
            "gateway_status": status,
            "gateway_status_detalhe": status_detalhe,
            "chats_iniciais": chats[:50],
        },
    )


@login_required
@require_GET
def whatsapp_chats_api(request):
    if not gateway_configurado():
        return JsonResponse(
            {"ok": False, "erro": "Integração ainda não configurada."},
            status=503,
        )
    try:
        payload = listar_chats()
        chats = payload.get("data") if isinstance(payload, dict) else []
        chats = _sincronizar_nao_lidas(
            request.user,
            _enriquecer_chats(chats if isinstance(chats, list) else []),
        )
        return JsonResponse({
            "ok": True,
            "chats": chats,
            "totalNaoLidas": sum(chat.get("naoLidas", 0) for chat in chats),
        })
    except WhatsAppGatewayError as exc:
        return JsonResponse(
            {"ok": False, "erro": str(exc)},
            status=exc.status_code or 502,
        )


@login_required
@require_GET
def whatsapp_chat_api(request):
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
@require_POST
def whatsapp_foto_api(request):
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
    if not mensagem:
        return JsonResponse({"ok": False, "erro": "Digite uma mensagem."}, status=400)

    try:
        resposta = enviar_mensagem_chat(jid, mensagem)
        return JsonResponse({"ok": True, "jid": jid, "resposta": resposta})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_gerenciar_chat_api(request):
    jid = (request.POST.get("jid") or "").strip()
    acao = (request.POST.get("acao") or "").strip()
    ativo = str(request.POST.get("ativo") or "1").lower() not in {"0", "false", "nao", "não"}

    if not jid:
        return JsonResponse({"ok": False, "erro": "Conversa inválida."}, status=400)
    if acao not in {"pin", "archive", "mute", "read"}:
        return JsonResponse({"ok": False, "erro": "Ação inválida."}, status=400)

    try:
        resposta = gerenciar_chat(jid, acao, ativo)
        if acao == "read":
            _marcar_como_vista_no_emeca(request.user, jid)
        return JsonResponse({"ok": True, "resposta": resposta})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_enviar_midia_api(request):
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
        resposta = enviar_midia(
            jid,
            arquivo.read(),
            nome,
            content_type,
            tipo,
            legenda,
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

        resposta = enviar_mensagem_chat(jid, texto)
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
        payload = buscar_mensagens(q=q, jid=jid, tipo=tipo, page=page, limit=50)
        return JsonResponse({
            "ok": True,
            "mensagens": payload.get("data", []) if isinstance(payload, dict) else [],
            "pagination": payload.get("pagination", {}) if isinstance(payload, dict) else {},
        })
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_acao_mensagem_api(request):
    jid = (request.POST.get("jid") or "").strip()
    message_id = (request.POST.get("message_id") or "").strip()
    acao = (request.POST.get("acao") or "").strip()
    texto = (request.POST.get("texto") or "").strip()
    emoji = (request.POST.get("emoji") or "").strip()
    from_me = str(request.POST.get("from_me") or "").lower() in {"1", "true", "sim"}

    if not jid or not message_id:
        return JsonResponse({"ok": False, "erro": "Mensagem inválida."}, status=400)

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
                raise ValueError("Somente mensagens enviadas pela escola podem ser apagadas.")
            resposta = apagar_mensagem(jid, message_id)
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
    jid = (request.POST.get("jid") or "").strip()
    bloquear = str(request.POST.get("bloquear") or "1").lower() not in {"0", "false", "nao", "não"}
    if not jid:
        return JsonResponse({"ok": False, "erro": "Contato inválido."}, status=400)
    try:
        resposta = bloquear_contato(jid, bloquear)
        return JsonResponse({"ok": True, "resposta": resposta})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_presenca_api(request):
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
    jid = (request.GET.get("jid") or "").strip()
    try:
        gerais = listar_etiquetas()
        todas = gerais.get("data", {}).get("labels", []) if isinstance(gerais, dict) else []
        atuais = []
        if jid:
            payload = listar_etiquetas_chat(jid)
            if isinstance(payload, dict):
                atuais = payload.get("data", {}).get("labels", []) or payload.get("labels", []) or []
        return JsonResponse({"ok": True, "etiquetas": todas, "atuais": atuais})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)


@login_required
@require_POST
def whatsapp_etiquetas_atualizar_api(request):
    jid = (request.POST.get("jid") or "").strip()
    action = (request.POST.get("action") or "").strip()
    label_ids = [item.strip() for item in request.POST.getlist("label_ids") if item.strip()]
    if not jid or action not in {"add", "remove"} or not label_ids:
        return JsonResponse({"ok": False, "erro": "Dados de etiqueta inválidos."}, status=400)
    try:
        resposta = atualizar_etiquetas_chat(jid, label_ids, action)
        return JsonResponse({"ok": True, "resposta": resposta})
    except WhatsAppGatewayError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=exc.status_code or 502)



@login_required
@require_GET
def whatsapp_midia_recebida(request, message_id):
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
def whatsapp_gerenciamento(request):
    if request.method == "POST":
        acao = (request.POST.get("acao") or "").strip()
        try:
            if acao == "criar_etiqueta":
                nome = (request.POST.get("nome") or "").strip()
                cor = int(request.POST.get("cor") or 0)
                if not nome:
                    raise ValueError("Informe o nome da etiqueta.")
                criar_etiqueta(nome, cor)
                messages.success(request, "Etiqueta criada no WhatsApp.")
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
                criar_agendamento(jid, conteudo, enviar_em)
                messages.success(request, "Mensagem agendada.")
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
                criar_grupo(assunto, participantes)
                messages.success(request, "Grupo criado.")
            else:
                raise ValueError("Ação inválida.")
        except (ValueError, WhatsAppGatewayError) as exc:
            messages.error(request, str(exc))
        return redirect("whatsapp_gerenciamento")

    dados = {
        "gateway_configurado": gateway_configurado(),
        "etiquetas": [],
        "auto_respostas": [],
        "agendamentos": [],
        "historico_agendamentos": [],
        "grupos": [],
        "config_sistema": {},
    }
    if gateway_configurado():
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
            dados["grupos"] = payload.get("data", []) if isinstance(payload, dict) else []
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
