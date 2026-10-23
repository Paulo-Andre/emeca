"""Painel de envios permanece acessível durante a limpeza incompleta.

Testes locais com gateway simulado; não usam conta nem mensagens reais.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from usuarioSec.models import SessaoWhatsAppAtiva
from usuarioSec.whatsapp_gateway import WhatsAppGatewayError


class PainelLimpezaPendenteTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "admin-painel-teste", "gestor@example.invalid", "senha-local-teste"
        )
        self.client.force_login(self.usuario)

    @patch("usuarioSec.whatsapp_views.obter_sessao")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_painel_sem_consulta_remota_quando_limpeza_pendente(self, _gateway, obter):
        SessaoWhatsAppAtiva.objects.create(
            chave="secretaria", sessao_id="emeca-qa-pendente",
            limpeza_pendente=True,
        )
        resposta = self.client.get(reverse("whatsapp"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "LIMPEZA_PENDENTE")
        obter.assert_not_called()

    @patch("usuarioSec.whatsapp_views.obter_sessao",
           side_effect=WhatsAppGatewayError("Timeout", 0))
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_gateway_lento_nao_retira_painel_do_ar(self, _gateway, _obter):
        resposta = self.client.get(reverse("whatsapp"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "WA-AKG indisponível")
