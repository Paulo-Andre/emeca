#!/usr/bin/env python3
"""Diagnóstico SOMENTE LEITURA de WA-AKG, MySQL e backups do EMECA.

Nunca reinicia, remove, desvincula, faz login ou transmite mensagens.
Não imprime credenciais, sessionIds, JIDs, conteúdo de mensagens ou nomes.
"""
import json
import subprocess

def run(argv, timeout=15):
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

def main():
    print("=== Integridade WhatsApp e escola | somente leitura ===")
    for name in ("wa-akg-app", "wa-akg-db", "emeca-web-1", "emeca-whatsapp-worker-1"):
        p = run(["docker", "inspect", "--format",
                 "{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}", name], 8)
        if p is None or p.returncode:
            print(name, "não pôde ser inspecionado")
            continue
        fields = p.stdout.strip().split("|")
        if len(fields) == 3:
            print(name, "estado:", fields[0], "reinicios:", fields[1], "OOM:", fields[2])

    p=run(["docker", "stats", "--no-stream", "--format",
           "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}", "wa-akg-app", "wa-akg-db"], 15)
    if p and p.returncode == 0:
        for line in p.stdout.splitlines():
            cols=line.split("|")
            if len(cols)==3:
                print(cols[0], "CPU:", cols[1], "Memória:", cols[2])

    # Consulta HTTP local de baixo custo, sem autenticação nem conteúdo de resposta.
    p=run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
           "--connect-timeout", "2", "--max-time", "5",
           "http://127.0.0.1:3100/"], 8)
    print("WA-AKG interface HTTP:",
          (p.stdout.strip() if p and p.returncode==0 else "SEM_RESPOSTA_5S"))

    # SQL somente SELECT. Segredos são lidos da variável de ambiente no DB,
    # sem passar senha como argumento nem expor o resultado bruto.
    sql=(
        "SELECT 'SESSION_TOTAL', COUNT(*) FROM Session;"
        "SELECT CONCAT('STATUS_',status),COUNT(*) FROM Session GROUP BY status;"
        "SELECT 'MESSAGES_TOTAL', COUNT(*) FROM Message;"
        "SELECT 'AUTH_ROWS', COUNT(*) FROM AuthState;"
        "SELECT 'THREADS_RUNNING', VARIABLE_VALUE FROM performance_schema.global_status "
        "WHERE VARIABLE_NAME='Threads_running';"
    )
    shell = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s -uroot "$MYSQL_DATABASE" -e ' + "'" + sql.replace("'", "'\\''") + "'"
    p=run(["docker", "exec", "wa-akg-db", "sh", "-c", shell], 22)
    if p is None or p.returncode:
        print("WA-AKG MySQL: INDISPONIVEL / CONSULTA DEMORADA")
    else:
        print("WA-AKG MySQL: consulta concluída")
        for line in p.stdout.splitlines():
            cols=line.split("\t")
            if len(cols)==2 and cols[0].startswith(("SESSION_TOTAL","STATUS_","MESSAGES_TOTAL","AUTH_ROWS","THREADS_RUNNING")) and cols[1].strip().isdigit():
                print(" ",cols[0],cols[1])

    p=run(["docker", "exec", "emeca-web-1", "python", "manage.py", "shell", "-c", r'''
import os,json,sqlite3
from pathlib import Path
from django.db import connection
from site_publico.models import BoletimAluno
result={"engine":connection.settings_dict.get("ENGINE","").split(".")[-1],
        "current_bulletins":BoletimAluno.objects.count(),"backups":[]}
root=Path("/backups")
if root.exists():
    for f in sorted(root.glob("**/*"),key=lambda x: x.stat().st_mtime if x.exists() else 0,reverse=True):
        if len(result["backups"])>=12:break
        if not f.is_file() or f.suffix.lower() not in {".db",".sqlite",".sqlite3"}:
            continue
        entry={"size_kb":round(f.stat().st_size/1024)}
        try:
            uri="file:"+str(f)+"?mode=ro&immutable=1"
            db=sqlite3.connect(uri,uri=True,timeout=1)
            try:
                entry["bulletins"]=db.execute("SELECT COUNT(*) FROM site_publico_boletimaluno").fetchone()[0]
            finally: db.close()
        except (sqlite3.Error,OSError):
            entry["bulletins"]="nao_lido"
        # Nunca exibir caminhos do disco, nomes de backups, nem nomes de alunos.
        result["backups"].append(entry)
print("BACKUP_DIAG_JSON:"+json.dumps(result,ensure_ascii=False))
'''], 30)
    if p is None or p.returncode:
        print("EMECA /backups: consulta indisponível")
    else:
        for line in p.stdout.splitlines():
            if line.startswith("BACKUP_DIAG_JSON:"):
                try:r=json.loads(line.split(":",1)[1])
                except ValueError:continue
                print("Banco do EMECA:",r.get("engine"),"boletins atuais:",r.get("current_bulletins"))
                print("Arquivos SQLite de backup identificados:",len(r.get("backups",[])))
                for i,x in enumerate(r.get("backups",[]),1):
                    print("  candidato",i,"tamanho(KB):",x.get("size_kb"),
                          "boletins:",x.get("bulletins"))
                break

    print("FINAL: nenhuma conexão alterada e nenhum dado excluído.")

if __name__=="__main__":
    main()
