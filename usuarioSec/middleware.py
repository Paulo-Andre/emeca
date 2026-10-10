from django.shortcuts import redirect
from django.urls import reverse

class LoginRequiredMiddleware:
    PUBLIC_PREFIXES = ("/static/", "/historico/validar/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            return self.get_response(request)

        allowed_urls = {reverse("login"), reverse("matricula")}
        if request.path in allowed_urls or request.path.startswith(self.PUBLIC_PREFIXES):
            return self.get_response(request)

        return redirect(f"{reverse('login')}?next={request.get_full_path()}")
