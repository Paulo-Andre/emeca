"""Testes da exclusão permanente por sessão; WA-AKG sempre simulado.

O teste NUNCA usa WhatsApp real. A exclusão remota é substituída por mocks.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    ContatoAgendaWhatsApp,
    EstadoConversaWhatsApp,
    GrupoOcultoWhatsApp,
    IdentidadeContatoWhatsApp,
    SessaoWhatsAppAtiva,
)
from .sessao_whatsapp import sessao_atual_id, limpeza_historico_pendente
from .limpeza_historico_whatsapp import limpar_emeca_e_criar_sessao_nova
from .whatsapp_gateway import WhatsAppGatewayError


@override_settings(WA_AKG_SESSION_ID="conta-antiga-teste")
class LimpezaHistoricoWhatsAppTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="admin-limpeza-123", password="senha-local", is_superuser=True
        )
        self.client.force_login(self.admin)
        self.url = reverse("whatsapp_desconectar")
        self.old = sessao_atual_id()
        self.jid = "5538999991234@s.whatsapp.net"

    def _dados_exemplo(self):
        ContatoAgendaWhatsApp.objects.create(
            sessao=self.old, telefone_jid=self.jid, nome="Antigo"
        )
        IdentidadeContatoWhatsApp.objects.create(
            sessao=self.old, jid=self.jid, nome_exibicao="Antigo"
        )
        EstadoConversaWhatsApp.objects.create(
            sessao=self.old, jid=self.jid, fixado=True
        )
        GrupoOcultoWhatsApp.objects.create(
            sessao=self.old, jid="120363777777777777@g.us"
        )

    def _post(self, acao="desvincular", extras=None):
        dados = {
            "acao": acao,
            "confirmacao": {"desvincular": "DESVINCULAR",
                            "isolar": "ISOLAR",
                            "finalizar_limpeza": "APAGAR"}.get(acao, ""),
            "confirmar_exclusao": "APAGAR_HISTORICO",
        }
        dados.update(extras or {})
        return self.client.post(self.url, dados)

    @patch("usuarioSec.whatsapp_views.excluir_historico_sessao",
           return_value={"status": True, "data": {"messages": 20}})
    @patch("usuarioSec.whatsapp_views.desvincular_sessao",
           return_value={"status": True})
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_desvincular_apaga_dados_locais_e_cria_sessao_vazia(
        self, _config, _status, logout, purge
    ):
        self._dados_exemplo()
        response = self._post()
        self.assertEqual(response.status_code, 302)
        logout.assert_called_once_with()
        purge.assert_called_once_with(self.old)
        self.assertNotEqual(sessao_atual_id(), self.old)
        self.assertFalse(limpeza_historico_pendente())
        self.assertFalse(ContatoAgendaWhatsApp.objects.filter(sessao=self.old).exists())
        self.assertFalse(IdentidadeContatoWhatsApp.objects.filter(sessao=self.old).exists())
        self.assertFalse(EstadoConversaWhatsApp.objects.filter(sessao=self.old).exists())
        self.assertFalse(GrupoOcultoWhatsApp.objects.filter(sessao=self.old).exists())

    @patch("usuarioSec.whatsapp_views.excluir_historico_sessao")
    @patch("usuarioSec.whatsapp_views.desvincular_sessao",
           return_value={"status": True})
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_falha_da_purga_mantem_sessao_bloqueada(
        self, _config, _status, logout, purge
    ):
        purge.side_effect = WhatsAppGatewayError("Falha na exclusão", 500)
        self._dados_exemplo()
        response = self._post()
        self.assertEqual(response.status_code, 302)
        logout.assert_called_once_with()
        self.assertEqual(sessao_atual_id(), self.old)
        self.assertTrue(limpeza_historico_pendente())
        self.assertTrue(ContatoAgendaWhatsApp.objects.filter(sessao=self.old).exists())

    @patch("usuarioSec.whatsapp_views.iniciar_sessao")
    def test_nao_reconecta_enquanto_a_limpeza_estiver_pendente(self, iniciar):
        SessaoWhatsAppAtiva.objects.create(
            chave="secretaria", sessao_id=self.old, limpeza_pendente=True
        )
        response = self.client.post(reverse("whatsapp_conectar"))
        self.assertEqual(response.status_code, 302)
        iniciar.assert_not_called()

    @patch("usuarioSec.whatsapp_views.excluir_historico_sessao")
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "STOPPED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_pausa_nao_apaga(self, _config, _status, purge):
        self._dados_exemplo()
        with patch("usuarioSec.whatsapp_views.pausar_sessao",
                   return_value={"status": True}):
            response = self.client.post(self.url, {"acao": "pausar"})
        self.assertEqual(response.status_code, 302)
        purge.assert_not_called()
        self.assertTrue(ContatoAgendaWhatsApp.objects.filter(sessao=self.old).exists())

    @patch("usuarioSec.whatsapp_views.excluir_historico_sessao")
    @patch("usuarioSec.whatsapp_views.desvincular_sessao")
    def test_sem_confirmacao_destrutiva_nada_e_apagado(self, logout, purge):
        response = self._post(extras={"confirmar_exclusao": ""})
        self.assertEqual(response.status_code, 302)
        purge.assert_not_called()
        logout.assert_not_called()

    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "LOGGED_OUT"}})
    @patch("usuarioSec.whatsapp_views.excluir_historico_sessao",
           return_value={"status": True, "data": {"messages": 20}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_finalizar_limpeza_apos_logout_anterior(
        self, _config, purge, _status
    ):
        self._dados_exemplo()
        response = self._post(acao="finalizar_limpeza")
        self.assertEqual(response.status_code, 302)
        purge.assert_called_once_with(self.old)
        self.assertNotEqual(sessao_atual_id(), self.old)

    def test_limpeza_nao_apaga_conta_diferente(self):
        from .models import EtiquetaConversaWhatsApp
        self._dados_exemplo()
        EtiquetaConversaWhatsApp.objects.create(
            sessao="outra-conta", jid=self.jid,
            etiqueta_id="etiqueta", nome="Teste"
        )
        limpar_emeca_e_criar_sessao_nova(self.old)
        self.assertTrue(EtiquetaConversaWhatsApp.objects.filter(
            sessao="outra-conta"
        ).exists())
