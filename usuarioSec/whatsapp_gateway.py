import json
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
