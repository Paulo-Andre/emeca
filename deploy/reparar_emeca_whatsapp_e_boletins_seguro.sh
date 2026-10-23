#!/usr/bin/env bash
# Reparo conservador do EMECA (somente web + reposição seletiva de boletins).
# Não toca wa-akg-app, wa-akg-db, credenciais ou sessão WhatsApp.
set -euo pipefail
cd /srv/projetos/emeca

erro() {
  echo ""
  echo "REPARO INTERROMPIDO. Nenhum comando de limpeza WhatsApp foi executado."
  echo "Se o erro ocorreu na reposição, o banco atual permanece íntegro ou a transação foi revertida."
}
trap erro ERR

echo "== 1/5: confirmar integridade do repositório =="
git diff --quiet
git diff --cached --quiet
echo "== 2/5: compilar somente EMECA Web =="
docker compose build web

echo "== 3/5: testes isolados, sem banco e sem rede de produção =="
img="$(docker compose images -q web | head -n 1)"
if [[ -z "$img" ]]; then
  echo "Imagem web do EMECA não encontrada."
  exit 1
fi

docker run --rm --network none --entrypoint python \
  -e DJANGO_DEBUG=1 \
  -e DJANGO_SECRET_KEY=chave-sintetica-so-para-teste-emeca-2026 \
  -e DOCUMENT_SIGNING_KEY=assinatura-sintetica-so-para-teste-emeca-2026 \
  -e DJANGO_DB_ENGINE=sqlite \
  -e DJANGO_DB_PATH=/tmp/emeca-testes-reparo.sqlite3 \
  -e DJANGO_ALLOWED_HOSTS=localhost,testserver \
  -e DJANGO_RBAC_STRICT=0 \
  -e DJANGO_RATE_LIMIT_ENABLED=0 \
  "$img" manage.py test \
  usuarioSec.test_painel_whatsapp_pendente \
  site_publico.test_recuperacao_boletins_ausentes \
  site_publico.test_exclusao_boletim_individual --noinput

echo "== 4/5: substituir somente o contêiner web do EMECA =="
docker compose up -d --no-deps web
docker exec emeca-web-1 python manage.py check

echo "== 5/5: repor APENAS boletins ausentes, com snapshot e transação =="
docker exec emeca-web-1 python manage.py restaurar_boletins_ausentes --aplicar

echo ""
echo "REPARO CONCLUÍDO. Os boletins devem voltar a totalizar 27."
echo "A tela WhatsApp não faz mais consulta remota se a limpeza está pendente."
echo "A limpeza do WA-AKG permanece BLOQUEADA para impedir perda de histórico."
echo "WA-AKG NÃO foi reiniciado, reconstruído ou excluído neste procedimento."
