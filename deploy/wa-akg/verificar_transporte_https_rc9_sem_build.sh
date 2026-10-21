#!/usr/bin/env bash
# Smoke 100% offline do transporte HTTPS portado, sem modificar WA-AKG.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
V1="$ROOT/deploy/wa-akg/patch-baileys-rc9.cjs"
V2="$ROOT/deploy/wa-akg/patch-baileys-rc9-https.cjs"
IMAGE_ID="$(docker inspect -f '{{.Image}}' wa-akg-app)"
echo "=== Testando porta do uploader HTTPS em imagem descartável ==="
docker run --rm --network none --user 0 \
  --mount "type=bind,src=$V1,dst=/tmp/patch-v1.cjs,readonly" \
  --mount "type=bind,src=$V2,dst=/tmp/patch-v2.cjs,readonly" \
  --entrypoint sh "$IMAGE_ID" -ec '
    LIB=/app/node_modules/@whiskeysockets/baileys
    node /tmp/patch-v1.cjs "$LIB"
    node /tmp/patch-v2.cjs "$LIB"
    node --check "$LIB/lib/Utils/messages-media.js"
    node /tmp/patch-v1.cjs "$LIB"
    node /tmp/patch-v2.cjs "$LIB"
    echo "PORTA RC9 HTTPS: PASSOU; idempotente, JS válido, sem rede externa."
  '
echo "Contêiner WA-AKG ativo não foi modificado."
