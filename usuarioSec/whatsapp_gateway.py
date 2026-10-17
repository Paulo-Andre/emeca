import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings


class WhatsAppGatewayError(RuntimeError):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def configurado():
    return bool(
        getattr(settings, "WA_AKG_BASE_URL", "")
        and getattr(settings, "WA_AKG_API_KEY", "")
        and getattr(settings, "WA_AKG_SESSION_ID", "")
    )


def _request(method, path, payload=None):
    if not configurado():
        raise WhatsAppGatewayError(
            "A integração com o WhatsApp ainda não foi configurada no servidor."
        )

    base_url = settings.WA_AKG_BASE_URL.rstrip("/")
    url = f"{base_url}/{path.lstrip('/')}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "X-API-Key": settings.WA_AKG_API_KEY,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    request = Request(url, data=body, headers=headers, method=method.upper())

    try:
        with urlopen(request, timeout=settings.WA_AKG_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        message = (
            data.get("message")
            or data.get("error")
            or f"WA-AKG respondeu com HTTP {exc.code}."
        )
        raise WhatsAppGatewayError(str(message), exc.code, data) from exc
    except URLError as exc:
        raise WhatsAppGatewayError(
            "Não foi possível conectar ao serviço WA-AKG."
        ) from exc


def obter_sessao():
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("GET", f"sessions/{session_id}")


def preparar_sessao():
    try:
        return obter_sessao()
    except WhatsAppGatewayError as exc:
        if exc.status_code != 404:
            raise

    criada = _request(
        "POST",
        "sessions",
        {
            "name": "EMECA Secretaria",
            "sessionId": settings.WA_AKG_SESSION_ID,
        },
    )
    return criada


def iniciar_sessao():
    preparar_sessao()
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("POST", f"sessions/{session_id}/start", {})


def pausar_sessao():
    """Pausa o socket do WA-AKG sem apagar credenciais ou mensagens."""
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("POST", f"sessions/{session_id}/stop", {})


def desvincular_sessao():
    """Faz logout do aparelho: revoga o vínculo, mas não apaga mensagens."""
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("POST", f"sessions/{session_id}/logout", {})


def obter_qr():
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("GET", f"sessions/{session_id}/qr")


def enviar_broadcast(recipients, message):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request(
        "POST",
        f"messages/{session_id}/broadcast",
        {
            "recipients": recipients,
            "message": message,
            "delay": settings.WA_AKG_BROADCAST_DELAY_MS,
        },
    )


def _request_multipart(path, fields, filename, content_type, content):
    if not configurado():
        raise WhatsAppGatewayError(
            "A integração com o WhatsApp ainda não foi configurada no servidor."
        )

    boundary = f"----emeca-{uuid.uuid4().hex}"
    chunks = []

    for nome, valor in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{nome}"\r\n\r\n'.encode("utf-8"),
                str(valor).encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    base_url = settings.WA_AKG_BASE_URL.rstrip("/")
    url = f"{base_url}/{path.lstrip('/')}"
    request = Request(
        url,
        data=b"".join(chunks),
        headers={
            "Accept": "application/json",
            "X-API-Key": settings.WA_AKG_API_KEY,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=max(settings.WA_AKG_TIMEOUT_SECONDS, 30)) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        message = (
            data.get("message")
            or data.get("error")
            or f"WA-AKG respondeu com HTTP {exc.code}."
        )
        raise WhatsAppGatewayError(str(message), exc.code, data) from exc
    except URLError as exc:
        raise WhatsAppGatewayError(
            "Não foi possível conectar ao serviço WA-AKG."
        ) from exc


def enviar_midia(jid, conteudo, nome_arquivo, content_type, tipo, legenda=""):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request_multipart(
        f"messages/{session_id}/{jid_codificado}/media",
        {
            "type": tipo,
            "caption": legenda,
        },
        nome_arquivo,
        content_type or "application/octet-stream",
        conteudo,
    )


def enviar_documento(jid, conteudo_pdf, nome_arquivo, legenda=""):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request_multipart(
        f"messages/{session_id}/{jid_codificado}/media",
        {
            "type": "document",
            "caption": legenda,
        },
        nome_arquivo,
        "application/pdf",
        conteudo_pdf,
    )


def listar_chats():
    """Recebe todas as páginas disponíveis, com proteção contra cursores repetidos.

    O WA-AKG antigo só fornecia 50 conversas. A versão corrigida aceita
    ?limit=500&before=... e retorna meta.nextBefore.
    """
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    por_jid = {}
    cursors = set()
    cursor = ""
    for _ in range(25):
        url = f"chat/{session_id}?limit=500"
        if cursor:
            url += "&before=" + quote(cursor, safe="")
        resposta = _request("GET", url)
        if not isinstance(resposta, dict) or resposta.get("status") is False:
            return resposta
        pagina = resposta.get("data")
        if not isinstance(pagina, list):
            return resposta
        for chat in pagina:
            if not isinstance(chat, dict) or not chat.get("jid"):
                continue
            jid = str(chat["jid"])
            anterior = por_jid.get(jid)
            if anterior is None or str(
                (chat.get("lastMessage") or {}).get("timestamp") or ""
            ) > str((anterior.get("lastMessage") or {}).get("timestamp") or ""):
                por_jid[jid] = chat
        meta = resposta.get("meta") or {}
        proximo = meta.get("nextBefore") if isinstance(meta, dict) else None
        if not pagina or not proximo or proximo in cursors:
            break
        cursors.add(proximo)
        cursor = proximo
    chats = sorted(
        por_jid.values(),
        key=lambda chat: str((chat.get("lastMessage") or {}).get("timestamp") or ""),
        reverse=True,
    )
    return {"status": True, "data": chats}


def obter_mensagens_chat(jid):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request("GET", f"chat/{session_id}/{jid_codificado}")


def enviar_mensagem_chat(jid, texto):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request(
        "POST",
        f"messages/{session_id}/{jid_codificado}/send",
        {"message": {"text": texto}},
    )


def marcar_chat_como_lido(jid):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request(
        "PUT",
        f"chat/{session_id}/{jid_codificado}/read",
        {},
    )


def status_sessao():
    resposta = obter_sessao()
    dados = resposta.get("data") if isinstance(resposta, dict) else None
    if isinstance(dados, dict):
        bruto = dados.get("status")
    else:
        bruto = resposta.get("status") if isinstance(resposta, dict) else ""
    return str(bruto or "").upper()


def listar_contatos():
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("GET", f"contacts/{session_id}?limit=all")


def obter_foto_perfil(jid):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request(
        "POST",
        f"chat/{session_id}/{jid_codificado}/profile-picture",
        {},
    )


def obter_perfil_contato(jid):
    """Dados de perfil que o WhatsApp autoriza a sessão WA-AKG a consultar."""
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request("GET", f"chat/{session_id}/{jid_codificado}/contact-profile")


def verificar_numeros(numbers):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("POST", f"chat/{session_id}/check", {"numbers": numbers})


def confirmar_operacao_wa(resposta, descricao="ação"):
    """Aceita os dois contratos existentes do WA-AKG, mas rejeita falhas.

    O WA-AKG mistura {status: true} e {success: true}; antes, HTTP 200
    com status:false podia ser tratado como sucesso na interface.
    """
    if not isinstance(resposta, dict):
        raise WhatsAppGatewayError(f"Resposta inválida ao executar {descricao}.")
    if resposta.get("status") is False or resposta.get("success") is False:
        raise WhatsAppGatewayError(
            str(resposta.get("error") or resposta.get("message")
                or f"O WA-AKG não conseguiu executar {descricao}.")
        )
    if resposta.get("status") is not True and resposta.get("success") is not True:
        raise WhatsAppGatewayError(f"O WA-AKG não confirmou {descricao}.")
    return resposta


def gerenciar_chat(jid, acao, ativo=True):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    if acao == "pin":
        resposta = _request("PUT", f"chat/{session_id}/{jid_codificado}/pin", {"pin": bool(ativo)})
    elif acao == "archive":
        resposta = _request("PUT", f"chat/{session_id}/{jid_codificado}/archive", {"archive": bool(ativo)})
    elif acao == "mute":
        resposta = _request("PUT", f"chat/{session_id}/{jid_codificado}/mute", {"mute": bool(ativo)})
    elif acao == "read":
        resposta = marcar_chat_como_lido(jid)
    else:
        raise WhatsAppGatewayError("Ação de conversa inválida.")
    return confirmar_operacao_wa(resposta, f"{acao} da conversa")


def buscar_mensagens(q="", jid="", tipo="", page=1, limit=50):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    params = []
    if q:
        params.append(f"q={quote(str(q), safe='')}")
    if jid:
        params.append(f"jid={quote(str(jid), safe='')}")
    if tipo:
        params.append(f"type={quote(str(tipo), safe='')}")
    params.append(f"page={int(page)}")
    params.append(f"limit={min(max(int(limit), 1), 100)}")
    return _request("GET", f"messages/{session_id}/search?{'&'.join(params)}")


def responder_mensagem_citada(jid, message_id, texto):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    message_id_codificado = quote(message_id, safe="")
    return _request(
        "POST",
        f"messages/{session_id}/{jid_codificado}/{message_id_codificado}/reply",
        {"message": {"text": texto}},
    )


def favoritar_mensagem(jid, message_id, star=True, from_me=False):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    message_id_codificado = quote(message_id, safe="")
    return _request(
        "POST",
        f"messages/{session_id}/{jid_codificado}/{message_id_codificado}/star",
        {"star": bool(star), "fromMe": bool(from_me)},
    )


def reagir_mensagem(jid, message_id, emoji):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    message_id_codificado = quote(message_id, safe="")
    return _request(
        "POST",
        f"messages/{session_id}/{jid_codificado}/{message_id_codificado}/react",
        {"emoji": emoji},
    )


def editar_mensagem(jid, message_id, texto):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    message_id_codificado = quote(message_id, safe="")
    return _request(
        "PATCH",
        f"messages/{session_id}/{jid_codificado}/{message_id_codificado}",
        {"text": texto},
    )


def apagar_mensagem(jid, message_id):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    message_id_codificado = quote(message_id, safe="")
    return _request(
        "DELETE",
        f"messages/{session_id}/{jid_codificado}/{message_id_codificado}",
    )


def encaminhar_mensagem(from_jid, message_id, to_jids):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request(
        "POST",
        f"messages/{session_id}/forward",
        {
            "fromJid": from_jid,
            "messageId": message_id,
            "toJids": to_jids,
        },
    )


def bloquear_contato(jid, bloquear=True):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    acao = "block" if bloquear else "unblock"
    resposta = _request(
        "POST",
        f"contacts/{session_id}/{jid_codificado}/{acao}",
        {},
    )
    return confirmar_operacao_wa(resposta, "bloqueio do contato")


def enviar_presenca(jid, presence):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request(
        "POST",
        f"chat/{session_id}/{jid_codificado}/presence",
        {"presence": presence},
    )


def listar_etiquetas():
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("GET", f"labels/{session_id}")


def listar_etiquetas_chat(jid):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    return _request("GET", f"labels/{session_id}/chat/{jid_codificado}/labels")


def atualizar_etiquetas_chat(jid, label_ids, action):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    resposta = _request(
        "PUT",
        f"labels/{session_id}/chat/{jid_codificado}/labels",
        {"labelIds": label_ids, "action": action},
    )
    return confirmar_operacao_wa(resposta, "atualização de etiquetas")



def baixar_midia_mensagem(message_id):
    if not configurado():
        raise WhatsAppGatewayError(
            "A integração com o WhatsApp ainda não foi configurada no servidor."
        )

    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    message_id_codificado = quote(message_id, safe="")
    base_url = settings.WA_AKG_BASE_URL.rstrip("/")
    url = f"{base_url}/messages/{session_id}/download/{message_id_codificado}/media"
    request = Request(
        url,
        headers={
            "Accept": "*/*",
            "X-API-Key": settings.WA_AKG_API_KEY,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=max(settings.WA_AKG_TIMEOUT_SECONDS, 30)) as response:
            return (
                response.read(),
                response.headers.get("Content-Type") or "application/octet-stream",
                response.headers.get("Content-Disposition") or "",
            )
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        raise WhatsAppGatewayError(
            str(data.get("message") or data.get("error") or f"HTTP {exc.code}"),
            exc.code,
            data,
        ) from exc
    except URLError as exc:
        raise WhatsAppGatewayError(
            "Não foi possível baixar a mídia do WA-AKG."
        ) from exc


def listar_grupos():
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("GET", f"groups/{session_id}")


def criar_grupo(subject, participants):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request(
        "POST",
        f"groups/{session_id}/create",
        {"subject": subject, "participants": participants},
    )


def criar_etiqueta(name, color=0):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request(
        "POST",
        f"labels/{session_id}",
        {"name": name, "color": int(color)},
    )


def listar_respostas_automaticas():
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("GET", f"autoreplies/{session_id}")


def criar_resposta_automatica(keyword, response, match_type="EXACT", trigger_type="ALL"):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request(
        "POST",
        f"autoreplies/{session_id}",
        {
            "keyword": keyword,
            "response": response,
            "matchType": match_type,
            "triggerType": trigger_type,
            "isMedia": False,
        },
    )


def apagar_resposta_automatica(reply_id):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    reply_id = quote(reply_id, safe="")
    return _request("DELETE", f"autoreplies/{session_id}/{reply_id}")


def listar_agendamentos(tab="pending"):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("GET", f"scheduler/{session_id}?tab={quote(tab, safe='')}")


def criar_agendamento(jid, content, send_at):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request(
        "POST",
        f"scheduler/{session_id}",
        {
            "jid": jid,
            "content": content,
            "sendAt": send_at,
        },
    )


def apagar_agendamento(schedule_id):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    schedule_id = quote(schedule_id, safe="")
    return _request("DELETE", f"scheduler/{session_id}/{schedule_id}")


def obter_config_sistema():
    return _request("GET", "settings/system")


def salvar_config_sistema(app_name, logo_url, favicon_url, timezone, enable_registration=False):
    return _request(
        "POST",
        "settings/system",
        {
            "appName": app_name,
            "logoUrl": logo_url,
            "faviconUrl": favicon_url,
            "timezone": timezone,
            "enableRegistration": bool(enable_registration),
        },
    )


def baixar_midia_por_caminho(media_url):
    """Baixa mídia privada usando a rota /api/media/{filename} do WA-AKG."""
    media_url = str(media_url or "").strip()
    prefixos = ("/api/media/", "api/media/", "/media/", "media/")
    prefixo = next((item for item in prefixos if media_url.startswith(item)), None)
    if not prefixo:
        raise WhatsAppGatewayError("Caminho de mídia inválido.", 400)

    filename = media_url[len(prefixo):].strip("/")
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise WhatsAppGatewayError("Nome de mídia inválido.", 400)

    base_url = settings.WA_AKG_BASE_URL.rstrip("/")
    # WA_AKG_BASE_URL termina em /api. A rota de mídia também vive sob /api.
    url = f"{base_url}/media/{quote(filename, safe='')}"
    request = Request(
        url,
        headers={
            "Accept": "*/*",
            "X-API-Key": settings.WA_AKG_API_KEY,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=max(settings.WA_AKG_TIMEOUT_SECONDS, 30)) as response:
            return (
                response.read(),
                response.headers.get("Content-Type") or "application/octet-stream",
                response.headers.get("Content-Disposition") or "",
            )
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        raise WhatsAppGatewayError(
            str(data.get("message") or data.get("error") or f"HTTP {exc.code}"),
            exc.code,
            data,
        ) from exc
    except URLError as exc:
        raise WhatsAppGatewayError("Não foi possível baixar a mídia do WA-AKG.") from exc
