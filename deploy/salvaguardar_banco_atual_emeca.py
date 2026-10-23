#!/usr/bin/env python3
"""Snapshot consistente do SQLite EMECA, sem parar serviços ou restaurar nada.

Roda no host via Docker exec; cria backup com permissões restritas em /backups.
Não envia dados para redes e não imprime conteúdo ou localização do DB.
"""
import subprocess
import json
import os

CODE = r'''
import os, sqlite3, stat, json, time
from pathlib import Path
from django.conf import settings
db=settings.DATABASES["default"]
out={"tipo":db["ENGINE"].rsplit(".",1)[-1]}
if not db["ENGINE"].endswith("sqlite3"):
    out["status"]="NAO_SQLITE"
else:
    source=Path(str(db["NAME"]))
    destdir=Path("/backups")
    if not source.is_file() or not destdir.is_dir():
        out["status"]="CAMINHO_INDISPONIVEL"
    else:
        name="emeca-resguardo-incidente-"+time.strftime("%Y%m%d-%H%M%S")+".sqlite3"
        target=destdir/name
        src=None
        dst=None
        try:
            fd=os.open(str(target),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(fd)
            src=sqlite3.connect("file:"+str(source)+"?mode=ro",uri=True,timeout=30)
            dst=sqlite3.connect(str(target),timeout=30)
            src.backup(dst,pages=200,sleep=0.1)
            dst.commit()
            ok=dst.execute("PRAGMA quick_check").fetchone()[0]
            size=target.stat().st_size
            if ok!="ok" or size<4096:
                raise RuntimeError("BACKUP_NAO_VALIDADO")
            out.update({"status":"OK","nome":name,"bytes":size,"integridade":"OK"})
        except Exception as ex:
            out.update({"status":"FALHOU","classe":type(ex).__name__})
            # Cópia incompleta não deve parecer backup válido.
            try:
                if dst: dst.close()
                if src: src.close()
                target.unlink(missing_ok=True)
            except OSError: pass
        finally:
            if dst: dst.close()
            if src: src.close()
print("EMECA_SNAPSHOT_JSON:"+json.dumps(out))
'''

def main():
    print("=== Salvaguarda consistente do banco atual EMECA ===")
    print("Esta cópia preserva o estado ATUAL; não recupera por si só dados já excluídos.")
    try:
        result=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",CODE],
            capture_output=True,text=True,timeout=120,check=False
        )
    except (OSError,subprocess.TimeoutExpired) as e:
        print("Não foi possível fazer a cópia:",type(e).__name__)
        return
    if result.returncode:
        print("Não foi possível validar o backup (código",result.returncode,").")
        return
    for line in result.stdout.splitlines():
        if line.startswith("EMECA_SNAPSHOT_JSON:"):
            try: item=json.loads(line.split(":",1)[1])
            except ValueError: break
            if item.get("status")=="OK":
                print("Backup OK:",item["nome"],"| tamanho:",round(item["bytes"]/1024/1024,2),"MiB | integridade:",item["integridade"])
                print("Destino: /srv/backups/emeca/ (no mini PC); arquivo restrito ao administrador.")
            else:
                print("Backup não criado:",item.get("status"),item.get("classe",""))
            return
    print("Não foi possível verificar a resposta do banco de dados.")

if __name__=="__main__":
    main()
