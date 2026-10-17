"""Regressões: duas contas WhatsApp jamais dividem sessão, leituras ou JIDs.

Os dados são fictícios. Não usa rede real nem faz logout em produção.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    EstadoConversaWhatsApp,
    IdentidadeContatoWhatsApp,
    LeituraChatWhatsApp,
    SessaoWhatsAppAtiva,
)
from .sessao_whatsapp import criar_sessao_isolada, sessao_atual_id
from .whatsapp_gateway import listar_chats, obter_sessao
from .whatsapp_views import _enriquecer_chats, _sincronizar_nao_lidas


@override_settings(WA_AKG_SESSION_ID="emeca-legado")
class IsolamentoContasWhatsAppTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="admin_troca_whatsapp",
            password="senha-ficticia",
            is_superuser=True,
        )
        self.client.force_login(self.admin)
        self.jid = "5538999990011@s.whatsapp.net"

    def test_nova_sessao_nao_reutiliza_legacy_e_preserva_mapeamento_antigo(self):
        IdentidadeContatoWhatsApp.objects.create(
            sessao="emeca-legado", jid="1234567890@lid",
            telefone_jid=self.jid, nome_exibicao="Contato da conta antiga",
        )
        EstadoConversaWhatsApp.objects.create(
            sessao="emeca-legado", jid=self.jid, arquivado=True
        )
        self.assertEqual(sessao_atual_id(), "emeca-legado")
        sessao = criar_sessao_isolada()
        self.assertEqual(sessao["anterior"], "emeca-legado")
        self.assertNotEqual(sessao["atual"], "emeca-legado")
        self.assertTrue(sessao_atual_id().startswith("emeca-"))
        self.assertEqual(
            IdentidadeContatoWhatsApp.objects.get(
                sessao="emeca-legado", jid="1234567890@lid"
            ).nome_exibicao,
            "Contato da conta antiga",
        )
        self.assertFalse(IdentidadeContatoWhatsApp.objects.filter(
            sessao=sessao_atual_id()
        ).exists())
        self.assertFalse(EstadoConversaWhatsApp.objects.filter(
            sessao=sessao_atual_id(), arquivado=True
        ).exists())

    def test_cada_troca_cria_id_novo_e_arquivo_antigo_permanece(self):
        ids = ["emeca-legado"]
        for _ in range(3):
            ids.append(criar_sessao_isolada()["atual"])
        self.assertEqual(len(ids), len(set(ids)))

    @patch("usuarioSec.whatsapp_gateway._request")
    def test_gateway_usa_id_ativo_nao_o_id_da_conta_antiga(self, requisicao):
        requisicao.return_value = {"status": True, "data": []}
        listar_chats()
        self.assertIn("emeca-legado", requisicao.call_args.args[1])
        novo = criar_sessao_isolada()["atual"]
        listar_chats()
        self.assertIn(novo, requisicao.call_args.args[1])
        self.assertNotIn("emeca-legado", requisicao.call_args.args[1])
        obter_sessao()
        self.assertIn(novo, requisicao.call_args.args[1])

    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_nomes_e_estados_da_sessao_anterior_nao_aparecem_na_nova(self, _contatos):
        IdentidadeContatoWhatsApp.objects.create(
            sessao="emeca-legado", jid=self.jid,
            nome_exibicao="Funcionário da conta anterior",
            origem="MANUAL",
        )
        EstadoConversaWhatsApp.objects.create(
            sessao="emeca-legado", jid=self.jid, fixado=True
        )
        origem = [{"jid": self.jid, "lastMessage": {
            "timestamp": "2026-10-17T12:00:00Z", "content": "exemplo"
        }}]
        antigos = _enriquecer_chats(origem)
        self.assertEqual(antigos[0]["name"], "Funcionário da conta anterior")
        self.assertTrue(antigos[0]["fixado"])
        criar_sessao_isolada()
        novos = _enriquecer_chats(origem)
        self.assertNotEqual(novos[0]["name"], "Funcionário da conta anterior")
        self.assertFalse(novos[0]["fixado"])

    def test_nao_lidas_separadas_mesmo_usuario_e_mesmo_contato(self):
        LeituraChatWhatsApp.objects.create(
            usuario=self.admin, sessao="emeca-legado",
            jid=self.jid, nao_lidas=6
        )
        criar_sessao_isolada()
        chats = [{"jid": self.jid, "aliases": [self.jid],
                  "lastMessage": {"timestamp": "2026-10-17T15:00:00Z"}}]
        result = _sincronizar_nao_lidas(self.admin, chats)
        self.assertEqual(result[0]["naoLidas"], 0)
        self.assertEqual(LeituraChatWhatsApp.objects.count(), 2)
        self.assertEqual(LeituraChatWhatsApp.objects.get(
            sessao="emeca-legado"
        ).nao_lidas, 6)

    @patch("usuarioSec.whatsapp_views.excluir_historico_sessao",
           return_value={"status": True, "data": {"messages": 2}})
    @patch("usuarioSec.whatsapp_views.desvincular_sessao",
           return_value={"status": True})
    @patch("usuarioSec.whatsapp_views.obter_sessao",
           return_value={"data": {"status": "CONNECTED"}})
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_acao_isolar_desvincula_e_cria_sessao_nova(
        self, _configurado, _sessao, logout, apagar
    ):
        response = self.client.post(reverse("whatsapp_desconectar"), {
            "acao": "isolar", "confirmacao": "ISOLAR",
            "confirmar_exclusao": "APAGAR_HISTORICO",
        })
        self.assertEqual(response.status_code, 302)
        logout.assert_called_once_with()
        apagar.assert_called_once_with("emeca-legado")
        self.assertNotEqual(sessao_atual_id(), "emeca-legado")

    @patch("usuarioSec.whatsapp_views.desvincular_sessao")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_sem_confirmacao_nao_muda_sessao(self, _config, logout):
        self.client.post(reverse("whatsapp_desconectar"), {
            "acao": "isolar",
        })
        self.assertEqual(sessao_atual_id(), "emeca-legado")
        logout.assert_not_called()

    @patch("usuarioSec.whatsapp_views.enviar_mensagem_chat")
    def test_aba_antiga_nao_pode_enviar_na_sessao_nova(self, enviar):
        criar_sessao_isolada()
        response = self.client.post(
            reverse("whatsapp_responder_api"),
            {"jid": self.jid, "mensagem": "Texto fictício"},
            HTTP_X_EMECA_WA_SESSION="emeca-legado",
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["sessao_alterada"])
        enviar.assert_not_called()

    @patch("usuarioSec.whatsapp_views.listar_chats")
    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=True)
    def test_aba_antiga_nao_acessa_chats_de_nova_conta(
        self, _config, listar
    ):
        criar_sessao_isolada()
        resposta = self.client.get(
            reverse("whatsapp_chats_api"),
            HTTP_X_EMECA_WA_SESSION="emeca-legado",
        )
        self.assertEqual(resposta.status_code, 409)
        listar.assert_not_called()

    @patch("usuarioSec.whatsapp_views.enviar_broadcast")
    @patch("usuarioSec.whatsapp_views.enviar_mensagem_chat")
    def test_formulario_antigo_nao_pode_enviar_campanhas(
        self, enviar, broadcast
    ):
        criar_sessao_isolada()
        resposta = self.client.post(reverse("whatsapp_enviar"), {
            "wa_session_id": "emeca-legado",
            "mensagem": "Texto fictício",
            "modo": "todos",
        })
        self.assertEqual(resposta.status_code, 302)
        enviar.assert_not_called()
        broadcast.assert_not_called()

    def test_lote_antigo_nao_e_processado_na_conta_nova(self):
        from .models import EnvioBoletimWhatsApp
        from .management.commands.processar_envios_whatsapp import claim_proximo_lote
        antigo = EnvioBoletimWhatsApp.objects.create(
            tipo_periodo="TRIMESTRE", numero_periodo=1, ano=2026,
            modo="todos", sessao="emeca-legado", status="PENDENTE",
        )
        criar_sessao_isolada()
        self.assertIsNone(claim_proximo_lote())
        antigo.refresh_from_db()
        self.assertEqual(antigo.status, "PENDENTE")
        novo = EnvioBoletimWhatsApp.objects.create(
            tipo_periodo="TRIMESTRE", numero_periodo=1, ano=2026,
            modo="todos", sessao=sessao_atual_id(), status="PENDENTE",
        )
        self.assertEqual(claim_proximo_lote().pk, novo.pk)

    @patch("usuarioSec.whatsapp_gateway._request_multipart")
    def test_pdf_da_fila_utiliza_sessao_original(self, request):
        from .whatsapp_gateway import enviar_documento
        request.return_value = {"status": True}
        criar_sessao_isolada()
        enviar_documento(
            self.jid, b"%PDF-1.4 exemplo", "teste.pdf",
            sessao_id="emeca-legado"
        )
        self.assertIn("emeca-legado", request.call_args.args[0])
        self.assertNotIn(sessao_atual_id(), request.call_args.args[0])
