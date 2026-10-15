from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from site_publico.views import media_publica

urlpatterns = [
    path("admin/", admin.site.urls),
    path("media/<path:arquivo>", media_publica, name="site_publico_media"),
    path("", include("site_publico.urls")),
    path("historico/", include("historico.urls")),
    path("", include("cadastro.urls")),
    path("", include("usuarioSec.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("login/", auth_views.LoginView.as_view(
        template_name="registration/login.html"
    ), name="login"),
]
