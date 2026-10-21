#!/usr/bin/env bash
# Implantar HTTPS V2 SOMENTE no arquivo Baileys do contêiner WA-AKG existente.
# Sem build, sem npm, sem Docker Compose up e sem recriar contêiner/volumes.
# Verificação padrão: trabalha apenas numa cópia em /tmp do mesmo contêiner.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="${1:---verificar}"
[[ "$MODE" == "--verificar" || "$MODE" == "--aplicar" ]] || {
  echo "Uso: bash $0 [--verificar|--aplicar]" >&2; exit 2;
}
cd "$ROOT"
APP="wa-akg-app"
BASE="/app/node_modules/@whiskeysockets/baileys"
TARGET="$BASE/lib/Utils/messages-media.js"
SRC="${WA_AKG_DIR:-/srv/projetos/wa-akg}"
PATCH="$ROOT/deploy/wa-akg/patch-baileys-rc9-https.cjs"

[[ -r "$PATCH" ]] || { echo "Patch HTTPS V2 não localizado" >&2; exit 1; }
[[ "$(docker inspect -f '{{.State.Running}}' "$APP")" == "true" ]] || {
  echo "WA-AKG não está em execução; nada foi alterado" >&2; exit 1;
}

echo "=== Biblioteca em execução ==="
docker exec "$APP" node -e '
const fs=require("node:fs");
const dir="/app/node_modules/@whiskeysockets/baileys";
const v=require(dir+"/package.json").version;
const s=fs.readFileSync(dir+"/lib/Utils/messages-media.js","utf8");
console.log("Baileys:",v);
console.log("V1:",s.includes("EMECA_BAILEYS_RC9_UPLOAD_V1"));
console.log("V2:",s.includes("EMECA_RC9_HTTPS_UPLOAD_V2"));
console.log("Diagnóstico 400:",s.includes("WA-MEDIA-REJECTION-DIAG-V1"));
if(v!=="7.0.0-rc.9" || !s.includes("EMECA_BAILEYS_RC9_UPLOAD_V1"))
  throw Error("Biblioteca incompatível. Sem alterações.");
if(s.includes("EMECA_RC9_HTTPS_UPLOAD_V2"))
  throw Error("V2 já encontrada no contêiner. Evitar implantação duplicada.");
'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$SRC/.emeca-backups/https-v2-in-place-$STAMP"
mkdir -p -m 700 "$BACKUP"
chmod 700 "$BACKUP"
docker cp "$APP:$TARGET" "$BACKUP/original.js"
docker cp "$APP:$BASE/package.json" "$BACKUP/package.json"
echo "Original preservado em: $BACKUP/original.js"

# Executar tudo num diretório separado; o módulo real não é tocado.
TMP="/tmp/emeca-https-v2-$STAMP"
docker exec -u 0 "$APP" mkdir -p "$TMP/lib/Utils"
docker cp "$BACKUP/original.js" "$APP:$TMP/lib/Utils/messages-media.js"
docker cp "$BACKUP/package.json" "$APP:$TMP/package.json"
docker cp "$PATCH" "$APP:$TMP/patch.cjs"
docker exec -u 0 "$APP" node "$TMP/patch.cjs" "$TMP"
docker exec -u 0 "$APP" node --check "$TMP/lib/Utils/messages-media.js"
docker exec -u 0 "$APP" node "$TMP/patch.cjs" "$TMP"
docker exec -u 0 "$APP" node -e '
const fs=require("node:fs");
const s=fs.readFileSync(process.argv[1],"utf8");
const must=[
"EMECA_BAILEYS_RC9_UPLOAD_V1",
"EMECA_RC9_HTTPS_UPLOAD_V2",
"emecaHttpsUploadWithNode(url, filePath, {",
"text: async () => responseBody",
];
if(must.some(x=>!s.includes(x))) throw Error("Cópia não possui o código V1/V2 completo");
if(s.includes("const response = await fetch(url, {")) throw Error("Cópia ainda contém fetch no uploader");
console.log("Cópia V2 válida: HTTPS nativo com compatibilidade de diagnóstico.");
' "$TMP/lib/Utils/messages-media.js"
docker cp "$APP:$TMP/lib/Utils/messages-media.js" "$BACKUP/verificado.js"
echo "=== Verificação completa numa cópia, sem alterar WA-AKG ==="

if [[ "$MODE" == "--verificar" ]]; then
  echo "Modo verificar: contêiner NÃO reiniciado e código ativo NÃO alterado."
  echo "Para implantar: bash deploy/wa-akg/ativar_https_v2_sem_build.sh --aplicar"
  exit 0
fi

echo "=== Conferindo ausência de envios em andamento antes do reinício ==="
echo "[FILAS 1/2] Consultando boletins do EMECA (limite de 30s)..."
if ! timeout -k 5s 30s docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n=EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
print("Boletins pendentes/processando:",n)
if n: raise SystemExit("Existem boletins ativos: intervenção cancelada")
'; then
  echo "ERRO: consulta EMECA falhou ou excedeu limite; WA-AKG não foi reiniciado." >&2
  exit 1
fi
echo "[FILAS 1/2] EMECA: OK."
echo "[FILAS 2/2] Consultando campanhas WA-AKG (limite de 25s)..."
if ! N="$(timeout -k 5s 25s docker exec wa-akg-db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -s -uroot "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' 2>/dev/null)"; then
  echo "ERRO: consulta WA-AKG falhou ou excedeu limite; WA-AKG não foi reiniciado." >&2
  exit 1
fi
N="$(printf '%s' "$N" | tr -d '[:space:]')"
echo "Campanhas WA-AKG em execução: $N"
if [[ "$N" != "0" ]]; then
  echo "Campanhas WA-AKG ativas ou resposta inconclusiva; WA-AKG não foi reiniciado." >&2
  exit 1
fi
echo "[FILAS 2/2] WA-AKG: OK. Não existem filas ativas nesses dois sistemas."

docker image tag "$(docker inspect -f '{{.Image}}' "$APP")" "wa-akg-pre-https-v2:$STAMP"

SWITCHED=0
restore_if_failure() {
  STATUS=$?
  if [[ "$STATUS" -ne 0 && "$SWITCHED" == "1" ]]; then
    echo "Falha após início da troca. Restaurando arquivo anterior..." >&2
    docker stop --time 20 "$APP" >/dev/null || true
    docker cp "$BACKUP/original.js" "$APP:$TARGET" || true
    docker start "$APP" >/dev/null || true
    echo "Arquivo original restaurado; confira WhatsApp CONNECTED." >&2
  fi
}
trap restore_if_failure EXIT

echo "=== Parada controlada apenas do WA-AKG, com volumes e banco preservados ==="
SWITCHED=1
docker stop --time 30 "$APP" >/dev/null
docker cp "$BACKUP/verificado.js" "$APP:$TARGET"
docker start "$APP" >/dev/null

echo "=== Testando início do WA-AKG ==="
python3 - <<'PY'
import time, urllib.request, urllib.error
for _ in range(24):
    try:
        with urllib.request.urlopen("http://127.0.0.1:3100/", timeout=3) as response:
            if response.status < 500:
                print("HTTP restaurado:",response.status)
                raise SystemExit(0)
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            print("HTTP restaurado:",exc.code)
            raise SystemExit(0)
    except Exception:
        pass
    time.sleep(2)
raise SystemExit("WA-AKG indisponível após ativação V2")
PY

docker exec "$APP" node -e '
const fs=require("node:fs");
const p="/app/node_modules/@whiskeysockets/baileys";
const s=fs.readFileSync(p+"/lib/Utils/messages-media.js","utf8");
if(require(p+"/package.json").version!=="7.0.0-rc.9"
  || !s.includes("EMECA_RC9_HTTPS_UPLOAD_V2")
  || !s.includes("emecaHttpsUploadWithNode(url, filePath, {"))
 throw Error("V2 não encontrada no contêiner após reinício");
console.log("TRANSPORTE HTTPS V2: ATIVO no contêiner reiniciado");
console.log("Diagnóstico HTTP 400:",s.includes("WA-MEDIA-REJECTION-DIAG-V1"));
'
SWITCHED=0
echo "CONCLUÍDO. Sem build e sem alteração de imagens, banco, volumes ou sessão."
echo "Confirme CONNECTED na página; teste no máximo um PDF pequeno enviado a você."
echo "Cópia original: $BACKUP/original.js"
echo "ATENÇÃO: patch in-place é temporário; será perdido se o contêiner for recriado."
