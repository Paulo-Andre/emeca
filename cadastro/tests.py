import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase


class IntegracaoPublicaEInternaTests(TestCase):
    def test_historico_exige_login(self):
        response = self.client.get("/historico/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    def test_validacao_publica_nao_redireciona_para_login(self):
        response = self.client.get("/historico/validar/00000000-0000-0000-0000-000000000000/")
        self.assertNotEqual(response.status_code, 302)

    def test_api_matricula_permanece_publica(self):
        response = self.client.post(
            "/matricula/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertNotEqual(response.status_code, 302)

    def test_matricula_online_nao_exige_login(self):
        response = self.client.get("/matricula-online/")
        self.assertNotEqual(response.status_code, 302)

    def test_historico_abre_para_usuario_autenticado(self):
        User = get_user_model()
        user = User.objects.create_user(username="teste", password="SenhaMuitoForte123!")
        self.client.force_login(user)
        response = self.client.get("/historico/")
        self.assertEqual(response.status_code, 200)
