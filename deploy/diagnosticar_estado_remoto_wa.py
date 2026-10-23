#!/usr/bin/env python3
"""Consulta passiva à sessão WA-AKG no MySQL, com resultados anônimos.

Não imprime nem grava sessionId, JID, credenciais, corpo de mensagens ou tokens.
Nunca chama rotas de logout, purge, início de sessão ou envio.
"""
import re
import subprocess

def cmd(args, timeout=25):
    try:
        return subprocess.run(args,text=True,capture_output=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired):
        return None

def main():
    print("=== WA-AKG: estado persistido da sessão (somente leitura) ===")
    script="from usuarioSec.sessao_whatsapp import sessao_atual_id; print('SESSAO_INTERNA:'+sessao_atual_id())"
    r=cmd(["docker","exec","emeca-web-1","python","manage.py","shell","-c",script])
    if r is None or r.returncode:
        print("Não foi possível obter o ID da sessão local; conteúdo protegido.")
        return
    ids=[line.removeprefix("SESSAO_INTERNA:") for line in r.stdout.splitlines() if line.startswith("SESSAO_INTERNA:")]
    if len(ids)!=1 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,120}",ids[0]):
        print("Sessão inesperada; consulta cancelada.")
        return
    sid=ids[0]
    # ID validado permite escapar de qualquer interpolação SQL insegura.
    sql=(
        "SELECT s.status, "
        "(SELECT COUNT(*) FROM Message m WHERE m.sessionId = s.id), "
        "(SELECT COUNT(*) FROM AuthState a WHERE a.sessionId = s.sessionId) "
        "FROM Session s WHERE s.sessionId = '"+sid+"' LIMIT 1;"
    )
    shell=(
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s -uroot '
        '"$MYSQL_DATABASE" -e '+ "'"+sql+"'"
    )
    q=cmd(["docker","exec","wa-akg-db","sh","-c",shell],timeout=25)
    if q is None:
        print("Consulta ao banco WA-AKG indisponível ou excedeu o tempo.")
        return
    if q.returncode:
        print("Consulta ao MySQL falhou (código",q.returncode,"); resultado bruto omitido.")
        return
    lines=q.stdout.strip().splitlines()
    if not lines:
        print("Sessão registrada no EMECA: NÃO encontrada na tabela Session do WA-AKG.")
    elif len(lines)==1:
        parts=lines[0].split("\t")
        if len(parts)!=3 or not all(p.isdigit() for p in parts[1:]):
            print("Resposta SQL inesperada; saída omitida por segurança.")
            return
        status=parts[0] if parts[0] in {"CONNECTED","CONNECTING","DISCONNECTED","LOGGED_OUT","STOPPED","SCAN_QR","STARTING"} else "OUTRO"
        print("Estado da sessão no banco WA-AKG:",status)
        print("Mensagens persistidas nessa sessão:",parts[1])
        print("Registros de autenticação dessa sessão:",parts[2])
    else:
        print("Resposta inesperada; saída omitida.")
    print("Somente SELECT. Nenhuma mensagem excluída, nenhuma sessão alterada.")

if __name__=="__main__":
    main()
