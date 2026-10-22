from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from site_publico.models import AlunoBoletim, BoletimAluno, PeriodoBoletim
from usuarioSec.models import declaracao


class ExclusaoBoletimIndividualTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_superuser(
            "gestor_exclusao_teste", "gestor@example.invalid", "senha-teste"
        )
        self.client.force_login(usuario)
        self.declaracao = declaracao.objects.create(
            nomeDoAluno="ALUNA TESTE", dataNascimentoAluno=date(2018, 4, 2)
        )
        self.aluno = AlunoBoletim.objects.create(
            nome="ALUNA TESTE", declaracao=self.declaracao
        )
        self.periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=1, ano=2026, turma="TURMA TESTE", publicado=False
        )
        self.outro = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=2, ano=2026, turma="TURMA TESTE", publicado=False
        )
        self.b1 = BoletimAluno.objects.create(
            periodo=self.periodo, aluno=self.aluno, faltas_totais=3
        )
        self.b2 = BoletimAluno.objects.create(
            periodo=self.outro, aluno=self.aluno, faltas_totais=5
        )

    def url(self):
        return reverse("site_publico:gestao_boletim_aluno_excluir", args=[
            self.periodo.pk, self.b1.pk
        ])

    def test_excluir_um_preserva_declaracao_e_outro_periodo(self):
        resposta = self.client.post(self.url(), {"confirmar": "EXCLUIR"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
        self.assertEqual(BoletimAluno.objects.get(pk=self.b2.pk).faltas_totais, 5)
        self.assertTrue(declaracao.objects.filter(pk=self.declaracao.pk).exists())

    def test_publicado_pode_excluir_so_um_boletim(self):
        self.periodo.publicado = True
        self.periodo.save(update_fields=["publicado"])
        resposta = self.client.post(self.url(), {"confirmar": "EXCLUIR"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
        self.assertTrue(BoletimAluno.objects.filter(pk=self.b2.pk).exists())
        self.assertTrue(declaracao.objects.filter(pk=self.declaracao.pk).exists())
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.publicado)

    def test_sem_confirmacao_nao_exclui(self):
        resposta = self.client.post(self.url(), {"confirmar": ""})
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(BoletimAluno.objects.filter(pk=self.b1.pk).exists())

    def test_get_nao_exclui(self):
        self.assertEqual(self.client.get(self.url()).status_code, 405)
        self.assertTrue(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
