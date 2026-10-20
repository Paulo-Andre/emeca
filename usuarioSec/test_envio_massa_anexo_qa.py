"""QA sintético de campanhas de mídia; nenhum envio para números reais."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from usuarioSec.access_control import GRUPO_WHATSAPP
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse


class CampanhaComAnexoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="qa-campanha-arquivos", password="senha-de-teste-ficticia"
        )
        # O middleware exige o perfil do módulo, inclusive na base de testes.
        # Não desligar RBAC nem elevar o usuário a superadministrador.
        grupo, _ = Group.objects.get_or_create(name=GRUPO_WHATSAPP)
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)

    def test_sem_perfil_whatsapp_o_acesso_continua_proibido(self):
        self.usuario.groups.clear()
        resposta = self.client.post(reverse("whatsapp_enviar"), {
            "conteudo": "mensagem", "modo": "todos", "mensagem": "QA",
        })
        self.assertEqual(resposta.status_code, 403)

    def test_mensagem_em_massa_pode_conter_pdf_sem_legenda(self):
        arquivo = SimpleUploadedFile(
            "informativo.pdf", b"%PDF-1.4\nSOMENTE TESTE\n%%EOF\n",
            content_type="application/pdf",
        )
        mod = "usuarioSec.whatsapp_views"
        with (
            patch(f"{mod}._validar_sessao_cliente", return_value=None),
            patch(f"{mod}._resolver_destinatarios", return_value=(
                ["5538999991111@s.whatsapp.net", "5538999992222@s.whatsapp.net"], 0, [],
            )),
            patch(f"{mod}.enviar_broadcast_midia", return_value={
                "status": True, "data": {"broadcastId": "lote-ficticio"},
            }) as midia,
            patch(f"{mod}.enviar_broadcast") as texto,
        ):
            resposta = self.client.post(reverse("whatsapp_enviar"), {
                "conteudo": "mensagem", "modo": "todos", "mensagem": "",
                "anexo": arquivo,
            })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(midia.call_count, 1)
        self.assertEqual(midia.call_args.args[0][0], "5538999991111@s.whatsapp.net")
        self.assertEqual(midia.call_args.args[1], "")
        self.assertEqual(midia.call_args.args[2], b"%PDF-1.4\nSOMENTE TESTE\n%%EOF\n")
        self.assertEqual(midia.call_args.args[4], "application/pdf")
        texto.assert_not_called()

    def test_executavel_mascarado_de_pdf_e_recusado_antes_do_gateway(self):
        arquivo = SimpleUploadedFile(
            "enganoso.pdf", b"MZ" + b"X" * 20,
            content_type="application/pdf",
        )
        mod = "usuarioSec.whatsapp_views"
        with (
            patch(f"{mod}._validar_sessao_cliente", return_value=None),
            patch(f"{mod}._resolver_destinatarios") as resolver,
            patch(f"{mod}.enviar_broadcast_midia") as midia,
        ):
            resposta = self.client.post(reverse("whatsapp_enviar"), {
                "conteudo": "mensagem", "modo": "todos",
                "mensagem": "Teste", "anexo": arquivo,
            })
        self.assertEqual(resposta.status_code, 302)
        resolver.assert_not_called()
        midia.assert_not_called()
