#!/usr/bin/env python3
"""Auditoria de estado da sessão EMECA / WA-AKG, SEM limpeza ou conexões.

Não mostra IDs de sessão, credenciais, JIDs, nomes, textos ou qualquer mídia.
Não usa API de logout/purge e não escreve em nenhum banco.
"""
import json
import re
import subprocess

DJANGO_QUERY = r"""
import json
from usuarioSec.sessao_whatsapp import sessao_atual_id, limpeza_historico_pendente
print("EMECA_ESTADO_WA:" + json.dumps({
    "id":sessao_atual_id(),
    "pendente":limpeza_historico_pendente()
}))
"""

def run(args, *, input=None, timeout=16):
    try:
        out=subprocess.run(args,input=input,capture_output=True,text=True,
                           check=False,timeout=timeout)
        return out if out.returncode == 0 else None
    except (OSError,subprocess.TimeoutExpired):
        return None

def main():
    print("=== SITUAÇÃO DA LIMPEZA WHATSAPP (SOMENTE LEITURA) ===")
    proc=run(["docker","exec","emeca-web-1","python",
              "manage.py","shell","-c",DJANGO_QUERY],timeout=18)
    if not proc:
        print("Django: consulta indisponível.")
        return
    d=None
    for line in proc.stdout.splitlines():
        if line.startswith("EMECA_ESTADO_WA:"):
            try:d=json.loads(line.split(":",1)[1])
            except ValueError:pass
    if not isinstance(d,dict):
        print("Django: retorno não reconhecido.")
        return
    print("Marcador de limpeza pendente no EMECA:",bool(d.get("pendente")))
    sid=d.get("id")
    if not isinstance(sid,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,120}",sid):
        print("Formato interno de ID inesperado. Consulta abortada.")
        return

    sql=("SELECT status FROM Session WHERE sessionId = '"+sid+"' LIMIT 1;")
    # SQL de SELECT chega por stdin, não por argumento/linha de comando.
    p=run(["docker","exec","-i","wa-akg-db","sh","-c",
           'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s -uroot "$MYSQL_DATABASE"'],
           input=sql+"\n",timeout=18)
    if p is None:
        print("Banco WA-AKG: indisponível. NÃO tente limpar novamente.")
    else:
        estados=[x.strip() for x in p.stdout.splitlines() if x.strip()]
        print("Sessão no banco WA-AKG:", estados[0][:40] if estados else "NÃO ENCONTRADA")
        print("Isso é apenas um retrato do banco; não comprova estado do socket.")
    status=run(["docker","inspect","-f",
                "{{.State.Status}}|{{.State.OOMKilled}}|{{.RestartCount}}",
                "wa-akg-app"],timeout=10)
    if status and "|" in status.stdout:
        estado,oom,reinicios=status.stdout.strip().split("|",2)
        print("Contêiner WA-AKG:", estado,
              "| OOMKilled:",oom,"| reinícios:",reinicios)
    print("Nenhuma conexão iniciada, mensagem enviada ou limpeza executada.")

if __name__=="__main__":
    main()
