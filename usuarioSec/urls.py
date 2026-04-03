from django.contrib import admin
from django.urls import path, include
from .views import AccountCreateView
from .import views 


urlpatterns = [
   
    path('cadastro', AccountCreateView.as_view(), name="cadastro"),
    path('dashboard/',views.dashboard, name="dashboard"),
    path('buscar/', views.buscar_cadrasto, name="buscar_cadrasto"),
    path('editAluno/<int:id>/', views.edit_aluno, name="edit_aluno"),
    path('excluirAluno/<int:id>/', views.deletar_aluno, name="deletar_aluno"),
    path('imprimir/<int:id>/', views.matriculaimpressao, name="matriculaimpressao"),
    path('sair/', views.sair, name='sair'),
    path('declaracoes/', views.declaracoes,name="declaracoes"),
    path('historico/', views.historico,name="historico"),
    path('transferencia/', views.transferencia,name="transferencia"),
    path('escolaridade/', views.escolaridade,name="escolaridade"),
    path('bolsaFamilia/', views.bolsaFamilia,name="bolsaFamilia"),
    path('comparecimento/', views.comparecimento,name="comparecimento"),
    path('telaDeclaracao/', views.telaDeclaracao,name="telaDeclaracao"),
    path("importar/", views.importar_alunos, name="importar_alunos"),
    path('buscardeclaracao/', views.buscar_dados_declaracao, name="buscar_dados_declaracao"),
    path('salvar-declaracao/<int:id>/', views.salvar_declaracao, name='salvar_declaracao'),
    path('imprimirDeclaracao/<int:id>/', views.imprimirDeclaracao, name='imprimirDeclaracao'),
    path('deletar_aluno_declaracao/<int:id>/', views.deletar_aluno_declaracao, name='deletar_aluno_declaracao'),
    path('cadastrar_aluno/', views.cadastrar_aluno, name='cadastrar_aluno'),
    path('apagar_todos_alunos/', views.apagar_todos_alunos, name='apagar_todos_alunos'),
    path('apagar_todos_alunos_matricula/', views.apagar_todos_alunos_matricula, name='apagar_todos_alunos_matricula'),

    
    
    
]
