#!/usr/bin/env bash
# Recuperação de indisponibilidade do WA-AKG após troca de Baileys.
# Uso padrão (--verificar) não altera nada.
# --restaurar: recoloca APENAS a imagem anterior (sem limpar dados/sessões).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${WA_AKG_DIR:-/srv/projetos/wa-akg}"
COMPOSE="$ROOT/deploy/wa-akg/compose.secure.yaml"
MODE="${1:---verificar}"
cd "$ROOT"

if [[ "$MODE" != "--verificar" && "$MODE" != "--restaurar" ]]; then
  echo "Uso: bash $0 [--verificar|--restaurar]" >&2
  exit 2
fi

echo "=== WA-AKG: estado do container ==="
docker ps -a --filter 'name=^/wa-akg-app$' --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker inspect -f 'Status={{.State.Status}} RestartCount={{.RestartCount}} ExitCode={{.State.ExitCode}}' wa-akg-app
echo "=== Porta HTTP do WA-AKG no host ==="
if python3 - <<'PY'
import urllib.error, urllib.request
url="http://127.0.0.1:3100/"
try:
    with urllib.request.urlopen(urllib.request.Request(url, method="GET"),timeout=6) as resp:
        print("HTTP WA-AKG:",resp.status)
        raise SystemExit(0 if resp.status<500 else 1)
except urllib.error.HTTPError as err:
    print("HTTP WA-AKG:",err.code)
    raise SystemExit(0 if err.code<500 else 1)
except Exception as err:
    print("WA-AKG não responde:",type(err).__name__)
    raise SystemExit(1)
PY
then
  echo "O serviço WA-AKG responde no host. Não é seguro forçar rollback sem verificar a comunicação com o EMECA."
  exit 0
fi

echo "=== Imagens de rollback disponíveis ==="
mapfile -t TAGS < <(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^wa-akg-emeca-before-rc14:' | sort -r)
if [[ "${#TAGS[@]}" -eq 0 ]]; then
  echo "ERRO: não há imagem anterior etiquetada. NÃO apagando nem reiniciando nada." >&2
  exit 1
fi
OLD_TAG="${TAGS[0]}"
echo "Imagem anterior: $OLD_TAG"
echo "Versão contida na imagem anterior:"
docker run --rm --entrypoint node "$OLD_TAG" -e '
const p=require("/app/node_modules/@whiskeysockets/baileys/package.json");
console.log("Baileys:",p.version);
'

STAMP="${OLD_TAG##*:}"
BACKUP="$SRC/.emeca-backups/baileys-rc14-$STAMP"
if [[ ! -s "$BACKUP/package.json" || ! -s "$BACKUP/package-lock.json" ]]; then
  echo "ERRO: manifestos de backup não encontrados em $BACKUP. Sem modificações." >&2
  exit 1
fi
echo "Manifestos preservados em: $BACKUP"

if [[ "$MODE" != "--restaurar" ]]; then
  echo "Modo apenas leitura. Para restaurar execute o mesmo script com --restaurar."
  exit 0
fi

echo "=== Protegendo envios pendentes antes da recuperação ==="
docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n=EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
print("Boletins em aberto:",n)
if n: raise SystemExit("Há boletins em processamento. Restauração cancelada.")
'
ATIVOS="$(docker exec wa-akg-db sh -c 'mysql -N -s -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' 2>/dev/null | tr -d '[:space:]')"
if [[ "$ATIVOS" != "0" ]]; then
  echo "Campanhas em andamento ou estado inconclusivo. Restauração cancelada." >&2
  exit 1
fi

echo "=== Restaurando imagem anterior sem build ou alteração do banco ==="
CURRENT_IMAGE="$(docker inspect -f '{{.Image}}' wa-akg-app)"
RECOVERY_TAG="wa-akg-emeca-rc14-to-investigate:$(date -u +%Y%m%dT%H%M%SZ)"
docker image tag "$CURRENT_IMAGE" "$RECOVERY_TAG"
docker image tag "$OLD_TAG" 'wa-akg-app:latest'
docker compose -f "$COMPOSE" up -d --no-deps --force-recreate app

echo "=== Verificando HTTP restaurado ==="
if ! python3 - <<'PY'
import urllib.error,urllib.request,time
url="http://127.0.0.1:3100/"
for _ in range(15):
    try:
        with urllib.request.urlopen(url,timeout=3) as res:
            print("HTTP após rollback:",res.status)
            raise SystemExit(0 if res.status<500 else 1)
    except urllib.error.HTTPError as err:
        print("HTTP após rollback:",err.code)
        if err.code<500: raise SystemExit(0)
    except Exception: pass
    time.sleep(2)
print("Não foi possível confirmar a recuperação do HTTP.")
raise SystemExit(1)
PY
then
  echo "AVISO: imagem anterior reativada mas HTTP não confirmou recuperação. Verifique logs antes de nova ação." >&2
  exit 1
fi

cp -p "$BACKUP/package.json" "$SRC/package.json"
cp -p "$BACKUP/package-lock.json" "$SRC/package-lock.json"
echo "HTTP recuperado. Manifestos anteriores restaurados."
echo "A imagem problemática permanece preservada em $RECOVERY_TAG."
echo "Não houve reenvio automático; confirme CONNECTED na página antes de qualquer teste."
