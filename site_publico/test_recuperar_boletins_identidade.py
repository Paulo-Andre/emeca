"""Testes sintéticos do reconhecimento de identidade da recuperação.

Não usa o backup da escola nem realiza restauração em produção.
"""
from datetime import date
from django.test import SimpleTestCase
from site_publico.management.commands.recuperar_boletins_por_identidade import (
    _chave, _nome, _nasc,
)


class IdentidadeRecuperacaoBoletinsTests(SimpleTestCase):
    def test_nome_com_acentos_e_espacos(self):
        self.assertEqual(
            _nome(" Ana   Vitória de  Sá "),
            "ANA VITORIA DE SA",
        )

    def test_nome_e_nascimento_identificam_aluno(self):
        self.assertEqual(
            _chave("João da Silva", date(2018, 10, 2)),
            ("JOAO DA SILVA", "2018-10-02"),
        )
        self.assertEqual(
            _chave("JOAO DA SILVA", "2018-10-02"),
            ("JOAO DA SILVA", "2018-10-02"),
        )

    def test_sem_nascimento_nao_permite_vinculo(self):
        self.assertIsNone(_chave("João da Silva", ""))
        self.assertIsNone(_chave("João da Silva", "nascimento-desconhecido"))

    def test_alunos_homonimos_com_datas_distintas_nao_confundidos(self):
        self.assertNotEqual(
            _chave("ANA MARIA", "2017-01-01"),
            _chave("ANA MARIA", "2017-02-01"),
        )
