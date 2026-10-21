#!/usr/bin/env bash
# Atualização controlada do uploader Baileys; NÃO envia mensagens nem toca em
# bancos, sessão WhatsApp, volumes ou outros contêineres.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${WA_AKG_DIR:-$(realpath "$ROOT/../wa-akg")}"
COMPOSE="$ROOT/deploy/wa-akg/compose.secure.yaml"
VERSION="7.0.0-rc14"
MODE="${1:---verificar}"

if [[ "$MODE" != "--verificar" && "$MODE" != "--aplicar" ]]; then
  echo "Uso: bash $0 [--verificar|--aplicar]" >&2
  exit 2
fi
if [[ ! -f "$SRC/package.json" || ! -f "$SRC/package-lock.json" || ! -f "$COMPOSE" ]]; then
  echo "Arquivos do WA-AKG não encontrados; nada foi alterado." >&2
  exit 1
fi

echo "=== Estado atual ==="
docker ps --filter name='^/wa-akg-app$' --format '{{.Names}} {{.Status}}'
docker exec wa-akg-app node -e '
const p=require("/app/node_modules/@whiskeysockets/baileys/package.json");
console.log("Baileys ativo:", p.version, "Node:", process.version);
'
python3 - "$SRC" <<'PY'
import json, pathlib, sys
src=pathlib.Path(sys.argv[1])
p=json.loads((src/"package.json").read_text())
lock=json.loads((src/"package-lock.json").read_text())
print("Baileys no manifesto:",p["dependencies"].get("@whiskeysockets/baileys"))
print("Baileys no lockfile:",lock.get("packages",{}).get("node_modules/@whiskeysockets/baileys",{}).get("version"))
PY

if [[ "$MODE" == "--verificar" ]]; then
  echo "Somente leitura: nenhuma alteração feita."
  exit 0
fi
cd "$ROOT"

sem_envios_ativos() {
  docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n=EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
print("Boletins pendentes/processando:",n)
if n: raise SystemExit("Há boletins ativos. Interrompendo.")
'
  local ativos
  ativos="$(docker exec wa-akg-db sh -c 'mysql -N -s -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' 2>/dev/null | tr -d '[:space:]')"
  if [[ "$ativos" != "0" ]]; then
    echo "Campanhas ativas ou contagem desconhecida: ${ativos:-desconhecido}. Cancelado." >&2
    exit 1
  fi
}

echo "[1/6] Verificando filas e testes sem enviar mídia..."
sem_envios_ativos
python3 -m unittest discover -s "$ROOT/deploy/wa-akg" -p 'test_*.py'

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$SRC/.emeca-backups/baileys-rc14-$STAMP"
mkdir -p -m 700 "$BACKUP"
cp -p "$SRC/package.json" "$SRC/package-lock.json" "$BACKUP/"
OLD_IMAGE="$(docker inspect --format '{{.Image}}' wa-akg-app)"
OLD_TAG="wa-akg-emeca-before-rc14:$STAMP"
docker image tag "$OLD_IMAGE" "$OLD_TAG"
echo "Backup dos manifestos: $BACKUP"
echo "Imagem anterior: $OLD_TAG"

DEPLOY_STARTED=0
restore_on_failed_build() {
  status=$?
  if [[ "$status" != "0" && "$DEPLOY_STARTED" == "0" ]]; then
    cp -p "$BACKUP/package.json" "$SRC/package.json" || true
    cp -p "$BACKUP/package-lock.json" "$SRC/package-lock.json" || true
    echo "Build/validação falhou: manifestos restaurados, contêiner antigo preservado." >&2
  fi
}
trap restore_on_failed_build EXIT

echo "[2/6] Fixando apenas Baileys rc14 no package.json e no lock..."
docker run --rm --user "$(id -u):$(id -g)" \
  -e npm_config_cache=/tmp/.npm \
  -v "$SRC:/workspace" -w /workspace node:26-alpine \
  npm install --save-exact --package-lock-only --ignore-scripts \
  --legacy-peer-deps --no-audit --no-fund "@whiskeysockets/baileys@$VERSION"

python3 - "$SRC" "$VERSION" <<'PY'
import json, pathlib, sys
src,wanted=pathlib.Path(sys.argv[1]),sys.argv[2]
p=json.loads((src/"package.json").read_text())
lock=json.loads((src/"package-lock.json").read_text())
a=p["dependencies"].get("@whiskeysockets/baileys")
b=lock["packages"]["node_modules/@whiskeysockets/baileys"]["version"]
if a!=wanted or b!=wanted: raise SystemExit(f"Dependência/lock divergentes: {a}, {b}")
print("Dependência e lock:",wanted)
PY

echo "[3/6] Build APENAS do WA-AKG (sem substituir contêiner ativo)..."
docker compose -f "$COMPOSE" build app

echo "[4/6] Testando a nova biblioteca na imagem compilada..."
docker run --rm --entrypoint node wa-akg-app -e '
const fs=require("node:fs"),p=require("/app/node_modules/@whiskeysockets/baileys/package.json");
if(p.version!=="7.0.0-rc14")throw Error("Versao Baileys incorreta");
const s=fs.readFileSync("/app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js","utf8");
if(!s.includes("Content-Length")||!s.includes("direct_path"))throw Error("Uploader nao corresponde a rc14");
console.log("Baileys rc14 com Content-Length e direct_path: OK");
'

echo "[5/6] Rechecando filas antes de atualizar..."
sem_envios_ativos
echo "[6/6] Reiniciando SOMENTE o WA-AKG..."
DEPLOY_STARTED=1
docker compose -f "$COMPOSE" up -d --no-deps app
docker exec wa-akg-app node -e '
const p=require("/app/node_modules/@whiskeysockets/baileys/package.json");
if(p.version!=="7.0.0-rc14")process.exit(1);
console.log("Baileys ativo:",p.version);
'
echo "Upgrade concluído. Não houve reenvio automático; volumes preservados."
echo "Aguardar CONNECTED e testar somente UM PDF pequeno para seu próprio número."
echo "Backup de manifests: $BACKUP"
echo "Imagem anterior: $OLD_TAG"
