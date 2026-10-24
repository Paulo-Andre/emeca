#!/usr/bin/env bash
# Publica ajuste da seleção "Turmas do Boletim" para PDFs personalizados.
# Executa um backup consistente; testes completos são responsabilidade do CI.
# Não envia mensagens e não reinicia WA-AKG (Node/MySQL).
set -Eeuo pipefail
cd /srv/projetos/emeca
echo "=== Atualização única: PDFs por Turmas do Boletim ==="
test "$(git branch --show-current)" = "main" || { echo "Use a branch main."; exit 1; }
test -z "$(git status --porcelain)" || { echo "Arquivos locais alterados: não sobrescrever."; exit 1; }
docker compose config --quiet
test -f .env && test -d /srv/backups/emeca || { echo "Ambiente ou backups ausentes."; exit 1; }

# Nunca interromper um lote de boletins no meio de envio de PDFs.
EM_ANDAMENTO="$(docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp, ItemEnvioBoletimWhatsApp
print("FILAS_PROCESSANDO=" + str(
    EnvioBoletimWhatsApp.objects.filter(status="PROCESSANDO").count()
    + ItemEnvioBoletimWhatsApp.objects.filter(status="PROCESSANDO").count()
))
' | sed -n 's/^FILAS_PROCESSANDO=//p' | tail -n1)"
[[ "$EM_ANDAMENTO" =~ ^[0-9]+$ ]] || { echo "Não foi possível conferir fila."; exit 1; }
test "$EM_ANDAMENTO" = 0 || {
  echo "Há envios de boletins processando; atualização suspensa, sem interromper o worker."
  exit 1
}

echo "1/4: ÚNICO backup consistente do banco escolar"
BACKUP_LOG="$(docker compose exec -T web python manage.py shell < deploy/backup_emeca_seguro.py)"
echo "$BACKUP_LOG" | grep '^BACKUP_OK:' || {
  echo "Backup íntegro não confirmado: implantação bloqueada."
  exit 1
}
echo "$BACKUP_LOG" | grep '^No host:'

echo "2/4: Compilando a versão aprovada no GitHub"
docker compose build web whatsapp-worker

echo "3/4: Atualizando a interface sem tocar no WA-AKG"
docker compose up -d --no-deps web
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py migrate --check
docker compose up -d --no-deps whatsapp-worker

echo "4/4: Resumo sem envio de mensagens"
docker compose ps web whatsapp-worker
docker compose exec -T web python manage.py shell -c '
from site_publico.models import PeriodoBoletim
from django.db.models import Count
for p in PeriodoBoletim.objects.annotate(total=Count("boletins")).filter(total__gt=0).order_by("-ano","-numero","pk"):
    print(f"BOLETIM_PERIODO_ID={p.pk} / ANO={p.ano} / TURMA={p.turma} / PUBLICADO={p.publicado} / ALUNOS={p.total}")
'
echo "Concluído. Turmas do Boletim agora disponíveis também para PDFs individuais."
echo "Nenhum envio real foi disparado pelo instalador."
