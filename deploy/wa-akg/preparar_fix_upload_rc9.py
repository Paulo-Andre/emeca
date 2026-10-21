#!/usr/bin/env python3
"""Preparar patch do uploader Baileys rc.9 no código WA-AKG, sem construir ou reiniciar.

O Dockerfile aplicará o patch APÓS npm ci, antes de next build. A versão da
biblioteca não muda. Guardas impedem patch em rc14 ou fonte diferente.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
import datetime as dt


def preparar(source: Path, script: Path, dry_run: bool) -> list[str]:
    source = source.resolve()
    dockerfile = source / "Dockerfile"
    pkg_file = source / "package.json"
    lock_file = source / "package-lock.json"
    patch_file = source / "emeca-patches" / "patch-baileys-rc9.cjs"
    if any(not p.is_file() for p in (dockerfile, pkg_file, lock_file, script)):
        raise RuntimeError("Dockerfile, manifestos ou patch não encontrados; nenhuma escrita")

    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    version = lock.get("packages", {}).get("node_modules/@whiskeysockets/baileys", {}).get("version")
    if version != "7.0.0-rc.9":
        raise RuntimeError(
            "Lockfile contém Baileys %r, esperado 7.0.0-rc.9. "
            "Instalação CANCELADA para não mudar versões." % version
        )
    dep = pkg.get("dependencies", {}).get("@whiskeysockets/baileys")
    if dep not in ("7.0.0-rc.9", "7.0.0-rc9", "^7.0.0-rc.9"):
        raise RuntimeError(
            "Versão declarada no manifesto %r difere do lock. "
            "Nenhuma atualização automática de pacote." % dep
        )

    before = dockerfile.read_text(encoding="utf-8")
    old_line = "RUN npx prisma generate && npm run build"
    new_line = "RUN node emeca-patches/patch-baileys-rc9.cjs && npx prisma generate && npm run build"
    if before.count(new_line) == 1:
        after = before
    elif before.count(old_line) == 1:
        after = before.replace(old_line, new_line, 1)
    else:
        raise RuntimeError("Dockerfile desconhecido ou duplicado; nenhum arquivo alterado.")

    source_patch = script.read_text(encoding="utf-8")
    if "EMECA_BAILEYS_RC9_UPLOAD_V1" not in source_patch:
        raise RuntimeError("Patch do Baileys inválido")
    if patch_file.exists() and patch_file.read_text(encoding="utf-8") != source_patch:
        raise RuntimeError("Existe patch diferente no WA-AKG; não sobrescrevendo")

    changes = []
    if before != after:
        changes.append("Dockerfile: aplicar patch após npm ci")
    if not patch_file.exists():
        changes.append("emeca-patches/patch-baileys-rc9.cjs: criar patch")
    if not changes:
        print("Código WA-AKG já preparado; nenhuma alteração necessária")
        return []
    print("Arquivos a preparar:", *changes, sep="\n - ")
    if dry_run:
        print("Somente leitura: nenhuma alteração")
        return changes

    backup_dir = source / ".emeca-backups" / ("uploader-rc9-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(dockerfile, backup_dir / "Dockerfile")
    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text(source_patch, encoding="utf-8")
    dockerfile.write_text(after, encoding="utf-8")
    print("Preparação concluída. Backup do Dockerfile em:", backup_dir)
    print("Nenhum contêiner, volume, banco ou credencial foi alterado.")
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/srv/projetos/wa-akg"))
    parser.add_argument("--dry-run", action="store_true")
    opts = parser.parse_args()
    script = Path(__file__).with_name("patch-baileys-rc9.cjs")
    preparar(opts.source, script, opts.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERRO:", str(exc), file=sys.stderr)
        sys.exit(1)
