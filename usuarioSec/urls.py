from django.contrib import admin
from django.urls import path, include
from .views import AccountCreateView
from .import views 
from . import whatsapp_views
from django.shortcuts import redirect


urlpatterns = [
    path('', lambda request: redirect('dashboard/')),  # 👈 AQUI
    path('cadastro', AccountCreateView.as_view(), name="cadastro"),
    path('usuarios/acessos/', views.gerenciar_acessos, name="gerenciar_acessos"),
    path('entrada/', views.entrada, name="entrada"),
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
    path('whatsapp/', whatsapp_views.whatsapp, name='whatsapp'),
    path('whatsapp/contatos/', whatsapp_views.whatsapp_buscar_contatos, name='whatsapp_buscar_contatos'),
    path('whatsapp/destinatarios/', whatsapp_views.whatsapp_destinatarios, name='whatsapp_destinatarios'),
    path('whatsapp/boletins-preview/', whatsapp_views.whatsapp_boletins_preview, name='whatsapp_boletins_preview'),
    path('whatsapp/conectar/', whatsapp_views.whatsapp_conectar, name='whatsapp_conectar'),
    path('whatsapp/desconectar/', whatsapp_views.whatsapp_desconectar, name='whatsapp_desconectar'),
    path('whatsapp/qr/', whatsapp_views.whatsapp_qr, name='whatsapp_qr'),
    path('whatsapp/enviar/', whatsapp_views.whatsapp_enviar, name='whatsapp_enviar'),
    path('whatsapp/mensagens/', whatsapp_views.whatsapp_mensagens, name='whatsapp_mensagens'),
    path('whatsapp/gerenciamento/', whatsapp_views.whatsapp_gerenciamento, name='whatsapp_gerenciamento'),
    path('whatsapp/importar-contatos/', whatsapp_views.whatsapp_importar_agenda, name='whatsapp_importar_agenda'),
    path('whatsapp/chats-api/', whatsapp_views.whatsapp_chats_api, name='whatsapp_chats_api'),
    path('whatsapp/chat-api/', whatsapp_views.whatsapp_chat_api, name='whatsapp_chat_api'),
    path('whatsapp/identificar-contato/', whatsapp_views.whatsapp_identificar_contato_api, name='whatsapp_identificar_contato_api'),
    path('whatsapp/contatos-wa/', whatsapp_views.whatsapp_buscar_contatos_wa, name='whatsapp_buscar_contatos_wa'),
    path('whatsapp/nova-conversa/', whatsapp_views.whatsapp_nova_conversa_api, name='whatsapp_nova_conversa_api'),
    path('whatsapp/gerenciar-chat/', whatsapp_views.whatsapp_gerenciar_chat_api, name='whatsapp_gerenciar_chat_api'),
    path('whatsapp/perfil-api/', whatsapp_views.whatsapp_perfil_api, name='whatsapp_perfil_api'),
    path('whatsapp/foto-api/', whatsapp_views.whatsapp_foto_api, name='whatsapp_foto_api'),
    path('whatsapp/foto-imagem/', whatsapp_views.whatsapp_foto_imagem, name='whatsapp_foto_imagem'),
    path('whatsapp/midia-api/', whatsapp_views.whatsapp_enviar_midia_api, name='whatsapp_enviar_midia_api'),
    path('whatsapp/responder-api/', whatsapp_views.whatsapp_responder_api, name='whatsapp_responder_api'),
    path('whatsapp/buscar-mensagens/', whatsapp_views.whatsapp_buscar_mensagens_api, name='whatsapp_buscar_mensagens_api'),
    path('whatsapp/acao-mensagem/', whatsapp_views.whatsapp_acao_mensagem_api, name='whatsapp_acao_mensagem_api'),
    path('whatsapp/encaminhar/', whatsapp_views.whatsapp_encaminhar_api, name='whatsapp_encaminhar_api'),
    path('whatsapp/bloqueio/', whatsapp_views.whatsapp_bloqueio_api, name='whatsapp_bloqueio_api'),
    path('whatsapp/presenca/', whatsapp_views.whatsapp_presenca_api, name='whatsapp_presenca_api'),
    path('whatsapp/etiquetas/', whatsapp_views.whatsapp_etiquetas_api, name='whatsapp_etiquetas_api'),
    path('whatsapp/etiquetas/criar/', whatsapp_views.whatsapp_etiquetas_criar_api, name='whatsapp_etiquetas_criar_api'),
    path('whatsapp/etiquetas/atualizar/', whatsapp_views.whatsapp_etiquetas_atualizar_api, name='whatsapp_etiquetas_atualizar_api'),
    path('whatsapp/midia/<str:message_id>/', whatsapp_views.whatsapp_midia_recebida, name='whatsapp_midia_recebida'),

    
    
    
]
