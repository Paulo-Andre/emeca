#!/usr/bin/env bash
# Instala a cópia HTTPS V2 já validada sem recompilar nem recriar contêiner.
# --verificar (padrão): somente leitura; --aplicar: preflight e implantação.
set -euo pipefail
MODE="${1:---verificar}"
[[ "$MODE" == "--verificar" || "$MODE" == "--aplicar" ]] || { echo "Uso: bash $0 [--verificar|--aplicar]" >&2; exit 2; }
APP=wa-akg-app
SOURCE="/srv/projetos/wa-akg/.emeca-backups/https-v2-in-place-20261021T203806Z"
ORIGINAL="$SOURCE/original.js"
VERIFIED="$SOURCE/verificado.js"
TARGET="/app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SAVE="/srv/projetos/wa-akg/.emeca-backups/https-v2-ativacao-$STAMP"

echo "=== Verificando cópia HTTPS V2 ==="
for F in "$ORIGINAL" "$VERIFIED"; do
  [[ -s "$F" ]] || { echo "Arquivo original ou V2 indisponível: $F" >&2; exit 1; }
done
grep -Fq "EMECA_RC9_HTTPS_UPLOAD_V2" "$VERIFIED" || { echo "Arquivo não contém V2" >&2; exit 1; }
grep -Fq "text: async () => responseBody" "$VERIFIED" || { echo "V2 sem compatibilidade com diagnóstico" >&2; exit 1; }
grep -Fq "WA-MEDIA-REJECTION-DIAG-V1" "$VERIFIED" || { echo "Cópia sem diagnóstico esperado" >&2; exit 1; }
if grep -Fq "const response = await fetch(url, {" "$VERIFIED"; then
  echo "Upload fetch ainda presente na cópia; abortado" >&2; exit 1
fi
[[ "$(docker inspect -f '{{.State.Running}}' "$APP")" == "true" ]] || { echo "WA-AKG não está rodando" >&2; exit 1; }
docker exec "$APP" node -e '
const fs=require("node:fs");
const base="/app/node_modules/@whiskeysockets/baileys";
const code=fs.readFileSync(base+"/lib/Utils/messages-media.js","utf8");
if(require(base+"/package.json").version!=="7.0.0-rc.9"
 || !code.includes("EMECA_BAILEYS_RC9_UPLOAD_V1")
 || code.includes("EMECA_RC9_HTTPS_UPLOAD_V2"))
 throw Error("Código ativo não corresponde à V1 esperada; nenhuma alteração.");
console.log("Baileys V1 atual confirmado.");
'
mkdir -p -m 700 "$SAVE"
chmod 700 "$SAVE"
docker cp "$APP:$TARGET" "$SAVE/antes-da-troca.js"
cmp -s "$SAVE/antes-da-troca.js" "$ORIGINAL" || {
  echo "O módulo ativo mudou em relação ao backup V1. Não substituir." >&2; exit 1;
}
echo "Backup ativo: $SAVE/antes-da-troca.js"
echo "Cópia HTTPS V2 compatível com o código ativo."
if [[ "$MODE" == "--verificar" ]]; then
  echo "CONCLUÍDO sem reiniciar, sem trocar arquivo e sem enviar mensagem."
  echo "Ativação: bash deploy/wa-akg/ativar_https_v2_validada.sh --aplicar"
  exit 0
fi

echo "=== Verificando filas com docker exec direto (sem Docker Compose) ==="
echo "[1/2] Boletins EMECA..."
if ! timeout -k 3s 20s docker exec emeca-web-1 python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n=EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
print("Boletins ativos:",n)
if n: raise SystemExit("Boletins em andamento. Abortado.")
'; then
  echo "Verificação EMECA falhou ou identificou fila ativa. NENHUMA troca feita." >&2
  exit 1
fi

echo "[2/2] Campanhas WA-AKG..."
if ! N="$(timeout -k 3s 20s docker exec wa-akg-db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -s -uroot "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' 2>/dev/null)"; then
  echo "Verificação MySQL falhou. NENHUMA troca feita." >&2; exit 1
fi
N="$(printf '%s' "$N" | tr -d '[:space:]')"
echo "Campanhas ativas: $N"
[[ "$N" == "0" ]] || { echo "Campanhas ativas ou resposta inconclusiva. Cancelado." >&2; exit 1; }

CHANGED=0
rollback() {
  STATUS=$?
  if [[ "$STATUS" -ne 0 && "$CHANGED" == "1" ]]; then
    echo "Falha após início da troca: restaurando V1..." >&2
    docker stop --time 15 "$APP" >/dev/null || true
    docker cp "$SAVE/antes-da-troca.js" "$APP:$TARGET" || true
    docker start "$APP" >/dev/null || true
    echo "Restauração solicitada. Verifique status CONNECTED." >&2
  fi
}
trap rollback EXIT

echo "=== Parando apenas o WA-AKG para instalar V2 ==="
CHANGED=1
docker stop --time 20 "$APP" >/dev/null
docker cp "$VERIFIED" "$APP:$TARGET"
docker start "$APP" >/dev/null

echo "=== Validando resposta do WA-AKG ==="
python3 - <<'PY'
import time,urllib.request,urllib.error
for _ in range(20):
    try:
        with urllib.request.urlopen("http://127.0.0.1:3100/",timeout=3) as r:
            if r.status<500:
                print("HTTP WA-AKG:",r.status)
                raise SystemExit(0)
    except urllib.error.HTTPError as ex:
        if ex.code<500:
            print("HTTP WA-AKG:",ex.code)
            raise SystemExit(0)
    except Exception:
        pass
    time.sleep(2)
raise SystemExit("WA-AKG não respondeu; executar rollback.")
PY

docker exec "$APP" node -e '
const fs=require("node:fs");
const p="/app/node_modules/@whiskeysockets/baileys";
const s=fs.readFileSync(p+"/lib/Utils/messages-media.js","utf8");
if(!s.includes("EMECA_RC9_HTTPS_UPLOAD_V2")
  || !s.includes("emecaHttpsUploadWithNode(url, filePath, {")
  || !s.includes("WA-MEDIA-REJECTION-DIAG-V1"))
 throw Error("V2 ausente ou diagnóstico inconsistente após reinício");
console.log("TRANSPORTE HTTPS V2: ATIVO");
'
CHANGED=0
echo "V2 ativada, sem build e sem recriar contêiner/volumes."
echo "Confirme WhatsApp CONNECTED antes de enviar apenas um PDF pequeno."
echo "Esta alteração é temporária: recriar o contêiner restaura código da imagem."
