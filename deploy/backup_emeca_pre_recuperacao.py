#!/usr/bin/env python3
"""Copia consistente de SEGURANÇA do SQLite EMECA no volume /backups.
Não altera banco original, não reinicia serviços e não apaga backups antigos.
"""
import subprocess

CODE = r'''
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from django.conf import settings
base = settings.DATABASES["default"]
if base["ENGINE"] != "django.db.backends.sqlite3":
    print("BACKUP_EMECA: BANCO_NAO_SQLITE; use procedimento próprio de backup do PostgreSQL.")
else:
    original = str(base["NAME"])
    destino_dir = "/backups"
    if not os.path.isfile(original):
        print("BACKUP_EMECA: FONTE_INDISPONIVEL")
    elif not os.path.isdir(destino_dir):
        print("BACKUP_EMECA: DIRETORIO_INDISPONIVEL")
    else:
        nome = "emeca-pre-recuperacao-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-"
        fd, arquivo = tempfile.mkstemp(prefix=nome,suffix=".sqlite3",dir=destino_dir)
        os.close(fd)
        try:
            with sqlite3.connect("file:" + original + "?mode=ro", uri=True,timeout=20) as origem:
                with sqlite3.connect(arquivo,timeout=20) as copia:
                    origem.backup(copia,pages=100,sleep=0.1)
                    ok = copia.execute("PRAGMA integrity_check").fetchone()[0]
                    if ok != "ok":
                        raise RuntimeError("Integridade da copia nao confirmada")
            os.chmod(arquivo,0o600)
            print("BACKUP_EMECA: OK")
            print("ARQUIVO_BACKUP: " + arquivo)
            print("BYTES_BACKUP: " + str(os.stat(arquivo).st_size))
            print("INTEGRIDADE_BACKUP: OK")
        except Exception as e:
            print("BACKUP_EMECA: FALHOU - " + type(e).__name__)
            print("Copia nao validada. Nao restaure este arquivo.")
'''
def main():
    print("=== Cópia de preservação do EMECA, sem alterar o banco em uso ===")
    try:
        p = subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",CODE],
            capture_output=True,text=True,timeout=90,check=False,
        )
    except (subprocess.TimeoutExpired,OSError) as exc:
        print("Backup indisponível:",type(exc).__name__)
        return
    if p.returncode:
        print("Não foi possível criar cópia. Código:",p.returncode,
              "detalhes técnicos ocultados para não divulgar dados.")
        return
    for line in p.stdout.splitlines():
        if line.startswith(("BACKUP_EMECA:","ARQUIVO_BACKUP:","BYTES_BACKUP:","INTEGRIDADE_BACKUP:")):
            print(line)
    print("Nenhum dado escolar foi excluído nem substituído.")

if __name__=="__main__":
    main()
