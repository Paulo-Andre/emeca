from django.db import migrations, models
import django.core.validators


PAGINAS = [
    ("escola", "A Escola", "A Escola", "Conheça a identidade, os valores e o trabalho da nossa escola.", 10),
    ("vida_escolar", "Vida Escolar", "Vida Escolar", "Informações e orientações para estudantes e famílias.", 20),
    ("atividades", "Atividades e Jogos", "Atividades e Jogos", "Jogos, quizzes, desafios e materiais educativos.", 30),
    ("projetos", "Projetos", "Projetos", "Conheça ações e projetos desenvolvidos pela comunidade escolar.", 40),
    ("noticias", "Notícias", "Notícias", "Acompanhe acontecimentos, atividades e novidades da escola.", 50),
    ("galeria", "Galeria", "Galeria", "Fotos e registros de momentos da comunidade escolar.", 60),
    ("matricula", "Matrícula", "Matrícula Online", "Orientações e acesso ao formulário de matrícula.", 70),
    ("boletim", "Boletim", "Boletim", "Acompanhamento e consulta de informações escolares.", 80),
    ("documentos", "Documentos", "Documentos e Downloads", "Formulários, orientações e materiais disponibilizados pela escola.", 90),
    ("faq", "Perguntas Frequentes", "Perguntas Frequentes", "Respostas para dúvidas comuns de estudantes e famílias.", 100),
    ("contato", "Contato", "Contato", "Envie uma mensagem ou consulte os canais de atendimento.", 110),
]


def criar_paginas(apps, schema_editor):
    PaginaPublica = apps.get_model("site_publico", "PaginaPublica")
    for chave, nome, titulo, subtitulo, ordem in PAGINAS:
        PaginaPublica.objects.get_or_create(
            chave=chave,
            defaults={
                "nome": nome,
                "titulo": titulo,
                "subtitulo": subtitulo,
                "ativa": True,
                "ordem": ordem,
            },
        )


def remover_paginas(apps, schema_editor):
    PaginaPublica = apps.get_model("site_publico", "PaginaPublica")
    PaginaPublica.objects.filter(chave__in=[item[0] for item in PAGINAS]).delete()


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0003_conteudo_publico_generico")]

    operations = [
        migrations.CreateModel(
            name="PaginaPublica",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chave", models.CharField(choices=[
                    ("escola", "A Escola"), ("vida_escolar", "Vida Escolar"),
                    ("atividades", "Atividades e Jogos"), ("projetos", "Projetos"),
                    ("noticias", "Notícias"), ("galeria", "Galeria"),
                    ("matricula", "Matrícula"), ("boletim", "Boletim"),
                    ("documentos", "Documentos"), ("faq", "Perguntas Frequentes"),
                    ("contato", "Contato"),
                ], max_length=40, unique=True)),
                ("nome", models.CharField(max_length=120)),
                ("ativa", models.BooleanField(default=True)),
                ("titulo", models.CharField(blank=True, max_length=180)),
                ("subtitulo", models.CharField(blank=True, max_length=360)),
                ("texto_principal", models.TextField(blank=True)),
                ("imagem_capa", models.FileField(blank=True, upload_to="site_publico/paginas/", validators=[django.core.validators.FileExtensionValidator(["jpg", "jpeg", "png", "webp"])])),
                ("ordem", models.PositiveSmallIntegerField(default=0)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["ordem", "nome"], "verbose_name": "Página pública", "verbose_name_plural": "Páginas públicas"},
        ),
        migrations.RunPython(criar_paginas, remover_paginas),
    ]
