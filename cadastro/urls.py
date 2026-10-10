from django.urls import path
from . import views

urlpatterns = [
    path("matricula/", views.cadastrar, name="matricula"),
    path("matricula-online/", views.matricula_publica, name="matricula_publica"),
]
