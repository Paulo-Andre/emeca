"""Testes de conciliação segura sem publicação, com dados fictícios."""
from datetime import date
from django.test import TestCase
from django.core.management import call_command
from io import StringIO
from site_publico.models import AlunoBoletim, BoletimAluno, PeriodoBoletim
from site_publico.management.commands.reconciliar_vinculos_boletins import planejar
from usuarioSec.models import declaracao


class ReconciliacaoVinculosTestes(TestCase):
    def setUp(self):
        self.periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=2, ano=2026, turma="TURMA FICTICIA", publicado=False
        )
        self.p = AlunoBoletim.objects.create(nome="CRIANCA FICTICIA")
        BoletimAluno.objects.create(periodo=self.periodo, aluno=self.p, faltas_totais=3)

    def test_simula_e_aplica_sem_publicar(self):
        d = declaracao.objects.create(
            nomeDoAluno="CRIANCA FICTICIA",
            dataNascimentoAluno=date(2018, 2, 15),
            cpfMae="123.456.789-09"
        )
        preview = StringIO()
        call_command("reconciliar_vinculos_boletins", stdout=preview)
        self.assertIn("PERFIS APTOS: 1", preview.getvalue())
        self.p.refresh_from_db()
        self.assertIsNone(self.p.declaracao_id)
        call_command("reconciliar_vinculos_boletins", "--aplicar",
                     "--confirmar", "VINCULAR-SEM-PUBLICAR", stdout=StringIO())
        self.p.refresh_from_db()
        self.periodo.refresh_from_db()
        self.assertEqual(self.p.declaracao_id, d.pk)
        self.assertFalse(self.periodo.publicado)
        self.assertEqual(self.p.boletins.get().faltas_totais, 3)

    def test_duplicado_nao_vincula(self):
        for _ in range(2):
            declaracao.objects.create(
                nomeDoAluno="CRIANCA FICTICIA",
                dataNascimentoAluno=date(2018, 2, 15),
                cpfMae="123.456.789-09"
            )
        acoes, pendencias = planejar()
        self.assertFalse(acoes)
        self.assertIn("Nome duplicado", [motivo for _, motivo in pendencias])

    def test_nome_divergente_nao_vincula(self):
        declaracao.objects.create(
            nomeDoAluno="OUTRA CRIANCA",
            dataNascimentoAluno=date(2018, 2, 15),
            cpfMae="123.456.789-09"
        )
        acoes, _ = planejar()
        self.assertFalse(acoes)
