#!/usr/bin/env python3
"""Diagnóstico de leitura, sem segredos: MySQL WA-AKG, containers e backups EMECA.

NUNCA executa POST, DELETE, logout, stop, restart ou migracao.
Nao mostra numeros, contatos, credenciais, JIDs, nomes ou queries de clientes.
"""
import json
import os
import subprocess
from datetime import datetime, timezone

def run(argv, timeout=12):
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        return "OS_ERROR"

def mysql(query, label, timeout=12):
    cmd = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s -uroot "$MYSQL_DATABASE" -e ' + "'" + query.replace("'", "'\\''") + "'"
    r = run(["docker", "exec", "wa-akg-db", "sh", "-c", cmd], timeout=timeout)
    if r is None:
        print(label+": TEMPO_ESGOTADO")
        return None
    if r == "OS_ERROR":
        print(label+": IMPOSSIVEL_EXECUTAR_DOCKER")
        return None
    if r.returncode == 0:
        print(label+": OK")
        return r.stdout.strip()
    error = (r.stderr or "").lower()
    categories = [
        ("access denied", "ACESSO_NEGADO"),
        ("unknown column", "COLUNA_INEXISTENTE"),
        ("doesn't exist", "TABELA_INEXISTENTE"),
        ("unknown database", "BANCO_NAO_ENCONTRADO"),
        ("can't connect", "MYSQL_SEM_CONEXAO"),
        ("connection refused", "CONEXAO_RECUSADA"),
        ("server has gone away", "MYSQL_SEM_CONEXAO"),
        ("lost connection", "CONEXAO_PERDIDA"),
        ("lock wait timeout", "MYSQL_BLOQUEADO"),
        ("deadlock", "MYSQL_CONCORRENCIA"),
        ("no such file", "MYSQL_CLIENTE_AUSENTE"),
        ("not found", "MYSQL_CLIENTE_OU_BANCO_AUSENTE"),
        ("1045", "ACESSO_NEGADO"),
        ("1054", "COLUNA_INEXISTENTE"),
        ("1146", "TABELA_INEXISTENTE"),
        ("2002", "MYSQL_SEM_CONEXAO"),
        ("2003", "MYSQL_SEM_CONEXAO"),
    ]
    category=next((name for needle,name in categories if needle in error), "ERRO_SQL_NAO_CLASSIFICADO")
    print(label+": "+category+" (exit="+str(r.returncode)+")")
    return None

def main():
    print("=== EMECA / WA-AKG: estado seguro para recuperação ===")
    for service in ("emeca-web-1","emeca-whatsapp-worker-1","wa-akg-app","wa-akg-db"):
        template='{{json .State}}'
        r=run(["docker","inspect","--format",template,service],timeout=6)
        if not r or r=="OS_ERROR" or r.returncode!=0:
            print(service+": NAO_INSPECIONAVEL")
            continue
        try:
            st=json.loads(r.stdout)
            print(service+":",str(st.get("Status","?")),
                  "reinicios:",st.get("RestartCount","?"),
                  "health:",(st.get("Health") or {}).get("Status","sem_healthcheck"))
        except (ValueError,TypeError):
            print(service+": INSPECAO_INCONCLUSIVA")

    mysql("SELECT 1;", "MySQL autenticação/saúde")
    mysql("SELECT COUNT(*) FROM Session;", "MySQL tabela Session")
    mysql("SELECT COUNT(*) FROM AuthState;", "MySQL tabela AuthState")
    # Contagem por sessao feita somente se houver ID validado por EMECA.
    code = """import json
from usuarioSec.sessao_whatsapp import sessao_atual_id
from usuarioSec.models import SessaoWhatsAppAtiva
s=sessao_atual_id()
flag=SessaoWhatsAppAtiva.objects.filter(chave='secretaria', limpeza_pendente=True).exists()
print('WA_STATE:'+json.dumps({'id':s,'pendente':flag}))"""
    p=run(["docker","exec","emeca-web-1","python","manage.py","shell","-c",code],timeout=12)
    sid=None
    if p and p!="OS_ERROR" and p.returncode==0:
        import re
        for ln in p.stdout.splitlines():
            if ln.startswith("WA_STATE:"):
                try:
                    x=json.loads(ln[len("WA_STATE:"):])
                    if isinstance(x.get("id"),str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}",x["id"]):
                        sid=x["id"]
                    print("EMECA limpeza pendente:",bool(x.get("pendente")))
                except (ValueError,TypeError):
                    pass
    if sid:
        # Respostas retidas dentro do script, sem exibir identificador da conta.
        session=mysql("SELECT status FROM Session WHERE sessionId='"+sid+"' LIMIT 1;",
                      "MySQL estado da sessão do EMECA")
        if session is not None:
            print("Sessão antiga:", session if session else "NAO_ENCONTRADA")
        mysql("SELECT COUNT(*) FROM Message WHERE sessionId IN (SELECT id FROM Session WHERE sessionId='"+sid+"');",
              "MySQL mensagens da sessão")
        mysql("SELECT COUNT(*) FROM AuthState WHERE sessionId='"+sid+"';",
              "MySQL autenticações da sessão")

    root="/srv/backups/emeca"
    if os.path.isdir(root):
        try:
            files=[]
            for base,dirs,items in os.walk(root):
                dirs[:]=dirs[:]
                for name in items:
                    path=os.path.join(base,name)
                    try:
                        st=os.stat(path)
                        if os.path.isfile(path):
                            files.append((st.st_mtime,st.st_size))
                    except OSError: pass
            print("Arquivos em /srv/backups/emeca:",len(files))
            if files:
                newest=max(files)
                dt=datetime.fromtimestamp(newest[0],tz=timezone.utc)
                print("Backup mais recente (UTC, metadados apenas):",dt.strftime("%Y-%m-%d %H:%M"),
                      "tamanho do arquivo:",newest[1],"bytes")
        except OSError:
            print("Pasta de backup: SEM_ACESSO")
    else:
        print("Pasta /srv/backups/emeca: NAO_ENCONTRADA")

    print("Verificação encerrada. NENHUM dado alterado.")

if __name__=="__main__":
    main()
