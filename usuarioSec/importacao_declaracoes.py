import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd


class ImportacaoDeclaracaoErro(ValueError):
    pass


CAMPOS_ALIASES = {
    "nome": {"NOME", "NOME DO ALUNO", "ALUNO"},
    "mae": {"MAE", "NOME DA MAE"},
    "pai": {"PAI", "NOME DO PAI"},
    "nascimento": {"NASCIMENTO", "DATA NASCIMENTO", "DATA DE NASCIMENTO"},
    "naturalidade": {"NATURALIDADE"},
    "nacionalidade": {"NACIONALIDADE", "NACIONALIDAD"},
    "uf": {"UF", "ESTADO NASCIMENTO", "UF NASCIMENTO"},
    "sexo": {"SEXO"},
    "turma": {"TURMA", "SERIE", "SERIE TURMA"},
}


def normalizar_cabecalho(valor):
    texto = texto_celula(valor)
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.upper()
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def texto_celula(valor):
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


def _cabecalho_corresponde(cabecalho, aliases):
    if not cabecalho:
        return False
    if cabecalho in aliases:
        return True
    return any(
        len(alias) >= 4
        and (
            cabecalho.startswith(alias + " ")
            or alias.startswith(cabecalho + " ")
        )
        for alias in aliases
    )


def encontrar_linha_cabecalho(df):
    limite = min(len(df.index), 30)
    for indice in range(limite):
        headers = [normalizar_cabecalho(v) for v in df.iloc[indice].tolist()]
        tem_nome = any(_cabecalho_corresponde(h, CAMPOS_ALIASES["nome"]) for h in headers)
        tem_nascimento = any(
            _cabecalho_corresponde(h, CAMPOS_ALIASES["nascimento"]) for h in headers
        )
        marcadores = sum(
            any(_cabecalho_corresponde(h, CAMPOS_ALIASES[chave]) for h in headers)
            for chave in ("naturalidade", "nacionalidade", "sexo", "turma")
        )
        if tem_nome and tem_nascimento and marcadores >= 2:
            return indice
    raise ImportacaoDeclaracaoErro(
        "Não foi possível localizar a linha de cabeçalho. "
        "A planilha deve conter pelo menos NOME, NASCIMENTO e os campos da declaração."
    )


def _indice_campo(headers, chave):
    aliases = CAMPOS_ALIASES[chave]
    for indice, header in enumerate(headers):
        if _cabecalho_corresponde(header, aliases):
            return indice
    return None


def mapear_colunas(headers):
    mapa = {chave: _indice_campo(headers, chave) for chave in CAMPOS_ALIASES}

    # O arquivo legado usado pela escola pode ter Mãe/Pai sem rótulo legível,
    # posicionados entre NOME e NASCIMENTO.
    if (
        mapa["nome"] is not None
        and mapa["nascimento"] is not None
        and mapa["nascimento"] - mapa["nome"] >= 3
    ):
        if mapa["mae"] is None:
            mapa["mae"] = mapa["nome"] + 1
        if mapa["pai"] is None:
            mapa["pai"] = mapa["nome"] + 2

    telefones = {"PAI": [], "MAE": [], "RESPONSAVEL": []}
    for indice, header in enumerate(headers):
        if not header:
            continue
        eh_telefone = (
            "TELEFONE" in header
            or header.startswith("TEL ")
            or header == "TEL"
            or "CELULAR" in header
        )
        if not eh_telefone:
            continue

        if "PAI" in header:
            telefones["PAI"].append(indice)
        elif "MAE" in header:
            telefones["MAE"].append(indice)
        elif "RESP" in header:
            telefones["RESPONSAVEL"].append(indice)
        elif header in {"TELEFONE", "TEL"}:
            telefones["RESPONSAVEL"].append(indice)

    mapa["telefones"] = telefones

    if mapa["nome"] is None:
        raise ImportacaoDeclaracaoErro("A coluna NOME não foi encontrada.")

    return mapa


def normalizar_numero_telefone(valor):
    texto = texto_celula(valor)
    if not texto:
        return ""

    digitos = re.sub(r"\D", "", texto)
    if not digitos:
        return ""

    # Remove código do Brasil para comparar números nacionais de forma uniforme.
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]

    return digitos


def _mesmo_telefone(a, b):
    if not a or not b:
        return False
    if a == b:
        return True

    # Planilhas antigas misturam o mesmo número com e sem DDD.
    if len(a) in (8, 9) and len(b) >= 10:
        return b.endswith(a)
    if len(b) in (8, 9) and len(a) >= 10:
        return a.endswith(b)

    return False


def formatar_telefone(digitos):
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    if len(digitos) == 9:
        return f"{digitos[:5]}-{digitos[5:]}"
    if len(digitos) == 8:
        return f"{digitos[:4]}-{digitos[4:]}"
    return digitos


def deduplicar_telefones(valores):
    unicos = []
    duplicados = 0

    for valor in valores:
        numero = normalizar_numero_telefone(valor)
        if not numero:
            continue

        indice_duplicado = next(
            (i for i, existente in enumerate(unicos) if _mesmo_telefone(existente, numero)),
            None,
        )
        if indice_duplicado is not None:
            duplicados += 1
            # Prefere a versão mais completa, normalmente a que contém DDD.
            if len(numero) > len(unicos[indice_duplicado]):
                unicos[indice_duplicado] = numero
            continue

        unicos.append(numero)

    return [formatar_telefone(n) for n in unicos], duplicados


def _valor_linha(row, indice):
    if indice is None or indice >= len(row):
        return ""
    return texto_celula(row.iloc[indice])


def converter_data(valor):
    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if 1 <= float(valor) <= 80000:
            convertido = pd.to_datetime(
                float(valor),
                unit="D",
                origin="1899-12-30",
                errors="coerce",
            )
            if not pd.isna(convertido):
                return convertido.date()

    texto = texto_celula(valor)
    if not texto:
        return None

    convertido = pd.to_datetime(texto, dayfirst=True, errors="coerce")
    if pd.isna(convertido):
        return None
    return convertido.date()


def ler_planilha(arquivo):
    nome = getattr(arquivo, "name", "")
    extensao = Path(nome).suffix.lower()

    if extensao not in {".xls", ".xlsx", ".csv"}:
        raise ImportacaoDeclaracaoErro(
            "Formato não permitido. Envie um arquivo .xls, .xlsx ou .csv."
        )

    tamanho = getattr(arquivo, "size", None)
    if tamanho and tamanho > 10 * 1024 * 1024:
        raise ImportacaoDeclaracaoErro("O arquivo deve ter no máximo 10 MB.")

    try:
        arquivo.seek(0)
        if extensao == ".csv":
            try:
                df = pd.read_csv(
                    arquivo,
                    header=None,
                    dtype=object,
                    sep=None,
                    engine="python",
                    encoding="utf-8-sig",
                )
            except UnicodeDecodeError:
                arquivo.seek(0)
                df = pd.read_csv(
                    arquivo,
                    header=None,
                    dtype=object,
                    sep=None,
                    engine="python",
                    encoding="latin-1",
                )
        else:
            engine = "xlrd" if extensao == ".xls" else "openpyxl"
            df = pd.read_excel(
                arquivo,
                header=None,
                dtype=object,
                engine=engine,
            )
    except Exception as exc:
        raise ImportacaoDeclaracaoErro(
            "Não foi possível ler a planilha. Verifique se o arquivo não está corrompido."
        ) from exc

    if df.empty:
        raise ImportacaoDeclaracaoErro("A planilha está vazia.")

    if len(df.index) > 10000:
        raise ImportacaoDeclaracaoErro(
            "A planilha possui mais de 10.000 linhas e não pode ser importada de uma só vez."
        )

    header_idx = encontrar_linha_cabecalho(df)
    headers = [normalizar_cabecalho(v) for v in df.iloc[header_idx].tolist()]
    mapa = mapear_colunas(headers)

    registros = []
    ignoradas = 0
    telefones_duplicados = 0

    for _, row in df.iloc[header_idx + 1 :].iterrows():
        nome = _valor_linha(row, mapa["nome"])
        if not nome:
            if any(texto_celula(v) for v in row.tolist()):
                ignoradas += 1
            continue

        telefones_por_tipo = {}
        for tipo, indices in mapa["telefones"].items():
            valores = [_valor_linha(row, indice) for indice in indices]
            unicos, duplicados = deduplicar_telefones(valores)
            telefones_por_tipo[tipo] = unicos
            telefones_duplicados += duplicados

        nascimento_raw = (
            row.iloc[mapa["nascimento"]]
            if mapa["nascimento"] is not None and mapa["nascimento"] < len(row)
            else None
        )

        registros.append(
            {
                "nomeDoAluno": nome,
                "nomeMae": _valor_linha(row, mapa["mae"]),
                "nomePai": _valor_linha(row, mapa["pai"]),
                "dataNascimentoAluno": converter_data(nascimento_raw),
                "natularidadeAluno": _valor_linha(row, mapa["naturalidade"]),
                "nacionaliadeAluno": _valor_linha(row, mapa["nacionalidade"]),
                "ufAluno": _valor_linha(row, mapa["uf"]),
                "sexoDoAluno": _valor_linha(row, mapa["sexo"]),
                "turmaDoAluno": _valor_linha(row, mapa["turma"]),
                "telefones": telefones_por_tipo,
            }
        )

    if not registros:
        raise ImportacaoDeclaracaoErro(
            "Nenhum aluno válido foi encontrado depois da linha de cabeçalho."
        )

    return {
        "registros": registros,
        "ignoradas": ignoradas,
        "telefones_duplicados": telefones_duplicados,
        "cabecalhos": headers,
    }
