import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from django.db import transaction
from django.db.models import Max

from .academico import matriz_para_ano
from .models import Aluno, ConfiguracaoAno, Nota, RegistroAcademico


logger = logging.getLogger(__name__)

MAX_PAGINAS = 250
MAX_ITENS = 15000

COMPONENTES = {
    "lingua_portuguesa": Nota.LINGUA_PORTUGUESA,
    "arte": Nota.ARTE,
    "educacao_fisica": Nota.EDUCACAO_FISICA,
    "lingua_inglesa": Nota.LINGUA_INGLESA,
    "matematica": Nota.MATEMATICA,
    "ciencias": Nota.CIENCIAS,
    "geografia": Nota.GEOGRAFIA,
    "historia": Nota.HISTORIA,
    "educacao_religiosa": Nota.EDUCACAO_RELIGIOSA,
}

ROTULOS_COMPONENTES = dict(Nota.COMPONENTES)

ALIASES_COMPONENTES = {
    Nota.LINGUA_PORTUGUESA: {
        "lingua portuguesa",
        "portugues",
        "lingua portuguesa literatura",
        "portugues literatura",
        "lp",
    },
    Nota.ARTE: {"arte", "artes"},
    Nota.EDUCACAO_FISICA: {
        "educacao fisica",
        "ed fisica",
        "educ fisica",
        "ed fis",
    },
    Nota.LINGUA_INGLESA: {
        "lingua inglesa",
        "ingles",
        "lingua estrangeira ingles",
    },
    Nota.MATEMATICA: {"matematica", "mat"},
    Nota.CIENCIAS: {
        "ciencias",
        "ciencias da natureza",
        "ciencia",
    },
    Nota.GEOGRAFIA: {"geografia", "geo"},
    Nota.HISTORIA: {"historia"},
    Nota.EDUCACAO_RELIGIOSA: {
        "educacao religiosa",
        "ensino religioso",
        "ed religiosa",
        "religiao",
    },
}

ALIASES_CAMPOS = {
    "nome": {
        "nome",
        "aluno",
        "nome aluno",
        "nome do aluno",
        "estudante",
    },
    "turma": {"turma", "classe"},
    "ano": {
        "ano letivo",
        "ano escolar",
        "ano calendario",
        "ano calendario letivo",
    },
    "serie": {
        "serie",
        "serie ano",
        "serie escolar",
        "etapa",
    },
}


# Estrutura da "ATA DE RESULTADO FINAL DE APROVEITAMENTO" do SAEWEB.
# Cada componente ocupa 3 colunas: N (nota), F (faltas) e RF.
# O histórico escolar usa a coluna N dos nove componentes abaixo.
SAEWEB_NOTA_COLUNAS = {
    5: Nota.LINGUA_PORTUGUESA,
    11: Nota.ARTE,
    14: Nota.EDUCACAO_FISICA,
    17: Nota.LINGUA_INGLESA,
    20: Nota.MATEMATICA,
    23: Nota.CIENCIAS,
    26: Nota.GEOGRAFIA,
    29: Nota.HISTORIA,
    32: Nota.EDUCACAO_RELIGIOSA,
}


class ErroImportacaoNotasPdf(ValueError):
    pass


def _sem_acentos(valor):
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(caractere)
    )


def _normalizar(valor):
    texto = _sem_acentos(valor).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _normalizar_nome(valor):
    return re.sub(r"\s+", " ", _sem_acentos(valor).upper()).strip()


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return re.sub(r"\s+", " ", str(valor)).strip()


def _ano(valor):
    texto = _texto(valor)
    encontrados = re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", texto)
    if encontrados:
        return int(encontrados[0])
    try:
        numero = int(float(texto.replace(",", ".")))
    except (ValueError, TypeError):
        return None
    return numero if 1900 <= numero <= 2100 else None


def _serie(valor):
    texto = _normalizar(valor)
    if not texto:
        return None

    padroes = (
        r"\b([1-9])\s*(?:o|a)?\s*ano\b",
        r"\b([1-9])\s*(?:o|a)?\s*serie\b",
        r"\bserie\s*([1-9])\b",
        r"\bano\s*([1-9])\b",
        r"^([1-9])$",
    )
    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            return int(match.group(1))
    return None


def _contexto_ata_saeweb(texto, anterior=None):
    contexto = dict(anterior or {})
    texto = texto or ""

    ano_match = re.search(
        r"ATA\s+DE\s+RESULTADO\s+FINAL\s+DE\s+APROVEITAMENTO\s*-\s*ANO\s*:\s*(\d{4})",
        texto,
        flags=re.IGNORECASE,
    )
    if ano_match:
        contexto["ano"] = int(ano_match.group(1))

    turma_match = re.search(
        r"Turma\s*:\s*(.*?)\s+Ensino\s*:",
        texto,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if turma_match:
        contexto["turma"] = _texto(turma_match.group(1))

    serie_match = re.search(
        r"(?:Série|Serie)\s*/\s*Etapa\s*:\s*(.*?)\s+Turno\s*:",
        texto,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if serie_match:
        contexto["serie"] = _serie(serie_match.group(1))

    return contexto


def _nota_saeweb(valor):
    valor = _texto(valor)
    if not valor or valor in {"-", "—", "–"}:
        return ""
    return valor


def _parece_tabela_saeweb(tabela):
    if not tabela:
        return False

    for linha in tabela[:6]:
        if not linha or len(linha) < 36:
            continue
        primeira = _normalizar(linha[0] if len(linha) > 0 else "")
        segunda = _normalizar(linha[1] if len(linha) > 1 else "")
        ultima = _normalizar(linha[35] if len(linha) > 35 else "")
        if (
            primeira in {"n", "no", "n o", "numero", ""}
            and segunda == "estudante"
            and "situacao final" in ultima
        ):
            return True
    return False


def _itens_tabela_saeweb(tabela, contexto, numero_pagina):
    if not _parece_tabela_saeweb(tabela):
        return []
    if not contexto.get("ano") or not contexto.get("serie"):
        return []

    itens = []
    for linha in tabela:
        if not linha or len(linha) < 36:
            continue

        numero = _texto(linha[0])
        nome = _texto(linha[1])
        if not numero.isdigit() or not nome:
            continue

        notas = {}
        for indice, componente in SAEWEB_NOTA_COLUNAS.items():
            valor = _nota_saeweb(linha[indice])
            if valor:
                notas[componente] = valor

        # Alunos transferidos/remanejados podem aparecer sem notas. A relação
        # com a turma continua sendo importada para preservar o percurso do
        # aluno, mas nasce inativa no Histórico Escolar oficial.
        itens.append(
            {
                "nome": nome,
                "turma": _texto(contexto.get("turma")),
                "ano": contexto["ano"],
                "serie": contexto["serie"],
                "resultado": _texto(linha[35]),
                "notas": notas,
                "_pagina": numero_pagina,
            }
        )

    return itens


def _mapear_cabecalho(celulas):
    mapa = {}
    reconhecidos = set()

    for indice, celula in enumerate(celulas):
        chave = _normalizar(celula)
        if not chave:
            continue

        for campo, aliases in ALIASES_CAMPOS.items():
            if chave in aliases and campo not in reconhecidos:
                mapa[indice] = ("campo", campo)
                reconhecidos.add(campo)
                break
        else:
            for componente, aliases in ALIASES_COMPONENTES.items():
                if chave in aliases and componente not in reconhecidos:
                    mapa[indice] = ("nota", componente)
                    reconhecidos.add(componente)
                    break

    score = 0
    campos = {valor for tipo, valor in mapa.values() if tipo == "campo"}
    notas = {valor for tipo, valor in mapa.values() if tipo == "nota"}

    if "nome" in campos:
        score += 6
    if "turma" in campos:
        score += 2
    if "ano" in campos:
        score += 2
    if "serie" in campos:
        score += 2
    score += min(len(notas), 6)

    return score, mapa


def _inferir_ano_serie(dados, linha_original):
    if dados.get("ano") and dados.get("serie"):
        return

    candidatos = [_texto(v) for v in linha_original if _texto(v)]
    for candidato in candidatos:
        if not dados.get("ano"):
            valor_ano = _ano(candidato)
            if valor_ano:
                dados["ano"] = valor_ano
        if not dados.get("serie"):
            valor_serie = _serie(candidato)
            if valor_serie:
                dados["serie"] = valor_serie


def _linha_tabela_para_item(linha, mapa, pagina):
    dados = {
        "nome": "",
        "turma": "",
        "ano": None,
        "serie": None,
        "resultado": "",
        "notas": {},
        "_pagina": pagina,
    }

    for indice, definicao in mapa.items():
        if indice >= len(linha):
            continue

        tipo, chave = definicao
        valor = _texto(linha[indice])
        if tipo == "nota":
            if valor:
                dados["notas"][chave] = valor
            continue

        if chave == "ano":
            dados["ano"] = _ano(valor)
        elif chave == "serie":
            dados["serie"] = _serie(valor)
        else:
            dados[chave] = valor

    _inferir_ano_serie(dados, linha)
    return dados


def _extrair_tabelas_pagina(pagina, numero_pagina, contexto=None):
    itens = []
    for tabela in pagina.extract_tables() or []:
        if not tabela:
            continue

        itens_saeweb = _itens_tabela_saeweb(
            tabela,
            contexto or {},
            numero_pagina,
        )
        if itens_saeweb:
            itens.extend(itens_saeweb)
            continue

        cabecalho = None
        mapa = None
        indice_cabecalho = None

        for indice, linha in enumerate(tabela[:8]):
            score, candidato = _mapear_cabecalho(linha or [])
            if mapa is None or score > cabecalho:
                cabecalho = score
                mapa = candidato
                indice_cabecalho = indice

        if not mapa or cabecalho < 7:
            continue

        for linha in tabela[indice_cabecalho + 1:]:
            if not linha:
                continue
            item = _linha_tabela_para_item(linha, mapa, numero_pagina)
            if not item["nome"]:
                continue
            itens.append(item)
            if len(itens) >= MAX_ITENS:
                return itens

    return itens


def _valor_rotulado(texto, rotulos):
    rotulo = "|".join(re.escape(item) for item in rotulos)
    match = re.search(
        rf"(?:^|\n)\s*(?:{rotulo})\s*[:\-]\s*([^\n]+)",
        texto,
        flags=re.IGNORECASE,
    )
    return _texto(match.group(1)) if match else ""


def _parsear_blocos_texto(texto, pagina):
    if not texto:
        return []

    normalizado = texto.replace("\r", "\n")
    marcadores = list(
        re.finditer(
            r"(?im)^\s*(?:nome(?:\s+do\s+aluno)?|aluno|estudante)\s*[:\-]\s*",
            normalizado,
        )
    )
    if not marcadores:
        return []

    itens = []
    for indice, marcador in enumerate(marcadores):
        fim = (
            marcadores[indice + 1].start()
            if indice + 1 < len(marcadores)
            else len(normalizado)
        )
        bloco = normalizado[marcador.start():fim]

        primeira_linha = bloco.splitlines()[0]
        nome = re.sub(
            r"(?i)^\s*(?:nome(?:\s+do\s+aluno)?|aluno|estudante)\s*[:\-]\s*",
            "",
            primeira_linha,
        ).strip()

        turma = _valor_rotulado(bloco, ("turma", "classe"))
        ano_texto = _valor_rotulado(
            bloco,
            ("ano letivo", "ano escolar", "ano"),
        )
        serie_texto = _valor_rotulado(
            bloco,
            ("série", "serie", "série/ano", "serie/ano", "etapa"),
        )

        item = {
            "nome": nome,
            "turma": turma,
            "ano": _ano(ano_texto),
            "serie": _serie(serie_texto),
            "resultado": "",
            "notas": {},
            "_pagina": pagina,
        }

        if not item["serie"]:
            item["serie"] = _serie(serie_texto or bloco)

        for componente, aliases in ALIASES_COMPONENTES.items():
            aliases_regex = "|".join(
                re.escape(alias) for alias in sorted(aliases, key=len, reverse=True)
            )
            match = re.search(
                rf"(?im)^\s*(?:{aliases_regex})\s*[:\-]\s*"
                rf"([A-Za-z0-9,\.\-]+)\s*$",
                _sem_acentos(bloco),
            )
            if match:
                item["notas"][componente] = _texto(match.group(1))

        if item["nome"] and item["notas"]:
            itens.append(item)

    return itens


def _mesclar_itens(itens):
    agrupados = {}

    for item in itens:
        chave = (
            _normalizar_nome(item.get("nome")),
            item.get("ano"),
            item.get("serie"),
            _normalizar(item.get("turma")),
        )

        if chave not in agrupados:
            agrupados[chave] = {
                "nome": item.get("nome", ""),
                "turma": item.get("turma", ""),
                "ano": item.get("ano"),
                "serie": item.get("serie"),
                "resultado": item.get("resultado", ""),
                "notas": {},
                "_paginas": [],
            }

        destino = agrupados[chave]
        if not destino.get("resultado") and item.get("resultado"):
            destino["resultado"] = item["resultado"]
        destino["notas"].update(
            {
                componente: valor
                for componente, valor in item.get("notas", {}).items()
                if _texto(valor)
            }
        )
        if item.get("_pagina") and item["_pagina"] not in destino["_paginas"]:
            destino["_paginas"].append(item["_pagina"])

    return list(agrupados.values())


def extrair_notas_pdf(caminho):
    import pdfplumber

    caminho = Path(caminho)
    itens = []
    paginas_com_texto = 0

    try:
        with pdfplumber.open(caminho) as pdf:
            if len(pdf.pages) > MAX_PAGINAS:
                raise ErroImportacaoNotasPdf(
                    f"O PDF possui {len(pdf.pages)} páginas. "
                    f"O limite é {MAX_PAGINAS} páginas."
                )

            contexto_saeweb = {}
            for numero, pagina in enumerate(pdf.pages, start=1):
                texto_pagina = pagina.extract_text() or ""
                if texto_pagina.strip():
                    paginas_com_texto += 1

                # No relatório SAEWEB, páginas de continuação nem sempre repetem
                # ano/turma/série. Mantemos o contexto da página anterior até
                # surgir o cabeçalho da próxima turma.
                contexto_saeweb = _contexto_ata_saeweb(
                    texto_pagina,
                    contexto_saeweb,
                )

                tabelas = _extrair_tabelas_pagina(
                    pagina,
                    numero,
                    contexto_saeweb,
                )
                itens.extend(tabelas)

                # O parser textual complementa PDFs de outros formatos nos
                # quais a tabela não é detectada pelo mecanismo geométrico.
                if not tabelas:
                    itens.extend(_parsear_blocos_texto(texto_pagina, numero))

                if len(itens) >= MAX_ITENS:
                    break
    except ErroImportacaoNotasPdf:
        raise
    except Exception as exc:
        raise ErroImportacaoNotasPdf(
            "Não foi possível abrir ou interpretar o PDF."
        ) from exc

    if paginas_com_texto == 0:
        raise ErroImportacaoNotasPdf(
            "O PDF parece ser apenas uma imagem digitalizada. "
            "Envie um PDF com texto selecionável."
        )

    itens = _mesclar_itens(itens)

    validos = []
    incompletos = []
    for item in itens:
        faltando = []
        if not item.get("nome"):
            faltando.append("nome")
        if not item.get("ano"):
            faltando.append("ano")
        if not item.get("serie"):
            faltando.append("série")
        if faltando:
            item["erro"] = "Faltando: " + ", ".join(faltando)
            incompletos.append(item)
        else:
            validos.append(item)

    if not validos:
        raise ErroImportacaoNotasPdf(
            "Não encontrei registros completos com nome do aluno, ano e "
            "série. Verifique o formato do PDF."
        )

    return {
        "itens": validos,
        "incompletos": incompletos,
        "paginas_com_texto": paginas_com_texto,
    }


def _indice_alunos():
    indice = defaultdict(list)
    for aluno in Aluno.objects.all().order_by("id"):
        indice[_normalizar_nome(aluno.nome)].append(aluno)
    return indice


def _resolver_aluno(nome, indice):
    encontrados = indice.get(_normalizar_nome(nome), [])
    if len(encontrados) == 1:
        return encontrados[0], None
    if len(encontrados) > 1:
        return None, "Existem vários alunos no banco com este mesmo nome."
    return None, None


def _resolver_registro(aluno, item):
    registros = list(
        aluno.registros_academicos.filter(
            ano=item["ano"],
            serie=item["serie"],
        ).order_by("id")
    )

    if not registros:
        return None, None

    turma = _normalizar(item.get("turma"))
    if turma:
        mesma_turma = [
            registro
            for registro in registros
            if _normalizar(registro.turma) == turma
        ]
        if len(mesma_turma) == 1:
            return mesma_turma[0], None
        if len(mesma_turma) > 1:
            return None, "Há mais de um registro acadêmico para a mesma turma."

        # Turma diferente representa outra relação acadêmica. Não reutilize
        # automaticamente o registro anterior, pois isso misturaria notas de
        # transferências entre turmas.
        return None, None

    if len(registros) == 1:
        return registros[0], None

    return None, (
        "Há mais de um registro acadêmico para este aluno, ano e série. "
        "Informe uma turma que identifique o registro correto."
    )


def analisar_notas_pdf(resultado):
    indice = _indice_alunos()
    itens = []
    alunos_novos = 0
    alunos_existentes = 0
    conflitos = 0
    registros_novos = 0
    registros_existentes = 0
    notas_novas = 0
    notas_preservadas = 0

    for item in resultado["itens"]:
        aluno, erro = _resolver_aluno(item["nome"], indice)
        registro = None
        componentes_existentes = set()

        if erro:
            status = "conflito"
            conflitos += 1
        elif aluno:
            alunos_existentes += 1
            registro, erro_registro = _resolver_registro(aluno, item)
            if erro_registro:
                status = "conflito"
                erro = erro_registro
                conflitos += 1
            elif registro:
                status = "completar"
                registros_existentes += 1
                componentes_existentes = set(
                    registro.notas.values_list("componente", flat=True)
                )
            else:
                status = "novo_registro"
                registros_novos += 1
        else:
            status = "novo_aluno"
            alunos_novos += 1
            registros_novos += 1

        notas_legiveis = []
        novas_item = 0
        preservadas_item = 0

        for componente, valor in item["notas"].items():
            ja_existe = componente in componentes_existentes
            if ja_existe:
                preservadas_item += 1
                notas_preservadas += 1
            else:
                novas_item += 1
                notas_novas += 1

            notas_legiveis.append(
                {
                    "componente": ROTULOS_COMPONENTES.get(
                        componente,
                        componente,
                    ),
                    "valor": valor,
                    "ja_existe": ja_existe,
                }
            )

        itens.append(
            {
                **item,
                "status": status,
                "erro": erro or "",
                "aluno_codigo": aluno.codigo if aluno else "",
                "registro_id": registro.id if registro else "",
                "quantidade_notas": len(item["notas"]),
                "notas_novas": novas_item,
                "notas_preservadas": preservadas_item,
                "notas_legiveis": notas_legiveis,
            }
        )

    return {
        "total": len(itens),
        "alunos_novos": alunos_novos,
        "alunos_existentes": alunos_existentes,
        "registros_novos": registros_novos,
        "registros_existentes": registros_existentes,
        "notas_novas": notas_novas,
        "notas_preservadas": notas_preservadas,
        "conflitos": conflitos,
        "incompletos": len(resultado.get("incompletos", [])),
        "itens": itens,
    }


def _novo_codigo():
    return (Aluno.objects.aggregate(maximo=Max("codigo"))["maximo"] or 0) + 1


def aplicar_notas_pdf(resultado):
    indice = _indice_alunos()
    proximo_codigo = _novo_codigo()

    alunos_criados = 0
    alunos_localizados = 0
    registros_criados = 0
    registros_existentes = 0
    notas_adicionadas = 0
    notas_preservadas = 0
    conflitos = []
    processados = 0

    for item in resultado["itens"]:
        try:
            # Cada aluno/ano é confirmado em uma transação curta. Assim um
            # registro problemático não desfaz os demais e reduz o tempo em
            # que o SQLite permanece bloqueado para escrita.
            with transaction.atomic():
                aluno, erro = _resolver_aluno(item["nome"], indice)
                if erro:
                    conflitos.append(
                        {
                            "nome": item["nome"],
                            "ano": item["ano"],
                            "serie": item["serie"],
                            "erro": erro,
                        }
                    )
                    continue

                criou_aluno = False
                if aluno is None:
                    while Aluno.objects.filter(codigo=proximo_codigo).exists():
                        proximo_codigo += 1
                    aluno = Aluno.objects.create(
                        codigo=proximo_codigo,
                        nome=_texto(item["nome"])[:255],
                        curso="ENSINO FUNDAMENTAL",
                        ativo=True,
                    )
                    proximo_codigo += 1
                    criou_aluno = True
                else:
                    alunos_localizados += 1

                registro, erro_registro = _resolver_registro(aluno, item)
                if erro_registro:
                    # Se o aluno acabou de ser criado nesta mesma transação,
                    # o rollback evita deixar cadastro incompleto.
                    raise ErroImportacaoNotasPdf(erro_registro)

                if registro is None:
                    config = ConfiguracaoAno.objects.filter(
                        ano=item["ano"]
                    ).first()
                    matriz = (
                        config.matriz_curricular
                        if config and config.matriz_curricular_id
                        else matriz_para_ano(item["ano"])
                    )
                    ativos_mesma_serie = list(
                        aluno.registros_academicos
                        .select_for_update()
                        .filter(
                            serie=item["serie"],
                            ativo_no_historico=True,
                        )
                        .prefetch_related("notas")
                    )

                    tem_notas_importadas = any(
                        _texto(valor) not in {"", "-", "*"}
                        for valor in item.get("notas", {}).values()
                    )
                    ativo_novo = bool(
                        tem_notas_importadas and not ativos_mesma_serie
                    )

                    if ativos_mesma_serie and tem_notas_importadas:
                        algum_ativo_com_nota = any(
                            any(
                                _texto(nota.valor) not in {"", "-", "*"}
                                for nota in existente.notas.all()
                            )
                            for existente in ativos_mesma_serie
                        )
                        if not algum_ativo_com_nota:
                            ids_ativos = [
                                existente.id
                                for existente in ativos_mesma_serie
                            ]
                            RegistroAcademico.objects.filter(
                                id__in=ids_ativos
                            ).update(ativo_no_historico=False)
                            ativo_novo = True

                    registro = RegistroAcademico.objects.create(
                        aluno=aluno,
                        nome_original=aluno.nome,
                        ano=item["ano"],
                        serie=item["serie"],
                        turma=_texto(item.get("turma"))[:120],
                        resultado=_texto(item.get("resultado"))[:80],
                        carga_horaria=(config.ch_anual if config else ""),
                        escola=(config.escola if config else ""),
                        municipio=(
                            config.municipio if config else "MONTES CLAROS"
                        ),
                        uf=(config.uf if config else "MG"),
                        matriz_curricular=matriz,
                        ativo_no_historico=ativo_novo,
                    )
                    registros_criados += 1
                else:
                    # Modo aditivo: nunca substitui informação preenchida.
                    # Apenas completa campos vazios do mesmo aluno + ano + série.
                    alterados = []
                    turma = _texto(item.get("turma"))[:120]
                    resultado_item = _texto(item.get("resultado"))[:80]

                    if not registro.turma and turma:
                        registro.turma = turma
                        alterados.append("turma")
                    if not registro.resultado and resultado_item:
                        registro.resultado = resultado_item
                        alterados.append("resultado")
                    if not registro.nome_original:
                        registro.nome_original = aluno.nome
                        alterados.append("nome_original")

                    if alterados:
                        registro.save(update_fields=alterados)
                    registros_existentes += 1

                for componente, valor in item["notas"].items():
                    valor = _texto(valor)
                    if not valor:
                        continue

                    _, criada = Nota.objects.get_or_create(
                        registro=registro,
                        componente=componente,
                        defaults={"valor": valor[:40]},
                    )
                    if criada:
                        notas_adicionadas += 1
                    else:
                        # Regra append-only: mantém a nota já existente.
                        notas_preservadas += 1

                if criou_aluno:
                    indice[_normalizar_nome(aluno.nome)].append(aluno)
                    alunos_criados += 1

                processados += 1

        except ErroImportacaoNotasPdf as exc:
            conflitos.append(
                {
                    "nome": item.get("nome", ""),
                    "ano": item.get("ano", ""),
                    "serie": item.get("serie", ""),
                    "erro": str(exc),
                }
            )
        except Exception as exc:
            logger.exception(
                "Falha ao importar registro da ATA PDF ano=%r serie=%r",
                item.get("ano"),
                item.get("serie"),
            )
            conflitos.append(
                {
                    "nome": item.get("nome", ""),
                    "ano": item.get("ano", ""),
                    "serie": item.get("serie", ""),
                    "erro": (
                        "Erro técnico neste registro. "
                        f"Tipo: {exc.__class__.__name__}."
                    ),
                }
            )

    if processados == 0 and conflitos:
        primeiro = conflitos[0]["erro"]
        raise ErroImportacaoNotasPdf(
            "Nenhum registro pôde ser gravado. "
            f"Primeiro problema encontrado: {primeiro}"
        )

    return {
        "total": len(resultado["itens"]),
        "processados": processados,
        "alunos_criados": alunos_criados,
        "alunos_localizados": alunos_localizados,
        "registros_criados": registros_criados,
        "registros_existentes": registros_existentes,
        "notas_adicionadas": notas_adicionadas,
        "notas_preservadas": notas_preservadas,
        "conflitos": conflitos,
    }
