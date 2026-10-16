from unittest.mock import patch

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .importacao_declaracoes import deduplicar_telefones, ler_planilha
from .models import TelefoneDeclaracao, declaracao


class ImportacaoDeclaracoesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.usuario = User.objects.create_superuser(
            username="admin_importacao",
            email="admin@example.com",
            password="senha-segura-123",
        )
        self.client.force_login(self.usuario)

    @staticmethod
    def _planilha_modelo_antigo():
        return pd.DataFrame(
            [
                ["E.M EGIDIO CORDEIRO AQUINO"] + [None] * 18,
                ["declara"] + [None] * 18,
                [
                    "NOME",
                    "",
                    "",
                    "NASCIMENTO",
                    "NATURALIDADE",
                    "NACIONALIDAD",
                    "SEXO",
                    "TURMA",
                    "TELEFONE",
                    "CELULAR PAI",
                    "Telefone da Mãe",
                    "TEL. RESPONS.",
                    "Telefone do Pai*",
                    "Telefone2 da Mãe",
                    "Telefone2 do Pai",
                    "RESPONS",
                    "CPF do Pai",
                    "CPF da Mãe",
                    "CPF RESPONS.",
                ],
                [
                    "Aluno Teste",
                    "Maria Teste",
                    "João Teste",
                    "13/08/2017",
                    "Montes Claros",
                    "Brasileira",
                    "MASCULINO",
                    "3º Ano Lavanda",
                    "998552563",
                    "998215463",
                    "999598271",
                    "(38) 99855-2563",
                    "(38) 99821-5463",
                    "(38) 99959-8271",
                    "998215463",
                    "Maria Responsável",
                    "11122233344",
                    "555.666.777-88",
                    "99988877766",
                ],
            ]
        )

    def test_deduplica_mesmo_telefone_com_e_sem_ddd(self):
        numeros, duplicados = deduplicar_telefones(
            ["99855-2563", "(38) 99855-2563", "998552563"]
        )

        self.assertEqual(numeros, ["(38) 99855-2563"])
        self.assertEqual(duplicados, 2)

    @patch("usuarioSec.importacao_declaracoes.pd.read_excel")
    def test_leitor_aceita_xls_e_detecta_modelo_antigo(self, read_excel):
        read_excel.return_value = self._planilha_modelo_antigo()
        arquivo = SimpleUploadedFile(
            "declaracao.xls",
            b"conteudo-xls-simulado",
            content_type="application/vnd.ms-excel",
        )

        resultado = ler_planilha(arquivo)

        read_excel.assert_called_once()
        self.assertEqual(read_excel.call_args.kwargs["engine"], "xlrd")
        self.assertEqual(len(resultado["registros"]), 1)

        aluno = resultado["registros"][0]
        self.assertEqual(aluno["nomeDoAluno"], "Aluno Teste")
        self.assertEqual(aluno["nomeMae"], "Maria Teste")
        self.assertEqual(aluno["nomePai"], "João Teste")
        self.assertEqual(aluno["nomeResponsavel"], "Maria Responsável")
        self.assertEqual(aluno["cpfPai"], "111.222.333-44")
        self.assertEqual(aluno["cpfMae"], "555.666.777-88")
        self.assertEqual(aluno["cpfResponsavel"], "999.888.777-66")
        self.assertEqual(str(aluno["dataNascimentoAluno"]), "2017-08-13")
        self.assertEqual(aluno["nacionaliadeAluno"], "Brasileira")
        self.assertEqual(aluno["turmaDoAluno"], "3º Ano Lavanda")

        self.assertEqual(
            aluno["telefones"]["RESPONSAVEL"],
            ["(38) 99855-2563"],
        )
        self.assertEqual(
            aluno["telefones"]["PAI"],
            ["(38) 99821-5463"],
        )
        self.assertEqual(
            aluno["telefones"]["MAE"],
            ["(38) 99959-8271"],
        )
        self.assertEqual(resultado["telefones_duplicados"], 4)

    @patch("usuarioSec.importacao_declaracoes.pd.read_excel")
    def test_importacao_salva_um_telefone_por_responsavel_sem_duplicar(self, read_excel):
        read_excel.return_value = self._planilha_modelo_antigo()
        arquivo = SimpleUploadedFile(
            "declarao (1).xls",
            b"conteudo-xls-simulado",
            content_type="application/vnd.ms-excel",
        )

        response = self.client.post(
            reverse("importar_alunos"),
            {"arquivo": arquivo},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(declaracao.objects.count(), 1)

        aluno = declaracao.objects.get()
        self.assertEqual(aluno.nomeDoAluno, "Aluno Teste")
        self.assertEqual(aluno.nomeMae, "Maria Teste")
        self.assertEqual(aluno.nomePai, "João Teste")
        self.assertEqual(aluno.nomeResponsavel, "Maria Responsável")
        self.assertEqual(aluno.cpfPai, "111.222.333-44")
        self.assertEqual(aluno.cpfMae, "555.666.777-88")
        self.assertEqual(aluno.cpfResponsavel, "999.888.777-66")

        responsavel = list(
            aluno.telefones.filter(tipo="RESPONSAVEL").values_list("telefone", flat=True)
        )
        pai = list(
            aluno.telefones.filter(tipo="PAI").values_list("telefone", flat=True)
        )
        mae = list(
            aluno.telefones.filter(tipo="MAE").values_list("telefone", flat=True)
        )

        self.assertEqual(responsavel, ["(38) 99855-2563"])
        self.assertEqual(pai, ["(38) 99821-5463"])
        self.assertEqual(mae, ["(38) 99959-8271"])
        self.assertEqual(TelefoneDeclaracao.objects.count(), 3)

    def test_tela_de_importacao_informa_suporte_a_xls(self):
        response = self.client.get(reverse("importar_alunos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ".xls")
        self.assertContains(response, 'accept=".xls,.xlsx,.csv"')
        self.assertContains(response, "Telefones repetidos")


    def test_modal_cadastro_manual_tem_os_mesmos_campos_da_planilha(self):
        response = self.client.get(reverse("telaDeclaracao"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="nomeDoAluno"')
        self.assertContains(response, 'name="nomeMae"')
        self.assertContains(response, 'name="nomePai"')
        self.assertContains(response, 'name="nomeResponsavel"')
        self.assertContains(response, 'name="cpfPai"')
        self.assertContains(response, 'name="cpfMae"')
        self.assertContains(response, 'name="cpfResponsavel"')
        self.assertContains(response, 'name="dataNascimentoAluno"')
        self.assertContains(response, 'name="natularidadeAluno"')
        self.assertContains(response, 'name="nacionaliadeAluno"')
        self.assertContains(response, 'name="sexoDoAluno"')
        self.assertContains(response, 'name="turmaDoAluno"')
        self.assertContains(response, "3º ANO LAVANDA")
        self.assertContains(response, 'name="telefonePai"', count=3)
        self.assertContains(response, 'name="telefoneMae"', count=3)
        self.assertContains(response, 'name="telefoneResponsavel"', count=3)

    def test_cadastro_manual_salva_dados_da_planilha_e_remove_telefones_repetidos(self):
        response = self.client.post(
            reverse("cadastrar_aluno"),
            {
                "nomeDoAluno": "Aluno Manual",
                "nomeMae": "Maria Manual",
                "nomePai": "João Manual",
                "nomeResponsavel": "Ana Responsável",
                "cpfPai": "11122233344",
                "cpfMae": "55566677788",
                "cpfResponsavel": "99988877766",
                "dataNascimentoAluno": "2017-08-13",
                "natularidadeAluno": "Montes Claros",
                "nacionaliadeAluno": "Brasileira",
                "ufAluno": "MG",
                "sexoDoAluno": "MASCULINO",
                "turmaDoAluno": "3º ANO LAVANDA",
                "cartaoSusDoAluno": "123456",
                "cpfDoAluno": "11122233344",
                "telefonePai": [
                    "99821-5463",
                    "(38) 99821-5463",
                    "998215463",
                ],
                "telefoneMae": [
                    "99959-8271",
                    "(38) 99959-8271",
                    "999598271",
                ],
                "telefoneResponsavel": [
                    "99855-2563",
                    "(38) 99855-2563",
                    "998552563",
                ],
            },
        )

        self.assertEqual(response.status_code, 302)
        aluno = declaracao.objects.get(nomeDoAluno="Aluno Manual")
        self.assertEqual(aluno.nomeMae, "Maria Manual")
        self.assertEqual(aluno.nomePai, "João Manual")
        self.assertEqual(aluno.nomeResponsavel, "Ana Responsável")
        self.assertEqual(aluno.cpfPai, "111.222.333-44")
        self.assertEqual(aluno.cpfMae, "555.666.777-88")
        self.assertEqual(aluno.cpfResponsavel, "999.888.777-66")
        self.assertEqual(str(aluno.dataNascimentoAluno), "2017-08-13")
        self.assertEqual(aluno.natularidadeAluno, "Montes Claros")
        self.assertEqual(aluno.nacionaliadeAluno, "Brasileira")
        self.assertEqual(aluno.ufAluno, "MG")
        self.assertEqual(aluno.sexoDoAluno, "MASCULINO")
        self.assertEqual(aluno.turmaDoAluno, "3º ANO LAVANDA")

        self.assertEqual(
            list(aluno.telefones.filter(tipo="PAI").values_list("telefone", flat=True)),
            ["(38) 99821-5463"],
        )
        self.assertEqual(
            list(aluno.telefones.filter(tipo="MAE").values_list("telefone", flat=True)),
            ["(38) 99959-8271"],
        )
        self.assertEqual(
            list(aluno.telefones.filter(tipo="RESPONSAVEL").values_list("telefone", flat=True)),
            ["(38) 99855-2563"],
        )
        self.assertEqual(TelefoneDeclaracao.objects.filter(declaracao=aluno).count(), 3)


    @patch("usuarioSec.importacao_declaracoes.pd.read_excel")
    def test_importacao_reconhece_coluna_respons_do_arquivo_enviado(self, read_excel):
        read_excel.return_value = self._planilha_modelo_antigo()
        arquivo = SimpleUploadedFile(
            "declarao-respons.xls",
            b"conteudo-xls-simulado",
            content_type="application/vnd.ms-excel",
        )

        resultado = ler_planilha(arquivo)

        self.assertEqual(
            resultado["registros"][0]["nomeResponsavel"],
            "Maria Responsável",
        )


    def test_apagar_todas_declaracoes_remove_telefones_sem_erro_500(self):
        aluno1 = declaracao.objects.create(
            nomeDoAluno="Aluno 1",
            nomeResponsavel="Responsável 1",
        )
        aluno2 = declaracao.objects.create(
            nomeDoAluno="Aluno 2",
            nomeResponsavel="Responsável 2",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=aluno1,
            tipo="RESPONSAVEL",
            telefone="(38) 99999-1111",
        )
        TelefoneDeclaracao.objects.create(
            declaracao=aluno2,
            tipo="PAI",
            telefone="(38) 99999-2222",
        )

        response = self.client.post(reverse("apagar_todos_alunos"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("telaDeclaracao"))
        self.assertEqual(declaracao.objects.count(), 0)
        self.assertEqual(TelefoneDeclaracao.objects.count(), 0)

    def test_apagar_declaracoes_com_banco_vazio_nao_gera_erro(self):
        response = self.client.post(reverse("apagar_todos_alunos"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(declaracao.objects.count(), 0)
        self.assertEqual(TelefoneDeclaracao.objects.count(), 0)
        mensagens = [str(m) for m in response.context["messages"]]
        self.assertTrue(
            any("Registros de declarações removidos: 0" in mensagem for mensagem in mensagens)
        )


    @patch("usuarioSec.importacao_declaracoes.pd.read_excel")
    def test_importacao_reconhece_variacoes_de_cabecalho_de_cpf(self, read_excel):
        read_excel.return_value = self._planilha_modelo_antigo()
        arquivo = SimpleUploadedFile(
            "declaracao-com-cpf.xls",
            b"conteudo-xls-simulado",
            content_type="application/vnd.ms-excel",
        )

        resultado = ler_planilha(arquivo)
        aluno = resultado["registros"][0]

        self.assertEqual(aluno["cpfPai"], "111.222.333-44")
        self.assertEqual(aluno["cpfMae"], "555.666.777-88")
        self.assertEqual(aluno["cpfResponsavel"], "999.888.777-66")


    def test_menu_principal_da_secretaria_exibe_boletins_independente_da_gestao_site(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Boletins")
        self.assertContains(
            response,
            f'href="{reverse("site_publico:gestao_boletins")}"',
        )
        self.assertEqual(reverse("site_publico:gestao_boletins"), "/boletins/")
