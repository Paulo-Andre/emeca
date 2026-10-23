#!/usr/bin/env python3
"""Leitura anônima de estado de purga WA-AKG/EMECA. Sem DELETE/POST/PUT.

Usa as credenciais que já existem DENTRO de cada contêiner.
Não imprime JID, sessionId, telefone, chave, nome nem mensagem.
"""
import json
import re
import subprocess

D = r'''
import json
from usuarioSec.models import SessaoWhatsAppAtiva
from usuarioSec.sessao_whatsapp import sessao_atual_id
x=SessaoWhatsAppAtiva.objects.filter(chave="secretaria").first()
print("ESTADO_LOCAL:"+json.dumps({
    "sessao": sessao_atual_id(),
    "pendente": bool(x and x.limpeza_pendente),
    "registro": bool(x),
}))
'''

def exec_query(args,timeout=20):
    try:
        return subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired):
        return None

def main():
    print("=== Estado de limpeza WhatsApp: somente leitura ===")
    r=exec_query(["docker","exec","emeca-web-1","python","manage.py","shell","-c",D])
    if r is None or r.returncode!=0:
        print("EMECA: consulta indisponível (sem dados expostos).")
        return
    info=None
    for line in r.stdout.splitlines():
        if line.startswith("ESTADO_LOCAL:"):
            try: info=json.loads(line.split(":",1)[1])
            except ValueError: pass
    if not isinstance(info,dict):
        print("EMECA: resposta inesperada.")
        return
    print("Limpeza pendente:", bool(info.get("pendente")))
    print("Registro de sessão:", bool(info.get("registro")))
    sid=info.get("sessao")
    if not isinstance(sid,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}",sid):
        print("ID de sessão não validado: consulta remota cancelada.")
        return

    # Uma consulta somente de leitura. Nunca executar DROP/DELETE/PURGE.
    sql=(
        "SELECT 'SESSAO',status FROM Session WHERE sessionId='"+sid+"';"
        "SELECT 'MENSAGENS',COUNT(*) FROM Message WHERE sessionId IN "
        "(SELECT id FROM Session WHERE sessionId='"+sid+"');"
        "SELECT 'AUTENTICACOES',COUNT(*) FROM AuthState WHERE sessionId='"+sid+"';"
    )
    cmd=(
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" '
        'mysql -N -B -s -uroot "$MYSQL_DATABASE" -e '+"'"+sql+"'"
    )
    q=exec_query(["docker","exec","wa-akg-db","sh","-c",cmd])
    if q is None or q.returncode!=0:
        print("WA-AKG MySQL: consulta indisponível (sem dados expostos).")
        return
    dados={}
    for line in q.stdout.splitlines():
        row=line.split("\t")
        if len(row)==2 and row[0] in {"SESSAO","MENSAGENS","AUTENTICACOES"}:
            dados[row[0]]=row[1][:40]
    print("Sessão antiga no WA-AKG:", "ENCONTRADA" if "SESSAO" in dados else "NAO_ENCONTRADA")
    print("Status WA-AKG:",dados.get("SESSAO","—"))
    print("Mensagens associadas:",dados.get("MENSAGENS","indefinido"))
    print("Credenciais da sessão (quantidade de registros):",
          dados.get("AUTENTICACOES","indefinido"))
    print("Somente análise do estado. Nada desconectado, apagado ou enviado.")

if __name__=="__main__":
    main()
