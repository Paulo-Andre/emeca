#!/usr/bin/env python3
"""Apenas compara contagens de boletins em backups SQLite do EMECA.

Nenhum arquivo é criado, regravado ou restaurado. Saída sem nomes de alunos.
"""
import json
import subprocess

CODE = r'''
import json
import sqlite3
from pathlib import Path
root=Path("/backups")
report={"caminho":"/srv/backups/emeca","arquivos":[]}
table="site_publico_boletimaluno"
entries=[]
if root.is_dir():
    for path in root.glob("**/*"):
        if path.is_file() and path.suffix.lower() in (".sqlite3",".sqlite",".db"):
            if len(path.relative_to(root).parts)>3:
                continue
            entries.append(path)
entries=sorted(entries,key=lambda p:p.stat().st_mtime,reverse=True)
report["encontrados"]=len(entries)
for path in entries[:60]:
    entry={"arquivo":str(path.relative_to(root)),"bytes":path.stat().st_size}
    try:
        with sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True,timeout=5) as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            if not exists:
                entry["estado"]="SEM_TABELA_BOLETIM"
            else:
                entry["estado"]="LEGIVEL"
                entry["total"]=db.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0]
                entry["periodo_3"]=db.execute('SELECT COUNT(*) FROM "'+table+'" WHERE periodo_id=?',(3,)).fetchone()[0]
    except (sqlite3.Error,OSError) as e:
        entry["estado"]="ERRO_"+type(e).__name__
    report["arquivos"].append(entry)
print("EMECA_BACKUPS_COMPARADOS:"+json.dumps(report,ensure_ascii=False))
'''

def main():
    print("=== Backups SQLite: comparação SOMENTE LEITURA ===")
    try:
        p=subprocess.run(
            ["docker","exec","emeca-web-1","python","-c",CODE],
            capture_output=True,text=True,timeout=35,check=False)
    except (subprocess.TimeoutExpired,OSError) as e:
        print("Consulta indisponível:",type(e).__name__)
        return
    if p.returncode:
        print("Consulta falhou com código",p.returncode,
              "(saída original não divulgada).")
        return
    for line in p.stdout.splitlines():
        if line.startswith("EMECA_BACKUPS_COMPARADOS:"):
            try:
                info=json.loads(line.split(":",1)[1])
            except ValueError:
                break
            print("Cópias SQLite identificadas:",info.get("encontrados",0))
            for row in info.get("arquivos",[]):
                name=str(row.get("arquivo",""))
                if not name or ".." in name or not all(
                    c.isascii() and (c.isalnum() or c in "._-/") for c in name
                ):
                    name="[nome ocultado]"
                print(name,"| estado:",row.get("estado"),
                      "| total boletins:",row.get("total","-"),
                      "| período 3:",row.get("periodo_3","-"))
            if info.get("encontrados",0)>60:
                print("Mostradas somente as 60 cópias mais recentes.")
            print("NENHUM ARQUIVO FOI RESTAURADO OU MODIFICADO.")
            return
    print("Resultado inconclusivo. Nenhum arquivo modificado.")

if __name__=="__main__":
    main()
