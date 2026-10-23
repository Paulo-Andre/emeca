#!/usr/bin/env python3
"""Diagnóstico read-only de saúde do WA-AKG quando limpeza está pendente.

NÃO reinicia serviços, NÃO muda banco, NÃO chama logout/purge, NÃO envia mensagens.
Saída anônima: não inclui session IDs, tokens, JIDs, nomes ou corpos de mensagens.
"""
import json
import re
import subprocess

def command(args, timeout=9):
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, check=False)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return "TIMEOUT", ""
    except OSError:
        return "INDISPONIVEL", ""

def check_containers():
    for name in ("emeca-web-1", "wa-akg-app", "wa-akg-db"):
        rc, stdout = command(["docker", "inspect", "--format",
            '{{json .State}}', name], 5)
        if rc == 0:
            try:
                s = json.loads(stdout)
                print(name + ":", "running" if s.get("Running") else "stopped",
                      "| oom:", bool(s.get("OOMKilled")),
                      "| exit:", s.get("ExitCode"),
                      "| health:", (s.get("Health") or {}).get("Status", "não informado"))
            except ValueError:
                print(name + ": estado sem formato reconhecido")
        else:
            print(name + ": docker inspect indisponível", rc)

def check_mysql():
    sql = "SELECT 1;"
    cmd = ('MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql '
           '--connect-timeout=3 -N -B -s -uroot "$MYSQL_DATABASE" -e '
           + "'" + sql + "'")
    rc, output = command(["docker", "exec", "wa-akg-db", "sh", "-c", cmd], 10)
    print("WA-AKG MySQL SELECT 1:", "OK" if rc == 0 and output.strip() == "1"
          else "FALHA/TEMPO ESGOTADO " + str(rc))
    if rc != 0:
        return
    sql = "SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_connected','Threads_running');"
    cmd = ('MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql '
           '--connect-timeout=3 -N -B -s -uroot "$MYSQL_DATABASE" -e '
           + "'" + sql.replace("'", "'\\''") + "'")
    rc, output = command(["docker", "exec", "wa-akg-db", "sh", "-c", cmd], 10)
    if rc == 0:
        for line in output.splitlines():
            pieces = line.split("\t")
            if len(pieces) == 2 and pieces[0] in ("Threads_connected","Threads_running"):
                if pieces[1].isdigit():
                    print("MySQL "+pieces[0]+": "+pieces[1])
    else:
        print("MySQL estatísticas não disponíveis:", rc)

def check_emeca_tcp():
    snippet = r"""
from django.conf import settings
from urllib.parse import urlparse
import socket
p=urlparse(settings.WA_AKG_BASE_URL)
if not p.hostname or p.scheme not in ("http","https"):
    print("WA_TCP:NAO_CONFIGURADO")
else:
    try:
        with socket.create_connection((p.hostname,p.port or (443 if p.scheme == "https" else 80)),timeout=3):
            print("WA_TCP:OK")
    except (OSError,TimeoutError) as exc:
        print("WA_TCP:"+type(exc).__name__)
"""
    rc,out=command(["docker","exec","emeca-web-1","python","manage.py",
                    "shell","-c",snippet],10)
    msg=next((l.split("WA_TCP:",1)[1].strip() for l in out.splitlines()
              if l.startswith("WA_TCP:")),None) if rc == 0 else None
    print("EMECA -> WA-AKG TCP:",msg or "SEM_RESPOSTA " + str(rc))

def check_wa_local_http():
    snippet = """
const http=require('http');
const req=http.get('http://127.0.0.1:3000/',res=>{
  console.log('WA_LOCAL_HTTP:'+res.statusCode);
  res.destroy();
});
req.setTimeout(3000,()=>req.destroy(new Error('TEMPO')));
req.on('error',err=>console.log('WA_LOCAL_HTTP:'+(
  err.message==='TEMPO' ? 'TIMEOUT' : err.code || 'ERRO'
)));
"""
    rc,out=command(["docker","exec","wa-akg-app","node","-e",snippet],9)
    msg=next((l.split("WA_LOCAL_HTTP:",1)[1].strip() for l in out.splitlines()
              if l.startswith("WA_LOCAL_HTTP:")),None) if rc == 0 else None
    print("WA-AKG HTTP interno:",msg or "SEM_RESPOSTA " + str(rc))

def check_log_signals():
    rc,out=command(["docker","logs","--tail","180","wa-akg-app"],9)
    if rc != 0:
        print("Sinais de erro (logs): indisponíveis",rc)
        return
    markers={
        "Prisma/BD": r"\b(prisma|P20\d\d|database error|database connection)\b",
        "Timeout": r"\b(timeout|timed out|ETIMEDOUT)\b",
        "Memória": r"\b(out of memory|heap out of memory|allocation failed)\b",
        "Reinício/falha fatal": r"\b(fatal|uncaught|unhandled rejection)\b",
        "Socket WhatsApp": r"\b(connection closed|stream errored|logged out)\b",
    }
    for name, pattern in markers.items():
        n=len(re.findall(pattern,out,re.IGNORECASE))
        print("Sinais logs",name+":",n,"ocorrência(s)")
    print("O script não imprime linhas de log nem mensagens dos responsáveis.")

def main():
    print("=== Diagnóstico não destrutivo do WA-AKG ===")
    check_containers()
    check_mysql()
    check_emeca_tcp()
    check_wa_local_http()
    check_log_signals()
    print("Nenhuma alteração feita. Não repetir logout/purge enquanto limpeza pendente.")

if __name__ == "__main__":
    main()
