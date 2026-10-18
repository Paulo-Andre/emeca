"""Testa reparo conservador das faltas já armazenadas (sem alterar notas)."""
from io import StringIO
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import AlunoBoletim, BoletimAluno, PeriodoBoletim


class ConferenciaFaltasBoletimTests(TestCase):
    def setUp(self):
        self.periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=2, ano=2026, turma="1 Tulipa",
        )
        self.perfil = AlunoBoletim.objects.create(nome="ALUNA FICTICIA")
        self.boletim = BoletimAluno.objects.create(
            periodo=self.periodo, aluno=self.perfil,
            numero_chamada=1, faltas_totais=8,
        )
        self.arquivo = NamedTemporaryFile(suffix=".xls")
        self.arquivo.write(b"arquivo ficticio nao lido pela rotina")
        self.arquivo.flush()
        self.addCleanup(self.arquivo.close)

    def dados(self, nome="ALUNA FICTICIA", chamada=1):
        return {
            "metadados": {
                "tipo": "TRIMESTRE", "numero": 2,
                "ano": 2026, "turma": "1 Tulipa",
            },
            "alunos": [{
                "nome": nome, "numero_chamada": chamada,
                "faltas_totais": 3,
            }],
        }

    def _comando(self, dados, *flags):
        resultado = StringIO()
        with patch(
            "site_publico.management.commands.conferir_faltas_boletim.ler_planilha_boletim",
            return_value=dados,
        ):
            call_command(
                "conferir_faltas_boletim",
                self.arquivo.name,
                "--periodo-id", str(self.periodo.pk),
                *flags,
                stdout=resultado,
            )
        return resultado.getvalue()

    def test_previa_nao_altera_dados(self):
        texto = self._comando(self.dados())
        self.assertIn("1 divergentes", texto)
        self.boletim.refresh_from_db()
        self.assertEqual(self.boletim.faltas_totais, 8)

    def test_aplicar_so_corrige_total_sem_mudar_demais_dados(self):
        texto = self._comando(
            self.dados(), "--aplicar", "--backup-confirmado",
        )
        self.assertIn("1 total(is) de faltas corrigido(s)", texto)
        self.boletim.refresh_from_db()
        self.assertEqual(self.boletim.faltas_totais, 3)
        self.assertEqual(self.boletim.numero_chamada, 1)
        self.assertEqual(self.boletim.aluno_id, self.perfil.pk)

    def test_nao_aplica_sem_backup(self):
        with self.assertRaisesRegex(CommandError, "backup"):
            self._comando(self.dados(), "--aplicar")
        self.boletim.refresh_from_db()
        self.assertEqual(self.boletim.faltas_totais, 8)

    def test_chamada_diferente_cancela_lote(self):
        with self.assertRaisesRegex(CommandError, "cancelada"):
            self._comando(
                self.dados(chamada=99),
                "--aplicar", "--backup-confirmado",
            )
        self.boletim.refresh_from_db()
        self.assertEqual(self.boletim.faltas_totais, 8)

    def test_periodo_errado_nao_corrige(self):
        dados = self.dados()
        dados["metadados"]["turma"] = "TURMA DIFERENTE"
        with self.assertRaisesRegex(CommandError, "não correspondem"):
            self._comando(
                dados, "--aplicar", "--backup-confirmado",
            )
        self.boletim.refresh_from_db()
        self.assertEqual(self.boletim.faltas_totais, 8)
