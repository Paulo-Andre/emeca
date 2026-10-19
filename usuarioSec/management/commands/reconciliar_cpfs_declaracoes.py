"""Reconcilia CPFs de uma planilha oficial SEM criar Declarações ou trocar vínculos.

Por padrão apenas simula. Usa nome integral normalizado + nascimento
coincidentes e únicos NOS DOIS LADOS. CPFs inválidos ou conflitantes bloqueiam
o registro. AC=responsável, AD=aluno, AB=mãe; AE não é importada.
"""
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from usuarioSec.importacao_declaracoes import (
    converter_data,
    encontrar_linha_cabecalho,
    mapear_colunas,
    normalizar_cabecalho,
    texto_celula,
)
from usuarioSec.models import declaracao
from site_publico.boletim_importacao import normalizar_nome


# Índices baseados em zero; regras confirmadas pela Secretaria.
COLUNAS_CPF = {"cpfMae": 27, "cpfResponsavel": 28, "cpfDoAluno": 29}
CABECALHOS_ESPERADOS = {
    27: "CPF DA MAE",
    28: "CPF",
    29: "CPF",
    30: "CPF DO PAI",
}


def _cpf_valido(digitos):
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        total = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (total * 10) % 11
        if dv == 10:
            dv = 0
        if dv != int(digitos[tamanho]):
            return False
    return True


def _cpf_da_celula(valor):
    texto = texto_celula(valor)
    if not texto:
        return "", False
    digitos = re.sub(r"\D", "", texto)
    # Excel pode perder zero à esquerda ao armazenar CPF numericamente.
    if len(digitos) == 10:
        digitos = digitos.zfill(11)
    if not _cpf_valido(digitos):
        return "", True
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}", False


def _identidade(nome, nascimento):
    return (normalizar_nome(nome), nascimento)


def _ler_planilha(caminho, contagem):
    caminho = Path(caminho)
    if not caminho.is_file() or caminho.suffix.lower() not in {".xls", ".xlsx"}:
        raise CommandError("Planilha inexistente ou formato não permitido (.xls/.xlsx).")
    if caminho.stat().st_size > 10 * 1024 * 1024:
        raise CommandError("Arquivo acima do limite de 10 MB.")
    try:
        df = pd.read_excel(
            caminho, header=None, dtype=object,
            engine="xlrd" if caminho.suffix.lower() == ".xls" else "openpyxl",
        )
    except Exception as exc:
        raise CommandError("Não foi possível ler o Excel.") from exc
    if df.empty or len(df.index) > 10000 or len(df.columns) < 31:
        raise CommandError("Estrutura ou tamanho da planilha incompatível.")
    try:
        header_idx = encontrar_linha_cabecalho(df)
        headers = [normalizar_cabecalho(v) for v in df.iloc[header_idx]]
        mapa = mapear_colunas(headers)
    except Exception as exc:
        raise CommandError("Não foi possível localizar cabeçalho confiável.") from exc
    for indice, esperado in CABECALHOS_ESPERADOS.items():
        if headers[indice] != esperado:
            raise CommandError(
                f"Cabeçalho inesperado na coluna {indice+1}; operação cancelada."
            )
    if mapa["nascimento"] is None:
        raise CommandError("Coluna de nascimento obrigatória não encontrada.")
    fonte = defaultdict(list)
    for _, row in df.iloc[header_idx + 1:].iterrows():
        nome = texto_celula(row.iloc[mapa["nome"]])
        if not nome:
            contagem["linhas_sem_nome_ignoradas"] += 1
            continue
        contagem["linhas_com_nome"] += 1
        nascimento = converter_data(row.iloc[mapa["nascimento"]])
        if not nascimento:
            contagem["linhas_sem_nascimento"] += 1
            continue
        identidade = _identidade(nome, nascimento)
        if not identidade[0]:
            contagem["linhas_sem_identidade"] += 1
            continue
        valores, invalido = {}, False
        for campo, coluna in COLUNAS_CPF.items():
            valores[campo], erro = _cpf_da_celula(row.iloc[coluna])
            invalido = invalido or erro
        fonte[identidade].append((valores, invalido))
    return fonte, hashlib.sha256(caminho.read_bytes()).hexdigest()


def _preparar_plano(fonte, hash_arquivo, contagem):
    banco = defaultdict(list)
    cpf_aluno_banco = defaultdict(set)
    for registro in declaracao.objects.all().only(
        "id", "nomeDoAluno", "dataNascimentoAluno",
        "cpfMae", "cpfResponsavel", "cpfDoAluno",
    ).iterator():
        banco[_identidade(registro.nomeDoAluno, registro.dataNascimentoAluno)].append(registro)
        doc = re.sub(r"\D", "", registro.cpfDoAluno or "")
        if len(doc) == 11:
            cpf_aluno_banco[doc].add(registro.pk)

    # Um CPF de aluno não pode pertencer a duas identidades distintas na fonte.
    cpf_aluno_fonte = defaultdict(set)
    for chave, entradas in fonte.items():
        for valores, erro in entradas:
            if not erro and valores["cpfDoAluno"]:
                cpf_aluno_fonte[re.sub(r"\D", "", valores["cpfDoAluno"])].add(chave)

    alteracoes = []
    for chave, entradas in fonte.items():
        if len(entradas) != 1:
            contagem["identidades_duplicadas_planilha"] += 1
            continue
        registros = banco.get(chave, [])
        if not registros:
            contagem["sem_correspondencia"] += 1
            continue
        if len(registros) != 1:
            contagem["identidades_duplicadas_banco"] += 1
            continue
        valores, cpf_invalido = entradas[0]
        if cpf_invalido:
            contagem["cpfs_invalidos"] += 1
            continue
        if not any(valores.values()):
            contagem["sem_cpf_na_planilha"] += 1
            continue

        aluno_doc = re.sub(r"\D", "", valores["cpfDoAluno"])
        if aluno_doc and any(
            re.sub(r"\\D", "", valores[campo]) == aluno_doc
            for campo in ("cpfMae", "cpfResponsavel") if valores[campo]
        ):
            contagem["cpf_aluno_igual_responsavel"] += 1
            continue
        if aluno_doc and (
            len(cpf_aluno_fonte[aluno_doc]) != 1
            or cpf_aluno_banco[aluno_doc] - {registros[0].pk}
        ):
            contagem["cpf_aluno_duplicado"] += 1
            continue

        registro = registros[0]
        originais = {campo: getattr(registro, campo) or "" for campo in COLUNAS_CPF}
        conflito = any(
            valor and originais[campo]
            and re.sub(r"\D", "", originais[campo])
                != re.sub(r"\D", "", valor)
            for campo, valor in valores.items()
        )
        if conflito:
            contagem["conflitos_existentes"] += 1
            continue
        novos = {
            campo: valor for campo, valor in valores.items()
            if valor and not originais[campo]
        }
        if not novos:
            contagem["ja_preenchidos_ou_sem_mudancas"] += 1
            continue
        contagem["cadastros_atualizaveis"] += 1
        for campo in novos:
            contagem["campo_" + campo] += 1
        alteracoes.append((registro.pk, originais, novos))

    serializar = {
        "arquivo": hash_arquivo,
        "alteracoes": sorted(alteracoes, key=lambda x: x[0]),
    }
    plano = hashlib.sha256(json.dumps(
        serializar, sort_keys=True, ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return alteracoes, plano


def _fazer_backup():
    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
        raise CommandError("Backup automático disponível apenas para SQLite.")
    origem = Path(settings.DATABASES["default"]["NAME"])
    diretorio = Path("/backups/conferencia-boletins")
    if not diretorio.is_dir() or not origem.is_file():
        raise CommandError("Banco SQLite ou diretório de backups não encontrado.")
    nome = "antes-reconciliacao-cpfs-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    ) + "-" + os.urandom(4).hex() + ".sqlite3"
    destino = diretorio / nome
    fd = os.open(str(destino), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(f"file:{origem}?mode=ro", uri=True) as atual:
            with sqlite3.connect(destino) as copia:
                atual.backup(copia)
                if copia.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise CommandError("Cópia SQLite falhou no integrity_check.")
    except Exception:
        raise CommandError("Backup falhou. Nenhuma Declaração foi atualizada.")
    return destino


class Command(BaseCommand):
    help = (
        "Simula reconciliação de CPFs AB(mãe), AC(responsável), AD(aluno), "
        "por nome e nascimento únicos. --aplicar exige o hash da simulação."
    )

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--aplicar", action="store_true")
        parser.add_argument("--plano-id", default="")

    def handle(self, *args, **options):
        if options["aplicar"] and not re.fullmatch(r"[0-9a-f]{64}", options["plano_id"]):
            raise CommandError("Para aplicar, informe --plano-id obtido na prévia.")
        contagem = Counter()
        fonte, hash_arquivo = _ler_planilha(options["arquivo"], contagem)
        alteracoes, plano = _preparar_plano(fonte, hash_arquivo, contagem)
        self.stdout.write("===== PRÉVIA DA RECONCILIAÇÃO (SEM DADOS PESSOAIS) =====")
        for chave in (
            "linhas_com_nome", "linhas_sem_nome_ignoradas",
            "linhas_sem_nascimento", "identidades_duplicadas_planilha",
            "sem_correspondencia", "identidades_duplicadas_banco",
            "cpfs_invalidos", "cpf_aluno_duplicado",
            "cpf_aluno_igual_responsavel",
            "conflitos_existentes", "sem_cpf_na_planilha",
            "ja_preenchidos_ou_sem_mudancas", "cadastros_atualizaveis",
            "campo_cpfMae", "campo_cpfResponsavel", "campo_cpfDoAluno",
        ):
            self.stdout.write(f"{chave}: {contagem[chave]}")
        self.stdout.write("plano_id: " + plano)
        if not options["aplicar"]:
            self.stdout.write("SIMULAÇÃO CONCLUÍDA. Nenhum cadastro foi alterado.")
            return
        if options["plano_id"] != plano:
            raise CommandError("Plano não corresponde à prévia. Nenhum dado alterado.")
        if not alteracoes:
            self.stdout.write("Não há campos novos para gravar.")
            return

        backup = _fazer_backup()
        self.stdout.write("Backup íntegro criado em: " + str(backup))
        with transaction.atomic():
            for pk, originais, novos in alteracoes:
                atual = declaracao.objects.select_for_update().get(pk=pk)
                if any(
                    (getattr(atual, campo) or "") != valor
                    for campo, valor in originais.items()
                ):
                    raise CommandError(
                        "Cadastro alterado após a prévia. Transação cancelada."
                    )
                for campo, valor in novos.items():
                    setattr(atual, campo, valor)
                atual.save(update_fields=list(novos))
        self.stdout.write(
            self.style.SUCCESS(
                f"CONCLUÍDO: {len(alteracoes)} Declarações atualizadas. "
                "Nenhuma Declaração, nota ou vínculo foi criado ou apagado."
            )
        )
