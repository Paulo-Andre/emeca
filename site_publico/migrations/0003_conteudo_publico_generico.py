from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def popular_conteudo_generico(apps, schema_editor):
    ConfiguracaoSite = apps.get_model("site_publico", "ConfiguracaoSite")
    DestaqueHome = apps.get_model("site_publico", "DestaqueHome")
    Noticia = apps.get_model("site_publico", "Noticia")
    Projeto = apps.get_model("site_publico", "Projeto")
    AtividadeJogo = apps.get_model("site_publico", "AtividadeJogo")
    Evento = apps.get_model("site_publico", "Evento")
    PerguntaFrequente = apps.get_model("site_publico", "PerguntaFrequente")

    configuracao, _ = ConfiguracaoSite.objects.get_or_create(
        pk=1,
        defaults={
            "nome_escola": "E. M. Egídio Cordeiro Aquino",
            "subtitulo": "Educação, acolhimento e aprendizagem construídos juntos.",
            "cidade": "Montes Claros/MG",
        },
    )

    campos_genericos = {
        "apresentacao": (
            "A Escola Municipal Egídio Cordeiro Aquino é um espaço de aprendizagem, "
            "convivência e desenvolvimento. O trabalho escolar busca aproximar estudantes, "
            "famílias e comunidade, valorizando o respeito, a participação e o compromisso "
            "com a educação pública."
        ),
        "historia": (
            "A trajetória da escola é construída diariamente por estudantes, famílias e "
            "profissionais da educação. Este espaço foi preparado para registrar momentos "
            "importantes, projetos, conquistas e acontecimentos que fazem parte da memória "
            "da comunidade escolar."
        ),
        "missao_valores": (
            "Nossa missão é contribuir para a formação integral dos estudantes por meio de "
            "experiências de aprendizagem significativas, acolhedoras e responsáveis. "
            "Valorizamos o respeito, a cooperação, a inclusão, a curiosidade, a autonomia, "
            "o cuidado com o outro e a participação das famílias na vida escolar."
        ),
        "vida_escolar": (
            "A vida escolar envolve muito mais do que as aulas. Ao longo do ano, estudantes "
            "participam de atividades pedagógicas, projetos, avaliações, momentos de leitura, "
            "ações culturais e experiências de convivência. As famílias são parceiras nesse "
            "processo e devem acompanhar comunicados, reuniões, frequência e orientações "
            "publicadas pela escola.\n\n"
            "Sempre que houver informações importantes sobre horários, reuniões, atividades "
            "ou alterações na rotina, elas poderão ser divulgadas neste site e na área de "
            "avisos da página inicial."
        ),
    }

    alterou = False
    for campo, valor in campos_genericos.items():
        if not getattr(configuracao, campo):
            setattr(configuracao, campo, valor)
            alterou = True
    if alterou:
        configuracao.save()

    destaques = [
        {
            "titulo": "Bem-vindos ao site da nossa escola",
            "descricao": "Um espaço para acompanhar notícias, projetos, atividades e informações importantes da comunidade escolar.",
            "categoria": "COMUNICADO",
            "texto_botao": "Conheça a escola",
            "link": "/a-escola/",
            "ordem": 10,
        },
        {
            "titulo": "Aprendizagem para além da sala de aula",
            "descricao": "Projetos e atividades ajudam a tornar a aprendizagem mais participativa, criativa e significativa.",
            "categoria": "PROJETO",
            "texto_botao": "Ver projetos",
            "link": "/projetos/",
            "ordem": 20,
        },
    ]
    for item in destaques:
        DestaqueHome.objects.get_or_create(
            titulo=item["titulo"],
            defaults={
                **item,
                "ativo": True,
            },
        )

    agora = timezone.now()
    noticias = [
        {
            "titulo": "Escola fortalece ações de leitura e aprendizagem",
            "slug": "acoes-de-leitura-e-aprendizagem",
            "resumo": "Atividades de leitura, interpretação e produção de texto fazem parte do cotidiano escolar e contribuem para diferentes aprendizagens.",
            "conteudo": (
                "A leitura está presente em diferentes momentos da rotina escolar e pode ser "
                "trabalhada de muitas formas: histórias, pesquisas, rodas de conversa, produção "
                "de textos e atividades interdisciplinares.\n\n"
                "A proposta é ampliar o contato dos estudantes com diferentes gêneros textuais, "
                "estimular a curiosidade e fortalecer a autonomia durante o processo de aprendizagem."
            ),
            "publicado_em": agora - timedelta(days=3),
            "destaque": True,
        },
        {
            "titulo": "Projetos aproximam escola, estudantes e famílias",
            "slug": "projetos-aproximam-escola-e-familias",
            "resumo": "A participação em projetos amplia as possibilidades de aprendizagem e favorece a integração da comunidade escolar.",
            "conteudo": (
                "Os projetos escolares criam oportunidades para que os estudantes investiguem, "
                "criem, compartilhem ideias e desenvolvam atividades em grupo.\n\n"
                "A participação das famílias e da comunidade contribui para tornar essas experiências "
                "ainda mais significativas e próximas da realidade dos alunos."
            ),
            "publicado_em": agora - timedelta(days=8),
            "destaque": True,
        },
        {
            "titulo": "Atividades pedagógicas incentivam participação e criatividade",
            "slug": "atividades-pedagogicas-e-criatividade",
            "resumo": "Jogos, desafios e propostas interativas podem complementar os conteúdos trabalhados em sala de aula.",
            "conteudo": (
                "Atividades diversificadas ajudam a revisar conteúdos, desenvolver estratégias "
                "de resolução de problemas e incentivar a participação dos estudantes.\n\n"
                "Neste site, a área de Atividades e Jogos poderá reunir propostas educativas "
                "organizadas por disciplina e ano escolar."
            ),
            "publicado_em": agora - timedelta(days=14),
            "destaque": False,
        },
    ]
    for item in noticias:
        Noticia.objects.get_or_create(
            slug=item["slug"],
            defaults={
                **item,
                "ativo": True,
            },
        )

    projetos = [
        {
            "titulo": "Leitura que Aproxima",
            "slug": "leitura-que-aproxima",
            "resumo": "Proposta voltada ao incentivo à leitura, à oralidade e à produção de textos.",
            "conteudo": (
                "O projeto propõe atividades de leitura e compartilhamento de histórias, com "
                "momentos de conversa, interpretação e produção dos estudantes. As ações podem "
                "ser adaptadas de acordo com as turmas e os objetivos pedagógicos de cada período."
            ),
            "destaque": True,
            "ordem": 10,
        },
        {
            "titulo": "Escola e Comunidade",
            "slug": "escola-e-comunidade",
            "resumo": "Ações para fortalecer a participação das famílias e os vínculos com a comunidade escolar.",
            "conteudo": (
                "A aproximação entre escola e família contribui para o acompanhamento da aprendizagem "
                "e para a construção de uma convivência mais participativa. O projeto pode reunir "
                "encontros, exposições, atividades coletivas e momentos de integração."
            ),
            "destaque": True,
            "ordem": 20,
        },
        {
            "titulo": "Cuidar do Nosso Espaço",
            "slug": "cuidar-do-nosso-espaco",
            "resumo": "Atividades de conscientização, responsabilidade coletiva e cuidado com o ambiente escolar.",
            "conteudo": (
                "O cuidado com os espaços compartilhados pode ser trabalhado por meio de atividades "
                "que abordem organização, sustentabilidade, responsabilidade e participação. "
                "A proposta valoriza pequenas atitudes que contribuem para o bem-estar de todos."
            ),
            "destaque": True,
            "ordem": 30,
        },
    ]
    for item in projetos:
        Projeto.objects.get_or_create(
            slug=item["slug"],
            defaults={
                **item,
                "ativo": True,
            },
        )

    atividades = [
        {
            "titulo": "Desafio da Tabuada",
            "slug": "desafio-da-tabuada",
            "descricao": (
                "Uma proposta de revisão de multiplicação com desafios progressivos. "
                "O professor pode utilizar a atividade como apoio para treino, revisão ou trabalho em grupo."
            ),
            "tipo": "DESAFIO",
            "ano_escolar": "3º ao 5º ano",
            "disciplina": "Matemática",
            "dificuldade": "MEDIO",
            "destaque": True,
            "ordem": 10,
        },
        {
            "titulo": "Quiz de Leitura e Interpretação",
            "slug": "quiz-de-leitura-e-interpretacao",
            "descricao": (
                "Atividade para estimular leitura atenta, identificação de informações e interpretação. "
                "Pode ser adaptada a diferentes textos e níveis de aprendizagem."
            ),
            "tipo": "QUIZ",
            "ano_escolar": "3º ao 5º ano",
            "disciplina": "Língua Portuguesa",
            "dificuldade": "MEDIO",
            "destaque": True,
            "ordem": 20,
        },
        {
            "titulo": "Descobrindo o Meio Ambiente",
            "slug": "descobrindo-o-meio-ambiente",
            "descricao": (
                "Proposta educativa sobre cuidado com o ambiente, uso consciente dos recursos "
                "e atitudes que podem ser adotadas na escola, em casa e na comunidade."
            ),
            "tipo": "ATIVIDADE",
            "ano_escolar": "1º ao 5º ano",
            "disciplina": "Ciências",
            "dificuldade": "FACIL",
            "destaque": True,
            "ordem": 30,
        },
        {
            "titulo": "Palavras e Significados",
            "slug": "palavras-e-significados",
            "descricao": (
                "Atividade de vocabulário para ampliar o repertório dos estudantes por meio de "
                "palavras, significados, sinônimos e construção de pequenas frases."
            ),
            "tipo": "JOGO",
            "ano_escolar": "2º ao 5º ano",
            "disciplina": "Língua Portuguesa",
            "dificuldade": "FACIL",
            "destaque": True,
            "ordem": 40,
        },
    ]
    for item in atividades:
        AtividadeJogo.objects.get_or_create(
            slug=item["slug"],
            defaults={
                **item,
                "ativo": True,
            },
        )

    perguntas = [
        (
            "Como acompanho os avisos da escola?",
            "Os avisos ativos aparecem na página inicial do site. Comunicados importantes também podem ser divulgados pelos canais oficiais utilizados pela escola.",
        ),
        (
            "Como funciona a matrícula online?",
            "O formulário online organiza os dados do estudante e dos responsáveis. O preenchimento não confirma a vaga automaticamente; a matrícula é concluída após a conferência das informações e dos documentos pela escola.",
        ),
        (
            "Onde encontro documentos e orientações?",
            "A página Documentos e Downloads reúne os arquivos públicos disponibilizados pela escola. Quando um novo documento for publicado, ele ficará disponível nessa área.",
        ),
        (
            "Onde encontro atividades para os estudantes?",
            "A página Atividades e Jogos reúne propostas por tipo, disciplina e ano escolar. Novos conteúdos podem ser adicionados ao longo do ano.",
        ),
        (
            "Como posso entrar em contato com a escola?",
            "Utilize a página Contato para enviar uma mensagem. Os demais canais oficiais, como telefone e e-mail, aparecem no site quando cadastrados pela equipe escolar.",
        ),
    ]
    for ordem, (pergunta, resposta) in enumerate(perguntas, start=10):
        PerguntaFrequente.objects.get_or_create(
            pergunta=pergunta,
            defaults={
                "resposta": resposta,
                "ativo": True,
                "ordem": ordem,
            },
        )

    eventos = [
        {
            "titulo": "Encontro com as famílias",
            "descricao": "Momento de diálogo, orientações e acompanhamento da vida escolar.",
            "inicio": agora + timedelta(days=21),
            "local": "Escola",
        },
        {
            "titulo": "Mostra de atividades dos estudantes",
            "descricao": "Exposição de trabalhos, produções e experiências desenvolvidas pelas turmas.",
            "inicio": agora + timedelta(days=45),
            "local": "Escola",
        },
    ]
    for item in eventos:
        Evento.objects.get_or_create(
            titulo=item["titulo"],
            defaults={
                **item,
                "ativo": True,
            },
        )


def remover_conteudo_generico(apps, schema_editor):
    DestaqueHome = apps.get_model("site_publico", "DestaqueHome")
    Noticia = apps.get_model("site_publico", "Noticia")
    Projeto = apps.get_model("site_publico", "Projeto")
    AtividadeJogo = apps.get_model("site_publico", "AtividadeJogo")
    Evento = apps.get_model("site_publico", "Evento")
    PerguntaFrequente = apps.get_model("site_publico", "PerguntaFrequente")

    DestaqueHome.objects.filter(
        titulo__in=[
            "Bem-vindos ao site da nossa escola",
            "Aprendizagem para além da sala de aula",
        ]
    ).delete()
    Noticia.objects.filter(
        slug__in=[
            "acoes-de-leitura-e-aprendizagem",
            "projetos-aproximam-escola-e-familias",
            "atividades-pedagogicas-e-criatividade",
        ]
    ).delete()
    Projeto.objects.filter(
        slug__in=[
            "leitura-que-aproxima",
            "escola-e-comunidade",
            "cuidar-do-nosso-espaco",
        ]
    ).delete()
    AtividadeJogo.objects.filter(
        slug__in=[
            "desafio-da-tabuada",
            "quiz-de-leitura-e-interpretacao",
            "descobrindo-o-meio-ambiente",
            "palavras-e-significados",
        ]
    ).delete()
    Evento.objects.filter(
        titulo__in=[
            "Encontro com as famílias",
            "Mostra de atividades dos estudantes",
        ]
    ).delete()
    PerguntaFrequente.objects.filter(
        pergunta__in=[
            "Como acompanho os avisos da escola?",
            "Como funciona a matrícula online?",
            "Onde encontro documentos e orientações?",
            "Onde encontro atividades para os estudantes?",
            "Como posso entrar em contato com a escola?",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0002_configuracao_inicial")]

    operations = [
        migrations.RunPython(popular_conteudo_generico, remover_conteudo_generico),
    ]
