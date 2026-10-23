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
    # Verificar os contêineres antes de qualquer consulta.
    for container in ("wa-akg-db", "wa-akg-app", "emeca-web-1"):
        estado=cmd(["docker","inspect","--format","{{.State.Status}}",container],timeout=8)
        valor=(estado.stdout or "").strip() if estado and estado.returncode==0 else "NAO_LOCALIZADO"
        print("Container",container+":",valor if valor in
              ("running","exited","created","restarting","paused","dead") else "NAO_LOCALIZADO")

    def sql_ro(query):
        try:
            # SQL via stdin e somente leitura. Não imprimir saída bruta.
            return subprocess.run(
                ["docker","exec","-i","wa-akg-db","sh","-c",
                 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s -uroot "$MYSQL_DATABASE"'],
                input=query+"\n",capture_output=True,text=True,
                timeout=24,check=False,
            )
        except (OSError,subprocess.TimeoutExpired):
            return None

    def tratar_erro(p):
        if p is None:
            print("Consulta ao banco WA-AKG indisponível ou excedeu o tempo.")
            return
        code_match=re.search(r"(?:ERROR|Error)\s+(\d{3,4})",p.stderr or "")
        codigo=code_match.group(1) if code_match else "NAO_IDENTIFICADO"
        print("Consulta MySQL não concluída. Código MySQL:",codigo,
              "| código de processo:",p.returncode)

    # A mesma consulta já usada pelo diagnóstico de limpeza funciona neste
    # servidor. Evita JOIN/subconsulta até confirmar o esquema.
    status=sql_ro("SELECT status FROM Session WHERE sessionId='"+sid+"' LIMIT 1;")
    if status is None or status.returncode:
        tratar_erro(status)
        return
    linhas=[x.strip() for x in status.stdout.splitlines() if x.strip()]
    if not linhas:
        print("Sessão registrada no EMECA: NÃO encontrada em Session WA-AKG.")
        print("Não inicie nova sessão nem remova dados sem reconciliar a limpeza.")
        return
    st=linhas[0] if linhas[0] in (
        "CONNECTED","CONNECTING","DISCONNECTED","LOGGED_OUT",
        "STOPPED","SCAN_QR","STARTING"
    ) else "OUTRO"
    print("Estado da sessão no banco WA-AKG:",st)

    # Checar colunas efetivamente existentes, sem assumir o esquema Prisma
    # de outro commit. Não exibir a lista completa de tabelas/colunas.
    cols=sql_ro("SHOW COLUMNS FROM Message;")
    sess_cols=sql_ro("SHOW COLUMNS FROM Session;")
    if (cols is None or cols.returncode or
            sess_cols is None or sess_cols.returncode):
        print("Contagem de mensagens não disponível: consulta de esquema falhou.")
        return
    campos={row.split("\t",1)[0] for row in cols.stdout.splitlines() if "\t" in row}
    sess_fields={row.split("\t",1)[0] for row in sess_cols.stdout.splitlines() if "\t" in row}
    if not {"sessionId"}.issubset(campos) or not {"id","sessionId"}.issubset(sess_fields):
        print("Contagem de mensagens indisponível: campos divergem do modelo esperado.")
        return
    q=("SELECT COUNT(*) FROM Message WHERE sessionId="
       "(SELECT id FROM Session WHERE sessionId='"+sid+"' LIMIT 1);")
    total=sql_ro(q)
    if total is None or total.returncode:
        tratar_erro(total)
        return
    dado=total.stdout.strip()
    if not dado.isdigit():
        print("Contagem de mensagens inesperada; valor omitido.")
        return
    print("Mensagens persistidas nessa sessão:",dado)
    print("Registros de autenticação: não consultados.")
    print("Somente SELECT. Nenhuma mensagem excluída, nenhuma sessão alterada.")

if __name__=="__main__":
    main()
