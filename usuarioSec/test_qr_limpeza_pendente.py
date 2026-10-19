"""Regressão da tela QR e da finalização de sessão antiga ausente."""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from usuarioSec.models import SessaoWhatsAppAtiva


@override_settings(WA_AKG_SESSION_ID="sessao-antiga-qa")
class QRLimpezaPendenteTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_superuser(
            username="qa_limpeza_qr", email="qa@example.invalid", password="senha-teste"
        )
        self.client.force_login(usuario)
        SessaoWhatsAppAtiva.objects.create(
            chave="secretaria", sessao_id="sessao-antiga-qa", limpeza_pendente=True
        )

    @patch("usuarioSec.whatsapp_views.obter_qr")
    def test_qr_bloqueado_antes_de_chamar_gateway(self, gateway):
        response = self.client.get(reverse("whatsapp_qr"))
        self.assertEqual(response.status_code, 409)
        self.assertIn("Limpeza", response.json()["erro"])
        gateway.assert_not_called()
