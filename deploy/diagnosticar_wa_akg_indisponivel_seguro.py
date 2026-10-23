#!/usr/bin/env python3
"""Diagnóstico seguro da disponibilidade do WA-AKG após tentativa de limpeza.

Somente GET local e informações de status. Não acessa mensagens nem destinatários,
não faz POST, não reinicia contêineres, não imprime tokens ou dados pessoais.
"""
import json
import subprocess
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

def docker_state(name):
    try:
        p = subprocess.run(
            ["docker","inspect","--format","{{json .State}}",name],
            capture_output=True, text=True, timeout=6, check=False
        )
        if p.returncode:
            return "não localizado/erro de consulta"
        st=json.loads(p.stdout)
        return (
            f"status={st.get('Status','?')} "
            f"running={st.get('Running',False)} "
            f"restarting={st.get('Restarting',False)} "
            f"oom={st.get('OOMKilled',False)} "
            f"exit={st.get('ExitCode','?')} "
            f"health={(st.get('Health') or {}).get('Status','não configurado')}"
        )
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        return "erro: "+type(exc).__name__

def restarts(name):
    try:
        p=subprocess.run(
            ["docker","inspect","--format","{{.RestartCount}}",name],
            capture_output=True,text=True,timeout=6,check=False
        )
        return p.stdout.strip() if p.returncode == 0 and p.stdout.strip().isdigit() else "?"
    except (subprocess.TimeoutExpired, OSError):
        return "?"

def local_http():
    try:
        req=Request("http://127.0.0.1:3100/",method="GET",
                    headers={"User-Agent":"EMECA-Healthcheck/1.0"})
        with urlopen(req,timeout=5) as r:
            return "HTTP "+str(r.status)+" (servidor web respondeu)"
    except HTTPError as exc:
        return "HTTP "+str(exc.code)+" (servidor respondeu; rota pode exigir autenticação)"
    except (URLError, TimeoutError, ConnectionError, OSError) as exc:
        cause=getattr(exc,"reason",None)
        return "Falha "+type(exc).__name__+(
            " / "+type(cause).__name__ if cause is not None else ""
        )

def current_cleanup():
    code = (
        "import json;"
        "from usuarioSec.sessao_whatsapp import limpeza_historico_pendente;"
        "from usuarioSec.models import EnvioBoletimWhatsApp, SessaoWhatsAppAtiva;"
        "from usuarioSec.whatsapp_gateway import obter_sessao, WhatsAppGatewayError;"
        "resultado={'pendente':limpeza_historico_pendente(),"
        "'registro':SessaoWhatsAppAtiva.objects.filter(chave='secretaria').exists(),"
        "'lotes_ativos':EnvioBoletimWhatsApp.objects.filter(status__in=['PENDENTE','PROCESSANDO']).count()};"
        "\ntry:\n r=obter_sessao(); d=(r.get('data') or {}) if isinstance(r,dict) else {};"
        " resultado['gateway']=str(d.get('status') or 'INDEFINIDO').upper()\n"
        "except WhatsAppGatewayError as e:\n resultado['gateway']='FALHA_CONSULTA';"
        " resultado['http']=e.status_code or 0;"
        " resultado['causa']=type(e.__cause__).__name__ if e.__cause__ else 'não informada'\n"
        "except Exception as e:\n resultado['gateway']='ERRO_LOCAL'; resultado['causa']=type(e).__name__\n"
        "print('EMECA_STATUS_PUBLICAVEL:'+json.dumps(resultado))"
    )
    try:
        p=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",code],
            capture_output=True,text=True,timeout=25,check=False
        )
    except subprocess.TimeoutExpired:
        return "consulta expirou (25 s)"
    except OSError as exc:
        return "erro: "+type(exc).__name__
    if p.returncode:
        return "falha controlada (código "+str(p.returncode)+")"
    for line in p.stdout.splitlines():
        if line.startswith("EMECA_STATUS_PUBLICAVEL:"):
            try:
                d=json.loads(line.split(":",1)[1])
            except json.JSONDecodeError:
                return "resposta ilegível"
            return (
                "limpeza_pendente="+str(d.get("pendente"))+
                " registro_sessao="+str(d.get("registro"))+
                " lotes_ativos="+str(d.get("lotes_ativos"))+
                " gateway="+str(d.get("gateway"))+
                " http="+str(d.get("http","-"))+
                " causa="+str(d.get("causa","-"))
            )
    return "resposta sem marcador"

def main():
    print("=== EMECA / WA-AKG: diagnóstico somente leitura ===")
    for name in ("wa-akg-app","wa-akg-db","emeca-web-1","emeca-whatsapp-worker-1"):
        print(name+":",docker_state(name),"reinícios="+restarts(name))
    print("HTTP host -> WA-AKG (porta 3100):",local_http())
    print("EMECA -> sessão WhatsApp:",current_cleanup())
    print("SEM ENVIO, SEM LOGOUT, SEM LIMPEZA, SEM REINÍCIO, SEM ALTERAÇÃO DE DADOS.")

if __name__ == "__main__":
    main()
