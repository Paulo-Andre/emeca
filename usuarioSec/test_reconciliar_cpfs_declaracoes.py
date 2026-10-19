"""Cenários fictícios: nunca armazenar CPFs/nome de aluno real no repositório."""
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from usuarioSec.models import declaracao
from usuarioSec.management.commands.reconciliar_cpfs_declaracoes import (
    _cpf_da_celula,
    _cpf_valido,
)


def _gerar_cpf(nove):
    numeros = [int(c) for c in nove]
    for tamanho in (9, 10):
        calculado = (sum(numeros[i] * (tamanho + 1 - i)
                         for i in range(tamanho)) * 10) % 11
        numeros.append(0 if calculado == 10 else calculado)
    return "".join(str(d) for d in numeros)


def _planilha(*, duplicar=False, cpf_invalido=False, nao_identificado=False):
    linhas = [[""] * 31 for _ in range(5 if not duplicar else 6)]
    linhas[0][:4] = ["NOME", "NASCIMENTO", "NATURALIDADE", "TURMA"]
    linhas[0][27:31] = ["CPF DA MÃE", "CPF", "CPF", "CPF DO PAI"]
    linhas[1][:4] = ["CRIANCA DE TESTE", date(2017, 5, 21), "MONTES CLAROS", "1"]
    linhas[1][27] = _gerar_cpf("529982247")
    linhas[1][28] = _gerar_cpf("123456789")
    linhas[1][29] = _gerar_cpf("987654321") if not cpf_invalido else "111.111.111-11"
    linhas[1][30] = _gerar_cpf("888777666")  # Nunca atribuir CPF do pai.
    linhas[2][:4] = ["", date(2017, 5, 21), "MONTES CLAROS", "1"]
    linhas[2][27:30] = [
        _gerar_cpf("222333444"), _gerar_cpf("888888123"), _gerar_cpf("999999123"),
    ]  # Não existe aluno, não importar campos.
    linhas[3][:4] = ["CRIANCA DESCONHECIDA", date(2017, 5, 21), "MG", "1"]
    if nao_identificado:
        linhas[1][1] = None
    if duplicar:
        linhas[5] = list(linhas[1])
    return pd.DataFrame(linhas)


class ReconciliaCPFsTestes(TestCase):
    def setUp(self):
        self.aluno = declaracao.objects.create(
            nomeDoAluno="CRIANCA DE TESTE",
            dataNascimentoAluno=date(2017, 5, 21),
            nomeMae="RESPONSAVEL FICTICIA",
        )

    def _rodar(self, planilha, *, aplicar=False, plano_id=""):
        with TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "declaracoes.xls"
            arquivo.write_bytes(b"planilha-sintetica")
            resultado = StringIO()
            with patch(
                "usuarioSec.management.commands.reconciliar_cpfs_declaracoes.pd.read_excel",
                return_value=planilha,
            ), patch(
                "usuarioSec.management.commands.reconciliar_cpfs_declaracoes._fazer_backup",
                return_value=Path("/backups/teste-sem-dados-reais.sqlite3"),
            ):
                call_command(
                    "reconciliar_cpfs_declaracoes", str(arquivo),
                    stdout=resultado,
                    **({"aplicar": True, "plano_id": plano_id} if aplicar else {}),
                )
            return resultado.getvalue()

    def test_simulacao_nao_muda_nenhum_cadastro(self):
        resultado = self._rodar(_planilha())
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.cpfMae, None if self.aluno.cpfMae is None else "")
        self.assertEqual(self.aluno.cpfResponsavel or "", "")
        self.assertIn("cadastros_atualizaveis: 1", resultado)
        self.assertIn("linhas_sem_nome_ignoradas:", resultado)
        self.assertIn("SIMULAÇÃO CONCLUÍDA", resultado)
        self.assertEqual(declaracao.objects.count(), 1)

    def test_previa_e_aplicacao_com_id_exato(self):
        planilha = _planilha()
        previa = self._rodar(planilha)
        identificador = previa.split("plano_id: ")[1].splitlines()[0]
        resultado = self._rodar(planilha, aplicar=True, plano_id=identificador)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.cpfMae, _cpf_da_celula(_gerar_cpf("529982247"))[0])
        self.assertEqual(
            self.aluno.cpfResponsavel,
            _cpf_da_celula(_gerar_cpf("123456789"))[0],
        )
        self.assertEqual(self.aluno.cpfDoAluno, _cpf_da_celula(_gerar_cpf("987654321"))[0])
        self.assertEqual(self.aluno.cpfPai or "", "")  # AE ignorada.
        self.assertEqual(self.aluno.nomeMae, "RESPONSAVEL FICTICIA")
        self.assertEqual(declaracao.objects.count(), 1)
        self.assertIn("CONCLUÍDO: 1 Declarações", resultado)

    def test_plano_incorreto_impede_escrita(self):
        with self.assertRaises(CommandError):
            self._rodar(_planilha(), aplicar=True, plano_id="a" * 64)
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.cpfResponsavel)

    def test_cpf_invalido_impede_atualizacao_de_toda_linha(self):
        resultado = self._rodar(_planilha(cpf_invalido=True))
        self.assertIn("cpfs_invalidos: 1", resultado)
        self.assertIn("cadastros_atualizaveis: 0", resultado)

    def test_duplicidade_de_identidade_na_planilha_nao_atualiza(self):
        resultado = self._rodar(_planilha(duplicar=True))
        self.assertIn("identidades_duplicadas_planilha: 1", resultado)
        self.assertIn("cadastros_atualizaveis: 0", resultado)

    def test_duplicidade_de_identidade_no_banco_nao_atualiza(self):
        declaracao.objects.create(
            nomeDoAluno="CRIANCA DE TESTE", dataNascimentoAluno=date(2017, 5, 21),
        )
        resultado = self._rodar(_planilha())
        self.assertIn("identidades_duplicadas_banco: 1", resultado)
        self.assertIn("cadastros_atualizaveis: 0", resultado)

    def test_sem_nascimento_nao_importa_identidade_por_nome(self):
        resultado = self._rodar(_planilha(nao_identificado=True))
        self.assertIn("linhas_sem_nascimento: 1", resultado)
        self.assertIn("cadastros_atualizaveis: 0", resultado)

    def test_cpf_repetido_e_invalido(self):
        self.assertFalse(_cpf_valido("11111111111"))
        self.assertTrue(_cpf_valido(_gerar_cpf("529982247")))
        self.assertEqual(_cpf_da_celula("111.111.111-11"), ("", True))
