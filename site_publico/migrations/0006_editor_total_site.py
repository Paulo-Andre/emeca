from django.core.validators import FileExtensionValidator
from django.db import migrations, models


ROTULOS_PAGINAS = {
    "escola": "Nossa história",
    "vida_escolar": "Informações para famílias e estudantes",
    "atividades": "Aprender também pode ser divertido",
    "projetos": "Nossa escola em movimento",
    "noticias": "Acontece na escola",
    "galeria": "Memórias da escola",
    "matricula": "Para pais e responsáveis",
    "boletim": "Acompanhamento escolar",
    "documentos": "Arquivos públicos",
    "faq": "Dúvidas comuns",
    "contato": "Fale com a escola",
}


def preencher_rotulos(apps, schema_editor):
    PaginaPublica = apps.get_model("site_publico", "PaginaPublica")
    for chave, rotulo in ROTULOS_PAGINAS.items():
        PaginaPublica.objects.filter(chave=chave, rotulo="").update(rotulo=rotulo)


SECOES_INICIAIS = [
    ("home", "home_fallback_slide", "Início — carrossel alternativo", "Aprender e participar", "Atividades, projetos e notícias da escola", "Quando fotos e notícias forem publicadas, elas passam a ocupar este carrossel automaticamente.", 10),
    ("home", "home_avisos", "Início — avisos", "Comunicados", "Avisos importantes", "Informações ativas da escola", 20),
    ("home", "home_acesso", "Início — acesso rápido", "Acesso rápido", "Informações e serviços da escola", "Encontre rapidamente os principais caminhos para estudantes e famílias.", 30),
    ("home", "home_modelo", "Início — apresentação da escola", "Nossa escola", "", "Educação pública com participação e cuidado", 35),
    ("home", "home_noticias", "Início — notícias", "Acontece na escola", "Últimas notícias", "Projetos, eventos, atividades e acontecimentos da comunidade escolar.", 40),
    ("home", "home_atividades", "Início — atividades", "Aprender brincando", "Atividades e jogos em destaque", "Conteúdos para aprender, revisar e se divertir.", 50),
    ("home", "home_projetos", "Início — projetos", "Nossa escola em movimento", "Projetos em destaque", "Iniciativas que fortalecem aprendizagem, participação e convivência.", 60),
    ("home", "home_galeria", "Início — galeria", "Nossa escola em imagens", "Galeria de fotos", "Momentos que fazem parte da nossa história.", 70),
    ("home", "home_agenda", "Início — agenda", "Agenda", "Próximos acontecimentos", "", 80),
    ("home", "home_contato", "Início — contato", "Escola e família juntas", "Precisa falar com a escola?", "Use nossos canais de atendimento ou envie uma mensagem diretamente pelo site.", 90),

    ("escola", "escola_quem_somos", "A Escola — quem somos", "", "Quem somos", "", 10),
    ("escola", "escola_historia", "A Escola — nossa história", "", "Nossa história", "", 20),
    ("escola", "escola_missao", "A Escola — missão e valores", "O que nos orienta", "Missão e valores", "", 30),

    ("vida_escolar", "vida_rotina", "Vida Escolar — rotina", "", "Rotina escolar", "Informações sobre horários, entrada e saída, organização do dia e orientações gerais poderão ser publicadas pela escola.", 10),
    ("vida_escolar", "vida_aprendizagem", "Vida Escolar — aprendizagem", "", "Acompanhamento da aprendizagem", "Espaço para orientações sobre avaliações, recuperação, frequência, reuniões e acompanhamento das famílias.", 20),
    ("vida_escolar", "vida_reunioes", "Vida Escolar — reuniões e comunicados", "", "Reuniões e comunicados", "Os principais avisos aparecem automaticamente na página inicial enquanto estiverem ativos.", 30),
    ("vida_escolar", "vida_documentos", "Vida Escolar — documentos", "", "Documentos", "Formulários, orientações e arquivos públicos podem ser encontrados na área de Documentos e Downloads.", 40),

    ("matricula", "matricula_como_funciona", "Matrícula — como funciona", "Como funciona", "Preencha com calma, etapa por etapa", "O formulário foi dividido para facilitar o preenchimento pelo celular. Tenha em mãos os dados do estudante, responsáveis, endereço e contatos de emergência.", 10),
    ("matricula", "matricula_passo1", "Matrícula — passo 1", "", "Confirme a orientação", "Use o formulário após a orientação da escola ou o encaminhamento do Cadastro Escolar.", 20),
    ("matricula", "matricula_passo2", "Matrícula — passo 2", "", "Preencha os dados", "Informe os dados do aluno e responsáveis. Você verá o progresso durante todo o processo.", 30),
    ("matricula", "matricula_passo3", "Matrícula — passo 3", "", "Conclua na escola", "A vaga é confirmada somente após a conferência dos documentos e a assinatura presencial.", 40),
    ("matricula", "matricula_antes", "Matrícula — antes de começar", "Antes de começar", "Tenha as informações em mãos", "Separe documentos pessoais, comprovante de residência, contatos de emergência e informações de saúde ou acompanhamento do estudante quando aplicável.", 50),
    ("matricula", "matricula_ajuda", "Matrícula — ajuda", "Precisa de ajuda?", "Estamos disponíveis", "Se tiver dúvidas antes ou durante o preenchimento, consulte as perguntas frequentes ou entre em contato com a escola.", 60),
    ("matricula", "matricula_final", "Matrícula — chamada final", "Pronto para começar?", "O formulário salva os dados durante esta sessão", "Reserve alguns minutos e revise as informações antes de finalizar.", 70),

    ("boletim", "boletim_consulta", "Boletim — consulta", "Boletim online", "Consulta de notas e resultados", "Esta área foi preparada para receber a consulta de boletins. A integração com os dados acadêmicos poderá ser adicionada posteriormente sem alterar o menu ou a identidade visual do site.", 10),
    ("boletim", "boletim_orientacao", "Boletim — orientação", "", "Precisa de orientação?", "Entre em contato com a escola para informações sobre resultados, avaliações e acompanhamento escolar.", 20),

    ("contato", "contato_informacoes", "Contato — informações da escola", "", "Informações da escola", "", 10),
]


def criar_secoes(apps, schema_editor):
    SecaoPagina = apps.get_model("site_publico", "SecaoPagina")
    for pagina, chave, nome, rotulo, titulo, texto, ordem in SECOES_INICIAIS:
        SecaoPagina.objects.update_or_create(
            chave=chave,
            defaults={
                "pagina": pagina,
                "nome": nome,
                "rotulo": rotulo,
                "titulo": titulo,
                "texto": texto,
                "ordem": ordem,
                "ativa": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0005_configuracaosite_home")]

    operations = [
        migrations.AddField(
            model_name="paginapublica",
            name="rotulo",
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.RunPython(preencher_rotulos, migrations.RunPython.noop),
        migrations.AddField(
            model_name="configuracaosite",
            name="logo_site",
            field=models.FileField(
                blank=True,
                upload_to="site_publico/configuracao/",
                validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
            ),
        ),
        migrations.CreateModel(
            name="SecaoPagina",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pagina", models.CharField(choices=[
                    ("home", "Início"),
                    ("escola", "A Escola"),
                    ("vida_escolar", "Vida Escolar"),
                    ("atividades", "Atividades e Jogos"),
                    ("projetos", "Projetos"),
                    ("noticias", "Notícias"),
                    ("galeria", "Galeria"),
                    ("matricula", "Matrícula"),
                    ("boletim", "Boletim"),
                    ("documentos", "Documentos"),
                    ("faq", "Perguntas Frequentes"),
                    ("contato", "Contato"),
                ], max_length=40)),
                ("chave", models.SlugField(max_length=90, unique=True)),
                ("nome", models.CharField(max_length=180)),
                ("rotulo", models.CharField(blank=True, help_text="Texto pequeno exibido acima do título, quando o bloco usar esse elemento.", max_length=180)),
                ("titulo", models.CharField(blank=True, max_length=220)),
                ("texto", models.TextField(blank=True)),
                ("imagem", models.FileField(blank=True, upload_to="site_publico/secoes/", validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])])),
                ("ativa", models.BooleanField(default=True)),
                ("ordem", models.PositiveSmallIntegerField(default=0)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Seção editável",
                "verbose_name_plural": "Seções editáveis",
                "ordering": ["pagina", "ordem", "nome"],
            },
        ),
        migrations.RunPython(criar_secoes, migrations.RunPython.noop),
    ]
