#!/usr/bin/env bash
# Atualização NÃO destrutiva da integração EMECA + WA-AKG para anexos.
# Requer pull prévio do repositório EMECA e Docker Compose funcionando.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ"

echo "[1/7] Verificando se há envios de boletins em andamento..."
docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n = EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE", "PROCESSANDO"]).count()
print("Lotes de boletins em aberto:", n)
if n:
    raise SystemExit("Aguarde os lotes de boletins antes de atualizar.")
'

echo "[2/7] Verificando campanhas do WA-AKG ainda em andamento..."
ativos="$(docker exec wa-akg-db sh -c 'mysql -N -s -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' | tr -d '[:space:]')"
case "$ativos" in
    0) ;;
    *[!0-9]*|"") echo "Não foi possível verificar os lotes. Atualização interrompida."; exit 1 ;;
    *) echo "Existem $ativos campanhas do WA-AKG em execução. Aguarde."; exit 1 ;;
esac

echo "[3/7] Validando patches e arquivos antes de modificar o WA-AKG..."
python3 -m unittest discover -s deploy/wa-akg -p 'test_*.py' -v
python3 deploy/wa-akg/aplicar_correcoes.py --dry-run

echo "[4/7] Aplicando o patch no código, sem tocar em dados/credenciais..."
python3 deploy/wa-akg/aplicar_correcoes.py

echo "[5/7] Construindo as novas imagens (pode demorar alguns minutos)..."
docker compose -f deploy/wa-akg/compose.secure.yaml build app
docker compose build web whatsapp-worker

echo "Executando testes da imagem nova ANTES da substituição de contêineres..."
docker compose run --rm --no-deps -e SKIP_DJANGO_INIT=1 web python manage.py check
docker compose run --rm --no-deps -e SKIP_DJANGO_INIT=1 web python manage.py test \
    usuarioSec.test_anexos_whatsapp_qa \
    usuarioSec.test_envio_massa_anexo_qa \
    usuarioSec.test_gateway_media_qa \
    usuarioSec.test_fila_boletim_qa

echo "[6/7] Rechecando lotes que possam ter iniciado durante a compilação..."
docker compose exec -T web python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp
n = EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE", "PROCESSANDO"]).count()
if n:
    raise SystemExit("Há envios pendentes. Imagens compiladas; reinício adiado.")
'
ativos="$(docker exec wa-akg-db sh -c 'mysql -N -s -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM BroadcastLog WHERE status = '\''running'\'';"' | tr -d '[:space:]')"
if [[ "$ativos" != "0" ]]; then
    echo "Há campanhas em andamento ou estado desconhecido; imagens compiladas, reinício adiado."
    exit 1
fi

echo "[7/7] Atualizando SOMENTE os aplicativos (nenhum banco ou volume é removido)..."
docker compose -f deploy/wa-akg/compose.secure.yaml up -d --no-deps app
docker compose up -d --no-deps web whatsapp-worker
docker compose exec -T web python manage.py check

echo "Instalação concluída. Confirme WhatsApp CONNECTED e teste somente UM documento autorizado."
echo "Não repetir automaticamente um PDF que possa ter sido recebido."
