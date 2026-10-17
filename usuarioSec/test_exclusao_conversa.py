"""Exclusão de conversa somente no EMECA — sem apagar dados do WA-AKG."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ConversaExcluidaWhatsApp
from .sessao_whatsapp import criar_sessao_isolada, sessao_atual_id
from .whatsapp_views import _filtrar_conversas_excluidas_wa


@override_settings(WA_AKG_SESSION_ID="sessao-escola-teste")
class ExclusaoConversaWhatsAppTests(TestCase):
    def setUp(self):
        self.operador = get_user_model().objects.create_user(
            username="operador-exclui", password="Senha-local-123"
        )
        self.colega = get_user_model().objects.create_user(
            username="operador-colega", password="Senha-local-456"
        )
        self.client.force_login(self.operador)
        self.jid = "5538999991234@s.whatsapp.net"
        self.alias = "1234567890123@lid"
        self.ontem = (timezone.now() - timedelta(days=1)).isoformat()
        self.amanha = (timezone.now() + timedelta(days=1)).isoformat()
        self.chat = {
            "jid": self.jid, "aliases": [self.jid, self.alias],
            "lastMessage": {"timestamp": self.ontem, "content": "Mensagem antiga"}
        }

    def _excluir(self, confirmacao="EXCLUIR", jid=None):
        return self.client.post(reverse("whatsapp_excluir_conversa_api"), {
            "jid": jid or self.jid, "confirmacao": confirmacao,
        })

    @patch("usuarioSec.whatsapp_views._enriquecer_chats")
    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_exclui_da_lista_sem_apagar_no_gateway(
        self, _gateway, listar, enriquecer
    ):
        listar.return_value = {"status": True, "data": [{"jid": self.jid}]}
        enriquecer.return_value = [self.chat]
        resposta = self._excluir()
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertTrue(resposta.json()["ok"])
        self.assertEqual(ConversaExcluidaWhatsApp.objects.count(), 2)
        self.assertEqual(
            _filtrar_conversas_excluidas_wa(self.operador, [self.chat]), []
        )
        self.assertEqual(
            len(_filtrar_conversas_excluidas_wa(self.colega, [self.chat])), 1
        )

    @patch("usuarioSec.whatsapp_views._sincronizar_nao_lidas",
           side_effect=lambda usuario, chats: chats)
    @patch("usuarioSec.whatsapp_views._enriquecer_chats")
    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_api_de_conversas_oculta_a_excluida_no_refresh(
        self, _gateway, listar, enriquecer, _nao_lidas
    ):
        listar.return_value = {"status": True, "data": [{"jid": self.jid}]}
        enriquecer.return_value = [self.chat]
        resposta = self._excluir()
        self.assertEqual(resposta.status_code, 200)
        carregamento = self.client.get(reverse("whatsapp_chats_api"))
        self.assertEqual(carregamento.status_code, 200)
        self.assertEqual(carregamento.json()["chats"], [])

    @patch("usuarioSec.whatsapp_views._enriquecer_chats")
    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_uma_mensagem_nova_reabre_a_conversa(
        self, _gateway, listar, enriquecer
    ):
        listar.return_value = {"status": True, "data": [{"jid": self.jid}]}
        enriquecer.return_value = [self.chat]
        self._excluir()
        self.assertFalse(_filtrar_conversas_excluidas_wa(self.operador, [self.chat]))
        updated = {**self.chat, "lastMessage": {
            "timestamp": self.amanha, "content": "Mensagem nova"
        }}
        self.assertEqual(
            len(_filtrar_conversas_excluidas_wa(self.operador, [updated])), 1
        )

    @patch("usuarioSec.whatsapp_views._enriquecer_chats")
    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    @patch("usuarioSec.whatsapp_views.obter_mensagens_chat")
    @patch("usuarioSec.whatsapp_views._contatos_wa", return_value=[])
    @patch("usuarioSec.whatsapp_views.marcar_chat_como_lido")
    def test_historico_antigo_oculto_quando_reaparece(
        self, _lido, _contatos, mensagens, _gateway, listar, enriquecer
    ):
        listar.return_value = {"status": True, "data": [{"jid": self.jid}]}
        enriquecer.return_value = [self.chat]
        self._excluir()
        mensagens.return_value = {"data": [
            {"keyId": "antiga", "timestamp": self.ontem, "content": "Antiga"},
            {"keyId": "nova", "timestamp": self.amanha, "content": "Nova"}
        ]}
        resultado = self.client.get(reverse("whatsapp_chat_api"), {
            "jid": self.jid
        })
        self.assertEqual(resultado.status_code, 200, resultado.content)
        self.assertEqual(
            [m["keyId"] for m in resultado.json()["mensagens"]], ["nova"]
        )

    @patch("usuarioSec.whatsapp_views._enriquecer_chats")
    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_alias_lid_compartilha_corte_com_telefone(
        self, _gateway, listar, enriquecer
    ):
        listar.return_value = {"status": True, "data": [{"jid": self.jid}]}
        enriquecer.return_value = [self.chat]
        self._excluir(jid=self.alias)
        self.assertEqual(
            ConversaExcluidaWhatsApp.objects.filter(
                sessao=sessao_atual_id()
            ).count(), 2
        )
        self.assertFalse(_filtrar_conversas_excluidas_wa(self.operador, [self.chat]))

    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_recusa_sem_confirmacao(self, _gateway, listar):
        resp = self._excluir(confirmacao="NÃO")
        self.assertEqual(resp.status_code, 400)
        listar.assert_not_called()
        self.assertFalse(ConversaExcluidaWhatsApp.objects.exists())

    @patch("usuarioSec.whatsapp_views.listar_chats")
    def test_exige_login(self, listar):
        self.client.logout()
        resposta = self._excluir()
        self.assertEqual(resposta.status_code, 302)
        listar.assert_not_called()

    def test_exige_post(self):
        resposta = self.client.get(reverse("whatsapp_excluir_conversa_api"))
        self.assertEqual(resposta.status_code, 405)

    @patch("usuarioSec.whatsapp_views._enriquecer_chats")
    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_conta_nova_nao_herda_conversa_excluida(
        self, _gateway, listar, enriquecer
    ):
        listar.return_value = {"status": True, "data": [{"jid": self.jid}]}
        enriquecer.return_value = [self.chat]
        self._excluir()
        criar_sessao_isolada()
        self.assertEqual(
            len(_filtrar_conversas_excluidas_wa(self.operador, [self.chat])), 1
        )

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    def test_botao_e_confirmacao_visiveis(self, _gateway):
        resultado = self.client.get(reverse("whatsapp_mensagens"))
        self.assertEqual(resultado.status_code, 200)
        self.assertContains(resultado, 'id="deleteChatButton"')
        self.assertContains(resultado, 'id="deleteChatDialog"')
        self.assertContains(resultado, "histórico original do WhatsApp")
