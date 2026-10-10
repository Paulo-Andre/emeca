from django.urls import path, re_path

from . import views


urlpatterns = [
    path(
        "api/public/matricula/",
        views.cadastrar,
        name="matricula_api",
    ),
    re_path(
        r"^matricula(?:/(?P<subpath>.*))?$",
        views.matricula_publica,
        name="matricula_publica",
    ),
]
