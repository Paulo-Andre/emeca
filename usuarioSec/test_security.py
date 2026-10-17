import json
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from cadastro.models import matricula
from historico.auditoria import detalhes_seguros, registrar_auditoria
from historico.models import AuditoriaEvento
from site_publico.forms import get_content_form
from site_publico.models import Noticia, validar_imagem_upload
from usuarioSec.forms import AccountSignupForm
from usuarioSec.access_control import (
    GRUPO_HISTORICO,
    GRUPO_SECRETARIA,
)
from usuarioSec.models import SecurityRateLimit, declaracao


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


    def test_link_editavel_rejeita_javascript_scheme(self):
        FormClass = get_content_form("avisos")
        form = FormClass(
            data={
                "titulo": "Aviso sintético",
                "texto": "Conteúdo de teste",
                "tipo": "INFO",
                "link": "javascript:alert(1)",
                "ativo": "on",
                "inicio": "",
                "fim": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("link", form.errors)

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

    @override_settings(EMECA_RBAC_STRICT=True)
    def test_rbac_bloqueia_modulo_sem_perfil(self):
        self.client.force_login(self.user)

        negado = self.client.get(reverse("dashboard"))
        self.assertEqual(negado.status_code, 403)

        self.user.groups.add(Group.objects.get(name=GRUPO_SECRETARIA))
        permitido = self.client.get(reverse("dashboard"))
        self.assertEqual(permitido.status_code, 200)

        historico = self.client.get(reverse("historico:inicio"))
        self.assertEqual(historico.status_code, 403)

    @override_settings(EMECA_RBAC_STRICT=True)
    def test_rbac_permite_modulo_historico_quando_concedido(self):
        self.user.groups.add(Group.objects.get(name=GRUPO_HISTORICO))
        self.client.force_login(self.user)

        response = self.client.get(reverse("historico:inicio"))
        self.assertEqual(response.status_code, 200)

    @override_settings(
        RATE_LIMIT_ENABLED=True,
        LOGIN_RATE_LIMIT_ACCOUNT=2,
        LOGIN_RATE_LIMIT_IP=50,
        LOGIN_RATE_LIMIT_WINDOW=900,
        EMECA_RBAC_STRICT=False,
    )
    def test_rate_limit_bloqueia_brute_force_de_login(self):
        for _ in range(2):
            response = self.client.post(
                reverse("login"),
                {"username": "alvo_sintetico", "password": "senha-incorreta"},
                REMOTE_ADDR="198.51.100.10",
            )
            self.assertEqual(response.status_code, 200)

        bloqueado = self.client.post(
            reverse("login"),
            {"username": "alvo_sintetico", "password": "senha-incorreta"},
            REMOTE_ADDR="198.51.100.10",
        )
        self.assertEqual(bloqueado.status_code, 429)
        self.assertIn("Retry-After", bloqueado)
        self.assertGreaterEqual(SecurityRateLimit.objects.count(), 1)

    @override_settings(
        RATE_LIMIT_ENABLED=True,
        BOLETIM_RATE_LIMIT_IP=2,
        BOLETIM_RATE_LIMIT_WINDOW=900,
        EMECA_RBAC_STRICT=False,
    )
    def test_rate_limit_publico_bloqueia_abuso_no_boletim(self):
        payload = {
            "cpf": "11111111111",
            "data_nascimento": "2017-01-01",
        }
        for _ in range(2):
            response = self.client.post(
                reverse("site_publico:boletim"),
                payload,
                REMOTE_ADDR="198.51.100.20",
            )
            self.assertNotEqual(response.status_code, 429)

        bloqueado = self.client.post(
            reverse("site_publico:boletim"),
            payload,
            REMOTE_ADDR="198.51.100.20",
        )
        self.assertEqual(bloqueado.status_code, 429)

    def test_upload_com_extensao_de_imagem_e_conteudo_invalido_e_rejeitado(self):
        arquivo = SimpleUploadedFile(
            "imagem.jpg",
            b"isto-nao-e-uma-imagem",
            content_type="image/jpeg",
        )
        with self.assertRaises(ValidationError):
            validar_imagem_upload(arquivo)

    def test_cadastro_usuario_aplica_perfis_selecionados(self):
        admin = get_user_model().objects.create_superuser(
            username="admin_perfis",
            email="admin-perfis@example.invalid",
            password="Senha-Admin-Perfis-2026!",
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("cadastro"),
            {
                "username": "servidor_limitado",
                "email": "servidor@example.invalid",
                "password": "Senha-Forte-Servidor-2026!",
                "perfis": ["secretaria", "historico"],
            },
        )

        self.assertEqual(response.status_code, 302)
        criado = get_user_model().objects.get(username="servidor_limitado")
        grupos = set(criado.groups.values_list("name", flat=True))
        self.assertIn(GRUPO_SECRETARIA, grupos)
        self.assertIn(GRUPO_HISTORICO, grupos)
        self.assertNotIn("EMECA - Administração", grupos)

