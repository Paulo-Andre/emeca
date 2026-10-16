import re
import secrets
import uuid

from django.db import DatabaseError

from .auditoria import SENSITIVE_METHODS, registrar_auditoria


class SecurityAuditMiddleware:
    """
    Acrescenta request-id, cabeçalhos defensivos e registra metadados mínimos
    de operações sensíveis. O conteúdo de formulários/arquivos não é armazenado.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.audit_request_id = uuid.uuid4()
        request.csp_nonce = secrets.token_urlsafe(18)
        response = self.get_response(request)

        if (
            content_type.startswith("text/html")
            and not getattr(response, "streaming", False)
            and getattr(response, "content", None)
        ):
            try:
                html = response.content.decode(response.charset or "utf-8")
                nonce = request.csp_nonce
                html = re.sub(
                    r"<script(?![^>]*\\bnonce=)",
                    f'<script nonce="{nonce}"',
                    html,
                    flags=re.IGNORECASE,
                )
                html = re.sub(
                    r"<style(?![^>]*\\bnonce=)",
                    f'<style nonce="{nonce}"',
                    html,
                    flags=re.IGNORECASE,
                )
                response.content = html.encode(response.charset or "utf-8")
                if response.has_header("Content-Length"):
                    response["Content-Length"] = str(len(response.content))
            except (UnicodeDecodeError, AttributeError):
                pass

        response["X-Request-ID"] = str(request.audit_request_id)
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "same-origin"
        response["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        content_type = response.get("Content-Type", "")
        if (
            content_type.startswith("text/html")
            or content_type.startswith("application/json")
        ):
            response["Cache-Control"] = "no-store, max-age=0"
            response["Pragma"] = "no-cache"
        nonce = request.csp_nonce
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "object-src 'none'; "
            "img-src 'self' data:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            f"style-src 'self' https://fonts.googleapis.com 'nonce-{nonce}'; "
            "style-src-attr 'unsafe-inline'; "
            f"script-src 'self' https://unpkg.com 'nonce-{nonce}'; "
            "script-src-attr 'unsafe-inline'"
        )

        if (
            request.method in SENSITIVE_METHODS
            and getattr(request, "user", None) is not None
            and request.user.is_authenticated
            and response.status_code < 500
        ):
            try:
                registrar_auditoria(
                    request,
                    "REQUEST_SENSIVEL",
                    entidade="HTTP",
                    objeto_id=request.path,
                    detalhes={
                        "status": response.status_code,
                        "content_type": response.get("Content-Type", ""),
                    },
                )
            except DatabaseError:
                # Auditoria nunca deve derrubar a operação principal.
                pass

        return response
