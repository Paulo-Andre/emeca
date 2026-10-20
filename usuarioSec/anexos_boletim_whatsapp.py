"""Anexos opcionais de boletins; arquivos privados, sem URLs públicas.

Não requer migração de esquema: um envelope versionado só é usado em novos
lotes com anexo, preservando os registros antigos de mensagem simples.
"""
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from django.conf import settings

PREFIXO = "__EMECA_ANEXO_BOLETIM_V1__:"
REFERENCIA = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|pdf)$")
MAX_BYTES = 25 * 1024 * 1024


def _pasta():
    """Irmã de MEDIA_ROOT: nunca acessível sob a URL pública /media/."""
    caminho = Path(settings.MEDIA_ROOT).resolve().parent / "whatsapp-anexos-privados"
    caminho.mkdir(mode=0o700, parents=True, exist_ok=True)
    return caminho


def _caminho(referencia):
    if not isinstance(referencia, str) or not REFERENCIA.fullmatch(referencia):
        raise ValueError("Referência de anexo inválida.")
    return _pasta() / referencia


def mensagem_com_anexo(mensagem, referencia):
    """Acopla uma referência privada à legenda; preserva placeholders existentes."""
    _caminho(referencia)
    return PREFIXO + json.dumps(
        {"mensagem": mensagem, "anexo": referencia},
        ensure_ascii=False, separators=(",", ":"),
    )


def extrair_mensagem_anexo(valor):
    if not (valor or "").startswith(PREFIXO):
        return (valor or ""), ""
    try:
        data = json.loads(valor[len(PREFIXO):])
        ref = data.get("anexo")
        mensagem = data.get("mensagem")
        if not isinstance(mensagem, str):
            raise ValueError("Legenda inválida.")
        _caminho(ref)
        return mensagem, ref
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Anexo do boletim está inválido.") from exc


def salvar_anexo(arquivo, nome_seguro):
    if nome_seguro not in {"imagem.jpg", "imagem.png", "imagem.webp", "documento.pdf"}:
        raise ValueError("Formato de anexo inválido.")
    if arquivo.size < 1 or arquivo.size > MAX_BYTES:
        raise ValueError("Anexo acima do limite de 25 MB.")
    referencia = uuid4().hex + "." + nome_seguro.rsplit(".", 1)[-1]
    caminho = _caminho(referencia)
    descritor = os.open(str(caminho), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descritor, "wb") as destino:
            for pedaco in arquivo.chunks():
                destino.write(pedaco)
    except Exception:
        caminho.unlink(missing_ok=True)
        raise
    return referencia


def ler_anexo(referencia):
    caminho = _caminho(referencia)
    if caminho.stat().st_size < 1 or caminho.stat().st_size > MAX_BYTES:
        raise ValueError("Anexo ausente ou maior que 25 MB.")
    conteudo = caminho.read_bytes()
    ext = caminho.suffix.lower()
    tipos = {
        ".jpg": ("imagem.jpg", "image/jpeg", "image"),
        ".png": ("imagem.png", "image/png", "image"),
        ".webp": ("imagem.webp", "image/webp", "image"),
        ".pdf": ("documento.pdf", "application/pdf", "document"),
    }
    nome, mime, tipo = tipos[ext]
    cabecalho = conteudo[:16]
    valido = {
        ".jpg": cabecalho.startswith(b"\xff\xd8\xff"),
        ".png": cabecalho.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": cabecalho[:4] == b"RIFF" and cabecalho[8:12] == b"WEBP",
        ".pdf": cabecalho.startswith(b"%PDF-"),
    }[ext]
    if not valido:
        raise ValueError("Arquivo do lote inválido.")
    return conteudo, nome, mime, tipo


def apagar_anexo(referencia):
    if referencia:
        _caminho(referencia).unlink(missing_ok=True)
