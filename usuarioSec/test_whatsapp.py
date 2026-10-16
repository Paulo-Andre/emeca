from django.test import TestCase

from .models import TelefoneDeclaracao, declaracao
from .whatsapp_views import _normalizar_jid, _resolver_destinatarios


class WhatsAppDestinatariosTests(TestCase):
    def setUp(self):
        self.aluna_a = declaracao.objects.create(
            nomeDoAluno="ALUNA A",
            turmaDoAluno="1º A",
        )
        self.aluno_b = declaracao.objects.create(
            nomeDoAluno="ALUNO B",
            turmaDoAluno="2º B",
        )

        self.mae_a = TelefoneDeclaracao.objects.create(
            declaracao=self.aluna_a,
            tipo="MAE",
            telefone="(38) 99999-1111",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=self.aluna_a,
            tipo="PAI",
            telefone="38 98888-2222",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=self.aluno_b,
            tipo="MAE",
            telefone="+55 (38) 99999-1111",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=self.aluno_b,
            tipo="RESPONSAVEL",
            telefone="9999-0000",
        )

    def test_normaliza_numero_brasileiro_para_jid(self):
        self.assertEqual(
            _normalizar_jid("(38) 99999-1111"),
            "5538999991111@s.whatsapp.net",
        )
        self.assertEqual(
            _normalizar_jid("+55 38 98888-2222"),
            "5538988882222@s.whatsapp.net",
        )
        self.assertEqual(
            _normalizar_jid("(55) 99999-1111"),
            "5555999991111@s.whatsapp.net",
        )
        self.assertIsNone(_normalizar_jid("9999-0000"))

    def test_envio_para_todos_remove_duplicados(self):
        destinatarios, invalidos, _ = _resolver_destinatarios("todos")
        self.assertEqual(len(destinatarios), 2)
        self.assertEqual(invalidos, 1)

    def test_envio_por_turma_filtra_alunos(self):
        destinatarios, invalidos, _ = _resolver_destinatarios(
            "turma",
            turma="1º A",
        )
        self.assertEqual(len(destinatarios), 2)
        self.assertEqual(invalidos, 0)

    def test_envio_individual_escolhe_um_contato(self):
        destinatarios, invalidos, _ = _resolver_destinatarios(
            "individual",
            contato_id=self.mae_a.id,
        )
        self.assertEqual(
            destinatarios,
            ["5538999991111@s.whatsapp.net"],
        )
        self.assertEqual(invalidos, 0)

    def test_sem_tipos_selecionados_nao_envia_para_todos(self):
        destinatarios, invalidos, _ = _resolver_destinatarios(
            "todos",
            tipos=[],
        )
        self.assertEqual(destinatarios, [])
        self.assertEqual(invalidos, 0)
