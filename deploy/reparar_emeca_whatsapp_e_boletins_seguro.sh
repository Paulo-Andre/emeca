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

echo "== 5/5: recuperação conservadora por identidade comprovada =="
fase="reposição dos boletins"
# O banco já possui backup íntegro. A origem histórica também precisa
# corresponder à turma/ano, nome E data de nascimento. Nunca restaurar
# boletins por mera igualdade de ID (IDs podem ter sido reutilizados).
if docker exec emeca-web-1 python manage.py recuperar_boletins_por_identidade; then
  if docker exec emeca-web-1 python manage.py recuperar_boletins_por_identidade --aplicar; then
    echo "REPOSICAO: verifique a contagem acima (boletins seguros restaurados)."
  else
    echo "REPOSICAO_NAO_APLICADA: o comando rejeitou uma condição insegura."
    echo "Os boletins atuais e todos os backups permanecem preservados."
  fi
else
  echo "REPOSICAO_NAO_APLICADA: sem referência histórica válida ou vínculo seguro."
  echo "O painel foi atualizado, mas a recuperação de dados continua pendente."
fi

echo "== Resumo final da instalação (somente leitura) =="
fase="resumo"
docker exec emeca-web-1 python manage.py shell -c '
from site_publico.models import BoletimAluno
from usuarioSec.models import SessaoWhatsAppAtiva
from django.conf import settings
print("BOLETINS_PERIODO_3:", BoletimAluno.objects.filter(periodo_id=3).count())
print("BOLETINS_TOTAL:", BoletimAluno.objects.count())
print("WA_LIMPEZA_PENDENTE:", SessaoWhatsAppAtiva.objects.filter(
    chave="secretaria", limpeza_pendente=True
).exists())
'
echo ""
echo "== Verificação automática do erro HTTP 500 (sem ação destrutiva) =="
python3 deploy/diagnosticar_whatsapp_500_e_boletins.py || true
echo "IMPLANTACAO WEB CONCLUIDA. Nenhum serviço WA-AKG foi reiniciado."
echo "A sessão com limpeza pendente NÃO é apagada ou liberada por este script:"
echo "isso exige verificação da situação remota, para impedir perda de mensagens."
echo "Se houver menos de 27 boletins no período 3, a recuperação permanece parcial."
