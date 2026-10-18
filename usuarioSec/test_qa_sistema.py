"""Auditoria QA caixa cinza: contratos HTTP, perfis, privacidade e usabilidade.

Tudo roda na base de TESTES do Django com dados sintéticos. Nenhum contato
WhatsApp é usado e nenhuma mensagem ou boletim real é enviado.
"""
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .access_control import GRUPO_SECRETARIA, GRUPO_HISTORICO


class ArvoreHTML(HTMLParser):
    """Detecta identificadores repetidos e formulários aninhados."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.erros = []
        self.form_depth = 0
        self.secoes = 0
        self.botoes_sem_nome = 0
        self._botao = None

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if props.get("id"):
            self.ids.append(props["id"])
        if tag == "form":
            self.form_depth += 1
            if self.form_depth > 1:
                self.erros.append("Formulário aninhado")
        if tag == "main":
            self.secoes += 1
        if tag == "button":
            self._botao = {
                "nome": bool(props.get("aria-label") or props.get("title")),
                "tipo": props.get("type", ""),
                "texto": "",
            }

    def handle_data(self, data):
        if self._botao:
            self._botao["texto"] += data.strip()

    def handle_endtag(self, tag):
        if tag == "form":
            self.form_depth -= 1
        if tag == "button" and self._botao:
            if not self._botao["nome"] and not self._botao["texto"].strip():
                self.botoes_sem_nome += 1
            self._botao = None


@override_settings(EMECA_RBAC_STRICT=True, RATE_LIMIT_ENABLED=False)
class QACaixaCinzaSistemaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.administrador = User.objects.create_superuser(
            username="qa_admin", email="qa@example.invalid",
            password="SenhaSinteticaSegura!2026",
        )
        self.secretaria = User.objects.create_user(
            username="qa_secretaria", password="SenhaSinteticaSegura!2026",
        )
        grupo, _ = Group.objects.get_or_create(name=GRUPO_SECRETARIA)
        self.secretaria.groups.add(grupo)
        self.historico = User.objects.create_user(
            username="qa_historico", password="SenhaSinteticaSegura!2026",
        )
        grupo_hist, _ = Group.objects.get_or_create(name=GRUPO_HISTORICO)
        self.historico.groups.add(grupo_hist)

    def test_telas_publicas_abrem_sem_autenticacao(self):
        cliente = Client()
        rotas = [
            reverse("site_publico:home"),
            reverse("site_publico:boletim"),
            reverse("site_publico:matricula_landing"),
            reverse("site_publico:contato"),
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                resposta = cliente.get(rota)
                self.assertEqual(resposta.status_code, 200, rota)

    def test_rotas_privadas_nao_vazam_conteudo_sem_login(self):
        cliente = Client()
        rotas = [
            reverse("dashboard"),
            reverse("telaDeclaracao"),
            reverse("site_publico:gestao_boletins"),
            reverse("site_publico:gestao_site"),
            reverse("historico:inicio"),
            reverse("whatsapp_mensagens"),
            reverse("whatsapp_gerenciamento"),
            reverse("gerenciar_acessos"),
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                resposta = cliente.get(rota)
                self.assertIn(resposta.status_code, (302, 403, 404), rota)
                self.assertNotEqual(resposta.status_code, 200, rota)

    def test_smoke_painel_de_cada_modulo_administrativo(self):
        self.client.force_login(self.administrador)
        rotas = [
            "dashboard", "telaDeclaracao", "historico:inicio",
            "site_publico:gestao_boletins",
            "site_publico:gestao_boletim_importar",
            "site_publico:gestao_site", "whatsapp_mensagens",
            "whatsapp_gerenciamento", "whatsapp",
        ]
        # Indisponibilidade simulada: jamais chama a conta WA-AKG real.
        with patch(
            "usuarioSec.whatsapp_views.gateway_configurado",
            return_value=False,
        ):
            for nome in rotas:
                with self.subTest(rota=nome):
                    resposta = self.client.get(reverse(nome))
                    self.assertEqual(resposta.status_code, 200, nome)

    def test_usuario_restrito_nao_ganha_acesso_a_outros_modulos(self):
        for usuario, permitido, negado in [
            (self.secretaria, "telaDeclaracao", "historico:inicio"),
            (self.historico, "historico:inicio", "telaDeclaracao"),
        ]:
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.username):
                self.assertEqual(
                    self.client.get(reverse(permitido)).status_code, 200,
                )
                self.assertEqual(
                    self.client.get(reverse(negado)).status_code, 403,
                )

    def test_whatsapp_nao_tem_forms_aninhados_ids_duplicados_ou_botoes_sem_nome(self):
        self.client.force_login(self.administrador)
        with patch(
            "usuarioSec.whatsapp_views.gateway_configurado",
            return_value=False,
        ):
            resposta = self.client.get(reverse("whatsapp_mensagens"))
        self.assertEqual(resposta.status_code, 200)
        arvore = ArvoreHTML()
        arvore.feed(resposta.content.decode("utf-8"))
        self.assertEqual(arvore.erros, [])
        self.assertEqual(len(arvore.ids), len(set(arvore.ids)))
        self.assertEqual(arvore.secoes, 1)
        self.assertEqual(arvore.botoes_sem_nome, 0)

    def test_mensagem_nao_conectada_exibe_status_e_nao_autoenvia(self):
        self.client.force_login(self.administrador)
        with patch(
            "usuarioSec.whatsapp_views.gateway_configurado",
            return_value=False,
        ):
            resposta = self.client.get(reverse("whatsapp_mensagens"))
        self.assertContains(resposta, "Integração ainda não configurada")
        self.assertContains(resposta, 'id="newChatButton"')
        self.assertContains(resposta, 'id="attachButton"')
        self.assertNotContains(resposta, "Mensagem enviada.")

    def test_ajax_privado_sem_login_nao_retorna_lista_de_chats(self):
        with patch(
            "usuarioSec.whatsapp_views.gateway_configurado",
            return_value=False,
        ):
            resposta = Client().get(reverse("whatsapp_chats_api"))
        self.assertNotEqual(resposta.status_code, 200)
