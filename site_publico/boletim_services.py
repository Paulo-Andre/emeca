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
    """Compatibilidade com perfis antigos sem utilizar CPF da Matrícula.

    Os cadastros históricos de Matrículas e Declarações são independentes.
    Apenas uma Declaração inequivocamente correspondente fornece CPF e data
    de nascimento ao boletim; em conflito, o perfil permanece pendente.
    """
    perfil, _ = AlunoBoletim.objects.get_or_create(
        matricula=aluno_matricula,
        defaults={"nome": aluno_matricula.nomeDoAluno},
    )
    perfil, _ = sincronizar_perfil_por_nome_declaracao(perfil)
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
    """Associa a identidade do boletim ao cadastro explícito em Declarações.

    Matrícula e Histórico continuam representando períodos independentes.
    Um perfil já vinculado a outra Declaração nunca é relocado pelo nome.
    """
    if perfil.declaracao_id and perfil.declaracao_id != aluno_declaracao.pk:
        raise ValueError("O boletim já está vinculado a outro aluno de Declarações.")
    if AlunoBoletim.objects.filter(
        declaracao=aluno_declaracao
    ).exclude(pk=perfil.pk).exists():
        raise ValueError("Essa declaração já possui um perfil de boletim. Selecione-o.")

    dados = {
        "declaracao_id": aluno_declaracao.pk,
        "data_nascimento": aluno_declaracao.dataNascimentoAluno,
        "cpf_mae": aluno_declaracao.cpfMae or "",
        "cpf_responsavel": aluno_declaracao.cpfResponsavel or "",
    }
    alterados = []
    for campo, valor in dados.items():
        if getattr(perfil, campo) != valor:
            setattr(perfil, campo, valor)
            alterados.append("declaracao" if campo == "declaracao_id" else campo)
    if alterados:
        perfil.save(update_fields=alterados + ["atualizado_em"])
    return perfil


def sincronizar_perfil_com_declaracoes(perfil, registros):
    """Só resolve automaticamente uma correspondência única e não conflitante."""
    if perfil.declaracao_id:
        registro = declaracao.objects.filter(pk=perfil.declaracao_id).first()
        if registro:
            return sincronizar_perfil_declaracao(perfil, registro), "vinculado"

    registros = list(registros)
    if len(registros) == 1:
        registro = registros[0]
        # Identidades incompatíveis não são mescladas por semelhança de nome.
        if (perfil.data_nascimento and registro.dataNascimentoAluno
                and perfil.data_nascimento != registro.dataNascimentoAluno):
            return perfil, "conflito"
        try:
            return sincronizar_perfil_declaracao(perfil, registro), "vinculado"
        except ValueError:
            return perfil, "ambiguo"

    # Não publicar nem autenticar boletim que não tenha vínculo explícito.
    return perfil, "ambiguo" if len(registros) > 1 else "nao_encontrado"


def sincronizar_perfil_por_nome_declaracao(perfil, nome=None):
    if perfil.declaracao_id:
        return sincronizar_perfil_com_declaracoes(perfil, [])
    chave = normalizar_nome(nome or perfil.nome)
    registros = _mapa_declaracoes_por_nome().get(chave, [])
    return sincronizar_perfil_com_declaracoes(perfil, registros)

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

    # Importar notas não modifica Matrículas nem Histórico. A declaração
    # existente é a única fonte da identidade e do acesso ao boletim.
    mapa_declaracoes = _mapa_declaracoes_por_nome()
    perfis_por_nome = defaultdict(list)
    perfis_por_declaracao = {}
    for existente in AlunoBoletim.objects.all():
        perfis_por_nome[normalizar_nome(existente.nome)].append(existente)
        if existente.declaracao_id:
            perfis_por_declaracao[existente.declaracao_id] = existente

    importados = 0
    sem_cadastro = []
    ambiguos = []
    sem_acesso = []
    pendentes_vinculo = []
    perfis_no_periodo = set()

    for linha in dados_planilha["alunos"]:
        nome = linha["nome"]
        chave = normalizar_nome(nome)
        declaracoes_mesmo_nome = mapa_declaracoes.get(chave, [])
        declaracao_unica = declaracoes_mesmo_nome[0] if len(declaracoes_mesmo_nome) == 1 else None

        perfil = (
            perfis_por_declaracao.get(declaracao_unica.pk)
            if declaracao_unica else None
        )
        if perfil is None:
            # A coincidência por nome nunca substitui um vínculo explícito.
            candidatos = [
                p for p in perfis_por_nome.get(chave, [])
                if p.declaracao_id is None
            ]
            if len(candidatos) == 1:
                perfil = candidatos[0]
            else:
                perfil = AlunoBoletim.objects.create(nome=nome)
                perfis_por_nome[chave].append(perfil)

        if perfil.pk in perfis_no_periodo:
            if len(declaracoes_mesmo_nome) > 1:
                # Há homônimos: mantém ambos os lançamentos, mas exige que
                # a Secretaria escolha a Declaração certa para cada um.
                perfil = AlunoBoletim.objects.create(nome=nome)
                perfis_por_nome[chave].append(perfil)
            else:
                raise ValueError(
                    f"Aluno '{nome}' aparece mais de uma vez na planilha e "
                    "não há dois cadastros distintos em Declarações. Revise as linhas."
                )
        perfis_no_periodo.add(perfil.pk)

        if perfil.nome != nome:
            perfil.nome = nome
            perfil.save(update_fields=["nome", "atualizado_em"])

        perfil, status_declaracao = sincronizar_perfil_com_declaracoes(
            perfil, declaracoes_mesmo_nome,
        )
        if status_declaracao == "vinculado":
            perfis_por_declaracao[perfil.declaracao_id] = perfil
        else:
            pendentes_vinculo.append(nome)
            if status_declaracao == "nao_encontrado":
                sem_cadastro.append(nome)
            else:
                ambiguos.append(nome)

        faltas_totais = linha.get("faltas_totais")

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

        if not perfil.declaracao_id or not perfil.data_nascimento or not (
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
        "pendentes_vinculo": pendentes_vinculo,
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
    cpf, data_nascimento, somente_publicados=True,
):
    """Consulta pública exige CPF e nascimento da MESMA Declaração vinculada.

    Não combina CPFs de matrícula antiga, dados de boletim e datas de
    declarações diferentes; nem associa homônimos por nome.
    """
    cpf_normalizado = somente_digitos(cpf)
    if len(cpf_normalizado) != 11 or not data_nascimento:
        return []

    candidatos = AlunoBoletim.objects.filter(
        declaracao__isnull=False,
        declaracao__dataNascimentoAluno=data_nascimento,
    ).select_related("declaracao")
    if somente_publicados:
        candidatos = candidatos.filter(boletins__periodo__publicado=True)
    else:
        candidatos = candidatos.filter(boletins__isnull=False)

    encontrados = []
    for perfil in candidatos.distinct():
        registro = perfil.declaracao
        if cpf_normalizado in {
            somente_digitos(registro.cpfMae),
            somente_digitos(registro.cpfResponsavel),
        } - {""}:
            encontrados.append(perfil)
    return encontrados

def conceder_acesso_boletim(request, alunos):
    """Guarda a autorização no servidor sem colocar credenciais na URL/log."""
    ids = sorted({int(aluno.pk) for aluno in alunos})
    request.session.cycle_key()
    request.session["boletim_acesso_ids"] = ids
    request.session["boletim_acesso_expira"] = int(time.time()) + TOKEN_MAX_AGE
    request.session.modified = True
    return ids


def ler_acesso_boletim(request):
    expira = int(request.session.get("boletim_acesso_expira") or 0)
    if not expira or int(time.time()) > expira:
        request.session.pop("boletim_acesso_ids", None)
        request.session.pop("boletim_acesso_expira", None)
        request.session.modified = True
        return []

    ids = request.session.get("boletim_acesso_ids") or []
    try:
        return [int(pk) for pk in ids]
    except (TypeError, ValueError):
        request.session.pop("boletim_acesso_ids", None)
        request.session.pop("boletim_acesso_expira", None)
        request.session.modified = True
        return []


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
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image,
        KeepTogether,
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
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=13 * mm,
        bottomMargin=16 * mm,
        title=f"Boletim - {boletim.aluno.nome}",
        author=(
            config_site.nome_escola
            if config_site and config_site.nome_escola
            else "E. M. Egídio Cordeiro Aquino"
        ),
    )

    verde = colors.HexColor("#14532d")
    verde_medio = colors.HexColor("#15803d")
    verde_claro = colors.HexColor("#f0fdf4")
    azul = colors.HexColor("#1d4ed8")
    azul_claro = colors.HexColor("#eff6ff")
    cinza_texto = colors.HexColor("#475569")
    cinza_borda = colors.HexColor("#dbe4dc")
    cinza_fundo = colors.HexColor("#f8fafc")

    styles = getSampleStyleSheet()
    escola_style = ParagraphStyle(
        "EscolaBoletim",
        parent=styles["Normal"],
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
        fontSize=13.5,
        leading=16,
        textColor=verde,
        spaceAfter=2,
    )
    institucional_style = ParagraphStyle(
        "Institucional",
        parent=styles["Normal"],
        alignment=TA_LEFT,
        fontSize=7.5,
        leading=9.5,
        textColor=cinza_texto,
    )
    titulo_style = ParagraphStyle(
        "TituloBoletim",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=21,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2,
    )
    subtitulo_style = ParagraphStyle(
        "SubtituloBoletim",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        leading=12,
        textColor=cinza_texto,
    )
    label = ParagraphStyle(
        "LabelBoletim",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#64748b"),
    )
    valor = ParagraphStyle(
        "ValorBoletim",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#17251b"),
    )
    normal = ParagraphStyle(
        "NormalBoletim",
        parent=styles["Normal"],
        alignment=TA_LEFT,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1f2937"),
    )
    nota_style = ParagraphStyle(
        "NotaBoletim",
        parent=normal,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=9,
    )
    pequeno = ParagraphStyle(
        "PequenoBoletim",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=7.3,
        leading=9.5,
        textColor=colors.HexColor("#64748b"),
    )
    rodape_style = ParagraphStyle(
        "RodapeBoletim",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#64748b"),
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
    endereco = (
        config_site.endereco
        if config_site and getattr(config_site, "endereco", "")
        else ""
    )
    telefone = (
        config_site.telefone
        if config_site and getattr(config_site, "telefone", "")
        else ""
    )

    logo = None
    if config_site and getattr(config_site, "logo_site", None):
        try:
            config_site.logo_site.open("rb")
            logo_bytes = config_site.logo_site.read()
            config_site.logo_site.close()
            if logo_bytes:
                logo = Image(BytesIO(logo_bytes), width=22 * mm, height=22 * mm)
                logo._restrictSize(22 * mm, 22 * mm)
        except Exception:
            logo = None

    contato_linhas = [cidade]
    if endereco:
        contato_linhas.append(endereco)
    if telefone:
        contato_linhas.append(f"Telefone: {telefone}")
    contato = " · ".join(item for item in contato_linhas if item)

    identidade = Table(
        [
            [
                logo or Paragraph("<b>EMECA</b>", ParagraphStyle(
                    "Selo",
                    parent=styles["Normal"],
                    alignment=TA_CENTER,
                    fontName="Helvetica-Bold",
                    fontSize=10,
                    textColor=colors.white,
                )),
                [
                    Paragraph(escape(escola), escola_style),
                    Paragraph(escape(contato), institucional_style),
                ],
                Paragraph(
                    "<b>DOCUMENTO ESCOLAR</b><br/>Acompanhamento de aprendizagem",
                    ParagraphStyle(
                        "DocLabel",
                        parent=styles["Normal"],
                        alignment=TA_RIGHT,
                        fontName="Helvetica-Bold",
                        fontSize=7.5,
                        leading=10,
                        textColor=verde,
                    ),
                ),
            ]
        ],
        colWidths=[25 * mm, 103 * mm, 49 * mm],
        rowHeights=[27 * mm],
    )
    identidade.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), verde_medio if logo is None else colors.white),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#b7cabc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    titulo_bloco = Table(
        [
            [Paragraph("BOLETIM ESCOLAR", titulo_style)],
            [
                Paragraph(
                    escape(
                        f"{boletim.periodo.nome_periodo} · Ano letivo {boletim.periodo.ano}"
                    ),
                    subtitulo_style,
                )
            ],
        ],
        colWidths=[177 * mm],
    )
    titulo_bloco.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), cinza_fundo),
                ("BOX", (0, 0), (-1, -1), 0.6, cinza_borda),
                ("TOPPADDING", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ]
        )
    )

    dados = [
        [
            [Paragraph("ALUNO(A)", label), Paragraph(escape(boletim.aluno.nome), valor)],
            [Paragraph("TURMA", label), Paragraph(escape(boletim.periodo.turma), valor)],
        ],
        [
            [
                Paragraph("PROFESSOR(A) REGENTE", label),
                Paragraph(escape(boletim.periodo.regente or "Não informado"), valor),
            ],
            [
                Paragraph("Nº DE CHAMADA", label),
                Paragraph(_pdf_texto(boletim.numero_chamada), valor),
            ],
        ],
    ]
    dados_table = Table(dados, colWidths=[119 * mm, 58 * mm])
    dados_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, cinza_borda),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, cinza_borda),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    nascimento = (
        boletim.aluno.data_nascimento.strftime("%d/%m/%Y")
        if boletim.aluno.data_nascimento
        else "Não informado"
    )
    resumo = Table(
        [
            [
                [
                    Paragraph("DATA DE NASCIMENTO", label),
                    Paragraph(escape(nascimento), valor),
                ],
                [
                    Paragraph("FALTAS NO PERÍODO", label),
                    Paragraph(_pdf_texto(boletim.faltas_totais), ParagraphStyle(
                        "FaltasValor",
                        parent=valor,
                        fontSize=12,
                        textColor=azul,
                    )),
                ],
                [
                    Paragraph("PERÍODO", label),
                    Paragraph(escape(boletim.periodo.nome_periodo), valor),
                ],
            ]
        ],
        colWidths=[59 * mm, 59 * mm, 59 * mm],
    )
    resumo.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), verde_claro),
                ("BACKGROUND", (1, 0), (1, 0), azul_claro),
                ("BACKGROUND", (2, 0), (2, 0), verde_claro),
                ("BOX", (0, 0), (-1, -1), 0.6, cinza_borda),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, cinza_borda),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    linhas = [
        [
            Paragraph("<b>COMPONENTE CURRICULAR</b>", normal),
            Paragraph("<b>NOTA</b>", nota_style),
        ]
    ]
    for resultado in boletim.resultados.select_related("disciplina").all():
        nota = (
            f"{resultado.nota:.2f}".replace(".", ",")
            if resultado.nota is not None
            else "—"
        )
        linhas.append(
            [
                Paragraph(escape(resultado.disciplina.nome), normal),
                Paragraph(escape(nota), nota_style),
            ]
        )

    tabela = Table(linhas, colWidths=[145 * mm, 32 * mm], repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), verde),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, cinza_borda),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, cinza_fundo]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    assinaturas = Table(
        [
            ["____________________________________", "____________________________________"],
            ["Professor(a) Regente", "Direção / Secretaria Escolar"],
        ],
        colWidths=[88.5 * mm, 88.5 * mm],
    )
    assinaturas.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 1), (-1, 1), cinza_texto),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
            ]
        )
    )

    story = [
        identidade,
        Spacer(1, 6 * mm),
        titulo_bloco,
        Spacer(1, 6 * mm),
        dados_table,
        Spacer(1, 4 * mm),
        resumo,
        Spacer(1, 7 * mm),
        tabela,
        Spacer(1, 11 * mm),
        KeepTogether(
            [
                assinaturas,
                Spacer(1, 6 * mm),
                Paragraph(
                    "Este boletim apresenta os resultados do período informado. "
                    "Em caso de dúvida sobre notas ou frequência, procure a secretaria escolar.",
                    pequeno,
                ),
            ]
        ),
    ]

    def pagina(canvas, documento):
        canvas.saveState()
        largura, altura = A4
        canvas.setFillColor(verde)
        canvas.rect(0, altura - 4 * mm, largura, 4 * mm, fill=1, stroke=0)
        canvas.setStrokeColor(colors.HexColor("#d7e1da"))
        canvas.line(15 * mm, 12 * mm, largura - 15 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            15 * mm,
            7.7 * mm,
            f"{escola} · {boletim.periodo.nome_periodo} · {boletim.periodo.ano}",
        )
        canvas.drawRightString(
            largura - 15 * mm,
            7.7 * mm,
            f"Página {documento.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    buffer.seek(0)
    return buffer

