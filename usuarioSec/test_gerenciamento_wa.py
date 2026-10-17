"""Regressões do gerenciamento de etiquetas e grupos da Secretaria EMECA."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import EtiquetaConversaWhatsApp, GrupoOcultoWhatsApp
from .sessao_whatsapp import criar_sessao_isolada, sessao_atual_id
from .whatsapp_gateway import WhatsAppGatewayError


@override_settings(WA_AKG_SESSION_ID="sessao-escola-teste")
class GerenciamentoWhatsAppTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="gerente_wa", password="SenhaFicticia123"
        )
        self.client.force_login(self.admin)
        self.url = reverse("whatsapp_gerenciamento")
        self.grupo_jid = "120363012345678901@g.us"
        self.grupo = {
            "jid": self.grupo_jid, "subject": "Pais do 5º Ano", "size": 32
        }

    def _post(self, action, **extra):
        return self.client.post(
            self.url,
            {"acao": action, "wa_session_id": sessao_atual_id(), **extra}
        )

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    def test_paleta_mostra_as_20_cores_e_usa_radio_estavel(self, _gateway):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="wa-color-choice"', count=20)
        self.assertContains(response, 'type="radio" name="cor"', count=20)
        self.assertContains(response, '#9400D3')
        self.assertContains(response, "Roxo")
        self.assertNotContains(response, "<option value=\"0\">Cor 1</option>")

    @patch("usuarioSec.whatsapp_views.criar_etiqueta", return_value={"status": True})
    def test_criacao_transmite_cor_escolhida_ao_gateway(self, criar):
        response = self._post("criar_etiqueta", nome="Urgente", cor="6")
        self.assertEqual(response.status_code, 302)
        criar.assert_called_once_with("Urgente", 6)

    @patch("usuarioSec.whatsapp_views.criar_etiqueta")
    def test_cor_invalida_nao_e_enviada_ao_gateway(self, criar):
        response = self._post("criar_etiqueta", nome="Urgente", cor="22")
        self.assertEqual(response.status_code, 302)
        criar.assert_not_called()

    @patch("usuarioSec.whatsapp_views.apagar_etiqueta", return_value={"status": True})
    def test_excluir_etiqueta_remove_associacoes_locais_sem_apagar_mensagens(self, apagar):
        EtiquetaConversaWhatsApp.objects.create(
            sessao=sessao_atual_id(), jid="5538999990000@s.whatsapp.net",
            etiqueta_id="label_123", nome="Urgente", cor="#FF0000"
        )
        response = self._post(
            "apagar_etiqueta", id="label_123", confirmacao="EXCLUIR"
        )
        self.assertEqual(response.status_code, 302)
        apagar.assert_called_once_with("label_123")
        self.assertFalse(EtiquetaConversaWhatsApp.objects.exists())

    @patch("usuarioSec.whatsapp_views.apagar_etiqueta")
    def test_etiqueta_exige_confirmacao(self, apagar):
        response = self._post("apagar_etiqueta", id="label_123")
        self.assertEqual(response.status_code, 302)
        apagar.assert_not_called()

    @patch("usuarioSec.whatsapp_views.apagar_etiqueta")
    def test_falha_exclusao_remota_preserva_etiqueta(self, apagar):
        EtiquetaConversaWhatsApp.objects.create(
            sessao=sessao_atual_id(), jid="5538999990000@s.whatsapp.net",
            etiqueta_id="label_123", nome="Urgente", cor="#FF0000"
        )
        apagar.side_effect = WhatsAppGatewayError("Erro remoto", 500)
        self._post("apagar_etiqueta", id="label_123", confirmacao="EXCLUIR")
        self.assertEqual(EtiquetaConversaWhatsApp.objects.count(), 1)

    @patch("usuarioSec.whatsapp_views.listar_grupos")
    @patch("usuarioSec.whatsapp_views.sair_grupo", return_value={"status": True})
    def test_sair_grupo_real_depois_oculta_registro_local(self, sair, listar):
        listar.return_value = {"status": True, "data": [self.grupo]}
        response = self._post(
            "sair_grupo", jid=self.grupo_jid, confirmacao="SAIR"
        )
        self.assertEqual(response.status_code, 302)
        sair.assert_called_once_with(self.grupo_jid)
        self.assertEqual(
            GrupoOcultoWhatsApp.objects.get(jid=self.grupo_jid).motivo, "SAIU"
        )

    @patch("usuarioSec.whatsapp_views.listar_grupos")
    @patch("usuarioSec.whatsapp_views.sair_grupo")
    def test_remover_grupo_nao_envia_logout_ou_group_leave(self, sair, listar):
        listar.return_value = {"status": True, "data": [self.grupo]}
        response = self._post(
            "remover_grupo", jid=self.grupo_jid, confirmacao="REMOVER"
        )
        self.assertEqual(response.status_code, 302)
        sair.assert_not_called()
        self.assertEqual(
            GrupoOcultoWhatsApp.objects.get(jid=self.grupo_jid).motivo, "REMOVIDO"
        )

    @patch("usuarioSec.whatsapp_views.listar_grupos")
    @patch("usuarioSec.whatsapp_views.sair_grupo")
    def test_grupo_nao_cadastrado_na_conta_atual_nao_e_alterado(self, sair, listar):
        listar.return_value = {"status": True, "data": []}
        self._post("sair_grupo", jid=self.grupo_jid, confirmacao="SAIR")
        sair.assert_not_called()
        self.assertFalse(GrupoOcultoWhatsApp.objects.exists())

    @patch("usuarioSec.whatsapp_views.listar_grupos")
    @patch("usuarioSec.whatsapp_views.sair_grupo")
    def test_saida_remota_falhou_entao_grupo_permanece_na_lista(self, sair, listar):
        listar.return_value = {"status": True, "data": [self.grupo]}
        sair.side_effect = WhatsAppGatewayError("Sem permissão de saída", 500)
        self._post("sair_grupo", jid=self.grupo_jid, confirmacao="SAIR")
        self.assertFalse(GrupoOcultoWhatsApp.objects.exists())

    @patch("usuarioSec.whatsapp_views.sair_grupo")
    @patch("usuarioSec.whatsapp_views.listar_grupos")
    def test_confirmacao_e_validacao_jid_impedem_saida_acidental(self, listar, sair):
        self._post("sair_grupo", jid=self.grupo_jid)
        self._post("sair_grupo", jid="https://example.invalid", confirmacao="SAIR")
        listar.assert_not_called()
        sair.assert_not_called()

    @patch("usuarioSec.whatsapp_views.listar_grupos",
           return_value={"status": True, "data": []})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"status": True, "data": {"status": "CONNECTED"}})
    def test_grupo_removido_nao_aparece_novamente_no_gerenciamento(
        self, _sessao, _gateway, listar
    ):
        GrupoOcultoWhatsApp.objects.create(
            sessao=sessao_atual_id(), jid=self.grupo_jid
        )
        listar.return_value = {"status": True, "data": [self.grupo]}
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.grupo["subject"])

    @patch("usuarioSec.whatsapp_views.apagar_etiqueta")
    @patch("usuarioSec.whatsapp_views.sair_grupo")
    def test_usuario_comum_nao_pode_excluir_ou_sair(self, sair, apagar):
        comum = get_user_model().objects.create_user(
            username="secretario_comum", password="SenhaTeste123"
        )
        self.client.force_login(comum)
        self.assertEqual(self._post(
            "sair_grupo", jid=self.grupo_jid, confirmacao="SAIR"
        ).status_code, 403)
        self.assertEqual(self._post(
            "apagar_etiqueta", id="label_123", confirmacao="EXCLUIR"
        ).status_code, 403)
        sair.assert_not_called()
        apagar.assert_not_called()

    def test_remover_grupo_oculta_tambem_na_lista_de_conversas(self):
        from .whatsapp_views import _filtrar_conversas_excluidas_wa
        grupo = {
            "jid": self.grupo_jid,
            "aliases": [self.grupo_jid],
            "lastMessage": {"timestamp": "2026-10-17T15:00:00Z"}
        }
        GrupoOcultoWhatsApp.objects.create(
            sessao=sessao_atual_id(), jid=self.grupo_jid
        )
        self.assertEqual(
            _filtrar_conversas_excluidas_wa(self.admin, [grupo]), []
        )
        self.assertEqual(
            _filtrar_conversas_excluidas_wa(self.admin, [{
                "jid": "5538999990000@s.whatsapp.net",
                "aliases": ["5538999990000@s.whatsapp.net"],
                "lastMessage": {"timestamp": "2026-10-17T15:00:00Z"},
            }])[0]["jid"],
            "5538999990000@s.whatsapp.net"
        )

    @patch("usuarioSec.whatsapp_gateway._request",
           return_value={"status": True})
    def test_gateway_usa_apis_de_etiqueta_e_grupo_correta(self, chamada):
        from .whatsapp_gateway import apagar_etiqueta, sair_grupo
        apagar_etiqueta("label-1")
        self.assertEqual(chamada.call_args.args[:2], (
            "DELETE", "labels/sessao-escola-teste/label-1"
        ))
        sair_grupo(self.grupo_jid)
        self.assertEqual(chamada.call_args.args[:2], (
            "POST", "groups/sessao-escola-teste/" + self.grupo_jid + "/leave"
        ))

    @patch("usuarioSec.whatsapp_views.listar_grupos")
    @patch("usuarioSec.whatsapp_views.sair_grupo", return_value={"status": True})
    def test_grupos_de_conta_anterior_nao_ficam_ocultos_em_nova_conta(
        self, _sair, listar
    ):
        listar.return_value = {"status": True, "data": [self.grupo]}
        self._post("sair_grupo", jid=self.grupo_jid, confirmacao="SAIR")
        criar_sessao_isolada()
        self.assertFalse(GrupoOcultoWhatsApp.objects.filter(
            sessao=sessao_atual_id()
        ).exists())
