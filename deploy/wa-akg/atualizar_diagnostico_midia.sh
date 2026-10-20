#!/usr/bin/env bash
# Instrumentação segura de mídia do WA-AKG; não envia mensagens.
# Não apaga volumes, AuthState, histórico ou banco da escola.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

sem_envios_ativos() {
  docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n = EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE", "PROCESSANDO"]).count()
print("Boletins pendentes ou em processamento:", n)
if n: raise SystemExit("Há boletins pendentes. Atualização suspensa.")
'
  local ativos
  ativos="$(docker exec wa-akg-db sh -c 'mysql -N -s -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' | tr -d '[:space:]')"
  if [[ "$ativos" != "0" ]]; then
    echo "Campanhas ativas ou estado desconhecido: ${ativos:-desconhecido}. Atualização suspensa." >&2
    exit 1
  fi
}

echo "[1/5] Verificando filas..."
sem_envios_ativos
echo "[2/5] Testando patch sem envio de mensagens..."
python3 -m unittest discover -s deploy/wa-akg -p 'test_*.py' -v
python3 deploy/wa-akg/aplicar_correcoes.py --dry-run
echo "[3/5] Aplicando patch no código..."
python3 deploy/wa-akg/aplicar_correcoes.py
echo "[4/5] Compilando apenas WA-AKG..."
docker compose -f deploy/wa-akg/compose.secure.yaml build app
echo "[5/5] Rechecando filas e atualizando apenas WA-AKG..."
sem_envios_ativos
docker compose -f deploy/wa-akg/compose.secure.yaml up -d --no-deps app
echo "Instrumentação instalada. Nenhum banco ou volume removido."
echo "Aguarde WhatsApp CONNECTED antes do teste para o próprio número."
