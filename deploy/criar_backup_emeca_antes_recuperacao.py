#!/usr/bin/env python3
"""Cópia consistente do SQLite atual, sem modificar dados da escola.

A cópia fica SOMENTE no diretório de backups já montado do EMECA
(/backups no contêiner = /srv/backups/emeca no mini-PC).
Não apaga, renomeia, restaura nem corrige tabelas.
"""
import json
import subprocess

CODE = r'''
import os, json, sqlite3
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote
from django.conf import settings

report={"seguro":True}
db=settings.DATABASES["default"]
if db.get("ENGINE")!="django.db.backends.sqlite3":
    report["status"]="BANCO_NAO_SQLITE"
else:
    src=Path(db["NAME"])
    base=Path("/backups")
    if not src.is_file():
        report["status"]="BANCO_NAO_LOCALIZADO"
    elif not base.is_dir():
        report["status"]="DIRETORIO_BACKUP_NAO_MONTADO"
    else:
        if not os.access(base, os.W_OK):
            report["status"]="DIRETORIO_BACKUP_SEM_PERMISSAO"
        else:
            utc=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            dest=base / ("emeca_antes_recuperacao_boletins_"+utc+".sqlite3")
            fd=None
            try:
                fd=os.open(dest, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
                os.close(fd)
                fd=None
                uri="file:"+quote(str(src),safe="/")+"?mode=ro"
                with sqlite3.connect(uri,uri=True,timeout=30) as original:
                    with sqlite3.connect(str(dest),timeout=30) as copia:
                        original.backup(copia,pages=256,sleep=0.1)
                        check=copia.execute("PRAGMA quick_check").fetchone()
                        if check is None or check[0]!="ok":
                            raise RuntimeError("integridade")
                os.chmod(dest,0o600)
                report["status"]="BACKUP_OK"
                report["arquivo"]=dest.name
                report["bytes"]=dest.stat().st_size
                report["integridade"]="OK"
            except Exception as e:
                report["status"]="FALHA_BACKUP"
                report["classe"]=type(e).__name__
                try: dest.unlink(missing_ok=True)
                except Exception: pass
            finally:
                if fd is not None: os.close(fd)
print("EMECA_BACKUP_CONFERIDO:"+json.dumps(report))
'''

def main():
    print("=== Proteção de dados: cópia do banco EMECA ===")
    print("Apenas uma cópia consistente. Não altera os dados originais.")
    try:
        r=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",CODE],
            text=True,capture_output=True,timeout=120,check=False,
        )
    except subprocess.TimeoutExpired:
        print("Tempo esgotado. Confirme espaço e backup antes de continuar.")
        return
    except OSError as e:
        print("Docker indisponível:",type(e).__name__)
        return
    if r.returncode:
        print("Comando de backup falhou com código",r.returncode,
              "— saída técnica oculta por privacidade.")
        return
    for line in r.stdout.splitlines():
        if not line.startswith("EMECA_BACKUP_CONFERIDO:"):
            continue
        try:
            report=json.loads(line.split(":",1)[1])
        except ValueError:
            break
        print("Resultado:",report.get("status"))
        if report.get("status")=="BACKUP_OK":
            print("Arquivo no servidor: /srv/backups/emeca/"+report.get("arquivo",""))
            print("Tamanho em bytes:",report.get("bytes"))
            print("Verificação de integridade:",report.get("integridade"))
            print("Permissão restrita: 600")
        else:
            print("Detalhe técnico (classe):",report.get("classe","—"))
            print("Nenhuma exclusão, limpeza ou restauração executada.")
        return
    print("Formato do relatório inesperado, dados técnicos omitidos.")

if __name__=="__main__":
    main()
