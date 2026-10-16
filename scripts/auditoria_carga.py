#!/usr/bin/env python3
"""Smoke de carga com dados 100% sintéticos para CI.

Não usa dados reais. Mede GETs públicos e escritas concorrentes da matrícula.
"""
import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil((p / 100) * len(ordered)) - 1))
    return ordered[index]


def request_once(url, method="GET", body=None, headers=None, timeout=10):
    inicio = time.perf_counter()
    req = Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            resp.read()
            status = resp.status
    except HTTPError as exc:
        exc.read()
        status = exc.code
    except URLError:
        status = 0
    return status, (time.perf_counter() - inicio) * 1000


def run_batch(name, total, workers, callable_):
    tempos = []
    statuses = []
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(callable_, i) for i in range(total)]
        for future in as_completed(futures):
            status, elapsed = future.result()
            statuses.append(status)
            tempos.append(elapsed)
    duracao = time.perf_counter() - inicio
    ok = sum(1 for status in statuses if 200 <= status < 300)
    erros = total - ok
    resultado = {
        "cenario": name,
        "total": total,
        "workers": workers,
        "ok": ok,
        "erros": erros,
        "p50_ms": round(percentile(tempos, 50), 2),
        "p95_ms": round(percentile(tempos, 95), 2),
        "max_ms": round(max(tempos) if tempos else 0, 2),
        "req_s": round(total / duracao if duracao else 0, 2),
        "status": {str(code): statuses.count(code) for code in sorted(set(statuses))},
    }
    print(json.dumps(resultado, ensure_ascii=False))
    return resultado


def csrf_token(base):
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    with opener.open(base + "/matricula-online/", timeout=10) as resp:
        resp.read()
    for cookie in jar:
        if cookie.name == "csrftoken":
            return cookie.value
    raise RuntimeError("Cookie CSRF não foi emitido pelo frontend de matrícula.")


def payload_matricula(indice):
    return {
        "nomeDoAluno": f"ESTUDANTE SINTETICO CARGA {indice:04d}",
        "dataNascimentoAluno": "2017-01-01",
        "temIrmaosEscola": "NAO",
        "problemaSaude": "NAO",
        "tratamentoSaude": "NAO",
        "necessidadeEspecial": "NAO",
        "medicamento": "NAO",
        "internado": "NAO",
        "atendimentoEspecializado": "NAO",
        "salaRecurso": "NAO",
        "gestacao": "NAO",
        "cras": "NAO",
        "visitaSocial": "NAO",
        "conselhoTutelar": "NAO",
        "atendimentoDomiciliar": "NAO",
        "transporteEscolar": "NAO",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    token = csrf_token(base)
    cookie_header = f"csrftoken={token}"

    resultados = []
    resultados.append(
        run_batch(
            "home_get",
            total=120,
            workers=20,
            callable_=lambda _: request_once(base + "/"),
        )
    )
    resultados.append(
        run_batch(
            "configuracao_get",
            total=120,
            workers=20,
            callable_=lambda _: request_once(base + "/configuracao-site-publica/"),
        )
    )

    def postar(indice):
        body = json.dumps(payload_matricula(indice)).encode("utf-8")
        return request_once(
            base + "/matricula/",
            method="POST",
            body=body,
            headers={
                "Content-Type": "application/json",
                "X-CSRFToken": token,
                "Cookie": cookie_header,
                "User-Agent": "EMECA-Auditoria-Sintetica/1.0",
            },
            timeout=20,
        )

    resultados.append(
        run_batch(
            "matricula_post_concorrente",
            total=30,
            workers=10,
            callable_=postar,
        )
    )

    falhas = sum(item["erros"] for item in resultados)
    print(json.dumps({"resumo": "auditoria_carga", "falhas": falhas}, ensure_ascii=False))
    raise SystemExit(1 if falhas else 0)


if __name__ == "__main__":
    main()
