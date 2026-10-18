"""Regressões de faltas totais (H) e símbolo no PDF dos boletins.

Os testes criam planilhas/dados fictícios e não utilizam informações reais.
"""
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pdfplumber
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .boletim_importacao import (
    ImportacaoBoletimErro,
    ler_planilha_boletim,
)
from .boletim_services import (
    _imagem_simbolo_boletim,
    gerar_pdf_boletim,
    importar_dados_boletim,
)
from .models import AlunoBoletim, BoletimAluno, PeriodoBoletim


def planilha_turma(faltas_h=3):
    linhas = [[""] * 12 for _ in range(8)]
    linhas[0][0] = "Notas e Faltas 2º Trimestre Turma 1 Tulipa - 2026"
    linhas[2][6] = "Língua Portuguesa"
    linhas[2][8] = "Matemática"
    linhas[2][10] = "Ciências"
    linhas[3][0] = "Num."
    linhas[3][1] = "Nome"
    linhas[3][6:12] = ["N", "F", "N", "F", "N", "F"]
    linhas[4][0] = 1
    linhas[4][1] = "ALUNA FICTICIA"
    linhas[4][5] = 99  # Antiga coluna F não é a falta real.
    linhas[4][6:12] = [24, faltas_h, 27, 1, 29, 2]
    return pd.DataFrame(linhas)


class ImportacaoFaltasColunaHTests(TestCase):
    def _ler(self, faltas_h):
        arquivo = SimpleUploadedFile("notas.xls", b"planilha-de-teste")
        with patch(
            "site_publico.boletim_importacao.pd.read_excel",
            return_value=planilha_turma(faltas_h),
        ):
            return ler_planilha_boletim(arquivo)

    def test_coluna_h_e_total_nao_soma_decomposicao(self):
        leitura = self._ler(3)
        self.assertEqual(leitura["alunos"][0]["faltas_totais"], 3)
        self.assertEqual(
            [r["faltas"] for r in leitura["alunos"][0]["resultados"]],
            [3, 1, 2],
        )
        resultado = importar_dados_boletim(leitura)
        self.assertEqual(resultado["importados"], 1)
        boletim = BoletimAluno.objects.get()
        self.assertEqual(boletim.faltas_totais, 3)
        self.assertFalse(
            boletim.resultados.filter(faltas__isnull=False).exists()
        )

    def test_zero_em_h_nao_herda_faltas_de_outras_colunas(self):
        leitura = self._ler(0)
        self.assertEqual(leitura["alunos"][0]["faltas_totais"], 0)

    def test_arquivo_sem_coluna_h_nao_gera_faltas_inventadas(self):
        arquivo = SimpleUploadedFile("notas.xls", b"planilha-de-teste")
        sem_h = planilha_turma().iloc[:, :7].copy()
        with patch(
            "site_publico.boletim_importacao.pd.read_excel",
            return_value=sem_h,
        ):
            with self.assertRaisesRegex(ImportacaoBoletimErro, "coluna H"):
                ler_planilha_boletim(arquivo)


class PDFBoletimSimboloTests(TestCase):
    def test_simbolo_oficial_esta_disponivel_sem_configuracao(self):
        resultado = _imagem_simbolo_boletim(None)
        self.assertIsNotNone(
            resultado,
            "O símbolo institucional padrão precisa estar incluído no projeto.",
        )
        dados, largura, altura = resultado
        self.assertTrue(dados.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(largura, 0)
        self.assertGreater(altura, 0)

    def test_pdf_usa_imagem_em_vez_de_apenas_selo_em_texto(self):
        periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=2, ano=2026,
            turma="1º TESTE", regente="Docente Fictício",
        )
        aluno = AlunoBoletim.objects.create(nome="ALUNA FICTICIA")
        boletim = BoletimAluno.objects.create(
            periodo=periodo, aluno=aluno, faltas_totais=3,
        )
        arquivo = gerar_pdf_boletim(boletim)
        with pdfplumber.open(BytesIO(arquivo.getvalue())) as pdf:
            self.assertTrue(pdf.pages)
            self.assertGreater(
                len(pdf.pages[0].images), 0,
                "O PDF deve embutir o símbolo como imagem no cabeçalho.",
            )
        arquivo.close()
