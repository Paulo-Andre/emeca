"""Teste de caixa branca da seleção de 620 famílias SEM disparar WhatsApp.

Apenas contatos sintéticos e banco SQLite de teste, nenhuma chamada externa.
"""
from django.test import TestCase

from .models import TelefoneDeclaracao, declaracao
from .whatsapp_views import _resolver_destinatarios


class LoteContatosSinteticosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        alunos = declaracao.objects.bulk_create(
            [
                declaracao(
                    nomeDoAluno=f"ESTUDANTE FICTICIO {i:04d}",
                    turmaDoAluno=("1º A" if i < 310 else "1º B"),
                )
                for i in range(620)
            ]
        )
        telefones = [
            TelefoneDeclaracao(
                declaracao=aluno, tipo="MAE",
                telefone=f"(38) 9{i:08d}",
            )
            for i, aluno in enumerate(alunos)
        ]
        # 20 responsáveis compartilham o número da mãe cadastrada;
        # cada telefone deve receber só uma mensagem, sem duplicação.
        telefones += [
            TelefoneDeclaracao(
                declaracao=alunos[i], tipo="RESPONSAVEL",
                telefone=f"(38) 9{i:08d}",
            )
            for i in range(20)
        ]
        telefones += [
            TelefoneDeclaracao(
                declaracao=alunos[i + 20], tipo="PAI",
                telefone="sem telefone",
            )
            for i in range(3)
        ]
        TelefoneDeclaracao.objects.bulk_create(telefones)

    def test_todos_620_contatos_unicos_sem_envios(self):
        with self.assertNumQueries(1):
            jids, invalidos, amostra = _resolver_destinatarios("todos")
        self.assertEqual(len(jids), 620)
        self.assertEqual(len(set(jids)), 620)
        self.assertEqual(invalidos, 3)
        self.assertEqual(len(amostra), 8)
        self.assertTrue(all("••••" in item["telefone"] for item in amostra))

    def test_filtrar_uma_turma_nao_envia_para_a_outra(self):
        with self.assertNumQueries(1):
            jids, invalidos, amostra = _resolver_destinatarios(
                "turma", turma="1º A",
            )
        self.assertEqual(len(jids), 310)
        self.assertEqual(invalidos, 3)
        self.assertEqual(len(amostra), 8)

    def test_selecao_apenas_mae_nao_inclui_outros_contatos(self):
        jids, invalidos, _ = _resolver_destinatarios("todos", tipos=["MAE"])
        self.assertEqual(len(jids), 620)
        self.assertEqual(invalidos, 0)
