#!/usr/bin/env bash
set -euo pipefail

OLD_DIR="${1:-/srv/projetos/historico_egidio}"
NEW_DIR="${2:-/srv/projetos/emeca}"

fail() {
  echo "ERRO: $*" >&2
  exit 1
}

[ -d "$OLD_DIR" ] || fail "Projeto legado não encontrado em $OLD_DIR"
[ -d "$NEW_DIR" ] || fail "Projeto unificado não encontrado em $NEW_DIR"

OLD_H="$OLD_DIR/historico"
NEW_H="$NEW_DIR/historico"

for file in   "$OLD_H/templates/historico/base.html"   "$OLD_H/templates/historico/historico.html"   "$OLD_H/static/historico/css/app.css"   "$OLD_H/static/historico/css/document.css"   "$OLD_H/static/historico/js/historico-editor.js"
do
  [ -f "$file" ] || fail "Arquivo legado ausente: $file"
done

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$NEW_DIR/.backup-historico-impressao-$STAMP"
mkdir -p "$BACKUP/templates" "$BACKUP/css" "$BACKUP/js" "$BACKUP/img"

echo "1/6 - Fazendo backup do estado atual em $BACKUP"
cp -a "$NEW_H/templates/historico/document_base.html" "$BACKUP/templates/" 2>/dev/null || true
cp -a "$NEW_H/templates/historico/historico.html" "$BACKUP/templates/" 2>/dev/null || true
cp -a "$NEW_H/static/historico/css/app.css" "$BACKUP/css/" 2>/dev/null || true
cp -a "$NEW_H/static/historico/css/document.css" "$BACKUP/css/" 2>/dev/null || true
cp -a "$NEW_H/static/historico/js/historico-editor.js" "$BACKUP/js/" 2>/dev/null || true
cp -a "$NEW_H/static/historico/img/timbragem_historico_egidio."* "$BACKUP/img/" 2>/dev/null || true

echo "2/6 - Copiando exatamente os arquivos do Histórico que funcionava antes da junção"
cp -f "$OLD_H/templates/historico/base.html" "$NEW_H/templates/historico/document_base.html"
cp -f "$OLD_H/templates/historico/historico.html" "$NEW_H/templates/historico/historico.html"
cp -f "$OLD_H/static/historico/css/app.css" "$NEW_H/static/historico/css/app.css"
cp -f "$OLD_H/static/historico/css/document.css" "$NEW_H/static/historico/css/document.css"
cp -f "$OLD_H/static/historico/js/historico-editor.js" "$NEW_H/static/historico/js/historico-editor.js"

# Só troca a base herdada para não substituir a interface unificada das demais telas.
python3 - "$NEW_H/templates/historico/historico.html" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
old = "{% extends 'historico/base.html' %}"
new = "{% extends 'historico/document_base.html' %}"
if old not in s:
    raise SystemExit("ERRO: não encontrei a extensão da base no historico.html legado")
p.write_text(s.replace(old, new, 1), encoding="utf-8")
PY

echo "3/6 - Restaurando a timbragem real usada pelo projeto legado"
mkdir -p "$NEW_H/static/historico/img"
if [ -f "$OLD_H/static/historico/img/timbragem_historico_egidio.jpeg" ]; then
  cp -f "$OLD_H/static/historico/img/timbragem_historico_egidio.jpeg"         "$NEW_H/static/historico/img/timbragem_historico_egidio.jpeg"
elif [ -f "$OLD_H/static/historico/img/timbragem_historico_egidio.jpg" ]; then
  cp -f "$OLD_H/static/historico/img/timbragem_historico_egidio.jpg"         "$NEW_H/static/historico/img/timbragem_historico_egidio.jpeg"
elif [ -f "$OLD_H/static/historico/img/timbragem_historico_egidio.b64" ]; then
  cp -f "$OLD_H/static/historico/img/timbragem_historico_egidio.b64"         "$NEW_H/static/historico/img/timbragem_historico_egidio.b64"
  python3 - "$OLD_H/static/historico/img/timbragem_historico_egidio.b64"              "$NEW_H/static/historico/img/timbragem_historico_egidio.jpeg" <<'PY'
from pathlib import Path
import base64, sys
src, dst = map(Path, sys.argv[1:3])
payload = "".join(src.read_text(encoding="ascii").split())
dst.write_bytes(base64.b64decode(payload, validate=True))
PY
else
  fail "Nem JPEG/JPG nem B64 da timbragem foram encontrados no projeto legado"
fi

# Mantém também o fallback b64 quando existir.
if [ -f "$OLD_H/static/historico/img/timbragem_historico_egidio.b64" ]; then
  cp -f "$OLD_H/static/historico/img/timbragem_historico_egidio.b64"         "$NEW_H/static/historico/img/timbragem_historico_egidio.b64"
fi

echo "4/6 - Limpando arquivos estáticos antigos e reconstruindo sem cache"
cd "$NEW_DIR"
docker compose down
docker image rm emeca-web >/dev/null 2>&1 || true
docker compose build --no-cache

echo "5/6 - Subindo o EMECA"
docker compose up -d

echo "6/6 - Conferindo os arquivos que estão realmente dentro do container"
docker compose exec -T web sh -lc '
set -e
echo "--- TIMBRAGEM ---"
ls -lh /app/historico/static/historico/img/timbragem_historico_egidio.jpeg
ls -lh /app/staticfiles/historico/img/timbragem_historico_egidio.jpeg
echo "--- CSS ---"
sha256sum /app/historico/static/historico/css/document.css
sha256sum /app/staticfiles/historico/css/document.css
echo "--- JS ---"
sha256sum /app/historico/static/historico/js/historico-editor.js
sha256sum /app/staticfiles/historico/js/historico-editor.js
'

echo
echo "Restauração local concluída."
echo "Backup: $BACKUP"
echo
echo "IMPORTANTE: teste a impressão agora antes de executar outro git pull."
echo "Se funcionar, este estado local é a referência correta para sincronizar com o GitHub."
