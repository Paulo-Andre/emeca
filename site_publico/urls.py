from django.urls import path
from . import views

app_name = "site_publico"

urlpatterns = [
    path("", views.home, name="home"),
    path("a-escola/", views.escola, name="escola"),
    path("vida-escolar/", views.vida_escolar, name="vida_escolar"),
    path("atividades-jogos/", views.atividades, name="atividades"),
    path("atividades-jogos/<slug:slug>/", views.atividade, name="atividade"),
    path("projetos/", views.projetos, name="projetos"),
    path("projetos/<slug:slug>/", views.projeto, name="projeto"),
    path("noticias/", views.noticias, name="noticias"),
    path("noticias/<slug:slug>/", views.noticia, name="noticia"),
    path("galeria/", views.galeria, name="galeria"),
    path("galeria/<slug:slug>/", views.album, name="album"),
    path("matricula/", views.matricula_landing, name="matricula_landing"),
    path("documentos/", views.documentos, name="documentos"),
    path("perguntas-frequentes/", views.faq, name="faq"),
    path("contato/", views.contato, name="contato"),
]
