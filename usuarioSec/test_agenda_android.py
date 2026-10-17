from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .access_control import GRUPO_WHATSAPP
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .agenda_android import ler_agenda_vcf, normalizar_telefone_br, processar_agenda_vcf
from .models import ContatoAgendaWhatsApp
from .whatsapp_views import _enriquecer_chats


VCF = (
    "BEGIN:VCARD\nVERSION:3.0\nFN:Maria Escola\n"
    "TEL;TYPE=CELL:+55 38 99999-1234\nEND:VCARD\n"
    "BEGIN:VCARD\nVERSION:3.0\nFN:Joao Silva\n"
    "TEL:38 98888-5678\nEND:VCARD\n"
).encode("utf-8")


@override_settings(WA_AKG_SESSION_ID="teste-agenda")
class AgendaAndroidTests(TestCase):
    def test_normalizacao_sem_inventar_lid(self):
        self.assertEqual(normalizar_telefone_br("(38) 99999-1234"), "5538999991234@s.whatsapp.net")
        self.assertFalse(normalizar_telefone_br("123456789@lid"))
        self.assertFalse(normalizar_telefone_br("9999-1234"))

    def test_previa_nao_grava_e_reimportacao_nao_duplicada(self):
        contatos, stats = ler_agenda_vcf(VCF)
        self.assertEqual(len(contatos), 2)
        self.assertEqual(stats["cartoes"], 2)
        preview = processar_agenda_vcf(VCF, sessao="teste-agenda")
        self.assertEqual(preview["novos"], 2)
        self.assertFalse(ContatoAgendaWhatsApp.objects.exists())
        processar_agenda_vcf(VCF, sessao="teste-agenda", aplicar=True)
        again = processar_agenda_vcf(VCF, sessao="teste-agenda", aplicar=True)
        self.assertEqual(again["importados"], 0)
        self.assertEqual(ContatoAgendaWhatsApp.objects.count(), 2)

    def test_conflito_mesmo_numero_nao_mescla_pessoas(self):
        text = (
            "BEGIN:VCARD\nFN:Pessoa A\nTEL:38 99999-1234\nEND:VCARD\n"
            "BEGIN:VCARD\nFN:Pessoa B\nTEL:38 99999-1234\nEND:VCARD\n"
        ).encode()
        contacts, summary = ler_agenda_vcf(text)
        self.assertFalse(contacts)
        self.assertEqual(summary["conflitos_no_arquivo"], 1)

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    @patch("usuarioSec.whatsapp_views.listar_contatos", return_value={"data": []})
    def test_aparece_nome_somente_com_numero_real(self, _contacts, _connected):
        processar_agenda_vcf(VCF, sessao="teste-agenda", aplicar=True)
        chats = _enriquecer_chats([
            {"jid": "5538999991234@s.whatsapp.net"},
            {"jid": "184774392074394@lid"},
        ])
        self.assertEqual(chats[0]["name"], "Maria Escola")
        self.assertNotEqual(chats[1]["name"], "Maria Escola")

    def test_endpoint_requer_administrador(self):
        user = get_user_model().objects.create_user(username="exemplo_comum")
        self.client.force_login(user)
        response = self.client.post(
            reverse("whatsapp_importar_agenda"),
            {"modo": "importar", "arquivo": SimpleUploadedFile("agenda.vcf", VCF)},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ContatoAgendaWhatsApp.objects.exists())

    def test_preview_e_importacao_por_admin(self):
        user = get_user_model().objects.create_user(username="exemplo_admin", is_staff=True)
        grupo, _ = Group.objects.get_or_create(name=GRUPO_WHATSAPP)
        user.groups.add(grupo)
        self.client.force_login(user)
        url = reverse("whatsapp_importar_agenda")
        payload = lambda mode: {"modo": mode, "arquivo": SimpleUploadedFile("agenda.vcf", VCF)}
        preview = self.client.post(url, payload("previa"))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["resultado"]["novos"], 2)
        self.assertFalse(ContatoAgendaWhatsApp.objects.exists())
        saved = self.client.post(url, payload("importar"))
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["resultado"]["importados"], 2)

    @patch("usuarioSec.whatsapp_views.listar_contatos")
    def test_busca_unifica_agenda_e_contatos_wa(self, listar):
        processar_agenda_vcf(VCF, sessao="teste-agenda", aplicar=True)
        listar.return_value = {"data": [{
            "jid": "5538999991234@s.whatsapp.net", "name": "Nome antigo",
        }]}
        user = get_user_model().objects.create_user(username="busca_agenda")
        grupo, _ = Group.objects.get_or_create(name=GRUPO_WHATSAPP)
        user.groups.add(grupo)
        self.client.force_login(user)
        response = self.client.get(
            reverse("whatsapp_buscar_contatos_wa"), {"q": "Maria"}
        )
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["nome"], "Maria Escola")
        self.assertEqual(results[0]["jid"], "5538999991234@s.whatsapp.net")

    def test_nome_anterior_nao_e_sobrescrito(self):
        ContatoAgendaWhatsApp.objects.create(
            sessao="teste-agenda",
            telefone_jid="5538999991234@s.whatsapp.net",
            nome="Nome revisado",
        )
        result = processar_agenda_vcf(VCF, sessao="teste-agenda", aplicar=True)
        self.assertEqual(result["nomes_diferentes_preservados"], 1)
        self.assertEqual(
            ContatoAgendaWhatsApp.objects.get(
                telefone_jid="5538999991234@s.whatsapp.net"
            ).nome, "Nome revisado"
        )

    def test_vcf_acentuado_e_multiplos_telefones(self):
        data = (
            "BEGIN:VCARD\nVERSION:3.0\nFN:José Maria\n"
            "TEL:38 99999-1234\nTEL:38 98888-5678\nEND:VCARD\n"
        ).encode("utf-8")
        contacts, summary = ler_agenda_vcf(data)
        self.assertEqual(len(contacts), 2)
        self.assertEqual(summary["cartoes"], 1)
        self.assertIn("José Maria", contacts.values())

    @patch("usuarioSec.whatsapp_views.gateway_configurado", return_value=False)
    def test_gerenciamento_oferece_sincronizacao_automatica_sem_vcf_obrigatorio(self, _gateway):
        usuario = get_user_model().objects.create_user(
            username="administrador_sincronizacao", is_staff=True
        )
        grupo, _ = Group.objects.get_or_create(name=GRUPO_WHATSAPP)
        usuario.groups.add(grupo)
        self.client.force_login(usuario)
        pagina = self.client.get(reverse("whatsapp_gerenciamento"))
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Sincronização automática de contatos")
        self.assertNotContains(pagina, "Importar contatos</a>")
