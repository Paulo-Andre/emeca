import hashlib
import json
import uuid

from django.conf import settings

from .models import AuditoriaEvento


SENSITIVE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "chave",
    "cookie",
    "cpf",
    "cpf_mae",
    "cpf_pai",
    "cpf_responsavel",
    "data_nascimento",
    "email",
    "nascimento",
    "password",
    "senha",
    "secret",
    "segredo",
    "telefone",
    "token",
    "whatsapp",
}


def _ip_cliente(request):
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _hash_privado(valor):
    if valor in (None, ""):
        return ""
    segredo = str(settings.SECRET_KEY).encode("utf-8")
    bruto = str(valor).encode("utf-8")
    return hashlib.sha256(segredo + b":" + bruto).hexdigest()


def hash_ip(ip):
    return _hash_privado(ip)


def request_id(request):
    valor = getattr(request, "audit_request_id", None)
    if valor:
        return valor
    valor = uuid.uuid4()
    request.audit_request_id = valor
    return valor


def _chave_sensivel(chave):
    normalizada = str(chave or "").strip().lower().replace("-", "_")
    return any(
        normalizada == item
        or normalizada.startswith(f"{item}_")
        or normalizada.endswith(f"_{item}")
        for item in SENSITIVE_KEYS
    )


def _redigir(valor):
    if isinstance(valor, dict):
        return {
            str(chave): "[REDACTED]" if _chave_sensivel(chave) else _redigir(item)
            for chave, item in valor.items()
        }
    if isinstance(valor, (list, tuple, set)):
        return [_redigir(item) for item in valor]
    return valor


def detalhes_seguros(detalhes):
    if not detalhes:
        return {}
    # Redação defensiva antes da serialização. Mesmo que um chamador envie
    # acidentalmente senha, token, CPF ou contato, o valor não é persistido.
    seguro = _redigir(detalhes)
    bruto = json.dumps(seguro, ensure_ascii=False, default=str)
    if len(bruto) > 12000:
        bruto = bruto[:12000]
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return {"resumo": "[TRUNCATED]"}


def _referencia_segura(valor):
    if not valor:
        return ""
    return f"ref:{_hash_privado(valor)[:16]}"


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

    resolver = getattr(request, "resolver_match", None) if request else None
    caminho = (
        getattr(resolver, "view_name", "")
        or (getattr(request, "path", "") if request else "")
    )

    evento = AuditoriaEvento.objects.create(
        usuario=usuario,
        acao=acao,
        entidade=str(entidade or "")[:80],
        objeto_id=str(objeto_id or "")[:80],
        # A representação frequentemente contém nome de aluno. Guardamos apenas
        # uma referência correlacionável, sem PII em texto claro.
        objeto_repr=_referencia_segura(objeto_repr)[:255],
        metodo=(getattr(request, "method", "") or "")[:10] if request else "",
        caminho=str(caminho)[:255],
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
