import json
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from cadastro.models import matricula
from historico.auditoria import detalhes_seguros, registrar_auditoria
from historico.models import AuditoriaEvento
from site_publico.models import Noticia
from usuarioSec.forms import AccountSignupForm
from usuarioSec.models import declaracao


class SecurityValidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="usuario_sintetico",
            password="Senha-Sintetica-2026!",
        )

    def test_area_interna_bloqueia_anonimo(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_exclusao_total_nao_aceita_get(self):
        admin = get_user_model().objects.create_superuser(
            username="admin_sintetico",
            email="admin@example.invalid",
            password="Senha-Admin-Sintetica-2026!",
        )
        declaracao.objects.create(nomeDoAluno="ESTUDANTE SINTETICO")
        self.client.force_login(admin)

        response = self.client.get(reverse("apagar_todos_alunos"))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(declaracao.objects.filter(nomeDoAluno="ESTUDANTE SINTETICO").exists())

    def test_exclusao_total_post_exige_csrf(self):
        admin = get_user_model().objects.create_superuser(
            username="admin_csrf",
            email="admin2@example.invalid",
            password="Senha-Admin-Sintetica-2026!",
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(admin)

        response = client.post(reverse("apagar_todos_alunos"))

        self.assertEqual(response.status_code, 403)

    def test_cadastro_usuario_rejeita_senha_fraca(self):
        form = AccountSignupForm(
            data={
                "username": "novo_usuario",
                "email": "novo@example.invalid",
                "password": "123456",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_matricula_publica_exige_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("matricula"),
            data=json.dumps({"nomeDoAluno": "ESTUDANTE SINTETICO"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_json_invalido_em_declaracao_retorna_400(self):
        self.client.force_login(self.user)
        aluno = declaracao.objects.create(nomeDoAluno="ESTUDANTE SINTETICO")
        response = self.client.post(
            reverse("salvar_declaracao", args=[aluno.pk]),
            data=b"{json-invalido",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_csrf_protege_endpoint_json_interno(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        aluno = declaracao.objects.create(nomeDoAluno="ESTUDANTE SINTETICO")
        response = client.post(
            reverse("salvar_declaracao", args=[aluno.pk]),
            data=json.dumps({"nome": "ALTERADO"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_payload_sql_injection_nao_expande_resultados(self):
        self.client.force_login(self.user)
        declaracao.objects.create(nomeDoAluno="ALUNO UM", cpfDoAluno="111.111.111-11")
        declaracao.objects.create(nomeDoAluno="ALUNO DOIS", cpfDoAluno="222.222.222-22")

        response = self.client.post(
            reverse("buscar_dados_declaracao"),
            {"tipo": "nome", "busca": "' OR 1=1 --"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "ALUNO UM")
        self.assertNotContains(response, "ALUNO DOIS")

    def test_conteudo_publico_e_escapado_contra_xss(self):
        Noticia.objects.create(
            titulo="<script id=xss>alert(1)</script>",
            resumo="Resumo sintético",
            conteudo="<img src=x onerror=alert(1)>",
            publicado_em=timezone.now(),
            ativo=True,
        )

        response = self.client.get(reverse("site_publico:noticias"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script id=xss>", html=False)
        self.assertContains(response, "&lt;script id=xss&gt;", html=False)

    def test_headers_defensivos_estao_presentes(self):
        response = self.client.get(reverse("site_publico:home"))
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_cors_nao_e_aberto_globalmente(self):
        self.assertFalse(settings.CORS_ALLOW_ALL_ORIGINS)
        self.assertNotIn("*", settings.ALLOWED_HOSTS)

    def test_redacao_de_logs_remove_pii_e_segredos(self):
        entrada = {
            "cpf": "123.456.789-00",
            "nested": {
                "telefone": "(38) 99999-0000",
                "api_key": "segredo-api",
                "status": "ok",
            },
            "lista": [{"password": "senha-clara"}],
        }
        saida = detalhes_seguros(entrada)

        self.assertEqual(saida["cpf"], "[REDACTED]")
        self.assertEqual(saida["nested"]["telefone"], "[REDACTED]")
        self.assertEqual(saida["nested"]["api_key"], "[REDACTED]")
        self.assertEqual(saida["lista"][0]["password"], "[REDACTED]")
        self.assertEqual(saida["nested"]["status"], "ok")

    def test_auditoria_nao_grava_nome_em_texto_claro(self):
        self.client.force_login(self.user)
        request = RequestFactory().post("/historico/aluno/999/")
        request.user = self.user

        evento = registrar_auditoria(
            request,
            "TESTE_SEGURANCA",
            entidade="Aluno",
            objeto_id="999",
            objeto_repr="NOME SINTETICO COMPLETO",
            detalhes={"status": "ok"},
        )

        evento.refresh_from_db()
        self.assertNotIn("NOME SINTETICO", evento.objeto_repr)
        self.assertTrue(evento.objeto_repr.startswith("ref:"))
