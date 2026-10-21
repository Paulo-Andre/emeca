#!/usr/bin/env bash
# Diagnóstico TEMPORÁRIO da rejeição HTTP 400, sem rebuild do WA-AKG.
# Nunca imprime corpo HTTP, token, URL, JID, PDF ou chave de API.
# --verificar (padrão): somente prepara/testa uma cópia.
# --aplicar: instala em contêiner atual, reinicia somente WA-AKG.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${WA_AKG_DIR:-/srv/projetos/wa-akg}"
MODE="${1:---verificar}"
TARGET="/app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js"
PKG="/app/node_modules/@whiskeysockets/baileys/package.json"
PATCH="$ROOT/deploy/wa-akg/patch-resposta-400.cjs"
cd "$ROOT"
if [[ "$MODE" != "--verificar" && "$MODE" != "--aplicar" ]]; then
  echo "Uso: bash $0 [--verificar|--aplicar]" >&2; exit 2
fi
if [[ "$(docker inspect -f '{{.State.Running}}' wa-akg-app)" != "true" ]]; then
  echo "WA-AKG não está em execução. Sem alterações." >&2; exit 1
fi
docker exec wa-akg-app node -e '
const fs=require("node:fs");
const pkg=require("/app/node_modules/@whiskeysockets/baileys/package.json");
const code=fs.readFileSync("/app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js","utf8");
if(pkg.version!=="7.0.0-rc.9"){
  throw Error("Versão Baileys diferente de rc.9; nenhuma alteração.");
}
const v2=code.includes("EMECA_RC9_HTTPS_UPLOAD_V2");
const v1=code.includes("EMECA_BAILEYS_RC9_UPLOAD_V1");
if(!v2&&!v1){
  throw Error("Uploader sem instrumentação reconhecida V1/V2; nenhuma alteração.");
}
console.log("Baileys rc.9. Transporte em uso:",v2?"HTTPS V2":"fetch V1");
console.log("Código existente preservado até a validação da cópia.");
'

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$SRC/.emeca-backups/rejeicao-http-400-$STAMP"
mkdir -p -m 700 "$BACKUP"
chmod 700 "$BACKUP"
docker cp "wa-akg-app:$TARGET" "$BACKUP/original.js"
docker cp "wa-akg-app:$PKG" "$BACKUP/package.json"
echo "Biblioteca original preservada em: $BACKUP/original.js"

WORK="/tmp/emeca-http-400-$STAMP"
docker exec -u 0 wa-akg-app mkdir -p "$WORK/lib/Utils"
docker cp "$BACKUP/original.js" "wa-akg-app:$WORK/lib/Utils/messages-media.js"
docker cp "$BACKUP/package.json" "wa-akg-app:$WORK/package.json"
docker cp "$PATCH" "wa-akg-app:$WORK/patch.cjs"
docker exec -u 0 wa-akg-app node "$WORK/patch.cjs" "$WORK"
docker exec -u 0 wa-akg-app node --check "$WORK/lib/Utils/messages-media.js"
docker exec -u 0 wa-akg-app node -e 'const fs=require("node:fs");const code=fs.readFileSync(process.argv[1],"utf8");if(!code.includes("WA-MEDIA-REJECTION-DIAG-V1")) process.exit(2);console.log("Diagnóstico sanitizado verificado na cópia.");' "$WORK/lib/Utils/messages-media.js"
docker exec -u 0 wa-akg-app node "$WORK/patch.cjs" "$WORK"
docker cp "wa-akg-app:$WORK/lib/Utils/messages-media.js" "$BACKUP/verificado.js"
echo "Diagnóstico verificado numa cópia. Nenhum PDF enviado."

if [[ "$MODE" == "--verificar" ]]; then
  echo "SEM REINÍCIO. Para instalar: bash deploy/wa-akg/diagnosticar_rejeicao_400_sem_build.sh --aplicar"
  exit 0
fi

echo "Verificando se há boletins ou campanhas em andamento..."
docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n=EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
print("Boletins ativos:",n)
if n: raise SystemExit("Boletins em processamento. Cancelado.")
'
ATIVOS="$(docker exec wa-akg-db sh -c 'mysql -N -s -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' 2>/dev/null | tr -d '[:space:]')"
if [[ "$ATIVOS" != "0" ]]; then
  echo "Campanhas ativas ou verificação inconclusiva. Abortado." >&2; exit 1
fi

INSTALLED=0
rollback_on_failure() {
  local status=$?
  if [[ "$status" -ne 0 && "$INSTALLED" -eq 1 ]]; then
    echo "Falha na reinicialização: restaurando biblioteca original..." >&2
    docker cp "$BACKUP/original.js" "wa-akg-app:$TARGET" || true
    docker restart wa-akg-app || true
    echo "Biblioteca anterior reposta. Verificar status CONNECTED." >&2
  fi
}
trap rollback_on_failure EXIT

echo "Instalando diagnóstico apenas no contêiner existente..."
docker cp "$BACKUP/verificado.js" "wa-akg-app:$TARGET"
INSTALLED=1
docker restart wa-akg-app >/dev/null
echo "Verificando resposta HTTP local do WA-AKG..."
python3 - <<'PY'
import time, urllib.request, urllib.error
for _ in range(18):
    try:
        with urllib.request.urlopen("http://127.0.0.1:3100/",timeout=3) as r:
            if r.status < 500:
                print("WA-AKG respondeu HTTP",r.status)
                raise SystemExit(0)
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            print("WA-AKG respondeu HTTP",exc.code)
            raise SystemExit(0)
    except Exception: pass
    time.sleep(2)
raise SystemExit("WA-AKG não respondeu após reinício")
PY
docker exec wa-akg-app node -e '
const fs=require("node:fs");
const t=fs.readFileSync("/app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js","utf8");
if(!t.includes("WA-MEDIA-REJECTION-DIAG-V1")) process.exit(1);
console.log("Classificação sanitizada de HTTP 400: INSTALADA");
'
INSTALLED=0
echo "Instalação temporária concluída. Não apaga sessão, mensagens ou banco."
echo "Apenas após CONNECTED, realizar UM teste para o próprio número."
echo "A alteração temporária não sobrevive à recriação da imagem Docker."
echo "Original disponível em $BACKUP/original.js"
