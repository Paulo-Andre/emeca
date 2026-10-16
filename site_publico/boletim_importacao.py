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
            if nome:
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

    if not itens:
        raise ImportacaoBoletimErro(
            "Nenhuma disciplina com colunas de Nota/Falta foi identificada."
        )
    return itens


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
        match = re.search(rf"(\d+)\s+{tipo}", norm)
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
    for linha in range(min(len(df.index), 20)):
        valores = [texto(v) for v in df.iloc[linha].tolist()]
        for col, valor in enumerate(valores):
            if normalizar(valor) == "REGENTE":
                for candidato in valores[col + 1 :]:
                    if candidato:
                        regente = candidato
                        break
                if not regente and linha + 1 < len(df.index):
                    abaixo = [texto(v) for v in df.iloc[linha + 1].tolist()]
                    regente = next((v for v in abaixo if v), "")
                break
        if regente:
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

        alunos.append(
            {
                "numero_chamada": numero_chamada,
                "nome": nome_aluno,
                "nome_normalizado": normalizar_nome(nome_aluno),
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
