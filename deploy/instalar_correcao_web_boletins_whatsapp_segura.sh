#!/usr/bin/env bash
# Atualiza SOMENTE o serviço web do EMECA após backup consistente do SQLite
# e testes isolados. Não desconecta, limpa histórico ou reinicia WA-AKG.
set -euo pipefail

cd /srv/projetos/emeca
echo "=== RECUPERAÇÃO SEGURA: EMECA web ==="
for bin in docker git; do command -v "$bin" >/dev/null || { echo "Dependência ausente: $bin"; exit 1; }; done
docker compose config --services | grep -qx "web" || { echo "Serviço web inexistente"; exit 1; }
docker inspect emeca-web-1 >/dev/null || { echo "Contêiner antigo web não encontrado"; exit 1; }
test -f .env || { echo "Arquivo .env não encontrado. Abortando."; exit 1; }

OLD_IMAGE="$(docker inspect -f '{{.Image}}' emeca-web-1)"
WA_IMAGE_ANTES="$(docker inspect -f '{{.Image}}' wa-akg-app 2>/dev/null || true)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_TAG="emeca-web:antes-correcao-$STAMP"
docker tag "$OLD_IMAGE" "$BACKUP_TAG"
echo "Imagem anterior preservada: $BACKUP_TAG"

echo "Gerando backup SQLite online consistente em /srv/backups/emeca..."
docker exec -i emeca-web-1 python manage.py shell -c '
from django.conf import settings
from datetime import datetime, timezone
from pathlib import Path
import os, sqlite3

config = settings.DATABASES["default"]
if "sqlite3" not in config["ENGINE"]:
    raise SystemExit("ABORTADO: banco nao e SQLite. Providencie backup verificado antes de atualizar.")
source = Path(config["NAME"])
if not source.is_file():
    raise SystemExit("ABORTADO: arquivo SQLite nao encontrado.")
target_dir = Path("/backups")
if not target_dir.is_dir():
    raise SystemExit("ABORTADO: volume /backups nao montado. Verifique docker-compose.yml.")
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
target = target_dir / ("emeca-antes-correcoes-whatsapp-boletins-" + stamp + ".sqlite3")
try:
    origem = sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True, timeout=30)
    destino = sqlite3.connect(str(target), timeout=30)
    try:
        os.chmod(target, 0o600)
        origem.backup(destino, pages=1000, sleep=0.05)
        integridade = destino.execute("PRAGMA integrity_check").fetchone()
        if not integridade or integridade[0] != "ok":
            raise RuntimeError("Backup SQLite nao passou na verificacao de integridade.")
    finally:
        destino.close()
        origem.close()
except BaseException:
    if target.exists():
        target.unlink()
    raise
print("BACKUP_OK:", target.name, "bytes:", target.stat().st_size)
'

echo "Construindo somente a imagem do EMECA web..."
docker compose build web
WEB_IMAGE="$(docker compose images -q web)"
test -n "$WEB_IMAGE" || { echo "Imagem web nao disponivel"; exit 1; }

echo "Executando testes de regressao em banco temporario e sem rede..."
docker run --rm --network none --entrypoint python \
    -e DJANGO_DEBUG=1 \
    -e DJANGO_SECRET_KEY=chave-sintetica-exclusiva-para-teste \
    -e DOCUMENT_SIGNING_KEY=assinatura-sintetica-exclusiva-para-teste \
    -e DJANGO_DB_ENGINE=sqlite \
    -e DJANGO_DB_PATH=/tmp/emeca-validacao-segura.sqlite3 \
    -e DJANGO_RBAC_STRICT=0 \
    -e DJANGO_RATE_LIMIT_ENABLED=0 \
    "$WEB_IMAGE" manage.py test \
    site_publico.test_exclusao_boletim_individual \
    usuarioSec.test_recuperacao_whatsapp_producao \
    usuarioSec.test_limpeza_sessao_whatsapp \
    usuarioSec.test_historico_falhas_whatsapp_qa \
    --noinput

echo "Testes passaram. Atualizando apenas o web; worker e WA-AKG preservados."
docker compose up -d --no-deps web
echo "Conferindo Django, sem enviar mensagens ou apagar dados..."
docker exec emeca-web-1 python manage.py check
WA_IMAGE_DEPOIS="$(docker inspect -f '{{.Image}}' wa-akg-app 2>/dev/null || true)"
if [ "$WA_IMAGE_ANTES" != "$WA_IMAGE_DEPOIS" ]; then
    echo "ATENCAO: imagem WA-AKG mudou externamente durante o processo; investigar."
    exit 1
fi
echo "=== INSTALAÇÃO WEB CONCLUÍDA ==="
echo "Backup criado em /srv/backups/emeca; imagem anterior: $BACKUP_TAG"
echo "WA-AKG nao foi recriado nem reiniciado por este script."
echo "Agora execute: python3 deploy/diagnosticar_whatsapp_500_e_boletins.py"
