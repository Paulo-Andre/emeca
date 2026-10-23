#!/usr/bin/env python3
"""Fotografia de segurança do banco EMECA e auditoria anônima dos backups.

Executar no host via: python3 deploy/proteger_e_auditar_boletins.py
Somente leitura no banco principal; uma cópia consistente SQLite é gravada
em /srv/backups/emeca (montado como /backups no web). Não restaura, exclui,
sincroniza, envia mensagens ou interage com WhatsApp.
"""
import json
import subprocess

DJANGO = r"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from django.db import connection
from site_publico.models import PeriodoBoletim, BoletimAluno

out = {"modo": "copia_de_seguranca", "estado": "INICIADO"}
conf = connection.settings_dict
engine = str(conf.get("ENGINE") or "")
if engine != "django.db.backends.sqlite3":
    out.update(estado="ENGINE_NAO_SQLITE", engine=engine)
else:
    source = str(conf["NAME"])
    backup_dir = Path("/backups")
    if not backup_dir.is_dir():
        out.update(estado="DESTINO_NAO_DISPONIVEL")
    else:
        # SQLite online backup via conexão só-leitura é consistente com WAL.
        nome = "emeca-incidente-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".sqlite3"
        dest = backup_dir / nome
        try:
            origin = sqlite3.connect(Path(source).absolute().as_uri()+"?mode=ro", uri=True,timeout=10)
            target = sqlite3.connect(str(dest),timeout=10)
            try:
                origin.backup(target, pages=200, sleep=0.05)
                good = target.execute("PRAGMA quick_check").fetchone()
            finally:
                target.close()
                origin.close()
            os.chmod(dest,0o600)
            if not good or good[0] != "ok":
                out.update(estado="COPIA_NAO_VERIFICADA")
            else:
                out.update(estado="BACKUP_VERIFICADO", arquivo=nome, tamanho=dest.stat().st_size)
        except Exception as exc:
            out.update(estado="ERRO_BACKUP", classe=type(exc).__name__)
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass

    out["periodo_3_atual"] = (
        BoletimAluno.objects.filter(periodo_id=3).count()
        if PeriodoBoletim.objects.filter(pk=3).exists()
        else None
    )
    # Apenas arquivos SQLite legíveis, em um diretório restrito da escola.
    # Outros formatos de backup não são restaurados nem abertos.
    candidatos = sorted(
        (p for p in backup_dir.rglob("*") if p.is_file()
         and p.suffix.lower() in {".sqlite", ".sqlite3", ".db"}
         and not p.name.startswith("emeca-incidente-")),
        key=lambda p: p.stat().st_mtime, reverse=True
    )[:25] if backup_dir.is_dir() else []
    itens=[]
    for p in candidatos:
        try:
            uri=p.absolute().as_uri()+"?mode=ro"
            db=sqlite3.connect(uri, uri=True,timeout=3)
            try:
                table=db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='site_publico_boletimaluno'"
                ).fetchone()
                total=db.execute(
                    "SELECT COUNT(*) FROM site_publico_boletimaluno WHERE periodo_id=3"
                ).fetchone()[0] if table else None
                itens.append({"arquivo":p.name[:110], "periodo_3":total,
                              "bytes":p.stat().st_size})
            finally:
                db.close()
        except (sqlite3.Error, OSError):
            itens.append({"arquivo":p.name[:110],"periodo_3":"INACESSIVEL"})
    out["copias_existentes"]=itens

print("EMECA_AUDITORIA_BACKUP:" + json.dumps(out,ensure_ascii=False))
"""

def main():
    print("=== Proteção do banco EMECA e busca de cópias antigas ===")
    print("Nenhum dado escolar é exibido; não há exclusões ou restauração.")
    try:
        p=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",DJANGO],
            capture_output=True,text=True,timeout=90,check=False,
        )
    except (OSError,subprocess.TimeoutExpired) as exc:
        print("Cópia indisponível:",type(exc).__name__);return
    if p.returncode:
        print("Diagnóstico retornou código",p.returncode,
              "— saída técnica omitida por privacidade.");return
    for line in p.stdout.splitlines():
        if not line.startswith("EMECA_AUDITORIA_BACKUP:"):
            continue
        try: obj=json.loads(line.split(":",1)[1])
        except ValueError:break
        print("Estado:",obj.get("estado"))
        if obj.get("classe"):print("Falha:",obj["classe"])
        if obj.get("engine"):print("Banco:",obj["engine"])
        if obj.get("arquivo"):
            print("Cópia consistente:",obj["arquivo"],"tamanho (bytes):",obj.get("tamanho"))
            print("Armazenada em /srv/backups/emeca/ no mini PC.")
        print("Boletins atuais no período 3:",obj.get("periodo_3_atual"))
        antigos=obj.get("copias_existentes") or []
        if antigos:
            print("Outros arquivos SQLite encontrados (leitura somente):")
            for x in antigos:
                print("  ",x["arquivo"],"| período 3:",x.get("periodo_3","?"))
        else:
            print("Nenhuma outra cópia SQLite encontrada no diretório de backup.")
        print("Não foi restaurado, apagado ou reenviado nenhum dado.")
        return
    print("Nenhuma resposta reconhecida; cópia não confirmada.")

if __name__=="__main__":
    main()
