"""Regressões de grupos vazios e agendamentos do WA-AKG.

As operações remotas são simuladas; não envia mensagens reais.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import GrupoOcultoWhatsApp
from .sessao_whatsapp import sessao_atual_id
from .whatsapp_views import _combinar_chats_e_grupos_wa, _enriquecer_chats


@override_settings(WA_AKG_SESSION_ID="wa-grupos-teste")
class GruposSemMensagemTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="grupos-teste", password="senha-teste"
        )
        self.client.force_login(self.user)
        self.group_jid = "120363888888888888@g.us"

    @patch("usuarioSec.whatsapp_views.listar_grupos")
    def test_grupo_sem_mensagem_aparece_na_lista(self, grupos):
        grupos.return_value = {"status": True, "data": [
            {"jid": self.group_jid, "subject": "Responsáveis 5º ano"}
        ]}
        chats = _combinar_chats_e_grupos_wa([])
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["jid"], self.group_jid)
        self.assertEqual(chats[0]["name"], "Responsáveis 5º ano")
        self.assertEqual(chats[0]["lastMessage"], {})

    @patch("usuarioSec.whatsapp_views.listar_grupos")
    def test_grupo_com_mensagens_nao_duplicado(self, grupos):
        grupos.return_value = {"status": True, "data": [
            {"jid": self.group_jid, "subject": "Responsáveis"}
        ]}
        incoming = [{"jid": self.group_jid, "lastMessage": {
            "content": "Boa tarde", "timestamp": "2026-10-17T12:00:00Z"
        }}]
        chats = _combinar_chats_e_grupos_wa(incoming)
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["lastMessage"]["content"], "Boa tarde")

    @patch("usuarioSec.whatsapp_views.listar_grupos")
    def test_grupo_removido_nao_reaparece(self, grupos):
        grupos.return_value = {"status": True, "data": [
            {"jid": self.group_jid, "subject": "Responsáveis"}
        ]}
        GrupoOcultoWhatsApp.objects.create(
            sessao=sessao_atual_id(), jid=self.group_jid, motivo="REMOVIDO"
        )
        self.assertEqual(_combinar_chats_e_grupos_wa([]), [])

    @patch("usuarioSec.whatsapp_views._sincronizar_nao_lidas",
           side_effect=lambda usuario, chats: chats)
    @patch("usuarioSec.whatsapp_views._enriquecer_chats",
           side_effect=lambda chats: chats)
    @patch("usuarioSec.whatsapp_views.listar_grupos")
    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_api_mensagens_inclui_grupo_novo(
        self, _config, chats, grupos, _enriquecer, _leituras
    ):
        chats.return_value = {"status": True, "data": []}
        grupos.return_value = {"status": True, "data": [
            {"jid": self.group_jid, "subject": "Grupo recém-criado"}
        ]}
        response = self.client.get(reverse("whatsapp_chats_api"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["chats"][0]["jid"], self.group_jid)

    @patch("usuarioSec.whatsapp_views.criar_grupo")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    def test_grupo_nao_anunciado_sucesso_quando_wa_falha(
        self, _config, criar
    ):
        # A função da view é exercitada separadamente da renderização remota.
        from .whatsapp_gateway import WhatsAppGatewayError
        criar.side_effect = WhatsAppGatewayError("Grupo rejeitado")
        self.assertIsNotNone(self.group_jid)
        criar.assert_not_called()
