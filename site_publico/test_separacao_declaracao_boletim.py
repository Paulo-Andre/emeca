"""Separação entre cadastros de Declarações e notas/faltas dos boletins."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from site_publico.boletim_services import religar_boletins_apos_importar_declaracoes
from site_publico.models import AlunoBoletim, BoletimAluno, PeriodoBoletim
from usuarioSec.models import declaracao


class SeparacaoDeclaracaoBoletimTests(TestCase):
    def setUp(self):
        self.gestor = get_user_model().objects.create_superuser(
            "gestor_separacao", "teste@example.invalid", "senha-exemplo"
        )
        self.client.force_login(self.gestor)
        self.nasc = date(2018, 5, 19)
        self.fonte = declaracao.objects.create(
            nomeDoAluno="CRIANCA DE TESTE",
            dataNascimentoAluno=self.nasc,
            cpfMae="111.222.333-44",
        )
        self.perfil = AlunoBoletim.objects.create(
            nome="CRIANCA DE TESTE", declaracao=self.fonte,
            data_nascimento=self.nasc, cpf_mae=self.fonte.cpfMae,
        )
        periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=1, ano=2026, turma="TURMA TESTE",
            publicado=False,
        )
        self.boletim = BoletimAluno.objects.create(
            periodo=periodo, aluno=self.perfil, faltas_totais=3
        )

    def test_apagar_declaracoes_preserva_boletim_e_religa_apos_nova_importacao(self):
        resposta = self.client.post(reverse("apagar_todos_alunos"))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(declaracao.objects.filter(pk=self.fonte.pk).exists())
        self.perfil.refresh_from_db()
        self.boletim.refresh_from_db()
        self.assertIsNone(self.perfil.declaracao_id)
        self.assertEqual(self.boletim.faltas_totais, 3)
        nova = declaracao.objects.create(
            nomeDoAluno="CRIANCA DE TESTE",
            dataNascimentoAluno=self.nasc,
            cpfResponsavel="555.666.777-88",
        )
        vinculados, pendentes = religar_boletins_apos_importar_declaracoes()
        self.assertEqual((vinculados, pendentes), (1, 0))
        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.declaracao_id, nova.pk)
        self.assertEqual(self.perfil.cpf_responsavel, "555.666.777-88")
        self.boletim.refresh_from_db()
        self.assertEqual(self.boletim.faltas_totais, 3)

    def test_nascimento_divergente_bloqueia_religacao(self):
        self.client.post(reverse("apagar_todos_alunos"))
        declaracao.objects.create(
            nomeDoAluno="CRIANCA DE TESTE",
            dataNascimentoAluno=date(2017, 5, 19),
            cpfMae="111.222.333-44",
        )
        self.assertEqual(religar_boletins_apos_importar_declaracoes(), (0, 1))

    def test_duplicidades_bloqueiam_religacao(self):
        self.client.post(reverse("apagar_todos_alunos"))
        for _ in range(2):
            declaracao.objects.create(
                nomeDoAluno="CRIANCA DE TESTE", dataNascimentoAluno=self.nasc
            )
        self.assertEqual(religar_boletins_apos_importar_declaracoes(), (0, 1))
