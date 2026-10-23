"""Protege a interface do EMECA contra timeout de socket do WA-AKG.

Todos os testes usam rede fictícia e mocks. Não enviam mensagens.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from usuarioSec.whatsapp_gateway import WhatsAppGatewayError, _request, _request_multipart


CONFIG = override_settings(
    WA_AKG_BASE_URL="http://gateway.invalid",
    WA_AKG_API_KEY="chave-sintetica-testes",
    WA_AKG_SESSION_ID="sessao-qa",
    WA_AKG_TIMEOUT_SECONDS=2,
)


@CONFIG
class GatewayTimeoutTests(SimpleTestCase):
    @patch("usuarioSec.whatsapp_gateway.urlopen", side_effect=TimeoutError("timeout ficticio"))
    def test_get_timeout_de_socket_retorna_erro_tratado(self, _urlopen):
        with self.assertRaises(WhatsAppGatewayError) as context:
            _request("GET", "sessions/sessao-qa")
        self.assertIn("não respondeu no prazo", str(context.exception))

    @patch("usuarioSec.whatsapp_gateway.urlopen", side_effect=TimeoutError("timeout ficticio"))
    def test_multipart_timeout_nao_reenvia_nem_revela_dados(self, urlopen):
        with self.assertRaises(WhatsAppGatewayError):
            _request_multipart(
                "messages/sessao-qa/ficticio/media",
                {"type": "document"}, "documento.pdf",
                "application/pdf", b"%PDF-1.4 sintentico",
            )
        urlopen.assert_called_once()


@CONFIG
class TelaEnviosTimeoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="teste_gateway_indisponivel",
            email="teste@example.invalid",
            password="senha-local-de-testes",
        )
        self.client.force_login(self.user)

    @patch("usuarioSec.whatsapp_gateway.urlopen", side_effect=TimeoutError("timeout ficticio"))
    def test_tela_whatsapp_nao_retorna_500_quando_gateway_expira(self, _urlopen):
        resposta = self.client.get(reverse("whatsapp"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "WhatsApp")
