#!/usr/bin/env python3
"""Preserva snapshot consistente e audita boletins/sessão WhatsApp sem modificar dados.

Executar no host: python3 deploy/auditar_incidente_boletins.py
Somente leitura do banco de produção; escreve exclusivamente cópia em /backups.
Nunca envia mensagens, apaga documentos ou realiza restauração.
"""
import json
import subprocess

DJANGO = r'''
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from django.conf import settings
from django.db.models import Count
from site_publico.models import PeriodoBoletim, BoletimAluno, AlunoBoletim, NotaBoletim
from usuarioSec.models import (
    EnvioBoletimWhatsApp, ItemEnvioBoletimWhatsApp, SessaoWhatsAppAtiva,
)

rel = {
    "snapshot": "NAO_TENTADO",
    "banco": settings.DATABASES["default"]["ENGINE"].rsplit(".",1)[-1],
    "periodos": list(
        PeriodoBoletim.objects.order_by("pk").annotate(
            quantidade=Count("boletins", distinct=True)
        ).values("pk", "publicado", "quantidade")
    ),
    "total_boletins": BoletimAluno.objects.count(),
    "total_perfis_alunos": AlunoBoletim.objects.count(),
    "total_notas": NotaBoletim.objects.count(),
    "total_lotes_whatsapp": EnvioBoletimWhatsApp.objects.count(),
    "total_itens_envio": ItemEnvioBoletimWhatsApp.objects.count(),
    "limpeza_whatsapp_pendente": bool(
        SessaoWhatsAppAtiva.objects.filter(
            chave="secretaria", limpeza_pendente=True
        ).exists()
    ),
    "sessao_atual_registrada": bool(
        SessaoWhatsAppAtiva.objects.filter(chave="secretaria").exists()
    ),
}
backup_dir=Path("/backups")
if rel["banco"]=="sqlite3" and backup_dir.is_dir():
    src = Path(settings.DATABASES["default"]["NAME"]).resolve()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename="emeca-snapshot-incidente-"+stamp+".sqlite3"
    destino=backup_dir/filename
    temporario=backup_dir/("."+filename+".partial")
    try:
        if destino.exists() or temporario.exists():
            raise FileExistsError("Nome da cópia já reservado.")
        os.umask(0o077)
        source=sqlite3.connect("file:"+str(src)+"?mode=ro",uri=True,timeout=15)
        try:
            target=sqlite3.connect(str(temporario),timeout=15)
            try:
                source.backup(target,pages=100,sleep=0.10)
                integridade=target.execute("PRAGMA quick_check").fetchone()
            finally:
                target.close()
        finally:
            source.close()
        if not integridade or integridade[0]!="ok":
            raise sqlite3.DatabaseError("Cópia não passou no quick_check")
        os.replace(temporario,destino)
        os.chmod(destino,0o600)
        rel["snapshot"]="OK"
        rel["snapshot_arquivo_host"]="/srv/backups/emeca/"+filename
        rel["snapshot_bytes"]=destino.stat().st_size
    except Exception as exc:
        rel["snapshot"]="FALHOU"
        rel["snapshot_erro_classe"]=type(exc).__name__
elif rel["banco"]!="sqlite3":
    rel["snapshot"]="BANCO_NAO_SQLITE_NAO_COPIADO"
else:
    rel["snapshot"]="DIRETORIO_BACKUP_NAO_MONTADO"

# Inventário somente de cópias anteriores. Não abre qualquer banco atual
# senão pela API de leitura; arquivos compactados não são restaurados.
arquivos=[]
if backup_dir.is_dir():
    for base,dirs,nomes in os.walk(backup_dir,followlinks=False):
        prof=len(Path(base).relative_to(backup_dir).parts)
        if prof>=4:
            dirs[:]=[]
        for nome in nomes:
            if not nome.lower().endswith((".sqlite3",".sqlite",".db",".bak",".zip",".sql",".gz")):
                continue
            arquivo=Path(base)/nome
            if not arquivo.is_file() or arquivo.is_symlink():
                continue
            try:
                arquivos.append((arquivo.stat().st_mtime,arquivo))
            except OSError:
                pass

candidatas=[]
for _,arquivo in sorted(arquivos,reverse=True)[:25]:
    if arquivo.name.startswith(".") or arquivo.name.startswith("emeca-snapshot-incidente-"):
        continue
    linha={"arquivo":str(arquivo.relative_to(backup_dir))[:100]}
    if arquivo.suffix.lower() in {".sqlite3",".sqlite",".db"}:
        try:
            con=sqlite3.connect("file:"+str(arquivo)+"?mode=ro",uri=True,timeout=1)
            try:
                existe=con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='site_publico_boletimaluno'"
                ).fetchone()
                if existe:
                    linha["boletins"]=con.execute(
                        "SELECT COUNT(*) FROM site_publico_boletimaluno"
                    ).fetchone()[0]
                    linha["por_periodo"]=[
                        {"id":int(p),"quantidade":int(q)}
                        for p,q in con.execute(
                            "SELECT periodo_id,COUNT(*) FROM site_publico_boletimaluno GROUP BY periodo_id"
                        ).fetchall()
                    ]
            finally:
                con.close()
        except (sqlite3.Error,OSError):
            linha["leitura"]="INDISPONIVEL"
    else:
        linha["tipo"]="ARQUIVO_COMPACTADO_OU_EXPORTADO"
    candidatas.append(linha)
rel["candidatas_backup"]=candidatas[:12]
print("EMECA_AUDITORIA_INCIDENTE:"+json.dumps(rel,ensure_ascii=False))
'''

def main():
    print("=== INCIDENTE EMECA — preservação e auditoria sem exclusões ===")
    try:
        p=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",DJANGO],
            capture_output=True,text=True,check=False,timeout=100
        )
    except subprocess.TimeoutExpired:
        print("Tempo excedido. Não tente restauração sem identificar o estado do snapshot.")
        return
    except OSError as exc:
        print("Falha de acesso ao Docker:",type(exc).__name__)
        return
    if p.returncode:
        print("Consulta terminou com erro técnico. Código:",p.returncode)
        print("Saída bruta omitida para proteger dados da escola.")
        return
    for line in p.stdout.splitlines():
        if not line.startswith("EMECA_AUDITORIA_INCIDENTE:"):
            continue
        try:
            r=json.loads(line.split(":",1)[1])
        except (ValueError,TypeError):
            break
        print("Banco:",r.get("banco"))
        print("Snapshot consistente:",r.get("snapshot"))
        if r.get("snapshot_erro_classe"):
            print("Falha do snapshot:",r["snapshot_erro_classe"])
        if r.get("snapshot_arquivo_host"):
            print("Caminho da cópia:",r["snapshot_arquivo_host"])
            print("Tamanho (bytes):",r.get("snapshot_bytes"))
        print("Boletins atuais:",r.get("total_boletins"))
        print("Perfis de aluno:",r.get("total_perfis_alunos"),
              "| Lançamentos de notas:",r.get("total_notas"))
        for t in r.get("periodos",[]):
            print("Período id:",t.get("pk"),
                  "| Publicado:",t.get("publicado"),
                  "| Boletins:",t.get("quantidade"))
        print("Lotes WhatsApp:",r.get("total_lotes_whatsapp"),
              "| Itens de envio:",r.get("total_itens_envio"))
        print("Limpeza WhatsApp pendente:",r.get("limpeza_whatsapp_pendente"))
        print("Sessão WhatsApp registrada:",r.get("sessao_atual_registrada"))
        print("Cópias anteriores encontradas (sem dados pessoais):")
        for b in r.get("candidatas_backup",[]):
            s=b.get("arquivo","?")
            print(" ",s,"| boletins:",b.get("boletins","não inspecionado"))
            for c in b.get("por_periodo",[])[:12]:
                print("   id:",c["id"],"boletins:",c["quantidade"])
        print("NENHUMA EXCLUSÃO, RESTAURAÇÃO, LIMPEZA OU ENVIO EXECUTADO.")
        return
    print("Resultado de auditoria não reconhecido. Saída técnica omitida.")

if __name__=="__main__":
    main()
