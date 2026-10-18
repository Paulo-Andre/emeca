"""Regressões: HTTP 200 do gateway não implica mensagem realmente aceita.

Sem rede ou chamadas reais ao WhatsApp.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse


class RespostaNegativaDoGatewayTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="qa-gateway",
            email="qa-gateway@example.invalid",
            password="SenhaSinteticaSegura!2026",
        )
        self.client.force_login(self.usuario)
        self.jid = "5538999991111@s.whatsapp.net"

    @patch(
        "usuarioSec.whatsapp_views.enviar_mensagem_chat",
        return_value={"status": False, "message": "rejeitado"},
    )
    def test_resposta_negativa_na_mensagem_de_chat(self, enviar):
        resposta = self.client.post(
            reverse("whatsapp_responder_api"),
            {"jid": self.jid, "mensagem": "QA sintético"},
        )
        self.assertEqual(resposta.status_code, 502)
        self.assertFalse(resposta.json()["ok"])
        enviar.assert_called_once()

    @patch(
        "usuarioSec.whatsapp_views.enviar_mensagem_chat",
        return_value={"success": False, "error": "rejeitado"},
    )
    def test_resposta_negativa_em_nova_conversa(self, enviar):
        resposta = self.client.post(
            reverse("whatsapp_nova_conversa_api"),
            {"jid": self.jid, "mensagem": "QA sintético"},
        )
        self.assertEqual(resposta.status_code, 502)
        self.assertFalse(resposta.json()["ok"])
        enviar.assert_called_once()

    @patch(
        "usuarioSec.whatsapp_views.enviar_midia",
        return_value={"status": False, "message": "sem sessão"},
    )
    def test_resposta_negativa_em_anexo(self, enviar):
        arquivo = SimpleUploadedFile(
            "arquivo-qa.pdf", b"%PDF-1.4 sintético", content_type="application/pdf",
        )
        resposta = self.client.post(
            reverse("whatsapp_enviar_midia_api"),
            {"jid": self.jid, "legenda": "QA", "arquivo": arquivo},
        )
        self.assertEqual(resposta.status_code, 502)
        self.assertFalse(resposta.json()["ok"])
        enviar.assert_called_once()

    @patch(
        "usuarioSec.whatsapp_views.enviar_midia",
        return_value={"success": False},
    )
    def test_resposta_negativa_em_nova_conversa_com_documento(self, enviar):
        arquivo = SimpleUploadedFile(
            "arquivo-qa.pdf", b"%PDF-1.4 sintético", content_type="application/pdf",
        )
        resposta = self.client.post(
            reverse("whatsapp_nova_conversa_api"),
            {"jid": self.jid, "mensagem": "QA", "arquivo": arquivo},
        )
        self.assertEqual(resposta.status_code, 502)
        self.assertFalse(resposta.json()["ok"])
        enviar.assert_called_once()

    @patch(
        "usuarioSec.whatsapp_views.enviar_broadcast",
        return_value={"status": False, "message": "não iniciado"},
    )
    @patch("usuarioSec.whatsapp_views._resolver_destinatarios")
    def test_broadcast_rejeitado_nao_vira_mensagem_de_sucesso(
        self, resolver, enviar,
    ):
        resolver.return_value = (
            [self.jid, "5538999992222@s.whatsapp.net"], 0, [],
        )
        resposta = self.client.post(
            reverse("whatsapp_enviar"),
            {"modo": "todos", "mensagem": "QA sintético"},
        )
        self.assertEqual(resposta.status_code, 302)
        avisos = [str(msg) for msg in resposta.wsgi_request._messages]
        self.assertTrue(any("Falha ao enviar" in aviso for aviso in avisos), avisos)
        self.assertFalse(any("Envio iniciado" in aviso for aviso in avisos))
        enviar.assert_called_once()
