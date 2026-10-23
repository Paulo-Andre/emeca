#!/usr/bin/env python3
"""Triagem sem alterações: conectividade WA-AKG e cópias de banco EMECA.

- Não apaga dados, não reinicia contêineres, não cria sessão.
- Não divulga contatos, mensagens, boletins, tokens ou nomes de arquivos privados.
- Apenas consultas GET/TCP e leitura de metadados de backups.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import subprocess

def run(args, timeout=35):
    try:
        return subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

DJANGO = r"""
import json, socket, os
from urllib.parse import urlparse
from django.conf import settings
from usuarioSec.models import SessaoWhatsAppAtiva
from usuarioSec.sessao_whatsapp import sessao_atual_id
from usuarioSec.whatsapp_gateway import obter_sessao, WhatsAppGatewayError
out={}
info=urlparse(settings.WA_AKG_BASE_URL)
out["gateway_configurado"]=bool(info.scheme and info.hostname)
out["esquema"]=info.scheme if info.scheme in ("http","https") else "invalido"
out["porta"]=info.port or (443 if info.scheme=="https" else 80)
out["destino_tipo"]="host.docker.internal" if info.hostname=="host.docker.internal" else ("local" if info.hostname in ("localhost","127.0.0.1") else "outro")
out["dns"]="NAO_CONSULTADO"
out["tcp"]="NAO_CONSULTADO"
if info.hostname:
    try:
        socket.getaddrinfo(info.hostname,out["porta"])
        out["dns"]="OK"
        try:
            with socket.create_connection((info.hostname,out["porta"]),timeout=3):
                out["tcp"]="OK"
        except Exception as e:
            out["tcp"]=type(e).__name__
    except Exception as e:
        out["dns"]=type(e).__name__
try:
    sessao=obter_sessao()
    dado=sessao.get("data") if isinstance(sessao,dict) else {}
    dado=dado if isinstance(dado,dict) else {}
    out["obter_sessao"]="OK"
    out["estado_remoto"]=str(dado.get("status") or "SEM_STATUS")
except WhatsAppGatewayError as e:
    out["obter_sessao"]="FALHA"
    out["gateway_http"]=e.status_code or 0
    cause=e.__cause__
    out["erro_causa"]=type(getattr(cause,"reason",None)).__name__ if cause else "Sem_causa"
except Exception as e:
    out["obter_sessao"]=type(e).__name__
out["limpeza_pendente"]=bool(SessaoWhatsAppAtiva.objects.filter(chave="secretaria",limpeza_pendente=True).exists())
out["sessao_local_registrada"]=SessaoWhatsAppAtiva.objects.filter(chave="secretaria").exists()
out["motor_bd"]=settings.DATABASES["default"]["ENGINE"].split(".")[-1]
out["caminho_bd_padrao"] = str(settings.DATABASES["default"]["NAME"]).startswith("/data/")
print("DIAG_WA_SAFE:"+json.dumps(out,ensure_ascii=False))
"""

def container_summary(name):
    p=run(["docker","inspect","--format",
           "{{.State.Status}}|{{.RestartCount}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}sem_health{{end}}",
           name],12)
    if p is None or p.returncode:
        print("Contêiner",name,": não encontrado/indisponível")
        return
    fields=p.stdout.strip().split("|")
    if len(fields)==3:
        print("Contêiner",name,": estado",fields[0],"; reinícios",fields[1],"; health",fields[2])

def backup_inventory():
    print("=== Cópias de segurança (somente inventário) ===")
    root=Path("/srv/backups/emeca")
    if not root.is_dir():
        print("/srv/backups/emeca: diretório ausente/sem acesso")
        return
    files=[]
    suffixes=(".sqlite3",".sqlite",".db",".bak",".dump",".sql",".gz",".zip",".tar",".tgz",".backup")
    try:
        for path in root.rglob("*"):
            if len(files)>=5000: break
            if path.is_file() and (path.name.lower().endswith(suffixes) or "backup" in path.name.lower()):
                stat=path.stat()
                if stat.st_size>0:
                    files.append((stat.st_mtime,stat.st_size,path))
    except (PermissionError,OSError) as e:
        print("Inventário parcial:",type(e).__name__)
    files.sort(reverse=True)
    print("Arquivos de backup compatíveis encontrados:",len(files))
    for time_value,size,path in files[:15]:
        print("  Modificação:",datetime.fromtimestamp(time_value).strftime("%Y-%m-%d %H:%M"),
              "| tamanho:",round(size/1024/1024,2),"MiB",
              "| tipo:",path.suffix.lower() or "sem_extensao")
    if not files:
        print("Nenhuma cópia identificada nesta pasta. Pode haver backups em outro local.")

def main():
    print("=== EMECA: triagem de recuperação sem alteração ===")
    for name in ("emeca-web-1","emeca-whatsapp-worker-1","wa-akg-app","wa-akg-db"):
        container_summary(name)
    p=run(["docker","exec","emeca-web-1","python","manage.py","shell","-c",DJANGO],40)
    if p is None:
        print("Diagnóstico Django: tempo esgotado/execução indisponível")
    elif p.returncode:
        print("Diagnóstico Django falhou, código",p.returncode,
              "(saída bruta omitida por privacidade)")
    else:
        for line in p.stdout.splitlines():
            if line.startswith("DIAG_WA_SAFE:"):
                try: obj=json.loads(line[len("DIAG_WA_SAFE:"):])
                except ValueError: break
                print("=== Conexão do EMECA ao WA-AKG ===")
                for k in ("gateway_configurado","esquema","porta","destino_tipo",
                          "dns","tcp","obter_sessao","gateway_http","erro_causa",
                          "estado_remoto","limpeza_pendente","sessao_local_registrada",
                          "motor_bd","caminho_bd_padrao"):
                    if k in obj: print(k+":",obj[k])
                break
            else: continue
    backup_inventory()
    print("Concluído: nenhuma exclusão, migração, restauração ou reconexão executada.")

if __name__=="__main__":
    main()
