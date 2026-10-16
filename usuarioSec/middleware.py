from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .access_control import usuario_tem_modulo
from .security_rate_limit import consumir_limite, ip_cliente, limpar_limite


class SecurityRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _bloqueado(self, request, segundos):
        resposta_json = (
            request.path == reverse("matricula")
            or "application/json" in (request.headers.get("Content-Type") or "")
        )
        if resposta_json:
            response = JsonResponse(
                {
                    "status": "erro",
                    "mensagem": "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
                },
                status=429,
            )
        else:
            response = HttpResponse(
                "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
                status=429,
                content_type="text/plain; charset=utf-8",
            )
        response["Retry-After"] = str(max(1, int(segundos)))
        response["Cache-Control"] = "no-store"
        return response

    def __call__(self, request):
        if request.method != "POST" or not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return self.get_response(request)

        ip = ip_cliente(request)
        login_path = reverse("login")
        boletim_path = reverse("site_publico:boletim")
        matricula_path = reverse("matricula")
        contato_path = reverse("site_publico:contato")

        chaves_consumidas = []

        if request.path == login_path:
            username = (request.POST.get("username") or "").strip().casefold()[:150]
            if username:
                permitido, retry = consumir_limite(
                    "login-conta",
                    username,
                    settings.LOGIN_RATE_LIMIT_ACCOUNT,
                    settings.LOGIN_RATE_LIMIT_WINDOW,
                )
                if not permitido:
                    return self._bloqueado(request, retry)
                chaves_consumidas.append(("login-conta", username))

            permitido, retry = consumir_limite(
                "login-ip",
                ip,
                settings.LOGIN_RATE_LIMIT_IP,
                settings.LOGIN_RATE_LIMIT_WINDOW,
            )
            if not permitido:
                return self._bloqueado(request, retry)

        elif request.path == boletim_path:
            permitido, retry = consumir_limite(
                "boletim-ip",
                ip,
                settings.BOLETIM_RATE_LIMIT_IP,
                settings.BOLETIM_RATE_LIMIT_WINDOW,
            )
            if not permitido:
                return self._bloqueado(request, retry)

        elif request.path == matricula_path:
            permitido, retry = consumir_limite(
                "matricula-ip",
                ip,
                settings.MATRICULA_RATE_LIMIT_IP,
                settings.MATRICULA_RATE_LIMIT_WINDOW,
            )
            if not permitido:
                return self._bloqueado(request, retry)

        elif request.path == contato_path:
            permitido, retry = consumir_limite(
                "contato-ip",
                ip,
                settings.CONTATO_RATE_LIMIT_IP,
                settings.CONTATO_RATE_LIMIT_WINDOW,
            )
            if not permitido:
                return self._bloqueado(request, retry)

        response = self.get_response(request)

        # Um login bem-sucedido limpa somente o contador da conta.
        # O contador do IP continua impedindo spray distribuído de senhas.
        if (
            request.path == login_path
            and 300 <= response.status_code < 400
            and getattr(request.user, "is_authenticated", False)
        ):
            for bucket, identidade in chaves_consumidas:
                limpar_limite(bucket, identidade)

        return response


class LoginRequiredMiddleware:
    PUBLIC_PREFIXES = (
        "/static/",
        "/media/site_publico/",
        "/historico/validar/",
        "/matricula-online/",
        "/a-escola/",
        "/vida-escolar/",
        "/atividades-jogos/",
        "/projetos/",
        "/noticias/",
        "/galeria/",
        "/documentos/",
        "/perguntas-frequentes/",
        "/contato/",
        "/configuracao-site-publica/",
        "/boletim/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            return self.get_response(request)

        allowed_urls = {
            "/",
            reverse("login"),
            reverse("matricula"),
            reverse("site_publico:matricula_landing"),
        }
        if request.path in allowed_urls or request.path.startswith(self.PUBLIC_PREFIXES):
            return self.get_response(request)

        return redirect(f"{reverse('login')}?next={request.get_full_path()}")


class ModuleAccessMiddleware:
    MODULE_PREFIXES = (
        ("administracao", ("/cadastro",)),
        ("historico", ("/historico/",)),
        ("boletins", ("/boletins/",)),
        ("site", ("/gestao-site/",)),
        ("whatsapp", ("/whatsapp/",)),
        (
            "secretaria",
            (
                "/dashboard/",
                "/buscar/",
                "/editAluno/",
                "/excluirAluno/",
                "/imprimir/",
                "/declaracoes/",
                "/transferencia/",
                "/escolaridade/",
                "/bolsaFamilia/",
                "/comparecimento/",
                "/telaDeclaracao/",
                "/importar/",
                "/buscardeclaracao/",
                "/salvar-declaracao/",
                "/imprimirDeclaracao/",
                "/deletar_aluno_declaracao/",
                "/cadastrar_aluno/",
                "/apagar_todos_alunos/",
                "/apagar_todos_alunos_matricula/",
            ),
        ),
    )

    PUBLIC_EXCEPTIONS = (
        "/historico/validar/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        if request.path.startswith(self.PUBLIC_EXCEPTIONS):
            return self.get_response(request)

        strict = getattr(settings, "EMECA_RBAC_STRICT", True)
        for modulo, prefixos in self.MODULE_PREFIXES:
            if request.path.startswith(prefixos):
                if not usuario_tem_modulo(request.user, modulo, strict=strict):
                    return HttpResponseForbidden(
                        "Você não possui permissão para acessar este módulo."
                    )
                break

        return self.get_response(request)
