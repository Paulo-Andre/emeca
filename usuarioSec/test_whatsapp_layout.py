"""Regressões de UI do atendimento WhatsApp. Não envia mensagens reais."""
import re

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse


class WhatsAppInboxDesignTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="design_whatsapp",
            email="ui@example.invalid",
            password="SenhaDeTeste#123",
        )
        self.client.force_login(user)

    def test_tela_carrega_tema_exclusivo_e_navegacao_mobile(self):
        resposta = self.client.get(reverse("whatsapp_mensagens"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "whatsapp-inbox-redesign.css")
        self.assertContains(resposta, 'id="backToChats"')
        self.assertContains(resposta, 'id="chatMoreMenu"')
        self.assertContains(resposta, 'class="wa-chat-more-panel"')
        self.assertContains(resposta, 'id="filterUnreadChats"')
        self.assertContains(resposta, 'id="unreadChatsCount"')
        self.assertContains(resposta, 'id="filterGroupChats"')

    def test_preserva_acoes_e_campos_essenciais(self):
        resposta = self.client.get(reverse("whatsapp_mensagens"))
        for elemento in (
            "chatSearch", "chatList", "conversation", "contactAvatar",
            "contactName", "contactNumber", "viewContactProfile",
            "identityDialog", "labelsButton", "messageSearchButton",
            "deleteChatButton", "replyForm", "replyMessage", "replyFile",
            "attachButton", "sendReply", "newChatDialog", "waNewFile",
            "contactProfileDialog", "deleteMessageDialog",
        ):
            with self.subTest(elemento=elemento):
                self.assertContains(resposta, f'id="{elemento}"')

    def test_sem_ids_html_duplicados(self):
        resposta = self.client.get(reverse("whatsapp_mensagens"))
        ids = re.findall(r'\bid="([^"]+)"', resposta.content.decode("utf-8"))
        self.assertGreater(len(ids), 40)
        self.assertEqual(len(ids), len(set(ids)))

    def test_css_contem_layout_movel_e_menu_gerencial(self):
        caminho = finders.find("css/whatsapp-inbox-redesign.css")
        self.assertTrue(caminho, "CSS institucional da tela não encontrado")
        with open(caminho, encoding="utf-8") as arquivo:
            css = arquivo.read()
        self.assertIn(".wa-inbox-shell.is-chat-open", css)
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn(".wa-chat-more-panel", css)
        self.assertIn(".wa-reply-form", css)
