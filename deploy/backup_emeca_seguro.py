"""Snapshot seguro do SQLite EMECA usando API nativa de backup.

Uso (do host):
  docker exec -i emeca-web-1 python manage.py shell < deploy/backup_emeca_seguro.py

Roda DENTRO do Django, não apaga nem altera tabelas e gera um único .sqlite3
no diretório /backups (montado em /srv/backups/emeca no servidor).
"""
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from django.db import connection
from django.conf import settings

if connection.vendor != "sqlite":
    print("BACKUP_NAO_EXECUTADO: banco não é SQLite; não tente cópia de arquivo. Use pg_dump validado.")
else:
    origem = Path(settings.DATABASES["default"]["NAME"]).resolve()
    destino_dir = Path("/backups")
    if not origem.is_file() or not destino_dir.is_dir():
        print("BACKUP_NAO_EXECUTADO: origem ou pasta /backups indisponível.")
    else:
        os.umask(0o077)
        temp = None
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            final = destino_dir / ("emeca-preservacao-" + stamp + ".sqlite3")
            if final.exists():
                raise FileExistsError("Já existe um backup com o mesmo nome.")
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".emeca-backup-", suffix=".partial",
                dir=str(destino_dir), delete=False
            ) as handle:
                temp = Path(handle.name)
            os.chmod(temp, 0o600)
            uri = "file:" + quote(str(origem), safe="/") + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=15) as source:
                with sqlite3.connect(str(temp), timeout=15) as target:
                    source.backup(target, pages=256, sleep=0.1)
                    verificado = target.execute("PRAGMA integrity_check").fetchone()
                    if not verificado or verificado[0] != "ok":
                        raise RuntimeError("Falha na checagem de integridade do backup.")
            os.replace(temp, final)
            temp = None
            os.chmod(final, 0o600)
            print("BACKUP_OK:", str(final), "| bytes:", final.stat().st_size,
                  "| integridade: OK")
            print("No host: /srv/backups/emeca/" + final.name)
            print("Nenhuma tabela da escola foi alterada.")
        except (OSError, sqlite3.Error, RuntimeError) as exc:
            print("BACKUP_FALHOU:", type(exc).__name__, "— banco original não foi alterado.")
        finally:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
