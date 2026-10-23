#!/usr/bin/env python3
"""Diagnóstico seguro de disponibilidade WA-AKG, sem efeitos colaterais.

Somente docker inspect, GET HTTP em localhost e SELECT 1 no MySQL.
Não faz logout, reconexão, limpeza, envio ou leitura de mensagens.
Não mostra segredos, telefones, JIDs ou dados escolares.
"""
import json
import subprocess
import urllib.error
import urllib.request


def cmd(args, limit=9):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=limit,
                           check=False)
    except subprocess.TimeoutExpired:
        return "TEMPO ESGOTADO", ""
    except OSError as e:
        return type(e).__name__, ""
    return ("OK" if p.returncode == 0 else f"FALHA({p.returncode})",
            p.stdout.strip())


def estado(nome):
    st, data = cmd(["docker", "inspect", "--format",
                    "{{json .State}}", nome])
    if st != "OK":
        print(nome, ":", st)
        return
    try:
        obj = json.loads(data)
    except ValueError:
        print(nome, ": resposta inválida")
        return
    health = obj.get("Health") or {}
    print(nome, ":", "estado=", obj.get("Status", "-"),
          "rodando=", obj.get("Running", False),
          "saida=", obj.get("ExitCode", "-"),
          "health=", health.get("Status", "sem-healthcheck"),
          "erro-oom=", obj.get("OOMKilled", False))


def http_gateway():
    try:
        request = urllib.request.Request("http://127.0.0.1:3100/",
                                         headers={"User-Agent": "EMECA-Diagnostico-Local"})
        with urllib.request.urlopen(request, timeout=5) as r:
            print("WA-AKG HTTP local: respondeu", r.status)
    except urllib.error.HTTPError as e:
        # 401/403/404 também provam que o servidor HTTP respondeu.
        print("WA-AKG HTTP local: respondeu", e.code)
    except Exception as e:
        print("WA-AKG HTTP local: FALHA", type(e).__name__)


def banco():
    comando = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -s -uroot "$MYSQL_DATABASE" -e "SELECT 1"'
    st, result = cmd(["docker", "exec", "wa-akg-db", "sh", "-c", comando], limit=9)
    print("WA-AKG MySQL: ", "RESPONDE" if st == "OK" and result == "1" else st)


def main():
    print("=== Estado de infraestrutura WhatsApp (somente leitura) ===")
    estado("wa-akg-app")
    estado("wa-akg-db")
    estado("emeca-web-1")
    estado("emeca-whatsapp-worker-1")
    http_gateway()
    banco()
    print("Nenhum contêiner reiniciado e nenhum dado modificado.")


if __name__ == "__main__":
    main()
