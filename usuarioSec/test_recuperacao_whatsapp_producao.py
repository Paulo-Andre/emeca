"""Regressões de recuperação segura da integração WhatsApp em produção."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarioSec.models import SessaoWhatsAppAtiva
from usuarioSec.whatsapp_gateway import WhatsAppGatewayError


@override_settings(WA_AKG_SESSION_ID="wa-qa-producao")
class RecuperacaoWhatsAppTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser(
            username="qa_recuperacao_wa", email="qa@example.invalid", password="senha-qa"
        )
        self.client.force_login(admin)

    @patch("usuarioSec.whatsapp_views.obter_qr")
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    def test_nao_pede_qr_de_sessao_conectada(self, consulta, qr):
        resp = self.client.get(reverse("whatsapp_qr"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["connected"])
        qr.assert_not_called()

    @patch("usuarioSec.whatsapp_views.obter_qr")
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           side_effect=WhatsAppGatewayError("Session not found", 404))
    def test_sessao_ausente_nao_recria_nem_apaga(self, consulta, qr):
        resp = self.client.get(reverse("whatsapp_qr"))
        self.assertEqual(resp.status_code, 409)
        self.assertIn("Conectar WhatsApp", resp.json()["erro"])
        qr.assert_not_called()

    @patch("usuarioSec.whatsapp_views.obter_qr")
    @patch("usuarioSec.whatsapp_views.obter_sessao")
    def test_limpeza_pendente_impede_consulta_ao_servidor(self, consulta, qr):
        SessaoWhatsAppAtiva.objects.create(
            chave="secretaria", sessao_id="wa-qa-producao",
            limpeza_pendente=True
        )
        resp = self.client.get(reverse("whatsapp_qr"))
        self.assertEqual(resp.status_code, 409)
        consulta.assert_not_called()
        qr.assert_not_called()

    @patch("usuarioSec.whatsapp_views.obter_qr",
           return_value={"base64": "data:image/png;base64,QUJD"})
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "SCAN_QR"}})
    def test_qr_valido_continua_funcionando(self, consulta, qr):
        resp = self.client.get(reverse("whatsapp_qr"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        qr.assert_called_once_with()
