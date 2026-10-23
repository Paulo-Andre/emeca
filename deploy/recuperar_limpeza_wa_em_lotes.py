#!/usr/bin/env python3
"""Recuperar limpeza P2028 de sessão WA-AKG LOGGED_OUT sem recriar contêineres.
--preflight: somente leitura. --aplicar: backups e purga por lotes autocommit.
ATENÇÃO: a exclusão solicitada é irreversível; revisar backups antes.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone

PAT = re.compile(r"[A-Za-z0-9_-]{3,120}\Z")
CONFIRM = "APAGAR_HISTORICO_DESVINCULADO"
BATCH = 2000

def run(args, timeout=60):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError("Comando falhou (%d); saída suprimida por privacidade." % p.returncode)
    return p.stdout.strip()

def db(sql, timeout=90):
    shell = ('MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s '
             '-uroot "$MYSQL_DATABASE" -e ' + shlex.quote(sql))
    return run(["docker", "exec", "wa-akg-db", "sh", "-c", shell], timeout)

def count(sql):
    value = db(sql).strip()
    if not value.isdecimal():
        raise RuntimeError("Contagem MySQL inválida.")
    return int(value)

def literal(value):
    if not isinstance(value, str) or not PAT.fullmatch(value):
        raise RuntimeError("Identificador inválido; interrompido.")
    return "'" + value + "'"

def django(code, timeout=60):
    output = run(["docker", "exec", "emeca-web-1", "python",
                  "manage.py", "shell", "-c", code], timeout)
    for line in output.splitlines():
        if line.startswith("WA_RECUPERACAO:"):
            return json.loads(line.split(":", 1)[1])
    raise RuntimeError("Resposta do Django sem marcador.")

STATUS = """
import json
from django.db import connection
from usuarioSec.sessao_whatsapp import sessao_atual_id,limpeza_historico_pendente
from usuarioSec.models import EnvioBoletimWhatsApp
print('WA_RECUPERACAO:'+json.dumps({
  'sid':sessao_atual_id(),
  'pendente':limpeza_historico_pendente(),
  'lotes':EnvioBoletimWhatsApp.objects.filter(
    status__in=['PENDENTE','PROCESSANDO']).count(),
  'banco':connection.vendor,
}))
"""

def preflight():
    state = django(STATUS)
    sid = state.get("sid")
    literal(sid)
    if not state.get("pendente"):
        raise RuntimeError("Não existe limpeza pendente: nada será alterado.")
    if state.get("lotes") != 0:
        raise RuntimeError("Há boletins na fila: não prosseguir.")
    if state.get("banco") != "sqlite":
        raise RuntimeError("Este recuperador somente aceita EMECA SQLite.")
    records = db("SELECT id,status FROM Session WHERE sessionId=" + literal(sid))
    parts = records.splitlines()
    if len(parts) > 1:
        raise RuntimeError("Identidade duplicada na tabela Session.")
    dbid = None
    if parts:
        row = parts[0].split("\t")
        if len(row) != 2 or not PAT.fullmatch(row[0]) or row[1] != "LOGGED_OUT":
            raise RuntimeError("A sessão remota não está LOGGED_OUT: bloqueado.")
        dbid = row[0]
    if count("SELECT COUNT(*) FROM AuthState WHERE sessionId="+literal(sid)) != 0:
        raise RuntimeError("Ainda há autenticação WA-AKG: exclusão bloqueada.")
    messages = count("SELECT COUNT(*) FROM Message WHERE sessionId="+literal(dbid)) if dbid else 0
    return sid, dbid, messages

def backup_all():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path("/srv/backups/emeca") / ("wa-p2028-" + stamp)
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(root, 0o700)
    temporary = "/tmp/wa-emeca-backup-" + stamp + ".sqlite3"
    make = ("import sqlite3,json;"
            "from django.db import connection;"
            "src=sqlite3.connect(str(connection.settings_dict['NAME']));"
            "dst=sqlite3.connect("+repr(temporary)+");"
            "src.backup(dst);dst.close();src.close();"
            "print('WA_RECUPERACAO:'+json.dumps({'ok':True}))")
    django(make, timeout=180)
    try:
        run(["docker", "cp", "emeca-web-1:" + temporary, str(root / "emeca.sqlite3")], 180)
    finally:
        subprocess.run(["docker", "exec", "emeca-web-1", "rm", "-f", temporary],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    if (root / "emeca.sqlite3").stat().st_size < 4096:
        raise RuntimeError("Backup SQLite incompleto. Nada apagado.")
    os.chmod(root / "emeca.sqlite3", 0o600)
    dump = root / "wa-akg.sql.gz"
    command = ('MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot '
               '--single-transaction --quick --no-tablespaces '
               '--set-gtid-purged=OFF "$MYSQL_DATABASE"')
    print("Backups: SQLite concluído; gerando dump integral MySQL...", flush=True)
    p = subprocess.Popen(["docker", "exec", "wa-akg-db", "sh", "-c", command],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with dump.open("wb") as f:
            os.chmod(dump, 0o600)
            with gzip.GzipFile(fileobj=f, mode="wb", compresslevel=2) as gz:
                shutil.copyfileobj(p.stdout, gz, length=1024*1024)
        p.stdout.close()
        code = p.wait(timeout=180)
    except BaseException:
        p.kill()
        p.wait()
        raise
    if code != 0 or dump.stat().st_size < 4096:
        raise RuntimeError("Dump MySQL falhou. Nada apagado.")
    print("BACKUPS CONCLUÍDOS:", root, flush=True)
    return root

def batches(table, key):
    if table not in ("Message", "Contact"):
        raise RuntimeError("Tabela inesperada.")
    total = 0
    while True:
        n = count("DELETE FROM " + table + " WHERE sessionId=" + literal(key)
                  + " LIMIT " + str(BATCH) + "; SELECT ROW_COUNT();")
        total += n
        if not n:
            return total
        if total % 20000 < BATCH:
            print(table, "apagados:", total, flush=True)

def purge(sid, dbid):
    if dbid:
        msg = batches("Message", dbid)
        contacts = batches("Contact", dbid)
        if count("SELECT COUNT(*) FROM Message WHERE sessionId="+literal(dbid)) \
            or count("SELECT COUNT(*) FROM Contact WHERE sessionId="+literal(dbid)):
            raise RuntimeError("Ainda existem mensagens ou contatos: sessão preservada.")
        db("DELETE FROM Label WHERE sessionId="+literal(sid))
        db("DELETE FROM BroadcastLog WHERE sessionId="+literal(sid))
        db("DELETE FROM AuthState WHERE sessionId="+literal(sid))
        n = count("DELETE FROM Session WHERE id="+literal(dbid)
                  +" AND sessionId="+literal(sid)
                  +" AND status='LOGGED_OUT';SELECT ROW_COUNT();")
        if n != 1:
            raise RuntimeError("Sessão não foi removida; pendência permanece.")
        print("WA-AKG: removidos",msg,"mensagens e",contacts,"contatos.", flush=True)
    if count("SELECT COUNT(*) FROM Session WHERE sessionId="+literal(sid)):
        raise RuntimeError("WA-AKG ainda tem esta sessão; não finalizar EMECA.")
    finish = (
        "import json;"
        "from usuarioSec.sessao_whatsapp import sessao_atual_id,limpeza_historico_pendente;"
        "from usuarioSec.limpeza_historico_whatsapp import limpar_emeca_e_criar_sessao_nova;"
        "antiga="+repr(sid)+";"
        "assert limpeza_historico_pendente() and sessao_atual_id()==antiga;"
        "r=limpar_emeca_e_criar_sessao_nova(antiga);"
        "print('WA_RECUPERACAO:'+json.dumps({'finalizada':True}))"
    )
    if not django(finish, 120).get("finalizada"):
        raise RuntimeError("Django não confirmou finalização.")
    print("EMECA: pendência encerrada; sessão nova e isolada.")
    print("Mídias da sessão antiga no volume WA-AKG foram preservadas;")
    print("a remoção delas exige etapa separada e verificação por arquivo.")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--aplicar", action="store_true")
    p.add_argument("--confirmar", default="")
    args = p.parse_args()
    print("=== Recuperação P2028: exclusivamente sessão desvinculada ===")
    try:
        sid, dbid, total = preflight()
        print("Limpeza pendente: SIM; remoto:", "LOGGED_OUT" if dbid else "AUSENTE")
        print("Mensagens da sessão:",total)
        if not args.aplicar:
            print("SOMENTE LEITURA. Para aplicar: --aplicar --confirmar="+CONFIRM)
            return
        if args.confirmar != CONFIRM:
            raise RuntimeError("Confirmação explícita ausente; nada apagado.")
        backup_all()
        purge(sid, dbid)
        print("FIM. Nenhum boletim escolar foi apagado por esta recuperação.")
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print("INTERROMPIDO:",str(exc))
        print("Em interrupções após o primeiro lote, a pendência permanece.")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
