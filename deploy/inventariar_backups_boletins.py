#!/usr/bin/env python3
"""Localiza cópias de segurança existentes do EMECA SEM restaurar nada.

Somente lista metadados e, para SQLite legível, conta boletins do período 3.
Não lê PDFs, dados de alunos ou contatos e não altera backups/banco ativo.
"""
import datetime
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

ROOTS = (Path("/srv/backups/emeca"), Path("/srv/backups"))
SUFFIXES = (".sqlite3", ".sqlite", ".db", ".sqlite3.gz", ".db.gz",
            ".zip", ".tar", ".tar.gz", ".tgz", ".bak", ".sql", ".dump")

def scan():
    found = {}
    for root in ROOTS:
        if not root.is_dir():
            continue
        for parent, dirs, files in os.walk(root, followlinks=False):
            path = Path(parent)
            depth = len(path.relative_to(root).parts)
            if depth >= 4:
                dirs[:] = []
            dirs[:] = [name for name in dirs if not name.startswith(".")][:50]
            for name in files[:300]:
                if len(found) >= 200:
                    return found
                if not name.lower().endswith(SUFFIXES):
                    continue
                p = path / name
                if p.is_symlink():
                    continue
                try:
                    if not p.is_file():
                        continue
                    st = p.stat()
                except OSError:
                    continue
                found[str(p)] = (p, st)
    return found

def count_sqlite(path):
    # Arquivo de backup é aberto de forma estritamente read-only. Immutable
    # evita criar arquivos WAL/SHM ou mexer em bloqueios; não usar no DB ativo.
    if not path.name.lower().endswith((".sqlite3", ".sqlite", ".db")):
        return None
    conn = None
    try:
        conn = sqlite3.connect("file:" + quote(str(path), safe="/") +
                               "?mode=ro&immutable=1", uri=True, timeout=1)
        conn.execute("PRAGMA query_only=ON")
        nomes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "site_publico_boletimaluno" not in nomes:
            return "sem_tabela_boletim"
        rows = conn.execute("SELECT COUNT(*) FROM site_publico_boletimaluno WHERE periodo_id=3")
        return next(rows)[0]
    except (sqlite3.Error, OSError):
        return "não_legível_ou_outro_formato"
    finally:
        if conn:
            conn.close()

def main():
    print("=== INVENTÁRIO NÃO DESTRUTIVO DE BACKUPS EMECA ===")
    found = scan()
    if not found:
        print("Nenhuma cópia identificada nas pastas de backups verificadas.")
        print("Isso NÃO prova que não existam cópias em outros locais/volumes.")
        return
    print("Arquivos candidatos encontrados:", len(found))
    entries = sorted(found.values(), key=lambda x:x[1].st_mtime, reverse=True)
    for path,stat in entries[:30]:
        d=datetime.datetime.fromtimestamp(stat.st_mtime,datetime.timezone.utc)
        # Não exibe localização de segredos, nomes de alunos nem dados escolares.
        print("Arquivo:", path.name[:100],
              "| data UTC:", d.strftime("%Y-%m-%d %H:%M"),
              "| MiB:", round(stat.st_size/1048576,2),
              "| boletins período 3:", count_sqlite(path))
    if len(found)>30:
        print("Outros",len(found)-30,"arquivos não exibidos.")
    print("NADA restaurado, copiado, excluído ou alterado.")

if __name__ == "__main__":
    main()
