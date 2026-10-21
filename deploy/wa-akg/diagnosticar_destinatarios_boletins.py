#!/usr/bin/env python3
"""Verificação controlada de destinatários dos últimos boletins.
Não envia mensagens. Consulta presença de ATÉ 4 números no WhatsApp.
Não altera dados locais, nem exibe nomes, telefones, JIDs ou PDF.
"""
import json
import subprocess

QUERY = r'''
import json
from usuarioSec.models import ItemEnvioBoletimWhatsApp, TelefoneDeclaracao
from usuarioSec.whatsapp_views import _normalizar_jid
from usuarioSec.whatsapp_gateway import verificar_numeros, WhatsAppGatewayError
from usuarioSec.sessao_whatsapp import sessao_atual_id

items = list(
    ItemEnvioBoletimWhatsApp.objects.select_related(
        "envio", "boletim__aluno"
    ).filter(status="ENVIADO").order_by("-envio_id","-id")[:4]
)
saida=[]
for item in items:
    dado={
        "lote":item.envio_id,
        "situacao":"NAO_CONFERIDO",
        "sessao_correta": item.envio.sessao == sessao_atual_id(),
        "cadastro_consistente":False,
    }
    declaracao_id = item.boletim.aluno.declaracao_id
    if declaracao_id:
        telefones=TelefoneDeclaracao.objects.filter(declaracao_id=declaracao_id).values_list("telefone",flat=True)
        dado["cadastro_consistente"]=any(_normalizar_jid(t) == item.jid for t in telefones)
    if not item.jid.endswith("@s.whatsapp.net"):
        dado["situacao"]="FORMATO_DESTINATARIO_INESPERADO"
        saida.append(dado)
        continue
    numero=item.jid.split("@")[0]
    if not numero.isdigit() or len(numero) not in (12,13):
        dado["situacao"]="FORMATO_NUMERO_INVALIDO"
        saida.append(dado)
        continue
    if not dado["sessao_correta"]:
        dado["situacao"]="LOTE_DE_OUTRA_SESSAO"
        saida.append(dado)
        continue
    try:
        resposta=verificar_numeros([numero])
        dados=resposta.get("data") if isinstance(resposta,dict) else {}
        resultados=dados.get("results") if isinstance(dados,dict) else []
        registro=resultados[0] if isinstance(resultados,list) and resultados else {}
        if not isinstance(registro,dict):
            dado["situacao"]="RETORNO_INVALIDO"
        elif registro.get("exists") is True:
            real=registro.get("jid") or ""
            if real == item.jid:
                dado["situacao"]="REGISTRO_CONFIRMADO"
                dado["tipo_divergencia"]="NENHUMA"
            else:
                dado["situacao"]="REGISTRO_JID_DIFERENTE"
                if str(real).endswith("@lid"):
                    dado["tipo_divergencia"]="LID_SEM_RELACAO_COMPROVADA"
                elif str(real).endswith("@s.whatsapp.net"):
                    recebido=str(real).split("@")[0]
                    entrada=numero
                    maior,menor=sorted((entrada,recebido),key=len,reverse=True)
                    if (maior.isdigit() and menor.isdigit()
                        and len(maior)==13 and len(menor)==12
                        and maior[:4]==menor[:4]
                        and maior[4]=="9"
                        and maior[5:]==menor[4:]):
                        dado["tipo_divergencia"]="APENAS_NONO_DIGITO_BR"
                    else:
                        dado["tipo_divergencia"]="DDD_OU_ASSINANTE_DIFERENTE"
                else:
                    dado["tipo_divergencia"]="JID_NAO_TELEFONICO"
        elif registro.get("exists") is False:
            dado["situacao"]="NUMERO_NAO_ENCONTRADO"
        else:
            dado["situacao"]="RESULTADO_INCONCLUSIVO"
    except WhatsAppGatewayError as e:
        dado["situacao"]="FALHA_NA_CONSULTA"
        dado["codigo_http"]=int(e.status_code or 0)
    except Exception as e:
        dado["situacao"]="ERRO_TECNICO"
        dado["classe_erro"]=type(e).__name__
    saida.append(dado)
print("EMECA_VERIFICACAO_DESTINATARIOS:"+json.dumps(saida,ensure_ascii=False))
'''

def main():
    print("=== Auditoria de destinatários de boletins (sem reenvio) ===")
    print("Consultando presença WhatsApp de até 4 destinatários já usados nos lotes.")
    try:
        proc=subprocess.run(
            ["docker","exec","emeca-web-1","python","manage.py","shell","-c",QUERY],
            text=True,capture_output=True,timeout=55,check=False,
        )
    except subprocess.TimeoutExpired:
        print("Consulta excedeu limite de tempo. Nenhuma mensagem enviada.")
        return
    except OSError as e:
        print("Falha ao iniciar:",type(e).__name__)
        return
    if proc.returncode:
        print("Consulta falhou (código)",proc.returncode,
              "— detalhes não apresentados por privacidade.")
        return
    for line in proc.stdout.splitlines():
        if not line.startswith("EMECA_VERIFICACAO_DESTINATARIOS:"):
            continue
        try: dados=json.loads(line.split(":",1)[1])
        except ValueError: break
        if not isinstance(dados,list): break
        if not dados:
            print("Nenhum boletim marcado como aceito para conferir.")
        for item in dados:
            if not isinstance(item,dict):continue
            print("Lote",item.get("lote"),"| registro WhatsApp:",item.get("situacao"),
                  "| sessão correta:",item.get("sessao_correta"),
                  "| telefone vinculado ao aluno:",item.get("cadastro_consistente"),
                  "| divergência:",item.get("tipo_divergencia","—"),
                  "| HTTP:",item.get("codigo_http","—"))
        print("O WhatsApp pode confirmar um registro sem comprovar a entrega da mensagem.")
        print("SEM ENVIO DE PDF, SEM ALTERAÇÃO DO BANCO E SEM REINÍCIO.")
        return
    print("Resposta de diagnóstico inesperada; dados sensíveis omitidos.")

if __name__=="__main__":
    main()
