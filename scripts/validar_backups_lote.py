#!/usr/bin/env python3
"""Verifica snapshots EMECA antes de trocar containers.

Executa um ensaio de restauração isolada do SQLite num diretório temporário.
Para MySQL verifica integridade superficial do dump e conclusão do processo,
NÃO substitui um teste de restauração real numa instância MySQL descartável.
Nunca exibe dados de crianças ou telefones nos logs.
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path


def validar_sqlite(caminho: Path) -> None:
    if not caminho.is_file() or caminho.stat().st_size == 0:
        raise RuntimeError("Backup SQLite não existe ou está vazio.")
    with tempfile.TemporaryDirectory(prefix="emeca-restauracao-qa-") as pasta:
        restaurado = Path(pasta) / "restaurado.sqlite3"
        shutil.copy2(caminho, restaurado)
        with sqlite3.connect(str(restaurado)) as conexao:
            resultado = conexao.execute("PRAGMA integrity_check").fetchone()
            if resultado != ("ok",):
                raise RuntimeError("SQLite restaurado falhou no integrity_check.")
            # Exercita a leitura das estruturas restauradas sem extrair PII.
            conexao.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()


def validar_tar_gzip(caminho: Path) -> None:
    if not caminho.is_file() or caminho.stat().st_size == 0:
        raise RuntimeError("Arquivo compactado de mídias/sessão ausente ou vazio.")
    with tarfile.open(caminho, "r:gz") as arquivo:
        total = 0
        for membro in arquivo:
            # Não extrair arquivos nem seguir symlinks: inspeção somente.
            if membro.name.startswith("/") or ".." in Path(membro.name).parts:
                raise RuntimeError("Arquivo compactado contém caminho inseguro.")
            total += 1
        if total == 0:
            raise RuntimeError("Arquivo compactado não contém entradas.")


def validar_dump_mysql(caminho: Path) -> None:
    if not caminho.is_file() or caminho.stat().st_size == 0:
        raise RuntimeError("Dump MySQL ausente ou vazio.")
    # Em geral mysqldump termina com este marcador. Nunca imprimir conteúdo.
    final = caminho.read_bytes()[-8192:]
    if b"-- Dump completed on " not in final:
        raise RuntimeError("Dump MySQL sem confirmação de conclusão.")


def validar_pacote(pasta: Path) -> None:
    validar_sqlite(pasta / "emeca.sqlite3")
    validar_tar_gzip(pasta / "emeca-media.tar.gz")
    validar_tar_gzip(pasta / "wa-akg-volumes.tar.gz")
    validar_dump_mysql(pasta / "wa-akg.sql")


def main() -> None:
    parser = argparse.ArgumentParser(description="Conferir backups de implantação.")
    parser.add_argument("pasta", type=Path, help="Diretório privado de backups")
    args = parser.parse_args()
    validar_pacote(args.pasta)
    print("Ensaio isolado SQLite e inspeção dos arquivos: APROVADOS.")
    print("Restauração MySQL completa ainda exige ambiente descartável.")


if __name__ == "__main__":
    main()
