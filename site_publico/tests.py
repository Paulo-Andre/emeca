from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pandas as pd

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastro.models import matricula
from usuarioSec.models import declaracao

from .boletim_importacao import ler_planilha_boletim
from .boletim_services import importar_dados_boletim, localizar_alunos_por_credenciais, sincronizar_perfil_matricula
from .forms import (
    BoletimImportacaoForm,
    FotoGaleriaLoteForm,
    PaginaPublicaForm,
    PeriodoBoletimForm,
    get_content_form,
)
from .models import (
    AlbumGaleria,
    AlunoBoletim,
    BoletimAluno,
    ArquivoPaginaPublica,
    Aviso,
    FotoGaleria,
    Noticia,
    DisciplinaBoletim,
    NotaBoletim,
    PaginaPublica,
    PeriodoBoletim,
    SecaoPagina,
)


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
        self.assertContains(response, "O que você quer alterar?")
        self.assertContains(response, "Apresentação")
        self.assertContains(response, "Blocos da página")
        self.assertContains(response, "Carrossel e avisos")
        self.assertContains(response, "Conteúdos em destaque")
        self.assertContains(response, 'data-home-tab-target="apresentacao"')

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


    def test_editor_home_retorna_para_aba_de_blocos(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="editor_home_retorno",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)
        secao = SecaoPagina.objects.get(chave="home_avisos")

        response = self.client.get(
            reverse("site_publico:gestao_secao_editar", args=[secao.chave]) + "?origem=home"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("site_publico:gestao_inicio") + "#blocos",
        )


    def test_tela_de_fotos_permite_nome_de_novo_album_e_varias_imagens(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_galeria_lote",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        response = self.client.get(
            reverse("site_publico:gestao_conteudo_novo", args=["fotos"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nome do novo álbum")
        self.assertContains(response, "Escolher várias fotos")
        self.assertContains(response, 'name="fotos"')
        self.assertContains(response, "multiple")

    def test_cria_novo_album_e_adiciona_varias_fotos_de_uma_vez(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_novo_album",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        foto1 = SimpleUploadedFile(
            "foto-1.jpg",
            b"imagem-1",
            content_type="image/jpeg",
        )
        foto2 = SimpleUploadedFile(
            "foto-2.png",
            b"imagem-2",
            content_type="image/png",
        )
        foto3 = SimpleUploadedFile(
            "foto-3.webp",
            b"imagem-3",
            content_type="image/webp",
        )

        response = self.client.post(
            reverse("site_publico:gestao_conteudo_novo", args=["fotos"]),
            {
                "novo_album": "Festa Junina 2026",
                "descricao_album": "Momentos da festa da escola.",
                "fotos": [foto1, foto2, foto3],
            },
        )

        self.assertEqual(response.status_code, 302)
        album = AlbumGaleria.objects.get(titulo="Festa Junina 2026")
        self.assertEqual(album.fotos.count(), 3)
        self.assertEqual(album.foto_capa_id, album.fotos.first().pk)

        publica = self.client.get(reverse("site_publico:galeria"))
        self.assertContains(publica, "Festa Junina 2026")

    def test_adiciona_varias_fotos_em_album_existente(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_album_existente",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)
        album = AlbumGaleria.objects.create(titulo="Feira Cultural", ativo=True)

        foto1 = SimpleUploadedFile(
            "feira-1.jpg",
            b"imagem-1",
            content_type="image/jpeg",
        )
        foto2 = SimpleUploadedFile(
            "feira-2.jpg",
            b"imagem-2",
            content_type="image/jpeg",
        )

        response = self.client.post(
            reverse("site_publico:gestao_conteudo_novo", args=["fotos"]),
            {
                "album_existente": str(album.pk),
                "fotos": [foto1, foto2],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(FotoGaleria.objects.filter(album=album).count(), 2)


    def test_data_do_album_usa_campo_date_do_navegador(self):
        FormClass = get_content_form("albuns")
        form = FormClass()

        self.assertEqual(form.fields["data_evento"].widget.input_type, "date")
        self.assertEqual(form.fields["data_evento"].input_formats, ["%Y-%m-%d"])

    def test_data_do_album_rejeita_letras(self):
        FormClass = get_content_form("albuns")
        form = FormClass(
            data={
                "titulo": "Álbum com data inválida",
                "descricao": "",
                "data_evento": "45/45sfdsf",
                "ativo": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("data_evento", form.errors)

    def test_upload_multiplo_rejeita_data_com_letras(self):
        form = FotoGaleriaLoteForm(
            data={
                "novo_album": "Novo álbum",
                "data_evento": "45/45sfdsf",
            },
            files={
                "fotos": SimpleUploadedFile(
                    "foto.jpg",
                    b"imagem",
                    content_type="image/jpeg",
                )
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("data_evento", form.errors)


    def test_editor_do_album_permite_escolher_foto_como_capa(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_capa_album",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        album = AlbumGaleria.objects.create(titulo="Semana da Criança", ativo=True)
        foto1 = FotoGaleria.objects.create(
            album=album,
            imagem="site_publico/galeria/fotos/semana-1.jpg",
            ordem=1,
        )
        foto2 = FotoGaleria.objects.create(
            album=album,
            imagem="site_publico/galeria/fotos/semana-2.jpg",
            ordem=2,
        )

        pagina = self.client.get(
            reverse("site_publico:gestao_conteudo_editar", args=["albuns", album.pk])
        )
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Escolher uma foto como capa")
        self.assertContains(
            pagina,
            reverse(
                "site_publico:gestao_album_definir_capa",
                args=[album.pk, foto2.pk],
            ),
        )

        response = self.client.post(
            reverse(
                "site_publico:gestao_album_definir_capa",
                args=[album.pk, foto2.pk],
            )
        )
        self.assertEqual(response.status_code, 302)

        album.refresh_from_db()
        self.assertEqual(album.foto_capa_id, foto2.pk)

        publica = self.client.get(reverse("site_publico:galeria"))
        self.assertContains(publica, foto2.imagem.url)

    def test_nao_permite_definir_como_capa_foto_de_outro_album(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_capa_segura",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        album1 = AlbumGaleria.objects.create(titulo="Álbum 1", ativo=True)
        album2 = AlbumGaleria.objects.create(titulo="Álbum 2", ativo=True)
        foto_outro = FotoGaleria.objects.create(
            album=album2,
            imagem="site_publico/galeria/fotos/outra.jpg",
        )

        response = self.client.post(
            reverse(
                "site_publico:gestao_album_definir_capa",
                args=[album1.pk, foto_outro.pk],
            )
        )

        self.assertEqual(response.status_code, 404)
        album1.refresh_from_db()
        self.assertIsNone(album1.foto_capa_id)


    @staticmethod
    def _matricula_para_boletim(nome="Alice Vitória Soares Veloso", cpf_mae="123.456.789-09", cpf_responsavel=""):
        return matricula.objects.create(
            nomeDoAluno=nome,
            dataNascimentoAluno=date(2017, 8, 13),
            cpfMae=cpf_mae,
            cpfResponsavel=cpf_responsavel,
            temIrmaosEscola="NAO",
            problemaSaude="NAO",
            tratamentoSaude="NAO",
            necessidadeEspecial="NAO",
            medicamento="NAO",
            internado="NAO",
            atendimentoEspecializado="NAO",
            salaRecurso="NAO",
            gestacao="NAO",
            cras="NAO",
            visitaSocial="NAO",
            conselhoTutelar="NAO",
            atendimentoDomiciliar="NAO",
            trasporteEscolar="NAO",
        )

    @staticmethod
    def _periodo_publicado(tipo="TRIMESTRE", numero=2, ano=2026, turma="1º Tulipa"):
        return PeriodoBoletim.objects.create(
            tipo=tipo,
            numero=numero,
            ano=ano,
            turma=turma,
            regente="Helena Freitas Oliveira",
            publicado=True,
        )

    def _criar_boletim_publicado(self):
        cadastro = self._matricula_para_boletim()
        perfil = sincronizar_perfil_matricula(cadastro)
        periodo = self._periodo_publicado()
        portugues = DisciplinaBoletim.objects.create(
            periodo=periodo,
            nome="Língua Portuguesa",
            ordem=0,
        )
        matematica = DisciplinaBoletim.objects.create(
            periodo=periodo,
            nome="Matemática",
            ordem=1,
        )
        boletim = BoletimAluno.objects.create(
            periodo=periodo,
            aluno=perfil,
            numero_chamada=1,
            faltas_totais=3,
        )
        NotaBoletim.objects.create(
            boletim=boletim,
            disciplina=portugues,
            nota=Decimal("21.00"),
            faltas=None,
        )
        NotaBoletim.objects.create(
            boletim=boletim,
            disciplina=matematica,
            nota=Decimal("30.00"),
            faltas=None,
        )
        return cadastro, perfil, periodo, boletim

    def test_formulario_publico_do_boletim_pede_cpf_e_nascimento(self):
        response = self.client.get(reverse("site_publico:boletim"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CPF da mãe ou do responsável")
        self.assertContains(response, "Data de nascimento da criança")
        self.assertContains(response, "Consultar boletim")
        self.assertIn("no-store", response["Cache-Control"])

    def test_responsavel_acessa_boletim_com_cpf_da_mae_e_nascimento(self):
        self._criar_boletim_publicado()

        response = self.client.post(
            reverse("site_publico:boletim"),
            {
                "cpf": "12345678909",
                "data_nascimento": "2017-08-13",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/boletim/acesso/", response.url)

        resultado = self.client.get(response.url)
        self.assertEqual(resultado.status_code, 200)
        self.assertContains(resultado, "Alice Vitória Soares Veloso")
        self.assertContains(resultado, "Língua Portuguesa")
        self.assertContains(resultado, "21")
        self.assertContains(resultado, "Faltas totais")
        self.assertContains(resultado, "<strong>3</strong>", html=True)
        self.assertNotContains(resultado, "<th>Faltas</th>", html=True)
        self.assertContains(resultado, "Baixar boletim em PDF")
        self.assertEqual(resultado["X-Robots-Tag"], "noindex, nofollow, noarchive")

    def test_homonimos_nao_compartilham_credenciais_de_boletim(self):
        nome = "ESTUDANTE HOMONIMO SINTETICO"
        cadastro_a = self._matricula_para_boletim(
            nome=nome,
            cpf_mae="123.456.789-09",
        )
        cadastro_b = self._matricula_para_boletim(
            nome=nome,
            cpf_mae="987.654.321-00",
        )
        perfil_a = sincronizar_perfil_matricula(cadastro_a)
        perfil_b = sincronizar_perfil_matricula(cadastro_b)
        periodo = self._periodo_publicado(
            tipo="TRIMESTRE",
            numero=1,
            ano=2026,
            turma="TURMA HOMONIMOS",
        )
        BoletimAluno.objects.create(periodo=periodo, aluno=perfil_a)
        BoletimAluno.objects.create(periodo=periodo, aluno=perfil_b)

        encontrados = localizar_alunos_por_credenciais(
            "12345678909",
            date(2017, 8, 13),
        )

        self.assertEqual([aluno.pk for aluno in encontrados], [perfil_a.pk])
        self.assertNotIn(perfil_b.pk, [aluno.pk for aluno in encontrados])

    def test_cpf_errado_nao_expoe_boletim(self):
        self._criar_boletim_publicado()

        response = self.client.post(
            reverse("site_publico:boletim"),
            {
                "cpf": "99999999999",
                "data_nascimento": "2017-08-13",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não foi possível localizar um boletim")
        self.assertNotContains(response, "Língua Portuguesa")

    def test_cpf_do_responsavel_tambem_da_acesso(self):
        cadastro = self._matricula_para_boletim(
            cpf_mae="",
            cpf_responsavel="987.654.321-00",
        )
        perfil = sincronizar_perfil_matricula(cadastro)
        periodo = self._periodo_publicado()
        disciplina = DisciplinaBoletim.objects.create(
            periodo=periodo,
            nome="Artes",
            ordem=0,
        )
        boletim = BoletimAluno.objects.create(periodo=periodo, aluno=perfil)
        NotaBoletim.objects.create(
            boletim=boletim,
            disciplina=disciplina,
            nota=Decimal("28.00"),
            faltas=0,
        )

        response = self.client.post(
            reverse("site_publico:boletim"),
            {"cpf": "98765432100", "data_nascimento": "2017-08-13"},
        )

        self.assertEqual(response.status_code, 302)

    def test_pdf_do_boletim_e_baixavel_e_protegido_pela_sessao(self):
        _, _, periodo, boletim = self._criar_boletim_publicado()
        acesso = self.client.post(
            reverse("site_publico:boletim"),
            {"cpf": "12345678909", "data_nascimento": "2017-08-13"},
        )

        self.assertEqual(acesso.url, reverse("site_publico:boletim_acesso"))
        self.assertNotIn("12345678909", acesso.url)
        self.assertNotIn("2017-08-13", acesso.url)

        response = self.client.get(
            reverse("site_publico:boletim_pdf", args=[boletim.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        conteudo = b"".join(response.streaming_content)
        self.assertTrue(conteudo.startswith(b"%PDF"))

        # Outra sessão, sem as credenciais validadas, não pode reutilizar o ID.
        outro_cliente = self.client_class()
        negado = outro_cliente.get(
            reverse("site_publico:boletim_pdf", args=[boletim.pk])
        )
        self.assertEqual(negado.status_code, 404)

        # Mesmo dentro da sessão válida, um boletim não autorizado é bloqueado.
        outro_aluno = AlunoBoletim.objects.create(nome="Estudante Sintético B")
        outro_boletim = BoletimAluno.objects.create(
            periodo=periodo,
            aluno=outro_aluno,
        )
        idor = self.client.get(
            reverse("site_publico:boletim_pdf", args=[outro_boletim.pk])
        )
        self.assertEqual(idor.status_code, 404)

    def test_trimestre_nao_aceita_periodo_quatro(self):
        form = PeriodoBoletimForm(
            data={
                "tipo": "TRIMESTRE",
                "numero": 4,
                "ano": 2026,
                "turma": "1º Tulipa",
                "regente": "",
                "publicado": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("numero", form.errors)

    def test_bimestre_aceita_periodo_quatro(self):
        form = PeriodoBoletimForm(
            data={
                "tipo": "BIMESTRE",
                "numero": 4,
                "ano": 2026,
                "turma": "1º Tulipa",
                "regente": "",
                "publicado": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    @patch("site_publico.boletim_importacao.pd.read_excel")
    def test_leitor_reconhece_planilha_de_notas_e_faltas_enviada(self, read_excel):
        # Estrutura equivalente ao XLS usado pela escola:
        # o nome do regente fica abaixo do marcador REGENTE e as disciplinas
        # aparecem acima dos pares N./F.
        read_excel.return_value = pd.DataFrame([
            ["E.M EGIDIO CORDEIRO AQUINO", None, None, None, None, None, None, None],
            ["Notas e Faltas do 2º Trimestre - Turma 1º Tulipa - 2026", None, None, None, None, None, None, None],
            [None, None, "LÍNG. PORT.", None, "REGENTE", None, "MATEMÁTICA", None],
            [None, None, None, None, "Prof. Helena Freitas Oliveira", None, None, None],
            ["Num.", "Nome", "N.", "F.", None, None, "N.", "F."],
            [1, "Alice Vitória Soares Veloso", 21.0, 1, None, None, 30.0, 0],
            [2, "Arthur Gabriel Alves Lopes", 18.0, 2, None, None, 27.0, 1],
        ])
        arquivo = SimpleUploadedFile(
            "NotaseFaltasdo2TrimestreTurma1Tulipa2026.xls",
            b"xls-simulado",
            content_type="application/vnd.ms-excel",
        )

        dados = ler_planilha_boletim(arquivo)

        self.assertEqual(dados["metadados"]["tipo"], "TRIMESTRE")
        self.assertEqual(dados["metadados"]["numero"], 2)
        self.assertEqual(dados["metadados"]["ano"], 2026)
        self.assertIn("Tulipa", dados["metadados"]["turma"])
        self.assertEqual(dados["metadados"]["regente"], "Helena Freitas Oliveira")
        self.assertEqual([item["nome"] for item in dados["disciplinas"]], ["LÍNG. PORT.", "MATEMÁTICA"])
        self.assertEqual(dados["alunos"][0]["nome"], "Alice Vitória Soares Veloso")
        self.assertEqual(dados["alunos"][0]["resultados"][0]["nota"], Decimal("21.00"))
        self.assertEqual(dados["alunos"][0]["resultados"][0]["faltas"], 1)

    def test_importacao_vincula_notas_ao_aluno_da_matricula(self):
        self._matricula_para_boletim()
        dados = {
            "metadados": {
                "tipo": "TRIMESTRE",
                "numero": 2,
                "ano": 2026,
                "turma": "1º Tulipa",
                "regente": "Helena Freitas Oliveira",
                "titulo_original": "",
            },
            "disciplinas": [
                {"nome": "Língua Portuguesa", "ordem": 0, "nota_col": 2, "faltas_col": 3},
                {"nome": "Matemática", "ordem": 1, "nota_col": 4, "faltas_col": 5},
            ],
            "alunos": [
                {
                    "numero_chamada": 1,
                    "nome": "Alice Vitória Soares Veloso",
                    "nome_normalizado": "ALICE VITORIA SOARES VELOSO",
                    "resultados": [
                        {"disciplina": "Língua Portuguesa", "ordem": 0, "nota": Decimal("21.00"), "faltas": 1},
                        {"disciplina": "Matemática", "ordem": 1, "nota": Decimal("30.00"), "faltas": 0},
                    ],
                }
            ],
        }

        resultado = importar_dados_boletim(dados)

        self.assertEqual(resultado["importados"], 1)
        self.assertEqual(PeriodoBoletim.objects.count(), 1)
        self.assertEqual(BoletimAluno.objects.count(), 1)
        self.assertEqual(NotaBoletim.objects.count(), 2)
        self.assertFalse(resultado["periodo"].publicado)
        self.assertEqual(resultado["periodo"].tipo, "TRIMESTRE")
        self.assertEqual(resultado["periodo"].numero, 2)
        self.assertEqual(resultado["periodo"].ano, 2026)
        self.assertEqual(resultado["periodo"].turma, "1º Tulipa")
        self.assertEqual(resultado["periodo"].regente, "Helena Freitas Oliveira")
        self.assertEqual(
            resultado["disciplinas_detectadas"],
            ["Língua Portuguesa", "Matemática"],
        )

    def test_importacao_mantem_aluno_sem_correspondencia_em_matriculas(self):
        dados = {
            "metadados": {
                "tipo": "TRIMESTRE",
                "numero": 2,
                "ano": 2026,
                "turma": "1º Tulipa",
                "regente": "Helena Freitas Oliveira",
                "titulo_original": "",
            },
            "disciplinas": [
                {"nome": "Língua Portuguesa", "ordem": 0, "nota_col": 2, "faltas_col": 3},
                {"nome": "Matemática", "ordem": 1, "nota_col": 4, "faltas_col": 5},
            ],
            "alunos": [
                {
                    "numero_chamada": 7,
                    "nome": "Aluno Somente da Planilha",
                    "nome_normalizado": "ALUNO SOMENTE DA PLANILHA",
                    "resultados": [
                        {"disciplina": "Língua Portuguesa", "ordem": 0, "nota": Decimal("22.00"), "faltas": 1},
                        {"disciplina": "Matemática", "ordem": 1, "nota": Decimal("28.50"), "faltas": 0},
                    ],
                }
            ],
        }

        resultado = importar_dados_boletim(dados)

        self.assertEqual(resultado["importados"], 1)
        self.assertEqual(resultado["sem_cadastro"], ["Aluno Somente da Planilha"])

        boletim = BoletimAluno.objects.select_related("aluno").get()
        self.assertEqual(boletim.aluno.nome, "Aluno Somente da Planilha")
        self.assertIsNone(boletim.aluno.matricula_id)
        self.assertEqual(boletim.numero_chamada, 7)

        boletim.refresh_from_db()
        self.assertEqual(boletim.faltas_totais, 1)
        notas = {
            item.disciplina.nome: (item.nota, item.faltas)
            for item in boletim.resultados.select_related("disciplina")
        }
        self.assertEqual(notas["Língua Portuguesa"], (Decimal("22.00"), None))
        self.assertEqual(notas["Matemática"], (Decimal("28.50"), None))

    def test_importacao_com_nome_duplicado_em_matriculas_importa_sem_vinculo(self):
        self._matricula_para_boletim(nome="João da Silva")
        self._matricula_para_boletim(
            nome="João da Silva",
            cpf_mae="111.222.333-44",
        )
        dados = {
            "metadados": {
                "tipo": "TRIMESTRE",
                "numero": 2,
                "ano": 2026,
                "turma": "1º Tulipa",
                "regente": "",
                "titulo_original": "",
            },
            "disciplinas": [
                {"nome": "Artes", "ordem": 0, "nota_col": 2, "faltas_col": 3},
            ],
            "alunos": [
                {
                    "numero_chamada": 8,
                    "nome": "João da Silva",
                    "nome_normalizado": "JOAO DA SILVA",
                    "resultados": [
                        {"disciplina": "Artes", "ordem": 0, "nota": Decimal("27.00"), "faltas": 0},
                    ],
                }
            ],
        }

        resultado = importar_dados_boletim(dados)

        self.assertEqual(resultado["importados"], 1)
        self.assertEqual(resultado["ambiguos"], ["João da Silva"])
        boletim = BoletimAluno.objects.select_related("aluno").get()
        self.assertIsNone(boletim.aluno.matricula_id)
        self.assertEqual(boletim.aluno.nome, "João da Silva")

    def test_importacao_usa_cpf_e_nascimento_de_declaracoes_sem_matricula(self):
        declaracao.objects.create(
            nomeDoAluno="Aluno Somente da Declaração",
            dataNascimentoAluno=date(2019, 8, 18),
            nomeMae="Mãe Teste",
            cpfMae="138.090.846-97",
            nomeResponsavel="Responsável Teste",
            cpfResponsavel="",
        )
        dados = {
            "metadados": {
                "tipo": "TRIMESTRE",
                "numero": 2,
                "ano": 2026,
                "turma": "1º Tulipa",
                "regente": "Helena Freitas Oliveira",
                "titulo_original": "",
            },
            "disciplinas": [
                {"nome": "Matemática", "ordem": 0, "nota_col": 2, "faltas_col": 3},
            ],
            "alunos": [
                {
                    "numero_chamada": 9,
                    "nome": "Aluno Somente da Declaração",
                    "nome_normalizado": "ALUNO SOMENTE DA DECLARACAO",
                    "resultados": [
                        {"disciplina": "Matemática", "ordem": 0, "nota": Decimal("29.00"), "faltas": 0},
                    ],
                }
            ],
        }

        resultado = importar_dados_boletim(dados)

        perfil = AlunoBoletim.objects.get(nome="Aluno Somente da Declaração")
        self.assertIsNone(perfil.matricula_id)
        self.assertEqual(perfil.data_nascimento, date(2019, 8, 18))
        self.assertEqual(perfil.cpf_mae, "138.090.846-97")
        self.assertNotIn(perfil.nome, resultado["sem_acesso"])

    def test_consulta_publica_encontra_boletim_avulso_pelos_dados_da_mae_em_matriculas(self):
        periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE",
            numero=2,
            ano=2026,
            turma="1º Tulipa",
            publicado=True,
        )
        disciplina = DisciplinaBoletim.objects.create(
            periodo=periodo,
            nome="Matemática",
            ordem=0,
        )
        perfil = AlunoBoletim.objects.create(
            nome="Alice Vitória Soares Veloso",
        )
        boletim = BoletimAluno.objects.create(
            periodo=periodo,
            aluno=perfil,
            numero_chamada=1,
            faltas_totais=3,
        )
        NotaBoletim.objects.create(
            boletim=boletim,
            disciplina=disciplina,
            nota=Decimal("30.00"),
        )
        self._matricula_para_boletim(
            nome="Alice Vitória Soares Veloso",
            cpf_mae="138.090.846-97",
        )

        response = self.client.post(
            reverse("site_publico:boletim"),
            {
                "cpf": "138.090.846-97",
                "data_nascimento": "2017-08-13",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/boletim/acesso/", response.url)

    def test_importacao_soma_as_faltas_e_salva_somente_o_total(self):
        dados = {
            "metadados": {
                "tipo": "TRIMESTRE",
                "numero": 2,
                "ano": 2026,
                "turma": "1º Tulipa",
                "regente": "",
                "titulo_original": "",
            },
            "disciplinas": [
                {"nome": "Língua Portuguesa", "ordem": 0, "nota_col": 2, "faltas_col": 3},
                {"nome": "Matemática", "ordem": 1, "nota_col": 4, "faltas_col": 5},
                {"nome": "Ciências", "ordem": 2, "nota_col": 6, "faltas_col": 7},
            ],
            "alunos": [
                {
                    "numero_chamada": 1,
                    "nome": "Alice Vitória Soares Veloso",
                    "nome_normalizado": "ALICE VITORIA SOARES VELOSO",
                    "faltas_totais": 3,
                    "resultados": [
                        {"disciplina": "Língua Portuguesa", "ordem": 0, "nota": Decimal("21.00"), "faltas": 1},
                        {"disciplina": "Matemática", "ordem": 1, "nota": Decimal("30.00"), "faltas": 2},
                        {"disciplina": "Ciências", "ordem": 2, "nota": Decimal("29.00"), "faltas": 0},
                    ],
                }
            ],
        }

        resultado = importar_dados_boletim(dados)

        self.assertEqual(resultado["importados"], 1)
        boletim = BoletimAluno.objects.get()
        self.assertEqual(boletim.faltas_totais, 3)
        self.assertFalse(
            NotaBoletim.objects.filter(boletim=boletim, faltas__isnull=False).exists()
        )

    def test_consulta_publica_usa_dados_existentes_em_declaracoes(self):
        periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE",
            numero=2,
            ano=2026,
            turma="1º Tulipa",
            publicado=True,
        )
        disciplina = DisciplinaBoletim.objects.create(
            periodo=periodo,
            nome="Matemática",
            ordem=0,
        )
        perfil = AlunoBoletim.objects.create(nome="Criança Teste")
        boletim = BoletimAluno.objects.create(
            periodo=periodo,
            aluno=perfil,
            numero_chamada=5,
        )
        NotaBoletim.objects.create(
            boletim=boletim,
            disciplina=disciplina,
            nota=Decimal("28.00"),
            faltas=1,
        )
        declaracao.objects.create(
            nomeDoAluno="Criança Teste",
            dataNascimentoAluno=date(2019, 8, 18),
            cpfMae="138.090.846-97",
        )

        response = self.client.post(
            reverse("site_publico:boletim"),
            {
                "cpf": "13809084697",
                "data_nascimento": "2019-08-18",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/boletim/acesso/", response.url)

        perfil.refresh_from_db()
        self.assertEqual(perfil.data_nascimento, date(2019, 8, 18))
        self.assertEqual(perfil.cpf_mae, "138.090.846-97")

    def test_consulta_avisa_quando_dados_estao_corretos_mas_boletim_nao_publicado(self):
        periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE",
            numero=2,
            ano=2026,
            turma="1º Tulipa",
            publicado=False,
        )
        perfil = AlunoBoletim.objects.create(nome="Criança em Rascunho")
        BoletimAluno.objects.create(
            periodo=periodo,
            aluno=perfil,
            numero_chamada=6,
        )
        declaracao.objects.create(
            nomeDoAluno="Criança em Rascunho",
            dataNascimentoAluno=date(2019, 8, 18),
            cpfResponsavel="138.090.846-97",
        )

        response = self.client.post(
            reverse("site_publico:boletim"),
            {
                "cpf": "13809084697",
                "data_nascimento": "2019-08-18",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Os dados do estudante foram reconhecidos, mas o boletim ainda não foi publicado pela escola.",
        )

    def test_gestao_de_boletins_exige_login(self):
        response = self.client.get(reverse("site_publico:gestao_boletins"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_boletins_ficam_separados_da_gestao_do_site(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_boletim",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        gestao_site = self.client.get(reverse("site_publico:gestao_site"))
        self.assertEqual(gestao_site.status_code, 200)
        self.assertNotContains(gestao_site, "Acompanhamento escolar")
        self.assertNotContains(gestao_site, "Gerenciar boletins")

        url_boletins = reverse("site_publico:gestao_boletins")
        self.assertEqual(url_boletins, "/boletins/")

        lista = self.client.get(url_boletins)
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, "Editar dados dos boletins")
        self.assertContains(lista, "Importar boletim")
        self.assertNotContains(lista, "Cadastrar sem planilha")

    def test_gestao_boletins_funciona_mesmo_com_pagina_publica_boletim_desativada(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_boletim_independente",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        pagina = PaginaPublica.objects.get(chave="boletim")
        pagina.ativa = False
        pagina.save(update_fields=["ativa", "atualizado_em"])

        response = self.client.get(reverse("site_publico:gestao_boletins"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editar dados dos boletins")
        self.assertContains(response, "Importar boletim")

    def test_formulario_importacao_solicita_somente_o_arquivo(self):
        form = BoletimImportacaoForm()
        self.assertEqual(list(form.fields.keys()), ["arquivo"])
        self.assertIn("extraídos automaticamente", form.fields["arquivo"].help_text)

    def test_tela_importacao_informa_quais_dados_serao_extraidos(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_importacao_auto",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("site_publico:gestao_boletim_importar"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não é necessário preencher turma, ano, período")
        self.assertContains(response, "Organização do ano")
        self.assertContains(response, "Professor(a) regente")
        self.assertContains(response, "Disciplinas")
        self.assertNotContains(response, 'name="tipo"')
        self.assertNotContains(response, 'name="ano"')
        self.assertNotContains(response, 'name="turma"')

    def test_gestao_permite_editar_dados_e_disciplinas_sem_perder_notas(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_dados_boletim",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        _, _, periodo, boletim = self._criar_boletim_publicado()
        disciplina = periodo.disciplinas.get(nome="Língua Portuguesa")
        nota = NotaBoletim.objects.get(boletim=boletim, disciplina=disciplina)

        pagina = self.client.get(
            reverse("site_publico:gestao_boletim_periodo_editar", args=[periodo.pk])
        )
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Dados extraídos do arquivo")
        self.assertContains(pagina, "Língua Portuguesa")
        self.assertContains(pagina, "Adicionar disciplina")

        response = self.client.post(
            reverse(
                "site_publico:gestao_boletim_disciplina_editar",
                args=[periodo.pk, disciplina.pk],
            ),
            {"nome": "Língua Portuguesa e Produção Textual"},
        )
        self.assertEqual(response.status_code, 302)

        disciplina.refresh_from_db()
        nota.refresh_from_db()
        self.assertEqual(disciplina.nome, "Língua Portuguesa e Produção Textual")
        self.assertEqual(nota.disciplina_id, disciplina.pk)
        self.assertEqual(nota.nota, Decimal("21.00"))

        response = self.client.post(
            reverse("site_publico:gestao_boletim_disciplina_adicionar", args=[periodo.pk]),
            {"nome": "Tecnologia e Inovação"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            periodo.disciplinas.filter(nome="Tecnologia e Inovação").exists()
        )

    def test_gestao_permite_corrigir_turma_ano_periodo_e_regente(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_correcao_boletim",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)
        periodo = self._periodo_publicado()

        response = self.client.post(
            reverse("site_publico:gestao_boletim_periodo_editar", args=[periodo.pk]),
            {
                "tipo": "BIMESTRE",
                "numero": 1,
                "ano": 2027,
                "turma": "2º Girassol",
                "regente": "Maria Silva",
                "publicado": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        periodo.refresh_from_db()
        self.assertEqual(periodo.tipo, "BIMESTRE")
        self.assertEqual(periodo.numero, 1)
        self.assertEqual(periodo.ano, 2027)
        self.assertEqual(periodo.turma, "2º Girassol")
        self.assertEqual(periodo.regente, "Maria Silva")
        self.assertFalse(periodo.publicado)


    @patch("site_publico.boletim_importacao.pd.read_excel")
    def test_leitor_reconhece_xls_crystal_sem_celulas_nota_falta_no_cabecalho(self, read_excel):
        # Replica a característica do arquivo enviado: Num./Nome existem,
        # as disciplinas ficam acima, mas N./F. não são gravados como texto.
        read_excel.return_value = pd.DataFrame([
            ["E.M EGIDIO CORDEIRO AQUINO", None, None, None, None, None],
            ["Notas e Faltas do 2º Trimestre - Turma 1º Tulipa - 2026", None, None, None, None, None],
            [None, None, "LÍNG. PORT.", None, "MATEMÁTICA", None],
            ["Num.", "Nome", None, None, None, None],
            [1, "Alice Vitória Soares Veloso", 21.0, 1, 30.0, 0],
            [2, "Arthur Gabriel Alves Lopes", 18.0, 2, 27.0, 1],
        ])
        arquivo = SimpleUploadedFile(
            "NotaseFaltasdo2TrimestreTurma1Tulipa2026.xls",
            b"xls-crystal-simulado",
            content_type="application/vnd.ms-excel",
        )

        dados = ler_planilha_boletim(arquivo)

        self.assertEqual(
            [item["nome"] for item in dados["disciplinas"]],
            ["LÍNG. PORT.", "MATEMÁTICA"],
        )
        self.assertEqual(dados["disciplinas"][0]["nota_col"], 2)
        self.assertEqual(dados["disciplinas"][0]["faltas_col"], 3)
        self.assertEqual(dados["disciplinas"][1]["nota_col"], 4)
        self.assertEqual(dados["disciplinas"][1]["faltas_col"], 5)
        self.assertEqual(dados["alunos"][0]["resultados"][0]["nota"], Decimal("21.00"))
        self.assertEqual(dados["alunos"][0]["resultados"][0]["faltas"], 1)

    @patch("site_publico.boletim_importacao.pd.read_excel")
    def test_leitor_usa_falta_total_do_campo_geral_do_crystal(self, read_excel):
        read_excel.return_value = pd.DataFrame([
            ["E.M EGIDIO CORDEIRO AQUINO"] + [None] * 11,
            ["Notas e Faltas do 2º Trimestre - Turma 1º Tulipa - 2026"] + [None] * 11,
            [None, None, None, None, None, None, "Regente", None, "LÍNG. PORT.", None, "MATEMÁTICA", None],
            ["Num.", None, "Nome", None, None, None, None, None, None, None, None, None],
            [None, None, None, None, None, None, "N.", "F.", "N.", "F.", "N.", "F."],
            [1, None, "Alice Vitória Soares Veloso", None, None, None, None, "3", "21,00", "0", "30,00", "1"],
        ])
        arquivo = SimpleUploadedFile(
            "NotaseFaltasdo2TrimestreTurma1Tulipa2026.xls",
            b"xls-crystal-simulado",
            content_type="application/vnd.ms-excel",
        )

        dados = ler_planilha_boletim(arquivo)

        self.assertEqual(dados["alunos"][0]["faltas_totais"], 3)
        self.assertEqual(dados["alunos"][0]["resultados"][0]["faltas"], 0)
        self.assertEqual(dados["alunos"][0]["resultados"][1]["faltas"], 1)

    def test_consulta_combina_cpf_do_perfil_com_nascimento_de_declaracoes(self):
        periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE",
            numero=2,
            ano=2026,
            turma="1º Tulipa",
            publicado=True,
        )
        perfil = AlunoBoletim.objects.create(
            nome="Alice Vitória Soares Veloso",
            cpf_mae="138.090.846-97",
        )
        BoletimAluno.objects.create(
            periodo=periodo,
            aluno=perfil,
            numero_chamada=1,
            faltas_totais=3,
        )
        declaracao.objects.create(
            nomeDoAluno="Alice Vitória Soares Veloso",
            dataNascimentoAluno=date(2019, 8, 18),
        )

        response = self.client.post(
            reverse("site_publico:boletim"),
            {
                "cpf": "13809084697",
                "data_nascimento": "2019-08-18",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/boletim/acesso/", response.url)

        perfil.refresh_from_db()
        self.assertEqual(perfil.data_nascimento, date(2019, 8, 18))

    @patch("site_publico.boletim_importacao.pd.read_excel")
    def test_layout_real_alice_usa_falta_total_3_do_campo_geral(self, read_excel):
        # Espelha as posições do XLS real enviado pela escola:
        # Regente em G, total de faltas em H e disciplinas iniciando em I.
        read_excel.return_value = pd.DataFrame([
            [None] * 34,
            [None, None, None, None, None, "E.M EGIDIO CORDEIRO AQUINO"] + [None] * 28,
            [None] * 34,
            [None, None, None, None, None, "Notas e Faltas do 2º Trimestre - Turma 1º Tulipa - 2026"] + [None] * 28,
            [None] * 34,
            [None, None, None, None, None, None, "Regente", None,
             "LÍNG. PORT.", None, "EXP. LITERÁRIAS", None, "ARTES", None,
             "EDUCAÇÃO FÍSICA", None, "LEM - INGLES", None, "MATEMÁTICA", None,
             "CIÊN. NAT.", None, "GEOGRAFIA", None, "HISTORIA", None, "ENS. REL."] + [None] * 7,
            ["Num.", None, "Nome"] + [None] * 31,
            [None, None, None, None, None, None, "N.", "F.",
             "N.", "F.", "N.", "F.", "N.", "F.", "N.", "F.", "N.", "F.",
             "N.", "F.", "N.", "F.", "N.", "F.", "N.", "F.", "N.", "F."] + [None] * 6,
            [None] * 34,
            [1, None, "Alice Vitória Soares Veloso", None, None, None, None, "3",
             "21,00", None, None, None, "30,00", "0", "29,00", "1",
             "28,00", "0", "23,00", None, "25,00", None, "28,00", None,
             "26,00", None, "30,00", "0"] + [None] * 6,
        ])
        arquivo = SimpleUploadedFile(
            "NotaseFaltasdo2TrimestreTurma1Tulipa2026(1).xls",
            b"xls-real-simulado",
            content_type="application/vnd.ms-excel",
        )

        dados = ler_planilha_boletim(arquivo)

        alice = dados["alunos"][0]
        self.assertEqual(alice["nome"], "Alice Vitória Soares Veloso")
        self.assertEqual(alice["faltas_totais"], 3)
        self.assertEqual(alice["resultados"][0]["nota"], Decimal("21.00"))

    def test_consulta_combina_cpf_e_nascimento_mesmo_com_registros_duplicados(self):
        periodo = PeriodoBoletim.objects.create(
            tipo="TRIMESTRE",
            numero=2,
            ano=2026,
            turma="1º Tulipa",
            publicado=True,
        )
        perfil = AlunoBoletim.objects.create(nome="Alice Vitória Soares Veloso")
        BoletimAluno.objects.create(
            periodo=periodo,
            aluno=perfil,
            numero_chamada=1,
            faltas_totais=3,
        )

        # Duplicata legada 1: contém o CPF da mãe, mas sem data.
        matricula.objects.create(
            nomeDoAluno="Alice Vitória Soares Veloso",
            cpfMae="138.090.846-97",
            dataNascimentoAluno=None,
            temIrmaosEscola="NAO",
            problemaSaude="NAO",
            tratamentoSaude="NAO",
            necessidadeEspecial="NAO",
            medicamento="NAO",
            internado="NAO",
            atendimentoEspecializado="NAO",
            salaRecurso="NAO",
            gestacao="NAO",
            cras="NAO",
            visitaSocial="NAO",
            conselhoTutelar="NAO",
            atendimentoDomiciliar="NAO",
            trasporteEscolar="NAO",
        )

        # Duplicata legada 2 / Declarações: contém a data correta.
        declaracao.objects.create(
            nomeDoAluno="Alice Vitória Soares Veloso",
            dataNascimentoAluno=date(2019, 8, 18),
        )

        response = self.client.post(
            reverse("site_publico:boletim"),
            {
                "cpf": "138.090.846-97",
                "data_nascimento": "2019-08-18",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/boletim/acesso/", response.url)

        perfil.refresh_from_db()
        self.assertEqual(perfil.data_nascimento, date(2019, 8, 18))
        self.assertEqual(perfil.cpf_mae, "138.090.846-97")

    def test_menu_boletins_tem_apenas_importar_e_editar_dados(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_menu_boletim_simples",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("site_publico:gestao_boletins"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Importar boletim")
        self.assertContains(response, "Editar dados")
        self.assertNotContains(response, "Cadastrar período")

    def test_adicionar_aluno_manual_sem_matricula_e_lancar_notas(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_aluno_manual_boletim",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        periodo = self._periodo_publicado()
        disciplina = DisciplinaBoletim.objects.create(
            periodo=periodo,
            nome="Língua Portuguesa",
            ordem=0,
        )

        response = self.client.post(
            reverse("site_publico:gestao_boletim_aluno_novo", args=[periodo.pk]),
            {
                "aluno": "",
                "nome_aluno": "Aluno Inserido Manualmente",
                "data_nascimento": "2017-05-10",
                "cpf_mae": "123.456.789-09",
                "cpf_responsavel": "",
                "numero_chamada": 30,
                "faltas_totais": "2",
                f"nota_{disciplina.pk}": "24,50",
            },
        )

        self.assertEqual(response.status_code, 302)
        boletim = BoletimAluno.objects.select_related("aluno").get(
            periodo=periodo,
            aluno__nome="Aluno Inserido Manualmente",
        )
        self.assertIsNone(boletim.aluno.matricula_id)
        self.assertEqual(boletim.numero_chamada, 30)
        self.assertEqual(boletim.faltas_totais, 2)
        resultado = NotaBoletim.objects.get(
            boletim=boletim,
            disciplina=disciplina,
        )
        self.assertEqual(resultado.nota, Decimal("24.50"))
        self.assertIsNone(resultado.faltas)

    def test_editar_nome_e_nota_de_aluno_existente_no_boletim(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username="gestor_edita_nome_boletim",
            password="senha-segura-123",
        )
        self.client.force_login(usuario)

        _, _, periodo, boletim = self._criar_boletim_publicado()
        disciplina = periodo.disciplinas.get(nome="Língua Portuguesa")

        response = self.client.post(
            reverse(
                "site_publico:gestao_boletim_aluno_editar",
                args=[periodo.pk, boletim.pk],
            ),
            {
                "nome_aluno": "Alice Vitória Soares Veloso Corrigido",
                "data_nascimento": "2017-08-13",
                "cpf_mae": "123.456.789-09",
                "cpf_responsavel": "",
                "numero_chamada": 1,
                "faltas_totais": "3",
                f"nota_{disciplina.pk}": "25",
            },
        )

        self.assertEqual(response.status_code, 302)
        boletim.refresh_from_db()
        boletim.aluno.refresh_from_db()
        self.assertEqual(
            boletim.aluno.nome,
            "Alice Vitória Soares Veloso Corrigido",
        )
        resultado = NotaBoletim.objects.get(
            boletim=boletim,
            disciplina=disciplina,
        )
        self.assertEqual(resultado.nota, Decimal("25.00"))
        self.assertIsNone(resultado.faltas)
        boletim.refresh_from_db()
        self.assertEqual(boletim.faltas_totais, 3)
