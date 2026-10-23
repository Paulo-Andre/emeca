#!/usr/bin/env bash
# Reparo do painel EMECA sem alterações do WA-AKG e SEM RESTAURAR boletins
# com vínculos de identidade não comprovados.
set -Eeuo pipefail
cd /srv/projetos/emeca

fase="iniciando"
falha() {
  echo ""
  echo "REPARO SUSPENSO NA ETAPA: ${fase}"
  echo "Nenhum boletim foi restaurado ou excluído; nenhum WhatsApp foi desconectado."
  echo "Backups e banco atual não foram substituídos."
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
  site_publico.test_exclusao_boletim_individual --noinput

echo "== 4/5: atualizar somente a interface do EMECA =="
fase="implantar web"
docker compose up -d --no-deps web
docker exec emeca-web-1 python manage.py check

echo "== 5/5: auditar boletins antigos sem gravar nada =="
fase="auditoria de vínculos"
# A restauração antiga pressupunha IDs de alunos imutáveis; a reconciliação
# mostrou que podem ter sido alterados. Não chamar --aplicar automaticamente.
python3 deploy/comparar_boletins_atual_backups_readonly.py
python3 deploy/auditar_correspondencia_24_boletins.py
python3 deploy/auditar_identidade_24o_boletim.py

trap - ERR
echo ""
echo "INTERFACE EMECA ATUALIZADA SEM LIMPEZA WHATSAPP."
echo "Os boletins permanecem intactos. Backups existentes foram preservados."
echo "Restauração seletiva BLOQUEADA até todos os vínculos de alunos serem validados."
echo "WA-AKG, sessões, mídia e MySQL não foram recriados nem alterados."
