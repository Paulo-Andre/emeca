#!/usr/bin/env bash
# Atualiza apenas EMECA web. Nenhuma cópia de segurança é criada.
# NUNCA toca WA-AKG, sessão, autenticação, mensagens ou worker de boletins.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" != "--aplicar" ]]; then
  echo "Uso: bash deploy/aplicar_correcao_whatsapp_boletins_sem_backup.sh --aplicar"
  echo "Atualiza só o EMECA Web, após testes sintéticos isolados."
  exit 2
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "CANCELADO: há alterações locais no repositório; não sobrescrever arquivos."
  exit 1
fi

echo "== Compilando exclusivamente a imagem EMECA Web =="
docker compose build web

echo "== Testes com banco SQLite temporário, sem rede =="
docker run --rm --network none --entrypoint python \
  -e DJANGO_DEBUG=1 \
  -e DJANGO_SECRET_KEY=chave-sintetica-so-para-qa-20261023 \
  -e DOCUMENT_SIGNING_KEY=assinatura-sintetica-so-para-qa-20261023 \
  -e DJANGO_ALLOWED_HOSTS=testserver,localhost,127.0.0.1 \
  -e DJANGO_DB_ENGINE=sqlite \
  -e DJANGO_DB_PATH=/tmp/emeca-qa-20261023.sqlite3 \
  -e DJANGO_RBAC_STRICT=0 \
  -e DJANGO_RATE_LIMIT_ENABLED=0 \
  emeca-web manage.py test \
  site_publico.test_exclusao_boletim_individual \
  site_publico.test_boletim_faltas_logo \
  usuarioSec.test_painel_whatsapp_pendente \
  usuarioSec.test_limpeza_sessao_whatsapp \
  usuarioSec.test_historico_falhas_whatsapp_qa \
  --noinput

echo "== Testes aprovados. Atualizando apenas web =="
docker compose up -d --no-deps web
docker compose ps web
echo "Conclusão: apenas EMECA Web atualizado. WA-AKG e worker preservados."
echo "Consulte /whatsapp/ e /boletins/3/; não inicie nova limpeza nem exclusões de teste."
