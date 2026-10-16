import re
import time
import unicodedata
from xml.sax.saxutils import escape
from collections import defaultdict
from io import BytesIO

from django.core import signing
from django.db import transaction

from cadastro.models import matricula
from usuarioSec.models import declaracao

from .boletim_importacao import normalizar_nome
from .models import (
    AlunoBoletim,
    BoletimAluno,
    DisciplinaBoletim,
    NotaBoletim,
    PeriodoBoletim,
)


TOKEN_SALT = "site-publico-boletim-v1"
TOKEN_MAX_AGE = 30 * 60
TENTATIVAS_JANELA = 15 * 60
TENTATIVAS_LIMITE = 5


def somente_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def formatar_cpf(valor):
    digitos = somente_digitos(valor)
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return (valor or "").strip()


def sincronizar_perfil_matricula(aluno_matricula):
    perfil, _ = AlunoBoletim.objects.get_or_create(
        matricula=aluno_matricula,
        defaults={
            "nome": aluno_matricula.nomeDoAluno,
            "data_nascimento": aluno_matricula.dataNascimentoAluno,
            "cpf_mae": aluno_matricula.cpfMae or "",
            "cpf_responsavel": aluno_matricula.cpfResponsavel or "",
        },
    )

    alterados = []
    # O nome do boletim pode ser corrigido manualmente sem alterar a
    # matrícula. Por isso, depois que o perfil existe, sincronizamos apenas
    # os dados usados para acesso público, preservando o nome editado.
    dados = {
        "data_nascimento": aluno_matricula.dataNascimentoAluno,
        "cpf_mae": aluno_matricula.cpfMae or "",
        "cpf_responsavel": aluno_matricula.cpfResponsavel or "",
    }
    for campo, valor in dados.items():
        if getattr(perfil, campo) != valor:
            setattr(perfil, campo, valor)
            alterados.append(campo)
    if alterados:
        perfil.save(update_fields=alterados + ["atualizado_em"])
    return perfil


def _mapa_matriculas_por_nome():
    mapa = defaultdict(list)
    for aluno in matricula.objects.only(
        "id",
        "nomeDoAluno",
        "dataNascimentoAluno",
        "cpfMae",
        "cpfResponsavel",
    ):
        mapa[normalizar_nome(aluno.nomeDoAluno)].append(aluno)
    return mapa


def _mapa_declaracoes_por_nome(queryset=None):
    mapa = defaultdict(list)
    registros = queryset if queryset is not None else declaracao.objects.all()
    for aluno in registros.only(
        "id",
        "nomeDoAluno",
        "dataNascimentoAluno",
        "cpfMae",
        "cpfResponsavel",
    ):
        mapa[normalizar_nome(aluno.nomeDoAluno)].append(aluno)
    return mapa


def sincronizar_perfil_declaracao(perfil, aluno_declaracao):
    """Preenche dados de acesso do boletim a partir de Declarações.

    O nome do boletim é preservado porque pode ter sido corrigido manualmente.
    Campos vazios na declaração não apagam dados já existentes no boletim.
    """
    dados = {
        "data_nascimento": aluno_declaracao.dataNascimentoAluno,
        "cpf_mae": aluno_declaracao.cpfMae or "",
        "cpf_responsavel": aluno_declaracao.cpfResponsavel or "",
    }
    alterados = []
    for campo, valor in dados.items():
        if valor and getattr(perfil, campo) != valor:
            setattr(perfil, campo, valor)
            alterados.append(campo)

    if alterados:
        perfil.save(update_fields=alterados + ["atualizado_em"])
    return perfil


@transaction.atomic
def importar_dados_boletim(dados_planilha, dados_periodo=None):
    """Importa o boletim usando os metadados detectados no próprio arquivo."""
    metadados = dados_planilha["metadados"]
    dados_periodo = dados_periodo or {}

    tipo = (metadados.get("tipo") or "").strip().upper()
    numero = metadados.get("numero")
    ano = metadados.get("ano")
    turma = (metadados.get("turma") or "").strip()
    regente = (metadados.get("regente") or "").strip()

    faltantes = []
    if tipo not in {"BIMESTRE", "TRIMESTRE"}:
        faltantes.append("organização do ano (Bimestre/Trimestre)")
    if not numero:
        faltantes.append("período")
    if not ano:
        faltantes.append("ano letivo")
    if not turma:
        faltantes.append("turma")

    if faltantes:
        raise ValueError(
            "Não foi possível identificar automaticamente no arquivo: "
            + ", ".join(faltantes)
            + ". Verifique se a planilha segue o modelo de Notas e Faltas da escola."
        )

    limite = 4 if tipo == "BIMESTRE" else 3
    if numero < 1 or numero > limite:
        raise ValueError(
            f"O arquivo informa {numero}º {tipo.lower()}, mas para essa organização "
            f"o período deve estar entre 1 e {limite}."
        )

    periodo, criado = PeriodoBoletim.objects.get_or_create(
        tipo=tipo,
        numero=numero,
        ano=ano,
        turma=turma,
        defaults={
            "regente": regente,
            # Toda importação entra como rascunho para revisão antes da publicação.
            "publicado": False,
        },
    )
    if not criado:
        periodo.regente = regente
        periodo.publicado = False
        periodo.full_clean()
        periodo.save(update_fields=["regente", "publicado", "atualizado_em"])

    # Reimportar o mesmo período substitui os lançamentos daquele período.
    periodo.boletins.all().delete()
    periodo.disciplinas.all().delete()

    disciplinas = {}
    nomes_disciplinas = []
    for item in dados_planilha["disciplinas"]:
        nome_disciplina = (item.get("nome") or "").strip()
        if not nome_disciplina:
            continue
        disciplina = DisciplinaBoletim.objects.create(
            periodo=periodo,
            nome=nome_disciplina,
            ordem=item["ordem"],
        )
        disciplinas[normalizar_nome(nome_disciplina)] = disciplina
        nomes_disciplinas.append(nome_disciplina)

    if not disciplinas:
        raise ValueError("Nenhuma disciplina foi identificada na planilha.")

    mapa_alunos = _mapa_matriculas_por_nome()
    mapa_declaracoes = _mapa_declaracoes_por_nome()

    # Perfis sem vínculo com Matrículas são válidos no módulo de Boletins.
    # Eles permitem importar todos os nomes do arquivo e revisar depois.
    perfis_avulsos = defaultdict(list)
    for perfil_existente in AlunoBoletim.objects.filter(matricula__isnull=True):
        perfis_avulsos[normalizar_nome(perfil_existente.nome)].append(perfil_existente)

    importados = 0
    sem_cadastro = []
    ambiguos = []
    sem_acesso = []

    for linha in dados_planilha["alunos"]:
        candidatos = mapa_alunos.get(linha["nome_normalizado"], [])
        cadastro = None

        declaracoes_mesmo_nome = mapa_declaracoes.get(linha["nome_normalizado"], [])

        if len(candidatos) == 1:
            cadastro = candidatos[0]
            perfil = sincronizar_perfil_matricula(cadastro)

            # Se Matrículas estiver incompleto, aproveita também os dados
            # existentes em Declarações para CPF/data de nascimento.
            if len(declaracoes_mesmo_nome) == 1:
                perfil = sincronizar_perfil_declaracao(
                    perfil,
                    declaracoes_mesmo_nome[0],
                )

            # O boletim deve refletir o nome existente no arquivo importado.
            # Isso não altera o cadastro mestre de Matrículas.
            if perfil.nome != linha["nome"]:
                perfil.nome = linha["nome"]
                perfil.save(update_fields=["nome", "atualizado_em"])
        else:
            if not candidatos:
                sem_cadastro.append(linha["nome"])
            else:
                ambiguos.append(linha["nome"])

            existentes = perfis_avulsos.get(linha["nome_normalizado"], [])
            if len(existentes) == 1:
                perfil = existentes[0]
                if perfil.nome != linha["nome"]:
                    perfil.nome = linha["nome"]
                    perfil.save(update_fields=["nome", "atualizado_em"])
            else:
                perfil = AlunoBoletim.objects.create(nome=linha["nome"])
                perfis_avulsos[linha["nome_normalizado"]].append(perfil)

            # Mesmo sem matrícula, um registro único em Declarações fornece
            # automaticamente data de nascimento e CPF da mãe/responsável.
            if len(declaracoes_mesmo_nome) == 1:
                perfil = sincronizar_perfil_declaracao(
                    perfil,
                    declaracoes_mesmo_nome[0],
                )

        faltas_totais = linha.get("faltas_totais")
        if faltas_totais is None:
            # Compatibilidade com outros modelos de planilha que não possuem
            # o campo F. geral antes das disciplinas.
            faltas_totais = sum(
                item["faltas"] or 0
                for item in linha["resultados"]
                if item.get("faltas") is not None
            )

        boletim = BoletimAluno.objects.create(
            periodo=periodo,
            aluno=perfil,
            numero_chamada=linha["numero_chamada"],
            faltas_totais=faltas_totais,
        )

        resultados = []
        for item in linha["resultados"]:
            disciplina = disciplinas.get(normalizar_nome(item["disciplina"]))
            if disciplina is None:
                continue
            resultados.append(
                NotaBoletim(
                    boletim=boletim,
                    disciplina=disciplina,
                    nota=item["nota"],
                    # As faltas são exibidas e editadas apenas como total do
                    # período, evitando duplicação por componente curricular.
                    faltas=None,
                )
            )
        NotaBoletim.objects.bulk_create(resultados)
        importados += 1

        if not perfil.data_nascimento or not (
            somente_digitos(perfil.cpf_mae)
            or somente_digitos(perfil.cpf_responsavel)
        ):
            sem_acesso.append(perfil.nome)

    return {
        "periodo": periodo,
        "criado": criado,
        "importados": importados,
        "sem_cadastro": sem_cadastro,
        "ambiguos": ambiguos,
        "sem_acesso": sem_acesso,
        "detectado": metadados,
        "disciplinas_detectadas": nomes_disciplinas,
    }


def registrar_tentativa(request, sucesso=False):
    agora = int(time.time())
    tentativas = request.session.get("boletim_tentativas", [])
    tentativas = [
        int(valor)
        for valor in tentativas
        if agora - int(valor) < TENTATIVAS_JANELA
    ]
    if sucesso:
        request.session["boletim_tentativas"] = []
        return 0

    tentativas.append(agora)
    request.session["boletim_tentativas"] = tentativas
    request.session.modified = True
    return len(tentativas)


def consulta_bloqueada(request):
    agora = int(time.time())
    tentativas = request.session.get("boletim_tentativas", [])
    recentes = [
        int(valor)
        for valor in tentativas
        if agora - int(valor) < TENTATIVAS_JANELA
    ]
    request.session["boletim_tentativas"] = recentes
    return len(recentes) >= TENTATIVAS_LIMITE


def _adicionar_identidade(cpfs, datas, registro):
    if registro is None:
        return
    data = getattr(registro, "dataNascimentoAluno", None)
    if data:
        datas.add(data)
    cpf_mae = somente_digitos(getattr(registro, "cpfMae", ""))
    cpf_responsavel = somente_digitos(getattr(registro, "cpfResponsavel", ""))
    if cpf_mae:
        cpfs.add(cpf_mae)
    if cpf_responsavel:
        cpfs.add(cpf_responsavel)


def localizar_alunos_por_credenciais(
    cpf,
    data_nascimento,
    somente_publicados=True,
):
    """Localiza boletins com CPF do responsável + nascimento da criança.

    Cadastros antigos podem ter informações divididas entre Matrículas,
    Declarações e o próprio perfil de Boletim. Para o mesmo nome completo,
    o sistema combina essas fontes e também tolera registros duplicados,
    desde que o CPF informado e a data informada sejam encontrados entre
    os registros daquele mesmo estudante.
    """
    cpf_normalizado = somente_digitos(cpf)
    if len(cpf_normalizado) != 11:
        return []

    candidatos = AlunoBoletim.objects.select_related("matricula").distinct()
    if somente_publicados:
        candidatos = candidatos.filter(boletins__periodo__publicado=True)
    else:
        candidatos = candidatos.filter(boletins__isnull=False)

    mapa_matriculas = _mapa_matriculas_por_nome()
    mapa_declaracoes = _mapa_declaracoes_por_nome()

    encontrados = []
    vistos = set()

    for aluno in candidatos:
        if aluno.pk in vistos:
            continue

        chave_nome = normalizar_nome(aluno.nome)
        registros = []

        # O próprio perfil do boletim entra como uma fonte.
        registros.append({
            "data": aluno.data_nascimento,
            "cpf_mae": somente_digitos(aluno.cpf_mae),
            "cpf_responsavel": somente_digitos(aluno.cpf_responsavel),
            "origem": "boletim",
        })

        if aluno.matricula_id:
            registros.append({
                "data": aluno.matricula.dataNascimentoAluno,
                "cpf_mae": somente_digitos(aluno.matricula.cpfMae),
                "cpf_responsavel": somente_digitos(aluno.matricula.cpfResponsavel),
                "origem": aluno.matricula,
            })

        # Não exige mais correspondência única por nome. Duplicatas do mesmo
        # aluno são comuns nos bancos legados; as credenciais informadas é que
        # determinam qual registro é válido.
        for registro in mapa_matriculas.get(chave_nome, []):
            registros.append({
                "data": registro.dataNascimentoAluno,
                "cpf_mae": somente_digitos(registro.cpfMae),
                "cpf_responsavel": somente_digitos(registro.cpfResponsavel),
                "origem": registro,
            })

        for registro in mapa_declaracoes.get(chave_nome, []):
            registros.append({
                "data": registro.dataNascimentoAluno,
                "cpf_mae": somente_digitos(registro.cpfMae),
                "cpf_responsavel": somente_digitos(registro.cpfResponsavel),
                "origem": registro,
            })

        cpf_matches = [
            item for item in registros
            if cpf_normalizado in {item["cpf_mae"], item["cpf_responsavel"]}
        ]
        data_matches = [
            item for item in registros
            if item["data"] == data_nascimento
        ]

        # Primeiro tenta a forma mais forte: CPF e nascimento no mesmo registro.
        mesmo_registro = any(
            item["data"] == data_nascimento
            and cpf_normalizado in {item["cpf_mae"], item["cpf_responsavel"]}
            for item in registros
        )

        # Em dados legados, CPF e nascimento podem estar divididos entre
        # fontes diferentes. Como todas as fontes acima pertencem ao mesmo
        # nome completo normalizado, a combinação continua identificando o
        # mesmo estudante sem abrir acesso por apenas um dos fatores.
        if not mesmo_registro and not (cpf_matches and data_matches):
            continue

        alterados = []

        if aluno.data_nascimento != data_nascimento:
            aluno.data_nascimento = data_nascimento
            alterados.append("data_nascimento")

        cpfs_perfil = {
            somente_digitos(aluno.cpf_mae),
            somente_digitos(aluno.cpf_responsavel),
        }
        if cpf_normalizado not in cpfs_perfil:
            origem_mae = any(
                item["cpf_mae"] == cpf_normalizado
                for item in cpf_matches
            )
            if origem_mae:
                aluno.cpf_mae = formatar_cpf(cpf)
                alterados.append("cpf_mae")
            else:
                aluno.cpf_responsavel = formatar_cpf(cpf)
                alterados.append("cpf_responsavel")

        if alterados:
            aluno.save(update_fields=alterados + ["atualizado_em"])

        encontrados.append(aluno)
        vistos.add(aluno.pk)

    return encontrados


def criar_token_acesso(alunos):
    ids = sorted({aluno.pk for aluno in alunos})
    return signing.dumps({"alunos": ids}, salt=TOKEN_SALT, compress=True)


def ler_token_acesso(token):
    dados = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    ids = dados.get("alunos") or []
    return [int(pk) for pk in ids]


def aplicar_headers_privacidade(response):
    response["Cache-Control"] = "no-store, private, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Referrer-Policy"] = "same-origin"
    return response


def _pdf_texto(valor):
    if valor is None or valor == "":
        return "—"
    return str(valor)


def gerar_pdf_boletim(boletim, config_site=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Boletim - {boletim.aluno.nome}",
        author=(config_site.nome_escola if config_site else "E. M. Egídio Cordeiro Aquino"),
    )

    styles = getSampleStyleSheet()
    escola_style = ParagraphStyle(
        "Escola",
        parent=styles["Heading2"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0d3f22"),
        spaceAfter=2,
    )
    titulo_style = ParagraphStyle(
        "TituloBoletim",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=19,
        textColor=colors.HexColor("#17251b"),
        spaceAfter=3,
    )
    subtitulo_style = ParagraphStyle(
        "Subtitulo",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        textColor=colors.HexColor("#59665c"),
        spaceAfter=10,
    )
    normal = ParagraphStyle(
        "NormalBoletim",
        parent=styles["Normal"],
        alignment=TA_LEFT,
        fontSize=9,
        leading=12,
    )
    pequeno = ParagraphStyle(
        "Pequeno",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#6b746d"),
    )

    escola = (
        config_site.nome_escola
        if config_site and config_site.nome_escola
        else "E. M. Egídio Cordeiro Aquino"
    )
    cidade = (
        config_site.cidade
        if config_site and config_site.cidade
        else "Montes Claros/MG"
    )

    story = [
        Paragraph(escape(escola), escola_style),
        Paragraph("BOLETIM ESCOLAR", titulo_style),
        Paragraph(
            escape(f"{boletim.periodo.nome_periodo} · Ano letivo {boletim.periodo.ano}"),
            subtitulo_style,
        ),
    ]

    dados = [
        [
            Paragraph("<b>Aluno(a)</b>", normal),
            Paragraph(escape(boletim.aluno.nome), normal),
            Paragraph("<b>Turma</b>", normal),
            Paragraph(escape(boletim.periodo.turma), normal),
        ],
        [
            Paragraph("<b>Nascimento</b>", normal),
            Paragraph(
                boletim.aluno.data_nascimento.strftime("%d/%m/%Y")
                if boletim.aluno.data_nascimento
                else "—",
                normal,
            ),
            Paragraph("<b>Nº</b>", normal),
            Paragraph(_pdf_texto(boletim.numero_chamada), normal),
        ],
        [
            Paragraph("<b>Regente</b>", normal),
            Paragraph(escape(boletim.periodo.regente or "—"), normal),
            Paragraph("<b>Faltas totais</b>", normal),
            Paragraph(_pdf_texto(boletim.faltas_totais), normal),
        ],
        [
            Paragraph("<b>Município</b>", normal),
            Paragraph(escape(cidade), normal),
            Paragraph("", normal),
            Paragraph("", normal),
        ],
    ]
    info = Table(dados, colWidths=[27 * mm, 72 * mm, 24 * mm, 55 * mm])
    info.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd9d1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f5ee")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f0f5ee")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([info, Spacer(1, 8 * mm)])

    linhas = [["Componente curricular", "Nota"]]
    for resultado in boletim.resultados.select_related("disciplina").all():
        nota = (
            f"{resultado.nota:.2f}".replace(".", ",")
            if resultado.nota is not None
            else "—"
        )
        linhas.append([resultado.disciplina.nome, nota])

    tabela = Table(linhas, colWidths=[148 * mm, 30 * mm], repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5a2b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 1), (1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccd6ce")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8faf7")]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([tabela, Spacer(1, 14 * mm)])

    assinaturas = Table(
        [
            ["____________________________________", "____________________________________"],
            ["Professor(a) Regente", "Direção / Secretaria Escolar"],
        ],
        colWidths=[89 * mm, 89 * mm],
    )
    assinaturas.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#5c675f")),
            ]
        )
    )
    story.extend(
        [
            assinaturas,
            Spacer(1, 8 * mm),
            Paragraph(
                "Boletim emitido pelo portal da escola. Confira os dados e, em caso de dúvida, entre em contato com a secretaria.",
                pequeno,
            ),
        ]
    )

    def rodape(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#778078"))
        canvas.drawCentredString(
            A4[0] / 2,
            8 * mm,
            f"{escola} · {boletim.periodo.titulo}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    buffer.seek(0)
    return buffer
