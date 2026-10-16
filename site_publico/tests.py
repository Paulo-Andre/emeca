from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import PaginaPublicaForm
from .models import ArquivoPaginaPublica, Aviso, Noticia, PaginaPublica, SecaoPagina


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
            "site_publico:boletim",
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


    def test_gestao_site_exige_autenticacao(self):
        response = self.client.get(reverse("site_publico:gestao_site"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_usuario_autenticado_acessa_gestao_site(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_site",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("site_publico:gestao_site"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gestão do Site")
        self.assertContains(response, "Páginas públicas")

    def test_pagina_desativada_some_do_menu_e_retorna_404(self):
        pagina = PaginaPublica.objects.get(chave="noticias")
        pagina.ativa = False
        pagina.save(update_fields=["ativa", "atualizado_em"])

        home = self.client.get(reverse("site_publico:home"))
        pagina_response = self.client.get(reverse("site_publico:noticias"))

        self.assertEqual(home.status_code, 200)
        self.assertNotContains(home, 'href="/noticias/"')
        self.assertEqual(pagina_response.status_code, 404)

    def test_matricula_desativada_bloqueia_landing_e_formulario(self):
        pagina = PaginaPublica.objects.get(chave="matricula")
        pagina.ativa = False
        pagina.save(update_fields=["ativa", "atualizado_em"])

        home = self.client.get(reverse("site_publico:home"))
        landing = self.client.get(reverse("site_publico:matricula_landing"))
        formulario = self.client.get(reverse("matricula_publica"))

        self.assertNotContains(home, 'href="/matricula-escolar/"')
        self.assertEqual(landing.status_code, 404)
        self.assertEqual(formulario.status_code, 404)


    def test_configuracao_publica_reflete_pagina_desativada(self):
        pagina = PaginaPublica.objects.get(chave="boletim")
        pagina.ativa = False
        pagina.save(update_fields=["ativa", "atualizado_em"])

        response = self.client.get(reverse("site_publico:configuracao_publica"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["paginas"]["boletim"])


    def test_editor_de_textos_e_imagens_exige_autenticacao(self):
        response = self.client.get(reverse("site_publico:gestao_secoes"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_usuario_autenticado_edita_bloco_e_alteracao_aparece_no_site(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="editor_site",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)
        secao = SecaoPagina.objects.get(chave="boletim_consulta")

        response = self.client.post(
            reverse("site_publico:gestao_secao_editar", args=[secao.chave]),
            {
                "ativa": "on",
                "rotulo": "Boletim da escola",
                "titulo": "Resultados e acompanhamento",
                "texto": "Texto atualizado pela equipe autenticada.",
            },
        )

        self.assertEqual(response.status_code, 302)
        secao.refresh_from_db()
        self.assertEqual(secao.titulo, "Resultados e acompanhamento")

        pagina = self.client.get(reverse("site_publico:boletim"))
        self.assertContains(pagina, "Resultados e acompanhamento")
        self.assertContains(pagina, "Texto atualizado pela equipe autenticada.")


    def test_formulario_de_pagina_aceita_pdf_como_capa(self):
        pagina = PaginaPublica.objects.get(chave="documentos")
        pdf = SimpleUploadedFile(
            "orientacoes.pdf",
            b"%PDF-1.4\n% teste\n",
            content_type="application/pdf",
        )
        form = PaginaPublicaForm(
            data={
                "ativa": "on",
                "rotulo": pagina.rotulo,
                "titulo": pagina.titulo,
                "subtitulo": pagina.subtitulo,
                "texto_principal": pagina.texto_principal,
            },
            files={"imagem_capa": pdf},
            instance=pagina,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_desmarcar_ativa_desativa_contato_mesmo_com_arquivo_invalido(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_visibilidade",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)
        pagina = PaginaPublica.objects.get(chave="contato")
        arquivo_invalido = SimpleUploadedFile(
            "planilha.xls",
            b"arquivo-invalido",
            content_type="application/vnd.ms-excel",
        )

        response = self.client.post(
            reverse("site_publico:gestao_pagina_editar", args=[pagina.chave]),
            {
                "rotulo": pagina.rotulo,
                "titulo": pagina.titulo,
                "subtitulo": pagina.subtitulo,
                "texto_principal": pagina.texto_principal,
                "imagem_capa": arquivo_invalido,
            },
        )

        self.assertEqual(response.status_code, 200)
        pagina.refresh_from_db()
        self.assertFalse(pagina.ativa)
        self.assertEqual(self.client.get(reverse("site_publico:contato")).status_code, 404)

        home = self.client.get(reverse("site_publico:home"))
        self.assertNotContains(home, 'href="/contato/"')


    def test_usuario_pode_adicionar_varios_documentos_na_mesma_pagina(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_documentos",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)
        pagina = PaginaPublica.objects.get(chave="documentos")
        arquivo1 = SimpleUploadedFile(
            "regimento.pdf",
            b"%PDF-1.4\nregimento\n",
            content_type="application/pdf",
        )
        arquivo2 = SimpleUploadedFile(
            "calendario.xlsx",
            b"planilha-teste",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(
            reverse("site_publico:gestao_pagina_documentos_adicionar", args=[pagina.chave]),
            {"documentos": [arquivo1, arquivo2]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ArquivoPaginaPublica.objects.filter(pagina=pagina).count(), 2)

        publica = self.client.get(reverse("site_publico:documentos"))
        self.assertContains(publica, "regimento.pdf")
        self.assertContains(publica, "calendario.xlsx")

    def test_documento_anexo_pode_ser_excluido_individualmente(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_exclusao_documentos",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)
        pagina = PaginaPublica.objects.get(chave="documentos")
        documento = ArquivoPaginaPublica.objects.create(
            pagina=pagina,
            titulo="arquivo.pdf",
            arquivo=SimpleUploadedFile(
                "arquivo.pdf",
                b"%PDF-1.4\n",
                content_type="application/pdf",
            ),
        )

        response = self.client.post(
            reverse(
                "site_publico:gestao_pagina_documento_excluir",
                args=[pagina.chave, documento.pk],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ArquivoPaginaPublica.objects.filter(pk=documento.pk).exists())


    def test_pagina_inicial_tem_editor_dedicado(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_home",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("site_publico:gestao_inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editar página inicial")
        self.assertContains(response, "Título, texto e pilares")
        self.assertContains(response, "Carrossel, avisos e destaques")

    def test_editor_da_pagina_inicial_salva_conteudo(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="editor_home",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("site_publico:gestao_inicio"),
            {
                "home_titulo": "Nossa escola, nosso futuro",
                "home_texto": "Texto atualizado da página inicial.",
                "home_pilar1_titulo": "Aprender",
                "home_pilar1_texto": "Aprender todos os dias.",
                "home_pilar2_titulo": "Conviver",
                "home_pilar2_texto": "Conviver com respeito.",
                "home_pilar3_titulo": "Participar",
                "home_pilar3_texto": "Família e comunidade presentes.",
            },
        )

        self.assertEqual(response.status_code, 302)
        pagina = self.client.get(reverse("site_publico:home"))
        self.assertContains(pagina, "Nossa escola, nosso futuro")
        self.assertContains(pagina, "Texto atualizado da página inicial.")

    def test_lista_de_paginas_mostra_pagina_inicial(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_lista_home",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("site_publico:gestao_paginas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Página inicial")
        self.assertContains(response, reverse("site_publico:gestao_inicio"))
