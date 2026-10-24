"""Testes com banco isolado e WhatsApp simulado para turmas de Boletins.

Não transmite mensagens, PDFs, arquivos nem consulta o gateway real.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from site_publico.models import AlunoBoletim, BoletimAluno, PeriodoBoletim
from usuarioSec.models import TelefoneDeclaracao, declaracao
from usuarioSec.whatsapp_gateway import WhatsAppGatewayError
from usuarioSec.whatsapp_views import _resolver_destinatarios

BASE = "usuarioSec.whatsapp_views."
JID_A = "5538999991111@s.whatsapp.net"
JID_B = "5538988882222@s.whatsapp.net"
JID_C = "5538977773333@s.whatsapp.net"
ANTIGO_A = "553899991111@s.whatsapp.net"
ANTIGO_B = "553888882222@s.whatsapp.net"


class TurmasBoletimWhatsAppTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "admin-turmas-boletim", "boletins-teste@example.invalid", "senha-de-teste"
        )
        self.client.force_login(self.usuario)
        self.periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=2, ano=2026, turma="1º Tulipa", publicado=True,
        )
        self.outro = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=3, ano=2026, turma="1º Tulipa", publicado=True,
        )
        self.declaracoes = []
        for indice, (nome, telefone) in enumerate((
            ("ALUNO UM", "(38) 99999-1111"),
            ("ALUNO DOIS", "(38) 98888-2222"),
            ("ALUNO OUTRO PERIODO", "(38) 97777-3333"),
            ("ALUNO SEM BOLETIM", "(38) 96666-4444"),
        )):
            registro = declaracao.objects.create(
                nomeDoAluno=nome, turmaDoAluno="TURMA DIFERENTE",
            )
            TelefoneDeclaracao.objects.create(
                declaracao=registro, tipo="MAE", telefone=telefone,
            )
            self.declaracoes.append(registro)
            aluno = AlunoBoletim.objects.create(nome=nome, declaracao=registro)
            if indice < 2:
                BoletimAluno.objects.create(periodo=self.periodo, aluno=aluno)
            elif indice == 2:
                BoletimAluno.objects.create(periodo=self.outro, aluno=aluno)
        # O mesmo telefone em outro cadastro da turma não deve duplicar o envio.
        registro_irmao = declaracao.objects.create(
            nomeDoAluno="IRMAO", turmaDoAluno="OUTRA TURMA",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=registro_irmao, tipo="PAI",
            telefone="(38) 99999-1111",
        )
        aluno_irmao = AlunoBoletim.objects.create(
            nome="IRMAO", declaracao=registro_irmao,
        )
        BoletimAluno.objects.create(periodo=self.periodo, aluno=aluno_irmao)

    def test_filtra_pelo_periodo_e_vinculo_sem_correspondencia_por_nome(self):
        dados, invalidos, _ = _resolver_destinatarios(
            "turma_boletim", periodo_boletim_id=self.periodo.pk,
        )
        self.assertEqual(set(dados), {JID_A, JID_B})
        self.assertEqual(len(dados), 2)
        self.assertEqual(invalidos, 0)

        outro, _, _ = _resolver_destinatarios(
            "turma_boletim", periodo_boletim_id=self.outro.pk,
        )
        self.assertEqual(outro, [JID_C])

    def test_exige_id_valido_e_nao_abre_todos_por_engano(self):
        for valor in (None, "", "abc", "0", "999999"):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    _resolver_destinatarios(
                        "turma_boletim", periodo_boletim_id=valor,
                    )

    def test_endpoint_preview_e_tela_mostram_apenas_a_turma_escolhida(self):
        with patch(BASE + "gateway_configurado", return_value=False):
            page = self.client.get(reverse("whatsapp"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Turmas do Boletim")
        self.assertContains(page, 'value="turma_boletim"')
        self.assertContains(page, 'id="periodoBoletimId"')
        self.assertContains(page, "1º Tulipa")

        response = self.client.get(
            reverse("whatsapp_destinatarios"),
            {"modo": "turma_boletim", "periodo_boletim_id": self.periodo.pk,
             "tipos": ["MAE", "PAI"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quantidade"], 2)
        self.assertEqual(
            self.client.get(
                reverse("whatsapp_destinatarios"),
                {"modo": "turma_boletim"},
            ).status_code,
            400,
        )

    @patch(BASE + "enviar_broadcast")
    @patch(BASE + "verificar_numeros")
    def test_envia_apenas_jids_confirmados_do_periodo(self, verificar, broadcast):
        def check(numeros):
            self.assertCountEqual(numeros, [JID_A.split("@")[0], JID_B.split("@")[0]])
            return {"status": True, "data": {"results": [
                {"number": JID_A.split("@")[0], "exists": True, "jid": ANTIGO_A},
                {"number": JID_B.split("@")[0], "exists": True, "jid": ANTIGO_B},
            ]}}
        verificar.side_effect = check
        broadcast.return_value = {"status": True, "data": {"broadcastId": "lote-sintetico"}}
        resposta = self.client.post(reverse("whatsapp_enviar"), {
            "conteudo": "mensagem", "modo": "turma_boletim",
            "periodo_boletim_id": str(self.periodo.pk),
            "tipos": ["MAE", "PAI", "RESPONSAVEL"],
            "mensagem": "Comunicado sintético para teste.",
        })
        self.assertEqual(resposta.status_code, 302)
        broadcast.assert_called_once()
        self.assertCountEqual(broadcast.call_args.args[0], [ANTIGO_A, ANTIGO_B])
        self.assertEqual(broadcast.call_args.args[1], "Comunicado sintético para teste.")

    @patch(BASE + "enviar_broadcast")
    @patch(BASE + "verificar_numeros")
    def test_jid_divergente_bloqueia_todo_disparo(self, verificar, broadcast):
        verificar.return_value = {"status": True, "data": {"results": [
            {"number": JID_A.split("@")[0], "exists": True, "jid": ANTIGO_A},
            {"number": JID_B.split("@")[0], "exists": True,
             "jid": "5538977773333@s.whatsapp.net"},
        ]}}
        resposta = self.client.post(reverse("whatsapp_enviar"), {
            "conteudo": "mensagem", "modo": "turma_boletim",
            "periodo_boletim_id": str(self.periodo.pk),
            "tipos": ["MAE"],
            "mensagem": "Teste sem entrega.",
        })
        self.assertEqual(resposta.status_code, 302)
        broadcast.assert_not_called()

    @patch(BASE + "gateway_configurado", return_value=True)
    @patch(BASE + "enviar_documento")
    def test_nova_modalidade_nao_envia_pdf_de_boletim(
        self, enviar_pdf, _gateway,
    ):
        resposta = self.client.post(reverse("whatsapp_enviar"), {
            "conteudo": "boletim",
            "modo": "turma_boletim",
            "periodo_boletim_id": str(self.periodo.pk),
        })
        self.assertEqual(resposta.status_code, 302)
        enviar_pdf.assert_not_called()

    @patch(BASE + "limpeza_historico_pendente", return_value=True)
    @patch(BASE + "enviar_broadcast")
    @patch(BASE + "verificar_numeros")
    def test_limpeza_pendente_bloqueia_envio(
        self, verificar, broadcast, _pendente,
    ):
        resposta = self.client.post(reverse("whatsapp_enviar"), {
            "conteudo": "mensagem",
            "modo": "turma_boletim",
            "periodo_boletim_id": str(self.periodo.pk),
            "tipos": ["MAE"],
            "mensagem": "Teste sem entrega.",
        })
        self.assertEqual(resposta.status_code, 302)
        verificar.assert_not_called()
        broadcast.assert_not_called()

    @patch(BASE + "enviar_broadcast")
    def test_nao_envia_sem_escolher_turma_do_boletim(self, broadcast):
        resposta = self.client.post(reverse("whatsapp_enviar"), {
            "conteudo": "mensagem", "modo": "turma_boletim",
            "tipos": ["MAE"], "mensagem": "Teste sem entrega.",
        })
        self.assertEqual(resposta.status_code, 302)
        broadcast.assert_not_called()
