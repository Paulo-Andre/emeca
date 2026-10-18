"""Regras de vinculação explícita dos Boletins às Declarações.

Usa dados fictícios, sem acesso ao WhatsApp e sem modificar Matrículas/Histórico.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarioSec.models import declaracao
from cadastro.models import matricula

from .boletim_importacao import normalizar_nome
from .boletim_services import (
    importar_dados_boletim, localizar_alunos_por_credenciais,
    sincronizar_perfil_declaracao,
)
from .models import AlunoBoletim, BoletimAluno, DisciplinaBoletim, PeriodoBoletim


@override_settings(EMECA_RBAC_STRICT=True)
class BoletimVinculoDeclaracaoTests(TestCase):
    def setUp(self):
        self.gestor = get_user_model().objects.create_superuser(
            username="gestor_boletim_sintetico",
            email="gestor@example.invalid",
            password="Senha-Sintetica-2026!",
        )
        self.client.force_login(self.gestor)

    def periodo(self, publicado=False):
        return PeriodoBoletim.objects.create(
            tipo="TRIMESTRE", numero=2, ano=2026, turma="1º TURMA TESTE",
            regente="Docente Teste", publicado=publicado,
        )

    def declaracao(self, nome="ALUNO EXEMPLO", cpf="111.222.333-44"):
        return declaracao.objects.create(
            nomeDoAluno=nome,
            dataNascimentoAluno=date(2017, 5, 9),
            cpfMae=cpf,
            turmaDoAluno="1º TURMA TESTE",
        )

    def grade(self, nome="ALUNO EXEMPLO"):
        return {
            "metadados": {
                "tipo": "TRIMESTRE", "numero": 2, "ano": 2026,
                "turma": "1º TURMA TESTE", "regente": "Docente Teste",
            },
            "disciplinas": [{"nome": "Matemática", "ordem": 0}],
            "alunos": [{
                "nome": nome, "nome_normalizado": normalizar_nome(nome),
                "numero_chamada": 1, "faltas_totais": 3,
                "resultados": [{
                    "disciplina": "Matemática",
                    "nota": Decimal("23.50"), "faltas": 9,
                }],
            }],
        }

    def test_importacao_vincula_declaracao_e_ignora_identidade_de_matricula(self):
        fonte = self.declaracao()
        matricula.objects.create(
            nomeDoAluno=fonte.nomeDoAluno,
            dataNascimentoAluno=date(2010, 1, 1),
            cpfMae="999.999.999-99",
            temIrmaosEscola="NAO",
            problemaSaude="NAO", tratamentoSaude="NAO",
            necessidadeEspecial="NAO", medicamento="NAO",
            internado="NAO", atendimentoEspecializado="NAO",
            salaRecurso="NAO", gestacao="NAO", cras="NAO",
            visitaSocial="NAO", conselhoTutelar="NAO",
            atendimentoDomiciliar="NAO", trasporteEscolar="NAO",
        )
        resultado = importar_dados_boletim(self.grade())
        self.assertEqual(resultado["importados"], 1)
        boletim = BoletimAluno.objects.select_related("aluno").get()
        self.assertEqual(boletim.aluno.declaracao_id, fonte.pk)
        self.assertIsNone(boletim.aluno.matricula_id)
        self.assertEqual(boletim.faltas_totais, 3)
        self.assertEqual(boletim.resultados.first().nota, Decimal("23.50"))
        self.assertEqual(boletim.resultados.first().faltas, None)
        self.assertEqual(
            localizar_alunos_por_credenciais("99999999999", date(2010, 1, 1), False),
            [],
        )
        self.assertEqual(
            localizar_alunos_por_credenciais("11122233344", date(2017, 5, 9), False),
            [boletim.aluno],
        )

    def test_importacao_sem_declaracao_preserva_notas_e_bloqueia_publicacao(self):
        resultado = importar_dados_boletim(self.grade())
        self.assertEqual(resultado["pendentes_vinculo"], ["ALUNO EXEMPLO"])
        boletim = BoletimAluno.objects.select_related("aluno").get()
        self.assertIsNone(boletim.aluno.declaracao_id)
        self.assertEqual(boletim.resultados.first().nota, Decimal("23.50"))
        resp = self.client.post(
            reverse("site_publico:gestao_boletim_publicar", args=[resultado["periodo"].pk]),
        )
        self.assertEqual(resp.status_code, 302)
        resultado["periodo"].refresh_from_db()
        self.assertFalse(resultado["periodo"].publicado)
        self.assertEqual(
            localizar_alunos_por_credenciais("11122233344", date(2017, 5, 9), False),
            [],
        )

    def test_homonimos_exigem_selecao_de_declaracao(self):
        a = self.declaracao(cpf="111.111.111-11")
        b = self.declaracao(cpf="222.222.222-22")
        importacao = importar_dados_boletim(self.grade())
        self.assertEqual(importacao["pendentes_vinculo"], ["ALUNO EXEMPLO"])
        boletim = BoletimAluno.objects.get()
        self.assertIsNone(boletim.aluno.declaracao_id)
        editar = reverse(
            "site_publico:gestao_boletim_aluno_editar",
            args=[boletim.periodo_id, boletim.pk],
        )
        resp = self.client.post(editar, {
            "nome_aluno": "ALUNO EXEMPLO",
            "numero_chamada": "1", "faltas_totais": "3",
            "declaracao_aluno": str(b.pk),
        })
        self.assertEqual(resp.status_code, 302)
        boletim.aluno.refresh_from_db()
        self.assertEqual(boletim.aluno.declaracao_id, b.pk)
        self.assertEqual(
            localizar_alunos_por_credenciais(
                "11111111111", date(2017, 5, 9), False,
            ), [],
        )
        self.assertEqual(
            localizar_alunos_por_credenciais(
                "22222222222", date(2017, 5, 9), False,
            ), [boletim.aluno],
        )

    def test_alteracao_cpf_declaracao_troca_credencial_sem_mexer_notas(self):
        d = self.declaracao()
        importar_dados_boletim(self.grade())
        perfil = AlunoBoletim.objects.get(declaracao=d)
        d.cpfMae = "555.666.777-88"
        d.dataNascimentoAluno = date(2018, 6, 12)
        d.save()
        perfil.refresh_from_db()
        self.assertEqual(perfil.cpf_mae, "555.666.777-88")
        self.assertEqual(perfil.data_nascimento, date(2018, 6, 12))
        self.assertEqual(
            localizar_alunos_por_credenciais("11122233344", date(2017, 5, 9), False),
            [],
        )
        self.assertEqual(
            localizar_alunos_por_credenciais("55566677788", date(2018, 6, 12), False),
            [perfil],
        )
        self.assertEqual(perfil.boletins.first().resultados.first().nota, Decimal("23.50"))

    def test_nao_apaga_declaracao_com_notas_vinculadas(self):
        d = self.declaracao()
        importar_dados_boletim(self.grade())
        resultado = self.client.post(
            reverse("deletar_aluno_declaracao", args=[d.pk]),
        )
        self.assertEqual(resultado.status_code, 302)
        self.assertTrue(declaracao.objects.filter(pk=d.pk).exists())
        self.assertEqual(BoletimAluno.objects.count(), 1)

    def test_nao_permite_religar_boletim_a_outro_aluno(self):
        a = self.declaracao()
        b = self.declaracao(nome="OUTRO ALUNO")
        importar_dados_boletim(self.grade())
        boletim = BoletimAluno.objects.get()
        url = reverse(
            "site_publico:gestao_boletim_aluno_editar",
            args=[boletim.periodo_id, boletim.pk],
        )
        resposta = self.client.post(url, {
            "nome_aluno": "OUTRO ALUNO",
            "declaracao_aluno": str(b.pk),
            "faltas_totais": "3",
        })
        self.assertEqual(resposta.status_code, 200)
        boletim.aluno.refresh_from_db()
        self.assertEqual(boletim.aluno.declaracao_id, a.pk)
