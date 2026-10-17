#!/usr/bin/env bash
# Backups consistentes dos dois bancos antes de separar as contas WhatsApp.
# Não para contêineres, não altera tabelas, não limpa volumes.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
stamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="/srv/backups/emeca"
mkdir -p "$backup_dir"

echo "[1/2] Backup consistente do EMECA (SQLite)"
docker compose exec -T web python -c '
import sqlite3
source = sqlite3.connect("/data/emeca.sqlite3")
destination = sqlite3.connect("/backups/emeca-antes-troca-wa-'"$stamp"'.sqlite3")
try:
    source.backup(destination)
finally:
    destination.close()
    source.close()
'
test -s "$backup_dir/emeca-antes-troca-wa-$stamp.sqlite3"

echo "[2/2] Backup transacional WA-AKG MySQL"
dump="$backup_dir/wa-akg-antes-troca-$stamp.sql"
if ! docker compose -f deploy/wa-akg/compose.secure.yaml exec -T db sh -c \
    'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE"' > "$dump"; then
  rm -f "$dump"
  echo "Backup WA-AKG falhou. Não prossiga com a atualização." >&2
  exit 1
fi
chmod 600 "$backup_dir/emeca-antes-troca-wa-$stamp.sqlite3" "$dump"
test -s "$dump"
echo "Backups criados e validados no diretório $backup_dir"
