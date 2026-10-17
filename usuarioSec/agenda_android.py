"""Importação segura de contatos VCF do Android para a agenda do EMECA.

Não altera a base do WA-AKG, mensagens, sessões ou estado de leitura.
Nomes são vinculados apenas a telefones brasileiros completos com DDD.
"""
import quopri
import re
import unicodedata
from collections import defaultdict
from urllib.parse import unquote

from django.db import transaction

from .models import ContatoAgendaWhatsApp

MAX_VCF_BYTES = 8 * 1024 * 1024
MAX_CONTACTS = 20000
MAX_PREVIEW = 8


class AgendaImportError(ValueError):
    pass


def normalizar_telefone_br(numero):
    """Produz JID telefônico sem adivinhar DDD ou converter IDs LID."""
    if not isinstance(numero, str):
        return ""
    valor = unquote(numero).strip()
    if valor.lower().startswith("tel:"):
        valor = valor[4:]
    if "@lid" in valor.lower() or "@" in valor or re.search(r"[A-Za-z]", valor):
        return ""
    # Números de outros países exigem tratamento explícito; não inventar +55.
    if valor.startswith("+") and not valor.startswith("+55"):
        return ""
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if len(digitos) not in (12, 13) or not digitos.startswith("55"):
        return ""
    ddd = int(digitos[2:4])
    if not (11 <= ddd <= 99) or set(digitos[4:]) == {"0"}:
        return ""
    return digitos + "@s.whatsapp.net"


def _texto_vcard(valor, cabecalho):
    """Decodifica texto de um campo VCF, incluindo escapes e QP."""
    valor = valor.strip()
    header = cabecalho.upper()
    if "QUOTED-PRINTABLE" in header:
        charset = re.search(r"CHARSET=([A-Z0-9_-]+)", header)
        encoding = charset.group(1) if charset else "utf-8"
        try:
            valor = quopri.decodestring(valor.encode("latin-1", errors="replace")).decode(
                encoding, errors="replace"
            )
        except LookupError:
            valor = quopri.decodestring(valor.encode("latin-1", errors="replace")).decode(
                "utf-8", errors="replace"
            )
    valor = re.sub(r"\\[nN]", " ", valor)
    valor = valor.replace(r"\,", ",").replace(r"\;", ";")
    valor = unicodedata.normalize("NFC", valor)
    valor = "".join(c for c in valor if c.isprintable())
    return " ".join(valor.split()).strip()[:160]


def _linhas_desdobradas(texto):
    previous = ""
    for raw in texto.splitlines():
        if raw.startswith((" ", "\t")):
            previous += raw[1:]
            continue
        if previous and previous.endswith("=") and "QUOTED-PRINTABLE" in previous.split(":", 1)[0].upper():
            previous = previous[:-1] + raw
            continue
        if previous:
            yield previous
        previous = raw
    if previous:
        yield previous


def ler_agenda_vcf(conteudo):
    """Retorna telefones únicos e resumo; conflitos de nomes não são importados."""
    if len(conteudo) > MAX_VCF_BYTES:
        raise AgendaImportError("O arquivo deve ter no máximo 8 MB.")
    texto = conteudo.decode("utf-8-sig", errors="replace")
    if "BEGIN:VCARD" not in texto.upper():
        raise AgendaImportError("O arquivo não contém contatos VCF válidos.")

    entradas = defaultdict(set)
    sem_telefone = 0
    descartados = 0
    total_cartoes = 0
    dados = None

    def concluir(cartao):
        nonlocal total_cartoes, sem_telefone, descartados
        if cartao is None:
            return
        total_cartoes += 1
        if total_cartoes > MAX_CONTACTS:
            raise AgendaImportError("O arquivo excede o limite de 20 mil contatos.")
        nome = cartao["nome"] or cartao["n"]
        if not nome:
            descartados += 1
            return
        telefones = {normalizar_telefone_br(n) for n in cartao["telefones"]}
        telefones.discard("")
        if not telefones:
            sem_telefone += 1
        for jid in telefones:
            entradas[jid].add(nome)

    for line in _linhas_desdobradas(texto):
        upper = line.strip().upper()
        if upper == "BEGIN:VCARD":
            dados = {"nome": "", "n": "", "telefones": []}
            continue
        if upper == "END:VCARD":
            concluir(dados)
            dados = None
            continue
        if dados is None or ":" not in line:
            continue
        header, value = line.split(":", 1)
        tipo = header.split(";", 1)[0].split(".")[-1].upper()
        if tipo == "FN" and not dados["nome"]:
            dados["nome"] = _texto_vcard(value, header)
        elif tipo == "N" and not dados["n"]:
            parts = value.split(";")
            family = _texto_vcard(parts[0], header) if parts else ""
            given = _texto_vcard(parts[1], header) if len(parts) > 1 else ""
            dados["n"] = " ".join(x for x in (given, family) if x)
        elif tipo == "TEL":
            dados["telefones"].append(_texto_vcard(value, header))
    if dados is not None:
        raise AgendaImportError("O arquivo VCF termina antes de END:VCARD.")

    conflitantes = {jid for jid, nomes in entradas.items() if len(nomes) != 1}
    unicos = {
        jid: next(iter(nomes))
        for jid, nomes in entradas.items()
        if jid not in conflitantes
    }
    return unicos, {
        "cartoes": total_cartoes,
        "telefones_unicos": len(entradas),
        "conflitos_no_arquivo": len(conflitantes),
        "sem_telefone_brasileiro_com_ddd": sem_telefone,
        "sem_nome": descartados,
    }


def processar_agenda_vcf(conteudo, *, sessao, aplicar=False):
    """Idempotente: nunca sobrescreve nomes anteriores nem cria duplicatas."""
    if not sessao:
        raise AgendaImportError("Sessão do WhatsApp não configurada.")
    telefones, resumo = ler_agenda_vcf(conteudo)
    chaves = list(telefones)
    existentes = {
        obj.telefone_jid: obj.nome
        for obj in ContatoAgendaWhatsApp.objects.filter(
            sessao=sessao, telefone_jid__in=chaves
        ).only("telefone_jid", "nome")
    }
    novos = {jid: nome for jid, nome in telefones.items() if jid not in existentes}
    alterados = sum(
        1 for jid, nome in telefones.items()
        if jid in existentes and existentes[jid].casefold() != nome.casefold()
    )
    resultado = {
        **resumo,
        "novos": len(novos),
        "ja_importados": len(existentes),
        "nomes_diferentes_preservados": alterados,
        "amostra": [
            {"nome": nome, "numero": jid.split("@")[0]}
            for jid, nome in list(novos.items())[:MAX_PREVIEW]
        ],
        "importados": 0,
    }
    if not aplicar:
        return resultado

    with transaction.atomic():
        ContatoAgendaWhatsApp.objects.bulk_create(
            [
                ContatoAgendaWhatsApp(
                    sessao=sessao, telefone_jid=jid, nome=nome
                )
                for jid, nome in novos.items()
            ],
            ignore_conflicts=True,
            batch_size=500,
        )
        # Verificar inserções reais, considerando outros operadores simultâneos.
        inseridos = ContatoAgendaWhatsApp.objects.filter(
            sessao=sessao, telefone_jid__in=list(novos)
        ).count()
    resultado["importados"] = inseridos
    return resultado
