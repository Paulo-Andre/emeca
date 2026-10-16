#!/usr/bin/env python3
"""Scanner simples de segredos de alta confiança sem imprimir o valor encontrado."""
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    "openai_key": re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    "wa_akg_key": re.compile(rb"wag_[A-Za-z0-9]{20,}"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

SKIP = {
    "scripts/auditoria_segredos.py",
}


def tracked_files():
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [Path(item.decode("utf-8")) for item in raw.split(b"\0") if item]


def main():
    achados = []
    for path in tracked_files():
        nome = path.as_posix()
        if nome in SKIP or not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        for rotulo, pattern in PATTERNS.items():
            for match in pattern.finditer(data):
                linha = data.count(b"\n", 0, match.start()) + 1
                achados.append((nome, linha, rotulo))

    if achados:
        print("Possíveis segredos encontrados (valores ocultados):")
        for nome, linha, rotulo in achados:
            print(f"- {nome}:{linha} [{rotulo}]")
        raise SystemExit(1)

    print("Nenhum segredo de alta confiança encontrado nos arquivos versionados.")


if __name__ == "__main__":
    main()
