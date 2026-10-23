#!/usr/bin/env python3
"""Diagnóstico não destrutivo: serviço WA-AKG, acesso pelo EMECA e limpeza.

NÃO envia mensagens, não desconecta, não reinicia, não remove dados.
Não imprime números, nomes, IDs de sessão, URLs, tokens, mensagens ou logs.
"""
import json
import subprocess


def run(args, timeout=20):
    try:
        return subprocess.run(
            args, text=True, capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        print("TEMPO_ESGOTADO:", args[0])
        return None
    except OSError as exc:
        print("FALHA_LOCAL:", type(exc).__name__)
        return None


DJANGO = r'''
import json
import socket
from urllib.parse import urlsplit
from django.conf import settings
from usuarioSec.models import EnvioBoletimWhatsApp, SessaoWhatsAppAtiva
from usuarioSec.whatsapp_gateway import obter_sessao, WhatsAppGatewayError

out = {}
registrada = SessaoWhatsAppAtiva.objects.filter(chave="secretaria").first()
out["sessao_local_configurada"] = bool(registrada)
out["limpeza_pendente"] = bool(registrada and registrada.limpeza_pendente)
out["lotes_ativos"] = EnvioBoletimWhatsApp.objects.filter(
    status__in=["PENDENTE","PROCESSANDO"]
).count()
url = urlsplit(settings.WA_AKG_BASE_URL or "")
out["url_gateway_configurada"] = bool(url.hostname)
if url.hostname:
    try:
        port = url.port or (443 if url.scheme == "https" else 80)
        with socket.create_connection((url.hostname, port), timeout=3):
            out["acesso_tcp"] = "OK"
    except Exception as exc:
        out["acesso_tcp"] = type(exc).__name__
try:
    resposta = obter_sessao()
    dados = resposta.get("data") if isinstance(resposta, dict) else {}
    dados = dados if isinstance(dados, dict) else {}
    out["consulta_sessao"] = "OK"
    out["status_remoto"] = str(dados.get("status") or "SEM_STATUS").upper()
except WhatsAppGatewayError as exc:
    out["consulta_sessao"] = "FALHA"
    out["status_http"] = int(exc.status_code or 0)
    causa = getattr(exc, "__cause__", None)
    out["classe_causa"] = type(causa).__name__ if causa else "NAO_INFORMADA"
except Exception as exc:
    out["consulta_sessao"] = "ERRO"
    out["classe_causa"] = type(exc).__name__
print("WA_EMECA_DIAG:" + json.dumps(out, ensure_ascii=False))
'''


def main():
    print("=== WA-AKG: diagnóstico seguro de indisponibilidade ===")
    for nome in ("wa-akg-app", "wa-akg-db", "emeca-web-1", "emeca-whatsapp-worker-1"):
        p = run([
            "docker", "inspect", "--format",
            "{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}",
            nome,
        ], timeout=9)
        if p is None or p.returncode:
            print(nome, "não encontrado ou indisponível")
            continue
        partes = p.stdout.strip().split("|")
        if len(partes) == 3:
            print(nome, "estado:", partes[0], "reinícios:", partes[1],
                  "OOM:", partes[2])
    p = run([
        "docker", "stats", "--no-stream", "--format",
        "{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}",
        "wa-akg-app",
    ], timeout=14)
    if p is not None and p.returncode == 0:
        for linha in p.stdout.splitlines()[:1]:
            partes = linha.split("|")
            if len(partes) == 3:
                print("WA-AKG CPU:", partes[1], "MEM:", partes[2])

    p = run([
        "docker", "exec", "emeca-web-1", "python", "manage.py",
        "shell", "-c", DJANGO,
    ], timeout=26)
    if p is not None and p.returncode == 0:
        d = None
        for linha in p.stdout.splitlines():
            if linha.startswith("WA_EMECA_DIAG:"):
                try:
                    d = json.loads(linha.split(":", 1)[1])
                except json.JSONDecodeError:
                    pass
        if isinstance(d, dict):
            for chave in ("sessao_local_configurada","limpeza_pendente",
                          "lotes_ativos","url_gateway_configurada","acesso_tcp",
                          "consulta_sessao","status_remoto","status_http",
                          "classe_causa"):
                if chave in d:
                    print(chave + ":", d[chave])
        else:
            print("Django: resposta não reconhecida; saída bruta omitida.")
    elif p is not None:
        print("Django: falha técnica (código", p.returncode, "); saída bruta omitida.")

    p = run(["docker", "logs", "--since", "20m", "--tail", "200",
             "wa-akg-app"], timeout=10)
    if p is not None and p.returncode == 0:
        logs = (p.stdout + "\n" + p.stderr).lower()
        patterns = {
            "timeout": "timeout", "connection_refused": "econnrefused",
            "database_error": "prismaclient", "out_of_memory": "heap out of memory",
            "disconnected": "disconnected",
        }
        print("Padrões nos logs recentes (apenas contagens, sem conteúdo):")
        for label, phrase in patterns.items():
            print(" ", label, logs.count(phrase))

    print("NENHUM serviço reiniciado; nenhum dado apagado; nenhum envio realizado.")


if __name__ == "__main__":
    main()
