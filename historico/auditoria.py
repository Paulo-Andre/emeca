import hashlib
import json
import uuid

from django.conf import settings

from .models import AuditoriaEvento


SENSITIVE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _ip_cliente(request):
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def hash_ip(ip):
    if not ip:
        return ""
    segredo = str(settings.SECRET_KEY).encode("utf-8")
    return hashlib.sha256(segredo + b":" + ip.encode("utf-8")).hexdigest()


def request_id(request):
    valor = getattr(request, "audit_request_id", None)
    if valor:
        return valor
    valor = uuid.uuid4()
    request.audit_request_id = valor
    return valor


def detalhes_seguros(detalhes):
    if not detalhes:
        return {}
    # Normalização defensiva: evita objetos não serializáveis e payloads
    # gigantes em logs. Nunca grave senha, token, CPF ou arquivo bruto aqui.
    bruto = json.dumps(detalhes, ensure_ascii=False, default=str)
    if len(bruto) > 12000:
        bruto = bruto[:12000]
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return {"resumo": bruto}


def registrar_auditoria(
    request,
    acao,
    *,
    entidade="",
    objeto_id="",
    objeto_repr="",
    detalhes=None,
):
    usuario = None
    if request is not None:
        candidato = getattr(request, "user", None)
        if candidato is not None and getattr(candidato, "is_authenticated", False):
            usuario = candidato

    evento = AuditoriaEvento.objects.create(
        usuario=usuario,
        acao=acao,
        entidade=str(entidade or "")[:80],
        objeto_id=str(objeto_id or "")[:80],
        objeto_repr=str(objeto_repr or "")[:255],
        metodo=(getattr(request, "method", "") or "")[:10] if request else "",
        caminho=(getattr(request, "path", "") or "")[:255] if request else "",
        ip_hash=hash_ip(_ip_cliente(request)) if request else "",
        user_agent=(
            (request.META.get("HTTP_USER_AGENT", "") or "")[:255]
            if request
            else ""
        ),
        request_id=request_id(request) if request else None,
        detalhes=detalhes_seguros(detalhes),
    )
    return evento
