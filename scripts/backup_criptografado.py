#!/usr/bin/env python3
"""Cria backup consistente do EMECA e cifra o pacote com AES-256.

Não inclui arquivos .env. A senha de backup deve ser fornecida somente por
EMECA_BACKUP_PASSPHRASE.
"""
import os
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _snapshot_sqlite(destino, data_dir):
    db_path = Path(
        os.environ.get("DJANGO_DB_PATH", str(data_dir / "emeca.sqlite3"))
    ).resolve()
    if not db_path.is_file():
        raise SystemExit(f"Banco SQLite não encontrado em {db_path}")

    origem = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    alvo = sqlite3.connect(destino)
    try:
        origem.backup(alvo)
    finally:
        alvo.close()
        origem.close()


def _snapshot_postgres(destino):
    senha = os.environ.get("DJANGO_DB_PASSWORD", "")
    if not senha:
        raise SystemExit("DJANGO_DB_PASSWORD não está definido para o backup PostgreSQL.")

    ambiente = os.environ.copy()
    ambiente["PGPASSWORD"] = senha
    comando = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--host", os.environ.get("DJANGO_DB_HOST", "db"),
        "--port", os.environ.get("DJANGO_DB_PORT", "5432"),
        "--username", os.environ.get("DJANGO_DB_USER", "emeca"),
        "--file", str(destino),
        os.environ.get("DJANGO_DB_NAME", "emeca"),
    ]
    subprocess.run(comando, check=True, env=ambiente)


def main():
    passphrase = os.environ.get("EMECA_BACKUP_PASSPHRASE", "")
    if len(passphrase) < 20:
        raise SystemExit(
            "Defina EMECA_BACKUP_PASSPHRASE com pelo menos 20 caracteres."
        )

    data_dir = Path(os.environ.get("DJANGO_DATA_DIR", "/data")).resolve()
    backup_dir = Path(os.environ.get("EMECA_BACKUP_DIR", "/backups")).resolve()
    retention_days = max(
        7,
        int(os.environ.get("EMECA_BACKUP_RETENTION_DAYS", "30")),
    )
    db_engine = os.environ.get("DJANGO_DB_ENGINE", "sqlite").strip().lower()

    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        backup_dir.chmod(0o700)
    except OSError:
        pass

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = backup_dir / f"emeca-{stamp}.tar.gz.enc"

    with tempfile.TemporaryDirectory(prefix="emeca-backup-") as tmp:
        tmp_path = Path(tmp)

        if db_engine in {"postgres", "postgresql"}:
            db_snapshot = tmp_path / "emeca.pgdump"
            _snapshot_postgres(db_snapshot)
            arcname = "database/emeca.pgdump"
        elif db_engine == "sqlite":
            db_snapshot = tmp_path / "emeca.sqlite3"
            _snapshot_sqlite(db_snapshot, data_dir)
            arcname = "database/emeca.sqlite3"
        else:
            raise SystemExit(
                "DJANGO_DB_ENGINE inválido para backup. Use sqlite ou postgresql."
            )

        pacote = tmp_path / "emeca.tar.gz"
        with tarfile.open(pacote, "w:gz") as tar:
            tar.add(db_snapshot, arcname=arcname)
            media = data_dir / "media"
            if media.is_dir():
                tar.add(media, arcname="media")

        subprocess.run(
            [
                "openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2",
                "-iter", "200000",
                "-pass", "env:EMECA_BACKUP_PASSPHRASE",
                "-in", str(pacote),
                "-out", str(destino),
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
            modificado = datetime.fromtimestamp(
                item.stat().st_mtime,
                timezone.utc,
            )
            if modificado < limite:
                item.unlink()
        except OSError:
            continue

    print(destino)


if __name__ == "__main__":
    main()
