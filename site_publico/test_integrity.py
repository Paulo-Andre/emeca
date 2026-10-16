from django.test import TestCase

from site_publico.boletim_services import importar_dados_boletim
from site_publico.models import PeriodoBoletim


class IntegridadeTransacionalTests(TestCase):
    def test_importacao_boletim_invalida_faz_rollback_completo(self):
        dados = {
            "metadados": {
                "tipo": "TRIMESTRE",
                "numero": 1,
                "ano": 2099,
                "turma": "TURMA SINTETICA",
                "regente": "REGENTE SINTETICO",
            },
            "disciplinas": [],
            "alunos": [],
        }

        with self.assertRaises(ValueError):
            importar_dados_boletim(dados)

        self.assertFalse(
            PeriodoBoletim.objects.filter(
                tipo="TRIMESTRE",
                numero=1,
                ano=2099,
                turma="TURMA SINTETICA",
            ).exists()
        )
