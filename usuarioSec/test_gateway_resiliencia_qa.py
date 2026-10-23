"""Falhas do gateway nunca derrubam WhatsApp Web com erro 500.

Todos os cenários usam mocks e valores sintéticos; nenhum envio real ocorre.
"""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .whatsapp_gateway import WhatsAppGatewayError, _request, _request_multipart


@override_settings(
    WA_AKG_BASE_URL="http://gateway.invalid",
    WA_AKG_API_KEY="token-sintetico-nao-real",
    WA_AKG_SESSION_ID="sessao-sintetica",
    WA_AKG_TIMEOUT_SECONDS=2,
)
class ResilienciaGatewayWhatsAppTests(SimpleTestCase):
    @patch("usuarioSec.whatsapp_gateway.urlopen", side_effect=TimeoutError())
    def test_timeout_da_consulta_de_sessao_nao_gera_erro_500(self, abrir):
        with self.assertRaises(WhatsAppGatewayError):
            _request("GET", "sessions/sessao-sintetica")
        abrir.assert_called_once()

    @patch("usuarioSec.whatsapp_gateway.urlopen", side_effect=TimeoutError())
    def test_timeout_de_purga_nao_faz_retentativa(self, abrir):
        with self.assertRaises(WhatsAppGatewayError):
            _request("POST", "sessions/sessao-sintetica/purge-history", {})
        abrir.assert_called_once()

    @patch("usuarioSec.whatsapp_gateway.urlopen")
    def test_resposta_html_na_consulta_de_sessao_eh_rejeitada(self, abrir):
        abrir.return_value.__enter__.return_value.read.return_value = b"<html>erro</html>"
        with self.assertRaises(WhatsAppGatewayError):
            _request("GET", "sessions/sessao-sintetica")
        abrir.assert_called_once()

    @patch("usuarioSec.whatsapp_gateway.urlopen")
    def test_resposta_html_no_multipart_eh_rejeitada(self, abrir):
        abrir.return_value.__enter__.return_value.read.return_value = b"<html>erro</html>"
        with self.assertRaises(WhatsAppGatewayError):
            _request_multipart("messages/teste/media", {"type": "document"},
                               "teste.pdf", "application/pdf", b"%PDF-1.4")
        abrir.assert_called_once()
