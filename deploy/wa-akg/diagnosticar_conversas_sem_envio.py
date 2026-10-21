#!/usr/bin/env python3
"""Diagnóstico SOMENTE LEITURA de carregamento de conversas no EMECA.
Sem disparos, sem mudanças de estado, sem revelar JIDs, contatos, mensagens,
tokens, corpo da API ou configuração da conta.
"""
import json
import subprocess

SNIPPET = r'''
import json
from urllib.parse import quote
from usuarioSec.whatsapp_gateway import obter_sessao, _request, WhatsAppGatewayError
from usuarioSec.sessao_whatsapp import sessao_atual_id
from usuarioSec.models import (
    EnvioBoletimWhatsApp, ItemEnvioBoletimWhatsApp, LeituraChatWhatsApp
)
from django.db.models import Count
out={"fase":"iniciada"}
try:
    r=obter_sessao()
    data=r.get("data") if isinstance(r,dict) else None
    data=data if isinstance(data,dict) else {}
    out["sessao_status"]=str(data.get("status") or (r.get("status") if isinstance(r,dict) else "") or "INDEFINIDO").upper()
except WhatsAppGatewayError as exc:
    out["sessao_status"]="ERRO_GATEWAY"
    out["sessao_http"]=exc.status_code or 0
except Exception as exc:
    out["sessao_status"]="ERRO_LOCAL"
    out["sessao_excecao"]=type(exc).__name__
try:
    sid=quote(sessao_atual_id(),safe="")
    r=_request("GET", f"chat/{sid}?limit=5")
    data=r.get("data") if isinstance(r,dict) else None
    out["api_raw_ok"]=bool(isinstance(r,dict) and r.get("status") is True)
    out["api_raw_tipo"]=type(data).__name__
    out["api_raw_quantidade"]=len(data) if isinstance(data,list) else -1
    meta=r.get("meta") if isinstance(r,dict) else None
    out["api_raw_cursor"]=bool(meta.get("nextBefore")) if isinstance(meta,dict) else False
except WhatsAppGatewayError as exc:
    out["api_raw_ok"]=False
    out["api_raw_http"]=exc.status_code or 0
except Exception as exc:
    out["api_raw_ok"]=False
    out["api_raw_excecao"]=type(exc).__name__

out["lotes_pendentes"]=EnvioBoletimWhatsApp.objects.filter(status__in=["PENDENTE","PROCESSANDO"]).count()
out["mensagens_nao_lidas_registradas"]=LeituraChatWhatsApp.objects.count()
out["fase"]="concluida"
print("EMECA_DIAG_CHAT:"+json.dumps(out,ensure_ascii=False))
'''

def main():
    print("=== DIAGNÓSTICO DE CONVERSAS (sem mensagens e sem dados pessoais) ===")
    try:
        p=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",SNIPPET],
            capture_output=True,text=True,timeout=30,check=False
        )
    except subprocess.TimeoutExpired:
        print("EMECA Django: TEMPO ESGOTADO consultando sessão ou página inicial de chats.")
        return
    except OSError as exc:
        print("Django indisponível:",type(exc).__name__)
        return
    if p.returncode:
        print("Django shell retornou erro (código)",p.returncode,
              "— detalhe oculto para proteger dados da escola.")
        return
    report=None
    for line in p.stdout.splitlines():
        if line.startswith("EMECA_DIAG_CHAT:"):
            try: report=json.loads(line.split(":",1)[1])
            except json.JSONDecodeError: pass
    if not isinstance(report,dict):
        print("Sem relatório de diagnóstico — nenhuma alteração feita.")
        return
    for k in ("sessao_status","sessao_http","sessao_excecao",
              "api_raw_ok","api_raw_http","api_raw_excecao","api_raw_tipo",
              "api_raw_quantidade","api_raw_cursor","lotes_pendentes",
              "mensagens_nao_lidas_registradas"):
        if k in report:
            print(k+":",report[k])
    print("A contagem da API mede somente a resposta inicial e não altera o histórico.")
    print("=== STATUS DOS CONTÊINERES ===")
    q=subprocess.run(
        ["docker","ps","--format","{{.Names}} {{.Status}}",
         "--filter","name=wa-akg-app","--filter","name=emeca-web-1"],
        capture_output=True,text=True,timeout=10,check=False
    )
    if q.returncode==0:
        for line in q.stdout.splitlines():
            # Nome e uptime somente. Nenhum dado pessoal.
            print(line[:120])
    print("SEM REINÍCIO, SEM ENVIO, SEM MUDANÇAS NOS BANCOS.")

if __name__=="__main__":
    main()
