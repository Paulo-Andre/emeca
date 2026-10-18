#!/usr/bin/env bash
# Ponto de entrada legado. NÃO reinicia containers automaticamente.
# O script protegido exige backups de EMECA + WA-AKG antes do deploy.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$ROOT/deploy/atualizar_lote_seguro.sh" "$@"
