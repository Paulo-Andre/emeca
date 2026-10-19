"""Testes de segurança do fluxo web de atualização de CPFs."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from io import StringIO

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from usuarioSec.importacao_cpfs_web import CHAVE


@override_settings(EMECA_RBAC_STRICT=False)
class FluxoCPFsWebTestes(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin_cpfs_ficticio", email="admin@test.invalid", password="senha-teste"
        )
        self.client.force_login(self.user)
        self.pasta = TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.patcher = patch("usuarioSec.importacao_cpfs_web.PASTA", Path(self.pasta.name))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_formulario_existente_exibe_dois_modos(self):
        resposta = self.client.get(reverse("importar_alunos"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Atualizar CPFs das declarações existentes")
        self.assertContains(resposta, "Importar novas declarações")

    def test_nao_aceita_arquivo_de_formato_errado(self):
        resp = self.client.post(reverse("importar_cpfs"), {
            "acao": "previsualizar",
            "arquivo": SimpleUploadedFile("malicioso.txt", b"teste"),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn(CHAVE, self.client.session)

    def test_confirmacao_sem_previa_nao_aplica(self):
        with patch("usuarioSec.importacao_cpfs_web.call_command") as cmd:
            resp = self.client.post(reverse("importar_cpfs"), {"acao": "confirmar"})
        self.assertEqual(resp.status_code, 302)
        cmd.assert_not_called()

    def test_previa_confirmacao_com_hash_e_cancelamento(self):
        plano = "a" * 64
        def simular(*args, **kwargs):
            destino = kwargs["stdout"]
            if kwargs.get("aplicar"):
                destino.write("CONCLUÍDO: 1 Declarações atualizadas.\n")
            else:
                destino.write(
                    "cadastros_atualizaveis: 1\n"
                    "campo_cpfMae: 1\n"
                    f"plano_id: {plano}\n"
                )
        with patch("usuarioSec.importacao_cpfs_web.call_command", side_effect=simular) as cmd:
            r = self.client.post(reverse("importar_cpfs"), {
                "acao": "previsualizar",
                "arquivo": SimpleUploadedFile("teste.xls", b"planilha-ficticia"),
            })
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "Confirmar atualização com backup")
            self.assertIn(CHAVE, self.client.session)
            r = self.client.post(reverse("importar_cpfs"), {"acao": "confirmar"})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(cmd.call_count, 2)
            self.assertTrue(cmd.call_args.kwargs["aplicar"])
            self.assertEqual(cmd.call_args.kwargs["plano_id"], plano)
            self.assertNotIn(CHAVE, self.client.session)
            self.assertEqual(list(Path(self.pasta.name).iterdir()), [])

    def test_cancelar_previa_nao_aplica(self):
        self.client.post(reverse("importar_cpfs"), {"acao": "cancelar"})
        self.assertNotIn(CHAVE, self.client.session)

    def test_usuario_nao_autenticado_bloqueado(self):
        self.client.logout()
        r = self.client.post(reverse("importar_cpfs"), {"acao": "confirmar"})
        self.assertEqual(r.status_code, 403)
