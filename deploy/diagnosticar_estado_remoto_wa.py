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
        "0 "
        "FROM Session s WHERE s.sessionId = '"+sid+"' LIMIT 1;"
    )
    shell=(
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s -uroot '
        '"$MYSQL_DATABASE" -e '+ "'"+sql+"'"
    )
    # Verificar se o processo está ativo antes da consulta SQL. Nunca imprimir
    # variáveis de ambiente, IDs ou as mensagens de erro brutas do MySQL.
    for container in ("wa-akg-db", "wa-akg-app", "emeca-web-1"):
        estado=cmd(["docker","inspect","--format","{{.State.Status}}",container],timeout=8)
        valor=(estado.stdout or "").strip() if estado and estado.returncode==0 else "NAO_LOCALIZADO"
        print("Container",container+":",valor if valor in ("running","exited","created","restarting","paused","dead") else "NAO_LOCALIZADO")

    # A contagem de AuthState pode não existir no esquema instalado.
    q=cmd(["docker","exec","wa-akg-db","sh","-c",shell],timeout=25)
    if q is None:
        print("Consulta ao banco WA-AKG indisponível ou excedeu o tempo.")
        return
    if q.returncode:
        # Reproduzir apenas códigos MySQL padronizados; erro bruto pode conter
        # host, arquivo interno, credencial ou JID.
        code_match=re.search(r"(?:ERROR|Error)\s+(\d{3,4})",q.stderr or "")
        code=code_match.group(1) if code_match else "NAO_IDENTIFICADO"
        print("Consulta ao MySQL falhou. Código de processo:",q.returncode,
              "| código MySQL:",code)
        if code=="NAO_IDENTIFICADO":
            raw=(q.stderr or "").lower()
            if "not found" in raw:
                print("Classificação: executável/contêiner/comando não localizado.")
            elif "not running" in raw:
                print("Classificação: contêiner não está em execução.")
            else:
                print("Classificação: revisar disponibilidade ou autenticação do banco.")
        elif code in ("1045","1698"):
            print("Classificação: acesso ao MySQL recusado.")
        elif code in ("2002","2003","2006","2013"):
            print("Classificação: serviço MySQL indisponível ou conexão interrompida.")
        elif code in ("1146","1054","1064"):
            print("Classificação: consulta incompatível com esquema SQL atual.")
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
        print("Registros de autenticação: não consultados nesta versão segura.")
    else:
        print("Resposta inesperada; saída omitida.")
    print("Somente SELECT. Nenhuma mensagem excluída, nenhuma sessão alterada.")

if __name__=="__main__":
    main()
