from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Aviso, Noticia


class SitePublicoTests(TestCase):
    def test_home_e_publica(self):
        response = self.client.get(reverse("site_publico:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E. M. Egídio Cordeiro Aquino")
        self.assertContains(response, 'class="hero-carousel"')
        self.assertContains(response, 'data-carousel')

    def test_paginas_principais_sao_publicas(self):
        nomes = [
            "site_publico:escola",
            "site_publico:vida_escolar",
            "site_publico:atividades",
            "site_publico:projetos",
            "site_publico:noticias",
            "site_publico:galeria",
            "site_publico:matricula_landing",
            "site_publico:documentos",
            "site_publico:faq",
            "site_publico:contato",
        ]
        for nome in nomes:
            with self.subTest(nome=nome):
                response = self.client.get(reverse(nome))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="menu-principal"')

    def test_area_de_avisos_some_quando_nao_ha_aviso(self):
        response = self.client.get(reverse("site_publico:home"))
        self.assertNotContains(response, 'id="avisos-escola"')

    def test_area_de_avisos_aparece_quando_ha_aviso_ativo(self):
        Aviso.objects.create(titulo="Reunião", texto="Reunião com responsáveis.", ativo=True)
        response = self.client.get(reverse("site_publico:home"))
        self.assertContains(response, 'id="avisos-escola"')
        self.assertContains(response, "Reunião com responsáveis.")

    def test_aviso_expirado_nao_aparece(self):
        Aviso.objects.create(
            titulo="Antigo",
            texto="Não deve aparecer.",
            ativo=True,
            fim=timezone.now() - timedelta(minutes=1),
        )
        response = self.client.get(reverse("site_publico:home"))
        self.assertNotContains(response, "Não deve aparecer.")


    def test_noticia_com_imagem_entra_no_carrossel(self):
        noticia = Noticia.objects.create(
            titulo="Feira Cultural",
            resumo="Um dia de aprendizagem e participação.",
            conteudo="Conteúdo da notícia.",
            imagem="site_publico/noticias/feira-cultural.jpg",
            publicado_em=timezone.now(),
            ativo=True,
            destaque=True,
        )

        response = self.client.get(reverse("site_publico:home"))

        self.assertEqual(response.status_code, 200)
        slides = response.context["slides_home"]
        self.assertTrue(
            any(
                slide["rotulo"] == "Notícia"
                and slide["titulo"] == noticia.titulo
                and slide["imagem"].endswith("feira-cultural.jpg")
                for slide in slides
            )
        )
        self.assertContains(response, "Feira Cultural")
        self.assertContains(response, "hero-carousel")

    def test_noticia_futura_nao_aparece(self):
        Noticia.objects.create(
            titulo="Futura",
            conteudo="Conteúdo futuro",
            publicado_em=timezone.now() + timedelta(days=1),
            ativo=True,
        )
        response = self.client.get(reverse("site_publico:home"))
        self.assertNotContains(response, "Futura")
