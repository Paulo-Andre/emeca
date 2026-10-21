#!/usr/bin/env bash
# Correção cirúrgica do upload PDF no Baileys 7.0.0-rc.9.
# NÃO atualiza Baileys/Node, não toca em banco/volumes/sessão e não envia arquivos.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${WA_AKG_DIR:-/srv/projetos/wa-akg}"
COMPOSE="$ROOT/deploy/wa-akg/compose.secure.yaml"
MODE="${1:---verificar}"
cd "$ROOT"

if [[ "$MODE" != "--verificar" && "$MODE" != "--aplicar" ]]; then
  echo "Uso: bash $0 [--verificar|--aplicar]" >&2
  exit 2
fi

echo "=== Verificando versão atualmente conectada ==="
docker exec wa-akg-app node -e '
const p = require("/app/node_modules/@whiskeysockets/baileys/package.json");
console.log("Baileys:",p.version);
if(p.version!=="7.0.0-rc.9")process.exit(1);
'
echo "=== Executando testes sintéticos sem WhatsApp ==="
python3 -m unittest discover -s deploy/wa-akg -p 'test_patch_upload_rc9.py' -v

echo "=== Conferindo patch e Dockerfile sem alteração ==="
python3 deploy/wa-akg/preparar_fix_upload_rc9.py --source "$SRC" --dry-run
if [[ "$MODE" == "--verificar" ]]; then
  echo "Pré-verificação concluída. Nenhuma alteração no servidor."
  echo "Para aplicar: bash deploy/wa-akg/corrigir_upload_pdf_rc9.sh --aplicar"
  exit 0
fi

sem_envios_ativos() {
  docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n = EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
print("Boletins pendentes/processando:", n)
if n: raise SystemExit("Há boletins ativos. Não reiniciar WA-AKG.")
'
  local ativos
  ativos="$(docker exec wa-akg-db sh -c 'mysql -N -s -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' 2>/dev/null | tr -d '[:space:]')"
  if [[ "$ativos" != "0" ]]; then
    echo "Envios WA-AKG ativos ou consulta inconclusiva. Abortando." >&2
    exit 1
  fi
}

echo "=== Confirmando que não há envios em andamento ==="
sem_envios_ativos
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OLD_IMAGE="$(docker inspect --format '{{.Image}}' wa-akg-app)"
OLD_TAG="wa-akg-emeca-pre-fix-upload-rc9:$STAMP"
docker image tag "$OLD_IMAGE" "$OLD_TAG"
echo "Imagem original preservada em $OLD_TAG"

SWAPPED=0
# Preservar Dockerfile exatamente como estava antes da tentativa.
DOCKERFILE_BACKUP="$(mktemp)"
cp -p "$SRC/Dockerfile" "$DOCKERFILE_BACKUP"
rollback_on_failure() {
  code=$?
  if [[ "$code" -ne 0 ]]; then
    cp -p "$DOCKERFILE_BACKUP" "$SRC/Dockerfile" || true
    echo "Dockerfile anterior restaurado após falha." >&2
  fi
  rm -f "$DOCKERFILE_BACKUP"
  if [[ "$code" -ne 0 && "$SWAPPED" -eq 1 ]]; then
    echo "Falha após início da atualização: recuperando a imagem antiga." >&2
    docker image tag "$OLD_TAG" wa-akg-app:latest || true
    docker compose -f "$COMPOSE" up -d --no-deps --force-recreate app || true
    echo "O banco/volumes não foram alterados. Verifique CONNECTED." >&2
  fi
}
trap rollback_on_failure EXIT

echo "=== Aplicando patch somente no código local de build ==="
python3 deploy/wa-akg/preparar_fix_upload_rc9.py --source "$SRC"

echo "=== Compilando somente o WA-AKG; serviço antigo continua funcionando ==="
docker compose -f "$COMPOSE" build app

echo "=== Verificando a imagem NOVA antes de reiniciar ==="
docker run --rm --network none --entrypoint node wa-akg-app -e '
const fs=require("node:fs");
const ver=require("/app/node_modules/@whiskeysockets/baileys/package.json").version;
const file="/app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js";
const text=fs.readFileSync(file,"utf8");
if(ver!=="7.0.0-rc.9" ||
   !text.includes("EMECA_BAILEYS_RC9_UPLOAD_V1") ||
   !text.includes("Content-Length") ||
   !text.includes("WA-MEDIA-HTTP-DIAG")){
   throw new Error("Biblioteca ou patch no container não passaram pela validação");
}
console.log("Baileys rc.9 corrigido na imagem, sem mudar versão: OK");
'

echo "=== Segunda verificação de filas antes de reiniciar ==="
sem_envios_ativos
SWAPPED=1
docker compose -f "$COMPOSE" up -d --no-deps app

echo "=== Verificando retorno do serviço HTTP ==="
python3 - <<'PY'
import time
import urllib.error
import urllib.request
url="http://127.0.0.1:3100/"
for attempt in range(24):
    try:
        with urllib.request.urlopen(url,timeout=3) as response:
            if response.status < 500:
                print("WA-AKG disponível: HTTP",response.status)
                raise SystemExit(0)
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            print("WA-AKG disponível: HTTP",exc.code)
            raise SystemExit(0)
    except Exception:
        pass
    time.sleep(2)
raise SystemExit("WA-AKG não iniciou; reverter automaticamente")
PY

docker exec wa-akg-app node -e '
const fs=require("node:fs");
const v=require("/app/node_modules/@whiskeysockets/baileys/package.json").version;
const t=fs.readFileSync("/app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js","utf8");
if(v!=="7.0.0-rc.9"||!t.includes("EMECA_BAILEYS_RC9_UPLOAD_V1"))process.exit(1);
console.log("Baileys ativo:",v,"patch de upload: SIM");
'
SWAPPED=0
echo "Correção aplicada. Não houve reenvio automático nem limpeza de dados."
echo "Aguarde WhatsApp CONNECTED. Envie somente UM PDF pequeno para o PRÓPRIO número."
echo "Se falhar, colete apenas WA-MEDIA-HTTP-DIAG + WA-MEDIA-UPLOAD-DIAG."
echo "Imagem anterior mantida: $OLD_TAG"
