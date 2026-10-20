"""Testes sintéticos do envio multipart de PDF ao WA-AKG.

Não cria boletins reais, não conecta ao WhatsApp e não envia mensagens.
"""
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from django.test import SimpleTestCase, override_settings

from usuarioSec.whatsapp_gateway import (
    WhatsAppGatewayError,
    enviar_documento,
    enviar_broadcast_midia,
)


class _HttpResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


@override_settings(
    WA_AKG_BASE_URL="http://wa-akg-teste:3000/api",
    WA_AKG_API_KEY="chave-de-teste",
    WA_AKG_SESSION_ID="emeca-sessao-sintetica",
    WA_AKG_TIMEOUT_SECONDS=10,
)
class GatewayPdfContratoTests(SimpleTestCase):
    def test_multipart_documento_pdf_respeita_endpoint_e_corpo(self):
        texto = b"%PDF-1.4\nDOCUMENTO SINTETICO\n%%EOF\n"
        with (
            patch("usuarioSec.whatsapp_gateway.sessao_atual_id", return_value="sessao-qa"),
            patch("usuarioSec.whatsapp_gateway.urlopen", return_value=_HttpResponse(
                b'{"status":true,"data":{"messageId":"id-sintetico"}}'
            )) as http,
        ):
            resposta = enviar_documento(
                "5538999991111@s.whatsapp.net", texto,
                "boletim-sintetico.pdf", "Teste de documento",
                sessao_id="sessao-qa",
            )
        requisicao = http.call_args.args[0]
        self.assertEqual(requisicao.get_method(), "POST")
        self.assertTrue(
            requisicao.full_url.endswith(
                "/messages/sessao-qa/5538999991111%40s.whatsapp.net/media"
            )
        )
        self.assertEqual(requisicao.headers["X-api-key"], "chave-de-teste")
        self.assertIn("multipart/form-data", requisicao.headers["Content-type"])
        self.assertIn(b'name="type"\r\n\r\ndocument', requisicao.data)
        self.assertIn(b'name="caption"\r\n\r\nTeste de documento', requisicao.data)
        self.assertIn(
            b'name="file"; filename="boletim-sintetico.pdf"', requisicao.data
        )
        self.assertIn(b"Content-Type: application/pdf\r\n\r\n" + texto, requisicao.data)
        self.assertEqual(resposta["status"], True)
        self.assertEqual(http.call_count, 1)

    def test_campanha_arquivo_multipart_preserva_lista_de_destinatarios(self):
        pdf = b"%PDF-1.4\nFICTICIO\n%%EOF\n"
        with (
            patch("usuarioSec.whatsapp_gateway.sessao_atual_id", return_value="sessao-qa"),
            patch("usuarioSec.whatsapp_gateway.urlopen", return_value=_HttpResponse(
                b'{"status":true,"data":{"broadcastId":"lote-qa"}}'
            )) as http,
        ):
            resposta = enviar_broadcast_midia(
                ["5538999991111@s.whatsapp.net", "5538999992222@s.whatsapp.net"],
                "", pdf, "documento.pdf", "application/pdf",
            )
        req = http.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/messages/sessao-qa/broadcast"))
        self.assertIn(b'name="recipients"', req.data)
        self.assertIn(b'5538999991111@s.whatsapp.net', req.data)
        self.assertIn(b'5538999992222@s.whatsapp.net', req.data)
        self.assertIn(b'name="message"', req.data)
        self.assertIn(b'Content-Type: application/pdf', req.data)
        self.assertIn(pdf, req.data)
        self.assertEqual(resposta["status"], True)
        self.assertEqual(http.call_count, 1)

    def test_falha_500_gera_erro_sem_reenvio_automatico(self):
        with (
            patch("usuarioSec.whatsapp_gateway.sessao_atual_id", return_value="sessao-qa"),
            patch("usuarioSec.whatsapp_gateway.urlopen") as http,
        ):
            http.side_effect = HTTPError(
                "http://wa-akg-teste:3000/api/messages/qa/media", 500,
                "Internal Server Error", {},
                BytesIO(
                    b'{"status":false,"message":"Falha no envio de midia '
                    b'(MEDIA_SEND_FAILED).","error":"MEDIA_SEND_FAILED"}'
                ),
            )
            with self.assertRaisesRegex(
                WhatsAppGatewayError, "MEDIA_SEND_FAILED"
            ) as ctx:
                enviar_documento(
                    "5538999991111@s.whatsapp.net", b"%PDF-1.4",
                    "boletim-sintetico.pdf", sessao_id="sessao-qa",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(http.call_count, 1)
