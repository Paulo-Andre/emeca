"""Exibe erros de envios já existentes, sem transmitir boletins."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from site_publico.models import AlunoBoletim, BoletimAluno, PeriodoBoletim
from usuarioSec.models import (
    EnvioBoletimWhatsApp,
    ItemEnvioBoletimWhatsApp,
    declaracao,
)


class HistoricoFalhasWhatsAppTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="qa-historico-whatsapp", email="qa@example.test",
            password="senha-de-teste-ficticia",
        )
        self.client.force_login(self.usuario)
        registro = declaracao.objects.create(nomeDoAluno="ALUNO FICTICIO QA")
        periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=2, ano=2026,
            turma="1º QA", publicado=True,
        )
        aluno = AlunoBoletim.objects.create(
            nome="ALUNO FICTICIO QA", declaracao=registro,
        )
        boletim = BoletimAluno.objects.create(
            periodo=periodo, aluno=aluno, faltas_totais=0,
        )
        self.envio = EnvioBoletimWhatsApp.objects.create(
            usuario=self.usuario, sessao="emeca-qa-historico",
            tipo_periodo="TRIMESTRE", numero_periodo=2, ano=2026,
            modo="individual", total=1, enviados=0, falhas=1,
            status="COM_ERROS",
        )
        self.item = ItemEnvioBoletimWhatsApp.objects.create(
            envio=self.envio, boletim=boletim,
            jid="5538999991111@s.whatsapp.net",
            status="ERRO", erro="MEDIA_SEND_FAILED (etapa SEND)",
        )

    def test_mostra_erro_existente_sem_novo_disparo(self):
        with (
            patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False),
            patch("usuarioSec.whatsapp_views.sessao_atual_id",
                  return_value="emeca-qa-historico"),
            patch("usuarioSec.whatsapp_views.limpeza_historico_pendente",
                  return_value=False),
            patch("usuarioSec.management.commands.processar_envios_whatsapp.enviar_documento") as enviar,
        ):
            response = self.client.get(reverse("whatsapp"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Motivo da falha:")
        self.assertContains(response, "MEDIA_SEND_FAILED (etapa SEND)")
        enviar.assert_not_called()

    def test_nao_executa_html_presente_em_erro(self):
        self.item.erro = "<script>alert(1)</script>"
        self.item.save(update_fields=["erro"])
        with (
            patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False),
            patch("usuarioSec.whatsapp_views.sessao_atual_id",
                  return_value="emeca-qa-historico"),
            patch("usuarioSec.whatsapp_views.limpeza_historico_pendente",
                  return_value=False),
        ):
            response = self.client.get(reverse("whatsapp"))
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_status_data_nulo_do_gateway_nao_derruba_pagina(self):
        # Quando existe limpeza pendente, nem consultar o gateway é seguro.
        with (
            patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True),
            patch("usuarioSec.whatsapp_views.obter_sessao",
                  return_value={"status": True, "data": None}) as obter_sessao,
            patch("usuarioSec.whatsapp_views.limpeza_historico_pendente",
                  return_value=True),
            patch("usuarioSec.management.commands.processar_envios_whatsapp.enviar_documento") as enviar,
            patch("usuarioSec.whatsapp_views.excluir_historico_sessao") as limpar,
        ):
            response = self.client.get(reverse("whatsapp"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LIMPEZA_PENDENTE")
        obter_sessao.assert_not_called()
        enviar.assert_not_called()
        limpar.assert_not_called()

    def test_status_sessao_invalida_nao_derruba_pagina(self):
        with (
            patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True),
            patch("usuarioSec.whatsapp_views.obter_sessao", return_value=[]),
            patch("usuarioSec.management.commands.processar_envios_whatsapp.enviar_documento") as enviar,
        ):
            response = self.client.get(reverse("whatsapp"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WA-AKG indisponível")
        enviar.assert_not_called()

    def test_tela_envios_abre_quando_gateway_retorna_data_nulo(self):
        # Após uma limpeza parcial, a API pode responder 200 com data:null.
        # O usuário deve continuar vendo a tela e os avisos, não HTTP 500.
        with (
            patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True),
            patch("usuarioSec.whatsapp_views.obter_sessao",
                  return_value={"status": True, "data": None}),
            patch("usuarioSec.whatsapp_views.sessao_atual_id",
                  return_value="emeca-qa-historico"),
            patch("usuarioSec.whatsapp_views.limpeza_historico_pendente",
                  return_value=True),
        ):
            response = self.client.get(reverse("whatsapp"))
        self.assertEqual(response.status_code, 200)

    def test_tela_envios_abre_quando_gateway_retorna_resposta_invalida(self):
        with (
            patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True),
            patch("usuarioSec.whatsapp_views.obter_sessao", return_value=None),
            patch("usuarioSec.whatsapp_views.sessao_atual_id",
                  return_value="emeca-qa-historico"),
            patch("usuarioSec.whatsapp_views.limpeza_historico_pendente",
                  return_value=True),
        ):
            response = self.client.get(reverse("whatsapp"))
        self.assertEqual(response.status_code, 200)

    def test_timeout_de_gateway_e_tratado_sem_500(self):
        from django.test import override_settings

        with (
            override_settings(
                WA_AKG_BASE_URL="http://127.0.0.1:3100",
                WA_AKG_API_KEY="credencial-sintetica-apenas-teste",
                WA_AKG_SESSION_ID="emeca-qa-historico",
                WA_AKG_TIMEOUT_SECONDS=2,
            ),
            patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True),
            patch("usuarioSec.whatsapp_gateway.urlopen",
                  side_effect=TimeoutError("tempo esgotado")),
            patch("usuarioSec.whatsapp_views.limpeza_historico_pendente",
                  return_value=False),
            patch("usuarioSec.management.commands.processar_envios_whatsapp.enviar_documento") as enviar,
            patch("usuarioSec.whatsapp_views.excluir_historico_sessao") as limpar,
        ):
            response = self.client.get(reverse("whatsapp"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WA-AKG indisponível")
        enviar.assert_not_called()
        limpar.assert_not_called()
