#!/usr/bin/env bash
# Preparação e implantação única EMECA + WA-AKG.
# USO: bash deploy/atualizar_lote_seguro.sh --preflight
#      EMECA_APLICAR_LOTE=SIM bash deploy/atualizar_lote_seguro.sh --aplicar
# Nunca é executado automaticamente pelo git pull. Exige confirmação.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
WA_COMPOSE="$ROOT/deploy/wa-akg/compose.secure.yaml"
WA_ENV="$ROOT/deploy/wa-akg/.env"
WA_ARGS=(--env-file "$WA_ENV" -f "$WA_COMPOSE")
PATCHER="$ROOT/deploy/wa-akg/aplicar_correcoes.py"
DEST_BASE="/srv/backups/emeca"
MODO="${1:---preflight}"

falhar() { echo "ERRO: $*" >&2; exit 1; }
log() { printf '\n[EMECA] %s\n' "$*"; }
exigir() { command -v "$1" >/dev/null || falhar "Falta comando: $1"; }

case "$MODO" in
  --preflight|--aplicar) ;;
  *) falhar "Use --preflight (sem mudanças) ou --aplicar (com confirmação e backups)." ;;
esac

log "Conferindo ferramentas e código local"
for ferramenta in docker git python3; do exigir "$ferramenta"; done
test -r "$ROOT/.env" || falhar "Arquivo .env do EMECA não encontrado."
test -r "$WA_COMPOSE" || falhar "Compose WA-AKG não encontrado."
test -r "$WA_ENV" || falhar "Arquivo .env do WA-AKG não encontrado em deploy/wa-akg/.env."
test -r "$PATCHER" || falhar "Aplicador WA-AKG não encontrado."
test -d /srv/projetos/wa-akg || falhar "WA-AKG não está em /srv/projetos/wa-akg."
docker compose config --quiet
docker compose "${WA_ARGS[@]}" config --quiet
docker compose ps
docker compose "${WA_ARGS[@]}" ps
git rev-parse --short HEAD
if test -n "$(git status --porcelain)"; then
  log "Há arquivos EMECA alterados localmente:"
  git status --short
  if test "$MODO" = "--aplicar"; then
    falhar "Resolva alterações locais com segurança ANTES do lote; não usar git reset --hard."
  fi
fi

log "Conferindo código e migrações, sem aplicar nenhuma mudança"
python3 -m py_compile "$PATCHER"
python3 "$PATCHER" --dry-run
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py migrate --plan
# Evitar liberação inesperada de PDFs pendentes após reinício do worker.
FILA="$(docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
print(EnvioBoletimWhatsApp.objects.filter(
    status__in=["PENDENTE", "PROCESSANDO"]
).count())' | tail -1 | tr -d '\r')"
case "$FILA" in
  ''|*[!0-9]*) falhar "Não foi possível verificar a fila de boletins." ;;
esac
log "Lotes de PDF em fila/processamento: $FILA"
if test "$MODO" = "--aplicar" && test "$FILA" != "0"; then
  falhar "Há boletins aguardando envio. Aguarde/revise os lotes antes de reiniciar o worker."
fi
# Agendamentos WA-AKG interrompidos não podem ser repetidos às cegas.
# Antes da atualização, exigir revisão manual dos PROCESSING, sem ler
# nem exibir telefone, mensagem ou qualquer dado do destinatário.
WA_INCERTOS="$(docker compose "${WA_ARGS[@]}" exec -T db sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -Nse "SELECT COUNT(*) FROM ScheduledMessage WHERE status = \\"PROCESSING\\";" "$MYSQL_DATABASE"' \
  | tail -1 | tr -d '\r')" || falhar "Não foi possível conferir agendamentos WA-AKG."
case "$WA_INCERTOS" in
  ''|*[!0-9]*) falhar "A contagem de agendamentos WA-AKG é inválida." ;;
esac
log "Agendamentos WA-AKG em estado incerto (PROCESSING): $WA_INCERTOS"
if test "$MODO" = "--aplicar" && test "$WA_INCERTOS" != "0"; then
  falhar "Existem agendamentos WA-AKG com envio incerto; revise antes da implantação."
fi

if test "$MODO" = "--preflight"; then
  log "Pré-verificação concluída. Nenhuma imagem ou banco foi modificado."
  log "Na manutenção, execute explicitamente --aplicar após confirmar a versão e os backups."
  exit 0
fi

test "${EMECA_APLICAR_LOTE:-}" = "SIM" || falhar \
  "Para aplicar, defina EMECA_APLICAR_LOTE=SIM após avaliar a pré-verificação."

log "Validando que o banco EMECA é SQLite (backup consistente integrado)"
BANCO="$(docker compose exec -T web python manage.py shell -c \
  'from django.db import connection; print(connection.vendor)' | tail -1 | tr -d '\r')"
test "$BANCO" = "sqlite" || falhar \
  "Banco detectado: $BANCO. Não há backup PostgreSQL automático neste script. Pare e prepare o backup específico."

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$DEST_BASE/implantacao-$STAMP"
mkdir -p "$DEST"
chmod 700 "$DEST"
log "Backups em $DEST; NÃO continuar caso qualquer arquivo falhe"

# O snapshot SQLite usa sqlite3.backup, seguro com WAL e usuários conectados.
SQLITE_SNAPSHOT="implantacao-$STAMP.sqlite3"
docker compose exec -T web python - "$SQLITE_SNAPSHOT" <<'PY'
import os
import sqlite3
import sys
from pathlib import Path

origem = Path(os.environ.get("DJANGO_DB_PATH", "/data/emeca.sqlite3"))
destino = Path("/backups") / sys.argv[1]
if not origem.is_file() or destino.exists():
    raise SystemExit("Banco ausente ou arquivo de backup já existente.")
fonte = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
alvo = sqlite3.connect(str(destino))
try:
    fonte.backup(alvo)
    resultado = alvo.execute("PRAGMA quick_check").fetchone()
    if resultado != ("ok",):
        raise RuntimeError("Verificação de integridade do snapshot falhou.")
finally:
    alvo.close()
    fonte.close()
destino.chmod(0o600)
print("Backup SQLite consistente verificado.")
PY
test -s "$DEST_BASE/$SQLITE_SNAPSHOT" || falhar "Snapshot SQLite vazio."
# O /backups do container web é bind mount para /srv/backups/emeca.
mv "$DEST_BASE/$SQLITE_SNAPSHOT" "$DEST/emeca.sqlite3"

# As mídias institucionais são importantes para os PDFs com logo oficial.
docker compose exec -T web sh -c 'tar -czf - -C /data media' > "$DEST/emeca-media.tar.gz"
test -s "$DEST/emeca-media.tar.gz" || falhar "Arquivo de mídias EMECA vazio."

# Salvar dados do WhatsApp preserva anexos e arquivos de sessão no volume.
docker compose "${WA_ARGS[@]}" exec -T app sh -c \
  'tar -czf - -C /app data uploads' > "$DEST/wa-akg-volumes.tar.gz"
test -s "$DEST/wa-akg-volumes.tar.gz" || falhar "Arquivo de volumes WA-AKG vazio."

DUMP="$DEST/wa-akg.sql"
if ! docker compose "${WA_ARGS[@]}" exec -T db sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE"' \
  > "$DUMP"; then
  rm -f "$DUMP"
  falhar "Backup MySQL WA-AKG falhou: implantação interrompida."
fi
test -s "$DUMP" || falhar "Dump MySQL WA-AKG vazio."
# Evitar a falsa sensação de backup: conferir assinatura de dump completo,
# legibilidade das mídias e restauração de SQLite em processo separado.
if ! grep -q '^-- Dump completed on ' "$DUMP"; then
  falhar "O dump WA-AKG não terminou normalmente. Nada será implantado."
fi
gzip -t "$DEST/emeca-media.tar.gz" || falhar "Backup de mídias EMECA corrompido."
gzip -t "$DEST/wa-akg-volumes.tar.gz" || falhar "Backup de volumes WA-AKG corrompido."
python3 - "$DEST/emeca.sqlite3" <<'PY'
import sqlite3
import sys
from pathlib import Path

arquivo = Path(sys.argv[1])
with sqlite3.connect(f"file:{arquivo}?mode=ro", uri=True) as banco:
    resultado = banco.execute("PRAGMA integrity_check").fetchone()
    if resultado != ("ok",):
        raise SystemExit("Backup SQLite não passou na verificação de integridade.")
print("Integridade do backup SQLite conferida.")
PY
chmod 600 "$DEST"/*
# Simular restauração de banco SQLite em um diretório descartável e
# conferir leitura das mídias e conclusão do dump MySQL.
python3 scripts/validar_backups_lote.py "$DEST"
printf '%s\n' "$(git rev-parse HEAD)" > "$DEST/commit-emeca.txt"
docker inspect --format '{{.Image}}' wa-akg-app > "$DEST/imagem-wa-anterior.txt" || true
docker inspect --format '{{.Image}}' emeca-web-1 > "$DEST/imagem-emeca-anterior.txt" || true
log "Backups concluídos. Arquivos e snapshots permanecem privados em $DEST"

log "Aplicando sobreposição WA-AKG com backup dos fontes pelo patcher"
python3 "$PATCHER"
log "Compilando imagens antes de substituir containers ativos"
docker compose "${WA_ARGS[@]}" build app
docker compose build web whatsapp-worker
# A nova imagem precisa passar pelo Django check ANTES de interromper
# a aplicação atual. O entrypoint deve ser desabilitado explicitamente.
docker compose run --rm --no-deps -T -e SKIP_DJANGO_INIT=1 web \
  python manage.py check

log "Pausando worker ANTES de reiniciar WhatsApp e migrar EMECA"
docker compose stop whatsapp-worker
log "Substituindo somente a aplicação WA-AKG, preservando banco/volumes"
docker compose "${WA_ARGS[@]}" up -d --no-deps app
log "Substituindo EMECA web (entrypoint aplicará migrações automaticamente)"
docker compose up -d --no-deps web
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py migrate --check
log "Substituindo worker da fila de PDFs depois das migrações"
docker compose up -d --no-deps whatsapp-worker

log "Verificando estado dos serviços e integridade sem enviar mensagens"
docker compose ps
docker compose "${WA_ARGS[@]}" ps
docker compose exec -T web python manage.py showmigrations site_publico
echo "IMPLANTAÇÃO CONCLUÍDA. Os testes com WhatsApp real continuam manuais."
echo "Backups localizados em: $DEST"
