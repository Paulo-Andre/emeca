import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd


class ImportacaoBoletimErro(ValueError):
    pass


def texto(valor):
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def normalizar(valor):
    valor = texto(valor)
    valor = unicodedata.normalize("NFKD", valor)
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    valor = valor.upper()
    valor = re.sub(r"[^A-Z0-9]+", " ", valor)
    return re.sub(r"\s+", " ", valor).strip()


def normalizar_nome(valor):
    valor = re.sub(r"\([^)]*TRANSF[^)]*\)", "", texto(valor), flags=re.I)
    return normalizar(valor)


def _numero_inteiro(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    try:
        numero = int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    return numero if numero >= 0 else None


def _decimal(valor):
    bruto = texto(valor)
    if not bruto:
        return None
    bruto = bruto.replace(".", "").replace(",", ".") if "," in bruto else bruto
    try:
        return Decimal(bruto).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _linha_cabecalho(df):
    for indice in range(min(len(df.index), 30)):
        valores = [normalizar(v) for v in df.iloc[indice].tolist()]
        if "NOME" in valores and any(v in {"NUM", "NUMERO", "N"} for v in valores[:3]):
            return indice
    raise ImportacaoBoletimErro(
        "Não foi possível localizar a linha com Num./Nome/Nota/Falta na planilha."
    )


def _rotulo_disciplina(df, cabecalho_idx, coluna):
    ignorar = {
        "REGENTE",
        "NUM",
        "NUMERO",
        "NOME",
        "NOTAS",
        "FALTAS",
        "NOTAS E FALTAS",
    }
    for deslocamento in range(1, 6):
        linha = cabecalho_idx - deslocamento
        if linha < 0:
            break
        candidato = texto(df.iat[linha, coluna]) if coluna < len(df.columns) else ""
        if candidato and normalizar(candidato) not in ignorar:
            return re.sub(r"\s+", " ", candidato.replace("\n", " ")).strip()

    # Alguns XLS antigos mantêm o texto apenas na primeira célula da mesclagem.
    if coluna > 0:
        for deslocamento in range(1, 4):
            linha = cabecalho_idx - deslocamento
            if linha < 0:
                break
            candidato = texto(df.iat[linha, coluna - 1])
            if candidato and normalizar(candidato) not in ignorar:
                return re.sub(r"\s+", " ", candidato.replace("\n", " ")).strip()
    return ""


def _nome_disciplina_valido(valor):
    norm = normalizar(valor)
    if not norm:
        return False
    if norm in {
        "REGENTE",
        "NUM",
        "NUMERO",
        "NOME",
        "N",
        "F",
        "NOTA",
        "NOTAS",
        "FALTA",
        "FALTAS",
        "NOTAS E FALTAS",
    }:
        return False
    if norm.startswith("NOTAS E FALTAS"):
        return False
    if norm.startswith("E M EGIDIO"):
        return False
    if "TRIMESTRE" in norm or "BIMESTRE" in norm or "TURMA" in norm:
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]", texto(valor)))


def _disciplinas_por_rotulos(df, cabecalho_idx, nome_col):
    """Fallback para XLS do Crystal Reports sem N./F. como células de texto.

    Nesse formato cada disciplina ocupa um par de colunas (nota/falta) e o
    rótulo normalmente está acima da primeira coluna do par.
    """
    candidatos = []

    # Procura rótulos nas linhas imediatamente acima de Num./Nome.
    inicio = max(0, cabecalho_idx - 8)
    for col in range(nome_col + 1, len(df.columns)):
        # A coluna reservada ao professor regente não é disciplina.
        if any(
            normalizar(df.iat[linha, col]) == "REGENTE"
            for linha in range(inicio, cabecalho_idx)
        ):
            continue

        encontrado = ""
        linha_encontrada = None
        for linha in range(cabecalho_idx - 1, inicio - 1, -1):
            valor = texto(df.iat[linha, col])
            if _nome_disciplina_valido(valor):
                encontrado = re.sub(r"\s+", " ", valor.replace("\n", " ")).strip()
                linha_encontrada = linha
                break
        if encontrado:
            candidatos.append((col, linha_encontrada, encontrado))

    if not candidatos:
        return []

    # Em células mescladas o mesmo rótulo pode aparecer em mais de uma coluna.
    # Mantém apenas a primeira ocorrência próxima e considera o próximo campo
    # como faltas.
    itens = []
    usados = set()
    ordem = 0
    for col, _, nome in candidatos:
        chave = normalizar(nome)
        if chave in usados:
            continue

        # Se a coluna anterior já iniciou uma disciplina, esta coluna é o par
        # de faltas e não uma nova disciplina.
        if itens and col <= itens[-1]["nota_col"] + 1:
            continue

        faltas_col = col + 1 if col + 1 < len(df.columns) else None
        itens.append(
            {
                "nome": nome,
                "nota_col": col,
                "faltas_col": faltas_col,
                "ordem": ordem,
            }
        )
        usados.add(chave)
        ordem += 1

    return itens


def _disciplinas(df, cabecalho_idx, nome_col):
    headers = [normalizar(v) for v in df.iloc[cabecalho_idx].tolist()]
    itens = []
    ordem = 0
    col = nome_col + 1

    while col < len(headers):
        marcador = headers[col]
        if marcador in {"N", "NOTA", "NOTAS"}:
            faltas_col = None
            if col + 1 < len(headers) and headers[col + 1] in {"F", "FALTA", "FALTAS"}:
                faltas_col = col + 1
            nome = _rotulo_disciplina(df, cabecalho_idx, col)
            if nome and _nome_disciplina_valido(nome):
                itens.append(
                    {
                        "nome": nome,
                        "nota_col": col,
                        "faltas_col": faltas_col,
                        "ordem": ordem,
                    }
                )
                ordem += 1
            col += 2 if faltas_col is not None else 1
            continue
        col += 1

    if itens:
        return itens

    itens = _disciplinas_por_rotulos(df, cabecalho_idx, nome_col)
    if itens:
        return itens

    raise ImportacaoBoletimErro(
        "Nenhuma disciplina foi identificada no arquivo. O importador procurou "
        "tanto cabeçalhos Nota/Falta quanto o formato legado do Crystal Reports."
    )


COLUNA_FALTAS_TOTAIS_EXCEL = 5  # coluna F (A=0)


def _coluna_faltas_totais(df, cabecalho_idx, nome_col, componentes):
    """Usa exclusivamente a coluna F da planilha como faltas totais.

    A planilha oficial da escola registra na coluna F o total de faltas da
    criança no período. Faltas presentes nos pares de cada disciplina não
    devem ser somadas nem usadas como total do boletim.
    """
    if len(df.columns) <= COLUNA_FALTAS_TOTAIS_EXCEL:
        return None
    return COLUNA_FALTAS_TOTAIS_EXCEL

def _metadados(df):
    blocos = []
    for linha in range(min(len(df.index), 15)):
        valores = [texto(v) for v in df.iloc[linha].tolist() if texto(v)]
        if valores:
            blocos.append(" ".join(valores))

    cabecalho = " | ".join(blocos)
    norm = normalizar(cabecalho)

    tipo = "TRIMESTRE" if "TRIMESTRE" in norm else ("BIMESTRE" if "BIMESTRE" in norm else "")
    numero = None
    if tipo:
        # Aceita títulos como "2º Trimestre", que após normalização
        # podem aparecer como "2O TRIMESTRE".
        match = re.search(rf"(\d+)\s*(?:O\s*)?{tipo}", norm)
        if match:
            numero = int(match.group(1))

    ano_match = re.search(r"\b(20\d{2})\b", norm)
    ano = int(ano_match.group(1)) if ano_match else None

    turma = ""
    for bloco in blocos:
        match = re.search(
            r"Turma\s+(.+?)(?:\s+-\s+20\d{2}|\s+20\d{2}|$)",
            bloco,
            flags=re.I,
        )
        if match:
            turma = re.sub(r"\s+", " ", match.group(1)).strip(" -")
            break

    regente = ""
    regente_col = None
    for linha in range(min(len(df.index), 20)):
        valores = [texto(v) for v in df.iloc[linha].tolist()]
        for col, valor in enumerate(valores):
            if normalizar(valor) != "REGENTE":
                continue
            regente_col = col

            # No modelo usado pela escola, o marcador "REGENTE" fica acima
            # do nome do professor. Por isso procuramos primeiro logo abaixo
            # da mesma coluna e só depois à direita, para não confundir o
            # próximo componente curricular com o nome do regente.
            for deslocamento in range(1, 4):
                linha_abaixo = linha + deslocamento
                if linha_abaixo >= len(df.index):
                    break
                candidato = texto(df.iat[linha_abaixo, col])
                candidato_norm = normalizar(candidato)
                if (
                    candidato
                    and candidato_norm not in {"N", "F", "NOTA", "NOTAS", "FALTA", "FALTAS"}
                    and re.search(r"[A-Za-zÀ-ÿ]", candidato)
                ):
                    regente = re.sub(r"^PROF(?:ESSOR(?:A)?)?\.?\s*", "", candidato, flags=re.I).strip()
                    break

            if not regente:
                for candidato in valores[col + 1 : col + 4]:
                    candidato_norm = normalizar(candidato)
                    if (
                        candidato
                        and candidato_norm not in {"N", "F", "NOTA", "NOTAS", "FALTA", "FALTAS"}
                        and re.search(r"[A-Za-zÀ-ÿ]", candidato)
                    ):
                        regente = re.sub(r"^PROF(?:ESSOR(?:A)?)?\.?\s*", "", candidato, flags=re.I).strip()
                        break
            break
        if regente:
            break

    # Alguns relatórios do Crystal Reports colocam o nome do regente
    # no rodapé da mesma coluna, depois da lista de alunos.
    if not regente and regente_col is not None:
        try:
            cabecalho_idx = _linha_cabecalho(df)
            headers = [normalizar(v) for v in df.iloc[cabecalho_idx].tolist()]
            nome_col = headers.index("NOME")
            numero_col = next(
                (i for i, valor in enumerate(headers[: nome_col + 1]) if valor in {"NUM", "NUMERO", "N"}),
                None,
            )
        except (ImportacaoBoletimErro, ValueError):
            cabecalho_idx = 0
            nome_col = None
            numero_col = None

        if regente_col != nome_col:
            for linha in range(cabecalho_idx + 1, len(df.index)):
                if numero_col is not None and numero_col < len(df.columns):
                    if _numero_inteiro(df.iat[linha, numero_col]) is not None:
                        continue
                candidato = texto(df.iat[linha, regente_col])
                norm_candidato = normalizar(candidato)
                if (
                    candidato
                    and len(candidato.split()) >= 2
                    and _nome_disciplina_valido(candidato)
                    and norm_candidato not in {"REGENTE"}
                ):
                    regente = re.sub(
                        r"^PROF(?:ESSOR(?:A)?)?\.?\s*",
                        "",
                        candidato,
                        flags=re.I,
                    ).strip()
                    break

    return {
        "tipo": tipo,
        "numero": numero,
        "ano": ano,
        "turma": turma,
        "regente": regente,
        "titulo_original": next((b for b in blocos if "NOTAS" in normalizar(b) and "FALTAS" in normalizar(b)), ""),
    }


def ler_planilha_boletim(arquivo):
    nome = getattr(arquivo, "name", "")
    extensao = Path(nome).suffix.lower()
    if extensao not in {".xls", ".xlsx"}:
        raise ImportacaoBoletimErro("Envie uma planilha .xls ou .xlsx.")

    tamanho = getattr(arquivo, "size", None)
    if tamanho and tamanho > 10 * 1024 * 1024:
        raise ImportacaoBoletimErro("A planilha deve ter no máximo 10 MB.")

    try:
        arquivo.seek(0)
        engine = "xlrd" if extensao == ".xls" else "openpyxl"
        df = pd.read_excel(arquivo, header=None, dtype=object, engine=engine)
    except Exception as exc:
        raise ImportacaoBoletimErro(
            "Não foi possível ler a planilha de notas. Verifique se o arquivo está íntegro."
        ) from exc

    if df.empty:
        raise ImportacaoBoletimErro("A planilha está vazia.")

    cabecalho_idx = _linha_cabecalho(df)
    headers = [normalizar(v) for v in df.iloc[cabecalho_idx].tolist()]
    nome_col = headers.index("NOME")
    numero_col = next(
        (i for i, valor in enumerate(headers[: nome_col + 1]) if valor in {"NUM", "NUMERO", "N"}),
        None,
    )
    componentes = _disciplinas(df, cabecalho_idx, nome_col)
    faltas_totais_col = _coluna_faltas_totais(
        df,
        cabecalho_idx,
        nome_col,
        componentes,
    )

    alunos = []
    vazias_seguidas = 0
    for _, row in df.iloc[cabecalho_idx + 1 :].iterrows():
        nome_aluno = texto(row.iloc[nome_col]) if nome_col < len(row) else ""
        numero_chamada = (
            _numero_inteiro(row.iloc[numero_col])
            if numero_col is not None and numero_col < len(row)
            else None
        )

        if not nome_aluno:
            vazias_seguidas += 1
            if vazias_seguidas >= 5 and alunos:
                break
            continue
        vazias_seguidas = 0

        # Ignora totais e rodapés numéricos que podem existir depois da turma.
        if not re.search(r"[A-Za-zÀ-ÿ]", nome_aluno):
            continue

        # Linhas de rodapé/regente não têm número de chamada no modelo enviado.
        if numero_col is not None and numero_chamada is None:
            continue

        resultados = []
        for componente in componentes:
            nota = (
                _decimal(row.iloc[componente["nota_col"]])
                if componente["nota_col"] < len(row)
                else None
            )
            faltas = (
                _numero_inteiro(row.iloc[componente["faltas_col"]])
                if componente["faltas_col"] is not None and componente["faltas_col"] < len(row)
                else None
            )
            resultados.append(
                {
                    "disciplina": componente["nome"],
                    "ordem": componente["ordem"],
                    "nota": nota,
                    "faltas": faltas,
                }
            )

        faltas_totais = (
            _numero_inteiro(row.iloc[faltas_totais_col])
            if faltas_totais_col is not None and faltas_totais_col < len(row)
            else None
        )

        alunos.append(
            {
                "numero_chamada": numero_chamada,
                "nome": nome_aluno,
                "nome_normalizado": normalizar_nome(nome_aluno),
                "faltas_totais": faltas_totais,
                "resultados": resultados,
            }
        )

    if not alunos:
        raise ImportacaoBoletimErro("Nenhum aluno com notas foi identificado na planilha.")

    return {
        "metadados": _metadados(df),
        "disciplinas": componentes,
        "alunos": alunos,
    }
