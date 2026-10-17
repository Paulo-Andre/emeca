#!/usr/bin/env bash
# Executar no mini PC: bash deploy/wa-akg/implantar_emeca.sh
# Não altera credenciais, chaves, volume de autenticação ou banco por DDL.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$ROOT/deploy/wa-akg/compose.secure.yaml"
PATCHER="$ROOT/deploy/wa-akg/aplicar_correcoes.py"
BACKUP_DIR="/srv/backups/wa-akg"

echo "[1/7] Validando caminhos e containers"
test -f "$COMPOSE"
test -d /srv/projetos/wa-akg
docker compose -f "$COMPOSE" ps

echo "[2/7] Salvando backup transacional do banco WA-AKG"
mkdir -p "$BACKUP_DIR"
BACKUP="$BACKUP_DIR/wa-akg-$(date +%Y%m%d-%H%M%S).sql"
if ! docker compose -f "$COMPOSE" exec -T db \
    sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE"' \
    > "$BACKUP"; then
  rm -f "$BACKUP"
  echo "Falha no backup. Implantação interrompida; nada foi aplicado." >&2
  exit 1
fi
chmod 600 "$BACKUP"
echo "Backup criado em $BACKUP"

echo "[3/7] Conferindo compatibilidade do código WA-AKG"
python3 "$PATCHER" --dry-run

echo "[4/7] Fazendo backup dos fontes e aplicando correções"
python3 "$PATCHER"

echo "[5/7] Compilando imagem WA-AKG (serviço ativo permanece disponível)"
docker compose -f "$COMPOSE" build app

echo "[6/7] Atualizando apenas a aplicação WA-AKG; mantendo banco e volumes"
docker compose -f "$COMPOSE" up -d --no-deps app

echo "[7/7] Atualizando EMECA e conferindo integração"
cd "$ROOT"
docker compose up -d --build
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py test \
  usuarioSec.test_whatsapp \
  usuarioSec.test_isolamento_contas_whatsapp \
  usuarioSec.test_limpeza_sessao_whatsapp \
  usuarioSec.test_grupos_agendamentos_whatsapp
docker compose exec -T web python manage.py diagnosticar_contatos_whatsapp

echo "Implantação concluída. Faça Ctrl+Shift+R na página de mensagens."
