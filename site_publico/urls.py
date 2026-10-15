from django.urls import path
from . import views, management_views

app_name = "site_publico"

urlpatterns = [
    path("gestao-site/", management_views.gestao_site, name="gestao_site"),
    path("gestao-site/configuracao/", management_views.gestao_configuracao, name="gestao_configuracao"),
    path("gestao-site/paginas/", management_views.gestao_paginas, name="gestao_paginas"),
    path("gestao-site/paginas/<str:chave>/editar/", management_views.gestao_pagina_editar, name="gestao_pagina_editar"),
    path("gestao-site/paginas/<str:chave>/alternar/", management_views.gestao_pagina_toggle, name="gestao_pagina_toggle"),
    path("gestao-site/conteudo/<str:tipo>/", management_views.gestao_conteudo_lista, name="gestao_conteudo_lista"),
    path("gestao-site/conteudo/<str:tipo>/novo/", management_views.gestao_conteudo_novo, name="gestao_conteudo_novo"),
    path("gestao-site/conteudo/<str:tipo>/<int:pk>/editar/", management_views.gestao_conteudo_editar, name="gestao_conteudo_editar"),
    path("gestao-site/conteudo/<str:tipo>/<int:pk>/excluir/", management_views.gestao_conteudo_excluir, name="gestao_conteudo_excluir"),
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
    path("matricula-escolar/", views.matricula_landing, name="matricula_landing"),
    path("boletim/", views.boletim, name="boletim"),
    path("documentos/", views.documentos, name="documentos"),
    path("perguntas-frequentes/", views.faq, name="faq"),
    path("contato/", views.contato, name="contato"),
]
