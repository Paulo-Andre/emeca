#!/usr/bin/env python3
"""Diagnóstico não destrutivo: GET WhatsApp, situação de limpeza e contagens.
Sem destinatários, senhas, PDFs, mensagens, nomes ou JIDs nos resultados.
Não tenta enviar, apagar, desconectar ou reconectar o WA-AKG.
"""
import json
import subprocess

CODE = r"""
import json
import traceback
from django.db import transaction
from django.contrib.auth import get_user_model
from django.test import Client
from django.conf import settings
from django.db.models import Count
from site_publico.models import PeriodoBoletim, BoletimAluno
from usuarioSec.models import EnvioBoletimWhatsApp, ItemEnvioBoletimWhatsApp, SessaoWhatsAppAtiva
from usuarioSec.sessao_whatsapp import limpeza_historico_pendente
from usuarioSec.whatsapp_gateway import obter_sessao, WhatsAppGatewayError, configurado

out = {"modo": "somente_leitura", "pagina": "/whatsapp/"}
out["boletins_total"] = BoletimAluno.objects.count()
out["periodos"] = list(
    PeriodoBoletim.objects.order_by("pk").values("pk", "publicado")
    .annotate(qtde_boletins=Count("boletins", distinct=True))
)
out["itens_envio_total"] = ItemEnvioBoletimWhatsApp.objects.count()
out["lotes_whatsapp_total"] = EnvioBoletimWhatsApp.objects.count()
out["limpeza_pendente"] = limpeza_historico_pendente()
out["registro_de_sessao"] = SessaoWhatsAppAtiva.objects.filter(chave="secretaria").exists()
if configurado():
    try:
        resposta = obter_sessao()
        data = resposta.get("data") if isinstance(resposta,dict) else {}
        data = data if isinstance(data,dict) else {}
        out["gateway_status"] = str(data.get("status") or "INDEFINIDO").upper()
    except WhatsAppGatewayError as e:
        out["gateway_status"] = "ERRO_HTTP"
        out["gateway_http"] = e.status_code or 0
        # Identificar falha de rede sem revelar URL, IP, senha ou corpo HTTP.
        causa = getattr(e, "__cause__", None)
        out["gateway_causa"] = type(causa).__name__ if causa else "NAO_INFORMADA"
        motivo = getattr(causa, "reason", None)
        if motivo is not None:
            out["gateway_motivo"] = type(motivo).__name__
    except Exception as e:
        out["gateway_status"] = "ERRO_TECNICO"
        out["gateway_erro_classe"] = type(e).__name__
else:
    out["gateway_status"] = "NAO_CONFIGURADO"

with transaction.atomic():
    try:
        user = get_user_model().objects.filter(
            is_active=True,is_superuser=True
        ).order_by("pk").first()
        if not user:
            out["teste_pagina"] = "SEM_ADMIN_PARA_TESTE"
        else:
            settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
            client = Client(raise_request_exception=True)
            client.force_login(user)
            response = client.get("/whatsapp/", HTTP_HOST="testserver")
            out["teste_pagina"] = "HTTP"
            out["http_status"] = response.status_code
    except Exception as e:
        out["teste_pagina"] = "EXCECAO"
        out["erro_classe"] = type(e).__name__
        stack = traceback.extract_tb(e.__traceback__)
        frames = [f for f in stack if "/app/" in f.filename and "site-packages" not in f.filename]
        frame = frames[-1] if frames else (stack[-1] if stack else None)
        if frame:
            out["erro_arquivo"] = frame.filename.rsplit("/",1)[-1]
            out["erro_funcao"] = frame.name
            out["erro_linha"] = frame.lineno
    finally:
        transaction.set_rollback(True)
print("EMECA_DIAGNOSTICO_SEGURO:" + json.dumps(out,ensure_ascii=False))
"""

def main():
    print("=== Diagnóstico EMECA: WhatsApp 500, limpeza e boletins ===")
    print("Somente GET e consultas ao banco; transação de teste será revertida.")
    try:
        p = subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",CODE],
            capture_output=True,text=True,timeout=45,check=False,
        )
    except subprocess.TimeoutExpired:
        print("Teste excedeu 45 segundos: possível lentidão/timeout na rota.")
        return
    except OSError as exc:
        print("Não foi possível conectar ao contêiner:",type(exc).__name__)
        return
    if p.returncode:
        print("Diagnóstico Django retornou código",p.returncode,
              "(stdout e erros técnicos ocultados por privacidade).")
        return
    for line in p.stdout.splitlines():
        if line.startswith("EMECA_DIAGNOSTICO_SEGURO:"):
            try:
                report=json.loads(line.split(":",1)[1])
            except ValueError:
                break
            print("Página /whatsapp/:",report.get("teste_pagina"),
                  report.get("http_status",""))
            if report.get("erro_classe"):
                print("Falha técnica:",report.get("erro_classe"),
                      "arquivo:",report.get("erro_arquivo","-"),
                      "função:",report.get("erro_funcao","-"),
                      "linha:",report.get("erro_linha","-"))
            print("WA-AKG:",report.get("gateway_status"),
                  "HTTP:",report.get("gateway_http","-"),
                  "causa:",report.get("gateway_causa","-"),
                  "tipo de falha:",report.get("gateway_motivo","-"))
            print("Limpeza WhatsApp pendente:",report.get("limpeza_pendente"))
            print("Registro de sessão existente:",report.get("registro_de_sessao"))
            print("Períodos e números de boletins (sem dados pessoais):")
            for periodo in report.get("periodos",[]):
                print("  Periodo id:",periodo.get("pk"),
                      "publicado:",periodo.get("publicado"),
                      "boletins:",periodo.get("qtde_boletins"))
            print("Total de boletins:",report.get("boletins_total"))
            print("Total de lotes WhatsApp:",report.get("lotes_whatsapp_total"))
            print("Total de itens de lote:",report.get("itens_envio_total"))
            print("Fim: nenhuma exclusão, conexão, envio ou alteração gravada.")
            return
    print("Diagnóstico sem formato reconhecido; resultados brutos omitidos.")

if __name__=="__main__":
    main()
