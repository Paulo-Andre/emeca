"""Fluxo autenticado de prévia e confirmação dos CPFs na importação existente."""
import os
import re
import tempfile
import time
from pathlib import Path

from django.contrib import messages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils.crypto import get_random_string
from io import StringIO

from .access_control import usuario_tem_modulo

PASTA = Path("/backups/conferencia-boletins")
CHAVE = "emeca_previa_cpfs"
LIMITE = 10 * 1024 * 1024
VALIDADE = 30 * 60


def _autorizado(request):
    return request.user.is_authenticated and usuario_tem_modulo(
        request.user, "administracao",
        strict=getattr(settings, "EMECA_RBAC_STRICT", True),
    )


def _limpar(request):
    anterior = request.session.pop(CHAVE, None)
    if anterior:
        caminho = PASTA / anterior.get("arquivo", "")
        if caminho.parent == PASTA and caminho.name.startswith("upload-cpfs-"):
            caminho.unlink(missing_ok=True)


def _resumo(texto):
    chaves = (
        "linhas_com_nome", "sem_correspondencia",
        "identidades_duplicadas_planilha", "identidades_duplicadas_banco",
        "cpfs_invalidos", "cpf_aluno_duplicado",
        "cpf_aluno_igual_responsavel", "conflitos_existentes",
        "cadastros_atualizaveis", "campo_cpfMae",
        "campo_cpfResponsavel", "campo_cpfDoAluno",
    )
    saida = {}
    for chave in chaves:
        achado = re.search(r"^" + chave + r": (\d+)$", texto, flags=re.M)
        saida[chave] = int(achado.group(1)) if achado else 0
    plano = re.search(r"^plano_id: ([a-f0-9]{64})$", texto, flags=re.M)
    if not plano:
        raise ValueError("A prévia não retornou um plano válido.")
    return saida, plano.group(1)


def importar_cpfs(request):
    if not _autorizado(request):
        return HttpResponseForbidden("Acesso negado")
    if request.method != "POST":
        return redirect("importar_alunos")

    acao = request.POST.get("acao")
    if acao == "cancelar":
        _limpar(request)
        messages.info(request, "Prévia cancelada. Nenhum CPF alterado.")
        return redirect("importar_alunos")

    if acao == "previsualizar":
        _limpar(request)
        arquivo = request.FILES.get("arquivo")
        if not arquivo or Path(arquivo.name).suffix.lower() not in {".xls", ".xlsx"}:
            messages.error(request, "Escolha uma planilha .xls ou .xlsx.")
            return redirect("importar_alunos")
        if arquivo.size < 1 or arquivo.size > LIMITE:
            messages.error(request, "O Excel deve ter até 10 MB.")
            return redirect("importar_alunos")
        PASTA.mkdir(mode=0o700, parents=True, exist_ok=True)
        nome = "upload-cpfs-" + get_random_string(28) + Path(arquivo.name).suffix.lower()
        caminho = PASTA / nome
        try:
            fd = os.open(str(caminho), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as destino:
                for bloco in arquivo.chunks():
                    destino.write(bloco)
            saida = StringIO()
            call_command("reconciliar_cpfs_declaracoes", str(caminho), stdout=saida)
            resumo, plano = _resumo(saida.getvalue())
        except (CommandError, OSError, ValueError):
            caminho.unlink(missing_ok=True)
            messages.error(request, "Planilha incompatível ou não validada. Nenhum CPF alterado.")
            return redirect("importar_alunos")
        request.session[CHAVE] = {
            "arquivo": nome, "plano": plano, "criacao": time.time(),
        }
        return render(request, "declaracoes/importardados.html", {
            "previa_cpfs": resumo,
        })

    if acao != "confirmar":
        return redirect("importar_alunos")
    registro = request.session.get(CHAVE)
    if not registro or time.time() - registro.get("criacao", 0) > VALIDADE:
        _limpar(request)
        messages.error(request, "Prévia expirada. Envie a planilha novamente.")
        return redirect("importar_alunos")
    caminho = PASTA / registro.get("arquivo", "")
    if caminho.parent != PASTA or not caminho.name.startswith("upload-cpfs-"):
        _limpar(request)
        return HttpResponseForbidden("Arquivo inválido")
    try:
        saida = StringIO()
        # O comando confere o hash do plano e cria um backup consistente
        # ANTES de abrir a transação de atualização.
        call_command(
            "reconciliar_cpfs_declaracoes", str(caminho),
            aplicar=True, plano_id=registro["plano"], stdout=saida,
        )
        quantidade = re.search(r"CONCLUÍDO: (\d+)", saida.getvalue())
        if quantidade:
            messages.success(request, f"CPFs atualizados em {quantidade.group(1)} declarações. Backup criado.")
        else:
            messages.info(request, "Nenhuma alteração necessária.")
    except (CommandError, OSError):
        messages.error(request, "Não foi possível aplicar. Confira se a prévia ainda é válida e se o backup está disponível.")
    finally:
        _limpar(request)
    return redirect("importar_alunos")
