#!/usr/bin/env bash
# EMECA: diagnóstico SOMENTE LEITURA de erro 500 e aceite de boletins.
# Não reinicia, não aplica migração, não envia mensagens e não expõe telefones/JIDs.
set -uo pipefail

echo "=== 1. Integridade do sistema ==="
docker ps --filter name=emeca-web-1 --filter name=emeca-whatsapp-worker-1 --filter name=wa-akg-app --format 'table {{.Names}}\t{{.Status}}'

echo "=== 2. Migrações WhatsApp no EMECA (somente leitura) ==="
if ! timeout -k 2s 20s docker exec emeca-web-1 python manage.py showmigrations usuarioSec 2>&1 | tail -22; then
  echo "Não foi possível verificar as migrações; nenhum ajuste feito."
fi

echo "=== 3. Lotes e estado dos itens, sem dados de alunos ==="
if ! timeout -k 2s 20s docker exec emeca-web-1 python manage.py shell -c '
from usuarioSec.models import EnvioBoletimWhatsApp, ItemEnvioBoletimWhatsApp
from django.db.models import Count
for lote in EnvioBoletimWhatsApp.objects.order_by("-id")[:8]:
    itens = dict(ItemEnvioBoletimWhatsApp.objects.filter(envio_id=lote.id)
        .values("status").annotate(quantidade=Count("id"))
        .values_list("status", "quantidade"))
    print("Lote", lote.id, "status", lote.status, "aceites", lote.enviados, "falhas", lote.falhas, "itens", itens)
' 2>&1 | tail -25; then
  echo "Consulta de lotes indisponível; nenhum dado foi alterado."
fi

echo "=== 4. Tipos e linhas relevantes dos erros 500 do Django ==="
python3 - <<'PY'
import os
import re
import subprocess
try:
    cmd=subprocess.run(
        ["docker","logs","--since","3h","--tail","1200","emeca-web-1"],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        errors="replace",timeout=20,check=False)
except (OSError,subprocess.TimeoutExpired) as exc:
    print("Não foi possível consultar logs; tipo:",type(exc).__name__)
    raise SystemExit(0)
if cmd.returncode:
    print("Leitura de logs falhou (código)",cmd.returncode)
    raise SystemExit(0)
lines=(cmd.stdout+"\n"+cmd.stderr).splitlines()
blocks=[]
start=0
for idx,line in enumerate(lines):
    if "Traceback (most recent call last):" in line:
        start=idx
    if re.search(r"(?:^|\s)(?:[\w.]*)(?:Error|Exception)\s*:",line):
        blocks.append(lines[max(0,start):idx+1])
print("Exceções registradas:",len(blocks))
if not blocks:
    print("Nenhuma exceção com traceback identificada nesse período.")
for block in blocks[-4:]:
    safe=[]
    for line in block[-50:]:
        mt=re.search(r'File "([^"]+)", line (\d+)(?:, in ([a-zA-Z0-9_<>]+))?',line)
        if mt:
            filename=os.path.basename(mt.group(1))
            fn=mt.group(3) or "?"
            safe.append("  "+filename+":"+mt.group(2)+" em "+fn)
            continue
        if "Internal Server Error" in line:
            safe.append("  "+("Rota WhatsApp Mensagens" if "/whatsapp/mensagens/" in line else "Erro interno registrado"))
            continue
        mt=re.search(r'([A-Za-z_][\w.]*(?:Error|Exception))\s*:',line)
        if mt:
            description=line[mt.end():].strip()
            # Só reproduzir a estrutura de erro conhecida e não confidencial.
            allow=(
                r"^(?:no such table|no such column|table .* does not exist|"
                r"column .* does not exist|database is locked|"
                r"UNIQUE constraint failed|Cannot resolve keyword|"
                r"Field .* does not exist)"
            )
            if re.search(allow,description,re.I):
                description=re.sub(r"[0-9]{7,}","[número]",description)
                description=re.sub(r"[\w.+-]+@[\w.-]+","[e-mail]",description)
                description=re.sub(r"https?://\S+","[URL]",description)
                description=description[:150]
                safe.append("  "+mt.group(1)+": "+description)
            else:
                safe.append("  "+mt.group(1)+" (detalhe suprimido por privacidade)")
    for v in safe[-18:]: print(v)
    print("---")
PY

echo "=== 5. Resumo anônimo dos documentos enviados no WA-AKG ==="
timeout -k 2s 20s docker exec wa-akg-db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -s -uroot "$MYSQL_DATABASE" -e "SELECT type, status, COUNT(*) FROM Message WHERE fromMe=1 AND type = '\''DOCUMENT'\'' AND timestamp >= (UTC_TIMESTAMP() - INTERVAL 24 HOUR) GROUP BY type,status ORDER BY type,status;"' 2>/dev/null || echo "Resumo indisponível; nenhum dado alterado."

echo "DIAGNÓSTICO FINALIZADO (somente leitura, sem telefone, JID ou conteúdo de boletins)."
