#!/usr/bin/env bash
# Reparo do painel EMECA sem alterações do WA-AKG, repondo APENAS boletins
# com vínculos de identidade fortemente comprovados.
set -Eeuo pipefail
cd /srv/projetos/emeca

fase="iniciando"
falha() {
  echo ""
  echo "REPARO SUSPENSO NA ETAPA: ${fase}"
  echo "Nenhum comando de exclusão, logout ou limpeza WhatsApp foi executado por este reparo."
  echo "Nenhum backup existente foi substituído."
  echo "Se a falha ocorreu na reposição, a transação corrente é revertida; consulte a contagem atual."
}
trap falha ERR

echo "== 1/5: garantir cópia íntegra do banco ANTES de qualquer atualização =="
fase="backup atual"
# A versão do container web já em execução conhece o caminho SQLite verdadeiro.
# Não confiar apenas em 'docker cp' (pode ignorar o WAL).
backup_log="$(docker exec -i emeca-web-1 python manage.py shell < deploy/backup_emeca_seguro.py)"
if ! grep -q '^BACKUP_OK:' <<< "$backup_log"; then
  echo "Backup não confirmado; não é seguro implantar o reparo."
  exit 1
fi
echo "$backup_log" | grep '^BACKUP_OK:'
echo "Cópia preservada em /srv/backups/emeca; fonte original inalterada."

echo "== 2/5: compilar somente o EMECA web =="
fase="build web"
docker compose build web

echo "== 3/5: validações AUTOMÁTICAS na imagem nova (sem produção) =="
fase="testes isolados"
# docker compose images -q web pode devolver um digest de container ANTIGO
# já removido pelo build, gerando 'No such image: sha256:...'.
# A nova imagem foi publicada explicitamente como emeca-web:latest.
imagem="emeca-web:latest"
docker image inspect "$imagem" >/dev/null
docker run --rm --network none --entrypoint python \
  -e DJANGO_DEBUG=1 \
  -e DJANGO_SECRET_KEY=chave-sintetica-so-para-teste-emeca-2026 \
  -e DOCUMENT_SIGNING_KEY=assinatura-sintetica-so-para-teste-emeca-2026 \
  -e DJANGO_DB_ENGINE=sqlite \
  -e DJANGO_DB_PATH=/tmp/emeca-testes-reparo.sqlite3 \
  -e DJANGO_ALLOWED_HOSTS=localhost,testserver \
  -e DJANGO_RBAC_STRICT=0 \
  -e DJANGO_RATE_LIMIT_ENABLED=0 \
  "$imagem" manage.py test \
  usuarioSec.test_painel_whatsapp_pendente \
  usuarioSec.test_qr_limpeza_pendente \
  site_publico.test_recuperacao_boletins_ausentes \
  site_publico.test_recuperar_boletins_identidade \
  site_publico.test_exclusao_boletim_individual --noinput

echo "== 4/5: atualizar somente a interface do EMECA =="
fase="implantar web"
docker compose up -d --no-deps web
docker exec emeca-web-1 python manage.py check

echo "== 5/5: reposição SOMENTE por identidade única (sem reutilizar IDs antigos) =="
fase="simulação automática da correspondência de alunos"
# O comando antigo restaurar_boletins_ausentes dependia de IDs antigos,
# que podem estar reciclados. Não o utilizar.
docker exec emeca-web-1 python manage.py recuperar_boletins_por_identidade
fase="snapshot e reposição dos vínculos verificados"
# O próprio comando cria segundo snapshot íntegro e faz tudo em transação.
# Se houver menos de 23 vínculos comprovados, falha SEM restaurar.
# A identidade não resolvida fica pendente para conferência.
docker exec emeca-web-1 python manage.py recuperar_boletins_por_identidade --aplicar

trap - ERR
echo ""
echo "REPARO DO PAINEL E REPOSIÇÃO DE BOLETINS COM IDENTIDADE VERIFICADA CONCLUÍDOS."
echo "Alunos sem correspondência forte NÃO foram restaurados nem ligados a notas de terceiros."
echo "WA-AKG, sessão, mensagens e MySQL não foram recriados nem limpos."
echo "Backups anteriores e snapshots novos foram preservados."
