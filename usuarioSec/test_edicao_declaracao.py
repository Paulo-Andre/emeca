"""Testes de edição dos dados completos das Declarações (sem gerar impressão)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .access_control import GRUPO_SECRETARIA
from .models import TelefoneDeclaracao, declaracao


class EdicaoDadosDeclaracaoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="secretaria_edicao", password="Senha-Ficticia-2026!",
        )
        grupo, _ = Group.objects.get_or_create(name=GRUPO_SECRETARIA)
        self.usuario.groups.add(grupo)
        self.aluno = declaracao.objects.create(
            nomeDoAluno="ALUNO DE TESTE",
            nomeMae="MAE ANTERIOR",
            cpfPai="111.111.111-11",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=self.aluno, tipo="MAE", telefone="(38) 98888-7777",
        )
        self.url = reverse("editar_aluno_declaracao", args=[self.aluno.pk])

    def test_exige_login(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_restringe_a_secretaria(self):
        outro = get_user_model().objects.create_user(
            username="outro_modulo", password="Senha-Ficticia-2026!",
        )
        self.client.force_login(outro)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 403)

    def test_exibe_cpfs_e_telefones_existentes(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "111.111.111-11")
        self.assertContains(resposta, "98888-7777")

    def test_edita_dados_completos_e_deduplica_telefones(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, {
            "nomeDoAluno": "ALUNO ATUALIZADO",
            "dataNascimentoAluno": "2016-04-19",
            "nacionaliadeAluno": "BRASILEIRA",
            "natularidadeAluno": "MONTES CLAROS",
            "ufAluno": "MG",
            "sexoDoAluno": "MASCULINO",
            "turmaDoAluno": "4º ANO",
            "cartaoSusDoAluno": "1234567890",
            "cpfDoAluno": "12345678901",
            "nomePai": "PAI NOVO",
            "cpfPai": "12345678901",
            "nomeMae": "MAE NOVA",
            "cpfMae": "98765432100",
            "nomeResponsavel": "RESPONSAVEL NOVO",
            "cpfResponsavel": "23456789012",
            "telefonePai": ["(38) 99999-2222", "38999992222", ""],
            "telefoneMae": ["(38) 97777-6666", "", ""],
            "telefoneResponsavel": ["(38) 98888-1111", "", ""],
        })
        self.assertEqual(resposta.status_code, 302)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.nomeDoAluno, "ALUNO ATUALIZADO")
        self.assertEqual(self.aluno.nomeResponsavel, "RESPONSAVEL NOVO")
        self.assertEqual(self.aluno.cpfPai, "123.456.789-01")
        self.assertEqual(self.aluno.cpfMae, "987.654.321-00")
        self.assertEqual(self.aluno.cpfResponsavel, "234.567.890-12")
        self.assertEqual(
            TelefoneDeclaracao.objects.filter(declaracao=self.aluno, tipo="PAI").count(), 1,
        )
        self.assertEqual(
            TelefoneDeclaracao.objects.filter(declaracao=self.aluno, tipo="MAE").count(), 1,
        )

    def test_cpf_incompleto_nao_grava_parcialmente(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, {
            "nomeDoAluno": "ALTERACAO INVALIDA",
            "cpfPai": "123",
        })
        self.assertEqual(resposta.status_code, 200)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.nomeDoAluno, "ALUNO DE TESTE")
        self.assertEqual(self.aluno.cpfPai, "111.111.111-11")
        self.assertEqual(
            TelefoneDeclaracao.objects.filter(declaracao=self.aluno).count(), 1,
        )
