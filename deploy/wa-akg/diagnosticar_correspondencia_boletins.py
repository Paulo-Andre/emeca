#!/usr/bin/env python3
"""Diagnóstico de leitura: cruza boletins EMECA e registros WA-AKG.

Não imprime telefones, JIDs, conteúdo, nome de alunos, credenciais ou message IDs.
Não modifica nenhum banco e não envia mensagens.
A correspondência é indicativa: o EMECA ainda não armazena o message ID do WA-AKG.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys

TIMEOUT=35

def run(args, *, marker=None):
    try:
        r=subprocess.run(args, text=True, capture_output=True, timeout=TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("Consulta indisponível:",type(exc).__name__)
        return None
    if r.returncode:
        # Nunca reproduzir stderr ou stdout; podem conter dados da escola.
        print("Consulta falhou (código):",r.returncode)
        return None
    if marker:
        for line in reversed(r.stdout.splitlines()):
            if line.startswith(marker):
                try: return json.loads(line[len(marker):])
                except json.JSONDecodeError: break
        print("Formato de resposta Django não reconhecido")
        return None
    return r.stdout

def dateutc(value):
    if not value: return None
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt.astimezone(timezone.utc)
    except (ValueError,TypeError): return None

def main():
    print("=== Compilação do template WhatsApp Mensagens ===")
    template=run([
        "docker","exec","emeca-web-1","python","manage.py","shell","-c",
        "from django.template.loader import get_template; get_template('whatsapp_mensagens.html'); print('TEMPLATE_EMECA_VALIDO')",
    ])
    if template is not None:
        print("Template:", "sintaxe válida" if "TEMPLATE_EMECA_VALIDO" in template else "resultado inconclusivo")
    else:
        print("Template: falha ao compilar ou consulta indisponível (detalhes não divulgados)")
    print("=== Comparação anônima de boletins e documentos do WA-AKG ===")
    django_cmd = (
        "import json;"
        "from usuarioSec.models import ItemEnvioBoletimWhatsApp;"
        "q=list(ItemEnvioBoletimWhatsApp.objects"
        ".select_related('envio')"
        ".order_by('-envio_id','id')[:40]);"
        "dados=[{'lote':x.envio_id,'lote_status':x.envio.status,"
        "'item_status':x.status,'sessao':x.envio.sessao,"
        "'jid':x.jid,'inicio':x.envio.criado_em.isoformat(),"
        "'aceito':x.enviado_em.isoformat() if x.enviado_em else None}"
        " for x in q];"
        "print('EMECA_DIAG_JSON:'+json.dumps(dados))"
    )
    items=run(["docker","exec","emeca-web-1","python","manage.py","shell","-c",django_cmd],
              marker="EMECA_DIAG_JSON:")
    if items is None:
        print("Não foi possível comparar lotes: leitura do EMECA indisponível")
        return
    sql=(
        "SELECT s.sessionId,m.remoteJid,m.status,"
        "DATE_FORMAT(m.timestamp,'%Y-%m-%dT%H:%i:%s') "
        "FROM Message AS m JOIN Session AS s ON s.id=m.sessionId "
        "WHERE m.fromMe=1 AND m.type='DOCUMENT' "
        "AND m.timestamp >= UTC_TIMESTAMP() - INTERVAL 3 DAY "
        "ORDER BY m.timestamp DESC LIMIT 600;"
    )
    mysql_cmd=(
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" '
        'mysql -N -B -s -uroot "$MYSQL_DATABASE" -e '+ "'" + sql.replace("'","'\\''") + "'"
    )
    mysql=run(["docker","exec","wa-akg-db","sh","-c",mysql_cmd])
    if mysql is None:
        print("Não foi possível comparar lotes: leitura MySQL indisponível")
        return
    docs=defaultdict(list)
    for line in mysql.splitlines():
        cells=line.split("\t")
        if len(cells)!=4: continue
        sessao,jid,status,when=cells
        parsed=dateutc(when)
        if parsed is not None: docs[(sessao,jid)].append((parsed,status))

    by_batch=defaultdict(list)
    for x in items:
        if isinstance(x,dict) and isinstance(x.get("lote"),int):
            by_batch[x["lote"]].append(x)
    if not by_batch:
        print("Nenhum item de boletim nos últimos lotes")
        return
    for batch,rows in sorted(by_batch.items(),reverse=True)[:8]:
        matched=0
        observed=Counter()
        for item in rows:
            start=dateutc(item.get("inicio"))
            if start is None: continue
            # Apenas documentos enviados no intervalo próximo à criação do lote.
            candidates=[
                (dt,status) for dt,status in docs.get((item.get("sessao"),item.get("jid")),[])
                if start-timedelta(minutes=5)<=dt<=start+timedelta(hours=3)
            ]
            if candidates:
                matched+=1
                observed[candidates[0][1]]+=1
        print(
            f"Lote {batch}: EMECA={rows[0].get('lote_status','?')}, "
            f"itens={len(rows)}, aceites={sum(x.get('item_status')=='ENVIADO' for x in rows)}, "
            f"documentos possivelmente correspondentes={matched}; "
            f"estados WA-AKG={dict(sorted(observed.items()))}"
        )
    print("Nota: a relação é por sessão + destinatário + horário, não por ID da mensagem;")
    print("um documento correspondente NÃO prova que foi aquele boletim nem sua entrega.")
    print("Fim. Nenhuma mensagem enviada ou dado alterado.")

if __name__=="__main__":
    main()
