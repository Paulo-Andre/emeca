import re
import time
import unicodedata
from xml.sax.saxutils import escape
from collections import defaultdict
from io import BytesIO

from django.core import signing
from django.db import transaction

from cadastro.models import matricula

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
    dados = {
        "nome": aluno_matricula.nomeDoAluno,
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


@transaction.atomic
def importar_dados_boletim(dados_planilha, dados_periodo):
    metadados = dados_planilha["metadados"]
    turma = (dados_periodo.get("turma") or metadados.get("turma") or "").strip()
    if not turma:
        raise ValueError(
            "A turma não foi identificada na planilha. Informe a turma no formulário."
        )

    regente = (dados_periodo.get("regente") or metadados.get("regente") or "").strip()

    periodo, criado = PeriodoBoletim.objects.get_or_create(
        tipo=dados_periodo["tipo"],
        numero=dados_periodo["numero"],
        ano=dados_periodo["ano"],
        turma=turma,
        defaults={
            "regente": regente,
            "publicado": bool(dados_periodo.get("publicar")),
        },
    )
    if not criado:
        periodo.regente = regente
        periodo.publicado = bool(dados_periodo.get("publicar"))
        periodo.full_clean()
        periodo.save(update_fields=["regente", "publicado", "atualizado_em"])

    # Reimportar o mesmo período substitui os lançamentos daquele período.
    periodo.boletins.all().delete()
    periodo.disciplinas.all().delete()

    disciplinas = {}
    for item in dados_planilha["disciplinas"]:
        disciplina = DisciplinaBoletim.objects.create(
            periodo=periodo,
            nome=item["nome"],
            ordem=item["ordem"],
        )
        disciplinas[normalizar_nome(item["nome"])] = disciplina

    mapa_alunos = _mapa_matriculas_por_nome()
    importados = 0
    sem_cadastro = []
    ambiguos = []
    sem_acesso = []

    for linha in dados_planilha["alunos"]:
        candidatos = mapa_alunos.get(linha["nome_normalizado"], [])
        if not candidatos:
            sem_cadastro.append(linha["nome"])
            continue
        if len(candidatos) > 1:
            ambiguos.append(linha["nome"])
            continue

        cadastro = candidatos[0]
        perfil = sincronizar_perfil_matricula(cadastro)
        boletim = BoletimAluno.objects.create(
            periodo=periodo,
            aluno=perfil,
            numero_chamada=linha["numero_chamada"],
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
                    faltas=item["faltas"],
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


def localizar_alunos_por_credenciais(cpf, data_nascimento):
    from django.db.models import Q

    cpf_normalizado = somente_digitos(cpf)
    if len(cpf_normalizado) != 11:
        return []

    candidatos = (
        AlunoBoletim.objects
        .filter(boletins__periodo__publicado=True)
        .filter(
            Q(data_nascimento=data_nascimento)
            | Q(matricula__dataNascimentoAluno=data_nascimento)
        )
        .select_related("matricula")
        .distinct()
    )
    encontrados = []
    for aluno in candidatos:
        cpfs = {
            somente_digitos(aluno.cpf_mae),
            somente_digitos(aluno.cpf_responsavel),
        }
        if aluno.matricula_id:
            cpfs.update({
                somente_digitos(aluno.matricula.cpfMae),
                somente_digitos(aluno.matricula.cpfResponsavel),
            })

        if cpf_normalizado in cpfs:
            if aluno.matricula_id:
                aluno = sincronizar_perfil_matricula(aluno.matricula)
            encontrados.append(aluno)
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
            Paragraph("<b>Município</b>", normal),
            Paragraph(escape(cidade), normal),
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

    linhas = [["Componente curricular", "Nota", "Faltas"]]
    for resultado in boletim.resultados.select_related("disciplina").all():
        nota = (
            f"{resultado.nota:.2f}".replace(".", ",")
            if resultado.nota is not None
            else "—"
        )
        faltas = _pdf_texto(resultado.faltas)
        linhas.append([resultado.disciplina.nome, nota, faltas])

    tabela = Table(linhas, colWidths=[118 * mm, 30 * mm, 30 * mm], repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5a2b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
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
