from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect


class LoginRequiredMiddleware:
    """
    Protege toda a área interna do EMECA.

    Exceções deliberadamente públicas:
    - matrícula online dos responsáveis;
    - API pública usada pela própria página de matrícula;
    - login/recuperação de conta e arquivos estáticos.

    O módulo /historico/ NÃO está na lista pública e, portanto, exige
    usuário autenticado.
    """

    PUBLIC_PREFIXES = (
        "/matricula",
        "/api/public/matricula/",
        "/login/",
        "/accounts/",
        "/static/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if request.user.is_authenticated:
            return self.get_response(request)

        if any(path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES):
            return self.get_response(request)

        login_url = settings.LOGIN_URL
        return redirect(f"{login_url}?next={quote(path)}")
