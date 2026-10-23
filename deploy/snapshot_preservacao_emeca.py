#!/usr/bin/env python3
"""Snapshot pontual de preservação do EMECA, nunca substitui ou apaga backups.

Rodar DENTRO de emeca-web-1 (montagem /backups). Restringe permissões a 0600.
Suporta SQLite e PostgreSQL. Não acessa o WA-AKG.
"""
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

def main():
    os.umask(0o077)
    root=Path("/backups")
    if not root.is_dir():
        raise SystemExit("ERRO: /backups não está montado; nada foi salvo.")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    engine=os.getenv("DJANGO_DB_ENGINE","sqlite").strip().lower()
    if engine=="sqlite":
        source=Path(os.getenv("DJANGO_DB_PATH","/data/emeca.sqlite3"))
        if not source.is_file():
            raise SystemExit("ERRO: arquivo do banco SQLite não encontrado; nada foi salvo.")
        target=root / ("emeca-preservacao-"+stamp+".sqlite3")
        if target.exists():
            raise SystemExit("Já existe snapshot com esse nome; nada foi substituído.")
        origin=sqlite3.connect("file:"+quote(str(source),safe="/")+"?mode=ro",uri=True)
        try:
            # SQLite backup API cria uma fotografia consistente mesmo com
            # conexões concorrentes. Nunca copia diretamente o arquivo aberto.
            dest=sqlite3.connect(str(target))
            try:
                origin.backup(dest,pages=256,sleep=0.05)
            finally:
                dest.close()
        finally:
            origin.close()
    elif engine in {"postgres","postgresql"}:
        target=root / ("emeca-preservacao-"+stamp+".pgdump")
        if target.exists():
            raise SystemExit("Já existe snapshot com esse nome; nada foi substituído.")
        env=os.environ.copy()
        env["PGPASSWORD"]=env.get("DJANGO_DB_PASSWORD","")
        args=[
            "pg_dump","--format=custom","--no-owner","--no-privileges",
            "--host",env.get("DJANGO_DB_HOST","db"),
            "--port",env.get("DJANGO_DB_PORT","5432"),
            "--username",env.get("DJANGO_DB_USER","emeca"),
            "--file",str(target),env.get("DJANGO_DB_NAME","emeca"),
        ]
        subprocess.run(args,check=True,env=env,capture_output=True)
    else:
        raise SystemExit("Tipo de banco não suportado, nada foi salvo.")
    target.chmod(0o600)
    print("SNAPSHOT EMECA CRIADO:",target.name,
          "| MB:",round(target.stat().st_size/1048576,2))
    print("Arquivo contém dados escolares sensíveis. Guardar com acesso restrito e criptografar para transferência.")
    print("Nenhum backup anterior foi alterado ou eliminado.")

if __name__=="__main__":
    main()
