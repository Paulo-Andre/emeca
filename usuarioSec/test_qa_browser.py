"""Testes de caixa preta/UX com navegador Chromium (Playwright).

A execução normal Django ignora este módulo quando Playwright não está
instalado. O workflow qa-navegador.yml o instala em ambiente isolado.
Nenhum WhatsApp é acessado; toda conversa é um fixture fictício.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright, "Requer Playwright no workflow de navegador")
class QANavegadorWhatsAppTests(StaticLiveServerTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="qa_browser",
            password="SenhaSinteticaSegura!2026",
            email="qa@example.invalid",
        )
        self.client.force_login(self.user)

    def abrir(self, largura, altura):
        motor = sync_playwright().start()
        navegador = motor.chromium.launch(headless=True, args=["--no-sandbox"])
        contexto = navegador.new_context(
            viewport={"width": largura, "height": altura},
            device_scale_factor=1,
        )
        contexto.add_cookies([{
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }])
        # Detecta falhas por script CDN, em vez de depender da rede externa.
        contexto.route("https://**/*", lambda route: route.abort())
        pagina = contexto.new_page()
        falhas_js = []
        pagina.on("pageerror", lambda erro: falhas_js.append(str(erro)))
        return motor, navegador, contexto, pagina, falhas_js

    @staticmethod
    def fixture_chats():
        jid = "5538999990000@s.whatsapp.net"
        return [{
            "jid": jid,
            "phoneJid": jid,
            "name": "RESPONSAVEL QA SINTETICO",
            "notify": "QA",
            "naoLidas": 2,
            "lastMessage": {"content": "Mensagem de teste"},
        }]

    def iniciar_fake_gateway(self):
        from contextlib import ExitStack
        stack = ExitStack()
        mod = "usuarioSec.whatsapp_views"
        falsos = {
            "gateway_configurado": lambda: True,
            "obter_sessao": lambda: {"data": {"status": "CONNECTED"}},
            "listar_chats": lambda: {"data": self.fixture_chats()},
            "_combinar_chats_e_grupos_wa": lambda c: c,
            "_enriquecer_chats": lambda c: c,
            "_filtrar_conversas_excluidas_wa": lambda u, c: c,
            "_sincronizar_nao_lidas": lambda u, c: c,
        }
        for nome, falso in falsos.items():
            stack.enter_context(patch(f"{mod}.{nome}", new=falso))
        return stack

    @staticmethod
    def fake_api(pagina):
        pagina.route(
            "**/whatsapp/chat-api/**",
            lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "messages": []}),
            ),
        )
        pagina.route(
            "**/whatsapp/chats-api/**",
            lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({
                    "ok": True, "chats": QANavegadorWhatsAppTests.fixture_chats(),
                }),
            ),
        )

    @staticmethod
    def salvar_tela(pagina, nome):
        diretorio = Path("qa_screens")
        diretorio.mkdir(exist_ok=True)
        pagina.screenshot(path=str(diretorio / nome), full_page=False)

    def test_desktop_conversas_filtros_e_anexos_sem_erro_js(self):
        motor, navegador, contexto, pagina, erros = self.abrir(1440, 900)
        try:
            self.fake_api(pagina)
            with self.iniciar_fake_gateway():
                resposta = pagina.goto(
                    self.live_server_url + "/whatsapp/mensagens/",
                    wait_until="domcontentloaded",
                )
                self.assertEqual(resposta.status, 200)
                pagina.locator("#chatList .wa-chat-item").first.wait_for(timeout=10000)
                self.assertTrue(pagina.locator(".wa-chat-list-panel").is_visible())
                self.assertTrue(pagina.locator(".wa-conversation-panel").is_visible())
                pagina.locator("#filterUnreadChats").click()
                self.assertEqual(
                    pagina.locator("#filterUnreadChats").get_attribute("aria-pressed"),
                    "true",
                )
                pagina.locator("#filterAllChats").click()
                pagina.locator("#chatList .wa-chat-item").first.click()
                pagina.locator("#replyMessage").wait_for(state="visible", timeout=10000)
                self.assertTrue(pagina.locator("#attachButton").is_visible())
                pagina.locator("#chatMoreMenu summary").click()
                self.assertTrue(
                    pagina.locator("#chatMoreMenu .wa-chat-more-panel").is_visible()
                )
                self.salvar_tela(pagina, "whatsapp_desktop_sintetico.png")
                self.assertEqual(erros, [], f"Erros JavaScript: {erros}")
        finally:
            contexto.close()
            navegador.close()
            motor.stop()

    def test_mobile_abre_conversa_e_retorna_a_lista(self):
        motor, navegador, contexto, pagina, erros = self.abrir(390, 844)
        try:
            self.fake_api(pagina)
            with self.iniciar_fake_gateway():
                resposta = pagina.goto(
                    self.live_server_url + "/whatsapp/mensagens/",
                    wait_until="domcontentloaded",
                )
                self.assertEqual(resposta.status, 200)
                pagina.locator("#chatList .wa-chat-item").first.wait_for(timeout=10000)
                self.assertTrue(pagina.locator(".wa-chat-list-panel").is_visible())
                self.assertFalse(pagina.locator(".wa-conversation-panel").is_visible())
                pagina.locator("#chatList .wa-chat-item").first.click()
                pagina.locator("#replyMessage").wait_for(state="visible", timeout=10000)
                self.assertTrue(pagina.locator(".wa-conversation-panel").is_visible())
                self.assertFalse(pagina.locator(".wa-chat-list-panel").is_visible())
                self.assertTrue(pagina.locator("#backToChats").is_visible())
                self.salvar_tela(pagina, "whatsapp_mobile_sintetico.png")
                pagina.locator("#backToChats").click()
                self.assertTrue(pagina.locator(".wa-chat-list-panel").is_visible())
                self.assertFalse(pagina.locator(".wa-conversation-panel").is_visible())
                self.assertEqual(erros, [], f"Erros JavaScript: {erros}")
        finally:
            contexto.close()
            navegador.close()
            motor.stop()
