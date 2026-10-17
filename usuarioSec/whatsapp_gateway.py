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
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("GET", f"chat/{session_id}")


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


def verificar_numeros(numbers):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    return _request("POST", f"chat/{session_id}/check", {"numbers": numbers})


def gerenciar_chat(jid, acao, ativo=True):
    session_id = quote(settings.WA_AKG_SESSION_ID, safe="")
    jid_codificado = quote(jid, safe="")
    if acao == "pin":
        return _request("PUT", f"chat/{session_id}/{jid_codificado}/pin", {"pin": bool(ativo)})
    if acao == "archive":
        return _request("PUT", f"chat/{session_id}/{jid_codificado}/archive", {"archive": bool(ativo)})
    if acao == "mute":
        return _request("PUT", f"chat/{session_id}/{jid_codificado}/mute", {"mute": bool(ativo)})
    if acao == "read":
        return marcar_chat_como_lido(jid)
    raise WhatsAppGatewayError("Ação de conversa inválida.")
