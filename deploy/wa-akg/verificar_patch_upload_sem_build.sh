#!/usr/bin/env bash
# Testa patch Baileys rc.9 dentro de contêiner DESCARTÁVEL, sem rebuild,
# internet, sessões, montagens de banco ou alteração no WA-AKG ativo.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PATCH="$ROOT/deploy/wa-akg/patch-baileys-rc9.cjs"
if [[ ! -r "$PATCH" ]]; then echo "Patch não encontrado" >&2; exit 1; fi
echo "=== Contêiner ativo (somente leitura) ==="
docker ps --filter name='^/wa-akg-app$' --format '{{.Names}} {{.Status}}'
echo "=== Simulação em contêiner descartável da imagem ativa ==="
IMAGE_ID="$(docker inspect -f '{{.Image}}' wa-akg-app)"
docker run --rm --network none \
  --mount "type=bind,src=$PATCH,dst=/tmp/patch-baileys-rc9.cjs,readonly" \
  --entrypoint sh "$IMAGE_ID" -ec '
    echo "Baileys na imagem:"
    node -p "require(\"/app/node_modules/@whiskeysockets/baileys/package.json\").version"
    node /tmp/patch-baileys-rc9.cjs /app/node_modules/@whiskeysockets/baileys
    node --check /app/node_modules/@whiskeysockets/baileys/lib/Utils/messages-media.js
    node /tmp/patch-baileys-rc9.cjs /app/node_modules/@whiskeysockets/baileys
    echo "SUCESSO: patch aplicou em biblioteca real, JS válido, idempotente."
  '
echo "Fim. O WA-AKG em execução NÃO foi tocado."
