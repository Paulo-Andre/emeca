from django.test import SimpleTestCase
from usuarioSec.importacao_declaracoes import mapear_colunas


class ColunasCPFOficialTests(SimpleTestCase):
    def test_cpfs_genericos_na_posicao_oficial(self):
        colunas = [""] * 31
        colunas[0] = "NOME"
        colunas[1] = "NASCIMENTO"
        colunas[27:31] = ["CPF DA MAE", "CPF", "CPF", "CPF DO PAI"]
        mapa = mapear_colunas(colunas)
        self.assertEqual(mapa["cpf_mae"], 27)
        self.assertEqual(mapa["cpf_responsavel"], 28)
        self.assertEqual(mapa["cpf_aluno"], 29)
        self.assertEqual(mapa["cpf_pai"], 30)

    def test_planilha_diferente_nao_inventa_associacoes(self):
        colunas = ["NOME", "NASCIMENTO", "CPF", "CPF"]
        mapa = mapear_colunas(colunas)
        self.assertIsNone(mapa["cpf_responsavel"])
        self.assertIsNone(mapa["cpf_aluno"])
