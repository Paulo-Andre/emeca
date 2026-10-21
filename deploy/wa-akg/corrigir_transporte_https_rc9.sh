#!/usr/bin/env bash
# Correção HTTPS para upload de PDF com Baileys rc.9 preservado.
# --verificar: sem build nem reinício.
# --aplicar: build e troca apenas depois de todos os testes, com rollback.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${WA_AKG_DIR:-/srv/projetos/wa-akg}"
COMPOSE="$ROOT/deploy/wa-akg/compose.secure.yaml"
MODE="${1:---verificar}"
cd "$ROOT"

if [[ "$MODE" != "--verificar" && "$MODE" != "--aplicar" ]]; then
  echo "Uso: bash $0 [--verificar|--aplicar]" >&2; exit 2
fi
echo "[1/6] Teste real de compatibilidade em imagem temporária sem rede..."
bash deploy/wa-akg/verificar_transporte_https_rc9_sem_build.sh
echo "[2/6] Testes unitários sem WhatsApp..."
python3 -m unittest discover -s deploy/wa-akg -p 'test_patch_https_rc9.py' -v
echo "[3/6] Conferindo modificações locais..."
python3 deploy/wa-akg/preparar_transporte_https_rc9.py --source "$SRC" --dry-run
if [[ "$MODE" == "--verificar" ]]; then
  echo "Verificação encerrada: sem build, reinício, envio ou modificações."
  exit 0
fi

sem_envios_ativos() {
  docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n=EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
print("Boletins em aberto:",n)
if n: raise SystemExit("Boletins ativos. Atualização cancelada.")
'
  local n
  n="$(docker exec wa-akg-db sh -c 'mysql -N -s -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' 2>/dev/null | tr -d '[:space:]')"
  if [[ "$n" != "0" ]]; then echo "Lotes WA-AKG ativos ou consulta falhou. Cancelado." >&2; exit 1; fi
}
echo "Verificando filas..."
sem_envios_ativos

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OLD_TAG="wa-akg-before-https-rc9:$STAMP"
docker image tag "$(docker inspect -f '{{.Image}}' wa-akg-app)" "$OLD_TAG"
BACKUP_DOCKERFILE="$(mktemp)"
cp -p "$SRC/Dockerfile" "$BACKUP_DOCKERFILE"
SWAPPED=0
recover() {
  code=$?
  if [[ "$code" -ne 0 ]]; then
    cp -p "$BACKUP_DOCKERFILE" "$SRC/Dockerfile" || true
    if [[ "$SWAPPED" -eq 1 ]]; then
      echo "Aplicativo falhou: recuperando imagem anterior..." >&2
      docker image tag "$OLD_TAG" wa-akg-app:latest || true
      docker compose -f "$COMPOSE" up -d --no-deps --force-recreate app || true
    fi
    echo "Falha; não executar envios. Contêiner anterior preservado/recuperado." >&2
  fi
  rm -f "$BACKUP_DOCKERFILE"
}
trap recover EXIT

echo "[4/6] Preparando alteração apenas no uploader da biblioteca rc.9..."
python3 deploy/wa-akg/preparar_transporte_https_rc9.py --source "$SRC"
echo "Construindo apenas o WA-AKG; contêiner em funcionamento não foi substituído..."
docker compose -f "$COMPOSE" build app
echo "[5/6] Validando imagem FINAL antes de reiniciar..."
docker run --rm --network none --entrypoint node wa-akg-app -e '
const fs=require("node:fs");
const pkg=require("/app/node_modules/@whiskeysockets/baileys/package.json");
const code=fs.readFileSync("/app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js","utf8");
if(pkg.version!=="7.0.0-rc.9"||!code.includes("EMECA_RC9_HTTPS_UPLOAD_V2")||
  !code.includes("emecaHttpsUploadWithNode(url, filePath, {"))
  throw Error("Imagem não contém transporte HTTPS V2. Serviço anterior intocado.");
console.log("Imagem validada, Baileys rc.9, transporte HTTPS V2 presente.");
'
sem_envios_ativos
echo "[6/6] Atualizando somente WA-AKG..."
SWAPPED=1
docker compose -f "$COMPOSE" up -d --no-deps app
python3 - <<'PY'
import time,urllib.request,urllib.error
for i in range(24):
    try:
        with urllib.request.urlopen("http://127.0.0.1:3100/",timeout=3) as resp:
            if resp.status<500:
                print("HTTP WA-AKG:",resp.status)
                raise SystemExit(0)
    except urllib.error.HTTPError as e:
        if e.code<500:
            print("HTTP WA-AKG:",e.code)
            raise SystemExit(0)
    except Exception:
        pass
    time.sleep(2)
raise SystemExit("HTTP indisponível após atualização")
PY
SWAPPED=0
echo "Serviço HTTP respondeu. Imagem antiga preservada em $OLD_TAG."
echo "Confirmar CONNECTED antes de testar somente UM PDF pequeno para seu número."
