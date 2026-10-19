"""Regressão: a impressão deve funcionar em aba HTTP e manter o template original."""
import json
from unittest.mock import patch

from django.test import SimpleTestCase, RequestFactory

from usuarioSec.views import imprimirDeclaracao


class ImpressaoDeclaracoesTestes(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.dados = {
            "tipo": "Transferência",
            "nome": "ALUNO FICTICIO",
            "nasc": "2015-06-17",
            "naturalidade": "MONTES CLAROS",
            "serie": "5º ANO",
            "mae": "MAE FICTICIA",
            "pai": "PAI FICTICIO",
            "ano": "2026",
            "anoCursa": "6",
            "assinatura": False,
            "carimbo": False,
        }

    @patch("usuarioSec.views.render")
    def test_form_post_abre_template_correto(self, renderizar):
        request = self.factory.post("/imprimirDeclaracao/1/", {
            "dados": json.dumps(self.dados)
        })
        imprimirDeclaracao(request, 1)
        self.assertEqual(renderizar.call_args.args[1], "declaracoes/transferencia.html")
        contexto = renderizar.call_args.args[2]
        self.assertEqual(contexto["nome"], "ALUNO FICTICIO")
        self.assertEqual(contexto["serie"], "5")

    @patch("usuarioSec.views.render")
    def test_json_antigo_continua_compativel(self, renderizar):
        request = self.factory.post("/imprimirDeclaracao/1/",
                                    data=json.dumps(self.dados),
                                    content_type="application/json")
        imprimirDeclaracao(request, 1)
        self.assertEqual(renderizar.call_args.args[1], "declaracoes/transferencia.html")

    def test_form_post_invalido_retorna_400(self):
        request = self.factory.post("/imprimirDeclaracao/1/", {"dados": "invalido"})
        self.assertEqual(imprimirDeclaracao(request, 1).status_code, 400)
