#!/usr/bin/env python3
"""Auditoria de leitura de uma limpeza pendente do WA-AKG.
NÃO chama APIs de exclusão/logout, não envia mensagens e não modifica bancos.
Não revela session ID, JIDs, nomes, tokens, conteúdo ou senhas.
"""
import json
import re
import shlex
import subprocess

def run(args,timeout=22):
    try:
        return subprocess.run(args, capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as e:
        print("Consulta indisponível:",type(e).__name__)
        return None

READ_DJANGO = """
import json
from usuarioSec.sessao_whatsapp import sessao_atual_id, limpeza_historico_pendente
from usuarioSec.models import EnvioBoletimWhatsApp
from site_publico.models import PeriodoBoletim, BoletimAluno
print("ESTADO_SEGURO:"+json.dumps({
  "sessao": sessao_atual_id(),
  "pendente": limpeza_historico_pendente(),
  "periodo_3_boletins": BoletimAluno.objects.filter(periodo_id=3).count(),
  "periodo_3_existe": PeriodoBoletim.objects.filter(pk=3).exists(),
  "lotes_ativos": EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
}))
"""

def main():
    print("=== Estado da limpeza WA-AKG e dos boletins: SOMENTE LEITURA ===")
    p=run(["docker","exec","emeca-web-1","python","manage.py","shell","-c",READ_DJANGO])
    if not p or p.returncode:
        print("Falha ao consultar Django, sem mostrar saída com dados particulares.")
        return
    data=None
    for line in p.stdout.splitlines():
        if line.startswith("ESTADO_SEGURO:"):
            try:data=json.loads(line.split(":",1)[1])
            except ValueError:pass
    if not isinstance(data,dict):
        print("Formato da consulta EMECA não reconhecido.")
        return
    print("Limpeza pendente:",data.get("pendente"))
    print("Período 3 existe:",data.get("periodo_3_existe"))
    print("Boletins restantes no período 3:",data.get("periodo_3_boletins"))
    print("Lotes de boletins ativos:",data.get("lotes_ativos"))
    sid=data.get("sessao")
    if not isinstance(sid,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}",sid):
        print("Identificador de sessão com formato inesperado. Consulta WA cancelada.")
        return
    sqlsid="'"+sid+"'"
    sql=(
      "SELECT "
      f"(SELECT COUNT(*) FROM Session WHERE sessionId={sqlsid}),"
      f"(SELECT COALESCE(MAX(status),'AUSENTE') FROM Session WHERE sessionId={sqlsid}),"
      f"(SELECT COUNT(*) FROM AuthState WHERE sessionId={sqlsid}),"
      f"(SELECT COUNT(*) FROM Message WHERE sessionId IN (SELECT id FROM Session WHERE sessionId={sqlsid}));"
    )
    command=(
      'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s -uroot "$MYSQL_DATABASE"'
      ' -e '+shlex.quote(sql)
    )
    w=run(["docker","exec","wa-akg-db","sh","-c",command],timeout=25)
    if not w or w.returncode:
        print("WA-AKG MySQL: consulta não disponível. Não altere a sessão.")
    else:
        cells=w.stdout.strip().split("\t")
        if len(cells)==4 and all(re.fullmatch(r"\d+",cells[j] or "") for j in (0,2,3)):
            print("Sessão remota existe:",int(cells[0])>0)
            print("Estado gravado no WA-AKG:",cells[1][:30])
            print("Registros de autenticação:",cells[2])
            print("Registros de mensagens da sessão:",cells[3])
        else:
            print("WA-AKG MySQL: resposta desconhecida, conteúdo omitido.")
    q=run(["docker","inspect","--format","{{.State.Status}}","wa-akg-app"],timeout=5)
    if q and q.returncode==0:
        print("Contêiner WA-AKG:",q.stdout.strip()[:40])
    print("SEM EXCLUSÃO, SEM RECONEXÃO, SEM DISPARO E SEM ALTERAÇÕES.")

if __name__=="__main__":
    main()
