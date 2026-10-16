#!/usr/bin/env python3
"""Cria backup consistente do EMECA e o cifra com AES-256.

Não inclui o arquivo .env. A senha deve ser fornecida somente pela variável
EMECA_BACKUP_PASSPHRASE.
"""
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    passphrase = os.environ.get("EMECA_BACKUP_PASSPHRASE", "")
    if len(passphrase) < 20:
        raise SystemExit("Defina EMECA_BACKUP_PASSPHRASE com pelo menos 20 caracteres.")

    data_dir = Path(os.environ.get("DJANGO_DATA_DIR", "/data")).resolve()
    db_path = Path(os.environ.get("DJANGO_DB_PATH", str(data_dir / "emeca.sqlite3"))).resolve()
    backup_dir = Path(os.environ.get("EMECA_BACKUP_DIR", "/srv/backups/emeca")).resolve()
    retention_days = max(7, int(os.environ.get("EMECA_BACKUP_RETENTION_DAYS", "30")))

    if not db_path.is_file():
        raise SystemExit(f"Banco SQLite não encontrado em {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        backup_dir.chmod(0o700)
    except OSError:
        pass

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = backup_dir / f"emeca-{stamp}.tar.gz.enc"

    with tempfile.TemporaryDirectory(prefix="emeca-backup-") as tmp:
        tmp_path = Path(tmp)
        db_snapshot = tmp_path / "emeca.sqlite3"

        origem = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        destino_db = sqlite3.connect(db_snapshot)
        try:
            origem.backup(destino_db)
        finally:
            destino_db.close()
            origem.close()

        pacote = tmp_path / "emeca.tar.gz"
        with tarfile.open(pacote, "w:gz") as tar:
            tar.add(db_snapshot, arcname="database/emeca.sqlite3")
            media = data_dir / "media"
            if media.is_dir():
                tar.add(media, arcname="media")

        subprocess.run(
            [
                "openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2",
                "-iter", "200000", "-pass", "env:EMECA_BACKUP_PASSPHRASE",
                "-in", str(pacote), "-out", str(destino),
            ],
            check=True,
            env=os.environ.copy(),
        )

    try:
        destino.chmod(0o600)
    except OSError:
        pass

    limite = datetime.now(timezone.utc) - timedelta(days=retention_days)
    for item in backup_dir.glob("emeca-*.tar.gz.enc"):
        try:
            modificado = datetime.fromtimestamp(item.stat().st_mtime, timezone.utc)
            if modificado < limite:
                item.unlink()
        except OSError:
            continue

    print(destino)


if __name__ == "__main__":
    main()
