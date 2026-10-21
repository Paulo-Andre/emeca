#!/usr/bin/env python3
"""Preparação isolada de HTTPS nativo no Baileys rc.9, sem reiniciar nada."""
import argparse
import json
from pathlib import Path
import shutil
import datetime as dt
import sys


def preparar(source: Path, patch: Path, dry_run: bool):
    source=source.resolve()
    dockerfile=source/"Dockerfile"
    manifest=source/"package.json"
    lockfile=source/"package-lock.json"
    dest=source/"emeca-patches"/"patch-baileys-rc9-https.cjs"
    if not all(f.is_file() for f in [dockerfile,manifest,lockfile,patch]):
        raise RuntimeError("Dockerfile, pacote/lock ou patch não encontrados")
    package=json.loads(manifest.read_text())
    lock=json.loads(lockfile.read_text())
    if package.get("dependencies",{}).get("@whiskeysockets/baileys")!="7.0.0-rc.9" or (
        lock.get("packages",{}).get("node_modules/@whiskeysockets/baileys",{}).get("version")!="7.0.0-rc.9"
    ):
        raise RuntimeError("Dependência local não é exatamente Baileys rc.9; sem alterações")

    original=dockerfile.read_text()
    old_build="RUN node emeca-patches/patch-baileys-rc9.cjs && npx prisma generate && npm run build"
    new_build="RUN node emeca-patches/patch-baileys-rc9.cjs && node emeca-patches/patch-baileys-rc9-https.cjs && npx prisma generate && npm run build"
    old_final="\nRUN node emeca-patches/patch-baileys-rc9.cjs\n"
    new_final="\nRUN node emeca-patches/patch-baileys-rc9.cjs && node emeca-patches/patch-baileys-rc9-https.cjs\n"
    if original.count(new_build)==1:
        updated=original
    elif original.count(old_build)==1:
        updated=original.replace(old_build,new_build,1)
    else:
        raise RuntimeError("Etapa de build alterada; abortando")
    if updated.count(new_final)==1:
        pass
    elif updated.count(old_final)==1:
        updated=updated.replace(old_final,new_final,1)
    else:
        raise RuntimeError("Etapa final do Dockerfile alterada; abortando")
    v2=patch.read_bytes()
    if b"EMECA_RC9_HTTPS_UPLOAD_V2" not in v2:
        raise RuntimeError("Patch não identificado")
    existing=dest.read_bytes() if dest.is_file() else None
    if existing is not None and existing!=v2:
        raise RuntimeError("Patch HTTPS diferente já existente, requer revisão")
    changes=[]
    if updated!=original:changes.append("Dockerfile: aplicar V2 após V1 nas duas etapas")
    if existing!=v2:changes.append("emeca-patches: criar patch HTTPS V2")
    if not changes:
        print("Arquivos já preparados; nenhuma modificação")
        return
    print("Alterações:",*changes,sep="\n - ")
    if dry_run:
        print("Prévia concluída, nenhuma modificação")
        return
    timestamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup=source/".emeca-backups"/("https-rc9-"+timestamp)
    backup.mkdir(parents=True,exist_ok=False)
    shutil.copy2(dockerfile,backup/"Dockerfile")
    dest.parent.mkdir(parents=True,exist_ok=True)
    if existing is not None:shutil.copy2(dest,backup/dest.name)
    dest.write_bytes(v2)
    dockerfile.write_text(updated)
    print("Código de build preparado; backup:",backup)
    print("Nenhum contêiner, volume, banco ou sessão modificado.")


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,default=Path("/srv/projetos/wa-akg"))
    ap.add_argument("--dry-run",action="store_true")
    args=ap.parse_args()
    try:
        preparar(args.source,Path(__file__).with_name("patch-baileys-rc9-https.cjs"),args.dry_run)
    except Exception as e:
        print("ERRO:",str(e),file=sys.stderr)
        sys.exit(1)
