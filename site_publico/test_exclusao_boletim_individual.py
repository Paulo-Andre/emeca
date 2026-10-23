from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from site_publico.models import AlunoBoletim, BoletimAluno, PeriodoBoletim, DisciplinaBoletim, NotaBoletim
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

    def test_tres_alunos_mesmo_periodo_excluir_um_preserva_outros_dois(self):
        outros = []
        for indice in range(2):
            registro = declaracao.objects.create(
                nomeDoAluno=f"OUTRO ALUNO TESTE {indice}"
            )
            aluno = AlunoBoletim.objects.create(
                nome=f"OUTRO ALUNO TESTE {indice}", declaracao=registro
            )
            outros.append(BoletimAluno.objects.create(
                periodo=self.periodo, aluno=aluno, faltas_totais=indice + 1
            ))
        disciplinas = [
            DisciplinaBoletim.objects.create(
                periodo=self.periodo, nome=f"DISCIPLINA {indice}"
            ) for indice in range(3)
        ]
        for disciplina in disciplinas:
            NotaBoletim.objects.create(
                boletim=self.b1, disciplina=disciplina, nota=8,
            )

        self.assertEqual(self.periodo.boletins.count(), 3)
        self.assertEqual(self.b1.resultados.count(), 3)
        resposta = self.client.post(self.url(), {"confirmar": "EXCLUIR"})

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.periodo.boletins.count(), 2)
        self.assertFalse(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
        self.assertFalse(NotaBoletim.objects.filter(boletim_id=self.b1.pk).exists())
        self.assertTrue(
            all(BoletimAluno.objects.filter(pk=item.pk).exists() for item in outros)
        )
        self.assertTrue(declaracao.objects.filter(pk=self.declaracao.pk).exists())

    def test_botao_excluir_associa_nome_e_id_corretos_na_pagina(self):
        self.periodo.publicado = True
        self.periodo.save(update_fields=["publicado"])
        resposta = self.client.get(reverse(
            "site_publico:gestao_boletim_periodo", args=[self.periodo.pk]
        ))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "bulletin-student-manager-actions")
        self.assertContains(resposta, "Excluir o boletim de ALUNA TESTE")
        self.assertContains(resposta, self.url())

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

    def test_exclui_um_de_tres_boletins_do_mesmo_periodo(self):
        # Regressão para o relato de vários alunos desaparecendo por um clique.
        colegas = []
        for idx in range(2):
            registro = declaracao.objects.create(
                nomeDoAluno=f"COLEGA SINTETICO {idx}",
                dataNascimentoAluno=date(2018, 4, 3),
            )
            aluno = AlunoBoletim.objects.create(
                nome=f"COLEGA SINTETICO {idx}",
                declaracao=registro,
            )
            colegas.append(BoletimAluno.objects.create(
                periodo=self.periodo, aluno=aluno, faltas_totais=idx + 1,
            ))

        self.periodo.publicado = True
        self.periodo.save(update_fields=["publicado"])
        self.assertEqual(self.periodo.boletins.count(), 3)

        resposta = self.client.post(self.url(), {"confirmar": "EXCLUIR"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.periodo.boletins.count(), 2)
        self.assertFalse(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
        for colega in colegas:
            colega.refresh_from_db()
            self.assertEqual(colega.periodo_id, self.periodo.pk)
            self.assertTrue(BoletimAluno.objects.filter(pk=colega.pk).exists())
        self.assertTrue(declaracao.objects.filter(pk=self.declaracao.pk).exists())

    def test_excluir_um_de_tres_alunos_do_mesmo_periodo_preserva_os_outros(self):
        segundo = AlunoBoletim.objects.create(nome="ALUNO SINTETICO 2")
        terceiro = AlunoBoletim.objects.create(nome="ALUNO SINTETICO 3")
        b2 = BoletimAluno.objects.create(
            periodo=self.periodo, aluno=segundo, faltas_totais=2,
        )
        b3 = BoletimAluno.objects.create(
            periodo=self.periodo, aluno=terceiro, faltas_totais=7,
        )
        self.periodo.publicado = True
        self.periodo.save(update_fields=["publicado"])
        self.assertEqual(self.periodo.boletins.count(), 3)

        resposta = self.client.post(self.url(), {"confirmar": "EXCLUIR"})

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.periodo.boletins.count(), 2)
        self.assertFalse(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
        self.assertEqual(BoletimAluno.objects.get(pk=b2.pk).faltas_totais, 2)
        self.assertEqual(BoletimAluno.objects.get(pk=b3.pk).faltas_totais, 7)
        self.assertTrue(declaracao.objects.filter(pk=self.declaracao.pk).exists())

    def test_sem_confirmacao_nao_exclui(self):
        resposta = self.client.post(self.url(), {"confirmar": ""})
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(BoletimAluno.objects.filter(pk=self.b1.pk).exists())

    def test_excluir_um_entre_tres_preserva_outros_dois_e_notas(self):
        from site_publico.models import DisciplinaBoletim, NotaBoletim

        segundo_cadastro = declaracao.objects.create(nomeDoAluno="ALUNO B TESTE")
        terceiro_cadastro = declaracao.objects.create(nomeDoAluno="ALUNO C TESTE")
        segundo = AlunoBoletim.objects.create(
            nome="ALUNO B TESTE", declaracao=segundo_cadastro,
        )
        terceiro = AlunoBoletim.objects.create(
            nome="ALUNO C TESTE", declaracao=terceiro_cadastro,
        )
        boletim_b = BoletimAluno.objects.create(
            periodo=self.periodo, aluno=segundo, faltas_totais=7,
        )
        boletim_c = BoletimAluno.objects.create(
            periodo=self.periodo, aluno=terceiro, faltas_totais=8,
        )
        disciplina = DisciplinaBoletim.objects.create(
            periodo=self.periodo, nome="Matemática", ordem=1,
        )
        NotaBoletim.objects.create(boletim=self.b1, disciplina=disciplina, nota=8)
        NotaBoletim.objects.create(boletim=boletim_b, disciplina=disciplina, nota=7)
        NotaBoletim.objects.create(boletim=boletim_c, disciplina=disciplina, nota=6)
        self.periodo.publicado = True
        self.periodo.save(update_fields=["publicado"])

        antes = set(self.periodo.boletins.values_list("pk", flat=True))
        self.assertEqual(len(antes), 3)
        response = self.client.post(self.url(), {"confirmar": "EXCLUIR"})
        self.assertEqual(response.status_code, 302)
        depois = set(self.periodo.boletins.values_list("pk", flat=True))
        self.assertEqual(depois, antes - {self.b1.pk})
        self.assertEqual(NotaBoletim.objects.filter(boletim=self.b1).count(), 0)
        self.assertEqual(NotaBoletim.objects.filter(
            boletim_id__in=[boletim_b.pk, boletim_c.pk],
        ).count(), 2)
        self.assertTrue(declaracao.objects.filter(pk=self.declaracao.pk).exists())
        self.assertTrue(BoletimAluno.objects.filter(pk=self.b2.pk).exists())

    def test_excluir_um_de_tres_alunos_no_mesmo_periodo(self):
        """A exclusão jamais deve remover outros boletins da mesma turma."""
        outros = []
        for indice in (2, 3):
            declaracao_extra = declaracao.objects.create(
                nomeDoAluno=f"ALUNO TESTE {indice}"
            )
            aluno_extra = AlunoBoletim.objects.create(
                nome=f"ALUNO TESTE {indice}", declaracao=declaracao_extra
            )
            outros.append(
                BoletimAluno.objects.create(
                    periodo=self.periodo, aluno=aluno_extra,
                    numero_chamada=indice, faltas_totais=indice
                ).pk
            )
        self.assertEqual(self.periodo.boletins.count(), 3)

        resposta = self.client.post(self.url(), {"confirmar": "EXCLUIR"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
        self.assertEqual(self.periodo.boletins.count(), 2)
        self.assertEqual(
            set(self.periodo.boletins.values_list("pk", flat=True)),
            set(outros),
        )
        self.assertEqual(BoletimAluno.objects.get(pk=outros[0]).faltas_totais, 2)
        self.assertEqual(BoletimAluno.objects.get(pk=outros[1]).faltas_totais, 3)
        self.assertTrue(declaracao.objects.filter(pk=self.declaracao.pk).exists())
        self.assertTrue(BoletimAluno.objects.filter(pk=self.b2.pk).exists())

    def test_excluir_um_em_turma_com_tres_preserva_outros_dois(self):
        outro_cadastro = declaracao.objects.create(nomeDoAluno="ALUNA FICTICIA 2")
        terceiro_cadastro = declaracao.objects.create(nomeDoAluno="ALUNA FICTICIA 3")
        outro_aluno = AlunoBoletim.objects.create(
            nome="ALUNA FICTICIA 2", declaracao=outro_cadastro
        )
        terceiro_aluno = AlunoBoletim.objects.create(
            nome="ALUNA FICTICIA 3", declaracao=terceiro_cadastro
        )
        segundo = BoletimAluno.objects.create(
            periodo=self.periodo, aluno=outro_aluno, faltas_totais=1
        )
        terceiro = BoletimAluno.objects.create(
            periodo=self.periodo, aluno=terceiro_aluno, faltas_totais=2
        )
        self.periodo.publicado = True
        self.periodo.save(update_fields=["publicado"])
        self.assertEqual(self.periodo.boletins.count(), 3)
        resposta = self.client.post(self.url(), {"confirmar": "EXCLUIR"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.periodo.boletins.count(), 2)
        self.assertFalse(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
        self.assertTrue(BoletimAluno.objects.filter(pk=segundo.pk).exists())
        self.assertTrue(BoletimAluno.objects.filter(pk=terceiro.pk).exists())

    def test_get_nao_exclui(self):
        self.assertEqual(self.client.get(self.url()).status_code, 405)
        self.assertTrue(BoletimAluno.objects.filter(pk=self.b1.pk).exists())
