from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
        ),
        name="login",
    ),
    path("accounts/", include("django.contrib.auth.urls")),

    # Área interna autenticada.
    path("historico/", include("historico.urls")),

    # Área pública de matrícula + restante do sistema legado.
    path("", include("cadastro.urls")),
    path("", include("usuarioSec.urls")),
]
